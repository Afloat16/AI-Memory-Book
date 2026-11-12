"""Derive the final native-budget assessment from every frozen stage summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks/native-completion-manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/RESULTS-native-token-budget.md")
    parser.add_argument("--json-output", type=Path, default=ROOT / "benchmarks/reports/native-completion-assessment.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    base = (args.manifest.parent / manifest["cwd"]).resolve()
    rows, hashes, source_hashes = [], {}, set()
    for stage in manifest["stages"]:
        name = next(p for p in stage["outputs"] if p.endswith(".summary.json"))
        path = base / name
        raw = path.read_bytes()
        report = json.loads(raw)
        if report.get("validation", {}).get("passed") is not True:
            raise ValueError(f"Incomplete or failing stage: {stage['id']}")
        hashes[name] = hashlib.sha256(raw).hexdigest()
        old, new = report["engines"]
        if not all(e["source_unchanged"] and e["evaluator_unchanged"] for e in (old, new)):
            raise ValueError("A measured source changed")
        source_hashes.add(new["source_sha256_before"])
        expected = int(stage["argv"][stage["argv"].index("--expected-queries") + 1])
        paired = []
        for config, change in zip(new["configurations"], report["paired_changes"], strict=True):
            keys = ("budget_chars", "tokenizer", "budget_tokens")
            before = next(c for c in old["configurations"] if c["policy"] == "native_excerpt_pack"
                          and all(c[k] == config[k] for k in keys))
            if config["metrics"]["queries"] != expected:
                raise ValueError("Unexpected cohort size")
            if any(change[key] for key in ("annotation_losses", "complete_question_losses", "baseline_block_losses")):
                raise ValueError("Native preservation failed")
            paired.append({**{k: config[k] for k in keys},
                "queries": expected, "answerable_queries": config["metrics"]["answerable_queries"],
                "baseline_complete_evidence_rate": before["metrics"]["complete_evidence_rate"],
                "candidate_complete_evidence_rate": config["metrics"]["complete_evidence_rate"],
                "baseline_evidence_recall": before["metrics"]["evidence_recall"],
                "candidate_evidence_recall": config["metrics"]["evidence_recall"],
                "baseline_p95_ms": before["latency"]["p95_ms"],
                "candidate_p95_ms": config["latency"]["p95_ms"],
                **{k: len(change[k]) for k in ("annotation_gains", "annotation_losses",
                    "complete_question_gains", "complete_question_losses", "baseline_block_losses")}})
        rows.append({"stage": stage["id"], "summary": name, "dataset": report["dataset"],
                     "baseline_source_sha256": old["source_sha256_before"],
                     "candidate_source_sha256": new["source_sha256_before"], "configurations": paired})
    if len(source_hashes) != 1:
        raise ValueError("Candidate runtime differs across frozen stages")
    assessment = {"schema_version": 1, "manifest": str(args.manifest.relative_to(ROOT)),
                  "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                  "stage_summaries_sha256": hashes, "stages": rows,
                  "validation": {"passed": True, "stages": len(rows),
                      "query_configuration_pairs": sum(c["queries"] for row in rows for c in row["configurations"]),
                      "annotation_losses": 0, "complete_question_losses": 0, "baseline_block_losses": 0}}
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(assessment, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Completed native token-budget validation", "",
             "The interrupted eight-stage protocol is complete. All stages passed the fixed budget, source-coordinate, tokenizer, repeated-context, unchanged-source and old-native-block preservation gates.", "",
             "These are original-evidence retrieval measurements. Complete evidence is the fraction of answerable questions for which every annotated evidence span is present; it is not generated-answer accuracy.", "",
             "## 512-token results", "",
             "Both native policies use the same character cap, scope, five-page limit and `cl100k_base` tokenizer. The baseline returns its native cited excerpts and then uses exact whole-block first-fit packing. The candidate enforces the token limit during native assembly and can add intact original source units.", "",
             "| Cohort | Questions / answerable | Character cap | Old native complete evidence | New native complete evidence | Additional complete questions | Old / new p95 ms |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        for c in row["configurations"]:
            if c["tokenizer"] == "cl100k_base" and c["budget_tokens"] == 512:
                lines.append(f"| {row['stage']} | {c['queries']} / {c['answerable_queries']} | {c['budget_chars']} | {c['baseline_complete_evidence_rate']:.2%} | {c['candidate_complete_evidence_rate']:.2%} | {c['complete_question_gains']} | {c['baseline_p95_ms']:.3f} / {c['candidate_p95_ms']:.3f} |")
    lines += ["", "No annotated evidence, complete questions or already-fitting baseline native blocks were lost in any measured configuration. This is a measured invariant for these cohorts; it is not a claim of perfect recall on arbitrary future archives.", "",
              "## Reproducible scope and costs", "",
              "Each stage evaluates character caps 2,000/8,000, token caps 512/1,024/2,048, both `cl100k_base` and `o200k_base`, and three uncached repetitions in sequential workers. Historical full-page packing at its distinct 100,000-character retrieval cap is retained separately in each full report. It must not be relabeled as the baseline's native excerpt policy.", "",
              "Exact token assembly performs extra work to recover intact evidence. Its p95 can exceed plain excerpt packing. The separate development optimization compares the previous native-token implementation with the stable-prefix implementation; do not mix that speed comparison with the older no-native-token baseline in the table above. All timing samples are host-specific and use warm OS/SQLite caches.", "",
              "Model summaries and embedding queries are absent from this lexical path. Ingestion is measured separately in every worker. These runs do not measure actual generated answers or native observer/compression/answer costs of competitor projects.", "",
              "## Data boundaries", "",
              "The synthetic seeds and LoCoMo cohort are regression data; new synthetic seeds share templates. The authored 36-case diagnostic is also previously observed. The 128 HotpotQA distractor questions were selected and hash-frozen before candidate scoring and add an independently authored external multi-hop diagnostic. This scoped sample is not broad cross-domain or full-Wikipedia validation. It becomes regression data after this run.", "",
              "## Complete evidence files", "",
              "Every linked summary has an adjacent `.json.gz` with all per-query source/context hashes, evidence gains/losses, category metrics and a Markdown table. The originally interrupted manifest, checkpoint and completed development result remain preserved.", ""]
    for row in rows:
        relative = Path(row["summary"]).relative_to("benchmarks")
        lines.append(f"- [{row['stage']}]({relative.as_posix()})")
    lines += ["", "The aggregate checks and input hashes are in [native-completion-assessment.json](reports/native-completion-assessment.json). The [completion manifest](native-completion-manifest.json) and [performance plan](experiments/native-token-performance-plan.json) specify the frozen sources and commands.", ""]
    args.output.write_text("\n".join(lines))
    print(json.dumps(assessment["validation"]))


if __name__ == "__main__":
    main()
