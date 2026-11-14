"""Prepare and run one registered hosted round-six stage with durable evidence.

No benchmark is imported through a product source before the subprocess worker.
Preparation downloads are hash-checked and excluded from latency observations.
The finally path preserves failures and uploads no credentials or private data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round6_performance as benchmark


def call(*args):
    result = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    benchmark.require(result.returncode == 0, "Preparation command failed; credential-bearing diagnostics omitted")
    return result.stdout


def materialize(path):
    benchmark.require(isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts,
                      "Unsafe frozen evidence path")
    location = ROOT / path
    if not location.exists():
        raw = call("git", "show", "HEAD:" + path)
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes(raw)


def prepare(binding_path):
    raw = json.loads(binding_path.read_bytes())
    commits = {benchmark.PLAN_COMMIT, raw["evaluator_commit"], raw["plan_commit"], *(s["commit"] for s in raw["sources"].values())}
    for commit in sorted(commits):
        benchmark.require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Invalid frozen Git commit")
        call("git", "fetch", "--no-tags", "--depth", "1", "--filter=blob:none", "origin", commit)
    for group in raw["evidence"].values():
        for record in group.values():
            materialize(record["path"])
    binding = benchmark.load_binding(binding_path)
    paths = {}
    for label, source in binding["sources"].items():
        location = ROOT / (".artifacts/round6-source-" + label)
        if not location.exists():
            location.parent.mkdir(parents=True, exist_ok=True)
            call("git", "worktree", "add", "--no-checkout", "--detach", str(location), source["commit"])
            call("git", "-C", str(location), "sparse-checkout", "set", "--cone", "src")
            call("git", "-C", str(location), "read-tree", "-mu", "HEAD")
        benchmark.require(benchmark.source_identity(location / "src") == source, "Prepared source differs from binding")
        paths[label] = location / "src"
    spec = json.loads((ROOT / "benchmarks/locomo_split.json").read_bytes())
    locomo = ROOT / ".artifacts/round6-locomo10.json"
    if not locomo.exists():
        with urllib.request.urlopen(spec["url"], timeout=60) as response:
            content = response.read(spec["bytes"] + 1)
        benchmark.require(len(content) == spec["bytes"] and benchmark.sha(content) == spec["sha256"], "Public input download differs")
        locomo.parent.mkdir(parents=True, exist_ok=True)
        locomo.write_bytes(content)
    benchmark.require(locomo.stat().st_size == spec["bytes"] and benchmark.sha(locomo.read_bytes()) == spec["sha256"], "Old input file changed")
    import tiktoken
    benchmark.require(tiktoken.__version__ == "0.12.0", "Unexpected tokenizer package")
    for name in ("cl100k_base", "o200k_base"):
        tiktoken.get_encoding(name).encode("Initialize reference tokenizer data outside every timed worker.")
    print(json.dumps({"prepared": True, "stage": binding["stage"], "product_calls": 0, "source_refs": binding["sources"]}), flush=True)
    return binding, paths, locomo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=benchmark.STAGES, required=True)
    parser.add_argument("--binding", type=Path)
    args = parser.parse_args(argv)
    identity, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    benchmark.require(identity.isdigit() and attempt == "1", "Only the first hosted run attempt is authorized")
    label = "performance" if args.stage == "formal" else args.stage
    binding_path = (args.binding or ROOT / ("benchmarks/experiments/round6-" + label + "-binding.json")).resolve()
    suffix = label + "-" + identity + "-1"
    public = ROOT / ("benchmarks/reports/round6-" + suffix)
    state = ROOT / (".artifacts/round6-" + suffix)
    runner = SimpleNamespace(binding=binding_path, state_dir=state, output=public / "report.json.gz",
                             publish_branch="validation/v034-round6-" + suffix)
    benchmark.require(not public.exists() and not state.exists(), "Preserve an existing stage; no retry")
    measurement_code, audit_code, error = None, None, None
    try:
        prior_publication_failures = list((ROOT / "benchmarks/reports").glob("round6-*-" + identity + "-1/publication-failure.json"))
        benchmark.require(not prior_publication_failures, "A preceding stage had an ambiguous checkpoint push; no subsequent timing")
        binding, paths, locomo = prepare(binding_path)
        benchmark.require(binding["stage"] == args.stage, "Stage differs from binding")
        runner.baseline_src, runner.candidate_src, runner.locomo_path = paths["baseline"], paths["candidate"], locomo
        benchmark.publication_identity(runner, binding)
        command = [sys.executable, "-u", str(ROOT / "scripts/round6_performance.py"), "--binding", str(binding_path),
            "--baseline-src", str(paths["baseline"]), "--candidate-src", str(paths["candidate"]),
            "--locomo-path", str(locomo), "--state-dir", str(state), "--output", str(runner.output), "--publish-branch", runner.publish_branch]
        measurement_code = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}).returncode
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        public.mkdir(parents=True, exist_ok=True)
        benchmark.export_checkpoint(runner)
        if runner.output.is_file():
            audit_code = subprocess.run([sys.executable, str(ROOT / "scripts/round6_audit_performance.py"),
                "--report", str(runner.output), "--state-dir", str(public), "--output", str(public / "independent-audit.json")], cwd=ROOT).returncode
        summary = benchmark.read_json(public / "report.summary.json") if (public / "report.summary.json").is_file() else {}
        record = {"schema_version": 1, "stage": args.stage, "created_at": benchmark.now(), "run_id": identity, "run_attempt": attempt,
            "workflow_commit": call("git", "rev-parse", "HEAD").decode().strip(), "measurement_returncode": measurement_code,
            "audit_returncode": audit_code, "error": error, "validation": summary.get("validation"), "acceptance": summary.get("acceptance"),
            "status": "completed" if measurement_code == 0 and audit_code == 0 else "failed_or_requires_review",
            "files_sha256": {p.relative_to(public).as_posix(): benchmark.sha(p.read_bytes()) for p in sorted(public.rglob("*")) if p.is_file()},
            "scope": "Every start, completion, failure and adverse sample retained. Auditing never repeats retrieval; raw resource-review failures stay false."}
        benchmark.exclusive(public / "completion.json", record)
        if (state / "run.json").is_file() and not (public / "publication-failure.json").exists():
            try:
                benchmark.publish_checkpoint(runner, benchmark.read_json(state / "run.json"), "independent audit and completion")
            except benchmark.CheckpointPublicationError:
                error = {"type": "CheckpointPublicationError", "message": "Completion push failed; preserve artifact without retry"}
        print(json.dumps({"stage": args.stage, "measurement_returncode": measurement_code, "audit_returncode": audit_code,
                          "result_branch": runner.publish_branch, "error": error}), flush=True)
    return 0 if measurement_code == 0 and audit_code == 0 and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
