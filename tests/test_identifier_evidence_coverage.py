"""Agent-visible missing evidence, without declaring archive absence or dropping history."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.mcp_server import recall_payload

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def record(text, *, project="workers", session="decision", title="Worker configuration"):
    return {"project": project, "session_id": session, "task_id": "configuration",
            "title": title, "created_at": "2006-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content": text}]}


class IdentifierEvidenceCoverageTests(unittest.TestCase):
    def test_relevance_missing_field_keeps_original_context_and_reports_insufficiency(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("Approved configuration: worker_count=7. This project deploys seven workers."))
            result = book.recall("What approved lease_duration value should this project deploy?", project="workers")
            self.assertEqual(result["temporal"]["resolved"], "relevance")
            self.assertEqual(result["temporal"]["evidence_assessment"]["status"], "not_assessed")
            self.assertIn("worker_count=7", result["context"])
            assessment = result["evidence_coverage"]
            self.assertEqual(assessment["status"], "insufficient_evidence")
            self.assertEqual(assessment["scope"], "returned_excerpts")
            self.assertEqual(assessment["missing_identifiers"], ["lease_duration"])
            self.assertIn("same project", " ".join(result["warnings"]))
            for hit in result["results"]:
                page = book.read(hit["id"], project="workers")
                for ref in hit["source_refs"]:
                    self.assertEqual(ref["project"], "workers")
                    self.assertIn(page["content"][ref["start"]:ref["end"]], hit["text"])

    def test_partial_multi_field_coverage_does_not_claim_a_complete_answer(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Production worker_count=7; deployment remains approved."))
            result = book.recall("current worker_count and lease_duration", project="workers")
            assessment = result["evidence_coverage"]
            self.assertEqual(assessment["missing_identifiers"], ["lease_duration"])
            self.assertEqual(assessment["requested_identifiers"], ["worker_count", "lease_duration"])
            self.assertIn("worker_count=7", result["context"])

    def test_namespaces_word_boundaries_and_private_markers_are_not_erased(self):
        cases = (("cache.timeout", "other.timeout=7"), ("user.id", "user_id=7"),
                 ("a_bc", "ab_c=7"), ("retry_limit", "max_retry_limit=7"),
                 ("_retry_limit", "retry_limit=7"), ("retry_limit", "retry_limit_extra=7"))
        for query, text in cases:
            with self.subTest(query=query, text=text), MemoryBook(":memory:") as book:
                book.ingest(record("Approved worker configuration: " + text))
                result = book.recall("Approved worker configuration " + query, project="workers")
                self.assertTrue(result["context"])
                self.assertEqual(result["evidence_coverage"]["missing_identifiers"], [query])

    def test_whole_snake_camel_and_adjacent_prose_mentions_are_lexical_only(self):
        cases = (("retry_limit", "RetryLimit=7"), ("RetryLimit", "retry_limit=7"),
                 ("retry_limit", "Retry limit is now 7"),
                 ("HTTPPort", "http_port=443"), ("cache.timeout", "Cache.Timeout=7"))
        for query, text in cases:
            with self.subTest(query=query, text=text), MemoryBook(":memory:") as book:
                book.ingest(record("Approved worker configuration: " + text))
                result = book.recall("Approved worker configuration " + query, project="workers")
                assessment = result["evidence_coverage"]
                self.assertEqual(assessment["status"], "identifier_mentions_present")
                self.assertEqual(assessment["missing_identifiers"], [])
                self.assertIn("do not establish", assessment["basis"])

    def test_mention_without_a_value_stays_unconfirmed(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Production lease_duration remains on the agenda. No value was decided."))
            result = book.recall("current production lease_duration", project="workers")
            self.assertEqual(result["evidence_coverage"]["status"], "identifier_mentions_present")
            self.assertEqual(result["temporal"]["evidence_assessment"]["status"], "no_comparable_declaration")
            self.assertIn("No value was decided", result["context"])

    def test_titles_and_foreign_projects_cannot_satisfy_source_coverage(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Approved worker deployment uses seven workers.", title="lease_duration configuration"))
            book.ingest(record("Approved lease_duration=999.", project="workers-copy"))
            scoped = book.recall("Approved lease_duration worker deployment", project="workers")
            self.assertEqual(scoped["evidence_coverage"]["status"], "insufficient_evidence")
            self.assertTrue(scoped["results"])
            for hit in scoped["results"]:
                self.assertTrue(all(ref["project"] == "workers" for ref in hit["source_refs"]))
            foreign = book.recall("Approved lease_duration", project="workers-copy")
            self.assertEqual(foreign["evidence_coverage"]["status"], "identifier_mentions_present")

    def test_separate_original_pages_cannot_be_joined_into_a_field_mention(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("The deployment uses retry.", session="retry-discussion"))
            book.ingest(record("Limit approval remains pending for deployment.", session="limit-discussion"))
            result = book.recall("deployment retry_limit", project="workers")
            self.assertEqual(len(result["results"]), 2)
            self.assertIn("retry", result["context"])
            self.assertIn("Limit", result["context"])
            self.assertEqual(result["evidence_coverage"]["missing_identifiers"], ["retry_limit"])

    def test_empty_budget_reports_only_what_was_returned(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Approved lease_duration=7."))
            empty = book.recall("lease_duration", project="workers", budget_chars=0)
            self.assertEqual(empty["context"], "")
            self.assertEqual(empty["evidence_coverage"]["status"], "insufficient_evidence")
            present = book.recall("lease_duration", project="workers", budget_chars=1200)
            self.assertEqual(present["evidence_coverage"]["status"], "identifier_mentions_present")

    def test_history_keeps_old_evidence_and_uses_the_same_coverage_boundary(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Original lease_duration=7. This historical decision was superseded."))
            for mode in ("auto", "relevance", "current"):
                result = book.recall("original lease_duration", project="workers", temporal=mode)
                self.assertIn("lease_duration=7", result["context"])
                self.assertEqual(result["evidence_coverage"]["status"], "identifier_mentions_present")

    def test_cache_and_source_replacement_reassess_delivered_evidence(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Approved deployment worker_count=7."))
            query = "Approved deployment lease_duration"
            first = book.recall(query, project="workers")
            cached = book.recall(query, project="workers")
            self.assertFalse(first["cache_hit"])
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(first["evidence_coverage"], cached["evidence_coverage"])
            book.ingest(record("Approved deployment lease_duration=7."))
            replaced = book.recall(query, project="workers")
            self.assertFalse(replaced["cache_hit"])
            self.assertEqual(replaced["evidence_coverage"]["status"], "identifier_mentions_present")
            book.delete_session("workers", "decision")
            missing = book.recall(query, project="workers")
            self.assertEqual(missing["evidence_coverage"]["status"], "insufficient_evidence")
            self.assertEqual(missing["context"], "")

    def test_ordinary_words_dates_urls_and_fenced_plain_names_are_not_identifiers(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Worker configuration documentation was approved in 2006."))
            for query in ("What worker configuration was approved?", "worker configuration on 2006-01-01",
                          "worker configuration at https://example.com/a_b", "contact worker@example.com",
                          "worker configuration ```timeout```", "version v0.13.0"):
                with self.subTest(query=query):
                    self.assertNotIn("evidence_coverage", book.recall(query, project="workers"))
            quoted = book.recall("worker configuration `timeout`", project="workers")
            self.assertEqual(quoted["evidence_coverage"]["missing_identifiers"], ["timeout"])

    def test_alternatives_exclusions_and_excessive_names_do_not_create_false_obligations(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Approved retry_limit=7."))
            for query in ("retry_limit or wait_limit", "retry_limit without changing wait_limit",
                          "retry_limit 或 wait_limit", "not retry_limit",
                          " ".join(f"field_{i}" for i in range(33))):
                with self.subTest(query=query):
                    result = book.recall(query, project="workers")
                    self.assertEqual(result["evidence_coverage"]["status"], "not_assessed")
                    self.assertEqual(result["evidence_coverage"]["missing_identifiers"], [])

    def test_both_mcp_projections_keep_the_diagnostic_without_mutating_evidence(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("Approved deployment worker_count=7."))
            result = book.recall("approved deployment lease_duration", project="workers")
            for details in (False, True):
                for format_name in ("objects", "indexed"):
                    payload = recall_payload(result, details=details, source_format=format_name)
                    self.assertEqual(payload["evidence_coverage"], result["evidence_coverage"])
                    self.assertEqual(payload["context"], result["context"])
                    self.assertEqual([hit["id"] for hit in payload["results"]],
                                     [hit["id"] for hit in result["results"]])


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for official SDK checks")
class IdentifierEvidenceCoverageMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_compact_stdio_keeps_relevance_insufficiency_and_scoped_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "memory.db")
            with MemoryBook(database) as book:
                book.ingest(record("Approved deployment worker_count=7."))
            parameters = StdioServerParameters(command=sys.executable, args=[
                "-c", "import sys; from memory_book.mcp_server import serve; "
                "serve(sys.argv[1], project='workers')", database],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                     "PYTHONUNBUFFERED": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as client:
                    await client.initialize()
                    reply = await client.call_tool("recall_memory", {
                        "query": "What approved lease_duration value should this project deploy?"})
                    self.assertFalse(reply.isError, reply)
                    payload = json.loads("".join(part.text for part in reply.content if part.type == "text"))
                    self.assertNotIn("temporal", payload)
                    self.assertEqual(payload["evidence_coverage"]["status"], "insufficient_evidence")
                    self.assertIn("worker_count=7", payload["context"])
                    for hit in payload["results"]:
                        original = await client.call_tool("read_page", {"page_id": hit["id"]})
                        self.assertFalse(original.isError, original)
                        page = json.loads("".join(part.text for part in original.content if part.type == "text"))
                        self.assertTrue(all(ref["project"] == "workers" for ref in page["source_refs"]))


if __name__ == "__main__":
    unittest.main()
