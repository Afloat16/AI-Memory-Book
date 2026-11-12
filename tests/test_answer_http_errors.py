"""Failed endpoint calls retain reported usage without exporting error text."""

import hashlib
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from benchmarks import answer_eval


class AnswerHTTPErrorTests(unittest.TestCase):
    def call_error(self, raw, key=None):
        error = HTTPError("https://fixture.invalid/v1/chat/completions", 503,
                          "fixture error", {}, BytesIO(raw))
        with patch.object(answer_eval.request, "build_opener") as build:
            build.return_value.open.side_effect = error
            return answer_eval.call_endpoint(error.url, {"model": "fixture"}, key, 1)

    def test_reported_usage_on_http_error_remains_counted_but_unscored(self):
        raw = json.dumps({"error": {"message": "private server detail"},
                          "usage": {"prompt_tokens": 19, "completion_tokens": 4,
                                    "total_tokens": 23}}).encode()
        result = self.call_error(raw)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 503)
        self.assertIsNone(result["answer"])
        self.assertEqual(result["provider_usage"]["total_tokens"], 23)
        self.assertTrue(result["provider_usage"]["fully_reported"])
        self.assertEqual(result["response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("private server detail", json.dumps(result))

    def test_credential_echo_on_failed_response_never_enters_the_ledger(self):
        secret = "fixture-credential"
        raw = json.dumps({"error": secret, "usage": {"prompt_tokens": 9}}).encode()
        result = self.call_error(raw, secret)
        self.assertEqual(result["provider_usage"]["prompt_tokens"], 9)
        self.assertEqual(result["error_reason"], "credential_echo_in_response")
        self.assertNotIn(secret, json.dumps(result))
        self.assertIsNone(result["provider_usage"]["total_tokens"])

    def test_invalid_or_oversized_failure_body_keeps_cost_unknown(self):
        invalid = self.call_error(b"not JSON")
        self.assertFalse(invalid["provider_usage"]["fully_reported"])
        with patch.object(answer_eval, "MAX_RESPONSE_BYTES", 8):
            oversized = self.call_error(b'{"usage":{"prompt_tokens":99}}')
        self.assertTrue(oversized["response_body_truncated"])
        self.assertIsNone(oversized["provider_usage"]["prompt_tokens"])


if __name__ == "__main__":
    unittest.main()
