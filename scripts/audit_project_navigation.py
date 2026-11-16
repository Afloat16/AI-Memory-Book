"""Independently recompute retained v0.7.0 comparisons and Book contracts.

No retrieval, indexing or foreign runtime is executed here. The unchanged
original workload, scorer/packer and previously tested audit primitives remain
the reference. ReMe paths, chunk hashes and scope are authenticated separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_workflow as engineering
from benchmarks import project_navigation_data as data
from scripts import audit_memory_systems as old

BACKENDS = (*old.BACKENDS, "reme")
BUDGETS, REPEATS = (1200, 2400), 3
ENGINEERING_SHA = "87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3"
SAME_TOPIC_SHA = "589be00eb493fd05fc12dd59050e113a074cd0c2833c059848de50d0ffdfd74b"
V060_RUNTIME_SHA = "adb63d45a0d18f15b757d4c1bcacd9f35763a20e2c8399de480b51d13b5b9be4"
CLAUDE_PIN = "c4a9f5725f420bf9c6e866cdd3b94bd36498af09"
SCOPE_LIMITATION = "native_ascii_nocase_project_scope_incompatible_with_exact_case_ids"
DEFAULT_PREVIOUS = ROOT / "benchmarks/reports/v0.6.0-engineering/hosted"


def protocol(steps):
    cases, sources, sessions, visible = {}, {}, {}, {}
    for step in steps:
        for source in step["sessions"]:
            visible[(source["project"], source["session_id"])] = source
        sources[step["checkpoint"]] = engineering.visible_sources(visible)
        sessions[step["checkpoint"]] = dict(visible)
        for case in step["cases"]:
            if case["id"] in cases:
                raise ValueError("Repeated canonical case ID")
            cases[case["id"]] = case
    return steps, cases, sources, sessions


def expected_counts(cases):
    values = list(cases.values())
    return {"cases": len(values), "answerable_cases": sum(bool(case["required"]) for case in values),
            "required_evidence_spans": sum(len(case["required"]) for case in values),
            "fixed_consumer_cases": sum(bool(case["consumer_family"]) for case in values),
            "missing_evidence_cases": sum(not case["required"] for case in values),
            "categories": dict(sorted(Counter(case["category"] for case in values).items()))}


def missing_categories(rows, cases):
    result = []
    missing = {identity: case for identity, case in cases.items() if not case["required"]}
    for backend in BACKENDS:
        for budget in BUDGETS:
            for category in sorted({case["category"] for case in missing.values()}):
                expected = {identity for identity, case in missing.items() if case["category"] == category}
                own = [row for row in rows.values() if row["backend"] == backend
                       and row["budget_chars"] == budget and row["case_id"] in expected]
                result.append({"backend": backend, "budget_chars": budget, "category": category,
                               "expected_cases": len(expected), "completed_cases": len(own),
                               "empty_context_case_ids": [row["case_id"] for row in own if not row["response"]["context"]],
                               "nonempty_context_case_ids": [row["case_id"] for row in own if row["response"]["context"]]})
    return result


def reme_identity(doc):
    """Pinned FileChunk identity: SHA256 of space-joined path/lines/body."""
    project_hash = hashlib.sha256(doc["project"].encode("utf-8")).hexdigest()
    page_hash = hashlib.sha256(doc["id"].encode("utf-8")).hexdigest()
    path = f"pages/{project_hash}/{page_hash}.txt"
    end_line = 1 + doc["text"].count("\n") - int(doc["text"].endswith("\n"))
    chunk_id = hashlib.sha256(" ".join((path, "1", str(end_line), doc["text"])).encode("utf-8")).hexdigest()
    return {"id": doc["id"], "project": doc["project"], "native_path": path,
            "original_sha256": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(),
            "native_chunk_id": chunk_id, "start_line": 1, "end_line": end_line}


def verify_reme_native(audit, native, ids, documents, project, context):
    audit.check(isinstance(ids, list) and len(ids) <= 5 and len(ids) == len(set(ids)),
                "reme_top_five_distinct", context)
    if not audit.check(all(identity in documents and documents[identity]["project"] == project for identity in ids),
                       "reme_exact_project_mapping", context):
        return
    audit.equal(native["hit_ids"], ids, "reme_ids_match_payload", context)
    audit.equal(native["records"], [{"id": identity, "project": project, "text": documents[identity]["text"]}
                                     for identity in ids], "reme_original_records", context)
    expected_paths = [reme_identity(doc)["native_path"] for doc in documents.values() if doc["project"] == project]
    audit.equal(native["native_search_filter"], {"paths": expected_paths}, "reme_exact_prelimit_paths", context)
    rows = native["native_payload"]
    audit.check(len(rows) == len(ids), "reme_native_payload_count", context)
    for identity, row in zip(ids, rows):
        wanted = reme_identity(documents[identity])
        actual = {"native_path": row["path"], "native_chunk_id": row["id"],
                  "start_line": row["start_line"], "end_line": row["end_line"]}
        audit.equal(actual, {key: wanted[key] for key in actual}, "reme_native_chunk_identity", context + "/" + identity)
        audit.equal(row["text"], documents[identity]["text"], "reme_native_original_text", context + "/" + identity)


def registered_scope_response(audit, observation, documents, metadata, query, project, context):
    """Independent source authentication, never acceptance as a scoped result."""
    before = len(audit.failures)
    for key, wanted in {"repository": "thedotmack/claude-mem", "commit": CLAUDE_PIN,
                        "package_version": "15.18.1", "fts_integrity_check": True,
                        "lock_sha256": old.file_sha(ROOT / "benchmarks/competitors/claude-mem-round2-lock.json")}.items():
        audit.equal(metadata.get(key), wanted, "registered_scope_component_identity", context + "/" + key)
    audit.equal(observation.get("backend"), "claude_mem", "registered_scope_backend", context)
    audit.equal(observation.get("status"), "returned", "scope_failure_has_original_response", context)
    audit.equal(observation.get("project"), project, "scope_failure_original_project_request", context)
    audit.equal(observation.get("request"), {"op": "search", "query": query, "project": project, "limit": 5},
                "scope_failure_original_query_and_limit", context)
    response = observation["response"]
    audit.equal(observation.get("response_sha256"), engineering.sha(response), "transport_original_response_hash", context)
    ids, payload = response["hit_ids"], response["native_payload"]
    audit.check(isinstance(ids, list) and 0 < len(ids) <= 5 and len(ids) == len(set(ids)),
                "scope_failure_distinct_top_five", context)
    audit.equal(len(ids), len(payload), "scope_failure_payload_count", context)
    lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    foreign = []
    for identity, row in zip(ids, payload):
        doc = documents[identity]
        for field in ("title", "text", "project"):
            audit.equal(row[field], doc[field], "scope_failure_unmodified_original_source", context + "/" + identity + "/" + field)
        audit.equal(row.get("memory_session_id"), "supplied-page:" + identity, "scope_failure_native_page_identity", context + "/" + identity)
        audit.equal(row["project"].translate(lower), project.translate(lower), "only_registered_ascii_case_mismatch", context)
        if row["project"] != project:
            foreign.append({"hit_id": identity, "project": row["project"]})
    audit.check(bool(foreign), "original_response_proves_scope_incompatibility", context)
    if len(audit.failures) != before:
        return None
    return {"kind": SCOPE_LIMITATION, "commit": CLAUDE_PIN, "trace_id": observation["trace_id"],
            "requested_project": project, "foreign_original_records": foreign,
            "response_sha256": observation["response_sha256"], "quality_success": False}


def audit_transport_and_failure(audit, folder, proto, documents, report, label, cohort):
    cases = proto[1]
    raw = audit.jsonl(folder / "transport.jsonl")
    by_id = {row.get("trace_id"): row for row in raw}
    failure, limitations = None, []
    failures = report.get("failures", [])
    if failures:
        audit.check(cohort == "same-topic" and len(failures) == 1,
                    "only_preregistered_single_backend_failure", label)
        candidate = failures[0]
        before = len(audit.failures)
        try:
            audit.equal(candidate.get("backend"), "claude_mem", "registered_failure_backend", label)
            audit.equal(candidate.get("stage"), "query", "registered_failure_stage", label)
            audit.equal(candidate.get("error_type"), "ValueError", "registered_failure_type", label)
            audit.equal(candidate.get("message"), "Native project scope violation", "registered_failure_message", label)
            audit.check(candidate.get("error", "").rstrip().endswith("ValueError: Native project scope violation"),
                        "original_scope_exception_retained", label)
            case = cases[candidate["case_id"]]
            for field in ("checkpoint", "query", "project"):
                audit.equal(candidate[field], case[field], "failure_canonical_case_metadata", label + "/" + field)
            audit.check(type(candidate["repetition"]) is int and candidate["repetition"] in range(REPEATS),
                        "failure_repetition_is_registered", label)
            refs = candidate["transport_trace_ids"]
            audit.equal(len(refs), 1, "failed_call_has_one_original_transport", label)
            checkpoint = audit.json(folder / f"checkpoint-{case['checkpoint']}.json")
            evidence = registered_scope_response(audit, by_id[refs[0]], documents[case["checkpoint"]],
                checkpoint["backends"]["claude_mem"], case["query"], case["project"], label + "/failure")
            audit.equal(candidate.get("scope_diagnosis"), evidence, "scope_diagnosis_independently_recomputes", label)
            if cohort == "same-topic" and len(failures) == 1 and evidence is not None and len(audit.failures) == before:
                failure = candidate
                limitations.append(evidence)
        except Exception as error:
            audit.check(False, "registered_failure_schema", label, error=f"{type(error).__name__}: {error}")
    expected, counters = [], Counter()
    sample_counts = {(identity, backend): REPEATS for identity in cases for backend in BACKENDS}
    stopped = False
    for identity, case in cases.items():
        if stopped:
            sample_counts.pop((identity, "claude_mem"))
            continue
        failed_here = failure is not None and identity == failure["case_id"]
        repeat_count = failure["repetition"] + 1 if failed_here else REPEATS
        if failed_here:
            sample_counts[(identity, "claude_mem")] = failure["repetition"]
        for repeat in range(repeat_count):
            checkpoint = case["checkpoint"]
            trace_id = f"{checkpoint}:claude_mem:{counters[checkpoint]}"
            counters[checkpoint] += 1
            expected.append({"trace_id": trace_id, "backend": "claude_mem", "checkpoint": checkpoint,
                             "case_id": identity, "project": case["project"], "repetition": repeat,
                             "status": "returned", "request": {"op": "search", "query": case["query"],
                                                                   "project": case["project"], "limit": 5}})
        stopped = failed_here
    traces = audit.unique(raw, ("trace_id",), {(row["trace_id"],) for row in expected}, label + "/transport")
    audit.equal([row.get("trace_id") for row in raw], [row["trace_id"] for row in expected],
                "original_transport_execution_order", label)
    by_call = {}
    for wanted in expected:
        row = traces.get((wanted["trace_id"],))
        if row is None:
            continue
        location = label + "/transport/" + wanted["trace_id"]
        for field, value in wanted.items():
            audit.equal(row.get(field), value, "transport_canonical_call_binding", location + "/" + field)
        audit.equal(row.get("response_sha256"), engineering.sha(row.get("response")), "transport_original_response_hash", location)
        by_call[(wanted["case_id"], wanted["repetition"])] = row
    if failure is not None:
        row = by_call.get((failure["case_id"], failure["repetition"]))
        audit.equal(failure["transport_trace_ids"], [row["trace_id"]] if row else [], "failed_query_exact_transport_binding", label)
    return sample_counts, by_call, limitations, failure


def audit_extended_native(audit, folder, cases, documents, label, sample_counts, transport):
    rows = audit.jsonl(folder / "native.jsonl")
    expected = set(sample_counts)
    index = audit.unique(rows, ("case_id", "backend"), expected, label + "/native")
    for key, row in index.items():
        if key not in expected:
            continue
        case_id, backend = key
        case = cases[case_id]
        context = f"{label}/{case_id}/{backend}"
        try:
            for field in ("query", "project", "checkpoint"):
                audit.equal(row[field], case[field], "native_case_metadata", context + "/" + field)
            samples = row["samples"]
            count = sample_counts[key]
            audit.equal([sample["repetition"] for sample in samples], list(range(count)), "exact_completed_native_repetitions", context)
            ids_per_repeat, digests = [], []
            for ordinal, sample in enumerate(samples):
                location = context + f"/repeat-{ordinal}"
                try:
                    ids, native = sample["hit_ids"], sample["native"]
                    if backend == "reme":
                        verify_reme_native(audit, native, ids, documents[case["checkpoint"]], case["project"], location)
                    else:
                        old.verify_native_payload(audit, backend, native, ids, documents[case["checkpoint"]],
                                                  case["project"], location)
                    if backend == "claude_mem":
                        observed = transport[(case_id, ordinal)]
                        audit.equal(sample.get("transport_trace_ids"), [observed["trace_id"]], "successful_query_exact_transport_binding", location)
                        audit.equal({key: value for key, value in native.items() if key != "bridge_ms"}, observed["response"],
                                    "validated_result_equals_original_transport", location)
                    digest = engineering.sha(old.stable_native(native))
                    audit.equal(sample["native_sha256"], digest, "native_digest_recomputes", location)
                    for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms"):
                        audit.check(old.finite_nonnegative(sample[field]), "valid_native_timing", location + "/" + field)
                    ids_per_repeat.append(ids)
                    digests.append(digest)
                except Exception as error:
                    audit.check(False, "native_sample_schema", location, error=f"{type(error).__name__}: {error}")
            audit.check(len(ids_per_repeat) == count and all(ids == ids_per_repeat[0] for ids in ids_per_repeat),
                        "completed_candidates_stable", context)
            audit.check(len(digests) == count and (not digests or len(set(digests)) == 1), "completed_nontiming_native_stability", context)
        except Exception as error:
            audit.check(False, "native_record_schema", context, error=f"{type(error).__name__}: {error}")
    return index


def audit_checkpoints(audit, folder, proto, documents, report, label):
    locked = audit.json(ROOT / "benchmarks/competitors/reme-lock.json")
    for step in proto[0]:
        checkpoint = step["checkpoint"]
        context = f"{label}/checkpoint-{checkpoint}"
        value = audit.json(folder / f"checkpoint-{checkpoint}.json")
        docs = documents[checkpoint]
        audit.equal(value.get("documents"), len(docs), "checkpoint_document_count", context)
        audit.equal(value.get("documents_sha256"), engineering.sha(list(docs.values())), "checkpoint_document_identity", context)
        metadata = value.get("backends", {}).get("reme", {})
        audit.equal(metadata.get("source_mapping"), [reme_identity(doc) for doc in docs.values()],
                    "reme_complete_source_mapping", context)
        audit.equal(metadata.get("page_count"), len(docs), "reme_indexed_page_count", context)
        audit.equal(metadata.get("native_chunk_count"), len(docs), "reme_single_native_chunk_per_page", context)
        audit.equal(metadata.get("embedding_store"), None, "reme_embedding_disabled", context)
        audit.equal(metadata.get("llm_constructed"), False, "reme_no_llm", context)
        audit.equal(metadata.get("python_network_attempts"), [], "reme_no_network_attempts", context)
        audit.equal(metadata.get("source", {}).get("commit"), locked.get("source", {}).get("commit"),
                    "reme_pinned_source_commit", context)
        matches = [entry for entry in report.get("checkpoints", []) if entry.get("checkpoint") == checkpoint]
        audit.equal(matches, [value], "report_checkpoint_binding", context)


class RetainedRowPartition:
    """Reuse the unchanged audit on explicit, already coverage-checked rows."""

    def __init__(self, audit, path, rows):
        self.audit, self.path, self.rows = audit, path, rows

    def __getattr__(self, name):
        return getattr(self.audit, name)

    def jsonl(self, path):
        if Path(path) != self.path:
            raise ValueError("Unexpected retained-row partition path")
        return self.rows


def audit_extended_packed(audit, folder, proto, documents, native, sample_counts, label):
    raw = audit.jsonl(folder / "raw.jsonl")
    expected = {(identity, backend, budget) for (identity, backend), count in sample_counts.items()
                if count == REPEATS for budget in BUDGETS}
    audit.unique(raw, ("case_id", "backend", "budget_chars"), expected, label + "/entire-packed-matrix")
    rows = {}
    for backend in BACKENDS:
        eligible = {identity: case for identity, case in proto[1].items()
                    if sample_counts.get((identity, backend)) == REPEATS}
        partition = RetainedRowPartition(audit, folder / "raw.jsonl", [row for row in raw if row.get("backend") == backend])
        partial_proto = (proto[0], eligible, proto[2], proto[3])
        rows.update(old.audit_packed_rows(partition, folder, partial_proto, (backend,), label + "/" + backend,
                                         documents=documents, native=native))
    return rows


def check_extended_report(audit, report, proto, rows, native, failure, label):
    complete = tuple(backend for backend in BACKENDS if failure is None or backend != "claude_mem")
    complete_rows = [row for row in rows.values() if row["backend"] in complete]
    partial_rows = [row for row in rows.values() if row["backend"] not in complete]
    summary = engineering.summarize(complete_rows) if complete_rows else []
    by_category = {category: engineering.summarize([row for row in complete_rows if row["category"] == category])
                   for category in sorted({row["category"] for row in complete_rows})}
    audit.equal(report.get("status"), "completed_with_backend_failures" if failure else "completed", "report_preserves_native_failures", label)
    audit.equal(report.get("integrity_passed"), failure is None, "failed_backend_not_declared_integrity_pass", label)
    audit.equal(report.get("dataset_sha256"), engineering.sha(proto[0]), "canonical_dataset_hash", label)
    audit.equal(report.get("case_count"), len(proto[1]), "reported_case_count", label)
    settings = report.get("settings", {})
    for key, value in {"backends": list(BACKENDS), "budgets_chars": list(BUDGETS), "repeats": REPEATS,
                       "limit": 5, "result_cache": False}.items():
        audit.equal(settings.get(key), value, "registered_extended_settings", label + "/" + key)
    for field in ("runtime", "evaluator"):
        manifest = report.get(field, {})
        audit.equal(manifest.get("sha256"), engineering.sha(manifest.get("files", {})), "extended_identity_manifest_hash", label + "/" + field)
        audit.equal(report.get(field + "_final_sha256"), manifest.get("sha256"), "extended_final_identity", label + "/" + field)
        audit.equal(report.get(field + "_unchanged"), True, "extended_identity_unchanged", label + "/" + field)
    for name in ("benchmarks/engineering_workflow.py", "benchmarks/engineering_components.py"):
        audit.equal(report.get("evaluator", {}).get("files", {}).get(name), old.file_sha(ROOT / name),
                    "unchanged_original_scorer_and_packer", label + "/" + name)
    audit.equal(report.get("summary"), summary, "only_complete_backend_summary_recomputes", label)
    audit.equal(report.get("by_category"), by_category, "only_complete_backend_categories_recompute", label)
    audit.equal(report.get("partial_summary"), engineering.summarize(partial_rows) if partial_rows else [],
                "diagnostic_partial_summary_recomputes_without_quality_eligibility", label)
    statuses = {backend: {"status": "completed" if backend in complete else "failed_or_incomplete",
                         "packed_rows": sum(row["backend"] == backend for row in rows.values()),
                         "expected_packed_rows": len(proto[1]) * len(BUDGETS)} for backend in BACKENDS}
    audit.equal(report.get("backend_status"), statuses, "exact_backend_completion_and_partial_counts", label)
    audit.equal(report.get("completed_native_query_backend_pairs"), len(native), "reported_native_pair_count", label)
    return summary, by_category, complete


def audit_extended_track(audit, folder, proto, label, cohort):
    report = audit.json(folder / "report.json")
    audit.equal(audit.json(folder / "dataset.json"), proto[0], "complete_canonical_dataset", label)
    documents = old.audit_documents(audit, folder, proto, label)
    sample_counts, transport, limitations, failure = audit_transport_and_failure(audit, folder, proto, documents, report, label, cohort)
    native = audit_extended_native(audit, folder, proto[1], documents, label, sample_counts, transport)
    rows = audit_extended_packed(audit, folder, proto, documents, native, sample_counts, label)
    summary, by_category, completed_backends = check_extended_report(audit, report, proto, rows, native, failure, label)
    timing = audit.capture("native_timing_schema", label, lambda: old.native_timing_summary(native, BACKENDS))
    audit.equal(report.get("native_timing"), timing, "native_timing_recomputes_exactly", label)
    audit.equal(report.get("cohort"), cohort, "registered_cohort_name", label)
    audit.equal(report.get("cohort_counts"), expected_counts(proto[1]), "registered_cohort_denominators", label)
    audit.equal(report.get("settings", {}).get("backends"), list(BACKENDS), "eight_registered_backends", label)
    missing_by_category = missing_categories(rows, proto[1])
    audit.equal(report.get("missing_evidence"), missing_by_category, "missing_categories_recompute_exactly", label)
    audit_checkpoints(audit, folder, proto, documents, report, label)
    return {"report": report, "rows": rows, "native": native, "documents": documents,
            "summary": summary, "by_category": by_category, "native_timing": timing,
            "completed_backends": completed_backends, "registered_limitations": limitations,
            "quality_matrix_complete": failure is None,
            "missing_by_category": missing_by_category,
            "missing_evidence": old.missing_evidence_summary(rows, proto[1], BACKENDS)}


def audit_smoke(audit, evidence):
    """Recheck the tiny real API evidence independently of the producer gate."""
    folder = evidence / "adapter-smoke"
    report, gate = audit.json(folder / "report.json"), audit.json(evidence / "smoke-eligibility.json")
    projects = ("scope-a", "scope-ab", "Scope-a", "absent-project")
    fixtures = {project: {"project": project, "session_id": "same-session", "task_id": "contract",
        "created_at": "2026-01-01T00:00:00Z", "messages": [
            {"role": "user", "content": "memorytoken_alpha source contract"},
            {"role": "assistant", "content": f"memorytoken_alpha uses exact value {value}."}]}
        for project, value in (("scope-a", "ALPHA17"), ("scope-ab", "BETA91"), ("Scope-a", "GAMMA42"))}
    raw_docs = audit.json(folder / "documents.json")
    docs = {doc["id"]: doc for doc in raw_docs}
    audit.equal(len(docs), 3, "smoke_three_distinct_source_ids", "smoke")
    audit.equal(len(raw_docs), 3, "smoke_no_duplicate_sources", "smoke")
    audit.equal(sorted(doc["project"] for doc in raw_docs), sorted(fixtures), "smoke_exact_original_projects", "smoke")
    for doc in raw_docs:
        source = fixtures[doc["project"]]
        verify_navigation_document(audit, doc, source, engineering.original_turn(source), "smoke/document/" + doc["id"])
    traces_raw = audit.jsonl(folder / "transport.jsonl")
    expected_ids = {(f"smoke:claude_mem:{index}",) for index in range(4)}
    traces = audit.unique(traces_raw, ("trace_id",), expected_ids, "smoke/transport")
    for index, project in enumerate(projects):
        trace = traces.get((f"smoke:claude_mem:{index}",), {})
        for key, wanted in {"backend": "claude_mem", "checkpoint": "smoke", "case_id": "smoke:" + project,
                            "project": project, "repetition": 0, "status": "returned",
                            "request": {"op": "search", "query": "memorytoken_alpha", "project": project, "limit": 5}}.items():
            audit.equal(trace.get(key), wanted, "smoke_original_transport_request", project + "/" + key)
        audit.equal(trace.get("response_sha256"), engineering.sha(trace.get("response")), "smoke_original_transport_hash", project)
    audit.equal(sorted(report.get("backends", {})), sorted(BACKENDS), "smoke_all_eight_registered_backends", "smoke")
    limitations, failed_projects = [], []
    for backend in BACKENDS:
        item = report.get("backends", {}).get(backend, {})
        samples = item.get("samples", [])
        audit.equal([sample.get("project") for sample in samples], list(projects), "smoke_four_fixed_project_requests", backend)
        for index, sample in enumerate(samples):
            context = f"smoke/{backend}/{sample['project']}"
            project = projects[index]
            audit.equal(sample.get("query"), "memorytoken_alpha", "smoke_fixed_query", context)
            trace = traces.get((f"smoke:claude_mem:{index}",), {}) if backend == "claude_mem" else None
            if trace is not None:
                audit.equal(sample.get("transport_trace_ids"), [trace.get("trace_id")], "smoke_original_transport_binding", context)
            if sample.get("status") == "passed":
                ids, native = sample["hit_ids"], sample["native"]
                audit.check((not ids) if project == "absent-project" else bool(ids), "smoke_expected_source_presence", context)
                if backend == "reme":
                    verify_reme_native(audit, native, ids, docs, project, context)
                else:
                    old.verify_native_payload(audit, backend, native, ids, docs, project, context)
                if trace is not None:
                    audit.equal({key: value for key, value in native.items() if key != "bridge_ms"}, trace.get("response"),
                                "smoke_success_equals_original_transport", context)
            else:
                audit.equal(backend, "claude_mem", "only_registered_smoke_backend_mismatch", context)
                audit.check(project in ("scope-a", "Scope-a"), "only_case_colliding_smoke_requests_mismatch", context)
                audit.equal(sample.get("status"), "failed", "smoke_scope_mismatch_remains_failed", context)
                audit.equal(sample.get("error_type"), "ValueError", "smoke_registered_exception_type", context)
                audit.equal(sample.get("error"), "Native project scope violation", "smoke_registered_exception_message", context)
                proof = registered_scope_response(audit, trace, docs, item.get("metadata", {}),
                                                  "memorytoken_alpha", project, context)
                if proof is not None:
                    limitations.append(proof)
                    failed_projects.append(project)
        audit.equal(item.get("status"), "failed" if any(sample.get("status") != "passed" for sample in samples) else "passed",
                    "backend_smoke_status_preserves_failed_calls", backend)
    failures = report.get("failures", [])
    audit.equal([failure.get("project") for failure in failures], failed_projects, "smoke_all_and_only_registered_failures", "smoke")
    for failure, proof in zip(failures, limitations):
        for key, wanted in {"backend": "claude_mem", "stage": "smoke", "query": "memorytoken_alpha",
                            "error_type": "ValueError", "message": "Native project scope violation",
                            "transport_trace_ids": [proof["trace_id"]], "scope_diagnosis": proof}.items():
            audit.equal(failure.get(key), wanted, "smoke_failure_independently_authenticated", key)
        audit.check(failure.get("error", "").rstrip().endswith("ValueError: Native project scope violation"),
                    "smoke_original_exception_retained", "smoke")
    expected_status = "failed" if limitations else "passed"
    audit.equal(report.get("status"), expected_status, "smoke_failure_never_declared_passed", "smoke")
    for key, wanted in {"schema": "project-navigation-execution-eligibility-v1",
                        "status": "eligible_with_registered_scope_mismatch" if limitations else "eligible",
                        "eligible_for_execution": True, "smoke_status": expected_status,
                        "all_smokes_passed": not limitations, "registered_limitations": limitations,
                        "blocking_reasons": [], "retained_failure_count": len(limitations)}.items():
        audit.equal(gate.get(key), wanted, "smoke_execution_eligibility_independently_recomputes", key)
    for name in ("report.json", "documents.json", "transport.jsonl"):
        audit.equal(gate.get("input_sha256", {}).get(name), hashlib.sha256(audit.payload(folder / name)).hexdigest(),
                    "smoke_gate_bound_to_original_evidence", name)
    return {"smoke_status": expected_status, "registered_limitations": limitations,
            "passed_backends": [backend for backend in BACKENDS if report["backends"][backend]["status"] == "passed"],
            "evaluator": report.get("evaluator", {})}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def forbidden_keys(value):
    if isinstance(value, dict):
        return bool({"text", "content", "context"} & value.keys()) or any(forbidden_keys(v) for v in value.values())
    if isinstance(value, list):
        return any(forbidden_keys(v) for v in value)
    return False


def audit_call_traffic(audit, row, context):
    for index, call in enumerate(row["calls"]):
        location = f"{context}/call-{index}"
        audit.check(old.finite_nonnegative(call["latency_ms"]), "contract_call_timing", location)
        payload = call["response"] if call["status"] == "ok" else {key: call[key] for key in ("error_type", "error")}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        audit.equal(call["serialized_response_chars"], len(encoded), "contract_serialized_chars", location)
        audit.equal(call["serialized_response_utf8_bytes"], len(encoded.encode("utf-8")), "contract_serialized_bytes", location)
    expected = {"calls": len(row["calls"]),
                "serialized_response_chars": sum(call["serialized_response_chars"] for call in row["calls"]),
                "serialized_response_utf8_bytes": sum(call["serialized_response_utf8_bytes"] for call in row["calls"]),
                "latency_ms": sum(call["latency_ms"] for call in row["calls"])}
    audit.equal(row.get("traffic"), expected, "contract_traffic_summary", context)


def audit_directory_query(audit, row, request, docs, context):
    audit.equal(row["request"], request, "directory_registered_request", context)
    entries, offset, total = [], 0, None
    for ordinal, call in enumerate(row["calls"]):
        location = f"{context}/page-{ordinal}"
        audit.equal(call["method"], "search_directory", "directory_native_method", location)
        audit.equal(call["args"], [request["query"], request["project"]], "directory_unchanged_query_scope", location)
        audit.equal(call["kwargs"], {"offset": offset, "limit": 2}, "directory_registered_pagination", location)
        audit.equal(call["status"], "ok", "directory_call_succeeded", location)
        value = call["response"]
        audit.equal(value["project"]["id"], request["project"], "directory_response_scope", location)
        audit.equal(value["match_fields"], ["title", "question", "directory"], "directory_only_metadata_fields", location)
        audit.check(not forbidden_keys(value), "directory_no_body_keys", location)
        leaves = list(strings(value))
        for doc in docs.values():
            assistant = doc["text"].partition("\n\nASSISTANT: ")[2]
            audit.check(not any(doc["text"] in leaf or (assistant and assistant in leaf) for leaf in leaves),
                        "directory_no_hidden_source_body", location + "/" + doc["id"])
        if total is None:
            total = value["total"]
        audit.equal(value["total"], total, "directory_stable_total", location)
        audit.check(type(total) is int and total >= 0 and len(value["entries"]) <= 2, "directory_bounded_results", location)
        entries.extend(value["entries"])
        continuation = value["next_offset"]
        if ordinal == len(row["calls"]) - 1:
            audit.equal(continuation, None, "directory_terminal_page", location)
        else:
            audit.check(type(continuation) is int and continuation > offset, "directory_forward_offset", location)
            offset = continuation
    audit.equal(len(entries), total, "directory_complete_pagination", context)
    audit.check(len({entry["section_id"] for entry in entries}) == len(entries), "directory_unique_sections", context)
    for entry in entries:
        identity = entry["matched_page_id"]
        if not audit.check(identity in docs and docs[identity]["project"] == request["project"],
                           "directory_original_page_scope", context + "/" + str(identity)):
            continue
        audit.equal(entry["title"], docs[identity]["title"], "directory_question_title", context + "/" + identity)
        audit.equal(entry["summary"], docs[identity]["title"], "directory_question_summary", context + "/" + identity)
        audit.equal(entry["source_refs"], [{key: docs[identity]["source_refs"][0][key]
                                          for key in ("project", "session_id", "turn_index")}],
                    "directory_source_address", context + "/" + identity)
        audit.equal(entry["breadcrumb"][0]["id"], request["project"], "directory_breadcrumb_scope", context + "/" + identity)
    if request["kind"] in ("body_only", "missing"):
        audit.equal(entries, [], "directory_body_only_and_absent_do_not_match", context)
    else:
        audit.check(any(entry["session_id"] == "active-config" for entry in entries), "directory_target_address_present", context)


def audit_roundtrip(audit, row, project, docs, originals, context):
    audit.equal(row["request"], {"project": project, "task_id": data.MAIN_TASK, "session_id": "active-config"},
                "navigation_public_descriptor", context)
    address = row["resolved_address"]
    audit.equal(address["project"], project, "navigation_address_project", context)
    page_id = address["page_id"]
    audit.check(page_id in docs and docs[page_id]["project"] == project, "navigation_page_scope", context)
    source_id = (project, "active-config", 0)
    audit.equal(address["source"], list(source_id), "navigation_source_identity", context)
    audit.equal([[ref[key] for key in ("project", "session_id", "turn_index")] for ref in docs[page_id]["source_refs"]],
                [list(source_id)], "navigation_page_original_source_identity", context)
    audit.equal(docs[page_id]["text"], originals[source_id], "navigation_page_is_requested_original_turn", context)
    methods = {call["method"] for call in row["calls"]}
    audit.equal(methods and sorted(methods), sorted(["toc", "chapter", "section", "read", "read_turn"]),
                "navigation_all_native_stages", context)
    page_parts, turn_parts, source_hash, page_offset, turn_offset = [], [], None, 0, 0
    encountered_chapters, encountered_sections, encountered_pages = set(), set(), set()
    for ordinal, call in enumerate(row["calls"]):
        location = f"{context}/call-{ordinal}"
        audit.equal(call["status"], "ok", "navigation_call_succeeded", location)
        value, method = call["response"], call["method"]
        if method == "toc":
            audit.equal(call["args"], [project], "toc_exact_project_request", location)
            audit.equal(value["project"]["id"], project, "toc_exact_project_response", location)
            for chapter in value["chapters"]:
                audit.equal(chapter["project_id"], project, "toc_chapter_scope", location)
                if chapter["task_id"] == "task:" + data.MAIN_TASK:
                    encountered_chapters.add(chapter["id"])
        elif method in ("chapter", "section"):
            audit.equal(call["kwargs"].get("project"), project, "navigation_guard_requested", location)
            audit.equal(value["project_id"], project, "navigation_directory_scope", location)
            allowed = encountered_chapters if method == "chapter" else encountered_sections
            audit.check(call["args"][0] in allowed, "navigation_uses_returned_address", location)
            audit.equal(call["args"], [address[method + "_id"]], "resolved_address_matches_navigated_directory", location)
            audit.equal(value["id"], call["args"][0], "directory_response_address_identity", location)
            if method == "chapter":
                encountered_sections.update(section["id"] for section in value["sections"] if section["session_id"] == "active-config")
            else:
                encountered_pages.update(page["id"] for page in value["pages"])
        else:
            audit.check(len(value["content"]) <= 128, "bounded_source_read", location)
            if source_hash is None:
                source_hash = value["source_hash"]
                audit.check(isinstance(source_hash, str) and re.fullmatch(r"[0-9a-f]{64}", source_hash) is not None,
                            "navigation_source_hash_format", location)
            audit.equal(value["source_hash"], source_hash, "navigation_source_revision_stable", location)
            original = docs[page_id]["text"] if method == "read" else originals[source_id]
            expected_offset = page_offset if method == "read" else turn_offset
            expected_end = min(expected_offset + 128, len(original))
            audit.equal(value["content"], original[expected_offset:expected_end], "native_read_exact_original_window", location)
            audit.equal(value["total_chars"], len(original), "native_read_original_total_chars", location)
            audit.equal(value["next_offset"], expected_end if expected_end < len(original) else None,
                        "native_read_contiguous_next_offset", location)
            if method == "read":
                audit.check(call["args"] == [page_id] and page_id in encountered_pages, "page_from_returned_directory", location)
                audit.equal(call["kwargs"], {"offset": page_offset, "limit": 128, "project": project}, "guarded_page_window", location)
                audit.equal(value["breadcrumb"][0]["id"], project, "guarded_page_response_scope", location)
                audit.equal(value["offset"], page_offset, "page_window_offset", location)
                expected_ref = {**docs[page_id]["source_refs"][0], "start": page_offset, "end": expected_end,
                                "turn_start": page_offset, "turn_end": expected_end}
                audit.equal(value["source_refs"], [expected_ref], "page_read_original_source_reference", location)
                page_parts.append(value["content"])
                page_offset += len(value["content"])
            else:
                audit.equal(call["args"], list(source_id), "turn_original_address", location)
                audit.equal(call["kwargs"], {"offset": turn_offset, "limit": 128, "source_hash": source_hash},
                            "source_hash_bound_turn_window", location)
                audit.equal(value["offset"], turn_offset, "turn_window_offset", location)
                ref = value["source_ref"]
                audit.equal([ref[key] for key in ("project", "session_id", "turn_index")], list(source_id),
                            "turn_reference_identity", location)
                audit.equal([ref[key] for key in ("start", "end", "turn_start", "turn_end")],
                            [0, len(value["content"]), turn_offset, turn_offset + len(value["content"])],
                            "turn_reference_window", location)
                audit.equal(value["message_indices"], [0, 1], "turn_original_message_indices", location)
                audit.equal(ref["message_indices"], [0, 1], "turn_reference_message_indices", location)
                turn_parts.append(value["content"])
                turn_offset += len(value["content"])
    audit.equal("".join(page_parts), docs[page_id]["text"], "entire_page_reconstructed", context)
    audit.equal("".join(turn_parts), originals[source_id], "entire_original_turn_reconstructed", context)
    audit.equal("".join(page_parts), "".join(turn_parts), "page_and_turn_are_the_same_original_source", context)
    return address


SCOPE_CASES = {
    "empty": ("ok", []), "sole-book": ("ok", ["scope-a"]),
    "multiple-books": ("error", []), "multiple-books-limit-one": ("error", []),
    "multiple-books-session-only": ("error", []), "known-chapter": ("ok", ["scope-a"]),
    "deliberate-global": ("ok", ["scope-a", "scope-ab"]), "empty-project": ("error", []),
    "whitespace-project": ("error", []), "unknown-project": ("ok", []),
    "conflicting-project-chapter": ("ok", []), "project-and-global": ("error", []),
    "explicit-project": ("ok", ["scope-a"]), "nonboolean-global": ("error", []),
}


def scope_kwargs(name, chapter):
    """Caller requests are fixed independently of producer expectation fields."""
    values = {
        "empty": {}, "sole-book": {}, "multiple-books": {},
        "multiple-books-limit-one": {"limit": 1}, "multiple-books-session-only": {"session": "shared"},
        "known-chapter": {"chapter": chapter}, "deliberate-global": {"all_projects": True},
        "empty-project": {"project": ""}, "whitespace-project": {"project": "   "},
        "unknown-project": {"project": "scope-missing"},
        "conflicting-project-chapter": {"project": "scope-ab", "chapter": chapter},
        "project-and-global": {"project": "scope-a", "all_projects": True},
        "explicit-project": {"project": "scope-a"}, "nonboolean-global": {"all_projects": 1},
    }
    return values[name]


def verify_scope_call(audit, row, name, chapter, originals, context):
    status, projects = SCOPE_CASES[name]
    audit.equal(len(row["calls"]), 1, "scope_single_native_request", context)
    call = row["calls"][0]
    audit.equal(call["method"], "recall", "scope_native_recall", context)
    audit.equal(call["args"], ["scopecontracttoken"], "scope_fixed_query", context)
    audit.equal(call["kwargs"], scope_kwargs(name, chapter), "scope_registered_parameters", context)
    audit.equal(call["status"], status, "scope_registered_outcome", context)
    audit.equal(row["request"], {"kwargs": scope_kwargs(name, chapter), "expected": status,
                                 "expected_projects": projects}, "scope_registered_request", context)
    if status == "error":
        audit.equal(call["error_type"], "ValueError", "scope_clear_refusal", context)
        audit.check("response" not in call, "scope_refusal_has_no_source_response", context)
        return
    response = call["response"]
    returned = sorted({ref["project"] for hit in response["results"] for ref in hit["source_refs"]})
    audit.equal(returned, sorted(projects), "scope_exact_native_source_projects", context)
    if not projects:
        audit.equal(response["context"], "", "no_scope_result_has_empty_context", context)
    blocks = []
    for ordinal, hit in enumerate(response["results"]):
        owners = {ref["project"] for ref in hit["source_refs"]}
        audit.check(len(owners) == 1, "scope_single_owner_per_hit", context + "/" + str(ordinal))
        if len(owners) == 1:
            errors = engineering.source_errors({"results": [hit], "context": response["context"]}, originals, next(iter(owners)))
            audit.equal(errors, [], "scope_original_provenance", context + "/" + str(ordinal))
        ref = hit["source_refs"][0]
        audit.check(isinstance(hit["id"], str) and re.fullmatch(r"p_[0-9a-f]{24}", hit["id"]) is not None,
                    "scope_citation_is_page_address", context + "/" + str(ordinal))
        audit.equal(hit["created_at"], "2026-01-01T00:00:00+00:00", "scope_original_timestamp", context)
        audit.equal(hit["breadcrumb"][0]["id"], ref["project"], "scope_breadcrumb_source_owner", context)
        blocks.append(f"[{hit['id']}] {ref['project']} / {ref['session_id']} | {hit['created_at']}\n{hit['text']}")
        if name == "known-chapter":
            audit.equal(hit["breadcrumb"][1]["id"], chapter, "resolved_chapter_matches_actual_source", context)
    audit.equal(response["context"], "\n\n".join(blocks), "scope_context_entirely_cited_originals", context)
    for identity, body in originals.items():
        if identity[0] not in projects:
            audit.check(body not in response["context"], "no_unreferenced_foreign_scope_body", context + "/" + identity[0])


def verify_navigation_document(audit, doc, session, original, context):
    refs = doc["source_refs"]
    audit.equal(len(refs), 1, "navigation_one_original_source", context)
    ref = refs[0]
    audit.equal(doc["project"], session["project"], "navigation_document_scope", context)
    audit.equal([ref[key] for key in ("project", "session_id", "turn_index")],
                [session["project"], session["session_id"], 0], "navigation_original_source_identity", context)
    audit.equal(doc["text"], original, "navigation_original_page", context)
    # Every registered source is a short one-turn question/answer pair. The
    # canonical question, not a producer-supplied document field, is the title.
    audit.equal(doc["title"], session["messages"][0]["content"], "navigation_canonical_question_title", context)
    audit.equal([ref[key] for key in ("start", "end", "turn_start", "turn_end")],
                [0, len(original), 0, len(original)], "navigation_complete_original_coordinates", context)
    audit.equal(ref["message_indices"], [0, 1], "navigation_original_messages", context)
    created = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    audit.equal(doc["created_at"], created, "navigation_original_timestamp", context)
    audit.equal(ref["created_at"], created, "navigation_original_reference_timestamp", context)


def audit_wrong_book(audit, row, identity, addresses, context):
    expected = {f"wrong-book:{project}:{kind}": {
        "project": project, "foreign_project": data.PROJECT_IDS[(index + 1) % len(data.PROJECT_IDS)], "address_kind": kind}
        for index, project in enumerate(data.PROJECT_IDS) for kind in ("chapter", "section", "page")}
    request = expected[identity]
    audit.equal(row["request"], request, "guard_canonical_case_request", context)
    project, neighbor, kind = request["project"], request["foreign_project"], request["address_kind"]
    audit.equal(len(row["calls"]), 2, "guard_control_and_mismatch_calls", context)
    control, mismatch = row["calls"]
    method = "read" if kind == "page" else kind
    address = addresses[neighbor][kind + "_id"]
    for value, expected_project in ((control, neighbor), (mismatch, project)):
        audit.equal(value["method"], method, "guard_native_method", context)
        audit.equal(value["args"], [address], "guard_real_returned_address", context)
        audit.equal(value["kwargs"], {"project": expected_project, "limit": 1}, "guard_exact_expected_project", context)
    audit.equal(control["status"], "ok", "guard_valid_read_control", context)
    audit.equal(mismatch["status"], "error", "guard_mismatched_book_refused", context)
    audit.check(mismatch["error_type"] in ("KeyError", "ValueError") and "response" not in mismatch,
                "guard_no_foreign_content_response", context)


def audit_contracts(audit, folder, proto):
    label = "navigation-contracts"
    report = audit.json(folder / "report.json")
    sources = audit.json(folder / "sources.json")
    final_checkpoint = proto[0][-1]["checkpoint"]
    audit.equal(sources, list(proto[3][final_checkpoint].values()), "navigation_canonical_sources", label)
    docs_list = audit.json(folder / "documents.json")
    docs = audit.unique(docs_list, ("id",), {(doc["id"],) for doc in docs_list}, label + "/documents")
    docs = {key[0]: value for key, value in docs.items()}
    originals = proto[2][final_checkpoint]
    seen_sources = []
    for identity, doc in docs.items():
        context = label + "/document/" + identity
        try:
            ref = doc["source_refs"][0]
            source = (ref["project"], ref["session_id"], ref["turn_index"])
            seen_sources.append(source)
            verify_navigation_document(audit, doc, proto[3][final_checkpoint][source[:2]], originals[source], context)
        except Exception as error:
            audit.check(False, "navigation_document_schema", context, error=str(error))
    audit.equal(sorted(seen_sources), sorted(originals), "navigation_exact_visible_sources", label)
    queries = {request["id"]: request for request in data.directory_queries()}
    audit.equal(audit.json(folder / "directory-requests.json"), data.directory_queries(), "registered_directory_queries", label)
    expected = {("registry",)} | {(identity,) for identity in queries} | {
        ("roundtrip:" + project,) for project in data.PROJECT_IDS} | {
        (f"wrong-book:{project}:{kind}",) for project in data.PROJECT_IDS for kind in ("chapter", "section", "page")} | {
        ("scope:" + name,) for name in SCOPE_CASES}
    rows = audit.unique(audit.jsonl(folder / "raw.jsonl"), ("case_id",), expected, label)
    addresses = {}
    for key, row in rows.items():
        context = label + "/" + str(key[0])
        if key not in expected:
            continue
        try:
            audit.equal(row["status"], "passed", "native_contract_passed", context)
            expected_kind = ("registry" if key[0] == "registry" else "directory" if key[0] in queries
                             else "roundtrip" if key[0].startswith("roundtrip:")
                             else "wrong_book" if key[0].startswith("wrong-book:") else "scope")
            audit.equal(row["kind"], expected_kind, "registered_contract_kind", context)
            audit.check(bool(row["checks"]) and all(item.get("passed") is True for item in row["checks"]),
                        "no_suppressed_contract_failures", context)
            audit_call_traffic(audit, row, context)
            identity = key[0]
            if identity == "registry":
                audit.equal(len(row["calls"]), 1, "registry_call_count", context)
                value = row["calls"][0]
                audit.equal(value["method"], "projects", "registry_native_api", context)
                projects = value["response"]
                audit.equal(sorted(project["id"] for project in projects), sorted(data.PROJECT_IDS), "registry_exact_ids", context)
                audit.check(all(project["name"] == data.PROJECT_NAME for project in projects), "registry_colliding_names", context)
            elif identity in queries:
                audit_directory_query(audit, row, queries[identity], docs, context)
            elif identity.startswith("roundtrip:"):
                project = identity[len("roundtrip:"):]
                addresses[project] = audit_roundtrip(audit, row, project, docs, originals, context)
        except Exception as error:
            audit.check(False, "navigation_contract_schema", context, error=f"{type(error).__name__}: {error}")
    scope_sources = audit.json(folder / "scope-sources.json")
    scope_originals = {(source["project"], source["session_id"], 0): engineering.original_turn(source) for source in scope_sources}
    audit.equal(sorted(scope_originals), [("scope-a", "shared", 0), ("scope-ab", "shared", 0)], "scope_fixture_source_ids", label)
    scope_chapter = audit.capture("scope_chapter_binding", label,
                                  lambda: rows[("scope:known-chapter",)]["calls"][0]["kwargs"]["chapter"])
    for key, row in rows.items():
        if key not in expected:
            continue
        identity = key[0]
        context = label + "/" + identity
        try:
            if identity.startswith("wrong-book:"):
                audit_wrong_book(audit, row, identity, addresses, context)
            elif identity.startswith("scope:"):
                name = identity[len("scope:"):]
                verify_scope_call(audit, row, name, scope_chapter, scope_originals, context)
        except Exception as error:
            audit.check(False, "scope_contract_schema", context, error=f"{type(error).__name__}: {error}")
    audit.equal(report.get("status"), "passed", "contract_report_passed", label)
    audit.equal(report.get("failures"), [], "contract_report_no_hidden_failures", label)
    audit.equal(report.get("case_count"), len(expected), "contract_report_case_count", label)
    kinds = {kind: {"cases": sum(row["kind"] == kind for row in rows.values()),
                    "passed": sum(row["kind"] == kind and row["status"] == "passed" for row in rows.values())}
             for kind in sorted({row["kind"] for row in rows.values()})}
    audit.equal(report.get("kinds"), kinds, "contract_group_counts_recompute", label)
    audit.equal(kinds, {"registry": {"cases": 1, "passed": 1}, "directory": {"cases": 32, "passed": 32},
                        "roundtrip": {"cases": 8, "passed": 8}, "wrong_book": {"cases": 24, "passed": 24},
                        "scope": {"cases": 14, "passed": 14}}, "registered_contract_group_counts", label)
    audit.equal(report.get("records"), [{"case_id": row["case_id"], "kind": row["kind"], "status": row["status"],
                                          "traffic": row.get("traffic")} for row in rows.values()],
                "contract_summary_records_recompute", label)
    for field in ("runtime", "evaluator"):
        value = report.get(field, {})
        audit.equal(value.get("sha256"), engineering.sha(value.get("files", {})), "contract_identity_manifest", label + "/" + field)
        audit.equal(report.get(field + "_final_sha256"), value.get("sha256"), "contract_final_identity", label + "/" + field)
        audit.equal(report.get(field + "_unchanged"), True, "contract_identity_unchanged", label + "/" + field)
    return {"report": report, "rows": rows, "kinds": kinds}


def compare_packed(audit, left, right, cases, backends, context):
    matches, mismatches = 0, []
    for case in cases:
        for backend in backends:
            for budget in BUDGETS:
                key = (case, backend, budget)
                location = f"{context}/{case}/{backend}/{budget}"
                a, b = left.get(key), right.get(key)
                if not audit.check(a is not None and b is not None, "bridge_pair_present", location):
                    mismatches.append(list(key))
                elif audit.equal(a["response"], b["response"], "entire_packed_response_equivalence", location):
                    matches += 1
                else:
                    mismatches.append(list(key))
    return {"expected_pairs": len(cases) * len(backends) * 2, "equal_pairs": matches,
            "mismatches": mismatches, "comparison": "All packed response fields, no exclusions"}


def verify_previous_release(audit, report, context):
    audit.equal(report.get("runtime", {}).get("sha256"), V060_RUNTIME_SHA,
                "previous_reference_is_published_v060_runtime", context)


def run(evidence, output, *, previous=DEFAULT_PREVIOUS):
    evidence, output, previous = Path(evidence).resolve(), Path(output).resolve(), Path(previous).resolve()
    if output.exists():
        raise FileExistsError("Choose a fresh output JSON; previous audits are retained")
    output.parent.mkdir(parents=True, exist_ok=True)
    audit = old.Audit()
    result = {"schema": "independent-project-navigation-audit-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Retained-output audit, no retrieval or quality tuning", "evidence_directory": str(evidence),
              "previous_directory": str(previous), "script_sha256": old.file_sha(__file__),
              "audit_helper_sha256": old.file_sha(old.__file__), "tracks": {}}
    try:
        engineering_proto, same_proto = protocol(engineering.workload()), protocol(data.workload())
        audit.equal(engineering.sha(engineering_proto[0]), ENGINEERING_SHA, "frozen_engineering_workload", "protocol")
        audit.equal(engineering.sha(same_proto[0]), SAME_TOPIC_SHA, "preregistered_same_topic_workload", "protocol")
        for case in same_proto[1].values():
            if case["category"] == "missing_evidence_neighbor":
                foreign = case["neighbor_evidence"][0]
                originals = same_proto[2][case["checkpoint"]]
                audit.check(foreign["project"] != case["project"] and foreign["quote"] in originals[
                    (foreign["project"], foreign["session_id"], 0)], "real_neighbor_negative_witness", case["id"])
                field = foreign["quote"].split("=", 1)[0]
                audit.check(all(field not in body for identity, body in originals.items() if identity[0] == case["project"]),
                            "neighbor_fact_absent_from_requested_project", case["id"])
        result["cohort_denominators"] = {"engineering": expected_counts(engineering_proto[1]),
                                         "same-topic": expected_counts(same_proto[1])}
        smoke = audit.capture("independent_smoke_audit", "adapter-smoke", lambda: audit_smoke(audit, evidence))
        if smoke is not None:
            result["smoke"] = smoke
        tracks = {}
        specs = (("native", evidence / "native", old.NATIVE_BACKENDS, False),
                 ("components", evidence / "components", ("book", "billion"), True),
                 ("memory_systems", evidence / "memory-systems", old.BACKENDS, True),
                 ("previous_native", previous / "native", old.NATIVE_BACKENDS, False),
                 ("previous_components", previous / "components", ("book", "billion"), True),
                 ("previous_memory_systems", previous / "memory-systems", old.BACKENDS, True))
        for label, folder, backends, component in specs:
            track = audit.capture("track_audit", label, lambda f=folder, b=backends, l=label, c=component:
                                  old.audit_track(audit, f, engineering_proto, b, l, c))
            if track is not None:
                tracks[label] = track
                if label.startswith("previous_"):
                    verify_previous_release(audit, track["report"], label)
        for label, cohort, proto in (("project_engineering", "engineering", engineering_proto),
                                     ("project_same_topic", "same-topic", same_proto)):
            track = audit.capture("extended_track_audit", label, lambda l=label, c=cohort, p=proto:
                                  audit_extended_track(audit, evidence / l.replace("_", "-"), p, l, c))
            if track is not None:
                tracks[label] = track
        for label, track in tracks.items():
            result["tracks"][label] = {"packed_rows_audited": len(track["rows"]),
                                        "native_pairs_audited": len(track["native"]) if track["native"] is not None else None,
                                        "summary": track["summary"], "by_category": track["by_category"],
                                        "native_timing": track["native_timing"], "missing_evidence": track["missing_evidence"],
                                        "missing_by_category": track.get("missing_by_category"),
                                        "completed_backends": track.get("completed_backends"),
                                        "quality_matrix_complete": track.get("quality_matrix_complete", True),
                                        "registered_limitations": track.get("registered_limitations", [])}
        contracts = audit.capture("navigation_contract_audit", "navigation-contracts",
                                  lambda: audit_contracts(audit, evidence / "navigation-contracts", same_proto))
        if contracts is not None:
            result["navigation_contracts"] = {"cases": len(contracts["rows"]), "kinds": contracts["kinds"]}
        current = [label for label in tracks if not label.startswith("previous_")]
        if current:
            identity = tracks[current[0]]["report"].get("runtime", {}).get("sha256")
            for label in current:
                audit.equal(tracks[label]["report"].get("runtime", {}).get("sha256"), identity,
                            "same_frozen_runtime_across_current_tracks", label)
            if contracts is not None:
                audit.equal(contracts["report"].get("runtime", {}).get("sha256"), identity,
                            "same_frozen_runtime_across_current_tracks", "navigation-contracts")
        if {"components", "memory_systems", "project_engineering"} <= tracks.keys():
            result["harness_equivalence"] = {
                "original_two_to_original_seven": compare_packed(audit, tracks["components"]["rows"], tracks["memory_systems"]["rows"],
                                                                  engineering_proto[1], ("book", "billion"), "two-to-seven"),
                "original_seven_to_extended_eight": compare_packed(audit, tracks["memory_systems"]["rows"], tracks["project_engineering"]["rows"],
                                                                   engineering_proto[1], old.BACKENDS, "seven-to-eight")}
            audit.equal(tracks["components"]["documents"], tracks["memory_systems"]["documents"], "same_original_page_bundles", "two-to-seven")
            audit.equal(tracks["memory_systems"]["documents"], tracks["project_engineering"]["documents"], "same_original_page_bundles", "seven-to-eight")
        result["previous_to_current_book"] = {}
        for name, previous_label, current_label in (("native", "previous_native", "native"),
                                                    ("whole_block", "previous_components", "project_engineering")):
            if {previous_label, current_label} <= tracks.keys():
                result["previous_to_current_book"][name] = [old.paired(tracks[previous_label]["rows"], tracks[current_label]["rows"],
                    engineering_proto[1], budget, "book", "book", "v0.6.0 -> current " + name) for budget in BUDGETS]
        result["current_book_vs_competitors"] = {}
        for label, proto in (("project_engineering", engineering_proto), ("project_same_topic", same_proto)):
            if label in tracks:
                result["current_book_vs_competitors"][label] = [old.paired(tracks[label]["rows"], tracks[label]["rows"], proto[1],
                    budget, backend, "book", "current shared whole-block components")
                    for backend in tracks[label]["completed_backends"] if backend != "book" for budget in BUDGETS]
        host, frozen = audit.json(evidence / "host.json"), audit.json(evidence / "freeze.json")
        audit.equal(host.get("preparation_only"), False, "full_quality_run_not_preparation_only", "host")
        for key, wanted in {"schema": "project-navigation-freeze-v1", "approved": True,
                            "engineering_dataset_sha256": ENGINEERING_SHA, "same_topic_dataset_sha256": SAME_TOPIC_SHA,
                            "backends": list(BACKENDS), "repeats": 3, "budgets_chars": list(BUDGETS),
                            "audit_sha256": old.file_sha(__file__), "audit_helper_sha256": old.file_sha(old.__file__),
                            "reader_asset_sha256": old.file_sha(ROOT / "src/memory_book/static/index.html")}.items():
            audit.equal(frozen.get(key), wanted, "approved_freeze_binding", key)
        if smoke is not None:
            audit.equal(smoke.get("evaluator", {}).get("sha256"), frozen.get("evaluator_sha256"),
                        "full_run_smoke_uses_frozen_protocol", "smoke")
        for label in ("project_engineering", "project_same_topic"):
            if label in tracks:
                for field in ("runtime", "evaluator"):
                    audit.equal(tracks[label]["report"].get(field, {}).get("sha256"), frozen.get(field + "_sha256"),
                                "executed_frozen_identity", label + "/" + field)
        result["source_commit"] = host.get("source_commit")
    except Exception:
        audit.check(False, "audit_execution", "run", error=traceback.format_exc())
    audit.finalize_inputs()
    audit.equal(old.file_sha(__file__), result["script_sha256"], "auditor_unchanged_during_audit", "audit")
    audit.equal(old.file_sha(old.__file__), result["audit_helper_sha256"], "audit_helper_unchanged_during_audit", "audit")
    result.update(status="passed" if not audit.failures else "failed", failures=audit.failures,
                  checks={"total": sum(audit.counts.values()), "failed": sum(audit.failed_counts.values()),
                          "by_name": {key: {"total": count, "failed": audit.failed_counts[key]} for key, count in sorted(audit.counts.items())}},
                  input_files=audit.inputs)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path, default=DEFAULT_PREVIOUS)
    args = parser.parse_args()
    result = run(args.evidence, args.output, previous=args.previous)
    print(json.dumps({"status": result["status"], "checks": result["checks"]["total"],
                      "failures": len(result["failures"]), "output": str(args.output)}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
