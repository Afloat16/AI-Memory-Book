"""Prospective Q2 attempt2; strict union of imports and the explicit registry.

A missing exact candidate binding fails before claim or download. One historical
builder creates each new snapshot once. Exact historical persisted-vector
identity gates every query; no original SQLite bytes or timestamps are recreated.
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
import shutil
import sqlite3
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from scripts import round5_q2_compatibility as legacy

ATTEMPT = "round5-q2-recovery-hosted-2"
BRANCH = "validation/v033-q2-recovery-hosted-2"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SCOPE = ROOT / "benchmarks/experiments/round5-q2-recovery-hosted-v2-scope.json"
SOURCE_BINDING = ROOT / "benchmarks/experiments/round5-q2-recovery-source.json"
SOURCE_BINDING_SHA = "c6ae40b490a7e8358c1709dbb7e6a5999bf6756ef37c66da55488d3539e57828"
ORIGINAL_SCOPE = ROOT / "benchmarks/experiments/round5-q2-recovery-hosted-scope.json"
ORIGINAL_SCOPE_SHA = "f893b6197a1c81e93841dbfe8212cf2f1657e24cc1525123966e5b1cb3554b1e"
SCOPE_SHA = "fc7a0f53b371ffdf6039ce0d171c70f152ce0eb66a2d5a28ba94d32b8ba589c9"
LEGACY_SHA = "c3f01a5ae10b40706f4115dd5188a730c84307e62cabdd3324c5eb29c3a38048"
REFERENCE = "43b65c004e1ac1f1d75cf6d1a2421b36e4eab740"
HELPER = "scripts/round4_semantic_compatibility.py"
OLD = "benchmarks/reports/round4-compatibility-final"
COHORTS = ("authored36", "hotpot128")
ENCODERS = ("cl100k_base", "o200k_base")


class PublicationError(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return legacy.file_sha(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return legacy.read_json(path)


def require(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def blob(commit, name):
    return subprocess.check_output(["git", "show", commit + ":" + name], cwd=ROOT, timeout=120)


def fetch(commit):
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected exact commit")
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags", "origin", commit],
                   cwd=ROOT, check=True, timeout=180)


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



def validate_candidate(value):
    require(type(value) is dict and value.get("status") == "frozen-before-q2-recovery",
            "Missing prospective exact Q2 candidate binding")
    require(isinstance(value.get("candidate"), str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value["candidate"]),
            "Missing candidate label")
    for key, count in (("commit", 40), ("runtime_sha256", 64)):
        require(isinstance(value.get(key), str) and re.fullmatch("[0-9a-f]{" + str(count) + "}", value[key]),
                "Invalid exact candidate " + key)
    files = value.get("files_sha256")
    require(type(files) is dict and files, "Missing full source inventory")
    for path, checksum in files.items():
        require(isinstance(path, str) and path.startswith("src/memory_book/")
                and PurePosixPath(path).as_posix() == path and ".." not in PurePosixPath(path).parts
                and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum),
                "Invalid exact source file inventory")
    require("src/memory_book/__init__.py" in files, "Source package missing")
    return {key: value[key] for key in ("candidate", "commit", "runtime_sha256", "files_sha256")}


def candidate_binding():
    # Deliberately first in run(): no claim, source fetch or asset access precedes this.
    value = validate_candidate(read(SOURCE_BINDING))
    require(sha(SOURCE_BINDING) == SOURCE_BINDING_SHA, "Exact selected NO binding changed")
    require(not SOURCE_BINDING.is_symlink()
            and blob("HEAD", SOURCE_BINDING.relative_to(ROOT).as_posix()) == SOURCE_BINDING.read_bytes(),
            "Candidate binding must match its committed Git blob")
    return value


def source_files(directory):
    return {path.relative_to(directory).as_posix(): sha(path)
            for path in sorted((directory / "src").rglob("*")) if path.is_file()}


def export_source(label, identity):
    directory = STATE / "sources" / label
    require(not directory.exists(), "Source export already exists")
    directory.parent.mkdir(parents=True, exist_ok=True)
    fetch(identity["commit"])
    subprocess.run(["git", "worktree", "add", "--no-checkout", "--detach", str(directory), identity["commit"]],
                   cwd=ROOT, check=True, timeout=120)
    subprocess.run(["git", "-C", str(directory), "sparse-checkout", "set", "--cone", "src"],
                   cwd=ROOT, check=True, timeout=120)
    subprocess.run(["git", "-C", str(directory), "read-tree", "-mu", "HEAD"],
                   cwd=ROOT, check=True, timeout=120)
    actual = source_files(directory)
    if "files_sha256" in identity:
        require(actual == identity["files_sha256"], "Candidate full source inventory differs")
    result = {**identity, "source": (directory / "src").relative_to(ROOT).as_posix(),
              "files_sha256": actual}
    verify_source(result)
    return result


def verify_source(identity):
    source = ROOT / identity["source"]
    directory = source.parent
    require(not directory.is_symlink() and not source.is_symlink()
            and not any(path.is_symlink() for path in source.rglob("*")), "Source contains a symlink")
    require(source_files(directory) == identity["files_sha256"], "Full source inventory changed")
    require(subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"]).decode().strip()
            == identity["commit"], "Source checkout HEAD changed")
    legacy.source_identity(source, identity["commit"], identity["runtime_sha256"])


def schedule():
    return [{"index": index + 1, "id": f"{index + 1:02d}-{cohort}-{encoder}-{label}",
             "cohort": cohort, "encoder": encoder, "label": label}
            for index, (cohort, encoder, label) in enumerate(
                (c, e, label) for c in COHORTS for e in ENCODERS for label in ("baseline", "candidate"))]


def historical_metadata(scope):
    """Read only exact old small Git objects; never check out report history."""
    def frozen(name, checksum):
        raw = blob(REFERENCE, name)
        require(hashlib.sha256(raw).hexdigest() == checksum, "Historical object changed: " + name)
        return raw

    paired = legacy.parse_json(frozen(OLD + "/paired-audit.json", legacy.PINS[OLD + "/paired-audit.json"]))
    legacy.parse_json(frozen(OLD + "/ledger-archive.json", legacy.PINS[OLD + "/ledger-archive.json"]))
    authored = read(ROOT / "benchmarks/transfer_cases.json")
    manifest = read(ROOT / "benchmarks/transfer_manifest.json")
    require(sha(ROOT / "benchmarks/transfer_cases.json") == manifest["sha256"],
            "Original authored cases differ")
    hotpot = read(ROOT / "benchmarks/hotpot_manifest.json")
    ids = {"authored36": [query["id"] for domain in authored["domains"] for query in domain["queries"]],
           "hotpot128": hotpot["selected_ids"]}
    historical = {"cohorts": {}, "old_evaluator_files": scope["original_files"]["old_evaluator_sha256"],
                  "model": scope["model"], "old_c2": {}}
    for cohort in COHORTS:
        name = OLD + "/" + cohort + "-preparation.json"
        previous = legacy.parse_json(frozen(name, legacy.PINS[name]))
        registered = scope["cohorts"][cohort]
        require(len(ids[cohort]) == len(set(ids[cohort])) == registered["queries"]
                and all(isinstance(value, str) and value for value in ids[cohort]), "Historical ID matrix differs")
        require(previous["source_sha256"] == scope["sources"]["historical_builder"]["runtime_sha256"]
                and previous["dataset_sha256"] == registered["dataset_sha256"]
                and previous["queries"] == registered["queries"]
                and previous["evaluator_files"] == historical["old_evaluator_files"]
                and digest(previous["model"]) == digest(scope["model"])
                and digest(previous["vectors"]) == digest(registered["historical_vectors"])
                and previous["originals_sha256"] == registered["historical_originals_sha256"],
                "Historical preparation differs from prospective scope")
        historical["cohorts"][cohort] = {
            "query_ids": ids[cohort], "dataset_sha256": previous["dataset_sha256"],
            "preparation": name, "preparation_sha256": legacy.PINS[name],
            "originals_sha256": previous["originals_sha256"], "vectors": previous["vectors"]}
    rows = {}
    for worker in schedule():
        if worker["label"] != "baseline":
            continue
        key = worker["cohort"] + "/" + worker["encoder"]
        name = worker["cohort"] + "-candidate-" + worker["encoder"] + ".json.gz"
        compressed = frozen(OLD + "/" + name, paired["file_sha256"][name])
        compressed_ledger = frozen(OLD + "/" + name + ".attempts.jsonl.gz",
                                  paired["file_sha256"][name + ".attempts.jsonl.gz"])
        report_raw, ledger_raw = gzip.decompress(compressed), gzip.decompress(compressed_ledger)
        require(hashlib.sha256(ledger_raw).hexdigest() == paired["file_sha256"][name + ".attempts.jsonl"],
                "Historical raw ledger differs")
        rows[key] = legacy.audit_report(legacy.parse_json(report_raw), ledger_raw,
            legacy.expected_report(historical, worker, historical=True),
            historical["cohorts"][worker["cohort"]]["query_ids"])
        historical["old_c2"][key] = {
            "report": OLD + "/" + name, "report_sha256": paired["file_sha256"][name],
            "report_bytes": len(compressed), "report_raw_sha256": hashlib.sha256(report_raw).hexdigest(),
            "ledger": OLD + "/" + name + ".attempts.jsonl.gz",
            "ledger_sha256": paired["file_sha256"][name + ".attempts.jsonl.gz"],
            "ledger_bytes": len(compressed_ledger),
            "ledger_raw_sha256": paired["file_sha256"][name + ".attempts.jsonl"]}
    return historical, rows, hotpot


def verify_recovery_registration(scope):
    """Source-only prior-evidence and unchanged operational-registration gate."""
    original_bytes = ORIGINAL_SCOPE.read_bytes()
    require(not ORIGINAL_SCOPE.is_symlink()
            and hashlib.sha256(original_bytes).hexdigest() == ORIGINAL_SCOPE_SHA
            == scope["original_scope"]["sha256"]
            and original_bytes == blob("HEAD", ORIGINAL_SCOPE.relative_to(ROOT).as_posix()),
            "Preserved original scope bytes changed")
    original = json.loads(original_bytes)
    fields = ("sources", "original_files", "model", "dependencies", "environment",
              "cohorts", "assets", "preparation", "queries", "validation")
    require(scope["preserved_operational_fields"] == list(fields)
            and all(scope[name] == original[name] for name in fields),
            "Original Q2 operational fields or gates changed")
    require(scope["attempt"] == ATTEMPT
            and scope["durability"]["result_branch"] == BRANCH
            and scope["durability"]["output"] == PUBLIC.relative_to(ROOT).as_posix() + "/"
            and scope["durability"]["state"] == STATE.relative_to(ROOT).as_posix() + "/",
            "Recovery2 namespace changed")
    require(scope["candidate_binding"]["exact_binding_sha256"] == SOURCE_BINDING_SHA,
            "Recovery2 source-binding pin changed")
    candidate = candidate_binding()
    require(candidate["candidate"] == scope["candidate_binding"]["candidate"]
            and candidate["commit"] == scope["candidate_binding"]["exact_commit"]
            and candidate["runtime_sha256"] == scope["candidate_binding"]["exact_runtime_sha256"]
            and len(candidate["files_sha256"]) == scope["candidate_binding"]["source_file_count"],
            "Recovery2 selected source differs")
    evidence = []
    for item in scope["preexecution_evidence"]:
        fetch(item["commit"])
        content = blob(item["commit"], item["path"])
        require(hashlib.sha256(content).hexdigest() == item["sha256"],
                "Prior Q2 failure/review evidence changed: " + item["path"])
        evidence.append(json.loads(content))
    require(len(evidence) == 2, "Two frozen prior-evidence receipts required")
    failed, independent = evidence
    prior = scope["previous_attempt"]
    boundary = failed["exact_control_flow_boundary"]
    require(failed["status"] == "failed-before-attempt-claim-no-q2-retrieval"
            and failed["run_id"] == prior["run_id"] == 43497153581
            and failed["run_attempt"] == 1
            and failed["workflow_commit"] == prior["workflow_commit"]
            and failed["failure"]["message"] == "Preparation evaluator identity changed"
            and failed["source_binding"]["sha256"] == SOURCE_BINDING_SHA
            and all(type(boundary[name]) is int and boundary[name] == 0 for name in
                    ("retrieval_calls", "index_builds", "query_embedding_inferences",
                     "registered_model_downloads", "registered_dataset_downloads",
                     "fresh_metadata_or_content_reads"))
            and failed["preserved_evidence"]["raw_log_sha256"] == prior["run_log_sha256"],
            "Previous attempt is not the frozen zero-query preclaim failure")
    require(independent["status"] == "confirmed-independent-preclaim-registration-root-cause"
            and independent["reviewed_controller_commit"] == prior["workflow_commit"]
            and independent["historical_reference_commit"] == REFERENCE
            and independent["identity"]["candidate_binding_sha256"] == SOURCE_BINDING_SHA
            and independent["identity"]["scope_sha256"] == ORIGINAL_SCOPE_SHA
            and independent["inventories"]["legacy_helper_closure"]
                == scope["strict_union_repair"]["original_import_closure"]
            and independent["inventories"]["union_historical_and_current_git_blobs"]
                == scope["strict_union_repair"]["expected_union_git_blobs"],
            "Independent root-cause review differs from prospective repair")
    return scope["preexecution_evidence"]


def registered_helper_union(scope):
    """Read every real union member; an expected digest is never a substitute."""
    repair = scope["strict_union_repair"]
    closure = set(legacy.helper_closure())
    registered = scope["original_files"]["old_evaluator_sha256"]
    require(sorted(closure) == repair["original_import_closure"],
            "Original import closure changed")
    names = closure | set(registered)
    expected_blobs = repair["expected_union_git_blobs"]
    require(names == set(expected_blobs), "Frozen union membership changed")
    files, entries = {}, {}
    for name in sorted(names):
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(),
                "Missing or symlink registered helper/input: " + name)
        actual, historical = path.read_bytes(), blob(REFERENCE, name)
        require(actual == historical, "Historical helper/input bytes changed: " + name)
        git_blob = hashlib.sha1(("blob " + str(len(actual)) + "\0").encode() + actual).hexdigest()
        require(git_blob == expected_blobs[name], "Frozen historical Git blob differs: " + name)
        checksum = hashlib.sha256(actual).hexdigest()
        if name in registered:
            require(checksum == registered[name], "Preparation evaluator identity changed: " + name)
        files[name] = checksum
        entries[name] = {"sha256": checksum, "git_blob": git_blob,
                         "in_import_closure": name in closure,
                         "in_explicit_registry": name in registered}
    counts = {"original_closure": len(closure), "explicit_registry": len(registered), "union": len(names)}
    require(counts == repair["expected_counts"], "Frozen helper inventory counts differ")
    proof = {"status": "verified-source-only-union", "counts": counts,
             "scope_only_paths": sorted(set(registered) - closure),
             "historical_reference_commit": REFERENCE, "files": entries,
             "retrieval_calls": 0, "model_or_dataset_downloads": 0,
             "database_builds": 0, "fresh_metadata_or_content_reads": 0}
    require(proof["scope_only_paths"] == repair["scope_only_paths"],
            "Scope-only inventory differs from independent witness")
    return files, proof


def source_preflight():
    """No saved corpus rows, asset access, database construction or remote claim."""
    candidate_binding()
    require(sha(SCOPE) == SCOPE_SHA and sha(ROOT / legacy.SCRIPT) == LEGACY_SHA,
            "Prospective scope or unchanged legacy auditor differs")
    scope = read(SCOPE)
    evidence = verify_recovery_registration(scope)
    fetch(REFERENCE)
    files, proof = registered_helper_union(scope)
    for name in ("scripts/round5_q2_hosted_recovery_v2.py",
                 "tests/test_round5_q2_hosted_recovery_v2.py",
                 ".github/workflows/round5-q2-recovery-hosted-v2.yml",
                 SCOPE.relative_to(ROOT).as_posix(), ORIGINAL_SCOPE.relative_to(ROOT).as_posix(),
                 SOURCE_BINDING.relative_to(ROOT).as_posix()):
        require(not (ROOT / name).is_symlink()
                and (ROOT / name).read_bytes() == blob("HEAD", name),
                "Uncommitted or symlink recovery input: " + name)
        files[name] = sha(ROOT / name)
    proof.update(attempt=ATTEMPT, scope_sha256=SCOPE_SHA,
                 original_scope_sha256=ORIGINAL_SCOPE_SHA,
                 source_binding_sha256=SOURCE_BINDING_SHA, prior_evidence=evidence)
    return scope, files, proof


def check_registry():
    _, _, proof = source_preflight()
    return proof


def static_preflight():
    scope, files, proof = source_preflight()
    historical, rows, hotpot = historical_metadata(scope)
    return scope, files, historical, rows, hotpot, proof


def download(target, url, expected_bytes, expected_sha):
    require(not target.exists() and not target.with_name(target.name + ".partial").exists(),
            "Never reuse a downloaded asset or partial attempt")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    total, value = 0, hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("xb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            require(total <= expected_bytes, "Asset exceeds frozen size")
            value.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    require(total == expected_bytes and value.hexdigest() == expected_sha, "Frozen asset bytes differ")
    temporary.replace(target)


def environment(scope):
    versions = {name: importlib.metadata.version(name) for name in scope["dependencies"]}
    require(versions == scope["dependencies"], "Dependency versions differ from historical pins")
    selected = {key: os.environ.get(key) for key in
                ("PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "ORT_DISABLE_TELEMETRY")}
    require(selected == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "ORT_DISABLE_TELEMETRY": "1"},
            "Process environment differs from the frozen protocol")
    cpu = sorted({line.strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                  if line.startswith(("model name", "flags"))})
    return {"python": sys.version, "python_executable_sha256": sha(Path(sys.executable).resolve()),
            "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "machine": platform.machine(),
            "cpu_identity": cpu, "packages": versions, "environment": selected,
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "tokenizer_cache": {path.name: sha(path) for path in sorted(
                Path(os.environ["TIKTOKEN_CACHE_DIR"]).glob("*")) if path.is_file()}}


def assets(scope, candidate, helpers, historical, hotpot):
    save(PUBLIC / "assets.intent.json", {"status": "started", "created_at": stamp(),
        "model": scope["model"], "parquet_sha256": hotpot["upstream_sha256"],
        "parquet_bytes": hotpot["upstream_bytes"], "candidate_binding_sha256": sha(SOURCE_BINDING),
        "scope": "Exact source exports, pinned asset bytes and reference tokenizer readiness only."})
    publish("bench: claim Q2 exact source and asset preparation")
    sources = {label: export_source(label, identity) for label, identity in (
        ("historical_builder", scope["sources"]["historical_builder"]),
        ("baseline", scope["sources"]["baseline"]), ("candidate", candidate))}
    model = STATE / "model"
    for entry in scope["model"]["files"]:
        url = "https://huggingface.co/" + scope["model"]["repository"] + "/resolve/" + scope["model"]["revision"] + "/" + entry["path"]
        download(model / entry["path"], url, entry["bytes"], entry["sha256"])
    parquet = STATE / "hotpot-validation.parquet"
    download(parquet, hotpot["source_url"], hotpot["upstream_bytes"], hotpot["upstream_sha256"])
    import tiktoken
    for encoder in ENCODERS:
        tiktoken.get_encoding(encoder).encode("Q2 reference tokenizer readiness.", disallowed_special=())
    binding = {"schema_version": 1, "attempt": ATTEMPT, "created_at": stamp(),
        "workflow_commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "scope_sha256": sha(SCOPE), "source_binding_sha256": sha(SOURCE_BINDING),
        "helpers_sha256": helpers, "sources": sources, "environment": environment(scope),
        "model": scope["model"], "model_dir": model.relative_to(ROOT).as_posix(),
        "parquet": {"path": parquet.relative_to(ROOT).as_posix(), "bytes": hotpot["upstream_bytes"],
                    "sha256": hotpot["upstream_sha256"]},
        "old_evaluator_files": historical["old_evaluator_files"],
        "historical_reference_commit": REFERENCE, "historical": historical,
        "workers": schedule(), "calls": 1968, "complete_payload_pairs": 984,
        "snapshot_policy": "New historical-builder databases; old ingestion timestamps and old full-originals hashes are never recreated or substituted.",
        "fresh_rows_decoded": 0, "configured_generative_model_calls": 0, "performance_claim": False}
    save(PUBLIC / "asset-binding.json", binding)
    publish("bench: bind Q2 exact sources assets and environment before index construction")
    return binding


def guards(scope, binding):
    require(sha(SCOPE) == binding["scope_sha256"]
            and sha(SOURCE_BINDING) == binding["source_binding_sha256"], "Scope/source binding changed")
    for name, checksum in binding["helpers_sha256"].items():
        require(sha(ROOT / name) == checksum, "Helper/input changed: " + name)
    for source in binding["sources"].values():
        verify_source(source)
    require(digest(environment(scope)) == digest(binding["environment"]), "Bound environment changed")
    for entry in binding["model"]["files"]:
        path = ROOT / binding["model_dir"] / entry["path"]
        require(path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"], "Model bytes changed")
    parquet = binding["parquet"]
    require((ROOT / parquet["path"]).stat().st_size == parquet["bytes"]
            and sha(ROOT / parquet["path"]) == parquet["sha256"], "Parquet bytes changed")
    for cohort in binding.get("cohorts", {}).values():
        path = ROOT / cohort["database"]
        require(sha(path) == cohort["database_sha256"], "Immutable new source database changed")
        require(not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")),
                "Immutable new source database has a sidecar")
        validate_database(legacy.database_identity(path), cohort)
        require(sha(ROOT / cohort["preparation"]) == cohort["preparation_sha256"], "New preparation changed")


def validate_database(actual, cohort):
    require(type(actual.get("cache_rows")) is int and actual["cache_rows"] == 0,
            "Unexpected persisted result cache")
    require(actual["originals_sha256"] == cohort["originals_sha256"]
            and digest(actual["vectors"]) == digest(cohort["vectors"]), "New originals/vector identity changed")


def validate_preparation(value, actual, registered, scope):
    """The old original hash is recorded separately; complete vectors must match."""
    require(value["source_sha256"] == scope["sources"]["historical_builder"]["runtime_sha256"]
            and value["dataset_sha256"] == registered["dataset_sha256"]
            and type(value["queries"]) is int and value["queries"] == registered["queries"]
            and value["evaluator_files"] == scope["original_files"]["old_evaluator_sha256"]
            and value["ort_disable_telemetry"] == "1"
            and digest(value["model"]) == digest(scope["model"]), "New preparation provenance differs")
    index = value["semantic_index"]
    require(type(index["inference_threads"]) is int and index["inference_threads"] == 1
            and index["model_fingerprint"] == registered["historical_vectors"]["model_fingerprint"]
            and index["runtime"] == {name: scope["dependencies"][name]
                                    for name in ("onnxruntime", "tokenizers", "numpy")},
            "Builder model/runtime/thread configuration differs")
    require(digest(value["vectors"]) == digest(registered["historical_vectors"])
            and digest(actual["vectors"]) == digest(registered["historical_vectors"]),
            "Reconstructed persisted vectors do not exactly match historical identity; stop before queries")
    require(isinstance(value["originals_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["originals_sha256"]),
            "Invalid new originals digest")
    validate_database(actual, value)


def compress_ledgers():
    for path in sorted(PUBLIC.glob("*.json.gz.attempts.jsonl")):
        compressed = path.with_name(path.name + ".gz")
        raw = path.read_bytes()
        if compressed.exists():
            require(gzip.decompress(compressed.read_bytes()) == raw, "Preserved ledger bytes changed")
        else:
            with compressed.open("xb") as stream:
                stream.write(gzip.compress(raw, mtime=0))
                stream.flush()
                os.fsync(stream.fileno())


def run_stage(stage, command, timeout):
    """The caller has already published intent; preserve any exit before auditing."""
    log = PUBLIC / (stage + ".log.partial")
    returncode, error_text = None, None
    try:
        with log.open("xb") as stream:
            returncode = subprocess.run(command, cwd=ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", ORT_DISABLE_TELEMETRY="1"),
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout).returncode
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as error:
        error_text = type(error).__name__ + ": " + str(error)
    if returncode == 0 and error_text is None:
        log.rename(PUBLIC / (stage + ".log"))
    compress_ledgers()
    save(PUBLIC / (stage + ".exit.json"), {"returncode": returncode, "error": error_text,
        "finished_at": stamp(), "available_file_sha256": {
            path.name: sha(path) for path in sorted(PUBLIC.glob(stage + "*")) if path.is_file()},
        "policy": "This stage is never retried; all incomplete/negative observations remain preserved."})
    publish("bench: preserve Q2 stage output " + stage)
    require(returncode == 0 and error_text is None, "Q2 stage did not complete: " + stage)


def helper_command(mode, binding, source_label, cohort, state, output):
    source = binding["sources"][source_label]
    return [sys.executable, "-u", str(ROOT / HELPER), mode, "--source", str(ROOT / source["source"]),
            "--expected-source-sha", source["runtime_sha256"], "--state", str(state),
            "--output", str(output), "--cohort", cohort, "--model-dir", str(ROOT / binding["model_dir"]),
            "--hotpot-parquet", str(ROOT / binding["parquet"]["path"])]


def prepare_snapshots(scope, binding):
    cohorts = {}
    for cohort in COHORTS:
        stage = "prepare-" + cohort
        guards(scope, binding)
        state, output = STATE / "prepare" / cohort, PUBLIC / (stage + ".json")
        require(not state.exists() and not output.exists(), "Preparation already started")
        command = helper_command("prepare", binding, "historical_builder", cohort, state, output)
        save(PUBLIC / (stage + ".intent.json"), {"status": "started", "created_at": stamp(),
            "argv": command, "asset_binding_sha256": sha(PUBLIC / "asset-binding.json"),
            "expected_historical_vectors": scope["cohorts"][cohort]["historical_vectors"],
            "builds_permitted": 1, "retrieval_calls_permitted": 0})
        publish("bench: claim once-only Q2 snapshot construction " + cohort)
        run_stage(stage, command, scope["preparation"]["timeout_seconds_per_cohort"])
        audit = {"status": "failed", "cohort": cohort, "created_at": stamp()}
        try:
            value = read(output)
            require(value["cohort"] == cohort, "Prepared cohort differs")
            path = state / "prepared.db"
            actual = legacy.database_identity(path)
            require(not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")),
                    "New prepared database has a sidecar")
            audit.update(new_database_sha256=sha(path), new_database_bytes=path.stat().st_size,
                         new_identity=actual, historical_originals_sha256=scope["cohorts"][cohort]["historical_originals_sha256"],
                         historical_vectors=scope["cohorts"][cohort]["historical_vectors"])
            validate_preparation(value, actual, scope["cohorts"][cohort], scope)
            cohorts[cohort] = {**binding["historical"]["cohorts"][cohort],
                "preparation": output.relative_to(ROOT).as_posix(), "preparation_sha256": sha(output),
                "database": path.relative_to(ROOT).as_posix(), "database_sha256": sha(path),
                "database_bytes": path.stat().st_size, "originals_sha256": value["originals_sha256"],
                "vectors": value["vectors"],
                "historical_originals_sha256": scope["cohorts"][cohort]["historical_originals_sha256"]}
            audit.update(status="passed", exact_historical_vectors=True,
                         original_database_restored=False, timestamp_rewrite_permitted=False)
        except BaseException as error:
            audit["error"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            save(PUBLIC / (stage + ".audit.json"), audit)
            publish("bench: preserve Q2 new snapshot identity audit " + cohort)
        # Guard every already-prepared source while building the other cohort.
        binding = {**binding, "cohorts": dict(cohorts)}
    require(set(cohorts) == set(COHORTS), "Both snapshots must pass before any query")
    save(PUBLIC / "binding.json", binding)
    publish("bench: bind both new Q2 snapshots before the first query")
    return binding

def worker(scope, binding, entry, historical_rows, baseline_rows):
    stage = entry["id"]
    guards(scope, binding)
    cohort = binding["cohorts"][entry["cohort"]]
    state = STATE / "workers" / stage
    output = PUBLIC / (stage + ".json.gz")
    require(not state.exists() and not output.exists()
            and not (PUBLIC / (stage + ".intent.json")).exists(), "Worker already started")
    database = state / (entry["label"] + ".db")
    legacy.backup_database(ROOT / cohort["database"], database)
    before = legacy.database_identity(database)
    validate_database(before, cohort)
    command = helper_command("worker", binding, entry["label"], entry["cohort"], state, output)
    command += ["--label", entry["label"], "--preparation", str(ROOT / cohort["preparation"]),
                "--tokenizer", entry["encoder"]]
    save(PUBLIC / (stage + ".intent.json"), {"status": "started", "created_at": stamp(), "worker": entry,
        "binding_sha256": sha(PUBLIC / "binding.json"), "argv": command,
        "expected_calls": len(cohort["query_ids"]) * 3,
        "new_source_database_sha256": cohort["database_sha256"],
        "worker_database_before": before, "worker_database_bytes_sha256_before": sha(database),
        "policy": "Independent SQLite backup of the same once-built persisted vectors; no reindex or replay."})
    publish("bench: claim Q2 worker " + stage)
    run_stage(stage, command, scope["queries"]["timeout_seconds_per_worker"])
    audit = {"status": "failed", "worker": entry, "created_at": stamp()}
    rows = None
    try:
        ledger = output.with_name(output.name + ".attempts.jsonl")
        compressed = ledger.with_name(ledger.name + ".gz")
        raw = ledger.read_bytes()
        require(gzip.decompress(compressed.read_bytes()) == raw, "Worker ledger gzip is not lossless")
        rows = legacy.audit_report(read(output), raw, legacy.expected_report(binding, entry), cohort["query_ids"])
        after = legacy.database_identity(database)
        validate_database(after, cohort)
        guards(scope, binding)
        key = entry["cohort"] + "/" + entry["encoder"]
        comparator = historical_rows[key] if entry["label"] == "baseline" else baseline_rows[key]
        legacy.equal_payloads(rows, comparator)
        audit.update(status="passed", calls=len(rows),
            comparator="saved historical v032 C2" if entry["label"] == "baseline" else "this attempt's baseline",
            full_payload_and_context_equal=True, worker_database_after=after,
            worker_database_bytes_sha256_after=sha(database), report_sha256=sha(output),
            report_raw_sha256=hashlib.sha256(gzip.decompress(output.read_bytes())).hexdigest(),
            ledger_raw_sha256=hashlib.sha256(raw).hexdigest(), ledger_gzip_sha256=sha(compressed))
    except BaseException as error:
        audit["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        save(PUBLIC / (stage + ".audit.json"), audit)
        publish("bench: preserve strict Q2 worker audit " + stage)
    return rows


def run():
    candidate = candidate_binding()
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/v033-q2-recovery-hosted-2",
            "Only the registered first hosted Q2 attempt may execute")
    require(not PUBLIC.exists() and not STATE.exists() and remote_head() is None,
            "Fixed Q2 attempt already exists; no replay")
    scope, helpers, historical, historical_rows, hotpot, helper_proof = static_preflight()
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    save(STATE / "publication.json", {"expected_remote": None})
    save(PUBLIC / "registered-helper-union.json", helper_proof)
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    save(PUBLIC / "attempt.intent.json", {"status": "started", "created_at": stamp(),
        "attempt": ATTEMPT, "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1,
        "workflow_commit": os.environ["GITHUB_SHA"], "scope_sha256": sha(SCOPE),
        "candidate": candidate, "candidate_binding_sha256": sha(SOURCE_BINDING),
        "helpers_sha256": helpers, "historical": historical, "worker_order": schedule(),
        "registered_helper_union_sha256": sha(PUBLIC / "registered-helper-union.json"),
        "previous_failed_attempt": scope["previous_attempt"],
        "calls_permitted": 1968, "pairs_expected": 984, "fresh_rows_decoded": 0,
        "original_database_restored": False, "performance_claim": False})
    publish("bench: claim separately identified Q2 reconstruction before assets or inference")
    stage = "assets"
    try:
        binding = assets(scope, candidate, helpers, historical, hotpot)
        stage = "once-only-snapshot-construction"
        binding = prepare_snapshots(scope, binding)
        baseline_rows, calls, pairs = {}, 0, 0
        for entry in schedule():
            stage = entry["id"]
            rows = worker(scope, binding, entry, historical_rows, baseline_rows)
            calls += len(rows)
            key = entry["cohort"] + "/" + entry["encoder"]
            if entry["label"] == "baseline":
                baseline_rows[key] = rows
            else:
                pairs += len(rows)
        stage = "saved-result-audit"
        guards(scope, binding)
        require((calls, pairs, len(baseline_rows)) == (1968, 984, 4), "Incomplete Q2 matrix")
        # Re-audit the saved matrix, without another runtime invocation.
        for entry in schedule():
            cohort = binding["cohorts"][entry["cohort"]]
            output = PUBLIC / (entry["id"] + ".json.gz")
            ledger = output.with_name(output.name + ".attempts.jsonl.gz")
            rows = legacy.audit_report(read(output), gzip.decompress(ledger.read_bytes()),
                                       legacy.expected_report(binding, entry), cohort["query_ids"])
            key = entry["cohort"] + "/" + entry["encoder"]
            legacy.equal_payloads(rows, historical_rows[key] if entry["label"] == "baseline" else baseline_rows[key])
        save(PUBLIC / "completion.json", {"status": "completed", "created_at": stamp(), "attempt": ATTEMPT,
            "calls": calls, "complete_payload_pairs": pairs, "baseline_calls_equal_to_saved_C2": 984,
            "candidate_calls_equal_to_new_baseline": 984, "all_invariant_errors": 0,
            "both_new_persisted_vector_identities_equal_history": True,
            "new_source_databases_unchanged": True, "original_database_restored": False,
            "configured_generative_model_calls": 0, "fresh_rows_decoded": 0,
            "performance_claim": False, "formal_or_release_acceptance": False,
            "limits": "Historical compatibility only. New full-originals hashes identify new ingestion timestamps; no claim that the lost old SQLite bytes were restored."})
        publish("bench: preserve complete Q2 saved-result compatibility audit")
    except BaseException as error:
        partials = [*STATE.glob("model/**/*.partial"), *STATE.glob("*.parquet.partial")]
        save(PUBLIC / "failure.json", {"status": "failed_or_incomplete", "stage": stage,
            "created_at": stamp(), "error": type(error).__name__ + ": " + str(error),
            "partial_asset_metadata": {path.relative_to(STATE).as_posix(): {
                "bytes": path.stat().st_size, "sha256": sha(path)} for path in partials if path.is_file()},
            "replay_permitted": False, "threshold_relaxation_permitted": False,
            "original_database_restored": False, "formal_or_release_acceptance": False})
        if not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve failed or interrupted Q2 reconstruction")
        raise


def preserve():
    """Always-step preservation performs no asset download, database build or query."""
    if not PUBLIC.exists() or not (STATE / "publication.json").exists():
        return
    log = ROOT / ".artifacts" / (ATTEMPT + "-runner.log")
    if log.exists():
        shutil.copyfile(log, PUBLIC / "runner.log")
    try:
        compress_ledgers()
    except BaseException as error:
        save(PUBLIC / "preservation-error.json", {"error": type(error).__name__ + ": " + str(error)})
    save(PUBLIC / "workflow-outcome.json", {"created_at": stamp(),
        "outcome": os.environ.get("Q2_OUTCOME"), "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "scope": "Preservation only; zero inference/retrieval calls in this step."})
    if not (PUBLIC / "publication-failure.json").exists():
        publish("bench: preserve Q2 workflow logs and available partial evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "check-binding", "check-registry", "preserve"))
    mode = parser.parse_args().mode
    if mode == "run":
        run()
    elif mode == "check-registry":
        print(json.dumps(check_registry(), sort_keys=True))
    elif mode == "check-binding":
        value = candidate_binding()
        print(json.dumps({"candidate": value["candidate"], "source_commit": value["commit"],
                          "candidate_binding_sha256": sha(SOURCE_BINDING),
                          "asset_downloads": 0, "claims": 0}))
    else:
        preserve()
