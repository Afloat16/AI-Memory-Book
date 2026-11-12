"""Measure one-time index upgrades and verify that archived source bytes survive.

The baseline and candidate are imported in separate worker processes. Only
statistics and hashes are published; temporary databases and source text remain
inside an automatically cleaned temporary directory. This is not query latency.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance, latency_summary, load_dataset


SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _canonical(value) -> bytes:
    def encode_binary(item):
        if isinstance(item, bytes):
            return {"sqlite_blob_base64": base64.b64encode(item).decode("ascii")}
        raise TypeError(f"Unsupported SQLite value type: {type(item).__name__}")

    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=encode_binary).encode("utf-8")


def _rows_fingerprint(connection: sqlite3.Connection, table: str,
                      columns: tuple[str, ...] | None = None) -> dict:
    """Hash individually encoded rows in a stable order, never publish rows."""
    if columns is None:
        columns = tuple(row[1] for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(table)})"))
    if not columns:
        raise RuntimeError(f"Source table is absent or has no columns: {table}")
    names = ",".join(map(_quote_identifier, columns))
    digest = hashlib.sha256(_canonical(list(columns)) + b"\n")
    count = 0
    for row in connection.execute(
            f"SELECT {names} FROM {_quote_identifier(table)} ORDER BY {names}"):
        digest.update(hashlib.sha256(_canonical(list(row))).digest())
        count += 1
    return {"columns": list(columns), "rows": count, "sha256": digest.hexdigest()}


def database_snapshot(connection: sqlite3.Connection) -> dict:
    """Exclude mutable metadata, caches and derived FTS data from source hashes."""
    tables = {name: _rows_fingerprint(connection, name) for name in SOURCE_TABLES}
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    revision = int(connection.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {
        "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
        "application_id": connection.execute("PRAGMA application_id").fetchone()[0],
        "revision": revision,
        "page_count": page_count,
        "page_size": page_size,
        "logical_database_bytes": page_count * page_size,
        "source_tables": tables,
        "source_tables_sha256": hashlib.sha256(_canonical(tables)).hexdigest(),
        "page_ids_content_source_refs": _rows_fingerprint(
            connection, "pages", ("id", "content", "source_refs")),
        "cache_rows": connection.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0],
        "valid_cache_rows": connection.execute(
            "SELECT COUNT(*) FROM recall_cache WHERE revision=?", (revision,)).fetchone()[0],
        "index_rows": {name: connection.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(name)}").fetchone()[0]
            for name in ("pages_fts", "pages_stem_fts") if name in names},
    }


def assert_source_preserved(before: dict, after: dict) -> None:
    for field in ("source_tables", "source_tables_sha256", "page_ids_content_source_refs"):
        if before[field] != after[field]:
            raise RuntimeError(f"Upgrade changed archived source identity: {field}")
    if before["application_id"] != after["application_id"]:
        raise RuntimeError("Upgrade changed the database application identity")


def _checkpoint(connection: sqlite3.Connection) -> None:
    busy, _, _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if busy:
        raise RuntimeError("Database checkpoint remained busy; refusing to copy an incomplete database")


def _load_engine(source: Path):
    source = source.resolve()
    if "memory_book" in sys.modules:
        raise RuntimeError("MemoryBook was imported before worker source selection")
    sys.path.insert(0, str(source))
    import memory_book
    source_root = Path(memory_book.__file__).resolve().parent
    if source_root != source / "memory_book":
        raise RuntimeError("Imported MemoryBook does not match the requested source directory")
    return memory_book, source_root, engine_source_hash(source_root)


def _engine_identity(module, source_root: Path, before: str, label: str) -> dict:
    after = engine_source_hash(source_root)
    if before != after:
        raise RuntimeError("Engine source changed during upgrade measurement")
    return {"label": label, "engine_version": module.__version__,
            "source_sha256_before": before, "source_sha256_after": after,
            "source_unchanged": True, "source_provenance": checkout_provenance(source_root)}


def prepare_baseline(args) -> dict:
    module, source_root, source_hash = _load_engine(args.engine_src)
    dataset = load_dataset(args.corpus, args.seed, args.split, args.projects,
                           args.locomo_path, args.max_queries)
    if not dataset.sessions:
        raise RuntimeError("Upgrade cost measurement requires at least one source session")
    started = time.perf_counter_ns()
    book = module.MemoryBook(args.database, max_page_chars=900, cache_size=128)
    create_ms = (time.perf_counter_ns() - started) / 1e6
    try:
        started = time.perf_counter_ns()
        for session in dataset.sessions:
            book.ingest(session)
        import_ms = (time.perf_counter_ns() - started) / 1e6
        # A real, revision-valid cached call proves that migration invalidates
        # existing responses. The artificial probe and its timing are excluded
        # from both import and upgrade cost measurements.
        book.recall("upgrade_cost_cache_probe", project=dataset.sessions[0]["project"],
                    budget_chars=2000, limit=5, use_cache=True)
        snapshot = database_snapshot(book.db)
        if snapshot["valid_cache_rows"] < 1:
            raise RuntimeError("Baseline did not create a valid recall cache entry")
        _checkpoint(book.db)
    finally:
        book.close()
    wal = Path(str(args.database) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError("Baseline WAL is nonempty after checkpoint and close")
    return {"engine": _engine_identity(module, source_root, source_hash, args.label),
            "dataset": dataset.description(), "create_database_ms": create_ms,
            "import_ms": import_ms, "snapshot": snapshot,
            "checkpointed_file_bytes": args.database.stat().st_size}


def measure_upgrade(args) -> dict:
    module, source_root, source_hash = _load_engine(args.engine_src)
    connection = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        before = database_snapshot(connection)
    finally:
        connection.close()
    started = time.perf_counter_ns()
    book = module.MemoryBook(args.database, max_page_chars=900, cache_size=128)
    migration_ms = (time.perf_counter_ns() - started) / 1e6
    try:
        after = database_snapshot(book.db)
        assert_source_preserved(before, after)
        if after["schema_version"] <= before["schema_version"]:
            raise RuntimeError("Candidate did not upgrade the schema; choose an older baseline checkout")
        if before["valid_cache_rows"] < 1 or after["cache_rows"] != 0:
            raise RuntimeError("Migration did not invalidate a previously valid recall cache")
        if after["index_rows"].get("pages_stem_fts") != after["source_tables"]["pages"]["rows"]:
            raise RuntimeError("Porter index was not populated for every source page")
        _checkpoint(book.db)
    finally:
        book.close()
    started = time.perf_counter_ns()
    book = module.MemoryBook(args.database, max_page_chars=900, cache_size=128)
    reopen_ms = (time.perf_counter_ns() - started) / 1e6
    try:
        reopened = database_snapshot(book.db)
        assert_source_preserved(before, reopened)
        if reopened != after:
            raise RuntimeError("Reopening a migrated database unexpectedly changed its state")
        _checkpoint(book.db)
    finally:
        book.close()
    return {"engine": _engine_identity(module, source_root, source_hash, args.label),
            "migration_open_ms": migration_ms, "reopen_ms": reopen_ms,
            "before": before, "after": after, "reopened": reopened,
            "checkpointed_file_bytes_after": args.database.stat().st_size,
            "source_tables_preserved": True, "page_ids_content_source_refs_preserved": True,
            "cache_invalidated": True, "reopen_unchanged": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--candidate-label", default="candidate")
    parser.add_argument("--corpus", choices=("synthetic", "locomo"), default="synthetic")
    parser.add_argument("--split", choices=("development", "heldout"), default="development")
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=8)
    parser.add_argument("--locomo-path")
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=("prepare", "upgrade"), help=argparse.SUPPRESS)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--database", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--label", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.max_queries < 0:
        parser.error("repeats must be positive and max-queries must be nonnegative")
    if args.worker:
        if args.engine_src is None or args.database is None or args.label is None:
            parser.error("workers require engine-src, database and label")
        result = prepare_baseline(args) if args.worker == "prepare" else measure_upgrade(args)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    if args.baseline_src is None:
        parser.error("baseline-src must identify the old package source directory")
    evaluator_hash = engine_source_hash(Path(__file__).parent)
    work_parent = args.work_dir.resolve() if args.work_dir else Path.cwd().parent
    work_parent.mkdir(parents=True, exist_ok=True)
    common = [sys.executable, "-m", "benchmarks.upgrade_costs", "--corpus", args.corpus,
              "--split", args.split, "--seed", str(args.seed), "--projects", str(args.projects),
              "--max-queries", str(args.max_queries)]
    if args.locomo_path:
        common += ["--locomo-path", str(Path(args.locomo_path).resolve())]
    trials = []
    with tempfile.TemporaryDirectory(prefix="memory-upgrade-costs-", dir=work_parent) as directory:
        root = Path(directory)
        baseline_db, output = root / "baseline.db", root / "worker-result.json"
        subprocess.run([*common, "--worker", "prepare", "--engine-src", str(args.baseline_src.resolve()),
                        "--database", str(baseline_db), "--label", args.baseline_label,
                        "--output", str(output)], check=True)
        baseline = json.loads(output.read_text(encoding="utf-8"))
        for repetition in range(args.repeats):
            database = root / f"upgrade-{repetition}.db"
            shutil.copyfile(baseline_db, database)
            subprocess.run([*common, "--worker", "upgrade", "--engine-src", str(args.candidate_src.resolve()),
                            "--database", str(database), "--label", args.candidate_label,
                            "--output", str(output)], check=True)
            result = json.loads(output.read_text(encoding="utf-8"))
            if result["before"] != baseline["snapshot"]:
                raise RuntimeError("Upgrade trial did not start from the identical checkpointed baseline")
            if trials and result["engine"]["source_sha256_before"] != trials[0]["engine"]["source_sha256_before"]:
                raise RuntimeError("Candidate source changed between repeated upgrade trials")
            trials.append({"repetition": repetition + 1, **result})
    if evaluator_hash != engine_source_hash(Path(__file__).parent):
        raise RuntimeError("Benchmark implementation changed during upgrade measurement")
    before_bytes = baseline["snapshot"]["logical_database_bytes"]
    report = {"schema_version": 1, "evaluator_version": "upgrade-costs-1.0",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                          "platform": platform.platform()},
              "evaluator_source_sha256": evaluator_hash,
              "parameters": {"repeats": args.repeats, "max_page_chars": 900},
              "dataset": baseline["dataset"], "baseline": baseline, "trials": trials,
              "summary": {
                  "import_ms": baseline["import_ms"],
                  "schema_before": baseline["snapshot"]["schema_version"],
                  "schema_after": [trial["after"]["schema_version"] for trial in trials],
                  "logical_database_bytes_before": before_bytes,
                  "logical_database_bytes_after": [trial["after"]["logical_database_bytes"] for trial in trials],
                  "logical_database_growth_bytes": [trial["after"]["logical_database_bytes"] - before_bytes for trial in trials],
                  "migration_open": latency_summary([trial["migration_open_ms"] for trial in trials]),
                  "reopen": latency_summary([trial["reopen_ms"] for trial in trials]),
                  "source_tables_preserved": True, "page_ids_content_source_refs_preserved": True,
                  "cache_invalidated": True, "reopen_unchanged": True},
              "methodology": [
                  "Baseline and every candidate trial run in independent Python processes; requested package roots are checked against actual imports.",
                  "Baseline imports the corpus once, seeds one real revision-valid recall-cache entry, checkpoints WAL and closes. Each upgrade uses a fresh byte-for-byte copy of that database.",
                  "Import timing covers ingest calls only. Database construction, cache seeding, dataset loading, hashing, copying, checkpointing and process startup are reported separately or excluded.",
                  "Migration timing covers MemoryBook construction including schema upgrade/index materialization and its commit; reopen timing covers a second construction on the already upgraded database. Neither measures query or end-to-end model latency.",
                  "Source rows are individually SHA-256 hashed in stable column/row order. Six complete source-table fingerprints and an additional page-ID/text/source-reference fingerprint must remain identical before migration, after migration and on reopen.",
                  "Mutable meta, recall_cache and derived FTS rows are excluded from source hashes. Schema, revision, cache invalidation and FTS row counts are checked separately. Reopen must preserve the entire recorded snapshot.",
                  "Logical storage is SQLite page_count multiplied by page_size; checkpointed file bytes are recorded separately. It is not peak temporary disk usage, WAL write volume or resident memory.",
                  "Repeated copies have warm operating-system caches; measurements are not cold-disk or process-startup estimates. Every measured duration is retained.",
                  "Public corpora remain separately downloaded; reports contain counts, schema metadata and hashes, never source rows, questions or answers. Temporary databases are deleted on success or failure.",
                  "Source hashes identify executed Python bytes; dirty checkout commits identify base revisions only. Source/evaluator changes or preservation failures abort without publishing a successful report.",
              ]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
