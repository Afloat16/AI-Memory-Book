"""Current ordering must not turn a later mention into a supported revision.

These authored regression cases exercise source-scoped statement comparison,
not natural-language truth or benchmark answer accuracy.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook


def record(sid, body, *, project="workers", task="queue", title="Worker configuration",
           date="2026-01-01T00:00:00Z"):
    return {"project": project, "task_id": task, "task_title": title,
            "session_id": sid, "title": title, "created_at": date,
            "messages": [{"role": "assistant", "content": body}]}


def sessions(result):
    return [hit["source_refs"][0]["session_id"] for hit in result["results"]]


class CurrentAuthorityTests(unittest.TestCase):
    def assert_sources(self, book, result):
        self.assertEqual(result["context_chars"], len(result["context"]))
        self.assertLessEqual(result["context_chars"], result["budget_chars"])
        for hit in result["results"]:
            page = book.read(hit["id"], project="workers", limit=100000)
            for ref in hit["source_refs"]:
                self.assertEqual(ref["project"], "workers")
                source = book.db.execute(
                    "SELECT t.content FROM turns t JOIN sessions s ON s.id=t.session_pk "
                    "WHERE s.project_id=? AND s.external_id=? AND t.ordinal=?",
                    (ref["project"], ref["session_id"], ref["turn_index"])).fetchone()[0]
                self.assertEqual(page["content"][ref["start"]:ref["end"]],
                                 source[ref["turn_start"]:ref["turn_end"]])

    def compare(self, earlier, later, query, *, title="Worker configuration", **options):
        book = MemoryBook(":memory:", cache_size=0, **options)
        self.addCleanup(book.close)
        book.ingest(record("decision", earlier, title=title))
        book.ingest(record("recent", later, title=title, date="2026-10-01T00:00:00Z"))
        result = book.recall(query, project="workers", temporal="current", limit=1,
                             budget_chars=1200, use_cache=False)
        self.assert_sources(book, result)
        return book, result

    def test_unrelated_sentence_and_suffix_cannot_supply_an_environment(self):
        texts = (
            "Staging lease_duration=99. The production review remains open.",
            "Production remains pending; staging lease_duration=99.",
            "Production discussion includes staging lease_duration=99.",
            "Production lease_duration=99 for staging.",
            "Production lease duration is now 99 for staging.",
            "Production max_connections=50. Staging lease_duration=99.",
        )
        for text in texts:
            for title in ("Worker configuration", "Production configuration"):
                with self.subTest(text=text, title=title):
                    _, result = self.compare(
                        "Production lease_duration=30. " + "production lease_duration. " * 12,
                        text, "current production lease_duration", title=title)
                    self.assertEqual(sessions(result), ["decision"])
                    self.assertNotIn("99", result["context"])

    def test_unqueried_explicit_scope_cannot_merge_with_an_unqualified_statement(self):
        for title in ("Worker configuration", "Production configuration"):
            for earlier in ("lease_duration=30. ", "Production lease_duration=30. "):
                for query in ("current lease_duration", "current production lease_duration"):
                    with self.subTest(title=title, earlier=earlier, query=query):
                        _, result = self.compare(earlier + "lease_duration. " * 12,
                            "Staging lease_duration=99.", query, title=title)
                        self.assertEqual(sessions(result), ["decision"])

    def test_matching_environment_revisions_remain_eligible(self):
        for old, new in (("Production lease_duration=30", "Production lease_duration=12"),
                         ("EU staging lease_duration=30", "EU staging lease_duration=12")):
            with self.subTest(old=old):
                _, result = self.compare(old + ". " + "lease_duration. " * 12,
                                          new + ".", "current lease_duration")
                self.assertEqual(sessions(result), ["recent"])
                self.assertIn("=12", result["context"])

    def test_a_later_agenda_never_inherits_a_plain_numeric_decision(self):
        for fact in ("The retry limit is three attempts.", "Retry limit is 3.", "retry_limit=3."):
            with self.subTest(fact=fact):
                _, result = self.compare(fact + " retry limit. " * 12,
                    "The retry limit remains on tomorrow's agenda. No decision has been made.",
                    "current retry limit")
                self.assertEqual(sessions(result), ["decision"])

    def test_numeric_prose_can_establish_a_field_without_a_code_example(self):
        for first, last, query in (
            ("Worker prefetch window is 12.", "Worker prefetch window is now 3.", "worker prefetch window"),
            ("The retry limit is three attempts.", "The retry limit is seven attempts.", "retry limit"),
            ("Cache interval is twenty-one seconds.", "Cache interval is thirty seconds.", "cache interval"),
            ("梯度累积步数设为8。", "梯度累积步数现在改为2。", "梯度累积步数"),
        ):
            with self.subTest(last=last):
                _, result = self.compare(first + (" " + query + ".") * 12,
                                          last, "current " + query)
                self.assertEqual(sessions(result), ["recent"])
                self.assertIn(last, result["context"])

    def test_assignment_and_prose_share_quantity_units(self):
        for first, last, query in (
            ("timeout=30 seconds.", "timeout=5 seconds.", "timeout"),
            ("retry_limit=3 retries.", "retry_limit=7 retries.", "retry_limit"),
            ("The retry limit is 3 retries.", "The retry limit is now 7 retries.", "retry limit"),
            ("Worker delay is 20 milliseconds.", "Worker delay is 5ms.", "worker delay"),
            ("buffer_bytes=3 MiB.", "buffer_bytes=7 MiB.", "buffer_bytes"),
            ("Production lease_duration=30 seconds.", "Production lease_duration=12 seconds.",
             "production lease_duration"),
            ("超时参数设置为30秒。", "超时参数调整为5秒。", "超时参数"),
        ):
            with self.subTest(last=last):
                _, result = self.compare(first + (" " + query + ".") * 12,
                                          last, "current " + query)
                self.assertEqual(sessions(result), ["recent"])
                self.assertIn(last, result["context"])

    def test_simple_causal_explanation_preserves_a_numeric_update(self):
        for old, new, query in (
            ("Worker prefetch window is 12.",
             "Worker prefetch window is now 3 because memory usage was too high.",
             "worker prefetch window"),
            ("timeout=30 seconds.", "timeout=5 seconds because latency exceeded expectations.", "timeout"),
        ):
            with self.subTest(new=new):
                _, result = self.compare(old + (" " + query + ".") * 12, new, "current " + query)
                self.assertEqual(sessions(result), ["recent"])
                self.assertIn(new, result["context"])

    def test_a_reason_cannot_introduce_a_scope_condition_or_another_assignment(self):
        for reason in ("this setting applies only to staging", "latency increased for staging",
                       "another_limit=8", "the proposal is pending", "this holds when testing staging",
                       'the log said "retry_limit=3"'):
            with self.subTest(reason=reason):
                _, result = self.compare("Production retry_limit=3. " + "production retry_limit. " * 12,
                    "Production retry_limit=99 because " + reason + ".", "current production retry_limit")
                self.assertEqual(sessions(result), ["decision"])
                self.assertNotIn("=99", result["context"])

    def test_reporting_labels_and_chapter_topics_do_not_split_one_field(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            title = "Delivery numerical kernel"
            book.ingest(record("initial", "Initial project decision: delivery_mode=buffered. "
                               "The delivery kernel uses this contract.", title=title))
            book.ingest(record("replacement", "Approved replacement for the initial contract: "
                               "delivery_mode=streaming. The delivery policy was reviewed.",
                               title=title, date="2026-02-01T00:00:00Z"))
            for i in range(3):
                book.ingest(record(f"review-{i}", "Reviewed delivery kernel and delivery_mode names. "
                                   "No new setting was chosen.", title=title,
                                   date=f"2026-03-0{i + 1}T00:00:00Z"))
            result = book.recall("current delivery_mode for the delivery kernel", project="workers",
                                 limit=5, budget_chars=2400)
            # Declaration ordering fixes comparability, not every BM25 error.
            # A high-relevance original review can still precede this pair.
            self.assertLess(sessions(result).index("replacement"), sessions(result).index("initial"))
            self.assertIn("delivery_mode=streaming", result["context"])
            self.assert_sources(book, result)

    def test_same_page_latest_turn_requires_its_own_declaration_and_scope(self):
        for newest in (
            "The production lease_duration remains on the next review agenda.",
            "Staging lease_duration=99. Production review remains open.",
            "Production lease_duration=99 for staging.",
        ):
            with self.subTest(newest=newest), MemoryBook(":memory:", cache_size=0) as book:
                source = record("conversation", "unused")
                source["messages"] = [
                    {"role": "user", "content": "Production lease_duration?"},
                    {"role": "assistant", "content": "Production lease_duration=30. "
                     + "production lease_duration. " * 8},
                    {"role": "user", "content": "Production lease_duration follow-up?"},
                    {"role": "assistant", "content": newest},
                ]
                self.assertEqual(book.ingest(source)["pages"], 1)
                request = dict(query="current production lease_duration", project="workers",
                               limit=1, budget_chars=300, use_cache=False)
                current = book.recall(**request)
                relevance = book.recall(**request, temporal="relevance")
                self.assertEqual(current["context"], relevance["context"])
                self.assertEqual(current["results"], relevance["results"])
                self.assert_sources(book, current)

    def test_same_page_directory_title_cannot_supply_a_turns_missing_scope(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            source = record("samepage", "unused", title="Production configuration")
            source["messages"] = [
                {"role": "user", "content": "Production lease_duration?"},
                {"role": "assistant", "content": "Production lease_duration=30. "
                 + "production lease_duration. " * 8},
                {"role": "user", "content": "Production lease_duration follow-up?"},
                {"role": "assistant", "content": "Staging lease_duration=99. The production review remains open."},
            ]
            self.assertEqual(book.ingest(source)["pages"], 1)
            for budget in (200, 250, 300):
                with self.subTest(budget=budget):
                    request = dict(query="current production lease_duration", project="workers",
                                   limit=1, budget_chars=budget, use_cache=False)
                    current = book.recall(**request)
                    relevance = book.recall(**request, temporal="relevance")
                    self.assertEqual(current["results"], relevance["results"])
                    self.assertNotIn("Staging lease_duration=99", current["context"])
                    self.assert_sources(book, current)

    def test_examples_and_questions_are_not_plain_numeric_updates(self):
        for text in ("Example: retry limit is 9.", "Should retry limit be 9?",
                     "If retry limit is 9, use the old experiment.",
                     'The log said "retry limit is 9".', "```text\nretry limit is 9\n```"):
            with self.subTest(text=text):
                _, result = self.compare("Retry limit is 3. " + "retry limit. " * 12,
                                          text, "current retry limit")
                self.assertEqual(sessions(result), ["decision"])

    def test_unknown_text_keeps_relevance_order_without_a_recency_claim(self):
        book, current = self.compare("Worker backoff options review. " + "worker backoff. " * 12,
                                     "Worker backoff discussion remains open.", "current worker backoff")
        plain = book.recall("current worker backoff", project="workers", temporal="relevance",
                            limit=1, budget_chars=1200, use_cache=False)
        self.assertEqual(current["results"], plain["results"])
        self.assertEqual(current["context"], plain["context"])

    def test_partial_original_turn_can_anchor_but_never_establish_a_newer_revision(self):
        book, current = self.compare("retry_limit=3. " + "retry_limit. " * 80,
                                     "retry_limit=7.", "current retry_limit",
                                     max_page_chars=160, min_page_chars=0)
        self.assertEqual(sessions(current), ["recent"])
        self.assertIn("retry_limit=7", current["context"])
        self.assertGreater(current["temporal"]["declaration_ordering"]["complete_source_partial_anchors"], 0)
        book.ingest(record("incomplete-new", "retry_limit=999. " + "pending " * 180 + "Not accepted.",
                           date="2026-11-01T00:00:00Z"))
        result = book.recall("current retry_limit", project="workers", limit=1, budget_chars=1200)
        self.assertEqual(sessions(result), ["recent"])
        self.assertNotIn("999", result["context"])
        self.assert_sources(book, result)

    def test_namesake_projects_tasks_and_sessions_keep_their_original_scope(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            first = book.ingest(record("initial", "retry_limit=3. " + "retry_limit. " * 12))
            book.ingest(record("replacement", "retry_limit=7.", date="2026-03-01T00:00:00Z"))
            book.ingest(record("replacement", "retry_limit=99.", project="workers-copy",
                               date="2026-11-01T00:00:00Z"))
            book.ingest(record("other-task", "retry_limit=88.", task="another",
                               date="2026-11-01T00:00:00Z"))
            result = book.recall("current retry_limit", project="workers", chapter=first["chapter_id"],
                                 limit=1, budget_chars=1200)
            self.assertEqual(sessions(result), ["replacement"])
            self.assertIn("retry_limit=7", result["context"])
            self.assert_sources(book, result)
            original = book.recall("current retry_limit", project="workers", session="initial", limit=1)
            self.assertEqual(sessions(original), ["initial"])

    def test_relevance_history_and_occurrences_do_not_enter_declaration_ordering(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("initial", "retry_limit=3. " + "retry_limit. " * 12))
            book.ingest(record("replacement", "retry_limit=7.", date="2026-03-01T00:00:00Z"))
            with patch("memory_book.store._declaration_groups", side_effect=AssertionError("classified")):
                for query, options in (("current retry_limit", {"temporal": "relevance"}),
                                       ("original retry_limit", {}),
                                       ("current retry_limit event timeline", {})):
                    result = book.recall(query, project="workers", limit=5, use_cache=False, **options)
                    self.assertTrue(result["results"])


if __name__ == "__main__":
    unittest.main()
