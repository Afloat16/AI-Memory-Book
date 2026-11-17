"""Opt-in semantic configuration must not change the model-free default."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.cli import main, parser
from memory_book.mcp_server import recall_payload


class SemanticCLITests(unittest.TestCase):
    def test_explicit_model_directory_and_index_command(self):
        args = parser().parse_args(["semantic-index", "--semantic-model-dir", "/models/semantic"])
        self.assertEqual(args.semantic_model_dir, "/models/semantic")
        args = parser().parse_args(["mcp", "--semantic-model-dir", "/models/semantic"])
        self.assertEqual(args.semantic_model_dir, "/models/semantic")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["semantic-index"])

    def test_default_works_without_model_and_opt_in_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            with MemoryBook(database) as book:
                book.ingest({"project": "lab", "session_id": "cache", "messages": [
                    {"role": "user", "content": "Cache expiry is 45 seconds."}]})
            command = ["--db", database, "recall", "cache expiry", "--project", "lab", "--json"]
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(command), 0)
            self.assertIn("45 seconds", json.loads(out.getvalue())["context"])
            self.assertNotIn("semantic", json.loads(out.getvalue()))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(command + ["--semantic"]), 2)
            self.assertIn("semantic_model_dir", err.getvalue())
            self.assertEqual(out.getvalue(), "")

    def test_compact_response_preserves_semantic_provenance(self):
        response = {"context": "", "results": [], "context_chars": 0, "budget_chars": 4000,
                    "revision": 1, "truncated": False, "warnings": [],
                    "semantic": True, "semantic_model_fingerprint": "test-model-fingerprint"}
        compact = recall_payload(response)
        self.assertTrue(compact["semantic"])
        self.assertEqual(compact["semantic_model_fingerprint"], "test-model-fingerprint")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[mcp] for real MCP checks")
class SemanticMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_semantic_is_strict_and_requires_operator_model(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            parameters = StdioServerParameters(command=sys.executable,
                args=["-m", "memory_book", "--db", database, "mcp"],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONUNBUFFERED": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    tool = next(t for t in tools.tools if t.name == "recall_memory")
                    self.assertEqual(tool.inputSchema["properties"]["semantic"]["type"], "boolean")
                    self.assertNotIn("semantic_model_dir", tool.inputSchema["properties"])
                    for value in ("true", "false", 0, 1, True):
                        result = await client.call_tool("recall_memory", {"query": "cache", "semantic": value})
                        self.assertTrue(result.isError, (value, result))
                    result = await client.call_tool("recall_memory", {"query": "cache", "semantic": False})
                    self.assertFalse(result.isError, result)


if __name__ == "__main__":
    unittest.main()
