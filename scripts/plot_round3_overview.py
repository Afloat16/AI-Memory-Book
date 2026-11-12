"""Render the v0.3.1 README figure from completed, saved measurements only.

Requires matplotlib. No network access, retrieval, model calls, or benchmark
execution. The fixed official checkpoint must be complete-verified; every
component summary is checked against its published SHA256. The separate
original ABBA summary retains its automatic resource-review exception.

    python scripts/plot_round3_overview.py --png /tmp/round3-overview.png

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
RUN = "43267797247-1"
FORMAL_SHA = "b6f9391956a0231383687d383cb87b0579e2a79d8776e43105e4b172e2d875a1"
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
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def number(value, description, *, maximum=None):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            description + " must be a finite, nonnegative number")
    require(maximum is None or value <= maximum, description + " exceeds its range")
    return float(value)


def one(items, predicate, description):
    matched = [item for item in items if predicate(item)]
    require(len(matched) == 1, "Require exactly one " + description)
    return matched[0]


def extract(results, checkpoint_path, formal_path):
    checkpoint, checkpoint_sha = read_json(checkpoint_path)
    require(checkpoint.get("run_id") == RUN and checkpoint.get("status") == "complete-verified",
            "The authoritative comparison must be complete-verified before plotting")
    require(Path(checkpoint["result_directory"]).name == results.name,
            "Checkpoint result directory does not match the summaries")
    rows, identities, source_hashes = [], [], {}
    for stage, label, color in ENGINES:
        path = results / (stage + ".summary.json")
        summary, fingerprint = read_json(path)
        record = checkpoint["stages"][stage]
        key = str(Path(checkpoint["result_directory"]) / path.name)
        require(record.get("status") == "completed" and record.get("exit_code") == 0
                and record["outputs"].get(key) == fingerprint,
                "Incomplete stage or summary hash mismatch: " + stage)
        require(summary["stage"] == stage and summary["status"] == "completed"
                and summary["validation"]["passed"], "Invalid component summary: " + stage)
        require(summary["host_id"] == checkpoint["host"]["id"]
                and summary["source_commit"] == checkpoint["source_commit"]
                and summary["binding_sha256"] == checkpoint["binding_sha256"]
                and summary["cohort_manifest_sha256"] == checkpoint["cohort_manifest_sha256"],
                "Component source, host or selection differs: " + stage)
        cell = one(summary["configurations"], lambda item: item["tokenizer"] == "cl100k_base"
                   and item["budget_tokens"] == 1024, stage + " common-packing cell")
        metric, latency = cell["metrics"], summary["native_search_latency"]
        require(summary["dataset"]["queries"] == metric["queries"] == 256
                and metric["answerable_queries"] == 256 and latency["samples"] == 768,
                "Question or repetition count differs: " + stage)
        require(all(value == 0 for value in cell["invariants"].values()),
                "Common-context invariant failed: " + stage)
        identities.append((summary["dataset"]["sha256"], metric["required_evidence"],
                           json.dumps(summary["frozen_corpus"], sort_keys=True)))
        rows.append({"stage": stage, "label": label, "color": color,
                     "complete_percent": 100 * number(metric["complete_evidence_rate"], stage + " completeness", maximum=1),
                     "search_p95_ms": number(latency["p95_ms"], stage + " search p95")})
        source_hashes[path.name] = fingerprint
    require(len(set(identities)) == 1, "Components use different evidence or supplied pages")

    formal, formal_sha = read_json(formal_path)
    require(formal_sha == FORMAL_SHA and formal["validation"]["passed"]
            and formal["validation"]["timed_calls"] == 47320
            and formal["acceptance"]["numeric_gate_passed"],
            "Require the unchanged, complete original ABBA summary")
    paired = []
    for identity, label in FORMAL_CONFIGS:
        cell = one(formal["comparisons"], lambda item: item["cohort"] == "public1015"
                   and item["id"] == identity, "original public paired cell " + identity)
        require(all(cell[engine]["latency"]["samples"] == 4060 for engine in ("baseline", "candidate")),
                "Original paired sample counts changed")
        paired.append({"id": identity, "label": label,
                       **{engine: number(cell[engine]["latency"]["p95_ms"], identity + " p95")
                          for engine in ("baseline", "candidate")}})
    return {"components": rows, "paired": paired, "dataset_sha256": identities[0][0],
            "checkpoint_sha256": checkpoint_sha, "summary_sha256": source_hashes,
            "formal_summary_sha256": formal_sha}


def render(data, output, png=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter, MaxNLocator

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "text.color": "#172333", "axes.labelcolor": "#48566a",
                         "xtick.color": "#607086", "ytick.color": "#172333",
                         "svg.fonttype": "none", "svg.hashsalt": "memory-book-round3-overview-v1"})
    fig = plt.figure(figsize=(12.5, 9.1), facecolor="white")
    grid = fig.add_gridspec(2, 2, left=.205, right=.965, top=.825, bottom=.225,
                           height_ratios=(1.13, 1), hspace=.72, wspace=.30)
    quality, latency = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    paired = fig.add_subplot(grid[1, :])
    fig.text(.055, .954, "AI-Memory-Book v0.3.1 · measured results", fontsize=21, weight="bold")
    fig.text(.055, .916, "256 HotpotQA questions · identical supplied pages · top five · common whole-page packing",
             fontsize=11, color="#48566a")
    fig.text(.055, .890, "Component view: 1,024 cl100k_base tokens. Complete evidence measures retrieval, not answer accuracy.",
             fontsize=10, color="#607086")

    colors = [row["color"] for row in data["components"]]
    y = list(range(len(data["components"])))
    for axis, field, title in ((quality, "complete_percent", "Complete evidence · higher is better"),
                               (latency, "search_p95_ms", "Measured search p95 · lower is better")):
        values = [row[field] for row in data["components"]]
        axis.barh(y, values, color=colors, height=.58, zorder=3)
        axis.set_yticks(y, [row["label"] for row in data["components"]] if axis is quality else [])
        axis.invert_yaxis()
        axis.set_title(title, fontsize=12, weight="bold", loc="left", pad=15)
        limit = 105 if axis is quality else max(values) * 1.25
        axis.set_xlim(0, limit)
        axis.set_axisbelow(True)
        axis.grid(axis="x", color="#e5eaf0", linewidth=.7)
        axis.tick_params(axis="both", length=0, pad=8)
        if axis is quality:
            axis.set_xticks([0, 20, 40, 60, 80, 100])
            axis.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        else:
            axis.set_xlabel("Milliseconds · native search measurement", fontsize=9, labelpad=9)
            axis.xaxis.set_major_locator(MaxNLocator(5))
        for position, value in zip(y, values):
            suffix = "%" if axis is quality else " ms"
            axis.text(value + limit * .02, position, f"{value:.2f}" + suffix,
                      va="center", fontsize=10, weight="bold", color="#26374b")
        for spine in axis.spines.values():
            spine.set_visible(False)

    x = list(range(len(data["paired"])))
    width = .31
    for engine, offset, color, label in (("baseline", -width / 2, "#a7b3c2", "v0.3.0"),
                                       ("candidate", width / 2, "#2563eb", "v0.3.1")):
        bars = paired.bar([position + offset for position in x], [row[engine] for row in data["paired"]],
                          width=width, color=color, label=label, zorder=3)
        paired.bar_label(bars, fmt="%.2f", padding=4, fontsize=9, color="#26374b")
    paired.set_title("Separate paired test · public conversations · identical returned evidence", loc="left",
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

    notes = (
        "Top: 256 questions; three repetitions; native_search_latency. Bridge and page-read costs are separate in the full report.",
        "Python Book, SQLite/Bun claude-mem, HTTP/MCP ai-memory and the Node billion-context kernel have different boundaries.",
        "Bottom: original ABBA run, four balanced rounds and 4,060 calls per version/configuration; no retrieval was repeated for this figure.",
        "Original startup mean +14.04% is retained and independently reviewed. Setup, generation and whole-product speed are not claimed.",
        "Sources: comparison 43267797247-1 · formal performance 43246417515-1. Full reports retain all budgets, losses and resource costs.",
    )
    for index, text in enumerate(notes):
        fig.text(.055, .147 - index * .023, text, fontsize=8.5, color="#607086")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", metadata={"Date": None,
                "Title": "AI-Memory-Book v0.3.1 component comparison and separate paired performance",
                "Description": json.dumps(data, sort_keys=True, separators=(",", ":"))})
    if png is not None:
        png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "benchmarks/results" / ("round3-comparison-" + RUN))
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "benchmarks/reports" / ("round3-comparison-" + RUN + "-checkpoint.json"))
    parser.add_argument("--performance-summary", type=Path, default=ROOT / "benchmarks/reports/round3-performance-43246417515-1/report.summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/v0.3.1-comparison.svg")
    parser.add_argument("--png", type=Path, help="Optional local PNG for visual inspection")
    args = parser.parse_args()
    data = extract(args.results_dir, args.checkpoint, args.performance_summary)
    render(data, args.output, args.png)
    print(json.dumps({"svg": str(args.output), "png": str(args.png) if args.png else None,
                      "component_rows": data["components"], "retrieval_calls_executed": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
