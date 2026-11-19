"""Delivery-level declaration checks, including conservative abstentions."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.cli import main
from memory_book.mcp_server import recall_payload


def source(sid, content, date="2020-01-01T00:00:00Z", project="engine"):
    return {"project": project, "session_id": sid, "task_id": "limits",
            "task_title": "Production limits", "title": "Configuration",
            "created_at": date, "messages": [{"role": "assistant", "content": content}]}


class RequiredFieldsTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn")
        self.addCleanup(self.book.close)
        self.book.ingest(source("old", "Production retry_limit=30."))
        self.book.ingest(source("new", "Production retry_limit=12.", "2021-01-01T00:00:00Z"))

    def recall(self, fields=None, **kwargs):
        return self.book.recall("current production retry_limit", project="engine",
                                required_fields=fields, **kwargs)

    def test_default_unchanged_and_strict_cache_is_separate(self):
        normal = self.recall()
        strict = self.recall(["retry_limit"])
        self.assertNotIn("evidence_gate", normal)
        self.assertEqual(strict["context"], normal["context"])
        self.assertEqual(strict["evidence_gate"]["status"], "supported")
        self.assertFalse(strict["cache_hit"])
        self.assertTrue(self.recall(["retry_limit"])["cache_hit"])
        self.assertNotIn("_support", strict["temporal"]["evidence_assessment"])
        self.assertNotIn("_required_fields", strict["temporal"])

    def test_missing_requested_field_withholds_related_context(self):
        self.assertTrue(self.recall()["context"])
        result = self.recall(["retry_limit", "unrecorded_timeout"])
        self.assertEqual(result["context"], "")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["context_chars"], 0)
        self.assertEqual(result["estimated_tokens"], 0)
        self.assertEqual(result["evidence_gate"]["missing_fields"], ["unrecorded_timeout"])
        self.assertGreater(result["candidate_count"], 0)
        self.assertTrue(result["evidence_gate"]["withheld_page_ids"])

    def test_same_timestamp_conflict_is_not_reported_supported(self):
        self.book.ingest(source("conflict", "Production retry_limit=99.", "2021-01-01T00:00:00Z"))
        result = self.recall(["retry_limit"])
        self.assertEqual(result["context"], "")
        self.assertEqual(result["evidence_gate"]["reason"], "conflicting_declarations")

    def test_all_fields_must_be_delivered_in_complete_pages(self):
        self.book.ingest(source("lease", "Production lease_window=18.", "2021-01-02T00:00:00Z"))
        query = "current production retry_limit lease_window"
        complete = self.book.recall(query, project="engine", required_fields=["retry_limit", "lease_window"])
        self.assertEqual(complete["evidence_gate"]["status"], "supported")
        one = self.book.recall(query, project="engine", limit=1,
                               required_fields=["retry_limit", "lease_window"])
        self.assertEqual(one["evidence_gate"]["status"], "abstained")
        self.assertEqual(one["context"], "")
        tiny = self.recall(["retry_limit"], budget_chars=0)
        self.assertEqual(tiny["evidence_gate"]["status"], "abstained")

    def test_historical_and_qualified_names_cannot_borrow_support(self):
        historical = self.recall(["retry_limit"], temporal="relevance")
        self.assertEqual(historical["evidence_gate"]["reason"], "current_declaration_required")
        qualified = self.recall(["worker.retry_limit"])
        self.assertEqual(qualified["evidence_gate"]["status"], "abstained")

    def test_foreign_evidence_cannot_supply_missing_field(self):
        self.book.ingest(source("foreign", "Production retry_limit=99. Production lease_window=80.",
                                "2025-01-01T00:00:00Z", project="engine-copy"))
        result = self.recall(["retry_limit", "lease_window"])
        self.assertEqual(result["evidence_gate"]["status"], "abstained")
        self.assertEqual(result["context"], "")

    def test_original_replacement_and_delete_invalidate_gate(self):
        self.assertEqual(self.recall(["retry_limit"])["evidence_gate"]["status"], "supported")
        self.book.delete_session("engine", "old")
        self.book.ingest(source("new", "Production retry_limit remains on the agenda. No value was decided.",
                                "2022-01-01T00:00:00Z"))
        self.assertEqual(self.recall(["retry_limit"])["evidence_gate"]["status"], "abstained")
        self.book.delete_session("engine", "new")
        self.assertEqual(self.recall(["retry_limit"])["evidence_gate"]["status"], "abstained")

    def test_quoted_and_conditional_values_are_not_supported_declarations(self):
        for body in ('The example says "Production wait_limit=18."',
                     'If staging is active, Production wait_limit=18.',
                     'Production wait_limit remains on the agenda. No value was decided.'):
            with self.subTest(body=body), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("unconfirmed", body))
                result = book.recall("current production wait_limit", project="engine",
                                     required_fields=["wait_limit"])
                self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_mcp_compact_and_indexed_preserve_gate(self):
        result = self.recall(["unrecorded_timeout"])
        for fmt in ("objects", "indexed"):
            for details in (False, True):
                payload = recall_payload(result, details=details, source_format=fmt)
                self.assertEqual(payload["evidence_gate"], result["evidence_gate"])
                self.assertEqual(payload["context"], "")

    def test_scope_mismatch_never_borrows_a_related_value(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("staging", "Staging lease_duration=12."))
            result = book.recall("current production lease_duration", project="engine",
                                 required_fields=["lease_duration"])
            self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_conditional_or_extra_scope_prefixes_are_not_discarded(self):
        for prefix in ("Not", "Hypothetical", "If", "Example", "Unapproved", "Revoked", "Unknown"):
            with self.subTest(prefix=prefix), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("not-a-decision", prefix + " Production wait_limit=99."))
                result = book.recall("current production wait_limit", project="engine",
                                     required_fields=["wait_limit"])
                self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_overlapping_field_groups_are_checked_for_conflict(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("both", "Production retry_limit=12. Production lease_window=18."))
            book.ingest(source("one", "Production retry_limit=99."))
            result = book.recall("current production retry_limit lease_window", project="engine",
                                 required_fields=["retry_limit", "lease_window"])
            self.assertEqual(result["evidence_gate"]["reason"], "conflicting_declarations")
            self.assertEqual(result["context"], "")

    def test_cross_sentence_quotation_revocation_and_unknown_prose_are_unconfirmed(self):
        for body in ('The review says “\nProduction wait_limit=99.\n”',
                     'A hypothetical example follows:\nProduction wait_limit=99.',
                     'Production wait_limit=99. This decision was revoked.',
                     'Production wait_limit=99. Do not use this value.',
                     'Production wait_limit=99. 未确认此配置。'):
            with self.subTest(body=body), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("unconfirmed", body))
                result = book.recall("current production wait_limit", project="engine",
                                     required_fields=["wait_limit"])
                self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_later_unclassified_revocation_blocks_an_older_declaration(self):
        self.book.ingest(source("revoked", "Production retry_limit was revoked. No new value was selected.",
                                "2022-01-01T00:00:00Z"))
        result = self.recall(["retry_limit"])
        self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_ambiguous_environment_is_not_inferred_from_a_bare_field(self):
        self.book.ingest(source("staging", "Staging retry_limit=99.", "2022-01-01T00:00:00Z"))
        result = self.book.recall("current retry_limit", project="engine", required_fields=["retry_limit"])
        self.assertEqual(result["evidence_gate"]["status"], "abstained")

    def test_only_latest_per_field_can_supply_complete_returned_support(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("both", "Production retry_limit=12. Production lease_window=18."))
            book.ingest(source("one", "Production retry_limit=99.", "2021-01-01T00:00:00Z"))
            result = book.recall("current production retry_limit lease_window", project="engine",
                                 required_fields=["retry_limit", "lease_window"])
            self.assertEqual(result["evidence_gate"]["status"], "supported")
            pages = {p["id"]: p for p in result["results"]}
            for page_id in result["evidence_gate"]["supporting_page_ids"]["retry_limit"]:
                self.assertIn("retry_limit=99", pages[page_id]["text"])

    def test_invalid_fields_fail_before_retrieval(self):
        for fields in ([], "retry_limit", [""], [False], ["retry limit"], ["x..y"], ["a"] * 17):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.recall(fields)
        with self.assertRaisesRegex(ValueError, "explicit project"):
            self.book.recall("current retry_limit", required_fields=["retry_limit"])

    def test_cli_reports_withheld_context_and_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = str(Path(temporary) / "memory.db")
            with MemoryBook(database, segmentation="turn") as book:
                book.ingest(source("value", "Production retry_limit=12."))
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(["--db", database, "recall", "current production retry_limit",
                               "--project", "engine", "--require-field", "not_recorded", "--json"])
            self.assertEqual(status, 0, errors.getvalue())
            result = json.loads(output.getvalue())
            self.assertEqual(result["evidence_gate"]["status"], "abstained")
            self.assertEqual(result["context"], "")


if __name__ == "__main__":
    unittest.main()
