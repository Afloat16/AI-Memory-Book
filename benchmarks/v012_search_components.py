"""Actual LanceDB and Whoosh components on the unchanged engineering development set.

The workload, whole-block packer and scorer are imported without changes. Read
competitors/v012_search_components.protocol.md before executing a fresh output directory.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import inspect
import hashlib
import math
import subprocess
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
from benchmarks.competitors.v012_search_components import (
    BACKENDS, LOCK_PATH, SearchComponents, result_identity,
)
from benchmarks.competitors.memory_systems import ROOT, sha_file, validate_response, write_json

VERSION = "engineering-v012-search-components-v1"
MATERIALIZER_COMMIT = "78cc906d81818a16884de7de2e613e5a56346f93"
SOURCE_FILES = tuple(dict.fromkeys((*components.SOURCE_FILES,
    "benchmarks/v012_search_components.py", "benchmarks/competitors/v012_search_components.py",
    "benchmarks/competitors/v012_search_components.lock.json",
    "benchmarks/competitors/v012_search_components.protocol.md",
    "benchmarks/competitors/memory_systems.py",
    "benchmarks/competitors/memory_systems_worker.py",
)))


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def source_identity(commit=None, *, require_committed=False):
    commit = commit or git(ROOT, "rev-parse", "HEAD").decode().strip()
    files = {name: sha_file(ROOT / name) for name in SOURCE_FILES}
    if Path(inspect.getfile(workflow)).resolve() != ROOT / "benchmarks/engineering_workflow.py":
        raise ValueError("Loaded workload outside the bound evaluator")
    if Path(inspect.getfile(components)).resolve() != ROOT / "benchmarks/engineering_components.py":
        raise ValueError("Loaded common packer outside the bound evaluator")
    if Path(inspect.getfile(SearchComponents)).resolve() != ROOT / "benchmarks/competitors/v012_search_components.py":
        raise ValueError("Loaded adapter outside the bound evaluator")
    if require_committed:
        for name, digest in files.items():
            if hashlib.sha256(git(ROOT, "show", commit + ":" + name)).hexdigest() != digest:
                raise ValueError("Evaluator bytes differ from frozen commit: " + name)
    return {"commit": commit if require_committed else None,
            "binding": "exact-committed-bytes" if require_committed else "working-tree-api-smoke-only",
            "files": files, "sha256": workflow.sha(files)}


def runtime_identity(module):
    root = Path(inspect.getfile(module)).resolve().parent
    checkout = root.parent.parent
    if root != checkout / "src/memory_book":
        raise ValueError("Expected the immutable materializer source checkout")
    if git(checkout, "rev-parse", "HEAD").decode().strip() != MATERIALIZER_COMMIT:
        raise ValueError("Fixture materializer is not the preregistered v0.11 source")
    names = git(checkout, "ls-tree", "-r", "--name-only", MATERIALIZER_COMMIT,
                "src/memory_book").decode().splitlines()
    files = {}
    for name in names:
        actual = (checkout / name).read_bytes()
        if actual != git(checkout, "show", MATERIALIZER_COMMIT + ":" + name):
            raise ValueError("Materializer source differs from immutable Git bytes: " + name)
        files[name] = hashlib.sha256(actual).hexdigest()
    from memory_book import _text_backend
    if (_text_backend.BACKEND_NAME != "native" or _text_backend.NATIVE is None
            or Path(_text_backend.NATIVE.__file__).resolve().parent != root):
        raise ValueError("Materializer must use its own loaded native backend")
    binary = Path(_text_backend.NATIVE.__file__).resolve()
    return {"root": str(root), "commit": MATERIALIZER_COMMIT, "version": module.__version__,
            "backend": _text_backend.BACKEND_NAME, "files": files, "sha256": workflow.sha(files),
            "native_binary": {"path": str(binary), "sha256": sha_file(binary)},
            "purpose": "original fixture-page materialization only; Book recall is not scored here"}

def fresh_output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError("Use a fresh empty output directory; earlier attempts remain unchanged")
    return path


def append(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def validate_native(backend, native, documents, project, query=None):
    """Reconstruct records from complete upstream rows, independently of mappings."""
    ids = validate_response(native, documents, project)
    request = native.get("request", {})
    if request.get("project") != project or request.get("limit") != 5 or (query is not None and request.get("query") != query):
        raise ValueError("Native request changed original query, project or limit")
    if native.get("network_attempts") != 0:
        raise ValueError("Native worker network tripwire was violated")
    if backend == "lancedb_fts":
        rows = native["native_payload"]["rows"]
        scores = [row["_score"] for row in rows]
    elif backend == "whoosh_bm25f_or":
        payload = native["native_payload"]
        rows = [hit["fields"] for hit in payload["hits"]]
        scores = [hit["score"] for hit in payload["hits"]]
        if payload["scored_length"] != len(rows):
            raise ValueError("Whoosh scored result count differs")
    else:
        raise ValueError("Unknown native payload format")
    expected = [{key: row[key] for key in ("id", "project", "text")} for row in rows]
    if expected != native["records"] or scores != native["scores"] or len(scores) != len(ids):
        raise ValueError("Mapped records or scores differ from full upstream output")
    for row, identity, score in zip(rows, ids, scores):
        if any(row[key] != documents[identity][key] for key in ("id", "project", "title", "text", "created_at")):
            raise ValueError("Native full stored fields differ from supplied original page")
        if type(score) not in (int, float) or not math.isfinite(score):
            raise ValueError("Invalid native score")
    return ids

def markdown_report(report):
    lines = ["# Additional actual search components", "",
             f"Status: `{report['status']}`. Protocol: `{VERSION}`.", "",
             "LanceDB native FTS and Whoosh BM25F with an explicitly declared OR parser. "
             "Authored development data; 80 original questions, six checkpoints and a fixed common "
             "whole-block packer. No generated answers, held-out generalization or full-product ranking.", "",
             "| Actual component | Chars | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean chars |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in report.get("summary", []):
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | {cell['evidence_recall']:.2%} | "
                     f"{cell['complete_evidence_rate']:.2%} | {cell['fixed_consumer_all_checks_pass_rate']:.2%} | "
                     f"{cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines += ["", "Each native query is sent unchanged, with exact project scope applied before the five-result limit. "
              "Complete original stored fields and native scores are preserved and verified before packing. "
              "Three repeats are stability observations, not new independent questions. Setup/search/transport "
              "timings are retained for diagnosis; no speed claim is registered.", "",
              "Whoosh's OrGroup is an explicit configuration; its QueryParser default is AND. "
              "Neither component is a complete engineering-memory product. Empty original native results are "
              "preserved without rewritten replacement queries or adapter-level score thresholds.", ""]
    if report.get("failures"):
        lines += ["## Retained failures", ""]
        lines.extend(f"- {failure.get('backend', 'runner')}: {failure['stage']} — see original traceback."
                     for failure in report["failures"])
    return "\n".join(lines)

def close_adapters(active, state, output, checkpoint, failures, checkpoint_record=None):
    for backend, adapter in active.items():
        try:
            verification = adapter.verify_packages()
            if verification["packages"] != adapter.metadata["packages"] or verification["packages_unchanged"] is not True:
                raise ValueError("Upstream package closure changed")
            if checkpoint_record is not None:
                checkpoint_record["backends"][backend]["final_verification"] = verification
        except Exception:
            failures.append({"backend": backend, "checkpoint": checkpoint,
                             "stage": "final package verification", "error": traceback.format_exc()})
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

    if tuple(backends) != BACKENDS or tuple(budgets) != (1200, 2400) or repeats != 3:
        raise ValueError("Quality execution requires the entire preregistered two-component matrix")
    output = fresh_output(output)
    steps = workflow.workload()
    report = {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
              "evidence_level": "authored-development-supplied-page-components",
              "dataset_sha256": workflow.sha(steps), "runtime": runtime_identity(memory_book),
              "evaluator": source_identity(require_committed=True), "lock": json.loads(LOCK_PATH.read_text(encoding="utf-8")),
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
                            adapter = SearchComponents(backend, documents, state / backend, python=python)
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
                                    ids = validate_native(backend, native, lookup, case["project"], case["query"])
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
                    close_adapters(active, state, output, checkpoint_id, failures, checkpoint)
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
                    disabled.update(failure["backend"] for failure in failures if "backend" in failure)
    except BaseException:
        failures.append({"stage": stage, "error": traceback.format_exc()})
    runtime_after = runtime_identity(memory_book)
    evaluator_after = source_identity(commit=report["evaluator"]["commit"], require_committed=True)
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
                  runtime_after=runtime_after, evaluator_after=evaluator_after,
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
    """Only arbitrary marker pages; original engineering questions are not used."""
    output = fresh_output(output)
    projects = ("scope-alpha", "scope-alpha/child", "scope-alpha' OR 1=1 --", "scope-beta")
    documents = [{"id": "page-" + str(index), "project": project, "title": "API smoke",
                  "text": f"USER: scope_marker valve\n\nASSISTANT: marker_value={index}; 保留原文。",
                  "created_at": "2026-01-01T09:00:00+00:00"}
                 for index, project in enumerate((*projects, *(["scope-beta"] * 8)))]
    lookup, failures, active = {doc["id"]: doc for doc in documents}, [], {}
    report = {"status": "started", "scope": "API, complete-source and exact-scope smoke only; no quality score",
              "evaluator": source_identity(), "backends": {}}
    write_json(output / "documents.json", documents)
    with tempfile.TemporaryDirectory(prefix="state-", dir=output) as temporary:
        state = Path(temporary)
        try:
            for backend in backends:
                item = {"status": "started", "samples": []}
                report["backends"][backend] = item
                try:
                    adapter = SearchComponents(backend, documents, state / backend, python=python)
                    active[backend] = adapter
                    item["metadata"] = adapter.metadata
                    for project in (*projects, "absent-project"):
                        native = adapter.search("scope_marker", project, 5)
                        ids = validate_native(backend, native, lookup, project, "scope_marker")
                        expected = {doc["id"] for doc in documents if doc["project"] == project}
                        if len(ids) != min(5, len(expected)) or not set(ids) <= expected:
                            raise AssertionError("Native exact scope or top-five boundary differs")
                        item["samples"].append({"project": project, "native": native})
                    item["final_verification"] = adapter.verify_packages()
                    item["status"] = "passed"
                except Exception:
                    item["status"] = "failed"
                    failures.append({"backend": backend, "stage": "API smoke", "error": traceback.format_exc()})
                write_json(output / f"{backend}.json", item)
        finally:
            close_adapters(active, state, output, "smoke", failures)
    report.update(status="passed" if not failures else "failed", failures=failures)
    write_json(output / "report.json", report)
    return report

def audit_inventory(steps, settings, native_rows, rows):
    """Require the exact registered case inventory and original request labels."""
    cases = {case["id"]: case for step in steps for case in step["cases"]}
    backends, budgets, repeats = settings["backends"], settings["budgets_chars"], settings["repeats"]
    if (not backends or len(set(backends)) != len(backends) or set(backends) - set(BACKENDS)
            or not budgets or len(set(budgets)) != len(budgets)
            or any(type(budget) is not int or not 0 < budget <= 100000 for budget in budgets)
            or type(repeats) is not int or not 1 <= repeats <= 30 or settings["top_k"] != 5):
        raise ValueError("Report settings violate the registered component contract")
    native_lookup = {(row["backend"], row["case_id"]): row for row in native_rows}
    row_lookup = {(row["backend"], row["case_id"], row["budget_chars"]): row for row in rows}
    if len(native_lookup) != len(native_rows) or len(row_lookup) != len(rows):
        raise ValueError("Duplicate evidence rows")
    expected_native = {(backend, case_id) for backend in backends for case_id in cases}
    expected_packed = {(backend, case_id, budget) for backend in backends for case_id in cases for budget in budgets}
    if set(native_lookup) != expected_native or set(row_lookup) != expected_packed:
        raise ValueError("Evidence row inventory differs from the exact registered Cartesian product")
    for native in native_rows:
        case = cases[native["case_id"]]
        if any(native.get(key) != case[key] for key in ("query", "project", "checkpoint")):
            raise ValueError("Native request labels differ from the frozen case")
        if [sample["repetition"] for sample in native["samples"]] != list(range(repeats)):
            raise ValueError("Native repetition inventory differs from the registered order")
    for row in rows:
        case = cases[row["case_id"]]
        if any(row.get(key) != case[key] for key in ("query", "project", "checkpoint", "category")):
            raise ValueError("Packed response labels differ from the frozen case")
        native = native_lookup[(row["backend"], row["case_id"])]
        if row["latency_ms"] != [sample["adapter_call_ms"] for sample in native["samples"]]:
            raise ValueError("Packed timing observations differ from saved native samples")
    return native_lookup, row_lookup


def audit_summaries(report, rows):
    summary = workflow.summarize(rows)
    by_category = {category: workflow.summarize([row for row in rows if row["category"] == category])
                   for category in sorted({row["category"] for row in rows})}
    if summary != report["summary"] or by_category != report["by_category"]:
        raise ValueError("Overall or per-category summary differs from independent row recomputation")


def audit(output):
    """Recompute every native mapping, packed response and evidence score offline."""
    output = Path(output)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    binding = json.loads((output / "binding.json").read_text(encoding="utf-8"))
    if (report.get("status") != "completed" or report.get("integrity_passed") is not True
            or report.get("failures") or any(report[key] != binding[key] for key in
                ("version", "dataset_sha256", "settings", "runtime", "evaluator", "lock", "environment"))):
        raise ValueError("Run is incomplete or differs from its pre-execution binding")
    locked = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if report["lock"] != locked:
        raise ValueError("Initial lock document differs from frozen evaluator lock")
    expected_packages = {name: {key: spec[key] for key in ("version", "active_dependencies", "files_sha256",
                                                         "record_sha256", "native_files")}
                         | {"installed_files": len(spec["files"])}
                         for name, spec in locked["packages"].items()}
    runtime = report["runtime"]
    expected_runtime = {name: hashlib.sha256(git(ROOT, "show", MATERIALIZER_COMMIT + ":" + name)).hexdigest()
                        for name in git(ROOT, "ls-tree", "-r", "--name-only", MATERIALIZER_COMMIT,
                                        "src/memory_book").decode().splitlines()}
    if (runtime["commit"] != MATERIALIZER_COMMIT or runtime["backend"] != "native"
            or runtime["files"] != expected_runtime or runtime["sha256"] != workflow.sha(expected_runtime)):
        raise ValueError("Materializer binding differs from original committed source")
    steps = json.loads((output / "dataset.json").read_text(encoding="utf-8"))
    if workflow.sha(steps) != report["dataset_sha256"] or steps != workflow.workload():
        raise ValueError("Dataset is not the frozen engineering workload")
    if (report["evaluator"] != source_identity(commit=report["evaluator"]["commit"], require_committed=True)
            or report["evaluator_after"] != report["evaluator"]
            or report["runtime_after"] != report["runtime"]):
        raise ValueError("Evaluator closure changed after the recorded run")
    native_rows = [json.loads(line) for line in (output / "native.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text(encoding="utf-8").splitlines()]
    if (report["settings"]["backends"] != list(BACKENDS)
            or report["settings"]["budgets_chars"] != [1200, 2400]
            or report["settings"]["repeats"] != 3
            or report["settings"]["query_rewrite"] is not False):
        raise ValueError("Reported run is not the preregistered complete matrix")
    native_lookup, row_lookup = audit_inventory(steps, report["settings"], native_rows, rows)
    expected_cases = sum(len(step["cases"]) for step in steps)
    expected_statuses = {backend: {"status": "completed", "packed_rows": expected_cases * len(report["settings"]["budgets_chars"]),
                                   "expected_packed_rows": expected_cases * len(report["settings"]["budgets_chars"])}
                         for backend in report["settings"]["backends"]}
    if (report["case_count"] != expected_cases or report["backend_status"] != expected_statuses
            or report["completed_native_query_backend_pairs"] != len(native_rows)):
        raise ValueError("Reported completed counts differ from exact verified row inventory")
    if [item["checkpoint"] for item in report["checkpoints"]] != [step["checkpoint"] for step in steps]:
        raise ValueError("Checkpoint inventory differs from the original workload")
    journal = [json.loads(line) for line in (output / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    expected_events = []
    for step in steps:
        for backend in BACKENDS:
            expected_events.extend({"event": event, "checkpoint": step["checkpoint"], "backend": backend}
                                   for event in ("setup_started", "setup_completed"))
        for ordinal, case in enumerate(step["cases"]):
            for repetition in range(3):
                order = list(BACKENDS)
                if (ordinal + repetition) % 2:
                    order.reverse()
                for backend in order:
                    event = {"backend": backend, "checkpoint": step["checkpoint"],
                             "case_id": case["id"], "repetition": repetition}
                    expected_events.append({"event": "query_started", **event})
                    expected_events.append({"event": "query_completed", **event,
                                            "sample": native_lookup[(backend, case["id"])]["samples"][repetition]})
    if journal != expected_events:
        raise ValueError("Attempt journal differs from complete ordered native execution matrix")
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
        if checkpoint != json.loads((output / f"checkpoint-{step['checkpoint']}.json").read_text(encoding="utf-8")):
            raise ValueError("Final checkpoint record differs")
        if set(checkpoint["backends"]) != set(BACKENDS):
            raise ValueError("Checkpoint omitted or added a component")
        for backend in BACKENDS:
            metadata = checkpoint["backends"][backend]
            verification = metadata["final_verification"]
            if (metadata["backend"] != backend or metadata["supplied_pages"] != len(documents)
                    or verification["packages"] != metadata["packages"] or metadata["packages"] != expected_packages
                    or verification["packages_unchanged"] is not True or verification["network_attempts"] != 0):
                raise ValueError("Checkpoint package/source verification differs")
        if workflow.sha(documents) != checkpoint["documents_sha256"]:
            raise ValueError("Supplied page bundle digest mismatch")
        for case in step["cases"]:
            for backend in report["settings"]["backends"]:
                native_row = native_lookup[(backend, case["id"])]
                if len(native_row["samples"]) != report["settings"]["repeats"]:
                    raise ValueError("Missing native repetitions")
                identities = set()
                for sample in native_row["samples"]:
                    ids = validate_native(backend, sample["native"], lookup, case["project"], case["query"])
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
    audit_summaries(report, rows)
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
