"""Count source checks and pure parsing in the authored current-route probe.

Instrumentation changes runtime cost; this file reports work, not latency.
Use PYTHONPATH to select an isolated source snapshot for an exact comparison.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to replace an earlier observation")
    fixture_path = Path(__file__).with_name("v011-current-route-probe.py")
    record = runpy.run_path(str(fixture_path))["record"]
    observations = []
    for old_count in (4, 100, 1000):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(old_count):
                book.ingest(record(f"old-{index}", "retry_limit=3. " + "retry_limit. " * 12,
                                   f"2026-01-{index % 28 + 1:02}T00:00:00Z"))
            book.ingest(record("new", "retry_limit=7. The short accepted revision replaces the original configuration.",
                               "2026-06-01T00:00:00Z"))
            for limit in (1, 5):
                counts = {"application_selects": 0, "internal_sql_statements": 0,
                          "source_pages_checked": 0, "source_pages_certified": 0}

                def trace(statement):
                    statement = statement.lstrip().upper()
                    if statement.startswith(("SELECT", "WITH")):
                        counts["application_selects"] += 1
                    elif statement.startswith("--"):
                        counts["internal_sql_statements"] += 1

                def measured(name, function):
                    counts[name + "_calls"] = 0
                    counts[name + "_chars"] = 0

                    def call(text, *arguments, **options):
                        counts[name + "_calls"] += 1
                        counts[name + "_chars"] += len(text)
                        return function(text, *arguments, **options)

                    return call

                authenticate = store._complete_declaration_pages

                def source_check(db, contents, references):
                    counts["source_pages_checked"] += len(contents)
                    certified = authenticate(db, contents, references)
                    counts["source_pages_certified"] += len(certified)
                    return certified

                book.db.set_trace_callback(trace)
                with ExitStack() as stack:
                    for name in ("_declaration_clauses", "_quoted_spans", "_field_identity"):
                        stack.enter_context(patch.object(store, name, measured(name, getattr(store, name))))
                    stack.enter_context(patch.object(store, "_complete_declaration_pages", source_check))
                    result = book.recall("retry_limit", project="workers", temporal="current",
                                         limit=limit, use_cache=False)
                book.db.set_trace_callback(None)
                result.pop("latency_ms")
                payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                observations.append({"old_count": old_count, "limit": limit, "counts": counts,
                                     "candidate_expansion": result["temporal"]["candidate_expansion"],
                                     "result_sha256_without_latency": hashlib.sha256(payload).hexdigest()})
    result = {"scope": "authored development work counts; instrumentation is not a latency measurement",
              "label": args.label, "python": platform.python_version(), "backend": BACKEND_NAME,
              "store_sha256": hashlib.sha256(Path(store.__file__).read_bytes()).hexdigest(),
              "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "fixture_probe_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
              "observations": observations}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "observations": len(observations)}))


if __name__ == "__main__":
    main()
