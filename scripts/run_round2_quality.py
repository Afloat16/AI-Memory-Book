"""Run one preregistered Q1 development cohort and save public audit files.

No blind-validation cohort, model retry, weight selection, or automatic replay
is exposed here. Hosted cleanup exports the existing metric ledger only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_hosted_validation as host
from benchmarks.round2_quality_eval import PLAN, export_checkpoint


def cohorts():
    return {entry["label"]: entry for entry in json.loads(PLAN.read_text())["development_cohorts"]}


def paths(stage):
    if stage not in cohorts():
        raise ValueError("Only registered old development cohorts are accepted")
    prefix = ROOT / "benchmarks/results" / ("round2-quality-" + stage)
    marker = ROOT / "benchmarks/reports" / ("round2-quality-" + stage + "-hosted.json")
    state = ROOT / ".artifacts/round2-quality" / stage
    return prefix, marker, state


def public_paths(stage):
    prefix, marker, _ = paths(stage)
    allowed = [marker, *[Path(str(prefix) + suffix) for suffix in
                         (".json.gz", ".summary.json", ".md", ".checkpoint.json", ".attempts.json.gz")]]
    result = []
    for path in allowed:
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT.parent):
            raise ValueError("Refusing a symlink in public output paths")
        path.resolve().relative_to(ROOT)
        if path.is_file():
            if path.stat().st_size > 80 * 1024 * 1024:
                raise ValueError("Public output is unexpectedly large")
            result.append(path.relative_to(ROOT).as_posix())
    return result


def publish(stage):
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not run_id.isdigit() or not attempt.isdigit() or os.environ.get("GITHUB_REPOSITORY") != "Afloat16/AI-Memory-Book":
        raise ValueError("Publication requires the intended repository and hosted run identity")
    branch = "validation/round2-quality-" + stage + "-" + run_id + "-" + attempt
    files = public_paths(stage)
    git = host.publication_command
    source = git("rev-parse", "HEAD").stdout.strip()
    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + branch).stdout.strip()
    base = source
    if remote:
        base = remote.split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise ValueError("Invalid publication branch identity")
        git("fetch", "--no-tags", "origin", "refs/heads/" + branch)
        if git("merge-base", "--is-ancestor", source, base, check=False).returncode:
            raise ValueError("Existing publication branch is from another source checkout")
    cache = ROOT / ".artifacts/round2-quality-publication"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git("read-tree", base, env=env)
        git("add", "--", *files, env=env)
        tree = git("write-tree", env=env).stdout.strip()
        commit = base
        if tree != git("rev-parse", base + "^{tree}").stdout.strip():
            message = Path(temporary) / "message.txt"
            message.write_text("bench: preserve Q1 development " + stage + "\n", encoding="utf-8")
            commit = git("-c", "user.name=github-actions[bot]", "-c",
                         "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                         "commit-tree", tree, "-p", base, "-F", str(message), env=env).stdout.strip()
            git("push", "origin", commit + ":refs/heads/" + branch)
    print(json.dumps({"event": "public_audit_saved", "branch": branch, "commit": commit, "files": files}), flush=True)
    return commit


def marker_base(stage):
    return {"schema_version": 1, "stage": stage, "scope": "old development/regression; no blind validation",
            "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "source_commit": host.publication_command("rev-parse", "HEAD").stdout.strip(),
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "execution_deadline_seconds": 330 * 60,
            "execution_deadline_scope": "Hosted process time limit; model, scoring and evaluation axes are unchanged."}


def evaluate(stage, do_publish):
    cohort = cohorts()[stage]
    prefix, marker, state = paths(stage)
    if marker.exists() or (state / "progress.sqlite3").exists():
        raise ValueError("Preserve the prior attempt; this hosted runner never automatically replays it")
    record = {**marker_base(stage), "status": "running", "started_at": host.now()}
    host.atomic(marker, record)
    if do_publish:
        publish(stage)
    deadline = time.monotonic() + 330 * 60
    configured = os.environ.get("ROUND2_QUALITY_DEADLINE_UNIX")
    if configured:
        deadline = min(deadline, time.monotonic() + max(0, float(configured) - time.time()))
    host._DEADLINE = deadline
    exit_code = 1
    try:
        with host.interrupt_handlers(), host.execution_timer(max(.001, deadline - time.monotonic())):
            host.run([sys.executable, "scripts/prepare_semantic_model.py"])
            if cohort["corpus"] in {"locomo", "hotpotqa"}:
                host.run([sys.executable, "-m", "benchmarks.prepare_native_data"])
            argv = [sys.executable, "-u", "-m", "benchmarks.round2_quality_eval", "--engine-src", "src",
                    "--model-dir", ".artifacts/models/semantic", "--corpus", cohort["corpus"],
                    "--split", cohort.get("split", "development"), "--seed", "61",
                    "--expected-queries", str(cohort["queries"]), "--expected-dataset-sha256", cohort["sha256"],
                    "--state-dir", str(state), "--output", str(prefix)]
            if cohort["corpus"] == "locomo":
                argv.extend(["--locomo-path", ".artifacts/data/locomo10.json"])
            if cohort["corpus"] == "hotpotqa":
                argv.extend(["--hotpot-path", ".artifacts/data/hotpotqa-dev-distractor.json"])
            host.run(argv)
            summary = json.loads(Path(str(prefix) + ".summary.json").read_text())
            if summary["validation"]["passed"] is not True or summary["completed_samples"] != cohort["queries"] * 27:
                raise ValueError("The complete registered comparison did not pass its measurement invariants")
            record.update(status="completed", completed_samples=summary["completed_samples"])
            exit_code = 0
    except host.ValidationInterrupted as exc:
        record.update(status="interrupted", interruption_reason=exc.reason)
        exit_code = exc.exit_code
    except KeyboardInterrupt:
        record.update(status="interrupted", interruption_reason="KeyboardInterrupt")
        exit_code = 130
    except BaseException as exc:
        record.update(status="failed", failure_type=type(exc).__name__)
        exit_code = 1
    finally:
        with host.cleanup_signals():
            record["finished_at"] = host.now()
            host.atomic(marker, record)
    return exit_code


def finalize(stage, do_publish):
    prefix, marker, state = paths(stage)
    if marker.exists():
        record = json.loads(marker.read_text())
        expected = marker_base(stage)
        if any(record.get(key) != expected[key] for key in ("stage", "source_commit", "run_id", "run_attempt")):
            raise ValueError("Finalization cannot mix another cohort/source")
        if record["status"] == "running":
            record.update(status="interrupted_unknown", interruption_reason="process_ended_without_final_marker")
    else:
        record = {**marker_base(stage), "status": "not_started", "interruption_reason": "no_start_marker"}
    exported = export_checkpoint(state, prefix, record["status"])
    record["finalized_at"] = host.now()
    record["checkpoint_exported"] = exported is not None
    record["public_files"] = {path: host.sha(ROOT / path) for path in public_paths(stage)
                              if path != marker.relative_to(ROOT).as_posix()}
    host.atomic(marker, record)
    if do_publish:
        publish(stage)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=tuple(cohorts()), required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    return finalize(args.stage, args.publish) if args.finalize else evaluate(args.stage, args.publish)


if __name__ == "__main__":
    raise SystemExit(main())
