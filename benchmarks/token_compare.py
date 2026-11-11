"""Paired source-evidence evaluation with measured reference-tokenizer costs.

Run baseline and candidate in independent Python processes. The optional shared
token packer keeps whole evidence blocks; it never sees answer labels and never
repeats retrieval to negotiate a budget. This is retrieval, not LLM answer QA.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from benchmarks.data import generate_dataset
from benchmarks.run import (aggregate, engine_source_hash, evaluate_response,
                            original_turn_texts, percentile)


ENCODINGS = ("cl100k_base", "o200k_base")


class TokenCounter:
    def __init__(self, name: str):
        if name not in ENCODINGS:
            raise ValueError("Choose a published reference tokenizer")
        try:
            import tiktoken
        except ImportError as exc:
            raise RuntimeError("Token measurements require tiktoken==0.12.0; no estimate fallback is used") from exc
        self.name = name
        self.version = tiktoken.__version__
        self.encoding = tiktoken.get_encoding(name)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))


def evidence_blocks(response: dict) -> list[tuple[str, dict]]:
    """Recover complete ordered blocks from the actual returned context.

    Assert the decomposition instead of silently scoring metadata for evidence
    that was absent from the model-visible context. Original spans are untouched.
    """
    context = response["context"]
    cursor = 0
    blocks = []
    for item in response.get("results", []):
        text = item.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("A scored result needs nonempty original text")
        start = cursor + (2 if blocks else 0)
        if blocks and context[cursor:start] != "\n\n":
            raise ValueError("Evidence blocks must have an exact separator")
        # Text bodies start after a newline. This avoids matching a short title
        # accidentally when the original text also appears in a citation header.
        body = context.find("\n" + text, start)
        if body < start:
            raise ValueError("Result text is not present in the returned context")
        end = body + 1 + len(text)
        blocks.append((context[start:end], item))
        cursor = end
    if cursor != len(context) or "\n\n".join(block for block, _ in blocks) != context:
        raise ValueError("Context and returned evidence blocks disagree")
    return blocks


def pack_whole_blocks(response: dict, budget_tokens: int, counter: TokenCounter) -> dict:
    """Rank-order first-fit packing, identical for every compared system.

    A block that does not fit is skipped; later smaller blocks may fit. No text
    or source reference is shortened, and no ground-truth label is consulted.
    """
    if budget_tokens < 0:
        raise ValueError("Token budget must be nonnegative")
    blocks, results = [], []
    for block, result in evidence_blocks(response):
        proposed = "\n\n".join(blocks + [block])
        if counter.count(proposed) <= budget_tokens:
            blocks.append(block)
            results.append(copy.deepcopy(result))
    context = "\n\n".join(blocks)
    return {**response, "context": context, "context_chars": len(context),
            "results": results, "packing_tokenizer": counter.name,
            "packing_budget_tokens": budget_tokens,
            "truncated": bool(response.get("truncated")) or len(results) != len(response.get("results", []))}


def load_dataset(corpus: str, seed: int, split: str, projects: int,
                 locomo_path: str | None = None, max_queries: int = 0):
    if corpus == "synthetic":
        return generate_dataset(seed=seed, split=split, projects=projects)
    from benchmarks.public_data import load_locomo
    if not locomo_path:
        raise ValueError("--locomo-path is required for the external LoCoMo data")
    return load_locomo(Path(locomo_path), split=split, max_queries=max_queries)


def latency_summary(values: list[float]) -> dict:
    return {"samples": len(values), "p50_ms": percentile(values, .5),
            "p95_ms": percentile(values, .95), "mean_ms": statistics.fmean(values) if values else None}


def summarize_rows(rows: list[dict]) -> dict:
    result = aggregate(rows)
    result["mean_context_tokens"] = {
        name: statistics.fmean(row["context_tokens"][name] for row in rows) if rows else None
        for name in ENCODINGS}
    return result


def score_row(case, response, source_texts, counters, *, public: bool) -> dict:
    row = evaluate_response(case, response, response["budget_chars"], source_texts)
    row["context_tokens"] = {name: counter.count(response["context"]) for name, counter in counters.items()}
    if public:
        # The dataset is downloaded separately under its own license. Published
        # reports retain IDs/metrics, never questions, answers, or source quotes.
        row.pop("query", None)
    return row


def measure_engine(args) -> dict:
    sys.path.insert(0, str(Path(args.engine_src).resolve()))
    from memory_book import MemoryBook, __version__
    import memory_book
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    dataset = load_dataset(args.corpus, args.seed, args.split, args.projects,
                           args.locomo_path, args.max_queries)
    source_texts = original_turn_texts(dataset)
    source_root = Path(memory_book.__file__).parent
    source_hash = engine_source_hash(source_root)
    report = {"label": args.label, "engine_version": __version__,
              "source_sha256_before": source_hash, "dataset": dataset.description(),
              "tokenizer": {"library": "tiktoken", "version": counters[ENCODINGS[0]].version,
                            "encodings": list(ENCODINGS)},
              "parameters": {"budget_chars": args.budget_chars, "packing_token_budgets": args.token_budgets,
                             "packing_input_char_cap": max(args.budget_chars), "limit": args.limit,
                             "repeats": args.repeats, "segmentation": "adaptive", "max_page_chars": 900},
              "configurations": [], "packed_configurations": []}
    with tempfile.TemporaryDirectory(prefix="memory-token-compare-", dir=Path.cwd().parent) as directory:
        database = Path(directory) / "memory.db"
        with MemoryBook(database, max_page_chars=900, cache_size=128) as book:
            start = time.perf_counter_ns()
            for session in dataset.sessions:
                book.ingest(session)
            report["ingestion_ms"] = (time.perf_counter_ns() - start) / 1e6
            report["engine_stats"] = book.stats()
            for budget in args.budget_chars:
                timings, first_timings, repeat_timings, rows, responses = [], [], [], {}, {}
                for repetition in range(args.repeats):
                    cases = list(dataset.queries)
                    random.Random(args.seed + 1009 * repetition).shuffle(cases)
                    for case in cases:
                        start = time.perf_counter_ns()
                        response = book.recall(case.query, project=case.project, budget_chars=budget,
                                               limit=args.limit, use_cache=False)
                        elapsed = (time.perf_counter_ns() - start) / 1e6
                        timings.append(elapsed)
                        (first_timings if repetition == 0 else repeat_timings).append(elapsed)
                        if repetition == 0:
                            rows[case.id] = score_row(case, response, source_texts, counters,
                                                      public=args.corpus != "synthetic")
                            responses[case.id] = response
                ordered = [rows[case.id] for case in dataset.queries]
                categories = defaultdict(list)
                for row in ordered:
                    categories[row["category"]].append(row)
                report["configurations"].append({"budget_chars": budget, "metrics": summarize_rows(ordered),
                    "latency": latency_summary(timings), "first_pass_latency": latency_summary(first_timings),
                    "repeat_latency": latency_summary(repeat_timings),
                    "by_category": {key: summarize_rows(value) for key, value in sorted(categories.items())},
                    "query_results": ordered})
                if budget == max(args.budget_chars):
                    for name, counter in counters.items():
                        for token_budget in args.token_budgets:
                            packed_rows, packing_ms = [], []
                            for case in dataset.queries:
                                start = time.perf_counter_ns()
                                packed = pack_whole_blocks(responses[case.id], token_budget, counter)
                                packing_ms.append((time.perf_counter_ns() - start) / 1e6)
                                row = score_row(case, packed, source_texts, counters, public=args.corpus != "synthetic")
                                row["token_budget_violation"] = row["context_tokens"][name] > token_budget
                                packed_rows.append(row)
                            report["packed_configurations"].append({"tokenizer": name, "budget_tokens": token_budget,
                                "source_budget_chars": budget, "metrics": summarize_rows(packed_rows),
                                "packing_latency": latency_summary(packing_ms),
                                "token_budget_violations": sum(row["token_budget_violation"] for row in packed_rows),
                                "query_results": packed_rows})
            # Actual new Python CLI processes; database and OS caches remain warm.
            cold = []
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(args.engine_src).resolve()) + os.pathsep + env.get("PYTHONPATH", "")
            env["MEMORY_BOOK_HOME"] = str(Path(directory) / "isolated-home")
            env["MEMORY_BOOK_CONFIG"] = str(Path(directory) / "absent-config.json")
            for case in dataset.queries[:min(3, len(dataset.queries))]:
                command = [sys.executable, "-m", "memory_book", "--db", str(database), "recall", case.query,
                           "--budget", str(args.budget_chars[0]), "--limit", str(args.limit), "--json", "--no-cache"]
                if case.project is not None:
                    command += ["--project", case.project]
                start = time.perf_counter_ns()
                completed = subprocess.run(command, env=env, capture_output=True, timeout=30, check=True)
                cold.append((time.perf_counter_ns() - start) / 1e6)
                json.loads(completed.stdout)
            report["fresh_process_cli_latency"] = latency_summary(cold)
    report["source_sha256_after"] = engine_source_hash(source_root)
    report["source_unchanged"] = source_hash == report["source_sha256_after"]
    return report


def comparison_markdown(report: dict) -> str:
    def percent(value):
        return "n/a" if value is None else f"{value:.2%}"
    lines = ["# Paired retrieval and token-cost measurements", "",
             "These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.", "",
             "## Same character-budget retrieval", "",
             "| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for engine in report["engines"]:
        for config in engine["configurations"]:
            m, t = config["metrics"], config["latency"]
            lines.append(f"| {engine['label']} | {config['budget_chars']} | {percent(m['evidence_recall'])} | {percent(m['complete_evidence_rate'])} | {m['mean_context_tokens']['cl100k_base']:.1f} | {m['mean_context_tokens']['o200k_base']:.1f} | {t['p50_ms']:.3f} | {t['p95_ms']:.3f} |")
    lines += ["", "## Identical whole-evidence-block token packing", "",
              "One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.", "",
              "| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for engine in report["engines"]:
        for config in engine["packed_configurations"]:
            m = config["metrics"]
            lines.append(f"| {engine['label']} | {config['tokenizer']} | {config['budget_tokens']} | {percent(m['evidence_recall'])} | {percent(m['complete_evidence_rate'])} | {m['mean_context_tokens'][config['tokenizer']]:.1f} | {config['packing_latency']['p95_ms']:.3f} |")
    lines += ["", "## Measurement boundaries", ""]
    lines += ["- " + item for item in report["methodology"]]
    lines += ["", "See the complete compressed JSON for category results, failures, source references, fingerprints, ingest cost, and fresh-process CLI measurements.", ""]
    return "\n".join(lines)


def write_artifacts(report: dict, prefix: Path) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    compressed = gzip.compress(raw, mtime=0)
    assert gzip.decompress(compressed) == raw
    Path(str(prefix) + ".json.gz").write_bytes(compressed)
    summary = copy.deepcopy(report)
    for engine in summary["engines"]:
        for field in ("configurations", "packed_configurations"):
            for config in engine[field]:
                config.pop("query_results", None)
    summary["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    Path(str(prefix) + ".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    Path(str(prefix) + ".md").write_text(comparison_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--corpus", choices=("synthetic", "locomo"), default="synthetic")
    parser.add_argument("--locomo-path")
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--split", choices=("development", "heldout"), default="development")
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=8)
    parser.add_argument("--budget-chars", type=int, nargs="+", default=[2000, 8000])
    parser.add_argument("--token-budgets", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/token-comparison"))
    parser.add_argument("--engine-src", help=argparse.SUPPRESS)
    parser.add_argument("--label", help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.budget_chars) < 128 or min(args.token_budgets) < 1 or args.repeats < 1 or args.limit < 1:
        parser.error("budgets, repeats and limit must be positive; character caps need at least 128")
    if args.worker:
        report = measure_engine(args)
        args.output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return 0 if report["source_unchanged"] else 2
    if args.baseline_src is None:
        parser.error("--baseline-src must identify the frozen baseline package source directory")
    engines = []
    with tempfile.TemporaryDirectory(prefix="memory-token-workers-", dir=Path.cwd().parent) as directory:
        for label, source in (("v0.2.1", args.baseline_src), ("candidate", args.candidate_src)):
            output = Path(directory) / (label + ".json")
            command = [sys.executable, "-m", "benchmarks.token_compare", "--worker", "--engine-src", str(source.resolve()),
                       "--label", label, "--corpus", args.corpus, "--split", args.split, "--seed", str(args.seed),
                       "--projects", str(args.projects), "--limit", str(args.limit), "--repeats", str(args.repeats),
                       "--max-queries", str(args.max_queries), "--output", str(output),
                       "--budget-chars", *map(str, args.budget_chars), "--token-budgets", *map(str, args.token_budgets)]
            if args.locomo_path:
                command += ["--locomo-path", str(Path(args.locomo_path).resolve())]
            subprocess.run(command, check=True)
            engines.append(json.loads(output.read_text()))
            print(f"{label}: measured {engines[-1]['dataset']['queries']} queries", file=sys.stderr, flush=True)
    if engines[0]["dataset"]["sha256"] != engines[1]["dataset"]["sha256"]:
        raise RuntimeError("Engines did not receive identical datasets")
    report = {"schema_version": 1, "evaluator_version": "token-compare-1.0",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "platform": platform.platform()},
              "dataset": engines[0]["dataset"], "engines": engines,
              "methodology": [
                  "Both versions run in independent Python processes with identical records, query order, scope, result limit, page settings, and budgets.",
                  "Context tokens are actual tiktoken 0.12.0 counts for cl100k_base and o200k_base; they are reference encodings, not every provider's tokenizer or billed API usage.",
                  "Recall latency excludes token counting, ingestion, MCP, networking and model inference. Result caching is disabled; SQLite and OS caches are not flushed.",
                  "Fresh-process CLI measurements include Python startup, imports, database open, recall and JSON serialization, with warm disk caches; they are not cold-disk latency.",
                  "The common token packer sees no evidence labels, retains whole returned blocks, and never invokes retrieval again. Packing latency is reported separately.",
                  "Evidence requires original source identity and span plus the complete annotated text in the actual returned context. Unanswerable nonempty retrieval is not a hallucination rate.",
                  "Synthetic heldout seeds were reserved after development selection; shared templates still limit generalization. Public LoCoMo data remains separately downloaded under CC BY-NC 4.0; reports contain IDs and metrics, not dataset text.",
                  "This paired version comparison does not execute external competitor products. See the separate component comparison for any measured upstream kernels."]}
    write_artifacts(report, args.output)
    print(comparison_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
