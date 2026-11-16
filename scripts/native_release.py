"""Audit v0.8+ native wheels and prepare the compiler-free fallback artifacts.

Native wheels are supplied by the same release workflow's platform jobs. Their
receipts bind committed build inputs, complete wheel contents, and a real
installed-native smoke check. This module does not rebuild foreign binaries or
claim that a receipt is a reproducible-build proof.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import datetime
from email.parser import BytesParser
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

try:
    from scripts import release as legacy
except ModuleNotFoundError:
    import release as legacy


ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSIONS = tuple(f"3.{minor}" for minor in range(10, 16))
TARGETS = ("linux_x86_64", "linux_aarch64", "macos_x86_64", "macos_arm64", "windows_amd64")
EXPECTED_MATRIX = frozenset((python, target) for python in PYTHON_VERSIONS for target in TARGETS)
BUILD_INPUTS = ("pyproject.toml", "setup.py", "README.md", "LICENSE")
AUDITWHEEL_VERSION = "6.4.2"
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_BUILD_LOG_BYTES = 4 * 1024 * 1024
require, sha = legacy.require, legacy.sha


def source_inputs(root, sources):
    """Return the exact source/build bytes which every platform must share."""
    result = {"src/" + name: data for name, data in sources.items()}
    for name in BUILD_INPUTS:
        path = root / name
        require(path.is_file() and not path.is_symlink(), "Missing or linked build input: " + name)
        result[name] = path.read_bytes()
    return result


def file_hashes(files):
    return {name: sha(data) for name, data in sorted(files.items())}


def _unique_json(data):
    def pairs(values):
        result = {}
        for name, value in values:
            require(name not in result, "Duplicate JSON key: " + name)
            result[name] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def _wheel_parts(filename):
    require(filename.endswith(".whl"), "Expected a wheel")
    parts = filename[:-4].split("-")
    require(len(parts) == 5 and parts[0] == "ai_memory_book", "Unexpected wheel filename")
    _, version, python_tag, abi_tag, platform_tag = parts
    return {"version": version, "python_tag": python_tag, "abi_tag": abi_tag,
            "platform_tag": platform_tag,
            "tags": sorted(f"{python_tag}-{abi_tag}-{tag}" for tag in platform_tag.split("."))}


def _target_platform(platform_tag, target):
    patterns = {
        "linux_x86_64": r"(?:manylinux_2_17|manylinux2014)_x86_64",
        "linux_aarch64": r"(?:manylinux_2_17|manylinux2014)_aarch64",
        "macos_x86_64": r"macosx_\d+_\d+_x86_64",
        "macos_arm64": r"macosx_\d+_\d+_arm64",
        "windows_amd64": r"win_amd64",
    }
    return target in patterns and all(re.fullmatch(patterns[target], tag)
                                       for tag in platform_tag.split("."))


def _zip_members(path):
    require(path.is_file() and not path.is_symlink(), "Wheel must be an ordinary file")
    require(path.stat().st_size <= legacy.MAX_ARCHIVE_BYTES, "Unexpectedly large wheel")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(sum(info.file_size for info in infos) <= legacy.MAX_ARCHIVE_BYTES,
                "Unexpected wheel expansion size")
        require(len({info.filename for info in infos}) == len(infos), "Duplicate wheel member")
        info_root = "ai_memory_book-" + _wheel_parts(path.name)["version"] + ".dist-info/"
        for info in infos:
            legacy.safe_member(info.filename)
            kind = (info.external_attr >> 16) & 0o170000
            if info.is_dir():
                # auditwheel 6.4.2 writes explicit empty ZIP directory entries;
                # RECORD inventories files, not this directory metadata.
                require(info.file_size == 0 and kind in {0, 0o040000}
                        and (info.filename.startswith("memory_book/") or info.filename.startswith(info_root)),
                        "Unexpected wheel directory metadata")
            else:
                require(kind in {0, 0o100000}, "Wheel contains a symbolic link or special file")
        return {info.filename: archive.read(info) for info in infos if not info.is_dir()}


def _check_record(members, info_root):
    name = info_root + "RECORD"
    require(name in members, "Wheel is missing RECORD")
    rows = list(csv.reader(io.StringIO(members[name].decode("utf-8"))))
    require(all(len(row) == 3 for row in rows), "Invalid wheel RECORD row")
    require(len({row[0] for row in rows}) == len(rows), "Duplicate wheel RECORD entry")
    require({row[0] for row in rows} == set(members), "Wheel RECORD does not cover every member")
    for member, digest, size in rows:
        if member == name:
            require(digest == size == "", "RECORD must not contain its own hash")
        else:
            expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(members[member]).digest()).decode().rstrip("=")
            require(digest == expected and size == str(len(members[member])),
                    "Wheel RECORD hash/size differs: " + member)


def inspect_wheel(path, identity, sources, *, target=None):
    """Validate source bytes, tags, metadata, RECORD and the only allowed binary."""
    parts = _wheel_parts(path.name)
    require(parts["version"] == identity["version"], "Wheel version differs from release")
    members = _zip_members(path)
    info_root = f"ai_memory_book-{identity['version']}.dist-info/"
    require(all(name.startswith("memory_book/") or name.startswith(info_root) for name in members),
            "Unexpected wheel package")
    require(info_root + "METADATA" in members and info_root + "WHEEL" in members,
            "Wheel metadata is incomplete")
    metadata = BytesParser().parsebytes(members[info_root + "METADATA"])
    require(metadata.get("Name") == "ai-memory-book" and metadata.get("Version") == identity["version"],
            "Wheel project metadata differs")
    require(metadata.get("Requires-Python") == ">=3.10", "Wheel Python requirement differs")
    require(info_root + "entry_points.txt" in members, "Wheel console entry point is missing")
    entrypoints = configparser.ConfigParser(interpolation=None)
    entrypoints.read_string(members[info_root + "entry_points.txt"].decode("utf-8"))
    require(entrypoints.sections() == ["console_scripts"]
            and dict(entrypoints["console_scripts"]) == {"memory-book": "memory_book.cli:main"},
            "Wheel console entry point differs")
    wheel = BytesParser().parsebytes(members[info_root + "WHEEL"])
    require(sorted(wheel.get_all("Tag", [])) == parts["tags"], "Wheel filename and WHEEL tags differ")
    _check_record(members, info_root)
    actual = {name: data for name, data in members.items() if name.startswith("memory_book/")}
    native = [name for name in actual if re.fullmatch(r"memory_book/_native\.[^/]+\.(?:so|pyd)", name)]
    if target is None:
        require(parts["python_tag"] == "py3" and parts["abi_tag"] == "none" and parts["platform_tag"] == "any",
                "Fallback wheel must be py3-none-any")
        require(not native and wheel.get("Root-Is-Purelib", "").lower() == "true",
                "Fallback wheel unexpectedly contains a native extension")
    else:
        require(parts["python_tag"] in {"cp" + value.replace(".", "") for value in PYTHON_VERSIONS}
                and parts["abi_tag"] == parts["python_tag"], "Unsupported CPython ABI tag")
        require(_target_platform(parts["platform_tag"], target), "Wheel platform differs from matrix target")
        require(len(native) == 1 and wheel.get("Root-Is-Purelib", "").lower() == "false",
                "Native wheel must contain exactly one _native extension")
        digits = parts["python_tag"][2:]
        require((".cpython-" + digits + "-") in native[0] or (".cp" + digits + "-") in native[0],
                "Native extension filename differs from CPython tag")
        require(native[0].endswith(".pyd") == (target == "windows_amd64"),
                "Native extension suffix differs from target")
        actual.pop(native[0])
    require(actual == sources, "Wheel runtime/source/reader bytes differ from committed source")
    result = {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha(path.read_bytes()),
              **{key: value for key, value in parts.items() if key != "version"}}
    if native:
        result.update(native_member=native[0], native_bytes=len(members[native[0]]),
                      native_sha256=sha(members[native[0]]))
    return result


def inspect_sdist(path, identity, sources, inputs):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= legacy.MAX_ARCHIVE_BYTES,
            "Unexpected source archive")
    prefix = "ai_memory_book-" + identity["version"] + "/"
    with tarfile.open(path, "r:gz") as archive:
        entries = archive.getmembers()
        require(sum(entry.size for entry in entries) <= legacy.MAX_ARCHIVE_BYTES, "Unexpected source archive expansion size")
        require(all(entry.isfile() or entry.isdir() for entry in entries), "Source archive contains links or special files")
        require(len({entry.name for entry in entries}) == len(entries), "Duplicate source archive member")
        for entry in entries:
            legacy.safe_member(entry.name)
            require(entry.name == prefix.rstrip("/") or entry.name.startswith(prefix), "Unexpected source archive root")
        members = {entry.name: archive.extractfile(entry).read() for entry in entries if entry.isfile()}
    relative = {name.removeprefix(prefix): data for name, data in members.items()}
    require(all(name in {*BUILD_INPUTS, "PKG-INFO", "setup.cfg"}
                or name.startswith("src/memory_book/") or name.startswith("src/ai_memory_book.egg-info/")
                for name in relative), "Unexpected source archive content")
    actual = {name.removeprefix("src/"): data for name, data in relative.items() if name.startswith("src/memory_book/")}
    require(actual == sources, "Source archive runtime/source/reader bytes differ from committed source")
    require(all(relative.get(name) == inputs[name] for name in BUILD_INPUTS), "Source archive build inputs differ")
    return members


def canonicalize_fallback(path, identity, sources, inputs):
    """Normalize archive metadata only; never alter a supplied native wheel."""
    epoch = identity["epoch"]
    buffer = io.BytesIO()
    if path.suffix == ".whl":
        inspect_wheel(path, identity, sources)
        members = _zip_members(path)
        timestamp = datetime.datetime.fromtimestamp(max(epoch, 315532800), datetime.timezone.utc).timetuple()[:6]
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(members.items()):
                info = zipfile.ZipInfo(name, timestamp)
                info.create_system, info.external_attr, info.compress_type = 3, 0o100644 << 16, zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
    else:
        members = inspect_sdist(path, identity, sources, inputs)
        with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(members.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), 0o644, epoch
                    archive.addfile(info, io.BytesIO(data))
    path.write_bytes(buffer.getvalue())


def validate_receipt(path, wheel_path, identity, sources, inputs, *, run_id=None, run_attempt=None):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_RECEIPT_BYTES,
            "Unexpected native receipt")
    receipt = _unique_json(path.read_text(encoding="utf-8"))
    require(receipt.get("schema_version") == 1, "Unknown native receipt schema")
    source, build = receipt.get("source", {}), receipt.get("build", {})
    require(source.get("commit") == identity["commit"] and source.get("tree") == identity["tree"],
            "Native receipt belongs to another source commit/tree")
    require(source.get("files_sha256") == file_hashes(inputs), "Native receipt source/build hashes differ")
    require(build.get("implementation") == "cpython" and build.get("python_version") in PYTHON_VERSIONS
            and build.get("target") in TARGETS, "Unsupported native receipt matrix cell")
    require(build.get("python_tag") == "cp" + build["python_version"].replace(".", ""),
            "Native receipt Python version/tag differs")
    require(isinstance(build.get("run_id"), str) and re.fullmatch(r"[1-9][0-9]*", build["run_id"])
            and type(build.get("run_attempt")) is int and build["run_attempt"] >= 1,
            "Native receipt needs a workflow run and attempt")
    if run_id is not None:
        require(build["run_id"] == str(run_id), "Native receipt belongs to another workflow run")
    if run_attempt is not None:
        require(build["run_attempt"] == int(run_attempt), "Native receipt belongs to another workflow attempt")
    expected_tools = dict(legacy.BUILD_TOOLS)
    if build["target"].startswith("linux_"):
        expected_tools["auditwheel"] = AUDITWHEEL_VERSION
    require(build.get("tools") == expected_tools, "Native receipt build tool versions differ")
    expected_flags = ["/O2"] if build["target"] == "windows_amd64" else ["-O3"]
    require(build.get("native_build_mode") == "1" and build.get("extra_compile_args") == expected_flags,
            "Native receipt did not require the declared native compiler flags")
    log = build.get("build_log", {})
    require(isinstance(log.get("filename"), str) and Path(log["filename"]).name == log["filename"]
            and type(log.get("bytes")) is int and 0 < log["bytes"] <= MAX_BUILD_LOG_BYTES
            and isinstance(log.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", log["sha256"])
            and isinstance(log.get("commands"), list) and log["commands"]
            and all(isinstance(line, str) and "_native" in line for line in log["commands"])
            and any(expected_flags[0] in line for line in log["commands"]),
            "Native receipt is missing compiler-log provenance")
    actual = inspect_wheel(wheel_path, identity, sources, target=build["target"])
    require(actual == receipt.get("wheel"), "Native wheel bytes or metadata differ from receipt")
    require(actual["python_tag"] == build["python_tag"], "Native wheel/receipt Python tag differs")
    require(path.name == wheel_path.name + ".receipt.json", "Native receipt filename differs from wheel")
    smoke = receipt.get("runtime_smoke", {})
    require(smoke.get("backend") == "native" and smoke.get("native_sha256") == actual["native_sha256"]
            and smoke.get("version") == identity["version"]
            and smoke.get("python_version") == build["python_version"]
            and smoke.get("source_files_match") is True and smoke.get("ingest_recall_sources_match") is True,
            "Native receipt lacks the matching installed-native smoke result")
    return {**actual, "target": build["target"], "python_version": build["python_version"],
            "receipt": path.name}, build


def collect_native(native_dir, identity, sources, inputs):
    require(native_dir.is_dir() and not native_dir.is_symlink(), "Native wheel directory is missing")
    files = [path for path in native_dir.rglob("*") if path.is_file() or path.is_symlink()]
    require(all(not path.is_symlink() and (path.name.endswith(".whl") or path.name.endswith(".whl.receipt.json"))
                for path in files), "Unexpected native artifact or symbolic link")
    require(len({path.name for path in files}) == len(files), "Duplicate native artifact filename")
    by_name = {path.name: path for path in files}
    wheels = [path for path in files if path.name.endswith(".whl")]
    require(set(by_name) == {name for wheel in wheels for name in (wheel.name, wheel.name + ".receipt.json")},
            "Every native wheel needs exactly one receipt")
    run_id, attempt = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")
    records, cells, provenance = [], set(), None
    for wheel in sorted(wheels):
        record, build = validate_receipt(by_name[wheel.name + ".receipt.json"], wheel, identity, sources, inputs,
                                        run_id=run_id, run_attempt=attempt)
        cell = (build["python_version"], build["target"])
        require(cell not in cells, "Duplicate native matrix cell")
        cells.add(cell)
        origin = {"run_id": build["run_id"], "run_attempt": build["run_attempt"]}
        require(provenance is None or origin == provenance, "Native wheels mix workflow runs or attempts")
        provenance = origin
        records.append(record)
    require(cells == EXPECTED_MATRIX, "Native wheel matrix is incomplete or unexpected")
    return records, by_name, provenance


_NATIVE_SMOKE = r'''
import hashlib, importlib.metadata, json, pathlib, sys
import memory_book
from memory_book import MemoryBook, _native, _text_backend
expected = json.loads(sys.argv[1])
assert _text_backend.BACKEND_NAME == "native"
assert memory_book.__version__ == importlib.metadata.version("ai-memory-book") == expected["version"]
assert hashlib.sha256(pathlib.Path(_native.__file__).read_bytes()).hexdigest() == expected["native_sha256"]
package = pathlib.Path(memory_book.__file__).parent
for name, digest in expected["runtime_files"].items():
    assert hashlib.sha256((package / name.removeprefix("memory_book/")).read_bytes()).hexdigest() == digest
with MemoryBook(":memory:", segmentation="turn") as book:
    for project, value in (("alpha", "82"), ("beta", "999")):
        book.ingest({"project": project, "session_id": "one", "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": "café Straße 缓存压力"},
                         {"role": "assistant", "content": "café Straße 缓存压力 is " + value + "."}]})
    result = book.recall("cafe strasse 缓存压力", project="alpha", use_cache=False)
    assert "82" in result["context"] and "999" not in result["context"] and result["results"]
    for hit in result["results"]:
        page = book.read(hit["id"], project="alpha")["content"]
        for lo, hi in hit["excerpt_spans"]:
            assert page[lo:hi] in hit["text"]
        assert hit["source_refs"] and all(ref["project"] == "alpha" for ref in hit["source_refs"])
        for ref in hit["source_refs"]:
            turn = book.db.execute("SELECT t.content FROM turns t JOIN sessions s ON s.id=t.session_pk "
                "WHERE s.project_id=? AND s.external_id=? AND t.ordinal=?",
                (ref["project"], ref["session_id"], ref["turn_index"])).fetchone()[0]
            assert page[ref["start"]:ref["end"]] == turn[ref["turn_start"]:ref["turn_end"]]
print(json.dumps({"backend": "native", "native_sha256": expected["native_sha256"],
    "version": expected["version"], "python_version": ".".join(map(str, sys.version_info[:2])),
    "source_files_match": True, "ingest_recall_sources_match": True}))
'''


def native_runtime_smoke(wheel, identity, sources):
    expected = {"version": identity["version"], "native_sha256": wheel["native_sha256"],
                "runtime_files": file_hashes(sources)}
    env = legacy.clean_environment()
    env["MEMORY_BOOK_TEXT_BACKEND"] = "native"
    result = legacy.command([sys.executable, "-I", "-c", _NATIVE_SMOKE, json.dumps(expected)], env=env)
    return _unique_json(result.stdout.decode("utf-8"))


def _portable_identity(root):
    """Receipt jobs include Python 3.10, before stdlib tomllib existed."""
    head = legacy.git(root, "rev-parse", "HEAD").decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}", head), "Unexpected source commit")
    require(not legacy.git(root, "status", "--porcelain", "--untracked-files=no"), "Build inputs must be committed")
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", project)
    require(section is not None, "Missing project metadata")
    version = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$', section[1], re.M)
    require(version is not None and tuple(map(int, version[1].split("."))) >= (0, 8, 0),
            "Native releases require version 0.8.0 or newer")
    names = legacy.git(root, "ls-tree", "-r", "--name-only", head, "src/memory_book").decode().splitlines()
    sources = {}
    for name in names:
        path = root / name
        require(path.is_file() and not path.is_symlink(), "Unexpected source entry")
        data = path.read_bytes()
        require(data == legacy.git(root, "show", head + ":" + name), "Source differs from committed bytes")
        sources[name.removeprefix("src/")] = data
    identity = {"version": version[1], "tag": "v" + version[1], "commit": head,
                "tree": legacy.git(root, "rev-parse", "HEAD^{tree}").decode().strip()}
    inputs = source_inputs(root, sources)
    for name, data in inputs.items():
        require(data == legacy.git(root, "show", head + ":" + name), "Build input differs from committed bytes")
    return identity, sources, inputs


def _host_target():
    system, machine = platform.system(), platform.machine().lower()
    if system == "Linux" and machine in {"x86_64", "amd64", "aarch64", "arm64"}:
        return "linux_x86_64" if machine in {"x86_64", "amd64"} else "linux_aarch64"
    if system == "Darwin" and machine in {"x86_64", "arm64"}:
        return "macos_" + machine
    if system == "Windows" and machine in {"amd64", "x86_64"}:
        return "windows_amd64"
    return None


def build_log_provenance(root, target):
    """Keep actual compiler command lines without copying arbitrary pip output."""
    require(os.environ.get("MEMORY_BOOK_BUILD_NATIVE") == "1", "Receipt creation requires MEMORY_BOOK_BUILD_NATIVE=1")
    declared = os.environ.get("NATIVE_BUILD_LOG")
    require(bool(declared), "NATIVE_BUILD_LOG must identify the captured native build output")
    path = Path(declared)
    if not path.is_absolute():
        path = root / path
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_BUILD_LOG_BYTES,
            "Native build log is missing, linked, empty or oversized")
    data = path.read_bytes()
    commands = []
    compiler = re.compile(r"\b(?:gcc(?:-\d+)?|g\+\+|cc|clang(?:-cl)?|cl\.exe|link\.exe)\b", re.I)
    for line in data.decode("utf-8", errors="replace").splitlines():
        if ("_native" in line and compiler.search(line)
                and re.search(r"(?:^|\s)(?:-c|-shared|-bundle|/c|/DLL)(?:\s|$)", line, re.I)):
            commands.append(line.strip())
    flags = ["/O2"] if target == "windows_amd64" else ["-O3"]
    require(commands and any(flags[0] in line for line in commands),
            "Native build log does not retain the expected compiler command and optimization flag")
    return {"filename": path.name, "bytes": len(data), "sha256": sha(data), "commands": commands}


def write_receipt(root, wheel_path, output, target, *, run_id=None, run_attempt=None):
    require(not output.exists(), "Never overwrite an existing native receipt")
    require(sys.implementation.name == "cpython" and _host_target() == target, "Receipt target differs from running interpreter")
    identity, sources, inputs = _portable_identity(root)
    python_version = ".".join(map(str, sys.version_info[:2]))
    require((python_version, target) in EXPECTED_MATRIX, "Unsupported native build cell")
    wheel = inspect_wheel(wheel_path, identity, sources, target=target)
    require(wheel["python_tag"] == "cp" + python_version.replace(".", ""), "Wheel differs from running CPython")
    tools = dict(legacy.BUILD_TOOLS)
    if target.startswith("linux_"):
        tools["auditwheel"] = AUDITWHEEL_VERSION
    require({name: importlib.metadata.version(name) for name in tools} == tools, "Native build tool versions differ")
    build = {"implementation": "cpython", "python_version": python_version,
             "python_tag": wheel["python_tag"], "target": target, "tools": tools,
             "native_build_mode": "1", "extra_compile_args": ["/O2"] if target == "windows_amd64" else ["-O3"],
             "build_log": build_log_provenance(root, target),
             "run_id": str(run_id or os.environ.get("GITHUB_RUN_ID", "")),
             "run_attempt": int(run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT", "0"))}
    receipt = {"schema_version": 1, "source": {"commit": identity["commit"], "tree": identity["tree"],
                "files_sha256": file_hashes(inputs)}, "build": build, "wheel": wheel,
               "runtime_smoke": native_runtime_smoke(wheel, identity, sources)}
    require(output.name == wheel_path.name + ".receipt.json", "Receipt filename must be wheel filename plus .receipt.json")
    # Validate the same data before exposing it as a workflow artifact.
    with tempfile.TemporaryDirectory(prefix="native-receipt-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        validate_receipt(staged, wheel_path, identity, sources, inputs,
                         run_id=build["run_id"], run_attempt=build["run_attempt"])
        output.write_bytes(staged.read_bytes())
    return receipt


def install_fallback_smoke(artifact, identity, workspace):
    env = legacy.clean_environment()
    env.update(MEMORY_BOOK_BUILD_NATIVE="0", MEMORY_BOOK_TEXT_BACKEND="python")
    with tempfile.TemporaryDirectory(prefix="fallback-install-", dir=workspace) as temporary:
        directory = Path(temporary)
        legacy.command([sys.executable, "-m", "venv", str(directory / "venv")], env=env)
        python = directory / "venv/bin/python"
        if artifact.name.endswith(".tar.gz"):
            legacy.command([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check",
                            "setuptools==" + legacy.BUILD_TOOLS["setuptools"],
                            "wheel==" + legacy.BUILD_TOOLS["wheel"]], env=env)
        legacy.command([str(python), "-I", "-m", "pip", "install", "--no-deps", "--no-build-isolation",
                        str(artifact)], env=env)
        code = '''import importlib.metadata, importlib.util, memory_book
from memory_book import MemoryBook, _text_backend
assert _text_backend.BACKEND_NAME == "python" and importlib.util.find_spec("memory_book._native") is None
assert memory_book.__version__ == importlib.metadata.version("ai-memory-book") == VERSION
with MemoryBook(":memory:") as book:
    book.ingest({"project": "release-check", "session_id": "one", "created_at": "2026-01-01T00:00:00Z",
        "messages": [{"role": "user", "content": "Native fallback café cache marker 82."}]})
    result = book.recall("cafe cache marker", project="release-check", use_cache=False)
    assert "82" in result["context"] and result["results"][0]["source_refs"]
'''.replace("VERSION", repr(identity["version"]))
        legacy.command([str(python), "-I", "-c", code], cwd=directory, env=env)
        actual = legacy.command([str(directory / "venv/bin/memory-book"), "--version"], cwd=directory, env=env).stdout.decode().strip()
        require(actual == identity["version"], "Fallback console command has another version")


def prepare(root, output, identity, sources, native_dir):
    """Create all v0.8+ release assets after checking the complete native matrix."""
    root, output, native_dir = Path(root), Path(output), Path(native_dir)
    require(tuple(map(int, identity["version"].split("."))) >= (0, 8, 0), "Historical releases use the original preparation path")
    require(not output.exists(), "Choose a fresh asset directory; never overwrite a previous local build")
    require({name: importlib.metadata.version(name) for name in legacy.BUILD_TOOLS} == legacy.BUILD_TOOLS,
            "Build tool versions differ")
    inputs = source_inputs(root, sources)
    for name, data in inputs.items():
        require(data == legacy.git(root, "show", identity["commit"] + ":" + name), "Build input is not committed")
    records, native_files, provenance = collect_native(native_dir, identity, sources, inputs)
    output.mkdir(parents=True)
    env = legacy.clean_environment()
    env.update(SOURCE_DATE_EPOCH=str(identity["epoch"]), MEMORY_BOOK_BUILD_NATIVE="0", MEMORY_BOOK_TEXT_BACKEND="python")
    fallback = f"ai_memory_book-{identity['version']}-py3-none-any.whl"
    sdist = f"ai_memory_book-{identity['version']}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="release-native-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        for name, data in inputs.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        legacy.command([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output), str(stage)],
                       cwd=stage, env=env)
        require({path.name for path in output.iterdir()} == {fallback, sdist}, "Expected one fallback wheel and one source distribution")
        for artifact in sorted(output.iterdir()):
            canonicalize_fallback(artifact, identity, sources, inputs)
            install_fallback_smoke(artifact, identity, stage)
    for name, path in sorted(native_files.items()):
        shutil.copyfile(path, output / name)
    for record in records:
        validate_receipt(output / record["receipt"], output / record["filename"], identity, sources, inputs,
                         run_id=provenance["run_id"], run_attempt=provenance["run_attempt"])
    for name in legacy.INSTALLERS:
        data = (root / "scripts" / name).read_bytes()
        require(data == legacy.git(root, "show", identity["commit"] + ":scripts/" + name), "Installer is not committed")
        require(identity["tag"].encode() in data, "Installer does not refer to this release")
        (output / name).write_bytes(data)
    assets = {path.name: {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
              for path in sorted(output.iterdir())}
    manifest = {"schema_version": 2, **identity, "repository": legacy.REPOSITORY, "project": "ai-memory-book",
        "prerelease": legacy.release_prerelease(identity["tag"]),
        "build_tools": dict(legacy.BUILD_TOOLS), "assets": assets,
        "runtime_files_sha256": file_hashes(sources), "source_files_sha256": file_hashes(inputs),
        "python_fallback_wheel": fallback, "source_distribution": sdist,
        "native_wheels": records, "native_build_run": provenance,
        "checks": {"fallback_wheel_and_sdist_installed_in_separate_clean_environments": True,
                   "native_matrix_receipts_and_installed_native_smokes_validated": True,
                   "runtime_source_and_reader_bytes_match_source": True,
                   "large_research_data_excluded": True},
        "scope": "GitHub release; no PyPI publication, model download or benchmark execution. Native receipts attest the supplied workflow builds; binaries are not rebuilt during aggregation."}
    (output / "release-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("".join(sha(path.read_bytes()) + "  " + path.name + "\n"
                                            for path in sorted(output.iterdir())), encoding="utf-8")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    receipt = commands.add_parser("receipt", help="Record a wheel after installing it in this native build interpreter")
    receipt.add_argument("--root", type=Path, default=ROOT)
    receipt.add_argument("--wheel", type=Path, required=True)
    receipt.add_argument("--output", type=Path, required=True)
    receipt.add_argument("--target", choices=TARGETS, required=True)
    receipt.add_argument("--run-id")
    receipt.add_argument("--run-attempt", type=int)
    args = parser.parse_args()
    result = write_receipt(args.root.resolve(), args.wheel.resolve(), args.output.resolve(), args.target,
                           run_id=args.run_id, run_attempt=args.run_attempt)
    print(json.dumps({"receipt": str(args.output), "wheel": result["wheel"]["filename"],
                      "sha256": result["wheel"]["sha256"], "target": args.target}))


if __name__ == "__main__":
    main()
