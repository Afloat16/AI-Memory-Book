"""Count candidate4 qualifier work on six authored review cases.

All inputs and responses are retained. Instrumented elapsed times are not
performance measurements. This is a development diagnostic, not a holdout or
an external-product comparison. Existing output is never replaced.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import platform
import runpy
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
import memory_book.store as store


def cases():
    fixture_path = Path(__file__).with_name("v011-facet-association-review.py")
    fixtures = runpy.run_path(str(fixture_path))["fixtures"]
    for count in (8, 104):
        for valid in (False, True):
            sessions = fixtures(count)
            if valid:
                sessions[-1]["session_id"] = "accepted"
                sessions[-1]["messages"][0]["content"] = "Production lease_duration=12."
            yield f"{'adjacent' if valid else 'other-sentence'}-{count}", sessions
    sessions = fixtures(8)
    for source in sessions[:-1]:
        source["messages"][0]["content"] = (
            "Staging lease_duration=30. The production review remains open. "
            + "production lease_duration. " * 12)
    sessions[-1]["messages"][0]["content"] = (
        "Production lease_duration=12. " + "Administrative scheduling note. " * 100)
    yield "unqualified-original-anchor", sessions
    sessions = fixtures(8)
    sessions[-1]["messages"][0]["content"] = (
        "Production lease_duration=30. Staging lease_duration=99. "
        + "Administrative scheduling note. " * 100)
    yield "multiple-declarations-of-one-field", sessions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to replace an earlier observation")
    observations = []
    for name, sessions in cases():
        with MemoryBook(":memory:", segmentation="turn") as book:
            for source in sessions:
                book.ingest(source)
            request = {"query": "current production lease_duration", "project": "workers",
                       "limit": 1, "budget_chars": 2400, "use_cache": False}
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
                           for name in ("_declaration_clauses", "_declaration_qualifier", "_quoted_spans")}
                stack.enter_context(patch.object(store, "_complete_declaration_pages", source_check))
                book.db.set_trace_callback(trace)
                response = book.recall(**request)
                book.db.set_trace_callback(None)
                counts.update({name + "_calls": function.call_count for name, function in parsers.items()})
            counts["unique_source_pages_checked"] = len(checked)
            counts["unique_source_pages_certified"] = len(certified_ids)
            observations.append({"case": name, "sessions": sessions, "request": request,
                                 "response": response, "counts": counts})
    output = {
        "scope": "Authored qualifier work diagnostic; instrumented latency is not a speed measurement",
        "python": platform.python_version(), "backend": BACKEND_NAME,
        "actual_store_path": str(Path(store.__file__).resolve()),
        "store_sha256": hashlib.sha256(Path(store.__file__).read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            Path(__file__).with_name("v011-facet-association-review.py").read_bytes()).hexdigest(),
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(output, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(json.dumps({"output": str(args.output), "cases": len(observations), "backend": BACKEND_NAME}))


if __name__ == "__main__":
    main()
