"""Execute one frozen cohort on a hosted runner and persist public results.

Each cohort has its own VM. Paired modes run sequentially. Raw datasets,
prompts, model weights and credentials are never added to Git.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NATIVE = "benchmarks/native-recovery-20261112-manifest.json"
SEMANTIC = "benchmarks/semantic-recovery-20261112-manifest.json"
ANSWERS = "benchmarks/local-answer-recovery-manifest.json"
BASELINE = "5abc85eef00097555366f8524fc81f8b5711ad7a"
CANDIDATE = "407cda1c5f1dac0e67dfe527d3c23febdad5e818"

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)

def run(argv, check=True):
    print(json.dumps({"event": "command", "argv": list(map(str, argv))}), flush=True)
    return subprocess.run(list(map(str, argv)), cwd=ROOT, check=check).returncode

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
        codes[phase] = run(command, check=False)
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
            "packages": subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines()}

def publish(stage, marker, public_paths):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")
    if not run_id or not run_id.isdigit() or not attempt or not attempt.isdigit():
        raise ValueError("Publishing requires a GitHub Actions run identity")
    branch = "validation/20261112-" + stage + "-" + run_id + "-" + attempt
    files = []
    for item in public_paths + [str(marker.relative_to(ROOT))]:
        path = (ROOT / item).resolve()
        path.relative_to(ROOT / "benchmarks")
        if path.is_file():
            files.append(str(path.relative_to(ROOT)))
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run(["git", "add", "--", *sorted(set(files))])
    run(["git", "commit", "-m", "bench: preserve " + stage + " hosted validation"])
    run(["git", "push", "origin", "HEAD:refs/heads/" + branch])
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write("Saved [" + stage + "](https://github.com/" + os.environ["GITHUB_REPOSITORY"]
                         + "/tree/" + branch + ").\n")
    print(json.dumps({"event": "published", "branch": branch, "commit": git("rev-parse", "HEAD")}), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=choices(), required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(ROOT / ".artifacts/tiktoken")
    marker = ROOT / ("benchmarks/reports/hosted-" + args.stage + "-completion.json")
    metadata = {"schema_version": 1, "stage": args.stage, "status": "running",
                "source_commit": git("rev-parse", "HEAD"), "started_at": now(),
                "environment": environment(),
                "timing_boundary": "One isolated hosted runner; paired modes are sequential. Do not pool timings across hosts."}
    public_paths, exit_code = [], 1
    try:
        prepare(args.stage)
        metadata["prepared_at"] = now()
        if args.stage.startswith(("native-", "semantic-")):
            command, public_paths, parent = manifest_stage(args.stage)
            metadata.update(parent_manifest=parent, parent_manifest_sha256=sha(ROOT / parent), argv=command)
            exit_code = run(command, check=False)
        elif args.stage.startswith("answers-"):
            codes, public_paths = answer_stage(args.stage)
            metadata["phase_exit_codes"] = codes
            exit_code = 0 if len(codes) == 3 and all(v == 0 for v in codes.values()) else 1
        else:
            public_paths = ["benchmarks/results/full-workflow-transfer36.json",
                            "benchmarks/results/full-workflow-transfer36-assessment.json",
                            "benchmarks/RESULTS-full-workflow.md"]
            exit_code = run([sys.executable, "-u", "-m", "benchmarks.full_workflow_eval",
                             "--launch-server"], check=False)
            if (ROOT / public_paths[0]).is_file():
                assessment_exit = run([sys.executable, "scripts/summarize_workflow.py"], check=False)
                metadata["assessment_exit_code"] = assessment_exit
                exit_code = max(exit_code, assessment_exit)
        missing = [p for p in public_paths if not (ROOT / p).is_file()]
        metadata.update(status="completed" if exit_code == 0 and not missing else "failed",
                        exit_code=exit_code, missing_outputs=missing)
        if missing:
            exit_code = max(exit_code, 1)
    except Exception as exc:
        exit_code = 1
        metadata.update(status="failed", error_type=type(exc).__name__, error_message=str(exc))
        traceback.print_exc()
    finally:
        metadata["finished_at"] = now()
        metadata["public_output_sha256"] = {p: sha(ROOT / p) for p in public_paths if (ROOT / p).is_file()}
        atomic(marker, metadata)
        if args.publish:
            publish(args.stage, marker, public_paths)
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
