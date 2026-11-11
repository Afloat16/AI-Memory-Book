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


def command(arguments: list[str], environment: dict[str, str], *, succeeds: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, env=environment, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180)
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


def assert_launcher(record: dict, environment: dict[str, str]) -> None:
    result = command([record["launcher"], "--version"], environment)
    assert result.stdout.strip() == record["version"], result.stdout
    result = command([record["python"], "-c", "import sys; print(sys.prefix)"], environment)
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
        # Do not let the test runner's source tree leak into the isolated CLI.
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
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / "src" / "memory_book", source / "src" / "memory_book", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        wheels = work / "wheels"
        wheels.mkdir()
        command([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheels), str(source)], environment)
        wheel = next(wheels.glob("ai_memory_book-*.whl"))

        prefix, bin_dir = work / "Install Space 记忆", work / "Command Bin 记忆"
        arguments = install_command(wheel, prefix, bin_dir)
        command(arguments, environment)
        first = manifest(prefix)
        assert first["extras"] == []
        assert Path(first["launcher"]).parent == bin_dir
        assert Path(first["python"]).is_absolute()
        assert_launcher(first, environment)
        print("PASS: isolated install and absolute launcher with spaces and Unicode paths", flush=True)

        old_launcher = Path(first["launcher"]).read_bytes()
        old_record = (prefix / "installation.json").read_bytes()
        broken_wheel = work / "ai_memory_book-0.0.0-py3-none-any.whl"
        broken_wheel.write_bytes(b"an intentionally invalid wheel")
        command(install_command(broken_wheel, prefix, bin_dir), environment, succeeds=False)
        assert Path(first["launcher"]).read_bytes() == old_launcher
        assert (prefix / "installation.json").read_bytes() == old_record
        assert sorted((prefix / "envs").iterdir()) == [Path(first["environment"])]
        assert_launcher(first, environment)
        print("PASS: failed package installation preserves the working launcher and cleans its staging environment", flush=True)

        command(arguments, environment)
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
            command(install_command(wheel, extras_prefix, extras_bin, extras=True), network_environment)
            record = manifest(extras_prefix)
            assert record["extras"] == ["mcp", "clients"]
            command([record["python"], "-c", "import mcp, tomlkit"], network_environment)
            assert_launcher(record, network_environment)
            print("PASS: the default MCP and client configuration extras import inside the installed environment", flush=True)

        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-extras", action="store_true")
    options = parser.parse_args()
    run(options.with_extras)
