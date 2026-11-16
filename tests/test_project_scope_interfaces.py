"""Exercise project assertions through real CLI, HTTP and MCP boundaries."""

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


def sample(project, value):
    return {"project": project, "project_name": "same-service", "session_id": "setup",
            "task_id": "runtime", "task_title": "same task", "title": "configuration",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": "What is the retry_limit?"},
                         {"role": "assistant", "content": f"retry_limit={value}."}]}


class ScopeFixture:
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "memory.db"
        self.ids = {}
        with MemoryBook(self.database) as book:
            for project, value in (("service-alpha", 3), ("service-beta", 9)):
                book.ingest(sample(project, value))
                chapter = book.toc(project)["chapters"][0]["id"]
                section = book.chapter(chapter)["sections"][0]
                self.ids[project] = {"chapter": chapter, "section": section["id"],
                                     "read": section["pages"][0]["id"]}


class ProjectScopeCLIHTTPTests(ScopeFixture, unittest.TestCase):
    def test_cli_assertions_reject_foreign_ids_and_preserve_global_mode(self):
        for command in ("chapter", "section", "read"):
            foreign = self.ids["service-beta"][command]
            for project, expected in (("service-alpha", 2), ("service-beta", 0), (None, 0)):
                with self.subTest(command=command, project=project):
                    out, err = io.StringIO(), io.StringIO()
                    args = ["--db", str(self.database), command, foreign]
                    if project is not None:
                        args += ["--project", project]
                    with redirect_stdout(out), redirect_stderr(err):
                        code = main(args)
                    self.assertEqual(code, expected, err.getvalue())
                    if expected:
                        self.assertEqual(out.getvalue(), "")
                        self.assertNotIn("retry_limit=9", err.getvalue())
                        self.assertNotIn("service-beta", err.getvalue())
                    else:
                        self.assertIsInstance(json.loads(out.getvalue()), dict)

    def test_http_assertions_preserve_scope_on_every_followup(self):
        server = make_server(self.database, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/api/recall?q=retry_limit&project=")
                response = connection.getresponse()
                body = response.read().decode()
                self.assertEqual(response.status, 400, body)
                self.assertNotIn("retry_limit=9", body)
                self.assertNotIn("retry_limit=3", body)
            finally:
                connection.close()
            for command in ("chapter", "section", "read"):
                foreign = self.ids["service-beta"][command]
                for project, expected in (("service-alpha", 404), ("service-beta", 200), (None, 200), ("", 400)):
                    with self.subTest(command=command, project=project):
                        params = {"id": foreign}
                        if project is not None:
                            params["project"] = project
                        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                        try:
                            connection.request("GET", "/api/" + command + "?" + urlencode(params))
                            response = connection.getresponse()
                            body = response.read().decode()
                            self.assertEqual(response.status, expected, body)
                            if expected != 200:
                                self.assertNotIn("retry_limit=9", body)
                                self.assertNotIn("service-beta", body)
                        finally:
                            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[mcp] for protocol tests")
class ProjectScopeMCPTests(ScopeFixture, unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def decode(result):
        return json.loads("".join(part.text for part in result if part.type == "text"))

    async def test_real_stdio_bound_connection_inherits_scope_and_rejects_foreign_reads_and_writes(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "memory_book", "--db", str(self.database), "mcp", "--project=service-alpha", "--allow-write"],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                initialized = await client.initialize()
                self.assertIn('bound to project "service-alpha"', initialized.instructions)

                async def call(name, arguments, error=False):
                    response = await client.call_tool(name, arguments)
                    self.assertEqual(bool(response.isError), error, response)
                    text = "".join(part.text for part in response.content if part.type == "text")
                    if error:
                        self.assertNotIn("retry_limit=9", text)
                        return text
                    return json.loads(text)

                projects = await call("browse_projects", {})
                self.assertEqual([item["id"] for item in projects], ["service-alpha"])
                for arguments in ({"query": "retry_limit"}, {"query": "retry_limit", "project": "service-alpha"},
                                  {"query": "retry_limit", "session": "setup"}):
                    response = await call("recall_memory", arguments)
                    self.assertIn("retry_limit=3", response["context"])
                    self.assertNotIn("retry_limit=9", response["context"])
                    self.assertEqual({ref["project"] for hit in response["results"] for ref in hit["source_refs"]}, {"service-alpha"})
                await call("recall_memory", {"query": "retry_limit", "project": "service-beta"}, True)
                await call("recall_memory", {"query": "retry_limit", "project": ""}, True)
                await call("browse_book", {"project": "service-alpha"})
                inherited_toc = await call("browse_book", {})
                self.assertEqual(inherited_toc["project"]["id"], "service-alpha")
                await call("browse_book", {"project": "service-beta"}, True)
                for method, tool, parameter in (("chapter", "browse_chapter", "chapter_id"),
                                                ("section", "browse_section", "section_id"),
                                                ("read", "read_page", "page_id")):
                    await call(tool, {parameter: self.ids["service-alpha"][method]})
                    await call(tool, {parameter: self.ids["service-beta"][method]}, True)
                    await call(tool, {parameter: self.ids["service-beta"][method], "project": "service-beta"}, True)
                await call("remember_session", {"payload": sample("service-beta", 99)}, True)
                missing = sample("service-alpha", 7)
                del missing["project"]
                await call("remember_session", {"payload": missing}, True)
                await call("remember_session", {"payload": sample("service-alpha", 7)})
                after = await call("recall_memory", {"query": "retry_limit"})
                self.assertIn("retry_limit=7", after["context"])
                self.assertNotIn("retry_limit=3", after["context"])
        with MemoryBook(self.database) as book:
            self.assertIn("retry_limit=9", book.recall("retry_limit", project="service-beta")["context"])

    async def test_bound_servers_keep_separate_scope_and_unknown_scope_does_not_fall_back(self):
        from memory_book.mcp_server import create_server
        for project in ("service-alpha", "service-beta", "missing-project", "service-alpha"):
            server = create_server(self.database, project=project)
            projects = self.decode(await server.call_tool("browse_projects", {}))
            response = self.decode(await server.call_tool("recall_memory", {"query": "retry_limit"}))
            if project == "missing-project":
                self.assertEqual(projects, [])
                self.assertEqual(response["results"], [])
                self.assertEqual(response["context"], "")
            else:
                self.assertEqual([item["id"] for item in projects], [project])
                self.assertEqual({ref["project"] for hit in response["results"] for ref in hit["source_refs"]}, {project})

    async def test_unbound_server_remains_global_but_can_assert_followup_project(self):
        from memory_book.mcp_server import create_server
        from mcp.server.fastmcp.exceptions import ToolError
        server = create_server(self.database)
        projects = self.decode(await server.call_tool("browse_projects", {}))
        self.assertEqual({item["id"] for item in projects}, set(self.ids))
        for project in self.ids:
            result = self.decode(await server.call_tool("read_page", {"page_id": self.ids[project]["read"]}))
            self.assertEqual(result["breadcrumb"][0]["id"], project)
        with self.assertRaises(ToolError):
            await server.call_tool("read_page", {"page_id": self.ids["service-beta"]["read"], "project": "service-alpha"})
        with self.assertRaises(ToolError):
            await server.call_tool("browse_book", {})

    async def test_invalid_binding_fails_before_creating_database(self):
        from memory_book.mcp_server import create_server
        missing = self.database.parent / "missing" / "archive.db"
        for project in ("", " ", " service-alpha", "service-alpha ", "x" * 201, "a\x00b", "\ud800", 7, False):
            with self.subTest(project=repr(project)), self.assertRaises(ValueError):
                create_server(missing, project=project)
        self.assertFalse(missing.parent.exists())
