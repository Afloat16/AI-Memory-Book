"""Render the v0.3.2 overview from completed, saved measurements only.

Requires matplotlib. No network access, retrieval, inference or benchmark
execution. Refuse to render before the fixed comparison is complete-verified,
with its assessment and all ten completed summaries matching checkpoint hashes.
The separate formal summary is pinned byte-for-byte and must pass every
automatic gate without a resource waiver. This presentation check does not
replace the original strict raw-result audits.

The component panel uses adapter_roundtrip_latency and common whole-page
packing at 1,024 cl100k_base tokens. Additional page-read costs remain separate.
SVG proof metadata contains only aggregate values, identities and artifact links;
no questions, answers, passages, query IDs or per-query results are copied.

    python scripts/plot_round4_overview.py --png /tmp/round4-overview.png

For byte-identical SVG regeneration, use the same matplotlib/font versions.
SVG timestamps are omitted and element identifiers use a fixed salt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = "43363060062-1"
FORMAL_RUN = "43361086255-1"
FORMAL_SHA = "c7b5a8e9283e7c5d73b9c39cae6d4f2a308098e523d2df70f9f472438a15c4e8"
BINDING_SHA = "84dbe28c068a3067f9706c6439d42301eaddfef95c44ae2633398346c66a8c79"
MANIFEST_SHA = "b0485b3a089c9b04fc4453fd9f129364e123ce1b9f25b593edf4f6ee6df4a20b"
DATASET_SHA = "fb3cd70ea58fafa5bd9cef0f04dba7399aaafba76f5f92605eee9e516f115e1b"
RESULT_DIRECTORY = "benchmarks/results/round4-comparison-" + RUN
NATIVE = ("baseline-native", "candidate-native", "candidate-semantic-native")
COMPONENTS = ("baseline-component", "candidate-component", "candidate-semantic-component",
              "claude-mem-fts", "ai-memory-hybrid", "billion-context")
STAGES = ("export", *NATIVE, *COMPONENTS)
ENGINES = (
    ("candidate-component", "Book · lexical", "#2563eb"),
    ("candidate-semantic-component", "Book · Q2", "#7954b8"),
    ("claude-mem-fts", "claude-mem · FTS", "#8896a8"),
    ("ai-memory-hybrid", "ai-memory · hybrid", "#8896a8"),
    ("billion-context", "billion-context · kernel", "#087f77"),
)
FORMAL_CONFIGS = (
    ("native-char4000", "Native\n4,000 chars"),
    ("mcp-char4000", "MCP\n4,000 chars"),
    ("native-token512", "Native\n512 tokens"),
    ("native-token1024", "Native\n1,024 tokens"),
    ("native-token2048", "Native\n2,048 tokens"),
    ("mcp-token1024", "MCP\n1,024 tokens"),
)
REPOSITORY = "https://github.com/Afloat16/AI-Memory-Book"
COMPARISON_URL = (REPOSITORY + "/tree/validation/round4-comparison-" + RUN
                  + "/" + RESULT_DIRECTORY)
FORMAL_URL = (REPOSITORY + "/tree/validation/v032-round4-performance-" + FORMAL_RUN
              + "/benchmarks/reports/round4-performance-" + FORMAL_RUN)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def number(value, description, *, maximum=None, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value),
            description + " must be a finite number")
    require(minimum is None or value >= minimum, description + " is below its range")
    require(maximum is None or value <= maximum, description + " exceeds its range")
    return float(value)


def one(items, predicate, description):
    matched = [item for item in items if predicate(item)]
    require(len(matched) == 1, "Require exactly one " + description)
    return matched[0]


def extract(results, checkpoint_path, formal_path):
    results = Path(results)
    checkpoint, checkpoint_sha = read_json(checkpoint_path)
    require(checkpoint.get("run_id") == RUN and checkpoint.get("status") == "complete-verified"
            and checkpoint.get("assessment_exit_code") == 0,
            "The authoritative comparison must be complete-verified before plotting")
    require(checkpoint["binding_sha256"] == BINDING_SHA
            and checkpoint["cohort_manifest_sha256"] == MANIFEST_SHA,
            "Comparison binding or selected cohort differs")
    require(checkpoint["result_directory"] == RESULT_DIRECTORY
            and results.name == Path(RESULT_DIRECTORY).name,
            "Checkpoint result directory does not match the summaries")
    require(tuple(checkpoint["stages"]) == STAGES, "Missing, extra or reordered comparison stages")

    assessment_path = results / "assessment.json"
    assessment, assessment_sha = read_json(assessment_path)
    require(checkpoint["assessment_outputs"].get(RESULT_DIRECTORY + "/assessment.json") == assessment_sha,
            "Assessment hash does not match the completed checkpoint")
    require(assessment["run_id"] == RUN and assessment["status"] == "complete-verified"
            and assessment["validation"]["passed"] is True and not assessment["validation"]["failures"]
            and assessment["binding_sha256"] == BINDING_SHA
            and assessment["cohort_manifest_sha256"] == MANIFEST_SHA
            and assessment["dataset_sha256"] == DATASET_SHA and assessment["required_evidence"] == 635
            and assessment["source_commit"] == checkpoint["source_commit"]
            and assessment["host"]["id"] == checkpoint["host"]["id"]
            and tuple(assessment["verified_stages"]) == STAGES
            and tuple(assessment["expected_stages"]) == STAGES
            and assessment["native_calls"] == assessment["component_search_calls"] == 4608
            and assessment["quality_candidate_included"] is False,
            "The completed assessment does not verify the registered full matrix")
    equivalence = assessment["default_payload_equivalence"]
    require(equivalence["passed"] is True and equivalence["native_pairs"] == 1536
            and equivalence["component_pairs"] == 768
            and not equivalence["native_differences"] and not equivalence["component_differences"],
            "Default complete-payload equivalence failed")

    summaries, source_hashes, frozen = {}, {}, []
    for stage in STAGES:
        path = results / (stage + ".summary.json")
        summary, fingerprint = read_json(path)
        record = checkpoint["stages"][stage]
        require(record.get("status") == "completed" and record.get("exit_code") == 0
                and record["outputs"].get(RESULT_DIRECTORY + "/" + path.name) == fingerprint,
                "Incomplete stage or summary hash mismatch: " + stage)
        require(summary["stage"] == stage and summary["status"] == "completed"
                and summary["evaluator"] == "round4-native-component-comparison-1"
                and summary["validation"]["passed"] is True and not summary["validation"]["failures"],
                "Invalid completed summary: " + stage)
        require(summary["host_id"] == checkpoint["host"]["id"]
                and summary["source_commit"] == checkpoint["source_commit"]
                and summary["execution_claim"] == checkpoint["claim_commit"]
                and summary["execution_intent"] == record["execution_intent"]
                and summary["plan_sha256"] == checkpoint["plan_sha256"]
                and summary["binding_sha256"] == BINDING_SHA
                and summary["cohort_manifest_sha256"] == MANIFEST_SHA,
                "Stage source, host, claim or selection differs: " + stage)
        require(summary["dataset"]["queries"] == 256 and summary["dataset"]["sha256"] == DATASET_SHA,
                "Stage dataset differs: " + stage)
        expected_calls = 0 if stage == "export" else 1536 if stage in NATIVE else 768
        require(summary["attempts_started"] == summary["attempts_finished"] == expected_calls,
                "Stage attempt count differs: " + stage)
        for cell in summary["configurations"]:
            metric = cell["metrics"]
            require(metric["queries"] == metric["answerable_queries"] == 256
                    and metric["required_evidence"] == 635
                    and cell["invariants"] and all(value == 0 for value in cell["invariants"].values()),
                    "Evidence denominator or context invariant differs: " + stage)
        frozen.append(json.dumps(summary["frozen_corpus"], sort_keys=True, separators=(",", ":")))
        summaries[stage] = summary
        source_hashes[path.name] = fingerprint
    require(len(set(frozen)) == 1, "Stages use different supplied pages or evidence")

    rows = []
    for stage, label, color in ENGINES:
        summary = summaries[stage]
        cell = one(summary["configurations"], lambda item: item["tokenizer"] == "cl100k_base"
                   and item["budget_tokens"] == 1024, stage + " common whole-page packing cell")
        metric, latency = cell["metrics"], summary["adapter_roundtrip_latency"]
        require(latency["samples"] == 768, "Component search repetition count differs: " + stage)
        rows.append({"stage": stage, "label": label, "color": color,
                     "complete_percent": 100 * number(metric["complete_evidence_rate"], stage + " completeness", maximum=1),
                     "search_p95_ms": number(latency["p95_ms"], stage + " adapter roundtrip p95")})

    fresh = {}
    for name, stage in (("baseline", "baseline-component"), ("candidate", "candidate-component")):
        summary = summaries[stage]
        fresh[name] = {
            "p95_ms": number(summary["adapter_roundtrip_latency"]["p95_ms"], stage + " p95", minimum=1e-12),
            "setup_tree_peak_rss_mib": number(
                summary["resources"]["sampled_process_tree_peak_rss_bytes"]["setup"],
                stage + " sampled setup RSS", minimum=1) / 1048576,
        }
    fresh["p95_change_percent"] = 100 * (fresh["candidate"]["p95_ms"] / fresh["baseline"]["p95_ms"] - 1)
    fresh["setup_tree_peak_rss_change_percent"] = 100 * (
        fresh["candidate"]["setup_tree_peak_rss_mib"] / fresh["baseline"]["setup_tree_peak_rss_mib"] - 1)
    fresh["boundary"] = "100000-character component ranker; one unbalanced run; RSS includes evaluator/data"

    formal, formal_sha = read_json(formal_path)
    require(formal_sha == FORMAL_SHA and formal["status"] == "measurements_completed"
            and formal["error"] is None and formal["evaluator_unchanged"] is True
            and formal["validation"]["passed"] is True
            and formal["validation"]["timed_calls"] == formal["validation"]["expected_calls"] == 56784
            and formal["acceptance"]["accepted"] is True
            and formal["acceptance"]["numeric_gate_passed"] is True
            and formal["acceptance"]["resource_review"] == [],
            "Require the unchanged complete formal summary with all automatic gates passed")
    publication = formal["run"]["publication"]
    require(publication["run_id"] + "-" + publication["run_attempt"] == FORMAL_RUN,
            "Formal summary belongs to another execution")
    paired = []
    for identity, label in FORMAL_CONFIGS:
        cell = one(formal["comparisons"], lambda item: item["cohort"] == "public1015"
                   and item["id"] == identity, "formal public paired cell " + identity)
        require(all(cell[engine]["latency"]["samples"] == 4060 for engine in ("baseline", "candidate"))
                and len(cell["rounds"]) == 4, "Formal paired sample or round counts changed")
        require(cell["surface"] == ("official-sdk-mcp-stdio" if identity.startswith("mcp-") else "native"),
                "Formal native/MCP measurement boundary differs")
        paired.append({"id": identity, "label": label,
                       **{engine: number(cell[engine]["latency"]["p95_ms"], identity + " p95")
                          for engine in ("baseline", "candidate")},
                       "candidate_change_percent": number(cell["candidate_change_percent"]["p95_ms"],
                                                           identity + " p95 change", minimum=None)})
    mcp_character = one(paired, lambda item: item["id"] == "mcp-char4000", "MCP character tradeoff")
    resources = formal["acceptance"]["resource_comparisons"]
    for row in resources:
        number(row["mean_change_percent"], "Resource mean change", minimum=None)
    largest_resource = max(resources, key=lambda item: item["mean_change_percent"])
    require(f"{mcp_character['candidate_change_percent']:.2f}" == "1.44"
            and f"{largest_resource['mean_change_percent']:.2f}" == "6.02",
            "Registered negative-result footnotes differ")

    # Deliberate whitelist: never embed whole summaries or assessment query rows.
    return {"schema_version": 1, "components": rows, "paired": paired,
            "comparison_run": RUN, "formal_run": FORMAL_RUN,
            "dataset_sha256": DATASET_SHA, "queries": 256, "required_annotations": 635,
            "comparison_native_calls": 4608, "comparison_component_search_calls": 4608,
            "default_complete_payload_pairs": {"native": 1536, "component": 768},
            "comparison_binding_sha256": BINDING_SHA, "cohort_manifest_sha256": MANIFEST_SHA,
            "checkpoint_sha256": checkpoint_sha, "assessment_sha256": assessment_sha,
            "summary_sha256": source_hashes,
            "frozen_corpus_metadata_sha256": hashlib.sha256(frozen[0].encode()).hexdigest(),
            "component_latency_boundary": "adapter_roundtrip_latency",
            "component_quality_boundary": "First response; common whole-page packing; top five; 1024 cl100k_base tokens",
            "fresh_component_version_comparison": fresh,
            "formal_summary_sha256": formal_sha,
            "formal_raw_report_sha256": formal["full_report_sha256"],
            "formal_compressed_report_sha256": formal["compressed_report_sha256"],
            "formal_sources": formal["run"]["binding"]["sources"],
            "formal_calls": 56784, "formal_public_samples_per_source_configuration": 4060,
            "formal_automatic_acceptance": True, "resource_waiver": False,
            "public_mcp_character_p95_change_percent": mcp_character["candidate_change_percent"],
            "maximum_registered_resource_mean_change_percent": largest_resource["mean_change_percent"],
            "maximum_resource_metric": largest_resource["metric"],
            "maximum_resource_cohort": largest_resource["cohort"],
            "artifact_links": {"comparison_all_raw_results_and_losses": COMPARISON_URL,
                               "formal_all_raw_results_and_ledgers": FORMAL_URL},
            "retrieval_calls_executed": 0, "inference_calls_executed": 0}


def render(data, output, png=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator, PercentFormatter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "text.color": "#172333", "axes.labelcolor": "#48566a",
                         "xtick.color": "#607086", "ytick.color": "#172333",
                         "svg.fonttype": "none", "svg.hashsalt": "memory-book-round4-overview-v1"})
    fig = plt.figure(figsize=(13, 10.8), facecolor="white")
    grid = fig.add_gridspec(2, 2, left=.205, right=.965, top=.825, bottom=.325,
                           height_ratios=(1.13, 1), hspace=.76, wspace=.30)
    quality, latency = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    paired = fig.add_subplot(grid[1, :])
    fig.text(.055, .954, "AI-Memory-Book v0.3.2 · measured results", fontsize=21, weight="bold")
    fig.text(.055, .916, "256 HotpotQA questions · identical supplied pages · top five · common whole-page packing",
             fontsize=11, color="#48566a")
    fig.text(.055, .890, "Component view: 1,024 cl100k_base tokens. Complete evidence measures retrieval, not answer accuracy.",
             fontsize=10, color="#607086")

    colors = [row["color"] for row in data["components"]]
    y = list(range(len(data["components"])))
    for axis, field, title in ((quality, "complete_percent", "Complete evidence · higher is better"),
                               (latency, "search_p95_ms", "Search adapter p95 · lower is better")):
        values = [row[field] for row in data["components"]]
        axis.barh(y, values, color=colors, height=.58, zorder=3)
        axis.set_yticks(y, [row["label"] for row in data["components"]] if axis is quality else [])
        axis.invert_yaxis()
        axis.set_title(title, fontsize=12, weight="bold", loc="left", pad=15)
        limit = 105 if axis is quality else max(1, max(values) * 1.25)
        axis.set_xlim(0, limit)
        axis.set_axisbelow(True)
        axis.grid(axis="x", color="#e5eaf0", linewidth=.7)
        axis.tick_params(axis="both", length=0, pad=8)
        if axis is quality:
            axis.set_xticks([0, 20, 40, 60, 80, 100])
            axis.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        else:
            axis.set_xlabel("Milliseconds · adapter search roundtrip", fontsize=9, labelpad=9)
            axis.xaxis.set_major_locator(MaxNLocator(5))
        for position, value in zip(y, values):
            suffix = "%" if axis is quality else " ms"
            axis.text(value + limit * .02, position, f"{value:.2f}" + suffix,
                      va="center", fontsize=10, weight="bold", color="#26374b")
        for spine in axis.spines.values():
            spine.set_visible(False)

    x = list(range(len(data["paired"])))
    width = .31
    for engine, offset, color, label in (("baseline", -width / 2, "#a7b3c2", "v0.3.1"),
                                       ("candidate", width / 2, "#2563eb", "v0.3.2")):
        bars = paired.bar([position + offset for position in x], [row[engine] for row in data["paired"]],
                          width=width, color=color, label=label, zorder=3)
        paired.bar_label(bars, fmt="%.2f", padding=4, fontsize=9, color="#26374b")
    paired.set_title("Paired public conversation test · identical outputs", loc="left",
                     fontsize=12, weight="bold", pad=20)
    paired.set_xticks(x, [row["label"] for row in data["paired"]], fontsize=9)
    paired.set_ylabel("p95 milliseconds", fontsize=10)
    paired.set_ylim(0, max(max(row["baseline"], row["candidate"]) for row in data["paired"]) * 1.30)
    paired.set_axisbelow(True)
    paired.grid(axis="y", color="#e5eaf0", linewidth=.7)
    paired.tick_params(axis="both", length=0, pad=8)
    paired.legend(loc="upper right", frameon=False, ncols=2, bbox_to_anchor=(1, 1.04), fontsize=9)
    for spine in paired.spines.values():
        spine.set_visible(False)

    fresh = data["fresh_component_version_comparison"]
    notes = (
        "Top: 256 questions; three search repetitions. Search timings exclude common packing and additional page-read costs.",
        "Different boundaries: Book Python recall/assembly; claude-mem SQLite/Bun; ai-memory HTTP/MCP; billion-context Node kernel.",
        f"Fresh Book component vs v0.3.1: 100,000-char p95 {fresh['p95_change_percent']:+.2f}%; setup tree RSS "
        f"{fresh['baseline']['setup_tree_peak_rss_mib']:.2f} to {fresh['candidate']['setup_tree_peak_rss_mib']:.2f} MiB.",
        "That fresh component run is unbalanced. RSS includes evaluator/data, may double-count shared pages; no cause is established.",
        "Bottom: 56,784 total formal calls; four balanced rounds; 4,060 calls per version/public configuration. No retrieval repeated here.",
        f"Public MCP 4,000-char p95 +{data['public_mcp_character_p95_change_percent']:.2f}%; largest registered resource mean "
        f"+{data['maximum_registered_resource_mean_change_percent']:.2f}% (public MCP token startup).",
        "All formal automatic gates passed; no resource waiver. OS/SQLite caches warm naturally; these are not OS-cold measurements.",
        "No claim of statistical significance, whole-product speed or universal speedup. All negative cells and resource costs are retained.",
    )
    for index, note in enumerate(notes):
        fig.text(.055, .256 - index * .023, note, fontsize=8.5, color="#607086")
    fig.text(.055, .052, "Full comparison 43363060062-1: raw results, per-question gains/losses and search/read costs",
             fontsize=8.5, color="#2563eb", url=COMPARISON_URL)
    fig.text(.055, .029, "Formal performance 43361086255-1: raw report, every worker, all rounds and attempt ledgers",
             fontsize=8.5, color="#2563eb", url=FORMAL_URL)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", metadata={"Date": None,
                "Title": "AI-Memory-Book v0.3.2 component comparison and separate paired performance",
                "Description": json.dumps(data, sort_keys=True, separators=(",", ":"))})
    # Normalize only SVG whitespace; keep the underlying measurements intact.
    output.write_text("\n".join(line.rstrip() for line in output.read_text(encoding="utf-8").splitlines())
                      + "\n", encoding="utf-8")
    if png is not None:
        png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / RESULT_DIRECTORY)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "benchmarks/reports" / ("round4-comparison-" + RUN + "-checkpoint.json"))
    parser.add_argument("--performance-summary", type=Path, default=ROOT / "benchmarks/reports" / ("round4-performance-" + FORMAL_RUN) / "report.summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/v0.3.2-comparison.svg")
    parser.add_argument("--png", type=Path, help="Optional local PNG for visual inspection")
    args = parser.parse_args()
    data = extract(args.results_dir, args.checkpoint, args.performance_summary)
    render(data, args.output, args.png)
    print(json.dumps({"svg": str(args.output), "png": str(args.png) if args.png else None,
                      "component_rows": data["components"], "retrieval_calls_executed": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
