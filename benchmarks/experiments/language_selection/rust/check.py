"""Run independent existing semantic tests on the Rust-only six-function module."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.build), str(args.python_source)]
    import _language_rust as candidate
    suite = unittest.TestSuite()
    source_names = []
    for filename, cls in (("test_native_backend.py", "NativeLoopEquivalenceTests"),
                          ("test_native_excerpt_backend.py", "NativeLiteralPositionsTests")):
        spec = importlib.util.spec_from_file_location("rust_check_" + filename[:-3], args.repo / "tests" / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.NATIVE = candidate
        test_class = getattr(module, cls)
        # Existing decorators ask whether the baseline C module is installed.
        # The supplied build path is independently checked by importing Rust.
        test_class.__unittest_skip__ = False
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_class))
        source_names.append(filename + ":" + cls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"module": candidate.__file__, "tests": result.testsRun,
                      "success": result.wasSuccessful(), "references": source_names}))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
