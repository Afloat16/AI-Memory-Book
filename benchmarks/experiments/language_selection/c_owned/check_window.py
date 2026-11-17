"""Independent C-output and floating-point checks for the same larger C stage."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import struct
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new correctness output")
    sys.path.insert(0, str(args.python_source))
    from memory_book import _native as baseline
    spec = importlib.util.spec_from_file_location("_language_c_owned", args.binary)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    bits = lambda value: struct.pack("!d", value)
    expected = [math.log1p(i) for i in range(1, 2561)]
    actual = candidate.log1p_values(list(range(1, 2561)))
    differing = [i+1 for i, (a,b) in enumerate(zip(actual,expected)) if bits(a)!=bits(b)]
    assert not [i for i in differing if i <= 40], differing
    rng = random.Random(202611170935)
    sum_digest = hashlib.sha256()
    for _ in range(10000):
        values = [expected[rng.randrange(40)] for _ in range(rng.randrange(65))]
        result = candidate.positive_fsum(values)
        assert bits(result)==bits(math.fsum(values)), values
        sum_digest.update(bits(result))
    digest = hashlib.sha256()
    cases = 0
    alphabet = "AaB9 aabb_./:- .!?。！？缓存当前中éß\u0301\ud800\udfff🙂𠀀\r\n\t\x00\x85\u00a0\u2003\u2028\u3000"
    for i in range(6000):
        length = rng.randrange(2,1000)
        source = "".join(rng.choices(alphabet,k=length))
        q = list(dict.fromkeys(rng.choices(list(dict.fromkeys(alphabet)), k=rng.randrange(20))))
        if i % 10 == 0:
            q = ["term" + str(n) for n in range(64)]
            positions = [(rng.randrange(length+1), term) for term in q for _ in range(rng.randrange(5))]
        else:
            positions = baseline.literal_positions(source,q,None)
        width = rng.randrange(1,length)
        left = positions[:]
        right = positions[:]
        want = baseline.excerpt_window(source,q,left,width,baseline.evidence_units,math.log1p,math.fsum)
        got = candidate.excerpt_window_owned(source,q,right,width)
        assert got is not NotImplemented, (i, q, len(positions))
        assert want == got and left==right, (i,repr(source),q,width,want,got)
        digest.update(json.dumps([got,right],ensure_ascii=True,separators=(",",":")).encode())
        cases += 1
    # Unsupported inputs must return before mutating the position list.
    fallbacks = [
        ("a"*100,["a","a"],[(30,"a"),(1,"a")],20),
        ("a"*100,["a"],[(i,"a") for i in range(41)],20),
        ("abc",["a"],[(1,"a")],0),
        ("abc",["a"],[(1,"a")],3),
        ("abc",["a"],[(1,"other")],2),
        ("abc",["a"],[(10**100,"a")],2),
        ("abc",["a"],[(1,"a")],10**100),
        ("abc",["a"],[(1,"a")],True),
    ]
    for source,q,positions,width in fallbacks:
        before=positions[:]
        assert candidate.excerpt_window_owned(source,q,positions,width) is NotImplemented
        assert positions==before
    report = {
        "candidate": "c-owned-window", "status": "passed", "cases": cases,
        "result_sha256": digest.hexdigest(), "fsum_cases": 10000,
        "fsum_output_sha256": sum_digest.hexdigest(), "log1p_tested_integers": 2560,
        "log1p_differences": differing, "accepted_frequency_domain": [1,40],
        "unsupported_cases": len(fallbacks), "python": sys.version,
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Complete ordinary-query window; native units, selection and floating scores, exact codepoint slicing; custom callbacks handled by adapter fallback.",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
