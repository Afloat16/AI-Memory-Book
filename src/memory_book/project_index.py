"""Bounded, opt-in project-local FTS statistics without a persistent migration.

The ordinary archive keeps its global BM25 contract. This module materializes
one complete, small project's existing rows in an independent SQLite database.
It does not re-ingest or resegment sources. All IDs, original turns, offsets,
lexical tokens and temporal evidence logic remain the same. BM25 statistics are
deliberately project-local, so ranks need not equal the global mode's ranks.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import MemoryBook


PAGE_LIMIT = 256
ROW_LIMIT = 8192
PROJECT_BYTE_LIMIT = 4 * 1024 * 1024
CACHE_PROJECT_LIMIT = 2
CACHE_BYTE_LIMIT = 8 * 1024 * 1024

# Fixed identifiers only. No caller text is interpolated into SQL identifiers.
_COLUMNS = {
    "projects": ("id", "name", "created_at", "updated_at"),
    "chapters": ("id", "project_id", "task_id", "title", "summary", "updated_at"),
    "sessions": ("id", "external_id", "project_id", "chapter_id", "title", "created_at",
                 "updated_at", "content_hash", "raw_json", "segmentation", "message_count",
                 "turn_count", "content_chars", "settings_json"),
    "turns": ("id", "session_pk", "ordinal", "question", "content", "message_indices"),
    "sections": ("id", "session_pk", "chapter_id", "title", "summary", "ordinal"),
    "pages": ("rid", "id", "section_id", "session_pk", "chapter_id", "project_id",
              "title", "question", "content", "source_refs", "ordinal"),
    "pages_fts": ("rowid", "title", "question", "body", "directory"),
    "pages_stem_fts": ("rowid", "title", "question", "body", "directory"),
}


@dataclass
class _Entry:
    book: MemoryBook
    fingerprint: bytes
    token: tuple[int, int, int]
    payload_bytes: int


def _ordinary_memory_book(parent: MemoryBook) -> bool:
    """A plain projection cannot stand in for customized instance behavior.

    Existing retrieval paths honor subclass and instance reference/breadcrumb
    hooks. Keep those calls on the original instance, including their errors,
    instead of silently replacing them with a newly constructed MemoryBook.
    """
    from .store import MemoryBook, _ORDINARY_DIRECTORY_TOKENS

    if type(parent) is not MemoryBook:
        return False
    if (parent._directory_tokens is not parent._ordinary_directory_cache
            or getattr(parent._directory_tokens, "__wrapped__", None) is not _ORDINARY_DIRECTORY_TOKENS):
        return False
    for name in vars(parent):
        descriptor = vars(MemoryBook).get(name)
        if callable(descriptor) or isinstance(descriptor, (staticmethod, classmethod, property)):
            return False
    return True


def _close_books(books) -> None:
    """Attempt every release and retain the first cleanup exception."""
    first_error = None
    for book in books:
        try:
            book.close()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _set_revision(book: MemoryBook, revision: int) -> None:
    """Synchronize only derived metadata; never trigger an FTS rebuild."""
    value = str(revision)
    book.db.execute("BEGIN IMMEDIATE")
    try:
        for key in ("stem_revision", "lexical_revision", "revision"):
            book.db.execute("UPDATE meta SET value=? WHERE key=?", (value, key))
        book.db.execute("DELETE FROM recall_cache")
        book.db.execute("COMMIT")
    except BaseException:
        book.db.execute("ROLLBACK")
        raise


def _coherent(rows: dict[str, list[tuple]], project: str) -> bool:
    """Do not turn malformed ownership into apparently valid local evidence."""
    data = {table: [dict(zip(_COLUMNS[table], row)) for row in values]
            for table, values in rows.items() if not table.endswith("_fts")}
    chapters = {row["id"]: row for row in data["chapters"]}
    sessions = {row["id"]: row for row in data["sessions"]}
    sections = {row["id"]: row for row in data["sections"]}
    if len(data["projects"]) != 1 or data["projects"][0]["id"] != project:
        return False
    for row in sessions.values():
        chapter = chapters.get(row["chapter_id"])
        if chapter is None or chapter["project_id"] != project:
            return False
    for row in sections.values():
        session = sessions.get(row["session_pk"])
        if session is None or row["chapter_id"] != session["chapter_id"]:
            return False
    for row in data["pages"]:
        session, section = sessions.get(row["session_pk"]), sections.get(row["section_id"])
        if (session is None or section is None or row["project_id"] != project
                or row["chapter_id"] != session["chapter_id"]
                or row["chapter_id"] != section["chapter_id"]
                or row["session_pk"] != section["session_pk"]):
            return False
    return all(row["session_pk"] in sessions for row in data["turns"])


def _snapshot(book: MemoryBook, project: str) -> tuple[dict | None, str | None, int]:
    """Load a complete scope only after row and byte bounds are certified.

    Each estimate is evaluated in SQLite before source strings cross into
    Python. A project with few very large source turns is therefore bounded as
    well as one with many pages. The caller owns the consistent read snapshot.
    """
    if book.db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone() is None:
        return None, "project_not_found", 0
    page_ids = [row[0] for row in book.db.execute(
        "SELECT rid FROM pages WHERE project_id=? LIMIT ?", (project, PAGE_LIMIT + 1))]
    if len(page_ids) > PAGE_LIMIT:
        return None, "project_page_limit", 0
    predicates = {
        "projects": ("id=?", (project,)),
        "chapters": ("project_id=?", (project,)),
        "sessions": ("project_id=?", (project,)),
        "turns": ("session_pk IN (SELECT id FROM sessions WHERE project_id=?)", (project,)),
        "sections": ("chapter_id IN (SELECT id FROM chapters WHERE project_id=?)", (project,)),
        "pages": ("project_id=?", (project,)),
    }
    membership = "rowid IN (" + ",".join("?" for _ in page_ids) + ")" if page_ids else "0"
    for table in ("pages_fts", "pages_stem_fts"):
        predicates[table] = (membership, tuple(page_ids))
    loaded, total_bytes, total_rows = {}, 0, 0
    for table, columns in _COLUMNS.items():
        predicate, params = predicates[table]
        projection = ",".join(columns)
        byte_sum = "+".join(f"COALESCE(length(CAST({column} AS BLOB)),0)" for column in columns)
        count, size = book.db.execute(
            f"SELECT COUNT(*),COALESCE(SUM({byte_sum}),0) FROM "
            f"(SELECT {projection} FROM {table} WHERE {predicate} LIMIT ?)",
            (*params, ROW_LIMIT + 1)).fetchone()
        total_rows += count
        total_bytes += size
        if total_rows > ROW_LIMIT:
            return None, "project_row_limit", 0
        if total_bytes > PROJECT_BYTE_LIMIT:
            return None, "project_byte_limit", 0
        loaded[table] = [tuple(row) for row in book.db.execute(
            f"SELECT {projection} FROM {table} WHERE {predicate} ORDER BY {columns[0]}", params)]
    if not _coherent(loaded, project):
        return None, "inconsistent_project_ownership", 0
    return loaded, None, total_bytes


def _materialize(parent: MemoryBook, rows: dict, revision: int) -> MemoryBook:
    from .store import MemoryBook

    book = MemoryBook(":memory:", segmentation=parent.segmentation,
                      max_page_chars=parent.max_page_chars, min_page_chars=parent.min_page_chars,
                      similarity_threshold=parent.similarity_threshold, cache_size=parent.cache_size)
    try:
        book.db.execute("BEGIN IMMEDIATE")
        for table, columns in _COLUMNS.items():
            book.db.executemany(
                f"INSERT INTO {table}(" + ",".join(columns) + ") VALUES(" +
                ",".join("?" for _ in columns) + ")", rows[table])
        book.db.execute("COMMIT")
        _set_revision(book, revision)
    except BaseException:
        book.close()
        raise
    return book


class ProjectIndexes:
    """Connection-owned LRU of at most two byte-bounded project projections."""

    def __init__(self) -> None:
        self.entries: OrderedDict[str, _Entry] = OrderedDict()

    def close(self) -> None:
        books = [entry.book for entry in reversed(self.entries.values())]
        self.entries.clear()
        _close_books(books)

    def _prepare(self, parent: MemoryBook, project: str, *, cache: bool) -> tuple:
        # Read data_version *before* revision establishes the source snapshot.
        # A concurrent commit after this token cannot be mistaken for a checked
        # future snapshot on the next call. total_changes also sees direct
        # writes made through this same connection.
        data_version = parent.db.execute("PRAGMA data_version").fetchone()[0]
        revision = parent.revision
        token = (data_version, revision, parent.db.total_changes)
        entry = self.entries.get(project) if cache else None
        if entry is not None and entry.token == token:
            self.entries.move_to_end(project)
            return entry.book, None, True, False
        rows, reason, size = _snapshot(parent, project)
        if rows is None:
            if cache and project in self.entries:
                self.entries.pop(project).book.close()
            return None, reason, False, True
        fingerprint = hashlib.sha256(json.dumps(
            rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).digest()
        if entry is not None and entry.fingerprint == fingerprint:
            if entry.book.revision != revision:
                _set_revision(entry.book, revision)
            entry.token = token
            self.entries.move_to_end(project)
            return entry.book, None, True, True
        local = _materialize(parent, rows, revision)
        if cache:
            prior = self.entries.pop(project, None)
            self.entries[project] = _Entry(local, fingerprint, token, size)
            retired = [prior.book] if prior is not None else []
            while (len(self.entries) > CACHE_PROJECT_LIMIT
                   or sum(value.payload_bytes for value in self.entries.values()) > CACHE_BYTE_LIMIT):
                _, old = self.entries.popitem(last=False)
                retired.append(old.book)
            # Install the new entry before closing retired resources. If a
            # cleanup hook fails, the newly opened book is still owned and a
            # later parent.close() can release it; every retired book is tried.
            _close_books(retired)
        return local, None, False, True

    def call(self, parent: MemoryBook, operation: str, query: str, options: dict) -> dict:
        started = time.perf_counter_ns()
        project = options.get("project")
        reason = None
        local = None
        reused, checked = False, False
        caller_transaction = parent.db.in_transaction
        ordinary = (type(parent.db) is sqlite3.Connection and parent.db.row_factory is sqlite3.Row
                    and parent.db.text_factory is str)
        if not _ordinary_memory_book(parent):
            reason = "customized_memory_book"
        elif type(project) is not str or not project:
            reason = "explicit_project_required"
        elif options.get("semantic"):
            reason = "semantic_index_requires_global_scope"
        elif not ordinary or not parent._can_batch_scoped_query("SELECT 1", PAGE_LIMIT + 1):
            reason = "customized_sqlite_connection"
        elif operation == "recall" and caller_transaction:
            # Preserve recall's existing nested-transaction error contract.
            reason = "existing_transaction"
        else:
            if not caller_transaction:
                parent.db.execute("BEGIN")
            try:
                local, reason, reused, checked = self._prepare(parent, project, cache=not caller_transaction)
            finally:
                if not caller_transaction and parent.db.in_transaction:
                    parent.db.execute("ROLLBACK")
        preparation_ms = (time.perf_counter_ns() - started) / 1e6
        try:
            if local is not None:
                # cache_size is intentionally mutable on MemoryBook. Mirror
                # its existing enable/disable/next-write eviction semantics
                # without rebuilding an otherwise unchanged project index.
                local.cache_size = parent.cache_size
                response = getattr(local, operation)(query, **options)
            elif operation == "recall":
                response = parent._recall(query, **options)
            else:
                from .directory import search_directory
                response = search_directory(parent, query, **options)
        finally:
            if caller_transaction and local is not None:
                # Never retain a view of uncommitted data after caller rollback.
                local.close()
        response["ranking_scope"] = {
            "requested": "project", "actual": "project" if local is not None else "global",
            "statistics": "project_local_bm25" if local is not None else "archive_global_bm25",
            "fallback_reason": reason, "page_limit": PAGE_LIMIT,
            "source_byte_limit": PROJECT_BYTE_LIMIT, "index_cache_hit": reused,
            "fingerprint_checked": checked, "preparation_ms": preparation_ms,
        }
        if local is None:
            response.setdefault("warnings", []).append(
                "Project-local ranking unavailable: " + str(reason) + "; used global ranking.")
        if operation == "recall":
            response["latency_ms"] = (time.perf_counter_ns() - started) / 1e6
        return response
