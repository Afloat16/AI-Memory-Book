"""Bound historical Q2 reuse; the round-four scoring helper stays unchanged.

Commit this driver/tests, run ``bind`` and commit its output, run ``prepare``
and commit its receipt, then run ``intent`` and commit it. Run ``worker`` with
indices 1..8, committing each report, ledger and attempt receipt before the
next index. Finally run ``audit``. This program never mutates Git. Bind,
prepare, intent and audit execute no retrieval or model inference; workers
reuse page vectors but still perform query-embedding inference.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/round5_q2_compatibility.py"
TEST = "tests/test_round5_q2_compatibility.py"
HELPER = "scripts/round4_semantic_compatibility.py"
OLD = "benchmarks/reports/round4-compatibility-final"
BASELINE_COMMIT = "692fb959ddf8934c5f516ba3d74ceb4385a2fa82"
BASELINE_SHA = "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"
BUILDER_COMMIT = "7b7a5d7336b9350a128f5e0a888811b1b3015e68"
BUILDER_SHA = "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"
MODEL = "2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25"
PINS = {
    "benchmarks/experiments/round5-plan.json": "d3302ef1169aa180b492af6b9c9938e5717ff7261e202ef7a3df50e14febaccd",
    "benchmarks/experiments/round5-materialization-addendum.json": "547aa0068fc5fd6a18e448719d855295c3c85ac78faea69867d208c175f77a34",
    OLD + "/authored36-preparation.json": "0fb2e417f465fd4748d35a327aaa928f58ae40a3eb9d07d884b5d1ca1bd3e5a9",
    OLD + "/hotpot128-preparation.json": "e16ec2b31633fff438971e48fd4dd7394442018ce16d82d33df4808e684739d5",
    OLD + "/paired-audit.json": "5e5bffde4729250169e8eb92f1d14088c46c9c57aef1e22be2f52ceafb4593d6",
    OLD + "/ledger-archive.json": "0a6dad8456c81a9eb59e88d4af143562bdf6bb877f81c77a6b4bd5da437294e9",
}
COHORTS = {
    "authored36": (36, "ecc46c474d5184995938419fa985b8e08c0ddb51560da49990247465db6db0b0"),
    "hotpot128": (128, "0791515aca6bccf19a97895cad681e06a07536d6c08050d54189cc64cb819822"),
}
ENCODERS = ("cl100k_base", "o200k_base")
BUDGETS = (512, 1024, 2048)
ERRORS = ("source", "projection", "scope", "token", "metadata")
VERSIONS = {"onnxruntime": "1.31.1", "tokenizers": "0.23.3", "numpy": "2.5.4",
            "tiktoken": "0.12.0", "pyarrow": "26.0.1"}
ENVIRONMENT = {"ORT_DISABLE_TELEMETRY": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONHASHSEED": "0"}
VECTOR_BOUNDARY = ("All semantic_vectors columns in primary-key order, length-prefixed JSON "
                   "identity/offset fields and exact BLOB bytes. No semantic_meta timestamps or model rerun.")


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def parse_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "Duplicate JSON field")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_json(path):
    raw = Path(path).read_bytes()
    return parse_json(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def write_receipt(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    temporary = path.with_name(path.name + ".partial") if replace else path
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def relative(path):
    """Public receipts contain repository-relative paths, never input text."""
    path = Path(os.path.abspath(path))
    value = path.relative_to(ROOT).as_posix()
    require(path.resolve().is_relative_to(ROOT), "Path escapes the repository")
    return value


def local(name):
    path = ROOT / name
    require(not Path(name).is_absolute() and ".." not in Path(name).parts
            and path.resolve().is_relative_to(ROOT), "Invalid bound repository path")
    return path


def git(*args, cwd=ROOT):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def committed(path, commit="HEAD"):
    name = relative(path)
    raw = Path(path).read_bytes()
    require(not Path(path).is_symlink() and git("show", commit + ":" + name) == raw,
            "File must match its committed Git blob: " + name)
    return hashlib.sha256(raw).hexdigest()


def source_identity(source, commit, expected_sha):
    source = Path(source).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) and re.fullmatch(r"[0-9a-f]{64}", expected_sha),
            "Require exact runtime commit and SHA-256")
    repository = Path(git("rev-parse", "--show-toplevel", cwd=source).decode().strip())
    package = source / "memory_book"
    prefix = package.relative_to(repository).as_posix()
    entries = git("ls-tree", "-r", "--name-only", commit, "--", prefix, cwd=repository).decode().splitlines()
    expected = {name for name in entries if name.endswith(".py")}
    head_files = git("ls-tree", "-r", "--name-only", "HEAD", "--", prefix, cwd=repository).decode().splitlines()
    actual = {path.relative_to(repository).as_posix() for path in package.rglob("*.py")}
    require(expected and expected == actual == {name for name in head_files if name.endswith(".py")},
            "Runtime Python file inventory differs")
    hasher = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        name = path.relative_to(repository).as_posix()
        raw = path.read_bytes()
        # Non-runtime checkpoint commits may advance HEAD. Both the named
        # source commit and checkout HEAD must still identify these exact bytes.
        require(not path.is_symlink() and git("show", commit + ":" + name, cwd=repository) == raw
                and git("show", "HEAD:" + name, cwd=repository) == raw,
                "Runtime differs from committed source")
        hasher.update(path.relative_to(package).as_posix().encode() + b"\0" + raw + b"\0")
    require(hasher.hexdigest() == expected_sha, "Runtime SHA-256 differs")
    return {"source": relative(source), "commit": commit, "runtime_sha256": expected_sha}


def helper_closure():
    """Pin local Python imports without importing the evaluator or product."""
    found, pending = set(), [HELPER]
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        for node in ast.walk(ast.parse(local(name).read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = name.removesuffix(".py").split("/")[:-node.level]
                    base = ".".join(package + ([base] if base else []))
                modules = [base, *[base + "." + alias.name for alias in node.names]]
            for module in modules:
                bits = module.split(".")
                if bits[0] not in ("benchmarks", "scripts"):
                    continue
                paths = ["/".join(bits) + ".py"]
                paths += ["/".join(bits[:i]) + "/__init__.py" for i in range(1, len(bits) + 1)]
                pending.extend(path for path in paths if local(path).is_file() and path not in found)
    return found | {SCRIPT, TEST, "benchmarks/transfer_cases.json", "benchmarks/transfer_manifest.json",
                    "benchmarks/hotpot_manifest.json"}


def settings(encoder):
    return {"semantic": True, "coverage": False, "budget_chars": 8000,
            "token_budgets": list(BUDGETS), "tokenizer": encoder, "limit": 5,
            "cache_size": 0, "use_cache": False, "repetitions": 1}


def expected_report(binding, worker, *, historical=False):
    cohort = binding["cohorts"][worker["cohort"]]
    return {"cohort": worker["cohort"], "label": "candidate" if historical else worker["label"],
            "runtime_sha256": BASELINE_SHA if historical else binding["sources"][worker["label"]]["runtime_sha256"],
            "dataset_sha256": cohort["dataset_sha256"], "evaluator_files": binding["old_evaluator_files"],
            "preparation_sha256": cohort["preparation_sha256"], "ort_disable_telemetry": "1",
            "model": binding["model"], "configured_generative_model_calls": 0,
            "expected_calls": len(cohort["query_ids"]) * 3, "settings": settings(worker["encoder"]),
            "originals_sha256": cohort["originals_sha256"], "vectors": cohort["vectors"],
            "interpretation": "Previously-scored regression compatibility only; no timing claim."}


def audit_report(report, ledger_raw, expected, query_ids):
    """Pure saved-result audit; no imports, database access or calls."""
    count = len(query_ids) * len(BUDGETS)
    require(len(query_ids) == len(set(query_ids)), "Duplicate registered query ID")
    fixed = {**expected, "status": "completed", "attempts_started": count, "attempts_finished": count}
    require(set(report) == set(fixed) | {"rows", "ledger_sha256"}, "Unexpected report fields")
    require(digest({key: report[key] for key in fixed}) == digest(fixed), "Report identity/settings differ")
    for key in ("expected_calls", "attempts_started", "attempts_finished", "configured_generative_model_calls"):
        require(type(report[key]) is int, "Non-integer call count")
    require(report["ledger_sha256"] == hashlib.sha256(ledger_raw).hexdigest(), "Raw ledger SHA differs")
    require(ledger_raw.endswith(b"\n"), "Truncated ledger")
    lines = ledger_raw.splitlines()
    keys = [(budget, identity) for budget in BUDGETS for identity in query_ids]
    require(len(report["rows"]) == count and len(lines) == count * 2, "Incomplete call/ledger matrix")
    for index, (row, (budget, identity)) in enumerate(zip(report["rows"], keys)):
        require(set(row) == {"query_id", "budget_tokens", "payload_sha256", "context_sha256", "errors"},
                "Unexpected row fields")
        require(row["query_id"] == identity and type(row["budget_tokens"]) is int
                and row["budget_tokens"] == budget, "Missing, duplicate or reordered row")
        require(set(row["errors"]) == set(ERRORS)
                and all(type(value) is int and value == 0 for value in row["errors"].values()),
                "Invariant errors or invalid error counters")
        require(all(isinstance(row[key], str) and re.fullmatch(r"[0-9a-f]{64}", row[key])
                    for key in ("payload_sha256", "context_sha256")), "Invalid payload digest")
        require(digest(parse_json(lines[index * 2])) == digest({"state": "started", "query_id": identity,
                                                               "budget_tokens": budget}), "Ledger start differs")
        require(digest(parse_json(lines[index * 2 + 1])) == digest({"state": "finished", **row}), "Ledger finish differs")
    return report["rows"]


def equal_payloads(left, right):
    require(len(left) == len(right), "Pair size differs")
    require(all((a["query_id"], a["budget_tokens"], a["payload_sha256"], a["context_sha256"])
                == (b["query_id"], b["budget_tokens"], b["payload_sha256"], b["context_sha256"])
                for a, b in zip(left, right)), "Full payload/context equality failed")


def schedule(binding):
    result = []
    for cohort in COHORTS:
        for encoder in ENCODERS:
            for label in ("baseline", "candidate"):
                index = len(result) + 1
                name = f"{index:02d}-{cohort}-{encoder}-{label}"
                state = binding["state_root"] + f"/{cohort}/{encoder}/{label}"
                report = binding["results_root"] + "/" + name + ".json.gz"
                worker = {"index": index, "id": name, "cohort": cohort, "encoder": encoder,
                          "label": label, "state": state, "database": state + "/" + label + ".db",
                          "report": report, "ledger": report + ".attempts.jsonl",
                          "receipt": binding["results_root"] + "/" + name + ".attempt.json",
                          "expected_calls": COHORTS[cohort][0] * 3}
                worker["argv"] = [binding["python_executable"], "-u", str(ROOT / HELPER), "worker",
                    "--source", str(local(binding["sources"][label]["source"])),
                    "--expected-source-sha", binding["sources"][label]["runtime_sha256"],
                    "--state", str(local(state)), "--output", str(local(report)), "--cohort", cohort,
                    "--label", label, "--model-dir", str(local(binding["model_dir"])),
                    "--hotpot-parquet", str(local(binding["parquet"]["path"])),
                    "--preparation", str(local(binding["cohorts"][cohort]["preparation"])),
                    "--tokenizer", encoder]
                result.append(worker)
    return result


def verify_environment(binding):
    require(sys.executable == binding["python_executable"] and sys.version == binding["python_version"],
            "Interpreter changed")
    require({name: importlib.metadata.version(name) for name in VERSIONS} == VERSIONS == binding["dependencies"],
            "Pinned dependency version differs")
    for entry in binding["model"]["files"]:
        path = local(binding["model_dir"]) / entry["path"]
        require(path.stat().st_size == entry["bytes"] and file_sha(path) == entry["sha256"],
                "Actual model artifact changed")
    parquet = binding["parquet"]
    require(local(parquet["path"]).stat().st_size == parquet["bytes"]
            and file_sha(local(parquet["path"])) == parquet["sha256"], "Historical Parquet changed")


def verify_binding(binding):
    require(binding["schema_version"] == 1 and binding["protocol"] == "round5-q2-reuse-v1"
            and binding["registered_pins"] == PINS and binding["environment"] == ENVIRONMENT,
            "Binding protocol differs")
    require(binding["original_builder"] == {"commit": BUILDER_COMMIT, "runtime_sha256": BUILDER_SHA}
            and (binding["expected_calls"], binding["expected_pairs"], binding["expected_ledger_events"])
            == (1968, 984, 3936), "Builder attribution or total matrix changed")
    require(binding["state_root"].startswith(".artifacts/round5-")
            and binding["results_root"].startswith("benchmarks/reports/round5-"),
            "Require new private/public round-five paths")
    require(binding["sources"]["baseline"]["commit"] == BASELINE_COMMIT
            and binding["sources"]["baseline"]["runtime_sha256"] == BASELINE_SHA,
            "Historical baseline differs")
    require(set(binding["cohorts"]) == set(COHORTS) and digest(binding["model"]) == MODEL,
            "Cohort/model binding differs")
    for cohort, (count, fingerprint) in COHORTS.items():
        value = binding["cohorts"][cohort]
        require(value["dataset_sha256"] == fingerprint and len(value["query_ids"]) == count
                and len(set(value["query_ids"])) == count
                and all(isinstance(identity, str) and identity for identity in value["query_ids"]),
                "Registered ID matrix differs")
        preparation = read_json(local(value["preparation"]))
        require(value["preparation"] == OLD + "/" + cohort + "-preparation.json"
                and value["preparation_sha256"] == PINS[value["preparation"]]
                and value["original_database"] == f".artifacts/round4-q2-final-{cohort}/prepared.db"
                and preparation["source_sha256"] == BUILDER_SHA
                and value["originals_sha256"] == preparation["originals_sha256"]
                and value["vectors"] == preparation["vectors"]
                and binding["model"] == preparation["model"]
                and binding["old_evaluator_files"] == preparation["evaluator_files"],
                "Original preparation identity differs")
    for name, expected in {**PINS, **binding["evaluator_files"]}.items():
        require(file_sha(local(name)) == expected and committed(local(name), binding["authoring_commit"]) == expected,
                "Frozen evaluator/input bytes changed: " + name)
    for name, expected in binding["old_evaluator_files"].items():
        require(binding["evaluator_files"].get(name) == expected, "Old helper differs from preparation")
    require(binding["workers"] == schedule(binding), "Fixed eight-worker schedule changed")
    for source in binding["sources"].values():
        require(source_identity(local(source["source"]), source["commit"], source["runtime_sha256"]) == source,
                "Source identity differs")
    verify_environment(binding)
    audit_old_reports(binding)


def audit_old_reports(binding):
    result = {}
    require(set(binding["old_c2"]) == {cohort + "/" + encoder for cohort in COHORTS for encoder in ENCODERS},
            "Old C2 matrix differs")
    pinned = read_json(local(OLD + "/paired-audit.json"))["file_sha256"]
    for worker in binding["workers"]:
        if worker["label"] != "baseline":
            continue
        key = worker["cohort"] + "/" + worker["encoder"]
        saved = binding["old_c2"][key]
        basename = f"{worker['cohort']}-candidate-{worker['encoder']}.json.gz"
        ledger_name = basename + ".attempts.jsonl.gz"
        require(saved == {"report": OLD + "/" + basename, "report_sha256": pinned[basename],
            "ledger": OLD + "/" + ledger_name, "ledger_sha256": pinned[ledger_name],
            "ledger_raw_sha256": pinned[basename + ".attempts.jsonl"]}, "Old C2 binding differs from frozen audit")
        require(file_sha(local(saved["report"])) == saved["report_sha256"]
                and file_sha(local(saved["ledger"])) == saved["ledger_sha256"], "Old C2 artifact changed")
        raw = gzip.decompress(local(saved["ledger"]).read_bytes())
        require(hashlib.sha256(raw).hexdigest() == saved["ledger_raw_sha256"], "Old C2 ledger changed")
        result[key] = audit_report(read_json(local(saved["report"])), raw,
            expected_report(binding, worker, historical=True), binding["cohorts"][worker["cohort"]]["query_ids"])
    require(len(result) == 4, "Incomplete old C2 matrix")
    return result


def bind(args):
    require(not args.output.exists() and not args.state.exists() and not args.results.exists(),
            "Binding/state/results must be fresh")
    for name, expected in PINS.items():
        require(file_sha(local(name)) == expected, "Registered historical input changed")
    historical = read_json(local(OLD + "/paired-audit.json"))
    preparations = {cohort: read_json(local(OLD + "/" + cohort + "-preparation.json")) for cohort in COHORTS}
    authored = read_json(local("benchmarks/transfer_cases.json"))
    authored_manifest = read_json(local("benchmarks/transfer_manifest.json"))
    require(file_sha(local("benchmarks/transfer_cases.json")) == authored_manifest["sha256"],
            "Authored source bytes differ")
    manifest = read_json(local("benchmarks/hotpot_manifest.json"))
    ids = {"authored36": [case["id"] for domain in authored["domains"] for case in domain["queries"]],
           "hotpot128": manifest["selected_ids"]}
    files = helper_closure() | set(preparations["authored36"]["evaluator_files"])
    binding = {"schema_version": 1, "protocol": "round5-q2-reuse-v1", "registered_at": now(),
        "registered_pins": PINS, "authoring_commit": git("rev-parse", "HEAD").decode().strip(),
        "evaluator_files": {name: committed(local(name)) for name in sorted(files)},
        "old_evaluator_files": preparations["authored36"]["evaluator_files"],
        "sources": {"baseline": source_identity(args.baseline_src, BASELINE_COMMIT, BASELINE_SHA),
                    "candidate": source_identity(args.candidate_src, args.candidate_commit, args.candidate_sha)},
        "original_builder": {"commit": BUILDER_COMMIT, "runtime_sha256": BUILDER_SHA},
        "model": preparations["authored36"]["model"], "model_dir": relative(args.model_dir),
        "parquet": {"path": relative(args.hotpot_parquet), "sha256": manifest["upstream_sha256"],
                    "bytes": manifest["upstream_bytes"]},
        "python_executable": sys.executable, "python_version": sys.version, "dependencies": VERSIONS,
        "environment": ENVIRONMENT, "state_root": relative(args.state), "results_root": relative(args.results),
        "cohorts": {}, "old_c2": {}, "expected_calls": 1968, "expected_pairs": 984,
        "expected_ledger_events": 3936,
        "boundary": "Original v031 page vectors reused by v032/B; no index rebuild. Query embeddings execute in workers. Historical compatibility only; no timing or quality claim.",
        "failure_rule": "One fixed schedule; no replay, replacement calls or automatic retry. Commit each complete worker before advancing; preserve every partial artifact."}
    for cohort, (count, fingerprint) in COHORTS.items():
        prep = preparations[cohort]
        require(prep["cohort"] == cohort and prep["queries"] == count and prep["dataset_sha256"] == fingerprint,
                "Historical preparation cohort differs")
        name = OLD + "/" + cohort + "-preparation.json"
        binding["cohorts"][cohort] = {"dataset_sha256": fingerprint, "query_ids": ids[cohort],
            "preparation": name, "preparation_sha256": PINS[name],
            "original_database": f".artifacts/round4-q2-final-{cohort}/prepared.db",
            "originals_sha256": prep["originals_sha256"], "vectors": prep["vectors"]}
        for encoder in ENCODERS:
            report = f"{cohort}-candidate-{encoder}.json.gz"
            ledger = report + ".attempts.jsonl.gz"
            binding["old_c2"][cohort + "/" + encoder] = {
                "report": OLD + "/" + report, "report_sha256": historical["file_sha256"][report],
                "ledger": OLD + "/" + ledger, "ledger_sha256": historical["file_sha256"][ledger],
                "ledger_raw_sha256": historical["file_sha256"][report + ".attempts.jsonl"]}
    binding["workers"] = schedule(binding)
    verify_binding(binding)
    write_receipt(args.output, binding)
    return {"binding": relative(args.output), "sha256": file_sha(args.output), "calls_executed": 0}


def database_identity(path):
    """Read one SQLite snapshot, including WAL, without product imports."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        originals = digest({table: [list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
                            for table in ("projects", "chapters", "sessions", "turns", "sections", "pages")})
        columns = [row[1] for row in db.execute("PRAGMA table_info(semantic_vectors)")]
        require(columns == ["page_id", "ordinal", "char_start", "char_end", "vector"], "Vector schema changed")
        revision, fingerprint = db.execute("SELECT revision,model_fingerprint FROM semantic_meta WHERE singleton=1").fetchone()
        hasher = hashlib.sha256(b"semantic_vectors/page_id,ordinal,char_start,char_end,vector/v1\n")
        rows = size = 0
        for page, ordinal, start, end, vector in db.execute("SELECT page_id,ordinal,char_start,char_end,vector FROM semantic_vectors ORDER BY page_id,ordinal"):
            require(type(vector) is bytes and len(vector) == 384 * 4, "Vector representation changed")
            header = json.dumps([page, ordinal, start, end], ensure_ascii=False, separators=(",", ":")).encode()
            hasher.update(len(header).to_bytes(8, "big") + header + len(vector).to_bytes(8, "big") + vector)
            rows += 1
            size += len(vector)
        return {"originals_sha256": originals, "vectors": {"sha256": hasher.hexdigest(), "rows": rows,
            "vector_bytes": size, "revision": revision, "model_fingerprint": fingerprint,
            "boundary": VECTOR_BOUNDARY}, "cache_rows": db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}


def expected_database(binding, cohort):
    value = binding["cohorts"][cohort]
    return {"originals_sha256": value["originals_sha256"], "vectors": value["vectors"], "cache_rows": 0}


def check_database(binding, cohort, path):
    identity = database_identity(path)
    require(identity == expected_database(binding, cohort), "Originals/vectors/cache differ: " + relative(path))
    return identity


def check_originals(binding):
    return {cohort: check_database(binding, cohort, local(value["original_database"]))
            for cohort, value in binding["cohorts"].items()}


def backup_database(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=False)
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)) as src:
        src.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst, pages=128)
            dst.commit()


def load_binding(path):
    committed(path)
    binding = read_json(path)
    verify_binding(binding)
    return binding


def control_path(binding, name):
    return local(binding["results_root"]) / name


def prepare(args):
    binding = load_binding(args.binding)
    state, output = local(binding["state_root"]), local(binding["results_root"])
    require(not state.exists() and not output.exists(), "Never repeat preparation or reuse a state directory")
    state.mkdir(parents=True)
    output.mkdir(parents=True)
    path = control_path(binding, "preparation-reuse.json")
    receipt = {"schema_version": 1, "status": "running", "started_at": now(),
               "binding_sha256": file_sha(args.binding), "original_builder": binding["original_builder"],
               "method": "mode=ro SQLite backup includes WAL; explicit connection closes. Physical SHM bytes are not an identity.",
               "copies": [], "retrieval_calls": 0, "inference_calls": 0}
    write_receipt(path, receipt)
    try:
        receipt["originals_before"] = check_originals(binding)
        for worker in binding["workers"]:
            source = local(binding["cohorts"][worker["cohort"]]["original_database"])
            target = local(worker["database"])
            backup_database(source, target)
            identity = check_database(binding, worker["cohort"], target)
            receipt["copies"].append({"worker": worker["id"], "database": worker["database"],
                                      "initial_file_sha256": file_sha(target), "identity": identity})
            write_receipt(path, receipt, replace=True)
        receipt["originals_after"] = check_originals(binding)
        verify_binding(binding)
        receipt["status"] = "completed"
    except BaseException as error:
        receipt.update(status="failed-incomplete", error_type=type(error).__name__)
        raise
    finally:
        receipt["finished_at"] = now()
        write_receipt(path, receipt, replace=True)
    return {"preparation": relative(path), "sha256": file_sha(path), "copies": 8, "calls_executed": 0}


def load_preparation(binding, binding_path):
    path = control_path(binding, "preparation-reuse.json")
    committed(path)
    value = read_json(path)
    require(value["status"] == "completed" and value["binding_sha256"] == file_sha(binding_path)
            and value["original_builder"] == binding["original_builder"]
            and value["retrieval_calls"] == value["inference_calls"] == 0,
            "Preparation receipt incomplete or rebound")
    expected_originals = {cohort: expected_database(binding, cohort) for cohort in COHORTS}
    require(value["originals_before"] == value["originals_after"] == expected_originals,
            "Preparation changed historical originals/vectors")
    require(len(value["copies"]) == 8, "Incomplete backup matrix")
    for copy, worker in zip(value["copies"], binding["workers"]):
        require(copy["worker"] == worker["id"] and copy["database"] == worker["database"]
                and copy["identity"] == expected_database(binding, worker["cohort"]), "Backup receipt differs")
    return value


def no_replay(binding, start):
    for worker in binding["workers"][start:]:
        for name in ("report", "ledger", "receipt"):
            path = local(worker[name])
            require(not path.exists() and not path.with_name(path.name + ".partial").exists(),
                    "Worker already has an attempt artifact; never replay: " + worker["id"])
    require(not control_path(binding, "paired-audit.json").exists(), "Audit already exists")


def check_layout(binding):
    expected = {"preparation-reuse.json", "execution-intent.json", "paired-audit.json"}
    expected |= {Path(work[key]).name for work in binding["workers"] for key in ("report", "ledger", "receipt")}
    output = local(binding["results_root"])
    require(all(path.is_file() and path.name in expected for path in output.iterdir()),
            "Unexpected or partial artifact in the registered results directory")


def intent(args):
    binding = load_binding(args.binding)
    preparation = load_preparation(binding, args.binding)
    check_layout(binding)
    no_replay(binding, 0)
    for copy, worker in zip(preparation["copies"], binding["workers"]):
        check_database(binding, worker["cohort"], local(worker["database"]))
        require(file_sha(local(worker["database"])) == copy["initial_file_sha256"], "Backup bytes changed before intent")
    originals = check_originals(binding)
    value = {"schema_version": 1, "status": "registered-before-first-recall", "registered_at": now(),
             "binding_sha256": file_sha(args.binding),
             "preparation_sha256": file_sha(control_path(binding, "preparation-reuse.json")),
             "workers": binding["workers"], "environment": binding["environment"],
             "originals": originals, "expected_calls": 1968, "expected_pairs": 984,
             "expected_ledger_events": 3936, "cross_round_v032_equality_required": True,
             "rule": "Run indices1..8 once; prior report/ledger/receipt must be committed and complete before each next worker."}
    path = control_path(binding, "execution-intent.json")
    write_receipt(path, value)
    return {"intent": relative(path), "sha256": file_sha(path), "calls_executed": 0}


def load_intent(binding, binding_path):
    load_preparation(binding, binding_path)
    path = control_path(binding, "execution-intent.json")
    committed(path)
    value = read_json(path)
    require(value["status"] == "registered-before-first-recall"
            and value["binding_sha256"] == file_sha(binding_path)
            and value["preparation_sha256"] == file_sha(control_path(binding, "preparation-reuse.json"))
            and value["workers"] == binding["workers"] and value["environment"] == ENVIRONMENT
            and value["originals"] == {cohort: expected_database(binding, cohort) for cohort in COHORTS}
            and (value["expected_calls"], value["expected_pairs"], value["expected_ledger_events"]) == (1968, 984, 3936)
            and value["cross_round_v032_equality_required"] is True, "Execution intent changed")
    return value


def report_artifacts(worker):
    return {key + "_sha256": file_sha(local(worker[key])) if local(worker[key]).exists() else None
            for key in ("report", "ledger")}


def audit_worker(binding, worker, *, require_commit=True):
    if require_commit:
        for key in ("report", "ledger", "receipt"):
            committed(local(worker[key]))
    receipt = read_json(local(worker["receipt"]))
    identity = expected_database(binding, worker["cohort"])
    originals = {cohort: expected_database(binding, cohort) for cohort in COHORTS}
    intent_path = control_path(binding, "execution-intent.json")
    require(receipt["status"] == "completed" and type(receipt["returncode"]) is int and receipt["returncode"] == 0
            and receipt["worker"] == worker and receipt["before"] == receipt["after"] == identity
            and receipt["originals_before"] == receipt["originals_after"] == originals
            and receipt["artifacts"] == report_artifacts(worker)
            and receipt["binding_sha256"] == read_json(intent_path)["binding_sha256"]
            and receipt["intent_sha256"] == file_sha(intent_path),
            "Worker receipt is incomplete or rebound")
    return audit_report(read_json(local(worker["report"])), local(worker["ledger"]).read_bytes(),
                        expected_report(binding, worker), binding["cohorts"][worker["cohort"]]["query_ids"])


def audit_prefix(binding, count, *, require_commit=True):
    require(type(count) is int and 0 <= count <= 8, "Invalid prefix length")
    old = audit_old_reports(binding)
    rows, artifacts = {}, {}
    for worker in binding["workers"][:count]:
        saved = audit_worker(binding, worker, require_commit=require_commit)
        key = worker["cohort"] + "/" + worker["encoder"]
        if worker["label"] == "baseline":
            equal_payloads(saved, old[key])
            rows[key] = saved
        else:
            equal_payloads(rows[key], saved)
        artifacts[worker["id"]] = {**report_artifacts(worker),
                                   "receipt_sha256": file_sha(local(worker["receipt"]))}
    return artifacts


def execute(command, stdout, stderr, environment):
    """Fresh process; regular log files avoid pipe-reader cleanup deadlocks."""
    process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **environment},
        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        return process.wait(timeout=3600)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            process.wait(timeout=1)


def worker(args):
    binding = load_binding(args.binding)
    load_intent(binding, args.binding)
    check_layout(binding)
    require(type(args.index) is int and 1 <= args.index <= 8, "Worker index must be1..8")
    audit_prefix(binding, args.index - 1)
    no_replay(binding, args.index - 1)
    work = binding["workers"][args.index - 1]
    before = check_database(binding, work["cohort"], local(work["database"]))
    originals = check_originals(binding)
    receipt = {"schema_version": 1, "status": "running", "started_at": now(), "worker": work,
        "binding_sha256": file_sha(args.binding),
        "intent_sha256": file_sha(control_path(binding, "execution-intent.json")),
        "before": before, "originals_before": originals, "returncode": None}
    path = local(work["receipt"])
    write_receipt(path, receipt)
    logs = {key: local(work["state"]) / (key + ".log") for key in ("stdout", "stderr")}
    try:
        with logs["stdout"].open("xb") as stdout, logs["stderr"].open("xb") as stderr:
            receipt["returncode"] = execute(work["argv"], stdout, stderr, ENVIRONMENT)
        require(receipt["returncode"] == 0, "Compatibility worker failed; preserve and stop")
        receipt["after"] = check_database(binding, work["cohort"], local(work["database"]))
        receipt["originals_after"] = check_originals(binding)
        verify_binding(binding)
        rows = audit_report(read_json(local(work["report"])), local(work["ledger"]).read_bytes(),
                            expected_report(binding, work), binding["cohorts"][work["cohort"]]["query_ids"])
        if work["label"] == "baseline":
            equal_payloads(rows, audit_old_reports(binding)[work["cohort"] + "/" + work["encoder"]])
        else:
            equal_payloads(rows, read_json(local(binding["workers"][args.index - 2]["report"]))["rows"])
        receipt["status"] = "completed"
    except BaseException as error:
        receipt.update(status="failed-incomplete", error_type=type(error).__name__)
        raise
    finally:
        receipt.update(finished_at=now(), artifacts=report_artifacts(work),
            private_logs={key: {"path": relative(value), "sha256": file_sha(value), "bytes": value.stat().st_size}
                          for key, value in logs.items() if value.exists()})
        write_receipt(path, receipt, replace=True)
    return {"worker": work["id"], "status": "completed", "calls": work["expected_calls"],
            "commit_before_next": [work[key] for key in ("report", "ledger", "receipt")]}


def audit(args):
    binding = load_binding(args.binding)
    load_intent(binding, args.binding)
    check_layout(binding)
    path = control_path(binding, "paired-audit.json")
    require(not path.exists(), "Never replace an audit")
    artifacts = audit_prefix(binding, 8)
    databases = {work["id"]: check_database(binding, work["cohort"], local(work["database"]))
                 for work in binding["workers"]}
    originals = check_originals(binding)
    require(sum(work["expected_calls"] for work in binding["workers"]) == 1968, "Call matrix changed")
    value = {"schema_version": 1, "status": "passed", "audited_at": now(),
        "binding_sha256": file_sha(args.binding), "intent_sha256": file_sha(control_path(binding, "execution-intent.json")),
        "sources": binding["sources"], "complete_calls": 1968, "exact_full_payload_pairs": 984,
        "cross_round_v032_payload_pairs": 984, "ledger_events": 3936,
        "invariant_error_totals": {key: 0 for key in ERRORS}, "artifacts": artifacts,
        "databases": databases, "historical_originals": originals,
        "retrieval_calls_executed_by_audit": 0, "inference_calls_executed_by_audit": 0,
        "limits": ["Previously scored historical cohorts; no new quality or performance claim.",
                   "Payload/context bodies are omitted. Audit verifies saved invariants and exact digests; it cannot independently re-tokenize or re-project omitted bodies.",
                   "Reused page vectors retain original v031 builder attribution; old index-build timings are not new measurements."]}
    write_receipt(path, value)
    return {"audit": relative(path), "sha256": file_sha(path), "calls_executed": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    command = sub.add_parser("bind")
    for name in ("baseline-src", "candidate-src", "model-dir", "hotpot-parquet", "state", "results", "output"):
        command.add_argument("--" + name, type=Path, required=True)
    command.add_argument("--candidate-commit", required=True)
    command.add_argument("--candidate-sha", required=True)
    for mode in ("prepare", "intent", "worker", "audit"):
        command = sub.add_parser(mode)
        command.add_argument("--binding", type=Path, required=True)
        if mode == "worker":
            command.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(globals()[args.mode](args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
