"""Pinned claude-mem native SQLite FTS component, not an observer workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import queue
import subprocess
import tarfile
import threading
import time
import zipfile

from .download import fetch_bytes

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "claude-mem-lock.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_download(root, spec, *, offline=False):
    path = root / spec["name"]
    if not path.exists():
        if offline:
            raise FileNotFoundError(f"Missing pinned artifact: {path}")
        data = fetch_bytes(spec["url"], timeout=180)
        if len(data) != spec["bytes"] or digest(data) != spec["sha256"]:
            raise ValueError(f"Pinned download integrity failed: {path.name}")
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
    data = path.read_bytes()
    if len(data) != spec["bytes"] or digest(data) != spec["sha256"]:
        raise ValueError(f"Pinned cache integrity failed: {path.name}")
    return path


def source_members(archive):
    """Read selected regular files only, without extracting archive paths."""
    selected = {}
    with tarfile.open(archive, "r:gz") as package:
        for member in package:
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or len(parts) < 2:
                continue
            relative = PurePosixPath(*parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe pinned source member")
            name = str(relative)
            if not (name.startswith("src/") or name in {"package.json", "LICENSE", "NOTICE"}):
                continue
            if name in selected:
                raise ValueError("Duplicate pinned source member")
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError("Missing source member bytes")
            selected[name] = stream.read()
    if not all(name in selected for name in (
            "src/services/sqlite/SessionSearch.ts", "src/services/sqlite/SessionStore.ts",
            "package.json", "LICENSE")):
        raise ValueError("Incomplete pinned source archive")
    return selected


def directory_fingerprint(root, expected):
    hashes = {}
    for name, data in sorted(expected.items()):
        actual = (root / name).read_bytes()
        if actual != data:
            raise ValueError(f"Executed source differs from pinned archive: {name}")
        hashes[name] = digest(actual)
    return digest(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())


def prepare(cache_dir, *, offline=False):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise RuntimeError("The pinned Bun adapter requires Linux x86-64")
    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = json.loads(LOCK_PATH.read_text())
    begin = time.perf_counter()
    source_archive = checked_download(root, lock["source_archive"], offline=offline)
    runtime_archive = checked_download(root, lock["runtime"], offline=offline)
    expected = source_members(source_archive)
    source_root = root / "verified-source"
    for name, data in expected.items():
        target = source_root / name
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError(f"Modified cached source: {name}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    fingerprint = directory_fingerprint(source_root, expected)
    with zipfile.ZipFile(runtime_archive) as package:
        data = package.read(lock["runtime"]["member"])
    if (len(data) != lock["runtime"]["binary_bytes"]
            or digest(data) != lock["runtime"]["binary_sha256"]):
        raise ValueError("Pinned Bun executable integrity failed")
    binary = root / "bun"
    if binary.exists() and binary.read_bytes() != data:
        raise ValueError("Modified cached Bun executable")
    if not binary.exists():
        binary.write_bytes(data)
    binary.chmod(0o755)
    metadata = {
        "repository": lock["repository"], "commit": lock["commit"],
        "package_version": lock["package_version"], "license": lock["license"],
        "source_url": lock["source_url"],
        "source_archive_sha256": lock["source_archive"]["sha256"],
        "runtime_archive_sha256": lock["runtime"]["sha256"],
        "runtime_binary_sha256": lock["runtime"]["binary_sha256"],
        "lock_sha256": digest(LOCK_PATH.read_bytes()),
        "source_sha256": fingerprint, "verified_source_files": len(expected),
        "preparation_ms": (time.perf_counter() - begin) * 1000
    }
    return binary, source_root, expected, metadata


def validate_native_rows(response, documents, project, limit):
    ids = response["hit_ids"]
    rows = response["native_payload"]
    if len(ids) != len(rows) or len(ids) > limit or len(ids) != len(set(ids)):
        raise ValueError("Native result count/identity mismatch")
    for identity, row in zip(ids, rows):
        if identity not in documents:
            raise ValueError("Unknown native source mapping")
        document = documents[identity]
        if (row.get("text") != document["text"]
                or row.get("title") != document["title"]
                or row.get("project") != document["project"]):
            raise ValueError("Native result changed original supplied source")
        if project is not None and row["project"] != project:
            raise ValueError("Native project scope violation")
    return ids


class ClaudeMemFTS:
    def __init__(self, documents, cache_dir, state_dir, *, offline=False, timeout=120):
        docs = list(documents)
        self.documents = {doc["id"]: doc for doc in docs}
        if len(self.documents) != len(docs):
            raise ValueError("Duplicate supplied page ID")
        for doc in docs:
            if any(not isinstance(doc.get(k), str) for k in
                   ("id", "project", "title", "text", "created_at")):
                raise ValueError("Invalid supplied page fields")
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        database = self.state_dir / "claude-mem.db"
        if database.exists():
            raise FileExistsError("Use a fresh state directory; measured runs never overwrite a DB")
        binary, self.source_root, self.expected, self.metadata = prepare(cache_dir, offline=offline)
        self.timeout = timeout
        self._id = 0
        self._closed = False
        self._responses = queue.Queue()
        self._stderr = []
        self._log = (self.state_dir / "native-stderr.log").open("w", encoding="utf8")
        settings = self.state_dir / "settings.json"
        settings.write_text(json.dumps({"CLAUDE_MEM_LOG_LEVEL": "SILENT"}))
        begin = time.perf_counter()
        self.process = subprocess.Popen(
            [str(binary), str(HERE / "claude_mem_bridge.ts"), str(self.source_root), str(database)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf8", bufsize=1,
            env={"PATH": os.defpath, "LANG": "C.UTF-8",
                 "CLAUDE_MEM_DATA_DIR": str(self.state_dir),
                 "CLAUDE_CONFIG_DIR": str(self.state_dir / "client-config"),
                 "CLAUDE_MEM_LOG_LEVEL": "SILENT"})
        self._out_thread = threading.Thread(target=self._stdout, daemon=True)
        self._err_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._out_thread.start()
        self._err_thread.start()
        try:
            ready = self._request({"op": "ping"})
            if ready["bun_version"] != "1.3.13":
                raise ValueError("Unexpected pinned Bun version")
            self.metadata["process_startup_ms"] = (time.perf_counter() - begin) * 1000
            initialized = self._request({"op": "init", "documents": [
                {key: doc[key] for key in ("id", "project", "title", "text", "created_at")}
                for doc in docs]})
            self.metadata.update(initialized)
            self.metadata.update(
                name="claude-mem supplied-source SQLite FTS retrieval component",
                implementation="unchanged pinned SessionStore schema and SessionSearch.searchObservations; direct Bun TypeScript imports",
                comparison_scope="supplied-source retrieval component, not native observer or full product",
                latency_scope="native function and persistent Python/Bun JSON bridge separately",
                representation="original page title/text; empty semantic fields; harness bulk INSERT with native FTS triggers",
                native_payload_surface="unmodified returned observation row array; not MCP or viewer presentation",
                result_cache="no adapter result cache; SQLite and process caches warm naturally",
                ready=ready)
        except BaseException:
            self.close()
            raise

    def _stdout(self):
        for line in self.process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def _read_stderr(self):
        for line in self.process.stderr:
            self._log.write(line)
            self._log.flush()
            self._stderr.append(line)
            if len(self._stderr) > 100:
                del self._stderr[:50]

    def _request(self, value):
        if self._closed:
            raise RuntimeError("Native component is closed")
        self._id += 1
        self.process.stdin.write(json.dumps({"id": self._id, **value}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        try:
            line = self._responses.get(timeout=self.timeout)
        except queue.Empty as error:
            raise TimeoutError("Native component response timeout") from error
        if line is None:
            raise RuntimeError("Native component exited:\n" + "".join(self._stderr))
        result = json.loads(line)
        if result.get("id") != self._id:
            raise ValueError("Native bridge response identity mismatch")
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    def search(self, query, project=None, limit=5):
        if not isinstance(query, str) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Invalid query/limit")
        started = time.perf_counter()
        result = self._request({"op": "search", "query": query, "project": project, "limit": limit})
        result["bridge_ms"] = (time.perf_counter() - started) * 1000
        validate_native_rows(result, self.documents, project, limit)
        return result

    def close(self):
        if self._closed:
            return
        try:
            if self.process.poll() is None:
                self.metadata["shutdown"] = self._request({"op": "close"})
        finally:
            self._closed = True
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self._err_thread.join(timeout=5)
            self._out_thread.join(timeout=5)
            for stream in (self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()
            self._log.close()
            self.metadata["source_sha256_after"] = directory_fingerprint(self.source_root, self.expected)
            self.metadata["source_unchanged"] = self.metadata["source_sha256"] == self.metadata["source_sha256_after"]
            self.metadata["native_process_exit_code"] = self.process.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.cache, offline=args.offline)[3], indent=2))


if __name__ == "__main__":
    main()
