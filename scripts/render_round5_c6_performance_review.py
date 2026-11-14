"""Render the complete C6 review from its final saved report and two audits.

This standard-library formatter performs no retrieval or timing. It cannot
render before the exact final report, independent audit and strict saved-ledger
audit exist. It preserves rejected and resource-review-required outcomes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUN = "43557136276-1"
BINDING_COMMIT = "4d737fc60a12b60433f6f020614b296908b4c833"
BINDING_SHA256 = "2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a"
EVALUATOR_COMMIT = "0bd9ccf48bc9ed6a666888838ca11580c3104b98"
AUDITOR_SHA256 = "fe9bf79e6c998ae6aa9523a2876ec2111f5c66a9f184c3fa1de69f3fed9027e2"
SOURCES = {
    "baseline": {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
                 "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"},
    "candidate": {"commit": "1bd97221e31e8e975498ece00f4bbfb3e0426aac",
                  "runtime_sha256": "cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78"},
}
PREFIX = "benchmarks/reports/round5-c6-performance-" + RUN
REPORT = ROOT / PREFIX / "report.json.gz"
SUMMARY = ROOT / PREFIX / "report.summary.json"
AUDIT = ROOT / "benchmarks/reports/round5-c6-performance-independent-audit.json"
LOCAL_AUDIT = ROOT / "benchmarks/reports/round5-c6-performance-local-audit.json"
BINDING = ROOT / "benchmarks/experiments/round5-c6-performance-binding.json"
HOTPOT = ROOT / "benchmarks/reports/round5-c6-hotpot-regression.summary.json"
DEVELOPMENT = ROOT / "benchmarks/reports/round5-development/candidate-c6-full/summary.json"
OUTPUT = ROOT / "docs/round5-c6-performance-review.md"
COHORTS = ("synthetic61", "public1015")
CONFIGS = ("native-char4000", "mcp-char4000", "native-token512",
           "native-token1024", "native-token2048", "mcp-token1024")
METRICS = ("p50_ms", "p95_ms", "mean_ms")
THRESHOLDS = {
    "geometric_mean_p95_improvement": 10,
    "at_least_one_public_native_token_p95_improvement": 15,
    "public_mcp_token1024_p95_improvement": 10,
    "maximum_pooled_p50_p95_regression": 5,
    "resource_mean_increase_review": 10,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_bytes(commit, path):
    return subprocess.check_output(
        ["git", "show", commit + ":" + str(path.relative_to(ROOT))],
        cwd=ROOT, timeout=30)


def same(actual, expected):
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    if isinstance(expected, (int, float)):
        return type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            same(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            same(x, y) for x, y in zip(actual, expected))
    return actual == expected


def load_evidence(result_commit):
    require(re.fullmatch(r"[0-9a-f]{40}", result_commit) is not None,
            "Supply the exact final hosted result commit; no provisional result is accepted")
    binding_raw = BINDING.read_bytes()
    require(sha(binding_raw) == BINDING_SHA256
            and binding_raw == git_bytes(BINDING_COMMIT, BINDING), "Frozen binding differs")
    binding = json.loads(binding_raw)
    require(binding["evaluator_commit"] == EVALUATOR_COMMIT
            and binding["sources"] == SOURCES and len(binding["evaluator_files"]) == 51,
            "Frozen source/evaluator identity differs")
    require(sha((ROOT / "scripts/audit_round5_c6_performance.py").read_bytes()) == AUDITOR_SHA256,
            "Independent auditor changed")
    audit, local = json.loads(AUDIT.read_bytes()), json.loads(LOCAL_AUDIT.read_bytes())
    require(audit["audit_passed"] is True and local["audit_passed"] is True,
            "Both saved-result audits must succeed before review generation")
    require(audit["sources"] == SOURCES and audit["binding_sha256"] == BINDING_SHA256
            and audit["evaluator_commit"] == EVALUATOR_COMMIT
            and audit["evaluator_files_verified"] == 51
            and audit["audit_script_sha256"] == AUDITOR_SHA256, "Independent audit identity differs")
    compressed = REPORT.read_bytes()
    raw = gzip.decompress(compressed)
    summary_raw = SUMMARY.read_bytes()
    require(compressed == git_bytes(result_commit, REPORT)
            and summary_raw == git_bytes(result_commit, SUMMARY), "Final hosted result bytes differ")
    require(sha(raw) == audit["full_report_sha256"]
            and sha(compressed) == audit["compressed_report_sha256"]
            and sha(compressed) == local["report_sha256"], "Report/audit hashes differ")
    summary = json.loads(summary_raw)
    require(summary["status"] == "measurements_completed" and summary["error"] is None
            and summary["evaluator_unchanged"] is True
            and summary["evaluator"] == "round5-c6-default-performance-1", "Incomplete/wrong C6 result")
    require(summary["run"]["binding"] == binding
            and summary["run"]["binding_sha256"] == BINDING_SHA256
            and summary["run"]["publication"] == {
                "run_id": RUN.removesuffix("-1"), "run_attempt": "1",
                "branch": "validation/v033-round5-c6-performance-" + RUN,
                "claim_branch": "validation/v033-round5-c6-claim-" + BINDING_SHA256},
            "Hosted source/run/publication identity differs")
    require(summary["full_report_sha256"] == sha(raw)
            and summary["compressed_report_sha256"] == sha(compressed),
            "Saved summary identifies other report bytes")
    summary_record = audit["saved_file_checksums"].get(str(SUMMARY.resolve()))
    if summary_record is None:
        suffix = "/" + str(SUMMARY.relative_to(ROOT))
        matches = [v for k, v in audit["saved_file_checksums"].items() if k.endswith(suffix)]
        require(len(matches) == 1, "Summary is absent or ambiguous in independent audit")
        summary_record = matches[0]
    require(summary_record == {"bytes": len(summary_raw), "sha256": sha(summary_raw)},
            "Summary changed after independent audit")
    counts = audit["counts"]
    fixed_counts = {
        "workers": 16, "cells": 12, "timed_calls": 56784, "ledger_events": 113568,
        "baseline_candidate_pairs": 28392, "unique_query_configuration_pairs": 7098,
        "native_mcp_provenance_pairs": 18928, "complete_output_differences": 0,
        "recorded_invariant_failures": 0}
    require(all(counts[key] == value for key, value in fixed_counts.items()),
        "Complete C6 audit counts differ")
    require(local["timed_calls"] == 56784 and local["retrieval_calls_during_audit"] == 0
            and audit["retrieval_calls_executed"] == audit["models_or_tokenizers_executed"]
                == audit["tests_or_timing_runs_executed"] == 0, "Audit execution boundary differs")
    acceptance = audit["acceptance_recomputed"]
    require(same(summary["acceptance"], acceptance)
            and local["accepted"] is acceptance["accepted"]
            and summary["plan"]["thresholds_percent"] == THRESHOLDS, "Decision or thresholds differ")
    cells = audit["cells"]
    require(len(cells) == 12 and {(c["cohort"], c["id"]) for c in cells}
            == {(cohort, config) for cohort in COHORTS for config in CONFIGS},
            "Twelve-cell matrix is incomplete")
    require(all(len(c[label]["by_round"]) == 4 for c in cells for label in SOURCES),
            "Forty-eight round cells are incomplete")
    require(len(acceptance["resource_comparisons"]) == 28
            and len(audit["logical_storage"]) == 6, "Resource/storage matrix is incomplete")
    candidates = [m for m in audit["native_token_count_memo_audit"] if m["label"] == "candidate"]
    require(len(candidates) == 8 and all(m["available"] and m["empty_connection_start_verified"]
            and len(m["native_configurations"]) == 4 for m in candidates),
            "Eight fresh candidate books / 32 native memo observations are incomplete")
    hotpot_raw, development_raw = HOTPOT.read_bytes(), DEVELOPMENT.read_bytes()
    require(hotpot_raw == git_bytes(EVALUATOR_COMMIT, HOTPOT)
            and development_raw == git_bytes(EVALUATOR_COMMIT, DEVELOPMENT),
            "Pre-formal compatibility/development archive changed")
    hotpot, development = json.loads(hotpot_raw), json.loads(development_raw)
    require(hotpot["status"] == "passed" and hotpot["candidate"]["commit"] == SOURCES["candidate"]["commit"]
            and hotpot["candidate"]["runtime_sha256"] == SOURCES["candidate"]["runtime_sha256"]
            and hotpot["counts"] == {"native": {"match": 1536}, "component": {"match": 768}}
            and hotpot["saved_evidence_audit"]["ledger_events_checked"] == 4608,
            "Final-source Hotpot compatibility differs")
    require(development["status"] == "completed" and development["total_calls"] == 18928
            and development["complete_payload_pairs"] == 9464
            and development["formal_acceptance_evaluated"] is False,
            "Development archive identity or boundary differs")
    return {"a": audit, "s": summary, "l": local, "b": binding, "g": acceptance,
            "h": hotpot, "d": development, "result_commit": result_commit}


def code(value):
    return chr(96) + str(value) + chr(96)


def table(headers, rows):
    def cell(value):
        return str(value).replace("|", r"\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(cell, headers)) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(map(cell, row)) + " |" for row in rows)
    return "\n".join(lines)


def percent(value):
    return "undefined (zero baseline)" if value is None else f"{value:+.6f}%"


def nested(value, path):
    for part in path.split("."):
        value = value[part]
    return value


def render(e):
    a, s, g, h, d = (e[k] for k in ("a", "s", "g", "h", "d"))
    cells = {(c["cohort"], c["id"]): c for c in a["cells"]}
    accepted, numeric = g["accepted"], g["numeric_gate_passed"]
    state = "observed pass" if accepted else ("resource review required" if numeric else "rejected")
    decision = ("The complete run meets the registered numerical and resource gates."
                if accepted else "Numerical gates pass, but the original accepted:false remains pending required resource review."
                if numeric else "The complete run fails its registered numerical acceptance; accepted:false is retained.")
    out = [f"# Round-five C6 formal performance review — {state}",
           f"**{decision}** This is the sole frozen C6 run against published v0.3.2. "
           "All 56,784 recorded calls completed, and all 28,392 complete non-timing output pairs match. "
           "This review preserves the original decision; it does not approve a release or replace final-commit CI and packaging.",
           f"The independent arithmetic and original report both retain "
           f"{code('numeric_gate_passed:' + str(numeric).lower())} and "
           f"{code('accepted:' + str(accepted).lower())}. The observed aggregate p95 gain is "
           f"**{g['geometric_mean_p95_improvement_percent']:.10f}%**, best public native-token p95 gain "
           f"**{g['best_public_native_token_p95_improvement_percent']:.10f}%**, and public actual-MCP token1024 "
           f"p95 gain **{g['public_mcp_token1024_p95_improvement_percent']:.10f}%**.",
           "## Frozen identities and retained evidence",
           table(["Role", "Commit", "Runtime SHA256"], [
               [label, code(v["commit"]), code(v["runtime_sha256"])] for label, v in SOURCES.items()]),
           f"Evaluator {code(EVALUATOR_COMMIT)}; binding commit {code(BINDING_COMMIT)}; "
           f"binding SHA256 {code(BINDING_SHA256)}; final hosted result commit {code(e['result_commit'])}. "
           "All **51 evaluator input hashes** were verified against their bound Git objects, including retained "
           "C3/C4/C5 inputs and both prior formal rejections.",
           f"[Sole run {RUN}](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{RUN.removesuffix('-1')}) · "
           "[Original plan](../benchmarks/experiments/round5-plan.json) · "
           "[C6 registration](../benchmarks/experiments/round5-c6-addendum.json) · "
           "[Frozen binding](../benchmarks/experiments/round5-c6-performance-binding.json) · "
           "[Source review](../benchmarks/reports/round5-c6-source-review.json)",
           f"Saved measurement interval: **{s['started_at']} → {s['finished_at']}**. The observed host reports "
           f"**{s['run']['host']['cpu_count']} CPUs**, {s['run']['host']['platform']}, "
           f"Python **{s['run']['host']['python']}** and SQLite **{s['run']['host']['sqlite']}**. "
           f"Frozen packages: {code(json.dumps(s['run']['host']['packages'], sort_keys=True))}. "
           "These describe this run and do not establish a hardware-independent guarantee.",
           "## Matrix and timing boundaries",
           "The full old cohorts contain 168 synthetic and 1,015 public-conversation questions. Six configurations "
           "and four balanced **AB/BA/BA/AB** rounds produce sixteen sequential worker processes and twelve pooled cells. "
           "Character settings use 4,000 characters; token settings use cl100k_base, an 8,000-character ceiling, "
           "the specified 512/1,024/2,048-token cap and at most five results.",
           "**Native query-result caching is disabled; derived exact-count reuse is enabled.** Each fresh candidate "
           "MemoryBook starts without an allocated memo. Character recall leaves it absent; native token512 starts empty. "
           "Later token1024 and token2048 configurations naturally reuse counts from earlier configurations on the same "
           "connection. All first queries remain included. No extra warmup, discarded first query or selective clearing "
           "is introduced. Earlier shorthand such as 'uncached API' describes query-result caching.",
           "**Each actual official-SDK MCP configuration starts a fresh server process.** Query-result cache entries "
           "are cleared outside the timer. The normal server cache write, serialization, server work and SDK roundtrip "
           "remain timed. The derived memo may warm naturally inside that process; no private MCP memo counters are "
           "exposed. Native hit rates cannot be assigned to MCP. OS/SQLite warmth remains possible: this is not a "
           "cold-storage experiment or an experiment with every cache disabled.",
           "The per-connection memo retains at most **2,048 entries / 2,097,152 post-encode text-object bytes**, shared "
           "by the supported encoders. Key/container/count/encoder overhead is additional. The separate **4,096 KiB** "
           "pager target is connection-local. Neither setting caps whole-process memory. Native RSS includes evaluator "
           "and corpus allocations; actual MCP server memory is sampled separately.",
           "## Complete-output and saved-record audit",
           f"The [independent auditor](../scripts/audit_round5_c6_performance.py), SHA256 {code(AUDITOR_SHA256)}, "
           "uses only standard-library saved-data and Git-object reads. It performs zero retrieval, tokenizer/model, "
           "test or timing workloads. The frozen evaluator's separate strict saved-ledger audit also adds no calls.",
           table(["Check", "Verified count"], [[key.replace("_", " "), f"{value:,}"] for key, value in a["counts"].items()]),
           "Every worker and every original start/finish event is retained in original order. Complete non-timing "
           "native/MCP payload digests, MCP envelope/provenance digests and all recorded source/scope/budget/cache "
           "invariants are compared. Only latency_ms is excluded from stable response equality. The audit verifies "
           "saved digests and calculations; omitted response bodies are not reconstructed or re-tokenized. "
           "audit_passed:true means the records check out, independently of the numerical acceptance result.",
           "## All twelve pooled latency cells",
           "Each synthetic cell has 672 samples per version and each public cell has 4,060. Percentiles linearly "
           "interpolate at (N − 1) × quantile over all four rounds' samples; round percentiles are not averaged. "
           "Negative changes mean lower latency. Decisions use the unrounded values."]
    headers = ["Corpus", "Configuration", "Baseline p50 ms", "C6 p50 ms", "p50 change",
               "Baseline p95 ms", "C6 p95 ms", "p95 change", "Baseline mean ms", "C6 mean ms", "Mean change"]
    pooled = []
    for cohort in COHORTS:
        for config in CONFIGS:
            c = cells[cohort, config]
            row = [cohort, config]
            for metric in METRICS:
                row.extend([f"{c['baseline']['latency'][metric]:.6f}",
                            f"{c['candidate']['latency'][metric]:.6f}",
                            percent(c["candidate_change_percent"][metric])])
            pooled.append(row)
    out.append(table(headers, pooled))
    out.extend(["## Unchanged acceptance gates",
                "For each cell, r is C6 pooled p95 divided by baseline pooled p95. The aggregate is "
                "100 × (1 − exp(sum(log(r)) / 12)). Each cell has equal weight; it is not a query-weighted "
                "mean or the geometric mean of percentage gains. Native gains cannot replace an actual-MCP gate."])
    gate_rows = []
    for label, key, threshold in (
            ("Aggregate pooled p95 improvement", "geometric_mean_p95_improvement_percent", 10),
            ("Best public native-token p95 improvement", "best_public_native_token_p95_improvement_percent", 15),
            ("Public actual-MCP token1024 p95 improvement", "public_mcp_token1024_p95_improvement_percent", 10)):
        value = g[key]
        gate_rows.append([label, f"at least {threshold}%", f"{value:.10f}%",
                          f"{value-threshold:+.10f} percentage points",
                          "Satisfied" if value >= threshold - 1e-9 else "**Failed**"])
    gate_rows.extend([
        ["Complete stable outputs and recorded invariants", "all equal; zero failures",
         "28,392 equal pairs; zero failures", "—", "Satisfied"],
        ["Pooled p50/p95 regression", "no increase greater than 5%",
         f"{len(g['regressions_above_five_percent'])} flagged comparisons", "—",
         "Satisfied" if not g["regressions_above_five_percent"] else "**Failed**"],
        ["Resource mean increase", "greater than 10% requires explicit review",
         f"{len(g['resource_review'])} triggered comparisons", "—",
         "No exception needed" if not g["resource_review"] else "**Review required; no automatic waiver**"]])
    out.append(table(["Requirement", "Threshold", "Observed", "Margin", "Decision"], gate_rows))
    out.append(f"The original result remains {code('accepted:' + str(accepted).lower())}. "
               + ("All fixed numeric gates pass and no resource trigger requires an exception."
                  if accepted else "The failure or required review is not overridden by this document."))
    out.extend(["## Every round: all 48 cohort/configuration cells",
                "Round 0 is AB, rounds 1 and 2 are BA, and round 3 is AB. Each cell retains "
                "168 or 1,015 samples per version. No round or adverse value is omitted."])
    for cohort in COHORTS:
        rows = []
        for round_no in range(4):
            for config in CONFIGS:
                c = cells[cohort, config]
                row = [round_no, config]
                for metric in METRICS:
                    old = c["baseline"]["by_round"][round_no][metric]
                    new = c["candidate"]["by_round"][round_no][metric]
                    row.extend([f"{old:.6f}", f"{new:.6f}", percent(100*(new/old-1))])
                rows.append(row)
        out.extend(["### " + cohort, table(["Round", *headers[1:]], rows)])
    out.append("## Every adverse latency observation")
    for heading, key in (("Pooled", "all_pooled_adverse_latency_metrics"),
                         ("Per round", "all_per_round_adverse_latency_metrics")):
        rows = a[key]
        out.append("### " + heading)
        out.append(table(["Corpus", "Configuration", "Round", "Metric", "Increase"], [
            [r["cohort"], r["config"], r.get("round", "pooled"), r["metric"],
             percent(r["change_percent"])] for r in rows]) if rows else
            "No positive latency change was recorded in this category.")
    out.extend(["## All 28 resource comparisons",
                "These retain the four original samples per version and cohort. Acceptance compares arithmetic "
                "means in original units; byte observations below are displayed as MiB. A mean increase above 10% "
                "requires an explicit cause and independent review. This document does not grant an exception."])
    workers = {(w["cohort"], w["label"], w["round"]): w for w in s["workers"]}
    resource_rows = []
    for r in g["resource_comparisons"]:
        divisor = 2**20 if r["metric"].endswith("_bytes") else 1
        unit = "MiB" if divisor != 1 else "ms"
        samples = {}
        for label in SOURCES:
            samples[label] = [nested(workers[r["cohort"], label, k], r["metric"]) for k in range(4)]
            require(same(sum(samples[label])/4, r[label]["mean"]), "Resource mean/samples disagree")
        resource_rows.append([r["cohort"], r["metric"], unit,
            ", ".join(f"{x/divisor:.6f}" for x in samples["baseline"]),
            ", ".join(f"{x/divisor:.6f}" for x in samples["candidate"]),
            f"{r['baseline']['mean']/divisor:.6f}", f"{r['candidate']['mean']/divisor:.6f}",
            percent(r["mean_change_percent"]),
            "Review required" if r in g["resource_review"] else "No trigger"])
    out.append(table(["Corpus", "Metric", "Unit", "Baseline four samples", "C6 four samples",
                      "Baseline mean", "C6 mean", "Mean change", "Resource rule"], resource_rows))
    out.append("RSS is a process observation, not the exact-count memo allocation. High-water marks can retain "
               "earlier peaks and do not establish equal live memory. The experiment does not isolate the cause "
               "of any individual resource change. Startup, ingestion, cache and index costs remain visible.")
    out.extend(["### Logical database storage", table(
        ["Corpus", "Phase", "Baseline mean bytes", "C6 mean bytes", "Difference bytes", "Change"],
        [[r["cohort"], r["phase"], f"{r['baseline_bytes']['mean']:.0f}",
          f"{r['candidate_bytes']['mean']:.0f}", f"{r['mean_difference_bytes']:+.0f}",
          percent(r["mean_change_percent"])] for r in a["logical_storage"]]),
        "These are SQLite logical page-count × page-size observations, not index-only allocations or "
        "filesystem/RSS measurements. Earlier C3 one-sample upgrade/index probes retain their own source "
        "identity in the release notes; they are not new C6 upgrade measurements."])
    out.extend(["## All 32 native memo configuration observations",
                "Snapshots occur outside timers: before the configuration, immediately after its retained first "
                "call, and after the configuration. Entries and text bytes show those three snapshots. Counter "
                "deltas below belong only to that configuration. A first call may already hit because later "
                "native settings inherit the same connection; this is disclosed, not removed from the samples."])
    memo_rows, by_config, snapshots = [], defaultdict(lambda: defaultdict(int)), []
    for m in a["native_token_count_memo_audit"]:
        if m["label"] != "candidate":
            require(m["available"] is False, "Baseline unexpectedly exposes candidate memo counters")
            continue
        for c in m["native_configurations"]:
            snaps = [c[k] for k in ("before", "after_first_call", "after")]
            snapshots.extend(snaps)
            first, delta = c["first_call_counter_delta"], c["configuration_counter_delta"]
            memo_rows.append([m["worker"], c["id"], c["first_query_id"],
                " / ".join(str(v["entries"]) for v in snaps),
                " / ".join(str(v["text_bytes"]) for v in snaps),
                f"{first['hits']} / {first['misses']}", f"{delta['hits']} / {delta['misses']}",
                delta["evictions"], delta["uncertified_bypasses"], delta["oversized_bypasses"],
                delta["invalidations"]])
            cohort = next(name for name in COHORTS if "-" + name + "-" in m["worker"])
            for key, value in delta.items():
                by_config[cohort, c["id"]][key] += value
    require(len(memo_rows) == 32, "Memo table omitted a configuration")
    out.append(table(["Worker", "Configuration", "First query ID", "Entries before/first/after",
                      "Text bytes before/first/after", "First-call hits/misses", "All hits/misses",
                      "Evictions", "Uncertified bypasses", "Oversized bypasses", "Invalidations"], memo_rows))
    out.append(f"The maximum **recorded snapshot** contains {max(v['entries'] for v in snapshots):,} entries "
               f"and {max(v['text_bytes'] for v in snapshots):,} retained text-object bytes. These sampled maxima "
               "are not a continuously observed peak. The independent audit checks every snapshot against "
               "2,048 entries and 2,097,152 bytes and checks exact continuity across native configurations.")
    hit_rows = []
    for cohort in COHORTS:
        for config in ("native-token512", "native-token1024", "native-token2048"):
            delta = by_config[cohort, config]
            total = delta["hits"] + delta["misses"]
            hit_rows.append([cohort, config, delta["hits"], delta["misses"],
                             f"{100*delta['hits']/total:.6f}%" if total else "not applicable",
                             delta["evictions"], delta["uncertified_bypasses"]])
    out.extend(["### Aggregate eligible count-lookup shares", table(
        ["Corpus", "Configuration", "Hits", "Misses", "Hits / (hits + misses)", "Evictions", "Uncertified bypasses"], hit_rows),
        "These are text-count lookup shares, not query hit rates or causal speedup estimates. Bypassed custom/"
        "uncertified count operations are outside that denominator. Published v0.3.2 has no such counters and "
        "is recorded as unavailable. Actual MCP counters were not collected; no MCP hit rate is inferred."])
    out.extend(["## Correctness history, development and old-cohort compatibility",
                "C6 batches at most 400 exact source-turn pairs inside the original read snapshot and permits "
                "single-span source-reference reuse at most once per page capture. Source integrity checks, "
                "custom/malformed/low-limit fallbacks and nested mutable reference independence remain intact. "
                "The pre-timing alias issue and the later isolated-import fixture correction remain in "
                "[source review](../benchmarks/reports/round5-c6-source-review.json) and "
                "[CI fixture-fix evidence](../benchmarks/reports/round5-c6-ci-fixture-fix.json). "
                "Nine green jobs on the fixture-fix commit verify the identical product tree; final release "
                "publication still needs all nine jobs on its own final commit.",
                f"The sole native development run retained **{d['total_calls']:,} calls / "
                f"{d['complete_payload_pairs']:,} complete output pairs**, with its own native-only aggregate "
                f"p95 gain **{d['geometric_mean_p95_improvement_percent']:.10f}%**. Its "
                f"{len(d['all_pooled_adverse_metrics'])} pooled and "
                f"{len(d['all_per_round_adverse_metrics'])} per-round adverse metrics remain in the "
                "[development archive](../benchmarks/reports/round5-development/candidate-c6-full/README.md). "
                "It contains no actual-MCP or formal RSS acceptance evidence and supplies no missing formal gate.",
                "Final-source C6 reproduces **2,304 / 2,304** saved default v0.3.2 Hotpot256 payload hashes: "
                "**1,536 native** calls across both encoders and three caps, plus **768 component** calls. "
                "All **4,608** original start/finish events were reconciled. The "
                "[compatibility summary](../benchmarks/reports/round5-c6-hotpot-regression.summary.json) "
                "retains exact source/input/helper identities and unchanged source/index/document projections. "
                "This reuses previously scored questions; it adds no new quality, competitor timing, Q2, "
                "generated-answer accuracy or unseen-domain claim."])
    for name, path in (("C3", "round5-performance-review.md"), ("C5", "round5-c5-performance-review.md")):
        previous = a["continuation_provenance"]["rejected_" + name.lower()]
        require(previous["original_accepted"] is False, "Prior rejection was relabeled")
        out.append(f"The complete [{name} rejection]({path}) remains unchanged: aggregate p95 gain "
                   f"{previous['aggregate_p95_gain_percent']:.10f}%, best public native gain "
                   f"{previous['public_native_best_gain_percent']:.10f}%, public actual-MCP gain "
                   f"{previous['public_mcp_token1024_gain_percent']:.10f}%; original accepted:false. "
                   "Its figures are not added to C6.")
    out.extend(["C4 has retained development evidence and was never a bound formal acceptance. C6's separate "
                "source, binding and single hosted result determine its own verdict. No successful subset, "
                "alternative source, repeated formal sample or earlier result replaces an adverse observation.",
                "## Decision scope and reproducible evidence",
                decision + " All observed values above are from the saved C6 run. Repeated old queries on one host "
                "do not establish statistical significance, unseen-domain quality, universal speedup or "
                "whole-product superiority over another repository. Competitors were not remeasured.",
                f"[Full original report](../{PREFIX}/report.json.gz) · "
                f"[Original summary](../{PREFIX}/report.summary.json) · "
                "[Independent arithmetic audit](../benchmarks/reports/round5-c6-performance-independent-audit.json) · "
                "[Strict saved-ledger audit](../benchmarks/reports/round5-c6-performance-local-audit.json)",
                table(["Artifact", "SHA256"], [
                    [str(p.relative_to(ROOT)), code(sha(p.read_bytes()))]
                    for p in (REPORT, SUMMARY, AUDIT, LOCAL_AUDIT, BINDING, HOTPOT, DEVELOPMENT, Path(__file__).resolve())]),
                "The release gate remains separate: final-commit CI, approved exact runtime, package and asset "
                "verification, public installer verification and any required explicit resource acceptance "
                "must all complete. This review never writes the runtime approval table or modifies raw reports."])
    return "\n\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-commit", required=True,
                        help="Exact final hosted result Git commit, available only after completion")
    args = parser.parse_args()
    require(not OUTPUT.exists(), "Preserve the existing C6 review; explicitly review any replacement")
    evidence = load_evidence(args.result_commit)
    rendered = render(evidence)
    with OUTPUT.open("x") as stream:
        stream.write(rendered)
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "sha256": sha(OUTPUT.read_bytes()),
                      "accepted": evidence["g"]["accepted"], "new_measurements": 0}))


if __name__ == "__main__":
    main()

