"""Actual-SDK costs and paired latency for the frozen operator source format.

Only the two registered old regression corpora are used. Raw reports contain
IDs, hashes, counts and timings, not their questions or source text. Both modes
run the same committed runtime in sequential isolated workers. No model calls.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import gzip
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# This helper does not import memory_book. Runtime imports happen only after
# selecting the exact frozen source, separately in each worker process.
from scripts.benchmark_default_recall import (
    atomic_json, cases_for, dataset, digest, dump, indexed_content, numeric,
    server_rss, sha, storage,
)
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance, latency_summary

PLAN_PATH = ROOT / "benchmarks/experiments/indexed-references-operator-plan.json"
BINDING_PATH = ROOT / "benchmarks/experiments/indexed-references-operator-binding.json"
FIXTURE_PATH = ROOT / "tests/fixtures/mcp-object-reference-baseline.json"
COHORT_IDENTITIES = {c["name"]: c for c in json.loads((ROOT /
    "benchmarks/experiments/round2-default-recall-performance-plan.json").read_text())["cohorts"]}
COHORTS = ("synthetic61", "public1015")
BUDGETS = (2000, 4000, 8000)
DETAILS = (False, True)
FORMATS = ("objects", "indexed")
ENCODINGS = ("cl100k_base", "o200k_base")
ROUNDS = 4
REFERENCE_KEYS = frozenset(("project", "session_id", "turn_index"))
# Full initialization instructions from the frozen 2797562 format implementation
# (including the explicit zero-based clarification), checked before measurement.
INDEXED_INSTRUCTIONS_SHA256 = "627d79fb8974413ff773bce7a1c1d1acb4ce2bf90815c3ba52338c03ceb170ab"
DEPENDENCIES = (
    "scripts/benchmark_default_recall.py", "benchmarks/data.py",
    "benchmarks/public_data.py", "benchmarks/run.py", "benchmarks/token_compare.py",
    "benchmarks/query_guard.py", "benchmarks/locomo_split.json",
    "benchmarks/experiments/round2-default-recall-performance-plan.json",
    "tests/fixtures/mcp-object-reference-baseline.json",
)


def decode(payload):
    """Independent specification decoder; never call the production encoder."""
    if payload.get("source_format") != "indexed-v1":
        raise ValueError("Unexpected reference version")
    sessions = payload["source_sessions"]
    if any(not isinstance(pair, list) or len(pair) != 2 for pair in sessions):
        raise ValueError("Malformed session table")
    if len({tuple(pair) for pair in sessions}) != len(sessions):
        raise ValueError("Session table contains duplicate identities")
    results = []
    for hit in payload["results"]:
        refs = []
        for entry in hit["source_refs"]:
            if (not isinstance(entry, list) or len(entry) not in (2, 3)
                    or type(entry[0]) is not int or not 0 <= entry[0] < len(sessions)):
                raise ValueError("Malformed indexed reference")
            extra = entry[2] if len(entry) == 3 else {}
            if not isinstance(extra, dict) or REFERENCE_KEYS.intersection(extra):
                raise ValueError("Extra fields replace the source identity")
            project, session = sessions[entry[0]]
            refs.append({"project": project, "session_id": session,
                         "turn_index": entry[1], **extra})
        results.append({**hit, "source_refs": refs})
    return {**{k: v for k, v in payload.items()
               if k not in ("source_sessions", "source_format")}, "results": results}


def source_identity(path, binding):
    package = path.resolve() / "memory_book"
    provenance = checkout_provenance(package)
    actual_hash = engine_source_hash(package)
    if (not provenance["commit_identifies_source"]
            or provenance["git_commit"] != binding["runtime_commit"]
            or actual_hash != binding["runtime_source_sha256"]):
        raise ValueError("Runtime is not the exact pre-registered integrated source")
    return {"sha256": actual_hash, "provenance": provenance}


def archive_reference_audit(book, recall_payload):
    """Check every stored reference, including pages never returned by recall."""
    original, restored, count = [], [], 0
    for row in book.db.execute("SELECT id,content,source_refs FROM pages ORDER BY id"):
        refs = json.loads(row["source_refs"])
        native = {"context": row["content"], "results": [{"id": row["id"],
            "source_refs": refs, "excerpt_spans": [[0, len(row["content"])]], "truncated": False}]}
        objects = recall_payload(native, details=True)
        encoded = recall_payload(native, details=True, source_format="indexed")
        decoded = decode(encoded)
        if decoded != objects or objects["results"][0]["source_refs"] != refs:
            raise ValueError("An archived source field failed the complete-value round trip")
        original.append([row["id"], refs])
        restored.append([row["id"], decoded["results"][0]["source_refs"]])
        count += len(refs)
    return {"passed": True, "pages": len(original), "references": count,
            "original_sha256": digest(original), "decoded_sha256": digest(restored)}


async def measure_mcp(args, data, database, work, encodings, reference, report):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from memory_book.mcp_server import INDEXED_REFERENCE_INSTRUCTIONS, _json

    fixture = json.loads(FIXTURE_PATH.read_text())
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(database), "mcp",
              *(["--source-format", "indexed"] if args.format == "indexed" else [])],
        env={**os.environ, "PYTHONPATH": str(args.runtime_src.resolve()),
             "MEMORY_BOOK_HOME": str(work / "isolated-home"), "MEMORY_BOOK_DB": str(database),
             "PYTHONDONTWRITEBYTECODE": "1"})
    def counts(values):
        return {name: {key: len(encoding.encode(value, disallowed_special=()))
                       for key, value in values.items()} for name, encoding in encodings.items()}
    with sqlite3.connect(database) as cache:
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        started = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                report["startup_to_initialize_ms"] = (time.perf_counter_ns() - started) / 1e6
                tools = await client.list_tools()
                schema = tools.model_dump_json(exclude_none=True)
                instructions = initialized.instructions or ""
                expected_instructions = fixture["instructions"] + (
                    INDEXED_REFERENCE_INSTRUCTIONS if args.format == "indexed" else "")
                if schema != fixture["schema"] or sha(schema.encode()) != reference["schema_sha256"]:
                    raise ValueError("Tool schemas changed from the frozen actual SDK reference")
                if instructions != expected_instructions:
                    raise ValueError("Initialization instructions differ from the selected frozen format")
                report["metadata"] = {"schema": schema, "instructions": instructions,
                    "schema_sha256": sha(schema.encode()), "instructions_sha256": sha(instructions.encode()),
                    "tokens": counts({"tool_schema": schema, "instructions": instructions})}
                for budget in BUDGETS:
                    for details in DETAILS:
                        rows = []
                        for case in cases_for(data, args.round, budget):
                            arguments = {"query": case.query, "project": case.project,
                                         "budget_chars": budget, "limit": 5}
                            if details:
                                arguments["details"] = True
                            argument_json = _json(arguments)
                            # This committed clear is outside the measured interval.
                            # The server's usual cache lookup and write remain inside.
                            cache.execute("DELETE FROM recall_cache")
                            cache.commit()
                            if cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] != 0:
                                raise ValueError("Result cache was not empty before the timed call")
                            started = time.perf_counter_ns()
                            response = await client.call_tool("recall_memory", arguments)
                            elapsed = (time.perf_counter_ns() - started) / 1e6
                            if (response.isError or response.structuredContent is not None
                                    or len(response.content) != 1 or response.content[0].type != "text"):
                                raise ValueError("Unexpected actual MCP response shape")
                            payload = response.content[0].text
                            envelope = response.model_dump_json(exclude_none=True)
                            body = json.loads(payload)
                            decoded = decode(body) if args.format == "indexed" else body
                            if args.format == "objects" and any(
                                    key in body for key in ("source_format", "source_sessions")):
                                raise ValueError("Default payload unexpectedly contains an indexed table")
                            if (len(decoded["context"]) > budget or decoded.get("cache_hit") is True
                                    or (details and decoded.get("cache_hit") is not False)):
                                raise ValueError("Budget or no-result-cache contract failed")
                            matched = None
                            if not details:
                                previous = reference["cohorts"][args.cohort][str(budget)][case.id]
                                matched = sha(_json(decoded).encode()) == previous["payload_sha256"]
                                if args.format == "objects":
                                    matched = matched and sha(envelope.encode()) == previous["envelope_sha256"]
                                if not matched:
                                    raise ValueError("Default compact content differs from prior actual SDK bytes")
                            # Cost counts retain every returned byte, including the
                            # existing latency diagnostic in detailed mode. Only the
                            # full-value equivalence hash excludes that diagnostic.
                            stable = {k: v for k, v in decoded.items() if k != "latency_ms"}
                            rows.append({"query_id": case.id, "wall_ms": elapsed,
                                "payload_sha256": sha(payload.encode()), "envelope_sha256": sha(envelope.encode()),
                                "decoded_value_sha256": digest(stable), "context_sha256": sha(decoded["context"].encode()),
                                "context_chars": len(decoded["context"]), "response_utf8_bytes": len(payload.encode()),
                                "result_count": len(decoded["results"]),
                                "source_refs": sum(len(hit["source_refs"]) for hit in decoded["results"]),
                                "arguments_sha256": sha(argument_json.encode()), "cache_verified_empty": True,
                                "prior_compact_matched": matched,
                                "tokens": counts({"context": decoded["context"], "response_text": payload,
                                                  "response_envelope_json": envelope, "arguments": argument_json})})
                        report["configurations"].append({"budget_chars": budget, "details": details,
                            "rows": rows, "latency": latency_summary([row["wall_ms"] for row in rows])})
                        print(json.dumps({"cohort": args.cohort, "round": args.round, "format": args.format,
                            "budget_chars": budget, "details": details, "calls": len(rows)}), file=sys.stderr, flush=True)
                report["server_memory_after_calls"] = server_rss()
                report["storage_after_calls_live"] = storage(cache, database)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        report["indexed_content_after_calls"] = indexed_content(cache)


def worker(args):
    sys.path.insert(0, str(args.runtime_src.resolve()))
    from memory_book import MemoryBook
    from memory_book.mcp_server import recall_payload
    import memory_book
    import tiktoken

    if Path(memory_book.__file__).resolve().parent != (args.runtime_src / "memory_book").resolve():
        raise ValueError("Worker imported another runtime")
    binding = json.loads(BINDING_PATH.read_text())
    source = source_identity(args.runtime_src, binding)
    data = dataset(args.cohort, args.locomo_path)
    reference = json.loads(args.reference_compact.read_text())
    report = {"format": args.format, "cohort": args.cohort, "round": args.round,
              "source": source, "dataset": data.description(), "configurations": []}
    with tempfile.TemporaryDirectory(prefix="indexed-references-worker-") as temporary:
        work = Path(temporary)
        database = work / "memory.db"
        with MemoryBook(database, cache_size=0) as book:
            for session in data.sessions:
                book.ingest(session)
            report["indexed_content"] = indexed_content(book.db)
            if report["indexed_content"] != reference["indexes"][args.cohort]:
                raise ValueError("Indexed source content differs from the audited original corpus")
            report["archive_references"] = archive_reference_audit(book, recall_payload)
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            report["storage_after_ingest_checkpoint"] = storage(book.db, database)
        encodings = {name: tiktoken.get_encoding(name) for name in ENCODINGS}
        asyncio.run(measure_mcp(args, data, database, work, encodings, reference, report))
    report["source_sha256_after"] = engine_source_hash(args.runtime_src / "memory_book")
    return report


def strict_validation(report):
    """Reject incomplete axes, mismatched source/payloads and fabricated summaries."""
    issues, stable, common = [], {}, {}
    workers = report["workers"]
    binding = json.loads(BINDING_PATH.read_text())
    fixture = json.loads(FIXTURE_PATH.read_text())
    expected_workers = {(c, r, f) for c in COHORTS for r in range(ROUNDS) for f in FORMATS}
    actual = [(w["cohort"], w["round"], w["format"]) for w in workers]
    if len(actual) != len(set(actual)) or set(actual) != expected_workers:
        issues.append("missing_or_duplicate_worker")
    expected_order = [(c, r, f) for r in range(ROUNDS) for c in COHORTS
                      for f in (FORMATS if r % 2 == 0 else tuple(reversed(FORMATS)))]
    if actual != expected_order:
        issues.append("registered_worker_order")
    if (report["plan"] != json.loads(PLAN_PATH.read_text())
            or report["plan_sha256"] != sha(PLAN_PATH.read_bytes())
            or report["binding"] != binding or report["binding_sha256"] != sha(BINDING_PATH.read_bytes())):
        issues.append("registration_or_binding_changed")
    if (report["reference_report_sha256"] != binding["reference_report_sha256"]
            or set(report["cohorts"]) != set(COHORTS)):
        issues.append("reference_or_cohort_axis")
    for cohort in COHORTS:
        manifest = report["cohorts"].get(cohort, {})
        expected = COHORT_IDENTITIES[cohort]
        if (manifest.get("sha256") != expected["sha256"] or manifest.get("queries") != expected["queries"]
                or len(manifest.get("query_ids", [])) != expected["queries"]
                or len(set(manifest.get("query_ids", []))) != expected["queries"]
                or sorted(manifest.get("query_ids_original_order", [])) != manifest.get("query_ids")):
            issues.append(cohort + ":manifest")
    expected_configs = {(b, d) for b in BUDGETS for d in DETAILS}
    for w in workers:
        name, mode = w["cohort"], w["format"]
        identity = f"{name}/{w['round']}/{mode}"
        manifest = report["cohorts"][name]
        source = w["source"]
        if (source["sha256"] != binding["runtime_source_sha256"]
                or w["source_sha256_after"] != binding["runtime_source_sha256"]
                or source["provenance"]["git_commit"] != binding["runtime_commit"]
                or not source["provenance"]["commit_identifies_source"]):
            issues.append(identity + ":source")
        if w["dataset"]["sha256"] != manifest["sha256"] or w["dataset"]["queries"] != manifest["queries"]:
            issues.append(identity + ":dataset")
        archive = w["archive_references"]
        if (not archive["passed"] or archive["pages"] != w["indexed_content"]["pages"]["rows"]
                or archive["original_sha256"] != archive["decoded_sha256"] or archive["references"] <= 0):
            issues.append(identity + ":archive_references")
        for field in ("archive_references", "indexed_content"):
            key = (name, field)
            if key in common and common[key] != w[field]:
                issues.append(identity + ":" + field)
            common.setdefault(key, w[field])
        if w["indexed_content"] != w["indexed_content_after_calls"]:
            issues.append(identity + ":index_mutated")
        if w["indexed_content"] != report["reference_indexes"][name]:
            issues.append(identity + ":prior_index")
        metadata = w["metadata"]
        if (metadata["schema_sha256"] != report["reference_schema_sha256"]
                or metadata["schema"] != fixture["schema"]
                or sha(metadata["schema"].encode()) != metadata["schema_sha256"]
                or sha(metadata["instructions"].encode()) != metadata["instructions_sha256"]):
            issues.append(identity + ":metadata_hash")
        if ((mode == "objects" and metadata["instructions"] != fixture["instructions"])
                or (mode == "indexed" and metadata["instructions_sha256"] != INDEXED_INSTRUCTIONS_SHA256)):
            issues.append(identity + ":registered_instructions")
        expected_metadata = report["expected_metadata"][mode]
        if metadata != expected_metadata:
            issues.append(identity + ":format_metadata")
        configs = [(c["budget_chars"], c["details"]) for c in w["configurations"]]
        if len(configs) != len(set(configs)) or set(configs) != expected_configs:
            issues.append(identity + ":configuration_matrix")
        for c in w["configurations"]:
            ids = [row["query_id"] for row in c["rows"]]
            order = list(manifest["query_ids_original_order"])
            random.Random(61 + 1009 * w["round"] + c["budget_chars"]).shuffle(order)
            if len(ids) != len(set(ids)) or sorted(ids) != manifest["query_ids"] or ids != order:
                issues.append(identity + ":query_ids_or_order")
            if c["latency"] != latency_summary([row["wall_ms"] for row in c["rows"]]):
                issues.append(identity + ":latency_summary")
            for row in c["rows"]:
                if (not row["cache_verified_empty"] or row["context_chars"] > c["budget_chars"]
                        or not math.isfinite(row["wall_ms"]) or row["wall_ms"] < 0):
                    issues.append(identity + ":budget_cache_timing")
                if row["prior_compact_matched"] != (None if c["details"] else True):
                    issues.append(identity + ":prior_compact")
                if set(row["tokens"]) != set(ENCODINGS) or any(
                        set(v) != {"context", "arguments", "response_text", "response_envelope_json"}
                        or any(type(n) is not int or n < 0 for n in v.values()) for v in row["tokens"].values()):
                    issues.append(identity + ":token_axes")
                key = (name, c["budget_chars"], c["details"], row["query_id"])
                value = {k: row[k] for k in ("decoded_value_sha256", "context_sha256", "context_chars",
                    "result_count", "source_refs", "arguments_sha256")}
                value["tokens"] = {e: {k: row["tokens"][e][k] for k in ("context", "arguments")} for e in ENCODINGS}
                if key in stable and stable[key] != value:
                    issues.append(identity + ":complete_payload_or_arguments:" + row["query_id"])
                stable.setdefault(key, value)
    if report.get("error") or not report.get("evaluator_unchanged"):
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(expected_workers), "configurations": len(COHORTS) * len(expected_configs),
            "unique_payload_pairs": sum(c["queries"] for c in report["cohorts"].values()) * len(expected_configs),
            "timed_calls": sum(len(c["rows"]) for w in workers for c in w["configurations"]),
            "unique_archive_references": sum(common[(name, "archive_references")]["references"]
                                             for name in COHORTS if (name, "archive_references") in common)}


def comparisons(report):
    """Pool every round, retain paired differences and all positive/negative costs."""
    result = []
    for cohort in COHORTS:  # Registered order, independent of sorted JSON dictionaries.
        for budget in BUDGETS:
            for details in DETAILS:
                selected = [w for w in report["workers"] if w["cohort"] == cohort]
                by_mode, metadata = {}, {}
                for mode in FORMATS:
                    by_mode[mode] = {(w["round"], r["query_id"]): r for w in selected if w["format"] == mode
                        for c in w["configurations"] if (c["budget_chars"], c["details"]) == (budget, details)
                        for r in c["rows"]}
                    found = next((w["metadata"] for w in selected if w["format"] == mode), None)
                    if found is not None:
                        metadata[mode] = found
                if not all(by_mode.values()) or set(by_mode["objects"]) != set(by_mode["indexed"]):
                    continue  # Checkpoint summaries remain explicitly incomplete.
                keys = sorted(by_mode["objects"])
                modes, costs = {}, {}
                for mode in FORMATS:
                    rows = [by_mode[mode][key] for key in keys]
                    modes[mode] = {"latency": latency_summary([r["wall_ms"] for r in rows]),
                        "response_utf8_bytes": numeric([r["response_utf8_bytes"] for r in rows]),
                        "source_refs": numeric([r["source_refs"] for r in rows]),
                        "result_count": numeric([r["result_count"] for r in rows])}
                for encoding in ENCODINGS:
                    samples = {mode: [] for mode in FORMATS}
                    for mode in FORMATS:
                        fixed = metadata[mode]["tokens"][encoding]
                        for key in keys:
                            row = by_mode[mode][key]["tokens"][encoding]
                            samples[mode].append({**row, **fixed,
                                "first_call_text": row["response_text"] + row["arguments"] + sum(fixed.values()),
                                "first_call_envelope": row["response_envelope_json"] + row["arguments"] + sum(fixed.values()),
                                "later_call_text": row["response_text"] + row["arguments"],
                                "later_call_envelope": row["response_envelope_json"] + row["arguments"]})
                    savings = {field: [old[field] - new[field] for old, new in zip(samples["objects"], samples["indexed"])]
                        for field in ("response_text", "response_envelope_json", "first_call_text", "first_call_envelope",
                                      "later_call_text", "later_call_envelope")}
                    costs[encoding] = {mode: {field: numeric([r[field] for r in rows]) for field in rows[0]}
                                       for mode, rows in samples.items()}
                    costs[encoding]["savings"] = {field: numeric(values) for field, values in savings.items()}
                    costs[encoding]["outcomes"] = {field: {"saves_tokens": sum(v > 0 for v in values),
                        "equal_tokens": sum(v == 0 for v in values), "adds_tokens": sum(v < 0 for v in values)}
                        for field, values in savings.items()}
                rounds = [{"round": repetition, **{mode: latency_summary([
                    by_mode[mode][key]["wall_ms"] for key in keys if key[0] == repetition]) for mode in FORMATS}}
                    for repetition in range(ROUNDS)]
                result.append({"cohort": cohort, "budget_chars": budget, "details": details,
                    "paired_samples": len(keys), **modes, "costs": costs, "rounds": rounds,
                    "indexed_latency_change_percent": {metric: 100 * (modes["indexed"]["latency"][metric]
                        - modes["objects"]["latency"][metric]) / modes["objects"]["latency"][metric]
                        for metric in ("mean_ms", "p50_ms", "p95_ms")},
                    "paired_latency_delta_ms": numeric([by_mode["indexed"][key]["wall_ms"]
                                                        - by_mode["objects"][key]["wall_ms"] for key in keys])})
    return result


def summary_value(report, raw, compressed):
    result = {k: v for k, v in report.items() if k not in ("workers", "cohorts")}
    result["cohorts"] = {name: {k: v for k, v in value.items() if not k.startswith("query_ids")}
                         for name, value in report["cohorts"].items()}
    result["workers"] = [{k: v for k, v in w.items() if k != "configurations"} for w in report["workers"]]
    result["full_report_sha256"] = sha(raw)
    result["compressed_report_sha256"] = sha(compressed)
    return result


def save_report(path, report):
    report["validation"] = strict_validation(report)
    report["comparisons"] = comparisons(report)
    raw = atomic_json(path, report, compressed=True)
    atomic_json(path.with_name(path.name.removesuffix(".json.gz") + ".summary.json"),
                summary_value(report, raw, path.read_bytes()))


def audit(path):
    """Verify saved original bytes, complete matrix, metadata counts and every cost cell."""
    import tiktoken
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    actual = json.loads(path.with_name(path.name.removesuffix(".json.gz") + ".summary.json").read_text())
    if report["validation"] != strict_validation(report) or not report["validation"]["passed"]:
        raise ValueError("Saved report did not pass the full strict gate")
    if report["comparisons"] != comparisons(report):
        raise ValueError("Saved costs or latency summaries differ from all original rows")
    for metadata in report["expected_metadata"].values():
        for name in ENCODINGS:
            encoding = tiktoken.get_encoding(name)
            counted = {key: len(encoding.encode(metadata[field], disallowed_special=()))
                       for key, field in (("tool_schema", "schema"), ("instructions", "instructions"))}
            if counted != metadata["tokens"][name]:
                raise ValueError("Actual initialization metadata costs did not reproduce")
    if actual != summary_value(report, raw, compressed):
        raise ValueError("Summary, gzip or decompressed original bytes changed")
    print(json.dumps({"audit": "passed", "full_report_sha256": sha(raw), "validation": report["validation"]}))


def compact_reference(path, binding):
    raw = gzip.decompress(path.read_bytes())
    source = json.loads(raw)
    if sha(raw) != binding["reference_report_sha256"] or not source["validation"]["passed"]:
        raise ValueError("Reference is not the previously audited actual SDK report")
    workers = [w for w in source["workers"] if w["label"] == "candidate" and w["round"] == 0]
    return {"schema_sha256": workers[0]["mcp_tool_schema_sha256"],
            "indexes": {w["cohort"]: w["indexed_content"] for w in workers},
            "cohorts": {w["cohort"]: {str(c["budget_chars"]): {r["query_id"]: {
                k: r[k] for k in ("payload_sha256", "envelope_sha256")} for r in c["rows"]}
                for c in w["configurations"] if c["surface"] == "mcp_stdio"} for w in workers}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--reference-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--format", choices=FORMATS, help=argparse.SUPPRESS)
    parser.add_argument("--cohort", choices=COHORTS, help=argparse.SUPPRESS)
    parser.add_argument("--round", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--reference-compact", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.audit:
        audit(args.audit)
        return
    if not all((args.runtime_src, args.locomo_path, args.output)):
        parser.error("Require runtime-src, locomo-path and output")
    if args.output.exists() or not args.output.name.endswith(".json.gz"):
        parser.error("Select a new run-specific .json.gz output; preserve existing results")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, version in (("mcp", "1.30.0"), ("tiktoken", "0.12.0"), ("pydantic", "2.14.3")):
        if importlib.metadata.version(name) != version:
            raise ValueError("Use the registered SDK and tokenizer dependencies")
    if args.format:
        if args.cohort is None or args.round not in range(ROUNDS) or not args.reference_compact:
            parser.error("Worker requires a cohort, registered round and compact reference")
        atomic_json(args.output, worker(args), compressed=True)
        return
    if not args.reference_report:
        parser.error("Require the audited original reference report")
    plan, binding = json.loads(PLAN_PATH.read_text()), json.loads(BINDING_PATH.read_text())
    source = source_identity(args.runtime_src, binding)
    reference = compact_reference(args.reference_report, binding)
    cohorts = {}
    for name in COHORTS:
        data = dataset(name, args.locomo_path)
        ids = [q.id for q in data.queries]
        cohorts[name] = {"sha256": data.fingerprint, "queries": len(ids),
                         "query_ids": sorted(ids), "query_ids_original_order": ids}
    evaluator = sha(Path(__file__).read_bytes())
    dependencies = {name: sha((ROOT / name).read_bytes()) for name in DEPENDENCIES}
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Frozen operator mode on old regression corpora; complete-value reversibility and actual-SDK costs/latency. No answers, quality retuning or new blinded data.",
        "plan": plan, "plan_sha256": sha(PLAN_PATH.read_bytes()),
        "binding": binding, "binding_sha256": sha(BINDING_PATH.read_bytes()), "source": source,
        "evaluator_sha256": evaluator, "evaluator_dependency_sha256": dependencies, "evaluator_unchanged": False,
        "reference_report_sha256": binding["reference_report_sha256"],
        "reference_schema_sha256": reference["schema_sha256"], "reference_indexes": reference["indexes"],
        "cohorts": cohorts, "workers": [], "expected_metadata": {}, "error": None,
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
            **{name: importlib.metadata.version(name) for name in ("mcp", "tiktoken", "pydantic")}},
        "metric_boundaries": {
            "latency": "Wall time of actual official-SDK call_tool; startup/ingestion/token counts/hash/validation/cache clear excluded. Every call begins with an empty result cache; normal server lookup/write included. All four paired rounds on one host, warm OS/SQLite caches.",
            "first_call_cost": "One complete list_tools JSON + initialize.instructions + compact tool arguments JSON + actual response text OR SDK result envelope. Reference-tokenizer counts; no provider prompt wrapping/billing claim.",
            "later_call_cost": "Arguments + response, assuming initialization metadata is reused. No source_format argument exists. If a client resends metadata every call, use first_call totals instead.",
            "detailed_cost": "Every actual returned diagnostic byte is counted, including latency_ms; only that diagnostic is excluded from complete-value equality hashes across independent calls.",
            "memory": "Linux live MCP child VmRSS/VmHWM after calls; not whole-host peak allocation. Storage/index data are consistency checks, not separate ingestion speed claims.",
            "all_source_references": "Every original page source_refs is independently decoded outside timing, including pages never retrieved; all returned compact and detailed payloads are then paired across modes and rounds."}}
    try:
        with tempfile.TemporaryDirectory(prefix="indexed-references-controller-") as temporary:
            reference_path = Path(temporary) / "compact-reference.json"
            atomic_json(reference_path, reference)
            for repetition in range(ROUNDS):
                order = FORMATS if repetition % 2 == 0 else tuple(reversed(FORMATS))
                for cohort in COHORTS:
                    for mode in order:
                        output = Path(temporary) / f"{repetition}-{cohort}-{mode}.json.gz"
                        subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            "--runtime-src", str(args.runtime_src.resolve()), "--format", mode,
                            "--cohort", cohort, "--round", str(repetition), "--reference-compact", str(reference_path),
                            "--locomo-path", str(args.locomo_path.resolve()), "--output", str(output)],
                            check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
                        measured = json.loads(gzip.decompress(output.read_bytes()))
                        report["expected_metadata"].setdefault(mode, measured["metadata"])
                        report["workers"].append(measured)
                        save_report(args.output, report)
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    report["evaluator_unchanged"] = (evaluator == sha(Path(__file__).read_bytes())
        and dependencies == {name: sha((ROOT / name).read_bytes()) for name in DEPENDENCIES}
        and report["plan_sha256"] == sha(PLAN_PATH.read_bytes())
        and report["binding_sha256"] == sha(BINDING_PATH.read_bytes()))
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_report(args.output, report)
    print(json.dumps({"output": str(args.output), "validation": report["validation"]}))
    if not report["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
