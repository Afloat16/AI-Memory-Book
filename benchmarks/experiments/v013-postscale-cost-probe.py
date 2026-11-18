"""Small, source-bound cost diagnosis after longitudinal run 1.

This is instrumented development evidence, not a throughput/latency acceptance
experiment. Real ingest creates at most 2,048 pages in memory. No gold,
production route, scoring rule or frozen scale protocol is changed. Original
responses (including failures) and intentionally unhelpful SQL variants remain.
"""
from __future__ import annotations

import argparse
from collections import Counter
import cProfile
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import sqlite3
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from benchmarks import v013_scale as scale, v013_workload as gen
from scripts.validate_v011_revision_recovery import source_identity

PROTOCOL_COMMIT = "b3fd165cb632c439ff28873fdba7f33e9d258178"
SCENARIOS = (
    ("core128", 0, 0, "clustered"),
    ("foreign1024", 896, 0, "clustered"),
    ("foreign2048", 1920, 0, "clustered"),
    ("mixed2048", 960, 960, "clustered"),
    ("interleaved2048", 960, 960, "interleaved"),
)
CASE_IDS = ("routing-archive:current", "routing-archive:historical",
            "routing-archive:directory", "routing-core:current", "ranking-next:directory")
WARM_REPEATS = 20


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def profile(book, call):
    traced, progress = Counter(), [0]
    def trace(statement):
        traced[statement] += 1
    def step():
        progress[0] += 1
        return 0
    book.db.set_trace_callback(trace)
    book.db.set_progress_handler(step, 100)
    profiler = cProfile.Profile()
    started = time.perf_counter_ns()
    raw = None
    error = None
    try:
        raw = profiler.runcall(call)
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        elapsed = time.perf_counter_ns() - started
        book.db.set_trace_callback(None)
        book.db.set_progress_handler(None, 0)
    statistics = pstats.Stats(profiler).stats
    rows = [{"file": file, "line": line, "function": name, "primitive_calls": cc,
             "calls": nc, "self_seconds": own, "cumulative_seconds": total}
            for (file, line, name), (cc, nc, own, total, _) in statistics.items()]
    result = {"profiled_wall_ns": elapsed, "error": error,
              "sqlite_vm_progress_interval": 100, "sqlite_vm_progress_callbacks": progress[0],
              "top_cumulative": sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:25],
              "top_self": sorted(rows, key=lambda row: row["self_seconds"], reverse=True)[:20],
              "sqlite_trace_counts": [{"statement": sql, "count": count} for sql, count in traced.items()]}
    return raw, result


def micro_sql(book, case):
    from memory_book import directory
    from memory_book.text import query_terms
    expression = "{title question directory} : (" + " OR ".join(
        '"' + token.replace('"', '""') + '"' for token in query_terms(case["query"])) + ")"
    where = "pages_fts MATCH ? AND p.project_id=?"
    parameters = [expression, case["project"]]
    bounds = getattr(book, "_project_rowid_bounds", lambda project: None)(case["project"])
    active_where = where + (" AND pages_fts.rowid BETWEEN ? AND ?" if bounds else "")
    active_parameters = parameters + (list(bounds) if bounds else [])
    active = directory._ranked_hits(active_where)
    variants = {
        "production_ranked_hits": (active, active_parameters),
        "same_cursor_without_bm25_diagnostic_only":
            (active.replace("bm25(pages_fts,2.0,1.0,0.0,4.0)", "0.0"), active_parameters),
        "scope_in_point_probes": (directory._ranked_hits(where +
            " AND pages_fts.rowid IN (SELECT rid FROM pages WHERE project_id=?)"), parameters + [case["project"]]),
        "scope_in_single_scan": (directory._ranked_hits(where +
            " AND +pages_fts.rowid IN (SELECT rid FROM pages WHERE project_id=?)"), parameters + [case["project"]]),
    }
    output = []
    for name, (sql, params) in variants.items():
        query_plan = [list(row) for row in book.db.execute("EXPLAIN QUERY PLAN " + sql, params)]
        raw, timing = profile(book, lambda: [list(row) for row in book.db.execute(sql, params)])
        output.append({"variant": name, "sql": sql, "parameters": params,
                       "query_plan": query_plan, "rows": raw, **timing})
    expected = sorted(output[0]["rows"]) if output[0]["rows"] is not None else None
    for row in output:
        if "diagnostic_only" not in row["variant"]:
            row["exact_global_bm25_rows_equal_to_original"] = (
                row["rows"] is not None and sorted(row["rows"]) == expected)
    return {"project_bounds": bounds, "variants": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = source_identity(source, args.commit)
    MemoryBook, imported = scale.load_runtime(source, "native")
    inputs = scale.frozen_identity(PROTOCOL_COMMIT)
    configuration = scale.plan()
    cases = {case["id"]: case for case in gen.cases()}
    report = {"schema": "v013-postscale-small-cost-probe-v1", "status": "running",
              "scope": "Instrumented diagnosis only. Not the formal scale matrix or a latency acceptance claim.",
              "started_at": datetime.now(timezone.utc).isoformat(), "source_before": before,
              "imported": imported, "frozen_inputs": inputs,
              "probe_sha256": sha(Path(__file__).read_bytes()), "python": sys.version,
              "sqlite": sqlite3.sqlite_version, "scenarios": [], "api_invocations": 0}
    write(output / "report.json", report)
    raw_path = output / "responses.jsonl.gz"
    try:
        with gzip.GzipFile(filename=str(raw_path), mode="xb", mtime=0) as responses:
            for name, foreign, own, layout in SCENARIOS[:1] if args.core_only else SCENARIOS:
                spec = {"id": name, "foreign_pages": foreign, "own_pages": own,
                        "total_pages": 128 + foreign + own, "layout": layout, "revision": 0, "shift_days": 0}
                stage = {"spec": spec, "status": "building", "observations": []}
                report["scenarios"].append(stage)
                write(output / "report.json", report)
                with MemoryBook(":memory:", segmentation="turn", max_page_chars=900,
                                min_page_chars=0, cache_size=128) as book:
                    ingestion = hashlib.sha256()
                    calls = 0
                    for session in gen.sessions(spec):
                        ingestion.update(gen.encoded(session) + b"\n")
                        saved = book.ingest(session)
                        if saved["pages"] != len(session["messages"]) // 2:
                            raise ValueError("Real ingest did not create the expected complete turns")
                        calls += 1
                    actual_pages = book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
                    if actual_pages != spec["total_pages"]:
                        raise ValueError("Real page count differs from diagnosis specification")
                    stage.update(status="profiling", actual_pages=actual_pages, ingest_calls=calls,
                                 ingestion_order_sha256=ingestion.hexdigest(),
                                 fingerprint=scale.source_fingerprint(book.db))
                    for identity in CASE_IDS:
                        case = cases[identity]
                        book.db.execute("DELETE FROM recall_cache")
                        def invoke():
                            if case["surface"] == "directory":
                                return scale.directory_read(book, case["query"], case["project"], configuration["directory"])
                            return book.recall(case["query"], project=case["project"], budget_chars=2400, limit=5,
                                               strategy="book", temporal="auto", coverage=False, semantic=False, use_cache=True)
                        raw, costs = profile(book, invoke)
                        report["api_invocations"] += 1
                        normalized = raw[0] if case["surface"] == "directory" and raw is not None else raw
                        scored = scale.score(normalized, case, spec) if normalized is not None else None
                        record = {"scenario": name, "case": identity, "mode": "cold-with-cache-write",
                                  "response": raw, "score": scored, "error": costs["error"]}
                        responses.write(gen.encoded(record) + b"\n")
                        responses.flush()
                        stage["observations"].append({"case": identity, "score": scored, **costs})
                    case = cases["routing-archive:current"]
                    book.recall(case["query"], project=case["project"], use_cache=True)
                    report["api_invocations"] += 1
                    collected = []
                    def warm():
                        for repeat in range(WARM_REPEATS):
                            response = book.recall(case["query"], project=case["project"], use_cache=True)
                            if not response["cache_hit"]:
                                raise ValueError("Expected a genuine warm result-cache hit")
                            collected.append(response)
                    _, warm_cost = profile(book, warm)
                    report["api_invocations"] += len(collected)
                    for repeat, response in enumerate(collected):
                        responses.write(gen.encoded({"scenario": name, "case": case["id"], "mode": "warm",
                                                     "repeat": repeat, "response": response}) + b"\n")
                    payload = book.db.execute("SELECT payload FROM recall_cache ORDER BY touched_ns DESC LIMIT 1").fetchone()[0]
                    stage["warm"] = {"case": case["id"], "repeats": len(collected),
                                     "cached_payload_utf8_bytes": len(payload.encode()), **warm_cost}
                    stage["sql_micro"] = micro_sql(book, cases["routing-archive:directory"])
                    stage["source_tables_unchanged_after_reads"] = (scale.source_fingerprint(book.db) == stage["fingerprint"])
                    stage["status"] = "completed"
                    write(output / "report.json", report)
        report["source_after"] = source_identity(source, args.commit)
        if before != report["source_after"] or scale.frozen_identity(PROTOCOL_COMMIT) != inputs:
            raise ValueError("Runtime or frozen evaluator changed during the probe")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error),
                                              "traceback": traceback.format_exc()})
    finally:
        if raw_path.exists():
            raw = raw_path.read_bytes()
            report["raw_archive"] = {"file": raw_path.name, "bytes": len(raw), "sha256": sha(raw)}
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(output / "report.json", report)
    print(json.dumps({"status": report["status"], "api_invocations": report["api_invocations"], "output": str(output)}))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
