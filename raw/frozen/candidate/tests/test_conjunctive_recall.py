"""Independent multi-fact source, scope and budget checks."""

from __future__ import annotations

import hashlib
import json
import unittest

from memory_book import MemoryBook


def seed_conjunctive_book(book, chinese=False):
    """Put the same facts on unequal-length pages with repeated first-subject notes."""
    primary = ("转子校准偏移为四十一毫伏。" if chinese else
               "Rotor calibration offset is 41 millivolts.")
    secondary = ("接收器公差为零点七分贝。" if chinese else
                 "Receiver tolerance is 0.7 decibels.")
    texts = [(f"rotor-{i}", primary * 3) for i in range(12)]
    texts.append(("receiver", secondary + "\n" +
                  "The technician kept the instrument manual available in the laboratory. " * 25))
    # Other archived material makes the repeated first topic a relevant but
    # non-universal part of the collection. These pages contain neither topic.
    texts.extend((f"inventory-{i}", "The optics cabinet contains spare lenses and cleaning cloths.")
                 for i in range(32))
    for sid, text in texts:
        record = book.ingest({
            "project": "lab", "session_id": sid, "task_id": "calibration",
            "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": "Archived instrument note"},
                         {"role": "assistant", "content": text}],
        })
    return primary, secondary, record


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
        return seed_conjunctive_book(self.book, chinese)

    def test_both_requested_facts_survive_repeated_first_subject(self):
        primary, secondary, _ = self.populate()
        result = self.book.recall("rotor calibration offset and receiver tolerance",
                                  project="lab", limit=2, budget_chars=600,
                                  use_cache=False, coverage=True)
        self.assertIn(primary, result["context"])
        self.assertIn(secondary, result["context"])
        self.assert_sources(result, 600)

    def test_chinese_conjunction_keeps_independent_source_evidence(self):
        primary, secondary, _ = self.populate(chinese=True)
        result = self.book.recall("转子校准偏移和接收器公差", project="lab",
                                  limit=2, budget_chars=600, use_cache=False, coverage=True)
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
                                          use_cache=False, coverage=True, **scope)
                self.assertIn(secondary, result["context"])
                self.assertTrue(all(ref["project"] == "lab"
                                    for hit in result["results"] for ref in hit["source_refs"]))
                self.assert_sources(result, 600)
        result = self.book.recall("rotor calibration offset and receiver tolerance",
                                  session="rotor-0", limit=2, budget_chars=600,
                                  use_cache=False, coverage=True)
        self.assertNotIn(secondary, result["context"])
        self.assertTrue(all(ref["session_id"] == "rotor-0"
                            for hit in result["results"] for ref in hit["source_refs"]))
        self.assert_sources(result, 600)

    def test_first_result_is_unchanged_with_only_one_slot(self):
        self.populate()
        query = "rotor calibration offset and receiver tolerance"
        single = self.book.recall(query, project="lab", limit=1,
                                  budget_chars=600, use_cache=False, coverage=True)
        combined = self.book.recall(query, project="lab", limit=2,
                                    budget_chars=600, use_cache=False, coverage=True)
        self.assertEqual(single["results"][0]["id"], combined["results"][0]["id"])

    def test_coverage_is_optional_and_cache_entries_cannot_cross_modes(self):
        _, secondary, _ = self.populate()
        self.book.cache_size = 8
        arguments = {"project": "lab", "limit": 2, "budget_chars": 600}
        query = "rotor calibration offset and receiver tolerance"
        default = self.book.recall(query, **arguments)
        covered = self.book.recall(query, coverage=True, **arguments)
        self.assertFalse(default["cache_hit"])
        self.assertFalse(covered["cache_hit"])
        self.assertNotIn(secondary, default["context"])
        self.assertIn(secondary, covered["context"])
        for flag, expected in ((False, default), (True, covered)):
            cached = self.book.recall(query, coverage=flag, **arguments)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(cached["context"], expected["context"])
            self.assertEqual(cached["results"], expected["results"])
        self.assertEqual(self.book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0], 2)

    def test_prior_automatic_coverage_cache_is_not_reused(self):
        self.populate()
        self.book.cache_size = 8
        query = "rotor calibration offset and receiver tolerance"
        old_fields = [3, 8, query, "lab", None, None, 600, 2, "book"]
        old_key = hashlib.sha256(json.dumps(old_fields, ensure_ascii=False,
                                          sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.book.db.execute("INSERT INTO recall_cache VALUES(?,?,?,?)",
                             (old_key, self.book.revision, '{"context":"old automatic coverage"}', 0))
        for flag in (False, True):
            result = self.book.recall(query, project="lab", limit=2,
                                      budget_chars=600, coverage=flag)
            self.assertFalse(result["cache_hit"])
            self.assertNotEqual(result["context"], "old automatic coverage")

    def test_coverage_validation_rejects_ambiguous_values_and_flat_combination(self):
        for value in (None, "false", "true", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "boolean"):
                self.book.recall("rotor calibration", coverage=value)
        with self.assertRaisesRegex(ValueError, "book strategy"):
            self.book.recall("rotor calibration", strategy="flat", coverage=True)
        self.book.recall("rotor calibration", strategy="flat", coverage=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
