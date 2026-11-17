"""Offline audit fixtures use dummy binary bytes; nothing is built or installed."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
import warnings
import zipfile

from scripts import audit_comprehensive_release as audit
from tests.test_native_release import TARGET_PLATFORMS


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def zipped(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return stream.getvalue()


def wheel(directory, identity, sources, version="3.10", target=None):
    tag = "cp" + version.replace(".", "") if target else "py3"
    abi, platform = (tag, TARGET_PLATFORMS[target]) if target else ("none", "any")
    name = f"ai_memory_book-{identity['version']}-{tag}-{abi}-{platform}.whl"
    members = dict(sources)
    if target:
        binary = (f"memory_book/_native.{tag}-win_amd64.pyd" if target == "windows_amd64"
                  else f"memory_book/_native.cpython-{version.replace('.', '')}-fixture.so")
        members[binary] = b"non-executable native metadata fixture " + name.encode()
    info = "ai_memory_book-" + identity["version"] + ".dist-info/"
    members[info + "METADATA"] = ("Metadata-Version: 2.4\nName: ai-memory-book\nVersion: "
                                  + identity["version"] + "\nRequires-Python: >=3.10\n\n").encode()
    members[info + "WHEEL"] = ("Wheel-Version: 1.0\nRoot-Is-Purelib: " + ("false" if target else "true")
                              + "\n" + "".join(f"Tag: {tag}-{abi}-{part}\n" for part in platform.split("."))).encode()
    members[info + "entry_points.txt"] = b"[console_scripts]\nmemory-book = memory_book.cli:main\n"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for member, raw in sorted(members.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        writer.writerow((member, "sha256=" + digest, len(raw)))
    writer.writerow((info + "RECORD", "", ""))
    members[info + "RECORD"] = stream.getvalue().encode()
    path = directory / name
    path.write_bytes(zipped(members))
    return audit.native.inspect_wheel(path, identity, sources, target=target)


class ReleaseFixture:
    """A complete tiny 30-cell release; its smoke declarations are synthetic."""

    def __init__(self, root, version="0.10.0"):
        self.root, self.run_id, self.attempt = root, 12345, 2
        self.native_baseline = "b" * 40
        self.identity = {"version": version, "tag": "v" + version, "commit": "a" * 40,
                         "tree": "c" * 40, "epoch": 1760000000, "runtime_sha256": "d" * 64}
        self.sources = {"memory_book/__init__.py": f'__version__ = "{version}"\n'.encode(),
                        "memory_book/static/index.html": b"<title>fixture</title>\n",
                        "memory_book/_native.c": b"/* metadata fixture, never compiled */\n"}
        self.inputs = {"src/" + name: raw for name, raw in self.sources.items()}
        self.inputs.update({"pyproject.toml": f'[project]\nname="ai-memory-book"\nversion="{version}"\n'.encode(),
                            "setup.py": b"# fixture\n", "README.md": b"fixture\n", "LICENSE": b"MIT\n"})
        self.source_files = {**self.inputs, **{name: (audit.ROOT / name).read_bytes()
                                              for name in (*audit.VALIDATORS, audit.WORKFLOW)}}
        self.source_files.update({"scripts/" + name: ("# fixture " + self.identity["tag"] + "\n").encode()
                                  for name in audit.release.INSTALLERS})
        self.snapshot = (self.identity, self.sources, self.inputs, self.source_files, {})
        self.metadata, self.archives, self.jobs, self.logs = {}, {}, {}, {}
        self.records, self.receipts = {}, {}
        self.public_dir = root / "public-assets"
        self.public_dir.mkdir()
        for name in ("metadata", "artifacts", "logs"):
            (root / name).mkdir()
        for index, target in enumerate(audit.native.TARGETS):
            self.add_platform(index, target)
        self.add_release()
        self.flush()

    def step(self, name, number):
        return {"name": name, "number": number, "status": "completed", "conclusion": "success"}

    def job(self, name, number, steps):
        return {"id": number, "name": name, "run_id": self.run_id, "run_attempt": self.attempt,
                "head_sha": self.identity["commit"], "status": "completed", "conclusion": "success",
                "runner_name": "fixture-runner-" + str(number), "steps": steps,
                "html_url": f"https://github.com/{audit.release.REPOSITORY}/actions/runs/{self.run_id}/job/{number}"}

    def add_platform(self, index, target):
        name = "native-wheel (" + target + ")"
        steps = [self.step(prefix + version, 2 * minor + offset)
                 for minor, version in enumerate(audit.native.PYTHON_VERSIONS)
                 for offset, prefix in ((1, "Set up CPython "), (2, "Build install and verify CPython "))]
        steps += [self.step("Retain each successfully tested wheel and receipt", 13),
                  self.step("Preserve all six native cell logs and validation records", 14)]
        job = self.jobs[name] = self.job(name, 100 + index, steps)
        evidence, output = {}, []
        for minor, version in enumerate(audit.native.PYTHON_VERSIONS):
            cp = "cp" + version.replace(".", "")
            executable = "C:/Python/" + cp + "/python.exe" if target == "windows_amd64" else "/python/" + cp
            cwd = "D:/checkout" if target == "windows_amd64" else "/checkout"
            work = cwd + "/.artifacts/native-build-cells/" + target + "/" + cp
            record = wheel(self.public_dir, self.identity, self.sources, version, target)
            repaired = work + "/repaired/" + record["filename"]
            commands = [("build-tools", [executable, "-m", "pip", "install", "setuptools==80.9.0",
                                         "wheel==0.45.1", "build==1.3.0"], "tools.log")]
            if target.startswith("linux_"):
                commands.append(("abi-tools", [executable, "-m", "pip", "install", "auditwheel==6.4.2",
                                                "patchelf==0.17.2.4"], "abi-tools.log"))
            build_log = "native-build-" + target + "-" + cp + ".log"
            commands.append(("compile-wheel", [executable, "-m", "pip", "wheel", "--verbose", "--no-deps",
                              "--no-build-isolation", "--wheel-dir", work + "/raw", "."], build_log))
            if target.startswith("linux_"):
                commands.append(("repair-wheel", [executable, "-m", "auditwheel", "repair", "--only-plat",
                                  "--plat", "manylinux_2_17_" + target.removeprefix("linux_"), "--wheel-dir",
                                  work + "/repaired", work + "/raw/raw.whl"], "repair.log"))
            if target.startswith("macos_"):
                commands.append(("macho-slices", ["lipo", "-archs", "/tmp/" + Path(record["native_member"]).name],
                                  "architecture.log"))
            commands += [("install-wheel", [executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", repaired], "install.log"),
                         ("isolated-native-import", [executable, "-I", "-c", "from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'"], "native-import.log"),
                         ("installed-native-tests", [executable, "-m", "unittest", *audit.cell.SUITES, "-v"], "test.log"),
                         ("installed-native-smoke-and-receipt", [executable, "scripts/native_release.py", "receipt", "--wheel", repaired,
                          "--output", repaired + ".receipt.json", "--target", target], "receipt.log")]
            compiler = "cl.exe /O2 /c memory_book/_native.c" if target == "windows_amd64" else "gcc -O3 -c memory_book/_native.c"
            skipped = (index + minor) % 4
            skip_lines = [f"{method} ({cls}) ... skipped {reason!r}" for method, cls, reason in audit.cell.ALLOWED_SKIPS[:skipped]]
            test_log = "\n".join(skip_lines + ["", "Ran 144 tests in 0.001s", "", "OK" + (f" (skipped={skipped})" if skipped else ""), ""])
            raw_logs = {filename: (phase + " fixture completed\n").encode() for phase, command, filename in commands}
            raw_logs[build_log] = (compiler + "\n").encode()
            raw_logs["test.log"] = test_log.encode()
            if target.startswith("macos_"):
                raw_logs["architecture.log"] = (target.removeprefix("macos_") + "\n").encode()
            entries = [{"phase": phase, "command": command, "cwd": cwd, "returncode": 0,
                        "elapsed_seconds": 0.001, "log": filename,
                        "log_bytes": len(raw_logs[filename]), "log_sha256": audit.sha(raw_logs[filename])}
                       for phase, command, filename in commands]
            tools = dict(audit.release.BUILD_TOOLS)
            if target.startswith("linux_"):
                tools["auditwheel"] = audit.native.AUDITWHEEL_VERSION
            smoke = {"backend": "native", "native_sha256": record["native_sha256"], "version": self.identity["version"],
                     "python_version": version, "source_files_match": True, "ingest_recall_sources_match": True}
            receipt = {"schema_version": 1,
                       "source": {"commit": self.identity["commit"], "tree": self.identity["tree"],
                                  "files_sha256": audit.native.file_hashes(self.inputs)},
                       "build": {"implementation": "cpython", "python_version": version, "python_tag": cp,
                                 "target": target, "tools": tools, "native_build_mode": "1",
                                 "extra_compile_args": ["/O2"] if target == "windows_amd64" else ["-O3"],
                                 "run_id": str(self.run_id), "run_attempt": self.attempt,
                                 "build_log": {"filename": build_log, "bytes": len(raw_logs[build_log]),
                                               "sha256": audit.sha(raw_logs[build_log]), "commands": [compiler]}},
                       "wheel": record, "runtime_smoke": smoke}
            receipt_name = record["filename"] + ".receipt.json"
            (self.public_dir / receipt_name).write_bytes(encoded(receipt))
            self.records[version, target] = {**record, "target": target, "python_version": version, "receipt": receipt_name}
            self.receipts[version, target] = receipt
            report = {"schema_version": 1, "status": "passed", "expected_python": version, "target": target,
                      "step_id": "cell" + version.replace(".", ""), "run_id": str(self.run_id), "run_attempt": str(self.attempt),
                      "runner_name": job["runner_name"],
                      "source": {key: self.identity[key] for key in ("version", "tag", "commit", "tree")}
                                | {"files_sha256": audit.native.file_hashes(self.inputs)},
                      "interpreter": {"implementation": "cpython", "python_version": version, "version": version + ".1 fixture",
                                      "setup_python_version": version + ".1", "executable": executable, "setup_python_path": executable},
                      "build_log": build_log, "commands": entries,
                      "tests": {**audit.cell.test_summary(test_log), "returncode": 0, "suites": list(audit.cell.SUITES),
                                "log": "test.log", "log_sha256": audit.sha(raw_logs["test.log"])},
                      "wheel": {key: record[key] for key in ("filename", "bytes", "sha256", "native_sha256")},
                      "receipt": {"filename": receipt_name, "sha256": audit.sha(encoded(receipt))}, "runtime_smoke": smoke}
            if target.startswith("macos_"):
                arch = target.removeprefix("macos_")
                report["macos_build"] = {"architecture": arch, "observed_slices": [arch]}
            evidence.update({cp + "/" + filename: raw for filename, raw in raw_logs.items()})
            evidence[cp + "/validation.json"] = encoded(report)
            output += [f'##[group]Run "$NATIVE_CELL_PYTHON" scripts/build_native_release_cell.py --expected-python {version} --target "$WHEEL_TARGET"',
                       "  NATIVE_CELL_PYTHON: " + executable, "  NATIVE_CELL_RESOLVED_VERSION: " + version + ".1",
                       "  NATIVE_CELL_STEP: " + report["step_id"], "  WHEEL_TARGET: " + target, "##[endgroup]"]
            for entry in entries:
                output += ["CELL COMMAND " + entry["phase"] + " " + json.dumps(entry["command"]), raw_logs[entry["log"]].decode().rstrip("\n")]
        suffix = str(self.run_id) + "-" + str(self.attempt) + "-" + target
        self.archives["native-cell-evidence-" + suffix] = evidence
        self.archives["native-wheel-" + suffix] = {record[key]: (self.public_dir / record[key]).read_bytes()
            for (version, platform), record in self.records.items() if platform == target for key in ("filename", "receipt")}
        self.logs[name] = "\n".join(output) + "\n"

    def add_release(self):
        fallback = wheel(self.public_dir, self.identity, self.sources)
        sdist = "ai_memory_book-" + self.identity["version"] + ".tar.gz"
        with tarfile.open(self.public_dir / sdist, "w:gz") as archive:
            for name, raw in self.inputs.items():
                info = tarfile.TarInfo("ai_memory_book-" + self.identity["version"] + "/" + name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
        for name in audit.release.INSTALLERS:
            (self.public_dir / name).write_bytes(self.source_files["scripts/" + name])
        self.manifest = {"schema_version": 2, **self.identity, "repository": audit.release.REPOSITORY,
                         "project": "ai-memory-book", "prerelease": False, "build_tools": audit.release.BUILD_TOOLS,
                         "native_build_run": {"run_id": str(self.run_id), "run_attempt": self.attempt},
                         "runtime_files_sha256": audit.native.file_hashes(self.sources),
                         "source_files_sha256": audit.native.file_hashes(self.inputs),
                         "python_fallback_wheel": fallback["filename"], "source_distribution": sdist,
                         "native_wheels": list(self.records.values()),
                         "assets": {path.name: {"bytes": path.stat().st_size, "sha256": audit.sha(path.read_bytes())}
                                    for path in self.public_dir.iterdir()}}
        (self.public_dir / "release-manifest.json").write_bytes(encoded(self.manifest))
        (self.public_dir / "SHA256SUMS").write_bytes("".join(audit.sha(path.read_bytes()) + "  " + path.name + "\n"
              for path in sorted(self.public_dir.iterdir())).encode())
        self.public = {path.name: path.read_bytes() for path in self.public_dir.iterdir()}
        self.archives[f"release-{self.run_id}-{self.attempt}"] = {"release-notes.md": b"Release fixture\n",
                                                                 **{"release-assets/" + name: raw for name, raw in self.public.items()}}
        (self.root / "public-install.py").write_bytes(self.public["install.py"])
        self.metadata["release"] = {"id": 777, "tag_name": self.identity["tag"], "target_commitish": self.identity["commit"],
            "draft": False, "prerelease": False, "body": "Release fixture\n", "published_at": "2026-11-17T00:00:00Z",
            "html_url": "https://github.com/" + audit.release.REPOSITORY + "/releases/tag/" + self.identity["tag"],
            "assets": [{"id": number, "name": name, "size": len(raw), "digest": "sha256:" + audit.sha(raw),
                        "state": "uploaded", "browser_download_url": "https://github.com/" + audit.release.REPOSITORY
                        + "/releases/download/" + self.identity["tag"] + "/" + name}
                       for number, (name, raw) in enumerate(self.public.items(), 500)]}
        self.metadata["latest-release"] = self.metadata["release"]
        self.metadata["commit"] = {"sha": self.identity["commit"], "commit": {"tree": {"sha": self.identity["tree"]}}}
        for name, ref in (("main-ref", "refs/heads/main"), ("tag-ref", "refs/tags/" + self.identity["tag"])):
            self.metadata[name] = {"ref": ref, "object": {"type": "commit", "sha": self.identity["commit"]}}
        for index, (name, steps) in enumerate((("preflight", ["Require the exact approved main commit and complete CI"]),
                ("release", ["Verify existing CI, build, check and publish", "Preserve release assets and checksums"]),
                ("published-install", [audit.PUBLISHED_STEP]))):
            self.jobs[name] = self.job(name, 200 + index, [self.step(step, number) for number, step in enumerate(steps, 1)])
            self.logs[name] = "successful job fixture\n"
        workflow = self.source_files[audit.WORKFLOW].decode()
        script = workflow.split("      - name: " + audit.PUBLISHED_STEP + "\n")[1].split("        run: |\n")[1]
        lines = [line[10:] for line in script.splitlines()]
        environment = ("\nenv:\n  RELEASE_TAG: " + self.identity["tag"]
                       + "\n  RELEASE_VERSION: " + self.identity["version"]
                       + "\n  RELEASE_COMMIT: " + self.identity["commit"])
        self.logs["published-install"] = ("##[group]Run " + "\n".join(lines) + environment
            + "\n##[endgroup]\nDefault text backend: native\n" + audit.PUBLISHED_MARKER + "\n")
        self.metadata["run"] = {"id": self.run_id, "run_attempt": self.attempt, "head_sha": self.identity["commit"],
            "head_branch": "release/" + self.identity["tag"], "path": audit.WORKFLOW, "event": "push",
            "status": "completed", "conclusion": "success", "head_repository": {"full_name": audit.release.REPOSITORY},
            "html_url": f"https://github.com/{audit.release.REPOSITORY}/actions/runs/{self.run_id}"}
        ci_run = {**self.metadata["run"], "id": 12344, "run_attempt": 3, "path": ".github/workflows/ci.yml"}
        self.metadata["ci-runs"] = {"total_count": 1, "workflow_runs": [ci_run]}
        ci_jobs = [{**self.job(name, number, []), "run_id": 12344, "run_attempt": 3}
                   for number, name in enumerate(sorted(audit.release.EXPECTED_JOBS), 300)]
        self.metadata["ci-jobs"] = {"total_count": len(ci_jobs), "jobs": ci_jobs}

    def flush(self):
        artifacts = []
        for number, (name, members) in enumerate(self.archives.items(), 900):
            raw = zipped(members)
            (self.root / "artifacts" / f"{number}.zip").write_bytes(raw)
            artifacts.append({"id": number, "name": name, "expired": False, "size_in_bytes": len(raw),
                              "digest": "sha256:" + audit.sha(raw),
                              "workflow_run": {"id": self.run_id, "head_sha": self.identity["commit"]}})
        self.metadata["artifacts"] = {"total_count": len(artifacts), "artifacts": artifacts}
        self.metadata["jobs"] = {"total_count": len(self.jobs), "jobs": list(self.jobs.values())}
        for name, value in self.metadata.items():
            (self.root / "metadata" / (name + ".json")).write_bytes(encoded(value))
        for name, raw in self.logs.items():
            (self.root / "logs" / (str(self.jobs[name]["id"]) + ".log")).write_bytes(raw.encode())

    def run(self):
        return audit.audit(audit.Evidence(self.root), self.snapshot, self.run_id, self.attempt, self.native_baseline)

    def cells(self):
        return audit.audit_cells(self.identity, self.manifest, self.records, self.receipts, self.public,
                                 self.archives, self.jobs, self.logs, self.run_id, self.attempt)

    def replace_first_test_log(self, text):
        target, version = audit.native.TARGETS[0], audit.native.PYTHON_VERSIONS[0]
        files = self.archives[f"native-cell-evidence-{self.run_id}-{self.attempt}-{target}"]
        prefix = "cp" + version.replace(".", "") + "/"
        old = files[prefix + "test.log"]
        raw = files[prefix + "test.log"] = text.encode()
        report = json.loads(files[prefix + "validation.json"])
        report["tests"] = {**audit.cell.test_summary(text), "returncode": 0, "suites": list(audit.cell.SUITES),
                           "log": "test.log", "log_sha256": audit.sha(raw)}
        command = next(entry for entry in report["commands"] if entry["phase"] == "installed-native-tests")
        command.update(log_bytes=len(raw), log_sha256=audit.sha(raw))
        files[prefix + "validation.json"] = encoded(report)
        name = "native-wheel (" + target + ")"
        self.logs[name] = self.logs[name].replace(old.decode().rstrip("\n"), text.rstrip("\n"), 1)


class ComprehensiveReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release-audit-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = ReleaseFixture(Path(self.temporary.name))

    def test_complete_matrix_current_schema_and_all_allowed_skip_subsets(self):
        before = {path: audit.sha(path.read_bytes()) for path in self.fixture.root.rglob("*") if path.is_file()}
        proof = self.fixture.run()
        self.assertEqual(proof["status"], "passed")
        self.assertEqual(proof["source"]["version"], "0.10.0")
        self.assertEqual(proof["workflow"]["run_attempt"], 2)
        self.assertEqual(proof["counts"]["native_cells"], 30)
        self.assertEqual(proof["counts"]["native_test_outcomes"], 4320)
        self.assertEqual(proof["counts"]["public_assets"], 67)
        self.assertEqual(proof["counts"]["manifest_payloads"], 65)
        self.assertEqual(proof["counts"]["checksum_entries"], 66)
        self.assertEqual({record["tests"]["skipped"] for record in proof["native_cells"]}, {0, 1, 2, 3})
        self.assertEqual(len(proof["artifacts"]), 11)
        self.assertEqual(before, {path: audit.sha(path.read_bytes()) for path in self.fixture.root.rglob("*") if path.is_file()})

    def test_version_is_parameterized_instead_of_reusing_v9_literals(self):
        with tempfile.TemporaryDirectory() as location:
            fixture = ReleaseFixture(Path(location), version="0.8.0")
            self.assertEqual(fixture.run()["source"]["tag"], "v0.8.0")

    def test_old_attempt_jobs_and_artifact_names_are_rejected(self):
        self.fixture.jobs["native-wheel (linux_x86_64)"]["run_attempt"] = 1
        self.fixture.flush()
        with self.assertRaisesRegex(ValueError, "another source/run/attempt"):
            self.fixture.run()
        self.fixture.jobs["native-wheel (linux_x86_64)"]["run_attempt"] = 2
        key = "native-wheel-12345-2-linux_x86_64"
        self.fixture.archives["native-wheel-linux_x86_64"] = self.fixture.archives.pop(key)
        self.fixture.flush()
        with self.assertRaisesRegex(ValueError, "current-attempt artifacts"):
            self.fixture.run()

    def test_public_file_tampering_is_rejected(self):
        (self.fixture.public_dir / "install.py").write_bytes(b"unrelated public bytes\n")
        with self.assertRaisesRegex(ValueError, "Public asset differs"):
            self.fixture.run()

    def test_original_grouped_wheel_bytes_must_match_published_bytes(self):
        members = self.fixture.archives["native-wheel-12345-2-linux_x86_64"]
        name = next(name for name in members if name.endswith(".whl"))
        members[name] += b"changed original artifact"
        self.fixture.flush()
        with self.assertRaisesRegex(ValueError, "Grouped wheel artifact differs"):
            self.fixture.run()

    def test_unknown_skip_and_success_after_failure_are_rejected(self):
        self.fixture.replace_first_test_log("test_hidden (tests.unrelated.RequiredTest) ... skipped 'disabled'\n\nRan 144 tests in 1s\n\nOK (skipped=1)\n")
        with self.assertRaisesRegex(RuntimeError, "Unexpected or duplicate skipped"):
            self.fixture.cells()
        self.fixture.replace_first_test_log("ERROR: test_hidden (tests.RequiredTest)\n\nRan 144 tests in 1s\n\nOK\n")
        with self.assertRaisesRegex(RuntimeError, "must not contain failures"):
            self.fixture.cells()

    def test_duplicate_or_incomplete_test_summary_is_rejected(self):
        self.fixture.replace_first_test_log("Ran 144 tests in 1s\n\nOK\nRan 144 tests in 1s\n\nOK\n")
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            self.fixture.cells()
        self.fixture.replace_first_test_log("Ran 143 tests in 1s\n\nOK\n")
        with self.assertRaisesRegex(RuntimeError, "all 144"):
            self.fixture.cells()

    def test_test_or_compiler_log_cannot_be_detached_from_actual_job(self):
        name = "native-wheel (linux_x86_64)"
        self.fixture.logs[name] = self.fixture.logs[name].replace("gcc -O3 -c memory_book/_native.c", "missing compiler output", 1)
        with self.assertRaisesRegex(ValueError, "raw output absent"):
            self.fixture.cells()

    def test_published_installer_needs_executed_marker_not_just_printed_source(self):
        self.fixture.logs["published-install"] = self.fixture.logs["published-install"].removesuffix(audit.PUBLISHED_MARKER + "\n")
        self.fixture.flush()
        with self.assertRaisesRegex(ValueError, "did not report"):
            self.fixture.run()

    def test_published_installer_requires_unique_step_scoped_release_identity(self):
        original = self.fixture.logs["published-install"]
        expected = {"RELEASE_TAG": self.fixture.identity["tag"],
                    "RELEASE_VERSION": self.fixture.identity["version"],
                    "RELEASE_COMMIT": self.fixture.identity["commit"]}
        for key, value in expected.items():
            line = "  " + key + ": " + value + "\n"
            for replacement in ("", "  " + key + ": unrelated-release\n", line + line):
                changed = original.replace(line, replacement)
                with self.subTest(key=key, replacement=replacement), self.assertRaisesRegex(ValueError, "step environment differs"):
                    audit.published_installer_proof(self.fixture.source_files[audit.WORKFLOW],
                        self.fixture.jobs["published-install"], changed, self.fixture.identity)
        # Correct values elsewhere in the job cannot repair a missing step env.
        absent = original.replace("  RELEASE_COMMIT: " + self.fixture.identity["commit"] + "\n", "")
        with self.assertRaisesRegex(ValueError, "step environment differs"):
            audit.published_installer_proof(self.fixture.source_files[audit.WORKFLOW],
                self.fixture.jobs["published-install"], "RELEASE_COMMIT: " + self.fixture.identity["commit"]
                + "\n" + absent, self.fixture.identity)

    def test_attempt_jobs_pagination_cannot_be_silently_truncated(self):
        document = {"total_count": 2, "jobs": [{"id": 1}]}
        with self.assertRaisesRegex(ValueError, "Incomplete paginated"):
            audit.collection(document, "jobs")

    def test_archive_links_duplicate_names_and_traversal_are_rejected(self):
        for name in ("../outside", "/absolute", "back\\slash"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe evidence path"):
                audit.zip_members(zipped({name: b"x"}))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo("linked")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
        with self.assertRaisesRegex(ValueError, "Linked or special"):
            audit.zip_members(stream.getvalue())
        stream = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(stream, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            archive.writestr("duplicate", b"first")
            archive.writestr("duplicate", b"second")
        with self.assertRaisesRegex(ValueError, "Duplicate artifact member"):
            audit.zip_members(stream.getvalue())


if __name__ == "__main__":
    unittest.main()
