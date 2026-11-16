"""Reproducible, in-memory native v0.8.1 hotspot diagnostic.

Run from the repository root, without installing or downloading anything:
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=src:. \
    MEMORY_BOOK_TEXT_BACKEND=native python \
    benchmarks/reports/native-core/development/profile_native_core.py

cProfile measures instrumented elapsed time, not CPU utilization or an A/B
speedup. Self-time groups are disjoint; cumulative function times overlap.
Python-frame self time can include opaque native operations (notably JSON
encoding). The SQLite and existing C-helper shares cannot be removed merely by
translating their Python callers. This is development evidence, not a formal
performance acceptance measurement. No on-disk database is created.
"""
from __future__ import annotations

import argparse
import cProfile
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pstats
import sqlite3
import subprocess
import sys
import time
import unicodedata

from benchmarks.data import generate_dataset
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME, NATIVE


EXPECTED_COMMIT = "56eccd8c3a6f1d5637664607936da2595ce50c62"
DEFAULT_OUTPUT = Path(__file__).with_name("v0.8.1-synthetic61-native-profile.json.gz")
ROOT = Path.cwd().resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_hashes() -> dict[str, str]:
    paths = sorted(path for path in Path("src/memory_book").rglob("*")
                   if path.is_file() and path.suffix in {".py", ".c", ".h"})
    paths.extend([Path("pyproject.toml"), Path("setup.py")])
    return {path.as_posix(): sha256(path) for path in paths}


def commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def display_file(filename: str) -> str:
    if filename.startswith(str(ROOT) + "/"):
        return filename[len(str(ROOT)) + 1:]
    return filename


def category(filename: str, function: str) -> str:
    if filename == "~":
        if "sqlite3." in function:
            return "native_sqlite"
        if "memory_book._native." in function:
            return "native_text_extension"
        if "re.Pattern" in function or "re.Match" in function:
            return "native_regex"
        if "unicodedata." in function:
            return "native_unicode_database"
        if "'str' objects" in function:
            return "native_string_methods"
        if "math." in function:
            return "native_math"
        return "native_other_builtins"
    if filename.startswith("src/memory_book/"):
        return "python_project"
    if filename == display_file(__file__):
        return "python_diagnostic_driver"
    return "python_stdlib_and_dependencies"


def capture(label: str, function, work_items: int) -> dict:
    profile = cProfile.Profile()
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    profile.runcall(function)
    wall_seconds = time.perf_counter() - wall_start
    process_seconds = time.process_time() - cpu_start
    stats = pstats.Stats(profile)
    rows = []
    groups = {}
    modules = {}
    for (filename, line, name), values in sorted(stats.stats.items()):
        primitive, total, own, cumulative, callers = values
        filename = display_file(filename)
        group = category(filename, name)
        groups[group] = groups.get(group, 0.0) + own
        if group == "python_project":
            modules[filename] = modules.get(filename, 0.0) + own
        rows.append({
            "filename": filename, "line": line, "function": name,
            "primitive_calls": primitive, "total_calls": total,
            "calls_per_work_item": total / work_items,
            "self_seconds": own, "cumulative_seconds": cumulative,
            "self_pct": 100 * own / stats.total_tt,
            "cumulative_pct": 100 * cumulative / stats.total_tt,
            "exclusive_category": group,
            "callers": [
                {"filename": display_file(key[0]), "line": key[1],
                 "function": key[2], "primitive_calls": value[0],
                 "total_calls": value[1], "self_seconds": value[2],
                 "cumulative_seconds": value[3]}
                for key, value in sorted(callers.items())
            ],
        })
    def exclusive_summary(values):
        return [{"name": name, "self_seconds": seconds,
                 "self_pct": 100 * seconds / stats.total_tt}
                for name, seconds in sorted(values.items(), key=lambda pair: -pair[1])]
    return {
        "label": label, "work_items": work_items,
        "elapsed_wall_seconds": wall_seconds,
        "process_cpu_seconds": process_seconds,
        "profile_total_elapsed_seconds": stats.total_tt,
        "total_calls": stats.total_calls,
        "exclusive_categories": exclusive_summary(groups),
        "exclusive_project_modules": exclusive_summary(modules),
        "functions": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-commit", default=EXPECTED_COMMIT)
    parser.add_argument("--passes", type=int, default=3)
    args = parser.parse_args()
    if args.passes <= 0:
        parser.error("--passes must be positive")
    if args.output.exists():
        parser.error("refusing to overwrite existing diagnostic output")
    if BACKEND_NAME != "native" or NATIVE is None:
        raise RuntimeError("This diagnostic requires the actual native backend")
    before_commit, before = commit(), runtime_hashes()
    if before_commit != args.expected_commit:
        raise RuntimeError("HEAD differs from the requested baseline commit")
    native_path = Path(NATIVE.__file__)
    native_before = sha256(native_path)
    dataset = generate_dataset(seed=61, split="development", projects=8)
    if dataset.fingerprint != "117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26":
        raise RuntimeError("The registered synthetic61 dataset fingerprint changed")

    with MemoryBook(":memory:", cache_size=0) as book:
        def ingest():
            for session in dataset.sessions:
                book.ingest(session)

        def query(passes=1):
            for _ in range(passes):
                for case in dataset.queries:
                    book.recall(case.query, project=case.project,
                                budget_chars=2400, limit=5, use_cache=False)

        profiles = [capture("ingest-fresh", ingest, len(dataset.sessions)),
                    capture("ingest-unchanged", ingest, len(dataset.sessions))]
        query()  # One complete untimed warm-up; existing directory cache stays on.
        profiles.append(capture(f"recall-chars2400-{args.passes}-passes", lambda: query(args.passes),
                                args.passes * len(dataset.queries)))
        db_counts = {table: book.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                     for table in ("projects", "sessions", "turns", "sections", "pages")}

    after, after_commit = runtime_hashes(), commit()
    native_after = sha256(native_path)
    stable = before == after and native_before == native_after and before_commit == after_commit
    result = {
        "schema": "native-core-development-profile-v1",
        "purpose": "hotspot diagnosis only; no backend speed comparison",
        "commit_before": before_commit, "commit_after": after_commit,
        "source_and_binary_stable": stable,
        "runner_sha256": sha256(Path(__file__)),
        "runtime_hashes_before": before, "runtime_hashes_after": after,
        "native_binary": {"path": display_file(str(native_path)),
                          "sha256_before": native_before, "sha256_after": native_after},
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                        "unicode": unicodedata.unidata_version,
                        "hash_seed": os.environ.get("PYTHONHASHSEED"),
                        "backend": BACKEND_NAME},
        "workload": {"cohort": dataset.description(), "database": ":memory:",
                     "db_counts": db_counts, "max_page_chars": 900, "budget_chars": 2400,
                     "limit": 5, "cache_size": 0, "use_query_result_cache": False,
                     "warmup_query_passes": 1, "profiled_query_passes": args.passes,
                     "directory_token_cache": "unchanged production behavior",
                     "token_budget_profile": "not run: tokenizer dependency unavailable"
                     if importlib.util.find_spec("tiktoken") is None else
                     "not run: this diagnostic is scoped to the default character budget"},
        "limitations": [
            "Instrumented elapsed-time shares are not CPU utilization or formal speedups.",
            "Cumulative shares overlap and must not be added.",
            "Python-frame self time can include opaque C work, including JSON encoding.",
            "In-memory SQLite excludes disk, WAL, fsync, locks, and connection startup.",
            "Small fixed synthetic development cohort; no public-corpus or scale claim.",
            "No MCP, token-budget, semantic-model, or cold-start workload is profiled.",
        ],
        "profiles": profiles,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    args.output.write_bytes(gzip.compress(encoded, mtime=0))
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": sha256(args.output), "source_and_binary_stable": stable}))
    if not stable:
        raise RuntimeError("Source, binary or HEAD changed during the profile; retain as invalid diagnostic")


if __name__ == "__main__":
    main()
