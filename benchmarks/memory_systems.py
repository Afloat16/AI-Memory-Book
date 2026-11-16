"""Real, pinned memory/retrieval components on unchanged engineering pages.

Run --prepare, then --self-test, then the replay in a fresh output directory.
The protocol was fixed before quality results; see competitors/memory-systems-plan.md.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid

from benchmarks import engineering_components as components
from benchmarks import engineering_workflow as workflow
from benchmarks.competitors.billion import BillionKernel, prepare as prepare_billion
from benchmarks.competitors.claude_mem import ClaudeMemFTS, prepare as prepare_claude
from benchmarks.competitors.memory_systems import (
    BACKENDS, PYTHON_BACKENDS, LOCK_PATH, PythonComponent, ROOT,
    sanitized_environment, sha_file, stable_native, write_json,
)

VERSION = "engineering-memory-systems-v1"
SOURCE_FILES = tuple(dict.fromkeys((*components.SOURCE_FILES,
    "benchmarks/memory_systems.py", "benchmarks/competitors/claude_mem.py",
    "benchmarks/competitors/claude_mem_bridge.ts",
    "benchmarks/competitors/claude-mem-round2-lock.json",
    "benchmarks/competitors/memory_systems.py",
    "benchmarks/competitors/memory_systems_worker.py",
    "benchmarks/competitors/memory-systems-lock.json",
    "benchmarks/competitors/memory-systems-plan.md",
    "benchmarks/competitors/memory-systems-requirements.in",
    "benchmarks/competitors/memory-systems-requirements.txt",
)))


def source_identity():
    files = {name: sha_file(ROOT / name) for name in SOURCE_FILES}
    return {"files": files, "sha256": workflow.sha(files)}


def fresh_output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError("Use a fresh empty output directory; previous attempts are retained")
    return path


def prepare(cache, *, python=sys.executable, node="node"):
    """Public installation artifacts only; no quality workload is executed."""
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    state = cache / ("prepare-" + uuid.uuid4().hex)
    state.mkdir()
    report = {"status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
              "evaluator": source_identity(), "preparation": {}}
    try:
        result = subprocess.run(
            [str(python), "-m", "benchmarks.competitors.memory_systems_worker", "--prepare",
             "--state", str(state), "--cache", str(cache)],
            cwd=ROOT, env=sanitized_environment(state, cache), capture_output=True,
            text=True, encoding="utf-8", timeout=900, check=False,
        )
        (state / "stderr.log").write_text(result.stderr, encoding="utf-8")
        (state / "stdout.json").write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Python component preparation failed: " + result.stderr[-12000:])
        report["preparation"]["python"] = json.loads(result.stdout)
        billion_lock = ROOT / "benchmarks/competitors/billion-round2-lock.json"
        prepare_billion(cache / "billion", node=node, lock_path=billion_lock)
        report["preparation"]["billion"] = json.loads(billion_lock.read_text())
        report["preparation"]["claude_mem"] = prepare_claude(
            cache / "claude-mem", lock_path=ROOT / "benchmarks/competitors/claude-mem-round2-lock.json")[3]
        report["status"] = "prepared"
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
    write_json(cache / "preparation.json", report)
    write_json(state / "preparation.json", report)
    return report


def make_adapter(backend, book, documents, state, cache, python, node):
    if backend == "book":
        return book
    if backend == "billion":
        return BillionKernel(documents, cache / "billion", node=node, offline=True,
                             lock_path=ROOT / "benchmarks/competitors/billion-round2-lock.json")
    if backend == "claude_mem":
        return ClaudeMemFTS(documents, cache / "claude-mem", state, offline=True,
                            lock_path=ROOT / "benchmarks/competitors/claude-mem-round2-lock.json")
    return PythonComponent(backend, documents, state, cache, python=python)


def native_search(backend, adapter, query, project, documents):
    """Preserve complete upstream output; only validate/match source identity."""
    if backend == "book":
        native = components.book_search(adapter, query, project)
        ids = components.mapped_ids(native, backend, documents, project)
    elif backend == "billion":
        native = adapter.search(query, project=project, limit=5, preview_chars=100000)
        ids = components.mapped_ids(native, backend, documents, project)
    else:
        native = adapter.search(query, project=project, limit=5)
        ids = native["hit_ids"]
    return native, ids


def close_adapters(active, state_root, output, checkpoint, failures):
    for backend, adapter in active.items():
        if backend == "book":
            continue
        try:
            adapter.close()
        except Exception:
            failures.append({"backend": backend, "checkpoint": checkpoint,
                             "stage": "close", "error": traceback.format_exc()})
    # Setup can fail before an adapter enters active. Retain those diagnostics too.
    for backend in BACKENDS:
        for filename in ("stderr.log", "native-stderr.log"):
            source = state_root / backend / filename
            if source.exists():
                shutil.copyfile(source, output / f"checkpoint-{checkpoint}-{backend}-{filename}")


def markdown_report(report):
    lines = ["# Real memory component replay", "",
        f"Status: `{report['status']}`. Protocol: `{VERSION}`.", "",
        "Authored synthetic development cases, no coding LLM and no independent holdout. "
        "Only fully completed, integrity-valid backends appear in the quality table. "
        "Failures and partial rows remain in the JSON and logs.", "",
        "All backends receive the same complete original pages and unchanged questions. "
        "The project filter and top-five candidate boundary precede the unchanged common "
        "whole-block packer. This is separate from native Book excerpt packing.", "",
        "| Component | Chars | Evidence recall | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in report.get("summary", []):
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | {cell['evidence_recall']:.2%} | "
                     f"{cell['complete_evidence_rate']:.2%} | {cell['fixed_consumer_all_checks_pass_rate']:.2%} | "
                     f"{cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "## Interpretation", "",
        "Basic Memory executes explicit native text search rather than its default hybrid workflow. "
        "claude-mem receives raw original observations without its LLM observer; Mem0 uses infer=False "
        "and therefore does not run its default fact extraction. Chroma and LangGraph are retrieval/store "
        "infrastructure, not complete memory products.", "",
        "Chroma, LangGraph and Mem0 share the actual official MiniLM embedding model. Identical or "
        "similar rankings are correlated evidence, not three independent model-quality confirmations. "
        "Native model truncation and native query thresholds remain in force. Neither generated nor "
        "mock embeddings are used.", "",
        "Native timing includes real query embedding where that backend needs it. Model preparation, "
        "indexing and process startup are separate from search and common packing. Python IPC, Bun IPC "
        "and in-process Book timers have different boundaries. No complete-product speed ratio or "
        "developer-productivity claim follows.", "",
        "All budgets, missing-evidence cases, stale-only failures, native outputs and source checks are "
        "retained. A zero match under a component's documented query semantics is not a general defeat "
        "of that complete product. See the fixed protocol and per-checkpoint actual configuration.", ""]
    if report.get("failures"):
        lines += ["## Execution failures", ""]
        for failure in report["failures"]:
            lines.append(f"- {failure.get('backend', 'runner')} / {failure['stage']}: "
                         f"`{failure['error'].splitlines()[-1]}`")
    return "\n".join(lines) + "\n"


def _binding(backends, budgets, repeats):
    import memory_book
    return {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
            "evidence_level": "synthetic_development_real_memory_components",
            "runtime": workflow.runtime_identity(memory_book), "evaluator": source_identity(),
            "upstream_lock": json.loads(LOCK_PATH.read_text()),
            "environment": {"python": sys.version, "platform": platform.platform(),
                            "sqlite": sqlite3.sqlite_version},
            "settings": {"backends": list(backends), "budgets_chars": list(budgets),
                         "repeats": repeats, "limit": 5, "result_cache": False,
                         "packing": "unchanged common_pack; original whole pages; skip oversized blocks",
                         "query_transformation": "none in harness; native component preprocessing only",
                         "shared_embedding_backends": ["chroma", "langgraph", "mem0"]}}


def run(output, cache, *, budgets=(1200, 2400), repeats=3, backends=BACKENDS,
        python=sys.executable, node="node"):
    import memory_book
    from memory_book import MemoryBook

    if (not budgets or len(set(budgets)) != len(budgets)
            or any(type(b) is not int or not 0 < b <= 100000 for b in budgets)):
        raise ValueError("Distinct positive budgets up to 100000 are required")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("repeats must be between 1 and 30")
    if not backends or len(set(backends)) != len(backends) or set(backends) - set(BACKENDS):
        raise ValueError("Select distinct registered backends")
    output, cache = fresh_output(output), Path(cache).resolve()
    run_state = cache / "runs" / uuid.uuid4().hex
    run_state.mkdir(parents=True)
    steps = workflow.workload()
    report = _binding(backends, budgets, repeats)
    report["dataset_sha256"] = workflow.sha(steps)
    write_json(output / "binding.json", report)
    write_json(output / "dataset.json", steps)
    if (cache / "preparation.json").exists():
        shutil.copyfile(cache / "preparation.json", output / "preparation.json")
    rows, native_rows, checkpoints, failures, visible = [], [], [], [], {}
    disabled = set()
    try:
        with ExitStack() as stack:
            book = stack.enter_context(MemoryBook(run_state / "book.db", cache_size=0))
            trace = stack.enter_context((output / "raw.jsonl").open("w", encoding="utf-8"))
            native_trace = stack.enter_context((output / "native.jsonl").open("w", encoding="utf-8"))
            for step in steps:
                checkpoint_id = step["checkpoint"]
                start = time.perf_counter_ns()
                for session in step["sessions"]:
                    book.ingest(session)
                    visible[(session["project"], session["session_id"])] = session
                ingest_ms = (time.perf_counter_ns() - start) / 1e6
                documents = components.export_documents(book, visible)
                lookup = {doc["id"]: doc for doc in documents}
                sources = workflow.visible_sources(visible)
                write_json(output / f"documents-{checkpoint_id}.json", documents)
                checkpoint = {"checkpoint": checkpoint_id, "documents": len(documents),
                              "documents_sha256": workflow.sha(documents),
                              "book_incremental_ingest_ms": ingest_ms, "backends": {}}
                checkpoints.append(checkpoint)
                checkpoint_state = run_state / f"checkpoint-{checkpoint_id}"
                checkpoint_state.mkdir()
                active = {}
                try:
                    for backend in backends:
                        if backend in disabled:
                            continue
                        try:
                            adapter = make_adapter(backend, book, documents, checkpoint_state / backend,
                                                   cache, python, node)
                            active[backend] = adapter
                            checkpoint["backends"][backend] = getattr(adapter, "metadata", {
                                "mode": "native Book selection, common whole-block packing"})
                        except Exception:
                            disabled.add(backend)
                            failures.append({"backend": backend, "checkpoint": checkpoint_id,
                                             "stage": "setup", "error": traceback.format_exc()})
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
                    for ordinal, case in enumerate(step["cases"]):
                        measurements = {b: [] for b in active if b not in disabled}
                        for repeat in range(repeats):
                            order = list(measurements)
                            if (ordinal + repeat) % 2:
                                order.reverse()
                            for backend in order:
                                if backend in disabled:
                                    continue
                                try:
                                    started = time.perf_counter_ns()
                                    native, ids = native_search(backend, active[backend], case["query"],
                                                                case["project"], lookup)
                                    elapsed = (time.perf_counter_ns() - started) / 1e6
                                    measurements[backend].append({
                                        "repetition": repeat, "adapter_call_ms": elapsed,
                                        "native_search_ms": native.get("search_ms", elapsed),
                                        "native_bridge_ms": native.get("bridge_ms", elapsed),
                                        "hit_ids": ids, "native_sha256": workflow.sha(stable_native(native)),
                                        "native": native})
                                except Exception:
                                    disabled.add(backend)
                                    failures.append({"backend": backend, "checkpoint": checkpoint_id,
                                                     "case_id": case["id"], "stage": "query",
                                                     "error": traceback.format_exc()})
                        for backend, samples in measurements.items():
                            native_row = {"case_id": case["id"], "backend": backend,
                                          "query": case["query"], "project": case["project"],
                                          "checkpoint": checkpoint_id, "samples": samples}
                            native_trace.write(json.dumps(native_row, ensure_ascii=False, allow_nan=False) + "\n")
                            native_trace.flush()
                            native_rows.append(native_row)
                            if len(samples) != repeats:
                                continue  # a failed attempt never becomes a zero-scored successful response
                            for budget in budgets:
                                started = time.perf_counter_ns()
                                response = components.common_pack(samples[0]["hit_ids"], lookup,
                                                                  case["project"], budget)
                                row = {"case_id": case["id"], "backend": backend,
                                       "category": case["category"], "project": case["project"],
                                       "query": case["query"], "checkpoint": checkpoint_id,
                                       "budget_chars": budget,
                                       "common_pack_ms": (time.perf_counter_ns() - started) / 1e6,
                                       "latency_ms": [s["adapter_call_ms"] for s in samples],
                                       "repeat_outputs_equal": len({s["native_sha256"] for s in samples}) == 1,
                                       "native_first_output_sha256": samples[0]["native_sha256"],
                                       "response": response,
                                       "score": workflow.score(case, response, sources, budget)}
                                rows.append(row)
                                trace.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                                trace.flush()
                finally:
                    close_adapters(active, checkpoint_state, output, checkpoint_id, failures)
                    disabled.update(f["backend"] for f in failures if "backend" in f)
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
    except Exception:
        failures.append({"stage": "runner", "error": traceback.format_exc()})
    runtime_after, evaluator_after = workflow.runtime_identity(memory_book), source_identity()
    expected_cases = sum(len(s["cases"]) for s in steps)
    statuses, complete_rows = {}, []
    for backend in backends:
        own = [row for row in rows if row["backend"] == backend]
        complete = len(own) == expected_cases * len(budgets) and backend not in disabled
        integrity = complete and all(not row["score"]["source_errors"]
                                     and row["score"]["within_budget"]
                                     and row["repeat_outputs_equal"] for row in own)
        statuses[backend] = {"status": "completed" if integrity else "failed_or_incomplete",
                             "packed_rows": len(own), "expected_packed_rows": expected_cases * len(budgets)}
        if integrity:
            complete_rows.extend(own)
    report.update(
        status="completed" if all(v["status"] == "completed" for v in statuses.values()) and not failures
               else "completed_with_backend_failures",
        runtime_unchanged=report["runtime"] == runtime_after,
        evaluator_unchanged=report["evaluator"] == evaluator_after,
        runtime_final_sha256=runtime_after["sha256"], evaluator_final_sha256=evaluator_after["sha256"],
        case_count=expected_cases, backend_status=statuses, failures=failures,
        checkpoints=checkpoints, completed_native_query_backend_pairs=len(native_rows),
        summary=workflow.summarize(complete_rows) if complete_rows else [],
        partial_summary=workflow.summarize([r for r in rows if statuses[r["backend"]]["status"] != "completed"])
                        if any(statuses[r["backend"]]["status"] != "completed" for r in rows) else [],
        by_category={cat: workflow.summarize([r for r in complete_rows if r["category"] == cat])
                     for cat in sorted({r["category"] for r in complete_rows})},
    )
    report["native_timing"] = {backend: {phase: {
        field: components.timing([s[field] for row in native_rows if row["backend"] == backend
                                  for s in row["samples"]
                                  if (s["repetition"] == 0) == (phase == "first_query_search")])
        for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms")}
        for phase in ("first_query_search", "repeat_query_search")} for backend in backends}
    report["integrity_passed"] = (report["status"] == "completed"
                                  and report["runtime_unchanged"] and report["evaluator_unchanged"])
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def self_test(output, cache, *, python=sys.executable, node="node", backends=BACKENDS):
    """Real upstream calls on tiny API/provenance fixtures, not workload tuning."""
    from memory_book import MemoryBook

    output, cache = fresh_output(output), Path(cache).resolve()
    state = cache / "smoke" / uuid.uuid4().hex
    state.mkdir(parents=True)
    fixtures = [
        {"project": "scope-alpha", "session_id": "same-session", "task_id": "contract",
         "created_at": "2026-01-01T00:00:00Z", "messages": [
             {"role": "user", "content": "memorytoken_alpha source contract"},
             {"role": "assistant", "content": "memorytoken_alpha uses unique value ALPHA17."}]},
        {"project": "scope-beta", "session_id": "same-session", "task_id": "contract",
         "created_at": "2026-01-01T00:00:00Z", "messages": [
             {"role": "user", "content": "memorytoken_alpha source contract"},
             {"role": "assistant", "content": "memorytoken_alpha uses foreign value BETA91."}]},
    ]
    report = {"status": "started", "scope": "API execution and provenance, no engineering quality score",
              "evaluator": source_identity(), "backends": {}, "failures": []}
    with MemoryBook(state / "book.db", cache_size=0) as book:
        visible = {}
        for session in fixtures:
            book.ingest(session)
            visible[(session["project"], session["session_id"])] = session
        docs = components.export_documents(book, visible)
        lookup = {d["id"]: d for d in docs}
        write_json(output / "documents.json", docs)
        for backend in backends:
            active = {}
            item = {"samples": [], "checks": {}}
            report["backends"][backend] = item
            try:
                adapter = make_adapter(backend, book, docs, state / backend, cache, python, node)
                active[backend] = adapter
                item["metadata"] = getattr(adapter, "metadata", {})
                for project in ("scope-alpha", "scope-beta", "absent-project"):
                    native, ids = native_search(backend, adapter, "memorytoken_alpha", project, lookup)
                    if project == "absent-project":
                        if ids:
                            raise AssertionError("Unknown project returned evidence")
                    elif not ids or any(lookup[i]["project"] != project for i in ids):
                        raise AssertionError("Native original-page/project smoke failed")
                    item["samples"].append({"project": project, "native": native, "hit_ids": ids})
                item["checks"] = {"actual_upstream_calls": True, "known_projects_have_original_evidence": True,
                                  "missing_project_is_empty": True, "source_mapping": True}
                item["status"] = "passed"
            except Exception:
                item["status"] = "failed"
                report["failures"].append({"backend": backend, "stage": "smoke", "error": traceback.format_exc()})
            finally:
                close_adapters(active, state, output, "smoke", report["failures"])
                write_json(output / f"{backend}.json", item)
    report["status"] = "passed" if not report["failures"] else "failed"
    write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--budget-chars", nargs="+", type=int, default=[1200, 2400])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS))
    parser.add_argument("--backend-python", default=sys.executable)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    if args.prepare:
        if args.self_test or args.output:
            parser.error("--prepare uses --cache only, separately from output runs")
        report = prepare(args.cache, python=args.backend_python, node=args.node)
    elif args.output is None:
        parser.error("--output is required for self-test or replay")
    elif args.self_test:
        report = self_test(args.output, args.cache, python=args.backend_python,
                           node=args.node, backends=args.backends)
    else:
        report = run(args.output, args.cache, budgets=args.budget_chars, repeats=args.repeats,
                     backends=args.backends, python=args.backend_python, node=args.node)
    print(json.dumps({"status": report["status"], "output": str(args.output or args.cache),
                      "backend_status": report.get("backend_status"),
                      "failure_count": len(report.get("failures", [])),
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] in {"completed", "passed", "prepared"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
