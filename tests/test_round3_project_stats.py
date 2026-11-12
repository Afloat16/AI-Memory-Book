"""Fabricated records only: no benchmark corpus retrieval or candidate scoring."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round3_project_stats as runner


def empty_scope():
    return {"initialized": False, "policy_version": None, "project": None, "revision": None,
        "page_count": 0, "builds": 0, "switches": 0, "last_build_ms": 0.0, "total_build_ms": 0.0,
        "temporary_storage": {"page_count": 0, "page_size": 4096, "freelist_count": 0,
            "allocated_bytes": 0, "live_bytes": 0, "temp_store_pragma": 0, "boundary": "fake"}}


def fixture():
    declaration = copy.deepcopy(runner.plan())
    for cohort in declaration["cohorts"]:
        cohort["queries"] = 12
    identities = {mode: {"commit": commit, "source_sha256": digest}
                  for mode, commit, digest in zip(runner.MODES,
                    (runner.BASELINE_COMMIT, runner.CANDIDATE_COMMIT), (runner.BASELINE_HASH, runner.CANDIDATE_HASH))}
    binding = {"modes": identities}
    report = {"plan": declaration, "binding": binding, "binding_sha256": "fake-binding",
        "workers": [], "attempted_workers": [], "error": None, "evaluator_hashes": {"fake": "sha"},
        "evaluator_unchanged": True}
    for name, mode in runner.expected_order():
        cohort = next(c for c in declaration["cohorts"] if c["name"] == name)
        ids = [name + "-fake-" + str(index) for index in range(12)]
        order = list(ids)
        random.Random(31061).shuffle(order)
        source = identities[mode]
        worker = {"cohort": name, "mode": mode, "status": "completed", "worker_exit_code": 0,
            "source": {"source_sha256": source["source_sha256"],
                "provenance": {"git_commit": source["commit"], "commit_identifies_source": True}},
            "source_sha256_after": source["source_sha256"], "dataset": {"queries": 12, "sha256": cohort["sha256"]},
            "query_ids": sorted(ids), "query_ids_original_order": ids, "evaluator_hashes": report["evaluator_hashes"],
            "binding_sha256": report["binding_sha256"], "evaluator_unchanged": True, "originals_unchanged": True,
            "indexed_content": {"fake": name}, "indexed_content_after": {"fake": name}, "cache_rows": 0,
            "configurations": [], "scope_initial": empty_scope(), "fresh_connection_initialize_ms": .1,
            "cli_stats_process_ms": .2, "ingestion_ms": .3, "memory_after_calls": {"rss_bytes": 10, "hwm_bytes": 20}}
        previous = empty_scope()
        for budget in runner.BUDGETS:
            rows = []
            for identity in order:
                project = None if name == "synthetic61" and identity.endswith("-0") else "fake-" + name
                applied = mode == runner.MODES[1] and project is not None
                after = copy.deepcopy(previous)
                if applied and not after["initialized"]:
                    after.update(initialized=True, policy_version=1, project="fake-" + name, revision=1,
                        page_count=2, builds=1, last_build_ms=.25, total_build_ms=.25)
                    after["temporary_storage"].update(page_count=8, allocated_bytes=32768, live_bytes=32768)
                matched = not identity.endswith("-0")
                rows.append({"id": identity, "project": project, "category": "fake", "answerable": True,
                    "required_evidence": 1, "matched_evidence": int(matched), "complete": matched,
                    "reciprocal_rank": 1.0 if matched else 0.0, "evidence_ranks": [1 if matched else None],
                    "stale_ranks": [], "stale_only": False, "stale_before_current": False, "nonempty": True,
                    "returned_characters": 10, "returned_utf8_bytes": 10, "context_size_consistent": True,
                    "budget_violation": False, "duplicate_source_characters": 0, "context_tokens": {e: 3 for e in runner.ENCODINGS},
                    "result_count": 1, "elapsed_ms": 1.0, "returned_payload_tokens": {e: 20 for e in runner.ENCODINGS},
                    "context_sha256": "fake-context", "diagnostic_groups": ["all", "category:fake", runner.GROUPS[0]],
                    "scope_cost": runner.scope_event(copy.deepcopy(previous), copy.deepcopy(after), mode, applied=applied),
                    "statistics_applied": applied, "non_timing_payload_sha256": "same-" + identity + "-" + str(budget),
                    "memory_after": {"rss_bytes": 10, "hwm_bytes": 20}, "query_has_terms": True, "archive_revision": 1,
                    **{key: 0 for key in runner.INVARIANTS}})
                previous = after
            worker["configurations"].append({"budget_chars": 8000, "budget_tokens": budget,
                "tokenizer": "cl100k_base", "rows": rows, **runner.summarize(rows)})
        worker["scope_final"] = previous
        report["workers"].append(worker)
        report["attempted_workers"].append({"cohort": name, "mode": mode, "status": "completed", "exit_code": 0})
    return declaration, binding, report


def write_artifacts(report, output):
    workers = []
    for original in report["workers"]:
        raw_path, ledger_path = runner.worker_paths(output, original["cohort"], original["mode"])
        body = {k: copy.deepcopy(v) for k, v in original.items() if k != "worker_exit_code"}
        ledger = runner.Ledger(ledger_path)
        for config in body["configurations"]:
            for row in config["rows"]:
                event = {"query_id": row["id"], "budget_tokens": config["budget_tokens"]}
                ledger.append({**event, "status": "started"})
                ledger.append({**event, "status": "completed", "row_sha256": runner.digest(row)})
        ledger.close()
        body["ledger_sha256"] = runner.sha(ledger_path.read_bytes())
        runner.write_json(raw_path, body, compressed=True)
        workers.append(runner.adopt_worker(raw_path, ledger_path, 0))
    report["workers"] = workers


class Round3ProjectStatisticsTests(unittest.TestCase):
    def test_complete_fabricated_matrix_and_cost_totals(self):
        _, _, report = fixture()
        result = runner.validate(report)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["calls"], 288)
        self.assertEqual(result["candidate_unscoped_global_calls"], 3)
        self.assertEqual(result["candidate_applied_calls"], 141)
        self.assertEqual(len(runner.comparisons(report)), 12)
        self.assertFalse(runner.screen(runner.comparisons(report), valid=True)["qualified"])
        self.assertEqual(runner.comparisons(json.loads(runner.canonical(report))), runner.comparisons(report))

    def test_malformed_axes_source_budget_cache_groups_or_costs_cannot_pass(self):
        for mutation in ("worker", "order", "budget", "query", "source", "cache", "aggregate",
                         "scope", "cost", "annotation", "oversize", "unscoped", "applied", "group", "exit"):
            _, _, report = fixture()
            worker = report["workers"][1]
            config = worker["configurations"][0]
            row = config["rows"][0]
            if mutation == "worker":
                report["workers"].pop()
            elif mutation == "order":
                report["workers"][:2] = reversed(report["workers"][:2])
            elif mutation == "budget":
                worker["configurations"].pop()
            elif mutation == "query":
                config["rows"].pop()
            elif mutation == "source":
                worker["source_sha256_after"] = "changed"
            elif mutation == "cache":
                worker["cache_rows"] = 1
            elif mutation == "aggregate":
                config["metrics"]["matched_evidence"] += 1
            elif mutation == "scope":
                row["scope_cost"]["after"]["project"] = "another-project"
            elif mutation == "cost":
                row["scope_cost"]["build_ms"] += 1
            elif mutation == "annotation":
                row["matched_evidence"] = 99
            elif mutation == "oversize":
                row["context_tokens"]["cl100k_base"] = 513
            elif mutation == "unscoped":
                next(r for r in config["rows"] if r["project"] is None)["non_timing_payload_sha256"] = "changed"
            elif mutation == "applied":
                row["statistics_applied"] = not row["statistics_applied"]
            elif mutation == "group":
                row["diagnostic_groups"].append("changed-case-group")
            else:
                worker["worker_exit_code"] = 1
            with self.subTest(mutation=mutation):
                self.assertFalse(runner.validate(report)["passed"])

    def test_any_declared_loss_blocks_gains_in_other_cells(self):
        _, _, report = fixture()
        cells = runner.comparisons(report)
        cells[0]["candidate"]["metrics"]["complete_evidence_rate"] = 1.0
        self.assertTrue(runner.screen(cells, valid=True)["qualified"])
        for negative in ("aggregate", "unsupported", "primary"):
            changed = copy.deepcopy(cells)
            if negative == "aggregate":
                changed[1]["candidate"]["metrics"]["evidence_recall"] = 0.0
            elif negative == "unsupported":
                changed[1]["candidate"]["unsupported_nonempty"] = 1
            else:
                changed[0]["by_group"][runner.GROUPS[0]]["after"]["evidence_recall"] = 0.0
            with self.subTest(negative=negative):
                result = runner.screen(changed, valid=True)
                self.assertFalse(result["qualified"])
                self.assertTrue(result["gains"])
                self.assertTrue(result["losses"])
        self.assertFalse(runner.screen(cells, valid=False)["qualified"])
        with self.assertRaises(ValueError):
            runner.screen(cells[:-1], valid=True)

    def test_small_group_and_individual_losses_remain_visible_without_changing_registered_gate(self):
        _, _, report = fixture()
        cells = runner.comparisons(report)
        cells[0]["candidate"]["metrics"]["complete_evidence_rate"] = 1.0
        group = cells[0]["by_group"][runner.GROUPS[0]]
        group["before"]["queries"] = group["after"]["queries"] = 9
        group["after"]["evidence_recall"] = 0.0
        cells[0]["paired_changes"]["complete_question_losses"] = ["retained-individual-loss"]
        result = runner.screen(cells, valid=True)
        self.assertTrue(result["qualified"])
        self.assertEqual(cells[0]["paired_changes"]["complete_question_losses"], ["retained-individual-loss"])
        self.assertFalse(result["individual_zero_loss_required"])

    def test_ledger_hash_binds_every_attempt_and_original_worker(self):
        _, _, report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "round3-project-stats-fixture.json.gz"
            write_artifacts(report, output)
            self.assertTrue(runner.validate(report, ledger_root=output.parent)["passed"])
            for worker in report["workers"]:
                runner.verify_worker_files(worker, output.parent)
            worker = report["workers"][0]
            ledger_path = output.parent / worker["ledger_file"]
            ledger_path.write_bytes(ledger_path.read_bytes() + b'{"status":"extra"}\n')
            self.assertFalse(runner.validate(report, ledger_root=output.parent)["passed"])
            with self.assertRaisesRegex(ValueError, "ledger"):
                runner.verify_worker_files(worker, output.parent)

    def test_saved_report_audit_preserves_rejection_and_recomputes_all_summaries(self):
        declaration, binding, report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "round3-project-stats-fixture.json.gz"
            binding_path = Path(directory) / "binding.json"
            runner.write_json(binding_path, binding)
            report["binding_sha256"] = runner.sha(binding_path.read_bytes())
            for worker in report["workers"]:
                worker["binding_sha256"] = report["binding_sha256"]
            write_artifacts(report, output)
            runner.save_report(output, report)
            with patch.object(runner, "registered", return_value=(declaration, binding)), \
                    patch.object(runner, "helper_hashes", return_value=report["evaluator_hashes"]):
                runner.audit(output, binding_path)
                _, summary_path, _ = runner.result_paths(output)
                saved = json.loads(summary_path.read_text())
                saved["screening"]["qualified"] = True
                runner.write_json(summary_path, saved)
                with self.assertRaisesRegex(ValueError, "summary"):
                    runner.audit(output, binding_path)

    def test_publication_refuses_unrelated_branch_before_git_actions(self):
        with patch.object(runner.subprocess, "run") as command:
            with self.assertRaises(ValueError):
                runner.publish(Path("/tmp/result.json.gz"), {}, "main")
            command.assert_not_called()

    def test_scope_cost_events_keep_builds_inside_complete_call_boundary(self):
        before = empty_scope()
        after = copy.deepcopy(before)
        after.update(initialized=True, project="one", revision=1, policy_version=1,
                     builds=1, last_build_ms=.2, total_build_ms=.2)
        self.assertEqual(runner.scope_event(before, after, runner.MODES[1])["kind"], "cold_build")
        switched = copy.deepcopy(after)
        switched.update(project="two", builds=2, switches=1, last_build_ms=.3, total_build_ms=.5)
        self.assertEqual(runner.scope_event(after, switched, runner.MODES[1])["kind"], "project_switch")
        self.assertEqual(runner.scope_event(after, after, runner.MODES[1])["kind"], "reuse")
        self.assertEqual(runner.scope_event(after, after, runner.MODES[1], needed=False)["kind"], "not_used")
        with self.assertRaises(ValueError):
            runner.scope_event(before, switched, runner.MODES[1])

    def test_controller_saves_a_spawn_failure_without_claiming_completion(self):
        declaration, binding, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "round3-project-stats-failure.json.gz"
            binding_path = Path(directory) / "binding.json"
            runner.write_json(binding_path, binding)
            args = SimpleNamespace(binding=binding_path, baseline_src=Path(directory) / "baseline",
                candidate_src=Path(directory) / "candidate", data_dir=Path(directory), output=output,
                resume=False, publish_branch=None)
            with patch.object(runner, "registered", return_value=(declaration, binding)), \
                    patch.object(runner, "verify_source", return_value={"fixture": True}), \
                    patch.object(runner, "helper_hashes", return_value={"fake": "sha"}), \
                    patch.object(runner, "git", return_value=b"fixture-commit"), \
                    patch.object(runner.platform, "platform", return_value="fixture platform"), \
                    patch.object(runner.importlib.metadata, "version", return_value="0.12.0"), \
                    patch.object(runner.subprocess, "run", side_effect=RuntimeError("fixture launch failure")):
                self.assertEqual(runner.run(args), 2)
            saved = json.loads(gzip.decompress(output.read_bytes()))
            self.assertEqual(saved["workers"], [])
            self.assertEqual(saved["attempted_workers"][0]["status"], "interrupted")
            self.assertEqual(saved["error"]["type"], "RuntimeError")
            self.assertFalse(saved["validation"]["passed"])
            self.assertFalse(saved["screening"]["qualified"])
            self.assertTrue(runner.result_paths(output)[1].exists())
            self.assertTrue(runner.result_paths(output)[2].exists())

    def test_resume_keeps_a_completed_worker_and_refuses_half_worker(self):
        declaration, binding, report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "round3-project-stats-resume.json.gz"
            binding_path = Path(directory) / "binding.json"
            runner.write_json(binding_path, binding)
            report["binding_sha256"] = runner.sha(binding_path.read_bytes())
            report["workers"] = report["workers"][:1]
            report["workers"][0]["binding_sha256"] = report["binding_sha256"]
            report["attempted_workers"] = report["attempted_workers"][:1]
            report["sources"] = {mode: {"fixture": mode} for mode in runner.MODES}
            write_artifacts(report, output)
            runner.save_report(output, report)
            first_path = output.parent / report["workers"][0]["files"]["raw"]
            original = first_path.read_bytes()
            args = SimpleNamespace(binding=binding_path, baseline_src=Path(directory) / "baseline",
                candidate_src=Path(directory) / "candidate", data_dir=Path(directory), output=output,
                resume=True, publish_branch=None)
            with patch.object(runner, "registered", return_value=(declaration, binding)), \
                    patch.object(runner, "verify_source", side_effect=lambda path, mode, binding: {"fixture": mode}), \
                    patch.object(runner, "helper_hashes", return_value=report["evaluator_hashes"]), \
                    patch.object(runner.subprocess, "run", side_effect=RuntimeError("stop before new fixture worker")) as launch:
                self.assertEqual(runner.run(args), 2)
                self.assertEqual(launch.call_count, 1)
                self.assertIn(runner.MODES[1], launch.call_args.args[0])
                self.assertEqual(first_path.read_bytes(), original)
                saved = json.loads(gzip.decompress(output.read_bytes()))
                self.assertEqual(len(saved["workers"]), 1)
                # A failed attempt is not made resumable by claiming that its
                # successfully saved prefix was the entire attempted matrix.
                with self.assertRaises(ValueError):
                    runner.run(args)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "native worker fixture needs optional exact tokenizers")
    def test_real_worker_on_three_artificial_queries_including_unscoped_and_empty_terms(self):
        from benchmarks.data import Dataset, Evidence, QueryCase
        import memory_book
        data = Dataset(seed=0, split="development", variant="artificial-worker-fixture")
        for project, sid, text in (("p", "a", "Alpha marker 71."), ("q", "b", "Beta marker 83.")):
            data.sessions.append({"project": project, "session_id": sid, "created_at": "2026-01-01T00:00:00Z",
                "messages": [{"role": "user", "content": text}]})
        data.queries = [QueryCase("scoped", "alpha", "fixture", "p", (Evidence("a", 0, "Alpha marker 71."),)),
                        QueryCase("unscoped", "beta", "fixture", None, (Evidence("b", 0, "Beta marker 83."),)),
                        QueryCase("empty-terms", "the and", "fixture", "p", (Evidence("a", 0, "Alpha marker 71."),))]
        source = Path(memory_book.__file__).resolve().parents[1]
        modes = runner.MODES if importlib.util.find_spec("memory_book.scoped") else runner.MODES[:1]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binding = directory / "binding.json"
            runner.write_json(binding, {"artificial_test": True})
            reports = []
            for mode in modes:
                args = SimpleNamespace(binding=binding, engine_src=source, mode=mode, cohort="artificial_fixture",
                    data_dir=directory, output=directory / (mode + ".json.gz"), ledger=directory / (mode + ".jsonl"))
                with patch.object(runner, "registered", return_value=(runner.plan(), {})), \
                        patch.object(runner, "verify_source", return_value={"fixture": True}), \
                        patch.object(runner, "dataset_for", return_value=data), \
                        patch.object(runner, "helper_hashes", return_value={"fake": "sha"}), \
                        patch.object(runner, "rss", return_value={"rss_bytes": 10, "hwm_bytes": 20}):
                    result = runner.worker(args)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(sum(len(c["rows"]) for c in result["configurations"]), 9)
                self.assertFalse(runner.ledger_errors(result, args.ledger))
                for config in result["configurations"]:
                    self.assertFalse(any(config["invariants"].values()))
                    unscoped = next(r for r in config["rows"] if r["id"] == "unscoped")
                    self.assertFalse(unscoped["statistics_applied"])
                    self.assertEqual(unscoped["scope_cost"]["kind"], "disabled" if mode == runner.MODES[0] else "unscoped_global")
                reports.append(result)
            if len(reports) == 2:
                for old, new in zip(reports[0]["configurations"], reports[1]["configurations"]):
                    a = next(row for row in old["rows"] if row["id"] == "unscoped")
                    b = next(row for row in new["rows"] if row["id"] == "unscoped")
                    self.assertEqual(a["non_timing_payload_sha256"], b["non_timing_payload_sha256"])


if __name__ == "__main__":
    unittest.main()
