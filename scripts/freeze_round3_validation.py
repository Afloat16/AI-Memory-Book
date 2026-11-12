"""Freeze round-three identities and ID-only selection without scoring a question.

The existing comparison controller is deliberately launched in a later,
separate GitHub push. This preparation never invokes a retrieval worker.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round3_comparison as comparison
from scripts import round3_data
from scripts.run_round3_comparison import snapshot
from benchmarks.prepare_native_data import checked_download
from benchmarks.round2_resources import storage

PLAN = ROOT / "benchmarks/experiments/round3-freeze-plan.json"
TRIGGER = "refs/heads/ci/v031-round3-freeze-run"
REPOSITORY = "Afloat16/AI-Memory-Book"


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=180)
    if check:
        require(result.returncode == 0, "Git operation failed: " + args[0])
        return result.stdout.decode().strip()
    return result


def commit_and_publish(paths, branch, expected_parent, message):
    require(git("rev-parse", "HEAD") == expected_parent, "Unexpected checkout head")
    current = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    require(not current or current.split()[0] == expected_parent,
            "Another writer advanced the preparation branch")
    names = []
    for path in paths:
        path = Path(path).resolve()
        require(path.is_relative_to((ROOT / "benchmarks").resolve())
                and path.is_file() and not path.is_symlink(), "Unsafe public artifact")
        names.append(str(path.relative_to(ROOT)))
    require(names, "No public artifacts to preserve")
    git("add", "--", *sorted(names))
    git("-c", "user.name=github-actions[bot]", "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", message)
    head = git("rev-parse", "HEAD")
    git("push", "origin", head + ":refs/heads/" + branch)
    return head


def main():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == TRIGGER
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
        "Require the dedicated first-attempt preparation push")
    require(os.environ.get("ORT_DISABLE_TELEMETRY") == "1", "Disable model telemetry")
    run_id = os.environ["GITHUB_RUN_ID"]
    require(run_id.isdigit(), "Invalid workflow run identity")
    source = git("rev-parse", "HEAD")
    require(source == os.environ["GITHUB_SHA"], "Checkout differs from triggering commit")
    require(git("remote", "get-url", "origin") in (
        "https://github.com/Afloat16/AI-Memory-Book",
        "https://github.com/Afloat16/AI-Memory-Book.git"), "Unexpected publication origin")
    comparison.require_committed(PLAN)
    plan = json.loads(PLAN.read_bytes())
    require(plan["baseline_commit"] == comparison.BASELINE["commit"]
        and re.fullmatch("[0-9a-f]{40}", plan["candidate_commit"])
        and plan["optional_project_statistics"] is False, "Unexpected frozen source axes")
    require(not comparison.BINDING.exists() and not comparison.MANIFEST.exists(),
            "Never replace a prior binding or selection")
    comparison.registered_plan()
    comparison.evaluator_files()
    decision = plan["quality_decision"]
    require(re.fullmatch("[0-9a-f]{40}", decision["commit"])
        and decision["path"].startswith("benchmarks/reports/")
        and ".." not in Path(decision["path"]).parts, "Unsafe quality evidence reference")
    if git("cat-file", "-e", decision["commit"] + "^{commit}", check=False).returncode:
        git("fetch", "--no-tags", "origin", decision["commit"])
    decision_ref = decision["commit"] + ":" + decision["path"]
    require(git("rev-parse", decision_ref) == decision["git_blob_sha"],
            "Quality decision differs from its restored evidence")
    decision_raw = subprocess.check_output(["git", "show", decision_ref], cwd=ROOT, timeout=30)
    quality = json.loads(decision_raw)
    require(quality["validation_passed"] is True and quality["calls"] == 8082
        and quality["workers"] == 8 and quality["qualified"] is False
        and quality["new_measurement_calls"] == 0
        and quality["original_evaluator_audit"] == "passed",
        "The excluded optional candidate lacks its full audited rejection")
    installed = {name: importlib.metadata.version(name) for name in comparison.PACKAGES}
    require(installed == comparison.PACKAGES, "Preparation dependencies differ from registered pins")
    public = ROOT / "benchmarks/reports" / ("round3-freeze-" + run_id + "-1")
    private = ROOT / ".artifacts" / ("round3-freeze-" + run_id + "-1")
    require(not public.exists() and not private.exists(), "Preserve the existing attempt")
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    branch = "validation/v031-round3-frozen-" + run_id + "-1"
    require(not git("ls-remote", "--heads", "origin", "refs/heads/" + branch),
            "Preparation branch already exists")
    parent = source
    record = {"schema_version": 1, "status": "preparation-running",
        "run_id": run_id, "trigger_commit": source, "prepared_branch": branch,
        "started_at": comparison.reused.now(), "packages": installed, "stages": {},
        "measurement_calls": 0, "policy": "Preparation and ID-only freeze; no scoring, no timing claims."}
    status = public / "completion.json"

    def measured(name, function, location):
        item = {"status": "running", "started_at": comparison.reused.now()}
        record["stages"][name] = item
        start = time.perf_counter_ns()
        try:
            value = function()
            item["status"] = "completed"
            return value
        except BaseException as error:
            item.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            item.update(finished_at=comparison.reused.now(),
                wall_ms=(time.perf_counter_ns() - start) / 1e6, storage=storage(location))

    try:
        baseline, candidate = private / "baseline", private / "candidate"
        measured("baseline_source", lambda: snapshot(baseline, plan["baseline_commit"]), baseline)
        measured("candidate_source", lambda: snapshot(candidate, plan["candidate_commit"]), candidate)
        sources = {name: comparison.source_identity(path / "src")
                   for name, path in (("baseline", baseline), ("candidate", candidate))}
        require(sources["candidate"]["source_sha256"] == plan["candidate_runtime_sha256"],
                "Candidate differs from the completed performance measurement")
        model = private / "semantic-model"

        def prepare_model():
            subprocess.run([sys.executable, "scripts/prepare_semantic_model.py", "--output", str(model)],
                           cwd=ROOT, check=True, timeout=600)
            comparison.verify_model(model, comparison.model_identity())
        measured("verified_book_model", prepare_model, model)
        cache = private / "upstream"
        from benchmarks.competitors.ai_memory import prepare as ai_binary, prepare_models
        from benchmarks.competitors.claude_mem import prepare as claude
        from benchmarks.competitors.billion import prepare as billion
        locks = comparison.reused.UPSTREAM_LOCKS
        measured("verified_ai_memory_binary_and_models",
            lambda: (ai_binary(cache / "ai-memory"), prepare_models(cache / "ai-memory")),
            cache / "ai-memory")
        measured("verified_claude_mem_sources_and_bun",
            lambda: claude(cache / "claude-mem", lock_path=ROOT / locks["claude-mem"]),
            cache / "claude-mem")
        measured("verified_billion_kernel_sources",
            lambda: billion(cache / "billion-context", lock_path=ROOT / locks["billion-context"]),
            cache / "billion-context")
        preflight = public / "asset-verification.json"
        comparison.reused.atomic(preflight, {"schema_version": 1,
            "status": "all-assets-verified-before-selection", "sources": sources,
            "model": comparison.model_identity(), "packages": installed,
            "upstream_locks_sha256": {name: comparison.file_sha(ROOT / path) for name, path in locks.items()},
            "preparation": record["stages"], "verified_at": comparison.reused.now(),
            "quality_decision": {**decision, "sha256": comparison.sha(decision_raw)},
            "question_content_read": False, "measurement_calls": 0})
        parent = commit_and_publish([preflight], branch, parent,
            "bench: verify round-three assets before binding or selection")
        command = [sys.executable, "scripts/round3_comparison.py", "bind",
            "--baseline-src", str(baseline / "src"), "--candidate-src", str(candidate / "src"),
            "--model-dir", str(model)]
        for extra in ("scripts/freeze_round3_validation.py",
                      ".github/workflows/round3-freeze.yml",
                      "benchmarks/experiments/round3-freeze-plan.json",
                      str(preflight.relative_to(ROOT))):
            command += ["--extra-evaluator", extra]
        subprocess.run(command, cwd=ROOT, check=True, timeout=180)
        parent = commit_and_publish([comparison.BINDING], branch, parent,
            "bench: freeze exact round-three runtime and evaluator before new IDs")
        comparison.frozen_inputs()
        source_data = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
        parquet = private / "hotpot-dev-distractor.parquet"
        measured("verified_parquet_download",
            lambda: checked_download(source_data["source_url"], parquet,
                source_data["upstream_sha256"], source_data["upstream_bytes"]), parquet)
        manifest = round3_data.freeze(parquet, comparison.BINDING)
        record.update(status="frozen-not-scored", binding_commit=parent,
            binding_sha256=comparison.file_sha(comparison.BINDING),
            manifest_sha256=comparison.file_sha(comparison.MANIFEST),
            expected_queries=manifest["expected_queries"],
            prior_selection_overlap=manifest["prior_selection_overlap"],
            selected_ids_sha256=manifest["selected_ids_sha256"],
            finished_at=comparison.reused.now())
        comparison.reused.atomic(status, record)
        parent = commit_and_publish([comparison.MANIFEST, status], branch, parent,
            "bench: freeze 256 disjoint ID-selected questions before round-three scoring")
        round3_data.load(parquet, comparison.BINDING)
        print(json.dumps({"status": record["status"], "prepared_branch": branch,
                          "commit": parent, "queries": manifest["expected_queries"],
                          "measurement_calls": 0}))
        return 0
    except BaseException as error:
        record.update(status="failed-before-scoring", error_type=type(error).__name__,
                      finished_at=comparison.reused.now())
        comparison.reused.atomic(status, record)
        commit_and_publish([status], branch, parent,
            "bench: preserve round-three preparation failure without scoring")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
