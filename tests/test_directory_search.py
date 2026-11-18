"""Development contracts for indexed, project-scoped directory discovery.

These authored fixtures test a new navigation API. They are not a held-out
retrieval benchmark, and the preceding release has no equivalent API to score.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.directory import search_directory


# Fixed before implementing the directory API. No answer labels are supplied
# to the locator: only ordinary canonical session inputs are indexed.
DIRECTORY_FIXTURES = (
    ("algorithm-alpha", "routing", "NebulaRPC transport routing", "connection-review",
     "Connection review", "The selected retry limit is seven attempts."),
    ("algorithm-alpha", "monitoring", "NebulaRPC monitoring", "monitoring-review",
     "Monitoring review", "Metrics use the existing collector."),
    ("algorithm-beta", "routing", "NebulaRPC transport routing", "connection-review",
     "Connection review", "The selected retry limit is eleven attempts."),
    ("algorithm-alpha", "training", "训练流水线变更与优化器配置", "optimizer-review",
     "参数复核", "保留既有配置，下一步先复核日志。"),
    ("algorithm-alpha", "identifiers", "HTTPRetryPolicy maxRetryCount", "api-review",
     "Client API review", "The relevant setting has already been approved."),
)


def payload(row, *, turns=1):
    project, task, title, session, session_title, answer = row
    messages = []
    for index in range(turns):
        messages.extend([
            {"role": "user", "content": f"Review checkpoint {index}: what was agreed?"},
            {"role": "assistant", "content": answer},
        ])
    return {
        "project": project, "project_name": "Similar engineering service",
        "task_id": task, "task_title": title,
        "session_id": session, "title": session_title,
        "created_at": "2026-11-01T08:00:00Z", "messages": messages,
    }


class DirectorySearchTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn")
        self.addCleanup(self.book.close)
        self.ids = {}
        for row in DIRECTORY_FIXTURES:
            saved = self.book.ingest(payload(row, turns=24 if row is DIRECTORY_FIXTURES[0] else 1))
            self.ids[(row[0], row[1])] = saved["chapter_id"]

    def search(self, query, **options):
        return search_directory(self.book, query, **options)

    def test_title_only_hit_locates_metadata_without_claiming_body_evidence(self):
        self.assertEqual(self.book.recall("NebulaRPC", project="algorithm-alpha")["context"], "")
        response = self.search("NebulaRPC", project="algorithm-alpha")
        self.assertEqual(response["result_type"], "directory")
        self.assertFalse(response["evidence"])
        self.assertEqual(response["scope"], {"project": "algorithm-alpha", "chapter": None})
        self.assertEqual(response["revision"], self.book.revision)
        self.assertEqual(response["total"], 2)

        def check_keys(value):
            if isinstance(value, dict):
                self.assertFalse({"content", "context", "source_refs", "excerpt"} & value.keys())
                for nested in value.values():
                    check_keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    check_keys(nested)

        check_keys(response)

    def test_many_pages_do_not_displace_a_second_matching_chapter(self):
        response = self.search("NebulaRPC", project="algorithm-alpha", limit=2)
        self.assertEqual({item["chapter_id"] for item in response["results"]},
                         {self.ids[("algorithm-alpha", "routing")],
                          self.ids[("algorithm-alpha", "monitoring")]})
        self.assertEqual(response["total"], 2)
        large = next(item for item in response["results"] if item["task_id"] == "task:routing")
        self.assertEqual(large["pages_total"], 24)
        self.assertEqual(large["matching_sections_total"], 24)
        self.assertEqual(len(large["sections"]), 5)
        self.assertTrue(large["sections_truncated"])

    def test_chapter_pagination_is_unique_stable_and_bounded(self):
        first = self.search("NebulaRPC", project="algorithm-alpha", limit=1)
        second = self.search("NebulaRPC", project="algorithm-alpha", limit=1,
                             offset=first["next_offset"])
        self.assertEqual((first["offset"], first["limit"], first["next_offset"]), (0, 1, 1))
        self.assertIsNone(second["next_offset"])
        self.assertEqual(first["total"], second["total"])
        self.assertNotEqual(first["results"][0]["id"], second["results"][0]["id"])
        self.assertEqual(first, self.search("NebulaRPC", project="algorithm-alpha", limit=1))
        past = self.search("NebulaRPC", project="algorithm-alpha", limit=1, offset=20)
        self.assertEqual((past["results"], past["total"], past["next_offset"]), ([], 2, None))

    def test_all_returned_ids_are_real_navigable_and_scoped(self):
        response = self.search("NebulaRPC", project="algorithm-alpha")
        for item in response["results"]:
            self.assertEqual(item["kind"], "chapter")
            self.assertEqual(item["id"], item["chapter_id"])
            chapter = self.book.chapter(item["chapter_id"], project=item["project_id"])
            self.assertEqual((item["title"], item["summary"]), (chapter["title"], chapter["summary"]))
            for preview in item["sections"]:
                section = self.book.section(preview["section_id"], project=item["project_id"])
                self.assertEqual(preview["kind"], "section")
                self.assertEqual(preview["id"], preview["section_id"])
                self.assertEqual(preview["chapter_id"], item["chapter_id"])
                self.assertEqual(preview["project_id"], item["project_id"])
                self.assertEqual(preview["session_id"], section["session_id"])
                self.assertEqual(preview["session_pk"], section["session_pk"])
                self.assertEqual(preview["pages_total"], section["total"])

    def test_scope_precedes_grouping_and_limit(self):
        response = self.search("NebulaRPC", project="algorithm-beta", limit=1)
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["results"][0]["chapter_id"], self.ids[("algorithm-beta", "routing")])
        self.assertEqual({item["project_id"] for item in response["results"]}, {"algorithm-beta"})
        unscoped = self.search("NebulaRPC")
        self.assertEqual(unscoped["total"], 3)
        self.assertEqual(unscoped["scope"], {"project": None, "chapter": None})
        self.assertEqual({item["project_id"] for item in unscoped["results"]},
                         {"algorithm-alpha", "algorithm-beta"})

    def test_chapter_deduplication_preserves_distinct_session_addresses(self):
        source = payload(DIRECTORY_FIXTURES[1])
        source["session_id"] = "monitoring-followup"
        source["title"] = "Follow-up review"
        self.book.ingest(source)
        chapter = self.ids[("algorithm-alpha", "monitoring")]
        response = self.search("NebulaRPC", chapter=chapter)
        self.assertEqual((response["total"], len(response["results"])), (1, 1))
        result = response["results"][0]
        self.assertEqual((result["pages_total"], result["sessions_total"], result["sections_total"]), (2, 2, 2))
        self.assertEqual({row["session_id"] for row in result["sections"]},
                         {"monitoring-review", "monitoring-followup"})
        self.assertEqual(len({row["session_pk"] for row in result["sections"]}), 2)
        self.assertFalse(result["sections_truncated"])

    def test_chapter_scope_is_exact_and_never_broadens_after_a_miss(self):
        chapter = self.ids[("algorithm-alpha", "monitoring")]
        response = self.search("NebulaRPC", chapter=chapter)
        self.assertEqual([item["id"] for item in response["results"]], [chapter])
        self.assertEqual(response["scope"], {"project": None, "chapter": chapter})
        for options in ({"chapter": "missing"}, {"chapter": "NebulaRPC monitoring"},
                        {"chapter": chapter.upper()}, {"chapter": chapter, "project": "algorithm-beta"}):
            with self.subTest(options=options), self.assertRaises(KeyError):
                self.search("NebulaRPC", **options)
        for project in ("missing", "ALGORITHM-ALPHA", "algorithm", "x' OR 1=1--"):
            with self.subTest(project=project), self.assertRaises(KeyError):
                self.search("NebulaRPC", project=project)
        with self.assertRaises(KeyError):
            self.search("", project="missing")
        with self.assertRaises(KeyError):
            self.search("", chapter="missing")

    def test_chinese_and_code_identifier_aliases_find_directory_titles(self):
        for query, task in (("训练流水线", "training"), ("优化器配置", "training"),
                            ("HTTPRetryPolicy", "identifiers"), ("http retry policy", "identifiers"),
                            ("max_retry_count", "identifiers"), ("maxRetryCount", "identifiers")):
            with self.subTest(query=query):
                response = self.search(query, project="algorithm-alpha")
                self.assertIn(self.ids[("algorithm-alpha", task)],
                              {item["chapter_id"] for item in response["results"]})

    def test_question_metadata_is_searchable_but_body_only_terms_are_not(self):
        row = ("algorithm-alpha", "incident", "Incident notebook", "incident-42",
               "Daily record", "Bodysecretneedle is an implementation detail.")
        source = payload(row)
        source["messages"][0]["content"] = "Where is the diagnostic handoff?"
        chapter = self.book.ingest(source)["chapter_id"]
        self.assertEqual([item["id"] for item in self.search("diagnostic handoff")["results"]], [chapter])
        self.assertEqual(self.search("Bodysecretneedle")["results"], [])
        self.assertEqual(self.search('\") OR body : "Bodysecretneedle"')["results"], [])

    def test_empty_or_punctuation_query_is_an_empty_search_not_a_browse(self):
        for query in ("", "  ", "?!", '"():*', "the and is"):
            with self.subTest(query=query):
                response = self.search(query, project="algorithm-alpha")
                self.assertEqual((response["results"], response["total"], response["next_offset"]), ([], 0, None))
                self.assertEqual(response["revision"], self.book.revision)

    def test_invalid_inputs_are_rejected_without_changing_archive_or_transaction(self):
        before = self.book.export()
        bad = ({"project": " algorithm-alpha"}, {"project": "algorithm-alpha "},
               {"project": ""}, {"project": True}, {"project": "x" * 201},
               {"project": "bad\x00id"}, {"project": "bad\ud800id"},
               {"chapter": " "}, {"chapter": True}, {"chapter": " ch_id"},
               {"chapter": "x" * 501}, {"chapter": "bad\x00id"},
               {"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": 1.0},
               {"offset": -1}, {"offset": 10_000_001}, {"offset": True})
        for options in bad:
            with self.subTest(options=repr(options)), self.assertRaises(ValueError):
                self.search("NebulaRPC", **options)
        for query in (None, True, [], "x" * 8001, "bad\x00query", "bad\ud800query"):
            with self.subTest(query=repr(query)), self.assertRaises(ValueError):
                self.search(query)
        self.assertEqual(self.book.export(), before)
        self.assertFalse(self.book.db.in_transaction)

    def test_caller_transaction_and_rollback_are_preserved(self):
        chapter = self.ids[("algorithm-alpha", "monitoring")]
        old = self.book.chapter(chapter)["summary"]
        self.book.db.execute("BEGIN")
        try:
            self.book.db.execute("UPDATE chapters SET summary=? WHERE id=?", ("Pending metadata", chapter))
            response = self.search("NebulaRPC", chapter=chapter)
            self.assertEqual(response["results"][0]["summary"], "Pending metadata")
            self.assertTrue(self.book.db.in_transaction)
            with self.assertRaises(KeyError):
                self.search("NebulaRPC", chapter="missing")
            self.assertTrue(self.book.db.in_transaction)
        finally:
            self.book.db.execute("ROLLBACK")
        self.assertEqual(self.book.chapter(chapter)["summary"], old)

    def test_owned_snapshot_closes_on_success_and_sql_error(self):
        self.search("NebulaRPC")
        self.assertFalse(self.book.db.in_transaction)
        self.book.db.execute("ALTER TABLE pages_fts RENAME TO unavailable_fts")
        with self.assertRaises(sqlite3.OperationalError):
            self.search("NebulaRPC")
        self.assertFalse(self.book.db.in_transaction)

    def test_revision_count_results_and_previews_share_one_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.sqlite3"
            with MemoryBook(path, segmentation="turn") as reader, MemoryBook(path, segmentation="turn") as writer:
                reader.ingest(payload(DIRECTORY_FIXTURES[0]))
                old_revision = reader.revision
                triggered = []

                def concurrent_write(sql):
                    if "COUNT(DISTINCT" in sql and not triggered:
                        triggered.append(True)
                        writer.ingest(payload(DIRECTORY_FIXTURES[1]))

                reader.db.set_trace_callback(concurrent_write)
                try:
                    response = search_directory(reader, "NebulaRPC", project="algorithm-alpha")
                finally:
                    reader.db.set_trace_callback(None)
                self.assertEqual(triggered, [True])
                self.assertEqual((response["revision"], response["total"]), (old_revision, 1))
                self.assertEqual(len(response["results"]), 1)
                next_response = search_directory(reader, "NebulaRPC", project="algorithm-alpha")
                self.assertEqual(next_response["total"], 2)
                self.assertGreater(next_response["revision"], old_revision)

    def test_renames_and_source_replacement_use_current_index_and_revision(self):
        row = DIRECTORY_FIXTURES[1]
        source = payload(row)
        source["task_title"] = "CometTracer metrics"
        self.book.ingest(source)
        response = self.search("NebulaRPC", project="algorithm-alpha")
        self.assertEqual(response["total"], 1)
        renamed = self.search("CometTracer", project="algorithm-alpha")
        self.assertEqual(renamed["results"][0]["title"], source["task_title"])
        self.assertEqual(renamed["revision"], self.book.revision)

    def test_lookup_uses_existing_fts_postings_instead_of_scanning_titles(self):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            self.search("NebulaRPC", project="algorithm-alpha")
        finally:
            self.book.db.set_trace_callback(None)
        matched = [sql for sql in statements if "pages_fts MATCH" in sql and not sql.startswith("--")]
        self.assertTrue(matched)
        self.assertTrue(all("{title question directory}" in sql for sql in matched))
        self.assertFalse(any(" LIKE " in sql.upper() for sql in matched))
        for sql in matched:
            plan = [row[3] for row in self.book.db.execute("EXPLAIN QUERY PLAN " + sql)]
            self.assertTrue(any("VIRTUAL TABLE INDEX" in detail and "M" in detail for detail in plan), plan)
        self.assertNotIn("CREATE", "\n".join(statements))


if __name__ == "__main__":
    unittest.main()
