"""Exact semantic results and transaction cleanup across bounded vector batches."""

import importlib.util
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from memory_book import semantic


def reference_rank_pages(db, model, query, where, params):
    """The ranking body frozen at 238c8058f723a203eaca99f94d924ab77de4c0b3."""
    rows = db.execute("""SELECT p.id,p.rid,p.project_id,p.chapter_id,
        c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at,
        v.ordinal,v.vector FROM semantic_vectors v JOIN pages p ON p.id=v.page_id
        JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
        WHERE 1=1""" + where + " ORDER BY p.id,v.ordinal", params).fetchall()
    if not rows:
        return []
    query_vectors = model.encode_query(query)
    if not len(query_vectors):
        return []
    np = model.np
    best = {}
    for start in range(0, len(rows), 4096):
        chunk = rows[start:start + 4096]
        if any(len(row["vector"]) != semantic.DIMENSIONS * 4 for row in chunk):
            raise semantic.SemanticIndexError("Semantic index vector dimensions are invalid; rebuild it")
        matrix = np.frombuffer(b"".join(row["vector"] for row in chunk), dtype="<f4").reshape(-1, semantic.DIMENSIONS)
        if not np.isfinite(matrix).all():
            raise semantic.SemanticIndexError("Semantic index contains non-finite values; rebuild it")
        similarities = np.einsum("ij,kj->ik", matrix, query_vectors, optimize=False).max(axis=1)
        for row, similarity in zip(chunk, similarities):
            score = float(similarity)
            if row["id"] not in best or score > best[row["id"]]["semantic_similarity"]:
                item = {key: row[key] for key in row.keys() if key not in {"vector", "ordinal"}}
                item["semantic_similarity"] = score
                best[row["id"]] = item
    return sorted(best.values(), key=lambda row: (-row["semantic_similarity"], row["id"]))[:semantic.CANDIDATE_LIMIT]


def fixture_database(window_count, *, windows_per_page=3, path=":memory:"):
    import numpy as np
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE pages (id TEXT PRIMARY KEY, rid INTEGER, project_id TEXT,
                            chapter_id TEXT, session_pk TEXT);
        CREATE TABLE chapters (id TEXT PRIMARY KEY, title TEXT);
        CREATE TABLE sessions (id TEXT PRIMARY KEY, external_id TEXT, title TEXT, created_at TEXT);
        CREATE TABLE semantic_vectors (page_id TEXT, ordinal INTEGER, vector BLOB,
                                       PRIMARY KEY(page_id,ordinal));
    """)
    db.executemany("INSERT INTO chapters VALUES(?,?)", ((f"c-{n}", f"Chapter {n}") for n in range(4)))
    db.executemany("INSERT INTO sessions VALUES(?,?,?,?)",
                   ((f"s-{n}", f"external-{n}", f"Session {n}", "2026-01-01") for n in range(8)))
    db.execute("BEGIN")
    for number in range(window_count):
        page, ordinal = divmod(number, windows_per_page)
        page_id = f"page-{page:06d}"
        if ordinal == 0:
            db.execute("INSERT INTO pages VALUES(?,?,?,?,?)",
                       (page_id, page, f"p-{page % 2}", f"c-{page % 4}", f"s-{page % 8}"))
        vector = np.zeros(semantic.DIMENSIONS, dtype="<f4")
        # Repeated scores exercise deterministic page-ID ties. Three windows
        # put a page across the 4,096-row boundary, including a later winner.
        vector[0] = ((page % 17) - 8 + ordinal) / 16
        vector[1] = ((page % 5) - 2 - ordinal) / 8
        vector[9] = (ordinal - 1) / 4
        db.execute("INSERT INTO semantic_vectors VALUES(?,?,?)", (page_id, ordinal, vector.tobytes()))
    db.execute("COMMIT")
    return db


@unittest.skipUnless(importlib.util.find_spec("numpy"), "optional semantic vector tests need NumPy")
class SemanticStreamingTests(unittest.TestCase):
    def model(self, encode=None):
        import numpy as np
        queries = np.zeros((2, semantic.DIMENSIONS), dtype="<f4")
        queries[0, 0] = 1
        queries[1, 0], queries[1, 1], queries[1, 9] = 0.5, 0.25, -0.5
        return SimpleNamespace(np=np, encode_query=encode or (lambda query: queries))

    def test_exact_results_at_batch_edges_and_scopes(self):
        for windows in (0, 1, 4095, 4096, 4097, 8195):
            with self.subTest(windows=windows):
                db = fixture_database(windows)
                try:
                    for where, params in (("", []), (" AND p.project_id=?", ["p-1"]),
                                          (" AND p.chapter_id=? AND s.external_id=?", ["c-2", "external-6"]),
                                          (" AND p.project_id=?", ["missing"])):
                        model = self.model()
                        expected = reference_rank_pages(db, model, "fixture", where, params)
                        self.assertEqual(semantic.rank_pages(db, model, "fixture", where, params), expected)
                finally:
                    db.close()

    def test_page_winner_after_batch_boundary_and_signed_scores(self):
        db = fixture_database(4098, windows_per_page=4098)
        try:
            # A single page spans batches. Its final window must still win;
            # replacing every vector with a negative one also retains a page.
            result = semantic.rank_pages(db, self.model(), "fixture", "", [])
            self.assertEqual(result, reference_rank_pages(db, self.model(), "fixture", "", []))
            self.assertEqual(len(result), 1)
            vector = self.model().np.zeros(semantic.DIMENSIONS, dtype="<f4")
            vector[0], vector[1] = -1, -1
            db.execute("UPDATE semantic_vectors SET vector=?", (vector.tobytes(),))
            result = semantic.rank_pages(db, self.model(), "fixture", "", [])
            self.assertEqual(result[0]["semantic_similarity"], -0.75)
        finally:
            db.close()

    def test_late_corruption_is_rejected_even_outside_top_candidates(self):
        import numpy as np
        db = fixture_database(4097, windows_per_page=1)
        try:
            for kind, value in (("dimensions", b"bad"), ("non-finite", float("nan")),
                                ("non-finite", float("inf")), ("non-finite", float("-inf"))):
                with self.subTest(value=value):
                    if not isinstance(value, bytes):
                        vector = np.zeros(semantic.DIMENSIONS, dtype="<f4")
                        vector[0] = value
                        value = vector.tobytes()
                    db.execute("UPDATE semantic_vectors SET vector=? WHERE page_id='page-004096'", (value,))
                    with self.assertRaisesRegex(semantic.SemanticIndexError, kind):
                        semantic.rank_pages(db, self.model(), "fixture", "", [])
        finally:
            db.close()

    def test_empty_scope_does_not_encode_and_empty_query_skips_validation(self):
        db = fixture_database(1)
        try:
            def fail(query):
                self.fail("An empty scope must not initialize query inference")
            self.assertEqual(semantic.rank_pages(db, self.model(fail), "fixture", " AND p.id=?", ["missing"]), [])
            db.execute("UPDATE semantic_vectors SET vector=?", (b"invalid",))
            self.assertEqual(semantic.rank_pages(db, self.model(lambda query: []), "fixture", "", []), [])
        finally:
            db.close()

    def test_encoder_failure_and_empty_query_release_read_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.db"
            db = fixture_database(4097, path=path)
            writer = sqlite3.connect(path, timeout=0, isolation_level=None)
            failure = None
            try:
                def fail(query):
                    raise RuntimeError("query fixture failure")
                try:
                    semantic.rank_pages(db, self.model(fail), "fixture", "", [])
                except RuntimeError as exc:
                    failure = exc  # Retain traceback locals, including the cursor.
                self.assertIsNotNone(failure)
                self.assertEqual(str(failure), "query fixture failure")
                writer.execute("UPDATE sessions SET title='after failure'")
                self.assertEqual(semantic.rank_pages(db, self.model(lambda query: []), "fixture", "", []), [])
                writer.execute("UPDATE sessions SET title='after empty query'")
            finally:
                writer.close()
                db.close()

    def test_caller_snapshot_survives_concurrent_writer(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.db"
            db = fixture_database(4097, windows_per_page=1, path=path)
            db.execute("PRAGMA journal_mode=WAL").fetchone()
            writer = sqlite3.connect(path, isolation_level=None)
            try:
                expected = reference_rank_pages(db, self.model(), "fixture", "", [])
                regular_encode = self.model().encode_query
                def write_during_encode(query):
                    vector = np.zeros(semantic.DIMENSIONS, dtype="<f4")
                    vector[0] = 100
                    writer.execute("UPDATE semantic_vectors SET vector=? WHERE page_id='page-004096'", (vector.tobytes(),))
                    return regular_encode(query)
                db.execute("BEGIN")
                self.assertEqual(semantic.rank_pages(db, self.model(write_during_encode), "fixture", "", []), expected)
                self.assertTrue(db.in_transaction)
                db.execute("COMMIT")
                refreshed = semantic.rank_pages(db, self.model(), "fixture", "", [])
                self.assertEqual(refreshed[0]["id"], "page-004096")
                self.assertEqual(refreshed[0]["semantic_similarity"], 100)
            finally:
                writer.close()
                db.close()


if __name__ == "__main__":
    unittest.main()
