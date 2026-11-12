"""Read-only audit of old-data Q2 compatibility; does not call recall or models."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COHORTS = {
    "authored36": (36, "ecc46c474d5184995938419fa985b8e08c0ddb51560da49990247465db6db0b0"),
    "hotpot128": (128, "0791515aca6bccf19a97895cad681e06a07536d6c08050d54189cc64cb819822"),
}
SOURCES = {
    "baseline": ("dd2f88be742ed330269e7dd5915b6f75089d7fef",
                 "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57"),
    "candidate": ("6fbee6051b0a2f61cf69b22e35a5e914650ab0c7",
                  "799f3960cefd2dbe2d88f571e141a92d35a1e4cf97d1b22bc3ccc698d8c3be39"),
}
SETTINGS = {"semantic": True, "coverage": False, "budget_chars": 8000,
    "token_budgets": [512, 1024, 2048], "tokenizer": "cl100k_base", "limit": 5,
    "cache_size": 0, "use_cache": False, "repetitions": 1}
MODEL = "2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_hash(commit):
    prefix = "src/memory_book/"
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit, prefix],
                                    cwd=ROOT, text=True).splitlines()
    result = hashlib.sha256()
    for name in sorted(name for name in names if name.endswith(".py")):
        raw = subprocess.check_output(["git", "show", commit + ":" + name], cwd=ROOT)
        result.update(name.removeprefix(prefix).encode() + b"\0" + raw + b"\0")
    return result.hexdigest()


def audit(directory, cohorts):
    for label, (commit, fingerprint) in SOURCES.items():
        require(source_hash(commit) == fingerprint, "Source commit pin differs: " + label)
    historical = json.loads((ROOT / "benchmarks/round2_candidate.json").read_bytes())
    helpers = historical["evaluator_sha256"]
    require(len(helpers) == 58, "Historical binding count differs")
    for name, fingerprint in helpers.items():
        require(sha((ROOT / name).read_bytes()) == fingerprint, "Historical helper changed: " + name)
    reports = []
    files = {}

    def load(name):
        path = directory / name
        raw = path.read_bytes()
        files[name] = {"bytes": len(raw), "sha256": sha(raw)}
        return gzip.decompress(raw) if name.endswith(".gz") else raw

    for cohort in cohorts:
        count, dataset_sha = COHORTS[cohort]
        preparation = json.loads(load("q2-" + cohort + "-preparation.json"))
        require(preparation["cohort"] == cohort and preparation["queries"] == count
                and preparation["dataset_sha256"] == dataset_sha, "Preparation dataset differs")
        require(preparation["source_sha256"] == SOURCES["baseline"][1], "Preparation source differs")
        require(preparation["semantic_index"]["inference_threads"] == 1
                and preparation["semantic_index"]["model_fingerprint"] == MODEL
                and preparation["vectors"]["model_fingerprint"] == MODEL, "Model/thread pin differs")
        by_label = {}
        for label in SOURCES:
            name = "q2-" + cohort + "-" + label + ".json.gz"
            report = json.loads(load(name))
            require(report["status"] == "completed" and report["cohort"] == cohort
                    and report["label"] == label, "Worker identity/status differs")
            require(report["runtime_sha256"] == SOURCES[label][1]
                    and report["dataset_sha256"] == dataset_sha, "Worker source/dataset differs")
            require(report["settings"] == SETTINGS and report["configured_generative_model_calls"] == 0,
                    "Worker settings differ")
            require(report["expected_calls"] == report["attempts_started"] == report["attempts_finished"]
                    == len(report["rows"]) == count * 3, "Incomplete attempts")
            for key in ("model", "vectors", "originals_sha256"):
                require(report[key] == preparation[key], "Worker prepared snapshot differs: " + key)
            ledger_raw = load(name + ".attempts.jsonl.gz")
            require(sha(ledger_raw) == report["ledger_sha256"], "Raw ledger hash differs")
            ledger = [json.loads(line) for line in ledger_raw.splitlines()]
            require(len(ledger) == count * 6, "Incomplete ledger")
            seen = set()
            for position, row in enumerate(report["rows"]):
                key = (row["budget_tokens"], row["query_id"])
                require(key not in seen and row["budget_tokens"] in SETTINGS["token_budgets"],
                        "Duplicate/unregistered sample")
                seen.add(key)
                require(row["errors"] == dict.fromkeys(("source", "projection", "scope", "token", "metadata"), 0),
                        "Nonzero invariant error")
                require(ledger[2 * position] == {"state": "started", "query_id": row["query_id"],
                        "budget_tokens": row["budget_tokens"]}, "Started event differs")
                require(ledger[2 * position + 1] == {"state": "finished", **row}, "Finished event differs")
            ids = [row["query_id"] for row in report["rows"][:count]]
            require(len(set(ids)) == count, "Query count differs")
            require([(row["budget_tokens"], row["query_id"]) for row in report["rows"]]
                    == [(budget, query) for budget in SETTINGS["token_budgets"] for query in ids],
                    "Sample matrix/order differs")
            by_label[label] = report["rows"]
        require(by_label["baseline"] == by_label["candidate"], "Full payload/context hash differs")
        reports.append({"cohort": cohort, "dataset_sha256": dataset_sha, "queries": count,
            "calls": count * 6, "payload_pairs": count * 3, "payload_differences": 0,
            "invariant_errors": 0, "cells": [{"budget_tokens": budget, "pairs": count,
                "payload_differences": 0} for budget in SETTINGS["token_budgets"]],
            "vectors": preparation["vectors"], "originals_sha256": preparation["originals_sha256"]})
    return {"status": "passed", "interpretation": "Previously-scored Q2 regression compatibility only; no speed or generalization claim.",
        "comparison": "Full returned JSON SHA256 after removing latency_ms only; no result/score/context fields removed.",
        "query_embedding_boundary": "Pinned model files/settings and equal output payloads; persisted index-vector equality does not assert separately measured query-embedding identity.",
        "sources": {label: {"commit": commit, "runtime_sha256": fingerprint}
                    for label, (commit, fingerprint) in SOURCES.items()},
        "historical_helpers_verified": len(helpers), "settings": SETTINGS, "cohorts": reports,
        "calls": sum(row["calls"] for row in reports),
        "payload_pairs": sum(row["payload_pairs"] for row in reports),
        "payload_differences": 0, "invariant_errors": 0, "public_files": files,
        "audit_script_sha256": sha(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--cohorts", nargs="+", choices=tuple(COHORTS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(len(args.cohorts) == len(set(args.cohorts)), "Duplicate cohort")
    result = audit(args.directory, args.cohorts)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "calls", "payload_pairs", "payload_differences")}))


if __name__ == "__main__":
    main()
