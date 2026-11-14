"""Exact ranking-prefix bounds, shared directories and conservative fallback."""
import copy
import math
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.text import terms


def session(identity, project="fixture"):
    messages = []
    for number in range(8):
        repeats = 1 + number
        text = ("Quartz pressure " * repeats + "cedars voltage qualified evidence. " +
                "ordinary background " * (36 - 4 * number))
        messages.append({"role": "user", "content": text})
    return {"project": project, "session_id": identity, "task_id": "task-" + identity,
            "title": "Quartz pressure" if int(identity) % 2 else "Other notes",
            "task_title": "Cedar voltage" if int(identity) % 3 else "",
            "created_at": f"2026-11-{int(identity) + 1:02d}T00:00:00Z", "messages": messages}


class CandidateMetadataBoundTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", cache_size=0, segmentation="turn",
                               max_page_chars=900, min_page_chars=0)
        self.addCleanup(self.book.close)
        for number in range(9):
            self.book.ingest(session(str(number)))
        self.book.ingest(session("9", "outside"))
        self.rows = {row["id"]: {"id": row["id"], "rid": row["rid"], "rank": -1.0}
                     for row in self.book.db.execute("SELECT id,rid FROM pages WHERE project_id='fixture'")}
        self.identities = list(self.rows)
        self.relevance = {identity: 4.0 if i < 3 else 0.01 for i, identity in enumerate(self.identities)}

    def assert_original(self, query, **options):
        actual = self.book.recall(query, use_cache=False, **options)
        with patch.object(self.book, "_bounded_candidate_metadata", return_value=None):
            expected = self.book.recall(query, use_cache=False, **options)
        actual.pop("latency_ms")
        expected.pop("latency_ms")
        self.assertEqual(actual, expected)
        return actual

    def test_full_payloads_scopes_limits_budgets_and_fused_routes(self):
        retained = []
        original = self.book._bounded_candidate_metadata

        def observe(rows, relevance, count):
            result = original(rows, relevance, count)
            if result is not None:
                retained.append((len(rows), len(result)))
            return result

        chapter = self.book.db.execute("SELECT id FROM chapters WHERE project_id='fixture' ORDER BY id").fetchone()[0]
        with patch.object(self.book, "_bounded_candidate_metadata", side_effect=observe):
            for query in ("quartz", "quartz pressure", "cedar", "current quartz", "previous current quartz"):
                for scope in ({}, {"project": "fixture"}, {"chapter": chapter}, {"session": "0"},
                              {"project": "fixture", "session": "0"}, {"project": "absent"}):
                    for limit in (1, 5):
                        with self.subTest(query=query, scope=scope, limit=limit):
                            self.assert_original(query, budget_chars=4000, limit=limit, **scope)
            for tokenizer in ("cl100k_base", "o200k_base"):
                for tokens in (0, 512, 1024, 2048):
                    self.assert_original("quartz pressure", project="fixture", budget_chars=8000,
                                         budget_tokens=tokens, tokenizer=tokenizer)
            for chars in (0, 100, 100000):
                self.assert_original("quartz pressure", budget_chars=chars, limit=50)
        self.assertTrue(retained, "Fixture must execute real pruning")
        self.assertTrue(all(before > after for before, after in retained))

    def test_original_novelty_pool_including_current_single_word_limit_one(self):
        for query, limit, expected in (("quartz", 1, 1), ("quartz pressure", 1, 1),
                ("quartz pressure", 3, 12), ("current quartz", 1, 4),
                ("previous current quartz", 1, 1), ("latest quartz", 2, 8)):
            with self.subTest(query=query, limit=limit):
                with patch.object(self.book, "_bounded_candidate_metadata", return_value=None) as bound:
                    self.book.recall(query, limit=limit, use_cache=False)
                bound.assert_called_once()
                self.assertEqual(bound.call_args.args[2], expected)

    def test_late_title_boost_and_exact_upper_bound_ties_are_retained(self):
        relevance = {identity: 0.01 for identity in self.identities}
        for identity in self.identities[:3]:
            relevance[identity] = 1.15
        relevance[self.identities[3]] = 1.05  # Can overtake the base leaders.
        relevance[self.identities[4]] = 1.0   # Upper bound equals the floor.
        relevance[self.identities[5]] = math.nextafter(1.0, 0.0)
        result = self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), relevance, 3)
        self.assertIsNotNone(result)
        self.assertEqual(list(result), self.identities[:5])
        self.assertGreater(1.05 * 1.15, 1.15)
        self.assertLess(relevance[self.identities[5]] * 1.15, 1.15)

    def test_shared_directory_query_includes_every_pair_once(self):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        result = self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3)
        self.book.db.set_trace_callback(None)
        self.assertEqual(len(result), 3)
        queries = [sql for sql in statements if sql.startswith("WITH requested")]
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].split("SELECT requested", 1)[0].count("),(") + 1, 9)
        self.assertEqual(len(self.rows), 72)

    def test_ties_zero_nonfinite_negative_and_small_sets_keep_old_path(self):
        possibilities = [{identity: value for identity in self.identities} for value in (0.0, 1.0)]
        for value in (float("nan"), float("inf"), float("-inf"), -0.01):
            values = dict(self.relevance)
            values[self.identities[-1]] = value
            possibilities.append(values)
        statements = []
        self.book.db.set_trace_callback(statements.append)
        for relevance in possibilities:
            self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), relevance, 3))
        self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 72))
        self.book.db.set_trace_callback(None)
        self.assertEqual(statements, [])

    def test_custom_row_text_and_directory_functions_fall_back(self):
        original_row, original_text = self.book.db.row_factory, self.book.db.text_factory
        for name, value in (("row_factory", lambda cursor, row: sqlite3.Row(cursor, row)),
                            ("text_factory", lambda raw: raw.decode("utf-8"))):
            try:
                setattr(self.book.db, name, value)
                self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3))
                self.assert_original("quartz pressure", project="fixture")
            finally:
                self.book.db.row_factory, self.book.db.text_factory = original_row, original_text
        with patch.object(self.book, "_directory_tokens", side_effect=lambda text: frozenset(terms(text, query=True))):
            self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3))
            self.assert_original("quartz pressure", project="fixture")

    def assert_old_error(self, query, **options):
        errors = []
        for enabled in (True, False):
            try:
                if enabled:
                    self.book.recall(query, use_cache=False, **options)
                else:
                    with patch.object(self.book, "_bounded_candidate_metadata", return_value=None):
                        self.book.recall(query, use_cache=False, **options)
            except Exception as exc:
                errors.append((type(exc), exc.args))
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0], errors[1])

    def test_orphaned_tail_keeps_old_error_and_does_not_partially_mutate_rows(self):
        identity = self.identities[-1]
        self.book.db.execute("PRAGMA foreign_keys=OFF")
        self.book.db.execute("UPDATE pages SET chapter_id='missing' WHERE id=?", (identity,))
        rows = copy.deepcopy(self.rows)
        self.assertIsNone(self.book._bounded_candidate_metadata(rows, self.relevance, 3))
        self.assertEqual(rows, self.rows)
        self.assert_old_error("quartz", project="fixture", limit=1)

    def test_nontext_tail_title_keeps_original_type_error(self):
        chapter = self.book.db.execute("SELECT chapter_id FROM pages WHERE id=?", (self.identities[-1],)).fetchone()[0]
        self.book.db.execute("UPDATE chapters SET title=? WHERE id=?", (sqlite3.Binary(b"bad"), chapter))
        rows = copy.deepcopy(self.rows)
        self.assertIsNone(self.book._bounded_candidate_metadata(rows, self.relevance, 3))
        self.assertEqual(rows, self.rows)
        self.assert_old_error("quartz", project="fixture", limit=1)

    def test_nontext_identifiers_and_dates_keep_original_path(self):
        identity = self.identities[-1]
        self.book.db.execute("PRAGMA foreign_keys=OFF")
        original = self.book.db.execute("SELECT chapter_id,session_pk FROM pages WHERE id=?", (identity,)).fetchone()
        for column, index in (("chapter_id", 0), ("session_pk", 1)):
            with self.subTest(column=column):
                self.book.db.execute(f"UPDATE pages SET {column}=? WHERE id=?", (sqlite3.Binary(b"bad"), identity))
                self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3))
                self.book.db.execute(f"UPDATE pages SET {column}=? WHERE id=?", (original[index], identity))
        self.book.db.execute("UPDATE sessions SET created_at=? WHERE id=?", (sqlite3.Binary(b"bad"), original[1]))
        self.assertIsNone(self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3))

    def test_empty_directory_titles_remain_valid(self):
        self.book.db.execute("UPDATE chapters SET title=''")
        self.book.db.execute("UPDATE sessions SET title=''")
        result = self.book._bounded_candidate_metadata(copy.deepcopy(self.rows), self.relevance, 3)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(row["chapter_title"] == row["session_title"] == "" for row in result.values()))
        self.assert_original("quartz pressure", project="fixture")

    def test_selected_source_corruption_still_raises_original_error(self):
        response = self.assert_original("quartz pressure", project="fixture", budget_chars=8000, budget_tokens=1024)
        identity = response["results"][0]["id"]
        self.book.db.execute("UPDATE pages SET content=replace(content,'Quartz','Wrong!') WHERE id=?", (identity,))
        self.assert_old_error("quartz pressure", project="fixture", budget_chars=8000, budget_tokens=1024)

    def test_coverage_flat_and_semantic_paths_retain_original_candidate_population(self):
        with patch.object(self.book, "_bounded_candidate_metadata", side_effect=AssertionError("must not prune")) as bound:
            self.book.recall("quartz pressure and cedar voltage", coverage=True, use_cache=False)
            self.book.recall("quartz pressure", strategy="flat", use_cache=False)
            bound.assert_not_called()
        encoder = SimpleNamespace(fingerprint="fixture-only-no-model")
        with patch.object(self.book, "_semantic_encoder", return_value=encoder), \
                patch("memory_book.semantic.check_index"), \
                patch("memory_book.semantic.rank_pages", return_value=[]), \
                patch("memory_book.semantic.fuse_candidates", side_effect=lambda lexical, _: lexical + [dict(lexical[-1])]), \
                patch.object(self.book, "_bounded_candidate_metadata", side_effect=AssertionError("must not prune")) as bound:
            result = self.book.recall("quartz pressure", semantic=True, use_cache=False)
            bound.assert_not_called()
        self.assertEqual(result["candidate_count"], 81)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
