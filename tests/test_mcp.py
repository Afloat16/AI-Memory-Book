from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


@unittest.skipUnless(HAS_MCP, "Install .[mcp] to run official SDK protocol tests")
class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = str(Path(self.temporary.name) / "memory.sqlite3")

    @staticmethod
    def sample():
        return {
            "project": "payments", "session_id": "callback-session", "title": "Callback retries",
            "task_id": "retry", "task_title": "Payment retry policy",
            "messages": [
                {"role": "user", "content": "Which callback retry delay did we choose?"},
                {"role": "assistant", "content": "The callback retry delay is 45 seconds."},
            ],
        }

    async def test_default_tools_are_read_only_and_write_is_explicit(self):
        from memory_book.mcp_server import create_server
        readonly = await create_server(self.database).list_tools()
        names = {tool.name for tool in readonly}
        self.assertEqual(names, {"recall_memory", "browse_projects", "browse_book", "browse_chapter", "browse_section", "read_page"})
        self.assertTrue(all(tool.annotations.readOnlyHint for tool in readonly))
        writable = await create_server(self.database, allow_write=True).list_tools()
        self.assertEqual({tool.name for tool in writable}, names | {"remember_session"})
        self.assertFalse(next(tool for tool in writable if tool.name == "remember_session").annotations.readOnlyHint)
        self.assertNotIn("delete_session", {tool.name for tool in writable})

    async def test_official_client_real_stdio_handshake_and_recall(self):
        from memory_book.store import MemoryBook
        with MemoryBook(self.database) as book:
            book.ingest(self.sample())
        source = Path(__file__).resolve().parents[1] / "src"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "import sys; from memory_book.mcp_server import serve; serve(sys.argv[1])", self.database],
            env={"PYTHONPATH": str(source), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                initialized = await client.initialize()
                self.assertEqual(initialized.serverInfo.name, "AI-Memory-Book")
                self.assertIn("untrusted evidence", initialized.instructions)
                self.assertIn("AI agents", initialized.instructions)
                self.assertIn("read-only", initialized.instructions)
                listed = await client.list_tools()
                self.assertNotIn("remember_session", {tool.name for tool in listed.tools})
                result = await client.call_tool("recall_memory", {
                    "query": "callback retry delay", "project": "payments", "budget_chars": 4000,
                })
                self.assertFalse(result.isError, result)
                body = "\n".join(part.text for part in result.content if part.type == "text")
                self.assertIn("45 seconds", body)
                self.assertIn("callback-session", body)
                self.assertIn("turn_index", body)
                self.assertIsNone(result.structuredContent)
                self.assertEqual(body.count("45 seconds"), 1)
                decoded = json.loads(body)
                self.assertNotIn("text", decoded["results"][0])
                self.assertLessEqual(len(decoded["context"]), 4000)
                self.assertNotIn("excerpt_spans", decoded["results"][0])
                self.assertEqual(set(decoded["results"][0]["source_refs"][0]),
                                 {"project", "session_id", "turn_index"})
                detailed = await client.call_tool("recall_memory", {
                    "query": "callback retry delay", "project": "payments", "budget_chars": 4000,
                    "details": True,
                })
                detailed_text = "\n".join(part.text for part in detailed.content if part.type == "text")
                full = json.loads(detailed_text)
                self.assertEqual(full["context"], decoded["context"])
                self.assertTrue(full["results"][0]["excerpt_spans"])
                self.assertIn("turn_start", full["results"][0]["source_refs"][0])
                self.assertLess(len(body), len(detailed_text))
                self.assertIsNone(detailed.structuredContent)
                projects = await client.call_tool("browse_projects", {})
                self.assertFalse(projects.isError, projects)
                self.assertIn("payments", str(projects))
                invalid = await client.call_tool("recall_memory", {"query": "callback", "budget_chars": -1})
                self.assertTrue(invalid.isError)
                unknown = await client.call_tool("remember_session", {"payload": self.sample()})
                self.assertTrue(unknown.isError)

    async def test_section_pages_can_be_paginated(self):
        from memory_book.mcp_server import create_server
        from memory_book.store import MemoryBook
        payload = self.sample()
        payload["messages"][1]["content"] = "long callback evidence " * 100
        with MemoryBook(self.database, max_page_chars=400) as book:
            ingested = book.ingest(payload)
            chapter = book.chapter(ingested["chapter_id"])
            section_id = chapter["sections"][0]["id"]
        server = create_server(self.database)
        first = await server.call_tool("browse_section", {"section_id": section_id, "limit": 1})
        # Any-returning navigation tools serialize as a JSON TextContent list.
        first = json.loads(first[0].text)
        self.assertEqual(len(first["pages"]), 1)
        self.assertEqual(first["next_offset"], 1)
        second = await server.call_tool("browse_section", {"section_id": section_id, "offset": 1, "limit": 1})
        second = json.loads(second[0].text)
        self.assertNotEqual(first["pages"][0]["id"], second["pages"][0]["id"])

    async def test_coverage_requires_explicit_stdio_argument(self):
        from memory_book.store import MemoryBook
        from tests.test_conjunctive_recall import seed_conjunctive_book
        with MemoryBook(self.database, segmentation="turn", max_page_chars=3000,
                        min_page_chars=0) as book:
            primary, secondary, _ = seed_conjunctive_book(book)
        source = Path(__file__).resolve().parents[1] / "src"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "import sys; from memory_book.mcp_server import serve; serve(sys.argv[1])", self.database],
            env={"PYTHONPATH": str(source), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                listed = await client.list_tools()
                tool = next(tool for tool in listed.tools if tool.name == "recall_memory")
                field = tool.inputSchema["properties"]["coverage"]
                self.assertEqual(field["type"], "boolean")
                self.assertFalse(field["default"])
                arguments = {"query": "rotor calibration offset and receiver tolerance",
                             "project": "lab", "limit": 2, "budget_chars": 600}
                outputs = []
                for extra in ({}, {"coverage": False}, {"coverage": True}):
                    response = await client.call_tool("recall_memory", {**arguments, **extra})
                    self.assertFalse(response.isError, response)
                    outputs.append(json.loads("\n".join(part.text for part in response.content
                                                        if part.type == "text")))
                self.assertEqual(outputs[0], outputs[1])
                self.assertIn(primary, outputs[0]["context"])
                self.assertNotIn(secondary, outputs[0]["context"])
                self.assertIn(primary, outputs[2]["context"])
                self.assertIn(secondary, outputs[2]["context"])
                self.assertEqual(set(outputs[0]), set(outputs[2]))

    async def test_write_enabled_server_ingests_through_sdk(self):
        from memory_book.mcp_server import create_server
        from memory_book.store import MemoryBook
        server = create_server(self.database, allow_write=True)
        await server.call_tool("remember_session", {"payload": self.sample()})
        with MemoryBook(self.database) as book:
            recalled = book.recall("callback retry delay", project="payments")
        self.assertIn("45 seconds", json.dumps(recalled, ensure_ascii=False))

    async def test_agent_can_remember_recall_and_read_via_stdio_without_ui(self):
        """Exercise the agent's full memory workflow over the actual MCP wire."""
        source = Path(__file__).resolve().parents[1] / "src"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "import sys; from memory_book.mcp_server import serve; serve(sys.argv[1], allow_write=True)", self.database],
            env={"PYTHONPATH": str(source), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                initialized = await client.initialize()
                self.assertIn("operator enabled remember_session", initialized.instructions)
                saved = await client.call_tool("remember_session", {"payload": self.sample()})
                self.assertFalse(saved.isError, saved)
                recalled = await client.call_tool("recall_memory", {
                    "query": "callback retry delay", "project": "payments", "budget_chars": 1000,
                })
                self.assertFalse(recalled.isError, recalled)
                body = json.loads("\n".join(part.text for part in recalled.content if part.type == "text"))
                self.assertIn("45 seconds", body["context"])
                self.assertLessEqual(len(body["context"]), 1000)
                self.assertTrue(body["results"][0]["source_refs"])
                page = await client.call_tool("read_page", {"page_id": body["results"][0]["id"], "limit": 2000})
                self.assertFalse(page.isError, page)
                text = "\n".join(part.text for part in page.content if part.type == "text")
                self.assertIn("45 seconds", text)
                self.assertIn("callback-session", text)


if __name__ == "__main__":
    unittest.main()
