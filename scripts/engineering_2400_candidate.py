"""Replay one frozen Book candidate against immutable engineering controls.

Only Book executes. Three external components are reused from their completed
control runs, with file/row provenance; their timings are from different runs.
This is correction validation on known synthetic development data, not holdout
evaluation, a new external-product run, or a coding-LLM productivity measure.

Use --identity with an explicit candidate PYTHONPATH and the three --inputs to
obtain the runtime/evaluator/control-input fields for a candidate plan. This
mode reads and hashes files only; it never calls recall, ingestion, or scoring.
The plan must add passed preflight_validation with hashed artifacts before a
scored invocation. Existing output directories are never reused or removed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks import engineering_components as shared
from benchmarks import engineering_workflow as workflow
from scripts import engineering_open_source_2400 as control
from scripts import verify_engineering_2400_default as default_bridge

VERSION = "engineering-2400-candidate-replay-v1"
NOISE_LEVELS = (2, 8, 32)
BUDGET, LIMIT, REPEATS = 2400, 5, 3
CANDIDATE_VERSION = "0.4.1"
BACKENDS = control.BACKENDS
DEFAULT_PLAN = ROOT / "benchmarks/experiments/engineering-2400-open-source-plan.json"
CONTROL_SOURCE_ROOT = ROOT / "benchmarks/results/engineering-2400-20261115/frozen-source"
NON_EXECUTED_CONTROL_TEST = "tests/test_engineering_open_source_2400.py"
SETTINGS = {"budget_chars": BUDGET, "limit": LIMIT, "repeats": REPEATS,
            "noise_grid": list(NOISE_LEVELS)}
SCOPE = {
    "evidence": "Known authored synthetic development cases, used to diagnose the candidate; not an independent holdout.",
    "cohort": "The same 80 project/checkpoint case IDs at three noise levels; 25 query texts and 56 project/query combinations, not 240 independent questions.",
    "execution": "Only candidate Book is executed; every external row is copied from a completed immutable control and carries its source file and canonical row hash.",
    "ranking": "Unmodified shared.book_search: top five, native budget 100000, result cache disabled, no gold or future sources passed to retrieval.",
    "packing": "Unmodified shared.common_pack: complete original blocks, native order, 2400 characters including headings, no truncation or refill.",
    "consumer": "Unmodified known-policy extraction and handwritten algorithm checks; not generated-code accuracy.",
    "timing": "Candidate Book is a new execution batch. External timing values are retained control observations, not concurrent or interleaved measurements; no cross-batch speed winner or ratio is established.",
    "default_bridge": "After all timed searches of each checkpoint, call recall(query, project=...) with every recall option omitted. Compare context, ordered IDs, text, source_refs, created_at and score; do not aggregate its incidental latency as performance.",
    "validation": "Preflight test status is an attestation in the frozen candidate plan whose artifact hashes are checked. This runner does not execute regression tests.",
    "control_source": "The complete original source closure is checked against frozen-source, including the original test bytes. Only the unexecuted original runner test may differ in the live tree for version-fixture compatibility; its current bytes are still frozen in the candidate evaluator. All original execution helpers and locks must retain their exact control bytes.",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(path, manifest):
    path = Path(path).resolve()
    choices = [p for p in (path, Path(str(path) + ".gz")) if p.is_file()]
    require(len(choices) == 1, f"Expected exactly one plain or gzip input: {path}")
    selected = choices[0]
    original = selected.read_bytes()
    decoded = gzip.decompress(original) if selected.suffix == ".gz" else original
    identity = {"sha256": hashlib.sha256(original).hexdigest(), "bytes": len(original),
                "decoded_sha256": hashlib.sha256(decoded).hexdigest(), "decoded_bytes": len(decoded)}
    require(str(selected) not in manifest or manifest[str(selected)] == identity,
            f"Input changed between reads: {selected}")
    manifest[str(selected)] = identity
    return decoded, selected


def read_json(path, manifest):
    data, _ = read_bytes(path, manifest)
    return json.loads(data)


def read_rows(path, manifest):
    data, selected = read_bytes(path, manifest)
    rows, provenance = [], []
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        require(bool(line.strip()), f"Empty JSONL line: {selected}:{number}")
        row = json.loads(line)
        rows.append(row)
        provenance.append({"source_file": str(selected), "source_line": number,
                           "source_file_sha256": manifest[str(selected)]["sha256"],
                           "source_decoded_file_sha256": manifest[str(selected)]["decoded_sha256"],
                           "source_row_sha256": workflow.sha(row)})
    return rows, provenance


def input_snapshot(inputs):
    """Hash the fixed file set without ingestion, recall, packing or scoring."""
    manifest = {}
    for directory in inputs:
        for name in ("report.json", "raw.jsonl", "dataset.json",
                     *(f"documents-{i}.json" for i in range(1, 7))):
            read_bytes(directory / name, manifest)
    return manifest


def source_identity():
    files = dict(control.source_identity(control.DEFAULT_LOCKS)["files"])
    for path in (Path(__file__).resolve(), Path(default_bridge.__file__).resolve()):
        files[str(path.relative_to(ROOT))] = file_hash(path)
    return {"files": files, "sha256": workflow.sha(files)}


def control_archive_identity(old_plan, manifest):
    archive = read_json(CONTROL_SOURCE_ROOT / "manifest.json", manifest)
    expected = {f"src/memory_book/{name}": digest for name, digest in old_plan["runtime"]["files"].items()}
    expected.update(old_plan["evaluator"]["files"])
    require(set(archive["files"]) == set(expected)
            and archive["runtime_sha256"] == old_plan["runtime"]["sha256"]
            and archive["evaluator_sha256"] == old_plan["evaluator"]["sha256"],
            "Frozen control source archive has a different source inventory or identity")
    for name, digest in expected.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unexpected archived source path")
        _, selected = read_bytes(CONTROL_SOURCE_ROOT / name, manifest)
        actual, recorded = manifest[str(selected)], archive["files"][name]
        require(actual["decoded_sha256"] == digest == recorded["uncompressed_sha256"]
                and actual["decoded_bytes"] == recorded["uncompressed_bytes"]
                and actual["sha256"] == recorded["stored_sha256"] and actual["bytes"] == recorded["stored_bytes"]
                and selected == (CONTROL_SOURCE_ROOT.parent / recorded["stored_path"]).resolve(),
                "Frozen original runtime or evaluator source bytes changed")
    return {"directory": str(CONTROL_SOURCE_ROOT), "source_commit": archive["source_commit"],
            "files": manifest, "live_nonexecuted_test_exception": NON_EXECUTED_CONTROL_TEST}


def identities(inputs, control_plan):
    import memory_book
    archive = control_archive_identity(read_json(control_plan, {}), {})
    return {"book_version": memory_book.__version__, "runtime": workflow.runtime_identity(memory_book),
            "evaluator": source_identity(), "settings": SETTINGS,
            "control_plan_sha256": file_hash(control_plan),
            "control_source_archive": archive,
            "input_directories": [str(p) for p in inputs], "control_inputs": input_snapshot(inputs),
            "preflight_validation": {"status": "not_recorded", "artifacts": []},
            "scope": SCOPE}


def validate_plan(plan, old_plan, control_plan_path, runtime, evaluator, manifest, archive_manifest):
    import memory_book
    require(plan.get("book_version") == memory_book.__version__ == CANDIDATE_VERSION,
            "The frozen plan and imported runtime must both be v0.4.1")
    require(plan.get("runtime") == runtime and len(runtime["files"]) == 17,
            "The actual imported 17-file runtime differs from the frozen candidate plan")
    require(set(runtime["files"]) == set(old_plan["runtime"]["files"]),
            "The candidate runtime source-file inventory changed")
    python_paths = {Path(p).expanduser().resolve() for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p}
    require(Path(runtime["imported_runtime_root"]).parent in python_paths,
            "Select the candidate source explicitly through PYTHONPATH")
    require(plan.get("evaluator") == evaluator, "Candidate evaluator closure differs from its frozen plan")
    require(plan.get("settings") == SETTINGS, "No budget, limit, repeat or noise-grid changes are permitted")
    require(plan.get("control_plan_sha256") == file_hash(control_plan_path), "Frozen control plan changed")
    require(old_plan.get("book_version") == "0.4.0" and old_plan.get("schema") == "engineering-open-source-2400-frozen-plan-v1",
            "Unexpected original control plan")
    require(plan.get("control_source_archive") == control_archive_identity(old_plan, archive_manifest),
            "Frozen control source archive differs from the candidate plan")
    current_control = control.source_identity(control.DEFAULT_LOCKS)["files"]
    require(set(current_control) == set(old_plan["evaluator"]["files"])
            and all(current_control[name] == digest for name, digest in old_plan["evaluator"]["files"].items()
                    if name != NON_EXECUTED_CONTROL_TEST),
            "An original executed runner, scorer, exporter, adapter or lock changed")
    preflight = plan.get("preflight_validation", {})
    require(preflight.get("status") == "passed" and preflight.get("artifacts"),
            "Freeze passed generic current/history regression evidence in preflight_validation")
    for item in preflight["artifacts"]:
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        data, selected = read_bytes(path, manifest)
        require(manifest[str(selected)]["sha256"] == item["sha256"], "Preflight evidence hash changed")
        require(data, "Empty preflight validation artifact")
    parameters = inspect.signature(memory_book.MemoryBook.recall).parameters
    defaults = {key: parameters[key].default for key in
                ("budget_chars", "limit", "strategy", "coverage", "semantic", "budget_tokens")}
    require(defaults == {"budget_chars": BUDGET, "limit": LIMIT, "strategy": "book",
                         "coverage": False, "semantic": False, "budget_tokens": None},
            "Candidate native API defaults differ from the declared profile")
    return defaults


def load_control(directory, old_plan, manifest):
    report = read_json(directory / "report.json", manifest)
    require(report.get("version") == control.VERSION and report.get("status") == "completed"
            and report.get("integrity_passed") is True and report.get("integrity_checks")
            and all(value is True for value in report["integrity_checks"].values()),
            f"Control must be completed with passing integrity checks: {directory}")
    require(report["runtime"] == old_plan["runtime"] and report["evaluator"] == old_plan["evaluator"],
            "Control runtime/evaluator does not match its original frozen plan")
    require(report.get("runtime_final_sha256") == old_plan["runtime"]["sha256"]
            and report.get("evaluator_final_sha256") == old_plan["evaluator"]["sha256"],
            "Control source identity drifted during its run")
    settings, noise = report["settings"], report["settings"]["noise_per_step"]
    require(noise in NOISE_LEVELS and settings["budget_chars"] == BUDGET and settings["limit"] == LIMIT
            and settings["repeats"] == REPEATS and settings["book_result_cache"] is False
            and settings["book_native_budget_chars"] == 100000
            and settings["quality_repetition"] == 0 and tuple(settings["backends"]) == BACKENDS,
            "Control does not use the frozen evaluation settings")
    profile = next(item for item in old_plan["profiles"] if item["noise_per_step"] == noise)
    steps = read_json(directory / "dataset.json", manifest)
    require(workflow.sha(steps) == report["dataset_sha256"] == profile["dataset_sha256"]
            == workflow.sha(workflow.workload(noise)), "Control dataset differs from the frozen workload")
    cases = [case for step in steps for case in step["cases"]]
    require(len(cases) == len({case["id"] for case in cases}) == report["case_count"] == 80,
            "Require exactly the complete 80-case cohort")
    require([step["checkpoint"] for step in steps] == list(range(1, 7)), "Require six chronological checkpoints")
    rows, origins = read_rows(directory / "raw.jsonl", manifest)
    expected = {(case["id"], backend) for case in cases for backend in BACKENDS}
    by_key = {(row["case_id"], row["backend"]): row for row in rows}
    require(len(rows) == len(by_key) == 320 and set(by_key) == expected, "Missing, duplicate or foreign control rows")
    documents, visible = {}, {}
    for step in steps:
        number = step["checkpoint"]
        for session in step["sessions"]:
            visible[(session["project"], session["session_id"])] = session
        sources = workflow.visible_sources(visible)
        docs = read_json(directory / f"documents-{number}.json", manifest)
        recorded = next(c for c in report["checkpoints"] if c["checkpoint"] == number)
        require(workflow.sha(docs) == recorded["documents_sha256"] and len(docs) == recorded["documents"],
                "Control supplied-source bundle does not match its report")
        lookup = {doc["id"]: doc for doc in docs}
        require(len(lookup) == len(docs), "Duplicate control document IDs")
        documents[number] = docs
        for case in step["cases"]:
            for backend in BACKENDS:
                row = by_key[(case["id"], backend)]
                require(row["budget_chars"] == BUDGET and all(row[key] == case[key] for key in
                        ("project", "query", "category", "checkpoint")), "Control row differs from its case")
                require(len(row["latency_ms"]) == REPEATS and len(row["repeat_scores"]) == REPEATS
                        and row["repeat_outputs_equal"] and row["repeat_hit_ids_equal"], "Unstable or incomplete control repetitions")
                mapping = row["source_map"]
                require(len(mapping) <= LIMIT, "Control has more than five native slots")
                ids = [hit["document_id"] for hit in mapping if hit["document_id"] is not None]
                for hit in mapping:
                    if hit["document_id"] is None:
                        require(backend == "ai-memory-hybrid", "Unexpected unmapped control hit")
                        continue
                    doc = lookup[hit["document_id"]]
                    require(doc["project"] == case["project"] and hit["source_refs"] == doc["source_refs"]
                            and hit["source_text_sha256"] == hashlib.sha256(doc["text"].encode()).hexdigest(),
                            "Control source mapping differs from its supplied document")
                require(shared.common_pack(ids, lookup, case["project"], BUDGET) == row["response"],
                        "Control pack cannot be reconstructed from its native source mapping")
                rescored = workflow.score(case, row["response"], sources, BUDGET)
                require(rescored == row["score"] and all(score == rescored for score in row["repeat_scores"]),
                        "Control scores cannot be reproduced")
                require(rescored["within_budget"] and not rescored["source_errors"], "Invalid control evidence")
    require(workflow.summarize(rows) == report["summary"], "Control summary differs from its complete raw rows")
    return {"directory": str(directory), "noise": noise, "report": report, "steps": steps,
            "cases": cases, "documents": documents, "by_key": by_key,
            "origins": {(row["case_id"], row["backend"]): origin for row, origin in zip(rows, origins, strict=True)}}


def comparisons(candidate_rows, bundle):
    changes, lost_units = [], []
    case_by_id = {case["id"]: case for case in bundle["cases"]}
    for row in candidate_rows:
        old, new = bundle["by_key"][(row["case_id"], "book")]["score"], row["score"]
        outcomes = {}
        for metric, left, right in (
            ("complete_evidence", new["complete_evidence"] if new["answerable"] else None,
             old["complete_evidence"] if old["answerable"] else None),
            ("evidence_matches", new["matched_evidence"] if new["answerable"] else None,
             old["matched_evidence"] if old["answerable"] else None),
            ("fixed_consumer", new.get("fixed_consumer", {}).get("all_passed"),
             old.get("fixed_consumer", {}).get("all_passed")),
        ):
            outcomes[metric] = ("not_applicable" if left is None or right is None else
                                "candidate_gain" if left > right else "candidate_loss" if left < right else "tie")
        changes.append({"case_id": row["case_id"], "category": row["category"], "outcomes": outcomes,
                        "control_score": old, "candidate_score": new})
        for index, (before, after) in enumerate(zip(old["evidence_ranks"], new["evidence_ranks"], strict=True)):
            if before is not None and after is None:
                lost_units.append({"case_id": row["case_id"], "required_index": index,
                                   "required_evidence": case_by_id[row["case_id"]]["required"][index]})
    return {"cases": changes, "lost_previously_retrieved_evidence_units": lost_units,
            "metrics": {metric: dict(Counter(row["outcomes"][metric] for row in changes))
                        for metric in ("complete_evidence", "evidence_matches", "fixed_consumer")}}


def run_profile(bundle, output, runtime, evaluator):
    import memory_book
    from memory_book import MemoryBook
    output.mkdir(parents=True, exist_ok=False)
    noise = bundle["noise"]
    report = {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(),
              "package_version": memory_book.__version__, "runtime": runtime, "evaluator": evaluator,
              "scope": SCOPE, "dataset_sha256": bundle["report"]["dataset_sha256"],
              "settings": {**SETTINGS, "noise_per_step": noise, "backends": list(BACKENDS),
                           "quality_repetition": 0, "book_native_budget_chars": 100000, "book_result_cache": False},
              "control_directory": bundle["directory"], "control_runtime": bundle["report"]["runtime"],
              "upstream_locks": bundle["report"]["upstream_locks"],
              "timing_batches": {"book": "new candidate execution", "external_components": "reused immutable control execution"}}
    shared.write_json(output / "binding.json", report)
    shared.write_json(output / "dataset.json", bundle["steps"])
    book_rows, joined, samples, defaults, checkpoints, visible = [], [], [], [], [], {}
    stage, sequence = "prepare", 0
    try:
        with ExitStack() as stack:
            temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=f"engineering-candidate-{noise}-")))
            database = temporary / "book.db"
            streams = {name: stack.enter_context((output / f"{name}.jsonl").open("w", encoding="utf-8"))
                       for name in ("native", "book_raw", "raw", "default", "reuse", "operations")}
            for step in bundle["steps"]:
                checkpoint = step["checkpoint"]
                stage = f"checkpoint-{checkpoint}-source-replay"
                with MemoryBook(database, cache_size=0) as builder:
                    for session in step["sessions"]:
                        builder.ingest(session)
                        visible[(session["project"], session["session_id"])] = session
                    documents = shared.export_documents(builder, visible)
                shared.write_json(output / f"documents-{checkpoint}.json", documents)
                checkpoint_record = {"checkpoint": checkpoint, "documents": len(documents),
                                     "documents_sha256": workflow.sha(documents),
                                     "source_bundle_equal": documents == bundle["documents"][checkpoint]}
                checkpoints.append(checkpoint_record)
                require(checkpoint_record["source_bundle_equal"], "Candidate re-export changed the supplied source pages")
                lookup, sources = {doc["id"]: doc for doc in documents}, workflow.visible_sources(visible)
                checkpoint_rows = {}
                with MemoryBook(database, cache_size=0) as book:
                    for case in step["cases"]:
                        measurements = []
                        for repetition in range(REPEATS):
                            stage = f"checkpoint-{checkpoint}-{case['id']}-repeat-{repetition}"
                            sequence += 1
                            sample = {"sequence": sequence, "backend": "book", "case_id": case["id"],
                                      "checkpoint": checkpoint, "project": case["project"], "query": case["query"],
                                      "category": case["category"], "repetition": repetition}
                            control.append_json(streams["operations"], {**sample, "event": "search_started"})
                            try:
                                begin = time.perf_counter_ns()
                                native = shared.book_search(book, case["query"], case["project"])
                                sample["adapter_call_ms"] = (time.perf_counter_ns() - begin) / 1e6
                                # As in the original runner, Book is in process;
                                # these aliases do not imply a separate timer.
                                sample["native_search_ms"] = sample["adapter_call_ms"]
                                sample["native_bridge_ms"] = sample["adapter_call_ms"]
                                sample.update(native=native, native_sha256=workflow.sha(shared.stable(native)))
                                sample.update(control.map_hits(native, "book", lookup, case["project"]))
                                begin = time.perf_counter_ns()
                                packed = shared.common_pack(sample["hit_ids"], lookup, case["project"], BUDGET)
                                sample["common_pack_ms"] = (time.perf_counter_ns() - begin) / 1e6
                                sample.update(response=packed, packed_sha256=workflow.sha(packed),
                                              score=workflow.score(case, packed, sources, BUDGET))
                                require(sample["score"]["within_budget"] and not sample["score"]["source_errors"],
                                        "Candidate packed response failed source or budget validation")
                            except BaseException as error:
                                sample["error"] = {"type": type(error).__name__, "message": str(error)}
                                raise
                            finally:
                                samples.append(sample)
                                control.append_json(streams["native"], sample)
                            measurements.append(sample)
                            control.append_json(streams["operations"], {"sequence": sequence, "event": "search_completed"})
                        first = measurements[0]
                        row = {"case_id": case["id"], "backend": "book", **{key: case[key] for key in
                               ("query", "project", "checkpoint", "category")}, "budget_chars": BUDGET,
                               "latency_ms": [item["adapter_call_ms"] for item in measurements],
                               "common_pack_ms": first["common_pack_ms"],
                               "repeat_outputs_equal": len({item["packed_sha256"] for item in measurements}) == 1,
                               "repeat_native_outputs_equal": len({item["native_sha256"] for item in measurements}) == 1,
                               "repeat_hit_ids_equal": all(item["source_map"] == first["source_map"] for item in measurements),
                               "repeat_scores_equal": all(item["score"] == first["score"] for item in measurements),
                               "native_sequences": [item["sequence"] for item in measurements],
                               "native_first_output_sha256": first["native_sha256"], "source_map": first["source_map"],
                               "response": first["response"], "score": first["score"],
                               "repeat_scores": [item["score"] for item in measurements],
                               "execution_origin": {"kind": "candidate_book_replay", "runtime_sha256": runtime["sha256"]}}
                        book_rows.append(row)
                        checkpoint_rows[case["id"]] = row
                        control.append_json(streams["book_raw"], row)
                        joined.append(row)
                        control.append_json(streams["raw"], row)
                        for backend in BACKENDS[1:]:
                            original = bundle["by_key"][(case["id"], backend)]
                            origin = {"kind": "reused_immutable_control", **bundle["origins"][(case["id"], backend)],
                                      "native_sequences_resolve_in_control_directory": bundle["directory"], "executed_in_this_run": False}
                            reused = {**original, "execution_origin": origin}
                            require(workflow.sha({key: value for key, value in reused.items() if key != "execution_origin"})
                                    == origin["source_row_sha256"], "Reused external row was changed")
                            joined.append(reused)
                            control.append_json(streams["raw"], reused)
                            control.append_json(streams["reuse"], {"case_id": case["id"], "backend": backend, **origin})
                # All checkpoint search timings finish before default recall.
                with MemoryBook(database, cache_size=0) as book:
                    for case in step["cases"]:
                        stage = f"checkpoint-{checkpoint}-default-{case['id']}"
                        row = {"case_id": case["id"], "checkpoint": checkpoint, "project": case["project"],
                               "query": case["query"], "category": case["category"]}
                        try:
                            response = book.recall(case["query"], project=case["project"])
                            row["default_response"] = response
                            score = workflow.score(case, response, sources, BUDGET)
                            common = checkpoint_rows[case["id"]]
                            row.update(default_score=score, common_response=common["response"], common_score=common["score"],
                                       comparison=default_bridge.compare_payload(response, common["response"], score, common["score"]))
                        except BaseException as error:
                            row["error"] = {"type": type(error).__name__, "message": str(error)}
                            raise
                        finally:
                            control.append_json(streams["default"], row)
                        defaults.append(row)
                checkpoint_record["timed_book_calls"] = len(step["cases"]) * REPEATS
                checkpoint_record["default_calls_after_timing"] = len(step["cases"])
                shared.write_json(output / f"checkpoint-{checkpoint}.json", checkpoint_record)
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        report["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
    checks = {
        "all_80_book_cases": len(book_rows) == 80 and len({r["case_id"] for r in book_rows}) == 80,
        "all_240_book_repetitions": len(samples) == 240 and all("score" in sample for sample in samples),
        "all_320_joined_rows": len(joined) == 320 and len({(r["case_id"], r["backend"]) for r in joined}) == 320,
        "all_six_source_bundles_equal": len(checkpoints) == 6 and all(c["source_bundle_equal"] for c in checkpoints),
        "all_80_default_calls": len(defaults) == 80,
        "three_repetitions_stable": all(all(row[key] for key in ("repeat_outputs_equal", "repeat_native_outputs_equal",
                                                                 "repeat_hit_ids_equal", "repeat_scores_equal")) for row in book_rows),
        "zero_source_or_budget_errors": all(s.get("score", {}).get("within_budget") and not s["score"]["source_errors"] for s in samples)
            and all(row["default_score"]["within_budget"] and not row["default_score"]["source_errors"] for row in defaults),
    }
    report.update(case_count=len(book_rows), native_search_calls=len(samples), default_recall_calls=len(defaults),
                  reused_external_rows=sum(row["backend"] != "book" for row in joined), checkpoints=checkpoints,
                  summary=workflow.summarize(joined) if joined else [], pairwise=control.pairwise(joined),
                  candidate_vs_control=comparisons(book_rows, bundle), integrity_checks=checks,
                  integrity_passed=report["status"] == "completed" and all(checks.values()),
                  default_api_equivalent=len(defaults) == 80 and all(all(row["comparison"].values()) for row in defaults),
                  default_comparison_counts={field: sum(row["comparison"][field] for row in defaults)
                                             for field in (defaults[0]["comparison"] if defaults else ())})
    for dimension in ("category", "family", "checkpoint"):
        group = lambda row: row["project"].split("-", 1)[0] if dimension == "family" else row[dimension]
        report[f"by_{dimension}"] = {str(key): workflow.summarize([row for row in joined if group(row) == key])
                                     for key in sorted({group(row) for row in joined})}
    report["candidate_timing"] = {phase: {field: shared.timing([s[field] for s in samples if field in s
        and (s["repetition"] == 0) == (phase == "first_query_search")])
        for field in ("adapter_call_ms", "native_search_ms", "native_bridge_ms", "common_pack_ms")}
        for phase in ("first_query_search", "repeat_query_search")}
    report["reused_external_native_timing"] = {key: bundle["report"]["native_timing"][key] for key in BACKENDS[1:]}
    report["reused_external_delayed_read_timing"] = bundle["report"]["delayed_native_read_timing"]
    old_scores = [bundle["by_key"][(case["id"], "book")]["score"] for case in bundle["cases"]]
    before, after = default_bridge.quality_counts(old_scores), default_bridge.quality_counts([r["score"] for r in book_rows])
    report["quality_counts"] = {"control_book": before, "candidate_book": after}
    report["quality_acceptance"] = {
        "complete_evidence_not_lower": after["complete_evidence_cases"] >= before["complete_evidence_cases"],
        "fixed_consumer_not_lower": after["fixed_consumer_all_checks_passed"] >= before["fixed_consumer_all_checks_passed"],
        "base_no_previously_retrieved_evidence_loss": noise != 2 or not report["candidate_vs_control"]["lost_previously_retrieved_evidence_units"],
        "default_api_equivalent": report["default_api_equivalent"],
    }
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    shared.write_json(output / "report.json", report)
    return report


def run(inputs, output, control_plan_path, candidate_plan_path):
    directories = [Path(path).resolve() for path in inputs]
    output = Path(output).resolve()
    require(len(directories) == len(set(directories)) == 3, "Provide three distinct complete control directories")
    require(all(output != path and not output.is_relative_to(path) and not path.is_relative_to(output) for path in directories),
            "Candidate outputs must be separate from all immutable control directories")
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "status": "started", "created_at": datetime.now(timezone.utc).isoformat(), "scope": SCOPE,
              "input_directories": [str(p) for p in directories], "profiles": [],
              "environment": {"python": sys.version, "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                              "logical_cpu_count": os.cpu_count(), "PYTHONPATH": os.environ.get("PYTHONPATH", "")}}
    manifests = {"plans": {}, "controls": {}, "preflight": {}, "control_archive": {}}
    runtime_before = evaluator_before = None
    stage, bundles = "read-plans", []
    try:
        import memory_book
        old_plan = read_json(control_plan_path, manifests["plans"])
        plan = read_json(candidate_plan_path, manifests["plans"])
        runtime_before, evaluator_before = workflow.runtime_identity(memory_book), source_identity()
        report.update(package_version=memory_book.__version__, runtime=runtime_before, evaluator=evaluator_before,
                      candidate_plan=plan, control_plan_sha256=file_hash(control_plan_path))
        shared.write_json(output / "binding.json", report)
        stage = "validate-frozen-plan"
        report["defaults"] = validate_plan(plan, old_plan, control_plan_path, runtime_before, evaluator_before,
                                           manifests["preflight"], manifests["control_archive"])
        stage = "validate-immutable-controls"
        bundles = sorted((load_control(path, old_plan, manifests["controls"]) for path in directories), key=lambda b: b["noise"])
        require(tuple(b["noise"] for b in bundles) == NOISE_LEVELS, "Expected exactly noise levels 2, 8 and 32")
        require(all(bundle["cases"] == bundles[0]["cases"] for bundle in bundles), "Noise levels changed the case/evidence cohort")
        require(plan.get("control_inputs") == manifests["controls"], "Immutable control files differ from the candidate plan snapshot")
        require(plan.get("input_directories") == [str(path) for path in directories], "Control directory order differs from the frozen plan")
        shared.write_json(output / "source-inputs-before.json", manifests)
        for bundle in bundles:
            stage = f"noise-{bundle['noise']}-candidate-replay"
            profile = run_profile(bundle, output / f"noise-{bundle['noise']}", runtime_before, evaluator_before)
            report["profiles"].append(profile)
            require(profile["status"] == "completed" and profile["integrity_passed"], "Candidate profile failed; retain partial output and stop")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        report["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
    runtime_after = evaluator_after = None
    after = {}
    try:
        import memory_book
        runtime_after, evaluator_after = workflow.runtime_identity(memory_book), source_identity()
        after = {group: {path: file_hash(path) for path in entries} for group, entries in manifests.items()}
    except BaseException as error:
        report["final_verification_error"] = {"type": type(error).__name__, "message": str(error)}
    checks = {
        "three_complete_profiles": len(report["profiles"]) == 3 and all(p["status"] == "completed" and p["integrity_passed"] for p in report["profiles"]),
        "runtime_unchanged": runtime_before is not None and runtime_before == runtime_after,
        "evaluator_unchanged": evaluator_before is not None and evaluator_before == evaluator_after,
        "all_inputs_unchanged": after == {group: {path: identity["sha256"] for path, identity in entries.items()}
                                         for group, entries in manifests.items()},
    }
    report.update(integrity_checks=checks, integrity_passed=report["status"] == "completed" and all(checks.values()),
                  runtime_after=runtime_after, evaluator_after=evaluator_after, source_inputs_before=manifests,
                  source_inputs_after=after, native_candidate_search_calls=sum(p["native_search_calls"] for p in report["profiles"]),
                  default_recall_calls=sum(p["default_recall_calls"] for p in report["profiles"]),
                  reused_external_rows=sum(p["reused_external_rows"] for p in report["profiles"]),
                  preflight_validation=report.get("candidate_plan", {}).get("preflight_validation"))
    report["acceptance_passed"] = report["integrity_passed"] and all(all(p["quality_acceptance"].values()) for p in report["profiles"])
    if report["status"] == "completed" and not report["integrity_passed"]:
        report["status"] = "completed_with_integrity_failures"
    shared.write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs=3, type=Path, required=True, help="Completed immutable noise-2, noise-8, noise-32 directories, in that order")
    parser.add_argument("--control-plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--candidate-plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--identity", action="store_true", help="Print plan identity fields only; never ingest, recall or score")
    args = parser.parse_args()
    inputs = [path.resolve() for path in args.inputs]
    if args.identity:
        print(json.dumps(identities(inputs, args.control_plan.resolve()), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if not args.candidate_plan or not args.output:
        parser.error("--candidate-plan and --output are required for replay")
    report = run(inputs, args.output, args.control_plan.resolve(), args.candidate_plan.resolve())
    print(json.dumps({"status": report["status"], "integrity_passed": report["integrity_passed"],
                      "acceptance_passed": report["acceptance_passed"], "error": report.get("error"),
                      "profiles": [{"noise": p["settings"]["noise_per_step"], "quality": p["quality_counts"],
                                    "acceptance": p["quality_acceptance"]} for p in report["profiles"]]}, ensure_ascii=False))
    return 0 if report["acceptance_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
