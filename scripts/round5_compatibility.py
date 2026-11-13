"""Exact-output historical Hotpot256 regression and character-path diagnostic.

This reads the already scored round-four manifest without selecting new IDs or
running external components. Each worker has an exclusive state/output path.
Timing is recorded only for the separately registered character ABBA diagnostic;
token configurations are correctness checks. Raw queries/source text stay local.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.run import engine_source_hash, original_turn_texts
from benchmarks.native_budget_eval import source_errors
from benchmarks.semantic_eval import page_projection_errors, source_snapshot
from benchmarks.token_compare import TokenCounter, checkout_provenance, latency_summary
from scripts.benchmark_default_recall import indexed_content, rss
from benchmarks.round2_resources import storage
from scripts.round5_performance import host_identity

PLAN = "benchmarks/experiments/round5-plan.json"
PLAN_COMMIT = "7068594181c7e98c576f68a81daf85cd0d06c729"
ADDENDUM = "benchmarks/experiments/round5-materialization-addendum.json"
ADDENDUM_COMMIT = "9042570d8cff01be7c95cd01f8698e166fc7d313"
C_SCOPE = "benchmarks/experiments/round5-canonical-row-addendum.json"
C_SCOPE_COMMIT = "c724452e8f7333af73ed8a0424f572b7d7280a07"
BASELINE = "692fb959ddf8934c5f516ba3d74ceb4385a2fa82"
BASELINE_HASH = "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"
DATA_HASH = "fb3cd70ea58fafa5bd9cef0f04dba7399aaafba76f5f92605eee9e516f115e1b"
MANIFEST = "benchmarks/experiments/round4-hotpot256-manifest.json"
OLD_BINDING = "benchmarks/experiments/round4-validation-binding.json"
ENCODINGS = ("cl100k_base", "o200k_base")
ORDER = (("baseline", "candidate"), ("candidate", "baseline"),
         ("candidate", "baseline"), ("baseline", "candidate"))
ERRORS = ("source", "projection", "scope", "chars", "tokens", "metadata", "cache", "policy", "limit")
VERSION = "round5-historical256-compatibility-1"
EXTRA = ("scripts/round5_compatibility.py", "tests/test_round5_compatibility.py",
         "scripts/round5_performance.py", PLAN, ADDENDUM, C_SCOPE, MANIFEST, OLD_BINDING)


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    # Same full-payload canonical convention as the historical comparison.
    return sha(raw(value).rstrip(b"\n"))


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30,
                                   stderr=subprocess.DEVNULL)


def read(path):
    value = Path(path).read_bytes()
    return json.loads(gzip.decompress(value) if str(path).endswith(".gz") else value)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = raw(value)
    if path.suffix == ".gz":
        value = gzip.compress(value, mtime=0)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def source(path):
    package = Path(path).resolve() / "memory_book"
    provenance = checkout_provenance(package)
    require(provenance["commit_identifies_source"], "Runtime must equal its exact commit")
    return {"commit": provenance["git_commit"], "runtime_sha256": engine_source_hash(package)}


def registry():
    old = read(ROOT / OLD_BINDING)["evaluator_files"]
    names = set(old) | set(EXTRA)
    return {name: sha((ROOT / name).read_bytes()) for name in sorted(names)}


def registered():
    value = (ROOT / PLAN).read_bytes()
    require(value == git("show", PLAN_COMMIT + ":" + PLAN), "Original round-five plan changed")
    addendum = (ROOT / ADDENDUM).read_bytes()
    require(addendum == git("show", ADDENDUM_COMMIT + ":" + ADDENDUM),
            "Registered materialization addendum changed")
    require(json.loads(addendum)["original_plan_commit"] == PLAN_COMMIT,
            "Materialization addendum names another plan")
    scope = (ROOT / C_SCOPE).read_bytes()
    require(scope == git("show", C_SCOPE_COMMIT + ":" + C_SCOPE),
            "Registered canonical-row scope changed")
    registered_scope = json.loads(scope)
    require(registered_scope["original_plan_commit"] == PLAN_COMMIT and
            registered_scope["materialization_addendum_commit"] == ADDENDUM_COMMIT,
            "Canonical-row scope names another registration")
    plan = json.loads(value)
    require(plan["baseline"]["commit"] == BASELINE and
            plan["baseline"]["runtime_sha256"] == BASELINE_HASH, "Wrong baseline")
    diagnostic = plan["compatibility"]["historical_char100000_diagnostic"]
    require(diagnostic["calls"] == 2048 and diagnostic["seed"] == 51256 and
            diagnostic["engine_order"] == [list(x) for x in ORDER], "Changed character schedule")
    return plan


def bind(args):
    registered()
    require(not args.output.exists(), "Never overwrite a compatibility binding")
    sources = {name: source(path) for name, path in
               (("baseline", args.baseline_src), ("candidate", args.candidate_src))}
    require(sources["baseline"] == {"commit": BASELINE, "runtime_sha256": BASELINE_HASH}, "Wrong released baseline")
    files, commit = registry(), git("rev-parse", "HEAD").decode().strip()
    for name, expected in files.items():
        require(sha(git("show", commit + ":" + name)) == expected, "Commit evaluator first: " + name)
    manifest = read(ROOT / MANIFEST)
    require(manifest["dataset_sha256"] == DATA_HASH and manifest["expected_queries"] == 256, "Wrong historical cohort")
    save(args.output, {"version": VERSION, "created_at": now(), "plan_commit": PLAN_COMMIT,
        "addendum_commit": ADDENDUM_COMMIT, "addendum_sha256": sha((ROOT / ADDENDUM).read_bytes()),
        "canonical_scope_commit": C_SCOPE_COMMIT,
        "canonical_scope_sha256": sha((ROOT / C_SCOPE).read_bytes()),
        "evaluator_commit": commit, "files": files, "sources": sources,
        "dataset_sha256": DATA_HASH, "ids": manifest["selected_ids"],
        "token_calls": 3072, "character_calls": 2048,
        "interpretation": "Historical exact-output regression; no fresh selection or new external-component claim."})


def binding(path):
    registered()
    value = read(path)
    require(value["version"] == VERSION and value["plan_commit"] == PLAN_COMMIT and
            value["files"] == registry(), "Compatibility evaluator changed")
    require(value["addendum_commit"] == ADDENDUM_COMMIT and
            value["addendum_sha256"] == sha((ROOT / ADDENDUM).read_bytes()),
            "Compatibility addendum binding changed")
    require(value["canonical_scope_commit"] == C_SCOPE_COMMIT and
            value["canonical_scope_sha256"] == sha((ROOT / C_SCOPE).read_bytes()),
            "Compatibility canonical-row scope binding changed")
    relative = Path(path).resolve().relative_to(ROOT).as_posix()
    require(Path(path).read_bytes() == git("show", "HEAD:" + relative), "Commit binding before execution")
    for name, expected in value["files"].items():
        require(sha(git("show", value["evaluator_commit"] + ":" + name)) == expected,
                "Frozen evaluator commit mismatch: " + name)
    require(value["sources"]["baseline"] == {"commit": BASELINE, "runtime_sha256": BASELINE_HASH}, "Baseline changed")
    require(value["dataset_sha256"] == DATA_HASH and len(set(value["ids"])) == len(value["ids"]) == 256,
            "Wrong historical IDs")
    return value


def data_for(args, bound):
    from scripts.round4_data import load
    data = load(args.parquet, ROOT / OLD_BINDING, ROOT / MANIFEST)
    require(data.fingerprint == DATA_HASH and [q.id for q in data.queries] == bound["ids"], "Historical data changed")
    return data


def imported(path, expected):
    require(source(path) == expected, "Wrong source checkout")
    sys.path.insert(0, str(Path(path).resolve()))
    import memory_book
    require(Path(memory_book.__file__).resolve().parent == Path(path).resolve() / "memory_book",
            "Another runtime was imported")
    return memory_book.MemoryBook


def prepare(args):
    bound = binding(args.binding)
    require(not args.output.exists() and not args.state.exists(), "Preserve prior preparation")
    data = data_for(args, bound)
    Book = imported(args.source, bound["sources"]["baseline"])
    args.state.mkdir(parents=True)
    database = args.state / "prepared.db"
    with Book(database, max_page_chars=900, cache_size=0) as book:
        for session in data.sessions:
            book.ingest(session)
        originals, index = source_snapshot(book.db), indexed_content(book.db)
        count = book.db.execute("SELECT count(*) FROM pages").fetchone()[0]
        require(count == 3953, "Historical canonical page count changed")
    save(args.output, {"status": "prepared", "version": VERSION,
        "binding_sha256": sha(args.binding.read_bytes()), "dataset_sha256": DATA_HASH,
        "source": bound["sources"]["baseline"], "originals_sha256": originals,
        "indexed_content": index, "pages": count, "database_sha256": sha(database.read_bytes()),
        "database_bytes": database.stat().st_size, "created_at": now()})
    print(json.dumps({"prepared": True, "pages": count}), flush=True)


def configurations(kind):
    if kind == "char":
        return [{"budget_chars": 100000}]
    require(kind == "tokens", "Unknown regression mode")
    return [{"budget_chars": 8000, "budget_tokens": cap, "tokenizer": name}
            for name in ENCODINGS for cap in (512, 1024, 2048)]


def schedule():
    return ([{"kind": "tokens", "round": 0, "label": label} for label in ("baseline", "candidate")]
            + [{"kind": "char", "round": repetition, "label": label}
               for repetition, labels in enumerate(ORDER) for label in labels])


def filename(item):
    return f'{item["kind"]}-r{item["round"]}-{item["label"]}.json.gz'


def intent(args):
    bound = binding(args.binding)
    require(not args.output.exists(), "Preserve the execution intent")
    preparation = read(args.preparation)
    require(preparation["binding_sha256"] == sha(args.binding.read_bytes()), "Wrong preparation")
    save(args.output, {"version": VERSION, "status": "registered-before-retrieval", "created_at": now(),
        "binding_sha256": sha(args.binding.read_bytes()), "preparation_sha256": sha(args.preparation.read_bytes()),
        "sources": bound["sources"], "host": host_identity(), "schedule": schedule(),
        "calls": 5120, "policy": "Exact complete-prefix continuation only; never replay partial or completed workers."})


def execution_intent(path, bound, binding_path):
    record = read(path)
    relative = Path(path).resolve().relative_to(ROOT).as_posix()
    require(Path(path).read_bytes() == git("show", "HEAD:" + relative), "Commit execution intent before retrieval")
    require(record["version"] == VERSION and record["schedule"] == schedule()
            and record["calls"] == 5120 and record["sources"] == bound["sources"]
            and record["binding_sha256"] == sha(Path(binding_path).read_bytes()), "Execution intent differs")
    return record


def worker(args):
    bound = binding(args.binding)
    execution = execution_intent(args.intent, bound, args.binding)
    require(execution["host"] == host_identity(), "Worker must remain on the registered host/boot")
    item = {"kind": args.kind, "round": args.round, "label": args.label}
    require(item in schedule() and args.output.name == filename(item), "Worker is outside the registered schedule")
    require(args.output.parent.resolve() == args.intent.parent.resolve(), "Worker output must accompany its intent")
    position = schedule().index(item)
    for index, prior in enumerate(schedule()):
        prior_path = args.output.parent / filename(prior)
        if index < position:
            completed = read(prior_path)
            require(completed["status"] == "completed" and completed["host"] == execution["host"]
                    and completed["intent_sha256"] == sha(args.intent.read_bytes())
                    and completed["finished_monotonic_ns"] < time.monotonic_ns(), "Previous worker is not a complete prefix")
        else:
            require(not prior_path.exists() and not prior_path.with_name(prior_path.name + ".attempts.jsonl").exists(),
                    "Preserve a prior partial, duplicate or out-of-order worker")
    require(not args.state.exists() and not args.output.exists(), "Never replay/overwrite a worker")
    require(args.label in ("baseline", "candidate") and 0 <= args.round < 4, "Wrong worker identity")
    require(args.kind == "char" or args.round == 0, "Token regression has one pass")
    prep = read(args.preparation)
    require(execution["preparation_sha256"] == sha(args.preparation.read_bytes()), "Preparation changed after intent")
    require(prep["binding_sha256"] == sha(args.binding.read_bytes()) and
            prep["source"] == bound["sources"]["baseline"] and prep["dataset_sha256"] == DATA_HASH,
            "Preparation belongs to another binding")
    require(sha(args.database.read_bytes()) == prep["database_sha256"], "Prepared database changed")
    data = data_for(args, bound)
    Book = imported(args.source, bound["sources"][args.label])
    args.state.mkdir(parents=True)
    path = args.state / "worker.db"
    shutil.copyfile(args.database, path)
    counters = {name: TokenCounter(name) for name in ENCODINGS}
    for counter in counters.values():
        require(counter.version == "0.12.0", "Wrong reference tokenizer")
        counter.count("readiness")
    configs = configurations(args.kind)
    report = {"version": VERSION, "status": "running", "kind": args.kind,
        "label": args.label, "round": args.round, "source": bound["sources"][args.label],
        "binding_sha256": sha(args.binding.read_bytes()), "dataset_sha256": DATA_HASH,
        "expected_calls": len(data.queries) * len(configs), "started": 0, "finished": 0,
        "host": execution["host"], "intent_sha256": sha(args.intent.read_bytes()),
        "started_monotonic_ns": time.monotonic_ns(),
        "created_at": now(), "rows": [], "source_text_exported": False,
        "timing_scope": "Native recall only for char ABBA; token rows are untimed correctness checks. Evaluator validation runs after each call."}
    ledger_path = args.output.with_name(args.output.name + ".attempts.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not ledger_path.exists(), "Preserve an existing attempt ledger")
    save(args.output, report)
    source_texts = original_turn_texts(data)
    try:
        with ledger_path.open("x", encoding="utf-8") as ledger, Book(path, max_page_chars=900, cache_size=0) as book:
            def event(value):
                ledger.write(raw(value).decode())
                ledger.flush()
                os.fsync(ledger.fileno())
            require(source_snapshot(book.db) == prep["originals_sha256"] and
                    indexed_content(book.db) == prep["indexed_content"], "Copied archive differs")
            pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
            report["rss_after_open"] = rss()
            for number, config in enumerate(configs):
                cases = list(data.queries)
                random.Random(51256 + 1009 * args.round + number).shuffle(cases)
                for case in cases:
                    identity = {"query_id": case.id, "configuration": config}
                    event({"state": "started", **identity})
                    report["started"] += 1
                    begin = time.perf_counter_ns() if args.kind == "char" else None
                    response = book.recall(case.query, project=case.project, limit=5,
                        use_cache=False, coverage=False, semantic=False, **config)
                    elapsed = (time.perf_counter_ns() - begin) / 1e6 if begin is not None else None
                    require("latency_ms" in response, "Missing timing metadata")
                    response.pop("latency_ms")
                    counts = {name: counter.count(response["context"]) for name, counter in counters.items()}
                    tokenized = "budget_tokens" in config
                    errors = {"source": source_errors(response, source_texts),
                        "projection": page_projection_errors(response, pages),
                        "scope": sum(item["breadcrumb"][0]["id"] != case.project for item in response["results"])
                            if case.project is not None else 0,
                        "chars": int(len(response["context"]) > config["budget_chars"]),
                        "tokens": int(tokenized and counts[config["tokenizer"]] > config["budget_tokens"]),
                        "metadata": int(tokenized and (response.get("context_tokens") != counts[config["tokenizer"]]
                            or response.get("budget_tokens") != config["budget_tokens"]
                            or response.get("tokenizer") != config["tokenizer"] or response.get("tokenizer_version") != "0.12.0")),
                        "cache": int(bool(response["cache_hit"])),
                        "policy": int(bool(response.get("semantic")) or bool(response.get("project_local_fts_statistics"))),
                        "limit": int(len(response["results"]) > 5)}
                    row = {**identity, "payload_sha256": digest(response), "context_sha256": sha(response["context"].encode()),
                           "context_chars": len(response["context"]), "result_count": len(response["results"]),
                           "reference_tokens": counts, "errors": errors, "elapsed_ms": elapsed}
                    event({"state": "finished", **row})
                    report["finished"] += 1
                    report["rows"].append(row)
                    require(not any(errors.values()), "Source/scope/budget/cache invariant failure")
                save(args.output, report)
            require(source_snapshot(book.db) == prep["originals_sha256"] and
                    indexed_content(book.db) == prep["indexed_content"], "Read-only recall changed archive")
            require(book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0] == 0, "Cache written")
            report["rss_after_calls"] = rss()
            report["storage_before_close"] = storage(args.state)
        require(source(args.source) == bound["sources"][args.label], "Runtime changed during worker")
        report.update(status="completed", originals_unchanged=True, index_unchanged=True,
                      recall_cache_rows=0, storage_after_close=storage(args.state))
    except BaseException as error:
        report.update(status="failed-incomplete", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report["finished_at"] = now()
        report["finished_monotonic_ns"] = time.monotonic_ns()
        if ledger_path.exists():
            report["ledger_sha256"] = sha(ledger_path.read_bytes())
        save(args.output, report)
    print(json.dumps({"kind": args.kind, "label": args.label, "round": args.round,
                      "finished": report["finished"], "status": report["status"]}), flush=True)


def verify_worker(report, bound, ledger):
    require(report["version"] == VERSION and report["status"] == "completed", "Incomplete worker")
    kind, label, repetition = report["kind"], report["label"], report["round"]
    require(label in ("baseline", "candidate") and 0 <= repetition < 4 and
            (kind == "char" or repetition == 0), "Invalid worker identity")
    require(report["source"] == bound["sources"][label] and report["dataset_sha256"] == DATA_HASH,
            "Worker identity differs")
    require(type(report["started_monotonic_ns"]) is int and type(report["finished_monotonic_ns"]) is int
            and 0 < report["started_monotonic_ns"] < report["finished_monotonic_ns"], "Invalid worker lifetime")
    expected = []
    for number, config in enumerate(configurations(kind)):
        ids = list(bound["ids"])
        random.Random(51256 + 1009 * repetition + number).shuffle(ids)
        expected.extend((identity, config) for identity in ids)
    require(report["started"] == report["finished"] == report["expected_calls"] == len(expected), "Wrong call count")
    require(len(report["rows"]) == len(expected) and len(ledger) == 2 * len(expected), "Incomplete rows/ledger")
    require(report["originals_unchanged"] is True and report["index_unchanged"] is True and
            report["recall_cache_rows"] == 0, "Mutated source/index/cache")
    for index, (row, (identity, config)) in enumerate(zip(report["rows"], expected)):
        require((row["query_id"], row["configuration"]) == (identity, config), "Changed query schedule")
        require(set(row["errors"]) == set(ERRORS) and all(type(v) is int and v == 0 for v in row["errors"].values()),
                "Recorded invariant failure")
        for name in ("payload_sha256", "context_sha256"):
            require(isinstance(row[name], str) and len(row[name]) == 64 and
                    all(c in "0123456789abcdef" for c in row[name]), "Invalid output digest")
        require(set(row["reference_tokens"]) == set(ENCODINGS) and
                all(type(v) is int and v >= 0 for v in row["reference_tokens"].values()), "Invalid exact counts")
        require(type(row["context_chars"]) is int and 0 <= row["context_chars"] <= config["budget_chars"]
                and type(row["result_count"]) is int and 0 <= row["result_count"] <= 5,
                "Saved character/result limit exceeded")
        if "budget_tokens" in config:
            require(row["reference_tokens"][config["tokenizer"]] <= config["budget_tokens"],
                    "Saved exact token count exceeds its registered cap")
        elapsed = row["elapsed_ms"]
        require((kind == "tokens" and elapsed is None) or (kind == "char" and
                type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0), "Invalid timing boundary")
        require(ledger[2 * index] == {"state": "started", "query_id": identity, "configuration": config}
                and ledger[2 * index + 1] == {"state": "finished", **row}, "Ledger order/payload differs")


def audit(args):
    bound = binding(args.binding)
    execution = execution_intent(args.intent, bound, args.binding)
    require(not args.output.exists(), "Preserve an existing audit")
    workers, files = {}, {}
    for path in sorted(args.reports.glob("*-r*-*.json.gz")):
        report = read(path)
        ledger_path = path.with_name(path.name + ".attempts.jsonl")
        if ledger_path.exists():
            ledger_bytes = ledger_path.read_bytes()
        else:
            ledger_bytes = gzip.decompress(ledger_path.with_suffix(ledger_path.suffix + ".gz").read_bytes())
        require(sha(ledger_bytes) == report["ledger_sha256"], "Ledger bytes changed")
        require(report["binding_sha256"] == sha(args.binding.read_bytes()), "Worker binding differs")
        require(report["host"] == execution["host"] and report["intent_sha256"] == sha(args.intent.read_bytes()),
                "Changed worker host/boot or execution intent")
        verify_worker(report, bound, [json.loads(line) for line in ledger_bytes.splitlines()])
        key = (report["kind"], report["round"], report["label"])
        require(key not in workers, "Duplicate worker")
        workers[key] = report
        files[path.name] = sha(path.read_bytes())
    keys = {("tokens", 0, label) for label in ("baseline", "candidate")} | {
        ("char", repetition, label) for repetition in range(4) for label in ("baseline", "candidate")}
    require(set(workers) == keys, "Incomplete registered worker matrix")
    previous_end = 0
    for item in schedule():
        report = workers[(item["kind"], item["round"], item["label"])]
        require(report["started_monotonic_ns"] > previous_end, "Registered ABBA/prefix execution order changed")
        previous_end = report["finished_monotonic_ns"]
    pairs = 0
    for kind, repetition in sorted({(k[0], k[1]) for k in keys}):
        old, new = (workers[(kind, repetition, label)] for label in ("baseline", "candidate"))
        for left, right in zip(old["rows"], new["rows"]):
            for field in ("query_id", "configuration", "payload_sha256", "context_sha256", "context_chars", "result_count", "reference_tokens", "errors"):
                require(left[field] == right[field], "Paired complete output mismatch: " + field)
            pairs += 1
    pooled, rounds = {}, []
    for label in ("baseline", "candidate"):
        values = [row["elapsed_ms"] for repetition in range(4)
                  for row in workers[("char", repetition, label)]["rows"]]
        pooled[label] = latency_summary(values)
    for repetition in range(4):
        rounds.append({"round": repetition, **{label: latency_summary([
            row["elapsed_ms"] for row in workers[("char", repetition, label)]["rows"]])
            for label in ("baseline", "candidate")}})
    change = {name: 100 * (pooled["candidate"][name] / pooled["baseline"][name] - 1)
              for name in ("p50_ms", "p95_ms")}
    accepted = all(v <= 5 + 1e-9 for v in change.values())
    save(args.output, {"version": VERSION, "status": "verified", "accepted": accepted, "created_at": now(),
        "binding_sha256": sha(args.binding.read_bytes()), "files": files,
        "intent_sha256": sha(args.intent.read_bytes()), "host": execution["host"],
        "calls": 2 * pairs, "complete_payload_pairs": pairs, "workers": len(workers),
        "character_diagnostic": {"calls": 2048, "pooled": pooled, "rounds": rounds,
            "candidate_change_percent": change, "nonregression_gate_passed": accepted},
        "interpretation": "Exact-output historical regression plus separate character diagnostic. No new quality claim; no pooling with the formal matrix.",
        "retrieval_calls_during_audit": 0})
    print(json.dumps({"status": "verified", "accepted": accepted, "calls": 2 * pairs, "pairs": pairs, "character_changes": change}), flush=True)
    return 0 if accepted else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("bind", "prepare", "intent", "worker", "audit"))
    for name in ("binding", "source", "baseline-src", "candidate-src", "state", "output", "database", "preparation", "reports", "intent"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--parquet", type=Path, default=ROOT / ".artifacts/round4-inputs/hotpot-validation.parquet")
    parser.add_argument("--label", choices=("baseline", "candidate"))
    parser.add_argument("--kind", choices=("tokens", "char"))
    parser.add_argument("--round", type=int, default=0)
    args = parser.parse_args()
    required = {"bind": ("baseline_src", "candidate_src", "output"),
        "prepare": ("binding", "source", "state", "output"),
        "intent": ("binding", "preparation", "output"),
        "worker": ("binding", "source", "state", "output", "database", "preparation", "label", "kind", "intent"),
        "audit": ("binding", "reports", "output", "intent")}[args.mode]
    require(all(getattr(args, name) is not None for name in required), "Missing mode arguments")
    return {"bind": bind, "prepare": prepare, "intent": intent, "worker": worker, "audit": audit}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
