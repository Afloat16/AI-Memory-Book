"""Inspect the original C7 MCP development failure without any new measurement.

The original aggregate compared whole source snapshots across independently
created databases. Those snapshots include host timestamps. This supplement
retains that failure and every original byte, verifies each archive's complete
before/after snapshot, and compares the saved logical projections across them.
It does not establish equality of fields omitted from those projections.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round5_c7_mcp_development_pair as original
from scripts import round5_c7_performance as c7

RESULT_COMMIT = "dff0a89b1298b9a34e4e0bfe94d1ace4e0c30820"
EVALUATOR_COMMIT = "64ba02f77f36476f4073d52dfffccbe922a7e715"
RESULT_DIRECTORY = "benchmarks/reports/round5-c7-development-43562541460-1"
REPORT_SHA256 = "cf29fa50adbc8fbac6d0940c539b8fe41efc8eef4f96f08869fd53bf7026f92d"
HELPER_SHA256 = "f5134503531afad08bbe251acf36f503e45bd474e1937f7b7e46592b86e94870"
ORIGINAL_ERROR = {"type": "ValueError", "message": "Cross-source archive/ingestion differs"}
ARCHIVE_FIELDS = {"source_snapshot_sha256", "indexed_content", "revision", "cache_entries"}
INDEX_TABLES = {"pages", "sections", "turns", "chapters", "sessions", "pages_fts", "pages_stem_fts"}
INGESTION_FIELDS = ("fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assert_archive_projections(workers):
    """Keep full per-archive equality and exact cross-archive projected equality."""
    require(bool(workers), "No original archives")
    canonical, snapshots = None, []
    for worker in workers:
        before, after = worker["archive_before"], worker["archive_after"]
        require(before == after, "Complete within-worker source snapshot changed")
        require(set(before) == ARCHIVE_FIELDS, "Unexpected archive projection fields")
        snapshot = before["source_snapshot_sha256"]
        require(isinstance(snapshot, str) and re.fullmatch(r"[0-9a-f]{64}", snapshot) is not None,
                "Invalid original source snapshot digest")
        require(set(before["indexed_content"]) == INDEX_TABLES, "Missing logical index/source table")
        for table, value in before["indexed_content"].items():
            require(set(value) == {"rows", "sha256"} and type(value["rows"]) is int
                    and value["rows"] >= 0 and isinstance(value["sha256"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
                    "Invalid logical table projection: " + table)
        require(type(before["revision"]) is int and before["revision"] > 0
                and type(before["cache_entries"]) is int and before["cache_entries"] == 0,
                "Invalid source revision or nonempty query cache")
        projected = {key: before[key] for key in ("indexed_content", "revision", "cache_entries")}
        for key in INGESTION_FIELDS:
            require(isinstance(worker[key], str) and re.fullmatch(r"[0-9a-f]{64}", worker[key]) is not None,
                    "Invalid ingestion digest")
            projected[key] = worker[key]
        require(canonical is None or projected == canonical, "Cross-archive logical source/index/ingestion differs")
        canonical = projected
        snapshots.append({"worker": worker["key"], "before": snapshot,
                          "after": after["source_snapshot_sha256"], "within_worker_unchanged": True})
    return {"cross_archive_projection": canonical, "original_complete_snapshots": snapshots,
            "distinct_cross_archive_snapshot_hashes": len({row["before"] for row in snapshots})}


def paired_outputs(workers, query_ids):
    """Inspect every non-timing field, including complete payload/envelope hashes."""
    require(len(query_ids) == len(set(query_ids)) and bool(query_ids), "Invalid original query axis")
    pairs, canonical, timing = {}, {}, {}
    for worker in workers:
        rows = worker["configurations"][0]["rows"]
        require(len(rows) == len(query_ids) and {row["query_id"] for row in rows} == set(query_ids),
                "Missing, duplicate or extra query observations")
        key = (worker["round"], worker["label"])
        require(key not in timing, "Duplicate source/round worker")
        timing[key] = [row["wall_ms"] for row in rows]
        for row in rows:
            stable = original.frozen.stable_row(row)
            pair = pairs.setdefault((worker["round"], row["query_id"]), {})
            require(worker["label"] not in pair, "Duplicate source pair member")
            pair[worker["label"]] = stable
            identity = row["query_id"]
            require(identity not in canonical or canonical[identity] == stable,
                    "Complete output/count/metadata differs across source or round")
            canonical.setdefault(identity, stable)
    require(set(timing) == {(r, label) for r in (0, 1) for label in ("baseline", "candidate")}
            and len(pairs) == 2 * len(query_ids) and len(canonical) == len(query_ids)
            and all(set(pair) == {"baseline", "candidate"}
                    and pair["baseline"] == pair["candidate"] for pair in pairs.values()),
            "Incomplete or unequal original source pairs")
    return pairs, canonical, timing


def statistics(values):
    require(bool(values) and all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values),
            "Invalid original timing values")
    ordered = sorted(values)
    def quantile(p):
        position = (len(ordered) - 1) * p
        lo, hi = math.floor(position), math.ceil(position)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)
    return {"calls": len(values), "mean_ms": math.fsum(values) / len(values),
            "p50_ms": quantile(.5), "p95_ms": quantile(.95)}


def comparison(values, repetition):
    result = {"round": repetition, **{label: statistics(values[label]) for label in ("baseline", "candidate")}}
    result["change_percent"] = {metric: 100 * (result["candidate"][metric] / result["baseline"][metric] - 1)
                                for metric in ("mean_ms", "p50_ms", "p95_ms")}
    return result


def nested(value, path):
    for name in path.split("."):
        value = value[name]
    return value


def resource_comparisons(workers):
    fields = ("mcp_startup_to_initialize_ms", "mcp_server_memory_after_calls.rss_bytes",
              "mcp_server_memory_after_calls.hwm_bytes", "storage_after_mcp_live.logical_db_bytes",
              "storage_after_mcp_live.files_bytes.db", "storage_after_mcp_live.files_bytes.shm",
              "storage_after_mcp_live.files_bytes.wal")
    results = []
    for field in fields:
        values = {label: [nested(w["mcp_sessions"][original.CONFIG["id"]], field)
                          for w in workers if w["label"] == label] for label in ("baseline", "candidate")}
        require(all(len(v) == 2 and all(type(x) in (int, float) and math.isfinite(x) and x > 0
                    for x in v) for v in values.values()), "Missing original resource values")
        means = {label: math.fsum(values[label]) / len(values[label]) for label in values}
        results.append({"metric": field, "values": values, "means": means,
                        "mean_change_percent": 100 * (means["candidate"] / means["baseline"] - 1)})
    return results


def audit(report_path, state):
    """Read committed original files only; no retrieval, SDK or timer is run."""
    original_paths = {}
    def read_committed(path):
        path = path.resolve()
        relative = path.relative_to(ROOT).as_posix()
        require(relative.startswith(RESULT_DIRECTORY + "/"), "Input is outside the original result directory")
        raw = path.read_bytes()
        expected = subprocess.check_output(["git", "rev-parse", RESULT_COMMIT + ":" + relative],
                                           cwd=ROOT, text=True).strip()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == expected, "Original committed result bytes changed: " + relative)
        original_paths[relative] = {"bytes": len(raw), "sha256": sha(raw), "git_blob_sha1": blob}
        return raw
    raw = read_committed(report_path)
    require(sha(raw) == REPORT_SHA256, "Original failed report identity changed")
    require(sha((ROOT / original.SCRIPT_PATH).read_bytes()) == HELPER_SHA256,
            "The frozen original measurement/audit helper was modified")
    report = json.loads(gzip.decompress(raw))
    require(report["status"] == "failed" and report["error"] == ORIGINAL_ERROR
            and report.get("verification") is None, "Do not relabel the original aggregate failure")
    run = report["run"]
    plan, _, registration, ids = original.registered_inputs()
    require(run["evaluator_commit"] == EVALUATOR_COMMIT and run["evaluator"] == original.VERSION
            and run["plan"] == plan and run["plan_sha256"] == original.PLAN_SHA256
            and run["registration"] == registration and run["query_ids_original_order"] == ids
            and run["helper_sha256"] == HELPER_SHA256 and run["evaluator_files"] == c7.file_hashes()
            and run["sources"] == {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}
            and run["host"]["packages"] == original.frozen.PACKAGES,
            "Original source/evaluator/registration/host identity differs")
    require(json.loads(read_committed(state / "run.json")) == run, "Original standalone run differs")
    require(run["schedule"] == list(original.SCHEDULE)
            and [w["key"] for w in report["workers"]] == [item["key"] for item in original.SCHEDULE],
            "Missing, duplicate or reordered original workers")
    count, sessions = 0, {}
    for worker, item in zip(report["workers"], original.SCHEDULE, strict=True):
        prefix = state / "workers" / worker["key"]
        marker = json.loads(read_committed(prefix.with_name(prefix.name + ".started.json")))
        require(marker == {"worker": item, "run_identity_sha256": original.frozen.digest(run)},
                "Original worker intent differs")
        saved = json.loads(gzip.decompress(read_committed(prefix.with_name(prefix.name + ".json.gz"))))
        require(saved == worker, "Original worker file differs from aggregate")
        ledger = gzip.decompress(read_committed(prefix.with_name(prefix.name + ".attempts.jsonl.gz")))
        count += original.validate_saved_worker(worker, run, ledger)
        session = worker["mcp_sessions"][original.CONFIG["id"]]
        for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            require(field not in sessions or sessions[field] == session[field], "SDK initialization differs")
            sessions.setdefault(field, session[field])
    try:
        original.inspect_saved(report, state)
    except ValueError as error:
        require(str(error) == ORIGINAL_ERROR["message"], "Original failed check now fails for another reason")
    else:
        raise ValueError("The original failed aggregate unexpectedly passed")
    archives = assert_archive_projections(report["workers"])
    pairs, canonical, timing = paired_outputs(report["workers"], ids)
    require(count == 4060 and len(pairs) == 2030 and len(canonical) == 1015,
            "Original registered call count differs")
    per_round = [comparison({label: timing[(r, label)] for label in ("baseline", "candidate")}, r)
                 for r in (0, 1)]
    pooled = comparison({label: [v for r in (0, 1) for v in timing[(r, label)]]
                         for label in ("baseline", "candidate")}, None)
    resources = resource_comparisons(report["workers"])
    return {"schema_version": 1, "supplemental_audit_passed": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Saved-data-only supplemental development diagnosis; original aggregate remains failed.",
        "original_result_commit": RESULT_COMMIT, "original_report_status": report["status"],
        "original_report_error": report["error"], "original_error_reproduced": True,
        "original_files": original_paths, "audit_script_sha256": sha(Path(__file__).read_bytes()),
        "frozen_measurement_helper_sha256": HELPER_SHA256,
        "sources": run["sources"], "evaluator_commit": run["evaluator_commit"],
        "timed_calls_in_original_records": count, "ledger_events_verified": 2 * count,
        "complete_output_pairs": len(pairs), "cross_round_stable_queries": len(canonical),
        "all_saved_complete_output_fields_equal": True, "all_original_worker_checks_passed": True,
        "all_original_call_invariants_passed": True, "normal_cache_costs_preserved": True,
        **archives, "sdk_initialization": sessions, "pooled": pooled, "per_round": per_round,
        "all_adverse_latency_metrics": [{"round": row["round"], "metric": key, "change_percent": value}
            for row in [pooled, *per_round] for key, value in row["change_percent"].items() if value > 0],
        "first_query_rows_retained": [{"worker": w["key"], "row": w["configurations"][0]["rows"][0]}
                                      for w in report["workers"]],
        "original_session_resources": [{"worker": w["key"], **w["mcp_sessions"][original.CONFIG["id"]]}
                                       for w in report["workers"]],
        "resource_comparisons": resources,
        "all_adverse_resource_means": [row for row in resources if row["mean_change_percent"] > 0],
        "retrieval_calls_during_audit": 0, "sdk_sessions_during_audit": 0, "timing_runs_during_audit": 0,
        "formal_acceptance_evaluated": False, "release_acceptance": False,
        "limitations": [
            "The original four independently ingested archives have different complete source hashes, including two workers running the same baseline source. Each archive's full hash is unchanged before/after its own measurement.",
            "source_snapshot uses SELECT * for projects, chapters, sessions, turns, sections and pages. Ingestion assigns host-created/updated timestamps. Those fields make cross-archive full-hash equality inappropriate for independent database construction.",
            "Only hashes and logical projections were retained, not the original databases. This audit cannot reconstruct or prove that timestamp bytes are the only differences.",
            "The cross-archive projection preserves all pages/sections/turns and full FTS content; chapter/session projections omit host update timestamps, and the projects table is not in that projection. Equality of omitted project fields is not established by this supplement.",
            "All original output hashes, counts, budgets, cache records, resources, first calls and adverse results remain checked. No input, measurement helper, source, timer or original failure status is changed.",
            "This is an old-cohort two-round MCP development observation, not formal acceptance, new competitor measurement, statistical significance or a universal speed claim. Round 1 p95 improves only 9.908465%, below 10% as an individual round.",
            "The unchanged separately bound 56784-call formal run and every original numerical/resource gate remain required for release."
        ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / RESULT_DIRECTORY / "mcp-manifest.json.gz")
    parser.add_argument("--state-dir", type=Path, default=ROOT / RESULT_DIRECTORY / "mcp-state")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Preserve earlier audit receipts")
    result = audit(args.report, args.state_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("supplemental_audit_passed", "original_report_status",
        "timed_calls_in_original_records", "ledger_events_verified", "complete_output_pairs", "pooled",
        "per_round", "all_adverse_resource_means", "formal_acceptance_evaluated")}, indent=2))


if __name__ == "__main__":
    main()
