"""Execute one frozen cohort on a hosted runner and persist public results.

Each cohort has its own VM. Paired modes run sequentially. Raw datasets,
prompts, model weights and credentials are never added to Git.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, ExitStack
import importlib.metadata
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NATIVE = "benchmarks/native-recovery-20261112-manifest.json"
SEMANTIC = "benchmarks/semantic-recovery-20261112-manifest.json"
ANSWERS = "benchmarks/local-answer-recovery-manifest.json"
BASELINE = "5abc85eef00097555366f8524fc81f8b5711ad7a"
CANDIDATE = "407cda1c5f1dac0e67dfe527d3c23febdad5e818"
HOSTED_EXECUTION_SECONDS = 330 * 60
_DEADLINE = None
_LOCK_FD = None


class ValidationInterrupted(BaseException):
    """Controlled execution interruption, never a completed measurement."""

    def __init__(self, reason, exit_code=124):
        self.reason, self.exit_code = reason, exit_code


@contextmanager
def interrupt_handlers():
    def stop(signum, _frame):
        # Preserve one interruption and give the owned child time to flush.
        for candidate in (signal.SIGINT, signal.SIGTERM):
            signal.signal(candidate, signal.SIG_IGN)
        raise ValidationInterrupted("signal_" + signal.Signals(signum).name, 128 + signum)
    old = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


@contextmanager
def cleanup_signals():
    # A second controlled signal must not interrupt atomic audit publication.
    # SIGKILL or runner loss cannot be handled and remains a documented limit.
    old = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)



@contextmanager
def execution_timer(seconds):
    # Linux hosted jobs also need a deadline during in-process preparation.
    if seconds is None or not hasattr(signal, "setitimer"):
        yield
        return
    def expire(_signum, _frame):
        raise ValidationInterrupted("execution_deadline")
    old_handler = signal.signal(signal.SIGALRM, expire)
    old_timer = signal.setitimer(signal.ITIMER_REAL, max(seconds, .001))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, *old_timer)


def stop_process(process):
    if process.poll() is None:
        if os.name == "nt":
            process.terminate()
        else:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if os.name != "nt":
        # The process owns this group; terminate only its possible descendants.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        time.sleep(.1)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

def run(argv, check=True, timeout_seconds=None, *, enforce_deadline=True):
    print(json.dumps({"event": "command", "argv": list(map(str, argv))}), flush=True)
    timeout, reason = timeout_seconds, "registered_phase_timeout"
    if enforce_deadline and _DEADLINE is not None:
        remaining = _DEADLINE - time.monotonic()
        if remaining <= 0:
            raise ValidationInterrupted("execution_deadline")
        if timeout is None or remaining < timeout:
            timeout, reason = remaining, "execution_deadline"
    options = {"start_new_session": True} if os.name != "nt" else {}
    if os.name != "nt" and _LOCK_FD is not None:
        options["pass_fds"] = (_LOCK_FD,)
    with subprocess.Popen(list(map(str, argv)), cwd=ROOT, **options) as process:
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_process(process)
            raise ValidationInterrupted(reason) from None
        except BaseException:
            stop_process(process)
            raise
    if check and code:
        raise subprocess.CalledProcessError(code, list(map(str, argv)))
    return code

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def registered_stages(path):
    return json.loads((ROOT / path).read_bytes())["stages"]

def choices():
    return (["native-" + s["id"] for s in registered_stages(NATIVE)]
            + ["semantic-" + s["id"] for s in registered_stages(SEMANTIC)]
            + ["answers-locomo", "answers-hotpotqa", "workflow-transfer36"])

def snapshot(path, revision):
    path = ROOT / path
    if path.exists():
        if git("-C", str(path), "rev-parse", "HEAD") != revision:
            raise ValueError("Existing frozen source has another commit")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "worktree", "add", "--detach", path, revision])

def prepare(stage):
    snapshot(".artifacts/native-baseline-5abc", BASELINE)
    snapshot(".artifacts/native-completion-candidate", CANDIDATE)
    run([sys.executable, "-m", "benchmarks.prepare_native_data"])
    from benchmarks.token_compare import TokenCounter
    for name in ("cl100k_base", "o200k_base"):
        TokenCounter(name).count("explicit tokenizer preparation")
    if stage.startswith(("semantic-", "answers-")):
        run([sys.executable, "scripts/prepare_semantic_model.py"])
    if stage.startswith(("answers-", "workflow-")):
        run([sys.executable, "scripts/prepare_local_answer_model.py"])
    if stage.startswith("workflow-"):
        from benchmarks.competitors.ai_memory import prepare as binary, prepare_models
        cache = ROOT / ".artifacts/competitors/ai-memory"
        binary(cache)
        prepare_models(cache)

def manifest_stage(stage):
    family, original_id = stage.split("-", 1)
    source = NATIVE if family == "native" else SEMANTIC
    manifest = json.loads((ROOT / source).read_bytes())
    selected = [s for s in manifest["stages"] if s["id"] == original_id]
    if len(selected) != 1:
        raise ValueError("Stage must uniquely match the registered manifest")
    manifest["stages"] = selected
    manifest["cwd"] = "../../.."
    manifest["description"] = ("Unchanged registered cohort on one isolated hosted runner. "
                               "Do not pool latency across hosts. Parent: " + source)
    path = ROOT / ".artifacts/hosted/manifests" / (stage + ".json")
    atomic(path, manifest)
    checkpoint = "benchmarks/reports/hosted-" + stage + "-checkpoint.json"
    command = [sys.executable, "-u", "-m", "benchmarks.resume",
               "--manifest", str(path), "--checkpoint", checkpoint]
    return command, selected[0]["outputs"] + [checkpoint], source

def answer_stage(stage):
    cohort = stage.removeprefix("answers-")
    steps = {s["id"]: s for s in registered_stages(ANSWERS)}
    codes = {}
    for phase in ("prepare", "generate", "export"):
        command = [sys.executable if x == "{python}" else x
                   for x in steps[phase + "-" + cohort]["argv"]]
        codes[phase] = run(command, check=False, timeout_seconds=steps[phase + "-" + cohort]["timeout_seconds"])
        if codes[phase] and phase != "generate":
            break
        if codes[phase] and phase == "generate":
            summary = ROOT / (".artifacts/local-answer-evaluation/" + cohort
                              + "/registered-run.summary.json")
            if not summary.exists():
                break  # Never replay an uncertain model request.
    return codes, steps["export-" + cohort]["outputs"]

def environment():
    cpu = None
    path = Path("/proc/cpuinfo")
    if path.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
                    if line.startswith("model name")), None)
    return {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(), "cpu_model": cpu, "logical_cpus": os.cpu_count(),
            "runner_os": os.environ.get("RUNNER_OS"), "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion"),
            "packages": sorted({(item.metadata.get("Name", ""), item.version)
                                for item in importlib.metadata.distributions()
                                if re.fullmatch(r"[A-Za-z0-9_.-]+", item.metadata.get("Name", ""))
                                and re.fullmatch(r"[A-Za-z0-9_.+!-]+", item.version)})}

def public_paths(stage):
    family, cohort = stage.split("-", 1)
    if family in {"native", "semantic"}:
        source = NATIVE if family == "native" else SEMANTIC
        selected = [row for row in registered_stages(source) if row["id"] == cohort]
        if len(selected) != 1:
            raise ValueError("Unregistered stage")
        paths = selected[0]["outputs"] + ["benchmarks/reports/hosted-" + stage + "-checkpoint.json"]
    elif family == "answers":
        selected = [row for row in registered_stages(ANSWERS) if row["id"] == "export-" + cohort]
        if len(selected) != 1:
            raise ValueError("Unregistered answer cohort")
        paths = selected[0]["outputs"]
    elif stage == "workflow-transfer36":
        paths = ["benchmarks/results/full-workflow-transfer36.json",
                 "benchmarks/results/full-workflow-transfer36-assessment.json",
                 "benchmarks/RESULTS-full-workflow.md"]
    else:
        raise ValueError("Unregistered stage")
    return list(paths)


def marker_path(stage):
    return ROOT / ("benchmarks/reports/hosted-" + stage + "-completion.json")


def diagnostic_paths(stage):
    directory = ROOT / "benchmarks/reports"
    expression = re.compile(re.escape("hosted-" + stage + "-interrupted-") + r"[0-9]+\.json")
    return sorted(path for path in directory.glob("hosted-" + stage + "-interrupted-*.json")
                  if expression.fullmatch(path.name) and path.is_file() and not path.is_symlink())


def write_diagnostic(stage):
    if not stage.startswith(("answers-", "workflow-")):
        return []
    from benchmarks.export_interrupted_validation import (
        answer_diagnostic, workflow_diagnostic, sensitive_environment_values)
    secrets = sensitive_environment_values()
    if stage.startswith("answers-"):
        root = ROOT / ".artifacts/local-answer-evaluation" / stage.removeprefix("answers-")
        value = answer_diagnostic(root / "registered-run.jsonl", root / "registered-run.server.json",
                                  root / "prepared.json", secrets)
    else:
        root = ROOT / ".artifacts/full-workflow"
        value = workflow_diagnostic(root / "checkpoint.json", root / "native-model-trace.jsonl",
                                    root / "model-server-verification.jsonl",
                                    ROOT / "benchmarks/experiments/full-workflow-answers.json", secrets)
    existing = diagnostic_paths(stage)
    for path in existing:
        if json.loads(path.read_bytes()) == value:
            return [str(item.relative_to(ROOT)) for item in existing]
    # Preserve each different snapshot; never overwrite prior measured intents.
    sequence = max((int(path.stem.rsplit("-", 1)[1]) for path in existing), default=0) + 1
    target = ROOT / ("benchmarks/reports/hosted-" + stage + "-interrupted-" + str(sequence) + ".json")
    atomic(target, value)
    return [str(path.relative_to(ROOT)) for path in existing + [target]]


def safe_public_files(stage, marker, extra=()):
    allowed = set(public_paths(stage)) | {str(marker.relative_to(ROOT))}
    allowed.update(str(path.relative_to(ROOT)) for path in diagnostic_paths(stage))
    selected = []
    for item in sorted(set(public_paths(stage)) | {str(marker.relative_to(ROOT))} | set(extra)):
        if item not in allowed:
            raise ValueError("Refusing an unregistered public output path")
        path = ROOT / item
        if path.is_symlink():
            raise ValueError("Refusing a symlink in public output paths")
        if not path.is_file():
            continue
        path.resolve().relative_to((ROOT / "benchmarks").resolve())
        if not (item.startswith("benchmarks/results/") or item.startswith("benchmarks/reports/")
                or item == "benchmarks/RESULTS-full-workflow.md"):
            raise ValueError("Refusing a non-report publication")
        selected.append(item)
    return selected


def publication_command(*args, env=None, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if check and result.returncode:
        # Git diagnostics can contain credential-bearing remote URLs.
        raise RuntimeError("Publication Git operation failed")
    return result


def publish(stage, marker, paths):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")
    if not run_id or not run_id.isdigit() or not attempt or not attempt.isdigit():
        raise ValueError("Publishing requires a GitHub Actions run identity")
    branch = "validation/20261112-" + stage + "-" + run_id + "-" + attempt
    files = safe_public_files(stage, marker, paths)
    source = publication_command("rev-parse", "HEAD").stdout.strip()
    remote = publication_command("ls-remote", "--heads", "origin", "refs/heads/" + branch).stdout.strip()
    base = source
    if remote:
        base = remote.split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise ValueError("Unexpected remote publication identity")
        publication_command("fetch", "--no-tags", "origin", "refs/heads/" + branch)
        if publication_command("merge-base", "--is-ancestor", source, base, check=False).returncode:
            raise ValueError("Publication branch does not descend from this source")
    cache = ROOT / ".artifacts/hosted/publications"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        publication_command("read-tree", base, env=environment)
        publication_command("add", "--", *files, env=environment)
        tree = publication_command("write-tree", env=environment).stdout.strip()
        old_tree = publication_command("rev-parse", base + "^{tree}").stdout.strip()
        commit, changed = base, tree != old_tree
        if changed:
            body = Path(temporary) / "message.txt"
            body.write_text("bench: preserve " + stage + " hosted validation\n", encoding="utf-8")
            commit = publication_command("-c", "user.name=github-actions[bot]",
                "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit-tree", tree, "-p", base, "-F", str(body), env=environment).stdout.strip()
        if changed or not remote:
            # No force push. A competing writer must not be overwritten.
            publication_command("push", "origin", commit + ":refs/heads/" + branch)
    atomic(cache / (stage + "-" + run_id + "-" + attempt + ".json"),
           {"branch": branch, "commit": commit, "public_files": files})
    print(json.dumps({"event": "published", "branch": branch, "commit": commit,
                      "changed": changed}), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and changed:
        with open(summary, "a") as stream:
            stream.write("Saved [" + stage + "](https://github.com/" + os.environ["GITHUB_REPOSITORY"]
                         + "/tree/" + branch + ").\n")
    return commit



def public_marker(stage, metadata):
    """Whitelist marker fields, including legacy nested environment records."""
    from benchmarks.export_interrupted_validation import sensitive_environment_values
    secrets = sensitive_environment_values()
    def object_hash(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def text(value, pattern=None, limit=512):
        return (isinstance(value, str) and len(value) <= limit
                and not any(secret in value for secret in secrets)
                and (re.fullmatch(pattern, value) is not None if pattern else
                     "\n" not in value and "\r" not in value and "://" not in value))
    def numeric(value):
        return ((isinstance(value, int) and not isinstance(value, bool))
                or (isinstance(value, float) and math.isfinite(value)))
    output = {"schema_version": 2, "stage": stage}
    if isinstance(metadata.get("status"), str) and metadata["status"] in {"running", "completed", "failed", "interrupted"}:
        output["status"] = metadata["status"]
    for field in ("started_at", "prepared_at", "finished_at"):
        if text(metadata.get(field), r"[0-9TZ:+.-]+", 48):
            output[field] = metadata[field]
    if text(metadata.get("source_commit"), r"[0-9a-f]{40}"):
        output["source_commit"] = metadata["source_commit"]
    for field in ("prior_marker_sha256", "parent_manifest_sha256", "argv_sha256",
                  "environment_omissions_sha256"):
        if isinstance(metadata.get(field), str) and re.fullmatch(r"[0-9a-f]{64}", metadata[field]):
            output[field] = metadata[field]
    if "argv" in metadata:
        output["argv_sha256"] = object_hash(metadata["argv"])
    if isinstance(metadata.get("parent_manifest"), str) and metadata["parent_manifest"] in {NATIVE, SEMANTIC, ANSWERS}:
        output["parent_manifest"] = metadata["parent_manifest"]
    for field in ("error_type", "diagnostic_export_error_type"):
        if text(metadata.get(field), r"[A-Za-z_][A-Za-z_0-9]*", 100):
            output[field] = metadata[field]
    for field in ("exit_code", "assessment_exit_code"):
        if isinstance(metadata.get(field), int) and not isinstance(metadata[field], bool):
            output[field] = metadata[field]
    if isinstance(metadata.get("phase_exit_codes"), dict):
        output["phase_exit_codes"] = {
            key: value for key, value in metadata["phase_exit_codes"].items()
            if key in {"prepare", "generate", "export"} and isinstance(value, int) and not isinstance(value, bool)}
    known_reasons = {"execution_deadline", "registered_phase_timeout", "signal_SIGINT",
                     "signal_SIGTERM", "KeyboardInterrupt", "invalid_prior_marker",
                     "runner_marker_missing", "cleanup_after_unfinished_runner"}
    if isinstance(metadata.get("interruption"), str) and metadata["interruption"] in known_reasons:
        output["interruption"] = metadata["interruption"]
    if metadata.get("publication_incomplete") is True:
        output["publication_incomplete"] = True
    if "timing_boundary" in metadata:
        output["timing_boundary"] = ("One isolated hosted runner; paired modes are sequential. "
                                     "Do not pool timings across hosts.")
    deadline = metadata.get("execution_deadline")
    if isinstance(deadline, dict):
        output["execution_deadline"] = {
            key: value for key, value in deadline.items()
            if key in {"seconds_available_at_runner_start", "hosted_job_hard_limit_seconds",
                       "registered_answer_generate_timeout_seconds"}
            and (value is None or numeric(value))}
        output["execution_deadline"]["scope"] = (
            "Execution deadline only; no model, prompt, cohort, budget or scoring parameter changes. "
            "Expiry is interrupted, never complete.")
    environment = metadata.get("environment")
    if isinstance(environment, dict):
        cleaned = {key: value for key, value in environment.items()
                   if key in {"python", "sqlite", "platform", "cpu_model", "runner_os", "runner_arch",
                              "image_os", "image_version"} and (value is None or text(value))}
        if isinstance(environment.get("logical_cpus"), int) and not isinstance(environment["logical_cpus"], bool):
            cleaned["logical_cpus"] = environment["logical_cpus"]
        packages = environment.get("packages")
        if isinstance(packages, (list, tuple)):
            cleaned["packages"] = [list(pair) for pair in packages
                if isinstance(pair, (list, tuple)) and len(pair) == 2
                and text(pair[0], r"[A-Za-z0-9_.-]+") and text(pair[1], r"[A-Za-z0-9_.+!-]+")]
        if object_hash(cleaned) != object_hash(environment):
            output["environment_omissions_sha256"] = object_hash(environment)
        output["environment"] = cleaned
    allowed = set(public_paths(stage)) | {str(path.relative_to(ROOT)) for path in diagnostic_paths(stage)}
    for field in ("missing_outputs", "diagnostic_outputs"):
        if isinstance(metadata.get(field), list):
            output[field] = [path for path in metadata[field] if isinstance(path, str) and path in allowed]
    hashes = metadata.get("public_output_sha256")
    if isinstance(hashes, dict):
        output["public_output_sha256"] = {
            key: value for key, value in hashes.items()
            if key in allowed and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)}
    return output


def finalize(stage, do_publish=False, metadata=None):
    marker = marker_path(stage)
    if metadata is None:
        if marker.exists():
            try:
                metadata = json.loads(marker.read_bytes())
                if not isinstance(metadata, dict) or metadata.get("stage") != stage:
                    raise ValueError
            except (ValueError, UnicodeError):
                metadata = {"schema_version": 2, "stage": stage, "status": "interrupted",
                            "prior_marker_sha256": sha(marker), "interruption": "invalid_prior_marker"}
        else:
            metadata = {"schema_version": 2, "stage": stage, "status": "interrupted",
                        "interruption": "runner_marker_missing"}
    metadata = public_marker(stage, metadata)
    if metadata.get("status") not in {"completed", "failed", "interrupted"}:
        metadata.update(status="interrupted", interruption="cleanup_after_unfinished_runner")
    metadata.setdefault("finished_at", now())
    paths = public_paths(stage)
    try:
        diagnostics = write_diagnostic(stage)
        metadata["diagnostic_outputs"] = diagnostics
        paths += diagnostics
    except Exception as exc:
        metadata["diagnostic_export_error_type"] = type(exc).__name__
        if metadata["status"] == "completed":
            metadata["publication_incomplete"] = True
    metadata["public_output_sha256"] = {p: sha(ROOT / p) for p in paths if (ROOT / p).is_file()}
    atomic(marker, metadata)
    if do_publish:
        publish(stage, marker, paths)
    return metadata


def execution_budget(seconds):
    budget = seconds
    if budget is None and os.environ.get("GITHUB_ACTIONS") == "true":
        budget = HOSTED_EXECUTION_SECONDS
    absolute = os.environ.get("MEMORY_VALIDATION_DEADLINE_UNIX")
    if absolute:
        remaining = float(absolute) - time.time()
        budget = remaining if budget is None else min(budget, remaining)
    if budget is not None and not math.isfinite(budget):
        raise ValueError("Execution deadline must be finite")
    return budget


def main(argv=None):
    global _DEADLINE, _LOCK_FD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=choices(), required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--finalize", action="store_true",
                        help="Export and publish diagnostics only; never execute or replay a cohort")
    parser.add_argument("--wall-time-seconds", type=float,
                        help="Execution deadline, separate from registered model/scoring parameters")
    args = parser.parse_args(argv)
    if args.wall_time_seconds is not None and (not math.isfinite(args.wall_time_seconds)
                                               or args.wall_time_seconds <= 0):
        parser.error("Execution wall budget must be finite and positive")
    os.chdir(ROOT)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(ROOT / ".artifacts/tiktoken")
    lock_path = ROOT / ".artifacts/hosted/locks" / args.stage
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    from benchmarks.resume import _lock
    with _lock(lock_path) as lock:
        _LOCK_FD = lock.fileno()
        try:
            if args.finalize:
                with cleanup_signals():
                    finalize(args.stage, args.publish)
                return 0
            marker = marker_path(args.stage)
            if marker.exists():
                raise ValueError("Stage marker exists; preserve it and finalize instead of replaying")
            metadata = {"schema_version": 2, "stage": args.stage, "status": "running",
                        "started_at": now(),
                        "timing_boundary": "One isolated hosted runner; paired modes are sequential. Do not pool timings across hosts."}
            # Durable intent precedes environment collection, downloads or model work.
            atomic(marker, public_marker(args.stage, metadata))
            exit_code = 1
            try:
                with interrupt_handlers(), ExitStack() as resources:
                    budget = execution_budget(args.wall_time_seconds)
                    _DEADLINE = time.monotonic() + budget if budget is not None else None
                    metadata.update(source_commit=git("rev-parse", "HEAD"), environment=environment(),
                        execution_deadline={"seconds_available_at_runner_start": budget,
                            "hosted_job_hard_limit_seconds": 21600 if os.environ.get("GITHUB_ACTIONS") == "true" else None,
                            "registered_answer_generate_timeout_seconds": 28800,
                            "scope": "Execution deadline only; no model, prompt, cohort, budget or scoring parameter changes. Expiry is interrupted, never complete."})
                    atomic(marker, public_marker(args.stage, metadata))
                    if budget is not None and budget <= 0:
                        raise ValidationInterrupted("execution_deadline")
                    resources.enter_context(execution_timer(budget))
                    if args.publish:
                        # Preserve started intent remotely before any model work.
                        publish(args.stage, marker, [])
                    prepare(args.stage)
                    metadata["prepared_at"] = now()
                    atomic(marker, public_marker(args.stage, metadata))
                    if args.stage.startswith(("native-", "semantic-")):
                        command, _, parent = manifest_stage(args.stage)
                        metadata.update(parent_manifest=parent, parent_manifest_sha256=sha(ROOT / parent), argv=command)
                        atomic(marker, public_marker(args.stage, metadata))
                        exit_code = run(command, check=False)
                    elif args.stage.startswith("answers-"):
                        codes, _ = answer_stage(args.stage)
                        metadata["phase_exit_codes"] = codes
                        exit_code = 0 if len(codes) == 3 and all(v == 0 for v in codes.values()) else 1
                    else:
                        paths = public_paths(args.stage)
                        exit_code = run([sys.executable, "-u", "-m", "benchmarks.full_workflow_eval",
                                         "--launch-server"], check=False)
                        if (ROOT / paths[0]).is_file():
                            assessment_exit = run([sys.executable, "scripts/summarize_workflow.py"], check=False)
                            metadata["assessment_exit_code"] = assessment_exit
                            exit_code = max(exit_code, assessment_exit)
                    missing = [p for p in public_paths(args.stage) if not (ROOT / p).is_file()]
                    metadata.update(status="completed" if exit_code == 0 and not missing else "failed",
                                    exit_code=exit_code, missing_outputs=missing)
                    if missing:
                        exit_code = max(exit_code, 1)
            except ValidationInterrupted as exc:
                exit_code = exc.exit_code
                metadata.update(status="interrupted", interruption=exc.reason, exit_code=exit_code)
            except KeyboardInterrupt:
                exit_code = 130
                metadata.update(status="interrupted", interruption="KeyboardInterrupt", exit_code=exit_code)
            except Exception as exc:
                exit_code = 1
                metadata.update(status="failed", error_type=type(exc).__name__, exit_code=exit_code)
            finally:
                _DEADLINE = None
                with cleanup_signals():
                    finalize(args.stage, args.publish, metadata)
            return exit_code
        finally:
            _DEADLINE, _LOCK_FD = None, None


if __name__ == "__main__":
    sys.exit(main())
