"""One sequential hosted comparison; publish every completed or failed stage.

The committed manifest must already exist. This controller never selects IDs,
retries a worker, resumes another host, or rewrites a prior experiment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round3_comparison as comparison
from scripts.run_round2_validation import execute
from benchmarks.prepare_native_data import checked_download
from benchmarks.round2_resources import storage

TRIGGER = "refs/heads/ci/v031-round3-comparison-run"
REPOSITORY = "Afloat16/AI-Memory-Book"


def git(*args, cwd=None, env=None, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT if cwd is None else cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=120)
    if check:
        comparison.require(result.returncode == 0, "Git operation failed; credential-bearing diagnostics omitted")
        return result.stdout.decode().strip()
    return result


def actions_identity():
    identity, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    comparison.require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == TRIGGER and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and identity.isdigit() and attempt == "1", "Require the authorized push branch and first Actions attempt")
    comparison.require(os.environ.get("ORT_DISABLE_TELEMETRY") == "1", "Disable ORT telemetry before the controller starts")
    return identity + "-" + attempt


def authorized_origin():
    comparison.require(git("remote", "get-url", "origin") in (
        "https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git",
        "git@github.com:Afloat16/AI-Memory-Book.git"), "Unauthorized publication origin")


def safe_names(paths):
    names = []
    for path in paths:
        path = Path(path)
        comparison.require(path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to((ROOT / "benchmarks").resolve()), "Only regular public artifacts may be committed")
        names.append(str(path.relative_to(ROOT)))
    return sorted(names)


def public_commit(paths, parent, message):
    names = safe_names(paths)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        environment = {**os.environ, "GIT_INDEX_FILE": str(directory / "index")}
        git("read-tree", parent, env=environment)
        git("add", "--", *names, env=environment)
        tree = git("write-tree", env=environment)
        body = directory / "message"
        body.write_text(message + "\n")
        return git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit-tree", tree, "-p", parent, "-F", str(body), env=environment)


def claim(binding_path, source, run_id, manifest_path):
    """A dedicated immutable branch prevents another push from rescoring one binding."""
    comparison.require(actions_identity() == run_id, "Execution claim run identity differs")
    authorized_origin()
    fingerprint = comparison.file_sha(binding_path)
    branch = "refs/heads/validation/round3-comparison-claim-" + fingerprint
    comparison.require(not git("ls-remote", "--heads", "origin", branch),
        "This binding already has an execution claim; no implicit new run is allowed")
    path = ROOT / "benchmarks/reports" / ("round3-comparison-claim-" + fingerprint + ".json")
    comparison.require(not path.exists(), "Preserve the existing execution claim")
    comparison.reused.atomic(path, {"schema_version": 1, "status": "claimed-before-preparation",
        "run_id": run_id, "source_commit": source, "binding_sha256": fingerprint,
        "cohort_manifest_sha256": comparison.file_sha(manifest_path), "claimed_at": comparison.reused.now(),
        "policy": "One registered execution. Any explicit recovery must preserve this attempt and use a separately registered binding."})
    commit = public_commit([path], source, "bench: claim one frozen round-three comparison execution")
    # Simultaneous claims have the same source parent and different run IDs, so
    # the second non-force push cannot fast-forward the first claim commit.
    git("push", "origin", commit + ":" + branch)
    return commit, path


def publish(checkpoint_path, result_dir, binding, parent, run_id):
    comparison.require(actions_identity() == run_id, "Publication run identity differs")
    authorized_origin()
    branch = "refs/heads/validation/round3-comparison-" + run_id
    expected = [checkpoint_path]
    for stage in comparison.stages(binding):
        expected.extend(path for path in comparison.public_paths(result_dir / stage) if path.is_file())
    expected.extend(path for name in ("assessment.json", "report.md") if (path := result_dir / name).is_file())
    current = git("ls-remote", "--heads", "origin", branch)
    comparison.require(not current or current.split()[0] == parent, "Another writer advanced this result branch; never force push")
    commit = public_commit(expected, parent, "bench: preserve round-three component stage and audit")
    git("push", "origin", commit + ":" + branch)
    return commit


def snapshot(path, commit):
    comparison.require(re.fullmatch("[0-9a-f]{40}", commit) and not path.exists(), "Require a fresh exact source checkout")
    if git("cat-file", "-e", commit + "^{commit}", check=False).returncode:
        git("fetch", "--no-tags", "origin", commit)
    git("worktree", "add", "--no-checkout", "--detach", str(path), commit)
    git("sparse-checkout", "set", "--cone", "src", cwd=path)
    git("read-tree", "-mu", commit, cwd=path)


def prepare(directory, binding, checkpoint, persist):
    def measured(name, function, location):
        record = {"status": "running", "started_at": comparison.reused.now(), "preexisting_storage": storage(location)}
        checkpoint["preparation"][name] = record
        persist()
        begin = time.perf_counter_ns()
        try:
            value = function()
            record["status"] = "completed"
            return value
        except BaseException as error:
            record.update(status="failed", error_type=type(error).__name__,
                failure=comparison.failure_diagnostic(error, stage="preparation:" + name,
                                                      check="preparation_exception"))
            raise
        finally:
            record.update(wall_ms=(time.perf_counter_ns() - begin) / 1e6,
                finished_at=comparison.reused.now(), prepared_storage=storage(location))
            persist()
    private = directory / "private"
    private.mkdir()
    data = private / "hotpot-dev-distractor.parquet"
    source = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
    measured("verified_parquet_download", lambda: checked_download(source["source_url"], data,
        source["upstream_sha256"], source["upstream_bytes"]), private)
    cache = directory / "cache"
    os.environ["TIKTOKEN_CACHE_DIR"] = str(directory / "tokenizers")
    measured("reference_tokenizers", comparison.counters_for, directory / "tokenizers")
    from benchmarks.competitors.ai_memory import prepare as ai_binary, prepare_models
    from benchmarks.competitors.claude_mem import prepare as claude
    from benchmarks.competitors.billion import prepare as billion
    measured("ai_memory_binary_and_local_model", lambda: (ai_binary(cache / "ai-memory"),
        prepare_models(cache / "ai-memory")), cache / "ai-memory")
    measured("claude_mem_source_and_bun", lambda: claude(cache / "claude-mem",
        lock_path=ROOT / binding["upstream_locks"]["claude-mem"]), cache / "claude-mem")
    measured("billion_context_search_kernel", lambda: billion(cache / "billion-context",
        lock_path=ROOT / binding["upstream_locks"]["billion-context"]), cache / "billion-context")
    model = directory / "semantic-model"
    def prepare_model():
        subprocess.run([sys.executable, "scripts/prepare_semantic_model.py", "--output", str(model)],
            cwd=ROOT, stdout=subprocess.DEVNULL, check=True, timeout=600)
        comparison.verify_model(model, binding["model"]["identity"])
    measured("book_semantic_model", prepare_model, model)
    return data, cache, model


def run(args):
    run_id = actions_identity()
    plan, binding = comparison.frozen_inputs(args.binding)
    from scripts.round3_data import registered_inputs
    registered_inputs(args.binding)  # Check source/model/old/new evaluator identities without reading questions.
    comparison.require_committed(args.manifest)
    manifest = json.loads(args.manifest.read_bytes())
    comparison.require(manifest["binding_sha256"] == comparison.file_sha(args.binding), "Selection belongs to another binding")
    directory = ROOT / ".artifacts/round3-comparison" / run_id
    result_dir = ROOT / "benchmarks/results" / ("round3-comparison-" + run_id)
    checkpoint_path = ROOT / "benchmarks/reports" / ("round3-comparison-" + run_id + "-checkpoint.json")
    comparison.require(not directory.exists() and not result_dir.exists() and not checkpoint_path.exists(),
                       "Never replay an existing run or overwrite its public artifacts")
    comparison.require(args.wall_time_seconds >= 300, "Reserve sufficient measurement and publication time")
    directory.mkdir(parents=True)
    source = git("rev-parse", "HEAD")
    comparison.require(source == os.environ.get("GITHUB_SHA"), "Checkout must equal the immutable triggering source SHA")
    parent, claim_path = claim(args.binding, source, run_id, args.manifest)
    checkpoint = {"schema_version": 1, "protocol": plan["protocol"], "run_id": run_id,
        "status": "running", "source_commit": source, "claim_commit": parent,
        "claim_path": str(claim_path.relative_to(ROOT)), "started_at": comparison.reused.now(),
        "host": comparison.host_record(), "plan_sha256": comparison.file_sha(comparison.PLAN),
        "binding_sha256": comparison.file_sha(args.binding), "cohort_manifest_sha256": comparison.file_sha(args.manifest),
        "result_directory": str(result_dir.relative_to(ROOT)), "preparation": {}, "stages": {}}
    deadline = time.monotonic() + args.wall_time_seconds
    def persist():
        nonlocal parent
        comparison.reused.atomic(checkpoint_path, checkpoint)
        parent = publish(checkpoint_path, result_dir, binding, parent, run_id)
    success = False
    try:
        persist()
        baseline, candidate = directory / "baseline", directory / "candidate"
        snapshot(baseline, binding["baseline"]["commit"])
        snapshot(candidate, binding["candidate"]["commit"])
        data, cache, model = prepare(directory, binding, checkpoint, persist)
        bundle, frozen_db = directory / "frozen-pages.json", directory / "states/export/frozen.db"
        for stage in comparison.stages(binding):
            state, prefix = directory / "states" / stage, result_dir / stage
            command = [sys.executable, "-u", "scripts/round3_comparison.py", "worker", "--stage", stage,
                "--binding", str(args.binding), "--manifest", str(args.manifest), "--data", str(data),
                "--bundle", str(bundle), "--frozen-db", str(frozen_db), "--state", str(state), "--cache", str(cache),
                "--model-dir", str(model), "--output", str(prefix), "--host-id", checkpoint["host"]["id"]]
            if stage == "export" or stage.startswith("baseline-"):
                command += ["--source", str(baseline / "src")]
            elif stage.startswith("candidate-"):
                command += ["--source", str(candidate / "src")]
            record = {"status": "running", "started_at": comparison.reused.now(), "argv": command}
            checkpoint["stages"][stage] = record
            persist()
            try:
                code = execute(command, deadline - time.monotonic() - 120, directory / (stage + ".log"))
                record.update(status="completed" if code == 0 else "failed", exit_code=code)
            except BaseException as error:
                record.update(status="interrupted", error_type=type(error).__name__,
                    failure=comparison.failure_diagnostic(error, stage=stage, check="stage_execution_exception"))
                raise
            finally:
                comparison.save_ledger(state, prefix)
                record.update(finished_at=comparison.reused.now(), outputs={str(path.relative_to(ROOT)): comparison.file_sha(path)
                    for path in comparison.public_paths(prefix) if path.is_file()})
                persist()  # No later worker until the previous raw/summary/ledger bytes are durably committed.
            comparison.require(record["status"] == "completed", "A measured stage failed; no retry or later stage")
        checkpoint["status"] = "measurements-complete-awaiting-assessment"
        persist()
        assessment = comparison.assess(checkpoint_path, args.binding, args.manifest)
        checkpoint["assessment_outputs"] = {str(path.relative_to(ROOT)): comparison.file_sha(path)
            for name in ("assessment.json", "report.md") if (path := result_dir / name).is_file()}
        checkpoint["status"] = assessment["status"]
        checkpoint["assessment_exit_code"] = 0 if assessment["status"] == "complete-verified" else 2
        success = checkpoint["assessment_exit_code"] == 0
    except BaseException as error:
        checkpoint.update(status="failed-incomplete", error_type=type(error).__name__,
            failure=comparison.failure_diagnostic(error, stage="controller", check="controller_exception"))
    finally:
        checkpoint["finished_at"] = comparison.reused.now()
        persist()
    print(json.dumps({"status": checkpoint["status"], "checkpoint": str(checkpoint_path.relative_to(ROOT)),
        "completed_stages": sum(record["status"] == "completed" for record in checkpoint["stages"].values())}))
    return 0 if success else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, default=comparison.BINDING)
    parser.add_argument("--manifest", type=Path, default=comparison.MANIFEST)
    parser.add_argument("--wall-time-seconds", type=int, default=10800)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except BaseException as error:
        comparison.failure_diagnostic(error, stage="controller", check="controller_boundary_exception")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
