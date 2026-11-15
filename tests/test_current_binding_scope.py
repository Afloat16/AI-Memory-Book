"""Cross-source freshness needs more than a repeated topic mention.

Independent lease/queue examples: these do not import benchmark fixtures,
expected policy lists, scorers or external retrieval components.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store
from memory_book.store import _current_binding_keys


def record(identity, body, *, day="2026-01-01", project="harbor", task="leases", question="Lease settings"):
    return {"project": project, "session_id": identity, "task_id": task,
            "title": question, "task_title": "Lease settings", "created_at": day + "T09:00:00Z",
            "messages": [{"role": "user", "content": question}, {"role": "assistant", "content": body}]}


def first_session(result):
    return result["results"][0]["source_refs"][0]["session_id"]


class CurrentBindingScopeTests(unittest.TestCase):
    def test_only_literal_queried_properties_with_values_supply_a_binding_key(self):
        cases = [
            ("Lease policy: lease.ttl=30.", "current lease.ttl", {("assignment", "lease.ttl")}),
            ('cache.mode="write through"', "current cache.mode", {("assignment", "cache.mode")}),
            ("Queue capacity is now 16.", "current queue capacity", {("numeric_phrase", "queue capacity")}),
            ("Queue capacity is now 16.", "current capacity", set()),
            ("Inspected lease.ttl during the handover.", "current lease.ttl", set()),
            ("archive.ttl=30", "current lease.ttl", set()),
            ("lease.ttl=30", "current archive.lease.ttl", set()),
            ("lease.ttl == 30", "current lease.ttl", set()),
            ("lease.ttl=", "current lease.ttl", set()),
        ]
        for content, query, expected in cases:
            with self.subTest(content=content, query=query):
                self.assertEqual(_current_binding_keys(content, query), expected)

    def test_property_punctuation_and_multiple_query_properties_are_not_conflated(self):
        self.assertEqual(_current_binding_keys("lease.ttl=30", "current lease_ttl"), set())
        query = "current lease.ttl and cache.size"
        self.assertEqual(_current_binding_keys("lease.ttl=30; cache.size was inspected.", query), set())
        self.assertEqual(_current_binding_keys("lease.ttl=30; cache.size=64", query),
                         {("assignment", "lease.ttl"), ("assignment", "cache.size")})

    def test_numeric_phrase_only_strips_one_explicit_temporal_prefix(self):
        expected = {("numeric_phrase", "queue capacity")}
        for phrase in ("Original queue capacity is 4.", "Previous queue capacity is 8.",
                       "Current queue capacity is 16."):
            with self.subTest(phrase=phrase):
                self.assertEqual(_current_binding_keys(phrase, "current queue capacity"), expected)
        for phrase in ("Backup queue capacity is 8.", "Originals queue capacity is 8.",
                       "Original previous queue capacity is 8.", "As of queue capacity is 8."):
            with self.subTest(phrase=phrase):
                self.assertEqual(_current_binding_keys(phrase, "current queue capacity"), set())
        self.assertEqual(_current_binding_keys("Original Retry_Limit is 8.", "current retry_limit"), set())
        self.assertEqual(_current_binding_keys("original_retry_limit=8", "current retry_limit"), set())

    def test_code_property_case_and_numeric_statement_syntax_remain_distinct(self):
        self.assertEqual(_current_binding_keys("Retry_Limit=9", "current retry_limit"), set())
        self.assertEqual(_current_binding_keys("retry_limit=2", "current retry_limit"),
                         {("assignment", "retry_limit")})
        self.assertNotEqual(_current_binding_keys("capacity=2", "current capacity"),
                            _current_binding_keys("capacity is 3.", "current capacity"))
        self.assertEqual(_current_binding_keys("Queue capacity is 2.", "current queue capacity"),
                         _current_binding_keys("queue capacity is now 3.", "current queue capacity"))
        with MemoryBook(":memory:") as book:
            book.ingest(record("lowercase", "retry_limit=2."))
            book.ingest(record("uppercase", "Retry_Limit=9. This is a separate case-sensitive option "
                               "with its own interface and allocation record.", day="2026-11-01"))
            result = book.recall("current retry_limit", project="harbor", limit=1)
            self.assertEqual(first_session(result), "lowercase")

    def test_newer_observations_cannot_take_a_stronger_contracts_relevance_slot(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("contract", "Lease settings: lease.ttl=30."))
            for index in range(8):
                book.ingest(record(f"journal-{index}",
                    f"Team {index} inspected lease.ttl during the office handover and filed the equipment checklist.",
                    question=f"Office handover {index}", day=f"2026-10-{index + 1:02}"))
            plain = book.recall("lease.ttl", project="harbor", limit=1, use_cache=False)
            self.assertEqual(first_session(plain), "contract")
            for limit in (1, 5):
                with self.subTest(limit=limit):
                    current = book.recall("current lease.ttl", project="harbor", limit=limit,
                                          budget_chars=2400, use_cache=False)
                    self.assertEqual(first_session(current), "contract")
                    self.assertEqual(current["candidate_count"], 9)
                    self.assertEqual(len(current["results"]), limit)
                    self.assertLessEqual(len(current["context"]), 2400)
                    for hit in current["results"]:
                        page = book.read(hit["id"])
                        self.assertEqual(hit["text"], page["content"])
                        self.assertEqual(hit["source_refs"], page["source_refs"])

    def test_explicit_cross_source_replacement_keeps_time_preference(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("first", "Lease settings: lease.ttl=30."))
            book.ingest(record("revised", "Lease settings: lease.ttl=45. "
                               "This follows the new handover schedule and the additional delay from the ferry crossing.",
                               day="2026-04-01"))
            book.ingest(record("later-observation", "Lease settings were checked; lease.ttl appeared in the operator journal. "
                               "The next visit requires an equipment inventory and a handover signature.", day="2026-11-01"))
            plain = book.recall("lease.ttl", project="harbor", limit=1, use_cache=False)
            current = book.recall("current lease.ttl", project="harbor", limit=1, use_cache=False)
            self.assertEqual(first_session(plain), "first")
            self.assertEqual(first_session(current), "revised")
            self.assertIn("lease.ttl=45", current["context"])
            self.assertEqual(current["candidate_count"], 3)

    def test_another_property_assignment_does_not_make_a_topic_mention_current(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("contract", "Lease settings: lease.ttl=30."))
            book.ingest(record("other-property", "Inspected lease.ttl in the operator journal. "
                               "The unrelated archive.ttl=300 entry was copied to the equipment sheet.", day="2026-11-01"))
            self.assertEqual(first_session(book.recall("current lease.ttl", project="harbor", limit=1)), "contract")

    def test_partial_multi_property_mentions_keep_the_complete_contract_available(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("contract", "lease.ttl=30; cache.size=64."))
            book.ingest(record("partial", "lease.ttl=45. The cache.size label was seen during an equipment inspection "
                               "along with the operator's handover sheet.", day="2026-11-01"))
            result = book.recall("current lease.ttl and cache.size", project="harbor", limit=1)
            self.assertEqual(first_session(result), "contract")
            book.ingest(record("both-revised", "lease.ttl=60; cache.size=128. "
                               "These settings follow the revised capacity plan, operator review and allocation record.",
                               day="2026-12-01"))
            revised = book.recall("current lease.ttl and cache.size", project="harbor", limit=1)
            self.assertEqual(first_session(revised), "both-revised")

    def test_same_source_later_turn_does_not_require_assignment_syntax(self):
        source = record("conversation", "lease.ttl=30. " + "lease.ttl " * 20)
        source["messages"] += [{"role": "user", "content": "What about lease.ttl?"},
                               {"role": "assistant", "content": "Use forty-five seconds from this point on."}]
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source)
            result = book.recall("current lease.ttl", project="harbor", limit=1)
            self.assertIn("forty-five seconds", result["context"])
            self.assertEqual({ref["turn_index"] for ref in result["results"][0]["source_refs"]}, {1})

    def test_project_and_task_boundaries_do_not_share_timestamp_slots(self):
        for other_project, other_task in (("remote-harbor", "leases"), ("harbor", "inventory")):
            with self.subTest(project=other_project, task=other_task), MemoryBook(":memory:") as book:
                book.ingest(record("contract", "Lease settings: lease.ttl=30."))
                book.ingest(record("other", "Lease settings: lease.ttl=90. "
                                   "This record applies to a different operating context and its own allocation plan.",
                                   project=other_project, task=other_task, day="2026-11-01"))
                plain = book.recall("lease.ttl", limit=1, use_cache=False)
                current = book.recall("current lease.ttl", limit=1, use_cache=False)
                self.assertEqual(first_session(plain), "contract")
                self.assertEqual(first_session(current), "contract")

    def test_history_stays_lexical_and_event_queries_keep_observation_chronology(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("first", "Lease settings: lease.ttl=30."))
            book.ingest(record("revised", "Lease settings: lease.ttl=45. "
                               "This follows the revised allocation schedule and handover record.", day="2026-04-01"))
            book.ingest(record("observation", "Inspected lease.ttl during the office handover, "
                               "filed the equipment checklist and closed the journal.", day="2026-11-01"))
            for query in ("lease.ttl", "original lease.ttl", "current lease.ttl as of 2026"):
                with self.subTest(query=query):
                    self.assertEqual(first_session(book.recall(query, project="harbor", limit=1)), "first")
            events = book.recall("current lease.ttl event timeline", project="harbor", limit=1)
            self.assertEqual(first_session(events), "observation")

    def test_binding_signal_does_not_claim_to_resolve_approval_or_quotation(self):
        # The signal says that a literal property has a syntactic binding, not
        # that it is approved or true. Rejecting hypothetical/revoked values
        # would require a separate authority/conflict model; no such claim is
        # made by this narrowly scoped ordering guard.
        for text in ("Rejected trial: cache.mode=experimental.",
                     "The manual quotes `cache.mode=experimental` as an example."):
            self.assertEqual(_current_binding_keys(text, "current cache.mode"), {("assignment", "cache.mode")})

    def test_previous_recall_version_cache_is_ignored_and_new_sources_are_retained(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("contract", "lease.ttl=30."))
            with patch.object(store, "RECALL_VERSION", 13):
                book.recall("current lease.ttl", project="harbor", limit=1)
            book.db.execute("UPDATE recall_cache SET payload=?", (json.dumps({"context": "old ranking cache"}),))
            current = book.recall("current lease.ttl", project="harbor", limit=1)
            self.assertFalse(current["cache_hit"])
            self.assertIn("lease.ttl=30", current["context"])
            cached = book.recall("current lease.ttl", project="harbor", limit=1)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(cached["results"], current["results"])
            self.assertEqual(cached["context"], current["context"])


if __name__ == "__main__":
    unittest.main()
