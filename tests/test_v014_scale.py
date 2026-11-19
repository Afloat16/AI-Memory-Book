"""Evaluator integrity checks; no formal scale retrieval query runs here."""

from copy import deepcopy
from datetime import datetime
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import v014_scale as scale
from benchmarks import v014_workload as work


def supplied_response(case, spec, sid=None):
    sid = sid or case["required"][0]["session_id"]
    source = work.source_for(spec, case["project"], sid)
    text = work.source_turn(source["messages"], 0)
    ref = {"project": source["project"], "session_id": sid, "turn_index": 0,
           "start": 0, "end": len(text), "turn_start": 0, "turn_end": len(text),
           "created_at": source["created_at"]}
    hit = {"id": "p_integrity_fixture", "text": text, "source_refs": [ref],
           "breadcrumb": [{"id": source["project"], "kind": "project"}]}
    prefix = (f"[{hit['id']}] {source['project']} / {sid} | {source['created_at']}\n"
              if case["surface"] == "recall" else "")
    return {"context": prefix + text, "results": [hit]}


class V014WorkloadIntegrityTests(unittest.TestCase):
    def test_frozen_matrix_matches_registered_counts_and_reaches_200k(self):
        plan = scale.plan()
        specs = work.checkpoints()
        self.assertEqual([row["id"] for row in specs], plan["resource_profiles"]["main"]["checkpoint_ids"])
        self.assertEqual([row["total_pages"] for row in specs], plan["resource_profiles"]["main"]["total_pages"])
        self.assertEqual(specs[-1]["total_pages"], 200000)
        self.assertEqual(work.checkpoints("expanded")[-1]["total_pages"], 500000)
        self.assertEqual(scale.measurement_counts(plan, len(specs))["api_measurements_total"], 11520)
        self.assertTrue(all(row["development_only"] for row in work.checkpoints("development")))
        self.assertFalse(any(row["development_only"] for row in specs))

    def test_core_ground_truth_is_replayed_and_missing_facets_are_separate(self):
        rows = work.cases()
        self.assertEqual(len(rows), 88)
        self.assertEqual(sum(row["surface"] == "recall" for row in rows), 80)
        self.assertEqual(sum(row["answerability"] == "answerable" for row in rows), 64)
        self.assertEqual(sum(row["answerability"] == "partial" for row in rows), 8)
        self.assertEqual(sum(row["answerability"] == "unanswerable" for row in rows), 16)
        for revision in (0, 1):
            spec = {**work.checkpoints()[0], "revision": revision}
            for row in work.cases(revision):
                for required in row["required"] + row["stale"]:
                    source = work.source_for(spec, row["project"], required["session_id"])
                    self.assertIn(required["quote"], work.source_turn(source["messages"], required["turn_index"]))
                self.assertEqual(bool(row["missing_identifiers"]), row["answerability"] != "answerable")

    def test_age_controls_only_shift_source_dates(self):
        original = list(work.sessions(work.checkpoints()[0]))
        for spec in work.checkpoints()[1:3]:
            shifted = list(work.sessions(spec))
            self.assertEqual(len(original), len(shifted))
            for before, after in zip(original, shifted):
                self.assertEqual({k: v for k, v in before.items() if k != "created_at"},
                                 {k: v for k, v in after.items() if k != "created_at"})
                days = (datetime.fromisoformat(before["created_at"]) -
                        datetime.fromisoformat(after["created_at"])).days
                self.assertEqual(days, spec["shift_days"])

    def test_200k_layout_and_target_counts_are_logically_identical(self):
        clustered, interleaved = work.checkpoints()[6:8]
        sources, counts, before_order = {}, {}, []
        for source in work.sessions(clustered):
            key = source["project"], source["session_id"]
            self.assertNotIn(key, sources)
            sources[key] = work.digest(source)
            before_order.append(key)
            counts[key[0]] = counts.get(key[0], 0) + len(source["messages"]) // 2
        self.assertEqual(sum(counts.values()), 200000)
        for target in work.TARGETS:
            if target["lifecycle"] == "inactive":
                self.assertEqual(counts[target["project"]], 16)
        after_order = []
        for source in work.sessions(interleaved):
            key = source["project"], source["session_id"]
            self.assertEqual(sources.pop(key), work.digest(source))
            after_order.append(key)
        self.assertFalse(sources)
        self.assertNotEqual(before_order, after_order)

    def test_foreign_growth_does_not_change_any_target_payload(self):
        small, large = work.checkpoints()[0], work.checkpoints()[5]
        targets = {row["project"] for row in work.TARGETS}
        left = {(row["project"], row["session_id"]): row for row in work.sessions(small)
                if row["project"] in targets}
        # Check only target sources; generator construction guarantees background
        # IDs are distinct, also covered by the full layout/count assertion.
        right = {(project, sid): work.source_for(large, project, sid) for project, sid in left}
        self.assertEqual(left, right)

    def test_new_seed_reconstructs_exact_sources_and_refuses_unseen_history(self):
        spec = work.checkpoints("development")[0]
        for source in work.sessions(spec):
            self.assertEqual(source, work.source_for(spec, source["project"], source["session_id"]))
            text = json.dumps(source)
            self.assertNotIn("distributed_all_reduce_bucket_bytes", text)
        with self.assertRaises(KeyError):
            work.source_for(spec, "routing-archive", "growth-000000")
        with self.assertRaises(KeyError):
            work.source_for(spec, "routing-similar-000999", "maintenance-000000")


class V014ScoringIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.spec = work.checkpoints()[0]
        self.rows = {row["id"]: row for row in work.cases()}
        self.current = self.rows["routing-archive:current"]
        self.response = supplied_response(self.current, self.spec)

    def coverage(self, case, **changes):
        return {"status": "insufficient_evidence", "scope": "returned_excerpts",
                "requested_identifiers": case["missing_identifiers"],
                "missing_identifiers": case["missing_identifiers"], **changes}

    def test_valid_source_and_fabricated_source_are_distinguished(self):
        self.assertTrue(scale.score(self.response, self.current, self.spec)["complete"])
        bad = deepcopy(self.response)
        bad["results"][0]["text"] += " Fabricated approval."
        bad["context"] += " Fabricated approval."
        scored = scale.score(bad, self.current, self.spec)
        self.assertFalse(scored["complete"])
        self.assertIn("hit-0:unsupported_excerpt_text", scored["source_errors"])

    def test_related_context_is_not_scored_as_an_answer_to_a_missing_fact(self):
        case = self.rows["routing-archive:missing_identifier"]
        scored = scale.score(self.response, case, self.spec)
        self.assertIsNone(scored["complete"])
        self.assertIsNone(scored["available_evidence_complete"])
        self.assertTrue(scored["returned_context_for_missing"])
        self.assertFalse(scored["explicit_missing_signal"])
        self.assertEqual(scored["coverage_status"], "metadata_absent")
        self.assertEqual(scored["source_errors"], [])

    def test_missing_signal_requires_the_requested_identifier_and_returned_scope(self):
        case = self.rows["routing-archive:missing_identifier"]
        response = {**self.response, "evidence_coverage": self.coverage(case)}
        self.assertTrue(scale.score(response, case, self.spec)["explicit_missing_signal"])
        for changes in ({"scope": "whole_archive"}, {"missing_identifiers": ["unrelated_field"]},
                        {"status": "literal_mentions_present"}, {"status": "not_assessed"}):
            response["evidence_coverage"] = self.coverage(case, **changes)
            self.assertFalse(scale.score(response, case, self.spec)["explicit_missing_signal"])

    def test_missing_signal_cannot_hide_a_false_missing_claim_about_a_present_literal(self):
        case = self.rows["routing-archive:partial_identifier"]
        identifiers = case["missing_identifiers"] + ["edge_policy"]
        response = {**self.response, "evidence_coverage": self.coverage(case,
            requested_identifiers=identifiers, missing_identifiers=identifiers)}
        scored = scale.score(response, case, self.spec)
        self.assertFalse(scored["explicit_missing_signal"])
        self.assertIn("missing_identifier_is_literally_present:edge_policy", scored["coverage_errors"])
        self.assertTrue(scored["available_evidence_complete"])

    def test_missing_metadata_must_be_internally_consistent(self):
        case = self.rows["routing-archive:missing_identifier"]
        for changes in ({"requested_identifiers": []}, {"missing_identifiers": "wrong-shape"},
                        {"requested_identifiers": [None]}, {"status": "not_assessed"}):
            response = {**self.response, "evidence_coverage": self.coverage(case, **changes)}
            scored = scale.score(response, case, self.spec)
            self.assertFalse(scored["explicit_missing_signal"])
            self.assertTrue(scored["coverage_errors"])

    def test_partial_request_cannot_become_complete_just_because_known_facet_is_present(self):
        case = self.rows["routing-archive:partial_identifier"]
        response = {**self.response, "evidence_coverage": self.coverage(case)}
        scored = scale.score(response, case, self.spec)
        self.assertTrue(scored["available_evidence_complete"])
        self.assertIsNone(scored["complete"])
        self.assertFalse(scored["answerable"])
        self.assertEqual(scored["answerability"], "partial")
        self.assertTrue(scored["explicit_missing_signal"])

    def test_mention_metadata_cannot_repair_missing_required_evidence(self):
        response = {"context": "", "results": [], "evidence_coverage": {
            "status": "literal_mentions_present", "scope": "returned_excerpts",
            "requested_identifiers": ["edge_policy"], "missing_identifiers": []}}
        self.assertFalse(scale.score(response, self.current, self.spec)["complete"])

    def test_false_missing_signal_on_answerable_case_is_visible(self):
        response = {**self.response, "evidence_coverage": {
            "status": "insufficient_evidence", "scope": "returned_excerpts",
            "missing_identifiers": ["edge_policy"]}}
        scored = scale.score(response, self.current, self.spec)
        self.assertTrue(scored["complete"])
        self.assertTrue(scored["false_missing_signal_on_answerable"])

    def test_cross_project_or_unicode_coordinate_forgery_loses_credit(self):
        for field, value in (("project", "routing-core"), ("turn_end", 10**9)):
            bad = deepcopy(self.response)
            bad["results"][0]["source_refs"][0][field] = value
            self.assertFalse(scale.score(bad, self.current, self.spec)["complete"])

    def test_same_source_id_cannot_authenticate_the_replaced_old_payload(self):
        old = self.rows["routing-core:replacement"]
        latest = next(row for row in work.cases(1) if row["id"] == old["id"])
        response = supplied_response(old, self.spec)
        scored = scale.score(response, latest, work.checkpoints()[-1])
        self.assertFalse(scored["complete"])
        self.assertTrue(scored["source_errors"])


class V014MeasurementIntegrityTests(unittest.TestCase):
    def record_supplied_response(self, raw, score_exception=None):
        case = work.cases()[0]
        spec = work.checkpoints()[0]
        class Book:
            def __init__(self):
                self.db = sqlite3.connect(":memory:")

            def recall(self, *args, **kwargs):
                return raw
        book = Book()
        try:
            with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as folder:
                recorder = scale.Recorder(folder)
                with patch.object(scale, "score", side_effect=score_exception) as scorer:
                    row = scale.measure_case(book, case, spec, "quality", {}, recorder, scale.plan())
                packet = json.loads(gzip.decompress(recorder.raw.read_bytes()))
                return row, packet, scorer.call_count
        finally:
            book.db.close()

    def test_scorer_exception_retains_the_original_api_response_and_timer(self):
        raw = {"query": work.cases()[0]["query"], "strategy": "book", "budget_chars": 2400,
               "temporal": {"requested": "auto"}, "results": [], "context": "unaltered original"}
        row, packet, calls = self.record_supplied_response(raw, ValueError("deliberate verifier failure"))
        self.assertEqual(calls, 1)
        self.assertEqual(row["error"]["phase"], "validation")
        self.assertEqual(packet["original_response"], raw)
        self.assertEqual(row["raw_sha256"], scale.digest(raw))
        self.assertIsInstance(row["wall_ns"], int)

    def test_bad_api_framing_is_saved_as_failed_validation_before_scoring(self):
        for raw in ([], {"query": "wrong request"}, {"query": work.cases()[0]["query"],
                    "strategy": "book", "budget_chars": 2400, "temporal": None}):
            row, packet, calls = self.record_supplied_response(raw)
            self.assertEqual(row["error"]["phase"], "validation")
            self.assertEqual(packet["original_response"], raw)
            self.assertEqual(calls, 0)

    def test_balanced_schedule_and_sample_counts(self):
        config = scale.plan()
        self.assertEqual(scale.expected_samples_per_round("cold-result-cache", config), 8)
        self.assertEqual(scale.expected_samples_per_round("warm-result-cache", config), 8)
        self.assertEqual(scale.expected_samples_per_round("first-connection", config), 1)
        self.assertEqual(scale.expected_samples_per_round("sql-work-probe", config), 1)
        broken = deepcopy(config)
        broken["measurement"]["arm_order_by_round"][0] = ["baseline", "baseline"]
        with self.assertRaises(ValueError):
            scale.measurement_counts(broken, 9)

    def test_sql_progress_is_observable_and_explicitly_not_a_row_count(self):
        db = sqlite3.connect(":memory:")
        try:
            probe = scale.SQLiteWorkProbe(db, 100)
            probe.start()
            db.execute("WITH RECURSIVE seq(n) AS (SELECT 0 UNION ALL SELECT n+1 FROM seq WHERE n<999) SELECT SUM(n) FROM seq").fetchone()
            probe.stop()
            result = probe.result()
            self.assertGreater(result["progress_callbacks"], 0)
            self.assertGreater(result["sqlite_trace_callbacks"], 0)
            self.assertEqual(result["vm_steps_proxy"], 100 * result["progress_callbacks"])
            self.assertIn("not scanned rows", result["interpretation"])
            before = result["progress_callbacks"]
            db.execute("SELECT 1").fetchone()
            self.assertEqual(probe.result()["progress_callbacks"], before)
        finally:
            db.close()

    def test_instrumented_work_is_not_silently_mixed_with_uninstrumented_metrics(self):
        self.assertIsNone(scale.work_metrics([{"sql_work": None}]))
        result = scale.work_metrics([{"sql_work": {"vm_steps_proxy": 200,
            "progress_callbacks": 2, "sqlite_trace_callbacks": 1}}])
        self.assertEqual(result["vm_steps_proxy"]["p50"], 200)

    def test_original_responses_survive_gzip_members_and_missing_errors(self):
        with tempfile.TemporaryDirectory(dir=scale.ROOT.parent) as folder:
            recorder = scale.Recorder(folder)
            raw = {"context": "原始返回", "evidence_coverage": {"status": "not_assessed"}}
            observation = {"case": "test-only", "mode": "sql-work-probe"}
            recorder.record(observation, raw)
            recorder.record({"case": "failed-only", "error": {"type": "TimeoutError"}}, None)
            blob = recorder.raw.read_bytes()
            member = blob[observation["raw_gzip_offset"]:observation["raw_gzip_offset"] + observation["raw_gzip_bytes"]]
            self.assertEqual(json.loads(gzip.decompress(member))["original_response"], raw)
            self.assertEqual(len(gzip.decompress(blob).splitlines()), 2)

    def test_new_protocol_freezes_its_legacy_generator_dependency(self):
        self.assertIn("benchmarks/v013_workload.py", scale.FROZEN_FILES)
        self.assertNotIn("benchmarks/v013_scale.py", scale.FROZEN_FILES)
        self.assertEqual(scale.plan()["baseline_commit"], "861b7f35ac2557024d89bc51d5b3017ca35cb9d0")


if __name__ == "__main__":
    unittest.main()
