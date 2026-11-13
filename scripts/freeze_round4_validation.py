"""Freeze round-four identities and ID-only selection without scoring a question.

The existing comparison controller is deliberately launched in a later,
separate GitHub push. This preparation never invokes a retrieval worker.
"""
from __future__ import annotations

import argparse
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
from scripts import round4_comparison as comparison
from scripts import round4_data
from scripts.run_round4_comparison import public_commit, snapshot
from benchmarks.prepare_native_data import checked_download
from benchmarks.round2_resources import storage

PLAN = ROOT / "benchmarks/experiments/round4-freeze-plan.json"
TRIGGER = "refs/heads/ci/v032-round4-freeze-run"
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
    head = public_commit(paths, expected_parent, message)
    git("push", "origin", head + ":refs/heads/" + branch)
    git("update-ref", "HEAD", head, expected_parent)
    return head


def requested_sources(plan, args):
    """Candidate IDs are declaration inputs, never hardcoded future commits."""
    require(plan["schema_version"] == 1
        and plan["status"] == "registered-before-new-selection-and-scoring"
        and plan["baseline_commit"] == comparison.BASELINE["commit"]
        and plan["optional_project_statistics"] is False,
        "Unexpected preparation declaration")
    candidate = args.candidate_commit or plan["candidate_commit"]
    fingerprint = args.candidate_runtime_sha256 or plan["candidate_runtime_sha256"]
    require(isinstance(candidate, str) and re.fullmatch("[0-9a-f]{40}", candidate)
        and isinstance(fingerprint, str) and re.fullmatch("[0-9a-f]{64}", fingerprint),
        "Provide the exact accepted candidate commit and runtime SHA-256 before preparation")
    require(plan["candidate_commit"] in (None, candidate)
        and plan["candidate_runtime_sha256"] in (None, fingerprint),
        "CLI candidate differs from the committed preparation declaration")
    return {**plan, "candidate_commit": candidate, "candidate_runtime_sha256": fingerprint}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--candidate-runtime-sha256")
    parser.add_argument("--evaluator-commit", help="Assert the exact triggering evaluator checkout")
    args = parser.parse_args(argv)
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
    plan = requested_sources(json.loads(PLAN.read_bytes()), args)
    require(args.evaluator_commit in (None, source), "Evaluator checkout differs from the declared commit")
    require(not comparison.BINDING.exists() and not comparison.MANIFEST.exists(),
            "Never replace a prior binding or selection")
    comparison.registered_plan()
    comparison.evaluator_files()
    installed = {name: importlib.metadata.version(name) for name in comparison.PACKAGES}
    require(installed == comparison.PACKAGES, "Preparation dependencies differ from registered pins")
    node = subprocess.check_output(["node", "--version"], timeout=30).decode().strip()
    require(sys.version_info[:2] == (3, 12) and node == "v24.22.1", "Preparation language runtimes differ")
    public = ROOT / "benchmarks/reports" / ("round4-freeze-" + run_id + "-1")
    private = ROOT / ".artifacts" / ("round4-freeze-" + run_id + "-1")
    require(not public.exists() and not private.exists(), "Preserve the existing attempt")
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    branch = "validation/v032-round4-frozen-" + run_id + "-1"
    require(not git("ls-remote", "--heads", "origin", "refs/heads/" + branch),
            "Preparation branch already exists")
    parent = source
    record = {"schema_version": 1, "status": "preparation-running",
        "run_id": run_id, "trigger_commit": source, "prepared_branch": branch,
        "started_at": comparison.reused.now(), "packages": installed, "stages": {},
        "measurement_calls": 0, "policy": "Preparation and ID-only freeze; no scoring, no timing claims."}
    status = public / "completion.json"

    def persist():
        nonlocal parent
        comparison.reused.atomic(status, record)
        parent = commit_and_publish([status], branch, parent,
            "bench: preserve round-four preparation progress before selection")

    def measured(name, function, location):
        item = {"status": "running", "started_at": comparison.reused.now()}
        record["stages"][name] = item
        persist()
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
            persist()

    try:
        persist()
        baseline, candidate = private / "baseline", private / "candidate"
        measured("baseline_source", lambda: snapshot(baseline, plan["baseline_commit"]), baseline)
        measured("candidate_source", lambda: snapshot(candidate, plan["candidate_commit"]), candidate)
        sources = {name: comparison.source_identity(path / "src")
                   for name, path in (("baseline", baseline), ("candidate", candidate))}
        require(sources["candidate"]["source_sha256"] == plan["candidate_runtime_sha256"],
                "Candidate differs from the declared runtime identity")
        require(sources["baseline"] == comparison.BASELINE, "Baseline source differs from published v0.3.1")
        os.environ["TIKTOKEN_CACHE_DIR"] = str(private / "tokenizers")
        measured("verified_reference_tokenizers", comparison.counters_for, private / "tokenizers")
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
            "language_runtimes": {"python": sys.version.split()[0], "node": node},
            "upstream_locks_sha256": {name: comparison.file_sha(ROOT / path) for name, path in locks.items()},
            "preparation": record["stages"], "verified_at": comparison.reused.now(),
            "trigger_commit": source, "preparation_plan_sha256": comparison.file_sha(PLAN),
            "question_content_read": False, "measurement_calls": 0})
        parent = commit_and_publish([preflight], branch, parent,
            "bench: verify round-four assets before binding or selection")
        command = [sys.executable, "scripts/round4_comparison.py", "bind",
            "--baseline-src", str(baseline / "src"), "--candidate-src", str(candidate / "src"),
            "--model-dir", str(model), "--asset-verification", str(preflight),
            "--evaluator-commit", parent]
        for extra in ("scripts/freeze_round4_validation.py",
                      ".github/workflows/round4-freeze.yml",
                      "benchmarks/experiments/round4-freeze-plan.json",
                      str(preflight.relative_to(ROOT))):
            command += ["--extra-evaluator", extra]
        subprocess.run(command, cwd=ROOT, check=True, timeout=180)
        parent = commit_and_publish([comparison.BINDING], branch, parent,
            "bench: freeze exact round-four runtime and evaluator before new IDs")
        binding_commit = parent
        comparison.frozen_inputs()
        source_data = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
        input_directory = private / "input"
        input_directory.mkdir()
        parquet = input_directory / "hotpot-dev-distractor.parquet"
        measured("verified_parquet_download",
            lambda: checked_download(source_data["source_url"], parquet,
                source_data["upstream_sha256"], source_data["upstream_bytes"]), input_directory)
        manifest = round4_data.freeze(parquet, comparison.BINDING)
        record.update(status="frozen-not-scored", binding_commit=binding_commit,
            binding_sha256=comparison.file_sha(comparison.BINDING),
            manifest_sha256=comparison.file_sha(comparison.MANIFEST),
            expected_queries=manifest["expected_queries"],
            prior_selection_overlap=manifest["prior_selection_overlap"],
            selected_ids_sha256=manifest["selected_ids_sha256"],
            finished_at=comparison.reused.now())
        comparison.reused.atomic(status, record)
        parent = commit_and_publish([comparison.MANIFEST, status], branch, parent,
            "bench: freeze 256 disjoint ID-selected questions before round-four scoring")
        round4_data.load(parquet, comparison.BINDING)
        print(json.dumps({"status": record["status"], "prepared_branch": branch,
                          "commit": parent, "queries": manifest["expected_queries"],
                          "measurement_calls": 0}))
        return 0
    except BaseException as error:
        record.update(status="failed-before-scoring", error_type=type(error).__name__,
                      finished_at=comparison.reused.now())
        comparison.reused.atomic(status, record)
        commit_and_publish([status], branch, parent,
            "bench: preserve round-four preparation failure without scoring")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
