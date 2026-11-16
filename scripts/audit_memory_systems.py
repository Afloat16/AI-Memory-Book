"""Independently audit retained real-memory comparison outputs, without retrieval.

This script imports only the unchanged workload, scorer and common packer. It
does not import the new runner/adapters, run an index, change a query or tune a
ranker. Every failed check is retained; a failed audit is not quality evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_workflow as workflow
from benchmarks.engineering_components import common_pack

BACKENDS = ("book", "billion", "claude_mem", "basic_memory", "chroma", "langgraph", "mem0")
NATIVE_BACKENDS = ("book", "flat", "recent_history", "no_memory")
BUDGETS = (1200, 2400)
REPEATS = 3
DEFAULT_PREVIOUS = ROOT / "benchmarks/reports/v0.5.0-engineering"
TIMING_FIELDS = {"latency_ms", "search_ms", "bridge_ms", "native_cpu_user_us", "native_cpu_system_us"}


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def strict_json(text):
    def reject(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    return json.loads(text, object_pairs_hook=strict_object, parse_constant=reject)


def stable_native(value):
    if isinstance(value, dict):
        return {key: stable_native(item) for key, item in value.items() if key not in TIMING_FIELDS}
    if isinstance(value, list):
        return [stable_native(item) for item in value]
    return value


def finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class Audit:
    def __init__(self):
        self.counts = Counter()
        self.failed_counts = Counter()
        self.failures = []
        self.inputs = {}

    def check(self, condition, code, context, **details):
        self.counts[code] += 1
        if not condition:
            self.failed_counts[code] += 1
            self.failures.append({"check": code, "context": context, **details})
        return bool(condition)

    def equal(self, actual, expected, code, context):
        # Python equality alone would silently accept true == 1 or 1200.0 ==
        # 1200. Canonical JSON equality retains the original protocol types.
        actual_hash, expected_hash = workflow.sha(actual), workflow.sha(expected)
        return self.check(actual_hash == expected_hash, code, context,
                          actual_sha256=actual_hash, expected_sha256=expected_hash)

    def capture(self, code, context, action, default=None):
        try:
            return action()
        except Exception as error:
            self.check(False, code, context, error=f"{type(error).__name__}: {error}")
            return default

    def bytes(self, path):
        path = Path(path).resolve(strict=True)
        data = path.read_bytes()
        self.inputs[str(path)] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        return data

    def payload(self, base):
        """Accept either transport; conflicting plain/gzip duplicates fail."""
        base = Path(base)
        plain, zipped = base.exists(), Path(str(base) + ".gz").exists()
        if not plain and not zipped:
            raise FileNotFoundError(str(base) + "[.gz]")
        raw = self.bytes(base) if plain else None
        unzipped = gzip.decompress(self.bytes(str(base) + ".gz")) if zipped else None
        if plain and zipped:
            self.check(raw == unzipped, "equivalent_duplicate_transports", str(base))
        return raw if plain else unzipped

    def json(self, path):
        return self.capture("read_json", str(path), lambda: strict_json(self.payload(path)), {})

    def jsonl(self, path):
        data = self.capture("read_jsonl", str(path), lambda: self.payload(path))
        if data is None:
            return []
        rows = []
        for number, line in enumerate(data.splitlines(), 1):
            if not line.strip():
                self.check(False, "nonempty_jsonl_record", f"{path}:{number}")
                continue
            row = self.capture("parse_jsonl", f"{path}:{number}", lambda: strict_json(line))
            if self.check(isinstance(row, dict), "jsonl_object", f"{path}:{number}"):
                rows.append(row)
        return rows

    def unique(self, rows, fields, expected, label):
        index = {}
        expected_types = [{type(key[n]) for key in expected} for n in range(len(fields))]
        self.check(len(rows) == len(expected), "exact_row_count", label,
                   actual=len(rows), expected=len(expected))
        for number, row in enumerate(rows):
            key = self.capture("row_identity_shape", f"{label}:{number}",
                               lambda: tuple(row[field] for field in fields))
            if key is None:
                continue
            if not self.check(all(type(value) in allowed for value, allowed in zip(key, expected_types)),
                              "row_identity_types", f"{label}:{number}",
                              actual_types=[type(value).__name__ for value in key]):
                continue
            try:
                if key in index:
                    self.check(False, "unique_row_identity", label, key=list(key),
                               first_sha256=workflow.sha(index[key]), duplicate_sha256=workflow.sha(row))
                else:
                    index[key] = row
            except TypeError:
                self.check(False, "row_identity_hashable", label, row_number=number)
        found = set(index)
        self.check(found == expected, "complete_exact_matrix", label,
                   missing=[list(k) for k in sorted(expected - found, key=str)],
                   unexpected=[list(k) for k in sorted(found - expected, key=str)])
        return index

    def finalize_inputs(self):
        for path, identity in self.inputs.items():
            self.capture("input_stable_after_audit", path,
                         lambda p=path, h=identity["sha256"]: self.check(
                             file_sha(p) == h, "input_stable_after_audit", p))


def canonical_protocol():
    steps = workflow.workload()
    cases, sources, sessions, visible = {}, {}, {}, {}
    for step in steps:
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"])] = session
        sources[step["checkpoint"]] = workflow.visible_sources(visible)
        sessions[step["checkpoint"]] = dict(visible)
        for case in step["cases"]:
            if case["id"] in cases:
                raise ValueError("Canonical workload has duplicate case IDs")
            cases[case["id"]] = case
    return steps, cases, sources, sessions


def audit_documents(audit, folder, protocol, label):
    steps, _, sources, sessions = protocol
    bundles = {}
    for step in steps:
        checkpoint = step["checkpoint"]
        context = f"{label}/checkpoint-{checkpoint}"
        docs = audit.json(folder / f"documents-{checkpoint}.json")
        if not audit.check(isinstance(docs, list), "document_bundle_is_list", context):
            bundles[checkpoint] = {}
            continue
        lookup, identities = {}, set()
        for number, doc in enumerate(docs):
            location = f"{context}/document-{number}"
            try:
                identity = doc["id"]
                if not audit.check(isinstance(identity, str) and bool(identity) and identity not in lookup,
                                   "unique_document_id", location):
                    continue
                lookup[identity] = doc
                refs = doc["source_refs"]
                if not audit.check(isinstance(refs, list) and len(refs) == 1,
                                   "one_complete_original_turn", location):
                    continue
                ref = refs[0]
                source_id = (ref["project"], ref["session_id"], ref["turn_index"])
                audit.check(source_id not in identities, "unique_document_source", location)
                identities.add(source_id)
                original = sources[checkpoint].get(source_id)
                audit.check(original is not None and doc["text"] == original,
                            "original_visible_page_body", location)
                audit.check(doc["project"] == source_id[0], "document_project", location)
                audit.equal([ref.get(k) for k in ("start", "turn_start", "end", "turn_end")],
                            [0, 0, len(doc["text"]), len(doc["text"])], "complete_source_coordinates", location)
                session = sessions[checkpoint].get(source_id[:2])
                if session:
                    audit.equal(doc["title"], session["title"], "original_document_title", location)
                    audit.equal(doc["created_at"], session["created_at"], "original_document_timestamp", location)
                    audit.equal(ref.get("created_at"), session["created_at"], "original_reference_timestamp", location)
                audit.equal(ref.get("message_indices"), [0, 1], "original_message_indices", location)
            except Exception as error:
                audit.check(False, "document_schema", location, error=f"{type(error).__name__}: {error}")
        audit.check(identities == set(sources[checkpoint]), "all_and_only_visible_sources", context,
                    actual=len(identities), expected=len(sources[checkpoint]))
        audit.check(len(docs) == len(sources[checkpoint]), "exact_document_count", context,
                    actual=len(docs), expected=len(sources[checkpoint]))
        bundles[checkpoint] = lookup
    return bundles


def verify_native_payload(audit, backend, native, ids, docs, project, context):
    """Authenticate IDs using fields actually returned by each upstream API."""
    audit.check(isinstance(ids, list) and len(ids) <= 5 and len(ids) == len(set(ids)),
                "native_top_five_distinct", context)
    if not audit.check(all(i in docs and docs[i]["project"] == project for i in ids),
                       "native_project_mapping", context):
        return
    if backend in ("book", "billion"):
        hits = native["results"]
        key, body = ("id", "text") if backend == "book" else ("ref", "preview")
        audit.equal([h[key] for h in hits], ids, "native_ids_match_payload", context)
        for identity, hit in zip(ids, hits):
            audit.equal(hit[body], docs[identity]["text"], "native_original_body", context + "/" + identity)
        return
    audit.equal(native["hit_ids"], ids, "native_ids_match_payload", context)
    if backend == "claude_mem":
        rows = native["native_payload"]
        audit.check(len(rows) == len(ids), "native_payload_count", context)
        for identity, row in zip(ids, rows):
            audit.equal(row["text"], docs[identity]["text"], "native_original_body", context + "/" + identity)
            audit.equal(row["title"], docs[identity]["title"], "native_original_title", context + "/" + identity)
            audit.equal(row["project"], project, "native_original_project", context + "/" + identity)
            audit.equal(row["memory_session_id"], "supplied-page:" + identity,
                        "claude_native_mapping", context + "/" + identity)
        return
    records = native["records"]
    audit.check(len(records) == len(ids), "adapter_record_count", context)
    for identity, record in zip(ids, records):
        audit.equal(record, {"id": identity, "project": project, "text": docs[identity]["text"]},
                    "adapter_original_record", context + "/" + identity)
    payload = native["native_payload"]
    if backend == "basic_memory":
        projects = {p: n + 1 for n, p in enumerate(sorted({d["project"] for d in docs.values()}))}
        audit.equal([r["permalink"] for r in payload], ids, "basic_memory_native_ids", context)
        for identity, row in zip(ids, payload):
            audit.equal(row["content_snippet"], docs[identity]["text"], "native_original_body", context + "/" + identity)
            audit.equal(row["project_id"], projects[project], "native_original_project", context + "/" + identity)
    elif backend == "chroma":
        audit.equal(payload["ids"], [ids], "chroma_native_ids", context)
        audit.equal(payload["documents"], [[docs[i]["text"] for i in ids]], "chroma_original_bodies", context)
        audit.equal([m["project"] for m in payload["metadatas"][0]], [project] * len(ids),
                    "chroma_native_projects", context)
    elif backend == "langgraph":
        audit.equal([r["key"] for r in payload], ids, "langgraph_native_ids", context)
        for identity, row in zip(ids, payload):
            audit.equal(row["namespace"], [project, "original_pages"], "langgraph_namespace", context + "/" + identity)
            for key in ("id", "project", "text", "title", "created_at"):
                audit.equal(row["value"][key], docs[identity][key], "langgraph_original_field", context + "/" + identity + "/" + key)
    elif backend == "mem0":
        rows = payload["results"]
        audit.equal([r["metadata"]["page_id"] for r in rows], ids, "mem0_native_page_ids", context)
        audit.check(len({r["id"] for r in rows}) == len(rows), "mem0_unique_native_ids", context)
        for identity, row in zip(ids, rows):
            audit.equal(row["memory"], docs[identity]["text"], "native_original_body", context + "/" + identity)
            audit.equal(row["user_id"], project, "mem0_native_user_id", context + "/" + identity)
            audit.equal(row["metadata"]["source_project"], project, "native_original_project", context + "/" + identity)
    else:
        raise ValueError("Unregistered native backend")


def audit_native_rows(audit, folder, cases, documents, backends, label):
    rows = audit.jsonl(folder / "native.jsonl")
    expected = {(case, backend) for case in cases for backend in backends}
    index = audit.unique(rows, ("case_id", "backend"), expected, label + "/native")
    for key, row in index.items():
        if key not in expected:
            continue
        case_id, backend = key
        context = f"{label}/native/{case_id}/{backend}"
        case = cases[case_id]
        try:
            for field in ("query", "project", "checkpoint"):
                audit.equal(row[field], case[field], "native_case_metadata", context + "/" + field)
            samples = row["samples"]
            audit.check(len(samples) == REPEATS, "three_native_repetitions", context, actual=len(samples))
            audit.equal([s["repetition"] for s in samples], list(range(REPEATS)),
                        "native_repetition_order", context)
            candidate_lists, digests = [], []
            for number, sample in enumerate(samples):
                location = f"{context}/repeat-{number}"
                ids, native = sample["hit_ids"], sample["native"]
                verify_native_payload(audit, backend, native, ids, documents[case["checkpoint"]],
                                      case["project"], location)
                digest = workflow.sha(stable_native(native))
                audit.equal(sample["native_sha256"], digest, "native_digest_recomputes", location)
                for timing in ("adapter_call_ms", "native_search_ms", "native_bridge_ms"):
                    audit.check(finite_nonnegative(sample[timing]), "valid_native_timing", location + "/" + timing)
                candidate_lists.append(ids)
                digests.append(digest)
            audit.check(bool(candidate_lists) and all(ids == candidate_lists[0] for ids in candidate_lists),
                        "three_candidates_stable", context)
            audit.check(len(set(digests)) == 1, "complete_nontiming_native_stability", context)
        except Exception as error:
            audit.check(False, "native_record_schema", context, error=f"{type(error).__name__}: {error}")
    return index


def audit_packed_rows(audit, folder, protocol, backends, label, *, documents=None, native=None):
    _, cases, sources, sessions = protocol
    rows = audit.jsonl(folder / "raw.jsonl")
    expected = {(case, backend, budget) for case in cases for backend in backends for budget in BUDGETS}
    index = audit.unique(rows, ("case_id", "backend", "budget_chars"), expected, label + "/packed")
    rescored = {}
    for key, row in index.items():
        if key not in expected:
            continue
        case_id, backend, budget = key
        case = cases[case_id]
        context = f"{label}/packed/{case_id}/{backend}/{budget}"
        try:
            for field in ("query", "project", "checkpoint", "category"):
                audit.equal(row[field], case[field], "packed_case_metadata", context + "/" + field)
            response = row["response"]
            score = workflow.score(case, response, sources[case["checkpoint"]], budget)
            audit.equal(row["score"], score, "score_recomputes_exactly", context)
            audit.check(not score["source_errors"], "source_validation", context, errors=score["source_errors"])
            audit.check(score["within_budget"], "character_budget", context,
                        actual=score["context_chars"], budget=budget)
            audit.check(row["repeat_outputs_equal"] is True, "claimed_repetition_stability", context)
            audit.check(len(row["latency_ms"]) == REPEATS and all(finite_nonnegative(t) for t in row["latency_ms"]),
                        "three_packed_timing_samples", context)
            if native is not None:
                native_row = native.get((case_id, backend))
                if audit.check(native_row is not None, "packed_has_native_record", context):
                    samples = native_row["samples"]
                    if samples:
                        rebuilt = common_pack(samples[0]["hit_ids"], documents[case["checkpoint"]],
                                              case["project"], budget)
                        audit.equal(response, rebuilt, "whole_packed_response_rebuilds", context)
                        audit.equal(row["native_first_output_sha256"], workflow.sha(stable_native(samples[0]["native"])),
                                    "packed_native_binding", context)
                        audit.equal(row["latency_ms"], [s["adapter_call_ms"] for s in samples],
                                    "packed_native_timing_binding", context)
            else:
                expected_digest = workflow.sha({k: v for k, v in response.items() if k != "latency_ms"})
                audit.equal(row["output_sha256"], [expected_digest] * REPEATS,
                            "native_workflow_repeat_digests", context)
                audit.equal(row["visible_sessions"], len(sessions[case["checkpoint"]]),
                            "native_workflow_visibility_count", context)
            rescored[key] = {**row, "score": score}
        except Exception as error:
            audit.check(False, "packed_record_schema", context, error=f"{type(error).__name__}: {error}")
    return rescored


def check_report(audit, report, protocol, rows, backends, label, *, component):
    steps, cases, _, _ = protocol
    audit.check(report.get("status") == "completed", "report_completed", label, status=report.get("status"))
    audit.equal(report.get("dataset_sha256"), workflow.sha(steps), "canonical_dataset_hash", label)
    audit.equal(report.get("case_count"), len(cases), "reported_case_count", label)
    settings = report.get("settings", {})
    audit.equal(settings.get("budgets_chars"), list(BUDGETS), "reported_budgets", label)
    audit.equal(settings.get("repeats"), REPEATS, "reported_repetitions", label)
    audit.equal(settings.get("limit"), 5, "reported_top_five", label)
    audit.check(settings.get("result_cache") is False, "result_cache_disabled", label)
    audit.check(report.get("runtime_unchanged") is True, "runtime_unchanged", label)
    audit.check(report.get("evaluator_unchanged") is True, "evaluator_unchanged", label)
    runtime = report.get("runtime", {})
    audit.equal(runtime.get("sha256"), workflow.sha(runtime.get("files", {})), "runtime_manifest_hash", label)
    audit.equal(report.get("runtime_final_sha256"), runtime.get("sha256"), "runtime_final_identity", label)
    expected_workflow_hash = file_sha(Path(workflow.__file__))
    if component:
        evaluator = report.get("evaluator", {})
        audit.equal(evaluator.get("sha256"), workflow.sha(evaluator.get("files", {})), "evaluator_manifest_hash", label)
        audit.equal(evaluator.get("files", {}).get("benchmarks/engineering_workflow.py"), expected_workflow_hash,
                    "unchanged_scorer_identity", label)
        audit.equal(evaluator.get("files", {}).get("benchmarks/engineering_components.py"),
                    file_sha(ROOT / "benchmarks/engineering_components.py"), "unchanged_common_packer_identity", label)
        audit.equal(report.get("evaluator_final_sha256"), evaluator.get("sha256"), "evaluator_final_identity", label)
        audit.check(report.get("integrity_passed") is True, "claimed_integrity_passed", label)
    else:
        audit.equal(report.get("evaluator_sha256"), expected_workflow_hash, "unchanged_scorer_identity", label)
    summary = workflow.summarize(list(rows.values())) if rows else []
    by_category = {category: workflow.summarize([r for r in rows.values() if r["category"] == category])
                   for category in sorted({r["category"] for r in rows.values()})}
    audit.equal(report.get("summary"), summary, "summary_recomputes_exactly", label)
    audit.equal(report.get("by_category"), by_category, "categories_recompute_exactly", label)
    if tuple(backends) == BACKENDS:
        audit.equal(settings.get("backends"), list(BACKENDS), "seven_registered_backends", label)
        audit.equal(report.get("failures"), [], "runner_has_no_suppressed_failures", label)
        audit.equal(report.get("completed_native_query_backend_pairs"), len(cases) * len(backends),
                    "reported_native_pair_count", label)
        for backend in backends:
            status = report.get("backend_status", {}).get(backend, {})
            audit.equal(status.get("status"), "completed", "backend_completed", label + "/" + backend)
            audit.equal(status.get("packed_rows"), len(cases) * len(BUDGETS), "backend_packed_count", label + "/" + backend)
    return summary, by_category


def native_timing_summary(native, backends):
    """Recompute retained native timings; these are distinct API boundaries."""
    result = {}
    for backend in backends:
        phases = {}
        for phase in ("first_query_search", "repeat_query_search"):
            fields = {}
            for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms"):
                values = [sample[field] for row in native.values() if row["backend"] == backend
                          for sample in row["samples"]
                          if (sample["repetition"] == 0) == (phase == "first_query_search")]
                fields[field] = {"samples": len(values), "p50_ms": statistics.median(values),
                                 "p95_ms": workflow.quantile(values, .95)} if values else None
            phases[phase] = fields
        result[backend] = phases
    return result


def missing_evidence_summary(rows, cases, backends):
    missing = sorted(c for c, case in cases.items() if not case["required"])
    result = []
    for backend in backends:
        for budget in BUDGETS:
            available = [(case, rows[(case, backend, budget)]) for case in missing
                         if (case, backend, budget) in rows]
            result.append({"backend": backend, "budget_chars": budget,
                           "expected_cases": len(missing), "audited_cases": len(available),
                           "case_ids": [case for case, _ in available],
                           "nonempty_context_case_ids": [case for case, row in available if row["response"]["context"]],
                           "empty_context_case_ids": [case for case, row in available if not row["response"]["context"]]})
    return result


def paired(left, right, cases, budget, left_backend, right_backend, label):
    """Gains mean right passes while left fails; do not hide stale-only changes."""
    result = {"comparison": label, "budget_chars": budget, "left_backend": left_backend,
              "right_backend": right_backend, "direction": "gains mean right passes and left fails",
              "available_cases": 0, "missing_case_ids": [], "change_details": []}
    names = ("complete_evidence", "fixed_policy", "stale_only")
    measurements = {name: {"eligible_cases": 0, "gains": [], "losses": [],
                           "unchanged_pass": [], "unchanged_fail": []} for name in names[:2]}
    stale = {"introduced": [], "resolved": [], "unchanged_stale": [], "unchanged_not_stale": []}
    for case_id, case in sorted(cases.items()):
        old, new = left.get((case_id, left_backend, budget)), right.get((case_id, right_backend, budget))
        if old is None or new is None:
            result["missing_case_ids"].append(case_id)
            continue
        result["available_cases"] += 1
        a, b = old["score"], new["score"]
        changed = False
        for name, eligible, x, y in (
            ("complete_evidence", bool(case["required"]), a["complete_evidence"], b["complete_evidence"]),
            ("fixed_policy", bool(case["consumer_family"]), a.get("fixed_consumer", {}).get("all_passed", False),
             b.get("fixed_consumer", {}).get("all_passed", False)),
        ):
            if not eligible:
                continue
            cell = measurements[name]
            cell["eligible_cases"] += 1
            category = "gains" if not x and y else "losses" if x and not y else "unchanged_pass" if x else "unchanged_fail"
            cell[category].append(case_id)
            changed |= x != y
        x, y = a["stale_only"], b["stale_only"]
        category = "introduced" if not x and y else "resolved" if x and not y else "unchanged_stale" if x else "unchanged_not_stale"
        stale[category].append(case_id)
        changed |= x != y
        # Also retain a worsened abstention/selected-policy mode when both booleans fail.
        ac, bc = a.get("fixed_consumer", {}), b.get("fixed_consumer", {})
        changed |= (ac.get("selected_policy"), ac.get("abstained")) != (bc.get("selected_policy"), bc.get("abstained"))
        if changed:
            result["change_details"].append({
                "case_id": case_id, "category": case["category"], "project": case["project"],
                "query": case["query"], "required_policy": case.get("consumer_expected_policy"),
                "left": {"complete_evidence": a["complete_evidence"], "stale_only": x,
                         "fixed_consumer": ac or None},
                "right": {"complete_evidence": b["complete_evidence"], "stale_only": y,
                          "fixed_consumer": bc or None},
            })
    for name, value in measurements.items():
        value["counts"] = {k: len(v) for k, v in value.items() if isinstance(v, list)}
        result[name] = value
    stale["counts"] = {k: len(v) for k, v in stale.items()}
    result["stale_only"] = stale
    result["complete_case_coverage"] = result["available_cases"] == len(cases)
    return result


def audit_track(audit, folder, protocol, backends, label, component):
    steps, cases, _, _ = protocol
    report = audit.json(folder / "report.json")
    dataset = audit.json(folder / "dataset.json")
    audit.equal(dataset, steps, "complete_canonical_dataset", label)
    documents, native = None, None
    if component:
        documents = audit_documents(audit, folder, protocol, label)
        native = audit_native_rows(audit, folder, cases, documents, backends, label)
    rows = audit_packed_rows(audit, folder, protocol, backends, label, documents=documents, native=native)
    summary, by_category = check_report(audit, report, protocol, rows, backends, label, component=component)
    native_timing = None
    if component:
        native_timing = audit.capture("native_timing_schema", label,
                                      lambda: native_timing_summary(native, backends))
        audit.equal(report.get("native_timing"), native_timing, "native_timing_recomputes_exactly", label)
    return {"report": report, "rows": rows, "documents": documents, "native": native,
            "summary": summary, "by_category": by_category, "native_timing": native_timing,
            "missing_evidence": missing_evidence_summary(rows, cases, backends)}


def run(evidence, output, *, previous=DEFAULT_PREVIOUS):
    evidence, output, previous = Path(evidence).resolve(), Path(output).resolve(), Path(previous).resolve()
    if output.exists():
        raise FileExistsError("Audit output already exists; choose a fresh JSON path")
    output.parent.mkdir(parents=True, exist_ok=True)
    audit = Audit()
    result = {"schema": "independent-memory-systems-audit-v1",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Retained-output audit only; no retrieval, indexing, query rewriting or new quality experiment",
              "evidence_directory": str(evidence), "previous_directory": str(previous),
              "script_sha256": file_sha(Path(__file__)), "tracks": {}}
    try:
        protocol = canonical_protocol()
        steps, cases, _, _ = protocol
        audit.equal(len(cases), 80, "canonical_case_count", "protocol")
        audit.equal(sum(bool(c["required"]) for c in cases.values()), 72, "canonical_answerable_count", "protocol")
        audit.equal(sum(len(c["required"]) for c in cases.values()), 80, "canonical_evidence_spans", "protocol")
        audit.equal(sum(bool(c["consumer_family"]) for c in cases.values()), 48, "canonical_policy_count", "protocol")
        audit.equal(sum(not c["required"] for c in cases.values()), 8, "canonical_missing_count", "protocol")
        result["dataset_sha256"] = workflow.sha(steps)
        result["scorer_sha256"] = file_sha(Path(workflow.__file__))
        result["common_packer_file_sha256"] = file_sha(ROOT / "benchmarks/engineering_components.py")
        specs = (
            ("native", evidence / "native", NATIVE_BACKENDS, False),
            ("components", evidence / "components", ("book", "billion"), True),
            ("memory_systems", evidence / "memory-systems", BACKENDS, True),
            ("previous_native", previous / "current-workflow", NATIVE_BACKENDS, False),
            ("previous_components", previous / "current-components", ("book", "billion"), True),
        )
        tracks = {}
        for label, folder, backends, component in specs:
            track = audit.capture("track_audit", label,
                                  lambda f=folder, b=backends, l=label, c=component:
                                  audit_track(audit, f, protocol, b, l, c))
            if track is None:
                continue
            tracks[label] = track
            result["tracks"][label] = {"packed_rows_audited": len(track["rows"]),
                                        "native_pairs_audited": len(track["native"]) if track["native"] is not None else None,
                                        "summary": track["summary"], "by_category": track["by_category"],
                                        "native_timing": track["native_timing"],
                                        "missing_evidence": track["missing_evidence"]}
        if {"native", "components", "memory_systems"} <= tracks.keys():
            baseline_runtime = tracks["native"]["report"].get("runtime", {}).get("sha256")
            for label in ("components", "memory_systems"):
                audit.equal(tracks[label]["report"].get("runtime", {}).get("sha256"), baseline_runtime,
                            "same_current_runtime_across_tracks", label)
            old, new = tracks["components"], tracks["memory_systems"]
            audit.equal(new["documents"], old["documents"], "identical_old_new_component_page_bundles", "components-vs-memory-systems")
            equal_responses, mismatches = 0, []
            for case_id in cases:
                for backend in ("book", "billion"):
                    for budget in BUDGETS:
                        key = (case_id, backend, budget)
                        a, b = old["rows"].get(key), new["rows"].get(key)
                        context = f"{case_id}/{backend}/{budget}"
                        if not audit.check(a is not None and b is not None, "old_new_bridge_pair_present", context):
                            mismatches.append(context)
                            continue
                        if audit.equal(b["response"], a["response"], "complete_packed_response_old_new_equivalence", context):
                            equal_responses += 1
                        else:
                            mismatches.append(context)
            result["old_new_harness_equivalence"] = {"expected_pairs": 320, "equal_pairs": equal_responses,
                                                       "mismatches": mismatches,
                                                       "comparison": "All packed-response fields; no fields excluded"}
        if {"previous_native", "native", "previous_components", "memory_systems"} <= tracks.keys():
            result["previous_to_current_book"] = {
                "native": [paired(tracks["previous_native"]["rows"], tracks["native"]["rows"], cases, budget,
                                  "book", "book", "v0.5.0 native -> current native") for budget in BUDGETS],
                "whole_block_components": [paired(tracks["previous_components"]["rows"], tracks["memory_systems"]["rows"],
                                                    cases, budget, "book", "book", "v0.5.0 whole blocks -> current whole blocks")
                                            for budget in BUDGETS],
            }
        if "memory_systems" in tracks:
            rows = tracks["memory_systems"]["rows"]
            result["current_book_vs_competitors"] = [paired(rows, rows, cases, budget, backend, "book",
                                                            "current shared whole-block components")
                                                     for backend in BACKENDS if backend != "book" for budget in BUDGETS]
    except Exception:
        audit.check(False, "audit_execution", "run", error=traceback.format_exc())
    audit.finalize_inputs()
    result.update(status="passed" if not audit.failures else "failed", failures=audit.failures,
                  checks={"total": sum(audit.counts.values()), "failed": sum(audit.failed_counts.values()),
                          "by_name": {key: {"total": count, "failed": audit.failed_counts[key]}
                                      for key, count in sorted(audit.counts.items())}},
                  input_files=audit.inputs)
    # Exclusive creation is checked again at write time to reject races.
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
