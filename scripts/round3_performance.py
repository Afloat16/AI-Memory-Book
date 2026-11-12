"""Registered round-three complete-payload performance comparison.

Only old synthetic61/public1015 data is accepted. Binding and an explicit run
command are required; importing this module or running tests never measures.
Completed workers are immutable. Resume can continue an untouched suffix on the
same boot, but an incomplete worker is preserved and never measured again.
"""
from __future__ import annotations

import argparse
import asyncio
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
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_default_recall import (dump, digest, indexed_content,
    numeric, rss, server_rss, sha, storage)
from benchmarks.native_budget_eval import source_errors
from benchmarks.resume import _lock
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import page_projection_errors
from benchmarks.token_compare import (ENCODINGS, TokenCounter,
    checkout_provenance, evidence_blocks, latency_summary, load_dataset)

PLAN = ROOT / "benchmarks/experiments/round3-plan.json"
PLAN_COMMIT = "2ce405408d323aac61fa9e9f536a704dd5f2b372"
BASELINE = "dd2f88be742ed330269e7dd5915b6f75089d7fef"
BASELINE_HASH = "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57"
VERSION = "round3-default-performance-1"
PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}
HELPERS = ("scripts/benchmark_default_recall.py", "benchmarks/__init__.py",
    "benchmarks/native_budget_eval.py", "benchmarks/semantic_eval.py",
    "benchmarks/component_eval.py", "benchmarks/token_compare.py",
    "benchmarks/run.py", "benchmarks/data.py", "benchmarks/public_data.py",
    "benchmarks/long_data.py", "benchmarks/transfer_data.py",
    "benchmarks/hotpot_data.py", "benchmarks/query_guard.py", "benchmarks/resume.py",
    "benchmarks/locomo_split.json")
TOOLS = ("scripts/round3_performance.py", "tests/test_round3_performance.py",
         ".github/workflows/round3-performance.yml")
INVARIANTS = ("cache_error", "source_span_errors", "source_scope_errors",
    "page_projection_errors", "context_reconstruction_error", "metadata_error",
    "character_budget_error", "token_budget_error", "token_metadata_error",
    "mcp_projection_error", "result_limit_error", "unexpected_policy")
RESOURCE_FIELDS = ("runtime_import_ms", "native_open_ms", "fresh_ingestion_ms",
    "unchanged_reingestion_ms", "mcp_startup_to_initialize_ms",
    "native_memory_after_ingestion.rss_bytes", "native_memory_after_ingestion.hwm_bytes",
    "native_memory_after_calls.rss_bytes", "native_memory_after_calls.hwm_bytes",
    "mcp_server_memory_after_calls.rss_bytes", "mcp_server_memory_after_calls.hwm_bytes")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value):
    return (dump(value) + "\n").encode()


def exclusive_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def atomic(path, value, *, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json_bytes(value)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(gzip.compress(raw, mtime=0) if compressed else raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return raw


def exclusive(path, value):
    exclusive_bytes(path, json_bytes(value))


def git(*args, root=ROOT):
    return subprocess.check_output(["git", *args], cwd=root, timeout=30)


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in (*HELPERS, *TOOLS)}


def load_plan():
    raw = PLAN.read_bytes()
    require(raw == git("show", PLAN_COMMIT + ":" + str(PLAN.relative_to(ROOT))),
            "The registered plan changed")
    plan = json.loads(raw)
    require(plan["baseline"]["commit"] == BASELINE and
            plan["baseline"]["runtime_sha256"] == BASELINE_HASH, "Wrong baseline")
    formal = plan["performance_candidate"]["formal"]
    require(formal["rounds"] == 4 and formal["calls"] == 47320 and
            formal["engine_order"] == [["baseline", "candidate"], ["candidate", "baseline"],
                                       ["candidate", "baseline"], ["baseline", "candidate"]],
            "Registered ABBA schedule changed")
    return plan


def source_identity(src):
    package = src.resolve() / "memory_book"
    provenance = checkout_provenance(package)
    require(provenance["commit_identifies_source"], "Runtime differs from its committed source")
    return {"commit": provenance["git_commit"], "runtime_sha256": engine_source_hash(package)}


def bind(args):
    plan = load_plan()
    require(args.baseline_src and args.candidate_src, "Binding needs both exact source checkouts")
    sources = {label: source_identity(path) for label, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == {"commit": BASELINE, "runtime_sha256": BASELINE_HASH},
            "Binding baseline differs from v0.3.0")
    tool_commit = git("rev-parse", "HEAD").decode().strip()
    hashes = file_hashes()
    for name, expected in hashes.items():
        require(sha(git("show", tool_commit + ":" + name)) == expected,
                "Commit evaluator and tests before binding: " + name)
    for name in HELPERS:
        require(sha(git("show", BASELINE + ":" + name)) == hashes[name],
                "A reused frozen helper changed: " + name)
    value = {"schema_version": 1, "evaluator": VERSION, "status": "frozen-before-formal-timing",
        "created_at": now(), "plan_sha256": sha(PLAN.read_bytes()),
        "sources": sources, "evaluator_commit": tool_commit, "evaluator_files": hashes,
        "packages": PACKAGES, "policy": "One registered candidate; preserve every attempt and all rounds."}
    exclusive(args.bind, value)
    print(json.dumps({"binding": str(args.bind), "sha256": sha(args.bind.read_bytes()),
                      "next": "Commit this binding before formal measurement."}))


def load_binding(path):
    value = json.loads(path.read_bytes())
    require(value["status"] == "frozen-before-formal-timing" and value["evaluator"] == VERSION,
            "Candidate is not frozen")
    require(value["plan_sha256"] == sha(PLAN.read_bytes()) and value["evaluator_files"] == file_hashes()
            and value["packages"] == PACKAGES, "Plan/evaluator/packages differ from binding")
    require(value["sources"]["baseline"] == {"commit": BASELINE, "runtime_sha256": BASELINE_HASH},
            "Binding baseline changed")
    relative = path.resolve().relative_to(ROOT).as_posix()
    require(path.read_bytes() == git("show", "HEAD:" + relative),
            "Commit the exact source binding before timing")
    for name, expected in value["evaluator_files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == expected,
                "Bound evaluator commit differs: " + name)
    return value


def host_identity():
    # Boot identity disallows pooling timings from a restarted/replacement VM.
    return {"boot_sha256": sha(Path("/proc/sys/kernel/random/boot_id").read_bytes()),
        "machine_sha256": sha(platform.node().encode()), "platform": platform.platform(),
        "processor": platform.processor(), "cpu_count": os.cpu_count(),
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}


def dataset(plan, name, locomo):
    require(name in plan["performance_candidate"]["formal"]["cohorts"], "Unregistered cohort")
    data = load_dataset("synthetic", 61, "development", 8, None, 0) if name == "synthetic61" else \
        load_dataset("locomo", 61, "heldout", 8, str(locomo), 0)
    expected = next(c for c in plan["cohorts"] if c["name"] == name)
    require(len(data.queries) == expected["queries"] and data.fingerprint == expected["sha256"],
            "Old regression input count or digest differs")
    return data


def schedule(plan):
    formal = plan["performance_candidate"]["formal"]
    return [{"key": f"r{repetition}-{cohort}-{label}", "round": repetition,
             "cohort": cohort, "label": label}
            for repetition, labels in enumerate(formal["engine_order"])
            for cohort in formal["cohorts"] for label in labels]


def query_order(ids, repetition, config_index):
    values = list(ids)
    random.Random(31061 + 1009 * repetition + config_index).shuffle(values)
    return values


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def make_row(case, response, elapsed, payload, envelope, native, config, counters,
             sources, pages, before, after, source_sha, projection=None):
    """Validate the actual response and cached full provenance without recall."""
    context = response["context"]
    tokens = {name: {"context": counter.count(context), "response_text": counter.count(payload),
                    "response_envelope_json": counter.count(envelope) if envelope is not None else None}
              for name, counter in counters.items()}
    mcp = config["surface"] == "official-sdk-mcp-stdio"
    scope_errors = sum(int(case.project is not None and item.get("breadcrumb", [{}])[0].get("id") != case.project)
                       + sum(int(ref.get("project") != item.get("breadcrumb", [{}])[0].get("id"))
                             for ref in item["source_refs"]) for item in native["results"])
    try:
        evidence_blocks(native)
        reconstruction_error = False
    except ValueError:
        reconstruction_error = True
    token_budget = config["budget_tokens"]
    invariants = {"cache_error": before != 0 or after != (1 if mcp else 0) or native.get("cache_hit") is not False,
        "source_span_errors": source_errors(native, sources), "source_scope_errors": scope_errors,
        "page_projection_errors": page_projection_errors(native, pages),
        "context_reconstruction_error": reconstruction_error,
        "metadata_error": response.get("context_chars") != len(context)
            or response.get("budget_chars") != config["budget_chars"] or native.get("query") != case.query
            or response["context"] != native["context"],
        "character_budget_error": len(context) > config["budget_chars"],
        "token_budget_error": token_budget is not None and tokens["cl100k_base"]["context"] > token_budget,
        "token_metadata_error": token_budget is not None and any((native.get("budget_tokens") != token_budget,
            native.get("tokenizer") != "cl100k_base", native.get("tokenizer_version") != "0.12.0",
            native.get("context_tokens") != tokens["cl100k_base"]["context"])),
        "mcp_projection_error": mcp and projection != payload,
        "result_limit_error": len(response["results"]) > 5 or len({x["id"] for x in response["results"]}) != len(response["results"]),
        "unexpected_policy": bool(native.get("semantic") or native.get("project_local_fts_statistics"))}
    return {"query_id": case.id, "category": case.category, "wall_ms": elapsed,
        "engine_source_sha256": source_sha, "payload_sha256": sha(payload.encode()),
        "native_payload_sha256": digest(native), "context_sha256": sha(context.encode()),
        "envelope_sha256": sha(envelope.encode()) if envelope is not None else None,
        "response_utf8_bytes": len(payload.encode()),
        "envelope_utf8_bytes": len(envelope.encode()) if envelope is not None else None,
        "context_chars": len(context), "result_count": len(response["results"]),
        "cache_rows_before": before, "cache_rows_after": after,
        "tokens": tokens, "invariants": invariants}


class Ledger:
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf-8")
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


async def mcp_configuration(data, config, order, db_path, work, src, counters, sources,
                            pages, report, ledger):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import recall_payload, _json
    environment = {**os.environ, "PYTHONPATH": str(src.resolve()), "PYTHONDONTWRITEBYTECODE": "1",
                   "MEMORY_BOOK_HOME": str(work / "isolated-home"), "MEMORY_BOOK_DB": str(db_path)}
    if environment.get("TIKTOKEN_CACHE_DIR"):
        environment["TIKTOKEN_CACHE_DIR"] = str(Path(environment["TIKTOKEN_CACHE_DIR"]).resolve())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(db_path), "mcp"], env=environment, cwd=str(work))
    cases = {case.id: case for case in data.queries}
    rows = []
    with sqlite3.connect(db_path) as cache:
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        begin = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                report["mcp_startup_to_initialize_ms"] = (time.perf_counter_ns() - begin) / 1e6
                tools = await client.list_tools()
                schema = tools.model_dump_json(exclude_none=True)
                instructions = initialized.instructions or ""
                report["mcp_tool_schema_sha256"] = sha(schema.encode())
                report["mcp_instructions_sha256"] = sha(instructions.encode())
                report["mcp_initialization_tokens"] = {name: {"tool_schema": c.count(schema),
                    "instructions": c.count(instructions)} for name, c in counters.items()}
                for identity in order:
                    case = cases[identity]
                    cache.execute("DELETE FROM recall_cache")
                    cache.commit()
                    before = cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                    require(before == 0, "MCP result cache was not empty before timing")
                    seq = ledger.start(config["id"], identity)
                    begin = time.perf_counter_ns()
                    result = await client.call_tool("recall_memory", {"query": case.query,
                        "project": case.project, "budget_chars": config["budget_chars"], "limit": 5})
                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                    require(not result.isError and all(p.type == "text" for p in result.content), "MCP returned an error or unexpected content")
                    payload = "\n".join(part.text for part in result.content)
                    response = json.loads(payload)
                    cached = cache.execute("SELECT payload FROM recall_cache").fetchall()
                    require(len(cached) == 1, "MCP did not leave exactly one full native provenance record")
                    native = json.loads(cached[0][0])
                    row = make_row(case, response, elapsed, payload, result.model_dump_json(exclude_none=True),
                        native, config, counters, sources, pages, before, len(cached),
                        report["source"]["runtime_sha256"], _json(recall_payload(native)))
                    ledger.finish(seq, config["id"], row)
                    rows.append(row)
                    require(not any(row["invariants"].values()), "MCP provenance/budget/cache invariant failed")
                report["mcp_server_memory_after_calls"] = server_rss()
                require(report["mcp_server_memory_after_calls"]["available"], "Live MCP process RSS unavailable")
                report["storage_after_mcp_live"] = storage(cache, db_path)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
    return rows


def worker(args, plan, binding):
    state = args.state_dir.resolve()
    run = json.loads((state / "run.json").read_bytes())
    item = next(s for s in run["schedule"] if s["key"] == args.worker)
    require(run["binding_sha256"] == sha(args.binding.read_bytes()) and run["host"] == host_identity(),
            "Worker binding/host differs from controller")
    marker = state / "workers" / (item["key"] + ".started.json")
    require(json.loads(marker.read_bytes()) == {"worker": item, "run_identity_sha256": digest(run)},
            "Worker has no matching controller intent")
    output = state / "workers" / (item["key"] + ".json.gz")
    ledger_path = state / "workers" / (item["key"] + ".attempts.jsonl")
    require(not output.exists() and not ledger_path.exists(), "A worker attempt already exists; never repeat it")
    src = Path(run["source_paths"][item["label"]])
    expected = binding["sources"][item["label"]]
    require(source_identity(src) == expected, "Worker runtime source differs")
    sys.path.insert(0, str(src))
    begin = time.perf_counter_ns()
    import memory_book
    from memory_book import MemoryBook
    imported_ms = (time.perf_counter_ns() - begin) / 1e6
    require(Path(memory_book.__file__).parent.resolve() == (src / "memory_book").resolve(),
            "Worker imported a different runtime")
    data = dataset(plan, item["cohort"], args.locomo_path)
    ids = [case.id for case in data.queries]
    require(ids == run["cohorts"][item["cohort"]]["query_ids_original_order"], "Worker query identities differ")
    report = {**item, "status": "started", "started_at": now(), "source": expected,
        "run_identity_sha256": digest(run), "runtime_import_ms": imported_ms,
        "dataset_sha256": data.fingerprint, "configurations": [], "error": None}
    ledger = Ledger(ledger_path)
    try:
        with tempfile.TemporaryDirectory(prefix="round3-perf-") as temporary:
            work = Path(temporary)
            db_path = work / "memory.db"
            begin = time.perf_counter_ns()
            with MemoryBook(db_path, cache_size=0) as book:
                report["native_open_ms"] = (time.perf_counter_ns() - begin) / 1e6
                begin = time.perf_counter_ns()
                ingested = [book.ingest(session) for session in data.sessions]
                report["fresh_ingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["fresh_ingestion_results_sha256"] = digest(ingested)
                report["native_memory_after_ingestion"] = rss()
                report["storage_after_ingestion_live"] = storage(book.db, db_path)
                begin = time.perf_counter_ns()
                replayed = [book.ingest(session) for session in data.sessions]
                report["unchanged_reingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["unchanged_reingestion_results_sha256"] = digest(replayed)
                report["all_replayed_sessions_skipped"] = all(row["skipped"] for row in replayed)
                report["indexed_content"] = indexed_content(book.db)
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                sources = original_turn_texts(data)
                begin = time.perf_counter_ns()
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    counter.count("Initialize reference tokenizer before query timing.")
                report["reference_tokenizer_initialization_ms"] = (time.perf_counter_ns() - begin) / 1e6
                cases = {case.id: case for case in data.queries}
                for index, config in enumerate(plan["performance_candidate"]["formal"]["configs"]):
                    order = query_order(ids, item["round"], index)
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows = asyncio.run(mcp_configuration(data, config, order, db_path, work, src,
                            counters, sources, pages, report, ledger))
                    else:
                        rows = []
                        for identity in order:
                            case = cases[identity]
                            before = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            require(before == 0, "Native result cache was not empty before timing")
                            options = {"project": case.project, "budget_chars": config["budget_chars"],
                                       "limit": 5, "use_cache": False}
                            if config["budget_tokens"] is not None:
                                options.update(budget_tokens=config["budget_tokens"], tokenizer="cl100k_base")
                            seq = ledger.start(config["id"], identity)
                            begin = time.perf_counter_ns()
                            response = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - begin) / 1e6
                            response.pop("latency_ms")  # The sole excluded native response field.
                            after = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            row = make_row(case, response, elapsed, dump(response), None, response, config,
                                counters, sources, pages, before, after, expected["runtime_sha256"])
                            ledger.finish(seq, config["id"], row)
                            rows.append(row)
                            require(not any(row["invariants"].values()), "Native provenance/budget/cache invariant failed")
                    report["configurations"].append({**config, "rows": rows,
                        "latency": latency_summary([r["wall_ms"] for r in rows])})
                    atomic(output, report, compressed=True)
                report["native_memory_after_calls"] = rss()
                report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                report["indexed_content_after_calls"] = indexed_content(book.db)
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["storage_after_checkpoint"] = storage(book.db, db_path)
        report["source_after"] = source_identity(src)
        require(report["source_after"] == expected, "Runtime source changed while measuring")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        ledger.close()
        raw_ledger = ledger_path.read_bytes()
        ledger_path.with_suffix(".jsonl.gz").write_bytes(gzip.compress(raw_ledger, mtime=0))
        report["ledger_sha256"] = sha(raw_ledger)
        report["finished_at"] = now()
        atomic(output, report, compressed=True)
    return 0


def stable_row(row):
    return {key: value for key, value in row.items() if key not in ("wall_ms", "engine_source_sha256")}


def verify_worker(w, run, plan, *, ledger=None):
    """Reject missing/duplicate rows, fake summaries and interrupted ledgers."""
    require(w["status"] == "completed" and w["error"] is None, "Incomplete worker is not reusable")
    item = next(x for x in run["schedule"] if x["key"] == w["key"])
    require(all(w[k] == v for k, v in item.items()) and w["run_identity_sha256"] == digest(run),
            "Worker identity differs")
    expected = run["binding"]["sources"][w["label"]]
    require(w["source"] == w["source_after"] == expected, "Worker source binding differs")
    cohort = run["cohorts"][w["cohort"]]
    require(w["dataset_sha256"] == cohort["sha256"], "Worker cohort differs")
    require(w["all_replayed_sessions_skipped"] and w["native_recall_cache_rows"] == 0
            and w["indexed_content"] == w["indexed_content_after_calls"], "Ingest/index/cache invariant failed")
    configs = plan["performance_candidate"]["formal"]["configs"]
    require(len(w["configurations"]) == len(configs), "Worker configuration axis is incomplete")
    expected_ledger = []
    for index, (c, spec) in enumerate(zip(w["configurations"], configs, strict=True)):
        require({k: c[k] for k in spec} == spec, "Worker configuration changed")
        order = query_order(cohort["query_ids_original_order"], w["round"], index)
        require([r["query_id"] for r in c["rows"]] == order, "Worker dropped, duplicated or reordered queries")
        require(c["latency"] == latency_summary([r["wall_ms"] for r in c["rows"]]), "Worker latency summary changed")
        for row in c["rows"]:
            require(finite(row["wall_ms"]) and row["wall_ms"] > 0
                    and row["engine_source_sha256"] == expected["runtime_sha256"],
                    "Invalid timing/source row")
            require(set(row["invariants"]) == set(INVARIANTS) and not any(row["invariants"].values()),
                    "Response provenance/budget/cache invariant failed")
            require(row["cache_rows_before"] == 0 and row["cache_rows_after"] ==
                    (1 if spec["surface"] == "official-sdk-mcp-stdio" else 0), "Cache counts differ")
            require(row["context_chars"] <= spec["budget_chars"] and row["result_count"] <= 5,
                    "Returned character/result bound differs")
            require(set(row["tokens"]) == set(ENCODINGS), "Reference tokenizer axis differs")
            for costs in row["tokens"].values():
                require(set(costs) == {"context", "response_text", "response_envelope_json"}, "Token surface axis differs")
                require(all(type(costs[k]) is int and costs[k] >= 0 for k in ("context", "response_text")), "Invalid token counts")
                require((type(costs["response_envelope_json"]) is int and costs["response_envelope_json"] >= 0)
                        if spec["surface"] == "official-sdk-mcp-stdio" else costs["response_envelope_json"] is None,
                        "Envelope token boundary differs")
            if spec["budget_tokens"] is not None:
                require(row["tokens"]["cl100k_base"]["context"] <= spec["budget_tokens"], "Token bound exceeded")
            for field in ("payload_sha256", "native_payload_sha256", "context_sha256"):
                require(isinstance(row[field], str) and len(row[field]) == 64, "Missing complete-payload digest")
            require((isinstance(row["envelope_sha256"], str) and len(row["envelope_sha256"]) == 64)
                    if spec["surface"] == "official-sdk-mcp-stdio" else row["envelope_sha256"] is None,
                    "MCP envelope identity is missing or native surface is mislabeled")
            expected_ledger.append((spec["id"], row))
    native_default = next(c for c in w["configurations"] if c["id"] == "native-char4000")
    mcp_default = next(c for c in w["configurations"] if c["id"] == "mcp-char4000")
    native_hashes = {row["query_id"]: row["native_payload_sha256"] for row in native_default["rows"]}
    require(all(native_hashes[row["query_id"]] == row["native_payload_sha256"] for row in mcp_default["rows"]),
            "MCP cached provenance differs from the paired full native default")
    require(w["mcp_server_memory_after_calls"]["available"], "MCP resource sample missing")
    for field in RESOURCE_FIELDS:
        require(finite(nested(w, field)), "Resource sample missing or invalid: " + field)
    if ledger is not None:
        require(sha(ledger) == w["ledger_sha256"], "Attempt ledger bytes changed")
        events = [json.loads(line) for line in ledger.splitlines()]
        require(len(events) == 2 * len(expected_ledger), "Interrupted or extra attempt ledger")
        for seq, (config, row) in enumerate(expected_ledger):
            begin, end = events[seq * 2:seq * 2 + 2]
            require(begin["event"] == "started" and end["event"] == "finished"
                    and begin["seq"] == end["seq"] == seq and begin["config"] == end["config"] == config
                    and begin["query_id"] == row["query_id"] and end["row"] == row,
                    "Ledger call/response does not match original worker")
    return sum(len(c["rows"]) for c in w["configurations"])


def nested(value, path):
    for key in path.split("."):
        value = value[key]
    return value


def validation(report):
    issues, canonical, total = [], {}, 0
    run, plan = report["run"], report["plan"]
    workers = report["workers"]
    if [w["key"] for w in workers] != [w["key"] for w in schedule(plan)]:
        issues.append("missing_duplicate_or_reordered_workers")
    for w in workers:
        try:
            total += verify_worker(w, run, plan)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(w.get("key", "unknown") + ":" + str(error))
            continue
        for field in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256",
                      "mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            key = (w["cohort"], field)
            if key in canonical and canonical[key] != w[field]:
                issues.append(w["key"] + ":" + field)
            canonical.setdefault(key, w[field])
        for c in w["configurations"]:
            for row in c["rows"]:
                key = (w["cohort"], c["id"], row["query_id"])
                value = stable_row(row)
                if key in canonical and canonical[key] != value:
                    issues.append(w["key"] + ":payload:" + c["id"] + ":" + row["query_id"])
                canonical.setdefault(key, value)
    if total != plan["performance_candidate"]["formal"]["calls"]:
        issues.append("registered_call_count")
    if report["error"] or not report["evaluator_unchanged"]:
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(schedule(plan)), "timed_calls": total,
            "expected_calls": plan["performance_candidate"]["formal"]["calls"]}


def comparisons(report):
    rows = []
    formal = report["plan"]["performance_candidate"]["formal"]
    for cohort in formal["cohorts"]:
        for spec in formal["configs"]:
            samples = {label: [r for w in report["workers"] if w["cohort"] == cohort and w["label"] == label
                for c in w["configurations"] if c["id"] == spec["id"] for r in c["rows"]]
                for label in ("baseline", "candidate")}
            by_round = []
            for repetition in range(formal["rounds"]):
                values = {w["label"]: c["latency"] for w in report["workers"]
                    if w["cohort"] == cohort and w["round"] == repetition
                    for c in w["configurations"] if c["id"] == spec["id"]}
                by_round.append({"round": repetition, **values})
            engines = {}
            for label, values in samples.items():
                partition = lambda first: [r["wall_ms"] for w in report["workers"]
                    if w["cohort"] == cohort and w["label"] == label and ((w["round"] == 0) == first)
                    for c in w["configurations"] if c["id"] == spec["id"] for r in c["rows"]]
                engines[label] = {"latency": latency_summary([r["wall_ms"] for r in values]),
                    "first_round_latency": latency_summary(partition(True)),
                    "repeat_rounds_latency": latency_summary(partition(False)),
                    "response_utf8_bytes": numeric([r["response_utf8_bytes"] for r in values]),
                    "context_chars": numeric([r["context_chars"] for r in values]),
                    "tokens": {name: {field: numeric([r["tokens"][name][field] for r in values])
                        if values and values[0]["tokens"][name][field] is not None else None
                        for field in ("context", "response_text", "response_envelope_json")} for name in ENCODINGS}}
            changes = {metric: 100 * (engines["candidate"]["latency"][metric] /
                         engines["baseline"]["latency"][metric] - 1)
                       if engines["baseline"]["latency"][metric] and engines["candidate"]["latency"][metric] is not None else None
                       for metric in ("p50_ms", "p95_ms", "mean_ms")}
            rows.append({"cohort": cohort, **spec, **engines, "candidate_change_percent": changes, "rounds": by_round})
    return rows


def acceptance(report, compared):
    if not report["validation"]["passed"]:
        return {"accepted": False, "numeric_gate_passed": False, "reason": "incomplete_or_invalid", "resource_review": []}
    require(all(c[label]["latency"][metric] > 0 for c in compared for label in ("baseline", "candidate")
                for metric in ("p50_ms", "p95_ms")), "Zero clock samples cannot support a speed claim")
    ratios = [c["candidate"]["latency"]["p95_ms"] / c["baseline"]["latency"]["p95_ms"] for c in compared]
    geometric_improvement = 100 * (1 - math.exp(statistics.fmean(math.log(r) for r in ratios)))
    public_improvements = [-c["candidate_change_percent"]["p95_ms"] for c in compared
                           if c["cohort"] == "public1015" and c["surface"] == "native"]
    regressions = [{"cohort": c["cohort"], "config": c["id"], "metric": key, "change_percent": c["candidate_change_percent"][key]}
                  for c in compared for key in ("p50_ms", "p95_ms") if c["candidate_change_percent"][key] > 5 + 1e-9]
    resources, review = [], []
    for cohort in report["plan"]["performance_candidate"]["formal"]["cohorts"]:
        for field in RESOURCE_FIELDS:
            values = {label: [nested(w, field) for w in report["workers"] if w["cohort"] == cohort and w["label"] == label]
                      for label in ("baseline", "candidate")}
            old, new = (statistics.fmean(values[label]) for label in ("baseline", "candidate"))
            change = 100 * (new / old - 1) if old else (0.0 if new == 0 else None)
            row = {"cohort": cohort, "metric": field, "baseline": numeric(values["baseline"]),
                   "candidate": numeric(values["candidate"]), "mean_change_percent": change}
            resources.append(row)
            if change is None or change > 10 + 1e-9:
                review.append(row)
    passed = geometric_improvement >= 5 - 1e-9 and max(public_improvements) >= 10 - 1e-9 and not regressions
    return {"accepted": passed and not review, "numeric_gate_passed": passed,
        "geometric_mean_p95_improvement_percent": geometric_improvement,
        "best_public_native_p95_improvement_percent": max(public_improvements),
        "regressions_above_five_percent": regressions, "resource_comparisons": resources,
        "resource_review": review, "resource_rule": "Any increase above 10% requires an explicit cause and independent review; no automatic override."}


def summary(report, compressed, raw):
    value = {k: v for k, v in report.items() if k not in ("workers", "run")}
    value["run"] = {k: v for k, v in report["run"].items() if k != "cohorts"}
    value["run"]["cohorts"] = {k: {f: v for f, v in c.items() if not f.startswith("query_ids")}
                                for k, c in report["run"]["cohorts"].items()}
    value["workers"] = [{k: v for k, v in w.items() if k != "configurations"} for w in report["workers"]]
    value.update(full_report_sha256=sha(raw), compressed_report_sha256=sha(compressed))
    return value


def save_report(path, report):
    report["validation"] = validation(report)
    report["comparisons"] = comparisons(report)
    report["acceptance"] = acceptance(report, report["comparisons"])
    raw = atomic(path, report, compressed=True)
    atomic(path.with_name(path.name.removesuffix(".json.gz") + ".summary.json"), summary(report, path.read_bytes(), raw))


def load_completed(state, item, run, plan):
    prefix = state / "workers" / item["key"]
    report = json.loads(gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes()))
    ledger = Path(str(prefix) + ".attempts.jsonl").read_bytes()
    require(gzip.decompress(Path(str(prefix) + ".attempts.jsonl.gz").read_bytes()) == ledger,
            "Original and public attempt ledgers differ")
    verify_worker(report, run, plan, ledger=ledger)
    return report


def artifact_hashes(state, run):
    result = {}
    for item in run["schedule"]:
        for suffix in (".started.json", ".json.gz", ".attempts.jsonl", ".attempts.jsonl.gz"):
            relative = "workers/" + item["key"] + suffix
            path = state / relative
            if path.is_file():
                result[relative] = sha(path.read_bytes())
    return result


def resume_prefix(state, run, plan):
    """Only an immutable complete prefix can be skipped; no retries of rows."""
    complete, pending = [], False
    for item in run["schedule"]:
        prefix = state / "workers" / item["key"]
        marker = Path(str(prefix) + ".started.json")
        present = list(prefix.parent.glob(prefix.name + ".*"))
        if not present:
            pending = True
            continue
        require(not pending and marker.exists(), "Worker states are not a complete scheduled prefix")
        require(json.loads(marker.read_bytes()) == {"worker": item, "run_identity_sha256": digest(run)},
                "Saved worker intent differs")
        try:
            complete.append(load_completed(state, item, run, plan))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ValueError("Incomplete/invalid worker preserved; do not remeasure: " + item["key"]) from error
    return complete


class CheckpointPublicationError(RuntimeError):
    """Stop measurement when a durable checkpoint cannot be published."""


def publication_identity(args):
    """Restrict writes to this Actions attempt's fresh result directory/ref."""
    if not args.publish_branch:
        return None
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    workflow_commit = os.environ.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[1-9][0-9]*", run_id) and re.fullmatch(r"[1-9][0-9]*", attempt)
            and re.fullmatch(r"[0-9a-f]{40}", workflow_commit), "Publication requires an exact Actions attempt")
    require(os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book",
            "Publish only from the authorized repository")
    suffix = run_id + "-" + attempt
    branch = "validation/v031-round3-performance-" + suffix
    relative = "benchmarks/reports/round3-performance-" + suffix
    require(args.publish_branch == branch and args.output.resolve() == (ROOT / relative / "report.json.gz").resolve(),
            "Publication branch/output must identify this exact Actions attempt")
    require(git("remote", "get-url", "origin").decode().strip() in
            ("https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git",
             "git@github.com:Afloat16/AI-Memory-Book.git"), "Publication origin is not the authorized repository")
    git("merge-base", "--is-ancestor", workflow_commit, "HEAD")
    changed = git("diff", "--name-only", workflow_commit, "HEAD").decode().splitlines()
    require(all(name.startswith(relative + "/") for name in changed),
            "Checkpoint commits may change only this attempt's result directory")
    return {"branch": branch, "directory": relative, "workflow_commit": workflow_commit,
            "run_id": run_id, "run_attempt": attempt}


def export_checkpoint(args):
    """Copy the audit-ready state; retain both original and compressed ledgers."""
    state, public = args.state_dir.resolve(), args.output.resolve().parent
    public.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "checkpoint.json"):
        if (state / name).is_file():
            shutil.copyfile(state / name, public / name)
    history = state / "controller-attempts"
    if history.is_dir():
        shutil.copytree(history, public / "controller-attempts", dirs_exist_ok=True)
    for source in sorted((state / "workers").glob("*")):
        if source.is_file() and source.name.endswith((".started.json", ".json.gz", ".attempts.jsonl", ".attempts.jsonl.gz")):
            destination = public / "workers" / source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)


def publish_checkpoint(args, run, phase):
    """Synchronous Git I/O outside timing; never retry or force a ref update."""
    try:
        identity = publication_identity(args)
        require(identity is not None and identity == run["publication"], "Publication identity changed")
        export_checkpoint(args)
        prefix = identity["directory"] + "/"
        staged = git("diff", "--cached", "--name-only").decode().splitlines()
        require(all(name.startswith(prefix) for name in staged), "Unrelated staged changes must not enter the result commit")
        subprocess.run(["git", "add", "--", identity["directory"]], cwd=ROOT, check=True)
        if git("diff", "--cached", "--name-only").strip():
            subprocess.run(["git", "-c", "user.name=github-actions[bot]", "-c",
                "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m",
                "bench: preserve round3 performance " + phase], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + identity["branch"]], cwd=ROOT, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise CheckpointPublicationError("Durable checkpoint publication failed: " + str(error)) from error


def checkpoint(args, report):
    run, state = report["run"], args.state_dir.resolve()
    report["evaluator_unchanged"] = file_hashes() == run["evaluator_files"] and sha(PLAN.read_bytes()) == run["plan_sha256"]
    report["worker_artifacts_sha256"] = artifact_hashes(state, run)
    save_report(args.output, report)
    atomic(state / "checkpoint.json", {"run_identity_sha256": digest(run),
        "completed_workers": [w["key"] for w in report["workers"]],
        "report_sha256": sha(args.output.read_bytes()), "status": report["status"],
        "error": report["error"], "at": now()})


def controller_locked(args, plan, binding):
    require(args.baseline_src and args.candidate_src and args.locomo_path and args.output and args.state_dir,
            "Measurement needs both sources, old LoCoMo input, output and state directory")
    require(args.output.name.endswith(".json.gz"), "Use a new run-specific .json.gz output")
    host = host_identity()
    require(host["packages"] == PACKAGES, "Install the bound SDK/tokenizer versions before timing")
    paths = {label: str(path.resolve()) for label, path in
             (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    for label, path in paths.items():
        require(source_identity(Path(path)) == binding["sources"][label], "Source path differs from binding")
    cohorts = {}
    for name in plan["performance_candidate"]["formal"]["cohorts"]:
        data = dataset(plan, name, args.locomo_path)
        ids = [c.id for c in data.queries]
        require(len(ids) == len(set(ids)), "Duplicate input query IDs")
        cohorts[name] = {"sha256": data.fingerprint, "queries": len(ids),
                         "query_ids": sorted(ids), "query_ids_original_order": ids}
    publication = publication_identity(args)
    run = {"evaluator": VERSION, "plan_sha256": sha(PLAN.read_bytes()), "binding": binding,
        "binding_sha256": sha(args.binding.read_bytes()), "evaluator_files": file_hashes(),
        "source_paths": paths, "host": host, "cohorts": cohorts, "schedule": schedule(plan),
        "locomo_file_sha256": sha(args.locomo_path.read_bytes()), "output": str(args.output.resolve()),
        "workflow_commit": os.environ.get("GITHUB_SHA"), "publication": publication}
    state = args.state_dir.resolve()
    if args.resume:
        require(json.loads((state / "run.json").read_bytes()) == run,
                "Resume must use the exact binding, data, paths, evaluator, boot and packages")
    else:
        require(not args.output.exists() and not state.exists(), "Existing attempt must be preserved; use --resume only for a complete prefix")
        exclusive(state / "run.json", run)
    history = state / "controller-attempts"
    attempt = 1
    while (history / f"{attempt:04d}.started.json").exists():
        attempt += 1
    exclusive(history / f"{attempt:04d}.started.json", {"at": now(), "run_identity_sha256": digest(run)})
    # A resumed controller never erases the prior failure or partial aggregate.
    # Worker files themselves are always immutable after completion.
    if args.output.exists():
        exclusive_bytes(history / f"{attempt:04d}.prior.json.gz", args.output.read_bytes())
        previous_summary = args.output.with_name(args.output.name.removesuffix(".json.gz") + ".summary.json")
        if previous_summary.exists():
            exclusive_bytes(history / f"{attempt:04d}.prior.summary.json", previous_summary.read_bytes())
    report = {"schema_version": 1, "evaluator": VERSION, "plan": plan, "run": run,
        "started_at": now(), "controller_attempt": attempt, "workers": [], "error": None, "evaluator_unchanged": False,
        "worker_artifacts_sha256": {},
        "status": "running", "interpretation": {
            "quality": "Old regression complete-payload equality; no new-domain or generated-answer evidence.",
            "native": "Complete uncached API call; only latency_ms excluded from canonical native payload.",
            "mcp": "Actual SDK stdio response and envelope unchanged; clear cache before timing, include normal write cost. Audit full provenance from that call's cache record without another recall.",
            "timing": "Registered ABBA schedule, four fresh process rounds pooled. First/repeat means round 0 versus rounds 1-3, not cold OS caches.",
            "resources": "Linux process snapshots and high-water values; native evaluator imports and live MCP child are separately labeled. Fresh ingest/replay measured every worker, identical indexed-content digests required.",
            "resume": "Same-boot completed worker prefix only; no resampling of an incomplete or completed worker."}}
    publication_failed = False
    try:
        report["workers"] = resume_prefix(state, run, plan)
        for item in run["schedule"][len(report["workers"]):]:
            exclusive(state / "workers" / (item["key"] + ".started.json"),
                      {"worker": item, "run_identity_sha256": digest(run)})
            checkpoint(args, report)
            if publication is not None:
                publish_checkpoint(args, run, item["key"] + " started")
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                "--binding", str(args.binding.resolve()), "--state-dir", str(state),
                "--locomo-path", str(args.locomo_path.resolve())]
            subprocess.run(command, check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
            report["workers"].append(load_completed(state, item, run, plan))
            checkpoint(args, report)
            if publication is not None:
                publish_checkpoint(args, run, item["key"] + " completed")
            print(json.dumps({"worker_completed": item["key"], "completed_workers": len(report["workers"])}), flush=True)
        report["status"] = "measurements_completed"
    except BaseException as error:
        report["status"] = "failed_or_interrupted"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        publication_failed = isinstance(error, CheckpointPublicationError)
    finally:
        report["finished_at"] = now()
        checkpoint(args, report)
        if publication is not None and not publication_failed:
            try:
                publish_checkpoint(args, run, "controller finished")
            except CheckpointPublicationError as error:
                report["status"] = "failed_or_interrupted"
                report["error"] = {"type": type(error).__name__, "message": str(error)}
                checkpoint(args, report)
        exclusive(history / f"{attempt:04d}.finished.json", {"run_identity_sha256": digest(run),
            "status": report["status"], "error": report["error"], "at": now(),
            "report_sha256": sha(args.output.read_bytes()), "validation": report["validation"],
            "accepted": report["acceptance"]["accepted"]})
        if publication is not None:
            # Keep local/public failure evidence for the workflow's always-run
            # export/upload step even if the one synchronous push failed.
            export_checkpoint(args)
    print(json.dumps({"output": str(args.output), "validation": report["validation"],
                      "accepted": report["acceptance"]["accepted"]}))
    return 2 if not report["validation"]["passed"] else (0 if report["acceptance"]["accepted"] else 3)


def controller(args, plan, binding):
    require(args.state_dir is not None, "A new state directory is required")
    args.state_dir.resolve().parent.mkdir(parents=True, exist_ok=True)
    # Stable OS lock releases after process death; concurrent resume cannot
    # launch a duplicate worker or overwrite an active controller's checkpoint.
    with _lock(args.state_dir.resolve().with_name(args.state_dir.name + ".controller")):
        return controller_locked(args, plan, binding)


def audit(path, state):
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    expected = json.loads(path.with_name(path.name.removesuffix(".json.gz") + ".summary.json").read_bytes())
    require(report["validation"] == validation(report), "Stored validation differs")
    require(report["comparisons"] == comparisons(report), "Stored comparisons differ")
    require(report["acceptance"] == acceptance(report, report["comparisons"]), "Stored acceptance differs")
    require(expected == summary(report, compressed, raw), "Summary or raw hashes differ")
    require(report["plan"] == load_plan() and report["run"]["evaluator_files"] == file_hashes(),
            "Auditor must use the original registered plan/evaluator")
    require(report["validation"]["passed"], "Measurement is incomplete or invalid; original remains preserved")
    require(json.loads((state / "run.json").read_bytes()) == report["run"], "Original run identity differs")
    require(artifact_hashes(state, report["run"]) == report["worker_artifacts_sha256"], "Original worker artifact hashes differ")
    original_workers = resume_prefix(state, report["run"], report["plan"])
    require(original_workers == report["workers"], "Aggregate differs from original workers and every attempt ledger")
    return {"verified": True, "validation": report["validation"], "accepted": report["acceptance"]["accepted"],
            "full_report_sha256": sha(raw), "retrieval_calls_executed": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path, help="Write a NEW binding, then commit it before measuring")
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--publish-branch", help="Optional exact run-specific validation ref; stop if any checkpoint push fails")
    parser.add_argument("--audit", type=Path, help="Verify existing source-free rows without retrieval")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.audit:
        require(args.state_dir is not None, "Audit needs the saved original state/worker/ledger directory")
        print(json.dumps(audit(args.audit, args.state_dir)))
        return 0
    if args.bind:
        bind(args)
        return 0
    require(args.binding is not None, "An exact committed source binding is required; no default candidate")
    plan, binding = load_plan(), load_binding(args.binding)
    return worker(args, plan, binding) if args.worker else controller(args, plan, binding)


if __name__ == "__main__":
    raise SystemExit(main())
