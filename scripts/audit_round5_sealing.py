"""Independently audit the bounded ASCII separator certificate without timing.

This reproduces the artificial cases used by the independent reviewer. It does
not load a benchmark corpus, change retrieval, or measure elapsed time. Both
token-ID equalities must hold, not merely the proposed count difference.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EXPECTED_PATTERNS = {
    "cl100k_base": "f021c3d976978e62ee64cdad150cc3405c2e3d6e3b40407850bb9e8d9eb65899",
    "o200k_base": "2d1b8dc11e89af71459b36004f698ab3693f59fd84f63e8ec2b49564ab857420",
}
# An independent regex formulation of the stated certificate, rather than the
# implementation's reverse scan. This also detects unexpectedly skipped cases.
ELIGIBLE = re.compile(r"[A-Za-z0-9]([\x00-\x2f\x3a-\x40\x5b-\x60\x7b-\x7f]{0,64})\Z")


def cases():
    rng = random.Random(109752)
    alphabet = [chr(c) for c in range(128)
                if not (48 <= c <= 57 or 65 <= c <= 90 or 97 <= c <= 122)]
    prefixes = ["a", "A", "1234567", "中文a", "e\u0301A", "I'll", "we're",
                "\U0001f469\u200d\U0001f4bb9", "\u0130\u017fK",
                "[p] scope\n<|endoftext|", "\u2028\u0085\r\n9"]
    values = [prefix + suffix for prefix, suffix in itertools.product(prefixes, alphabet)]
    values += [rng.choice(prefixes) + "".join(suffix)
               for suffix in itertools.product(alphabet, repeat=2)]
    values += [rng.choice(prefixes) + "".join(rng.choices(alphabet, k=length))
               for length in (0, 3, 7, 31, 63, 64) for _ in range(100)]
    values += [prefix + suffix for prefix, suffix in itertools.product(prefixes,
        ["\r\n/", "/\r\n", "\r /\n", "\t" * 64, " " * 64, "'", "...", "!!!",
         "\x00\x7f", "\x1c\x1d\x1e\x1f"])]
    return values


def audit():
    import tiktoken
    from memory_book import token_budget

    source = ROOT / "src/memory_book/token_budget.py"
    assert Path(token_budget.__file__).resolve() == source.resolve(), "Wrong runtime source"
    assert tiktoken.__version__ == "0.12.0", "Audit binds tiktoken 0.12.0"
    generated = cases()
    fallback_examples = ("a\u0301", "a\u00a0", "a\u2028", "a\u0085", "a\ud800",
                         "a" + " " * 65, "中文", " " * 100)
    rows = []
    for name, expected_pattern in EXPECTED_PATTERNS.items():
        counter = token_budget.TokenCounter(name)
        assert token_budget._can_seal_blocks(counter), "Ordinary encoder certificate unavailable"
        encoding = counter.encoding
        pattern_sha = hashlib.sha256(encoding._pat_str.encode()).hexdigest()
        assert pattern_sha == expected_pattern, "Tokenizer pattern differs from audit binding"
        pairs, fallbacks = 0, 0
        for index, text in enumerate(generated):
            suffix = token_budget._ascii_sealing_suffix(text)
            expected = ELIGIBLE.search(text)
            assert suffix == (expected[1] if expected else None), (name, index, "certificate")
            if suffix is None:
                fallbacks += 1
                continue
            prefix = text[:-len(suffix)] if suffix else text
            assert encoding.encode_ordinary(text) == (
                encoding.encode_ordinary(prefix) + encoding.encode_ordinary(suffix)
            ), (name, index, "before separator")
            assert encoding.encode_ordinary(text + "\n\n") == (
                encoding.encode_ordinary(prefix) + encoding.encode_ordinary(suffix + "\n\n")
            ), (name, index, "after separator")
            pairs += 1
        for index, text in enumerate(fallback_examples):
            assert token_budget._ascii_sealing_suffix(text) is None, (name, index, "fallback")
        assert (pairs, fallbacks) == (5784, 8), "Registered fixture coverage changed"
        rows.append({"name": name, "pattern_sha256": pattern_sha,
                     "boundary_pairs": pairs, "bounded_fallbacks": fallbacks,
                     "explicit_unicode_or_overlong_fallbacks": len(fallback_examples),
                     "token_id_equalities": 2 * pairs})
    return {
        "schema_version": 1,
        "status": "passed",
        "scope": "Artificial non-timing boundary regression; no benchmark corpus or performance claim.",
        "tokenizer_version": tiktoken.__version__,
        "token_budget_source": "src/memory_book/token_budget.py",
        "token_budget_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "audit_script": "scripts/audit_round5_sealing.py",
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "random_seed": 109752,
        "generated_cases_per_tokenizer": len(generated),
        "boundary_pairs": sum(row["boundary_pairs"] for row in rows),
        "bounded_fallbacks": sum(row["bounded_fallbacks"] for row in rows),
        "explicit_unicode_or_overlong_fallbacks": sum(row["explicit_unicode_or_overlong_fallbacks"] for row in rows),
        "token_id_equalities": sum(row["token_id_equalities"] for row in rows),
        "equations": ["encode(block) = encode(prefix) + encode(suffix)",
                      "encode(block + LF + LF) = encode(prefix) + encode(suffix + LF + LF)"],
        "certificate_reason": "The ASCII tail has no letters or digits, so it cannot extend either fixed pattern's letter, number, or contraction piece. All remaining changes after appending LF are confined to that tail.",
        "tokenizers": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/reports/round5-sealing-independent-audit.json")
    args = parser.parse_args()
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "boundary_pairs": report["boundary_pairs"],
                      "bounded_fallbacks": report["bounded_fallbacks"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
