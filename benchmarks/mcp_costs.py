"""Measure actual MCP stdio startup, calls, and tokenizer-counted payloads.

Run with installed optional benchmark + MCP dependencies. Each --engine is a
label=checkout path. Fixture indexing and tokenization are outside call timing.
Counts describe reference encodings of returned text/protocol JSON, not billing
by a particular model provider or the host's private prompt serialization.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmarks.data import generate_dataset
from benchmarks.query_guard import require_query_count
from benchmarks.run import percentile


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def fingerprint(root):
    digest = hashlib.sha256()
    for path in sorted((root / "src" / "memory_book").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def summarize(values):
    return {"n": len(values), "mean": statistics.fmean(values),
            "p50": percentile(values, .5), "p95": percentile(values, .95),
            "min": min(values), "max": max(values)}


async def measure(label, root, dataset, work, encodings, repeats, budget,
                  budget_tokens=None, tokenizer="cl100k_base"):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    source_hash = fingerprint(root)
    source = work / "sessions.json"
    source.write_text(dump(dataset.sessions), encoding="utf-8")
    database = work / "memory.db"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(root / "src"), *sys.path])
    environment["MEMORY_BOOK_HOME"] = str(work / "isolated-home")
    environment["MEMORY_BOOK_DB"] = str(database)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    prepared = subprocess.run([sys.executable, "-m", "memory_book", "--db", str(database),
                               "import", str(source)], env=environment,
                              cwd=work, capture_output=True, text=True, timeout=120)
    if prepared.returncode:
        raise RuntimeError(prepared.stderr)
    rows, startups, schemas, instructions, detail_costs = [], [], [], [], []
    keys = [(case.query, case.project) for case in dataset.queries]
    assert len(dataset.queries) == len({case.id for case in dataset.queries}), "Fixture query IDs must be unique"
    distinct_pairs = len(set(keys))
    duplicate_cache_clears = 0
    for repetition in range(repeats):
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM recall_cache")
        parameters = StdioServerParameters(command=sys.executable,
            args=["-m", "memory_book", "--db", str(database), "mcp"], env=environment)
        started = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                startup = (time.perf_counter_ns() - started) / 1e6
                tools = await client.list_tools()
                startups.append(startup)
                schema = tools.model_dump_json(exclude_none=True)
                instruction = initialized.instructions or ""
                schemas.append({name: len(encoding.encode(schema)) for name, encoding in encodings.items()})
                instructions.append({name: len(encoding.encode(instruction)) for name, encoding in encodings.items()})
                supports_details = any(tool.name == "recall_memory" and
                    "details" in tool.inputSchema.get("properties", {}) for tool in tools.tools)
                compact_results = {}
                seen_pairs = set()
                cases = list(dataset.queries)
                random.Random(740 + repetition).shuffle(cases)
                for case in cases:
                    arguments = {"query": case.query, "project": case.project,
                                 "budget_chars": budget, "limit": 5}
                    if budget_tokens is not None:
                        arguments.update(budget_tokens=budget_tokens, tokenizer=tokenizer)
                    pair = (case.query, case.project)
                    duplicate_pair = pair in seen_pairs
                    if duplicate_pair:
                        # A separate annotation can ask the same question.
                        # Keep its ID, but do not time a previous row's cached
                        # response as a first call. Commit before starting the
                        # clock; the following immediate repeat remains hot.
                        with sqlite3.connect(database) as connection:
                            connection.execute("DELETE FROM recall_cache")
                        duplicate_cache_clears += 1
                    seen_pairs.add(pair)
                    for state in ("first_call_after_cache_clear", "immediate_repeat"):
                        before = time.perf_counter_ns()
                        response = await client.call_tool("recall_memory", arguments)
                        elapsed = (time.perf_counter_ns() - before) / 1e6
                        if response.isError:
                            raise RuntimeError(str(response))
                        text = "\n".join(part.text for part in response.content if part.type == "text")
                        body = json.loads(text)
                        envelope = response.model_dump_json(exclude_none=True)
                        context = body["context"]
                        assert len(context) <= budget
                        if budget_tokens is not None:
                            assert len(encodings[tokenizer].encode(context, disallowed_special=())) <= budget_tokens
                        if state == "first_call_after_cache_clear":
                            assert body.get("cache_hit") is not True, "First-call measurement returned a cached response"
                        compact_results[case.id] = (arguments, body, text)
                        row = {"query_id": case.id, "category": case.category,
                               "repeat": repetition, "state": state,
                               "duplicate_pair_cache_clear": duplicate_pair and state == "first_call_after_cache_clear",
                               "reported_cache_hit": body.get("cache_hit"),
                               "wall_ms": elapsed, "context_chars": len(context),
                               "result_count": len(body.get("results", [])),
                               "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
                               "page_ids": [item["id"] for item in body.get("results", [])],
                               "response_text_utf8_bytes": len(text.encode()),
                               "tokens": {name: {
                                   "context": len(encoding.encode(context)),
                                   "response_text": len(encoding.encode(text)),
                                   "response_envelope_json": len(encoding.encode(envelope)),
                                   "tool_arguments_json": len(encoding.encode(dump(arguments))),
                               } for name, encoding in encodings.items()}}
                        rows.append(row)
                # Measure detailed metadata only after all timed calls in the
                # last repetition. This comparison holds evidence text fixed.
                if repetition == repeats - 1 and supports_details:
                    for case_id, (arguments, compact, compact_text) in compact_results.items():
                        response = await client.call_tool("recall_memory", {**arguments, "details": True})
                        if response.isError:
                            raise RuntimeError(str(response))
                        detailed_text = "\n".join(part.text for part in response.content if part.type == "text")
                        detailed = json.loads(detailed_text)
                        assert detailed["context"] == compact["context"], "Detail mode changed evidence"
                        assert [item["id"] for item in detailed["results"]] == [item["id"] for item in compact["results"]]
                        detail_costs.append({"query_id": case_id, "context_identical": True,
                            "tokens": {name: {"compact_response_text": len(encoding.encode(compact_text)),
                                              "detailed_response_text": len(encoding.encode(detailed_text))}
                                       for name, encoding in encodings.items()}})
    assert source_hash == fingerprint(root), "Engine changed during measurement"
    aggregate = {}
    for state in ("first_call_after_cache_clear", "immediate_repeat"):
        selected = [row for row in rows if row["state"] == state]
        aggregate[state] = {"wall_ms": summarize([row["wall_ms"] for row in selected]),
            "tokens": {name: {key: summarize([row["tokens"][name][key] for row in selected])
                        for key in ("context", "response_text", "response_envelope_json", "tool_arguments_json")}
                       for name in encodings}}
    return {"label": label, "engine_sha256": source_hash,
            "native_budget_tokens": budget_tokens, "native_tokenizer": tokenizer if budget_tokens is not None else None,
            "startup_to_initialize_ms": summarize(startups),
            "tool_list_json_tokens": schemas, "initialization_instruction_tokens": instructions,
            "query_pair_counts": {"query_rows": len(keys),
                                  "distinct_query_project_pairs": distinct_pairs,
                                  "duplicate_query_project_rows": len(keys) - distinct_pairs,
                                  "duplicate_pair_cache_clears": duplicate_cache_clears},
            "aggregate": aggregate, "rows": rows, "same_evidence_detail_comparison": detail_costs}


async def main_async(args):
    import tiktoken
    encodings = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}
    if args.corpus == "locomo":
        from benchmarks.public_data import load_locomo
        if args.locomo_path is None:
            raise ValueError("--corpus locomo requires --locomo-path")
        dataset = load_locomo(args.locomo_path, split=args.split, max_queries=args.max_queries)
    else:
        dataset = generate_dataset(seed=args.seed, split=args.split, projects=args.projects)
    require_query_count(dataset, getattr(args, "expected_queries", None))
    results = []
    native_labels = set(getattr(args, "native_token_engine", None) or [])
    labels = {value.partition("=")[0] for value in args.engine}
    if native_labels - labels:
        raise ValueError("--native-token-engine names an unknown engine")
    with tempfile.TemporaryDirectory(prefix="mcp-costs-", dir=args.work_dir) as temporary:
        for index, value in enumerate(args.engine):
            label, separator, path = value.partition("=")
            if not separator:
                raise ValueError("--engine expects LABEL=/absolute/checkout")
            root = Path(path).resolve()
            work = Path(temporary) / str(index)
            work.mkdir()
            print(f"Measuring {label} via real MCP stdio", file=sys.stderr, flush=True)
            token_cap = args.budget_tokens if label in native_labels else None
            results.append(await measure(label, root, dataset, work, encodings, args.repeats, args.budget_chars,
                                         budget_tokens=token_cap, tokenizer=getattr(args, "tokenizer", "cl100k_base")))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "fixture": dataset.description(), "budget_chars": args.budget_chars,
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "sqlite": sqlite3.sqlite_version, "mcp": importlib.metadata.version("mcp"),
                              "tiktoken": importlib.metadata.version("tiktoken")},
              "scope": ["Actual official-SDK subprocess stdio, not a hand-written wire approximation.",
                        "Indexing and tokenization are excluded from call latency; startup is reported separately.",
                        "First calls disable prior query-result entries; OS/SQLite caches are not flushed.",
                        "All query IDs are retained. Each repeated exact (query, project) pair clears recall_cache through a separate SQLite connection before its timed first call; cache clearing is excluded from call latency and recorded per row.",
                        "Immediate repeats retain cache entries. This is not a guarantee for novel questions.",
                        "Token counts are exact for named reference encodings, not provider billing or host prompt formats.",
                        "Tool schemas/instructions are counted separately; hosts decide how often to include them.",
                        "No model inference, network model call, or generated-answer quality is measured."],
              "engines": results}
    if native_labels:
        report["scope"].append("Native token caps apply only to named engines. Older engines retain their character-only MCP response; this actual transport comparison is distinct from common token-capped evidence evaluation.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if args.output.name.endswith(".json.gz"):
        compressed = gzip.compress(encoded, mtime=0)
        assert gzip.decompress(compressed) == encoded
        args.output.write_bytes(compressed)
        summary_engines = []
        for result in results:
            summary = {key: value for key, value in result.items()
                       if key not in {"rows", "same_evidence_detail_comparison"}}
            comparisons = result["same_evidence_detail_comparison"]
            summary["same_evidence_detail_comparison"] = {
                "queries": len(comparisons),
                "all_contexts_identical": all(row["context_identical"] for row in comparisons),
                "mean_tokens": {name: {key: statistics.fmean(row["tokens"][name][key] for row in comparisons)
                                        for key in ("compact_response_text", "detailed_response_text")}
                                for name in encodings} if comparisons else None}
            summary_engines.append(summary)
        summary = {**report, "engines": summary_engines,
                   "artifact": {"path": args.output.name, "uncompressed_sha256": hashlib.sha256(encoded).hexdigest()}}
        summary_path = args.output.with_name(args.output.name.removesuffix(".json.gz") + ".summary.json")
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        args.output.write_bytes(encoded)
    print(json.dumps({"output": str(args.output), "engines": [
        {"label": result["label"], "startup_ms": result["startup_to_initialize_ms"],
         "aggregate": result["aggregate"]} for result in results]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", action="append", required=True)
    parser.add_argument("--corpus", choices=("synthetic", "locomo"), default="synthetic")
    parser.add_argument("--split", choices=("development", "heldout"), default="development")
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--max-queries", type=int, default=256)
    parser.add_argument("--expected-queries", type=int)
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--budget-chars", type=int, default=2000)
    parser.add_argument("--budget-tokens", type=int)
    parser.add_argument("--tokenizer", choices=("cl100k_base", "o200k_base"), default="cl100k_base")
    parser.add_argument("--native-token-engine", action="append", help="Only this engine receives the native token cap")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or args.projects < 1 or args.max_queries < 0:
        parser.error("--repeats and --projects must be positive; --max-queries must be nonnegative")
    if bool(args.native_token_engine) != (args.budget_tokens is not None) or (args.budget_tokens is not None and args.budget_tokens < 1):
        parser.error("A positive --budget-tokens and at least one --native-token-engine must be supplied together")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
