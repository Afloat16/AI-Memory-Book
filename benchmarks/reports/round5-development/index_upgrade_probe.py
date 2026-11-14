"""One disclosed first-open upgrade observation per old cohort and source.

No retrieval is timed. Fresh copied files share warm OS caches; this is not an
OS-cold or repeated-sample speed claim. Never opens the source archive writable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time


TABLES = ("meta", "projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache")


def logical(database):
    values = {}
    for name in TABLES:
        rows = database.execute(f"SELECT * FROM {name}").fetchall()
        values[name] = sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False))
    for name in ("pages_fts", "pages_stem_fts"):
        values[name] = database.execute(f"SELECT rowid,* FROM {name} ORDER BY rowid").fetchall()
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def inspect(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as database:
        index_bytes = database.execute("SELECT coalesce(sum(pgsize),0) FROM dbstat WHERE name='pages_recall_metadata'").fetchone()[0]
        return {"logical_sha256": logical(database),
                "revision": int(database.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]),
                "schema_version": database.execute("PRAGMA user_version").fetchone()[0],
                "index_bytes": index_bytes, "file_bytes": path.stat().st_size,
                "fresh_sqlite_connection_cache_size": database.execute("PRAGMA cache_size").fetchone()[0]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--candidate-source", type=Path)
    parser.add_argument("--db-directory", type=Path)
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Do not overwrite a prior observation")
    if args.worker:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from benchmarks.run import engine_source_hash
        sys.path.insert(0, str(args.source.resolve()))
        if engine_source_hash(args.source / "memory_book") != args.source_sha:
            raise RuntimeError("Source differs from the requested runtime")
        from memory_book import MemoryBook
        started = time.perf_counter_ns()
        book = MemoryBook(args.database, cache_size=0)
        open_ms = (time.perf_counter_ns() - started) / 1e6
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        active_cache_size = book.db.execute("PRAGMA cache_size").fetchone()[0]
        started = time.perf_counter_ns()
        book.close()
        close_ms = (time.perf_counter_ns() - started) / 1e6
        if engine_source_hash(args.source / "memory_book") != args.source_sha:
            raise RuntimeError("Source changed during observation")
        args.output.write_text(json.dumps({"first_open_ms": open_ms,
            "close_ms": close_ms, "process_peak_rss_after_open_bytes": peak_rss,
            "memory_book_connection_cache_size": active_cache_size,
            "after": inspect(args.database.resolve())}, indent=2) + "\n")
        return
    args.state.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benchmarks.run import engine_source_hash
    sources = {label: engine_source_hash(source / "memory_book")
               for label, source in (("baseline", args.baseline_source), ("candidate", args.candidate_source))}
    report = {"schema_version": 1, "status": "running", "retrieval_calls": 0,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": __doc__, "source_runtime_sha256": sources,
        "observations": []}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for cohort in ("synthetic61", "public1015"):
        original = (args.db_directory / (cohort + ".db")).resolve()
        before = inspect(original)
        if before["index_bytes"]:
            raise RuntimeError("Source archive already contains the candidate index")
        for label, source in (("baseline", args.baseline_source), ("candidate", args.candidate_source)):
            target = (args.state / (cohort + "-" + label + ".db")).resolve()
            output = args.state / (cohort + "-" + label + ".json")
            shutil.copy2(original, target)
            subprocess.run([sys.executable, __file__, "--worker", "--source", str(source.resolve()),
                "--source-sha", sources[label],
                "--database", str(target), "--output", str(output)], check=True)
            value = json.loads(output.read_text())
            if value["after"]["logical_sha256"] != before["logical_sha256"]:
                raise RuntimeError("Index preparation changed logical contents")
            report["observations"].append({"cohort": cohort, "label": label, "before": before, **value})
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        if inspect(original) != before:
            raise RuntimeError("Source archive changed during the observation")
    report["status"] = "completed"
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
