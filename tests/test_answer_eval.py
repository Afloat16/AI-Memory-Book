"""Answer-evaluation plumbing tests; fixture replies are not model-quality data."""

from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks import answer_eval as evaluation


ROOT = Path(__file__).resolve().parents[1]


def cases():
    return {"sessions": [{"project": "fixture", "session_id": "decision",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": "What is the cache TTL?"},
                         {"role": "assistant", "content": "The cache TTL is 45 seconds."}]}],
            "queries": [
                {"id": "ttl", "query": "What is the cache TTL?", "project": "fixture",
                 "answerable": True, "answers": ["45 seconds", "GOLD_ONLY_NEVER_IN_PROMPT"]},
                {"id": "unsupported", "query": "Who owns the cache?", "project": "fixture",
                 "answerable": False, "answers": []}]}


class AnswerMetricTests(unittest.TestCase):
    def test_lexical_metrics_and_explicit_abstention(self):
        case = {"answerable": True, "answers": ["45 seconds", "45秒"]}
        self.assertEqual(evaluation.answer_scores("45 秒。", case)["normalized_exact_match"], 1.0)
        self.assertEqual(evaluation.answer_scores("45 seconds, please", case)["lexical_token_f1"], .8)
        unsupported = {"answerable": False, "answers": []}
        self.assertTrue(evaluation.answer_scores(evaluation.ABSTAIN, unsupported)["abstained"])
        self.assertFalse(evaluation.answer_scores("I don't know", unsupported)["abstained"])
        self.assertIsNone(evaluation.answer_scores(evaluation.ABSTAIN, unsupported)["lexical_token_f1"])

    def test_cases_require_unique_ids_and_explicit_answerability(self):
        for mutation in (lambda data: data["queries"].append(data["queries"][0]),
                         lambda data: data["queries"][0].pop("answerable"),
                         lambda data: data["queries"][1].update(answers=["fabricated"]),
                         lambda data: data["sessions"].append(data["sessions"][0])):
            data = cases()
            mutation(data)
            with self.assertRaises(ValueError):
                evaluation.validated_cases(data)

    def test_usage_is_unknown_without_provider_counts(self):
        for value in (None, {}, {"prompt_tokens": True, "completion_tokens": -1}):
            usage = evaluation.provider_usage(value)
            self.assertIsNone(usage["prompt_tokens"])
            self.assertIsNone(usage["completion_tokens"])
            self.assertFalse(usage["fully_reported"])
        self.assertEqual(evaluation.provider_usage({"prompt_tokens": 0})["prompt_tokens"], 0)

    def test_endpoint_requires_explicit_credential_free_location(self):
        for url in ("", "ftp://example.test/v1", "https://user:secret@example.test/v1",
                    "https://example.test/v1?key=secret", "http://example.test/v1"):
            with self.assertRaises(ValueError):
                evaluation.completion_url(url)
        self.assertEqual(evaluation.completion_url("http://127.0.0.1:1234/v1/"),
                         "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(evaluation.completion_url("https://example.test/v1"),
                         "https://example.test/v1/chat/completions")

    def test_failed_attempts_remain_in_metrics_and_partial_usage_is_not_a_total(self):
        engine = {"label": "one", "ingestion_events": [{"elapsed_ms": 1.0}],
                  "rows": [{"recall_ms": 2.0, "packing_ms": .1}]}
        prepared = {"queries": [{"id": "q", "answerable": True}], "engines": [engine]}
        success = {"engine": "one", "id": "q", "status": "ok", "endpoint_roundtrip_ms": 3,
                   "scores": {"normalized_exact_match": 1, "lexical_token_f1": 1, "abstained": False},
                   "provider_usage": evaluation.provider_usage({"prompt_tokens": 7,
                                                                "completion_tokens": 2, "total_tokens": 9})}
        failure = {**success, "status": "error", "provider_usage": evaluation.provider_usage(None),
                   "scores": {"normalized_exact_match": 0, "lexical_token_f1": 0, "abstained": False}}
        result = evaluation.summarize(prepared, [success, failure])["engines"][0]
        self.assertEqual(result["answerable_normalized_exact_match"], .5)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["answerable_attempts"], 2)
        self.assertEqual(result["unique_answerable_queries"], 1)
        self.assertIsNone(result["provider_usage"]["total_tokens"]["total_if_complete"])
        self.assertEqual(result["provider_usage"]["total_tokens"]["known_subtotal"], 9)
        self.assertIsNone(result["full_workflow_cost"])

    def test_pair_flags_changing_or_unreported_model_identity(self):
        prepared = {"queries": [{"id": "q", "answerable": True}], "engines": []}
        stable = {"status": "ok", "served_model": "served-alias-target", "system_fingerprint": "weights-a"}
        for rows, status in (([stable, stable], "same_reported_identity"),
                             ([stable, {**stable, "served_model": "different"}], "incomparable"),
                             ([stable, {**stable, "system_fingerprint": "weights-b"}], "incomparable"),
                             ([stable, {**stable, "served_model": None}], "unverified"),
                             ([stable, {**stable, "system_fingerprint": None}], "unverified")):
            self.assertEqual(evaluation.summarize(prepared, rows)["model_comparability"]["status"], status)


class EndpointTransportTests(unittest.TestCase):
    def server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/v1"

    def test_redirect_does_not_forward_credentials_or_retry(self):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed.append(self.path)
                self.send_response(307)
                self.send_header("Location", "/credential-sink")
                self.end_headers()

            def log_message(self, *args):
                pass

        result = evaluation.call_endpoint(evaluation.completion_url(self.server(Handler)),
                                          {"model": "transport-fixture"}, "test-secret", 5)
        self.assertEqual(observed, ["/v1/chat/completions"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 307)
        self.assertNotIn("test-secret", json.dumps(result))

    def test_successful_endpoint_credential_echo_is_discarded_before_trace(self):
        secret = "fixture-api-key-must-never-be-saved"

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                reply = {"model": "model-" + secret, "choices": [
                    {"message": {"content": "Answer echo: " + secret}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12,
                              "debug": {"Authorization": "Bearer " + secret}},
                    "debug": {"request_headers": {"Authorization": "Bearer " + secret}}}
                encoded = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):
                pass

        result = evaluation.call_endpoint(evaluation.completion_url(self.server(Handler)),
                                          {"model": "transport-fixture"}, secret, 5)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_reason"], "credential_echo_in_response")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["provider_usage"]["total_tokens"], 12)
        self.assertIsNotNone(result["response_sha256"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("debug", json.dumps(result))

    def test_truncated_chunked_response_is_a_recorded_error_without_retry(self):
        attempts = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                attempts.append(1)
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b'20\r\n{"choices":[')
                self.close_connection = True

            def log_message(self, *args):
                pass

        result = evaluation.call_endpoint(evaluation.completion_url(self.server(Handler)),
                                          {"model": "transport-fixture"}, None, 5)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "IncompleteRead")
        self.assertIsNone(result["provider_usage"]["total_tokens"])
        self.assertEqual(len(attempts), 1)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Optional tiktoken benchmark dependency")
    def test_prepared_pair_and_http_fixture_keep_errors_labels_and_unknown_costs_separate(self):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                observed.append(body)
                if len(observed) == 2:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"server detail deliberately omitted from logs")
                    return
                reply = {"model": "transport-test-fixture", "choices": [
                    {"message": {"content": "45 seconds"}, "finish_reason": "stop"}]}
                # Deliberately absent usage must stay absent in the ledger.
                encoded = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):
                pass

        base_url = self.server(Handler)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            case_path, prepared_path = directory / "cases.json", directory / "prepared.json"
            evaluation.save_new(case_path, cases())
            prep_args = SimpleNamespace(cases=case_path, source=[f"base={ROOT / 'src'}", f"candidate={ROOT / 'src'}"],
                cohort_label="protocol fixture only", output=prepared_path, tokenizer="cl100k_base",
                budget_chars=2000, budget_tokens=512, limit=5)
            prepared = evaluation.prepare(prep_args)
            for engine in prepared["engines"]:
                self.assertTrue(all("GOLD_ONLY_NEVER_IN_PROMPT" not in row["context"] for row in engine["rows"]))
            args = SimpleNamespace(base_url=base_url, model="transport-test-fixture", api_key_env="ANSWER_TEST_KEY",
                prepared=prepared_path, output=directory / "run", output_token_field="max_completion_tokens",
                max_output_tokens=32, omit_temperature=False, temperature=0.0, repeats=1, timeout=5)
            with patch.dict(os.environ, {"ANSWER_TEST_KEY": "transport-fixture-secret"}):
                summary = evaluation.run(args)
            self.assertEqual(len(observed), 4)  # No retries after HTTP 500.
            self.assertNotIn("GOLD_ONLY_NEVER_IN_PROMPT", json.dumps(observed))
            self.assertEqual(sum(e["errors"] for e in summary["engines"]), 1)
            self.assertFalse(summary["full_workflow_measured"])
            for engine in summary["engines"]:
                self.assertIsNone(engine["provider_usage"]["total_tokens"]["total_if_complete"])
            trace_path = directory / "run.jsonl"
            trace = trace_path.read_text()
            self.assertNotIn("transport-fixture-secret", trace)
            self.assertEqual(trace.count('"kind":"request_started"'), 4)
            self.assertEqual(trace.count('"kind":"request_finished"'), 4)
            if os.name == "posix":
                self.assertEqual(trace_path.stat().st_mode & 0o777, 0o600)
            # Changes to source contexts or QA labels are rejected before HTTP.
            counter = evaluation.TokenCounter("cl100k_base")
            changed = copy.deepcopy(prepared)
            changed["queries"][0]["answers"] = ["changed"]
            with self.assertRaises(ValueError):
                evaluation.validate_prepared(changed, counter)
            changed = copy.deepcopy(prepared)
            changed["engines"][0]["rows"][0]["context"] += " changed"
            with self.assertRaises(ValueError):
                evaluation.validate_prepared(changed, counter)
            with patch.object(evaluation, "evaluator_sources", return_value={}):
                with self.assertRaises(ValueError):
                    evaluation.validate_prepared(prepared, counter)
            args.api_key_env = None
            with self.assertRaises(ValueError):
                evaluation.run(args)
            self.assertEqual(len(observed), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
