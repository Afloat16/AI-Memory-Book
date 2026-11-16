"""Read-only, separate recomputation of the final scope replay artifacts.

This does not import or execute the evaluator or product runtime. It checks the
recorded calls against their inputs, recomputes every reported response digest
and aggregate, and compares complete canonical values with the original run.
It updates only the audit section of the new final execution receipt.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]
FINAL = Path(__file__).resolve().parent
BASELINE = FINAL.parent / "baseline"
CANDIDATE = FINAL / "scope-candidate"
SOURCE_COMMIT = "df5186c628ab68cd5cedda65ca244c49b218adb7"
RUNTIME_DIGEST = "a7940db8e429e9c8ecb4aceb3fab83227da75cc2cac96b1eac5fedf286c87027"
OMIT = {"latency_ms", "cache_hit", "updated_at"}
checks = Counter()


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    checks[name] += 1


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode())


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value):
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key not in OMIT:
            result[key] = normalize(item)
    if isinstance(result.get("project"), dict):
        result["project"].pop("created_at", None)
    if all(key in result for key in ("chapters", "sessions", "pages", "name", "id")):
        result.pop("created_at", None)
    return result


def audit_recorded_run(directory):
    report, dataset = load(directory / "report.json"), load(directory / "dataset.json")
    raw = (directory / "raw.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    check(report["raw_sha256"] == sha(raw), "raw_file_hash")
    check(report["dataset_sha256"] == digest(dataset), "dataset_digest")
    check(report["runtime"]["sha256"] == digest(report["runtime"]["files"]), "runtime_map_digest")
    check(report["calls"] == len(rows), "raw_call_count")
    check(len({row["case_id"] for row in rows}) == len(rows), "unique_case_ids")
    outcomes = dict(Counter(row["outcome"] for row in rows))
    summary = {kind: dict(Counter(row["outcome"] for row in rows if row["category"] == kind))
               for kind in sorted({row["category"] for row in rows})}
    check(report["outcomes"] == outcomes, "all_outcomes_recomputed")
    check(report["summary"] == summary, "all_category_summaries_recomputed")
    check(report["failed_case_ids"] == [row["case_id"] for row in rows if row["outcome"] == "failed"],
          "failed_case_ids_recomputed")
    compatibility = {}
    for row in rows:
        error, response = row["error"], row["response"]
        if response is not None:
            check(row["canonical_response_sha256"] == digest(normalize(response)), "every_response_digest")
        if not row["capability_supported"] and error and error["type"] == "TypeError":
            check(row["outcome"] == "unsupported", "unsupported_is_not_a_rejection_pass")
        elif row["expected"] in ("KeyError", "ValueError"):
            check(error is not None and error["type"] == row["expected"] and response is None
                  and row["outcome"] == "passed" and not row["validation_errors"], "expected_errors_exact")
        else:
            check(error is None and response is not None and row["outcome"] == "passed"
                  and not row["validation_errors"], "recorded_success_shape")
        if row["compatibility_case"]:
            compatibility[row["case_id"]] = {
                "response_sha256": digest(normalize(response)) if response is not None else None,
                "error": error, "outcome": row["outcome"]}
    check(report["compatibility_cases"] == compatibility, "all_compatibility_summaries_recomputed")
    return report, dataset, rows


baseline, old_data, old_rows = audit_recorded_run(BASELINE)
candidate, data, rows = audit_recorded_run(CANDIDATE)
check(data == old_data, "identical_input_objects")
for key in ("version", "dataset_sha256", "evaluator_sha256", "canonicalization", "identities"):
    check(baseline[key] == candidate[key], "matched_run_metadata")
check(candidate["runtime_unchanged"] and candidate["evaluator_unchanged"], "runtime_stayed_frozen")
check(candidate["runtime"]["sha256"] == RUNTIME_DIGEST, "expected_final_runtime")
check(candidate["evaluator_sha256"] == sha((ROOT / "benchmarks/project_scope_eval.py").read_bytes()),
      "current_evaluator_matches_run")
live_files = {path.relative_to(ROOT / "src/memory_book").as_posix(): sha(path.read_bytes())
              for path in sorted((ROOT / "src/memory_book").rglob("*.py"))}
check(candidate["runtime"]["files"] == live_files, "current_runtime_matches_run")
for name, expected in live_files.items():
    blob = subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:src/memory_book/{name}"], cwd=ROOT)
    check(sha(blob) == expected, "runtime_file_matches_frozen_commit")

old = {row["case_id"]: row for row in old_rows if row["compatibility_case"]}
new = {row["case_id"]: row for row in rows if row["compatibility_case"]}
check(old.keys() == new.keys(), "same_compatibility_case_ids")
differences = []
for case_id in sorted(old):
    left, right = old[case_id], new[case_id]
    check(left["operation"] == right["operation"] and left["arguments"] == right["arguments"]
          and left["expected"] == right["expected"], "same_compatibility_call")
    if (normalize(left["response"]), left["error"], left["outcome"]) != (
            normalize(right["response"]), right["error"], right["outcome"]):
        differences.append(case_id)
comparison = load(CANDIDATE / "comparison.json")
check(comparison["compared_cases"] == len(old) and comparison["equal_cases"] == len(old) - len(differences)
      and comparison["differences"] == differences == [] and comparison["status"] == "matched",
      "full_canonical_objects_and_exact_errors_match")
for prefix, report in (("baseline", baseline), ("candidate", candidate)):
    check(comparison[f"{prefix}_runtime_sha256"] == report["runtime"]["sha256"]
          and comparison[f"{prefix}_outcomes"] == report["outcomes"], "comparison_metadata_recomputed")

projects = data["projects"]
sources = {(item["project"], item["session_id"], 0): "\n\n".join(
    message["role"].upper() + ": " + message["content"] for message in item["messages"])
    for item in data["sessions"]}
full_coverage = {identity: set() for identity in sources}
section_walk, page_walk = defaultdict(list), defaultdict(list)
identity_owner = {}
for project, ids in candidate["identities"].items():
    for identity in [ids["chapter"], *ids["sections"], *ids["pages"]]:
        check(identity not in identity_owner, "ids_do_not_overlap_projects")
        identity_owner[identity] = project
for row in rows:
    response, error = row["response"], row["error"]
    kw, args = row["arguments"]["keywords"], row["arguments"]["positional"]
    scope = kw.get("project")
    category = row["category"]
    if category == "foreign_id_assertion":
        check(identity_owner[args[0]] != scope and scope in projects and error["type"] == "KeyError",
              "foreign_id_rejected")
    elif category == "unknown_project_assertion":
        check(scope not in projects and error["type"] == "KeyError", "unknown_project_rejected")
    elif category == "invalid_project_assertion":
        check((not isinstance(scope, str) or not scope.strip()) and error["type"] == "ValueError",
              "invalid_project_rejected")
    if error is not None:
        continue
    if row["operation"] == "ingest":
        replacement = args[0]
        check(replacement == data["replacement"] and response["revision"] == 13, "replacement_recorded")
        sources[(replacement["project"], replacement["session_id"], 0)] = "\n\n".join(
            item["role"].upper() + ": " + item["content"] for item in replacement["messages"])
    if row["operation"] == "delete_project":
        check(response is True and args == [projects[1]], "project_deletion_recorded")
    if row["operation"] == "chapter":
        check(response["project_id"] == (scope or identity_owner[args[0]]), "chapter_scope_matches")
        if category == "paginated_directory":
            section_walk[scope].extend(section["id"] for section in response["sections"])
    if row["operation"] == "section" and category == "paginated_directory":
        page_walk[scope].extend(page["id"] for page in response["pages"])
    if row["operation"] == "read":
        project = scope or identity_owner[args[0]]
        content, offset = response["content"], response["offset"]
        check(response["breadcrumb"][0]["id"] == project, "read_breadcrumb_scope")
        check(offset == kw.get("offset", 0), "read_offset")
        covered = set()
        for ref in response["source_refs"]:
            identity = (ref["project"], ref["session_id"], ref["turn_index"])
            source = sources[identity]
            a, b, lo, hi = ref["start"], ref["end"], ref["turn_start"], ref["turn_end"]
            check(identity[0] == project and 0 <= lo < hi <= len(source)
                  and offset <= a < b <= offset + len(content)
                  and source[lo:hi] == content[a-offset:b-offset], "read_source_coordinates_and_text")
            covered.update(range(a-offset, b-offset))
            if category == "complete_source_read":
                full_coverage[identity].update(range(lo, hi))
        check(all(index in covered or char.isspace() for index, char in enumerate(content)), "read_has_no_unsourced_text")
        if category == "complete_source_read":
            check(offset == 0 and response["next_offset"] is None and len(content) == response["total_chars"],
                  "full_page_is_complete")
        if "limit" in kw:
            check(len(content) == min(kw["limit"], response["total_chars"] - offset), "read_slice_length")
    if row["operation"] == "recall":
        context, hits = response["context"], response["results"]
        check(response["context_chars"] == len(context) <= 2400, "recall_character_budget")
        if category == "conflicting_recall_filter" or row["case_id"] == "deleted-project-recall":
            check(hits == [] and context == "", "conflicting_or_deleted_scope_empty")
        else:
            check(bool(hits), "recall_has_evidence")
        if category in ("explicit_project_recall", "interleaved_hot_cache", "source_replacement", "project_deletion"):
            check(response["cache_hit"] is (category == "interleaved_hot_cache"), "cold_hot_invalidation_state")
            number = projects.index(scope)
            value = 111 if number == 0 and category in ("source_replacement", "project_deletion") else 11 + number
            if row["case_id"] != "deleted-project-recall":
                check(f"retry_limit={value}." in context, "correct_project_decision_after_mutations")
        seen_projects = set()
        for hit in hits:
            text = hit["text"]
            check(text in context, "recall_snippet_in_context")
            covered = set()
            for ref in hit["source_refs"]:
                identity = (ref["project"], ref["session_id"], ref["turn_index"])
                lo, hi = ref["turn_start"], ref["turn_end"]
                fragment = sources[identity][lo:hi]
                start = text.find(fragment)
                check(0 <= lo < hi <= len(sources[identity]) and start >= 0
                      and hi-lo == ref["end"]-ref["start"], "recall_source_coordinates_and_text")
                check(scope is None or identity[0] == scope, "recall_project_scope")
                covered.update(range(start, start+len(fragment)))
                seen_projects.add(identity[0])
            check(all(index in covered or char.isspace() or char == "…" for index, char in enumerate(text)),
                  "recall_has_no_unsourced_text")
        if category == "unbound_global_control":
            check(seen_projects == set(projects), "unbound_global_control_all_projects")

for project in projects:
    check(section_walk[project] == candidate["identities"][project]["sections"], "directory_all_sections_in_order")
    check(page_walk[project] == candidate["identities"][project]["pages"], "directory_all_pages_in_order")
for item in data["sessions"]:
    identity = (item["project"], item["session_id"], 0)
    original = "\n\n".join(message["role"].upper() + ": " + message["content"] for message in item["messages"])
    check(all(index in full_coverage[identity] or char.isspace() for index, char in enumerate(original)),
          "directory_covers_original_nonwhitespace_source")

receipt_path = FINAL / "scope-execution.json"
receipt = load(receipt_path)
check(receipt["exit_code"] == 0 and receipt["source_before"] == receipt["source_after"], "execution_source_frozen")
check(receipt["source_before"]["commit"] == SOURCE_COMMIT, "execution_source_commit")
stdout = load(FINAL / "scope-execution.log")
check(stdout["calls"] == candidate["calls"] and stdout["outcomes"] == candidate["outcomes"]
      and stdout["runtime"] == candidate["runtime"]["sha256"] and stdout["status"] == candidate["status"],
      "execution_stdout_matches_artifacts")
for name, metadata in receipt["files"].items():
    blob = (ROOT / name).read_bytes()
    check(sha(blob) == metadata["sha256"] and len(blob) == metadata["bytes"], "execution_file_hashes_stable")
receipt["status"] = "completed_and_independently_recomputed"
receipt["audit"] = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "method": "Separate standard-library artifact audit; no evaluator or runtime imports; complete canonical values and exact errors compared directly.",
    "audit_script_sha256": sha(Path(__file__).read_bytes()), "checks": dict(sorted(checks.items())),
    "baseline": {"calls": baseline["calls"], "outcomes": baseline["outcomes"], "summary": baseline["summary"]},
    "candidate": {"calls": candidate["calls"], "outcomes": candidate["outcomes"], "summary": candidate["summary"]},
    "compatibility": {"compared_cases": len(old), "equal_cases": len(old)-len(differences), "differences": differences},
    "baseline_file_hashes": {str(path.relative_to(ROOT)): sha(path.read_bytes())
                             for path in sorted(BASELINE.glob("*.json*"))},
    "limitations": ["Authored development/regression contracts; not holdout, product accuracy, speed, or an access-control audit.",
                    "Core Python replay; MCP/CLI/HTTP/browser execution is covered by separate artifacts.",
                    "Canonicalization omits latency_ms, cache_hit, updated_at and project-directory creation timestamps; cache states are checked separately."]}
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": receipt["status"], "checks": sum(checks.values()),
                  "candidate_calls": len(rows), "compatibility_equal": len(old)-len(differences)}, indent=2))
