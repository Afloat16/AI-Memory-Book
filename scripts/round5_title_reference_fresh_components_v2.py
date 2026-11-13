"""One frozen supplied-page comparison on the already selected T1 cohort.

There is no selector here. Registration and intents decode no selected source
content. Export/search workers require committed selection/data and a remotely
published, single-use intent. Import and invented tests execute no retrieval.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import random
import secrets
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_title_reference_fresh_data_v2 as d
from scripts import round5_title_reference_fresh_v2 as native
from scripts import round5_title_reference_eval_v2 as scoring
from scripts.round5_source_content_snapshot import source_content_snapshot, verify_content_snapshot
from scripts.benchmark_default_recall import indexed_content
from scripts.round4_comparison import component_costs
from benchmarks import round2_eval as reused
from benchmarks.component_eval import canonical_json, evidence_attainability, shared_response
from benchmarks.round2_resources import Resources, storage
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import source_snapshot
from benchmarks.token_compare import ENCODINGS, TokenCounter, latency_summary, pack_whole_blocks, summarize_rows

VERSION = "round5-t1-fresh512-comparators-2"
SCOPE = "benchmarks/experiments/round5-title-reference-fresh-components-v2-scope.json"
NEW_FILES = (SCOPE, "scripts/round5_title_reference_fresh_components_v2.py",
             "tests/test_round5_title_reference_fresh_components_v2.py")
ENGINES = ("final-default-component", "final-follow-titles-component", "claude-mem-fts",
           "billion-context", "ai-memory-hybrid")
WORKERS = ("export", *ENGINES)
CONFIGURATIONS = tuple({"index": i, "tokenizer": name, "budget_tokens": budget,
                        "budget_chars": 8000} for i, (name, budget) in enumerate(
                            itertools.product(ENCODINGS, (512, 1024, 2048))))
DEPENDENCIES = {"tiktoken": "0.12.0", "pyarrow": "26.0.1", "node": "v24.22.1", "bun": "1.3.13"}
require, read, save, raw, sha, digest, now = d.require, d.read, d.save, d.raw, d.sha, d.digest, d.now


def scope():
    value = read(ROOT / SCOPE)
    require(value["protocol"] == VERSION and value["dependencies"] == DEPENDENCIES
            and value["axes"]["top_k"] == 5 and value["axes"]["common_budget_chars"] == 8000
            and value["axes"]["tokenizers"] == list(ENCODINGS)
            and value["axes"]["token_budgets"] == [512, 1024, 2048]
            and value["schedule"]["worker_order"] == list(WORKERS)
            and value["schedule"]["total_search_calls"] == 7680
            and value["schedule"]["total_quality_rows"] == 15360,
            "Comparator scope axes or schedule changed")
    return value


def evaluator_files():
    names = set(scoring.registry()) | set(d.NEW_FILES) | set(NEW_FILES)
    names.add("scripts/round4_comparison.py")
    names.update(d.registered()["snapshot_repair"]["preserved_original_files_sha256"])
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "benchmarks/competitors").iterdir()
                 if p.suffix in {".py", ".mjs", ".ts", ".json"})
    return {name: sha(ROOT / name) for name in sorted(names)}


def asset_pins(cache, node):
    """Read prepared pinned assets only; never prepare, download or launch an engine."""
    from benchmarks.competitors.claude_mem import source_members, directory_fingerprint
    from benchmarks.competitors.billion import _verify
    cache, node = Path(cache).resolve(), Path(node).resolve()
    require(cache.is_dir() and node.is_file(), "Prepared comparator assets and explicit Node binary required")
    locks = {name: read(ROOT / path) for name, path in reused.UPSTREAM_LOCKS.items()}

    def checked(path, expected, size=None):
        require(path.is_file() and not path.is_symlink() and sha(path) == expected
                and (size is None or path.stat().st_size == size), "Pinned asset differs: " + str(path))
        return {"sha256": expected, "bytes": path.stat().st_size}

    cm = locks["claude-mem"]
    cm_root = cache / "claude-mem"
    cm_archive = cm_root / cm["source_archive"]["name"]
    cm_files = {"source_archive": checked(cm_archive, cm["source_archive"]["sha256"], cm["source_archive"]["bytes"]),
                "runtime_archive": checked(cm_root / cm["runtime"]["name"], cm["runtime"]["sha256"], cm["runtime"]["bytes"]),
                "runtime_binary": checked(cm_root / "bun", cm["runtime"]["binary_sha256"], cm["runtime"]["binary_bytes"])}
    members = source_members(cm_archive)
    cm_files.update(source_fingerprint=directory_fingerprint(cm_root / "verified-source", members),
                    verified_source_files=len(members))
    billion_files = {}
    for entry in locks["billion-context"]["files"]:
        body = (cache / "billion-context" / entry["path"]).read_bytes()
        _verify(body, entry)
        billion_files[entry["path"]] = entry["sha256"]
    ai, ai_root = locks["ai-memory"], cache / "ai-memory"
    ai_files = {
        "archive": checked(ai_root / f"ai-memory-linux-x86_64-{ai['version']}.tar.gz", ai["archive_sha256"], ai["archive_bytes"]),
        "binary": checked(ai_root / f"ai-memory-{ai['version']}", ai["binary_sha256"]),
        "model": {entry["name"]: checked(ai_root / "models" / ai["embedding_model"]["name"] / entry["name"],
                                         entry["sha256"], entry["bytes"])
                  for entry in ai["embedding_model"]["files"]}}
    version = subprocess.check_output([str(node), "--version"], text=True, timeout=20).strip()
    require(version == DEPENDENCIES["node"], "Use the frozen Node 24.22.1 runtime")
    return {"lock_sha256": {name: sha(ROOT / path) for name, path in reused.UPSTREAM_LOCKS.items()},
            "claude-mem": cm_files, "ai-memory": ai_files,
            "billion-context": {"files": len(billion_files), "manifest_sha256": digest(billion_files)},
            "node": {"path": str(node), "version": version, "sha256": sha(node), "bytes": node.stat().st_size},
            "generated_javascript": "Excluded as an asset: the unchanged adapter regenerates it from pinned TypeScript and the pinned Node/compiler before every engine setup."}


def register(args):
    plan, fresh = scope(), d.registered()
    require(args.source and args.selection and args.state and args.output and args.cache and args.node,
            "Registration needs final source, future selection/state/output and prepared assets")
    for path in (args.register, args.selection, args.state, args.output):
        require(not path.exists(), "Registration/selection/state/output must be fresh")
        d.relative(path)
    files = evaluator_files()
    for name in files:
        d.committed(ROOT / name)
    candidate = scoring.source(args.source)
    pins = asset_pins(args.cache, args.node)
    require({name: importlib.metadata.version(name) for name in ("tiktoken", "pyarrow")}
            == {name: DEPENDENCIES[name] for name in ("tiktoken", "pyarrow")}, "Reference dependencies changed")
    value = {"protocol": VERSION, "status": "frozen-before-selection", "created_at": now(),
        "scope": {"path": SCOPE, "sha256": sha(ROOT / SCOPE)}, "candidate_source": candidate,
        "exporter_source": plan["export"]["source"], "upstream_pins": fresh["comparators"]["pins"],
        "selection_manifest": d.relative(args.selection), "state": d.relative(args.state),
        "output": d.relative(args.output), "cache": d.relative(args.cache), "top_k": 5,
        "tokenizers": list(ENCODINGS), "token_budgets": [512, 1024, 2048],
        "configurations": list(CONFIGURATIONS), "evaluator_files": files,
        "dependencies": DEPENDENCIES, "native_boundaries": plan["native_boundaries"],
        "schedule": plan["schedule"], "asset_pins": pins, "host": d.host(),
        "fresh_content_rows_decoded": 0, "retrieval_calls_executed": 0}
    save(args.register, value, exclusive=True)
    print(json.dumps({"registration": d.relative(args.register), "fresh_rows_decoded": 0,
                      "next": "Publish this registration before the native --bind and metadata-only selection."}), flush=True)


def context(args):
    bound = d.load_binding(args.binding)
    registration = ROOT / bound["comparators"]["path"]
    comparison, plan = read(registration), scope()
    require(comparison["scope"] == {"path": SCOPE, "sha256": sha(ROOT / SCOPE)}
            and comparison["candidate_source"] == bound["sources"]["candidate"]
            and comparison["exporter_source"] == bound["sources"]["baseline"]
            and comparison["configurations"] == list(CONFIGURATIONS)
            and comparison["dependencies"] == DEPENDENCIES
            and comparison["schedule"] == plan["schedule"]
            and comparison["native_boundaries"] == plan["native_boundaries"]
            and comparison["evaluator_files"] == evaluator_files()
            and comparison["host"] == bound["host"], "Frozen component registration changed")
    selection = d.load_selection(bound, args.binding)
    data_binding = d.frozen_data(bound, args.binding, selection)
    return bound, comparison, selection, data_binding


def paths(comparison, index):
    stem = f"component-{index:02d}-{WORKERS[index]}"
    public, private = ROOT / comparison["output"], ROOT / comparison["state"]
    return {"report": public / (stem + ".json.gz"), "intent": public / (stem + ".intent.json"),
            "ledger": public / (stem + ".attempts.jsonl"), "archive": public / (stem + ".attempts.jsonl.gz"),
            "state": private / stem, "ticket": private / "tickets" / (stem + ".ticket")}


def search_schedule(ids):
    result = []
    for repetition in range(3):
        ordered = list(ids)
        random.Random(61512 + 1009 * repetition).shuffle(ordered)
        result.extend((repetition, identity) for identity in ordered)
    return result


class PackingCounter:
    """Only a whole-block admission guard; ordinary counters score actual text."""
    def __init__(self, counter, token_cap, char_cap=8000):
        self.counter, self.token_cap, self.char_cap = counter, token_cap, char_cap
        self.name = counter.name

    def count(self, text):
        return self.token_cap + 1 if len(text) > self.char_cap else self.counter.count(text)


def project_pages(ids, documents, config, counter):
    response = shared_response(ids, documents)
    packed = pack_whole_blocks(response, config["budget_tokens"],
                               PackingCounter(counter, config["budget_tokens"], config["budget_chars"]))
    require(len(packed["context"]) <= config["budget_chars"]
            and counter.count(packed["context"]) <= config["budget_tokens"], "Common projection exceeded its caps")
    return packed


def score_projection(case, response, originals, counters, config, groups):
    row = reused.sample_score(case, response, originals, counters, config, groups)
    row["input_query"] = scoring.query_projection(case.query)
    row["annotated_pages"] = scoring.annotated_pages(case, response, originals)
    row["annotated_page_hits"] = sum(bool(page["annotations"]) for page in row["annotated_pages"])
    row["annotated_page_precision"] = row["annotated_page_hits"] / row["result_count"] if row["result_count"] else None
    row["common_character_violation"] = len(response["context"]) > config["budget_chars"]
    row["packed_payload_sha256"] = digest(response)
    return row


def quality_metrics(rows):
    result = summarize_rows(rows)
    pages = sum(row["result_count"] for row in rows)
    hits = sum(row["annotated_page_hits"] for row in rows)
    result.update(returned_pages=pages, annotated_pages=hits,
                  annotated_page_precision=hits / pages if pages else None,
                  zero_page_queries=sum(row["result_count"] == 0 for row in rows))
    return result


def verify_dataset(data, data_binding, selection):
    require(data.fingerprint == data_binding["dataset_sha256"]
            and len(data.queries) == 512 and {case.id for case in data.queries} == set(selection["selected_ids"]),
            "Selected dataset or query universe changed")
    for case in data.queries:
        expected = data_binding["queries"][case.id]
        require(case.project == expected["project"] and len(case.required) == expected["required_evidence"]
                and case.category == expected["category"] and scoring.query_projection(case.query) == expected["input_query"],
                "Selected query/annotation identity changed")


def canonical_bundle(comparison):
    return paths(comparison, 0)["state"] / "bundle.json"


def load_bundle(comparison, export_report):
    path = canonical_bundle(comparison)
    require(path.is_file() and sha(path) == export_report["bundle_sha256"], "Canonical bundle changed or is missing")
    bundle = read(path)
    verify_content_snapshot(bundle["source_content_snapshot"])
    database = ROOT / bundle["database"]
    require(sha(database) == bundle["database_sha256"] == export_report["database_sha256"]
            and digest(bundle["documents"]) == bundle["documents_sha256"]
            and digest(bundle["diagnostics"]) == bundle["diagnostics_sha256"]
            and not Path(str(database) + "-wal").exists() and not Path(str(database) + "-shm").exists(),
            "Canonical database/documents/diagnostics changed")
    return bundle


class BookComponent:
    def __init__(self, source, expected, database, bundle, follow_titles):
        self.source = Path(source).resolve() / "memory_book"
        MemoryBook, actual, provenance = reused.imported_book(Path(source),
            {"commit": expected["commit"], "source_sha256": expected["runtime_sha256"]})
        require(actual == self.source, "Wrong imported Book component")
        self.expected, self.follow_titles = expected, follow_titles
        self.documents = {item["id"]: item for item in bundle["documents"]}
        shutil.copy2(ROOT / bundle["database"], database)
        self.book = MemoryBook(database, max_page_chars=900, cache_size=0)
        self.metadata = {"source": expected, "source_provenance": provenance,
                         "follow_titles": follow_titles, "result_cache": "disabled",
                         "boundary": scope()["native_boundaries"]["book"]}
        try:
            self.originals, self.index = source_snapshot(self.book.db), indexed_content(self.book.db)
            require(self.originals == bundle["source_snapshot"] and self.index == bundle["index"]
                    and source_content_snapshot(self.book.db) == bundle["source_content_snapshot"]
                    and digest(reused.documents_from(self.book)) == bundle["documents_sha256"],
                    "Book component differs from the canonical pages/index/sources")
        except BaseException:
            self.book.close()
            raise

    def search(self, query, project, limit):
        begin = time.perf_counter_ns()
        value = self.book.recall(query, project=project, limit=limit, budget_chars=100000,
            strategy="book", use_cache=False, coverage=False, semantic=False, follow_titles=self.follow_titles)
        elapsed = (time.perf_counter_ns() - begin) / 1e6
        require(value["cache_hit"] is False and not value.get("semantic")
                and not value.get("project_local_fts_statistics")
                and (isinstance(value.get("title_reference"), dict) if self.follow_titles else "title_reference" not in value),
                "Book policy or shipping title flag differs")
        for item in value["results"]:
            require(item["id"] in self.documents and item["text"] == self.documents[item["id"]]["text"],
                    "Book offered page was truncated or not canonical")
        return {"results": value["results"], "hit_ids": [item["id"] for item in value["results"]],
                "native_payload": value, "native_text": value["context"], "search_ms": elapsed,
                "bridge_ms": elapsed, "book_payload_sha256": digest({k: v for k, v in value.items() if k != "latency_ms"})}

    def close(self):
        try:
            self.metadata.update(source_snapshot_after=source_snapshot(self.book.db),
                index_after=indexed_content(self.book.db), source_content_snapshot_after=source_content_snapshot(self.book.db),
                result_cache_rows=self.book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0])
            require(self.metadata["source_snapshot_after"] == self.originals
                    and self.metadata["index_after"] == self.index and self.metadata["result_cache_rows"] == 0,
                    "Book changed sources/index or cached results")
        finally:
            self.book.close()
        require(engine_source_hash(self.source) == self.expected["runtime_sha256"], "Book runtime changed during component worker")


def make_engine(name, args, comparison, bundle, state):
    documents, cache = bundle["documents"], ROOT / comparison["cache"]
    if name in ENGINES[:2]:
        return BookComponent(args.source, comparison["candidate_source"], state / "book.db", bundle,
                             name == "final-follow-titles-component"), state
    if name == "claude-mem-fts":
        from benchmarks.competitors.claude_mem import ClaudeMemFTS
        return ClaudeMemFTS(documents, cache / "claude-mem", state / "native", offline=True,
            lock_path=ROOT / reused.UPSTREAM_LOCKS["claude-mem"]), state / "native"
    if name == "billion-context":
        from benchmarks.competitors.billion import BillionKernel
        return BillionKernel(documents, cache / "billion-context", offline=True,
            node=comparison["asset_pins"]["node"]["path"], lock_path=ROOT / reused.UPSTREAM_LOCKS["billion-context"]), None
    require(name == "ai-memory-hybrid", "Unknown frozen component")
    from benchmarks.competitors.ai_memory import AiMemoryNative
    engine = AiMemoryNative(documents, cache / "ai-memory", offline=True, retrieval="hybrid")
    return engine, engine._data_dir


def check_native_export(bound, binding_path, selection, data_binding, export_report, *, required=False):
    location = native.paths(bound, 0)
    if not location["report"].exists():
        require(not required, "Native baseline worker 0 is required for final canonical-page verification")
        return False
    reports = native.completed_prefix(bound, binding_path, selection, data_binding)
    require(reports and reports[0]["source_content_before"] == export_report["source_content_snapshot"]
            and reports[0]["index_before"] == export_report["index"],
            "Canonical component export differs from native baseline deterministic source content/index")
    return True


def search_cost(response, documents, project, name, counters, identity, repetition):
    ids, mapped, native_hashes = reused.component_hits(response, documents, project, name)
    payload = canonical_json(response["native_payload"] if "native_payload" in response else response["results"])
    result = {"id": identity, "repetition": repetition, "status": "ok", "hit_ids": mapped,
        "native_hit_ids": ids, "native_result_id_sha256": native_hashes,
        "unmapped_native_hits": len(ids) - len(mapped), "payload_sha256": digest(json.loads(payload)),
        "search_payload_tokens": {key: counter.count(payload) for key, counter in counters.items()},
        "search_content_tokens": {key: counter.count(response["native_text"]) for key, counter in counters.items()}
            if response.get("native_text") is not None else None,
        "search_ms": response["search_ms"], "bridge_ms": response["bridge_ms"],
        "read_policy_applied": name == "ai-memory-hybrid" and repetition == 0,
        "read_calls": 0, "read_ms": 0.0, "read_ids": [], "read_payload_sha256": [],
        "read_payload_tokens": dict.fromkeys(ENCODINGS, 0), "read_content_tokens": dict.fromkeys(ENCODINGS, 0)}
    if "book_payload_sha256" in response:
        result["book_payload_sha256"] = response["book_payload_sha256"]
    require(finite(result["search_ms"], positive=True) and finite(result["bridge_ms"], positive=True),
            "Invalid native search timing")
    return result


def read_cost(value, identity, document, counters):
    require(not value["result"].get("truncated") and value["result"].get("body") == document["text"],
            "Native read did not return the complete supplied page")
    require(finite(value["read_ms"], positive=True), "Invalid native read timing")
    payload = canonical_json(value.get("native_payload", value["result"]))
    content = value["native_text"] if value.get("native_text") is not None else canonical_json(value["result"])
    return {"page_id": identity, "body_sha256": hashlib.sha256(document["text"].encode()).hexdigest(),
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(), "read_ms": value["read_ms"],
        "payload_tokens": {name: counter.count(payload) for name, counter in counters.items()},
        "content_tokens": {name: counter.count(content) for name, counter in counters.items()}}


def run_export(args, bound, comparison, data, location, report, ledger, resources):
    MemoryBook, package, provenance = reused.imported_book(args.source,
        {"commit": comparison["exporter_source"]["commit"], "source_sha256": comparison["exporter_source"]["runtime_sha256"]})
    database = location["state"] / "frozen.db"
    seq = ledger.start("export", "source-export", 0, "selected-cohort")
    start = time.perf_counter_ns()
    with MemoryBook(database, max_page_chars=900, cache_size=0) as book:
        for session in data.sessions:
            book.ingest(session)
        ingestion_ms = (time.perf_counter_ns() - start) / 1e6
        documents, groups = reused.documents_from(book), reused.groups_for(data, book)
        bundle = {"dataset_sha256": data.fingerprint, "dataset": data.description(),
            "documents": documents, "diagnostics": groups, "documents_sha256": digest(documents),
            "diagnostics_sha256": digest(groups), "source_snapshot": source_snapshot(book.db),
            "source_content_snapshot": source_content_snapshot(book.db),
            "index": indexed_content(book.db), "stats": book.stats(),
            "source": comparison["exporter_source"], "source_provenance": provenance,
            "evidence_attainability": evidence_attainability(data, documents),
            "database": d.relative(database)}
        require(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0,
                "Canonical export unexpectedly cached a query")
        full_after = source_snapshot(book.db)
        content_after = source_content_snapshot(book.db)
        require(full_after == bundle["source_snapshot"] and content_after == bundle["source_content_snapshot"],
                "Canonical export source changed after ingestion")
        book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    require(engine_source_hash(package) == comparison["exporter_source"]["runtime_sha256"], "Exporter source changed")
    require(not Path(str(database) + "-wal").exists() and not Path(str(database) + "-shm").exists(), "Export has live SQLite sidecars")
    bundle["database_sha256"] = sha(database)
    save(canonical_bundle(comparison), bundle, exclusive=True)
    report.update(bundle_sha256=sha(canonical_bundle(comparison)), database_sha256=bundle["database_sha256"],
        source_snapshot=bundle["source_snapshot"], source_snapshot_after=full_after,
        source_content_snapshot=bundle["source_content_snapshot"], source_content_snapshot_after=content_after,
        index=bundle["index"], documents_sha256=bundle["documents_sha256"],
        diagnostics_sha256=bundle["diagnostics_sha256"], document_count=len(documents),
        source_ingestion_ms=ingestion_ms, source_provenance=provenance,
        evidence_attainability=bundle["evidence_attainability"], storage=storage(location["state"]))
    ledger.finish(seq, {"operation": "export", "database_sha256": bundle["database_sha256"],
                        "documents_sha256": bundle["documents_sha256"]})


def run_component(args, comparison, selection, data, bundle, location, report, ledger, resources):
    name = WORKERS[args.worker]
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    require(all(counter.version == "0.12.0" for counter in counters.values()), "Reference tokenizer version changed")
    originals = original_turn_texts(data)
    cases = {case.id: case for case in data.queries}
    documents = {doc["id"]: doc for doc in bundle["documents"]}
    require(len(documents) == len(bundle["documents"]), "Canonical documents repeat an ID")
    start = time.perf_counter_ns()
    engine, native_state = make_engine(name, args, comparison, bundle, location["state"])
    report["preparation"] = {"engine_setup_wall_ms": (time.perf_counter_ns() - start) / 1e6}
    first_ids = {}
    resources.set_phase("queries")
    try:
        for repetition, identity in search_schedule(selection["selected_ids"]):
            case = cases[identity]
            seq = ledger.start(name, "search", repetition, identity)
            response = engine.search(case.query, case.project, 5)
            cost = search_cost(response, documents, case.project, name, counters, identity, repetition)
            ledger.finish(seq, {"operation": "search", "cost": copy.deepcopy(cost)})
            if cost["read_policy_applied"]:
                for page_id in cost["hit_ids"]:
                    seq = ledger.start(name, "native-read", repetition, identity)
                    part = read_cost(engine.read(page_id), page_id, documents[page_id], counters)
                    ledger.finish(seq, {"operation": "native-read", "id": identity, "repetition": repetition, "read": part})
                    cost["read_calls"] += 1
                    cost["read_ms"] += part["read_ms"]
                    cost["read_ids"].append(page_id)
                    cost["read_payload_sha256"].append(part["payload_sha256"])
                    for encoding in ENCODINGS:
                        cost["read_payload_tokens"][encoding] += part["payload_tokens"][encoding]
                        cost["read_content_tokens"][encoding] += part["content_tokens"][encoding]
            report["timing_rows"].append(cost)
            if repetition == 0:
                first_ids[identity] = list(cost["hit_ids"])
        resources.set_phase("finalization")
        report["storage_before_close"] = storage(native_state) if native_state else {
            "regular_file_bytes": 0, "boundary": "Upstream search kernel uses an in-memory supplied corpus; no persistent corpus store."}
    finally:
        try:
            engine.close()
        finally:
            report["metadata"] = engine.metadata
    report["storage_after_close"] = storage(native_state) if native_state else report["storage_before_close"]
    resources.set_phase("packing")
    for config in CONFIGURATIONS:
        rows, packing = [], []
        for identity in selection["selected_ids"]:
            seq = ledger.start(name, config, 0, identity)
            begin = time.perf_counter_ns()
            response = project_pages(first_ids[identity], documents, config, counters[config["tokenizer"]])
            elapsed = (time.perf_counter_ns() - begin) / 1e6
            score = score_projection(cases[identity], response, originals, counters, config, bundle["diagnostics"])
            sample = {"id": identity, "elapsed_ms": elapsed, "score": score}
            ledger.finish(seq, {"operation": "packing", "configuration": config["index"], "sample": sample})
            rows.append(score)
            packing.append({"id": identity, "elapsed_ms": elapsed, "score_sha256": digest(score)})
        report["configurations"].append({**config, "query_results": rows, "packing_samples": packing,
                                         "packing_latency": latency_summary([x["elapsed_ms"] for x in packing]),
                                         "metrics": quality_metrics(rows)})
    report.update(component_costs(report["timing_rows"], "First repetition only: every mapped original top-five page is read through native memory_read_page; None metadata slots are not replaced. Later repetitions measure search only."))
    originals_by_query = {row["id"]: row for row in report["timing_rows"] if row["repetition"] == 0}
    report["repeat_changes"] = [{"id": row["id"], "repetition": row["repetition"],
        "native_slots_changed": row["native_hit_ids"] != originals_by_query[row["id"]]["native_hit_ids"],
        "native_id_hashes_changed": row["native_result_id_sha256"] != originals_by_query[row["id"]]["native_result_id_sha256"]}
        for row in report["timing_rows"] if row["repetition"]]
    report["quality_boundary"] = "Only first-pass offered pages, projected by the same whole-page/character/token rules. MRR/precision refer to actually packed page context, while all original native slots, unmapped metadata, native/read payloads and costs remain separate. No generated answer or native T1 title-quality gate is inferred."


def finite(value, *, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def verify_projection(row, config, expected):
    require(row["project"] == expected["project"] and row["category"] == expected["category"]
            and row["required_evidence"] == expected["required_evidence"] and row["answerable"] is True
            and row["input_query"] == expected["input_query"], "Packed row changed query/annotation identity")
    require(not any(row[key] for key in reused.INVARIANTS) and not row["common_character_violation"],
            "Packed row has source, scope, reconstruction or budget violations")
    ids = row["result_ids"]
    pages = row["annotated_pages"]
    require([page["id"] for page in pages] == ids and len(ids) == len(set(ids)) == row["result_count"] <= 5,
            "Packed page count/identity changed")
    for page in pages:
        require(page["annotations"] == sorted(set(page["annotations"]))
                and all(type(i) is int and 0 <= i < expected["required_evidence"] for i in page["annotations"]),
                "Invalid packed-page annotation accounting")
    ranks = [next((rank for rank, page in enumerate(pages, 1) if index in page["annotations"]), None)
             for index in range(expected["required_evidence"])]
    found = sum(rank is not None for rank in ranks)
    hits = sum(bool(page["annotations"]) for page in pages)
    require(row["evidence_ranks"] == ranks and row["matched_evidence"] == found
            and row["complete"] == (found == expected["required_evidence"])
            and row["reciprocal_rank"] == (1 / min(rank for rank in ranks if rank is not None) if found else 0.0)
            and row["annotated_page_hits"] == hits
            and row["annotated_page_precision"] == (hits / len(ids) if ids else None),
            "Packed evidence metrics do not follow all returned-page annotations")
    require(type(row["returned_characters"]) is int and 0 <= row["returned_characters"] <= config["budget_chars"]
            and row["reported_context_chars"] == row["returned_characters"] and row["context_size_consistent"] is True
            and set(row["context_tokens"]) == set(ENCODINGS)
            and all(type(value) is int and value >= 0 for value in row["context_tokens"].values())
            and row["context_tokens"][config["tokenizer"]] <= config["budget_tokens"], "Packed character/token counts changed")


def finished_events(ledger):
    events = [json.loads(line) for line in ledger.splitlines()]
    require(len(events) % 2 == 0, "Incomplete component call ledger")
    finished = []
    for offset in range(0, len(events), 2):
        start, end = events[offset:offset + 2]
        require(start["event"] == "started" and end["event"] == "finished"
                and start["seq"] == end["seq"] == offset // 2 + 1, "Component ledger order or completion changed")
        finished.append((start, end))
    return finished


def verify_report(report, ledger, bound, comparison, selection, data_binding, binding_path, index):
    require(report["version"] == VERSION and report["status"] == "completed"
            and "error" not in report
            and report["worker"] == {"index": index, "name": WORKERS[index]}
            and report["binding_sha256"] == sha(binding_path)
            and report["selection_sha256"] == sha(ROOT / bound["selection"])
            and report["data_binding_sha256"] == sha(ROOT / bound["data_binding"])
            and report["registration_sha256"] == bound["comparators"]["sha256"]
            and report["host"] == bound["host"] and report["dataset_sha256"] == data_binding["dataset_sha256"]
            and report["ledger_sha256"] == hashlib.sha256(ledger).hexdigest(), "Component report provenance changed")
    verify_content_snapshot(report["source_content_snapshot"])
    location = paths(comparison, index)
    intent = read(location["intent"])
    verify_intent(intent, bound, comparison, selection, binding_path, index)
    publication = report["intent_publication_commit"]
    require(type(publication) is str and len(publication) == 40 and all(c in "0123456789abcdef" for c in publication)
            and report["intent_sha256"] == sha(location["intent"])
            and location["intent"].read_bytes() == d.git("show", publication + ":" + d.relative(location["intent"])),
            "Component report lacks its exact previously published intent")
    events = finished_events(ledger)
    require(all(start["stage"] == WORKERS[index] for start, _ in events), "Ledger stage differs from the fixed worker")
    if index == 0:
        require(report["source_snapshot_after"] == report["source_snapshot"]
                and report["source_content_snapshot_after"] == report["source_content_snapshot"],
                "Canonical export source changed within its worker")
        require(len(events) == 1 and events[0][1]["operation"] == "export"
                and events[0][0]["configuration"] == "source-export" and events[0][0]["repetition"] == 0
                and events[0][0]["id"] == "selected-cohort"
                and events[0][1]["database_sha256"] == report["database_sha256"]
                and events[0][1]["documents_sha256"] == report["documents_sha256"], "Export ledger differs")
        return
    costs = report["timing_rows"]
    require([(row["repetition"], row["id"]) for row in costs] == search_schedule(selection["selected_ids"]),
            "A native search repetition was omitted, replaced or reordered")
    expected_operations = []
    for row in costs:
        expected_operations.append(("search", row["repetition"], row["id"]))
        if index == 5 and row["repetition"] == 0:
            expected_operations.extend(("native-read", 0, row["id"]) for _ in row["hit_ids"])
    expected_operations.extend(("packing", 0, identity) for _ in CONFIGURATIONS for identity in selection["selected_ids"])
    require([(end["operation"], start["repetition"], start["id"]) for start, end in events] == expected_operations,
            "Search/read/packing operations differ from the fixed chronological schedule")
    search_events = [(start, end) for start, end in events if end["operation"] == "search"]
    require(len(search_events) == len(costs) == 1536, "Native search count differs")
    read_events = [(start, end) for start, end in events if end["operation"] == "native-read"]
    reads_by_query = {}
    for start, end in read_events:
        require(start["configuration"] == "native-read" and start["id"] == end["id"]
                and start["repetition"] == end["repetition"], "Native read ledger identity changed")
        reads_by_query.setdefault((start["repetition"], start["id"]), []).append(end["read"])
    for row, (start, end) in zip(costs, search_events, strict=True):
        require(start["id"] == row["id"] and start["repetition"] == row["repetition"]
                and start["configuration"] == "search", "Search ledger identity changed")
        original = end["cost"]
        read_fields = {"read_calls", "read_ms", "read_ids", "read_payload_sha256", "read_payload_tokens", "read_content_tokens"}
        require({key: value for key, value in row.items() if key not in read_fields}
                == {key: value for key, value in original.items() if key not in read_fields}, "Search result changed after native execution")
        ids = row["native_hit_ids"]
        require(len(ids) <= 5 and row["hit_ids"] == [identity for identity in ids if identity is not None]
                and len(row["hit_ids"]) == len(set(row["hit_ids"]))
                and len(row["native_result_id_sha256"]) == len(set(row["native_result_id_sha256"])) == len(ids)
                and row["unmapped_native_hits"] == ids.count(None), "Native slots were dropped, replaced or duplicated")
        require(index == 5 or None not in ids, "Unmapped metadata is only allowed for ai-memory")
        require(finite(row["search_ms"], positive=True) and finite(row["bridge_ms"], positive=True)
                and finite(row["read_ms"]), "Invalid component native timing")
        parts = reads_by_query.get((row["repetition"], row["id"]), [])
        expected_reads = row["hit_ids"] if index == 5 and row["repetition"] == 0 else []
        require([part["page_id"] for part in parts] == row["read_ids"] == expected_reads
                and row["read_calls"] == len(parts) and row["read_ms"] == sum(part["read_ms"] for part in parts)
                and row["read_payload_sha256"] == [part["payload_sha256"] for part in parts], "Native read proof/count differs")
        require(all(finite(part["read_ms"], positive=True) for part in parts), "Invalid native read timing")
        for field, native_field in (("read_payload_tokens", "payload_tokens"), ("read_content_tokens", "content_tokens")):
            require(row[field] == {name: sum(part[native_field][name] for part in parts) for name in ENCODINGS}, "Native read token totals differ")
    require(len(read_events) <= 2560 and len(read_events) == sum(row["read_calls"] for row in costs), "Unaccounted native reads")
    packing_events = [(start, end) for start, end in events if end["operation"] == "packing"]
    require(len(packing_events) == 3072 and len(events) == 1536 + len(read_events) + 3072, "Extra/missing component operation")
    require([{key: value[key] for key in config} for value, config in zip(report["configurations"], CONFIGURATIONS, strict=True)]
            == list(CONFIGURATIONS), "Component axes changed")
    cursor = 0
    first = {row["id"]: row for row in costs if row["repetition"] == 0}
    for value, config in zip(report["configurations"], CONFIGURATIONS, strict=True):
        rows, samples = value["query_results"], value["packing_samples"]
        require([row["id"] for row in rows] == selection["selected_ids"]
                and [row["id"] for row in samples] == selection["selected_ids"], "Packed query order/count changed")
        for row, sample in zip(rows, samples, strict=True):
            start, end = packing_events[cursor]
            cursor += 1
            require(start["configuration"] == config and start["id"] == row["id"] and start["repetition"] == 0
                    and end["configuration"] == config["index"] and end["sample"] == {"id": row["id"], "elapsed_ms": sample["elapsed_ms"], "score": row}
                    and sample["score_sha256"] == digest(row) and finite(sample["elapsed_ms"], positive=True), "Packing ledger or timing differs")
            offered = first[row["id"]]["hit_ids"]
            require(row["result_ids"] == [identity for identity in offered if identity in row["result_ids"]], "Packing replaced or reordered offered pages")
            verify_projection(row, config, data_binding["queries"][row["id"]])
        require(value["metrics"] == quality_metrics(rows)
                and value["packing_latency"] == latency_summary([x["elapsed_ms"] for x in samples]), "Packed aggregates differ from saved rows")
    costs_summary = component_costs(costs, "First repetition only: every mapped original top-five page is read through native memory_read_page; None metadata slots are not replaced. Later repetitions measure search only.")
    require(all(report[key] == value for key, value in costs_summary.items()), "Native cost aggregates differ from original rows")
    changes = [{"id": row["id"], "repetition": row["repetition"],
        "native_slots_changed": row["native_hit_ids"] != first[row["id"]]["native_hit_ids"],
        "native_id_hashes_changed": row["native_result_id_sha256"] != first[row["id"]]["native_result_id_sha256"]}
        for row in costs if row["repetition"]]
    require(report["repeat_changes"] == changes, "Repeat changes were omitted or rewritten")
    if index in (1, 2):
        require(report["metadata"]["source"] == comparison["candidate_source"]
                and report["metadata"]["follow_titles"] is (index == 2)
                and report["metadata"]["source_snapshot_after"] == report["source_snapshot"]
                and report["metadata"]["source_content_snapshot_after"] == report["source_content_snapshot"]
                and report["metadata"]["index_after"] == report["index"]
                and report["metadata"]["result_cache_rows"] == 0, "Book source/index/cache policy changed")
    else:
        repository = {3: "thedotmack/claude-mem", 4: "ranxianglei/billion-context", 5: "akitaonrails/ai-memory"}[index]
        pin = next(item for item in comparison["upstream_pins"] if item["repository"] == repository)
        require(report["metadata"]["commit"] == pin["commit"], "Comparator executed another source revision")
        if index == 3:
            require(report["metadata"]["source_unchanged"] is True, "Claude-mem source changed")


def completed_prefix(bound, comparison, selection, data_binding, binding_path):
    completed, missing = [], False
    for index in range(len(WORKERS)):
        location = paths(comparison, index)
        if location["report"].exists():
            require(not missing, "Component completion is not a contiguous prefix")
            value = read(location["report"])
            verify_report(value, native.ledger_bytes(location), bound, comparison, selection, data_binding, binding_path, index)
            completed.append(value)
        else:
            missing = True
            require(not location["state"].exists() and not location["ledger"].exists()
                    and not location["archive"].exists(), "Preserve an interrupted component attempt; do not replay it")
    return completed


def published_paths(bound, comparison, binding_path, completed):
    result = [binding_path, ROOT / bound["selection"], ROOT / bound["data_binding"], ROOT / bound["comparators"]["path"]]
    for index in range(len(completed)):
        location = paths(comparison, index)
        result.extend(location[key] for key in ("intent", "report", "archive"))
    native_zero = native.paths(bound, 0)
    if native_zero["report"].exists():
        result.extend(native_zero[key] for key in ("intent", "report", "archive"))
    return result


def verify_intent(intent, bound, comparison, selection, binding_path, index):
    require(intent["version"] == VERSION and intent["status"] == "intent-before-single-use-launch"
            and intent["worker"] == {"index": index, "name": WORKERS[index]}
            and intent["binding_sha256"] == sha(binding_path)
            and intent["selection_sha256"] == sha(ROOT / bound["selection"])
            and intent["data_binding_sha256"] == sha(ROOT / bound["data_binding"])
            and intent["registration_sha256"] == bound["comparators"]["sha256"]
            and intent["completed_prefix"] == list(range(index)) and intent["host"] == bound["host"]
            and intent["search_schedule_sha256"] == (digest(search_schedule(selection["selected_ids"])) if index else None),
            "Component worker intent changed")


def create_intent(args):
    bound, comparison, selection, data_binding = context(args)
    require(0 <= args.intent < len(WORKERS), "Unknown component stage")
    (ROOT / bound["state"]).parent.mkdir(parents=True, exist_ok=True)
    with scoring._lock(ROOT / bound["state"]):
        completed = completed_prefix(bound, comparison, selection, data_binding, args.binding)
        require(args.intent == len(completed) and d.host() == bound["host"], "Only next component stage on the frozen host may start")
        d.published(bound, args.published_commit, published_paths(bound, comparison, args.binding, completed))
        location = paths(comparison, args.intent)
        require(not any(path.exists() for path in location.values()), "Preserve prior component intent/ticket/attempt")
        require(not d.git("ls-tree", args.published_commit, "--", d.relative(location["intent"])),
                "A published component intent cannot receive a replacement ticket")
        ticket = secrets.token_hex(32).encode()
        location["ticket"].parent.mkdir(parents=True, exist_ok=True)
        with location["ticket"].open("xb") as stream:
            stream.write(ticket)
            stream.flush()
            os.fsync(stream.fileno())
        intent = {"version": VERSION, "status": "intent-before-single-use-launch",
            "worker": {"index": args.intent, "name": WORKERS[args.intent]}, "created_at": now(),
            "binding_sha256": sha(args.binding), "selection_sha256": sha(ROOT / bound["selection"]),
            "data_binding_sha256": sha(ROOT / bound["data_binding"]),
            "registration_sha256": bound["comparators"]["sha256"], "host": bound["host"],
            "completed_prefix": list(range(args.intent)), "prior_publication_commit": args.published_commit,
            "search_schedule_sha256": digest(search_schedule(selection["selected_ids"])) if args.intent else None,
            "ticket_sha256": hashlib.sha256(ticket).hexdigest(),
            "rule": "Publish this exact intent, then consume the private ticket once; a partial export/search worker is never recreated."}
        save(location["intent"], intent, exclusive=True)
    print(json.dumps({"intent": d.relative(location["intent"]), "content_rows_decoded": 0,
                      "next": "Publish the intent before --worker."}), flush=True)


def worker(args):
    bound, comparison, selection, data_binding = context(args)
    require(0 <= args.worker < len(WORKERS) and args.parquet, "Worker needs an exact index and pinned Parquet")
    if args.worker <= 2:
        expected = comparison["exporter_source"] if args.worker == 0 else comparison["candidate_source"]
        require(args.source and scoring.source(args.source) == expected, "Worker source differs from its frozen revision")
    location = paths(comparison, args.worker)
    (ROOT / bound["state"]).parent.mkdir(parents=True, exist_ok=True)
    with scoring._lock(ROOT / bound["state"]):
        completed = completed_prefix(bound, comparison, selection, data_binding, args.binding)
        require(len(completed) == args.worker and d.host() == bound["host"], "Wrong component prefix or host")
        intent = read(location["intent"])
        verify_intent(intent, bound, comparison, selection, args.binding, args.worker)
        d.published(bound, args.published_commit, [*published_paths(bound, comparison, args.binding, completed), location["intent"]])
        native.consume_ticket(location, intent)
        report = {"version": VERSION, "status": "running", "started_at": now(),
            "worker": {"index": args.worker, "name": WORKERS[args.worker]},
            "binding_sha256": sha(args.binding), "selection_sha256": sha(ROOT / bound["selection"]),
            "data_binding_sha256": sha(ROOT / bound["data_binding"]), "registration_sha256": bound["comparators"]["sha256"],
            "intent_sha256": sha(location["intent"]), "intent_publication_commit": args.published_commit,
            "host": bound["host"], "dataset_sha256": data_binding["dataset_sha256"],
            "timing_rows": [], "configurations": []}
        with native.retain_attempt(report, location):
            resources = Resources()
            ledger = None
            try:
                resources.set_phase("asset-verification")
                require(asset_pins(ROOT / comparison["cache"], comparison["asset_pins"]["node"]["path"])
                        == comparison["asset_pins"], "Prepared comparator assets changed after registration")
                resources.set_phase("selected-data-loading")
                data = d.load_dataset(args.parquet, bound, selection)
                verify_dataset(data, data_binding, selection)
                location["ledger"].parent.mkdir(parents=True, exist_ok=True)
                ledger = reused.Ledger(location["ledger"])
                resources.set_phase("setup")
                if args.worker == 0:
                    run_export(args, bound, comparison, data, location, report, ledger, resources)
                    report["native_baseline_cross_check"] = check_native_export(bound, args.binding, selection, data_binding, report)
                else:
                    bundle = load_bundle(comparison, completed[0])
                    require(bundle["dataset_sha256"] == data_binding["dataset_sha256"], "Exported cohort differs")
                    report.update(source_snapshot=bundle["source_snapshot"], source_content_snapshot=bundle["source_content_snapshot"],
                                  index=bundle["index"],
                                  documents_sha256=bundle["documents_sha256"], canonical_export_sha256=sha(paths(comparison, 0)["report"]))
                    report["native_baseline_cross_check"] = check_native_export(bound, args.binding, selection, data_binding, completed[0])
                    run_component(args, comparison, selection, data, bundle, location, report, ledger, resources)
                resources.set_phase("final-verification")
                require(asset_pins(ROOT / comparison["cache"], comparison["asset_pins"]["node"]["path"])
                        == comparison["asset_pins"], "Comparator assets changed during execution")
            finally:
                if ledger is not None:
                    ledger.close()
                report["resources"] = resources.close()
            report["status"] = "completed"
            ledger_data = location["ledger"].read_bytes()
            report["ledger_sha256"] = hashlib.sha256(ledger_data).hexdigest()
            verify_report(report, ledger_data, bound, comparison, selection, data_binding, args.binding, args.worker)
    print(json.dumps({"worker": args.worker, "report": d.relative(location["report"]),
                      "next": "Publish complete report, intent and lossless ledger archive before the next component intent."}), flush=True)


def paired_quality(left, right):
    require(set(left) == set(right), "Paired component question universe differs")
    gains = [identity for identity in left if not left[identity]["complete"] and right[identity]["complete"]]
    losses = [identity for identity in left if left[identity]["complete"] and not right[identity]["complete"]]
    before, after = quality_metrics(list(left.values())), quality_metrics(list(right.values()))
    fields = ("complete_evidence_rate", "evidence_recall", "mrr", "annotated_page_precision")
    return {"before": before, "after": after,
        "deltas": {key: after[key] - before[key] if before[key] is not None and after[key] is not None else None for key in fields},
        "complete_gain_ids": gains, "complete_loss_ids": losses,
        "note": "Descriptive paired supplied-page comparison; no new native-T1 or whole-product acceptance gate."}


def audit(args):
    bound, comparison, selection, data_binding = context(args)
    completed = completed_prefix(bound, comparison, selection, data_binding, args.binding)
    require(len(completed) == len(WORKERS), "All fixed component stages are required; preserve an incomplete attempt")
    d.published(bound, args.published_commit, published_paths(bound, comparison, args.binding, completed))
    check_native_export(bound, args.binding, selection, data_binding, completed[0], required=True)
    require(all(report["source_snapshot"] == completed[0]["source_snapshot"]
                and report["source_content_snapshot"] == completed[0]["source_content_snapshot"]
                and report["index"] == completed[0]["index"]
                and report["documents_sha256"] == completed[0]["documents_sha256"] for report in completed[1:]),
            "Component workers used different pages/sources/indexes")
    comparisons = []
    for configuration in CONFIGURATIONS:
        mode_rows = {report["worker"]["name"]: {row["id"]: row for row in report["configurations"][configuration["index"]]["query_results"]}
                     for report in completed[1:]}
        pairs = [(ENGINES[0], ENGINES[1]), *[(other, own) for other in ENGINES[2:] for own in ENGINES[:2]]]
        comparisons.append({"configuration": configuration,
            "pairs": [{"before_engine": before, "after_engine": after, **paired_quality(mode_rows[before], mode_rows[after])}
                      for before, after in pairs]})
    summary = {"version": VERSION, "status": "same-cohort-components-complete", "integrity_passed": True,
        "binding_sha256": sha(args.binding), "selection_sha256": sha(ROOT / bound["selection"]),
        "data_binding_sha256": sha(ROOT / bound["data_binding"]), "registration_sha256": bound["comparators"]["sha256"],
        "total_search_calls": 7680, "quality_rows": 15360,
        "actual_ai_memory_native_reads": sum(row["read_calls"] for row in completed[5]["timing_rows"]),
        "comparisons": comparisons, "native_boundaries": comparison["native_boundaries"],
        "workers": [{"worker": report["worker"], "report_sha256": sha(paths(comparison, index)["report"]),
                     "ledger_sha256": report["ledger_sha256"], "archive_sha256": sha(paths(comparison, index)["archive"])}
                    for index, report in enumerate(completed)],
        "limits": "All native search/read, first/repeat, packing, setup, RSS and storage costs remain in their original engine reports. Common packed context quality is separate from native T1 and generated-answer quality; no historical competitor score or mismatched transport latency is spliced into this result."}
    target = ROOT / comparison["output"] / "summary.json.gz"
    if args.write_summary:
        require(not target.exists(), "Never overwrite a comparison summary")
        save(target, summary, exclusive=True)
    else:
        require(read(target) == summary, "Published comparator summary differs from original rows")
    print(json.dumps({"verified": True, "search_calls_executed_by_audit": 0, "quality_rows": 15360}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--register", type=Path)
    action.add_argument("--intent", type=int)
    action.add_argument("--worker", type=int)
    action.add_argument("--audit", action="store_true")
    for name in ("binding", "source", "selection", "state", "output", "cache", "node", "parquet"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--published-commit")
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args(argv)
    if args.register:
        register(args)
    else:
        require(args.binding is not None, "The exact native fresh binding is required")
        if args.intent is not None:
            create_intent(args)
        elif args.worker is not None:
            worker(args)
        else:
            audit(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
