"""Protocol tests with invented scores only; never run development benchmarks."""
from argparse import Namespace
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks import round2_quality_eval as evaluation
from benchmarks.data import QueryCase


class Round2QualityEvaluationTests(unittest.TestCase):
    def test_rotation_balances_three_policy_positions(self):
        for position in range(4):
            orders = [evaluation.mode_order(position, repetition) for repetition in range(3)]
            for column in zip(*orders):
                self.assertEqual(set(column), set(evaluation.MODES))

    def test_reference_rejects_a_changed_legacy_function_or_constant(self):
        import inspect
        source = inspect.getsource(evaluation.legacy_rrf).replace("def legacy_rrf(", "def fuse_candidates(")
        baseline = "RRF_K = 60\n" + source
        with patch.object(evaluation.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=baseline)):
            self.assertEqual(evaluation.verify_reference()["rrf_k"], 60)
        for different in (baseline.replace("RRF_K = 60", "RRF_K = 10"), baseline.replace("1 / (RRF_K + rank)", "2 / (RRF_K + rank)")):
            with patch.object(evaluation.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=different)):
                with self.assertRaises(ValueError):
                    evaluation.verify_reference()

    def test_wrong_import_and_unregistered_axes_fail_before_model_use(self):
        with self.assertRaisesRegex(RuntimeError, "requested source"):
            evaluation.require_source(Path("candidate/src"), Path("another/src/memory_book/__init__.py"))
        plan = json.loads(evaluation.PLAN.read_text())
        cohort = plan["development_cohorts"][0]
        args = Namespace(**{key: value for key, value in plan["parameters"].items()
                            if key in ("budget_chars", "token_budgets", "tokenizers", "limit", "repeats")},
                         seed=61, projects=8, max_queries=0, corpus=cohort["corpus"], split="development",
                         expected_queries=cohort["queries"], expected_dataset_sha256=cohort["sha256"])
        evaluation.validate_arguments(args)
        args.repeats = 1
        with self.assertRaisesRegex(ValueError, "axes"):
            evaluation.validate_arguments(args)
        args.repeats = 3
        args.expected_queries = 256
        with self.assertRaisesRegex(ValueError, "old development"):
            evaluation.validate_arguments(args)

    def test_reference_policy_restores_on_failure_and_counts_real_encoding(self):
        import memory_book.semantic as semantic
        encode = lambda query: [[1.0]]
        book = SimpleNamespace(_semantic_model=SimpleNamespace(encode_query=encode))
        original = semantic.fuse_candidates
        with self.assertRaises(RuntimeError):
            with evaluation.fusion_mode(book, evaluation.MODES[1]) as counter:
                self.assertIs(semantic.fuse_candidates, evaluation.legacy_rrf)
                self.assertEqual(book._semantic_model.encode_query("fixture"), [[1.0]])
                self.assertEqual(counter[0], 1)
                raise RuntimeError("fixture")
        self.assertIs(semantic.fuse_candidates, original)
        self.assertIs(book._semantic_model.encode_query, encode)
        with evaluation.fusion_mode(book, evaluation.MODES[2]) as counter:
            self.assertIs(semantic.fuse_candidates, original)
            self.assertEqual(counter[0], 0)

    def test_all_three_modes_are_required_before_a_complete_report(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = evaluation.Progress(Path(directory) / "state.db", {})
            try:
                with self.assertRaisesRegex(ValueError, "three-mode"):
                    evaluation.build_report(progress, SimpleNamespace(queries=[QueryCase("q", "fixture", "fixture", "p")]),
                                            [{"budget_tokens": 512}], Namespace(repeats=3), "", {}, "")
            finally:
                progress.close()

    def test_interruption_export_keeps_metrics_and_unknown_without_source_or_error_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress = evaluation.Progress(root / "progress.sqlite3", {"model": "fixture"})
            complete = progress.start("config", 0, "q", evaluation.MODES[0])
            progress.finish(complete, 1.0, {"id": "q", "complete": True, "context_sha256": "a" * 64,
                                            "query": "PRIVATE QUESTION", "answer": "PRIVATE ANSWER", "context": "PRIVATE SOURCE"})
            pending = progress.start("config", 0, "other", evaluation.MODES[1])
            progress.db.execute("UPDATE samples SET error='PRIVATE EXCEPTION' WHERE seq=?", (pending,))
            progress.db.commit()
            ledger = evaluation.export_checkpoint(root, root / "public", "interrupted")
            self.assertFalse(ledger["complete_comparison"])
            self.assertEqual(ledger["attempt_counts"], {"completed": 1, "interrupted_unknown": 1})
            raw = gzip.decompress((root / "public.attempts.json.gz").read_bytes()).decode()
            self.assertNotIn("PRIVATE", raw)
            metrics = json.loads(raw)["completed_metrics"]
            self.assertTrue(metrics[0]["metrics"]["complete"])
            self.assertEqual(progress.db.execute("SELECT status FROM samples WHERE seq=?", (pending,)).fetchone()[0], "running")
            progress.close()


if __name__ == "__main__":
    unittest.main()
