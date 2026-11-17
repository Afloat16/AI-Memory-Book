import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.native_budget_eval import (archive_existing_outputs, block_ids,
    dataset_for, paired_changes, source_errors, validation)


class NativeBudgetEvaluationTests(unittest.TestCase):
    def test_wrong_frozen_dataset_stops_before_engine_work(self):
        args = SimpleNamespace(corpus="synthetic", seed=61, split="development", projects=8,
            locomo_path=None, max_queries=0, expected_queries=1, expected_dataset_sha256="expected")
        dataset = SimpleNamespace(queries=[SimpleNamespace(id="one")], fingerprint="different")
        with patch("benchmarks.native_budget_eval.load_dataset", return_value=dataset):
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                dataset_for(args)

    def test_explicit_rerun_retains_previous_partial_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "attempt"
            partial = Path(str(prefix) + ".summary.json")
            partial.write_bytes(b'{"incomplete": true}')
            with self.assertRaises(ValueError):
                archive_existing_outputs(prefix)
            self.assertTrue(partial.is_file())
            archive = archive_existing_outputs(prefix, enabled=True)
            self.assertFalse(partial.exists())
            self.assertEqual((Path(archive["directory"]) / partial.name).read_bytes(),
                             b'{"incomplete": true}')
            self.assertIsNone(archive_existing_outputs(prefix))

    def response(self):
        return {"context": "[p] project\nThe cache expires after 45 seconds.",
                "results": [{"id": "p", "text": "The cache expires after 45 seconds.",
                    "breadcrumb": [{"id": "project"}], "source_refs": [{"project": "project",
                    "session_id": "session", "turn_index": 0, "turn_start": 0, "turn_end": 35}]}]}

    def test_preservation_requires_same_text_citation_and_source_coordinates(self):
        first = self.response()
        altered = copy.deepcopy(first)
        altered["results"][0]["source_refs"][0]["session_id"] = "wrong"
        self.assertNotEqual(block_ids(first), block_ids(altered))
        altered = copy.deepcopy(first)
        altered["context"] = altered["context"].replace("[p]", "[q]")
        self.assertNotEqual(block_ids(first), block_ids(altered))

    def test_invalid_source_span_is_detected_even_if_words_match(self):
        response = self.response()
        text = response["results"][0]["text"]
        response["results"][0]["source_refs"][0]["turn_end"] = len(text)
        sources = {("project", "session", 0): text}
        self.assertEqual(source_errors(response, sources), 0)
        response["results"][0]["source_refs"][0]["turn_end"] += 1
        self.assertEqual(source_errors(response, sources), 1)

    def test_quality_gains_cannot_hide_lost_baseline_blocks(self):
        old = {"id": "q", "evidence_ranks": [1, None], "complete": False, "block_hashes": ["old"]}
        new = {"id": "q", "evidence_ranks": [1, 2], "complete": True, "block_hashes": ["replacement"]}
        common = {"budget_chars": 2000, "tokenizer": "cl100k_base", "budget_tokens": 512}
        baseline = {"configurations": [{**common, "policy": "native_excerpt_pack", "query_results": [old]}]}
        candidate = {"configurations": [{**common, "policy": "native_token_budget", "query_results": [new]}]}
        changes = paired_changes(baseline, candidate)
        self.assertEqual(len(changes[0]["annotation_gains"]), 1)
        self.assertEqual(changes[0]["complete_question_gains"], ["q"])
        self.assertEqual(changes[0]["baseline_block_losses"][0]["id"], "q")
        engine = {"label": "test", "source_unchanged": True, "evaluator_unchanged": True,
                  "evaluator_files": {}, "configurations": []}
        self.assertFalse(validation([engine], changes)["passed"])
        # Different semantic ranking is still reported, but does not promise
        # the lexical packer's exact block set.
        self.assertTrue(validation([engine], changes, require_preservation=False)["passed"])
