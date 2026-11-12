"""Verify and summarize the two preregistered real local-model answer cohorts.

Only exported hashes, scores and timings are read. This command never makes a
model request and never substitutes retrieval completeness for answer quality.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.answer_eval import digest
from benchmarks.run import percentile
from benchmarks.token_compare import latency_summary

COHORTS = ("locomo", "hotpotqa")
LABELS = {
    "baseline_native_excerpt_pack": "Prior default + excerpt pack",
    "candidate_native_token_budget": "Native token budget",
    "candidate_semantic_native_token_budget": "Semantic + native token budget",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values):
    return statistics.fmean(values) if values else None


def verify_cohort(root, cohort):
    prefix = root / "benchmarks/results" / ("local-answer-final-" + cohort)
    raw_path = Path(str(prefix) + ".json.gz")
    summary_path = Path(str(prefix) + ".summary.json")
    raw = gzip.decompress(raw_path.read_bytes())
    report, compact = json.loads(raw), json.loads(summary_path.read_bytes())
    if compact.get("full_report_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError(f"Public raw/summary hash mismatch: {cohort}")
    if any(report.get(key) != value for key, value in compact.items()
           if key not in {"full_report_sha256", "truncated_responses"}):
        raise ValueError(f"Public compact report differs from raw report: {cohort}")
    if report.get("status") != "completed-real-local-model" or report.get("cohort") != cohort:
        raise ValueError(f"Missing completed real-model report: {cohort}")
    for field, filename in (("plan", "local-answer-plan.json"),
                            ("execution_plan", "local-answer-execution.json")):
        path = root / "benchmarks/experiments" / filename
        if report[field] != json.loads(path.read_bytes()) or report[field + "_sha256"] != sha(path):
            raise ValueError(f"Frozen answer plan changed: {cohort}")
    engines = report["plan"]["engines"]
    if engines != list(LABELS):
        raise ValueError("Unexpected registered engine ordering")
    cases = report["query_identities"]
    case_by_id = {case["id"]: case for case in cases}
    if len(cases) != 128 or len(case_by_id) != 128:
        raise ValueError(f"Incomplete or duplicate answer cohort: {cohort}")
    attempts = report["attempts"]
    expected = {(engine, qid, 0) for engine in engines for qid in case_by_id}
    actual = [(row["engine"], row["id"], row["repetition"]) for row in attempts]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError(f"Incomplete or duplicate actual answer matrix: {cohort}")
    if compact["truncated_responses"] != sum(row.get("finish_reason") == "length" for row in attempts):
        raise ValueError(f"Truncation accounting differs: {cohort}")
    proof = report["owned_server_proof"]
    if (proof.get("ownership") != "spawned_by_registered_local_answer_runner"
            or proof.get("identity_sha256") != digest(proof["identity"])
            or proof["identity"]["prepared_sha256"] != report["prepared_sha256"]
            or not proof["runs"] or proof["runs"][-1].get("status") != "completed"
            or not proof["runs"][-1].get("runtime_unchanged")
            or proof["runs"][-1].get("trace_sha256") != report["raw_trace_sha256"]):
        raise ValueError(f"Missing bound process proof: {cohort}")
    model = report["plan"]["model"]
    server = report["plan"]["server"]
    if report["artifact_verification"] != {
        "model_sha256": model["sha256"], "server_archive_sha256": server["sha256"]
    }:
        raise ValueError(f"Wrong model/server artifact: {cohort}")
    rows = []
    summaries = {row["engine"]: row for row in report["summary"]["engines"]}
    preparations = {row["engine"]: row for row in report["preparation"]}
    if set(summaries) != set(engines) or set(preparations) != set(engines):
        raise ValueError(f"Missing engine summary/preparation: {cohort}")
    for engine in engines:
        selected = [row for row in attempts if row["engine"] == engine]
        supported = [row for row in selected if case_by_id[row["id"]]["answerable"]]
        unsupported = [row for row in selected if not case_by_id[row["id"]]["answerable"]]
        if any("answer" in row or row["context_tokens"] > 512 for row in selected):
            raise ValueError(f"Public answer text or token overflow: {cohort}")
        if any(row["status"] == "ok" and row.get("served_model") != model["served_alias"] for row in selected):
            raise ValueError(f"Successful response used a different served model: {cohort}")
        for row in selected:
            if row["status"] not in {"ok", "error", "interrupted"}:
                raise ValueError("Unknown attempt status")
            scores = row["scores"]
            if row["status"] != "ok" and (scores["normalized_exact_match"] != 0 or scores["abstained"]
                                             or scores["lexical_token_f1"] not in (None, 0)):
                raise ValueError("Failed attempt received quality credit")
        computed = {
            "attempts": len(selected), "successful_responses": sum(row["status"] == "ok" for row in selected),
            "errors": sum(row["status"] != "ok" for row in selected),
            "interrupted_unknown_outcomes": sum(row["status"] == "interrupted" for row in selected),
            "answerable_attempts": len(supported), "unsupported_attempts": len(unsupported),
            "answerable_normalized_exact_match": mean([r["scores"]["normalized_exact_match"] for r in supported]),
            "answerable_lexical_token_f1": mean([r["scores"]["lexical_token_f1"] for r in supported]),
            "unsupported_exact_abstention_rate": mean([float(r["scores"]["abstained"]) for r in unsupported]),
            "endpoint_roundtrip": latency_summary([r["endpoint_roundtrip_ms"] for r in selected if r["endpoint_roundtrip_ms"] is not None]),
        }
        if any(summaries[engine].get(key) != value for key, value in computed.items()):
            raise ValueError(f"Scores/counts/timings do not reproduce from attempts: {cohort}/{engine}")
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            known = [r["provider_usage"][key] for r in selected if r["provider_usage"][key] is not None]
            expected_usage = {"reported_calls": len(known), "known_subtotal": sum(known),
                              "total_if_complete": sum(known) if len(known) == len(selected) else None}
            if summaries[engine]["provider_usage"][key] != expected_usage:
                raise ValueError(f"Usage accounting mismatch: {cohort}/{engine}")
        preparation = preparations[engine]
        prepared_rows = {row["id"]: row for row in preparation["rows"]}
        if (len(prepared_rows) != 128 or set(prepared_rows) != set(case_by_id)
                or preparation["source_sha256"] != preparation["source_sha256_after"]
                or any(prepared_rows[r["id"]]["context_sha256"] != r["context_sha256"] for r in selected)):
            raise ValueError(f"Prepared contexts/source identities differ: {cohort}/{engine}")
        rows.append({"cohort": cohort, **summaries[engine],
                     "source_sha256": preparation["source_sha256"],
                     "mean_context_tokens": mean([r["context_tokens"] for r in selected]),
                     "truncated_responses": sum(r.get("finish_reason") == "length" for r in selected),
                     "endpoint_roundtrip_p99_ms": percentile([r["endpoint_roundtrip_ms"] for r in selected if r["endpoint_roundtrip_ms"] is not None], .99),
                     "recall_latency": latency_summary([r["recall_ms"] for r in preparation["rows"]]),
                     "external_packing_latency": latency_summary([r["packing_ms"] for r in preparation["rows"]])})
    pairs = []
    for left, right in zip(engines, engines[1:]):
        a = {r["id"]: r for r in attempts if r["engine"] == left}
        b = {r["id"]: r for r in attempts if r["engine"] == right}
        for metric in ("normalized_exact_match", "lexical_token_f1"):
            ids = [c["id"] for c in cases if c["answerable"]]
            changes = [{"id": qid, "before": a[qid]["scores"][metric], "after": b[qid]["scores"][metric]}
                       for qid in ids if a[qid]["scores"][metric] != b[qid]["scores"][metric]]
            pairs.append({"cohort": cohort, "baseline": left, "candidate": right, "metric": metric,
                          "answerable_queries": len(ids),
                          "gains": [r for r in changes if r["after"] > r["before"]],
                          "losses": [r for r in changes if r["after"] < r["before"]]})
    return {"cohort": cohort, "rows": rows, "paired_changes": pairs,
            "comparability": report["summary"]["model_comparability"],
            "server_runs": proof["runs"], "model": model, "server": server,
            "evaluator_sources": report["evaluator_sources"],
            "provenance": {"raw_file": str(raw_path.relative_to(root)), "raw_file_sha256": sha(raw_path),
                           "raw_content_sha256": hashlib.sha256(raw).hexdigest(),
                           "summary_file": str(summary_path.relative_to(root)), "summary_file_sha256": sha(summary_path)}}


def assess(root):
    cohorts = [verify_cohort(root, name) for name in COHORTS]
    for key in ("model", "server", "evaluator_sources"):
        if any(cohort[key] != cohorts[0][key] for cohort in cohorts[1:]):
            raise ValueError(f"Cohorts used different {key}")
    for index, engine in enumerate(LABELS):
        if cohorts[0]["rows"][index]["source_sha256"] != cohorts[1]["rows"][index]["source_sha256"]:
            raise ValueError(f"Engine sources differ across cohorts: {engine}")
    return {"schema_version": 1, "status": "complete-registered-local-answer-matrix",
            "actual_attempts": sum(row["attempts"] for c in cohorts for row in c["rows"]),
            "cohorts": cohorts,
            "interpretation": "Real outputs from one pinned 0.5B quantized CPU model. Fixed lexical exact/F1 metrics; no semantic judge or official LoCoMo scoring. This experiment measures supplied-context answers and separate preparation costs, not complete native competitor workflows or general semantic memory."}


def pct(value):
    return "n/a" if value is None else f"{value:.2%}"


def num(value):
    return "n/a" if value is None else f"{value:.3f}"


def markdown(result):
    lines = ["# Real local-model answers: completed registered evaluation", "",
             f"**{result['actual_attempts']} actual answer attempts** across 128 LoCoMo and 128 HotpotQA questions, each with three retrieval modes.", "",
             "The model is the pinned Qwen2.5-0.5B-Instruct Q4_K_M artifact served by llama.cpp b12110 on CPU. "
             "All modes use the same fixed prompt, 4096-token model context, 512-token cl100k_base evidence cap, "
             "8000-character cap, top-five limit, temperature 0 and maximum 128 output tokens. "
             "Engine order rotates per question. Prompt reuse is disabled. There is one generation per question/mode; "
             "these results do not establish performance for larger or hosted models.", "",
             "## Answer quality", "",
             "EM is normalized exact match; F1 is the fixed lexical token-overlap metric. Both use answerable questions only. "
             "Unsupported questions have a separate exact `INSUFFICIENT_EVIDENCE` abstention rate. "
             "Failed/interrupted attempts retain zero quality credit and remain in denominators. "
             "These are actual generated-answer scores, not evidence completeness or a semantic judge.", "",
             "| Cohort | Retrieval mode | Answerable / unsupported | EM | F1 | Exact abstention | Errors / truncated |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for cohort in result["cohorts"]:
        for row in cohort["rows"]:
            lines.append(f"| {row['cohort']} | {LABELS[row['engine']]} | {row['answerable_attempts']} / {row['unsupported_attempts']} | {pct(row['answerable_normalized_exact_match'])} | {pct(row['answerable_lexical_token_f1'])} | {pct(row['unsupported_exact_abstention_rate'])} | {row['errors']} / {row['truncated_responses']} |")
    lines.extend(["", "## Generation and context costs", "",
                  "Endpoint latency includes the sequential loopback HTTP request, actual inference and decoded response. "
                  "It excludes ingestion and retrieval preparation. Prompt/output counts are reported by the verified local model server; "
                  "they are not a provider bill. The evidence cap uses cl100k_base, whereas these usage counts use the model's tokenizer.", "",
                  "| Cohort | Mode | Mean evidence tokens | Answer p50 / p95 / p99 ms | Reported prompt tokens | Reported output tokens | Reported total tokens |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    for cohort in result["cohorts"]:
        for row in cohort["rows"]:
            usage = row["provider_usage"]
            amount = lambda key: str(usage[key]["total_if_complete"]) if usage[key]["total_if_complete"] is not None else f"{usage[key]['known_subtotal']} known; total unknown"
            times = row["endpoint_roundtrip"]
            lines.append(f"| {row['cohort']} | {LABELS[row['engine']]} | {row['mean_context_tokens']:.1f} | {num(times['p50_ms'])} / {num(times['p95_ms'])} / {num(row['endpoint_roundtrip_p99_ms'])} | {amount('prompt_tokens')} | {amount('completion_tokens')} | {amount('total_tokens')} |")
    lines.extend(["", "## Once-per-cohort preparation", "",
                  "Each engine independently imports the same histories. Semantic mode explicitly builds its local index. "
                  "All configured summaries are extractive and make zero generative summary calls. "
                  "Retrieval and packing totals cover one preparation call per question. They are separate stage observations, "
                  "not a complete workflow stopwatch; source exports retain original session and page coordinates.", "",
                  "| Cohort | Mode | Import ms | Semantic preparation ms | Recall ms total | External packing ms total | Closed database bytes |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    for cohort in result["cohorts"]:
        for row in cohort["rows"]:
            storage = row.get("database_storage_closed") or {}
            lines.append(f"| {row['cohort']} | {LABELS[row['engine']]} | {num(row['ingestion_ms_once'])} | {num(row['semantic_index_ms_once'])} | {num(row['recall_ms_once'])} | {num(row['packing_ms_once'])} | {storage.get('total_bytes', 'unknown')} |")
    lines.extend(["", "## Paired gains and losses", "",
                  "The first comparison isolates the saved native-budget continuation relative to the prior default. "
                  "The second adds semantic candidate ranking while retaining native packing. Every changed question ID "
                  "and its before/after score is preserved in the machine-readable assessment.", "",
                  "| Cohort | Comparison | Metric | Improved questions | Regressed questions |",
                  "|---|---|---|---:|---:|"])
    for cohort in result["cohorts"]:
        for pair in cohort["paired_changes"]:
            lines.append(f"| {cohort['cohort']} | {LABELS[pair['baseline']]} → {LABELS[pair['candidate']]} | {pair['metric']} | {len(pair['gains'])} | {len(pair['losses'])} |")
    lines.extend(["", "## Boundaries and reproducibility", "",
                  "- LoCoMo is previously observed retrieval regression data. HotpotQA is the separately frozen scoped-distractor multi-hop diagnostic; after scoring it also becomes regression data. Model pretraining overlap is unknown.",
                  "- Lexical EM/F1 can penalize correct paraphrases and reward partial word overlap. No human or model semantic judge is claimed. One small quantized model and 256 bounded questions cannot establish general answer quality or broad transfer.",
                  "- The owned-process proof verifies model/archive/extracted-runtime hashes and launch arguments, and binds them to the completed trace and prepared inputs. Identical model identity does not guarantee deterministic generation.",
                  "- The original licensed passages, prompts and answer text remain in ignored private work artifacts. Public reports retain request/response/context/answer hashes, per-attempt scores, failure state, usage and timing.",
                  "- Native competitor observation, consolidation and adaptive follow-up are outside this experiment. The separate full-workflow diagnostic uses different model context settings and must not be pooled with these scores.", ""])
    for cohort in result["cohorts"]:
        lines.append(f"- {cohort['cohort']}: [full exported metrics]({cohort['provenance']['raw_file'].removeprefix('benchmarks/')}), [summary]({cohort['provenance']['summary_file'].removeprefix('benchmarks/')}); reported model comparability: `{cohort['comparability']['status']}`.")
    lines.extend(["", "[Frozen model and cohort plan](experiments/local-answer-plan.json) · [Execution plan](experiments/local-answer-execution.json) · [Evaluation guide](../docs/answer-evaluation.md) · [Machine-readable assessment](results/local-answer-final-assessment.json)", "",
                  "Reproduce the verification and tables without making model calls:", "", "```bash",
                  "python scripts/summarize_local_answers.py", "```", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    result = assess(root)
    for path, text in ((root / "benchmarks/results/local-answer-final-assessment.json", json.dumps(result, indent=2) + "\n"),
                       (root / "benchmarks/RESULTS-local-answers.md", markdown(result))):
        temporary = path.with_name(path.name + ".partial")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"status": result["status"], "actual_attempts": result["actual_attempts"]}))


if __name__ == "__main__":
    main()
