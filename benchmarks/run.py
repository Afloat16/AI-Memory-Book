"""Run a fair, local retrieval microbenchmark with source-level evidence labels.

Example::

    python -m benchmarks.run --split development --seed 17 --projects 4 \
        --output benchmarks/results/development-17
    python -m benchmarks.run --split heldout --seed 29 --budget-chars 2000 8000 \
        --output benchmarks/results/heldout-29

The engine is imported only inside ``run`` so dataset/evaluator tests do not
require a database or the complete application.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import platform
import random
import re
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .data import DATASET_VERSION, Dataset, Evidence, QueryCase, generate_dataset


SEGMENTATIONS = ("session", "turn", "adaptive")
STRATEGIES = ("flat", "book")
EVALUATOR_VERSION = "1.2"
SourceTexts = dict[tuple[str, str, int], str]


def percentile(values: list[float], quantile: float) -> float | None:
    """Linearly interpolate percentiles, including samples smaller than 100."""
    if not values:
        return None
    ordered = sorted(values)
    location = (len(ordered) - 1) * quantile
    lower, upper = math.floor(location), math.ceil(location)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _ref_project(result: dict[str, Any], ref: dict[str, Any],
                 fallback: str | None = None) -> str | None:
    project = ref.get("project", ref.get("project_id"))
    if project is None and result.get("breadcrumb"):
        project = result["breadcrumb"][0].get("id")
    return project if project is not None else fallback


def original_turn_texts(dataset: Dataset) -> SourceTexts:
    """Reconstruct source-turn text to verify returned original-turn offsets.

    The fixture format contains alternating user/assistant pairs. Uppercase
    speaker labels and blank-line separators are the engine's documented turn
    representation; this evaluator does not call the engine to create labels.
    """
    result: SourceTexts = {}
    for session in dataset.sessions:
        turn, pieces = -1, []
        for message in session["messages"]:
            if message["role"] == "user":
                if pieces:
                    result[(session["project"], session["session_id"], turn)] = "\n\n".join(pieces)
                turn += 1
                pieces = []
            pieces.append(f"{message['role'].upper()}: {message['content']}")
        if pieces:
            result[(session["project"], session["session_id"], turn)] = "\n\n".join(pieces)
    return result


def _evidence_rank(evidence: Evidence, results: list[dict[str, Any]],
                   context: str, project: str | None = None,
                   source_texts: SourceTexts | None = None) -> int | None:
    needle = _normalized(evidence.needle)
    # A retrieved hit whose actual budgeted context lost its answer is a miss.
    if needle not in _normalized(context):
        return None
    for rank, result in enumerate(results, 1):
        if needle not in _normalized(str(result.get("text", ""))):
            continue
        for ref in result.get("source_refs", []):
            ref_project = _ref_project(result, ref, project)
            if (ref.get("session_id") != evidence.session_id
                    or ref.get("turn_index") != evidence.turn_index
                    or (project is not None and ref_project != project)):
                continue
            if source_texts is not None:
                original = source_texts.get((str(ref_project), evidence.session_id, evidence.turn_index))
                lo, hi = ref.get("turn_start"), ref.get("turn_end")
                if (original is None or not isinstance(lo, int) or not isinstance(hi, int)
                        or not 0 <= lo <= hi <= len(original)
                        or needle not in _normalized(original[lo:hi])):
                    continue
            return rank
    return None


def _duplicate_source_characters(results: list[dict[str, Any]],
                                 default_project: str | None = None) -> int:
    """Count overlapping source intervals when the engine exposes valid spans.

    This is source-span overlap, not semantic redundancy. Repeated wording in
    different turns is intentionally not called duplicate source content.
    """
    intervals: dict[tuple[str, str, int], list[tuple[int, int]]] = defaultdict(list)
    duplicates = 0
    seen_pages: set[str] = set()
    for result in results:
        page_id = str(result.get("id", ""))
        if page_id and page_id in seen_pages:
            duplicates += len(str(result.get("text", "")))
            continue
        if page_id:
            seen_pages.add(page_id)
        for ref in result.get("source_refs", []):
            # start/end are page-local in MemoryBook; continuation pages can
            # reuse those coordinates without overlapping the original turn.
            start = ref.get("turn_start", ref.get("start"))
            end = ref.get("turn_end", ref.get("end"))
            turn = ref.get("turn_index")
            if (not isinstance(start, int) or not isinstance(end, int)
                    or end <= start or not isinstance(turn, int)):
                continue
            project = _ref_project(result, ref, default_project)
            key = (str(project or ""),
                   str(ref.get("session_id", "")), turn)
            overlap = sum(max(0, min(end, old_end) - max(start, old_start))
                          for old_start, old_end in intervals[key])
            duplicates += overlap
            merged: list[tuple[int, int]] = []
            for old_start, old_end in sorted(intervals[key] + [(start, end)]):
                if merged and old_start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], old_end))
                else:
                    merged.append((old_start, old_end))
            intervals[key] = merged
    return duplicates


def evaluate_response(case: QueryCase, response: dict[str, Any],
                      budget_chars: int,
                      source_texts: SourceTexts | None = None) -> dict[str, Any]:
    """Evaluate only evidence that reached the returned, budgeted context."""
    results = response.get("results", [])
    context = str(response.get("context", ""))
    ranks = [_evidence_rank(item, results, context, case.project, source_texts)
             for item in case.required]
    stale_ranks = [_evidence_rank(item, results, context, case.project, source_texts)
                   for item in case.stale]
    found = [rank for rank in ranks if rank is not None]
    old_found = [rank for rank in stale_ranks if rank is not None]
    # Retrieval is not answer generation. For an unanswerable question, a
    # nonempty context is a diagnostic, not proof of an incorrect answer.
    return {
        "id": case.id,
        "query": case.query,
        "category": case.category,
        "project": case.project,
        "answerable": case.answerable,
        "required_evidence": len(case.required),
        "matched_evidence": len(found),
        "complete": bool(case.required) and len(found) == len(case.required),
        "reciprocal_rank": (1 / min(found)) if found else 0.0,
        "evidence_ranks": ranks,
        "stale_ranks": stale_ranks,
        "stale_only": bool(old_found) and not bool(found),
        "stale_before_current": bool(old_found) and bool(found)
                                and min(old_found) < min(found),
        "nonempty": bool(context.strip()),
        "returned_characters": len(context),
        "returned_utf8_bytes": len(context.encode("utf-8")),
        "reported_context_chars": response.get("context_chars"),
        "context_size_consistent": response.get("context_chars") == len(context),
        "budget_violation": len(context) > budget_chars,
        "estimated_tokens": response.get("estimated_tokens"),
        "candidate_count": response.get("candidate_count"),
        "result_count": len(results),
        "duplicate_source_characters": _duplicate_source_characters(results, case.project),
        "result_ids": [result.get("id") for result in results],
        "result_sources": [result.get("source_refs", []) for result in results],
    }


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    answerable = [row for row in rows if row["answerable"]]
    unanswerable = [row for row in rows if not row["answerable"]]
    latest = [row for row in rows if row["category"] == "latest_decision"]
    required = sum(row["required_evidence"] for row in answerable)

    def mean(items: list[dict[str, Any]], key: str) -> float | None:
        return statistics.fmean(float(item[key]) for item in items) if items else None

    return {
        "queries": len(rows),
        "answerable_queries": len(answerable),
        "unanswerable_queries": len(unanswerable),
        "required_evidence": required,
        "matched_evidence": sum(row["matched_evidence"] for row in answerable),
        "evidence_recall": (sum(row["matched_evidence"] for row in answerable)
                            / required) if required else None,
        "complete_evidence_rate": mean(answerable, "complete"),
        "mrr": mean(answerable, "reciprocal_rank"),
        "mean_context_characters": mean(rows, "returned_characters"),
        "mean_answerable_context_characters": mean(answerable, "returned_characters"),
        "mean_context_utf8_bytes": mean(rows, "returned_utf8_bytes"),
        "mean_duplicate_source_characters": mean(rows, "duplicate_source_characters"),
        "unanswerable_nonempty_rate": mean(unanswerable, "nonempty"),
        "latest_stale_only_rate": mean(latest, "stale_only"),
        "latest_stale_before_current_rate": mean(latest, "stale_before_current"),
        "budget_violations": sum(row["budget_violation"] for row in rows),
        "context_size_mismatches": sum(not row["context_size_consistent"] for row in rows),
    }


def _latency_summary(samples: list[float]) -> dict[str, Any]:
    return {"samples": len(samples), "p50_ms": percentile(samples, .5),
            "p95_ms": percentile(samples, .95),
            "mean_ms": statistics.fmean(samples) if samples else None,
            "min_ms": min(samples) if samples else None,
            "max_ms": max(samples) if samples else None}


def engine_source_hash(source_root: Path) -> str:
    """Hash sorted package Python paths and bytes, without host-specific roots."""
    source_hash = hashlib.sha256()
    for path in sorted(source_root.rglob("*.py")):
        source_hash.update(str(path.relative_to(source_root)).encode("utf-8"))
        source_hash.update(b"\0")
        source_hash.update(path.read_bytes())
        source_hash.update(b"\0")
    return source_hash.hexdigest()


def _call(book: Any, case: QueryCase, budget: int, strategy: str,
          limit: int, use_cache: bool) -> dict[str, Any]:
    return book.recall(case.query, project=case.project, budget_chars=budget,
                       limit=limit, strategy=strategy, use_cache=use_cache)


def _measure_configuration(book: Any, dataset: Dataset, segmentation: str,
                           strategy: str, budget: int, repeats: int, limit: int,
                           measure_cache: bool) -> dict[str, Any]:
    # This is explicitly not cold-process or cold-OS-cache latency: other
    # configurations run in the same process. Each segmentation has a new DB.
    first = dataset.queries[0]
    start = time.perf_counter_ns()
    _call(book, first, budget, strategy, limit, False)
    first_ms = (time.perf_counter_ns() - start) / 1_000_000
    rows: dict[str, dict[str, Any]] = {}
    source_texts = original_turn_texts(dataset)
    latencies: list[float] = []
    per_query_latency: dict[str, list[float]] = defaultdict(list)
    for repetition in range(repeats):
        cases = list(dataset.queries)
        random.Random(dataset.seed + 1009 * repetition).shuffle(cases)
        for case in cases:
            start = time.perf_counter_ns()
            response = _call(book, case, budget, strategy, limit, False)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            latencies.append(elapsed)
            per_query_latency[case.id].append(elapsed)
            if repetition == 0:
                rows[case.id] = evaluate_response(case, response, budget, source_texts)
    cache_latencies: list[float] = []
    cache_hits = 0
    if measure_cache:
        # Warm exactly the same query immediately before timing its cached
        # lookup. This does not hide cache churn in the primary uncached run.
        for case in dataset.queries:
            _call(book, case, budget, strategy, limit, True)
            start = time.perf_counter_ns()
            response = _call(book, case, budget, strategy, limit, True)
            cache_latencies.append((time.perf_counter_ns() - start) / 1_000_000)
            cache_hits += bool(response.get("cache_hit"))
    ordered_rows = [rows[case.id] for case in dataset.queries]
    for row in ordered_rows:
        row["latency"] = _latency_summary(per_query_latency[row["id"]])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered_rows:
        grouped[row["category"]].append(row)
    return {
        "segmentation": segmentation, "strategy": strategy,
        "budget_chars": budget, "limit": limit,
        "first_query_same_process_ms": first_ms,
        "uncached_latency": _latency_summary(latencies),
        "immediately_repeated_cache_latency": (_latency_summary(cache_latencies)
                                               if measure_cache else None),
        "immediately_repeated_cache_hit_rate": (cache_hits / len(dataset.queries)
                                               if measure_cache else None),
        "metrics": aggregate(ordered_rows),
        "by_category": {category: aggregate(grouped[category])
                        for category in sorted(grouped)},
        "query_results": ordered_rows,
    }


def run(*, seed: int = 29, split: str = "heldout", projects: int = 8,
        budgets: tuple[int, ...] = (4000,), repeats: int = 3, limit: int = 5,
        max_page_chars: int = 900, min_page_chars: int = 400,
        similarity_threshold: float = .12, measure_cache: bool = True,
        include_long_sessions: bool = True,
        segmentations: tuple[str, ...] = SEGMENTATIONS,
        strategies: tuple[str, ...] = STRATEGIES) -> dict[str, Any]:
    from memory_book import MemoryBook
    import memory_book

    if repeats < 1 or limit < 1 or any(budget < 128 for budget in budgets):
        raise ValueError("repeats and limit must be positive; budgets must be at least 128")
    if not segmentations or set(segmentations) - set(SEGMENTATIONS):
        raise ValueError("invalid segmentation selection")
    if not strategies or set(strategies) - set(STRATEGIES):
        raise ValueError("invalid strategy selection")
    dataset = generate_dataset(seed=seed, split=split, projects=projects,
                               include_long_sessions=include_long_sessions)
    source_root = Path(memory_book.__file__).parent
    source_hash = engine_source_hash(source_root)
    started = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "schema_version": 1,
        "evaluator_version": EVALUATOR_VERSION,
        "started_at_utc": started,
        "runtime": {"python": platform.python_version(),
                    "python_implementation": platform.python_implementation(),
                    "sqlite": sqlite3.sqlite_version,
                    "platform": platform.platform(),
                    "machine": platform.machine(),
                    "engine_python_source_sha256": source_hash},
        "dataset": dataset.description(),
        "parameters": {"budgets_chars": list(budgets), "repeats": repeats,
                       "limit": limit, "max_page_chars": max_page_chars,
                       "min_page_chars": min_page_chars,
                       "similarity_threshold": similarity_threshold,
                       "cache_size": 128,
                       "segmentations": list(segmentations),
                       "strategies": list(strategies)},
        "methodology": {
            "primary_measurement": "In-process recall with result caching disabled; OS and SQLite caches are not flushed.",
            "first_query": "First query per configuration in the same Python process, not a cold-process or cold-OS-cache measurement.",
            "cache_measurement": "Each timed cached query immediately follows the identical warm-up query; this is a best-case hot-cache diagnostic.",
            "quality": "Evidence counts only when its original project, session, turn and source offset span match a returned hit and its text survives into the actual budgeted context.",
            "scope": "All methods receive the identical project scope, source transcripts, task metadata, query, result limit, and character budget.",
            "strategy_comparison": "Flat and book share the metadata-aware FTS index; book additionally applies soft directory-overlap reranking. This is not a comparison against an index stripped of directory metadata.",
            "units": "Characters and UTF-8 bytes are exact; estimated_tokens is an engine heuristic, not tokenizer-measured cost.",
            "unanswerable": "Nonempty retrieval on an unanswerable question is measured; the benchmark does not generate answers or measure hallucinations.",
            "limitations": [
                "Synthetic source and question templates; no real user conversations or external project engines are benchmarked.",
                "Task identifiers are supplied metadata, not inferred clustering accuracy.",
                "Directory strategy and page segmentation are separate factors; superiority is not assumed.",
                "Each retrieved unit contributes one query-centered excerpt. A separately optimized multi-window whole-session retriever is not tested.",
                "Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.",
                "No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.",
                "Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.",
            ],
        },
        "ingestion": [], "configurations": [],
    }
    with tempfile.TemporaryDirectory(prefix="memory-book-benchmark-") as directory:
        for segmentation in segmentations:
            path = Path(directory) / f"{segmentation}.sqlite3"
            book = MemoryBook(path, segmentation=segmentation,
                              max_page_chars=max_page_chars,
                              min_page_chars=min_page_chars,
                              similarity_threshold=similarity_threshold,
                              cache_size=128)
            try:
                start = time.perf_counter_ns()
                for session in dataset.sessions:
                    book.ingest(session)
                elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                stats = book.stats()
                page_count = stats.get("pages", 0)
                # Page text size may include serialization labels. If the
                # engine exposes only raw chars, do not call raw/page mean page
                # size; publish the raw-source-per-page ratio explicitly.
                result["ingestion"].append({
                    "segmentation": segmentation, "elapsed_ms": elapsed_ms,
                    "sessions_per_second": len(dataset.sessions) / (elapsed_ms / 1000)
                                           if elapsed_ms else None,
                    "source_characters_per_second": dataset.source_characters / (elapsed_ms / 1000)
                                                    if elapsed_ms else None,
                    "pages": page_count,
                    "source_characters_per_page": dataset.source_characters / page_count
                                                  if page_count else None,
                    "mean_page_characters": (stats["page_chars"] / page_count
                                             if page_count and "page_chars" in stats else None),
                    "engine_stats": stats,
                    "database_and_wal_bytes_after_ingest": sum(
                        item.stat().st_size for item in Path(directory).glob(f"{segmentation}.sqlite3*")
                        if item.is_file()),
                })
                for budget in budgets:
                    for strategy in strategies:
                        configuration = _measure_configuration(
                            book, dataset, segmentation, strategy, budget,
                            repeats, limit, measure_cache)
                        result["configurations"].append(configuration)
                        metrics = configuration["metrics"]
                        print(f"{segmentation:8s} {strategy:4s} budget={budget:5d} "
                              f"recall={metrics['evidence_recall']:.3f} "
                              f"complete={metrics['complete_evidence_rate']:.3f} "
                              f"p95={configuration['uncached_latency']['p95_ms']:.3f} ms",
                              file=sys.stderr, flush=True)
            finally:
                book.close()
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["runtime"]["engine_python_source_sha256_after"] = engine_source_hash(source_root)
    result["runtime"]["engine_source_unchanged_during_run"] = (
        result["runtime"]["engine_python_source_sha256"]
        == result["runtime"]["engine_python_source_sha256_after"])
    return result


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _decimal(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def to_markdown(report: dict[str, Any]) -> str:
    """Render observed values without asserting that one method must win."""
    dataset, params = report["dataset"], report["parameters"]
    lines = [
        "# AI-Memory-Book synthetic retrieval benchmark", "",
        "This is a reproducible local microbenchmark on generated conversations. "
        "It is **not** a benchmark of claude-mem, billion-context, ai-memory, "
        "or real user workloads, and it does not measure LLM answer quality.", "",
        "## Dataset and runtime", "",
        f"- Dataset: version {dataset['version']}, `{dataset['split']}`, seed `{dataset['seed']}`.",
        f"- Fingerprint: `{dataset['sha256']}`.",
        f"- Size: {dataset['projects']} projects, {dataset['sessions']} sessions, "
        f"{dataset['turns']} user turns, {dataset['source_characters']:,} source characters, "
        f"{dataset['queries']} queries ({dataset['answerable_queries']} answerable).",
        f"- Python {report['runtime']['python']}; SQLite {report['runtime']['sqlite']}; "
        f"{report['runtime']['platform']}.",
        f"- Engine Python source fingerprint: `{report['runtime'].get('engine_python_source_sha256', 'not recorded in the earliest development run')}`.",
        f"- Run: {report['started_at_utc']} to {report['finished_at_utc']}.",
        f"- Result limit: {params['limit']}; uncached repeats: {params['repeats']}; "
        f"page settings: max={params['max_page_chars']}, min={params['min_page_chars']}, "
        f"similarity={params['similarity_threshold']}.", "",
        "Task identifiers are supplied input metadata. Every configuration uses "
        "the same source records, tokenizer/search implementation, project scope "
        "and context budget. Source evidence, rather than generated page IDs, "
        "determines correctness.", "",
        "Both ranking strategies use the same metadata-aware FTS index. `book` "
        "adds soft directory-overlap reranking to `flat`; this experiment does "
        "not compare hierarchy against an index stripped of all directory metadata.", "",
        "## Main results", "",
        "Recall counts required facts that are present in the actual returned "
        "context **and** traceable to the expected original session and turn. "
        "Complete means all required facts for an answerable query were returned. "
        "Mean characters includes unanswerable queries and citation metadata.", "",
        "| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if report.get("release_stage"):
        provenance = [f"**Release stage:** {report['release_stage']}.", ""]
        if report.get("source_integrity_note"):
            provenance += [report["source_integrity_note"], ""]
        elif report.get("release_verification"):
            check = report["release_verification"]
            provenance += [
                f"Fresh Python process: {check['fresh_python_process']}; "
                f"package source unchanged during run: "
                f"{report['runtime'].get('engine_source_unchanged_during_run')}; "
                f"per-query quality differences from pre-release: "
                f"{check['quality_differences_from_pre_release']}.", ""]
        lines[4:4] = provenance
    for config in report["configurations"]:
        metrics, latency = config["metrics"], config["uncached_latency"]
        lines.append(f"| {config['segmentation']} | {config['strategy']} | {config['budget_chars']} "
                     f"| {_percent(metrics['evidence_recall'])} | {_percent(metrics['complete_evidence_rate'])} "
                     f"| {_decimal(metrics['mrr'], 3)} | {_decimal(metrics['mean_context_characters'], 0)} "
                     f"| {_decimal(latency['p50_ms'], 3)} | {_decimal(latency['p95_ms'], 3)} |")
    lines += ["", "## Failure diagnostics", "",
              "A nonempty result for an unanswerable question is a retrieval "
              "diagnostic, not proof that a model would fabricate an answer. "
              "Stale-only means old evidence was returned without current "
              "evidence for a current-state query.", "",
              "| Segmentation | Retrieval | Budget | Unanswerable nonempty | Latest stale-only | Old before current | Budget violations | Size mismatches |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for config in report["configurations"]:
        metrics = config["metrics"]
        lines.append(f"| {config['segmentation']} | {config['strategy']} | {config['budget_chars']} "
                     f"| {_percent(metrics['unanswerable_nonempty_rate'])} "
                     f"| {_percent(metrics['latest_stale_only_rate'])} "
                     f"| {_percent(metrics['latest_stale_before_current_rate'])} "
                     f"| {metrics['budget_violations']} | {metrics['context_size_mismatches']} |")
    lines += ["", "## Evidence recall by category", "",
              "The same category is measured for all configurations; low lexical "
              "overlap and short follow-ups are retained even when they fail.", "",
              "| Segmentation | Retrieval | Budget | Category | Queries | Evidence recall | Complete |",
              "|---|---|---:|---|---:|---:|---:|"]
    for config in report["configurations"]:
        for category, metrics in config["by_category"].items():
            if not metrics["answerable_queries"]:
                continue
            lines.append(f"| {config['segmentation']} | {config['strategy']} | {config['budget_chars']} "
                         f"| {category} | {metrics['queries']} | {_percent(metrics['evidence_recall'])} "
                         f"| {_percent(metrics['complete_evidence_rate'])} |")
    lines += ["", "## Ingestion and storage", "",
              "Mean page characters uses the engine's stored page text, including "
              "speaker labels but excluding separately stored title metadata. File "
              "size includes SQLite WAL/SHM files present after ingestion.", "",
              "| Segmentation | Pages | Mean page chars | Ingest ms | Sessions/sec | DB + WAL bytes |",
              "|---|---:|---:|---:|---:|---:|"]
    for ingest in report["ingestion"]:
        lines.append(f"| {ingest['segmentation']} | {ingest['pages']} "
                     f"| {_decimal(ingest.get('mean_page_characters'), 0)} "
                     f"| {_decimal(ingest['elapsed_ms'])} | {_decimal(ingest['sessions_per_second'])} "
                     f"| {ingest['database_and_wal_bytes_after_ingest']:,} |")
    lines += ["", "## Cache and measurement boundaries", "",
              "Main latency measurements disable the result cache. They run in "
              "one Python process; SQLite and OS page caches are not flushed. "
              "The first-query column is therefore **not a cold-process or "
              "cold-OS-cache benchmark**. The hot-cache test immediately repeats "
              "each query and represents a best-case cache hit, not typical traffic.", "",
              "| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for config in report["configurations"]:
        cache = config["immediately_repeated_cache_latency"] or {}
        lines.append(f"| {config['segmentation']} | {config['strategy']} | {config['budget_chars']} "
                     f"| {_decimal(config['first_query_same_process_ms'], 3)} "
                     f"| {_decimal(cache.get('p50_ms'), 3)} | {_decimal(cache.get('p95_ms'), 3)} "
                     f"| {_percent(config['immediately_repeated_cache_hit_rate'])} |")
    lines += ["", "## Interpretation limits", ""]
    lines.extend("- " + item for item in report["methodology"]["limitations"])
    lines += ["", "All timing values above are measured, not projected. The JSON "
              "companion includes per-query evidence ranks, references, categories, "
              "and measured latency distributions for inspection.", ""]
    if report.get("artifacts"):
        files = report["artifacts"]
        lines += [f"[Complete raw results (gzip)]({files['full_report']}) · "
                  f"[Compact machine-readable summary]({files['summary']})", ""]
    return "\n".join(lines)


def write_report(report: dict[str, Any], prefix: Path) -> dict[str, Path]:
    """Write complete compressed evidence and a compact derivative summary.

    Gzip headers have no filename or wall-clock mtime. The complete report is
    verified by decompression before it is written; no per-query evidence is
    dropped to save space.
    """
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {"full_report": Path(str(prefix) + ".json.gz"),
             "summary": Path(str(prefix) + ".summary.json"),
             "markdown": Path(str(prefix) + ".md")}
    report["artifacts"] = {key: path.name for key, path in paths.items()}
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9,
                       fileobj=buffer, mtime=0) as archive:
        archive.write(raw)
    compressed = buffer.getvalue()
    if gzip.decompress(compressed) != raw:
        raise RuntimeError("compressed report failed round-trip validation")
    summary = {key: value for key, value in report.items() if key != "configurations"}
    summary["configurations"] = [{key: value for key, value in config.items()
                                  if key != "query_results"}
                                 for config in report["configurations"]]
    summary["full_report_uncompressed_sha256"] = hashlib.sha256(raw).hexdigest()
    paths["full_report"].write_bytes(compressed)
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["markdown"].write_text(to_markdown(report), encoding="utf-8")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("development", "heldout"), default="heldout")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--projects", type=int, default=8)
    parser.add_argument("--budget-chars", type=int, nargs="+", default=[4000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-page-chars", type=int, default=900)
    parser.add_argument("--min-page-chars", type=int, default=400)
    parser.add_argument("--similarity-threshold", type=float, default=.12)
    parser.add_argument("--segmentation", choices=SEGMENTATIONS, nargs="+", default=list(SEGMENTATIONS),
                        help="Filter configurations for development sweeps; default tests all")
    parser.add_argument("--strategy", choices=STRATEGIES, nargs="+", default=list(STRATEGIES))
    parser.add_argument("--short-sessions", action="store_true",
                        help="Reproduce the original v1 short-session corpus instead of v2")
    parser.add_argument("--no-cache-measurement", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/benchmark"),
                        help="Output prefix; writes PREFIX.json.gz, PREFIX.summary.json and PREFIX.md")
    parser.add_argument("--dump-dataset", type=Path,
                        help="Optionally write synthetic sessions and independent labels as JSON")
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else (17 if args.split == "development" else 29)
    if args.dump_dataset:
        dataset = generate_dataset(seed, args.split, args.projects,
                                   include_long_sessions=not args.short_sessions)
        args.dump_dataset.parent.mkdir(parents=True, exist_ok=True)
        args.dump_dataset.write_text(json.dumps({
            "description": dataset.description(), "sessions": dataset.sessions,
            "queries": [asdict(case) for case in dataset.queries],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = run(seed=seed, split=args.split, projects=args.projects,
                 budgets=tuple(args.budget_chars), repeats=args.repeats, limit=args.limit,
                 max_page_chars=args.max_page_chars, min_page_chars=args.min_page_chars,
                 similarity_threshold=args.similarity_threshold,
                 measure_cache=not args.no_cache_measurement,
                 include_long_sessions=not args.short_sessions,
                 segmentations=tuple(args.segmentation), strategies=tuple(args.strategy))
    paths = write_report(report, args.output)
    print("Wrote " + ", ".join(str(path) for path in paths.values()), file=sys.stderr)
    return 1 if any(config["metrics"]["budget_violations"]
                    or config["metrics"]["context_size_mismatches"]
                    for config in report["configurations"]) or not report["runtime"]["engine_source_unchanged_during_run"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
