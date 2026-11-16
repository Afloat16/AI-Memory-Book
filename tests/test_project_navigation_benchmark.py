"""Protocol/source contracts; no registered-cohort retrieval or optional deps."""
from __future__ import annotations

import copy
import io
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


def claude_scope_metadata():
    return {"repository": "thedotmack/claude-mem", "commit": comparison.CLAUDE_SCOPE_PIN,
            "package_version": "15.18.1", "fts_integrity_check": True,
            "lock_sha256": comparison.sha_file(comparison.ROOT / "benchmarks/competitors/claude-mem-round2-lock.json")}


def smoke_gate_fixture(folder):
    """Protocol-only records; these are never published as upstream execution."""
    docs = [{"id": f"fixture-{index}", "project": project, "title": "Fixture question",
             "text": "Fixture original body " + project}
            for index, project in enumerate(comparison.SMOKE_PROJECTS[:3])]
    report = {"status": "failed", "backends": {}, "failures": []}
    traces = []
    for backend in comparison.BACKENDS:
        item = {"metadata": claude_scope_metadata() if backend == "claude_mem" else {},
                "status": "failed" if backend == "claude_mem" else "passed", "samples": []}
        report["backends"][backend] = item
        for index, project in enumerate(comparison.SMOKE_PROJECTS):
            own = [doc for doc in docs if doc["project"] == project]
            sample = {"project": project, "query": "memorytoken_alpha", "status": "passed",
                      "hit_ids": [doc["id"] for doc in own]}
            if backend == "claude_mem":
                own = [doc for doc in docs if doc["project"].lower() == project.lower()]
                native = {"hit_ids": [doc["id"] for doc in own], "native_payload": [
                    {key: doc[key] for key in ("title", "project", "text")} for doc in own], "search_ms": 1.0}
                trace_id = f"smoke:claude_mem:{index}"
                trace = {"backend": backend, "checkpoint": "smoke", "case_id": "smoke:" + project,
                         "project": project, "repetition": 0, "trace_id": trace_id, "status": "returned",
                         "request": {"op": "search", "query": "memorytoken_alpha", "project": project, "limit": 5},
                         "response": native, "response_sha256": engineering.sha(native)}
                traces.append(trace)
                sample["transport_trace_ids"] = [trace_id]
                if project in {"scope-a", "Scope-a"}:
                    sample.pop("hit_ids")
                    sample.update(status="failed", error_type="ValueError", error="Native project scope violation")
                    report["failures"].append({"backend": backend, "stage": "smoke", "project": project,
                        "query": "memorytoken_alpha", "error_type": "ValueError", "message": "Native project scope violation",
                        "error": "ValueError: Native project scope violation", "transport_trace_ids": [trace_id]})
                else:
                    sample["native"] = {**native, "bridge_ms": 2.0}
            item["samples"].append(sample)
    folder.mkdir()
    (folder / "documents.json").write_text(json.dumps(docs))
    (folder / "report.json").write_text(json.dumps(report))
    (folder / "transport.jsonl").write_text("".join(json.dumps(row) + "\n" for row in traces))
    return docs, report, traces


class ProjectNavigationBenchmarkContracts(unittest.TestCase):
    def test_transport_observer_returns_the_original_object_and_flushes_after_call(self):
        response = {"hit_ids": ["p1"], "native_payload": [{"text": "original"}], "search_ms": 1.0}

        class Adapter:
            def _request(self, request):
                self.received = request
                return response

        adapter, stream = Adapter(), io.StringIO()
        observer = comparison.TransportObserver(adapter, "smoke", stream)
        observer.begin("fixture", "scope-a", 0)
        request = {"op": "search", "query": "unchanged", "project": "scope-a", "limit": 5}
        actual = adapter._request(request)
        self.assertIs(actual, response)
        self.assertIs(adapter.received, request)
        self.assertEqual(stream.getvalue(), "")
        actual["bridge_ms"] = 2.0
        retained = observer.flush()
        self.assertNotIn("bridge_ms", retained[0]["response"])
        self.assertEqual(json.loads(stream.getvalue())["response"], retained[0]["response"])
        self.assertIs(actual["native_payload"], response["native_payload"])

    def test_known_nocase_failure_is_eligible_only_for_execution_and_stays_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, output = Path(temp) / "smoke", Path(temp) / "gate.json"
            smoke_gate_fixture(folder)
            result = comparison.check_smoke(folder, output)
            self.assertEqual(result["status"], "eligible_with_registered_scope_mismatch")
            self.assertTrue(result["eligible_for_execution"])
            self.assertEqual(result["smoke_status"], "failed")
            self.assertFalse(result["all_smokes_passed"])
            self.assertEqual(len(result["registered_limitations"]), 2)
            self.assertTrue(all(item["quality_success"] is False for item in result["registered_limitations"]))
            with self.assertRaises(FileExistsError):
                comparison.check_smoke(folder, output)

    def test_missing_raw_changed_source_prefix_collision_or_other_error_blocks_execution(self):
        for corruption in ("missing_raw", "changed_source", "prefix_collision", "changed_pin", "other_error", "hidden_failure"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temp:
                folder, output = Path(temp) / "smoke", Path(temp) / "gate.json"
                docs, report, traces = smoke_gate_fixture(folder)
                if corruption == "missing_raw":
                    traces = []
                elif corruption == "changed_source":
                    traces[0]["response"]["native_payload"][-1]["text"] += " altered"
                    traces[0]["response_sha256"] = engineering.sha(traces[0]["response"])
                elif corruption == "prefix_collision":
                    traces[0]["response"]["hit_ids"][-1] = docs[1]["id"]
                    traces[0]["response"]["native_payload"][-1] = {key: docs[1][key] for key in ("title", "project", "text")}
                    traces[0]["response_sha256"] = engineering.sha(traces[0]["response"])
                elif corruption == "changed_pin":
                    report["backends"]["claude_mem"]["metadata"]["commit"] = "different source"
                elif corruption == "other_error":
                    report["failures"].append({"backend": "reme", "stage": "close", "error": "close failed"})
                else:
                    report["failures"] = []
                    report["status"] = "passed"
                (folder / "report.json").write_text(json.dumps(report))
                (folder / "transport.jsonl").write_text("".join(json.dumps(row) + "\n" for row in traces))
                result = comparison.check_smoke(folder, output)
                self.assertEqual(result["status"], "blocked")
                self.assertFalse(result["eligible_for_execution"])

    def test_actual_unchanged_validator_failure_keeps_transport_and_attempts_four_tiny_queries(self):
        from benchmarks.competitors.claude_mem import validate_native_rows

        class IncorrectScopeFixture:
            """Deliberately wrong test transport, not a replacement ranker."""
            metadata = claude_scope_metadata()

            def __init__(self, docs):
                self.docs = {doc["id"]: doc for doc in docs}

            def _request(self, request):
                own = [doc for doc in self.docs.values() if doc["project"].lower() == request["project"].lower()]
                return {"hit_ids": [doc["id"] for doc in own], "native_payload": [
                    {key: doc[key] for key in ("title", "project", "text")} for doc in own], "search_ms": 1.0}

            def search(self, query, project, limit):
                response = self._request({"op": "search", "query": query, "project": project, "limit": limit})
                response["bridge_ms"] = 2.0
                validate_native_rows(response, self.docs, project, limit)
                return response

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as temp:
            output, cache = Path(temp) / "smoke", Path(temp) / "cache"
            with patch.object(comparison, "make_adapter", side_effect=lambda backend, book, docs, *args: IncorrectScopeFixture(docs)):
                report = comparison.self_test(output, cache, backends=("claude_mem",))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(len(report["failures"]), 2)
            item = report["backends"]["claude_mem"]
            self.assertEqual([sample["status"] for sample in item["samples"]], ["failed", "passed", "failed", "passed"])
            traces = [json.loads(line) for line in (output / "transport.jsonl").read_text().splitlines()]
            self.assertEqual(len(traces), 4)
            self.assertNotIn("bridge_ms", traces[0]["response"])
            self.assertEqual(report["failures"][0]["scope_diagnosis"]["foreign_original_records"][0]["project"], "Scope-a")
        steps = tiny_workload()
        foreign = copy.deepcopy(steps[0]["sessions"][0])
        foreign["project"] = "Alpha"
        foreign["messages"][1]["content"] = "memorytoken has a conflicting independent value BETA91."
        steps[0]["sessions"].append(foreign)
        with tempfile.TemporaryDirectory() as temp:
            output, cache = Path(temp) / "run", Path(temp) / "cache"
            with patch.object(comparison, "cohort_workload", return_value=steps), \
                 patch.object(comparison, "make_adapter", side_effect=lambda backend, book, docs, *args:
                              book if backend == "book" else IncorrectScopeFixture(docs)):
                report = comparison.run(output, cache, backends=("book", "claude_mem"))
            self.assertEqual(report["status"], "completed_with_backend_failures")
            self.assertEqual(report["backend_status"]["book"]["status"], "completed")
            self.assertEqual(report["backend_status"]["claude_mem"]["packed_rows"], 0)
            self.assertEqual({row["backend"] for row in report["summary"]}, {"book"})
            self.assertEqual(report["failures"][0]["scope_diagnosis"]["requested_project"], "alpha")
            self.assertEqual(len((output / "transport.jsonl").read_text().splitlines()), 1)

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
