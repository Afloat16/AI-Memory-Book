#!/usr/bin/env python3
"""Freeze and preserve one hosted comprehensive runtime attempt without rerunning it.

The evidence ref is a new parentless Git tree. Raw partial files remain raw;
audit errors or missing observations fail the job after evidence is preserved.
Only the standard library is needed for freezing, auditing, and preservation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import statistics
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "238c8058f723a203eaca99f94d924ab77de4c0b3"
REPOSITORY = "Afloat16/AI-Memory-Book"
BRANCH = "validation/comprehensive-v010-formal-1"
WORKFLOW = ".github/workflows/comprehensive-runtime-performance.yml"
PLAN = "benchmarks/comprehensive-runtime-plan.json"
PROTOCOL = "comprehensive-runtime-v010-1"
NUMPY = "2.5.5"
WORK_PATH = ".artifacts/comprehensive-runtime"
PRESERVATION_PATH = ".artifacts/comprehensive-runtime-preservation"
EVALUATOR_PATHS = (
    "scripts/comprehensive_runtime_preserve.py", "scripts/benchmark_semantic_runtime.py",
    "scripts/benchmark_directory_runtime.py", "benchmarks/semantic-runtime-plan.json",
    "benchmarks/directory-runtime-plan.json", PLAN,
    WORKFLOW, "pyproject.toml",
)
STEPS = ("checkout", "python", "freeze", "install", "contracts", "semantic_validate",
         "directory_validate", "semantic_measure", "directory_measure")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(*arguments, input=None, env=None, check=True):
    return subprocess.run(["git", *arguments], cwd=ROOT, input=input, env=env,
                          check=check, capture_output=True)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def read(path):
    return json.loads(path.read_bytes())


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def inventory(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}


def failure(error):
    details = {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, subprocess.CalledProcessError):
        details.update(stdout=(error.stdout or b"").decode(errors="replace"),
                       stderr=(error.stderr or b"").decode(errors="replace"))
    return details


def hosted_identity():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "Only the dedicated hosted push and first attempt may run or publish evidence")
    run, commit = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_SHA", "")
    require(run.isdigit() and int(run) > 0 and len(commit) == 40
            and git("rev-parse", "HEAD").stdout.decode().strip() == commit
            and os.environ.get("GITHUB_WORKFLOW_SHA") == commit
            and os.environ.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH,
            "Workflow pipeline, run, or candidate HEAD differs")
    return {"id": run, "attempt": 1, "commit": commit,
            "url": f"https://github.com/{REPOSITORY}/actions/runs/{run}"}


def clean_source():
    require(git("diff", "--quiet", "HEAD", "--", check=False).returncode == 0,
            "Tracked candidate source changed")
    untracked = git("ls-files", "--others", "-z").stdout.decode().split("\0")
    require(all(not name or name.startswith(".artifacts/") for name in untracked),
            "Untracked candidate files exist outside .artifacts")


def freeze_tree(work, label, commit, paths, files):
    entries = git("ls-tree", "-rz", commit, "--", *paths).stdout.split(b"\0")
    require(any(entries), "Frozen source tree is unavailable: " + label)
    for entry in entries:
        if not entry:
            continue
        metadata, name_bytes = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        name = name_bytes.decode()
        require(mode in (b"100644", b"100755") and kind == b"blob", "Frozen input is not a regular file: " + name)
        raw = git("cat-file", "blob", object_id.decode()).stdout
        target = "frozen/" + label + "/" + name
        write_new(work / target, raw)
        files[target] = {**inventory(raw), "source": name, "commit": commit}


def freeze():
    identity = hosted_identity()
    work = ROOT / WORK_PATH
    work.mkdir(parents=True, exist_ok=True)
    require(not (work / "source-manifest.json").exists() and not (work / "frozen").exists(),
            "This attempt already has frozen inputs; refuse to overwrite them")
    manifest = {"protocol": PROTOCOL, "source_run": identity, "baseline_commit": BASELINE,
                "status": "freezing", "files": {},
                "environment": {"python": platform.python_version(), "platform": platform.platform(),
                    "runner_os": os.environ.get("RUNNER_OS"), "runner_arch": os.environ.get("RUNNER_ARCH"),
                    "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion"),
                    "text_backend": os.environ.get("MEMORY_BOOK_TEXT_BACKEND"),
                    "thread_environment": {key: os.environ.get(key) for key in
                                           ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}}
    try:
        freeze_tree(work, "candidate", identity["commit"],
                    ("src/memory_book", "tests", *EVALUATOR_PATHS), manifest["files"])
        clean_source()
        require(sys.version_info[:2] == (3, 12) and os.environ.get("MEMORY_BOOK_TEXT_BACKEND") == "python",
                "Frozen experiment requires Python 3.12 and the Python text backend")
        fetched = git("fetch", "--no-tags", "--filter=blob:none", "--depth=1", "origin", BASELINE, check=False)
        write_new(work / "logs/baseline-fetch.stdout.log", fetched.stdout)
        write_new(work / "logs/baseline-fetch.stderr.log", fetched.stderr)
        require(fetched.returncode == 0 and git("rev-parse", BASELINE + "^{commit}").stdout.decode().strip() == BASELINE,
                "Exact baseline could not be fetched")
        freeze_tree(work, "baseline", BASELINE, ("src/memory_book", "pyproject.toml"), manifest["files"])
        required = ["frozen/candidate/" + path for path in EVALUATOR_PATHS]
        require(all(path in manifest["files"] for path in required), "A frozen evaluator or protocol file is missing")
        manifest["status"] = "frozen"
    except BaseException as error:
        manifest["status"] = "failed"
        manifest["error"] = failure(error)
        raise
    finally:
        write_new(work / "source-manifest.json", encoded(manifest))
    print(json.dumps({"status": "frozen", "files": len(manifest["files"]), "source_run": identity}))


def verify_frozen(work, identity, check_worktree=False):
    manifest = read(work / "source-manifest.json")
    require(manifest["protocol"] == PROTOCOL and manifest["status"] == "frozen"
            and manifest["source_run"] == identity and manifest["baseline_commit"] == BASELINE,
            "Frozen manifest does not identify this complete source attempt")
    for name, specification in manifest["files"].items():
        require(inventory((work / name).read_bytes()) == {key: specification[key] for key in ("bytes", "sha256")},
                "Frozen bytes changed: " + name)
        if check_worktree and name.startswith("frozen/candidate/"):
            require((ROOT / specification["source"]).read_bytes() == (work / name).read_bytes(),
                    "Candidate input changed after freezing: " + specification["source"])
    return manifest


def check():
    identity = hosted_identity()
    clean_source()
    manifest = verify_frozen(ROOT / WORK_PATH, identity, check_worktree=True)
    import numpy
    require(sys.version_info[:2] == (3, 12) and numpy.__version__ == NUMPY,
            "Python or NumPy differs from the frozen environment")
    require(os.environ.get("MEMORY_BOOK_TEXT_BACKEND") == "python"
            and os.environ.get("PYTHONHASHSEED") == "0"
            and all(os.environ.get(key) == "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")),
            "Backend, hash seed, or thread environment differs")
    print(json.dumps({"source_run": identity, "frozen_files_verified": len(manifest["files"]), "numpy": numpy.__version__}))


def balanced(rows, pairs, fields):
    expected = [(pair, position, arm) for pair in range(pairs)
                for position, arm in enumerate(("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline"))]
    require([(row["pair"], row["position"], row["arm"]) for row in rows] == expected,
            "Missing, duplicate, reordered or unbalanced paired observations")
    for row in rows:
        require(all(type(row[key]) is int and row[key] > 0 for key in fields), "Invalid observation measurement")


def source_hash(manifest, arm, path):
    return manifest["files"]["frozen/" + arm + "/" + path]["sha256"]


def semantic_summary(rows, field):
    medians = {arm: statistics.median(row[field] for row in rows if row["arm"] == arm)
               for arm in ("baseline", "candidate")}
    paired = []
    for pair in sorted({row["pair"] for row in rows}):
        values = {row["arm"]: row[field] for row in rows if row["pair"] == pair}
        paired.append(values["candidate"] / values["baseline"])
    return {"median_" + field: medians, "candidate_over_baseline_pair_ratios": paired,
            "median_candidate_over_baseline": statistics.median(paired)}


def audit_summary(section, field):
    computed = semantic_summary(section["observations"], field)
    require(all(section[key] == value for key, value in computed.items()), "Semantic summary differs from raw observations")


def audit_semantic(work, manifest, identity):
    path = work / "reports/semantic-runtime.json"
    report = read(path)
    events = [json.loads(line) for line in (work / "reports/semantic-runtime.events.jsonl").read_text().splitlines()]
    require(report["protocol"] == "semantic-runtime-development-v3" and report["baseline_ref"] == BASELINE,
            "Semantic baseline/protocol differs")
    require(report["sources"]["baseline"]["commit"] == BASELINE
            and report["sources"]["candidate"]["head"] == identity["commit"]
            and report["sources"]["candidate"]["source_status"] == "", "Semantic source identity differs")
    for arm in ("baseline", "candidate"):
        require(report["sources"][arm]["source_sha256"] == source_hash(manifest, arm, "src/memory_book/semantic.py"),
                "Semantic source hash differs")
    require(report["script_sha256"] == source_hash(manifest, "candidate", "scripts/benchmark_semantic_runtime.py")
            and report["plan_sha256"] == source_hash(manifest, "candidate", "benchmarks/semantic-runtime-plan.json"),
            "Semantic evaluator hash differs")
    require(report["environment"]["numpy"] == NUMPY and report["environment"]["python"].startswith("3.12."),
            "Semantic environment differs")
    for key, value in {"windows": [4096, 32768], "pairs": 4, "memory_pairs": 2, "artifact_pairs": 4,
                       "warmups": 2, "model_bytes": 118453870, "tokenizer_bytes": 9081518}.items():
        require(report["arguments"][key] == value, "Semantic argument differs: " + key)
    expected_events = [{"event": "started", "run": {key: value for key, value in report.items()
                        if key not in ("ranking", "artifact_initialization")}}]
    require([case["fixture"]["windows"] for case in report["ranking"]] == [4096, 32768], "Semantic fixture matrix differs")
    for case in report["ranking"]:
        windows, validation = case["fixture"]["windows"], case["validation"]
        require(validation["exact_equal"] is True and validation["cursor_closed"] is True
                and all(type(size) is int and 0 <= size <= 4096 for size in validation["batch_rows"])
                and sum(validation["batch_rows"]) == windows
                and max(validation["batch_rows"]) == validation["maximum_vector_batch_rows"] <= 4096,
                "Semantic equality or bounded cursor contract failed")
        expected_events.append({"event": "ranking-validated", "fixture": case["fixture"],
            "output_sha256": validation["output_sha256"], "batch_rows": validation["batch_rows"], "cursor_closed": True})
        for section, pairs, fields, kind in (
                (case["latency"], 4, ("elapsed_ns", "process_cpu_ns"), "ranking-latency"),
                (case["allocations"], 2, ("peak_python_bytes",), "ranking-allocations")):
            balanced(section["observations"], pairs, fields)
            require(all(row["exact_equal"] is True and "error" not in row
                        and row["output_sha256"] == validation["output_sha256"] for row in section["observations"]),
                    "Semantic measured output differs")
            audit_summary(section, fields[0])
            if "process_cpu_ns" in fields:
                require(section["process_cpu"] == semantic_summary(section["observations"], "process_cpu_ns"),
                        "Semantic CPU summary differs")
            for row in section["observations"]:
                expected_events.append({"event": kind + "-started", "windows": windows,
                    **{key: row[key] for key in ("pair", "position", "arm")}})
                expected_events.append({"event": kind, "windows": windows, "observation": row})
    artifact = report["artifact_initialization"]
    total = 118453870 + 9081518
    require(artifact["fixture"]["total_artifact_bytes"] == total, "Artifact fixture size differs")
    for arm, multiplier in (("baseline", 2), ("candidate", 1)):
        validation = artifact["validation"][arm]
        require(all(validation[key] is True for key in ("identity_equal", "fingerprint_equal", "bytes_equal"))
                and validation["read_bytes"] == validation["artifact_hash_bytes"] == total * multiplier,
                "Verified artifact equality or exact half I/O contract failed")
        expected_events.append({"event": "artifacts-validated", "arm": arm, "validation": validation})
    latency = artifact["latency"]
    balanced(latency["observations"], 4, ("elapsed_ns", "process_cpu_ns"))
    require(all(row["exact_equal"] is True and "error" not in row for row in latency["observations"])
            and len({row["model_fingerprint"] for row in latency["observations"]}) == 1,
            "Measured artifact identity differs")
    audit_summary(latency, "elapsed_ns")
    require(latency["process_cpu"] == semantic_summary(latency["observations"], "process_cpu_ns"), "Artifact CPU summary differs")
    for row in latency["observations"]:
        expected_events.append({"event": "artifact-latency-started", **{key: row[key] for key in ("pair", "position", "arm")}})
        expected_events.append({"event": "artifact-latency", "observation": row})
    expected_events.append({"event": "completed", "report_sha256": sha(path.read_bytes())})
    require(events == expected_events, "Semantic append-only event ledger is incomplete, reordered or differs from the report")
    return {"state": "complete", "ranking_latency_calls": 16, "allocation_calls": 8, "artifact_latency_calls": 8}


def audit_directory(work, manifest, identity):
    report = read(work / "reports/directory-runtime.json")
    events = [json.loads(line) for line in (work / "reports/directory-runtime.events.jsonl").read_text().splitlines()]
    require(report["protocol"] == "directory-runtime-v1" and report["status"] == "completed"
            and report["protocol_parameters_match"] is True and report["native_backend_loaded"] is False,
            "Directory run is incomplete or has a different backend/protocol")
    require(report["sources"]["baseline"]["commit"] == BASELINE
            and report["sources"]["candidate"]["head"] == identity["commit"]
            and report["sources"]["candidate"]["source_status"] == "", "Directory source identity differs")
    for arm in ("baseline", "candidate"):
        require(report["sources"][arm]["source_sha256"] == source_hash(manifest, arm, "src/memory_book/store.py"),
                "Directory source hash differs")
    require(report["sources"]["harness_sha256"] == source_hash(manifest, "candidate", "scripts/benchmark_directory_runtime.py")
            and report["sources"]["protocol_sha256"] == source_hash(manifest, "candidate", "benchmarks/directory-runtime-plan.json"),
            "Directory evaluator hash differs")
    require(report["arguments"]["rounds"] == 4 and report["arguments"]["iterations"] == 20
            and report["arguments"]["baseline_commit"] == BASELINE and report["arguments"]["validate_only"] is False,
            "Directory arguments differ")
    require(report["environment"]["github_run_id"] == identity["id"]
            and report["environment"]["github_run_attempt"] == "1", "Directory workflow identity differs")
    configurations = report["configurations"]
    require([(item["sections"], item["page_limit"]) for item in configurations]
            == [(sections, pages) for sections in (1, 20, 100) for pages in (1, 20, 100)], "Directory matrix differs")
    expected_events = [{"event": "started", "arguments": report["arguments"]}]
    for configuration in configurations:
        require(configuration["exact_equality"] is True, "Directory exact equality failed")
        audits = configuration["audit"]
        require(audits["baseline"]["output_sha256"] == audits["candidate"]["output_sha256"]
                and all(audits[arm]["content_length_evaluations"] == audits[arm]["materialized_previews"]
                        == configuration["sections"] * configuration["page_limit"] for arm in ("baseline", "candidate")),
                "Directory output or bounded materialization differs")
        for arm in ("baseline", "candidate"):
            audit = audits[arm]
            require(audit["select_count"] == sum(sql.lstrip().upper().startswith("SELECT") for sql in audit["statements"])
                    == (3 + 3 * configuration["sections"] if arm == "baseline" else 5)
                    and audit["statement_count"] == len(audit["statements"]), "Directory SQL audit differs")
        expected_events.append({"event": "audit", "configuration": configuration["id"], "audit": audits})
        require([trial["round"] for trial in configuration["rounds"]] == list(range(4)), "Directory rounds are incomplete")
        for trial in configuration["rounds"]:
            order = ["baseline", "candidate"] if trial["round"] % 2 == 0 else ["candidate", "baseline"]
            require(trial["order"] == order and set(trial["arms"]) == set(order), "Directory arm order differs")
            for position, arm in enumerate(order):
                rows = trial["arms"][arm]
                require([row["call"] for row in rows] == list(range(20)), "Directory call sequence is incomplete")
                for row in rows:
                    require(row["exact_equality"] is True and "error" not in row
                            and row["output_sha256"] == audits[arm]["output_sha256"]
                            and all(type(row[metric]) is int and row[metric] > 0 for metric in ("wall_ns", "process_cpu_ns")),
                            "Directory measured output or timing is invalid")
                    expected_events.append({"event": "call", "configuration": configuration["id"],
                        "round": trial["round"], "order_position": position, "arm": arm, **row})
            expected_events.append({"event": "round_completed", "configuration": configuration["id"], "round": trial["round"]})
        for metric in ("wall_ns", "process_cpu_ns"):
            medians = {arm: statistics.median(row[metric] for trial in configuration["rounds"] for row in trial["arms"][arm])
                       for arm in ("baseline", "candidate")}
            ratios = [statistics.median(row[metric] for row in trial["arms"]["candidate"])
                      / statistics.median(row[metric] for row in trial["arms"]["baseline"]) for trial in configuration["rounds"]]
            require(configuration["summary"][metric] == {"median_per_call": medians,
                    "paired_candidate_over_baseline": ratios, "median_paired_ratio": statistics.median(ratios)},
                    "Directory summary differs from raw observations")
    expected_events.append({"event": "completed", "configurations": 9})
    require(events == expected_events,
            "Directory event ledger is incomplete or differs from the report")
    return {"state": "complete", "configurations": 9, "timed_calls": sum(row["event"] == "call" for row in events)}


def audit_snapshot(work, identity, outcomes):
    result = {"state": "incomplete", "remeasured_calls": 0, "components": {}, "errors": []}
    try:
        manifest = verify_frozen(work, identity)
    except Exception as error:
        result["errors"].append({"stage": "frozen-source", "type": type(error).__name__, "message": str(error)})
        return result
    for name, auditor in (("semantic", audit_semantic), ("directory", audit_directory)):
        try:
            result["components"][name] = auditor(work, manifest, identity)
        except Exception as error:
            result["components"][name] = {"state": "incomplete-or-invalid", "error": {"type": type(error).__name__, "message": str(error)}}
    successful = all(outcomes.get(name) == "success" for name in STEPS)
    if successful and all(item["state"] == "complete" for item in result["components"].values()):
        result["state"] = "complete"
    return result


def collect(work, destination):
    originals = {}
    if work.exists():
        for source in sorted(work.rglob("*")):
            if source.is_dir() and not source.is_symlink():
                continue
            name = source.relative_to(work).as_posix()
            require(stat.S_ISREG(source.lstat().st_mode), "Evidence input is not a regular file: " + name)
            raw = source.read_bytes()
            write_new(destination / "raw" / name, raw)
            originals["raw/" + name] = inventory(raw)
    return originals


def publish(destination, branch):
    ref = "refs/heads/" + branch
    environment = dict(os.environ, GIT_AUTHOR_NAME="Afloat", GIT_AUTHOR_EMAIL="ShuffleMonkey@163.com",
                       GIT_COMMITTER_NAME="Afloat", GIT_COMMITTER_EMAIL="ShuffleMonkey@163.com")
    with tempfile.TemporaryDirectory(prefix="comprehensive-evidence-index-") as temporary:
        environment["GIT_INDEX_FILE"] = str(Path(temporary) / "index")
        git("read-tree", "--empty", env=environment)
        for path in sorted(destination.rglob("*")):
            if path.is_dir():
                continue
            require(stat.S_ISREG(path.lstat().st_mode), "Evidence tree contains a non-regular file")
            name = path.relative_to(destination).as_posix()
            blob = git("hash-object", "-w", "--stdin", input=path.read_bytes()).stdout.decode().strip()
            git("update-index", "-z", "--index-info", input=f"100644 {blob}\t{name}\0".encode(), env=environment)
        tree = git("write-tree", env=environment).stdout.decode().strip()
    existing = git("ls-remote", "--exit-code", "origin", ref, check=False)
    require(existing.returncode in (0, 2), "Unable to check whether the evidence ref already exists")
    if existing.returncode == 0:
        commit = existing.stdout.decode().split()[0]
        git("fetch", "--no-tags", "--filter=blob:none", "--depth=1", "origin", commit)
        require(git("rev-parse", commit + "^{tree}").stdout.decode().strip() == tree,
                "Existing evidence differs; it will not be overwritten")
        return {"commit": commit, "tree": tree, "already_preserved": True}
    commit = git("commit-tree", tree, "-m", "evidence: preserve comprehensive runtime " + os.environ["GITHUB_RUN_ID"],
                 env=environment).stdout.decode().strip()
    git("push", "origin", commit + ":" + ref)
    require(git("ls-remote", "--exit-code", "origin", ref).stdout.decode().split()[0] == commit,
            "Published evidence ref differs")
    return {"commit": commit, "tree": tree, "already_preserved": False}


def preserve():
    identity = hosted_identity()
    work, preservation = ROOT / WORK_PATH, ROOT / PRESERVATION_PATH
    destination = preservation / "evidence"
    destination.mkdir(parents=True, exist_ok=False)
    outcomes = {name: os.environ.get("COMPREHENSIVE_" + name.upper() + "_OUTCOME", "unavailable") for name in STEPS}
    branch = "validation/evidence-comprehensive-v010-" + identity["id"] + "-1"
    checkpoint = {"stage": "collecting", "branch": branch, "source_run": identity}
    try:
        originals = collect(work, destination)
        recovered = {}
        if not (work / "source-manifest.json").exists():
            # A setup failure may precede freeze. Preserve the committed inputs
            # as recovery evidence, but never treat this as a pre-run freeze.
            recovered = {"recorded_after_failure": True, "files": {}}
            try:
                freeze_tree(destination / "recovered-inputs", "candidate", identity["commit"],
                            ("src/memory_book", "tests", *EVALUATOR_PATHS), recovered["files"])
            except Exception as error:
                recovered["error"] = failure(error)
        audit = audit_snapshot(destination / "raw", identity, outcomes)
        try:
            clean_source()
            verify_frozen(work, identity, check_worktree=True)
        except Exception as error:
            audit["state"] = "incomplete"
            audit["errors"].append({"stage": "final-source-check", "type": type(error).__name__, "message": str(error)})
        write_new(destination / "audit.json", encoded(audit))
        write_new(destination / "evidence-manifest.json", encoded({"protocol": PROTOCOL, "repository": REPOSITORY,
            "source_run": identity, "evidence_branch": branch, "workflow_steps": outcomes, "original_files": originals,
            "recovered_inputs": recovered, "audit": audit,
            "scope": "All raw outputs and frozen inputs; no remeasurement, source branch changes, or corpus databases."}))
        write_new(destination / "README.md", (f"# Comprehensive runtime evidence\n\nHosted run {identity['id']}, attempt 1, source `{identity['commit']}`.\n"
            f"Preservation audit: **{audit['state']}**. Incomplete or differing output is retained and fails the job.\n\n"
            "`evidence-manifest.json` hashes every original byte under `raw/`, including failed or partial reports, logs and ledgers.\n"
            "`raw/source-manifest.json` binds the frozen source, workflow, evaluator and prospective protocol.\n"
            "This is component evidence; all regressions remain visible and no universal or end-to-end speedup is claimed.\n"
            "Allocation values are tracemalloc-tracked peaks, including NumPy registered buffers, not total RSS or untracked SQLite/native allocations.\n").encode())
        checkpoint.update(stage="publishing", audit=audit)
        published = publish(destination, branch)
        checkpoint.update(stage="completed", **published)
        print(json.dumps(checkpoint), flush=True)
        require(audit["state"] == "complete", "Evidence was preserved, but one or more components or preflight steps were incomplete or invalid")
    except BaseException as error:
        checkpoint["error"] = failure(error)
        raise
    finally:
        write_new(preservation / "preservation-result.json", encoded(checkpoint))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "check", "preserve"))
    command = parser.parse_args(argv).command
    {"freeze": freeze, "check": check, "preserve": preserve}[command]()


if __name__ == "__main__":
    main()
