#!/usr/bin/env python3
"""Freeze, audit and preserve directory formal 2, including rejected results.

Formal 1's evaluator, auditor and observations remain unchanged. Only its pure
file, hash and create-only Git helpers are reused. No measurements run here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
_shared_spec = importlib.util.spec_from_file_location("_directory_v2_frozen_io", ROOT / "scripts/comprehensive_runtime_preserve.py")
shared = importlib.util.module_from_spec(_shared_spec)
_shared_spec.loader.exec_module(shared)

BASELINE = shared.BASELINE
REPOSITORY = shared.REPOSITORY
BRANCH = "validation/comprehensive-v010-directory-formal-2"
WORKFLOW = ".github/workflows/directory-runtime-performance-v2.yml"
PLAN = "benchmarks/directory-runtime-plan-v2.json"
HARNESS = "scripts/benchmark_directory_runtime_v2.py"
PROTOCOL = "directory-runtime-v2"
WORK_PATH = ".artifacts/comprehensive-directory-v2"
PRESERVATION_PATH = ".artifacts/comprehensive-directory-v2-preservation"
STORE_SHA256 = "355687bb28eff83160b42120d7a22be1273c6405fa77e8549266f92dfe0e8b87"
SEMANTIC_SHA256 = "76aaaf40144146c5b3e6c542c1a3dedcad1a19f78d654da613dc085586bec6fd"
FIXTURE_SHA256 = "d7a00bd8d393c9d6153c1cd5094eba0812eaceb7c47db986e361e853c2b944e4"
MAX_WALL_RATIO = 1.05
REQUIRED_IMPROVEMENTS = ((20, 20), (100, 20))
EVALUATOR_PATHS = ("scripts/directory_runtime_v2_preserve.py", "scripts/comprehensive_runtime_preserve.py",
                   HARNESS, PLAN, WORKFLOW, "pyproject.toml")
STEPS = ("checkout", "python", "freeze", "install", "validate", "measure")
require, read, sha = shared.require, shared.read, shared.sha


def identity():
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "Only the dedicated directory formal-2 first attempt is allowed")
    run, commit = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_SHA", "")
    require(run.isdigit() and int(run) > 0 and len(commit) == 40
            and shared.git("rev-parse", "HEAD").stdout.decode().strip() == commit
            and os.environ.get("GITHUB_WORKFLOW_SHA") == commit
            and os.environ.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH,
            "Workflow, source, or run identity differs")
    return {"id": run, "attempt": 1, "commit": commit, "url": f"https://github.com/{REPOSITORY}/actions/runs/{run}"}


def freeze():
    run = identity()
    work = ROOT / WORK_PATH
    require(not (work / "source-manifest.json").exists() and not (work / "frozen").exists(), "Frozen inputs already exist")
    manifest = {"protocol": PROTOCOL, "source_run": run, "baseline_commit": BASELINE, "status": "freezing", "files": {},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
            "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion"),
            "runner_os": os.environ.get("RUNNER_OS"), "runner_arch": os.environ.get("RUNNER_ARCH"),
            "text_backend": os.environ.get("MEMORY_BOOK_TEXT_BACKEND"),
            "thread_environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}}
    try:
        shared.freeze_tree(work, "candidate", run["commit"], ("src/memory_book", "tests", *EVALUATOR_PATHS), manifest["files"])
        shared.clean_source()
        require(sys.version_info[:2] == (3, 12) and os.environ.get("MEMORY_BOOK_TEXT_BACKEND") == "python", "Backend or Python differs")
        require(sha((ROOT / "src/memory_book/store.py").read_bytes()) == STORE_SHA256
                and sha((ROOT / "src/memory_book/semantic.py").read_bytes()) == SEMANTIC_SHA256,
                "Candidate directory source differs, or semantic source changed and requires new evidence")
        fetched = shared.git("fetch", "--no-tags", "--filter=blob:none", "--depth=1", "origin", BASELINE, check=False)
        shared.write_new(work / "logs/baseline-fetch.stdout.log", fetched.stdout)
        shared.write_new(work / "logs/baseline-fetch.stderr.log", fetched.stderr)
        require(fetched.returncode == 0 and shared.git("rev-parse", BASELINE + "^{commit}").stdout.decode().strip() == BASELINE,
                "Exact baseline could not be fetched")
        shared.freeze_tree(work, "baseline", BASELINE, ("src/memory_book", "pyproject.toml"), manifest["files"])
        require(all("frozen/candidate/" + name in manifest["files"] for name in EVALUATOR_PATHS), "An evaluator input is missing")
        manifest["status"] = "frozen"
    except BaseException as error:
        manifest.update(status="failed", error=shared.failure(error))
        raise
    finally:
        shared.write_new(work / "source-manifest.json", shared.encoded(manifest))
    print(json.dumps({"status": "frozen", "source_run": run, "files": len(manifest["files"])}))


def verify_frozen(work, run, check_worktree=False):
    manifest = read(work / "source-manifest.json")
    require(manifest["protocol"] == PROTOCOL and manifest["status"] == "frozen"
            and manifest["source_run"] == run and manifest["baseline_commit"] == BASELINE, "Frozen identity differs")
    for name, specification in manifest["files"].items():
        raw = (work / name).read_bytes()
        require(shared.inventory(raw) == {key: specification[key] for key in ("bytes", "sha256")}, "Frozen bytes changed: " + name)
        if check_worktree and name.startswith("frozen/candidate/"):
            require((ROOT / specification["source"]).read_bytes() == raw, "Candidate changed after freezing: " + specification["source"])
    require(shared.source_hash(manifest, "candidate", "src/memory_book/store.py") == STORE_SHA256
            and shared.source_hash(manifest, "candidate", "src/memory_book/semantic.py") == SEMANTIC_SHA256,
            "Frozen candidate differs from the prospective source")
    return manifest


def check():
    run = identity()
    shared.clean_source()
    manifest = verify_frozen(ROOT / WORK_PATH, run, check_worktree=True)
    import numpy
    require(sys.version_info[:2] == (3, 12) and numpy.__version__ == shared.NUMPY
            and os.environ.get("MEMORY_BOOK_TEXT_BACKEND") == "python" and os.environ.get("PYTHONHASHSEED") == "0"
            and all(os.environ.get(key) == "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")),
            "Frozen environment differs")
    print(json.dumps({"source_run": run, "frozen_files_verified": len(manifest["files"]), "numpy": numpy.__version__}))


def summarize(configuration, metric):
    medians = {arm: statistics.median(row[metric] for trial in configuration["rounds"] for row in trial["arms"][arm])
               for arm in ("baseline", "candidate")}
    paired = [statistics.median(row[metric] for row in trial["arms"]["candidate"])
              / statistics.median(row[metric] for row in trial["arms"]["baseline"]) for trial in configuration["rounds"]]
    return {"median_per_call": medians, "paired_candidate_over_baseline": paired, "median_paired_ratio": statistics.median(paired)}


def acceptance(report):
    configurations, violations = [], []
    for item in report["configurations"]:
        wall, cpu = summarize(item, "wall_ns"), summarize(item, "process_cpu_ns")
        ratio = wall["median_paired_ratio"]
        limits = {"maximum_wall_ratio": MAX_WALL_RATIO, "strict_improvement_required": (item["sections"], item["page_limit"]) in REQUIRED_IMPROVEMENTS}
        passed = ratio <= MAX_WALL_RATIO and (not limits["strict_improvement_required"] or ratio < 1)
        configurations.append({"id": item["id"], "sections": item["sections"], "page_limit": item["page_limit"],
            "wall": wall, "process_cpu": cpu, "criteria": limits, "passed": passed,
            "regressing_wall_pairs": [index for index, value in enumerate(wall["paired_candidate_over_baseline"]) if value > 1],
            "regressing_cpu_pairs": [index for index, value in enumerate(cpu["paired_candidate_over_baseline"]) if value > 1]})
        if not passed:
            violations.append(item["id"])
    return {"passed": not violations, "violations": violations, "configurations": configurations,
            "basis": "Median of all four paired wall ratios; CPU never overrides wall acceptance. All regressions remain recorded."}


def audit_directory(work, manifest, run):
    report = read(work / "reports/directory-runtime.json")
    events = [json.loads(line) for line in (work / "reports/directory-runtime.events.jsonl").read_text().splitlines()]
    require(report["protocol"] == PROTOCOL and report["status"] == "completed"
            and report["protocol_parameters_match"] is True and report["native_backend_loaded"] is False, "Directory run is incomplete or differs")
    require(report["sources"]["baseline"]["commit"] == BASELINE and report["sources"]["candidate"]["head"] == run["commit"]
            and report["sources"]["candidate"]["source_status"] == "", "Directory source identity differs")
    for arm in ("baseline", "candidate"):
        require(report["sources"][arm]["source_sha256"] == shared.source_hash(manifest, arm, "src/memory_book/store.py"), "Directory source hash differs")
    require(report["sources"]["harness_sha256"] == shared.source_hash(manifest, "candidate", HARNESS)
            and report["sources"]["protocol_sha256"] == shared.source_hash(manifest, "candidate", PLAN), "Directory evaluator hash differs")
    require(report["arguments"]["rounds"] == 4 and report["arguments"]["iterations"] == 20
            and report["arguments"]["baseline_commit"] == BASELINE and report["arguments"]["validate_only"] is False, "Directory arguments differ")
    require(report["environment"]["github_run_id"] == run["id"] and report["environment"]["github_run_attempt"] == "1", "Directory run/attempt differs")
    require(report["fixture"]["sha256"] == FIXTURE_SHA256 and report["fixture"]["target_sections"] == 100
            and report["fixture"]["target_pages_per_section"] == {"minimum": 130, "maximum": 130}, "Frozen directory fixture differs")
    require([(item["sections"], item["page_limit"]) for item in report["configurations"]]
            == [(sections, pages) for sections in (1, 20, 100) for pages in (1, 20, 100)], "Directory matrix differs")
    expected = [{"event": "started", "arguments": report["arguments"]}]
    for item in report["configurations"]:
        audits = item["audit"]
        require(item["exact_equality"] is True and audits["baseline"]["output_sha256"] == audits["candidate"]["output_sha256"], "Directory equality differs")
        for arm in ("baseline", "candidate"):
            audit = audits[arm]
            require(audit["materialized_previews"] == audit["content_length_evaluations"] == item["sections"] * item["page_limit"],
                    "Directory materialization exceeds the returned previews")
            require(audit["select_count"] == sum(sql.lstrip().upper().startswith("SELECT") for sql in audit["statements"])
                    == (3 + 3 * item["sections"] if arm == "baseline" else 4 + item["sections"])
                    and audit["statement_count"] == len(audit["statements"]), "Directory formal-2 SQL counts differ")
        expected.append({"event": "audit", "configuration": item["id"], "audit": audits})
        require([trial["round"] for trial in item["rounds"]] == list(range(4)), "Directory rounds are incomplete")
        for trial in item["rounds"]:
            order = ["baseline", "candidate"] if trial["round"] % 2 == 0 else ["candidate", "baseline"]
            require(trial["order"] == order and set(trial["arms"]) == set(order), "Directory arm order differs")
            for position, arm in enumerate(order):
                require([row["call"] for row in trial["arms"][arm]] == list(range(20)), "Directory calls are incomplete")
                for row in trial["arms"][arm]:
                    require(row["exact_equality"] is True and "error" not in row and row["output_sha256"] == audits[arm]["output_sha256"]
                            and all(type(row[metric]) is int and row[metric] > 0 for metric in ("wall_ns", "process_cpu_ns")), "Directory observation differs")
                    expected.append({"event": "call", "configuration": item["id"], "round": trial["round"], "order_position": position, "arm": arm, **row})
            expected.append({"event": "round_completed", "configuration": item["id"], "round": trial["round"]})
        for metric in ("wall_ns", "process_cpu_ns"):
            require(item["summary"][metric] == summarize(item, metric), "Directory summary differs from raw observations")
    expected.append({"event": "completed", "configurations": 9})
    require(events == expected, "Directory event ledger differs or is incomplete")
    return {"state": "complete", "configurations": 9, "timed_calls": 1440, "events": len(events), "acceptance": acceptance(report)}


def audit_snapshot(work, run, outcomes):
    result = {"state": "incomplete", "remeasured_calls": 0, "errors": []}
    try:
        manifest = verify_frozen(work, run)
        result["directory"] = audit_directory(work, manifest, run)
        if all(outcomes.get(name) == "success" for name in STEPS):
            result["state"] = "accepted" if result["directory"]["acceptance"]["passed"] else "rejected"
    except Exception as error:
        result["errors"].append(shared.failure(error))
    return result


def preserve():
    run = identity()
    work, preservation = ROOT / WORK_PATH, ROOT / PRESERVATION_PATH
    destination = preservation / "evidence"
    destination.mkdir(parents=True, exist_ok=False)
    outcomes = {name: os.environ.get("DIRECTORY_V2_" + name.upper() + "_OUTCOME", "unavailable") for name in STEPS}
    branch = "validation/evidence-comprehensive-v010-directory-v2-" + run["id"] + "-1"
    checkpoint = {"stage": "collecting", "branch": branch, "source_run": run}
    try:
        originals = shared.collect(work, destination)
        recovered = {}
        if not (work / "source-manifest.json").exists():
            recovered = {"recorded_after_failure": True, "files": {}}
            try:
                shared.freeze_tree(destination / "recovered-inputs", "candidate", run["commit"],
                                   ("src/memory_book", "tests", *EVALUATOR_PATHS), recovered["files"])
            except Exception as error:
                recovered["error"] = shared.failure(error)
        audit = audit_snapshot(destination / "raw", run, outcomes)
        try:
            shared.clean_source()
            verify_frozen(work, run, check_worktree=True)
        except Exception as error:
            audit["state"] = "incomplete"
            audit["errors"].append({"stage": "final-source-check", **shared.failure(error)})
        shared.write_new(destination / "audit.json", shared.encoded(audit))
        shared.write_new(destination / "evidence-manifest.json", shared.encoded({"protocol": PROTOCOL, "repository": REPOSITORY,
            "source_run": run, "evidence_branch": branch, "workflow_steps": outcomes, "original_files": originals,
            "recovered_inputs": recovered, "audit": audit, "previous_evidence_commit": "780a99faa71da50eb0bf6e290fddc765e2b49b43"}))
        shared.write_new(destination / "README.md", (f"# Directory formal-2 evidence\n\nRun {run['id']}, attempt 1, source `{run['commit']}`.\n"
            f"Audit and prospective acceptance: **{audit['state']}**. All original observations, including regressions and failures, are retained.\n\n"
            "The rejected five-SELECT candidate remains at evidence commit `780a99faa71da50eb0bf6e290fddc765e2b49b43`.\n"
            "This comparison uses the same frozen fixture, nine configurations and four balanced rounds, with no semantic rerun.\n"
            "Acceptance requires every median paired wall ratio <= 1.05 and strict improvement for 20x20 and 100x20.\n"
            "Process CPU does not override wall latency. This is component evidence, with no universal or end-to-end speed claim.\n"
            "`evidence-manifest.json` hashes every original raw byte. The frozen auditor never remeasures a call.\n").encode())
        checkpoint.update(stage="publishing", audit=audit)
        checkpoint.update(stage="completed", **shared.publish(destination, branch))
        print(json.dumps(checkpoint), flush=True)
        require(audit["state"] == "accepted", "Evidence preserved, but directory formal-2 acceptance failed; inspect the retained result")
    except BaseException as error:
        checkpoint["error"] = shared.failure(error)
        raise
    finally:
        shared.write_new(preservation / "preservation-result.json", shared.encoded(checkpoint))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "check", "preserve"))
    {"freeze": freeze, "check": check, "preserve": preserve}[parser.parse_args(argv).command]()


if __name__ == "__main__":
    main()
