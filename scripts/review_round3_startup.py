"""Reproduce the separate resource review without executing any measurement.

The original automatic acceptance and all samples remain immutable. This is an
explicit engineering decision to retain a measured startup cost, not a new score
or evidence that an unobserved operating-system event caused that cost.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "dd2f88be742ed330269e7dd5915b6f75089d7fef"
CANDIDATE = "2d199b93f650eccd3dd239178822b31001b880e3"
RESULT = "35b8618a078fe377ecd6c5acc331c1281dbf61e7"
PREFIX = "benchmarks/reports/round3-performance-43246417515-1/"
SUMMARY_SHA = "b6f9391956a0231383687d383cb87b0579e2a79d8776e43105e4b172e2d875a1"
COMPLETION_SHA = "5f0e556d093eb5f70dd0deafa66aee7fd95fc6ef1bb772a48af88c957100523e"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_file(commit, path):
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def node_for(tree, name):
    if name.startswith("MemoryBook."):
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MemoryBook")
        return next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name.split(".")[1])
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
    raise ValueError("Missing initialization-path node: " + name)


def review():
    raw = git_file(RESULT, PREFIX + "report.summary.json")
    completion_raw = git_file(RESULT, PREFIX + "completion.json")
    require(sha(raw) == SUMMARY_SHA and sha(completion_raw) == COMPLETION_SHA, "Original result identity differs")
    summary, completion = json.loads(raw), json.loads(completion_raw)
    require(completion["audit_outcome"] == "success", "Original saved-row audit did not pass")
    require(summary["validation"] == {"expected_calls": 47320, "expected_workers": 16,
        "issues": [], "passed": True, "timed_calls": 47320, "workers": 16}, "Formal validation differs")
    acceptance = summary["acceptance"]
    require(acceptance["numeric_gate_passed"] is True and acceptance["accepted"] is False,
            "This review is only for the recorded resource exception")
    require(len(acceptance["resource_review"]) == 1 and
        acceptance["resource_review"][0]["cohort"] == "public1015" and
        acceptance["resource_review"][0]["metric"] == "native_open_ms", "Unexpected resource exception")
    sources = {label: git_file(commit, "src/memory_book/store.py").decode()
        for label, commit in (("baseline", BASELINE), ("candidate", CANDIDATE))}
    trees = {label: ast.parse(source) for label, source in sources.items()}
    checks = []
    for name in ("MemoryBook.__init__", "MemoryBook.__enter__", "_integer", "_directory_tokens",
                 "SCHEMA", "SCHEMA_VERSION", "INDEX_VERSION", "APPLICATION_ID", "STEM_INDEX_SQL",
                 "STEM_DELETE_SQL", "STEM_REVISION_SQL"):
        entries = {}
        for label in sources:
            node = node_for(trees[label], name)
            entries[label] = {"source_sha256": sha(ast.get_source_segment(sources[label], node).encode()),
                "ast_sha256": sha(ast.dump(node, include_attributes=False).encode())}
        require(entries["baseline"] == entries["candidate"], "Initialization code changed: " + name)
        checks.append({"name": name, "equal": True, **entries})
    for name in ("text.py", "segmentation.py"):
        entries = {label: sha(git_file(commit, "src/memory_book/" + name))
            for label, commit in (("baseline", BASELINE), ("candidate", CANDIDATE))}
        require(entries["baseline"] == entries["candidate"], "Initialization dependency changed")
        checks.append({"name": name, "equal": True, "sha256": entries})
    samples = []
    for round_index in range(4):
        values = {worker["label"]: worker["native_open_ms"] for worker in summary["workers"]
            if worker["cohort"] == "public1015" and worker["round"] == round_index}
        require(set(values) == {"baseline", "candidate"}, "Missing startup sample")
        samples.append({"round": round_index, **values,
            "delta_ms": values["candidate"] - values["baseline"],
            "change_percent": 100 * (values["candidate"] / values["baseline"] - 1)})
    means = {label: statistics.fmean(row[label] for row in samples) for label in ("baseline", "candidate")}
    return {"schema_version": 1, "decision": "accept_with_explicit_startup_resource_tradeoff",
        "formal_automatic_acceptance_unchanged": False, "additional_formal_measurements": 0,
        "original_result_commit": RESULT, "baseline_commit": BASELINE, "candidate_commit": CANDIDATE,
        "inputs": {"summary_sha256": SUMMARY_SHA, "completion_sha256": COMPLETION_SHA,
            "raw_report_sha256": summary["full_report_sha256"],
            "compressed_report_sha256": summary["compressed_report_sha256"]},
        "formal_validation": summary["validation"], "formal_numeric_gate_passed": True,
        "geometric_mean_p95_improvement_percent": acceptance["geometric_mean_p95_improvement_percent"],
        "best_public_native_p95_improvement_percent": acceptance["best_public_native_p95_improvement_percent"],
        "resource_exception": acceptance["resource_review"][0], "startup_samples_ms": samples,
        "observed_mean_delta_ms": means["candidate"] - means["baseline"],
        "startup_code_path_changed": False, "specific_host_cause_identified": False,
        "static_checks": checks,
        "cause_analysis": "The threshold is driven by the longer round-zero observation in an unchanged empty-database initialization path. The retrieval optimization and semantic model construction are outside that timed boundary. No per-SQL, scheduling or storage trace was recorded; the specific host cause is unknown.",
        "decision_scope": "Accept the observed +4.84 ms mean empty-database opening cost as an explicit tradeoff for verified retrieval improvements. Do not claim startup non-regression, discard any round, change the failed Actions conclusion, or replace the original accepted=false. This separate review does not make the original automatic gate pass.",
        "cells": [{"cohort": cell["cohort"], "configuration": cell["id"],
            "baseline": cell["baseline"]["latency"], "candidate": cell["candidate"]["latency"],
            "candidate_change_percent": cell["candidate_change_percent"]} for cell in summary["comparisons"]]}


def markdown(value):
    lines = ["# v0.3.1 performance and startup resource review", "",
        "**Accept the retrieval optimization with an explicitly retained startup cost.** "
        "The original automatic report remains `accepted=false`; its resource threshold required "
        "a separate review. This decision does not rewrite that outcome or any measurement.", "",
        "The frozen run completed **47,320 calls, 16 workers and four balanced rounds**. "
        "All complete non-timing outputs, source/scope/budget invariants and the independent saved-row audit passed. "
        "Across ten cohort/configuration cells, the pooled-p95 geometric mean improves **11.36%**. "
        "The largest public native p95 improvement is **26.05%**; no pooled p50 or p95 regresses by more than 5%.", "",
        "## All pooled cells", "", "Negative changes are faster. Timings are from the same formal host; "
        "they are not a cross-product or cold-cache comparison.", "",
        "| Cohort | Configuration | Baseline p95 ms | Candidate p95 ms | p95 change | p50 change |",
        "|---|---|---:|---:|---:|---:|"]
    for cell in value["cells"]:
        change = cell["candidate_change_percent"]
        lines.append(f"| {cell['cohort']} | {cell['configuration']} | {cell['baseline']['p95_ms']:.3f} | {cell['candidate']['p95_ms']:.3f} | {change['p95_ms']:+.2f}% | {change['p50_ms']:+.2f}% |")
    lines += ["", "The synthetic 512-token p95 increases **0.125%**; that negative cell is retained. "
        "Public actual SDK/MCP p95 improves **19.87%**, while synthetic MCP improves **3.68%**.", "",
        "## Explicit startup tradeoff", "",
        "The one resource threshold crossing is public1015 empty-database opening: "
        "**34.4557 → 39.2941 ms mean, +4.8384 ms / +14.04%**. All four samples remain:", "",
        "| Round | Baseline ms | Candidate ms | Change ms |", "|---|---:|---:|---:|"]
    for row in value["startup_samples_ms"]:
        lines.append(f"| {row['round']} | {row['baseline']:.6f} | {row['candidate']:.6f} | {row['delta_ms']:+.6f} |")
    lines += ["", "The timed boundary is `MemoryBook(db_path, cache_size=0)` plus `__enter__` on a new, "
        "empty database, before ingestion or recall. Thirteen reproducible source/AST checks establish "
        "that the constructor, entry method, schema, triggers, constants and initialization dependencies "
        "are identical. The rowid optimization is in recall; the semantic telemetry change is in model construction.", "",
        value["cause_analysis"], "", value["decision_scope"], "",
        "An independent review confirmed the full sample set, code boundary and this limitation. "
        "Other recorded resource means increase by at most 0.72%. No startup-speed claim is made.", "",
        "## Evidence and reproduction", "",
        "- [Original formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515)",
        "- [Unmodified report and every worker](../benchmarks/reports/round3-performance-43246417515-1/)",
        "- [Machine-readable separate review](../benchmarks/reports/round3-performance-resource-review.json)",
        "- [Pre-registered protocol](../benchmarks/experiments/round3-plan.json)", "",
        "```bash", "python scripts/review_round3_startup.py", "```", "",
        "The command only reads committed source and saved summaries. It performs no retrieval, "
        "tokenization, model inference, or timing rerun. The original saved-row audit covers the full raw "
        "report and ledgers; this additional script checks input identities and the resource-review evidence.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Create the review artifacts; never overwrite")
    args = parser.parse_args()
    value = review()
    if args.write:
        paths = [(ROOT / "benchmarks/reports/round3-performance-resource-review.json", json.dumps(value, indent=2) + "\n"),
                 (ROOT / "docs/round3-performance-review.md", markdown(value))]
        require(not any(path.exists() for path, _ in paths), "Preserve existing review artifacts")
        for path, content in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(content)
    print(json.dumps({"decision": value["decision"], "static_checks": len(value["static_checks"]),
        "formal_calls": value["formal_validation"]["timed_calls"], "additional_measurements": 0}))


if __name__ == "__main__":
    main()
