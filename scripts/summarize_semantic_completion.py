"""Reproduce the cross-cohort semantic assessment from committed raw reports.

No model inference or retrieval occurs here. A missing/failed cohort prevents
a final assessment; --allow-partial labels an explicitly interim checkpoint.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("low_lexical_overlap_le_0.25", "cross_chapter", "cross_session",
          "category:multi_section", "category:low_overlap_paraphrase")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percent(value):
    return "n/a" if value is None else f"{100 * value:.2f}%"


def number(value):
    return "n/a" if value is None else f"{value:.3f}"


def load_reports(root, allow_partial=False):
    plan = json.loads((root / "benchmarks/semantic-final-plan.json").read_bytes())
    reports, missing = [], []
    for cohort in plan["cohorts"]:
        prefix = root / "benchmarks/results" / ("semantic-final-" + cohort["label"])
        raw_path, summary_path = Path(str(prefix) + ".json.gz"), Path(str(prefix) + ".summary.json")
        if not raw_path.is_file() or not summary_path.is_file():
            missing.append(cohort["label"])
            continue
        raw = gzip.decompress(raw_path.read_bytes())
        report, summary = json.loads(raw), json.loads(summary_path.read_bytes())
        if summary.get("full_report_sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError(f"Raw/summary integrity mismatch: {cohort['label']}")
        if report["validation"]["passed"] is not True:
            raise ValueError(f"Measurement validation failed: {cohort['label']}")
        if report["dataset"]["sha256"] != cohort["sha256"] or report["dataset"]["queries"] != cohort["queries"]:
            raise ValueError(f"Frozen cohort changed: {cohort['label']}")
        expected_configs = [{"budget_chars": plan["parameters"]["budget_chars"], "budget_tokens": tokens,
                             "tokenizer": tokenizer, "limit": plan["parameters"]["limit"]}
                            for tokenizer in plan["parameters"]["tokenizers"]
                            for tokens in plan["parameters"]["token_budgets"]]
        if report["identity"]["configurations"] != expected_configs or report["identity"]["repeats"] != plan["parameters"]["repeats"]:
            raise ValueError(f"Registered configuration changed: {cohort['label']}")
        expected_samples = cohort["queries"] * len(expected_configs) * 2 * plan["parameters"]["repeats"]
        if report["completed_samples"] != expected_samples:
            raise ValueError(f"Incomplete sample matrix: {cohort['label']}")
        reports.append({"cohort": cohort, "report": report,
                        "raw_file": str(raw_path.relative_to(root)), "raw_file_sha256": file_hash(raw_path),
                        "raw_content_sha256": hashlib.sha256(raw).hexdigest(),
                        "summary_file": str(summary_path.relative_to(root)), "summary_file_sha256": file_hash(summary_path)})
    if missing and not allow_partial:
        raise ValueError("Missing frozen semantic cohorts: " + ", ".join(missing))
    if not reports:
        raise ValueError("No completed semantic cohorts to summarize")
    identities = [item["report"]["identity"] for item in reports]
    for key in ("runtime_source_sha256", "evaluator_files", "model", "configurations", "runtime", "repeats"):
        if any(identity[key] != identities[0][key] for identity in identities[1:]):
            raise ValueError(f"Incomparable cohort identity: {key}")
    return plan, reports, missing


def assess(root, allow_partial=False):
    plan, reports, missing = load_reports(root, allow_partial)
    rows, groups, costs, provenance = [], [], [], []
    for item in reports:
        label, report = item["cohort"]["label"], item["report"]
        provenance.append({key: value for key, value in item.items() if key != "report"})
        for config in report["configurations"]:
            old, new = config["modes"]
            if [old["mode"], new["mode"]] != ["lexical_native_token_budget", "semantic_native_token_budget"]:
                raise ValueError("Unexpected paired-mode ordering")
            a, b = old["metrics"], new["metrics"]
            changes = config["paired_changes"]
            if a["answerable_queries"] != b["answerable_queries"]:
                raise ValueError("Paired evidence denominators differ")
            rows.append({"cohort": label, "tokenizer": config["tokenizer"], "budget_tokens": config["budget_tokens"],
                         "queries": a["queries"], "answerable_queries": a["answerable_queries"],
                         "lexical_complete": a["complete_evidence_rate"], "semantic_complete": b["complete_evidence_rate"],
                         "complete_delta_pp": 100 * (b["complete_evidence_rate"] - a["complete_evidence_rate"]),
                         "lexical_recall": a["evidence_recall"], "semantic_recall": b["evidence_recall"],
                         "lexical_tokens": a["mean_context_tokens"][config["tokenizer"]],
                         "semantic_tokens": b["mean_context_tokens"][config["tokenizer"]],
                         "lexical_latency": old["latency"], "semantic_latency": new["latency"],
                         "annotation_gains": len(changes["annotation_gains"]), "annotation_losses": len(changes["annotation_losses"]),
                         "complete_gains": len(changes["complete_question_gains"]), "complete_losses": len(changes["complete_question_losses"]),
                         "complete_gain_ids": changes["complete_question_gains"], "complete_loss_ids": changes["complete_question_losses"]})
            for group in GROUPS:
                left, right = old["by_group"].get(group), new["by_group"].get(group)
                if left is None and right is None:
                    continue
                if left is None or right is None or left["answerable_queries"] != right["answerable_queries"]:
                    raise ValueError("Paired diagnostic groups differ")
                groups.append({"cohort": label, "group": group, "budget_tokens": config["budget_tokens"],
                               "answerable_queries": left["answerable_queries"],
                               "lexical_complete": left["complete_evidence_rate"],
                               "semantic_complete": right["complete_evidence_rate"],
                               "lexical_recall": left["evidence_recall"], "semantic_recall": right["evidence_recall"]})
        preparation = report["preparation"]
        index = preparation["semantic_index"]
        costs.append({"cohort": label, "ingestion_ms": preparation["ingestion_ms"],
                      "model_load_ms": index["model_load_ms"], "index_build_ms": index["build_ms"],
                      "pages": index["pages"], "windows": index["windows"], "vector_bytes": index["vector_bytes"],
                      "logical_database_bytes": preparation["engine_stats"]["database_bytes"],
                      "process_segments": len(report["process_segments"]),
                      "preserved_incomplete_attempts": len(report["preserved_incomplete_attempts"]),
                      "preparation_attempts": report["preparation_attempts"]})
    return {"schema_version": 1, "status": "partial" if missing else "complete-frozen-matrix",
            "plan_sha256": file_hash(root / "benchmarks/semantic-final-plan.json"),
            "runtime_source_sha256": reports[0]["report"]["identity"]["runtime_source_sha256"],
            "model": reports[0]["report"]["identity"]["model"],
            "completed_cohorts": len(reports), "missing_cohorts": missing,
            "quality": rows, "diagnostic_groups": groups, "preparation_costs": costs,
            "provenance": provenance, "methodology": plan["methodology"]}


def markdown(assessment):
    lines = ["# Local semantic retrieval: completed evidence comparison", "",
             f"Status: **{assessment['status']}**. Completed cohorts: {assessment['completed_cohorts']}/4.", ""]
    if assessment["missing_cohorts"]:
        lines.extend(["This is an interim checkpoint. Missing cohorts: " + ", ".join(assessment["missing_cohorts"]) + ".", ""])
    lines.extend(["The optional semantic route and lexical route use the **same measured runtime**, archive, "
                  "8000-character context cap, native token assembly and top-five page limit. "
                  "The local model and rank-fusion policy were declared before scoring. Each configuration "
                  "has three uncached repetitions; the mode order rotates by question and repetition.", "",
                  "These are **returned-source evidence scores**. They do not measure generated answers or "
                  "a complete competitor memory workflow. Every loss remains in the raw reports.", "",
                  "## Complete evidence and evidence recall", "",
                  "Complete evidence is the share of answerable questions for which all required source annotations reached the budgeted context. "
                  "Evidence recall uses the count of required annotations. Unsupported questions are excluded from both quality denominators and remain in latency/token statistics.", "",
                  "| Cohort | Token cap | Answerable | Lexical complete | Semantic complete | Change (pp) | Lexical recall | Semantic recall | Complete gains / losses |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in assessment["quality"]:
        lines.append(f"| {row['cohort']} | {row['budget_tokens']} | {row['answerable_queries']} | {percent(row['lexical_complete'])} | {percent(row['semantic_complete'])} | {row['complete_delta_pp']:+.2f} | {percent(row['lexical_recall'])} | {percent(row['semantic_recall'])} | {row['complete_gains']} / {row['complete_losses']} |")
    lines.extend(["", "## Declared low-overlap and cross-chapter diagnostics", "",
                  "Low overlap means at most 25% of the question's unique normalized lexical terms occur in the required evidence text. "
                  "It is an evaluator-only grouping, not a learned semantic relevance label. Cross-chapter labels require evidence "
                  "from at least two actual indexed chapter IDs; within-session `multi_section` cases are reported separately. "
                  "Groups overlap and their rows must not be added together. The JSON/raw reports include every dataset category.", "",
                  "| Cohort | Group | Token cap | Answerable | Lexical complete | Semantic complete | Lexical recall | Semantic recall |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"])
    for row in assessment["diagnostic_groups"]:
        lines.append(f"| {row['cohort']} | {row['group']} | {row['budget_tokens']} | {row['answerable_queries']} | {percent(row['lexical_complete'])} | {percent(row['semantic_complete'])} | {percent(row['lexical_recall'])} | {percent(row['semantic_recall'])} |")
    lines.extend(["", "## Query cost and context size", "",
                  "Times are milliseconds per uncached recall. They exclude model/index preparation, scoring and checkpoint writes. "
                  "First-pass timings follow explicit model loading/indexing and are not OS/disk-cold measurements. "
                  "The raw reports retain every query's repetition timings and any resume segments.", "",
                  "| Cohort | Token cap | Lexical mean tokens | Semantic mean tokens | Lexical p50 / p95 ms | Semantic p50 / p95 ms |",
                  "|---|---:|---:|---:|---:|---:|"])
    for row in assessment["quality"]:
        a, b = row["lexical_latency"], row["semantic_latency"]
        lines.append(f"| {row['cohort']} | {row['budget_tokens']} | {row['lexical_tokens']:.1f} | {row['semantic_tokens']:.1f} | {a['p50_ms']:.3f} / {a['p95_ms']:.3f} | {b['p50_ms']:.3f} / {b['p95_ms']:.3f} |")
    lines.extend(["", "## One-time corpus preparation", "",
                  "The two modes share the canonical archive for the paired experiment. The semantic index is derived from original pages only. "
                  "Model loading is separate from index construction. Vector bytes exclude SQLite overhead; database bytes are logical SQLite pages, not peak disk writes. "
                  "The fixed model artifacts total 127,535,388 bytes, excluding optional Python dependencies.", "",
                  "| Cohort | Ingestion ms | Model load ms | Index build ms | Pages / windows | Vector bytes | Logical DB bytes |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for row in assessment["preparation_costs"]:
        lines.append(f"| {row['cohort']} | {number(row['ingestion_ms'])} | {number(row['model_load_ms'])} | {number(row['index_build_ms'])} | {row['pages']} / {row['windows']} | {row['vector_bytes']} | {row['logical_database_bytes']} |")
    lines.extend(["", "## Interpretation and reproducibility", "",
                  "- Synthetic61 is development evidence with shared templates. The six-domain authored36 and LoCoMo1015 cohorts are known regression data.",
                  "- Hotpot128 was frozen separately before scoring. It is externally authored encyclopedia multi-hop QA in a scoped distractor setting; it is not full-Wikipedia retrieval or a representative conversation-memory population. Once scored, these IDs become regression data.",
                  "- The sentence model's pretraining overlap with the public datasets is unknown. These bounded cohorts do not establish universal semantic memory or cross-domain completion.",
                  "- Semantic ranking can displace useful lexical evidence and can return a nearest page for an unsupported question. It remains explicitly opt-in; all contexts retain original source coordinates.",
                  "- Measurement validation covers exact token/character caps, entire original-page slice projection, source references, project scope, model metadata, source stability and deterministic repeated contexts. It is not a minimum quality guarantee.",
                  "- Book's configured extractive summaries make zero model calls. Model inference for embedding has real CPU/index costs; no electricity, provider-bill or full-workflow cost advantage is inferred.", "",
                  f"Measured runtime SHA-256: `{assessment['runtime_source_sha256']}`.", "",
                  "The [frozen plan](semantic-final-plan.json), [execution manifest](semantic-final-manifest.json), "
                  "[machine-readable assessment](results/semantic-final-assessment.json) and raw reports preserve full identities and per-question gains/losses:", ""])
    for item in assessment["provenance"]:
        label = item["cohort"]["label"]
        lines.append(f"- {label}: [readable report](results/semantic-final-{label}.md), [summary](results/semantic-final-{label}.summary.json), [full metrics](results/semantic-final-{label}.json.gz).")
    lines.extend(["", "Rebuild the assessment without making model calls:", "", "```bash",
                  "python scripts/summarize_semantic_completion.py", "```", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    result = assess(args.root.resolve(), args.allow_partial)
    for target, content in ((args.root / "benchmarks/results/semantic-final-assessment.json",
                             json.dumps(result, ensure_ascii=False, indent=2) + "\n"),
                            (args.root / "benchmarks/RESULTS-semantic-retrieval.md", markdown(result))):
        temporary = target.with_name(target.name + ".partial")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
    print(json.dumps({"status": result["status"], "cohorts": result["completed_cohorts"],
                      "missing": result["missing_cohorts"]}))


if __name__ == "__main__":
    main()
