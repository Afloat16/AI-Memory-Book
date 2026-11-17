"""Deterministic differential checks; writes only a requested lab result file."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import sys
import unicodedata

from client import NodeClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from memory_book import _native, text

    rng = random.Random(20261117)
    counts = {}
    digest = hashlib.sha256()

    def record(name, expected, actual):
        if actual != expected:
            raise AssertionError((name, repr(expected)[:1000], repr(actual)[:1000]))
        counts[name] = counts.get(name, 0) + 1
        digest.update(json.dumps(actual, ensure_ascii=True, sort_keys=True).encode())

    with NodeClient(native=_native) as client:
        identity = client.request({"op": "identity"})
        # Every pair of ASCII code points: exact camel boundaries and filtering.
        for begin in range(0, 128 * 128, 256):
            cases, expected = [], []
            for encoded in range(begin, begin + 256):
                value = chr(encoded // 128) + chr(encoded % 128)
                for name in ("terms_ascii", "ascii_tokens"):
                    for query in (False, True):
                        cases.append({"name": name, "args": [value, query, list(text.STOP)]})
                        expected.append(getattr(_native, name)(value, query, text.STOP))
            results = client.request({"op": "batch", "cases": cases})
            for case, reference, result in zip(cases, expected, results):
                record(case["name"], reference, result)

        for _ in range(200):
            value = "".join(chr(rng.randrange(128)) for _ in range(rng.randrange(2000)))
            for name in ("terms_ascii", "ascii_tokens"):
                for query in (False, True):
                    record(name, getattr(_native, name)(value, query, text.STOP),
                           getattr(client, name)(value, query, text.STOP))

        # Unicode tables are matched to Python, not Node's newer ICU database.
        assert client.unicode_verified
        for start in range(0, 0x110000, 4096):
            value = " ".join(chr(cp) for cp in range(start, min(start + 4096, 0x110000)))
            for query in (False, True):
                record("unicode_tokens_all_codepoints", _native.unicode_tokens(value, query, text.STOP, text.ZH_STOP),
                       client.unicode_tokens(value, query, text.STOP, text.ZH_STOP))
            plain = "".join(chr(cp) for cp in range(start, min(start + 4096, 0x110000)))
            record("fold_table_all_codepoints", _native.fold_excerpt_source(plain, unicodedata.normalize, unicodedata.category),
                   client.fold_excerpt_source(plain, unicodedata.normalize, unicodedata.category))

        alphabet = "aaAB0_ .+*?[]()\\^$\t\n\x00缓存éß\u0301🙂\U00020000\ud800\udfff"
        literal_cases = [
            ("", ["", "absent"]),
            ("a" * 120, ["", "a", "aa", "a"]),
            ("A中🙂B\ud800_éß\udfff\x00A中🙂B", ["🙂", "中🙂", "\ud800", "\udfff", "\x00", "A中🙂B"]),
            ("\U00010000\ud800\udc00\U00010000", ["\U00010000", "\ud800\udc00", "\ud800", "\udc00", ""]),
        ]
        for _ in range(400):
            value = "".join(rng.choices(alphabet, k=rng.randrange(1, 180)))
            terms = [value[start:start + rng.randrange(0, 7)]
                     for start in (rng.randrange(len(value)) for _ in range(8))]
            literal_cases.append((value, terms + ["absent", terms[0]]))
        for value, terms in literal_cases:
            for mapping in (None, [index // 2 for index in range(len(value) + 1)]):
                record("literal_positions", _native.literal_positions(value, terms, mapping),
                       client.literal_positions(value, terms, mapping))
        marker = object()
        mapping = [-1, 10**100, marker, "mapped", None]
        terms = ["a", "b", "c", "d", "e", "a"]
        mapped = client.literal_positions("abcde", terms, mapping)
        for index in range(5):
            assert mapped[index][0] is mapping[index]
            assert mapped[index][1] is terms[index]
        counts["mapping_object_identity"] = 5
        for value, terms, mapping in [("abc", [""], []), ("abcabc", ["b"], [0]), ("", [""], [])]:
            for backend in (_native, client):
                try:
                    backend.literal_positions(value, terms, mapping)
                except IndexError:
                    pass
                else:
                    raise AssertionError("short mapping did not retain IndexError")
            counts["mapping_index_error"] = counts.get("mapping_index_error", 0) + 1

        for _ in range(600):
            value = "".join(rng.choices(alphabet + ".!?。！？\n \u0085\u001c\u200b\ufeff", k=rng.randrange(1, 800)))
            width = rng.choice((-1, 0, 1, 5, 20, 120, len(value), len(value) + 1))
            record("evidence_units", _native.evidence_units(value, width), client.evidence_units(value, width))
        for char in [chr(i) for i in range(0x110000) if chr(i).isspace()] + ["\u200b", "\ufeff"]:
            value = "x.x?" + char + "a.a!" + char + "b.b."
            record("evidence_units", _native.evidence_units(value, 5), client.evidence_units(value, 5))

        for index in range(600):
            pages = [{"id": str(i) + "🙂\ud800\udc00", "project_id": "测试", "session_id": "session",
                      "created_at": "2026-11-17T00:00:00Z", "unserialized": object(),
                      "content": "".join(rng.choices(alphabet, k=rng.randrange(0, 600)))}
                     for i in range(rng.randrange(0, 30))]
            budget = rng.choice((0, 1, 8, 9, 100, 2400, 10000, rng.randrange(10000)))
            expected, actual = _native.context_allocations(pages, budget), client.context_allocations(pages, budget)
            assert actual == expected, ("context_allocations", index)
            for page, header, allowance in actual:
                assert any(page is original for original in pages)
            serializable = [[page["id"], header, allowance] for page, header, allowance in actual]
            record("context_allocations", serializable, serializable)

        # Positive-frequency fsum receives precisely the same finite binary64
        # log values, in dictionary insertion order, as the reference scorer.
        assert client.math_verified, "Node and reference log1p differ within 1..40"
        log_diagnostics = client.invoke("log1p_values", list(range(1, 2561)))
        math_differences = [{"input": n, "python_hex": math.log1p(n).hex(), "node_hex": actual.hex()}
            for n, actual in enumerate(log_diagnostics, 1) if math.log1p(n).hex() != actual.hex()]
        for _ in range(1000):
            values = [math.log1p(rng.randrange(1, 41)) for _ in range(rng.randrange(65))]
            actual = client.invoke("positive_fsum", values)
            assert float(actual).hex() == math.fsum(values).hex(), ("fsum", values, actual)
            counts["positive_fsum_float_bits"] = counts.get("positive_fsum_float_bits", 0) + 1

        for _ in range(2500):
            value = "".join(rng.choices(alphabet + ".!?。！？\n ", k=rng.randrange(20, 1400)))
            lower, mapping = text._fold_excerpt_source(value)
            q = list(dict.fromkeys(lower[start:start + rng.randrange(1, 8)]
                     for start in (rng.randrange(len(lower)) for _ in range(rng.randrange(1, 65)))))
            width = rng.randrange(1, len(value))
            hits = _native.literal_positions(lower, q, mapping)
            expected = _native.excerpt_window(value, q, list(hits), width, text._evidence_units, math.log1p, math.fsum)
            actual = client.excerpt_window(value, q, list(hits), width, text._evidence_units, math.log1p, math.fsum)
            assert expected is not NotImplemented
            record("excerpt_window", expected, actual)
            combined = client.invoke("excerpt_selection", value, lower, q, mapping, width)
            combined = combined[0], [tuple(span) for span in combined[1]]
            record("excerpt_selection", expected, combined)

    code = r'''
import json, math, sys, unicodedata as u
sys.path.insert(0, sys.argv[1])
from memory_book import _native, text
from client import NodeClient
kind=sys.argv[2]
calls=[]
if kind=='normalize':
    original=u.normalize
    def override(form,value):
        calls.append((form,value))
        return original(form,value)
    u.normalize=override
elif kind=='category':
    original=u.category
    def override(value):
        calls.append(value)
        return original(value)
    u.category=override
else:
    original=getattr(math,kind)
    def override(value):
        if kind=='fsum': value=list(value)
        calls.append(value)
        return original(value)
    setattr(math,kind,override)
with NodeClient(native=_native) as node:
    if kind in ('normalize','category'):
        assert not node.unicode_verified
        args=('éé A\u0301 Straße',u.normalize,u.category)
        expected=_native.fold_excerpt_source(*args)
        old_calls=list(calls); calls.clear()
        actual=node.fold_excerpt_source(*args)
    else:
        assert not node.math_verified
        args=('cache next sentence. '*20,['cache'],[(0,'cache'),(21,'cache')],60,text._evidence_units,math.log1p,math.fsum)
        expected=_native.excerpt_window(*args)
        old_calls=list(calls); calls.clear()
        actual=node.excerpt_window(*args)
    assert actual==expected and calls==old_calls
print(json.dumps({'override_before_client_construction':kind,'passed':True}))
'''
    overrides = []
    for kind in ("normalize", "category", "log1p", "fsum"):
        run = subprocess.run([sys.executable, "-c", code, str(args.source.resolve()), kind],
            cwd=Path(__file__).parent, check=True, capture_output=True, text=True)
        overrides.append(json.loads(run.stdout))
    here = Path(__file__).resolve().parent
    report = {"status": "passed", "kind": "correctness-not-performance", "counts": counts,
              "output_digest": digest.hexdigest(), "python": platform.python_version(),
              "unicode": unicodedata.unidata_version, "node": identity,
              "unicode_codepoints_covered_in_blocks": 0x110000,
              "log1p_differences_outside_ordinary_query_range": math_differences,
              "preconstruction_override_checks": overrides,
              "source_sha256": {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
                                for name in ("kernels.mjs", "worker.mjs", "client.py", "verify.py", "unicode-properties.json")},
              "reference_binary_sha256": hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest(),
              "scope": "normal exact builtin inputs; tagged surrogate transport; no production patches",
              "limits": ["not a proof for arbitrary Python callback or concurrent mutation semantics",
                         "JavaScript safe integer limits use Python/C fallback in the adapter"]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
