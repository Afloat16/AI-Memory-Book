"""Targeted certificate regression; no performance measurements or source edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import unicodedata

from client import NodeClient


def current_kernel_check(path, here, native):
    """Bind an explicit current-run verify.py report to these exact inputs."""
    path = path.resolve()
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("status") != "passed" or value.get("kind") != "correctness-not-performance":
        raise ValueError("--kernel-report must be a successful verify.py correctness report")
    expected_sources = {
        name: hashlib.sha256((here / name).read_bytes()).hexdigest()
        for name in ("kernels.mjs", "worker.mjs", "client.py", "verify.py", "unicode-properties.json")
    }
    if value.get("source_sha256") != expected_sources:
        raise ValueError("--kernel-report source hashes differ from the current experiment")
    binary_sha256 = hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
    if value.get("reference_binary_sha256") != binary_sha256:
        raise ValueError("--kernel-report reference binary differs from the loaded native module")
    if value.get("python") != platform.python_version() or value.get("unicode") != unicodedata.unidata_version:
        raise ValueError("--kernel-report Python or Unicode runtime differs")
    if value.get("unicode_codepoints_covered_in_blocks") != 0x110000:
        raise ValueError("--kernel-report does not cover the full Unicode code-point domain")
    counts = value.get("counts")
    if not isinstance(counts, dict) or not counts or not all(type(count) is int and count > 0 for count in counts.values()):
        raise ValueError("--kernel-report contains invalid correctness counts")
    output_digest = value.get("output_digest")
    if not isinstance(output_digest, str) or len(output_digest) != 64 or any(c not in "0123456789abcdef" for c in output_digest):
        raise ValueError("--kernel-report has no valid output digest")
    node = value.get("node")
    if not isinstance(node, dict) or not isinstance(node.get("versions"), dict) or not isinstance(node.get("node"), str):
        raise ValueError("--kernel-report has no Node runtime identity")
    receipt = {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "status": value["status"],
        "kind": value["kind"],
        "output_digest": output_digest,
        "counts": counts,
        "source_sha256": expected_sources,
        "source_hashes_match": True,
        "reference_binary_sha256": binary_sha256,
        "reference_binary_matches": True,
        "python": value["python"],
        "unicode": value["unicode"],
        "unicode_codepoints_covered_in_blocks": value["unicode_codepoints_covered_in_blocks"],
        "node": node,
        "scope": "Explicit current-run core-check report supplied by --kernel-report; no historical report discovery or fallback",
    }
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--kernel-report", type=Path, required=True,
                        help="Successful verify.py report produced by this experiment run")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text

    here = Path(__file__).resolve().parent
    kernel_check = current_kernel_check(args.kernel_report, here, _native)
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
                identity = node.request({"op": "identity"})
                assert identity["node"] == kernel_check["node"]["node"]
                assert identity["versions"] == kernel_check["node"]["versions"]
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
    report = {"status": "passed", "kind": "targeted-guard-regression-not-performance",
        "cases": records, "client_sha256": hashlib.sha256((here / "client.py").read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inherited_full_check": kernel_check}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
