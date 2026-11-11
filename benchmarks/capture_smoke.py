"""Measure initial capture, unchanged polls, and one changed transcript.

Run from a source checkout after installation, or with PYTHONPATH=src:
    python benchmarks/capture_smoke.py

This measures sync_once wall time on synthetic local files. It does not measure
a resident service's CPU/memory use, client latency, or operating-system-cold I/O.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
import random
import sqlite3
import statistics
from pathlib import Path
import tempfile
import time

from memory_book import MemoryBook, __version__
from memory_book.sync import SyncConfig, WatchSource, sync_once


ROOT = Path(__file__).resolve().parents[1]
COUNTERS = ("scanned", "imported", "updated_sessions", "skipped", "partial", "deferred", "errors", "ignored", "missing")


def fixture(index: int, rng: random.Random) -> dict:
    component = rng.choice(("search", "cache", "export", "sync", "reader", "index"))
    delay = rng.randrange(10, 91)
    return {
        "project": f"capture-demo-{index % 3}",
        "session_id": f"synthetic-session-{index:04d}",
        "title": f"Synthetic {component} discussion {index:04d}",
        "task_id": f"topic-{index % 10}",
        "task_title": f"Synthetic task {index % 10}",
        "created_at": "2026-11-01T00:00:00+00:00",
        "messages": [
            {"role": "user", "content": f"Which retry interval should the {component} component use?"},
            {"role": "assistant", "content": f"For this fictional session, use {delay} seconds between retries. Keep the previous local result available during a network interruption. This is synthetic benchmark data, not a production recommendation."},
            {"role": "user", "content": "发生冲突时如何保留原始记录？"},
            {"role": "assistant", "content": "演示约定：保留原始会话和两个修改版本，记录来源与时间，之后再确认合并结果。这个文本只用于本地捕获性能测量。"},
        ],
    }


def write_fixture(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def cycle(config: SyncConfig) -> dict:
    started = time.perf_counter_ns()
    result = sync_once(config)
    wall_ms = (time.perf_counter_ns() - started) / 1_000_000
    if result["errors"] or result["deferred"] or result["partial"]:
        raise RuntimeError(f"Unexpected capture result: {result}")
    return {
        "wall_elapsed_ms": wall_ms,
        "elapsed_ms": result["elapsed_ms"],
        "database_rebound": result["database_rebound"],
        **{name: result[name] for name in COUNTERS},
    }


def implementation_hash() -> str:
    digest = hashlib.sha256()
    for name in ("sync.py", "store.py", "importers.py", "segmentation.py", "text.py"):
        path = ROOT / "src" / "memory_book" / name
        digest.update(name.encode("ascii") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def measure(sessions: int = 300, idle_cycles: int = 8, seed: int = 20261111) -> dict:
    if not 1 <= sessions <= 10_000 or not 5 <= idle_cycles <= 10:
        raise ValueError("Use 1–10000 sessions and 5–10 idle cycles.")
    started = time.perf_counter_ns()
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="capture-smoke-", dir=ROOT) as temporary:
        work = Path(temporary)
        source = work / "transcripts"
        source.mkdir()
        paths = []
        for index in range(sessions):
            path = source / f"session-{index:04d}.json"
            write_fixture(path, fixture(index, rng))
            paths.append(path)
        initial_bytes = sum(path.stat().st_size for path in paths)
        config = SyncConfig(
            database=work / "book.sqlite3",
            state_path=work / "state.json",
            log_path=work / "worker.jsonl",
            poll_interval=1.0,
            sources=(WatchSource("synthetic", source, "canonical"),),
        )
        initial = cycle(config)
        assert initial["scanned"] == sessions
        assert initial["imported"] == initial["updated_sessions"] == sessions
        idle = [cycle(config) for _ in range(idle_cycles)]
        for result in idle:
            assert result["scanned"] == result["skipped"] == sessions
            assert result["imported"] == result["updated_sessions"] == 0

        changed_path = paths[seed % sessions]
        changed = json.loads(changed_path.read_text(encoding="utf-8"))
        changed["messages"].extend([
            {"role": "user", "content": "Record one follow-up for the incremental capture measurement."},
            {"role": "assistant", "content": "Only this synthetic transcript changed; retain the same project and session identity."},
        ])
        write_fixture(changed_path, changed)
        update = cycle(config)
        assert update["scanned"] == sessions
        assert update["imported"] == update["updated_sessions"] == 1
        assert update["skipped"] == sessions - 1
        settled = cycle(config)
        assert settled["skipped"] == sessions and settled["updated_sessions"] == settled["imported"] == 0
        final_bytes = sum(path.stat().st_size for path in paths)
        with MemoryBook(config.database) as book:
            stats = book.stats()
            assert stats["sessions"] == sessions
        idle_times = sorted(item["wall_elapsed_ms"] for item in idle)
        result = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project_version": __version__,
            "implementation_sha256": implementation_hash(),
            "environment": {
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
            "fixture": {
                "kind": "synthetic canonical JSON conversations",
                "seed": seed,
                "sessions": sessions,
                "projects": stats["projects"],
                "idle_cycles": idle_cycles,
                "source_bytes_initial": initial_bytes,
                "source_bytes_after_update": final_bytes,
                "largest_source_file_bytes": max(path.stat().st_size for path in paths),
                "changed_files": 1,
                "changed_session_id": changed["session_id"],
            },
            "initial_capture": initial,
            "unchanged_cycles": idle,
            "unchanged_wall_ms": {
                "min": min(idle_times),
                "median": statistics.median(idle_times),
                "p95_nearest_rank": idle_times[math.ceil(0.95 * len(idle_times)) - 1],
                "max": max(idle_times),
            },
            "single_file_update": update,
            "unchanged_after_update": settled,
            "final_counts": stats,
            "storage_file_bytes": {
                "database": config.database.stat().st_size,
                "state_manifest": config.state_path.stat().st_size,
                "event_log": config.log_path.stat().st_size,
            },
            "measurement_wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "scope": [
                "Initial capture uses a new database in the same Python process; OS caches are not flushed.",
                "Idle cycles run consecutively without the worker's normal polling sleep, so filesystem caches are warm.",
                "wall_elapsed_ms includes the sync_once lock and state load; elapsed_ms is the core's returned cycle measurement.",
                "Source byte counts and storage_file_bytes describe file sizes, not measured disk I/O volume.",
                "The state manifest and heartbeat are still updated on idle cycles; zero imported sessions does not mean zero disk writes.",
                "This smoke measurement does not quantify resident-service CPU, RAM, battery impact, client latency, or performance at other scales or on other machines.",
            ],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=300)
    parser.add_argument("--idle-cycles", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "reports" / "capture-v0.2.0.json")
    arguments = parser.parse_args()
    report = measure(arguments.sessions, arguments.idle_cycles, arguments.seed)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(arguments.output),
        "sessions": report["fixture"]["sessions"],
        "source_bytes": report["fixture"]["source_bytes_initial"],
        "initial_wall_ms": report["initial_capture"]["wall_elapsed_ms"],
        "idle_wall_ms": report["unchanged_wall_ms"],
        "single_update_wall_ms": report["single_file_update"]["wall_elapsed_ms"],
        "single_update_sessions": report["single_file_update"]["updated_sessions"],
        "measurement_wall_ms": report["measurement_wall_ms"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
