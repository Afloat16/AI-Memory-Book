"""Release metadata fixtures: no GitHub calls, native execution or publication.

Dummy extension bytes exercise rejection of damaged/misattributed packages.
Only the production receipt command records an actual installed-native smoke.
"""

from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import native_release as native


IDENTITY = {"version": "0.8.0", "tag": "v0.8.0", "commit": "a" * 40,
            "tree": "b" * 40, "epoch": 1760000000, "runtime_sha256": "c" * 64}
SOURCES = {"memory_book/__init__.py": b'__version__ = "0.8.0"\n',
           "memory_book/text.py": b"VALUE = 'source fixture'\n",
           "memory_book/_native.c": b"/* committed native source fixture */\n",
           "memory_book/_native_core.h": b"/* committed native header fixture */\n",
           "memory_book/static/index.html": b"<!doctype html><title>Memory Book</title>\n"}
TARGET_PLATFORMS = {
    "linux_x86_64": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    "linux_aarch64": "manylinux_2_17_aarch64.manylinux2014_aarch64",
    "macos_x86_64": "macosx_10_9_x86_64", "macos_arm64": "macosx_11_0_arm64",
    "windows_amd64": "win_amd64",
}


def write_zip(path, members, *, record=True):
    members = dict(members)
    info_root = "ai_memory_book-0.8.0.dist-info/"
    if record:
        members.pop(info_root + "RECORD", None)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        for name, data in sorted(members.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            writer.writerow((name, "sha256=" + digest, len(data)))
        writer.writerow((info_root + "RECORD", "", ""))
        members[info_root + "RECORD"] = buffer.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def wheel_fixture(directory, *, python="3.12", target="linux_x86_64", sources=None, abi=None):
    sources = SOURCES if sources is None else sources
    python_tag = "py3" if target is None else "cp" + python.replace(".", "")
    abi_tag = ("none" if target is None else python_tag) if abi is None else abi
    platform_tag = "any" if target is None else TARGET_PLATFORMS[target]
    path = directory / f"ai_memory_book-0.8.0-{python_tag}-{abi_tag}-{platform_tag}.whl"
    members = dict(sources)
    if target is not None:
        if target == "windows_amd64":
            member = f"memory_book/_native.{python_tag}-win_amd64.pyd"
        else:
            suffix = {"linux_x86_64": "x86_64-linux-gnu", "linux_aarch64": "aarch64-linux-gnu",
                      "macos_x86_64": "darwin", "macos_arm64": "darwin"}[target]
            member = f"memory_book/_native.cpython-{python.replace('.', '')}-{suffix}.so"
        members[member] = b"dummy extension bytes for metadata tests only: " + python.encode() + target.encode()
    info_root = "ai_memory_book-0.8.0.dist-info/"
    members[info_root + "METADATA"] = b"Metadata-Version: 2.4\nName: ai-memory-book\nVersion: 0.8.0\nRequires-Python: >=3.10\nLicense: MIT\n\n"
    tags = "".join(f"Tag: {python_tag}-{abi_tag}-{tag}\n" for tag in platform_tag.split("."))
    members[info_root + "WHEEL"] = ("Wheel-Version: 1.0\nRoot-Is-Purelib: " +
        ("true" if target is None else "false") + "\n" + tags).encode()
    members[info_root + "entry_points.txt"] = b"[console_scripts]\nmemory-book = memory_book.cli:main\n"
    write_zip(path, members)
    return path


def write_sdist(path, inputs, *, extra=None):
    members = dict(inputs)
    members["PKG-INFO"] = b"Name: ai-memory-book\nVersion: 0.8.0\n"
    if extra:
        members.update(extra)
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            item = tarfile.TarInfo("ai_memory_book-0.8.0/" + name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))


class NativeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-release-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.supplied = self.root / "native-wheels"
        self.supplied.mkdir()
        for name, data in {
            "pyproject.toml": b'[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "ai-memory-book"\nversion = "0.8.0"\n',
            "setup.py": b"# committed build configuration fixture\n",
            "README.md": b"Release fixture\n", "LICENSE": b"MIT\n",
        }.items():
            (self.root / name).write_bytes(data)
        self.inputs = native.source_inputs(self.root, SOURCES)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "2"}).start()

    def receipt(self, wheel, *, target="linux_x86_64", python="3.12"):
        actual = native.inspect_wheel(wheel, IDENTITY, SOURCES, target=target)
        tools = dict(native.legacy.BUILD_TOOLS)
        if target.startswith("linux_"):
            tools["auditwheel"] = native.AUDITWHEEL_VERSION
        flags = ["/O2"] if target == "windows_amd64" else ["-O3"]
        command = ('"C:\\Compiler\\cl.exe" /c /O2 src/memory_book/_native.c /Fobuild/_native.obj'
                   if target == "windows_amd64" else "gcc -c src/memory_book/_native.c -o build/_native.o -O3")
        raw_log = (command + "\n").encode()
        value = {"schema_version": 1,
            "source": {"commit": IDENTITY["commit"], "tree": IDENTITY["tree"],
                       "files_sha256": native.file_hashes(self.inputs)},
            "build": {"implementation": "cpython", "python_version": python,
                      "python_tag": "cp" + python.replace(".", ""), "target": target,
                      "tools": tools, "run_id": "12345", "run_attempt": 2,
                      "native_build_mode": "1", "extra_compile_args": flags,
                      "build_log": {"filename": "native-build.log", "bytes": len(raw_log),
                                    "sha256": native.sha(raw_log), "commands": [command]}},
            "wheel": actual,
            "runtime_smoke": {"backend": "native", "native_sha256": actual["native_sha256"],
                "version": "0.8.0", "python_version": python,
                "source_files_match": True, "ingest_recall_sources_match": True}}
        path = self.supplied / (wheel.name + ".receipt.json")
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, value

    def validate(self, path, wheel):
        return native.validate_receipt(path, wheel, IDENTITY, SOURCES, self.inputs,
                                       run_id="12345", run_attempt=2)

    def test_declared_matrix_contains_all_thirty_exact_cpython_platform_cells(self):
        self.assertEqual(len(native.EXPECTED_MATRIX), 30)
        self.assertEqual({python for python, _ in native.EXPECTED_MATRIX},
                         {"3.10", "3.11", "3.12", "3.13", "3.14", "3.15"})
        self.assertEqual({target for _, target in native.EXPECTED_MATRIX}, set(TARGET_PLATFORMS))

    def test_matching_receipts_bind_every_runtime_source_build_input_and_binary(self):
        for python, target in sorted(native.EXPECTED_MATRIX):
            wheel = wheel_fixture(self.supplied, python=python, target=target)
            receipt, _ = self.receipt(wheel, python=python, target=target)
            record, build = self.validate(receipt, wheel)
            self.assertEqual(record["target"], target)
            self.assertEqual(build["python_version"], python)
            self.assertEqual(record["sha256"], native.sha(wheel.read_bytes()))
        records, files, provenance = native.collect_native(self.supplied, IDENTITY, SOURCES, self.inputs)
        self.assertEqual((len(records), len(files)), (30, 60))
        self.assertEqual(provenance, {"run_id": "12345", "run_attempt": 2})
        self.assertIn("src/memory_book/_native.c", self.inputs)
        self.assertIn("src/memory_book/_native_core.h", self.inputs)
        self.assertTrue({"setup.py", "pyproject.toml"} <= self.inputs.keys())

    def test_wrong_commit_build_hash_run_attempt_or_smoke_is_rejected(self):
        wheel = wheel_fixture(self.supplied)
        path, baseline = self.receipt(wheel)
        changes = [("source", "commit", "d" * 40), ("source", "tree", "e" * 40),
                   ("source", "files_sha256", {**baseline["source"]["files_sha256"], "setup.py": "0" * 64}),
                   ("build", "run_id", "99999"), ("build", "run_attempt", 1),
                   ("build", "python_tag", "cp313"), ("build", "tools", {}),
                   ("build", "native_build_mode", "auto"), ("build", "build_log", {}),
                   ("runtime_smoke", "backend", "python"),
                   ("runtime_smoke", "native_sha256", "0" * 64),
                   ("runtime_smoke", "source_files_match", False)]
        for section, key, value in changes:
            changed = copy.deepcopy(baseline)
            changed[section][key] = value
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                self.validate(path, wheel)

    def test_wheel_tampering_is_rejected_even_if_outer_digest_is_recomputed(self):
        wheel = wheel_fixture(self.supplied)
        receipt, baseline = self.receipt(wheel)
        with zipfile.ZipFile(wheel) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for member, data, update_record in (
                ("memory_book/text.py", b"tampered Python source", True),
                ("memory_book/_native.c", b"tampered C source", True),
                ("memory_book/_native_core.h", b"tampered C header", True),
                (baseline["wheel"]["native_member"], b"changed binary", False),
                ("memory_book/../../outside.py", b"unsafe path", True),
                ("memory_book/_native.second.so", b"extra binary", True)):
            changed = dict(original)
            changed[member] = data
            write_zip(wheel, changed, record=update_record)
            value = copy.deepcopy(baseline)
            value["wheel"].update(sha256=native.sha(wheel.read_bytes()), bytes=wheel.stat().st_size)
            receipt.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(member=member, record=update_record), self.assertRaises(ValueError):
                self.validate(receipt, wheel)

    def test_wheel_and_metadata_tags_and_abi_must_agree(self):
        wheel = wheel_fixture(self.supplied, abi="cp313t")
        with self.assertRaisesRegex(ValueError, "ABI"):
            native.inspect_wheel(wheel, IDENTITY, SOURCES, target="linux_x86_64")
        wheel = wheel_fixture(self.supplied)
        with self.assertRaisesRegex(ValueError, "platform"):
            native.inspect_wheel(wheel, IDENTITY, SOURCES, target="windows_amd64")
        with zipfile.ZipFile(wheel) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        members["ai_memory_book-0.8.0.dist-info/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"
        write_zip(wheel, members)
        with self.assertRaisesRegex(ValueError, "tags"):
            native.inspect_wheel(wheel, IDENTITY, SOURCES, target="linux_x86_64")

    def test_repaired_wheel_directory_metadata_is_allowed_but_never_counted_as_record_files(self):
        wheel = wheel_fixture(self.supplied)
        with zipfile.ZipFile(wheel, "a") as archive:
            for name in ("memory_book/", "memory_book/static/", "ai_memory_book-0.8.0.dist-info/"):
                entry = zipfile.ZipInfo(name)
                entry.create_system, entry.external_attr = 3, 0o040755 << 16
                archive.writestr(entry, b"")
        native.inspect_wheel(wheel, IDENTITY, SOURCES, target="linux_x86_64")
        with zipfile.ZipFile(wheel, "a") as archive:
            entry = zipfile.ZipInfo("outside/")
            entry.create_system, entry.external_attr = 3, 0o040755 << 16
            archive.writestr(entry, b"")
        with self.assertRaisesRegex(ValueError, "directory"):
            native.inspect_wheel(wheel, IDENTITY, SOURCES, target="linux_x86_64")
        wheel = wheel_fixture(self.supplied)
        with zipfile.ZipFile(wheel, "a") as archive:
            entry = zipfile.ZipInfo("memory_book/linked.py")
            entry.create_system, entry.external_attr = 3, 0o120777 << 16
            archive.writestr(entry, b"../../outside.py")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            native.inspect_wheel(wheel, IDENTITY, SOURCES, target="linux_x86_64")

    def test_missing_or_orphaned_receipt_incomplete_matrix_and_duplicate_json_fail(self):
        wheel = wheel_fixture(self.supplied)
        with self.assertRaisesRegex(ValueError, "receipt"):
            native.collect_native(self.supplied, IDENTITY, SOURCES, self.inputs)
        receipt, _ = self.receipt(wheel)
        with self.assertRaisesRegex(ValueError, "matrix"):
            native.collect_native(self.supplied, IDENTITY, SOURCES, self.inputs)
        receipt.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            self.validate(receipt, wheel)

    def test_pure_wheel_and_sdist_include_exact_build_sources_without_binaries_or_research(self):
        wheel = wheel_fixture(self.root, target=None)
        descriptor = native.inspect_wheel(wheel, IDENTITY, SOURCES)
        self.assertEqual(descriptor["tags"], ["py3-none-any"])
        self.assertNotIn("native_member", descriptor)
        sdist = self.root / "ai_memory_book-0.8.0.tar.gz"
        write_sdist(sdist, self.inputs)
        native.canonicalize_fallback(wheel, IDENTITY, SOURCES, self.inputs)
        native.canonicalize_fallback(sdist, IDENTITY, SOURCES, self.inputs)
        native.inspect_wheel(wheel, IDENTITY, SOURCES)
        native.inspect_sdist(sdist, IDENTITY, SOURCES, self.inputs)
        for extra in ({"setup.py": b"uncommitted build logic"}, {"benchmarks/private.json": b"{}"},
                      {"src/memory_book/_native_core.h": b"changed header"},
                      {"src/memory_book/_native.leaked.so": b"generated binary"}):
            write_sdist(sdist, self.inputs, extra=extra)
            with self.subTest(extra=list(extra)), self.assertRaises(ValueError):
                native.inspect_sdist(sdist, IDENTITY, SOURCES, self.inputs)

    def test_missing_native_header_is_rejected_in_native_fallback_and_source_packages(self):
        missing = {name: data for name, data in SOURCES.items()
                   if name != "memory_book/_native_core.h"}
        for target in ("linux_x86_64", None):
            wheel = wheel_fixture(self.root, target=target, sources=missing)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "source"):
                native.inspect_wheel(wheel, IDENTITY, SOURCES, target=target)
        sdist = self.root / "ai_memory_book-0.8.0.tar.gz"
        write_sdist(sdist, {name: data for name, data in self.inputs.items()
                           if name != "src/memory_book/_native_core.h"})
        with self.assertRaisesRegex(ValueError, "source"):
            native.inspect_sdist(sdist, IDENTITY, SOURCES, self.inputs)

    def test_preparation_builds_only_the_fallback_and_keeps_supplied_native_bytes(self):
        wheel = wheel_fixture(self.supplied)
        receipt, _ = self.receipt(wheel)
        original_native, original_receipt = wheel.read_bytes(), receipt.read_bytes()
        (self.root / "scripts").mkdir()
        installer = b"installer v0.8.0 fixture\n"
        for name in native.legacy.INSTALLERS:
            (self.root / "scripts" / name).write_bytes(installer)
        output = self.root / "assets"

        def committed(root, command, spec):
            self.assertEqual((root, command), (self.root, "show"))
            self.assertTrue(spec.startswith(IDENTITY["commit"] + ":"))
            name = spec.split(":", 1)[1]
            return installer if name.startswith("scripts/") else self.inputs[name]

        def build(argv, *, cwd, env):
            self.assertEqual(argv[1:3], ["-m", "build"])
            self.assertEqual(env["MEMORY_BOOK_BUILD_NATIVE"], "0")
            self.assertEqual(env["MEMORY_BOOK_TEXT_BACKEND"], "python")
            actual = {path.relative_to(cwd).as_posix(): path.read_bytes() for path in cwd.rglob("*") if path.is_file()}
            self.assertEqual(actual, self.inputs)
            wheel_fixture(output, target=None)
            write_sdist(output / "ai_memory_book-0.8.0.tar.gz", self.inputs)

        with patch.object(native, "EXPECTED_MATRIX", frozenset({("3.12", "linux_x86_64")})), \
                patch.object(native.importlib.metadata, "version", side_effect=native.legacy.BUILD_TOOLS.__getitem__), \
                patch.object(native.legacy, "git", side_effect=committed), \
                patch.object(native.legacy, "command", side_effect=build), \
                patch.object(native, "install_fallback_smoke") as smoke, \
                patch.dict(native.legacy.RELEASE_PRERELEASE, {"v0.8.0": False}):
            self.assertEqual(native.prepare(self.root, output, IDENTITY, SOURCES, self.supplied), IDENTITY)
        self.assertEqual(smoke.call_count, 2)
        self.assertEqual((output / wheel.name).read_bytes(), original_native)
        self.assertEqual((output / receipt.name).read_bytes(), original_receipt)
        manifest = json.loads((output / "release-manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["repository"], "Afloat16/AI-Memory-Book")
        self.assertEqual(manifest["project"], "ai-memory-book")
        self.assertEqual(manifest["python_fallback_wheel"], "ai_memory_book-0.8.0-py3-none-any.whl")
        self.assertEqual(manifest["native_wheels"][0]["receipt"], receipt.name)
        self.assertEqual(manifest["source_files_sha256"], native.file_hashes(self.inputs))
        self.assertEqual(len(list(output.iterdir())), 9)  # 7 historic assets + one wheel/receipt pair.
        for name, details in manifest["assets"].items():
            self.assertEqual(details["sha256"], native.sha((output / name).read_bytes()))

    def test_historical_versions_and_existing_output_are_refused_before_building(self):
        with self.assertRaisesRegex(ValueError, "Historical"):
            native.prepare(self.root, self.root / "out", {**IDENTITY, "version": "0.7.0"}, SOURCES, self.supplied)
        output = self.root / "already-exists"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            native.prepare(self.root, output, IDENTITY, SOURCES, self.supplied)

    def test_build_log_records_actual_commands_and_hash_without_arbitrary_pip_output(self):
        path = self.root / "native-build.log"
        linux = "gcc -Wextra -c src/memory_book/_native.c -o build/_native.o -O3"
        windows = '"C:\\Program Files\\Compiler\\cl.exe" /c /O2 src/memory_book/_native.c /Fobuild/_native.obj'
        for target, command in (("linux_x86_64", linux), ("windows_amd64", windows)):
            data = ("pip output not retained as commands\n" + command + "\n").encode()
            path.write_bytes(data)
            with patch.dict(os.environ, {"NATIVE_BUILD_LOG": str(path), "MEMORY_BOOK_BUILD_NATIVE": "1"}):
                result = native.build_log_provenance(self.root, target)
            self.assertEqual(result["commands"], [command])
            self.assertEqual(result["sha256"], native.sha(data))
            self.assertEqual(result["bytes"], len(data))
        path.write_text("No compiler command was captured.\n", encoding="utf-8")
        with patch.dict(os.environ, {"NATIVE_BUILD_LOG": str(path), "MEMORY_BOOK_BUILD_NATIVE": "1"}):
            with self.assertRaisesRegex(ValueError, "compiler"):
                native.build_log_provenance(self.root, "linux_x86_64")
        with patch.dict(os.environ, {"NATIVE_BUILD_LOG": str(path), "MEMORY_BOOK_BUILD_NATIVE": "auto"}):
            with self.assertRaisesRegex(ValueError, "BUILD_NATIVE=1"):
                native.build_log_provenance(self.root, "linux_x86_64")


if __name__ == "__main__":
    unittest.main()
