"""Profile fixed old cohorts and preserve complete payload hashes; no speed gate.

This is a development diagnostic, not a formal performance comparison or a
fresh quality evaluation. Source text is never written to the report.
"""
from __future__ import annotations

import argparse
import cProfile
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pstats
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = (
    ("native-char4000", {"budget_chars": 4000}),
    ("native-token512", {"budget_chars": 8000, "budget_tokens": 512}),
    ("native-token1024", {"budget_chars": 8000, "budget_tokens": 1024}),
    ("native-token2048", {"budget_chars": 8000, "budget_tokens": 2048}),
)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def save(path, report):
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--locomo-path", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve an existing development profile")
    args.state.mkdir(parents=True, exist_ok=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(args.source.resolve()), str(ROOT)]
    import memory_book
    from benchmarks.run import engine_source_hash
    from scripts.benchmark_default_recall import dataset
    from memory_book.token_budget import TokenCounter
    package = Path(memory_book.__file__).resolve().parent
    if package != args.source.resolve() / "memory_book":
        raise ValueError("Imported another runtime")
    if engine_source_hash(package) != args.expected_source_sha:
        raise ValueError("Runtime hash does not match requested source")
    TokenCounter("cl100k_base").count("Prepare the reference tokenizer before profiling.")
    report = {
        "schema_version": 1, "status": "running", "label": args.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_source_sha256": args.expected_source_sha,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Old-data development profile and full payload hash regression only; cProfile overhead is included. No formal speed or new quality claim.",
        "settings": {"cache_size": 0, "use_cache": False, "limit": 5,
                     "semantic": False, "coverage": False, "tokenizer": "cl100k_base",
                     "query_shuffle_seed": 41061},
        "expected_calls": 4732, "attempted_calls": 0, "completed_calls": 0,
        "cells": [],
    }
    save(args.output, report)
    try:
        for cohort in ("synthetic61", "public1015"):
            data = dataset(cohort, args.locomo_path)
            queries = list(data.queries)
            random.Random(41061).shuffle(queries)
            with memory_book.MemoryBook(args.state / (cohort + ".db"), cache_size=0) as book:
                for session in data.sessions:
                    book.ingest(session)
                for config_id, options in CONFIGS:
                    cell = {"cohort": cohort, "configuration": config_id,
                            "dataset_sha256": data.fingerprint,
                            "queries": len(queries), "status": "running", "rows": []}
                    report["cells"].append(cell)
                    save(args.output, report)
                    profile = cProfile.Profile()
                    for case in queries:
                        report["attempted_calls"] += 1
                        profile.enable()
                        try:
                            result = book.recall(case.query, project=case.project,
                                use_cache=False, **options)
                        finally:
                            profile.disable()
                        result.pop("latency_ms")
                        cell["rows"].append({"query_id": case.id,
                            "non_timing_payload_sha256": fingerprint(result)})
                        report["completed_calls"] += 1
                    stats = pstats.Stats(profile)
                    functions = []
                    for (path, line, name), (primitive, total, own, cumulative, _) in stats.stats.items():
                        if "/memory_book/" not in path and path != "~":
                            continue
                        shown = "src/memory_book/" + path.split("/memory_book/", 1)[1] if "/memory_book/" in path else path
                        functions.append({"path": shown, "line": line, "function": name,
                            "primitive_calls": primitive, "total_calls": total,
                            "self_seconds": own, "cumulative_seconds": cumulative})
                    cell.update(status="completed", profile_total_seconds=stats.total_tt,
                        top_self=sorted(functions, key=lambda x: x["self_seconds"], reverse=True)[:30],
                        top_cumulative=sorted(functions, key=lambda x: x["cumulative_seconds"], reverse=True)[:30])
                    save(args.output, report)
                    print(json.dumps({"cohort": cohort, "configuration": config_id,
                        "calls": len(cell["rows"]), "profile_seconds": stats.total_tt}), flush=True)
        if engine_source_hash(package) != args.expected_source_sha:
            raise ValueError("Runtime source changed during development profile")
        if report["completed_calls"] != report["expected_calls"]:
            raise ValueError("Development matrix incomplete")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(args.output, report)


if __name__ == "__main__":
    main()
