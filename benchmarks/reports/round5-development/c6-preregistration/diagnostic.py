"""One fixed C5 SDK SQL observation; no measured latencies or source changes."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write(path, value, mode="x"):
    with path.open(mode, encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def family(sql):
    value = " ".join(sql.split())
    for needle, label in (
        ("INSERT OR REPLACE INTO recall_cache", "result_cache_insert"),
        ("DELETE FROM recall_cache", "result_cache_eviction"),
        ("SELECT payload FROM recall_cache", "result_cache_lookup"),
        ("WITH requested(chapter_id,session_pk)", "candidate_directory_pairs"),
        ("SELECT id,project_id,chapter_id,session_pk", "candidate_light_metadata"),
        ("SELECT p.id,p.project_id,p.chapter_id", "candidate_full_metadata"),
        ("SELECT ordinal,content FROM turns", "original_turns"),
        ("SELECT rowid,body FROM pages_fts", "novelty_body"),
        ("highlight(pages_stem_fts", "highlight_body"),
        ("p.content,p.source_refs", "selected_source_pages"),
        ("bm25(pages_stem_fts", "stem_fts_route"),
        ("bm25(pages_fts", "exact_fts_route"),
        ("SELECT value FROM meta WHERE key='revision'", "revision"),
        ("SELECT MIN(rid) FROM pages", "project_rowid_bounds"),
    ):
        if needle in value:
            return label
    if value in {"BEGIN", "BEGIN IMMEDIATE", "COMMIT", "ROLLBACK"}:
        return value.lower().replace(" ", "_")
    return "startup_or_other:" + value.split(" ", 1)[0].lower()


def install_observer():
    """Installed only in the real SDK child by the fixed sitecustomize hook."""
    import atexit
    output = Path(os.environ["ROUND5_C6_SQL_TRACE"])
    stream = output.open("x", encoding="utf-8", buffering=1)
    original_connect = sqlite3.connect
    templates, connections, loads = {}, [], defaultdict(lambda: [0, 0])
    sequence = query_sequence = 0
    loads_code = json.loads.__code__

    def emit(value):
        stream.write(dump(value) + "\n")

    class ObservedConnection(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.observer_id = len(connections) + 1
            connections.append(self.observer_id)
            emit({"event": "connection_open", "connection": self.observer_id,
                  "thread": threading.get_ident(), "database": str(args[0]),
                  "cached_statements": kwargs.get("cached_statements", 128)})

        def observe(self, method, sql, parameters, invoke):
            nonlocal sequence, query_sequence
            if sql not in templates:
                templates[sql] = len(templates) + 1
                emit({"event": "template", "id": templates[sql], "sql": sql,
                      "family": family(sql), "characters": len(sql),
                      "utf8_bytes": len(sql.encode()), "placeholders": sql.count("?")})
            if method == "execute" and sql == "BEGIN":
                query_sequence += 1
            sequence += 1
            row = {"event": "sql", "sequence": sequence, "connection": self.observer_id,
                   "thread": threading.get_ident(), "query_sequence": query_sequence or None,
                   "template": templates[sql], "method": method,
                   "parameter_count": len(parameters) if type(parameters) in (tuple, list, dict) else None}
            try:
                result = invoke()
            except BaseException as exc:
                emit({**row, "success": False, "error_type": type(exc).__name__, "error": str(exc)})
                raise
            emit({**row, "success": True})
            return result

        def execute(self, sql, parameters=(), /):
            return self.observe("execute", sql, parameters,
                lambda: super(ObservedConnection, self).execute(sql, parameters))

        def executemany(self, sql, parameters, /):
            return self.observe("executemany", sql, None,
                lambda: super(ObservedConnection, self).executemany(sql, parameters))

        def executescript(self, sql, /):
            return self.observe("executescript", sql, None,
                lambda: super(ObservedConnection, self).executescript(sql))

        def close(self):
            super().close()
            emit({"event": "connection_close", "connection": self.observer_id,
                  "thread": threading.get_ident(), "query_sequence": query_sequence or None})

    def connect(*args, **kwargs):
        if "factory" in kwargs or len(args) > 5:
            raise RuntimeError("Unexpected custom connection factory; stop this observation")
        return original_connect(*args, factory=ObservedConnection, **kwargs)

    def profile(frame, event, value):
        if event != "call" or frame.f_code is not loads_code:
            return
        caller = frame.f_back
        filename = caller.f_code.co_filename
        # Record all Python json.loads callers without saving their input text.
        query = query_sequence if "/memory_book/" in filename else None
        source = frame.f_locals["s"]
        size = (len(source.encode("utf-8", "surrogatepass")) if type(source) is str
                else len(source) if type(source) in (bytes, bytearray) else 0)
        key = (query, filename, caller.f_code.co_name, caller.f_lineno, type(source).__name__)
        loads[key][0] += 1
        loads[key][1] += size

    def finish():
        sys.setprofile(None)
        threading.setprofile(None)
        for (query, filename, caller, line, kind), (count, size) in loads.items():
            emit({"event": "json_loads", "query_sequence": query, "filename": filename,
                  "caller": caller, "line": line, "input_type": kind,
                  "calls": count, "input_utf8_bytes_or_bytes": size})
        emit({"event": "observer_finished", "connections": len(connections),
              "read_transactions": query_sequence, "sql_calls": sequence,
              "templates": len(templates)})
        stream.close()

    emit({"event": "observer_started", "sqlite_connect_signature": original_connect.__text_signature__,
          "sqlite_version": sqlite3.sqlite_version, "python": sys.version,
          "scope": "Application Connection.execute/executemany/executescript; no SQLite internal SQL, no timing"})
    sqlite3.connect = connect
    atexit.register(finish)
    sys.setprofile(profile)
    threading.setprofile(profile)


def replay(events, capacities):
    templates = {row["id"]: row for row in events if row["event"] == "template"}
    raw = [row for row in events if row["event"] == "sql"]
    calls = [row for row in raw if row["method"] != "executescript" and row["success"]]
    distance = defaultdict(OrderedDict)
    reuse_histogram, family_rows = Counter(), {}
    reuse_by_sequence = {}
    for row in calls:
        template = templates[row["template"]]
        group = family_rows.setdefault(template["family"], {"calls": 0, "templates": set(),
            "placeholder_counts_by_call": Counter(), "sql_utf8_bytes_by_call": Counter(),
            "reuse_distances": Counter()})
        group["calls"] += 1
        group["templates"].add(template["id"])
        group["placeholder_counts_by_call"][template["placeholders"]] += 1
        group["sql_utf8_bytes_by_call"][template["utf8_bytes"]] += 1
        history, identity = distance[row["connection"]], template["id"]
        reuse = len(history) - 1 - list(history).index(identity) if identity in history else "cold"
        reuse_by_sequence[row["sequence"]] = reuse
        reuse_histogram[str(reuse)] += 1
        group["reuse_distances"][str(reuse)] += 1
        history[identity] = None
        history.move_to_end(identity)
    models = {}
    for capacity in capacities:
        caches, seen = defaultdict(OrderedDict), defaultdict(set)
        counts, by_family, by_query = Counter(), defaultdict(Counter), defaultdict(Counter)
        for row in calls:
            identity, connection = row["template"], row["connection"]
            cache = caches[connection]
            if identity in cache:
                result = "hit"
                cache.move_to_end(identity)
            else:
                result = "repeat_miss" if identity in seen[connection] else "cold_miss"
                if len(cache) >= capacity:
                    cache.popitem(last=False)
                cache[identity] = None
            seen[connection].add(identity)
            counts[result] += 1
            by_family[templates[identity]["family"]][result] += 1
            by_query[str(row["query_sequence"])][result] += 1
        def stats(values):
            result = {key: values[key] for key in ("hit", "cold_miss", "repeat_miss")}
            misses = result["cold_miss"] + result["repeat_miss"]
            result.update(calls=sum(result.values()), misses=misses,
                repeat_miss_fraction_of_misses=result["repeat_miss"] / misses if misses else 0)
            return result
        models[str(capacity)] = {"total": stats(counts),
            "families": {key: stats(value) for key, value in by_family.items()},
            "queries_including_startup": {key: stats(value) for key, value in by_query.items()}}
    for group in family_rows.values():
        identities = sorted(group.pop("templates"))
        group["template_ids"], group["distinct_templates"] = identities, len(identities)
        group["large_templates_at_least_32_placeholders"] = [templates[key] for key in identities
            if templates[key]["placeholders"] >= 32]
    return {"sql_calls": len(raw), "modeled_calls": len(calls), "distinct_templates": len(templates),
        "excluded_executescript_or_failed_calls": len(raw) - len(calls),
        "reuse_distance_definition": "Distinct application SQL templates used since the previous use, per connection; startup included.",
        "reuse_distances": dict(reuse_histogram), "families": family_rows, "models": models,
        "reuse_by_sql_sequence": reuse_by_sequence,
        "limitations": "LRU model only, not observed prepare/compile counts or elapsed time. Busy statements, schema invalidations and SQLite/FTS internal statements are not modeled."}


def validate_inputs(plan):
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
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(DIRECTORY), plan["source_path"])),
        "PYTHONDONTWRITEBYTECODE": "1", "ROUND5_C6_SQL_TRACE": str(output / "server-trace.jsonl"),
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
        sources = original_turn_texts(data.sessions)
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
                        print(dump({"completed_calls": sequence, "timings_collected": False}), flush=True)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        after = {"source": source_snapshot(cache), "indexed": indexed_content(cache),
                 "revision": cache.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]}
        assert before == after
        assert cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0
    events = [json.loads(line) for line in (output / "server-trace.jsonl").read_text().splitlines()]
    finished = [row for row in events if row["event"] == "observer_finished"]
    assert len(finished) == 1 and finished[0]["read_transactions"] == len(rows) == 1015
    assert all(row["success"] for row in events if row["event"] == "sql")
    models = replay(events, plan["offline_statement_lru_capacities"])
    write(output / "statement-models.json", models)
    loads = [row for row in events if row["event"] == "json_loads"]
    grouped = defaultdict(lambda: {"calls": 0, "input_utf8_bytes_or_bytes": 0})
    for row in loads:
        group = grouped[row["filename"] + ":" + str(row["line"]) + ":" + row["caller"]]
        for key in group:
            group[key] += row[key]
    return {"status": "completed", "source": plan["source"], "calls": len(rows),
        "all_payload_envelope_and_native_hashes_equal": True, "all_invariants_passed": True,
        "source_and_index_before": before, "source_and_index_after": after,
        "connection_events": [row for row in events if row["event"] in ("connection_open", "connection_close")],
        "observer_finished": finished[0], "sql_summary": {key: models[key] for key in
            ("sql_calls", "modeled_calls", "distinct_templates", "excluded_executescript_or_failed_calls")},
        "lru_totals": {key: value["total"] for key, value in models["models"].items()},
        "json_loads_by_caller": grouped, "query_order_sha256": plan["query_order_sha256"],
        "boundary": "One unchanged-source observation, no elapsed-time fields, no cache-size changes, no performance acceptance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DIRECTORY / "plan.json")
    parser.add_argument("--preflight", action="store_true", help="Check pinned files and inputs only; no database or SDK calls")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_bytes())
    worker, config, data = validate_inputs(plan)
    if args.preflight:
        print(dump({"status": "preflight-passed-no-retrieval", "source": plan["source"], "calls_planned": 1015}))
        return
    output = DIRECTORY / plan["output_directory"]
    output.mkdir(exist_ok=False)
    write(output / "started.json", {"plan_sha256": sha(args.plan.read_bytes()),
          "at_utc": datetime.now(timezone.utc).isoformat(), "retry_policy": "No automatic retry; preserve all failures"})
    try:
        report = asyncio.run(observe(plan, worker, config, data, output))
        validate_inputs(plan)
        report["plan_sha256"] = sha(args.plan.read_bytes())
        report["diagnostic_files"] = plan["diagnostic_files"]
        write(output / "summary.json", report)
        print(dump({"status": report["status"], "calls": report["calls"], "lru_totals": report["lru_totals"]}))
    except BaseException as exc:
        write(output / "failure.json", {"status": "failed-no-retry", "type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    main()
