"""Publish freeze before selection; run one sequential, durable fresh comparison.

The freeze and comparison have separate authorized push branches. No scoring
occurs in freeze. Every measured stage requires a committed execution intent;
failed/incomplete stages are retained and never automatically retried.
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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round6_comparison as comparison
from scripts import round6_comparison_data as data_loader
from scripts.run_round2_validation import execute
from benchmarks.prepare_native_data import checked_download
from benchmarks.round2_resources import storage

TRIGGER = comparison.TRIGGER
REPOSITORY = comparison.REPOSITORY


def git(*args, cwd=None, env=None, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT if cwd is None else cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=120)
    if check:
        comparison.require(result.returncode == 0, "Git operation failed; credential-bearing diagnostics omitted")
        return result.stdout.decode().strip()
    return result


def actions_identity(phase="run"):
    identity, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    comparison.require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and phase in ("run", "freeze")
        and os.environ.get("GITHUB_REF") == (TRIGGER if phase == "run" else comparison.FREEZE_TRIGGER) and os.environ.get("GITHUB_EVENT_NAME") == "push"
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
    branch = "refs/heads/validation/round6-comparison-claim-" + fingerprint
    comparison.require(not git("ls-remote", "--heads", "origin", branch),
        "This binding already has an execution claim; no implicit new run is allowed")
    path = ROOT / "benchmarks/reports" / ("round6-comparison-claim-" + fingerprint + ".json")
    comparison.require(not path.exists(), "Preserve the existing execution claim")
    comparison.reused.atomic(path, {"schema_version": 1, "status": "claimed-before-preparation",
        "run_id": run_id, "source_commit": source, "binding_sha256": fingerprint,
        "cohort_manifest_sha256": comparison.file_sha(manifest_path), "claimed_at": comparison.reused.now(),
        "policy": "One registered execution. Any explicit recovery must preserve this attempt and use a separately registered binding."})
    commit = public_commit([path], source, "bench: claim one frozen round-six comparison execution")
    # Simultaneous claims have the same source parent and different run IDs, so
    # the second non-force push cannot fast-forward the first claim commit.
    git("push", "origin", commit + ":" + branch)
    return commit, path


def publish(checkpoint_path, result_dir, binding, parent, run_id):
    comparison.require(actions_identity() == run_id, "Publication run identity differs")
    authorized_origin()
    branch = "refs/heads/validation/round6-comparison-" + run_id
    expected = [checkpoint_path]
    for stage in comparison.stages(binding):
        expected.extend(path for path in comparison.public_paths(result_dir / stage) if path.is_file())
    expected.extend(path for name in ("assessment.json", "report.md") if (path := result_dir / name).is_file())
    current = git("ls-remote", "--heads", "origin", branch)
    comparison.require(not current or current.split()[0] == parent, "Another writer advanced this result branch; never force push")
    commit = public_commit(expected, parent, "bench: preserve round-six component stage and audit")
    git("push", "origin", commit + ":" + branch)
    return commit


def snapshot(path, commit):
    comparison.require(re.fullmatch("[0-9a-f]{40}", commit) and not path.exists(), "Require a fresh exact source checkout")
    if git("cat-file", "-e", commit + "^{commit}", check=False).returncode:
        git("fetch", "--no-tags", "origin", commit)
    git("worktree", "add", "--no-checkout", "--detach", str(path), commit)
    git("sparse-checkout", "set", "--cone", "src", cwd=path)
    git("read-tree", "-mu", commit, cwd=path)


def prepare_assets(cache, tokenizers, measured):
    os.environ["TIKTOKEN_CACHE_DIR"] = str(tokenizers)
    measured("reference_tokenizers", comparison.legacy.counters_for, tokenizers)
    from benchmarks.competitors.ai_memory import prepare as ai_binary, prepare_models
    from benchmarks.competitors.claude_mem import prepare as claude
    from benchmarks.competitors.billion import prepare as billion
    measured("ai_memory_binary_and_models", lambda: (ai_binary(cache / "ai-memory"),
        prepare_models(cache / "ai-memory")), cache / "ai-memory")
    measured("claude_mem_sources_and_bun", lambda: claude(cache / "claude-mem",
        lock_path=ROOT / comparison.UPSTREAM_LOCKS["claude-mem"]), cache / "claude-mem")
    measured("billion_kernel_sources", lambda: billion(cache / "billion-context",
        lock_path=ROOT / comparison.UPSTREAM_LOCKS["billion-context"]), cache / "billion-context")


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
            record.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            record.update(wall_ms=(time.perf_counter_ns() - begin) / 1e6,
                finished_at=comparison.reused.now(), prepared_storage=storage(location))
            persist()
    private = directory / "private"
    private.mkdir()
    source = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
    data = private / "hotpot-dev-distractor.parquet"
    measured("verified_parquet_download", lambda: checked_download(source["source_url"], data,
        source["upstream_sha256"], source["upstream_bytes"]), private)
    cache = directory / "cache"
    prepare_assets(cache, directory / "tokenizers", measured)
    return data, cache


def freeze_claim(source, run_id, plan, sources):
    """Prevent a new push from silently creating another freeze for one declaration."""
    identity = {"sources": sources, "plan_sha256": comparison.file_sha(comparison.PLAN),
                "evaluator_files": comparison.evaluator_files()}
    fingerprint = comparison.reused.digest(identity)
    branch = "refs/heads/validation/round6-comparison-freeze-claim-" + fingerprint
    comparison.require(not git("ls-remote", "--heads", "origin", branch),
                       "This exact declaration already has a freeze claim; preserve it, no implicit retry")
    path = ROOT / "benchmarks/reports" / ("round6-comparison-freeze-claim-" + fingerprint + ".json")
    comparison.require(not path.exists(), "Preserve the original freeze claim")
    comparison.reused.atomic(path, {"schema_version": 1, "status": "claimed-before-assets-and-selection",
        "run_id": run_id, "source_commit": source, "identity": identity, "identity_sha256": fingerprint,
        "claimed_at": comparison.reused.now(), "measurement_calls": 0})
    commit = public_commit([path], source, "bench: claim one round-six asset freeze and fresh selection")
    git("push", "origin", commit + ":" + branch)
    return commit, path


def commit_and_publish(paths, branch, parent, message):
    comparison.require(git("rev-parse", "HEAD") == parent, "Unexpected preparation checkout head")
    current = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    comparison.require(not current or current.split()[0] == parent, "Another writer advanced preparation; never force push")
    commit = public_commit(paths, parent, message)
    git("push", "origin", commit + ":refs/heads/" + branch)
    git("update-ref", "HEAD", commit, parent)
    return commit


def freeze(args):
    run_id = actions_identity("freeze")
    authorized_origin()
    source = git("rev-parse", "HEAD")
    comparison.require(source == os.environ.get("GITHUB_SHA"), "Checkout differs from triggering source")
    plan = comparison.registered_plan()
    candidate = comparison.requested_candidate(plan)  # Null identities stop before any asset/data work.
    comparison.require(not comparison.BINDING.exists() and not comparison.MANIFEST.exists(), "Never replace a prior binding/selection")
    packages = {name: importlib.metadata.version(name) for name in comparison.PACKAGES}
    node = subprocess.check_output(["node", "--version"], timeout=30).decode().strip()
    comparison.require(packages == comparison.PACKAGES and sys.version_info[:2] == (3, 12)
                       and node == comparison.NODE, "Freeze dependencies/language runtimes differ")
    sources = {"baseline": comparison.BASELINE, "candidate": candidate}
    for label, identity in sources.items():
        comparison.require(comparison.runtime_hash(identity["commit"]) == identity["source_sha256"],
                           "Declared runtime differs before assets/selection: " + label)
    public = ROOT / "benchmarks/reports" / ("round6-comparison-freeze-" + run_id)
    private = ROOT / ".artifacts/round6-comparison-freeze" / run_id
    comparison.require(not public.exists() and not private.exists(), "Preserve an existing freeze attempt")
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    branch = "validation/v034-round6-comparison-frozen-" + run_id
    comparison.require(not git("ls-remote", "--heads", "origin", "refs/heads/" + branch), "Freeze branch already exists")
    parent, claim_path = freeze_claim(source, run_id, plan, sources)
    git("update-ref", "HEAD", parent, source)
    record = {"schema_version": 1, "status": "preparation-running", "run_id": run_id,
        "trigger_commit": source, "freeze_claim_commit": parent, "freeze_claim_path": str(claim_path.relative_to(ROOT)),
        "prepared_branch": branch, "started_at": comparison.reused.now(), "packages": packages,
        "stages": {}, "measurement_calls": 0, "policy": "Preparation and ID-only freeze; no scoring or speed claim."}
    status = public / "completion.json"

    def persist():
        nonlocal parent
        comparison.reused.atomic(status, record)
        parent = commit_and_publish([status], branch, parent, "bench: preserve round-six freeze progress before scoring")

    def measured(name, function, location):
        item = {"status": "running", "started_at": comparison.reused.now()}
        record["stages"][name] = item
        persist()
        begin = time.perf_counter_ns()
        try:
            result = function()
            item["status"] = "completed"
            return result
        except BaseException as error:
            item.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            item.update(finished_at=comparison.reused.now(), wall_ms=(time.perf_counter_ns() - begin) / 1e6,
                        storage=storage(location))
            persist()

    try:
        persist()
        baseline_path, candidate_path = private / "baseline", private / "candidate"
        measured("baseline_source", lambda: snapshot(baseline_path, sources["baseline"]["commit"]), baseline_path)
        measured("candidate_source", lambda: snapshot(candidate_path, sources["candidate"]["commit"]), candidate_path)
        actual = {name: comparison.source_identity(path / "src")
                  for name, path in (("baseline", baseline_path), ("candidate", candidate_path))}
        comparison.require(actual == sources, "Prepared checkout differs from declared source")
        prepare_assets(private / "upstream", private / "tokenizers", measured)
        preflight = public / "asset-verification.json"
        receipt = {"schema_version": 1, "status": "all-assets-verified-before-selection", "sources": sources,
            "model": comparison.model_identity(), "optional_semantic": False, "packages": packages,
            "language_runtimes": {"python": sys.version.split()[0], "node": node},
            "upstream_locks_sha256": {name: comparison.file_sha(ROOT / path)
                                      for name, path in comparison.UPSTREAM_LOCKS.items()},
            "preparation": record["stages"], "verified_at": comparison.reused.now(), "trigger_commit": source,
            "preparation_plan_sha256": comparison.file_sha(comparison.PLAN),
            "question_content_read": False, "measurement_calls": 0}
        comparison.verify_asset_receipt(receipt, sources, receipt["upstream_locks_sha256"])
        comparison.reused.atomic(preflight, receipt)
        parent = commit_and_publish([preflight], branch, parent, "bench: publish verified round-six assets before selection")
        comparison.bind(argparse.Namespace(baseline_src=baseline_path / "src", candidate_src=candidate_path / "src",
            asset_verification=preflight, evaluator_commit=parent, output=comparison.BINDING))
        parent = commit_and_publish([comparison.BINDING], branch, parent,
                                    "bench: freeze round-six sources evaluator dependencies and models before IDs")
        binding_commit = parent
        comparison.frozen_inputs()
        # No source/question bytes are downloaded or decoded until the complete
        # binding above is published and a separate Git commit identifies it.
        source_data = json.loads((ROOT / "benchmarks/hotpot_manifest.json").read_bytes())
        input_dir = private / "input"
        input_dir.mkdir()
        parquet = input_dir / "hotpot-dev-distractor.parquet"
        measured("verified_parquet_download", lambda: checked_download(source_data["source_url"], parquet,
            source_data["upstream_sha256"], source_data["upstream_bytes"]), input_dir)
        manifest = data_loader.freeze(parquet, comparison.BINDING, comparison.MANIFEST)
        record.update(status="frozen-not-scored", binding_commit=binding_commit,
            binding_sha256=comparison.file_sha(comparison.BINDING), manifest_sha256=comparison.file_sha(comparison.MANIFEST),
            expected_queries=manifest["expected_queries"], excluded_prior_queries=manifest["excluded_prior_queries"],
            prior_selection_overlap=manifest["prior_selection_overlap"], selected_ids_sha256=manifest["selected_ids_sha256"],
            finished_at=comparison.reused.now())
        comparison.reused.atomic(status, record)
        parent = commit_and_publish([comparison.MANIFEST, status], branch, parent,
                                    "bench: publish 256 fresh IDs excluding all 896 historical IDs before scoring")
        data_loader.load(parquet, comparison.BINDING, comparison.MANIFEST)
        print(json.dumps({"status": record["status"], "prepared_branch": branch, "commit": parent,
                          "queries": 256, "excluded_prior_queries": 896, "measurement_calls": 0}))
        return 0
    except BaseException as error:
        record.update(status="failed-before-scoring", error_type=type(error).__name__, finished_at=comparison.reused.now())
        persist()
        raise




def run(args):
    run_id = actions_identity()
    plan, binding = comparison.frozen_inputs(args.binding)
    _, manifest = data_loader.committed_manifest(args.binding, args.manifest)
    comparison.require(manifest["binding_sha256"] == comparison.file_sha(args.binding), "Selection belongs to another binding")
    directory = ROOT / ".artifacts/round6-comparison" / run_id
    result_dir = ROOT / "benchmarks/results" / ("round6-comparison-" + run_id)
    checkpoint_path = ROOT / "benchmarks/reports" / ("round6-comparison-" + run_id + "-checkpoint.json")
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
        data, cache = prepare(directory, binding, checkpoint, persist)
        bundle, frozen_db = directory / "frozen-pages.json", directory / "states/export/frozen.db"
        for stage in comparison.stages(binding):
            state, prefix = directory / "states" / stage, result_dir / stage
            source_path = None
            if stage == "export" or stage.startswith("baseline-"):
                source_path = baseline / "src"
            elif stage.startswith("candidate-"):
                source_path = candidate / "src"
            command = comparison.worker_command(argparse.Namespace(stage=stage,
                binding=args.binding, manifest=args.manifest, data=data, bundle=bundle,
                frozen_db=frozen_db, state=state, cache=cache, output=prefix,
                host_id=checkpoint["host"]["id"], execution_claim=checkpoint["claim_commit"], source=source_path))
            record = {"status": "running", "started_at": comparison.reused.now(), "argv": command}
            checkpoint["stages"][stage] = record
            persist()
            # The intent commit cannot contain its own ID. Retain the original
            # command in that commit and attach its exact published ID only to
            # the launched process and subsequent completion checkpoints.
            record["execution_intent"] = parent
            launched = [*command, "--execution-intent", parent]
            try:
                code = execute(launched, deadline - time.monotonic() - 120, directory / (stage + ".log"))
                record.update(status="completed" if code == 0 else "failed", exit_code=code)
            except BaseException as error:
                record.update(status="interrupted", error_type=type(error).__name__)
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
        checkpoint.update(status="failed-incomplete", error_type=type(error).__name__)
    finally:
        checkpoint["finished_at"] = comparison.reused.now()
        persist()
    print(json.dumps({"status": checkpoint["status"], "checkpoint": str(checkpoint_path.relative_to(ROOT)),
        "completed_stages": sum(record["status"] == "completed" for record in checkpoint["stages"].values())}))
    return 0 if success else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("freeze", "run"))
    parser.add_argument("--binding", type=Path, default=comparison.BINDING)
    parser.add_argument("--manifest", type=Path, default=comparison.MANIFEST)
    parser.add_argument("--wall-time-seconds", type=int, default=6300)
    args = parser.parse_args(argv)
    return freeze(args) if args.phase == "freeze" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
