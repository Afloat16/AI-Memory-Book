"""Regressions for evidence lost during bounded context assembly."""

from __future__ import annotations

import hashlib
import json
import unittest

from memory_book import MemoryBook


class RecallBudgetTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000, min_page_chars=0)
        for sid, title, question, answer in (
            ("design", "Relay calibration", "orbital relay calibration specification",
             "Orbital relay calibration uses 41 millivolts. " +
             "Document each measurement and calibration step before approving the relay. " * 12),
            ("status", "Relay update", "relay update", "The relay inspection is complete."),
            ("owner", "Relay owner", "relay owner", "Mira owns the relay."),
        ):
            self.book.ingest({
                "project": "lab", "session_id": sid, "title": title,
                "created_at": "2025-07-03T12:00:00Z",
                "messages": [{"role": "user", "content": question},
                             {"role": "assistant", "content": answer}],
            })
        self.query = "orbital relay calibration"

    def tearDown(self):
        self.book.close()

    def test_whole_selected_evidence_is_preserved_when_it_fits(self):
        full = self.book.recall(self.query, project="lab", limit=3, budget_chars=8000, use_cache=False)
        self.assertGreater(full["results"][0]["page_chars"], 900)
        self.assertEqual(len(full["results"]), 3)
        # A long first result and short later results expose the former
        # one-way allocator: it could not return later unused space upstream.
        exact_fit = self.book.recall(self.query, project="lab", limit=3,
                                     budget_chars=len(full["context"]), use_cache=False)
        self.assertEqual(exact_fit["context"], full["context"])
        self.assertFalse(any(item["truncated"] for item in exact_fit["results"]))

    def test_short_evidence_and_source_spans_survive_a_shared_budget(self):
        result = self.book.recall(self.query, project="lab", limit=3, budget_chars=700, use_cache=False)
        self.assertLessEqual(len(result["context"]), 700)
        self.assertEqual(result["context_chars"], len(result["context"]))
        self.assertIn("The relay inspection is complete.", result["context"])
        self.assertIn("Mira owns the relay.", result["context"])
        self.assertTrue(result["results"][0]["truncated"])
        for item in result["results"]:
            original = self.book.read(item["id"])["content"]
            for lo, hi in item["excerpt_spans"]:
                self.assertIn(original[lo:hi], item["text"])
            for ref in item["source_refs"]:
                source = self.book.get_session(ref["project"], ref["session_id"])
                turn = "\n\n".join(f'{message["role"].upper()}: {message["content"]}'
                                     for message in source["messages"])
                self.assertEqual(original[ref["start"]:ref["end"]],
                                 turn[ref["turn_start"]:ref["turn_end"]])

    def test_tiny_budget_retains_a_single_cited_fragment(self):
        full = self.book.recall(self.query, project="lab", limit=3, use_cache=False)
        citation_chars = full["context"].index("\n") + 1
        too_small = self.book.recall(self.query, project="lab", limit=3,
                                     budget_chars=citation_chars + 8, use_cache=False)
        self.assertEqual(too_small["context"], "")
        self.assertTrue(too_small["warnings"])
        fragment = self.book.recall(self.query, project="lab", limit=3,
                                    budget_chars=citation_chars + 30, use_cache=False)
        self.assertEqual(len(fragment["results"]), 1)
        self.assertLessEqual(len(fragment["context"]), citation_chars + 30)
        self.assertTrue(fragment["results"][0]["source_refs"])

    def test_prior_retrieval_cache_is_not_used_after_allocator_change(self):
        # v0.3.0 keyed caches with the index version only. Existing databases
        # must use the new retrieval behavior without reimporting their data.
        old_key_fields = [3, self.query, "lab", None, None, 700, 3, "book"]
        old_key = hashlib.sha256(json.dumps(old_key_fields, ensure_ascii=False,
                                          sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.book.db.execute("INSERT INTO recall_cache VALUES(?,?,?,?)",
                             (old_key, self.book.revision, '{"context":"stale allocator"}', 0))
        result = self.book.recall(self.query, project="lab", limit=3, budget_chars=700)
        self.assertFalse(result["cache_hit"])
        self.assertNotEqual(result["context"], "stale allocator")
        self.assertTrue(self.book.recall(self.query, project="lab", limit=3,
                                        budget_chars=700)["cache_hit"])


class MorphologyRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000, min_page_chars=0)

    def tearDown(self):
        self.book.close()

    def add(self, project, sid, answer, *, question="A local note", **metadata):
        return self.book.ingest({
            "project": project, "session_id": sid, "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": question},
                         {"role": "assistant", "content": answer}], **metadata,
        })

    def test_inflected_query_finds_original_word_form(self):
        self.add("travel", "visit", "Mira attended a conference in Tallinn.")
        recalled = self.book.recall("conferences", project="travel", use_cache=False)
        self.assertIn("conference in Tallinn", recalled["context"])
        self.assertEqual(recalled["results"][0]["source_refs"][0]["session_id"], "visit")
        self.assertEqual(self.book.recall("conferences", project="travel", strategy="flat",
                                         use_cache=False)["results"], [])

    def test_exact_term_is_not_replaced_by_a_broader_stem(self):
        self.add("science", "cosmos", "The universe contains the observable galaxies.")
        for i in range(12):
            self.add("science", f"school-{i}", "University university university enrollment.",
                     question="University schedule")
        result = self.book.recall("universe", project="science", limit=1, use_cache=False)
        self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "cosmos")

    def test_stem_candidates_are_scoped_before_the_candidate_limit(self):
        for i in range(110):
            self.add("other", f"foreign-{i}", "Conference conference conference.", question="Conference")
        target = self.add("travel", "visit", "Mira attended a conference in Tallinn.", task_id="trip")
        for scope in ({"project": "travel"}, {"chapter": target["chapter_id"]}, {"session": "visit"}):
            with self.subTest(scope=scope):
                result = self.book.recall("conferences", limit=1, use_cache=False, **scope)
                self.assertIn("Tallinn", result["context"])
                self.assertTrue(all(ref["project"] == "travel" for ref in result["results"][0]["source_refs"]))
        self.assertEqual(self.book.recall("conferences", project="other", session="visit",
                                         use_cache=False)["results"], [])

    def test_stem_directory_match_without_body_evidence_is_ignored(self):
        self.add("travel", "visit", "The calendar has an ordinary local appointment.",
                 task_id="events", task_title="Conferences")
        self.assertEqual(self.book.recall("conference", project="travel", use_cache=False)["results"], [])

    def test_inflection_excerpt_uses_matching_original_form_and_exact_offsets(self):
        answer = ("Unrelated itinerary details should remain available in the archive. " * 24 +
                  "\n\nAt the conference, Mira received the Kestrel award.")
        self.add("travel", "visit", answer)
        statements = []
        self.book.db.set_trace_callback(statements.append)
        result = self.book.recall("conferences", project="travel", budget_chars=420, limit=1, use_cache=False)
        self.book.db.set_trace_callback(None)
        self.assertIn("At the conference, Mira received the Kestrel award.", result["context"])
        self.assertLessEqual(len(result["context"]), 420)
        self.assertEqual(sum("highlight(" in statement.lower() for statement in statements), 1)
        item = result["results"][0]
        original = self.book.read(item["id"])["content"]
        for lo, hi in item["excerpt_spans"]:
            self.assertIn(original[lo:hi], item["text"])
        for ref in item["source_refs"]:
            self.assertIn(original[ref["start"]:ref["end"]], item["text"])

    def test_full_pages_skip_highlight_and_plain_chinese_skips_stem_search(self):
        self.add("travel", "visit", "Mira attended a conference in Tallinn. 缓存有效期是四十秒。")
        statements = []
        self.book.db.set_trace_callback(statements.append)
        self.assertIn("Tallinn", self.book.recall("conferences", project="travel", use_cache=False)["context"])
        self.assertFalse(any("highlight(" in statement.lower() for statement in statements))
        statements.clear()
        self.assertIn("四十秒", self.book.recall("缓存有效期", project="travel", use_cache=False)["context"])
        self.assertFalse(any("pages_stem_fts" in statement for statement in statements))
        statements.clear()
        self.book.recall("conference", project="travel", strategy="flat", use_cache=False)
        self.assertFalse(any("pages_stem_fts" in statement for statement in statements))
        self.book.db.set_trace_callback(None)

    def test_stem_index_follows_replace_rename_link_and_delete(self):
        self.add("travel", "visit", "Mira attended a conference in Tallinn.",
                 task_id="meetings", task_title="Planning")
        self.add("travel", "next", "Mira attended a workshop in Lisbon.",
                 task_id="meetings", task_title="Scheduling")
        self.book.link_session("travel", "visit", "renamed", "Events")
        exact = [tuple(row) for row in self.book.db.execute("SELECT rowid,title,question,body,directory FROM pages_fts ORDER BY rowid")]
        stem = [tuple(row) for row in self.book.db.execute("SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid")]
        self.assertEqual(exact, stem)
        self.add("travel", "visit", "Mira enjoyed an exhibition in Riga.", task_id="renamed")
        self.assertEqual(self.book.recall("conferences", project="travel", use_cache=False)["results"], [])
        self.assertIn("Riga", self.book.recall("exhibitions", project="travel", use_cache=False)["context"])
        self.book.delete_session("travel", "visit")
        self.assertEqual(self.book.recall("exhibitions", project="travel", use_cache=False)["results"], [])
        self.book.delete_project("travel")
        self.assertEqual(self.book.db.execute("SELECT count(*) FROM pages_stem_fts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
