"""Additional real lexical components on the frozen engineering development set.

The workload, whole-block packer and scorer are imported without changes. Read
competitors/extended-lexical-plan.md before executing a fresh output directory.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback

from benchmarks import engineering_components as components
from benchmarks import engineering_workflow as workflow
from benchmarks.competitors.extended_lexical import (
    BACKENDS, LOCK_PATH, ExtendedLexical, memvid_record, result_identity,
)
from benchmarks.competitors.memory_systems import ROOT, sha_file, validate_response, write_json

VERSION = "engineering-extended-lexical-v1"
SOURCE_FILES = tuple(dict.fromkeys((*components.SOURCE_FILES,
    "benchmarks/extended_components.py", "benchmarks/competitors/extended_lexical.py",
    "benchmarks/competitors/extended-lexical-lock.json",
    "benchmarks/competitors/extended-lexical-plan.md",
    "benchmarks/competitors/extended-lexical-requirements.txt",
    "benchmarks/competitors/memory_systems.py",
    "benchmarks/competitors/memory_systems_worker.py",
)))


def source_identity():
    files = {name: sha_file(ROOT / name) for name in SOURCE_FILES}
    return {"files": files, "sha256": workflow.sha(files)}


def runtime_identity(module):
    root = Path(inspect.getfile(module)).resolve().parent
    files = {str(path.relative_to(root)): sha_file(path) for path in sorted(root.iterdir())
             if path.is_file() and (path.suffix in (".py", ".c", ".h", ".so", ".pyd", ".dll", ".dylib"))}
    from memory_book._text_backend import BACKEND_NAME
    return {"root": str(root), "version": module.__version__, "backend": BACKEND_NAME,
            "files": files, "sha256": workflow.sha(files),
            "purpose": "fixture-page materialization only; Book retrieval is not timed or scored here"}


def fresh_output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError("Use a fresh empty output directory; earlier attempts remain unchanged")
    return path


def append(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def validate_native(backend, native, documents, project):
    """Independently reconstruct mapped records from complete upstream payloads."""
    ids = validate_response(native, documents, project)
    if len(native["scores"]) != len(ids):
        raise ValueError("Native score count differs from result identities")
    if backend == "haystack_bm25":
        rows = native["native_payload"]["documents"]
        expected = [{"id": row["id"], "project": row["project"], "text": row["content"]}
                    for row in rows]
        scores = [row["score"] for row in rows]
    elif backend == "bm25s":
        payload = native["native_payload"]
        if payload.get("absent_namespace"):
            if any(doc["project"] == project for doc in documents.values()):
                raise ValueError("BM25S claimed a present namespace was absent")
            expected, scores = [], []
        else:
            rows = payload["results"][0]
            expected = [{"id": row["id"], "project": row["project"], "text": row["text"]} for row in rows]
            scores = payload["scores"][0]
    elif backend == "memvid_lex":
        hits, frames = native["native_payload"]["hits"], native["native_frames"]
        if len(hits) != len(frames):
            raise ValueError("Memvid native frame count differs from hit count")
        expected = [memvid_record(hit, frame, documents, project) for hit, frame in zip(hits, frames)]
        scores = [hit["score"] for hit in hits]
        if hits and native["native_payload"].get("engine") != "tantivy":
            raise ValueError("Memvid did not execute the registered Tantivy lexical engine")
    else:
        raise ValueError("Unknown native payload format")
    if expected != native["records"] or scores != native["scores"]:
        raise ValueError("Mapped records or scores differ from complete upstream output")
    return ids


def markdown_report(report):
    lines = ["# Additional upstream lexical component replay", "",
        f"Status: `{report['status']}`. Protocol: `{VERSION}`.", "",
        "Authored synthetic development data; 80 unchanged questions, including eight missing-evidence "
        "questions. This is a supplied-page ranking and common whole-block packing comparison, "
        "not a held-out test, generated answer accuracy, or complete memory product benchmark.", "",
        "| Actual upstream mode | Chars | Evidence recall | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in report.get("summary", []):
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | {cell['evidence_recall']:.2%} | "
                     f"{cell['complete_evidence_rate']:.2%} | {cell['fixed_consumer_all_checks_pass_rate']:.2%} | "
                     f"{cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "Haystack is a retrieval framework component; BM25S is a lexical library; "
        "Memvid is tested only in explicit lexical mode. All three execute unmodified pinned "
        "upstream code. Each receives the same original page bodies and project scope. "
        "Indexed metadata and native tokenization remain backend-specific.", "",
        "Memvid normalizes whitespace and adds known metadata framing in native hits. Every "
        "complete indexed body and frame identity is checked before the common packer restores "
        "the supplied original page. This is not a test of byte-exact Memvid native source reads.", "",
        "Setup/indexing, in-worker search and process roundtrip durations are retained for diagnosis. "
        "No speed ranking or whole-product performance claim is made. Repetitions are not additional "
        "quality examples. Missing-evidence queries are reported without relabelling context as an answer.", ""]
    if report.get("failures"):
        lines += ["## Retained failures", ""]
        for failure in report["failures"]:
            lines.append(f"- {failure.get('backend', 'runner')}: {failure['stage']} — see complete JSON traceback.")
    return "\n".join(lines)


def close_adapters(active, state, output, checkpoint, failures):
    for backend, adapter in active.items():
        try:
            adapter.close()
        except Exception:
            failures.append({"backend": backend, "checkpoint": checkpoint,
                             "stage": "close", "error": traceback.format_exc()})
    for backend in BACKENDS:
        path = state / backend / "stderr.log"
        if path.exists():
            shutil.copyfile(path, output / f"checkpoint-{checkpoint}-{backend}-stderr.log")


def run(output, *, python=sys.executable, backends=BACKENDS, budgets=(1200, 2400), repeats=3):
    import memory_book
    from memory_book import MemoryBook

    if not backends or len(set(backends)) != len(backends) or set(backends) - set(BACKENDS):
        raise ValueError("Select distinct registered external backends")
    if (not budgets or len(set(budgets)) != len(budgets)
            or any(type(value) is not int or not 0 < value <= 100000 for value in budgets)):
        raise ValueError("Choose distinct positive character budgets up to 100000")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("Choose between one and thirty repetitions")
    output = fresh_output(output)
    steps = workflow.workload()
    report = {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
              "evidence_level": "authored-development-supplied-page-components",
              "dataset_sha256": workflow.sha(steps), "runtime": runtime_identity(memory_book),
              "evaluator": source_identity(), "lock": json.loads(LOCK_PATH.read_text(encoding="utf-8")),
              "settings": {"backends": list(backends), "budgets_chars": list(budgets), "repeats": repeats,
                           "top_k": 5, "query_rewrite": False, "noise_per_step": 2,
                           "packing": "frozen common whole-block packer; original supplied pages",
                           "stability": "ordered IDs, recovered full bodies/project and exact upstream scores"},
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "sqlite": sqlite3.sqlite_version, "backend_python": str(python)}}
    write_json(output / "binding.json", report)
    write_json(output / "dataset.json", steps)
    visible, rows, native_rows, checkpoints, failures, disabled = {}, [], [], [], [], set()
    stage = "initialize"
    try:
        with ExitStack() as stack:
            state_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="state-", dir=output)))
            book = stack.enter_context(MemoryBook(state_root / "book.db", cache_size=0))
            raw_trace = stack.enter_context((output / "raw.jsonl").open("w", encoding="utf-8"))
            native_trace = stack.enter_context((output / "native.jsonl").open("w", encoding="utf-8"))
            attempts = stack.enter_context((output / "attempts.jsonl").open("w", encoding="utf-8"))
            for step in steps:
                checkpoint_id = step["checkpoint"]
                stage = f"checkpoint-{checkpoint_id}-ingest"
                for session in step["sessions"]:
                    book.ingest(session)
                    visible[(session["project"], session["session_id"])] = session
                documents = components.export_documents(book, visible)
                lookup, sources = {doc["id"]: doc for doc in documents}, workflow.visible_sources(visible)
                write_json(output / f"documents-{checkpoint_id}.json", documents)
                checkpoint = {"checkpoint": checkpoint_id, "documents": len(documents),
                              "documents_sha256": workflow.sha(documents), "backends": {}}
                checkpoints.append(checkpoint)
                state, active = state_root / str(checkpoint_id), {}
                try:
                    for backend in backends:
                        if backend in disabled:
                            continue
                        append(attempts, {"event": "setup_started", "checkpoint": checkpoint_id, "backend": backend})
                        try:
                            adapter = ExtendedLexical(backend, documents, state / backend, python=python)
                            active[backend] = adapter
                            checkpoint["backends"][backend] = adapter.metadata
                            append(attempts, {"event": "setup_completed", "checkpoint": checkpoint_id, "backend": backend})
                        except Exception:
                            disabled.add(backend)
                            failure = {"backend": backend, "checkpoint": checkpoint_id,
                                       "stage": "setup", "error": traceback.format_exc()}
                            failures.append(failure)
                            append(attempts, {"event": "failed", **failure})
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
                    for ordinal, case in enumerate(step["cases"]):
                        stage = f"query-{case['id']}"
                        measurements = {backend: [] for backend in active if backend not in disabled}
                        for repeat in range(repeats):
                            order = list(measurements)
                            if (ordinal + repeat) % 2:
                                order.reverse()
                            for backend in order:
                                if backend in disabled:
                                    continue
                                event = {"backend": backend, "checkpoint": checkpoint_id,
                                         "case_id": case["id"], "repetition": repeat}
                                append(attempts, {"event": "query_started", **event})
                                try:
                                    start = time.perf_counter_ns()
                                    native = active[backend].search(case["query"], case["project"], 5)
                                    elapsed = (time.perf_counter_ns() - start) / 1e6
                                    ids = validate_native(backend, native, lookup, case["project"])
                                    sample = {"repetition": repeat, "adapter_call_ms": elapsed,
                                              "native_search_ms": native["search_ms"],
                                              "native_bridge_ms": native["bridge_ms"],
                                              "hit_ids": ids, "native_result_sha256": result_identity(native),
                                              "native": native}
                                    measurements[backend].append(sample)
                                    append(attempts, {"event": "query_completed", **event, "sample": sample})
                                except Exception:
                                    disabled.add(backend)
                                    failure = {**event, "stage": "query", "error": traceback.format_exc()}
                                    failures.append(failure)
                                    append(attempts, {"event": "failed", **failure})
                        for backend, samples in measurements.items():
                            if not samples:
                                continue
                            native_row = {"case_id": case["id"], "backend": backend, "query": case["query"],
                                          "project": case["project"], "checkpoint": checkpoint_id, "samples": samples}
                            native_rows.append(native_row)
                            append(native_trace, native_row)
                            for budget in budgets:
                                response = components.common_pack(samples[0]["hit_ids"], lookup, case["project"], budget)
                                row = {"case_id": case["id"], "backend": backend, "category": case["category"],
                                       "project": case["project"], "query": case["query"], "checkpoint": checkpoint_id,
                                       "budget_chars": budget, "latency_ms": [s["adapter_call_ms"] for s in samples],
                                       "repeat_outputs_equal": len(samples) == repeats and len({s["native_result_sha256"] for s in samples}) == 1,
                                       "response": response, "score": workflow.score(case, response, sources, budget)}
                                rows.append(row)
                                append(raw_trace, row)
                finally:
                    close_adapters(active, state, output, checkpoint_id, failures)
                    disabled.update(failure["backend"] for failure in failures if "backend" in failure)
    except BaseException:
        failures.append({"stage": stage, "error": traceback.format_exc()})
    runtime_after, evaluator_after = runtime_identity(memory_book), source_identity()
    expected_cases = sum(len(step["cases"]) for step in steps)
    statuses, complete_rows = {}, []
    for backend in backends:
        own = [row for row in rows if row["backend"] == backend]
        complete = len(own) == expected_cases * len(budgets) and backend not in disabled
        integrity = complete and all(not row["score"]["source_errors"] and row["score"]["within_budget"]
                                     and row["repeat_outputs_equal"] for row in own)
        statuses[backend] = {"status": "completed" if integrity else "failed_or_incomplete",
                             "packed_rows": len(own), "expected_packed_rows": expected_cases * len(budgets)}
        if integrity:
            complete_rows.extend(own)
    report.update(status="completed" if all(s["status"] == "completed" for s in statuses.values()) and not failures
                  else "completed_with_backend_failures", case_count=expected_cases,
                  runtime_unchanged=report["runtime"] == runtime_after,
                  evaluator_unchanged=report["evaluator"] == evaluator_after,
                  backend_status=statuses, checkpoints=checkpoints, failures=failures,
                  completed_native_query_backend_pairs=len(native_rows),
                  summary=workflow.summarize(complete_rows) if complete_rows else [],
                  by_category={category: workflow.summarize([row for row in complete_rows if row["category"] == category])
                               for category in sorted({row["category"] for row in complete_rows})})
    report["integrity_passed"] = (report["status"] == "completed" and report["runtime_unchanged"]
                                  and report["evaluator_unchanged"])
    if not report["runtime_unchanged"] or not report["evaluator_unchanged"]:
        report["status"] = "completed_with_integrity_failures"
        report["unverified_summary"] = report.pop("summary")
        report["summary"] = []
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def self_test(output, *, python=sys.executable, backends=BACKENDS):
    """Tiny identity/scope/API fixture, with no scored engineering questions."""
    output = fresh_output(output)
    documents = [{"id": "page-" + str(index), "project": project, "title": "API smoke",
                  "text": f"USER: scope_marker valve\n\nASSISTANT: marker_value={color}; 保留原文。",
                  "created_at": "2026-01-01T09:00:00+00:00"}
                 for index, (project, color) in enumerate((
                     ("scope-alpha", "crimson"), ("scope-alpha/child", "cobalt"), ("scope-beta", "amber")))]
    lookup, failures, active = {doc["id"]: doc for doc in documents}, [], {}
    report = {"status": "started", "scope": "API and source identity smoke only; no benchmark score",
              "evaluator": source_identity(), "backends": {}, "limitations": []}
    write_json(output / "documents.json", documents)
    with tempfile.TemporaryDirectory(prefix="state-", dir=output) as temporary:
        state = Path(temporary)
        try:
            for backend in backends:
                item = {"status": "started", "samples": []}
                report["backends"][backend] = item
                try:
                    adapter = ExtendedLexical(backend, documents, state / backend, python=python)
                    active[backend] = adapter
                    item["metadata"] = adapter.metadata
                    for project in ("scope-alpha", "scope-alpha/child", "scope-beta", "absent-project"):
                        try:
                            native = adapter.search("scope_marker", project, 5)
                        except RuntimeError as error:
                            if (backend != "memvid_lex" or project != "absent-project"
                                    or "memvid_sdk.LexIndexDisabledError: MV004: Lexical index is not enabled" not in str(error)):
                                raise
                            limitation = {"backend": backend, "project": project,
                                          "scope": "unknown project native API error; not converted to an empty native result",
                                          "error": traceback.format_exc()}
                            report["limitations"].append(limitation)
                            item["samples"].append({"project": project, "native_error": limitation["error"]})
                            continue
                        ids = validate_native(backend, native, lookup, project)
                        expected = [doc["id"] for doc in documents if doc["project"] == project]
                        if ids != expected:
                            raise AssertionError("Native scope fixture did not return exactly its source page")
                        item["samples"].append({"project": project, "native": native})
                    item["status"] = ("passed_known_scope_with_documented_unknown_scope_error"
                                      if any(entry["backend"] == backend for entry in report["limitations"])
                                      else "passed")
                except Exception:
                    item["status"] = "failed"
                    failures.append({"backend": backend, "stage": "API smoke", "error": traceback.format_exc()})
                write_json(output / f"{backend}.json", item)
        finally:
            close_adapters(active, state, output, "smoke", failures)
    report.update(status=("passed_with_documented_limitations" if report["limitations"] else "passed")
                  if not failures else "failed", failures=failures)
    write_json(output / "report.json", report)
    return report


def audit(output):
    """Recompute every native mapping, packed response and evidence score offline."""
    output = Path(output)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    steps = json.loads((output / "dataset.json").read_text(encoding="utf-8"))
    if workflow.sha(steps) != report["dataset_sha256"] or steps != workflow.workload():
        raise ValueError("Dataset is not the frozen engineering workload")
    if report["evaluator"] != source_identity():
        raise ValueError("Evaluator closure changed after the recorded run")
    native_rows = [json.loads(line) for line in (output / "native.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text(encoding="utf-8").splitlines()]
    native_lookup = {(row["backend"], row["case_id"]): row for row in native_rows}
    row_lookup = {(row["backend"], row["case_id"], row["budget_chars"]): row for row in rows}
    if len(native_lookup) != len(native_rows) or len(row_lookup) != len(rows):
        raise ValueError("Duplicate evidence rows")
    visible, checked, native_calls = {}, 0, 0
    for step in steps:
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"])] = session
        documents = json.loads((output / f"documents-{step['checkpoint']}.json").read_text(encoding="utf-8"))
        lookup = {doc["id"]: doc for doc in documents}
        sources = workflow.visible_sources(visible)
        seen = set()
        for doc in documents:
            if len(doc.get("source_refs", [])) != 1:
                raise ValueError("Supplied page does not contain exactly one source turn")
            ref = doc["source_refs"][0]
            identity = (ref["project"], ref["session_id"], ref["turn_index"])
            if (identity in seen or identity not in sources or doc["text"] != sources[identity]
                    or ref["turn_start"] != 0 or ref["turn_end"] != len(sources[identity])
                    or doc["project"] != identity[0]):
                raise ValueError("Supplied page differs from complete visible original source")
            seen.add(identity)
        if seen != set(sources) or len(lookup) != len(documents):
            raise ValueError("Supplied page bundle omits/repeats/adds a source")
        checkpoint = next(c for c in report["checkpoints"] if c["checkpoint"] == step["checkpoint"])
        if workflow.sha(documents) != checkpoint["documents_sha256"]:
            raise ValueError("Supplied page bundle digest mismatch")
        for case in step["cases"]:
            for backend in report["settings"]["backends"]:
                native_row = native_lookup[(backend, case["id"])]
                if len(native_row["samples"]) != report["settings"]["repeats"]:
                    raise ValueError("Missing native repetitions")
                identities = set()
                for sample in native_row["samples"]:
                    ids = validate_native(backend, sample["native"], lookup, case["project"])
                    digest = result_identity(sample["native"])
                    if ids != sample["hit_ids"] or digest != sample["native_result_sha256"]:
                        raise ValueError("Native mapping/digest changed")
                    identities.add(digest)
                    native_calls += 1
                for budget in report["settings"]["budgets_chars"]:
                    row = row_lookup[(backend, case["id"], budget)]
                    response = components.common_pack(native_row["samples"][0]["hit_ids"], lookup, case["project"], budget)
                    score = workflow.score(case, response, sources, budget)
                    if (response != row["response"] or score != row["score"]
                            or row["repeat_outputs_equal"] != (len(identities) == 1)):
                        raise ValueError("Packed response, score or stability differs")
                    checked += 1
    if workflow.summarize(rows) != report["summary"]:
        raise ValueError("Summary differs from independent row recomputation")
    return {"status": "verified", "packed_responses": checked, "native_calls": native_calls,
            "dataset_sha256": report["dataset_sha256"], "evaluator_sha256": report["evaluator"]["sha256"],
            "files": {path.name: sha_file(path) for path in sorted(output.iterdir())
                      if path.is_file() and path.name != "audit.json"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend-python", default=sys.executable)
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS))
    parser.add_argument("--budget-chars", nargs="+", type=int, default=[1200, 2400])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.audit:
        report = audit(args.output)
        write_json(args.output / "audit.json", report)
    elif args.self_test:
        report = self_test(args.output, python=args.backend_python, backends=args.backends)
    else:
        report = run(args.output, python=args.backend_python, backends=args.backends,
                     budgets=tuple(args.budget_chars), repeats=args.repeats)
    print(json.dumps({key: report[key] for key in ("status", "integrity_passed", "backend_status", "summary",
                                                   "packed_responses", "native_calls") if key in report}, indent=2))
    return 0 if report["status"] in ("passed", "passed_with_documented_limitations", "verified", "completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
