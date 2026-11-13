"""Invented comparator inputs only: no fresh selection, engine or model calls."""
from __future__ import annotations

from contextlib import nullcontext
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.data import Evidence, QueryCase
from scripts import round5_title_reference_fresh_components_v2 as bench


class Counter:
    version = "0.12.0"

    def __init__(self, name="cl100k_base"):
        self.name = name

    def count(self, text):
        return len(text)


def document(identity, text="Alpha fact. Beta fact.", session="s", project="p"):
    return {"id": identity, "title": "Invented notes", "project": project,
        "created_at": "2026-01-01", "text": text,
        "breadcrumb": [{"id": project, "kind": "project"}],
        "source_refs": [{"project": project, "session_id": session, "turn_index": 0,
                         "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text)}]}


def case(identity="invented-000"):
    return QueryCase(identity, "Which invented fact?", "fixture", "p",
                     (Evidence("s", 0, "Alpha fact."), Evidence("s", 0, "Beta fact.")))


def expected_query(value):
    return {"project": value.project, "category": value.category, "required_evidence": len(value.required),
            "input_query": bench.scoring.query_projection(value.query)}


def scored_fixture(identity="invented-000", config=None):
    config = config or bench.CONFIGURATIONS[0]
    item = case(identity)
    docs = {name: document(name) for name in ("a", "b")}
    docs["noise"] = document("noise", "Noise only.", session="noise")
    counters = {name: Counter(name) for name in bench.ENCODINGS}
    response = bench.project_pages(list(docs), docs, config, counters[config["tokenizer"]])
    originals = {("p", "s", 0): "Alpha fact. Beta fact.", ("p", "noise", 0): "Noise only."}
    groups = {identity: {"diagnostic_groups": ["invented"]}}
    return bench.score_projection(item, response, originals, counters, config, groups)


class CommonPackingTests(unittest.TestCase):
    def test_claude_observation_surface_does_not_require_results_key(self):
        docs = {"a": document("a")}
        response = {"hit_ids": ["a"], "native_payload": [{"id": 7, "text": docs["a"]["text"]}],
                    "native_text": None, "search_ms": 1.0, "bridge_ms": 2.0}
        row = bench.search_cost(response, docs, "p", "claude-mem-fts",
            {name: Counter(name) for name in bench.ENCODINGS}, "invented", 0)
        self.assertEqual(row["hit_ids"], ["a"])
        self.assertIsNone(row["search_content_tokens"])

    def test_none_metadata_keeps_native_slots_and_never_refills(self):
        docs = {name: document(name) for name in ("a", "b", "c", "sixth")}
        response = {"hit_ids": [None, "a", None, "b", "c"],
            "results": [{"id": f"native-{i}", "project": "p", "workspace": "benchmark"} for i in range(5)],
            "native_payload": {"content": []}, "native_text": "metadata and snippets",
            "search_ms": 1.0, "bridge_ms": 2.0}
        row = bench.search_cost(response, docs, "p", "ai-memory-hybrid",
            {name: Counter(name) for name in bench.ENCODINGS}, "invented", 0)
        self.assertEqual(row["native_hit_ids"], [None, "a", None, "b", "c"])
        self.assertEqual(row["hit_ids"], ["a", "b", "c"])
        self.assertEqual(row["unmapped_native_hits"], 2)
        packed = bench.project_pages(row["hit_ids"], docs, bench.CONFIGURATIONS[0], Counter())
        self.assertEqual([page["id"] for page in packed["results"]], ["a", "b", "c"])
        self.assertNotIn("sixth", packed["context"])

    def test_sixth_unknown_duplicate_or_foreign_hits_fail(self):
        docs = {name: document(name) for name in ("a", "b", "c", "d", "e", "f")}
        for ids in (["a"] * 2, ["unknown"], ["a", "b", "c", "d", "e", "f"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                bench.reused.component_hits({"hit_ids": ids, "results": [{"ref": name} for name in ids]}, docs, "p", "billion-context")
        with self.assertRaises(ValueError):
            bench.reused.component_hits({"hit_ids": ["a"], "results": [{"ref": "a"}]}, docs, "other", "billion-context")

    def test_common_character_and_token_caps_admit_whole_later_page(self):
        docs = {"large": document("large", "x" * 100), "small": document("small", "café 缓存")}
        before = copy.deepcopy(docs)
        config = {"tokenizer": "cl100k_base", "budget_tokens": 60, "budget_chars": 60}
        packed = bench.project_pages(["large", "small"], docs, config, Counter())
        self.assertEqual([page["id"] for page in packed["results"]], ["small"])
        self.assertEqual(packed["results"][0]["text"], docs["small"]["text"])
        self.assertEqual(packed["results"][0]["source_refs"], docs["small"]["source_refs"])
        self.assertEqual(docs, before)
        self.assertLessEqual(len(packed["context"]), 60)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[benchmark] for exact reference tokenizer fixtures")
    def test_registered_six_cells_use_real_reference_counts(self):
        docs = {"a": document("a", "café 缓存 👩🏽‍💻 " * 100), "b": document("b", "The result is amber.")}
        counters = {name: bench.TokenCounter(name) for name in bench.ENCODINGS}
        for config in bench.CONFIGURATIONS:
            with self.subTest(config=config):
                packed = bench.project_pages(list(docs), docs, config, counters[config["tokenizer"]])
                self.assertLessEqual(counters[config["tokenizer"]].count(packed["context"]), config["budget_tokens"])
                self.assertLessEqual(len(packed["context"]), 8000)
                self.assertTrue(all(page["text"] == docs[page["id"]]["text"] for page in packed["results"]))

    def test_native_read_requires_exact_complete_body(self):
        doc = document("a")
        counters = {name: Counter(name) for name in bench.ENCODINGS}
        value = {"result": {"body": doc["text"], "truncated": False}, "read_ms": 1.5}
        measured = bench.read_cost(value, "a", doc, counters)
        self.assertEqual(measured["body_sha256"], hashlib.sha256(doc["text"].encode()).hexdigest())
        for change in ({"body": "partial"}, {"body": doc["text"], "truncated": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                bench.read_cost({"result": change, "read_ms": 1.5}, "a", doc, counters)
        with self.assertRaises(ValueError):
            bench.read_cost({**value, "read_ms": float("nan")}, "a", doc, counters)


class MetricAndScheduleTests(unittest.TestCase):
    def test_later_duplicate_support_pages_both_count(self):
        row = scored_fixture()
        self.assertEqual([page["annotations"] for page in row["annotated_pages"]], [[0, 1], [0, 1], []])
        self.assertEqual(row["annotated_page_hits"], 2)
        self.assertEqual(row["annotated_page_precision"], 2 / 3)
        bench.verify_projection(row, bench.CONFIGURATIONS[0], expected_query(case()))
        forged = copy.deepcopy(row)
        forged["annotated_page_hits"] = 1
        forged["annotated_page_precision"] = 1 / 3
        with self.assertRaises(ValueError):
            bench.verify_projection(forged, bench.CONFIGURATIONS[0], expected_query(case()))

    def test_wrong_query_source_budget_and_mrr_fail(self):
        original = scored_fixture()
        changes = ({"input_query": bench.scoring.query_projection("different")},
                   {"source_span_errors": 1}, {"returned_characters": 8001},
                   {"context_tokens": {name: 99999 for name in bench.ENCODINGS}},
                   {"reciprocal_rank": 0.5}, {"result_ids": ["replacement"]})
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                bench.verify_projection({**copy.deepcopy(original), **change}, bench.CONFIGURATIONS[0], expected_query(case()))

    def test_three_repetitions_keep_same_invented_universe(self):
        ids = [f"invented-{i:03d}" for i in range(512)]
        schedule = bench.search_schedule(ids)
        self.assertEqual(len(schedule), 1536)
        self.assertEqual(schedule, bench.search_schedule(ids))
        for repetition in range(3):
            rows = [identity for repeat, identity in schedule if repeat == repetition]
            self.assertEqual(len(rows), len(set(rows)), 512)
            self.assertEqual(set(rows), set(ids))
        self.assertNotEqual(schedule[:512], schedule[512:1024])

    def test_paired_losses_are_retained_and_no_quality_gate_is_invented(self):
        good = scored_fixture()
        bad = copy.deepcopy(good)
        bad.update(complete=False, matched_evidence=0, evidence_ranks=[None, None], reciprocal_rank=0.0,
                   annotated_page_hits=0, annotated_page_precision=0.0)
        for page in bad["annotated_pages"]:
            page["annotations"] = []
        result = bench.paired_quality({"invented-000": good}, {"invented-000": bad})
        self.assertEqual(result["complete_loss_ids"], ["invented-000"])
        self.assertEqual(result["complete_gain_ids"], [])
        self.assertLess(result["deltas"]["complete_evidence_rate"], 0)
        self.assertNotIn("passed", result)


class PublicationAndFailureTests(unittest.TestCase):
    def test_ticket_is_consumed_before_selected_content_and_cannot_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comparison = {"state": "private", "output": "public"}
            with patch.object(bench, "ROOT", root):
                location = bench.paths(comparison, 0)
            location["ticket"].parent.mkdir(parents=True)
            location["ticket"].write_bytes(b"one-use-invented-ticket")
            intent = {"ticket_sha256": bench.sha(location["ticket"])}
            bench.native.consume_ticket(location, intent)
            self.assertTrue(location["state"].is_dir())
            self.assertFalse(location["ticket"].exists())
            with self.assertRaises(ValueError):
                bench.native.consume_ticket(location, intent)

    def test_failed_final_validation_retains_raw_ledger_and_failed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(bench, "ROOT", root):
                location = bench.paths({"state": "private", "output": "public"}, 1)
            location["ledger"].parent.mkdir(parents=True)
            original = b'{"event":"started","seq":1}\n'
            location["ledger"].write_bytes(original)
            report = {"version": bench.VERSION, "status": "completed"}
            with self.assertRaisesRegex(ValueError, "invented final guard"):
                with bench.native.retain_attempt(report, location):
                    raise ValueError("invented final guard")
            saved = bench.read(location["report"])
            self.assertEqual(saved["status"], "failed_or_interrupted")
            self.assertEqual(location["ledger"].read_bytes(), original)
            self.assertEqual(gzip.decompress(location["archive"].read_bytes()), original)

    def test_registration_never_loads_selection_or_selected_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope_file = root / bench.SCOPE
            scope_file.parent.mkdir(parents=True)
            scope_file.write_text("{}")
            candidate = {"commit": "a" * 40, "runtime_sha256": "b" * 64}
            plan = {"export": {"source": candidate}, "native_boundaries": {"fixture": "no engine"},
                    "schedule": {"total_search_calls": 7680, "total_quality_rows": 15360}}
            args = SimpleNamespace(register=root / "registration.json", source=root / "source", selection=root / "selection.json",
                                   state=root / "state", output=root / "output", cache=root / "cache", node=root / "node")
            with patch.object(bench, "ROOT", root), patch.object(bench, "scope", return_value=plan), \
                 patch.object(bench.d, "registered", return_value={"comparators": {"pins": ["invented-pin"]}}), \
                 patch.object(bench.d, "relative", side_effect=lambda p: str(Path(p).relative_to(root))), \
                 patch.object(bench.d, "committed"), patch.object(bench.scoring, "source", return_value=candidate), \
                 patch.object(bench, "asset_pins", return_value={"invented": "pin"}), \
                 patch.object(bench, "evaluator_files", return_value={"fixture.py": "c" * 64}), \
                 patch.object(bench.importlib.metadata, "version", side_effect=lambda name: bench.DEPENDENCIES[name]), \
                 patch.object(bench.d, "host", return_value={"invented": "host"}), \
                 patch.object(bench.d, "load_selection", side_effect=AssertionError("selection decoded")) as selected, \
                 patch.object(bench.d, "load_dataset", side_effect=AssertionError("fresh content decoded")) as loaded:
                bench.register(args)
            selected.assert_not_called()
            loaded.assert_not_called()
            saved = bench.read(args.register)
            self.assertEqual(saved["status"], "frozen-before-selection")
            self.assertEqual(saved["candidate_source"], candidate)
            self.assertEqual(saved["fresh_content_rows_decoded"], 0)
            self.assertEqual(saved["schedule"]["total_search_calls"], 7680)


if __name__ == "__main__":
    unittest.main(verbosity=2)
