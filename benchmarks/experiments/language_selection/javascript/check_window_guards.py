"""Targeted certificate regression; no performance measurements or source edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from client import NodeClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text

    original = text._evidence_units.__code__
    records = []
    value = "First cache explanation.\nAnother cache sentence.\n" * 9
    q, hits, width = ["cache"], _native.literal_positions(value, ["cache"], None), 70
    text._node_guard_calls = []

    def changed_units(value, width):
        _node_guard_calls.append((value, width))
        return []

    def check(when):
        text._evidence_units.__code__ = original
        if when == "before":
            text._evidence_units.__code__ = changed_units.__code__
        try:
            with NodeClient(native=_native) as node:
                if when == "after":
                    assert node.evidence_certified
                    text._evidence_units.__code__ = changed_units.__code__
                elif when == "before":
                    assert not node.evidence_certified
                else:
                    assert node.evidence_certified
                assert text._native_excerpt_window_ready(), "Fixture must retain the old identity-only guard"
                text._node_guard_calls.clear()
                expected = _native.excerpt_window(value, q, list(hits), width,
                    text._evidence_units, math.log1p, math.fsum)
                expected_calls = list(text._node_guard_calls)
                text._node_guard_calls.clear()
                requests = []
                invoke = node.invoke
                def observed(name, *arguments):
                    requests.append(name)
                    return invoke(name, *arguments)
                node.invoke = observed
                actual = node.excerpt_window(value, q, list(hits), width,
                    text._evidence_units, math.log1p, math.fsum)
                assert actual == expected
                assert text._node_guard_calls == expected_calls
                assert requests == (["excerpt_window"] if when == "ordinary" else [])
                records.append({"case": when, "passed": True, "node_operations": requests,
                                "callback_calls": len(expected_calls)})
        finally:
            text._evidence_units.__code__ = original

    try:
        for when in ("ordinary", "before", "after"):
            check(when)
    finally:
        del text._node_guard_calls
    here = Path(__file__).resolve().parent
    inherited = json.loads((here / "correctness-local.json").read_text())
    report = {"status": "passed", "kind": "targeted-guard-regression-not-performance",
        "cases": records, "client_sha256": hashlib.sha256((here / "client.py").read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inherited_full_check": {"path": "correctness-local.json",
            "sha256": hashlib.sha256((here / "correctness-local.json").read_bytes()).hexdigest(),
            "scope": "Kernel and worker bytes are unchanged; this followup changes only Python callback certification",
            "kernel_unchanged": inherited["source_sha256"]["kernels.mjs"] == hashlib.sha256((here / "kernels.mjs").read_bytes()).hexdigest(),
            "worker_unchanged": inherited["source_sha256"]["worker.mjs"] == hashlib.sha256((here / "worker.mjs").read_bytes()).hexdigest()}}
    assert report["inherited_full_check"]["kernel_unchanged"] and report["inherited_full_check"]["worker_unchanged"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
