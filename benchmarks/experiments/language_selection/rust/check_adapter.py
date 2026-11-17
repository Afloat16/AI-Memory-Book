"""Exercise existing public/custom-dependency tests with the real Rust adapter."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from window_adapter import install


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new verification output")
    sys.path.insert(0, str(args.python_source))
    from memory_book import _native as native, text as lexical
    spec = importlib.util.spec_from_file_location("_language_rust", args.binary)
    rust = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rust)
    original_methods = {name: getattr(native,name) for name in dir(native) if not name.startswith("_")}
    original_kernel = rust.excerpt_window_owned
    calls = Counter()

    def observed(*arguments):
        result = original_kernel(*arguments)
        calls["unsupported" if result is NotImplemented else "rust_completed"] += 1
        return result

    rust.excerpt_window_owned = observed
    install(native, lexical, rust)
    changed = [name for name,value in original_methods.items() if getattr(native,name) is not value]
    assert changed == ["excerpt_window"]
    assert lexical._native_excerpt_window_ready()
    spec = importlib.util.spec_from_file_location("owned_window_tests", args.repo / "tests/test_native_window_backend.py")
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert calls["rust_completed"] > 0
    report = {
        "candidate": "rust-owned-window-adapter", "passed": result.wasSuccessful(),
        "tests": result.testsRun, "skipped": len(result.skipped), "calls": dict(calls),
        "changed_method_names": changed, "remaining_methods_preserve_identity": len(original_methods)-1,
        "window_ready_after_install": lexical._native_excerpt_window_ready(),
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(Path(__file__).with_name("window_adapter.py").read_bytes()).hexdigest(),
        "test_source_sha256": hashlib.sha256((args.repo / "tests/test_native_window_backend.py").read_bytes()).hexdigest(),
        "note": "Kernel probe exists only in this correctness process; timing uses a fresh uninstrumented process.",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
