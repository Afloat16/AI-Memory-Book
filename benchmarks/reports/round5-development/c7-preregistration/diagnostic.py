"""One fixed C6 SDK tool-body profile and transparent transport call counts.

No product source edits, alternative retrieval or formal performance claims.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def write(path, value, mode="x"):
    with path.open(mode, encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def install_observer():
    """Wrap only registered tool.fn; leave its validation metadata unchanged."""
    import atexit
    from collections import Counter
    import cProfile
    from functools import wraps
    import io
    import pstats
    import threading
    import anyio
    import memory_book.mcp_server as product

    output = Path(os.environ["ROUND5_C7_PROFILE_DIRECTORY"])
    stream = (output / "observer-events.jsonl").open("x", encoding="utf-8", buffering=1)
    profile = cProfile.Profile()
    owner = threading.get_ident()
    tool_calls = tool_errors = server_count = 0
    counts = Counter()
    original_create_server = product.create_server
    original_write, original_flush = anyio.AsyncFile.write, anyio.AsyncFile.flush
    original_run_sync = anyio.to_thread.run_sync

    def emit(value):
        stream.write(dump(value) + "\n")
        stream.flush()

    def standard_stdout(file):
        return (type(getattr(file, "_fp", None)) is io.TextIOWrapper
                and file._fp.buffer is getattr(sys.stdout, "buffer", None))

    @wraps(original_write)
    async def counted_write(file, *args, **kwargs):
        if standard_stdout(file):
            counts["sdk_stdout_write"] += 1
        return await original_write(file, *args, **kwargs)

    @wraps(original_flush)
    async def counted_flush(file, *args, **kwargs):
        if standard_stdout(file):
            counts["sdk_stdout_flush"] += 1
        return await original_flush(file, *args, **kwargs)

    @wraps(original_run_sync)
    async def counted_run_sync(function, *args, **kwargs):
        name = getattr(function, "__qualname__", type(function).__qualname__)
        receiver = getattr(function, "__self__", None)
        if (type(receiver) is io.TextIOWrapper
                and receiver.buffer is getattr(sys.stdout, "buffer", None)):
            kind = "sdk_stdout:" + name
        else:
            kind = "other:" + name
        counts["to_thread_run_sync:" + kind] += 1
        return await original_run_sync(function, *args, **kwargs)

    def save_profile(label):
        binary = output / (label + ".pstats")
        profile.dump_stats(str(binary))
        stats = pstats.Stats(profile)
        functions = []
        for (filename, line, name), (primitive, total, own, cumulative, callers) in sorted(stats.stats.items()):
            functions.append({"filename": filename, "line": line, "name": name,
                "primitive_calls": primitive, "total_calls": total,
                "profile_self_seconds": own, "profile_cumulative_seconds": cumulative,
                "callers": [{"filename": key[0], "line": key[1], "name": key[2],
                              "stats": list(value) if isinstance(value, tuple) else value}
                            for key, value in sorted(callers.items())]})
        value = {"scope": "cProfile only while original recall_memory tool.fn executes",
            "boundary": "Instrumented attribution only; not recall latency, throughput, speedup or acceptance evidence.",
            "tool_calls_included": tool_calls, "primitive_calls": stats.prim_calls,
            "total_calls": stats.total_calls, "profile_total_seconds": stats.total_tt,
            "functions": functions, "pstats_sha256": sha(binary.read_bytes()),
            "pstats_bytes": binary.stat().st_size}
        write(output / (label + ".functions.json"), value)
        return {"pstats_path": binary.name, "pstats_sha256": value["pstats_sha256"],
                "functions_path": label + ".functions.json", "functions": len(functions),
                "tool_calls_included": tool_calls}

    @wraps(original_create_server)
    def observed_create_server(*args, **kwargs):
        nonlocal server_count, tool_calls, tool_errors
        server = original_create_server(*args, **kwargs)
        server_count += 1
        assert server_count == 1
        tool = server._tool_manager.get_tool("recall_memory")
        assert tool is not None and tool.is_async is False
        original_fn, metadata, parameters = tool.fn, tool.fn_metadata, tool.parameters
        assert original_fn.__name__ == "recall_memory"
        assert Path(original_fn.__code__.co_filename).resolve() == Path(product.__file__).resolve()
        schema = dump(parameters)

        @wraps(original_fn)
        def observed_tool(*args, **kwargs):
            nonlocal tool_calls, tool_errors
            assert threading.get_ident() == owner
            assert tool.fn_metadata is metadata and tool.parameters is parameters and dump(parameters) == schema
            assert tool.is_async is False
            tool_calls += 1
            emit({"event": "tool_started", "sequence": tool_calls})
            failure = None
            profile.enable()
            try:
                return original_fn(*args, **kwargs)
            except BaseException as exc:
                failure = {"error_type": type(exc).__name__, "error": str(exc)}
                tool_errors += 1
                raise
            finally:
                profile.disable()
                emit({"event": "tool_finished", "sequence": tool_calls, "error": failure})
                if tool_calls == 1:
                    emit({"event": "first_call_profile", **save_profile("first-call")})

        tool.fn = observed_tool
        assert tool.fn_metadata is metadata and tool.parameters is parameters and dump(parameters) == schema
        emit({"event": "tool_wrapped", "original_filename": original_fn.__code__.co_filename,
              "original_line": original_fn.__code__.co_firstlineno,
              "metadata_identity_preserved": True, "schema_unchanged": True,
              "wrapper_invokes_original_fn": True, "is_async": tool.is_async})
        return server

    def finish():
        profile.disable()
        anyio.AsyncFile.write, anyio.AsyncFile.flush = original_write, original_flush
        anyio.to_thread.run_sync = original_run_sync
        product.create_server = original_create_server
        profiles = save_profile("all-calls")
        emit({"event": "observer_finished", "server_count": server_count,
              "tool_calls": tool_calls, "tool_errors": tool_errors,
              "transport_counts": dict(sorted(counts.items())), "profile": profiles})
        stream.close()

    emit({"event": "observer_started", "python": sys.version,
          "tool_body_only": True, "between_calls_profile_disabled": True,
          "transport_observation": "Count-only wrappers delegate unchanged AsyncFile.write/flush and to_thread.run_sync calls",
          "sqlite_connect_replaced": False, "json_loads_replaced": False,
          "token_counter_or_source_methods_replaced": False})
    anyio.AsyncFile.write, anyio.AsyncFile.flush = counted_write, counted_flush
    anyio.to_thread.run_sync = counted_run_sync
    product.create_server = observed_create_server
    atexit.register(finish)


def validate_inputs(plan):
    import importlib.metadata
    assert {name: importlib.metadata.version(name) for name in plan["packages"]} == plan["packages"]
    for name, expected in plan["environment_files"].items():
        assert sha(Path(name).read_bytes()) == expected, name
    sys.path[:0] = [plan["source_path"], str(ROOT)]
    from benchmarks.run import engine_source_hash
    from scripts.benchmark_default_recall import dataset
    import memory_book
    assert Path(memory_book.__file__).parent.resolve() == Path(plan["source_path"]) / "memory_book"
    assert engine_source_hash(Path(plan["source_path"]) / "memory_book") == plan["source"]["runtime_sha256"]
    assert subprocess.check_output(["git", "-C", plan["source_path"], "rev-parse", "HEAD"],
                                   text=True).strip() == plan["source"]["commit"]
    for name, expected in plan["input_files"].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    for name, expected in plan["diagnostic_files"].items():
        assert sha((DIRECTORY / name).read_bytes()) == expected, name
    worker = json.loads(gzip.decompress((ROOT / plan["reference_worker"]).read_bytes()))
    assert worker["source"] == plan["source"] and worker["status"] == "completed"
    assert sha((ROOT / plan["reference_worker"]).read_bytes()) == plan["reference_worker_sha256"]
    config = next(cell for cell in worker["configurations"] if cell["id"] == "mcp-token1024")
    data = dataset("public1015", ROOT / plan["locomo_path"])
    assert data.fingerprint == worker["dataset_sha256"] == plan["dataset_sha256"]
    assert len(config["rows"]) == len(data.queries) == plan["calls"] == 1015
    assert sha(dump([row["query_id"] for row in config["rows"]]).encode()) == plan["query_order_sha256"]
    assert {case.id for case in data.queries} == {row["query_id"] for row in config["rows"]}
    return worker, config, data

async def observe(plan, worker, config, data, output):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import recall_payload, _json
    from scripts.round4_performance import make_row, digest, TokenCounter, original_turn_texts
    from scripts.benchmark_default_recall import indexed_content
    from benchmarks.semantic_eval import source_snapshot
    source_db = ROOT / plan["database_path"]
    wal = Path(str(source_db) + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    database = output / "book.db"
    shutil.copyfile(source_db, database)
    counters = {name: TokenCounter(name) for name in ("cl100k_base", "o200k_base")}
    for counter in counters.values():
        counter.count("Prepare independent budget validation; no product query is issued.")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(DIRECTORY / "hook"), str(DIRECTORY), plan["source_path"])),
        "PYTHONDONTWRITEBYTECODE": "1", "ROUND5_C7_PROFILE_DIRECTORY": str(output),
        "MEMORY_BOOK_HOME": str(output / "isolated-home"), "MEMORY_BOOK_DB": str(database)}
    env["TIKTOKEN_CACHE_DIR"] = str(Path(env["TIKTOKEN_CACHE_DIR"]).resolve())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(database), "mcp"], env=env, cwd=str(output))
    cases, rows = {case.id: case for case in data.queries}, []
    with sqlite3.connect(database) as cache, (output / "attempts.jsonl").open("x") as ledger, \
            (output / "server-stderr.log").open("x") as errors:
        def append(value):
            ledger.write(dump(value) + "\n")
            ledger.flush()
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        before = {"source": source_snapshot(cache), "indexed": indexed_content(cache),
                  "revision": cache.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]}
        assert before["indexed"] == worker["indexed_content"]
        pages = dict(cache.execute("SELECT id,content FROM pages"))
        sources = original_turn_texts(data)
        async with stdio_client(parameters, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=60)) as client:
                initialized = await client.initialize()
                tools = await client.list_tools()
                session = worker["mcp_sessions"]["mcp-token1024"]
                assert sha((initialized.instructions or "").encode()) == session["mcp_instructions_sha256"]
                assert sha(tools.model_dump_json(exclude_none=True).encode()) == session["mcp_tool_schema_sha256"]
                for sequence, expected in enumerate(config["rows"], 1):
                    case = cases[expected["query_id"]]
                    cache.execute("DELETE FROM recall_cache")
                    cache.commit()
                    count = cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                    assert count == 0
                    append({"event": "call_started", "sequence": sequence, "query_id": case.id})
                    arguments = {"query": case.query, "project": case.project, "budget_chars": 8000,
                                 "budget_tokens": 1024, "tokenizer": "cl100k_base", "limit": 5}
                    response = await client.call_tool("recall_memory", arguments)
                    assert not response.isError and all(part.type == "text" for part in response.content)
                    payload = "\n".join(part.text for part in response.content)
                    body = json.loads(payload)
                    cached = cache.execute("SELECT payload FROM recall_cache").fetchall()
                    assert len(cached) == 1
                    native = json.loads(cached[0][0])
                    row = make_row(case, body, None, payload, response.model_dump_json(exclude_none=True),
                        native, config, counters, sources, pages, count, len(cached),
                        plan["source"]["runtime_sha256"], _json(recall_payload(native)))
                    row.pop("wall_ms")
                    row["sequence"] = sequence
                    append({"event": "call_finished", "row": row})
                    rows.append(row)
                    assert not any(row["invariants"].values())
                    for key in ("payload_sha256", "native_payload_sha256", "envelope_sha256",
                                "context_sha256", "token_metadata", "tokens"):
                        assert row[key] == expected[key], (case.id, key)
                    assert str(native["revision"]) == before["revision"]
                    if sequence % 128 == 0:
                        print(dump({"completed_calls": sequence, "formal_latencies_collected": False}), flush=True)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        after = {"source": source_snapshot(cache), "indexed": indexed_content(cache),
                 "revision": cache.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]}
        assert before == after
        assert cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0
    events = [json.loads(line) for line in (output / "observer-events.jsonl").read_text().splitlines()]
    finished = [row for row in events if row["event"] == "observer_finished"]
    starts = [row for row in events if row["event"] == "tool_started"]
    ends = [row for row in events if row["event"] == "tool_finished"]
    assert len(finished) == 1 and finished[0]["server_count"] == 1
    transport = finished[0]["transport_counts"]
    assert transport.get("sdk_stdout_write", 0) == transport.get("sdk_stdout_flush", -1) >= 1017
    assert finished[0]["tool_calls"] == len(rows) == len(starts) == len(ends) == 1015
    assert finished[0]["tool_errors"] == 0 and all(row["error"] is None for row in ends)
    assert [row["sequence"] for row in starts] == [row["sequence"] for row in ends] == list(range(1, 1016))
    profile = json.loads((output / "all-calls.functions.json").read_bytes())
    assert profile["tool_calls_included"] == 1015 and profile["functions"]
    assert sha((output / "all-calls.pstats").read_bytes()) == profile["pstats_sha256"]
    first = json.loads((output / "first-call.functions.json").read_bytes())
    assert first["tool_calls_included"] == 1 and first["functions"]
    assert sha((output / "first-call.pstats").read_bytes()) == first["pstats_sha256"]
    assert any(row["name"] == "recall_memory" and row["total_calls"] == 1015 for row in profile["functions"])
    return {"status": "completed", "source": plan["source"], "calls": len(rows),
        "all_payload_envelope_and_native_hashes_equal": True, "all_invariants_passed": True,
        "source_and_index_before": before, "source_and_index_after": after,
        "observer_finished": finished[0], "query_order_sha256": plan["query_order_sha256"],
        "profiles": {name: {"sha256": sha((output / name).read_bytes()), "bytes": (output / name).stat().st_size}
                     for name in ("first-call.pstats", "first-call.functions.json", "all-calls.pstats", "all-calls.functions.json")},
        "boundary": "One unchanged-source instrumented attribution run. Tool-body cProfile seconds are not formal latency or a speedup claim; transport observations are counts only."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DIRECTORY / "plan.json")
    parser.add_argument("--preflight", action="store_true", help="Check pinned files and inputs only; no database or SDK calls")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_bytes())
    if args.preflight:
        validate_inputs(plan)
        print(dump({"status": "preflight-passed-no-retrieval", "source": plan["source"], "calls_planned": 1015}))
        return
    output = DIRECTORY / plan["output_directory"]
    output.mkdir(exist_ok=False)
    write(output / "started.json", {"plan_sha256": sha(args.plan.read_bytes()),
          "at_utc": datetime.now(timezone.utc).isoformat(), "retry_policy": "No automatic retry; preserve all failures"})
    try:
        worker, config, data = validate_inputs(plan)
        report = asyncio.run(observe(plan, worker, config, data, output))
        validate_inputs(plan)
        report["plan_sha256"] = sha(args.plan.read_bytes())
        report["diagnostic_files"] = plan["diagnostic_files"]
        write(output / "summary.json", report)
        print(dump({"status": report["status"], "calls": report["calls"], "profiled_tool_calls": report["observer_finished"]["tool_calls"]}))
    except BaseException as exc:
        write(output / "failure.json", {"status": "failed-no-retry", "type": type(exc).__name__, "error": str(exc)})
        raise

if __name__ == "__main__":
    main()
