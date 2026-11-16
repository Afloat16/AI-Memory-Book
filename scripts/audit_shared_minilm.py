"""Explain equal scores by auditing frozen records, without running retrieval.

Revalidate the seven-component matrix with the existing source/packing auditor,
then compare the three shared-MiniLM configurations at distinct output levels.
Equality is an observation, not an acceptance condition. No model, index, query,
historical result or scoring rule is changed by this script.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import audit_memory_systems as retained

DENSE = ("chroma", "langgraph", "mem0")
DEFAULT_EVIDENCE = ROOT / "benchmarks/reports/v0.6.0-engineering/hosted/memory-systems"
FROZEN_FILES = (
    "benchmarks/engineering_components.py",
    "benchmarks/engineering_workflow.py",
    "benchmarks/memory_systems.py",
    "benchmarks/competitors/memory_systems.py",
    "benchmarks/competitors/memory_systems_worker.py",
    "benchmarks/competitors/memory-systems-lock.json",
)


def relative(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())


def framed_page(doc):
    session = doc["source_refs"][0]["session_id"]
    return (f"[{doc['id']}] {doc['project']} / {session} | "
            f"{doc['created_at']}\n{doc['text']}")


def compare_pair(left, right, cases, track):
    native, packed, documents = track["native"], track["rows"], track["documents"]
    records = []
    for case_id in sorted(cases):
        case = cases[case_id]
        docs = documents[case["checkpoint"]]
        a = native[case_id, left]["samples"][0]
        b = native[case_id, right]["samples"][0]
        ids_a, ids_b = a["hit_ids"], b["hit_ids"]
        bodies_a = [docs[identity]["text"] for identity in ids_a]
        bodies_b = [docs[identity]["text"] for identity in ids_b]
        differences = []
        for rank, (id_a, id_b) in enumerate(itertools.zip_longest(ids_a, ids_b), 1):
            if id_a == id_b:
                continue
            doc_a, doc_b = docs.get(id_a), docs.get(id_b)
            differences.append({
                "rank": rank, "left_id": id_a, "right_id": id_b,
                "left_source": doc_a["source_refs"] if doc_a else None,
                "right_source": doc_b["source_refs"] if doc_b else None,
                "same_body": bool(doc_a and doc_b and doc_a["text"] == doc_b["text"]),
                "left_framed_chars": len(framed_page(doc_a)) if doc_a else None,
                "right_framed_chars": len(framed_page(doc_b)) if doc_b else None,
            })
        budgets = []
        for budget in retained.BUDGETS:
            pa, pb = packed[case_id, left, budget], packed[case_id, right, budget]
            ra, rb = pa["response"], pb["response"]
            budgets.append({
                "budget_chars": budget,
                "same_complete_response": ra == rb,
                "same_context": ra["context"] == rb["context"],
                "same_ordered_bodies": [hit["text"] for hit in ra["results"]]
                                       == [hit["text"] for hit in rb["results"]],
                "same_full_score": pa["score"] == pb["score"],
                "same_context_chars": len(ra["context"]) == len(rb["context"]),
                "left_context_chars": len(ra["context"]),
                "right_context_chars": len(rb["context"]),
                "left_response_sha256": retained.workflow.sha(ra),
                "right_response_sha256": retained.workflow.sha(rb),
            })
        records.append({
            "case_id": case_id, "checkpoint": case["checkpoint"],
            "category": case["category"],
            "same_ordered_candidate_ids": ids_a == ids_b,
            "same_candidate_id_set": set(ids_a) == set(ids_b),
            "same_ordered_native_bodies": bodies_a == bodies_b,
            "same_framed_lengths_by_rank": [len(framed_page(docs[i])) for i in ids_a]
                                           == [len(framed_page(docs[i])) for i in ids_b],
            "same_complete_native_payload": retained.stable_native(a["native"])
                                            == retained.stable_native(b["native"]),
            "candidate_differences": differences,
            "budgets": budgets,
        })
    native_fields = (
        "same_ordered_candidate_ids", "same_candidate_id_set", "same_ordered_native_bodies",
        "same_framed_lengths_by_rank", "same_complete_native_payload",
    )
    packed_fields = (
        "same_complete_response", "same_context", "same_ordered_bodies",
        "same_full_score", "same_context_chars",
    )
    differences = [diff for row in records for diff in row["candidate_differences"]]
    return {
        "left": left, "right": right, "cases": len(records),
        "native": {field: sum(row[field] for row in records) for field in native_fields},
        "differing_rank_positions": len(differences),
        "differing_positions_with_identical_body": sum(d["same_body"] for d in differences),
        "differing_source_session_ids": sorted({
            ref["session_id"] for diff in differences
            for field in ("left_source", "right_source") for ref in diff[field] or []}),
        "budgets": [
            {"budget_chars": budget, **{
                field: sum(row["budgets"][index][field] for row in records)
                for field in packed_fields}}
            for index, budget in enumerate(retained.BUDGETS)
        ],
        "per_case": records,
    }


def document_repetition(documents):
    summaries = []
    for checkpoint, lookup in sorted(documents.items()):
        docs = list(lookup.values())
        maintenance = [doc for doc in docs if
                       doc["source_refs"][0]["session_id"].startswith("maintenance-")]
        occurrences = Counter((doc["project"], doc["text"]) for doc in maintenance)
        summaries.append({
            "checkpoint": checkpoint, "pages": len(docs),
            "unique_body_strings_across_projects": len({doc["text"] for doc in docs}),
            "maintenance_pages": len(maintenance),
            "unique_maintenance_body_strings_across_projects": len({doc["text"] for doc in maintenance}),
            "maximum_identical_maintenance_bodies_within_one_project": max(occurrences.values(), default=0),
        })
    return summaries


def run(evidence, output):
    audit = retained.Audit()
    protocol = retained.canonical_protocol()
    binding = audit.json(evidence / "binding.json")
    identities = {}
    for name in FROZEN_FILES:
        actual = retained.file_sha(ROOT / name)
        expected = binding.get("evaluator", {}).get("files", {}).get(name)
        audit.equal(actual, expected, "frozen_execution_source_unchanged", name)
        identities[name] = actual
    track = retained.audit_track(audit, evidence, protocol, retained.BACKENDS,
                                 "frozen-memory-systems", component=True)
    pairs = []
    if not audit.failures:
        pairs = [compare_pair(left, right, protocol[1], track)
                 for left, right in itertools.combinations(DENSE, 2)]
    audit.finalize_inputs()
    output.parent.mkdir(parents=True, exist_ok=True)
    case_rows = []
    for pair in pairs:
        case_rows.extend({"left": pair["left"], "right": pair["right"], **row}
                         for row in pair.pop("per_case"))
    case_payload = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")) + "\n" for row in case_rows).encode("utf-8")
    case_trace = output.with_name(output.stem + ".cases.jsonl.gz")
    case_trace.write_bytes(gzip.compress(case_payload, mtime=0))
    result = {
        "schema": "shared-minilm-record-audit-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if audit.failures else "passed",
        "scope": "Reanalysis of saved v0.6.0 records; no external retrieval rerun or new quality experiment",
        "evidence_directory": relative(evidence),
        "auditor_files": {relative(path): retained.file_sha(path) for path in
                          (Path(__file__), Path(retained.__file__))},
        "unchanged_execution_files": identities,
        "inputs": {relative(path): identity for path, identity in sorted(audit.inputs.items())},
        "revalidated_matrix": {
            "backends": list(retained.BACKENDS), "cases": len(protocol[1]),
            "native_query_backend_records": len(track["native"]),
            "native_call_samples": sum(len(row["samples"]) for row in track["native"].values()),
            "packed_outputs": len(track["rows"]),
        },
        "checks": {"total": sum(audit.counts.values()), "by_kind": dict(sorted(audit.counts.items()))},
        "failures": audit.failures,
        "summary": [row for row in track["summary"] if row["backend"] in DENSE],
        "pairs": pairs,
        "document_repetition_by_checkpoint": document_repetition(track["documents"]),
        "per_case_trace": {"path": relative(case_trace), "records": len(case_rows),
                           "sha256": retained.file_sha(case_trace),
                           "uncompressed_sha256": hashlib.sha256(case_payload).hexdigest()},
        "interpretation_limits": [
            "Pair comparisons use the first native repetition; all three repetitions were validated for stability.",
            "Whole-response equality includes omitted_for_budget, whereas context equality compares only delivered text.",
            "Equal page bodies do not imply identical source identities, timestamps, native scores or latency.",
            "Repeated authored maintenance bodies reduce this workload's ability to distinguish the three configurations.",
            "The native vectors and Mem0's internal collection metric were not archived; neither is reconstructed here.",
            "This is a repository-maintained audit, not third-party certification or held-out product evaluation.",
        ],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.evidence.resolve(), args.output.resolve())
    print(json.dumps({"status": result["status"], "checks": result["checks"]["total"],
                      "failures": len(result["failures"]), "output": str(args.output),
                      "pairs": [{key: value for key, value in pair.items() if key != "per_case"}
                                for pair in result["pairs"]]}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
