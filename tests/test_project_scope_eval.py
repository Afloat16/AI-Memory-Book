"""Guard the development diagnostic against false source/scope success."""
import copy
import tempfile
from pathlib import Path
import unittest

from benchmarks import project_scope_eval as evaluation
from memory_book import MemoryBook


class ProjectScopeEvaluationTests(unittest.TestCase):
    def test_unsupported_or_wrong_exception_does_not_fake_scope_rejection(self):
        error = {"type": "TypeError", "message": "unexpected project keyword"}
        self.assertEqual(evaluation.classify_outcome("KeyError", None, error, False, None)[0], "unsupported")
        self.assertEqual(evaluation.classify_outcome("KeyError", None, error, True, None)[0], "failed")
        self.assertEqual(evaluation.classify_outcome("KeyError", {"content": "foreign"}, None, True, None)[0], "failed")
        self.assertEqual(evaluation.classify_outcome("KeyError", None, {"type": "KeyError"}, True, None)[0], "passed")

    def test_source_audit_rejects_foreign_refs_and_fabricated_page_text(self):
        source = evaluation.workload()["sessions"][0]
        sources = {(source["project"], source["session_id"], 0): evaluation.original_turn(source)}
        with MemoryBook(":memory:") as book:
            book.ingest(source)
            recall = book.recall("retry_limit", project=source["project"])
            self.assertEqual(evaluation.recall_errors(recall, source["project"], sources, "retry_limit=11."), [])
            bad = copy.deepcopy(recall)
            bad["results"][0]["source_refs"][0]["project"] = "similar/alpha-copy"
            self.assertTrue(evaluation.recall_errors(bad, source["project"], sources))
            page = book.read(recall["results"][0]["id"], offset=13, limit=47)
            self.assertEqual(evaluation.page_errors(page, source["project"], sources), [])
            page["content"] = "X" + page["content"][1:]
            self.assertTrue(evaluation.page_errors(page, source["project"], sources))

    def test_comparison_preserves_source_time_and_detects_omitted_case(self):
        original = {"context": "raw evidence", "created_at": "source-time", "latency_ms": 1,
                    "cache_hit": False, "source_refs": [{"project": "alpha", "turn_start": 1, "turn_end": 4}]}
        changed = copy.deepcopy(original)
        changed.update(latency_ms=9, cache_hit=True)
        self.assertEqual(evaluation.canonical_response(original), evaluation.canonical_response(changed))
        changed["created_at"] = "different-source-time"
        self.assertNotEqual(evaluation.canonical_response(original), evaluation.canonical_response(changed))
        report = {"version": "v", "dataset_sha256": "d", "evaluator_sha256": "e", "canonicalization": {},
                  "compatibility_cases": {"existing": {"response_sha256": "one", "error": None, "outcome": "passed"}},
                  "runtime": {"sha256": "r"}, "outcomes": {"passed": 1}}
        other = copy.deepcopy(report)
        other["compatibility_cases"] = {}
        result = evaluation.compare_reports(report, other)
        self.assertEqual(result["equal_cases"], 0)
        self.assertEqual(result["differences"][0]["case_id"], "existing")

    def test_directory_completeness_detects_a_missing_page_without_directory_counts(self):
        source = evaluation.workload()["sessions"][-1]
        sources = {(source["project"], source["session_id"], 0): evaluation.original_turn(source)}
        with MemoryBook(":memory:") as book:
            result = book.ingest(source)
            chapter = book.chapter(result["chapter_id"])
            pages = [book.read(page["id"]) for section in chapter["sections"] for page in section["pages"]]
            self.assertGreater(len(pages), 1)
            self.assertEqual(evaluation.directory_source_errors(source["project"], pages, sources), [])
            self.assertTrue(evaluation.directory_source_errors(source["project"], pages[:-1], sources))

    def test_run_refuses_to_overwrite_retained_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = output / "raw.jsonl"
            evidence.write_text("retained\n")
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                evaluation.run(output)
            self.assertEqual(evidence.read_text(), "retained\n")


if __name__ == "__main__":
    unittest.main()
