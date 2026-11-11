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


async def measure(label, root, dataset, work, encodings, repeats, budget):
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
    assert len(keys) == len(set(keys)), "First-call fixture must contain unique query/scope pairs"
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
                cases = list(dataset.queries)
                random.Random(740 + repetition).shuffle(cases)
                for case in cases:
                    arguments = {"query": case.query, "project": case.project,
                                 "budget_chars": budget, "limit": 5}
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
                        compact_results[case.id] = (arguments, body, text)
                        row = {"query_id": case.id, "category": case.category,
                               "repeat": repetition, "state": state,
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
    return {"label": label, "engine_sha256": source_hash, "startup_to_initialize_ms": summarize(startups),
            "tool_list_json_tokens": schemas, "initialization_instruction_tokens": instructions,
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
    results = []
    with tempfile.TemporaryDirectory(prefix="mcp-costs-", dir=args.work_dir) as temporary:
        for index, value in enumerate(args.engine):
            label, separator, path = value.partition("=")
            if not separator:
                raise ValueError("--engine expects LABEL=/absolute/checkout")
            root = Path(path).resolve()
            work = Path(temporary) / str(index)
            work.mkdir()
            print(f"Measuring {label} via real MCP stdio", file=sys.stderr, flush=True)
            results.append(await measure(label, root, dataset, work, encodings, args.repeats, args.budget_chars))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "fixture": dataset.description(), "budget_chars": args.budget_chars,
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "sqlite": sqlite3.sqlite_version, "mcp": importlib.metadata.version("mcp"),
                              "tiktoken": importlib.metadata.version("tiktoken")},
              "scope": ["Actual official-SDK subprocess stdio, not a hand-written wire approximation.",
                        "Indexing and tokenization are excluded from call latency; startup is reported separately.",
                        "First calls disable prior query-result entries; OS/SQLite caches are not flushed.",
                        "Immediate repeats retain cache entries. This is not a guarantee for novel questions.",
                        "Token counts are exact for named reference encodings, not provider billing or host prompt formats.",
                        "Tool schemas/instructions are counted separately; hosts decide how often to include them.",
                        "No model inference, network model call, or generated-answer quality is measured."],
              "engines": results}
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
    parser.add_argument("--seed", type=int, default=61)
    parser.add_argument("--projects", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--budget-chars", type=int, default=2000)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or args.projects < 1 or args.max_queries < 0:
        parser.error("--repeats and --projects must be positive; --max-queries must be nonnegative")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
