"""Round-five fixed-source, sequential A/B performance experiment.

This is a new protocol, not a continuation of round four's acceptance gate.
Every query attempt is fsynced before/after timing. A claimed worker can start
once; only an untouched suffix may continue on the same host/boot/runtime.
Public artifacts contain complete-output hashes, never upstream source text.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_default_recall import indexed_content, rss, server_rss, storage
from scripts.round4_performance import INVARIANTS, make_row
from benchmarks.resume import _lock
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.token_compare import ENCODINGS, TokenCounter, latency_summary, load_dataset

VERSION = "round5-exact-output-performance-1"
BASELINE_COMMIT = "692fb959ddf8934c5f516ba3d74ceb4385a2fa82"
BASELINE_SHA = "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"
COHORTS = {
    "synthetic61": {"queries": 168, "sessions": 112,
        "sha256": "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"},
    "public1015": {"queries": 1015, "sessions": 216,
        "sha256": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"},
}
CONFIGURATIONS = (
    {"id": "native-char4000", "surface": "native", "budget_chars": 4000, "budget_tokens": None},
    {"id": "native-char100000", "surface": "native", "budget_chars": 100000, "budget_tokens": None},
    {"id": "native-token512", "surface": "native", "budget_chars": 8000, "budget_tokens": 512, "tokenizer": "cl100k_base"},
    {"id": "native-token1024", "surface": "native", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
    {"id": "native-token2048", "surface": "native", "budget_chars": 8000, "budget_tokens": 2048, "tokenizer": "cl100k_base"},
    {"id": "mcp-char4000", "surface": "official-sdk-mcp-stdio", "budget_chars": 4000, "budget_tokens": None},
    {"id": "mcp-token1024", "surface": "official-sdk-mcp-stdio", "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"},
)
ORDERS = (("baseline", "candidate"), ("candidate", "baseline"),
          ("candidate", "baseline"), ("baseline", "candidate"))
EXPECTED_CALLS = 66248
CHUNK_CHARS = 480000
HELPERS = (
    "scripts/round5_performance.py", "tests/test_round5_performance.py",
    "scripts/round4_performance.py", "scripts/benchmark_default_recall.py",
    "benchmarks/__init__.py", "benchmarks/native_budget_eval.py",
    "benchmarks/semantic_eval.py", "benchmarks/component_eval.py",
    "benchmarks/token_compare.py", "benchmarks/run.py", "benchmarks/data.py",
    "benchmarks/public_data.py", "benchmarks/long_data.py", "benchmarks/transfer_data.py",
    "benchmarks/hotpot_data.py", "benchmarks/query_guard.py", "benchmarks/resume.py",
    "benchmarks/locomo_split.json",
)
HASH = re.compile(r"[0-9a-f]{64}\Z")
RESOURCE_FIELDS = ("runtime_import_ms", "native_open_ms", "fresh_ingestion_ms",
                   "unchanged_reingestion_ms", "reference_tokenizer_initialization_ms")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def raw_json(value):
    return (dump(value) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(dump(value).encode())


def exclusive_bytes(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def exclusive(path, value):
    exclusive_bytes(path, raw_json(value))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def files_identity():
    return {name: sha((ROOT / name).read_bytes()) for name in HELPERS}


def environment():
    packages = sorted({(re.sub(r"[-_.]+", "-", d.metadata.get("Name", "")).lower(), d.version)
                       for d in importlib.metadata.distributions()})
    require(importlib.metadata.version("tiktoken") == "0.12.0", "Use the frozen tiktoken 0.12.0")
    return {"python": platform.python_version(), "executable_sha256": sha(Path(sys.executable).read_bytes()),
            "sqlite": sqlite3.sqlite_version, "packages": [list(item) for item in packages]}


def host_identity():
    return {"boot_sha256": sha(Path("/proc/sys/kernel/random/boot_id").read_bytes()),
            "machine_sha256": sha(platform.node().encode()), "platform": platform.platform(),
            "processor": platform.processor(), "cpu_count": os.cpu_count(), "runtime": environment()}


def source_identity(src, commit):
    """Check a source snapshot against exact Git blobs, not its parent checkout."""
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Source commit must be a full Git SHA")
    package = Path(src).resolve() / "memory_book"
    expected = {}
    for line in git("ls-tree", "-r", "-z", commit, "--", "src/memory_book").split(b"\0"):
        if not line:
            continue
        metadata, path = line.decode().split("\t", 1)
        mode, kind, identity = metadata.split()
        if path.endswith(".py"):
            require(kind == "blob" and mode != "120000", "Unexpected source object")
            expected[path.removeprefix("src/memory_book/")] = identity
    actual = {p.relative_to(package).as_posix(): p for p in package.rglob("*.py")}
    require(expected and set(expected) == set(actual), "Source snapshot file axis differs from its commit")
    for name, path in actual.items():
        content = path.read_bytes()
        blob = b"blob " + str(len(content)).encode() + b"\0" + content
        require(hashlib.sha1(blob).hexdigest() == expected[name], "Uncommitted runtime source: " + name)
    return {"commit": commit, "runtime_sha256": engine_source_hash(package), "python_files": len(actual)}


def committed_source_identity(commit):
    """Rebuild the same runtime fingerprint from Git, without an old scratch path."""
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Source commit must be a full SHA")
    names = []
    for line in git("ls-tree", "-r", "-z", commit, "--", "src/memory_book").split(b"\0"):
        if line:
            metadata, path = line.decode().split("\t", 1)
            mode, kind, _ = metadata.split()
            if path.endswith(".py"):
                require(kind == "blob" and mode != "120000", "Unexpected committed runtime object")
                names.append(path.removeprefix("src/memory_book/"))
    require(names, "Committed runtime contains no Python files")
    fingerprint = hashlib.sha256()
    for name in sorted(names):
        fingerprint.update(name.encode())
        fingerprint.update(b"\0")
        fingerprint.update(git("show", commit + ":src/memory_book/" + name))
        fingerprint.update(b"\0")
    return {"commit": commit, "runtime_sha256": fingerprint.hexdigest(), "python_files": len(names)}


def dataset(name, locomo):
    require(name in COHORTS, "Unregistered regression cohort")
    value = load_dataset("synthetic", 61, "development", 8, None, 0) if name == "synthetic61" else \
        load_dataset("locomo", 61, "heldout", 8, str(locomo), 0)
    expected = COHORTS[name]
    ids = [case.id for case in value.queries]
    require(len(ids) == len(set(ids)) == expected["queries"]
            and len(value.sessions) == expected["sessions"] and value.fingerprint == expected["sha256"],
            "Regression cohort/count/fingerprint differs")
    return value


def schedule():
    return [{"key": f"r{r}-{cohort}-{label}", "round": r, "cohort": cohort, "label": label}
            for r, labels in enumerate(ORDERS) for cohort in COHORTS for label in labels]


def query_order(ids, repetition, config_index):
    values = list(ids)
    random.Random(51061 + 1009 * repetition + config_index).shuffle(values)
    return values


def bind(args):
    evaluator_commit = git("rev-parse", "HEAD").decode().strip()
    hashes = files_identity()
    for name, identity in hashes.items():
        require(sha(git("show", evaluator_commit + ":" + name)) == identity,
                "Commit the evaluator and tests before binding: " + name)
    source_paths = {"baseline": str(args.baseline_src.resolve()), "candidate": str(args.candidate_src.resolve())}
    sources = {"baseline": source_identity(args.baseline_src, args.baseline_commit),
               "candidate": source_identity(args.candidate_src, args.candidate_commit or evaluator_commit)}
    require(sources["baseline"]["commit"] == BASELINE_COMMIT
            and sources["baseline"]["runtime_sha256"] == BASELINE_SHA, "Baseline must be published v0.3.2")
    cohorts = {}
    for name in COHORTS:
        data = dataset(name, args.locomo_path)
        cohorts[name] = {**COHORTS[name], "query_ids_original_order": [q.id for q in data.queries]}
    value = {"schema_version": 1, "protocol": VERSION, "created_at": now(),
        "sources": sources, "source_paths": source_paths, "evaluator_commit": evaluator_commit,
        "evaluator_files": hashes, "runtime": environment(), "cohorts": cohorts,
        "configurations": list(CONFIGURATIONS), "schedule": schedule(), "expected_calls": EXPECTED_CALLS,
        "locomo_path": str(args.locomo_path.resolve()), "locomo_sha256": sha(args.locomo_path.read_bytes()),
        "policy": {"quality": "Old regression data; exact complete-output equality, no quality gain claim.",
            "timing": "Sequential isolated workers, AB BA BA AB, warm OS caches; all samples retained.",
            "target": "Report whether unchanged-ingestion mean improves >=20% in each cohort; all recall cells and regressions are descriptive.",
            "resources": "Process snapshots include evaluator overhead. Unavailable MCP RSS is unknown, never zero or a passed resource gate.",
            "artifacts": "Complete native/MCP text/envelope hashes, counts and invariant outcomes; no upstream source text.",
            "resume": "Same-host untouched worker suffix only. Preserve every started, failed or incomplete attempt."}}
    exclusive(args.output, value)
    return {"binding": str(args.output), "sha256": sha(args.output.read_bytes()),
            "next": "Commit the exact binding, then init and publish each claim before worker execution."}


def load_binding(path, *, check_environment=True):
    path = Path(path).resolve()
    value = json.loads(path.read_bytes())
    require(value["protocol"] == VERSION and value["configurations"] == list(CONFIGURATIONS)
            and value["schedule"] == schedule() and value["expected_calls"] == EXPECTED_CALLS,
            "Binding protocol/matrix differs")
    require(set(value["cohorts"]) == set(COHORTS), "Binding cohort axis differs")
    for name, expected in COHORTS.items():
        actual = value["cohorts"][name]
        require(all(actual[k] == v for k, v in expected.items())
                and len(actual["query_ids_original_order"]) == len(set(actual["query_ids_original_order"])) == expected["queries"],
                "Binding cohort metadata differs")
    require(value["evaluator_files"] == files_identity(), "Evaluator/helper/test bytes changed")
    if check_environment:
        require(value["runtime"] == environment(), "Python/SQLite/dependency environment changed")
    relative = path.relative_to(ROOT).as_posix()
    require(path.read_bytes() == git("show", "HEAD:" + relative), "Exact binding must be Git-committed before use")
    for name, identity in value["evaluator_files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == identity,
                "Evaluator source commit differs: " + name)
    for label, source in value["sources"].items():
        actual = (source_identity(Path(value["source_paths"][label]), source["commit"])
                  if check_environment else committed_source_identity(source["commit"]))
        require(actual == source, "Frozen source identity changed")
    require(value["sources"]["baseline"]["commit"] == BASELINE_COMMIT
            and value["sources"]["baseline"]["runtime_sha256"] == BASELINE_SHA, "Baseline identity differs")
    return value


def init(args):
    binding = load_binding(args.binding)
    locomo = Path(binding["locomo_path"])
    require(sha(locomo.read_bytes()) == binding["locomo_sha256"], "Local dataset bytes changed")
    for name in COHORTS:
        data = dataset(name, locomo)
        require([q.id for q in data.queries] == binding["cohorts"][name]["query_ids_original_order"],
                "Dataset query identity order changed")
    state = args.state_dir.resolve()
    state_relative = state.relative_to(ROOT).as_posix()
    require(not state.exists(), "Execution directory already exists")
    binding_sha = sha(args.binding.read_bytes())
    registration = "benchmarks/experiments/round5-run-" + binding_sha + ".json"
    run = {"protocol": VERSION, "created_at": now(), "binding_path": str(args.binding.resolve()),
           "binding_repo_path": args.binding.resolve().relative_to(ROOT).as_posix(),
           "binding_sha256": binding_sha, "binding": binding, "state_path": state_relative,
           "registration_path": registration, "host": host_identity(),
           "schedule": schedule(), "cohorts": binding["cohorts"]}
    exclusive(ROOT / registration, registration_value(run))
    state.mkdir(parents=True, exist_ok=False)
    (state / "workers").mkdir()
    exclusive(state / "run.json", run)
    return {"state": str(state), "run_sha256": digest(run), "registration": registration,
            "next_worker": run["schedule"][0]["key"], "next": "Commit run.json and the one-time registration before claiming a worker."}


def registration_value(run):
    return {"binding_sha256": run["binding_sha256"], "run_identity_sha256": digest(run), "state_path": run["state_path"]}


def committed_bytes(path, commit="HEAD"):
    path = Path(path).resolve()
    require(path.read_bytes() == git("show", commit + ":" + path.relative_to(ROOT).as_posix()),
            "Saved execution evidence is not exactly committed: " + path.name)


def load_run(state, *, measuring=True):
    run = json.loads((Path(state) / "run.json").read_bytes())
    binding_path = ROOT / run["binding_repo_path"]
    binding = load_binding(binding_path, check_environment=measuring)
    require(run["protocol"] == VERSION and run["binding"] == binding
            and run["binding_sha256"] == sha(binding_path.read_bytes())
            and run["schedule"] == schedule() and run["cohorts"] == binding["cohorts"],
            "Saved run identity differs")
    require(json.loads((ROOT / run["registration_path"]).read_bytes()) == registration_value(run),
            "The one-time execution registration changed")
    committed_bytes(ROOT / run["registration_path"])
    committed_bytes(Path(state) / "run.json")
    if measuring:
        require(Path(state).resolve() == ROOT / run["state_path"], "Measured execution directory differs from its one-time registration")
        require(run["host"] == host_identity(), "Run must continue on its original host, boot and runtime")
    return run


def write_archive(directory, stem, raw):
    """Transport binary-safe archives as bounded, independently hashed text parts."""
    compressed = gzip.compress(raw, mtime=0)
    encoded = base64.b64encode(compressed)
    parts = []
    for i, start in enumerate(range(0, len(encoded), CHUNK_CHARS)):
        name = stem + ("" if len(encoded) <= CHUNK_CHARS else f".part{i:03d}") + ".gz.b64"
        content = encoded[start:start + CHUNK_CHARS] + b"\n"
        exclusive_bytes(Path(directory) / name, content)
        parts.append({"path": name, "bytes": len(content), "sha256": sha(content)})
    return {"encoding": "concatenated-base64-of-gzip-mtime0", "raw_sha256": sha(raw), "raw_bytes": len(raw),
            "gzip_sha256": sha(compressed), "gzip_bytes": len(compressed), "parts": parts}


def read_archive(directory, descriptor):
    require(descriptor["encoding"] == "concatenated-base64-of-gzip-mtime0" and descriptor["parts"],
            "Unknown/empty archive encoding")
    encoded = []
    seen = set()
    for item in descriptor["parts"]:
        name = item["path"]
        require(name == Path(name).name and name not in seen, "Unsafe/duplicate archive part")
        seen.add(name)
        content = (Path(directory) / name).read_bytes()
        require(len(content) == item["bytes"] and sha(content) == item["sha256"], "Archive part bytes changed")
        encoded.append(content.strip())
    compressed = base64.b64decode(b"".join(encoded), validate=True)
    require(len(compressed) == descriptor["gzip_bytes"] and sha(compressed) == descriptor["gzip_sha256"],
            "Compressed archive hash differs")
    raw = gzip.decompress(compressed)
    require(len(raw) == descriptor["raw_bytes"] and sha(raw) == descriptor["raw_sha256"], "Raw archive hash differs")
    return raw


class Ledger:
    def __init__(self, path):
        self.stream = Path(path).open("x", encoding="utf-8")
        self.seq = 0

    def write(self, value):
        self.stream.write(dump(value) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def start(self, config, identity):
        seq = self.seq
        self.seq += 1
        self.write({"event": "started", "seq": seq, "config": config, "query_id": identity, "at": now()})
        return seq

    def finish(self, seq, config, row):
        self.write({"event": "finished", "seq": seq, "config": config, "row": row, "at": now()})

    def close(self):
        self.stream.close()


def memory_sample():
    try:
        return {"available": True, **rss()}
    except (OSError, KeyError, ValueError) as error:
        return {"available": False, "reason": type(error).__name__, "rss_bytes": None, "hwm_bytes": None}


def mcp_memory_sample():
    try:
        return server_rss()
    except (OSError, KeyError, ValueError) as error:
        return {"available": False, "reason": type(error).__name__, "rss_bytes": None, "hwm_bytes": None}


async def mcp_configuration(data, config, order, db_path, work, src, counters, sources, pages, report, ledger):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import recall_payload, _json
    env = {**os.environ, "PYTHONPATH": str(src.resolve()), "PYTHONDONTWRITEBYTECODE": "1",
           "MEMORY_BOOK_HOME": str(work / "isolated-home"), "MEMORY_BOOK_DB": str(db_path)}
    if env.get("TIKTOKEN_CACHE_DIR"):
        env["TIKTOKEN_CACHE_DIR"] = str(Path(env["TIKTOKEN_CACHE_DIR"]).resolve())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(db_path), "mcp"], env=env, cwd=str(work))
    cases, rows, session = {q.id: q for q in data.queries}, [], {}
    report["mcp_sessions"][config["id"]] = session
    with sqlite3.connect(db_path) as cache:
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        begin = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                session["startup_to_initialize_ms"] = (time.perf_counter_ns() - begin) / 1e6
                tools = await client.list_tools()
                schema, instructions = tools.model_dump_json(exclude_none=True), initialized.instructions or ""
                session.update(tool_schema_sha256=sha(schema.encode()), instructions_sha256=sha(instructions.encode()),
                    initialization_tokens={name: {"tool_schema": c.count(schema), "instructions": c.count(instructions)}
                                           for name, c in counters.items()})
                for identity in order:
                    case = cases[identity]
                    cache.execute("DELETE FROM recall_cache")
                    cache.commit()
                    before = cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                    require(before == 0, "MCP cache was not empty before timing")
                    arguments = {"query": case.query, "project": case.project, "budget_chars": config["budget_chars"], "limit": 5}
                    if config["budget_tokens"] is not None:
                        arguments.update(budget_tokens=config["budget_tokens"], tokenizer=config["tokenizer"])
                    seq = ledger.start(config["id"], identity)
                    begin = time.perf_counter_ns()
                    result = await client.call_tool("recall_memory", arguments)
                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                    require(not result.isError and all(p.type == "text" for p in result.content), "MCP error/unexpected content")
                    payload = "\n".join(part.text for part in result.content)
                    response = json.loads(payload)
                    cached = cache.execute("SELECT payload FROM recall_cache").fetchall()
                    require(len(cached) == 1, "MCP must preserve its normal one full native cache write")
                    native = json.loads(cached[0][0])
                    row = make_row(case, response, elapsed, payload, result.model_dump_json(exclude_none=True),
                        native, config, counters, sources, pages, before, len(cached),
                        report["source"]["runtime_sha256"], _json(recall_payload(native)))
                    ledger.finish(seq, config["id"], row)
                    rows.append(row)
                    require(not any(row["invariants"].values()), "MCP source/budget/cache invariant failed")
                session["memory_after_calls"] = mcp_memory_sample()
                session["storage_live"] = storage(cache, db_path)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
    return rows


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def verify_memory(sample):
    require(type(sample.get("available")) is bool, "Memory availability is not explicit")
    if sample["available"]:
        require(all(type(sample.get(k)) is int and sample[k] >= 0 for k in ("rss_bytes", "hwm_bytes")),
                "Available memory sample has invalid byte counts")
    else:
        require(isinstance(sample.get("reason"), str) and sample["reason"]
                and sample.get("rss_bytes") is None and sample.get("hwm_bytes") is None,
                "Unknown memory must retain its reason and null costs")


def verify_worker(w, run, ledger, operations):
    item = next((x for x in run["schedule"] if x["key"] == w.get("key")), None)
    require(item is not None and all(w.get(k) == v for k, v in item.items()), "Unexpected worker identity")
    require(w["status"] == "completed" and w["error"] is None, "Started/failed worker is not reusable")
    source = run["binding"]["sources"][item["label"]]
    require(w["run_identity_sha256"] == digest(run) and w["source"] == w["source_after"] == source
            and w["evaluator_files_after"] == run["binding"]["evaluator_files"]
            and w["host_after"] == run["host"], "Worker source/evaluator/host identity changed")
    cohort = run["cohorts"][item["cohort"]]
    require(w["dataset_sha256"] == cohort["sha256"] and w["session_count"] == cohort["sessions"], "Worker dataset differs")
    require(w["all_replayed_sessions_skipped"] is True and w["native_recall_cache_rows"] == 0
            and w["indexed_content"] == w["indexed_content_after_replay"] == w["indexed_content_after_calls"],
            "Ingestion, source index or native-cache invariant failed")
    require(all(finite(w[k]) for k in RESOURCE_FIELDS), "Invalid resource duration")
    verify_memory(w["native_memory_after_ingestion"])
    verify_memory(w["native_memory_after_calls"])
    require(sha(operations) == w["operations_sha256"], "Ingestion operation ledger hash changed")
    operation_events = [json.loads(line) for line in operations.splitlines()]
    require(len(operation_events) == 4, "Ingestion operation ledger incomplete/extra")
    for index, (phase, field) in enumerate((("fresh", "fresh_ingestion"), ("unchanged", "unchanged_reingestion"))):
        begin, end = operation_events[index * 2:index * 2 + 2]
        require(begin["event"] == "started" and end["event"] == "finished"
                and begin["phase"] == end["phase"] == phase
                and begin["sessions"] == end["sessions"] == cohort["sessions"]
                and end["wall_ms"] == w[field + "_ms"]
                and end["results_sha256"] == w[field + "_results_sha256"],
                "Ingestion/replay duration, result hash or session denominator differs from ledger")
    require(len(w["configurations"]) == len(CONFIGURATIONS), "Incomplete configuration axis")
    expected_events = []
    for index, (cell, config) in enumerate(zip(w["configurations"], CONFIGURATIONS)):
        require({k: cell[k] for k in config} == config, "Configuration changed")
        require([r["query_id"] for r in cell["rows"]] == query_order(cohort["query_ids_original_order"], item["round"], index),
                "Missing, duplicate, or reordered queries")
        require(cell["latency"] == latency_summary([r["wall_ms"] for r in cell["rows"]]), "Latency summary differs")
        mcp = config["surface"] == "official-sdk-mcp-stdio"
        for row in cell["rows"]:
            require(finite(row["wall_ms"]) and row["wall_ms"] > 0 and row["engine_source_sha256"] == source["runtime_sha256"],
                    "Invalid sample timing/source")
            require(set(row["invariants"]) == set(INVARIANTS) and not any(row["invariants"].values()), "Response invariant failed")
            require(row["cache_rows_before"] == 0 and row["cache_rows_after"] == int(mcp), "Cache policy differs")
            require(type(row["context_chars"]) is int and 0 <= row["context_chars"] <= config["budget_chars"]
                    and type(row["result_count"]) is int and 0 <= row["result_count"] <= 5, "Result/character bound differs")
            require(set(row["tokens"]) == set(ENCODINGS), "Reference tokenizer axis differs")
            for costs in row["tokens"].values():
                require(set(costs) == {"context", "response_text", "response_envelope_json"}, "Token surface axis differs")
                require(all(type(costs[k]) is int and costs[k] >= 0 for k in ("context", "response_text")), "Invalid token cost")
                require((type(costs["response_envelope_json"]) is int and costs["response_envelope_json"] >= 0)
                        if mcp else costs["response_envelope_json"] is None, "Envelope cost boundary differs")
            if config["budget_tokens"] is not None:
                count = row["tokens"]["cl100k_base"]["context"]
                metadata = {"budget_tokens": config["budget_tokens"], "tokenizer": "cl100k_base",
                            "tokenizer_version": "0.12.0", "context_tokens": count}
                require(count <= config["budget_tokens"] and row["token_metadata"] == {"native": metadata, "response": metadata},
                        "Exact token budget/metadata differs")
            else:
                require(row["token_metadata"] is None, "Unexpected token metadata")
            for field in ("payload_sha256", "native_payload_sha256", "context_sha256"):
                require(isinstance(row[field], str) and HASH.fullmatch(row[field]), "Complete payload hash missing")
            require((isinstance(row["envelope_sha256"], str) and HASH.fullmatch(row["envelope_sha256"]))
                    if mcp else row["envelope_sha256"] is None, "MCP envelope hash missing/wrong surface")
            expected_events.append((config["id"], row))
    for suffix in ("char4000", "token1024"):
        native = next(c for c in w["configurations"] if c["id"] == "native-" + suffix)
        mcp = next(c for c in w["configurations"] if c["id"] == "mcp-" + suffix)
        hashes = {r["query_id"]: r["native_payload_sha256"] for r in native["rows"]}
        require(all(hashes[r["query_id"]] == r["native_payload_sha256"] for r in mcp["rows"]), "MCP full provenance differs from native")
    require(set(w["mcp_sessions"]) == {"mcp-char4000", "mcp-token1024"}, "MCP session axis incomplete")
    for session in w["mcp_sessions"].values():
        require(finite(session["startup_to_initialize_ms"]), "MCP startup duration missing")
        verify_memory(session["memory_after_calls"])
        for key in ("tool_schema_sha256", "instructions_sha256"):
            require(HASH.fullmatch(session[key]), "MCP initialization hash missing")
    require(sha(ledger) == w["ledger_sha256"], "Attempt ledger hash changed")
    events = [json.loads(line) for line in ledger.splitlines()]
    require(len(events) == 2 * len(expected_events), "Incomplete/extra attempt ledger")
    for seq, (config, row) in enumerate(expected_events):
        start, end = events[2 * seq:2 * seq + 2]
        require(start["event"] == "started" and end["event"] == "finished"
                and start["seq"] == end["seq"] == seq and start["config"] == end["config"] == config
                and start["query_id"] == row["query_id"] and end["row"] == row, "Ledger does not match the complete worker")
    return len(expected_events)


def load_worker(state, item, run):
    directory = Path(state) / "workers"
    summary = json.loads((directory / (item["key"] + ".summary.json")).read_bytes())
    report = json.loads(read_archive(directory, summary["report_archive"]))
    ledger = read_archive(directory, summary["ledger_archive"])
    operations = read_archive(directory, summary["operations_archive"])
    local_ledger = directory / (item["key"] + ".attempts.jsonl")
    if local_ledger.exists():
        require(local_ledger.read_bytes() == ledger, "Local and exported ledgers differ")
    local_operations = directory / (item["key"] + ".operations.jsonl")
    if local_operations.exists():
        require(local_operations.read_bytes() == operations, "Local and exported operation ledgers differ")
    count = verify_worker(report, run, ledger, operations)
    require(summary["key"] == item["key"] and summary["status"] == "completed"
            and summary["error"] == report["error"] and summary["calls"] == count
            and summary["run_identity_sha256"] == digest(run), "Worker summary identity/count differs")
    return report


def completed_prefix(state, run, *, compact=False):
    workers, gap = [], False
    directory = Path(state) / "workers"
    for item in run["schedule"]:
        stem = directory / item["key"]
        summary = Path(str(stem) + ".summary.json")
        started = Path(str(stem) + ".started.json")
        claimed = Path(str(stem) + ".claimed.json")
        if summary.exists():
            require(not gap and started.exists() and claimed.exists(), "Completed workers do not form a claimed prefix")
            require(json.loads(claimed.read_bytes()) == claim_value(item, run), "Worker claim differs")
            marker = json.loads(started.read_bytes())
            require(marker["claim"] == claim_value(item, run), "Worker started marker differs")
            report = load_worker(state, item, run)
            workers.append({"key": report["key"]} if compact else report)
            del report
        else:
            require(not started.exists(), "Incomplete started worker preserved; never remeasure: " + item["key"])
            require(not any(directory.glob(item["key"] + ".attempts.*"))
                    and not any(directory.glob(item["key"] + ".operations.*"))
                    and not any(directory.glob(item["key"] + ".json*")),
                    "Unclaimed/orphan worker result preserved; never remeasure: " + item["key"])
            if claimed.exists():
                require(not gap and json.loads(claimed.read_bytes()) == claim_value(item, run), "Claim is outside untouched suffix head")
            gap = True
    return workers


def claim_value(item, run):
    return {"worker": item, "run_identity_sha256": digest(run), "binding_sha256": run["binding_sha256"]}


def verify_publication(state, run, completed, item, commit, claim_path):
    """Check exact committed bytes; the caller separately verifies remote publication."""
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Claim commit must be a full SHA")
    require(git("rev-parse", "HEAD").decode().strip() == commit, "Worker HEAD must be the verified claim commit")
    expected = Path(state) / "workers" / (item["key"] + ".claimed.json")
    require(claim_path == expected.relative_to(ROOT).as_posix(), "Claim path is not this worker's canonical file")
    paths = [Path(state) / "run.json", ROOT / run["registration_path"], expected]
    for worker in completed:
        directory = Path(state) / "workers"
        summary_path = directory / (worker["key"] + ".summary.json")
        summary = json.loads(summary_path.read_bytes())
        paths.extend([summary_path, directory / (worker["key"] + ".claimed.json"),
                      directory / (worker["key"] + ".started.json")])
        for field in ("report_archive", "ledger_archive", "operations_archive"):
            paths.extend(directory / part["path"] for part in summary[field]["parts"])
    for path in paths:
        committed_bytes(path, commit)
    return {"commit": commit, "claim_path": claim_path,
            "verified_committed_files": {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in paths},
            "remote_observation": "Caller must verify the remote ref after publication; this offline check verifies Git objects."}


def claim(args):
    state = args.state_dir.resolve()
    run = load_run(state)
    with _lock(state / "execution"):
        workers = completed_prefix(state, run, compact=True)
        require(len(workers) < len(run["schedule"]), "All workers already completed")
        item = run["schedule"][len(workers)]
        require(item["key"] == args.worker, "Only the next untouched worker may be claimed")
        path = state / "workers" / (item["key"] + ".claimed.json")
        exclusive(path, claim_value(item, run))
    return {"claim": str(path), "sha256": sha(path.read_bytes()), "next": "Preserve this claim remotely before starting its worker."}


def worker(args):
    state = args.state_dir.resolve()
    run = load_run(state)
    with _lock(state / "execution"):
        completed = completed_prefix(state, run, compact=True)
        require(len(completed) < len(run["schedule"]), "All workers are already complete")
        item = run["schedule"][len(completed)]
        require(item["key"] == args.worker, "Only the next worker in the fixed schedule may run")
        directory, stem = state / "workers", item["key"]
        require(json.loads((directory / (stem + ".claimed.json")).read_bytes()) == claim_value(item, run), "Worker needs its exact saved claim")
        publication = verify_publication(state, run, completed, item, args.claim_commit, args.claim_path)
        exclusive(directory / (stem + ".started.json"), {"claim": claim_value(item, run), "at": now(), "pid": os.getpid()})
        report = {**item, "status": "started", "error": None, "started_at": now(),
                  "run_identity_sha256": digest(run), "source": run["binding"]["sources"][item["label"]],
                  "configurations": [], "mcp_sessions": {}, "publication": publication,
                  "resource_boundary": "Evaluator process includes source/tokenizer/result storage and prior-prefix verification; prior full worker reports are released before import. MCP child samples are separate."}
        ledger_path = directory / (stem + ".attempts.jsonl")
        ledger = Ledger(ledger_path)
        operation_path = directory / (stem + ".operations.jsonl")
        operations = Ledger(operation_path)
        work = state / "private" / stem
        work.mkdir(parents=True, exist_ok=False)
        src = Path(run["binding"]["source_paths"][item["label"]])
        error = None
        try:
            require("memory_book" not in sys.modules, "Fresh worker already imported a runtime")
            sys.path.insert(0, str(src))
            begin = time.perf_counter_ns()
            import memory_book
            from memory_book import MemoryBook
            report["runtime_import_ms"] = (time.perf_counter_ns() - begin) / 1e6
            require(Path(memory_book.__file__).resolve().parent == (src / "memory_book").resolve(), "Imported another runtime")
            locomo = Path(run["binding"]["locomo_path"])
            require(sha(locomo.read_bytes()) == run["binding"]["locomo_sha256"], "Dataset file changed")
            data = dataset(item["cohort"], locomo)
            ids = [q.id for q in data.queries]
            require(ids == run["cohorts"][item["cohort"]]["query_ids_original_order"], "Query order axis differs")
            report.update(dataset_sha256=data.fingerprint, session_count=len(data.sessions))
            db_path = work / "memory.db"
            begin = time.perf_counter_ns()
            with MemoryBook(db_path, cache_size=0) as book:
                report["native_open_ms"] = (time.perf_counter_ns() - begin) / 1e6
                for phase, field in (("fresh", "fresh_ingestion"), ("unchanged", "unchanged_reingestion")):
                    operations.write({"event": "started", "phase": phase, "at": now(), "sessions": len(data.sessions)})
                    begin = time.perf_counter_ns()
                    results = [book.ingest(session) for session in data.sessions]
                    report[field + "_ms"] = (time.perf_counter_ns() - begin) / 1e6
                    report[field + "_results_sha256"] = digest(results)
                    operations.write({"event": "finished", "phase": phase, "at": now(), "sessions": len(results),
                                      "wall_ms": report[field + "_ms"], "results_sha256": digest(results)})
                    if phase == "fresh":
                        report["native_memory_after_ingestion"] = memory_sample()
                        report["storage_after_ingestion_live"] = storage(book.db, db_path)
                        report["indexed_content"] = indexed_content(book.db)
                    else:
                        report["all_replayed_sessions_skipped"] = all(r.get("skipped") is True for r in results)
                        report["indexed_content_after_replay"] = indexed_content(book.db)
                        require(report["all_replayed_sessions_skipped"] and report["indexed_content"] == report["indexed_content_after_replay"],
                                "Unchanged replay modified indexed content or was not skipped")
                pages = {r["id"]: r["content"] for r in book.db.execute("SELECT id,content FROM pages")}
                sources, cases = original_turn_texts(data), {q.id: q for q in data.queries}
                begin = time.perf_counter_ns()
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    counter.count("Initialize reference tokenizer outside query timing.")
                report["reference_tokenizer_initialization_ms"] = (time.perf_counter_ns() - begin) / 1e6
                for index, config in enumerate(CONFIGURATIONS):
                    order = query_order(ids, item["round"], index)
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows = asyncio.run(mcp_configuration(data, config, order, db_path, work, src, counters, sources, pages, report, ledger))
                    else:
                        rows = []
                        for identity in order:
                            case = cases[identity]
                            before = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            require(before == 0, "Native cache not empty")
                            options = {"project": case.project, "budget_chars": config["budget_chars"], "limit": 5, "use_cache": False}
                            if config["budget_tokens"] is not None:
                                options.update(budget_tokens=config["budget_tokens"], tokenizer=config["tokenizer"])
                            seq = ledger.start(config["id"], identity)
                            begin = time.perf_counter_ns()
                            response = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - begin) / 1e6
                            response.pop("latency_ms")
                            after = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            row = make_row(case, response, elapsed, dump(response), None, response, config, counters,
                                sources, pages, before, after, report["source"]["runtime_sha256"])
                            ledger.finish(seq, config["id"], row)
                            rows.append(row)
                            require(not any(row["invariants"].values()), "Native source/budget/cache invariant failed")
                    report["configurations"].append({**config, "rows": rows, "latency": latency_summary([r["wall_ms"] for r in rows])})
                    exclusive(directory / (stem + "." + config["id"] + ".completed.json"),
                        {"config": config["id"], "calls": len(rows), "rows_sha256": digest(rows), "at": now()})
                    print(dump({"worker": stem, "configuration": config["id"], "calls": len(rows)}), flush=True)
                report["native_memory_after_calls"] = memory_sample()
                report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                report["indexed_content_after_calls"] = indexed_content(book.db)
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["storage_after_checkpoint"] = storage(book.db, db_path)
            report["source_after"] = source_identity(src, report["source"]["commit"])
            report["evaluator_files_after"] = files_identity()
            report["host_after"] = host_identity()
            report["status"] = "completed"
        except BaseException as caught:
            error = caught
            report["status"] = "failed"
            report["error"] = {"type": type(caught).__name__, "message": str(caught)}
        finally:
            ledger.close()
            operations.close()
            ledger_raw = ledger_path.read_bytes()
            report["ledger_sha256"] = sha(ledger_raw)
            report["operations_sha256"] = sha(operation_path.read_bytes())
            report["finished_at"] = now()
            if error is None:
                try:
                    verify_worker(report, run, ledger_raw, operation_path.read_bytes())
                except BaseException as caught:
                    error = caught
                    report["status"] = "failed"
                    report["error"] = {"type": type(caught).__name__, "message": str(caught)}
            report_archive = write_archive(directory, stem + ".json", raw_json(report))
            ledger_archive = write_archive(directory, stem + ".attempts.jsonl", ledger_raw)
            operations_archive = write_archive(directory, stem + ".operations.jsonl", operation_path.read_bytes())
            summary = {"key": stem, "status": report["status"], "error": report["error"],
                       "run_identity_sha256": digest(run), "calls": sum(len(c["rows"]) for c in report["configurations"]),
                       "report_archive": report_archive, "ledger_archive": ledger_archive,
                       "operations_archive": operations_archive}
            exclusive(directory / (stem + ".summary.json"), summary)
        if error is not None:
            raise error
    return {"worker": stem, "status": "completed", "calls": summary["calls"], "summary": str(directory / (stem + ".summary.json"))}


def stable_row(row):
    return {k: v for k, v in row.items() if k not in ("wall_ms", "engine_source_sha256")}


def assess(workers, run, *, partial=False):
    require([w["key"] for w in workers] == [i["key"] for i in run["schedule"][:len(workers)]], "Workers are not the complete prefix")
    complete = len(workers) == len(run["schedule"])
    require(partial or complete, "Full audit requires every registered worker")
    reference, pairs = {}, 0
    for w in workers:
        cohort = w["cohort"]
        stable_ingest = {key: w[key] for key in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256")}
        first = reference.setdefault((cohort, "ingestion"), stable_ingest)
        require(stable_ingest == first, "Version/round ingestion or indexed content differs")
        for session_name, session in w["mcp_sessions"].items():
            identity = {key: session[key] for key in ("tool_schema_sha256", "instructions_sha256", "initialization_tokens")}
            require(reference.setdefault(("mcp-initialization", session_name), identity) == identity,
                    "MCP schema/instructions/token initialization identity changed")
        for config in w["configurations"]:
            for row in config["rows"]:
                key = (cohort, config["id"], row["query_id"])
                require(reference.setdefault(key, stable_row(row)) == stable_row(row), "Complete non-timing output mismatch: " + str(key))
                if w["label"] == "candidate":
                    pairs += 1
    cells, rounds = [], []
    for cohort in run["cohorts"]:
        for config in CONFIGURATIONS:
            values = {label: [row["wall_ms"] for w in workers if w["cohort"] == cohort and w["label"] == label
                             for c in w["configurations"] if c["id"] == config["id"] for row in c["rows"]]
                      for label in ("baseline", "candidate")}
            if all(values.values()):
                a, b = latency_summary(values["baseline"]), latency_summary(values["candidate"])
                cells.append({"cohort": cohort, "configuration": config["id"], "baseline": a, "candidate": b,
                              "p50_change_pct": 100 * (b["p50_ms"] / a["p50_ms"] - 1),
                              "p95_change_pct": 100 * (b["p95_ms"] / a["p95_ms"] - 1)})
            for r in range(4):
                selected = {w["label"]: next(c["latency"] for c in w["configurations"] if c["id"] == config["id"])
                            for w in workers if w["cohort"] == cohort and w["round"] == r}
                if set(selected) == {"baseline", "candidate"}:
                    rounds.append({"round": r, "cohort": cohort, "configuration": config["id"], **selected})
    resources = []
    for cohort in run["cohorts"]:
        for field in RESOURCE_FIELDS:
            samples = {label: [w[field] for w in workers if w["cohort"] == cohort and w["label"] == label]
                       for label in ("baseline", "candidate")}
            if all(samples.values()):
                means = {label: statistics.fmean(values) for label, values in samples.items()}
                resources.append({"cohort": cohort, "field": field, "samples": samples, "means": means,
                                  "change_pct": 100 * (means["candidate"] / means["baseline"] - 1) if means["baseline"] else None})
        for session_name in ("mcp-char4000", "mcp-token1024"):
            samples = {label: [w["mcp_sessions"][session_name]["startup_to_initialize_ms"] for w in workers
                              if w["cohort"] == cohort and w["label"] == label] for label in ("baseline", "candidate")}
            if all(samples.values()):
                means = {label: statistics.fmean(values) for label, values in samples.items()}
                resources.append({"cohort": cohort, "field": session_name + ".startup_to_initialize_ms", "samples": samples,
                                  "means": means, "change_pct": 100 * (means["candidate"] / means["baseline"] - 1) if means["baseline"] else None})
    missing_memory = [{"worker": w["key"], "phase": phase, "reason": value.get("reason", "unavailable")}
        for w in workers for phase, value in [("native_after_ingestion", w["native_memory_after_ingestion"]),
            ("native_after_calls", w["native_memory_after_calls"]),
            *[(key, session["memory_after_calls"]) for key, session in w["mcp_sessions"].items()]] if not value["available"]]
    call_count = sum(len(c["rows"]) for w in workers for c in w["configurations"])
    expected_calls = sum(run["cohorts"][x["cohort"]]["queries"] * len(CONFIGURATIONS) for x in run["schedule"])
    require(not complete or call_count == expected_calls, "Full call denominator differs")
    targets = {r["cohort"]: r["change_pct"] <= -20 for r in resources
               if r["field"] == "unchanged_reingestion_ms" and r["change_pct"] is not None} if complete else {}
    return {"protocol": VERSION, "status": "complete-verified" if complete else "verified-prefix",
        "workers": len(workers), "expected_workers": len(run["schedule"]), "calls": call_count,
        "expected_calls": expected_calls, "candidate_output_pairs": pairs, "complete_output_equality": True,
        "cells": cells, "per_round": rounds, "resources": resources, "missing_memory_samples": missing_memory,
        "resource_evidence_complete": not missing_memory, "unchanged_import_20pct_target_by_cohort": targets,
        "interpretation": "One fixed candidate on old regression data; retain every cell and adverse result. No round-four acceptance gate, confidence claim, quality gain, or whole-product competitor ratio."}


def audit(args):
    state = args.state_dir.resolve()
    run = load_run(state, measuring=False)
    with _lock(state / "execution"):
        workers = completed_prefix(state, run)
        result = assess(workers, run, partial=args.partial)
        result["binding_sha256"] = run["binding_sha256"]
        result["run_identity_sha256"] = digest(run)
        result["worker_summary_hashes"] = {w["key"]: sha((state / "workers" / (w["key"] + ".summary.json")).read_bytes()) for w in workers}
        if args.output:
            exclusive(args.output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("bind", help="Freeze exact committed sources, evaluator, data and environment")
    p.add_argument("--baseline-src", type=Path, required=True)
    p.add_argument("--candidate-src", type=Path, required=True)
    p.add_argument("--baseline-commit", default=BASELINE_COMMIT)
    p.add_argument("--candidate-commit")
    p.add_argument("--locomo-path", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("init", help="Create a new immutable execution identity")
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--state-dir", type=Path, required=True)
    for name in ("claim", "worker"):
        p = commands.add_parser(name)
        p.add_argument("--state-dir", type=Path, required=True)
        p.add_argument("--worker", required=True)
        if name == "worker":
            p.add_argument("--claim-commit", required=True)
            p.add_argument("--claim-path", required=True)
    p = commands.add_parser("audit", help="Recompute saved results without retrieval")
    p.add_argument("--state-dir", type=Path, required=True)
    p.add_argument("--partial", action="store_true")
    p.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = {"bind": bind, "init": init, "claim": claim, "worker": worker, "audit": audit}[args.command](args)
    print(dump(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
