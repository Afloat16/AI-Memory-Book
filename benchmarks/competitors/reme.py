"""Pinned ReMe native file/BM25 component; no locally implemented ranker.

Source preparation may download the official archive. Indexing and queries run
in a separate, network-blocked Python process with an independent dependency lock.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import queue
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

from .memory_systems import (
    PythonComponent, sanitized_environment, sha_bytes, sha_file,
    validate_documents, validate_response,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK_PATH = HERE / "reme-lock.json"
REQUIREMENTS_PATH = HERE / "reme-requirements.txt"


def load_lock():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if sha_file(REQUIREMENTS_PATH) != lock["dependencies"]["requirements_sha256"]:
        raise ValueError("ReMe dependency lock and requirements bytes differ")
    return lock


def git_blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def source_identity(source, spec=None):
    """Authenticate every runtime file against the pinned upstream Git tree."""
    source = Path(source).resolve()
    spec = spec or load_lock()["source"]
    hashes = {}
    for relative, expected in spec["files"].items():
        path = source / relative
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("Symlink in ReMe source tree")
        data = path.read_bytes()
        if len(data) != expected["bytes"] or git_blob_sha1(data) != expected["git_blob_sha1"]:
            raise ValueError(f"Pinned upstream source changed: {relative}")
        hashes[relative] = sha_bytes(data)
    actual = {p.relative_to(source).as_posix() for p in (source / "reme").rglob("*")
              if p.is_file() or p.is_symlink()}
    expected_runtime = {p for p in spec["files"] if p.startswith("reme/")}
    if actual != expected_runtime:
        raise ValueError("Unexpected or missing file in pinned ReMe runtime")
    return {"repository": spec["repository"], "commit": spec["commit"],
            "declared_source_version": spec["declared_source_version"],
            "release_status": spec["release_status"], "verified_files": len(hashes),
            "files_sha256": sha_bytes(json.dumps(hashes, sort_keys=True).encode()),
            "files": hashes, "source_directory": str(source)}


def materialize_source(cache_dir, *, offline=False):
    """Read only verified regular runtime files from the official archive."""
    spec = load_lock()["source"]
    root = Path(cache_dir).resolve() / "reme" / spec["commit"]
    source = root / "source"
    if source.exists():
        source_identity(source, spec)
        return source
    archive = root / "upstream.tar.gz"
    root.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        if offline:
            raise FileNotFoundError("Missing ReMe source; run --prepare before offline execution")
        partial = root / "upstream.tar.gz.partial"
        request = urllib.request.Request(spec["archive_url"],
                                        headers={"User-Agent": "AI-Memory-Book-benchmark/1"})
        try:
            count = 0
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("xb") as out:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    count += len(chunk)
                    if count > spec["archive_bytes"]:
                        raise ValueError("ReMe archive exceeded its recorded size")
                    out.write(chunk)
            if count != spec["archive_bytes"] or sha_file(partial) != spec["archive_sha256"]:
                raise ValueError("ReMe official archive identity mismatch")
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    if archive.stat().st_size != spec["archive_bytes"] or sha_file(archive) != spec["archive_sha256"]:
        raise ValueError("Cached ReMe archive identity mismatch")
    staging = Path(tempfile.mkdtemp(prefix="source-", dir=root))
    try:
        found = set()
        with tarfile.open(archive, "r:gz") as package:
            for member in package:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or not name.parts:
                    raise ValueError("Unsafe path in ReMe source archive")
                relative = PurePosixPath(*name.parts[1:]).as_posix()
                expected = spec["files"].get(relative)
                if expected is None:
                    continue
                if not member.isfile() or member.issym() or member.islnk() or relative in found:
                    raise ValueError("Unexpected source archive entry")
                if member.size != expected["bytes"]:
                    raise ValueError("Upstream source member size changed")
                stream = package.extractfile(member)
                if stream is None:
                    raise ValueError("Missing upstream source member")
                data = stream.read()
                if git_blob_sha1(data) != expected["git_blob_sha1"]:
                    raise ValueError("Upstream archive does not match pinned Git tree")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                found.add(relative)
        if found != set(spec["files"]):
            raise ValueError("Incomplete ReMe source archive")
        source_identity(staging, spec)
        staging.rename(source)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return source


def dependency_identity():
    """Check independently locked versions and installed wheel RECORD hashes."""
    lock = load_lock()
    result = {}
    for name, expected in lock["dependencies"]["packages"].items():
        dist = importlib.metadata.distribution(name)
        if dist.version != expected["version"]:
            raise ValueError(f"ReMe requires {name}=={expected['version']}; found {dist.version}")
        files = {}
        for entry in dist.files or ():
            if entry.hash is None or entry.hash.mode != "sha256":
                continue
            actual = sha_file(dist.locate_file(entry))
            encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).decode().rstrip("=")
            if encoded != entry.hash.value:
                raise ValueError(f"Installed ReMe dependency differs from wheel: {name}/{entry}")
            files[str(entry)] = actual
        if not files:
            raise ValueError(f"No verifiable installed files for {name}")
        result[name] = {"version": dist.version, "verified_files": len(files),
                        "files_sha256": sha_bytes(json.dumps(files, sort_keys=True).encode())}
    return {"requirements_sha256": lock["dependencies"]["requirements_sha256"],
            "package_count": len(result), "packages": result,
            "identity_sha256": sha_bytes(json.dumps(result, sort_keys=True).encode())}


def environment(state, cache_dir):
    env = sanitized_environment(state, cache_dir)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def prepare(cache_dir, *, python=sys.executable, offline=False):
    """Download/verify source, then verify the separate installed environment."""
    source = materialize_source(cache_dir, offline=offline)
    state = source.parent / "verification"
    state.mkdir(exist_ok=True)
    result = subprocess.run(
        [str(python), "-m", "benchmarks.competitors.reme_worker", "--identity",
         "--source", str(source)], cwd=ROOT, env=environment(state, cache_dir),
        check=False, text=True, encoding="utf-8", capture_output=True, timeout=300,
    )
    if result.returncode:
        raise RuntimeError("ReMe environment verification failed:\n" + result.stderr[-12000:])
    value = json.loads(result.stdout)
    if value["source"]["commit"] != load_lock()["source"]["commit"]:
        raise ValueError("Worker reported an unexpected ReMe source identity")
    return value


class ReMeComponent(PythonComponent):
    """Use the existing strict JSON transport with the ReMe-only worker."""

    def __init__(self, documents, cache_dir, state_dir, *, python=sys.executable,
                 offline=True, timeout=300):
        docs = list(documents)
        self.documents = validate_documents(docs)
        source = materialize_source(cache_dir, offline=offline)
        self.state = Path(state_dir).resolve()
        self.state.mkdir(parents=True, exist_ok=False)
        self.timeout = timeout
        self.closed = False
        self.counter = 0
        self.responses = queue.Queue()
        self.stderr_tail = []
        self.stderr_file = (self.state / "stderr.log").open("w", encoding="utf-8")
        started = time.perf_counter_ns()
        self.threads = []
        try:
            self.process = subprocess.Popen(
                [str(python), "-m", "benchmarks.competitors.reme_worker",
                 "--source", str(source), "--state", str(self.state)],
                cwd=ROOT, env=environment(self.state, cache_dir),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1,
            )
        except BaseException:
            self.closed = True
            self.stderr_file.close()
            raise
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

    def search(self, query, project, limit=5):
        if not isinstance(project, str) or not project:
            raise ValueError("This ranked component protocol requires an explicit project ID")
        result = super().search(query, project, limit)
        validate_response(result, self.documents, project, limit)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.cache, python=args.python, offline=args.offline),
                     ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
