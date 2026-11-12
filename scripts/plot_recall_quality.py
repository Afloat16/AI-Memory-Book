"""Plot completed recall-quality measurements without running any benchmark.

Run only after the frozen evaluation and assessment have completed:

    python scripts/plot_recall_quality.py

The default input is benchmarks/results/recall-final-assessment.json. Its outputs
remain docs/assets/recall-quality-costs.svg and .png. A later assessment may name
its comparison artifacts, version labels, and default output prefix through
plot_sources, or --output-prefix can override the destination. Requires
matplotlib. Panel C compares only real AI-Memory-Book MCP stdio calls; component
timings with different observation boundaries are never combined.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPS = (512, 1024, 2048)
CHAR_CAPS = (2000, 8000)
COLORS = {
    "main": "#64748b",
    "preserved": "#b45309",
    "first-round": "#be185d",
    "candidate": "#2563eb",
    "billion-context": "#7c3aed",
    "ai-memory-hybrid": "#0f766e",
}
VERSION_NAMES = {"main": "Main v0.2.1", "preserved": "Preserved v0.3", "candidate": "Optimized"}
COMPONENT_NAMES = {"candidate": "AI-Memory-Book optimized",
                   "billion-context": "billion-context kernel",
                   "ai-memory-hybrid": "ai-memory local hybrid"}
DEFAULT_PLOT_SOURCES = {
    "primary_pair": "recall-final-public-expanded.json.gz", "cohort": "all_1015",
    "versions": [
        {"key": "main", "name": VERSION_NAMES["main"], "artifact": "recall-final-main-expanded.json.gz",
         "side": "old", "tick_label": "Main\nv0.2.1"},
        {"key": "preserved", "name": VERSION_NAMES["preserved"], "artifact": "recall-final-public-expanded.json.gz",
         "side": "old", "tick_label": "Preserved\nv0.3"},
        {"key": "candidate", "name": VERSION_NAMES["candidate"], "artifact": "recall-final-public-expanded.json.gz",
         "side": "new", "tick_label": "Optimized"},
    ],
    "component_names": COMPONENT_NAMES,
    "output_prefix": "docs/assets/recall-quality-costs",
}


def unique(items, predicate, description):
    selected = [item for item in items if predicate(item)]
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one {description}; found {len(selected)}")
    return selected[0]


def number(value, description, *, fraction=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{description} must be a finite nonnegative number")
    if fraction and value > 1:
        raise ValueError(f"{description} must be a fraction between zero and one")
    return float(value)


def extract(assessment, tokenizer):
    """Require matching populations and complete fields; never invent values."""
    if assessment.get("schema_version") != 1:
        raise ValueError("Unsupported assessment schema")
    if not assessment.get("preflight", {}).get("validation", {}).get("passed"):
        raise ValueError("The completed assessment needs a passing source-evidence preflight")
    if assessment["preflight"]["unattainable_labels"] != 0:
        raise ValueError("Unattainable evidence labels remain in the assessment")

    sources = assessment.get("plot_sources", DEFAULT_PLOT_SOURCES)
    versions = sources["versions"]
    keys = [version["key"] for version in versions]
    if not 2 <= len(keys) <= 5 or len(keys) != len(set(keys)) or "candidate" not in keys:
        raise ValueError("Plot sources require two to five unique versions including candidate")
    if any(key not in COLORS for key in keys):
        raise ValueError("Plot version needs an explicit display color")
    pairs = assessment["paired_results"]
    primary = unique(pairs, lambda row: row["artifact"] == sources["primary_pair"], "primary public comparison")
    mcp = assessment["mcp"]["public"]
    dataset = primary["dataset"]
    dataset_hash = dataset["sha256"]
    if mcp["fixture"]["sha256"] != dataset_hash:
        raise ValueError("Public paired and MCP populations must match")

    labels, paired_versions = {}, {}
    candidate_source = primary["sources"][1]
    for version in versions:
        key, side = version["key"], version["side"]
        if side not in ("old", "new") or (key == "candidate" and side != "new"):
            raise ValueError("A plotted version must select an old/new paired side; candidate must select new")
        pair = unique(pairs, lambda row: row["artifact"] == version["artifact"], f"{key} public comparison")
        if pair["dataset"]["sha256"] != dataset_hash:
            raise ValueError("Plotted paired versions must use identical public populations")
        if any(pair["sources"][1][field] != candidate_source[field] for field in ("label", "source_sha256_before")):
            raise ValueError("Paired comparisons do not identify the same candidate bytes")
        labels[key] = pair["sources"][0 if side == "old" else 1]["label"]
        paired_versions[key] = pair
    component_names = sources.get("component_names", COMPONENT_NAMES)
    if set(component_names) != set(COMPONENT_NAMES):
        raise ValueError("The component plot requires candidate, billion-context and ai-memory-hybrid")

    curves = {}
    for selector in component_names:
        engine = unique(assessment["native_components"], lambda row: row["engine_selector"] == selector,
                        f"{selector} component")
        if engine["dataset"]["sha256"] != dataset_hash:
            raise ValueError("The common-page component population must match the public comparison")
        if engine.get("validation", {}).get("passed") is False:
            raise ValueError(f"{selector} component has failed validation")
        if selector == "candidate" and engine["label"] != labels["candidate"]:
            raise ValueError("Component and paired candidate labels differ")
        points = []
        for cap in CAPS:
            config = unique(engine["packed_configurations"],
                            lambda row: row["tokenizer"] == tokenizer and row["budget_tokens"] == cap,
                            f"{selector} {tokenizer} {cap}-token configuration")
            metrics = config["metrics"]
            if config.get("token_budget_violations", 0) or metrics.get("budget_violations", 0) or metrics.get("context_size_mismatches", 0):
                raise ValueError(f"{selector} has invalid budget measurements")
            points.append({"cap": cap,
                           "tokens": number(metrics["mean_context_tokens"][tokenizer], "common context tokens"),
                           "recall": 100 * number(metrics["evidence_recall"], "component evidence recall", fraction=True)})
        curves[selector] = points

    quality = {key: [] for key in keys}
    for cap in CHAR_CAPS:
        reference = unique(primary["budgets"], lambda row: row["cohort"] == sources["cohort"] and row["budget_chars"] == cap,
                           f"primary public comparison at {cap} characters")
        for version in versions:
            key = version["key"]
            budget = unique(paired_versions[key]["budgets"],
                            lambda row: row["cohort"] == sources["cohort"] and row["budget_chars"] == cap,
                            f"{key} public comparison at {cap} characters")
            for metric in ("evidence_recall", "complete_evidence_rate"):
                if budget["new"][metric] != reference["new"][metric]:
                    raise ValueError("The candidate's paired quality differs between otherwise identical public runs")
            quality[key].append(100 * number(budget[version["side"]]["evidence_recall"], "paired evidence recall", fraction=True))

    mcp_costs = {}
    for key, label in labels.items():
        engine = unique(mcp["engines"], lambda row: row["label"] == label, f"{label} actual MCP result")
        calls = engine["aggregate"]["first_call_after_cache_clear"]
        cost = {"tokens": number(calls["tokens"]["o200k_base"]["response_text"]["mean"], "MCP response tokens"),
                "p50": number(calls["wall_ms"]["p50"], "MCP p50 latency"),
                "p95": number(calls["wall_ms"]["p95"], "MCP p95 latency")}
        if cost["p95"] < cost["p50"]:
            raise ValueError("MCP p95 must be at least its p50")
        mcp_costs[key] = cost
    return {"dataset": dataset, "curves": curves, "quality": quality, "mcp": mcp_costs,
            "mcp_budget_chars": mcp["budget_chars"],
            "commit": assessment["candidate_runtime_commit"], "labels": labels,
            "versions": versions, "component_names": component_names,
            "output_prefix": sources["output_prefix"]}


def draw(data, tokenizer, output_prefix, dpi):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import StrMethodFormatter

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#cbd5e1", "axes.labelcolor": "#334155",
        "text.color": "#0f172a", "xtick.color": "#475569", "ytick.color": "#475569",
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "svg.fonttype": "none", "svg.hashsalt": "ai-memory-book-recall-quality",
    })
    figure, axes = plt.subplots(1, 3, figsize=(18.2, 7.3))
    figure.subplots_adjust(left=.055, right=.985, top=.735, bottom=.30, wspace=.32)
    figure.text(.055, .95, "Recall quality and the cost of delivering evidence", fontsize=20, fontweight="bold", va="top")
    dataset = data["dataset"]
    figure.text(.055, .884,
                f"Frozen evaluation  ·  LoCoMo {dataset['queries']:,} questions ({dataset['answerable_queries']:,} answerable)  ·  "
                f"candidate {data['commit'][:12]}", fontsize=10.5, color="#475569")
    for axis in axes:
        axis.grid(axis="y", color="#e2e8f0", linewidth=.8)
        axis.set_axisbelow(True)
        axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))

    # A: same supplied pages, packing policy, tokenizer and selected questions.
    axis = axes[0]
    markers = ("o", "s", "^")
    for selector, points in data["curves"].items():
        axis.plot([point["tokens"] for point in points], [point["recall"] for point in points],
                  color=COLORS[selector], linewidth=2, label=data["component_names"][selector], zorder=2)
        for marker, point in zip(markers, points):
            axis.scatter(point["tokens"], point["recall"], color=COLORS[selector], marker=marker,
                         s=54, edgecolor="white", linewidth=.7, zorder=3)
    axis.set_title("A   Common-page quality / context", loc="left", pad=29, fontsize=12, fontweight="bold")
    axis.set_xlabel(f"Mean delivered context tokens · {tokenizer}", labelpad=10)
    axis.set_ylabel("Required source evidence delivered (%)")
    axis.set_ylim(0, 100)
    axis.set_yticks(range(0, 101, 20))
    axis.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    legend = axis.legend(loc="lower left", frameon=False, fontsize=8.3)
    axis.add_artist(legend)
    cap_handles = [Line2D([], [], color="#64748b", marker=marker, linestyle="None", markersize=5,
                          label=f"{cap:,} cap") for marker, cap in zip(markers, CAPS)]
    axis.legend(handles=cap_handles, loc="lower right", frameon=False, fontsize=8)
    axis.text(0, -.245, "Identical full-page assembly and whole-block packing.\n"
              "Context counts exclude native search/read payloads.", transform=axis.transAxes,
              fontsize=9, color="#475569", va="top", linespacing=1.5)

    # B: every explicitly named Book version, identical population/caps.
    axis = axes[1]
    versions = data["versions"]
    width = .69 / len(versions)
    for index, version in enumerate(versions):
        key = version["key"]
        positions = [position + (index - (len(versions) - 1) / 2) * width for position in range(len(CHAR_CAPS))]
        values = data["quality"][key]
        bars = axis.bar(positions, values, width=width * .90, color=COLORS[key], label=version["name"])
        axis.bar_label(bars, labels=[f"{value:.1f}" for value in values], padding=4, fontsize=9)
    axis.set_title("B   Public recall at the same character cap", loc="left", pad=29, fontsize=12, fontweight="bold")
    axis.set_ylabel("Required source evidence delivered (%)")
    axis.set_xticks([0, 1], ["2,000 characters", "8,000 characters"])
    axis.set_ylim(0, 100)
    axis.set_yticks(range(0, 101, 20))
    axis.legend(frameon=False, loc="lower left", bbox_to_anchor=(-.015, 1.005), ncols=3 if len(versions) == 3 else 2,
                fontsize=7.8, handlelength=1.2, columnspacing=1.0)
    axis.text(0, -.245, "All eligible public questions; no favorable subset.\n"
              "Budget includes source citation headings.", transform=axis.transAxes,
              fontsize=9, color="#475569", va="top", linespacing=1.5)

    # C: native Book MCP response tokens, with same-boundary measured latency.
    # Latencies remain an explicit table, not a second arbitrary vertical scale.
    axis = axes[2]
    values = [data["mcp"][version["key"]]["tokens"] for version in versions]
    bars = axis.bar(range(len(versions)), values, width=.55, color=[COLORS[version["key"]] for version in versions])
    axis.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=5, fontsize=10)
    axis.set_title("C   Actual Book MCP · one stdio boundary", loc="left", pad=29, fontsize=12, fontweight="bold")
    axis.set_ylabel("Mean returned-text tokens · o200k_base")
    axis.set_xticks(range(len(versions)), [version.get("tick_label", version["name"]) for version in versions])
    axis.set_ylim(0, max(values) * 1.20 if max(values) else 1)
    axis.set_xlim(-.6, len(versions) - .4)
    axis.text(0, 1.025, f"Public workload · {data['mcp_budget_chars']:,}-character cap", transform=axis.transAxes,
              fontsize=9, color="#475569", va="bottom")
    for y, metric in ((-.255, "p50"), (-.335, "p95")):
        axis.text(-.09, y, f"{metric} ms", transform=axis.transAxes, fontsize=8.8, color="#475569", va="center")
        for index, version in enumerate(versions):
            key = version["key"]
            axis.text(index, y, f"{data['mcp'][key][metric]:.2f}", transform=axis.get_xaxis_transform(),
                      ha="center", va="center", fontsize=9.5, fontweight="bold", color=COLORS[key])
    axis.text(0, -.43, "Uncached first calls; startup and model inference excluded.", transform=axis.transAxes,
              fontsize=8.7, color="#475569", va="top")

    figure.text(.055, .082, "Source-evidence retrieval, not generated-answer accuracy", fontsize=11, fontweight="bold")
    figure.text(.055, .045,
                "Reference-tokenizer counts, not provider billing. Common-page context and native response costs are separate consumption surfaces.",
                fontsize=9, color="#475569")
    figure.text(.055, .018,
                "ai-memory native totals elsewhere use search + every mapped top-k page, not minimum required reads. Incomparable component latency is not plotted.",
                fontsize=8.7, color="#475569")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = [output_prefix.with_name(output_prefix.name + suffix) for suffix in (".svg", ".png")]
    try:
        figure.savefig(paths[0], facecolor="white", metadata={"Date": None})
        figure.savefig(paths[1], dpi=dpi, facecolor="white")
    finally:
        plt.close(figure)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, default=ROOT / "benchmarks/results/recall-final-assessment.json")
    parser.add_argument("--output-prefix", type=Path,
                        help="Output path without extension; default comes from the assessment, or the first-round prefix")
    parser.add_argument("--context-tokenizer", choices=("cl100k_base", "o200k_base"), default="cl100k_base")
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    if args.dpi < 72:
        parser.error("dpi must be at least 72")
    try:
        assessment = json.loads(args.assessment.read_text(encoding="utf-8"))
        data = extract(assessment, args.context_tokenizer)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(f"Cannot plot incomplete or incompatible assessment: {error}")
    output_prefix = args.output_prefix if args.output_prefix is not None else ROOT / data["output_prefix"]
    paths = draw(data, args.context_tokenizer, output_prefix, args.dpi)
    print(json.dumps({"input": str(args.assessment), "outputs": [str(path) for path in paths]}, indent=2))


if __name__ == "__main__":
    main()
