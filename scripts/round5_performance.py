"""v0.3.3 versus published v0.3.2, with immutable complete-output evidence.

The frozen round-four measurement primitives are reused without changing their
bytes. This new controller binds new sources, retains every ABBA sample and
refuses to overwrite or repeat an existing binding claim or worker attempt.
No retrieval is performed by --bind, --audit, or the unit tests.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
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
from scripts import round4_performance as previous
from scripts.round4_performance import (CONFIGURATIONS, PACKAGES, ENCODINGS,
    Ledger, TokenCounter, atomic, dataset, digest, dump, exclusive,
    exclusive_bytes, git, host_identity, indexed_content, json_bytes,
    latency_summary, make_row, mcp_configuration, now, original_turn_texts,
    query_order, require, rss, schedule, sha, source_identity, stable_row,
    storage, verify_worker)
from benchmarks.resume import _lock

VERSION = "round5-default-performance-1"
PLAN = ROOT / "benchmarks/experiments/round5-plan.json"
BASELINE = {"commit": "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
            "runtime_sha256": "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"}
TOOLS = (*previous.HELPERS, "scripts/round4_performance.py",
         "scripts/round5_performance.py", "tests/test_round5_performance.py",
         "tests/test_round5_recall_work.py",
         ".github/workflows/round5-performance.yml")


def file_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in TOOLS}


def load_plan():
    plan = json.loads(PLAN.read_bytes())
    require(plan["protocol"] == "v033-exact-output-performance-v1"
            and plan["baseline"] == {"release": "v0.3.2", **BASELINE},
            "Round-five baseline or protocol changed")
    formal = plan["performance_candidate"]["formal"]
    require(formal["rounds"] == 4 and formal["calls"] == 56784
            and formal["engine_order"] == [["baseline", "candidate"],
                ["candidate", "baseline"], ["candidate", "baseline"], ["baseline", "candidate"]]
            and formal["cohorts"] == ["synthetic61", "public1015"]
            and formal["configs"] == list(CONFIGURATIONS),
            "Registered ABBA matrix changed")
    require(plan["thresholds_percent"] == {
        "geometric_mean_p95_improvement": 10,
        "at_least_one_public_native_token_p95_improvement": 15,
        "public_mcp_token1024_p95_improvement": 10,
        "maximum_pooled_p50_p95_regression": 5,
        "resource_mean_increase_review": 10}, "Registered gates changed")
    return plan


def bind(args):
    plan = load_plan()
    require(args.baseline_src and args.candidate_src, "Both source checkouts are required")
    sources = {label: source_identity(path) for label, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == BASELINE, "Use the published v0.3.2 tag as baseline")
    commit = git("rev-parse", "HEAD").decode().strip()
    hashes = file_hashes()
    for path, expected in {**hashes, str(PLAN.relative_to(ROOT)): sha(PLAN.read_bytes())}.items():
        require(sha(git("show", commit + ":" + path)) == expected,
                "Commit the exact plan, evaluator and tests before binding: " + path)
    for path in (*previous.HELPERS, "scripts/round4_performance.py"):
        require(sha(git("show", BASELINE["commit"] + ":" + path)) == hashes[path],
                "Historical measurement helper differs from v0.3.2: " + path)
    value = {"schema_version": 1, "evaluator": VERSION,
        "status": "frozen-before-formal-timing", "created_at": now(),
        "plan_sha256": sha(PLAN.read_bytes()), "sources": sources,
        "evaluator_commit": commit, "evaluator_files": hashes, "packages": PACKAGES,
        "policy": "One exclusive execution claim per binding; preserve every attempt and sample."}
    exclusive(args.bind, value)
    print(json.dumps({"binding": str(args.bind), "sha256": sha(args.bind.read_bytes()),
                      "next": "Commit this binding, then run the single formal comparison."}))


def load_binding(path):
    value = json.loads(path.read_bytes())
    require(value["evaluator"] == VERSION and value["status"] == "frozen-before-formal-timing",
            "Wrong round-five binding")
    require(value["plan_sha256"] == sha(PLAN.read_bytes())
            and value["evaluator_files"] == file_hashes()
            and value["packages"] == PACKAGES and value["sources"]["baseline"] == BASELINE,
            "Bound plan, evaluators, packages or baseline changed")
    relative = path.resolve().relative_to(ROOT).as_posix()
    require(path.read_bytes() == git("show", "HEAD:" + relative),
            "Commit the exact binding before timing")
    for name, expected in value["evaluator_files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == expected,
                "Evaluator provenance changed: " + name)
    return value


def execution_claim_path(binding):
    return binding.with_name(binding.name + ".execution.json")


def claim_execution(args, run):
    claim = {"schema_version": 1, "evaluator": VERSION, "created_at": now(),
             "binding_sha256": sha(args.binding.read_bytes()),
             "run_identity_sha256": digest(run), "host": run["host"],
             "state_dir": str(args.state_dir.resolve()), "output": str(args.output.resolve())}
    exclusive(execution_claim_path(args.binding), claim)
    return claim


class CheckpointPublicationError(RuntimeError):
    """Stop timing after any rejected or ambiguous Git checkpoint write."""


def publication_identity(args):
    if not getattr(args, "publish_branch", None):
        return None
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(re.fullmatch(r"[0-9]+", run_id) is not None and attempt == "1"
            and os.environ.get("GITHUB_REPOSITORY") == "Afloat16/AI-Memory-Book"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/ci/v033-round5-performance",
            "Publication requires the first-attempt registered hosted trigger")
    expected = "validation/v033-round5-performance-" + run_id + "-" + attempt
    require(args.publish_branch == expected, "Unexpected validation branch")
    public = ROOT / ("benchmarks/reports/round5-performance-" + run_id + "-" + attempt)
    require(args.output.resolve().parent == public.resolve(), "Unexpected public checkpoint directory")
    require(args.state_dir.resolve() != public.resolve(), "Keep mutable worker state separate from public checkpoints")
    return {"run_id": run_id, "run_attempt": attempt, "branch": expected,
            "claim_branch": "validation/v033-round5-claim-" + sha(args.binding.read_bytes())}


def export_checkpoint(args):
    """Publish immutable gzip ledgers; audit accepts them without raw duplication."""
    state, public = args.state_dir.resolve(), args.output.resolve().parent
    public.mkdir(parents=True, exist_ok=True)

    def preserve(destination, raw):
        if destination.exists():
            require(destination.is_file() and not destination.is_symlink()
                    and destination.read_bytes() == raw,
                    "Never replace an immutable exported artifact: " + str(destination))
        else:
            exclusive_bytes(destination, raw)

    if (state / "run.json").is_file():
        preserve(public / "run.json", (state / "run.json").read_bytes())
    if (state / "checkpoint.json").is_file():
        atomic(public / "checkpoint.json", json.loads((state / "checkpoint.json").read_bytes()))
    claim = execution_claim_path(args.binding)
    if claim.is_file():
        preserve(public / "execution.json", claim.read_bytes())
    for source in sorted((state / "workers").glob("*")):
        require(not source.is_symlink(), "Refuse symbolic checkpoint files")
        if source.is_file() and source.name.endswith((".started.json", ".json.gz", ".attempts.jsonl.gz")):
            preserve(public / "workers" / source.name, source.read_bytes())
        elif source.is_file() and source.name.endswith(".attempts.jsonl"):
            compressed = source.with_suffix(".jsonl.gz")
            if not compressed.exists():  # Preserve an abruptly interrupted call ledger verbatim.
                preserve(public / "workers" / compressed.name, gzip.compress(source.read_bytes(), mtime=0))


def publish_checkpoint(args, run, phase):
    publication = run.get("publication")
    if publication is None:
        return
    failure = args.output.resolve().parent / "publication-failure.json"
    require(not failure.exists(), "Prior checkpoint push failed; do not retry automatically")
    try:
        export_checkpoint(args)
        branch_ref = "refs/heads/" + publication["branch"]
        claim_ref = "refs/heads/" + publication["claim_branch"]
        head = git("rev-parse", "HEAD").decode().strip()
        remote = git("ls-remote", "--heads", "origin", branch_ref).decode().split()
        require(not remote or remote == [head, branch_ref], "Another writer advanced the result ref")
        public = args.output.resolve().parent.relative_to(ROOT).as_posix()
        claim = execution_claim_path(args.binding).resolve().relative_to(ROOT).as_posix()
        staged = git("diff", "--cached", "--name-only").decode().splitlines()
        require(all(path == claim or path.startswith(public + "/") for path in staged),
                "Unrelated staged changes must not enter a benchmark checkpoint")
        git("add", "--", public, claim)
        changed = git("diff", "--cached", "--name-only").decode().splitlines()
        require(changed and all(path == claim or path.startswith(public + "/") for path in changed),
                "Checkpoint is empty or includes an unrelated path")
        git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "bench: preserve round-five " + phase)
        if phase == "execution claimed":
            # Empty expected ref means create only. A simultaneous checkout or
            # later workflow cannot acquire this same binding a second time.
            git("push", "--force-with-lease=" + claim_ref + ":", "origin", "HEAD:" + claim_ref)
        git("push", "origin", "HEAD:" + branch_ref)
    except BaseException as error:
        if not failure.exists():
            exclusive(failure, {"phase": phase, "status": "publication-failed-no-automatic-retry",
                "error_type": type(error).__name__, "message": str(error), "at": now()})
        raise CheckpointPublicationError("Checkpoint publication failed; stopped before further timing") from error


def load_completed(state, item, run, plan):
    prefix = state / "workers" / item["key"]
    marker = json.loads(Path(str(prefix) + ".started.json").read_bytes())
    require(marker == {"worker": item, "run_identity_sha256": digest(run)}, "Worker start marker differs")
    value = json.loads(gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes()))
    ledger = gzip.decompress(Path(str(prefix) + ".attempts.jsonl.gz").read_bytes())
    raw = Path(str(prefix) + ".attempts.jsonl")
    if raw.exists():
        require(raw.read_bytes() == ledger, "Original and compressed attempt ledgers differ")
    verify_worker(value, run, plan, ledger=ledger)
    return value


def worker(args, plan, binding):
    state = args.state_dir.resolve()
    run = json.loads((state / "run.json").read_bytes())
    claim = json.loads(execution_claim_path(args.binding).read_bytes())
    require(claim["binding_sha256"] == sha(args.binding.read_bytes())
            and claim["run_identity_sha256"] == digest(run)
            and claim["state_dir"] == str(state), "Worker has no exact execution claim")
    item = next(s for s in run["schedule"] if s["key"] == args.worker)
    require(run["binding_sha256"] == sha(args.binding.read_bytes()) and run["host"] == host_identity(),
            "Worker binding/host differs from controller")
    marker = state / "workers" / (item["key"] + ".started.json")
    require(json.loads(marker.read_bytes()) == {"worker": item, "run_identity_sha256": digest(run)},
            "Worker has no matching controller intent")
    output = state / "workers" / (item["key"] + ".json.gz")
    ledger_path = state / "workers" / (item["key"] + ".attempts.jsonl")
    require(not output.exists() and not ledger_path.exists(), "A worker attempt already exists; never repeat it")
    src = Path(run["source_paths"][item["label"]])
    expected = binding["sources"][item["label"]]
    require(source_identity(src) == expected, "Worker runtime source differs")
    sys.path.insert(0, str(src))
    begin = time.perf_counter_ns()
    import memory_book
    from memory_book import MemoryBook
    imported_ms = (time.perf_counter_ns() - begin) / 1e6
    require(Path(memory_book.__file__).parent.resolve() == (src / "memory_book").resolve(),
            "Worker imported a different runtime")
    data = dataset(plan, item["cohort"], args.locomo_path)
    ids = [case.id for case in data.queries]
    require(ids == run["cohorts"][item["cohort"]]["query_ids_original_order"], "Worker query identities differ")
    report = {**item, "status": "started", "started_at": now(), "source": expected,
        "run_identity_sha256": digest(run), "runtime_import_ms": imported_ms,
        "dataset_sha256": data.fingerprint, "configurations": [], "error": None}
    ledger = Ledger(ledger_path)
    try:
        with tempfile.TemporaryDirectory(prefix="round5-perf-") as temporary:
            work = Path(temporary)
            db_path = work / "memory.db"
            begin = time.perf_counter_ns()
            with MemoryBook(db_path, cache_size=0) as book:
                report["native_open_ms"] = (time.perf_counter_ns() - begin) / 1e6
                begin = time.perf_counter_ns()
                ingested = [book.ingest(session) for session in data.sessions]
                report["fresh_ingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["fresh_ingestion_results_sha256"] = digest(ingested)
                report["native_memory_after_ingestion"] = rss()
                report["storage_after_ingestion_live"] = storage(book.db, db_path)
                begin = time.perf_counter_ns()
                replayed = [book.ingest(session) for session in data.sessions]
                report["unchanged_reingestion_ms"] = (time.perf_counter_ns() - begin) / 1e6
                report["unchanged_reingestion_results_sha256"] = digest(replayed)
                report["all_replayed_sessions_skipped"] = all(row["skipped"] for row in replayed)
                report["indexed_content"] = indexed_content(book.db)
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                sources = original_turn_texts(data)
                begin = time.perf_counter_ns()
                counters = {name: TokenCounter(name) for name in ENCODINGS}
                for counter in counters.values():
                    counter.count("Initialize reference tokenizer before query timing.")
                report["reference_tokenizer_initialization_ms"] = (time.perf_counter_ns() - begin) / 1e6
                cases = {case.id: case for case in data.queries}
                for index, config in enumerate(plan["performance_candidate"]["formal"]["configs"]):
                    order = query_order(ids, item["round"], index)
                    if config["surface"] == "official-sdk-mcp-stdio":
                        rows = asyncio.run(mcp_configuration(data, config, order, db_path, work, src,
                            counters, sources, pages, report, ledger))
                    else:
                        rows = []
                        for identity in order:
                            case = cases[identity]
                            before = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            require(before == 0, "Native result cache was not empty before timing")
                            options = {"project": case.project, "budget_chars": config["budget_chars"],
                                       "limit": 5, "use_cache": False}
                            if config["budget_tokens"] is not None:
                                options.update(budget_tokens=config["budget_tokens"], tokenizer="cl100k_base")
                            seq = ledger.start(config["id"], identity)
                            begin = time.perf_counter_ns()
                            response = book.recall(case.query, **options)
                            elapsed = (time.perf_counter_ns() - begin) / 1e6
                            response.pop("latency_ms")  # The sole excluded native response field.
                            after = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                            row = make_row(case, response, elapsed, dump(response), None, response, config,
                                counters, sources, pages, before, after, expected["runtime_sha256"])
                            ledger.finish(seq, config["id"], row)
                            rows.append(row)
                            require(not any(row["invariants"].values()), "Native provenance/budget/cache invariant failed")
                    report["configurations"].append({**config, "rows": rows,
                        "latency": latency_summary([r["wall_ms"] for r in rows])})
                    atomic(output, report, compressed=True)
                report["native_memory_after_calls"] = rss()
                report["native_recall_cache_rows"] = book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]
                report["indexed_content_after_calls"] = indexed_content(book.db)
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report["storage_after_checkpoint"] = storage(book.db, db_path)
        report["source_after"] = source_identity(src)
        require(report["source_after"] == expected, "Runtime source changed while measuring")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        ledger.close()
        raw_ledger = ledger_path.read_bytes()
        ledger_path.with_suffix(".jsonl.gz").write_bytes(gzip.compress(raw_ledger, mtime=0))
        report["ledger_sha256"] = sha(raw_ledger)
        report["finished_at"] = now()
        atomic(output, report, compressed=True)
    return 0


def validation(report):
    issues, canonical, total = [], {}, 0
    run, plan = report["run"], report["plan"]
    workers = report["workers"]
    if [w["key"] for w in workers] != [w["key"] for w in schedule(plan)]:
        issues.append("missing_duplicate_or_reordered_workers")
    for w in workers:
        try:
            total += verify_worker(w, run, plan)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(w.get("key", "unknown") + ":" + str(error))
            continue
        for field in ("indexed_content", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256",
                      "mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            key = (w["cohort"], field)
            if key in canonical and canonical[key] != w[field]:
                issues.append(w["key"] + ":" + field)
            canonical.setdefault(key, w[field])
        for c in w["configurations"]:
            for row in c["rows"]:
                key = (w["cohort"], c["id"], row["query_id"])
                value = stable_row(row)
                if key in canonical and canonical[key] != value:
                    issues.append(w["key"] + ":payload:" + c["id"] + ":" + row["query_id"])
                canonical.setdefault(key, value)
    if total != plan["performance_candidate"]["formal"]["calls"]:
        issues.append("registered_call_count")
    if report["error"] or not report["evaluator_unchanged"]:
        issues.append("incomplete_or_changed_evaluator")
    return {"passed": not issues, "issues": issues, "workers": len(workers),
            "expected_workers": len(schedule(plan)), "timed_calls": total,
            "expected_calls": plan["performance_candidate"]["formal"]["calls"]}


def save_report(args, report):
    report["evaluator_unchanged"] = (file_hashes() == report["run"]["evaluator_files"]
        and sha(PLAN.read_bytes()) == report["run"]["plan_sha256"])
    report["validation"] = validation(report)
    if report["validation"]["passed"]:
        report["comparisons"] = previous.comparisons(report)
        report["acceptance"] = previous.acceptance(report, report["comparisons"])
    else:
        report["comparisons"] = []
        report["acceptance"] = {"accepted": False, "numeric_gate_passed": False,
            "reason": "incomplete_or_invalid", "resource_review": []}
    raw = atomic(args.output, report, compressed=True)
    compact = previous.summary(report, args.output.read_bytes(), raw)
    atomic(args.output.with_name(args.output.name.removesuffix(".json.gz") + ".summary.json"), compact)
    atomic(args.state_dir / "checkpoint.json", {"run_identity_sha256": digest(report["run"]),
        "status": report["status"], "completed_workers": [w["key"] for w in report["workers"]],
        "report_sha256": sha(args.output.read_bytes()), "at": now()})


def controller(args, plan, binding):
    require(getattr(args, "publish_branch", None),
            "Formal timing requires a hosted binding claim and per-worker remote checkpoints")
    require(args.baseline_src and args.candidate_src and args.locomo_path and args.output and args.state_dir,
            "Both sources, old LoCoMo data, state directory and output are required")
    require(args.output.name.endswith(".json.gz"), "Use a new .json.gz output path")
    state = args.state_dir.resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    with _lock(state.with_name(state.name + ".controller")):
        require(not state.exists() and not args.output.exists(), "Preserve existing execution; no timing rerun")
        host = host_identity()
        require(host["packages"] == PACKAGES, "Install the exact bound dependencies")
        paths = {label: str(path.resolve()) for label, path in
                 (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
        for label, path in paths.items():
            require(source_identity(Path(path)) == binding["sources"][label], "Frozen source differs")
        cohorts = {}
        for name in plan["performance_candidate"]["formal"]["cohorts"]:
            data = dataset(plan, name, args.locomo_path)
            ids = [c.id for c in data.queries]
            require(len(ids) == len(set(ids)), "Duplicate input query IDs")
            cohorts[name] = {"sha256": data.fingerprint, "queries": len(ids),
                "query_ids": sorted(ids), "query_ids_original_order": ids}
        run = {"evaluator": VERSION, "plan_sha256": sha(PLAN.read_bytes()), "binding": binding,
            "binding_sha256": sha(args.binding.read_bytes()), "evaluator_files": file_hashes(),
            "source_paths": paths, "host": host, "cohorts": cohorts, "schedule": schedule(plan),
            "locomo_file_sha256": sha(args.locomo_path.read_bytes()), "output": str(args.output.resolve()),
            "publication": publication_identity(args)}
        claim_execution(args, run)
        exclusive(state / "run.json", run)
        report = {"schema_version": 1, "evaluator": VERSION, "plan": plan, "run": run,
            "started_at": now(), "workers": [], "error": None, "evaluator_unchanged": False,
            "status": "running", "interpretation": {
                "quality": "Old-data regression, complete output equality; no new-domain or generated-answer claim.",
                "native": "Complete uncached API call, only latency_ms excluded from equality.",
                "mcp": "Actual SDK stdio call/envelope, empty result cache, normal cache-write cost included.",
                "timing": "Four ABBA rounds on one machine; all samples retained, no cold-OS or significance claim.",
                "resources": "Startup, ingest/replay, native and actual MCP process memory measured separately."}}
        try:
            save_report(args, report)
            publish_checkpoint(args, run, "execution claimed")
            for item in run["schedule"]:
                exclusive(state / "workers" / (item["key"] + ".started.json"),
                          {"worker": item, "run_identity_sha256": digest(run)})
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " started")
                command = [sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                    "--binding", str(args.binding.resolve()), "--state-dir", str(state),
                    "--locomo-path", str(args.locomo_path.resolve())]
                subprocess.run(command, check=True, env={**os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
                report["workers"].append(load_completed(state, item, run, plan))
                save_report(args, report)
                publish_checkpoint(args, run, item["key"] + " completed")
                print(json.dumps({"worker_completed": item["key"], "completed_workers": len(report["workers"]),
                                  "report": str(args.output)}), flush=True)
            report["status"] = "measurements_completed"
        except BaseException as error:
            report["status"] = "failed_or_interrupted"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            report["finished_at"] = now()
            save_report(args, report)
            if not (args.output.resolve().parent / "publication-failure.json").exists():
                try:
                    publish_checkpoint(args, run, "controller finished")
                except CheckpointPublicationError as error:
                    report["status"] = "failed_or_interrupted"
                    report["error"] = {"type": type(error).__name__, "message": str(error)}
                    save_report(args, report)
            export_checkpoint(args)
        print(json.dumps({"output": str(args.output), "validation": report["validation"],
                          "acceptance": report["acceptance"]}), flush=True)
        return 2 if not report["validation"]["passed"] else (0 if report["acceptance"]["accepted"] else 3)


def audit(path, state):
    raw = gzip.decompress(path.read_bytes())
    report = json.loads(raw)
    run, plan = report["run"], report["plan"]
    require(report["evaluator"] == VERSION and run["evaluator"] == VERSION, "Wrong evaluator")
    require(json.loads((state / "run.json").read_bytes()) == run, "Saved run identity differs")
    require(plan == load_plan() and run["plan_sha256"] == sha(PLAN.read_bytes())
            and run["evaluator_files"] == file_hashes(), "Audit evaluator or plan differs")
    require(run["binding"]["evaluator_files"] == run["evaluator_files"]
            and run["binding"]["sources"]["baseline"] == BASELINE, "Audit binding differs")
    for item, stored in zip(run["schedule"], report["workers"], strict=True):
        worker = load_completed(state, item, run, plan)
        require(worker == stored, "Worker bytes differ from aggregate")
    checked = validation(report)
    require(checked == report["validation"] and checked["passed"], "Invalid or incomplete saved measurements")
    compared = previous.comparisons(report)
    accepted = previous.acceptance(report, compared)
    require(compared == report["comparisons"] and accepted == report["acceptance"],
            "Stored arithmetic or acceptance changed")
    compact_path = path.with_name(path.name.removesuffix(".json.gz") + ".summary.json")
    require(json.loads(compact_path.read_bytes()) == previous.summary(report, path.read_bytes(), raw),
            "Stored summary differs")
    return {"audit_passed": True, "timed_calls": checked["timed_calls"],
            "accepted": accepted["accepted"], "report_sha256": sha(path.read_bytes()),
            "retrieval_calls_during_audit": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--publish-branch", help="First-attempt hosted validation branch; push each immutable checkpoint")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.audit:
        require(args.state_dir is not None, "Audit needs original worker/ledger state")
        print(json.dumps(audit(args.audit, args.state_dir)))
        return 0
    if args.bind:
        bind(args)
        return 0
    require(args.binding is not None, "A committed binding is required")
    plan, binding = load_plan(), load_binding(args.binding)
    return worker(args, plan, binding) if args.worker else controller(args, plan, binding)


if __name__ == "__main__":
    raise SystemExit(main())
