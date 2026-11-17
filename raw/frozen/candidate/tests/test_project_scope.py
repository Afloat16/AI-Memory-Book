"""Keep a known project attached to directory and original-evidence reads."""

from __future__ import annotations

import unittest

from memory_book import MemoryBook


def session(project: str, answer: str, *, sid: str = "same-session") -> dict:
    return {
        "project": project,
        "project_name": "Similar algorithm service",
        "task_id": "same-task",
        "task_title": "Retry configuration",
        "session_id": sid,
        "title": "Retry configuration",
        "created_at": "2026-10-01T08:00:00Z",
        "messages": [
            {"role": "user", "content": "What is the retry configuration?"},
            {"role": "assistant", "content": answer},
        ],
    }


class ProjectScopeTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="adaptive", max_page_chars=180,
                               min_page_chars=0)
        self.addCleanup(self.book.close)
        self.ids = {}
        for project, value in (("algorithm-alpha", "45 seconds"),
                               ("algorithm-beta", "90 seconds")):
            ingested = self.book.ingest(session(project, f"Retry delay is {value}."))
            chapter = self.book.chapter(ingested["chapter_id"])
            section = chapter["sections"][0]
            self.ids[project] = {
                "chapter": chapter["id"],
                "section": section["id"],
                "read": section["pages"][0]["id"],
            }

    def test_scoped_navigation_retains_complete_unscoped_payloads(self):
        """Same labels do not merge books, tasks, source sessions, or page reads."""
        for project, ids in self.ids.items():
            with self.subTest(project=project):
                for method, identity in ids.items():
                    operation = getattr(self.book, method)
                    self.assertEqual(operation(identity, project=project), operation(identity))
                    self.assertEqual(operation(identity, project=None), operation(identity))
                page = self.book.read(ids["read"], project=project)
                self.assertEqual(page["breadcrumb"][0]["id"], project)
                self.assertEqual({ref["project"] for ref in page["source_refs"]}, {project})
                self.assertEqual({ref["session_id"] for ref in page["source_refs"]},
                                 {"same-session"})
        self.assertNotEqual(self.ids["algorithm-alpha"], self.ids["algorithm-beta"])

    def test_foreign_ids_fail_with_the_same_error_as_missing_ids(self):
        """An ID carried over from another engineering task is not opened."""
        for method, foreign_id in self.ids["algorithm-beta"].items():
            operation = getattr(self.book, method)
            with self.subTest(method=method):
                with self.assertRaises(KeyError) as wrong:
                    operation(foreign_id, project="algorithm-alpha")
                with self.assertRaises(KeyError) as unknown:
                    operation(foreign_id, project="unknown-project")
                self.assertEqual(wrong.exception.args, unknown.exception.args)
                self.assertNotIn("algorithm-beta", str(wrong.exception))
                self.assertNotIn("90 seconds", str(wrong.exception))
                # Deliberately unscoped archive navigation remains available.
                self.assertTrue(operation(foreign_id))

    def test_project_ids_are_exact_and_never_broaden_after_a_miss(self):
        for project in (" algorithm-alpha", "algorithm-alpha ", "ALGORITHM-ALPHA",
                        "algorithm", "algorithm-alpha' OR 1=1--"):
            for method, identity in self.ids["algorithm-alpha"].items():
                with self.subTest(project=project, method=method), self.assertRaises(KeyError):
                    getattr(self.book, method)(identity, project=project)
        quoted = "algorithm's-copy"
        saved = self.book.ingest(session(quoted, "Retry delay is 15 seconds."))
        chapter = self.book.chapter(saved["chapter_id"], project=quoted)
        section = self.book.section(chapter["sections"][0]["id"], project=quoted)
        page = self.book.read(section["pages"][0]["id"], project=quoted)
        self.assertEqual(page["breadcrumb"][0]["id"], quoted)
        self.assertIn("15 seconds", page["content"])

    def test_invalid_project_scope_is_rejected_without_changing_the_archive(self):
        before = (self.book.revision, self.book.export())
        for project in ("", " \t", "bad\x00project", "bad\ud800project", True, 1,
                        [], "x" * 501):
            for method, identity in self.ids["algorithm-alpha"].items():
                with self.subTest(project=repr(project), method=method), self.assertRaises(ValueError):
                    getattr(self.book, method)(identity, project=project)
        self.assertEqual((self.book.revision, self.book.export()), before)

    def test_project_follows_all_directory_and_original_text_pagination(self):
        project = "algorithm-alpha"
        answer = "\n\n".join(
            f"Alpha evidence {index}: retry behavior must retain its complete original constraint."
            for index in range(18)
        )
        saved = self.book.ingest(session(project, answer, sid="long-session"))
        self.book.ingest(session("algorithm-beta", answer.replace("Alpha", "Beta"),
                                 sid="long-session"))
        chapter_offset = 0
        seen_sections, seen_pages = set(), set()
        while True:
            chapter = self.book.chapter(saved["chapter_id"], project=project,
                                        offset=chapter_offset, limit=1, page_limit=1)
            self.assertEqual(chapter, self.book.chapter(saved["chapter_id"],
                             offset=chapter_offset, limit=1, page_limit=1))
            for preview in chapter["sections"]:
                seen_sections.add(preview["id"])
                section_offset = 0
                while True:
                    section = self.book.section(preview["id"], project=project,
                                                offset=section_offset, limit=1)
                    self.assertEqual(section, self.book.section(preview["id"],
                                     offset=section_offset, limit=1))
                    for page in section["pages"]:
                        seen_pages.add(page["id"])
                        parts, page_offset = [], 0
                        while True:
                            part = self.book.read(page["id"], project=project,
                                                 offset=page_offset, limit=37)
                            self.assertEqual(part, self.book.read(page["id"],
                                             offset=page_offset, limit=37))
                            self.assertTrue(all(ref["project"] == project
                                                for ref in part["source_refs"]))
                            parts.append(part["content"])
                            if part["next_offset"] is None:
                                break
                            page_offset = part["next_offset"]
                        text = "".join(parts)
                        self.assertEqual(text, self.book.read(page["id"])["content"])
                        self.assertNotIn("Beta evidence", text)
                    if section["next_offset"] is None:
                        break
                    section_offset = section["next_offset"]
            if chapter["next_offset"] is None:
                break
            chapter_offset = chapter["next_offset"]
        self.assertGreater(len(seen_sections), 1)
        self.assertGreater(len(seen_pages), len(seen_sections))

    def test_source_replacement_cannot_redirect_an_old_page_to_a_namesake(self):
        alpha_old = self.ids["algorithm-alpha"]["read"]
        beta_id = self.ids["algorithm-beta"]["read"]
        beta_before = self.book.read(beta_id, project="algorithm-beta")
        self.book.ingest(session("algorithm-alpha", "Retry delay is now 120 seconds."))
        for project in ("algorithm-alpha", "algorithm-beta"):
            with self.subTest(project=project), self.assertRaises(KeyError):
                self.book.read(alpha_old, project=project)
        self.assertEqual(self.book.read(beta_id, project="algorithm-beta"), beta_before)
        recalled = self.book.recall("retry delay", project="algorithm-alpha")
        self.assertIn("120 seconds", recalled["context"])
        for hit in recalled["results"]:
            page = self.book.read(hit["id"], project="algorithm-alpha")
            self.assertEqual({ref["project"] for ref in page["source_refs"]},
                             {"algorithm-alpha"})

    def test_project_deletion_does_not_fall_back_to_matching_foreign_labels(self):
        beta_id = self.ids["algorithm-beta"]["read"]
        beta_before = self.book.read(beta_id, project="algorithm-beta")
        self.book.delete_project("algorithm-alpha")
        for ids in self.ids.values():
            for method, identity in ids.items():
                with self.subTest(method=method, identity=identity), self.assertRaises(KeyError):
                    getattr(self.book, method)(identity, project="algorithm-alpha")
        self.assertEqual(self.book.read(beta_id, project="algorithm-beta"), beta_before)


if __name__ == "__main__":
    unittest.main()
