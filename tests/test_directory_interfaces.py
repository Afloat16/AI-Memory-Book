"""Directory addresses keep their exact project through CLI, HTTP and MCP."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from memory_book.cli import main
from memory_book.store import MemoryBook
from memory_book.web import make_server


class DirectoryFixture:
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "archive.db"
        self.chapters = {}
        with MemoryBook(self.database) as book:
            for project, value in (("service-alpha", 3), ("service-beta", 9)):
                saved = book.ingest({
                    "project": project, "session_id": "same-session",
                    "task_id": "same-task", "task_title": "Early stopping callback",
                    "title": "Early stopping callback",
                    "created_at": "2026-01-01T00:00:00Z",
                    "messages": [{"role": "assistant", "content": f"patience={value}; min_delta=0.001"}],
                })
                self.chapters[project] = saved["chapter_id"]

    def assert_navigation(self, result, project):
        self.assertEqual(result["result_type"], "directory")
        self.assertFalse(result["evidence"])
        self.assertEqual({row["project_id"] for row in result["results"]}, {project})
        self.assertEqual(result["results"][0]["chapter_id"], self.chapters[project])
        self.assertNotIn("context", result)
        self.assertNotIn("patience=9", json.dumps(result))
        for chapter in result["results"]:
            self.assertNotIn("content", chapter)
            self.assertNotIn("source_refs", chapter)
            for section in chapter["sections"]:
                self.assertNotIn("content", section)
                self.assertNotIn("source_refs", section)


class DirectoryCLIHTTPTests(DirectoryFixture, unittest.TestCase):
    def test_cli_locates_titles_then_reads_the_original_scoped_page(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", str(self.database), "locate", "early stopping",
                         "--project", "service-alpha", "--limit", "1"])
        self.assertEqual(code, 0, err.getvalue())
        result = json.loads(out.getvalue())
        self.assert_navigation(result, "service-alpha")
        with MemoryBook(self.database) as book:
            chapter = book.chapter(result["results"][0]["chapter_id"], project="service-alpha")
            page_id = chapter["sections"][0]["pages"][0]["id"]
            page = book.read(page_id, project="service-alpha")
        self.assertIn("patience=3", page["content"])
        self.assertNotIn("patience=9", page["content"])

    def test_http_rejects_conflicting_chapters_and_empty_scope(self):
        server = make_server(self.database, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cases = [
                ({"project": "service-alpha"}, 200),
                ({"project": "service-alpha", "chapter": self.chapters["service-beta"]}, 404),
                ({"project": ""}, 400),
            ]
            for params, expected in cases:
                with self.subTest(params=params):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    try:
                        connection.request("GET", "/api/locate?" + urlencode({"q": "early stopping", **params}))
                        response = connection.getresponse()
                        body = response.read().decode()
                        self.assertEqual(response.status, expected, body)
                        if expected == 200:
                            self.assert_navigation(json.loads(body), "service-alpha")
                        else:
                            self.assertNotIn("patience=9", body)
                    finally:
                        connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[mcp] for protocol tests")
class DirectoryMCPTests(DirectoryFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_inherits_project_and_rejects_foreign_navigation(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "memory_book", "--db", str(self.database), "mcp", "--project=service-alpha"],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                response = await client.call_tool("search_directory", {"query": "early stopping"})
                self.assertFalse(response.isError, response)
                result = json.loads("".join(part.text for part in response.content if part.type == "text"))
                self.assert_navigation(result, "service-alpha")
                for extra in ({"project": "service-beta"}, {"chapter": self.chapters["service-beta"]},
                              {"project": ""}, {"limit": True}):
                    response = await client.call_tool("search_directory", {"query": "early stopping", **extra})
                    self.assertTrue(response.isError, response)
                    self.assertNotIn("patience=9", str(response))


if __name__ == "__main__":
    unittest.main()
