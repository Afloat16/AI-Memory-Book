"""Artificial integration checks for native-row I and the opt-in T1 path.

These fixtures contain invented text only. They perform no corpus selection,
benchmark, model call, timing comparison, or performance acceptance.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


def without_timing(response, *, provenance=False):
    result = {key: value for key, value in response.items() if key != "latency_ms"}
    if provenance:
        result.pop("title_reference", None)
    return result


class NativeTitleReferenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.book = MemoryBook(Path(self.temporary.name) / "memory.db",
                               segmentation="turn", min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        for project, identity, title, content in (
            ("lab", "anchor", "Calibration memo",
             "quartzsignal points to Cedar Observatory. quartzsignal is recorded here."),
            ("lab", "target", "Cedar Observatory",
             "The instruments stand beside the northern inlet."),
            ("outside", "target", "Cedar Observatory",
             "outsidecanary belongs only to another project."),
        ):
            self.book.ingest({
                "project": project, "session_id": identity, "title": title,
                "task_id": "archive", "task_title": "Evidence archive",
                "created_at": "2025-01-01T00:00:00Z",
                "messages": [{"role": "user", "content": content}],
            })

    def recall(self, **options):
        arguments = {"project": "lab", "budget_chars": 2000, "limit": 5,
                     "use_cache": False}
        arguments.update(options)
        return self.book.recall("quartzsignal", **arguments)

    def observed_recall(self, **options):
        original = store._candidate_rows
        connections = []

        def capture(cursor, description, connection=None):
            connections.append(connection)
            return original(cursor, description, connection)

        with patch.object(store, "_candidate_rows", side_effect=capture):
            result = self.recall(**options)
        return result, connections

    def test_default_and_inactive_option_keep_native_behavior(self):
        for options, reason in (
            ({}, None),
            ({"project": None}, "project_required"),
            ({"limit": 1}, "limit_below_two"),
        ):
            with self.subTest(options=options):
                expected, default_connections = self.observed_recall(**options)
                self.assertTrue(default_connections)
                self.assertTrue(all(value is self.book.db for value in default_connections))
                flag = reason is not None
                actual, connections = self.observed_recall(follow_titles=flag, **options)
                self.assertTrue(connections)
                self.assertTrue(all(value is self.book.db for value in connections))
                self.assertEqual(without_timing(actual, provenance=flag),
                                 without_timing(expected))
                if flag:
                    self.assertFalse(actual["title_reference"]["active"])
                    self.assertEqual(actual["title_reference"]["reason"], reason)
                else:
                    self.assertNotIn("title_reference", actual)
        self.assertIs(self.book.db.row_factory, sqlite3.Row)
        self.assertIs(self.book._native_db, self.book.db)

    def test_active_hop_uses_full_rows_without_disabling_later_native_calls(self):
        before, _ = self.observed_recall()
        result, connections = self.observed_recall(follow_titles=True)
        self.assertTrue(connections)
        self.assertTrue(all(value is None for value in connections))
        state = result["title_reference"]
        self.assertTrue(state["active"])
        self.assertTrue(state["applied"])
        self.assertEqual(state["target"]["session_id"], "target")
        self.assertEqual(state["target"]["route"], "title_reference")
        self.assertEqual(result["results"][0]["id"], before["results"][0]["id"])
        self.assertIn("northern inlet", result["context"])
        self.assertNotIn("outsidecanary", result["context"])
        self.assertIs(self.book.db.row_factory, sqlite3.Row)
        self.assertIs(self.book._native_db, self.book.db)
        after, connections = self.observed_recall()
        self.assertTrue(connections)
        self.assertTrue(all(value is self.book.db for value in connections))
        self.assertEqual(without_timing(before), without_timing(after))

    def test_custom_factory_is_observed_and_preserves_complete_payloads(self):
        for enabled in (False, True):
            with self.subTest(follow_titles=enabled):
                expected = self.recall(follow_titles=enabled)
                descriptions = []

                def factory(cursor, values):
                    descriptions.append(tuple(column[0] for column in cursor.description))
                    return sqlite3.Row(cursor, values)

                self.book.db.row_factory = factory
                try:
                    actual = self.recall(follow_titles=enabled)
                finally:
                    self.book.db.row_factory = sqlite3.Row
                self.assertIn(("rid", "id", "rank"), descriptions)
                self.assertEqual(without_timing(actual), without_timing(expected))
                self.assertIs(self.book._native_db, self.book.db)


if __name__ == "__main__":
    unittest.main()
