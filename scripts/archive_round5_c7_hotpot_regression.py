"""Audit and losslessly archive the one completed C7 Hotpot compatibility run.

Only saved JSON, JSONL and local Git objects are read. This script does not
import the product, open an archive, select questions, recall or measure time.
Run again with --check to reproduce the summary without writing anything.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "benchmarks/reports/round5-c7-hotpot-regression"
PREFLIGHT = "benchmarks/reports/round5-c7-hotpot-preflight/missing-sparse-input.json.gz"
REFERENCE = "benchmarks/results/round4-comparison-43363060062-1"
BINDING = "benchmarks/experiments/round4-validation-binding.json"
MANIFEST = "benchmarks/experiments/round4-hotpot256-manifest.json"
HELPER = "scripts/round5_c7_hotpot_regression.py"
SOURCE = "d0c84cbfc9bad440ad447d41e211d070ef5b2cae"
RUNTIME = "55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45"
BASELINE = "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"
BASELINE_COMMIT = "2d7b5e38839fb21724ad3beec6b6ebabbda45636"
CONFIGS = [{"budget_chars": 8000, "tokenizer": name, "budget_tokens": cap}
           for name in ("cl100k_base", "o200k_base") for cap in (512, 1024, 2048)]
START_FIELDS = ("sequence", "stage", "id", "repetition", "configuration", "expected_payload_sha256")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, timeout=30)


def git_bytes(commit, path):
    return git("show", commit + ":" + path)


def runtime_hash(commit):
    prefix = "src/memory_book/"
    names = sorted(name for name in git("ls-tree", "-r", "--name-only", commit,
                                       prefix).decode().splitlines() if name.endswith(".py"))
    require(bool(names), "Frozen runtime files are unavailable")
    result = hashlib.sha256()
    for name in names:
        result.update(name.removeprefix(prefix).encode() + b"\0" + git_bytes(commit, name) + b"\0")
    return result.hexdigest()


def lossless_gzip(raw):
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped:
        zipped.write(raw)
    result = stream.getvalue()
    require(gzip.decompress(result) == raw, "Compressed ledger changed bytes")
    return result


def validate_rows(report, references, ledger, query_ids):
    """Reject missing, repeated, substituted or mismatched saved observations."""
    rows = report["rows"]
    require(len(rows) == report["expected_calls"] == 2304, "Expected exactly 2304 completed calls")
    require(len(ledger) == 4608, "Expected all 4608 original start/finish events")
    expected_matrix = Counter(("native", identity, 0, canonical(config))
                             for identity in query_ids for config in CONFIGS)
    expected_matrix.update(("component", identity, repetition, canonical({"budget_chars": 100000}))
                          for identity in query_ids for repetition in range(3))
    actual_matrix = Counter((row["stage"], row["id"], row["repetition"], canonical(row["configuration"]))
                            for row in rows)
    require(actual_matrix == expected_matrix, "Compatibility call matrix differs")
    expected_rows = []
    for stage, count, field in (("native", 1536, "payload_sha256"),
                                ("component", 768, "book_payload_sha256")):
        samples = references[stage]["timing_rows"]
        require(len(samples) == count and all(row["status"] == "ok" for row in samples),
                "Historical call count/status differs")
        for sample in samples:
            expected_rows.append({"sequence": len(expected_rows), "stage": stage,
                "id": sample["id"], "repetition": sample["repetition"],
                "configuration": sample["configuration"] if stage == "native" else {"budget_chars": 100000},
                "expected_payload_sha256": sample[field], "actual_payload_sha256": sample[field],
                "status": "match"})
    require(rows == expected_rows, "Complete payload hashes/order differ from historical raw reports")
    for number, row in enumerate(rows):
        require(ledger[2 * number] == {**{key: row[key] for key in START_FIELDS}, "event": "started"}
                and ledger[2 * number + 1] == {**row, "event": "finished"},
                "Original ledger differs from saved complete observations")
    counts = {stage: dict(Counter(row["status"] for row in rows if row["stage"] == stage))
              for stage in ("native", "component")}
    require(counts == report["counts"] == {"native": {"match": 1536}, "component": {"match": 768}},
            "Reported compatibility counts differ")


def audited_archive():
    report_bytes = (ROOT / (PREFIX + ".json.gz")).read_bytes()
    report_raw = gzip.decompress(report_bytes)
    report = json.loads(report_raw)
    require(report["schema_version"] == 1 and report["status"] == "passed"
            and report["evaluator"] == "round5-c7-hotpot-regression-1", "Wrong or incomplete C7 report")
    require({key: report["candidate"][key] for key in ("commit", "runtime_sha256")}
            == {"commit": SOURCE, "runtime_sha256": RUNTIME}
            and report["runtime_sha256_after"] == runtime_hash(SOURCE) == RUNTIME
            and runtime_hash(report["candidate"]["checkout_commit"]) == RUNTIME,
            "Candidate source changed")
    require(report["helper_sha256"] == sha((ROOT / HELPER).read_bytes())
            == sha(git_bytes(report["candidate"]["checkout_commit"], HELPER)),
            "Executed helper differs from the recorded execution checkout")
    require(report["packages"] == {"tiktoken": "0.12.0", "pyarrow": "26.0.1"}
            and report["result_limit"] == 5
            and all(report[key] is False for key in ("semantic", "coverage", "use_cache")),
            "Recorded execution settings differ")
    binding_raw, manifest_raw = (ROOT / BINDING).read_bytes(), (ROOT / MANIFEST).read_bytes()
    require(binding_raw == git_bytes(SOURCE, BINDING) and manifest_raw == git_bytes(SOURCE, MANIFEST),
            "Frozen cohort inputs changed")
    binding, manifest = json.loads(binding_raw), json.loads(manifest_raw)
    ids, dataset = manifest["selected_ids"], report["dataset"]
    require(len(ids) == len(set(ids)) == dataset["queries"] == 256
            and dataset["selected_ids_sha256"] == manifest["selected_ids_sha256"] == sha(canonical(ids))
            and dataset["fingerprint"] == manifest["dataset_sha256"]
            and dataset["binding_sha256"] == sha(binding_raw)
            and dataset["manifest_sha256"] == sha(manifest_raw)
            and dataset["parquet_sha256"] == manifest["upstream_sha256"]
                == "c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6"
            and dataset["parquet_bytes"] == manifest["upstream_bytes"] == 27452575
            and dataset["turns"] == manifest["source_turns"]
            and dataset["sessions"] == manifest["selected_context_paragraphs"]
            and dataset["source_characters"] == manifest["source_characters"], "Frozen dataset identity differs")
    require(runtime_hash(BASELINE_COMMIT) == BASELINE, "Historical runtime source differs")
    before, after = report["archive_before"], report["archive_after"]
    require(before == after and before["stats"]["cache_entries"] == 0, "Source/index/statistics changed during recall")
    require(set(report["reference_reports"]) == {"native", "component"}, "Reference stages differ")
    references = {}
    for stage, count, field in (("native", 1536, "payload_sha256"),
                                ("component", 768, "book_payload_sha256")):
        path = REFERENCE + "/candidate-" + stage + ".json.gz"
        raw = (ROOT / path).read_bytes()
        require(raw == git_bytes(SOURCE, path), "Historical raw report changed")
        old = references[stage] = json.loads(gzip.decompress(raw))
        metadata = old["metadata"]
        require(report["reference_reports"][stage] == {"path": path, "file_sha256": sha(raw),
                "calls": count, "runtime_sha256": BASELINE, "runtime_commit": BASELINE_COMMIT,
                "payload_field": field}, "Historical report identity differs")
        require(old["status"] == "completed" and old["validation"]["passed"] is True
                and old["dataset"]["sha256"] == dataset["fingerprint"]
                and old["dataset"]["provenance"]["selected_ids"] == ids
                and old["binding_sha256"] == sha(binding_raw)
                and old["cohort_manifest_sha256"] == sha(manifest_raw), "Historical matrix/cohort is incomplete")
        require(metadata.get("source_sha256_before", metadata.get("source_sha256"))
                == metadata["source_sha256_after"] == BASELINE
                and metadata["source_unchanged"] is True and metadata["originals_unchanged"] is True
                and metadata["source_provenance"]["git_commit"] == BASELINE_COMMIT
                and all(metadata[key] is False for key in ("semantic", "coverage", "project_local_fts_statistics")),
                "Historical runtime/settings differ")
        require(metadata["indexed_content_before"] == metadata["indexed_content_after"] == before["indexed_content"]
                and metadata["documents_sha256"] == before["documents_sha256"],
                "Historical/current source index or canonical documents differ")
    ledger_path = ROOT / (PREFIX + ".attempts.jsonl")
    zipped_path = ROOT / (PREFIX + ".attempts.jsonl.gz")
    ledger_raw = ledger_path.read_bytes() if ledger_path.exists() else gzip.decompress(zipped_path.read_bytes())
    require(sha(ledger_raw) == report["attempt_ledger_sha256"], "Original ledger hash differs")
    ledger = [json.loads(line) for line in ledger_raw.splitlines()]
    validate_rows(report, references, ledger, ids)
    zipped = lossless_gzip(ledger_raw)
    preflight_raw = (ROOT / PREFLIGHT).read_bytes()
    preflight = json.loads(gzip.decompress(preflight_raw))
    missing_path = binding["asset_verification"]["path"]
    require(preflight["status"] == "error" and preflight["error_type"] == "FileNotFoundError"
            and missing_path in preflight["error"] and preflight["rows"] == []
            and preflight["counts"] == {"native": {}, "component": {}}
            and preflight["candidate"] == report["candidate"]
            and preflight["helper_sha256"] == report["helper_sha256"]
            and datetime.fromisoformat(preflight["finished_at"]) < datetime.fromisoformat(report["started_at"]),
            "Initial zero-call preflight record differs")
    materialized = (ROOT / missing_path).read_bytes()
    require(sha(materialized) == binding["asset_verification"]["sha256"]
            and materialized == git_bytes(SOURCE, missing_path), "Recovered sparse input differs from frozen binding")
    summary = {key: value for key, value in report.items() if key != "rows"}
    summary.update(derived_from_report={"path": PREFIX + ".json.gz", "bytes": len(report_bytes),
        "sha256": sha(report_bytes), "uncompressed_sha256": sha(report_raw)},
        attempt_ledger={"path": PREFIX + ".attempts.jsonl.gz", "gzip_sha256": sha(zipped),
            "raw_sha256": sha(ledger_raw), "raw_bytes": len(ledger_raw), "gzip_bytes": len(zipped),
            "events": len(ledger), "starts": 2304, "finishes": 2304},
        saved_evidence_audit={"status": "passed", "rows_checked": 2304, "ledger_events_checked": 4608,
            "historical_raw_reports_checked": 2, "exact_payload_hashes_match": True,
            "complete_matrix_checked": True, "source_and_indexes_unchanged": True,
            "retrieval_calls_during_audit": 0, "timed_calls_during_audit": 0,
            "script": "scripts/" + Path(__file__).name, "script_sha256": sha(Path(__file__).read_bytes()),
            "boundary": "Rechecks saved hashes and events; does not reconstruct payload text, rerun retrieval, or provide new quality/latency evidence."},
        initial_preflight={"path": PREFLIGHT, "sha256": sha(preflight_raw), "bytes": len(preflight_raw),
            "status": "error", "error_type": "FileNotFoundError", "retrieval_calls": 0,
            "missing_path": missing_path, "materialized_sha256": sha(materialized),
            "resolution": "Materialized the existing frozen sparse-checkout input before the sole completed 2304-call comparison; preserved the failed zero-call preflight unchanged."})
    return summary, zipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate existing derived files without writes")
    args = parser.parse_args()
    summary, zipped = audited_archive()
    outputs = {PREFIX + ".attempts.jsonl.gz": zipped,
        PREFIX + ".summary.json": (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()}
    for name, raw in outputs.items():
        path = ROOT / name
        if args.check or path.exists():
            require(path.read_bytes() == raw, "Existing derived archive differs: " + name)
        else:
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    print(json.dumps({"status": "passed", "rows_checked": 2304, "ledger_events_checked": 4608,
                      "retrieval_calls_during_audit": 0, "check_only": args.check}))


if __name__ == "__main__":
    main()
