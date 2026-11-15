"""Apply the frozen release-selection criteria to independently audited evidence.

This never calls retrieval or changes a score. A completed protocol replay can
pass its original aggregate gate and still be unsuitable for release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


def read(path: Path):
    stored = path if path.exists() else Path(str(path) + ".gz")
    data = stored.read_bytes()
    if stored.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data), hashlib.sha256(data).hexdigest()


def select(candidate: Path, source_commit: str):
    report, report_sha = read(candidate / "report.json")
    audit, audit_sha = read(candidate / "independent-recomputation.json")
    plan = report["candidate_plan"]
    selector_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    checks = {
        "completed_and_original_gate_passed": report.get("status") == "completed"
            and report.get("integrity_passed") is True and report.get("acceptance_passed") is True,
        "independent_audit_passed": audit.get("passed") is True and not audit.get("errors"),
        "audited_report_bytes": audit["top_level_inputs"]["report.json"]["uncompressed_sha256"] == report_sha,
        "three_prespecified_conditions": [r["noise_per_step"] for r in audit["runs"]] == [2, 8, 32],
        "selector_matches_frozen_plan": plan.get("release_selection", {}).get("selector_sha256") == selector_sha,
        "source_commit_matches_audited_snapshot": bool(source_commit)
            and (audit.get("source_snapshot") or {}).get("source_commit") == source_commit,
        "regression_preflight_is_bound": plan.get("preflight_validation", {}).get("status") == "passed"
            and bool(plan.get("preflight_validation", {}).get("artifacts"))
            and report.get("preflight_validation") == plan.get("preflight_validation"),
    }
    conditions = []
    for run in audit["runs"]:
        new, old = run["candidate_summary"], run["control_book_summary"]
        other = [cell for name, cell in run["all_components"].items() if name != "book"]
        changes = run["candidate_vs_control"]
        gates = {
            "no_previously_retrieved_evidence_unit_lost": not changes["lost_previously_retrieved_evidence_units"],
            "no_previous_consumer_pass_lost": changes["metrics"]["fixed_consumer"].get("candidate_loss", 0) == 0,
            "stale_only_not_increased": new["stale_only"] <= old["stale_only"],
            "complete_evidence_at_least_best_tested_external": new["complete_cases"] >= max(x["complete_cases"] for x in other),
            "consumer_at_least_best_tested_external": new["consumer_passed"] >= max(x["consumer_passed"] for x in other),
            "all_actual_defaults_equal_common_context": run["default_cases_verified"] == 80,
            "all_native_calls_and_external_rows_verified": run["native_calls_verified"] == 240
                and run["reused_external_rows_verified"] == 240 and run["errors"] == 0,
        }
        conditions.append({"noise_per_step": run["noise_per_step"], "gates": gates,
            "candidate_summary": new, "control_book_summary": old})
    selected = all(checks.values()) and all(all(r["gates"].values()) for r in conditions)
    return {"schema": "engineering-2400-candidate-selection-v2",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_name": report["candidate_plan"]["candidate_name"],
        "source_commit": source_commit, "package_version": report["package_version"],
        "runtime_sha256": report["runtime"]["sha256"],
        "report_sha256": report_sha, "independent_audit_sha256": audit_sha,
        "selector_sha256": selector_sha,
        "automatic_replay_acceptance_passed": report["acceptance_passed"],
        "checks": checks, "conditions": conditions, "selected_for_release": selected,
        "scope": "Selection on this known authored development workload. Generic regression tests are separate, hash-bound preflight artifacts, not benchmark outcomes. This does not establish hidden-task, LLM-agent or full-product superiority.",
        "retention": "All original scores and failed candidates remain unchanged."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.candidate / "selection.json"
    if output.exists():
        parser.error(f"Refusing to replace an existing selection record: {output}")
    result = select(args.candidate, args.source_commit)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"selected_for_release": result["selected_for_release"],
        "checks": result["checks"], "conditions": [{"noise": r["noise_per_step"],
        "gates": r["gates"]} for r in result["conditions"]], "output": str(output)}, indent=2))
    return 0 if result["selected_for_release"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
