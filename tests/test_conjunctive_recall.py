"""Independent multi-fact source, scope and budget checks."""

from __future__ import annotations

import unittest

from memory_book import MemoryBook


class ConjunctiveRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)

    def add(self, sid, text, *, project="lab", task="calibration"):
        return self.book.ingest({
            "project": project, "session_id": sid, "task_id": task,
            "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": "Archived instrument note"},
                         {"role": "assistant", "content": text}],
        })

    def assert_sources(self, response, budget):
        self.assertLessEqual(len(response["context"]), budget)
        self.assertEqual(response["context_chars"], len(response["context"]))
        for result in response["results"]:
            page = self.book.read(result["id"])["content"]
            for lo, hi in result["excerpt_spans"]:
                self.assertIn(page[lo:hi], result["text"])
            self.assertTrue(result["source_refs"])
            for ref in result["source_refs"]:
                self.assertIn(page[ref["start"]:ref["end"]], result["text"])

    def populate(self, chinese=False):
        primary = ("转子校准偏移为四十一毫伏。" if chinese else
                   "Rotor calibration offset is 41 millivolts.")
        secondary = ("接收器公差为零点七分贝。" if chinese else
                     "Receiver tolerance is 0.7 decibels.")
        for i in range(12):
            record = self.add(f"rotor-{i}", primary * 3)
        self.add("receiver", secondary + "\n" +
                 "The technician kept the instrument manual available in the laboratory. " * 25)
        return primary, secondary, record

    def test_both_requested_facts_survive_repeated_first_subject(self):
        primary, secondary, _ = self.populate()
        result = self.book.recall("rotor calibration offset and receiver tolerance",
                                  project="lab", limit=2, budget_chars=600,
                                  use_cache=False)
        self.assertIn(primary, result["context"])
        self.assertIn(secondary, result["context"])
        self.assert_sources(result, 600)

    def test_chinese_conjunction_keeps_independent_source_evidence(self):
        primary, secondary, _ = self.populate(chinese=True)
        result = self.book.recall("转子校准偏移和接收器公差", project="lab",
                                  limit=2, budget_chars=600, use_cache=False)
        self.assertIn(primary, result["context"])
        self.assertIn(secondary, result["context"])
        self.assert_sources(result, 600)

    def test_each_requested_scope_is_enforced_for_clause_results(self):
        _, secondary, record = self.populate()
        for i in range(110):
            self.add(f"foreign-{i}", "Receiver tolerance is 99 decibels.", project="other")
        for scope in ({"project": "lab"}, {"chapter": record["chapter_id"]}):
            with self.subTest(scope=scope):
                result = self.book.recall("rotor calibration offset and receiver tolerance",
                                          limit=2, budget_chars=600,
                                          use_cache=False, **scope)
                self.assertIn(secondary, result["context"])
                self.assertTrue(all(ref["project"] == "lab"
                                    for hit in result["results"] for ref in hit["source_refs"]))
                self.assert_sources(result, 600)
        result = self.book.recall("rotor calibration offset and receiver tolerance",
                                  session="rotor-0", limit=2, budget_chars=600,
                                  use_cache=False)
        self.assertNotIn(secondary, result["context"])
        self.assertTrue(all(ref["session_id"] == "rotor-0"
                            for hit in result["results"] for ref in hit["source_refs"]))
        self.assert_sources(result, 600)

    def test_first_result_is_unchanged_with_only_one_slot(self):
        self.populate()
        query = "rotor calibration offset and receiver tolerance"
        single = self.book.recall(query, project="lab", limit=1,
                                  budget_chars=600, use_cache=False)
        combined = self.book.recall(query, project="lab", limit=2,
                                    budget_chars=600, use_cache=False)
        self.assertEqual(single["results"][0]["id"], combined["results"][0]["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
