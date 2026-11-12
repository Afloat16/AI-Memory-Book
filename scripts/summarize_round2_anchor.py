"""Validate and summarize all fixed Q2 old development reports without inference."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.round2_anchor_eval import MODES, PLAN, VERSION
from benchmarks.resume import _save
from scripts.summarize_round2_quality import verified_report as verified_q1_report

SOURCE_COMMIT = "6286564e33f09db9863a80613771722c32ba363b"
SOURCE_SHA256 = "cce621cbe62b0e8d7a94fbdb023372e0ff2004ca390e2ffd5c01863596059b43"
RUN_ID = "43196880064"
GROUPS = ("low_lexical_overlap_le_0.25", "multiple_required_evidence", "cross_session", "cross_chapter")


def control_reproduction(current, prior):
    """Cross-run context/evidence diagnostics; never pool latency across hosts."""
    comparisons = []
    for after, before in zip(current["configurations"], prior["configurations"], strict=True):
        if after["budget_tokens"] != before["budget_tokens"]:
            raise ValueError("Control budgets differ")
        modes = []
        for current_mode, prior_mode in zip(after["modes"][:3], before["modes"], strict=True):
            if current_mode["mode"] != prior_mode["mode"]:
                raise ValueError("Control identities differ")
            old = {row["id"]: row for row in prior_mode["query_results"]}
            new = {row["id"]: row for row in current_mode["query_results"]}
            if old.keys() != new.keys():
                raise ValueError("Control query sets differ")
            modes.append({"mode": current_mode["mode"],
                          "changed_context_ids": [key for key in old if old[key]["context_sha256"] != new[key]["context_sha256"]],
                          "changed_evidence_ids": [key for key in old if old[key]["evidence_ranks"] != new[key]["evidence_ranks"]],
                          "changed_annotation_presence_ids": [key for key in old if
                              [rank is not None for rank in old[key]["evidence_ranks"]] !=
                              [rank is not None for rank in new[key]["evidence_ranks"]]],
                          "complete_question_gains": [key for key in old if new[key]["complete"] and not old[key]["complete"]],
                          "complete_question_losses": [key for key in old if old[key]["complete"] and not new[key]["complete"]]})
        comparisons.append({"budget_tokens": after["budget_tokens"], "modes": modes})
    return comparisons


def validate_marker(record, stage):
    if (record["stage"], record["status"], record["run_id"], str(record["run_attempt"]), record["source_commit"]) != (
            stage, "completed", RUN_ID, "1", SOURCE_COMMIT):
        raise ValueError("Report is not from the fixed successful hosted run/attempt/source")


def verified_report(directory, cohort):
    prefix = Path(directory) / ("round2-anchor-" + cohort["label"])
    summary_path = Path(str(prefix) + ".summary.json")
    raw_path = Path(str(prefix) + ".json.gz")
    marker_path = Path(directory).parent / "reports" / ("round2-anchor-" + cohort["label"] + "-hosted.json")
    marker = json.loads(marker_path.read_text())
    validate_marker(marker, cohort["label"])
    for path in (summary_path, raw_path):
        public_path = "benchmarks/results/" + path.name
        if marker["public_files"].get(public_path) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Public file bytes differ from the finalized hosted marker")
    summary = json.loads(summary_path.read_text())
    raw = gzip.decompress(raw_path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != summary["full_report_sha256"]:
        raise ValueError("Full report checksum differs from its summary")
    report = json.loads(raw)
    projected = json.loads(raw)
    for config in projected["configurations"]:
        for mode in config["modes"]:
            mode.pop("query_results")
    if {key: value for key, value in summary.items() if key != "full_report_sha256"} != projected:
        raise ValueError("Summary is not an exact projection of the complete report")
    plan = json.loads(PLAN.read_text())
    identity = report["identity"]
    expected_configs = [{"budget_chars": 8000, "budget_tokens": cap, "tokenizer": "cl100k_base", "limit": 5}
                        for cap in plan["parameters"]["token_budgets"]]
    if (report["evaluator"], identity["runtime_source_sha256"], report["dataset"]["sha256"], report["dataset"]["queries"],
        report["completed_samples"], identity["repeats"], identity["modes"], identity["configurations"]) != (
            VERSION, SOURCE_SHA256, cohort["sha256"], cohort["queries"], cohort["queries"] * 36, 3, list(MODES), expected_configs):
        raise ValueError("Report differs from the frozen Q2 source/cohort/axis matrix")
    if report["validation"] != {"passed": True, "failures": []}:
        raise ValueError("A failed measurement is diagnostic, not an accepted comparison")
    if report["preserved_incomplete_attempts"]:
        raise ValueError("This registered hosted run was not expected to replay an incomplete query")
    if report["source_sha256_after"] != SOURCE_SHA256 or report["evaluator_files_after"] != identity["evaluator_files"]:
        raise ValueError("Sources changed during measurement")
    if any(segment["source_provenance"]["git_commit"] != SOURCE_COMMIT or
           not segment["source_provenance"]["commit_identifies_source"] for segment in report["process_segments"]):
        raise ValueError("Measured source is not the frozen hosted source")
    for config, expected in zip(report["configurations"], expected_configs, strict=True):
        if {key: config[key] for key in expected} != expected or [mode["mode"] for mode in config["modes"]] != list(MODES):
            raise ValueError("Missing or reordered configuration/mode")
        for mode in config["modes"]:
            rows = mode["query_results"]
            if len(rows) != cohort["queries"] or len({row["id"] for row in rows}) != cohort["queries"]:
                raise ValueError("Missing or duplicate query")
            if mode["repeat_context_mismatches"] or any(mode["invariants"].values()):
                raise ValueError("A retrieval invariant failed")
            if any({item["repetition"] for item in row["measurements"]} != {0, 1, 2}
                   or len(row["measurements"]) != 3 for row in rows):
                raise ValueError("Missing or duplicate repetition")
    return report, {"full_report": raw_path.name, "summary": summary_path.name,
                    "full_report_sha256": summary["full_report_sha256"],
                    "compressed_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}


def collect(directory, allow_partial=False):
    plan = json.loads(PLAN.read_text())
    reports, missing, shared = [], [], None
    for cohort in plan["development_cohorts"]:
        prefix = Path(directory) / ("round2-anchor-" + cohort["label"])
        if not Path(str(prefix) + ".summary.json").exists():
            missing.append(cohort["label"])
            continue
        report, provenance = verified_report(directory, cohort)
        prior, prior_provenance = verified_q1_report(directory, cohort)
        reproduced = control_reproduction(report, prior)
        identity = report["identity"]
        common = {key: identity[key] for key in ("evaluator", "runtime_source_sha256", "evaluator_files", "model", "reference", "modes", "fusion_version", "configurations", "repeats", "seed")}
        if shared is None:
            shared = common
        elif common != shared:
            raise ValueError("Cohorts used different runtime/model/evaluator/configuration identities")
        configs = []
        for config in report["configurations"]:
            modes = []
            for mode in config["modes"]:
                projected = {key: value for key, value in mode.items() if key not in {"query_results", "by_group"}}
                projected["by_group"] = {group: mode["by_group"][group] for group in GROUPS if group in mode["by_group"]}
                modes.append(projected)
            configs.append({**{key: config[key] for key in ("budget_chars", "budget_tokens", "tokenizer", "limit")},
                            "modes": modes,
                            "paired_change_counts": {name: {key: len(value) for key, value in changes.items()}
                                                     for name, changes in config["paired_changes"].items()}})
        reports.append({"cohort": cohort["label"], "dataset": report["dataset"], "provenance": provenance,
                        "environment": identity["runtime"], "preparation": report["preparation"], "configurations": configs,
                        "previous_q1_run_provenance": prior_provenance, "control_reproduction": reproduced,
                        "cross_run_controls": {
                            "model_identity_equal": identity["model"] == prior["identity"]["model"],
                            "recorded_environment_equal": identity["runtime"] == prior["identity"]["runtime"],
                            "indexed_page_text_and_ids_equal": report["preparation"]["semantic_index"]["source_sha256"] == prior["preparation"]["semantic_index"]["source_sha256"],
                            "interpretation": "Within-run comparisons share one actual index. Cross-run semantic changes are retained; a hardware/numerical cause is not established. Full source snapshots also include lifecycle timestamps, so they are not used as cross-run text fingerprints."}})
    if missing and not allow_partial:
        raise ValueError("Do not claim completion before all four old development cohorts are present: " + ", ".join(missing))
    return {"schema_version": 1, "status": "partial" if missing else "completed",
            "source_commit": SOURCE_COMMIT, "runtime_source_sha256": SOURCE_SHA256,
            "hosted_run_id": RUN_ID, "run_attempt": 1, "missing_cohorts": missing,
            "identity": shared, "cohorts": reports,
            "default_semantic": False,
            "limits": "Old development/regression data only; no blind questions or new-domain claims. No answer generation. Latency comparisons are paired within each cohort VM; do not pool host timing distributions."}


def percent(value):
    return "—" if value is None else f"{value:.2%}"


def markdown(report):
    lines = ["# Q2 lexical-anchor semantic fusion: old development record", "",
             f"Status: **{report['status']}**. This is a fusion-policy experiment; lexical remains the product default.", "",
             f"Frozen runtime `{report['runtime_source_sha256']}` at [{report['source_commit'][:7]}](https://github.com/Afloat16/AI-Memory-Book/commit/{report['source_commit']}); "
             f"[hosted execution](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{report['hosted_run_id']}).", "",
             "All four modes use the same source archive, MiniLM model/index, 900-character pages, top-five results, 8000-character cap and native token assembler. Caps are 512/1024/2048 cl100k_base tokens, each with three repetitions. Original RRF(k=60) and Q1 score-fusion controls are checked against their original Git function bodies and constants; all four modes share the Q2 surrounding runtime.", "",
             "Q2 promotes only the first page from the existing lexical order, preserving every other page in original RRF relative order and retaining every page original RRF score. It adds no model call or score threshold. Frozen Q1 remains a .75/.25 control. The new 256-question cohort was not inspected or used for tuning. Existing v1 indexes are reusable; Q2 result-cache identity is version 3.", "",
             "## Complete evidence and evidence recall", "",
             "Each cell is **complete evidence / annotation recall**. All budgets and negative results are retained.", "",
             "| Old cohort | Token cap | Lexical | Original RRF | Q1 | Q2 |",
             "|---|---:|---:|---:|---:|---:|"]
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            values = [percent(mode["metrics"]["complete_evidence_rate"]) + " / " + percent(mode["metrics"]["evidence_recall"]) for mode in config["modes"]]
            lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | " + " | ".join(values) + " |")
    lines.extend(["", "## Every paired gain and loss", "",
                  "Counts below are paired questions/annotations; full reports retain their IDs even when aggregate scores tie.", "",
                  "| Old cohort | Cap | Comparison | Complete gains | Complete losses | Annotation gains | Annotation losses |",
                  "|---|---:|---|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            for name, counts in config["paired_change_counts"].items():
                lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {name} | {counts['complete_question_gains']} | {counts['complete_question_losses']} | {counts['annotation_gains']} | {counts['annotation_losses']} |")
    lines.extend(["", "## Low overlap and evidence combination", "",
                  "These overlapping evaluator groups are fixed diagnostics, not a new independent test. Cell values are complete-evidence rates; group membership is identical across modes.", "",
                  "| Old cohort | Cap | Group | Questions | Lexical | Original RRF | Q1 | Q2 |",
                  "|---|---:|---|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            for group in GROUPS:
                data = [mode["by_group"].get(group) for mode in config["modes"]]
                if not any(data):
                    continue
                if not all(data) or len({item["queries"] for item in data}) != 1:
                    raise ValueError("Diagnostic groups differ between paired modes")
                lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {group} | {data[0]['queries']} | " +
                             " | ".join(percent(item["complete_evidence_rate"]) for item in data) + " |")
    lines.extend(["", "## Query time and returned tokens", "",
                  "All query repetitions are retained. Timing excludes ingestion, model/index preparation, scoring and checkpoint/export I/O. The same actual query-encoding counter is included in all three semantic modes. First/repeat-pass distributions are available in JSON. Each cohort has its own hosted VM; compare its paired modes, not absolute milliseconds across cohorts.", "",
                  "Payload tokens count stable compact JSON for the entire response, including repeated context/result text and metadata, excluding latency/cache-hit diagnostics. They are distinct from the hard context-token budget.", "",
                  "| Old cohort | Cap | Mode | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms | Query encodes |",
                  "|---|---:|---|---:|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            for mode in config["modes"]:
                metrics, latency = mode["metrics"], mode["latency"]
                lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {mode['mode']} | {metrics['mean_context_tokens']['cl100k_base']:.1f} | {metrics['mean_returned_payload_tokens']['cl100k_base']:.1f} | {latency['p50_ms']:.3f} | {latency['p95_ms']:.3f} | {latency['p99_ms']:.3f} | {mode['query_encoding_operations']} |")
    lines.extend(["", "## Shared preparation costs", "",
                  "Fresh indexing here is experimental preparation, not an upgrade requirement for existing compatible indexes. Ordinary lexical operation requires no model or embedding index.", "",
                  "| Old cohort | Ingest ms | Model load ms | Index build ms | Windows | Vector bytes |",
                  "|---|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        preparation = cohort["preparation"]
        index = preparation["semantic_index"]
        lines.append(f"| {cohort['cohort']} | {preparation['ingestion_ms']:.1f} | {index['model_load_ms']:.1f} | {index['build_ms']:.1f} | {index['windows']} | {index['vector_bytes']} |")
    lines.extend(["", "## Unsupported questions and validity", "",
                  "A nonempty context on an unsupported question is a retrieval diagnostic. This experiment does not generate answers, so this is not an answer error rate.", "",
                  "| Old cohort | Cap | Unsupported questions | Lexical nonempty | RRF nonempty | Q1 nonempty | Q2 nonempty |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            data = [mode["metrics"] for mode in config["modes"]]
            lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {data[0]['unanswerable_queries']} | " +
                         " | ".join(percent(item["unanswerable_nonempty_rate"]) for item in data) + " |")
    lines.extend(["", "Accepted reports passed source/index-address stability, source-span projection, project scope, character/token caps, token/model metadata, result-cache isolation and repeat-context checks. These are measurement checks, not evidence of universal semantic memory.", "",
                  "## Repeated controls across experiments", "",
                  "This compares each current lexical/RRF/Q1 context and evidence outcome with the completed Q1 experiment. Differences are retained as diagnostics; timings are never pooled across runs or hosts. The JSON separately records verified model identity, recorded runtime environment and indexed page-text/ID fingerprint agreement. A hardware or numerical cause for any changes is not established by these records. The quality conclusions above use the four modes paired within the current run.", "",
                  "| Old cohort | Cap | Control | Changed contexts | Changed evidence ranks | Changed annotation presence | Complete gains | Complete losses |",
                  "|---|---:|---|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["control_reproduction"]:
            for mode in config["modes"]:
                lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {mode['mode']} | {len(mode['changed_context_ids'])} | {len(mode['changed_evidence_ids'])} | "
                             f"{len(mode['changed_annotation_presence_ids'])} | {len(mode['complete_question_gains'])} | {len(mode['complete_question_losses'])} |")
    lines.extend(["", "Public raw and summary reports remain linked below; private source datasets and model artifacts are not part of Git publication.", "", "## Reports", ""])
    for cohort in report["cohorts"]:
        provenance = cohort["provenance"]
        lines.append(f"- {cohort['cohort']}: [full rows](../results/{provenance['full_report']}) · [summary](../results/{provenance['summary']})")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "benchmarks/results")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round2-anchor-development")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    report = collect(args.input_dir, args.allow_partial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _save(Path(str(args.output) + ".json"), report)
    markdown_path = Path(str(args.output) + ".md")
    temporary = markdown_path.with_name(markdown_path.name + ".partial")
    temporary.write_text(markdown(report))
    temporary.replace(markdown_path)
    print(json.dumps({"status": report["status"], "completed_cohorts": len(report["cohorts"]), "missing": report["missing_cohorts"]}))


if __name__ == "__main__":
    main()
