"""Preflight uses the requested corpus plan and preserves failed diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import preflight


def corpus(kind="synthetic", split="heldout", seed=211, projects=8, max_queries=0, **extra):
    return {"corpus": kind, "split": split, "seed": seed, "projects": projects,
            "max_queries": max_queries, **extra}


class PreflightPlanTests(unittest.TestCase):
    def run_plan(self, corpora, *, behavior=None, locomo=True):
        commands = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "preflight.json"
            arguments = ["preflight", "--baseline-src", str(root / "baseline-src"),
                         "--candidate-src", str(root / "candidate-src"),
                         "--baseline-label", "preserved/v0.3", "--candidate-label", "candidate/quality",
                         "--output", str(output)]
            if corpora is not None:
                plan = root / "corpora.json"
                plan.write_text(json.dumps(corpora), encoding="utf-8")
                arguments += ["--corpora-json", str(plan)]
            if locomo:
                arguments += ["--locomo-path", str(root / "locomo.json")]

            def worker(command, **kwargs):
                commands.append(command)

                def value(flag):
                    return command[command.index(flag) + 1]

                source = value("--engine-src")
                record = {"label": value("--baseline-label"),
                          "dataset": {"sha256": ":".join(value(flag) for flag in
                                      ("--corpus", "--split", "--seed", "--projects", "--max-queries"))},
                          "source_provenance": {"source_root": source, "git_commit": "fixture"},
                          "source_sha256_before": source, "source_sha256_after": source,
                          "source_unchanged": True,
                          "evidence_attainability": {"unattainable_single_page_labels": []}}
                code = 0
                if behavior is not None:
                    record, code = behavior(len(commands) - 1, record)
                if record is not None:
                    Path(value("--output")).write_text(json.dumps(record), encoding="utf-8")
                return subprocess.CompletedProcess(command, code)

            with patch.object(sys, "argv", arguments), patch.object(preflight.subprocess, "run", side_effect=worker), \
                    patch("builtins.print"):
                code = preflight.main()
            return code, json.loads(output.read_text(encoding="utf-8")), commands

    def test_explicit_plan_preserves_every_seed_limit_source_and_display_label(self):
        corpora = [corpus(split="development", seed=61), corpus(seed=211), corpus(seed=509),
                   corpus("locomo", "development", 61, max_queries=128),
                   corpus("locomo", "heldout", 61, max_queries=256, label="regression/256"),
                   corpus("locomo", "heldout", 61, max_queries=0, label="expanded/1015")]
        code, report, commands = self.run_plan(corpora)
        self.assertEqual(code, 0)
        self.assertTrue(report["validation"]["passed"])
        self.assertEqual(report["corpora"], corpora)
        self.assertEqual(len(commands), 12)
        self.assertIn("explicit", report["scope"])
        outputs = [Path(command[command.index("--output") + 1]).name for command in commands]
        self.assertEqual(len(set(outputs)), 12)
        for command, record in zip(commands, report["records"]):
            expected = corpora[record["corpus_index"]]
            self.assertEqual(record["corpus_plan"], expected)
            for key in ("corpus", "split", "seed", "projects", "max_queries"):
                flag = "--" + key.replace("_", "-")
                self.assertEqual(command[command.index(flag) + 1], str(expected[key]))
            self.assertEqual(command[command.index("--baseline-label") + 1], record["label"])
            self.assertEqual(record["label"], report["source_labels"][record["engine_selector"]])
            self.assertEqual(record["source_provenance"]["source_root"], record["requested_source"])
            self.assertTrue(record["requested_source"].endswith(record["engine_selector"] + "-src"))

    def test_default_is_explicitly_historical_and_retains_original_selections(self):
        code, report, commands = self.run_plan(None)
        self.assertEqual(code, 0)
        self.assertEqual(len(commands), 10)
        self.assertEqual(report["corpora"], list(preflight.HISTORICAL_CORPORA))
        self.assertEqual([item["seed"] for item in report["corpora"][:3]], [61, 113, 307])
        self.assertIn("historical", report["scope"])
        self.assertIsNone(report["plan_path"])

    def test_failed_source_and_unattainable_evidence_are_saved_without_skipping_inputs(self):
        def fail(index, record):
            if index == 0:
                record["source_sha256_after"] = "changed"
                record["source_unchanged"] = False
                record["evidence_attainability"]["unattainable_single_page_labels"] = [
                    {"query_id": "q-long", "annotation_chars": 1000}]
                return record, 2
            return record, 0

        code, report, commands = self.run_plan([corpus(seed=211), corpus(seed=509)], behavior=fail)
        self.assertEqual(code, 2)
        self.assertEqual(len(commands), 4)
        self.assertFalse(report["validation"]["passed"])
        self.assertEqual(report["unattainable_labels"], 1)
        self.assertEqual(report["records"][0]["source_provenance"]["git_commit"], "fixture")
        self.assertEqual(report["records"][0]["evidence_attainability"]["unattainable_single_page_labels"][0]["query_id"], "q-long")
        checks = {item["check"] for item in report["validation"]["failures"]}
        self.assertTrue({"source_unchanged", "worker_exit_code", "unattainable_single_page_labels"} <= checks)

    def test_crashed_export_does_not_reuse_another_corpus_report_or_lose_diagnostics(self):
        def crash(index, record):
            return (None, 1) if index == 1 else (record, 0)

        code, report, commands = self.run_plan([corpus(seed=211), corpus(seed=509)], behavior=crash)
        self.assertEqual(code, 2)
        self.assertEqual(len(commands), 4)
        failed = report["records"][1]
        self.assertEqual(failed["corpus_plan"]["seed"], 509)
        self.assertIn("export_error", failed)
        self.assertNotIn("evidence_attainability", failed)
        self.assertFalse(report["validation"]["passed"])

    def test_synthetic_only_plan_needs_no_locomo_file(self):
        code, report, commands = self.run_plan([corpus(projects=3)], locomo=False)
        self.assertEqual(code, 0)
        self.assertTrue(all("--locomo-path" not in command for command in commands))
        self.assertEqual(report["records"][0]["corpus_plan"]["projects"], 3)

    def test_malformed_or_unsupported_plans_are_not_silently_defaulted(self):
        invalid = [[], {}, [corpus(seed=True)], [corpus(projects=0)],
                   [corpus(max_queries=-1)], [corpus(max_queries=1)],
                   [corpus(kind="other")], [corpus(split="test")], [corpus(label="")],
                   [{"corpus": "synthetic"}], [{**corpus(), "max_query": 5}]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpora.json"
            for plan in invalid:
                with self.subTest(plan=plan):
                    path.write_text(json.dumps(plan), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        preflight.load_corpora(path)
        first = preflight.load_corpora(None)
        first[0]["seed"] = 1
        self.assertEqual(preflight.load_corpora(None)[0]["seed"], 61)


if __name__ == "__main__":
    unittest.main()
