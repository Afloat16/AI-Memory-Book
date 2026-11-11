"""Prevent benchmark reports from attributing changed code to an old release."""

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.component_eval import component_label
from benchmarks.token_compare import checkout_provenance, main


class ComparisonIdentityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "source checkout identity requires git")
    def test_checkout_and_source_changes_are_distinguished(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "memory_book"
            source.mkdir(parents=True)
            module = source / "__init__.py"
            module.write_text('__version__ = "0.3.0"\n', encoding="utf-8")

            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()

            git("init")
            git("add", "src")
            git("-c", "user.name=Benchmark fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-m", "baseline fixture")
            commit = git("rev-parse", "HEAD")
            clean = checkout_provenance(source)
            self.assertEqual(clean["git_commit"], commit)
            self.assertEqual(clean["repository_root"], str(root.resolve()))
            self.assertFalse(clean["git_dirty"])
            self.assertFalse(clean["source_dirty"])
            self.assertTrue(clean["commit_identifies_source"])

            # New measurement output dirties the checkout, but does not change
            # the measured package. The two flags must not be conflated.
            (root / "report.json").write_text("{}", encoding="utf-8")
            report_only = checkout_provenance(source)
            self.assertTrue(report_only["git_dirty"])
            self.assertFalse(report_only["source_dirty"])
            self.assertTrue(report_only["commit_identifies_source"])

            module.write_text('__version__ = "0.3.1"\n', encoding="utf-8")
            dirty = checkout_provenance(source)
            self.assertEqual(dirty["git_commit"], commit)
            self.assertTrue(dirty["source_dirty"])
            self.assertFalse(dirty["commit_identifies_source"])

            git("checkout", "--", "src")
            (source / "extra.py").write_text("FEATURE = True\n", encoding="utf-8")
            self.assertTrue(checkout_provenance(source)["source_dirty"])

    @unittest.skipUnless(shutil.which("git"), "source checkout identity requires git")
    def test_ignored_and_assume_unchanged_python_are_not_attributed_to_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "memory_book"
            source.mkdir(parents=True)
            module = source / "__init__.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            (root / ".gitignore").write_text("generated.py\n", encoding="utf-8")

            def git(*args):
                subprocess.run(["git", "-C", str(root), *args], check=True,
                               capture_output=True, text=True)

            git("init")
            git("add", ".")
            git("-c", "user.name=Benchmark fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-m", "baseline fixture")
            ignored = source / "generated.py"
            ignored.write_text("VALUE = 2\n", encoding="utf-8")
            provenance = checkout_provenance(source)
            self.assertTrue(provenance["source_dirty"])
            self.assertFalse(provenance["commit_identifies_source"])
            self.assertIn("src/memory_book/generated.py", provenance["python_files_differing_from_commit"])
            ignored.unlink()
            git("update-index", "--assume-unchanged", "src/memory_book/__init__.py")
            module.write_text("VALUE = 3\n", encoding="utf-8")
            provenance = checkout_provenance(source)
            self.assertTrue(provenance["source_dirty"])
            self.assertFalse(provenance["commit_identifies_source"])

    def test_unversioned_sources_do_not_claim_a_commit(self):
        # Some sandbox runtimes choose cwd as tempfile's writable default;
        # deliberately place this archive beside, not inside, the repository.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            result = checkout_provenance(Path(directory))
            self.assertIsNone(result["git_commit"])
            self.assertIsNone(result["git_dirty"])
            self.assertFalse(result["commit_identifies_source"])

    def test_cli_labels_reach_workers_without_becoming_paths(self):
        commands = []
        reports = []

        def fake_worker(command, **kwargs):
            commands.append(command)
            output = Path(command[command.index("--output") + 1])
            label = command[command.index("--label") + 1]
            self.assertEqual(output.name, f"engine-{len(commands) - 1}.json")
            output.write_text(json.dumps({"label": label, "dataset": {"sha256": "same", "queries": 1}}))

        arguments = ["token_compare", "--baseline-src", "/baseline/src",
                     "--candidate-src", "/candidate/src", "--baseline-label", "v0.3.0",
                     "--candidate-label", "candidate/working tree"]
        with patch.object(sys, "argv", arguments), \
                patch("benchmarks.token_compare.subprocess.run", side_effect=fake_worker), \
                patch("benchmarks.token_compare.write_artifacts", side_effect=lambda report, _: reports.append(report)), \
                patch("benchmarks.token_compare.comparison_markdown", return_value=""), \
                patch("benchmarks.token_compare.platform.platform", return_value="fixture"), \
                patch("builtins.print"):
            self.assertEqual(main(), 0)
        self.assertEqual([item["label"] for item in reports[0]["engines"]],
                         ["v0.3.0", "candidate/working tree"])
        for selector in ("baseline", "v0.2.1"):
            self.assertEqual(component_label(Namespace(engine=selector, baseline_label="v0.3.0")), "v0.3.0")
        self.assertEqual(component_label(Namespace(engine="candidate", candidate_label="new")), "new")


if __name__ == "__main__":
    unittest.main()
