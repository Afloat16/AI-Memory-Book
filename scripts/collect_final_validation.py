"""Collect one fixed hosted run's public evidence using trusted main code only.

No model calls, benchmark replay, branch merge, or automatic main update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import aggregate_hosted_validation as aggregate

REPOSITORY = "Afloat16/AI-Memory-Book"
REPOSITORY_ID = 1453729431
TRUSTED_BASE = "d7f0f4bd322db7f243653a41a2a81a5c385c1b72"
TARGET = {
    "id": 43178953381, "run_attempt": 1, "workflow_id": 415712293,
    "name": "Complete registered memory validation",
    "path": ".github/workflows/complete-validation.yml",
    "head_sha": "4193623a4e7453546ae49bcfaf7bdb26f7a24782",
    "head_branch": "ci/complete-memory-validation", "event": "push",
    "status": "completed",
}
KICK_REF = "refs/heads/ci/automatic-final-aggregation"
AUDIT = "benchmarks/reports/automatic-final-aggregation.json"
BODIES = {
    "answers-locomo": (
        "benchmarks/results/local-answer-final-locomo.json.gz",
        "benchmarks/results/local-answer-final-locomo.summary.json"),
    "answers-hotpotqa": (
        "benchmarks/results/local-answer-final-hotpotqa.json.gz",
        "benchmarks/results/local-answer-final-hotpotqa.summary.json"),
    "workflow-transfer36": ("benchmarks/results/full-workflow-transfer36.json",),
}
# Validate these published derivations, but rebuild them with trusted main code.
WORKFLOW_DERIVED = (
    "benchmarks/results/full-workflow-transfer36-assessment.json",
    "benchmarks/RESULTS-full-workflow.md",
)


class CollectionError(ValueError):
    """Only controlled, source-free reason strings may enter the public audit."""


def marker_path(stage):
    return "benchmarks/reports/hosted-" + stage + "-completion.json"


def source_branch(stage):
    return "refs/heads/validation/20261112-" + stage + "-43178953381-1"


def identity(value):
    if not isinstance(value, dict):
        raise CollectionError("invalid_run_object")
    for key, expected in TARGET.items():
        if type(value.get(key)) is not type(expected) or value[key] != expected:
            raise CollectionError("unregistered_run_identity")
    for key in ("repository", "head_repository"):
        repo = value.get(key, {})
        if repo.get("full_name") != REPOSITORY or repo.get("id") != REPOSITORY_ID:
            raise CollectionError("unregistered_run_repository")
    if value.get("conclusion") not in {
        "success", "failure", "cancelled", "timed_out", "action_required",
        "neutral", "skipped", "stale", "startup_failure",
    }:
        raise CollectionError("run_has_no_final_conclusion")
    return {**TARGET, "conclusion": value["conclusion"]}


def event_identity(event, environment):
    repo = event.get("repository", {})
    if (environment.get("GITHUB_REPOSITORY") != REPOSITORY
            or repo.get("full_name") != REPOSITORY or repo.get("id") != REPOSITORY_ID):
        raise CollectionError("unregistered_event_repository")
    kind, ref = environment.get("GITHUB_EVENT_NAME"), environment.get("GITHUB_REF")
    if kind == "workflow_run" and ref == "refs/heads/main":
        if event.get("action") != "completed":
            raise CollectionError("event_is_not_completed")
        return identity(event.get("workflow_run"))
    if kind == "workflow_dispatch" and ref == "refs/heads/main":
        return None
    if kind == "push" and ref == KICK_REF and event.get("ref") == KICK_REF:
        if event.get("deleted") is True:
            raise CollectionError("deleted_kick_branch")
        return None
    raise CollectionError("unregistered_event_or_ref")


def read_attempt():
    url = ("https://api.github.com/repos/" + REPOSITORY
           + "/actions/runs/43178953381/attempts/1")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise CollectionError("missing_repository_token")
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "memory-validation-finalizer",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise CollectionError("oversized_run_metadata")
    return identity(json.loads(data))


def git(root, *args, env=None, check=True):
    result = subprocess.run(["git", *args], cwd=root, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if check and result.returncode:
        # Never publish Git stderr: a remote URL can contain credentials.
        raise CollectionError("git_operation_failed")
    return result


def checked_out_main(root):
    head = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    main = git(root, "rev-parse", "refs/remotes/origin/main").stdout.decode().strip()
    if (not re.fullmatch(r"[0-9a-f]{40}", head) or head != main
            or git(root, "merge-base", "--is-ancestor", TRUSTED_BASE, head,
                   check=False).returncode):
        raise CollectionError("collector_must_execute_trusted_main")
    return head


def safe_path(root, name):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise CollectionError("unsafe_public_output_path")
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise CollectionError("symlink_in_public_output_path")
    return path


def blob(root, commit, name):
    entry = git(root, "ls-tree", "-z", commit, "--", name).stdout
    parts = entry.rstrip(b"\0").split(b"\t")
    if len(parts) != 2 or parts[1].decode() != name:
        raise CollectionError("missing_public_blob:" + name)
    mode, kind, oid = parts[0].decode().split()
    if mode != "100644" or kind != "blob" or not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise CollectionError("public_output_is_not_a_regular_blob:" + name)
    size = int(git(root, "cat-file", "-s", oid).stdout)
    limit = 1024 * 1024 if name.endswith("-completion.json") else 64 * 1024 * 1024
    if not 0 < size <= limit:
        raise CollectionError("public_output_size_rejected:" + name)
    data = git(root, "cat-file", "blob", oid).stdout
    if len(data) != size:
        raise CollectionError("public_blob_size_changed:" + name)
    return data


def collect_stage(root, stage):
    ref = source_branch(stage)
    resolved = git(root, "ls-remote", "--exit-code", "--heads", "origin", ref).stdout.decode().split()
    if len(resolved) != 2 or resolved[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", resolved[0]):
        raise CollectionError("unresolved_result_branch:" + stage)
    commit = resolved[0]
    git(root, "fetch", "--no-tags", "--no-write-fetch-head", "origin", commit)
    if git(root, "merge-base", "--is-ancestor", TARGET["head_sha"], commit,
           check=False).returncode:
        raise CollectionError("result_branch_has_wrong_source:" + stage)
    bodies = BODIES[stage]
    published = bodies + (WORKFLOW_DERIVED if stage == "workflow-transfer36" else ())
    marker_name = marker_path(stage)
    allowed = set(published) | {marker_name}
    changed = {name.decode() for name in git(
        root, "diff", "--name-only", "--no-renames", "-z", TARGET["head_sha"], commit).stdout.split(b"\0") if name}
    if not changed <= allowed:
        raise CollectionError("result_branch_contains_unregistered_changes:" + stage)
    marker_bytes = blob(root, commit, marker_name)
    marker = json.loads(marker_bytes)
    if (marker.get("schema_version") != 1 or marker.get("stage") != stage
            or marker.get("source_commit") != TARGET["head_sha"]
            or marker.get("status") not in {"completed", "failed"}
            or marker.get("missing_outputs") != []
            or set(marker.get("public_output_sha256", {})) != set(published)):
        raise CollectionError("incomplete_or_unregistered_publication:" + stage)
    payloads = {name: blob(root, commit, name) for name in published}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    if hashes != marker["public_output_sha256"]:
        raise CollectionError("published_hash_mismatch:" + stage)
    # Check the entire stage before writing. An existing canonical byte is immutable.
    imports = {name: payloads[name] for name in bodies}
    imports[marker_name] = marker_bytes
    for name, data in imports.items():
        path = safe_path(root, name)
        if path.exists() and (not path.is_file() or path.read_bytes() != data):
            raise CollectionError("existing_canonical_input_differs:" + name)
    for name, data in imports.items():
        path = safe_path(root, name)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    return {
        "stage": stage, "branch": ref, "result_commit": commit,
        "measurement_source_commit": marker["source_commit"],
        "original_status": marker["status"], "original_exit_code": marker.get("exit_code"),
        "public_output_sha256": hashes,
        "imported_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in imports.items()},
    }


def publish(root, source, files):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or not run_id.isdigit() or not attempt.isdigit()
            or os.environ.get("GITHUB_REF") not in {"refs/heads/main", KICK_REF}):
        raise CollectionError("unregistered_publisher_environment")
    allowed = {AUDIT, aggregate.AUDIT, *aggregate.OUTPUTS,
               *(marker_path(stage) for stage in BODIES),
               *(name for values in BODIES.values() for name in values)}
    if not set(files) <= allowed:
        raise CollectionError("unregistered_publication_path")
    for name in files:
        if not safe_path(root, name).is_file():
            raise CollectionError("missing_publication_file")
    branch = "validation/automatic-final-43178953381-1-" + run_id + "-" + attempt
    ref = "refs/heads/" + branch
    existing = git(root, "ls-remote", "--exit-code", "--heads", "origin", ref, check=False)
    if existing.returncode not in {0, 2} or existing.stdout:
        raise CollectionError("publication_branch_exists_or_cannot_be_checked")
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git(root, "read-tree", source, env=env)
        git(root, "add", "--", *sorted(set(files)), env=env)
        tree = git(root, "write-tree", env=env).stdout.decode().strip()
        message = Path(directory) / "message.txt"
        message.write_text("bench: save fixed-run collection and strict final assessment\n", encoding="utf-8")
        commit = git(root, "-c", "user.name=github-actions[bot]",
                     "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                     "commit-tree", tree, "-p", source, "-F", str(message), env=env).stdout.decode().strip()
        git(root, "push", "origin", commit + ":" + ref)  # Never force or update main.
    print("Saved audit snapshot: https://github.com/" + REPOSITORY + "/tree/" + branch)
    return branch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    root = ROOT
    audit = {"schema_version": 1, "status": "running", "started_at": aggregate.now(),
             "target_run": TARGET, "collected": [],
             "model_calls_made_by_collector": 0,
             "timing_policy": "Retain each cohort's measured environment; never pool host timings."}
    aggregate.atomic(root / AUDIT, audit)
    success, authorized, aggregation_started = False, False, False
    previous_aggregation_sha = None
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        declared = event_identity(event, os.environ)
        source = checked_out_main(root)
        authorized = True  # A failed fixed API read may still publish a failure audit.
        observed = read_attempt()
        if declared is not None and declared != observed:
            raise CollectionError("event_and_fixed_attempt_disagree")
        audit.update(collector_source_commit=source, target_run=observed,
                     collector_run={"id": os.environ.get("GITHUB_RUN_ID"),
                                    "attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
                     trigger=os.environ["GITHUB_EVENT_NAME"],
                     collector_sha256=aggregate.sha(Path(__file__)),
                     prerequisites={key: os.environ.get(key) for key in
                                    ("FINALIZER_DEPENDENCIES_STATUS", "FINALIZER_TEST_STATUS")})
        if any(value != "success" for value in audit["prerequisites"].values()):
            raise CollectionError("trusted_dependency_or_test_gate_failed")
        for stage in BODIES:
            audit["collected"].append(collect_stage(root, stage))
            aggregate.atomic(root / AUDIT, audit)
        command = [sys.executable, str(root / "scripts/aggregate_hosted_validation.py")]
        # Do not spoof GITHUB_REF or use the manual aggregator's --publish guard.
        previous_aggregation_sha = (aggregate.sha(root / aggregate.AUDIT)
                                    if (root / aggregate.AUDIT).is_file() else None)
        aggregation_started = True
        outcome = subprocess.run(command, cwd=root, check=False, timeout=900)
        audit["aggregation_exit_code"] = outcome.returncode
        if outcome.returncode:
            raise CollectionError("strict_aggregation_failed")
        verified = aggregate.read(root, aggregate.AUDIT)
        if (verified.get("status") != "complete-verified-snapshot"
                or aggregate.sha(root / aggregate.AUDIT) == previous_aggregation_sha):
            raise CollectionError("strict_aggregation_has_no_complete_audit")
        audit["matrix"] = aggregate.verify_assessments(root)
        for entry in audit["collected"]:
            if any(aggregate.sha(root / name) != digest
                   for name, digest in entry["imported_sha256"].items()):
                raise CollectionError("collected_input_changed_during_aggregation")
        audit["aggregation_audit_sha256"] = aggregate.sha(root / aggregate.AUDIT)
        audit["output_sha256"] = {name: aggregate.sha(root / name) for name in aggregate.OUTPUTS}
        audit["status"] = "complete-verified-snapshot"
        success = True
    except Exception as exc:
        audit.update(status="failed", error_type=type(exc).__name__,
                     reason=str(exc) if isinstance(exc, CollectionError) else "collector_exception")
    finally:
        audit["finished_at"] = aggregate.now()
        aggregate.atomic(root / AUDIT, audit)
        if args.publish and authorized:
            files = {AUDIT, *(name for entry in audit["collected"] for name in entry["imported_sha256"])}
            if (aggregation_started and (root / aggregate.AUDIT).is_file()
                    and aggregate.sha(root / aggregate.AUDIT) != previous_aggregation_sha):
                files.add(aggregate.AUDIT)
            if success:
                files.update(aggregate.OUTPUTS)
            if any(not (root / name).is_file() or aggregate.sha(root / name) != digest
                   for entry in audit["collected"] for name, digest in entry["imported_sha256"].items()):
                success = False
                audit.update(status="failed", reason="canonical_input_changed_before_publication")
                files = {AUDIT}
                aggregate.atomic(root / AUDIT, audit)
            try:
                audit["publication_branch"] = publish(root, source, files)
            except Exception as exc:
                audit.update(assessment_status=audit["status"], status="publication-failed",
                             publication_status="failed", publication_error_type=type(exc).__name__)
                aggregate.atomic(root / AUDIT, audit)
                success = False
        print(json.dumps({"status": audit["status"], "publication": audit.get("publication_branch"),
                          "reason": audit.get("reason"), "source_run_conclusion": audit["target_run"].get("conclusion")}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
