"""Validate and summarize all fixed Q1 old development reports without inference."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.round2_quality_eval import MODES, PLAN, VERSION
from benchmarks.resume import _save

SOURCE_COMMIT = "973657b8c6ab29d2462c9d88303fb0baed2faf24"
SOURCE_SHA256 = "49ee4fc04efa89e0110a066094d5d5519f65e588f0ebbcce5f96961e57b29759"
RUN_ID = "43194168722"
GROUPS = ("low_lexical_overlap_le_0.25", "multiple_required_evidence", "cross_session", "cross_chapter")


def validate_marker(record, stage):
    if (record["stage"], record["status"], record["run_id"], str(record["run_attempt"]), record["source_commit"]) != (
            stage, "completed", RUN_ID, "1", SOURCE_COMMIT):
        raise ValueError("Report is not from the fixed successful hosted run/attempt/source")


def verified_report(directory, cohort):
    prefix = Path(directory) / ("round2-quality-" + cohort["label"])
    summary_path = Path(str(prefix) + ".summary.json")
    raw_path = Path(str(prefix) + ".json.gz")
    marker_path = Path(directory).parent / "reports" / ("round2-quality-" + cohort["label"] + "-hosted.json")
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
            VERSION, SOURCE_SHA256, cohort["sha256"], cohort["queries"], cohort["queries"] * 27, 3, list(MODES), expected_configs):
        raise ValueError("Report differs from the frozen Q1 source/cohort/axis matrix")
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
        prefix = Path(directory) / ("round2-quality-" + cohort["label"])
        if not Path(str(prefix) + ".summary.json").exists():
            missing.append(cohort["label"])
            continue
        report, provenance = verified_report(directory, cohort)
        identity = report["identity"]
        common = {key: identity[key] for key in ("evaluator", "runtime_source_sha256", "evaluator_files", "model", "reference", "modes", "fusion_version", "configurations", "repeats", "seed")}
        if shared is None:
            shared = common
        elif common != shared:
            raise ValueError("Cohorts used different runtime/model/evaluator/configuration identities")
        configs = []
        for config in report["configurations"]:
            configs.append({**{key: config[key] for key in ("budget_chars", "budget_tokens", "tokenizer", "limit")},
                            "modes": [{key: value for key, value in mode.items() if key != "query_results"} for mode in config["modes"]],
                            "paired_change_counts": {name: {key: len(value) for key, value in changes.items()}
                                                     for name, changes in config["paired_changes"].items()}})
        reports.append({"cohort": cohort["label"], "dataset": report["dataset"], "provenance": provenance,
                        "environment": identity["runtime"], "preparation": report["preparation"], "configurations": configs})
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
    lines = ["# Q1 score-aware semantic fusion: old development record", "",
             f"Status: **{report['status']}**. This is a fusion-policy experiment; lexical remains the product default.", "",
             f"Frozen runtime `{report['runtime_source_sha256']}` at [{report['source_commit'][:7]}](https://github.com/Afloat16/AI-Memory-Book/commit/{report['source_commit']}); "
             f"[hosted execution](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{report['hosted_run_id']}).", "",
             "All three modes use the same source archive, MiniLM model/index, 900-character pages, top-five results, 8000-character cap and native token assembler. Caps are 512/1024/2048 cl100k_base tokens, each with three repetitions. The original RRF control is checked against the original function's AST and k=60; its surrounding runtime is shared with Q1.", "",
             "Q1 fixes lexical/semantic weights at 0.75/0.25, preserving score margins. There was no weight search or tuning on the new 256-question cohort. Existing v1 embedding indexes are reusable; only semantic result-cache identity changes.", "",
             "## Complete evidence and evidence recall", "",
             "Each cell is **complete evidence / annotation recall**. All budgets and negative results are retained.", "",
             "| Old cohort | Token cap | Lexical | Original RRF | Q1 |",
             "|---|---:|---:|---:|---:|"]
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
                  "| Old cohort | Cap | Group | Questions | Lexical | Original RRF | Q1 |",
                  "|---|---:|---|---:|---:|---:|---:|"])
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
                  "All query repetitions are retained. Timing excludes ingestion, model/index preparation, scoring and checkpoint/export I/O. The same actual query-encoding counter is included in both semantic modes. First/repeat-pass distributions are available in JSON. Each cohort has its own hosted VM; compare its paired modes, not absolute milliseconds across cohorts.", "",
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
                  "| Old cohort | Cap | Unsupported questions | Lexical nonempty | RRF nonempty | Q1 nonempty |",
                  "|---|---:|---:|---:|---:|---:|"])
    for cohort in report["cohorts"]:
        for config in cohort["configurations"]:
            data = [mode["metrics"] for mode in config["modes"]]
            lines.append(f"| {cohort['cohort']} | {config['budget_tokens']} | {data[0]['unanswerable_queries']} | " +
                         " | ".join(percent(item["unanswerable_nonempty_rate"]) for item in data) + " |")
    lines.extend(["", "Accepted reports passed source/index-address stability, source-span projection, project scope, character/token caps, token/model metadata, result-cache isolation and repeat-context checks. These are measurement checks, not evidence of universal semantic memory. Public raw and summary reports remain linked below; private source datasets and model artifacts are not part of Git publication.", "", "## Reports", ""])
    for cohort in report["cohorts"]:
        provenance = cohort["provenance"]
        lines.append(f"- {cohort['cohort']}: [full rows](../results/{provenance['full_report']}) · [summary](../results/{provenance['summary']})")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "benchmarks/results")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round2-quality-development")
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
