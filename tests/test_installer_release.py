"""Check release download routing without touching a user's installation."""

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_installer", ROOT / "scripts/install.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerReleaseTests(unittest.TestCase):
    def test_pinned_wheel_and_legacy_source_routes(self):
        repository = "https://github.com/Afloat16/AI-Memory-Book"
        for version in ("v0.3.0", "0.3.0", "v0.3.1", "0.3.1", "v0.3.2", "0.3.2", "v0.3.3", "0.3.3", "v0.3.4", "0.3.4", "v0.4.0", "0.4.0", "v0.5.0", "0.5.0", "v0.6.0", "0.6.0", "v0.7.0", "0.7.0"):
            number = version.removeprefix("v")
            wheel = repository + f"/releases/download/v{number}/ai_memory_book-{number}-py3-none-any.whl"
            for extras in (True, False):
                with self.subTest(version=version, extras=extras):
                    name = "ai-memory-book[mcp,clients]" if extras else "ai-memory-book"
                    self.assertEqual(INSTALLER.package_spec(None, version, extras), f"{name} @ {wheel}")
        for version in ("v0.2.1", "v0.4.1"):
            with self.subTest(version=version):
                self.assertEqual(INSTALLER.package_spec(None, version, True),
                    f"ai-memory-book[mcp,clients] @ {repository}/archive/refs/tags/{version}.zip")
        commit = "ABCDEF0123456789" * 2 + "ABCDEF01"
        self.assertEqual(INSTALLER.package_spec(None, commit, False),
            f"ai-memory-book @ {repository}/archive/{commit.lower()}.zip")
        with tempfile.TemporaryDirectory(prefix="installer-routes-", dir=ROOT) as directory:
            source = Path(directory) / "local source 记忆"
            source.mkdir()
            (source / "pyproject.toml").write_text("[project]\nname = 'ai-memory-book'\n", encoding="utf-8")
            self.assertEqual(INSTALLER.package_spec(source, "v0.3.0", True),
                f"ai-memory-book[mcp,clients] @ {source.resolve().as_uri()}")
            local_wheel = source / "ai_memory_book-0.3.0-py3-none-any.whl"
            local_wheel.touch()
            self.assertEqual(INSTALLER.package_spec(local_wheel, "v0.3.0", False),
                f"ai-memory-book @ {local_wheel.resolve().as_uri()}")
            self.assertEqual(INSTALLER.package_spec(source, "v0.8.0", True),
                f"ai-memory-book[mcp,clients] @ {source.resolve().as_uri()}")
            self.assertEqual(INSTALLER.package_spec(local_wheel, "v0.8.0", False),
                f"ai-memory-book @ {local_wheel.resolve().as_uri()}")

    def test_release_defaults_match_package_and_wrappers(self):
        self.assertEqual(INSTALLER.DEFAULT_VERSION, "v0.12.0")
        self.assertIn('version = "0.12.0"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('__version__ = "0.12.0"', (ROOT / "src/memory_book/__init__.py").read_text(encoding="utf-8"))
        self.assertIn('installer_ref="v0.12.0"', (ROOT / "scripts/install.sh").read_text(encoding="utf-8"))
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$Version = 'v0.12.0'", powershell)
        self.assertIn("$InstallerRef = 'v0.12.0'", powershell)

    def test_native_era_never_uses_an_unverified_archive_route(self):
        for tag in ("v0.8.0", "0.8.0", "v0.8.1", "v1.0.0"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "manifest selection"):
                INSTALLER.package_spec(None, tag, False)


def release_manifest():
    fallback = "ai_memory_book-0.8.0-py3-none-any.whl"
    filenames = [
        "ai_memory_book-0.8.0-cp312-cp312-linux_x86_64.whl",
        "ai_memory_book-0.8.0-cp312-cp312-manylinux_2_17_x86_64.whl",
        "ai_memory_book-0.8.0-cp311-cp311-win_amd64.whl",
    ]
    assets = {name: {"bytes": 123, "sha256": hashlib.sha256(name.encode()).hexdigest()}
              for name in [fallback, *filenames]}
    return {"schema_version": 2, "repository": "Afloat16/AI-Memory-Book", "project": "ai-memory-book",
            "tag": "v0.8.0", "version": "0.8.0", "commit": "a" * 40, "assets": assets,
            "python_fallback_wheel": fallback,
            "native_wheels": [{"filename": name, **assets[name], "native_sha256": "b" * 64,
                               "tags": ["-".join(name[:-4].split("-")[-3:])]} for name in filenames]}


class NativeManifestTests(unittest.TestCase):
    def test_manifest_validates_project_version_and_every_declared_asset(self):
        valid = release_manifest()
        self.assertEqual(INSTALLER.validate_release_manifest(valid, "v0.8.0"), valid)
        mutations = [
            lambda m: m.update(schema_version=1),
            lambda m: m.update(repository="someone/other"),
            lambda m: m.update(project="another-package"),
            lambda m: m.update(version="0.8.1"),
            lambda m: m.update(tag="v0.8.1"),
            lambda m: m.update(commit="not-a-commit"),
            lambda m: m.update(native_wheels=[]),
            lambda m: m.update(python_fallback_wheel="../other.whl"),
            lambda m: m["assets"].update({"../escape.whl": {"bytes": 1, "sha256": "a" * 64}}),
            lambda m: m["assets"].update({"folder\\escape.whl": {"bytes": 1, "sha256": "a" * 64}}),
            lambda m: m["assets"][m["python_fallback_wheel"]].update(sha256="not-a-digest"),
            lambda m: m["assets"][m["python_fallback_wheel"]].update(bytes=True),
            lambda m: m["native_wheels"].append(copy.deepcopy(m["native_wheels"][0])),
            lambda m: m["native_wheels"][0].update(sha256="c" * 64),
            lambda m: m["native_wheels"][0].update(bytes=124),
            lambda m: m["native_wheels"][0].update(native_sha256="invalid"),
            lambda m: m["native_wheels"][0].update(tags=[]),
            lambda m: m["native_wheels"][0].update(tags=["same", "same"]),
        ]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(valid)
            mutate(value)
            with self.subTest(mutation=index), self.assertRaisesRegex(ValueError, "Invalid release manifest"):
                INSTALLER.validate_release_manifest(value, "v0.8.0")

    def test_tag_specific_manifest_selection_pins_the_asset_sha256(self):
        value = release_manifest()
        raw = json.dumps(value).encode()
        chosen = value["native_wheels"][1]
        answer = {"filename": chosen["filename"], "selection": "native", "matched_tag": chosen["tags"][0]}
        python = Path("isolated environment") / "bin" / "python"
        with patch.object(INSTALLER, "urlopen", return_value=io.BytesIO(raw)) as fetch, \
                patch.object(INSTALLER.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(answer))) as select:
            spec, record = INSTALLER.release_package_spec(python, "0.8.0", True)
        base = INSTALLER.REPOSITORY + "/releases/download/v0.8.0/"
        self.assertEqual(spec, "ai-memory-book[mcp,clients] @ " + base + chosen["filename"] + "#sha256=" + chosen["sha256"])
        self.assertEqual(record["filename"], chosen["filename"])
        self.assertEqual(record["native_sha256"], chosen["native_sha256"])
        self.assertEqual(record["manifest_sha256"], hashlib.sha256(raw).hexdigest())
        fetch.assert_called_once_with(base + "release-manifest.json", timeout=30)
        self.assertEqual(select.call_args.args[0][:5], [str(python), "-I", "-X", "utf8", "-c"])
        self.assertIn("pip._vendor.packaging.tags", select.call_args.args[0][5])
        self.assertEqual(json.loads(select.call_args.kwargs["input"])["native_wheels"], value["native_wheels"])

    def test_no_matching_wheel_has_a_hash_pinned_python_fallback(self):
        value = release_manifest()
        filename = value["python_fallback_wheel"]
        answer = {"filename": filename, "selection": "python-fallback", "matched_tag": "py3-none-any"}
        with patch.object(INSTALLER, "urlopen", return_value=io.BytesIO(json.dumps(value).encode())), \
                patch.object(INSTALLER.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(answer))):
            spec, record = INSTALLER.release_package_spec(Path("python"), "v0.8.0", False)
        self.assertTrue(spec.endswith(filename + "#sha256=" + value["assets"][filename]["sha256"]))
        self.assertEqual(record["selection"], "python-fallback")
        self.assertNotIn("native_sha256", record)

    def test_bad_or_unavailable_manifests_do_not_fall_back_to_an_archive(self):
        bad = [b"not JSON", b'{"schema_version":2,"schema_version":2}',
               b"x" * (INSTALLER.MANIFEST_LIMIT + 1), b"{}"]
        for raw in bad:
            with self.subTest(size=len(raw)), patch.object(INSTALLER, "urlopen", return_value=io.BytesIO(raw)), \
                    patch.object(INSTALLER.subprocess, "run") as select, self.assertRaises(ValueError):
                INSTALLER.release_package_spec(Path("python"), "v0.8.0", False)
            select.assert_not_called()
        with patch.object(INSTALLER, "urlopen", side_effect=URLError("offline")), \
                patch.object(INSTALLER.subprocess, "run") as select, self.assertRaises(URLError):
            INSTALLER.release_package_spec(Path("python"), "v0.8.0", False)
        select.assert_not_called()

    def test_selector_failure_is_an_error_not_a_fallback(self):
        error = subprocess.CalledProcessError(1, ["python"], stderr="invalid wheel version")
        with patch.object(INSTALLER, "urlopen", return_value=io.BytesIO(json.dumps(release_manifest()).encode())), \
                patch.object(INSTALLER.subprocess, "run", side_effect=error), \
                self.assertRaisesRegex(RuntimeError, "invalid wheel version"):
            INSTALLER.release_package_spec(Path("python"), "v0.8.0", False)


class TargetInterpreterWheelSelectionTests(unittest.TestCase):
    def select(self, value, compatible):
        try:
            from pip._vendor.packaging.tags import parse_tag
        except ImportError:
            self.skipTest("pip's vendored packaging is required for the isolated-interpreter selector test")
        tags = [next(iter(parse_tag(tag))) for tag in compatible]
        output = io.StringIO()
        inputs = {key: value[key] for key in ("version", "python_fallback_wheel", "native_wheels")}
        with patch("pip._vendor.packaging.tags.sys_tags", return_value=iter(tags)), \
                patch.object(sys, "stdin", io.StringIO(json.dumps(inputs))), contextlib.redirect_stdout(output):
            exec(INSTALLER.WHEEL_SELECTOR, {})
        return json.loads(output.getvalue())

    def test_uses_target_tag_preference_instead_of_manifest_order(self):
        value = release_manifest()
        tags = [value["native_wheels"][1]["tags"][0], value["native_wheels"][0]["tags"][0], "py3-none-any"]
        selected = self.select(value, tags)
        self.assertEqual(selected["filename"], value["native_wheels"][1]["filename"])
        self.assertEqual(selected["matched_tag"], tags[0])
        self.assertEqual(selected, self.select({**value, "native_wheels": list(reversed(value["native_wheels"]))}, tags))

    def test_unsupported_platform_interpreter_or_abi_selects_only_python_fallback(self):
        for tag in ("pp310-pypy310_pp73-manylinux_2_17_x86_64", "cp313-cp313t-win_amd64",
                    "cp312-cp312-macosx_11_0_arm64", "cp312-cp312-musllinux_1_2_x86_64"):
            with self.subTest(tag=tag):
                value = release_manifest()
                selected = self.select(value, [tag, "py3-none-any"])
                self.assertEqual(selected["filename"], value["python_fallback_wheel"])
                self.assertEqual(selected["selection"], "python-fallback")

    def test_compressed_platform_tags_are_parsed_by_packaging(self):
        value = release_manifest()
        wheel = value["native_wheels"][1]
        wheel["filename"] = "ai_memory_book-0.8.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        wheel["tags"] = ["cp312-cp312-manylinux_2_17_x86_64", "cp312-cp312-manylinux2014_x86_64"]
        result = self.select(value, [wheel["tags"][1], "py3-none-any"])
        self.assertEqual(result["filename"], wheel["filename"])

    def test_invalid_filename_version_or_declared_tags_fails_even_without_a_match(self):
        for replacement in ("other_project-0.8.0-cp312-cp312-win_amd64.whl",
                            "ai_memory_book-0.8.1-cp312-cp312-win_amd64.whl", "not-a-wheel.whl"):
            value = release_manifest()
            value["native_wheels"][0]["filename"] = replacement
            with self.subTest(filename=replacement), self.assertRaises(ValueError):
                self.select(value, ["py3-none-any"])
        value = release_manifest()
        value["native_wheels"][0]["tags"] = ["cp312-cp312-different_platform"]
        with self.assertRaisesRegex(ValueError, "tags differ"):
            self.select(value, ["py3-none-any"])

    def test_selector_bootstraps_packaging_in_a_real_isolated_python_process(self):
        try:
            from pip._vendor.packaging.tags import sys_tags
        except ImportError:
            self.skipTest("pip is required for the isolated-interpreter selector test")
        tag = str(next(sys_tags()))
        filename = "ai_memory_book-0.8.0-" + tag + ".whl"
        value = {"version": "0.8.0", "python_fallback_wheel": "ai_memory_book-0.8.0-py3-none-any.whl",
                 "native_wheels": [{"filename": filename, "tags": [tag]}]}
        result = subprocess.run([sys.executable, "-I", "-c", INSTALLER.WHEEL_SELECTOR],
                                input=json.dumps(value), text=True, capture_output=True, check=True)
        selected = json.loads(result.stdout)
        self.assertEqual(selected, {"filename": filename, "selection": "native", "matched_tag": tag})


class BackendReceiptTests(unittest.TestCase):
    @staticmethod
    def backend(native):
        return {"backend": "native" if native else "python", "requested": "auto",
                "extension": "/installed/memory_book/_native.so" if native else None,
                "extension_sha256": "b" * 64 if native else None}

    def test_probe_records_the_installed_default_without_caller_backend_override(self):
        for native in (True, False):
            expected = self.backend(native)
            with self.subTest(native=native), patch.dict(os.environ, {"MEMORY_BOOK_TEXT_BACKEND": "python"}), \
                    patch.object(INSTALLER.subprocess, "check_output", return_value=json.dumps(expected)) as probe:
                self.assertEqual(INSTALLER.installed_backend(Path("isolated-python")), expected)
            self.assertEqual(probe.call_args.args[0][:5], ["isolated-python", "-I", "-X", "utf8", "-c"])
            self.assertEqual(probe.call_args.kwargs["env"]["MEMORY_BOOK_TEXT_BACKEND"], "auto")

    def test_probe_rejects_unverified_native_or_contradictory_python(self):
        invalid = [self.backend(True) | {"extension_sha256": None},
                   self.backend(True) | {"extension": None},
                   self.backend(False) | {"extension_sha256": "b" * 64}]
        for report in invalid:
            with patch.object(INSTALLER.subprocess, "check_output", return_value=json.dumps(report)), self.assertRaises(RuntimeError):
                INSTALLER.installed_backend(Path("python"))

    def test_legacy_package_without_backend_selector_reports_python(self):
        with tempfile.TemporaryDirectory(prefix="installer-legacy-backend-", dir=ROOT) as directory:
            package = Path(directory) / "memory_book"
            package.mkdir()
            (package / "__init__.py").write_text('__version__ = "0.7.0"\n')
            code = "import sys; sys.path.insert(0, " + repr(directory) + ")\n" + INSTALLER.BACKEND_PROBE
            result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), self.backend(False))

    def test_activation_requires_the_selected_native_backend_and_exact_extension(self):
        with tempfile.TemporaryDirectory(prefix="installer-native-record-", dir=ROOT) as directory:
            prefix = Path(directory) / "install"
            arguments = argparse.Namespace(prefix=prefix, bin_dir=None, source=None, version="v0.8.0", without_extras=True)
            asset = {"filename": "ai_memory_book-0.8.0-cp312-cp312-linux_x86_64.whl", "selection": "native",
                     "sha256": "a" * 64, "native_sha256": "b" * 64}

            def command(argv, **kwargs):
                if "venv" in argv:
                    scripts = Path(argv[-1]) / "Scripts"
                    scripts.mkdir()
                    (scripts / "memory-book.exe").write_bytes(b"mock native launcher")
                return subprocess.CompletedProcess(argv, 0)

            with patch.object(INSTALLER, "release_package_spec", return_value=("hash-pinned-release-spec", asset)), \
                    patch.object(INSTALLER.subprocess, "run", side_effect=command), \
                    patch.object(INSTALLER.subprocess, "check_output", return_value="0.8.0\n"), \
                    patch.object(INSTALLER, "installed_backend", return_value=self.backend(True)):
                installed = INSTALLER.install(arguments)
            self.assertEqual(installed["native_backend"], "native")
            self.assertEqual(installed["native_extension_sha256"], "b" * 64)
            self.assertEqual(installed["release_asset"], asset)
            previous_record = (prefix / "installation.json").read_bytes()
            previous_launcher = Path(installed["launcher"]).read_bytes()
            for backend in (self.backend(False), self.backend(True) | {"extension_sha256": "c" * 64}):
                with self.subTest(backend=backend), \
                        patch.object(INSTALLER, "release_package_spec", return_value=("hash-pinned-release-spec", asset)), \
                        patch.object(INSTALLER.subprocess, "run", side_effect=command), \
                        patch.object(INSTALLER.subprocess, "check_output", return_value="0.8.0\n"), \
                        patch.object(INSTALLER, "installed_backend", return_value=backend), self.assertRaises(RuntimeError):
                    INSTALLER.install(arguments)
                self.assertEqual((prefix / "installation.json").read_bytes(), previous_record)
                self.assertEqual(Path(installed["launcher"]).read_bytes(), previous_launcher)
                self.assertEqual(list((prefix / "envs").iterdir()), [Path(installed["environment"])])


if __name__ == "__main__":
    unittest.main()
