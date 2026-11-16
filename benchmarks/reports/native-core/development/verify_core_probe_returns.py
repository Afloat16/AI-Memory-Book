"""Verify the new effective-native-return gate using an existing native binary."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--evaluator-commit", required=True)
    parser.add_argument("--label", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root, source = args.repository.resolve(), args.source.resolve()
    if os.environ.get("PYTHONHASHSEED") != "0" or os.environ.get("MEMORY_BOOK_TEXT_BACKEND") != "native":
        raise RuntimeError("Run with PYTHONHASHSEED=0 and MEMORY_BOOK_TEXT_BACKEND=native")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != args.evaluator_commit:
        raise RuntimeError("Evaluator checkout differs")
    sys.path[:0] = [str(source), str(root)]
    from scripts import native_core_performance as perf
    evaluator_path = root / "scripts/native_core_performance.py"
    expected = subprocess.check_output(["git", "show", head + ":scripts/native_core_performance.py"], cwd=root)
    if evaluator_path.read_bytes() != expected:
        raise RuntimeError("Evaluator bytes differ from the committed source")
    plan = perf.validate_plan(perf.read(root / "benchmarks/experiments/native_core_formal_plan.json"))
    specification = plan["sources"][args.label]
    if specification != {"commit": args.source_commit, "backend": "native"}:
        raise RuntimeError("Runtime source differs from the plan")
    before = perf.source_manifest(source, specification)
    record = {"schema": "native-core-effective-return-probe-v1",
              "purpose": "Untimed verification of the newly added effective-return gate on an existing binary; no build or performance samples",
              "label": args.label, "evaluator_commit": head, "evaluator_sha256": perf.sha(expected),
              "runner_sha256": perf.sha(Path(__file__).read_bytes()),
              "python": sys.version, "platform": platform.platform(), "hash_seed": "0",
              "source_manifest_before": before, "status": "running", "error": None}
    try:
        identity = perf.active_backend(source, plan["native_helper_calls"][args.label],
            plan["native_helper_effective_calls"][args.label], plan["native_helper_fallback_calls"][args.label])
        record["backend"] = identity
        record["source_manifest_after"] = perf.source_manifest(source, specification)
        record["source_and_binary_unchanged"] = before == record["source_manifest_after"]
        if not record["source_and_binary_unchanged"]:
            raise RuntimeError("Runtime or binary changed")
        probe = identity["dispatch_probe"]
        if probe["native_helper_effective_calls"] != probe["native_helper_calls"] or any(probe["native_helper_fallback_calls"].values()):
            raise RuntimeError("The expected all-effective, zero-fallback gate did not hold")
        record["status"] = "completed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        with args.output.open("xb") as output:
            output.write(raw)
        print(json.dumps({"status": record["status"], "bytes": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest(), "output": str(args.output)}))


if __name__ == "__main__":
    main()
