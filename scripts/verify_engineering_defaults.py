"""Verify the selected release defaults against the frozen engineering replay.

This is a compatibility/quality check on already-seen development data, not a
new performance experiment. Every saved 2,400-character Book case is checked;
no winning subset is selected. The historical evaluator and evidence are read
without modification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_workflow as workflow

FROZEN = ROOT / "benchmarks/results/engineering-memory-20261115/final/2-candidate-workflow"
BUDGET = 2400


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(output):
    import memory_book
    from memory_book import MemoryBook

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw_path = FROZEN / "raw.jsonl.gz"
    raw_bytes = raw_path.read_bytes()
    frozen_rows = [json.loads(line) for line in gzip.decompress(raw_bytes).decode().splitlines()]
    expected = {row["case_id"]: row for row in frozen_rows
                if row["backend"] == "book" and row["budget_chars"] == BUDGET}
    require(len(expected) == 80, "The complete frozen 80-case Book matrix is required")
    historical_report = json.loads((FROZEN / "report.json").read_text())
    steps = workflow.workload()
    require(workflow.sha(steps) == historical_report["dataset_sha256"], "The workload changed")
    evaluator_hash = hashlib.sha256(Path(workflow.__file__).read_bytes()).hexdigest()
    require(evaluator_hash == historical_report["evaluator_sha256"], "The frozen evaluator changed")

    parameters = inspect.signature(MemoryBook.recall).parameters
    defaults = {name: parameters[name].default for name in
                ("budget_chars", "limit", "strategy", "coverage", "semantic", "budget_tokens")}
    require(defaults == {"budget_chars": BUDGET, "limit": 5, "strategy": "book",
                         "coverage": False, "semantic": False, "budget_tokens": None},
            "Default profile differs from the selected release configuration")
    runtime = workflow.runtime_identity(memory_book)
    visible, rows = {}, []
    with tempfile.TemporaryDirectory(prefix="engineering-defaults-") as directory, \
            MemoryBook(Path(directory) / "memory.db", cache_size=0) as book, \
            (output / "raw.jsonl").open("w", encoding="utf-8") as stream:
        for step in steps:
            for session in step["sessions"]:
                book.ingest(session)
                visible[(session["project"], session["session_id"])] = session
            sources = workflow.visible_sources(visible)
            for case in step["cases"]:
                # Leave the selected product options omitted, including the
                # normal use_cache default. cache_size=0 isolates output parity.
                default = book.recall(case["query"], project=case["project"])
                explicit = book.recall(case["query"], project=case["project"],
                                       budget_chars=BUDGET, limit=5, strategy="book",
                                       coverage=False, semantic=False, budget_tokens=None,
                                       use_cache=False)
                score = workflow.score(case, default, sources, BUDGET)
                old = expected[case["id"]]
                row = {"case_id": case["id"], "checkpoint": step["checkpoint"],
                       "query": case["query"], "project": case["project"],
                       "default_response": default, "explicit_response": explicit,
                       "score": score,
                       "default_equals_explicit": stable(default) == stable(explicit),
                       "default_equals_frozen": stable(default) == stable(old["response"]),
                       "score_equals_frozen": score == old["score"]}
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()

    checks = {
        "all_80_cases_present": len(rows) == len(expected) and {r["case_id"] for r in rows} == set(expected),
        "all_default_outputs_equal_explicit": all(r["default_equals_explicit"] for r in rows),
        "all_default_outputs_equal_frozen": all(r["default_equals_frozen"] for r in rows),
        "all_scores_equal_frozen": all(r["score_equals_frozen"] for r in rows),
        "zero_source_errors": all(not r["score"]["source_errors"] for r in rows),
        "zero_budget_violations": all(r["score"]["within_budget"] for r in rows),
        "runtime_unchanged": workflow.runtime_identity(memory_book) == runtime,
        "evaluator_unchanged": hashlib.sha256(Path(workflow.__file__).read_bytes()).hexdigest() == evaluator_hash,
    }
    answerable = [r for r in rows if r["score"]["answerable"]]
    consumers = [r["score"]["fixed_consumer"] for r in rows if r["score"].get("fixed_consumer") is not None]
    report = {
        "schema": "engineering-default-profile-verification-v1",
        "status": "passed" if all(checks.values()) else "failed",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": memory_book.__version__, "defaults": defaults,
        "runtime": runtime, "dataset_sha256": workflow.sha(steps),
        "evaluator_sha256": evaluator_hash,
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "historical_raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "historical_report_sha256": hashlib.sha256((FROZEN / "report.json").read_bytes()).hexdigest(),
        "checks": checks, "quality_cases": len(rows), "recall_calls": len(rows) * 2,
        "complete_evidence": {"passed": sum(r["score"]["complete_evidence"] for r in answerable),
                              "total": len(answerable)},
        "fixed_consumer": {"passed": sum(c["all_passed"] for c in consumers), "total": len(consumers)},
        "scope": "Default/explicit/frozen-output equivalence on the existing synthetic development cohort. "
                 "Not independent holdout, coding-LLM productivity, or a new timing comparison. "
                 "Only latency_ms is excluded from complete response equality. Result caching is disabled by cache_size=0.",
    }
    raw = (output / "raw.jsonl").read_bytes()
    (output / "raw.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))
    (output / "raw.jsonl").unlink()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    require(report["status"] == "passed", "Default profile verification failed; preserve the output for inspection")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({"status": report["status"], "cases": report["quality_cases"],
                      "complete_evidence": report["complete_evidence"],
                      "fixed_consumer": report["fixed_consumer"]}))


if __name__ == "__main__":
    main()
