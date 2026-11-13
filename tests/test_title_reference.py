"""Invented T1 source, scope, ambiguity, budget and default-compatibility cases."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.store import INDEX_VERSION, RECALL_VERSION
from memory_book.title_reference import (_eligible_title, _mentions, _normalization_map,
                                        follow_title_reference, normalize_title)


def source(identity, title, text, *, project="lab", task="archive"):
    return {"project": project, "session_id": identity, "title": title,
            "task_id": task, "task_title": "Evidence archive",
            "created_at": "2025-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": text}]}


def without_timing(response, *, provenance=False):
    result = {key: value for key, value in response.items() if key != "latency_ms"}
    if provenance:
        result.pop("title_reference", None)
    return result


class MentionMappingTests(unittest.TestCase):
    def mentions(self, text, *titles):
        return _mentions(text, [(normalize_title(title), {"id": str(i)})
                                for i, title in enumerate(titles)])

    def test_casefold_whitespace_and_exact_original_span(self):
        text = "prefix:  STRAẞE\u00a0\t Laboratory ; suffix"
        found = self.mentions(text, "Straße Laboratory")
        self.assertEqual(len(found), 1)
        lo, hi, _ = found[0]
        self.assertEqual(text[lo:hi], "STRAẞE\u00a0\t Laboratory")
        for text in ("\u001c A\x85 B \u00a0", "İ e\u0301 Straße", " 中文\t名字 "):
            normalized, mapping = _normalization_map(text)
            self.assertEqual(normalized, normalize_title(text))
            self.assertEqual(len(normalized), len(mapping))

    def test_partial_casefold_expansions_are_rejected(self):
        self.assertEqual(self.mentions("Alpha Maß", "Alpha Mas"), [])
        self.assertEqual(self.mentions("Alpha İ", "Alpha i"), [])
        self.assertTrue(self.mentions("Alpha Maß", "Alpha Mass"))
        self.assertTrue(self.mentions("Alpha İ", "Alpha i\u0307"))

    def test_combining_marks_letters_numbers_and_underscore_are_internal(self):
        for before, after in (("a", ""), ("7", ""), ("_", ""), ("\u0301", ""),
                              ("", "a"), ("", "7"), ("", "_"), ("", "\u0301")):
            with self.subTest(before=before, after=after):
                self.assertEqual(self.mentions(before + "Alpha Beta" + after, "Alpha Beta"), [])
        self.assertTrue(self.mentions("《青石天文台》", "青石天文台"))
        self.assertEqual(self.mentions("青石和天文台", "青石天文台"), [])
        self.assertEqual(self.mentions("新青石天文台", "青石天文台"), [])

    def test_prefix_boundary_checks_the_actual_next_character(self):
        title = "Alpha Beta"
        prefix = "." * (4096 - len(title)) + title
        self.assertTrue(self.mentions(prefix + ".", title))
        self.assertEqual(self.mentions(prefix + "x", title), [])
        self.assertEqual(self.mentions(prefix + "\u0301", title), [])
        self.assertEqual(self.mentions("." + prefix, title), [])

    def test_earliest_longest_then_stable_source_order(self):
        found = self.mentions("Alpha Beta Annex then Gamma Delta then Alpha Beta.",
                              "Gamma Delta", "Alpha Beta", "Alpha Beta Annex")
        self.assertEqual(found[0][2]["id"], "2")
        self.assertEqual(found[1][2]["id"], "1")
        self.assertEqual(found[2][2]["id"], "0")

    def test_title_eligibility_preserves_registered_rules_only(self):
        for title in ("1234 5678", "１２３ ４５６", "1234", "Cedar", "A B", "x" * 257):
            with self.subTest(title=title):
                self.assertFalse(_eligible_title(title))
        for title in ("Alpha Beta", "青石天文台", "General Notes", "Alpha Beta (film)"):
            with self.subTest(title=title):
                self.assertTrue(_eligible_title(title))
        self.assertEqual(self.mentions("Alpha Beta (film)", "Alpha Beta (book)"), [])


class TitleReferenceTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)

    def add(self, identity, title, text, **kwargs):
        return self.book.ingest(source(identity, title, text, **kwargs))

    def seed(self, title="Cedar Observatory"):
        self.add("anchor", "Calibration memo", f"quartzsignal points to {title}. quartzsignal is documented here.")
        self.add("target", title, "It stands beside the northern inlet.")

    def recall(self, **options):
        arguments = {"project": "lab", "limit": 5, "budget_chars": 4000, "use_cache": False}
        arguments.update(options)
        return self.book.recall("quartzsignal", **arguments)

    def ordered(self, identities):
        rows = []
        for i, identity in enumerate(identities):
            row = dict(self.book.db.execute(
                "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
                "s.external_id session_id,s.title session_title,s.created_at "
                "FROM pages p JOIN sessions s ON s.id=p.session_pk "
                "JOIN chapters c ON c.id=p.chapter_id WHERE s.external_id=? ORDER BY p.rid LIMIT 1",
                (identity,)).fetchone())
            row["score"] = 10.0 - i
            rows.append(row)
        return rows

    def test_unique_title_new_source_has_exact_native_provenance(self):
        self.seed()
        original, expanded = self.recall(), self.recall(follow_titles=True)
        self.assertNotIn("title_reference", original)
        state = expanded["title_reference"]
        self.assertTrue(state["active"])
        self.assertTrue(state["applied"])
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["target"]["session_id"], "target")
        self.assertEqual(state["target"]["route"], "title_reference")
        self.assertFalse(state["target_initial_page_in_pool"])
        self.assertFalse(state["target_initial_session_in_pool"])
        self.assertEqual(expanded["candidate_count"], original["candidate_count"] + 1)
        self.assertEqual(expanded["results"][0]["id"], original["results"][0]["id"])
        self.assertEqual(expanded["results"][1]["score"], 0.0)
        page = self.book.read(state["anchor"]["page_id"])["content"]
        lo, hi = state["mention"]["page_span"]
        self.assertEqual(page[lo:hi], "Cedar Observatory")
        self.assertEqual(state["mention"]["turn_span"], [lo, hi])
        self.assertEqual(state["mention"]["turn_index"], 0)
        self.assertLessEqual(expanded["context_chars"], 4000)

    def test_chinese_full_title_and_casefold_expansion_work(self):
        for title, mention in (("青石天文台", "青石天文台"),
                               ("Straße Laboratory", "STRAẞE\u00a0\t Laboratory")):
            with self.subTest(title=title), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("anchor", "Calibration memo", f"quartzsignal cites 《{mention}》。"))
                book.ingest(source("target", title, "Separate source information."))
                result = book.recall("quartzsignal", project="lab", follow_titles=True)
                self.assertTrue(result["title_reference"]["applied"])
                lo, hi = result["title_reference"]["mention"]["page_span"]
                self.assertEqual(book.read(result["results"][0]["id"])["content"][lo:hi], mention)

    def test_original_candidate_promotion_keeps_its_score_and_union(self):
        self.seed()
        self.add("middle", "Middle record", "quartzsignal intermediate evidence.")
        candidates = self.ordered(["anchor", "middle", "target"])
        expanded, state = follow_title_reference(self.book.db, candidates, project="lab",
                                                 chapter=None, session=None, limit=2)
        self.assertTrue(state["target_initial_page_in_pool"])
        self.assertTrue(state["target_initial_session_in_pool"])
        self.assertEqual(state["target"]["route"], "lexical")
        self.assertEqual([row["session_id"] for row in expanded], ["anchor", "target", "middle"])
        self.assertEqual(expanded[1]["score"], candidates[2]["score"])
        self.assertEqual(len(expanded), len(candidates))

    def test_already_selected_source_is_not_inserted_again(self):
        self.seed()
        candidates = self.ordered(["anchor", "target"])
        expanded, state = follow_title_reference(self.book.db, candidates, project="lab",
                                                 chapter=None, session=None, limit=2)
        self.assertIs(expanded, candidates)
        self.assertFalse(state["applied"])
        self.assertNotIn("target_initial_session_in_pool", state)

    def test_duplicate_titles_count_before_eligibility_filtering(self):
        self.seed()
        self.add("collision", "Cedar" + " " * 260 + "Observatory", "Unrelated source.")
        state = self.recall(follow_titles=True)["title_reference"]
        self.assertFalse(state["applied"])
        self.assertNotIn("target_initial_page_in_pool", state)

    def test_parenthetical_suffix_is_part_of_the_title(self):
        self.seed("Cedar Observatory (book)")
        self.add("film", "Cedar Observatory (film)", "Other source.")
        self.assertEqual(self.recall(follow_titles=True)["title_reference"]["target"]["session_id"], "target")

    def test_one_target_earliest_longest_and_no_recursive_hop(self):
        self.add("anchor", "Calibration memo", "quartzsignal cites Cedar Observatory Annex. Later Pine Laboratory; Cedar Observatory Annex again.")
        self.add("short", "Cedar Observatory", "A shorter title.")
        self.add("long", "Cedar Observatory Annex", "Read Pine Laboratory for another source.")
        self.add("other", "Pine Laboratory", "Another source.")
        result = self.recall(follow_titles=True)
        self.assertEqual(result["title_reference"]["target"]["session_id"], "long")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(len({row["id"] for row in result["results"]}), 2)

    def test_empty_first_target_does_not_try_a_later_mention(self):
        self.add("anchor", "Calibration memo", "quartzsignal cites Cedar Observatory and Pine Laboratory.")
        self.add("empty", "Cedar Observatory", "Temporary source.")
        self.add("later", "Pine Laboratory", "Later source.")
        self.book.db.execute("DELETE FROM pages WHERE session_pk=(SELECT id FROM sessions WHERE external_id='empty')")
        result = self.recall(follow_titles=True)
        self.assertEqual(result["title_reference"]["reason"], "no_target_page")
        self.assertFalse(result["title_reference"]["applied"])
        self.assertNotIn("target_initial_page_in_pool", result["title_reference"])
        self.assertEqual(len(result["results"]), 1)

    def test_scope_filters_catalog_and_target(self):
        anchor = self.add("anchor", "Calibration memo", "quartzsignal cites Cedar Observatory.", task="first")
        self.add("target", "Cedar Observatory", "The answer is here.", task="second")
        self.add("foreign", "Cedar Observatory", "Foreign duplicate.", project="elsewhere")
        self.assertTrue(self.recall(follow_titles=True)["title_reference"]["applied"])
        for scope in ({"chapter": anchor["chapter_id"]}, {"session": "anchor"}, {"project": "missing"}):
            with self.subTest(scope=scope):
                state = self.recall(follow_titles=True, **scope)["title_reference"]
                self.assertFalse(state["applied"])
                self.assertNotIn("target_initial_session_in_pool", state)

    def test_inactive_modes_preserve_payload_and_skip_catalog(self):
        self.seed()
        cases = (("quartzsignal", {"project": None}, "project_required"),
                 ("quartzsignal", {"limit": 1}, "limit_below_two"),
                 ("quartzsignal", {"budget_chars": 0}, "zero_character_budget"),
                 ("current quartzsignal", {}, "temporal_query"),
                 ("old quartzsignal", {}, "temporal_query"),
                 ("2025 quartzsignal", {}, "temporal_query"),
                 ("the", {}, "no_lexical_results"),
                 ("unknownneedle", {}, "no_lexical_results"))
        for query, changes, reason in cases:
            with self.subTest(query=query, changes=changes):
                options = {"project": "lab", "use_cache": False, **changes}
                old = self.book.recall(query, **options)
                trace = []
                self.book.db.set_trace_callback(trace.append)
                try:
                    new = self.book.recall(query, follow_titles=True, **options)
                finally:
                    self.book.db.set_trace_callback(None)
                self.assertEqual(without_timing(old), without_timing(new, provenance=True))
                self.assertEqual(new["title_reference"]["reason"], reason)
                self.assertFalse(new["title_reference"]["active"])
                self.assertFalse(any("LIMIT 513" in sql for sql in trace))

    def test_strict_flag_and_incompatible_options(self):
        for value in (None, 0, 1, "false", "true", [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "boolean"):
                self.recall(follow_titles=value)
        for options in ({"semantic": True}, {"coverage": True}, {"strategy": "flat"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.recall(follow_titles=True, **options)
        self.recall(follow_titles=False, strategy="flat")

    def test_false_uses_old_cache_key_and_trace(self):
        self.seed()
        self.book.cache_size = 8
        original = self.recall(use_cache=True)
        explicit = self.recall(use_cache=True, follow_titles=False)
        self.assertTrue(explicit["cache_hit"])
        fields = [INDEX_VERSION, RECALL_VERSION, "quartzsignal", "lab", None, None, 4000, 5, "book", False]
        key = hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(self.book.db.execute("SELECT key FROM recall_cache").fetchone()[0], key)
        explicit["cache_hit"] = original["cache_hit"]
        self.assertEqual(without_timing(original), without_timing(explicit))
        on = self.recall(use_cache=True, follow_titles=True)
        self.assertFalse(on["cache_hit"])
        self.assertTrue(self.recall(use_cache=True, follow_titles=True)["cache_hit"])
        self.assertEqual(self.book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0], 2)
        traces = []
        for flag in (None, False):
            trace = []
            self.book.db.set_trace_callback(trace.append)
            try:
                self.recall(**({} if flag is None else {"follow_titles": flag}))
            finally:
                self.book.db.set_trace_callback(None)
            traces.append(trace)
        self.assertEqual(*traces)

    def test_rename_and_delete_invalidate_opt_in_cache(self):
        self.seed()
        self.book.cache_size = 8
        old = self.recall(use_cache=True, follow_titles=True)
        self.assertTrue(old["title_reference"]["applied"])
        self.add("target", "Renamed Observatory", "It stands beside the northern inlet.")
        changed = self.recall(use_cache=True, follow_titles=True)
        self.assertFalse(changed["cache_hit"])
        self.assertFalse(changed["title_reference"]["applied"])
        self.assertGreater(changed["revision"], old["revision"])
        self.book.delete_session("lab", "target")
        self.assertFalse(self.recall(use_cache=True, follow_titles=True)["title_reference"]["applied"])

    def test_source_neighbor_corruption_cannot_invent_a_word_boundary(self):
        for original, damaged in (("AAlpha Beta", " Alpha Beta"), ("Alpha BetaX", "Alpha Beta ")):
            with self.subTest(original=original), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("anchor", "Calibration memo", "quartzsignal cites " + original + "."))
                book.ingest(source("target", "Alpha Beta", "Separate source."))
                row = book.db.execute("SELECT p.id,p.content FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE s.external_id='anchor'").fetchone()
                book.db.execute("UPDATE pages SET content=? WHERE id=?", (row["content"].replace(original, damaged), row["id"]))
                result = book.recall("quartzsignal", project="lab", use_cache=False, follow_titles=True)
                self.assertFalse(result["title_reference"]["applied"])

    def test_single_mention_cannot_cross_turn_mapping(self):
        self.add("anchor", "Calibration memo", "quartzsignal cites Cedar Observatory.")
        self.add("target", "Cedar Observatory", "Separate source.")
        row = self.book.db.execute("SELECT p.id,p.content,p.source_refs FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE s.external_id='anchor'").fetchone()
        original_ref = json.loads(row["source_refs"])[0]
        split = row["content"].index("Observatory")
        left = {**original_ref, "end": split, "turn_end": split}
        right = {**original_ref, "start": split, "turn_start": split}
        self.book.db.execute("UPDATE pages SET source_refs=? WHERE id=?", (json.dumps([left, right]), row["id"]))
        self.assertFalse(self.recall(follow_titles=True)["title_reference"]["applied"])

    def test_unproven_original_slice_edges_are_rejected(self):
        for edge in ("left", "right"):
            with self.subTest(edge=edge), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("anchor", "Calibration memo", "quartzsignal cites Alpha Beta."))
                book.ingest(source("target", "Alpha Beta", "Separate source."))
                row = book.db.execute("SELECT p.id,p.content,p.source_refs FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE s.external_id='anchor'").fetchone()
                full = row["content"]
                start = full.index("Alpha Beta") if edge == "left" else 0
                end = full.index("Alpha Beta") + len("Alpha Beta") if edge == "right" else len(full)
                original_ref = json.loads(row["source_refs"])[0]
                ref = {**original_ref, "start": 0, "end": end - start,
                       "turn_start": start, "turn_end": end}
                book.db.execute("UPDATE pages SET content=?,source_refs=? WHERE id=?",
                                (full[start:end], json.dumps([ref]), row["id"]))
                result = book.recall("quartzsignal", project="lab", follow_titles=True, use_cache=False)
                self.assertFalse(result["title_reference"]["applied"])

    def test_real_original_turn_end_proves_the_boundary(self):
        self.add("anchor", "Calibration memo", "quartzsignal cites Alpha Beta")
        self.add("target", "Alpha Beta", "Separate source.")
        state = self.recall(follow_titles=True)["title_reference"]
        self.assertTrue(state["applied"])
        page = self.book.read(state["anchor"]["page_id"])["content"]
        self.assertEqual(state["mention"]["page_span"][1], len(page))

    def test_source_projection_rejects_corrupt_identity_or_coordinates(self):
        self.seed()
        row = self.book.db.execute("SELECT p.id,p.source_refs FROM pages p JOIN sessions s ON s.id=p.session_pk WHERE s.external_id='anchor'").fetchone()
        original = json.loads(row["source_refs"])[0]
        changes = ({"project": "elsewhere"}, {"session_id": "other"}, {"turn_index": True},
                   {"turn_start": -1}, {"turn_end": original["turn_end"] + 1})
        for change in changes:
            with self.subTest(change=change):
                self.book.db.execute("UPDATE pages SET source_refs=? WHERE id=?",
                                     (json.dumps([{**original, **change}]), row["id"]))
                # Isolate the opt-in decision: the unchanged source assembler
                # has its own corruption policy for these deliberately bad maps.
                _, state = follow_title_reference(self.book.db, self.ordered(["anchor"]),
                                                  project="lab", chapter=None, session=None, limit=5)
                self.assertFalse(state["applied"])
        self.book.db.execute("UPDATE pages SET source_refs=? WHERE id=?", (row["source_refs"], row["id"]))

    def test_complete_pool_promotion_beyond_default_materialized_prefix(self):
        self.add("anchor", "Calibration memo", "quartzsignal " * 20 + "cites Cedar Observatory.")
        for i in range(30):
            self.add(f"middle-{i}", f"Middle source {i}", "quartzsignal witnessed here.")
        self.add("target", "Cedar Observatory", "quartzsignal " + "Independent source evidence. " * 160)
        expression = '("quartzsignal") AND body : ("quartzsignal")'
        ordered = self.book.db.execute(
            "SELECT s.external_id,bm25(pages_fts,2.0,2.0,1.0,0.25) rank FROM pages_fts "
            "JOIN pages p ON p.rid=pages_fts.rowid JOIN sessions s ON s.id=p.session_pk "
            "WHERE pages_fts MATCH ? ORDER BY rank,p.id LIMIT 96", (expression,)).fetchall()
        positions = [row["external_id"] for row in ordered]
        self.assertGreater(positions.index("target"), 20)
        original, expanded = self.recall(), self.recall(follow_titles=True)
        state = expanded["title_reference"]
        self.assertTrue(state["applied"])
        self.assertEqual(state["target"]["session_id"], "target")
        self.assertEqual(state["target"]["route"], "lexical")
        self.assertTrue(state["target_initial_page_in_pool"])
        self.assertTrue(state["target_initial_session_in_pool"])
        self.assertEqual(expanded["candidate_count"], original["candidate_count"])
        self.assertEqual(expanded["results"][0]["id"], original["results"][0]["id"])

    def test_real_anchor_prefix_boundary_never_reads_a_whole_long_turn(self):
        title = "Cedar Observatory"
        initial = "USER: quartzsignal "
        body = "quartzsignal " + "." * (4096 - len(initial) - len(title)) + title
        for neighbor, applied in ((".", True), ("x", False), ("\u0301", False)):
            with self.subTest(neighbor=neighbor), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("anchor", "Calibration memo", body + neighbor + " extra source text." * 200))
                book.ingest(source("target", title, "Separate source."))
                trace = []
                book.db.set_trace_callback(trace.append)
                try:
                    result = book.recall("quartzsignal", project="lab", follow_titles=True, use_cache=False)
                finally:
                    book.db.set_trace_callback(None)
                self.assertEqual(result["title_reference"]["applied"], applied)
                turn_reads = [sql for sql in trace if "FROM turns" in sql and not sql.startswith("--")]
                self.assertTrue(all("substr(content," in sql for sql in turn_reads))
                if applied:
                    self.assertEqual(result["title_reference"]["mention"]["page_span"][1], 4096)

    def test_catalog_cap_is_scoped_and_read_with_limit_plus_one(self):
        self.seed()
        for i in range(510):
            self.add(f"filler-{i}", f"Unused source {i}", "No queried token here.")
        self.add("outside", "Outside source", "Foreign page.", project="elsewhere")
        self.assertTrue(self.recall(follow_titles=True)["title_reference"]["applied"])
        self.add("overflow", "Overflow source", "No queried token here.")
        trace = []
        self.book.db.set_trace_callback(trace.append)
        try:
            result = self.recall(follow_titles=True)
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual(result["title_reference"]["reason"], "catalog_overflow")
        catalogs = [sql for sql in trace if "SELECT id,external_id,title FROM sessions" in sql]
        self.assertEqual(len(catalogs), 1)
        self.assertIn("LIMIT 513", catalogs[0])

    def test_concurrent_writer_cannot_mix_catalog_and_source_snapshots(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            database = Path(directory) / "book.db"
            with MemoryBook(database, segmentation="turn", cache_size=0) as reader, MemoryBook(database) as writer:
                reader.ingest(source("anchor", "Calibration memo", "quartzsignal cites Cedar Observatory."))
                writer.ingest(source("target", "Cedar Observatory", "Original target content."))
                old_revision = reader.revision
                changed = []

                def edit_during_read(sql):
                    if "SELECT id,external_id,title FROM sessions" in sql and not changed:
                        changed.append(True)
                        writer.ingest(source("target", "Renamed Observatory", "New target content."))

                reader.db.set_trace_callback(edit_during_read)
                try:
                    result = reader.recall("quartzsignal", project="lab", follow_titles=True, use_cache=False)
                finally:
                    reader.db.set_trace_callback(None)
                self.assertTrue(changed)
                self.assertEqual(result["revision"], old_revision)
                self.assertTrue(result["title_reference"]["applied"])
                self.assertIn("Original target content.", result["context"])
                self.assertNotIn("New target content.", result["context"])
                self.assertFalse(reader.recall("quartzsignal", project="lab", follow_titles=True)["title_reference"]["applied"])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens] for exact caps")
    def test_both_tokenizers_keep_source_and_budget_caps(self):
        from memory_book.token_budget import TokenCounter
        self.seed()
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 1, 32, 128, 512, 1024):
                with self.subTest(tokenizer=tokenizer, budget=budget):
                    result = self.recall(follow_titles=True, tokenizer=tokenizer,
                                         budget_tokens=budget, budget_chars=4000)
                    self.assertLessEqual(result["context_tokens"], budget)
                    self.assertEqual(result["context_tokens"], TokenCounter(tokenizer).count(result["context"]))
                    self.assertLessEqual(result["context_chars"], 4000)
                    self.assertEqual(len({row["id"] for row in result["results"]}), len(result["results"]))
                    for row in result["results"]:
                        page = self.book.read(row["id"])["content"]
                        for lo, hi in row["excerpt_spans"]:
                            self.assertIn(page[lo:hi], row["text"])
                    if budget == 0:
                        self.assertFalse(result["title_reference"]["active"])
                        self.assertEqual(result["title_reference"]["reason"], "zero_token_budget")


if __name__ == "__main__":
    unittest.main()
