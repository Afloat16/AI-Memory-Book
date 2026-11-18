"""Current-evidence uncertainty survives the actual compact MCP interface."""

from __future__ import annotations

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


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for the real SDK protocol checks")
class CurrentAssessmentMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = str(Path(self.temporary.name) / "memory.db")
        with MemoryBook(self.database, segmentation="turn") as book:
            for project, values in (("service", (30, 12)), ("service-copy", (930, 912))):
                for sid, value in zip(("decision-a", "decision-b"), values):
                    book.ingest({"project": project, "session_id": sid,
                        "task_id": "retry", "task_title": "Retry configuration",
                        "title": "Configuration", "created_at": "2020-01-01T00:00:00Z",
                        "messages": [{"role": "assistant",
                                      "content": f"Production retry_limit={value}."}]})
            book.ingest({"project": "service", "session_id": "lease-agenda",
                "task_id": "lease", "task_title": "Lease review", "title": "Agenda",
                "created_at": "2020-02-01T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                    "Production lease_duration remains on the agenda. No value was decided."}]})

    @staticmethod
    def decoded(result):
        return json.loads("\n".join(part.text for part in result.content if part.type == "text"))

    async def test_real_compact_stdio_retains_conflicts_and_scoped_followups(self):
        parameters = StdioServerParameters(command=sys.executable, args=[
            "-c", "import sys; from memory_book.mcp_server import serve; "
            "serve(sys.argv[1], project='service')", self.database],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                 "PYTHONUNBUFFERED": "1"})
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer,
                                     read_timeout_seconds=timedelta(seconds=20)) as client:
                initialized = await client.initialize()
                self.assertIn("evidence_assessment", initialized.instructions)
                arguments = {"query": "current production retry_limit", "limit": 1,
                             "budget_chars": 1200}
                response = await client.call_tool("recall_memory", arguments)
                self.assertFalse(response.isError, response)
                compact = self.decoded(response)
                self.assertNotIn("temporal", compact)
                assessment = compact["evidence_assessment"]
                self.assertEqual(assessment["status"], "potential_conflict")
                self.assertEqual(assessment["scope"], "bounded_candidate_pool")
                self.assertEqual(len(compact["results"]), 1)
                ids = {page for conflict in assessment["conflicts"]
                       for page in conflict["page_ids"]}
                self.assertEqual(len(ids), 2)
                self.assertTrue(ids - {hit["id"] for hit in compact["results"]})
                sessions = set()
                for page_id in ids:
                    original = await client.call_tool("read_page", {"page_id": page_id})
                    self.assertFalse(original.isError, original)
                    page = self.decoded(original)
                    self.assertEqual(page["id"], page_id)
                    for ref in page["source_refs"]:
                        self.assertEqual(ref["project"], "service")
                        sessions.add(ref["session_id"])
                self.assertEqual(sessions, {"decision-a", "decision-b"})
                forbidden = await client.call_tool("read_page", {
                    "page_id": next(iter(ids)), "project": "service-copy"})
                self.assertTrue(forbidden.isError)

                detailed = self.decoded(await client.call_tool("recall_memory", {
                    **arguments, "details": True}))
                self.assertEqual(detailed["context"], compact["context"])
                full = detailed["temporal"]["evidence_assessment"]
                self.assertEqual({key: full[key] for key in assessment}, assessment)
                self.assertIn("inspected_candidates", full)

                pending = self.decoded(await client.call_tool("recall_memory", {
                    "query": "current production lease_duration", "budget_chars": 1200}))
                self.assertEqual(pending["evidence_assessment"]["status"],
                                 "no_comparable_declaration")
                self.assertIn("agenda", pending["context"])
                self.assertTrue(pending["warnings"])

                for changes in ({"temporal": "relevance"}, {"budget_chars": 0}):
                    unassessed = self.decoded(await client.call_tool("recall_memory", {
                        **arguments, **changes}))
                    self.assertNotIn("evidence_assessment", unassessed)

    async def test_indexed_reference_transport_keeps_assessment_and_evidence(self):
        from memory_book.mcp_server import create_server
        outputs = []
        for source_format in ("objects", "indexed"):
            server = create_server(self.database, project="service",
                                   source_format=source_format)
            result = await server.call_tool("recall_memory", {
                "query": "current production retry_limit", "limit": 1,
                "budget_chars": 1200})
            outputs.append(json.loads("".join(part.text for part in result
                                               if part.type == "text")))
        objects, indexed = outputs
        self.assertEqual(objects["context"], indexed["context"])
        self.assertEqual(objects["evidence_assessment"], indexed["evidence_assessment"])
        self.assertEqual(indexed["source_format"], "indexed-v1")
        self.assertEqual({item[0] for item in indexed["source_sessions"]}, {"service"})
        self.assertEqual([item["id"] for item in objects["results"]],
                         [item["id"] for item in indexed["results"]])


if __name__ == "__main__":
    unittest.main()
