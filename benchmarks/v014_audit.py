"""Offline structural/source audit of v0.14 original journals; no API calls.

This re-scores saved responses against original sources and baseline snapshots.
It is an evidence audit using the registered evaluator, not an independent
quality benchmark or an untouched real-project holdout.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing, ExitStack
import gzip
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import v014_scale as scale
from benchmarks.v014_workload import cases, checkpoints, digest


def normalized(raw, surface):
    if surface != "directory":
        return raw
    reads = raw.get("reads", [])
    return {"context": "\n\n".join(r["content"] for r in reads),
            "results": [{"id": r["id"], "text": r["content"], "source_refs": r["source_refs"],
                         "breadcrumb": r["breadcrumb"]} for r in reads]}


def expected_count(bound, spec, arm, round_number):
    queries = {c["id"]: c for c in cases(spec)}
    selected = [queries[key] for key in scale.PERFORMANCE]
    recall = sum(c["surface"] == "recall" for c in selected)
    count = bound["repetitions"] * (len(selected) + recall * bound["warm_calls"])
    mutation = spec["axis"] in {"source_replacement", "source_deletion"}
    count += int(not mutation)
    if round_number == 0:
        count += len(queries) + len(selected) + 2
        if mutation:
            count += 3 * sum(c["category"] == "identifier" for c in queries.values())
        if arm == "candidate" and bound["required_fields_controls"]:
            count += sum(bool(scale.required_fields(c)) for c in queries.values())
    return count


def audit(directory):
    directory = Path(directory)
    bound = json.loads((directory / "binding.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    checks, errors, source_errors, cache_mismatches, api_errors = 0, [], [], [], []
    inventory, quality, field_controls = [], defaultdict(dict), []

    def check(condition, reason):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(reason)

    check(manifest["status"] == "completed", "run_not_completed")
    check([s["spec"] for s in manifest["stages"]] == checkpoints(bound["profile"]), "stage_matrix_differs")
    for stage in manifest["stages"]:
        spec = stage["spec"]
        snapshot = Path(stage["snapshot"]["path"])
        check(snapshot.is_file(), f"{spec['id']}:source_snapshot_missing")
        if not snapshot.is_file():
            continue
        check(scale.common.file_sha(snapshot) == stage["snapshot"]["sha256"], f"{spec['id']}:source_snapshot_hash_differs")
        expected = {(arm, rnd) for rnd in range(bound["rounds"]) for arm in ("baseline", "candidate")}
        check({(r["arm"], r["round"]) for r in stage["measurements"]} == expected,
              f"{spec['id']}:missing_or_extra_measurement_blocks")
        with ExitStack() as stack:
            raw_snapshot = stack.enter_context(scale.materialized_snapshot(stage["snapshot"], directory))
            db = stack.enter_context(closing(sqlite3.connect(f"file:{raw_snapshot}?mode=ro", uri=True)))
            db.row_factory = sqlite3.Row
            book = SimpleNamespace(db=db)
            previous_book = None
            if spec["axis"] in {"source_replacement", "source_deletion"}:
                parent = next(s for s in manifest["stages"] if s["spec"]["id"] == spec["parent"])
                parent_raw = stack.enter_context(scale.materialized_snapshot(parent["snapshot"], directory))
                previous = stack.enter_context(closing(sqlite3.connect(f"file:{parent_raw}?mode=ro", uri=True)))
                previous.row_factory = sqlite3.Row
                previous_book = SimpleNamespace(db=previous)
            for block in stage["measurements"]:
                folder = directory / block["output"]
                result = json.loads((folder / "result.json").read_text())
                arm, rnd = block["arm"], block["round"]
                prefix = f"{spec['id']}:{arm}:{rnd}"
                check(result["status"] == "completed", prefix + ":worker_not_completed")
                check(result["runtime"] == bound[arm], prefix + ":runtime_binding_differs")
                check(result["spec"] == spec, prefix + ":spec_differs")
                observations = [json.loads(line) for line in (folder / "observations.jsonl").read_text().splitlines()]
                with gzip.open(folder / "responses.jsonl.gz", "rt", encoding="utf-8") as stream:
                    packets = [json.loads(line) for line in stream]
                count = expected_count(bound, spec, arm, rnd)
                check(len(observations) == len(packets) == result["observations"] == count,
                      prefix + f":sample_count_differs:{len(observations)}:{len(packets)}:{count}")
                lookup = {c["id"]: c for c in cases(spec)}
                for index, (observation, packet) in enumerate(zip(observations, packets), 1):
                    check(observation["sequence"] == packet["sequence"] == index, prefix + f":sequence:{index}")
                    raw = packet["original_response"]
                    check(digest(raw) == observation["raw_sha256"], prefix + f":raw_hash:{index}")
                    reduced = {key: value for key, value in observation.items()
                               if key not in {"raw_gzip_offset", "raw_gzip_bytes", "raw_sha256"}}
                    check(reduced == packet["observation"], prefix + f":journal_pair:{index}")
                    if observation["error"] is not None:
                        api_errors.append({"block": prefix, "sequence": index, "error": observation["error"]})
                        continue
                    check(raw is not None, prefix + f":missing_successful_response:{index}")
                    check(digest(scale.common.stable_response(raw)) == observation["stable_response_sha256"],
                          prefix + f":stable_hash:{index}")
                    check(digest(scale.date_invariant_response(raw)) == observation["date_invariant_response_sha256"],
                          prefix + f":date_invariant_hash:{index}")
                    case = lookup[observation["case"]]
                    preceding = spec
                    if observation["mode"] in {"lifecycle-before", "lifecycle-warm"}:
                        preceding = dict(spec, revision=0 if spec["axis"] == "source_replacement" else 1,
                                         delete_config=False)
                        case = next(c for c in cases(preceding) if c["id"] == observation["case"])
                    response = normalized(raw, case["surface"])
                    if preceding is not spec:
                        rescored = scale.score(response, case, preceding, previous_book)
                    else:
                        rescored = scale.score(response, case, spec, book)
                    check(rescored == observation["score"], prefix + f":original_response_score:{index}")
                    if rescored["source_errors"]:
                        source_errors.append({"block": prefix, "sequence": index, "errors": rescored["source_errors"]})
                    if not observation["cache_mode_valid"]:
                        cache_mismatches.append({"block": prefix, "sequence": index, "mode": observation["mode"]})
                    if observation["mode"] == "quality":
                        quality[spec["id"], case["id"]][arm] = rescored
                    if observation["mode"] == "required-fields":
                        field_controls.append({"checkpoint": spec["id"], "case": case["id"], "score": rescored})
                inventory.append({"block": prefix, "observations": len(observations),
                    "response_sha256": scale.common.file_sha(folder / "responses.jsonl.gz"),
                    "observations_sha256": scale.common.file_sha(folder / "observations.jsonl")})
    regressions = [{"checkpoint": checkpoint, "case": case, "baseline": pair["baseline"], "candidate": pair["candidate"]}
                  for (checkpoint, case), pair in quality.items()
                  if set(pair) == {"baseline", "candidate"} and pair["baseline"]["complete"] is True
                  and pair["candidate"]["complete"] is False]
    return {"protocol": scale.PROTOCOL, "audit_type": "offline_saved_response_and_source_integrity",
            "checks": checks, "integrity_pass": not errors, "errors": errors,
            "source_errors": source_errors, "cache_mode_mismatches": cache_mismatches, "api_errors": api_errors,
            "complete_case_regressions": regressions,
            "safety_and_quality_pass": not (errors or source_errors or cache_mismatches or api_errors or regressions),
            "safety_and_quality_pass_scope": "Default retrieval completeness/isolation/cache behavior only; optional field-gate false rejections are separately reported below.",
            "required_fields_diagnostic": {
                "calls": len(field_controls),
                "positive_cases": sum(r["score"]["answerable"] for r in field_controls),
                "positive_incomplete": [r for r in field_controls if r["score"]["complete"] is False],
                "missing_cases": sum(not r["score"]["answerable"] for r in field_controls),
                "missing_returning_context": [r for r in field_controls if r["score"]["returned_context_for_missing"]]},
            "observations_audited": sum(row["observations"] for row in inventory), "inventory": inventory,
            "limitation": "Offline re-scoring uses the registered evaluator, not independent holdout or LLM answer-quality tests."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = audit(args.directory)
    destination = Path(args.output) if args.output else Path(args.directory) / "offline-audit.json"
    if destination.exists():
        raise FileExistsError("Do not overwrite an earlier audit")
    scale.common.atomic_json(destination, result)
    print(json.dumps({key: result[key] for key in ("integrity_pass", "safety_and_quality_pass",
                                                  "checks", "observations_audited")}))
    return 0 if result["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
