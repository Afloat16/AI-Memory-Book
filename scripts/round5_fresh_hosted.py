"""Single-use hosted orchestration for the prospectively frozen fresh v2 protocols.

Import and --preflight decode no fresh metadata/content and run no engine.
--run requires a separately committed final-source authorization and certificate.
The original workers own their random launch tickets, schedules and measurements.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import sqlite3
import subprocess
import sys
import tarfile
import traceback
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "round5-fresh-hosted-1"
TRIGGER = "refs/heads/ci/v033-fresh-hosted-1"
RESULT_REF = "refs/heads/validation/v033-fresh-hosted-1"
SCOPE = "benchmarks/experiments/round5-fresh-hosted-scope.json"
AUTH = "benchmarks/experiments/round5-fresh-source-authorization.json"
CERTIFICATE = "benchmarks/experiments/round5-final-interface-certificate.json"
PUBLIC = "benchmarks/reports/" + ATTEMPT
PRIVATE = ".artifacts/" + ATTEMPT
NATIVE = "scripts/round5_title_reference_fresh_v2.py"
COMPONENT = "scripts/round5_title_reference_fresh_components_v2.py"
BASELINE = {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
            "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"}
CERT_PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}
WORKERS = ("export", "final-default-component", "final-follow-titles-component",
           "claude-mem-fts", "billion-context", "ai-memory-hybrid")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def raw(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "Duplicate JSON key: " + key)
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)


def safe_name(name):
    require(type(name) is str and name and "\\" not in name and "\0" not in name,
            "Invalid relative file name")
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name
            and not any(part in {"", ".", "..", ".git"} for part in path.parts),
            "Unsafe repository path: " + name)
    return name


def local(root, name):
    path = root / safe_name(name)
    require(not any(item.is_symlink() for item in (path, *path.parents)
                    if item != root.parent and root in (item, *item.parents)),
            "Symlink in artifact or frozen path: " + name)
    require(path.resolve().is_relative_to(root.resolve()), "Path escapes repository")
    return path


def save(path, value, *, exclusive=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("xb") as stream:
            stream.write(raw(value))
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name(path.name + ".partial")
        with temporary.open("wb") as stream:
            stream.write(raw(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE, timeout=120)


def hex_string(value, size):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def committed(root, name):
    path = local(root, name)
    require(path.is_file() and path.read_bytes() == git(root, "show", "HEAD:" + name),
            "Commit exact frozen file before use: " + name)


def tracked(root):
    return [name.decode() for name in git(root, "ls-files", "-z").split(b"\0") if name]


def inventory_names(names, scope, certificate, evidence):
    result = set(scope["files"].values()) | {CERTIFICATE, evidence}
    result.update(certificate["generator_files"])
    for name in names:
        path = PurePosixPath(safe_name(name))
        if (path.suffix == ".py" and path.parts[0] in {"scripts", "benchmarks", "tests"}
                or name.startswith("benchmarks/competitors/") and path.suffix in {".mjs", ".ts", ".json"}
                or path.suffix == ".json" and (path.parent.as_posix() == "benchmarks"
                                             or name.startswith("benchmarks/experiments/"))):
            result.add(name)
    result.discard(AUTH)  # The claim separately freezes authorization bytes; no self-hash.
    return sorted(result)


def verify_manifest(root, manifest):
    require(type(manifest) is dict and manifest, "Empty frozen file manifest")
    for name, expected in manifest.items():
        path = local(root, name)
        require(hex_string(expected, 64) and path.is_file() and sha(path) == expected,
                "Frozen file changed or missing: " + name)


def validate_documents(root, scope, authorization, certificate, names):
    """Standard-library envelope/inventory checks; no evaluator imports or downloads."""
    required = set(scope["authorization"]["required_fields"])
    require(set(authorization) == required and type(authorization["schema_version"]) is int
            and authorization["schema_version"] == 1 and authorization["protocol"] == ATTEMPT
            and authorization["attempt"] == ATTEMPT
            and authorization["status"] == "approved-for-first-fresh-attempt"
            and type(authorization["fresh_rows_decoded_before_authorization"]) is int
            and authorization["fresh_rows_decoded_before_authorization"] == 0,
            "Missing explicit, prospective final-source authorization")
    sources = authorization["sources"]
    require(type(sources) is dict and set(sources) == {"baseline", "candidate"}
            and sources["baseline"] == BASELINE and sources["candidate"] != BASELINE,
            "Exact published baseline and selected final candidate required")
    for item in sources.values():
        require(type(item) is dict and set(item) == {"commit", "runtime_sha256"}
                and hex_string(item["commit"], 40) and hex_string(item["runtime_sha256"], 64),
                "Invalid exact source identity")
    manifests = authorization["source_files_sha256"]
    require(type(manifests) is dict and set(manifests) == set(sources),
            "Complete source manifests required")
    for manifest in manifests.values():
        require(type(manifest) is dict and "src/memory_book/__init__.py" in manifest,
                "Incomplete source file manifest")
        for name, expected in manifest.items():
            require(safe_name(name).startswith("src/") and hex_string(expected, 64),
                    "Invalid source file manifest entry")
    excluded = authorization["additional_exclusions"]
    require(type(excluded) is list and all(type(item) is str and item for item in excluded)
            and len(excluded) == len(set(excluded)), "Explicit unique additional exclusions required")
    evidence = authorization["selection_evidence"]
    require(type(evidence) is dict and set(evidence) == {"path", "sha256"}
            and hex_string(evidence["sha256"], 64), "Missing source selection evidence binding")
    evidence_path = local(root, evidence["path"])
    require(evidence_path.is_file() and sha(evidence_path) == evidence["sha256"],
            "Committed source-selection evidence missing or changed")
    cert_binding = authorization["interface_certificate"]
    require(cert_binding == {"path": CERTIFICATE, "sha256": sha(root / CERTIFICATE)},
            "Exact final interface certificate binding required")
    require(type(certificate.get("schema_version")) is int and certificate["schema_version"] == 1
            and certificate.get("evaluator") == "round5-final-interface-certificate-1"
            and certificate.get("status") == "verified-before-formal-measurement-and-fresh-selection"
            and certificate.get("sources") == sources
            and type(certificate.get("retrieval_calls_executed")) is int
            and certificate["retrieval_calls_executed"] == 0
            and certificate.get("packages") == CERT_PACKAGES
            and certificate.get("server_packages") == {label: CERT_PACKAGES for label in sources}
            and hex_string(certificate.get("generator_commit"), 40)
            and type(certificate.get("generator_files")) is dict and certificate["generator_files"]
            and set(certificate.get("observations", {})) == set(sources),
            "Invalid or incomplete source-bound interface certificate")
    require((root / CERTIFICATE).read_bytes() == raw(certificate),
            "Certificate canonical generated bytes changed")
    files = authorization["frozen_files_sha256"]
    require(type(files) is dict
            and sorted(files) == inventory_names(names, scope, certificate, evidence["path"]),
            "Independent controller/evaluator inventory incomplete or expanded")
    verify_manifest(root, files)
    verify_manifest(root, certificate["generator_files"])
    verify_manifest(root, scope["protocols"]["preserved_original_files_sha256"])
    for name in sorted(set(files) | {AUTH}):
        committed(root, name)
    return authorization


def preflight(root=ROOT):
    # Keep this before imports, filesystem claims, Git fetch, pip/asset download or any selector.
    root = Path(root).resolve()
    for name in (SCOPE, AUTH, CERTIFICATE):
        require(local(root, name).is_file(), "Required prospective authorization/certificate missing: " + name)
    scope, authorization, certificate = (read(root / name) for name in (SCOPE, AUTH, CERTIFICATE))
    require(scope["protocol"] == ATTEMPT
            and scope["attempt"] == {"id": ATTEMPT, "trigger_ref": TRIGGER, "result_ref": RESULT_REF,
                "public": PUBLIC, "private": PRIVATE, "run_attempt": 1,
                "host": "One Linux x86_64 hosted VM/boot, Python3.12; every measurement process executes sequentially on that same host. No parallel measurement or automatic replay."},
            "Hosted attempt registration changed")
    validate_documents(root, scope, authorization, certificate, tracked(root))
    return {"scope": scope, "authorization": authorization, "certificate": certificate,
            "authorization_sha256": sha(root / AUTH)}


class PublicationError(RuntimeError):
    pass


class Publisher:
    """Expected-remote comparison, one ordinary push, binary-preserving readback."""

    def __init__(self, root, public, state, result_ref=RESULT_REF):
        self.root, self.public, self.state = Path(root), Path(public), Path(state)
        self.result_ref = result_ref

    def remote(self):
        fields = git(self.root, "ls-remote", "--heads", "origin", self.result_ref).decode().split()
        if not fields:
            return None
        if len(fields) != 2 or fields[1] != self.result_ref or not hex_string(fields[0], 40):
            raise PublicationError("Unexpected result-ref response")
        return fields[0]

    def head(self):
        return git(self.root, "rev-parse", "HEAD").decode().strip()

    def expected(self):
        return read(self.state / "publication.json")["expected_remote"]

    def files(self):
        result = []
        for path in sorted(self.public.rglob("*")):
            if path.is_symlink():
                raise PublicationError("Symlink in public evidence")
            if not path.is_file():
                continue
            # Raw ledgers are uploaded and retained locally; Git uses original lossless gzip bytes.
            if path.name.endswith(".attempts.jsonl"):
                continue
            if path.suffix not in {".json", ".gz", ".log"} or "tickets" in path.parts:
                raise PublicationError("Unexpected public artifact: " + str(path))
            result.append(path.relative_to(self.root).as_posix())
        return result

    def publish(self, message):
        failure = self.public / "publication-failure.json"
        if failure.exists():
            raise PublicationError("Ambiguous publication: no write/measurement retry")
        expected, parent = self.expected(), self.head()
        try:
            if self.remote() != expected or (expected is not None and parent != expected):
                raise PublicationError("Result ref advanced or local ancestry changed")
            if git(self.root, "diff", "--cached", "--name-only").strip():
                raise PublicationError("Unrelated staged changes")
            names = self.files()
            require(names, "Empty checkpoint")
            # Path arguments preserve bytes. Never decode compressed reports to text.
            git(self.root, "add", "--sparse", "--", *names)
            changed = git(self.root, "diff", "--cached", "--name-only", "-z").split(b"\0")
            changed = [name.decode() for name in changed if name]
            if not changed or any(name not in names for name in changed):
                raise PublicationError("Empty or unrelated staged checkpoint")
            git(self.root, "commit", "-m", message + " [skip ci]")
            head = self.head()
            pushed = subprocess.run(["git", "push", "origin", "HEAD:" + self.result_ref],
                                    cwd=self.root, capture_output=True, timeout=120)
            observed = self.remote()
            if pushed.returncode or observed != head:
                raise PublicationError("Push failed or remote readback differed; rc="
                    + str(pushed.returncode) + "; stderr=" + pushed.stderr.decode(errors="replace"))
            for name in names:
                if git(self.root, "show", head + ":" + name) != (self.root / name).read_bytes():
                    raise PublicationError("Published raw Git blob differs: " + name)
            save(self.state / "publication.json", {"expected_remote": head}, exclusive=False)
            print(json.dumps({"checkpoint": head, "result_ref": self.result_ref, "stage": message}), flush=True)
            return head
        except BaseException as error:
            if not failure.exists():
                save(failure, {"at": now(), "previous_remote": expected, "local_parent": parent,
                    "error_type": type(error).__name__, "error": str(error),
                    "rule": "No automatic retry. Preserve local files and inspect remote evidence."})
            raise


def host_identity():
    return {"boot_sha256": sha(Path("/proc/sys/kernel/random/boot_id")),
            "machine_sha256": hashlib.sha256(platform.node().encode()).hexdigest(),
            "python": platform.python_version(), "python_executable": sys.executable,
            "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
            "cpu_count": os.cpu_count(),
            "packages": {name: importlib.metadata.version(name)
                         for name in ("mcp", "pydantic", "tiktoken", "pyarrow", "regex")}}


def source_manifest(directory):
    entries = list((directory / "src").rglob("*"))
    require(not any(path.is_symlink() for path in entries), "Source contains symlinks")
    return {path.relative_to(directory).as_posix(): sha(path)
            for path in sorted(entries) if path.is_file()}


def verify_source(directory, identity, expected):
    require(git(directory, "rev-parse", "HEAD").decode().strip() == identity["commit"],
            "Source checkout revision changed")
    entries = git(directory, "ls-tree", "-r", "-z", identity["commit"], "--", "src").split(b"\0")
    paths = []
    for entry in entries:
        if not entry:
            continue
        spec, name = entry.split(b"\t", 1)
        require(spec.split()[0] in {b"100644", b"100755"}, "Non-regular tracked source")
        paths.append(name.decode())
    require(sorted(paths) == sorted(expected) and source_manifest(directory) == expected,
            "Source file inventory or bytes changed")
    for name in paths:
        require(hashlib.sha256(git(directory, "show", identity["commit"] + ":" + name)).hexdigest()
                == expected[name], "Source manifest is not the committed source")
    result = hashlib.sha256()
    package = directory / "src/memory_book"
    for path in sorted(package.rglob("*.py")):
        result.update(path.relative_to(package).as_posix().encode())
        result.update(b"\0")
        result.update(path.read_bytes())
        result.update(b"\0")
    require(result.hexdigest() == identity["runtime_sha256"], "Runtime source hash changed")


def fetch_commit(root, commit):
    require(hex_string(commit, 40), "Only immutable explicit commit fetches")
    present = subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"],
                             cwd=root, capture_output=True, timeout=30)
    if present.returncode:
        git(root, "fetch", "--no-tags", "--depth=1", "--filter=blob:none", "origin", commit)


def prepare_sources(root, state, frozen):
    auth = frozen["authorization"]
    # Fetch only original provenance objects required by unchanged byte guards.
    native_scope = read(root / frozen["scope"]["protocols"]["native_scope"])
    commits = [native_scope["original_plan"]["commit"], frozen["certificate"]["generator_commit"]]
    commits.extend(item["commit"] for item in auth["sources"].values())
    for commit in dict.fromkeys(commits):
        fetch_commit(root, commit)
    git(root, "config", "extensions.worktreeConfig", "true")
    for label, identity in auth["sources"].items():
        directory = state / "sources" / label
        require(not directory.exists(), "Never recreate a source checkout")
        directory.parent.mkdir(parents=True, exist_ok=True)
        git(root, "worktree", "add", "--detach", "--no-checkout", str(directory), identity["commit"])
        git(directory, "sparse-checkout", "init", "--no-cone")
        git(directory, "sparse-checkout", "set", "--no-cone", "/src/")
        git(directory, "checkout", "--detach", identity["commit"])
        verify_source(directory, identity, auth["source_files_sha256"][label])
        # Runtime paths are read-only; database writes belong to original worker state.
        for path in (directory / "src").rglob("*"):
            if path.is_file():
                path.chmod(0o444)


def download_once(url, path, expected=None, size=None):
    """Exactly one HTTP acquisition. A failed partial file blocks every replay."""
    require(url.startswith("https://") and not path.exists(), "Fresh HTTPS asset destination required")
    partial = path.with_name(path.name + ".partial")
    require(not partial.exists(), "Preserve partial download; never retry")
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Memory-Book-frozen-benchmark"})
    with partial.open("xb") as output, urllib.request.urlopen(request, timeout=180) as response:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    require((expected is None or sha(partial) == expected)
            and (size is None or partial.stat().st_size == size), "Pinned asset verification failed: " + path.name)
    partial.rename(path)
    return path


def write_asset(path, content, expected=None, size=None, executable=False):
    require(expected is None or hashlib.sha256(content).hexdigest() == expected,
            "Extracted asset checksum differs")
    require(size is None or len(content) == size, "Extracted asset size differs")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
    if executable:
        path.chmod(0o755)
    return path


def tar_member(archive, name):
    with tarfile.open(archive, "r:*") as source:
        members = [member for member in source.getmembers() if member.name == name and member.isfile()]
        require(len(members) == 1, "Expected exactly one regular pinned archive member")
        stream = source.extractfile(members[0])
        require(stream is not None, "Missing pinned member bytes")
        return stream.read()


def node_checksum(raw_manifest, name):
    entries = []
    for line in raw_manifest.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == name:
            entries.append(fields[0])
    require(len(entries) == 1 and hex_string(entries[0], 64), "Exact Node release checksum missing or ambiguous")
    return entries[0]


def prepare_assets(root, state, scope):
    """Only verified downloads/extraction; original workers initialize every engine."""
    sys.path.insert(0, str(root))
    from benchmarks.competitors.claude_mem import source_members, directory_fingerprint
    from benchmarks.competitors.billion import _verify
    cache = state / "assets"
    require(not cache.exists(), "Never reuse a prepared asset directory")
    cache.mkdir(parents=True)
    node = scope["assets"]["node"]
    manifest = download_once(node["checksums_url"], cache / "node/SHASUMS256.txt")
    expected = node_checksum(manifest.read_bytes(), node["archive_name"])
    archive = download_once(node["archive_url"], cache / "node" / node["archive_name"], expected)
    binary = write_asset(cache / "node/bin/node", tar_member(archive, node["binary_member"]), executable=True)
    version = subprocess.check_output([str(binary), "--version"], timeout=20, text=True).strip()
    require(version == node["version"], "Exact Node version required")
    cm = read(root / "benchmarks/competitors/claude-mem-round2-lock.json")
    cmroot = cache / "claude-mem"
    cm_archives = []
    for spec in (cm["source_archive"], cm["runtime"]):
        cm_archives.append(download_once(spec["url"], cmroot / spec["name"], spec["sha256"], spec["bytes"]))
    members = source_members(cm_archives[0])
    for name, content in members.items():
        write_asset(local(cmroot / "verified-source", name), content)
    directory_fingerprint(cmroot / "verified-source", members)
    runtime = cm["runtime"]
    with zipfile.ZipFile(cm_archives[1]) as package:
        require(package.namelist().count(runtime["member"]) == 1, "Duplicate Bun archive member")
        content = package.read(runtime["member"])
    write_asset(cmroot / "bun", content, runtime["binary_sha256"], runtime["binary_bytes"], True)
    billion = read(root / "benchmarks/competitors/billion-round2-lock.json")
    for entry in billion["files"]:
        url = "https://raw.githubusercontent.com/" + billion["repository"] + "/" + billion["commit"] + "/" + entry["path"]
        path = download_once(url, local(cache / "billion-context", entry["path"]), entry["sha256"], entry["bytes"])
        _verify(path.read_bytes(), entry)  # Pure length/SHA256/Git-blob validation; no compile or adapter.
    ai = read(root / "benchmarks/competitors/ai-memory-lock.json")
    airoot = cache / "ai-memory"
    archive = download_once(ai["asset_url"], airoot / ("ai-memory-linux-x86_64-" + ai["version"] + ".tar.gz"),
                            ai["archive_sha256"], ai["archive_bytes"])
    write_asset(airoot / ("ai-memory-" + ai["version"]), tar_member(archive, "ai-memory"),
                ai["binary_sha256"], executable=True)
    write_asset(airoot / ("ai-memory-" + ai["version"] + "-LICENSE"), tar_member(archive, "LICENSE"))
    for entry in ai["embedding_model"]["files"]:
        download_once(ai["embedding_model"]["base_url"] + "/" + entry["name"],
            local(airoot / "models" / ai["embedding_model"]["name"], entry["name"]), entry["sha256"], entry["bytes"])
    upstream = read(root / "benchmarks/hotpot_manifest.json")
    parquet = download_once(upstream["source_url"], state / "upstream.parquet",
                            upstream["upstream_sha256"], upstream["upstream_bytes"])
    files = {path.relative_to(root).as_posix(): sha(path)
             for path in sorted(cache.rglob("*")) if path.is_file()}
    files[parquet.relative_to(root).as_posix()] = sha(parquet)
    return {"files_sha256": files, "node_version": version, "node_checksum": expected,
            "fresh_rows_decoded": 0, "retrieval_calls_executed": 0, "engines_initialized": 0}


def schedule():
    result = [("prepare-assets", "prepare", None), ("register-components", "register", None),
              ("bind-native", "bind", None), ("select-metadata", "select", None),
              ("bind-selected-data", "prepare-data", None)]
    for index in range(5):
        result.extend([("native-%02d-intent" % index, "native-intent", index),
                       ("native-%02d-worker" % index, "native-worker", index)])
    for index in range(6):
        result.extend([("component-%02d-intent" % index, "component-intent", index),
                       ("component-%02d-worker" % index, "component-worker", index)])
    return [*result, ("audit-components", "component-audit", None), ("audit-native-gate", "native-audit", None)]


def command(root, state, public, action, index, published):
    native, component = [sys.executable, str(root / NATIVE)], [sys.executable, str(root / COMPONENT)]
    binding, selection = public / "native-binding.json", public / "selection.json"
    common = ["--binding", str(binding), "--published-commit", published]
    source = lambda label: str(state / "sources" / label / "src")
    parquet = ["--parquet", str(state / "upstream.parquet")]
    if action == "register":
        return component + ["--register", str(public / "comparators.json"), "--source", source("candidate"),
            "--selection", str(selection), "--state", str(state / "component-state"),
            "--output", str(public / "components"), "--cache", str(state / "assets"),
            "--node", str(state / "assets/node/bin/node")]
    if action == "bind":
        return native + ["--bind", str(binding), "--baseline-src", source("baseline"),
            "--candidate-src", source("candidate"), *parquet, "--selection", str(selection),
            "--data-binding", str(public / "data-binding.json"), "--state", str(state / "native-state"),
            "--output", str(public / "native"), "--comparators", str(public / "comparators.json"),
            "--additional-exclusions", str(public / "additional-exclusions.json"), "--publication-ref", RESULT_REF]
    if action in {"select", "prepare-data"}:
        return native + ["--" + action, *common, *parquet]
    if action in {"native-intent", "component-intent"}:
        return (native if action.startswith("native") else component) + ["--intent", str(index), *common]
    if action in {"native-worker", "component-worker"}:
        own = action.startswith("native")
        result = (native if own else component) + ["--worker", str(index), *common, *parquet]
        if own or index <= 2:
            result += ["--source", source("baseline" if index == 0 else "candidate")]
        return result
    if action in {"component-audit", "native-audit"}:
        return (native if action.startswith("native") else component) + ["--audit", "--write-summary", *common]
    raise ValueError("Unknown frozen stage action")


def execute(argv, log, timeout=10800):
    """Stop the complete subprocess group on timeout/cancellation; never retry."""
    process = None
    with log.open("xb") as stream:
        try:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
            return process.wait(timeout=timeout)
        finally:
            if process is not None:
                # Even a crashed worker can leave Bun/Rust grandchildren alive.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    # A dead parent may leave live grandchildren in the session.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=10)
                stream.flush()
                os.fsync(stream.fileno())


def preserve_ledgers(public):
    for ledger in sorted(public.rglob("*.attempts.jsonl")):
        body = ledger.read_bytes()
        archive = ledger.with_name(ledger.name + ".gz")
        if archive.exists():
            try:
                if gzip.decompress(archive.read_bytes()) == body:
                    continue
            except (OSError, EOFError):
                pass  # Preserve a corrupt original archive as failure evidence too.
            # Never overwrite the original worker archive after interruption.
            archive = ledger.with_name(ledger.name + ".interrupted.gz")
        if not archive.exists():
            with archive.open("xb") as stream:
                stream.write(gzip.compress(body, mtime=0))


class Controller:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.public, self.state = self.root / PUBLIC, self.root / PRIVATE
        self.publisher = Publisher(self.root, self.public, self.state)
        self.frozen = None
        self.claim = None

    def guard(self):
        require(not (self.state / "stopped.json").exists(), "Attempt stopped; never resume")
        require(not (self.public / "publication-failure.json").exists(), "Publication failed; no further stage")
        verify_manifest(self.root, self.claim["frozen_files_sha256"])
        require(sha(self.root / AUTH) == self.claim["authorization_sha256"]
                and host_identity() == self.claim["host"], "Authorization or host/boot changed")
        for label, identity in self.claim["sources"].items():
            directory = self.state / "sources" / label
            if directory.exists():
                verify_source(directory, identity, self.claim["source_files_sha256"][label])
        prepared = self.public / "prepared-assets.json"
        if prepared.exists():
            verify_manifest(self.root, read(prepared)["files_sha256"])

    def start(self):
        self.frozen = preflight(self.root)
        require(os.environ.get("GITHUB_REF") == TRIGGER
                and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                and platform.system() == "Linux" and platform.machine() == "x86_64"
                and sys.version_info[:2] == (3, 12), "Use the registered first hosted Linux/Python3.12 attempt")
        require(not self.state.exists() and not self.public.exists() and self.publisher.remote() is None,
                "Existing attempt/ref/state: preserve it; never replay")
        environment = host_identity()
        require({name: environment["packages"][name] for name in CERT_PACKAGES} == CERT_PACKAGES
                and environment["packages"]["pyarrow"] == "26.0.1"
                and environment["packages"]["regex"] == "2026.11.9", "Pinned hosted dependencies differ")
        self.state.mkdir(parents=True, exist_ok=False)
        self.public.mkdir(parents=True, exist_ok=False)
        save(self.state / "publication.json", {"expected_remote": None})
        authorization = self.frozen["authorization"]
        self.claim = {"protocol": ATTEMPT, "status": "claimed-before-download-and-metadata",
            "created_at": now(), "driver_commit": self.publisher.head(),
            "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": 1,
            "authorization_sha256": self.frozen["authorization_sha256"],
            "frozen_files_sha256": authorization["frozen_files_sha256"],
            "sources": authorization["sources"], "source_files_sha256": authorization["source_files_sha256"],
            "source_selection_evidence": authorization["selection_evidence"],
            "host": environment, "stage_schedule": schedule(),
            "fresh_rows_decoded": 0, "retrieval_calls_executed": 0}
        save(self.public / "claim.json", self.claim)
        save(self.public / "additional-exclusions.json", authorization["additional_exclusions"])
        self.publisher.publish("Claim single-use fresh hosted attempt")
        save(self.state / "progress.json", {"next_stage": 0})

    def stage(self, ordinal, spec):
        name, action, index = spec
        require(read(self.state / "progress.json")["next_stage"] == ordinal, "Only exact next stage may run")
        intent, exit_path = self.public / (name + ".stage-intent.json"), self.public / (name + ".exit.json")
        log = self.public / (name + ".log")
        require(not any(path.exists() for path in (intent, exit_path, log)), "Started stage must never replay")
        self.guard()
        save(intent, {"at": now(), "ordinal": ordinal, "name": name, "action": action, "worker": index,
                      "prior_publication_commit": self.publisher.expected(),
                      "rule": "Exclusive stage; a partial or nonzero outcome is retained and never replayed."})
        self.publisher.publish("Authorize fresh stage " + name)
        argv, returncode, error = None, None, None
        try:
            self.guard()
            if action == "prepare":
                # No selected-data module is imported here; pure locked asset readers only.
                prepare_sources(self.root, self.state, self.frozen)
                pins = prepare_assets(self.root, self.state, self.frozen["scope"])
                save(self.public / "prepared-assets.json", pins)
                with log.open("xb") as stream:
                    stream.write(b"Exact source worktrees and asset bytes prepared; no fresh row decode or engine initialization.\n")
                returncode = 0
            else:
                argv = command(self.root, self.state, self.public, action, index, self.publisher.expected())
                returncode = execute(argv, log)
            require(returncode == 0, "Original stage returned " + str(returncode) + ": " + name)
            self.guard()
        except BaseException as caught:
            error = {"type": type(caught).__name__, "message": str(caught), "traceback": traceback.format_exc()}
            if isinstance(caught, subprocess.CalledProcessError):
                error.update(stdout=(caught.output or b"").decode(errors="replace"),
                             stderr=(caught.stderr or b"").decode(errors="replace"))
            save(self.state / "stopped.json", {"stage": name, "at": now(), "error": error})
            raise
        finally:
            preserve_ledgers(self.public)
            save(exit_path, {"at": now(), "ordinal": ordinal, "name": name,
                "status": "failed_or_interrupted" if error else "completed",
                "argv": argv, "returncode": returncode, "error": error,
                "log_sha256": sha(log) if log.exists() else None})
        self.publisher.publish("Preserve completed fresh stage " + name)
        save(self.state / "progress.json", {"next_stage": ordinal + 1}, exclusive=False)

    def run(self):
        self.start()
        for ordinal, spec in enumerate(schedule()):
            self.stage(ordinal, spec)
        self.guard()
        save(self.public / "completion.json", {"at": now(), "status": "completed-native-gate-passed",
            "stages": len(schedule()), "native_calls": 15360, "component_search_calls": 7680,
            "component_quality_rows": 15360, "claim_sha256": sha(self.public / "claim.json"),
            "native_summary_sha256": sha(self.public / "native/summary.json.gz"),
            "component_summary_sha256": sha(self.public / "components/summary.json.gz"),
            "claim_boundary": "Saved original gates only; no universal competitor superiority or release claim."})
        self.publisher.publish("Preserve complete frozen fresh comparison")

    def preserve(self, error=None):
        if not (self.state / "publication.json").exists():
            return  # Preflight failed: no claim, downloads, result ref or private state.
        if (self.public / "completion.json").exists() and not error:
            return
        marker = self.state / "preservation-started.json"
        if marker.exists():
            return
        save(marker, {"at": now()})
        preserve_ledgers(self.public)
        failure = self.public / "failure.json"
        if not failure.exists():
            save(failure, {"at": now(), "status": "failed_or_interrupted",
                "error": str(error) if error else "Hosted workflow ended without completion",
                "error_type": type(error).__name__ if error else None,
                "traceback": traceback.format_exc() if error else None,
                "progress": read(self.state / "progress.json") if (self.state / "progress.json").exists() else None,
                "rule": "No retry, reselection, export replay, ticket replacement or source change."})
        if not (self.public / "publication-failure.json").exists():
            self.publisher.publish("Preserve failed fresh attempt; no replay")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--preserve", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        frozen = preflight()
        print(json.dumps({"verified": True, "authorization_sha256": frozen["authorization_sha256"],
                          "claim_created": False, "downloads": 0, "fresh_rows_decoded": 0}))
        return 0
    controller = Controller()
    if args.preserve:
        controller.preserve()
        return 0

    def interrupted(signum, _frame):
        raise KeyboardInterrupt("Hosted process interrupted by signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    try:
        controller.run()
    except BaseException as error:
        controller.preserve(error)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
