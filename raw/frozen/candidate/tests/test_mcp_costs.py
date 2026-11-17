"""Retain duplicate annotations without measuring cached calls as first calls."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.data import Dataset, QueryCase
from benchmarks.mcp_costs import measure

try:
    from mcp import ClientSession
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class CharacterEncoder:
    """Only exercise the lifecycle here; real benchmarks still use tiktoken."""

    @staticmethod
    def encode(text):
        return tuple(text)


@unittest.skipUnless(HAS_MCP, "Install .[mcp] to run the real stdio cost-runner regression")
class MCPCostTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_pairs_retain_all_ids_with_uncached_first_calls_and_hot_repeats(self):
        dataset = Dataset(seed=61, split="development", sessions=[
            {"project": "payments", "session_id": "payments-session", "title": "Payment policies",
             "messages": [{"role": "user", "content": "What callback retry delay and release health check did we choose?"},
                          {"role": "assistant", "content": "The callback retry delay is 45 seconds. The release rollback health check is /health/live."}]},
            {"project": "shipping", "session_id": "shipping-session", "title": "Shipping policy",
             "messages": [{"role": "user", "content": "What callback retry delay did we choose?"},
                          {"role": "assistant", "content": "The callback retry delay is 99 seconds."}]},
        ], queries=[
            QueryCase("annotation-1", "callback retry delay", "lookup", "payments"),
            QueryCase("annotation-2", "callback retry delay", "lookup", "payments"),
            QueryCase("different-project", "callback retry delay", "lookup", "shipping"),
            QueryCase("different-question", "release rollback health", "lookup", "payments"),
        ])
        original_call = ClientSession.call_tool
        observed = []

        async def call_with_cache_diagnostics(client, name, arguments=None, *args, **kwargs):
            # The native details flag exposes the engine's actual cache_hit.
            # It does not alter the recall-cache key. Keep the real SDK,
            # subprocess, SQLite cache and requests; only observe diagnostics
            # that production compact payloads intentionally omit.
            response = await original_call(client, name, {**arguments, "details": True}, *args, **kwargs)
            if not arguments.get("details"):
                body = json.loads("\n".join(part.text for part in response.content if part.type == "text"))
                observed.append(body["cache_hit"])
            return response

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ClientSession, "call_tool", new=call_with_cache_diagnostics):
                result = await measure("fixture", root, dataset, Path(directory),
                                       {"fixture_characters": CharacterEncoder()}, repeats=2, budget=2000)

        self.assertEqual(result["query_pair_counts"], {
            "query_rows": 4, "distinct_query_project_pairs": 3,
            "duplicate_query_project_rows": 1, "duplicate_pair_cache_clears": 2})
        rows = result["rows"]
        self.assertEqual(len(rows), 16)
        self.assertEqual(observed, [False, True] * 8)
        for repetition in range(2):
            for case in dataset.queries:
                pair = [row for row in rows if row["query_id"] == case.id and row["repeat"] == repetition]
                self.assertEqual([row["state"] for row in pair], ["first_call_after_cache_clear", "immediate_repeat"])
                self.assertEqual([row["reported_cache_hit"] for row in pair], [False, True])
                self.assertEqual(pair[0]["context_sha256"], pair[1]["context_sha256"])
                self.assertEqual(pair[0]["page_ids"], pair[1]["page_ids"])
                self.assertFalse(pair[1]["duplicate_pair_cache_clear"])
            clears = [row for row in rows if row["repeat"] == repetition and row["duplicate_pair_cache_clear"]]
            self.assertEqual(len(clears), 1)
            self.assertIn(clears[0]["query_id"], {"annotation-1", "annotation-2"})
        details = result["same_evidence_detail_comparison"]
        self.assertEqual({row["query_id"] for row in details}, {case.id for case in dataset.queries})
        self.assertEqual(len(details), 4)
        self.assertTrue(all(row["context_identical"] for row in details))


if __name__ == "__main__":
    unittest.main()
