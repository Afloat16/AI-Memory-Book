"""Four pinned retrieval components on the chronological engineering workload.

Synthetic development data, supplied source pages, a shared 2,400-character
packer and fixed policy consumer. This does not measure an LLM, generated-code
accuracy, a complete memory product, or time to a correct engineering change.
Old evaluators, adapters, locks and evidence are imported without modification.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_components as shared
from benchmarks import engineering_workflow as workflow
from benchmarks.competitors.ai_memory import AiMemoryNative
from benchmarks.competitors.billion import BillionKernel
from benchmarks.competitors.claude_mem import ClaudeMemFTS, validate_native_rows

VERSION = "engineering-open-source-2400-v1"
BUDGET = 2400
LIMIT = 5
BACKENDS = ("book", "claude-mem-fts", "ai-memory-hybrid", "billion-context")
DEFAULT_LOCKS = {
    "claude-mem-fts": ROOT / "benchmarks/competitors/claude-mem-round2-lock.json",
    "ai-memory-hybrid": ROOT / "benchmarks/competitors/ai-memory-lock.json",
    "billion-context": ROOT / "benchmarks/competitors/billion-round2-lock.json",
}
DEFAULT_CACHES = {
    "claude-mem-fts": ROOT / ".artifacts/competitors/claude-round2",
    "ai-memory-hybrid": ROOT / ".artifacts/competitors/ai-memory",
    "billion-context": ROOT / ".artifacts/competitors/billion-round2",
}
SOURCE_FILES = (
    "scripts/engineering_open_source_2400.py",
    "tests/test_engineering_open_source_2400.py",
    "benchmarks/engineering_workflow.py", "benchmarks/engineering_components.py",
    "benchmarks/competitors/ai_memory.py", "benchmarks/competitors/billion.py",
    "benchmarks/competitors/claude_mem.py", "benchmarks/competitors/download.py",
    "benchmarks/competitors/billion_bridge.mjs", "benchmarks/competitors/compile_billion.mjs",
    "benchmarks/competitors/claude_mem_bridge.ts",
)

SCOPE = {
    "evidence": "authored synthetic development workload; no independent holdout or real-user study",
    "consumer": "fixed config-policy selection and handwritten algorithm checks; not generated-code accuracy",
    "packing": "same original full source blocks, native order, skip blocks that do not fit; no truncation or refill",
    "budget": "exactly a 2400 Unicode-character ceiling including source headers; not a model-token budget",
    "book": "v0.4.0 lexical recall, native hierarchy/FTS metadata, limit 5, native budget 100000 for candidate IDs; result cache disabled",
    "claude-mem-fts": "pinned SessionSearch.searchObservations, native SQLite schema/FTS triggers; supplied title/text/date; no observer, Chroma, worker, timeline or generated semantic fields",
    "ai-memory-hybrid": "pinned official executable, native MCP memory_query, local all-MiniLM-L6-v2 (384 dimensions, native 512-token model input limit), original title/body, episodic tier, empty tags, unpinned; native write-time metadata, not original source timestamps",
    "billion-context": "pinned upstream searchBlocks after syntax-only TypeScript erasure; uniform assistant message role, supplied title/body/project; no host decompression or original timestamp field",
    "representation": "same source content and project scope do not imply identical indexed fields, timestamp semantics, native result surfaces, or storage work",
    "query_timing": "outer adapter-call wall time only; Book in-process recall, Claude/Billion persistent JSON process bridge, ai-memory loopback MCP HTTP; native inner timings remain separately named",
    "read_timing": "ai-memory full-page reads validate every unique recalled supplied page after all checkpoint searches; excluded from search timing and not an end-to-end retrieval-plus-read measurement",
    "setup": "canonical Book incremental ingestion/export is separate; each query engine opens once per checkpoint; external engines freshly index all visible supplied pages; setup is not a comparable product lifecycle",
    "repetitions": "at least three timing repetitions per query with rotating backend order; repeated scores retained, not additional independent quality cases; native internal caches warm naturally",
    "missing_answer": "all missing-evidence queries retained; nonempty context is a retrieval diagnostic, not a hallucination or generated-answer claim",
    "upstream_versions": "explicit immutable pins, not a claim to run the latest releases",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(locks):
    paths = {str(ROOT / name) for name in SOURCE_FILES} | {str(Path(p).resolve()) for p in locks.values()}
    files = {}
    for name in sorted(paths):
        path = Path(name)
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        files[label] = file_hash(path)
    return {"files": files, "sha256": workflow.sha(files)}


def append_json(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def backend_order(checkpoint, ordinal=0, repetition=0):
    offset = (checkpoint - 1 + ordinal + repetition) % len(BACKENDS)
    return BACKENDS[offset:] + BACKENDS[:offset]


def search_component(backend, engine, query, project):
    """Only query, explicit project and fixed retrieval options cross this boundary."""
    if backend == "book":
        return shared.book_search(engine, query, project)
    if backend == "billion-context":
        return engine.search(query, project=project, limit=LIMIT, preview_chars=100000)
    return engine.search(query, project=project, limit=LIMIT)


def map_hits(native, backend, documents, project):
    """Retain all native top-five slots, including unmapped ai-memory metadata.

    Such metadata cannot become evidence or be replaced by a sixth result.
    The full native response is saved before mapping failures can abort a run.
    """
    require(backend in BACKENDS, "Unknown backend")
    hits = native.get("native_payload") if backend == "claude-mem-fts" else native.get("results")
    require(isinstance(hits, list) and len(hits) <= LIMIT
            and all(isinstance(hit, dict) for hit in hits), "Expected native top-five result rows")
    if backend in {"claude-mem-fts", "ai-memory-hybrid"}:
        ids = native.get("hit_ids")
    else:
        ids = [hit.get("id" if backend == "book" else "ref") for hit in hits]
    require(isinstance(ids, list) and len(ids) == len(hits), "Native rows and source mapping differ")
    if backend == "claude-mem-fts":
        validate_native_rows(native, documents, project, LIMIT)
    mapped, native_ids, mapping = [], [], []
    for rank, (identity, hit) in enumerate(zip(ids, hits, strict=True), 1):
        require(isinstance(identity, str) or identity is None, "Invalid supplied-source identity")
        native_id = hit.get("ref") if backend == "billion-context" else hit.get("id")
        require(isinstance(native_id, (str, int)) and not isinstance(native_id, bool), "Missing native result identity")
        native_ids.append(workflow.sha(native_id))
        require(identity in documents or (identity is None and backend == "ai-memory-hybrid"),
                "Native result has an unknown supplied-source mapping")
        require("project" not in hit or hit["project"] == project, "Native result crossed project scope")
        require("workspace" not in hit or hit["workspace"] == "benchmark", "Native result crossed workspace scope")
        item = {"native_rank": rank, "native_id": native_id, "document_id": identity}
        if identity is not None:
            doc = documents[identity]
            require(doc["project"] == project, "Mapped source crossed project scope")
            mapped.append(identity)
            item.update(source_refs=doc["source_refs"], source_text_sha256=hashlib.sha256(doc["text"].encode()).hexdigest())
        else:
            item["packing_disposition"] = "unmapped native metadata consumes its top-five slot; no refill"
        mapping.append(item)
    require(len(mapped) == len(set(mapped)), "Native response duplicated a supplied source")
    require(len(native_ids) == len(set(native_ids)), "Native response duplicated a native identity")
    return {"native_hit_ids": ids, "hit_ids": mapped, "source_map": mapping}


def validate_native_read(response, document):
    result = response.get("result")
    require(isinstance(result, dict) and not result.get("truncated")
            and result.get("body") == document["text"], "Native full read differs from the supplied source")
    require("project" not in result or result["project"] == document["project"], "Native read crossed project scope")
    require("workspace" not in result or result["workspace"] == "benchmark", "Native read crossed workspace scope")


def open_component(backend, documents, database, directory, caches, locks, node, offline):
    from memory_book import MemoryBook
    # Do not pass case objects, evidence labels or future records to adapters.
    fields = [{key: doc[key] for key in ("id", "project", "title", "text", "created_at")} for doc in documents]
    if backend == "book":
        return MemoryBook(database, cache_size=0)
    if backend == "claude-mem-fts":
        return ClaudeMemFTS(fields, caches[backend], directory / "claude", offline=offline, lock_path=locks[backend])
    if backend == "ai-memory-hybrid":
        return AiMemoryNative(fields, caches[backend], offline=offline, retrieval="hybrid")
    return BillionKernel(fields, caches[backend], node=node, offline=offline, lock_path=locks[backend])


def artifact_identity(backend, engine, caches, locks):
    """Hash executed immutable inputs outside the query timer, before and after."""
    if backend == "book":
        return None  # Imported Python source closure is checked for the entire run.
    cache = Path(caches[backend]).resolve()
    lock = json.loads(Path(locks[backend]).read_text())
    if backend == "claude-mem-fts":
        paths = [cache / "bun", cache / lock["source_archive"]["name"], cache / lock["runtime"]["name"]]
        paths += sorted(path for path in (cache / "verified-source").rglob("*") if path.is_file())
    elif backend == "ai-memory-hybrid":
        paths = [cache / f"ai-memory-{lock['version']}", cache / f"ai-memory-linux-x86_64-{lock['version']}.tar.gz"]
        paths += [cache / "models" / lock["embedding_model"]["name"] / entry["name"]
                  for entry in lock["embedding_model"]["files"]]
    else:
        paths = [cache / entry["path"] for entry in lock["files"]]
        paths += sorted((cache / ".memory-book-js").rglob("*.js"))
    files = {str(path.relative_to(cache)): file_hash(path) for path in paths}
    return {"files": files, "sha256": workflow.sha(files)}


def pairwise(rows):
    by_case = {}
    for row in rows:
        by_case.setdefault(row["case_id"], {})[row["backend"]] = row
    result = {}
    for backend in BACKENDS[1:]:
        cases = []
        for case_id, values in by_case.items():
            if "book" not in values or backend not in values:
                continue
            book, other = values["book"], values[backend]
            left, right = book["score"], other["score"]
            outcomes = {}
            for metric, a, b in (
                ("complete_evidence", left["complete_evidence"] if left["answerable"] else None,
                 right["complete_evidence"] if right["answerable"] else None),
                ("evidence_matches", left["matched_evidence"] if left["answerable"] else None,
                 right["matched_evidence"] if right["answerable"] else None),
                ("fixed_consumer", left.get("fixed_consumer", {}).get("all_passed"),
                 right.get("fixed_consumer", {}).get("all_passed")),
            ):
                outcomes[metric] = ("not_applicable" if a is None or b is None else
                                    "book_win" if a > b else "book_loss" if a < b else "tie")
            cases.append({"case_id": case_id, **{key: book[key] for key in ("project", "checkpoint", "category", "query")},
                          "outcomes": outcomes,
                          "mixed": "book_win" in outcomes.values() and "book_loss" in outcomes.values(),
                          "book_score": left, "component_score": right})
        result[backend] = {"metrics": {metric: dict(Counter(case["outcomes"][metric] for case in cases))
                                      for metric in ("complete_evidence", "evidence_matches", "fixed_consumer")},
                           "mixed_cases": sum(case["mixed"] for case in cases), "cases": cases}
    return result


def markdown_report(report):
    lines = ["# Four open-source retrieval components at 2,400 characters", "",
             "**Authored synthetic development workload; no LLM or full-product productivity comparison.**", "",
             f"Status: `{report['status']}`. Runner: `{VERSION}`. Book: `{report['package_version']}`.", "",
             "| Component | Evidence recall | Complete evidence | Fixed-consumer checks pass | Stale-only | Mean chars |",
             "|---|---:|---:|---:|---:|---:|"]
    def pct(value):
        return "n/a" if value is None else f"{value:.1%}"
    for cell in report.get("summary", []):
        lines.append(f"| {cell['backend']} | {pct(cell['evidence_recall'])} | {pct(cell['complete_evidence_rate'])} | "
                     f"{pct(cell['fixed_consumer_all_checks_pass_rate'])} | {cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "## Interpretation and measurement boundaries", ""]
    lines += [f"- **{key}:** {value}." for key, value in SCOPE.items()]
    lines += ["", "## Auditable outputs", "",
              "`native.jsonl` preserves every search response, source mapping, per-repetition context/score and raw timing. "
              "`reads.jsonl` preserves the delayed native full-page validation reads. `raw.jsonl` contains one row per "
              "case/component; summaries use repetition zero, while all repeated outcomes remain available. "
              "The operation ledger, setup metadata, source bundles, dataset, lock contents and before/after source "
              "hashes are retained. `report.json` includes all paired wins, losses, ties and mixed cases, plus "
              "category/checkpoint/family breakdowns. Native payload stability and packed evidence stability are "
              "reported separately: native CPU counters can vary without changing the result.", "",
              "## Upstream attribution", ""]
    for backend, lock in report["upstream_locks"].items():
        lines.append(f"- [{lock['repository']}](https://github.com/{lock['repository']}) at `{lock['commit']}`: {lock['license']}.")
    lines += ["- Billion's associated [acp-kernel](https://github.com/ranxianglei/acp-kernel) is also credited under its additional attribution term.", ""]
    if report.get("error"):
        lines += ["## Incomplete execution", "", f"`{report['error']['type']}` at `{report['error']['stage']}`: {report['error']['message']}", ""]
    return "\n".join(lines)


def run(output, *, repeats=3, noise_per_step=2, node="node", caches=None, offline=False,
        claude_lock=None, billion_lock=None):
    import memory_book
    from memory_book import MemoryBook
    require(type(repeats) is int and 3 <= repeats <= 30, "repeats must be an integer from 3 through 30")
    require(type(noise_per_step) is int and 0 <= noise_per_step <= 100, "noise_per_step must be an integer from 0 through 100")
    require(memory_book.__version__ == "0.4.0", "This versioned comparison requires Book v0.4.0")
    locks = dict(DEFAULT_LOCKS)
    if claude_lock is not None:
        locks["claude-mem-fts"] = Path(claude_lock).resolve()
    if billion_lock is not None:
        locks["billion-context"] = Path(billion_lock).resolve()
    caches = {key: Path(value).resolve() for key, value in (caches or DEFAULT_CACHES).items()}
    require(set(caches) == set(DEFAULT_CACHES), "Provide one cache directory for each external component")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    require(not any(output.iterdir()), "Choose a fresh empty output directory; earlier attempts are retained")
    started = datetime.now(timezone.utc).isoformat()
    runtime_before, evaluator_before = workflow.runtime_identity(memory_book), source_identity(locks)
    steps = workflow.workload(noise_per_step)
    cases = [case for step in steps for case in step["cases"]]
    report = {"version": VERSION, "status": "started", "created_at": started, "package_version": memory_book.__version__,
              "evidence_level": "synthetic_development_shared_page_components", "scope": SCOPE,
              "dataset_sha256": workflow.sha(steps), "runtime": runtime_before, "evaluator": evaluator_before,
              "upstream_locks": {key: json.loads(Path(path).read_text()) for key, path in locks.items()},
              "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                              "logical_cpu_count": os.cpu_count(), "node_command": node},
              "settings": {"budget_chars": BUDGET, "limit": LIMIT, "repeats": repeats, "noise_per_step": noise_per_step,
                           "backends": list(BACKENDS), "offline": offline, "book_result_cache": False,
                           "book_native_budget_chars": 100000, "billion_native_preview_chars": 100000,
                           "engine_startups_per_checkpoint_per_backend": 1,
                           "backend_order": "left rotate by checkpoint-1 + within-checkpoint case ordinal + repetition",
                           "quality_repetition": 0, "native_reads": "unique recalled ai-memory source pages after checkpoint searches"}}
    shared.write_json(output / "binding.json", report)
    shared.write_json(output / "dataset.json", steps)
    rows, samples, reads, checkpoints, visible = [], [], [], [], {}
    stage, sequence = "initialize", 0
    try:
        with ExitStack() as stack:
            directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="engineering-open-source-")))
            streams = {name: stack.enter_context((output / f"{name}.jsonl").open("w", encoding="utf-8"))
                       for name in ("raw", "native", "reads", "operations")}
            database = directory / "book.db"
            for step in steps:
                number = step["checkpoint"]
                stage = f"checkpoint-{number}-canonical-ingest"
                begin = time.perf_counter_ns()
                # Canonical preparation is distinct from a fresh query engine.
                with MemoryBook(database, cache_size=0) as builder:
                    for session in step["sessions"]:
                        builder.ingest(session)
                        visible[(session["project"], session["session_id"])] = session
                    documents = shared.export_documents(builder, visible)
                canonical_ms = (time.perf_counter_ns() - begin) / 1e6
                lookup = {doc["id"]: doc for doc in documents}
                sources = workflow.visible_sources(visible)
                shared.write_json(output / f"documents-{number}.json", documents)
                checkpoint = {"checkpoint": number, "visible_sessions": len(visible), "documents": len(documents),
                              "documents_sha256": workflow.sha(documents), "canonical_ingest_export_close_ms": canonical_ms,
                              "setup_order": list(backend_order(number)), "engines": {}}
                checkpoints.append(checkpoint)
                engines, required_reads, verified_reads = {}, set(), set()
                try:
                    with ExitStack() as engines_stack:
                        for backend in checkpoint["setup_order"]:
                            stage = f"checkpoint-{number}-{backend}-setup"
                            begin = time.perf_counter_ns()
                            engine = open_component(backend, documents, database, directory / str(number),
                                                    caches, locks, node, offline)
                            engines[backend] = engine
                            engines_stack.callback(engine.close)
                            setup_ms = (time.perf_counter_ns() - begin) / 1e6
                            checkpoint["engines"][backend] = {
                                "startup_count": 1, "adapter_setup_ms": setup_ms,
                                "metadata": getattr(engine, "metadata", {"name": "Book", "result_cache": False})}
                            checkpoint["engines"][backend]["artifacts_before"] = artifact_identity(backend, engine, caches, locks)
                            if backend == "ai-memory-hybrid":
                                native_map = dict(engine._by_page_id)
                                require(set(native_map.values()) == set(lookup) and len(native_map) == len(lookup),
                                        "Native ai-memory page map differs from the supplied sources")
                                checkpoint["engines"][backend]["native_page_map"] = native_map
                                checkpoint["engines"][backend]["native_locations"] = dict(engine._locations)
                        shared.write_json(output / f"checkpoint-{number}.json", checkpoint)
                        for ordinal, case in enumerate(step["cases"]):
                            measurements = {backend: [] for backend in BACKENDS}
                            for repetition in range(repeats):
                                order = backend_order(number, ordinal, repetition)
                                for position, backend in enumerate(order):
                                    stage = f"query-{case['id']}-{backend}-repeat-{repetition}"
                                    sequence += 1
                                    event = {"sequence": sequence, "checkpoint": number, "case_id": case["id"],
                                             "backend": backend, "repetition": repetition, "order": list(order), "position": position}
                                    append_json(streams["operations"], {**event, "event": "search_started"})
                                    begin = time.perf_counter_ns()
                                    native = search_component(backend, engines[backend], case["query"], case["project"])
                                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                                    sample = {**event, "query": case["query"], "project": case["project"],
                                              "category": case["category"], "adapter_call_ms": elapsed, "native": native,
                                              "native_search_ms": elapsed if backend == "book" else native.get("search_ms"),
                                              "native_bridge_ms": elapsed if backend == "book" else native.get("bridge_ms"),
                                              "native_sha256": workflow.sha(shared.stable(native))}
                                    try:
                                        sample.update(map_hits(native, backend, lookup, case["project"]))
                                        if backend == "ai-memory-hybrid":
                                            for hit in sample["source_map"]:
                                                require(engines[backend]._by_page_id.get(hit["native_id"]) == hit["document_id"],
                                                        "Native ai-memory hit does not match its write-time source map")
                                            required_reads.update(sample["hit_ids"])
                                        pack_begin = time.perf_counter_ns()
                                        response = shared.common_pack(sample["hit_ids"], lookup, case["project"], BUDGET)
                                        sample["common_pack_ms"] = (time.perf_counter_ns() - pack_begin) / 1e6
                                        sample.update(response=response, score=workflow.score(case, response, sources, BUDGET),
                                                      packed_sha256=workflow.sha(response))
                                    except Exception as error:
                                        sample["validation_error"] = {"type": type(error).__name__, "message": str(error)}
                                        raise
                                    finally:
                                        append_json(streams["native"], sample)
                                        samples.append(sample)
                                    append_json(streams["operations"], {**event, "event": "search_completed"})
                                    measurements[backend].append(sample)
                            for backend, values in measurements.items():
                                first = values[0]
                                row = {"case_id": case["id"], "backend": backend, "category": case["category"],
                                       "project": case["project"], "query": case["query"], "checkpoint": number,
                                       "budget_chars": BUDGET, "latency_ms": [item["adapter_call_ms"] for item in values],
                                       "common_pack_ms": first["common_pack_ms"],
                                       "repeat_outputs_equal": len({item["packed_sha256"] for item in values}) == 1,
                                       "repeat_native_outputs_equal": len({item["native_sha256"] for item in values}) == 1,
                                       "repeat_hit_ids_equal": all(item["source_map"] == first["source_map"] for item in values),
                                       "native_sequences": [item["sequence"] for item in values],
                                       "native_first_output_sha256": first["native_sha256"],
                                       "source_map": first["source_map"], "response": first["response"], "score": first["score"],
                                       "repeat_scores": [item["score"] for item in values]}
                                rows.append(row)
                                append_json(streams["raw"], row)
                        # Validation reads cannot affect this checkpoint's ranking.
                        stage = f"checkpoint-{number}-native-page-validation"
                        for identity in sorted(required_reads):
                            begin = time.perf_counter_ns()
                            native_read = engines["ai-memory-hybrid"].read(identity)
                            read = {"checkpoint": number, "document_id": identity,
                                    "adapter_read_ms": (time.perf_counter_ns() - begin) / 1e6,
                                    "native": native_read, "source_refs": lookup[identity]["source_refs"]}
                            try:
                                validate_native_read(native_read, lookup[identity])
                                verified_reads.add(identity)
                                read["source_validated"] = True
                            finally:
                                append_json(streams["reads"], read)
                                reads.append(read)
                        checkpoint["native_read_validation"] = {"required": len(required_reads), "verified": len(verified_reads),
                                                                 "all_valid": required_reads == verified_reads}
                finally:
                    for backend, engine in engines.items():
                        metadata = checkpoint["engines"][backend]
                        try:
                            metadata["artifacts_after"] = artifact_identity(backend, engine, caches, locks)
                            metadata["artifacts_unchanged"] = ("artifacts_before" in metadata
                                                               and metadata["artifacts_before"] == metadata["artifacts_after"])
                        except Exception as error:
                            # Do not replace an original setup/search failure with
                            # a secondary cleanup-integrity error.
                            metadata["artifacts_unchanged"] = False
                            metadata["artifact_verification_error"] = {"type": type(error).__name__, "message": str(error)}
                    shared.write_json(output / f"checkpoint-{number}.json", checkpoint)
            report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
    try:
        runtime_after, evaluator_after = workflow.runtime_identity(memory_book), source_identity(locks)
    except Exception as error:
        runtime_after = evaluator_after = {"sha256": None}
        report["final_source_verification_error"] = {"type": type(error).__name__, "message": str(error)}
    report.update(runtime_unchanged=runtime_before == runtime_after, evaluator_unchanged=evaluator_before == evaluator_after,
                  runtime_final_sha256=runtime_after["sha256"], evaluator_final_sha256=evaluator_after["sha256"],
                  case_count=len(cases), completed_query_backend_pairs=len(rows), native_search_calls=len(samples),
                  checkpoints=checkpoints, summary=workflow.summarize(rows) if rows else [],
                  pairwise=pairwise(rows))
    for dimension in ("category", "checkpoint", "family"):
        def group(row):
            return row["project"].split("-", 1)[0] if dimension == "family" else row[dimension]
        report[f"by_{dimension}"] = {str(value): workflow.summarize([row for row in rows if group(row) == value])
                                     for value in sorted({group(row) for row in rows})}
    report["native_timing"] = {backend: {phase: {
        field: shared.timing([sample[field] for sample in samples if sample["backend"] == backend
                              and (sample["repetition"] == 0) == (phase == "first_query_search")
                              and sample.get(field) is not None])
        for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms", "common_pack_ms")}
        for phase in ("first_query_search", "repeat_query_search")} for backend in BACKENDS}
    report["delayed_native_read_timing"] = shared.timing([read["adapter_read_ms"] for read in reads])
    report["repeat_native_output_changes"] = sum(not row["repeat_native_outputs_equal"] for row in rows)
    report["repeat_hit_id_changes"] = sum(not row["repeat_hit_ids_equal"] for row in rows)
    expected_pairs = len(cases) * len(BACKENDS)
    checks = {
        "runtime_unchanged": report["runtime_unchanged"], "evaluator_unchanged": report["evaluator_unchanged"],
        "all_case_backend_pairs": len(rows) == expected_pairs,
        "all_search_repetitions": len(samples) == expected_pairs * repeats,
        "all_checkpoint_engines": len(checkpoints) == len(steps) and all(set(c["engines"]) == set(BACKENDS) for c in checkpoints),
        "executed_artifacts_unchanged": all(m.get("artifacts_unchanged") and m["metadata"].get("source_unchanged", True)
                                            for c in checkpoints for m in c["engines"].values()),
        "all_native_reads_valid": all(c.get("native_read_validation", {}).get("all_valid", False) for c in checkpoints),
        "zero_source_or_budget_errors": all("score" in sample and not sample["score"]["source_errors"]
                                             and sample["score"]["within_budget"] for sample in samples),
        "packed_outputs_and_native_ids_stable": all(row["repeat_outputs_equal"] and row["repeat_hit_ids_equal"] for row in rows),
    }
    report["integrity_checks"] = checks
    report["integrity_passed"] = all(checks.values()) and report["status"] == "completed"
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    shared.write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeats", default=3, type=int)
    parser.add_argument("--noise-per-step", default=2, type=int)
    parser.add_argument("--node", default="node")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--claude-cache", type=Path, default=DEFAULT_CACHES["claude-mem-fts"])
    parser.add_argument("--ai-memory-cache", type=Path, default=DEFAULT_CACHES["ai-memory-hybrid"])
    parser.add_argument("--billion-cache", type=Path, default=DEFAULT_CACHES["billion-context"])
    parser.add_argument("--claude-lock", type=Path)
    parser.add_argument("--billion-lock", type=Path)
    args = parser.parse_args()
    report = run(args.output, repeats=args.repeats, noise_per_step=args.noise_per_step,
                 node=args.node, offline=args.offline, claude_lock=args.claude_lock, billion_lock=args.billion_lock,
                 caches={"claude-mem-fts": args.claude_cache, "ai-memory-hybrid": args.ai_memory_cache,
                         "billion-context": args.billion_cache})
    print(json.dumps({"status": report["status"], "output": str(args.output), "summary": report["summary"],
                      "integrity_checks": report["integrity_checks"], "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
