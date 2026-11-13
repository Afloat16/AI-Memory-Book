"""Transactional SQLite source archive, book index, and budgeted recall."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import _sqlite3
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from .segmentation import make_turns, segment
from .text import estimate_tokens, excerpt, headline, index_text, query_terms, terms

# Capture the C extension's objects rather than treating public sqlite3 aliases
# replaced before this module's first import as ordinary implementations.
_NATIVE_CONNECT = _sqlite3.connect
_NATIVE_CONNECTION = _sqlite3.Connection
_NATIVE_CURSOR = _sqlite3.Cursor
_NATIVE_ROW = _sqlite3.Row
_STEM_ROUTE_DESCRIPTION = tuple((name, None, None, None, None, None, None)
                                for name in ("rid", "id", "rank"))
_FULL_ROUTE_DESCRIPTION = tuple((name, None, None, None, None, None, None)
                                for name in ("id", "rid", "project_id", "chapter_id", "chapter_title",
                                             "session_id", "session_title", "created_at", "rank"))
_DIRECTORY_DESCRIPTION = tuple((name, None, None, None, None, None, None)
                               for name in ("id", "project_id", "chapter_id", "chapter_title",
                                            "session_id", "session_title", "created_at"))

SCHEMA_VERSION = 3
INDEX_VERSION = 3
RECALL_VERSION = 10
APPLICATION_ID = 0x4D424F4B
MAX_SESSION_CHARS = 8_000_000
CURRENT_QUERY = re.compile(r"\b(?:latest|current|now|final|finally)\b|当前|现在|最新|最终|最后", re.IGNORECASE)
HISTORICAL_QUERY = re.compile(r"\b(?:original|initial|previous|earlier|before|history|historical|formerly|old|as of)\b|最初|最早|之前|以前|原来|原始|历史|旧|\b(?:19|20)\d{2}\b", re.IGNORECASE)
ASCII_WORD = re.compile(r"[a-zA-Z]")
QUERY_CONJUNCTION = re.compile(r"\band\b|以及|并且|和", re.IGNORECASE)
STEM_INDEX_SQL = "CREATE VIRTUAL TABLE IF NOT EXISTS pages_stem_fts USING fts5(title, question, body, directory, tokenize='porter unicode61');"
STEM_DELETE_SQL = """CREATE TRIGGER IF NOT EXISTS pages_delete_stem_fts AFTER DELETE ON pages BEGIN
 DELETE FROM pages_stem_fts WHERE rowid = OLD.rid;
END;"""
STEM_REVISION_SQL = """CREATE TRIGGER IF NOT EXISTS meta_revision_sync_stem
AFTER UPDATE OF value ON meta
WHEN NEW.key='revision'
 AND COALESCE((SELECT value FROM meta WHERE key='stem_revision'), '') != NEW.value
BEGIN
 DELETE FROM pages_stem_fts;
 INSERT INTO pages_stem_fts(rowid,title,question,body,directory)
  SELECT rowid,title,question,body,directory FROM pages_fts;
 INSERT OR REPLACE INTO meta(key,value) VALUES('stem_revision',NEW.value);
END;"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('revision', '0');
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 task_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 UNIQUE(project_id, task_id)
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, external_id TEXT NOT NULL,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 content_hash TEXT NOT NULL, raw_json TEXT NOT NULL, segmentation TEXT NOT NULL,
 message_count INTEGER NOT NULL, turn_count INTEGER NOT NULL, content_chars INTEGER NOT NULL,
 settings_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(project_id, external_id)
);
CREATE INDEX IF NOT EXISTS sessions_chapter ON sessions(chapter_id, created_at);
CREATE TABLE IF NOT EXISTS turns (
 id TEXT PRIMARY KEY, session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL, message_indices TEXT NOT NULL,
 UNIQUE(session_pk, ordinal)
);
CREATE TABLE IF NOT EXISTS sections (
 id TEXT PRIMARY KEY, session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 title TEXT NOT NULL, summary TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sections_chapter ON sections(chapter_id, session_pk, ordinal);
CREATE TABLE IF NOT EXISTS pages (
 rid INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
 section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
 session_pk TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL,
 source_refs TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS pages_project ON pages(project_id);
CREATE INDEX IF NOT EXISTS pages_session ON pages(session_pk);
CREATE INDEX IF NOT EXISTS pages_chapter ON pages(chapter_id);
CREATE INDEX IF NOT EXISTS pages_section ON pages(section_id, ordinal);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(title, question, body, directory, tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS pages_delete_fts AFTER DELETE ON pages BEGIN
 DELETE FROM pages_fts WHERE rowid = OLD.rid;
END;
CREATE TABLE IF NOT EXISTS recall_cache (
 key TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, touched_ns INTEGER NOT NULL
);
""" + STEM_INDEX_SQL + "\n" + STEM_DELETE_SQL + """
INSERT OR IGNORE INTO meta(key,value)
 SELECT 'stem_revision',value FROM meta WHERE key='revision';
""" + STEM_REVISION_SQL + """
PRAGMA application_id = 1296191307;
PRAGMA user_version = 3;
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, *values: str) -> str:
    return prefix + hashlib.sha256(_json(values).encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _string(value: Any, name: str, *, maximum: int = 500, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{name} must be a nonempty string")
    value = value.strip()
    if len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be at most {maximum} characters and contain no NUL")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def normalize_session(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("a session must be a JSON object")
    project = _string(payload.get("project"), "project", maximum=200)
    session_id = _string(payload.get("session_id"), "session_id", maximum=256)
    title = _string(payload.get("title") or session_id, "title", maximum=500)
    task_id = _string(payload.get("task_id") or "", "task_id", maximum=256, required=False)
    task_title = _string(payload.get("task_title") or task_id or title, "task_title", maximum=500)
    created = payload.get("created_at") or ""
    if created:
        if not isinstance(created, str):
            raise ValueError("created_at must be an ISO 8601 string")
        try:
            stamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError) as exc:
            raise ValueError("created_at must be an ISO 8601 string") from exc
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > 50_000:
        raise ValueError("messages must be a nonempty list of at most 50000 text messages")
    normalized = []
    total = 0
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or not isinstance(message.get("role"), str) or message["role"] not in {"user", "assistant", "system", "developer", "tool"}:
            raise ValueError(f"messages[{i}] needs a supported role")
        content = message.get("content")
        if not isinstance(content, str) or "\x00" in content:
            raise ValueError(f"messages[{i}].content must be text without NUL")
        total += len(content)
        normalized.append({"role": message["role"], "content": content})
    if total > MAX_SESSION_CHARS:
        raise ValueError(f"session text exceeds {MAX_SESSION_CHARS} characters")
    if not any(m["content"].strip() and m["role"] in {"user", "assistant", "tool"} for m in normalized):
        raise ValueError("session must contain nonempty conversational content")
    return {"project": project, "project_name": _string(payload.get("project_name") or project, "project_name", maximum=500), "session_id": session_id, "title": title, "task_id": task_id, "task_title": task_title, "created_at": created, "messages": normalized}


def _context_allocations(pages: list[dict], budget: int) -> list[tuple[dict, str, int]]:
    """Share the body budget after reserving citations and complete short pages.

    Allocating while rendering only gives unused space to later results. That
    can truncate an early page even when all selected pages fit. Reserve small
    pages first, then share the remaining space between the longer pages. The
    order of evidence is unchanged and no answer labels are consulted.
    """
    selected: list[tuple[dict, str]] = []
    minimum, overhead = 0, 0
    for row in pages:
        header = f'[{row["id"]}] {row["project_id"]} / {row["session_id"]} | {row["created_at"]}\n'
        citation_cost = len(header) + (2 if selected else 0)
        required = citation_cost + min(120, len(row["content"]))
        if minimum + required > budget:
            # Keep the previous tiny-budget behavior: one useful cited
            # fragment is preferable to several headers with almost no text.
            if not selected and budget > citation_cost + 8:
                selected.append((row, header))
                overhead += citation_cost
            break
        selected.append((row, header))
        minimum += required
        overhead += citation_cost
    allowances = [0] * len(selected)
    remaining = budget - overhead
    order = sorted(range(len(selected)), key=lambda i: len(selected[i][0]["content"]))
    for position, i in enumerate(order):
        allowance = min(len(selected[i][0]["content"]), remaining // (len(order) - position))
        allowances[i] = allowance
        remaining -= allowance
    return [(row, header, allowances[i]) for i, (row, header) in enumerate(selected)]


def _directory_tokens(text: str) -> frozenset[str]:
    return frozenset(terms(text, query=True))


def _query_facets(query: str) -> list[list[str]]:
    """Recognize a small explicit conjunction, without semantic query rewriting.

    Each side needs at least two lexical terms: a name such as ``research and
    development`` is not automatically treated as two independent questions.
    This is deliberately limited syntax support, not a claim to parse intent.
    """
    pieces = QUERY_CONJUNCTION.split(query)
    if not 2 <= len(pieces) <= 3:
        return []
    facets = [query_terms(piece) for piece in pieces]
    return facets if all(len(facet) >= 2 for facet in facets) else []


def _candidate_rows(cursor, description: tuple, connection=None) -> tuple[list, sqlite3.Cursor | None]:
    """Read certified native candidate columns without allocating a Row each time.

    Only MemoryBook's original default-converter connection is eligible. A
    replacement connection, text factory, cursor or row factory keeps its
    original fetch behavior. The full ordered description, including duplicate
    names and every DB-API field, must agree before changing this cursor alone.
    The retained cursor reconstructs real Rows if any later guard needs the
    historical mapping path. Nothing changes the connection's row factory.
    """
    if (connection is not None and type(cursor) is _NATIVE_CURSOR and
            type(connection) is _NATIVE_CONNECTION and cursor.connection is connection and
            connection.text_factory is str and cursor.row_factory is _NATIVE_ROW and
            sqlite3.Row is _NATIVE_ROW and sqlite3.Cursor is _NATIVE_CURSOR and
            cursor.description == description):
        cursor.row_factory = None
        try:
            rows = cursor.fetchall()
        finally:
            cursor.row_factory = _NATIVE_ROW
        return rows, cursor
    return cursor.fetchall(), None



def _ranked_candidate_rows(db, statement: str, parameters: list, table: str,
                           connection=None) -> tuple[list, sqlite3.Cursor | None]:
    """Probe one native FTS rank route without changing its exact top-96 set.

    The inner query applies the original scopes before taking 97 rank-ordered
    rows. SQLite sorts only that bounded result by the original rank/id keys.
    A tie across the 96/97 boundary requires the complete historical query.
    Neither the connection factory nor any persistent FTS configuration changes.
    """
    ordinary = (connection is not None and db is connection and
                type(connection) is _NATIVE_CONNECTION and
                connection.text_factory is str and connection.row_factory is _NATIVE_ROW and
                sqlite3.Row is _NATIVE_ROW and sqlite3.Cursor is _NATIVE_CURSOR and
                table in ("pages_fts", "pages_stem_fts"))
    # Custom parameter adapters may be stateful. Keep their historical single
    # binding operation instead of potentially binding again after a probe.
    if ordinary:
        for value in parameters:
            kind = type(value)
            if (kind not in (str, int) or
                    (kind, _sqlite3.PrepareProtocol) in _sqlite3.adapters):
                ordinary = False
                break
    score = f"bm25({table},2.0,2.0,1.0,0.25) rank"
    tail = " ORDER BY rank,p.id LIMIT 96"
    if ordinary and statement.count(score) == 1 and statement.endswith(tail):
        inner = statement[:-len(tail)].replace(score, f"{table}.rank AS rank", 1)
        inner = inner.replace(f"FROM {table} JOIN pages p",
                              f"FROM {table} CROSS JOIN pages p", 1)
        inner += (f" AND {table}.rank MATCH 'bm25(2.0,2.0,1.0,0.25)'"
                  f" ORDER BY {table}.rank LIMIT 97")
        probe = "SELECT rid,id,rank FROM (" + inner + ") ranked_route ORDER BY rank,id"
        cursor = None
        rows, native_cursor = None, None
        try:
            cursor = db.execute(probe, parameters)
            rows, native_cursor = _candidate_rows(cursor, _STEM_ROUTE_DESCRIPTION, connection)
        except UnicodeDecodeError:
            # A 97th ID outside the old LIMIT may contain invalid UTF-8. Let
            # the original query determine whether its own selected IDs fail.
            pass
        except sqlite3.OperationalError as error:
            # CPython wraps its str-column decoder error as OperationalError,
            # without a SQLite error code. Never turn an arbitrary SQL error,
            # authorization denial or interruption into a retry.
            if not (type(error) is _sqlite3.OperationalError and
                    getattr(error, "sqlite_errorcode", None) is None and
                    str(error).startswith("Could not decode to UTF-8 column 'id' with text ")):
                raise
        finally:
            if cursor is not None:
                cursor.close()
        if (native_cursor is not None and type(rows) is list and len(rows) <= 97 and
                all(type(row) is tuple and len(row) == 3 and
                    type(row[0]) is int and type(row[1]) is str and
                    type(row[2]) in (int, float) and math.isfinite(row[2])
                    for row in rows)):
            if len(rows) < 97 or rows[95][2] != rows[96][2]:
                # The exhausted, closed native cursor retains its description
                # for _restore_candidate_rows if later metadata needs fallback.
                return rows[:96], native_cursor
    return _candidate_rows(db.execute(statement, parameters), _STEM_ROUTE_DESCRIPTION, connection)


def _restore_candidate_rows(rows: list, cursor: sqlite3.Cursor | None) -> list:
    """Restore only tuples produced by our certified native cursor."""
    return [_NATIVE_ROW(cursor, row) for row in rows] if cursor is not None else rows


class MemoryBook:
    """One SQLite connection per instance. Use a separate instance per thread.

    The database and raw conversations stay on the caller's machine. Lexical
    recall invokes no model or embedding provider. Opt-in exact token budgets
    may download the tokenizer's public vocabulary on first use; no source or
    query text is transmitted by that vocabulary initialization.
    """

    def __init__(self, path: str | Path = ".memory-book/memory.db", *, segmentation: str = "adaptive", max_page_chars: int = 900, min_page_chars: int = 400, similarity_threshold: float = 0.12, cache_size: int = 128, semantic_model_dir: str | Path | None = None):
        if segmentation not in {"adaptive", "turn", "session"}:
            raise ValueError("segmentation must be adaptive, turn, or session")
        _integer(max_page_chars, "max_page_chars", 128, 100_000)
        _integer(min_page_chars, "min_page_chars", 0, max_page_chars)
        _integer(cache_size, "cache_size", 0, 10_000)
        if isinstance(similarity_threshold, bool) or not isinstance(similarity_threshold, (int, float)) or not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        self.path = str(path)
        self.segmentation, self.max_page_chars = segmentation, max_page_chars
        self.min_page_chars, self.similarity_threshold = min_page_chars, similarity_threshold
        self.cache_size = cache_size
        if semantic_model_dir is not None and (not isinstance(semantic_model_dir, (str, Path)) or not str(semantic_model_dir).strip()):
            raise ValueError("semantic_model_dir must be an explicit local model directory")
        self.semantic_model_dir = Path(semantic_model_dir).expanduser().resolve() if semantic_model_dir is not None else None
        self._semantic_model = None
        # Directory text is immutable as a key: a rename or a concurrent
        # writer naturally gets a new entry. Cache only within this connection
        # and bound retained text independently of result-cache settings.
        self._directory_tokens = lru_cache(maxsize=512)(_directory_tokens)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        # The bounded route union produces many IN-list statement shapes.
        # Expand only the ordinary connection's prepared-statement cache;
        # custom connect callables retain their historical arguments.
        if sqlite3.connect is _NATIVE_CONNECT:
            self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None,
                                      cached_statements=512)
        else:
            self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        # This construction has no detect_types/converter option. Keep only
        # its identity as a certificate; custom/replaced connections never
        # acquire one, even if their current row factory happens to be Row.
        self._native_db = (self.db if sqlite3.connect is _NATIVE_CONNECT and
                           type(self.db) is _NATIVE_CONNECTION else None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
            if app_id not in {0, APPLICATION_ID}:
                raise ValueError("refusing to open a database belonging to another application")
            if version not in {0, 1, 2, SCHEMA_VERSION}:
                raise ValueError(f"unsupported database schema {version}; expected {SCHEMA_VERSION}")
            if version == 0:
                existing = self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if existing:
                    raise ValueError("refusing to initialize a non-Memory-Book database")
                self.db.executescript(SCHEMA)
            elif version < SCHEMA_VERSION or not self._stem_guard_ready():
                self._migrate_schema()
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self) -> MemoryBook:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.db.close()
        finally:
            self._directory_tokens.cache_clear()
            self._semantic_model = None
            self._native_db = None

    def _highlighted_bodies(self, expression: str, ids: list[int]) -> list[sqlite3.Row]:
        """Retain the original point-whitelist read for selected excerpts."""
        if not ids:
            return []
        parameters = ["\x01", "\x02", expression, *ids]
        return self.db.execute("""SELECT rowid,highlight(pages_stem_fts,2,?,?) body
          FROM pages_stem_fts WHERE pages_stem_fts MATCH ? AND rowid IN (""" +
          ",".join("?" for _ in ids) + ")", parameters).fetchall()

    def _semantic_encoder(self):
        if self.semantic_model_dir is None:
            raise ValueError("Semantic recall requires an explicit semantic_model_dir")
        if self._semantic_model is None:
            from .semantic import SemanticModel
            self._semantic_model = SemanticModel(self.semantic_model_dir)
        return self._semantic_model

    def build_semantic_index(self) -> dict:
        """Explicitly build optional local vectors without changing sources.

        Any ingestion, deletion or relinking makes the index stale. Semantic
        recall fails until this method succeeds; lexical recall remains usable.
        """
        from .semantic import build_index
        return build_index(self.db, self._semantic_encoder())

    def _stem_guard_ready(self) -> bool:
        """Also recognize schema-3 development databases created before the guard."""
        return bool(self.db.execute("""SELECT
          EXISTS(SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='meta_revision_sync_stem')
          AND EXISTS(SELECT 1 FROM meta WHERE key='stem_revision')""").fetchone()[0])

    def _migrate_schema(self) -> None:
        """Upgrade all derived indexes atomically without changing page addresses."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Another connection may have upgraded while this one waited for
            # the write lock. Never replay ALTER/backfill from a stale version.
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
            if app_id not in {0, APPLICATION_ID}:
                raise ValueError("refusing to migrate a database belonging to another application")
            if version not in {1, 2, SCHEMA_VERSION}:
                raise ValueError(f"unsupported database schema {version}; expected {SCHEMA_VERSION}")
            if version < SCHEMA_VERSION or not self._stem_guard_ready():
                names = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"meta", "projects", "sessions", "pages", "pages_fts", "recall_cache"} <= names:
                    raise ValueError("refusing to migrate a non-Memory-Book database")
                if version == 1:
                    self._migrate_v1()
                self._migrate_v2()
                self._changed()
                self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _migrate_v1(self) -> None:
        """Upgrade the development schema inside the caller's write transaction.

        Schema 1 did not record custom pagination limits. Retain actual pages
        and record the historical defaults for future relinking.
        """
        self.db.execute("ALTER TABLE sessions ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
        rows = self.db.execute("SELECT id,created_at,raw_json,segmentation FROM sessions").fetchall()
        for row in rows:
            source = json.loads(row["raw_json"])
            source["created_at"] = source.get("created_at") or row["created_at"]
            settings = {"segmentation": row["segmentation"], "max_page_chars": 1800, "min_page_chars": 400, "similarity_threshold": 0.12}
            self.db.execute("UPDATE sessions SET raw_json=?,settings_json=? WHERE id=?", (_json(source), _json(settings), row["id"]))
        self.db.execute("DELETE FROM pages_fts")
        pages = self.db.execute("SELECT p.*,c.title chapter_title,s.title session_title FROM pages p JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk").fetchall()
        for page in pages:
            question = headline(page["question"], 1200)
            self.db.execute("UPDATE pages SET question=? WHERE rid=?", (question, page["rid"]))
            self.db.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", (page["rid"], index_text(page["title"]), index_text(question), index_text(page["content"]), index_text(page["chapter_title"] + " " + page["session_title"])))

    def _migrate_v2(self) -> None:
        """Add the local stem index from existing tokens, preserving source bytes."""
        self.db.execute(STEM_INDEX_SQL)
        self.db.execute("DELETE FROM pages_stem_fts")
        self.db.execute("""INSERT INTO pages_stem_fts(rowid,title,question,body,directory)
          SELECT rowid,title,question,body,directory FROM pages_fts""")
        self.db.execute(STEM_DELETE_SQL)
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'stem_revision',value FROM meta WHERE key='revision'""")
        self.db.execute(STEM_REVISION_SQL)

    @property
    def revision(self) -> int:
        return int(self.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

    def _changed(self) -> None:
        # Current writers already update both indexes in their transaction.
        # Mark that work before advancing revision, so the database guard does
        # nothing on the normal path. An already-open older writer advances
        # only revision: the guard then rebuilds the entire stem index from
        # exact tokens inside that same write transaction. This compatibility
        # fallback is deliberately more expensive than current incremental writes.
        self.db.execute("""INSERT OR REPLACE INTO meta(key,value)
          SELECT 'stem_revision',CAST(value AS INTEGER)+1 FROM meta WHERE key='revision'""")
        self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
        self.db.execute("DELETE FROM recall_cache")

    def _refresh_chapter(self, chapter_id: str, *, reindex_directory: bool = False) -> None:
        rows = self.db.execute("SELECT sec.summary FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.chapter_id=? ORDER BY s.created_at, sec.ordinal LIMIT 8", (chapter_id,)).fetchall()
        if not rows:
            self.db.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
        else:
            summary = " · ".join(row[0] for row in rows)[:900]
            self.db.execute("UPDATE chapters SET summary=?,updated_at=? WHERE id=?", (summary, _now(), chapter_id))
            if reindex_directory:
                title = self.db.execute("SELECT title FROM chapters WHERE id=?", (chapter_id,)).fetchone()[0]
                pages = self.db.execute("SELECT p.rid,s.title FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE p.chapter_id=?", (chapter_id,)).fetchall()
                for page in pages:
                    values = (index_text(title + " " + page["title"]), page["rid"])
                    self.db.execute("UPDATE pages_fts SET directory=? WHERE rowid=?", values)
                    self.db.execute("UPDATE pages_stem_fts SET directory=? WHERE rowid=?", values)

    def ingest(self, payload: dict) -> dict:
        source = normalize_session(payload)
        turns = make_turns(source["messages"])
        sections = segment(turns, self.segmentation, self.max_page_chars, self.min_page_chars, self.similarity_threshold)
        project, external = source["project"], source["session_id"]
        session_pk = _id("ss_", project, external)
        task_key = "task:" + source["task_id"] if source["task_id"] else "session:" + external
        chapter_id = _id("ch_", project, task_key)
        now = _now()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_pk,)).fetchone()
            old_project = self.db.execute("SELECT name FROM projects WHERE id=?", (project,)).fetchone()
            old_chapter = self.db.execute("SELECT title FROM chapters WHERE id=?", (chapter_id,)).fetchone()
            if not payload.get("project_name") and old_project:
                source["project_name"] = old_project["name"]
            if not payload.get("task_title") and old_chapter:
                source["task_title"] = old_chapter["title"]
            source["created_at"] = source["created_at"] or (old["created_at"] if old else now)
            source_json = _json(source)
            settings = {"segmentation": self.segmentation, "max_page_chars": self.max_page_chars, "min_page_chars": self.min_page_chars, "similarity_threshold": self.similarity_threshold}
            content_hash = hashlib.sha256(_json([source, settings, INDEX_VERSION]).encode()).hexdigest()
            if old and old["content_hash"] == content_hash:
                counts = self.db.execute("SELECT COUNT(*) FROM pages WHERE session_pk=?", (session_pk,)).fetchone()[0]
                self.db.execute("COMMIT")
                return {"project": project, "session_id": external, "chapter_id": chapter_id, "pages": counts, "sections": len(sections), "turns": len(turns), "skipped": True, "revision": self.revision}
            self.db.execute("INSERT INTO projects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at", (project, source["project_name"], now, now))
            self.db.execute("INSERT INTO chapters(id,project_id,task_id,title,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at", (chapter_id, project, task_key, source["task_title"], now))
            if old:
                self.db.execute("DELETE FROM sessions WHERE id=?", (session_pk,))
            created = source["created_at"]
            self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (session_pk, external, project, chapter_id, source["title"], created, now, content_hash, source_json, self.segmentation, len(source["messages"]), len(turns), sum(len(t.content) for t in turns), _json(settings)))
            for turn in turns:
                self.db.execute("INSERT INTO turns VALUES(?,?,?,?,?,?)", (_id("t_", session_pk, str(turn.index)), session_pk, turn.index, turn.question, turn.content, _json(turn.message_indices)))
            page_count = 0
            indexed_directory = index_text(source["task_title"] + " " + source["title"])
            for i, section in enumerate(sections):
                section_id = _id("sec_", session_pk, str(i), section.title)
                self.db.execute("INSERT INTO sections VALUES(?,?,?,?,?,?)", (section_id, session_pk, chapter_id, section.title, section.summary, i))
                for j, page in enumerate(section.pages):
                    page_id = _id("p_", session_pk, str(i), str(j), page.content)
                    refs = [{**ref, "session_id": external, "project": project, "created_at": created} for ref in page.refs]
                    cur = self.db.execute("INSERT INTO pages(id,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", (page_id, section_id, session_pk, chapter_id, project, page.title, page.question, page.content, _json(refs), j))
                    indexed = (cur.lastrowid, index_text(page.title), index_text(page.question), index_text(page.content), indexed_directory)
                    self.db.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", indexed)
                    self.db.execute("INSERT INTO pages_stem_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", indexed)
                    page_count += 1
            self._refresh_chapter(chapter_id, reindex_directory=bool(old_chapter and old_chapter["title"] != source["task_title"]))
            if old and old["chapter_id"] != chapter_id:
                self._refresh_chapter(old["chapter_id"])
            self._changed()
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return {"project": project, "session_id": external, "chapter_id": chapter_id, "pages": page_count, "sections": len(sections), "turns": len(turns), "skipped": False, "revision": self.revision}

    def projects(self) -> list[dict]:
        rows = self.db.execute("""SELECT p.*,
          (SELECT COUNT(*) FROM sessions WHERE project_id=p.id) sessions,
          (SELECT COUNT(*) FROM chapters WHERE project_id=p.id) chapters,
          (SELECT COUNT(*) FROM pages WHERE project_id=p.id) pages
          FROM projects p ORDER BY p.name,p.id""").fetchall()
        return [dict(row) for row in rows]

    def toc(self, project: str, *, offset: int = 0, limit: int = 50) -> dict:
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        row = self.db.execute("SELECT * FROM projects WHERE id=?", (project,)).fetchone()
        if row is None:
            raise KeyError(f"project not found: {project}")
        total = self.db.execute("SELECT COUNT(*) FROM chapters WHERE project_id=?", (project,)).fetchone()[0]
        chapters = self.db.execute("""SELECT c.*,
          (SELECT COUNT(*) FROM sessions WHERE chapter_id=c.id) sessions,
          (SELECT COUNT(*) FROM sections WHERE chapter_id=c.id) sections,
          (SELECT COUNT(*) FROM pages WHERE chapter_id=c.id) pages
          FROM chapters c WHERE project_id=? ORDER BY title,id LIMIT ? OFFSET ?""", (project, limit, offset)).fetchall()
        return {"project": dict(row), "chapters": [dict(c) for c in chapters], "total": total, "next_offset": offset + limit if offset + limit < total else None, "revision": self.revision}

    def chapter(self, chapter_id: str, *, offset: int = 0, limit: int = 50, page_limit: int = 20) -> dict:
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        _integer(page_limit, "page_limit", 1, 100)
        row = self.db.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if row is None:
            raise KeyError(f"chapter not found: {chapter_id}")
        total = self.db.execute("SELECT COUNT(*) FROM sections WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
        rows = self.db.execute("SELECT sec.*,s.external_id session_id,s.title session_title,s.created_at FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.chapter_id=? ORDER BY s.created_at,s.id,sec.ordinal LIMIT ? OFFSET ?", (chapter_id, limit, offset)).fetchall()
        sections = []
        for sec in rows:
            preview = self.section(sec["id"], limit=page_limit)
            sections.append({**dict(sec), "pages": preview["pages"], "pages_total": preview["total"], "pages_next_offset": preview["next_offset"]})
        return {**dict(row), "sections": sections, "total": total, "next_offset": offset + limit if offset + limit < total else None}

    def section(self, section_id: str, *, offset: int = 0, limit: int = 50) -> dict:
        """Bound the page directory even for a single very long response."""
        _integer(offset, "offset", 0, 10_000_000)
        _integer(limit, "limit", 1, 100)
        row = self.db.execute("SELECT sec.*,s.external_id session_id,s.title session_title FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.id=?", (section_id,)).fetchone()
        if row is None:
            raise KeyError(f"section not found: {section_id}")
        total = self.db.execute("SELECT COUNT(*) FROM pages WHERE section_id=?", (section_id,)).fetchone()[0]
        pages = self.db.execute("SELECT id,title,length(content) chars,source_refs FROM pages WHERE section_id=? ORDER BY ordinal LIMIT ? OFFSET ?", (section_id, limit, offset)).fetchall()
        return {**dict(row), "pages": [{"id": p["id"], "title": p["title"], "chars": p["chars"], "turn_indices": sorted({r["turn_index"] for r in json.loads(p["source_refs"])})} for p in pages], "total": total, "next_offset": offset + limit if offset + limit < total else None}

    def _breadcrumb(self, row: sqlite3.Row | dict) -> list[dict]:
        return [{"id": row["project_id"], "title": row["project_name"], "kind": "project"}, {"id": row["chapter_id"], "title": row["chapter_title"], "kind": "chapter"}, {"id": row["section_id"], "title": row["section_title"], "kind": "section"}, {"id": row["id"], "title": row["title"], "kind": "page"}]

    @staticmethod
    def _refs(row: sqlite3.Row | dict, spans: list[tuple[int, int]]) -> list[dict]:
        result = []
        for lo, hi in spans:
            for ref in json.loads(row["source_refs"]):
                start, end = max(lo, ref["start"]), min(hi, ref["end"])
                if start < end:
                    result.append({**ref, "start": start, "end": end, "turn_start": ref["turn_start"] + start - ref["start"], "turn_end": ref["turn_start"] + end - ref["start"]})
        return result

    def read(self, page_id: str, *, offset: int = 0, limit: int = 12_000) -> dict:
        _integer(offset, "offset", 0, MAX_SESSION_CHARS * 2)
        _integer(limit, "limit", 1, 100_000)
        row = self.db.execute("""SELECT p.*,pr.name project_name,c.title chapter_title,sec.title section_title,s.external_id session_id,s.created_at
          FROM pages p JOIN projects pr ON pr.id=p.project_id JOIN chapters c ON c.id=p.chapter_id
          JOIN sections sec ON sec.id=p.section_id JOIN sessions s ON s.id=p.session_pk WHERE p.id=?""", (page_id,)).fetchone()
        if row is None:
            raise KeyError(f"page not found or changed: {page_id}")
        total, end = len(row["content"]), min(offset + limit, len(row["content"]))
        return {"id": row["id"], "title": row["title"], "content": row["content"][offset:end], "offset": offset, "total_chars": total, "next_offset": end if end < total else None, "source_refs": self._refs(row, [(offset, end)]), "breadcrumb": self._breadcrumb(row), "created_at": row["created_at"]}

    def get_session(self, project: str, session_id: str) -> dict:
        row = self.db.execute("SELECT raw_json FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
        if row is None:
            raise KeyError(f"session not found: {project}/{session_id}")
        return json.loads(row[0])

    def export(self, project: str | None = None) -> list[dict]:
        if project is None:
            rows = self.db.execute("SELECT raw_json FROM sessions ORDER BY project_id,created_at,id")
        else:
            rows = self.db.execute("SELECT raw_json FROM sessions WHERE project_id=? ORDER BY created_at,id", (project,))
        return [json.loads(row[0]) for row in rows]

    def link_session(self, project: str, session_id: str, task_id: str, title: str | None = None) -> dict:
        """Reassign a chapter without silently changing the session's split policy."""
        source = self.get_session(project, session_id)
        row = self.db.execute("SELECT segmentation,settings_json FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
        settings = json.loads(row["settings_json"])
        settings.setdefault("segmentation", row["segmentation"])
        previous = {key: getattr(self, key) for key in settings}
        try:
            for key, value in settings.items():
                setattr(self, key, value)
            source.pop("project_name", None)
            source.pop("task_title", None)
            source["task_id"] = _string(task_id, "task_id", maximum=256)
            if title is not None:
                source["task_title"] = _string(title, "title")
            return self.ingest(source)
        finally:
            for key, value in previous.items():
                setattr(self, key, value)

    def delete_session(self, project: str, session_id: str) -> bool:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id,chapter_id FROM sessions WHERE project_id=? AND external_id=?", (project, session_id)).fetchone()
            if row:
                self.db.execute("DELETE FROM sessions WHERE id=?", (row["id"],))
                self._refresh_chapter(row["chapter_id"])
                self.db.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project))
                self._changed()
            self.db.execute("COMMIT")
            return row is not None
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def delete_project(self, project: str) -> bool:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute("DELETE FROM projects WHERE id=?", (project,))
            if cur.rowcount:
                self._changed()
            self.db.execute("COMMIT")
            return bool(cur.rowcount)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def stats(self) -> dict:
        values = {key: self.db.execute(f"SELECT COUNT(*) FROM {key}").fetchone()[0] for key in ("projects", "chapters", "sessions", "turns", "sections", "pages")}
        values["chars"] = self.db.execute("SELECT COALESCE(SUM(content_chars),0) FROM sessions").fetchone()[0]
        values["page_chars"] = self.db.execute("SELECT COALESCE(SUM(length(content)),0) FROM pages").fetchone()[0]
        values["cache_entries"] = self.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
        values["database_bytes"] = self.db.execute("PRAGMA page_count").fetchone()[0] * self.db.execute("PRAGMA page_size").fetchone()[0]
        values["revision"], values["schema_version"] = self.revision, SCHEMA_VERSION
        return values

    def _project_rowid_bounds(self, project: str | None) -> tuple[int, int] | None:
        """Bound FTS iteration only when a project occupies a narrow rowid span.

        These covering-index probes run in recall's existing read snapshot.
        They retain no state across calls. Interleaved or archive-wide projects
        keep the original query plan instead of paying for ineffective bounds.
        """
        if project is None:
            return None
        lo, hi, archive_lo, archive_hi = self.db.execute("""SELECT
          (SELECT MIN(rid) FROM pages WHERE project_id=?),
          (SELECT MAX(rid) FROM pages WHERE project_id=?),
          (SELECT MIN(rid) FROM pages), (SELECT MAX(rid) FROM pages)""",
          (project, project)).fetchone()
        if lo is None:
            return (0, -1)
        if 2 * (hi - lo + 1) <= archive_hi - archive_lo + 1:
            return (lo, hi)
        return None

    def recall(self, query: str, project: str | None = None, chapter: str | None = None, session: str | None = None, *, budget_chars: int = 4000, limit: int = 5, strategy: str = "book", use_cache: bool = True, coverage: bool = False, budget_tokens: int | None = None, tokenizer: str = "cl100k_base", semantic: bool = False, follow_titles: bool = False) -> dict:
        started = time.perf_counter_ns()
        query = _string(query, "query", maximum=8000, required=False)
        _integer(budget_chars, "budget_chars", 0, 100_000)
        _integer(limit, "limit", 1, 50)
        from .token_budget import TOKENIZERS, TokenCounter
        if not isinstance(tokenizer, str) or tokenizer not in TOKENIZERS:
            raise ValueError("tokenizer must be cl100k_base or o200k_base")
        if budget_tokens is not None:
            _integer(budget_tokens, "budget_tokens", 0, 100_000)
        token_counter = TokenCounter(tokenizer) if budget_tokens is not None else None
        if strategy not in {"book", "flat"}:
            raise ValueError("strategy must be book or flat")
        if not isinstance(coverage, bool):
            raise ValueError("coverage must be a boolean")
        if coverage and strategy != "book":
            raise ValueError("coverage requires the book strategy")
        if not isinstance(semantic, bool):
            raise ValueError("semantic must be a boolean")
        if semantic and strategy != "book":
            raise ValueError("semantic recall requires the book strategy")
        if type(follow_titles) is not bool:
            raise ValueError("follow_titles must be a boolean")
        if follow_titles and strategy != "book":
            raise ValueError("follow_titles requires the book strategy")
        if follow_titles and (semantic or coverage):
            raise ValueError("follow_titles cannot be combined with semantic or coverage")
        for key, val in (("project", project), ("chapter", chapter), ("session", session)):
            if val is not None:
                _string(val, key)
        qt = query_terms(query)
        current_query = bool(CURRENT_QUERY.search(query) and not HISTORICAL_QUERY.search(query))
        use_stem = strategy == "book" and any(ASCII_WORD.search(token) for token in qt)
        semantic_model = self._semantic_encoder() if semantic else None
        follow_active = False
        title_reference_state = None
        if follow_titles:
            from .title_reference import VERSION as TITLE_REFERENCE_VERSION, follow_title_reference
            reason = ("project_required" if project is None else
                      "limit_below_two" if limit < 2 else
                      "zero_character_budget" if not budget_chars else
                      "zero_token_budget" if budget_tokens == 0 else
                      "temporal_query" if CURRENT_QUERY.search(query) or HISTORICAL_QUERY.search(query) else
                      "no_lexical_results" if not qt else None)
            follow_active = reason is None
            title_reference_state = {"version": TITLE_REFERENCE_VERSION,
                                     "active": False, "applied": False,
                                     "reason": reason or "no_lexical_results"}
        if self.db is not self._native_db:
            self._native_db = None
        native_connection = (self._native_db if not coverage and semantic_model is None
                             and not follow_active else None)
        # A read snapshot ties candidates, sources, and the cache revision together.
        self.db.execute("BEGIN")
        try:
            revision = self.revision
            cache_options = [INDEX_VERSION, RECALL_VERSION, query, project, chapter, session, budget_chars, limit, strategy, coverage]
            if semantic_model is not None:
                from .semantic import FUSION_VERSION, SEMANTIC_VERSION, check_index, fuse_candidates, rank_pages
                check_index(self.db, revision, semantic_model)
                cache_options.extend(["semantic", SEMANTIC_VERSION, semantic_model.fingerprint, FUSION_VERSION])
            if token_counter is not None:
                cache_options.extend([budget_tokens, tokenizer, token_counter.version])
            if follow_titles:
                cache_options.extend(["follow_titles", TITLE_REFERENCE_VERSION])
            cache_key = hashlib.sha256(_json(cache_options).encode()).hexdigest()
            cached = self.db.execute("SELECT payload FROM recall_cache WHERE key=? AND revision=?", (cache_key, revision)).fetchone() if use_cache and self.cache_size else None
            if cached:
                result = json.loads(cached[0])
                self.db.execute("COMMIT")
                result["cache_hit"] = True
                result["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
                return result
            clauses, params = [], []
            if project is not None:
                clauses.append("p.project_id=?")
                params.append(project)
            if chapter is not None:
                clauses.append("p.chapter_id=?")
                params.append(chapter)
            if session is not None:
                clauses.append("s.external_id=?")
                params.append(session)
            where = " AND " + " AND ".join(clauses) if clauses else ""
            candidates: list[dict] = []
            candidate_count = 0
            allocations: list[tuple[dict, str, int]] = []
            selected_pages: list[dict] = []
            source_units_for = None
            if (qt or (semantic and query)) and budget_chars:
                expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in qt)
                # The index enforces a body match, so a chapter name alone is
                # never treated as evidence. Select only metadata for candidate
                # ranking; large source bodies are loaded for selected pages.
                expression = f"({expression}) AND body : ({expression})"
                # Apply every requested scope before truncating the FTS hits.
                # Directory joins are needed only for the bounded candidates;
                # display-only fields are deferred to the final page fetch.
                scope_join = " JOIN sessions s ON s.id=p.session_pk" if session is not None else ""
                project_bounds = self._project_rowid_bounds(project) if qt and session is None else None
                routes, route_cursors = [], []
                route_description = _STEM_ROUTE_DESCRIPTION if use_stem else _FULL_ROUTE_DESCRIPTION
                for table in (("pages_fts", "pages_stem_fts") if use_stem else ("pages_fts",)):
                    # Table identifiers are fixed above; query text and every
                    # caller-supplied scope remain bound SQL parameters.
                    page_join = " CROSS JOIN" if project_bounds is not None else " JOIN"
                    statement = (f"""SELECT p.rid,p.id,bm25({table},2.0,2.0,1.0,0.25) rank
                      FROM {table}""" + page_join + f" pages p ON p.rid={table}.rowid" + scope_join +
                      f" WHERE {table} MATCH ?" + where)
                    route_params = [expression, *params]
                    if project_bounds is not None:
                        # Keep FTS outermost so range constraints narrow one
                        # posting scan, rather than restarting MATCH per page.
                        # The original scope still filters before the LIMIT.
                        statement += f" AND {table}.rowid BETWEEN ? AND ?"
                        route_params.extend(project_bounds)
                    statement += " ORDER BY rank,p.id LIMIT 96"
                    if not use_stem:
                        # Keep the single-route path to one candidate query.
                        statement = """SELECT p.id,p.rid,p.project_id,p.chapter_id,
                          c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at,hits.rank
                          FROM (""" + statement + """) hits JOIN pages p ON p.rid=hits.rid
                          JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
                          ORDER BY hits.rank,p.id"""
                    if qt and use_stem and native_connection is not None:
                        route, native_cursor = _ranked_candidate_rows(
                            self.db, statement, route_params, table, native_connection)
                    else:
                        route, native_cursor = (_candidate_rows(self.db.execute(statement, route_params),
                                                               route_description, native_connection)
                                                if qt else ([], None))
                    routes.append(route)
                    route_cursors.append(native_cursor)
                # Validate every route before reordering any derived work.
                # Native Rows may still contain custom values or columns.
                route_columns = (["rid", "id", "rank"] if use_stem else
                    ["id", "rid", "project_id", "chapter_id", "chapter_title",
                     "session_id", "session_title", "created_at", "rank"])
                metadata_columns = ["id", "project_id", "chapter_id", "chapter_title",
                                    "session_id", "session_title", "created_at"]
                id_position = 1 if use_stem else 0
                canonical_routes = (not coverage and semantic_model is None and not follow_active and
                                    type(routes[0]) is list and
                                    (not use_stem or type(routes[1]) is list))
                if canonical_routes:
                    for route, native_cursor in zip(routes, route_cursors):
                        expected_keys = route_columns
                        for row in route:
                            if native_cursor is None:
                                if type(row) is not sqlite3.Row:
                                    canonical_routes = False
                                    break
                                keys = row.keys()
                                if keys != expected_keys or len(row) != len(keys):
                                    canonical_routes = False
                                    break
                                if expected_keys is route_columns:
                                    expected_keys = keys
                            page_id, rank = row[id_position], row[-1]
                            rank_type = type(rank)
                            if type(page_id) is not str or (rank_type is not float and rank_type is not int):
                                canonical_routes = False
                                break
                        if not canonical_routes:
                            break
                if canonical_routes:
                    # The existing union and ordinal maps can share a pass.
                    # Duplicates keep first insertion and last ordinal/value;
                    # stem insertion still precedes exact-route overwrite.
                    rows, stem_ranks = {}, {}
                    if use_stem:
                        for i, row in enumerate(routes[1]):
                            page_id = row[id_position]
                            stem_ranks[page_id] = i + 1
                            rows[page_id] = row
                    exact_ranks = {}
                    for i, row in enumerate(routes[0]):
                        page_id = row[id_position]
                        exact_ranks[page_id] = i + 1
                        rows[page_id] = row
                    # Compare the ordered deduplicated keys, not raw routes.
                    # Identical routes retain BM25's original novelty scale.
                    fuse_routes = use_stem and list(exact_ranks) != list(stem_ranks)
                    if fuse_routes:
                        exact_scores = {row[id_position]: max(0.0, -row[-1]) for row in routes[0]}
                        stem_scores = {row[id_position]: max(0.0, -row[-1]) for row in routes[1]}
                        exact_scale = max(exact_scores.values(), default=1.0) or 1.0
                        stem_scale = max(stem_scores.values(), default=1.0) or 1.0
                else:
                    routes = [_restore_candidate_rows(route, cursor)
                              for route, cursor in zip(routes, route_cursors)]
                    route_cursors = [None] * len(routes)
                    # Preserve all original reads and exception ordering for
                    # custom values/factories and the optional full routes.
                    exact_ranks = {row["id"]: i + 1 for i, row in enumerate(routes[0])}
                    stem_ranks = {row["id"]: i + 1 for i, row in enumerate(routes[1])} if use_stem else {}
                    exact_scores = {row["id"]: max(0.0, -row["rank"]) for row in routes[0]}
                    stem_scores = {row["id"]: max(0.0, -row["rank"]) for row in routes[1]} if use_stem else {}
                    exact_scale = max(exact_scores.values(), default=1.0) or 1.0
                    stem_scale = max(stem_scores.values(), default=1.0) or 1.0
                    fuse_routes = use_stem and list(exact_ranks) != list(stem_ranks)
                    rows = {row["id"]: dict(row) for route in reversed(routes) for row in route}
                metadata_by_id = {}
                metadata = []
                metadata_cursor = None
                if use_stem and rows:
                    # Exact and stem routes commonly overlap. Fetch their
                    # directory metadata once, after both bounded searches.
                    ids = ([row[0] for row in rows.values()] if canonical_routes
                           else [row["rid"] for row in rows.values()])
                    metadata, metadata_cursor = _candidate_rows(self.db.execute("""SELECT p.id,p.project_id,p.chapter_id,
                      c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at
                      FROM pages p JOIN chapters c ON c.id=p.chapter_id
                      JOIN sessions s ON s.id=p.session_pk WHERE p.rid IN (""" +
                      ",".join("?" for _ in ids) + ")", ids), _DIRECTORY_DESCRIPTION,
                                                               native_connection if canonical_routes else None)
                late_materialize = canonical_routes
                if late_materialize and use_stem:
                    # Validate the original batch before collapsing any rows.
                    # Earlier duplicate rows may carry additional fields or
                    # failures that a last-value metadata map would discard.
                    if type(metadata) is not list:
                        late_materialize = False
                    else:
                        metadata_ids = set()
                        expected_keys = metadata_columns
                        for row in metadata:
                            if metadata_cursor is None:
                                if type(row) is not sqlite3.Row:
                                    late_materialize = False
                                    break
                                keys = row.keys()
                                if keys != expected_keys or len(row) != len(keys):
                                    late_materialize = False
                                    break
                                if expected_keys is metadata_columns:
                                    expected_keys = keys
                            page_id = row[0]
                            if type(page_id) is not str or page_id not in rows:
                                late_materialize = False
                                break
                            metadata_ids.add(page_id)
                        if len(metadata_ids) != len(rows):
                            late_materialize = False
                    if late_materialize:
                        metadata_by_id = {row[0]: row for row in metadata}
                if not late_materialize:
                    if canonical_routes:
                        routes = [_restore_candidate_rows(route, cursor)
                                  for route, cursor in zip(routes, route_cursors)]
                        rows = {row["id"]: dict(row) for route in reversed(routes) for row in route}
                    if use_stem:
                        metadata = _restore_candidate_rows(metadata, metadata_cursor)
                        # Keep the original mapping reads, duplicate updates,
                        # unknown-ID failures and their order on every fallback.
                        for row in metadata:
                            rows[row["id"]].update(dict(row))
                qset = set(qt)
                directory_factors = {}
                chapter_position, session_position = (3, 5) if use_stem else (4, 6)
                ranked_rows = []
                for row in rows.values():
                    if late_materialize:
                        # Ranking needs directory fields and the original route
                        # rank, not a private dictionary for every union row.
                        item = metadata_by_id[row[1]] if use_stem else row
                        page_id = item[0]
                    else:
                        # Fallback rows already contain the complete original
                        # mapping merge and are private to this recall call.
                        item = row
                    factor = 1
                    if strategy == "book":
                        directory = (item[chapter_position] + " " + item[session_position]
                                     if late_materialize else item["chapter_title"] + " " + item["session_title"])
                        if directory not in directory_factors:
                            title_overlap = len(qset & self._directory_tokens(directory)) / len(qset)
                            directory_factors[directory] = 1 + 0.15 * title_overlap
                        factor = directory_factors[directory]
                    if fuse_routes:
                        # Retain each route's
                        # relative BM25 margins instead of only its ordinal rank.
                        # Exact relevance retains the predeclared 2:1 preference.
                        # An absent route contributes zero, never a fake score.
                        if late_materialize:
                            relevance = (2 * exact_scores.get(page_id, 0.0) / exact_scale +
                                         stem_scores.get(page_id, 0.0) / stem_scale)
                        else:
                            relevance = (2 * exact_scores.get(item["id"], 0.0) / exact_scale +
                                         stem_scores.get(item["id"], 0.0) / stem_scale)
                    else:
                        relevance = -(row[-1] if late_materialize else item["rank"])
                    score = relevance * factor
                    if late_materialize:
                        ranked_rows.append((page_id, score, row, item))
                    else:
                        item["score"] = score
                        candidates.append(item)
                if late_materialize:
                    if fuse_routes:
                        ranked_rows.sort(key=lambda entry: (-entry[1], exact_ranks.get(entry[0], 97),
                                                            stem_ranks.get(entry[0], 97), entry[0]))
                    else:
                        ranked_rows.sort(key=lambda entry: (-entry[1], entry[0]))
                    candidate_count = len(ranked_rows)
                    # The unchanged temporal/novelty pass can only select from
                    # this prefix. Coverage and semantic fusion use all rows.
                    prefix_size = (limit * 4 if strategy == "book" and
                                   (current_query or (len(qt) > 1 and limit > 1)) else limit)
                    for _, score, row, metadata in ranked_rows[:prefix_size]:
                        item = dict(zip(route_columns, row))
                        if use_stem:
                            item.update(zip(metadata_columns, metadata))
                        item["score"] = score
                        candidates.append(item)
                elif fuse_routes:
                    candidates.sort(key=lambda item: (-item["score"], exact_ranks.get(item["id"], 97),
                                                      stem_ranks.get(item["id"], 97), item["id"]))
                else:
                    candidates.sort(key=lambda item: (-item["score"], item["id"]))
                if strategy == "book" and candidates and (current_query or (len(qt) > 1 and limit > 1)):
                    # Rerank a bounded pool using the FTS body's existing
                    # tokens. Complementary query facets can otherwise be
                    # crowded out by several almost-identical high scores.
                    pool = candidates[:limit * 4]
                    ids = [item["rid"] for item in pool]
                    matched = {row["rowid"]: qset.intersection(row["body"].split())
                               for row in self.db.execute(
                                   "SELECT rowid,body FROM pages_fts WHERE rowid IN (" +
                                   ",".join("?" for _ in ids) + ")", ids)}
                    if current_query:
                        # Timestamp preference is confined to the same task
                        # and identical matched query terms. Preserve each
                        # group's relevance positions so a recent unrelated
                        # task cannot displace a stronger topic match.
                        groups = {}
                        for i, item in enumerate(pool):
                            if not matched[item["rid"]]:
                                # Empty exact-term sets on stem-only hits do
                                # not establish equivalent factual revisions.
                                continue
                            key = (item["chapter_id"], frozenset(matched[item["rid"]]))
                            groups.setdefault(key, []).append(i)
                        for positions in groups.values():
                            scores = [pool[i]["score"] for i in positions]
                            revisions = sorted((pool[i] for i in positions), key=lambda item: item["created_at"], reverse=True)
                            for i, item, score in zip(positions, revisions, scores):
                                pool[i], item["score"] = item, score
                    chosen, pending = [pool[0]], pool[1:]
                    covered = set(matched[pool[0]["rid"]])
                    while pending and len(chosen) < limit:
                        best = max(range(len(pending)), key=lambda i: pending[i]["score"] *
                                   (1 + len(matched[pending[i]["rid"]] - covered) / len(qset)))
                        item = pending.pop(best)
                        chosen.append(item)
                        covered.update(matched[item["rid"]])
                    candidates = chosen + pending + candidates[len(pool):]
                facets = (_query_facets(query) if coverage and strategy == "book" and limit > 1 and
                          not CURRENT_QUERY.search(query) and not HISTORICAL_QUERY.search(query) else [])
                if candidates and facets:
                    # A whole-query OR score can fill every result slot with
                    # one requested subject. Rank each explicit clause over
                    # the already scoped, bounded candidate union and reserve
                    # its best page after the unchanged first result. No new
                    # sources, generated text, or answer labels enter this path.
                    candidate_ids = [item["rid"] for item in candidates]
                    original_positions = {item["rid"]: i for i, item in enumerate(candidates)}
                    preferred = [candidates[0]]
                    seen = {candidates[0]["rid"]}
                    for facet in facets:
                        clause = " OR ".join('"' + token.replace('"', '""') + '"' for token in facet)
                        clause = f"({clause}) AND body : ({clause})"
                        scores = []
                        for table in (("pages_fts", "pages_stem_fts") if use_stem else ("pages_fts",)):
                            # Unary + keeps SQLite from executing MATCH once
                            # per rowid in the IN-list. FTS scans the clause
                            # once, then applies the identical integer filter.
                            hits = self.db.execute(
                                f"SELECT rowid,bm25({table},2.0,2.0,1.0,0.25) rank FROM {table} "
                                f"WHERE {table} MATCH ? AND +rowid IN (" +
                                ",".join("?" for _ in candidate_ids) + ") ORDER BY rank,rowid LIMIT 96",
                                [clause, *candidate_ids]).fetchall()
                            route = {row["rowid"]: max(0.0, -row["rank"]) for row in hits}
                            scale = max(route.values(), default=1.0) or 1.0
                            scores.append({rid: value / scale for rid, value in route.items()})
                        found = set().union(*(route.keys() for route in scores))
                        if not found:
                            continue
                        leader = max(found, key=lambda rid: (
                            2 * scores[0].get(rid, 0.0) +
                            (scores[1].get(rid, 0.0) if use_stem else 0.0),
                            -original_positions[rid]))
                        if leader not in seen:
                            preferred.append(candidates[original_positions[leader]])
                            seen.add(leader)
                    candidates = preferred + [item for item in candidates if item["rid"] not in seen]
                if semantic_model is not None:
                    candidates = fuse_candidates(candidates, rank_pages(self.db, semantic_model, query, where, params))
                if follow_active:
                    # Opt-in T1 requires the unchanged complete lexical order,
                    # including original novelty, to attribute one target. The
                    # default and precondition-inactive paths keep the existing
                    # delayed materialization, SQL and cache identity.
                    candidates, title_reference_state = follow_title_reference(
                        self.db, candidates, project=project, chapter=chapter,
                        session=session, limit=limit)
                if not late_materialize:
                    candidate_count = len(candidates)
                if candidates:
                    selected_ids = [item["id"] for item in candidates[:limit]]
                    sources = {row["id"]: dict(row) for row in self.db.execute(
                        """SELECT p.id,p.title,p.section_id,p.session_pk,p.content,p.source_refs,
                          pr.name project_name,sec.title section_title FROM pages p
                          JOIN projects pr ON pr.id=p.project_id JOIN sections sec ON sec.id=p.section_id
                          WHERE p.id IN (""" + ",".join("?" for _ in selected_ids) + ")", selected_ids)}
                    for item in candidates[:limit]:
                        item.update(sources[item["id"]])
                    selected_pages = candidates[:limit]
                    allocations = _context_allocations(selected_pages, budget_chars)
                    truncated_ids = [item["rid"] for item, _, allowance in allocations
                                     if allowance < len(item["content"])] if use_stem else []
                    if truncated_ids:
                        # Highlight the normalized indexed body only when an
                        # actual excerpt needs word forms absent from the query.
                        # Full pages need no extra read or term extraction.
                        highlighted = self._highlighted_bodies(expression, truncated_ids)
                        forms = {}
                        for row in highlighted:
                            seen = set(qt)
                            extra = []
                            for match in re.finditer("\x01([^\x01\x02]+)\x02", row["body"]):
                                # FTS can merge adjacent highlighted tokens.
                                for form in match.group(1).split():
                                    if form not in seen:
                                        seen.add(form)
                                        extra.append(form)
                                        if len(extra) == 64:
                                            break
                                if len(extra) == 64:
                                    break
                            if extra:
                                forms[row["rowid"]] = qt + extra
                        for item, _, _ in allocations:
                            if item["rid"] in forms:
                                item["excerpt_terms"] = forms[item["rid"]]
                    if token_counter is not None and budget_tokens:
                        # Supplemental units are parsed in original turns so a
                        # page boundary cannot turn a cut sentence/fence into a
                        # purportedly complete new source unit. Read them under
                        # the same snapshot as ranking and page coordinates.
                        from .token_budget import prepare_source_units
                        wanted: dict[str, set[int]] = {}
                        refs_by_page = {}
                        for row in selected_pages:
                            refs = refs_by_page[row["id"]] = json.loads(row["source_refs"])
                            wanted.setdefault(row["session_pk"], set()).update(
                                ref["turn_index"] for ref in refs)
                        original_turns = {}
                        for session_pk, ordinals in wanted.items():
                            ordered = sorted(ordinals)
                            for source in self.db.execute(
                                "SELECT ordinal,content FROM turns WHERE session_pk=? AND ordinal IN (" +
                                ",".join("?" for _ in ordered) + ")", [session_pk, *ordered]):
                                original_turns[(session_pk, source["ordinal"])] = source["content"]
                        source_units_for = prepare_source_units(selected_pages, original_turns, refs_by_page)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        legacy = []
        for row, header, allowance in allocations:
            text, spans = excerpt(row["content"], query, allowance, prepared_terms=row.get("excerpt_terms", qt))
            legacy.append((row, header, text, spans))
        assembled = legacy
        if token_counter is not None:
            from .token_budget import assemble_with_count
            assembled, context_tokens = assemble_with_count(
                legacy, selected_pages, qt, budget_chars=budget_chars,
                budget_tokens=budget_tokens, counter=token_counter,
                source_units_for=source_units_for)
        results, blocks = [], []
        # Limit the work/response, but do not force one task/chapter branch.
        for row, header, text, spans in assembled:
            crumbs = self._breadcrumb(row)
            # The address and date are sufficient for agent recall. Display
            # names remain in breadcrumb metadata and exact read_page results;
            # repeating three long titles in every context block crowds out
            # evidence at small budgets without adding source identity.
            block = header + text
            refs = self._refs(row, spans)
            coverage = len(set(qt) & set(terms(text, query=True))) / len(qt) if qt else 0.0
            results.append({"id": row["id"], "title": row["title"], "text": text, "source_refs": refs, "breadcrumb": crumbs, "score": row["score"], "lexical_coverage": coverage, "created_at": row["created_at"], "truncated": len(text) < len(row["content"]), "page_chars": len(row["content"]), "excerpt_spans": [[a, b] for a, b in spans]})
            blocks.append(block)
        context = "\n\n".join(blocks)
        warnings = []
        if project is None and len({r["breadcrumb"][0]["id"] for r in results}) > 1:
            warnings.append("Results span projects; supply project to disambiguate.")
        if results and CURRENT_QUERY.search(query):
            warnings.append("Historical evidence can conflict. Check source timestamps; retrieval does not resolve which decision is authoritative.")
        if not results and candidates:
            warnings.append("Budget too small to return an evidence block including its citation.")
        result = {"query": query, "results": results, "context": context, "context_chars": len(context), "estimated_tokens": estimate_tokens(context), "candidate_count": candidate_count, "revision": revision, "cache_hit": False, "warnings": warnings, "strategy": strategy, "budget_chars": budget_chars, "truncated": candidate_count > len(results) or any(r["truncated"] for r in results)}
        if follow_titles:
            result["title_reference"] = title_reference_state
        if semantic_model is not None:
            result.update(semantic=True, semantic_model_fingerprint=semantic_model.fingerprint)
        if token_counter is not None:
            result.update(budget_tokens=budget_tokens, tokenizer=tokenizer,
                          tokenizer_version=token_counter.version,
                          context_tokens=context_tokens)
        if use_cache and self.cache_size:
            # A concurrent ingestion must not be overwritten by an old cache.
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if self.revision == revision:
                    self.db.execute("INSERT OR REPLACE INTO recall_cache VALUES(?,?,?,?)", (cache_key, revision, _json(result), time.time_ns()))
                    self.db.execute("DELETE FROM recall_cache WHERE key IN (SELECT key FROM recall_cache ORDER BY touched_ns DESC LIMIT -1 OFFSET ?)", (self.cache_size,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        result["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
        return result
