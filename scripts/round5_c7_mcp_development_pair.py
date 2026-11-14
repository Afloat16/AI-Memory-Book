"""One source-bound C7 actual-MCP development comparison; no formal acceptance.

The frozen round-four mcp_configuration owns the client, timer, cache clearing,
normal cache-write checks, complete response validation and per-call Ledger.
This controller only fixes the 4-worker schedule and saves every observation.
No product calls occur on import, while unregistered, or during saved-data audit.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round4_performance as frozen
from scripts import round5_c7_performance as c7
from benchmarks.semantic_eval import source_snapshot

VERSION = "round5-c7-actual-mcp-development-1"
PLAN_PATH = "benchmarks/experiments/round5-c7-mcp-development-plan.json"
PLAN_SHA256 = "d9dc8110810aa425839d73e4d877423b48aaf6ea0c1aec523a867685d641868f"
SCRIPT_PATH = "scripts/round5_c7_mcp_development_pair.py"
COHORT = "public1015"
CONFIG_INDEX = 5
CONFIG = {"id": "mcp-token1024", "surface": "official-sdk-mcp-stdio",
          "budget_chars": 8000, "budget_tokens": 1024, "tokenizer": "cl100k_base"}
ORDER = (("baseline", "candidate"), ("candidate", "baseline"))
SCHEDULE = tuple({"key": f"r{repetition}-{COHORT}-{label}", "round": repetition,
                  "cohort": COHORT, "label": label}
                 for repetition, labels in enumerate(ORDER) for label in labels)


def registered_inputs():
    """Fail closed before any source import, claim, sample read or product call."""
    c7.require_registered_source()
    registration = c7.continuation_registration()
    raw = (ROOT / PLAN_PATH).read_bytes()
    frozen.require(frozen.sha(raw) == PLAN_SHA256
        and raw == frozen.git("show", c7.CONTINUATION_COMMIT + ":" + PLAN_PATH),
        "MCP development plan must match its exact preregistration commit and SHA")
    plan = json.loads(raw)
    development = registration["document"]["development_protocol"]
    frozen.require(development["mcp_plan"] == PLAN_PATH and development["mcp_plan_sha256"] == PLAN_SHA256
        and development["mcp_calls"] == 4060
        and development["mcp_version_pairs"] == 2030, "MCP diagnostic is not registered in the C7 addendum")
    formal = c7.load_plan()
    frozen.require(plan["config"] == CONFIG == formal["performance_candidate"]["formal"]["configs"][CONFIG_INDEX]
        and plan["rounds"] == 2 and plan["engine_order"] == [list(labels) for labels in ORDER]
        and plan["workers"] == plan["fresh_sdk_servers"] == 4
        and plan["calls"] == 4060 and plan["version_pairs"] == 2030
        and plan["cohort"] == {"name": COHORT, "queries": 1015,
            "sha256": "8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857",
            "selection": "Every fixed old public query, unchanged."}, "MCP diagnostic matrix changed")
    measurement = plan["measurement"]
    frozen.require(measurement["module"] == "scripts/round4_performance.py"
        and measurement["entrypoint"] == "mcp_configuration"
        and measurement["row_validation"] == "make_row" and measurement["attempt_ledger"] == "Ledger"
        and measurement["packages"] == frozen.PACKAGES
        and frozen.sha((ROOT / measurement["module"]).read_bytes()) == measurement["module_sha256"],
        "Frozen MCP measurement primitive or dependency pins changed")
    reference = plan["query_order"]
    reference_raw = (ROOT / reference["reference_run"]).read_bytes()
    frozen.require(frozen.sha(reference_raw) == reference["reference_run_sha256"]
        and reference_raw == frozen.git("show", reference["reference_result_commit"] + ":" + reference["reference_run"])
        and reference["reference_formal_rounds"] == [0, 1] and reference["formal_config_index"] == CONFIG_INDEX,
        "Original complete formal query-order reference changed")
    ids = json.loads(reference_raw)["cohorts"][COHORT]["query_ids_original_order"]
    frozen.require(len(ids) == len(set(ids)) == 1015, "Original question axis is incomplete")
    return plan, formal, registration, ids


def projection(book):
    return {"source_snapshot_sha256": source_snapshot(book.db),
        "indexed_content": frozen.indexed_content(book.db), "revision": book.revision,
        "cache_entries": book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}


def validate_saved_worker(value, run, ledger_raw):
    """Inspect only saved rows and their exact original start/finish ledger."""
    item = next(item for item in run["schedule"] if item["key"] == value["key"])
    expected = run["sources"][item["label"]]
    frozen.require(value["status"] == "completed" and value["error"] is None
        and all(value[name] == item[name] for name in item)
        and value["run_identity_sha256"] == frozen.digest(run)
        and value["source"] == value["source_after"] == expected,
        "Incomplete or differently bound MCP worker")
    frozen.require(value["dataset_sha256"] == run["dataset_sha256"]
        and value["all_replayed_sessions_skipped"]
        and value["archive_before"] == value["archive_after"]
        and value["archive_before"]["cache_entries"] == 0, "Source/index/revision/cache state changed")
    frozen.require(len(value["configurations"]) == 1, "Unexpected MCP configuration axis")
    cell = value["configurations"][0]
    frozen.require({name: cell[name] for name in CONFIG} == CONFIG, "MCP configuration changed")
    rows = cell["rows"]
    order = frozen.query_order(run["query_ids_original_order"], item["round"], CONFIG_INDEX)
    frozen.require([row["query_id"] for row in rows] == order and len(rows) == 1015,
        "Missing, duplicate or reordered MCP samples")
    frozen.require(cell["latency"] == frozen.latency_summary([row["wall_ms"] for row in rows]),
        "Saved MCP arithmetic differs")
    for row in rows:
        frozen.require(frozen.finite(row["wall_ms"]) and row["wall_ms"] > 0
            and row["engine_source_sha256"] == expected["runtime_sha256"], "Invalid timing/source row")
        frozen.require(set(row["invariants"]) == set(frozen.INVARIANTS)
            and not any(row["invariants"].values())
            and row["cache_rows_before"] == 0 and row["cache_rows_after"] == 1,
            "MCP complete-output/source/budget/cache invariant failed")
        frozen.require(row["context_chars"] <= CONFIG["budget_chars"] and row["result_count"] <= 5
            and set(row["tokens"]) == set(frozen.ENCODINGS), "MCP output/count axis changed")
        for costs in row["tokens"].values():
            frozen.require(set(costs) == {"context", "response_text", "response_envelope_json"}
                and all(type(costs[name]) is int and costs[name] >= 0 for name in costs),
                "Invalid reference tokenizer counts")
        count = row["tokens"]["cl100k_base"]["context"]
        metadata = {"budget_tokens": 1024, "tokenizer": "cl100k_base",
            "tokenizer_version": frozen.PACKAGES["tiktoken"], "context_tokens": count}
        frozen.require(count <= 1024 and row["token_metadata"] == {"native": metadata, "response": metadata},
            "Full native/MCP token metadata differs")
        for field in ("payload_sha256", "native_payload_sha256", "context_sha256", "envelope_sha256"):
            frozen.require(isinstance(row[field], str) and re.fullmatch(r"[0-9a-f]{64}", row[field]) is not None,
                "Missing full MCP/native/envelope digest")
    frozen.require(set(value["mcp_sessions"]) == {CONFIG["id"]}, "Unexpected actual SDK session axis")
    session = value["mcp_sessions"][CONFIG["id"]]
    frozen.require(set(session) == set(frozen.MCP_SESSION_FIELDS)
        and frozen.finite(session["mcp_startup_to_initialize_ms"])
        and session["mcp_server_memory_after_calls"]["available"] is True,
        "Mandatory frozen MCP session/resource observation is missing")
    for metric in ("rss_bytes", "hwm_bytes"):
        frozen.require(frozen.finite(session["mcp_server_memory_after_calls"][metric]), "Invalid live MCP resource observation")
    frozen.require(frozen.sha(ledger_raw) == value["ledger_sha256"], "Original MCP ledger bytes changed")
    events = [json.loads(line) for line in ledger_raw.splitlines()]
    frozen.require(len(events) == 2 * len(rows), "Interrupted or extra MCP ledger events")
    for seq, row in enumerate(rows):
        begin, end = events[2 * seq:2 * seq + 2]
        frozen.require(begin["event"] == "started" and end["event"] == "finished"
            and begin["seq"] == end["seq"] == seq
            and begin["config"] == end["config"] == CONFIG["id"]
            and begin["query_id"] == row["query_id"] and end["row"] == row,
            "Saved call/response differs from its original MCP ledger")
    return len(rows)


def worker(args):
    plan, formal, registration, ids = registered_inputs()
    state = args.state_dir.resolve()
    run = json.loads((state / "run.json").read_bytes())
    frozen.require(run["evaluator"] == VERSION and run["plan_sha256"] == PLAN_SHA256
        and run["registration"] == registration
        and run["sources"] == {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}
        and run["host"] == frozen.host_identity() and run["query_ids_original_order"] == ids
        and run["state_dir"] == str(state),
        "MCP worker source/registration/host/order differs")
    claim = json.loads(Path(run["execution_claim"]).read_bytes())
    frozen.require(claim["run_identity_sha256"] == frozen.digest(run), "MCP worker has no exact execution claim")
    item = next(item for item in run["schedule"] if item["key"] == args.worker)
    marker = state / "workers" / (item["key"] + ".started.json")
    frozen.require(json.loads(marker.read_bytes()) == {"worker": item, "run_identity_sha256": frozen.digest(run)},
        "MCP worker has no exact controller intent")
    output = state / "workers" / (item["key"] + ".json.gz")
    ledger_path = state / "workers" / (item["key"] + ".attempts.jsonl")
    frozen.require(not output.exists() and not ledger_path.exists(), "Preserve the existing MCP attempt; never repeat it")
    source = Path(run["source_paths"][item["label"]])
    expected = run["sources"][item["label"]]
    frozen.require(c7.source_identity(source) == expected, "MCP worker runtime identity changed")
    frozen.require(frozen.sha(Path(__file__).read_bytes()) == run["helper_sha256"]
        and c7.file_hashes() == run["evaluator_files"], "MCP helper/evaluator inputs changed")
    sys.path.insert(0, str(source))
    import memory_book
    from memory_book import MemoryBook
    frozen.require(Path(memory_book.__file__).parent.resolve() == (source / "memory_book").resolve(),
        "MCP worker imported another runtime")
    data = frozen.dataset(formal, COHORT, args.locomo_path)
    frozen.require([case.id for case in data.queries] == ids, "MCP worker original question order changed")
    work = state / item["key"]
    work.mkdir(exist_ok=False)
    report = {**item, "evaluator": VERSION, "status": "started", "error": None,
        "started_at": frozen.now(), "source": expected, "run_identity_sha256": frozen.digest(run),
        "dataset_sha256": data.fingerprint, "configurations": []}
    frozen.atomic(output, report, compressed=True)
    ledger = frozen.Ledger(ledger_path)
    try:
        database = work / "memory.db"
        with MemoryBook(database, cache_size=0) as book:
            report["fresh_ingestion_results_sha256"] = frozen.digest([book.ingest(session) for session in data.sessions])
            replayed = [book.ingest(session) for session in data.sessions]
            report["unchanged_reingestion_results_sha256"] = frozen.digest(replayed)
            report["all_replayed_sessions_skipped"] = all(row["skipped"] for row in replayed)
            report["archive_before"] = projection(book)
            pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
            sources = frozen.original_turn_texts(data)
            counters = {name: frozen.TokenCounter(name) for name in frozen.ENCODINGS}
            for counter in counters.values():
                counter.count("Initialize reference tokenizer before query timing.")
            order = frozen.query_order(ids, item["round"], CONFIG_INDEX)
            rows = asyncio.run(frozen.mcp_configuration(data, CONFIG, order, database, work, source,
                counters, sources, pages, report, ledger))
            report["configurations"].append({**CONFIG, "rows": rows,
                "latency": frozen.latency_summary([row["wall_ms"] for row in rows])})
            report["archive_after"] = projection(book)
            frozen.require(report["archive_after"] == report["archive_before"], "MCP changed source/index/revision/cache state")
        report["source_after"] = c7.source_identity(source)
        frozen.require(report["source_after"] == expected
            and frozen.sha(Path(__file__).read_bytes()) == run["helper_sha256"]
            and c7.file_hashes() == run["evaluator_files"], "Source/helper changed during MCP measurement")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        ledger.close()
        raw = ledger_path.read_bytes()
        frozen.exclusive_bytes(ledger_path.with_suffix(".jsonl.gz"), gzip.compress(raw, mtime=0))
        report["ledger_sha256"] = frozen.sha(raw)
        report["finished_at"] = frozen.now()
        frozen.atomic(output, report, compressed=True)
    try:
        validate_saved_worker(report, run, raw)
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        frozen.atomic(output, report, compressed=True)
        raise
    return 0


def inspect_saved(report, state):
    """No product import or call: inspect all successful saved data, including losses."""
    run = report["run"]
    frozen.require(json.loads((state / "run.json").read_bytes()) == run,
        "Original MCP run file differs from its aggregate manifest")
    frozen.require(run["evaluator"] == VERSION and run["plan_sha256"] == PLAN_SHA256
        and run["sources"] == {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}
        and run["schedule"] == list(SCHEDULE)
        and [worker["key"] for worker in report["workers"]] == [item["key"] for item in SCHEDULE],
        "Incomplete, duplicated or reordered MCP development workers")
    pairs, canonical, projections, sessions, count = {}, {}, {}, {}, 0
    timing = {}
    for value in report["workers"]:
        item = next(item for item in SCHEDULE if item["key"] == value["key"])
        marker = state / "workers" / (value["key"] + ".started.json")
        frozen.require(json.loads(marker.read_bytes()) == {"worker": item,
            "run_identity_sha256": frozen.digest(run)}, "Original MCP worker intent differs")
        saved = json.loads(gzip.decompress((state / "workers" / (value["key"] + ".json.gz")).read_bytes()))
        frozen.require(saved == value, "Original worker file differs from the aggregate MCP manifest")
        path = state / "workers" / (value["key"] + ".attempts.jsonl.gz")
        count += validate_saved_worker(value, run, gzip.decompress(path.read_bytes()))
        session = value["mcp_sessions"][CONFIG["id"]]
        for field in ("mcp_tool_schema_sha256", "mcp_instructions_sha256", "mcp_initialization_tokens"):
            frozen.require(field not in sessions or sessions[field] == session[field], "SDK initialization identity changed")
            sessions.setdefault(field, session[field])
        for field in ("archive_before", "fresh_ingestion_results_sha256", "unchanged_reingestion_results_sha256"):
            frozen.require(field not in projections or projections[field] == value[field], "Cross-source archive/ingestion differs")
            projections.setdefault(field, value[field])
        rows = value["configurations"][0]["rows"]
        timing[(value["round"], value["label"])] = [row["wall_ms"] for row in rows]
        for row in rows:
            stable = frozen.stable_row(row)
            key = (value["round"], row["query_id"])
            pair = pairs.setdefault(key, {})
            frozen.require(value["label"] not in pair, "Duplicate MCP version-pair member")
            pair[value["label"]] = stable
            identity = row["query_id"]
            frozen.require(identity not in canonical or canonical[identity] == stable,
                "Complete MCP/native/envelope output differs between source or round: " + identity)
            canonical.setdefault(identity, stable)
    frozen.require(count == 4060 and len(pairs) == 2030 and len(canonical) == 1015
        and all(set(pair) == {"baseline", "candidate"} and pair["baseline"] == pair["candidate"] for pair in pairs.values()),
        "Incomplete or unequal 4060-call / 2030-pair actual MCP comparison")
    def compare(values, repetition):
        row = {"round": repetition, **{label: frozen.latency_summary(values[label]) for label in values}}
        row["change_percent"] = {metric: 100 * (row["candidate"][metric] / row["baseline"][metric] - 1)
            for metric in ("mean_ms", "p50_ms", "p95_ms")}
        return row
    per_round = [compare({label: timing[(repetition, label)] for label in ("baseline", "candidate")}, repetition)
        for repetition in range(2)]
    pooled = compare({label: [elapsed for repetition in range(2) for elapsed in timing[(repetition, label)]]
        for label in ("baseline", "candidate")}, None)
    return {"timed_calls": count, "complete_output_pairs": len(pairs), "cross_round_stable_queries": len(canonical),
        "ledger_events": 2 * count, "all_invariants_passed": True, "all_complete_outputs_equal": True,
        "pooled": pooled, "per_round": per_round,
        "adverse_metrics": [{"round": row["round"], "metric": metric, "change_percent": change}
            for row in [pooled, *per_round] for metric, change in row["change_percent"].items() if change > 0],
        "first_queries_retained": [{"worker": value["key"], "row": value["configurations"][0]["rows"][0]}
            for value in report["workers"]], "formal_acceptance_evaluated": False}


def main(argv=None):
    plan, formal, registration, ids = registered_inputs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--locomo-path", type=Path)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args(argv)
    if args.worker:
        return worker(args)
    if args.audit:
        report = json.loads(gzip.decompress(args.audit.read_bytes()))
        run = report["run"]
        frozen.require(run["plan"] == plan and run["registration"] == registration
            and run["query_ids_original_order"] == ids
            and run["helper_sha256"] == frozen.sha(Path(__file__).read_bytes())
            and run["evaluator_files"] == c7.file_hashes(), "Saved MCP audit provenance differs")
        verified = inspect_saved(report, args.state_dir.resolve())
        frozen.require(report["status"] == "completed" and report["verification"] == verified,
            "Saved MCP summary differs from its complete original rows")
        print(json.dumps(verified))
        return 0
    frozen.require(args.baseline_src and args.candidate_src and args.locomo_path and args.output,
        "Both frozen source checkouts, original data and a new output path are required")
    frozen.require(args.output.name.endswith(".json.gz"), "Use a new compressed MCP manifest path")
    frozen.require(not args.state_dir.exists() and not args.output.exists(), "Preserve prior MCP diagnostic state; no rerun")
    sources = {"baseline": c7.BASELINE, "candidate": c7.C7_SOURCE}
    paths = {label: str(path.resolve()) for label, path in (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    for label, path in paths.items():
        frozen.require(c7.source_identity(Path(path)) == sources[label], "MCP diagnostic source is not the frozen identity")
    host = frozen.host_identity()
    frozen.require(host["packages"] == frozen.PACKAGES, "Use the exact original MCP dependency pins")
    frozen.require(Path("/proc/self/status").is_file() and Path("/proc/self/task").is_dir(),
        "Frozen MCP resource observations require a compatible procfs host")
    data = frozen.dataset(formal, COHORT, args.locomo_path)
    frozen.require([case.id for case in data.queries] == ids, "MCP diagnostic input order differs from formal")
    helper_sha = frozen.sha(Path(__file__).read_bytes())
    evaluator_commit = frozen.git("rev-parse", "HEAD").decode().strip()
    hashes = {**c7.file_hashes(), SCRIPT_PATH: helper_sha, PLAN_PATH: PLAN_SHA256}
    for name, expected in hashes.items():
        frozen.require(frozen.sha(frozen.git("show", evaluator_commit + ":" + name)) == expected,
            "Commit all exact MCP diagnostic inputs before timing: " + name)
    fingerprint = frozen.digest({"plan_sha256": PLAN_SHA256, "sources": sources})
    claim_path = ROOT / ".artifacts" / ("round5-c7-mcp-development-" + fingerprint + ".execution.json")
    run = {"evaluator": VERSION, "plan": plan, "plan_sha256": PLAN_SHA256, "registration": registration,
        "sources": sources, "source_paths": paths, "host": host, "evaluator_commit": evaluator_commit,
        "evaluator_files": c7.file_hashes(), "helper_sha256": helper_sha, "schedule": list(SCHEDULE),
        "dataset_sha256": data.fingerprint, "query_ids_original_order": ids,
        "locomo_file_sha256": frozen.sha(args.locomo_path.read_bytes()),
        "execution_claim": str(claim_path), "state_dir": str(args.state_dir.resolve())}
    frozen.exclusive(claim_path, {"evaluator": VERSION, "created_at": frozen.now(),
        "run_identity_sha256": frozen.digest(run), "sources": sources, "plan_sha256": PLAN_SHA256})
    state = args.state_dir.resolve()
    state.mkdir(parents=True, exist_ok=False)
    frozen.exclusive(state / "run.json", run)
    report = {"evaluator": VERSION, "status": "running", "error": None, "created_at": frozen.now(),
        "run": run, "workers": [], "verification": None,
        "scope": "One complete old-data actual MCP development invocation, not formal acceptance. All samples, errors and adverse values retained."}
    frozen.atomic(args.output, report, compressed=True)
    try:
        for item in SCHEDULE:
            frozen.exclusive(state / "workers" / (item["key"] + ".started.json"),
                {"worker": item, "run_identity_sha256": frozen.digest(run)})
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", item["key"],
                "--state-dir", str(state), "--locomo-path", str(args.locomo_path.resolve())], check=True)
            value = json.loads(gzip.decompress((state / "workers" / (item["key"] + ".json.gz")).read_bytes()))
            raw = gzip.decompress((state / "workers" / (item["key"] + ".attempts.jsonl.gz")).read_bytes())
            calls = validate_saved_worker(value, run, raw)
            report["workers"].append(value)
            frozen.atomic(args.output, report, compressed=True)
            print(json.dumps({"worker_completed": item["key"], "calls": calls,
                "completed_workers": len(report["workers"])}), flush=True)
        report["verification"] = inspect_saved(report, state)
        frozen.require(helper_sha == frozen.sha(Path(__file__).read_bytes())
            and c7.file_hashes() == run["evaluator_files"], "MCP diagnostic inputs changed during execution")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["finished_at"] = frozen.now()
        frozen.atomic(args.output, report, compressed=True)
    print(json.dumps({"status": report["status"], "verification": report["verification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
