"""Frozen v0.3.3/v0.3.4 native and supplied-page comparison.

Only immutable, explicitly parameterized measurement/adapter functions are
reused. No historical registered_plan, frozen_inputs, selection or controller
is invoked or rebound. Fresh IDs are selected only by round6_comparison_data
after the new binding has been published and committed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round4_comparison as legacy

PLAN = ROOT / "benchmarks/experiments/round6-comparison-plan.json"
BINDING = ROOT / "benchmarks/experiments/round6-comparison-binding.json"
MANIFEST = ROOT / "benchmarks/experiments/round6-hotpot256-manifest.json"
VERSION = "round6-native-component-comparison-1"
PROTOCOL = "v034-fresh-native-component-comparison-v1"
MASTER_COMMIT = "afbb3233e16b80b3c0e5e76ab19466188abf41b4"
BASELINE = {"commit": "796cedfd1f5368144037a1fb72292b8d13884b8c",
            "source_sha256": "55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45"}
PREFIX = "AI-Memory-Book/v034/round6/2026-11-14/"
SEED = 41061  # The immutable measurement helpers' explicitly registered shuffle.
PACKAGES = {"tiktoken": "0.12.0", "pyarrow": "26.0.1"}
NODE = "v24.22.1"
REPOSITORY = "Afloat16/AI-Memory-Book"
TRIGGER = "refs/heads/ci/v034-round6-comparison-run"
FREEZE_TRIGGER = "refs/heads/ci/v034-round6-comparison-freeze"
NATIVE = ("baseline-native", "candidate-native")
COMPONENTS = ("baseline-component", "candidate-component", "claude-mem-fts",
              "ai-memory-hybrid", "billion-context")
PRIOR_MANIFESTS = ("benchmarks/hotpot_manifest.json", "benchmarks/round2_hotpot256_manifest.json",
                   "benchmarks/experiments/round3-hotpot256-manifest.json",
                   "benchmarks/experiments/round4-hotpot256-manifest.json")
NEW_FILES = ("scripts/round6_comparison.py", "scripts/round6_comparison_data.py",
             "scripts/round6_comparison_controller.py", "tests/test_round6_comparison.py",
             ".github/workflows/round6-comparison.yml", "benchmarks/experiments/round6-comparison-plan.json",
             "benchmarks/experiments/round6-plan.json")
EXTRA_REUSED_FILES = ("scripts/round4_comparison.py", "scripts/benchmark_default_recall.py",
                      "benchmarks/round2_candidate.json", *PRIOR_MANIFESTS)
UPSTREAM_LOCKS = legacy.reused.UPSTREAM_LOCKS
reused = legacy.reused
require = legacy.require
sha = legacy.sha
file_sha = legacy.file_sha
source_identity = legacy.source_identity
public_paths = legacy.public_paths
save_ledger = legacy.save_ledger
read_report = legacy.read_report
write_report = legacy.write_report
default_equivalence = legacy.default_equivalence
comparisons = legacy.comparisons


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=60,
                                   stderr=subprocess.DEVNULL)


def relative_file(name):
    require(isinstance(name, str), "Evaluator path must be text")
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == name,
            "Evaluator path must be canonical and repository-relative")
    target = ROOT / path
    require(target.is_file() and not target.is_symlink()
            and target.resolve().is_relative_to(ROOT.resolve()), "Missing/unsafe evaluator file: " + name)
    return target


def require_committed(path, commit="HEAD"):
    name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    relative_file(name)
    require(Path(path).read_bytes() == git("show", commit + ":" + name),
            "Commit the exact input before use: " + name)


def runtime_hash(commit):
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "Require exact runtime commit")
    require(git("rev-parse", commit + "^{commit}").decode().strip() == commit, "Invalid runtime commit")
    prefix = "src/memory_book/"
    names = sorted(name for name in git("ls-tree", "-r", "--name-only", commit, "--", prefix).decode().splitlines()
                   if name.endswith(".py"))
    require(bool(names), "Runtime commit contains no product Python files")
    value = hashlib.sha256()
    for name in names:
        value.update(name.removeprefix(prefix).encode() + b"\0" + git("show", commit + ":" + name) + b"\0")
    return value.hexdigest()


def validate_plan(plan):
    axes = plan["independent_validation"]
    require(plan["schema_version"] == 1 and plan["protocol"] == PROTOCOL
            and plan["status"] == "registered-before-fresh-selection-and-scoring"
            and plan["master_plan"] == {"path": "benchmarks/experiments/round6-plan.json", "commit": MASTER_COMMIT}
            and plan["baseline"] == {"release": "v0.3.3", "commit": BASELINE["commit"],
                                     "runtime_sha256": BASELINE["source_sha256"]}
            and plan["candidate"]["release"] == "v0.3.4", "Comparison plan identity differs")
    cohort, native, components = (axes[key] for key in ("cohort", "native", "components"))
    require(cohort["count"] == 256 and cohort["exclude_prior_count"] == 896
            and cohort["selection_prefix"] == PREFIX and cohort["prior_manifests"] == list(PRIOR_MANIFESTS)
            and cohort["prior_counts"] == [128, 256, 256, 256]
            and native["modes"] == ["v033_lexical", "candidate_lexical"]
            and native["tokenizers"] == list(legacy.ENCODINGS) and native["token_budgets"] == [512, 1024, 2048]
            and native["budget_chars"] == 8000 and native["limit"] == 5 and native["repeats"] == 1
            and native["calls"] == 3072 and components["repeats"] == 3 and components["top_k"] == 5
            and components["book_budget_chars"] == 100000 and components["search_calls"] == 3840
            and components["modes"] == ["v033_lexical", "candidate_lexical", "claude_mem_supplied_source_fts",
                                         "ai_memory_released_binary", "billion_locked_search_kernel"]
            and axes["stages"] == ["export", *NATIVE, *COMPONENTS] and axes["retrieval_and_search_calls"] == 6912
            and axes["quality_cells"] == 42 and axes["query_shuffle_seed"] == SEED
            and axes["optional_semantic"] is False and axes["optional_project_statistics"] is False,
            "Registered selection or complete comparison axes changed")
    dependencies = plan["dependencies"]
    require(dependencies["python_minor"] == "3.12" and dependencies["node"] == NODE
            and dependencies["python_packages"] == PACKAGES and dependencies["upstream_locks"] == UPSTREAM_LOCKS,
            "Registered language/package/upstream pins changed")
    return plan


def registered_plan():
    require_committed(PLAN)
    plan = validate_plan(json.loads(PLAN.read_bytes()))
    master = relative_file(plan["master_plan"]["path"])
    require(master.read_bytes() == git("show", MASTER_COMMIT + ":" + plan["master_plan"]["path"]),
            "Original round-six master registration changed")
    return plan


def requested_candidate(plan):
    candidate = plan["candidate"]
    require(isinstance(candidate["commit"], str) and re.fullmatch(r"[0-9a-f]{40}", candidate["commit"])
            and isinstance(candidate["runtime_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", candidate["runtime_sha256"]),
            "Declare and commit the exact final candidate before the freeze")
    require(candidate["runtime_sha256"] != BASELINE["source_sha256"], "Candidate must contain a changed runtime")
    return {"commit": candidate["commit"], "source_sha256": candidate["runtime_sha256"]}


def evaluator_files(extras=()):
    """Pin the reused library bytes, without invoking its old identity chain."""
    registry = relative_file("benchmarks/round2_candidate.json")
    require(registry.read_bytes() == git("show", BASELINE["commit"] + ":benchmarks/round2_candidate.json"),
            "Historical helper registry differs from the published baseline")
    hashes = json.loads(registry.read_bytes())["evaluator_sha256"]
    require(len(hashes) == 58, "Expected the complete immutable helper registry")
    result = {}
    for name in sorted(set(hashes) | set(EXTRA_REUSED_FILES)):
        raw = relative_file(name).read_bytes()
        require(raw == git("show", BASELINE["commit"] + ":" + name), "Reused helper/lock/history changed: " + name)
        if name in hashes:
            require(sha(raw) == hashes[name], "Historical helper hash changed: " + name)
        result[name] = sha(raw)
    for name in (*NEW_FILES, *extras):
        require(name not in {str(BINDING.relative_to(ROOT)), str(MANIFEST.relative_to(ROOT))},
                "Binding and future manifest must not be self-bound")
        result[name] = file_sha(relative_file(name))
    return dict(sorted(result.items()))


def model_identity():
    lock = json.loads(relative_file(UPSTREAM_LOCKS["ai-memory"]).read_bytes())
    return {"engine": "ai-memory-hybrid", "embedding_provider": "local", "model": lock["embedding_model"]}


def stages(binding):
    require(binding["optional_semantic"] is False and binding["optional_project_statistics"] is False,
            "Only the registered default lexical Book modes may execute")
    return ["export", *NATIVE, *COMPONENTS]


def host_record():
    boot = Path("/proc/sys/kernel/random/boot_id")
    require(platform.system() == "Linux" and boot.is_file(), "Live resource measurements require Linux boot identity")
    identity = {"node": platform.node(), "boot_id": boot.read_text().strip(),
                "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    return {**identity, "id": reused.digest(identity), "python": platform.python_version(),
            "platform": platform.platform(), "sqlite": sqlite3.sqlite_version, "logical_cpus": os.cpu_count(),
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES}}


def verify_asset_receipt(receipt, sources, lock_hashes):
    require(receipt["schema_version"] == 1 and receipt["status"] == "all-assets-verified-before-selection"
            and receipt["sources"] == sources and receipt["packages"] == PACKAGES
            and receipt["upstream_locks_sha256"] == lock_hashes and receipt["model"] == model_identity()
            and receipt["optional_semantic"] is False and receipt["question_content_read"] is False
            and receipt["measurement_calls"] == 0
            and receipt["language_runtimes"]["node"] == NODE
            and receipt["language_runtimes"]["python"].startswith("3.12."),
            "Assets/dependencies/models were not completely verified before selection")
    expected = {"baseline_source", "candidate_source", "reference_tokenizers", "ai_memory_binary_and_models",
                "claude_mem_sources_and_bun", "billion_kernel_sources"}
    require(set(receipt["preparation"]) == expected
            and all(row["status"] == "completed" for row in receipt["preparation"].values()),
            "Pre-selection preparation has missing or failed assets")


def bind(args):
    plan = registered_plan()
    require(args.output.resolve() == BINDING.resolve(), "Use only the registered binding path")
    require(not args.output.exists() and not MANIFEST.exists(), "Never replace a binding or select before its freeze")
    sources = {key: source_identity(value) for key, value in (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources == {"baseline": BASELINE, "candidate": requested_candidate(plan)}, "Declared sources differ")
    preflight = Path(args.asset_verification)
    name = preflight.resolve().relative_to(ROOT.resolve()).as_posix()
    require(name.startswith("benchmarks/reports/round6-comparison-freeze-")
            and preflight.name == "asset-verification.json", "Unexpected asset receipt path")
    require_committed(preflight)
    extras = [name]
    hashes = evaluator_files(extras)
    commit = args.evaluator_commit
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "Exact evaluator commit is required")
    for path, expected in hashes.items():
        require(sha(git("show", commit + ":" + path)) == expected, "Commit every evaluator input before binding: " + path)
    lock_hashes = {key: file_sha(ROOT / path) for key, path in UPSTREAM_LOCKS.items()}
    verify_asset_receipt(json.loads(preflight.read_bytes()), sources, lock_hashes)
    require({name: importlib.metadata.version(name) for name in PACKAGES} == PACKAGES,
            "Freeze environment differs from registered dependencies")
    value = {"schema_version": 1, "evaluator": VERSION, "status": "frozen-before-selection",
        "created_at": reused.now(), "plan_sha256": file_sha(PLAN), **sources,
        "optional_semantic": False, "optional_project_statistics": False,
        "upstream_locks": UPSTREAM_LOCKS, "upstream_lock_sha256": lock_hashes,
        "asset_verification": {"path": name, "sha256": file_sha(preflight)}, "model": model_identity(),
        "evaluator_commit": commit, "evaluator_files": hashes, "extra_evaluator_files": extras,
        "packages": PACKAGES, "language_runtimes": {"python_minor": "3.12", "node": NODE},
        "policy": "Publish binding before fresh ID selection, publish manifest before scoring; one claimed execution, no implicit replay."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def frozen_inputs(binding_path=BINDING):
    require(Path(binding_path).resolve() == BINDING.resolve(), "Use only the registered binding path")
    plan = registered_plan()
    require_committed(binding_path)
    binding = json.loads(Path(binding_path).read_bytes())
    require(binding["schema_version"] == 1 and binding["evaluator"] == VERSION
            and binding["status"] == "frozen-before-selection"
            and binding["plan_sha256"] == file_sha(PLAN)
            and binding["baseline"] == BASELINE and binding["candidate"] == requested_candidate(plan)
            and binding["optional_semantic"] is False and binding["optional_project_statistics"] is False
            and binding["packages"] == PACKAGES and binding["model"] == model_identity()
            and binding["language_runtimes"] == {"python_minor": "3.12", "node": NODE}
            and binding["upstream_locks"] == UPSTREAM_LOCKS,
            "New comparison binding source/policy/dependency/model identity differs")
    require(binding["evaluator_files"] == evaluator_files(binding["extra_evaluator_files"]), "Evaluator bytes changed")
    for name, expected in binding["evaluator_files"].items():
        require(sha(git("show", binding["evaluator_commit"] + ":" + name)) == expected,
                "Evaluator input did not exist before selection: " + name)
    for label in ("baseline", "candidate"):
        require(runtime_hash(binding[label]["commit"]) == binding[label]["source_sha256"], "Bound runtime changed: " + label)
    locks = {key: file_sha(ROOT / path) for key, path in UPSTREAM_LOCKS.items()}
    require(binding["upstream_lock_sha256"] == locks, "Upstream source/binary/model lock changed")
    receipt = binding["asset_verification"]
    require(set(receipt) == {"path", "sha256"} and binding["extra_evaluator_files"] == [receipt["path"]]
            and binding["evaluator_files"].get(receipt["path"]) == receipt["sha256"], "Asset receipt was not bound")
    verify_asset_receipt(json.loads(relative_file(receipt["path"]).read_bytes()),
                         {key: binding[key] for key in ("baseline", "candidate")}, locks)
    return plan, binding


def verify_report(report, plan, binding, query_ids):
    require(report["stage"] in stages(binding) and report["evaluator"] == VERSION
            and report["protocol"] == PROTOCOL, "Report belongs to another comparison/mode")
    # This helper only checks the explicit plan/binding/report arguments and
    # saved rows. Its historical freeze/selection functions are never called.
    legacy.verify_report(report, plan, binding, query_ids)



def verify_claim(commit, binding_path, manifest_path, source, run_id, *, published=False):
    """Require the exact claim commit; offline audits need no network access."""
    require(isinstance(commit, str) and re.fullmatch("[0-9a-f]{40}", commit), "Missing exact execution claim")
    fingerprint = file_sha(binding_path)
    name = "benchmarks/reports/round6-comparison-claim-" + fingerprint + ".json"
    raw = git("show", commit + ":" + name)
    value = json.loads(raw)
    require(value["schema_version"] == 1 and value["status"] == "claimed-before-preparation"
            and value["run_id"] == run_id and value["source_commit"] == source
            and value["binding_sha256"] == fingerprint
            and value["cohort_manifest_sha256"] == file_sha(manifest_path)
            and git("rev-parse", commit + "^").decode().strip() == source,
            "Execution claim source, run or input identity differs")
    if published:
        branch = "refs/heads/validation/round6-comparison-claim-" + fingerprint
        remote = git("ls-remote", "--heads", "origin", branch).decode().split()
        require(remote == [commit, branch], "Execution claim was not published immutably")
    return value


def worker_command(args):
    """The public stage intent excludes its own not-yet-created commit ID."""
    command = [sys.executable, "-u", "scripts/round6_comparison.py", "worker"]
    for name in ("stage", "binding", "manifest", "data", "bundle", "frozen_db", "state",
                 "cache", "output", "host_id", "execution_claim"):
        command += ["--" + name.replace("_", "-"), str(getattr(args, name))]
    if args.source is not None:
        command += ["--source", str(args.source)]
    return command


def require_worker_paths(args, run_id):
    """A published claim cannot be replayed into fresh alternate directories."""
    require(re.fullmatch(r"[0-9]+-1", run_id), "Invalid claimed worker run")
    root = ROOT.resolve()
    private = root / ".artifacts/round6-comparison" / run_id
    paths = {"state": private / "states" / args.stage,
        "output": root / "benchmarks/results" / ("round6-comparison-" + run_id) / args.stage,
        "bundle": private / "frozen-pages.json", "frozen_db": private / "states/export/frozen.db",
        "data": private / "private/hotpot-dev-distractor.parquet",
        "cache": private / "cache"}
    if args.stage == "export" or args.stage.startswith("baseline-"):
        paths["source"] = private / "baseline/src"
    elif args.stage.startswith("candidate-"):
        paths["source"] = private / "candidate/src"
    else:
        require(args.source is None, "External worker must not override the frozen runtime source")
    for name, expected in paths.items():
        value = getattr(args, name, None)
        require(value is not None and Path(value).resolve() == expected,
                "Worker must use the claim's canonical " + name + " path")


def verify_intent(commit, checkpoint, stage, binding, *, argv=None, published=False):
    """Verify the exact committed running-stage intent, also during offline audit."""
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
            "Missing exact running-stage intent")
    run_id = checkpoint["run_id"]
    require(re.fullmatch(r"[0-9]+-1", run_id), "Invalid intent run identity")
    name = "benchmarks/reports/round6-comparison-" + run_id + "-checkpoint.json"
    intent = json.loads(git("show", commit + ":" + name))
    fields = ("schema_version", "protocol", "run_id", "source_commit", "claim_commit",
              "plan_sha256", "binding_sha256", "cohort_manifest_sha256", "result_directory")
    require(all(intent.get(key) == checkpoint[key] for key in fields)
            and intent["host"]["id"] == checkpoint["host"]["id"]
            and intent["status"] == "running", "Running-stage intent belongs to another run or state")
    ordered = stages(binding)
    require(stage in ordered, "Unregistered stage intent")
    position = ordered.index(stage)
    require(list(intent["stages"]) == ordered[:position + 1], "Stage intent is not the next registered stage")
    require(all(intent["stages"][prior]["status"] == "completed"
                and intent["stages"][prior]["exit_code"] == 0 for prior in ordered[:position]),
            "Prior stage was not completed before this intent")
    record = intent["stages"][stage]
    require(record["status"] == "running" and "exit_code" not in record and "finished_at" not in record,
            "Intent does not authorize a new running stage")
    require(argv is None or record["argv"] == argv, "Worker arguments differ from the committed stage intent")
    git("merge-base", "--is-ancestor", checkpoint["claim_commit"], commit)
    if published:
        branch = "refs/heads/validation/round6-comparison-" + run_id
        require(git("ls-remote", "--heads", "origin", branch).decode().split() == [commit, branch],
                "Running-stage intent is not the current published checkpoint")
    return intent




Resources = legacy.Resources
export = legacy.export
native = legacy.native
component = legacy.component


def worker(args):
    require(os.environ.get("ORT_DISABLE_TELEMETRY") == "1", "Disable ORT telemetry before process launch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT", "1") == "1", "No implicit Actions rerun")
    plan, binding = frozen_inputs(args.binding)
    source_commit = git("rev-parse", "HEAD").decode().strip()
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/v034-round6-comparison-run"
            and os.environ.get("GITHUB_EVENT_NAME") == "push" and run_id.isdigit() and attempt == "1"
            and os.environ.get("GITHUB_SHA") == source_commit,
            "A scored worker requires the claimed first-attempt comparison push")
    verify_claim(args.execution_claim, args.binding, args.manifest, source_commit,
                 run_id + "-" + attempt, published=True)
    require(args.stage in stages(binding) and args.output.name == args.stage, "Unregistered stage/output name")
    run_id += "-" + attempt
    require_worker_paths(args, run_id)
    identity = {"schema_version": 1, "protocol": plan["protocol"], "run_id": run_id,
        "source_commit": source_commit, "claim_commit": args.execution_claim,
        "host": {"id": args.host_id}, "plan_sha256": file_sha(PLAN),
        "binding_sha256": file_sha(args.binding), "cohort_manifest_sha256": file_sha(args.manifest),
        "result_directory": "benchmarks/results/round6-comparison-" + run_id}
    verify_intent(args.execution_intent, identity, args.stage, binding,
                  argv=worker_command(args), published=True)
    require(not args.state.exists() and not any(path.exists() for path in public_paths(args.output)),
            "Never replay or overwrite an existing worker")
    host = host_record()
    require(host["id"] == args.host_id and host["packages"] == PACKAGES, "Worker host/dependency binding differs")
    require_committed(args.manifest)
    args.state.mkdir(parents=True)
    ledger = reused.Ledger(args.state / "attempts.jsonl")
    resources = Resources()
    report = {"schema_version": 1, "evaluator": VERSION, "protocol": plan["protocol"], "stage": args.stage,
        "status": "running", "host": host, "host_id": host["id"], "started_at": reused.now(),
        "source_commit": source_commit, "execution_claim": args.execution_claim,
        "execution_intent": args.execution_intent, "plan_sha256": file_sha(PLAN),
        "binding_sha256": file_sha(args.binding), "cohort_manifest_sha256": file_sha(args.manifest),
        "evaluator_files": binding["evaluator_files"], "ort_disable_telemetry": "1",
        "configured_generative_model_calls": 0, "configurations": [], "timing_rows": [],
        "validation": {"passed": False, "failures": []}}
    data = None
    try:
        from scripts.round6_comparison_data import load
        data = load(args.data, args.binding, args.manifest)
        report["dataset"] = data.description()
        if args.stage == "export":
            export(args, plan, binding, data, report, resources)
        else:
            exported = read_report(args.output.parent / "export")
            require(exported["host_id"] == host["id"] and exported["binding_sha256"] == report["binding_sha256"]
                    and exported["cohort_manifest_sha256"] == report["cohort_manifest_sha256"], "Export belongs to another host/protocol")
            verify_report(exported, plan, binding, [case.id for case in data.queries])
            require(file_sha(args.bundle) == exported["private_bundle_sha256"]
                    and file_sha(args.frozen_db) == exported["frozen_database_sha256"], "Canonical private artifacts changed")
            bundle = json.loads(args.bundle.read_bytes())
            require(bundle["dataset"]["sha256"] == data.fingerprint
                    and reused.digest(bundle["documents"]) == bundle["documents_sha256"]
                    and reused.digest(bundle["diagnostics"]) == bundle["diagnostics_sha256"], "Frozen corpus digest differs")
            report["frozen_corpus"] = exported["frozen_corpus"]
            if args.stage.endswith("native"):
                native(args, plan, binding, data, bundle, report, ledger, resources)
            else:
                component(args, plan, binding, data, bundle, report, ledger, resources)
        require(frozen_inputs(args.binding)[1] == binding, "Evaluator binding changed during worker")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed-incomplete", validation={"passed": False,
            "failures": [{"check": "stage_exception", "error_type": type(error).__name__}]})
    finally:
        ledger.close()
        report.update(finished_at=reused.now(), resources=resources.close(),
            ledger_sha256=file_sha(args.state / "attempts.jsonl"), attempts_started=ledger.started,
            attempts_finished=ledger.finished,
            attempt_states=[json.loads(line) for line in (args.state / "attempts.jsonl").read_text().splitlines()])
        if report["status"] == "completed":
            try:
                verify_report(report, plan, binding, [case.id for case in data.queries])
            except Exception as error:
                report.update(status="failed-incomplete", validation={"passed": False,
                    "failures": [{"check": "strict_stage_assessment", "error_type": type(error).__name__}]})
        save_ledger(args.state, args.output)
        write_report(report, args.output)
    print(json.dumps({"stage": args.stage, "status": report["status"], "validation": report["validation"],
                      "attempts_started": ledger.started, "attempts_finished": ledger.finished}))
    return 0 if report["status"] == "completed" else 2


def upstream_identities():
    result = {}
    for name, path in UPSTREAM_LOCKS.items():
        lock = json.loads(relative_file(path).read_bytes())
        result[name] = {"repository": lock["repository"], "commit": lock["commit"],
            "version": lock.get("version", lock.get("package_version")), "lock_path": path,
            "lock_sha256": file_sha(ROOT / path)}
        if name == "ai-memory":
            result[name].update(binary_sha256=lock["binary_sha256"], embedding_model=lock["embedding_model"])
        if name == "claude-mem":
            result[name]["runtime"] = lock["runtime"]
    return result


def markdown(assessment, reports):
    """Reuse the immutable table renderer, replacing all old experiment claims."""
    rendered = legacy.markdown(assessment, reports)
    rendered = rendered.replace("Round four", "Round six")
    replacements = {
        "The selection excludes all 640 IDs from Hotpot128, round-two Hotpot256 and round-three Hotpot256.":
        "The selection excludes all 896 IDs from Hotpot128 and the round-two, round-three and round-four Hotpot256 cohorts.",
        "Optional Q2 gains and losses are retained; integrity does not imply a quality improvement.":
        "Q2 is excluded. All baseline and competitor gains and losses remain visible; integrity does not imply an advantage over another component.",
        "Native Book stages separately record fresh ingestion and optional model/index construction. Component Book stages copy one canonical archive and measure their own setup/index costs. Q2's persisted native/component index-vector digests match; this does not assert separately measured query-embedding identity.":
        "Native Book stages separately record fresh ingestion and initialization. Component Book stages copy one canonical archive and measure their own setup costs. Both Book modes are lexical; only ai-memory uses its locked local embedding model.",
        "No quality or project-statistics candidate is included.":
        "Q2 and project-statistics candidates are excluded. Complete default output equality is required; no quality-changing candidate is included.",
    }
    for old, new in replacements.items():
        if assessment["validation"]["passed"]:
            require(old in rendered, "Immutable rendering boundary changed")
        rendered = rendered.replace(old, new)
    if not assessment["validation"]["passed"]:
        return rendered
    lines = [rendered.rstrip(), "", "## Exact sources and upstream identities", "",
             "| Role | Commit | Runtime SHA256 or locked version |", "|---|---|---|"]
    for name, source in assessment["sources"].items():
        lines.append(f"| Book {name} | `{source['commit']}` | `{source['source_sha256']}` |")
    for name, source in assessment["upstream_identities"].items():
        version = source["version"] or "locked search kernel"
        lines.append(f"| {name} | `{source['commit']}` | {version} |")
    lines += ["", f"Binding SHA256 `{assessment['binding_sha256']}`; selected-ID SHA256 "
              f"`{assessment['selected_ids_sha256']}`. The exact dependency, binary, model and source-lock "
              "hashes remain in the committed binding and machine-readable assessment.", "",
              "## Candidate versus every external component", "",
              "Each row compares the same first-response whole-block projection. Positive complete-evidence "
              "change favors the candidate. Per-question and annotation gains and losses are retained in "
              "assessment.json; neither adverse rows nor ties are omitted.", "",
              "| Comparator | Tokenizer | Cap | Candidate minus comparator complete evidence, pp | Complete question gains | Complete question losses |",
              "|---|---|---:|---:|---:|---:|"]
    for name, values in assessment["competitor_changes"].items():
        for row in values:
            delta = 100 * (row["after"]["complete_evidence_rate"] - row["before"]["complete_evidence_rate"])
            lines.append(f"| {name} | {row['tokenizer']} | {row['budget_tokens']} | {delta:+.4f} | "
                         f"{len(row['complete_question_gains'])} | {len(row['complete_question_losses'])} |")
    lines += ["", f"The registered matrix has **{assessment['quality_cells']} quality cells**, "
              f"**{assessment['retrieval_and_search_calls']:,} native retrieval/search calls** and "
              f"**{assessment['ai_memory_page_read_calls']:,} separately counted ai-memory page reads**. "
              "No generated-answer call is made. Search timing is sequential and descriptive; the independent "
              "registered 10%/15%/10% balanced performance gates are assessed separately.", "",
              "All native p50/p95, component first/repeat search distributions, offline packing, setup, "
              "RSS and storage values remain in the complete stage reports, including regressions. "
              "A comparison win does not establish whole-product, cross-domain or universal superiority."]
    return "\n".join(lines) + "\n"


def assess(checkpoint_path, binding_path=BINDING, manifest_path=MANIFEST, *, verify_existing=False):
    plan, binding = frozen_inputs(binding_path)
    from scripts.round6_comparison_data import committed_manifest
    _, manifest = committed_manifest(binding_path, manifest_path)
    checkpoint = json.loads(Path(checkpoint_path).read_bytes())
    run_id = checkpoint["run_id"]
    require(re.fullmatch(r"[0-9]+-1", run_id), "Invalid comparison run identity")
    require(checkpoint["result_directory"] == "benchmarks/results/round6-comparison-" + run_id,
            "Assessment directory must be the registered run's exact directory")
    directory = ROOT / checkpoint["result_directory"]
    require(directory.resolve().is_relative_to((ROOT / "benchmarks/results").resolve()), "Unsafe result directory")
    output = directory / "assessment.json"
    require(output.exists() if verify_existing else not output.exists(), "Never replace an assessment; use --verify-existing")
    expected_stages = stages(binding)
    reports, issues = {}, []
    equivalence = None
    try:
        verify_claim(checkpoint["claim_commit"], binding_path, manifest_path, checkpoint["source_commit"], run_id)
        require(checkpoint["protocol"] == PROTOCOL and checkpoint["plan_sha256"] == file_sha(PLAN)
                and checkpoint["binding_sha256"] == file_sha(binding_path)
                and checkpoint["cohort_manifest_sha256"] == file_sha(manifest_path), "Checkpoint identity differs")
        require(list(checkpoint["stages"]) == expected_stages and manifest["expected_queries"] == 256,
                "Missing or extra registered stage/query")
        for stage in expected_stages:
            record = checkpoint["stages"][stage]
            verify_intent(record["execution_intent"], checkpoint, stage, binding, argv=record["argv"])
            paths = public_paths(directory / stage)
            require(record["status"] == "completed" and record["exit_code"] == 0
                    and record["outputs"] == {str(path.relative_to(ROOT)): file_sha(path) for path in paths},
                    "Incomplete stage or checkpoint file hashes: " + stage)
            report = read_report(directory / stage)
            require(report["stage"] == stage and report["host_id"] == checkpoint["host"]["id"]
                    and report["host"]["packages"] == PACKAGES
                    and report["source_commit"] == checkpoint["source_commit"]
                    and report["execution_claim"] == checkpoint["claim_commit"]
                    and report["execution_intent"] == record["execution_intent"]
                    and report["plan_sha256"] == checkpoint["plan_sha256"]
                    and report["binding_sha256"] == checkpoint["binding_sha256"]
                    and report["cohort_manifest_sha256"] == checkpoint["cohort_manifest_sha256"]
                    and report["dataset"]["sha256"] == manifest["dataset_sha256"]
                    and report["dataset"]["queries"] == 256 and report["evaluator_files"] == binding["evaluator_files"]
                    and report["configured_generative_model_calls"] == 0 and report["ort_disable_telemetry"] == "1",
                    "Stage source/host/data identity differs: " + stage)
            verify_report(report, plan, binding, manifest["selected_ids"])
            require(all(c["metrics"]["required_evidence"] == manifest["required_evidence"]
                        and c["metrics"]["answerable_queries"] == 256 for c in report["configurations"]),
                    "Evidence/answerable denominator changed")
            if stage != "export":
                require(report["frozen_corpus"] == reports["export"]["frozen_corpus"], "Supplied corpus differs between engines")
            reports[stage] = report
        equivalence = default_equivalence(reports)
        require(equivalence["passed"] and equivalence["native_pairs"] == 1536
                and equivalence["component_pairs"] == 768, "Default complete output changed or pair count is incomplete")
        require(sum(len(reports[stage]["timing_rows"]) for stage in NATIVE) == 3072
                and sum(len(reports[stage]["timing_rows"]) for stage in COMPONENTS) == 3840
                and sum(len(report["configurations"]) for report in reports.values()) == 42,
                "The complete registered call/cell matrix did not finish")
    except Exception as error:
        issues.append({"check": str(error) if isinstance(error, ValueError) else "Missing/invalid stage artifact: " + type(error).__name__})
    assessment = {"schema_version": 1, "evaluator": VERSION, "run_id": run_id,
        "source_commit": checkpoint["source_commit"], "host": checkpoint["host"],
        "sources": {key: binding[key] for key in ("baseline", "candidate")}, "upstream_identities": upstream_identities(),
        "plan_sha256": file_sha(PLAN), "binding_sha256": file_sha(binding_path),
        "cohort_manifest_sha256": file_sha(manifest_path), "dataset_sha256": manifest["dataset_sha256"],
        "selected_ids_sha256": manifest["selected_ids_sha256"], "required_evidence": manifest["required_evidence"],
        "excluded_prior_queries": 896, "prior_selection_overlap": 0,
        "expected_stages": expected_stages, "verified_stages": list(reports),
        "validation": {"passed": not issues, "failures": issues}, "status": "failed-incomplete",
        "optional_semantic": False, "configured_generative_model_calls": 0,
        "performance_gate_evaluated": False, "default_payload_equivalence": equivalence}
    if not issues:
        assessment.update(status="complete-verified", native_calls=3072, component_search_calls=3840,
            retrieval_and_search_calls=6912, quality_cells=42,
            ai_memory_page_read_calls=sum(row["read_calls"] for row in reports["ai-memory-hybrid"]["timing_rows"]),
            book_version_native_changes=comparisons(reports["baseline-native"], reports["candidate-native"]),
            book_version_component_changes=comparisons(reports["baseline-component"], reports["candidate-component"]),
            competitor_changes={name: comparisons(reports[name], reports["candidate-component"])
                                for name in ("claude-mem-fts", "ai-memory-hybrid", "billion-context")},
            quality_candidate_included=False)
    rendered = markdown(assessment, reports)
    if verify_existing:
        require(json.loads(output.read_bytes()) == assessment and (directory / "report.md").read_text() == rendered,
                "Assessment/Markdown differ from strict raw recomputation")
    else:
        reused.atomic(output, assessment)
        with (directory / "report.md").open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    return assessment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("bind")
    p.add_argument("--baseline-src", type=Path, required=True)
    p.add_argument("--candidate-src", type=Path, required=True)
    p.add_argument("--asset-verification", type=Path, required=True)
    p.add_argument("--evaluator-commit", required=True)
    p.add_argument("--output", type=Path, default=BINDING)
    p = commands.add_parser("worker")
    p.add_argument("--stage", required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--binding", type=Path, default=BINDING)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    for name in ("bundle", "frozen-db", "state", "cache", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("host-id", "execution-claim", "execution-intent"):
        p.add_argument("--" + name, required=True)
    p = commands.add_parser("audit")
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--binding", type=Path, default=BINDING)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--verify-existing", action="store_true")
    commands.add_parser("host")
    args = parser.parse_args(argv)
    if args.command == "bind":
        bind(args)
        print(json.dumps({"binding": str(args.output.relative_to(ROOT)), "sha256": file_sha(args.output),
                          "measurement_calls": 0, "next": "Publish binding before selecting fresh IDs."}))
        return 0
    if args.command == "host":
        print(json.dumps(host_record()))
        return 0
    if args.command == "worker":
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        return worker(args)
    assessment = assess(args.checkpoint, args.binding, args.manifest, verify_existing=args.verify_existing)
    print(json.dumps({"status": assessment["status"], "validation": assessment["validation"]}))
    return 0 if assessment["status"] == "complete-verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
