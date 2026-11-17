"""Optional serialized diagnostic timings for captured ASCII inputs.

This is never a full retrieval/MCP benchmark or an adoption gate. Running this
file without --measure cannot start timing. Run check.py first on the same host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from client import BashClient, captured_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--cold-starts", type=int, default=3)
    parser.add_argument("--limit-cases", type=int, default=0)
    args = parser.parse_args()
    if not args.measure:
        parser.error("Measurement requires explicit --measure and a reserved CPU window")
    if args.output.exists():
        raise SystemExit("Choose a new diagnostic output; never replace earlier measurements")
    if args.rounds < 1 or not 1 <= args.iterations <= 100000 or args.warmup < 0 or args.cold_starts < 0:
        parser.error("Invalid measurement counts")
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text as lexical
    cases, omitted = captured_cases(args.inputs, lexical.STOP)
    if not cases:
        raise ValueError("Captured inputs contain no supported ASCII helper cases")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Captured case IDs are not unique")
    if args.limit_cases > 0:
        omitted.extend({"id": case["id"], "reason": "explicit diagnostic case limit in frozen capture order"}
                       for case in cases[args.limit_cases:])
        cases = cases[:args.limit_cases]
    bash_executable = shutil.which("bash")
    if not bash_executable:
        raise RuntimeError("Bash is unavailable")
    bash_path = Path(bash_executable).resolve()
    output = {
        "schema_version": 1, "status": "preflight", "kind": "ascii-helper-diagnostic-not-end-to-end",
        "input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        "worker_sha256": hashlib.sha256(Path(__file__).with_name("worker.bash").read_bytes()).hexdigest(),
        "client_sha256": hashlib.sha256(Path(__file__).with_name("client.py").read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "current_c_binary": {"path": _native.__file__, "sha256": hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest()},
        "bash": subprocess.check_output([str(bash_path), "--version"], text=True).splitlines()[0],
        "bash_binary": {"path": str(bash_path), "sha256": hashlib.sha256(bash_path.read_bytes()).hexdigest()},
        "python": sys.version, "rounds": args.rounds, "iterations": args.iterations,
        "warmup": args.warmup, "cases": len(cases), "omissions": omitted,
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "records": [], "cold_starts": [],
        "notes": [
            "current-c includes Python-to-C calls and result creation in the existing interpreter",
            "shell-rpc includes integer encoding, persistent-process IPC, Bash scanning and decoding per call",
            "shell-batch repeats the actual Bash scanner N times, amortizing one frame's encode/parse/IPC/decode cost",
            "shell-batch still includes a frame's overhead; it is an optimistic protocol diagnostic, not a pure kernel timer",
            "The frozen standard STOP set is initialized once per worker, matching a persistent ordinary constant, not a query-result cache",
            "Cold startup is separately reported for the auxiliary Bash worker including STOP loading; no C cold-start ratio is implied",
            "No full Shell application, SQL, ingestion, MCP or retrieval rewrite is implemented or timed",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    expected = {}
    operations = {}
    try:
        with BashClient(lexical.STOP, bash=str(bash_path)) as shell:
            for case in cases:
                name = case["function"]
                value, query, stop = case["args"]
                method = getattr(_native, name)
                stop = frozenset(stop)
                operations[case["id"]] = lambda method=method, value=value, query=query, stop=stop: method(value, query, stop)
                expected[case["id"]] = operations[case["id"]]()
                assert shell.invoke(name, value, query) == expected[case["id"]], case["id"]
                assert shell.invoke(name, value, query, repetitions=args.iterations) == expected[case["id"]], case["id"]
            output["status"] = "measuring"
            save()
            for case in cases:
                name = case["function"]
                value, query, _ = case["args"]
                for _ in range(args.warmup):
                    operations[case["id"]]()
                    shell.invoke(name, value, query)
            arms = ["current-c", "shell-rpc", "shell-batch"]
            for round_index in range(args.rounds):
                order = arms[round_index % 3:] + arms[:round_index % 3]
                if round_index % 2:
                    order.reverse()
                for arm in order:
                    for case in cases:
                        name = case["function"]
                        value, query, _ = case["args"]
                        sink = 0
                        start = time.perf_counter_ns()
                        if arm == "shell-batch":
                            last = shell.invoke(name, value, query, repetitions=args.iterations)
                            sink = len(last) * args.iterations
                        else:
                            operation = operations[case["id"]] if arm == "current-c" else lambda: shell.invoke(name, value, query)
                            for _ in range(args.iterations):
                                last = operation()
                                sink += len(last)
                        elapsed = time.perf_counter_ns() - start
                        assert last == expected[case["id"]], (arm, case["id"], round_index)
                        output["records"].append({
                            "round": round_index, "order": order, "backend": arm, "case_id": case["id"],
                            "cohort": case.get("cohort"), "phase": case.get("phase"), "function": name,
                            "input_characters": len(value), "query": query, "iterations": args.iterations,
                            "total_ns": elapsed, "ns_per_call": elapsed / args.iterations, "sink": sink,
                            "result_sha256": hashlib.sha256(json.dumps(last, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest(),
                        })
                    save()
        first = cases[0]
        name = first["function"]
        value, query, _ = first["args"]
        for index in range(args.cold_starts):
            start = time.perf_counter_ns()
            shell = BashClient(lexical.STOP, bash=str(bash_path))
            ready = time.perf_counter_ns()
            try:
                last = shell.invoke(name, value, query)
                completed = time.perf_counter_ns()
                assert last == expected[first["id"]]
            finally:
                shell.close()
            output["cold_starts"].append({
                "index": index, "case_id": first["id"],
                "worker_startup_and_stop_load_ns": ready - start,
                "first_rpc_ns": completed - ready,
                "startup_plus_first_rpc_ns": completed - start,
            })
            save()
        output["status"] = "completed"
        save()
    except BaseException as error:
        output["status"] = "failed"
        output["error"] = {"type": type(error).__name__, "message": str(error)}
        save()
        raise
    print(json.dumps({"output": str(args.output), "records": len(output["records"]),
                      "cases": len(cases), "status": output["status"]}))


if __name__ == "__main__":
    main()
