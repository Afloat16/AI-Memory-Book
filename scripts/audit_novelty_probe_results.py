"""Audit the saved old-data novelty probe without rerunning retrieval.

The original workflow's final Markdown byte check failed because canonical
JSON reordered its two candidate keys. Preserve all four original artifacts
and the failed completion marker. Recompute their numerical gates unchanged,
then require exact Markdown equality after restoring only the preregistered
candidate display order. This is a supplemental audit, not a new measurement.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_novelty_probe as probe

RESULT_COMMIT = "0f6b5da03b80f6119f050cd0d4116f19274cda07"
EVALUATOR_COMMIT = "848c0eb812e87e1cb5e3fb715c48459dcd1c4de8"
PREFIX = "benchmarks/reports/novelty-probe-43214192647-1"
ARTIFACT_SUFFIXES = (".json.gz", ".summary.json", ".md", ".completion.json")


def git_bytes(commit: str, path: str) -> bytes:
    probe.require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected a full immutable commit SHA")
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT)


def original_artifacts() -> tuple[dict, dict]:
    contents, identities = {}, {}
    for suffix in ARTIFACT_SUFFIXES:
        path = PREFIX + suffix
        value = (ROOT / path).read_bytes()
        probe.require(value == git_bytes(RESULT_COMMIT, path), "Original Git artifact changed: " + path)
        blob = subprocess.check_output(["git", "rev-parse", RESULT_COMMIT + ":" + path],
                                       cwd=ROOT, text=True).strip()
        contents[suffix] = value
        identities[path] = {"git_blob": blob, "sha256": probe.sha(value), "bytes": len(value)}
    return contents, identities


def source_identities(binding: dict) -> dict:
    """Hash committed files directly; do not import or execute product code."""
    sources, evidence = {}, {}
    for mode in probe.MODES:
        registered = binding["modes"][mode]
        commit = registered["commit"]
        paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit,
                                         "src/memory_book"], cwd=ROOT, text=True).splitlines()
        files = {path: git_bytes(commit, path) for path in paths}
        probe.require(len(files) == 17, "Frozen runtime file set changed")
        source_hash = hashlib.sha256()
        for path in sorted(files):
            if path.endswith(".py"):
                source_hash.update(path.removeprefix("src/memory_book/").encode())
                source_hash.update(b"\0" + files[path] + b"\0")
        probe.require(source_hash.hexdigest() == registered["source_sha256"],
                      "Committed runtime does not match recorded source hash")
        sources[mode] = files
        evidence[mode] = {"commit": commit, "source_sha256": source_hash.hexdigest(),
                          "runtime_files": len(files), "python_files": sum(p.endswith(".py") for p in files)}
    baseline = sources["default"]
    store = "src/memory_book/store.py"
    original = probe.ORIGINAL.encode()
    probe.require(baseline[store].count(original) == 1, "Baseline expression is not unique")
    for mode in probe.MODES:
        files = sources[mode]
        probe.require(files.keys() == baseline.keys(), "Runtime path set differs")
        expected = baseline[store].replace(original, probe.EXPRESSIONS[mode].encode())
        probe.require(files[store] == expected, "Candidate store change exceeds the registered expression")
        changed = [path for path in baseline if files[path] != baseline[path]]
        probe.require(changed == ([] if mode == "default" else [store]), "Unregistered runtime change")
        evidence[mode]["changed_runtime_files"] = changed
        evidence[mode]["store_sha256"] = probe.sha(files[store])
    return evidence


def presentation_order_audit(report: dict, saved: str) -> dict:
    """Accept only exact reproduction with the original registered key order."""
    candidates = report["screening"]["candidates"]
    probe.require(set(candidates) == set(probe.MODES[1:]), "Candidate set differs from registration")
    ordered = {**report, "screening": {**report["screening"],
        "candidates": {mode: candidates[mode] for mode in probe.MODES[1:]}}}
    expected = probe.markdown(ordered)
    probe.require(saved == expected, "Saved Markdown differs beyond registered candidate display order")
    canonical_rendering = probe.markdown(report)
    return {"passed": True,
        "original_audit_byte_comparison_passed": saved == canonical_rendering,
        "registered_order_reproduces_original_bytes": True,
        "registered_order": list(probe.MODES[1:]), "deserialized_order": list(candidates),
        "original_markdown_sha256": probe.sha(saved.encode()),
        "canonical_key_order_rendering_sha256": probe.sha(canonical_rendering.encode()),
        "exact_diff": "".join(difflib.unified_diff(saved.splitlines(True), canonical_rendering.splitlines(True),
            fromfile="original_saved", tofile="reconstructed_sorted_json"))}


def old_data_identity(report: dict) -> dict:
    path = "benchmarks/hotpot_manifest.json"
    raw = (ROOT / path).read_bytes()
    manifest = json.loads(raw)
    ids = manifest["selected_ids"]
    probe.require(manifest["expected_queries"] == len(ids) == 128 and len(set(ids)) == 128,
                  "Only the old 128-row Hotpot manifest is allowed")
    workers = [w for w in report["workers"] if w["cohort"] == "hotpot128"]
    probe.require(len(workers) == 3, "Missing old Hotpot workers")
    for worker in workers:
        probe.require(worker["query_ids"] == sorted(ids) and worker["query_ids_original_order"] == ids,
                      "Recorded Hotpot queries differ from the old 128-row manifest")
        probe.require(worker["dataset"]["provenance"]["selected_ids"] == ids,
                      "Recorded Hotpot provenance differs from the old manifest")
    probe.require("benchmarks.round2_data" not in sys.modules, "New-cohort loader must not be imported")
    return {"old_manifest_sha256": probe.sha(raw), "old_hotpot_queries": 128,
        "all_three_hotpot_workers_match_old_manifest": True,
        "cohorts": {c["name"]: {k: c[k] for k in ("queries", "sha256")} for c in report["plan"]["cohorts"]},
        "evidence_boundary": "Original pinned preparation filters Parquet by the old manifest before normalization. All recorded Hotpot IDs and cohort fingerprints match that old manifest. This audit reads only saved probe records and the old manifest; it does not load any question text, corpus, new256 manifest or new256 result, and makes no operating-system file-access-trace claim."}


def audit() -> dict:
    artifacts, identities = original_artifacts()
    compressed = artifacts[".json.gz"]
    raw = gzip.decompress(compressed)
    report = json.loads(raw)
    completion = json.loads(artifacts[".completion.json"])
    probe.require(report["evaluator_commit"] == completion["evaluator_commit"] == EVALUATOR_COMMIT,
                  "Original evaluator commit changed")
    probe.require(completion["status"] == "failed_or_incomplete" and completion["outcomes"] == {
        "source": "success", "prepare": "success", "measure": "success", "audit": "failure"},
        "Preserve the original failed audit marker")
    probe.require(completion["runtime_bindings"] == report["binding"]["modes"], "Completion bindings changed")
    probe.require(completion["files_sha256"] == {PREFIX + suffix: probe.sha(artifacts[suffix])
        for suffix in ARTIFACT_SUFFIXES[:3]}, "Original completion hashes changed")
    actual = probe.evaluator_hashes()
    probe.require(report["evaluator_hashes"] == actual, "Frozen evaluator files changed")
    for path, digest in actual.items():
        probe.require(probe.sha(git_bytes(EVALUATOR_COMMIT, path)) == digest,
                      "Evaluator differs from its original commit: " + path)
    plan_path = "benchmarks/experiments/novelty-probe-plan.json"
    probe.require(git_bytes(report["binding"]["plan_commit"], plan_path) == (ROOT / plan_path).read_bytes(),
                  "Preregistered plan changed")
    validation = probe.validate(report)
    probe.require(validation == report["validation"] and validation["passed"], "Incomplete or invalid raw matrix")
    probe.require(report["comparisons"] == probe.comparisons(report), "Paired comparisons changed")
    probe.require(report["screening"] == probe.screen(report["comparisons"], complete=True), "Declared screen changed")
    probe.require(json.loads(artifacts[".summary.json"]) == probe.summary(report, raw, compressed),
                  "Summary or gzip hash differs from raw records")
    presentation = presentation_order_audit(report, artifacts[".md"].decode())
    probe.require(not presentation["original_audit_byte_comparison_passed"],
                  "Expected the preserved historical key-order failure")
    before = {path: identity["sha256"] for path, identity in identities.items()}
    sources = source_identities(report["binding"])
    data = old_data_identity(report)
    probe.require(before == {path: probe.sha((ROOT / path).read_bytes()) for path in before},
                  "Audit modified an original artifact")
    return {"audit": "passed_with_documented_presentation_order_failure",
        "measurement_rerun": False, "original_artifacts_modified": False,
        "result_commit": RESULT_COMMIT, "evaluator_commit": EVALUATOR_COMMIT,
        "auditor_sha256": probe.sha(Path(__file__).read_bytes()),
        "original_completion_status": completion["status"], "original_outcomes": completion["outcomes"],
        "original_artifacts": identities, "full_report_sha256": probe.sha(raw),
        "validation": validation, "all_24_paired_comparisons_recomputed": True,
        "all_36_configuration_aggregates_recomputed": True,
        "screening_recomputed": report["screening"], "presentation": presentation,
        "runtime_sources": sources, "old_data_identity": data,
        "scope": "Independent read-only execution of the unchanged numerical gates plus Git/source/old-cohort binding and an exact registered-order Markdown check. Source-evidence retrieval only; no retrieval, generated answer or final performance experiment is executed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New supplemental audit JSON; never overwrites")
    args = parser.parse_args()
    probe.require(not args.output.exists(), "Preserve prior audit artifacts; choose a new output path")
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"audit": result["audit"], "samples": result["validation"]["query_configuration_mode_samples"],
                      "full_report_sha256": result["full_report_sha256"]}))


if __name__ == "__main__":
    main()
