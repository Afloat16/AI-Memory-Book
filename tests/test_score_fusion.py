"""Independent fixtures fixed before the score-aware development comparison."""

from __future__ import annotations

import unittest

from memory_book import MemoryBook


class ControlledFusionTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)

    def add(self, sid, text, project="notes", title="Local record"):
        self.book.ingest({
            "project": project, "session_id": sid, "title": title,
            "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": "An archived note"},
                         {"role": "assistant", "content": text}],
        })

    def assert_source_and_budget(self, response, budget):
        self.assertLessEqual(len(response["context"]), budget)
        self.assertEqual(response["context_chars"], len(response["context"]))
        for result in response["results"]:
            page = self.book.read(result["id"])["content"]
            for lo, hi in result["excerpt_spans"]:
                self.assertIn(page[lo:hi], result["text"])
            self.assertTrue(result["source_refs"])
            for ref in result["source_refs"]:
                self.assertIn(page[ref["start"]:ref["end"]], result["text"])

    def test_exact_multi_term_fact_survives_porter_collision_distractors(self):
        fact = "The universe expansion calibration uses a constant of 71."
        self.add("cosmology", fact)
        for number in range(12):
            self.add(f"admissions-{number}",
                     "University expansion calibration is discussed in the admissions orientation. " * 3,
                     title="University expansion calibration")
        response = self.book.recall("universe expansion calibration", project="notes",
                                    limit=1, budget_chars=300, use_cache=False)
        self.assertIn(fact, response["context"])
        self.assertEqual(response["results"][0]["source_refs"][0]["session_id"], "cosmology")
        self.assert_source_and_budget(response, 300)

    def test_missing_exact_word_form_still_returns_original_evidence(self):
        fact = "At the conference, Mira received badge Kestrel-42."
        self.add("event", "Earlier travel notes remain archived for reference. " * 24 + "\n\n" + fact)
        response = self.book.recall("conferences", project="notes", limit=1,
                                    budget_chars=300, use_cache=False)
        self.assertIn(fact, response["context"])
        self.assert_source_and_budget(response, 300)

    def test_scope_prevents_stronger_foreign_evidence_from_entering_results(self):
        fact = "A conference in Tallinn issued badge Kestrel-42."
        self.add("local", fact)
        for number in range(12):
            self.add(f"foreign-{number}", "Conference conferences conference.", project="other")
        response = self.book.recall("conferences", project="notes", budget_chars=300,
                                    limit=5, use_cache=False)
        self.assertIn(fact, response["context"])
        self.assertTrue(all(ref["project"] == "notes"
                            for hit in response["results"] for ref in hit["source_refs"]))
        self.assert_source_and_budget(response, 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
