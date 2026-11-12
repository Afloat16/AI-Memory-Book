"""Verify all published cohorts, derive four reports, and save one audited snapshot.

This command performs no retrieval, embedding, data download or model request.
Missing cohorts fail before any summarizer runs. Negative measured outcomes are
retained; passing this audit is not a claim of improved answer/retrieval quality.
"""
from __future__ import annotations

import argparse
import copy
import gzip
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = "benchmarks/native-completion-manifest.json"
SEMANTIC = "benchmarks/semantic-recovery-20261112-manifest.json"
HOSTED = "benchmarks/hosted-validation-plan.json"
CLAUDE_PREFIX = "benchmarks/results/claude-mem-components-public"
CLAUDE_MARKER = "benchmarks/reports/hosted-claude-mem-completion.json"
CLAUDE_PLAN = "benchmarks/experiments/claude-mem-component-plan.json"
NATIVE_IDS = (
    "development-synthetic61", "regression-synthetic211", "regression-synthetic509",
    "regression-synthetic883", "regression-synthetic1297", "regression-public1015",
    "regression-authored36", "external-hotpot128",
)
SEMANTIC_IDS = (
    "development-synthetic61", "regression-authored36", "regression-public1015",
    "external-hotpot128",
)
OLD_CHECKPOINTS = (
    "benchmarks/reports/native-completion-checkpoint.json",
    "benchmarks/reports/native-continuation-checkpoint.json",
    "benchmarks/reports/native-recovery-checkpoint.json",
)
OUTPUTS = (
    "benchmarks/reports/native-completion-assessment.json",
    "benchmarks/RESULTS-native-token-budget.md",
    "benchmarks/results/semantic-final-assessment.json",
    "benchmarks/RESULTS-semantic-retrieval.md",
    "benchmarks/results/local-answer-final-assessment.json",
    "benchmarks/RESULTS-local-answers.md",
    "benchmarks/results/full-workflow-transfer36-assessment.json",
    "benchmarks/RESULTS-full-workflow.md",
)
AUDIT = "benchmarks/reports/hosted-final-aggregation.json"
SUMMARIZERS = (
    "scripts/summarize_native_completion.py",
    "scripts/summarize_semantic_completion.py",
    "scripts/summarize_local_answers.py",
    "scripts/summarize_workflow.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(root, name):
    return json.loads((root / name).read_bytes())


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def requirements(root):
    native, semantic = read(root, NATIVE), read(root, SEMANTIC)
    if tuple(s["id"] for s in native["stages"]) != NATIVE_IDS:
        raise ValueError("Require every original native cohort in its registered order")
    if tuple(s["id"] for s in semantic["stages"]) != SEMANTIC_IDS:
        raise ValueError("Require every registered semantic cohort in its original order")
    paths = {NATIVE, SEMANTIC, HOSTED, *OLD_CHECKPOINTS,
             "benchmarks/semantic-final-plan.json",
             "benchmarks/experiments/local-answer-plan.json",
             "benchmarks/experiments/local-answer-execution.json",
             "benchmarks/experiments/full-workflow-plan.json",
             "benchmarks/experiments/full-workflow-answers.json",
             "benchmarks/transfer_cases.json", CLAUDE_MARKER, CLAUDE_PLAN,
             "benchmarks/reports/claude-mem-native-smoke.json",
             *(CLAUDE_PREFIX + suffix for suffix in (".json.gz", ".summary.json", ".md"))}
    hosted = {}
    for family, manifest in (("native", native), ("semantic", semantic)):
        for stage in manifest["stages"]:
            paths.update(stage["outputs"])
            if family == "native" and stage["id"] in NATIVE_IDS[:3]:
                continue
            key = family + "-" + stage["id"]
            checkpoint = "benchmarks/reports/hosted-" + key + "-checkpoint.json"
            marker = "benchmarks/reports/hosted-" + key + "-completion.json"
            paths.update((checkpoint, marker))
            hosted[key] = {"outputs": stage["outputs"], "checkpoint": checkpoint,
                           "marker": marker, "registered_stage": stage}
    for cohort in ("locomo", "hotpotqa"):
        key = "answers-" + cohort
        outputs = ["benchmarks/results/local-answer-final-" + cohort + suffix
                   for suffix in (".json.gz", ".summary.json")]
        marker = "benchmarks/reports/hosted-" + key + "-completion.json"
        paths.update(outputs + [marker])
        hosted[key] = {"outputs": outputs, "marker": marker}
    marker = "benchmarks/reports/hosted-workflow-transfer36-completion.json"
    workflow = "benchmarks/results/full-workflow-transfer36.json"
    paths.update((marker, workflow))
    hosted["workflow-transfer36"] = {"outputs": [workflow], "marker": marker}
    declared = read(root, HOSTED)["stages"]
    if len(declared) != len(hosted) or set(declared) != set(hosted):
        raise ValueError("Hosted plan omits, duplicates or adds a cohort")
    return sorted(paths), hosted


def verify_checkpoint(root, name, stage):
    checkpoint = read(root, name)
    record = checkpoint["stages"].get(stage["id"], {})
    expected = {path: sha(root / path) for path in stage["outputs"]}
    identity = hashlib.sha256(json.dumps(checkpoint["identity"], sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    if (record.get("status") != "completed" or record.get("outputs") != expected
            or record.get("identity_sha256") != identity
            or record.get("argv", [])[1:] != stage["argv"][1:]):
        raise ValueError("Incomplete or inconsistent registered checkpoint: " + name)


def preflight(root):
    paths, hosted = requirements(root)
    missing = [name for name in paths if not (root / name).is_file()]
    if missing:
        raise ValueError("Missing required cohort evidence:\n" + "\n".join(missing))
    environments = []
    for key, specification in hosted.items():
        marker = read(root, specification["marker"])
        allowed_status = {"completed"} if "checkpoint" in specification else {"completed", "failed"}
        if marker.get("stage") != key or marker.get("status") not in allowed_status:
            raise ValueError("Hosted stage is not a final recorded attempt: " + key)
        expected = specification["outputs"] + ([specification["checkpoint"]]
                                              if "checkpoint" in specification else [])
        for name in expected:
            if marker.get("public_output_sha256", {}).get(name) != sha(root / name):
                raise ValueError("Hosted publication hash mismatch: " + name)
        if "checkpoint" in specification:
            verify_checkpoint(root, specification["checkpoint"], specification["registered_stage"])
        environments.append({"stage": key, "status": marker["status"],
                             "source_commit": marker.get("source_commit"),
                             "environment": marker.get("environment"),
                             "exit_code": marker.get("exit_code"),
                             "phase_exit_codes": marker.get("phase_exit_codes")})
    return {name: sha(root / name) for name in paths}, environments



def verify_claude_component(root):
    """Verify the preserved component result without querying native software."""
    prefix = root / CLAUDE_PREFIX
    compressed = Path(str(prefix) + ".json.gz").read_bytes()
    summary_bytes = Path(str(prefix) + ".summary.json").read_bytes()
    raw = gzip.decompress(compressed)
    if (hashlib.sha256(compressed).hexdigest() != "46eb187c99213dbf224367f1e2460213afad069125103029aecd3949a9cfa479"
            or hashlib.sha256(summary_bytes).hexdigest() != "52aa7d8be60360386962ad14ae7858f735559a6f3b19304d16dfd049d7b0295b"
            or hashlib.sha256(raw).hexdigest() != "484f8b1f47d5b12c1752bfc14a10c23e0aa9677c046741b03a2aa53c2bee0279"):
        raise ValueError("The preserved claude-mem component bytes changed")
    report, summary = json.loads(raw), json.loads(summary_bytes)
    derived = copy.deepcopy(report)
    derived["engine"].pop("native_query_costs")
    derived["engine"].pop("timing_rows")
    for config in derived["engine"]["packed_configurations"]:
        config.pop("query_results")
    derived["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    marker = read(root, CLAUDE_MARKER)
    if (derived != summary or report["validation"] != {"passed": True, "failures": []}
            or report["failures"] or marker["status"] != "completed"
            or marker["measurement_outcome"] != "success"
            or marker["ledger_sha256"] != report["ledger_sha256"]
            or report["plan"] != read(root, CLAUDE_PLAN)):
        raise ValueError("Invalid claude-mem report, plan or completion marker")
    for name, expected in marker["public_sha256"].items():
        if not name.startswith("benchmarks/") or sha(root / name) != expected:
            raise ValueError("claude-mem publication hash mismatch: " + name)
    engine, frozen = report["engine"], report["frozen_corpus"]
    metadata = engine["metadata"]
    dataset_hash = "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857"
    source_hash = "191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85"
    if (frozen["documents_sha256"] != "54aa61fd41b7b4058d07fd018bb6d99c6d34a7d73134fb567b67c56536df972a"
            or frozen["dataset"]["sha256"] != dataset_hash or engine["dataset"]["sha256"] != dataset_hash
            or not frozen["source_unchanged"] or frozen["source_sha256_before"] != source_hash
            or frozen["source_sha256_after"] != source_hash
            or frozen["source_provenance"]["git_commit"] != "6f5299004642618e606d001b4c574e1bae572a7e"
            or metadata["commit"] != "2cfed7620c1b44db87c7f04cbf073ec37efca38d"
            or not metadata["source_unchanged"] or metadata["native_process_exit_code"] != 0
            or not metadata["fts_integrity_check"] or metadata["supplied_pages"] != 1339):
        raise ValueError("claude-mem component source or corpus identity changed")
    query_ids = [row["id"] for row in engine["native_query_costs"]]
    if len(query_ids) != 1015 or len(set(query_ids)) != 1015 or any(
            row["status"] != "ok" for row in engine["native_query_costs"]):
        raise ValueError("Incomplete claude-mem native query records")
    expected_timings = {(qid, repetition) for qid in query_ids for repetition in range(3)}
    observed = [(row["id"], row["repetition"]) for row in engine["timing_rows"]]
    if len(observed) != 3045 or set(observed) != expected_timings:
        raise ValueError("Incomplete claude-mem repetition matrix")
    configs = engine["packed_configurations"]
    expected_configs = {(encoding, cap) for encoding in ("cl100k_base", "o200k_base")
                        for cap in (512, 1024, 2048)}
    if len(configs) != 6 or {(c["tokenizer"], c["budget_tokens"]) for c in configs} != expected_configs:
        raise ValueError("Incomplete claude-mem token budget matrix")
    for config in configs:
        metrics = config["metrics"]
        if (any(metrics[key] != value for key, value in {
                "queries": 1015, "answerable_queries": 649, "unanswerable_queries": 366,
                "required_evidence": 788, "budget_violations": 0, "context_size_mismatches": 0}.items())
                or config["token_budget_violations"] or len(config["query_results"]) != 1015
                or {row["id"] for row in config["query_results"]} != set(query_ids)):
            raise ValueError("Invalid claude-mem context metrics")
    states = marker["attempt_states"]
    starts = [(row["query_id"], row["repetition"]) for row in states if row["event"] == "started"]
    finishes = [row for row in states if row["event"] == "finished"]
    if (len(states) != 6090 or len(starts) != 3045 or set(starts) != expected_timings
            or len(finishes) != 3045
            or {(row["id"], row["repetition"]) for row in finishes} != expected_timings
            or any(row["status"] != "ok" or not row.get("payload_sha256") for row in finishes)):
        raise ValueError("Invalid published claude-mem attempt-state projection")
    return {"queries": 1015, "native_repetitions": 3045, "context_configurations": 6,
            "raw_content_sha256": summary["full_report_sha256"], "ledger_sha256": report["ledger_sha256"],
            "scope": metadata["comparison_scope"],
            "note": "Published attempt states are a projection; their JSON is not the original ledger bytes. Timing remains attributed to its original hosted process."}


def verify_assessments(root):
    native = read(root, OUTPUTS[0])
    semantic = read(root, OUTPUTS[2])
    answers = read(root, OUTPUTS[4])
    workflow = read(root, OUTPUTS[6])
    native_gate = native.get("validation", {})
    if (native_gate.get("passed") is not True or native_gate.get("stages") != 8
            or native_gate.get("query_configuration_pairs") != 24228
            or native_gate.get("raw_summary_checkpoint_agreement") is not True
            or native_gate.get("all_registered_axes") is not True
            or tuple(s["stage"] for s in native["stages"]) != NATIVE_IDS):
        raise ValueError("The full 24,228-pair native matrix did not pass integrity checks")
    if (semantic.get("status") != "complete-frozen-matrix"
            or semantic.get("completed_cohorts") != 4 or semantic.get("missing_cohorts")
            or len(semantic.get("quality", [])) != 12):
        raise ValueError("The full four-cohort semantic matrix is missing")
    if (answers.get("status") != "complete-registered-local-answer-matrix"
            or answers.get("actual_attempts") != 768
            or {c["cohort"] for c in answers["cohorts"]} != {"locomo", "hotpotqa"}):
        raise ValueError("The full 768-attempt real-answer matrix is missing")
    if (workflow.get("status") not in {"completed", "completed_with_failures"}
            or workflow.get("actual_answer_attempts") != 72
            or workflow.get("native_capture_sessions") != 42):
        raise ValueError("The complete registered native-workflow attempt matrix is missing")
    return {"native_query_configuration_pairs": 24228, "native_cohorts": 8,
            "semantic_cohorts": 4, "answer_attempts": 768, "workflow_answer_attempts": 72,
            "workflow_status": workflow["status"],
            "interpretation": "Integrity/completeness only. Gains, losses, model errors and unknown costs remain in the separate assessments. Timings are never pooled across hosts."}


def publish(root, success):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if (not run_id.isdigit() or not attempt.isdigit()
            or os.environ.get("GITHUB_REF") != "refs/heads/ci/aggregate-memory-validation"):
        raise ValueError("Publication requires the dedicated Actions branch and run identity")
    branch = "validation/final-memory-" + run_id + "-" + attempt
    files = [AUDIT] + (list(OUTPUTS) if success else [])
    commands = [
        ["git", "config", "user.name", "github-actions[bot]"],
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        ["git", "add", "--", *files],
        ["git", "commit", "-m", "bench: preserve complete memory assessment" if success
         else "bench: preserve failed memory aggregation audit"],
        ["git", "push", "origin", "HEAD:refs/heads/" + branch],
    ]
    for command in commands:
        subprocess.run(command, cwd=root, check=True)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as stream:
            stream.write("Saved " + ("validated reports" if success else "failure audit")
                         + " to branch " + branch + ".\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", action="store_true",
                        help="Print exact required input/output paths without creating reports")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.inventory:
        paths, _ = requirements(root)
        print(json.dumps({"inputs": paths, "outputs": list(OUTPUTS) + [AUDIT]}, indent=2))
        return 0
    audit = {"schema_version": 1, "status": "running", "started_at": now(),
             "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
             "summarizer_sha256": {name: sha(root / name) for name in SUMMARIZERS},
             "commands": [], "measurement": "Aggregate existing evidence only; no benchmark or model calls."}
    atomic(root / AUDIT, audit)
    success = False
    try:
        hashes, environments = preflight(root)
        audit.update(input_sha256=hashes, measured_environments=environments,
                     claude_component=verify_claude_component(root))
        atomic(root / AUDIT, audit)
        for script in SUMMARIZERS:
            command = [sys.executable, str(root / script)]
            outcome = subprocess.run(command, cwd=root, check=False)
            audit["commands"].append({"argv": command, "exit_code": outcome.returncode})
            atomic(root / AUDIT, audit)
            if outcome.returncode:
                raise ValueError("Strict summarizer failed: " + script)
        audit["matrix"] = verify_assessments(root)
        if any(sha(root / name) != expected for name, expected in hashes.items()):
            raise ValueError("A canonical input changed during aggregation")
        audit["output_sha256"] = {name: sha(root / name) for name in OUTPUTS}
        audit["status"] = "complete-verified-snapshot"
        success = True
    except Exception as exc:
        audit.update(status="failed", error_type=type(exc).__name__, error_message=str(exc))
        print(str(exc), file=sys.stderr)
    finally:
        audit["finished_at"] = now()
        atomic(root / AUDIT, audit)
        if args.publish:
            publish(root, success)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
