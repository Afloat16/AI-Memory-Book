"""Invented IDs/scores only; no Parquet, real selection, runtime or model calls."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.data import QueryCase
from scripts import round5_title_reference_fresh as bench
from scripts import round5_title_reference_fresh_data as data


def scope_fixture():
    # This is the prospective rule file, never an outcome or selected manifest.
    return json.loads((bench.ROOT / data.SCOPE).read_text())


def score_fixture(number, config, *, complete=False, enabled=False, introduced=False, latency=1.0):
    identity = "invented-question-" + str(number).zfill(4)
    first, second = "first-" + identity, ("new-" if introduced else "old-") + identity
    pages = [{"id": first, "session_id": first, "annotations": [0]},
             {"id": second, "session_id": second, "annotations": [1] if complete else []}]
    case = QueryCase(identity, "  Invented question " + str(number) + "  ", "fixture", "invented-project")
    response = {"context": "x" * 40, "context_chars": 40, "budget_chars": 8000,
        "budget_tokens": config["budget_tokens"], "tokenizer": config["tokenizer"],
        "tokenizer_version": "0.12.0", "context_tokens": 12, "query": case.query.strip()}
    metadata = {"version": 1, "active": True, "applied": introduced,
        "reason": "applied" if introduced else "no_title_mention"} if enabled else None
    if introduced and metadata is not None:
        metadata.update(target={"page_id": second}, target_initial_page_in_pool=False,
                        target_initial_session_in_pool=False)
    return {"id": identity, "answerable": True, "category": "fixture", "project": "invented-project",
        "required_evidence": 2, "matched_evidence": 2 if complete else 1, "complete": complete,
        "reciprocal_rank": 1.0, "evidence_ranks": [1, 2 if complete else None], "nonempty": True,
        "returned_characters": 40, "returned_utf8_bytes": 40, "reported_context_chars": 40,
        "duplicate_source_characters": 0, "budget_violation": False, "context_size_consistent": True,
        "stale_only": False, "stale_before_current": False, "result_count": 2, "result_ids": [first, second],
        "context_tokens": {name: 12 for name in bench.ENCODINGS},
        "response_tokens": {name: 30 for name in bench.ENCODINGS}, "response_utf8_bytes": 120,
        "wall_ms": latency, "annotated_pages": pages, "annotated_page_hits": 2 if complete else 1,
        "annotated_page_precision": 1.0 if complete else 0.5, "title_reference": metadata,
        "context_sha256": bench.digest([identity, complete, introduced]),
        "native_payload_sha256": bench.digest([identity, complete, introduced, enabled]),
        "metadata_diagnostics": bench.scoring.metadata_diagnostics(case, response, config,
            {name: 12 for name in bench.ENCODINGS}), "errors": {name: 0 for name in bench.scoring.ERRORS}}


def paired_fixture(config, *, before=200, after=240):
    off = [score_fixture(i, config, complete=i < before) for i in range(512)]
    on = [score_fixture(i, config, complete=i < after, enabled=True,
                        introduced=before <= i < after, latency=1.1) for i in range(512)]
    return off, on


class MetadataOnlySelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"id": "invented-" + kind + "-" + str(i), "type": kind}
                     for kind, count in (("bridge", 420), ("comparison", 150)) for i in range(count)]

    def test_stratified_hash_order_excludes_old_ids_and_is_input_order_independent(self):
        excluded = {row["id"] for row in self.rows[:20]}
        selected = data.choose_ids(self.rows, excluded)
        self.assertEqual(selected, data.choose_ids(list(reversed(self.rows)), excluded))
        self.assertEqual(len(selected), 512)
        self.assertEqual([r["type"] for r in selected], ["bridge"] * 384 + ["comparison"] * 128)
        self.assertFalse(excluded.intersection(r["id"] for r in selected))
        for kind, count in (("bridge", 384), ("comparison", 128)):
            eligible = [r["id"] for r in self.rows if r["type"] == kind and r["id"] not in excluded]
            expected = sorted(eligible, key=lambda identity: hashlib.sha256(
                ("AI-Memory-Book/v033/title-reference-t1/2026-11-13/" + identity).encode()).hexdigest())[:count]
            self.assertEqual([r["id"] for r in selected if r["type"] == kind], expected)

    def test_content_columns_duplicate_ids_and_unknown_types_are_rejected(self):
        variants = [self.rows + [self.rows[0]],
                    [{**self.rows[0], "question": "forbidden invented content"}, *self.rows[1:]],
                    [{**self.rows[0], "type": "unknown"}, *self.rows[1:]]]
        for rows in variants:
            with self.subTest(reason=rows[0].keys()), self.assertRaises(ValueError):
                data.choose_ids(rows, set())

    def test_insufficient_unseen_population_cannot_change_mixture(self):
        with self.assertRaisesRegex(ValueError, "Insufficient unseen"):
            data.choose_ids(self.rows, {r["id"] for r in self.rows[:100]})

    def test_metadata_reader_requests_only_id_type(self):
        observed = []
        class Table:
            def to_pylist(inner):
                return [{"id": "invented", "type": "bridge"}]
        def reader(path, **options):
            observed.append((path, options))
            return Table()
        self.assertEqual(data.read_metadata("invented.parquet", reader), [{"id": "invented", "type": "bridge"}])
        self.assertEqual(observed, [("invented.parquet", {"columns": ["id", "type"]})])

    def test_selected_content_reader_filters_exact_ids_and_preserves_question_edges(self):
        selected = [{"id": "invented-b", "type": "comparison"}, {"id": "invented-a", "type": "bridge"}]
        records = [{"id": item["id"], "type": item["type"], "question": "  Invented question  ",
            "answer": "invented answer", "level": "fixture",
            "context": {"title": ["Invented Source"], "sentences": [["Invented fact."]]},
            "supporting_facts": {"title": ["Invented Source"], "sent_id": [0]}} for item in reversed(selected)]
        observed = []
        class Table:
            def to_pylist(inner):
                return records
        def reader(path, **options):
            observed.append(options)
            return Table()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invented.parquet"
            path.write_bytes(b"invented reader input; this is not a real data file")
            selection = {"selected": selected, "selected_ids": [x["id"] for x in selected]}
            dataset = data.load_dataset(path, {"parquet": {"sha256": data.sha(path)}}, selection, reader)
        self.assertEqual(observed, [{"columns": list(data.SOURCE_COLUMNS),
            "filters": [("id", "in", ["invented-b", "invented-a"])]}])
        self.assertEqual([q.id for q in dataset.queries], ["invented-b", "invented-a"])
        self.assertTrue(all(q.query == "  Invented question  " for q in dataset.queries))
        self.assertTrue(all(s["messages"] == [{"role": "user", "content": "Invented fact."}] for s in dataset.sessions))

    def test_changed_comparator_pin_cannot_pass_preselection_registration(self):
        scope = scope_fixture()
        candidate = {"commit": "a" * 40, "runtime_sha256": "b" * 64}
        registration = {"protocol": "round5-t1-fresh512-comparators-1", "status": "frozen-before-selection",
            "upstream_pins": copy.deepcopy(scope["comparators"]["pins"]), "candidate_source": candidate,
            "selection_manifest": "invented-selection.json", "top_k": 5,
            "tokenizers": ["cl100k_base", "o200k_base"], "token_budgets": [512, 1024, 2048]}
        registration["upstream_pins"][0]["commit"] = "c" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registration.json"
            path.write_text(json.dumps(registration))
            with patch.object(data, "committed"):
                with self.assertRaisesRegex(ValueError, "other sources/axes"):
                    data.comparator_registration(path, scope, candidate, "invented-selection.json")

    def test_bound_schedule_keeps_all_five_workers_identical(self):
        scope = scope_fixture()
        ids = ["invented-" + str(i) for i in range(512)]
        schedule = bench.call_schedule({"configurations": scope["native"]["configurations"]}, ids)
        self.assertEqual(len(schedule), 3072)
        self.assertEqual(len(schedule) * len(scope["native"]["workers"]), 15360)
        self.assertEqual([w["follow_titles"] for w in scope["native"]["workers"]], [False, False, True, True, False])
        self.assertEqual(len(set(schedule)), 3072)
        self.assertEqual(ids, ["invented-" + str(i) for i in range(512)])
        self.assertEqual(schedule, bench.call_schedule({"configurations": scope["native"]["configurations"]}, ids))


class FreshQualityAndStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.scope = scope_fixture()
        self.config = self.scope["native"]["configurations"][1]

    def test_exact_two_sided_test_handles_zero_and_boundary_discordance(self):
        self.assertEqual(bench.exact_discordance(0, 0)["two_sided_p"], 1)
        self.assertEqual(bench.exact_discordance(5, 0)["two_sided_p"], 0.0625)
        self.assertFalse(bench.exact_discordance(5, 0)["p_le_0_05"])
        self.assertEqual(bench.exact_discordance(6, 0)["two_sided_p"], 0.03125)
        self.assertTrue(bench.exact_discordance(6, 0)["p_le_0_05"])
        self.assertEqual(bench.exact_discordance(6, 1)["two_sided_p"], bench.exact_discordance(1, 6)["two_sided_p"])

    def test_primary_512_fixture_meets_all_quality_gates(self):
        value = bench.quality_cell(*paired_fixture(self.config), self.config, self.scope)
        self.assertTrue(value["passed"], value["failed_gates"])
        self.assertEqual(len(value["complete_gain_ids"]), 40)
        self.assertEqual(value["complete_loss_ids"], [])
        self.assertEqual(value["introduced_pages"], 40)
        self.assertEqual(value["introduced_hit_rate"], 1)
        self.assertEqual(value["displaced_hit_rate"], 0)
        self.assertAlmostEqual(value["deltas"]["complete_evidence_rate"], 40 / 512)
        self.assertAlmostEqual(value["deltas"]["evidence_recall"], 40 / 1024)

    def test_too_few_net_gains_and_too_many_losses_are_separate_failures(self):
        off, on = paired_fixture(self.config, after=225)
        value = bench.quality_cell(off, on, self.config, self.scope)
        self.assertIn("net_complete_gains", value["failed_gates"])
        off, on = paired_fixture(self.config, after=270)
        for i in range(26):
            on[i] = score_fixture(i, self.config, complete=False, enabled=True)
        value = bench.quality_cell(off, on, self.config, self.scope)
        self.assertEqual(len(value["complete_loss_ids"]), 26)
        self.assertIn("complete_losses", value["failed_gates"])

    def test_no_introduced_returned_pages_cannot_support_primary_claim(self):
        off, on = paired_fixture(self.config)
        for old, new in zip(off, on):
            new["annotated_pages"][1]["id"] = old["annotated_pages"][1]["id"]
        value = bench.quality_cell(off, on, self.config, self.scope)
        self.assertIsNone(value["introduced_hit_rate"])
        self.assertIn("introduced_page_hit_rate", value["failed_gates"])

    def test_zero_displaced_is_null_and_unreturned_target_does_not_count(self):
        off, on = paired_fixture(self.config)
        for old, new in zip(off, on):
            if new["title_reference"]["applied"]:
                new["annotated_pages"].append(copy.deepcopy(old["annotated_pages"][1]))
                new["result_count"] += 1
                new["annotated_page_precision"] = new["annotated_page_hits"] / new["result_count"]
        value = bench.quality_cell(off, on, self.config, self.scope)
        self.assertIsNone(value["displaced_hit_rate"])
        self.assertNotIn("introduced_vs_displaced", value["failed_gates"])
        old, new = copy.deepcopy(off[0]), copy.deepcopy(off[0])
        new["title_reference"] = {"target": {"page_id": "not-returned"}}
        change = bench.scoring.paired_changes(old, new)
        self.assertFalse(change["target_returned"])
        self.assertEqual(change["introduced"], [])

    def test_512_cell_disallows_even_one_complete_loss(self):
        config = self.scope["native"]["configurations"][0]
        off, on = paired_fixture(config, after=199)
        value = bench.quality_cell(off, on, config, self.scope)
        self.assertIn("hotpot512_complete_decline", value["failed_gates"])
        self.assertNotIn("complete_evidence_rate_regression", value["failed_gates"])

    def test_later_repetitions_never_count_as_quality_samples(self):
        off, on = paired_fixture(self.config)
        reports = [{"worker": {"index": i}, "rows": [
            {"configuration": self.config["index"], "score": copy.deepcopy(r)}
            for r in (on if i in (2, 3) else off)]} for i in range(5)]
        # Deliberately invalid repeat quality cannot repair first-pass quality.
        # Full execution independently verifies every stored row before assess.
        for report in (reports[3], reports[4]):
            for row in report["rows"]:
                row["score"]["complete"] = False
                row["score"]["matched_evidence"] = 0
        value = bench.assess(reports, {"configurations": [self.config]}, self.scope)
        self.assertTrue(value["native_gate_passed"], value["failed_gates"])
        self.assertEqual(value["cells"][0]["quality"]["on"]["queries"], 512)
        self.assertEqual(len(value["cells"][0]["quality"]["complete_gain_ids"]), 40)
        reports[4]["rows"][0]["score"]["native_payload_sha256"] = "0" * 64
        value = bench.assess(reports, {"configurations": [self.config]}, self.scope)
        self.assertFalse(value["native_gate_passed"])
        self.assertEqual(value["cells"][0]["payload_mismatches"][0]["workers"], [0, 4])


class FreshCostAndIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.scope = scope_fixture()
        self.config = self.scope["native"]["configurations"][1]

    def test_latency_enforces_both_absolute_and_relative_limits(self):
        for before, after in ((1.0, 1.3), (10.0, 11.5)):
            partitions = {i: [after if i in (2, 3) else before] * 512 for i in (1, 2, 3, 4)}
            value = bench.cost_cell(partitions, self.scope)
            self.assertEqual(value["failed_gates"], ["p50_ms_cost", "p95_ms_cost"])
            self.assertEqual(value["pooled"]["off"]["samples"], 1024)
        passing = bench.cost_cell({i: [1.1 if i in (2, 3) else 1.0] * 512 for i in (1, 2, 3, 4)}, self.scope)
        self.assertTrue(passing["passed"])

    def test_p95_failure_is_not_hidden_by_passing_median(self):
        partitions = {i: [1.0] * 512 for i in (1, 2, 3, 4)}
        for i in (2, 3):
            partitions[i] = [1.0] * 450 + [3.0] * 62
        value = bench.cost_cell(partitions, self.scope)
        self.assertEqual(value["failed_gates"], ["p95_ms_cost"])

    def test_missing_repeat_partition_cannot_be_substituted_or_pooled(self):
        with self.assertRaisesRegex(ValueError, "512 samples"):
            bench.cost_cell({i: [1.0] * 512 for i in (1, 2, 3)}, self.scope)

    def test_saved_score_recomputes_annotations_and_metadata_against_bound_inputs(self):
        row = score_fixture(10, self.config)
        expected = {name: row[name] for name in ("required_evidence", "project", "category")}
        expected.update(input_query=row["metadata_diagnostics"]["input_query"],
                        expected_query=row["metadata_diagnostics"]["expected"]["query"])
        bench.verify_score(row, self.config, expected, False)
        for field, bad in (("evidence_ranks", [1, 2]), ("matched_evidence", 2),
                           ("annotated_page_hits", 2), ("complete", True),
                           ("project", "another-project"), ("title_reference", {"version": 1})):
            altered = copy.deepcopy(row)
            altered[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                bench.verify_score(altered, self.config, expected, False)
        altered = copy.deepcopy(row)
        altered["metadata_diagnostics"]["actual"]["budget_tokens"] = 9999
        with self.assertRaisesRegex(ValueError, "Metadata diagnostics"):
            bench.verify_score(altered, self.config, expected, False)


class FreshRecoveryTests(unittest.TestCase):
    def locations(self, directory):
        base = Path(directory)
        return {"ticket": base / "ticket", "state": base / "state", "report": base / "report.json.gz",
                "ledger": base / "ledger.jsonl", "archive": base / "ledger.jsonl.gz"}

    def test_ticket_can_be_consumed_once_and_lost_state_cannot_replay_it(self):
        with tempfile.TemporaryDirectory() as directory:
            location = self.locations(directory)
            location["ticket"].write_bytes(b"invented-private-ticket")
            intent = {"ticket_sha256": bench.sha(location["ticket"])}
            bench.consume_ticket(location, intent)
            self.assertTrue(location["state"].is_dir())
            self.assertFalse(location["ticket"].exists())
            location["state"].rmdir()
            with self.assertRaisesRegex(ValueError, "never replay"):
                bench.consume_ticket(location, intent)

    def test_partial_report_prevents_launch_even_with_unused_ticket(self):
        with tempfile.TemporaryDirectory() as directory:
            location = self.locations(directory)
            location["ticket"].write_bytes(b"invented-private-ticket")
            location["report"].write_bytes(b"partial")
            with self.assertRaisesRegex(ValueError, "never replay"):
                bench.consume_ticket(location, {"ticket_sha256": bench.sha(location["ticket"])})
            self.assertTrue(location["ticket"].exists())

    def test_failed_final_validation_persists_failure_and_exact_original_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            location = self.locations(directory)
            original = b'{"event":"started","id":"invented"}\n'
            location["ledger"].write_bytes(original)
            report = {"status": "running", "error": None}
            with self.assertRaisesRegex(ValueError, "final invariant"):
                with bench.retain_attempt(report, location):
                    report["status"] = "completed"
                    raise ValueError("final invariant")
            saved = bench.read(location["report"])
            self.assertEqual(saved["status"], "failed_or_interrupted")
            self.assertEqual(saved["error"], {"type": "ValueError", "message": "final invariant"})
            self.assertEqual(location["ledger"].read_bytes(), original)
            self.assertEqual(gzip.decompress(location["archive"].read_bytes()), original)
            self.assertEqual(saved["ledger_sha256"], hashlib.sha256(original).hexdigest())

    def test_read_only_recovery_accepts_lossless_archive_but_rejects_changed_raw_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            location = self.locations(directory)
            original = b'{"invented":true}\n'
            location["archive"].write_bytes(gzip.compress(original, mtime=0))
            self.assertEqual(bench.ledger_bytes(location), original)
            location["ledger"].write_bytes(original + b"changed")
            with self.assertRaisesRegex(ValueError, "archive differs"):
                bench.ledger_bytes(location)

    def test_incomplete_worker_blocks_advancing_to_any_next_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            location = self.locations(directory)
            location["state"].mkdir()
            bound = {"workers": [{"index": i} for i in range(5)]}
            with patch.object(bench, "paths", return_value=location):
                with self.assertRaisesRegex(ValueError, "incomplete/out-of-order"):
                    bench.completed_prefix(bound, Path(directory) / "binding.json", {}, {})


if __name__ == "__main__":
    unittest.main()
