"""Transactional FTS5 corpus statistics for complete small-project searches.

FTS5 computes a phrase's global document frequency by visiting its posting
list when bm25() first runs. A project rowid filter does not bound that work.
This derived index maintains the *same global* statistics during writes and
stores compact per-page frequencies. It changes neither tokenization nor the
ranking formula. Sources, FTS indexes and addresses remain authoritative.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
import math
import sqlite3
import zlib


VERSION = 1
MIN_ARCHIVE_PAGES = 4096
MAX_PROJECT_PAGES = 256
MAX_PROJECT_BYTES = 2 * 1024 * 1024
MAX_PROJECT_DECODED_BYTES = 8 * 1024 * 1024
_COLUMNS = ("title", "question", "body", "directory")
_WEIGHTS = (2.0, 2.0, 1.0, 0.25)
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS bm25_corpus (
      route INTEGER PRIMARY KEY, documents INTEGER NOT NULL, tokens INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS bm25_terms (
      route INTEGER NOT NULL, term TEXT NOT NULL, documents INTEGER NOT NULL,
      body_documents INTEGER NOT NULL, metadata_documents INTEGER NOT NULL,
      PRIMARY KEY(route,term)) WITHOUT ROWID""",
    """CREATE TABLE IF NOT EXISTS bm25_pages (
      rid INTEGER PRIMARY KEY, summary BLOB NOT NULL, decoded_bytes INTEGER NOT NULL)""",
)
_GUARD = """CREATE TRIGGER IF NOT EXISTS meta_revision_invalidate_bm25
AFTER UPDATE OF value ON meta
WHEN NEW.key='revision'
 AND COALESCE((SELECT value FROM meta WHERE key='bm25_revision'), '') != NEW.value
BEGIN
 UPDATE meta SET value='stale' WHERE key='bm25_revision';
END"""
_PROJECT_SQL = """SELECT p.rid,p.id,0.0 AS rank,p.project_id,p.chapter_id,p.session_pk,
  c.title AS chapter_title,s.external_id AS session_id,s.title AS session_title,s.created_at,
  p.section_id,p.ordinal,sec.ordinal AS section_ordinal,length(b.summary) AS summary_bytes,
  b.decoded_bytes,c.project_id AS chapter_project,s.project_id AS session_project,
  s.chapter_id AS session_chapter,sec.chapter_id AS section_chapter,
  sec.session_pk AS section_session
  FROM pages p INDEXED BY pages_project
  LEFT JOIN bm25_pages b ON b.rid=p.rid
  LEFT JOIN chapters c ON c.id=p.chapter_id LEFT JOIN sessions s ON s.id=p.session_pk
  LEFT JOIN sections sec ON sec.id=p.section_id WHERE p.project_id=? LIMIT ?"""
SCHEMA_SQL = ";\n".join(_SCHEMA) + ";\n" + """
INSERT OR IGNORE INTO bm25_corpus VALUES(0,0,0);
INSERT OR IGNORE INTO bm25_corpus VALUES(1,0,0);
INSERT OR IGNORE INTO meta VALUES('bm25_version','1');
INSERT OR IGNORE INTO meta SELECT 'bm25_revision',value FROM meta WHERE key='revision';
""" + _GUARD + ";\n"


class _Tokenizer:
    """Ask this SQLite build for its actual unicode61/Porter tokens."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        for route, tokenizer in enumerate(("unicode61", "porter unicode61")):
            self.db.execute(f"CREATE VIRTUAL TABLE tokens{route} USING fts5(value,tokenize='{tokenizer}')")
            self.db.execute(f"CREATE VIRTUAL TABLE vocabulary{route} USING fts5vocab(tokens{route},'instance')")
        self.cached = lru_cache(maxsize=256)(self._tokens)

    def _tokens(self, route: int, text: str) -> tuple[str, ...]:
        self.db.execute(f"DELETE FROM tokens{route}")
        self.db.execute(f"INSERT INTO tokens{route}(rowid,value) VALUES(1,?)", (text,))
        return tuple(row[0] for row in self.db.execute(
            f"SELECT term FROM vocabulary{route} ORDER BY offset"))

    def tokens(self, route: int, text: str) -> tuple[str, ...]:
        # Bound cache keys and retained token text; oversized pages still work.
        return self.cached(route, text) if len(text) <= 4096 else self._tokens(route, text)

    def close(self):
        self.cached.cache_clear()
        self.db.close()


def _decode(blob: bytes) -> list:
    return json.loads(zlib.decompress(blob))


class _ScopedRoutes(list):
    """Request-local complete matches, before the public candidate limit."""

    def __init__(self, routes, exact_matches):
        super().__init__(routes)
        self.exact_matches = exact_matches


class BM25Statistics:
    scope_statement = _PROJECT_SQL

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._tokenizer = None
        self._active = False

    def close(self):
        if self._tokenizer is not None:
            self._tokenizer.close()
            self._tokenizer = None

    def _tokens(self, route: int, text: str) -> tuple[str, ...]:
        if self._tokenizer is None:
            self._tokenizer = _Tokenizer()
        return self._tokenizer.tokens(route, text)

    def ready(self) -> bool:
        # Constant-size catalog/metadata lookups; never count or scan pages.
        return bool(self.db.execute("""SELECT
          EXISTS(SELECT 1 FROM sqlite_master WHERE name='bm25_pages' AND type='table')
          AND EXISTS(SELECT 1 FROM sqlite_master WHERE name='bm25_terms' AND type='table')
          AND EXISTS(SELECT 1 FROM sqlite_master WHERE name='bm25_corpus' AND type='table')
          AND EXISTS(SELECT 1 FROM sqlite_master WHERE name='meta_revision_invalidate_bm25' AND type='trigger')
          AND EXISTS(SELECT 1 FROM meta WHERE key='bm25_version' AND value=?)
          AND EXISTS(SELECT 1 FROM meta WHERE key='bm25_revision'
            AND value=(SELECT value FROM meta WHERE key='revision'))""", (str(VERSION),)).fetchone()[0])

    def ensure(self, *, force: bool = False):
        if not force and self.ready():
            self._active = True
            return
        owns_transaction = not self.db.in_transaction
        if owns_transaction:
            self.db.execute("BEGIN IMMEDIATE")
        try:
            # Recheck after acquiring the write lock: another initializer may
            # already have completed this one-time rebuild.
            if force or not self.ready():
                for statement in _SCHEMA:
                    self.db.execute(statement)
                self.db.execute("DELETE FROM bm25_pages")
                self.db.execute("DELETE FROM bm25_terms")
                self.db.execute("DELETE FROM bm25_corpus")
                self.db.executemany("INSERT INTO bm25_corpus VALUES(?,0,0)", ((0,), (1,)))
                cursor = self.db.execute("""SELECT rowid,title,question,body,directory
                  FROM pages_fts ORDER BY rowid""")
                while batch := cursor.fetchmany(128):
                    self.add_many(batch)
                self.db.execute("INSERT OR REPLACE INTO meta VALUES('bm25_version',?)", (str(VERSION),))
                self.db.execute("""INSERT OR REPLACE INTO meta
                  SELECT 'bm25_revision',value FROM meta WHERE key='revision'""")
                self.db.execute(_GUARD)
            self._active = True
            if owns_transaction:
                self.db.execute("COMMIT")
        except BaseException:
            if owns_transaction:
                self.db.execute("ROLLBACK")
            raise

    def advance_revision(self):
        if self._active:
            self.db.execute("""INSERT OR REPLACE INTO meta
              SELECT 'bm25_revision',CAST(value AS INTEGER)+1 FROM meta WHERE key='revision'""")

    def _summary(self, fields) -> list:
        summaries = []
        for route in (0, 1):
            frequencies = {}
            length = 0
            for column, text in enumerate(fields):
                counts = Counter(self._tokens(route, text))
                length += sum(counts.values())
                for term, count in counts.items():
                    frequencies.setdefault(term, [0, 0, 0, 0])[column] = count
            summaries.append([length, frequencies])
        return summaries

    @staticmethod
    def _accumulate(summaries: list, terms: dict, totals: list, direction: int):
        for route, (length, frequencies) in enumerate(summaries):
            totals[route][0] += direction
            totals[route][1] += direction * length
            for term, counts in frequencies.items():
                delta = terms.setdefault((route, term), [0, 0, 0])
                delta[0] += direction
                delta[1] += direction * bool(counts[2])
                delta[2] += direction * bool(counts[0] or counts[1] or counts[3])

    def _apply(self, terms: dict, totals: list):
        if not terms and not any(any(values) for values in totals):
            return
        self.db.executemany("""INSERT INTO bm25_terms VALUES(?,?,?,?,?)
          ON CONFLICT(route,term) DO UPDATE SET
            documents=documents+excluded.documents,
            body_documents=body_documents+excluded.body_documents,
            metadata_documents=metadata_documents+excluded.metadata_documents""",
          ((route, term, *counts) for (route, term), counts in terms.items()))
        # Remove only this mutation's zero-frequency keys, using the primary
        # key. A whole-vocabulary cleanup would make each write archive-wide.
        self.db.executemany("DELETE FROM bm25_terms WHERE route=? AND term=? AND documents=0",
                            (key for key, delta in terms.items() if delta[0] < 0))
        self.db.executemany("""UPDATE bm25_corpus SET documents=documents+?,tokens=tokens+?
          WHERE route=?""", ((*counts, route) for route, counts in enumerate(totals)))

    def add_many(self, indexed):
        pages, terms, totals = [], {}, [[0, 0], [0, 0]]
        for row in indexed:
            summaries = self._summary(row[1:])
            encoded = json.dumps(summaries, ensure_ascii=False, separators=(",", ":")).encode()
            blob = zlib.compress(encoded, 1)
            pages.append((row[0], blob, len(encoded)))
            self._accumulate(summaries, terms, totals, 1)
        self.db.executemany("INSERT INTO bm25_pages VALUES(?,?,?)", pages)
        self._apply(terms, totals)

    def remove(self, predicate: str, parameters):
        # Callers supply fixed SQL predicates, never user SQL. Pages still
        # exist at this point; source and summary removal share one transaction.
        cursor = self.db.execute("SELECT b.rid,b.summary FROM pages p JOIN bm25_pages b ON b.rid=p.rid WHERE "
                                 + predicate, parameters)
        terms, totals, ids = {}, [[0, 0], [0, 0]], []
        for rid, blob in cursor:
            ids.append((rid,))
            self._accumulate(_decode(blob), terms, totals, -1)
        self.db.executemany("DELETE FROM bm25_pages WHERE rid=?", ids)
        self._apply(terms, totals)

    def refresh(self, rid: int):
        self.remove("p.rid=?", (rid,))
        row = self.db.execute("SELECT rowid,title,question,body,directory FROM pages_fts WHERE rowid=?", (rid,)).fetchone()
        if row is not None:
            self.add_many([tuple(row)])

    def project_rows(self, project: str | None, *, minimum: int | None = None):
        """Return a certified complete bounded scope, or retain the old route."""
        if type(project) is not str:
            return None
        if not self.db.execute("""SELECT EXISTS(SELECT 1 FROM meta WHERE key='bm25_revision'
            AND value=(SELECT value FROM meta WHERE key='revision'))""").fetchone()[0]:
            # An already-open lexical-aware older writer remains compatible.
            # Its revision trigger invalidates this derived index atomically;
            # reads fall back until a current opener/writer rebuilds it.
            return None
        corpus = self.db.execute("SELECT documents,tokens FROM bm25_corpus WHERE route=0").fetchone()
        if corpus is None or corpus[0] < (MIN_ARCHIVE_PAGES if minimum is None else minimum):
            return None
        # Read at most one more page than the budget. Do not accidentally turn
        # a partial project prefix into its complete history.
        cursor = self.db.execute(_PROJECT_SQL, (project, MAX_PROJECT_PAGES + 1))
        rows = cursor.fetchall()
        if (len(rows) > MAX_PROJECT_PAGES or any(row["summary_bytes"] is None
                or row["chapter_title"] is None or row["session_title"] is None
                or row["section_ordinal"] is None for row in rows)):
            return None
        if (sum(row["summary_bytes"] for row in rows) > MAX_PROJECT_BYTES or
                sum(row["decoded_bytes"] for row in rows) > MAX_PROJECT_DECODED_BYTES):
            return None
        # Point reads cannot visit foreign postings. Keep the original cursor
        # description so ranked rows remain ordinary sqlite3.Row objects.
        summaries = {}
        for row in rows:
            blob = self.db.execute("SELECT summary FROM bm25_pages WHERE rid=?", (row["rid"],)).fetchone()[0]
            summaries[row["rid"]] = _decode(blob)
        return cursor, rows, summaries, tuple(corpus)

    def phrases(self, tokens: list[str], route: int):
        phrases = []
        for token in tokens:
            normalized = self._tokens(route, token)
            if len(normalized) != 1:
                return None  # Unsupported phrase shape uses actual FTS5.
            phrases.append(normalized[0])
        return phrases

    def _idf(self, route: int, phrases: list[str], documents: int, field: int) -> list[float]:
        result, memo = [], {}
        for term in phrases:
            if term not in memo:
                row = self.db.execute("""SELECT documents,body_documents,metadata_documents
                  FROM bm25_terms WHERE route=? AND term=?""", (route, term)).fetchone()
                count = row[field] if row else 0
                # Same order and floor as SQLite ext/fts5/fts5_aux.c.
                value = math.log((documents - count + 0.5) / (count + 0.5))
                memo[term] = value if value > 0.0 else 1e-6
            result.append(memo[term])
        return result

    @staticmethod
    def _score(length: int, frequencies: dict, phrases: list[str], idfs: list[list[float]],
               average: float, *, metadata: bool = False) -> float:
        score = 0.0
        for part, phrase_idfs in enumerate(idfs):
            for term, idf in zip(phrases, phrase_idfs):
                counts = frequencies.get(term, (0, 0, 0, 0))
                if metadata:
                    frequency = counts[0] * 2.0 + counts[1] * 1.0 + counts[3] * 4.0
                elif part:
                    frequency = counts[2] * 1.0
                else:
                    frequency = sum(count * weight for count, weight in zip(counts, _WEIGHTS))
                score += idf * ((frequency * (1.2 + 1.0)) /
                    (frequency + 1.2 * (1.0 - 0.75 + 0.75 * length / average)))
        return -score

    def ranked_routes(self, project: str | None, tokens: list[str], use_stem: bool,
                      chapter: str | None, session: str | None):
        snapshot = self.project_rows(project)
        if snapshot is None:
            return None
        cursor, rows, summaries, (documents, token_count) = snapshot
        if not documents or not token_count:
            return [[] for _ in range(2 if use_stem else 1)]
        routes, exact_matches = [], []
        for route in range(2 if use_stem else 1):
            phrases = self.phrases(tokens, route)
            if phrases is None:
                return None
            idfs = [self._idf(route, phrases, documents, field) for field in (0, 1)]
            ranked = []
            for row in rows:
                if (chapter is not None and row["chapter_id"] != chapter) or (
                        session is not None and row["session_id"] != session):
                    continue
                length, frequencies = summaries[row["rid"]][route]
                if not any(frequencies.get(term, (0, 0, 0, 0))[2] for term in phrases):
                    continue
                rank = self._score(length, frequencies, phrases, idfs, token_count / documents)
                values = tuple(row)
                ranked.append(sqlite3.Row(cursor, (*values[:2], rank, *values[3:])))
            ranked.sort(key=lambda row: (row["rank"], row["id"]))
            if route == 0:
                exact_matches = ranked
            routes.append(ranked[:96])
        return _ScopedRoutes(routes, exact_matches)

    @staticmethod
    def recent_routes(routes, chapter_ids, quota, remainder):
        result = {}
        for index, chapter_id in enumerate(chapter_ids):
            rows = [row for row in routes.exact_matches if row["chapter_id"] == chapter_id]
            rows.sort(key=lambda row: (row["session_pk"], -row["section_ordinal"],
                                      -row["ordinal"], row["id"]))
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            result[chapter_id] = rows[:quota + (index < remainder)]
        return result

    def directory_hits(self, project: str | None, tokens: list[str], chapter: str | None):
        snapshot = self.project_rows(project)
        if snapshot is None:
            return None
        cursor, rows, summaries, (documents, token_count) = snapshot
        if not documents or not token_count:
            return []
        phrases = self.phrases(tokens, 0)
        if phrases is None:
            return None
        idfs = [self._idf(0, phrases, documents, 2)]
        hits = []
        for row in rows:
            if chapter is not None and row["chapter_id"] != chapter:
                continue
            # Preserve directory's complete ownership checks, including
            # individually valid foreign keys pointing at another project.
            if not (row["project_id"] == row["chapter_project"] == row["session_project"]
                    and row["chapter_id"] == row["session_chapter"] == row["section_chapter"]
                    and row["session_pk"] == row["section_session"]):
                continue
            length, frequencies = summaries[row["rid"]][0]
            if not any(any(frequencies.get(term, (0, 0, 0, 0))[col] for col in (0, 1, 3))
                       for term in phrases):
                continue
            rank = self._score(length, frequencies, phrases, idfs,
                               token_count / documents, metadata=True)
            values = tuple(row)
            hits.append(sqlite3.Row(cursor, (*values[:2], rank, *values[3:])))
        return hits
