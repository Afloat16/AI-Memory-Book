#!/usr/bin/env python3
"""Install AI-Memory-Book into an isolated, replaceable user environment.

The shell and PowerShell entry points only locate Python and this helper. Package
installation, ownership checks, and activation use the same implementation on
every platform. Existing environments and memory databases are never deleted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import quote


DEFAULT_VERSION = "v0.2.1"
REPOSITORY = "https://github.com/Afloat16/AI-Memory-Book"


def data_home() -> Path:
    if os.environ.get("MEMORY_BOOK_HOME"):
        return Path(os.environ["MEMORY_BOOK_HOME"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "AI-Memory-Book"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AI-Memory-Book"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "ai-memory-book"


def absolute_path(value: Path) -> Path:
    result = value.expanduser().resolve()
    if any(character in str(result) for character in ("\x00", "\n", "\r")):
        raise ValueError("Installation paths cannot contain NUL or newline characters.")
    if result == Path(result.anchor):
        raise ValueError("Choose a user directory, not the filesystem root, as an installation path.")
    return result


def package_spec(source: Path | None, version: str, extras: bool) -> str:
    name = "ai-memory-book[mcp,clients]" if extras else "ai-memory-book"
    if source is not None:
        source = source.expanduser().resolve()
        if source.is_dir():
            if not (source / "pyproject.toml").is_file():
                raise ValueError("--source must contain AI-Memory-Book's pyproject.toml.")
        elif not (source.is_file() and source.suffix.lower() == ".whl"):
            raise ValueError("--source must be a source directory or a local wheel file.")
        return f"{name} @ {source.as_uri()}"
    if re.fullmatch(r"[0-9a-fA-F]{40}", version):
        archive = f"{REPOSITORY}/archive/{version.lower()}.zip"
    elif re.fullmatch(r"v?\d+\.\d+\.\d+[A-Za-z0-9.+-]*", version):
        tag = version if version.startswith("v") else "v" + version
        archive = f"{REPOSITORY}/archive/refs/tags/{quote(tag, safe='')}.zip"
    else:
        raise ValueError("--version must be a release tag such as v0.2.1 or a full 40-character commit SHA; use --source for a development checkout.")
    return f"{name} @ {archive}"


@contextmanager
def installation_lock(prefix: Path):
    """An OS-owned lock survives process crashes without leaving a stale lock."""
    handle = (prefix / ".install.lock").open("a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except (BlockingIOError, PermissionError) as exc:
        if not locked:
            raise RuntimeError("Another installer is using this prefix; wait for it to finish.") from exc
        raise
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def stage_file(destination: Path, content: bytes, executable: bool = False) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        staged.chmod(0o755 if executable else 0o600)
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def install(arguments: argparse.Namespace) -> dict:
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or later is required.")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE capability_check USING fts5(text)")
    except sqlite3.Error as exc:
        raise RuntimeError("This Python's SQLite lacks FTS5; install a Python build with FTS5 enabled.") from exc
    finally:
        connection.close()

    prefix = absolute_path(arguments.prefix or (data_home() / "install"))
    if arguments.bin_dir:
        bin_dir = absolute_path(arguments.bin_dir)
    elif arguments.prefix or os.environ.get("MEMORY_BOOK_HOME"):
        bin_dir = prefix / "bin"
    elif os.name == "nt":
        bin_dir = absolute_path(data_home() / "bin")
    else:
        bin_dir = absolute_path(Path.home() / ".local" / "bin")
    spec = package_spec(arguments.source, arguments.version, not arguments.without_extras)
    launcher = bin_dir / ("memory-book.exe" if os.name == "nt" else "memory-book")
    manifest = prefix / "installation.json"
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)

    with installation_lock(prefix):
        old_manifest = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
        if launcher.exists() or launcher.is_symlink():
            if launcher.is_symlink() or not launcher.is_file():
                raise RuntimeError(f"Refusing to replace an unmanaged launcher: {launcher}")
            owned = old_manifest.get("distribution") == "ai-memory-book" and old_manifest.get("launcher") == str(launcher)
            digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
            if not owned or digest != old_manifest.get("launcher_sha256"):
                raise RuntimeError(f"Refusing to replace an unmanaged or modified launcher: {launcher}. Choose --bin-dir or preserve that file first.")
        environments = prefix / "envs"
        environments.mkdir(exist_ok=True, mode=0o700)
        environment = Path(tempfile.mkdtemp(prefix="env-", dir=environments))
        activated = False
        staged_launcher = staged_manifest = rollback_launcher = None
        try:
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run([str(python), "-m", "pip", "--disable-pip-version-check", "install", "--no-input", "--upgrade", spec], check=True)
            installed_version = subprocess.check_output([str(python), "-m", "memory_book", "--version"], text=True, encoding="utf-8").strip()
            if not arguments.without_extras:
                subprocess.run([str(python), "-c", "import mcp, tomlkit"], check=True)
            if arguments.source is None and not re.fullmatch(r"[0-9a-fA-F]{40}", arguments.version):
                if installed_version != arguments.version.removeprefix("v"):
                    raise RuntimeError(f"The release reports {installed_version}, but {arguments.version} was requested.")

            bin_dir.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                # pip's native launcher embeds the absolute environment Python.
                # Copying it avoids shell quoting and execution-policy problems.
                content = (environment / "Scripts" / "memory-book.exe").read_bytes()
            else:
                content = ("#!/bin/sh\n# AI-Memory-Book managed launcher\nexec " + shlex.quote(str(python)) + ' -m memory_book "$@"\n').encode("utf-8")
            staged_launcher = stage_file(launcher, content, executable=True)
            result = {
                "schema": 1,
                "distribution": "ai-memory-book",
                "version": installed_version,
                "source": spec,
                "extras": [] if arguments.without_extras else ["mcp", "clients"],
                "prefix": str(prefix),
                "environment": str(environment),
                "python": str(python),
                "launcher": str(launcher),
                "launcher_sha256": hashlib.sha256(content).hexdigest(),
                "previous_environment": old_manifest.get("environment"),
                "installed_at": datetime.now(timezone.utc).isoformat(),
            }
            staged_manifest = stage_file(manifest, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            if launcher.exists():
                rollback_launcher = stage_file(launcher, launcher.read_bytes(), executable=True)
            os.replace(staged_launcher, launcher)
            try:
                os.replace(staged_manifest, manifest)
            except BaseException:
                if rollback_launcher:
                    os.replace(rollback_launcher, launcher)
                else:
                    launcher.unlink(missing_ok=True)
                raise
            activated = True
            return result
        finally:
            for staged in (staged_launcher, staged_manifest, rollback_launcher):
                if staged:
                    staged.unlink(missing_ok=True)
            if not activated:
                shutil.rmtree(environment, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Install this source checkout or local wheel instead of downloading a release")
    parser.add_argument("--version", default=DEFAULT_VERSION, help=f"Official release tag or full commit SHA (default: {DEFAULT_VERSION})")
    parser.add_argument("--prefix", type=Path, help="Installation directory; an explicit prefix also defaults launchers to PREFIX/bin")
    parser.add_argument("--bin-dir", type=Path, help="Directory for the memory-book launcher")
    parser.add_argument("--without-extras", action="store_true", help="Install only the standard-library core; omit MCP and client configuration support")
    parser.add_argument("--python", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    try:
        result = install(arguments)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"AI-Memory-Book installation failed: {exc}", file=sys.stderr)
        return 1
    command = "& '" + result["launcher"].replace("'", "''") + "'" if os.name == "nt" else shlex.quote(result["launcher"])
    print(f"\nInstalled AI-Memory-Book {result['version']}")
    print(f"Launcher: {result['launcher']}")
    print(f"Python:   {result['python']}")
    print(f"\nNext: {command} setup --client claude-code")
    print(f"Background capture: {command} setup --client claude-code --capture --background")
    print(f"\nAdd {Path(result['launcher']).parent} to PATH to use the short memory-book command.")
    print(f"Installation record: {Path(result['prefix']) / 'installation.json'}")
    if result["previous_environment"]:
        print(f"Previous environment retained: {result['previous_environment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
