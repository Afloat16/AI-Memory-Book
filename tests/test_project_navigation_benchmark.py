"""Protocol/source contracts; no registered-cohort retrieval or optional deps."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import engineering_components as components
from benchmarks import engineering_workflow as engineering
from benchmarks import project_navigation as comparison
from benchmarks import project_navigation_contracts as contracts
from benchmarks import project_navigation_data as data


def tiny_workload():
    source = {"project": "alpha", "session_id": "source", "task_id": "fixture",
              "created_at": "2026-01-01T00:00:00+00:00", "messages": [
                  {"role": "user", "content": "Fixture source"},
                  {"role": "assistant", "content": "memorytoken has original value ALPHA17."}]}
    case = {"id": "fixture-only", "checkpoint": 1, "project": "alpha", "query": "memorytoken",
            "category": "missing_evidence", "required": [], "stale": [], "consumer_family": None,
            "consumer_expected_policy": None}
    return [{"checkpoint": 1, "sessions": [source], "cases": [case]}]


class ProjectNavigationBenchmarkContracts(unittest.TestCase):
    def test_registered_dataset_hash_counts_and_exact_project_collisions(self):
        self.assertEqual(engineering.sha(data.workload()),
                         "589be00eb493fd05fc12dd59050e113a074cd0c2833c059848de50d0ffdfd74b")
        self.assertEqual(data.validate_workload(), {"cases": 80, "answerable": 64, "evidence_spans": 72,
                                                  "fixed_consumer": 40, "missing_global": 8, "missing_neighbor": 8})
        self.assertEqual(len(data.PROJECT_IDS), 8)
        self.assertEqual(len(set(data.PROJECT_IDS)), 8)
        self.assertEqual(set(data.PROJECT_IDS[:3]), {"route-kernel", "route_kernel", "Route-Kernel"})
        self.assertEqual(len(data.directory_queries()), 32)

    def test_neighbor_negative_has_real_foreign_witness_but_no_target_fact(self):
        steps, visible = data.workload(), {}
        for step in steps:
            for source in step["sessions"]:
                visible[(source["project"], source["session_id"])] = source
        originals = engineering.visible_sources(visible)
        cases = [case for step in steps for case in step["cases"] if case["category"] == "missing_evidence_neighbor"]
        self.assertEqual(len(cases), 8)
        for case in cases:
            foreign = case["neighbor_evidence"][0]
            field = foreign["quote"].split("=", 1)[0]
            self.assertNotEqual(foreign["project"], case["project"])
            self.assertIn(foreign["quote"], originals[(foreign["project"], foreign["session_id"], 0)])
            self.assertTrue(all(field not in body for key, body in originals.items() if key[0] == case["project"]))
            self.assertEqual(case["required"], [])

    def test_same_session_replacement_is_project_scoped_in_the_fixed_input(self):
        initial = {(source["project"], source["session_id"]): engineering.original_turn(source)
                   for source in data.workload()[0]["sessions"]}
        replacements = [source for source in data.workload()[1]["sessions"] if source["session_id"] == "active-config"]
        self.assertEqual(len(replacements), 8)
        for index, project in enumerate(data.PROJECT_IDS):
            replacement = next(source for source in replacements if source["project"] == project)
            self.assertIn(f"{data.SYMBOL}={64 + index}", initial[(project, "active-config")])
            self.assertIn(f"{data.SYMBOL}={128 + index}", engineering.original_turn(replacement))

    def test_existing_workload_packer_and_scorer_are_the_same_objects(self):
        self.assertIs(comparison.components.common_pack, components.common_pack)
        self.assertIs(comparison.engineering.score, engineering.score)
        self.assertEqual(comparison.cohort_workload("engineering"), engineering.workload())
        self.assertEqual(comparison.BACKENDS, ("book", "billion", "claude_mem", "basic_memory",
                                              "chroma", "langgraph", "mem0", "reme"))

    def test_reme_receives_only_unchanged_query_exact_scope_and_native_limit(self):
        calls = []

        class Adapter:
            def search(self, query, **kwargs):
                calls.append((query, kwargs))
                return {"hit_ids": [], "records": [], "native_payload": {"native_fields": []}}

        query = "当前 routing.relaxation_limit? - preserve punctuation"
        comparison.native_search("reme", Adapter(), query, "Route-Kernel", {})
        self.assertEqual(calls, [(query, {"project": "Route-Kernel", "limit": 5})])

    def test_setup_failure_remains_failure_and_has_no_successful_zero_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            output, cache = Path(temp) / "out", Path(temp) / "cache"
            with patch.object(comparison, "cohort_workload", return_value=tiny_workload()), \
                 patch.object(comparison, "make_adapter", side_effect=RuntimeError("original native setup failed")):
                report = comparison.run(output, cache, backends=("reme",), repeats=3)
            self.assertEqual(report["summary"], [])
            self.assertFalse(report["integrity_passed"])
            self.assertEqual(report["backend_status"]["reme"]["status"], "failed_or_incomplete")
            self.assertIn("original native setup failed", report["failures"][0]["error"])
            self.assertEqual((output / "raw.jsonl").read_text(), "")

    def test_two_real_outputs_survive_a_third_repeat_failure_without_packed_score(self):
        adapters = []

        class Adapter:
            metadata = {"mode": "protocol fixture, no actual retrieval"}

            def __init__(self, docs):
                self.doc, self.calls, self.closed = docs[0], 0, False

            def search(self, query, project, limit):
                self.calls += 1
                if self.calls == 3:
                    raise RuntimeError("third call failed")
                return {"hit_ids": [self.doc["id"]], "records": [
                    {"id": self.doc["id"], "project": project, "text": self.doc["text"]}],
                    "native_payload": {"upstream_field": "retained"}}

            def close(self):
                self.closed = True

        def make(backend, book, docs, *args):
            adapter = Adapter(docs)
            adapters.append(adapter)
            return adapter

        with tempfile.TemporaryDirectory() as temp:
            output, cache = Path(temp) / "out", Path(temp) / "cache"
            with patch.object(comparison, "cohort_workload", return_value=tiny_workload()), \
                 patch.object(comparison, "make_adapter", side_effect=make):
                report = comparison.run(output, cache, backends=("reme",), repeats=3)
            raw = [json.loads(line) for line in (output / "native.jsonl").read_text().splitlines()]
            self.assertEqual(len(raw), 1)
            self.assertEqual(len(raw[0]["samples"]), 2)
            self.assertEqual(raw[0]["samples"][0]["native"]["native_payload"], {"upstream_field": "retained"})
            self.assertEqual((output / "raw.jsonl").read_text(), "")
            self.assertFalse(report["integrity_passed"])
            self.assertTrue(adapters[0].closed)

    def test_unsupported_scope_argument_cannot_be_reported_as_a_working_guard(self):
        class Unsupported:
            def read(self, page_id, limit):
                return {"content": "foreign source"}

        row = contracts.execute_probe("guard", "wrong_book", {}, lambda probe: contracts.wrong_book(
            probe, Unsupported(), "alpha", {"project": "beta", "page_id": "p-beta"}, "page"))
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["calls"][0]["error_type"], "TypeError")
        self.assertEqual(row["checks"][0]["check"], "same_book_control_supported_and_readable")

    def test_metadata_contract_does_not_treat_question_titles_as_source_bodies(self):
        self.assertFalse(contracts.forbidden_body_keys({"entries": [{"title": "Question", "summary": "Question"}]}))
        self.assertTrue(contracts.forbidden_body_keys({"entries": [{"content": "Original answer"}]}))
        self.assertTrue(contracts.forbidden_body_keys({"entries": [{"nested": {"context": "Answer"}}]}))

    def test_original_body_hidden_in_a_summary_is_rejected(self):
        document = {"id": "p1", "project": "alpha", "title": "Configure fixture",
                    "text": "USER: Configure fixture\n\nASSISTANT: Original fixture answer."}

        class IncorrectDirectory:
            def search_directory(self, query, project, offset, limit):
                return {"project": {"id": project}, "match_fields": ["title", "question", "directory"],
                        "total": 1, "next_offset": None, "entries": [{
                            "section_id": "s1", "matched_page_id": "p1", "title": document["title"],
                            "summary": document["text"], "session_id": "active-config",
                            "breadcrumb": [{"id": project}], "source_refs": [{"project": project}]}]}

        request = {"query": "Configure fixture", "project": "alpha", "kind": "title"}
        row = contracts.execute_probe("metadata", "directory", request, lambda probe: contracts.directory_query(
            probe, IncorrectDirectory(), request, {"p1": document}))
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["checks"][-1], {"check": "source_body_not_hidden_in_metadata_strings", "passed": False})

    def test_tiny_directory_roundtrip_uses_public_task_namespace_and_real_read_windows(self):
        from memory_book import MemoryBook

        source = {"project": "contract-scope", "session_id": "active-config", "task_id": data.MAIN_TASK,
                  "created_at": "2026-01-01T00:00:00+00:00", "messages": [
                      {"role": "user", "content": "Read this separate contract fixture"},
                      {"role": "assistant", "content": "Independent roundtrip original evidence. " * 5}]}
        source_id = (source["project"], source["session_id"], 0)
        with tempfile.TemporaryDirectory() as temp, MemoryBook(Path(temp) / "fixture.db") as book:
            book.ingest(source)
            addresses = {}
            row = contracts.execute_probe("tiny-roundtrip", "roundtrip", {}, lambda probe: contracts.directory_roundtrip(
                probe, book, source["project"], {source_id: engineering.original_turn(source)}, addresses))
            self.assertEqual(row["status"], "passed", row.get("error"))
            self.assertIn(source["project"], addresses)
            self.assertGreater(sum(call["method"] == "read_turn" for call in row["calls"]), 1)


if __name__ == "__main__":
    unittest.main()
