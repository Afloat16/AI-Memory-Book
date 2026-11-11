"""Render the v0.3.0 release figure from published summaries (requires matplotlib)."""

from __future__ import annotations

import json
from pathlib import Path


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root = Path(__file__).resolve().parents[1]
    component = json.loads((root / "benchmarks/results/components-locomo-heldout.summary.json").read_text())
    mcp = [json.loads((root / f"benchmarks/reports/mcp-v0.3.0-{name}.summary.json").read_text())
           for name in ("synthetic", "locomo")]
    palette = {"v0.2.1": "#64748b", "candidate": "#2563eb",
               "billion-context": "#8b5cf6", "ai-memory-hybrid": "#b45309"}
    names = {"v0.2.1": "Book v0.2.1", "candidate": "Book v0.3.0",
             "billion-context": "billion-context", "ai-memory-hybrid": "ai-memory hybrid"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#cbd5e1", "axes.labelcolor": "#334155",
                         "text.color": "#0f172a", "xtick.color": "#475569", "ytick.color": "#475569",
                         "svg.hashsalt": "ai-memory-book-v0.3.0"})
    figure, axes = plt.subplots(1, 2, figsize=(12.8, 5.2))
    figure.subplots_adjust(left=.07, right=.98, top=.76, bottom=.22, wspace=.30)
    figure.text(.07, .94, "Less response overhead. Quality tradeoffs remain visible.",
                fontsize=17, fontweight="bold", va="top")
    figure.text(.07, .865, "AI-Memory-Book v0.3.0  /  frozen sources, real upstream components, actual MCP calls",
                fontsize=10, color="#475569")
    for ax in axes:
        ax.grid(axis="y", color="#e2e8f0", linewidth=.8)
        ax.set_axisbelow(True)
    for engine in component["engines"]:
        rows = sorted((row for row in engine["packed_configurations"] if row["tokenizer"] == "cl100k_base"),
                      key=lambda row: row["budget_tokens"])
        x = [row["metrics"]["mean_context_tokens"]["cl100k_base"] for row in rows]
        y = [100 * row["metrics"]["evidence_recall"] for row in rows]
        axes[0].plot(x, y, marker="o", markersize=5, linewidth=1.8,
                     linestyle="--" if engine["label"] == "v0.2.1" else "-",
                     color=palette[engine["label"]], label=names[engine["label"]])
    axes[0].set(title="Public LoCoMo · shared-page components", xlabel="Mean context tokens · cl100k_base",
                ylabel="Evidence recall (%)", xlim=(400, 930), ylim=(60, 78))
    axes[0].legend(frameon=False, ncols=2, fontsize=8.5, loc="lower right")
    axes[0].text(.0, -.30, "Each curve: caps of 512, 1,024 and 2,048 tokens.\n256 selected queries; 176 answerable; full-utterance evidence.",
                 transform=axes[0].transAxes, fontsize=8.5, color="#475569", va="top")
    for index, version in enumerate(("v0.2.1", "v0.3.0")):
        values = [next(engine for engine in report["engines"] if engine["label"] == version)
                  ["aggregate"]["first_call_after_cache_clear"]["tokens"]["o200k_base"]["response_text"]["mean"]
                  for report in mcp]
        x = [position + (index - .5) * .30 for position in range(2)]
        bars = axes[1].bar(x, values, width=.28, color=palette["v0.2.1" if index == 0 else "candidate"],
                           label=version)
        axes[1].bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=4, fontsize=10)
    axes[1].set(title="Actual MCP · returned text including metadata",
                ylabel="Mean response tokens · o200k_base", ylim=(0, 3800))
    axes[1].set_xticks([0, 1], ["Synthetic\n2,000 characters", "LoCoMo\n8,000 characters"])
    axes[1].legend(frameon=False, ncols=2, loc="upper left", fontsize=9)
    axes[1].text(.0, -.30, "46.2% and 54.9% fewer tokens than v0.2.1.\nReference-tokenizer counts; not provider billing or answer scores.",
                 transform=axes[1].transAxes, fontsize=8.5, color="#475569", va="top")
    target = root / "docs/assets/v0.3.0-cost-quality"
    figure.savefig(target.with_name(target.name + ".png"), dpi=180, facecolor="white")
    figure.savefig(target.with_name(target.name + ".svg"), facecolor="white", metadata={"Date": None})
    plt.close(figure)


if __name__ == "__main__":
    main()
