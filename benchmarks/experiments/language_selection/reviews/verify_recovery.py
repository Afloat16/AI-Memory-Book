#!/usr/bin/env python3
"""Verify a resumed, offline analysis without changing frozen evidence or timings.

The original runner verified its 209 frozen source/binary files in place. An
offline analysis cannot read those absolute host paths. This verifier checks
reproducibility apart from those two explicitly different audit fields, and
independently binds recoverable source bytes to the frozen Git commits.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    args = parser.parse_args()
    original = read(args.evidence / "analysis.json")
    replay = read(args.review / "reanalysis.json")
    run = read(args.evidence / "run.json")
    self_test = read(args.review / "analyzer-self-test.json")
    original_normalized, replay_normalized = copy.deepcopy(original), copy.deepcopy(replay)
    excluded = ("local_byte_verification_requested", "local_frozen_files_checked")
    scope_differences = {}
    for key in excluded:
        scope_differences[key] = {
            "original_runner": original_normalized["audit"].pop(key),
            "offline_replay": replay_normalized["audit"].pop(key),
        }
    errors = []
    if original_normalized != replay_normalized:
        errors.append("Offline analysis differs beyond the two declared host-local audit fields")
    if not original["audit"]["passed"] or not replay["audit"]["passed"]:
        errors.append("At least one full evidence audit failed")
    if self_test["status"] != "passed" or self_test["analysis_source_sha256"] != original["analysis_source_sha256"]:
        errors.append("Self-test does not certify the original analyzer bytes")

    baseline, frozen = original["baseline_commit"], original["experiment_commit"]
    git = ["git", "-C", str(args.repository.resolve())]
    product_paths = ["src", "pyproject.toml", "setup.py"]
    product_diff = subprocess.check_output(
        git + ["diff", "--name-only", baseline, frozen, "--", *product_paths], text=True
    ).splitlines()
    if product_diff:
        errors.append("Frozen experiment changed production source or build metadata")

    prefix = "/home/runner/work/AI-Memory-Book/AI-Memory-Book/"
    source_checks, unrecoverable = [], []
    cache = {}
    for host_path, expected in run["manifest"]["file_sha256"].items():
        if not host_path.startswith(prefix):
            unrecoverable.append({"host_path": host_path, "sha256": expected,
                                  "reason": "Original host executable is not preserved in this evidence tree"})
            continue
        relative = host_path[len(prefix):]
        ref, mapped = frozen, relative
        for staging in ("current", "rust-same"):
            start = f".artifacts/language-selection/run/{staging}/"
            if relative.startswith(start):
                ref, mapped = baseline, relative[len(start):]
                break
        if mapped.startswith(".artifacts/") or mapped.endswith((".so", ".a")):
            unrecoverable.append({"host_path": host_path, "sha256": expected,
                                  "reason": "Original build, runtime or dataset bytes are not in the recovered source tree"})
            continue
        key = (ref, mapped)
        if key not in cache:
            cache[key] = subprocess.check_output(git + ["show", f"{ref}:{mapped}"])
        actual = sha(cache[key])
        source_checks.append({"host_path": host_path, "git_commit": ref, "git_path": mapped,
                              "expected_sha256": expected, "actual_sha256": actual,
                              "passed": actual == expected})
        if actual != expected:
            errors.append("Source hash mismatch: " + host_path)
    before_after = run["manifest"]["file_sha256"] == run["file_sha256_after"]
    if not before_after:
        errors.append("Original before/after file bindings differ")

    result = {
        "status": "passed" if not errors else "failed",
        "kind": "offline-recovery-audit-not-new-performance-measurement",
        "no_timing_workers_rerun": True,
        "errors": errors,
        "baseline_commit": baseline,
        "frozen_experiment_commit": frozen,
        "evidence_commit": "351770ce9950ba60f77e04847a1de386c44dac2c",
        "analysis_matches_original_except_declared_local_scope": original_normalized == replay_normalized,
        "declared_scope_differences": scope_differences,
        "original_runner_byte_checks": original["audit"]["local_frozen_files_checked"],
        "original_before_after_bindings_equal": before_after,
        "source_bindings_reverified_from_frozen_git": len(source_checks),
        "distinct_source_blobs_read": len(cache),
        "original_host_inputs_not_independently_reread": len(unrecoverable),
        "production_paths_compared": product_paths,
        "production_changed_files": product_diff,
        "analyzer_self_test_checks": len(self_test["checks"]),
        "offline_audit": replay["audit"],
        "input_sha256": {
            "original_analysis.json": sha((args.evidence / "analysis.json").read_bytes()),
            "run.json": sha((args.evidence / "run.json").read_bytes()),
            "reanalysis.json": sha((args.review / "reanalysis.json").read_bytes()),
            "analyzer-self-test.json": sha((args.review / "analyzer-self-test.json").read_bytes()),
        },
        "verifier_sha256": sha(Path(__file__).read_bytes()),
        "source_checks": source_checks,
        "unrecoverable_original_host_inputs": unrecoverable,
        "limitations": [
            "This replay verifies saved report/ledger hashes and registered complete-output identities; it does not execute candidate implementations again.",
            "Original host executable and build bytes are not reconstructed or falsely claimed as independently reread.",
            "Six paired rounds on one Linux runner do not establish cross-platform behavior or a complete Rust service's performance.",
        ],
    }
    output = args.review / "recovery-verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "status", "errors", "analysis_matches_original_except_declared_local_scope",
        "source_bindings_reverified_from_frozen_git", "distinct_source_blobs_read",
        "original_host_inputs_not_independently_reread", "analyzer_self_test_checks")}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
