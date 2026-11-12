"""Project-range query plans preserve the original scoped FTS response."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook


def source(project, identity, task="policy"):
    return {"project": project, "session_id": identity, "task_id": task,
            "title": "Policy notes", "task_title": "Reliability policy",
            "created_at": "2025-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": "What is the reliability policy?"},
                         {"role": "assistant", "content": "Needle reliability is checked twice. 缓存保留两小时。"}]}


class ProjectRowidBoundsTests(unittest.TestCase):
    def assert_original_response(self, book, query, **kwargs):
        actual = book.recall(query, use_cache=False, **kwargs)
        with patch.object(book, "_project_rowid_bounds", return_value=None):
            expected = book.recall(query, use_cache=False, **kwargs)
        actual.pop("latency_ms")
        expected.pop("latency_ms")
        self.assertEqual(actual, expected)
        return actual

    def test_scoped_limits_scores_sources_and_single_or_dual_routes_are_unchanged(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            for i in range(150):
                book.ingest(source("outside", str(i)))
            for i in range(100):
                book.ingest(source("target", str(i)))
            self.assertIsNotNone(book._project_rowid_bounds("target"))
            chapter = book.db.execute("SELECT id FROM chapters WHERE project_id='target'").fetchone()[0]
            for query in ("needle reliability", "缓存保留", "unmatchedword"):
                for scope in ({"project": "target"}, {"project": "target", "chapter": chapter},
                              {"project": "target", "session": "0"}, {"project": "missing"},
                              {"project": "outside", "chapter": chapter}, {}):
                    with self.subTest(query=query, scope=scope):
                        response = self.assert_original_response(book, query, budget_chars=2000, **scope)
                        if scope.get("project") == "target":
                            self.assertTrue(all(row["breadcrumb"][0]["id"] == "target" for row in response["results"]))
            response = self.assert_original_response(book, "needle reliability", project="target")
            self.assertEqual(response["candidate_count"], 96)

    def test_interleaved_and_archive_wide_projects_keep_original_plan(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            book.ingest(source("sparse", "first"))
            for i in range(20):
                book.ingest(source("bulk", str(i)))
            book.ingest(source("sparse", "last"))
            self.assertIsNone(book._project_rowid_bounds("sparse"))
            self.assertIsNone(book._project_rowid_bounds("bulk"))
            self.assertIsNone(book._project_rowid_bounds(None))
            self.assertEqual(book._project_rowid_bounds("missing"), (0, -1))
            for project in ("sparse", "bulk"):
                self.assert_original_response(book, "needle reliability", project=project)

    def test_new_snapshot_tracks_other_connection_ingest_delete_and_relink(self):
        with tempfile.TemporaryDirectory(prefix="fts-bounds-", dir=Path(__file__).parent) as directory:
            path = Path(directory) / "memory.db"
            with MemoryBook(path, cache_size=0) as reader, MemoryBook(path, cache_size=0) as writer:
                for i in range(20):
                    writer.ingest(source("bulk", str(i)))
                writer.ingest(source("target", "first"))
                first = reader._project_rowid_bounds("target")
                self.assertIsNotNone(first)
                self.assert_original_response(reader, "needle reliability", project="target")
                writer.ingest(source("target", "second"))
                self.assertGreater(reader._project_rowid_bounds("target")[1], first[1])
                self.assert_original_response(reader, "needle reliability", project="target")
                linked = writer.link_session("target", "second", "new-task", "New policy")
                self.assert_original_response(reader, "needle reliability", project="target", chapter=linked["chapter_id"])
                writer.delete_session("target", "first")
                self.assert_original_response(reader, "needle reliability", project="target")
                writer.delete_project("target")
                self.assertEqual(reader._project_rowid_bounds("target"), (0, -1))
                self.assert_original_response(reader, "needle reliability", project="target")

    def test_result_cache_hits_do_not_recompute_bounds(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("target", "one"))
            with patch.object(book, "_project_rowid_bounds", wraps=book._project_rowid_bounds) as bounds:
                first = book.recall("needle reliability", project="target")
                second = book.recall("needle reliability", project="target")
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(bounds.call_count, 1)


if __name__ == "__main__":
    unittest.main()
