"""Compare complete native-token payloads against a frozen source checkout.

Each engine runs in its own process. Only per-query hashes and timings are
published; source passages are not included. This is a development equivalence
check, not a new retrieval-quality or cross-domain generalization experiment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import random
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import checkout_provenance, latency_summary, load_dataset


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def worker(args):
    sys.path.insert(0, str(args.engine_src.resolve()))
    from memory_book import MemoryBook
    import memory_book
    from memory_book.token_budget import TokenCounter
    source = Path(memory_book.__file__).parent
    before = engine_source_hash(source)
    data = load_dataset("synthetic", 61, "development", 8, None, 0)
    if len(data.queries) != 168 or data.fingerprint != "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26":
        raise ValueError("Development corpus differs from frozen input")
    report = {"source_provenance": checkout_provenance(source), "source_sha256_before": before,
              "dataset": data.description(), "configurations": []}
    with tempfile.TemporaryDirectory(prefix="native-equivalence-") as directory:
        with MemoryBook(Path(directory) / "memory.db", max_page_chars=900, cache_size=0) as book:
            started = time.perf_counter_ns()
            for session in data.sessions:
                book.ingest(session)
            report["ingestion_ms"] = (time.perf_counter_ns() - started) / 1e6
            for encoding in ("cl100k_base", "o200k_base"):
                TokenCounter(encoding).count("Initialize the tokenizer outside query timing.")
            for chars in (2000, 8000):
                for encoding in ("cl100k_base", "o200k_base"):
                    for tokens in (512, 1024, 2048):
                        rows, elapsed, mismatches = {}, [], []
                        for repetition in range(args.repeats):
                            cases = list(data.queries)
                            random.Random(61 + 1009 * repetition).shuffle(cases)
                            for case in cases:
                                started = time.perf_counter_ns()
                                result = book.recall(case.query, project=case.project, budget_chars=chars,
                                    budget_tokens=tokens, tokenizer=encoding, limit=5, use_cache=False)
                                elapsed.append((time.perf_counter_ns() - started) / 1e6)
                                result.pop("latency_ms")
                                value = {"id": case.id, "payload_sha256": digest(result),
                                         "context_sha256": hashlib.sha256(result["context"].encode()).hexdigest()}
                                if repetition == 0:
                                    rows[case.id] = value
                                elif value != rows[case.id]:
                                    mismatches.append(case.id)
                        configuration = {"budget_chars": chars, "tokenizer": encoding, "budget_tokens": tokens,
                            "latency": latency_summary(elapsed), "query_results": [rows[c.id] for c in data.queries],
                            "repeat_payload_mismatches": mismatches}
                        report["configurations"].append(configuration)
                        print(json.dumps({"source": str(source), "chars": chars, "tokens": tokens,
                                          "encoding": encoding, "latency": configuration["latency"]}),
                              file=sys.stderr, flush=True)
    report["source_sha256_after"] = engine_source_hash(source)
    report["source_unchanged"] = before == report["source_sha256_after"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--candidate-src", type=Path, default=Path("src"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    if args.output.exists():
        parser.error("Preserve existing output and select a new path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.engine_src:
        args.output.write_text(json.dumps(worker(args), ensure_ascii=False))
        return
    if not args.baseline_src:
        parser.error("--baseline-src is required")
    evaluator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    reports = []
    with tempfile.TemporaryDirectory(prefix="native-equivalence-workers-") as directory:
        for index, source in enumerate((args.baseline_src, args.candidate_src)):
            output = Path(directory) / f"{index}.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--engine-src", str(source.resolve()),
                "--repeats", str(args.repeats), "--output", str(output)], check=True)
            reports.append(json.loads(output.read_text()))
    comparisons = []
    for old, new in zip(reports[0]["configurations"], reports[1]["configurations"], strict=True):
        keys = ("budget_chars", "tokenizer", "budget_tokens")
        if any(old[k] != new[k] for k in keys):
            raise ValueError("Worker configurations differ")
        mismatches = [a["id"] for a, b in zip(old["query_results"], new["query_results"], strict=True) if a != b]
        comparisons.append({**{k: new[k] for k in keys}, "queries": len(new["query_results"]),
                            "payload_mismatches": mismatches, "baseline_latency": old["latency"],
                            "candidate_latency": new["latency"]})
    report = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Complete native-token payload equivalence and development timing; latency_ms alone is excluded from payload hashes.",
        "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "platform": platform.platform()},
        "methodology": "Independent sequential workers; no result cache; random query order with seed 61 + 1009 * repetition. Model/tokenizer loading is outside timed calls. Warm OS/SQLite caches; timing is host-specific.",
        "repeats": args.repeats, "evaluator_sha256": evaluator_hash, "engines": reports, "comparisons": comparisons,
        "validation": {"passed": all(not c["payload_mismatches"] for c in comparisons)
            and all(r["source_unchanged"] and all(not c["repeat_payload_mismatches"] for c in r["configurations"]) for r in reports)
            and evaluator_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    args.output.write_bytes(gzip.compress(raw, mtime=0))
    summary = {key: value for key, value in report.items() if key != "engines"}
    summary["sources"] = [{key: value for key, value in r.items() if key != "configurations"} for r in reports]
    summary["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.with_suffix("").with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"validation": report["validation"], "queries_compared": sum(c["queries"] for c in comparisons)}))
    if not report["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
