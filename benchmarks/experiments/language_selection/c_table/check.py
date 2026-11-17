"""Correctness-only differential checks for either shared-shim table variant."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unicodedata


def outcome(function, arguments):
    try:
        return ["return", function(*arguments)]
    except Exception as error:
        return ["error", type(error).__name__, str(error)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--exhaustive", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve()), str(args.build.resolve())]
    native = importlib.import_module("memory_book._native")
    control = importlib.import_module("_language_c_table")
    old = native.fold_excerpt_source
    new = control.fold_excerpt_source
    metadata = control.describe()
    assert metadata["table_enabled"], metadata
    normalizer, category = unicodedata.normalize, unicodedata.category

    checked = 0
    digest = hashlib.sha256()

    def equal(text):
        nonlocal checked
        expected = old(text, normalizer, category)
        actual = new(text, normalizer, category)
        assert actual == expected, (repr(text), expected, actual)
        assert type(actual) is tuple and type(actual[0]) is str and type(actual[1]) is list
        assert len(actual[0]) == len(actual[1])
        digest.update(json.dumps([text, actual], ensure_ascii=True, separators=(",", ":")).encode())
        checked += 1

    fixtures = ["", "ASCII lower UPPER CamelCase\x00", "Straße café cafe\u0301 Å🙂",
                "中\ud800\udfff🙂\U00010000", "\u0301\u034f\ufe0f", "\ufdfa\ufb03\u00df",
                "\u1100\u1161\u11a8\uac01", "a\u0315\u0300A\u0327\u0301", "\x00\r\n\x85\u2028\u2029"]
    for text in fixtures:
        equal(text)
        equal(text * 257)
    rng = random.Random(761137)
    special = [0, 65, 90, 97, 127, 128, 0xdf, 0xe9, 0x300, 0x315, 0x327,
               0x34f, 0x4e00, 0xac00, 0xd800, 0xdbff, 0xdc00, 0xdfff, 0xfdfa, 0xfb03, 0x10ffff]
    for _ in range(1200):
        equal("".join(chr(rng.choice(special) if rng.random() < .7 else rng.randrange(0x110000))
                      for _ in range(rng.randrange(256))))
    if args.exhaustive:
        for code_point in range(0x110000):
            equal(chr(code_point))

    class CustomString(str):
        pass

    invalid = [(), ("x",), ("x", normalizer), ("x", normalizer, category, 1),
               (None, normalizer, category), (CustomString("é"), normalizer, category),
               ("é", None, category), ("é", normalizer, None),
               ("é", lambda form, character: 7, category),
               ("é", normalizer, lambda character: 7)]
    for arguments in invalid:
        assert outcome(old, arguments) == outcome(new, arguments), repr(arguments)

    custom_cases = 0
    for text in ("ééA\u0301🙂é", "\ud800\ufb03\ufb03\u0301", ""):
        calls = []
        def custom_normalize(form, character):
            calls.append(["normalize", form, character])
            return normalizer(form, character)
        def custom_category(character):
            calls.append(["category", character])
            return category(character)
        expected = old(text, custom_normalize, custom_category)
        expected_calls = list(calls)
        calls.clear()
        actual = new(text, custom_normalize, custom_category)
        assert actual == expected and calls == expected_calls
        custom_cases += 1

    before = {name: getattr(native, name) for name in dir(native) if not name.startswith("_")}
    assert control.install_into(native) is old
    assert all(getattr(native, name) is value for name, value in before.items() if name != "fold_excerpt_source")
    assert native.fold_excerpt_source is new
    from memory_book import text
    assert text._native_excerpt_window_ready(), "Installing table fold changed unrelated native window dispatch"
    for value in fixtures:
        assert text._fold_excerpt_source(value) == old(value, normalizer, category)

    child_code = r'''
import importlib,json,sys,unicodedata as u
sys.path[:0] = json.loads(sys.argv[1])
kind = sys.argv[2]
if kind == "normalizer":
    u.normalize = lambda form, value: value
elif kind == "category":
    u.category = lambda value: "Ll"
else:
    u.unidata_version = "0.0.0"
import memory_book._native as native
import _language_c_table as control
assert not control.describe()["table_enabled"]
assert control.fold_excerpt_source("é\u0301",u.normalize,u.category) == native.fold_excerpt_source("é\u0301",u.normalize,u.category)
print(json.dumps({"preimport_override":kind,"passed":True}))
'''
    subprocess_results = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for kind in ("normalizer", "category", "version"):
        run = subprocess.run([sys.executable, "-c", child_code,
                              json.dumps([str(args.source.resolve()), str(args.build.resolve())]), kind],
                             env=env, check=True, capture_output=True, text=True)
        subprocess_results.append(json.loads(run.stdout))
    report = {
        "status": "passed", "candidate": metadata,
        "normal_input_cases": checked, "all_code_points_checked": args.exhaustive,
        "single_code_point_count": 0x110000 if args.exhaustive else 0,
        "random_sequence_count": 1200, "invalid_signature_cases": len(invalid),
        "custom_callable_cases_with_call_order": custom_cases,
        "preimport_override_checks": subprocess_results,
        "other_21_native_functions_unchanged": len(before) == 22,
        "native_excerpt_window_guard_after_install": text._native_excerpt_window_ready(),
        "output_sha256": digest.hexdigest(),
        "reference_binary_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "candidate_binary_sha256": hashlib.sha256(Path(control.__file__).read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timing": "No performance measurements. Functional differential checks only.",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
