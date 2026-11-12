"""Failure exports preserve bounded audit evidence, never source text or calls."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import export_interrupted_validation as exporter


def jsonl(rows):
    return b"".join((json.dumps(row) + "\n").encode() for row in rows)


class InterruptedValidationExportTests(unittest.TestCase):
    def test_complete_prefix_and_unknown_tail_keep_usage_without_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, trace, proof = root / "prepared.json", root / "run.jsonl", root / "proof.json"
            secret = "SECRET_TOKEN_NEVER_PUBLISH"
            prepared.write_text(json.dumps({"queries": [
                {"id": "q1", "query": "PRIVATE_QUESTION", "answers": ["PRIVATE_GOLD"]}, {"id": "q2"}]}))
            rows = [
                {"kind": "run_metadata", "prompt": "PRIVATE_PROMPT"},
                {"kind": "request_started", "engine": "candidate_native_token_budget", "id": "q1",
                 "repetition": 0, "request_sha256": "a" * 64, "context": "PRIVATE_CONTEXT"},
                {"kind": "request_finished", "engine": "candidate_native_token_budget", "id": "q1",
                 "repetition": 0, "request_sha256": "a" * 64, "response_sha256": "b" * 64,
                 "status": "ok", "answer": "PRIVATE_ANSWER", "served_model": secret,
                 "provider_usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13,
                                    "debug": secret}, "endpoint_roundtrip_ms": 17.5},
                {"kind": "request_started", "engine": "candidate_native_token_budget", "id": "q2",
                 "repetition": 0, "request_sha256": "c" * 64}]
            tail = ('{"partial":"' + secret).encode()
            raw = jsonl(rows) + tail
            trace.write_bytes(raw)
            proof.write_text(json.dumps({"identity": {"runtime": {"argv": [secret], "model_sha256": "d" * 64}},
                                         "runs": [{"status": "running", "pid": 12, "error": secret}]}))
            result = exporter.answer_diagnostic(trace, proof, prepared, (secret,))
            published = json.dumps(result)
            for private in (secret, "PRIVATE_QUESTION", "PRIVATE_GOLD", "PRIVATE_PROMPT",
                            "PRIVATE_CONTEXT", "PRIVATE_ANSWER"):
                self.assertNotIn(private, published)
            self.assertEqual(result["source"]["damaged_tail"]["sha256"], hashlib.sha256(tail).hexdigest())
            self.assertEqual(result["accounting"]["observed_unique_intents"], 2)
            self.assertEqual(result["accounting"]["observed_unique_finished_records"], 1)
            self.assertEqual(result["accounting"]["unresolved_intents"], 1)
            self.assertEqual(result["accounting"]["usage"]["total_tokens"]["known_subtotal"], 13)
            self.assertIsNone(result["accounting"]["usage"]["total_tokens"]["total_if_complete"])
            self.assertTrue(result["accounting"]["has_unknown_outcomes"])
            self.assertEqual([r.get("query_id") for r in result["records"][1:]], ["q1", "q1", "q2"])
            self.assertEqual(trace.read_bytes(), raw)
            self.assertFalse(result["sufficient_for_resume"])
            self.assertEqual(result["model_calls_made_by_exporter"], 0)

    def test_forged_identifiers_and_structured_status_are_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace, prepared = root / "run.jsonl", root / "prepared.json"
            secret = "looks-like-an-identifier"
            prepared.write_text(json.dumps({"queries": [{"id": secret}, {"id": "q1"}]}))
            trace.write_bytes(jsonl([
                {"kind": "run_metadata"},
                {"kind": "request_started", "engine": secret, "id": secret, "repetition": 0},
                {"kind": "request_finished", "engine": secret, "id": secret,
                 "repetition": 0, "status": {"error": secret}, "provider_usage": {"total_tokens": True}},
                {"kind": {"bad": secret}}]))
            result = exporter.answer_diagnostic(trace, prepared_path=prepared, secrets=(secret,))
            self.assertNotIn(secret, json.dumps(result))
            self.assertIsNone(result["records"][1]["engine"])
            self.assertIsNone(result["records"][1]["query_id"])
            self.assertEqual(result["records"][2]["status"], "unrecognized")
            self.assertEqual(result["accounting"]["unrecognized_records"], 1)
            self.assertTrue(result["accounting"]["has_unknown_outcomes"])

    def test_corrupt_middle_line_does_not_silently_accept_later_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            prefix = jsonl([{"kind": "run_metadata"}])
            tail = b"invalid JSON\n" + jsonl([{"kind": "request_finished", "status": "ok"}])
            path.write_bytes(prefix + tail)
            rows, source = exporter.read_jsonl(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(source["damaged_tail"]["offset"], len(prefix))
            self.assertEqual(source["damaged_tail"]["sha256"], hashlib.sha256(tail).hexdigest())
            self.assertTrue(source["unknown_content"])

    def test_workflow_checkpoint_keeps_ambiguity_and_model_usage_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint, trace, verification, ids = [root / name for name in
                                                    ("checkpoint.json", "model.jsonl", "verify.jsonl", "ids.json")]
            secret = "NEVER_PUBLISH_WORKFLOW_SECRET"
            ids.write_text(json.dumps({"answers": {"q1": [secret]}}))
            checkpoint.write_text(json.dumps({
                "stages": {"native-consolidate:private-session": {
                    "status": "error", "elapsed_ms": 25, "error_message": secret, "result": {"source": secret}}},
                "answers": {"book:q1": {"engine": "book", "id": "q1", "status": "interrupted",
                                        "question": secret, "context": secret, "answer": secret}},
                "model_server_runs": [{"model_sha256": "a" * 64, "argv": [secret], "runtime_unchanged": False}]}))
            attempt = "12345678-1234-1234-1234-123456789abc"
            trace.write_bytes(jsonl([
                {"event": "started", "attempt": attempt, "request_sha256": "b" * 64, "request": secret},
                {"event": "completed", "attempt": attempt, "http_status": 503, "response": secret,
                 "response_sha256": "c" * 64, "usage": {"prompt_tokens": 8, "total_tokens": 8},
                 "elapsed_ms": 30}]))
            verification.write_bytes(jsonl([{"runtime_unchanged": False, "argv": [secret]}]) + b"broken")
            result = exporter.workflow_diagnostic(checkpoint, trace, verification, ids, (secret,))
            serialized = json.dumps(result)
            self.assertNotIn(secret, serialized)
            self.assertNotIn("private-session", serialized)
            self.assertEqual(result["accounting"]["ambiguous_answer_records"], 1)
            self.assertEqual(result["accounting"]["observed_native_model_intents"], 1)
            self.assertEqual(result["model_attempts"][1]["usage"]["total_tokens"], 8)
            self.assertEqual(result["model_attempts"][1]["attempt_id"], attempt)
            self.assertEqual(result["stages"][0]["elapsed_ms"], 25)
            self.assertTrue(result["model_verification_source"]["unknown_content"])
            self.assertTrue(result["accounting"]["has_unknown_outcomes"])

    def test_missing_sources_are_unknown_and_do_not_prevent_cleanup_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = exporter.answer_diagnostic(root / "missing.jsonl")
            self.assertEqual(result["source"]["status"], "unavailable")
            self.assertTrue(result["accounting"]["has_unknown_outcomes"])
            output = root / "public.json"
            args = ["--kind", "answers", "--input", str(root / "missing.jsonl"), "--output", str(output)]
            with patch("builtins.print"):
                self.assertEqual(exporter.main(args), 0)
            self.assertEqual(json.loads(output.read_text())["status"], "partial_diagnostic_not_completion")
            with self.assertRaises(FileExistsError), patch("builtins.print"):
                exporter.main(args)

    def test_duplicate_intents_and_mismatched_outcomes_stay_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "run.jsonl"
            intent = {"kind": "request_started", "engine": "book", "id": "q1",
                      "repetition": 0, "request_sha256": "a" * 64}
            trace.write_bytes(jsonl([{"kind": "run_metadata"}, intent, intent, {
                **intent, "kind": "request_finished", "status": "ok", "request_sha256": "b" * 64,
                "provider_usage": {"total_tokens": 99}}]))
            result = exporter.answer_diagnostic(trace)
            self.assertEqual(result["accounting"]["duplicate_records"]["started"], 1)
            self.assertEqual(result["accounting"]["mismatched_request_hashes"], 1)
            self.assertEqual(result["accounting"]["usage"]["total_tokens"]["known_subtotal"], 0)
            self.assertTrue(result["accounting"]["has_unknown_outcomes"])

    def test_unbounded_and_nonfinite_numbers_are_not_published_as_usage(self):
        self.assertIsNone(exporter.integer(True))
        self.assertIsNone(exporter.number(2 ** 10000))
        self.assertIsNone(exporter.number(float("inf")))
        self.assertIsNone(exporter.number(float("nan")))
        self.assertEqual(exporter.usage({"total_tokens": 0})["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
