"""Frozen round-three native and supplied-page comparison, with no implicit replay.

This module never selects questions. The separate round3_data loader requires
a committed selection made after this evaluator, sources and assets are bound.
Historical round-two functions are reused with explicit new plan objects; their
registration, source constants and recorded reports are never rebound.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import round2_eval as reused
from benchmarks.component_eval import canonical_json, shared_response
from benchmarks.round2_resources import Resources, storage
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import paired_changes, source_snapshot
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
    latency_summary, pack_whole_blocks, summarize_rows)
from scripts.benchmark_default_recall import indexed_content
from scripts.summarize_round2_validation import verify_configurations, verify_samples

PLAN = ROOT / "benchmarks/experiments/round3-plan.json"
PLAN_COMMIT = "2ce405408d323aac61fa9e9f536a704dd5f2b372"
BINDING = ROOT / "benchmarks/experiments/round3-validation-binding.json"
MANIFEST = ROOT / "benchmarks/experiments/round3-hotpot256-manifest.json"
BASELINE = {"commit": "dd2f88be742ed330269e7dd5915b6f75089d7fef",
    "source_sha256": "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57"}
VERSION = "round3-native-component-comparison-1"
SEED = 31061
MODEL_FINGERPRINT = "2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25"
NEW_FILES = ("scripts/round3_comparison.py", "tests/test_round3_comparison.py",
             "scripts/round3_data.py", "tests/test_round3_data.py",
             "scripts/run_round3_comparison.py", "tests/test_round3_comparison_controller.py",
             ".github/workflows/round3-comparison.yml", "benchmarks/experiments/round3-plan.json")
ADDITIONAL_OLD_FILES = ("scripts/benchmark_default_recall.py",)
PACKAGES = {"tiktoken": "0.12.0", "onnxruntime": "1.31.1", "tokenizers": "0.23.3", "numpy": "2.5.4", "pyarrow": "26.0.1"}
NATIVE = ("baseline-native", "candidate-native", "candidate-semantic-native")
COMPONENTS = ("baseline-component", "candidate-component", "candidate-semantic-component",
              "claude-mem-fts", "ai-memory-hybrid", "billion-context")
PRIMARY_GROUPS = ("low_lexical_overlap_le_0.25", "multiple_required_evidence", "cross_session", "cross_chapter")
INVARIANTS = (*reused.INVARIANTS, "cache_error", "policy_error", "result_limit_error")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def relative_file(name):
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == name,
            "Evaluator path must be a canonical repository-relative file")
    target = ROOT / path
    require(target.resolve().is_relative_to(ROOT.resolve()) and target.is_file() and not target.is_symlink(),
            "Missing/unsafe regular evaluator file: " + name)
    return target


def require_committed(path):
    name = str(Path(path).resolve().relative_to(ROOT.resolve()))
    require(Path(path).read_bytes() == git("show", "HEAD:" + name), "Uncommitted input: " + name)


def registered_plan():
    require(PLAN.read_bytes() == git("show", PLAN_COMMIT + ":" + str(PLAN.relative_to(ROOT))),
            "Registered round-three plan changed")
    plan = json.loads(PLAN.read_bytes())
    p = plan["independent_validation"]
    require(plan["baseline"]["commit"] == BASELINE["commit"]
            and p["cohort"]["count"] == 256 and p["native"]["base_calls"] == 4608
            and p["components"]["base_search_calls"] == 4608
            and p["native"]["token_budgets"] == [512, 1024, 2048]
            and p["native"]["tokenizers"] == list(ENCODINGS)
            and p["native"]["budget_chars"] == 8000 and p["native"]["repeats"] == 1
            and p["components"]["repeats"] == 3 and p["components"]["top_k"] == 5,
            "Registered comparison axes changed")
    return plan


def evaluator_files(extras=()):
    historical_path = ROOT / "benchmarks/round2_candidate.json"
    require(historical_path.read_bytes() == git("show", BASELINE["commit"] + ":benchmarks/round2_candidate.json"),
            "Historical binding was changed")
    historical = json.loads(historical_path.read_bytes())["evaluator_sha256"]
    require(len(historical) == 58, "Expected all 58 historical evaluator files")
    hashes = {}
    for name, expected in historical.items():
        require(file_sha(relative_file(name)) == expected, "Historical helper changed: " + name)
        hashes[name] = expected
    for name in ADDITIONAL_OLD_FILES:
        require(relative_file(name).read_bytes() == git("show", BASELINE["commit"] + ":" + name),
                "Reused baseline helper changed: " + name)
    for name in (*ADDITIONAL_OLD_FILES, *NEW_FILES, *extras):
        hashes[name] = file_sha(relative_file(name))
    return dict(sorted(hashes.items()))


def model_identity():
    old = json.loads((ROOT / "benchmarks/experiments/semantic-local-plan.json").read_bytes())["model"]
    value = {key: old[key] for key in ("repository", "revision", "files", "dimensions", "max_sequence_tokens")}
    value.update(overlap_tokens=32, pooling="attention-mask mean pooling followed by L2 normalization", semantic_version=1)
    require(reused.digest(value) == MODEL_FINGERPRINT, "Pinned semantic identity changed")
    return value


def verify_model(directory, identity):
    require(identity == model_identity(), "Model identity differs from the registered files")
    for item in identity["files"]:
        path = Path(directory) / item["path"]
        require(path.is_file() and path.stat().st_size == item["bytes"]
                and file_sha(path) == item["sha256"], "Model file differs: " + item["path"])


def source_identity(path):
    package = Path(path).resolve() / "memory_book"
    provenance = checkout_provenance(package)
    require(provenance["commit_identifies_source"] is True, "Runtime is not its exact committed source")
    return {"commit": provenance["git_commit"], "source_sha256": engine_source_hash(package)}


def check_old_statistics_gate(path):
    raw = gzip.decompress(Path(path).read_bytes())
    report = json.loads(raw)
    summary_path = Path(str(path).removesuffix(".json.gz") + ".summary.json")
    summary = json.loads(summary_path.read_bytes())
    require(summary["full_report_sha256"] == sha(raw)
            and summary["compressed_report_sha256"] == file_sha(path), "Old statistics report hashes differ")
    projected = {key: value for key, value in report.items() if key != "workers"}
    projected["workers"] = [{**{key: value for key, value in worker.items()
        if key not in ("configurations", "query_ids", "query_ids_original_order")},
        "configurations": [{key: value for key, value in config.items() if key != "rows"}
                           for config in worker["configurations"]]} for worker in report["workers"]]
    projected.update(full_report_sha256=sha(raw), compressed_report_sha256=file_sha(path))
    require(summary == projected, "Old statistics summary is not its exact raw projection")
    require(report["validation"]["passed"] is True and report["validation"]["calls"] == 8082
            and report["validation"]["workers"] == len(report["workers"]) == 8
            and all(worker["status"] == "completed" for worker in report["workers"])
            and report["screening"]["qualified"] is True
            and report["screening"]["status"] == "qualified_for_independent_validation",
            "Project-statistics candidate did not qualify on the registered old data")
    for item in (path, summary_path):
        require_committed(item)
    return {"path": str(Path(path).relative_to(ROOT)), "sha256": file_sha(path),
            "summary_path": str(summary_path.relative_to(ROOT)), "summary_sha256": file_sha(summary_path)}


def bind(args):
    registered_plan()
    require(not args.output.exists(), "Never overwrite a prior binding")
    sources = {key: source_identity(value) for key, value in (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == BASELINE, "Baseline differs from v0.3.0")
    extras = sorted(set(args.extra_evaluator or []))
    require(not {str(args.output.resolve().relative_to(ROOT.resolve())), str(MANIFEST.relative_to(ROOT))} & set(extras),
            "Binding and future manifest must not be self-bound")
    hashes = evaluator_files(extras)
    commit = git("rev-parse", "HEAD").decode().strip()
    for name, expected in hashes.items():
        require(sha(git("show", commit + ":" + name)) == expected, "Commit evaluator before binding: " + name)
    identity = model_identity()
    verify_model(args.model_dir, identity)
    gate = check_old_statistics_gate(args.statistics_gate.resolve()) if args.statistics_gate else None
    value = {"schema_version": 1, "evaluator": VERSION, "status": "frozen-before-selection",
        "created_at": reused.now(), "plan_sha256": file_sha(PLAN), **sources,
        "optional_semantic": True, "optional_project_statistics": gate is not None,
        "project_statistics_old_gate": gate, "upstream_locks": reused.UPSTREAM_LOCKS,
        "upstream_lock_sha256": {key: file_sha(ROOT / path) for key, path in reused.UPSTREAM_LOCKS.items()},
        "model": {"identity": identity, "fingerprint": MODEL_FINGERPRINT},
        "evaluator_commit": commit, "evaluator_files": hashes, "extra_evaluator_files": extras,
        "packages": PACKAGES, "policy": "Freeze before selecting IDs; no reranking or repeat selection after first scoring. No automatic rerun."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"binding": str(args.output), "sha256": file_sha(args.output), "next": "Commit before selection."}))


def frozen_inputs(binding_path=BINDING):
    plan = registered_plan()
    require_committed(binding_path)
    binding = json.loads(Path(binding_path).read_bytes())
    require(binding["schema_version"] == 1 and binding["evaluator"] == VERSION
            and binding["status"] == "frozen-before-selection" and binding["baseline"] == BASELINE
            and binding["plan_sha256"] == file_sha(PLAN) and binding["optional_semantic"] is True
            and type(binding["optional_project_statistics"]) is bool
            and binding["upstream_locks"] == reused.UPSTREAM_LOCKS
            and binding["model"] == {"identity": model_identity(), "fingerprint": MODEL_FINGERPRINT}
            and binding["packages"] == PACKAGES, "Binding source, settings or assets differ")
    require(binding["evaluator_files"] == evaluator_files(binding["extra_evaluator_files"]),
            "Bound evaluator bytes differ")
    for name, expected in binding["evaluator_files"].items():
        require(sha(git("show", binding["evaluator_commit"] + ":" + name)) == expected,
                "Evaluator did not exist at its pre-selection commit")
    require(binding["upstream_lock_sha256"] == {key: file_sha(ROOT / path) for key, path in reused.UPSTREAM_LOCKS.items()},
            "Pinned upstream source/blob locks differ")
    gate = binding["project_statistics_old_gate"]
    require((gate is not None) == binding["optional_project_statistics"], "Optional axis and qualification gate differ")
    if gate is not None:
        require(check_old_statistics_gate(ROOT / gate["path"]) == gate, "Saved old-data qualification gate changed")
    return plan, binding


def stages(binding):
    native, components = list(NATIVE), list(COMPONENTS)
    if binding["optional_project_statistics"]:
        native.append("candidate-statistics-native")
        components.append("candidate-statistics-component")
    return ["export", *native, *components]


def old_shape_plan(plan, binding, stage):
    """Explicit adapter for pure old helpers; never uses their frozen_inputs()."""
    axes = plan["independent_validation"]
    return {"baseline": binding["baseline"], "cohort": {"seed": SEED},
        "common": {"repeats": 1 if stage.endswith("native") else 3},
        "native": {"budget_chars": [axes["native"]["budget_chars"]],
                   "tokenizers": axes["native"]["tokenizers"], "token_budgets": axes["native"]["token_budgets"]},
        "components": {"tokenizers": axes["native"]["tokenizers"], "token_budgets": axes["native"]["token_budgets"],
            "native_read_policy": "First repetition: read every mapped native top-five page in full. Metadata None slots earn no evidence, are not read, and are not replaced. Other engines need no extra native page read."}}


def mode(stage):
    return {"baseline": stage.startswith("baseline-"), "semantic": "semantic" in stage,
            "statistics": "statistics" in stage}


def vectors_digest(path):
    hasher = hashlib.sha256(b"semantic_vectors/page_id,ordinal,char_start,char_end,vector/v1\n")
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_vectors'").fetchone():
            return {"present": False}
        rows = size = 0
        revision, model = db.execute("SELECT revision,model_fingerprint FROM semantic_meta WHERE singleton=1").fetchone()
        for page, ordinal, start, end, vector in db.execute("SELECT page_id,ordinal,char_start,char_end,vector FROM semantic_vectors ORDER BY page_id,ordinal"):
            require(type(vector) is bytes and len(vector) == 384 * 4, "Unexpected persisted semantic vector")
            header = json.dumps([page, ordinal, start, end], ensure_ascii=False, separators=(",", ":")).encode()
            hasher.update(len(header).to_bytes(8, "big") + header + len(vector).to_bytes(8, "big") + vector)
            rows += 1
            size += len(vector)
    return {"present": True, "sha256": hasher.hexdigest(), "rows": rows, "vector_bytes": size,
            "revision": revision, "model_fingerprint": model}


def counters_for():
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    for counter in counters.values():
        require(counter.version == PACKAGES["tiktoken"], "Wrong tokenizer dependency")
        counter.count("readiness")
    return counters


def payload_hash(response):
    value = dict(response)
    require("latency_ms" in value, "Native response lacks latency field")
    value.pop("latency_ms")
    return reused.digest(value)


def statistics_state(book, enabled):
    if not enabled:
        return None
    from memory_book.scoped import state
    return state(book.db)


def native(args, plan, binding, data, bundle, report, ledger, resources):
    flags = mode(args.stage)
    expected = binding["baseline"] if flags["baseline"] else binding["candidate"]
    import_begin = time.perf_counter_ns()
    Book, source, provenance = reused.imported_book(args.source, expected)
    runtime_import_ms = (time.perf_counter_ns() - import_begin) / 1e6
    counters = counters_for()
    sources = original_turn_texts(data)
    started = time.perf_counter_ns()
    options = {"semantic_model_dir": args.model_dir} if flags["semantic"] else {}
    path = args.state / "native.db"
    with Book(path, max_page_chars=900, cache_size=0, **options) as book:
        begin = time.perf_counter_ns()
        for session in data.sessions:
            book.ingest(session)
        report["preparation"] = {"runtime_import_ms": runtime_import_ms,
                                 "source_ingestion_ms": (time.perf_counter_ns() - begin) / 1e6}
        if flags["semantic"]:
            report["preparation"]["semantic_index"] = book.build_semantic_index()
        report["preparation"]["engine_setup_wall_ms"] = (time.perf_counter_ns() - started) / 1e6
        documents = reused.documents_from(book)
        require(reused.digest(documents) == bundle["documents_sha256"], "Native pages differ from common corpus")
        originals, index, vectors = source_snapshot(book.db), indexed_content(book.db), vectors_digest(path)
        require(index == bundle["indexed_content"], "Native original/index projections differ from common corpus")
        pages = {doc["id"]: doc["text"] for doc in documents}
        report["metadata"] = {"source_provenance": provenance, "source_sha256_before": expected["source_sha256"],
            "semantic": flags["semantic"], "project_local_fts_statistics": flags["statistics"], "coverage": False,
            "comparison_scope": "Native Python recall including native context and exact token assembly; source ingest/index setup separate.",
            "originals_sha256": originals, "documents_sha256": reused.digest(documents),
            "cross_archive_source_boundary": "Canonical pages/addresses and the unchanged indexed_content projection must match. Fresh-ingest project created_at/updated_at and chapter/session updated_at are host-time metadata; the complete source_snapshot is instead checked before/after within each worker.",
            "indexed_content_before": index, "vectors_before": vectors, "stats": book.stats()}
        resources.set_phase("queries")
        adapted = old_shape_plan(plan, binding, args.stage)
        for config in reused.native_configurations(adapted):
            rows, samples = {}, []
            cases = list(data.queries)
            random.Random(SEED).shuffle(cases)
            for case in cases:
                seq = ledger.start(args.stage, config, 0, case.id)
                options = {"project_local_fts_statistics": True} if flags["statistics"] else {}
                begin = time.perf_counter_ns()
                response = book.recall(case.query, project=case.project, limit=5, use_cache=False,
                    coverage=False, semantic=flags["semantic"], **options, **config)
                elapsed = (time.perf_counter_ns() - begin) / 1e6
                row = reused.sample_score(case, response, sources, counters, config, bundle["diagnostics"], pages)
                row.update(payload_sha256=payload_hash(response), cache_error=bool(response["cache_hit"]),
                    policy_error=(bool(response.get("semantic", False)) != flags["semantic"]
                        or bool(response.get("project_local_fts_statistics", False)) != flags["statistics"]
                        or (flags["semantic"] and response.get("semantic_model_fingerprint") != MODEL_FINGERPRINT)),
                    result_limit_error=len(response["results"]) > 5)
                sample = {"id": case.id, "configuration": config, "repetition": 0, "elapsed_ms": elapsed,
                    "status": "ok", "row_sha256": reused.digest(row),
                    **{key: row[key] for key in ("payload_sha256", "context_sha256", "context_tokens", "complete", "evidence_ranks", *INVARIANTS)}}
                if flags["statistics"]:
                    sample["project_statistics_state"] = statistics_state(book, True)
                ledger.finish(seq, sample)
                report["timing_rows"].append(sample)
                rows[case.id] = row
                samples.append(sample)
            ordered = [rows[case.id] for case in data.queries]
            report["configurations"].append({**config, "metrics": summarize_rows(ordered),
                "by_group": reused.grouped_metrics(ordered), "query_results": ordered,
                "latency": latency_summary([sample["elapsed_ms"] for sample in samples]),
                "first_pass_latency": latency_summary([sample["elapsed_ms"] for sample in samples]),
                "repeat_pass_latency": latency_summary([]), "repeat_context_mismatches": 0,
                "invariants": {key: sum(int(row[key]) for row in ordered) for key in INVARIANTS}})
        resources.set_phase("finalization")
        report["metadata"].update(originals_unchanged=source_snapshot(book.db) == originals,
            indexed_content_after=indexed_content(book.db), vectors_after=vectors_digest(path), stats_after=book.stats(),
            project_statistics_state=statistics_state(book, flags["statistics"]))
        report["storage_before_close"] = storage(args.state, ("attempts.jsonl",))
    report["storage_after_close"] = storage(args.state, ("attempts.jsonl",))
    report["metadata"].update(source_sha256_after=engine_source_hash(source),
        source_unchanged=engine_source_hash(source) == expected["source_sha256"])
    report["validation"] = {"passed": True, "failures": []}


class BookComponent:
    def __init__(self, args, binding, bundle):
        self.flags = mode(args.stage)
        self.expected = binding["baseline"] if self.flags["baseline"] else binding["candidate"]
        Book, self.source, provenance = reused.imported_book(args.source, self.expected)
        self.path = args.state / "component.db"
        begin = time.perf_counter_ns()
        shutil.copyfile(args.frozen_db, self.path)
        copy_ms = (time.perf_counter_ns() - begin) / 1e6
        begin = time.perf_counter_ns()
        self.book = Book(self.path, max_page_chars=900, cache_size=0,
            **({"semantic_model_dir": args.model_dir} if self.flags["semantic"] else {}))
        self.metadata = {"source_provenance": provenance, "source_sha256": self.expected["source_sha256"],
            "book_open_ms": (time.perf_counter_ns() - begin) / 1e6, "frozen_database_copy_ms": copy_ms,
            "source_ingestion_ms": None, "semantic": self.flags["semantic"],
            "project_local_fts_statistics": self.flags["statistics"], "coverage": False,
            "setup_policy": "Copy the same baseline-ingested archive; Q2 builds its own measured index. Native stages separately measure fresh source ingestion.",
            "comparison_scope": "Supplied-page Book ranker including native hierarchy metadata and native context assembly.",
            "latency_scope": "In-process Python recall and context assembly; no bridge IPC."}
        try:
            require(reused.digest(reused.documents_from(self.book)) == bundle["documents_sha256"],
                    "Copied component pages differ from common corpus")
            self.originals = source_snapshot(self.book.db)
            self.index = indexed_content(self.book.db)
            require(self.originals == bundle["originals_sha256"] and self.index == bundle["indexed_content"],
                    "Copied source or lexical index differs from common corpus")
            require(vectors_digest(self.path) == bundle["vectors"], "Copied persisted vectors differ")
            if self.flags["semantic"]:
                self.metadata["semantic_index"] = self.book.build_semantic_index()
            self.vectors = vectors_digest(self.path)
            if self.flags["semantic"]:
                require(self.vectors == args.reference_vectors,
                        "Component Q2 vectors differ from native Q2; cannot attribute comparison to retrieval boundaries")
            self.metadata.update(originals_sha256=self.originals, indexed_content_before=self.index,
                                 documents_sha256=bundle["documents_sha256"], vectors_before=self.vectors, stats=self.book.stats())
        except BaseException:
            self.book.close()
            raise

    def search(self, query, project, limit):
        begin = time.perf_counter_ns()
        response = self.book.recall(query, project=project, limit=limit, budget_chars=100000,
            use_cache=False, coverage=False, semantic=self.flags["semantic"],
            **({"project_local_fts_statistics": True} if self.flags["statistics"] else {}))
        elapsed = (time.perf_counter_ns() - begin) / 1e6
        require(response["cache_hit"] is False and bool(response.get("semantic", False)) == self.flags["semantic"]
                and bool(response.get("project_local_fts_statistics", False)) == self.flags["statistics"],
                "Component Book cache or policy differs")
        if self.flags["semantic"]:
            require(response.get("semantic_model_fingerprint") == MODEL_FINGERPRINT, "Component semantic model differs")
        result = {"hit_ids": [item["id"] for item in response["results"]], "results": response["results"],
            "native_payload": response, "native_text": response["context"],
            "search_ms": elapsed, "bridge_ms": elapsed, "book_payload_sha256": payload_hash(response)}
        if self.flags["statistics"]:
            result["project_statistics_state"] = statistics_state(self.book, True)
        return result

    def close(self):
        try:
            self.metadata.update(stats_after=self.book.stats(), originals_unchanged=source_snapshot(self.book.db) == self.originals,
                indexed_content_after=indexed_content(self.book.db), vectors_after=vectors_digest(self.path),
                project_statistics_state=statistics_state(self.book, self.flags["statistics"]))
        finally:
            self.book.close()
        self.metadata.update(source_sha256_after=engine_source_hash(self.source),
                             source_unchanged=engine_source_hash(self.source) == self.expected["source_sha256"])


def component_engine(args, plan, binding, bundle):
    if args.stage.startswith(("baseline-", "candidate-")):
        return BookComponent(args, binding, bundle), args.state
    require(args.stage in {"claude-mem-fts", "ai-memory-hybrid", "billion-context"}, "Unknown external component")
    return reused.component_engine(args, old_shape_plan(plan, binding, args.stage), binding, bundle)


def component_costs(samples, read_policy):
    first = [row for row in samples if row["repetition"] == 0]
    result = {
        "native_search_latency": latency_summary([row["search_ms"] for row in samples]),
        "adapter_roundtrip_latency": latency_summary([row["bridge_ms"] for row in samples]),
        "first_pass_roundtrip_latency": latency_summary([row["bridge_ms"] for row in first]),
        "repeat_roundtrip_latency": latency_summary([row["bridge_ms"] for row in samples if row["repetition"] > 0]),
        "first_pass_search_plus_all_reads_latency": latency_summary([row["bridge_ms"] + row["read_ms"] for row in first]),
        "search_plus_all_reads_boundary": "Per-query first-pass adapter search roundtrip plus all declared read roundtrips, before percentiles. Excludes evaluator token counting and offline common packing.",
        "native_costs": {"queries": len(first), "read_policy": read_policy,
            "unmapped_native_hits": sum(row["unmapped_native_hits"] for row in first),
            "queries_with_unmapped_native_hits": sum(row["unmapped_native_hits"] > 0 for row in first),
            "mean_read_calls": statistics.fmean(row["read_calls"] for row in first),
            "mean_read_ms": statistics.fmean(row["read_ms"] for row in first),
            **{"mean_" + field: {name: statistics.fmean(row[field][name] for row in first) for name in ENCODINGS}
                if all(row[field] is not None for row in first) else None
                for field in ("search_payload_tokens", "search_content_tokens", "read_payload_tokens", "read_content_tokens")}}}
    return result


def component(args, plan, binding, data, bundle, report, ledger, resources):
    counters = counters_for()
    sources = original_turn_texts(data)
    documents = {doc["id"]: doc for doc in bundle["documents"]}
    begin = time.perf_counter_ns()
    engine, native_state = component_engine(args, plan, binding, bundle)
    report["preparation"] = {"engine_setup_wall_ms": (time.perf_counter_ns() - begin) / 1e6}
    responses, first_ids, repeat_changes = {}, {}, 0
    resources.set_phase("queries")
    try:
        for repetition in range(3):
            cases = list(data.queries)
            random.Random(SEED + 1009 * repetition).shuffle(cases)
            for case in cases:
                seq = ledger.start(args.stage, "search", repetition, case.id)
                response = engine.search(case.query, case.project, 5)
                ids, mapped, native_hashes = reused.component_hits(response, documents, case.project, args.stage)
                payload = canonical_json(response["native_payload"] if "native_payload" in response else response["results"])
                reads = []
                if args.stage == "ai-memory-hybrid" and repetition == 0:
                    for identity in mapped:
                        read = engine.read(identity)
                        require(not read["result"].get("truncated") and read["result"].get("body") == documents[identity]["text"],
                                "Native full read differs from the supplied page")
                        reads.append(read)
                read_payloads = [canonical_json(read["native_payload"] if "native_payload" in read else read["result"]) for read in reads]
                cost = {"id": case.id, "repetition": repetition, "status": "ok", "hit_ids": mapped,
                    "native_hit_ids": ids, "native_result_id_sha256": native_hashes,
                    "unmapped_native_hits": len(ids) - len(mapped), "payload_sha256": sha(payload.encode()),
                    "read_payload_sha256": [sha(value.encode()) for value in read_payloads],
                    "search_payload_tokens": {name: counter.count(payload) for name, counter in counters.items()},
                    "search_content_tokens": {name: counter.count(response["native_text"]) for name, counter in counters.items()}
                        if response.get("native_text") is not None else None,
                    "read_calls": len(reads), "read_ms": sum(read["read_ms"] for read in reads),
                    "read_payload_tokens": {name: sum(counter.count(value) for value in read_payloads) for name, counter in counters.items()},
                    "read_content_tokens": {name: sum(counter.count(read["native_text"] if read.get("native_text") is not None
                        else canonical_json(read["result"])) for read in reads) for name, counter in counters.items()},
                    "search_ms": response["search_ms"], "bridge_ms": response["bridge_ms"]}
                for key in ("book_payload_sha256", "project_statistics_state"):
                    if key in response:
                        cost[key] = response[key]
                ledger.finish(seq, cost)
                report["timing_rows"].append(cost)
                if repetition == 0:
                    responses[case.id] = shared_response(mapped, documents)
                    first_ids[case.id] = ids
                elif ids != first_ids[case.id]:
                    repeat_changes += 1
        resources.set_phase("finalization")
        report["storage_before_close"] = storage(native_state, ("attempts.jsonl",)) if native_state else {
            "regular_file_bytes": 0, "boundary": "Supplied-source search kernel retains an in-memory corpus; no persistent corpus state."}
    finally:
        engine.close()
        report["metadata"] = engine.metadata
    report["storage_after_close"] = storage(native_state, ("attempts.jsonl",)) if native_state else report["storage_before_close"]
    axes = plan["independent_validation"]["native"]
    for encoding, budget in itertools.product(axes["tokenizers"], axes["token_budgets"]):
        config = {"tokenizer": encoding, "budget_tokens": budget}
        rows, packing = [], []
        for case in data.queries:
            begin = time.perf_counter_ns()
            response = pack_whole_blocks(responses[case.id], budget, counters[encoding])
            elapsed = (time.perf_counter_ns() - begin) / 1e6
            row = reused.sample_score(case, response, sources, counters, config, bundle["diagnostics"])
            rows.append(row)
            packing.append({"id": case.id, "elapsed_ms": elapsed, "row_sha256": reused.digest(row)})
        report["configurations"].append({**config, "metrics": summarize_rows(rows), "by_group": reused.grouped_metrics(rows),
            "query_results": rows, "packing_samples": packing,
            "packing_latency": latency_summary([row["elapsed_ms"] for row in packing]),
            "invariants": {key: sum(int(row[key]) for row in rows) for key in reused.INVARIANTS}})
    report["repeat_hit_changes"] = repeat_changes
    report["repeat_hit_changes_boundary"] = "Changes in mapped supplied-page ID lists, including None positions. Original native result IDs are retained as SHA256 values; metadata identity changes within an unchanged None slot are not counted here."
    report["quality_boundary"] = "First response only, six offline whole-block projections. Every native top-five slot, including ai-memory metadata None, and all three search repetitions remain recorded. No extra diagnostic or replacement query."
    report.update(component_costs(report["timing_rows"], old_shape_plan(plan, binding, args.stage)["components"]["native_read_policy"]))
    report["validation"] = {"passed": True, "failures": []}


def export(args, plan, binding, data, report, resources):
    reused.export(args, old_shape_plan(plan, binding, "export"), binding, data, report, resources)
    bundle = json.loads(args.bundle.read_bytes())
    database = args.state / "frozen.db"
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        bundle["indexed_content"] = indexed_content(db)
    bundle["vectors"] = vectors_digest(database)
    require(bundle["vectors"] == {"present": False}, "Canonical lexical export unexpectedly contains vectors")
    reused.atomic(args.bundle, bundle)
    report["frozen_corpus"] = {key: value for key, value in bundle.items() if key not in {"documents", "diagnostics"}}
    report.update(private_bundle_sha256=file_sha(args.bundle), frozen_database_sha256=file_sha(database))


def host_record():
    boot = Path("/proc/sys/kernel/random/boot_id")
    require(platform.system() == "Linux" and boot.is_file(), "Registered resource measurements require Linux boot identity")
    identity = {"node": platform.node(), "boot_id": boot.read_text().strip(),
                "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    return {**identity, "id": reused.digest(identity), "python": platform.python_version(),
            "platform": platform.platform(), "sqlite": sqlite3.sqlite_version, "logical_cpus": os.cpu_count(),
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES}}


def public_paths(prefix):
    return [Path(str(prefix) + suffix) for suffix in (".json.gz", ".summary.json", ".attempts.jsonl.gz")]


def summary_of(report, raw_sha):
    result = reused.summary_of(report, raw_sha)
    for config in result.get("configurations", []):
        config.pop("packing_samples", None)
    return result


def save_ledger(state, prefix):
    """Also callable by a controller after a killed worker; no private data files."""
    source = Path(state) / "attempts.jsonl"
    if not source.is_file() or source.is_symlink():
        return None
    raw = source.read_bytes()
    # A final partial write is retained verbatim, not fabricated into a finish.
    output = public_paths(prefix)[2]
    output.parent.mkdir(parents=True, exist_ok=True)
    compressed = gzip.compress(raw, mtime=0)
    if output.exists():
        require(output.read_bytes() == compressed, "Never replace an already preserved ledger")
    else:
        temporary = output.with_name(output.name + ".partial")
        temporary.write_bytes(compressed)
        temporary.replace(output)
    return {"path": str(output), "sha256": sha(compressed), "raw_sha256": sha(raw), "raw_bytes": len(raw)}


def write_report(report, prefix):
    raw = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    compressed, summary, _ = public_paths(prefix)
    compressed.parent.mkdir(parents=True, exist_ok=True)
    temporary = compressed.with_name(compressed.name + ".partial")
    temporary.write_bytes(gzip.compress(raw, mtime=0))
    temporary.replace(compressed)
    reused.atomic(summary, summary_of(report, sha(raw)))


def read_report(prefix):
    compressed, summary, ledger = public_paths(prefix)
    raw = gzip.decompress(compressed.read_bytes())
    report = json.loads(raw)
    require(json.loads(summary.read_bytes()) == summary_of(report, sha(raw)), "Raw/summary projection differs")
    ledger_raw = gzip.decompress(ledger.read_bytes())
    require(sha(ledger_raw) == report["ledger_sha256"], "Preserved ledger bytes differ")
    require([json.loads(line) for line in ledger_raw.splitlines()] == report["attempt_states"], "Raw ledger events differ")
    return report


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def verify_report(report, plan, binding, query_ids):
    stage = report["stage"]
    require(stage in stages(binding) and report["status"] == "completed"
            and report["validation"] == {"passed": True, "failures": []}, "Stage is incomplete or failed")
    adapted = old_shape_plan(plan, binding, stage)
    verify_samples(report, adapted, query_ids)
    verify_configurations(report, adapted, query_ids)
    expected_order = []
    if stage != "export":
        configs = reused.native_configurations(adapted) if stage.endswith("native") else ["search"]
        for config in configs:
            for repetition in range(adapted["common"]["repeats"]):
                identities = list(query_ids)
                random.Random(SEED + 1009 * repetition).shuffle(identities)
                expected_order.extend((config, repetition, identity) for identity in identities)
    require([(row["configuration"], row["repetition"], row["id"]) for row in report["attempt_states"]
             if row["event"] == "started"] == expected_order, "Registered query/configuration order changed")
    for config in report["configurations"]:
        rows = config["query_results"]
        require([row["id"] for row in rows] == list(query_ids), "Published query order changed")
        for row in rows:
            ranks = row["evidence_ranks"]
            found = [rank for rank in ranks if rank is not None]
            require(row["required_evidence"] == len(ranks) and row["matched_evidence"] == len(found)
                    and row["complete"] == (bool(ranks) and len(found) == len(ranks))
                    and row["reciprocal_rank"] == (1 / min(found) if found else 0)
                    and all(type(rank) is int and 1 <= rank <= 5 for rank in found), "Evidence counts differ from ranks")
        if stage.endswith("native"):
            require(all(not row[key] for row in rows for key in INVARIANTS), "Native invariant failed")
            require(all(isinstance(row["payload_sha256"], str) and len(row["payload_sha256"]) == 64 for row in rows),
                    "Full native payload hash missing")
            mapped = {row["id"]: row for row in rows}
            for sample in report["timing_rows"]:
                if sample["configuration"] == {key: config[key] for key in ("budget_chars", "tokenizer", "budget_tokens")}:
                    require(sample["payload_sha256"] == mapped[sample["id"]]["payload_sha256"], "Native payload ledger differs")
        else:
            packing = config["packing_samples"]
            require([row["id"] for row in packing] == list(query_ids)
                    and all(finite(row["elapsed_ms"]) for row in packing)
                    and [row["row_sha256"] for row in packing] == [reused.digest(row) for row in rows]
                    and config["packing_latency"] == latency_summary([row["elapsed_ms"] for row in packing]),
                    "Offline packing samples or summary differ")
    if stage == "export":
        require(report["source_unchanged"] is True
                and report["frozen_corpus"]["source_provenance"]["git_commit"] == binding["baseline"]["commit"]
                and report["frozen_corpus"]["source_sha256"] == binding["baseline"]["source_sha256"],
                "Export source provenance differs")
    elif stage.startswith(("baseline-", "candidate-")):
        flags = mode(stage)
        expected = binding["baseline"] if flags["baseline"] else binding["candidate"]
        metadata = report["metadata"]
        require(metadata["source_provenance"]["git_commit"] == expected["commit"]
                and metadata.get("source_sha256_before", metadata.get("source_sha256")) == expected["source_sha256"]
                and metadata["source_sha256_after"] == expected["source_sha256"]
                and metadata["source_unchanged"] is True and metadata["originals_unchanged"] is True
                and metadata["indexed_content_before"] == metadata["indexed_content_after"]
                and metadata["vectors_before"] == metadata["vectors_after"], "Book source/index/vector provenance differs")
        require(metadata["indexed_content_before"] == report["frozen_corpus"]["indexed_content"]
                and metadata["documents_sha256"] == report["frozen_corpus"]["documents_sha256"],
                "Book stable source/index projection differs from canonical corpus")
        if not stage.endswith("native"):
            require(metadata["originals_sha256"] == report["frozen_corpus"]["originals_sha256"],
                    "Copied component source metadata differs from canonical corpus")
        require(metadata["semantic"] == flags["semantic"]
                and metadata["project_local_fts_statistics"] == flags["statistics"] and metadata["coverage"] is False,
                "Book policy metadata differs")
        if flags["semantic"]:
            index = report["preparation"].get("semantic_index", metadata.get("semantic_index"))
            require(index["model_fingerprint"] == MODEL_FINGERPRINT and index["inference_threads"] == 1
                    and metadata["vectors_before"]["model_fingerprint"] == MODEL_FINGERPRINT,
                    "Semantic model, thread count or persisted vector identity differs")
        else:
            require(metadata["vectors_before"] == {"present": False}, "Lexical path unexpectedly contains vectors")
    if stage != "export" and not stage.endswith("native"):
        expected_costs = component_costs(report["timing_rows"], adapted["components"]["native_read_policy"])
        require(all(report[key] == value for key, value in expected_costs.items()), "Native token/read cost aggregation differs")
        first = {row["id"]: row["native_hit_ids"] for row in report["timing_rows"] if row["repetition"] == 0}
        require(report["repeat_hit_changes"] == sum(row["native_hit_ids"] != first[row["id"]]
            for row in report["timing_rows"] if row["repetition"] > 0), "Repeated native hit changes were hidden")
        for row in report["timing_rows"]:
            for field in ("search_payload_tokens", "search_content_tokens", "read_payload_tokens", "read_content_tokens"):
                if row[field] is not None:
                    require(set(row[field]) == set(ENCODINGS)
                            and all(type(value) is int and value >= 0 for value in row[field].values()), "Invalid native token cost")
    upstream = {"claude-mem-fts": "claude-mem", "ai-memory-hybrid": "ai-memory", "billion-context": "billion-context"}
    if stage in upstream:
        metadata = report["metadata"]
        lock = json.loads((ROOT / binding["upstream_locks"][upstream[stage]]).read_bytes())
        require(metadata["commit"] == lock["commit"] and not metadata.get("native_process_exit_code", 0),
                "Measured upstream source/exit differs")
        if stage == "claude-mem-fts":
            require(metadata["source_unchanged"] is True, "claude-mem source changed")
        elif stage == "ai-memory-hybrid":
            require(metadata["binary_sha256"] == lock["binary_sha256"] and metadata["embedding_provider"] == "local"
                    and metadata["embedding_model"]["files"] == lock["embedding_model"]["files"], "ai-memory native binary/model differs")
    resources = report["resources"]
    require(resources["sampling_interval_ms"] == 20 and resources["samples"].get("setup", 0) > 0
            and (stage == "export" or resources["samples"].get("queries", 0) > 0), "Missing live resource measurements")


def worker(args):
    require(os.environ.get("ORT_DISABLE_TELEMETRY") == "1", "Disable ORT telemetry before process launch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT", "1") == "1", "No implicit Actions rerun")
    plan, binding = frozen_inputs(args.binding)
    require(args.stage in stages(binding) and args.output.name == args.stage, "Unregistered stage/output name")
    require(not args.state.exists() and not any(path.exists() for path in public_paths(args.output)),
            "Never replay or overwrite an existing worker")
    host = host_record()
    require(host["id"] == args.host_id and host["packages"] == PACKAGES, "Worker host/dependency binding differs")
    verify_model(args.model_dir, binding["model"]["identity"])
    require_committed(args.manifest)
    args.state.mkdir(parents=True)
    ledger = reused.Ledger(args.state / "attempts.jsonl")
    resources = Resources()
    report = {"schema_version": 1, "evaluator": VERSION, "protocol": plan["protocol"], "stage": args.stage,
        "status": "running", "host": host, "host_id": host["id"], "started_at": reused.now(),
        "source_commit": git("rev-parse", "HEAD").decode().strip(), "plan_sha256": file_sha(PLAN),
        "binding_sha256": file_sha(args.binding), "cohort_manifest_sha256": file_sha(args.manifest),
        "evaluator_files": binding["evaluator_files"], "ort_disable_telemetry": "1",
        "configured_generative_model_calls": 0, "configurations": [], "timing_rows": [],
        "validation": {"passed": False, "failures": []}}
    data = None
    try:
        from scripts.round3_data import load
        data = load(args.data, args.binding, args.manifest)
        report["dataset"] = data.description()
        if args.stage == "export":
            export(args, plan, binding, data, report, resources)
        else:
            exported = read_report(args.output.parent / "export")
            require(exported["host_id"] == host["id"] and exported["binding_sha256"] == report["binding_sha256"]
                    and exported["cohort_manifest_sha256"] == report["cohort_manifest_sha256"], "Export belongs to another host/protocol")
            verify_report(exported, plan, binding, [case.id for case in data.queries])
            require(file_sha(args.bundle) == exported["private_bundle_sha256"]
                    and file_sha(args.frozen_db) == exported["frozen_database_sha256"], "Canonical private artifacts changed")
            bundle = json.loads(args.bundle.read_bytes())
            require(bundle["dataset"]["sha256"] == data.fingerprint
                    and reused.digest(bundle["documents"]) == bundle["documents_sha256"]
                    and reused.digest(bundle["diagnostics"]) == bundle["diagnostics_sha256"], "Frozen corpus digest differs")
            report["frozen_corpus"] = exported["frozen_corpus"]
            if args.stage.endswith("native"):
                native(args, plan, binding, data, bundle, report, ledger, resources)
            else:
                if args.stage == "candidate-semantic-component":
                    prior = read_report(args.output.parent / "candidate-semantic-native")
                    verify_report(prior, plan, binding, [case.id for case in data.queries])
                    require(prior["host_id"] == host["id"] and prior["binding_sha256"] == report["binding_sha256"],
                            "Native Q2 index reference belongs to another run")
                    args.reference_vectors = prior["metadata"]["vectors_after"]
                component(args, plan, binding, data, bundle, report, ledger, resources)
        require(frozen_inputs(args.binding)[1] == binding, "Evaluator binding changed during worker")
        verify_model(args.model_dir, binding["model"]["identity"])
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed-incomplete", validation={"passed": False,
            "failures": [{"check": "stage_exception", "error_type": type(error).__name__}]})
    finally:
        ledger.close()
        report.update(finished_at=reused.now(), resources=resources.close(),
            ledger_sha256=file_sha(args.state / "attempts.jsonl"), attempts_started=ledger.started,
            attempts_finished=ledger.finished,
            attempt_states=[json.loads(line) for line in (args.state / "attempts.jsonl").read_text().splitlines()])
        if report["status"] == "completed":
            try:
                verify_report(report, plan, binding, [case.id for case in data.queries])
            except Exception as error:
                report.update(status="failed-incomplete", validation={"passed": False,
                    "failures": [{"check": "strict_stage_assessment", "error_type": type(error).__name__}]})
        save_ledger(args.state, args.output)
        write_report(report, args.output)
    print(json.dumps({"stage": args.stage, "status": report["status"], "validation": report["validation"],
                      "attempts_started": ledger.started, "attempts_finished": ledger.finished}))
    return 0 if report["status"] == "completed" else 2


def comparisons(before, after):
    values = []
    for old, new in zip(before["configurations"], after["configurations"], strict=True):
        axis = {key: new[key] for key in ("budget_chars", "tokenizer", "budget_tokens") if key in new}
        require(axis == {key: old[key] for key in axis}, "Paired configuration axes differ")
        values.append({**axis, "before": old["metrics"], "after": new["metrics"],
            "by_group": {name: {"before": old["by_group"].get(name), "after": new["by_group"].get(name)}
                         for name in sorted(set(old["by_group"]) | set(new["by_group"]))},
            "unsupported_before": sum(not row["answerable"] and row["nonempty"] for row in old["query_results"]),
            "unsupported_after": sum(not row["answerable"] and row["nonempty"] for row in new["query_results"]),
            **paired_changes(old["query_results"], new["query_results"])})
    return values


def statistics_gate(cells):
    losses = []
    require(len(cells) == 6, "Statistics qualification requires all six native cells")
    for cell in cells:
        axis = {key: cell[key] for key in ("budget_chars", "tokenizer", "budget_tokens")}
        for metric in ("complete_evidence_rate", "evidence_recall"):
            if cell["after"][metric] < cell["before"][metric]:
                losses.append({**axis, "group": "all", "metric": metric,
                               "before": cell["before"][metric], "after": cell["after"][metric]})
        if cell["unsupported_after"] > cell["unsupported_before"]:
            losses.append({**axis, "group": "unsupported", "metric": "nonempty_count",
                           "before": cell["unsupported_before"], "after": cell["unsupported_after"]})
        if cell["budget_tokens"] == 512:
            for name in PRIMARY_GROUPS:
                pair = cell["by_group"].get(name)
                if pair is None or pair["before"] is None or pair["before"]["queries"] < 10:
                    continue
                require(pair["after"] is not None and pair["after"]["queries"] == pair["before"]["queries"],
                        "Primary diagnostic denominator changed")
                for metric in ("complete_evidence_rate", "evidence_recall"):
                    if pair["after"][metric] < pair["before"][metric]:
                        losses.append({**axis, "group": name, "metric": metric,
                            "before": pair["before"][metric], "after": pair["after"][metric]})
    return {"status": "qualified" if not losses else "rejected", "qualified": not losses,
            "losses": losses, "individual_zero_loss_required": False,
            "boundary": "Registered native aggregate/group gate; every individual gain/loss and all smaller groups remain in comparisons."}


def default_equivalence(reports):
    native_differences, component_differences = [], []
    old, new = reports["baseline-native"], reports["candidate-native"]
    count = 0
    for before, after in zip(old["configurations"], new["configurations"], strict=True):
        axis = {key: before[key] for key in ("budget_chars", "tokenizer", "budget_tokens")}
        require(axis == {key: after[key] for key in axis}, "Default native axes differ")
        for left, right in zip(before["query_results"], after["query_results"], strict=True):
            require(left["id"] == right["id"], "Default native sample order differs")
            count += 1
            if left["payload_sha256"] != right["payload_sha256"]:
                native_differences.append({**axis, "id": left["id"], "before": left["payload_sha256"], "after": right["payload_sha256"]})
    left = {(row["id"], row["repetition"]): row["book_payload_sha256"]
            for row in reports["baseline-component"]["timing_rows"]}
    right = {(row["id"], row["repetition"]): row["book_payload_sha256"]
             for row in reports["candidate-component"]["timing_rows"]}
    require(left.keys() == right.keys(), "Default component sample axes differ")
    for (identity, repetition), value in left.items():
        if value != right[(identity, repetition)]:
            component_differences.append({"id": identity, "repetition": repetition, "before": value,
                                          "after": right[(identity, repetition)]})
    return {"passed": not native_differences and not component_differences, "native_pairs": count,
        "native_differences": native_differences, "component_pairs": len(left), "component_differences": component_differences,
        "boundary": "Complete native JSON SHA256 after removing latency_ms only, at registered native caps and at the component ranker's 100000-character cap."}


def markdown(assessment, reports):
    if not assessment["validation"]["passed"]:
        return "# Round three comparison: incomplete or failed\n\nNo complete comparison may be claimed.\n\n" + "\n".join(
            "- " + row["check"] for row in assessment["validation"]["failures"]) + "\n"
    lines = ["# Round three: native APIs and supplied-page components", "",
        "Candidate, evaluator, dependency/model and upstream source identities were committed before selecting these 256 IDs. "
        "The selection excludes both earlier Hotpot128 and round-two Hotpot256. It is another selection from the same HotpotQA source, not a new domain. "
        "These measurements assess returned source evidence, not generated-answer accuracy or a complete write/summarize/generate workflow.", "",
        "Integrity passed for every registered query, budget and repetition. Optional Q2 gains and losses are retained; integrity does not imply a quality improvement.", "",
        "## Native API", "", "| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage.endswith("native"):
            for c in report["configurations"]:
                m, t = c["metrics"], c["latency"]
                lines.append(f"| {stage} | {c['tokenizer']} | {c['budget_tokens']} | {m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | {m['mean_context_tokens'][c['tokenizer']]:.1f} | {t['p50_ms']:.3f} | {t['p95_ms']:.3f} |")
    lines += ["", "Native calls use 8000 characters, top five, no result cache and one repetition. The independent ABBA old-data performance experiment supplies the release performance gate; these native measurements are not a substitute for that gate.", "",
        "## Common whole-block projections", "", "| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Packed-context MRR | Context tokens |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage != "export" and not stage.endswith("native"):
            for c in report["configurations"]:
                m = c["metrics"]
                lines.append(f"| {stage} | {c['tokenizer']} | {c['budget_tokens']} | {m['evidence_recall']:.2%} | {m['complete_evidence_rate']:.2%} | {m['mrr']:.4f} | {m['mean_context_tokens'][c['tokenizer']]:.1f} |")
    lines += ["", "The six projections reuse the first native response. Three native search repetitions remain in raw ledgers; there are no extra diagnostic or replacement searches. "
        "ai-memory metadata hits consume original top-five slots, retain their native payload cost, and earn zero evidence credit. "
        "Packed-context MRR measures evidence order after metadata or oversized blocks are omitted; raw native positions remain recorded.", "",
        "## Measured component boundaries", "", "| Component | Search adapter p50/p95 ms | First search + all reads p50/p95 ms | Search payload cl100k/o200k | Read payload cl100k/o200k | Reads/query |",
        "|---|---:|---:|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage != "export" and not stage.endswith("native"):
            t, a, costs = report["adapter_roundtrip_latency"], report["first_pass_search_plus_all_reads_latency"], report["native_costs"]
            search, reads = costs["mean_search_payload_tokens"], costs["mean_read_payload_tokens"]
            lines.append(f"| {stage} | {t['p50_ms']:.3f}/{t['p95_ms']:.3f} | {a['p50_ms']:.3f}/{a['p95_ms']:.3f} | {search['cl100k_base']:.1f}/{search['o200k_base']:.1f} | {reads['cl100k_base']:.1f}/{reads['o200k_base']:.1f} | {costs['mean_read_calls']:.2f} |")
    lines += ["", "Search plus all reads sums each query's roundtrips before computing percentiles. "
        "Book is in-process Python including context assembly; claude-mem uses native SQLite/Bun; ai-memory uses local hybrid HTTP/MCP; billion-context uses its supplied-source search kernel/Node. "
        "These are distinct component boundaries, so no whole-product speed ratio follows. Native content, native payload and common packed context are separate token surfaces.", "",
        "## Setup, RSS and state", "", "| Mode | Setup wall ms | Setup RSS MiB | Query RSS MiB | Native state bytes |",
        "|---|---:|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage == "export":
            continue
        peak, state = report["resources"]["sampled_process_tree_peak_rss_bytes"], report["storage_before_close"]
        lines.append(f"| {stage} | {report['preparation']['engine_setup_wall_ms']:.3f} | {peak['setup']/1048576:.2f} | {peak['queries']/1048576:.2f} | {state['regular_file_bytes']} |")
    lines += ["", "Native Book stages separately record fresh ingestion and optional model/index construction. Component Book stages copy one canonical archive and measure their own setup/index costs. "
        "Q2's persisted native/component index-vector digests match; this does not assert separately measured query-embedding identity. "
        "RSS is sampled worker-plus-descendants every 20 ms, includes evaluator/data memory, can double-count shared pages, and provides observed lower bounds. "
        "Database main/WAL/SHM, live statistics and optional TEMP-index costs remain in raw summaries; symlinked model caches are excluded from native state bytes.", "",
        "## Low-overlap and multi-paragraph evidence", "", "| Mode | Group at 512 cl100k | Questions | Complete evidence | Evidence recall |",
        "|---|---|---:|---:|---:|"]
    for stage, report in reports.items():
        if stage == "export":
            continue
        c = next(c for c in report["configurations"] if c["tokenizer"] == "cl100k_base" and c["budget_tokens"] == 512)
        for group in PRIMARY_GROUPS:
            m = c["by_group"].get(group)
            if m:
                lines.append(f"| {stage} | {group} | {m['queries']} | {m['complete_evidence_rate']:.2%} | {m['evidence_recall']:.2%} |")
            else:
                lines.append(f"| {stage} | {group} | 0 | n/a | n/a |")
    lines += ["", "Cross-session/chapter labels arise from mapping supplied encyclopedia paragraphs to sessions/chapters; they do not measure private conversational transfer. "
        "Small diagnostic groups are retained and their sample sizes limit conclusions. All selected questions are answerable, so abstention and hallucination rates are not measured.", "",
        f"Run: `{assessment['run_id']}`. Native calls: {assessment['native_calls']}; native component searches: {assessment['component_search_calls']}. "
        f"Complete default payload equivalence: `{assessment['default_payload_equivalence']['passed']}`. "
        f"Optional project-statistics decision: `{assessment['project_statistics_gate']['status']}`.", "",
        "Every paired annotation/query gain and loss, all budget/tokenizer groups, repeat changes, native read costs and source hashes remain in the machine-readable assessment and stage reports. "
        "After first scoring these IDs are regression data. HotpotQA source is CC BY-SA 4.0; original questions, answers and passages are downloaded separately and are not published here."]
    return "\n".join(lines) + "\n"


def assess(checkpoint_path, binding_path=BINDING, manifest_path=MANIFEST, *, verify_existing=False):
    plan, binding = frozen_inputs(binding_path)
    require_committed(manifest_path)
    manifest = json.loads(Path(manifest_path).read_bytes())
    checkpoint = json.loads(Path(checkpoint_path).read_bytes())
    directory = ROOT / checkpoint["result_directory"]
    require(directory.resolve().is_relative_to((ROOT / "benchmarks/results").resolve())
            and directory.name.startswith("round3-comparison-"), "Assessment output directory is outside this experiment")
    output = directory / "assessment.json"
    require(output.exists() if verify_existing else not output.exists(),
            "Use --verify-existing for a read-only audit; never overwrite a prior assessment")
    expected_stages = stages(binding)
    reports, issues = {}, []
    try:
        require(checkpoint["plan_sha256"] == file_sha(PLAN) and checkpoint["binding_sha256"] == file_sha(binding_path)
                and checkpoint["cohort_manifest_sha256"] == file_sha(manifest_path)
                and manifest["binding_sha256"] == file_sha(binding_path), "Checkpoint/selection binding differs")
        require(list(checkpoint["stages"]) == expected_stages and manifest["expected_queries"] == 256,
                "Missing or extra registered stage/query")
        for stage in expected_stages:
            record = checkpoint["stages"][stage]
            paths = public_paths(directory / stage)
            require(record["status"] == "completed" and record["exit_code"] == 0
                    and record["outputs"] == {str(path.relative_to(ROOT)): file_sha(path) for path in paths},
                    "Incomplete stage or checkpoint file hashes: " + stage)
            report = read_report(directory / stage)
            require(report["stage"] == stage and report["host_id"] == checkpoint["host"]["id"]
                    and report["source_commit"] == checkpoint["source_commit"]
                    and report["plan_sha256"] == checkpoint["plan_sha256"]
                    and report["binding_sha256"] == checkpoint["binding_sha256"]
                    and report["cohort_manifest_sha256"] == checkpoint["cohort_manifest_sha256"]
                    and report["dataset"]["sha256"] == manifest["dataset_sha256"]
                    and report["dataset"]["queries"] == 256 and report["evaluator_files"] == binding["evaluator_files"]
                    and report["configured_generative_model_calls"] == 0 and report["ort_disable_telemetry"] == "1",
                    "Stage source/host/data identity differs: " + stage)
            verify_report(report, plan, binding, manifest["selected_ids"])
            require(all(c["metrics"]["required_evidence"] == manifest["required_evidence"]
                    and c["metrics"]["answerable_queries"] == 256 for c in report["configurations"]),
                    "Evidence/answerable denominator changed")
            if stage != "export":
                require(report["frozen_corpus"] == reports["export"]["frozen_corpus"], "Supplied corpus differs between engines")
            reports[stage] = report
        require(reports["candidate-semantic-native"]["metadata"]["vectors_after"]
                == reports["candidate-semantic-component"]["metadata"]["vectors_after"], "Q2 persisted indexes differ")
        equivalence = default_equivalence(reports)
        require(equivalence["passed"], "Default complete lexical payload changed")
    except Exception as error:
        issues.append({"check": str(error) if isinstance(error, ValueError) else "Missing/invalid stage artifact: " + type(error).__name__})
    assessment = {"schema_version": 1, "evaluator": VERSION, "run_id": checkpoint["run_id"],
        "source_commit": checkpoint["source_commit"], "host": checkpoint["host"],
        "plan_sha256": file_sha(PLAN), "binding_sha256": file_sha(binding_path),
        "cohort_manifest_sha256": file_sha(manifest_path), "dataset_sha256": manifest["dataset_sha256"],
        "selected_ids_sha256": manifest["selected_ids_sha256"], "required_evidence": manifest["required_evidence"],
        "expected_stages": expected_stages, "verified_stages": list(reports),
        "validation": {"passed": not issues, "failures": issues}, "status": "failed-incomplete"}
    if not issues:
        assessment.update(status="complete-verified", default_payload_equivalence=equivalence,
            native_calls=sum(len(report["timing_rows"]) for stage, report in reports.items() if stage.endswith("native")),
            component_search_calls=sum(len(report["timing_rows"]) for stage, report in reports.items()
                if stage != "export" and not stage.endswith("native")),
            q2_native_changes=comparisons(reports["candidate-native"], reports["candidate-semantic-native"]),
            q2_component_changes=comparisons(reports["candidate-component"], reports["candidate-semantic-component"]),
            project_statistics_gate={"status": "not-included", "qualified": None})
        if binding["optional_project_statistics"]:
            assessment["project_statistics_native_changes"] = comparisons(reports["candidate-native"], reports["candidate-statistics-native"])
            assessment["project_statistics_component_changes"] = comparisons(reports["candidate-component"], reports["candidate-statistics-component"])
            assessment["project_statistics_gate"] = statistics_gate(assessment["project_statistics_native_changes"])
            if not assessment["project_statistics_gate"]["qualified"]:
                assessment["status"] = "complete-with-rejected-optional-quality"
    rendered = markdown(assessment, reports)
    if verify_existing:
        require(json.loads(output.read_bytes()) == assessment and (directory / "report.md").read_text() == rendered,
                "Published assessment/Markdown differ from strict raw recomputation")
    else:
        reused.atomic(output, assessment)
        (directory / "report.md").write_text(rendered)
    return assessment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("bind")
    p.add_argument("--baseline-src", type=Path, required=True)
    p.add_argument("--candidate-src", type=Path, required=True)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--statistics-gate", type=Path)
    p.add_argument("--extra-evaluator", action="append")
    p.add_argument("--output", type=Path, default=BINDING)
    p = commands.add_parser("worker")
    p.add_argument("--stage", required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--binding", type=Path, default=BINDING)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--frozen-db", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--host-id", required=True)
    p = commands.add_parser("audit")
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--binding", type=Path, default=BINDING)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--verify-existing", action="store_true")
    commands.add_parser("host")
    args = parser.parse_args(argv)
    if args.command == "bind":
        bind(args)
        return 0
    if args.command == "host":
        print(json.dumps(host_record()))
        return 0
    if args.command == "worker":
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        return worker(args)
    assessment = assess(args.checkpoint, args.binding, args.manifest, verify_existing=args.verify_existing)
    print(json.dumps({"status": assessment["status"], "validation": assessment["validation"]}))
    return 0 if assessment["status"] == "complete-verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
