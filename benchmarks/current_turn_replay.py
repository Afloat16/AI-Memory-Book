"""Development replay for revisions inside one long engineering conversation.

This is a targeted synthetic diagnostic, not a heldout benchmark, an LLM test,
or a comparison against another product. Run the same file with two different
PYTHONPATH runtimes in AB/BA order. Result-cache reuse is disabled; SQLite and
OS caches are not flushed. Every timed call and its returned evidence is kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

from memory_book import MemoryBook
import memory_book.store as runtime


def corpus() -> tuple[list[dict], list[dict]]:
    """Known failure examples and unchanged-path controls, all public fixtures."""
    topics = [
        ("gradient accumulation steps", "8", "2"),
        ("checkpoint retention count", "12", "3"),
        ("ranking candidate budget", "64", "128"),
        ("solver iteration limit", "100", "250"),
        ("梯度累积步数", "8", "2"),
        ("检查点保留数量", "12", "3"),
        ("候选排序数量", "64", "128"),
        ("求解器迭代上限", "100", "250"),
    ]
    sessions, queries = [], []
    for index, (topic, before, after) in enumerate(topics):
        project = f"algorithm-{index:02d}"
        chinese = index >= 4
        first = (f"{topic}设置为{before}。" if chinese else f"{topic.capitalize()} are {before}. ")
        first += (topic + ("。" if chinese else ". ")) * (100 if chinese else 28)
        corrected = (f"{topic}现在设置为{after}。原来的{before}导致回归，已撤销。" if chinese else
                     f"{topic.capitalize()} are now {after}. The former value {before} caused a regression and is no longer valid.")
        sessions.append({
            "project": project, "session_id": "working-session", "task_id": "algorithm-config",
            "title": topic, "task_title": topic, "created_at": "2026-01-01T08:00:00Z",
            "messages": [
                {"role": "user", "content": topic + "?"},
                {"role": "assistant", "content": first},
                {"role": "user", "content": topic + "?"},
                {"role": "assistant", "content": corrected},
            ],
        })
        # The same identifiers in other projects must never supply evidence.
        for distractor in range(12):
            sessions.append({
                "project": f"unrelated-{index:02d}", "session_id": f"other-{distractor}",
                "task_id": "algorithm-config", "title": topic,
                "created_at": "2026-02-01T08:00:00Z",
                "messages": [{"role": "assistant", "content": f"{topic}: unrelated value 999."}],
            })
        for mode, query in (
            ("current", ("当前" if chinese else "current ") + topic),
            ("historical-control", ("最初" if chinese else "original ") + topic),
            ("ordinary-control", topic),
        ):
            queries.append({"id": f"{project}-{mode}", "project": project, "mode": mode,
                            "query": query, "correction": corrected})
    return sessions, queries


def percentile(values: list[float], probability: float) -> float:
    return sorted(values)[max(0, math.ceil(probability * len(values)) - 1)]


def source_check(book: MemoryBook, response: dict, project: str) -> bool:
    """Check returned coordinates against raw pages AND original turns."""
    for hit in response["results"]:
        page = book.read(hit["id"])["content"]
        spans = hit["excerpt_spans"]
        if any(not 0 <= start <= end <= len(page) for start, end in spans):
            return False
        # This diagnostic uses character-budget recall: one original window.
        text = hit["text"]
        if len(spans) != 1:
            return False
        start, end = spans[0]
        if text != ("…" if start else "") + page[start:end] + ("…" if end < len(page) else ""):
            return False
        for ref in hit["source_refs"]:
            if ref["project"] != project:
                return False
            from memory_book.segmentation import make_turns
            original = book.get_session(ref["project"], ref["session_id"])
            turn = make_turns(original["messages"])[ref["turn_index"]].content
            if page[ref["start"]:ref["end"]] != turn[ref["turn_start"]:ref["turn_end"]]:
                return False
    return True


def run(*, repeats: int, label: str) -> dict:
    sessions, queries = corpus()
    fixture_bytes = json.dumps([sessions, queries], ensure_ascii=False, sort_keys=True).encode()
    rows = []
    with tempfile.TemporaryDirectory(prefix="memory-current-turn-") as temporary:
        database = Path(temporary) / "book.sqlite3"
        started = time.perf_counter_ns()
        with MemoryBook(database, cache_size=0) as book:
            for source in sessions:
                book.ingest(source)
            ingest_ms = (time.perf_counter_ns() - started) / 1e6
            stats = book.stats()
            for repetition in range(repeats):
                # Alternate query order; do not drop first/slow samples.
                order = queries if repetition % 2 == 0 else list(reversed(queries))
                for case in order:
                    started = time.perf_counter_ns()
                    result = book.recall(case["query"], project=case["project"],
                                         budget_chars=500, limit=1, use_cache=False)
                    wall_ms = (time.perf_counter_ns() - started) / 1e6
                    rows.append({
                        "case_id": case["id"], "mode": case["mode"], "repetition": repetition,
                        "wall_ms": wall_ms, "source_valid": source_check(book, result, case["project"]),
                        "correction_visible": case["correction"] in result["context"],
                        "budget_valid": len(result["context"]) <= 500,
                        "response": result,
                    })
    summary = {}
    for mode in sorted({row["mode"] for row in rows}):
        selected = [row for row in rows if row["mode"] == mode]
        times = [row["wall_ms"] for row in selected]
        summary[mode] = {
            "calls": len(selected), "p50_ms": statistics.median(times),
            "p95_ms": percentile(times, .95), "source_failures": sum(not r["source_valid"] for r in selected),
            "budget_failures": sum(not r["budget_valid"] for r in selected),
            "first_pass_correction_visible": sum(r["correction_visible"] for r in selected if r["repetition"] == 0),
            "first_pass_cases": sum(r["repetition"] == 0 for r in selected),
        }
    runtime_root = Path(runtime.__file__).resolve().parent
    return {
        "schema": "engineering-current-turn-development-v1", "label": label,
        "limitations": ["Synthetic, already observed development failures; not a fresh holdout.",
                        "No LLM, agent code-generation run, or external memory system was executed.",
                        "Python recall wall time, including response construction; excludes source verification.",
                        "Result cache disabled; filesystem and SQLite caches are not flushed.",
                        "Bounded candidate pool can still omit a later correction."],
        "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
        "runtime_files_sha256": {str(p.relative_to(runtime_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(runtime_root.rglob("*.py"))},
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "settings": {"repeats": repeats, "budget_chars": 500, "limit": 1, "cache_size": 0},
        "ingest_ms": ingest_ms, "stats": stats, "summary": summary, "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="development")
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = run(repeats=args.repeats, label=args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
