"""After timing finishes, compare the default API with three saved 2400-char runs.

This is an output/quality compatibility check on the same synthetic development
questions, not a new performance experiment. It calls recall(query, project=...)
without overriding any recall options. It never calls the 100000-character
candidate-selection profile. Differences are retained, not optimized away.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_components as shared
from benchmarks import engineering_workflow as workflow

VERSION = "engineering-2400-default-applicability-v1"
NOISE_LEVELS = (2, 8, 32)
BUDGET = 2400
EVIDENCE_FIELDS = ("id", "text", "source_refs", "created_at")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verifier_identity():
    files = {str(path.relative_to(ROOT)): file_hash(path) for path in
             (Path(__file__).resolve(), Path(workflow.__file__).resolve(), Path(shared.__file__).resolve())}
    return {"files": files, "sha256": workflow.sha(files)}


def read_json(path, manifest):
    choices = [candidate for candidate in (path, Path(str(path) + ".gz")) if candidate.is_file()]
    require(len(choices) == 1, f"Expected exactly one JSON input, plain or gzip: {path.name}")
    selected = choices[0]
    data = selected.read_bytes()
    manifest[str(selected)] = hashlib.sha256(data).hexdigest()
    if selected.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))


def read_rows(directory, manifest):
    choices = [path for path in (directory / "raw.jsonl", directory / "raw.jsonl.gz") if path.is_file()]
    require(len(choices) == 1, "Each input must contain exactly one raw.jsonl or raw.jsonl.gz")
    path = choices[0]
    data = path.read_bytes()
    manifest[str(path)] = hashlib.sha256(data).hexdigest()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


def compare_payload(default, common, default_score, common_score):
    def values(response, field):
        return [hit[field] for hit in response["results"]]
    def projection(response):
        return [{field: hit[field] for field in EVIDENCE_FIELDS} for hit in response["results"]]
    return {
        "context_equal": default["context"] == common["context"],
        "ordered_result_ids_equal": values(default, "id") == values(common, "id"),
        "result_texts_equal": values(default, "text") == values(common, "text"),
        "source_refs_equal": values(default, "source_refs") == values(common, "source_refs"),
        "created_at_equal": values(default, "created_at") == values(common, "created_at"),
        "evidence_projection_equal": projection(default) == projection(common),
        "score_equal": default_score == common_score,
    }


def quality_counts(scores):
    answerable = [score for score in scores if score["answerable"]]
    consumers = [score["fixed_consumer"] for score in scores if "fixed_consumer" in score]
    return {
        "cases": len(scores), "answerable_cases": len(answerable),
        "required_evidence_units": sum(score["required_evidence"] for score in scores),
        "matched_evidence_units": sum(score["matched_evidence"] for score in scores),
        "complete_evidence_cases": sum(score["complete_evidence"] for score in answerable),
        "fixed_consumer_cases": len(consumers),
        "fixed_consumer_all_checks_passed": sum(consumer["all_passed"] for consumer in consumers),
        "stale_only_cases": sum(score["stale_only"] for score in scores),
        "missing_evidence_nonempty_cases": sum(score["missing_evidence_nonempty_context"] for score in scores),
        "source_validation_failures": sum(bool(score["source_errors"]) for score in scores),
        "budget_violations": sum(not score["within_budget"] for score in scores),
    }


def load_input(directory, runtime, manifest):
    report = read_json(directory / "report.json", manifest)
    require(report.get("version") == "engineering-open-source-2400-v1", "Unexpected comparison-runner version")
    require(report.get("status") == "completed" and report.get("integrity_passed"),
            "Input comparison must be complete and pass its recorded integrity checks")
    settings = report["settings"]
    noise = settings["noise_per_step"]
    require(noise in NOISE_LEVELS and settings["budget_chars"] == BUDGET and settings["limit"] == 5,
            "Expected the frozen noise 2/8/32, 2400-character, top-five experiment")
    require(report["package_version"] == "0.4.0" and report["runtime"]["sha256"] == runtime["sha256"],
            "Verification must use the same v0.4.0 runtime as the input comparison")
    for module in (workflow, shared):
        path = Path(module.__file__).resolve()
        require(report["evaluator"]["files"][str(path.relative_to(ROOT))] == file_hash(path),
                "The frozen workload, scorer or shared-page export code changed")
    steps = read_json(directory / "dataset.json", manifest)
    require(workflow.sha(steps) == report["dataset_sha256"] == workflow.sha(workflow.workload(noise)),
            "Saved input is not the declared chronological workload")
    cases = [case for step in steps for case in step["cases"]]
    ids = {case["id"] for case in cases}
    require(len(cases) == len(ids) == 80, "The full 80-question cohort is required")
    book_rows = [row for row in read_rows(directory, manifest) if row["backend"] == "book"]
    expected = {row["case_id"]: row for row in book_rows}
    require(len(book_rows) == len(expected) == 80 and set(expected) == ids,
            "The complete, unique Book row for every question is required")
    for case in cases:
        row = expected[case["id"]]
        require(row["budget_chars"] == BUDGET and all(row[key] == case[key]
                for key in ("query", "project", "checkpoint", "category")), "Saved Book row differs from its query")
    documents = {step["checkpoint"]: read_json(directory / f"documents-{step['checkpoint']}.json", manifest)
                 for step in steps}
    for checkpoint in report["checkpoints"]:
        require(workflow.sha(documents[checkpoint["checkpoint"]]) == checkpoint["documents_sha256"],
                "Saved supplied-source bundle hash differs from the comparison report")
    return {"directory": str(directory), "noise_per_step": noise, "steps": steps,
            "cases": cases, "expected": expected, "documents": documents,
            "dataset_sha256": report["dataset_sha256"], "comparison_evaluator_sha256": report["evaluator"]["sha256"]}


def verify(inputs, output):
    import memory_book
    from memory_book import MemoryBook
    directories = [Path(directory).resolve() for directory in inputs]
    require(len(directories) == len(set(directories)) == 3, "Provide three distinct completed experiment directories")
    output = Path(output).resolve()
    require(all(output != directory and not directory.is_relative_to(output) and not output.is_relative_to(directory)
                for directory in directories), "Keep the new verification output separate from all frozen inputs")
    output.mkdir(parents=True, exist_ok=False)
    runtime_before, verifier_before = workflow.runtime_identity(memory_book), verifier_identity()
    parameters = inspect.signature(MemoryBook.recall).parameters
    defaults = {name: parameters[name].default for name in
                ("budget_chars", "limit", "strategy", "coverage", "semantic", "budget_tokens")}
    report = {"version": VERSION, "status": "started", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "package_version": memory_book.__version__, "runtime": runtime_before, "verifier": verifier_before,
              "defaults": defaults, "input_directories": [str(path) for path in directories],
              "scope": "Post-timing output/quality compatibility on the same synthetic development cohort. "
                       "Three noise levels replay the same 80 questions, not 240 independent questions. "
                       "Only recall(query, project=...) is called; all recall options use actual API defaults. "
                       "cache_size=0 isolates output parity. Native metadata and incidental latency fields are retained "
                       "in raw responses but are neither compared as whole JSON nor summarized as performance. "
                       "Equality can support applicability of shared-pack quality points to this default API on these "
                       "inputs; it cannot transfer adapter/search timing to default-API latency or generalize to real coding."}
    shared.write_json(output / "binding.json", report)
    manifest, bundles, rows, checkpoints = {}, [], [], []
    stage = "validate-inputs"
    try:
        require(memory_book.__version__ == "0.4.0" and defaults == {
            "budget_chars": BUDGET, "limit": 5, "strategy": "book", "coverage": False,
            "semantic": False, "budget_tokens": None}, "Actual defaults differ from the selected v0.4.0 profile")
        bundles = sorted([load_input(directory, runtime_before, manifest) for directory in directories],
                         key=lambda bundle: bundle["noise_per_step"])
        require(tuple(bundle["noise_per_step"] for bundle in bundles) == NOISE_LEVELS, "Expected exactly noise levels 2, 8 and 32")
        require(all(bundle["cases"] == bundles[0]["cases"] for bundle in bundles),
                "The noise levels must replay exactly the same question and evidence labels")
        with (output / "raw.jsonl").open("w", encoding="utf-8") as trace:
            for bundle in bundles:
                noise, visible = bundle["noise_per_step"], {}
                with tempfile.TemporaryDirectory(prefix=f"engineering-default-{noise}-") as directory:
                    database = Path(directory) / "book.db"
                    for step in bundle["steps"]:
                        checkpoint = step["checkpoint"]
                        stage = f"noise-{noise}-checkpoint-{checkpoint}-source-replay"
                        with MemoryBook(database, cache_size=0) as builder:
                            for session in step["sessions"]:
                                builder.ingest(session)
                                visible[(session["project"], session["session_id"])] = session
                            documents = shared.export_documents(builder, visible)
                        equal_sources = documents == bundle["documents"][checkpoint]
                        checkpoints.append({"noise_per_step": noise, "checkpoint": checkpoint,
                                            "visible_sessions": len(visible), "source_bundle_equal": equal_sources})
                        require(equal_sources, "Replayed source pages differ from the measured supplied pages")
                        sources = workflow.visible_sources(visible)
                        with MemoryBook(database, cache_size=0) as book:
                            for case in step["cases"]:
                                stage = f"noise-{noise}-default-{case['id']}"
                                # The purpose of this verifier is to leave these
                                # recall options omitted, not emulate a default.
                                default = book.recall(case["query"], project=case["project"])
                                saved = bundle["expected"][case["id"]]
                                default_score = workflow.score(case, default, sources, BUDGET)
                                common_score = workflow.score(case, saved["response"], sources, BUDGET)
                                row = {"noise_per_step": noise, "case_id": case["id"], "project": case["project"],
                                       "query": case["query"], "checkpoint": checkpoint, "category": case["category"],
                                       "default_response": default, "common_response": saved["response"],
                                       "default_score": default_score, "common_score": common_score,
                                       "saved_common_score_reproduced": common_score == saved["score"],
                                       "comparison": compare_payload(default, saved["response"], default_score, common_score)}
                                rows.append(row)
                                trace.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                                trace.flush()
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
    try:
        runtime_after, verifier_after = workflow.runtime_identity(memory_book), verifier_identity()
        manifest_after = {path: file_hash(path) for path in manifest}
    except Exception as error:
        runtime_after = verifier_after = manifest_after = {}
        report["final_integrity_error"] = {"type": type(error).__name__, "message": str(error)}
    checks = {
        "all_three_noise_levels": len(bundles) == 3 and tuple(b["noise_per_step"] for b in bundles) == NOISE_LEVELS,
        "all_240_replays_present": len(rows) == 240 and len({(r["noise_per_step"], r["case_id"]) for r in rows}) == 240,
        "all_18_source_checkpoints_equal": len(checkpoints) == 18 and all(c["source_bundle_equal"] for c in checkpoints),
        "saved_common_scores_reproduced": all(row["saved_common_score_reproduced"] for row in rows),
        "zero_source_or_budget_errors": all(not row[key]["source_errors"] and row[key]["within_budget"]
                                            for row in rows for key in ("default_score", "common_score")),
        "runtime_unchanged": runtime_before == runtime_after,
        "verifier_unchanged": verifier_before == verifier_after,
        "frozen_inputs_unchanged": manifest == manifest_after,
    }
    profiles = []
    for noise in NOISE_LEVELS:
        entries = [row for row in rows if row["noise_per_step"] == noise]
        if not entries:
            continue
        comparisons = {field: {"equal": sum(row["comparison"][field] for row in entries), "total": len(entries),
                               "different_case_ids": [row["case_id"] for row in entries if not row["comparison"][field]]}
                       for field in entries[0]["comparison"]}
        profiles.append({"noise_per_step": noise, "replayed_cases": len(entries), "comparisons": comparisons,
                         "all_compared_evidence_and_scores_equal": all(all(row["comparison"].values()) for row in entries),
                         "default_quality": quality_counts([row["default_score"] for row in entries]),
                         "common_pack_quality": quality_counts([row["common_score"] for row in entries])})
    report.update(checks=checks, integrity_passed=all(checks.values()) and report["status"] == "completed",
                  profiles=profiles, checkpoints=checkpoints, default_recall_calls=len(rows),
                  source_inputs_before=manifest, source_inputs_after=manifest_after,
                  input_profiles=[{key: bundle[key] for key in
                                   ("directory", "noise_per_step", "dataset_sha256", "comparison_evaluator_sha256")}
                                  for bundle in bundles])
    report["all_compared_evidence_and_scores_equal"] = (report["integrity_passed"]
        and len(profiles) == 3 and all(profile["all_compared_evidence_and_scores_equal"] for profile in profiles))
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    # A real default/common difference is a result, not a reason to discard
    # the run or change the default. Execution integrity is a separate gate.
    shared.write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs=3, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.inputs, args.output)
    print(json.dumps({"status": report["status"], "integrity_passed": report["integrity_passed"],
                      "all_compared_evidence_and_scores_equal": report["all_compared_evidence_and_scores_equal"],
                      "default_recall_calls": report["default_recall_calls"], "profiles": report["profiles"],
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
