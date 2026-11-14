"""Round-six frozen, same-output native and actual-MCP performance measurements.

Only explicit source/evaluator bindings may measure. Development and formal
runs have separate immutable claims; every completed or interrupted observation
is retained. Importing this module and running its pure fixtures do not measure.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round4_performance as legacy
from scripts.round4_performance import (ENCODINGS, INVARIANTS, Ledger, PACKAGES,
    TokenCounter, atomic, dataset, digest, dump, exclusive, exclusive_bytes,
    finite, git, host_identity, indexed_content, latency_summary, make_row,
    mcp_configuration, nested, now, numeric, original_turn_texts, query_order,
    require, rss, sha, source_identity, stable_row, storage)
from benchmarks.resume import _lock
from benchmarks.semantic_eval import source_snapshot

VERSION = "round6-default-performance-1"
PLAN = ROOT / "benchmarks/experiments/round6-plan.json"
PLAN_COMMIT = "afbb3233e16b80b3c0e5e76ab19466188abf41b4"
BASELINE = {"commit": "796cedfd1f5368144037a1fb72292b8d13884b8c",
    "runtime_sha256": "55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45"}
STAGES = ("development-native", "development-mcp", "formal")
CONFIGURATIONS = legacy.CONFIGURATIONS
ORDERS = [["baseline", "candidate"], ["candidate", "baseline"],
          ["candidate", "baseline"], ["baseline", "candidate"]]
COHORTS = {"synthetic61": {"queries": 168,
    "sha256": "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26"},
    "public1015": {"queries": 1015,
    "sha256": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"}}
THRESHOLDS = {"geometric_mean_p95_improvement": 10,
    "at_least_one_public_native_token_p95_improvement": 15,
    "public_mcp_token1024_p95_improvement": 10,
    "maximum_pooled_p50_p95_regression": 5, "resource_mean_increase_review": 10}
MEMO_FIELDS = ("allocated", "entry_limit", "text_byte_limit", "entries", "text_bytes",
    "hits", "misses", "evictions", "invalidations", "oversized_bypasses", "uncertified_bypasses")
MEMO_COUNTERS = MEMO_FIELDS[5:]
SOURCE_TABLES = ("projects", "chapters", "sessions", "turns", "sections", "pages")
HOST_TIMESTAMP_COLUMNS = {"projects": ["created_at", "updated_at"],
    "chapters": ["updated_at"], "sessions": ["updated_at"]}
NEW_FILES = ("scripts/round6_performance.py", "scripts/round6_audit_performance.py",
    "scripts/round6_host.py", "scripts/round6_hotpot_compatibility.py",
    "tests/test_round6_benchmark.py", "tests/test_round6_benchmark_audit.py",
    ".github/workflows/round6-development.yml", ".github/workflows/round6-performance.yml")
TOOLS = (*legacy.HELPERS, "scripts/round4_performance.py", *NEW_FILES)


def validate_plan(plan):
    require(plan.get("schema_version") == 1, "Wrong plan schema")
    require({key: plan["baseline"].get(key) for key in BASELINE} == BASELINE,
            "Use the published v0.3.3 release as baseline")
    formal = plan["performance_candidate"]["formal"]
    require(formal["cohorts"] == list(COHORTS) and formal["configs"] == list(CONFIGURATIONS)
            and formal["rounds"] == 4 and formal["engine_order"] == ORDERS
            and formal["calls"] == 56784, "Registered formal matrix differs")
    require(plan["thresholds_percent"] == THRESHOLDS, "Registered gates differ")
    require({c["name"]: {k: c[k] for k in ("queries", "sha256")} for c in plan["cohorts"]}
            == COHORTS, "Regression cohorts differ")
    return plan


def load_plan():
    require(PLAN.read_bytes() == git("show", PLAN_COMMIT + ":" + str(PLAN.relative_to(ROOT))), "Preregistered round-six plan changed")
    return validate_plan(json.loads(PLAN.read_bytes()))


def measurement_spec(plan, stage):
    require(stage in STAGES, "Unregistered measurement stage")
    spec = copy.deepcopy(plan["performance_candidate"]["formal"])
    if stage != "formal":
        spec.update(rounds=2, engine_order=ORDERS[:2])
        if stage == "development-native":
            spec["configs"] = [c for c in spec["configs"] if c["surface"] == "native"]
            spec["calls"] = 18928
        else:
            spec["cohorts"] = ["public1015"]
            spec["configs"] = [c for c in spec["configs"] if c["id"] == "mcp-token1024"]
            spec["calls"] = 4060
    return spec


def schedule(spec):
    return legacy.schedule({"performance_candidate": {"formal": spec}})


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in sorted(TOOLS)}


def runtime_hash(commit):
    prefix = "src/memory_book/"
    names = sorted(name for name in git("ls-tree", "-r", "--name-only", commit, prefix)
                   .decode().splitlines() if name.endswith(".py"))
    require(bool(names), "Bound source tree has no Python files")
    value = hashlib.sha256()
    for name in names:
        value.update(name.removeprefix(prefix).encode() + b"\0")
        value.update(git("show", commit + ":" + name) + b"\0")
    return value.hexdigest()


def source_semantics(connection):
    """All six source tables; explicitly omit only host-maintained timestamps."""
    result = {}
    for table in SOURCE_TABLES:
        columns = [r[1] for r in connection.execute(f"PRAGMA table_info({table})")]
        excluded = HOST_TIMESTAMP_COLUMNS.get(table, [])
        require(set(excluded) <= set(columns), "Source schema lost a declared timestamp field")
        retained = [name for name in columns if name not in excluded]
        rows = [list(row) for row in connection.execute(
            "SELECT " + ",".join('"' + name + '"' for name in retained) + f" FROM {table} ORDER BY id")]
        result[table] = {"columns": retained, "excluded_host_columns": excluded,
                         "rows": len(rows), "sha256": digest(rows)}
    return result


def checked_relative(path):
    original = Path(path)
    require(not original.is_symlink(), "Refuse symbolic evidence file")
    path = original.resolve()
    require(path.is_relative_to(ROOT) and path.is_file(), "Unsafe/missing evidence file")
    return path.relative_to(ROOT).as_posix()


def committed_file(path, commit="HEAD"):
    name = checked_relative(path)
    require(path.read_bytes() == git("show", commit + ":" + name), "Commit exact evidence before binding: " + name)
    return {"path": name, "sha256": sha(path.read_bytes())}


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def formal_evidence(args, sources):
    """Bind both completed diagnostics and the final source compatibility check."""
    evidence = {}
    for stage, name in (("development-native", "native_development"), ("development-mcp", "mcp_development")):
        path, audit_path = getattr(args, name), getattr(args, name + "_audit")
        require(path is not None and audit_path is not None, "Formal binding needs both development reports and independent audits")
        report, audit = read_json(path), read_json(audit_path)
        require(report["evaluator"] == VERSION and report["run"]["stage"] == stage
                and report["run"]["binding"]["sources"] == sources
                and report["status"] == "measurements_completed" and report["validation"]["passed"],
                "Development evidence incomplete or from another source")
        expected_calls = measurement_spec(load_plan(), stage)["calls"]
        require(audit.get("passed") is True and audit.get("audit") == "round6-independent-saved-observations-1"
                and audit["report_sha256"] == sha(path.read_bytes()) and audit["sources"] == sources and audit["stage"] == stage
                and audit["timed_calls"] == expected_calls and audit["ledger_events"] == 2 * expected_calls
                and audit["complete_output_pairs"] == expected_calls // 2 and audit["no_new_measurements"] is True
                and report["validation"]["timed_calls"] == expected_calls,
                "Development independent audit does not bind the original report")
        evidence[stage] = {"report": committed_file(path), "audit": committed_file(audit_path)}
    path = args.compatibility
    require(path is not None, "Formal binding needs final-source historical compatibility")
    report = read_json(path)
    require(report["status"] == "passed" and report["expected_calls"] == 2304
            and len(report["rows"]) == 2304 and all(r["status"] == "match" for r in report["rows"])
            and {k: report["candidate"][k] for k in sources["candidate"]} == sources["candidate"]
            and report["runtime_sha256_after"] == sources["candidate"]["runtime_sha256"],
            "Compatibility evidence incomplete or from another final source")
    ledger = path.with_suffix("").with_suffix(".attempts.jsonl.gz")
    raw = gzip.decompress(ledger.read_bytes())
    require(sha(raw) == report["attempt_ledger_sha256"], "Compatibility ledger changed")
    events = [json.loads(line) for line in raw.splitlines()]
    require(len(events) == 4608, "Compatibility ledger has missing/extra attempts")
    for sequence, row in enumerate(report["rows"]):
        start, finish = events[2 * sequence:2 * sequence + 2]
        require(start["event"] == "started" and finish["event"] == "finished"
                and row["sequence"] == sequence and {k: v for k, v in finish.items() if k != "event"} == row
                and all(row[k] == v for k, v in start.items() if k != "event")
                and row["expected_payload_sha256"] == row["actual_payload_sha256"], "Compatibility ledger/output differs")
    evidence["compatibility"] = {"report": committed_file(path), "ledger": committed_file(ledger)}
    return evidence


def bind(args):
    plan = load_plan()
    require(args.baseline_src and args.candidate_src and args.stage in STAGES, "Both exact sources and a stage are required")
    name = args.bind.resolve().relative_to(ROOT).as_posix()
    require(name.startswith("benchmarks/experiments/round6-") and name.endswith("-binding.json"), "Use a new round-six binding")
    sources = {label: source_identity(path) for label, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == BASELINE and sources["candidate"]["runtime_sha256"] != BASELINE["runtime_sha256"],
            "A substantive changed candidate and the exact release baseline are required")
    commit = git("rev-parse", "HEAD").decode().strip()
    hashes = file_hashes()
    for path, expected in {**hashes, str(PLAN.relative_to(ROOT)): sha(PLAN.read_bytes())}.items():
        require(sha(git("show", commit + ":" + path)) == expected, "Commit evaluator/plan before binding: " + path)
    for path in (*legacy.HELPERS, "scripts/round4_performance.py"):
        require(sha(git("show", BASELINE["commit"] + ":" + path)) == hashes[path], "Immutable historical helper changed: " + path)
    evidence = formal_evidence(args, sources) if args.stage == "formal" else {}
    value = {"schema_version": 1, "evaluator": VERSION, "stage": args.stage,
        "status": "frozen-before-measurement", "created_at": now(), "plan_commit": PLAN_COMMIT,
        "plan_sha256": sha(PLAN.read_bytes()), "sources": sources, "evaluator_commit": commit,
        "evaluator_files": hashes, "packages": PACKAGES, "measurement": measurement_spec(plan, args.stage),
        "evidence": evidence,
        "policy": "One execution per source pair and stage, independent of binding filename; retain every sample and interruption."}
    exclusive(args.bind, value)
    print(json.dumps({"binding": name, "sha256": sha(args.bind.read_bytes()), "stage": args.stage,
                      "sources": sources, "next": "Commit this binding before invoking its first hosted run."}))


def load_binding(path):
    plan, value = load_plan(), read_json(path)
    require(value.get("schema_version") == 1 and value["evaluator"] == VERSION
            and value["status"] == "frozen-before-measurement" and value["stage"] in STAGES,
            "Wrong round-six binding")
    require(value["sources"]["baseline"] == BASELINE
            and set(value["sources"]) == {"baseline", "candidate"}
            and value["sources"]["candidate"]["runtime_sha256"] != BASELINE["runtime_sha256"], "Bound sources differ")
    for source in value["sources"].values():
        require(re.fullmatch(r"[0-9a-f]{40}", source["commit"]) is not None
                and runtime_hash(source["commit"]) == source["runtime_sha256"], "Bound source Git bytes differ")
    require(value["plan_commit"] == PLAN_COMMIT and value["plan_sha256"] == sha(PLAN.read_bytes()) and value["packages"] == PACKAGES
            and value["evaluator_files"] == file_hashes()
            and value["measurement"] == measurement_spec(plan, value["stage"]), "Bound evaluator/plan/matrix changed")
    require(PLAN.read_bytes() == git("show", value["plan_commit"] + ":" + str(PLAN.relative_to(ROOT))), "Plan provenance differs")
    committed_file(path)
    for name, expected in value["evaluator_files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == expected, "Evaluator provenance differs: " + name)
    require(set(value["evidence"]) == ({"development-native", "development-mcp", "compatibility"}
            if value["stage"] == "formal" else set()), "Missing formal evidence or unexpected diagnostic prerequisites")
    for stage in value["evidence"].values():
        for record in stage.values():
            require(sha((ROOT / record["path"]).read_bytes()) == record["sha256"]
                    and sha(git("show", value["evaluator_commit"] + ":" + record["path"])) == record["sha256"],
                    "Bound diagnostic or compatibility evidence changed")
    return value


def memo_diagnostics():
    return {"entry_limit": 2048, "text_byte_limit": 2097152,
        "boundary": "Both sources start empty and retain counts naturally across native settings. Read-only snapshots outside timing; every MCP configuration starts a fresh actual SDK server. No query prewarming.",
        "configurations": []}


def check_memo_snapshot(snapshot):
    require(snapshot.get("available") is True and set(snapshot) == {"available", *MEMO_FIELDS}, "Missing native memo diagnostics")
    require(all(type(snapshot[n]) is int and snapshot[n] >= 0 for n in MEMO_FIELDS), "Invalid native memo counters")
    require(snapshot["allocated"] in (0, 1) and snapshot["entry_limit"] == 2048 and snapshot["text_byte_limit"] == 2097152
            and snapshot["entries"] <= 2048 and snapshot["text_bytes"] <= 2097152, "Memo exceeds original registered bounds")
    dynamic = [n for n in MEMO_FIELDS if n not in ("entry_limit", "text_byte_limit")]
    require(snapshot["allocated"] or all(snapshot[n] == 0 for n in dynamic), "Unallocated memo is not empty")


def native_memo_snapshot(book, label):
    require(label in ("baseline", "candidate"), "Unknown source label")
    method = getattr(book, "_token_memo_snapshot", None)
    require(callable(method), "Both sources must expose the same read-only private observation API")
    snapshot = {"available": True, **method()}
    check_memo_snapshot(snapshot)
    return snapshot


def verify_native_memo(report, configurations):
    diagnostics = report["native_token_count_memo"]
    require({k: diagnostics[k] for k in ("entry_limit", "text_byte_limit", "boundary")} ==
            {k: memo_diagnostics()[k] for k in ("entry_limit", "text_byte_limit", "boundary")}, "Memo observation boundary changed")
    native = [c for c in configurations if c["surface"] == "native"]
    records = diagnostics["configurations"]
    require([r["id"] for r in records] == [c["id"] for c in native], "Native memo axis differs")
    previous = None
    for config, record in zip(native, records, strict=True):
        require(record["first_query_id"] == config["rows"][0]["query_id"], "Memo first-call query differs")
        snapshots = [record[k] for k in ("before", "after_first_call", "after")]
        for snapshot in snapshots:
            check_memo_snapshot(snapshot)
        require(snapshots[0] == previous if previous is not None else snapshots[0]["allocated"] == 0,
                "Both sources require an empty initial memo and natural state continuity")
        if config["budget_tokens"] is None:
            require(snapshots[0] == snapshots[1] == snapshots[2], "Character calls warmed token memo")
        for before, after in zip(snapshots, snapshots[1:]):
            require(after["allocated"] >= before["allocated"] and all(after[k] >= before[k] for k in MEMO_COUNTERS),
                    "Native memo cumulative counters decreased")
        previous = snapshots[-1]


def resource_fields(spec):
    fields = ["runtime_import_ms", "native_open_ms", "fresh_ingestion_ms", "unchanged_reingestion_ms",
        "native_memory_after_ingestion.rss_bytes", "native_memory_after_ingestion.hwm_bytes",
        "native_memory_after_calls.rss_bytes", "native_memory_after_calls.hwm_bytes"]
    stores = ["storage_after_ingestion_live", "storage_after_checkpoint"]
    for config in spec["configs"]:
        if config["surface"] == "official-sdk-mcp-stdio":
            prefix = "mcp_sessions." + config["id"] + "."
            fields += [prefix + "mcp_startup_to_initialize_ms", prefix + "mcp_server_memory_after_calls.rss_bytes",
                       prefix + "mcp_server_memory_after_calls.hwm_bytes"]
            stores.append(prefix + "storage_after_mcp_live")
    for prefix in stores:
        fields += [prefix + ".logical_db_bytes", *(prefix + ".files_bytes." + name for name in ("db", "wal", "shm"))]
    return fields


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
    configs = run["measurement"]["configs"]
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
                metadata = {"budget_tokens": spec["budget_tokens"], "tokenizer": spec["tokenizer"],
                    "tokenizer_version": PACKAGES["tiktoken"], "context_tokens": row["tokens"]["cl100k_base"]["context"]}
                require(row["token_metadata"] == {"native": metadata, "response": metadata},
                        "Native/returned token metadata differs from the actual configured limit and count")
            else:
                require(row["token_metadata"] is None, "Character configuration has unexpected token metadata")
            for field in ("payload_sha256", "native_payload_sha256", "context_sha256"):
                require(isinstance(row[field], str) and len(row[field]) == 64, "Missing complete-payload digest")
            require((isinstance(row["envelope_sha256"], str) and len(row["envelope_sha256"]) == 64)
                    if spec["surface"] == "official-sdk-mcp-stdio" else row["envelope_sha256"] is None,
                    "MCP envelope identity is missing or native surface is mislabeled")
            expected_ledger.append((spec["id"], row))
    for suffix in ("char4000", "token1024"):
        if not {"native-" + suffix, "mcp-" + suffix} <= {c["id"] for c in configs}:
            continue
        native_default = next(c for c in w["configurations"] if c["id"] == "native-" + suffix)
        mcp_default = next(c for c in w["configurations"] if c["id"] == "mcp-" + suffix)
        native_hashes = {row["query_id"]: row["native_payload_sha256"] for row in native_default["rows"]}
        require(all(native_hashes[row["query_id"]] == row["native_payload_sha256"] for row in mcp_default["rows"]),
                "MCP cached provenance differs from the paired full native " + suffix)
    expected_sessions = {c["id"] for c in configs if c["surface"] == "official-sdk-mcp-stdio"}
    require(set(w["mcp_sessions"]) == expected_sessions, "MCP session axis is incomplete")
    for identity, session in w["mcp_sessions"].items():
        require(set(session) == set(legacy.MCP_SESSION_FIELDS), "MCP session cost/schema record is incomplete")
        require(session["mcp_server_memory_after_calls"]["available"], "MCP resource sample missing")
        for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            first = next(iter(w["mcp_sessions"].values()))
            require(session[field] == first[field], "MCP session initialization identity differs: " + identity)
    if "mcp-char4000" in expected_sessions:
        require(all(w[field] == w["mcp_sessions"]["mcp-char4000"][field] for field in legacy.MCP_SESSION_FIELDS),
                "Legacy MCP fields must describe only the character session")
    for field in resource_fields(run["measurement"]):
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
    require(w["source_snapshot_before"] == w["source_snapshot_after"] and w["source_semantics_before"] == w["source_semantics_after"], "Original archive changed during retrieval")
    require(set(w["source_semantics_before"]) == set(SOURCE_TABLES), "Source semantic projection axis differs")
    for table, record in w["source_semantics_before"].items():
        require(record["excluded_host_columns"] == HOST_TIMESTAMP_COLUMNS.get(table, []), "Unexpected source projection omission")
    verify_native_memo(w, w["configurations"])
    return sum(len(c["rows"]) for c in w["configurations"])



def worker(args, plan, binding):
    state = args.state_dir.resolve()
    run = json.loads((state / "run.json").read_bytes())
    claim = json.loads(execution_claim_path(args.binding).read_bytes())
    require(claim["binding_sha256"] == sha(args.binding.read_bytes())
            and claim["run_identity_sha256"] == digest(run)
            and claim["state_dir"] == str(state), "Worker has no exact execution claim")
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
        "dataset_sha256": data.fingerprint, "configurations": [], "error": None,
        "native_token_count_memo": memo_diagnostics(), "mcp_sessions": {}}
    ledger = Ledger(ledger_path)
    try:
        with tempfile.TemporaryDirectory(prefix="round6-perf-") as temporary:
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
                report["source_snapshot_before"] = source_snapshot(book.db)
                report["source_semantics_before"] = source_semantics(book.db)
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                sources = original_turn_texts(data)
                begin = time.perf_counter_ns()
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    counter.count("Initialize reference tokenizer before query timing.")
                report["reference_tokenizer_initialization_ms"] = (time.perf_counter_ns() - begin) / 1e6
                cases = {case.id: case for case in data.queries}
                for index, config in enumerate(run["measurement"]["configs"]):
                    order = query_order(ids, item["round"], index)
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows = asyncio.run(mcp_configuration(data, config, order, db_path, work, src,
                            counters, sources, pages, report, ledger))
                    else:
                        rows = []
                        memo = {"id": config["id"], "before": native_memo_snapshot(book, item["label"]),
                                "first_query_id": None, "after_first_call": None, "after": None}
                        report["native_token_count_memo"]["configurations"].append(memo)
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
                            if len(rows) == 1:
                                memo["first_query_id"] = identity
                                memo["after_first_call"] = native_memo_snapshot(book, item["label"])
                        memo["after"] = native_memo_snapshot(book, item["label"])
                    report["configurations"].append({**config, "rows": rows,
                        "latency": latency_summary([r["wall_ms"] for r in rows])})
                    atomic(output, report, compressed=True)
                report["native_memory_after_calls"] = rss()
                report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                report["indexed_content_after_calls"] = indexed_content(book.db)
                report["source_snapshot_after"] = source_snapshot(book.db)
                report["source_semantics_after"] = source_semantics(book.db)
                require(report["source_snapshot_after"] == report["source_snapshot_before"] and report["source_semantics_after"] == report["source_semantics_before"], "Original archive changed during retrieval")
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["storage_after_checkpoint"] = storage(book.db, db_path)
                verify_native_memo(report, report["configurations"])
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


def validation(report):
    issues, canonical, total = [], {}, 0
    run, plan, workers = report["run"], report["plan"], report["workers"]
    if [w["key"] for w in workers] != [w["key"] for w in schedule(run["measurement"])]:
        issues.append("missing_duplicate_or_reordered_workers")
    for worker in workers:
        try:
            total += verify_worker(worker, run, plan)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(worker.get("key", "unknown") + ":" + str(error))
            continue
        for field in ("indexed_content", "source_semantics_before", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256"):
            key = (worker["cohort"], field)
            if key in canonical and canonical[key] != worker[field]:
                issues.append(worker["key"] + ":" + field)
            canonical.setdefault(key, worker[field])
        for config_id, session in worker["mcp_sessions"].items():
            for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
                key = (worker["cohort"], "mcp", field)
                if key in canonical and canonical[key] != session[field]:
                    issues.append(worker["key"] + ":" + config_id + ":" + field)
                canonical.setdefault(key, session[field])
        for config in worker["configurations"]:
            for row in config["rows"]:
                key = (worker["cohort"], config["id"], row["query_id"])
                value = stable_row(row)
                if key in canonical and canonical[key] != value:
                    issues.append(worker["key"] + ":payload:" + config["id"] + ":" + row["query_id"])
                canonical.setdefault(key, value)
    if total != run["measurement"]["calls"]:
        issues.append("registered_call_count")
    if report["error"] or not report["evaluator_unchanged"]:
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(schedule(run["measurement"])), "timed_calls": total,
            "expected_calls": run["measurement"]["calls"]}


def comparisons(report):
    adapted = {**report, "plan": {"performance_candidate": {"formal": report["run"]["measurement"]}}}
    return legacy.comparisons(adapted)


def acceptance(report, compared):
    if not report["validation"]["passed"]:
        return {"accepted": False, "numeric_gate_passed": False, "reason": "incomplete_or_invalid", "resource_review": []}
    ratios = [c["candidate"]["latency"]["p95_ms"] / c["baseline"]["latency"]["p95_ms"] for c in compared]
    improvement = 100 * (1 - math.exp(statistics.fmean(math.log(r) for r in ratios)))
    changes = [{"cohort": c["cohort"], "config": c["id"], "metric": key, "change_percent": c["candidate_change_percent"][key]}
        for c in compared for key in ("p50_ms", "p95_ms") if c["candidate_change_percent"][key] > 5 + 1e-9]
    resources, review = [], []
    for cohort in report["run"]["measurement"]["cohorts"]:
        for field in resource_fields(report["run"]["measurement"]):
            values = {label: [nested(w, field) for w in report["workers"] if w["cohort"] == cohort and w["label"] == label]
                      for label in ("baseline", "candidate")}
            old, new = (statistics.fmean(values[label]) for label in ("baseline", "candidate"))
            change = 100 * (new / old - 1) if old else (0.0 if new == 0 else None)
            row = {"cohort": cohort, "metric": field, "baseline": numeric(values["baseline"]),
                   "candidate": numeric(values["candidate"]), "mean_change_percent": change}
            resources.append(row)
            if change is None or change > 10 + 1e-9:
                review.append(row)
    native = [-c["candidate_change_percent"]["p95_ms"] for c in compared
              if c["cohort"] == "public1015" and c["surface"] == "native" and c["budget_tokens"] is not None]
    mcp = [-c["candidate_change_percent"]["p95_ms"] for c in compared if c["cohort"] == "public1015" and c["id"] == "mcp-token1024"]
    formal = report["run"]["stage"] == "formal"
    if formal:
        require(len(compared) == 12 and len(native) == 3 and len(mcp) == 1, "Incomplete formal acceptance axes")
    passed = formal and improvement >= 10 - 1e-9 and max(native) >= 15 - 1e-9 and mcp[0] >= 10 - 1e-9 and not changes
    return {"accepted": passed and not review, "numeric_gate_passed": passed if formal else None,
        "formal_acceptance_evaluated": formal, "geometric_mean_p95_improvement_percent": improvement,
        "best_public_native_token_p95_improvement_percent": max(native) if native else None,
        "public_mcp_token1024_p95_improvement_percent": mcp[0] if mcp else None,
        "thresholds_percent": THRESHOLDS, "regressions_above_five_percent": changes,
        "resource_comparisons": resources, "resource_review": review,
        "resource_rule": "Any increase above 10% requires explicit cause assessment and independent review; no automatic override.",
        "scope": "Formal preregistered gates" if formal else "Diagnostic observations only; no release acceptance or speed gate."}


def execution_claim_path(binding):
    return binding.with_name(binding.name + ".execution.json")


def publication_identity(args, binding):
    stage = binding["stage"]
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    trigger = "ci/v034-round6-" + ("performance" if stage == "formal" else "development")
    require(run_id.isdigit() and attempt == "1" and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") == "refs/heads/" + trigger,
            "Only the registered first-attempt hosted push may measure")
    require(git("remote", "get-url", "origin").decode().strip() in (
        "https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git",
        "git@github.com:Afloat16/AI-Memory-Book.git"), "Unauthorized checkpoint origin")
    suffix = ("performance" if stage == "formal" else stage) + "-" + run_id + "-1"
    branch = "validation/v034-round6-" + suffix
    require(args.publish_branch == branch and args.output.resolve().parent == ROOT / ("benchmarks/reports/round6-" + suffix)
            and args.state_dir.resolve() == ROOT / (".artifacts/round6-" + suffix), "Unexpected publication paths")
    # Keyed by actual Python source pair, not an editable binding filename or evaluator revision.
    key = digest({"stage": stage, "sources": {k: v["runtime_sha256"] for k, v in binding["sources"].items()}})
    return {"run_id": run_id, "run_attempt": attempt, "branch": branch,
            "claim_branch": "validation/v034-round6-claim-" + key, "source_pair_stage_sha256": key}


def claim_execution(args, run):
    claim = {"schema_version": 1, "evaluator": VERSION, "created_at": now(),
        "binding_sha256": sha(args.binding.read_bytes()), "run_identity_sha256": digest(run),
        "host": run["host"], "state_dir": str(args.state_dir.resolve()), "output": str(args.output.resolve())}
    exclusive(execution_claim_path(args.binding), claim)
    return claim


class CheckpointPublicationError(RuntimeError):
    """Stop all further measurement after rejected or ambiguous publication."""


def export_checkpoint(args):
    state, public = args.state_dir.resolve(), args.output.resolve().parent
    public.mkdir(parents=True, exist_ok=True)
    def preserve(destination, raw):
        if destination.exists():
            require(destination.is_file() and not destination.is_symlink() and destination.read_bytes() == raw,
                    "Never replace immutable raw evidence: " + str(destination))
        else:
            exclusive_bytes(destination, raw)
    for name in ("run.json", "resource-preflight.json"):
        if (state / name).is_file():
            preserve(public / name, (state / name).read_bytes())
    if (state / "checkpoint.json").is_file():
        atomic(public / "checkpoint.json", read_json(state / "checkpoint.json"))
    if execution_claim_path(args.binding).is_file():
        preserve(public / "execution.json", execution_claim_path(args.binding).read_bytes())
    for source in sorted((state / "workers").glob("*")):
        require(not source.is_symlink(), "Refuse symbolic raw evidence")
        if source.is_file() and source.name.endswith((".started.json", ".json.gz", ".attempts.jsonl.gz")):
            preserve(public / "workers" / source.name, source.read_bytes())
        elif source.is_file() and source.name.endswith(".attempts.jsonl") and not source.with_suffix(".jsonl.gz").exists():
            preserve(public / "workers" / source.with_suffix(".jsonl.gz").name, gzip.compress(source.read_bytes(), mtime=0))


def publish_checkpoint(args, run, phase):
    publication = run["publication"]
    failure = args.output.resolve().parent / "publication-failure.json"
    require(not failure.exists(), "A prior push failed; no automatic retry")
    try:
        export_checkpoint(args)
        branch_ref, claim_ref = ("refs/heads/" + publication[k] for k in ("branch", "claim_branch"))
        parent_path = args.state_dir / "publication-parent.json"
        parent = read_json(parent_path)["commit"] if parent_path.exists() else git("rev-parse", "HEAD").decode().strip()
        remote = git("ls-remote", "--heads", "origin", branch_ref).decode().split()
        require(not remote or remote == [parent, branch_ref], "Another writer advanced the result ref")
        if phase == "execution claimed":
            require(not git("ls-remote", "--heads", "origin", claim_ref).strip(), "This actual source pair/stage has already been claimed")
        public = args.output.resolve().parent.relative_to(ROOT).as_posix()
        names = [public, execution_claim_path(args.binding).resolve().relative_to(ROOT).as_posix()]
        with tempfile.TemporaryDirectory(prefix="round6-checkpoint-") as temporary:
            environment = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
            def indexed(*arguments):
                result = subprocess.run(["git", *arguments], cwd=ROOT, env=environment,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                require(result.returncode == 0, "Checkpoint Git operation failed; credential-bearing diagnostics omitted")
                return result.stdout.decode().strip()
            indexed("read-tree", parent)
            indexed("add", "--sparse", "--", *names)
            tree = indexed("write-tree")
            message = Path(temporary) / "message"
            message.write_text("bench: preserve round6 " + run["stage"] + " " + phase + "\n")
            commit = indexed("-c", "user.name=github-actions[bot]", "-c",
                "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit-tree", tree, "-p", parent, "-F", str(message))
        if phase == "execution claimed":
            git("push", "--force-with-lease=" + claim_ref + ":", "origin", commit + ":" + claim_ref)
        git("push", "origin", commit + ":" + branch_ref)
        atomic(parent_path, {"commit": commit, "phase": phase, "at": now()})
    except BaseException as error:
        if not failure.exists():
            exclusive(failure, {"phase": phase, "status": "publication-failed-no-automatic-retry", "error_type": type(error).__name__, "at": now()})
        raise CheckpointPublicationError("Checkpoint publication failed; no further timing") from error


def load_completed(state, item, run, plan):
    prefix = state / "workers" / item["key"]
    require(read_json(Path(str(prefix) + ".started.json")) == {"worker": item, "run_identity_sha256": digest(run)}, "Worker intent changed")
    value = read_json(Path(str(prefix) + ".json.gz"))
    ledger = gzip.decompress(Path(str(prefix) + ".attempts.jsonl.gz").read_bytes())
    raw = Path(str(prefix) + ".attempts.jsonl")
    require(not raw.exists() or raw.read_bytes() == ledger, "Compressed/raw ledger mismatch")
    verify_worker(value, run, plan, ledger=ledger)
    return value


def save_report(args, report):
    report["evaluator_unchanged"] = (file_hashes() == report["run"]["evaluator_files"]
        and sha(PLAN.read_bytes()) == report["run"]["plan_sha256"])
    report["validation"] = validation(report)
    report["comparisons"] = comparisons(report) if report["validation"]["passed"] else []
    report["acceptance"] = acceptance(report, report["comparisons"])
    raw = atomic(args.output, report, compressed=True)
    atomic(args.output.with_name("report.summary.json"), legacy.summary(report, args.output.read_bytes(), raw))
    atomic(args.state_dir / "checkpoint.json", {"run_identity_sha256": digest(report["run"]), "status": report["status"],
        "completed_workers": [w["key"] for w in report["workers"]], "report_sha256": sha(args.output.read_bytes()), "at": now()})


def resource_preflight(state):
    child = subprocess.Popen([sys.executable, "-c", 'import sys; print("ready", flush=True); sys.stdin.buffer.read(1)',
        "memory_book-procfs-preflight"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        require(child.stdout.readline() == b"ready\n", "Harmless resource preflight child failed")
        observation = legacy.server_rss()
    finally:
        child.communicate(b"x", timeout=10)
    record = {"observation": observation, "product_calls": 0, "sdk_sessions": 0}
    exclusive(state / "resource-preflight.json", record)
    require(observation["available"] and observation["rss_bytes"] > 0 and observation["hwm_bytes"] > 0,
            "Procfs must expose the actual child before any product measurement")
    return record


def controller(args, plan, binding):
    require(args.publish_branch and args.baseline_src and args.candidate_src and args.locomo_path
            and args.output and args.state_dir, "Hosted checkpoint publication and all explicit input paths are required")
    require(args.output.name == "report.json.gz", "Use the new report namespace")
    state = args.state_dir.resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    with _lock(state.with_name(state.name + ".controller")):
        require(not state.exists() and not args.output.exists(), "Preserve previous execution; no timing replay")
        host = host_identity()
        require(host["packages"] == PACKAGES, "Install the bound SDK/tokenizer versions")
        paths = {label: str(path.resolve()) for label, path in (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
        for label, path in paths.items():
            require(source_identity(Path(path)) == binding["sources"][label], "Frozen source differs")
        spec, cohorts = binding["measurement"], {}
        for name in spec["cohorts"]:
            data = dataset(plan, name, args.locomo_path)
            ids = [case.id for case in data.queries]
            require(len(ids) == len(set(ids)), "Duplicate input query IDs")
            cohorts[name] = {"sha256": data.fingerprint, "queries": len(ids), "query_ids": sorted(ids), "query_ids_original_order": ids}
        run = {"evaluator": VERSION, "stage": binding["stage"], "measurement": spec, "plan_sha256": sha(PLAN.read_bytes()),
            "binding": binding, "binding_sha256": sha(args.binding.read_bytes()), "binding_path": checked_relative(args.binding),
            "evaluator_files": file_hashes(), "source_paths": paths, "host": host, "cohorts": cohorts,
            "schedule": schedule(spec), "locomo_file_sha256": sha(args.locomo_path.read_bytes()),
            "output": str(args.output.resolve()), "publication": publication_identity(args, binding)}
        claim_execution(args, run)
        exclusive(state / "run.json", run)
        report = {"schema_version": 1, "evaluator": VERSION, "plan": plan, "run": run, "started_at": now(),
            "workers": [], "error": None, "evaluator_unchanged": False, "status": "running",
            "interpretation": {"quality": "Historical regression inputs; exact complete output equality, not new-domain or answer quality.",
                "native": "Complete call, query-result cache disabled. Both bounded derived memos start empty and warm naturally.",
                "mcp": "Actual official SDK stdio roundtrip and unchanged native cache writes; each setting has a new process.",
                "timing": "Fixed balanced source order, one host, no concurrent benchmark; retain first calls and every adverse sample.",
                "source": "Complete snapshots compared within each archive; six-table cross-archive projections omit only explicitly named host timestamps.",
                "resources": "Fresh import/open/ingest/replay, process RSS/HWM and logical/main/WAL/SHM bytes separately recorded."}}
        try:
            save_report(args, report)
            publish_checkpoint(args, run, "execution claimed")
            resource_preflight(state)
            publish_checkpoint(args, run, "zero-call resource preflight")
            for item in run["schedule"]:
                exclusive(state / "workers" / (item["key"] + ".started.json"), {"worker": item, "run_identity_sha256": digest(run)})
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " started")
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                    "--binding", str(args.binding.resolve()), "--state-dir", str(state), "--locomo-path", str(args.locomo_path.resolve())],
                    check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
                report["workers"].append(load_completed(state, item, run, plan))
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " completed")
                print(json.dumps({"worker_completed": item["key"], "completed_workers": len(report["workers"]), "stage": run["stage"]}), flush=True)
            report["status"] = "measurements_completed"
        except BaseException as error:
            report["status"] = "failed_or_interrupted"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            report["finished_at"] = now()
            save_report(args, report)
            if not (args.output.parent / "publication-failure.json").exists():
                try:
                    publish_checkpoint(args, run, "controller finished")
                except CheckpointPublicationError as error:
                    report.update(status="failed_or_interrupted", error={"type": type(error).__name__, "message": str(error)})
                    save_report(args, report)
            export_checkpoint(args)
        print(json.dumps({"stage": run["stage"], "validation": report["validation"], "acceptance": {k: v for k, v in report["acceptance"].items()
            if k not in ("resource_comparisons", "resource_review")}, "resource_review_count": len(report["acceptance"]["resource_review"])}), flush=True)
        return 2 if not report["validation"]["passed"] else (3 if binding["stage"] == "formal" and not report["acceptance"]["accepted"] else 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    for name in ("baseline-src", "candidate-src", "locomo-path", "output", "state-dir", "native-development",
                 "native-development-audit", "mcp-development", "mcp-development-audit", "compatibility"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--publish-branch")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.bind:
        bind(args)
        return 0
    require(args.binding is not None, "A committed source/evaluator binding is required")
    plan, binding = load_plan(), load_binding(args.binding)
    return worker(args, plan, binding) if args.worker else controller(args, plan, binding)


if __name__ == "__main__":
    raise SystemExit(main())
