"""Round-four Q2 compatibility on exact old cohorts; never a speed gate.

Run each source in a fresh process. Source text, model files and SQLite state
stay outside the published reports. This does not modify historical helpers.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
COHORTS = {
    "authored36": ("transfer", 36, "ecc46c474d5184995938419fa985b8e08c0ddb51560da49990247465db6db0b0"),
    "hotpot128": ("hotpotqa", 128, "0791515aca6bccf19a97895cad681e06a07536d6c08050d54189cc64cb819822"),
}
MODEL = "2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25"
BUDGETS = (512, 1024, 2048)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if path.suffix == ".gz":
        raw = gzip.compress(raw, mtime=0)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(raw)
    temporary.replace(path)


def engine(args):
    sys.path.insert(0, str(args.source.resolve()))
    sys.path.insert(1, str(ROOT))
    import memory_book
    from benchmarks.run import engine_source_hash
    package = Path(memory_book.__file__).resolve().parent
    if package != (args.source / "memory_book").resolve():
        raise ValueError("Imported another source")
    if engine_source_hash(package) != args.expected_source_sha:
        raise ValueError("Runtime source pin differs")
    return memory_book.MemoryBook, package, engine_source_hash


def sentinel_data(args):
    if args.cohort == "hotpot128":
        from scripts.round4_cold_development import load_historical, old_manifest
        data, _ = load_historical(args.hotpot_parquet, old_manifest())
    else:
        from benchmarks.semantic_eval import dataset_for
        corpus, count, fingerprint = COHORTS[args.cohort]
        data = dataset_for(SimpleNamespace(corpus=corpus, seed=61, split="heldout", projects=8,
            locomo_path=None, hotpot_path=None, max_queries=0,
            expected_queries=count, expected_dataset_sha256=fingerprint))
    if len(data.queries) != COHORTS[args.cohort][1] or data.fingerprint != COHORTS[args.cohort][2]:
        raise ValueError("Historical cohort identity changed")
    return data


def evaluator_sources():
    names = ("scripts/round4_semantic_compatibility.py", "scripts/round4_cold_development.py",
             "scripts/round3_development_checks.py", "scripts/novelty_cap_qualification.py",
             "benchmarks/hotpot_data.py", "benchmarks/prepare_native_data.py",
             "benchmarks/semantic_eval.py", "benchmarks/native_budget_eval.py",
             "benchmarks/token_compare.py", "benchmarks/run.py", "benchmarks/hotpot_manifest.json")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def validate_preparation(preparation, cohort, data):
    if (preparation.get("cohort") != cohort
            or preparation.get("dataset_sha256") != data.fingerprint
            or preparation.get("queries") != len(data.queries)):
        raise ValueError("Preparation does not identify the requested historical cohort")


def prepare(args):
    if args.output.exists():
        raise ValueError("Preserve existing Q2 preparation")
    MemoryBook, package, source_hash = engine(args)
    from benchmarks.semantic_eval import source_snapshot
    from scripts.novelty_cap_qualification import vectors_digest
    from memory_book.semantic import verify_model_files
    data = sentinel_data(args)
    args.state.mkdir(parents=True, exist_ok=False)
    path = args.state / "prepared.db"
    with MemoryBook(path, max_page_chars=900, cache_size=0,
                    semantic_model_dir=args.model_dir) as book:
        for session in data.sessions:
            book.ingest(session)
        before = source_snapshot(book.db)
        index = book.build_semantic_index()
        if index["model_fingerprint"] != MODEL or index["inference_threads"] != 1:
            raise ValueError("Model/thread pin differs")
        if before != source_snapshot(book.db):
            raise ValueError("Index construction changed originals")
        vectors = vectors_digest(path)
        for label in ("baseline", "candidate"):
            with sqlite3.connect(args.state / (label + ".db")) as target:
                book.db.backup(target)
    if source_hash(package) != args.expected_source_sha:
        raise ValueError("Source changed during preparation")
    write(args.output, {"cohort": args.cohort, "dataset_sha256": data.fingerprint,
        "queries": len(data.queries), "source_sha256": args.expected_source_sha,
        "evaluator_files": evaluator_sources(),
        "ort_disable_telemetry": os.environ.get("ORT_DISABLE_TELEMETRY"),
        "model": verify_model_files(args.model_dir), "semantic_index": index,
        "originals_sha256": before, "vectors": vectors,
        "method": "Baseline builds one index, then SQLite backup gives both sources identical persisted vectors.",
        "interpretation": "Correctness preparation only; no performance inference."})
    print(json.dumps({"prepared": args.cohort, "vector_rows": vectors["rows"]}), flush=True)


def sentinel(args):
    MemoryBook, package, source_hash = engine(args)
    from benchmarks.run import original_turn_texts
    from benchmarks.semantic_eval import page_projection_errors, source_snapshot
    from benchmarks.native_budget_eval import source_errors
    from benchmarks.token_compare import TokenCounter
    from scripts.novelty_cap_qualification import vectors_digest
    from memory_book.semantic import verify_model_files
    data = sentinel_data(args)
    preparation = json.loads(args.preparation.read_bytes())
    validate_preparation(preparation, args.cohort, data)
    if preparation["evaluator_files"] != evaluator_sources():
        raise ValueError("Compatibility evaluator changed after vector preparation")
    counter = TokenCounter(args.tokenizer)
    if counter.version != "0.12.0":
        raise ValueError("Tokenizer pin differs")
    counter.count("readiness")
    path = args.state / (args.label + ".db")
    report = {"status": "running", "cohort": args.cohort, "label": args.label,
        "runtime_sha256": args.expected_source_sha, "dataset_sha256": data.fingerprint,
        "evaluator_files": evaluator_sources(),
        "preparation_sha256": hashlib.sha256(args.preparation.read_bytes()).hexdigest(),
        "ort_disable_telemetry": os.environ.get("ORT_DISABLE_TELEMETRY"),
        "model": verify_model_files(args.model_dir), "configured_generative_model_calls": 0,
        "expected_calls": len(data.queries) * len(BUDGETS), "attempts_started": 0,
        "attempts_finished": 0, "rows": [],
        "settings": {"semantic": True, "coverage": False, "budget_chars": 8000,
                     "token_budgets": list(BUDGETS), "tokenizer": args.tokenizer, "limit": 5,
                     "cache_size": 0, "use_cache": False, "repetitions": 1},
        "interpretation": "Previously-scored regression compatibility only; no timing claim."}
    ledger_path = args.output.with_name(args.output.name + ".attempts.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() or ledger_path.exists():
        raise ValueError("Never overwrite an executed sentinel")
    sources = original_turn_texts(data)
    try:
        with ledger_path.open("x", encoding="utf-8") as ledger, MemoryBook(path,
                max_page_chars=900, cache_size=0, semantic_model_dir=args.model_dir) as book:
            def event(value):
                ledger.write(json.dumps(value, separators=(",", ":")) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            before = source_snapshot(book.db)
            vectors = vectors_digest(path)
            if before != preparation["originals_sha256"] or vectors != preparation["vectors"]:
                raise ValueError("Sources/index differ from prepared snapshot")
            if report["model"] != preparation["model"]:
                raise ValueError("Model files differ")
            pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
            for budget in BUDGETS:
                for case in data.queries:
                    event({"state": "started", "query_id": case.id, "budget_tokens": budget})
                    report["attempts_started"] += 1
                    response = book.recall(case.query, project=case.project, budget_chars=8000,
                        budget_tokens=budget, tokenizer=args.tokenizer, limit=5,
                        use_cache=False, coverage=False, semantic=True)
                    response.pop("latency_ms")
                    errors = {"source": source_errors(response, sources),
                        "projection": page_projection_errors(response, pages),
                        "scope": sum(r["breadcrumb"][0]["id"] != case.project for r in response["results"])
                            if case.project is not None else 0,
                        "token": int(response["context_tokens"] != counter.count(response["context"])
                                     or response["context_tokens"] > budget),
                        "metadata": int(response.get("semantic_model_fingerprint") != MODEL
                                        or response.get("semantic") is not True or response["cache_hit"])}
                    if any(errors.values()):
                        raise ValueError("Source/scope/budget/model invariant failed")
                    row = {"query_id": case.id, "budget_tokens": budget,
                        "payload_sha256": digest(response), "context_sha256": digest(response["context"]),
                        "errors": errors}
                    report["rows"].append(row)
                    report["attempts_finished"] += 1
                    event({"state": "finished", **row})
            if source_snapshot(book.db) != before or vectors_digest(path) != vectors:
                raise ValueError("Read-only recall changed sources/vectors")
            if source_hash(package) != args.expected_source_sha:
                raise ValueError("Runtime changed")
            report.update(status="completed", originals_sha256=before, vectors=vectors)
    except BaseException as error:
        report.update(status="failed-incomplete", error_type=type(error).__name__)
        raise
    finally:
        if ledger_path.exists():
            report["ledger_sha256"] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        write(args.output, report)
    print(json.dumps({"cohort": args.cohort, "label": args.label,
                      "finished": report["attempts_finished"], "status": report["status"]}), flush=True)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "worker"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cohort", choices=tuple(COHORTS), required=True)
    parser.add_argument("--label", choices=("baseline", "candidate"))
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--hotpot-parquet", type=Path,
                        default=ROOT / ".artifacts/round4-inputs/hotpot-validation.parquet")
    parser.add_argument("--preparation", type=Path)
    parser.add_argument("--tokenizer", choices=("cl100k_base", "o200k_base"), default="cl100k_base")
    args = parser.parse_args()
    if os.environ.get("ORT_DISABLE_TELEMETRY") != "1":
        parser.error("Set ORT_DISABLE_TELEMETRY=1 before process launch")
    if args.mode == "worker" and not (args.label and args.preparation):
        parser.error("Worker needs --label and --preparation")
    from benchmarks.token_compare import checkout_provenance
    if not checkout_provenance(args.source.resolve() / "memory_book")["commit_identifies_source"]:
        parser.error("Compatibility runtime must match its exact committed source")
    return prepare(args) if args.mode == "prepare" else sentinel(args)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
