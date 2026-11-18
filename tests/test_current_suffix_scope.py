"""Regressions from the independently retained v0.12 suffix-scope review.

These are source-ordering contracts, not a semantic truth classifier. A causal
old-value explanation cannot waive qualifier checks for a different scope.
"""
from __future__ import annotations

import unittest

from memory_book import MemoryBook


def record(sid, body, *, date="2026-01-01T00:00:00Z"):
    return {"project": "workers", "session_id": sid, "task_id": "queue",
            "task_title": "Worker configuration", "title": "Worker configuration",
            "created_at": date, "messages": [{"role": "assistant", "content": body}]}


def first_session(response):
    return response["results"][0]["source_refs"][0]["session_id"]


class CurrentSuffixScopeTests(unittest.TestCase):
    def compare(self, old, later, query, *, count=8):
        with MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
            sources = {}
            for i in range(count):
                source = record(f"decision-{i}", old)
                sources[source["session_id"]] = "ASSISTANT: " + old
                book.ingest(source)
            book.ingest(record("latest", later, date="2026-10-01T00:00:00Z"))
            sources["latest"] = "ASSISTANT: " + later
            replies = {}
            for mode in ("relevance", "current"):
                response = book.recall(query, project="workers", temporal=mode,
                                       limit=1, budget_chars=1200, use_cache=False)
                self.assertEqual(response["context_chars"], len(response["context"]))
                self.assertLessEqual(len(response["context"]), 1200)
                for hit in response["results"]:
                    page = book.read(hit["id"], project="workers", limit=100000)
                    for ref in hit["source_refs"]:
                        self.assertEqual(ref["project"], "workers")
                        original = sources[ref["session_id"]]
                        self.assertEqual(page["content"], original)
                        self.assertIn(original[ref["turn_start"]:ref["turn_end"]], hit["text"])
                replies[mode] = response
            return replies

    def test_old_value_suffix_cannot_add_another_scope_or_condition(self):
        endings = (
            "旧值已撤销{comma}此值仅用于 staging。",
            "旧值已撤销{comma}pending staging approval。",
            "旧值已撤销 for staging。",
            "旧值已撤销且新值仅适用于 staging。",
            "旧值已撤销{comma}若通过审批才生效。",
            "旧值已因只在 staging 试用而弃用。",
            "旧值已因pending staging approval而弃用。",
            "旧值已因timeout=99而弃用。",
            "旧值已因延迟测试失败而弃用{comma}production approval pending。",
        )
        for count in (2, 8):
            for comma in (",", "，"):
                for ending in endings:
                    with self.subTest(count=count, comma=comma, ending=ending):
                        result = self.compare(
                            "Production retry_limit=3. " + "production retry_limit. " * 12,
                            "Production retry_limit=99" + comma + ending.format(comma=comma),
                            "current production retry_limit", count=count)
                        self.assertTrue(first_session(result["relevance"]).startswith("decision-"))
                        self.assertEqual(result["current"]["results"], result["relevance"]["results"])
                        self.assertEqual(result["current"]["context"], result["relevance"]["context"])
                        self.assertNotIn("=99", result["current"]["context"])

    def test_prose_suffix_uses_the_same_source_local_guard(self):
        for comma in (",", "，"):
            with self.subTest(comma=comma):
                result = self.compare(
                    "Production retry limit is 3 retries. " + "production retry limit. " * 12,
                    "Production retry limit is now 99 retries" + comma
                    + "旧值已撤销" + comma + "此值仅用于 staging。",
                    "current production retry limit")
                self.assertTrue(first_session(result["current"]).startswith("decision-"))
                self.assertNotIn("99 retries", result["current"]["context"])

    def test_complete_old_value_explanations_preserve_valid_updates(self):
        endings = ("旧值已因收敛测试失败而弃用。", "旧值已因延迟测试失败而弃用。",
                   "原值已经因latency exceeded expectations而撤销。", "前值已撤销。")
        for comma in (",", "，"):
            for ending in endings:
                with self.subTest(comma=comma, ending=ending):
                    later = "Production retry_limit=7" + comma + ending
                    result = self.compare(
                        "Production retry_limit=3. " + "production retry_limit. " * 12,
                        later, "current production retry_limit")
                    self.assertTrue(first_session(result["relevance"]).startswith("decision-"))
                    self.assertEqual(first_session(result["current"]), "latest")
                    self.assertIn(later, result["current"]["context"])

    def test_temporal_reporting_labels_are_not_distinct_scopes(self):
        for first_label, next_label in (("Original", ""), ("Original", "Corrected"),
                                        ("Initial", "Revised"), ("Current", "Updated")):
            with self.subTest(first_label=first_label, next_label=next_label):
                later = (next_label + " parcel retention is 19 days.").strip()
                result = self.compare(first_label + " parcel retention is 7 days. "
                                      + "parcel retention. " * 12,
                                      later, "current parcel retention")
                self.assertTrue(first_session(result["relevance"]).startswith("decision-"))
                self.assertEqual(first_session(result["current"]), "latest")
                self.assertIn("19 days", result["current"]["context"])

    def test_reporting_label_support_does_not_erase_explicit_scope(self):
        for earlier, later in (("Production", "Staging"), ("Original production", "Corrected staging"),
                               ("EU production", "EU staging")):
            with self.subTest(earlier=earlier, later=later):
                result = self.compare(earlier + " parcel retention is 7 days. "
                                      + "parcel retention. " * 12,
                                      later + " parcel retention is 99 days.", "current parcel retention")
                # Reporting labels on different environments must not collapse
                # them into one unscoped declaration.
                self.assertTrue(first_session(result["current"]).startswith("decision-"))
                self.assertNotIn("99 days", result["current"]["context"])


if __name__ == "__main__":
    unittest.main()
