"""Invented source/reference cases for the prospectively registered T1 option.

These fixtures contain no benchmark questions or labels. Expected references
are checked against original text, including edges where following must stop.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import title_references


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


def stable(response, *, without_mode=False):
    ignored = {"latency_ms"}
    if without_mode:
        ignored.update(("follow_titles", "title_reference"))
    return {key: value for key, value in response.items() if key not in ignored}


def source(sid, title, body, *, project="lab", task=None):
    return {"project": project, "session_id": sid, "title": title,
            "task_id": task or sid, "task_title": "Archive notes",
            "created_at": "2001-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": body}]}


def anchor_row(text, *, refs=None, turn_start=0):
    if refs is None:
        refs = [{"project": "lab", "session_id": "anchor", "turn_index": 0,
                 "start": 0, "end": len(text), "turn_start": turn_start,
                 "turn_end": turn_start + len(text), "message_indices": [0]}]
    return {"id": "anchor-page", "project_id": "lab", "session_id": "anchor",
            "content": text, "source_refs": json.dumps(refs)}


def catalog_row(title, sid="target"):
    return {"id": "source-" + sid, "external_id": sid, "title": title}


class TitleMentionTests(unittest.TestCase):
    def find(self, text, title, *, refs=None, turn_start=0):
        return title_references._find_reference(
            anchor_row(text, refs=refs, turn_start=turn_start),
            [catalog_row(title)], {"anchor"})

    def test_casefold_and_whitespace_preserve_exact_original_coordinates(self):
        text = "USER: Consult Maße  \t\nDaten. The source is local."
        found = self.find(text, "MASSE DATEN", turn_start=17)
        self.assertIsNotNone(found)
        _, span = found
        start = text.index("Maße")
        end = text.index("Daten") + len("Daten")
        self.assertEqual(span, {"page_start": start, "page_end": end,
                                "turn_index": 0, "turn_start": 17 + start,
                                "turn_end": 17 + end})
        self.assertEqual(text[start:end], "Maße  \t\nDaten")

    def test_partial_casefold_expansions_are_not_titles(self):
        for title, text in (("se Notes", "USER: Read ße Notes. More text."),
                            ("Data ff", "USER: Read Data ﬃ. More text.")):
            with self.subTest(title=title):
                self.assertIsNone(self.find(text, title))

    def test_whole_delimited_chinese_title_and_no_scattered_or_word_internal_match(self):
        title = "云河研究"
        self.assertIsNotNone(self.find("USER: 请查《云河研究》。原始资料已保存。", title))
        for body in ("USER: 云河与研究是分散词。", "USER: 前往云河研究中心。"):
            with self.subTest(body=body):
                self.assertIsNone(self.find(body, title))

    def test_word_and_combining_mark_boundaries(self):
        for text in ("USER: Blue Cafeteria.", "USER: Blue Cafe\u0301.",
                     "USER: XBlue Cafe.", "USER: Blue Cafe_Archive."):
            with self.subTest(text=text):
                self.assertIsNone(self.find(text, "Blue Cafe"))
        self.assertIsNotNone(self.find("USER: Read [Blue Cafe].", "Blue Cafe"))

    def test_prefix_cut_uses_actual_next_character(self):
        title = "Blue Data"
        before = "USER: " + "x" * (4096 - len(title) - 7) + " "
        self.assertEqual(len(before) + len(title), 4096)
        self.assertIsNone(self.find(before + title + "Z.", title))
        found = self.find(before + title + ". Outside the scan prefix.", title)
        self.assertIsNotNone(found)
        self.assertEqual(found[1]["page_end"], 4096)
        self.assertIsNone(self.find(before + "x " + title + ".", title))

    def test_source_cuts_and_cross_turn_join_are_not_boundaries(self):
        self.assertIsNone(self.find("Blue Data. Continued page.", "Blue Data", turn_start=40))
        self.assertIsNone(self.find("USER: Consult Blue Data", "Blue Data"))
        text = "USER: Blue\n\nData."
        refs = [{"project": "lab", "session_id": "anchor", "turn_index": 0,
                 "start": 0, "end": 10, "turn_start": 0, "turn_end": 10},
                {"project": "lab", "session_id": "anchor", "turn_index": 1,
                 "start": 12, "end": len(text), "turn_start": 0,
                 "turn_end": len(text) - 12}]
        self.assertIsNone(self.find(text, "Blue Data", refs=refs))

    def test_source_start_is_provable_and_single_projection_is_required(self):
        text = "Blue Data. A complete original turn starts here."
        self.assertIsNotNone(self.find(text, "Blue Data"))
        row = anchor_row(text)
        refs = json.loads(row["source_refs"])
        self.assertIsNone(self.find(text, "Blue Data", refs=refs + refs))
        refs[0]["project"] = "other"
        self.assertIsNone(self.find(text, "Blue Data", refs=refs))

    def test_uniqueness_precedes_length_filter(self):
        rows = [catalog_row("Blue Data", "short"),
                catalog_row("Blue" + " " * 260 + "Data", "long")]
        result = title_references._find_reference(
            anchor_row("USER: Consult Blue Data."), rows, {"anchor"})
        self.assertIsNone(result)

    def test_casefold_collision_is_ambiguous(self):
        rows = [catalog_row("Maße Daten", "one"), catalog_row("MASSE DATEN", "two")]
        self.assertIsNone(title_references._find_reference(
            anchor_row("USER: Consult Maße Daten."), rows, {"anchor"}))

    def test_title_eligibility_and_parenthetical_suffixes(self):
        for title in ("X YZ", "Blue", "2024 2025", "The And", "Alpha " + "x" * 251):
            with self.subTest(title=title):
                self.assertIsNone(self.find("USER: Consult [" + title + "].", title))
        for title in ("XX YY", "Alpha " + "x" * 250):
            with self.subTest(title=title):
                self.assertIsNotNone(self.find("USER: Consult [" + title + "].", title))
        self.assertIsNone(self.find("USER: Consult Blue Data.", "Blue Data (Notes)"))
        self.assertIsNotNone(self.find("USER: Consult Blue Data (Notes).", "Blue Data (Notes)"))

    def test_earliest_longest_overlap_and_excluded_source_rules(self):
        rows = [catalog_row("Blue Data", "short"),
                catalog_row("Blue Data Handbook", "long"),
                catalog_row("Amber Lantern", "later")]
        text = "USER: Blue Data Handbook. Amber Lantern. Blue Data Handbook."
        found = title_references._find_reference(anchor_row(text), rows, {"anchor"})
        self.assertEqual(found[0]["external_id"], "long")
        self.assertEqual(found[1]["page_start"], text.index("Blue"))
        found = title_references._find_reference(
            anchor_row(text), list(reversed(rows)), {"anchor", "short", "long"})
        self.assertEqual(found[0]["external_id"], "later")


class TitleReferenceRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=5000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)

    def seed(self, *, project="lab", task=None, target_body="The permanent code is cobalt."):
        self.anchor_source = source("anchor", "Anchor Manual",
                                    "Quartz relay diagnostics. Consult Amber Lantern for the code.",
                                    project=project, task=task)
        self.target_source = source("target", "Amber Lantern", target_body,
                                    project=project, task=task)
        self.anchor_record = self.book.ingest(self.anchor_source)
        self.book.ingest(self.target_source)

    def recall(self, **kwargs):
        options = {"project": "lab", "limit": 5, "use_cache": False,
                   "budget_chars": 8000, "follow_titles": True}
        options.update(kwargs)
        query = options.pop("query", "quartz relay")
        return self.book.recall(query, **options)

    def assert_sources(self, response):
        self.assertEqual(response["context_chars"], len(response["context"]))
        self.assertLessEqual(len(response["context"]), response["budget_chars"])
        for result in response["results"]:
            page = self.book.db.execute("SELECT content,session_pk FROM pages WHERE id=?",
                                        (result["id"],)).fetchone()
            for ref in result["source_refs"]:
                original = self.book.db.execute(
                    "SELECT content FROM turns WHERE session_pk=? AND ordinal=?",
                    (page["session_pk"], ref["turn_index"])).fetchone()[0]
                piece = page["content"][ref["start"]:ref["end"]]
                self.assertEqual(piece, original[ref["turn_start"]:ref["turn_end"]])
                self.assertIn(piece, result["text"])
                self.assertEqual(ref["project"], "lab")

    def test_new_source_preserves_anchor_and_original_citations(self):
        self.seed()
        off = self.recall(follow_titles=False)
        on = self.recall()
        proof = on["title_reference"]
        self.assertEqual(off["candidate_count"], 1)
        self.assertEqual(on["candidate_count"], 2)
        self.assertEqual(on["results"][0]["id"], off["results"][0]["id"])
        self.assertEqual(on["results"][1]["score"], 0.0)
        self.assertIn("The permanent code is cobalt.", on["context"])
        self.assertTrue(proof["applied"])
        self.assertEqual(proof["project"], "lab")
        self.assertEqual(proof["anchor_session_id"], "anchor")
        self.assertEqual(proof["target_session_id"], "target")
        self.assertFalse(proof["target_initial_page_in_pool"])
        self.assertFalse(proof["target_initial_session_in_pool"])
        self.assertEqual(proof["target_route"], "title_reference")
        page = self.book.read(proof["anchor_page_id"])["content"]
        mention = proof["mention"]
        self.assertEqual(page[mention["page_start"]:mention["page_end"]], "Amber Lantern")
        self.assert_sources(on)

    def test_existing_tail_candidate_is_promoted_with_its_original_score(self):
        self.seed(target_body="Relay records. " + "Background cabinet inventory. " * 75)
        for number in range(7):
            self.book.ingest(source(f"other-{number}", "Other Notes", "Relay record. " * 12))
        off = self.recall(follow_titles=False, limit=2)
        full = self.recall(follow_titles=False, limit=50, budget_chars=100000)
        on = self.recall(limit=2)
        target = next(result for result in full["results"]
                      if result["source_refs"][0]["session_id"] == "target")
        self.assertEqual(off["results"][0]["source_refs"][0]["session_id"], "anchor")
        self.assertNotIn(target["id"], [result["id"] for result in off["results"]])
        self.assertEqual(on["results"][1]["id"], target["id"])
        self.assertEqual(on["results"][1]["score"], target["score"])
        self.assertEqual(on["candidate_count"], off["candidate_count"])
        self.assertTrue(on["title_reference"]["target_initial_page_in_pool"])
        self.assertTrue(on["title_reference"]["target_initial_session_in_pool"])
        self.assertEqual(on["title_reference"]["target_route"], "existing_lexical")

    def test_chinese_single_route_follows_only_the_delimited_original_title(self):
        self.book.ingest(source("anchor", "天线记录", "量子天线校准请查《云河研究》。"))
        self.book.ingest(source("target", "云河研究", "实验编号为青色。"))
        off = self.recall(query="量子天线", follow_titles=False)
        on = self.recall(query="量子天线")
        self.assertEqual(off["candidate_count"], 1)
        self.assertEqual(on["candidate_count"], 2)
        self.assertTrue(on["title_reference"]["applied"])
        self.assertIn("实验编号为青色。", on["context"])
        self.assert_sources(on)

    def test_new_target_uses_source_section_then_page_order(self):
        self.seed()
        target = dict(self.target_source)
        target["messages"] = [{"role": "user", "content": "Opening specification is copper."},
                              {"role": "user", "content": "Second specification is indigo."}]
        self.book.ingest(target)
        response = self.recall()
        target_result = response["results"][1]
        self.assertIn("Opening specification is copper.", target_result["text"])
        self.assertNotIn("Second specification", target_result["text"])
        self.assertEqual(target_result["source_refs"][0]["turn_index"], 0)

    def test_one_hop_does_not_follow_target_backlinks_or_other_mentions(self):
        self.seed(target_body="Consult Silver Compass and Anchor Manual. The code is cobalt.")
        self.book.ingest(source("third", "Silver Compass", "The third source is violet."))
        response = self.recall()
        sessions = {ref["session_id"] for result in response["results"]
                    for ref in result["source_refs"]}
        self.assertEqual(sessions, {"anchor", "target"})
        self.assertEqual(response["candidate_count"], 2)

    def test_scope_intersection_and_foreign_duplicate_title(self):
        self.seed(task="shared")
        self.book.ingest(source("target", "Amber Lantern", "Foreign code is scarlet.", project="outside"))
        for options in ({}, {"chapter": self.anchor_record["chapter_id"]},
                        {"chapter": self.anchor_record["chapter_id"], "session": None}):
            with self.subTest(options=options):
                response = self.recall(**options)
                self.assertTrue(response["title_reference"]["applied"])
                self.assertNotIn("scarlet", response["context"])
                self.assert_sources(response)
        response = self.recall(session="anchor")
        self.assertFalse(response["title_reference"]["applied"])
        self.assertNotIn("cobalt", response["context"])
        self.assertTrue(all(ref["session_id"] == "anchor" for row in response["results"]
                            for ref in row["source_refs"]))

    def test_target_in_another_chapter_is_not_followed_under_chapter_scope(self):
        self.seed()
        response = self.recall(chapter=self.anchor_record["chapter_id"])
        self.assertFalse(response["title_reference"]["applied"])
        self.assertNotIn("cobalt", response["context"])

    def test_same_scope_normalized_duplicate_title_declines(self):
        self.seed()
        self.book.ingest(source("duplicate", "AMBER   LANTERN", "A different source is green."))
        response = self.recall()
        self.assertFalse(response["title_reference"]["applied"])
        self.assertIsNone(response["title_reference"]["target_initial_page_in_pool"])
        self.assertEqual(response["candidate_count"], 1)

    def test_no_target_page_does_not_try_a_second_source(self):
        self.seed()
        anchor = dict(self.anchor_source)
        anchor["messages"] = [{"role": "user", "content":
                               "Quartz relay. Amber Lantern. Silver Compass."}]
        self.book.ingest(anchor)
        self.book.ingest(source("third", "Silver Compass", "The third source is violet."))
        self.book.db.execute("DELETE FROM pages WHERE session_pk=(SELECT id FROM sessions WHERE project_id=? AND external_id=?)",
                             ("lab", "target"))
        response = self.recall()
        self.assertEqual(response["title_reference"]["reason"], "no_target_page")
        self.assertFalse(response["title_reference"]["applied"])
        self.assertNotIn("violet", response["context"])

    def test_catalog_cap_and_overflow_preserve_original_selection(self):
        self.seed()
        for number in range(510):
            self.book.ingest(source(f"catalog-{number}", f"Catalog entry {number}",
                                    "Unrelated cabinet inventory."))
        response = self.recall()
        self.assertTrue(response["title_reference"]["applied"])
        self.book.ingest(source("overflow", "Overflow Record", "Unrelated cabinet inventory."))
        off = self.recall(follow_titles=False)
        on = self.recall()
        self.assertEqual(on["title_reference"]["reason"], "catalog_limit")
        self.assertEqual(stable(on, without_mode=True), stable(off))

    def test_disabled_mode_preserves_payload_sql_and_cache_identity(self):
        self.seed()
        statements = []
        self.book.db.set_trace_callback(statements.append)
        default = self.book.recall("quartz relay", project="lab", budget_chars=8000, use_cache=False)
        original_statements = list(statements)
        statements.clear()
        disabled = self.recall(follow_titles=False)
        self.book.db.set_trace_callback(None)
        self.assertEqual(stable(default), stable(disabled))
        # FTS emits its own -- PRAGMA data_version trace on the first access;
        # compare application statements, not SQLite's internal cache probes.
        application_sql = lambda values: [value for value in values
                                          if not value.lstrip().startswith("--")]
        self.assertEqual(application_sql(statements), application_sql(original_statements))
        self.assertNotIn("follow_titles", default)
        self.assertNotIn("title_reference", default)
        self.book.cache_size = 8
        first = self.book.recall("quartz relay", project="lab", budget_chars=8000)
        keys = [row[0] for row in self.book.db.execute("SELECT key FROM recall_cache")]
        disabled = self.recall(follow_titles=False, use_cache=True)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(disabled["cache_hit"])
        self.assertEqual([row[0] for row in self.book.db.execute("SELECT key FROM recall_cache")], keys)
        on = self.recall(use_cache=True)
        self.assertFalse(on["cache_hit"])
        self.assertEqual(self.book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 2)
        self.assertTrue(self.recall(use_cache=True)["cache_hit"])

    def test_inactive_calls_never_enter_title_helper_or_change_baseline_result(self):
        self.seed()
        cases = [({"project": None}, "unscoped"), ({"limit": 1}, "result_limit"),
                 ({"budget_chars": 0}, "zero_budget"),
                 ({"query": "latest quartz relay"}, "temporal_query"),
                 ({"query": "previous quartz relay"}, "temporal_query"),
                 ({"query": "the and"}, "no_lexical_results"),
                 ({"query": "unfindable zqwx"}, "no_lexical_results")]
        if HAS_TOKENS:
            cases.append(({"budget_tokens": 0}, "zero_budget"))
        with patch.object(title_references, "follow_title_reference", side_effect=AssertionError("inactive helper")):
            for options, reason in cases:
                with self.subTest(options=options):
                    off = self.recall(follow_titles=False, **options)
                    on = self.recall(**options)
                    self.assertEqual(stable(on, without_mode=True), stable(off))
                    self.assertFalse(on["title_reference"]["active"])
                    self.assertEqual(on["title_reference"]["reason"], reason)
                    self.assertIsNone(on["title_reference"]["target_initial_page_in_pool"])

    def test_strict_boolean_and_incompatible_modes_precede_model_loading(self):
        self.seed()
        for value in (None, 0, 1, "true", []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "follow_titles must be a boolean"):
                self.recall(follow_titles=value)
        with patch.object(self.book, "_semantic_encoder", side_effect=AssertionError("model loaded")):
            for options in ({"semantic": True}, {"coverage": True}, {"strategy": "flat"}):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, "follow_titles requires"):
                    self.recall(**options)

    def test_rename_delete_and_cache_invalidation(self):
        self.seed()
        self.book.cache_size = 8
        initial = self.recall(use_cache=True)
        self.assertTrue(initial["title_reference"]["applied"])
        changed = dict(self.target_source, title="Renamed Record")
        self.book.ingest(changed)
        renamed = self.recall(use_cache=True)
        self.assertFalse(renamed["cache_hit"])
        self.assertFalse(renamed["title_reference"]["applied"])
        self.assertGreater(renamed["revision"], initial["revision"])
        self.book.ingest(self.target_source)
        self.assertTrue(self.recall(use_cache=True)["title_reference"]["applied"])
        self.book.delete_session("lab", "target")
        deleted = self.recall(use_cache=True)
        self.assertFalse(deleted["cache_hit"])
        self.assertFalse(deleted["title_reference"]["applied"])

    @unittest.skipUnless(HAS_TOKENS, "optional tiktoken dependency")
    def test_both_tokenizers_budget_caps_and_selected_but_unreturned_target(self):
        self.seed()
        from memory_book.token_budget import TokenCounter
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (8, 128, 512):
                with self.subTest(tokenizer=tokenizer, budget=budget):
                    response = self.recall(budget_tokens=budget, tokenizer=tokenizer)
                    self.assertTrue(response["title_reference"]["applied"])
                    self.assertLessEqual(response["context_tokens"], budget)
                    self.assertEqual(TokenCounter(tokenizer).count(response["context"]), response["context_tokens"])
                    self.assert_sources(response)
                    if budget == 8:
                        self.assertEqual(response["results"], [])

    def test_concurrent_writer_cannot_change_the_current_title_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with MemoryBook(path, cache_size=8) as reader, MemoryBook(path, cache_size=0) as writer:
                a = source("anchor", "Anchor Manual", "Quartz relay. Consult Amber Lantern.")
                b = source("target", "Amber Lantern", "The original code is cobalt.")
                reader.ingest(a)
                reader.ingest(b)
                original_revision = reader.revision
                original_find = title_references._find_reference

                def update_after_catalog(*args):
                    found = original_find(*args)
                    writer.ingest(dict(b, title="Renamed Record",
                                       messages=[{"role": "user", "content": "The replacement code is scarlet."}]))
                    return found

                with patch.object(title_references, "_find_reference", side_effect=update_after_catalog):
                    response = reader.recall("quartz relay", project="lab", follow_titles=True)
                self.assertEqual(response["revision"], original_revision)
                self.assertTrue(response["title_reference"]["applied"])
                self.assertIn("original code is cobalt", response["context"])
                self.assertNotIn("scarlet", response["context"])
                self.assertEqual(reader.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)
                refreshed = reader.recall("quartz relay", project="lab", follow_titles=True)
                self.assertFalse(refreshed["title_reference"]["applied"])
                self.assertGreater(refreshed["revision"], original_revision)


if __name__ == "__main__":
    unittest.main()
