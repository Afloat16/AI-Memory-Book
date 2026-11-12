"""Audit published native workflow results and derive costs without model calls.

The fictional authored cohort permits publishing its actual native observations
and answers. Missing costs remain unknown and failed operations stay visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.answer_eval import answer_scores, digest
from benchmarks.full_workflow_eval import inputs, operation_succeeded
from benchmarks.run import percentile


def timing(values):
    known = [value for value in values if value is not None]
    if any(type(value) not in (int, float) or value < 0 for value in known):
        raise ValueError("Invalid measured duration")
    return {"attempts": len(values), "measured": len(known),
            "known_subtotal_ms": sum(known),
            "total_if_complete_ms": sum(known) if len(known) == len(values) else None,
            "mean_ms": statistics.fmean(known) if known else None,
            "p50_ms": percentile(known, .50) if known else None,
            "p95_ms": percentile(known, .95) if known else None,
            "p99_ms": percentile(known, .99) if known else None}


def assess(report):
    plan, sessions, cases = inputs()
    if report.get("status") not in {"completed", "completed_with_failures"}:
        raise ValueError("Workflow has not finished all registered attempts")
    identity = report["identity"]
    if (identity["plan"] != plan or identity["sessions_sha256"] != digest(sessions)
            or report["identity_sha256"] != digest({k: v for k, v in identity.items()
                                                     if k != "source_provenance"})):
        raise ValueError("Published workflow does not match its frozen identity")
    answers = report["answers"]
    cases_by_id = {case["id"]: case for case in cases}
    expected = {(engine, case["id"]) for engine in ("book", "ai-memory") for case in cases}
    keys = [(row["engine"], row["id"]) for row in answers]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("Incomplete or duplicate registered answer matrix")
    for row in answers:
        case = cases_by_id[row["id"]]
        if row["answerable"] != case["answerable"]:
            raise ValueError("Answerability differs from the frozen references")
        if row["status"] == "ok":
            if row["served_model"] != plan["model"]["served_alias"]:
                raise ValueError("Scored response used a different model")
            if row["scores"] != answer_scores(row["answer"], case):
                raise ValueError("Published answer scores do not reproduce")
        elif (row["scores"]["normalized_exact_match"] != 0
              or row["scores"]["lexical_token_f1"] not in (0, None)
              or row["scores"]["abstained"]):
            raise ValueError("A failed answer received quality credit")
    stages, contexts = report["stage_statuses"], report["contexts"]
    if len(report["capture_results"]) != len(sessions):
        raise ValueError("Native capture attempts are missing")
    if len([key for key in stages if key.startswith("book-ingest:")]) != len(sessions):
        raise ValueError("Book import attempts are missing")
    engine_rows = []
    for engine in ("book", "ai-memory"):
        selected = [row for row in answers if row["engine"] == engine]
        supported = [row for row in selected if row["answerable"]]
        unsupported = [row for row in selected if not row["answerable"]]
        selected_contexts = [contexts.get("context:" + engine + ":" + case["id"], {}) for case in cases]
        if any(c.get("context_tokens", 0) > 512 or len(c.get("context", "")) > 8000
               for c in selected_contexts):
            raise ValueError("Published context exceeds the registered cap")
        mean = lambda values: statistics.fmean(values) if values else None
        engine_rows.append({"engine": engine, "answer_attempts": len(selected),
            "successful_answers": sum(row["status"] == "ok" for row in selected),
            "truncated_answers": sum(row.get("finish_reason") == "length" for row in selected),
            "answerable_queries": len(supported), "unsupported_queries": len(unsupported),
            "normalized_exact_match": mean([row["scores"]["normalized_exact_match"] for row in supported]),
            "lexical_token_f1": mean([row["scores"]["lexical_token_f1"] for row in supported]),
            "exact_abstention_rate": mean([float(row["scores"]["abstained"]) for row in unsupported]),
            "retrieval_latency": timing([c.get("retrieval_ms") for c in selected_contexts]),
            "packing_latency": timing([c.get("packing_ms") for c in selected_contexts]),
            "answer_latency": timing([row.get("endpoint_roundtrip_ms") for row in selected]),
            "mean_context_tokens": mean([c["context_tokens"] for c in selected_contexts if "context_tokens" in c]),
            "mean_returned_tokens": mean([c["native_returned_tokens"] for c in selected_contexts if "native_returned_tokens" in c])})
    reported = {row["engine"]: row for row in report["summary"]["engines"]}
    for row in engine_rows:
        original = reported[row["engine"]]
        for key, value in row.items():
            if key not in {"retrieval_latency", "packing_latency", "answer_latency"} and original.get(key) != value:
                raise ValueError(f"Workflow summary differs from actual records: {row['engine']}/{key}")
        row.update({key: original[key] for key in ("phases", "answer_usage", "summary_usage",
                    "summary_model_calls", "retrieval_calls", "followup_read_calls")})
    capture_ok = sum(bool(result and result.get("ok") and result.get("remaining_events") == 0)
                     for result in report["capture_results"].values())
    consolidation_ok = sum(operation_succeeded(key, {**stages[key], "result": result})
                           for key, result in report["consolidation_outputs"].items())
    model_runs = report.get("model_server_runs") or []
    if not model_runs or any(run.get("ownership") != "spawned_by_this_runner"
                             or run.get("model_sha256") != plan["model"]["gguf_sha256"]
                             for run in model_runs):
        raise ValueError("Missing proof of the real pinned local model process")
    return {"schema_version": 1, "status": report["status"],
            "actual_answer_attempts": len(answers), "native_capture_sessions": len(sessions),
            "successful_native_capture_sessions": capture_ok,
            "native_consolidation_attempts": len(report["consolidation_outputs"]),
            "successful_native_consolidations": consolidation_ok,
            "native_model_attempts": report["summary"]["native_model_attempts"],
            "native_model_completed": report["summary"]["native_model_completed"],
            "engines": engine_rows, "storage": report["storage"], "model_server_runs": model_runs,
            "identity_sha256": report["identity_sha256"],
            "unmeasured": report["summary"]["unmeasured"],
            "interpretation": report["summary"]["interpretation"]}


def markdown(result):
    def number(value):
        return "unknown" if value is None else f"{value:,.2f}"
    def pct(value):
        return "n/a" if value is None else f"{value:.2%}"
    lines = ["# Actual capture, consolidation, retrieval and answer workflow", "",
             f"Status: **{result['status']}**. The complete registered matrix contains "
             f"**{result['actual_answer_attempts']} actual answer attempts**, using all 36 previously authored questions "
             "(30 answerable and 6 unsupported) across six fictional domains and 42 source sessions.", "",
             "Book's default lexical path is compared with the official ai-memory **v3.4.5** binary, "
             "native hooks, explicitly enabled model consolidation, local embeddings, MCP queries and full reads. "
             "Both answer with the same pinned Qwen2.5-0.5B Q4_K_M model, a 512-token cl100k_base evidence cap, "
             "8000-character cap and maximum 128 answer tokens. Native consolidation uses the separately "
             "preregistered 16,384-token model context. No synthetic replacement summaries are supplied.", "",
             "Current ai-memory also supports a zero-LLM default path. This experiment measures the "
             "explicitly configured v3.4.5 generative workflow, not a required charge for all ai-memory deployments.", "",
             "## Answer quality and failures", "",
             "| Engine | EM | Lexical F1 | Exact abstention | Successful answers | Truncated answers |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in result["engines"]:
        lines.append(f"| {row['engine']} | {pct(row['normalized_exact_match'])} | {pct(row['lexical_token_f1'])} | {pct(row['exact_abstention_rate'])} | {row['successful_answers']} / {row['answer_attempts']} | {row['truncated_answers']} |")
    lines += ["", "EM/F1 use all 30 answerable questions; exact abstention uses all 6 unsupported questions. "
              "Failures retain zero credit. These lexical metrics are not a human or model semantic judge.", "",
              "## Phase costs", "", "These are sequential phase observations with different native transport boundaries. "
              "Book uses its Python API; ai-memory uses authenticated HTTP/MCP and full reads. "
              "The table does not imply a same-boundary search-kernel speed ratio.", "",
              "| Engine | Phase | Successful operations | Known phase ms | Complete total ms |",
              "|---|---|---:|---:|---:|"]
    for row in result["engines"]:
        for phase, data in row["phases"].items():
            lines.append(f"| {row['engine']} | {phase} | {data['successful']} / {data['operations']} | {number(data['known_subtotal_ms'])} | {number(data['total_if_complete_ms'])} |")
    lines += ["", "| Engine | Retrieval p50 / p95 / p99 ms | Answer p50 / p95 / p99 ms | Mean context tokens | Mean native returned tokens | Search / follow-up reads |",
              "|---|---:|---:|---:|---:|---:|"]
    for row in result["engines"]:
        times = lambda key: " / ".join(number(row[key][field]) for field in ("p50_ms", "p95_ms", "p99_ms"))
        lines.append(f"| {row['engine']} | {times('retrieval_latency')} | {times('answer_latency')} | {number(row['mean_context_tokens'])} | {number(row['mean_returned_tokens'])} | {row['retrieval_calls']} / {row['followup_read_calls']} |")
    lines += ["", "## Actual model usage", "", "Local server usage counts are not dollar charges or energy estimates. "
              "Unknown usage is preserved; a known subtotal must not be presented as a complete total.", "",
              "| Engine | Phase | Model calls | Prompt tokens | Output tokens | Total tokens |",
              "|---|---|---:|---:|---:|---:|"]
    for row in result["engines"]:
        for phase, key, calls in (("consolidation", "summary_usage", row["summary_model_calls"]),
                                  ("answers", "answer_usage", row["answer_attempts"])):
            values = [number(row[key][field]["total_if_complete"]) for field in ("prompt_tokens", "completion_tokens", "total_tokens")]
            lines.append(f"| {row['engine']} | {phase} | {calls} | {' | '.join(values)} |")
    lines += ["", f"Native capture accepted **{result['successful_native_capture_sessions']} / {result['native_capture_sessions']}** sessions. "
              f"Native consolidation produced **{result['successful_native_consolidations']} / {result['native_consolidation_attempts']}** validated pages. "
              f"The native model proxy recorded **{result['native_model_attempts']}** attempts and **{result['native_model_completed']}** completed HTTP responses.", "",
              "## Storage and reproducibility", "", "```json", json.dumps(result["storage"], indent=2), "```", "",
              "The native directory includes its logs and wiki Git history; the shared embedding-model symlink is excluded. "
              "Book storage counts its closed SQLite files. These are declared storage boundaries, not interchangeable engine-only footprints.", "",
              "The [raw public report](results/full-workflow-transfer36.json) retains actual fictional contexts, native summary outputs, "
              "capture acknowledgments, per-attempt answers and scores, phase status, model usage and process hashes. "
              "The [assessment](results/full-workflow-transfer36-assessment.json) is derived by `python scripts/summarize_workflow.py` "
              "without another model request. The [frozen plan](experiments/full-workflow-plan.json) defines the exact replay and read policy.", "",
              "This is a previously observed six-domain diagnostic with one small quantized CPU model. Interactive host hooks, "
              "filesystem watcher overhead, adaptive agent reads, provider billing and electricity are unmeasured. "
              "claude-mem observer and billion-context compression workflows are outside this experiment. "
              "Larger-model answer quality, production concurrency and broad generalization remain unestablished.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "benchmarks/results/full-workflow-transfer36.json")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    result = assess(json.loads(raw))
    result["report_sha256"] = hashlib.sha256(raw).hexdigest()
    for path, text in ((ROOT / "benchmarks/results/full-workflow-transfer36-assessment.json", json.dumps(result, indent=2) + "\n"),
                       (ROOT / "benchmarks/RESULTS-full-workflow.md", markdown(result))):
        partial = path.with_suffix(path.suffix + ".partial")
        partial.write_text(text)
        partial.replace(path)
    print(json.dumps({"status": result["status"], "actual_answer_attempts": result["actual_answer_attempts"]}))


if __name__ == "__main__":
    main()
