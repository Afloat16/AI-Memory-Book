"""Exercise local ranking and required-field delivery over the real SDK transport."""
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

from memory_book import MemoryBook

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def source(value):
    return {"project": "engine", "session_id": "decision", "task_id": "limits",
            "task_title": "Production limits", "created_at": "2020-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content": f"Production retry_limit={value}."}]}


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for actual protocol checks")
class ProjectRankingMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_compact_gate_scope_directory_and_cross_connection_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = str(Path(temporary) / "memory.db")
            with MemoryBook(database, segmentation="turn") as book:
                book.ingest(source(12))
            parameters = StdioServerParameters(command=sys.executable, args=[
                "-c", "import sys; from memory_book.mcp_server import serve; "
                "serve(sys.argv[1], project='engine', ranking_scope='project')", database],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                     "PYTHONUNBUFFERED": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer,
                                         read_timeout_seconds=timedelta(seconds=20)) as client:
                    await client.initialize()

                    async def call(name, arguments):
                        response = await client.call_tool(name, arguments)
                        self.assertFalse(response.isError, response)
                        return json.loads("\n".join(part.text for part in response.content if part.type == "text"))

                    arguments = {"query": "current production retry_limit", "required_fields": ["retry_limit"]}
                    first = await call("recall_memory", arguments)
                    self.assertEqual(first["ranking_scope"]["actual"], "project")
                    self.assertEqual(first["evidence_gate"]["status"], "supported")
                    self.assertIn("retry_limit=12", first["context"])
                    hot = await call("recall_memory", {**arguments, "details": True})
                    self.assertTrue(hot["cache_hit"])
                    self.assertTrue(hot["ranking_scope"]["index_cache_hit"])
                    missing = await call("recall_memory", {**arguments, "required_fields": ["unknown_value"]})
                    self.assertEqual(missing["context"], "")
                    self.assertEqual(missing["evidence_gate"]["status"], "abstained")
                    directory = await call("search_directory", {"query": "Production limits"})
                    self.assertEqual(directory["ranking_scope"]["actual"], "project")
                    with MemoryBook(database, segmentation="turn") as writer_book:
                        writer_book.ingest(source(7))
                    revised = await call("recall_memory", {**arguments, "details": True})
                    self.assertFalse(revised["cache_hit"])
                    self.assertIn("retry_limit=7", revised["context"])
                    self.assertNotIn("retry_limit=12", revised["context"])
                    self.assertTrue(all(ref["project"] == "engine" for hit in revised["results"]
                                        for ref in hit["source_refs"]))


if __name__ == "__main__":
    unittest.main()
