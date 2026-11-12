"""Opt-in project-local statistics using SQLite's unchanged native FTS5 scorer.

Only one project's derived exact/stem pair is retained per connection. Source
text and global indexes are never modified. The marker lives in TEMP SQL, so
it is committed or rolled back with the derived index, not ahead of it in a
Python cache. A main-database revision change rebuilds the complete active
project; this is safe invalidation, not incremental index maintenance.
"""

from __future__ import annotations

import sqlite3
import time


POLICY_VERSION = 1
EXACT_TABLE = "memory_book_project_fts"
STEM_TABLE = "memory_book_project_stem_fts"
STATE_TABLE = "memory_book_project_fts_state"
TABLES = (EXACT_TABLE, STEM_TABLE)
_STATE_COLUMNS = ("policy_version", "project", "revision", "page_count",
                  "builds", "switches", "last_build_ms", "total_build_ms")


def _marker(db: sqlite3.Connection) -> dict | None:
    row = db.execute(f"SELECT {','.join(_STATE_COLUMNS)} FROM temp.{STATE_TABLE} WHERE singleton=1").fetchone()
    return dict(zip(_STATE_COLUMNS, row)) if row is not None else None


def project_tables(db: sqlite3.Connection, project: str, revision: int) -> tuple[str, str]:
    """Prepare both native FTS routes in the caller's existing read snapshot.

    The caller must supply the revision read from that same main-database
    transaction. No commit is performed here. Fixed private TEMP identifiers
    are returned for the normal MATCH/BM25 queries; user scope text is always
    a bound value. Unrelated projects cannot enter these tables.
    """
    if not db.in_transaction:
        raise RuntimeError("Project statistics require the existing recall read transaction")
    started = time.perf_counter_ns()
    # Do not use executescript: it would commit the caller's read transaction.
    db.execute(f"""CREATE TEMP TABLE IF NOT EXISTS {STATE_TABLE} (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        policy_version INTEGER NOT NULL, project TEXT NOT NULL,
        revision INTEGER NOT NULL, page_count INTEGER NOT NULL,
        builds INTEGER NOT NULL, switches INTEGER NOT NULL,
        last_build_ms REAL NOT NULL, total_build_ms REAL NOT NULL)""")
    db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS temp.{EXACT_TABLE} USING fts5(title,question,body,directory,tokenize='unicode61')")
    db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS temp.{STEM_TABLE} USING fts5(title,question,body,directory,tokenize='porter unicode61')")
    old = _marker(db)
    if old is not None and (old["policy_version"], old["project"], old["revision"]) == (POLICY_VERSION, project, revision):
        return TABLES
    # A private savepoint also preserves the previous active pair if an insert
    # fails and an outer caller elects to recover without aborting its read.
    db.execute("SAVEPOINT memory_book_project_statistics_build")
    try:
        for table in TABLES:
            db.execute(f"DELETE FROM temp.{table}")
            db.execute(f"""INSERT INTO temp.{table}(rowid,title,question,body,directory)
                SELECT f.rowid,f.title,f.question,f.body,f.directory
                FROM main.pages_fts f JOIN main.pages p ON p.rid=f.rowid
                WHERE p.project_id=?""", (project,))
        count = db.execute("SELECT COUNT(*) FROM main.pages WHERE project_id=?", (project,)).fetchone()[0]
        elapsed = (time.perf_counter_ns() - started) / 1e6
        builds = (old["builds"] if old is not None else 0) + 1
        switches = (old["switches"] if old is not None else 0) + int(old is not None and old["project"] != project)
        total = (old["total_build_ms"] if old is not None else 0.0) + elapsed
        db.execute(f"INSERT OR REPLACE INTO temp.{STATE_TABLE} VALUES(1,?,?,?,?,?,?,?,?)",
                   (POLICY_VERSION, project, revision, count, builds, switches, elapsed, total))
        db.execute("RELEASE memory_book_project_statistics_build")
    except BaseException:
        db.execute("ROLLBACK TO memory_book_project_statistics_build")
        db.execute("RELEASE memory_book_project_statistics_build")
        raise
    return TABLES


def state(db: sqlite3.Connection) -> dict:
    """Read diagnostic costs without creating an index or caching any query.

    Build time covers pair preparation through the last source-row insertion
    and row count, excluding the final marker write/savepoint release. Whole
    recall timing includes all of that work. TEMP byte counts cover SQLite's
    whole temporary database, not Python/SQLite RSS or physical disk usage.
    """
    exists = db.execute("SELECT 1 FROM sqlite_temp_master WHERE type='table' AND name=?", (STATE_TABLE,)).fetchone()
    marker = _marker(db) if exists else None
    result = {"initialized": marker is not None, "policy_version": None,
              "project": None, "revision": None, "page_count": 0,
              "builds": 0, "switches": 0, "last_build_ms": 0.0, "total_build_ms": 0.0}
    if marker is not None:
        result.update(marker)
    pages = db.execute("PRAGMA temp.page_count").fetchone()[0]
    page_size = db.execute("PRAGMA temp.page_size").fetchone()[0]
    free = db.execute("PRAGMA temp.freelist_count").fetchone()[0]
    result["temporary_storage"] = {"page_count": pages, "page_size": page_size,
        "freelist_count": free, "allocated_bytes": pages * page_size,
        "live_bytes": (pages - free) * page_size,
        "temp_store_pragma": db.execute("PRAGMA temp_store").fetchone()[0],
        "boundary": "Whole SQLite TEMP database; allocated includes free pages; not process RSS or physical disk bytes."}
    return result
