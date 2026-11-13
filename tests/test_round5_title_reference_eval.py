"""Artificial annotation, cost, and interruption fixtures; no benchmark calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.data import Evidence, QueryCase
from scripts import round5_title_reference_eval as bench


def page(identity, text, *, session="s", project="p", start=0, end=None):
    end = len(text) if end is None else end
    return {"id": identity, "text": text, "source_refs": [{"session_id": session,
        "project": project, "turn_index": 0, "turn_start": start, "turn_end": end}],
        "breadcrumb": [{"id": project}]}


def fixture_row(identity, *, complete, on=False, supported_new=False, latency=1.0):
    ranks = [1, 2 if supported_new else 1] if complete else [1, None]
    old_complete = int(identity) < 10
    first_annotations = [0, 1] if old_complete else [0]
    ids = ["first-" + identity, ("new-" if on else "old-") + identity]
    pages = [{"id": ids[0], "session_id": "first", "annotations": first_annotations},
             {"id": ids[1], "session_id": "new" if on else "old", "annotations": [1] if supported_new else []}]
    metadata = {"version": 1, "active": True, "applied": True, "reason": "followed",
                "target": {"page_id": ids[1]}, "target_initial_page_in_pool": False,
                "target_initial_session_in_pool": False} if on else None
    return {"id": identity, "answerable": True, "category": "fixture", "project": "p",
        "required_evidence": 2, "matched_evidence": sum(x is not None for x in ranks),
        "complete": complete, "reciprocal_rank": 1.0, "evidence_ranks": ranks,
        "nonempty": True, "returned_characters": 40, "returned_utf8_bytes": 40,
        "duplicate_source_characters": 0, "budget_violation": False, "context_size_consistent": True,
        "stale_only": False, "stale_before_current": False, "result_count": 2, "result_ids": ids,
        "context_tokens": {x: 12 for x in bench.ENCODINGS}, "response_tokens": {x: 30 for x in bench.ENCODINGS},
        "response_utf8_bytes": 120, "wall_ms": latency, "annotated_pages": pages,
        "annotated_page_hits": sum(bool(p["annotations"]) for p in pages),
        "annotated_page_precision": sum(bool(p["annotations"]) for p in pages) / 2,
        "title_reference": metadata, "context_sha256": bench.digest([identity, on]),
        "native_payload_sha256": bench.digest([identity, on]), "errors": {name: 0 for name in bench.ERRORS}}


def passing_cell():
    rows = []
    for i in range(20):
        identity = str(i)
        rows.extend([{"mode": bench.MODES[0], "score": fixture_row(identity, complete=i < 10)},
                     {"mode": bench.MODES[1], "score": fixture_row(identity, complete=i < 12, on=True,
                                                                 supported_new=i < 12, latency=1.1)}])
    return {"configuration": {"index": 3, "cohort": "round4-hotpot256", "queries": 20,
                              "tokenizer": "cl100k_base", "budget_tokens": 1024}, "rows": rows}


class AnnotationPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.original = "Alpha fact. Beta fact."
        self.sources = {("p", "s", 0): self.original}
        self.case = QueryCase("q", "question", "fixture", "p", (Evidence("s", 0, "Alpha fact."), Evidence("s", 0, "Beta fact.")))

    def test_later_duplicate_supporting_page_counts_independently(self):
        pages = [page("a", self.original), page("b", self.original), page("c", "Noise only", session="elsewhere")]
        response = {"results": pages, "context": "\n\n".join(p["text"] for p in pages)}
        scored = bench.annotated_pages(self.case, response, self.sources)
        self.assertEqual([p["annotations"] for p in scored], [[0, 1], [0, 1], []])
        self.assertEqual(sum(bool(p["annotations"]) for p in scored), 2)

    def test_wrong_source_or_partial_original_span_never_counts(self):
        response = {"results": [page("wrong", self.original, session="wrong"),
                                 page("partial", self.original, end=5)], "context": self.original}
        self.assertEqual([p["annotations"] for p in bench.annotated_pages(self.case, response, self.sources)], [[], []])

    def test_annotation_must_be_in_actual_returned_text_and_context(self):
        response = {"results": [page("a", "Alpha", end=len(self.original))], "context": self.original}
        self.assertEqual(bench.annotated_pages(self.case, response, self.sources)[0]["annotations"], [])
        response = {"results": [page("a", self.original)], "context": "nothing"}
        self.assertEqual(bench.annotated_pages(self.case, response, self.sources)[0]["annotations"], [])

    def test_unsupported_queries_remain_in_precision_denominator(self):
        good = fixture_row("10", complete=False)
        unsupported = fixture_row("20", complete=False)
        unsupported.update(answerable=False, required_evidence=0, matched_evidence=0,
            evidence_ranks=[], reciprocal_rank=0, annotated_page_hits=0, annotated_page_precision=0.0,
            annotated_pages=[{"id": "u1", "session_id": "u", "annotations": []},
                             {"id": "u2", "session_id": "u", "annotations": []}])
        value = bench.metrics([good, unsupported])
        self.assertEqual(value["returned_pages"], 4)
        self.assertEqual(value["annotated_pages"], 1)
        self.assertEqual(value["annotated_page_precision"], 0.25)
        self.assertEqual(value["answerable_queries"], 1)

    def test_zero_displaced_denominator_is_null_not_one(self):
        off = fixture_row("10", complete=False)
        on = fixture_row("10", complete=True, on=True, supported_new=True)
        on["annotated_pages"].append(copy.deepcopy(off["annotated_pages"][1]))
        change = bench.paired_changes(off, on)
        self.assertEqual(len(change["introduced"]), 1)
        self.assertEqual(change["displaced"], [])

    def test_selected_unreturned_target_is_not_introduced(self):
        off = fixture_row("10", complete=False)
        on = copy.deepcopy(off)
        on["title_reference"] = {"target": {"page_id": "not-returned"}}
        change = bench.paired_changes(off, on)
        self.assertFalse(change["target_returned"])
        self.assertEqual(change["introduced"], [])

    def test_metadata_only_payload_change_is_not_a_quality_gain(self):
        off = fixture_row("10", complete=False)
        on = copy.deepcopy(off)
        on["title_reference"] = {"version": 1, "active": False, "applied": False, "reason": "no_lexical_results"}
        on["native_payload_sha256"] = bench.digest([off["native_payload_sha256"], on["title_reference"]])
        change = bench.paired_changes(off, on)
        self.assertTrue(change["native_payload_changed"])
        self.assertEqual(change["annotation_gains"], [])
        self.assertEqual(change["introduced"], [])
        self.assertFalse(change["complete_gain"])
        self.assertEqual(bench.metrics([off]), bench.metrics([on]))

    def test_aggregate_recall_recomputes_counts_ignoring_cached_ratio(self):
        row = fixture_row("10", complete=False)
        for cached_ratio in (0.0, 1.0):
            row["evidence_recall"] = cached_ratio
            value = bench.metrics([row])
            self.assertEqual(value["matched_evidence"], 1)
            self.assertEqual(value["required_evidence"], 2)
            self.assertEqual(value["evidence_recall"], 0.5)


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((bench.ROOT / bench.PLAN).read_text())

    def test_primary_passing_fixture_and_complete_loss_ids(self):
        value = bench.assess_cell(passing_cell(), self.plan)
        self.assertTrue(value["passed"], value["failed_gates"])
        self.assertEqual(value["complete_gain_ids"], ["10", "11"])
        self.assertEqual(value["complete_loss_ids"], [])
        self.assertAlmostEqual(value["introduced_hit_rate"], 0.6)
        self.assertEqual(value["displaced_hit_rate"], 0)

    def test_latency_requires_both_relative_and_absolute_limit(self):
        for old, new in ((1.0, 1.3), (10.0, 11.5)):
            cell = passing_cell()
            for row in cell["rows"]:
                row["score"]["wall_ms"] = old if row["mode"] == bench.MODES[0] else new
            self.assertIn("p95_cost", bench.assess_cell(cell, self.plan)["failed_gates"])

    def test_insufficient_precision_rejects_despite_recall_gain(self):
        cell = passing_cell()
        for row in cell["rows"]:
            if row["mode"] == bench.MODES[1]:
                row["score"]["annotated_page_hits"] = 1
                row["score"]["annotated_page_precision"] = 0.5
        value = bench.assess_cell(cell, self.plan)
        self.assertIn("annotated_page_precision_primary_gain", value["failed_gates"])

    def test_missing_introduced_pages_is_a_primary_failure(self):
        cell = passing_cell()
        for row in cell["rows"]:
            if row["mode"] == bench.MODES[1]:
                row["score"]["annotated_pages"][1]["id"] = "old-" + row["score"]["id"]
        value = bench.assess_cell(cell, self.plan)
        self.assertIsNone(value["introduced_hit_rate"])
        self.assertIsNone(value["displaced_hit_rate"])
        self.assertIn("introduced_page_hit_rate", value["failed_gates"])

    def test_integrity_failure_rejects_even_with_quality_gains(self):
        cell = passing_cell()
        cell["rows"][0]["score"]["errors"]["source"] = 1
        self.assertIn("integrity", bench.assess_cell(cell, self.plan)["failed_gates"])

    def test_hotpot512_disallows_even_small_complete_decline(self):
        cell = passing_cell()
        cell["configuration"]["budget_tokens"] = 512
        for row in cell["rows"]:
            if row["mode"] == bench.MODES[1]:
                row["score"]["complete"] = int(row["score"]["id"]) < 9
        self.assertIn("hotpot512_complete_decline", bench.assess_cell(cell, self.plan)["failed_gates"])


class ProvenanceTests(unittest.TestCase):
    def test_disabled_mode_cannot_add_metadata(self):
        with self.assertRaisesRegex(ValueError, "Disabled"):
            bench.title_provenance({"title_reference": {}}, False, None, {}, {})

    def test_unexamined_membership_is_not_false(self):
        meta = {"version": 1, "active": True, "applied": False, "reason": "no-title"}
        self.assertEqual(bench.title_provenance({"title_reference": meta}, True, None, {}, {}), meta)
        meta["target_initial_page_in_pool"] = False
        with self.assertRaisesRegex(ValueError, "Unexamined"):
            bench.title_provenance({"title_reference": meta}, True, None, {}, {})

    def test_original_mention_projection_and_complete_title_required(self):
        text = "See Blue Atlas here."
        refs = [{"turn_index": 0, "start": 0, "end": len(text), "turn_start": 0}]
        pages = {"anchor": {"content": text, "source_refs": json.dumps(refs), "project_id": "p", "session_pk": "a", "session_id": "s"},
                 "target": {"project_id": "p", "session_pk": "b", "session_id": "t", "session_title": "Blue Atlas"}}
        meta = {"version": 1, "active": True, "applied": True, "reason": "followed",
            "anchor": {"page_id": "anchor", "session_pk": "a", "session_id": "s"},
            "target": {"page_id": "target", "session_pk": "b", "session_id": "t", "route": "title_reference"},
            "mention": {"page_span": [4, 14], "turn_index": 0, "turn_span": [4, 14]},
            "target_initial_page_in_pool": False, "target_initial_session_in_pool": False}
        case = QueryCase("q", "question", "fixture", "p")
        sources = {("p", "s", 0): text}
        self.assertEqual(bench.title_provenance({"title_reference": meta}, True, case, pages, sources), meta)
        meta["mention"]["turn_span"] = [3, 13]
        with self.assertRaisesRegex(ValueError, "original source"):
            bench.title_provenance({"title_reference": meta}, True, case, pages, sources)


class ScheduleAndRecoveryTests(unittest.TestCase):
    def test_offline_audit_rejects_inconsistent_answerability_even_with_matching_ledger(self):
        cell = {"index": 0, "cohort": "synthetic61", "queries": 1,
                "tokenizer": "cl100k_base", "budget_tokens": 1024}
        bound = {"source": {"commit": "artificial"}, "host": {"boot": "artificial"},
                 "datasets": {"synthetic61": {"sha256": "artificial", "ids": ["10"]}}}
        rows = [{"mode": mode, "score": fixture_row("10", complete=False, on=mode == bench.MODES[1])}
                for mode in bench.MODES]
        plan = json.loads((bench.ROOT / bench.PLAN).read_text())

        def artifact():
            events = [event for seq, row in enumerate(rows) for event in (
                {"event": "started", "seq": seq, "id": row["score"]["id"], "mode": row["mode"]},
                {"event": "finished", "seq": seq, "row": row})]
            ledger = b"".join(bench.raw(event) for event in events)
            value = {"status": "completed", "configuration": cell, "binding_sha256": bench.digest(bound),
                     "source": bound["source"], "source_after": bound["source"], "host": bound["host"],
                     "dataset_sha256": "artificial", "source_snapshot_before": "x", "source_snapshot_after": "x",
                     "index_before": "y", "index_after": "y", "rows": rows, "started": 2, "finished": 2,
                     "ledger_sha256": hashlib.sha256(ledger).hexdigest()}
            value["assessment"] = bench.assess_cell(value, plan)
            return value, ledger

        with patch.object(bench, "registered", return_value=plan):
            value, ledger = artifact()
            bench.verify_cell(value, ledger, bound, cell)
            for answerable in (False, 1):
                rows[0]["score"]["answerable"] = answerable
                value, ledger = artifact()
                with self.assertRaisesRegex(ValueError, "Answerability"):
                    bench.verify_cell(value, ledger, bound, cell)

    def test_fixed_matrix_is_5438_calls_and_alternating_pairs(self):
        plan = json.loads((bench.ROOT / bench.PLAN).read_text())
        cells = bench.schedule(plan)
        self.assertEqual(len(cells), 8)
        self.assertEqual(sum(c["queries"] * 2 for c in cells), 5438)
        ordered = bench.query_schedule(["a", "b", "c"], cells[0])
        self.assertEqual([m for _, m in ordered], [*bench.MODES, *reversed(bench.MODES), *bench.MODES])
        self.assertEqual([ordered[i][0] == ordered[i + 1][0] for i in (0, 2, 4)], [True] * 3)

    def test_partial_worker_is_preserved_not_rerun(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bench, "ROOT", Path(directory)):
            bound = {"schedule": [{"index": 0}], "output": "out", "state": "state"}
            output, _, _ = bench.cell_paths(bound, 0)
            bench.save(output, {"status": "running"})
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                bench.completed_prefix(bound)
            self.assertEqual(output.read_bytes(), before)

    def test_completed_suffix_without_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bench, "ROOT", Path(directory)):
            bound = {"schedule": [{"index": 0}, {"index": 1}], "output": "out", "state": "state"}
            output, ledger, state = bench.cell_paths(bound, 1)
            bench.save(output, {"status": "completed"})
            ledger.write_text("")
            state.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "out-of-order"):
                bench.completed_prefix(bound)


if __name__ == "__main__":
    unittest.main()
