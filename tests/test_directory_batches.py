"""Golden directory compatibility, bounded reads, and snapshot ownership."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from memory_book import MemoryBook
from memory_book.store import _integer, _string


def baseline_chapter(book, chapter_id, *, project=None, offset=0, limit=50, page_limit=20):
    """The v0.9.0 chapter implementation, using the unchanged section API."""
    _integer(offset, "offset", 0, 10_000_000)
    _integer(limit, "limit", 1, 100)
    _integer(page_limit, "page_limit", 1, 100)
    if project is not None:
        _string(project, "project")
    scope = " AND project_id=?" if project is not None else ""
    parameters = (chapter_id, project) if project is not None else (chapter_id,)
    row = book.db.execute("SELECT * FROM chapters WHERE id=?" + scope, parameters).fetchone()
    if row is None:
        raise KeyError(f"chapter not found: {chapter_id}")
    total = book.db.execute("SELECT COUNT(*) FROM sections WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
    rows = book.db.execute("SELECT sec.*,s.external_id session_id,s.title session_title,s.created_at FROM sections sec JOIN sessions s ON s.id=sec.session_pk WHERE sec.chapter_id=? ORDER BY s.created_at,s.id,sec.ordinal LIMIT ? OFFSET ?", (chapter_id, limit, offset)).fetchall()
    sections = []
    for sec in rows:
        preview = book.section(sec["id"], project=project, limit=page_limit)
        sections.append({**dict(sec), "pages": preview["pages"], "pages_total": preview["total"], "pages_next_offset": preview["next_offset"]})
    return {**dict(row), "sections": sections, "total": total, "next_offset": offset + limit if offset + limit < total else None}


def payload(index, *, project="alpha", long=True):
    answer = ("\n\n".join(f"Evidence {index}:{part}: 原始约束 must remain addressable without changing source order." for part in range(9))
              if long else f"Short evidence {index}.")
    return {"project": project, "project_name": "Directory fixture", "session_id": f"session-{index}",
            "task_id": "shared-task", "task_title": "A task directory", "title": f"Session {index}",
            "created_at": f"2026-10-0{index % 3 + 1}T08:00:00Z",
            "messages": [{"role": "user", "content": f"Which evidence is from session {index}?"},
                         {"role": "assistant", "content": answer}]}


class DirectoryBatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "book.db"
        self.book = MemoryBook(self.path, segmentation="adaptive", max_page_chars=128, min_page_chars=0)
        self.addCleanup(self.book.close)

    def populate(self, count=20, *, project="alpha", long=True):
        for index in range(count):
            result = self.book.ingest(payload(index, project=project, long=long))
        return result["chapter_id"]

    def assert_golden(self, chapter_id, **options):
        expected = baseline_chapter(self.book, chapter_id, **options)
        actual = self.book.chapter(chapter_id, **options)
        self.assertEqual(actual, expected)
        self.assertEqual(json.dumps(actual, ensure_ascii=False), json.dumps(expected, ensure_ascii=False))
        return actual

    def traced(self, operation):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            result = operation()
        finally:
            self.book.db.set_trace_callback(None)
        return result, statements

    def test_complete_payloads_and_all_pagination_boundaries_match_baseline(self):
        chapter = self.populate()
        self.populate(3, project="alpha's namesake")
        for project in (None, "alpha"):
            for offset, limit, page_limit in ((0, 50, 20), (0, 1, 1), (3, 7, 2),
                                              (19, 1, 100), (20, 100, 100), (10_000_000, 1, 1)):
                with self.subTest(project=project, offset=offset, limit=limit, page_limit=page_limit):
                    self.assert_golden(chapter, project=project, offset=offset, limit=limit, page_limit=page_limit)
        self.assertFalse(self.book.db.in_transaction)

    def test_session_and_turn_modes_keep_their_unsplit_page_contracts(self):
        for mode in ("session", "turn"):
            with self.subTest(mode=mode), MemoryBook(":memory:", segmentation=mode,
                                                    max_page_chars=128, min_page_chars=0) as book:
                for index in range(3):
                    source = payload(index)
                    source["messages"] += [{"role": "user", "content": "A second independent question?"},
                                           {"role": "assistant", "content": "Another original answer. " * 20}]
                    chapter = book.ingest(source)["chapter_id"]
                for offset, limit in ((0, 100), (1, 1), (6, 1)):
                    options = {"project": "alpha", "offset": offset, "limit": limit, "page_limit": 1}
                    expected = baseline_chapter(book, chapter, **options)
                    actual = book.chapter(chapter, **options)
                    self.assertEqual(actual, expected)
                    self.assertEqual(json.dumps(actual, ensure_ascii=False), json.dumps(expected, ensure_ascii=False))
                    self.assertEqual(actual["total"], 3 if mode == "session" else 6)
                    self.assertTrue(all(section["pages_total"] == 1 and section["pages_next_offset"] is None
                                        for section in actual["sections"]))

    def test_empty_sections_empty_chapter_and_duplicate_page_ordinals_match(self):
        chapter = self.populate(3)
        sections = baseline_chapter(self.book, chapter)["sections"]
        self.book.db.execute("DELETE FROM pages WHERE section_id=?", (sections[0]["id"],))
        self.book.db.execute("UPDATE pages SET ordinal=0 WHERE section_id=?", (sections[1]["id"],))
        directory = self.assert_golden(chapter, page_limit=3)
        self.assertEqual((directory["sections"][0]["pages"], directory["sections"][0]["pages_total"],
                          directory["sections"][0]["pages_next_offset"]), ([], 0, None))
        self.book.db.execute("DELETE FROM sections WHERE chapter_id=?", (chapter,))
        empty, statements = self.traced(lambda: self.assert_golden(chapter))
        self.assertEqual((empty["sections"], empty["total"], empty["next_offset"]), ([], 0, None))
        self.assertFalse(any("FROM pages" in sql for sql in statements))

    def test_selected_sections_share_counts_and_keep_original_indexed_preview_queries(self):
        chapter = self.populate(100)
        for selected in (1, 20, 100):
            with self.subTest(sections=selected):
                options = {"limit": selected, "page_limit": 3}
                expected, old_sql = self.traced(lambda: baseline_chapter(self.book, chapter, **options))
                actual, sql = self.traced(lambda: self.book.chapter(chapter, **options))
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual["sections"]), selected)
                self.assertEqual(sum(statement.startswith("SELECT") for statement in old_sql), 3 + 3 * selected)
                self.assertEqual(sum(statement.startswith("SELECT") for statement in sql), 4 + selected)
                self.assertEqual([statement for statement in sql if not statement.startswith("SELECT")], ["BEGIN", "ROLLBACK"])
                prefix = "SELECT id,title,length(content) chars,source_refs FROM pages WHERE section_id="
                previews = [statement for statement in sql if statement.startswith(prefix)]
                self.assertEqual(previews, [statement for statement in old_sql if statement.startswith(prefix)])
                self.assertEqual(len(previews), selected)
                for preview_sql in previews:
                    plan = [row[3] for row in self.book.db.execute("EXPLAIN QUERY PLAN " + preview_sql)]
                    self.assertEqual(sum("SEARCH pages USING INDEX pages_section" in detail for detail in plan), 1)
                    self.assertFalse(any(detail.startswith("SCAN pages") or "USE TEMP B-TREE" in detail for detail in plan), plan)

    def test_maximum_directory_materializes_only_selected_limited_previews(self):
        chapter = self.populate(101, long=False)
        selected = baseline_chapter(self.book, chapter, limit=100, page_limit=1)["sections"]
        rows = []
        for section in selected:
            original = self.book.db.execute("SELECT * FROM pages WHERE section_id=?", (section["id"],)).fetchone()
            for ordinal in range(1, 101):
                refs = "malformed beyond preview" if ordinal == 100 else json.dumps([{"turn_index": 2}, {"turn_index": 0}, {"turn_index": 2}])
                rows.append((original["id"] + f"-extra-{ordinal}", original["section_id"], original["session_pk"],
                             original["chapter_id"], original["project_id"], f"Extra page {ordinal}", "Question",
                             f"Evidence page {ordinal} 字符", refs, ordinal))
        self.book.db.executemany("INSERT INTO pages(id,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        omitted = baseline_chapter(self.book, chapter, offset=100, limit=1)["sections"][0]
        self.book.db.execute("UPDATE pages SET source_refs='malformed omitted section' WHERE section_id=?", (omitted["id"],))
        expected = baseline_chapter(self.book, chapter, limit=100, page_limit=100)
        evaluated = []
        self.book.db.create_function("length", 1, lambda value: evaluated.append(value) or len(value))
        decoded = []
        decode = json.loads

        def decode_preview(raw):
            # Reading another section before converting this one would retain
            # more than one section's raw previews at the conversion boundary.
            self.assertLessEqual(len(evaluated) - len(decoded), 100)
            result = decode(raw)
            decoded.append(True)
            return result

        with patch("memory_book.store.json.loads", side_effect=decode_preview):
            actual, statements = self.traced(lambda: self.book.chapter(chapter, limit=100, page_limit=100))
        self.assertEqual(actual, expected)
        self.assertEqual(len(evaluated), 10_000)
        self.assertEqual(len(decoded), 10_000)
        self.assertEqual(sum(statement.startswith("SELECT") for statement in statements), 104)
        self.assertEqual(actual["next_offset"], 100)
        self.assertTrue(all(len(section["pages"]) == 100 and section["pages_total"] == 101
                            and section["pages_next_offset"] == 100 for section in actual["sections"]))

    def test_exact_scope_and_validation_errors_match_baseline(self):
        chapter = self.populate(2)
        for options in ({"project": "elsewhere"}, {"project": " alpha"}, {"project": ""},
                        {"project": True}, {"offset": -1}, {"limit": 101}, {"page_limit": 0},
                        {"offset": True}, {"limit": 1.0}, {"page_limit": 101}):
            with self.subTest(options=options):
                with self.assertRaises((KeyError, ValueError)) as expected:
                    baseline_chapter(self.book, chapter, **options)
                with self.assertRaises(type(expected.exception)) as actual:
                    self.book.chapter(chapter, **options)
                self.assertEqual(actual.exception.args, expected.exception.args)
                self.assertFalse(self.book.db.in_transaction)
        with self.assertRaisesRegex(KeyError, "chapter not found: missing"):
            self.book.chapter("missing")

    def test_scoped_section_owner_validation_is_not_bypassed(self):
        chapter = self.populate(1)
        foreign = self.populate(1, project="beta")
        foreign_section = baseline_chapter(self.book, foreign)["sections"][0]["id"]
        # Legal foreign keys alone do not require section/session project agreement.
        self.book.db.execute("UPDATE sections SET chapter_id=? WHERE id=?", (chapter, foreign_section))
        self.assert_golden(chapter)
        with self.assertRaises(KeyError) as expected:
            baseline_chapter(self.book, chapter, project="alpha")
        with self.assertRaises(KeyError) as actual:
            self.book.chapter(chapter, project="alpha")
        self.assertEqual(actual.exception.args, expected.exception.args)
        self.assertFalse(self.book.db.in_transaction)

    def test_instance_section_override_keeps_original_calls_and_transaction_behavior(self):
        chapter = self.populate(3)
        ordinary = self.book.section
        transaction_states = []

        def customized(*arguments, **options):
            transaction_states.append(self.book.db.in_transaction)
            return ordinary(*arguments, **options)

        override = Mock(side_effect=customized)
        with patch.object(self.book, "section", override):
            expected = baseline_chapter(self.book, chapter, project="alpha", page_limit=2)
            override.reset_mock()
            transaction_states.clear()
            actual, sql = self.traced(lambda: self.book.chapter(chapter, project="alpha", page_limit=2))
        self.assertEqual(actual, expected)
        self.assertEqual(override.call_count, 3)
        self.assertTrue(all(call.kwargs == {"project": "alpha", "limit": 2} for call in override.call_args_list))
        # The chapter wrapper still does not own a transaction around custom
        # readers. Each delegated ordinary section now owns its read snapshot.
        self.assertEqual(transaction_states, [False, False, False])
        self.assertEqual([statement for statement in sql if statement in {"BEGIN", "ROLLBACK", "COMMIT"}],
                         ["BEGIN", "ROLLBACK"] * 3)
        self.assertFalse(self.book.db.in_transaction)
        self.book.db.execute("BEGIN")
        try:
            transaction_states.clear()
            with patch.object(self.book, "section", override):
                inside, sql = self.traced(lambda: self.book.chapter(chapter, project="alpha", page_limit=2))
            self.assertEqual(inside, expected)
            self.assertEqual(transaction_states, [True, True, True])
            self.assertFalse(any(statement in {"BEGIN", "ROLLBACK", "COMMIT"} for statement in sql))
            self.assertTrue(self.book.db.in_transaction)
        finally:
            self.book.db.execute("ROLLBACK")

    def test_class_and_subclass_section_overrides_are_not_bypassed(self):
        chapter = self.populate(3)
        original = MemoryBook.section
        calls = []

        def customized(book, identity, **options):
            calls.append(identity)
            preview = original(book, identity, **options)
            preview["pages"][0]["title"] = "Customized section preview"
            return preview

        with patch.object(MemoryBook, "section", customized):
            self.assert_golden(chapter)
            self.assertEqual(len(calls), 6)

        class CustomizedBook(MemoryBook):
            section = customized

        with CustomizedBook(self.path) as customized_book:
            expected = baseline_chapter(customized_book, chapter)
            calls.clear()
            self.assertEqual(customized_book.chapter(chapter), expected)
            self.assertEqual(len(calls), 3)

    def test_original_method_bound_to_another_book_is_still_an_override(self):
        chapter = self.populate(1)
        with MemoryBook(":memory:") as other, patch.object(self.book, "section", other.section):
            with self.assertRaises(KeyError) as expected:
                baseline_chapter(self.book, chapter)
            with self.assertRaises(KeyError) as actual:
                self.book.chapter(chapter)
            self.assertEqual(actual.exception.args, expected.exception.args)

    def test_caller_transaction_keeps_uncommitted_changes_and_ownership(self):
        chapter = self.populate(2)
        with MemoryBook(self.path) as observer:
            before = observer.chapter(chapter)["title"]
            self.book.db.execute("BEGIN")
            try:
                self.book.db.execute("UPDATE chapters SET title='Pending caller title' WHERE id=?", (chapter,))
                actual, sql = self.traced(lambda: self.assert_golden(chapter))
                self.assertEqual(actual["title"], "Pending caller title")
                self.assertTrue(self.book.db.in_transaction)
                self.assertEqual(observer.chapter(chapter)["title"], before)
                self.assertFalse(any(statement in {"BEGIN", "ROLLBACK", "COMMIT"} for statement in sql))
            finally:
                self.book.db.execute("ROLLBACK")
        self.assertEqual(self.book.chapter(chapter)["title"], before)

    def test_decode_failures_release_only_the_owned_snapshot(self):
        chapter = self.populate(1)
        page = self.book.chapter(chapter)["sections"][0]["pages"][0]["id"]
        for caller_transaction in (True, False):
            with self.subTest(caller_transaction=caller_transaction):
                if caller_transaction:
                    self.book.db.execute("BEGIN")
                    self.book.db.execute("INSERT INTO meta VALUES('caller-pending','yes')")
                self.book.db.execute("UPDATE pages SET source_refs='malformed' WHERE id=?", (page,))
                with self.assertRaises(json.JSONDecodeError):
                    self.book.chapter(chapter)
                self.assertEqual(self.book.db.in_transaction, caller_transaction)
                if caller_transaction:
                    self.assertEqual(self.book.db.execute("SELECT value FROM meta WHERE key='caller-pending'").fetchone()[0], "yes")
                    self.book.db.execute("ROLLBACK")
                    self.assert_golden(chapter)

    def test_sql_failure_releases_owned_snapshot(self):
        chapter = self.populate(1)

        def authorize(action, table, column, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table == "pages" and column == "source_refs" else sqlite3.SQLITE_OK

        self.book.db.set_authorizer(authorize)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                self.book.chapter(chapter)
            self.assertFalse(self.book.db.in_transaction)
        finally:
            # Passing None to disable the authorizer is supported only in 3.11+.
            self.book.db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
        self.assert_golden(chapter)

    def test_wal_delete_and_reingest_cannot_mix_directory_generations(self):
        chapter = self.populate(4)
        before = baseline_chapter(self.book, chapter)
        failures, triggered = [], []
        with MemoryBook(self.path, segmentation="adaptive", max_page_chars=128, min_page_chars=0) as writer:
            def concurrent_update(statement):
                if not triggered and "FROM pages WHERE section_id" in statement:
                    triggered.append(True)
                    try:
                        writer.delete_session("alpha", "session-0")
                        changed = payload(1)
                        changed["messages"][1]["content"] = "Replacement evidence with a different page address."
                        writer.ingest(changed)
                    except BaseException as exc:
                        failures.append(exc)

            self.book.db.set_trace_callback(concurrent_update)
            try:
                actual = self.book.chapter(chapter)
            finally:
                self.book.db.set_trace_callback(None)
            self.assertEqual(triggered, [True])
            self.assertFalse(failures, failures)
            self.assertEqual(actual, before)
            self.assertFalse(self.book.db.in_transaction)
            after = baseline_chapter(self.book, chapter)
            self.assertNotEqual(after, before)
            self.assertEqual(self.book.chapter(chapter), after)


if __name__ == "__main__":
    unittest.main()
