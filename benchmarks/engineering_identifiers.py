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
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/round7-identifiers-plan.json"
DATASET = ROOT / "benchmarks/fixtures/engineering_identifiers.json"
LOCK = ROOT / "benchmarks/competitors/billion-round2-lock.json"
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
    dataset = build_dataset(sources, plan)
    write_json(DATASET, dataset, exclusive=True)
    return {"dataset": str(DATASET), "sha256": sha(DATASET.read_bytes()),
            "documents": len(dataset["documents"]), "queries": len(dataset["queries"])}


def runtime_hash(source):
    from benchmarks.run import engine_source_hash
    return engine_source_hash(Path(source) / "memory_book")


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in FILES}


def bind(baseline, candidate, path):
    plan = json.loads(PLAN.read_bytes())
    data = json.loads(DATASET.read_bytes())
    if data["plan_sha256"] != sha(PLAN.read_bytes()):
        raise ValueError("Dataset belongs to a different plan")
    sources = {"v0.3.4": {"path": str(baseline.resolve()), "sha256": runtime_hash(baseline)},
               "round7-candidate": {"path": str(candidate.resolve()), "sha256": runtime_hash(candidate)}}
    if sources["v0.3.4"]["sha256"] != plan["baseline"]["runtime_sha256"]:
        raise ValueError("Baseline differs from released v0.3.4")
    value = {"schema_version": 1, "protocol": plan["protocol"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha(PLAN.read_bytes()), "dataset_sha256": sha(DATASET.read_bytes()),
        "harness_sha256": file_hashes(), "competitor_lock_sha256": sha(LOCK.read_bytes()),
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
            sha(LOCK.read_bytes()) != binding["competitor_lock_sha256"]):
        raise ValueError("Frozen experiment inputs changed")
    for source in binding["sources"].values():
        if runtime_hash(source["path"]) != source["sha256"]:
            raise ValueError("Frozen runtime changed")
    if platform.python_version() != binding["python"] or importlib.metadata.version("tiktoken") != binding["tiktoken"]:
        raise ValueError("Runtime dependencies changed")


def raw_index(documents):
    """Prepare the baseline's independent index once, like other arms."""
    index = []
    for doc in documents:
        words = WORDS.findall(doc["text"])
        families = {frozenset(split_name(word).lower().split()) for word in words}
        fields = frozenset(part for family in families for part in family)
        index.append({"id": doc["id"], "project": doc["project"],
                      "folded": doc["text"].casefold(), "families": families, "fields": fields})
    return index


def raw_search(query, index, limit):
    """Competent independent spelling-aware text baseline, not product code."""
    tokens = set(split_name(query).lower().split()) - {"where", "is", "defined?"}
    ranked = []
    for doc in index:
        coverage = len(tokens & doc["fields"])
        full = frozenset(tokens) in doc["families"]
        literal = query.casefold() in doc["folded"]
        if coverage or full or literal:
            ranked.append((not full, not literal, -coverage, doc["id"]))
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
    rows, attempts = [], json.loads((output / "attempts.json").read_bytes())
    for stage in attempts:
        path = output / stage["state"] / "events.jsonl"
        if path.exists():
            events = [json.loads(line) for line in path.read_text().splitlines()]
            rows.extend(event for event in events if event.get("event") == "completed")
    grouped = defaultdict(list)
    for row in rows:
        for score in row["scores"]:
            grouped[(row["arm"], row["variant"], score["budget_tokens"])].append((row, score))
    controls = json.loads(PLAN.read_bytes())["common_controls"]
    cases = json.loads(DATASET.read_bytes())["queries"]
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
    complete = len(rows) == binding["quality_calls"] and all(stage["returncode"] == 0 for stage in attempts)
    def metric(arm, variants):
        chosen = [c for c in cells if c["arm"] == arm and c["variant"] in variants and c["budget_tokens"] == 1024]
        return sum(c["hit_rate"] * c["expected_observations"] for c in chosen) / sum(c["expected_observations"] for c in chosen) if chosen else None
    before, after = (metric(a, ("spaced", "lowercase")) for a in ARMS[:2])
    exact_before, exact_after = (metric(a, ("exact",)) for a in ARMS[:2])
    numerical = bool(complete and after is not None and before is not None and after - before >= .10 - 1e-12
        and exact_after >= exact_before and not any(c["errors"] or c["budget_violations"] for c in cells))
    report = {"protocol": binding["protocol"], "binding": binding,
        "completed": complete, "observed_calls": len(rows), "expected_calls": binding["quality_calls"],
        "generated_answers": 0, "generated_patches": 0, "cells": cells,
        "bounded_numerical_gate_passed": numerical,
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
                try:
                    result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=300)
                    attempt["returncode"] = result.returncode
                except subprocess.TimeoutExpired:
                    attempt["returncode"] = "timeout"
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
    p.add_argument("--binding", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
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
        result = bind(args.baseline_src, args.candidate_src, args.binding)
    elif args.command == "worker":
        worker(args.binding, args.arm, args.repetition, args.state, args.cache)
        return
    else:
        result = run(args.binding, args.output, args.cache)
        result = {key: result[key] for key in ("completed", "observed_calls", "bounded_numerical_gate_passed", "spaced_lowercase_1024_delta_percentage_points")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
