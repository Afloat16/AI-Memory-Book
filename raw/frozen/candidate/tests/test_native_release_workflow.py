"""Check release artifact selection across attempts without running Actions."""
from __future__ import annotations

import fnmatch
from pathlib import Path
import re
import unittest

from scripts import native_release


ROOT = Path(__file__).resolve().parents[1]


def workflow_jobs():
    # Read only the fixed indentation of this workflow, without adding a YAML
    # dependency to the standard-library package or silently skipping the gate.
    source = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    return dict(re.findall(r"^  ([a-z][a-z-]*):\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)",
                           source, re.MULTILINE | re.DOTALL))


def action_steps(job, action):
    steps = re.findall(r"^      - .*?(?=^      - |\Z)", job, re.MULTILINE | re.DOTALL)
    return [step for step in steps if re.search(r"\buses: " + re.escape(action) + "@", step)]


def field(step, name):
    values = re.findall(r"^          " + re.escape(name) + r": (.+)$", step, re.MULTILINE)
    if len(values) != 1:
        raise AssertionError(f"Expected one {name} input in the action step")
    return values[0].strip("'\"")


def render(template, *, run_id, attempt, target=""):
    context = {"github.run_id": str(run_id), "github.run_attempt": str(attempt),
               "matrix.target": target}
    return re.sub(r"\$\{\{\s*([a-z_.]+)\s*\}\}",
                  lambda match: context[match[1]], template)


class NativeReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.jobs = workflow_jobs()
        self.native = self.jobs["native-wheel"]
        self.uploads = action_steps(self.native, "actions/upload-artifact")

    def test_all_thirty_cells_use_their_matching_setup_python_executable(self):
        targets = re.findall(r"^          - target: ([a-z0-9_]+)$", self.native, re.MULTILINE)
        setup = action_steps(self.native, "actions/setup-python")
        versions = [field(step, "python-version") for step in setup]
        self.assertEqual(len(targets), 5)
        self.assertEqual(set(targets), set(native_release.TARGETS))
        self.assertEqual(len(versions), 6)
        self.assertEqual(set(versions), set(native_release.PYTHON_VERSIONS))
        cells = re.findall(r"^      - name: Build install and verify CPython (\d+\.\d+)\n"
                           r"(.*?)(?=^      - |\Z)", self.native, re.MULTILINE | re.DOTALL)
        self.assertEqual(len(cells), len(versions))
        self.assertEqual({version for version, _ in cells}, set(versions))
        for version, step in cells:
            digits = version.replace(".", "")
            self.assertIn(f"NATIVE_CELL_PYTHON: ${{{{ steps.py{digits}.outputs.python-path }}}}", step)
            self.assertIn(f"steps.py{digits}.outcome == 'success'", step)
            self.assertIn('"$NATIVE_CELL_PYTHON" scripts/build_native_release_cell.py', step)
            self.assertIn(f'--expected-python {version} --target "$WHEEL_TARGET"', step)
        self.assertEqual({(version, target) for version in versions for target in targets},
                         native_release.EXPECTED_MATRIX)

    def test_full_reruns_preserve_unique_wheel_and_evidence_artifacts(self):
        self.assertEqual(len(self.uploads), 2)
        names = []
        for step in self.uploads:
            self.assertIn("if: always()", step)
            self.assertNotRegex(step, r"\boverwrite:")
            for run_id in (12345, 67890):
                for attempt in (1, 2):
                    for target in native_release.TARGETS:
                        names.append(render(field(step, "name"), run_id=run_id,
                                            attempt=attempt, target=target))
        self.assertEqual(len(names), 40)
        self.assertEqual(len(set(names)), len(names), "A full rerun would collide with an earlier artifact")

    def test_each_aggregator_downloads_only_the_current_complete_attempt(self):
        wheel_uploads = [step for step in self.uploads
                         if field(step, "path") == ".artifacts/native-wheels/"]
        self.assertEqual(len(wheel_uploads), 1)
        template = field(wheel_uploads[0], "name")
        expected = {render(template, run_id=12345, attempt=2, target=target)
                    for target in native_release.TARGETS}
        available = set(expected)
        for run_id, attempt in ((12345, 1), (12345, 20), (67890, 2)):
            available.update(render(template, run_id=run_id, attempt=attempt, target=target)
                             for target in native_release.TARGETS)
        available.update("native-wheel-" + target for target in native_release.TARGETS)
        for job_name in ("release", "prepare-only"):
            with self.subTest(job=job_name):
                job = self.jobs[job_name]
                self.assertIn("needs: [preflight, native-wheel]", job)
                downloads = action_steps(job, "actions/download-artifact")
                self.assertEqual(len(downloads), 1)
                pattern = render(field(downloads[0], "pattern"), run_id=12345, attempt=2)
                self.assertEqual({name for name in available if fnmatch.fnmatchcase(name, pattern)}, expected)
                self.assertEqual(field(downloads[0], "merge-multiple"), "true")
                # Rerunning only one platform cannot find the other four in the
                # preceding attempt; the unchanged receipt validator then fails.
                current_one = next(iter(expected))
                partial = (available - expected) | {current_one}
                self.assertEqual({name for name in partial if fnmatch.fnmatchcase(name, pattern)}, {current_one})


if __name__ == "__main__":
    unittest.main()
