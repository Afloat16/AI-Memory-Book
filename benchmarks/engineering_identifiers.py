"""Real CPython definition retrieval; no model answers or generated patches.

Prepare and bind never score. Run uses a fresh output directory, immutable
inputs, independent engine processes, and fsynced per-query event records.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
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
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/round7-identifiers-plan.json"
DATASET = ROOT / "benchmarks/fixtures/engineering_identifiers.json"
LOCK = ROOT / "benchmarks/competitors/billion-round2-lock.json"
SOURCE_LOCK = ROOT / "benchmarks/fixtures/engineering_identifiers_sources.json"
ARMS = ("v0.3.4", "round7-candidate", "raw-text-search", "billion-context-component", "no-memory")
ACRONYM = re.compile(r"[A-Z]{2,}[a-z]")
WORDS = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
PROJECT = "python/cpython@v3.12.0"
FILES = ("benchmarks/engineering_identifiers.py", "benchmarks/competitors/billion.py",
         "benchmarks/competitors/billion_bridge.mjs", "benchmarks/competitors/compile_billion.mjs",
         "benchmarks/competitors/download.py", "benchmarks/run.py", "benchmarks/data.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open("a", encoding="utf8") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def split_name(value):
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")


def build_dataset(sources, plan):
    """Deterministic selection from upstream AST, independent of retrieval."""
    documents, queries, source_records = [], [], []
    for path in plan["upstream"]["paths"]:
        raw = sources[path]
        text = raw.decode("utf8")
        lines = text.splitlines(keepends=True)
        source_hash = sha(raw)
        source_records.append({"path": path, "sha256": source_hash, "bytes": len(raw),
            "git_blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})
        tree = ast.parse(text, filename=path)
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
                 or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0]
        for node in sorted(nodes, key=lambda n: (n.lineno, n.name)):
            definition = "".join(lines[node.lineno - 1:node.end_lineno])[:1800]
            identity = path + ":" + str(node.lineno)
            declaration = lines[node.lineno - 1].strip()
            documents.append({"id": identity, "project": PROJECT, "title": node.name,
                "text": definition, "created_at": "2000-01-01T00:00:00+00:00",
                "source": {"path": path, "commit": plan["upstream"]["commit"],
                    "file_sha256": source_hash, "start_line": node.lineno,
                    "definition_end_line": node.end_lineno, "snippet_chars": len(definition)},
                "declaration": declaration, "kind": type(node).__name__})
            if isinstance(node, ast.ClassDef) and ACRONYM.search(node.name):
                spaced = split_name(node.name)
                for variant, query in (("exact", node.name), ("spaced", spaced),
                        ("lowercase", spaced.lower()), ("question", f"Where is {spaced} defined?")):
                    queries.append({"id": identity + ":" + variant, "query": query,
                        "variant": variant, "project": PROJECT, "expected_id": identity,
                        "declaration": declaration})
    if not queries or len({d["id"] for d in documents}) != len(documents):
        raise ValueError("Missing queries or ambiguous source identities")
    return {"schema_version": 1, "protocol": plan["protocol"], "upstream": plan["upstream"],
        "plan_sha256": sha(PLAN.read_bytes()), "source_files": source_records,
        "license": sources[plan["upstream"]["license_path"]].decode("utf8"),
        "license_sha256": sha(sources[plan["upstream"]["license_path"]]),
        "disclosure": "Real source excerpts; automatically authored identifier queries; fixed artificial capture timestamp shared by all arms. No authentic user conversations, temporal claims, generated answers or patches.",
        "documents": documents, "queries": queries}


def prepare(cache):
    from benchmarks.competitors.download import fetch_bytes
    plan = json.loads(PLAN.read_bytes())
    cache.mkdir(parents=True, exist_ok=True)
    paths = [*plan["upstream"]["paths"], plan["upstream"]["license_path"]]
    def fetch(path):
        target = cache / path
        if not target.exists():
            raw = fetch_bytes(f"https://raw.githubusercontent.com/{plan['upstream']['repository']}/{plan['upstream']['commit']}/{path}", timeout=40)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
        return path, target.read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = dict(pool.map(fetch, paths))
    verify_source_bytes(sources, plan)
    dataset = build_dataset(sources, plan)
    write_json(DATASET, dataset, exclusive=True)
    return {"dataset": str(DATASET), "sha256": sha(DATASET.read_bytes()),
            "documents": len(dataset["documents"]), "queries": len(dataset["queries"])}


def verify_source_bytes(sources, plan):
    lock = json.loads(SOURCE_LOCK.read_bytes())
    if (lock["repository"] != plan["upstream"]["repository"] or
            lock["commit"] != plan["upstream"]["commit"] or lock["truncated"]):
        raise ValueError("Source lock belongs to another upstream")
    expected = {item["path"]: item for item in lock["files"]}
    if set(sources) != set(expected):
        raise ValueError("Missing or extra upstream source files")
    for path, raw in sources.items():
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if len(raw) != expected[path]["bytes"] or blob != expected[path]["git_blob_sha"]:
            raise ValueError("Source does not match upstream Git blob: " + path)


def audit_dataset(cache):
    plan = json.loads(PLAN.read_bytes())
    paths = [*plan["upstream"]["paths"], plan["upstream"]["license_path"]]
    sources = {path: (cache / path).read_bytes() for path in paths}
    verify_source_bytes(sources, plan)
    expected = build_dataset(sources, plan)
    if expected != json.loads(DATASET.read_bytes()):
        raise ValueError("Dataset differs from complete registered selection over verified original source")
    return {"verified_files": len(sources), "documents": len(expected["documents"]),
            "queries": len(expected["queries"]), "source_lock_sha256": sha(SOURCE_LOCK.read_bytes())}


def runtime_hash(source):
    from benchmarks.run import engine_source_hash
    root = Path(source) / "memory_book"
    paths = list(root.rglob("*.py"))
    if not paths or root.is_symlink() or any(p.is_symlink() for p in paths):
        raise ValueError("Missing or symbolic runtime source")
    return engine_source_hash(root)


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in FILES}


def bind(baseline, candidate, source_cache, path):
    plan = json.loads(PLAN.read_bytes())
    data = json.loads(DATASET.read_bytes())
    if data["plan_sha256"] != sha(PLAN.read_bytes()):
        raise ValueError("Dataset belongs to a different plan")
    audited = audit_dataset(source_cache)
    sources = {"v0.3.4": {"path": str(baseline.resolve()), "sha256": runtime_hash(baseline)},
               "round7-candidate": {"path": str(candidate.resolve()), "sha256": runtime_hash(candidate)}}
    if sources["v0.3.4"]["sha256"] != plan["baseline"]["runtime_sha256"]:
        raise ValueError("Baseline differs from released v0.3.4")
    value = {"schema_version": 1, "protocol": plan["protocol"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha(PLAN.read_bytes()), "dataset_sha256": sha(DATASET.read_bytes()),
        "harness_sha256": file_hashes(), "competitor_lock_sha256": sha(LOCK.read_bytes()),
        "source_lock_sha256": audited["source_lock_sha256"], "source_cache": str(source_cache.resolve()),
        "sources": sources, "arms": list(ARMS), "documents": len(data["documents"]),
        "queries": len(data["queries"]), "python": platform.python_version(),
        "tiktoken": importlib.metadata.version("tiktoken"),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "quality_calls": len(data["queries"]) * len(ARMS) * plan["common_controls"]["repetitions"],
        "model_calls": 0}
    write_json(path, value, exclusive=True)
    return value


def verify(binding):
    if (sha(PLAN.read_bytes()) != binding["plan_sha256"] or
            sha(DATASET.read_bytes()) != binding["dataset_sha256"] or
            file_hashes() != binding["harness_sha256"] or
            sha(LOCK.read_bytes()) != binding["competitor_lock_sha256"] or
            sha(SOURCE_LOCK.read_bytes()) != binding["source_lock_sha256"]):
        raise ValueError("Frozen experiment inputs changed")
    for source in binding["sources"].values():
        if runtime_hash(source["path"]) != source["sha256"]:
            raise ValueError("Frozen runtime changed")
    if platform.python_version() != binding["python"] or importlib.metadata.version("tiktoken") != binding["tiktoken"]:
        raise ValueError("Runtime dependencies changed")
    if subprocess.check_output(["node", "--version"], text=True).strip() != binding["node"]:
        raise ValueError("Node runtime changed")
    audit_dataset(Path(binding["source_cache"]))


def raw_index(documents):
    """Prepare the baseline's independent index once, like other arms."""
    index = []
    for doc in documents:
        words = WORDS.findall(doc["text"])
        families = {frozenset(split_name(word).lower().split()) for word in words}
        fields = frozenset(part for family in families for part in family)
        index.append({"id": doc["id"], "project": doc["project"],
                      "compact_names": {word.replace("_", "").casefold() for word in words},
                      "fields": fields})
    return index


def raw_search(query, index, limit):
    """Competent independent spelling-aware text baseline, not product code."""
    parts = [part for part in split_name(query).lower().split() if part not in {"where", "is", "defined?"}]
    tokens, compact = set(parts), "".join(parts)
    ranked = []
    for doc in index:
        coverage = len(tokens & doc["fields"])
        full = compact in doc["compact_names"]
        if coverage or full:
            ranked.append((not full, coverage != len(tokens), -coverage, doc["id"]))
    return [item[-1] for item in sorted(ranked)[:limit]]


def pack(ids, documents, budget, encoder):
    blocks, retained = [], []
    for identity in ids:
        doc = documents[identity]
        block = f"[{identity}] {doc['project']} | {doc['source']['commit']}\n{doc['text']}"
        proposed = "\n\n".join([*blocks, block])
        if len(encoder.encode(proposed)) > budget:
            break
        blocks.append(block)
        retained.append(identity)
    context = "\n\n".join(blocks)
    return retained, context, len(encoder.encode(context))


def worker(binding_path, arm, repetition, state, cache):
    import tiktoken
    binding = json.loads(binding_path.read_bytes())
    verify(binding)
    plan = json.loads(PLAN.read_bytes())
    data = json.loads(DATASET.read_bytes())
    controls = plan["common_controls"]
    documents = {doc["id"]: doc for doc in data["documents"]}
    state.mkdir(parents=True, exist_ok=False)
    encoder = tiktoken.get_encoding(controls["tokenizer"])
    started = time.perf_counter_ns()
    engine, database, text_index = None, None, None
    metadata = {"arm": arm, "comparison_scope": "same-source retrieval component, not whole product or agent"}
    if arm in binding["sources"]:
        sys.path.insert(0, binding["sources"][arm]["path"])
        from memory_book import MemoryBook
        import memory_book
        expected_root = (Path(binding["sources"][arm]["path"]) / "memory_book").resolve()
        actual_root = Path(memory_book.__file__).resolve().parent
        actual_store = Path(sys.modules[MemoryBook.__module__].__file__).resolve()
        if actual_root != expected_root or actual_store != expected_root / "store.py":
            raise ValueError("Actually imported engine differs from frozen source")
        metadata["actual_import"] = {"package": str(actual_root), "store": str(actual_store)}
        database = state / "book.db"
        engine = MemoryBook(database, segmentation="turn", max_page_chars=4000, cache_size=0)
        for doc in documents.values():
            engine.ingest({"project": doc["project"], "session_id": doc["id"],
                "title": doc["title"], "created_at": doc["created_at"],
                "messages": [{"role": "assistant", "content": doc["text"]}]})
        metadata["runtime_sha256"] = runtime_hash(binding["sources"][arm]["path"])
    elif arm == "billion-context-component":
        from benchmarks.competitors.billion import BillionKernel
        engine = BillionKernel(documents.values(), cache, lock_path=LOCK)
        metadata["upstream"] = engine.metadata
    elif arm == "raw-text-search":
        text_index = raw_index(documents.values())
    elif arm != "no-memory":
        raise ValueError("Unregistered arm")
    metadata["initialize_and_ingest_ms"] = (time.perf_counter_ns() - started) / 1e6
    write_json(state / "initialization.json", metadata)
    cases = list(data["queries"])
    random.Random(controls["shuffle_seed"] + repetition).shuffle(cases)
    try:
        for case in cases:
            append(state / "events.jsonl", {"event": "started", "query_id": case["id"], "arm": arm, "repetition": repetition})
            begin = time.perf_counter_ns()
            error, native_ms, ids, payload = None, None, [], None
            try:
                if arm in binding["sources"]:
                    payload = engine.recall(case["query"], project=case["project"],
                        limit=controls["limit"], budget_chars=100000, use_cache=False)
                    for hit in payload["results"]:
                        refs = {ref["session_id"] for ref in hit["source_refs"]}
                        if len(refs) != 1:
                            raise ValueError("Ambiguous native source mapping")
                        ids.append(refs.pop())
                    native_ms = payload["latency_ms"]
                elif arm == "billion-context-component":
                    payload = engine.search(case["query"], case["project"], controls["limit"])
                    ids = [hit["ref"] for hit in payload["results"]]
                    native_ms = payload["search_ms"]
                elif arm == "raw-text-search":
                    ids = raw_search(case["query"], [d for d in text_index if d["project"] == case["project"]], controls["limit"])
                if len(set(ids)) != len(ids) or any(identity not in documents for identity in ids):
                    raise ValueError("Duplicate or unknown source ID")
                if any(documents[identity]["project"] != case["project"] for identity in ids):
                    raise ValueError("Project isolation violation")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                ids = []
            wall_ms = (time.perf_counter_ns() - begin) / 1e6
            scores = []
            for budget in controls["token_budgets"]:
                retained, context, count = pack(ids, documents, budget, encoder)
                rank = ids.index(case["expected_id"]) + 1 if case["expected_id"] in ids else None
                scores.append({"budget_tokens": budget, "retained_ids": retained,
                    "context": context, "context_tokens": count,
                    "hit": case["expected_id"] in retained and case["declaration"] in context,
                    "top1": bool(ids and ids[0] == case["expected_id"]),
                    "reciprocal_rank": 1 / rank if rank else 0,
                    "budget_violation": count > budget})
            append(state / "events.jsonl", {"event": "completed", "query_id": case["id"],
                "variant": case["variant"], "query": case["query"], "arm": arm, "repetition": repetition,
                "expected_id": case["expected_id"], "hit_ids": ids, "error": error,
                "lookup_wall_ms": wall_ms, "native_ms": native_ms, "scores": scores,
                "native_payload": payload})
    finally:
        if engine is not None:
            engine.close()
        if database is not None:
            metadata["database_bytes"] = database.stat().st_size
        write_json(state / "initialization.json", metadata)
    verify(binding)
    write_json(state / "completed.json", {"queries": len(cases), "arm": arm, "repetition": repetition})


def summarize(output, binding):
    rows, attempts, protocol_errors = [], json.loads((output / "attempts.json").read_bytes()), []
    controls = json.loads(PLAN.read_bytes())["common_controls"]
    cases = json.loads(DATASET.read_bytes())["queries"]
    case_map = {case["id"]: case for case in cases}
    expected_keys = {(arm, repetition, case["id"]) for arm in ARMS
                     for repetition in range(controls["repetitions"]) for case in cases}
    started, completed = set(), set()
    for stage in attempts:
        path = output / stage["state"] / "events.jsonl"
        if path.exists():
            for number, line in enumerate(path.read_bytes().splitlines(), 1):
                try:
                    event = json.loads(line)
                    key = (event["arm"], event["repetition"], event["query_id"])
                    if key not in expected_keys or key[:2] != (stage["arm"], stage["repetition"]):
                        raise ValueError("Event belongs to an unregistered matrix cell")
                    if event["event"] == "started":
                        if key in started:
                            raise ValueError("Duplicate started event")
                        started.add(key)
                    elif event["event"] == "completed":
                        if key not in started or key in completed:
                            raise ValueError("Unpaired or duplicate completed event")
                        case = case_map[key[2]]
                        if any(event[name] != case[name] for name in ("query", "variant", "expected_id")):
                            raise ValueError("Result identity differs from the frozen query")
                        if sorted(s["budget_tokens"] for s in event["scores"]) != controls["token_budgets"]:
                            raise ValueError("Result budget cells differ")
                        completed.add(key)
                        rows.append(event)
                    else:
                        raise ValueError("Unknown event type")
                except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                    protocol_errors.append({"state": stage["state"], "line": number,
                                            "error": f"{type(exc).__name__}: {exc}"})
    grouped = defaultdict(list)
    for row in rows:
        for score in row["scores"]:
            grouped[(row["arm"], row["variant"], score["budget_tokens"])].append((row, score))
    variant_counts = defaultdict(int)
    for case in cases:
        variant_counts[case["variant"]] += 1
    for arm in ARMS:
        for variant in variant_counts:
            for budget in controls["token_budgets"]:
                grouped.setdefault((arm, variant, budget), [])
    cells = []
    for (arm, variant, budget), values in sorted(grouped.items()):
        times = sorted(row["lookup_wall_ms"] for row, _ in values)
        expected = variant_counts[variant] * controls["repetitions"]
        cells.append({"arm": arm, "variant": variant, "budget_tokens": budget,
            "observations": len(values), "expected_observations": expected,
            "distinct_queries": len({r["query_id"] for r, _ in values}),
            "hit_rate": sum(s["hit"] for _, s in values) / expected,
            "top1_rate": sum(s["top1"] for _, s in values) / expected,
            "mrr": sum(s["reciprocal_rank"] for _, s in values) / expected,
            "mean_context_tokens": statistics.fmean(s["context_tokens"] for _, s in values) if values else None,
            "mean_lookup_ms": statistics.fmean(times) if times else None,
            "p95_lookup_ms": times[min(len(times) - 1, int(.95 * len(times)))] if times else None,
            "errors": sum(r["error"] is not None for r, _ in values) + max(0, expected - len(values)),
            "budget_violations": sum(s["budget_violation"] for _, s in values)})
    complete = (started == completed == expected_keys and not protocol_errors
                and len(rows) == binding["quality_calls"]
                and len(attempts) == len(ARMS) * controls["repetitions"]
                and all(stage["returncode"] == 0 for stage in attempts))
    def metric(arm, variants, budget=1024):
        chosen = [c for c in cells if c["arm"] == arm and c["variant"] in variants and c["budget_tokens"] == budget]
        return sum(c["hit_rate"] * c["expected_observations"] for c in chosen) / sum(c["expected_observations"] for c in chosen) if chosen else None
    before, after = (metric(a, ("spaced", "lowercase")) for a in ARMS[:2])
    exact_checks = [{"budget_tokens": budget, "before": metric(ARMS[0], ("exact",), budget),
                    "after": metric(ARMS[1], ("exact",), budget)} for budget in controls["token_budgets"]]
    numerical = bool(complete and after is not None and before is not None and after - before >= .10 - 1e-12
        and all(c["after"] >= c["before"] for c in exact_checks)
        and not any(c["errors"] or c["budget_violations"] for c in cells))
    report = {"protocol": binding["protocol"], "binding": binding,
        "completed": complete, "observed_calls": len(rows), "expected_calls": binding["quality_calls"],
        "generated_answers": 0, "generated_patches": 0, "cells": cells,
        "bounded_numerical_gate_passed": numerical,
        "exact_name_nonregression": exact_checks,
        "protocol_errors": protocol_errors,
        "missing_completed_cells": len(expected_keys - completed),
        "spaced_lowercase_1024_delta_percentage_points": None if before is None or after is None else 100 * (after - before),
        "release_approved": False,
        "limitations": ["Small single-repository identifier retrieval pilot; repetitions are correlated",
            "Whole-source shared packing measures a component, not native end-to-end model response",
            "Initialization, native lookup and IPC boundaries differ; no whole-product speed ranking",
            "No model answers, generated patches, longitudinal real-user or universal superiority result"],
        "attempts": attempts}
    write_json(output / "summary.json", report)
    return report


def run(binding_path, output, cache):
    binding = json.loads(binding_path.read_bytes())
    verify(binding)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "binding.json", binding)
    attempts = []
    repetitions = json.loads(PLAN.read_bytes())["common_controls"]["repetitions"]
    for repetition in range(repetitions):
        order = list(ARMS)
        if repetition % 2:
            order.reverse()
        elif repetition:
            order = order[repetition:] + order[:repetition]
        for arm in order:
            state_name = f"{repetition}-{arm}"
            attempt = {"arm": arm, "repetition": repetition, "state": state_name, "returncode": None}
            attempts.append(attempt)
            write_json(output / "attempts.json", attempts)
            command = [sys.executable, "-m", "benchmarks.engineering_identifiers", "worker",
                "--binding", str(binding_path.resolve()), "--arm", arm, "--repetition", str(repetition),
                "--state", str((output / state_name).resolve()), "--cache", str(cache.resolve())]
            with (output / (state_name + ".log")).open("wb") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=os.name != "nt")
                try:
                    attempt["returncode"] = process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    attempt["returncode"] = "timeout"
                finally:
                    if os.name != "nt":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            write_json(output / "attempts.json", attempts)
    verify(binding)
    return summarize(output, binding)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--cache", type=Path, required=True)
    p = sub.add_parser("bind")
    p.add_argument("--baseline-src", type=Path, required=True)
    p.add_argument("--candidate-src", type=Path, required=True)
    p.add_argument("--source-cache", type=Path, required=True)
    p.add_argument("--binding", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p = sub.add_parser("audit-data")
    p.add_argument("--cache", type=Path, required=True)
    p = sub.add_parser("worker")
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--arm", choices=ARMS, required=True)
    p.add_argument("--repetition", type=int, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.cache)
    elif args.command == "bind":
        result = bind(args.baseline_src, args.candidate_src, args.source_cache, args.binding)
    elif args.command == "audit-data":
        result = audit_dataset(args.cache)
    elif args.command == "worker":
        worker(args.binding, args.arm, args.repetition, args.state, args.cache)
        return
    else:
        result = run(args.binding, args.output, args.cache)
        result = {key: result[key] for key in ("completed", "observed_calls", "bounded_numerical_gate_passed", "spaced_lowercase_1024_delta_percentage_points")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
