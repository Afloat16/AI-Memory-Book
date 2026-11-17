"""Prospective directory-v2 acceptance and failure retention, without timing."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import directory_runtime_v2_preserve as preserve
from tests.test_comprehensive_runtime_preserve import IDENTITY, fixture as original_fixture, save


def save_report(work, report):
    events = [{"event": "started", "arguments": report["arguments"]}]
    for item in report["configurations"]:
        events.append({"event": "audit", "configuration": item["id"], "audit": item["audit"]})
        for trial in item["rounds"]:
            for position, arm in enumerate(trial["order"]):
                events.extend({"event": "call", "configuration": item["id"], "round": trial["round"],
                    "order_position": position, "arm": arm, **row} for row in trial["arms"][arm])
            events.append({"event": "round_completed", "configuration": item["id"], "round": trial["round"]})
        item["summary"] = {metric: preserve.summarize(item, metric) for metric in ("wall_ns", "process_cpu_ns")}
    events.append({"event": "completed", "configurations": len(report["configurations"])})
    save(work / "reports/directory-runtime.json", report)
    (work / "reports/directory-runtime.events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))


def fixture(work):
    manifest, _, report = original_fixture(work)
    manifest["protocol"] = preserve.PROTOCOL
    for name in ("src/memory_book/store.py", "src/memory_book/semantic.py", *preserve.EVALUATOR_PATHS):
        raw = (preserve.ROOT / name).read_bytes()
        path = "frozen/candidate/" + name
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest["files"][path] = {**preserve.shared.inventory(raw), "source": name, "commit": IDENTITY["commit"]}
    save(work / "source-manifest.json", manifest)
    report["protocol"] = preserve.PROTOCOL
    report["fixture"] = {"sha256": preserve.FIXTURE_SHA256, "target_sections": 100,
                         "target_pages_per_section": {"minimum": 130, "maximum": 130}}
    report["sources"]["candidate"]["source_sha256"] = preserve.STORE_SHA256
    report["sources"]["harness_sha256"] = preserve.shared.source_hash(manifest, "candidate", preserve.HARNESS)
    report["sources"]["protocol_sha256"] = preserve.shared.source_hash(manifest, "candidate", preserve.PLAN)
    for item in report["configurations"]:
        count = 4 + item["sections"]
        item["audit"]["candidate"].update(select_count=count, statement_count=count, statements=["SELECT 1"] * count)
    save_report(work, report)
    return manifest, report


def set_wall(report, sections, pages, candidate):
    item = next(item for item in report["configurations"] if (item["sections"], item["page_limit"]) == (sections, pages))
    for trial in item["rounds"]:
        for row in trial["arms"]["candidate"]:
            row["wall_ns"] = candidate


class DirectoryV2AuditTests(unittest.TestCase):
    def test_same_matrix_complete_ledger_and_new_query_counts_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            fixture(work)
            result = preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))
            self.assertEqual(result["state"], "accepted")
            self.assertEqual(result["remeasured_calls"], 0)
            self.assertEqual(result["directory"]["events"], 1487)
            self.assertEqual(result["directory"]["timed_calls"], 1440)

    def test_prospective_wall_ceiling_and_both_improvement_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            _, original = fixture(work)
            for sections, pages, candidate, expected in ((1, 1, 105, "accepted"), (1, 1, 106, "rejected"),
                    (20, 20, 100, "rejected"), (100, 20, 100, "rejected"), (100, 20, 99, "accepted")):
                with self.subTest(sections=sections, pages=pages, candidate=candidate):
                    report = copy.deepcopy(original)
                    set_wall(report, sections, pages, candidate)
                    save_report(work, report)
                    result = preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))
                    self.assertEqual(result["state"], expected)
                    row = next(row for row in result["directory"]["acceptance"]["configurations"]
                               if (row["sections"], row["page_limit"]) == (sections, pages))
                    self.assertEqual(row["wall"]["median_per_call"], {"baseline": 100, "candidate": candidate})
                    self.assertEqual(row["regressing_wall_pairs"], list(range(4)) if candidate > 100 else [])
                    # CPU remains faster even when wall latency rejects the candidate.
                    self.assertEqual(row["process_cpu"]["median_paired_ratio"], 0.5)

    def test_old_query_contract_missing_data_or_altered_fixture_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            manifest, original = fixture(work)
            mutations = {
                "old five-query candidate": lambda r: r["configurations"][3]["audit"]["candidate"].update(select_count=5, statement_count=5, statements=["SELECT 1"] * 5),
                "different fixture": lambda r: r["fixture"].update(sha256="f" * 64),
                "wrong attempt": lambda r: r["environment"].update(github_run_attempt="2"),
                "different source": lambda r: r["sources"]["candidate"].update(source_sha256="e" * 64),
                "selected subset": lambda r: r["configurations"].pop(),
                "missing call": lambda r: r["configurations"][0]["rounds"][0]["arms"]["baseline"].pop(),
                "different result": lambda r: r["configurations"][0]["rounds"][0]["arms"]["candidate"][0].update(exact_equality=False),
                "boolean clock": lambda r: r["configurations"][0]["rounds"][0]["arms"]["candidate"][0].update(wall_ns=True),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    report = copy.deepcopy(original)
                    mutate(report)
                    save_report(work, report)
                    self.assertEqual(preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))["state"], "incomplete")
            save_report(work, original)
            events = work / "reports/directory-runtime.events.jsonl"
            events.write_text("\n".join(line for line in events.read_text().splitlines() if json.loads(line)["event"] != "round_completed") + "\n")
            with self.assertRaisesRegex(ValueError, "ledger"):
                preserve.audit_directory(work, manifest, IDENTITY)
            save_report(work, original)
            outcomes = dict.fromkeys(preserve.STEPS, "success")
            outcomes["validate"] = "failure"
            self.assertEqual(preserve.audit_snapshot(work, IDENTITY, outcomes)["state"], "incomplete")

    def test_rejected_result_is_published_before_the_job_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / preserve.WORK_PATH
            _, report = fixture(work)
            set_wall(report, 100, 100, 140)
            save_report(work, report)
            original_verify = preserve.verify_frozen
            def verify(work, run, check_worktree=False):
                return original_verify(work, run)
            def publish(destination, branch):
                self.assertEqual(branch, "validation/evidence-comprehensive-v010-directory-v2-123-1")
                self.assertEqual((destination / "raw/reports/directory-runtime.json").read_bytes(), (work / "reports/directory-runtime.json").read_bytes())
                self.assertEqual(preserve.read(destination / "audit.json")["state"], "rejected")
                return {"commit": "b" * 40}
            environment = {"DIRECTORY_V2_" + name.upper() + "_OUTCOME": "success" for name in preserve.STEPS}
            with patch.object(preserve, "ROOT", root), patch.object(preserve, "identity", return_value=IDENTITY), \
                    patch.object(preserve, "verify_frozen", side_effect=verify), patch.object(preserve.shared, "clean_source"), \
                    patch.object(preserve.shared, "publish", side_effect=publish) as published, patch.dict(os.environ, environment), \
                    patch("builtins.print"):
                with self.assertRaisesRegex(ValueError, "Evidence preserved"):
                    preserve.preserve()
            published.assert_called_once()
            checkpoint = preserve.read(root / preserve.PRESERVATION_PATH / "preservation-result.json")
            self.assertEqual(checkpoint["stage"], "completed")
            self.assertEqual(checkpoint["audit"]["state"], "rejected")

    def test_dedicated_pipeline_and_attempt_guard(self):
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": preserve.REPOSITORY,
            "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/" + preserve.BRANCH,
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "123", "GITHUB_SHA": IDENTITY["commit"],
            "GITHUB_WORKFLOW_SHA": IDENTITY["commit"],
            "GITHUB_WORKFLOW_REF": preserve.REPOSITORY + "/" + preserve.WORKFLOW + "@refs/heads/" + preserve.BRANCH}
        with patch.object(preserve.shared, "git", return_value=SimpleNamespace(stdout=(IDENTITY["commit"] + "\n").encode())):
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(preserve.identity(), IDENTITY)
            for key, value in (("GITHUB_REF", "refs/heads/validation/comprehensive-v010-formal-1"),
                               ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_WORKFLOW_SHA", "b" * 40)):
                with self.subTest(key=key), patch.dict(os.environ, {**environment, key: value}, clear=True):
                    with self.assertRaises(ValueError):
                        preserve.identity()

    def test_frozen_originals_and_measurement_workload_are_unchanged(self):
        root = preserve.ROOT
        originals = {
            "scripts/benchmark_directory_runtime.py": "06bbe8d1aa50c9c14d6b753d3045c9b16987f15b0754c5e4818dfed5e84ccc5a",
            "benchmarks/directory-runtime-plan.json": "a05850a3f10752297bc65137bda71929a4e5d5efd90ad70bfb78ca83e88ad731",
            "scripts/comprehensive_runtime_preserve.py": "8183e44498adac27302490a5dca52b591a72e83f4eb9484d3719e431278a2400",
            ".github/workflows/comprehensive-runtime-performance.yml": "caebcedb2c9093bac83f484d719d492ae102124a55619701af706476abb919f8",
        }
        for name, expected in originals.items():
            self.assertEqual(preserve.sha((root / name).read_bytes()), expected, name)
        old = (root / "scripts/benchmark_directory_runtime.py").read_bytes()
        expected = old.replace(b'PLAN = "benchmarks/directory-runtime-plan.json"', b'PLAN = "benchmarks/directory-runtime-plan-v2.json"').replace(
            b'"protocol": "directory-runtime-v1"', b'"protocol": "directory-runtime-v2"')
        self.assertEqual((root / preserve.HARNESS).read_bytes(), expected)
        workflow = (root / preserve.WORKFLOW).read_text()
        self.assertIn("branches: ['" + preserve.BRANCH + "']", workflow)
        self.assertIn("github.run_attempt == 1", workflow)
        self.assertIn("--rounds 4 --iterations 20", workflow)
        self.assertNotIn("benchmark_semantic_runtime", workflow)
        self.assertIn("name: comprehensive-v010-directory-v2-${{ github.run_id }}-${{ github.run_attempt }}", workflow)
        plan = preserve.read(root / preserve.PLAN)
        criteria = plan["prospective_acceptance"]
        self.assertEqual(criteria["all_configurations_max_median_paired_wall_ratio"], preserve.MAX_WALL_RATIO)
        self.assertEqual(tuple((item["sections"], item["page_limit"]) for item in criteria["strict_improvement_required"]), preserve.REQUIRED_IMPROVEMENTS)
        self.assertTrue(all(item["median_paired_wall_ratio_less_than"] == 1.0 for item in criteria["strict_improvement_required"]))
        self.assertEqual(plan["candidate_source_sha256"], preserve.STORE_SHA256)
        self.assertEqual(plan["unchanged_semantic_source_sha256"], preserve.SEMANTIC_SHA256)
        self.assertEqual(plan["fixture"]["sha256"], preserve.FIXTURE_SHA256)


if __name__ == "__main__":
    unittest.main()
