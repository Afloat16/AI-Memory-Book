"""One frozen round-two engine stage; source text never enters public reports."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import statistics
import sys
import time

from benchmarks import round2_data
from benchmarks.component_eval import canonical_json, evidence_attainability, shared_response
from benchmarks.native_budget_eval import block_ids, source_errors
from benchmarks.round2_resources import Resources, storage
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.semantic_eval import diagnostics, page_projection_errors, source_snapshot
from benchmarks.token_compare import (ENCODINGS, TokenCounter, checkout_provenance,
    latency_summary, pack_whole_blocks, score_row, summarize_rows)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/round2_plan.json"
BINDING = ROOT / "benchmarks/round2_candidate.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def evaluator_sources(root=ROOT):
    paths = list((root / "benchmarks").glob("*.py"))
    paths += [path for path in (root / "benchmarks/competitors").iterdir()
              if path.suffix in {".py", ".mjs", ".ts", ".json"}]
    paths += [root / name for name in (
        "scripts/run_round2_validation.py", "scripts/summarize_round2_validation.py",
        ".github/workflows/round2-validation.yml", "benchmarks/round2_plan.json",
        "benchmarks/round2_hotpot256_manifest.json", "benchmarks/hotpot_manifest.json",
        "benchmarks/experiments/semantic-local-plan.json")]
    return {str(path.relative_to(root)): sha(path) for path in sorted(paths)}


def stages(plan, binding):
    result = ["export", *plan["native"]["engines"], *plan["components"]["engines"]]
    if binding["optional_semantic"]:
        result += [plan["native"]["optional_engine"], plan["components"]["optional_engine"]]
    return result


def frozen_inputs():
    plan = json.loads(PLAN.read_bytes())
    binding = json.loads(BINDING.read_bytes())
    import subprocess
    names = [str(path.relative_to(ROOT)) for path in (PLAN, BINDING, round2_data.MANIFEST)]
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", *names], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *names], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if (binding.get("status") != "frozen-before-scoring"
            or type(binding.get("optional_semantic")) is not bool
            or binding.get("plan_sha256") != sha(PLAN)
            or binding.get("cohort_manifest_sha256") != sha(round2_data.MANIFEST)
            or binding.get("evaluator_sha256") != evaluator_sources()):
        raise ValueError("A committed, unchanged candidate and evaluator binding is required")
    return plan, binding


def imported_book(source, expected):
    sys.path.insert(0, str(source.resolve()))
    import memory_book
    from memory_book import MemoryBook
    actual = Path(memory_book.__file__).resolve().parent
    provenance = checkout_provenance(actual)
    if (actual != source.resolve() / "memory_book"
            or engine_source_hash(actual) != expected["source_sha256"]
            or provenance["git_commit"] != expected["commit"]
            or provenance["commit_identifies_source"] is not True):
        raise ValueError("Imported runtime differs from its committed source pin")
    return MemoryBook, actual, provenance


def documents_from(book):
    documents = []
    for row in book.db.execute("SELECT id,project_id FROM pages ORDER BY id"):
        page = book.read(row["id"], limit=100000)
        if page["next_offset"] is not None:
            raise ValueError("A supplied page cannot be read in full")
        documents.append({"id": page["id"], "project": row["project_id"], "title": page["title"],
            "text": page["content"], "source_refs": page["source_refs"],
            "breadcrumb": page["breadcrumb"], "created_at": page["created_at"]})
    return documents


def groups_for(data, book):
    chapters = [(row["project_id"], row["id"], row["chapter_id"])
                for row in book.db.execute("SELECT project_id,id,chapter_id FROM sessions")]
    return {case.id: diagnostics(case, chapters) for case in data.queries}


def grouped_metrics(rows):
    grouped = defaultdict(list)
    for row in rows:
        for group in row["diagnostic_groups"]:
            grouped[group].append(row)
    return {group: summarize_rows(values) for group, values in sorted(grouped.items())}


def native_configurations(plan):
    return [{"budget_chars": chars, "tokenizer": encoding, "budget_tokens": tokens}
            for chars, encoding, tokens in itertools.product(plan["native"]["budget_chars"],
                plan["native"]["tokenizers"], plan["native"]["token_budgets"])]


def sample_score(case, response, sources, counters, config, groups, pages=None):
    row = score_row(case, response, sources, counters, public=True)
    row.update(groups[case.id], context_sha256=hashlib.sha256(response["context"].encode()).hexdigest(),
        block_hashes=block_ids(response),
        token_budget_violation=row["context_tokens"][config["tokenizer"]] > config["budget_tokens"],
        source_span_errors=source_errors(response, sources),
        scope_errors=sum(item["breadcrumb"][0]["id"] != case.project for item in response["results"]),
        page_projection_errors=page_projection_errors(response, pages) if pages is not None else 0,
        token_metadata_error=any((response.get("context_tokens") != row["context_tokens"][config["tokenizer"]],
            response.get("tokenizer") != config["tokenizer"], response.get("budget_tokens") != config["budget_tokens"],
            response.get("tokenizer_version") != "0.12.0")) if pages is not None else False)
    return row


INVARIANTS = ("token_budget_violation", "budget_violation", "source_span_errors", "scope_errors",
              "page_projection_errors", "token_metadata_error")


class Ledger:
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf-8")
        self.started = self.finished = 0

    def append(self, value):
        self.stream.write(canonical_json(value) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def start(self, stage, config, repetition, query_id):
        self.started += 1
        value = {"event": "started", "seq": self.started, "stage": stage,
                 "configuration": config, "repetition": repetition, "id": query_id, "at": now()}
        self.append(value)
        return self.started

    def finish(self, seq, row):
        self.finished += 1
        self.append({"event": "finished", "seq": seq, **row, "at": now()})

    def close(self):
        self.stream.close()


def export(args, plan, binding, data, report, resources):
    MemoryBook, source, provenance = imported_book(args.source, plan["baseline"])
    begin = time.perf_counter_ns()
    with MemoryBook(args.state / "frozen.db", max_page_chars=900, cache_size=0) as book:
        for session in data.sessions:
            book.ingest(session)
        ingestion_ms = (time.perf_counter_ns() - begin) / 1e6
        documents = documents_from(book)
        groups = groups_for(data, book)
        bundle = {"dataset": data.description(), "documents": documents, "diagnostics": groups,
            "documents_sha256": digest(documents), "diagnostics_sha256": digest(groups),
            "originals_sha256": source_snapshot(book.db), "stats": book.stats(),
            "source_provenance": provenance, "source_sha256": engine_source_hash(source),
            "source_ingestion_ms": ingestion_ms,
            "evidence_attainability": evidence_attainability(data, documents)}
        atomic(args.bundle, bundle)
    report.update(frozen_corpus={key: value for key, value in bundle.items()
                               if key not in {"documents", "diagnostics"}},
                  storage=storage(args.state), source_unchanged=engine_source_hash(source) == plan["baseline"]["source_sha256"])
    report["validation"] = {"passed": report["source_unchanged"], "failures": []}


def native(args, plan, binding, data, bundle, report, ledger, resources):
    expected = plan["baseline"] if args.stage == "baseline-native" else binding["candidate"]
    semantic = args.stage == "candidate-semantic-native"
    MemoryBook, source, provenance = imported_book(args.source, expected)
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    for counter in counters.values():
        if counter.version != "0.12.0":
            raise ValueError("Wrong reference tokenizer version")
    sources = original_turn_texts(data)
    setup_start = time.perf_counter_ns()
    init = {"semantic_model_dir": args.model_dir} if semantic else {}
    with MemoryBook(args.state / "native.db", max_page_chars=900, cache_size=0, **init) as book:
        begin = time.perf_counter_ns()
        for session in data.sessions:
            book.ingest(session)
        report["preparation"] = {"source_ingestion_ms": (time.perf_counter_ns() - begin) / 1e6}
        if semantic:
            report["preparation"]["semantic_index"] = book.build_semantic_index()
        report["preparation"]["engine_setup_wall_ms"] = (time.perf_counter_ns() - setup_start) / 1e6
        report["metadata"] = {"source_provenance": provenance, "source_sha256_before": expected["source_sha256"],
            "comparison_scope": "native recall API including context assembly and exact token counting",
            "semantic": semantic, "coverage": False, "stats": book.stats()}
        originals = source_snapshot(book.db)
        documents = documents_from(book)
        if digest(documents) != bundle["documents_sha256"]:
            raise ValueError("Candidate source pages differ from the preregistered common corpus")
        pages = {doc["id"]: doc["text"] for doc in documents}
        resources.set_phase("queries")
        for config in native_configurations(plan):
            rows, times, seen, invariant_counts = {}, [], {}, {key: 0 for key in INVARIANTS}
            mismatches = 0
            for repetition in range(plan["common"]["repeats"]):
                cases = list(data.queries)
                random.Random(plan["cohort"]["seed"] + 1009 * repetition).shuffle(cases)
                for case in cases:
                    seq = ledger.start(args.stage, config, repetition, case.id)
                    begin = time.perf_counter_ns()
                    response = book.recall(case.query, project=case.project, limit=5, use_cache=False,
                        coverage=False, semantic=semantic, **config)
                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                    row = sample_score(case, response, sources, counters, config, bundle["diagnostics"], pages)
                    sample = {"id": case.id, "configuration": config, "repetition": repetition,
                        "elapsed_ms": elapsed, "status": "ok", "row_sha256": digest(row),
                        **{key: row[key] for key in ("context_sha256", "context_tokens", "complete", "evidence_ranks", *INVARIANTS)}}
                    ledger.finish(seq, sample)
                    report["timing_rows"].append(sample)
                    times.append(sample)
                    for key in INVARIANTS:
                        invariant_counts[key] += int(row[key])
                    if repetition == 0:
                        rows[case.id] = row
                        seen[case.id] = row["context_sha256"]
                    elif seen[case.id] != row["context_sha256"]:
                        mismatches += 1
            ordered = [rows[case.id] for case in data.queries]
            report["configurations"].append({**config, "metrics": summarize_rows(ordered),
                "by_group": grouped_metrics(ordered), "query_results": ordered,
                "latency": latency_summary([sample["elapsed_ms"] for sample in times]),
                "first_pass_latency": latency_summary([sample["elapsed_ms"] for sample in times if sample["repetition"] == 0]),
                "repeat_pass_latency": latency_summary([sample["elapsed_ms"] for sample in times if sample["repetition"] > 0]),
                "invariants": invariant_counts, "repeat_context_mismatches": mismatches})
        resources.set_phase("finalization")
        report["metadata"].update(originals_unchanged=originals == source_snapshot(book.db), stats_after=book.stats())
        report["storage_before_close"] = storage(args.state)
    report["storage_after_close"] = storage(args.state)
    report["metadata"].update(source_sha256_after=engine_source_hash(source),
                              source_unchanged=engine_source_hash(source) == expected["source_sha256"])
    failures = []
    for config in report["configurations"]:
        if any(config["invariants"].values()) or config["metrics"]["context_size_mismatches"] or config["repeat_context_mismatches"]:
            failures.append({"check": "native_response_invariants", "configuration": {key: config[key] for key in
                ("budget_chars", "tokenizer", "budget_tokens")}})
    if not report["metadata"]["source_unchanged"] or not report["metadata"]["originals_unchanged"]:
        failures.append({"check": "source_unchanged"})
    report["validation"] = {"passed": not failures, "failures": failures}


def component_engine(args, plan, binding, bundle):
    if args.stage in {"baseline-component", "candidate-component", "candidate-semantic-component"}:
        expected = plan["baseline"] if args.stage == "baseline-component" else binding["candidate"]
        MemoryBook, source, provenance = imported_book(args.source, expected)
        begin = time.perf_counter_ns()
        shutil.copyfile(args.frozen_db, args.state / "component.db")
        copy_ms = (time.perf_counter_ns() - begin) / 1e6
        semantic = args.stage == "candidate-semantic-component"
        book = MemoryBook(args.state / "component.db", max_page_chars=900, cache_size=0,
                          **({"semantic_model_dir": args.model_dir} if semantic else {}))
        class BookComponent:
            metadata = {"source_provenance": provenance, "source_sha256": expected["source_sha256"],
                "comparison_scope": "shared-page Book ranker with native hierarchy metadata",
                "latency_scope": "Python recall and native context assembly; no IPC",
                "frozen_database_copy_ms": copy_ms, "source_ingestion_ms": None,
                "setup_policy": "Open a copy of the same baseline-ingested archive; native-stage reports measure source ingestion separately."}
            def search(self, query, project, limit):
                start = time.perf_counter_ns()
                response = book.recall(query, project=project, limit=limit, budget_chars=100000,
                                       use_cache=False, coverage=False, semantic=semantic)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                return {"hit_ids": [item["id"] for item in response["results"]], "results": response["results"],
                    "native_payload": response, "native_text": response["context"], "search_ms": elapsed, "bridge_ms": elapsed}
            def close(self):
                self.metadata.update(stats_after=book.stats(), originals_unchanged=source_snapshot(book.db) == bundle["originals_sha256"])
                book.close()
                self.metadata.update(source_sha256_after=engine_source_hash(source),
                                     source_unchanged=engine_source_hash(source) == expected["source_sha256"])
        engine = BookComponent()
        if semantic:
            engine.metadata["semantic_index"] = book.build_semantic_index()
        return engine, args.state
    if args.stage == "claude-mem-fts":
        from benchmarks.competitors.claude_mem import ClaudeMemFTS
        return ClaudeMemFTS(bundle["documents"], args.cache / "claude-mem", args.state / "native", offline=True), args.state / "native"
    if args.stage == "ai-memory-hybrid":
        from benchmarks.competitors.ai_memory import AiMemoryNative
        engine = AiMemoryNative(bundle["documents"], args.cache / "ai-memory", offline=True, retrieval="hybrid")
        return engine, engine._data_dir
    from benchmarks.competitors.billion import BillionKernel
    return BillionKernel(bundle["documents"], args.cache / "billion-context", offline=True), None


def component(args, plan, binding, data, bundle, report, ledger, resources):
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    sources = original_turn_texts(data)
    documents = {doc["id"]: doc for doc in bundle["documents"]}
    begin = time.perf_counter_ns()
    engine, native_state = component_engine(args, plan, binding, bundle)
    report["preparation"] = {"engine_setup_wall_ms": (time.perf_counter_ns() - begin) / 1e6}
    responses, observed_ids, repeat_changes = {}, {}, 0
    resources.set_phase("queries")
    try:
        for repetition in range(plan["common"]["repeats"]):
            cases = list(data.queries)
            random.Random(plan["cohort"]["seed"] + 1009 * repetition).shuffle(cases)
            for case in cases:
                seq = ledger.start(args.stage, "search", repetition, case.id)
                response = engine.search(case.query, case.project, 5)
                ids = response.get("hit_ids")
                if ids is None:
                    ids = [item["ref"] for item in response["results"]]
                if len(ids) > 5 or len(ids) != len(set(ids)):
                    raise ValueError("Native result limit or unique-ID invariant failed")
                mapped = [identity for identity in ids if identity in documents]
                if any(documents[identity]["project"] != case.project for identity in mapped):
                    raise ValueError("Native component returned another project's page")
                payload = canonical_json(response.get("native_payload", response["results"]))
                reads = []
                if repetition == 0 and args.stage == "ai-memory-hybrid":
                    for identity in mapped:
                        read = engine.read(identity)
                        if read["result"].get("truncated") or read["result"].get("body") != documents[identity]["text"]:
                            raise ValueError("Native full read differs from the supplied page")
                        reads.append(read)
                read_payloads = [canonical_json(read.get("native_payload", read["result"])) for read in reads]
                cost = {"id": case.id, "repetition": repetition, "status": "ok", "hit_ids": mapped,
                    "unmapped_native_hits": len(ids) - len(mapped), "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                    "search_payload_tokens": {name: counter.count(payload) for name, counter in counters.items()},
                    "search_content_tokens": {name: counter.count(response["native_text"]) for name, counter in counters.items()}
                        if response.get("native_text") is not None else None,
                    "read_calls": len(reads), "read_ms": sum(read["read_ms"] for read in reads),
                    "read_payload_tokens": {name: sum(counter.count(value) for value in read_payloads) for name, counter in counters.items()},
                    "read_content_tokens": {name: sum(counter.count(read.get("native_text", canonical_json(read["result"]))) for read in reads)
                                            for name, counter in counters.items()},
                    "search_ms": response["search_ms"], "bridge_ms": response["bridge_ms"]}
                ledger.finish(seq, cost)
                report["timing_rows"].append(cost)
                if repetition == 0:
                    responses[case.id] = shared_response(mapped, documents)
                    observed_ids[case.id] = ids
                elif observed_ids[case.id] != ids:
                    repeat_changes += 1
        if args.stage == "ai-memory-hybrid":
            probe = data.queries[0]
            info = engine.search_mcp(probe.query, probe.project, 5, explain=True)
            engine.metadata["post_measurement_stream_diagnostic"] = {
                "query_id": probe.id, "streams_active": info["decoded_native"].get("streams_active"),
                "boundary": "One explicitly unscored diagnostic call after timed repetitions; not included in query costs."}
        resources.set_phase("finalization")
        report["storage_before_close"] = storage(native_state) if native_state else {
            "regular_file_bytes": 0, "boundary": "This supplied-source search-kernel harness has an in-memory index and no persistent corpus store."}
    finally:
        engine.close()
        report["metadata"] = engine.metadata
    for encoding, budget in itertools.product(plan["components"]["tokenizers"], plan["components"]["token_budgets"]):
        rows, packing_times = [], []
        config = {"tokenizer": encoding, "budget_tokens": budget}
        for case in data.queries:
            begin = time.perf_counter_ns()
            response = pack_whole_blocks(responses[case.id], budget, counters[encoding])
            packing_times.append((time.perf_counter_ns() - begin) / 1e6)
            rows.append(sample_score(case, response, sources, counters, config, bundle["diagnostics"]))
        report["configurations"].append({**config, "metrics": summarize_rows(rows), "by_group": grouped_metrics(rows),
            "query_results": rows, "packing_latency": latency_summary(packing_times),
            "invariants": {key: sum(int(row[key]) for row in rows) for key in INVARIANTS}})
    report["repeat_hit_changes"] = repeat_changes
    report["quality_boundary"] = "First-pass query results; all three repetitions' hit IDs and timings are retained. Repeat differences are reported, not hidden or averaged into extra distinct questions."
    samples = report["timing_rows"]
    report["native_search_latency"] = latency_summary([row["search_ms"] for row in samples])
    report["adapter_roundtrip_latency"] = latency_summary([row["bridge_ms"] for row in samples])
    report["first_pass_roundtrip_latency"] = latency_summary([row["bridge_ms"] for row in samples if row["repetition"] == 0])
    report["repeat_roundtrip_latency"] = latency_summary([row["bridge_ms"] for row in samples if row["repetition"] > 0])
    first = [row for row in samples if row["repetition"] == 0]
    report["native_costs"] = {"queries": len(first), "read_policy": plan["components"]["native_read_policy"],
        "mean_read_calls": statistics.fmean(row["read_calls"] for row in first),
        "mean_read_ms": statistics.fmean(row["read_ms"] for row in first),
        **{"mean_" + field: {name: statistics.fmean(row[field][name] for row in first) for name in ENCODINGS}
           if all(row[field] is not None for row in first) else None
           for field in ("search_payload_tokens", "search_content_tokens", "read_payload_tokens", "read_content_tokens")}}
    failures = []
    if any(any(config["invariants"].values()) or config["metrics"]["context_size_mismatches"]
           for config in report["configurations"]):
        failures.append({"check": "packed_source_scope_budget_invariants"})
    if report["metadata"].get("source_unchanged") is False or report["metadata"].get("originals_unchanged") is False:
        failures.append({"check": "source_unchanged"})
    if report["metadata"].get("native_process_exit_code", 0):
        failures.append({"check": "native_process_exit"})
    report["validation"] = {"passed": not failures, "failures": failures}


def summary_of(report, raw_sha):
    summary = copy.deepcopy(report)
    summary.pop("timing_rows", None)
    for config in summary.get("configurations", []):
        config.pop("query_results", None)
    summary["full_report_sha256"] = raw_sha
    return summary


def write_report(report, output):
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    Path(str(output) + ".json.gz").write_bytes(gzip.compress(raw, mtime=0))
    atomic(Path(str(output) + ".summary.json"), summary_of(report, hashlib.sha256(raw).hexdigest()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--frozen-db", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-id", required=True)
    args = parser.parse_args(argv)
    plan, binding = frozen_inputs()
    if args.stage not in stages(plan, binding) or args.state.exists():
        raise ValueError("Require a registered stage and fresh state directory")
    if any(Path(str(args.output) + suffix).exists() for suffix in (".json.gz", ".summary.json")):
        raise ValueError("Preserve existing reports; use a separately attributed run")
    args.state.mkdir(parents=True)
    report = {"schema_version": 1, "protocol": plan["protocol"], "stage": args.stage, "host_id": args.host_id,
        "started_at": now(), "plan_sha256": sha(PLAN), "binding_sha256": sha(BINDING),
        "cohort_manifest_sha256": sha(round2_data.MANIFEST), "evaluator_sha256": evaluator_sources(),
        "configurations": [], "timing_rows": [], "validation": {"passed": False, "failures": []},
        "configured_generative_model_calls": 0}
    ledger = Ledger(args.state / "attempts.jsonl")
    resources = Resources()
    try:
        data = round2_data.load(args.data)
        report["dataset"] = data.description()
        if args.stage == "export":
            export(args, plan, binding, data, report, resources)
        else:
            bundle = json.loads(args.bundle.read_bytes())
            if (bundle["dataset"]["sha256"] != data.fingerprint or digest(bundle["documents"]) != bundle["documents_sha256"]
                    or digest(bundle["diagnostics"]) != bundle["diagnostics_sha256"]):
                raise ValueError("Frozen common corpus differs from the registered data")
            report["frozen_corpus"] = {key: value for key, value in bundle.items() if key not in {"documents", "diagnostics"}}
            if args.stage.endswith("native"):
                native(args, plan, binding, data, bundle, report, ledger, resources)
            else:
                component(args, plan, binding, data, bundle, report, ledger, resources)
        if evaluator_sources() != report["evaluator_sha256"]:
            raise ValueError("Evaluator changed during measurement")
    except BaseException as error:
        report["validation"] = {"passed": False, "failures": [{"check": "stage_exception", "error_type": type(error).__name__}]}
    finally:
        ledger.close()
        report.update(finished_at=now(), resources=resources.close(), ledger_sha256=sha(args.state / "attempts.jsonl"),
                      attempts_started=ledger.started, attempts_finished=ledger.finished)
        write_report(report, args.output)
    print(json.dumps({"stage": args.stage, "validation": report["validation"],
                      "attempts_started": ledger.started, "attempts_finished": ledger.finished}))
    return 0 if report["validation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
