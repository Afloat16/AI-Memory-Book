"""Re-score supplementary fixed-target journals against their exact snapshots.

This saved-response/source audit reuses the original frozen v014 scoring rules.
It adds checks for the separately registered pure-foreign matrix and unchanged
target source rows. It is not an independent quality benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import v014_fixed_scope as fixed
from benchmarks import v014_scale as scale
from benchmarks.v014_audit import expected_count, normalized
from benchmarks.v014_workload import cases, digest


def observation_identity(row):
    return tuple(row.get(field) for field in ("case", "mode", "repetition", "warm"))


def expected_observations(bound, spec, rnd):
    """Independent expected matrix; a matching total cannot hide duplicated rows."""
    lookup = {c["id"]: c for c in cases(spec)}
    wanted = Counter({("routing-archive:current", "first-request", None, None): 1})
    if rnd == 0:
        wanted.update((case, "quality", None, None) for case in lookup)
    for name in scale.PERFORMANCE:
        surface = lookup[name]["surface"]
        for repetition in range(bound["repetitions"]):
            wanted[name, "directory" if surface == "directory" else "cold", repetition, None] += 1
            if surface == "recall":
                wanted.update((name, "warm", repetition, warm) for warm in range(bound["warm_calls"]))
        if rnd == 0:
            wanted[name, "work-diagnostic", None, None] += 1
    if rnd == 0:
        for mode in ("foreign-write-before", "after-foreign-write"):
            wanted["routing-archive:current", mode, None, None] += 1
    return wanted


def audit(directory):
    directory = Path(directory).resolve()
    bound = json.loads((directory / "binding.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    plan = fixed.settings()
    checks, errors, source_errors, api_errors, cache_errors = 0, [], [], [], []
    inventory, pairs, initial_targets = [], defaultdict(dict), None

    def check(ok, reason):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(reason)

    check(manifest["status"] == "completed", "run_not_completed")
    check(manifest.get("protocol") == fixed.PROTOCOL, "wrong_supplementary_protocol")
    check({k: bound["supplementary_evaluator"][k] for k in ("protocol", "files")}
          == fixed.protocol_files_identity(), "supplementary_evaluator_bytes_differ")
    check(isinstance(bound["supplementary_evaluator"].get("commit"), str) and
          len(bound["supplementary_evaluator"]["commit"]) == 40, "missing_registered_protocol_commit")
    check(bound["evaluator"] == scale.protocol_identity(), "original_worker_evaluator_differs")
    check(bound["required_fields_controls"] is False, "unregistered_field_gate_controls")
    check(bound["candidate_ranking_scope"] == "project", "wrong_ranking_scope")
    check(bound["snapshot_encoding"] == "gzip", "wrong_storage_encoding")
    profile = plan["profiles"][bound["profile"]]
    for key in ("rounds", "repetitions", "warm_calls"):
        check(bound[key] == profile[key], "measurement_setting_differs:" + key)
    specs = fixed.checkpoints(bound["profile"], plan)
    check(bound["checkpoints"] == specs == [s["spec"] for s in manifest["stages"]], "stage_matrix_differs")
    check(bound["performance_cases"] == list(scale.PERFORMANCE), "performance_cases_differ")
    check(bound["expected_records"] == fixed.expected_records(bound["profile"], plan), "registered_count_differs")
    for identity in (bound["evaluator"], bound["supplementary_evaluator"]):
        for relative, sha in identity["files"].items():
            path = directory / "protocol" / relative
            check(path.is_file() and scale.common.file_sha(path) == sha, "saved_protocol_hash:" + relative)
    for arm in ("baseline", "candidate"):
        for key, expected in plan["runtimes"][arm].items():
            check(bound[arm][key] == expected, "registered_runtime_differs:" + arm + ":" + key)
    for stage in manifest["stages"]:
        spec, snapshot = stage["spec"], stage["snapshot"]
        check(digest(cases(spec)) == bound["cases_sha256"], spec["id"] + ":query_or_gold_changed")
        artifact = Path(snapshot["path"])
        check(artifact.is_file(), spec["id"] + ":snapshot_missing")
        if not artifact.is_file():
            continue
        check(scale.common.file_sha(artifact) == snapshot["sha256"], spec["id"] + ":snapshot_artifact_hash")
        expected_blocks = {(arm, rnd) for arm in ("baseline", "candidate") for rnd in range(bound["rounds"])}
        check({(r["arm"], r["round"]) for r in stage["measurements"]} == expected_blocks,
              spec["id"] + ":measurement_matrix")
        with scale.materialized_snapshot(snapshot, directory) as raw_snapshot:
            targets = fixed.target_fingerprint(raw_snapshot)
            check(targets == snapshot["fixed_target_fingerprint"], spec["id"] + ":saved_target_fingerprint")
            try:
                fixed.verify_target_scope(targets, initial_targets)
            except ValueError as exc:
                check(False, spec["id"] + ":target_invariance:" + str(exc))
            else:
                check(True, spec["id"] + ":target_invariance")
            if initial_targets is None:
                initial_targets = targets
            with closing(sqlite3.connect(f"file:{raw_snapshot}?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                book = SimpleNamespace(db=db)
                check(db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == spec["total_pages"],
                      spec["id"] + ":actual_page_count")
                lookup = {c["id"]: c for c in cases(spec)}
                for block in stage["measurements"]:
                    folder = directory / block["output"]
                    result = json.loads((folder / "result.json").read_text())
                    arm, rnd = block["arm"], block["round"]
                    prefix = f"{spec['id']}:{arm}:{rnd}"
                    check(result["status"] == "completed", prefix + ":worker_incomplete")
                    check(result["runtime"] == bound[arm], prefix + ":runtime_binding")
                    check(result["spec"] == spec, prefix + ":worker_spec")
                    for field in ("logical_sources_sha256", "page_ids", "source_tables_sha256"):
                        check(result["fingerprint"][field] == snapshot["fingerprint"][field], prefix + ":source_fingerprint:" + field)
                    rows = [json.loads(line) for line in (folder / "observations.jsonl").read_text().splitlines()]
                    with gzip.open(folder / "responses.jsonl.gz", "rt", encoding="utf-8") as stream:
                        packets = [json.loads(line) for line in stream]
                    check(len(rows) == len(packets) == result["observations"] == expected_count(bound, spec, arm, rnd),
                          prefix + ":sample_count")
                    check(Counter(observation_identity(row) for row in rows) == expected_observations(bound, spec, rnd),
                          prefix + ":complete_observation_identity_multiset")
                    check(Counter(row["case"] for row in rows if row["mode"] == "quality") ==
                          (Counter({name: 1 for name in lookup}) if rnd == 0 else Counter()),
                          prefix + ":complete_quality_case_multiset")
                    for index, (row, packet) in enumerate(zip(rows, packets), 1):
                        identifier = prefix + ":" + str(index)
                        check(row["sequence"] == packet["sequence"] == index, identifier + ":sequence")
                        check(row["arm"] == arm and row["round"] == rnd and row["checkpoint"] == spec["id"], identifier + ":assignment")
                        raw = packet["original_response"]
                        check(digest(raw) == row["raw_sha256"], identifier + ":original_response_hash")
                        check({k: v for k, v in row.items() if k not in
                               {"raw_gzip_offset", "raw_gzip_bytes", "raw_sha256"}} == packet["observation"],
                              identifier + ":paired_journal")
                        if row["error"] is not None:
                            api_errors.append({"block": prefix, "sequence": index, "error": row["error"]})
                            continue
                        check(raw is not None, identifier + ":missing_response")
                        if raw is None:
                            continue
                        check(digest(scale.common.stable_response(raw)) == row["stable_response_sha256"], identifier + ":stable_hash")
                        check(digest(scale.date_invariant_response(raw)) == row["date_invariant_response_sha256"], identifier + ":date_invariant_hash")
                        check(row["case"] in lookup, identifier + ":unknown_case")
                        if row["case"] not in lookup:
                            continue
                        case = lookup[row["case"]]
                        check(all(row[key] == case[key] for key in ("category", "cohort", "surface")),
                              identifier + ":case_metadata")
                        check(row["required_fields"] is None, identifier + ":unregistered_field_gate")
                        rescored = scale.score(normalized(raw, case["surface"]), case, spec, book)
                        check(rescored == row["score"], identifier + ":saved_response_source_score")
                        if rescored["source_errors"]:
                            source_errors.append({"block": prefix, "sequence": index, "errors": rescored["source_errors"]})
                        if not row["cache_mode_valid"]:
                            cache_errors.append({"block": prefix, "sequence": index, "mode": row["mode"]})
                        if row["mode"] == "quality":
                            pairs[spec["id"], row["case"]][arm] = rescored
                    inventory.append({"block": prefix, "observations": len(rows),
                        "responses_sha256": scale.common.file_sha(folder / "responses.jsonl.gz"),
                        "observations_sha256": scale.common.file_sha(folder / "observations.jsonl")})
    regressions = [{"checkpoint": key[0], "case": key[1], "baseline": pair["baseline"], "candidate": pair["candidate"]}
        for key, pair in pairs.items() if set(pair) == {"baseline", "candidate"}
        and pair["baseline"]["complete"] is True and pair["candidate"]["complete"] is False]
    observed = sum(row["observations"] for row in inventory)
    check(observed == bound["expected_records"], "overall_record_count")
    check(set(pairs) == {(spec["id"], case["id"]) for spec in specs for case in cases(spec)},
          "complete_stage_quality_case_coverage")
    check(all(set(arms) == {"baseline", "candidate"} for arms in pairs.values()), "paired_quality_arm_coverage")
    return {"protocol": fixed.PROTOCOL, "worker_protocol": scale.PROTOCOL,
        "audit_type": "offline_fixed_target_saved_response_and_source_integrity", "checks": checks,
        "integrity_pass": not errors, "errors": errors, "source_errors": source_errors,
        "api_errors": api_errors, "cache_mode_mismatches": cache_errors,
        "complete_case_regressions": regressions, "observations_audited": observed, "inventory": inventory,
        "safety_and_quality_pass": not (errors or source_errors or api_errors or cache_errors or regressions),
        "safety_and_quality_pass_scope": "Registered fixed-target source invariance, saved-response integrity, completeness and cache behavior only.",
        "fixed_target_fingerprint": initial_targets,
        "registered_protocol_commit": bound["supplementary_evaluator"]["commit"],
        "protocol_identity_scope": "Offline audit verifies all bound protocol bytes and saved copies. The recorded clean Git commit was enforced before and throughout execution; no live Git checkout is needed to re-score saved artifacts.",
        "target_invariance_scope": "All rows and columns recorded in fixed_target_fingerprint.source_tables, plus page rowid placement. Excludes projects.created_at/updated_at, chapters.updated_at, sessions.updated_at as ingestion-wallclock bookkeeping.",
        "limitation": "Reuses frozen v014 authored gold and scoring. Not an independent holdout, general ranking equivalence or downstream LLM task validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--output")
    args = parser.parse_args()
    destination = Path(args.output) if args.output else Path(args.directory) / "offline-audit.json"
    if destination.exists():
        raise FileExistsError("Do not overwrite an earlier audit")
    result = audit(args.directory)
    scale.common.atomic_json(destination, result)
    print(json.dumps({key: result[key] for key in ("integrity_pass", "safety_and_quality_pass", "checks", "observations_audited")}))
    return 0 if result["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
