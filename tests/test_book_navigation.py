"""Book identity, directory lookup and complete original-turn navigation."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.segmentation import make_turns


def record(project="route-kernel", session="same-session", *, question="Which retryLimit applies?",
           answer="retryLimit=3. uniquebodymarker remains in the original evidence.",
           task="configuration", title="Configuration checkpoint"):
    return {"project": project, "project_name": "Routing Kernel", "session_id": session,
            "task_id": task, "task_title": "Retry configuration", "title": title,
            "created_at": "2026-11-01T00:00:00Z",
            "messages": [{"role": "user", "content": question},
                         {"role": "assistant", "content": answer}]}


class BookNavigationTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:")
        self.addCleanup(self.book.close)

    def pair(self):
        own = self.book.ingest(record())
        other = self.book.ingest(record("route_kernel", answer="retryLimit=9. Neighbor policy."))
        return own, other

    def test_multiple_books_require_identity_before_returning_any_evidence(self):
        self.pair()
        for extra in ({}, {"limit": 1}, {"session": "same-session"},
                      {"budget_chars": 0}, {"use_cache": False}):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "Multiple project books"):
                self.book.recall("retryLimit", **extra)
            self.assertFalse(self.book.db.in_transaction)

    def test_empty_and_single_book_resolution_preserve_explicit_response(self):
        self.assertEqual(self.book.recall("retryLimit")["results"], [])
        self.book.ingest(record())
        implicit = self.book.recall("retryLimit", use_cache=False)
        explicit = self.book.recall("retryLimit", project="route-kernel", use_cache=False)
        implicit.pop("latency_ms")
        explicit.pop("latency_ms")
        self.assertEqual(implicit, explicit)

    def test_exact_project_ids_disambiguate_identical_names_and_session_ids(self):
        projects = ("route-kernel", "route_kernel", "Route-Kernel", "route-kernel-v2")
        for index, project in enumerate(projects):
            self.book.ingest(record(project, answer=f"retryLimit={index + 3}."))
        self.assertEqual({p["name"] for p in self.book.projects()}, {"Routing Kernel"})
        for index, project in enumerate(projects):
            result = self.book.recall("retryLimit", project=project)
            self.assertIn(f"retryLimit={index + 3}.", result["context"])
            self.assertEqual({r["project"] for hit in result["results"] for r in hit["source_refs"]}, {project})
        self.assertEqual(self.book.recall("retryLimit", project="Routing Kernel")["results"], [])
        self.assertEqual(self.book.recall("retryLimit", project="missing")["results"], [])

    def test_chapter_id_resolves_owning_book_without_query_guessing(self):
        own, other = self.pair()
        result = self.book.recall("retryLimit", chapter=own["chapter_id"])
        self.assertTrue(result["results"])
        self.assertEqual({r["breadcrumb"][0]["id"] for r in result["results"]}, {"route-kernel"})
        self.assertEqual(self.book.recall("retryLimit", chapter="ch_unknown")["results"], [])
        self.assertEqual(self.book.recall("retryLimit", project="route-kernel", chapter=other["chapter_id"])["results"], [])

    def test_global_search_is_explicit_and_warns_even_at_limit_one(self):
        self.pair()
        result = self.book.recall("retryLimit", all_projects=True, limit=1)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(any("explicitly enabled" in warning for warning in result["warnings"]))
        for value in (None, 0, 1, "true", [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "boolean"):
                self.book.recall("retryLimit", all_projects=value)
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            self.book.recall("retryLimit", project="route-kernel", all_projects=True)

    def test_blank_selectors_never_broaden_scope(self):
        self.pair()
        for key in ("project", "chapter", "session"):
            for value in ("", " ", "\x00", "\ud800"):
                with self.subTest(key=key, value=repr(value)), self.assertRaises(ValueError):
                    self.book.recall("retryLimit", **{key: value})

    def test_cached_single_book_response_does_not_bypass_new_ambiguity(self):
        self.book.ingest(record())
        first = self.book.recall("retryLimit")
        self.assertFalse(first["cache_hit"])
        self.assertTrue(self.book.recall("retryLimit")["cache_hit"])
        self.book.ingest(record("route_kernel"))
        with self.assertRaises(ValueError):
            self.book.recall("retryLimit")
        self.assertTrue(self.book.recall("retryLimit", project="route-kernel")["results"])
        self.assertTrue(self.book.recall("retryLimit", all_projects=True)["results"])

    def test_directory_matches_identifiers_and_titles_but_not_body_only_terms(self):
        self.pair()
        for query in ("retry_limit", "Configuration checkpoint", "Retry configuration"):
            result = self.book.search_directory(query, "route-kernel")
            self.assertEqual(result["total"], 1)
            entry = result["entries"][0]
            self.assertEqual(entry["breadcrumb"][0]["id"], "route-kernel")
            self.assertNotIn("content", entry)
            self.assertNotIn("uniquebodymarker", str(entry))
            self.assertEqual(entry["source_refs"], [{"project": "route-kernel",
                             "session_id": "same-session", "turn_index": 0}])
        self.assertEqual(self.book.search_directory("uniquebodymarker", "route-kernel")["entries"], [])
        self.assertEqual(self.book.search_directory("unrelatedmissingterm", "route-kernel")["entries"], [])
        self.assertTrue(self.book.recall("uniquebodymarker", project="route-kernel")["results"])

    def test_directory_scope_precedes_limit_and_continuations_do_not_crowd_sections(self):
        with MemoryBook(":memory:", max_page_chars=150, min_page_chars=50) as book:
            for index in range(30):
                book.ingest(record("neighbor", f"neighbor-{index}"))
            book.ingest(record(answer="retryLimit=3. " * 100))
            book.ingest(record(session="second", task="other"))
            first = book.search_directory("retry_limit", "route-kernel", limit=1)
            second = book.search_directory("retry_limit", "route-kernel", offset=first["next_offset"], limit=1)
            self.assertEqual(first["total"], 2)
            self.assertEqual(second["total"], 2)
            self.assertIsNone(second["next_offset"])
            entries = first["entries"] + second["entries"]
            self.assertEqual(len({entry["section_id"] for entry in entries}), 2)
            self.assertTrue(any(entry["page_count"] > 1 for entry in entries))
            self.assertTrue(all(entry["breadcrumb"][0]["id"] == "route-kernel" for entry in entries))

    def test_wrong_book_navigation_ids_are_rejected(self):
        own, other = self.pair()
        chapter = self.book.chapter(other["chapter_id"], project="route_kernel")
        section_id = chapter["sections"][0]["id"]
        page_id = chapter["sections"][0]["pages"][0]["id"]
        for method, identity in ((self.book.chapter, other["chapter_id"]),
                                 (self.book.section, section_id), (self.book.read, page_id)):
            self.assertTrue(method(identity, project="route_kernel"))
            with self.subTest(method=method.__name__), self.assertRaises(KeyError):
                method(identity, project="route-kernel")
            with self.assertRaises(ValueError):
                method(identity, project="")
        self.assertTrue(self.book.chapter(own["chapter_id"], project="route-kernel"))

    def test_complete_original_turn_roundtrip_survives_page_splitting(self):
        payload = record(question="Explain the complete retry configuration.",
                         answer="前置条件。" + "Unicode 😀 retryLimit=3.\n" * 120 + "最终边界。")
        with MemoryBook(":memory:", max_page_chars=150, min_page_chars=50) as book:
            book.ingest(payload)
            entry = book.search_directory("retry configuration", "route-kernel")["entries"][0]
            self.assertGreater(entry["page_count"], 1)
            page = book.read(entry["matched_page_id"], project="route-kernel")
            chunks, offset = [], 0
            while offset is not None:
                result = book.read_turn("route-kernel", "same-session", 0, offset=offset,
                                        limit=37, source_hash=page["source_hash"])
                self.assertLessEqual(len(result["content"]), 37)
                self.assertEqual(result["source_ref"]["turn_start"], offset)
                self.assertEqual(result["source_ref"]["turn_end"], offset + len(result["content"]))
                chunks.append(result["content"])
                offset = result["next_offset"]
            self.assertEqual("".join(chunks), make_turns(payload["messages"])[0].content)
            self.assertEqual(result["message_indices"], [0, 1])

    def test_original_turn_source_hash_rejects_replacement_between_chunks(self):
        payload = record()
        self.book.ingest(payload)
        first = self.book.read_turn("route-kernel", "same-session", 0, limit=10)
        payload["messages"][1]["content"] = "Replacement retryLimit=8."
        self.book.ingest(payload)
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.book.read_turn("route-kernel", "same-session", 0, offset=10,
                                source_hash=first["source_hash"])
        replacement = self.book.read_turn("route-kernel", "same-session", 0)
        self.assertNotEqual(replacement["source_hash"], first["source_hash"])
        self.assertIn("retryLimit=8", replacement["content"])

    def test_original_turn_is_scoped_bounded_and_validates_its_coordinates(self):
        self.pair()
        self.assertIn("retryLimit=3", self.book.read_turn("route-kernel", "same-session", 0)["content"])
        self.assertIn("retryLimit=9", self.book.read_turn("route_kernel", "same-session", 0)["content"])
        for project, session, turn in (("missing", "same-session", 0),
                                       ("route-kernel", "missing", 0), ("route-kernel", "same-session", 99)):
            with self.subTest(project=project, session=session, turn=turn), self.assertRaises(KeyError):
                self.book.read_turn(project, session, turn)
        tail = self.book.read_turn("route-kernel", "same-session", 0, offset=10000)
        self.assertEqual(tail["content"], "")
        self.assertIsNone(tail["next_offset"])
        self.assertEqual(tail["source_ref"]["turn_start"], tail["source_ref"]["turn_end"])
        for options in ({"offset": -1}, {"limit": 0}, {"offset": True}, {"source_hash": "wrong"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.book.read_turn("route-kernel", "same-session", 0, **options)
        with self.assertRaises(ValueError):
            self.book.read_turn("route-kernel", "same-session", True)

    def test_long_original_question_does_not_escape_chunk_budget_in_metadata(self):
        self.book.ingest(record(question="Long question " * 10000))
        result = self.book.read_turn("route-kernel", "same-session", 0, limit=1)
        self.assertEqual(len(result["content"]), 1)
        self.assertLessEqual(len(result["question"]), 240)

    def test_nested_directory_calls_preserve_callers_transaction(self):
        own, _ = self.pair()
        self.book.db.execute("BEGIN")
        try:
            self.book.toc("route-kernel")
            self.book.search_directory("retry", "route-kernel")
            self.book.chapter(own["chapter_id"], project="route-kernel")
            self.book.read_turn("route-kernel", "same-session", 0)
            self.assertTrue(self.book.db.in_transaction)
            with self.assertRaises(KeyError):
                self.book.chapter(own["chapter_id"], project="route_kernel")
            self.assertTrue(self.book.db.in_transaction)
        finally:
            self.book.db.execute("ROLLBACK")

    def test_navigation_snapshot_remains_coherent_during_another_writer_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as reader, MemoryBook(path) as writer:
                payload = record()
                own = writer.ingest(payload)
                changed = False

                def replace_after_project_read(statement):
                    nonlocal changed
                    if not changed and "COUNT(DISTINCT p.section_id)" in statement:
                        changed = True
                        replacement = copy.deepcopy(payload)
                        replacement["messages"][0]["content"] = "Different checkpoint question?"
                        writer.ingest(replacement)

                reader.db.set_trace_callback(replace_after_project_read)
                result = reader.search_directory("retry_limit", "route-kernel")
                reader.db.set_trace_callback(None)
                self.assertTrue(changed)
                self.assertEqual(result["revision"], own["revision"])
                self.assertEqual(result["total"], 1)
                self.assertEqual(result["entries"][0]["title"], payload["messages"][0]["content"])
                self.assertGreater(reader.revision, result["revision"])


if __name__ == "__main__":
    unittest.main()
