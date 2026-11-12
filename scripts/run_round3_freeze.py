"""Prepare and commit one round-three binding and ID selection; never score it.

Only the dedicated first-attempt Actions push may run this controller. Public
quality evidence, then the binding, must be confirmed on the remote result
branch before the original Parquet is opened. A plan-scoped claim prevents
another push from silently repeating a selection after an interrupted run.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round3_comparison as comparison
from scripts import round3_data
from benchmarks.prepare_native_data import checked_download

REPOSITORY = "Afloat16/AI-Memory-Book"
TRIGGER = "refs/heads/ci/v031-round3-freeze"
BASELINE = "dd2f88be742ed330269e7dd5915b6f75089d7fef"
CANDIDATE = "2d199b93f650eccd3dd239178822b31001b880e3"
QUALITY = "benchmarks/reports/round3-project-stats-recovered"
EXTRAS = ("scripts/run_round3_freeze.py", "tests/test_round3_freeze.py",
          ".github/workflows/round3-freeze.yml", "scripts/recover_round3_quality.py",
          "tests/test_round3_quality_recovery.py", "benchmarks/experiments/round3-quality-recovery.json",
          "scripts/prepare_semantic_model.py", "benchmarks/prepare_native_data.py")


def actions_identity():
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    comparison.require(os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == TRIGGER
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and re.fullmatch(r"[1-9][0-9]*", run_id) and attempt == "1"
        and re.fullmatch(r"[0-9a-f]{40}", os.environ.get("GITHUB_SHA", ""))
        and os.environ.get("ORT_DISABLE_TELEMETRY") == "1",
        "Require the exact repository, first Actions push attempt, SHA and telemetry opt-out")
    return run_id + "-" + attempt


def clean_environment():
    environment = {key: value for key, value in os.environ.items()
        if key not in {"GH_TOKEN", "GITHUB_TOKEN", "PYTHONPATH", "PYTHONHOME", "GIT_ASKPASS", "SSH_ASKPASS"}
        and not key.startswith(("GIT_CONFIG_", "GIT_TRACE"))}
    environment.update(PYTHONDONTWRITEBYTECODE="1", GIT_TERMINAL_PROMPT="0")
    return environment


def git(*args, token=None, cwd=None, environment=None, check=True):
    env = clean_environment()
    if environment:
        env.update(environment)
    if token is not None:
        # Credentials are only in this short-lived Git child's environment,
        # never in arguments, repository config, helper processes or reports.
        header = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="",
                   GIT_CONFIG_KEY_1="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_1="AUTHORIZATION: basic " + header)
    result = subprocess.run(["git", *args], cwd=ROOT if cwd is None else cwd, env=env,
                            capture_output=True, timeout=120)
    if not check:
        return result
    comparison.require(result.returncode == 0, "Git operation failed; credential-bearing diagnostics omitted")
    return result.stdout.decode().strip()


def authorized_origin():
    comparison.require(git("remote", "get-url", "origin") in (
        "https://github.com/Afloat16/AI-Memory-Book", "https://github.com/Afloat16/AI-Memory-Book.git"),
        "Publication requires the exact HTTPS repository origin")


def require_absent(paths):
    comparison.require(all(not Path(path).exists() and not Path(path).is_symlink() for path in paths),
                       "Preserve existing binding, selection or run state; no implicit replay")


def public_commit(paths, parent, message):
    names = []
    for path in paths:
        comparison.require(path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to((ROOT / "benchmarks").resolve()),
            "Only explicit regular public artifacts may be committed")
        names.append(path.relative_to(ROOT).as_posix())
    with tempfile.TemporaryDirectory() as temporary:
        location = Path(temporary)
        env = {"GIT_INDEX_FILE": str(location / "index")}
        git("read-tree", parent, environment=env)
        git("add", "--", *sorted(set(names)), environment=env)
        tree = git("write-tree", environment=env)
        body = location / "message"
        body.write_text(message + "\n", encoding="utf-8")
        return git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit-tree", tree, "-p", parent, "-F", str(body), environment=env)


def remote_head(branch, token):
    result = git("ls-remote", "--heads", "origin", branch, token=token)
    if not result:
        return None
    fields = result.split()
    comparison.require(len(fields) == 2 and fields[1] == branch
        and re.fullmatch(r"[0-9a-f]{40}", fields[0]), "Unexpected remote branch identity")
    return fields[0]


def push_commit(commit, parent, branch, token):
    authorized_origin()
    git("push", "origin", commit + ":" + branch, token=token)
    comparison.require(remote_head(branch, token) == commit, "Remote checkpoint was not confirmed")
    # Move only local detached HEAD after remote durability is confirmed.
    # The frozen readers inspect HEAD bytes, not an uncommitted working file.
    git("update-ref", "--no-deref", "HEAD", commit, parent)
    git("read-tree", commit)


def claim(source, run_id, token, plan_sha):
    branch = "refs/heads/validation/v031-round3-freeze-claim-" + plan_sha
    authorized_origin()
    comparison.require(remote_head(branch, token) is None,
        "This registered plan already has a freeze claim; recover it without selecting again")
    path = ROOT / "benchmarks/reports" / ("round3-freeze-claim-" + plan_sha + ".json")
    require_absent([path])
    comparison.reused.atomic(path, {"schema_version": 1, "run_id": run_id, "source_commit": source,
        "plan_sha256": plan_sha, "status": "claimed-before-preparation", "created_at": comparison.reused.now(),
        "policy": "One preparation and selection attempt; an interruption requires explicit recovery, never replay."})
    commit = public_commit([path], source, "bench: claim one round-three preparation and selection")
    # Racing claims are siblings of the same source; a second non-force push
    # cannot fast-forward the first successfully published claim.
    push_commit(commit, source, branch, token)
    return commit


def publish(checkpoint_path, outputs, parent, run_id, token):
    comparison.require(actions_identity() == run_id, "Publication run identity differs")
    branch = "refs/heads/validation/v031-round3-freeze-" + run_id
    comparison.require(remote_head(branch, token) in (None, parent),
        "Another writer advanced the result branch; never force push")
    commit = public_commit([checkpoint_path, *outputs], parent, "bench: preserve round-three preparation checkpoint")
    push_commit(commit, parent, branch, token)
    return commit


def helper(arguments, timeout=600):
    result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=clean_environment(),
                            capture_output=True, timeout=timeout)
    comparison.require(result.returncode == 0, "Preparation helper failed; captured output omitted")


def snapshot(path, commit):
    require_absent([path])
    if git("cat-file", "-e", commit + "^{commit}", check=False).returncode:
        git("fetch", "--no-tags", "origin", commit)
    git("worktree", "add", "--no-checkout", "--detach", str(path), commit)
    git("sparse-checkout", "set", "--cone", "src", cwd=path)
    git("read-tree", "-mu", commit, cwd=path)


def quality_disposition(directory):
    proof_path = directory / "recovery-proof.json"
    proof = json.loads(proof_path.read_bytes())
    validation, screening = proof["validation"], proof["screening"]
    comparison.require(proof["status"] == "recovered-and-audited" and proof["replayed_calls"] == 0
        and proof["frozen_audit_passed"] is True and proof["original_gzip_prefix_exact"] is True
        and proof["original_json_prefix_exact"] is True and validation["passed"] is True
        and validation["workers"] == 8 and validation["calls"] == 8082
        and screening["qualified"] is False and screening["status"] == "rejected_loss_or_no_gain",
        "Recovered statistics screen must be complete, verified and rejected before freezing the default candidate")
    inventory = proof["files"]
    comparison.require(isinstance(inventory, dict) and bool(inventory), "Missing recovery inventory")
    comparison.require(set(inventory) == {path.name for path in directory.iterdir()} - {proof_path.name},
                       "Recovery directory differs from its audited inventory")
    outputs = [proof_path]
    for name, identity in inventory.items():
        path = directory / name
        comparison.require(Path(name).name == name and name not in {".", ".."}
            and path.is_file() and not path.is_symlink() and path.stat().st_size == identity["bytes"]
            and comparison.file_sha(path) == identity["sha256"], "Recovery artifact identity differs")
        outputs.append(path)
    return sorted(outputs), {"status": screening["status"], "qualified": False,
        "calls": validation["calls"], "workers": validation["workers"], "replayed_calls": 0,
        "proof_sha256": comparison.file_sha(proof_path)}


def require_durable_binding(binding, parent, run_id, token):
    branch = "refs/heads/validation/v031-round3-freeze-" + run_id
    comparison.require(git("rev-parse", "HEAD") == parent and remote_head(branch, token) == parent,
                       "Commit and confirm the binding remotely before accessing selection data")
    comparison.require_committed(binding)
    comparison.frozen_inputs(binding)
    round3_data.registered_inputs(binding)


def run():
    run_id = actions_identity()
    token = os.environ.pop("GH_TOKEN", "")
    os.environ.pop("GITHUB_TOKEN", None)
    comparison.require(bool(token), "The dedicated publication step needs its scoped GitHub token")
    authorized_origin()
    source = git("rev-parse", "HEAD")
    comparison.require(source == os.environ["GITHUB_SHA"]
        and Path(git("rev-parse", "--show-toplevel")).resolve() == ROOT.resolve()
        and not git("status", "--porcelain", "--untracked-files=no"), "Require the exact clean triggering checkout")
    plan = comparison.registered_plan()
    directory = ROOT / ".artifacts/round3-freeze" / run_id
    checkpoint_path = ROOT / "benchmarks/reports" / ("round3-freeze-" + run_id + "-checkpoint.json")
    binding, manifest, quality = comparison.BINDING, comparison.MANIFEST, ROOT / QUALITY
    require_absent([directory, checkpoint_path, binding, manifest, quality])
    branch = "refs/heads/validation/v031-round3-freeze-" + run_id
    comparison.require(remote_head(branch, token) is None, "Preserve the existing preparation run")
    parent = claim(source, run_id, token, comparison.file_sha(comparison.PLAN))
    directory.mkdir(parents=True)
    checkpoint = {"schema_version": 1, "run_id": run_id, "source_commit": source,
        "claim_commit": parent, "protocol": plan["protocol"], "status": "preparing",
        "started_at": comparison.reused.now(), "stages": {}, "retrieval_calls": 0,
        "model_inference_calls": 0, "answer_calls": 0, "optional_project_statistics": False,
        "result_branch": branch.removeprefix("refs/heads/")}
    outputs, immutable = [], {}

    def persist():
        nonlocal parent
        comparison.require(all(comparison.file_sha(path) == expected for path, expected in immutable.items()),
                           "A completed preparation artifact changed")
        checkpoint["outputs_sha256"] = {path.relative_to(ROOT).as_posix(): comparison.file_sha(path)
                                        for path in outputs}
        comparison.reused.atomic(checkpoint_path, checkpoint)
        parent = publish(checkpoint_path, outputs, parent, run_id, token)

    def preserve(paths):
        for path in paths:
            outputs.append(path)
            immutable[path] = comparison.file_sha(path)

    def stage(name, action):
        record = {"status": "running", "started_at": comparison.reused.now()}
        checkpoint["stages"][name] = record
        persist()
        started = time.perf_counter_ns()
        try:
            value = action()
            record["status"] = "completed"
            return value
        except BaseException as error:
            record.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            record.update(finished_at=comparison.reused.now(), wall_ms=(time.perf_counter_ns() - started) / 1e6)
            persist()

    success = False
    try:
        def recover():
            helper(["scripts/recover_round3_quality.py"])
            files, disposition = quality_disposition(quality)
            preserve(files)
            checkpoint["statistics_disposition"] = disposition
        stage("recover_and_verify_old_quality", recover)
        baseline, candidate = directory / "baseline", directory / "candidate"
        stage("exact_source_checkouts", lambda: (snapshot(baseline, BASELINE), snapshot(candidate, CANDIDATE)))
        model = directory / "semantic-model"
        def prepare_model():
            helper(["scripts/prepare_semantic_model.py", "--output", str(model)])
            comparison.verify_model(model, comparison.model_identity())
        stage("download_and_verify_model_bytes", prepare_model)
        def bind():
            arguments = ["scripts/round3_comparison.py", "bind", "--baseline-src", str(baseline / "src"),
                         "--candidate-src", str(candidate / "src"), "--model-dir", str(model), "--output", str(binding)]
            for name in EXTRAS:
                arguments.extend(["--extra-evaluator", name])
            helper(arguments)
            preserve([binding])
        stage("freeze_and_publish_binding", bind)
        require_durable_binding(binding, parent, run_id, token)
        parquet = directory / "private/hotpot-dev-distractor.parquet"
        original = json.loads(round3_data.baseline_bytes(round3_data.ORIGINAL))
        stage("download_verified_original_parquet", lambda: checked_download(original["source_url"], parquet,
              original["upstream_sha256"], original["upstream_bytes"]))
        def select():
            require_durable_binding(binding, parent, run_id, token)
            round3_data.freeze(parquet, binding, manifest)
            preserve([manifest])
        stage("freeze_and_publish_registered_ids", select)
        comparison.require_committed(manifest)
        checkpoint.update(status="frozen-ready-for-comparison", finished_at=comparison.reused.now())
        success = True
    except BaseException as error:
        checkpoint.update(status="failed-incomplete", error_type=type(error).__name__, finished_at=comparison.reused.now())
    finally:
        persist()
    print(json.dumps({"status": checkpoint["status"], "result_branch": checkpoint["result_branch"],
        "checkpoint": checkpoint_path.relative_to(ROOT).as_posix(), "retrieval_calls": 0, "model_inference_calls": 0}))
    return 0 if success else 2


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        raise SystemExit(run())
    except Exception as error:
        # Do not echo subprocess exceptions, URLs, model bytes or credentials.
        print(json.dumps({"status": "preparation-controller-error", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(2)
