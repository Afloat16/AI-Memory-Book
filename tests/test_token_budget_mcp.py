from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from memory_book.store import MemoryBook
from tests.test_token_budget import sample


@unittest.skipUnless(importlib.util.find_spec("mcp") and importlib.util.find_spec("tiktoken"),
                     "Install .[mcp,tokens] for real MCP token-budget checks")
class TokenBudgetMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_strict_integer_and_compact_detailed_budget_parity(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from memory_book.token_budget import TokenCounter

        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "memory.db")
            with MemoryBook(database) as book:
                book.ingest(sample())
            parameters = StdioServerParameters(command=sys.executable,
                args=["-c", "import sys; from memory_book.mcp_server import serve; serve(sys.argv[1])", database],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONUNBUFFERED": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                    await client.initialize()
                    listing = await client.list_tools()
                    tool = next(t for t in listing.tools if t.name == "recall_memory")
                    kinds = {entry["type"] for entry in tool.inputSchema["properties"]["budget_tokens"]["anyOf"]}
                    self.assertEqual(kinds, {"integer", "null"})
                    for invalid in (True, False, "96", 96.0, -1, 100001):
                        result = await client.call_tool("recall_memory", {"query": "pressure", "budget_tokens": invalid})
                        self.assertTrue(result.isError, (invalid, result))
                    decoded = []
                    for details in (False, True):
                        result = await client.call_tool("recall_memory", {
                            "query": "pressure", "project": "lab", "budget_chars": 1000,
                            "budget_tokens": 96, "tokenizer": "cl100k_base", "details": details})
                        self.assertFalse(result.isError, result)
                        body = json.loads("\n".join(c.text for c in result.content if c.type == "text"))
                        self.assertEqual(body["context_tokens"], TokenCounter("cl100k_base").count(body["context"]))
                        self.assertLessEqual(body["context_tokens"], 96)
                        self.assertLessEqual(body["context_chars"], 1000)
                        decoded.append(body)
                    self.assertEqual(decoded[0]["context"], decoded[1]["context"])
                    self.assertEqual(decoded[0]["context_tokens"], decoded[1]["context_tokens"])
                    legacy = await client.call_tool("recall_memory", {"query": "pressure"})
                    body = json.loads(legacy.content[0].text)
                    self.assertNotIn("context_tokens", body)


if __name__ == "__main__":
    unittest.main()
