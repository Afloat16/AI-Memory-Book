"""Managed commands cannot borrow packages or Python configuration from callers."""

import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("isolated_installer", ROOT / "scripts/install.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def fixture_package(site, *, extras):
    """Place only owned test code in a disposable real virtual environment."""
    package = site / "memory_book"
    package.mkdir(parents=True)
    version = INSTALLER.DEFAULT_VERSION.removeprefix("v")
    (package / "__init__.py").write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    (package / "__main__.py").write_text("from .fixture_cli import main\nraise SystemExit(main())\n", encoding="utf-8")
    (package / "fixture_cli.py").write_text(
        "import json, os, sys\n"
        "def main():\n"
        "    if '--version' in sys.argv:\n"
        f"        print({version!r})\n"
        "    else:\n"
        "        print(json.dumps({'installed': True, 'argv': sys.argv[1:], 'utf8': sys.flags.utf8_mode,\n"
        "            'data_home': os.environ.get('MEMORY_BOOK_HOME'),\n"
        "            'backend': os.environ.get('MEMORY_BOOK_TEXT_BACKEND'),\n"
        "            'pip_index': os.environ.get('PIP_INDEX_URL')}, ensure_ascii=False))\n"
        "    return 0\n", encoding="utf-8")
    metadata = site / f"ai_memory_book-{version}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(f"Metadata-Version: 2.1\nName: ai-memory-book\nVersion: {version}\n", encoding="utf-8")
    # A distinct module proves that Windows generation uses installed metadata,
    # rather than hard-coding the current production entry point.
    (metadata / "entry_points.txt").write_text(
        "[console_scripts]\nmemory-book = memory_book.fixture_cli:main\n", encoding="utf-8")
    if extras:
        for name in ("mcp", "tomlkit"):
            (site / f"{name}.py").write_text("installed_fixture = True\n", encoding="utf-8")


class InstallerIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="installer-isolation-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.unrelated = self.work / "Unrelated Project 误导"
        self.unrelated.mkdir()
        for name in ("memory_book", "pip", "venv"):
            package = self.unrelated / name
            package.mkdir()
            (package / "__init__.py").write_text(f'raise RuntimeError("caller shadow: {name}")\n', encoding="utf-8")
        for name in ("mcp", "tomlkit"):
            # Ambient extras deliberately import successfully: the installer
            # must still reject a new environment that lacks its own extras.
            (self.unrelated / f"{name}.py").write_text("ambient_only = True\n", encoding="utf-8")
        self.clean = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        self.clean.update(MEMORY_BOOK_HOME=str(self.work / "Owned Data 记忆"),
                          MEMORY_BOOK_TEXT_BACKEND="python", PIP_INDEX_URL="https://owned-fixture.invalid/simple")
        self.poisoned = {**self.clean, "PYTHONPATH": str(self.unrelated),
                         "PYTHONHOME": str(self.work / "not-a-python-installation")}
        self.wheel = self.work / "ai_memory_book-0.0.0-py3-none-any.whl"
        self.wheel.write_bytes(b"owned fixture: package installation is stubbed")
        self.arguments = argparse.Namespace(prefix=self.work / "Install Space 记忆", bin_dir=self.work / "Command Bin 记忆",
            source=self.wheel, version=INSTALLER.DEFAULT_VERSION, without_extras=False)

    def install_fixture(self, *, extras=True):
        original_run = subprocess.run
        def command(argv, **kwargs):
            if "-m" in argv and argv[argv.index("-m") + 1] == "pip":
                probe = original_run([argv[0], "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                     capture_output=True, text=True, check=True)
                fixture_package(Path(probe.stdout.strip()), extras=extras)
                return subprocess.CompletedProcess(argv, 0)
            return original_run(argv, **kwargs)
        with patch.dict(os.environ, self.poisoned, clear=True), working_directory(self.unrelated), \
                patch.object(INSTALLER.subprocess, "run", side_effect=command):
            return INSTALLER.install(self.arguments)

    def test_managed_launcher_uses_installed_package_and_preserves_application_options(self):
        installed = self.install_fixture()
        self.assertEqual(installed["version"], INSTALLER.DEFAULT_VERSION.removeprefix("v"))
        cases = ((self.clean, self.unrelated),
                 ({**self.clean, "PYTHONPATH": str(self.unrelated)}, self.work),
                 ({**self.clean, "PYTHONHOME": self.poisoned["PYTHONHOME"]}, self.work),
                 (self.poisoned, self.unrelated))
        for environment, cwd in cases:
            with self.subTest(environment={key: environment.get(key) for key in ("PYTHONPATH", "PYTHONHOME")}):
                result = subprocess.run([installed["launcher"], "one argument", "记忆"], cwd=cwd, env=environment,
                                        capture_output=True, text=True, encoding="utf-8", check=True)
                self.assertEqual(json.loads(result.stdout), {
                    "installed": True, "argv": ["one argument", "记忆"], "utf8": 1,
                    "data_home": self.clean["MEMORY_BOOK_HOME"], "backend": "python",
                    "pip_index": self.clean["PIP_INDEX_URL"]})
        # The old interpreter command is a negative control using only our own
        # shadow package. A silently ignored fixture would make this fail.
        control = subprocess.run([installed["python"], "-m", "memory_book", "--version"],
                                 cwd=self.unrelated, env=self.clean, capture_output=True, text=True)
        self.assertNotEqual(control.returncode, 0)
        self.assertIn("caller shadow: memory_book", control.stderr)

    def test_ambient_extras_do_not_pass_and_failed_install_preserves_active_launcher(self):
        installed = self.install_fixture()
        launcher = Path(installed["launcher"])
        manifest = self.arguments.prefix / "installation.json"
        before_launcher, before_manifest = launcher.read_bytes(), manifest.read_bytes()
        with self.assertRaises(subprocess.CalledProcessError):
            self.install_fixture(extras=False)
        self.assertEqual(launcher.read_bytes(), before_launcher)
        self.assertEqual(manifest.read_bytes(), before_manifest)
        self.assertEqual(list((self.arguments.prefix / "envs").iterdir()), [Path(installed["environment"])])

    def test_launcher_generation_failure_preserves_active_installation(self):
        installed = self.install_fixture()
        launcher = Path(installed["launcher"])
        manifest = self.arguments.prefix / "installation.json"
        before_launcher, before_manifest = launcher.read_bytes(), manifest.read_bytes()
        failure = subprocess.CalledProcessError(7, [installed["python"], "-I", "-c", "launcher generator"])
        with patch.object(INSTALLER, "launcher_content", side_effect=failure), \
                self.assertRaises(subprocess.CalledProcessError):
            self.install_fixture()
        self.assertEqual(launcher.read_bytes(), before_launcher)
        self.assertEqual(manifest.read_bytes(), before_manifest)
        self.assertEqual(list((self.arguments.prefix / "envs").iterdir()), [Path(installed["environment"])])

    def test_platform_bootstrap_ignores_python_configuration_before_loading_helper(self):
        scripts = self.work / "Installer Scripts 记忆"
        scripts.mkdir()
        helper = scripts / "install.py"
        helper.write_text("import json, os, sys\nprint(json.dumps({'isolated': sys.flags.isolated, 'utf8': sys.flags.utf8_mode, "
                          "'pip_index': os.environ.get('PIP_INDEX_URL'), 'args': sys.argv[1:]}, ensure_ascii=False))\n", encoding="utf-8")
        if os.name == "nt":
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if not shell:
                self.skipTest("PowerShell is required for the Windows bootstrap")
            wrapper = scripts / "install.ps1"
            shutil.copyfile(ROOT / "scripts/install.ps1", wrapper)
            command = [shell, "-NoProfile", "-File", str(wrapper), "-Python", sys.executable, "-Prefix", str(self.work)]
        else:
            wrapper = scripts / "install.sh"
            shutil.copyfile(ROOT / "scripts/install.sh", wrapper)
            command = ["bash", str(wrapper), "--python", sys.executable, "--prefix", str(self.work)]
        result = subprocess.run(command, cwd=self.unrelated, env=self.poisoned,
                                capture_output=True, text=True, encoding="utf-8", check=True)
        output = json.loads(result.stdout)
        self.assertEqual(output["isolated"], 1)
        self.assertEqual(output["utf8"], 1)
        self.assertEqual(output["pip_index"], self.clean["PIP_INDEX_URL"])
        self.assertIn(str(self.work), output["args"])

    def test_owned_source_build_scrubs_python_routing_from_nested_backend(self):
        source = self.work / "Owned Source 记忆"
        source.mkdir()
        (source / "pyproject.toml").write_text(
            '[build-system]\nrequires = []\nbuild-backend = "owned_backend"\nbackend-path = ["."]\n',
            encoding="utf-8")
        version = INSTALLER.DEFAULT_VERSION.removeprefix("v")
        metadata = f"ai_memory_book-{version}.dist-info"
        files = {
            "memory_book/__init__.py": f"__version__ = {version!r}\n",
            "memory_book/__main__.py": "from .fixture_cli import main\nraise SystemExit(main())\n",
            "memory_book/fixture_cli.py": f"def main():\n    print({version!r})\n    return 0\n",
            f"{metadata}/METADATA": f"Metadata-Version: 2.1\nName: ai-memory-book\nVersion: {version}\n",
            f"{metadata}/WHEEL": "Wheel-Version: 1.0\nGenerator: owned-test-backend\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            f"{metadata}/entry_points.txt": "[console_scripts]\nmemory-book = memory_book.fixture_cli:main\n",
        }
        backend = '''import base64, csv, hashlib, io, json, os
from pathlib import Path
from zipfile import ZipFile

def record(hook):
    with (Path(__file__).parent / "hook-visits.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"hook": hook, "environment": {name: os.environ.get(name) for name in
            ("PYTHONHOME", "PYTHONPATH", "PIP_INDEX_URL", "PIP_NO_INDEX", "HTTPS_PROXY", "MEMORY_BOOK_HOME")}}) + "\\n")

def get_requires_for_build_wheel(config_settings=None):
    record("requirements")
    return []

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    record("wheel")
    rows = []
    with ZipFile(Path(wheel_directory) / WHEEL_NAME, "w") as wheel:
        for name, text in FILES.items():
            data = text.encode("utf-8")
            wheel.writestr(name, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            rows.append((name, "sha256=" + digest, str(len(data))))
        rows.append((RECORD_NAME, "", ""))
        output = io.StringIO()
        csv.writer(output, lineterminator="\\n").writerows(rows)
        wheel.writestr(RECORD_NAME, output.getvalue())
    return WHEEL_NAME
'''
        backend += f"\nFILES = {files!r}\nWHEEL_NAME = 'ai_memory_book-{version}-py3-none-any.whl'\nRECORD_NAME = '{metadata}/RECORD'\n"
        (source / "owned_backend.py").write_text(backend, encoding="utf-8")
        arguments = argparse.Namespace(**{**vars(self.arguments), "source": source, "without_extras": True})
        environment = {**self.poisoned, "PIP_NO_INDEX": "1", "HTTPS_PROXY": "http://owned-proxy.invalid:8080"}
        with patch.dict(os.environ, environment, clear=True), working_directory(self.unrelated):
            installed = INSTALLER.install(arguments)
            self.assertEqual(os.environ["PYTHONHOME"], environment["PYTHONHOME"])
            self.assertEqual(os.environ["PYTHONPATH"], environment["PYTHONPATH"])
        self.assertEqual(installed["version"], version)
        visits = [json.loads(line) for line in (source / "hook-visits.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(visit["hook"] == "wheel" for visit in visits))
        for visit in visits:
            values = visit["environment"]
            self.assertIsNone(values["PYTHONHOME"])
            # pip supplies its own build-environment sitecustomize directory,
            # which can live beneath the caller's temporary directory. Only
            # the original caller import entry must be absent.
            entries = [str(Path(entry).resolve()) for entry in (values["PYTHONPATH"] or "").split(os.pathsep) if entry]
            self.assertNotIn(str(self.unrelated.resolve()), entries)
            for name in ("PIP_INDEX_URL", "PIP_NO_INDEX", "HTTPS_PROXY", "MEMORY_BOOK_HOME"):
                self.assertEqual(values[name], environment[name])


@unittest.skipUnless(importlib.util.find_spec("pip"), "Windows generation uses the installation environment's pip")
class WindowsLauncherGenerationTests(unittest.TestCase):
    def test_generator_uses_declared_entry_point_and_supported_interpreter_options(self):
        made = []
        class Maker:
            def __init__(self, source, target):
                self.source, self.target = source, target
            def make(self, spec, options):
                made.append((self.source, self.target, self.variants, self.clobber, spec, options))
        entry = SimpleNamespace(group="console_scripts", name="memory-book", value="memory_book.custom_entry:run")
        with patch("pip._vendor.distlib.scripts.ScriptMaker", Maker), \
                patch("importlib.metadata.distribution", return_value=SimpleNamespace(entry_points=[entry])), \
                patch.object(sys, "argv", ["-c", "Owned Scripts 记忆"]):
            exec(INSTALLER.WINDOWS_LAUNCHER, {})
        self.assertEqual(made, [(None, "Owned Scripts 记忆", {""}, True,
                                "memory-book = memory_book.custom_entry:run", {"interpreter_args": ["-I", "-X", "utf8"]})])

    def test_missing_or_ambiguous_console_entry_point_fails_before_generation(self):
        entry = SimpleNamespace(group="console_scripts", name="memory-book", value="memory_book.cli:main")
        for entries in ([], [entry, entry]):
            with self.subTest(entries=len(entries)), \
                    patch("importlib.metadata.distribution", return_value=SimpleNamespace(entry_points=entries)), \
                    patch("pip._vendor.distlib.scripts.ScriptMaker") as maker, \
                    self.assertRaisesRegex(RuntimeError, "one memory-book console entry point"):
                exec(INSTALLER.WINDOWS_LAUNCHER, {})
            maker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
