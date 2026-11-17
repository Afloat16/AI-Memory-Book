"""Current decisions can change within a long engineering conversation."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

from memory_book import MemoryBook


def training_session(project="trainer", session_id="s1", *, date="2026-10-01T00:00:00Z"):
    return {
        "project": project,
        "session_id": session_id,
        "task_id": "gradient-memory",
        "title": "Gradient accumulation steps",
        "created_at": date,
        "messages": [
            {"role": "user", "content": "Gradient accumulation steps?"},
            {"role": "assistant", "content": "Gradient accumulation steps are 8. "
             + "gradient accumulation steps. " * 28},
            {"role": "user", "content": "Gradient accumulation steps?"},
            {"role": "assistant", "content": "Gradient accumulation steps are now 2. "
             "The former value 8 caused divergence and is no longer valid."},
        ],
    }


def same_page_session():
    source = training_session()
    source["messages"][1]["content"] = ("Gradient accumulation steps are 8. "
                                         + "gradient accumulation steps. " * 8)
    return source


class CurrentTurnRecallTests(unittest.TestCase):
    def test_default_segmentation_recalls_later_revision_in_same_session(self):
        with MemoryBook(":memory:") as book:
            book.ingest(training_session())
            result = book.recall("current gradient accumulation steps", project="trainer",
                                 limit=1, budget_chars=500, use_cache=False)
            self.assertIn("steps are now 2", result["context"])
            self.assertEqual({ref["turn_index"] for ref in result["results"][0]["source_refs"]}, {1})
            # Recency remains evidence ordering, not an authoritative state resolver.
            self.assertTrue(result["warnings"])

    def test_historical_and_unqualified_queries_keep_their_relevance_order(self):
        with MemoryBook(":memory:") as book:
            book.ingest(training_session())
            for query in ("gradient accumulation steps", "original gradient accumulation steps",
                          "current gradient accumulation steps as of 2026"):
                with self.subTest(query=query):
                    result = book.recall(query, project="trainer", limit=1, budget_chars=500)
                    self.assertEqual(result["results"][0]["source_refs"][0]["turn_index"], 0)

    def test_chinese_revision_respects_project_scope_with_duplicate_session_ids(self):
        with MemoryBook(":memory:", max_page_chars=384, min_page_chars=80) as book:
            for project, value in (("训练甲", "2"), ("训练乙", "4")):
                book.ingest({
                    "project": project, "session_id": "训练讨论", "task_id": "显存预算",
                    "title": "梯度累积步数", "created_at": "2026-10-01T00:00:00Z",
                    "messages": [
                        {"role": "user", "content": "梯度累积步数怎么设置？"},
                        {"role": "assistant", "content": "梯度累积步数设为8。" + "梯度累积步数。" * 48},
                        {"role": "user", "content": "梯度累积步数怎么设置？"},
                        {"role": "assistant", "content": f"梯度累积步数改为{value}，旧值已因收敛测试失败而弃用。"},
                    ],
                })
            for project, value in (("训练甲", "2"), ("训练乙", "4")):
                with self.subTest(project=project):
                    result = book.recall("当前梯度累积步数", project=project, limit=1, budget_chars=400)
                    self.assertIn(f"步数改为{value}", result["context"])
                    self.assertEqual({ref["project"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {project})
                    self.assertEqual(result["results"][0]["source_refs"][0]["turn_index"], 1)

    def test_turn_numbers_never_override_chronology_between_sessions(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(training_session())
            later = training_session(session_id="later", date="2026-11-01T00:00:00Z")
            later["messages"] = [
                {"role": "user", "content": "Gradient accumulation steps?"},
                {"role": "assistant", "content": "Gradient accumulation steps are now 3."},
            ]
            book.ingest(later)
            result = book.recall("current gradient accumulation steps", project="trainer",
                                 limit=3, budget_chars=4000)
            self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "later")
            same_session_turns = [hit["source_refs"][0]["turn_index"] for hit in result["results"]
                                  if hit["source_refs"][0]["session_id"] == "s1"]
            self.assertEqual(same_session_turns, [1, 0])

    def test_same_turn_continuations_keep_their_relevance_order(self):
        with MemoryBook(":memory:", max_page_chars=128, min_page_chars=0) as book:
            source = training_session()
            source["messages"] = source["messages"][:2]
            book.ingest(source)
            plain = book.recall("gradient accumulation steps", project="trainer", limit=3, use_cache=False)
            current = book.recall("current gradient accumulation steps", project="trainer", limit=3, use_cache=False)
            self.assertEqual([hit["id"] for hit in current["results"]],
                             [hit["id"] for hit in plain["results"]])
            self.assertTrue(all(ref["turn_index"] == 0 for hit in current["results"]
                                for ref in hit["source_refs"]))

    def test_reordered_evidence_keeps_budgets_and_original_source_coordinates(self):
        with MemoryBook(":memory:") as book:
            book.ingest(training_session())
            for budget in (150, 500, 4000):
                with self.subTest(budget=budget):
                    result = book.recall("current gradient accumulation steps", project="trainer",
                                         limit=1, budget_chars=budget)
                    self.assertLessEqual(result["context_chars"], budget)
                    self.assertEqual(result["context_chars"], len(result["context"]))
                    hit = result["results"][0]
                    original = book.read(hit["id"])["content"]
                    start, end = hit["excerpt_spans"][0]
                    self.assertEqual(hit["text"], ("…" if start else "") + original[start:end]
                                     + ("…" if end < len(original) else ""))
                    self.assertTrue(all(ref["turn_index"] == 1 for ref in hit["source_refs"]))
                    cached = book.recall("current gradient accumulation steps", project="trainer",
                                         limit=1, budget_chars=budget)
                    self.assertTrue(cached["cache_hit"])
                    self.assertEqual(cached["context"], result["context"])

    def test_current_excerpt_preserves_complete_later_turn_in_one_page(self):
        with MemoryBook(":memory:") as book:
            self.assertEqual(book.ingest(same_page_session())["pages"], 1)
            current = book.recall("current gradient accumulation steps", project="trainer",
                                  limit=1, budget_chars=300, use_cache=False)
            self.assertIn("steps are now 2", current["context"])
            self.assertIn("no longer valid", current["context"])
            hit = current["results"][0]
            self.assertEqual({ref["turn_index"] for ref in hit["source_refs"]}, {1})
            original = book.read(hit["id"])["content"]
            start, end = hit["excerpt_spans"][0]
            self.assertEqual(hit["text"], "…" + original[start:end])
            self.assertEqual(end, len(original))
            self.assertLessEqual(len(current["context"]), 300)
            for query in ("gradient accumulation steps", "original gradient accumulation steps"):
                unchanged = book.recall(query, project="trainer", limit=1, budget_chars=300)
                self.assertNotIn("steps are now 2", unchanged["context"])

    def test_chinese_current_excerpt_uses_the_later_complete_turn(self):
        with MemoryBook(":memory:") as book:
            book.ingest({
                "project": "训练", "session_id": "修订", "title": "梯度累积步数",
                "messages": [
                    {"role": "user", "content": "梯度累积步数？"},
                    {"role": "assistant", "content": "梯度累积步数设为8。" + "梯度累积步数。" * 40},
                    {"role": "user", "content": "梯度累积步数？"},
                    {"role": "assistant", "content": "梯度累积步数现在改为2。旧值导致回归，已经撤销。"},
                ],
            })
            result = book.recall("当前梯度累积步数", project="训练", budget_chars=220, limit=1)
            self.assertIn("现在改为2", result["context"])
            self.assertIn("已经撤销", result["context"])
            self.assertTrue(all(ref["turn_index"] == 1 for hit in result["results"]
                                for ref in hit["source_refs"]))

    def test_complete_pages_and_unfitting_current_turns_keep_existing_windows(self):
        with MemoryBook(":memory:") as book:
            book.ingest(same_page_session())
            for budget in (130, 5000):
                with self.subTest(budget=budget):
                    current = book.recall("current gradient accumulation steps", project="trainer",
                                          limit=1, budget_chars=budget, use_cache=False)
                    ordinary = book.recall("gradient accumulation steps", project="trainer",
                                           limit=1, budget_chars=budget, use_cache=False)
                    self.assertEqual(current["context"], ordinary["context"])
                    self.assertEqual(current["results"][0]["excerpt_spans"], ordinary["results"][0]["excerpt_spans"])

    def test_current_excerpt_checks_the_original_turn_not_just_page_coordinates(self):
        with MemoryBook(":memory:") as book:
            book.ingest(same_page_session())
            # Model a page containing only part of its claimed original turn.
            # The omitted qualification must prevent a complete-turn claim.
            book.db.execute("UPDATE turns SET content=content || ? WHERE ordinal=1",
                            (" Additional qualification not contained in this page.",))
            current = book.recall("current gradient accumulation steps", project="trainer",
                                  limit=1, budget_chars=300, use_cache=False)
            ordinary = book.recall("gradient accumulation steps", project="trainer",
                                   limit=1, budget_chars=300, use_cache=False)
            self.assertEqual(current["context"], ordinary["context"])

    def test_query_facets_spanning_turns_do_not_become_one_current_fact(self):
        source = same_page_session()
        source["messages"][2:] = [
            {"role": "user", "content": "Checkpoint retention count?"},
            {"role": "assistant", "content": "Checkpoint retention count is now 3."},
        ]
        with MemoryBook(":memory:") as book:
            book.ingest(source)
            topic = "gradient accumulation steps checkpoint retention count"
            current = book.recall("current " + topic, project="trainer", budget_chars=300, limit=1)
            ordinary = book.recall(topic, project="trainer", budget_chars=300, limit=1)
            self.assertEqual(current["context"], ordinary["context"])

    @unittest.skipUnless(find_spec("tiktoken"), "the optional real tokenizers are not installed")
    def test_real_token_caps_cannot_replace_a_preferred_current_turn_with_old_evidence(self):
        from memory_book.token_budget import TokenCounter

        with MemoryBook(":memory:") as book:
            book.ingest(same_page_session())
            baseline = book.recall("gradient accumulation steps", project="trainer", budget_chars=300, limit=1)
            hit = baseline["results"][0]
            page = book.read(hit["id"])
            latest = next(ref for ref in page["source_refs"] if ref["turn_index"] == 1)
            header = baseline["context"].split("\n", 1)[0] + "\n"
            preferred = "…" + page["content"][latest["start"]:latest["end"]]
            for name in ("cl100k_base", "o200k_base"):
                counter = TokenCounter(name)
                full_cap = counter.count(header + preferred)
                for cap in (full_cap, full_cap + 5, counter.count(header) + 6):
                    with self.subTest(tokenizer=name, cap=cap):
                        result = book.recall("current gradient accumulation steps", project="trainer",
                                             limit=1, budget_chars=300, budget_tokens=cap,
                                             tokenizer=name, use_cache=False)
                        self.assertLessEqual(result["context_tokens"], cap)
                        self.assertEqual(result["context_tokens"], counter.count(result["context"]))
                        self.assertTrue(all(ref["turn_index"] == 1 for item in result["results"]
                                            for ref in item["source_refs"]))
                        if cap >= full_cap:
                            self.assertIn("steps are now 2", result["context"])
                            self.assertIn("no longer valid", result["context"])


def maintenance_session(session_id, *, project="trainer", task="configuration",
                        topic="gradient accumulation steps", content=None, date="2026-10-01T00:00:00Z"):
    return {
        "project": project, "session_id": session_id, "task_id": task,
        "title": topic, "task_title": topic, "created_at": date,
        "messages": [{"role": "assistant", "content": content or
                      (topic.capitalize() + " maintenance review. " + (topic + ". ") * 8)}],
    }


class CurrentDuplicateEvidenceTests(unittest.TestCase):
    def populate(self, book, *, topic="gradient accumulation steps"):
        book.ingest(maintenance_session("decision", topic=topic, date="2026-01-01T00:00:00Z",
                                       content=topic.capitalize() + " are 2; verified by the convergence test."))
        for index in range(8):
            book.ingest(maintenance_session(f"review-{index}", topic=topic,
                                           date=f"2026-10-{index + 1:02}T00:00:00Z"))

    def test_identical_reviews_leave_space_for_different_current_evidence(self):
        with MemoryBook(":memory:") as book:
            self.populate(book)
            result = book.recall("current gradient accumulation steps", project="trainer",
                                 limit=3, budget_chars=4000, use_cache=False)
            self.assertIn("verified by the convergence test", result["context"])
            self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "review-7")
            self.assertEqual(result["candidate_count"], 9)
            self.assertEqual(len(result["results"]), 3)
            self.assertLessEqual(result["context_chars"], 4000)
            for hit in result["results"]:
                self.assertEqual(hit["text"], book.read(hit["id"])["content"])
                self.assertTrue(all(ref["project"] == "trainer" for ref in hit["source_refs"]))

    def test_retention_count_parameter_is_not_an_event_count_query(self):
        with MemoryBook(":memory:") as book:
            self.populate(book, topic="checkpoint retention count")
            result = book.recall("current checkpoint retention count", project="trainer", limit=3)
            self.assertIn("verified by the convergence test", result["context"])

    def test_one_code_punctuation_difference_keeps_both_sources_distinct(self):
        with MemoryBook(":memory:") as book:
            for session, operator in (("strict", "<"), ("inclusive", "<=")):
                book.ingest(maintenance_session(session, content=(
                    f"Gradient accumulation steps use `x {operator} y`. "
                    + "gradient accumulation steps. " * 8)))
            book.ingest(maintenance_session("decision", date="2026-01-01T00:00:00Z",
                                           content="Gradient accumulation steps are now 2."))
            result = book.recall("current gradient accumulation steps", project="trainer", limit=2)
            self.assertIn("x < y", result["context"])
            self.assertIn("x <= y", result["context"])
            self.assertEqual({ref["session_id"] for hit in result["results"]
                              for ref in hit["source_refs"]}, {"strict", "inclusive"})

    def test_historical_and_event_queries_keep_repeated_occurrences(self):
        with MemoryBook(":memory:") as book:
            self.populate(book)
            for query in (
                "original gradient accumulation steps",
                "current gradient accumulation steps how many times",
                "current gradient accumulation steps how often",
                "current gradient accumulation steps event timeline",
                "当前 gradient accumulation steps 出现次数",
                "当前 gradient accumulation steps 事件时间线",
            ):
                with self.subTest(query=query):
                    result = book.recall(query, project="trainer", limit=3, use_cache=False)
                    self.assertNotIn("verified by the convergence test", result["context"])
                    self.assertEqual(len(result["results"]), 3)
                    self.assertEqual(len({hit["text"] for hit in result["results"]}), 1)

    def test_identical_text_in_different_projects_or_tasks_is_not_collapsed(self):
        for across_projects in (False, True):
            with self.subTest(across_projects=across_projects), MemoryBook(":memory:") as book:
                book.ingest(maintenance_session("a", project="trainer-a", task="first"))
                book.ingest(maintenance_session("b", project="trainer-b" if across_projects else "trainer-a",
                                               task="first" if across_projects else "second"))
                book.ingest(maintenance_session("decision", project="trainer-a", task="first",
                                               date="2026-01-01T00:00:00Z",
                                               content="Gradient accumulation steps are now 2."))
                result = book.recall("current gradient accumulation steps", limit=2)
                self.assertEqual({ref["session_id"] for hit in result["results"]
                                  for ref in hit["source_refs"]}, {"a", "b"})

    def test_duplicate_sources_backfill_when_there_are_not_enough_distinct_pages(self):
        with MemoryBook(":memory:") as book:
            for index in range(3):
                book.ingest(maintenance_session(f"review-{index}", date=f"2026-10-{index + 1:02}T00:00:00Z"))
            result = book.recall("current gradient accumulation steps", project="trainer", limit=5)
            self.assertEqual(result["candidate_count"], 3)
            self.assertEqual(len(result["results"]), 3)
            self.assertEqual({ref["session_id"] for hit in result["results"]
                              for ref in hit["source_refs"]}, {"review-0", "review-1", "review-2"})


if __name__ == "__main__":
    unittest.main()
