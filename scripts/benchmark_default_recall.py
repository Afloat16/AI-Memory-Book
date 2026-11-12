"""Frozen-payload A/B experiment for default recall and real MCP stdio.

No query-result caching, answer generation, quality tuning, or new held-out
data is used. Each engine/cohort/round runs in a fresh sequential process.
Only IDs, hashes, counts and resource measurements are published.
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
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.run import engine_source_hash, percentile
from benchmarks.token_compare import checkout_provenance, latency_summary, load_dataset

PLAN = ROOT / "benchmarks/experiments/round2-default-recall-performance-plan.json"
BUDGETS = (2000, 4000, 8000)
SURFACES = ("native", "mcp_stdio")
ENCODINGS = ("cl100k_base", "o200k_base")
BASELINE = "cb7486b4937a3ecb7ccbf94a746c0bbbf44eb41f"
EVALUATOR_DEPENDENCIES = ("benchmarks/data.py", "benchmarks/public_data.py",
                        "benchmarks/run.py", "benchmarks/token_compare.py", "benchmarks/locomo_split.json")


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(dump(value).encode())


def numeric(values):
    return {"samples": len(values), "mean": statistics.fmean(values),
            "p50": percentile(values, .5), "p95": percentile(values, .95),
            "min": min(values), "max": max(values)} if values else None


def atomic_json(path, value, *, compressed=False):
    raw = (dump(value) + "\n").encode()
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
    temporary.replace(path)
    return raw


def dataset(name, locomo):
    if name == "synthetic61":
        result = load_dataset("synthetic", 61, "development", 8, None, 0)
    else:
        result = load_dataset("locomo", 61, "heldout", 8, str(locomo), 0)
    expected = next(c for c in json.loads(PLAN.read_text())["cohorts"] if c["name"] == name)
    if len(result.queries) != expected["queries"] or result.fingerprint != expected["sha256"]:
        raise ValueError("Old regression dataset does not match its frozen count and SHA-256")
    return result


def rss(pid="self"):
    status = Path(f"/proc/{pid}/status").read_text()
    values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
              for line in status.splitlines() if line.startswith(("VmRSS:", "VmHWM:"))}
    return {"rss_bytes": values["VmRSS"], "hwm_bytes": values["VmHWM"]}


def server_rss():
    # Inspect the live official-SDK child, not cumulative RUSAGE_CHILDREN,
    # which could also include earlier Git provenance subprocesses.
    children = set()
    for task in Path("/proc/self/task").iterdir():
        try:
            children.update((task / "children").read_text().split())
        except FileNotFoundError:
            # Threads may exit between listing and reading their /proc entry.
            continue
    servers = []
    for pid in children:
        try:
            if b"memory_book" in Path(f"/proc/{pid}/cmdline").read_bytes():
                servers.append(pid)
        except FileNotFoundError:
            continue
    if len(servers) != 1:
        return {"available": False, "reason": "Live MCP child not exposed by this procfs",
                "rss_bytes": None, "hwm_bytes": None}
    return {"available": True, **rss(servers[0])}


def storage(connection, path):
    return {"logical_db_bytes": connection.execute("PRAGMA page_count").fetchone()[0]
                                * connection.execute("PRAGMA page_size").fetchone()[0],
            "files_bytes": {name: (Path(str(path) + suffix).stat().st_size
                                    if Path(str(path) + suffix).exists() else 0)
                            for name, suffix in (("db", ""), ("wal", "-wal"), ("shm", "-shm"))}}


def indexed_content(connection):
    queries = {
        "pages": "SELECT * FROM pages ORDER BY rid",
        "sections": "SELECT * FROM sections ORDER BY id",
        "turns": "SELECT * FROM turns ORDER BY id",
        "chapters": "SELECT id,project_id,task_id,title,summary FROM chapters ORDER BY id",
        "sessions": "SELECT id,external_id,project_id,chapter_id,title,created_at,content_hash,raw_json,segmentation,message_count,turn_count,content_chars,settings_json FROM sessions ORDER BY id",
        "pages_fts": "SELECT rowid,title,question,body,directory FROM pages_fts ORDER BY rowid",
        "pages_stem_fts": "SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid",
    }
    result = {}
    for name, query in queries.items():
        rows = [list(row) for row in connection.execute(query)]
        result[name] = {"rows": len(rows), "sha256": digest(rows)}
    return result


def cases_for(data, repetition, budget):
    cases = list(data.queries)
    random.Random(61 + 1009 * repetition + budget).shuffle(cases)
    return cases


def payload_row(case, response, elapsed, payload, envelope=None, encodings=None):
    context = response["context"]
    row = {"query_id": case.id, "category": case.category, "wall_ms": elapsed,
           "payload_sha256": sha(payload.encode()), "context_sha256": sha(context.encode()),
           "envelope_sha256": sha(envelope.encode()) if envelope is not None else None,
           "response_utf8_bytes": len(payload.encode()), "context_chars": len(context),
           "result_count": len(response["results"]), "cache_verified_empty": True}
    if encodings:
        row["tokens"] = {name: {key: len(encoding.encode(value, disallowed_special=()))
                                for key, value in (("context", context), ("response_text", payload),
                                                   ("response_envelope_json", envelope))}
                         for name, encoding in encodings.items()}
    return row


async def mcp_measure(args, data, db_path, work, encodings, report):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    environment = {**os.environ, "PYTHONPATH": str(args.engine_src.resolve()),
                   "MEMORY_BOOK_HOME": str(work / "isolated-home"),
                   "MEMORY_BOOK_DB": str(db_path), "PYTHONDONTWRITEBYTECODE": "1"}
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "memory_book", "--db", str(db_path), "mcp"], env=environment)
    with sqlite3.connect(db_path) as cache:
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        started = time.perf_counter_ns()
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                report["mcp_startup_to_initialize_ms"] = (time.perf_counter_ns() - started) / 1e6
                tools = await client.list_tools()
                schema = tools.model_dump_json(exclude_none=True)
                report["mcp_tool_schema_sha256"] = sha(schema.encode())
                report["mcp_initialization_tokens"] = {name: {
                    "tool_schema": len(encoding.encode(schema, disallowed_special=())),
                    "instructions": len(encoding.encode(initialized.instructions or "", disallowed_special=()))}
                    for name, encoding in encodings.items()}
                for budget in BUDGETS:
                    rows = []
                    for case in cases_for(data, args.round, budget):
                        # A committed clear before EVERY timed call also covers
                        # repeated exact questions under different annotation IDs.
                        cache.execute("DELETE FROM recall_cache")
                        cache.commit()
                        if cache.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] != 0:
                            raise ValueError("MCP query-result cache was not empty")
                        started = time.perf_counter_ns()
                        response = await client.call_tool("recall_memory", {
                            "query": case.query, "project": case.project,
                            "budget_chars": budget, "limit": 5})
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        if response.isError:
                            raise ValueError("Actual MCP tool returned isError")
                        payload = "\n".join(part.text for part in response.content if part.type == "text")
                        body = json.loads(payload)
                        if len(body["context"]) > budget or body.get("cache_hit") is True:
                            raise ValueError("MCP character bound or empty-cache policy failed")
                        envelope = response.model_dump_json(exclude_none=True)
                        rows.append(payload_row(case, body, elapsed, payload, envelope, encodings))
                    report["configurations"].append({"surface": "mcp_stdio", "budget_chars": budget,
                        "rows": rows, "latency": latency_summary([r["wall_ms"] for r in rows])})
                    print(json.dumps({"engine": args.label, "cohort": args.cohort, "round": args.round,
                                      "surface": "mcp_stdio", "budget_chars": budget, "calls": len(rows)}),
                          file=sys.stderr, flush=True)
                report["mcp_server_memory_after_calls"] = server_rss()
                report["storage_after_mcp_live"] = storage(cache, db_path)
        cache.execute("DELETE FROM recall_cache")
        cache.commit()
        report["indexed_content_after_mcp"] = indexed_content(cache)


def worker(args):
    sys.path.insert(0, str(args.engine_src.resolve()))
    from memory_book import MemoryBook
    import memory_book

    source = Path(memory_book.__file__).parent
    if source.resolve() != (args.engine_src / "memory_book").resolve():
        raise ValueError("Worker imported another engine")
    before = engine_source_hash(source)
    provenance = checkout_provenance(source)
    if not provenance["commit_identifies_source"]:
        raise ValueError("Measured runtime must match its Git commit exactly")
    data = dataset(args.cohort, args.locomo_path)
    report = {"label": args.label, "cohort": args.cohort, "round": args.round,
              "source_provenance": provenance, "source_sha256_before": before,
              "dataset": data.description(), "configurations": []}
    with tempfile.TemporaryDirectory(prefix="default-recall-worker-") as temporary:
        work = Path(temporary)
        db_path = work / "memory.db"
        with MemoryBook(db_path, cache_size=0) as book:
            ingestion_rows = []
            started = time.perf_counter_ns()
            for session in data.sessions:
                ingestion_rows.append(book.ingest(session))
            report["fresh_ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
            report["fresh_ingestion_results_sha256"] = digest(ingestion_rows)
            report["native_memory_after_ingestion"] = rss()
            report["storage_after_ingestion_live"] = storage(book.db, db_path)
            replay_rows = []
            started = time.perf_counter_ns()
            for session in data.sessions:
                replay_rows.append(book.ingest(session))
            report["unchanged_reingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
            report["unchanged_reingestion_results_sha256"] = digest(replay_rows)
            report["all_replayed_sessions_skipped"] = all(row["skipped"] for row in replay_rows)
            report["indexed_content"] = indexed_content(book.db)
            for budget in BUDGETS:
                rows = []
                for case in cases_for(data, args.round, budget):
                    started = time.perf_counter_ns()
                    response = book.recall(case.query, project=case.project,
                                           budget_chars=budget, limit=5, use_cache=False)
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    if response["cache_hit"] or len(response["context"]) > budget:
                        raise ValueError("Native character bound or no-cache policy failed")
                    response.pop("latency_ms")  # The sole excluded complete-payload field.
                    rows.append(payload_row(case, response, elapsed, dump(response)))
                report["configurations"].append({"surface": "native", "budget_chars": budget,
                    "rows": rows, "latency": latency_summary([r["wall_ms"] for r in rows])})
            report["native_memory_after_calls"] = rss()
            report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
            book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            report["storage_after_native_checkpoint"] = storage(book.db, db_path)
        # Tokenizer and SDK imports are excluded from native process RSS.
        import tiktoken
        encodings = {name: tiktoken.get_encoding(name) for name in ENCODINGS}
        asyncio.run(mcp_measure(args, data, db_path, work, encodings, report))
    report["source_sha256_after"] = engine_source_hash(source)
    report["source_unchanged"] = before == report["source_sha256_after"]
    return report


def strict_validation(report):
    """Require the complete registered matrix, IDs, sources and payloads."""
    issues, canonical = [], {}
    plan, workers = report["plan"], report["workers"]
    expected_workers = {(c["name"], r, label) for c in plan["cohorts"]
                        for r in range(plan["measurement"]["rounds"]) for label in ("baseline", "candidate")}
    actual_workers = [(w["cohort"], w["round"], w["label"]) for w in workers]
    if len(actual_workers) != len(set(actual_workers)) or set(actual_workers) != expected_workers:
        issues.append("missing_or_duplicate_worker")
    expected_configs = {(s, b) for s in SURFACES for b in BUDGETS}
    for w in workers:
        name = w["cohort"]
        identity = f"{name}/{w['round']}/{w['label']}"
        manifest = report["cohorts"][name]
        source = report["sources"][w["label"]]
        if (w["source_sha256_before"] != source["sha256"] or not w["source_unchanged"]
                or w["source_sha256_after"] != source["sha256"]
                or not w["source_provenance"]["commit_identifies_source"]
                or w["source_provenance"]["git_commit"] != source["git_commit"]):
            issues.append(identity + ":source")
        if w["dataset"]["sha256"] != manifest["sha256"]:
            issues.append(identity + ":corpus")
        if not w["all_replayed_sessions_skipped"] or w["native_recall_cache_rows"] != 0:
            issues.append(identity + ":ingest_or_cache")
        for field in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256",
                      "mcp_tool_schema_sha256", "mcp_initialization_tokens"):
            key = (name, field)
            if key in canonical and canonical[key] != w[field]:
                issues.append(identity + ":" + field)
            canonical.setdefault(key, w[field])
        if w["indexed_content"] != w["indexed_content_after_mcp"]:
            issues.append(identity + ":index_mutated")
        configs = [(c["surface"], c["budget_chars"]) for c in w["configurations"]]
        if len(configs) != len(set(configs)) or set(configs) != expected_configs:
            issues.append(identity + ":matrix")
        for c in w["configurations"]:
            ids = [row["query_id"] for row in c["rows"]]
            if len(ids) != len(set(ids)) or sorted(ids) != manifest["query_ids"]:
                issues.append(identity + ":query_ids")
            expected_order = list(manifest["query_ids_original_order"])
            random.Random(61 + 1009 * w["round"] + c["budget_chars"]).shuffle(expected_order)
            if ids != expected_order:
                issues.append(identity + ":query_order")
            if c["latency"] != latency_summary([row["wall_ms"] for row in c["rows"]]):
                issues.append(identity + ":latency_summary")
            for row in c["rows"]:
                if not row["cache_verified_empty"] or row["context_chars"] > c["budget_chars"]:
                    issues.append(identity + ":cache_or_budget")
                if not math.isfinite(row["wall_ms"]) or row["wall_ms"] < 0:
                    issues.append(identity + ":invalid_timing")
                key = (name, c["surface"], c["budget_chars"], row["query_id"])
                stable = {k: v for k, v in row.items() if k != "wall_ms"}
                if key in canonical and canonical[key] != stable:
                    issues.append(identity + ":payload:" + row["query_id"])
                canonical.setdefault(key, stable)
    expected_scope = sorted(plan["runtime_files_allowed"])
    if sorted(report["changed_runtime_files"]) != expected_scope:
        issues.append("runtime_scope")
    if (report["sources"]["baseline"]["git_commit"] != plan["baseline_commit"]
            or report["sources"]["baseline"]["sha256"] != plan["baseline_source_sha256"]):
        issues.append("baseline_identity")
    if report.get("error") or not report.get("evaluator_unchanged"):
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(expected_workers), "unique_payload_pairs_per_surface": sum(
                len(c["query_ids"]) * len(BUDGETS) for c in report["cohorts"].values()),
            "timed_calls": sum(len(c["rows"]) for w in workers for c in w["configurations"])}


def comparisons(report):
    result = []
    for cohort in report["cohorts"]:
        for surface in SURFACES:
            for budget in BUDGETS:
                selected = [w for w in report["workers"] if w["cohort"] == cohort]
                engines, rounds = {}, []
                for label in ("baseline", "candidate"):
                    rows = [row for w in selected if w["label"] == label for c in w["configurations"]
                            if (c["surface"], c["budget_chars"]) == (surface, budget) for row in c["rows"]]
                    engines[label] = {"latency": latency_summary([r["wall_ms"] for r in rows]),
                        "response_utf8_bytes": numeric([r["response_utf8_bytes"] for r in rows]),
                        "context_chars": numeric([r["context_chars"] for r in rows]),
                        "tokens": {encoding: {key: numeric([r["tokens"][encoding][key] for r in rows])
                                              for key in ("context", "response_text", "response_envelope_json")}
                                   for encoding in ENCODINGS} if surface == "mcp_stdio" else None}
                for repetition in range(report["plan"]["measurement"]["rounds"]):
                    values = {w["label"]: c["latency"] for w in selected if w["round"] == repetition
                              for c in w["configurations"] if (c["surface"], c["budget_chars"]) == (surface, budget)}
                    rounds.append({"round": repetition, **values})
                change = {}
                for metric in ("mean_ms", "p50_ms", "p95_ms"):
                    old, new = (engines[label]["latency"][metric] for label in ("baseline", "candidate"))
                    change[metric] = 100 * (new - old) / old if old and new is not None else None
                result.append({"cohort": cohort, "surface": surface, "budget_chars": budget,
                               **engines, "candidate_change_percent": change, "rounds": rounds})
    return result


def save_report(path, report):
    report["validation"] = strict_validation(report)
    report["comparisons"] = comparisons(report)
    raw = atomic_json(path, report, compressed=True)
    summary = {k: v for k, v in report.items() if k not in ("workers", "cohorts")}
    summary["cohorts"] = {name: {k: v for k, v in c.items() if not k.startswith("query_ids")}
                          for name, c in report["cohorts"].items()}
    summary["workers"] = [{k: v for k, v in w.items() if k != "configurations"} for w in report["workers"]]
    summary["full_report_sha256"] = sha(raw)
    summary["compressed_report_sha256"] = sha(path.read_bytes())
    atomic_json(path.with_name(path.name.removesuffix(".json.gz") + ".summary.json"), summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path, default=ROOT / "src")
    parser.add_argument("--locomo-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--label", choices=("baseline", "candidate"), help=argparse.SUPPRESS)
    parser.add_argument("--cohort", choices=("synthetic61", "public1015"), help=argparse.SUPPRESS)
    parser.add_argument("--round", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing output; select a new run-specific path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.engine_src:
        atomic_json(args.output, worker(args), compressed=True)
        return
    if not args.baseline_src or not args.output.name.endswith(".json.gz"):
        parser.error("Require --baseline-src and a new .json.gz output")
    plan = json.loads(PLAN.read_text())
    if plan["measurement"]["rounds"] != 4 or plan["measurement"]["budget_chars"] != list(BUDGETS):
        raise ValueError("Registered measurement axes changed")
    sources = {}
    for label, source in (("baseline", args.baseline_src), ("candidate", args.candidate_src)):
        package = source.resolve() / "memory_book"
        provenance = checkout_provenance(package)
        if not provenance["commit_identifies_source"]:
            raise ValueError("Source is not an exact committed runtime")
        sources[label] = {"sha256": engine_source_hash(package), "git_commit": provenance["git_commit"],
                          "path": str(source.resolve())}
    changed = subprocess.check_output(["git", "diff", "--name-only", BASELINE, "HEAD", "--", "src"],
                                      cwd=args.candidate_src.resolve().parent, text=True).splitlines()
    cohorts = {}
    for c in plan["cohorts"]:
        data = dataset(c["name"], args.locomo_path)
        ids = [case.id for case in data.queries]
        cohorts[c["name"]] = {"sha256": data.fingerprint, "queries": len(ids),
                               "query_ids": sorted(ids), "query_ids_original_order": ids}
    evaluator = sha(Path(__file__).read_bytes())
    dependencies = {name: sha((ROOT / name).read_bytes()) for name in EVALUATOR_DEPENDENCIES}
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Old regression data, complete-payload equivalence and host-specific default API performance; no generated answers or new-domain quality evidence.",
        "plan": plan, "plan_sha256": sha(PLAN.read_bytes()), "evaluator_sha256": evaluator,
        "evaluator_dependency_sha256": dependencies,
        "evaluator_unchanged": False, "sources": sources, "changed_runtime_files": changed,
        "cohorts": cohorts, "workers": [], "error": None,
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
            "mcp": importlib.metadata.version("mcp"), "tiktoken": importlib.metadata.version("tiktoken")},
        "metric_boundaries": {"native": "Complete default MemoryBook.recall, cache_size=0/use_cache=False; only latency_ms omitted from payload hash. Bytes use canonical JSON, not a wire claim.",
            "mcp_stdio": "Actual SDK stdio compact recall; committed SQLite cache clear immediately before each timed call, clear excluded and normal server cache-write included. Exact returned text/envelope measured without deleting fields.",
            "memory": "Linux /proc VmRSS/VmHWM snapshots; native before tokenizer/SDK imports, live child after MCP calls; not system-wide allocation peaks.",
            "timing": "All four balanced-order rounds pooled; per-round statistics retained. Warm OS/SQLite caches, no cold-cache claim. Source loading/ingest/startup/hash/count/cache-clear excluded from recall timing."}}
    try:
        with tempfile.TemporaryDirectory(prefix="default-recall-controller-") as temporary:
            for repetition in range(4):
                order = ("baseline", "candidate") if repetition % 2 == 0 else ("candidate", "baseline")
                for cohort in cohorts:
                    for label in order:
                        output = Path(temporary) / f"{repetition}-{cohort}-{label}.json.gz"
                        subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            "--engine-src", sources[label]["path"], "--label", label,
                            "--cohort", cohort, "--round", str(repetition),
                            "--locomo-path", str(args.locomo_path.resolve()), "--output", str(output)],
                            check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
                        report["workers"].append(json.loads(gzip.decompress(output.read_bytes())))
                        save_report(args.output, report)
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    report["evaluator_unchanged"] = (evaluator == sha(Path(__file__).read_bytes())
        and report["plan_sha256"] == sha(PLAN.read_bytes())
        and dependencies == {name: sha((ROOT / name).read_bytes()) for name in EVALUATOR_DEPENDENCIES})
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_report(args.output, report)
    print(json.dumps({"output": str(args.output), "validation": report["validation"]}))
    if not report["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
