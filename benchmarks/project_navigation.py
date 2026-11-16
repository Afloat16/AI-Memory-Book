"""Frozen-cohort comparison and native Book navigation contracts for v0.7.0.

Existing workload/scorer/packer/adapters remain unchanged. This driver adds
explicit cohort selection and the separately pinned native ReMe component.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import time
import traceback
import uuid

from benchmarks import engineering_components as components
from benchmarks import engineering_workflow as engineering
from benchmarks import memory_systems as legacy
from benchmarks import project_navigation_data as same_topic
from benchmarks.competitors.memory_systems import ROOT, sha_file, stable_native, validate_response, write_json

VERSION = "project-navigation-components-v1"
BACKENDS = (*legacy.BACKENDS, "reme")
COHORTS = ("engineering", "same-topic")
CLAUDE_SCOPE_PIN = "c4a9f5725f420bf9c6e866cdd3b94bd36498af09"
SMOKE_PROJECTS = ("scope-a", "scope-ab", "Scope-a", "absent-project")
SCOPE_LIMITATION = "native_ascii_nocase_project_scope_incompatible_with_exact_case_ids"
NEW_SOURCE_FILES = (
    "benchmarks/project_navigation.py", "benchmarks/project_navigation_data.py",
    "benchmarks/project_navigation_contracts.py", "benchmarks/project_navigation-plan.md",
    "benchmarks/competitors/reme.py", "benchmarks/competitors/reme_worker.py",
    "benchmarks/competitors/reme-lock.json", "benchmarks/competitors/reme-requirements.in",
    "benchmarks/competitors/reme-requirements.txt",
    ".github/workflows/project-navigation-comparison.yml",
)


def source_identity():
    names = tuple(dict.fromkeys((*legacy.SOURCE_FILES, *NEW_SOURCE_FILES)))
    files = {name: sha_file(ROOT / name) for name in names}
    return {"files": files, "sha256": engineering.sha(files)}


def cohort_workload(name):
    if name == "engineering":
        return engineering.workload()
    if name == "same-topic":
        steps = same_topic.workload()
        same_topic.validate_workload(steps)
        return steps
    raise ValueError("Unknown registered cohort")


def prepare(cache, *, python=sys.executable, reme_python=sys.executable, node="node"):
    from benchmarks.competitors.reme import prepare as prepare_reme

    cache = Path(cache).resolve()
    report = {"status": "started", "evaluator": source_identity(), "components": {}, "failures": []}
    for name, action in (
        ("legacy", lambda: legacy.prepare(cache, python=python, node=node)),
        ("reme", lambda: prepare_reme(cache / "reme", python=reme_python)),
    ):
        try:
            value = action()
            report["components"][name] = value
            if value.get("status") not in (None, "prepared", "passed"):
                raise RuntimeError(f"{name} preparation did not pass: {value.get('status')}")
        except Exception:
            report["failures"].append({"backend": name, "stage": "prepare", "error": traceback.format_exc()})
    report["status"] = "prepared" if not report["failures"] else "failed"
    cache.mkdir(parents=True, exist_ok=True)
    write_json(cache / "project-preparation.json", report)
    return report


def make_adapter(backend, book, documents, state, cache, python, reme_python, node):
    if backend == "reme":
        from benchmarks.competitors.reme import ReMeComponent

        return ReMeComponent(documents, cache / "reme", state, python=reme_python, offline=True)
    return legacy.make_adapter(backend, book, documents, state, cache, python, node)


def native_search(backend, adapter, query, project, documents):
    if backend == "reme":
        native = adapter.search(query, project=project, limit=5)
        ids = validate_response(native, documents, project, limit=5)
        return native, ids
    return legacy.native_search(backend, adapter, query, project, documents)


class TransportObserver:
    """Observe the frozen claude bridge before its unchanged source validator.

    Return the exact original object. Only a top-level snapshot/list append is
    inside bridge timing; JSON serialization and disk writes happen in flush(),
    after the outer search timer has stopped (also on validation exceptions).
    The frozen adapter only adds bridge_ms after _request returns; its native
    payload is not mutated. Native search_ms is entirely inside the Bun worker.
    """

    def __init__(self, adapter, checkpoint, stream):
        self.stream, self.checkpoint = stream, checkpoint
        self.rows, self.pending, self.context = [], [], {}
        original = adapter._request

        def observe(request):
            if request.get("op") != "search":
                return original(request)
            record = {"backend": "claude_mem", "checkpoint": checkpoint,
                      **self.context, "request": dict(request)}
            try:
                response = original(request)
            except Exception as error:
                record.update(status="transport_error", error_type=type(error).__name__, error=str(error))
                self.pending.append(record)
                raise
            record.update(status="returned", response=dict(response))
            self.pending.append(record)
            return response

        adapter._request = observe

    def begin(self, case_id, project, repetition):
        if self.pending:
            raise RuntimeError("Previous native transport observation was not retained")
        self.context = {"case_id": case_id, "project": project, "repetition": repetition}

    def flush(self):
        retained = []
        for record in self.pending:
            record["trace_id"] = f"{self.checkpoint}:claude_mem:{len(self.rows)}"
            if "response" in record:
                record["response_sha256"] = engineering.sha(record["response"])
            self.stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            self.stream.flush()
            self.rows.append(record)
            retained.append(record)
        self.pending.clear()
        return retained


def scope_mismatch_evidence(metadata, observation, documents, *, query, project):
    """Authenticate only the preregistered native ASCII-NOCASE incompatibility.

    This is an execution-continuation classification, never a repaired result
    or a relaxation of the frozen adapter's exact-project/source validation.
    """
    if (metadata.get("repository") != "thedotmack/claude-mem"
            or metadata.get("commit") != CLAUDE_SCOPE_PIN
            or metadata.get("package_version") != "15.18.1"
            or metadata.get("lock_sha256") != sha_file(ROOT / "benchmarks/competitors/claude-mem-round2-lock.json")
            or metadata.get("fts_integrity_check") is not True):
        return None
    if (observation.get("status") != "returned"
            or observation.get("backend") != "claude_mem"
            or observation.get("project") != project
            or observation.get("request") != {"op": "search", "query": query, "project": project, "limit": 5}):
        return None
    response = observation.get("response", {})
    if observation.get("response_sha256") != engineering.sha(response):
        return None
    ids, payload = response.get("hit_ids"), response.get("native_payload")
    if (not isinstance(ids, list) or not isinstance(payload, list) or not ids
            or len(ids) != len(payload) or len(ids) > 5
            or any(not isinstance(identity, str) for identity in ids) or len(ids) != len(set(ids))):
        return None
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    foreign = []
    for identity, row in zip(ids, payload):
        doc = documents.get(identity)
        if not doc or not isinstance(row, dict) or any(row.get(key) != doc.get(key) for key in ("project", "title", "text")):
            return None
        if row["project"] != project:
            if row["project"].translate(ascii_lower) != project.translate(ascii_lower):
                return None
            foreign.append({"hit_id": identity, "project": row["project"]})
    if not foreign:
        return None
    return {"kind": SCOPE_LIMITATION, "commit": CLAUDE_SCOPE_PIN, "trace_id": observation["trace_id"],
            "requested_project": project, "foreign_original_records": foreign,
            "response_sha256": observation["response_sha256"], "quality_success": False}


def check_smoke(folder, output):
    """Keep smoke failure visible; permit only an authenticated known mismatch."""
    folder, output = Path(folder), Path(output)
    if output.exists():
        raise FileExistsError("Choose a fresh smoke-eligibility record")
    report = json.loads((folder / "report.json").read_text())
    docs = {doc["id"]: doc for doc in json.loads((folder / "documents.json").read_text())}
    traces = [json.loads(line) for line in (folder / "transport.jsonl").read_text().splitlines() if line]
    trace_index = {row["trace_id"]: row for row in traces}
    reasons, accepted = [], []
    if len(trace_index) != len(traces):
        reasons.append("duplicate transport trace identity")
    if [row.get("project") for row in traces] != list(SMOKE_PROJECTS):
        reasons.append("missing, repeated or changed original claude smoke transport")
    for ordinal, row in enumerate(traces):
        project = row.get("project")
        if (row.get("trace_id") != f"smoke:claude_mem:{ordinal}" or row.get("backend") != "claude_mem"
                or row.get("checkpoint") != "smoke" or row.get("case_id") != "smoke:" + str(project)
                or row.get("repetition") != 0 or row.get("status") != "returned"
                or row.get("request") != {"op": "search", "query": "memorytoken_alpha", "project": project, "limit": 5}
                or row.get("response_sha256") != engineering.sha(row.get("response"))):
            reasons.append("claude smoke transport identity, query or original response changed")
    if set(report.get("backends", {})) != set(BACKENDS):
        reasons.append("not all eight registered backends were exercised")
    for backend in BACKENDS:
        item = report.get("backends", {}).get(backend, {})
        samples = item.get("samples", [])
        if [sample.get("project") for sample in samples] != list(SMOKE_PROJECTS):
            reasons.append(f"{backend}: incomplete or changed smoke queries")
            continue
        for sample in samples:
            if sample.get("query") != "memorytoken_alpha":
                reasons.append(f"{backend}: changed smoke query")
            if backend == "claude_mem":
                refs = sample.get("transport_trace_ids", [])
                if (len(refs) != 1 or refs[0] not in trace_index
                        or trace_index[refs[0]].get("project") != sample["project"]):
                    reasons.append("claude sample is not bound to its original native transport")
            if sample.get("status") == "passed":
                ids, project = sample.get("hit_ids", []), sample["project"]
                if (project == "absent-project" and ids) or (project != "absent-project" and not ids):
                    reasons.append(f"{backend}: invalid source presence contract")
                if any(identity not in docs or docs[identity]["project"] != project for identity in ids):
                    reasons.append(f"{backend}: passed sample contains a foreign source")
                if backend == "claude_mem" and len(refs) == 1 and refs[0] in trace_index:
                    original = trace_index[refs[0]].get("response", {})
                    native = dict(sample.get("native", {}))
                    native.pop("bridge_ms", None)
                    if native != original or original.get("hit_ids") != ids:
                        reasons.append("passed claude sample differs from its native response")
                continue
            evidence = None
            refs = sample.get("transport_trace_ids", [])
            if (backend == "claude_mem" and sample["project"] in {"scope-a", "Scope-a"}
                    and sample.get("error_type") == "ValueError" and sample.get("error") == "Native project scope violation"
                    and len(refs) == 1 and refs[0] in trace_index):
                evidence = scope_mismatch_evidence(item.get("metadata", {}), trace_index[refs[0]], docs,
                                                   query="memorytoken_alpha", project=sample["project"])
            if evidence is None:
                reasons.append(f"{backend}/{sample['project']}: unregistered or unauthenticated failure")
            else:
                accepted.append(evidence)
        expected_status = "failed" if any(sample.get("status") != "passed" for sample in samples) else "passed"
        if item.get("status") != expected_status:
            reasons.append(f"{backend}: smoke status does not preserve failed probes")
    failures = report.get("failures", [])
    expected_failures = {(item["requested_project"], item["trace_id"]) for item in accepted}
    observed_failures = set()
    for failure in failures:
        refs = failure.get("transport_trace_ids", [])
        if (failure.get("backend") != "claude_mem" or failure.get("stage") != "smoke"
                or failure.get("error_type") != "ValueError" or failure.get("message") != "Native project scope violation"
                or failure.get("query") != "memorytoken_alpha" or len(refs) != 1):
            reasons.append("an unexpected setup, query, cleanup or runner failure remains")
        else:
            observed_failures.add((failure.get("project"), refs[0]))
    if observed_failures != expected_failures or len(failures) != len(accepted):
        reasons.append("failure list and authenticated native observations do not match")
    expected_status = "failed" if failures else "passed"
    if report.get("status") != expected_status:
        reasons.append("overall smoke status does not preserve failures")
    result = {"schema": "project-navigation-execution-eligibility-v1",
              "status": "blocked" if reasons else ("eligible_with_registered_scope_mismatch" if accepted else "eligible"),
              "eligible_for_execution": not reasons, "smoke_status": report.get("status"),
              "all_smokes_passed": report.get("status") == "passed", "registered_limitations": accepted,
              "blocking_reasons": reasons, "retained_failure_count": len(failures),
              "scope": "Execution continuation only; failed scope checks remain failed and receive no cohort quality score.",
              "decision_basis": "Pre-quality task authorization after preparation-attempt1 and pinned native NOCASE source review; no quality result informed this amendment.",
              "input_sha256": {name: sha_file(folder / name) for name in ("report.json", "documents.json", "transport.jsonl")}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return result


def close_adapters(active, state_root, output, checkpoint, failures):
    legacy.close_adapters({key: value for key, value in active.items() if key != "reme"},
                          state_root, output, checkpoint, failures)
    if "reme" in active:
        try:
            active["reme"].close()
        except Exception:
            failures.append({"backend": "reme", "checkpoint": checkpoint,
                             "stage": "close", "error": traceback.format_exc()})
    for name in ("stderr.log", "native-stderr.log"):
        source = state_root / "reme" / name
        if source.is_file():
            shutil.copyfile(source, output / f"checkpoint-{checkpoint}-reme-{name}")


def cohort_counts(steps):
    cases = [case for step in steps for case in step["cases"]]
    return {"cases": len(cases), "answerable_cases": sum(bool(case["required"]) for case in cases),
            "required_evidence_spans": sum(len(case["required"]) for case in cases),
            "fixed_consumer_cases": sum(bool(case["consumer_family"]) for case in cases),
            "missing_evidence_cases": sum(not case["required"] for case in cases),
            "categories": {name: sum(case["category"] == name for case in cases)
                           for name in sorted({case["category"] for case in cases})}}


def missing_evidence(rows, steps, backends, budgets):
    cases = {case["id"]: case for step in steps for case in step["cases"] if not case["required"]}
    result = []
    for backend in backends:
        for budget in budgets:
            for category in sorted({case["category"] for case in cases.values()}):
                expected = {identity for identity, case in cases.items() if case["category"] == category}
                own = [row for row in rows if row["backend"] == backend and row["budget_chars"] == budget
                       and row["case_id"] in expected]
                result.append({"backend": backend, "budget_chars": budget, "category": category,
                               "expected_cases": len(expected), "completed_cases": len(own),
                               "empty_context_case_ids": [row["case_id"] for row in own if not row["response"]["context"]],
                               "nonempty_context_case_ids": [row["case_id"] for row in own if row["response"]["context"]]})
    return result


def markdown_report(report):
    lines = ["# Project-scoped memory components", "",
             f"Cohort: `{report['cohort']}`. Status: `{report['status']}`. Protocol: `{VERSION}`.", "",
             "Authored synthetic development cases; supplied-source component modes; no answer model. "
             "Only fully completed, integrity-valid backends appear below. "
             "Failed attempts and partial rows remain in the JSON records.", "",
             "| Component | Chars | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |",
             "|---|---:|---:|---:|---:|---:|"]
    for cell in report.get("summary", []):
        complete, consumer = cell["complete_evidence_rate"], cell["fixed_consumer_all_checks_pass_rate"]
        complete_text = f"{complete:.2%}" if complete is not None else "n/a"
        consumer_text = f"{consumer:.2%}" if consumer is not None else "n/a"
        lines.append(f"| {cell['backend']} | {cell['budget_chars']} | "
                     f"{complete_text} | {consumer_text} | {cell['stale_only_cases']} | {cell['mean_context_chars']:.1f} |")
    lines.extend(["", "See `project_navigation-plan.md` for the fixed protocol, original modes, exact "
                  "scope, shared MiniLM correlation, missing-evidence cases and timing boundaries. "
                  "These results do not measure full products, default LLM extraction, developer "
                  "productivity, access control or autonomous project selection.", ""])
    if report.get("failures"):
        lines.extend(["## Retained failures", ""])
        for failure in report["failures"]:
            lines.append(f"- {failure.get('backend', 'runner')} / {failure['stage']}: "
                         f"`{failure['error'].splitlines()[-1]}`")
    return "\n".join(lines) + "\n"


def run(output, cache, *, cohort="same-topic", budgets=(1200, 2400), repeats=3,
        backends=BACKENDS, python=sys.executable, reme_python=sys.executable, node="node"):
    import memory_book
    from memory_book import MemoryBook

    if (not budgets or len(set(budgets)) != len(budgets)
            or any(type(value) is not int or not 0 < value <= 100000 for value in budgets)):
        raise ValueError("Distinct positive character caps up to 100000 are required")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("repeats must be between 1 and 30")
    if not backends or len(set(backends)) != len(backends) or set(backends) - set(BACKENDS):
        raise ValueError("Choose distinct registered backends")
    steps = cohort_workload(cohort)
    output, cache = legacy.fresh_output(output), Path(cache).resolve()
    run_state = cache / "project-runs" / uuid.uuid4().hex
    run_state.mkdir(parents=True)
    runtime_before, evaluator_before = engineering.runtime_identity(memory_book), source_identity()
    report = {"version": VERSION, "cohort": cohort, "status": "started",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "evidence_level": "authored_synthetic_supplied_source_components",
              "dataset_sha256": engineering.sha(steps), "cohort_counts": cohort_counts(steps),
              "runtime": runtime_before, "evaluator": evaluator_before,
              "upstream_lock": json.loads((ROOT / "benchmarks/competitors/memory-systems-lock.json").read_text()),
              "reme_lock": json.loads((ROOT / "benchmarks/competitors/reme-lock.json").read_text()),
              "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
              "settings": {"backends": list(backends), "budgets_chars": list(budgets), "repeats": repeats,
                           "limit": 5, "result_cache": False,
                           "packing": "unchanged common_pack; original whole pages; skip oversized blocks",
                           "query_transformation": "none in harness; native component preprocessing only",
                           "transport_observation": "claude bridge response snapshot before unchanged validation; JSON I/O after measured call; native worker timing unchanged",
                           "shared_embedding_backends": ["chroma", "langgraph", "mem0"]}}
    write_json(output / "binding.json", report)
    write_json(output / "dataset.json", steps)
    for name in ("preparation.json", "project-preparation.json"):
        if (cache / name).is_file():
            shutil.copyfile(cache / name, output / name)
    rows, native_rows, checkpoints, failures, visible, disabled = [], [], [], [], {}, set()
    try:
        with ExitStack() as stack:
            book = stack.enter_context(MemoryBook(run_state / "book.db", cache_size=0))
            trace = stack.enter_context((output / "raw.jsonl").open("w", encoding="utf-8"))
            native_trace = stack.enter_context((output / "native.jsonl").open("w", encoding="utf-8"))
            transport_trace = stack.enter_context((output / "transport.jsonl").open("w", encoding="utf-8"))
            for step in steps:
                checkpoint_id = step["checkpoint"]
                begin = time.perf_counter_ns()
                for session in step["sessions"]:
                    book.ingest(session)
                    visible[(session["project"], session["session_id"])] = session
                ingest_ms = (time.perf_counter_ns() - begin) / 1e6
                documents = components.export_documents(book, visible)
                lookup, sources = {doc["id"]: doc for doc in documents}, engineering.visible_sources(visible)
                write_json(output / f"documents-{checkpoint_id}.json", documents)
                checkpoint = {"checkpoint": checkpoint_id, "documents": len(documents),
                              "documents_sha256": engineering.sha(documents),
                              "book_incremental_ingest_ms": ingest_ms, "backends": {}}
                checkpoints.append(checkpoint)
                checkpoint_state = run_state / f"checkpoint-{checkpoint_id}"
                checkpoint_state.mkdir()
                active, observers = {}, {}
                try:
                    for backend in backends:
                        if backend in disabled:
                            continue
                        try:
                            adapter = make_adapter(backend, book, documents, checkpoint_state / backend,
                                                   cache, python, reme_python, node)
                            active[backend] = adapter
                            checkpoint["backends"][backend] = getattr(adapter, "metadata", {
                                "mode": "native Book selection, common whole-block packing"})
                            if backend == "claude_mem":
                                observers[backend] = TransportObserver(adapter, checkpoint_id, transport_trace)
                        except Exception:
                            disabled.add(backend)
                            failures.append({"backend": backend, "checkpoint": checkpoint_id,
                                             "stage": "setup", "error": traceback.format_exc()})
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
                    for ordinal, case in enumerate(step["cases"]):
                        measurements = {backend: [] for backend in active if backend not in disabled}
                        for repeat in range(repeats):
                            order = list(measurements)
                            if (ordinal + repeat) % 2:
                                order.reverse()
                            for backend in order:
                                if backend in disabled:
                                    continue
                                observer = observers.get(backend)
                                if observer is not None:
                                    observer.begin(case["id"], case["project"], repeat)
                                try:
                                    begin = time.perf_counter_ns()
                                    native, ids = native_search(backend, active[backend], case["query"],
                                                                case["project"], lookup)
                                    elapsed = (time.perf_counter_ns() - begin) / 1e6
                                    sample = {
                                        "repetition": repeat, "adapter_call_ms": elapsed,
                                        "native_search_ms": native.get("search_ms", elapsed),
                                        "native_bridge_ms": native.get("bridge_ms", elapsed),
                                        "hit_ids": ids, "native_sha256": engineering.sha(stable_native(native)),
                                        "native": native}
                                except Exception as error:
                                    disabled.add(backend)
                                    observed = observer.flush() if observer is not None else []
                                    failure = {"backend": backend, "checkpoint": checkpoint_id,
                                               "case_id": case["id"], "project": case["project"], "query": case["query"],
                                               "repetition": repeat, "stage": "query", "error": traceback.format_exc(),
                                               "error_type": type(error).__name__, "message": str(error),
                                               "transport_trace_ids": [item["trace_id"] for item in observed]}
                                    if (backend == "claude_mem" and type(error) is ValueError
                                            and str(error) == "Native project scope violation" and len(observed) == 1):
                                        failure["scope_diagnosis"] = scope_mismatch_evidence(
                                            checkpoint["backends"][backend], observed[0], lookup,
                                            query=case["query"], project=case["project"])
                                    failures.append(failure)
                                else:
                                    observed = observer.flush() if observer is not None else []
                                    if observer is not None:
                                        sample["transport_trace_ids"] = [item["trace_id"] for item in observed]
                                    measurements[backend].append(sample)
                        for backend, samples in measurements.items():
                            native_row = {"case_id": case["id"], "backend": backend, "query": case["query"],
                                          "project": case["project"], "checkpoint": checkpoint_id, "samples": samples}
                            native_trace.write(json.dumps(native_row, ensure_ascii=False, allow_nan=False) + "\n")
                            native_trace.flush()
                            native_rows.append(native_row)
                            if len(samples) != repeats:
                                continue
                            for budget in budgets:
                                begin = time.perf_counter_ns()
                                response = components.common_pack(samples[0]["hit_ids"], lookup, case["project"], budget)
                                packed_ms = (time.perf_counter_ns() - begin) / 1e6
                                row = {"case_id": case["id"], "backend": backend, "query": case["query"],
                                       "category": case["category"], "project": case["project"],
                                       "checkpoint": checkpoint_id, "budget_chars": budget, "common_pack_ms": packed_ms,
                                       "latency_ms": [sample["adapter_call_ms"] for sample in samples],
                                       "repeat_outputs_equal": len({sample["native_sha256"] for sample in samples}) == 1,
                                       "native_first_output_sha256": samples[0]["native_sha256"],
                                       "response": response, "score": engineering.score(case, response, sources, budget)}
                                rows.append(row)
                                trace.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                                trace.flush()
                finally:
                    close_adapters(active, checkpoint_state, output, checkpoint_id, failures)
                    disabled.update(item["backend"] for item in failures if "backend" in item)
                    write_json(output / f"checkpoint-{checkpoint_id}.json", checkpoint)
    except Exception:
        failures.append({"stage": "runner", "error": traceback.format_exc()})
    runtime_after, evaluator_after = engineering.runtime_identity(memory_book), source_identity()
    expected_cases = sum(len(step["cases"]) for step in steps)
    statuses, completed = {}, []
    for backend in backends:
        own = [row for row in rows if row["backend"] == backend]
        valid = (len(own) == expected_cases * len(budgets) and backend not in disabled
                 and all(not row["score"]["source_errors"] and row["score"]["within_budget"]
                         and row["repeat_outputs_equal"] for row in own))
        statuses[backend] = {"status": "completed" if valid else "failed_or_incomplete",
                             "packed_rows": len(own), "expected_packed_rows": expected_cases * len(budgets)}
        if valid:
            completed.extend(own)
    report.update(status="completed" if all(value["status"] == "completed" for value in statuses.values())
                  and not failures else "completed_with_backend_failures",
                  runtime_unchanged=runtime_before == runtime_after, evaluator_unchanged=evaluator_before == evaluator_after,
                  runtime_final_sha256=runtime_after["sha256"], evaluator_final_sha256=evaluator_after["sha256"],
                  case_count=expected_cases, backend_status=statuses, failures=failures, checkpoints=checkpoints,
                  completed_native_query_backend_pairs=len(native_rows),
                  summary=engineering.summarize(completed) if completed else [],
                  partial_summary=engineering.summarize([row for row in rows if statuses[row["backend"]]["status"] != "completed"])
                  if any(statuses[row["backend"]]["status"] != "completed" for row in rows) else [],
                  by_category={category: engineering.summarize([row for row in completed if row["category"] == category])
                               for category in sorted({row["category"] for row in completed})},
                  missing_evidence=missing_evidence(rows, steps, backends, budgets))
    report["native_timing"] = {backend: {phase: {
        field: components.timing([sample[field] for row in native_rows if row["backend"] == backend
                                  for sample in row["samples"]
                                  if (sample["repetition"] == 0) == (phase == "first_query_search")])
        for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms")}
        for phase in ("first_query_search", "repeat_query_search")} for backend in backends}
    report["integrity_passed"] = (report["status"] == "completed" and report["runtime_unchanged"]
                                  and report["evaluator_unchanged"])
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def self_test(output, cache, *, backends=BACKENDS, python=sys.executable,
              reme_python=sys.executable, node="node"):
    """Tiny independent API fixtures; no registered-cohort retrieval or scoring."""
    from memory_book import MemoryBook

    output, cache = legacy.fresh_output(output), Path(cache).resolve()
    state = cache / "project-smoke" / uuid.uuid4().hex
    state.mkdir(parents=True)
    fixtures = [{"project": project, "session_id": "same-session", "task_id": "contract",
                 "created_at": "2026-01-01T00:00:00Z", "messages": [
                     {"role": "user", "content": "memorytoken_alpha source contract"},
                     {"role": "assistant", "content": f"memorytoken_alpha uses exact value {value}."}]}
                for project, value in (("scope-a", "ALPHA17"), ("scope-ab", "BETA91"), ("Scope-a", "GAMMA42"))]
    report = {"status": "started", "scope": "API execution and provenance; no cohort quality score",
              "evaluator": source_identity(), "backends": {}, "failures": []}
    with MemoryBook(state / "book.db", cache_size=0) as book, \
            (output / "transport.jsonl").open("w", encoding="utf-8") as transport_trace:
        visible = {}
        for source in fixtures:
            book.ingest(source)
            visible[(source["project"], source["session_id"])] = source
        docs = components.export_documents(book, visible)
        lookup = {doc["id"]: doc for doc in docs}
        write_json(output / "documents.json", docs)
        for backend in backends:
            active, item = {}, {"samples": [], "checks": {}}
            report["backends"][backend] = item
            try:
                adapter = make_adapter(backend, book, docs, state / backend, cache, python, reme_python, node)
                active[backend] = adapter
                item["metadata"] = getattr(adapter, "metadata", {})
                observer = TransportObserver(adapter, "smoke", transport_trace) if backend == "claude_mem" else None
                for project in SMOKE_PROJECTS:
                    sample = {"project": project, "query": "memorytoken_alpha"}
                    if observer is not None:
                        observer.begin("smoke:" + project, project, 0)
                    try:
                        native, ids = native_search(backend, adapter, "memorytoken_alpha", project, lookup)
                        sample.update(native=native, hit_ids=ids)
                        if project == "absent-project":
                            if ids:
                                raise AssertionError("Unknown project returned source evidence")
                        elif not ids or any(lookup[identity]["project"] != project for identity in ids):
                            raise AssertionError("Exact project/source smoke failed")
                        sample["status"] = "passed"
                    except Exception as error:
                        observed = observer.flush() if observer is not None else []
                        sample.update(status="failed", error_type=type(error).__name__, error=str(error),
                                      transport_trace_ids=[row["trace_id"] for row in observed])
                        failure = {"backend": backend, "stage": "smoke", "project": project,
                                   "query": "memorytoken_alpha", "error": traceback.format_exc(),
                                   "error_type": type(error).__name__, "message": str(error),
                                   "transport_trace_ids": sample["transport_trace_ids"]}
                        if (backend == "claude_mem" and type(error) is ValueError
                                and str(error) == "Native project scope violation" and len(observed) == 1):
                            failure["scope_diagnosis"] = scope_mismatch_evidence(
                                item["metadata"], observed[0], lookup, query="memorytoken_alpha", project=project)
                        report["failures"].append(failure)
                    else:
                        observed = observer.flush() if observer is not None else []
                        if observer is not None:
                            sample["transport_trace_ids"] = [row["trace_id"] for row in observed]
                    item["samples"].append(sample)
                    write_json(output / f"{backend}.json", item)
                passed = all(sample["status"] == "passed" for sample in item["samples"])
                item["checks"] = {"actual_upstream_calls": True, "exact_case_prefix_project_filter": passed,
                                  "known_projects_have_original_evidence": all(sample["status"] == "passed" for sample in item["samples"][:3]),
                                  "missing_project_is_empty": item["samples"][-1]["status"] == "passed"}
                item["status"] = "passed" if passed else "failed"
            except Exception as error:
                item["status"] = "failed"
                report["failures"].append({"backend": backend, "stage": "setup", "error": traceback.format_exc(),
                                           "error_type": type(error).__name__, "message": str(error)})
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--check-smoke", type=Path, metavar="SMOKE_DIRECTORY")
    modes.add_argument("--contracts", action="store_true")
    parser.add_argument("--cohort", choices=COHORTS, default="same-topic")
    parser.add_argument("--budget-chars", nargs="+", type=int, default=[1200, 2400])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS))
    parser.add_argument("--backend-python", default=sys.executable)
    parser.add_argument("--reme-python", default=sys.executable)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    if args.prepare:
        if args.output:
            parser.error("--prepare writes only to its cache")
        report = prepare(args.cache, python=args.backend_python, reme_python=args.reme_python, node=args.node)
    elif args.output is None:
        parser.error("--output is required")
    elif args.check_smoke:
        report = check_smoke(args.check_smoke, args.output)
    elif args.contracts:
        from benchmarks.project_navigation_contracts import run_contracts
        report = run_contracts(args.output, args.cache)
    elif args.self_test:
        report = self_test(args.output, args.cache, backends=args.backends, python=args.backend_python,
                           reme_python=args.reme_python, node=args.node)
    else:
        report = run(args.output, args.cache, cohort=args.cohort, budgets=args.budget_chars, repeats=args.repeats,
                     backends=args.backends, python=args.backend_python, reme_python=args.reme_python, node=args.node)
    print(json.dumps({"status": report["status"], "output": str(args.output or args.cache),
                      "backend_status": report.get("backend_status"),
                      "failure_count": len(report.get("failures", []))}, ensure_ascii=False))
    return 0 if report["status"] in ("completed", "prepared", "passed", "eligible", "eligible_with_registered_scope_mismatch") else 2


if __name__ == "__main__":
    raise SystemExit(main())
