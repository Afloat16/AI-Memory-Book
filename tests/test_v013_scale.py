"""Integrity tests for the frozen v0.13 evaluator, not retrieval score targets.

No formal query is executed here. Tests exercise deterministic generation,
adversarial supplied responses, and tiny ingest/snapshot storage contracts.
"""

from copy import deepcopy
from contextlib import closing
from datetime import datetime
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import v013_scale as scale
from benchmarks.v013_workload import (TARGETS, background_session, cases, checkpoints,
                                     core_sessions, digest, sessions, source_for, source_turn)


def supplied_response(case, spec, *, session_id=None):
    required = case["required"][0]
    source = source_for(spec, case["project"], session_id or required["session_id"])
    text = source_turn(source["messages"], 0)
    ref = {"project": source["project"], "session_id": source["session_id"], "turn_index": 0,
           "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text),
           "created_at": source["created_at"]}
    hit = {"id": "p_integrity_fixture", "text": text, "source_refs": [ref],
           "breadcrumb": [{"id": source["project"], "kind": "project"}]}
    header = f"[{hit['id']}] {ref['project']} / {ref['session_id']} | {ref['created_at']}\n"
    return {"context": (header if case["surface"] == "recall" else "") + text, "results": [hit]}


class V013WorkloadIntegrityTests(unittest.TestCase):
    def test_registered_totals_come_from_real_source_turns(self):
        expected = [1024, 1024, 10016, 50016, 100000, 100000, 100000]
        self.assertEqual([s["total_pages"] for s in checkpoints()], expected)
        for spec in (checkpoints()[0], checkpoints()[4], checkpoints()[5]):
            counts, identities = {}, set()
            for source in sessions(spec):
                identity = source["project"], source["session_id"]
                self.assertNotIn(identity, identities)
                identities.add(identity)
                count = len(source["messages"]) // 2
                counts[source["project"]] = counts.get(source["project"], 0) + count
            self.assertEqual(sum(counts.values()), spec["total_pages"])
            for target in TARGETS:
                if target["lifecycle"] == "inactive":
                    self.assertEqual(counts[target["project"]], 16)

    def test_layout_changes_order_but_not_any_logical_payload_or_source_id(self):
        clustered, interleaved = checkpoints()[4:6]
        earlier = {(s["project"], s["session_id"]): digest(s) for s in sessions(clustered)}
        later = {(s["project"], s["session_id"]): digest(s) for s in sessions(interleaved)}
        self.assertEqual(earlier, later)
        self.assertNotEqual(list(earlier), list(later))

    def test_age_control_changes_only_uniform_dates_in_same_ingestion_order(self):
        earlier, later = map(lambda spec: list(sessions(spec)), checkpoints()[:2])
        self.assertEqual(len(earlier), len(later))
        for old, new in zip(earlier, later):
            old_date, new_date = old.pop("created_at"), new.pop("created_at")
            self.assertEqual(old, new)
            self.assertEqual((datetime.fromisoformat(old_date) - datetime.fromisoformat(new_date)).days, 3650)

    def test_gold_exists_in_requested_source_and_only_registered_replacements_change(self):
        before, after = {}, {}
        for target in TARGETS:
            before.update({(s["project"], s["session_id"]): s for s in core_sessions(target, 0)})
            after.update({(s["project"], s["session_id"]): s for s in core_sessions(target, 1)})
        changed = [identity for identity in before if before[identity] != after[identity]]
        self.assertEqual(len(changed), 6)
        self.assertTrue(all(sid == "active-config" for project, sid in changed))
        for revision, records in ((0, before), (1, after)):
            queries = cases(revision)
            self.assertEqual(len(queries), 72)
            self.assertEqual(sum(c["surface"] == "recall" for c in queries), 64)
            self.assertEqual(sum(c["surface"] == "recall" and bool(c["required"]) for c in queries), 56)
            for case in queries:
                for item in case["required"] + case["stale"]:
                    source = records[case["project"], item["session_id"]]
                    self.assertIn(item["quote"], source_turn(source["messages"], item["turn_index"]))

    def test_source_reconstruction_cannot_cross_project_or_unseen_history(self):
        spec = checkpoints()[0]
        source = background_session(3, "foreign")
        self.assertEqual(source_for(spec, source["project"], source["session_id"]), source)
        with self.assertRaises(KeyError):
            source_for(spec, "routing-similar-000001", source["session_id"])
        with self.assertRaises(KeyError):
            source_for(spec, "routing-core", "growth-000000")
        with self.assertRaises(KeyError):
            source_for(spec, "routing-archive", "growth-000000")


class V013SourceScoringTests(unittest.TestCase):
    def setUp(self):
        self.spec = checkpoints()[0]
        self.case = cases()[0]
        self.response = supplied_response(self.case, self.spec)

    def test_valid_cited_evidence_passes_but_invented_excerpt_or_context_fails(self):
        self.assertTrue(scale.score(self.response, self.case, self.spec)["complete"])
        injected = deepcopy(self.response)
        injected["results"][0]["text"] += " Fabricated implementation rule."
        injected["context"] += " Fabricated implementation rule."
        judged = scale.score(injected, self.case, self.spec)
        self.assertFalse(judged["complete"])
        self.assertIn("hit-0:unsupported_excerpt_text", judged["source_errors"])
        injected = deepcopy(self.response)
        injected["context"] += " Hidden unsupported context."
        self.assertIn("context_not_excerpts_plus_source_citations",
                      scale.score(injected, self.case, self.spec)["source_errors"])

    def test_cross_project_and_invalid_unicode_coordinates_cannot_receive_credit(self):
        injected = deepcopy(self.response)
        injected["results"][0]["source_refs"][0]["project"] = "routing-core"
        judged = scale.score(injected, self.case, self.spec)
        self.assertFalse(judged["complete"])
        self.assertIn("hit-0:cross_project_source", judged["source_errors"])
        injected = deepcopy(self.response)
        injected["results"][0]["source_refs"][0]["turn_end"] += 1
        self.assertFalse(scale.score(injected, self.case, self.spec)["complete"])

    def test_missing_gold_and_current_first_are_separate_from_completeness(self):
        missing = next(c for c in cases() if c["project"] == self.case["project"] and c["category"] == "missing")
        judged = scale.score(self.response, missing, self.spec)
        self.assertIsNone(judged["complete"])
        self.assertTrue(judged["returned_context_for_missing"])
        stale = supplied_response(self.case, self.spec, session_id="original-policy")
        together = {"context": stale["context"] + "\n\n" + self.response["context"],
                    "results": stale["results"] + self.response["results"]}
        judged = scale.score(together, self.case, self.spec)
        self.assertTrue(judged["complete"])
        self.assertFalse(judged["current_source_first"])
        self.assertTrue(judged["stale_before_current"])

    def test_source_replacement_makes_superseded_same_id_text_invalid(self):
        case = next(c for c in cases(1) if c["id"] == "routing-core:replacement")
        old_case = next(c for c in cases(0) if c["id"] == case["id"])
        obsolete = supplied_response(old_case, self.spec)
        revised_spec = checkpoints()[-1]
        self.assertFalse(scale.score(obsolete, case, revised_spec)["complete"])
        self.assertTrue(scale.score(obsolete, case, revised_spec)["source_errors"])

    def test_boundary_rank_one_does_not_count_as_current_policy_rank_one(self):
        case = next(c for c in cases() if c["project"] == self.case["project"] and c["category"] == "multi_source")
        current = supplied_response(case, self.spec)
        boundary = supplied_response(case, self.spec, session_id="boundary-contract")
        response = {"context": boundary["context"] + "\n\n" + current["context"],
                    "results": boundary["results"] + current["results"]}
        judged = scale.score(response, case, self.spec)
        self.assertTrue(judged["complete"])
        self.assertEqual(judged["required_ranks"], [2, 1])
        self.assertFalse(judged["current_source_first"])


class V013ExecutionIntegrityTests(unittest.TestCase):
    def test_directory_reads_only_returned_addresses_with_explicit_scope(self):
        class Directory:
            def __init__(self):
                self.calls = []

            def search_directory(self, query, **kw):
                self.calls.append(("search_directory", query, kw))
                return {"results": [{"sections": [{"id": "returned-section"}]}]}

            def section(self, identity, **kw):
                self.calls.append(("section", identity, kw))
                return {"pages": [{"id": "returned-page"}]}

            def read(self, identity, **kw):
                self.calls.append(("read", identity, kw))
                return {"id": identity, "content": "原始证据", "source_refs": [], "breadcrumb": []}

        book = Directory()
        response, raw = scale.directory_read(book, "selfcheck navigation", "exact-project", scale.plan()["directory"])
        self.assertEqual([call[0] for call in book.calls], ["search_directory", "section", "read"])
        self.assertTrue(all(call[2]["project"] == "exact-project" for call in book.calls))
        self.assertEqual(book.calls[1][1], "returned-section")
        self.assertEqual(book.calls[2][1], "returned-page")
        self.assertEqual(response["context"], "原始证据")
        self.assertEqual(raw["reads"][0]["content"], "原始证据")

    def test_directory_failure_retains_all_earlier_original_api_responses(self):
        class PartialDirectory:
            def search_directory(self, query, **kw):
                return {"results": [{"sections": [{"id": "first"}, {"id": "second"}]}]}

            def section(self, identity, **kw):
                return {"pages": [{"id": identity}]}

            def read(self, identity, **kw):
                if identity == "second":
                    raise TimeoutError("selfcheck interruption")
                return {"id": identity, "content": "已返回的原文", "source_refs": [], "breadcrumb": []}

        trace = {}
        with self.assertRaises(TimeoutError):
            scale.directory_read(PartialDirectory(), "selfcheck only", "project", scale.plan()["directory"], trace=trace)
        self.assertEqual(len(trace["sections"]), 2)
        self.assertEqual(trace["reads"][0]["content"], "已返回的原文")
        self.assertEqual(trace["pending_call"], {"surface": "read", "id": "second"})

    def test_untracked_python_module_is_rejected_before_runtime_import(self):
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as temporary:
            repo = Path(temporary)
            package = repo / "src/memory_book"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("# tracked\n")
            (package / "extra.py").write_text("# untracked import must not escape the binding\n")
            def fake_git(repo, *args):
                return {"rev-parse": b"0123456789\n", "status": b"", "ls-files": b"src/memory_book/__init__.py\n"}[args[0]]
            with patch.object(scale, "git", side_effect=fake_git):
                with self.assertRaisesRegex(ValueError, "Untracked Python modules"):
                    scale.runtime_identity(repo)

    def test_restore_removes_candidate_index_and_restarts_from_original_bytes(self):
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as temporary:
            folder = Path(temporary)
            original, working = folder / "original.sqlite", folder / "working.sqlite"
            with closing(sqlite3.connect(original)) as db:
                db.execute("CREATE TABLE source(id PRIMARY KEY, content)")
                db.execute("INSERT INTO source VALUES(1,'原始工程证据')")
                db.commit()
            limits = {"minimum_free_bytes": 0, "maximum_database_bytes": 10 * 1024 * 1024,
                      "minimum_snapshot_headroom_bytes": 0}
            snapshot = scale.snapshot_database(original, folder / "snapshot.gz", limits)
            scale.restore_snapshot(snapshot, working, limits)
            with closing(sqlite3.connect(working)) as db:
                db.execute("CREATE INDEX candidate_only ON source(content)")
                db.commit()
            scale.remove_working(working)
            scale.restore_snapshot(snapshot, working, limits)
            self.assertEqual(scale.file_sha(working), snapshot["database_sha256"])
            with closing(sqlite3.connect(working)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='candidate_only'").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT content FROM source").fetchone()[0], "原始工程证据")

    def test_gzip_members_preserve_original_responses_with_offsets(self):
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as temporary:
            recorder = scale.Recorder(temporary)
            raw = {"context": "原始返回", "latency_ms": 12.34, "cache_hit": True}
            first = {"case": "integrity-only", "mode": "warm-result-cache"}
            recorder.record(first, raw)
            recorder.record({"case": "failure-only", "error": {"type": "TimeoutError"}}, None)
            serialized = recorder.raw.read_bytes()
            member = serialized[first["raw_gzip_offset"]:first["raw_gzip_offset"] + first["raw_gzip_bytes"]]
            self.assertEqual(json.loads(gzip.decompress(member))["original_response"], raw)
            self.assertEqual(len(gzip.decompress(serialized).splitlines()), 2)

    def test_real_ingest_builds_real_pages_and_fresh_age_controls_without_recall(self):
        from memory_book import MemoryBook
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as temporary:
            fingerprints = []
            for index, spec in enumerate(checkpoints()[:2]):
                with MemoryBook(Path(temporary) / f"small-{index}.sqlite", segmentation="turn", min_page_chars=0) as book:
                    for source in list(sessions(spec))[:2]:
                        saved = book.ingest(source)
                        self.assertEqual(saved["pages"], 1)
                    fingerprints.append(scale.source_fingerprint(book.db))
            self.assertEqual(fingerprints[0]["age_invariant_sources_sha256"], fingerprints[1]["age_invariant_sources_sha256"])
            self.assertEqual(fingerprints[0]["physical_page_layout"], fingerprints[1]["physical_page_layout"])
            self.assertNotEqual(fingerprints[0]["source_dates_sha256"], fingerprints[1]["source_dates_sha256"])

    def test_floor_and_unfinished_cells_are_not_silently_treated_as_success(self):
        with patch.object(scale, "storage", return_value={"free_bytes": 100, "total_file_bytes": 20}):
            with self.assertRaises(scale.ResourceLimit):
                scale.enforce_resources("unused", {"minimum_free_bytes": 90, "maximum_database_bytes": 100}, extra_bytes=11)
        spec = checkpoints()[0]
        manifest = {"stages": {spec["id"]: {"blocks": [
            {"round": 0, "arm": "baseline", "execution": {"complete": True}},
            {"round": 0, "arm": "candidate", "execution": {"complete": False}}]}}}
        missing = scale.pending_cells(manifest, [spec])
        self.assertEqual(len(missing), 11)
        self.assertIn({"checkpoint": spec["id"], "round": 0, "arm": "candidate"}, missing)

    def test_p95_uses_registered_nearest_rank_and_does_not_hide_small_n(self):
        self.assertEqual(scale.percentile(list(range(1, 31)), .95), 29)
        self.assertEqual(scale.percentile(list(range(1, 91)), .95), 86)
        self.assertIsNone(scale.percentile([], .95))
        registered = scale.plan()["measurement"]
        self.assertEqual(registered["arm_order_by_round"], [["baseline", "candidate"], ["candidate", "baseline"],
                                                            ["candidate", "baseline"], ["baseline", "candidate"],
                                                            ["baseline", "candidate"], ["candidate", "baseline"]])
        counts = scale.measurement_counts(scale.plan(), len(checkpoints()))
        self.assertEqual(counts["api_measurements_total"], 13608)
        self.assertEqual(counts["performance_calls_total"], 12600)
        self.assertEqual(counts["quality_calls_total"], 1008)

    def test_resume_keeps_partial_attempt_but_does_not_pool_it_into_fixed_samples(self):
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as temporary:
            stage = {"blocks": []}
            for number, (complete, wall) in enumerate(((False, 1), (True, 100))):
                directory = Path(temporary) / str(number)
                directory.mkdir()
                row = {"case": "integrity-only", "mode": "cold-result-cache", "wall_ns": wall,
                       "process_cpu_ns": wall, "error": None, "cache_mode_valid": True}
                (directory / "observations.jsonl").write_text(json.dumps(row) + "\n")
                stage["blocks"].append({"round": 0, "arm": "baseline", "execution": {
                    "complete": complete, "result_path": str(directory / "result.json"),
                    "result": {"summary": {"quality": [], "timings": []}}}})
            summary = scale.checkpoint_summary(stage)
            self.assertEqual(summary["timing"][0]["wall_ns"]["n"], 1)
            self.assertEqual(summary["timing"][0]["wall_ns"]["p50"], 100)
            self.assertEqual(len(summary["all_attempts"]), 2)
            self.assertFalse(summary["all_attempts"][0]["included_in_fixed_sample_statistics"])
            stage["blocks"][0]["execution"]["complete"] = True
            with self.assertRaisesRegex(AssertionError, "More than one completed block"):
                scale.checkpoint_summary(stage)


if __name__ == "__main__":
    unittest.main()
