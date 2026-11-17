#!/usr/bin/env python3
"""Independent arithmetic/decision review of the frozen language experiment.

This script imports no experiment analyzer code. It checks the published paired
rounds and computes exhaustive whole-round bootstrap intervals as a sensitivity
check. It does not re-read the original runner's binaries or raw worker ledgers.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile_sorted(values: list[float], p: float) -> float:
    index = (len(values) - 1) * p
    low = math.floor(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (index - low) * (values[high] - values[low])


def exact_bootstrap_ci(values: list[float]) -> list[float]:
    n = len(values)
    means = sorted(sum(sample) / n for sample in itertools.product(values, repeat=n))
    return [quantile_sorted(means, 0.025), quantile_sorted(means, 0.975)]


def label(row: dict) -> dict:
    return {key: row[key] for key in
            ("phase", "baseline", "variant", "cohort", "configuration", "metric")}


def compact(row: dict) -> dict:
    return dict(label(row), mean_paired_improvement_percent=row["mean_paired_improvement_percent"],
                ci95_percent=row["ci95_percent"], improving_rounds=row["improving_rounds"],
                numeric_benefit=row["numeric_benefit"],
                repeatable_regression=row["repeatable_regression"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analysis_path = args.evidence / "analysis.json"
    run_path = args.evidence / "run.json"
    manifest_path = args.evidence / "manifest.json"
    analysis = json.loads(analysis_path.read_text())
    run = json.loads(run_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    errors: list[dict] = []
    bootstrap_sensitivity: list[dict] = []

    def require(condition: bool, reason: str, row: dict | None = None) -> None:
        if not condition:
            errors.append({"reason": reason, "row": label(row) if row else None})

    groups = ("comparisons", "control_comparisons", "aa_comparisons")
    expected = {"comparisons": 297, "control_comparisons": 99, "aa_comparisons": 7}
    all_rows = [row for group in groups for row in analysis[group]]
    for group in groups:
        require(len(analysis[group]) == expected[group], "unexpected_" + group + "_count")
    for row in all_rows:
        pairs = row["paired_rounds"]
        values = [100 * (1 - item["candidate_ms"] / item["baseline_ms"]) for item in pairs]
        mean = statistics.fmean(values)
        require(all(math.isfinite(v) for v in values), "nonfinite_round", row)
        require(len(values) == row["expected_rounds"], "incomplete_rounds", row)
        require(len({p["round"] for p in pairs}) == len(values), "duplicate_round", row)
        require(all(math.isclose(v, p["improvement_percent"], rel_tol=1e-11, abs_tol=1e-10)
                    for v, p in zip(values, pairs)), "round_arithmetic", row)
        require(math.isclose(mean, row["mean_paired_improvement_percent"],
                             rel_tol=1e-11, abs_tol=1e-10), "mean_arithmetic", row)
        improving = sum(v > 0 for v in values)
        regressing = sum(v < 0 for v in values)
        require(improving == row["improving_rounds"], "improving_count", row)
        require(regressing == row["regressing_rounds"], "regressing_count", row)
        require(sum(v < -3 for v in values) == row["rounds_worse_than_regression_threshold"],
                "worse_than_three_percent_count", row)
        ci = row["ci95_percent"]
        eligible = row["phase"] == "main" and len(values) == 6
        benefit = eligible and mean >= 5 and ci[0] > 0 and improving >= 5
        regression = eligible and mean < -3 and ci[1] < 0 and regressing >= 5
        require(bool(benefit) == row["numeric_benefit"], "benefit_gate", row)
        require(bool(regression) == row["repeatable_regression"], "regression_gate", row)
        exact_ci = exact_bootstrap_ci(values)
        exact_benefit = eligible and mean >= 5 and exact_ci[0] > 0 and improving >= 5
        exact_regression = eligible and mean < -3 and exact_ci[1] < 0 and regressing >= 5
        bootstrap_sensitivity.append(dict(label(row), samples=len(values) ** len(values),
            exact_percentile_ci95=exact_ci, reported_monte_carlo_ci95=ci,
            exact_numeric_benefit=bool(exact_benefit), exact_repeatable_regression=bool(exact_regression),
            gate_changed=bool(exact_benefit) != row["numeric_benefit"]
                         or bool(exact_regression) != row["repeatable_regression"]))

    aa_flags = []
    for row in analysis["aa_comparisons"]:
        ci = row["ci95_percent"]
        flagged = (len(row["paired_rounds"]) == 3
                   and abs(row["mean_paired_improvement_percent"]) >= 5
                   and (ci[0] > 0 or ci[1] < 0)
                   and max(row["improving_rounds"], row["regressing_rounds"]) == 3)
        aa_flags.append(dict(compact(row), independently_flagged=flagged))
    query_noise = any(r["independently_flagged"] and r["configuration"] != "ingestion" for r in aa_flags)
    ingestion_noise = sorted(r["metric"] for r in aa_flags
                             if r["independently_flagged"] and r["configuration"] == "ingestion")
    require(query_noise == analysis["aa_noise_flags"]["query_timing_noise_unresolved"], "aa_query_gate")
    require(ingestion_noise == analysis["aa_noise_flags"]["ingestion_metrics_with_unresolved_noise"],
            "aa_ingestion_gate")
    require(manifest["file_sha256"] == run["file_sha256_after"], "manifest_before_after_drift")
    require(len(run["schedule"]) == len(run["artifacts"]) == 186, "worker_manifest_count")

    resource_paths = ["worker.experimental_activation_ms", "worker.parent_after.rss_bytes",
        "configuration.mcp-char2400.startup_to_initialize_ms",
        "configuration.mcp-char2400.server_after.rss_bytes",
        "configuration.mcp-char2400.node_after.rss_bytes"]
    resource_summary = []
    for variant in ("c_table", "rust_table", "rust_same", "rust_window", "rust_metadata",
                    "c_metadata", "node_window", "node_small"):
        for path in resource_paths:
            rows = [r for r in analysis["resource_comparisons"]
                    if r["variant"] == variant and r["path"] == path]
            if not rows:
                continue
            paired = [r for r in rows if isinstance(r["baseline"], (int, float))
                      and isinstance(r["candidate"], (int, float))]
            resource_summary.append({"variant": variant, "path": path, "samples": len(rows),
                "baseline_arithmetic_mean": statistics.fmean(r["baseline"] for r in paired) if paired else None,
                "candidate_arithmetic_mean": statistics.fmean(r["candidate"] for r in rows),
                "paired_delta_arithmetic_mean": statistics.fmean(r["candidate"] - r["baseline"]
                                                                  for r in paired) if paired else None})

    decision_rows = [{key: r[key] for key in ("variant", "ordinary_production_gate", "stress_only_gate",
        "ordinary_numeric_targets_passed", "stress_numeric_targets_passed", "blocking_key_regressions")}
        for r in analysis["adoption"]]
    controls_passed = [compact(r) for r in analysis["control_comparisons"] if r["numeric_benefit"]]
    representative = [compact(r) for r in analysis["comparisons"]
                      if r["variant"] in ("c_table", "rust_table", "rust_same", "rust_window", "rust_metadata")
                      and r["configuration"] in ("direct-char2400", "mcp-char2400") and r["metric"] == "p95_ms"]
    controls = [compact(r) for r in analysis["control_comparisons"]
                if r["variant"] == "rust_table"
                and r["configuration"] in ("direct-char2400", "mcp-char2400")]
    review = {
        "schema_version": 1,
        "review_date": "2026-11-17",
        "reviewer": "Independent statistical review by recover_rust_work subagent",
        "status": "passed" if not errors else "failed",
        "inputs": {"evidence_commit": "351770ce9950ba60f77e04847a1de386c44dac2c",
            "formal_source_commit": analysis["experiment_commit"], "baseline_commit": analysis["baseline_commit"],
            "files": {p.name: {"path": str(p.resolve()), "sha256": sha256(p)}
                      for p in (analysis_path, run_path, manifest_path)},
            "review_script_sha256": sha256(Path(__file__)),
            "published_analyzer_source_sha256": analysis["analysis_source_sha256"]},
        "execution_method": {
            "prior_read": "Read exact GitHub result blob e2621c07bc3841e5f427210cf1b8531d0f416ae9 and formal job log 133965795078; first independently checked arithmetic in JavaScript.",
            "this_execution": "Re-read local analysis.json, run.json and manifest.json; independently recompute in this standard-library-only Python script; import no product or experiment analyzer code.",
            "round_arithmetic": "100 * (1 - candidate_ms / baseline_ms); arithmetic mean across whole paired rounds; check per-round values and direction counts.",
            "registered_gates": "Re-evaluate >=5 percent mean, positive reported 95 percent CI, >=5/6 positive rounds; regressions require mean<-3 percent, reported CI upper<0 and >=5/6 negative rounds.",
            "bootstrap_sensitivity": "Enumerate every with-replacement whole-round bootstrap sample (6^6=46656 per main comparison; 3^3=27 per A/A comparison); compute exact percentile 95 percent intervals. This post-result sensitivity analysis does not replace the frozen 10000-resample Monte Carlo analysis or redefine acceptance.",
            "source_hash_scope": "Check recorded manifest before/after equality only; do not claim to have reopened original runner binaries."},
        "checks": {"comparison_groups": {g: len(analysis[g]) for g in groups},
            "paired_rows_independently_recomputed": len(all_rows), "arithmetic_and_gate_errors": errors,
            "exact_bootstrap_rows": len(bootstrap_sensitivity),
            "exact_bootstrap_gate_changes": [r for r in bootstrap_sensitivity if r["gate_changed"]],
            "recorded_frozen_hashes_equal": manifest["file_sha256"] == run["file_sha256_after"],
            "recorded_frozen_hash_count": len(manifest["file_sha256"]),
            "audit_counts_from_published_analysis": analysis["audit"],
            "aa_query_noise": query_noise, "aa_ingestion_noise_metrics": ingestion_noise,
            "same_strategy_rust_vs_c_numeric_benefit_count": len(controls_passed)},
        "aa_independent_decisions": aa_flags,
        "published_candidate_decisions": decision_rows,
        "representative_paired_statistics": representative,
        "rust_table_versus_same_strategy_c": controls,
        "resource_descriptive_means": resource_summary,
        "exact_bootstrap_sensitivity": bootstrap_sensitivity,
        "conclusion": {
            "whole_project_rust_rewrite_supported": False,
            "local_table_strategy_supported": True,
            "recommendation_zh": "保留当前 Python+C 架构；本轮结果不构成全面 Rust 重构的必要性证据。Unicode 查表是有证据的局部优化方向；相同策略 C 对照也达到门槛，99条 Rust/C 控制比较没有5%的实质收益。",
            "production_authorization": "This review recommends a decision only and changes no production code, main, release tag or public README."},
        "limitations": [
            "The statistical reviewer re-read summary pair/resource records, not all 186 raw worker reports or 1252200 ledger events; the root agent performs the separate complete offline analyzer replay.",
            "Original host source/binary byte verification (209 files) is a published runner result. This reviewer checked recorded before/after hashes, not the original host binaries.",
            "Exhaustive bootstrap sensitivity is post-result and must not be substituted for the registered Monte Carlo results; per-scenario intervals have no multiplicity adjustment.",
            "Only six paired main rounds and three A/A rounds on one Linux x86-64 runner; ingestion A/A fresh-ingestion CI is wide even though its gate is not triggered.",
            "synthetic61 denotes seed 61 and contains 168 queries; public1015 has 1015 queries; Unicode stress has 96 queries. Query count is not the independent statistical sample size.",
            "Rust candidates retain CPython FFI, the GIL, Python SQLite and significant Python objects. A standalone Rust service, concurrency redesign and a complete Rust-owned retrieval pipeline are unmeasured.",
            "Resource means here are descriptive across 18 worker/cohort pairs. Sampled RSS and different process high-water marks must not be summed as a simultaneous process-tree peak.",
            "Experimental adapter activation cost is not an inherent property of the implementation language."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": review["status"], "input_analysis_sha256": sha256(analysis_path),
        "rows": len(all_rows), "errors": len(errors),
        "exact_bootstrap_gate_changes": len(review["checks"]["exact_bootstrap_gate_changes"]),
        "output": str(args.output)}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
