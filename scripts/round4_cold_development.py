"""Historical Hotpot128 first-use native / cold-body-feature diagnostic.

This is not OS-cold timing, a quality selection, or a formal acceptance run.
Four sequential fresh workers execute baseline/candidate, then candidate/baseline.
When present, only the candidate's body-feature cache is cleared outside each timer;
directory-token, tokenizer-file and OS/SQLite caches are left intact. Every wall
sample, complete non-latency payload hash and failed attempt remains on disk.
Without that feature cache, this is a first-use native diagnostic on fresh
workers, not per-query cold startup: four configurations reuse each connection.
Existing attempts cannot be resumed or replaced. Importing this module does not
read the Parquet input or execute retrieval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.round4_development_pair import digest
from scripts.benchmark_default_recall import indexed_content, rss, storage
from benchmarks.hotpot_data import convert_hotpot
from benchmarks.prepare_native_data import normalize_hotpot
from benchmarks.run import engine_source_hash
from benchmarks.semantic_eval import source_snapshot
from benchmarks.token_compare import TokenCounter, checkout_provenance, latency_summary

BASELINE = "7b7a5d7336b9350a128f5e0a888811b1b3015e68"
BASELINE_SHA = "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"
DATASET_SHA = "0791515aca6bccf19a97895cad681e06a07536d6c08050d54189cc64cb819822"
PARQUET_SHA = "c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6"
PARQUET_BYTES = 27_452_575
MANIFEST = ROOT / "benchmarks/hotpot_manifest.json"
COUNT = 128
SEED = 91261
EXPECTED_CALLS = 2048
FEATURE_ENTRIES = 256
FEATURE_BYTES = 2_097_152
VERSION = "round4-historical128-first-use-native-development-1"
CONFIGS = (("native-char4000", {"budget_chars": 4000}),
           ("native-token512", {"budget_chars": 8000, "budget_tokens": 512}),
           ("native-token1024", {"budget_chars": 8000, "budget_tokens": 1024}),
           ("native-token2048", {"budget_chars": 8000, "budget_tokens": 2048}))
COLUMNS = ("id", "question", "answer", "type", "level", "context", "supporting_facts")
HELPERS = ("scripts/round4_development_pair.py", "scripts/benchmark_default_recall.py",
    "benchmarks/hotpot_data.py", "benchmarks/prepare_native_data.py", "benchmarks/data.py",
    "benchmarks/run.py", "benchmarks/semantic_eval.py", "benchmarks/token_compare.py",
    "benchmarks/hotpot_manifest.json", "benchmarks/experiments/round4-development-addendum.json",
    "benchmarks/experiments/round4-counting-addendum.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode()


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw_json(value))
        stream.flush()
        os.fsync(stream.fileno())


def progress(path, value):
    """Advance only an already-created artifact owned by this attempt."""
    require(path.is_file(), "Create an exclusive attempt before checkpointing it")
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("wb") as stream:
        stream.write(raw_json(value))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def evaluator_files():
    return {name: sha((ROOT / name).read_bytes()) for name in
            ("scripts/round4_cold_development.py", *HELPERS)}


def old_manifest():
    raw = MANIFEST.read_bytes()
    committed = subprocess.check_output(["git", "show", BASELINE + ":benchmarks/hotpot_manifest.json"],
                                        cwd=ROOT, timeout=30, stderr=subprocess.DEVNULL)
    require(raw == committed, "Historical Hotpot128 manifest changed")
    value = json.loads(raw)
    ids = value["selected_ids"]
    require(value["expected_queries"] == COUNT and len(ids) == len(set(ids)) == COUNT
            and all(isinstance(identity, str) and identity for identity in ids), "Wrong historical ID set")
    require(value["upstream_bytes"] == PARQUET_BYTES and value["upstream_sha256"] == PARQUET_SHA
            and value["upstream_rows"] == 7405, "Wrong historical Parquet identity")
    return value


def load_historical(parquet, manifest):
    """Read IDs first; materialize only the manifest's already evaluated rows."""
    raw = Path(parquet).read_bytes()
    require(len(raw) == PARQUET_BYTES and sha(raw) == PARQUET_SHA, "Historical Parquet bytes changed")
    import pyarrow as pa
    import pyarrow.parquet as pq
    ids = pq.read_table(pa.BufferReader(raw), columns=["id"]).column("id").to_pylist()
    selected = manifest["selected_ids"]
    require(len(ids) == len(set(ids)) == manifest["upstream_rows"] and
            all(isinstance(identity, str) and identity for identity in ids)
            and not set(selected) - set(ids), "Historical source ID axis changed")
    rows = pq.read_table(pa.BufferReader(raw), columns=list(COLUMNS),
                         filters=[("id", "in", selected)]).to_pylist()
    actual = [row["id"] for row in rows]
    require(len(actual) == len(set(actual)) == COUNT and set(actual) == set(selected),
            "Filtered rows are not exactly the historical 128")
    mapping = {row["id"]: row for row in rows}
    normalized = normalize_hotpot([mapping[identity] for identity in selected])
    data = convert_hotpot(json.loads(normalized), selected, {key: manifest[key] for key in
        ("dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})
    require(len(data.queries) == COUNT and [case.id for case in data.queries] == selected
            and data.fingerprint == DATASET_SHA, "Historical dataset fingerprint changed")
    identity = {"cohort": "hotpot128", "queries": COUNT, "dataset_sha256": data.fingerprint,
        "manifest_sha256": sha(MANIFEST.read_bytes()), "selected_ids_sha256": digest(selected),
        "parquet_sha256": PARQUET_SHA, "parquet_bytes": PARQUET_BYTES,
        "selected_canonical_sha256": sha(normalized), "source_turns": data.turn_count,
        "representation": "Unchanged historical original-sentences-v2 and old provenance",
        "selection": "All historical manifest IDs; no new selection, label filtering or source-text export"}
    return data, identity


def source_record(source):
    package = Path(source).resolve() / "memory_book"
    require(package.is_dir(), "Runtime source directory is missing")
    return {"source_sha256": engine_source_hash(package), "provenance": checkout_provenance(package)}


def order(ids, repetition, config_number):
    values = list(ids)
    random.Random(SEED + 1009 * repetition + config_number).shuffle(values)
    return values


def schedule():
    return [{"key": f"r{repetition}-{label}", "round": repetition, "label": label}
            for repetition, labels in enumerate((("baseline", "candidate"), ("candidate", "baseline")))
            for label in labels]


def feature_state(book):
    if not hasattr(book, "_body_token_cache"):
        return {"available": False, "entries": 0, "accounted_entry_bytes": 0,
                "container_bytes": 0, "accounted_total_bytes": 0, "revision": None}
    cache = book._body_token_cache
    accounted = book._body_token_cache_bytes
    require(type(accounted) is int and accounted >= 0
            and accounted == sum(value[1] for value in cache.values()), "Body-feature byte accounting differs")
    total = accounted + sys.getsizeof(cache)
    require(len(cache) <= FEATURE_ENTRIES and total <= FEATURE_BYTES, "Body-feature retained bounds exceeded")
    return {"available": True, "entries": len(cache), "accounted_entry_bytes": accounted,
            "container_bytes": sys.getsizeof(cache), "accounted_total_bytes": total,
            "revision": book._body_token_cache_revision}


def directory_state(book):
    return dict(book._directory_tokens.cache_info()._asdict())


def feature_mode(book, runtime_store, label):
    initial = feature_state(book)
    require(initial["entries"] == 0 and initial["accounted_entry_bytes"] == 0,
            "Worker features were not initially empty")
    clear = getattr(book, "_clear_body_token_cache", None)
    if initial["available"]:
        require(label == "candidate" and callable(clear)
                and runtime_store.BODY_TOKEN_CACHE_ENTRIES == FEATURE_ENTRIES
                and runtime_store.BODY_TOKEN_CACHE_BYTES == FEATURE_BYTES,
                "Candidate feature-cache contract differs")
        return "artificial-cold-body-feature", initial
    require(clear is None, "Body-feature reset hook exists without its cache")
    return "first-use-historical-native", initial


class Ledger:
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf-8")
        self.started = self.finished = 0

    def write(self, value):
        self.stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def start(self, configuration, identity):
        seq = self.started
        self.started += 1
        self.write({"event": "started", "seq": seq, "configuration": configuration,
                    "query_id": identity, "at": now()})
        return seq

    def finish(self, seq, row):
        self.write({"event": "finished", "seq": seq, "row": row, "at": now()})
        self.finished += 1

    def close(self):
        self.stream.close()


def worker(args):
    run = json.loads(args.run.read_bytes())
    item = next(item for item in run["schedule"] if item["key"] == args.worker)
    state = Path(run["state"]) / item["key"]
    prefix = Path(run["worker_directory"]) / item["key"]
    output, ledger_path = prefix.with_suffix(".json"), prefix.with_suffix(".attempts.jsonl")
    require(json.loads(prefix.with_suffix(".started.json").read_bytes()) ==
            {"worker": item, "run_sha256": digest(run)}, "Worker has no matching start intent")
    require(not state.exists() and not output.exists() and not ledger_path.exists(), "Never repeat a development worker")
    state.mkdir()
    ledger = Ledger(ledger_path)
    label = item["label"]
    source = Path(run["sources"][label]["path"])
    expected_sha = run["sources"][label]["sha256"]
    result = {"schema_version": 1, "protocol": VERSION, **item, "run_sha256": digest(run),
        "status": "running", "started_at": now(), "cells": [], "expected_calls": COUNT * len(CONFIGS),
        "attempted_calls": 0, "finished_calls": 0, "feature_resets": 0,
        "cache_peak_boundary": "Maxima of retained cache state observed after calls; no instrumented in-call high-water claim",
        "observed_after_call_cache_peak": {"entries": 0, "accounted_total_bytes": 0}, "error": None}
    create(output, result)
    try:
        require(evaluator_files() == run["evaluator_files"], "Diagnostic evaluator changed before worker")
        result["source_before"] = source_record(source)
        require(result["source_before"]["source_sha256"] == expected_sha, "Runtime hash differs from requested source")
        if label == "baseline":
            require(result["source_before"]["provenance"]["git_commit"] == BASELINE
                    and result["source_before"]["provenance"]["commit_identifies_source"], "Baseline is not exact v0.3.1")
        sys.path.insert(0, str(source))
        begin = time.perf_counter_ns()
        import memory_book
        from memory_book import store as runtime_store
        require(Path(memory_book.__file__).resolve().parent == source / "memory_book", "Imported a different runtime")
        result["runtime_import_ms"] = (time.perf_counter_ns() - begin) / 1e6
        require(importlib.metadata.version("tiktoken") == "0.12.0", "Reference tokenizer version changed")
        counter = TokenCounter("cl100k_base")
        counter.count("Initialize the existing tokenizer cache outside all query timers.")
        manifest = old_manifest()
        require(sha(MANIFEST.read_bytes()) == run["manifest_sha256"], "Historical manifest changed during diagnostic")
        data, result["dataset"] = load_historical(Path(run["parquet"]), manifest)
        result["rss_after_input_load"] = rss()
        cases = {case.id: case for case in data.queries}
        database = state / "book.db"
        begin = time.perf_counter_ns()
        with memory_book.MemoryBook(database, cache_size=0) as book:
            result["native_open_ms"] = (time.perf_counter_ns() - begin) / 1e6
            begin = time.perf_counter_ns()
            ingestion = [book.ingest(session) for session in data.sessions]
            result["fresh_ingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
            result["ingestion_results_sha256"] = digest(ingestion)
            result["source_snapshot_before"] = source_snapshot(book.db)
            result["indexed_content_before"] = indexed_content(book.db)
            result["storage_before_queries"] = storage(book.db, database)
            result["rss_before_queries"] = rss()
            result["directory_cache_before_queries"] = directory_state(book)
            result["diagnostic_mode"], initial = feature_mode(book, runtime_store, label)
            result["feature_cache_before_queries"] = initial
            result["cache_boundary"] = ("Body-feature cache reset outside every measured call."
                if initial["available"] else "Body-feature cache and reset hook absent; no feature reset performed.")
            result["cache_boundary"] += (" Fresh process/database/connection per worker; four configurations reuse that connection."
                " Directory-token and tokenizer-file caches remain intact; no per-query cold startup or OS-cold claim.")
            for number, (configuration, options) in enumerate(CONFIGS):
                cell = {"configuration": configuration, "options": options,
                        "status": "running", "rows": []}
                result["cells"].append(cell)
                progress(output, result)
                for identity in order(manifest["selected_ids"], item["round"], number):
                    case = cases[identity]
                    result["current_attempt"] = {"configuration": configuration, "query_id": identity,
                                                 "phase": "outside-timer preparation"}
                    directory_before = directory_state(book)
                    if initial["available"]:
                        book._clear_body_token_cache()
                        result["feature_resets"] += 1
                    require(directory_state(book) == directory_before, "Feature reset changed the directory-token cache")
                    cold = feature_state(book)
                    require(cold["entries"] == 0 and cold["accounted_entry_bytes"] == 0, "Measured call is not feature-cold")
                    before = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                    require(before == 0, "Persistent result cache was not empty")
                    seq = ledger.start(configuration, identity)
                    result["attempted_calls"] = ledger.started
                    row = {"query_id": identity, "configuration": configuration,
                           "status": "running", "feature_cache_before": cold}
                    result["current_attempt"]["phase"] = "measured recall"
                    begin = time.perf_counter_ns()
                    try:
                        response = book.recall(case.query, project=case.project, limit=5, use_cache=False,
                            semantic=False, coverage=False, tokenizer="cl100k_base", **options)
                        row["wall_ms"] = (time.perf_counter_ns() - begin) / 1e6
                        result["current_attempt"]["phase"] = "outside-timer validation"
                        require("latency_ms" in response, "Native response lacks its timing field")
                        response.pop("latency_ms")  # The sole excluded response field.
                        row["payload_sha256"] = digest(response)
                        row["feature_cache_after"] = feature_state(book)
                        row["directory_cache_after"] = directory_state(book)
                        row["cache_rows_before"] = before
                        row["cache_rows_after"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                        context = response["context"]
                        tokens = counter.count(context)
                        row["context_tokens_cl100k"] = tokens
                        row["invariants"] = {
                            "result_cache": row["cache_rows_after"] == 0 and response["cache_hit"] is False,
                            "characters": response["context_chars"] == len(context) <= options["budget_chars"],
                            "token_budget": "budget_tokens" not in options or
                                (tokens <= options["budget_tokens"] and response["context_tokens"] == tokens
                                 and response["budget_tokens"] == options["budget_tokens"]
                                 and response["tokenizer"] == "cl100k_base"
                                 and response["tokenizer_version"] == "0.12.0"),
                            "default_policy": not response.get("semantic", False)
                                and not response.get("project_local_fts_statistics", False),
                            "result_limit": len(response["results"]) <= 5,
                            "directory_cache_preserved_by_reset": True}
                        for key in result["observed_after_call_cache_peak"]:
                            result["observed_after_call_cache_peak"][key] = max(
                                result["observed_after_call_cache_peak"][key], row["feature_cache_after"][key])
                        require(all(row["invariants"].values()), "Native response invariant failed")
                        row["status"] = "completed"
                    except BaseException as error:
                        row.setdefault("wall_ms", (time.perf_counter_ns() - begin) / 1e6)
                        row.update(status="failed", error_type=type(error).__name__)
                        raise
                    finally:
                        cell["rows"].append(row)
                        ledger.finish(seq, row)
                        result["finished_calls"] = ledger.finished
                cell.update(status="completed", latency=latency_summary([row["wall_ms"] for row in cell["rows"]]))
                progress(output, result)
            result["rss_after_queries"] = rss()
            result["source_snapshot_after"] = source_snapshot(book.db)
            result["indexed_content_after"] = indexed_content(book.db)
            result["storage_after_queries"] = storage(book.db, database)
            result["directory_cache_after_queries"] = directory_state(book)
            result["feature_cache_after_queries"] = feature_state(book)
            require(result["source_snapshot_before"] == result["source_snapshot_after"]
                    and result["indexed_content_before"] == result["indexed_content_after"], "Source or index changed during recall")
        result["feature_cache_after_close"] = feature_state(book)
        result["directory_cache_after_close"] = directory_state(book)
        result["rss_after_close"] = rss()
        result["source_after"] = source_record(source)
        require(result["source_after"]["source_sha256"] == expected_sha, "Runtime source changed during worker")
        require(evaluator_files() == run["evaluator_files"], "Diagnostic evaluator changed during worker")
        require(ledger.started == ledger.finished == result["expected_calls"], "Worker matrix incomplete")
        require(result["feature_resets"] == (result["expected_calls"] if initial["available"] else 0),
                "Feature reset count differs")
        result["status"] = "completed"
        result.pop("current_attempt", None)
    except BaseException as error:
        result.update(status="failed", error={"type": type(error).__name__})
    finally:
        ledger.close()
        result.update(finished_at=now(), ledger_sha256=sha(ledger_path.read_bytes()))
        database = state / "book.db"
        if "source_snapshot_after" not in result and database.is_file():
            try:
                connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
                try:
                    result["source_snapshot_after"] = source_snapshot(connection)
                    result["indexed_content_after"] = indexed_content(connection)
                    result["storage_after_queries"] = storage(connection, database)
                    result["database_finish_boundary"] = "Read-only snapshot after failed worker closure"
                finally:
                    connection.close()
            except BaseException as error:
                result["database_finish_error_type"] = type(error).__name__
        if "source_after" not in result:
            try:
                result["source_after"] = source_record(source)
            except BaseException as error:
                result["source_after_error_type"] = type(error).__name__
        try:
            result["rss_at_finish"] = rss()
        except OSError as error:
            result["rss_finish_error_type"] = type(error).__name__
        progress(output, result)
    print(json.dumps({"worker": item["key"], "status": result["status"],
                      "attempted_calls": result["attempted_calls"], "finished_calls": result["finished_calls"]}), flush=True)
    return 0 if result["status"] == "completed" else 2


def assess(workers, manifest):
    require([worker["key"] for worker in workers] == [item["key"] for item in schedule()], "Incomplete worker order")
    canonical, differences, cells, count = {}, [], [], 0
    indexed = workers[0]["indexed_content_before"]
    for worker in workers:
        require(worker["status"] == "completed" and worker["attempted_calls"] == worker["finished_calls"] == 512,
                "Incomplete worker retained; no complete diagnostic claim")
        require(worker["dataset"]["dataset_sha256"] == DATASET_SHA and worker["indexed_content_before"] == indexed
                and worker["indexed_content_after"] == indexed
                and worker["source_snapshot_before"] == worker["source_snapshot_after"], "Dataset/source/index identity differs")
        require([cell["configuration"] for cell in worker["cells"]] == [name for name, _ in CONFIGS], "Configuration axis differs")
        for number, cell in enumerate(worker["cells"]):
            require(cell["status"] == "completed" and [row["query_id"] for row in cell["rows"]] ==
                    order(manifest["selected_ids"], worker["round"], number), "Query order or completeness changed")
            for row in cell["rows"]:
                count += 1
                require(row["status"] == "completed" and all(row["invariants"].values()), "Failed call is retained")
                key = cell["configuration"], row["query_id"]
                if key in canonical and canonical[key] != row["payload_sha256"]:
                    differences.append({"round": worker["round"], "label": worker["label"],
                        "configuration": key[0], "query_id": key[1],
                        "first_payload_sha256": canonical[key], "payload_sha256": row["payload_sha256"]})
                canonical.setdefault(key, row["payload_sha256"])
    require(count == EXPECTED_CALLS, "Diagnostic call count differs")
    modes = {worker["diagnostic_mode"] for worker in workers if worker["label"] == "candidate"}
    require(len(modes) == 1, "Candidate cache surface changed between rounds")
    for configuration, _ in CONFIGS:
        values = {}
        for label in ("baseline", "candidate"):
            selected = [worker for worker in workers if worker["label"] == label]
            by_round = [{"round": worker["round"], "latency": latency_summary([
                row["wall_ms"] for cell in worker["cells"] if cell["configuration"] == configuration for row in cell["rows"]])}
                for worker in selected]
            values[label] = {"latency": latency_summary([row["wall_ms"] for worker in selected
                for cell in worker["cells"] if cell["configuration"] == configuration for row in cell["rows"]]),
                "rounds": by_round}
        changes = {metric: 100 * (values["candidate"]["latency"][metric] /
                   values["baseline"]["latency"][metric] - 1) for metric in ("p50_ms", "p95_ms", "mean_ms")}
        cells.append({"configuration": configuration, **values, "candidate_change_percent": changes})
    return {"complete": True, "timed_calls": count, "payload_equivalence": not differences,
            "payload_differences": differences, "comparisons": cells,
            "diagnostic_mode": modes.pop(), "formal_acceptance": None,
            "boundary": "Historical first-use native development diagnostic; only an available body-feature cache is reset. Four configurations reuse each fresh worker connection. No formal speed gate, per-query cold startup or OS-cold claim."}


def launch(command, environment):
    """Stop an interrupted child before hashing its final preserved artifacts."""
    process = subprocess.Popen(command, env=environment, start_new_session=True)
    try:
        return process.wait()
    except BaseException:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
        raise


def controller(args):
    require(args.baseline_src and args.candidate_src and args.candidate_sha,
            "Provide exact baseline/candidate source paths and candidate SHA-256")
    require(args.baseline_sha == BASELINE_SHA and re.fullmatch(r"[0-9a-f]{64}", args.candidate_sha),
            "Wrong baseline or candidate source SHA-256")
    state, output = args.state.resolve(), args.output.resolve()
    require(state.is_relative_to((ROOT / ".artifacts").resolve()), "Private diagnostic state belongs under .artifacts")
    public_workers = output.with_name(output.stem + ".workers")
    require(not state.exists() and not output.exists() and not public_workers.exists(), "Preserve every existing diagnostic attempt")
    state.mkdir(parents=True)
    public_workers.mkdir(parents=True)
    cache = (args.tokenizer_cache or os.environ.get("TIKTOKEN_CACHE_DIR") or state / "tokenizer-cache")
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)  # Preserve all existing tokenizer files.
    manifest = old_manifest()
    sources = {label: {"path": str(getattr(args, label + "_src").resolve()),
                       "sha256": getattr(args, label + "_sha")} for label in ("baseline", "candidate")}
    run = {"schema_version": 1, "protocol": VERSION, "schedule": schedule(), "sources": sources,
        "state": str(state), "worker_directory": str(public_workers), "output": str(output),
        "parquet": str(args.parquet.resolve()), "tokenizer_cache": str(cache),
        "manifest_sha256": sha(MANIFEST.read_bytes()), "dataset_sha256": DATASET_SHA,
        "query_ids_sha256": digest(manifest["selected_ids"]), "evaluator_files": evaluator_files(),
        "configurations": [{"id": name, **options} for name, options in CONFIGS],
        "host": {"python": platform.python_version(), "platform": platform.platform(),
                 "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()},
        "settings": {"cache_size": 0, "use_cache": False, "limit": 5, "semantic": False,
            "coverage": False, "tokenizer": "cl100k_base", "seed": SEED,
            "candidate_feature_reset": "When available, _clear_body_token_cache outside every measured call; absence reported as first-use historical native diagnostic",
            "directory_token_cache": "Preserved across queries within the fresh worker connection",
            "tokenizer_file_cache": "Existing directory preserved; initialization outside query timing",
            "feature_limits_when_available": {"entries": FEATURE_ENTRIES, "accounted_bytes": FEATURE_BYTES}}}
    run_path = state / "run.json"
    create(run_path, run)
    report = {"schema_version": 1, "protocol": VERSION, "run": run, "started_at": now(),
        "status": "running", "expected_calls": EXPECTED_CALLS, "workers": [], "error": None,
        "scope": "Historical Hotpot128 only. First-use native diagnostic on fresh workers; only an available derived-body-feature cache is reset per call. Four configurations reuse each connection. OS/SQLite/directory/tokenizer caches remain intact. Fresh ingestion outside recall timers. All negative cells retained; no labels used for choices and no formal gate changes."}
    create(output, report)
    try:
        for item in run["schedule"]:
            prefix = public_workers / item["key"]
            create(prefix.with_suffix(".started.json"), {"worker": item, "run_sha256": digest(run)})
            progress(output, report)
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", item["key"], "--run", str(run_path)]
            exit_code = launch(command, {**os.environ, "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1", "ORT_DISABLE_TELEMETRY": "1", "TIKTOKEN_CACHE_DIR": str(cache)})
            worker_path = prefix.with_suffix(".json")
            if worker_path.exists():
                report["workers"].append(json.loads(worker_path.read_bytes()))
            else:
                report["workers"].append({**item, "status": "missing_worker_report", "exit_code": exit_code})
            progress(output, report)
            require(exit_code == 0 and report["workers"][-1]["status"] == "completed",
                    "A worker failed; preserve it and stop later workers")
        require(evaluator_files() == run["evaluator_files"], "Diagnostic evaluator changed")
        report["assessment"] = assess(report["workers"], manifest)
        require(report["assessment"]["payload_equivalence"], "Complete non-timing payloads differ")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__})
    finally:
        # A killed worker's original partial ledger/report remains beside its
        # start marker. Never start it again, fabricate a finish, or delete its DB.
        recorded = {worker["key"] for worker in report["workers"]}
        for item in run["schedule"]:
            prefix = public_workers / item["key"]
            if item["key"] not in recorded and prefix.with_suffix(".started.json").exists():
                worker_path = prefix.with_suffix(".json")
                report["workers"].append(json.loads(worker_path.read_bytes()) if worker_path.exists()
                    else {**item, "status": "missing_worker_report"})
        report["finished_at"] = now()
        report["worker_artifacts_sha256"] = {path.name: sha(path.read_bytes()) for path in sorted(public_workers.iterdir())
                                             if path.is_file() and not path.name.endswith(".partial")}
        progress(output, report)
    print(json.dumps({"status": report["status"], "output": str(output),
        "finished_workers": len(report["workers"]), "expected_calls": EXPECTED_CALLS}), flush=True)
    return 0 if report["status"] == "completed" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--baseline-sha", default=BASELINE_SHA)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--parquet", type=Path, default=ROOT / ".artifacts/round4-inputs/hotpot-validation.parquet")
    parser.add_argument("--state", type=Path, help="New private directory under .artifacts; retained after failures")
    parser.add_argument("--output", type=Path, help="New public JSON report; sibling .workers directory retains every ledger")
    parser.add_argument("--tokenizer-cache", type=Path, help="Reuse this tokenizer-file cache without clearing it")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--run", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.worker:
        require(args.run is not None, "Worker requires the original diagnostic run identity")
        return worker(args)
    require(args.state is not None and args.output is not None, "Provide new state and output paths")
    return controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
