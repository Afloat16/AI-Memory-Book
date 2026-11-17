"""Exercise the real platform installer with disposable prefixes and wheels.

This standalone test is intentionally outside unittest discovery. It requires
setuptools and wheel in the test runner, but its core install/reinstall checks
disable package indexes and use a local wheel. --with-extras additionally checks
the normal MCP/client extras installation using the configured package index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def command(arguments: list[str], environment: dict[str, str], *, succeeds: bool = True,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, env=environment, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180)
    if (result.returncode == 0) != succeeds:
        raise AssertionError(f"Unexpected exit {result.returncode}: {arguments}\n{result.stdout[-5000:]}\n{result.stderr[-5000:]}")
    return result


def install_command(source: Path, prefix: Path, bin_dir: Path, *, extras: bool = False) -> list[str]:
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise RuntimeError("PowerShell is required for the Windows installer smoke test.")
        result = [shell, "-NoProfile", "-File", str(ROOT / "scripts" / "install.ps1"), "-Source", str(source), "-Prefix", str(prefix), "-BinDir", str(bin_dir), "-Python", sys.executable]
        if not extras:
            result.append("-WithoutExtras")
    else:
        result = ["bash", str(ROOT / "scripts" / "install.sh"), "--source", str(source), "--prefix", str(prefix), "--bin-dir", str(bin_dir), "--python", sys.executable]
        if not extras:
            result.append("--without-extras")
    return result


def manifest(prefix: Path) -> dict:
    return json.loads((prefix / "installation.json").read_text(encoding="utf-8"))


def assert_launcher(record: dict, environment: dict[str, str], *, cwd: Path | None = None) -> None:
    result = command([record["launcher"], "--version"], environment, cwd=cwd)
    assert result.stdout.strip() == record["version"], result.stdout
    result = command([record["python"], "-I", "-c", "import sys; print(sys.prefix)"], environment, cwd=cwd)
    assert Path(result.stdout.strip()).resolve() == Path(record["environment"]).resolve()


def run(with_extras: bool) -> None:
    # Even the test runner's cache and temporary files stay under this checkout.
    with tempfile.TemporaryDirectory(prefix="installer-smoke-", dir=ROOT) as temporary:
        work = Path(temporary)
        environment = os.environ.copy()
        environment.update({
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_CACHE_DIR": str(work / "pip-cache"),
            "PYTHONUTF8": "1",
            "MEMORY_BOOK_HOME": str(work / "Memory Data 记忆"),
            "TMPDIR": str(work / "tmp"),
            "TEMP": str(work / "tmp"),
            "TMP": str(work / "tmp"),
        })
        # Build the local wheel under a controlled environment, then explicitly
        # poison caller paths for the real installer and installed launcher.
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        (work / "tmp").mkdir()
        data = Path(environment["MEMORY_BOOK_HOME"])
        data.mkdir()
        sentinel = data / "memory.db"
        sentinel.write_bytes(b"installer smoke: existing memory must remain byte-for-byte intact\n")
        sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()

        source = work / "source"
        source.mkdir()
        for name in ("pyproject.toml", "setup.py", "README.md", "LICENSE"):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / "src" / "memory_book", source / "src" / "memory_book",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so", "*.pyd", "*.dylib"))
        wheels = work / "wheels"
        wheels.mkdir()
        command([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheels), str(source)], environment)
        wheel = next(wheels.glob("ai_memory_book-*.whl"))

        unrelated = work / "Unrelated Project 误导"
        unrelated.mkdir()
        for name in ("memory_book", "pip", "venv"):
            package = unrelated / name
            package.mkdir()
            (package / "__init__.py").write_text(
                f'raise RuntimeError("unrelated caller package: {name}")\n', encoding="utf-8")
        for name in ("mcp", "tomlkit"):
            (unrelated / f"{name}.py").write_text(
                f'raise RuntimeError("unrelated caller extra: {name}")\n', encoding="utf-8")
        poisoned = {**environment, "PYTHONPATH": str(unrelated),
                    "PYTHONHOME": str(work / "Not a Python installation")}
        prefix, bin_dir = work / "Install Space 记忆", work / "Command Bin 记忆"
        arguments = install_command(wheel, prefix, bin_dir)
        command(arguments, poisoned, cwd=unrelated)
        first = manifest(prefix)
        assert first["extras"] == []
        assert Path(first["launcher"]).parent == bin_dir
        assert Path(first["python"]).is_absolute()
        assert_launcher(first, environment)
        for label, caller_environment, caller_directory in (
                ("cwd", environment, unrelated),
                ("PYTHONPATH", {**environment, "PYTHONPATH": str(unrelated)}, work),
                ("PYTHONHOME", {**environment, "PYTHONHOME": poisoned["PYTHONHOME"]}, work),
                ("combined", poisoned, unrelated)):
            assert_launcher(first, caller_environment, cwd=caller_directory)
            print(f"PASS: installed launcher ignores unrelated {label} while using its managed environment", flush=True)
        backend = command([first["python"], "-I", "-c",
                           "from memory_book._text_backend import BACKEND_NAME; print(BACKEND_NAME)"], environment)
        assert backend.stdout.strip() == "native", backend.stdout
        print("PASS: isolated install and absolute launcher with spaces and Unicode paths", flush=True)

        old_launcher = Path(first["launcher"]).read_bytes()
        old_record = (prefix / "installation.json").read_bytes()
        broken_wheel = work / "ai_memory_book-0.0.0-py3-none-any.whl"
        broken_wheel.write_bytes(b"an intentionally invalid wheel")
        command(install_command(broken_wheel, prefix, bin_dir), poisoned, succeeds=False, cwd=unrelated)
        assert Path(first["launcher"]).read_bytes() == old_launcher
        assert (prefix / "installation.json").read_bytes() == old_record
        assert sorted((prefix / "envs").iterdir()) == [Path(first["environment"])]
        assert_launcher(first, environment)
        print("PASS: failed package installation preserves the working launcher and cleans its staging environment", flush=True)

        command(arguments, poisoned, cwd=unrelated)
        second = manifest(prefix)
        assert second["environment"] != first["environment"]
        assert second["previous_environment"] == first["environment"]
        assert Path(first["environment"]).is_dir()
        assert_launcher(second, environment)
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        print("PASS: reinstall activates a fresh environment and preserves old environments and memory data", flush=True)

        unknown_prefix, unknown_bin = work / "unknown-prefix", work / "unknown-bin"
        unknown_bin.mkdir()
        unknown_launcher = unknown_bin / Path(first["launcher"]).name
        unknown_launcher.write_bytes(b"another application's executable")
        command(install_command(wheel, unknown_prefix, unknown_bin), environment, succeeds=False)
        assert unknown_launcher.read_bytes() == b"another application's executable"
        assert not (unknown_prefix / "envs").exists()
        print("PASS: an unmanaged launcher is not overwritten", flush=True)

        if with_extras:
            network_environment = environment.copy()
            network_environment.pop("PIP_NO_INDEX", None)
            extras_prefix, extras_bin = work / "extras-install", work / "extras-bin"
            extras_environment = {**network_environment, "PYTHONPATH": str(unrelated),
                                  "PYTHONHOME": poisoned["PYTHONHOME"]}
            command(install_command(wheel, extras_prefix, extras_bin, extras=True), extras_environment, cwd=unrelated)
            record = manifest(extras_prefix)
            assert record["extras"] == ["mcp", "clients"]
            command([record["python"], "-I", "-c", "import mcp, tomlkit"], extras_environment, cwd=unrelated)
            assert_launcher(record, extras_environment, cwd=unrelated)
            print("PASS: the default MCP and client configuration extras import inside the installed environment", flush=True)

        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-extras", action="store_true")
    options = parser.parse_args()
    run(options.with_extras)
