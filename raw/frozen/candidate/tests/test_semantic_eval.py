import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from benchmarks.data import Evidence, QueryCase
from benchmarks.semantic_eval import Progress, diagnostics, page_projection_errors, paired_changes, source_snapshot


class SemanticEvaluationTests(unittest.TestCase):
    def test_valid_source_substring_cannot_hide_invented_output_text(self):
        result = {"id": "page", "excerpt_spans": [[0, 8]], "text": "original…"}
        response = {"results": [result]}
        self.assertEqual(page_projection_errors(response, {"page": "original sentence"}), 0)
        result["text"] = "original invented conclusion"
        self.assertEqual(page_projection_errors(response, {"page": "original sentence"}), 1)
        result["text"] = "original…"
        result["excerpt_spans"] = [[0, 999]]
        self.assertEqual(page_projection_errors(response, {"page": "original sentence"}), 1)

    def test_resume_preserves_interruption_and_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.db"
            progress = Progress(path, {"source": "a", "model": "b"})
            complete = progress.start("config", 0, "one", "lexical")
            progress.finish(complete, 1.25, {"context_sha256": "first"})
            interrupted = progress.start("config", 0, "two", "semantic")
            progress.close()
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                Progress(path, {"source": "changed", "model": "b"})
            progress = Progress(path, {"source": "a", "model": "b"})
            self.assertEqual(progress.completed(), {("config", 0, "one", "lexical")})
            row = progress.db.execute("SELECT * FROM samples WHERE seq=?", (interrupted,)).fetchone()
            self.assertEqual(row["status"], "interrupted")
            self.assertIsNone(row["elapsed_ms"])
            retry = progress.start("config", 0, "two", "semantic")
            progress.finish(retry, 2.5, {"context_sha256": "second"})
            self.assertEqual(progress.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 3)
            self.assertEqual(len(progress.completed()), 2)
            progress.close()

    def test_duplicate_success_cannot_double_count_a_question(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = Progress(Path(directory) / "progress.db", {})
            first = progress.start("config", 0, "q", "semantic")
            progress.finish(first, 1, {})
            duplicate = progress.start("config", 0, "q", "semantic")
            with self.assertRaises(sqlite3.IntegrityError):
                progress.finish(duplicate, 2, {})
            progress.close()

    def test_low_overlap_and_cross_chapter_are_distinct_diagnostics(self):
        case = QueryCase("q", "accessible exhibition accommodation", "paraphrase", "p",
                         (Evidence("s1", 0, "large print labels"), Evidence("s2", 0, "audio guides")))
        result = diagnostics(case, [("p", "s1", "c1"), ("p", "s2", "c2"), ("other", "s1", "c3")])
        self.assertEqual(result["required_chapters"], 2)
        self.assertEqual(result["query_term_coverage_by_required_text"], 0)
        self.assertIn("low_lexical_overlap_le_0.25", result["diagnostic_groups"])
        self.assertIn("cross_chapter", result["diagnostic_groups"])
        self.assertIn("cross_session", result["diagnostic_groups"])
        unsupported = diagnostics(QueryCase("absent", "missing fact", "unsupported", "p", answerable=False), [])
        self.assertIsNone(unsupported["query_term_coverage_by_required_text"])
        self.assertNotIn("low_lexical_overlap_le_0.25", unsupported["diagnostic_groups"])

    def test_all_gains_and_losses_survive_aggregate_tie(self):
        old = [{"id": "gain", "evidence_ranks": [None, 1], "complete": False, "context_sha256": "a"},
               {"id": "loss", "evidence_ranks": [1, 2], "complete": True, "context_sha256": "b"}]
        new = [{"id": "gain", "evidence_ranks": [1, 2], "complete": True, "context_sha256": "c"},
               {"id": "loss", "evidence_ranks": [None, 1], "complete": False, "context_sha256": "d"}]
        result = paired_changes(old, new)
        self.assertEqual(result["complete_question_gains"], ["gain"])
        self.assertEqual(result["complete_question_losses"], ["loss"])
        self.assertEqual(result["annotation_gains"], [{"id": "gain", "annotation": 0}])
        self.assertEqual(result["annotation_losses"], [{"id": "loss", "annotation": 0}])
        with self.assertRaisesRegex(ValueError, "different query IDs"):
            paired_changes(old, new[:1])

    def test_derived_index_is_excluded_but_source_addresses_are_hashed(self):
        with sqlite3.connect(":memory:") as db:
            for table in ("projects", "chapters", "sessions", "turns", "sections", "pages"):
                db.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY,content TEXT)")
                db.execute(f"INSERT INTO {table} VALUES('one','original')")
            before = source_snapshot(db)
            db.execute("CREATE TABLE semantic_vectors(vector BLOB)")
            db.execute("INSERT INTO semantic_vectors VALUES(?)", (b"derived",))
            self.assertEqual(source_snapshot(db), before)
            db.execute("UPDATE pages SET id='changed-address'")
            self.assertNotEqual(source_snapshot(db), before)


if __name__ == "__main__":
    unittest.main()
