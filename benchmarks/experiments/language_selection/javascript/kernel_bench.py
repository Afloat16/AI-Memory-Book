"""Serialized C, Rust, Node-kernel and Node-bridge helper comparisons.

Consumes capture_inputs.py's fixed input schema. These are helper costs, never
end-to-end retrieval latency. No production source or method is patched.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
import unicodedata

from client import NodeClient, decode, encode


def python_call(module, case, lexical):
    name, args = case["function"], case["args"]
    if name in ("terms_ascii", "ascii_tokens"):
        method = getattr(module, name)
        text, query, stop = args
        stop = frozenset(stop)
        return lambda: method(text, query, stop)
    if name == "unicode_tokens":
        method = getattr(module, name)
        text, query, stop, zh_stop = args
        stop, zh_stop = frozenset(stop), frozenset(zh_stop)
        return lambda: method(text, query, stop, zh_stop)
    if name == "fold_excerpt_source":
        method = module.fold_excerpt_source
        return lambda: method(args[0], unicodedata.normalize, unicodedata.category)
    if name == "literal_positions":
        method = module.literal_positions
        return lambda: method(*args)
    if name == "evidence_units":
        method = module.evidence_units
        return lambda: method(*args)
    if name == "context_allocations":
        method = module.context_allocations
        return lambda: method(*args)
    if name == "excerpt_window":
        method = module.excerpt_window
        text, q, hits, width = args
        hits = [tuple(hit) for hit in hits]
        # Keep every iteration's incoming state identical: the current native
        # entry mutates this list by sorting it. Node copies its incoming list.
        return lambda: method(text, q, list(hits), width, lexical._evidence_units, math.log1p, math.fsum)
    if name == "excerpt_selection":
        method = module.excerpt_window
        literal = module.literal_positions
        text, lower, q, mapping, width = args
        return lambda: method(text, q, literal(lower, q, mapping), width, lexical._evidence_units, math.log1p, math.fsum)
    raise KeyError(name)


def node_case(case):
    name, args = case["function"], case["args"]
    if name == "literal_positions":
        return name, args[:2]
    if name == "fold_excerpt_source":
        return "fold_table", args
    if name == "excerpt_window":
        text, q, hits, width = args
        ids = {term: index for index, term in enumerate(q)}
        return name, [text, q, [(position, ids[term]) for position, term in hits], width]
    return name, args


def normalize_node_output(case, value):
    name, args = case["function"], case["args"]
    if name == "literal_positions":
        _, terms, mapping = args
        return [(position if mapping is None else mapping[position], terms[term]) for position, term in value]
    if name == "context_allocations":
        pages = args[0]
        return [(pages[index], header, allowance) for index, header, allowance in value]
    return value


def canonical(value):
    if value is NotImplemented:
        raise ValueError("Candidate returned NotImplemented; do not time a silent fallback")
    return json.dumps(encode(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def main(args):
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text
    raw = args.inputs.read_bytes()
    document = decode(json.loads(raw))
    cases = document["cases"]
    backends = {"current-c": _native}
    imported_modules = set()
    for value in args.native_backend:
        label, path, module = value.split("=", 2)
        if label in backends or module in imported_modules:
            raise ValueError("Native backend labels/module names must be unique in one process")
        imported_modules.add(module)
        sys.path.insert(0, path)
        backends[label] = importlib.import_module(module)
    output = {"schema_version": 1, "status": "running", "kind": "helper-and-bridge-not-end-to-end",
        "input_sha256": hashlib.sha256(raw).hexdigest(), "iterations": args.iterations,
        "rounds": args.rounds, "warmup_per_case": args.warmup, "records": [], "omissions": [],
        "notes": ["current-c includes the Python-to-C call; node-kernel excludes JSON/IPC and Python object reconstruction",
                  "node-bridge includes JSON/IPC/object reconstruction; no hidden worker cache",
                  "Node fold is the shared immutable table candidate, not the callback-preserving direct translation",
                  "Native backend lacking a helper is recorded as omitted, never silently routed to C",
                  "Window-only includes an input-list reset because the C function mutates positions; coarse selection recreates hits naturally"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    with NodeClient(native=_native) as node:
        output["node_identity"] = node.request({"op": "identity"})
        output["unicode_identity"] = node.unicode_identity
        output["native_binaries"] = {label: {"path": module.__file__,
            "sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
            for label, module in backends.items()}
        calls, expected = {}, {}
        for case in cases:
            expected[case["id"]] = canonical(python_call(_native, case, text)())
            for label, module in backends.items():
                try:
                    operation = python_call(module, case, text)
                except AttributeError:
                    output["omissions"].append({"backend": label, "case_id": case["id"], "function": case["function"]})
                    continue
                if canonical(operation()) != expected[case["id"]]:
                    raise AssertionError((label, case["id"], "output mismatch"))
                calls[label, case["id"]] = operation
            name, values = node_case(case)
            if canonical(normalize_node_output(case, node.invoke(name, *values))) != expected[case["id"]]:
                raise AssertionError(("node-kernel", case["id"], "output mismatch"))
            if case["function"] != "excerpt_selection":
                operation = python_call(node, case, text)
                if canonical(operation()) != expected[case["id"]]:
                    raise AssertionError(("node-bridge", case["id"], "output mismatch"))
                calls["node-bridge", case["id"]] = operation
        if args.correctness_only:
            output["status"] = "correctness-only-passed"
            save()
            print(json.dumps({"status": output["status"], "cases": len(cases), "omissions": len(output["omissions"])}))
            return
        # The entire correctness pass precedes all measured rounds.
        for operation in calls.values():
            for _ in range(args.warmup):
                operation()
        for case in cases:
            name, values = node_case(case)
            node.request({"op": "bench", "name": name, "args": values, "iterations": 1,
                          "samples": 1, "warmup": args.warmup})
        arms = [*backends, "node-kernel", "node-bridge"]
        for round_index in range(args.rounds):
            # Cyclic, alternating direction; every arm is measured serially.
            order = arms[round_index % len(arms):] + arms[:round_index % len(arms)]
            if round_index % 2:
                order = list(reversed(order))
            for arm in order:
                for case in cases:
                    if arm == "node-kernel":
                        name, values = node_case(case)
                        result = node.request({"op": "bench", "name": name, "args": values,
                            "iterations": args.iterations, "samples": 1, "warmup": 0})
                        elapsed, sink = result["timings_ns"][0], result["sink"]
                        actual = canonical(normalize_node_output(case, result["last"]))
                    else:
                        operation = calls.get((arm, case["id"]))
                        if operation is None:
                            continue
                        sink = 0
                        start = time.perf_counter_ns()
                        for _ in range(args.iterations):
                            last = operation()
                            sink += len(last)
                        elapsed = time.perf_counter_ns() - start
                        actual = canonical(last)
                    if actual != expected[case["id"]]:
                        raise AssertionError((arm, case["id"], round_index, "timed output mismatch"))
                    output["records"].append({"round": round_index, "order": order, "backend": arm,
                        "case_id": case["id"], "cohort": case["cohort"], "phase": case["phase"],
                        "function": case["function"], "total_ns": elapsed,
                        "ns_per_call": elapsed / args.iterations, "sink": sink})
                save()
        output["status"] = "completed"
        save()
        print(json.dumps({"output": str(args.output), "records": len(output["records"]),
                          "omissions": len(output["omissions"]), "input_sha256": output["input_sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-backend", action="append", default=[], metavar="LABEL=DIR=MODULE")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=64)
    parser.add_argument("--warmup", type=int, default=16)
    parser.add_argument("--correctness-only", action="store_true")
    main(parser.parse_args())
