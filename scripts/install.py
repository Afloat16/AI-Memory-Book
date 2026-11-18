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
from urllib.request import urlopen


# Pin the packaged release; development checkouts are installed with --source.
DEFAULT_VERSION = "v0.12.0"
WHEEL_RELEASES = {"v0.3.0", "v0.3.1", "v0.3.2", "v0.3.3", "v0.3.4", "v0.4.0", "v0.5.0", "v0.6.0", "v0.7.0"}
REPOSITORY = "https://github.com/Afloat16/AI-Memory-Book"
MANIFEST_LIMIT = 2 * 1024 * 1024


# Run this in the newly created installation environment.  Its Python, ABI and
# platform tags are authoritative; the Python running this installer need not
# have a separately installed packaging distribution.
WHEEL_SELECTOR = r'''
import json, sys
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

value = json.load(sys.stdin)
rank = {tag: index for index, tag in enumerate(sys_tags())}
expected = Version(value["version"])

def inspect(filename):
    name, version, build, tags = parse_wheel_filename(filename)
    if canonicalize_name(name) != "ai-memory-book" or version != expected:
        raise ValueError("Wheel filename has a different distribution or version: " + filename)
    return tags

fallback = value["python_fallback_wheel"]
fallback_tags = inspect(fallback)
if {str(tag) for tag in fallback_tags} != {"py3-none-any"}:
    raise ValueError("The fallback must be a universal Python 3 wheel")
if not any(tag in rank for tag in fallback_tags):
    raise ValueError("This interpreter cannot use the declared Python fallback")
choices = []
for wheel in value["native_wheels"]:
    tags = inspect(wheel["filename"])
    if {str(tag) for tag in tags} != set(wheel["tags"]) or any(tag.platform == "any" for tag in tags):
        raise ValueError("Native wheel tags differ from its filename: " + wheel["filename"])
    matches = [(rank[tag], str(tag)) for tag in tags if tag in rank]
    if matches:
        priority, tag = min(matches)
        choices.append((priority, wheel["filename"], tag))
if choices:
    _, filename, tag = min(choices)
    selected = {"filename": filename, "selection": "native", "matched_tag": tag}
else:
    selected = {"filename": fallback, "selection": "python-fallback", "matched_tag": "py3-none-any"}
print(json.dumps(selected))
'''


BACKEND_PROBE = r'''
import hashlib, importlib.machinery, importlib.util, json
from pathlib import Path
import memory_book

result = {"backend": "python", "requested": "auto", "extension": None, "extension_sha256": None}
if importlib.util.find_spec("memory_book._text_backend") is not None:
    from memory_book import _text_backend
    result["backend"] = _text_backend.BACKEND_NAME
    if result["backend"] == "native":
        module = _text_backend.NATIVE
        path = Path(module.__file__).resolve()
        if path.parent != Path(memory_book.__file__).resolve().parent or not isinstance(module.__loader__, importlib.machinery.ExtensionFileLoader):
            raise RuntimeError("Native backend was not loaded from this installed package")
        for name in ("terms_ascii", "ascii_tokens", "unicode_tokens", "fold_excerpt_source", "evidence_units"):
            if not callable(getattr(module, name, None)):
                raise RuntimeError("Installed native backend lacks " + name)
        result.update(extension=str(path), extension_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    elif result["backend"] != "python" or _text_backend.NATIVE is not None:
        raise RuntimeError("Installed text backend reports an inconsistent state")
print(json.dumps(result))
'''


WINDOWS_LAUNCHER = r'''
import importlib.metadata, sys
from pip._vendor.distlib.scripts import ScriptMaker

entries = [entry for entry in importlib.metadata.distribution("ai-memory-book").entry_points
           if entry.group == "console_scripts" and entry.name == "memory-book"]
if len(entries) != 1:
    raise RuntimeError("The installed package must declare one memory-book console entry point")
maker = ScriptMaker(None, sys.argv[1])
maker.variants = {""}
maker.clobber = True
maker.make("memory-book = " + entries[0].value, options={"interpreter_args": ["-I", "-X", "utf8"]})
'''


def launcher_content(python: Path) -> bytes:
    """Bind the managed command to its installed environment on every platform."""
    if os.name == "nt":
        # Use pip's existing launcher generator and its interpreter-argument
        # API, including its quoting for paths with spaces. Generate only in
        # the new environment; activation retains the existing rollback path.
        subprocess.run([str(python), "-I", "-X", "utf8", "-c", WINDOWS_LAUNCHER, str(python.parent)], check=True)
        return (python.parent / "memory-book.exe").read_bytes()
    return ("#!/bin/sh\n# AI-Memory-Book managed launcher\nexec " + shlex.quote(str(python))
            + ' -I -X utf8 -m memory_book "$@"\n').encode("utf-8")


def manifest_release_tag(version: str) -> str | None:
    """Native-era tags use their manifest; historical archive routes stay exact."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)[A-Za-z0-9.+-]*", version)
    if match and tuple(map(int, match.groups())) >= (0, 8, 0):
        return version if version.startswith("v") else "v" + version
    return None


def manifest_require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("Invalid release manifest: " + message)


def safe_asset_name(name: object) -> bool:
    return isinstance(name, str) and len(name) <= 255 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", name) is not None


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_release_manifest(value: object, tag: str) -> dict:
    """Validate the selection fields; never turn malformed data into fallback."""
    manifest_require(type(value) is dict, "expected a JSON object")
    manifest_require(value.get("schema_version") == 2, "expected schema_version 2")
    manifest_require(value.get("repository") == "Afloat16/AI-Memory-Book"
                     and value.get("project") == "ai-memory-book", "different project")
    manifest_require(value.get("tag") == tag and value.get("version") == tag[1:], "different release version")
    manifest_require(isinstance(value.get("commit"), str)
                     and re.fullmatch(r"[0-9a-f]{40}", value["commit"]) is not None, "invalid source commit")
    assets = value.get("assets")
    manifest_require(type(assets) is dict and assets, "missing release assets")
    for filename, entry in assets.items():
        manifest_require(safe_asset_name(filename), "unsafe asset filename")
        manifest_require(type(entry) is dict and valid_sha256(entry.get("sha256"))
                         and type(entry.get("bytes")) is int and entry["bytes"] > 0,
                         "invalid asset digest or size: " + filename)
    fallback = value.get("python_fallback_wheel")
    manifest_require(safe_asset_name(fallback) and fallback.endswith(".whl") and fallback in assets,
                     "missing Python fallback wheel")
    wheels = value.get("native_wheels")
    manifest_require(type(wheels) is list and wheels, "missing native wheel inventory")
    seen = {fallback}
    for wheel in wheels:
        manifest_require(type(wheel) is dict, "invalid native wheel entry")
        filename = wheel.get("filename")
        manifest_require(safe_asset_name(filename) and filename.endswith(".whl")
                         and filename in assets and filename not in seen, "invalid or duplicate native wheel filename")
        seen.add(filename)
        manifest_require(wheel.get("sha256") == assets[filename]["sha256"]
                         and type(wheel.get("bytes")) is int and wheel["bytes"] == assets[filename]["bytes"],
                         "native wheel asset metadata differs: " + filename)
        manifest_require(valid_sha256(wheel.get("native_sha256")), "invalid native extension digest: " + filename)
        tags = wheel.get("tags")
        manifest_require(type(tags) is list and 0 < len(tags) <= 1024
                         and all(isinstance(tag, str) and 0 < len(tag) <= 255 for tag in tags)
                         and len(tags) == len(set(tags)), "invalid native wheel tags: " + filename)
    return value


def unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        manifest_require(key not in value, "duplicate JSON key: " + key)
        value[key] = item
    return value


def release_package_spec(python: Path, version: str, extras: bool) -> tuple[str, dict]:
    tag = manifest_release_tag(version)
    if tag is None:
        raise ValueError("A native-era release tag is required for manifest selection.")
    base = f"{REPOSITORY}/releases/download/{quote(tag, safe='')}/"
    url = base + "release-manifest.json"
    with urlopen(url, timeout=30) as response:
        raw = response.read(MANIFEST_LIMIT + 1)
    manifest_require(len(raw) <= MANIFEST_LIMIT, "manifest exceeds the size limit")
    value = validate_release_manifest(json.loads(raw, object_pairs_hook=unique_json_object), tag)
    selection_input = {key: value[key] for key in ("version", "python_fallback_wheel", "native_wheels")}
    try:
        output = subprocess.run([str(python), "-I", "-X", "utf8", "-c", WHEEL_SELECTOR], input=json.dumps(selection_input),
                                text=True, encoding="utf-8", capture_output=True, check=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()[-1500:]
        raise RuntimeError("Cannot select a release wheel for the isolated Python: " + detail) from error
    selected = json.loads(output.stdout)
    manifest_require(type(selected) is dict and isinstance(selected.get("filename"), str)
                     and selected["filename"] in value["assets"]
                     and selected.get("selection") in {"native", "python-fallback"}, "invalid wheel selector result")
    filename = selected["filename"]
    candidates = {wheel["filename"]: wheel for wheel in value["native_wheels"]}
    manifest_require((selected["selection"] == "native" and filename in candidates)
                     or (selected["selection"] == "python-fallback" and filename == value["python_fallback_wheel"]),
                     "wheel selector chose an undeclared artifact")
    digest = value["assets"][filename]["sha256"]
    name = "ai-memory-book[mcp,clients]" if extras else "ai-memory-book"
    spec = f"{name} @ {base}{quote(filename, safe='')}#sha256={digest}"
    record = {**selected, "sha256": digest, "manifest_url": url, "manifest_sha256": hashlib.sha256(raw).hexdigest()}
    if selected["selection"] == "native":
        record["native_sha256"] = candidates[filename]["native_sha256"]
    return spec, record


def installed_backend(python: Path) -> dict:
    """Inspect the installed default backend, independent of caller overrides."""
    environment = {**os.environ, "MEMORY_BOOK_TEXT_BACKEND": "auto"}
    output = subprocess.check_output([str(python), "-I", "-X", "utf8", "-c", BACKEND_PROBE],
                                     env=environment, text=True, encoding="utf-8")
    result = json.loads(output)
    if (type(result) is not dict or result.get("backend") not in {"native", "python"}
            or result.get("requested") != "auto"):
        raise RuntimeError("The installed backend probe returned an invalid result.")
    if result["backend"] == "native" and (not isinstance(result.get("extension"), str)
                                          or not valid_sha256(result.get("extension_sha256"))):
        raise RuntimeError("The installed native backend has no verified extension digest.")
    if result["backend"] == "python" and (result.get("extension") is not None
                                          or result.get("extension_sha256") is not None):
        raise RuntimeError("The installed Python backend unexpectedly reports a native extension.")
    return result


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
        artifact = f"{REPOSITORY}/archive/{version.lower()}.zip"
    elif re.fullmatch(r"v?\d+\.\d+\.\d+[A-Za-z0-9.+-]*", version):
        tag = version if version.startswith("v") else "v" + version
        if manifest_release_tag(version) is not None:
            raise ValueError("Releases from v0.8.0 require manifest selection using the isolated installation Python.")
        if tag in WHEEL_RELEASES:
            artifact = f"{REPOSITORY}/releases/download/{tag}/ai_memory_book-{tag[1:]}-py3-none-any.whl"
        else:
            artifact = f"{REPOSITORY}/archive/refs/tags/{quote(tag, safe='')}.zip"
    else:
        raise ValueError("--version must be a release tag such as v0.8.0 or a full 40-character commit SHA; use --source for a development checkout.")
    return f"{name} @ {artifact}"


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
    use_manifest = arguments.source is None and manifest_release_tag(arguments.version) is not None
    spec = None if use_manifest else package_spec(arguments.source, arguments.version, not arguments.without_extras)
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
            subprocess.run([sys.executable, "-I", "-X", "utf8", "-m", "venv", str(environment)], check=True)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            release_asset = None
            if use_manifest:
                spec, release_asset = release_package_spec(python, arguments.version, not arguments.without_extras)
            # pip can spawn build-backend interpreters without our -I flag.
            # Keep its caller-configured indexes/proxies and application values,
            # but do not pass Python import routing into those nested processes.
            build_environment = {key: value for key, value in os.environ.items()
                                 if key not in {"PYTHONHOME", "PYTHONPATH"}}
            subprocess.run([str(python), "-I", "-X", "utf8", "-m", "pip", "--disable-pip-version-check", "install", "--no-input", "--upgrade", spec],
                           env=build_environment, check=True)
            installed_version = subprocess.check_output([str(python), "-I", "-X", "utf8", "-m", "memory_book", "--version"], text=True, encoding="utf-8").strip()
            if not arguments.without_extras:
                subprocess.run([str(python), "-I", "-X", "utf8", "-c", "import mcp, tomlkit"], check=True)
            if arguments.source is None and not re.fullmatch(r"[0-9a-fA-F]{40}", arguments.version):
                if installed_version != arguments.version.removeprefix("v"):
                    raise RuntimeError(f"The release reports {installed_version}, but {arguments.version} was requested.")
            backend = installed_backend(python)
            if release_asset is not None:
                expected_backend = "native" if release_asset["selection"] == "native" else "python"
                if backend["backend"] != expected_backend:
                    raise RuntimeError(f"The selected {release_asset['filename']} installed the {backend['backend']} backend; expected {expected_backend}.")
                if expected_backend == "native" and backend["extension_sha256"] != release_asset["native_sha256"]:
                    raise RuntimeError("The installed native extension differs from the release manifest.")

            bin_dir.mkdir(parents=True, exist_ok=True)
            content = launcher_content(python)
            staged_launcher = stage_file(launcher, content, executable=True)
            result = {
                "schema": 1,
                "distribution": "ai-memory-book",
                "version": installed_version,
                "source": spec,
                "native_backend": backend["backend"],
                "native_backend_requested": backend["requested"],
                "native_extension": backend["extension"],
                "native_extension_sha256": backend["extension_sha256"],
                "release_asset": release_asset,
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
    print(f"Default text backend: {result['native_backend']}")
    print(f"\nNext: {command} setup --client claude-code")
    print(f"Background capture: {command} setup --client claude-code --capture --background")
    print(f"\nAdd {Path(result['launcher']).parent} to PATH to use the short memory-book command.")
    print(f"Installation record: {Path(result['prefix']) / 'installation.json'}")
    if result["previous_environment"]:
        print(f"Previous environment retained: {result['previous_environment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
