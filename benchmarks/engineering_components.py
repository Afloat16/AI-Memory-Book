"""Pinned external search components on the engineering development workload.

This evaluates supplied-page ranking with common whole-block packing, not an
LLM, a complete memory product, or real coding productivity. The foreign ranker
is the actual integrity-checked billion-context TypeScript searchBlocks().
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import time

from benchmarks import engineering_workflow as workflow
from benchmarks.competitors.billion import BillionKernel

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "benchmarks/competitors/billion-round2-lock.json"
BACKENDS = ("book", "billion")
VERSION = "engineering-shared-components-v1"
SOURCE_FILES = (
    "benchmarks/engineering_components.py", "benchmarks/engineering_workflow.py",
    "benchmarks/competitors/billion.py", "benchmarks/competitors/billion_bridge.mjs",
    "benchmarks/competitors/compile_billion.mjs", "benchmarks/competitors/download.py",
    "benchmarks/competitors/billion-round2-lock.json",
)


def source_identity():
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    return {"files": files, "sha256": workflow.sha(files)}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def export_documents(book, visible):
    """Export only present pages; assert one complete original turn per page."""
    sources = workflow.visible_sources(visible)
    documents, seen = [], set()
    for row in book.db.execute("SELECT id,project_id FROM pages ORDER BY id"):
        page = book.read(row["id"], limit=100000)
        refs = page["source_refs"]
        if page["next_offset"] is not None or len(refs) != 1:
            raise ValueError("This component protocol requires complete one-turn pages")
        ref = refs[0]
        identity = (ref["project"], ref["session_id"], ref["turn_index"])
        if (identity not in sources or identity in seen or page["content"] != sources[identity]
                or ref["turn_start"] != 0 or ref["turn_end"] != len(sources[identity])
                or row["project_id"] != identity[0]):
            raise ValueError("Supplied page differs from the visible original source")
        seen.add(identity)
        documents.append({"id": page["id"], "project": row["project_id"], "title": page["title"],
                          "text": page["content"], "source_refs": refs, "created_at": page["created_at"]})
    if seen != set(sources):
        raise ValueError("Supplied pages omit or add a visible source")
    return documents


def mapped_ids(native, backend, documents, project):
    hits = native["results"]
    if not isinstance(hits, list) or len(hits) > 5:
        raise ValueError("Native response is not a top-five result list")
    ids = [hit["id" if backend == "book" else "ref"] for hit in hits]
    if len(ids) != len(set(ids)):
        raise ValueError("Native response repeats a supplied page")
    if any(identity not in documents for identity in ids):
        raise ValueError("Native response contains an unmapped page")
    if any(documents[identity]["project"] != project for identity in ids):
        raise ValueError("Native response crossed the requested project scope")
    return ids


def common_pack(ids, documents, project, budget):
    """Same full source bodies and framing for both engines; never use previews.

    Keep native candidate order, skip blocks that do not wholly fit, and never
    truncate or supplement a body. This receives no query or answer labels.
    """
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget must be a positive integer")
    if len(ids) > 5 or len(ids) != len(set(ids)):
        raise ValueError("Expected at most five distinct native candidates")
    blocks, hits, omitted, used = [], [], [], 0
    for identity in ids:
        doc = documents[identity]
        if doc["project"] != project:
            raise ValueError("Common pack received another project's page")
        session = doc["source_refs"][0]["session_id"]
        header = f"[{identity}] {project} / {session} | {doc['created_at']}\n"
        block = header + doc["text"]
        cost = len(block) + (2 if blocks else 0)
        if used + cost > budget:
            omitted.append(identity)
            continue
        blocks.append(block)
        used += cost
        hits.append({"id": identity, "text": doc["text"], "created_at": doc["created_at"],
                     "source_refs": doc["source_refs"]})
    return {"context": "\n\n".join(blocks), "results": hits, "omitted_for_budget": omitted}


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items()
                if key not in {"latency_ms", "search_ms", "bridge_ms"}}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def book_search(book, query, project):
    # No case, expected policy, evidence labels or future records enter here.
    return book.recall(query, project=project, limit=5, budget_chars=100000,
                       use_cache=False, coverage=False)


def timing(values):
    return {"samples": len(values), "p50_ms": statistics.median(values),
            "p95_ms": workflow.quantile(values, .95)} if values else None


def markdown_report(report):
    lines = ["# Engineering supplied-page component comparison", "",
        "**Authored synthetic development data; fixed consumer; no LLM or full memory product evaluation.**", "",
        f"Status: `{report['status']}`. Runtime: `{report['runtime']['sha256']}`. "
        f"Evaluator closure: `{report['evaluator']['sha256']}`.", "",
        "Both rankers see the same complete source-page bodies, project filter and top-five limit. "
        "A common packer ignores native excerpts, retains native ordering, and skips whole blocks "
        "that exceed the character cap. Characters are not exact model tokens.", "",
        "Book retains native hierarchy/FTS metadata; Billion receives uniform assistant-role messages "
        "with supplied title/body/project. Common representation does not mean identical indexed features.", "",
        "| Component | Chars | Evidence recall | Complete evidence | Fixed-consumer pass | Stale-only | Mean chars |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in report.get("summary", []):
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | {cell['evidence_recall']:.1%} | "
                     f"{cell['complete_evidence_rate']:.1%} | {cell['fixed_consumer_all_checks_pass_rate']:.1%} | "
                     f"{cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "## Timing boundaries", "",
        "Book timing is in-process Python recall including its native context assembly. "
        "Billion separately reports searchBlocks kernel time and persistent JSON process roundtrip. "
        "The common pack timer is an in-memory supplied-fixture lookup and assembly; it does not measure "
        "Billion's host decompression or native follow-up reads. These boundaries cannot establish a "
        "whole-product speed ratio, end-to-end model latency, or time to a correct patch.", "",
        "Native searches are reused across both character caps; repetitions measure timing, not "
        "independent quality cases. The process is restarted for each chronological checkpoint; "
        "native document-feature caches evolve normally within that checkpoint. Book result caching "
        "is disabled. First searches and later repetitions are retained separately in report.json.", "",
        "The benchmark preserves complete native responses for every repetition in native.jsonl; "
        "raw.jsonl records every common-budget context and evidence/consumer score. Checkpoint page "
        "bundles and dataset.json permit provenance validation. Setup and source ingestion costs "
        "are recorded separately and use different backend operations, not a product-lifecycle comparison.", "",
        "## Upstream attribution", "",
        "This benchmark executes [billion-context](https://github.com/ranxianglei/billion-context) "
        "and its [acp-kernel](https://github.com/ranxianglei/acp-kernel) search implementation at "
        f"`{report['upstream_lock']['commit']}`. Its license is MIT text plus an additional "
        "product-surface attribution condition. Original files are digest-verified before Node's "
        "syntax-only TypeScript erasure; no ranking implementation is rewritten here.", ""]
    if report.get("error"):
        lines += ["## Incomplete execution", "", f"`{report['error']['type']}`: {report['error']['message']}", ""]
    return "\n".join(lines)


def run(output, *, budgets=(1200, 2400), repeats=3, node="node", cache=None, offline=False):
    import memory_book
    from memory_book import MemoryBook
    if (not budgets or len(set(budgets)) != len(budgets)
            or any(type(b) is not int or not 0 < b <= 100000 for b in budgets)):
        raise ValueError("Choose distinct positive character caps up to 100000")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("repeats must be between 1 and 30")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Choose a fresh empty output directory; earlier attempts are retained")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    runtime_before, evaluator_before = workflow.runtime_identity(memory_book), source_identity()
    steps, visible, rows, native_rows, checkpoints = workflow.workload(), {}, [], [], []
    report = {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "synthetic_development_shared_page_components", "dataset_sha256": workflow.sha(steps),
        "runtime": runtime_before, "evaluator": evaluator_before, "upstream_lock": lock,
        "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
        "settings": {"budgets_chars": list(budgets), "repeats": repeats, "limit": 5, "noise_per_step": 2,
                     "native_preview_chars": 100000, "book_native_budget_chars": 100000,
                     "result_cache": False, "node": node, "offline": offline,
                     "packing": "native order; whole original source blocks; skip blocks that do not fit"}}
    write_json(output / "binding.json", report)
    write_json(output / "dataset.json", steps)
    cache = Path(cache) if cache else ROOT / ".artifacts/competitors/billion-round2"
    stage = "initialize"
    try:
        with ExitStack() as stack:
            directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="engineering-components-")))
            book = stack.enter_context(MemoryBook(directory / "book.db", cache_size=0))
            trace = stack.enter_context((output / "raw.jsonl").open("w", encoding="utf-8"))
            native_trace = stack.enter_context((output / "native.jsonl").open("w", encoding="utf-8"))
            for step in steps:
                stage = f"checkpoint-{step['checkpoint']}-ingest"
                start = time.perf_counter_ns()
                for session in step["sessions"]:
                    book.ingest(session)
                    visible[(session["project"], session["session_id"])] = session
                ingest_ms = (time.perf_counter_ns() - start) / 1e6
                documents = export_documents(book, visible)
                lookup = {doc["id"]: doc for doc in documents}
                sources = workflow.visible_sources(visible)
                write_json(output / f"documents-{step['checkpoint']}.json", documents)
                checkpoint = {"checkpoint": step["checkpoint"], "visible_sessions": len(visible),
                    "documents": len(documents), "documents_sha256": workflow.sha(documents),
                    "supplied_search_fields_sha256": workflow.sha([
                        {key: doc[key] for key in ("id", "project", "title", "text")} for doc in documents]),
                    "book_incremental_ingest_ms": ingest_ms}
                checkpoints.append(checkpoint)
                stage = f"checkpoint-{step['checkpoint']}-billion-setup"
                with BillionKernel(documents, cache, node=node, offline=offline, lock_path=LOCK) as billion:
                    checkpoint["billion_metadata"] = billion.metadata
                    write_json(output / f"checkpoint-{step['checkpoint']}.json", checkpoint)
                    for ordinal, case in enumerate(step["cases"]):
                        stage = f"query-{case['id']}"
                        measurements = {backend: [] for backend in BACKENDS}
                        for repeat in range(repeats):
                            order = BACKENDS if (ordinal + repeat) % 2 == 0 else BACKENDS[::-1]
                            for backend in order:
                                start = time.perf_counter_ns()
                                native = (book_search(book, case["query"], case["project"]) if backend == "book"
                                          else billion.search(case["query"], project=case["project"], limit=5,
                                                              preview_chars=100000))
                                elapsed = (time.perf_counter_ns() - start) / 1e6
                                ids = mapped_ids(native, backend, lookup, case["project"])
                                measurements[backend].append({"repetition": repeat, "adapter_call_ms": elapsed,
                                    "native_search_ms": elapsed if backend == "book" else native["search_ms"],
                                    "native_bridge_ms": elapsed if backend == "book" else native["bridge_ms"],
                                    "hit_ids": ids, "native_sha256": workflow.sha(stable(native)), "native": native})
                        for backend, samples in measurements.items():
                            native_row = {"case_id": case["id"], "backend": backend, "query": case["query"],
                                "project": case["project"], "checkpoint": step["checkpoint"], "samples": samples}
                            native_rows.append(native_row)
                            native_trace.write(json.dumps(native_row, ensure_ascii=False, allow_nan=False) + "\n")
                            native_trace.flush()
                            for budget in budgets:
                                start = time.perf_counter_ns()
                                response = common_pack(samples[0]["hit_ids"], lookup, case["project"], budget)
                                pack_ms = (time.perf_counter_ns() - start) / 1e6
                                row = {"case_id": case["id"], "backend": backend, "category": case["category"],
                                    "project": case["project"], "query": case["query"], "checkpoint": step["checkpoint"],
                                    "budget_chars": budget, "common_pack_ms": pack_ms,
                                    "latency_ms": [sample["adapter_call_ms"] for sample in samples],
                                    "repeat_outputs_equal": len({s["native_sha256"] for s in samples}) == 1,
                                    "native_first_output_sha256": samples[0]["native_sha256"],
                                    "response": response, "score": workflow.score(case, response, sources, budget)}
                                rows.append(row)
                                trace.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                                trace.flush()
            report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
    runtime_after, evaluator_after = workflow.runtime_identity(memory_book), source_identity()
    report.update(runtime_unchanged=runtime_before == runtime_after, evaluator_unchanged=evaluator_before == evaluator_after,
        runtime_final_sha256=runtime_after["sha256"], evaluator_final_sha256=evaluator_after["sha256"],
        case_count=sum(len(step["cases"]) for step in steps), completed_native_query_backend_pairs=len(native_rows),
        checkpoints=checkpoints, summary=workflow.summarize(rows) if rows else [],
        by_category={category: workflow.summarize([row for row in rows if row["category"] == category])
                     for category in sorted({row["category"] for row in rows})})
    report["native_timing"] = {backend: {phase: {
        field: timing([sample[field] for row in native_rows if row["backend"] == backend for sample in row["samples"]
                       if (sample["repetition"] == 0) == (phase == "first_query_search")])
        for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms")}
        for phase in ("first_query_search", "repeat_query_search")} for backend in BACKENDS}
    report["common_pack_timing"] = [{"backend": backend, "budget_chars": budget,
        **(timing([row["common_pack_ms"] for row in rows if row["backend"] == backend and row["budget_chars"] == budget]) or {})}
        for backend in BACKENDS for budget in budgets]
    expected_pairs = report["case_count"] * len(BACKENDS)
    integrity = (report["runtime_unchanged"] and report["evaluator_unchanged"]
                 and len(native_rows) == expected_pairs and len(rows) == expected_pairs * len(budgets)
                 and all(not cell["source_validation_failures"] and not cell["budget_violations"]
                         and not cell["repeat_output_changes"] for cell in report["summary"]))
    report["integrity_passed"] = integrity
    if report["status"] == "completed" and not integrity:
        report["status"] = "completed_with_integrity_failures"
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-chars", nargs="+", type=int, default=[1200, 2400])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    report = run(args.output, budgets=args.budget_chars, repeats=args.repeats, node=args.node,
                 cache=args.cache, offline=args.offline)
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "summary": report["summary"], "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
