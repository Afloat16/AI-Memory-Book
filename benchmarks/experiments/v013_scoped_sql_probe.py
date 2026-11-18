"""Development SQL diagnosis on <=1920 pages; not a formal performance claim.

Replay the unchanged runtime's SQL, then inspect result-equivalent join/range
variants without editing runtime. A separate one-row BM25/no-rank comparison
isolates auxiliary scoring work; that comparison is deliberately NOT a ranking
replacement and is not eligible to be a product candidate.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

from v013_scoped_work_probe import MemoryBook, ROOT, inputs


def measure(db, sql, repeats=7):
    rows = None
    timings = []
    for _ in range(repeats):
        before = time.perf_counter_ns()
        actual = [list(row) for row in db.execute(sql)]
        timings.append((time.perf_counter_ns() - before) / 1e6)
        if rows is not None:
            assert rows == actual
        rows = actual
    calls = []
    instructions = [0]

    def progress():
        instructions[0] += 100
        return 0

    db.set_progress_handler(progress, 100)
    db.set_trace_callback(calls.append)
    assert [list(row) for row in db.execute(sql)] == rows
    db.set_progress_handler(None, 0)
    db.set_trace_callback(None)
    return {"sql": sql, "rows": rows, "elapsed_ms": timings,
            "median_elapsed_ms": statistics.median(timings),
            "observed_vm_instruction_lower_bound": instructions[0],
            "observed_trace_count": len(calls),
            "plan": [list(row) for row in db.execute("EXPLAIN QUERY PLAN " + sql)]}


def run(output, baseline_report):
    output.mkdir(parents=True, exist_ok=False)
    baseline = json.loads(baseline_report.read_text())
    cells = []
    for layout in ("contiguous", "interleaved"):
        for foreign_pages in (0, 480, 1800):
            original = next(cell for cell in baseline["cells"]
                            if cell["layout"] == layout and cell["foreign_pages"] == foreign_pages)
            with tempfile.TemporaryDirectory(prefix="sql-pilot-", dir=output.parent) as temporary:
                path = Path(temporary) / "memory.db"
                records = list(inputs(foreign_pages, layout))
                input_bytes = json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
                assert hashlib.sha256(input_bytes).hexdigest() == original["input_sha256"]
                with MemoryBook(path, cache_size=0) as book:
                    for record in records:
                        assert book.ingest(record)["pages"] == 1
                    assert book.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] <= 2000
                    lo, hi = book.db.execute(
                        "SELECT MIN(rid),MAX(rid) FROM pages WHERE project_id='target'").fetchone()
                    cell = {"layout": layout, "foreign_pages": foreign_pages,
                            "pages": len(records), "input_sha256": original["input_sha256"],
                            "target_rowid_bounds": [lo, hi], "queries": {}}
                    for name, sql in (
                        ("directory_count", original["operations"]["directory"]["fts_query_plans"][0]["sql"]),
                        ("directory_chapters", original["operations"]["directory"]["fts_query_plans"][1]["sql"]),
                        ("directory_preview", original["operations"]["directory"]["fts_query_plans"][2]["sql"]),
                        ("chronology", original["operations"]["current"]["fts_query_plans"][2]["sql"]),
                    ):
                        base = measure(book.db, sql)
                        variants = {"baseline": base}
                        if name == "chronology":
                            driven = sql.replace("FROM pages_fts JOIN pages p ON p.rid=pages_fts.rowid",
                                                 "FROM pages p INDEXED BY pages_chapter CROSS JOIN pages_fts ON pages_fts.rowid=p.rid")
                            bounded = sql.replace(" ORDER BY", f" AND pages_fts.rowid BETWEEN {lo} AND {hi} ORDER BY", 1)
                        else:
                            index = "pages_chapter" if name == "directory_preview" else "pages_project"
                            driven = sql.replace("FROM pages_fts\nCROSS JOIN pages p ON p.rid=pages_fts.rowid",
                                                 f"FROM pages p INDEXED BY {index}\nCROSS JOIN pages_fts ON pages_fts.rowid=p.rid")
                            bounded = (sql + f" AND pages_fts.rowid BETWEEN {lo} AND {hi}" if name == "directory_count"
                                       else sql.replace(" LIMIT -1", f" AND pages_fts.rowid BETWEEN {lo} AND {hi} LIMIT -1", 1))
                        assert driven != sql and bounded != sql
                        for key, candidate in (("scoped_pages_drive", driven), ("project_bounds", bounded)):
                            variants[key] = measure(book.db, candidate)
                            variants[key]["equal_to_baseline"] = variants[key]["rows"] == base["rows"]
                            assert variants[key]["equal_to_baseline"], (name, key)
                        cell["queries"][name] = variants
                    # Same single target row at every archive size. Equality here
                    # concerns rowid only; the no-BM25 expression is diagnostic.
                    expression = '("production" OR "retry" OR "limit" OR "retrylimit") AND body : ("production" OR "retry" OR "limit" OR "retrylimit")'
                    where = " FROM pages_fts WHERE pages_fts MATCH '" + expression + f"' AND rowid={lo}"
                    cell["bm25_one_row_diagnostic"] = {
                        "rank": measure(book.db, "SELECT rowid,bm25(pages_fts,2.0,2.0,1.0,0.25)" + where, 101),
                        "no_rank": measure(book.db, "SELECT rowid,0.0" + where, 101),
                        "not_a_product_candidate": True,
                    }
                    assert cell["bm25_one_row_diagnostic"]["rank"]["rows"][0][0] == lo
                    cells.append(cell)
                    print(json.dumps({"layout": layout, "foreign": foreign_pages,
                                      "query_medians_ms": {q: {k: round(v["median_elapsed_ms"], 6)
                                                               for k, v in variants.items()}
                                                           for q, variants in cell["queries"].items()},
                                      "one_row_ms": {k: round(cell["bm25_one_row_diagnostic"][k]["median_elapsed_ms"], 6)
                                                     for k in ("rank", "no_rank")}}), flush=True)
    report = {"status": "completed-development-diagnostic", "schema_version": 1,
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "baseline_report": str(baseline_report.relative_to(ROOT)),
              "baseline_report_sha256": hashlib.sha256(baseline_report.read_bytes()).hexdigest(),
              "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "runtime_sha256": baseline["runtime_sha256"], "python": sys.version,
              "sqlite": sqlite3.sqlite_version, "cells": cells,
              "limits": ["Authored and inspected development pilot; not a formal benchmark.",
                         "Timing occurs without trace/VM observer; separate observed replay retains instruction and trace counts.",
                         "SQLite connection and OS caches are warm; first samples and all repeats retained.",
                         "VM counts do not capture all C-level FTS work. One-row BM25 comparison is diagnostic only.",
                         "No runtime/schema/index modifications; all candidate SQL outputs exactly compared to the original query."]}
    for relative, digest in report["runtime_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    raw = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
    (output / "report.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    (output / "receipt.json").write_text(json.dumps({"status": report["status"], "cells": len(cells),
                                                   "report_sha256": hashlib.sha256(raw).hexdigest()}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.baseline_report.resolve())
