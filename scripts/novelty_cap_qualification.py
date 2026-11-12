"""Finite, separately bound regression qualification; historical helpers stay byte-identical."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import round2_data
from benchmarks.round2_eval import (Ledger, atomic, digest, evaluator_sources, export, native,
    now, sha, summary_of, write_report)
from benchmarks.round2_resources import Resources, storage
from benchmarks.run import engine_source_hash
from benchmarks.semantic_eval import paired_changes
from scripts.run_round2_validation import execute, git, host_record, snapshot
from scripts.summarize_round2_validation import verify_configurations, verify_samples

PLAN = ROOT / "benchmarks/experiments/novelty-cap-qualification-plan.json"
BINDING = ROOT / "benchmarks/experiments/novelty-cap-qualification-binding.json"
HISTORICAL = ROOT / "benchmarks/round2_candidate.json"
NEW_FILES = ("scripts/novelty_cap_qualification.py", ".github/workflows/novelty-cap-qualification.yml",
             "benchmarks/experiments/novelty-cap-qualification-plan.json", "tests/test_novelty_cap_qualification.py")
VARIANTS = [
    {"name": "current-default", "source": "current", "semantic": False, "helper_stage": "candidate-native"},
    {"name": "cap-default", "source": "cap", "semantic": False, "helper_stage": "candidate-native"},
    {"name": "current-q2", "source": "current", "semantic": True, "helper_stage": "candidate-semantic-native"},
    {"name": "cap-q2", "source": "cap", "semantic": True, "helper_stage": "candidate-semantic-native"}]


def require(value, message):
    if not value:
        raise ValueError(message)


def actions_identity():
    run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/novelty-cap-qualification-run"
            and run.isdigit() and attempt == "1", "Only the dedicated Actions ref and first attempt may score or publish")
    return run + "-" + attempt


def vectors_digest(path):
    """Read-only digest of vector rows, excluding semantic_meta timing JSON."""
    hasher = hashlib.sha256(b"semantic_vectors/page_id,ordinal,char_start,char_end,vector/v1\n")
    rows = vector_bytes = 0
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(semantic_vectors)")]
        require(columns == ["page_id", "ordinal", "char_start", "char_end", "vector"], "Unexpected vector schema")
        revision, fingerprint = db.execute("SELECT revision,model_fingerprint FROM semantic_meta WHERE singleton=1").fetchone()
        for page, ordinal, start, end, vector in db.execute("SELECT page_id,ordinal,char_start,char_end,vector FROM semantic_vectors ORDER BY page_id,ordinal"):
            header = json.dumps([page, ordinal, start, end], ensure_ascii=False, separators=(",", ":")).encode()
            require(type(vector) is bytes and len(vector) == 384 * 4, "Unexpected vector representation")
            hasher.update(len(header).to_bytes(8, "big") + header + len(vector).to_bytes(8, "big") + vector)
            rows += 1; vector_bytes += len(vector)
    return {"sha256": hasher.hexdigest(), "rows": rows, "vector_bytes": vector_bytes,
        "revision": revision, "model_fingerprint": fingerprint,
        "boundary": "All semantic_vectors columns in primary-key order, length-prefixed JSON identity/offset fields and exact BLOB bytes. No semantic_meta timestamps or model rerun."}


def registered_inputs(require_binding=True):
    plan = json.loads(PLAN.read_bytes())
    historical = json.loads(HISTORICAL.read_bytes())
    require(sha(HISTORICAL) == plan["historical_binding_sha256"] and len(historical["evaluator_sha256"]) == 58,
            "Historical binding differs")
    require(evaluator_sources() == historical["evaluator_sha256"], "A historical frozen helper changed")
    require(plan["status"] == "frozen-before-regression-qualification" and plan["variants"] == VARIANTS,
            "Candidate/source-mode registration is incomplete")
    require(plan["native"] == {"budget_chars": [2000, 8000], "tokenizers": ["cl100k_base", "o200k_base"]}
            and plan["common"] == {"repeats": 1, "limit": 5, "max_page_chars": 900, "cache_size": 0,
                "use_cache": False, "coverage": False, "default_semantic": False, "tokenizer_version": "0.12.0"}, "Registered axes changed")
    require(plan["phases"] == [{"name": "A", "token_budgets": [512], "expected_calls": 4096},
        {"name": "B", "token_budgets": [1024, 2048], "expected_calls": 8192, "requires": "A qualified"}], "Phase axes/counts changed")
    require(sha(ROOT / plan["cohort"]["manifest"]) == plan["cohort"]["manifest_sha256"], "Cohort manifest changed")
    manifest = json.loads(round2_data.MANIFEST.read_bytes())
    require(manifest["dataset_sha256"] == plan["cohort"]["dataset_sha256"]
            and manifest["selected_ids_sha256"] == plan["cohort"]["selected_ids_sha256"]
            and manifest["expected_queries"] == plan["cohort"]["queries"] == 256
            and manifest["required_evidence"] == plan["cohort"]["required_evidence"] == 614,
            "Registered cohort identity differs")
    for source in plan["sources"].values():
        require(re.fullmatch(r"[0-9a-f]{40}", source["commit"] or "")
                and re.fullmatch(r"[0-9a-f]{64}", source["source_sha256"] or ""), "Require exact source pins")
    files = {name: sha(ROOT / name) for name in NEW_FILES}
    git("ls-files", "--error-unmatch", "--", *NEW_FILES)
    git("diff", "--exit-code", "HEAD", "--", *NEW_FILES)
    if require_binding:
        git("ls-files", "--error-unmatch", "--", str(BINDING.relative_to(ROOT)))
        git("diff", "--exit-code", "HEAD", "--", str(BINDING.relative_to(ROOT)))
        binding = json.loads(BINDING.read_bytes())
        require(binding["plan_sha256"] == sha(PLAN) and binding["sources"] == plan["sources"]
                and binding["new_files_sha256"] == files
                and binding["historical_files_sha256"] == historical["evaluator_sha256"], "Qualification binding differs")
    else:
        binding = None
    return plan, binding, manifest, files, historical


def verify_source_delta(plan):
    current, candidate = (plan["sources"][name]["commit"] for name in ("current", "cap"))
    changed = git("diff", "--name-only", current, candidate, "--", "src/memory_book").splitlines()
    require(changed == ["src/memory_book/store.py"], "Unexpected runtime file changed")
    before = git("show", current + ":src/memory_book/store.py")
    after = git("show", candidate + ":src/memory_book/store.py")
    old = "(1 + len(matched[pending[i][\"rid\"]] - covered) / len(qset)))"
    new = "(1 + min(0.25, len(matched[pending[i][\"rid\"]] - covered) / len(qset))))"
    require(before.count(old) == 1 and before.count("RECALL_VERSION = 10") == 1, "Unexpected control source")
    require(after == before.replace(old, new).replace("RECALL_VERSION = 10", "RECALL_VERSION = 11"),
            "Only the registered cap and cache-version correction are permitted")


def bind(args):
    require(not BINDING.exists(), "Never replace an existing qualification binding")
    plan, _, _, files, historical = registered_inputs(False)
    verify_source_delta(plan)
    for name, path in (("current", args.current_src), ("cap", args.cap_src)):
        from benchmarks.token_compare import checkout_provenance
        require(engine_source_hash(path / "memory_book") == plan["sources"][name]["source_sha256"]
                and checkout_provenance(path / "memory_book")["git_commit"] == plan["sources"][name]["commit"], "Source checkout differs")
    atomic(BINDING, {"schema_version": 1, "status": "frozen-before-regression-qualification", "bound_at": now(),
        "plan_sha256": sha(PLAN), "sources": plan["sources"], "new_files_sha256": files,
        "historical_files_sha256": historical["evaluator_sha256"]})
    print(json.dumps({"binding_sha256": sha(BINDING), "new_files": len(files), "historical_files": 58}))
    return 0


def helper_plan(plan, phase):
    return {"baseline": plan["sources"]["current"], "cohort": {"seed": plan["cohort"]["seed"]},
            "common": plan["common"], "native": {**plan["native"], "token_budgets": phase["token_budgets"]}}


def worker_spec(plan, phase_name, variant_name):
    phase = next(p for p in plan["phases"] if p["name"] == phase_name)
    variant = next(v for v in plan["variants"] if v["name"] == variant_name)
    # The frozen native function recognizes its exact semantic stage name.
    # Each call receives a NEW, explicitly registered source object; neither
    # historical round2_candidate.json nor its frozen_inputs gate is altered.
    return phase, variant, helper_plan(plan, phase), {"candidate": plan["sources"][variant["source"]]}


def worker(args):
    plan, binding, manifest, _, _ = registered_inputs()
    run_id = actions_identity()
    require(args.host_id == run_id, "Worker host/run identity differs")
    cp_path = ROOT / "benchmarks/reports" / ("novelty-cap-" + run_id + "-checkpoint.json")
    cp = json.loads(cp_path.read_bytes())
    result_dir = ROOT / "benchmarks/results" / ("novelty-cap-" + run_id)
    worker_name = "export" if args.variant == "export" else args.phase + "-" + args.variant
    private = ROOT / ".artifacts/novelty-cap" / run_id
    role = "current" if args.variant == "export" else next(v["source"] for v in VARIANTS if v["name"] == args.variant)
    require(cp["run_id"] == run_id and cp["host"]["id"] == run_id
            and cp["source_commit"] == git("rev-parse", "HEAD") and cp["plan_sha256"] == sha(PLAN)
            and cp["binding_sha256"] == sha(BINDING) and cp["workers"][worker_name]["status"] == "running",
            "Worker lacks its registered running checkpoint")
    require(args.output.resolve() == (result_dir / worker_name).resolve()
            and args.state.resolve() == (private / "states" / worker_name).resolve()
            and args.bundle.resolve() == (private / "bundle.json").resolve()
            and args.source.resolve() == (private / role / "src").resolve()
            and args.model_dir.resolve() == (private / "model").resolve(), "Worker paths differ from the registered run")
    if args.variant != "export":
        require(cp["phases"][args.phase]["status"] == "running", "Worker phase is not running")
    if args.phase == "B":
        require(cp["phases"]["A"]["status"] == "qualified", "B requires the saved A qualification")
        gate_path = result_dir / "A-gate.json"
        require(sha(gate_path) == cp["phases"]["A"]["gate_sha256"], "Saved A gate bytes differ")
        verified_a = assess_phase(plan, binding, manifest, cp, plan["phases"][0], result_dir)
        require(verified_a["status"] == "qualified" and json.loads(gate_path.read_bytes()) == verified_a,
                "A gate does not match its verified same-run records")
    require(not args.state.exists() and not any(Path(str(args.output) + s).exists() for s in (".json.gz", ".summary.json")), "Fresh worker/output required")
    args.state.mkdir(parents=True)
    phase, variant = (None, None)
    if args.variant == "export":
        args.stage = "export"
        hp, hb = {"baseline": plan["sources"]["current"]}, {}
    else:
        phase, variant, hp, hb = worker_spec(plan, args.phase, args.variant)
        args.stage = variant["helper_stage"]
    report = {"schema_version": 1, "protocol": plan["protocol"], "stage": args.stage, "host_id": args.host_id,
        "plan_sha256": sha(PLAN), "qualification_binding_sha256": sha(BINDING), "started_at": now(),
        "qualification": {"phase": args.phase, "variant": args.variant, "source": plan["sources"][variant["source"] if variant else "current"],
                          "semantic": variant["semantic"] if variant else False},
        "historical_files_sha256": binding["historical_files_sha256"], "new_files_sha256": binding["new_files_sha256"],
        "configurations": [], "timing_rows": [], "validation": {"passed": False, "failures": []}, "configured_generative_model_calls": 0}
    ledger, resources = Ledger(args.state / "attempts.jsonl"), Resources()
    try:
        data = round2_data.load(args.data)
        report["dataset"] = data.description()
        if args.variant == "export":
            export(args, hp, hb, data, report, resources)
        else:
            bundle = json.loads(args.bundle.read_bytes())
            require(bundle["dataset"]["sha256"] == data.fingerprint == plan["cohort"]["dataset_sha256"]
                    and digest(bundle["documents"]) == bundle["documents_sha256"] == plan["cohort"]["documents_sha256"]
                    and digest(bundle["diagnostics"]) == bundle["diagnostics_sha256"] == plan["cohort"]["diagnostics_sha256"], "Frozen pages/diagnostics differ")
            report["frozen_corpus"] = {k: v for k, v in bundle.items() if k not in {"documents", "diagnostics"}}
            native(args, hp, hb, data, bundle, report, ledger, resources)
            if variant["semantic"] and report["validation"]["passed"]:
                report["semantic_vectors_digest"] = vectors_digest(args.state / "native.db")
        registered_inputs()
    except BaseException as error:
        report["validation"] = {"passed": False, "failures": [{"check": "worker_exception", "error_type": type(error).__name__}]}
    finally:
        ledger.close()
        report.update(finished_at=now(), resources=resources.close(), ledger_sha256=sha(args.state / "attempts.jsonl"),
                      attempts_started=ledger.started, attempts_finished=ledger.finished)
        report["attempt_states"] = [json.loads(line) for line in (args.state / "attempts.jsonl").read_text().splitlines()]
        write_report(report, args.output)
    print(json.dumps({"variant": args.variant, "phase": args.phase, "validation": report["validation"], "finished": ledger.finished}))
    return 0 if report["validation"]["passed"] else 2


def compare_reports(before, after):
    require(len(before["configurations"]) == len(after["configurations"]), "Configuration counts differ")
    comparisons = []
    for left, right in zip(before["configurations"], after["configurations"], strict=True):
        axes = {k: left[k] for k in ("budget_chars", "tokenizer", "budget_tokens")}
        require(axes == {k: right[k] for k in axes}, "Configuration order differs")
        require([r["id"] for r in left["query_results"]] == [r["id"] for r in right["query_results"]], "Question order differs")
        changes = paired_changes(left["query_results"], right["query_results"])
        comparisons.append({**axes, **changes, "current_metrics": left["metrics"], "cap_metrics": right["metrics"],
            "current_groups": left["by_group"], "cap_groups": right["by_group"]})
    losses = any(c["complete_question_losses"] or c["annotation_losses"] for c in comparisons)
    return {"status": "rejected" if losses else "qualified", "comparisons": comparisons}


def load_pair(cp, name, result_dir):
    prefix = result_dir / name
    record = cp["workers"][name]
    expected = {str(Path(str(prefix) + s).relative_to(ROOT)): sha(Path(str(prefix) + s)) for s in (".json.gz", ".summary.json")}
    require(record["status"] == "completed" and record["exit_code"] == 0 and record["outputs"] == expected, "Worker incomplete or corrupted: " + name)
    raw = gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes())
    report = json.loads(raw)
    require(json.loads(Path(str(prefix) + ".summary.json").read_bytes()) == summary_of(report, hashlib.sha256(raw).hexdigest()), "Raw/summary projection differs")
    ledger_path = result_dir / (name + ".attempts.jsonl.gz")
    ledger = gzip.decompress(ledger_path.read_bytes())
    require(cp["workers"][name]["ledger_output"] == {"path": str(ledger_path.relative_to(ROOT)),
        "sha256": sha(ledger_path), "raw_sha256": hashlib.sha256(ledger).hexdigest(), "raw_bytes": len(ledger)}
        and hashlib.sha256(ledger).hexdigest() == report["ledger_sha256"], "Published attempt ledger differs")
    require([json.loads(line) for line in ledger.decode().splitlines()] == report["attempt_states"], "Attempt ledger projection differs")
    return report


def verify_identity(report, plan, binding, cp):
    require(report["validation"] == {"passed": True, "failures": []}
            and report["protocol"] == plan["protocol"] and report["host_id"] == cp["host"]["id"]
            and report["plan_sha256"] == sha(PLAN) and report["qualification_binding_sha256"] == sha(BINDING)
            and report["historical_files_sha256"] == binding["historical_files_sha256"]
            and report["new_files_sha256"] == binding["new_files_sha256"]
            and report["configured_generative_model_calls"] == 0, "Worker identity/integrity differs")


def verify_export(plan, binding, manifest, cp, result_dir):
    report = load_pair(cp, "export", result_dir)
    verify_identity(report, plan, binding, cp)
    corpus = report["frozen_corpus"]
    require(report["stage"] == "export" and report["source_unchanged"] is True
            and report["qualification"] == {"phase": "A", "variant": "export", "source": plan["sources"]["current"], "semantic": False}
            and corpus["source_provenance"]["git_commit"] == plan["sources"]["current"]["commit"]
            and corpus["source_sha256"] == plan["sources"]["current"]["source_sha256"]
            and report["dataset"]["sha256"] == corpus["dataset"]["sha256"] == manifest["dataset_sha256"]
            and corpus["documents_sha256"] == plan["cohort"]["documents_sha256"]
            and corpus["diagnostics_sha256"] == plan["cohort"]["diagnostics_sha256"], "Export identity differs")
    verify_samples(report, helper_plan(plan, plan["phases"][0]), manifest["selected_ids"])
    verify_configurations(report, helper_plan(plan, plan["phases"][0]), manifest["selected_ids"])
    return report


def load_verified(plan, binding, manifest, cp, phase, variant, result_dir):
    name = phase["name"] + "-" + variant["name"]
    report = load_pair(cp, name, result_dir)
    verify_identity(report, plan, binding, cp)
    source = plan["sources"][variant["source"]]
    require(report["qualification"] == {"phase": phase["name"], "variant": variant["name"], "source": source, "semantic": variant["semantic"]}
            and report["stage"] == variant["helper_stage"], "Source/mode mapping differs")
    m = report["metadata"]
    require(m["source_provenance"]["git_commit"] == source["commit"]
            and m["source_sha256_before"] == m["source_sha256_after"] == source["source_sha256"]
            and m["source_unchanged"] and m["originals_unchanged"]
            and m["semantic"] is variant["semantic"] and m["coverage"] is False, "Source/mode invariant failed")
    require(report["dataset"]["sha256"] == manifest["dataset_sha256"]
            and report["frozen_corpus"]["documents_sha256"] == plan["cohort"]["documents_sha256"]
            and report["frozen_corpus"]["diagnostics_sha256"] == plan["cohort"]["diagnostics_sha256"], "Input identity differs")
    if variant["semantic"]:
        idx = report["preparation"]["semantic_index"]
        model = json.loads((ROOT / plan["model"]["plan"]).read_bytes())["model"]
        require(idx["model_fingerprint"] == plan["model"]["fingerprint"]
                and idx["inference_threads"] == 1 and idx["model"]["files"] == model["files"], "Model identity differs")
        vectors = report["semantic_vectors_digest"]
        require(vectors["rows"] == idx["windows"] and vectors["vector_bytes"] == idx["vector_bytes"]
                and vectors["revision"] == idx["revision"] and vectors["model_fingerprint"] == idx["model_fingerprint"], "Vector digest identity differs")
    hp = helper_plan(plan, phase)
    verify_samples(report, hp, manifest["selected_ids"])
    verify_configurations(report, hp, manifest["selected_ids"])
    require(all(c["metrics"]["queries"] == c["metrics"]["answerable_queries"] == 256
                and c["metrics"]["required_evidence"] == 614 for c in report["configurations"]), "Scored denominator changed")
    return report


def assess_phase(plan, binding, manifest, cp, phase, result_dir):
    verify_export(plan, binding, manifest, cp, result_dir)
    reports = {v["name"]: load_verified(plan, binding, manifest, cp, phase, v, result_dir) for v in VARIANTS}
    require(sum(r["attempts_started"] for r in reports.values()) == sum(r["attempts_finished"] for r in reports.values()) == phase["expected_calls"], "Phase call count differs")
    comparisons = {mode: compare_reports(reports["current-" + mode], reports["cap-" + mode]) for mode in ("default", "q2")}
    require(reports["current-q2"]["semantic_vectors_digest"] == reports["cap-q2"]["semantic_vectors_digest"],
            "Current and cap semantic vectors differ; do not attribute the result to the cap")
    return {"schema_version": 1, "phase": phase["name"], "status": "qualified" if all(r["status"] == "qualified" for r in comparisons.values()) else "rejected",
        "expected_calls": phase["expected_calls"], "actual_finished_calls": sum(r["attempts_finished"] for r in reports.values()),
        "plan_sha256": sha(PLAN), "binding_sha256": sha(BINDING), "comparisons": comparisons,
        "semantic_vectors_digest": reports["current-q2"]["semantic_vectors_digest"],
        "gate": "Zero per-question complete-evidence losses and zero per-annotation losses in every configuration and both modes. Gains never offset losses. This is stricter than the development aggregate gate.",
        "interpretation": "Previously-scored regression qualification only; one pass is not performance evidence or proof of generalization."}


def public_names(cp_path, result_dir, plan):
    names = [cp_path]
    prefixes = ["export"] + [p["name"] + "-" + v["name"] for p in plan["phases"] for v in VARIANTS]
    names += [Path(str(result_dir / p) + s) for p in prefixes for s in (".json.gz", ".summary.json", ".attempts.jsonl.gz")]
    names += [result_dir / (p["name"] + "-gate.json") for p in plan["phases"]]
    names += [result_dir / "qualification.json", result_dir / "report.md"]
    return [p for p in names if p.exists()]


def publish(cp_path, result_dir, plan, parent):
    run_id = actions_identity()
    branch = "refs/heads/validation/novelty-cap-" + run_id
    files = public_names(cp_path, result_dir, plan)
    require(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to((ROOT / "benchmarks").resolve()) for p in files), "Non-public publication path")
    existing = git("ls-remote", "--heads", "origin", branch)
    require(not existing or existing.split()[0] == parent, "Another writer changed the results branch")
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git("read-tree", parent, env=env)
        git("add", "--", *(str(p.relative_to(ROOT)) for p in files), env=env)
        tree = git("write-tree", env=env)
        msg = Path(directory) / "message.txt"
        msg.write_text("bench: preserve capped-novelty qualification stage and decision\n")
        commit = git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                     "commit-tree", tree, "-p", parent, "-F", str(msg), env=env)
        git("push", "origin", commit + ":" + branch)
    return commit


def run(args):
    plan, binding, manifest, _, _ = registered_inputs()
    verify_source_delta(plan)
    run_id = actions_identity()
    private = ROOT / ".artifacts/novelty-cap" / run_id
    require(not private.exists(), "No implicit replay of an existing run")
    private.mkdir(parents=True)
    result_dir = ROOT / "benchmarks/results" / ("novelty-cap-" + run_id)
    result_dir.mkdir(parents=True, exist_ok=False)
    cp_path = ROOT / "benchmarks/reports" / ("novelty-cap-" + run_id + "-checkpoint.json")
    require(not cp_path.exists(), "Existing checkpoint cannot be overwritten")
    parent = git("rev-parse", "HEAD")
    cp = {"schema_version": 1, "protocol": plan["protocol"], "status": "running", "run_id": run_id,
        "source_commit": parent, "host": host_record(run_id), "plan_sha256": sha(PLAN), "binding_sha256": sha(BINDING),
        "started_at": now(), "preparation": {}, "workers": {}, "phases": {"A": {"status": "pending"}, "B": {"status": "not-run", "reason": "Requires A qualified"}}}
    deadline = time.monotonic() + 5400
    def persist():
        nonlocal parent
        atomic(cp_path, cp)
        parent = publish(cp_path, result_dir, plan, parent)
    try:
        persist()
        for role, source in plan["sources"].items():
            snapshot(private / role, source["commit"])
        cp["preparation"]["status"] = "running"; persist()
        data = round2_data.prepare_data(private / "data")
        os.environ["TIKTOKEN_CACHE_DIR"] = str(private / "tokenizers")
        from benchmarks.token_compare import TokenCounter
        for encoding in plan["native"]["tokenizers"]:
            TokenCounter(encoding).count("explicit tokenizer preparation")
        model = private / "model"
        subprocess.run([sys.executable, "scripts/prepare_semantic_model.py", "--output", str(model)], cwd=ROOT, check=True, timeout=600)
        cp["preparation"] = {"status": "completed", "model_storage": storage(model), "data_storage": storage(private / "data")}; persist()
        def measured(phase_name, variant_name, role):
            name = "export" if variant_name == "export" else phase_name + "-" + variant_name
            prefix = result_dir / name
            command = [sys.executable, "scripts/novelty_cap_qualification.py", "worker", "--phase", phase_name,
                "--variant", variant_name, "--data", str(data), "--source", str(private / role / "src"),
                "--bundle", str(private / "bundle.json"), "--model-dir", str(model),
                "--state", str(private / "states" / name), "--output", str(prefix), "--host-id", run_id]
            record = {"status": "running", "started_at": now(), "argv": command}
            cp["workers"][name] = record; persist()
            try:
                code = execute(command, deadline - time.monotonic(), private / (name + ".log"))
                record.update(status="completed" if code == 0 else "failed", exit_code=code)
            except BaseException as error:
                record.update(status="interrupted", error_type=type(error).__name__)
                raise
            finally:
                record["finished_at"] = now()
                record["outputs"] = {str(Path(str(prefix) + s).relative_to(ROOT)): sha(Path(str(prefix) + s))
                    for s in (".json.gz", ".summary.json") if Path(str(prefix) + s).is_file()}
                ledger = private / "states" / name / "attempts.jsonl"
                if ledger.is_file():
                    raw = ledger.read_bytes()
                    target = result_dir / (name + ".attempts.jsonl.gz")
                    target.write_bytes(gzip.compress(raw, mtime=0))
                    record["ledger_output"] = {"path": str(target.relative_to(ROOT)), "sha256": sha(target),
                                               "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw)}
                persist()
            require(record["status"] == "completed", "Worker failed; no replay")
        measured("A", "export", "current")
        verify_export(plan, binding, manifest, cp, result_dir)
        for phase in plan["phases"]:
            name = phase["name"]
            require(name == "A" or cp["phases"]["A"]["status"] == "qualified", "B cannot run before A qualifies")
            cp["phases"][name] = {"status": "running"}; persist()
            for variant in VARIANTS:
                measured(name, variant["name"], variant["source"])
            decision = assess_phase(plan, binding, manifest, cp, phase, result_dir)
            target = result_dir / (name + "-gate.json"); atomic(target, decision)
            cp["phases"][name] = {"status": decision["status"], "actual_finished_calls": decision["actual_finished_calls"],
                "gate_path": str(target.relative_to(ROOT)), "gate_sha256": sha(target)}; persist()
            if decision["status"] == "rejected":
                cp["status"] = "rejected"
                if name == "A":
                    cp["phases"]["B"] = {"status": "not-run", "reason": "A rejected under preregistered zero-loss gate"}
                break
        else:
            cp["status"] = "qualified-regression-only-awaiting-separate-decision"
    except BaseException as error:
        cp.update(status="failed-incomplete", error_type=type(error).__name__)
        for phase in cp["phases"].values():
            if phase["status"] == "running":
                phase["status"] = "failed-incomplete"
    finally:
        cp["finished_at"] = now()
        conclusion = {"schema_version": 1, "status": cp["status"], "run_id": run_id, "source_commit": cp["source_commit"],
            "plan_sha256": sha(PLAN), "binding_sha256": sha(BINDING), "phases": copy.deepcopy(cp["phases"]),
            "sources": plan["sources"], "no_automatic_merge": True, "interpretation": plan["limits"]}
        atomic(result_dir / "qualification.json", conclusion)
        (result_dir / "report.md").write_text("# Capped-novelty regression qualification\n\nStatus: **" + cp["status"] + "**.\n\n"
            + "\n".join("- Phase " + key + ": **" + value["status"] + "**." for key, value in cp["phases"].items())
            + "\n\n" + plan["gates"]["explanation"] + "\n\n" + plan["limits"] + "\n")
        cp["conclusion_outputs"] = {str(p.relative_to(ROOT)): sha(p) for p in (result_dir / "qualification.json", result_dir / "report.md")}
        persist()
    print(json.dumps({"status": cp["status"], "run_id": run_id, "phases": cp["phases"]}))
    return 0 if cp["status"] == "qualified-regression-only-awaiting-separate-decision" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bind"); p.add_argument("--current-src", type=Path, required=True); p.add_argument("--cap-src", type=Path, required=True)
    sub.add_parser("run")
    sub.add_parser("check")
    p = sub.add_parser("worker")
    for name in ("data", "source", "bundle", "model-dir", "state", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--phase", choices=("A", "B"), required=True)
    p.add_argument("--variant", choices=("export", *(v["name"] for v in VARIANTS)), required=True)
    p.add_argument("--host-id", required=True)
    args = parser.parse_args()
    if args.command == "bind": return bind(args)
    if args.command == "run": return run(args)
    if args.command == "worker": return worker(args)
    registered_inputs(); print("qualification input binding verified; no scoring"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
