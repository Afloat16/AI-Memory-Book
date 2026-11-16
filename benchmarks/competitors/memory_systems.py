"""Transport, artifact verification and contracts for real memory components.

No ranker or embedding is implemented here. The isolated worker calls pinned
upstream packages; existing TypeScript adapters remain unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import queue
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK_PATH = HERE / "memory-systems-lock.json"
PYTHON_BACKENDS = ("basic_memory", "chroma", "langgraph", "mem0")
BACKENDS = ("book", "billion", "claude_mem", *PYTHON_BACKENDS)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def validate_documents(documents):
    lookup = {}
    for doc in documents:
        if any(not isinstance(doc.get(key), str) or not doc[key]
               for key in ("id", "project", "text", "created_at")):
            raise ValueError("Invalid supplied original page")
        if not isinstance(doc.get("title"), str) or doc["id"] in lookup:
            raise ValueError("Invalid title or repeated supplied page ID")
        lookup[doc["id"]] = doc
    return lookup


def validate_response(response, documents, project, limit=5):
    """Authenticate adapter IDs against native original-body evidence.

    Do not silently filter invalid/foreign results or fill missing candidates.
    A backend returning one is an integrity failure, not a quality miss.
    """
    ids, records = response["hit_ids"], response["records"]
    if (not isinstance(ids, list) or not isinstance(records, list)
            or len(ids) > limit or len(ids) != len(records)
            or len(ids) != len(set(ids))):
        raise ValueError("Invalid native result count or duplicate identity")
    for identity, record in zip(ids, records):
        if identity not in documents:
            raise ValueError("Unmapped native page")
        doc = documents[identity]
        if (record.get("id") != identity or record.get("project") != project
                or doc["project"] != project or record.get("text") != doc["text"]):
            raise ValueError("Native result changed source or crossed project boundary")
    return ids


def stable_native(value):
    if isinstance(value, dict):
        return {k: stable_native(v) for k, v in value.items()
                if k not in {"latency_ms", "search_ms", "bridge_ms",
                             "native_cpu_user_us", "native_cpu_system_us"}}
    if isinstance(value, (list, tuple)):
        return [stable_native(v) for v in value]
    return value


def sanitized_environment(state, cache):
    """Allowlist platform essentials; never inherit provider secrets/config."""
    state, cache = Path(state).resolve(), Path(cache).resolve()
    env = {key: os.environ[key] for key in
           ("PATH", "SYSTEMROOT", "WINDIR", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
           if key in os.environ}
    env.update({
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0",
        "PYTHONUNBUFFERED": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
        "BASIC_MEMORY_CONFIG_DIR": str(state / "basic-config"),
        "BASIC_MEMORY_HOME": str(state / "notes"),
        "BASIC_MEMORY_LOG_LEVEL": "ERROR", "BASIC_MEMORY_ENV": "test",
        "MEM0_DIR": str(state / "mem0-config"), "MEM0_TELEMETRY": "false",
        "ANONYMIZED_TELEMETRY": "false", "LOGFIRE_SEND_TO_LOGFIRE": "false",
        "OTEL_SDK_DISABLED": "true", "LANGCHAIN_TRACING_V2": "false",
        "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false", "FASTEMBED_CACHE_PATH": str(cache / "fastembed"),
        "XDG_CACHE_HOME": str(state / "cache"), "XDG_CONFIG_HOME": str(state / "config"),
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    })
    return env


def model_artifacts(cache, *, download=False):
    """Verify both official archive and every extracted regular model file."""
    spec = json.loads(LOCK_PATH.read_text())["model"]
    root = Path(cache).resolve() / "minilm"
    archive = root / "onnx.tar.gz"
    if not archive.exists():
        if not download:
            raise FileNotFoundError("Run --prepare first: missing verified MiniLM archive")
        root.mkdir(parents=True, exist_ok=True)
        temp = root / "onnx.tar.gz.partial"
        request = urllib.request.Request(spec["archive_url"],
                                        headers={"User-Agent": "AI-Memory-Book-benchmark/1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as source, temp.open("xb") as out:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    out.write(chunk)
            if sha_file(temp) != spec["archive_sha256"]:
                raise ValueError("Official MiniLM archive digest mismatch")
            temp.replace(archive)
        finally:
            temp.unlink(missing_ok=True)
    if sha_file(archive) != spec["archive_sha256"]:
        raise ValueError("Cached MiniLM archive was modified")
    files = {}
    with tarfile.open(archive, "r:gz") as package:
        for member in package:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk():
                raise ValueError("Unsafe model archive member")
            if member.isdir():
                continue
            if not member.isfile() or not name.parts or name.parts[0] != "onnx":
                raise ValueError("Unexpected model archive member")
            relative = name.as_posix()
            if relative in files:
                raise ValueError("Duplicate model archive member")
            target = root / relative
            if target.is_symlink() or any(p.is_symlink() for p in target.parents):
                raise ValueError("Symlink in model artifact path")
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError("Missing model member")
            digest = hashlib.sha256()
            if target.exists():
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                if sha_file(target) != digest.hexdigest():
                    raise ValueError(f"Extracted model file differs: {relative}")
            else:
                if not download:
                    raise FileNotFoundError(f"Missing extracted model file: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                        output.write(chunk)
            files[relative] = {"sha256": digest.hexdigest(), "bytes": member.size}
    required = {"onnx/model.onnx", "onnx/tokenizer.json", "onnx/config.json"}
    if not required <= files.keys():
        raise ValueError("Official model archive is incomplete")
    return {**spec, "files": files, "cache_directory": str(root)}


def installed_identity(names):
    """Check original wheel RECORD hashes, plus pinned top-level versions."""
    lock = json.loads(LOCK_PATH.read_text())
    result = {}
    for name in names:
        dist = importlib.metadata.distribution(name)
        expected = lock["packages"].get(name, {}).get("version")
        if expected and dist.version != expected:
            raise ValueError(f"Expected {name}=={expected}; found {dist.version}")
        hashes = {}
        for entry in dist.files or ():
            if entry.hash is None or entry.hash.mode != "sha256":
                continue  # generated entrypoints/pyc may have no wheel digest
            path = dist.locate_file(entry)
            actual = sha_file(path)
            encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).decode().rstrip("=")
            if encoded != entry.hash.value:
                raise ValueError(f"Installed upstream file differs from wheel: {name}/{entry}")
            hashes[str(entry)] = actual
        if not hashes:
            raise ValueError(f"No verifiable installed files for {name}")
        result[name] = {"version": dist.version, "verified_files": len(hashes),
                        "files": hashes, "files_sha256": sha_bytes(
                            json.dumps(hashes, sort_keys=True).encode())}
    return result


class PythonComponent:
    """Persistent isolated upstream process. An adapter error stays an error."""

    def __init__(self, backend, documents, state, cache, *, python=sys.executable, timeout=300):
        if backend not in PYTHON_BACKENDS:
            raise ValueError("Unknown Python memory component")
        docs = list(documents)
        self.documents = validate_documents(docs)
        self.state = Path(state).resolve()
        self.state.mkdir(parents=True, exist_ok=False)
        self.timeout = timeout
        self.closed = False
        self.counter = 0
        self.responses = queue.Queue()
        self.stderr_tail = []
        self.stderr_file = (self.state / "stderr.log").open("w", encoding="utf-8")
        started = time.perf_counter_ns()
        self.process = subprocess.Popen(
            [str(python), "-m", "benchmarks.competitors.memory_systems_worker",
             "--backend", backend, "--state", str(self.state), "--cache", str(Path(cache).resolve())],
            cwd=ROOT, env=sanitized_environment(self.state, cache),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.threads = [threading.Thread(target=self._stdout, daemon=True),
                        threading.Thread(target=self._stderr, daemon=True)]
        for thread in self.threads:
            thread.start()
        try:
            self.metadata = self._request({"op": "init", "documents": [
                {key: doc[key] for key in ("id", "project", "title", "text", "created_at")}
                for doc in docs]})
            self.metadata["startup_and_index_roundtrip_ms"] = (time.perf_counter_ns() - started) / 1e6
        except BaseException:
            self.close()
            raise

    def _stdout(self):
        for line in self.process.stdout:
            self.responses.put(line)
        self.responses.put(None)

    def _stderr(self):
        for line in self.process.stderr:
            self.stderr_file.write(line)
            self.stderr_file.flush()
            self.stderr_tail.append(line)
            if len(self.stderr_tail) > 80:
                del self.stderr_tail[:40]

    def _request(self, request):
        if self.closed:
            raise RuntimeError("Component process is closed")
        self.counter += 1
        self.process.stdin.write(json.dumps({"id": self.counter, **request}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        try:
            line = self.responses.get(timeout=self.timeout)
        except queue.Empty as error:
            raise TimeoutError("Upstream component request timed out") from error
        if line is None:
            raise RuntimeError("Upstream worker exited: " + "".join(self.stderr_tail)[-10000:])
        value = json.loads(line)
        if value.get("id") != self.counter:
            raise ValueError("Component response ID mismatch")
        if "error" in value:
            raise RuntimeError(value["error"])
        return value["result"]

    def search(self, query, project, limit=5):
        if not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("Invalid native query or limit")
        started = time.perf_counter_ns()
        result = self._request({"op": "search", "query": query, "project": project, "limit": limit})
        result["bridge_ms"] = (time.perf_counter_ns() - started) / 1e6
        validate_response(result, self.documents, project, limit)
        return result

    def close(self):
        if getattr(self, "closed", True):
            return
        self.closed = True
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for thread in self.threads:
            thread.join(timeout=5)
        for stream in (self.process.stdout, self.process.stderr):
            if stream:
                stream.close()
        self.stderr_file.close()
        if self.process.returncode:
            raise RuntimeError("Component exited unsuccessfully: " + "".join(self.stderr_tail)[-10000:])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
