"""Real CLI, HTTP, and MCP paths keep similar project books distinguishable."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from urllib.parse import urlencode

from memory_book import MemoryBook
from memory_book.cli import main
from memory_book.segmentation import make_turns
from memory_book.web import make_server

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def source(project, value):
    return {
        "project": project, "project_name": "Twin API", "session_id": "same-session",
        "title": "Same decisions", "task_id": "retry", "task_title": "Retry catalog",
        "created_at": "2026-11-01T00:00:00Z",
        "messages": [
            {"role": "user", "content": "How should retries work?"},
            {"role": "assistant", "content": f"retry_limit={value}\n" +
             (f"body_marker_{project} original evidence. " * 400) + "END OF TURN"},
        ],
    }


def result_projects(result):
    return {ref["project"] for hit in result["results"] for ref in hit["source_refs"]}


class _BookFixture:
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="memory-book-navigation-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "book.db"
        self.original = source("alpha", 3)
        with MemoryBook(self.database, max_page_chars=500, min_page_chars=0) as book:
            self.record = book.ingest(self.original)
            book.ingest(source("beta", 9))
            self.section = book.chapter(self.record["chapter_id"])["sections"][0]
            self.page_id = self.section["pages"][0]["id"]
        self.turn = make_turns(self.original["messages"])[0].content

    def change_source(self):
        changed = source("alpha", 7)
        with MemoryBook(self.database) as book:
            book.ingest(changed)


class CliBookNavigationTests(_BookFixture, unittest.TestCase):
    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--db", str(self.database), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_multi_book_recall_requires_explicit_scope_and_keeps_global_opt_in(self):
        code, text, error = self.cli("recall", "retry_limit", "--json", "--limit", "1")
        self.assertEqual(code, 2)
        self.assertEqual(text, "")
        self.assertIn("project", error)
        code, text, error = self.cli("recall", "retry_limit", "--project", "alpha", "--json")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(result_projects(json.loads(text)), {"alpha"})
        code, text, error = self.cli("recall", "retry_limit", "--all-projects", "--json")
        self.assertEqual((code, error), (0, ""))
        result = json.loads(text)
        self.assertEqual(result_projects(result), {"alpha", "beta"})
        self.assertTrue(result["warnings"])

    def test_directory_search_and_navigation_guards_reach_the_real_store(self):
        code, text, error = self.cli("index", "catalog", "--project", "alpha")
        self.assertEqual((code, error), (0, ""))
        result = json.loads(text)
        self.assertEqual(result["project"]["id"], "alpha")
        self.assertEqual(len(result["entries"]), 1)
        self.assertGreater(result["entries"][0]["page_count"], 1)
        self.assertNotIn("body_marker_alpha", text)
        for command, identity in (("chapter", self.record["chapter_id"]),
                                  ("section", self.section["id"]), ("read", self.page_id)):
            with self.subTest(command=command):
                code, text, error = self.cli(command, identity, "--project", "beta")
                self.assertEqual(code, 2)
                self.assertEqual(text, "")
                self.assertTrue(error)

    def test_turn_continuation_preserves_text_and_rejects_changed_source(self):
        code, text, error = self.cli("read", self.page_id, "--project", "alpha")
        self.assertEqual((code, error), (0, ""))
        source_hash = json.loads(text)["source_hash"]
        code, text, error = self.cli("turn", "alpha", "same-session", "0", "--limit", "53",
                                   "--source-hash", source_hash)
        self.assertEqual((code, error), (0, ""))
        first = json.loads(text)
        code, text, error = self.cli("turn", "alpha", "same-session", "0", "--offset",
                                   str(first["next_offset"]), "--limit", "100000",
                                   "--source-hash", source_hash)
        self.assertEqual((code, error), (0, ""))
        last = json.loads(text)
        self.assertEqual(first["content"] + last["content"], self.turn)
        self.assertIsNone(last["next_offset"])
        self.change_source()
        code, text, error = self.cli("turn", "alpha", "same-session", "0", "--offset", "53",
                                   "--source-hash", source_hash)
        self.assertEqual(code, 2)
        self.assertEqual(text, "")
        self.assertIn("source", error.lower())


class HttpBookNavigationTests(_BookFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.database, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def get(self, path, **params):
        with contextlib.closing(http.client.HTTPConnection(
                "127.0.0.1", self.server.server_address[1], timeout=5)) as connection:
            connection.request("GET", path + "?" + urlencode(params))
            response = connection.getresponse()
            return response.status, json.loads(response.read())

    def test_empty_or_missing_scope_never_falls_back_to_other_books(self):
        for extra in ({}, {"project": ""}, {"chapter": ""}, {"session": ""},
                      {"all_projects": ""}, {"all_projects": "1"},
                      {"project": "alpha", "all_projects": "true"}):
            with self.subTest(extra=extra):
                status, result = self.get("/api/recall", q="retry_limit", limit=1, **extra)
                self.assertEqual(status, 400)
                self.assertNotIn("results", result)
        status, result = self.get("/api/recall", q="retry_limit", project="alpha")
        self.assertEqual(status, 200)
        self.assertEqual(result_projects(result), {"alpha"})
        status, result = self.get("/api/recall", q="retry_limit", all_projects="true")
        self.assertEqual(status, 200)
        self.assertEqual(result_projects(result), {"alpha", "beta"})

    def test_book_guards_and_directory_metadata_do_not_return_foreign_evidence(self):
        for path, identity in (("/api/chapter", self.record["chapter_id"]),
                               ("/api/section", self.section["id"]), ("/api/read", self.page_id)):
            with self.subTest(path=path):
                status, result = self.get(path, id=identity, project="beta")
                self.assertEqual(status, 404)
                self.assertNotIn("content", result)
        status, result = self.get("/api/directory", q="catalog", project="alpha", limit=1)
        self.assertEqual(status, 200)
        self.assertEqual(len(result["entries"]), 1)
        self.assertNotIn("body_marker_alpha", json.dumps(result))
        self.assertTrue(all(ref["project"] == "alpha" for entry in result["entries"]
                            for ref in entry["source_refs"]))
        status, result = self.get("/api/directory", q="body_marker_alpha", project="alpha")
        self.assertEqual((status, result["entries"]), (200, []))
        status, _ = self.get("/api/directory", q="catalog", project="")
        self.assertEqual(status, 400)

    def test_source_turn_hash_is_forwarded_across_http_continuations(self):
        status, page = self.get("/api/read", id=self.page_id, project="alpha")
        self.assertEqual(status, 200)
        args = {"project": "alpha", "session_id": "same-session", "turn_index": 0,
                "source_hash": page["source_hash"]}
        status, first = self.get("/api/turn", **args, limit=53)
        self.assertEqual(status, 200)
        status, last = self.get("/api/turn", **args, offset=first["next_offset"], limit=24000)
        self.assertEqual(status, 200)
        self.assertEqual(first["content"] + last["content"], self.turn)
        self.assertIsNone(last["next_offset"])
        self.change_source()
        status, result = self.get("/api/turn", **args, offset=53)
        self.assertEqual(status, 400)
        self.assertNotIn("content", result)


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for official SDK navigation tests")
class McpBookNavigationTests(_BookFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_safe_scope_directory_and_complete_turn_workflow(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "memory_book", "--db", str(self.database), "mcp"],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as client:
                await client.initialize()
                listed = await client.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                self.assertTrue(tools["search_directory"].annotations.readOnlyHint)
                self.assertTrue(tools["read_source_turn"].annotations.readOnlyHint)
                self.assertEqual(tools["recall_memory"].inputSchema["properties"]["all_projects"]["default"], False)

                async def call(name, arguments):
                    response = await client.call_tool(name, arguments)
                    self.assertFalse(response.isError, response)
                    return json.loads(response.content[0].text)

                for extra in ({}, {"project": ""}, {"all_projects": 1}):
                    response = await client.call_tool("recall_memory", {"query": "retry_limit", "limit": 1, **extra})
                    self.assertTrue(response.isError)
                result = await call("recall_memory", {"query": "retry_limit", "project": "alpha"})
                self.assertEqual(result_projects(result), {"alpha"})
                result = await call("recall_memory", {"query": "retry_limit", "all_projects": True})
                self.assertEqual(result_projects(result), {"alpha", "beta"})
                directory = await call("search_directory", {"query": "catalog", "project": "alpha"})
                self.assertEqual(len(directory["entries"]), 1)
                self.assertNotIn("body_marker_alpha", json.dumps(directory))
                for name, identity in (("browse_chapter", {"chapter_id": self.record["chapter_id"]}),
                                       ("browse_section", {"section_id": self.section["id"]}),
                                       ("read_page", {"page_id": self.page_id})):
                    response = await client.call_tool(name, {**identity, "project": "beta"})
                    self.assertTrue(response.isError)
                page = await call("read_page", {"page_id": self.page_id, "project": "alpha"})
                args = {"project": "alpha", "session_id": "same-session", "turn_index": 0,
                        "source_hash": page["source_hash"]}
                first = await call("read_source_turn", {**args, "limit": 53})
                last = await call("read_source_turn", {**args, "offset": first["next_offset"], "limit": 100000})
                self.assertEqual(first["content"] + last["content"], self.turn)
                self.assertIsNone(last["next_offset"])
                self.change_source()
                response = await client.call_tool("read_source_turn", {**args, "offset": 53})
                self.assertTrue(response.isError)
