"""Protocol integrity tests; no optional memory packages or model downloads."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import engineering_components as components
from benchmarks import memory_systems
from benchmarks.competitors.memory_systems import (
    BACKENDS, PythonComponent, sanitized_environment, stable_native,
    validate_documents, validate_response,
)


def document(identity="p1", project="alpha", text="Original memorytoken source."):
    return {"id": identity, "project": project, "title": "Original title", "text": text,
            "created_at": "2026-01-01T00:00:00+00:00",
            "source_refs": [{"project": project, "session_id": "session", "turn_index": 0,
                             "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text)}]}


def native(doc):
    return {"hit_ids": [doc["id"]], "records": [
        {"id": doc["id"], "project": doc["project"], "text": doc["text"]}],
        "native_payload": {"untouched": "upstream fields"}}


class MemorySystemsContracts(unittest.TestCase):
    def test_original_identity_scope_and_body_are_all_authenticated(self):
        doc = document()
        lookup = validate_documents([doc, document("p2", "other")])
        value = native(doc)
        self.assertEqual(validate_response(value, lookup, "alpha"), ["p1"])
        corruptions = [
            {"id": "p2", "project": "alpha", "text": doc["text"]},
            {"id": "p1", "project": "other", "text": doc["text"]},
            {"id": "p1", "project": "alpha", "text": "Paraphrased or changed source"},
        ]
        for record in corruptions:
            with self.subTest(record=record), self.assertRaises(ValueError):
                validate_response({**value, "records": [record]}, lookup, "alpha")
        with self.assertRaises(ValueError):
            validate_response(native(lookup["p2"]), lookup, "alpha")

    def test_unmapped_duplicates_and_over_limit_fail_instead_of_being_filtered(self):
        docs = [document(f"p{i}") for i in range(6)]
        lookup = validate_documents(docs)
        for ids in (["unknown"], ["p0", "p0"], [f"p{i}" for i in range(6)]):
            response = {"hit_ids": ids, "records": [
                {"id": i, "project": "alpha", "text": docs[0]["text"]} for i in ids]}
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_response(response, lookup, "alpha")
        with self.assertRaises(ValueError):
            validate_documents([docs[0], docs[0]])

    def test_valid_empty_native_response_is_not_an_exception(self):
        self.assertEqual(validate_response({"hit_ids": [], "records": [], "native_payload": {}},
                                           {"p1": document()}, "alpha"), [])

    def test_only_measurements_are_removed_from_stability_identity(self):
        left = {"search_ms": 1.0, "bridge_ms": 2.0,
                "native_payload": {"distance": .25, "text": "old source", "created_at": "date"}}
        right = copy.deepcopy(left)
        right.update(search_ms=99.0, bridge_ms=100.0)
        self.assertEqual(stable_native(left), stable_native(right))
        for key, value in (("distance", .1), ("text", "different source"), ("created_at", "other")):
            changed = copy.deepcopy(right)
            changed["native_payload"][key] = value
            self.assertNotEqual(stable_native(left), stable_native(changed))

    def test_secret_environment_and_personal_configuration_are_not_inherited(self):
        with tempfile.TemporaryDirectory() as temp:
            state, cache = Path(temp) / "state", Path(temp) / "cache"
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret", "ANTHROPIC_API_KEY": "test-secret",
                                         "MEM0_API_KEY": "test-secret", "PYTHONPATH": "/private/code",
                                         "BASIC_MEMORY_CONFIG_DIR": "/private/config"}):
                env = sanitized_environment(state, cache)
            for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MEM0_API_KEY", "HOME"):
                self.assertNotIn(key, env)
            self.assertEqual(env["BASIC_MEMORY_CONFIG_DIR"], str(state / "basic-config"))
            self.assertEqual(env["MEM0_DIR"], str(state / "mem0-config"))
            self.assertEqual(env["MEM0_TELEMETRY"], "false")
            self.assertNotEqual(env["PYTHONPATH"], "/private/code")

    def test_unchanged_common_packer_never_truncates_or_supplements_native_candidates(self):
        short, large = document(), document("p2", text="A" * 1000)
        lookup = {short["id"]: short, large["id"]: large}
        packed = components.common_pack(["p2", "p1"], lookup, "alpha", 200)
        self.assertEqual([hit["id"] for hit in packed["results"]], ["p1"])
        self.assertEqual(packed["results"][0]["text"], short["text"])
        self.assertEqual(packed["omitted_for_budget"], ["p2"])
        self.assertLessEqual(len(packed["context"]), 200)
        self.assertEqual(components.common_pack([], lookup, "alpha", 200)["results"], [])

    def test_native_query_and_scope_are_forwarded_without_gold_or_rewriting(self):
        calls = []

        class Adapter:
            def search(self, query, **kwargs):
                calls.append((query, kwargs))
                return {"hit_ids": [], "records": [], "native_payload": {}}

        original = "当前 XMLParser / old decision? - keep punctuation"
        memory_systems.native_search("basic_memory", Adapter(), original, "alpha", {})
        self.assertEqual(calls, [(original, {"project": "alpha", "limit": 5})])

    def test_partial_execution_is_not_scored_as_empty_success(self):
        session = {"project": "alpha", "session_id": "s", "created_at": "2026-01-01T00:00:00Z",
                   "messages": [{"role": "user", "content": "memorytoken"},
                                {"role": "assistant", "content": "Original evidence."}]}
        step = {"checkpoint": 1, "sessions": [session], "cases": [
            {"id": "protocol-only", "category": "missing_evidence", "project": "alpha",
             "query": "memorytoken", "required": [], "stale": [], "consumer_family": None}]}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with patch.object(memory_systems.workflow, "workload", return_value=[step]), \
                 patch.object(memory_systems, "make_adapter", side_effect=RuntimeError("native setup failed")):
                report = memory_systems.run(output, Path(temp) / "cache", backends=("basic_memory",), repeats=1)
            self.assertEqual(report["summary"], [])
            self.assertEqual(report["backend_status"]["basic_memory"]["status"], "failed_or_incomplete")
            self.assertFalse(report["integrity_passed"])
            self.assertEqual(len(report["failures"]), 1)
            self.assertIn("native setup failed", report["failures"][0]["error"])
            self.assertEqual((output / "raw.jsonl").read_text(), "")

    def test_old_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "report.json").write_text('{"retained": true}')
            with self.assertRaises(ValueError):
                memory_systems.fresh_output(path)
            self.assertEqual(json.loads((path / "report.json").read_text()), {"retained": True})

    def test_registered_defaults_keep_both_budgets_and_six_external_projects(self):
        self.assertEqual(len(BACKENDS), 7)
        self.assertEqual(set(BACKENDS), {"book", "billion", "claude_mem", "basic_memory",
                                         "chroma", "langgraph", "mem0"})
        self.assertIs(memory_systems.components.common_pack, components.common_pack)
        self.assertEqual(memory_systems.run.__kwdefaults__["budgets"], (1200, 2400))


if __name__ == "__main__":
    unittest.main()
