"""Correctness only: Bash vs the current C helpers and independent Python regex."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

from client import BashClient, METHODS, captured_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new correctness output")
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text as lexical
    rng = random.Random(202611171604)
    corpus = [
        "", "aA a1B HTTPParser parseHTTPResponse snake_case", "a an the cache cache",
        "".join(chr(i) for i in range(128)), "".join(chr(i) for i in reversed(range(128))),
        "\x00\x7f A\x00B aAbC9 x_y/z:q.r-s", "a" * 256,
    ]
    corpus.extend("".join(chr(rng.randrange(128)) for _ in range(rng.randrange(97))) for _ in range(240))
    digest = hashlib.sha256()
    calls = 0
    seen = set()
    captures, omitted = captured_cases(args.inputs, lexical.STOP) if args.inputs else ([], [])
    with BashClient(lexical.STOP) as candidate:
        for sample in corpus:
            seen.update(map(ord, sample))
            for method in METHODS:
                for query in (False, True):
                    reference = re.sub(r"([a-z])([A-Z])", r"\1 \2", sample).casefold() if method == "terms_ascii" else sample
                    expected = re.findall(r"[a-z0-9]+", reference)
                    if query:
                        expected = [token for token in expected if token not in lexical.STOP]
                    current = getattr(_native, method)(sample, query, lexical.STOP)
                    actual = candidate.invoke(method, sample, query)
                    assert actual == current == expected, (method, query, repr(sample), actual, expected)
                    digest.update(json.dumps([method, query, actual], ensure_ascii=True, separators=(",", ":")).encode())
                    calls += 1
        for sample in corpus[:8]:
            for method in METHODS:
                for query in (False, True):
                    expected = getattr(_native, method)(sample, query, lexical.STOP)
                    assert candidate.invoke(method, sample, query, repetitions=3) == expected
                    calls += 1
        for case in captures:
            method = case["function"]
            sample, query, stop = case["args"]
            actual = candidate.invoke(method, sample, query)
            expected = getattr(_native, method)(sample, query, frozenset(stop))
            assert actual == expected, case["id"]
            digest.update(json.dumps([case["id"], actual], ensure_ascii=True, separators=(",", ":")).encode())
            calls += 1
    assert seen == set(range(128))
    report = {
        "candidate": "pure-bash-ascii", "status": "correctness-passed",
        "rpc_checks": calls, "generated_texts": len(corpus), "ascii_codepoints_covered": len(seen),
        "nul_and_del_covered": 0 in seen and 127 in seen, "captured_cases": len(captures),
        "omitted_cases": omitted, "result_sha256": digest.hexdigest(),
        "input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest() if args.inputs else None,
        "worker_sha256": hashlib.sha256(Path(__file__).with_name("worker.bash").read_bytes()).hexdigest(),
        "client_sha256": hashlib.sha256(Path(__file__).with_name("client.py").read_bytes()).hexdigest(),
        "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "current_c_binary_sha256": hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest(),
        "bash": subprocess.check_output([shutil.which("bash"), "--version"], text=True).splitlines()[0],
        "scope": "Only two ASCII lexical helpers, exact bool and the ordinary stop set. No full Shell application or retrieval claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
