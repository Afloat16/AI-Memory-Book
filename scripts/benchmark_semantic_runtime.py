#!/usr/bin/env python3
"""Development measurements of semantic vector memory and verified artifact I/O.

Uses deterministic vectors and fake ONNX/tokenizer runtimes. It does not measure
semantic quality, actual model inference, or a complete recall request. Baseline
code comes from the exact recorded Git commit; every observation is retained.
"""

from __future__ import annotations

import argparse
import builtins
from contextlib import ExitStack, contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REF = "238c8058f723a203eaca99f94d924ab77de4c0b3"
SOURCE_PATH = "src/memory_book/semantic.py"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def modules():
    baseline = git("show", f"{BASELINE_REF}:{SOURCE_PATH}")
    candidate = (ROOT / SOURCE_PATH).read_bytes()
    result = {}
    provenance = {}
    for arm, source in (("baseline", baseline), ("candidate", candidate)):
        name = f"_semantic_runtime_{arm}"
        module = ModuleType(name)
        module.__file__ = f"{BASELINE_REF}:{SOURCE_PATH}" if arm == "baseline" else str(ROOT / SOURCE_PATH)
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        result[arm] = module
        provenance[arm] = {"source_sha256": hashlib.sha256(source).hexdigest()}
    provenance["baseline"].update(commit=BASELINE_REF,
                                  blob=git("rev-parse", f"{BASELINE_REF}:{SOURCE_PATH}").decode().strip())
    provenance["candidate"].update(head=git("rev-parse", "HEAD").decode().strip(),
                                   source_status=git("status", "--porcelain", "--", SOURCE_PATH).decode().strip())
    return result, provenance


def fixture(np, dimensions, windows):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE pages (id TEXT PRIMARY KEY, rid INTEGER, project_id TEXT,
                            chapter_id TEXT, session_pk TEXT);
        CREATE TABLE chapters (id TEXT PRIMARY KEY, title TEXT);
        CREATE TABLE sessions (id TEXT PRIMARY KEY, external_id TEXT, title TEXT, created_at TEXT);
        CREATE TABLE semantic_vectors (page_id TEXT, ordinal INTEGER, vector BLOB,
                                       PRIMARY KEY(page_id,ordinal));
    """)
    db.executemany("INSERT INTO chapters VALUES(?,?)", ((f"c-{n}", f"Chapter {n}") for n in range(4)))
    db.executemany("INSERT INTO sessions VALUES(?,?,?,?)",
                   ((f"s-{n}", f"external-{n}", f"Session {n}", "2026-01-01") for n in range(8)))
    patterns = []
    for number in range(64):
        vector = np.zeros(dimensions, dtype="<f4")
        for axis in range(8):
            vector[axis] = ((number * (axis * 3 + 1) % 31) - 15) / 16
        patterns.append(np.asarray(vector / np.linalg.norm(vector), dtype="<f4"))
    blobs = [vector.tobytes() for vector in patterns]
    source_hash = hashlib.sha256()
    db.execute("BEGIN")
    for number in range(windows):
        page, ordinal = divmod(number, 4)
        page_id = f"page-{page:08d}"
        if ordinal == 0:
            values = (page_id, page, f"project-{page % 2}", f"c-{page % 4}", f"s-{page % 8}")
            db.execute("INSERT INTO pages VALUES(?,?,?,?,?)", values)
            source_hash.update(canonical(values).encode())
        blob = blobs[(page * 5 + ordinal) % len(blobs)]
        db.execute("INSERT INTO semantic_vectors VALUES(?,?,?)", (page_id, ordinal, blob))
        source_hash.update(canonical((page_id, ordinal)).encode())
        source_hash.update(blob)
    db.execute("COMMIT")
    queries = np.asarray([patterns[3], patterns[47]], dtype="<f4")
    model = SimpleNamespace(np=np, encode_query=lambda query: queries)
    metadata = {"windows": windows, "pages": (windows + 3) // 4, "dimensions": dimensions,
                "windows_per_page": 4, "query_windows": 2, "vector_payload_bytes": windows * dimensions * 4,
                "fixture_sha256": source_hash.hexdigest(),
                "query_vectors_sha256": hashlib.sha256(queries.tobytes()).hexdigest(),
                "sqlite_storage": "in-memory", "scope": "all fixture pages"}
    return db, model, metadata


def ordered_pairs(count):
    for pair in range(count):
        yield pair, ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")


def summary(observations, field):
    medians = {arm: statistics.median(row[field] for row in observations if row["arm"] == arm)
               for arm in ("baseline", "candidate")}
    ratios = []
    for pair in sorted({row["pair"] for row in observations}):
        values = {row["arm"]: row[field] for row in observations if row["pair"] == pair}
        ratios.append(values["candidate"] / values["baseline"])
    return {f"median_{field}": medians, "candidate_over_baseline_pair_ratios": ratios,
            "median_candidate_over_baseline": statistics.median(ratios)}


def ranking_case(np, engines, windows, args):
    db, model, metadata = fixture(np, engines["baseline"].DIMENSIONS, windows)
    observations = []
    allocations = []
    try:
        calls = {arm: (lambda engine=engine: engine.rank_pages(db, model, "fixture", "", []))
                 for arm, engine in engines.items()}
        expected = calls["baseline"]()
        if calls["candidate"]() != expected:
            raise AssertionError("Untimed candidate ranking differs from the frozen baseline")
        result_hash = digest(expected)
        for _ in range(args.warmups):
            for call in calls.values():
                if call() != expected:
                    raise AssertionError("Warmup ranking changed")
        for pair, order in ordered_pairs(args.pairs):
            for position, arm in enumerate(order):
                gc.collect()
                started = time.perf_counter_ns()
                cpu_started = time.process_time_ns()
                result = calls[arm]()
                cpu_elapsed = time.process_time_ns() - cpu_started
                elapsed = time.perf_counter_ns() - started
                if result != expected:
                    raise AssertionError("Timed ranking differs; validation runs outside the timer")
                observations.append({"pair": pair, "position": position, "arm": arm, "elapsed_ns": elapsed,
                                     "process_cpu_ns": cpu_elapsed,
                                     "output_sha256": result_hash})
                del result
        # Allocation measurements never contribute to the latency summary.
        for pair, order in ordered_pairs(args.memory_pairs):
            for position, arm in enumerate(order):
                gc.collect()
                tracemalloc.start()
                try:
                    result = calls[arm]()
                    retained, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                if result != expected:
                    raise AssertionError("Allocation ranking differs from the baseline")
                allocations.append({"pair": pair, "position": position, "arm": arm,
                                    "peak_python_bytes": peak, "retained_python_bytes": retained,
                                    "output_sha256": result_hash})
                del result
        return {"fixture": metadata, "validation": {"exact_equal": True, "output_sha256": result_hash,
                                                      "returned_pages": len(expected)},
                "latency": {"observations": observations, **summary(observations, "elapsed_ns"),
                            "process_cpu": summary(observations, "process_cpu_ns")},
                "allocations": {"observations": allocations, **summary(allocations, "peak_python_bytes")}}
    finally:
        db.close()


@contextmanager
def fake_runtimes():
    """No inference or optional runtime dependency is included in artifact timing."""
    captured = {}
    tokenizer = SimpleNamespace(no_padding=lambda: None, enable_truncation=lambda **kw: None,
                                token_to_id=lambda name: 0)
    def from_str(text):
        captured["tokenizer"] = text
        return tokenizer
    def session(blob, **kwargs):
        captured["model"] = blob
        return SimpleNamespace(get_inputs=lambda: [SimpleNamespace(name="input_ids"),
                                                    SimpleNamespace(name="attention_mask")])
    ort = SimpleNamespace(disable_telemetry_events=lambda: None, SessionOptions=SimpleNamespace,
                          InferenceSession=session)
    original_import = builtins.__import__
    def importing(name, *args, **kwargs):
        if name == "numpy":
            return SimpleNamespace()
        if name == "onnxruntime":
            if os.environ.get("ORT_DISABLE_TELEMETRY") != "1":
                raise AssertionError("Runtime imported before telemetry opt-out")
            return ort
        if name == "tokenizers":
            return SimpleNamespace(Tokenizer=SimpleNamespace(from_str=from_str))
        return original_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=importing), patch.dict(os.environ):
        yield captured


@contextmanager
def io_counts(paths):
    """Untimed read/hash byte counts; identity hashing is reported separately."""
    counts = {"read_bytes": 0, "hash_bytes": 0}
    original_open, original_sha = Path.open, hashlib.sha256
    class Stream:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.handle.__exit__(*args)
        def __getattr__(self, name):
            return getattr(self.handle, name)
        def read(self, size=-1):
            block = self.handle.read(size)
            counts["read_bytes"] += len(block)
            return block
    class Hash:
        def __init__(self, data=b"", **kwargs):
            counts["hash_bytes"] += len(data)
            self.wrapped = original_sha(data, **kwargs)
        def __getattr__(self, name):
            return getattr(self.wrapped, name)
        def update(self, data):
            counts["hash_bytes"] += len(data)
            return self.wrapped.update(data)
    def opening(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return Stream(handle) if path in paths else handle
    with patch.object(Path, "open", opening), patch.object(hashlib, "sha256", Hash):
        yield counts


def artifact_case(engines, args):
    with tempfile.TemporaryDirectory(prefix="semantic-runtime-") as directory:
        root = Path(directory)
        contents = {"fixture.onnx": b"m" * args.model_bytes,
                    "tokenizer.json": b"{}" + b" " * (args.tokenizer_bytes - 2)}
        files = []
        for name, blob in contents.items():
            (root / name).write_bytes(blob)
            files.append({"path": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()})
        total_bytes = sum(map(len, contents.values()))
        observations, validations = [], {}
        with ExitStack() as stack:
            for engine in engines.values():
                stack.enter_context(patch.object(engine, "MODEL_FILES", files))
            stack.enter_context(patch.object(engines["baseline"].importlib.metadata, "version", return_value="fixture"))
            captured = stack.enter_context(fake_runtimes())
            calls = {arm: (lambda engine=engine: engine.SemanticModel(root)) for arm, engine in engines.items()}
            identity = engines["baseline"].verify_model_files(root)
            fingerprint = hashlib.sha256(canonical(identity).encode()).hexdigest()
            def validate(model):
                if model.identity != identity or model.fingerprint != fingerprint:
                    raise AssertionError("Model identity/fingerprint changed")
                if captured["model"] != contents["fixture.onnx"] or captured["tokenizer"] != contents["tokenizer.json"].decode():
                    raise AssertionError("Runtime did not consume the verified artifact bytes")
            for arm, call in calls.items():
                with io_counts({root / name for name in contents}) as counts:
                    model = call()
                validate(model)
                counts["artifact_hash_bytes"] = counts["hash_bytes"] - len(canonical(identity).encode())
                validations[arm] = dict(counts, identity_equal=True, fingerprint_equal=True, bytes_equal=True)
                expected_bytes = total_bytes * (2 if arm == "baseline" else 1)
                if counts["read_bytes"] != expected_bytes or counts["artifact_hash_bytes"] != expected_bytes:
                    raise AssertionError(f"Unexpected verified artifact work for {arm}: {counts}")
                captured.clear()
                del model
            for _ in range(args.warmups):
                for call in calls.values():
                    model = call()
                    validate(model)
                    captured.clear()
                    del model
            for pair, order in ordered_pairs(args.artifact_pairs):
                for position, arm in enumerate(order):
                    gc.collect()
                    started = time.perf_counter_ns()
                    cpu_started = time.process_time_ns()
                    model = calls[arm]()
                    cpu_elapsed = time.process_time_ns() - cpu_started
                    elapsed = time.perf_counter_ns() - started
                    validate(model)
                    observations.append({"pair": pair, "position": position, "arm": arm,
                                         "elapsed_ns": elapsed, "process_cpu_ns": cpu_elapsed,
                                         "model_fingerprint": model.fingerprint})
                    captured.clear()
                    del model
        return {"fixture": {"files": files, "total_artifact_bytes": total_bytes,
                            "runtimes": "fake; no ONNX loading, inference, or tokenizer parsing",
                            "cache_state": "warm filesystem cache after validation and warmups"},
                "validation": validations, "latency": {"observations": observations,
                                                           **summary(observations, "elapsed_ns"),
                                                           "process_cpu": summary(observations, "process_cpu_ns")}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--windows", type=int, nargs="+", default=[4096, 32768])
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--memory-pairs", type=int, default=2)
    parser.add_argument("--artifact-pairs", type=int, default=8)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--model-bytes", type=int, default=118453870)
    parser.add_argument("--tokenizer-bytes", type=int, default=9081518)
    args = parser.parse_args(argv)
    if any(n <= 0 for n in [*args.windows, args.pairs, args.memory_pairs, args.artifact_pairs, args.model_bytes]) or args.tokenizer_bytes < 2 or args.warmups < 0:
        parser.error("Sizes and pair counts must be positive; tokenizer bytes >= 2 and warmups >= 0")
    if any(n % 2 for n in (args.pairs, args.memory_pairs, args.artifact_pairs)):
        parser.error("Use even pair counts so each arm runs first equally often")
    import numpy as np
    engines, provenance = modules()
    plan = ROOT / "benchmarks/semantic-runtime-plan.json"
    report = {"protocol": "semantic-runtime-development-v2", "evidence_label": "development",
              "scope": "Component memory and verified artifact I/O; no retrieval-quality or end-to-end claim",
              "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "baseline_ref": BASELINE_REF, "sources": provenance,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
              "environment": {"python": platform.python_version(), "executable": sys.executable,
                              "numpy": np.__version__, "sqlite": sqlite3.sqlite_version,
                              "platform": platform.platform(), "cpu_count": os.cpu_count()},
              "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
              "ranking": [ranking_case(np, engines, count, args) for count in args.windows],
              "artifact_initialization": artifact_case(engines, args)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(canonical({"report": str(args.output), "ranking": [
        {"windows": case["fixture"]["windows"], "latency_ratio": case["latency"]["median_candidate_over_baseline"],
         "process_cpu_ratio": case["latency"]["process_cpu"]["median_candidate_over_baseline"],
         "python_peak_ratio": case["allocations"]["median_candidate_over_baseline"]} for case in report["ranking"]],
        "artifact_initialization_ratio": report["artifact_initialization"]["latency"]["median_candidate_over_baseline"]}))


if __name__ == "__main__":
    main()
