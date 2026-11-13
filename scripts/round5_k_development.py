"""Prospective K isolated development with separate correctness and measurement exports.

Run one complete diagnostic profile, saved-reference payload audit, and balanced
native timing sequence. No fresh selection, formal acceptance, or replay is run.
Every measured stage is bracketed by verified remote Git checkpoints.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "round5-candidate-k-development-1"
BRANCH = "validation/v033-candidate-k-development-1"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SCOPE = ROOT / "benchmarks/experiments/round5-candidate-k-development-scope.json"
OLD = ROOT / "benchmarks/experiments/round5-development-attempt-i.json"
OLD_SHA = "02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5"
SOURCE_BINDING = ROOT / "benchmarks/experiments/round5-candidate-k-source.json"
SOURCE_BINDING_SHA = "416caf9fea33d41197bf8094de8d2a5545a49b619fd510864c8411895ac8b8fd"
SCOPE_SHA = "0580c895f8c756e8d8688c446bf95445791c53d5950106b5bb6b6da9c063045a"
REFERENCE_COMMIT = "761eaf5c9ca47c93dea25f73104eb259304df68a"
CORRECTNESS_MODULES = (
    "tests.test_round5_statement_cache",
    "tests.test_round5_native_rows",
    "tests.test_round5_materialization",
    "tests.test_round4_sealed_counts",
    "tests.test_round4_highlight",
    "tests.test_round4_token_work",
    "tests.test_token_budget",
    "tests.test_project_rowid_bounds",
    "tests.test_lexical_cache",
    "tests.test_title_reference",
    "tests.test_title_reference_interfaces",
    "tests.test_title_reference_native_integration",
    "tests.test_round5_normalization_identity",
)
COHORTS = ("synthetic61", "public1015")
CONFIGS = ("native-char4000", "native-token512", "native-token1024", "native-token2048")
TABLES = ("sessions", "chapters", "turns", "sections", "pages", "pages_fts", "pages_stem_fts")


class PublicationError(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def parse_remote(raw):
    fields = raw.split()
    if not fields:
        return None
    if len(fields) != 2 or fields[1] != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise PublicationError("Unexpected remote result-ref response")
    return fields[0]


def remote_head():
    return parse_remote(git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def publish(message):
    """One non-force push; reject divergent refs and never retry ambiguous writes."""
    journal = STATE / "publication.json"
    if (PUBLIC / "publication-failure.json").exists():
        raise PublicationError("Publication already failed; artifact-only preservation")
    expected = read(journal)["expected_remote"]
    parent = git("rev-parse", "HEAD")
    try:
        if remote_head() != expected:
            raise PublicationError("Another writer owns or advanced the result ref")
        if expected is not None and parent != expected:
            raise PublicationError("Local result ancestry changed")
        if git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged changes")
        subprocess.run(["git", "add", "--sparse", "--", str(PUBLIC.relative_to(ROOT))], cwd=ROOT, check=True)
        staged = git("diff", "--cached", "--name-only").splitlines()
        prefix = str(PUBLIC.relative_to(ROOT)) + "/"
        if not staged or any(not path.startswith(prefix) for path in staged):
            raise PublicationError("Checkpoint contains missing or unrelated files")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
                                cwd=ROOT, capture_output=True, text=True)
        observed = remote_head()
        if pushed.returncode or observed != head:
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected, "local_commit": head,
                "observed_remote": observed, "push_returncode": pushed.returncode,
                "stdout": pushed.stdout, "stderr": pushed.stderr,
                "policy": "No automatic write or measurement retry; retain artifacts."})
            raise PublicationError("Push failed or did not verify at the expected commit")
        save(journal, {"expected_remote": head})
        print(json.dumps({"checkpoint": head, "branch": BRANCH, "message": message}), flush=True)
    except BaseException as error:
        if not (PUBLIC / "publication-failure.json").exists():
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No automatic retry; inspect remote ref and artifact evidence."})
        raise


def verify_files(files, directory=ROOT):
    for path, expected in files.items():
        if sha(directory / path) != expected:
            raise ValueError("Frozen file changed: " + path)


def source_files(directory):
    return {str(path.relative_to(directory)): sha(path)
            for path in sorted((directory / "src").rglob("*")) if path.is_file()}



def runtime_sha(directory):
    """The unchanged published engine_source_hash boundary, without importing it."""
    package = directory / "src/memory_book"
    value = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        value.update(path.relative_to(package).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return value.hexdigest()


def verify_exact_source(directory, identity):
    if (directory.is_symlink() or (directory / "src").is_symlink()
            or any(path.is_symlink() for path in (directory / "src").rglob("*"))):
        raise ValueError("Runtime source contains a symlink")
    if source_files(directory) != identity["files_sha256"]:
        raise ValueError("Runtime source changed")
    if runtime_sha(directory) != identity["runtime_sha256"]:
        raise ValueError("Runtime aggregate SHA changed")


def inventory_difference(actual, expected):
    return {
        "added": {name: actual[name] for name in sorted(set(actual) - set(expected))},
        "missing": {name: expected[name] for name in sorted(set(expected) - set(actual))},
        "changed": {name: {"expected": expected[name], "actual": actual[name]}
                    for name in sorted(set(actual) & set(expected)) if actual[name] != expected[name]},
    }


def full_export_files(directory):
    return {path.relative_to(directory).as_posix(): sha(path) for path in sorted(directory.rglob("*"))
            if path.is_file() and not path.is_symlink()}


def correctness_inventory(directory, identity, before):
    """Retain differences in the unmeasured test copy; never relax a runtime guard."""
    actual = source_files(directory)
    difference = inventory_difference(actual, identity["files_sha256"])
    full_after = full_export_files(directory)
    full_difference = inventory_difference(full_after, before)
    errors, bytecode = [], {}
    if difference["missing"] or difference["changed"] or full_difference["missing"] or full_difference["changed"]:
        errors.append("A frozen source or fixture file changed or disappeared")
    if any(path.is_symlink() for path in directory.rglob("*")):
        errors.append("Correctness export contains a symlink")
    expected_caches = {
        Path(importlib.util.cache_from_source(str(directory / source))).relative_to(directory).as_posix(): source
        for source in identity["files_sha256"] if source.endswith(".py")}
    for name in full_difference["added"]:
        path = directory / name
        source_name = expected_caches.get(name)
        if source_name is None:
            errors.append("Unexpected added file: " + name)
            continue
        candidate = directory / source_name
        raw = path.read_bytes()
        if len(raw) < 16 or raw[:4] != importlib.util.MAGIC_NUMBER:
            errors.append("Unexpected added file: " + name)
        else:
            bytecode[name] = {"sha256": sha(path), "bytes": len(raw),
                "header_hex": raw[:16].hex(), "compiled_source": source_name,
                "compiled_source_sha256": sha(candidate)}
    if runtime_sha(directory) != identity["runtime_sha256"]:
        errors.append("Correctness runtime aggregate changed")
    return {"source_inventory": actual, "difference": difference,
            "full_export_inventory": full_after, "full_export_difference": full_difference,
            "generated_bytecode": bytecode, "errors": errors,
            "policy": "All files remain preserved. This export is never used for corpus preparation, profiling or timing."}


def archive_correctness_export(directory):
    """Keep the complete test export, including generated files and failures."""
    output = PUBLIC / "correctness-export.tar.gz"
    temporary = output.with_name(output.name + ".partial")
    with temporary.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                archive.add(directory, arcname="correctness-export")
        raw.flush()
        os.fsync(raw.fileno())
    temporary.replace(output)
    return {"path": output.relative_to(ROOT).as_posix(), "bytes": output.stat().st_size,
            "sha256": sha(output), "contents": "Complete exact-source correctness export and artificial fixture residue; no development corpus was downloaded yet."}


def validate_evidence_value(value, kind, identity):
    if kind == "independent_source_review":
        if (value.get("status") != "accepted-independent-source-review-of-isolated-k-on-i-t1-before-corpus"
                or value.get("reviewed_source_commit") != identity["commit"]
                or value.get("runtime_sha256") != identity["runtime_sha256"]
                or value.get("performance_accepted") is not False
                or value.get("corpus_calls_executed_by_review") != 0):
            raise ValueError("Independent review does not cover the exact unmeasured K source")
    elif kind == "prior_decision":
        if (value.get("status") != "verified-negative-development-result"
                or value.get("source_commit") != "910ba8904523ad81cb7d68073af77580942496eb"
                or value.get("calls") != 4096 or value.get("complete_payload_pairs") != 2048
                or value.get("payload_mismatches") != 0 or value.get("adverse_cells_over_five_percent") != 8
                or value.get("retrieval_calls_executed_by_audit") != 0
                or value.get("formal_acceptance") is not False):
            raise ValueError("Saved rejection evidence changed its original boundary")
    else:
        raise ValueError("Unknown source-free evidence kind")


def verify_development_prerequisites():
    """Verify committed K source/review and preserved negative evidence before claim."""
    if sha(SCOPE) != SCOPE_SHA:
        raise ValueError("K prospective scope bytes changed")
    scope, source = read(SCOPE), read(SOURCE_BINDING)
    derivation = scope["derivation"]
    if sha(ROOT / derivation["original_driver"]) != derivation["sha256"]:
        raise ValueError("Inherited isolated-source driver changed")
    for path in (Path(__file__).resolve(), SCOPE, SOURCE_BINDING):
        raw = subprocess.check_output(["git", "show", "HEAD:" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        if raw != path.read_bytes():
            raise ValueError("K development input is not its committed blob")
    ci = source["source_ci"]
    if (ci["head_sha"] != source["commit"] or ci["conclusion"] != "success"
            or len(ci["jobs"]) != 9 or any(job["conclusion"] != "success" for job in ci["jobs"])):
        raise ValueError("Complete exact-source integration CI is required")
    evidence = []
    for kind, items in (("independent_source_review", source.get("independent_source_review")),
                        ("prior_decision", scope.get("prior_decisions"))):
        if type(items) is not list or not items:
            raise ValueError("Missing immutable preclaim evidence")
        for item in items:
            if (type(item) is not dict or set(item) != {"commit", "path", "sha256"}
                    or re.fullmatch(r"[0-9a-f]{40}", item.get("commit", "")) is None
                    or re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is None
                    or not item["path"].startswith("benchmarks/reports/")
                    or ".." in Path(item["path"]).parts or Path(item["path"]).is_absolute()):
                raise ValueError("Invalid immutable preclaim evidence reference")
            subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                            "origin", item["commit"]], cwd=ROOT, check=True)
            raw = subprocess.check_output(["git", "show", item["commit"] + ":" + item["path"]], cwd=ROOT)
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("Immutable evidence bytes changed")
            validate_evidence_value(json.loads(raw), kind, source)
            evidence.append({"kind": kind, **item})
    return {"source_commit": source["commit"], "runtime_sha256": source["runtime_sha256"],
            "source_ci_run": ci["run_id"], "evidence": evidence,
            "derivation": derivation, "prior_k_corpus_calls": 0,
            "policy": "New isolated K candidate only; no replay or timing pooling."}


def export_source(label, identity):
    directory = STATE / "sources" / label
    directory.mkdir(parents=True, exist_ok=False)
    export_commit = identity["commit"]
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", export_commit], cwd=ROOT, check=True)
    archive = STATE / (label + ".tar")
    subprocess.run(["git", "archive", "--format=tar", "--output=" + str(archive),
                    export_commit, "src", "tests"], cwd=ROOT, check=True)
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] not in ("src", "tests") or ".." in parts:
                raise ValueError("Unexpected source archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Nonregular source archive member")
        stream.extractall(directory)
    archive.unlink()
    verify_exact_source(directory, identity)
    return directory


def environment():
    import tiktoken
    return {
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "machine": platform.machine(),
        "python_executable_sha256": sha(Path(sys.executable).resolve()),
        "packages": {name: importlib.metadata.version(name)
                     for name in ("mcp", "pydantic", "tiktoken", "regex")},
        "tokenizer_cache": {path.name: sha(path) for path in sorted(
            Path(os.environ["TIKTOKEN_CACHE_DIR"]).glob("*")) if path.is_file()},
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "scope": "This new hosted VM only; no cross-host timing pooling."}


def schedule():
    return [(cohort, round_number, label)
            for cohort in COHORTS
            for round_number, order in enumerate((("baseline", "candidate"), ("candidate", "baseline")))
            for label in order]


def ident(cohort, round_number, label):
    return f"{cohort}-r{round_number}-{label}"


def expected_ids(old, cohort, round_number, configuration):
    ids = list(old["cohorts"][cohort]["paired_selected_query_ids"])
    random.Random(91261 + round_number * 1009 + CONFIGS.index(configuration)).shuffle(ids)
    return ids


def validate_worker(value, old, cohort, round_number, label):
    source = old["baseline"] if label == "baseline" else old["candidate_source"]
    if (value.get("status"), value.get("cohort"), value.get("round"), value.get("label"),
        value.get("runtime_source_sha256"), value.get("dataset_sha256")) != (
            "completed", cohort, round_number, label, source["runtime_sha256"],
            old["cohorts"][cohort]["dataset_sha256"]):
        raise ValueError("Worker status, source, dataset, or axes mismatch")
    if [cell["configuration"] for cell in value["cells"]] != list(CONFIGS):
        raise ValueError("Worker configuration inventory/order mismatch")
    for cell in value["cells"]:
        if [row["query_id"] for row in cell["rows"]] != expected_ids(
                old, cohort, round_number, cell["configuration"]):
            raise ValueError("Missing, duplicated, or reordered query rows")
        for row in cell["rows"]:
            if not re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"]):
                raise ValueError("Invalid complete-payload digest")
            wall = row["wall_ms"]
            if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(wall) or wall < 0:
                raise ValueError("Invalid timing observation")


def quantile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def numeric(values):
    return {"samples": len(values), "p50": quantile(values, .5),
            "p95": quantile(values, .95), "mean": statistics.fmean(values)}


def audit(old):
    workers = {}
    records = []
    for cohort, round_number, label in schedule():
        identity = ident(cohort, round_number, label)
        path = PUBLIC / (identity + ".json")
        value = read(path)
        validate_worker(value, old, cohort, round_number, label)
        workers[cohort, round_number, label] = value
        records.append({"id": identity, "path": str(path.relative_to(ROOT)), "sha256": sha(path), "calls": 512})
    cells, mismatches = [], []
    for cohort in COHORTS:
        for index, config in enumerate(CONFIGS):
            rounds = []
            pooled = {"baseline": [], "candidate": []}
            for round_number in (0, 1):
                a = workers[cohort, round_number, "baseline"]["cells"][index]["rows"]
                b = workers[cohort, round_number, "candidate"]["cells"][index]["rows"]
                for left, right in zip(a, b):
                    if left["payload_sha256"] != right["payload_sha256"]:
                        mismatches.append({"cohort": cohort, "round": round_number,
                            "configuration": config, "query_id": left["query_id"],
                            "baseline": left["payload_sha256"], "candidate": right["payload_sha256"]})
                values = {"baseline": [row["wall_ms"] for row in a], "candidate": [row["wall_ms"] for row in b]}
                for label in pooled:
                    pooled[label].extend(values[label])
                summaries = {label: numeric(data) for label, data in values.items()}
                rounds.append({"round": round_number, **summaries,
                    **{metric + "_change_percent": (summaries["candidate"][metric] /
                        summaries["baseline"][metric] - 1) * 100 for metric in ("p50", "p95")}})
            summaries = {label: numeric(data) for label, data in pooled.items()}
            cells.append({"cohort": cohort, "configuration": config, **summaries, "rounds": rounds,
                **{metric + "_change_percent": (summaries["candidate"][metric] /
                    summaries["baseline"][metric] - 1) * 100 for metric in ("p50", "p95")}})
    improvement = (1 - math.exp(statistics.fmean(
        math.log(cell["candidate"]["p95"] / cell["baseline"]["p95"]) for cell in cells))) * 100
    return {"schema_version": 1, "attempt": ATTEMPT, "status": "completed",
        "workers": records, "calls": 4096, "complete_payload_pairs": 2048,
        "all_payloads_equal": not mismatches, "mismatches": mismatches, "cells": cells,
        "pooled_p95_geomean_improvement_percent": improvement,
        "adverse_cells_over_five_percent": [{"cohort": c["cohort"], "configuration": c["configuration"],
            "p50_change_percent": c["p50_change_percent"], "p95_change_percent": c["p95_change_percent"]}
            for c in cells if c["p50_change_percent"] > 5 or c["p95_change_percent"] > 5],
        "formal_acceptance": False, "fresh_rows_decoded": 0, "audit_retrieval_calls": 0,
        "scope": "All prospective K observations retained. Previous candidate timings are not pooled. Development only; original formal and release gates unchanged."}



def frozen_source():
    """No candidate can execute until a separately committed exact source is bound."""
    if sha(SOURCE_BINDING) != SOURCE_BINDING_SHA:
        raise ValueError("Original frozen K source binding bytes changed")
    value = read(SOURCE_BINDING)
    if (value.get("commit") != "4720728e47d53fc6c345fa89a2b5b739a67a1069"
            or value.get("runtime_sha256") != "90079d629d101370e6960a10e5391265802b1a053f65438e9b667b662638b251"):
        raise ValueError("Development must retain the exact isolated K runtime")
    if value.get("candidate") != "K" or value.get("status") != "frozen-before-any-k-corpus-call":
        raise ValueError("Candidate K has not been frozen before corpus execution")
    for key, length in (("commit", 40), ("runtime_sha256", 64)):
        if not re.fullmatch("[0-9a-f]{" + str(length) + "}", value.get(key, "")):
            raise ValueError("Invalid frozen candidate source identity")
    expected = {module.replace(".", "/") + ".py" for module in CORRECTNESS_MODULES}
    if set(value.get("correctness_files_sha256", {})) != expected:
        raise ValueError("Correctness fixture inventory differs from the registered 13 modules")
    files = value.get("files_sha256")
    if not files or not all(path.startswith("src/memory_book/") and re.fullmatch(r"[0-9a-f]{64}", checksum)
                            for path, checksum in files.items()):
        raise ValueError("Missing exact runtime file inventory")
    return {key: value[key] for key in ("commit", "runtime_sha256", "files_sha256")}


def prepare_references(old):
    """Read nine small pinned Git objects, without checking out historical reports."""
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                    "origin", REFERENCE_COMMIT], cwd=ROOT, check=True)
    directory = STATE / "profile-references"
    directory.mkdir(exist_ok=False)
    manifest_path = old["profile"]["baseline_reference"]
    raw = subprocess.check_output(["git", "show", REFERENCE_COMMIT + ":" + manifest_path], cwd=ROOT)
    if hashlib.sha256(raw).hexdigest() != old["profile"]["baseline_manifest_sha256"]:
        raise ValueError("Saved baseline profile manifest changed")
    (directory / "manifest.json").write_bytes(raw)
    manifest = json.loads(raw)
    if (manifest["runtime_source_sha256"] != old["baseline"]["runtime_sha256"]
            or manifest["script_sha256"] != old["helpers_sha256"]["scripts/round4_development_profile.py"]
            or manifest["status"] != "completed" or manifest["completed_calls"] != 4732):
        raise ValueError("Saved baseline manifest has different source/counts")
    for cell in old["profile"]["baseline_cells"]:
        compressed = subprocess.check_output(["git", "show", REFERENCE_COMMIT + ":" + cell["path"]], cwd=ROOT)
        if len(compressed) != cell["bytes"] or hashlib.sha256(compressed).hexdigest() != cell["sha256"]:
            raise ValueError("Saved baseline compressed cell changed")
        raw = gzip.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != cell["uncompressed_sha256"]:
            raise ValueError("Saved baseline raw cell changed")
        (directory / Path(cell["path"]).name).write_bytes(compressed)


def profile_audit(value, old, reference_values):
    """Compare every saved full-payload digest; never compare profiler latency."""
    expected_cells = [(c, config) for c in COHORTS for config in CONFIGS]
    if (value.get("status") != "completed" or value.get("expected_calls") != 4732
            or value.get("attempted_calls") != 4732 or value.get("completed_calls") != 4732
            or value.get("runtime_source_sha256") != old["candidate_source"]["runtime_sha256"]
            or value.get("script_sha256") != old["helpers_sha256"]["scripts/round4_development_profile.py"]):
        raise ValueError("Incomplete or differently sourced candidate profile")
    if [(c["cohort"], c["configuration"]) for c in value["cells"]] != expected_cells:
        raise ValueError("Profile cell inventory or order changed")
    if len(reference_values) != len(expected_cells):
        raise ValueError("Missing saved baseline reference cells")
    records, mismatches = [], []
    for candidate, baseline in zip(value["cells"], reference_values):
        cohort = candidate["cohort"]
        expected = old["cohorts"][cohort]
        for cell in (candidate, baseline):
            if (cell.get("status") != "completed" or cell.get("cohort") != cohort
                    or cell.get("configuration") != candidate["configuration"]
                    or cell.get("dataset_sha256") != expected["dataset_sha256"]
                    or cell.get("queries") != expected["queries"] or len(cell["rows"]) != expected["queries"]
                    or digest([row["query_id"] for row in cell["rows"]]) != expected["profile_query_order_sha256"]):
                raise ValueError("Profile data, count, or complete query schedule mismatch")
        for left, right in zip(baseline["rows"], candidate["rows"]):
            if not re.fullmatch(r"[0-9a-f]{64}", right["non_timing_payload_sha256"]):
                raise ValueError("Invalid profile full-payload digest")
            if left["non_timing_payload_sha256"] != right["non_timing_payload_sha256"]:
                mismatches.append({"cohort": cohort, "configuration": candidate["configuration"],
                    "query_id": right["query_id"], "baseline": left["non_timing_payload_sha256"],
                    "candidate": right["non_timing_payload_sha256"]})
        records.append({"cohort": cohort, "configuration": candidate["configuration"],
            "queries": expected["queries"], "query_order_sha256": expected["profile_query_order_sha256"],
            "profile_total_seconds_diagnostic_only": candidate["profile_total_seconds"],
            "top_self_diagnostic_only": candidate["top_self"][:10]})
    return {"schema_version": 1, "attempt": ATTEMPT, "calls": 4732,
        "all_full_non_timing_payloads_equal_to_v032_c2": not mismatches,
        "mismatches": mismatches, "cells": records, "speed_claim": False,
        "retrieval_calls_executed_by_audit": 0, "fresh_rows_decoded": 0}


def compress_profile():
    path = PUBLIC / "profile.json"
    if not path.exists():
        return
    raw = path.read_bytes()
    compressed = gzip.compress(raw, mtime=0)
    archive = PUBLIC / "profile.json.gz"
    archive.write_bytes(compressed)
    if gzip.decompress(archive.read_bytes()) != raw:
        raise ValueError("Lossless profile preservation failed")
    save(PUBLIC / "profile-storage.json", {"uncompressed_bytes": len(raw),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_bytes": len(compressed), "compressed_sha256": sha(archive),
        "encoding": "Exact original report bytes, gzip mtime=0; no rows removed."})
    path.unlink()


def profile(old, sources, locomo, binding):
    state = STATE / "profile-state"
    output = PUBLIC / "profile.json"
    if state.exists() or output.exists() or (PUBLIC / "profile.intent.json").exists():
        raise ValueError("The K profile has already started")
    command = [sys.executable, str(ROOT / "scripts/round4_development_profile.py"),
        "--source", str(sources["candidate"] / "src"),
        "--expected-source-sha", old["candidate_source"]["runtime_sha256"],
        "--label", "candidate-k", "--locomo-path", str(locomo),
        "--state", str(state), "--output", str(output)]
    save(PUBLIC / "profile.intent.json", {"status": "started", "created_at": stamp(),
        "argv": command, "expected_calls": 4732, "binding_sha256": sha(PUBLIC / "binding.json"),
        "source": old["candidate_source"], "helper_sha256": old["helpers_sha256"]["scripts/round4_development_profile.py"],
        "baseline_reference": old["profile"], "timeout_seconds": 600})
    publish("bench: claim the complete candidate K profile")
    returncode, failure = None, None
    try:
        with (PUBLIC / "profile.log").open("xb") as log:
            returncode = subprocess.run(command, cwd=ROOT, stdout=log,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                stderr=subprocess.STDOUT, timeout=600).returncode
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)
    save(PUBLIC / "profile.exit.json", {"returncode": returncode, "error": failure,
        "finished_at": stamp(), "output_sha256": sha(output) if output.exists() else None})
    compress_profile()
    publish("bench: preserve complete or interrupted candidate K profile")
    if failure or returncode != 0:
        raise RuntimeError("Candidate K profile did not complete")
    references = []
    for cell in old["profile"]["baseline_cells"]:
        path = STATE / "profile-references" / Path(cell["path"]).name
        if path.stat().st_size != cell["bytes"] or sha(path) != cell["sha256"]:
            raise ValueError("Saved profile reference changed after preflight")
        raw = gzip.decompress(path.read_bytes())
        if hashlib.sha256(raw).hexdigest() != cell["uncompressed_sha256"]:
            raise ValueError("Saved raw profile reference changed after preflight")
        references.append(json.loads(raw))
    value = json.loads(gzip.decompress((PUBLIC / "profile.json.gz").read_bytes()))
    result = profile_audit(value, old, references)
    result.update(profile_storage=read(PUBLIC / "profile-storage.json"),
                  source_binding_sha256=sha(SOURCE_BINDING),
                  binding_sha256=sha(PUBLIC / "binding.json"))
    save(PUBLIC / "profile-audit.json", result)
    publish("bench: preserve saved-reference audit before candidate K paired timing")
    if not result["all_full_non_timing_payloads_equal_to_v032_c2"]:
        raise RuntimeError("Profile payload mismatch; paired timing will not start")


def correctness(candidate):
    modules = list(CORRECTNESS_MODULES)
    identity = frozen_source()
    verify_exact_source(candidate, identity)
    verify_files(read(SOURCE_BINDING)["correctness_files_sha256"], candidate)
    before = full_export_files(candidate)
    save(PUBLIC / "correctness-export.intent.json", {
        "status": "started", "created_at": stamp(), "source_commit": identity["commit"],
        "runtime_sha256": identity["runtime_sha256"], "source_inventory": source_files(candidate),
        "full_export_inventory": before, "modules": modules, "source_binding_sha256": sha(SOURCE_BINDING),
        "policy": "This exact export is used only for the unchanged correctness suite and is retained in full afterward."})
    publish("bench: bind isolated K correctness export before fixtures")
    receipt = PUBLIC / "correctness.json"
    program = ("import json,sys,unittest; from pathlib import Path; import memory_book; "
        "source=Path(sys.argv[3]); "
        "assert Path(memory_book.__file__).resolve().parent == source/'src/memory_book'; "
        "modules=json.loads(sys.argv[1]); suite=unittest.defaultTestLoader.loadTestsFromNames(modules); "
        "assert all(Path(sys.modules[m].__file__).resolve()==source/(m.replace('.','/')+'.py') for m in modules); "
        "expected=suite.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(suite); "
        "Path(sys.argv[2]).write_text(json.dumps(dict(modules=modules,expected=expected,tests=r.testsRun,errors=len(r.errors),"
        "failures=len(r.failures),skipped=len(r.skipped),passed=r.wasSuccessful()),indent=2)+'\\n'); "
        "sys.exit(0 if r.wasSuccessful() and not r.skipped and r.testsRun==expected else 1)")
    env = dict(os.environ, PYTHONPATH=str(candidate / "src") + os.pathsep + str(ROOT),
               PYTHONDONTWRITEBYTECODE="1")
    returncode, failure = None, None
    try:
        with (PUBLIC / "correctness.log").open("xb") as log:
            returncode = subprocess.run([sys.executable, "-c", program, json.dumps(modules), str(receipt),
                str(candidate)], cwd=candidate, env=env, stdout=log,
                stderr=subprocess.STDOUT, timeout=180).returncode
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)
    inventory = correctness_inventory(candidate, identity, before)
    inventory["archive"] = archive_correctness_export(candidate)
    inventory["returncode"], inventory["execution_error"] = returncode, failure
    save(PUBLIC / "correctness-export-audit.json", inventory)
    publish("bench: preserve complete K correctness export outcome and file differences")
    if failure or returncode != 0 or inventory["errors"]:
        raise RuntimeError("Candidate correctness or source/fixture inventory failed")
    verify_files(read(SOURCE_BINDING)["correctness_files_sha256"], candidate)
    return inventory


def prepare(old):
    correctness_source = export_source("correctness", old["candidate_source"])
    correctness(correctness_source)
    sources = {label: export_source(label, old[key])
               for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))}
    save(PUBLIC / "measurement-exports.json", {label: {
        "source_commit": old[key]["commit"], "runtime_sha256": runtime_sha(sources[label]),
        "inventory": source_files(sources[label]), "correctness_export_reused": False}
        for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))})
    publish("bench: bind independent exact K measurement exports before corpus preparation")
    prepare_references(old)
    raw_spec = read(ROOT / "benchmarks/locomo_split.json")
    with urllib.request.urlopen(raw_spec["url"], timeout=60) as response:
        raw = response.read(raw_spec["bytes"] + 1)
    if len(raw) != raw_spec["bytes"] or hashlib.sha256(raw).hexdigest() != raw_spec["sha256"]:
        raise ValueError("Pinned LoCoMo input mismatch")
    locomo = STATE / "locomo10.json"
    locomo.write_bytes(raw)
    sys.path[:0] = [str(sources["baseline"] / "src"), str(ROOT)]
    import memory_book
    from benchmarks.run import engine_source_hash
    from scripts.benchmark_default_recall import dataset
    from memory_book.token_budget import TokenCounter
    if Path(memory_book.__file__).resolve().parent != sources["baseline"] / "src/memory_book":
        raise ValueError("Baseline snapshot builder imported another runtime")
    if engine_source_hash(Path(memory_book.__file__).resolve().parent) != old["baseline"]["runtime_sha256"]:
        raise ValueError("Baseline runtime digest mismatch")
    TokenCounter("cl100k_base").count("Initialize outside timed calls.")
    databases = STATE / "databases"
    databases.mkdir(exist_ok=False)
    cohorts = {}
    for cohort in COHORTS:
        data = dataset(cohort, locomo)
        previous = old["cohorts"][cohort]
        selected = sorted(data.queries, key=lambda c: (
            hashlib.sha256(("round4-native-development-v1/" + c.id).encode()).digest(), c.id))[:128]
        if [case.id for case in selected] != previous["paired_selected_query_ids"]:
            raise ValueError("Registered old query selection changed")
        if len(data.sessions) != previous["sessions"] or data.fingerprint != previous["dataset_sha256"]:
            raise ValueError("Registered old dataset changed")
        target = databases / (cohort + ".db")
        logical = {}
        with memory_book.MemoryBook(target, cache_size=0) as book:
            for session in data.sessions:
                book.ingest(session)
            for table in TABLES:
                rows = [list(row) for row in book.db.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]
                logical[table] = {"rows": len(rows), "sha256": digest(rows)}
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            del rows  # Preparation memory is not a formal worker/resource measurement.
        if any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Source snapshot has a live sidecar")
        cohorts[cohort] = {"dataset_sha256": data.fingerprint, "sessions": len(data.sessions),
            "queries": len(data.queries), "database_sha256": sha(target),
            "database_bytes": target.stat().st_size, "indexed_content": logical,
            "query_ids_sha256": digest([c.id for c in selected])}
    binding = {"schema_version": 1, "attempt": ATTEMPT, "created_at": stamp(),
        "scope_sha256": sha(SCOPE), "script_sha256": sha(Path(__file__)),
        "workflow_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "old_schedule_reference_sha256": sha(OLD), "sources": {label: old[key]
            for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))},
        "source_export_commits": {label: old[key]["commit"] for label, key in (("baseline", "baseline"), ("candidate", "candidate_source"))},
        "source_binding_sha256": sha(SOURCE_BINDING),
        "correctness_export_audit_sha256": sha(PUBLIC / "correctness-export-audit.json"),
        "correctness_export_archive_sha256": sha(PUBLIC / "correctness-export.tar.gz"),
        "measurement_exports_sha256": sha(PUBLIC / "measurement-exports.json"),
        "development_preflight_sha256": sha(PUBLIC / "development-preflight.json"),
        "profile_baseline_references": old["profile"],
        "candidate_correctness_tests_sha256": {str(p.relative_to(sources["candidate"])): sha(p)
            for p in sorted((sources["candidate"] / "tests").rglob("*.py"))},
        "environment": environment(), "cohorts": cohorts,
        "helpers_sha256": old["helpers_sha256"],
        "helper_dependency_sha256": old["helper_dependency_sha256"],
        "worker_order": [ident(*item) for item in schedule()],
        "calls": 4096, "complete_payload_pairs": 2048,
        "snapshot_policy": "New baseline-built immutable bytes shared by both labels; historical database bytes and timing pools remain separate.",
        "profile_calls_expected": 4732, "fresh_rows_decoded": 0, "formal_acceptance": False}
    save(PUBLIC / "binding.json", binding)
    publish("bench: bind candidate K sources environment and new snapshots before timing")
    return sources, locomo, databases, binding


def guards(old, binding, sources, locomo, databases):
    if sha(SOURCE_BINDING) != binding["source_binding_sha256"]:
        raise ValueError("Frozen K source binding changed")
    for filename, key in (("correctness-export-audit.json", "correctness_export_audit_sha256"),
                          ("correctness-export.tar.gz", "correctness_export_archive_sha256"),
                          ("measurement-exports.json", "measurement_exports_sha256"),
                          ("development-preflight.json", "development_preflight_sha256")):
        if sha(PUBLIC / filename) != binding[key]:
            raise ValueError("Bound development preflight evidence changed: " + filename)

    if sha(OLD) != OLD_SHA or sha(SCOPE) != binding["scope_sha256"] or sha(Path(__file__)) != binding["script_sha256"]:
        raise ValueError("K development scope, original binding, or orchestrator changed")
    verify_files(old["helpers_sha256"])
    verify_files(old["helper_dependency_sha256"])
    for label in ("baseline", "candidate"):
        verify_exact_source(sources[label], binding["sources"][label])
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise ValueError("Measurement bytecode-suppression environment changed")
    if environment() != binding["environment"]:
        raise ValueError("Bound environment changed")
    if sha(locomo) != read(ROOT / "benchmarks/locomo_split.json")["sha256"]:
        raise ValueError("Raw input changed")
    for cohort in COHORTS:
        path = databases / (cohort + ".db")
        if sha(path) != binding["cohorts"][cohort]["database_sha256"]:
            raise ValueError("Immutable source snapshot changed")
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Immutable source snapshot has a sidecar")


def run():
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1" or os.environ.get("GITHUB_REF") != "refs/heads/ci/v033-candidate-k-development-1":
        raise RuntimeError("Only the prospectively registered first hosted attempt may run")
    candidate_source = frozen_source()
    prerequisites = verify_development_prerequisites()
    if remote_head() is not None:
        raise RuntimeError("The fixed attempt is already claimed; do not replay")
    if PUBLIC.exists() or STATE.exists():
        raise RuntimeError("K output/state already exists; do not reuse")
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    save(STATE / "publication.json", {"expected_remote": None})
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    save(PUBLIC / "development-preflight.json", prerequisites)
    old = read(OLD)
    old["candidate_source"] = candidate_source
    if sha(OLD) != OLD_SHA:
        raise ValueError("Original I binding bytes changed")
    verify_files(old["helpers_sha256"])
    verify_files(old["helper_dependency_sha256"])
    save(PUBLIC / "attempt.intent.json", {"attempt": ATTEMPT, "status": "started",
        "created_at": stamp(), "workflow_commit": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1, "scope_sha256": sha(SCOPE),
        "candidate": "K", "source_binding_sha256": sha(SOURCE_BINDING),
        "prerequisites": prerequisites,
        "prior_evidence": "J2 completed all 8,828 original profile/paired calls with equal payloads but regressed every timing cell, and is rejected. K source choice excludes that route before any K corpus call. J/I/K timings are never pooled; no failed or unfavorable attempt is replayed.",
        "scope": "New independent old-data diagnostic only; original numerical/formal/release gates unchanged."})
    publish("bench: claim the separately registered candidate K isolated development attempt")
    stage = "prepare"
    try:
        sources, locomo, databases, binding = prepare(old)
        stage = "complete-profile-and-saved-reference-audit"
        guards(old, binding, sources, locomo, databases)
        profile(old, sources, locomo, binding)
        for cohort, round_number, label in schedule():
            stage = ident(cohort, round_number, label)
            guards(old, binding, sources, locomo, databases)
            output = PUBLIC / (stage + ".json")
            state = STATE / "workers" / stage
            if output.exists() or state.exists() or (PUBLIC / (stage + ".intent.json")).exists():
                raise ValueError("Worker was already started")
            identity = binding["sources"][label]
            command = [sys.executable, str(ROOT / "scripts/round4_development_pair.py"), "--worker",
                "--source", str(sources[label] / "src"), "--source-sha", identity["runtime_sha256"],
                "--label", label, "--cohort", cohort, "--round", str(round_number),
                "--db-directory", str(databases), "--locomo-path", str(locomo),
                "--state", str(state), "--output", str(output)]
            save(PUBLIC / (stage + ".intent.json"), {"status": "started", "created_at": stamp(),
                "worker": stage, "binding_sha256": sha(PUBLIC / "binding.json"), "argv": command,
                "expected_calls": 512, "frozen_runtime_origin": identity["commit"],
                "source_export_commit": binding["source_export_commits"][label],
                "snapshot_sha256": binding["cohorts"][cohort]["database_sha256"]})
            publish("bench: claim candidate K worker " + stage)
            returncode, failure = None, None
            try:
                with (PUBLIC / (stage + ".log")).open("xb") as log:
                    returncode = subprocess.run(command, cwd=ROOT, stdout=log,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                        stderr=subprocess.STDOUT, timeout=240).returncode
            except BaseException as error:
                failure = type(error).__name__ + ": " + str(error)
            save(PUBLIC / (stage + ".exit.json"), {"returncode": returncode,
                "error": failure, "finished_at": stamp(),
                "output_sha256": sha(output) if output.exists() else None,
                "policy": "All partial and negative observations are retained; no automatic replay."})
            publish("bench: preserve candidate K worker " + stage)
            if failure or returncode != 0:
                raise RuntimeError("Worker did not complete: " + stage)
            validate_worker(read(output), old, cohort, round_number, label)
        guards(old, binding, sources, locomo, databases)
        stage = "saved-result-audit"
        result = audit(old)
        save(PUBLIC / "paired-audit.json", result)
        save(PUBLIC / "completion.json", {"status": "completed", "created_at": stamp(),
            "attempt": ATTEMPT, "paired_calls": result["calls"], "complete_payload_pairs": 2048,
            "profile_calls": 4732, "all_profile_payloads_equal_to_saved_v032": True,
            "all_payloads_equal": result["all_payloads_equal"], "formal_acceptance": False,
            "source_snapshots_unchanged": True, "fresh_rows_decoded": 0})
        publish("bench: preserve all candidate K observations and saved-result audit")
        if not result["all_payloads_equal"]:
            raise RuntimeError("Complete payload equality failed; no formal acceptance")
    except BaseException as error:
        save(PUBLIC / "failure.json", {"status": "failed_or_incomplete", "stage": stage,
            "created_at": stamp(), "error": type(error).__name__ + ": " + str(error),
            "replay_permitted": False, "formal_acceptance": False})
        if not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve interrupted candidate K recovery evidence")
        raise


def preserve():
    """Workflow always step: save logs/partial evidence without invoking retrieval."""
    if not PUBLIC.exists() or not (STATE / "publication.json").exists():
        print("No new attempt was claimed; nothing to append.")
        return
    runner_log = ROOT / ".artifacts" / (ATTEMPT + "-runner.log")
    if runner_log.exists():
        shutil.copyfile(runner_log, PUBLIC / "runner.log")
    save(PUBLIC / "workflow-outcome.json", {"created_at": stamp(),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "outcome": os.environ.get("RECOVERY_OUTCOME"), "retrieval_calls": 0,
        "scope": "Preservation only. Existing receipts are not overwritten or replayed."})
    if (PUBLIC / "publication-failure.json").exists():
        print("Publication had failed; preserve through artifact upload without retry.")
        return
    publish("bench: preserve K development workflow log and outcome")


class ProtocolTests(unittest.TestCase):
    def test_remote_ref_parser_rejects_wrong_ref_or_multiple_rows(self):
        self.assertIsNone(parse_remote(""))
        value = "a" * 40
        self.assertEqual(parse_remote(value + "\trefs/heads/" + BRANCH), value)
        for raw in (value + "\trefs/heads/unrelated", value + " refs/heads/" + BRANCH + "\n" + value,
                    "not-a-sha refs/heads/" + BRANCH):
            with self.assertRaises(PublicationError):
                parse_remote(raw)

    def test_schedule_is_complete_and_balanced_without_replay(self):
        values = schedule()
        self.assertEqual(len(values), 8)
        self.assertEqual(len(set(values)), 8)
        self.assertEqual([label for _, _, label in values], ["baseline", "candidate", "candidate", "baseline"] * 2)

    def test_quantiles_interpolate_without_discarding_slow_rows(self):
        self.assertEqual(quantile([1, 2, 3, 4, 100], .5), 3)
        self.assertAlmostEqual(quantile([1, 2, 3, 4, 100], .95), 80.8)

    def test_worker_rejects_missing_reordered_and_nonfinite_observations(self):
        old = {"baseline": {"runtime_sha256": "a" * 64},
            "candidate_source": {"runtime_sha256": "b" * 64},
            "cohorts": {"synthetic61": {"dataset_sha256": "c" * 64,
                "paired_selected_query_ids": ["invented-" + str(i) for i in range(128)]}}}
        value = {"status": "completed", "cohort": "synthetic61", "round": 0, "label": "baseline",
            "runtime_source_sha256": "a" * 64, "dataset_sha256": "c" * 64,
            "cells": [{"configuration": config, "rows": [{"query_id": q, "wall_ms": 1.0,
                "payload_sha256": "d" * 64} for q in expected_ids(old, "synthetic61", 0, config)]}
                for config in CONFIGS]}
        validate_worker(value, old, "synthetic61", 0, "baseline")
        for mutation in ("missing", "order", "nan", "hash"):
            damaged = json.loads(json.dumps(value))
            rows = damaged["cells"][0]["rows"]
            if mutation == "missing":
                rows.pop()
            elif mutation == "order":
                rows.reverse()
            elif mutation == "nan":
                rows[0]["wall_ms"] = float("nan")
            else:
                rows[0]["payload_sha256"] = "invalid"
            with self.assertRaises(ValueError):
                validate_worker(damaged, old, "synthetic61", 0, "baseline")


    def test_profile_audit_keeps_mismatch_and_rejects_missing_reference_or_rows(self):
        old = {"baseline": {"runtime_sha256": "a" * 64},
            "candidate_source": {"runtime_sha256": "b" * 64},
            "helpers_sha256": {"scripts/round4_development_profile.py": "c" * 64}, "cohorts": {}}
        cells = []
        for cohort, count in (("synthetic61", 168), ("public1015", 1015)):
            ids = [cohort + "-invented-" + str(i) for i in range(count)]
            old["cohorts"][cohort] = {"queries": count, "dataset_sha256": "d" * 64,
                "profile_query_order_sha256": digest(ids)}
            for config in CONFIGS:
                cells.append({"cohort": cohort, "configuration": config, "queries": count,
                    "status": "completed", "dataset_sha256": "d" * 64, "profile_total_seconds": 1.0,
                    "top_self": [], "rows": [{"query_id": q, "non_timing_payload_sha256": "e" * 64}
                                           for q in ids]})
        value = {"status": "completed", "expected_calls": 4732, "attempted_calls": 4732,
            "completed_calls": 4732, "runtime_source_sha256": "b" * 64, "script_sha256": "c" * 64,
            "cells": json.loads(json.dumps(cells))}
        self.assertTrue(profile_audit(value, old, cells)["all_full_non_timing_payloads_equal_to_v032_c2"])
        value["cells"][0]["rows"][0]["non_timing_payload_sha256"] = "f" * 64
        result = profile_audit(value, old, cells)
        self.assertFalse(result["all_full_non_timing_payloads_equal_to_v032_c2"])
        self.assertEqual(len(result["mismatches"]), 1)
        with self.assertRaises(ValueError):
            profile_audit(value, old, cells[:-1])
        value["cells"][0]["rows"].pop()
        with self.assertRaises(ValueError):
            profile_audit(value, old, cells)

    def test_profile_storage_is_lossless_for_failed_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            raw = b'{"status":"failed","cells":[{"rows":[]}]}\\n'
            (path / "profile.json").write_bytes(raw)
            with patch(__name__ + ".PUBLIC", path):
                compress_profile()
            self.assertFalse((path / "profile.json").exists())
            self.assertEqual(gzip.decompress((path / "profile.json.gz").read_bytes()), raw)
            storage = read(path / "profile-storage.json")
            self.assertEqual(storage["uncompressed_sha256"], hashlib.sha256(raw).hexdigest())



class IsolationTests(unittest.TestCase):
    def invented_sources(self, directory):
        source = directory / "correctness"
        package = source / "src/memory_book"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("VALUE = 7\n")
        (package / "sample.py").write_text("VALUE = 11\n")
        fixture = source / "tests/fixture.json"
        fixture.parent.mkdir()
        fixture.write_text('{"invented": true}\n')
        identity = {"files_sha256": source_files(source), "runtime_sha256": runtime_sha(source)}
        measurement = directory / "measurement"
        shutil.copytree(source, measurement)
        return source, measurement, identity

    def test_added_bytecode_is_recorded_preserved_and_rejected_in_measurement(self):
        import py_compile
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            tested, measured, identity = self.invented_sources(directory)
            before = full_export_files(tested)
            original = tested / "src/memory_book/sample.py"
            py_compile.compile(str(original), doraise=True)
            cache = Path(importlib.util.cache_from_source(str(original)))
            self.assertTrue(cache.is_file())
            evidence = correctness_inventory(tested, identity, before)
            self.assertEqual(evidence["errors"], [])
            self.assertEqual(len(evidence["difference"]["added"]), 1)
            self.assertEqual(evidence["difference"]["missing"], {})
            self.assertEqual(evidence["difference"]["changed"], {})
            with self.assertRaisesRegex(ValueError, "Runtime source changed"):
                verify_exact_source(tested, identity)
            verify_exact_source(measured, identity)
            self.assertEqual(source_files(measured), identity["files_sha256"])
            public = directory / "public"
            public.mkdir()
            with patch(__name__ + ".PUBLIC", public), patch(__name__ + ".ROOT", directory):
                storage = archive_correctness_export(tested)
            self.assertTrue(cache.is_file())
            archive_path = directory / storage["path"]
            self.assertEqual(storage["sha256"], sha(archive_path))
            with tarfile.open(archive_path, "r:gz") as archive:
                member = "correctness-export/" + cache.relative_to(tested).as_posix()
                self.assertEqual(archive.extractfile(member).read(), cache.read_bytes())

    def test_duplicate_cache_tag_is_not_a_real_source_cache_path(self):
        import py_compile
        with tempfile.TemporaryDirectory() as name:
            tested, measured, identity = self.invented_sources(Path(name))
            before = full_export_files(tested)
            source = tested / "src/memory_book/sample.py"
            py_compile.compile(str(source), doraise=True)
            cache = Path(importlib.util.cache_from_source(str(source)))
            bogus = cache.with_name("sample." + sys.implementation.cache_tag
                                    + ".extra." + sys.implementation.cache_tag + ".pyc")
            cache.rename(bogus)
            evidence = correctness_inventory(tested, identity, before)
            self.assertTrue(evidence["errors"])
            self.assertEqual(evidence["generated_bytecode"], {})
            self.assertIn(bogus.relative_to(tested).as_posix(), evidence["difference"]["added"])
            self.assertTrue(bogus.exists())
            verify_exact_source(measured, identity)

    def test_changed_missing_or_unknown_source_is_never_accepted(self):
        for change in ("changed", "missing", "unknown-python", "unknown-binary", "changed-fixture"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as name:
                tested, measured, identity = self.invented_sources(Path(name))
                before = full_export_files(tested)
                source = tested / "src/memory_book/sample.py"
                if change == "changed":
                    source.write_text("VALUE = 99\n")
                elif change == "missing":
                    source.unlink()
                elif change == "unknown-python":
                    (source.parent / "unknown.py").write_text("VALUE = 99\n")
                elif change == "unknown-binary":
                    (source.parent / "unknown.bin").write_bytes(b"invented")
                else:
                    (tested / "tests/fixture.json").write_text('{"invented": false}\n')
                self.assertTrue(correctness_inventory(tested, identity, before)["errors"])
                if change != "changed-fixture":
                    with self.assertRaises(ValueError):
                        verify_exact_source(tested, identity)
                verify_exact_source(measured, identity)
                (measured / "src/memory_book/unknown.py").write_text("VALUE = 99\n")
                with self.assertRaises(ValueError):
                    verify_exact_source(measured, identity)

    def test_missing_source_binding_fails_before_claim_or_evidence_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(__name__ + ".SOURCE_BINDING", Path(directory) / "missing.json"), \
                    patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_REF": "refs/heads/ci/v033-candidate-k-development-1"}), \
                    patch(__name__ + ".remote_head") as remote, \
                    patch(__name__ + ".verify_development_prerequisites") as previous:
                with self.assertRaises(FileNotFoundError):
                    run()
                remote.assert_not_called()
                previous.assert_not_called()

    def test_prior_evidence_failure_stops_before_claim(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_REF": "refs/heads/ci/v033-candidate-k-development-1"}), \
                patch(__name__ + ".frozen_source", return_value={}), \
                patch(__name__ + ".verify_development_prerequisites", side_effect=ValueError("previous mismatch")), \
                patch(__name__ + ".remote_head") as remote:
            with self.assertRaisesRegex(ValueError, "previous mismatch"):
                run()
            remote.assert_not_called()


class PreflightTests(unittest.TestCase):
    def test_review_must_cover_the_exact_source_without_performance_claim(self):
        identity = {"commit": "a" * 40, "runtime_sha256": "b" * 64}
        value = {"status": "accepted-independent-source-review-of-isolated-k-on-i-t1-before-corpus",
                 "reviewed_source_commit": identity["commit"], "runtime_sha256": identity["runtime_sha256"],
                 "performance_accepted": False, "corpus_calls_executed_by_review": 0}
        validate_evidence_value(value, "independent_source_review", identity)
        for field, changed in (("reviewed_source_commit", "c" * 40), ("runtime_sha256", "d" * 64),
                               ("performance_accepted", True), ("corpus_calls_executed_by_review", 1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_evidence_value({**value, field: changed}, "independent_source_review", identity)

    def test_saved_negative_evidence_cannot_be_relabelled_as_acceptance(self):
        value = {"status": "verified-negative-development-result",
                 "source_commit": "910ba8904523ad81cb7d68073af77580942496eb",
                 "calls": 4096, "complete_payload_pairs": 2048, "payload_mismatches": 0,
                 "adverse_cells_over_five_percent": 8, "retrieval_calls_executed_by_audit": 0,
                 "formal_acceptance": False}
        validate_evidence_value(value, "prior_decision", {})
        for field, changed in (("calls", 4095), ("adverse_cells_over_five_percent", 0),
                               ("formal_acceptance", True), ("retrieval_calls_executed_by_audit", 1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_evidence_value({**value, field: changed}, "prior_decision", {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "preserve", "self-test"))
    mode = parser.parse_args().mode
    if mode == "self-test":
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests),
            unittest.defaultTestLoader.loadTestsFromTestCase(IsolationTests),
            unittest.defaultTestLoader.loadTestsFromTestCase(PreflightTests)]))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    elif mode == "preserve":
        preserve()
    else:
        run()
