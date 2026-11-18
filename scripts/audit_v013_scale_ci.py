"""Re-read the frozen scale run's original responses after all timing ends.

This audit performs no retrieval, ingestion or database restoration. It checks
the exact request schedule, gzip members, source coordinates and deterministic
turn-page IDs, then reuses the frozen scorer and statistics definitions. Low
quality scores remain low scores; completed measurement is not acceptance.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import v013_scale as scale
from benchmarks.v013_workload import cases, checkpoints, digest, encoded, source_for, source_turn


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def request_schedule(configuration, revision, round_number):
    selected = {case["id"]: case for case in cases(revision)}
    expected = []
    if round_number == 0:
        expected.extend((case_id, "quality", None, None) for case_id in selected)
    settings = configuration["measurement"]
    for case_id in settings["performance_query_ids"]:
        for repeat in range(settings["repetitions_per_query_per_round"]):
            if selected[case_id]["surface"] == "directory":
                expected.append((case_id, "uncached-directory", repeat, None))
            else:
                expected.append((case_id, "cold-result-cache", repeat, None))
                expected.extend((case_id, "warm-result-cache", repeat, warm)
                                for warm in range(settings["warm_result_cache_calls_per_cold_call"]))
    return selected, expected


def normalized_directory(raw, configuration):
    """Validate the saved navigation chain before reconstructing read evidence."""
    options = configuration["directory"]
    require(raw.get("pending_call") is None, "A successful directory call has an unfinished API request")
    chapters = raw["directory"]["results"]
    require(len(chapters) <= options["chapter_limit"], "Directory chapter limit exceeded")
    expected_sections = [section["id"] for chapter in chapters
                         for section in chapter["sections"][:options["sections_per_chapter"]]]
    require(len(raw["sections"]) == len(expected_sections), "Directory section trace is incomplete")
    reads = iter(raw["reads"])
    hits, blocks, used = [], [], 0
    for expected, section in zip(expected_sections, raw["sections"]):
        require(section["id"] == expected, "Section was not discovered by the directory response")
        require(len(section["pages"]) <= options["pages_per_section"], "Section page limit exceeded")
        for page in section["pages"]:
            separator = 2 if blocks else 0
            remaining = options["total_original_evidence_budget_chars"] - used - separator
            if remaining <= 0:
                continue
            original = next(reads, None)
            require(original is not None and original["id"] == page["id"], "Read was not discovered by its section")
            require(len(original["content"]) <= min(remaining, options["read_limit_chars"]), "Read budget exceeded")
            blocks.append(original["content"])
            used += separator + len(original["content"])
            hits.append({"id": original["id"], "text": original["content"],
                         "source_refs": original["source_refs"], "breadcrumb": original["breadcrumb"]})
    require(next(reads, None) is None, "Undiscovered extra original read")
    return {"context": "\n\n".join(blocks), "results": hits}


def page_id_violations(response, case, spec):
    """Independently reproduce the registered one-page-per-turn source IDs.

    The fixed ID encoding is part of baseline 8044's original-source layout.
    This deliberately does not import either arm's MemoryBook implementation.
    """
    def identity(prefix, *values):
        return prefix + hashlib.sha256(encoded(values)).hexdigest()[:24]
    violations, unverifiable = [], []
    for index, hit in enumerate(response["results"]):
        try:
            refs = hit.get("source_refs", [])
            if not refs:
                # The frozen source scorer already fails this output. Without
                # a source identity we cannot independently reconstruct its ID
                # or infer whether the runner's live DB lookup succeeded.
                unverifiable.append({"hit": index, "reason": "missing_original_references"})
                continue
            identities = {(ref["project"], ref["session_id"], ref["turn_index"]) for ref in refs}
            require(len(identities) == 1, "Turn segmentation returned mixed original turns")
            project, session, turn = next(iter(identities))
            require(project == case["project"], "Returned page crosses the exact project")
            original = source_for(spec, project, session)
            content = source_turn(original["messages"], turn)
            expected = identity("p_", identity("ss_", project, session), str(turn), "0", content)
            require(hit["id"] == expected, "Returned page ID does not own its reconstructed original turn")
        except (ValueError, KeyError, TypeError, IndexError) as error:
            violations.append({"hit": index, "reason": str(error)})
    return violations, unverifiable


def audit_block(directory, spec, arm, round_number, configuration, expected_runtime):
    result = read_json(directory / "result.json")
    require(result["spec"] == spec and result["arm"] == arm and result["round"] == round_number,
            "Worker result changed its checkpoint or arm identity")
    require(result["runtime"] == expected_runtime, "Worker runtime differs from the frozen arm")
    imported = result["imported"]
    root = Path(expected_runtime["repo_root"])
    require(Path(imported["package_file"]).parent == root / "src/memory_book", "Wrong imported package path")
    binary = Path(imported["extension_file"])
    require(imported["backend"] == "native" and binary.parent == root / "src/memory_book"
            and expected_runtime["native_extension_files"].get(binary.name) == imported["extension_sha256"],
            "Wrong actual native extension path/backend/hash")
    selected, schedule = request_schedule(configuration, spec["revision"], round_number)
    observations, interrupted_lines = [], []
    lines = (directory / "observations.jsonl").read_bytes().splitlines()
    for index, line in enumerate(lines):
        try:
            observations.append(json.loads(line))
        except (ValueError, UnicodeDecodeError):
            require(result["status"] != "completed" and index == len(lines) - 1,
                    "Malformed compact observation inside a completed prefix")
            interrupted_lines.append({"line": index + 1, "bytes": len(line),
                                      "sha256": hashlib.sha256(line).hexdigest()})
    require(len(observations) <= len(schedule), "Extra measurements outside the registered schedule")
    quality, errors, previous_end, source_violations, unverifiable_ids = [], 0, 0, [], []
    locator_fields = {"raw_gzip_offset", "raw_gzip_bytes", "raw_sha256"}
    with (directory / "responses.jsonl.gz").open("rb") as raw_file:
        for sequence, (row, expected) in enumerate(zip(observations, schedule), 1):
            require((row["case"], row["mode"], row.get("repetition"), row.get("warm_call")) == expected,
                    "Missing, duplicate or reordered request cell")
            require(row["sequence"] == sequence and row["arm"] == arm and row["round"] == round_number,
                    "Observation sequence/arm differs")
            case = selected[row["case"]]
            require(row["surface"] == case["surface"] and row["lifecycle"] == case["lifecycle"], "Case labels differ")
            require(row["raw_gzip_offset"] == previous_end and row["raw_gzip_bytes"] > 0, "Raw member boundaries differ")
            member = raw_file.read(row["raw_gzip_bytes"])
            require(len(member) == row["raw_gzip_bytes"], "Truncated original gzip member")
            packet = json.loads(gzip.decompress(member))
            previous_end += len(member)
            require(packet["sequence"] == sequence and packet["observation"] ==
                    {key: value for key, value in row.items() if key not in locator_fields},
                    "Original packet and compact observation differ")
            raw = packet["original_response"]
            require(digest(raw) == row["raw_sha256"], "Original response hash differs")
            require(row["stable_response_sha256"] == (digest(scale.stable_response(raw)) if raw is not None else None),
                    "Stable response hash differs")
            if row["error"] is None:
                require(all(type(row[field]) is int and row[field] >= 0 for field in ("wall_ns", "process_cpu_ns")),
                        "Completed response lacks recorded nonnegative durations")
                normalized = normalized_directory(raw, configuration) if case["surface"] == "directory" else raw
                if case["surface"] == "recall":
                    require(raw["query"] == case["query"] and raw["budget_chars"] == configuration["retrieval"]["budget_chars"]
                            and len(raw["results"]) <= configuration["retrieval"]["limit"], "Recall request/budget differs")
                violations, unverifiable = page_id_violations(normalized, case, spec)
                rescored = scale.score(normalized, case, spec, configuration["retrieval"]["budget_chars"])
                # A recorded API/source failure is a quality outcome, not a
                # missing measurement. Reproduce the runner's separate page-ID
                # check without re-opening a large database snapshot.
                page_errors = [error for error in row["score"]["source_errors"] if error in
                               {"returned_page_id_missing_or_foreign", "returned_page_id_does_not_own_source_reference"}]
                require(len(violations) <= len(page_errors) <= len(violations) + len(unverifiable),
                        "Recorded page-identity failures differ from original source IDs")
                if page_errors:
                    rescored["source_errors"].extend(page_errors)
                    rescored["covered_spans"] = 0
                    if rescored["answerable"]:
                        rescored["complete"] = False
                    if rescored["current_source_first"] is not None:
                        rescored["current_source_first"] = False
                if violations:
                    source_violations.append({"sequence": sequence, "case": row["case"], "violations": violations})
                if unverifiable:
                    unverifiable_ids.append({"sequence": sequence, "case": row["case"], "unverifiable": unverifiable})
                require(rescored == row["score"], "Saved score differs from reconstructed original-response score")
                cache_valid = (raw.get("cache_hit") is (row["mode"] == "warm-result-cache")) \
                    if case["surface"] == "recall" and row["mode"] != "quality" else True
                require(row["cache_mode_valid"] == cache_valid, "Cache-mode diagnostic differs from original response")
            else:
                errors += 1
                require(row["score"] is None, "Failed API call unexpectedly has a complete-response score")
            if row["mode"] == "quality":
                quality.append({key: row[key] for key in ("case", "surface", "error", "score", "stable_response_sha256")})
        tail = raw_file.read()
        trailing = len(tail)
    complete = result["status"] == "completed"
    if complete:
        require(len(observations) == len(schedule) and not trailing, "Completed worker has an incomplete raw matrix")
        require(result["observations"] == len(observations), "Worker observation count differs")
        require(result["summary"] == scale.summarize_observations(directory / "observations.jsonl"),
                "Worker timing/quality groups differ from audited observations")
    return {"directory": str(directory), "status": result["status"], "observations": len(observations),
            "call_errors": errors, "trailing_raw_bytes": trailing, "quality": scale.quality_totals(quality),
            "unindexed_raw_tail_sha256": hashlib.sha256(tail).hexdigest() if tail else None,
            "unindexed_tail_boundary": "Retained bytes without a complete compact observation are not counted as completed audited calls.",
            "interrupted_compact_lines": interrupted_lines,
            "original_page_identity_violations": source_violations,
            "unverifiable_page_ids_without_source_refs": unverifiable_ids,
            "responses_sha256": scale.file_sha(directory / "responses.jsonl.gz"),
            "observations_sha256": scale.file_sha(directory / "observations.jsonl")}


def audit(args):
    configuration = scale.plan()
    require(configuration["source"]["segmentation"] == "turn", "Unsupported source-page identity protocol")
    frozen = scale.frozen_identity(args.protocol_commit)
    manifest = read_json(args.run_root / "manifest.json")
    require(manifest["binding"]["protocol"] == frozen and manifest["binding"]["profile"] == "main"
            and manifest["binding"]["backend"] == "native", "Manifest protocol/profile/backend differs")
    local_runtimes = {"baseline": scale.runtime_identity(args.baseline_root, configuration["baseline_commit"]),
                      "candidate": scale.runtime_identity(args.candidate_root, args.candidate_commit)}
    runtimes = manifest["binding"]["runtimes"]
    if args.offline:
        for arm in runtimes:
            require(all(runtimes[arm][field] == local_runtimes[arm][field]
                        for field in ("commit", "tracked_runtime_sha256", "files")),
                    "Offline checkout does not reproduce the recorded runtime source bytes")
    else:
        require(runtimes == local_runtimes, "Runtime source/binary changed after measurement")
    original_root = None
    for stage in manifest["stages"].values():
        if stage.get("build"):
            original_root = Path(stage["build"]["result_path"]).parents[2]
            break
    require(original_root is not None and original_root.is_absolute(), "No original run-root can be authenticated")

    def relocate(value):
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if key in {"result_path", "stdout_path", "stderr_path"} and isinstance(child, str):
                    relative = Path(child).relative_to(original_root)
                    require(".." not in relative.parts, "Evidence path escapes its original run-root")
                    result[key] = str(args.run_root / relative)
                else:
                    result[key] = relocate(child)
            return result
        return [relocate(child) for child in value] if isinstance(value, list) else value

    # Only evidence paths are remapped. Runtime roots in historical import
    # records stay original; offline mode makes no new binary/DB-restoration claim.
    relocated = relocate(copy.deepcopy(manifest))
    specs = {spec["id"]: spec for spec in checkpoints("main")}
    require(set(manifest["stages"]) <= specs.keys(), "Unknown checkpoint")
    block_audits, issues, primary_observations, accepted_slots, attached = [], [], 0, set(), set()
    for checkpoint, stage in manifest["stages"].items():
        spec = specs[checkpoint]
        require(stage["spec"] == spec, "Checkpoint changed its frozen generator specification")
        for block in stage.get("blocks", []):
            directory = args.run_root / checkpoint / Path(block["execution"]["result_path"]).parent.name
            attached.add(directory)
            try:
                checked = audit_block(directory, spec, block["arm"], block["round"], configuration, runtimes[block["arm"]])
                checked["included_in_primary_matrix"] = block["execution"]["complete"]
                block_audits.append(checked)
                if block["execution"]["complete"]:
                    slot = checkpoint, block["round"], block["arm"]
                    require(slot not in accepted_slots and checked["status"] == "completed", "Duplicate/incomplete accepted arm")
                    require(block["execution"]["returncode"] == 0 and not block["execution"]["timed_out"],
                            "Accepted arm has a failed process exit or hard timeout")
                    require(read_json(directory / "result.json") == block["execution"]["result"], "Manifest copied worker result differs")
                    snapshot = stage["snapshot"]
                    require(block["restoration"]["restored_database_sha256"] == snapshot["database_sha256"]
                            and block["restoration"]["restored_database_bytes"] == snapshot["database_bytes"],
                            "Arm restoration identity differs from the baseline-built snapshot")
                    require(block["execution"]["result"]["fingerprint_after"]["source_tables_sha256"] ==
                            stage["build"]["result"]["fingerprint"]["source_tables_sha256"],
                            "Measured arm changed original source tables")
                    accepted_slots.add(slot)
                    primary_observations += checked["observations"]
            except Exception:
                issues.append({"directory": str(directory), "traceback": traceback.format_exc()})
        if stage.get("status") == "completed":
            try:
                require(stage["build"]["complete"] and stage["build"]["result"]["actual_pages"] == spec["total_pages"],
                        "Completed checkpoint has no matching real-ingest page count")
                require(stage["build"]["returncode"] == 0 and not stage["build"]["timed_out"],
                        "Completed builder has a failed process exit or hard timeout")
                builder = args.run_root / checkpoint / Path(stage["build"]["result_path"]).parent.name / "result.json"
                require(read_json(builder) == stage["build"]["result"], "Original builder result differs from manifest copy")
                fingerprint = stage["build"]["result"]["fingerprint"]
                require(read_json(args.run_root / checkpoint / "fingerprint.json") == fingerprint,
                        "Saved source fingerprint differs from the completed builder")
                require(stage["control_checks"] == scale.check_control(spec, fingerprint, manifest["stages"]),
                        "Age/layout/source controls differ from the frozen control rules")
                moved = relocated["stages"][checkpoint]
                require(moved["summary"] == scale.checkpoint_summary(moved), "Checkpoint timing/paired/quality summary differs")
                require(read_json(args.run_root / checkpoint / "summary.json") == stage["summary"], "Saved checkpoint summary differs")
            except Exception:
                issues.append({"checkpoint": checkpoint, "traceback": traceback.format_exc()})
    for observation in sorted(args.run_root.glob("*/*/observations.jsonl")):
        directory = observation.parent
        if directory in attached:
            continue
        match = re.fullmatch(r"round(\d+)-(baseline|candidate)-attempt\d+", directory.name)
        try:
            require(match is not None and directory.parent.name in specs, "Unrecognized unattached raw attempt")
            arm = match[2]
            checked = audit_block(directory, specs[directory.parent.name], arm, int(match[1]), configuration, runtimes[arm])
            checked["included_in_primary_matrix"] = False
            block_audits.append(checked)
        except Exception:
            issues.append({"directory": str(directory), "traceback": traceback.format_exc()})
    wanted_slots = {(checkpoint, round_number, arm) for checkpoint in specs
                    for round_number, order in enumerate(configuration["measurement"]["arm_order_by_round"]) for arm in order}
    counts = configuration["measurement"]["expected_primary_counts"]
    complete = (manifest["status"] == "measurements_completed" and accepted_slots == wanted_slots
                and primary_observations == counts["api_measurements_total"]
                and all(stage.get("status") == "completed" for stage in manifest["stages"].values())
                and not manifest.get("unexecuted_or_incomplete_cells"))
    partial_tails = [block["directory"] for block in block_audits
                     if block["trailing_raw_bytes"] or block["interrupted_compact_lines"]]
    return {"audit_status": ("integrity_errors" if issues else "verified_complete_records_with_retained_partial_tails"
                              if partial_tails else "verified_saved_records"),
            "measurement_complete": complete, "registered_api_measurements": counts["api_measurements_total"],
            "audited_primary_api_measurements": primary_observations, "audited_completed_arm_blocks": len(accepted_slots),
            "manifest_status": manifest["status"], "issues": issues, "blocks": block_audits,
            "partial_evidence_tails": partial_tails,
            "protocol": frozen, "auditor_sha256": scale.file_sha(__file__),
            "runtime_reverification": ("offline tracked-source bytes verified; original binary identity retained from worker records"
                                       if args.offline else "original source roots and actual extension bytes reverified in place"),
            "database_restoration": "Recorded restoration hashes and source fingerprints cross-checked; this auditor does not restore or reopen database snapshots.",
            "quality_acceptance": "Not inferred from process exit or completed measurement. Original low scores, missing evidence and changed evidence remain in each block's quality counts and checkpoint per-case records.",
            "comparison_boundary": "stable_response changes may include added metadata. Assess evidence_projection_sha256, required_ranks, source_errors, complete and current_source_first separately."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="Reverify tracked source bytes and remap saved evidence paths; do not claim original binary restoration")
    args = parser.parse_args()
    args.run_root = args.run_root.resolve()
    try:
        result = audit(args)
    except Exception:
        result = {"audit_status": "failed", "measurement_complete": False, "traceback": traceback.format_exc()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scale.atomic_json(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key not in {"blocks", "protocol"}}, ensure_ascii=False))
    return 0 if result["audit_status"] == "verified_saved_records" and result["measurement_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
