"""Compare frozen C6 Book output with saved v0.3.2 Hotpot256 payload hashes.

This is an old-cohort compatibility check, not new quality or timing evidence.
No competitor, model download, question selection or semantic call is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from benchmarks.round2_eval import documents_from
from benchmarks.run import engine_source_hash
from benchmarks.semantic_eval import source_snapshot
from scripts.benchmark_default_recall import indexed_content
from scripts.round4_data import BINDING, MANIFEST, canonical, digest, git, load, require, runtime_hash, sha
import memory_book
from memory_book import MemoryBook

REFERENCE = ROOT / "benchmarks/results/round4-comparison-43363060062-1"
BASELINE = "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"
CANDIDATE_COMMIT = None  # Blocked until the final C6 source commit is frozen.
CANDIDATE = None  # Blocked until the final C6 runtime SHA256 is frozen.
NAMESPACE = "round5-c6-hotpot-regression"
CONFIGS = [{"budget_chars": 8000, "tokenizer": name, "budget_tokens": cap}
           for name in ("cl100k_base", "o200k_base") for cap in (512, 1024, 2048)]


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("wb") as stream:
        stream.write(gzip.compress(canonical(value) + b"\n", mtime=0))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(isinstance(CANDIDATE_COMMIT, str) and len(CANDIDATE_COMMIT) == 40
            and isinstance(CANDIDATE, str) and len(CANDIDATE) == 64
            and all(c in "0123456789abcdef" for c in CANDIDATE_COMMIT + CANDIDATE),
            "C6 source is not frozen; compatibility retrieval is intentionally blocked")
    require(args.report.name.endswith(".json.gz"), "Report must end in .json.gz")
    require(args.report.name.startswith(NAMESPACE), "Use the separate C6 report and ledger namespace")
    require(not args.report.exists(), "Never overwrite an earlier attempt")
    args.state.mkdir(parents=True, exist_ok=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    ledger_path = args.report.with_suffix("").with_suffix(".attempts.jsonl")
    report = {"schema_version": 1, "evaluator": NAMESPACE + "-1",
        "status": "running", "started_at": now(), "expected_calls": 2304, "rows": [],
        "boundary": "Old round4 Hotpot256; complete Book payload excluding latency_ms only. No new quality or performance claim.",
        "semantic": False, "coverage": False, "use_cache": False, "result_limit": 5,
        "setup": "One fresh C6 archive; verify all source/index projections and canonical documents against both historical archives before recall.",
        "historical_timestamp_boundary": "Project created/updated and chapter/session updated host timestamps are not cross-archive compared; each complete source snapshot must remain unchanged within this run.",
        "helper_sha256": sha(Path(__file__).read_bytes()), "reference_reports": {}}
    save(args.report, report)
    try:
        source = Path(memory_book.__file__).resolve().parent
        require(source == ROOT / "src/memory_book", "Unexpected imported runtime")
        commit = git("rev-parse", CANDIDATE_COMMIT + "^{commit}").decode().strip()
        require(commit == CANDIDATE_COMMIT, "Frozen C6 commit differs")
        require(engine_source_hash(source) == runtime_hash(commit) == CANDIDATE, "Frozen C6 source changed")
        report["candidate"] = {"commit": commit, "runtime_sha256": CANDIDATE,
            "checkout_commit": git("rev-parse", "HEAD").decode().strip()}
        report["packages"] = {name: importlib.metadata.version(name) for name in ("tiktoken", "pyarrow")}
        require(report["packages"] == {"tiktoken": "0.12.0", "pyarrow": "26.0.1"}, "Evaluator package pins differ")
        data = load(args.parquet, ROOT / BINDING)
        cases = {case.id: case for case in data.queries}
        require(len(cases) == len(data.queries) == 256, "Expected frozen 256 query IDs")
        report["dataset"] = {"fingerprint": data.fingerprint, "queries": len(cases),
            "sessions": len(data.sessions), "turns": data.turn_count,
            "source_characters": data.source_characters, "selected_ids_sha256": digest(list(cases)),
            "parquet_sha256": sha(args.parquet.read_bytes()), "parquet_bytes": args.parquet.stat().st_size,
            "binding_sha256": sha((ROOT / BINDING).read_bytes()), "manifest_sha256": sha((ROOT / MANIFEST).read_bytes())}
        references = {}
        for stage, count in (("native", 1536), ("component", 768)):
            path = REFERENCE / ("candidate-" + stage + ".json.gz")
            raw = path.read_bytes()
            old = json.loads(gzip.decompress(raw))
            metadata = old["metadata"]
            require(old["status"] == "completed" and old["validation"]["passed"], "Historical report incomplete")
            require(old["dataset"]["sha256"] == data.fingerprint, "Historical dataset differs")
            require(old["binding_sha256"] == report["dataset"]["binding_sha256"] and
                    old["cohort_manifest_sha256"] == report["dataset"]["manifest_sha256"], "Historical binding differs")
            require(metadata.get("source_sha256_before", metadata.get("source_sha256")) == BASELINE
                    and metadata["source_sha256_after"] == BASELINE and metadata["source_unchanged"], "Historical runtime differs")
            require(all(metadata[key] is False for key in ("semantic", "coverage", "project_local_fts_statistics")), "Historical mode differs")
            samples = old["timing_rows"]
            require(len(samples) == count and all(row["status"] == "ok" for row in samples), "Historical calls incomplete")
            expected = Counter((identity, 0, digest(config)) for config in CONFIGS for identity in cases) if stage == "native" else Counter((identity, rep) for rep in range(3) for identity in cases)
            observed = Counter((row["id"], row["repetition"], digest(row["configuration"])) if stage == "native" else (row["id"], row["repetition"]) for row in samples)
            require(observed == expected, "Historical call matrix differs")
            report["reference_reports"][stage] = {"path": str(path.relative_to(ROOT)),
                "file_sha256": sha(raw), "calls": count, "runtime_sha256": BASELINE,
                "runtime_commit": metadata["source_provenance"]["git_commit"],
                "payload_field": "payload_sha256" if stage == "native" else "book_payload_sha256"}
            references[stage] = old
        save(args.report, report)
        with ledger_path.open("x", encoding="utf-8") as ledger, MemoryBook(args.state / "book.db", max_page_chars=900, cache_size=0) as book:
            for session in data.sessions:
                book.ingest(session)
            index, documents = indexed_content(book.db), digest(documents_from(book))
            for old in references.values():
                require(index == old["metadata"]["indexed_content_before"], "Original/index projection differs")
                require(documents == old["metadata"]["documents_sha256"], "Canonical page documents differ")
            originals = source_snapshot(book.db)
            report["archive_before"] = {"indexed_content": index, "documents_sha256": documents,
                "source_snapshot_sha256": originals, "stats": book.stats()}
            save(args.report, report)
            for stage, old in references.items():
                for sample in old["timing_rows"]:
                    case = cases[sample["id"]]
                    config = sample["configuration"] if stage == "native" else {"budget_chars": 100000}
                    field = report["reference_reports"][stage]["payload_field"]
                    row = {"sequence": len(report["rows"]), "stage": stage, "id": case.id,
                        "repetition": sample["repetition"], "configuration": config, "expected_payload_sha256": sample[field]}
                    ledger.write(json.dumps({**row, "event": "started"}, sort_keys=True) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                    try:
                        response = book.recall(case.query, project=case.project, limit=5, use_cache=False,
                            semantic=False, coverage=False, **config)
                        require("latency_ms" in response, "Response lacks latency_ms")
                        response.pop("latency_ms")
                        row["actual_payload_sha256"] = digest(response)
                        row["status"] = "match" if row["actual_payload_sha256"] == row["expected_payload_sha256"] else "mismatch"
                    except Exception as exc:
                        row.update(status="error", error_type=type(exc).__name__, error=str(exc))
                    report["rows"].append(row)
                    ledger.write(json.dumps({**row, "event": "finished"}, sort_keys=True) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                    if len(report["rows"]) % 256 == 0:
                        save(args.report, report)
                        print(json.dumps({"completed_calls": len(report["rows"]), "statuses": dict(Counter(r["status"] for r in report["rows"]))}), flush=True)
            report["archive_after"] = {"indexed_content": indexed_content(book.db), "documents_sha256": digest(documents_from(book)),
                "source_snapshot_sha256": source_snapshot(book.db), "stats": book.stats()}
            require(report["archive_after"]["source_snapshot_sha256"] == originals and
                    report["archive_after"]["indexed_content"] == index and report["archive_after"]["documents_sha256"] == documents,
                    "Source data changed during recall")
            require(book.stats()["cache_entries"] == 0, "Query result cache was populated")
        report["runtime_sha256_after"] = engine_source_hash(source)
        require(report["runtime_sha256_after"] == CANDIDATE, "Runtime changed during check")
        report["status"] = "passed" if len(report["rows"]) == 2304 and all(row["status"] == "match" for row in report["rows"]) else "failed"
    except BaseException as exc:
        report.update(status="error", error_type=type(exc).__name__, error=str(exc))
    finally:
        report["finished_at"] = now()
        report["counts"] = {stage: dict(Counter(row["status"] for row in report["rows"] if row["stage"] == stage)) for stage in ("native", "component")}
        if ledger_path.exists():
            report["attempt_ledger_sha256"] = sha(ledger_path.read_bytes())
        save(args.report, report)
        print(json.dumps({key: report[key] for key in ("status", "counts", "expected_calls")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
