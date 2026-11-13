"""Small source, isolation and connection-lifetime checks for the pager target.

The capture helpers also run unchanged against released v0.3.2 in a separate
process during development, comparing every response field except latency.
The unit tests require neither that checkout nor a benchmark corpus.
"""

from __future__ import annotations

from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

from memory_book import MemoryBook


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


def source_records():
    common = "The relay is orbiting above café. 缓存期限45秒。 The calibration key is amber."
    records = (
        ("lab", "same-a", common),
        ("lab", "same-b", common),
        ("lab", "stem", "The relay orbits above café. 缓存期限45秒。 The calibration key is amber."),
        ("outside", "same-a", "The yellowcanary receiver belongs to another project."),
    )
    return [
        {"project": project, "session_id": session, "task_id": "receiver",
         "task_title": "Receiver records", "title": "Flight notes",
         "created_at": "2025-01-01T00:00:00Z",
         "messages": [{"role": "assistant", "content": text}]}
        for project, session, text in records
    ]


def open_fixture(path, *, cache_size=0):
    book = MemoryBook(path, segmentation="turn", max_page_chars=5000,
                      min_page_chars=0, cache_size=cache_size)
    try:
        for record in source_records():
            book.ingest(record)
    except BaseException:
        book.close()
        raise
    return book


def capture_result(book, result):
    projections = []
    for item in result["results"]:
        page = book.read(item["id"], limit=100000)["content"]
        for ref in item["source_refs"]:
            original = book.db.execute(
                "SELECT content FROM turns WHERE ordinal=? AND session_pk=("
                "SELECT id FROM sessions WHERE project_id=? AND external_id=?)",
                (ref["turn_index"], ref["project"], ref["session_id"]),
            ).fetchone()[0]
            projections.append({
                "page_id": item["id"], "project": ref["project"],
                "session_id": ref["session_id"],
                "page_text": page[ref["start"]:ref["end"]],
                "turn_text": original[ref["turn_start"]:ref["turn_end"]],
            })
    return {
        "payload": {key: value for key, value in result.items() if key != "latency_ms"},
        "projections": projections,
    }


def capture_repeated_queries(*, tokens=False):
    options = {"budget_chars": 2000, "limit": 5, "use_cache": False}
    if tokens:
        options.update(budget_tokens=128, tokenizer="cl100k_base")
    captured = []
    with tempfile.TemporaryDirectory() as directory:
        with open_fixture(Path(directory) / "fixture.db") as book:
            for query in ("orbiting", "orbited", "yellowcanary"):
                for repeat in range(2):
                    result = book.recall(query, project="lab", **options)
                    captured.append({"query": query, "repeat": repeat,
                                     **capture_result(book, result)})
    return captured


def capture_external_update(*, use_cache):
    captured = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.db"
        with open_fixture(path, cache_size=128) as reader:
            def recall(phase):
                result = reader.recall("calibration key", project="lab", session="same-a",
                                       budget_chars=2000, use_cache=use_cache)
                captured.append({"phase": phase, **capture_result(reader, result)})

            recall("before")
            recall("before-repeat")
            changed = source_records()[0]
            changed["messages"] = [{"role": "assistant", "content":
                "The relay is orbiting above café. 缓存期限72秒。 The calibration key is violet."}]
            with MemoryBook(path) as writer:
                writer.ingest(changed)
            recall("after")
            recall("after-repeat")
    return captured


def capture_all_payloads():
    if not HAS_TOKENS:
        raise RuntimeError("The complete page-cache fixture capture requires tiktoken")
    return {
        "sources": source_records(),
        "character": capture_repeated_queries(),
        "token": capture_repeated_queries(tokens=True),
        "external_update_without_result_cache": capture_external_update(use_cache=False),
        "external_update_with_result_cache": capture_external_update(use_cache=True),
    }


class SQLitePageCacheTests(unittest.TestCase):
    def assert_projections(self, records):
        for record in records:
            for projection in record["projections"]:
                self.assertEqual(projection["project"], "lab")
                self.assertEqual(projection["page_text"], projection["turn_text"])
                self.assertTrue(projection["page_text"])

    def assert_repeated_queries(self, records):
        self.assertEqual(len(records), 6)
        self.assert_projections(records)
        for first, repeated in zip(records[::2], records[1::2]):
            self.assertEqual(first["payload"], repeated["payload"])
            payload = first["payload"]
            self.assertFalse(payload["cache_hit"])
            self.assertLessEqual(len(payload["context"]), 2000)
            if first["query"] == "yellowcanary":
                self.assertEqual(payload["results"], [])
                self.assertEqual(payload["context"], "")
            else:
                self.assertTrue(payload["results"])
                self.assertIn("café", payload["context"])
                self.assertIn("缓存", payload["context"])
                self.assertNotIn("yellowcanary", payload["context"])

    def test_repeated_character_queries_keep_ties_unicode_and_sources(self):
        records = capture_repeated_queries()
        self.assert_repeated_queries(records)
        results = records[0]["payload"]["results"]
        ties = {item["source_refs"][0]["session_id"]: item["score"] for item in results}
        self.assertIn("same-a", ties)
        self.assertIn("same-b", ties)
        self.assertEqual(ties["same-a"], ties["same-b"])

    @unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact token-budget checks")
    def test_repeated_token_queries_keep_complete_budgeted_sources(self):
        from memory_book.token_budget import TokenCounter
        records = capture_repeated_queries(tokens=True)
        self.assert_repeated_queries(records)
        counter = TokenCounter("cl100k_base")
        for record in records:
            payload = record["payload"]
            self.assertEqual(payload["context_tokens"], counter.count(payload["context"]))
            self.assertLessEqual(payload["context_tokens"], 128)

    def test_target_is_connection_local_without_persistent_format_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.db"
            with open_fixture(path):
                pass
            with closing(sqlite3.connect(path)) as raw:
                ordinary = raw.execute("PRAGMA main.cache_size").fetchone()[0]

                def snapshot(connection):
                    return (
                        tuple(connection.execute(f"PRAGMA {name}").fetchone()[0]
                              for name in ("page_size", "application_id", "user_version")),
                        tuple(connection.iterdump()),
                    )

                before = snapshot(raw)
                with MemoryBook(path, cache_size=0) as book:
                    self.assertEqual(book.db.execute("PRAGMA main.cache_size").fetchone()[0], -8192)
                    self.assertEqual(book.cache_size, 0)
                    self.assertEqual(raw.execute("PRAGMA main.cache_size").fetchone()[0], ordinary)
                    self.assertEqual(snapshot(raw), before)
                self.assertEqual(snapshot(raw), before)
            with closing(sqlite3.connect(path)) as reopened:
                self.assertEqual(reopened.execute("PRAGMA main.cache_size").fetchone()[0], ordinary)
                self.assertEqual(snapshot(reopened), before)

    def test_empty_in_memory_database_retains_supported_lifetime(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            self.assertEqual(book.db.execute("PRAGMA main.cache_size").fetchone()[0], -8192)
            self.assertEqual(book.stats()["pages"], 0)
            self.assertEqual(book.cache_size, 0)

    def test_warm_reader_observes_other_writer_and_result_cache_revision(self):
        for use_cache in (False, True):
            with self.subTest(use_cache=use_cache):
                records = capture_external_update(use_cache=use_cache)
                self.assert_projections(records)
                self.assertEqual([record["payload"]["cache_hit"] for record in records],
                                 [False, use_cache, False, use_cache])
                for record in records:
                    context = record["payload"]["context"]
                    if record["phase"].startswith("before"):
                        self.assertIn("amber", context)
                        self.assertNotIn("violet", context)
                    else:
                        self.assertIn("violet", context)
                        self.assertNotIn("amber", context)
                    self.assertTrue(all(projection["session_id"] == "same-a"
                                        for projection in record["projections"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
