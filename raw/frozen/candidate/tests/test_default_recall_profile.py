"""The shipped default must agree across API, CLI, HTTP, and real MCP calls."""

from __future__ import annotations

import contextlib
from datetime import timedelta
from html.parser import HTMLParser
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from memory_book import MemoryBook
from memory_book.cli import main
from memory_book.web import make_server

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


QUERIES = ("calibration cache", "current calibration cache", "original calibration cache")


def populate(path):
    with MemoryBook(path) as book:
        for index in range(6):
            book.ingest({
                "project": "defaults", "session_id": f"session-{index}", "task_id": "calibration",
                "title": "Calibration cache", "created_at": f"2026-01-{index + 1:02}T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                              f"Calibration cache record {index}. " +
                              "Calibration cache uses a verified source and preserves the configuration. " * 10}],
            })


def stable(payload):
    return {key: value for key, value in payload.items() if key not in {"latency_ms", "cache_hit"}}


class BudgetOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_budget = False
        self.values, self.selected = [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "select":
            self.in_budget = values.get("id") == "budget"
        elif self.in_budget and tag == "option":
            self.values.append(values.get("value"))
            if "selected" in values:
                self.selected.append(values.get("value"))

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_budget = False


class RecallDefaultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "memory.sqlite3"
        populate(self.database)

    def assert_default(self, payload):
        self.assertEqual(payload["budget_chars"], 2400)
        self.assertLessEqual(payload["context_chars"], 2400)
        self.assertEqual(len(payload["results"]), 5)
        self.assertNotIn("budget_tokens", payload)
        self.assertNotIn("semantic", payload)

    def test_python_omitted_profile_matches_explicit_values_and_keeps_overrides(self):
        with MemoryBook(self.database) as book:
            for query in QUERIES:
                with self.subTest(query=query):
                    omitted = book.recall(query, project="defaults", use_cache=False)
                    explicit = book.recall(query, project="defaults", budget_chars=2400, limit=5, use_cache=False)
                    self.assert_default(omitted)
                    self.assertEqual(omitted["strategy"], "book")
                    self.assertEqual(stable(omitted), stable(explicit))
            larger = book.recall(QUERIES[0], project="defaults", budget_chars=4000, use_cache=False)
            self.assertEqual(larger["budget_chars"], 4000)
            self.assertGreater(larger["context_chars"], 2400)
            self.assertLessEqual(larger["context_chars"], 4000)
            limited = book.recall(QUERIES[0], project="defaults", budget_chars=1200, limit=2, use_cache=False)
            self.assertEqual(limited["budget_chars"], 1200)
            self.assertLessEqual(limited["context_chars"], 1200)
            self.assertEqual(len(limited["results"]), 2)

    def cli_recall(self, query, *options):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--db", str(self.database), "recall", query,
                         "--project", "defaults", "--json", "--no-cache", *options])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_cli_omitted_profile_matches_python_and_explicit_overrides(self):
        with MemoryBook(self.database) as book:
            for query in QUERIES:
                with self.subTest(query=query):
                    omitted = self.cli_recall(query)
                    explicit = self.cli_recall(query, "--budget", "2400", "--limit", "5")
                    self.assert_default(omitted)
                    self.assertEqual(stable(omitted), stable(explicit))
                    self.assertEqual(stable(omitted), stable(book.recall(query, project="defaults", use_cache=False)))
        larger = self.cli_recall(QUERIES[0], "--budget", "4000")
        self.assertEqual(larger["budget_chars"], 4000)
        self.assertGreater(larger["context_chars"], 2400)
        limited = self.cli_recall(QUERIES[0], "--budget", "1200", "--limit", "2")
        self.assertEqual(limited["budget_chars"], 1200)
        self.assertLessEqual(limited["context_chars"], 1200)
        self.assertEqual(len(limited["results"]), 2)

    def test_http_and_served_reader_share_the_default_and_keep_explicit_budgets(self):
        server = make_server(self.database, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def get(path):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, body)
                return body
            finally:
                connection.close()

        def recall(query, **options):
            return json.loads(get("/api/recall?" + urlencode({"q": query, "project": "defaults", **options})))

        try:
            page = BudgetOptions()
            page.feed(get("/").decode("utf-8"))
            self.assertEqual(page.selected, ["2400"])
            self.assertIn("4000", page.values)
            for query in QUERIES:
                with self.subTest(query=query):
                    omitted = recall(query)
                    explicit = recall(query, budget_chars=2400, limit=5)
                    self.assert_default(omitted)
                    self.assertEqual(stable(omitted), stable(explicit))
            larger = recall(QUERIES[0], budget_chars=4000)
            self.assertEqual(larger["budget_chars"], 4000)
            self.assertGreater(larger["context_chars"], 2400)
            limited = recall(QUERIES[0], budget_chars=1200, limit=2)
            self.assertLessEqual(limited["context_chars"], 1200)
            self.assertEqual(len(limited["results"]), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@unittest.skipUnless(HAS_MCP, "Install .[mcp] to check the real stdio default")
class MCPRecallDefaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_omitted_budget_matches_explicit_profile_and_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "memory.sqlite3"
            populate(database)
            source = Path(__file__).resolve().parents[1] / "src"
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "memory_book", "--db", str(database), "mcp"],
                env={"PYTHONPATH": str(source), "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    schema = next(tool.inputSchema for tool in tools.tools if tool.name == "recall_memory")
                    self.assertEqual(schema["properties"]["budget_chars"]["default"], 2400)
                    self.assertEqual(schema["properties"]["limit"]["default"], 5)
                    self.assertFalse(schema["properties"]["details"]["default"])

                    async def recall(query, **options):
                        response = await client.call_tool("recall_memory", {
                            "query": query, "project": "defaults", **options,
                        })
                        self.assertFalse(response.isError, response)
                        return json.loads("".join(part.text for part in response.content if part.type == "text"))

                    for query in QUERIES:
                        with self.subTest(query=query):
                            omitted = await recall(query)
                            explicit = await recall(query, budget_chars=2400, limit=5)
                            self.assertEqual(omitted, explicit)
                            self.assertEqual(omitted["budget_chars"], 2400)
                            self.assertLessEqual(omitted["context_chars"], 2400)
                            self.assertEqual(len(omitted["results"]), 5)
                            self.assertNotIn("budget_tokens", omitted)
                            self.assertNotIn("semantic", omitted)
                            self.assertNotIn("source_format", omitted)
                    larger = await recall(QUERIES[0], budget_chars=4000)
                    self.assertEqual(larger["budget_chars"], 4000)
                    self.assertGreater(larger["context_chars"], 2400)
                    limited = await recall(QUERIES[0], budget_chars=1200, limit=2)
                    self.assertEqual(limited["budget_chars"], 1200)
                    self.assertLessEqual(limited["context_chars"], 1200)
                    self.assertEqual(len(limited["results"]), 2)


if __name__ == "__main__":
    unittest.main()
