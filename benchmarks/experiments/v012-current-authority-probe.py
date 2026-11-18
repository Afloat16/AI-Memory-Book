"""Replay the eight frozen current-ordering counterexamples and controls.

This is an authored development probe, not independent answer-accuracy evidence.
The same original records run in relevance and current mode. Every attempt gets
a fresh directory, raw responses, complete page reads and loaded source hashes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


CASES = (
    ("cross_sentence_scope", "current production lease_duration",
     "Production lease_duration=30. " + "production lease_duration. " * 12,
     "Staging lease_duration=99. The production review remains open.", "old"),
    ("agenda_word_value", "current retry limit",
     "The retry limit is three attempts. " + "retry limit. " * 10,
     "The retry limit remains on tomorrow's review agenda. No decision has been made.", "old"),
    ("agenda_numeric_value", "current retry limit",
     "Retry limit is 3. " + "retry limit. " * 10,
     "Retry limit remains on the agenda. No decision has been made.", "old"),
    ("matching_scope_revision", "current production lease_duration",
     "Production lease_duration=30. " + "production lease_duration. " * 12,
     "Production lease_duration=12.", "recent"),
    ("pure_prose_revision", "current worker prefetch window",
     "Worker prefetch window is 12. " + "worker prefetch window. " * 12,
     "Worker prefetch window is 3.", "recent"),
    ("pure_word_revision", "current retry limit",
     "The retry limit is three attempts. " + "retry limit. " * 12,
     "The retry limit is seven attempts.", "recent"),
    ("chinese_revision", "当前梯度累积步数",
     "梯度累积步数设为8。" + "梯度累积步数。" * 12,
     "梯度累积步数改为2。", "recent"),
    ("scope_suffix", "current production lease_duration",
     "Production lease_duration=30. " + "production lease_duration. " * 12,
     "Production lease_duration=99 for staging.", "old"),
)


def record(sid, text, date, project="workers"):
    return {"project": project, "task_id": "queue", "task_title": "Worker configuration",
            "session_id": sid, "title": "Worker configuration", "created_at": date,
            "messages": [{"role": "assistant", "content": text}]}


def run(output):
    import memory_book
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME

    root = Path(__file__).resolve().parents[2]
    package = Path(memory_book.__file__).resolve().parent
    output.mkdir(parents=True, exist_ok=False)

    def source_identity():
        return {"src/memory_book/" + p.relative_to(package).as_posix():
                hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(package.rglob("*"))
                if p.is_file() and p.suffix in {".py", ".c", ".h"}}

    identity = source_identity()
    report = {"status": "started", "protocol": "v012-current-authority-v1",
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "package_path": str(package), "runtime_files_sha256": identity,
              "runtime_sha256": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
              "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "backend": BACKEND_NAME, "python": sys.version,
              "scope": "Authored development counterexamples and positive controls, not independent answer-accuracy validation. Expected sessions apply only to current mode. Relevance records are regression controls."}

    def save():
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    rows = []
    try:
        with (output / "responses.jsonl").open("x", encoding="utf-8") as stream:
            for label, query, old, recent, expected in CASES:
                sessions = [record("old", old, "2026-01-01T00:00:00Z"),
                            record("recent", recent, "2026-10-01T00:00:00Z"),
                            record("recent", recent.replace("12", "999").replace("3", "999"),
                                   "2026-11-01T00:00:00Z", "workers-copy")]
                with MemoryBook(":memory:", cache_size=0, segmentation="turn") as book:
                    for session in sessions:
                        book.ingest(session)
                    for mode in ("relevance", "current"):
                        request = {"query": query, "project": "workers", "temporal": mode,
                                   "limit": 1, "budget_chars": 1200, "use_cache": False}
                        response = book.recall(**request)
                        row = {"case": label, "mode": mode, "sessions": sessions, "request": request,
                               "expected_current_session": expected, "response": response,
                               "full_page_reads": [book.read(hit["id"], limit=100000, project="workers")
                                                   for hit in response["results"]]}
                        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                        stream.flush()
                        rows.append(row)
        report.update(status="completed", responses=len(rows), runtime_unchanged=identity == source_identity(),
                      response_sha256=hashlib.sha256((output / "responses.jsonl").read_bytes()).hexdigest(),
                      current_observations=[{
                          "case": row["case"],
                          "selected_sessions": [hit["source_refs"][0]["session_id"] for hit in row["response"]["results"]],
                          "expected_session": row["expected_current_session"],
                          "matches_expected": bool(row["response"]["results"]) and
                          all(hit["source_refs"][0]["session_id"] == row["expected_current_session"]
                              for hit in row["response"]["results"]),
                      } for row in rows if row["mode"] == "current"])
        if not report["runtime_unchanged"]:
            raise ValueError("Loaded source changed during the probe")
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({key: result[key] for key in ("status", "responses", "current_observations")}, indent=2))
