"""Protocol guards for the new four-component comparison; no scored engine run."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import engineering_open_source_2400 as runner


def document(identity="one", project="routing-online"):
    text = "USER: Choose a policy\n\nASSISTANT: edge_policy=reject_negative."
    return {"id": identity, "project": project, "title": "Choose a policy", "text": text,
            "created_at": "2026-01-01T09:00:00+00:00",
            "source_refs": [{"project": project, "session_id": identity, "turn_index": 0,
                             "turn_start": 0, "turn_end": len(text)}]}


def tiny_workload():
    steps = []
    for checkpoint in (1, 2):
        session = {"project": "routing-online", "session_id": f"source-{checkpoint}",
                   "task_id": "routing", "title": "Choose a policy", "task_title": "routing",
                   "created_at": f"2026-0{checkpoint}-01T09:00:00+00:00",
                   "messages": [{"role": "user", "content": "Choose a policy"},
                                {"role": "assistant", "content": "edge_policy=reject_negative."}]}
        case = {"id": f"case-{checkpoint}", "project": "routing-online", "query": "missing fact",
                "checkpoint": checkpoint, "category": "missing_evidence", "required": [], "stale": [],
                "consumer_family": None, "consumer_expected_policy": None}
        steps.append({"checkpoint": checkpoint, "sessions": [session], "cases": [case]})
    return steps


class FakeEngine:
    def __init__(self, backend, documents, events, *, invalid=False, bad_read=False):
        self.backend, self.documents, self.events = backend, documents, events
        self.invalid, self.bad_read = invalid, bad_read
        self.metadata = {"name": backend}
        self._by_page_id = {f"native-{i}": doc["id"] for i, doc in enumerate(documents)}
        self._locations = {doc["id"]: (doc["project"], f"pages/{doc['id']}.md") for doc in documents}
        self.calls = 0

    def recall(self, query, **options):
        self.events.append(("search", self.backend))
        return {"results": [{"id": doc["id"]} for doc in self.documents[:5]], "latency_ms": 1.0}

    def search(self, query, **options):
        self.events.append(("search", self.backend))
        self.calls += 1
        docs = self.documents[:5]
        if self.backend == "billion-context":
            return {"results": [{"ref": "unknown" if self.invalid else doc["id"]} for doc in docs],
                    "search_ms": 0.1, "bridge_ms": 0.2}
        ids = [doc["id"] for doc in docs]
        if self.backend == "claude-mem-fts":
            return {"hit_ids": ids, "native_payload": [{"id": i, "project": doc["project"],
                    "title": doc["title"], "text": doc["text"]} for i, doc in enumerate(docs)],
                    "search_ms": 0.1, "bridge_ms": 0.2, "native_cpu_user_us": self.calls}
        return {"hit_ids": ids, "results": [{"id": f"native-{i}", "project": doc["project"],
                "workspace": "benchmark", "snippet": "untrusted truncated preview"} for i, doc in enumerate(docs)],
                "native_payload": {"content": "native MCP envelope"}, "search_ms": 0.1, "bridge_ms": 0.2}

    def read(self, identity):
        self.events.append(("read", self.backend))
        doc = next(doc for doc in self.documents if doc["id"] == identity)
        return {"result": {"body": "corrupted" if self.bad_read else doc["text"], "truncated": False}, "read_ms": .1}

    def close(self):
        self.events.append(("close", self.backend))


class EngineeringOpenSource2400Tests(unittest.TestCase):
    def setUp(self):
        # The archived control runner intentionally accepts only its measured
        # release. These protocol fixtures replace all ranking engines; keep
        # their simulated release explicit when the installed product advances.
        version = patch("memory_book.__version__", "0.4.0")
        version.start()
        self.addCleanup(version.stop)

    def test_control_runner_rejects_another_real_runtime_version(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("memory_book.__version__", "9.9.9"):
            with self.assertRaisesRegex(ValueError, "requires Book v0.4.0"):
                runner.run(Path(directory) / "unused", offline=True)
            self.assertFalse((Path(directory) / "unused").exists())

    def test_all_native_shapes_map_to_source_spans(self):
        doc = document()
        for backend in runner.BACKENDS:
            with self.subTest(backend=backend):
                engine = FakeEngine(backend, [doc], [])
                native = runner.search_component(backend, engine, "policy", doc["project"])
                mapped = runner.map_hits(native, backend, {doc["id"]: doc}, doc["project"])
                self.assertEqual(mapped["hit_ids"], [doc["id"]])
                self.assertEqual(mapped["source_map"][0]["source_refs"], doc["source_refs"])
                packed = runner.shared.common_pack(mapped["hit_ids"], {doc["id"]: doc}, doc["project"], runner.BUDGET)
                self.assertIn(doc["text"], packed["context"])
                self.assertNotIn("untrusted truncated preview", packed["context"])

    def test_native_metadata_keeps_slot_and_cannot_refill_or_become_evidence(self):
        doc = document()
        native = {"hit_ids": [None, "one", None, None, None],
                  "results": [{"id": f"native-{i}", "project": doc["project"], "workspace": "benchmark"} for i in range(5)]}
        mapped = runner.map_hits(native, "ai-memory-hybrid", {"one": doc}, doc["project"])
        self.assertEqual(mapped["native_hit_ids"], native["hit_ids"])
        self.assertEqual(mapped["hit_ids"], ["one"])
        self.assertEqual(len(mapped["source_map"]), 5)
        self.assertEqual(mapped["source_map"][1]["native_rank"], 2)
        native["hit_ids"].append("one")
        native["results"].append({"id": "sixth"})
        with self.assertRaisesRegex(ValueError, "top-five"):
            runner.map_hits(native, "ai-memory-hybrid", {"one": doc}, doc["project"])

    def test_mapping_rejects_unknown_duplicate_and_wrong_scope(self):
        docs = {"one": document(), "other": document("other", "routing-batch")}
        for hits in ([{"ref": "unknown"}], [{"ref": "one"}, {"ref": "one"}], [{"ref": "other"}]):
            with self.assertRaises(ValueError):
                runner.map_hits({"results": hits}, "billion-context", docs, "routing-online")
        native = {"results": [{"id": "metadata", "project": "routing-batch"}], "hit_ids": [None]}
        with self.assertRaisesRegex(ValueError, "project"):
            runner.map_hits(native, "ai-memory-hybrid", docs, "routing-online")
        native["results"][0].update(project="routing-online", workspace="wrong")
        with self.assertRaisesRegex(ValueError, "workspace"):
            runner.map_hits(native, "ai-memory-hybrid", docs, "routing-online")
        with self.assertRaisesRegex(ValueError, "mapping"):
            runner.map_hits({"results": [{"id": "one"}], "hit_ids": []}, "ai-memory-hybrid", docs, "routing-online")

    def test_native_source_body_checks_do_not_accept_only_a_preview(self):
        doc = document()
        native = FakeEngine("claude-mem-fts", [doc], []).search("policy")
        native["native_payload"][0]["text"] = "fabricated"
        with self.assertRaisesRegex(ValueError, "original supplied source"):
            runner.map_hits(native, "claude-mem-fts", {"one": doc}, doc["project"])
        runner.validate_native_read({"result": {"body": doc["text"], "truncated": False}}, doc)
        for result in ({"body": doc["text"], "truncated": True}, {"body": doc["text"][:-1]},
                       {"body": doc["text"], "project": "another-project"}):
            with self.assertRaises(ValueError):
                runner.validate_native_read({"result": result}, doc)

    def test_search_boundary_passes_only_query_and_fixed_options(self):
        class Spy:
            def recall(self, *args, **kwargs):
                self.call = (args, kwargs)
                return {}
            search = recall
        for backend in runner.BACKENDS:
            spy = Spy()
            runner.search_component(backend, spy, "query string", "routing-online")
            args, options = spy.call
            self.assertEqual(args, ("query string",))
            self.assertEqual(options["project"], "routing-online")
            self.assertEqual(options["limit"], 5)
            self.assertNotIn("required", options)
            self.assertNotIn("consumer_expected_policy", options)
            if backend == "book":
                self.assertEqual(options, {"project": "routing-online", "limit": 5, "budget_chars": 100000,
                                           "use_cache": False, "coverage": False})

    def test_setup_does_not_pass_gold_or_source_annotations_to_native_adapters(self):
        doc = {**document(), "required": "forbidden gold", "consumer_expected_policy": "forbidden label"}
        for backend, class_name in (("claude-mem-fts", "ClaudeMemFTS"), ("ai-memory-hybrid", "AiMemoryNative"),
                                    ("billion-context", "BillionKernel")):
            with patch.object(runner, class_name) as constructor:
                runner.open_component(backend, [doc], Path("db"), Path("state"), runner.DEFAULT_CACHES,
                                      runner.DEFAULT_LOCKS, "node", True)
                actual = constructor.call_args.args[0]
                self.assertEqual(set(actual[0]), {"id", "project", "title", "text", "created_at"})
                self.assertTrue(constructor.call_args.kwargs["offline"])
                if backend == "ai-memory-hybrid":
                    self.assertEqual(constructor.call_args.kwargs["retrieval"], "hybrid")

    def run_fake(self, output, events, *, invalid=False, bad_read=False, change_artifacts=False):
        identities = {}
        def factory(backend, documents, *args):
            events.append(("open", backend))
            return FakeEngine(backend, documents, events, invalid=invalid, bad_read=bad_read)
        def artifacts(backend, *args):
            identities[backend] = identities.get(backend, 0) + 1
            return {"sha256": str(identities[backend]) if change_artifacts else backend}
        with patch.object(runner.workflow, "workload", return_value=tiny_workload()), \
                patch.object(runner, "open_component", side_effect=factory), \
                patch.object(runner, "artifact_identity", side_effect=artifacts):
            return runner.run(output, offline=True)

    def test_lifecycle_rotates_engines_preserves_every_response_and_delays_reads(self):
        events = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            report = self.run_fake(output, events)
            self.assertEqual(report["status"], "completed", report.get("error"))
            self.assertTrue(report["integrity_passed"])
            self.assertEqual(report["native_search_calls"], 2 * 4 * 3)
            self.assertEqual(report["completed_query_backend_pairs"], 2 * 4)
            native = [json.loads(line) for line in (output / "native.jsonl").read_text().splitlines()]
            rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
            self.assertEqual(len(native), 24)
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(row["repeat_outputs_equal"] for row in rows))
            # CPU measurements are preserved but are not mistaken for changed evidence.
            self.assertTrue(all(not row["repeat_native_outputs_equal"] for row in rows if row["backend"] == "claude-mem-fts"))
            for backend in runner.BACKENDS:
                self.assertEqual(events.count(("open", backend)), 2)
                self.assertEqual(events.count(("close", backend)), 2)
            first_read = next(i for i, event in enumerate(events) if event[0] == "read")
            self.assertEqual(sum(event[0] == "search" for event in events[:first_read]), 12)
            for checkpoint in (1, 2):
                for repetition in range(3):
                    group = [row for row in native if row["checkpoint"] == checkpoint and row["repetition"] == repetition]
                    self.assertEqual([row["backend"] for row in group], list(runner.backend_order(checkpoint, 0, repetition)))
            # Missing-answer queries are retained in the quality denominator.
            self.assertTrue(all(cell["missing_evidence_nonempty_cases"] == 2 for cell in report["summary"]))
            self.assertEqual(report["settings"]["budget_chars"], 2400)
            for row in rows:
                self.assertLessEqual(len(row["response"]["context"]), 2400)
            with self.assertRaisesRegex(ValueError, "fresh empty"):
                runner.run(output, offline=True)

    def test_invalid_response_is_saved_and_partial_run_cannot_pass(self):
        events = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            report = self.run_fake(output, events, invalid=True)
            self.assertEqual(report["status"], "failed")
            self.assertFalse(report["integrity_passed"])
            native = [json.loads(line) for line in (output / "native.jsonl").read_text().splitlines()]
            self.assertEqual(native[-1]["native"]["results"][0]["ref"], "unknown")
            self.assertIn("validation_error", native[-1])
            self.assertTrue((output / "report.json").exists())
            for backend in runner.BACKENDS:
                self.assertEqual(events.count(("close", backend)), 1)

    def test_bad_native_read_and_changed_execution_inputs_fail_integrity(self):
        for options in ({"bad_read": True}, {"change_artifacts": True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "run"
                report = self.run_fake(output, [], **options)
                self.assertFalse(report["integrity_passed"])
                if options.get("bad_read"):
                    self.assertEqual(report["status"], "failed")
                    read = json.loads((output / "reads.jsonl").read_text().splitlines()[0])
                    self.assertEqual(read["native"]["result"]["body"], "corrupted")
                else:
                    self.assertEqual(report["status"], "completed_with_integrity_failures")
                    self.assertFalse(report["integrity_checks"]["executed_artifacts_unchanged"])

    def test_setup_and_artifact_errors_close_started_engines_and_keep_original_failure(self):
        for failure in ("setup", "artifact"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                events = []
                def factory(backend, documents, *args):
                    if failure == "setup" and backend == "claude-mem-fts":
                        raise RuntimeError("original setup failure")
                    events.append(("open", backend))
                    return FakeEngine(backend, documents, events)
                def artifacts(backend, *args):
                    if failure == "artifact":
                        raise RuntimeError("original artifact failure")
                    return {"sha256": backend}
                output = Path(directory) / "run"
                with patch.object(runner.workflow, "workload", return_value=tiny_workload()), \
                        patch.object(runner, "open_component", side_effect=factory), \
                        patch.object(runner, "artifact_identity", side_effect=artifacts):
                    report = runner.run(output, offline=True)
                self.assertEqual(report["status"], "failed")
                self.assertFalse(report["integrity_passed"])
                self.assertEqual(report["error"]["message"], f"original {failure} failure")
                self.assertEqual(events.count(("close", "book")), 1)
                self.assertEqual(report["native_search_calls"], 0)
                self.assertTrue((output / "checkpoint-1.json").exists())

    def test_pairwise_keeps_losses_mixed_and_missing_answer_cases(self):
        case = {"case_id": "case", "project": "routing-online", "checkpoint": 1, "category": "update", "query": "policy"}
        left = {"answerable": True, "complete_evidence": True, "matched_evidence": 2, "fixed_consumer": {"all_passed": False}}
        right = {"answerable": True, "complete_evidence": False, "matched_evidence": 1, "fixed_consumer": {"all_passed": True}}
        result = runner.pairwise([{**case, "backend": "book", "score": left},
                                  {**case, "backend": "ai-memory-hybrid", "score": right}])["ai-memory-hybrid"]
        self.assertEqual(result["mixed_cases"], 1)
        self.assertEqual(result["metrics"]["complete_evidence"], {"book_win": 1})
        self.assertEqual(result["metrics"]["fixed_consumer"], {"book_loss": 1})
        empty = {"answerable": False, "complete_evidence": False, "matched_evidence": 0}
        result = runner.pairwise([{**case, "backend": "book", "score": empty},
                                  {**case, "backend": "ai-memory-hybrid", "score": empty}])["ai-memory-hybrid"]
        self.assertEqual(result["metrics"]["complete_evidence"], {"not_applicable": 1})

    def test_preconditions_and_evaluator_closure(self):
        identity = runner.source_identity(runner.DEFAULT_LOCKS)
        self.assertIn("benchmarks/engineering_workflow.py", identity["files"])
        self.assertIn("benchmarks/engineering_components.py", identity["files"])
        self.assertIn("benchmarks/competitors/claude_mem_bridge.ts", identity["files"])
        self.assertIn("benchmarks/competitors/ai-memory-lock.json", identity["files"])
        with tempfile.TemporaryDirectory() as directory:
            for options in ({"repeats": 2}, {"repeats": True}, {"noise_per_step": True}, {"noise_per_step": 101}):
                with self.assertRaises(ValueError):
                    runner.run(Path(directory) / "unused", **options)
            self.assertFalse((Path(directory) / "unused").exists())


if __name__ == "__main__":
    unittest.main()
