"""Derive the final native-budget assessment from every frozen stage summary."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


SOURCE_IDENTITIES = (
    ("5abc85eef00097555366f8524fc81f8b5711ad7a",
     "88f5f749be55dd4f1094d236340bec645edb6b9306fd45c720dbebac91767e57"),
    ("407cda1c5f1dac0e67dfe527d3c23febdad5e818",
     "63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625"),
)


def relative_path(path):
    path = path.resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def argument(stage, name, *, multiple=False):
    values = stage["argv"]
    index = values.index(name) + 1
    if not multiple:
        return values[index]
    end = next((i for i in range(index, len(values)) if values[i].startswith("--")), len(values))
    return values[index:end]


def load_checkpoints(paths):
    records = []
    for path in paths:
        raw = path.read_bytes()
        records.append((relative_path(path), json.loads(raw), hashlib.sha256(raw).hexdigest()))
    return records


def checked_report(stage, base, checkpoints):
    """Require raw/summary/checkpoint agreement and all preregistered axes.

    A summary with a copied PASS field is not a completed cohort. Historical
    host paths are provenance only; no earlier workspace is accessed.
    """
    output_hashes = {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
                     for name in stage["outputs"]}
    summary_name = next(name for name in stage["outputs"] if name.endswith(".summary.json"))
    full_name = next(name for name in stage["outputs"] if name.endswith(".json.gz"))
    summary = json.loads((base / summary_name).read_text())
    raw = gzip.decompress((base / full_name).read_bytes())
    full = json.loads(raw)
    if len(full["engines"]) != 2:
        raise ValueError("A native comparison requires exactly two engines")
    derived = copy.deepcopy(full)
    for engine in derived["engines"]:
        for config in engine["configurations"]:
            config.pop("query_results")
    derived["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    if summary != derived:
        raise ValueError(f"Full report and summary disagree: {stage['id']}")
    if (summary.get("validation", {}).get("passed") is not True
            or summary["validation"].get("failures")
            or summary["validation"].get("baseline_block_preservation_required") is not True):
        raise ValueError(f"Incomplete or failing stage: {stage['id']}")

    provenance = []
    for name, checkpoint, checkpoint_hash in checkpoints:
        record = checkpoint["stages"].get(stage["id"], {})
        if record.get("status") != "completed" or record.get("outputs") != output_hashes:
            continue
        identity_hash = hashlib.sha256(json.dumps(checkpoint["identity"], sort_keys=True,
                                                  separators=(",", ":")).encode()).hexdigest()
        if record.get("identity_sha256") != identity_hash:
            raise ValueError(f"Checkpoint identity mismatch: {name}")
        # Interpreter paths differ across hosts; every evaluator argument stays fixed.
        if record["argv"][1:] != stage["argv"][1:]:
            raise ValueError(f"Checkpoint command differs from registration: {stage['id']}")
        provenance.append({"checkpoint": name, "checkpoint_sha256": checkpoint_hash,
                           "identity_sha256": identity_hash,
                           "started_at": record["started_at"], "finished_at": record["finished_at"],
                           "attempt": record["attempt"]})
    if not provenance:
        raise ValueError(f"No completed checkpoint authenticates all outputs: {stage['id']}")

    expected = int(argument(stage, "--expected-queries"))
    expected_dataset = argument(stage, "--expected-dataset-sha256")
    if summary["dataset"]["sha256"] != expected_dataset or summary["dataset"]["queries"] != expected:
        raise ValueError(f"Cohort differs from registration: {stage['id']}")
    chars = list(map(int, argument(stage, "--budget-chars", multiple=True)))
    tokens = list(map(int, argument(stage, "--token-budgets", multiple=True)))
    encodings = argument(stage, "--tokenizers", multiple=True)
    repeats = int(argument(stage, "--repeats"))
    expected_config = {"budget_chars": chars, "token_budgets": tokens, "tokenizers": encodings,
                       "limit": int(argument(stage, "--limit")), "repeats": repeats,
                       "semantic": False, "coverage": False}
    native_axes = set(itertools.product(chars, encodings, tokens))
    expected_ids = None
    for index, engine in enumerate(full["engines"]):
        commit, source_hash = SOURCE_IDENTITIES[index]
        source = engine["source_provenance"]
        if (engine["source_sha256_before"] != source_hash
                or engine["source_sha256_after"] != source_hash
                or not engine["source_unchanged"] or not engine["evaluator_unchanged"]
                or source["git_commit"] != commit or source["source_dirty"]
                or not source["commit_identifies_source"]):
            raise ValueError(f"Frozen source identity differs: {stage['id']}")
        if engine["configuration"] != expected_config or engine["tokenizer_version"] != "0.12.0":
            raise ValueError(f"Engine configuration differs: {stage['id']}")
        if engine["dataset"] != full["dataset"]:
            raise ValueError(f"Engine dataset differs: {stage['id']}")
        required = ({("native_excerpt_pack", *axis) for axis in native_axes}
                    | {("historical_whole_page_pack", 100000, enc, tok)
                       for enc, tok in itertools.product(encodings, tokens)}) if index == 0 else {
                           ("native_token_budget", *axis) for axis in native_axes}
        actual = [(c["policy"], c["budget_chars"], c["tokenizer"], c["budget_tokens"])
                  for c in engine["configurations"]]
        if set(actual) != required or len(actual) != len(required):
            raise ValueError(f"Missing or duplicate registered configuration: {stage['id']}")
        for config in engine["configurations"]:
            ids = [row["id"] for row in config["query_results"]]
            if expected_ids is None:
                expected_ids = ids
            if ids != expected_ids or len(ids) != expected or len(set(ids)) != expected:
                raise ValueError(f"Incomplete or inconsistent query records: {stage['id']}")
            if (config["metrics"]["queries"] != expected
                    or config["latency"]["samples"] != expected * repeats):
                raise ValueError(f"Missing registered queries or timing repetitions: {stage['id']}")
            if any(config[key] for key in ("token_budget_violations", "source_span_errors",
                                          "token_metadata_errors", "repeat_context_mismatches")):
                raise ValueError(f"Recorded invariant violation: {stage['id']}")
            if any(config["metrics"][key] for key in ("budget_violations", "context_size_mismatches")):
                raise ValueError(f"Recorded character-budget violation: {stage['id']}")
    changes = [(c["budget_chars"], c["tokenizer"], c["budget_tokens"]) for c in full["paired_changes"]]
    if set(changes) != native_axes or len(changes) != len(native_axes):
        raise ValueError(f"Incomplete paired changes: {stage['id']}")
    return summary, output_hashes, provenance


def detailed_tables(rows):
    lines = ["", "## Public and external budget curves", "",
        "These native-policy curves use the 8,000-character cap. Timing includes native recall and any separate exact packing, with three uncached repetitions. Tokens include source citations and separators but exclude enclosing MCP/HTTP metadata. Full 2,000-character curves, first/repeat-pass timings and category metrics remain in each stage report and the assessment JSON.", "",
        "| Cohort | Tokenizer / cap | Old / new evidence recall | Old / new complete evidence | Old / new mean context tokens | Old / new p50 ms | Old / new p95 ms | Old / new mean ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        if row["stage"] not in ("regression-public1015", "external-hotpot128"):
            continue
        for c in row["configurations"]:
            if c["budget_chars"] != 8000:
                continue
            old, new = c["baseline_metrics"], c["candidate_metrics"]
            old_t, new_t = c["baseline_latency"], c["candidate_latency"]
            encoding = c["tokenizer"]
            lines.append(f"| {row['stage']} | {encoding} / {c['budget_tokens']} | "
                         f"{old['evidence_recall']:.2%} / {new['evidence_recall']:.2%} | "
                         f"{old['complete_evidence_rate']:.2%} / {new['complete_evidence_rate']:.2%} | "
                         f"{old['mean_context_tokens'][encoding]:.1f} / {new['mean_context_tokens'][encoding]:.1f} | "
                         f"{old_t['p50_ms']:.3f} / {new_t['p50_ms']:.3f} | "
                         f"{old_t['p95_ms']:.3f} / {new_t['p95_ms']:.3f} | "
                         f"{old_t['mean_ms']:.3f} / {new_t['mean_ms']:.3f} |")
    lines += ["", "## Historical 512-token policy", "",
        "The earlier 66.72% to 66.26% cl100k_base result used full source pages and shared whole-block packing. This continuation adds an explicit native token-assembly API; it does not change or retroactively repair that historical full-page policy. Its results remain separate below at the registered 100,000-character retrieval boundary. Do not compare its latency as though it were the native excerpt route.", "",
        "| Public historical full-page policy | Token cap | Evidence recall | Complete evidence | Mean context tokens |",
        "|---|---:|---:|---:|---:|"]
    for row in rows:
        if row["stage"] == "regression-public1015":
            for c in row["historical_whole_page_configurations"]:
                m = c["metrics"]
                lines.append(f"| {c['tokenizer']} | {c['budget_tokens']} | {m['evidence_recall']:.2%} | "
                             f"{m['complete_evidence_rate']:.2%} | {m['mean_context_tokens'][c['tokenizer']]:.1f} |")
    lines += ["", "## Import and stored archive costs", "",
        "| Cohort | Source sessions / source UTF-8 bytes | Old / new import ms | Old / new database bytes | Pages |",
        "|---|---:|---:|---:|---:|"]
    for row in rows:
        old, new, data = row["baseline_engine_stats"], row["candidate_engine_stats"], row["dataset"]
        lines.append(f"| {row['stage']} | {data['sessions']} / {data['source_utf8_bytes']:,} | "
                     f"{row['baseline_ingestion_ms']:.1f} / {row['candidate_ingestion_ms']:.1f} | "
                     f"{old['database_bytes']:,} / {new['database_bytes']:,} | {new['pages']:,} |")
    lines += ["",
        "Database size is the engine's reported on-disk snapshot after ingestion, not peak RAM or total deployment size. Each import is one measured pass and can vary with filesystem and host scheduling. Peak memory, CPU energy and provider monetary bills were not measured. The preserved tokenizer-startup report measures a separate boundary; query timing here pre-initializes both encodings and is not tokenizer-cold latency.", "",
        "## Recovery provenance and reproduction", "",
        "The baseline source is 5abc85eef00097555366f8524fc81f8b5711ad7a; the native-token candidate is 407cda1c5f1dac0e67dfe527d3c23febdad5e818. Semantic recall and clause coverage are disabled. Every raw report, summary and Markdown file must match a completed checkpoint before aggregation. The three earlier completed cohorts remain unchanged. Freshly recovered jobs keep separate host/process identities and the same registered cohort, source, evaluator, budget and repetition settings. Baseline and candidate are sequential workers inside each cohort; timing samples are never pooled across jobs or earlier hosts.", "",
        "Run the original full manifest with a new checkpoint after preparing its verified data and source worktrees. Alternatively, run each unchanged stage in its own manifest/job and supply all resulting checkpoint files plus the original completed-stage checkpoints to the summarizer:", "",
        chr(96) * 3 + "bash",
        'export TIKTOKEN_CACHE_DIR="$PWD/.artifacts/tiktoken"',
        "python -m benchmarks.resume --manifest benchmarks/native-completion-manifest.json \\",
        "  --checkpoint .artifacts/native-fresh-checkpoint.json",
        "python scripts/summarize_native_completion.py \\",
        "  --checkpoints .artifacts/native-fresh-checkpoint.json",
        chr(96) * 3, ""]
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks/native-completion-manifest.json")
    parser.add_argument("--checkpoints", type=Path, nargs="+",
                        help="Completed original and continuation checkpoints; default discovers native checkpoints")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/RESULTS-native-token-budget.md")
    parser.add_argument("--json-output", type=Path, default=ROOT / "benchmarks/reports/native-completion-assessment.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    base = (args.manifest.parent / manifest["cwd"]).resolve()
    if len(manifest["stages"]) != 8 or len({stage["id"] for stage in manifest["stages"]}) != 8:
        raise ValueError("Final completion requires all eight registered cohorts, without duplicates")
    discovered = sorted(set((ROOT / "benchmarks/reports").glob("native-*-checkpoint.json"))
                        | set((ROOT / "benchmarks/reports").glob("hosted-native-*-checkpoint.json")))
    checkpoints = load_checkpoints(args.checkpoints or discovered)
    rows, hashes, source_hashes, evaluator_hashes = [], {}, set(), set()
    for stage in manifest["stages"]:
        name = next(p for p in stage["outputs"] if p.endswith(".summary.json"))
        report, output_hashes, provenance = checked_report(stage, base, checkpoints)
        hashes.update(output_hashes)
        old, new = report["engines"]
        if not all(e["source_unchanged"] and e["evaluator_unchanged"] for e in (old, new)):
            raise ValueError("A measured source changed")
        source_hashes.add(new["source_sha256_before"])
        for engine in (old, new):
            evaluator_hashes.add(json.dumps(engine["evaluator_files"], sort_keys=True))
        expected = int(stage["argv"][stage["argv"].index("--expected-queries") + 1])
        paired = []
        for config, change in zip(new["configurations"], report["paired_changes"], strict=True):
            keys = ("budget_chars", "tokenizer", "budget_tokens")
            if any(config[key] != change[key] for key in keys):
                raise ValueError("Paired changes are attached to the wrong configuration")
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
                "baseline_metrics": before["metrics"], "candidate_metrics": config["metrics"],
                "baseline_latency": before["latency"], "candidate_latency": config["latency"],
                "baseline_recall_latency": before["recall_latency"],
                "candidate_recall_latency": config["recall_latency"],
                "baseline_post_recall_packing_latency": before["post_recall_packing_latency"],
                "candidate_post_recall_packing_latency": config["post_recall_packing_latency"],
                "baseline_first_pass_latency": before["first_pass_latency"],
                "candidate_first_pass_latency": config["first_pass_latency"],
                "baseline_repeat_pass_latency": before["repeat_pass_latency"],
                "candidate_repeat_pass_latency": config["repeat_pass_latency"],
                "baseline_by_category": before["by_category"], "candidate_by_category": config["by_category"],
                **{k: len(change[k]) for k in ("annotation_gains", "annotation_losses",
                    "complete_question_gains", "complete_question_losses", "baseline_block_losses")}})
        rows.append({"stage": stage["id"], "summary": name, "dataset": report["dataset"],
                     "runtime": report["runtime"], "completion_provenance": provenance,
                     "baseline_source_sha256": old["source_sha256_before"],
                     "candidate_source_sha256": new["source_sha256_before"],
                     "baseline_ingestion_ms": old["ingestion_ms"],
                     "candidate_ingestion_ms": new["ingestion_ms"],
                     "baseline_engine_stats": old["engine_stats"],
                     "candidate_engine_stats": new["engine_stats"],
                     "historical_whole_page_configurations": [c for c in old["configurations"]
                                                               if c["policy"] == "historical_whole_page_pack"],
                     "configurations": paired})
    if len(source_hashes) != 1 or len(evaluator_hashes) != 1:
        raise ValueError("Candidate runtime or evaluator differs across frozen stages")
    assessment = {"schema_version": 2, "manifest": relative_path(args.manifest),
                  "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                  "stage_outputs_sha256": hashes, "stages": rows,
                  "source_identities": {"baseline": dict(zip(("commit", "sha256"), SOURCE_IDENTITIES[0])),
                                        "candidate": dict(zip(("commit", "sha256"), SOURCE_IDENTITIES[1]))},
                  "evaluator_files": json.loads(next(iter(evaluator_hashes))),
                  "methodology": "All raw/summary/Markdown bytes match completed checkpoints. Full reports match summaries, and the registered cohorts, axes, repetitions and sources are checked. Historical checkpoints remain unchanged. Host-specific latency samples stay per cohort and are not pooled across recovery environments.",
                  "validation": {"passed": True, "stages": len(rows),
                      "query_configuration_pairs": sum(c["queries"] for row in rows for c in row["configurations"]),
                      "annotation_losses": 0, "complete_question_losses": 0, "baseline_block_losses": 0,
                      "raw_summary_checkpoint_agreement": True, "all_registered_axes": True}}
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
    lines += detailed_tables(rows)
    args.output.write_text("\n".join(lines))
    print(json.dumps(assessment["validation"]))


if __name__ == "__main__":
    main()
