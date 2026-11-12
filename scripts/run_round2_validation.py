"""Run the registered stages sequentially on one host and persist every stage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import round2_data
from benchmarks.round2_eval import atomic, frozen_inputs, now, sha, stages
from benchmarks.round2_resources import storage


def git(*arguments, env=None, check=True):
    result = subprocess.run(["git", *arguments], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if check and result.returncode:
        raise RuntimeError("Git operation failed; diagnostics omitted to protect remote credentials")
    return result.stdout.decode().strip() if check else result


def host_record(run_id):
    cpu = None
    path = Path("/proc/cpuinfo")
    if path.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
                    if line.startswith("model name")), None)
    return {"id": run_id, "python": platform.python_version(), "platform": platform.platform(),
        "cpu_model": cpu, "logical_cpus": os.cpu_count(), "runner_os": os.environ.get("RUNNER_OS"),
        "image_version": os.environ.get("ImageVersion"),
        "packages": sorted((item.metadata.get("Name", ""), item.version) for item in importlib.metadata.distributions()
                           if re.fullmatch(r"[A-Za-z0-9_.-]+", item.metadata.get("Name", ""))),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "timing_policy": "All stages sequential on this one host. Fresh worker/state per engine; source/OS caches warm naturally. Different product interfaces remain separately labeled."}


def snapshot(path, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or path.exists():
        raise ValueError("Runtime snapshot requires a pinned commit and fresh directory")
    if git("cat-file", "-e", commit + "^{commit}", check=False).returncode:
        git("fetch", "--no-tags", "origin", commit)
    git("worktree", "add", "--detach", str(path), commit)


def publish(checkpoint, result_dir, parent):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if (os.environ.get("GITHUB_REPOSITORY") != "Afloat16/AI-Memory-Book"
            or not run_id.isdigit() or not attempt.isdigit()):
        raise ValueError("Result publication requires this repository's Actions run identity")
    branch = "refs/heads/validation/round2-" + run_id + "-" + attempt
    files = [checkpoint]
    if result_dir.exists():
        files += [path for path in result_dir.iterdir() if path.is_file() and not path.is_symlink()
                  and (path.name.endswith((".json.gz", ".summary.json")) or path.name in {"assessment.json", "report.md"})]
    names = []
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to((ROOT / "benchmarks").resolve()):
            raise ValueError("Non-public publication path")
        names.append(str(path.relative_to(ROOT)))
    existing = git("ls-remote", "--heads", "origin", branch)
    if existing and existing.split()[0] != parent:
        raise ValueError("Another writer changed the result branch; never force push")
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git("read-tree", parent, env=env)
        git("add", "--", *sorted(names), env=env)
        tree = git("write-tree", env=env)
        message = Path(directory) / "message.txt"
        message.write_text("bench: preserve registered round-two stage and audit\n", encoding="utf-8")
        commit = git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit-tree", tree, "-p", parent, "-F", str(message), env=env)
        git("push", "origin", commit + ":" + branch)
    return commit


def execute(argv, timeout, log_path):
    if timeout <= 0:
        raise TimeoutError("Execution time reserved for publication has been reached")
    with log_path.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=stream, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            raise


def prepare(directory, plan, binding, checkpoint, persist):
    steps = checkpoint["preparation"]
    def measured(name, function, location):
        record = {"status": "running", "started_at": now(), "preexisting_storage": storage(location)}
        steps[name] = record
        persist()
        begin = time.perf_counter_ns()
        value = function()
        record.update(status="completed", wall_ms=(time.perf_counter_ns() - begin) / 1e6,
                      finished_at=now(), prepared_storage=storage(location))
        persist()
        return value
    private = directory / "private"
    data = measured("verified_hotpot_download_and_conversion", lambda: round2_data.prepare_data(private), private)
    cache = directory / "cache"
    from benchmarks.token_compare import TokenCounter
    os.environ["TIKTOKEN_CACHE_DIR"] = str(directory / "tokenizers")
    measured("reference_tokenizers", lambda: [TokenCounter(name).count("explicit reference tokenizer preparation")
             for name in plan["native"]["tokenizers"]], directory / "tokenizers")
    from benchmarks.competitors.ai_memory import prepare as ai_binary, prepare_models
    from benchmarks.competitors.claude_mem import prepare as claude
    from benchmarks.competitors.billion import prepare as billion
    measured("ai_memory_binary_and_embedding", lambda: (ai_binary(cache / "ai-memory"), prepare_models(cache / "ai-memory")), cache / "ai-memory")
    measured("claude_mem_source_and_bun", lambda: claude(cache / "claude-mem",
             lock_path=ROOT / binding["upstream_locks"]["claude-mem"]), cache / "claude-mem")
    measured("billion_context_source", lambda: billion(cache / "billion-context",
             lock_path=ROOT / binding["upstream_locks"]["billion-context"]), cache / "billion-context")
    model = directory / "semantic-model"
    if binding["optional_semantic"]:
        def semantic_model():
            subprocess.run([sys.executable, "scripts/prepare_semantic_model.py", "--output", str(model)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, check=True, timeout=600)
        measured("book_semantic_model", semantic_model, model)
    return data, cache, model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--wall-time-seconds", type=int, default=9000)
    args = parser.parse_args(argv)
    plan, binding = frozen_inputs()  # Refuse unbound or uncommitted candidates before any scoring.
    if args.wall_time_seconds < 60:
        raise ValueError("Execution budget must reserve enough time for a meaningful stage")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    else:
        run_id = "local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + str(os.getpid())
    if not re.fullmatch(r"[A-Za-z0-9-]+", run_id):
        raise ValueError("Invalid run identity")
    directory = ROOT / ".artifacts/round2" / run_id
    if directory.exists():
        raise FileExistsError("Never replay an existing run implicitly")
    directory.mkdir(parents=True)
    result_dir = ROOT / "benchmarks/results" / ("round2-" + run_id)
    checkpoint_path = ROOT / "benchmarks/reports" / ("round2-" + run_id + "-checkpoint.json")
    parent = git("rev-parse", "HEAD")
    checkpoint = {"schema_version": 1, "protocol": plan["protocol"], "run_id": run_id,
        "status": "running", "source_commit": parent, "started_at": now(), "host": host_record(run_id),
        "plan_sha256": sha(ROOT / "benchmarks/round2_plan.json"),
        "binding_sha256": sha(ROOT / "benchmarks/round2_candidate.json"),
        "cohort_manifest_sha256": sha(round2_data.MANIFEST), "preparation": {}, "stages": {}}
    deadline = time.monotonic() + args.wall_time_seconds
    def persist():
        nonlocal parent
        atomic(checkpoint_path, checkpoint)
        if args.publish:
            parent = publish(checkpoint_path, result_dir, parent)
    success = False
    try:
        persist()  # Durable run identity before downloads or model/index preparation.
        baseline, candidate = directory / "baseline", directory / "candidate"
        snapshot(baseline, plan["baseline"]["commit"])
        snapshot(candidate, binding["candidate"]["commit"])
        data, cache, model = prepare(directory, plan, binding, checkpoint, persist)
        bundle = directory / "frozen-pages.json"
        frozen_db = directory / "states/export/frozen.db"
        for stage in stages(plan, binding):
            prefix = result_dir / stage
            command = [sys.executable, "-u", "-m", "benchmarks.round2_eval", "--stage", stage,
                "--data", str(data), "--bundle", str(bundle), "--frozen-db", str(frozen_db),
                "--state", str(directory / "states" / stage), "--cache", str(cache),
                "--model-dir", str(model), "--output", str(prefix), "--host-id", run_id]
            if stage == "export" or stage.startswith("baseline-"):
                command += ["--source", str(baseline / "src")]
            elif stage.startswith("candidate-"):
                command += ["--source", str(candidate / "src")]
            record = {"status": "running", "started_at": now(), "argv": command}
            checkpoint["stages"][stage] = record
            persist()
            try:
                code = execute(command, deadline - time.monotonic(), directory / (stage + ".log"))
                record.update(exit_code=code, status="completed" if code == 0 else "failed")
            except BaseException as error:
                record.update(status="interrupted", error_type=type(error).__name__)
                raise
            finally:
                record["finished_at"] = now()
                record["outputs"] = {str(path.relative_to(ROOT)): sha(path)
                    for suffix in (".json.gz", ".summary.json")
                    if (path := Path(str(prefix) + suffix)).is_file()}
                persist()  # No next measured stage until the preceding bytes are durable.
            if record["status"] != "completed":
                raise RuntimeError("A registered stage failed; preserve its diagnosis without automatic replay")
        checkpoint["status"] = "measurements-complete-awaiting-assessment"
        persist()
        code = execute([sys.executable, "scripts/summarize_round2_validation.py", "--checkpoint", str(checkpoint_path)],
                       min(600, deadline - time.monotonic()), directory / "assessment.log")
        checkpoint["assessment_exit_code"] = code
        if code:
            raise RuntimeError("Strict round-two assessment rejected the run")
        checkpoint["status"] = "complete-verified-snapshot"
        checkpoint["assessment_outputs"] = {str(path.relative_to(ROOT)): sha(path)
                                            for path in (result_dir / "assessment.json", result_dir / "report.md")}
        success = True
    except BaseException as error:
        checkpoint.update(status="failed", error_type=type(error).__name__)
    finally:
        checkpoint["finished_at"] = now()
        persist()
    print(json.dumps({"status": checkpoint["status"], "checkpoint": str(checkpoint_path.relative_to(ROOT)),
                      "completed_stages": sum(row["status"] == "completed" for row in checkpoint["stages"].values())}))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
