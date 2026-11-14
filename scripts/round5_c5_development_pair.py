"""Full frozen old-data C5 diagnostic; never substitutes for the formal run.

Two balanced rounds, all 168/1015 old queries, four native settings. Retain
every timing and payload hash, including negative cells. Sources are commit-bound.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = (("native-char4000", {"budget_chars": 4000}),
           ("native-token512", {"budget_chars": 8000, "budget_tokens": 512}),
           ("native-token1024", {"budget_chars": 8000, "budget_tokens": 1024}),
           ("native-token2048", {"budget_chars": 8000, "budget_tokens": 2048}))


def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(raw)
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def worker(args):
    sys.path[:0] = [str(args.source.resolve()), str(ROOT)]
    import memory_book
    from memory_book.token_budget import TokenCounter
    from benchmarks.run import engine_source_hash
    from benchmarks.semantic_eval import source_snapshot
    from scripts.benchmark_default_recall import dataset, indexed_content
    from scripts.round4_data import runtime_hash
    from scripts.round5_c5_performance import (memo_diagnostics, native_memo_snapshot,
                                               verify_native_memo)
    package = Path(memory_book.__file__).resolve().parent
    assert package == args.source.resolve() / "memory_book"
    assert engine_source_hash(package) == args.source_sha
    assert runtime_hash(args.source_commit) == args.source_sha
    assert not args.output.exists()
    args.state.mkdir(parents=True, exist_ok=False)
    target = args.state / "book.db"
    shutil.copy2(args.db_directory / (args.cohort + ".db"), target)
    data = dataset(args.cohort, args.locomo_path)
    cases = sorted(data.queries, key=lambda c: (hashlib.sha256(
        ("round4-native-development-v1/" + c.id).encode()).digest(), c.id))
    counter = TokenCounter("cl100k_base")
    counter.count("Initialize the tokenizer outside timing.")
    result = {"label": args.label, "cohort": args.cohort, "round": args.round,
              "runtime_source_sha256": args.source_sha, "runtime_source_commit": args.source_commit,
              "dataset_sha256": data.fingerprint,
              "status": "running", "cells": [],
              "native_token_count_memo": memo_diagnostics(),
              "invariant_checks": {"calls": 0, "exact_token_calls": 0, "violations": 0}}
    save(args.output, result)
    try:
        with memory_book.MemoryBook(target, cache_size=0) as book:
            result["archive_before"] = {"source_snapshot_sha256": source_snapshot(book.db),
                "indexed_content": indexed_content(book.db), "revision": book.revision,
                "cache_entries": book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}
            assert result["archive_before"]["cache_entries"] == 0
            for number, (config, options) in enumerate(CONFIGS):
                ordered = list(cases)
                random.Random(91261 + args.round * 1009 + number).shuffle(ordered)
                cell = {"configuration": config, "rows": []}
                result["cells"].append(cell)
                memo = {"id": config, "before": native_memo_snapshot(book, args.label),
                        "first_query_id": None, "after_first_call": None, "after": None}
                result["native_token_count_memo"]["configurations"].append(memo)
                for case in ordered:
                    start = time.perf_counter_ns()
                    response = book.recall(case.query, project=case.project,
                                           use_cache=False, **options)
                    wall_ms = (time.perf_counter_ns() - start) / 1e6
                    response.pop("latency_ms")
                    row = {"query_id": case.id, "wall_ms": wall_ms, "payload_sha256": digest(response)}
                    cell["rows"].append(row)
                    checks = {"context_size": len(response["context"]) == response["context_chars"],
                              "character_cap": len(response["context"]) <= options["budget_chars"],
                              "cache_hit_false": response["cache_hit"] is False,
                              "revision": response["revision"] == result["archive_before"]["revision"]}
                    result["invariant_checks"]["calls"] += 1
                    if "budget_tokens" in options:
                        exact = counter.count(response["context"])
                        checks["exact_token_count"] = exact == response["context_tokens"]
                        checks["token_cap"] = exact <= options["budget_tokens"]
                        result["invariant_checks"]["exact_token_calls"] += 1
                    row["invariants"] = checks
                    result["invariant_checks"]["violations"] += sum(not passed for passed in checks.values())
                    assert all(checks.values()), (case.id, config, checks)
                    if len(cell["rows"]) == 1:
                        memo["first_query_id"] = case.id
                        memo["after_first_call"] = native_memo_snapshot(book, args.label)
                memo["after"] = native_memo_snapshot(book, args.label)
                save(args.output, result)
            result["archive_after"] = {"source_snapshot_sha256": source_snapshot(book.db),
                "indexed_content": indexed_content(book.db), "revision": book.revision,
                "cache_entries": book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0]}
            assert result["archive_after"] == result["archive_before"]
            verify_native_memo(result, [{"id": cell["configuration"], "surface": "native",
                "rows": cell["rows"]} for cell in result["cells"]])
        assert engine_source_hash(package) == args.source_sha
        result["status"] = "completed"
    except BaseException as error:
        result.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        save(args.output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--baseline-sha")
    parser.add_argument("--baseline-commit")
    parser.add_argument("--candidate-src", type=Path)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--source-commit")
    parser.add_argument("--label")
    parser.add_argument("--cohort")
    parser.add_argument("--round", type=int)
    parser.add_argument("--db-directory", type=Path, required=True)
    parser.add_argument("--locomo-path", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    sys.path.insert(0, str(ROOT))
    from scripts.round5_c5_performance import (BASELINE, C3_SOURCE, C4_SOURCE, DEVELOPMENT_PLAN_PATH,
        DEVELOPMENT_PLAN_SHA256, continuation_registration, source_identity)
    registration = continuation_registration()
    sources = {label: {"commit": getattr(args, label + "_commit"),
                      "runtime_sha256": getattr(args, label + "_sha")}
               for label in ("baseline", "candidate")}
    assert sources["baseline"] == BASELINE
    assert sources["candidate"]["runtime_sha256"] not in {
        source["runtime_sha256"] for source in (BASELINE, C3_SOURCE, C4_SOURCE)}
    for label in sources:
        assert source_identity(getattr(args, label + "_src")) == sources[label]
    development = json.loads((ROOT / DEVELOPMENT_PLAN_PATH).read_bytes())
    assert [("native-" + c["id"], {key: value for key, value in c.items()
        if key in ("budget_chars", "budget_tokens") and value is not None}) for c in development["configs"]] == list(CONFIGS)
    assert [(c["name"], c["queries"]) for c in development["cohorts"]] == [("synthetic61", 168), ("public1015", 1015)]
    assert not args.output.exists()
    args.state.mkdir(parents=True, exist_ok=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "Old-data native development diagnostic, not formal acceptance; all attempts and negative cells retained.",
              "expected_calls": 18928, "workers": [],
              "development_plan": DEVELOPMENT_PLAN_PATH, "development_plan_sha256": DEVELOPMENT_PLAN_SHA256,
              "continuation_registration": registration, "sources": sources,
              "memo_policy": "Fresh empty per-book exact-token-count memo, fixed 2048 entries and 2MiB retained text-object bytes; no extra prewarming or clearing. Query-result cache remains disabled."}
    save(args.output, report)
    try:
        for cohort in ("synthetic61", "public1015"):
            for round_number, order in enumerate((("baseline", "candidate"), ("candidate", "baseline"))):
                for label in order:
                    identity = f"{cohort}-{round_number}-{label}"
                    worker_output = args.state / (identity + ".json")
                    command = [sys.executable, str(Path(__file__).resolve()), "--worker",
                               "--source", str(getattr(args, label + "_src").resolve()),
                               "--source-sha", getattr(args, label + "_sha"),
                               "--source-commit", getattr(args, label + "_commit"), "--label", label,
                               "--cohort", cohort, "--round", str(round_number),
                               "--db-directory", str(args.db_directory.resolve()),
                               "--locomo-path", str(args.locomo_path.resolve()),
                               "--state", str(args.state / identity), "--output", str(worker_output)]
                    subprocess.run(command, check=True)
                    value = json.loads(worker_output.read_bytes())
                    assert value["status"] == "completed"
                    report["workers"].append(value)
                    save(args.output, report)
                    print(json.dumps({"worker": identity, "calls": sum(len(c["rows"]) for c in value["cells"])}), flush=True)
        assert sum(len(c["rows"]) for w in report["workers"] for c in w["cells"]) == 18928
        paired = {}
        for value in report["workers"]:
            for cell in value["cells"]:
                for row in cell["rows"]:
                    key = (value["cohort"], value["round"], cell["configuration"], row["query_id"])
                    paired.setdefault(key, {})[value["label"]] = row["payload_sha256"]
        assert len(paired) == 9464 and all(set(pair) == {"baseline", "candidate"}
            and pair["baseline"] == pair["candidate"] for pair in paired.values()), "Complete saved C5 development payload pair differs"
        report["complete_payload_pairs"] = len(paired)
        report["complete_payload_mismatches"] = 0
        assert report["script_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(args.output, report)


if __name__ == "__main__":
    main()
