"""Development diagnostic for revision crowding, not a held-out benchmark.

Run from the repository with PYTHONPATH=src. Output retains all individual
measurements and exact returned evidence. No external system is evaluated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME


def record(identity: str, text: str, date: str) -> dict:
    return {"project": "workers", "session_id": identity, "task_id": "queue",
            "task_title": "Worker configuration", "title": "Worker configuration",
            "created_at": date, "messages": [{"role": "assistant", "content": text}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to replace an earlier observation")
    observations = []
    for old_count in (4, 100, 1000):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(old_count):
                book.ingest(record(f"old-{index}", "retry_limit=3. " + "retry_limit. " * 12,
                                   f"2026-01-{index % 28 + 1:02}T00:00:00Z"))
            book.ingest(record("new", "retry_limit=7. The short accepted revision replaces the original configuration.",
                               "2026-06-01T00:00:00Z"))
            for mode in ("relevance", "current"):
                for limit in (1, 5):
                    for repeat in range(3):
                        started = time.perf_counter_ns()
                        result = book.recall("retry_limit", project="workers", temporal=mode,
                                             limit=limit, use_cache=False)
                        elapsed = time.perf_counter_ns() - started
                        observations.append({"old_count": old_count, "mode": mode, "limit": limit,
                                             "repeat": repeat, "wall_ns": elapsed,
                                             "first_session": result["results"][0]["source_refs"][0]["session_id"],
                                             "new_present": "retry_limit=7" in result["context"],
                                             "result": result})
    source = Path("src/memory_book/store.py").read_bytes()
    result = {"scope": "authored development diagnostic; no external baselines or independent test set",
              "label": args.label, "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "store_sha256": hashlib.sha256(source).hexdigest(),
              "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "python": platform.python_version(), "platform": platform.platform(),
              "backend": BACKEND_NAME, "observations": observations}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "observations": len(observations),
                      "current_new_present": sum(row["new_present"] for row in observations if row["mode"] == "current"),
                      "current_observations": sum(row["mode"] == "current" for row in observations)}))


if __name__ == "__main__":
    main()
