"""Adversarial review: a mention must not move a field across environments.

These examples were authored after inspecting candidate3. They diagnose the
association of query facets with a declaration, not aggregate retrieval
quality, speed, or holdout performance. Retain all failed attempts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def fixtures(count):
    sessions = []
    for index in range(count):
        sessions.append({
            "project": "workers", "task_id": "queue", "task_title": "Worker configuration",
            "session_id": f"old-{index}", "title": "Worker configuration",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content":
                          "Production lease_duration=30. " + "production lease_duration. " * 12}],
        })
    sessions.append({
        "project": "workers", "task_id": "queue", "task_title": "Worker configuration",
        "session_id": "latest-staging", "title": "Worker configuration",
        "created_at": "2026-10-01T00:00:00Z",
        "messages": [{"role": "assistant", "content":
                      "Staging lease_duration=99. The production review remains open. "
                      + "A separate administrative scheduling note follows. " * 100}],
    })
    return sessions


def worker(count):
    import memory_book
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME
    package = Path(memory_book.__file__).resolve().parent
    sources = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(package.iterdir())
               if path.is_file() and path.suffix in {".py", ".c", ".h"}}
    sessions = fixtures(count)
    request = {"query": "current production lease_duration", "project": "workers",
               "limit": 1, "budget_chars": 2400, "use_cache": False}
    with MemoryBook(":memory:", segmentation="turn") as book:
        for source in sessions:
            book.ingest(source)
        response = book.recall(**request)
        followups = [book.read(item["id"], project="workers", limit=100000)
                     for item in response["results"]]
    return {
        "old_session_count": count,
        "scope": "Authored adversarial facet-association diagnosis; no product or speed score",
        "runtime": {"path": str(package), "version": memory_book.__version__,
                    "backend": BACKEND_NAME, "source_files_sha256": sources},
        "configuration": {"database": ":memory:", "segmentation": "turn"},
        "request": request, "sessions": sessions,
        "response": response, "full_selected_page_reads": followups,
        "selected_source_sessions": sorted({ref["session_id"] for item in response["results"]
                                            for ref in item["source_refs"]}),
        "production_decision_retained": "Production lease_duration=30." in response["context"],
        "unrelated_staging_assignment_selected": "Staging lease_duration=99." in response["context"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=int)
    parser.add_argument("--baseline-path", type=Path)
    parser.add_argument("--candidate-path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(worker(args.worker), ensure_ascii=False, allow_nan=False))
        return 0
    if not all((args.baseline_path, args.candidate_path, args.output)):
        parser.error("baseline-path, candidate-path and a new output path are required")
    args.output.mkdir(parents=True, exist_ok=False)
    observations = []
    for count in (8, 104):
        for arm, source in (("baseline", args.baseline_path), ("candidate", args.candidate_path)):
            environment = dict(os.environ, PYTHONPATH=str(source.resolve()))
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(count)],
                                       env=environment, text=True, capture_output=True, check=False)
            name = f"{arm}-{count}"
            (args.output / f"{name}.stderr.log").write_text(completed.stderr, encoding="utf-8")
            (args.output / f"{name}.raw.json").write_text(completed.stdout, encoding="utf-8")
            record = {"arm": arm, "old_session_count": count, "exit_code": completed.returncode,
                      "raw_path": f"{name}.raw.json",
                      "raw_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest()}
            if completed.returncode == 0:
                raw = json.loads(completed.stdout)
                record.update({key: raw[key] for key in (
                    "selected_source_sessions", "production_decision_retained",
                    "unrelated_staging_assignment_selected")})
                record["candidate_expansion"] = raw["response"].get("temporal", {}).get("candidate_expansion")
            observations.append(record)
    report = {
        "schema": "facet-association-review-v1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "Authored adversarial code-review reproduction after implementation; not a holdout",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "interpretation": "Production is a query qualifier. The latest complete turn assigns only a staging value and mentions production in a separate sentence without a new production decision. The 8-record case tests the original FTS tail; the 104-record case exceeds the 96-row exact route cap.",
        "observations": observations,
    }
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["exit_code"] == 0 for item in observations) else 1


if __name__ == "__main__":
    raise SystemExit(main())
