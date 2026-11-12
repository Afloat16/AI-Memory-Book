"""Interruption recovery must never replay an uncertain model request."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks import answer_eval as evaluation
from tests.test_answer_eval import ROOT, cases


@unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Optional tokenizer")
class AnswerResumeTests(unittest.TestCase):
    def prepare(self, directory):
        source = directory / "cases.json"
        evaluation.save_new(source, cases())
        prepared = directory / "prepared.json"
        evaluation.prepare(SimpleNamespace(cases=source, source=[f"base={ROOT / 'src'}", f"new={ROOT / 'src'}"],
            cohort_label="transport fixture only", output=prepared, tokenizer="cl100k_base",
            budget_chars=2000, budget_tokens=512, limit=5))
        return SimpleNamespace(base_url="http://127.0.0.1:1234/v1", model="transport-fixture",
            api_key_env=None, prepared=prepared, output=directory / "run", output_token_field="max_tokens",
            max_output_tokens=32, omit_temperature=False, temperature=0.0, repeats=1, timeout=5)

    def response(self, *args):
        return {"status": "ok", "answer": "45 seconds", "finish_reason": "stop",
                "served_model": "transport-fixture", "system_fingerprint": "fixture",
                "provider_usage": evaluation.provider_usage({"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}),
                "response_sha256": "fixture-response", "endpoint_roundtrip_ms": 1.0}

    def test_unknown_intent_is_not_retried_and_completed_results_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.prepare(Path(temporary))
            with patch.object(evaluation, "call_endpoint", side_effect=[self.response(), KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    evaluation.run(args)
            trace = Path(str(args.output) + ".jsonl")
            original = trace.read_bytes()
            args.resume = True
            with patch.object(evaluation, "call_endpoint", side_effect=self.response) as call:
                summary = evaluation.run(args)
            self.assertEqual(call.call_count, 2)
            self.assertTrue(trace.read_bytes().startswith(original))
            self.assertEqual(sum(e["attempts"] for e in summary["engines"]), 4)
            self.assertEqual(sum(e["interrupted_unknown_outcomes"] for e in summary["engines"]), 1)
            affected = next(e for e in summary["engines"] if e["interrupted_unknown_outcomes"])
            self.assertIsNone(affected["provider_usage"]["total_tokens"]["total_if_complete"])
            self.assertEqual(affected["answerable_normalized_exact_match"], 0.0)
            ledger = [json.loads(line) for line in trace.read_bytes().splitlines()]
            self.assertEqual(sum(row["kind"] == "request_started" for row in ledger), 4)
            with patch.object(evaluation, "call_endpoint") as call:
                with self.assertRaisesRegex(ValueError, "already exists"):
                    evaluation.run(args)
                call.assert_not_called()

    def test_changed_model_or_partial_ledger_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.prepare(Path(temporary))
            with patch.object(evaluation, "call_endpoint", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    evaluation.run(args)
            trace = Path(str(args.output) + ".jsonl")
            original = trace.read_bytes()
            args.resume, args.model = True, "another-model"
            with patch.object(evaluation, "call_endpoint") as call:
                with self.assertRaisesRegex(ValueError, "identity differs"):
                    evaluation.run(args)
                call.assert_not_called()
            self.assertEqual(trace.read_bytes(), original)
            args.model = "transport-fixture"
            trace.write_bytes(original + b'{"partial":')
            with patch.object(evaluation, "call_endpoint") as call:
                with self.assertRaisesRegex(ValueError, "partial final line"):
                    evaluation.run(args)
                call.assert_not_called()
            self.assertEqual(trace.read_bytes(), original + b'{"partial":')

    def test_second_runner_is_rejected_before_sending_a_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.prepare(Path(temporary))
            with evaluation._lock(Path(str(args.output) + ".jsonl")):
                with patch.object(evaluation, "call_endpoint") as call:
                    with self.assertRaisesRegex(RuntimeError, "active runner"):
                        evaluation.run(args)
                    call.assert_not_called()

    def test_wrong_served_model_keeps_costs_but_receives_no_quality_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.prepare(Path(temporary))
            wrong = {**self.response(), "served_model": "different-weights"}
            with patch.object(evaluation, "call_endpoint", return_value=wrong) as call:
                summary = evaluation.run(args)
            self.assertEqual(call.call_count, 4)
            self.assertEqual(sum(e["errors"] for e in summary["engines"]), 4)
            self.assertEqual(sum(e["provider_usage"]["total_tokens"]["known_subtotal"]
                                 for e in summary["engines"]), 52)
            for engine in summary["engines"]:
                self.assertEqual(engine["answerable_normalized_exact_match"], 0)
            rows = [json.loads(line) for line in Path(str(args.output) + ".jsonl").read_bytes().splitlines()]
            outcomes = [row for row in rows if row["kind"] == "request_finished"]
            self.assertTrue(all(row["error_type"] == "ModelIdentityMismatch" for row in outcomes))
            self.assertTrue(all(row["response_sha256"] == "fixture-response" for row in outcomes))

    def test_ledger_rejects_wrong_model_disguised_as_a_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = self.prepare(Path(temporary))
            with patch.object(evaluation, "call_endpoint", side_effect=[self.response(), KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    evaluation.run(args)
            trace = Path(str(args.output) + ".jsonl")
            rows = [json.loads(line) for line in trace.read_bytes().splitlines()]
            rows[2]["served_model"] = "another-model"
            trace.write_bytes(b"".join(evaluation.json_bytes(row) + b"\n" for row in rows))
            args.resume = True
            with patch.object(evaluation, "call_endpoint") as call:
                with self.assertRaisesRegex(ValueError, "different or unreported model"):
                    evaluation.run(args)
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
