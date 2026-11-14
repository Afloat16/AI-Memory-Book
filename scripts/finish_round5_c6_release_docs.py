"""Render C6 release documentation only after explicit, fully bound acceptance.

This module is also the read-only evidence validator used by the C6 README
renderer. Importing it does not read reports or write product documentation.
All candidate/publication identities remain blocked until explicitly frozen.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN = None
SOURCE = None
RUNTIME = None
BINDING_COMMIT = None
BINDING_SHA256 = None
EVALUATOR_COMMIT = None
RESULT_COMMIT = None
C6_CHANGE_SUMMARY = None
C6_CHANGE_SUMMARY_ZH = None
PUBLIC = "https://github.com/Afloat16/AI-Memory-Book/blob/v0.3.3/"
BASELINE = {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
    "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"}
PLAN_SHA256 = "b83c385c2e7160318ca2c8fded161937f716d43803c03799fd86fd4f63d484a8"
PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}
THRESHOLDS = {"geometric_mean_p95_improvement": 10,
    "at_least_one_public_native_token_p95_improvement": 15,
    "public_mcp_token1024_p95_improvement": 10,
    "maximum_pooled_p50_p95_regression": 5}
C5_RESULT_COMMIT = "3982ceab2bdce0e9a189135ce261445a3a38d779"
C5_SUMMARY = "benchmarks/reports/round5-c5-performance-43552372788-1/report.summary.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def git_bytes(commit, path):
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT, timeout=30)


def source_hash(commit):
    prefix = "src/memory_book/"
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit, prefix],
                                    cwd=ROOT, timeout=30).decode().splitlines()
    names = sorted(name for name in names if name.endswith(".py"))
    require(bool(names), "Frozen source tree is missing")
    value = hashlib.sha256()
    for name in names:
        value.update(name.removeprefix(prefix).encode() + b"\0" + git_bytes(commit, name) + b"\0")
    return value.hexdigest()


def equivalent(actual, expected):
    if type(actual) is dict and type(expected) is dict:
        return actual.keys() == expected.keys() and all(equivalent(actual[k], expected[k]) for k in actual)
    if type(actual) is list and type(expected) is list:
        return len(actual) == len(expected) and all(equivalent(a, b) for a, b in zip(actual, expected))
    if type(actual) in (int, float) and type(expected) in (int, float):
        return math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-9)
    return type(actual) is type(expected) and actual == expected


def load_accepted_evidence():
    """Fail before any write; C5 or rejected C6 evidence cannot supply approval."""
    for name, value, width in (("SOURCE", SOURCE, 40), ("RUNTIME", RUNTIME, 64),
            ("BINDING_COMMIT", BINDING_COMMIT, 40), ("BINDING_SHA256", BINDING_SHA256, 64),
            ("EVALUATOR_COMMIT", EVALUATOR_COMMIT, 40), ("RESULT_COMMIT", RESULT_COMMIT, 40)):
        require(type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value) is not None,
                "C6 documentation is blocked: final " + name + " is not frozen")
    require(type(RUN) is str and re.fullmatch(r"[0-9]+-1", RUN) is not None,
            "C6 documentation is blocked: the exact first hosted attempt is not bound")
    require(all(type(value) is str and value.strip() and "PENDING" not in value
                for value in (C6_CHANGE_SUMMARY, C6_CHANGE_SUMMARY_ZH)),
            "C6 implementation descriptions have not been reviewed")
    prefix = "benchmarks/reports/round5-c6-performance-" + RUN
    binding_path = "benchmarks/experiments/round5-c6-performance-binding.json"
    binding_raw = (ROOT / binding_path).read_bytes()
    b = json.loads(binding_raw)
    expected_sources = {"baseline": BASELINE, "candidate": {"commit": SOURCE, "runtime_sha256": RUNTIME}}
    require(sha(binding_raw) == BINDING_SHA256 and binding_raw == canonical(b) + b"\n"
            and binding_raw == git_bytes(BINDING_COMMIT, binding_path), "C6 binding bytes or frozen commit differ")
    require(b["evaluator"] == "round5-c6-default-performance-1"
            and b["status"] == "frozen-before-formal-timing" and b["sources"] == expected_sources
            and b["evaluator_commit"] == EVALUATOR_COMMIT and b["packages"] == PACKAGES
            and b["plan_sha256"] == PLAN_SHA256, "C6 source, evaluator or original-plan identity differs")
    require(source_hash(SOURCE) == RUNTIME, "Committed C6 runtime differs")
    plan_raw = git_bytes(EVALUATOR_COMMIT, "benchmarks/experiments/round5-plan.json")
    require(sha(plan_raw) == PLAN_SHA256, "Original numerical plan changed")
    for name, expected in b["evaluator_files"].items():
        require(sha(git_bytes(EVALUATOR_COMMIT, name)) == expected, "Frozen evaluator file differs: " + name)

    a = json.loads((ROOT / "benchmarks/reports/round5-c6-performance-independent-audit.json").read_bytes())
    l = json.loads((ROOT / "benchmarks/reports/round5-c6-performance-local-audit.json").read_bytes())
    report_path = prefix + "/report.json.gz"
    report_raw = (ROOT / report_path).read_bytes()
    summary_path = prefix + "/report.summary.json"
    summary_raw = (ROOT / summary_path).read_bytes()
    s = json.loads(summary_raw)
    require(report_raw == git_bytes(RESULT_COMMIT, report_path)
            and summary_raw == git_bytes(RESULT_COMMIT, summary_path), "C6 original report or summary differs from final result commit")
    require(sha(report_raw) == a["compressed_report_sha256"] == l["report_sha256"] == s["compressed_report_sha256"],
            "C6 audits do not identify the same original report bytes")
    require(sha(gzip.decompress(report_raw)) == a["full_report_sha256"] == s["full_report_sha256"],
            "C6 full report checksum differs")
    require(a["audit_passed"] is True and l["audit_passed"] is True
            and a["sources"] == expected_sources and a["binding_sha256"] == BINDING_SHA256
            and a["evaluator_commit"] == EVALUATOR_COMMIT
            and a["evaluator_files_verified"] == len(b["evaluator_files"]), "C6 independent audit identity differs")
    require(sha((ROOT / "scripts/audit_round5_c6_performance.py").read_bytes()) == a["audit_script_sha256"],
            "Independent audit no longer matches its recorded verifier")
    require(s["status"] == "measurements_completed" and s["error"] is None and s["evaluator_unchanged"] is True
            and s["evaluator"] == s["run"]["evaluator"] == "round5-c6-default-performance-1"
            and s["run"]["binding"] == b and s["run"]["binding_sha256"] == BINDING_SHA256
            and s["run"]["host"]["packages"] == PACKAGES, "Original C6 report identity or completion differs")
    run_id = RUN.removesuffix("-1")
    require(s["run"]["publication"] == {"run_id": run_id, "run_attempt": "1",
            "branch": "validation/v033-round5-c6-performance-" + RUN,
            "claim_branch": "validation/v033-round5-c6-claim-" + BINDING_SHA256}, "C6 report run/claim namespace differs")
    expected_counts = {"workers": 16, "cells": 12, "timed_calls": 56784, "ledger_events": 113568,
        "baseline_candidate_pairs": 28392, "unique_query_configuration_pairs": 7098,
        "native_mcp_provenance_pairs": 18928, "complete_output_differences": 0,
        "recorded_invariant_failures": 0, "negative_timing_samples": 0,
        "zero_timing_samples": 0, "nonfinite_or_invalid_timing_samples": 0}
    require(a["counts"] == expected_counts and l["timed_calls"] == 56784
            and l["retrieval_calls_during_audit"] == 0
            and s["validation"] == {"passed": True, "issues": [], "workers": 16,
                "expected_workers": 16, "timed_calls": 56784, "expected_calls": 56784}, "C6 complete call/equality matrix differs")
    g = a["acceptance_recomputed"]
    require(equivalent(s["acceptance"], g), "Saved C6 acceptance differs from independent arithmetic")
    # This renderer intentionally supports only the no-resource-exception path.
    # A future explicit resource decision needs a separately reviewed document
    # branch; neither a numeric failure nor C5 rejection can ever be overridden.
    require(g["accepted"] is True and g["numeric_gate_passed"] is True and l["accepted"] is True
            and s["acceptance"]["accepted"] is True and s["acceptance"]["numeric_gate_passed"] is True,
            "C6 documentation is blocked: all original acceptance decisions must pass")
    require(g["thresholds_percent"] == THRESHOLDS
            and g["geometric_mean_p95_improvement_percent"] >= 10 - 1e-9
            and g["best_public_native_token_p95_improvement_percent"] >= 15 - 1e-9
            and g["public_mcp_token1024_p95_improvement_percent"] >= 10 - 1e-9
            and g["regressions_above_five_percent"] == [] and g["resource_review"] == []
            and len(g["resource_comparisons"]) == 28
            and all(type(r["mean_change_percent"]) in (int, float)
                    and math.isfinite(r["mean_change_percent"]) and r["mean_change_percent"] <= 10 + 1e-9
                    for r in g["resource_comparisons"]), "C6 fixed numerical/resource gates do not all pass")
    require(len(a["cells"]) == 12 and a["resource_review_required"] is False,
            "C6 comparison matrix or resource decision differs")

    hprefix = "benchmarks/reports/round5-c6-hotpot-regression"
    h = json.loads((ROOT / (hprefix + ".summary.json")).read_bytes())
    hraw = (ROOT / (hprefix + ".json.gz")).read_bytes()
    hotpot = json.loads(gzip.decompress(hraw))
    expected_hotpot = {"native": {"match": 1536}, "component": {"match": 768}}
    require(h["evaluator"] == hotpot["evaluator"] == "round5-c6-hotpot-regression-1"
            and h["status"] == hotpot["status"] == "passed"
            and h["expected_calls"] == hotpot["expected_calls"] == 2304
            and h["counts"] == hotpot["counts"] == expected_hotpot,
            "C6 Hotpot check is incomplete, failed or belongs to another candidate")
    require(h["candidate"] == hotpot["candidate"]
            and {k: h["candidate"][k] for k in ("commit", "runtime_sha256")} == expected_sources["candidate"]
            and h["runtime_sha256_after"] == hotpot["runtime_sha256_after"] == RUNTIME,
            "C6 Hotpot source does not match the accepted performance source")
    require(h["derived_from_report"]["path"] == hprefix + ".json.gz"
            and h["derived_from_report"]["bytes"] == len(hraw)
            and h["derived_from_report"]["sha256"] == sha(hraw), "C6 Hotpot report bytes do not match its summary")
    if "uncompressed_sha256" in h["derived_from_report"]:
        require(h["derived_from_report"]["uncompressed_sha256"] == sha(gzip.decompress(hraw)), "C6 Hotpot raw report checksum differs")
    require(h["helper_sha256"] == hotpot["helper_sha256"]
            == sha((ROOT / "scripts/round5_c6_hotpot_regression.py").read_bytes()), "C6 Hotpot helper changed after execution")
    require(h["dataset"] == hotpot["dataset"] and h["reference_reports"] == hotpot["reference_reports"]
            and h["packages"] == hotpot["packages"] == {"tiktoken": "0.12.0", "pyarrow": "26.0.1"},
            "C6 Hotpot input, reference or package identity differs")
    rows = hotpot["rows"]
    require(len(rows) == 2304 and all(r["status"] == "match"
            and r["actual_payload_sha256"] == r["expected_payload_sha256"] for r in rows), "C6 Hotpot full-payload matrix differs")
    require(Counter((r["stage"], r["status"]) for r in rows)
            == {("native", "match"): 1536, ("component", "match"): 768}, "C6 Hotpot stage counts differ")
    configs = [{"budget_chars": 8000, "tokenizer": name, "budget_tokens": cap}
               for name in ("cl100k_base", "o200k_base") for cap in (512, 1024, 2048)]
    query_ids = {r["id"] for r in rows if r["stage"] == "native" and r["configuration"] == configs[0]}
    require(len(query_ids) == h["dataset"]["queries"] == 256
            and h["dataset"]["parquet_bytes"] == 27452575
            and h["dataset"]["parquet_sha256"] == "c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6",
            "C6 Hotpot frozen input identity differs")
    expected_matrix = Counter(("native", identity, 0, canonical(config)) for identity in query_ids for config in configs)
    expected_matrix.update(("component", identity, repetition, canonical({"budget_chars": 100000}))
                           for identity in query_ids for repetition in range(3))
    require(Counter((r["stage"], r["id"], r["repetition"], canonical(r["configuration"])) for r in rows) == expected_matrix,
            "C6 Hotpot contains missing, duplicated or substituted calls")
    require(set(h["reference_reports"]) == {"native", "component"}, "C6 Hotpot reference stages differ")
    for stage, reference in h["reference_reports"].items():
        ref_path = "benchmarks/results/round4-comparison-43363060062-1/candidate-" + stage + ".json.gz"
        ref_raw = (ROOT / ref_path).read_bytes()
        require(reference["path"] == ref_path and reference["runtime_sha256"] == BASELINE["runtime_sha256"]
                and sha(ref_raw) == reference["file_sha256"] and ref_raw == git_bytes(SOURCE, ref_path),
                "C6 Hotpot historical reference bytes differ")
    ledger_path = hprefix + ".attempts.jsonl.gz"
    ledger_zip = (ROOT / ledger_path).read_bytes()
    ledger_raw = gzip.decompress(ledger_zip)
    ledger = [json.loads(line) for line in ledger_raw.splitlines()]
    require(h["attempt_ledger"]["path"] == ledger_path and h["attempt_ledger"]["gzip_sha256"] == sha(ledger_zip)
            and h["attempt_ledger"]["raw_sha256"] == hotpot["attempt_ledger_sha256"] == sha(ledger_raw)
            and h["attempt_ledger"]["events"] == len(ledger) == 4608
            and h["attempt_ledger"]["starts"] == h["attempt_ledger"]["finishes"] == 2304,
            "C6 Hotpot original ledger checksum/count differs")
    fields = ("sequence", "stage", "id", "repetition", "configuration", "expected_payload_sha256")
    for number, row in enumerate(rows):
        require(row["sequence"] == number
                and ledger[number * 2] == {**{key: row[key] for key in fields}, "event": "started"}
                and ledger[number * 2 + 1] == {**row, "event": "finished"}, "C6 Hotpot events differ from complete saved output")

    c5_raw = (ROOT / C5_SUMMARY).read_bytes()
    require(c5_raw == git_bytes(C5_RESULT_COMMIT, C5_SUMMARY), "Preserved C5 rejection was altered")
    c5 = json.loads(c5_raw)
    require(c5["status"] == "measurements_completed" and c5["validation"]["timed_calls"] == 56784
            and c5["acceptance"]["accepted"] is False and c5["acceptance"]["numeric_gate_passed"] is False
            and c5["acceptance"]["public_mcp_token1024_p95_improvement_percent"] < 10,
            "C5 must retain its complete formal MCP rejection")
    return {"a": a, "l": l, "h": h, "b": b, "g": g, "s": s, "c5": c5,
            "run": RUN, "prefix": prefix}


def write_outputs(outputs):
    """Stage every validated document before replacing any product file."""
    allowed = {ROOT / name for name in ("CHANGELOG.md", "benchmarks/README.md", "docs/validation.md",
        "docs/releases/v0.3.3.md", "README.md", "README.zh-CN.md")}
    require(bool(outputs) and set(outputs) <= allowed, "Unexpected output path")
    require(all("PENDING_" not in text for text in outputs.values()), "A release document still has an unresolved marker")
    staged = []
    try:
        for path, text in outputs.items():
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                    prefix=".c6-doc-stage-", delete=False) as stream:
                stream.write(text)
                staged.append((Path(stream.name), path))
        for temporary, path in staged:
            temporary.replace(path)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)

def render_release_docs(e):
    a, l, h, b, g = (e[key] for key in ("a", "l", "h", "b", "g"))
    PREFIX = e["prefix"]
    C5_MCP_GAIN = e["c5"]["acceptance"]["public_mcp_token1024_p95_improvement_percent"]
    outputs = {}
    def stage(path, text):
        require(path not in outputs, "Duplicate document output")
        outputs[path] = text
    cells = {(c['cohort'], c['id']): c for c in a['cells']}
    require(len(cells) == 12, 'C6 document precondition failed')
    agg = g['geometric_mean_p95_improvement_percent']
    max_resource = max(g['resource_comparisons'], key=lambda x: x['mean_change_percent'])
    maxres = max_resource['mean_change_percent']
    require(maxres <= 10 and not g['resource_review'], 'C6 document precondition failed')
    def gain(config): return -cells['public1015', config]['candidate_change_percent']['p95_ms']
    def lat(config, label): return cells['public1015', config][label]['latency']['p95_ms']
    def url(path): return PUBLIC + path
    regressions = [r for r in a['all_pooled_adverse_latency_metrics'] if r['metric'] in ('p50_ms', 'p95_ms')]
    strict_improvement = all(c['candidate_change_percent'][metric] < 0 for c in a['cells'] for metric in ('p50_ms', 'p95_ms'))
    pooled_sentence = ('All twelve pooled p50 and p95 values improve.' if strict_improvement else
        'Every pooled p50/p95 regression remains within the fixed 5% ceiling; all adverse cells remain in the full review.')
    summary = (f'Pooled p95 geometric mean improves **{agg:.4f}%** against published v0.3.2. '
        f'Public native token512/token1024/token2048 p95 improves **{gain("native-token512"):.4f}% / '
        f'{gain("native-token1024"):.4f}% / {gain("native-token2048"):.4f}%**. '
        f'Actual public SDK MCP token1024 p95 is **{lat("mcp-token1024", "baseline"):.3f} → '
        f'{lat("mcp-token1024", "candidate"):.3f} ms**, an improvement of **{gain("mcp-token1024"):.4f}%**.')

    # The previous release sections remain verbatim below the new one.
    p = ROOT/'CHANGELOG.md'; old = p.read_text(); require(old.startswith('# Changelog\n\n') and '## 0.3.3 —' not in old, 'C6 document precondition failed')
    entry = f'''## 0.3.3 — 2026-11-14

    A normal GitHub release that reduces retrieval metadata and exact token-counting
    work while preserving complete default evidence. All fixed formal performance
    and resource gates pass against published v0.3.2.

    ### Retrieval and exact-count work

    - {C6_CHANGE_SUMMARY}
    - Add a narrow derived metadata index and batch shared chapter/session rows.
      Validate every referenced directory before pruning; use a strict title-score
      upper bound to skip candidates that cannot enter the existing ranking pool.
      Retain ties, full candidate counts and custom/semantic/coverage fallbacks.
    - Reuse identical ordered lexical routes and per-query directory overlaps.
      Reuse certified sealed-block suffix counts and reject impossible supplemental
      pages after the existing source-map checks.
    - Add a lazy per-connection exact-count memo, shared by both tokenizers and
      bounded by 2,048 entries / 2 MiB of retained text objects. Charge Unicode text
      after encoding, preserve complete string keys and exact encoder/core/method
      receiver identities, and release retained text when the connection closes.
    - Keep query-result cache controls, source reads, corruption checks, ranking,
      citations, context limits, schema 3 and dependency requirements unchanged.
      Unknown/custom tokenizer cases retain complete exact counting.
    - Set a separate 4 MiB SQLite pager target. The index has first-open and storage
      costs, and memo container/key/value overhead is additional to its text cap.
      Neither memory setting is a whole-process limit.

    ### Accepted performance and compatibility

    - Complete the single frozen 56,784-call comparison, sixteen sequential workers,
      four balanced AB/BA/BA/AB rounds and twelve pooled cells. All 28,392 complete
      non-timing output pairs and source/scope/budget/cache invariants match.
    - {summary}
    - {pooled_sentence} All per-round observations are retained. The largest
      registered resource mean increase is {maxres:.4f}%, below the 10% review
      trigger; no resource exception is needed.
    - Reproduce all 2,304 saved default outputs on historical Hotpot256: 1,536
      native calls over both tokenizers and three caps, plus 768 component calls.
      This retains old default quality results without a new competitor or Q2 run.
    - Preserve the complete rejected C3 and C5 formal runs, every earlier
      development candidate and all C4/C5/C6 development observations. C5 retains
      its actual-MCP p95 failure ({C5_MCP_GAIN:.6f}% against the unchanged 10% gate). Commit formal source,
      evaluator, binding and each worker checkpoint before progressing.
    - Publish through the explicit normal GitHub release channel, preserving older
      prerelease metadata and existing exact-source CI, package and installer gates.

    [Release notes](docs/releases/v0.3.3.md) · [Full performance review](docs/round5-c6-performance-review.md) ·
    [Source and decisions](docs/optimization-round5.md) · [Upgrade guide](docs/deployment.md#upgrading)

    '''
    stage(p, '# Changelog\n\n'+entry+old[len('# Changelog\n\n'):])

    p = ROOT/'benchmarks/README.md'; old = p.read_text(); old = old.replace('## Current: v0.3.2 completed fourth-round validation','## Historical: v0.3.2 completed fourth-round validation',1)
    section = f'''## Current: v0.3.3 completed fifth-round validation

    Final C6 source is [`{SOURCE[:7]}`](https://github.com/Afloat16/AI-Memory-Book/commit/{SOURCE}),
    runtime SHA256 `{RUNTIME}`. Its sole
    [formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{RUN[:-2]})
    passes all fixed numerical gates and requires no resource exception.

    {summary}

    {C6_CHANGE_SUMMARY}

    All **56,784 calls**, **28,392 complete payload pairs**, twelve pooled cells and
    four balanced rounds are retained. {pooled_sentence} The largest registered
    resource mean increase is **{maxres:.4f}%**. Full per-round adverse observations,
    all resource samples and derived count-memo diagnostics remain in the review.

    | Evidence | Scope and decision |
    |---|---|
    | [Original plan](experiments/round5-plan.json), [C6 addendum](experiments/round5-c6-addendum.json) and [frozen binding](experiments/round5-c6-performance-binding.json) | Exact versions, {len(b['evaluator_files'])} evaluator files, old inputs, ABBA order, cache policy and unchanged acceptance gates. |
    | [C6 correctness checks](reports/round5-c6-correctness.json) and [independent source review](reports/round5-c6-source-review.json) | C6-specific correctness and fallback evidence. Publication separately checks its exact final commit and the required nine CI jobs. |
    | [Retained C5 native development](reports/round5-development/candidate-c5-full/README.md) | C5's 18,928 calls / 9,464 pairs remain retained. Its best public native p95 was below 15%; this historical diagnostic does not substitute for C6 formal acceptance. |
    | [Formal review](../docs/round5-c6-performance-review.md), [summary](reports/round5-c6-performance-{RUN}/report.summary.json) and [original report](reports/round5-c6-performance-{RUN}/report.json.gz) | All formal calls, configurations, source/invariant checks and resource observations. |
    | [Independent arithmetic audit](reports/round5-c6-performance-independent-audit.json) and [frozen saved-ledger audit](reports/round5-c6-performance-local-audit.json) | Recompute saved evidence without further retrieval or timing. |
    | [Final-source Hotpot compatibility](reports/round5-c6-hotpot-regression.summary.json) | All 2,304 historical default output hashes and 4,608 attempt events match. No new quality, competitor timing or Q2 evaluation. |
    | [Retained C3 rejection](../docs/round5-performance-review.md), [retained C5 rejection](../docs/round5-c5-performance-review.md) and [all development decisions](../docs/optimization-round5.md) | Both complete formal rejections remain intact; C5 actual-MCP p95 gain was {C5_MCP_GAIN:.6f}%, below 10%. C4 has development evidence, not a formal acceptance. |

    Query-result caches are disabled or cleared before timers. C6's bounded exact
    count memo is enabled: native token512 starts empty, later native token settings
    reuse counts naturally, and each actual SDK MCP configuration has a fresh
    server process. The 2 MiB text-object cap excludes container/key/value overhead;
    actual RSS is measured separately. These are old-query measurements on one
    host, not a significance or universal-speedup claim.

    Historical competitor measurements below retain their original v0.3.2 version,
    corpus and component boundaries. Competitors were not remeasured in this round.

    '''
    require(old.startswith('# Retrieval experiments\n\n'), 'C6 document precondition failed');stage(p, '# Retrieval experiments\n\n'+section+old[len('# Retrieval experiments\n\n'):])

    p=ROOT/'docs/validation.md';old=p.read_text();marker='## Historical: v0.3.2 completed fourth-round methods and evidence';require(marker in old, 'C6 document precondition failed')
    section=f'''## Current: v0.3.3 completed fifth-round methods and evidence

    The [original plan](../benchmarks/experiments/round5-plan.json),
    [C6 continuation](../benchmarks/experiments/round5-c6-addendum.json) and
    [frozen binding](../benchmarks/experiments/round5-c6-performance-binding.json)
    retain published v0.3.2 as baseline. Final C6 source is `{SOURCE}`,
    runtime SHA256 `{RUNTIME}`; {len(b['evaluator_files'])} evaluator inputs are bound before timing.

    The [single formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{RUN[:-2]})
    completes all **56,784 calls**, sixteen workers and four balanced rounds.
    Independent arithmetic and the frozen saved-ledger auditor verify **113,568
    start/finish events**, **28,392 baseline/candidate complete-output pairs** and
    **18,928 native/MCP provenance pairs**, with zero differences or recorded
    invariant failures. Only `latency_ms` is excluded from payload comparisons.

    {summary}

    {C6_CHANGE_SUMMARY}

    {pooled_sentence} All fixed numerical gates pass. The largest registered
    resource mean increase is **{maxres:.4f}%**, so no resource exception is needed.
    The [complete review](round5-c6-performance-review.md) retains all twelve pooled
    cells, forty-eight per-round cells, adverse observations and twenty-eight
    resource comparisons. [Independent audit](../benchmarks/reports/round5-c6-performance-independent-audit.json) ·
    [Frozen saved-ledger audit](../benchmarks/reports/round5-c6-performance-local-audit.json).

    The existing evaluator phrase "uncached API" refers to query-result caching.
    The per-book exact-count memo is enabled under its registered 2,048-entry /
    2 MiB retained-text cap. Each native book starts empty, character recall does
    not allocate it, and later token configurations reuse earlier counts. Each
    MCP configuration uses a fresh official SDK stdio server process; no MCP memo
    hit rate is inferred from native diagnostics. Transport and normal server
    result-cache writes remain inside MCP timers. Container/keys/counts and
    vocabulary memory are additional to the text-object cap, and actual process
    RSS remains part of the registered resource measurements.

    [Final-source historical compatibility](../benchmarks/reports/round5-c6-hotpot-regression.summary.json)
    reproduces all **2,304** saved default Hotpot256 payload hashes: 1,536 native
    calls over both encoders and three caps plus 768 component calls. All 4,608
    attempt events and unchanged source/index/document projections are checked.
    This supports retention of the old default quality result on these same
    questions. It adds no new competitor timing, Q2 measurement, generated-answer
    accuracy or unseen-domain quality claim.

    The complete [C3 formal rejection](round5-performance-review.md),
    [C5 formal rejection](round5-c5-performance-review.md) and
    [C4/C5/C6 development records](optimization-round5.md) remain unchanged.
    C5 still has `accepted:false`: its actual-MCP p95 gain was {C5_MCP_GAIN:.6f}%,
    below the unchanged 10% gate. The retained C5
    development best public native p95 was below the formal 15% threshold, and is
    not used as a passed gate. Saved hashes and invariants support output equality;
    the offline audit cannot independently re-tokenize omitted response bodies.
    Exact release-commit CI and package/public-installer verification are separate
    publication requirements.

    '''
    stage(p, old.replace(marker,section+marker,1))

    p=ROOT/'docs/releases/v0.3.3.md';old=p.read_text()
    require("Candidate C6" in old and SOURCE in old and RUNTIME in old,
            "Prepare the C6 release-note draft with the same frozen source before rendering")
    old=old.replace('Candidate C6 reduces repeated metadata and exact token-counting work\nwhile preserving retrieval output. Formal performance acceptance is pending;\nthe completed compatibility and upgrade checks are described below.',
        'v0.3.3 reduces repeated metadata and exact token-counting work while preserving\ncomplete default retrieval output. Its registered formal performance gates and\nfinal-source historical compatibility checks pass against published v0.3.2.')
    start=old.index('**PENDING_FORMAL_ACCEPTANCE**');end=old.index('\n## Historical component strengths and limits',start)
    rows=[]
    for cohort in ('synthetic61','public1015'):
     for config in ('native-char4000','mcp-char4000','native-token512','native-token1024','native-token2048','mcp-token1024'):
      c=cells[cohort,config]
      rows.append(f'| {cohort} | {config} | {c["baseline"]["latency"]["p95_ms"]:.3f} | {c["candidate"]["latency"]["p95_ms"]:.3f} | {c["candidate_change_percent"]["p95_ms"]:+.2f}% |')
    formal=f'''The [sole frozen run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{RUN[:-2]})
    completes **56,784 calls**, four balanced rounds and all **28,392 complete
    non-timing output pairs**. All correctness and fixed numerical gates pass;
    the largest registered resource mean increase is **{maxres:.4f}%**, below the
    10% review trigger. No resource exception is needed.

    {summary}

    {C6_CHANGE_SUMMARY}

    | Cohort | Configuration | v0.3.2 p95, ms | v0.3.3 p95, ms | Change |
    |---|---|---:|---:|---:|
    '''+ '\n'.join(rows)+f'''

    {pooled_sentence} Every per-round observation and all resource comparisons,
    including adverse samples, remain in the
    [complete review]({url('docs/round5-c6-performance-review.md')}).
    [Original report]({url(PREFIX+'/report.json.gz')}) ·
    [Summary]({url(PREFIX+'/report.summary.json')}) ·
    [Independent arithmetic audit]({url('benchmarks/reports/round5-c6-performance-independent-audit.json')}) ·
    [Frozen saved-ledger audit]({url('benchmarks/reports/round5-c6-performance-local-audit.json')}).

    Query-result caching is disabled or cleared before timing. The registered
    derived count memo is enabled: native later token configurations reuse earlier
    counts, while each actual SDK MCP configuration starts a fresh server process.
    All first calls remain in the samples. MCP timing includes the roundtrip,
    serialization and normal server result-cache writes. These repeated old-query
    measurements on one host do not establish statistical significance or a
    universal speedup. The complete [C3 rejection]({url("docs/round5-performance-review.md")}) and
    [C5 rejection]({url("docs/round5-c5-performance-review.md")}) remain retained.
    C5 actual-MCP p95 gain was {C5_MCP_GAIN:.6f}%, below 10%, and its
    `accepted:false` is unchanged. All development observations remain retained; neither earlier gains nor old competitor timings supply a
    missing gate. [Plan]({url('benchmarks/experiments/round5-plan.json')}) ·
    [Frozen binding]({url('benchmarks/experiments/round5-c6-performance-binding.json')}).
    '''
    old=old[:start]+formal+old[end:]
    old=old.replace('Final C6 startup, ingestion, RSS and storage costs belong to its separate formal acceptance.',
        f'Final C6 startup, ingestion, RSS and storage costs are retained in the [formal review]({url("docs/round5-c6-performance-review.md")}).')
    require('PENDING_' not in old, 'C6 document precondition failed')
    stage(p, old)
    return outputs


def main():
    evidence = load_accepted_evidence()
    outputs = render_release_docs(evidence)
    write_outputs(outputs)
    print(json.dumps({"written": [str(p.relative_to(ROOT)) for p in outputs], "candidate": SOURCE, "run": RUN, "runtime_approval_changed": False}))


if __name__ == "__main__":
    main()
