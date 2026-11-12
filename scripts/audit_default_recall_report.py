"""Verify an existing default-recall measurement without rerunning retrieval."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_default_recall import comparisons, strict_validation


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(prefix, candidate_commit):
    compressed = Path(str(prefix) + ".json.gz").read_bytes()
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    summary_bytes = Path(str(prefix) + ".summary.json").read_bytes()
    summary = json.loads(summary_bytes)
    assert summary["full_report_sha256"] == sha(raw)
    assert summary["compressed_report_sha256"] == sha(compressed)
    assert report["validation"] == strict_validation(report)
    assert report["validation"]["passed"] is True, report["validation"]
    assert report["validation"]["workers"] == 16
    assert report["validation"]["timed_calls"] == 56784
    assert report["validation"]["unique_payload_pairs_per_surface"] == 3549
    assert len(report["comparisons"]) == 12
    assert report["comparisons"] == comparisons(report)
    assert report["sources"]["candidate"]["git_commit"] == candidate_commit
    assert report["environment"]["mcp"] == "1.30.0"
    assert report["environment"]["tiktoken"] == "0.12.0"
    for worker in report["workers"]:
        assert worker["mcp_server_memory_after_calls"]["available"] is True
    expected = {k: v for k, v in report.items() if k not in ("workers", "cohorts")}
    expected["cohorts"] = {name: {k: v for k, v in c.items() if not k.startswith("query_ids")}
                           for name, c in report["cohorts"].items()}
    expected["workers"] = [{k: v for k, v in w.items() if k != "configurations"} for w in report["workers"]]
    expected["full_report_sha256"] = sha(raw)
    expected["compressed_report_sha256"] = sha(compressed)
    assert expected == summary
    original_script = subprocess.check_output(["git", "show", candidate_commit + ":scripts/benchmark_default_recall.py"], cwd=ROOT)
    original_plan = subprocess.check_output(["git", "show", candidate_commit + ":benchmarks/experiments/round2-default-recall-performance-plan.json"], cwd=ROOT)
    assert report["evaluator_sha256"] == sha(original_script)
    assert report["plan_sha256"] == sha(original_plan)
    assert report["plan"] == json.loads(original_plan)
    for name, expected_hash in report["evaluator_dependency_sha256"].items():
        original = subprocess.check_output(["git", "show", candidate_commit + ":" + name], cwd=ROOT)
        assert sha(original) == expected_hash
    return {"status": "verified_existing_measurement", "validation": report["validation"],
            "candidate_commit": candidate_commit, "full_report_sha256": sha(raw),
            "compressed_report_sha256": sha(compressed), "summary_file_sha256": sha(summary_bytes),
            "plan_sha256": report["plan_sha256"], "measurement_evaluator_sha256": report["evaluator_sha256"],
            "audit_script_sha256": sha(Path(__file__).read_bytes()), "retrieval_calls_executed": 0,
            "comparison_rows_recomputed": 12,
            "correction": "Matrix order is taken from the registered plan instead of dictionary insertion order. JSON sort_keys had changed cohort mapping order in the original post-write audit. No metrics, samples, payloads or source files were changed.",
            "original_attempt_marker_preserved": True, "created_at": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing audits; choose a new output")
    result = audit(args.prefix, args.candidate_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
