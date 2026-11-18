"""Candidate3 qualification work on authored review regressions.

This records extra passes, independent source checks, and three uninstrumented
wall timings per case. It is a code-review diagnostic, not a holdout, a speed
benchmark, or a comparison with external memory products. Existing output is
never replaced. The damaged-source case intentionally corrupts stored turns.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import platform
import runpy
import time
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
import memory_book.store as store


def cases():
    directory = Path(__file__).parent
    agenda = runpy.run_path(str(directory / "v011-unclassified-proposal-review.py"))["fixtures"]
    record = runpy.run_path(str(directory / "v011-current-route-probe.py"))["record"]
    for count in (8, 120):
        yield f"agenda-{count}", agenda(count), {
            "query": "What is the current retry limit?", "project": "alpha", "limit": 1}, False
    for with_prose in (False, True):
        sessions = [record(f"old-{i}", "Retry limit is 3. " + "retry limit. " * 20,
                           "2026-01-01T00:00:00Z") for i in range(8)]
        if with_prose:
            sessions.append(record("prose-update", "Retry limit is now 7. "
                                   + "Administrative scheduling discussion. " * 60,
                                   "2026-06-01T00:00:00Z"))
        else:
            sessions.append(record("review", "Reviewed retry limit during maintenance. "
                                   + "retry limit. " * 20, "2026-03-01T00:00:00Z"))
        sessions.append(record("example", "Example: retry_limit=999. "
                               + "Administrative scheduling discussion. " * 100,
                               "2026-10-01T00:00:00Z"))
        yield ("cascade-rejected-spelling" if with_prose else "rejected-field-example"), sessions, {
            "query": "current retry limit", "project": "workers", "limit": 1}, False
    for damaged in (False, True):
        sessions = [record(f"old-{i}", "retry_limit=3. " + "retry_limit. " * 12,
                           "2026-01-01T00:00:00Z") for i in range(104)]
        sessions.append(record("accepted", "retry_limit=7. A deliberately concise revision.",
                               "2026-06-01T00:00:00Z"))
        if damaged:
            sessions.append(record("damaged-source", "retry_limit=7. A deliberately concise revision.",
                                   "2026-10-01T00:00:00Z"))
        yield ("damaged-identical-source" if damaged else "comparable-assignment"), sessions, {
            "query": "current retry_limit", "project": "workers", "limit": 5}, damaged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to replace an earlier observation")
    observations = []
    for name, sessions, request, damaged in cases():
        with MemoryBook(":memory:", segmentation="turn") as book:
            for session in sessions:
                book.ingest(session)
            corruption = None
            if damaged:
                corruption = {"session_id": "damaged-source", "table": "turns",
                              "replacement": ["retry_limit=7", "retry_limit=8"],
                              "purpose": "Artificial source-authentication fault; not normal ingestion"}
                book.db.execute("UPDATE turns SET content=replace(content,'retry_limit=7','retry_limit=8') "
                                "WHERE session_pk IN (SELECT id FROM sessions WHERE external_id='damaged-source')")
                book.db.commit()
            request = {**request, "use_cache": False, "budget_chars": 2400}
            timings = []
            for _ in range(3):
                start = time.perf_counter_ns()
                response = book.recall(**request)
                timings.append({"wall_ns": time.perf_counter_ns() - start, "response": response})
            counts = {"application_selects": 0, "internal_sql_statements": 0,
                      "source_authentication_calls": 0, "source_pages_checked": 0,
                      "source_pages_certified": 0}
            checked, certified_ids = set(), set()

            def trace(statement):
                text = statement.lstrip().upper()
                if text.startswith(("SELECT", "WITH")):
                    counts["application_selects"] += 1
                elif text.startswith("--"):
                    counts["internal_sql_statements"] += 1

            authenticate = store._complete_declaration_pages

            def source_check(db, contents, references):
                counts["source_authentication_calls"] += 1
                counts["source_pages_checked"] += len(contents)
                checked.update(contents)
                certified = authenticate(db, contents, references)
                counts["source_pages_certified"] += len(certified)
                certified_ids.update(certified)
                return certified

            with ExitStack() as stack:
                parsers = {name: stack.enter_context(patch.object(store, name, wraps=getattr(store, name)))
                           for name in ("_declaration_clauses", "_quoted_spans", "_field_identity")}
                stack.enter_context(patch.object(store, "_complete_declaration_pages", source_check))
                book.db.set_trace_callback(trace)
                response = book.recall(**request)
                book.db.set_trace_callback(None)
                counts.update({name + "_calls": function.call_count for name, function in parsers.items()})
            counts["unique_source_pages_checked"] = len(checked)
            counts["unique_source_pages_certified"] = len(certified_ids)
            observations.append({"case": name, "sessions": sessions, "corruption": corruption,
                                 "request": request, "uninstrumented": timings,
                                 "counts": counts, "instrumented_response": response})
    output = {
        "scope": "Authored candidate3 review work diagnostic; no independent quality or speed claim",
        "python": platform.python_version(), "platform": platform.platform(), "backend": BACKEND_NAME,
        "store_sha256": hashlib.sha256(Path(store.__file__).read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ("v011-current-route-probe.py", "v011-unclassified-proposal-review.py")},
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(output, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(json.dumps({"output": str(args.output), "cases": len(observations), "backend": BACKEND_NAME}))


if __name__ == "__main__":
    main()
