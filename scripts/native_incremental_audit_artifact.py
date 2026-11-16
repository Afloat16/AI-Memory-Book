"""Independently audit a completed native incremental Actions artifact in RAM.

This does not execute the application, remeasure a query, install dependencies,
or extract the large ZIP. Metadata is an unmodified API response wrapper with
``artifact`` and ``run`` objects, optionally an ``evidence`` commit/tree object.
Supply the temporary signed download URL on stdin (one line) or through a named
environment variable. The URL is never retained in reports or error messages.

Example (the process waits for its URL on stdin)::

    python scripts/native_incremental_audit_artifact.py --metadata metadata.json \
        --artifact-id ID --run-id RUN --evaluator-commit SHA --candidate-commit SHA \
        --url-stdin --output benchmarks/reports/native-incremental/formal-run-1
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gc
import gzip
import hashlib
import importlib.abc
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import stat
import statistics
import struct
import subprocess
import sys
import types
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Afloat16/AI-Memory-Book"
PROTOCOL = "native-language-performance-2"
BASELINE = "6a8a9c6d603a812c75def258b11eb563ed590c9b"
BRANCH = "validation/native-incremental-formal-1"
EVIDENCE = ".artifacts/native-incremental-preservation/evidence/"
CHECKPOINT = ".artifacts/native-incremental-preservation/checkpoint.json"
PRESERVATION_INDEX = ".artifacts/native-incremental-preservation/evidence.index"
REPORT = "benchmarks/reports/native-incremental/formal-run-1/"
BUILD = ".artifacts/native-incremental-formal/"
PLAN = "benchmarks/experiments/native_incremental_formal_plan.json"
EVALUATOR = "scripts/native_incremental_performance.py"
COUNTS = {"synthetic61": 168, "public1015": 1015}
COHORT_HASHES = {
    "synthetic61": "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26",
    "public1015": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857",
}
CONFIGS = {
    "native-char2400": {"surface": "native", "budget_chars": 2400, "budget_tokens": None},
    "mcp-char2400": {"surface": "official-sdk-mcp-stdio", "budget_chars": 2400, "budget_tokens": None},
    "native-token1024": {"surface": "native", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
    "mcp-token1024": {"surface": "official-sdk-mcp-stdio", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
}
ORDERS = [["baseline", "candidate"], ["candidate", "baseline"],
          ["candidate", "baseline"], ["baseline", "candidate"]]
STABLE = ("query_id", "payload_sha256", "native_payload_sha256", "context_sha256", "envelope_sha256",
          "context_chars", "context_tokens", "result_count", "invariants")
INVARIANTS = {"scope", "source_spans", "page_projection", "context_reconstruction", "metadata",
              "character_budget", "result_limit", "token_budget", "token_metadata"}
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024


class AuditFailure(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditFailure(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha(dump(value).encode())


def hex_value(value, length):
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name and "\0" not in name
            and "\n" not in name and not name.startswith("/")
            and all(part not in ("", ".", "..") for part in name.split("/"))
            and PurePosixPath(name).as_posix() == name, "Noncanonical archive/member name")
    return name


def validate_metadata(metadata, args):
    artifact, run = metadata["artifact"], metadata["run"]
    require(str(artifact["id"]) == args.artifact_id, "Artifact API identity differs")
    require(artifact["name"] == f"native-incremental-{args.run_id}-1", "Artifact API name differs")
    require(artifact.get("expired") is False, "Artifact is expired")
    require(type(artifact["size_in_bytes"]) is int and 0 < artifact["size_in_bytes"] <= MAX_ZIP_BYTES,
            "Artifact API size is missing or outside the audit bound")
    expected_digest = artifact.get("digest", "")
    require(expected_digest.startswith("sha256:") and hex_value(expected_digest[7:], 64),
            "Artifact API lacks its SHA-256 digest")
    require(str(run["id"]) == args.run_id and run["run_attempt"] == 1
            and run["status"] == "completed" and run["event"] == "push"
            and run["head_branch"] == BRANCH and run["head_sha"] == args.evaluator_commit,
            "Workflow API run/attempt/source/status differs")
    require(run["path"] == ".github/workflows/native-incremental-performance.yml", "Workflow path differs")
    if "repository" in run:
        require(run["repository"]["full_name"] == REPOSITORY, "Workflow repository differs")
    origin = artifact["workflow_run"]
    require(str(origin["id"]) == args.run_id and origin["head_sha"] == args.evaluator_commit
            and origin["head_branch"] == BRANCH, "Artifact belongs to another workflow source")
    return artifact["size_in_bytes"], expected_digest[7:]


def download(url, expected_size, expected_sha):
    require(isinstance(url, str) and url.startswith("https://"), "An HTTPS signed artifact URL is required")
    output = io.BytesIO()
    checksum = hashlib.sha256()
    try:
        with urlopen(url, timeout=60) as response:
            while True:
                block = response.read(min(1024 * 1024, expected_size + 1 - output.tell()))
                if not block:
                    break
                output.write(block)
                checksum.update(block)
                require(output.tell() <= expected_size, "Downloaded artifact exceeds API byte size")
    except AuditFailure:
        raise
    except Exception as error:
        # Signed URL parameters must not appear in a traceback or persisted log.
        raise AuditFailure("Artifact download failed: " + type(error).__name__) from None
    require(output.tell() == expected_size and checksum.hexdigest() == expected_sha,
            "Downloaded artifact size/SHA-256 differs from the API")
    output.seek(0)
    return output


class Archive:
    def __init__(self, buffer):
        self.zip = zipfile.ZipFile(buffer)
        self.files = {}
        infos = self.zip.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)) and len(names) <= 2000, "Duplicate/excessive ZIP members")
        require(sum(info.file_size for info in infos) <= MAX_EXPANDED_BYTES, "Expanded ZIP exceeds the audit bound")
        for info in infos:
            name = info.filename[:-1] if info.is_dir() else info.filename
            safe_name(name)
            mode = info.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR)
                    and not info.flag_bits & 1, "Nonregular/encrypted ZIP member: " + name)
            if info.is_dir():
                continue
            require(info.file_size <= MAX_MEMBER_BYTES, "ZIP member exceeds the audit bound: " + name)
            checksum = hashlib.sha256()
            blob = hashlib.sha1(f"blob {info.file_size}\0".encode())
            count = 0
            with self.zip.open(info) as member:
                while True:
                    chunk = member.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    checksum.update(chunk)
                    blob.update(chunk)
            require(count == info.file_size, "ZIP member size differs: " + name)
            # Reading to EOF also validates the ZIP's CRC independently of SHA.
            self.files[name] = {"bytes": count, "sha256": checksum.hexdigest(), "git_blob": blob.digest()}

    def raw(self, name):
        require(name in self.files, "Missing retained member: " + name)
        return self.zip.read(name)

    def read(self, name):
        raw = self.raw(name)
        return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)

    def identical(self, left, right):
        require(left in self.files and right in self.files, "Missing duplicated original: " + right)
        require(self.files[left] == self.files[right], "Duplicate file metadata differs: " + right)
        with self.zip.open(left) as a, self.zip.open(right) as b:
            while True:
                chunk = a.read(1024 * 1024)
                require(chunk == b.read(1024 * 1024), "Duplicate bytes differ: " + right)
                if not chunk:
                    break


def committed_sha(repo, commit, name):
    safe_name(name)
    require(hex_value(commit, 40), "Invalid bound Git commit")
    process = subprocess.run(["git", "show", commit + ":" + name], cwd=repo, capture_output=True)
    require(process.returncode == 0, "Bound committed file is unavailable locally: " + commit[:12] + ":" + name)
    return sha(process.stdout)


def evidence_tree(files):
    root = {}
    for full, record in files.items():
        if not full.startswith(EVIDENCE):
            continue
        parts = full[len(EVIDENCE):].split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            require(isinstance(node, dict), "Conflicting evidence file/directory")
        require(parts[-1] not in node, "Duplicate evidence tree path")
        node[parts[-1]] = record["git_blob"]

    def tree(node):
        payload = bytearray()
        ordered = sorted(node, key=lambda name: (name + ("/" if isinstance(node[name], dict) else "")).encode())
        for name in ordered:
            entry = node[name]
            is_directory = isinstance(entry, dict)
            payload.extend(("40000 " if is_directory else "100644 ").encode() + name.encode() + b"\0")
            payload.extend(tree(entry) if is_directory else entry)
        return hashlib.sha1(f"tree {len(payload)}\0".encode() + payload).digest()

    return tree(root).hex()


def publication_index(archive):
    """Check the retained temporary Git index; it is outside the evidence tree."""
    raw = archive.raw(PRESERVATION_INDEX)
    require(len(raw) >= 32 and raw[:4] == b"DIRC" and hashlib.sha1(raw[:-20]).digest() == raw[-20:],
            "Preservation Git index header/checksum differs")
    version, count = struct.unpack(">II", raw[4:12])
    require(version in (2, 3, 4), "Unknown preservation Git index version")
    expected = {name[len(EVIDENCE):]: value["git_blob"] for name, value in archive.files.items() if name.startswith(EVIDENCE)}
    require(count == len(expected), "Preservation index entry count differs from the evidence tree")
    checked = False
    if version in (2, 3):
        entries, cursor = {}, 12
        for _ in range(count):
            beginning = cursor
            require(cursor + 62 <= len(raw) - 20, "Truncated preservation index entry")
            mode = struct.unpack(">I", raw[cursor + 24:cursor + 28])[0]
            blob = raw[cursor + 40:cursor + 60]
            flags = struct.unpack(">H", raw[cursor + 60:cursor + 62])[0]
            require(mode == 0o100644 and flags & 0x3000 == 0, "Unexpected evidence index mode/stage")
            cursor += 62
            if flags & 0x4000:
                require(version == 3, "Extended flags require Git index version 3")
                cursor += 2
            ending = raw.find(b"\0", cursor, len(raw) - 20)
            require(ending >= cursor, "Missing evidence index path terminator")
            name = raw[cursor:ending].decode("utf-8")
            safe_name(name)
            require(name not in entries and (flags & 0xfff) == min(len(raw[cursor:ending]), 0xfff),
                    "Duplicate or incorrectly sized evidence index path")
            entries[name] = blob
            cursor = beginning + ((ending - beginning + 1 + 7) // 8) * 8
            require(raw[ending:cursor] == b"\0" * (cursor - ending), "Nonzero evidence index padding")
        require(entries == expected, "Preservation Git index paths/blob identities differ from the artifact")
        checked = True
    return {"path": PRESERVATION_INDEX, "bytes": len(raw), "sha256": sha(raw), "version": version,
            "entries": count, "checksum_verified": True, "all_paths_and_blob_ids_verified": checked,
            "scope": "Temporary publication index retained by Actions; not a member of the evidence Git tree."}


def verify_snapshot(archive, metadata, args):
    manifest = archive.read(EVIDENCE + "evidence-manifest.json")
    checkpoint = archive.read(CHECKPOINT)
    require(manifest["protocol"] == PROTOCOL and manifest["repository"] == REPOSITORY,
            "Evidence protocol/repository differs")
    source_run = manifest["source_run"]
    require(str(source_run["id"]) == args.run_id and source_run["attempt"] == 1
            and source_run["commit"] == args.evaluator_commit, "Evidence run identity differs")
    branch = f"evidence/native-incremental-{args.run_id}-1"
    require(manifest["evidence_branch"] == branch and not manifest["unavailable_runtime_sources"],
            "Evidence branch differs or runtime sources are incomplete")
    inventory = {}
    for field in ("original_files", "frozen_evaluator_files", "frozen_runtime_files"):
        for name, expected in manifest[field].items():
            safe_name(name)
            require(name not in inventory, "Overlapping evidence inventories")
            inventory[name] = expected
            observed = archive.files.get(EVIDENCE + name)
            require(observed is not None and expected == {key: observed[key] for key in ("bytes", "sha256")},
                    "Evidence member differs from manifest: " + name)
    extras = {"evidence-manifest.json", "audit.json", "README.md", "audit.stdout.log", "audit.stderr.log"}
    require({name[len(EVIDENCE):] for name in archive.files if name.startswith(EVIDENCE)} == set(inventory) | extras,
            "Uninventoried or missing evidence files")
    originals = manifest["original_files"]
    require({name for name in archive.files if not name.startswith(EVIDENCE)} == set(originals) | {CHECKPOINT, PRESERVATION_INDEX},
            "Unexpected/missing duplicate artifact members")
    for name in originals:
        archive.identical(EVIDENCE + name, name)
    require(checkpoint["stage"] == "completed" and str(checkpoint["source_run_id"]) == args.run_id
            and str(checkpoint["source_run_attempt"]) == "1" and checkpoint["branch"] == branch,
            "Git preservation did not complete for this attempt")
    tree = evidence_tree(archive.files)
    index = publication_index(archive)
    require(hex_value(checkpoint["commit"], 40) and checkpoint["tree"] == tree,
            "Preserved Git evidence tree differs from artifact bytes")
    if "evidence" in metadata:
        require(metadata["evidence"]["commit"] == checkpoint["commit"]
                and metadata["evidence"]["tree"] == tree, "Git API evidence commit/tree differs")

    run = archive.read(EVIDENCE + REPORT + "run.json")
    summary = archive.read(EVIDENCE + REPORT + "summary.json")
    require(run["protocol"] == PROTOCOL and run["evaluator_commit"] == args.evaluator_commit,
            "Measured evaluator identity differs")
    require(run["plan"]["sources"] == {"baseline": {"commit": args.baseline_commit, "backend": "native"},
                                          "candidate": {"commit": args.candidate_commit, "backend": "native"}},
            "Measured sources differ from the requested native pair")
    plan = archive.raw(EVIDENCE + "frozen-evaluator/" + PLAN)
    require(sha(plan) == run["plan_sha256"] and json.loads(plan) == run["plan"], "Frozen plan differs")
    require(set(manifest["frozen_evaluator_files"]) == {"frozen-evaluator/" + name for name in run["evaluator"]},
            "Frozen evaluator inventory differs")
    committed_files = 0
    for name, expected in run["evaluator"].items():
        require(archive.files[EVIDENCE + "frozen-evaluator/" + name]["sha256"] == expected
                == committed_sha(args.repo, args.evaluator_commit, name), "Frozen evaluator bytes differ from Git: " + name)
        committed_files += 1
    expected_runtime = set()
    for label, source in run["sources"].items():
        require(source["source_files_sha256"] == digest(source["source_files"])
                and source["unmaterialized_build_files"] == [] and len(source["native_binaries"]) == 1,
                "Runtime manifest is incomplete: " + label)
        for name, expected in source["source_files"].items():
            frozen = "frozen-runtimes/" + label + "/" + name
            expected_runtime.add(frozen)
            require(archive.files[EVIDENCE + frozen]["sha256"] == expected
                    == committed_sha(args.repo, source["commit"], name), "Frozen runtime bytes differ from Git: " + label + "/" + name)
            committed_files += 1
    require(set(manifest["frozen_runtime_files"]) == expected_runtime, "Frozen runtime inventory differs")
    build_raw = archive.raw(EVIDENCE + BUILD + "build-manifest.json")
    build = json.loads(build_raw)
    require(sha(build_raw) == run["build_manifest_sha256"] and build == run["build_manifest"], "Build manifest differs")
    require(build["workflow_commit"] == args.evaluator_commit and str(build["workflow_run_id"]) == args.run_id
            and build["workflow_run_attempt"] == 1 and build["status"] == "completed", "Native build hosted identity differs")
    probes = {}
    for label, source in run["sources"].items():
        record = build["builds"][label]
        require(record["status"] == "completed" and record["returncode"] == 0 and record["probe_returncode"] == 0
                and record["source_commit"] == source["commit"] and record["backend"] == "native"
                and record["native_binaries"] == source["native_binaries"], "Native build/probe did not complete: " + label)
        for name, expected in source["native_binaries"].items():
            require(archive.files[EVIDENCE + BUILD + label + "/" + name]["sha256"] == expected,
                    "Measured native binary differs: " + label)
        for name, field in (("build.log", "build_log_sha256"), ("probe.json", "probe_sha256")):
            require(archive.files[EVIDENCE + BUILD + label + "/" + name]["sha256"] == record[field],
                    "Native build/probe bytes differ: " + label + "/" + name)
        probe = archive.read(EVIDENCE + BUILD + label + "/probe.json")
        require(probe["requested"] == probe["actual"] == "native"
                and probe["binary_sha256"] in source["native_binaries"].values()
                and probe["available_functions"] == sorted(run["plan"]["native_helper_calls"][label])
                and probe["dispatch_probe"]["native_helper_calls"] == run["plan"]["native_helper_calls"][label]
                and probe["dispatch_probe"]["instrumentation_restored"] is True, "Native preflight binding differs: " + label)
        probes[label] = probe
    require(all(build["builds"]["baseline"][key] == build["builds"]["candidate"][key]
                for key in ("command", "compiler", "flags")), "Native compiler/command/flags differ")
    require(run["sources"]["baseline"]["source_files"]["setup.py"]
            == run["sources"]["candidate"]["source_files"]["setup.py"], "Native build definition differs")
    require(probes["baseline"]["dispatch_probe"]["outputs_sha256"]
            == probes["candidate"]["dispatch_probe"]["outputs_sha256"], "Native public preflight outputs differ")
    audit = archive.read(EVIDENCE + "audit.json")
    require(audit == manifest["audit"] == checkpoint["audit"] and audit["original_summary_exactly_reproduced"] is True
            and audit["remeasured_calls"] == 0 and audit["attempted_calls"] == 113568 and audit["paired_calls"] == 56784,
            "Preservation audit metadata differs")
    require(json.loads(archive.raw(EVIDENCE + "audit.stdout.log")) == summary, "Preserved auditor stdout differs from summary")
    return run, summary, build, probes, {"branch": branch, "commit": checkpoint["commit"], "tree": tree,
        "manifest_files": len(inventory), "duplicate_files": len(originals), "committed_files_verified": committed_files,
        "publication_index": index}


class Member:
    def __init__(self, archive, name):
        self.archive, self.name = archive, name

    def __truediv__(self, name):
        return Member(self.archive, self.name.rstrip("/") + "/" + name)

    def read_bytes(self):
        return self.archive.raw(self.name)


class FrozenModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, archive):
        self.archive = archive
        self.modules = {"benchmarks": "benchmarks/__init__.py", "benchmarks.data": "benchmarks/data.py",
                        "benchmarks.public_data": "benchmarks/public_data.py", "benchmarks.run": "benchmarks/run.py"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.modules:
            return importlib.util.spec_from_loader(fullname, self, is_package=fullname == "benchmarks")
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = self.modules[module.__name__]
        module.__file__ = "/frozen-evaluator/" + name
        exec(compile(self.archive.raw(EVIDENCE + "frozen-evaluator/" + name), module.__file__, "exec"), module.__dict__)


@contextmanager
def frozen_evaluator(archive):
    finder = FrozenModules(archive)
    saved = {name: sys.modules.pop(name) for name in list(sys.modules)
             if name == "benchmarks" or name.startswith("benchmarks.")}
    paths = list(sys.path)
    sys.meta_path.insert(0, finder)
    try:
        module = types.ModuleType("frozen_native_incremental_evaluator")
        module.__file__ = "/frozen-evaluator/" + EVALUATOR
        exec(compile(archive.raw(EVIDENCE + "frozen-evaluator/" + EVALUATOR), module.__file__, "exec"), module.__dict__)
        module.read = lambda member: archive.read(member.name)
        yield module
    finally:
        sys.meta_path.remove(finder)
        sys.path[:] = paths
        for name in list(sys.modules):
            if name == "benchmarks" or name.startswith("benchmarks."):
                del sys.modules[name]
        sys.modules.update(saved)


def percentile(values, quantile):
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def latency(values):
    require(values and all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in values),
            "Invalid raw latency sample")
    return {"samples": len(values), "mean_ms": statistics.fmean(values), "p50_ms": percentile(values, .5),
            "p95_ms": percentile(values, .95), "min_ms": min(values), "max_ms": max(values)}


def stats(values):
    require(values and all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in values),
            "Invalid resource sample")
    return {"n": len(values), "median": statistics.median(values), "min": min(values), "max": max(values)}


def order(identities, round_index, configuration_index):
    result = []
    for repetition in range(3):
        shuffled = list(identities)
        random.Random(110061 + 1009 * round_index + 97 * repetition + configuration_index).shuffle(shuffled)
        result.extend({"query_id": identity, "repetition": repetition} for identity in shuffled)
    return result


def independent_rows(archive, run, original, probes):
    plan = run["plan"]
    require(plan["cohorts"] == list(COUNTS) and plan["configurations"] == list(CONFIGS)
            and plan["engine_order"] == ORDERS and plan["repetitions_per_worker"] == 3
            and plan["expected_timed_calls"] == 113568 and plan["expected_paired_calls"] == 56784,
            "Independent expected experiment matrix differs")
    schedule = [{"key": f"r{number}-{cohort}-{label}", "round": number, "cohort": cohort, "label": label}
                for number, labels in enumerate(ORDERS) for cohort in COUNTS for label in labels]
    require(run["schedule"] == schedule, "Independent worker schedule differs")
    timings, cpus, canonical, protocols, archives, resources, round_cells = {}, {}, {}, {}, {}, {}, {}
    rows_count = pair_count = event_count = invariant_failures = difference_count = 0
    differences = []

    def difference(identity, reason):
        nonlocal difference_count
        difference_count += 1
        if len(differences) < 25:
            differences.append({"identity": identity, "reason": reason})

    for cohort, count in COUNTS.items():
        ids = run["query_ids"][cohort]
        require(len(ids) == len(set(ids)) == count, "Independent query identity count differs")
        require(run["cohorts"][cohort]["sha256"] == COHORT_HASHES[cohort]
                and run["cohorts"][cohort]["queries"] == count, "Independent registered cohort fingerprint differs")
        for round_index in range(4):
            paired = {label: archive.read(EVIDENCE + REPORT + f"r{round_index}-{cohort}-{label}.json.gz")
                      for label in ("baseline", "candidate")}
            for label, worker in paired.items():
                key = f"r{round_index}-{cohort}-{label}"
                item = next(item for item in schedule if item["key"] == key)
                started = archive.read(EVIDENCE + REPORT + key + ".started.json")
                require(started["worker"] == item and started["run_sha256"] == digest(run), "Independent start intent differs")
                require(all(worker[name] == value for name, value in item.items())
                        and worker["status"] == "completed" and worker["error"] is None and worker["source_unchanged"] is True
                        and worker["run_sha256"] == digest(run)
                        and worker["source_manifest_sha256"] == digest(run["sources"][label])
                        and worker["backend"] == probes[label] and worker["dataset"] == run["cohorts"][cohort],
                        "Independent worker identity/status differs: " + key)
                archive_identity = {name: worker[name] for name in ("archive_before", "archive_after", "ingestion_sha256", "unchanged_reingestion_sha256")}
                if archive_identity != archives.setdefault(cohort, archive_identity) or worker["archive_before"] != worker["archive_after"]:
                    difference(key, "archive or ingestion differs")
                require([cell["id"] for cell in worker["configurations"]] == list(CONFIGS), "Independent configuration order differs")
                ledger_raw = archive.raw(EVIDENCE + REPORT + key + ".attempts.jsonl.gz")
                require(sha(ledger_raw) == worker["ledger_sha256"], "Independent ledger byte hash differs")
                with gzip.GzipFile(fileobj=io.BytesIO(ledger_raw)) as ledger:
                    for index, cell in enumerate(worker["configurations"]):
                        config = cell["id"]
                        require({name: cell[name] for name in CONFIGS[config]} == CONFIGS[config], "Independent budget/surface differs")
                        if CONFIGS[config]["surface"] == "official-sdk-mcp-stdio":
                            protocol = {name: cell["resources"][name] for name in ("tool_schema_sha256", "instructions_sha256")}
                            if protocol != protocols.setdefault((cohort, config), protocol):
                                difference(key + ":" + config, "MCP tool schema or instructions differ")
                        expected_order = order(ids, round_index, index)
                        require([{name: row[name] for name in ("query_id", "repetition")} for row in cell["rows"]] == expected_order
                                and cell["query_order_sha256"] == digest(expected_order)
                                and run["query_order_sha256"][f"r{round_index}-{cohort}-{config}"] == digest(expected_order),
                                "Independent query schedule/digest differs")
                        for row in cell["rows"]:
                            identity = {"configuration": config, "query_id": row["query_id"], "repetition": row["repetition"],
                                        "attempt_id": f"{config}:p{row['repetition']}:{row['query_id']}"}
                            require(json.loads(ledger.readline()) == {"event": "started", **identity}
                                    and json.loads(ledger.readline()) == {"event": "finished", **identity, "row": row},
                                    "Independent started/finished ledger event differs")
                            event_count += 2
                            require(set(row["invariants"]) == INVARIANTS
                                    and all(type(value) is int and value >= 0 for value in row["invariants"].values()),
                                    "Independent invariant schema differs")
                            invariant_failures += sum(row["invariants"].values())
                            stable = {name: row[name] for name in STABLE}
                            canonical_key = (cohort, config, row["query_id"])
                            if stable != canonical.setdefault(canonical_key, stable):
                                difference(f"{key}:{identity['attempt_id']}", "recorded stable output differs across sources/passes/rounds")
                            cpu = row["calling_process_cpu_ms"]
                            require(type(cpu) in (int, float) and math.isfinite(cpu) and cpu >= 0, "Invalid raw CPU sample")
                        values = [row["wall_ms"] for row in cell["rows"]]
                        require(latency(values) == cell["latency"], "Independent worker latency summary differs")
                        timings.setdefault((cohort, config, label), []).extend(values)
                        cpus.setdefault((cohort, config, label), []).extend(row["calling_process_cpu_ms"] for row in cell["rows"])
                        round_cells[(cohort, config, round_index, label)] = latency(values)
                        rows_count += len(values)
                    require(ledger.read(1) == b"", "Unexpected extra ledger events")
                resources[key] = {"key": key, "runtime_import_ms": worker["runtime_import_ms"], "resources": worker["resources"],
                                  "configuration_resources": {cell["id"]: cell["resources"] for cell in worker["configurations"]}}
            for index, config in enumerate(CONFIGS):
                a, b = (paired[label]["configurations"][index] for label in ("baseline", "candidate"))
                require(len(a["rows"]) == len(b["rows"]), "Paired row count differs")
                for left, right in zip(a["rows"], b["rows"]):
                    require((left["query_id"], left["repetition"]) == (right["query_id"], right["repetition"]), "Paired attempt identity differs")
                    if any(left[name] != right[name] for name in STABLE):
                        difference(f"r{round_index}-{cohort}-{config}:{left['query_id']}:p{left['repetition']}", "paired stable fields differ")
                pair_count += len(a["rows"])
            del paired
            gc.collect()
    require(rows_count == 113568 and pair_count == 56784 and event_count == 227136, "Independent total counts differ")
    require(invariant_failures == 0, "Recorded source/scope/budget invariant failures exist")
    ordered_resources = [resources[item["key"]] for item in schedule]
    require(ordered_resources == original["worker_resources"], "Archived resources differ from raw workers")
    cells = []
    for archived in original["comparison"]["cells"]:
        cohort, config = archived["cohort"], archived["configuration"]
        calculated = {"cohort": cohort, "configuration": config}
        for label in ("baseline", "candidate"):
            values = timings[(cohort, config, label)]
            calculated[label] = latency(values)
            require(calculated[label] == archived[label], "Independent pooled timing summary differs")
        for quantile in ("p50", "p95"):
            name = quantile + "_improvement_percent"
            calculated[name] = 100 * (1 - calculated["candidate"][quantile + "_ms"] / calculated["baseline"][quantile + "_ms"])
            require(calculated[name] == archived[name], "Independent pooled reduction differs")
        calculated["rounds"] = []
        for number in range(4):
            a, b = (round_cells[(cohort, config, number, label)] for label in ("baseline", "candidate"))
            calculated["rounds"].append({"round": number, "baseline": a, "candidate": b,
                                         "p95_improvement_percent": 100 * (1 - b["p95_ms"] / a["p95_ms"])})
        require(calculated["rounds"] == archived["rounds"], "Independent per-round summaries differ")
        calculated["mean_calling_process_cpu_ms"] = {label: statistics.fmean(cpus[(cohort, config, label)])
                                                      for label in ("baseline", "candidate")}
        calculated["p95_regressing_rounds"] = [row["round"] for row in calculated["rounds"] if row["p95_improvement_percent"] < 0]
        cells.append(calculated)
    require([(cell["cohort"], cell["configuration"]) for cell in cells]
            == [(cohort, config) for cohort in COUNTS for config in CONFIGS], "Independent pooled cell inventory differs")
    require((difference_count == 0) == original["comparison"]["complete_output_and_archive_equivalence"],
            "Independent equivalence conclusion differs")
    return {"attempted_calls": rows_count, "paired_calls": pair_count, "ledger_events": event_count,
            "invariant_failures": invariant_failures, "difference_count": difference_count,
            "difference_examples": differences, "cells": cells, "raw_resources": ordered_resources}


def resource_summary(workers):
    result = []
    for cohort in COUNTS:
        grouped = {"cohort": cohort}
        for label in ("baseline", "candidate"):
            selected = [worker for worker in workers if worker["key"].endswith("-" + cohort + "-" + label)]
            require(len(selected) == 4, "Independent resource worker count differs")
            values = {"runtime_import_ms": stats([worker["runtime_import_ms"] for worker in selected])}
            for key in ("new_database_ms", "fresh_ingestion_ms", "unchanged_reingestion_ms", "existing_database_open_ms"):
                values[key] = stats([worker["resources"][key] for worker in selected])
            for stage in ("after_ingestion", "after_calls"):
                for key in ("rss_bytes", "hwm_bytes", "user_cpu_s", "system_cpu_s"):
                    values[stage + "_" + key] = stats([worker["resources"][stage][key] for worker in selected])
            for stage in ("storage_after_ingestion", "storage_after_checkpoint"):
                values[stage] = [worker["resources"][stage] for worker in selected]
            values["mcp"] = {}
            for config in ("mcp-char2400", "mcp-token1024"):
                records = [worker["configuration_resources"][config] for worker in selected]
                values["mcp"][config] = {
                    "startup_to_initialize_ms": stats([row["startup_to_initialize_ms"] for row in records]),
                    "server_rss_after_calls_bytes": stats([row["server_after_calls"]["rss_bytes"] for row in records]),
                    "server_hwm_after_calls_bytes": stats([row["server_after_calls"]["hwm_bytes"] for row in records]),
                    "server_cpu_during_calls_s": stats([sum(row["server_after_calls"][key] - row["server_before_calls"][key]
                        for key in ("user_cpu_s", "system_cpu_s")) for row in records]),
                    "storage_live": [row["storage_live"] for row in records],
                }
            grouped[label] = values
        result.append(grouped)
    return result


def save_exact(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, "Refusing to replace a different existing audit file: " + str(path))
        return
    with path.open("xb") as output:
        output.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evaluator-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--baseline-commit", default=BASELINE)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / REPORT)
    url = parser.add_mutually_exclusive_group(required=True)
    url.add_argument("--url-stdin", action="store_true")
    url.add_argument("--url-env", help="Name of an environment variable containing the signed URL")
    args = parser.parse_args(argv)
    metadata_raw = args.metadata.read_bytes()
    metadata = json.loads(metadata_raw)
    size, expected_sha = validate_metadata(metadata, args)
    signed_url = sys.stdin.readline().strip() if args.url_stdin else os.environ.get(args.url_env, "")
    buffer = download(signed_url, size, expected_sha)
    del signed_url
    archive = Archive(buffer)
    run, original, build, probes, evidence = verify_snapshot(archive, metadata, args)
    with frozen_evaluator(archive) as evaluator:
        require(set(run["evaluator"]) == set((*evaluator.EVALUATOR_FILES, PLAN)), "Frozen evaluator declared inventory differs")
        replayed = evaluator.audit(Member(archive, EVIDENCE + REPORT))
    require(replayed == original, "Frozen in-memory audit does not exactly reproduce the archived summary")
    del replayed
    gc.collect()
    independent = independent_rows(archive, run, original, probes)
    resources = resource_summary(independent.pop("raw_resources"))
    result = {"schema_version": 1, "protocol": PROTOCOL,
        "auditor": {"path": "scripts/native_incremental_audit_artifact.py", "sha256": sha(Path(__file__).read_bytes())},
        "api_metadata_sha256": sha(metadata_raw), "artifact_id": int(args.artifact_id),
        "artifact_name": metadata["artifact"]["name"], "artifact_bytes": size, "artifact_sha256": expected_sha,
        "artifact_entries": len(archive.zip.infolist()), "artifact_files": len(archive.files),
        "run": {"id": args.run_id, "attempt": 1, "evaluator_commit": args.evaluator_commit,
                "conclusion": metadata["run"]["conclusion"], "url": f"https://github.com/{REPOSITORY}/actions/runs/{args.run_id}"},
        "sources": run["plan"]["sources"], "evidence": evidence,
        "frozen_evaluator_summary_exactly_reproduced": True,
        "all_manifest_and_duplicate_bytes_verified": True, "all_frozen_sources_match_declared_git_commits": True,
        "both_native_binaries_builds_and_dispatch_probes_verified": True,
        "complete_output_digest_and_archive_equivalence": independent["difference_count"] == 0,
        "remeasured_calls": 0, **independent, "resources": resources, "host": run["host"],
        "timing_boundaries": run["timing_boundaries"],
        "validation_limits": "The hosted evaluator hashed outputs and checked source/scope/budget invariants at execution. This offline audit verifies retained bytes, Git identities, complete ledgers, output-digest equality and independently calculated timings/resources. It does not execute either runtime or recover original payload text from hashes. MCP per-call CPU belongs to the client; server CPU is a separate live-process delta. Negative latency improvements are regressions.",
        "file_sha256": {name: record["sha256"] for name, record in archive.files.items()}}
    for name, member in (("run.json", REPORT + "run.json"), ("summary.json", REPORT + "summary.json"),
                         ("build-manifest.json", BUILD + "build-manifest.json")):
        save_exact(args.output / name, archive.raw(EVIDENCE + member))
    save_exact(args.output / "independent-audit.json", (json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())
    print(dump({"audit": "passed", "artifact_id": int(args.artifact_id), "calls": independent["attempted_calls"],
                "pairs": independent["paired_calls"], "ledger_events": independent["ledger_events"], "evidence": evidence,
                "equivalent": result["complete_output_digest_and_archive_equivalence"], "output": str(args.output)}), flush=True)
    for cell in result["cells"]:
        print(dump({"cohort": cell["cohort"], "configuration": cell["configuration"],
                    "p50_improvement_percent": cell["p50_improvement_percent"], "p95_improvement_percent": cell["p95_improvement_percent"],
                    "round_p95_improvement_percent": [row["p95_improvement_percent"] for row in cell["rounds"]],
                    "baseline": cell["baseline"], "candidate": cell["candidate"]}), flush=True)
    for resource in resources:
        print(dump({"resource_cohort": resource["cohort"], **{label: {key: resource[label][key] for key in
            ("fresh_ingestion_ms", "unchanged_reingestion_ms", "runtime_import_ms", "after_calls_rss_bytes")}
            for label in ("baseline", "candidate")}}), flush=True)
    if not result["complete_output_digest_and_archive_equivalence"]:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except AuditFailure as error:
        raise SystemExit("Artifact audit failed: " + str(error)) from None
