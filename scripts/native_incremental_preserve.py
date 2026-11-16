"""Save this hosted attempt directly to Git, including incomplete evidence.

No artifact download or remeasurement is involved. The original experiment and
evidence refs remain untouched. A fresh evidence-only root tree prevents source
branches or CI from changing when this preservation step runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import native_incremental_performance as perf

REPOSITORY = "Afloat16/AI-Memory-Book"
TRIGGER_BRANCH = "validation/native-incremental-formal-1"
PLAN_PATH = "benchmarks/experiments/native_incremental_formal_plan.json"
REPORT_PATH = "benchmarks/reports/native-incremental/formal-run-1"
BUILD_PATH = ".artifacts/native-incremental-formal"
PREFLIGHT_PATH = ".artifacts/native-incremental-preflight"
WORK = ROOT / ".artifacts/native-incremental-preservation"
DESTINATION = WORK / "evidence"


def git(*arguments, input=None, env=None, check=True):
    return subprocess.run(["git", *arguments], cwd=ROOT, input=input, env=env,
                          check=check, capture_output=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def stage(stage_name, **details):
    WORK.mkdir(parents=True, exist_ok=True)
    perf.write(WORK / "checkpoint.json", {"stage": stage_name,
        "source_run_id": os.environ.get("GITHUB_RUN_ID"),
        "source_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), **details})


def copy_file(source, destination, inventory, name):
    perf.require(stat.S_ISREG(source.lstat().st_mode), "Evidence input is not a regular file: " + name)
    raw = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(raw)
    inventory[name] = {"bytes": len(raw), "sha256": perf.sha(raw)}


def collect_inputs(destination):
    """Retain every top-level report/ledger, never the temporary corpus DBs."""
    originals = {}
    preflight = ROOT / PREFLIGHT_PATH
    if preflight.exists():
        for source in sorted(preflight.iterdir()):
            name = source.relative_to(ROOT).as_posix()
            copy_file(source, destination / name, originals, name)
    report = ROOT / REPORT_PATH
    if report.exists():
        for source in sorted(report.iterdir()):
            if source.is_dir() and not source.is_symlink():
                # Worker TemporaryDirectory contains a dataset-derived DB, not
                # raw timing rows. Every timing event lives at the report root.
                continue
            name = source.relative_to(ROOT).as_posix()
            copy_file(source, destination / name, originals, name)
    build = ROOT / BUILD_PATH
    candidates = [build / name for name in ("preparation.json", "preparation.events.jsonl", "build-manifest.json")]
    for label in ("baseline", "candidate"):
        candidates.extend(build / label / name for name in ("build.log", "probe.json", "probe.log"))
        candidates.extend((build / label / "src/memory_book").glob("_native*.so"))
    for source in sorted(candidates):
        if source.exists() or source.is_symlink():
            name = source.relative_to(ROOT).as_posix()
            copy_file(source, destination / name, originals, name)
    return originals


def freeze_evaluator(destination, commit):
    frozen = {}
    for name in (*perf.EVALUATOR_FILES, PLAN_PATH):
        raw = git("show", commit + ":" + name).stdout
        perf.require((ROOT / name).read_bytes() == raw, "Evaluator changed during this hosted attempt: " + name)
        target_name = "frozen-evaluator/" + name
        target = destination / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        frozen[target_name] = {"bytes": len(raw), "sha256": perf.sha(raw)}
    return frozen


def freeze_runtime_sources(destination, plan):
    frozen, unavailable = {}, {}
    for label, specification in plan.get("sources", {}).items():
        commit = specification.get("commit", "")
        found = git("ls-tree", "-r", "--name-only", commit, "src/memory_book", *perf.BUILD_FILES, check=False)
        if found.returncode != 0 or not found.stdout:
            unavailable[label] = "Source object was unavailable before preparation failed."
            continue
        for name in found.stdout.decode().splitlines():
            raw = git("show", commit + ":" + name).stdout
            target_name = "frozen-runtimes/" + label + "/" + name
            target = destination / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            frozen[target_name] = {"bytes": len(raw), "sha256": perf.sha(raw)}
    return frozen, unavailable


def audit_snapshot(destination, commit, run_id):
    report = destination / REPORT_PATH
    summary = report / "summary.json"
    if not (report / "run.json").exists() or not summary.exists():
        return {"state": "incomplete", "complete_summary_present": False, "remeasured_calls": 0}
    build_path = destination / BUILD_PATH / "build-manifest.json"
    try:
        run = perf.read(report / "run.json")
        perf.require(run["evaluator_commit"] == commit and set(run["evaluator"]) == set((*perf.EVALUATOR_FILES, PLAN_PATH)),
                     "Run/evaluator identity differs")
        for name, expected in run["evaluator"].items():
            perf.require(perf.sha((destination / "frozen-evaluator" / name).read_bytes()) == expected,
                         "Frozen evaluator bytes differ: " + name)
        plan_bytes = (destination / "frozen-evaluator" / PLAN_PATH).read_bytes()
        perf.require(perf.sha(plan_bytes) == run["plan_sha256"] and json.loads(plan_bytes) == run["plan"],
                     "Frozen plan bytes differ")
        build = perf.read(build_path)
        perf.require(build == run["build_manifest"] and perf.sha(build_path.read_bytes()) == run["build_manifest_sha256"],
                     "Build manifest differs from measured run")
        perf.require(build["workflow_commit"] == commit and build["workflow_run_id"] == run_id
                     and build["workflow_run_attempt"] == 1, "Build hosted provenance differs")
        for label, source in run["sources"].items():
            for name, expected in source["source_files"].items():
                perf.require(perf.sha((destination / "frozen-runtimes" / label / name).read_bytes()) == expected,
                             "Runtime source bytes differ: " + label + "/" + name)
            for name, expected in source["native_binaries"].items():
                perf.require(perf.sha((destination / BUILD_PATH / label / name).read_bytes()) == expected,
                             "Measured native binary differs: " + label)
            record = build["builds"][label]
            for filename, field in (("build.log", "build_log_sha256"), ("probe.json", "probe_sha256")):
                perf.require(perf.sha((destination / BUILD_PATH / label / filename).read_bytes()) == record[field],
                             "Build/preflight evidence differs: " + label + "/" + filename)
        for item in run["schedule"]:
            intent = perf.read(report / (item["key"] + ".started.json"))
            perf.require(intent["worker"] == item and intent["run_sha256"] == perf.digest(run), "Worker start intent differs")
        environment = {key: value for key, value in os.environ.items() if key not in {"GITHUB_TOKEN", "GH_TOKEN", "PYTHONPATH"}}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run([sys.executable,
            str(destination / "frozen-evaluator/scripts/native_incremental_performance.py"), "--audit", str(report)],
            cwd=destination, env=environment, capture_output=True, timeout=300)
        (destination / "audit.stdout.log").write_bytes(completed.stdout)
        (destination / "audit.stderr.log").write_bytes(completed.stderr)
        audited = json.loads(completed.stdout)
        perf.require(audited == perf.read(summary), "Audit does not exactly reproduce the original summary")
        perf.require(completed.returncode in (0, 2), "Frozen auditor failed")
        return {"state": "complete-equivalent" if audited["comparison"]["complete_output_and_archive_equivalence"] else "complete-with-differences",
                "original_summary_exactly_reproduced": True, "auditor_returncode": completed.returncode,
                "attempted_calls": audited["attempted_calls"], "paired_calls": audited["paired_calls"],
                "run_sha256": audited["run_sha256"], "remeasured_calls": 0}
    except (ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.SubprocessError) as error:
        return {"state": "audit-failed", "error": {"type": type(error).__name__, "message": str(error)}, "remeasured_calls": 0}


def publish(destination, branch):
    environment = {**os.environ, "GIT_INDEX_FILE": str(WORK / "evidence.index"),
        "GIT_AUTHOR_NAME": "Afloat", "GIT_AUTHOR_EMAIL": "ShuffleMonkey@163.com",
        "GIT_COMMITTER_NAME": "Afloat", "GIT_COMMITTER_EMAIL": "ShuffleMonkey@163.com"}
    git("read-tree", "--empty", env=environment)
    entries = []
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            name = path.relative_to(destination).as_posix()
            blob = git("hash-object", "-w", "--stdin", input=path.read_bytes(), env=environment).stdout.decode().strip()
            entries.append(f"100644 {blob}\t{name}\0".encode())
    git("update-index", "-z", "--index-info", input=b"".join(entries), env=environment)
    tree = git("write-tree", env=environment).stdout.decode().strip()
    ref = "refs/heads/" + branch
    existing = git("ls-remote", "--exit-code", "origin", ref, check=False)
    perf.require(existing.returncode in (0, 2), "Could not determine whether evidence ref exists")
    if existing.returncode == 0:
        commit = existing.stdout.decode().split()[0]
        git("fetch", "--filter=blob:none", "--depth=1", "origin", commit)
        perf.require(git("rev-parse", commit + "^{tree}").stdout.decode().strip() == tree,
                     "Existing evidence differs; it will not be overwritten")
        return {"commit": commit, "tree": tree, "already_preserved": True}
    commit = git("commit-tree", tree, "-m", "evidence: preserve native incremental attempt " + os.environ["GITHUB_RUN_ID"],
                 env=environment).stdout.decode().strip()
    git("push", "origin", commit + ":" + ref)
    perf.require(git("ls-remote", "--exit-code", "origin", ref).stdout.decode().split()[0] == commit,
                 "Published evidence ref differs from verified tree")
    return {"commit": commit, "tree": tree, "already_preserved": False}


def main():
    perf.require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF") == "refs/heads/" + TRIGGER_BRANCH
        and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "Preserve only the dedicated hosted first attempt")
    run_id, commit = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_SHA"]
    perf.require(run_id.isdigit() and git("rev-parse", "HEAD").stdout.decode().strip() == commit, "Workflow identity differs")
    branch = "evidence/native-incremental-" + run_id + "-1"
    try:
        stage("collecting", branch=branch)
        DESTINATION.mkdir(parents=True, exist_ok=False)
        originals = collect_inputs(DESTINATION)
        evaluator = freeze_evaluator(DESTINATION, commit)
        plan = perf.read(ROOT / PLAN_PATH)
        runtimes, unavailable = freeze_runtime_sources(DESTINATION, plan)
        stage("auditing", original_files=len(originals))
        audit = audit_snapshot(DESTINATION, commit, run_id)
        (DESTINATION / "audit.json").write_bytes(json_bytes(audit))
        manifest = {"schema_version": 1, "protocol": perf.PROTOCOL, "repository": REPOSITORY, "evidence_branch": branch,
            "source_run": {"id": run_id, "attempt": 1, "commit": commit,
                           "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"},
            "original_files": originals, "frozen_evaluator_files": evaluator, "frozen_runtime_files": runtimes,
            "unavailable_runtime_sources": unavailable, "audit": audit,
            "workflow_steps": {name: os.environ.get("NATIVE_INCREMENTAL_" + name.upper() + "_OUTCOME", "unavailable")
                               for name in ("checkout", "python", "install", "validate", "measure")},
            "preservation_scope": "Every raw report/attempt ledger/log and preparation event, including partial files; no original corpus or temporary corpus-derived databases."}
        (DESTINATION / "evidence-manifest.json").write_bytes(json_bytes(manifest))
        (DESTINATION / "README.md").write_text(f"""# Native incremental evidence

This evidence-only branch preserves hosted run {run_id}, attempt 1, from source
commit `{commit}`. Preservation state: **{audit['state']}**.
It compares the already-native v0.8.0 baseline with the frozen native candidate.
Incomplete or differing runs remain evidence; they are not successful results.

`evidence-manifest.json` inventories every retained input with exact byte counts
and SHA-256 hashes. Both native binary/build records and available committed
runtime sources are retained. No data is downloaded or measured to audit this
branch. The original Python-to-native experiment remains separate and unchanged.

For a complete run, reproduce the full summary without executing either runtime:

```sh
PYTHONDONTWRITEBYTECODE=1 python frozen-evaluator/scripts/native_incremental_performance.py --audit {REPORT_PATH}
```

Compare the JSON result with the original `{REPORT_PATH}/summary.json`.
The frozen auditor requires only the Python standard library. `audit.json`
records whether the preserved summary was reproduced exactly. Raw ledgers,
including started attempts that failed, remain available when no summary exists.
""")
        stage("publishing", branch=branch, audit=audit)
        published = publish(DESTINATION, branch)
        stage("completed", branch=branch, audit=audit, **published)
        print(perf.dump({"evidence_branch": branch, "audit": audit, **published}), flush=True)
        if audit["state"] == "audit-failed":
            raise SystemExit("Evidence saved, but the frozen audit failed; inspect its retained error.")
    except BaseException as error:
        prior = perf.read(WORK / "checkpoint.json") if (WORK / "checkpoint.json").exists() else {}
        stage("failed", previous=prior, error={"type": type(error).__name__, "message": str(error)})
        raise


if __name__ == "__main__":
    main()
