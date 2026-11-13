"""Reconstruct one saved resource diagnostic without importing any runtime.

Only standard-library parsing and read-only local Git commands are used.
The original thirty published artifacts are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUN = "43377486180-1"
SOURCE = "d67e6c695aa586bbcbc9f0e134c769980d8e09ef"
RESULT = "2511be109e2877e86d4d452525754d399e514789"
DIRECTORY = "benchmarks/reports/round5-resources-" + RUN
PLAN = "benchmarks/experiments/round5-resource-plan.json"
ORDER = ("evaluator", "r0-v031", "r0-v032", "r1-v032", "r1-v031",
         "r2-v032", "r2-v031", "r3-v031", "r3-v032")
METRICS = ("root_rss_bytes", "root_pss_bytes", "tree_rss_bytes",
           "descendant_rss_bytes", "tree_pss_bytes")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode())


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, timeout=30)


@lru_cache(maxsize=None)
def blob(commit, name):
    return git("show", commit + ":" + name)


def document(commit, name):
    return json.loads(blob(commit, name))


def local_matches(commit, name):
    raw = (ROOT / name).read_bytes()
    require(raw == blob(commit, name), "Local bytes differ from exact commit: " + name)
    return sha(raw)


def runtime_hash(commit):
    prefix = "src/memory_book/"
    names = git("ls-tree", "-r", "--name-only", commit, "--", prefix).decode().splitlines()
    value = hashlib.sha256()
    for name in sorted(name for name in names if name.endswith(".py")):
        value.update(name.removeprefix(prefix).encode())
        value.update(bytes([0]))
        value.update(blob(commit, name))
        value.update(bytes([0]))
    return value.hexdigest()


def classify(sample, markers):
    if sample["boundary"] is not None:
        return sample["phase"]
    start, end = sample["started_monotonic_ns"], sample["finished_monotonic_ns"]
    if any(start < event["monotonic_ns"] <= end for event in markers):
        return "transition"
    previous = [event for event in markers if event["monotonic_ns"] <= start]
    if not previous:
        return "spawn"
    event = previous[-1]
    return event["phase"] if event["event"] == "phase_start" else "between_phases"


def audit_worker(name, plan, ids):
    prefix = DIRECTORY + "/" + name
    summary = document(RESULT, prefix + ".summary.json")
    events = [json.loads(line) for line in blob(RESULT, prefix + ".events.jsonl").splitlines()]
    samples = [json.loads(line) for line in gzip.decompress(blob(RESULT, prefix + ".trace.jsonl.gz")).splitlines()]
    product = name != "evaluator"
    expected_phases = plan["product" if product else "evaluator_only"]["phases"]
    require(summary["name"] == name and summary["status"] == "completed"
            and summary["exit_code"] == 0 and summary["failure_type"] is None
            and summary["failure_check"] is None and summary["trailing_stdout_bytes"] == 0,
            "Incomplete worker: " + name)
    cleanup = summary["cleanup"]
    require(cleanup["leader_reaped"] and not cleanup["errors"]
            and not cleanup["group_present_after_cleanup"], "Unfinished worker cleanup: " + name)
    require(summary["target_sampling_interval_ms"] == 20, "Changed sampling target")
    require(summary["events_sha256"] == sha(blob(RESULT, prefix + ".events.jsonl"))
            and summary["trace_sha256"] == sha(blob(RESULT, prefix + ".trace.jsonl.gz")),
            "Worker trace/event hashes differ")
    require(events and samples and all(event["pid"] == summary["root_pid"] for event in events),
            "Missing worker evidence or changed PID")
    require(all(left["monotonic_ns"] < right["monotonic_ns"]
                for left, right in zip(events, events[1:])), "Worker event order changed")
    markers = [event for event in events if event["event"].startswith("phase_")]
    require([(event["event"], event["phase"]) for event in markers] ==
            [(kind, phase) for phase in expected_phases for kind in ("phase_start", "phase_end")],
            "Registered phase order differs")
    queries = [event for event in events if event["event"].startswith("query_")]
    expected_ids = ids if product else []
    require([(event["event"], event["id"]) for event in queries] ==
            [(kind, identity) for identity in expected_ids for kind in ("query_start", "query_finish")],
            "Missing, reordered or repeated query event")
    finished = [event for event in queries if event["event"] == "query_finish"]
    require(summary["query_results"] == finished
            and summary["calls_started"] == summary["calls_finished"] == len(expected_ids),
            "Summary does not preserve exact query ledger")
    active = None
    for event in events:
        if event["event"] == "phase_start":
            active = event["phase"]
        elif event["event"] == "phase_end":
            active = None
        elif event["event"].startswith("query_"):
            require(active == "product_queries", "Query outside product phase")
        else:
            require(event["event"] == "done" and event is events[-1], "Failure or unexpected worker event")
    done = events[-1]
    require(done["event"] == "done" and done["recalls"] == len(expected_ids)
            and done["worker_peak_rss_bytes"] == summary["worker_peak_rss_bytes"], "Completion differs")
    if product:
        require(done["source_version"] == name[-4:] and done["sessions"] == 2548 and done["pages"] == 3953,
                "Product completion counts/source changed")
    else:
        require(done["embedding_inference_calls"] == done["generative_model_calls"] == 0,
                "Evaluator reports inference")
    for event in finished:
        require(len(event["payload_sha256"]) == 64 and
                all(char in "0123456789abcdef" for char in event["payload_sha256"]), "Invalid output hash")

    phases, missing, identities, boundaries = {}, [], set(), []
    root_identities, previous_end = set(), 0
    for index, sample in enumerate(samples):
        start, end = sample["started_monotonic_ns"], sample["finished_monotonic_ns"]
        require(type(start) is int and type(end) is int and previous_end <= start <= end,
                "Overlapping or reordered observer samples")
        previous_end = end
        require(sample["root_pid"] == summary["root_pid"], "Observer root PID changed")
        records = sample["processes"]
        pids = [record["pid"] for record in records]
        enumerated = sample["enumerated_pids"]
        require(pids == sorted(set(pids)) and enumerated == sorted(set(enumerated))
                and set(pids) <= set(enumerated), "Invalid process inventory")
        by_pid = {record["pid"]: record for record in records}
        root = by_pid.get(summary["root_pid"])
        for record in records:
            require(all(type(record[key]) is int and record[key] >= 0
                        for key in ("pid", "ppid", "start_ticks", "rss_bytes"))
                    and record["pid"] > 0 and record["comm_role"] in ("python", "git", "other"),
                    "Invalid PID identity/RSS")
            for key in ("pss_bytes", "private_bytes"):
                require(record[key] is None or type(record[key]) is int and record[key] >= 0,
                        "Invalid optional memory value")
            require((record["pss_bytes"] is None) == (record["pss_unavailable_reason"] is not None),
                    "Missing PSS reason changed")
            lineage, pid = set(), record["pid"]
            while pid != summary["root_pid"]:
                require(pid in by_pid and pid not in lineage, "Disconnected/cyclic descendant record")
                lineage.add(pid)
                pid = by_pid[pid]["ppid"]
            identities.add((record["pid"], record["ppid"], record["start_ticks"], record["comm_role"]))
        if root:
            root_identities.add((root["pid"], root["ppid"], root["start_ticks"]))
        complete = not sample["discovery_errors"] and len(records) == len(enumerated)
        pss_complete = bool(records) and complete and all(record["pss_bytes"] is not None for record in records)
        require(sample["discovery_complete"] == complete and sample["pss_complete"] == pss_complete,
                "Discovery/PSS completeness differs from raw process records")
        computed = {
            "root_rss_bytes": root["rss_bytes"] if root else None,
            "root_pss_bytes": root["pss_bytes"] if root else None,
            "tree_rss_bytes": sum(record["rss_bytes"] for record in records) if records else None,
            "descendant_rss_bytes": sum(record["rss_bytes"] for record in records
                                        if record["pid"] != summary["root_pid"]),
            "tree_pss_bytes": sum(record["pss_bytes"] for record in records) if pss_complete else None,
        }
        require(all(sample[key] == value for key, value in computed.items()), "Saved process totals differ")
        phase = classify(sample, markers)
        require(phase in set(expected_phases) | {"spawn", "between_phases", "transition"}, "Unknown phase")
        if sample["boundary"] is not None:
            require(sample["boundary"] in ("start", "end"), "Unknown boundary")
            marker = next(event for event in markers if event["phase"] == phase
                          and event["event"] == "phase_" + sample["boundary"])
            following = [event["monotonic_ns"] for event in events if event["monotonic_ns"] > marker["monotonic_ns"]]
            require(marker["monotonic_ns"] <= start and (not following or end < min(following)),
                    "Boundary is outside its acknowledged event interval")
            boundaries.append((phase, sample["boundary"]))
        if not pss_complete:
            missing.append({"worker": name, "sample_index": index, "phase": phase,
                            "enumerated_pids": enumerated, "readable_pids": pids,
                            "discovery_errors": sample["discovery_errors"]})
        aggregate = phases.setdefault(phase, {"samples": 0, "root_unreadable": 0,
            "incomplete_discovery_samples": 0, "complete_pss_samples": 0,
            "max_observed_processes": 0, "peaks": {}})
        aggregate["samples"] += 1
        aggregate["root_unreadable"] += root is None
        aggregate["incomplete_discovery_samples"] += not complete
        aggregate["complete_pss_samples"] += pss_complete
        aggregate["max_observed_processes"] = max(aggregate["max_observed_processes"], len(records))
        for metric, value in computed.items():
            peak = aggregate["peaks"].get(metric)
            if value is not None and (peak is None or value > peak["bytes"]):
                aggregate["peaks"][metric] = {"bytes": value, "sample_index": index,
                    "processes": records, "boundary": sample["boundary"]}
    require(boundaries == [(phase, kind) for phase in expected_phases for kind in ("start", "end")],
            "Boundary samples missing/reordered")
    require(len(root_identities) == 1 and phases == summary["phases"], "Phase/PID reconstruction differs")
    require(all(phases[phase]["samples"] >= 2 and phases[phase]["root_unreadable"] == 0
                for phase in expected_phases), "Registered phase lacks readable root")
    brief = {"name": name, "root_identity": list(next(iter(root_identities))),
        "trace_samples": len(samples), "events": len(events), "recalls": len(finished),
        "first_sample_monotonic_ns": samples[0]["started_monotonic_ns"],
        "last_sample_monotonic_ns": samples[-1]["finished_monotonic_ns"],
        "first_event_monotonic_ns": events[0]["monotonic_ns"],
        "last_event_monotonic_ns": events[-1]["monotonic_ns"],
        "whole_worker_high_water_rss_bytes": summary["worker_peak_rss_bytes"],
        "observed_process_identities": [list(identity) for identity in sorted(identities)],
        "phase_reconstruction_sha256": digest(phases),
        "phases": {phase: {**{key: value for key, value in values.items() if key != "peaks"},
                   "peaks_bytes": {metric: peak["bytes"] for metric, peak in values["peaks"].items()}}
                   for phase, values in phases.items()}}
    return brief, finished, missing


def audit():
    plan = document(SOURCE, PLAN)
    checkpoint = document(RESULT, DIRECTORY + "/checkpoint.json")
    assessment = document(RESULT, DIRECTORY + "/assessment.json")
    plan_hash = local_matches(SOURCE, PLAN)
    require(checkpoint["source_commit"] == SOURCE and checkpoint["run_id"] == RUN
            and checkpoint["plan_sha256"] == plan_hash and checkpoint["status"] == "complete-verified",
            "Wrong completed run identity")
    require(plan["protocol"] == "round5-historical-resource-attribution-v1"
            and plan["product"]["total_recall_calls"] == 256
            and plan["environment"]["generative_model_calls"] == plan["environment"]["embedding_inference_calls"] == 0,
            "Changed resource registration")
    claim_path = "benchmarks/reports/round5-resource-claim-" + plan_hash + ".json"
    claim_commit = checkpoint["claim_commit"]
    claim = document(claim_commit, claim_path)
    require(claim["source_commit"] == SOURCE and claim["run_id"] == RUN
            and claim["plan_sha256"] == plan_hash and claim["sources"] == plan["sources"]
            and claim["status"] == "claimed-before-preparation", "Claim identity differs")
    require(git("rev-list", "--parents", "-n", "1", claim_commit).decode().split() ==
            [claim_commit, SOURCE], "Claim does not directly descend from frozen code")
    require(blob(claim_commit, claim_path) == blob(RESULT, claim_path), "Claim changed in result history")
    require(set(claim["evaluator_files"]) == {PLAN, "scripts/round5_resource_diagnostic.py",
            "tests/test_round5_resource_diagnostic.py", ".github/workflows/round5-resource-diagnostic.yml"},
            "Changed evaluator file registry")
    for name, expected in claim["evaluator_files"].items():
        require(local_matches(SOURCE, name) == expected and sha(blob(RESULT, name)) == expected,
                "Frozen evaluator identity differs: " + name)
    inputs = {}
    for name, expected in ((plan["corpus"]["manifest"], plan["corpus"]["manifest_sha256"]),
                           (plan["corpus"]["binding"], plan["corpus"]["binding_sha256"]),
                           ("benchmarks/experiments/round5-plan.json", plan["parent_plan_sha256"])):
        inputs[name] = local_matches(SOURCE, name)
        require(inputs[name] == expected, "Frozen input registration differs")
    old_binding = document(SOURCE, plan["corpus"]["binding"])
    for name, expected in old_binding["evaluator_files"].items():
        require(sha(blob(SOURCE, name)) == expected, "Historical evaluator helper changed: " + name)
    for label, identity in plan["sources"].items():
        require(runtime_hash(identity["commit"]) == identity["runtime_sha256"], "Runtime source hash differs: " + label)
    manifest = document(SOURCE, plan["corpus"]["manifest"])
    require(len(manifest["selected_ids"]) == len(set(manifest["selected_ids"])) == 256, "Old ID set differs")
    ids = sorted(manifest["selected_ids"], key=lambda identity:
                 (sha((plan["corpus"]["selection_prefix"] + identity).encode()), identity))[:32]
    require(digest(ids) == plan["corpus"]["selected_ids_sha256"], "Registered selected-ID order differs")
    names = git("ls-tree", "-r", "--name-only", RESULT, "--", DIRECTORY).decode().splitlines()
    expected_names = {DIRECTORY + "/" + name + suffix for name in ORDER
                      for suffix in (".summary.json", ".events.jsonl", ".trace.jsonl.gz")}
    expected_names |= {DIRECTORY + "/checkpoint.json", DIRECTORY + "/assessment.json"}
    require(set(names) == expected_names, "Missing or unexpected published worker files")
    hashes = {name: local_matches(RESULT, name) for name in sorted(expected_names | {claim_path})}
    require(len(hashes) == 30, "Expected thirty published evidence files")
    require([stage["name"] for stage in checkpoint["stages"]] == list(ORDER), "Registered ABBA order changed")
    normalized = checkpoint["normalized_input"]
    require(normalized["sessions"] == 2548 and normalized["queries"] == 32
            and normalized["dataset_sha256"] == plan["corpus"]["dataset_sha256"]
            and normalized["selected_ids_sha256"] == digest(ids), "Normalized input identity differs")
    require(checkpoint["host"]["platform"] == "linux" and checkpoint["host"]["python"].startswith("3.12.")
            and checkpoint["host"]["packages"] == plan["environment"]["packages"], "Host/dependency contract differs")

    chain = git("rev-list", "--first-parent", "--reverse", claim_commit + ".." + RESULT).decode().splitlines()
    require(len(chain) == 21, "Unexpected preparation/intent/completion history")
    previous = claim_commit
    for index, commit in enumerate(chain):
        require(git("rev-list", "--parents", "-n", "1", commit).decode().split() == [commit, previous],
                "Nonlinear checkpoint history")
        historical = document(commit, DIRECTORY + "/checkpoint.json")
        for key in ("run_id", "source_commit", "claim_commit", "plan_sha256", "started_at", "host"):
            require(historical[key] == checkpoint[key], "Changed checkpoint identity")
        if index:
            require(historical["normalized_input"] == normalized, "Normalized input rebound")
        completed = max(0, min(9, (index - 1) // 2))
        intent = index >= 2 and index < 20 and index % 2 == 0
        expected = checkpoint["stages"][:completed]
        if intent:
            stage = checkpoint["stages"][completed]
            require(stage["intent_commit"] == commit, "Worker intent commit differs")
            expected = expected + [{key: value for key, value in stage.items()
                                    if key not in ("intent_commit", "finished_at", "outputs", "status")} |
                                   {"status": "intent-before-launch"}]
        require(historical["stages"] == expected, "Checkpoint prefix differs from exact prior workers")
        present = {DIRECTORY + "/checkpoint.json"} | {
            DIRECTORY + "/" + stage["name"] + suffix for stage in checkpoint["stages"][:completed]
            for suffix in (".summary.json", ".events.jsonl", ".trace.jsonl.gz")}
        if index == 20:
            present.add(DIRECTORY + "/assessment.json")
        require(set(git("ls-tree", "-r", "--name-only", commit, "--", DIRECTORY).decode().splitlines()) == present,
                "Outputs existed before their worker or checkpoint files are incomplete")
        for name in present - {DIRECTORY + "/checkpoint.json"}:
            require(blob(commit, name) == blob(RESULT, name), "Previously published worker output changed")
        previous = commit

    workers, reference, missing = [], None, []
    for stage in checkpoint["stages"]:
        name = stage["name"]
        require(stage["status"] == "completed" and len(stage["outputs"]) == 3, "Incomplete stage outputs")
        for filename, expected in stage["outputs"].items():
            require(hashes[DIRECTORY + "/" + filename] == expected, "Checkpoint output hash differs")
        argv = stage["argv"]
        require(argv[3] == ("evaluator-worker" if name == "evaluator" else "product-worker")
                and argv[argv.index("--name") + 1] == name
                and argv[argv.index("--claim") + 1] == claim_commit, "Worker command identity differs")
        if name != "evaluator":
            label = name[-4:]
            require(stage["source"] == plan["sources"][label]
                    and argv[argv.index("--version") + 1] == label, "Worker source binding differs")
            for key in ("sessions", "queries"):
                require(argv[argv.index("--" + key + "-sha256") + 1] == normalized[key + "_sha256"],
                        "Worker used a rebound private input hash")
        brief, rows, absent = audit_worker(name, plan, ids)
        if workers:
            require(brief["first_sample_monotonic_ns"] > workers[-1]["last_sample_monotonic_ns"]
                    and brief["first_event_monotonic_ns"] > workers[-1]["last_event_monotonic_ns"],
                    "Worker execution overlaps/reorders the registered schedule")
        if rows:
            payloads = [row["payload_sha256"] for row in rows]
            require(reference is None or payloads == reference, "Complete output hashes differ")
            reference = payloads
        workers.append(brief)
        missing.extend(absent)
    require(assessment["status"] == "complete-verified" and assessment["workers"] == 9
            and assessment["product_workers"] == 8 and assessment["product_calls"] == 256
            and assessment["complete_payload_pairs"] == 128 and assessment["all_output_hashes_equal"] is True
            and assessment["selected_ids_sha256"] == digest(ids)
            and assessment["pss_missing_samples"] == len(missing) == 6, "Assessment differs from reconstruction")
    return {"schema_version": 1, "audit": "round5-resource-saved-audit-1", "status": "verified-with-attribution-limits",
        "created_at": datetime.now(timezone.utc).isoformat(), "run_id": RUN,
        "source_commit": SOURCE, "result_commit": RESULT, "claim_commit": claim_commit,
        "plan_sha256": plan_hash, "auditor_sha256": sha(Path(__file__).read_bytes()),
        "evaluator_files": claim["evaluator_files"], "sources": plan["sources"],
        "frozen_input_files": inputs, "historical_helpers_verified": len(old_binding["evaluator_files"]),
        "published_files_sha256": hashes, "checkpoint_commits_verified": chain,
        "calls_reconstructed": 256, "complete_payload_pairs": 128,
        "selected_ids_sha256": digest(ids), "complete_payload_sequence_sha256": digest(reference),
        "trace_samples": sum(worker["trace_samples"] for worker in workers),
        "missing_complete_pss_samples": missing, "workers": workers,
        "high_water_scope_anomaly": {
            "product_reported_values_bytes": sorted({worker["whole_worker_high_water_rss_bytes"] for worker in workers[1:]}),
            "interpretation": "All eight product workers report the same 373.34375 MiB lifetime high-water counter, substantially above their roughly 31 MiB sampled query phases. This suggests launch/lifetime counter scope, but the trace does not establish its cause. It is not product steady RSS."},
        "limitations": [
            "Only immutable local Git objects and saved source-free evidence were inspected; private normalized inputs were not reread.",
            "Phase peaks are sampled lower bounds; each product query phase has only four samples including two acknowledged boundaries.",
            "Missing discovery/PSS is retained as unavailable, never zero; summed RSS can count shared mappings more than once.",
            "Evaluator phase values are cumulative resident peaks in one worker, not independent additive allocation costs.",
            "The new diagnostic does not retrospectively identify the old unrecorded children or replace the adverse round-four peaks.",
            "This historical diagnostic measures no v0.3.3 candidate and supports no speed, quality, leak or memory-saving claim."],
        "retrieval_calls_executed_by_audit": 0, "inference_calls_executed_by_audit": 0,
        "network_requests_executed_by_audit": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/reports/round5-resource-independent-audit.json")
    args = parser.parse_args()
    require(not args.output.exists(), "Preserve an existing independent audit receipt")
    result = audit()
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + chr(10))
    print(json.dumps({"status": result["status"], "files": len(result["published_files_sha256"]),
                      "workers": len(result["workers"]), "calls": result["calls_reconstructed"],
                      "samples": result["trace_samples"], "missing_complete_pss": len(result["missing_complete_pss_samples"]),
                      "retrieval_calls_executed_by_audit": 0}))


if __name__ == "__main__":
    main()
