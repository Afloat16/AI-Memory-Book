"""Independently aggregate saved first-pass component costs; never run retrieval.

This stdlib-only reader intentionally imports no frozen evaluator, adapter,
tokenizer or quality-scoring helper. It reads numeric cost records and checks
their original gzip/summary/checkpoint identities. Question text, answers and
quality judgments are neither inspected nor copied into the audit output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

ENCODINGS = ("cl100k_base", "o200k_base")
STAGES = ("baseline-component", "candidate-component", "claude-mem-fts",
          "ai-memory-hybrid", "billion-context", "candidate-semantic-component")
TOKEN_FIELDS = ("search_payload_tokens", "search_content_tokens",
                "read_payload_tokens", "read_content_tokens")
COST_FIELDS = ("queries", "unmapped_native_hits", "queries_with_unmapped_native_hits",
               "mean_read_calls", "mean_read_ms", *("mean_" + key for key in TOKEN_FIELDS))
POLICY_FIELDS = ("read_policy", "native_metadata_policy")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return sha(canonical(value).encode())


def nonnegative_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def percentile(values, probability):
    """Linear interpolation at (n-1)*p, implemented without producer imports."""
    require(bool(values), "No latency samples")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def latencies(values):
    require(all(nonnegative_number(value) for value in values), "Invalid latency sample")
    return {"samples": len(values), "p50_ms": percentile(values, .5),
            "p95_ms": percentile(values, .95), "mean_ms": statistics.fmean(values)}


def token_mean(rows, field):
    # None is a missing surface, not a zero-cost observation. Follow the
    # published all-rows mean boundary and disclose sample coverage separately.
    values = [row[field] for row in rows]
    if any(value is None for value in values):
        return None
    return {encoding: statistics.fmean(value[encoding] for value in values) for encoding in ENCODINGS}


def recompute(report):
    """Return independent numerical aggregates and internal ID sets only."""
    stage = report["stage"]
    require(stage in STAGES, "Unexpected component stage")
    first = [row for row in report["timing_rows"] if row["repetition"] == 0]
    require(bool(first), "Missing first-pass component records")
    ids = [row["id"] for row in first]
    require(len(ids) == len(set(ids)), "Duplicate first-pass query identity")
    for row in first:
        require(row["status"] == "ok", "Failed first-pass cost record")
        require(all(nonnegative_number(row[key]) for key in ("search_ms", "bridge_ms", "read_ms")),
                "Invalid first-pass latency")
        require(type(row["read_calls"]) is int and row["read_calls"] >= 0, "Invalid read count")
        native_ids = row["native_hit_ids"]
        mapped = [identity for identity in native_ids if identity is not None]
        metadata = sum(identity is None for identity in native_ids)
        require(row["hit_ids"] == mapped and len(native_ids) <= 5
                and len(mapped) == len(set(mapped)), "Native/mapped top-five boundary differs")
        require(row["unmapped_native_hits"] == metadata
                and (stage == "ai-memory-hybrid" or metadata == 0), "Metadata hit accounting differs")
        expected_reads = len(mapped) if stage == "ai-memory-hybrid" else 0
        require(row["read_calls"] == expected_reads
                and len(row["read_payload_sha256"]) == expected_reads, "First-pass native read policy differs")
        for field in TOKEN_FIELDS:
            values = row[field]
            require(values is None or (set(values) == set(ENCODINGS)
                    and all(type(value) is int and value >= 0 for value in values.values())),
                    "Missing or invalid reference-tokenizer axis")
        require(row["search_payload_tokens"] is not None
                and row["read_payload_tokens"] is not None and row["read_content_tokens"] is not None,
                "Required native payload/read token surface is missing")
        if row["read_calls"] == 0:
            require(row["read_ms"] == 0 and all(value == 0 for field in (
                "read_payload_tokens", "read_content_tokens") for value in row[field].values()),
                "A zero-read query contains invented read costs")
    computed = {"queries": len(first),
        "unmapped_native_hits": sum(row["native_hit_ids"].count(None) for row in first),
        "queries_with_unmapped_native_hits": sum(None in row["native_hit_ids"] for row in first),
        "mean_read_calls": statistics.fmean(row["read_calls"] for row in first),
        "mean_read_ms": statistics.fmean(row["read_ms"] for row in first),
        **{"mean_" + field: token_mean(first, field) for field in TOKEN_FIELDS}}
    # Read timings in the raw record are already the stored sum of all native
    # reads for that query. Add to that query's search bridge before sorting.
    combined = latencies([row["bridge_ms"] + row["read_ms"] for row in first])
    bridge = latencies([row["bridge_ms"] for row in first])
    require(set(report["native_costs"]) == set(COST_FIELDS) | set(POLICY_FIELDS),
            "Unexpected native_costs key; audit all numerical fields explicitly")
    require({key: report["native_costs"][key] for key in COST_FIELDS} == computed,
            "Published native_costs differs from original first-pass records")
    require(report["first_pass_search_plus_all_reads_latency"] == combined,
            "Published search-plus-reads latency differs from per-query sums")
    require(report["first_pass_roundtrip_latency"] == bridge,
            "Published first-pass search bridge latency differs")
    contexts = []
    axes = set()
    for config in report["configurations"]:
        axis = (config["tokenizer"], config["budget_tokens"])
        require(axis not in axes, "Duplicate common-context configuration")
        axes.add(axis)
        rows = config["query_results"]
        require(len(rows) == len(first) and {row["id"] for row in rows} == set(ids),
                "Common-context count/identity differs from the first pass")
        for row in rows:
            require(set(row["context_tokens"]) == set(ENCODINGS)
                    and all(type(value) is int and value >= 0 for value in row["context_tokens"].values()),
                    "Invalid common-context token record")
        means = {encoding: statistics.fmean(row["context_tokens"][encoding] for row in rows)
                 for encoding in ENCODINGS}
        require(config["metrics"]["mean_context_tokens"] == means,
                "Published common-context token mean differs from original records")
        contexts.append({"budget_tokenizer": axis[0], "budget_tokens": axis[1], "queries": len(rows),
                         "mean_context_tokens": means})
    require(axes == {(encoding, budget) for encoding in ENCODINGS for budget in (512, 1024, 2048)},
            "Missing common-context tokenizer/budget axis")
    selected = [{key: row[key] for key in ("id", "repetition", "status", "read_calls", "read_ms",
        "search_ms", "bridge_ms", "unmapped_native_hits", *TOKEN_FIELDS)} for row in first]
    # Hash only; never publish individual IDs or any quality/source content.
    result = {"stage": stage, "first_pass_query_ids_sha256": digest(sorted(ids)),
        "selected_original_cost_rows_sha256": digest(selected), "recomputed_native_costs": computed,
        "first_pass_search_bridge_latency": bridge,
        "first_pass_search_plus_all_reads_latency": combined,
        "first_pass_native_search_latency": latencies([row["search_ms"] for row in first]),
        "native_content_availability": {field: {"available": sum(row[field] is not None for row in first),
            "missing": sum(row[field] is None for row in first)} for field in TOKEN_FIELDS},
        "additional_per_query_sum_means": {
            "search_plus_read_payload_tokens": {encoding: statistics.fmean(
                row["search_payload_tokens"][encoding] + row["read_payload_tokens"][encoding] for row in first)
                for encoding in ENCODINGS},
            "search_plus_read_content_tokens": {encoding: statistics.fmean(
                row["search_content_tokens"][encoding] + row["read_content_tokens"][encoding] for row in first)
                for encoding in ENCODINGS} if all(row["search_content_tokens"] is not None for row in first) else None},
        "common_packed_context": contexts, "validation": {"passed": True,
            "all_native_cost_means_equal": True, "read_and_metadata_counts_equal": True,
            "per_query_sum_latency_equal": True, "common_context_means_equal": True}}
    return result


def committed_file(root, commit, relative):
    path = root / relative
    raw = path.read_bytes()
    result = subprocess.run(["git", "ls-tree", commit, "--", relative], cwd=root,
                            check=True, text=True, capture_output=True).stdout.strip()
    require(bool(result), "Audit input missing from the specified results commit")
    metadata, name = result.split("\t", 1)
    mode, kind, object_sha = metadata.split()
    algorithm = "sha1" if len(object_sha) == 40 else "sha256"
    actual = hashlib.new(algorithm, b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(name == relative and mode != "120000" and kind == "blob" and object_sha == actual,
            "Audit input bytes differ from the specified committed result")
    return raw


def audit(root, checkpoint_relative, results_commit):
    checkpoint_raw = committed_file(root, results_commit, checkpoint_relative)
    checkpoint = json.loads(checkpoint_raw)
    require(checkpoint["status"] == "complete-verified-snapshot" and checkpoint["assessment_exit_code"] == 0,
            "Full-stage strict assessment must finish before this independent cost audit")
    run_id = checkpoint["run_id"]
    require(all(char.isalnum() or char == "-" for char in run_id), "Invalid run identity")
    directory = "benchmarks/results/round2-" + run_id
    assessed_path = directory + "/assessment.json"
    assessed_raw = committed_file(root, results_commit, assessed_path)
    require(checkpoint["assessment_outputs"][assessed_path] == sha(assessed_raw), "Assessment bytes differ")
    assessment = json.loads(assessed_raw)
    require(assessment["status"] == "complete-verified-snapshot" and assessment["run_id"] == run_id,
            "Full-stage assessment did not pass")
    expected_queries = assessment["distinct_queries"]
    require(expected_queries == 256, "This audit expects the registered 256-query cohort")
    stages = []
    for stage in STAGES:
        raw_path, summary_path = directory + "/" + stage + ".json.gz", directory + "/" + stage + ".summary.json"
        compressed = committed_file(root, results_commit, raw_path)
        summary_raw = committed_file(root, results_commit, summary_path)
        record = checkpoint["stages"][stage]
        require(record["status"] == "completed" and record["exit_code"] == 0
                and record["outputs"] == {raw_path: sha(compressed), summary_path: sha(summary_raw)},
                "Stage is incomplete or its saved hashes differ")
        original = gzip.decompress(compressed)
        report, summary = json.loads(original), json.loads(summary_raw)
        require(summary["full_report_sha256"] == sha(original), "Original decompressed hash differs")
        require(report["stage"] == summary["stage"] == stage
                and report["host_id"] == summary["host_id"] == checkpoint["host"]["id"]
                and report["dataset"]["queries"] == expected_queries
                and report["dataset"]["sha256"] == assessment["dataset_sha256"]
                and report["validation"] == {"passed": True, "failures": []}, "Stage identity or validation differs")
        for key in ("plan_sha256", "binding_sha256", "cohort_manifest_sha256"):
            require(report[key] == summary[key] == checkpoint[key], "Stage protocol identity differs")
        result = recompute(report)
        require(result["recomputed_native_costs"]["queries"] == expected_queries, "Missing first-pass records")
        require(summary["native_costs"] == report["native_costs"]
                and summary["first_pass_search_plus_all_reads_latency"] == result["first_pass_search_plus_all_reads_latency"]
                and summary["first_pass_roundtrip_latency"] == result["first_pass_search_bridge_latency"],
                "Published summary differs from independently recomputed native costs")
        summary_context = {(c["tokenizer"], c["budget_tokens"]): c["metrics"]["mean_context_tokens"]
                           for c in summary["configurations"]}
        require(len(summary["configurations"]) == 6 and summary_context == {
            (c["budget_tokenizer"], c["budget_tokens"]): c["mean_context_tokens"] for c in result["common_packed_context"]},
            "Published summary differs from independently recomputed common-context means")
        result.update(host_id=report["host_id"], dataset_sha256=report["dataset"]["sha256"],
            supplied_documents_sha256=report["frozen_corpus"]["documents_sha256"],
            candidate_binding_status=report.get("candidate_binding_status", "frozen-before-scoring"),
            input_files={raw_path: sha(compressed), summary_path: sha(summary_raw)},
            decompressed_original_sha256=sha(original))
        stages.append(result)
    for key in ("first_pass_query_ids_sha256", "dataset_sha256", "supplied_documents_sha256", "host_id"):
        require(len({stage[key] for stage in stages}) == 1, "Component identity/host differs")
    return {"audit_version": 1, "status": "passed", "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id, "results_commit": results_commit,
        "auditor_sha256": sha(Path(__file__).read_bytes()),
        "prerequisite_files": {checkpoint_relative: sha(checkpoint_raw), assessed_path: sha(assessed_raw)},
        "components": len(stages), "first_pass_records": len(stages) * expected_queries,
        "tokenizers": list(ENCODINGS), "stages": stages,
        "scope": "Independent aggregation of saved numeric first-pass records only. No new query, scoring, model, source-text inspection or upstream retokenization; no prior-run timing pooled.",
        "boundaries": {
            "native_payload": "Stored canonical native JSON payload counts. Book, Bun/SQLite FTS, HTTP/MCP and Node return different native shapes; this is not one interchangeable whole-product interface or universal wire-envelope count.",
            "native_content": "Separately exposed native text content counts when available. Missing content remains null; it is never filled with zero or inferred by deleting payload fields.",
            "reads": "Original per-query read_ms and read token counts already sum all declared native reads. This audit recomputes means from those stored sums; individual read timers and original text are not retained here and are not reconstructed.",
            "combined_latency": "For each first-pass query, bridge_ms + read_ms; then linear-interpolated p50/p95 and arithmetic mean. Percentiles are never added to each other.",
            "common_context": "Whole-block evidence context after the shared supplied-source packer, at each declared budget and tokenizer. It is neither native content nor native payload and must not substitute for either cost.",
            "zero_and_null": "Zero reads means no extra read calls in this registered component policy, not a claim of a free or supported native feature. Null means the text-only surface was not available for an all-query mean.",
            "billing": "Reference-encoding counts of these surfaces; no provider billing, model prompt/history overhead or complete memory write/summarize/generate lifecycle claim."}}


def markdown(result):
    def pair(values):
        return "null" if values is None else " / ".join(f"{values[e]:.3f}" for e in ENCODINGS)
    lines = ["# Independent round-two component cost audit", "",
        f"Run `{result['run_id']}`, immutable result commit `{result['results_commit']}`. "
        f"All {result['components']} components and {result['first_pass_records']:,} first-pass cost records passed. "
        "The separate full-stage assessment passed before this audit. No retrieval, scoring or model calls were repeated.", "",
        "Every token pair below is **cl100k_base / o200k_base**. `null` is unavailable, not zero.", "",
        "| Component | Native search payload | Native search content | All-read payload | All-read content | Reads/query | Mean read ms | Metadata hits / queries |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for stage in result["stages"]:
        c = stage["recomputed_native_costs"]
        lines.append("| " + " | ".join([stage["stage"], *(pair(c["mean_" + field]) for field in TOKEN_FIELDS),
            f"{c['mean_read_calls']:.6f}", f"{c['mean_read_ms']:.6f}",
            f"{c['unmapped_native_hits']} / {c['queries_with_unmapped_native_hits']}"]) + " |")
    lines += ["", "## First-pass latency and total native message counts", "",
        "| Component | Search bridge p50 / p95 / mean ms | Search plus all reads p50 / p95 / mean ms | Search + read payload tokens | Search + read content tokens |",
        "| --- | --- | --- | --- | --- |"]
    for stage in result["stages"]:
        values = []
        for key in ("first_pass_search_bridge_latency", "first_pass_search_plus_all_reads_latency"):
            values.append(" / ".join(f"{stage[key][metric]:.6f}" for metric in ("p50_ms", "p95_ms", "mean_ms")))
        extra = stage["additional_per_query_sum_means"]
        lines.append("| " + " | ".join([stage["stage"], *values,
            pair(extra["search_plus_read_payload_tokens"]), pair(extra["search_plus_read_content_tokens"])]) + " |")
    lines += ["", "## Common packed context, a separate surface", "",
        "Each cell gives the mean tokens under the **same tokenizer that enforces that column's budget**. "
        "The JSON also retains the other reference encoding for every resulting context.", "",
        "| Component | cl100k 512 | cl100k 1024 | cl100k 2048 | o200k 512 | o200k 1024 | o200k 2048 |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for stage in result["stages"]:
        cells = {(c["budget_tokenizer"], c["budget_tokens"]): c for c in stage["common_packed_context"]}
        lines.append("| " + " | ".join([stage["stage"], *(f"{cells[(e,b)]['mean_context_tokens'][e]:.3f}"
            for e in ENCODINGS for b in (512, 1024, 2048))]) + " |")
    lines += ["", "## Interpretation and reproducibility", ""]
    lines += ["- **" + key.replace("_", " ") + ":** " + value for key, value in result["boundaries"].items()]
    lines += ["", "The JSON records compressed, decompressed, summary and checkpoint hashes, the auditor hash, "
        "and the digest of the exact selected numeric records. The auditor verifies local input bytes against "
        "their Git blobs at the supplied results commit. Policy strings are retained in original reports; "
        "all numerical `native_costs` fields, first-pass combined latency and context means are independently recomputed.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--checkpoint", required=True, help="Path relative to repository-root")
    parser.add_argument("--results-commit", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New .json audit path; also writes .md")
    args = parser.parse_args()
    require(len(args.results_commit) in (40, 64)
            and all(char in "0123456789abcdef" for char in args.results_commit),
            "Use an immutable full hexadecimal results commit, not a branch name")
    require(args.output.suffix == ".json" and not args.output.exists()
            and not args.output.with_suffix(".md").exists(), "Preserve audit evidence; choose new output paths")
    require(not Path(args.checkpoint).is_absolute() and ".." not in Path(args.checkpoint).parts,
            "Checkpoint must be an ordinary repository-relative path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = audit(args.repository_root.resolve(), args.checkpoint, args.results_commit)
    except Exception as error:
        failure = {"status": "failed", "results_commit": args.results_commit,
                   "auditor_sha256": sha(Path(__file__).read_bytes()),
                   "error_type": type(error).__name__, "reason": str(error)}
        args.output.write_text(json.dumps(failure, indent=2) + "\n")
        raise
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(markdown(result) + "\n")
    print(json.dumps({"status": result["status"], "components": result["components"],
                      "first_pass_records": result["first_pass_records"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
