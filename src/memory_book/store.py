"""Transactional SQLite source archive, book index, and budgeted recall."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .segmentation import make_turns, segment
from .text import estimate_tokens, excerpt, headline, index_text, query_terms, terms

SCHEMA_VERSION = 2
INDEX_VERSION = 2
APPLICATION_ID = 0x4D424F4B
MAX_SESSION_CHARS = 8_000_000
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
PRAGMA application_id = 1296191307;
PRAGMA user_version = 2;
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


class MemoryBook:
    """One SQLite connection per instance. Use a separate instance per thread.

    The database and raw conversations stay on the caller's machine. Queries
    never invoke a model, embedding provider, or network endpoint.
    """

    def __init__(self, path: str | Path = ".memory-book/memory.db", *, segmentation: str = "adaptive", max_page_chars: int = 900, min_page_chars: int = 400, similarity_threshold: float = 0.12, cache_size: int = 128):
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
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
            if app_id not in {0, APPLICATION_ID}:
                raise ValueError("refusing to open a database belonging to another application")
            if version not in {0, 1, SCHEMA_VERSION}:
                raise ValueError(f"unsupported database schema {version}; expected {SCHEMA_VERSION}")
            if version == 0:
                existing = self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if existing:
                    raise ValueError("refusing to initialize a non-Memory-Book database")
                self.db.executescript(SCHEMA)
            elif version == 1:
                names = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"meta", "projects", "sessions", "pages", "pages_fts", "recall_cache"} <= names:
                    raise ValueError("refusing to migrate a non-Memory-Book database")
                self._migrate_v1()
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            self.db.close()
            raise

    def __enter__(self) -> MemoryBook:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def _migrate_v1(self) -> None:
        """Preserve existing page addresses while rebuilding the lexical index.

        Development schema 1 did not record custom pagination limits. Retain its
        actual pages, and record the historical defaults for future relinking.
        """
        self.db.execute("BEGIN IMMEDIATE")
        try:
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
            self._changed()
            self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @property
    def revision(self) -> int:
        return int(self.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

    def _changed(self) -> None:
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
                    self.db.execute("UPDATE pages_fts SET directory=? WHERE rowid=?", (index_text(title + " " + page["title"]), page["rid"]))

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
            for i, section in enumerate(sections):
                section_id = _id("sec_", session_pk, str(i), section.title)
                self.db.execute("INSERT INTO sections VALUES(?,?,?,?,?,?)", (section_id, session_pk, chapter_id, section.title, section.summary, i))
                for j, page in enumerate(section.pages):
                    page_id = _id("p_", session_pk, str(i), str(j), page.content)
                    refs = [{**ref, "session_id": external, "project": project, "created_at": created} for ref in page.refs]
                    cur = self.db.execute("INSERT INTO pages(id,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", (page_id, section_id, session_pk, chapter_id, project, page.title, page.question, page.content, _json(refs), j))
                    self.db.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,?,?,?,?)", (cur.lastrowid, index_text(page.title), index_text(page.question), index_text(page.content), index_text(source["task_title"] + " " + source["title"])))
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

    def recall(self, query: str, project: str | None = None, chapter: str | None = None, session: str | None = None, *, budget_chars: int = 4000, limit: int = 5, strategy: str = "book", use_cache: bool = True) -> dict:
        started = time.perf_counter_ns()
        query = _string(query, "query", maximum=8000, required=False)
        _integer(budget_chars, "budget_chars", 0, 100_000)
        _integer(limit, "limit", 1, 50)
        if strategy not in {"book", "flat"}:
            raise ValueError("strategy must be book or flat")
        for key, val in (("project", project), ("chapter", chapter), ("session", session)):
            if val is not None:
                _string(val, key)
        qt = query_terms(query)
        # A read snapshot ties candidates, sources, and the cache revision together.
        self.db.execute("BEGIN")
        try:
            revision = self.revision
            cache_key = hashlib.sha256(_json([INDEX_VERSION, query, project, chapter, session, budget_chars, limit, strategy]).encode()).hexdigest()
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
            if qt and budget_chars:
                expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in qt)
                # The index enforces a body match, so a chapter name alone is
                # never treated as evidence. Select only metadata for candidate
                # ranking; large source bodies are loaded for selected pages.
                expression = f"({expression}) AND body : ({expression})"
                rows = self.db.execute("""SELECT p.id,p.project_id,p.chapter_id,p.section_id,p.title,
                  pr.name project_name,c.title chapter_title,sec.title section_title,
                  s.external_id session_id,s.title session_title,s.created_at,
                  bm25(pages_fts,2.0,2.0,1.0,0.25) rank
                  FROM pages_fts JOIN pages p ON p.rid=pages_fts.rowid
                  JOIN projects pr ON pr.id=p.project_id JOIN chapters c ON c.id=p.chapter_id
                  JOIN sections sec ON sec.id=p.section_id JOIN sessions s ON s.id=p.session_pk
                  WHERE pages_fts MATCH ?""" + where + " ORDER BY rank,p.id LIMIT 96", [expression, *params]).fetchall()
                qset = set(qt)
                for row in rows:
                    item = dict(row)
                    title_overlap = len(qset & set(terms(item["chapter_title"] + " " + item["session_title"], query=True))) / len(qset)
                    item["score"] = -item["rank"] * (1 + 0.15 * title_overlap if strategy == "book" else 1)
                    candidates.append(item)
                candidates.sort(key=lambda item: (-item["score"], item["id"]))
                for item in candidates[:limit]:
                    source = self.db.execute("SELECT content,source_refs FROM pages WHERE id=?", (item["id"],)).fetchone()
                    item.update(dict(source))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        results, blocks = [], []
        remaining = budget_chars
        # Limit the work/response, but do not force one task/chapter branch.
        selected = candidates[:limit]
        for i, row in enumerate(selected):
            crumbs = self._breadcrumb(row)
            short_path = " / ".join(headline(c["title"], 48) for c in crumbs[:3])
            header = f'[{row["id"]}] {short_path}\nsource: {row["session_id"]} | {row["created_at"]}\n'
            separator = 2 if blocks else 0
            if remaining <= len(header) + separator + 8:
                break
            slots = len(selected) - i
            # Share budget, let short pages leave more room for later pages.
            allowance = max(120, remaining // max(1, slots) - len(header) - separator)
            allowance = min(allowance, remaining - len(header) - separator)
            text, spans = excerpt(row["content"], query, allowance)
            block = header + text
            refs = self._refs(row, spans)
            coverage = len(set(qt) & set(terms(text, query=True))) / len(qt) if qt else 0.0
            results.append({"id": row["id"], "title": row["title"], "text": text, "source_refs": refs, "breadcrumb": crumbs, "score": row["score"], "lexical_coverage": coverage, "created_at": row["created_at"], "truncated": len(text) < len(row["content"]), "page_chars": len(row["content"]), "excerpt_spans": [[a, b] for a, b in spans]})
            blocks.append(block)
            remaining -= len(block) + separator
        context = "\n\n".join(blocks)
        warnings = []
        if project is None and len({r["breadcrumb"][0]["id"] for r in results}) > 1:
            warnings.append("Results span projects; supply project to disambiguate.")
        if results and any(term in query.casefold() for term in ("latest", "current", "now", "当前", "现在", "最终", "最新")):
            warnings.append("Historical evidence can conflict. Check source timestamps; retrieval does not resolve which decision is authoritative.")
        if not results and candidates:
            warnings.append("Budget too small to return an evidence block including its citation.")
        result = {"query": query, "results": results, "context": context, "context_chars": len(context), "estimated_tokens": estimate_tokens(context), "candidate_count": len(candidates), "revision": revision, "cache_hit": False, "warnings": warnings, "strategy": strategy, "budget_chars": budget_chars, "truncated": len(candidates) > len(results) or any(r["truncated"] for r in results)}
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
