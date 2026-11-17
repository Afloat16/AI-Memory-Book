"""Exercise connection ownership through real SDK calls and stdio transport."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import get_ident
import unittest
from unittest.mock import patch

from memory_book.store import MemoryBook

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


@unittest.skipUnless(HAS_MCP, "Install .[mcp] to run official SDK lifecycle tests")
class MCPLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "memory.sqlite3"
        with MemoryBook(self.database) as book:
            book.ingest(self.sample())

    @staticmethod
    def sample(value="amber"):
        return {
            "project": "lab", "session_id": "calibration", "title": "Calibration",
            "task_id": "instruments", "task_title": "Calibration records",
            "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": "Which calibration key is selected?"},
                         {"role": "assistant", "content": f"The calibration key is {value}."}],
        }

    @staticmethod
    def decoded(result):
        return json.loads("".join(part.text for part in result if part.type == "text"))

    @contextmanager
    def track_connections(self):
        records = []

        def open_book(*args, **kwargs):
            book = MemoryBook(*args, **kwargs)
            record = {"book": book, "opened": get_ident(), "closed": []}
            records.append(record)
            original_close = book.close

            def close():
                record["closed"].append(get_ident())
                original_close()

            book.close = close
            return book

        with patch("memory_book.mcp_server.MemoryBook", side_effect=open_book):
            yield records

    async def recall(self, server):
        return self.decoded(await server.call_tool("recall_memory", {
            "query": "calibration key", "project": "lab", "budget_chars": 1000,
        }))

    async def test_lifespan_reuses_one_connection_and_preserves_payload_and_schema(self):
        from memory_book.mcp_server import create_server, recall_payload
        server = create_server(self.database)
        declarations = [tool.model_dump(mode="json") for tool in await server.list_tools()]
        with MemoryBook(self.database) as book:
            expected = recall_payload(book.recall("calibration key", project="lab", budget_chars=1000))
        with self.track_connections() as records:
            async with server.settings.lifespan(server):
                self.assertEqual(records, [])  # Initialization and listing stay lazy.
                results = await asyncio.gather(*(self.recall(server) for _ in range(4)))
                self.assertEqual(results, [expected] * 4)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["closed"], [])
                self.assertEqual([tool.model_dump(mode="json") for tool in await server.list_tools()], declarations)
            self.assertEqual(records[0]["closed"], [records[0]["opened"]])
            with self.assertRaises(sqlite3.ProgrammingError):
                records[0]["book"].db.execute("SELECT 1")

    async def test_direct_calls_and_worker_threads_use_closed_temporary_connections(self):
        from memory_book.mcp_server import create_server
        server = create_server(self.database)
        with self.track_connections() as records:
            await self.recall(server)
            await self.recall(server)
            self.assertEqual(len(records), 2)
            self.assertTrue(all(record["closed"] == [record["opened"]] for record in records))
            async with server.settings.lifespan(server):
                owner_result = await self.recall(server)
                owner = records[-1]
                # to_thread copies ContextVars; the foreign thread must still
                # refuse to borrow the event-loop thread's SQLite connection.
                def worker():
                    return asyncio.run(self.recall(server))

                self.assertEqual(await asyncio.to_thread(worker), owner_result)
                worker_record = records[-1]
                self.assertNotEqual(worker_record["opened"], owner["opened"])
                self.assertEqual(worker_record["closed"], [worker_record["opened"]])
                self.assertEqual(owner["closed"], [])
                self.assertEqual(await self.recall(server), owner_result)
                self.assertEqual(len(records), 4)
            self.assertEqual(owner["closed"], [owner["opened"]])

    async def test_lifespan_exception_closes_connection_and_resets_fallback(self):
        from memory_book.mcp_server import create_server
        server = create_server(self.database)
        with self.track_connections() as records:
            with self.assertRaisesRegex(RuntimeError, "transport failure"):
                async with server.settings.lifespan(server):
                    await self.recall(server)
                    raise RuntimeError("transport failure")
            self.assertEqual(records[0]["closed"], [records[0]["opened"]])
            await self.recall(server)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[1]["closed"], [records[1]["opened"]])

    async def test_distinct_servers_keep_database_and_write_permissions_isolated(self):
        from memory_book.mcp_server import create_server
        other_path = self.database.with_name("other.sqlite3")
        with MemoryBook(other_path) as book:
            book.ingest(self.sample("violet"))
        readonly = create_server(self.database)
        writable = create_server(other_path, allow_write=True)
        async with readonly.settings.lifespan(readonly), writable.settings.lifespan(writable):
            original = await self.recall(readonly)
            self.assertIn("amber", original["context"])
            self.assertIn("violet", (await self.recall(writable))["context"])
            await writable.call_tool("remember_session", {"payload": self.sample("silver")})
            self.assertIn("silver", (await self.recall(writable))["context"])
            self.assertEqual(await self.recall(readonly), original)
            self.assertNotIn("remember_session", {tool.name for tool in await readonly.list_tools()})
            self.assertIn("remember_session", {tool.name for tool in await writable.list_tools()})

    @unittest.skipIf(sys.platform == "win32", "Windows does not permit replacing an open SQLite file")
    async def test_file_replacement_reopens_instead_of_serving_stale_connection(self):
        from memory_book.mcp_server import create_server
        replacement = self.database.with_name("replacement.sqlite3")
        with MemoryBook(replacement) as book:
            book.ingest(self.sample("cobalt"))
        server = create_server(self.database)
        with self.track_connections() as records:
            async with server.settings.lifespan(server):
                self.assertIn("amber", (await self.recall(server))["context"])
                # Fully checkpoint the old writer before replacing the main
                # file, so this test never mixes a new main file with old WAL.
                records[0]["book"].db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                replacement.replace(self.database)
                self.assertIn("cobalt", (await self.recall(server))["context"])
                self.assertEqual(len(records), 2)
                self.assertEqual(records[0]["closed"], [records[0]["opened"]])
                self.assertEqual(records[1]["closed"], [])
            self.assertEqual(records[1]["closed"], [records[1]["opened"]])

    async def test_missing_file_identity_does_not_retain_connections(self):
        from memory_book.mcp_server import create_server
        server = create_server(self.database)
        with self.track_connections() as records, patch("memory_book.mcp_server._database_identity", return_value=None):
            async with server.settings.lifespan(server):
                first = await self.recall(server)
                self.assertEqual(await self.recall(server), first)
                self.assertEqual(len(records), 2)
                self.assertTrue(all(record["closed"] == [record["opened"]] for record in records))

    async def test_real_stdio_observes_external_writer_and_invalidates_cached_recall(self):
        source = Path(__file__).resolve().parents[1] / "src"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "import sys; from memory_book.mcp_server import serve; serve(sys.argv[1])", str(self.database)],
            env={"PYTHONPATH": str(source), "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                arguments = {"query": "calibration key", "project": "lab", "budget_chars": 1000}
                first = await client.call_tool("recall_memory", arguments)
                self.assertFalse(first.isError)
                old = self.decoded(first.content)
                self.assertIn("amber", old["context"])
                repeated = await client.call_tool("recall_memory", arguments)
                self.assertEqual(self.decoded(repeated.content), old)
                with MemoryBook(self.database) as external:
                    external.ingest(self.sample("cobalt"))
                latest = await client.call_tool("recall_memory", arguments)
                self.assertFalse(latest.isError)
                current = self.decoded(latest.content)
                self.assertGreater(current["revision"], old["revision"])
                self.assertIn("cobalt", current["context"])
                self.assertNotIn("amber", current["context"])
                self.assertIsNone(latest.structuredContent)


if __name__ == "__main__":
    unittest.main()
