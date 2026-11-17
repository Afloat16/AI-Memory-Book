"""Check shared C/Rust adapter eligibility without changing product files."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rust"))
import window_adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--module", choices=["_language_c_owned", "_language_rust"], required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new guard report")
    sys.path.insert(0, str(args.python_source))
    from memory_book import _native as native, text as lexical
    spec = importlib.util.spec_from_file_location(args.module, args.binary)
    kernel_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel_module)
    original_native = native.excerpt_window
    value = "First alpha. Needle beta. Last gamma."
    operation = lambda: lexical.excerpt(value, "", 17, prepared_terms=["needle"])
    cases = []
    try:
        for name in ("log1p", "fsum"):
            ordinary = getattr(math, name)
            calls = []

            def custom(*arguments):
                if name == "fsum":
                    arguments = (tuple(arguments[0]),)
                calls.append(arguments)
                return ordinary(*arguments)

            setattr(math, name, custom)
            try:
                returned = window_adapter.install(native, lexical, kernel_module)
                assert returned is original_native and native.excerpt_window is original_native
                assert calls == [], "Installation must not call a custom math dependency"
                actual = operation()
                actual_calls = list(calls)
                calls.clear()
                ordinary_backend = lexical._NATIVE
                lexical._NATIVE = None
                try:
                    expected = operation()
                finally:
                    lexical._NATIVE = ordinary_backend
                assert actual == expected and calls == actual_calls and calls
                cases.append({"case": "preinstall_" + name, "installation_custom_calls": 0,
                              "product_custom_calls": len(calls), "original_method_preserved": True})
            finally:
                setattr(math, name, ordinary)

        mismatches = []

        def different_log(values):
            result = kernel_module.log1p_values(values)
            result[0] = math.nextafter(result[0], math.inf)
            mismatches.append(True)
            return result

        proxy = types.SimpleNamespace(log1p_values=different_log,
                                      excerpt_window_owned=kernel_module.excerpt_window_owned)
        returned = window_adapter.install(native, lexical, proxy)
        assert returned is original_native and native.excerpt_window is original_native and mismatches == [True]
        cases.append({"case": "preflight_log1p_difference", "original_method_preserved": True})

        ordinary_units = lexical._evidence_units
        original_code = ordinary_units.__code__
        had_trace = "_owned_guard_calls" in lexical.__dict__
        old_trace = lexical.__dict__.get("_owned_guard_calls")
        lexical.__dict__["_owned_guard_calls"] = []

        def changed_units(text, width):
            _owned_guard_calls.append((text, width))
            return []

        try:
            ordinary_units.__code__ = changed_units.__code__
            returned = window_adapter.install(native, lexical, kernel_module)
            assert returned is original_native and native.excerpt_window is original_native
            assert lexical.__dict__["_owned_guard_calls"] == []
            arguments = (value, ["needle"], [(13, "needle")], 15, ordinary_units, math.log1p, math.fsum)
            actual = native.excerpt_window(*arguments)
            assert len(lexical.__dict__["_owned_guard_calls"]) == 1
            expected = original_native(value, ["needle"], [(13, "needle")], 15, ordinary_units, math.log1p, math.fsum)
            assert actual == expected and len(lexical.__dict__["_owned_guard_calls"]) == 2
            cases.append({"case": "preinstall_helper_code", "original_method_preserved": True,
                          "callback_per_call": 1, "output": actual})
        finally:
            ordinary_units.__code__ = original_code
            if had_trace:
                lexical.__dict__["_owned_guard_calls"] = old_trace
            else:
                lexical.__dict__.pop("_owned_guard_calls", None)

        kernel_calls = []

        def observed(*arguments):
            result = kernel_module.excerpt_window_owned(*arguments)
            kernel_calls.append(result is not NotImplemented)
            return result

        expected = operation()
        proxy = types.SimpleNamespace(log1p_values=kernel_module.log1p_values, excerpt_window_owned=observed)
        returned = window_adapter.install(native, lexical, proxy)
        assert returned is original_native and native.excerpt_window is not original_native
        assert lexical._native_excerpt_window_ready()
        assert operation() == expected and kernel_calls == [True]
        cases.append({"case": "ordinary_activation", "kernel_completed": 1, "window_ready": True})
    finally:
        native.excerpt_window = original_native
    report = {
        "candidate_module": args.module, "passed": True, "cases": cases,
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(Path(window_adapter.__file__).read_bytes()).hexdigest(),
        "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "note": "All overrides are confined to this disposable process. No product files or certification flags changed.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
