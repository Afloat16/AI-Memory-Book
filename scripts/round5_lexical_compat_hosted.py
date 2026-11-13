"""Durable orchestration of the unchanged historical Hotpot256 lexical helper.

This module imports no product runtime and never selects a new cohort. The
registered helper owns data conversion, retrieval, timing and acceptance.
Staging CI uses artificial fixtures only; run requires a committed selection.
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
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_compatibility as original

ATTEMPT = "round5-lexical-compat-hosted-1"
BRANCH = "validation/v033-lexical-compat-hosted-1"
TRIGGER = "refs/heads/ci/v033-lexical-compat-hosted-1"
CONTROL = "9665e633d203e373e02d1e6b9ef259e7e51565e5"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SELECTION = ROOT / "benchmarks/experiments/round5-selected-runtime.json"
SCOPE = ROOT / "benchmarks/experiments/round5-lexical-compat-hosted-scope.json"
BINDING = ROOT / "benchmarks/experiments/round5-compatibility-binding.json"
PARQUET = STATE / "input/hotpot-validation.parquet"
PREPARATION = PUBLIC / "preparation.json"
DATABASE = STATE / "preparation/prepared.db"
INTENT = PUBLIC / "execution.intent.json"
FILES = ("scripts/round5_lexical_compat_hosted.py",
    "tests/test_round5_lexical_compat_hosted.py",
    ".github/workflows/round5-lexical-compat-hosted.yml",
    "benchmarks/experiments/round5-lexical-compat-hosted-scope.json")
BASELINE = {"commit": original.BASELINE, "runtime_sha256": original.BASELINE_HASH}
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


class PublicationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def journal(value):
    path = STATE / "publication.json"
    temporary = path.with_suffix(".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, timeout=120)


def text_git(*arguments):
    return git(*arguments).decode().strip()


def committed(path):
    require(Path(path).read_bytes() == git("show", "HEAD:" + relative(path)),
        "Commit exact input before execution: " + relative(path))


def valid_hex(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def safe_path(value, prefix):
    return (type(value) is str and value.startswith(prefix)
        and PurePosixPath(value).as_posix() == value
        and ".." not in PurePosixPath(value).parts)


def validate_selection(value):
    require(type(value) is dict and type(value.get("schema_version")) is int
        and value["schema_version"] == 1
        and value.get("status") == "selected-after-development-before-final-evaluation",
        "A reviewed committed final runtime selection is required")
    require(value.get("baseline") == BASELINE, "Released v0.3.2 baseline changed")
    candidate = value.get("candidate")
    require(type(candidate) is dict and set(candidate) == {"commit", "runtime_sha256"}
        and valid_hex(candidate.get("commit"), HEX40)
        and valid_hex(candidate.get("runtime_sha256"), HEX64), "Invalid candidate identity")
    files = value.get("candidate_files_sha256")
    require(type(files) is dict and files and all(safe_path(path, "src/memory_book/")
        and valid_hex(checksum, HEX64) for path, checksum in files.items()),
        "Complete candidate source inventory is required")
    for key in ("development_evidence", "independent_source_review"):
        items = value.get(key)
        require(type(items) is list and items, "Missing final-selection evidence: " + key)
        for item in items:
            require(type(item) is dict and set(item) == {"commit", "path", "sha256"}
                and valid_hex(item.get("commit"), HEX40)
                and safe_path(item.get("path"), "benchmarks/reports/")
                and valid_hex(item.get("sha256"), HEX64), "Invalid immutable evidence")
    require(all(value.get(key) is False for key in
        ("fresh_metadata_selected", "fresh_content_decoded", "formal_measurement_started")),
        "Select the final runtime before fresh/formal execution")
    return value


def parse_remote(raw):
    fields = raw.split()
    if not fields:
        return None
    if (len(fields) != 2 or fields[1] != "refs/heads/" + BRANCH
            or not valid_hex(fields[0], HEX40)):
        raise PublicationError("Unexpected result-ref response")
    return fields[0]


def remote_head():
    return parse_remote(text_git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def allowed(path):
    return path.startswith(relative(PUBLIC) + "/") or path == relative(BINDING)


def publish(message):
    """One non-force push/readback; journal only verified publication heads."""
    expected = read(STATE / "publication.json")["expected_remote"]
    marker = PUBLIC / "publication-failure.json"
    if marker.exists():
        raise PublicationError("Publication already failed; artifact preservation only")
    parent, head, observed = None, None, None
    try:
        parent = text_git("rev-parse", "HEAD")
        if remote_head() != expected:
            raise PublicationError("Result ref was claimed or advanced by another writer")
        if expected is not None and parent != expected:
            raise PublicationError("Local ancestry differs from the last verified publication")
        if text_git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged files")
        targets = [relative(PUBLIC)]
        if BINDING.exists():
            targets.append(relative(BINDING))
        subprocess.run(["git", "add", "--sparse", "--", *targets], cwd=ROOT, check=True)
        staged = text_git("diff", "--cached", "--name-only").splitlines()
        if not staged or not all(allowed(path) for path in staged):
            raise PublicationError("Missing or unrelated publication files")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = text_git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        observed = remote_head()
        if pushed.returncode or observed != head:
            raise PublicationError("Push/readback did not identify the exact new commit; returncode="
                + str(pushed.returncode))
        journal({"expected_remote": head})
        event = {"at": stamp(), "expected_previous": expected, "local_parent": parent,
            "published_commit": head, "observed_remote": observed, "message": message}
        append(PUBLIC / "publication-events.jsonl", event)
        print(json.dumps(event), flush=True)
        return head
    except BaseException as error:
        if not marker.exists():
            save(marker, {"at": stamp(), "expected_previous": expected,
                "local_parent": parent, "local_commit": head, "observed_remote": observed,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No automatic push or stage retry; keep artifact evidence."})
        raise


def fetch(commit):
    require(valid_hex(commit, HEX40), "Fetch only exact commits")
    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
        "origin", commit], cwd=ROOT, check=True, timeout=120)


def inventory(directory):
    result = {}
    for path in sorted((Path(directory) / "src").rglob("*")):
        require(not path.is_symlink(), "Symlinks are outside the exact runtime inventory")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = sha(path)
    return result


def prepare_source(label, identity, expected_files=None):
    fetch(identity["commit"])
    location = STATE / "sources" / label
    location.parent.mkdir(parents=True, exist_ok=True)
    require(not location.exists(), "Never reuse a source export")
    subprocess.run(["git", "worktree", "add", "--no-checkout", "--detach",
        str(location), identity["commit"]], cwd=ROOT, check=True)
    subprocess.run(["git", "-C", str(location), "sparse-checkout", "set", "src"], check=True)
    subprocess.run(["git", "-C", str(location), "read-tree", "-mu", "HEAD"], check=True)
    actual = inventory(location)
    expected = {}
    for entry in git("ls-tree", "-r", "-z", identity["commit"], "--", "src").decode().split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, _ = metadata.split()
        require(kind == "blob" and mode in ("100644", "100755"), "Unexpected runtime Git object")
        expected[name] = digest(git("show", identity["commit"] + ":" + name))
    require(actual and actual == expected, "Runtime inventory differs from exact committed bytes")
    if expected_files is not None:
        require(actual == expected_files, "Final candidate inventory differs from selection")
    require(original.source(location / "src") == identity, "Runtime identity/provenance differs")
    return {"source": str(location / "src"), "files_sha256": actual, "identity": identity}


def verify_registration(scope, selection):
    """Fetch only historical identities; never invoke a selector or load data."""
    from scripts import round4_data
    old = read(ROOT / original.OLD_BINDING)
    commits = {CONTROL, original.PLAN_COMMIT, original.ADDENDUM_COMMIT,
        original.C_SCOPE_COMMIT, original.D_SCOPE_COMMIT,
        round4_data.PLAN_COMMIT, round4_data.ADDENDUM_COMMIT,
        round4_data.COUNTING_ADDENDUM_COMMIT, round4_data.BASELINE,
        old["evaluator_commit"], old["baseline"]["commit"], old["candidate"]["commit"]}
    commits.update(item["commit"] for key in ("development_evidence", "independent_source_review")
                   for item in selection[key])
    for commit in sorted(commits):
        fetch(commit)
    materialized = {}
    for name, checksum in old["evaluator_files"].items():
        path = ROOT / name
        if not path.exists():
            require(safe_path(name, "benchmarks/reports/") and name.endswith(".json"),
                "Only registered source-free historical report objects may be materialized")
            raw = git("show", old["evaluator_commit"] + ":" + name)
            require(digest(raw) == checksum, "Historical report checksum differs")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            materialized[name] = checksum
        require(sha(path) == checksum, "Historical evaluator bytes changed: " + name)
    for key in ("development_evidence", "independent_source_review"):
        for item in selection[key]:
            require(digest(git("show", item["commit"] + ":" + item["path"])) == item["sha256"],
                "Final-selection evidence bytes differ")
    files = original.registry()
    for name, checksum in files.items():
        require(digest(git("show", CONTROL + ":" + name)) == checksum,
            "Original compatibility registration changed: " + name)
    original.registered()
    round4_data.registered_inputs(ROOT / original.OLD_BINDING)
    require(original.schedule() == scope["schedule"], "Original worker schedule differs")
    save(PUBLIC / "registration.json", {"registry_sha256": files,
        "materialized_source_free_reports": materialized,
        "fetch_commits": sorted(commits), "retrieval_calls_executed": 0})
    return files


def child_environment():
    return dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")


def environment(scope):
    versions = {name: importlib.metadata.version(name) for name in scope["environment"]["packages"]}
    require(versions == scope["environment"]["packages"], "Registered dependency versions differ")
    return {"host": original.host_identity(), "packages": versions,
        "python_executable_sha256": sha(Path(sys.executable).resolve()),
        "child_python_flags": {key: child_environment()[key]
            for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED")}}


def preserve_worker_bytes(output):
    """Keep original gzip output and losslessly archive any complete/partial ledger."""
    result = {"files": {}}
    candidates = (output, output.with_name(output.name + ".partial"))
    for path in candidates:
        if path.exists():
            raw = path.read_bytes()
            row = {"bytes": len(raw), "sha256": digest(raw)}
            try:
                decoded = gzip.decompress(raw)
                row.update(uncompressed_bytes=len(decoded), uncompressed_sha256=digest(decoded))
            except (OSError, EOFError) as error:
                row["gzip_error"] = type(error).__name__ + ": " + str(error)
            result["files"][path.name] = row
    ledger = output.with_name(output.name + ".attempts.jsonl")
    compressed = ledger.with_suffix(ledger.suffix + ".gz")
    if ledger.exists():
        require(not compressed.exists(), "Never overwrite an archived attempt ledger")
        raw = ledger.read_bytes()
        packed = gzip.compress(raw, mtime=0)
        require(gzip.decompress(packed) == raw, "Lossless ledger compression failed")
        with compressed.open("xb") as stream:
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())
        require(compressed.read_bytes() == packed, "Archived ledger readback differs")
        result["files"][compressed.name] = {"bytes": len(packed), "sha256": digest(packed),
            "uncompressed_bytes": len(raw), "uncompressed_sha256": digest(raw)}
        ledger.unlink()
    elif compressed.exists():
        packed = compressed.read_bytes()
        raw = gzip.decompress(packed)
        result["files"][compressed.name] = {"bytes": len(packed), "sha256": digest(packed),
            "uncompressed_bytes": len(raw), "uncompressed_sha256": digest(raw)}
    return result


def run_stage(name, command, timeout, outputs=(), worker_output=None):
    """Claim once, execute once, preserve every outcome before continuation."""
    save(PUBLIC / (name + ".remote-intent.json"), {"at": stamp(), "status": "started-before-launch",
        "argv": command, "timeout_seconds": timeout,
        "expected_publication_parent": read(STATE / "publication.json")["expected_remote"],
        "binding_sha256": sha(BINDING) if BINDING.exists() else None,
        "child_python_flags": {key: child_environment()[key]
            for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED")},
        "replay_permitted": False})
    publish("bench: claim historical lexical " + name)
    returncode, error, storage = None, None, None
    try:
        with (PUBLIC / (name + ".log")).open("xb") as log:
            returncode = subprocess.run(command, cwd=ROOT, env=child_environment(),
                stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
    except BaseException as failure:
        error = type(failure).__name__ + ": " + str(failure)
    if worker_output is not None:
        try:
            storage = preserve_worker_bytes(worker_output)
        except BaseException as failure:
            error = (error + "; " if error else "") + "preservation: " + type(failure).__name__ + ": " + str(failure)
    missing = [relative(path) for path in outputs if not path.is_file()]
    if missing and not error:
        error = "Required outputs are missing: " + ", ".join(missing)
    save(PUBLIC / (name + ".exit.json"), {"at": stamp(), "returncode": returncode,
        "error": error, "outputs_sha256": {relative(path): sha(path) for path in outputs if path.is_file()},
        "worker_storage": storage, "replay_permitted": False})
    publish("bench: preserve historical lexical " + name + " outcome")
    if returncode != 0 or error is not None:
        raise RuntimeError("Historical lexical stage failed: " + name)


def helper(mode, *arguments):
    return [sys.executable, "-B", "scripts/round5_compatibility.py", mode, *map(str, arguments)]


def guards(frozen, scope, sources, *, prepared=False, execution=False):
    for name, checksum in frozen["controller_files_sha256"].items():
        require(sha(ROOT / name) == checksum, "Controller/selection changed: " + name)
    for name, checksum in frozen["registry_sha256"].items():
        require(sha(ROOT / name) == checksum, "Original compatibility helper/input changed: " + name)
    for item in sources.values():
        src = Path(item["source"])
        require(inventory(src.parent) == item["files_sha256"], "Unknown or changed runtime files")
        require(original.source(src) == item["identity"], "Runtime source identity changed")
    require(environment(scope) == frozen["environment"], "Hosted environment changed")
    bound = original.binding(BINDING)
    require(bound["sources"] == {name: item["identity"] for name, item in sources.items()},
        "Compatibility binding refers to another selection")
    if prepared:
        info = read(PREPARATION)
        require(sha(PARQUET) == scope["input"]["upstream_sha256"]
            and PARQUET.stat().st_size == scope["input"]["upstream_bytes"], "Pinned Parquet changed")
        require(info["binding_sha256"] == sha(BINDING) and info["source"] == BASELINE
            and info["dataset_sha256"] == original.DATA_HASH and info["pages"] == 3953,
            "Original preparation identity changed")
        require(sha(DATABASE) == info["database_sha256"]
            and DATABASE.stat().st_size == info["database_bytes"], "Immutable prepared database changed")
        require(not any(Path(str(DATABASE) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal")), "Prepared database has a sidecar")
    if execution:
        record = original.execution_intent(INTENT, bound, BINDING)
        require(record["host"] == frozen["environment"]["host"], "Original execution host/boot changed")
    return bound


DOWNLOAD = """import shutil,sys,urllib.request
from pathlib import Path
path=Path(sys.argv[2])
path.parent.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen(sys.argv[1],timeout=60) as response,path.open("xb") as output:
    shutil.copyfileobj(response,output)
    output.flush()
    import os
    os.fsync(output.fileno())
"""


def download(scope):
    path = PARQUET
    require(not path.exists(), "Never reuse a downloaded compatibility input")
    run_stage("input-download", [sys.executable, "-B", "-c", DOWNLOAD,
        scope["input"]["source_url"], str(path)], scope["timeouts_seconds"]["download"], (path,))
    require(path.stat().st_size == scope["input"]["upstream_bytes"]
        and sha(path) == scope["input"]["upstream_sha256"], "Downloaded Parquet differs from pinned bytes")
    save(PUBLIC / "input-verification.json", {key: scope["input"][key]
        for key in ("source_url", "source_revision", "upstream_bytes", "upstream_sha256",
                    "historical_manifest", "historical_manifest_sha256", "queries", "dataset_sha256")})
    publish("bench: verify pinned historical lexical input before preparation")


def verify_completed_worker(item, bound):
    output = PUBLIC / original.filename(item)
    report = original.read(output)
    ledger = output.with_name(output.name + ".attempts.jsonl.gz")
    raw = gzip.decompress(ledger.read_bytes())
    require(digest(raw) == report["ledger_sha256"], "Original complete ledger digest differs")
    original.verify_worker(report, bound, [json.loads(line) for line in raw.splitlines()])
    execution = read(INTENT)
    require(report["binding_sha256"] == sha(BINDING) and report["intent_sha256"] == sha(INTENT)
        and report["host"] == execution["host"], "Worker changed its binding/host/intent")


def run():
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and os.environ.get("GITHUB_REF") == TRIGGER,
        "Only the registered first hosted compatibility attempt may execute")
    selection = validate_selection(read(SELECTION))
    committed(SELECTION)
    require(sys.dont_write_bytecode and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
        "Run with -B and explicit child bytecode suppression")
    scope = read(SCOPE)
    for name in (*FILES, relative(SELECTION)):
        committed(ROOT / name)
    for name, checksum in scope["untouched_files_sha256"].items():
        require(sha(ROOT / name) == checksum, "Original registered input changed: " + name)
    require(not PUBLIC.exists() and not STATE.exists() and not BINDING.exists(),
        "Existing attempts or bindings must never be overwritten")
    require(remote_head() is None, "The fixed compatibility result ref is already claimed")
    require(text_git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"], "Workflow checkout changed before claim")
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    journal({"expected_remote": None})
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    stage = "claim"
    try:
        control_files = {name: sha(ROOT / name) for name in (*FILES, relative(SELECTION))}
        save(PUBLIC / "attempt.intent.json", {"status": "started", "at": stamp(),
            "attempt": ATTEMPT, "workflow_commit": os.environ["GITHUB_SHA"],
            "run_id": os.environ["GITHUB_RUN_ID"], "selection": selection,
            "selection_sha256": sha(SELECTION), "controller_files_sha256": control_files,
            "calls_expected": 5120, "workers_expected": 10, "fresh_rows_decoded": 0,
            "formal_measurement_started": False, "automatic_replay_permitted": False})
        publish("bench: claim the single historical lexical compatibility attempt")
        stage = "verify-registration-and-source"
        registry = verify_registration(scope, selection)
        sources = {"baseline": prepare_source("baseline", selection["baseline"]),
            "candidate": prepare_source("candidate", selection["candidate"], selection["candidate_files_sha256"])}
        frozen = {"controller_files_sha256": control_files, "registry_sha256": registry,
            "sources": sources, "environment": environment(scope)}
        save(PUBLIC / "source-environment.json", frozen)
        publish("bench: bind exact historical lexical sources and environment")
        stage = "binding"
        run_stage(stage, helper("bind", "--baseline-src", sources["baseline"]["source"],
            "--candidate-src", sources["candidate"]["source"], "--output", BINDING),
            scope["timeouts_seconds"]["bind"], (BINDING,))
        guards(frozen, scope, sources)
        stage = "input-download"
        download(scope)
        stage = "preparation"
        run_stage(stage, helper("prepare", "--binding", BINDING, "--source", sources["baseline"]["source"],
            "--state", STATE / "preparation", "--output", PREPARATION, "--parquet", PARQUET),
            scope["timeouts_seconds"]["prepare"], (PREPARATION,))
        guards(frozen, scope, sources, prepared=True)
        stage = "global-intent"
        run_stage(stage, helper("intent", "--binding", BINDING, "--preparation", PREPARATION,
            "--output", INTENT), scope["timeouts_seconds"]["intent"], (INTENT,))
        bound = guards(frozen, scope, sources, prepared=True, execution=True)
        for item in original.schedule():
            stage = f'{item["kind"]}-r{item["round"]}-{item["label"]}'
            guards(frozen, scope, sources, prepared=True, execution=True)
            output = PUBLIC / original.filename(item)
            state = STATE / "workers" / stage
            require(not state.exists() and not any(PUBLIC.glob(output.name + "*")),
                "Preserve prior partial/duplicate worker state")
            run_stage(stage, helper("worker", "--binding", BINDING,
                "--source", sources[item["label"]]["source"], "--state", state,
                "--output", output, "--database", DATABASE, "--preparation", PREPARATION,
                "--parquet", PARQUET, "--label", item["label"], "--kind", item["kind"],
                "--round", item["round"], "--intent", INTENT),
                scope["timeouts_seconds"]["worker"], (output,), worker_output=output)
            verify_completed_worker(item, bound)
            guards(frozen, scope, sources, prepared=True, execution=True)
        stage = "audit"
        audit = PUBLIC / "audit.json"
        run_stage(stage, helper("audit", "--binding", BINDING, "--reports", PUBLIC,
            "--intent", INTENT, "--output", audit), scope["timeouts_seconds"]["audit"], (audit,))
        result = read(audit)
        require(result["status"] == "verified" and result["accepted"] is True
            and result["calls"] == 5120 and result["complete_payload_pairs"] == 2560
            and result["workers"] == 10, "Original historical compatibility audit did not accept")
        guards(frozen, scope, sources, prepared=True, execution=True)
        save(PUBLIC / "completion.json", {"status": "completed", "at": stamp(),
            "audit_sha256": sha(audit), "calls": 5120, "complete_payload_pairs": 2560,
            "workers": 10, "original_audit_accepted": True, "fresh_rows_decoded": 0,
            "formal_acceptance": False, "release_acceptance": False,
            "policy": "Historical regression only; no new quality/comparator claim or timing pooling."})
        publish("bench: complete original historical lexical compatibility")
    except BaseException as error:
        if not (PUBLIC / "failure.json").exists():
            save(PUBLIC / "failure.json", {"status": "failed_or_incomplete", "at": stamp(),
                "stage": stage, "error": type(error).__name__ + ": " + str(error),
                "replay_permitted": False, "fresh_rows_decoded": 0,
                "policy": "Retain every stage/worker and do not rerun an incomplete prefix."})
        if not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve failed historical lexical compatibility")
        raise


def preserve():
    """Workflow fallback preserves only source-free existing artifacts; never executes."""
    if not PUBLIC.exists() or not (STATE / "publication.json").exists():
        return
    log = ROOT / ".artifacts" / (ATTEMPT + "-runner.log")
    if log.exists() and not (PUBLIC / "runner.log").exists():
        shutil.copyfile(log, PUBLIC / "runner.log")
    inventories = {}
    for item in original.schedule():
        path = PUBLIC / original.filename(item)
        if path.exists() or path.with_name(path.name + ".attempts.jsonl").exists():
            try:
                inventories[path.name] = preserve_worker_bytes(path)
            except BaseException as error:
                inventories[path.name] = {"preservation_error": type(error).__name__ + ": " + str(error)}
    save(PUBLIC / "workflow-outcome.json", {"at": stamp(),
        "outcome": os.environ.get("COMPATIBILITY_OUTCOME"),
        "available_worker_storage": inventories, "retrieval_calls_during_preservation": 0,
        "replay_permitted": False})
    if not (PUBLIC / "publication-failure.json").exists():
        publish("bench: preserve historical lexical workflow logs and partial outcomes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "preserve"))
    args = parser.parse_args()
    run() if args.mode == "run" else preserve()
