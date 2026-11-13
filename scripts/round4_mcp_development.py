"""Old-public128 actual-MCP development diagnostic; never formal acceptance.

Four fresh sequential SDK/server workers run baseline/candidate, then
candidate/baseline. The 128 historical IDs use the native development selector;
no answers or outcomes influence selection. Each call clears only persistent
recall_cache before its timer, preserving normal SDK, server and cache-write
costs. Every call, negative result and incomplete attempt is retained. This
module does not invoke the formal controller, worker, claim or acceptance gate.
Importing it performs no dataset reads, model inference or retrieval.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import timedelta
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round4_performance as shared
from scripts.round4_cold_development import (
    BASELINE, BASELINE_SHA, create, launch, now, order, progress, require,
    schedule, sha, source_record,
)
from scripts.benchmark_default_recall import dataset, indexed_content, rss, server_rss, storage
from benchmarks.run import original_turn_texts
from benchmarks.semantic_eval import source_snapshot
from benchmarks.token_compare import ENCODINGS, TokenCounter, latency_summary

VERSION = "round4-old-public128-actual-mcp-development-1"
COHORT = "public1015"
# This is the converted heldout dataset identity, separate from raw LoCoMo bytes.
DATASET_SHA = "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"
COUNT = 128
EXPECTED_CALLS = 512
SELECTION_PREFIX = "round4-native-development-v1/"
CONFIG = {"id": "mcp-token1024", "surface": "official-sdk-mcp-stdio",
          "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"}
PACKAGES = {"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode())


def file_sha(path):
    return sha(Path(path).read_bytes())


def evaluator_files():
    names = {"scripts/round4_mcp_development.py", "scripts/round4_cold_development.py",
             "scripts/round4_development_pair.py", "scripts/round4_performance.py",
             "benchmarks/experiments/round2-default-recall-performance-plan.json", *shared.HELPERS}
    return {name: file_sha(ROOT / name) for name in sorted(names)}


def selected_cases(data):
    require(len(data.queries) == 1015 and data.fingerprint == DATASET_SHA,
            "Only the exact historical public1015 dataset is allowed")
    ids = [case.id for case in data.queries]
    require(len(ids) == len(set(ids)) and all(isinstance(value, str) and value for value in ids),
            "Historical query IDs differ")
    return sorted(data.queries, key=lambda case: (
        hashlib.sha256((SELECTION_PREFIX + case.id).encode()).digest(), case.id))[:COUNT]


def input_identity(path):
    manifest = json.loads((ROOT / "benchmarks/locomo_split.json").read_bytes())
    raw = Path(path).read_bytes()
    require(len(raw) == manifest["bytes"] and sha(raw) == manifest["sha256"],
            "Old public source bytes differ")
    return {"sha256": sha(raw), "bytes": len(raw)}


def database_files(path):
    path = Path(path)
    return {suffix or "db": {"sha256": file_sha(Path(str(path) + suffix)),
                             "bytes": Path(str(path) + suffix).stat().st_size}
            for suffix in ("", "-wal", "-shm") if Path(str(path) + suffix).is_file()}


def immutable_baseline_database(path):
    require(Path(path).is_file(), "The supplied baseline database is missing")
    require(not Path(str(path) + "-wal").exists() or Path(str(path) + "-wal").stat().st_size == 0,
            "Close/checkpoint the baseline database before copying it")
    return database_files(path)


def database_snapshot(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        return {"source_sha256": source_snapshot(connection),
                "indexed_content": indexed_content(connection), "storage": storage(connection, path),
                "cache_rows": connection.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}


class Ledger:
    """Exclusive fsynced events plus a durable worker checkpoint for each call."""
    def __init__(self, path, output, report):
        self.stream = path.open("x", encoding="utf-8")
        self.output, self.report = output, report

    def event(self, value):
        self.stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def start(self, identity):
        sequence = self.report["attempts_started"]
        self.event({"event": "started", "seq": sequence, "query_id": identity,
                    "configuration": CONFIG["id"], "at": now()})
        self.report["attempts_started"] += 1
        return sequence

    def finish(self, sequence, row):
        self.event({"event": "finished", "seq": sequence, "row": row, "at": now()})
        self.report["rows"].append(row)
        self.report["attempts_finished"] += 1
        progress(self.output, self.report)

    def close(self):
        self.stream.close()


async def measure(cases, identities, database, work, source, counters, sources, pages, report, ledger):
    """One real SDK session. No retrieval/projection is repeated for validation."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import recall_payload, _json
    environment = {**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1",
        "MEMORY_BOOK_HOME": str(work / "isolated-home"), "MEMORY_BOOK_DB": str(database)}
    if environment.get("TIKTOKEN_CACHE_DIR"):
        environment["TIKTOKEN_CACHE_DIR"] = str(Path(environment["TIKTOKEN_CACHE_DIR"]).resolve())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(database), "mcp"], env=environment, cwd=str(work))
    with closing(sqlite3.connect(database)) as cache:
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        begin = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                report["initialization"]["startup_to_initialize_ms"] = (time.perf_counter_ns() - begin) / 1e6
                tools = await client.list_tools()
                schema = tools.model_dump_json(exclude_none=True)
                instructions = initialized.instructions or ""
                report["initialization"].update(tool_schema_sha256=sha(schema.encode()),
                    instructions_sha256=sha(instructions.encode()),
                    tokens={name: {"tool_schema": counter.count(schema), "instructions": counter.count(instructions)}
                            for name, counter in counters.items()})
                report["server_rss_before_calls"] = server_rss()
                require(report["server_rss_before_calls"]["available"], "Live MCP server RSS is unavailable")
                for identity in identities:
                    case = cases[identity]
                    cache.execute("DELETE FROM recall_cache")
                    cache.commit()
                    before = cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                    require(before == 0, "Persistent result cache was not empty before timing")
                    arguments = {"query": case.query, "project": case.project, "budget_chars": 8000,
                                 "budget_tokens": 1024, "tokenizer": "cl100k_base", "limit": 5}
                    sequence = ledger.start(identity)
                    row = {"query_id": identity, "configuration": CONFIG["id"], "status": "running"}
                    begin = time.perf_counter_ns()
                    try:
                        result = await client.call_tool("recall_memory", arguments)
                        row["wall_ms"] = (time.perf_counter_ns() - begin) / 1e6
                        # Hash the complete returned SDK value even when its content is an error.
                        envelope = result.model_dump_json(exclude_none=True)
                        row["envelope_sha256"] = sha(envelope.encode())
                        row["envelope_utf8_bytes"] = len(envelope.encode())
                        require(all(part.type == "text" for part in result.content), "Unexpected MCP content type")
                        payload = "\n".join(part.text for part in result.content)
                        row["payload_sha256"] = sha(payload.encode())
                        row["response_utf8_bytes"] = len(payload.encode())
                        require(not result.isError, "MCP returned an error")
                        response = json.loads(payload)
                        cached = cache.execute("SELECT payload FROM recall_cache").fetchall()
                        require(len(cached) == 1, "MCP must write exactly one full native cache record")
                        native = json.loads(cached[0][0])
                        row["native_latency_present"] = "latency_ms" in native
                        native.pop("latency_ms", None)  # The sole native field excluded from equality.
                        row["native_payload_sha256"] = shared.digest(native)
                        row.update(shared.make_row(case, response, row["wall_ms"], payload, envelope,
                            native, CONFIG, counters, sources, pages, before, len(cached),
                            report["source"]["source_sha256"], _json(recall_payload(native))))
                        require(not any(row["invariants"].values()), "MCP source/budget/cache invariant failed")
                        row["status"] = "completed"
                    except BaseException as error:
                        row.setdefault("wall_ms", (time.perf_counter_ns() - begin) / 1e6)
                        row.update(status="failed", error_type=type(error).__name__)
                        raise
                    finally:
                        ledger.finish(sequence, row)
                report["server_rss_after_calls"] = server_rss()
                require(report["server_rss_after_calls"]["available"], "Live MCP server RSS is unavailable")
                report["storage_after_calls_live"] = storage(cache, database)
        # Keep the final cache record and database as evidence; no cleanup/replay.


def worker(args):
    run = json.loads(args.run.read_bytes())
    item = next(item for item in run["schedule"] if item["key"] == args.worker)
    state = Path(run["state"]) / item["key"]
    prefix = Path(run["worker_directory"]) / item["key"]
    output, ledger_path = prefix.with_suffix(".json"), prefix.with_suffix(".attempts.jsonl")
    require(json.loads(prefix.with_suffix(".started.json").read_bytes()) ==
            {"worker": item, "run_sha256": digest(run)}, "Worker start intent differs")
    require(not state.exists() and not output.exists() and not ledger_path.exists(), "Never repeat a development worker")
    state.mkdir()
    source = Path(run["sources"][item["label"]]["path"])
    expected = run["sources"][item["label"]]["sha256"]
    report = {"schema_version": 1, "protocol": VERSION, **item, "cohort": COHORT,
        "run_sha256": digest(run), "status": "running", "started_at": now(),
        "expected_calls": COUNT, "attempts_started": 0, "attempts_finished": 0,
        "rows": [], "initialization": {}, "error": None}
    create(output, report)
    ledger = Ledger(ledger_path, output, report)
    database = state / "book.db"
    baseline_db = Path(run["baseline_database"]["path"])
    try:
        require(evaluator_files() == run["evaluator_files"], "Development helper files changed")
        report["packages"] = {name: importlib.metadata.version(name) for name in PACKAGES}
        require(report["packages"] == PACKAGES, "SDK/Pydantic/tokenizer versions differ")
        report["source"] = source_record(source)
        require(report["source"]["source_sha256"] == expected
                and report["source"]["provenance"]["commit_identifies_source"], "Runtime source differs from exact committed files")
        if item["label"] == "baseline":
            require(report["source"]["provenance"]["git_commit"] == BASELINE
                    and expected == BASELINE_SHA, "Baseline is not released v0.3.1")
        sys.path.insert(0, str(source))
        begin = time.perf_counter_ns()
        import memory_book
        require(Path(memory_book.__file__).resolve().parent == source / "memory_book", "Imported a different runtime")
        report["runtime_import_ms"] = (time.perf_counter_ns() - begin) / 1e6
        report["runtime_version"] = memory_book.__version__
        report["input_before"] = input_identity(run["locomo_path"])
        require(report["input_before"] == run["input_identity"], "Input changed after development intent")
        data = dataset(COHORT, Path(run["locomo_path"]))
        selected = selected_cases(data)
        ids = [case.id for case in selected]
        report["dataset"] = {"sha256": data.fingerprint, "queries": len(data.queries),
            "selected_queries": len(ids), "selected_ids_sha256": digest(ids),
            "selection_prefix": SELECTION_PREFIX, "selection_uses_labels": False}
        sources = original_turn_texts(data)
        report["baseline_database_before"] = immutable_baseline_database(baseline_db)
        require(report["baseline_database_before"] == run["baseline_database"]["files"], "Baseline DB changed after intent")
        shutil.copyfile(baseline_db, database)
        require(file_sha(database) == run["baseline_database"]["files"]["db"]["sha256"], "Copied DB bytes differ")
        report["database_before"] = database_snapshot(database)
        report["database_files_before"] = database_files(database)
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            originals = {(project, session, ordinal): content for project, session, ordinal, content in connection.execute(
                "SELECT s.project_id,s.external_id,t.ordinal,t.content FROM turns t JOIN sessions s ON s.id=t.session_pk")}
            require(originals == sources, "Copied baseline DB is not exactly the old public source turns")
            pages = dict(connection.execute("SELECT id,content FROM pages"))
        counters = {name: TokenCounter(name) for name in ENCODINGS}
        for counter in counters.values():
            require(counter.version == PACKAGES["tiktoken"], "Reference tokenizer differs")
            counter.count("Initialize reference encodings outside all SDK query timers.")
        report["rss_before_calls"] = rss()
        progress(output, report)
        # Config index 2 is native-token1024 in the prior development diagnostic.
        asyncio.run(measure({case.id: case for case in selected}, order(ids, item["round"], 2),
            database, state, source, counters, sources, pages, report, ledger))
        report["rss_after_calls"] = rss()
        report["database_after"] = database_snapshot(database)
        require(report["database_after"]["source_sha256"] == report["database_before"]["source_sha256"]
                and report["database_after"]["indexed_content"] == report["database_before"]["indexed_content"],
                "MCP recall changed source or indexed content")
        report["source_after"] = source_record(source)
        require(report["source_after"]["source_sha256"] == expected, "Runtime source changed during worker")
        report["input_after"] = input_identity(run["locomo_path"])
        report["baseline_database_after"] = immutable_baseline_database(baseline_db)
        report["packages_after"] = {name: importlib.metadata.version(name) for name in PACKAGES}
        require(report["input_after"] == report["input_before"]
                and report["baseline_database_after"] == report["baseline_database_before"]
                and report["packages_after"] == report["packages"]
                and evaluator_files() == run["evaluator_files"], "Inputs or evaluator changed during worker")
        require(report["attempts_started"] == report["attempts_finished"] == COUNT
                and all(row["status"] == "completed" for row in report["rows"]), "Worker is incomplete")
        report["latency"] = latency_summary([row["wall_ms"] for row in report["rows"]])
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__})
    finally:
        ledger.close()
        report.update(finished_at=now(), ledger_sha256=file_sha(ledger_path))
        for name, operation in (("source_after", lambda: source_record(source)),
            ("input_after", lambda: input_identity(run["locomo_path"])),
            ("baseline_database_after", lambda: immutable_baseline_database(baseline_db)),
            ("database_after", lambda: database_snapshot(database)),
            ("database_files_after", lambda: database_files(database)),
            ("packages_after", lambda: {name: importlib.metadata.version(name) for name in PACKAGES}),
            ("rss_at_finish", rss)):
            if name not in report:
                try:
                    report[name] = operation()
                except BaseException as error:
                    report[name + "_error_type"] = type(error).__name__
        progress(output, report)
    print(json.dumps({"worker": item["key"], "status": report["status"],
                      "calls": report["attempts_finished"]}), flush=True)
    return 0 if report["status"] == "completed" else 2


def assess(workers):
    require([worker["key"] for worker in workers] == [item["key"] for item in schedule()], "Wrong worker order")
    canonical, differences, sessions = {}, [], None
    initial_db, data_identity = workers[0]["database_before"], workers[0]["dataset"]
    for worker in workers:
        require(worker["status"] == "completed"
                and worker["attempts_started"] == worker["attempts_finished"] == len(worker["rows"]) == COUNT,
                "Failed or incomplete worker remains retained")
        require(worker["dataset"] == data_identity and data_identity["sha256"] == DATASET_SHA,
                "Selected old cohort differs")
        require(worker["database_before"] == initial_db
                and worker["database_after"]["source_sha256"] == initial_db["source_sha256"]
                and worker["database_after"]["indexed_content"] == initial_db["indexed_content"],
                "Source or indexed projection differs")
        init = {key: value for key, value in worker["initialization"].items() if key != "startup_to_initialize_ms"}
        require(sessions is None or sessions == init, "MCP tool schema/instructions/token costs differ")
        sessions = init
        ids = [row["query_id"] for row in worker["rows"]]
        require(len(set(ids)) == COUNT, "Duplicate query ID")
        selected = sorted(ids, key=lambda identity: (hashlib.sha256((SELECTION_PREFIX + identity).encode()).digest(), identity))
        require(digest(selected) == data_identity["selected_ids_sha256"]
                and ids == order(selected, worker["round"], 2), "Selection or call order changed")
        for row in worker["rows"]:
            require(row["status"] == "completed" and not any(row["invariants"].values()), "Failed response retained")
            value = shared.stable_row(row)
            if row["query_id"] in canonical and canonical[row["query_id"]] != value:
                differences.append({"worker": worker["key"], "query_id": row["query_id"],
                                    "first_sha256": digest(canonical[row["query_id"]]), "sha256": digest(value)})
            canonical.setdefault(row["query_id"], value)
    values = {label: {"pooled": latency_summary([row["wall_ms"] for worker in workers
                if worker["label"] == label for row in worker["rows"]]),
            "rounds": [{"round": worker["round"], "latency": worker["latency"]}
                       for worker in workers if worker["label"] == label]} for label in ("baseline", "candidate")}
    changes = {metric: 100 * (values["candidate"]["pooled"][metric] /
                             values["baseline"]["pooled"][metric] - 1)
               for metric in ("mean_ms", "p50_ms", "p95_ms")}
    return {"complete": True, "actual_mcp_calls": sum(len(worker["rows"]) for worker in workers),
        "payload_equivalence": not differences, "differences": differences,
        "latency": values, "candidate_change_percent": changes, "formal_acceptance": None,
        "boundary": "Old-data development only. Native cache record excludes only latency_ms; actual SDK text and CallToolResult JSON remain complete. No acceptance thresholds or OS-cold claim."}


def controller(args):
    require(args.baseline_src and args.candidate_src and args.candidate_sha and args.baseline_db and args.locomo_path,
            "Provide both source paths, candidate SHA, baseline database and old LoCoMo input")
    require(args.baseline_sha == BASELINE_SHA and re.fullmatch(r"[0-9a-f]{64}", args.candidate_sha),
            "Wrong baseline or candidate source hash")
    state, output = args.state.resolve(), args.output.resolve()
    workers = output.with_name(output.stem + ".workers")
    require(state.is_relative_to((ROOT / ".artifacts").resolve()), "Private worker state belongs under .artifacts")
    require(not state.exists() and not output.exists() and not workers.exists(), "Never overwrite a diagnostic attempt")
    state.mkdir(parents=True)
    workers.mkdir(parents=True)
    cache = Path(args.tokenizer_cache or os.environ.get("TIKTOKEN_CACHE_DIR") or state / "tokenizer-cache").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    run = {"schema_version": 1, "protocol": VERSION, "development_only": True,
        "sources": {label: {"path": str(getattr(args, label + "_src").resolve()),
                            "sha256": getattr(args, label + "_sha")} for label in ("baseline", "candidate")},
        "schedule": schedule(), "state": str(state), "worker_directory": str(workers), "output": str(output),
        "tokenizer_cache": str(cache), "locomo_path": str(args.locomo_path.resolve()),
        "input_identity": input_identity(args.locomo_path),
        "baseline_database": {"path": str(args.baseline_db.resolve()), "files": immutable_baseline_database(args.baseline_db)},
        "packages": PACKAGES, "configuration": CONFIG, "expected_calls": EXPECTED_CALLS,
        "evaluator_files": evaluator_files(), "selection_prefix": SELECTION_PREFIX,
        "host": {"python": platform.python_version(), "platform": platform.platform(),
                 "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()},
        "scope": "Old public1015 deterministic128 only; two balanced rounds, fresh worker/server per source. Persistent cache DELETE/COMMIT outside each timer. Normal server cache write, SDK serialization and roundtrip included. Tokenizer-file cache preserved. All negative samples retained. No formal acceptance or new validation selection."}
    run_path = state / "run.json"
    create(run_path, run)
    report = {"schema_version": 1, "protocol": VERSION, "run": run, "status": "running",
              "started_at": now(), "workers": [], "error": None}
    create(output, report)
    try:
        for item in run["schedule"]:
            prefix = workers / item["key"]
            create(prefix.with_suffix(".started.json"), {"worker": item, "run_sha256": digest(run)})
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", item["key"], "--run", str(run_path)]
            code = launch(command, {**os.environ, "TIKTOKEN_CACHE_DIR": str(cache), "PYTHONHASHSEED": "0",
                                   "PYTHONDONTWRITEBYTECODE": "1", "ORT_DISABLE_TELEMETRY": "1"})
            path = prefix.with_suffix(".json")
            report["workers"].append(json.loads(path.read_bytes()) if path.exists()
                else {**item, "status": "missing_worker_report", "exit_code": code})
            progress(output, report)
            require(code == 0 and report["workers"][-1]["status"] == "completed", "Stop after a failed worker")
        require(evaluator_files() == run["evaluator_files"], "Development evaluator changed")
        report["assessment"] = assess(report["workers"])
        require(report["assessment"]["actual_mcp_calls"] == EXPECTED_CALLS
                and report["assessment"]["payload_equivalence"], "Full MCP/native payloads differ")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__})
    finally:
        recorded = {worker["key"] for worker in report["workers"]}
        for item in run["schedule"]:
            prefix = workers / item["key"]
            if item["key"] not in recorded and prefix.with_suffix(".started.json").exists():
                path = prefix.with_suffix(".json")
                report["workers"].append(json.loads(path.read_bytes()) if path.exists()
                    else {**item, "status": "missing_worker_report"})
        report["finished_at"] = now()
        report["worker_artifacts_sha256"] = {path.name: file_sha(path) for path in sorted(workers.iterdir())
                                             if path.is_file() and not path.name.endswith(".partial")}
        progress(output, report)
    print(json.dumps({"status": report["status"], "workers": len(report["workers"]),
                      "expected_calls": EXPECTED_CALLS, "output": str(output)}), flush=True)
    return 0 if report["status"] == "completed" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--baseline-sha", default=BASELINE_SHA)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--baseline-db", type=Path, help="Closed baseline public1015 database, copied per worker")
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tokenizer-cache", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--run", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.worker:
        require(args.run is not None, "Worker needs its original development intent")
        return worker(args)
    require(args.state is not None and args.output is not None, "Provide new state/output paths")
    return controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
