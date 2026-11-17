"""Freeze real helper inputs by reading the Python caller frame at c_call.

The profile event identifies the C callee, NOT its argument values. Known,
unchanged caller-frame local variables supply the arguments below. No helper
is monkeypatched, no readiness guard changes, and no timings are collected.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unicodedata

from client import encode

ROOT = Path(__file__).resolve().parents[4]
FIELDS = ("id", "project_id", "session_id", "created_at", "content")
CALLBACKS = {
    "fold_excerpt_source": {"normalize": "unicodedata.normalize", "category": "unicodedata.category"},
    "excerpt_window": {"evidence_units": "memory_book.text._evidence_units", "log1p": "math.log1p", "fsum": "math.fsum"},
    "excerpt_selection": {"evidence_units": "memory_book.text._evidence_units", "log1p": "math.log1p", "fsum": "math.fsum"},
}


def capture(args):
    sys.path[:0] = [str(args.source.resolve()), str(ROOT)]
    from memory_book import MemoryBook, text, _native
    from benchmarks.data import generate_dataset
    from benchmarks.public_data import load_locomo
    datasets = {"synthetic61": generate_dataset(seed=61, split="development", projects=8),
                "public1015": load_locomo(args.locomo)}
    rng = random.Random(11062026)
    slots, counts, skipped = {}, Counter(), Counter()
    state = {"cohort": None, "phase": None}

    def trace(frame, event, callee):
        if event != "c_call" or getattr(callee, "__self__", None) is not _native:
            return
        name = getattr(callee, "__name__", "")
        local = frame.f_locals
        caller = frame.f_code.co_name
        if name in ("terms_ascii", "ascii_tokens") and caller == "terms":
            values = [local["text"], local["query"], sorted(frame.f_globals["STOP"])]
        elif name == "unicode_tokens" and caller == "terms":
            values = [local["text"], local["query"], sorted(frame.f_globals["STOP"]), sorted(frame.f_globals["ZH_STOP"])]
        elif name == "fold_excerpt_source" and caller == "_fold_excerpt_source":
            values = [local["text"]]
        elif name == "literal_positions" and caller == "excerpt":
            values = [local["lower"], local["q"], local["source_positions"]]
        elif name == "evidence_units" and caller == "_evidence_units":
            values = [local["text"], local["width"]]
        elif name == "excerpt_window" and caller == "excerpt":
            values = [local["text"], local["q"], local["positions"], local["width"]]
        elif name == "context_allocations" and caller == "_context_allocations":
            values = [[{key: row[key] for key in FIELDS} for row in local["pages"]], local["budget"]]
        else:
            if name in ("terms_ascii", "ascii_tokens", "unicode_tokens", "fold_excerpt_source",
                        "literal_positions", "evidence_units", "excerpt_window", "context_allocations"):
                skipped[name + ":" + caller] += 1
            return
        key = state["cohort"], state["phase"], name
        counts[key] += 1
        entries = slots.setdefault(key, [])
        location = len(entries) if len(entries) < args.per_family else rng.randrange(counts[key])
        if location >= args.per_family:
            return
        case = {"cohort": state["cohort"], "phase": state["phase"], "function": name,
                "args": copy.deepcopy(values), "callbacks": CALLBACKS.get(name, {}),
                "sampled_call": counts[key], "caller": caller}
        if name == "excerpt_window":
            case["selection_args"] = copy.deepcopy([local["text"], local["lower"], local["q"],
                                                      local["source_positions"], local["width"]])
        if location == len(entries):
            entries.append(case)
        else:
            entries[location] = case

    args.output.parent.mkdir(parents=True, exist_ok=True)
    for cohort, data in datasets.items():
        state["cohort"] = cohort
        with tempfile.TemporaryDirectory(prefix="capture-inputs-", dir=args.output.parent) as directory:
            with MemoryBook(Path(directory) / "memory.db", cache_size=0) as book:
                for phase in ("ingest", "recall_char2400"):
                    state["phase"] = phase
                    sys.setprofile(trace)
                    try:
                        if phase == "ingest":
                            for session in data.sessions:
                                book.ingest(session)
                        else:
                            for query in data.queries:
                                book.recall(query.query, project=query.project, limit=5, budget_chars=2400, use_cache=False)
                    finally:
                        sys.setprofile(None)
                assert text._native_excerpt_window_ready()

    cases = []
    for key in sorted(slots):
        for case in slots[key]:
            selection = case.pop("selection_args", None)
            cases.append(case)
            if selection is not None:
                cases.append({**case, "function": "excerpt_selection", "args": selection,
                              "callbacks": CALLBACKS["excerpt_selection"]})

    def add(name, values):
        cases.append({"cohort": "unicode-long-stress", "phase": "synthetic-stress", "function": name,
                      "args": values, "callbacks": CALLBACKS.get(name, {}), "sampled_call": None, "caller": None})
    stop, zh_stop = sorted(text.STOP), sorted(text.ZH_STOP)
    ascii_text = "HTTPParser parseHTTPResponse cacheRetry_17 path/to/file.py current final " * 200
    add("terms_ascii", [ascii_text, True, stop])
    add("ascii_tokens", [ascii_text.lower(), False, stop])
    mixed = "缓存 Café Straße e\u0301 İstanbul 🙂\U00020000 \ud800\udc00 \udfff A中🙂B。下一句！\n" * 240
    add("unicode_tokens", [mixed, True, stop, zh_stop])
    add("fold_excerpt_source", [mixed])
    add("evidence_units", [mixed, 480])
    lower, mapping = text._fold_excerpt_source(mixed)
    terms = ["缓存", "cafe", "strasse", "istanbul", "🙂", "\ud800\udc00", "\U00020000"]
    hits = _native.literal_positions(lower, terms, mapping)
    add("literal_positions", [lower, terms, mapping])
    add("excerpt_window", [mixed, terms, hits, 480])
    add("excerpt_selection", [mixed, lower, terms, mapping, 480])
    pages = [{"id": f"page-{i}🙂", "project_id": "项目", "session_id": "session",
              "created_at": "2026-11-17T00:00:00Z", "content": mixed[:(i + 1) * 70]} for i in range(32)]
    add("context_allocations", [pages, 2400])
    long_terms = [f"token{i}x" for i in range(64)]
    long_text = "\n".join((" ".join(long_terms[i:i+8]) + " values remain exactly unchanged. ") * 3 for i in range(0, 64, 8))
    long_hits = _native.literal_positions(long_text, long_terms, None)
    add("excerpt_window", [long_text, long_terms, long_hits, 512])
    add("excerpt_selection", [long_text, long_text, long_terms, None, 512])
    for index, case in enumerate(cases):
        case["id"] = f"case-{index:04d}"
    record = {"schema_version": 1, "status": "frozen-inputs-not-a-performance-result",
        "baseline_commit": "234891619d7bed88ddf3fae37e7f3e1b14a808b6",
        "native_sha256": hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest(),
        "python": sys.version, "unicode_version": unicodedata.unidata_version,
        "sampling": {"method": "seeded reservoir per corpus/phase/helper", "seed": 11062026, "per_family": args.per_family},
        "capture_method": "sys.setprofile c_call identifies callee; unchanged Python caller-frame locals provide exact arguments",
        "case_count": len(cases), "observed_counts": {"/".join(key): count for key, count in sorted(counts.items())},
        "uncaptured_callers": dict(skipped), "cases": cases}
    raw = (json.dumps(encode(record), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    args.output.write_bytes(raw)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(raw).hexdigest(),
                      "bytes": len(raw), "case_count": len(cases), "uncaptured_callers": dict(skipped)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--locomo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=8)
    capture(parser.parse_args())
