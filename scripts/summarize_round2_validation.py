"""Strictly verify every registered round-two stage, then derive public tables."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import round2_data
from benchmarks.component_eval import canonical_json
from benchmarks.round2_eval import (INVARIANTS, atomic, digest, frozen_inputs, grouped_metrics,
    native_configurations, now, sha, stages, summary_of)
from benchmarks.semantic_eval import paired_changes
from benchmarks.token_compare import latency_summary, summarize_rows


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def sample_key(row):
    return canonical_json(row["configuration"]), row["repetition"], row["id"]


def verify_samples(report, plan, query_ids):
    stage = report["stage"]
    states = report["attempt_states"]
    ledger = "".join(canonical_json(row) + "\n" for row in states).encode()
    require(hashlib.sha256(ledger).hexdigest() == report["ledger_sha256"], "Attempt ledger bytes differ")
    starts = [row for row in states if row["event"] == "started"]
    finishes = [row for row in states if row["event"] == "finished"]
    timing = report["timing_rows"]
    configs = native_configurations(plan) if stage.endswith("native") else ["search"]
    expected = {(canonical_json(config), repetition, identity) for config in configs
                for repetition in range(plan["common"]["repeats"]) for identity in query_ids}
    if stage == "export":
        expected = set()
    count = len(expected)
    require(len(states) == 2 * count and len(starts) == len(finishes) == len(timing) == count,
            "Missing, duplicated or unfinished query attempts")
    require(report["attempts_started"] == report["attempts_finished"] == count, "Attempt counts differ")
    require([row["seq"] for row in starts] == list(range(1, count + 1))
            and [row["seq"] for row in finishes] == list(range(1, count + 1)), "Attempt sequence differs")
    require({sample_key(row) for row in starts} == expected, "Registered configuration/query/repetition axes differ")
    for started, finished, measured in zip(starts, finishes, timing, strict=True):
        without_envelope = {key: value for key, value in finished.items() if key not in {"event", "seq", "at"}}
        require(without_envelope == measured and started["id"] == measured["id"]
                and started["repetition"] == measured["repetition"] and started["stage"] == stage,
                "Finished sample disagrees with its original attempt")
        require(measured.get("status") == "ok", "Failed request in measured matrix")
        if stage.endswith("native"):
            require(sample_key(measured) == sample_key(started) and finite(measured["elapsed_ms"]), "Invalid native sample")
            require(not any(measured[key] for key in INVARIANTS), "Native per-attempt invariant failed")
        else:
            require(finite(measured["search_ms"]) and finite(measured["bridge_ms"]), "Invalid component latency")
            native_ids = measured["native_hit_ids"]
            require(len(native_ids) <= 5 and measured["hit_ids"] == [identity for identity in native_ids if identity is not None]
                    and len(measured["native_result_id_sha256"]) == len(native_ids)
                    and len(set(measured["native_result_id_sha256"])) == len(native_ids)
                    and measured["unmapped_native_hits"] == native_ids.count(None)
                    and (stage == "ai-memory-hybrid" or measured["unmapped_native_hits"] == 0)
                    and finite(measured["read_ms"]), "Invalid native metadata accounting or read cost")
            require(len(measured["hit_ids"]) <= 5 and len(set(measured["hit_ids"])) == len(measured["hit_ids"]),
                    "Invalid native top-five results")
            expected_reads = len(measured["hit_ids"]) if stage == "ai-memory-hybrid" and measured["repetition"] == 0 else 0
            require(measured["read_calls"] == expected_reads, "Declared native read policy changed")
            require(len(measured["read_payload_sha256"]) == expected_reads, "Missing native read payload digest")
    if stage != "export" and not stage.endswith("native"):
        first = [row for row in timing if row["repetition"] == 0]
        expected_latencies = {
            "native_search_latency": [row["search_ms"] for row in timing],
            "adapter_roundtrip_latency": [row["bridge_ms"] for row in timing],
            "first_pass_roundtrip_latency": [row["bridge_ms"] for row in first],
            "repeat_roundtrip_latency": [row["bridge_ms"] for row in timing if row["repetition"] > 0],
            "first_pass_search_plus_all_reads_latency": [row["bridge_ms"] + row["read_ms"] for row in first]}
        require(all(report[key] == latency_summary(values) for key, values in expected_latencies.items()),
                "Component latency summary differs from samples")


def verify_configurations(report, plan, query_ids):
    if report["stage"] == "export":
        require(not report["configurations"], "Export unexpectedly contains scored queries")
        return
    native = report["stage"].endswith("native")
    expected = native_configurations(plan) if native else [
        {"tokenizer": encoding, "budget_tokens": tokens} for encoding, tokens in
        itertools.product(plan["components"]["tokenizers"], plan["components"]["token_budgets"])]
    configs = report["configurations"]
    keys = ("budget_chars", "tokenizer", "budget_tokens") if native else ("tokenizer", "budget_tokens")
    require(len(configs) == len(expected)
            and [{key: config[key] for key in keys} for config in configs] == expected, "Configuration axis/order changed")
    for config in configs:
        rows = config["query_results"]
        require(len(rows) == len(query_ids) and {row["id"] for row in rows} == set(query_ids), "Wrong distinct question set")
        require(all("query" not in row and "answer" not in row and "text" not in row for row in rows), "Source text leaked into public rows")
        require(config["metrics"] == summarize_rows(rows) and config["by_group"] == grouped_metrics(rows), "Quality summary differs from rows")
        require(not any(config["invariants"].values()) and not config["metrics"]["context_size_mismatches"], "Context invariant failed")
        require(all(row["context_tokens"][config["tokenizer"]] <= config["budget_tokens"] for row in rows), "Exact context cap exceeded")
        if native:
            matched = [row for row in report["timing_rows"] if row["configuration"] == {key: config[key] for key in keys}]
            require(config["latency"]["samples"] == len(rows) * plan["common"]["repeats"] == len(matched), "Latency sample count changed")
            require(config["latency"] == latency_summary([row["elapsed_ms"] for row in matched])
                    and config["first_pass_latency"] == latency_summary([row["elapsed_ms"] for row in matched if row["repetition"] == 0])
                    and config["repeat_pass_latency"] == latency_summary([row["elapsed_ms"] for row in matched if row["repetition"] > 0]),
                    "Native latency summary differs from samples")
            require(not config["repeat_context_mismatches"], "Native deterministic outputs changed between repetitions")
            original = {row["id"]: row for row in rows}
            require(all(sample["context_sha256"] == original[sample["id"]]["context_sha256"]
                        and sample["evidence_ranks"] == original[sample["id"]]["evidence_ranks"] for sample in matched),
                    "Repeated native evidence does not match the published first-pass rows")
            require(all(sample["row_sha256"] == digest(original[sample["id"]]) for sample in matched if sample["repetition"] == 0),
                    "First-pass native evidence row hash differs")


def verify_stage(root, result_dir, stage, checkpoint, plan, binding, manifest):
    record = checkpoint["stages"][stage]
    compressed, summary_path = result_dir / (stage + ".json.gz"), result_dir / (stage + ".summary.json")
    expected_files = {str(path.relative_to(root)): sha(path) for path in (compressed, summary_path)}
    require(record["status"] == "completed" and record.get("exit_code") == 0
            and record["outputs"] == expected_files, "Stage checkpoint is incomplete or its output hashes differ: " + stage)
    raw = gzip.decompress(compressed.read_bytes())
    report, summary = json.loads(raw), json.loads(summary_path.read_bytes())
    require(summary == summary_of(report, hashlib.sha256(raw).hexdigest()), "Raw/summary projection differs: " + stage)
    require(report["stage"] == stage and report["host_id"] == checkpoint["host"]["id"]
            and report["protocol"] == plan["protocol"] and report["plan_sha256"] == checkpoint["plan_sha256"]
            and report["binding_sha256"] == checkpoint["binding_sha256"]
            and report["cohort_manifest_sha256"] == checkpoint["cohort_manifest_sha256"]
            and report["evaluator_sha256"] == binding["evaluator_sha256"], "Stage source/host identity differs")
    require(report["dataset"]["sha256"] == manifest["dataset_sha256"]
            and report["dataset"]["queries"] == manifest["expected_queries"], "Stage dataset differs")
    require(report["validation"] == {"passed": True, "failures": []}
            and report["configured_generative_model_calls"] == 0, "Stage measurement validation failed")
    verify_samples(report, plan, manifest["selected_ids"])
    verify_configurations(report, plan, manifest["selected_ids"])
    require(all(config["metrics"]["answerable_queries"] == manifest["expected_queries"]
                and config["metrics"]["required_evidence"] == manifest["required_evidence"]
                for config in report["configurations"]), "Registered question or evidence denominator changed")
    metadata = report.get("metadata", {})
    if stage.startswith(("baseline-", "candidate-")):
        expected = plan["baseline"] if stage.startswith("baseline-") else binding["candidate"]
        require(metadata["source_provenance"]["git_commit"] == expected["commit"]
                and metadata.get("source_sha256_before", metadata.get("source_sha256")) == expected["source_sha256"]
                and metadata["source_sha256_after"] == expected["source_sha256"]
                and metadata["source_unchanged"] is True and metadata["originals_unchanged"] is True,
                "Book source provenance differs")
    upstream = {"claude-mem-fts": "claude-mem", "ai-memory-hybrid": "ai-memory", "billion-context": "billion-context"}
    if stage in upstream:
        lock = json.loads((root / binding["upstream_locks"][upstream[stage]]).read_bytes())
        require(metadata["commit"] == lock["commit"], "Measured upstream commit differs")
        if stage == "ai-memory-hybrid":
            require(metadata["binary_sha256"] == lock["binary_sha256"]
                    and metadata["embedding_provider"] == "local"
                    and metadata["embedding_model"]["files"] == lock["embedding_model"]["files"],
                    "Native ai-memory binary/model boundary differs")
    require(report["resources"]["sampling_interval_ms"] == 20
            and report["resources"]["samples"].get("setup", 0) > 0, "RSS measurement missing")
    if stage != "export":
        require(report["resources"]["samples"].get("queries", 0) > 0, "Query RSS measurement missing")
    return report


def comparison(old, new):
    result = []
    for before, after in zip(old["configurations"], new["configurations"], strict=True):
        changes = paired_changes(before["query_results"], after["query_results"])
        result.append({**{key: after[key] for key in ("budget_chars", "tokenizer", "budget_tokens") if key in after},
            "baseline_complete_evidence_rate": before["metrics"]["complete_evidence_rate"],
            "candidate_complete_evidence_rate": after["metrics"]["complete_evidence_rate"],
            **changes})
    return result


def markdown(assessment, reports):
    lines = ["# Round two: new HotpotQA selection and same-host components", "",
        "The candidate, source versions and 256-question selection were frozen before scoring. All 256 IDs are disjoint from the previous Hotpot128. This is a new selection from the same scoped distractor corpus, not a new domain or a generated-answer evaluation.", "",
        "Integrity checks passed for every registered engine, configuration and repetition. This does not declare a quality improvement. Every selected paragraph and support annotation remains in the denominators.", "",
        "## Native API: complete evidence and latency", "",
        "| Mode | Characters | Tokenizer | Tokens | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for stage, report in reports.items():
        if not stage.endswith("native"):
            continue
        for config in report["configurations"]:
            m, t = config["metrics"], config["latency"]
            lines.append(f"| {stage} | {config['budget_chars']} | {config['tokenizer']} | {config['budget_tokens']} | {m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | {m['mean_context_tokens'][config['tokenizer']]:.1f} | {t['p50_ms']:.3f} | {t['p95_ms']:.3f} |")
    lines += ["", "## Shared-page component quality", "",
        "Identical supplied pages, project scope, top-five limit, citation format and whole-block packer. Component quality is measured on the first pass; all three repetitions' native hits, timings and any repeat differences remain in the raw reports.", "",
        "| Component | Tokenizer | Tokens | Evidence recall | Complete evidence | MRR | Context tokens |",
        "|---|---|---:|---:|---:|---:|---:|"]
    components = {stage: report for stage, report in reports.items() if stage != "export" and not stage.endswith("native")}
    for stage, report in components.items():
        for config in report["configurations"]:
            m = config["metrics"]
            lines.append(f"| {stage} | {config['tokenizer']} | {config['budget_tokens']} | {m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | {m['mrr']:.4f} | {m['mean_context_tokens'][config['tokenizer']]:.1f} |")
    lines += ["", "## Search and returned-payload boundaries", "",
        "| Component | Adapter p50 ms | Adapter p95 ms | First search + reads p50 / p95 ms | Search payload o200k | Full-read payload o200k | Reads/question | Mean full-read ms | Metadata hits |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for stage, report in components.items():
        t, c = report["adapter_roundtrip_latency"], report["native_costs"]
        combined = report["first_pass_search_plus_all_reads_latency"]
        lines.append(f"| {stage} | {t['p50_ms']:.3f} | {t['p95_ms']:.3f} | {combined['p50_ms']:.3f} / {combined['p95_ms']:.3f} | {c['mean_search_payload_tokens']['o200k_base']:.1f} | {c['mean_read_payload_tokens']['o200k_base']:.1f} | {c['mean_read_calls']:.2f} | {c['mean_read_ms']:.3f} | {c['unmapped_native_hits']} |")
    lines += ["", "Book is in-process Python including its native context assembly; claude-mem is SQLite FTS through Bun; ai-memory is local hybrid through HTTP/MCP; billion-context is its native search kernel through Node. Timings share a host but do not establish a whole-product speed multiplier. ai-memory reads every mapped top-five page on the first pass under a fixed policy; an agent could choose fewer reads. Native payload, text-only content and common packed evidence are distinct token surfaces.", "",
        "## Low-overlap and multi-hop groups", "",
        "Below is the registered 512-token cl100k view (8,000 characters for native APIs). All other group/budget rows remain in each machine-readable summary.", "",
        "| Mode | Group | Questions | Complete evidence | Evidence recall |",
        "|---|---|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage == "export":
            continue
        config = next(c for c in report["configurations"] if c["tokenizer"] == "cl100k_base" and c["budget_tokens"] == 512
                      and c.get("budget_chars", 8000) == 8000)
        for group in ("low_lexical_overlap_le_0.25", "multiple_required_evidence", "cross_session", "cross_chapter"):
            m = config["by_group"].get(group)
            if m:
                lines.append(f"| {stage} | {group} | {m['queries']} | {m['complete_evidence_rate']:.2%} | {m['evidence_recall']:.2%} |")
            else:
                lines.append(f"| {stage} | {group} | 0 | n/a | n/a |")
    lines += ["", "## Preparation, memory and storage", "",
        "| Mode | Setup wall ms | Setup RSS peak MiB | Query RSS peak MiB | Native-state bytes | SQLite main / WAL / SHM bytes |",
        "|---|---:|---:|---:|---:|---|"]
    for stage, report in reports.items():
        if stage == "export":
            continue
        rss, state = report["resources"]["sampled_process_tree_peak_rss_bytes"], report["storage_before_close"]
        sqlite = "/".join(str(state.get(key, "n/a")) for key in ("sqlite_main_file_bytes", "sqlite_wal_file_bytes", "sqlite_shm_file_bytes"))
        lines.append(f"| {stage} | {report['preparation']['engine_setup_wall_ms']:.3f} | {rss['setup']/1048576:.2f} | {rss['queries']/1048576:.2f} | {state['regular_file_bytes']} | {sqlite} |")
    lines += ["", "Setup is outside query timing. Native Book reports separate source ingestion and optional index construction; component Book opens a common frozen archive. Upstream metadata separately records native write/index/startup phases when available. Billion's supplied-source component keeps its index in memory. Preparation download/cache sizes and elapsed time are retained in the run checkpoint. No model generation calls are configured.", "",
        "RSS is the worker plus its descendants sampled every 20 ms, including the evaluator and loaded corpus. Sampling yields an observed lower bound and summed RSS can double-count shared pages; this is not unique physical memory. Native-state bytes exclude the harness attempt ledger and symlinked model caches. Full phase metadata, vector bytes and database statistics remain in the raw/summary reports.", "",
        "Native ai-memory metadata pages retain their original top-k slots and complete native payload cost. Their missing supplied-document mapping is recorded as null and earns zero evidence credit; the evaluator does not replace them with extra hits. Unknown non-null supplied IDs, duplicated identities and scope mismatches fail integrity checks.", "",
        "## Provenance and limitations", "",
        f"- Run: `{assessment['run_id']}`; source: `{assessment['source_commit']}`.",
        f"- Dataset SHA256: `{assessment['dataset_sha256']}`; selected-ID SHA256: `{assessment['selected_ids_sha256']}`.",
        f"- Native baseline/candidate paired query/configuration cases: **{assessment['native_query_configuration_pairs']}**.",
        f"- Required source annotations: **{assessment['required_evidence']}**; supplied paragraphs: **{assessment['supplied_paragraphs']}**.",
        "- All cases are answerable; this selection does not measure abstention, hallucination or final-answer accuracy.",
        "- HotpotQA is licensed CC BY-SA 4.0. Original questions, answers and source passages are downloaded separately and are not committed in these reports.",
        "- Low-overlap membership uses frozen baseline term analysis, and evidence labels remain outside ranking/indexing/packing.",
        "- Once scored, this selection becomes regression data. No outcome-driven retuning is claimed as the same heldout test.",
        "- A structural evidence-attainability diagnostic is retained in the export report; affected cases are never dropped.",
        "- Product source revisions, host/package details, input/output hashes and all failed/started intent records are preserved in the corresponding raw report and checkpoint."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args(argv)
    plan, binding = frozen_inputs()
    checkpoint = json.loads(args.checkpoint.read_bytes())
    run_id = checkpoint["run_id"]
    require(re.fullmatch(r"[A-Za-z0-9-]+", run_id) is not None, "Invalid run identity")
    result_dir = ROOT / "benchmarks/results" / ("round2-" + run_id)
    assessment = {"schema_version": 1, "status": "failed", "assessed_at": now(), "run_id": run_id,
                  "source_commit": checkpoint["source_commit"]}
    try:
        manifest = json.loads(round2_data.MANIFEST.read_bytes())
        required = stages(plan, binding)
        require(list(checkpoint["stages"]) == required, "Missing, extra or reordered registered engines")
        require(checkpoint["plan_sha256"] == sha(ROOT / "benchmarks/round2_plan.json")
                and checkpoint["binding_sha256"] == sha(ROOT / "benchmarks/round2_candidate.json")
                and checkpoint["cohort_manifest_sha256"] == sha(round2_data.MANIFEST), "Checkpoint input identity differs")
        preparation = {"verified_hotpot_download_and_conversion", "reference_tokenizers", "ai_memory_binary_and_embedding",
                       "claude_mem_source_and_bun", "billion_context_source"}
        if binding["optional_semantic"]:
            preparation.add("book_semantic_model")
        require(set(checkpoint["preparation"]) == preparation
                and all(row["status"] == "completed" for row in checkpoint["preparation"].values()), "Incomplete preparation")
        reports = {stage: verify_stage(ROOT, result_dir, stage, checkpoint, plan, binding, manifest) for stage in required}
        corpus_hash = reports["export"]["frozen_corpus"]["documents_sha256"]
        require(all(report["frozen_corpus"]["documents_sha256"] == corpus_hash for report in reports.values()), "Supplied pages differ between engines")
        paired = comparison(reports["baseline-native"], reports["candidate-native"])
        assessment.update(status="complete-verified-snapshot", dataset_sha256=manifest["dataset_sha256"],
            selected_ids_sha256=manifest["selected_ids_sha256"], host=checkpoint["host"],
            required_evidence=manifest["required_evidence"], supplied_paragraphs=manifest["selected_context_paragraphs"],
            distinct_queries=manifest["expected_queries"], stages=required,
            native_query_configuration_pairs=manifest["expected_queries"] * len(native_configurations(plan)),
            native_changes=paired,
            native_complete_gains=sum(len(row["complete_question_gains"]) for row in paired),
            native_complete_losses=sum(len(row["complete_question_losses"]) for row in paired),
            source_free_reports={stage: checkpoint["stages"][stage]["outputs"] for stage in required},
            interpretation="Complete measurement integrity only. Quality gains/losses and native interface boundaries remain explicit; no whole-product speed multiplier.")
        if binding["optional_semantic"]:
            assessment["optional_semantic_native_changes"] = comparison(reports["candidate-native"], reports["candidate-semantic-native"])
        text = markdown(assessment, reports)
        (result_dir / "report.md").write_text(text, encoding="utf-8")
        atomic(result_dir / "assessment.json", assessment)
        print(json.dumps({"status": assessment["status"], "stages": len(required),
                          "native_query_configuration_pairs": assessment["native_query_configuration_pairs"]}))
        return 0
    except Exception as error:
        assessment.update(error_type=type(error).__name__, reason=str(error))
        atomic(result_dir / "assessment.json", assessment)
        (result_dir / "report.md").write_text("# Round-two assessment failed\n\nThe registered matrix did not pass strict integrity/completeness checks. Preserve the checkpoint and original stage reports; do not publish partial results as a completed comparison.\n", encoding="utf-8")
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
