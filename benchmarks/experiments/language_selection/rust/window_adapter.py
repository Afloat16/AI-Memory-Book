"""Experiment-only runtime registration for the Rust-owned complete window.

It changes one attribute on an isolated imported native module. No source file,
certification flag, regex, SQL, cache, limit or ranking rule is edited. The real
adapter/conversion/guard cost remains inside request timing. Untimed probes may
wrap this function separately; this adapter contains no counters.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import types


FROZEN_TEXT_SOURCE_SHA256 = "b27b2a4992d1530736b502f00d80b6c442ccaca534b16c1eb6a750e31436b6c7"


def _certified_units(lexical, function):
    """Snapshotting an already modified __code__ would certify the mutation.

    Bind eligibility to the frozen source and independently compile its original
    code object without executing it. This setup cost is included in startup.
    """
    try:
        source = Path(lexical.__file__).read_bytes()
        if hashlib.sha256(source).hexdigest() != FROZEN_TEXT_SOURCE_SHA256:
            return False
        module = compile(source, lexical.__file__, "exec", dont_inherit=True, optimize=sys.flags.optimize)
        original = next(value for value in module.co_consts
                        if type(value) is types.CodeType and value.co_name == "_evidence_units")
        return (type(function) is types.FunctionType and function.__globals__ is lexical.__dict__
                and function.__code__ == original)
    except (OSError, SyntaxError, StopIteration, TypeError):
        return False


def install(native, lexical, rust):
    original = native.excerpt_window
    ordinary_units = lexical._evidence_units
    ordinary_code = getattr(ordinary_units, "__code__", None)
    units_certified = _certified_units(lexical, ordinary_units)
    ordinary_log = math.log1p
    ordinary_sum = math.fsum
    if not units_certified or not all(
            type(fn) is type(len) and fn.__module__ == "math" and fn.__name__ == name
            for fn, name in ((ordinary_log, "log1p"), (ordinary_sum, "fsum"))):
        # Installation is optional. Keep the original working backend when a
        # dependency was customized before installation; do not call it here.
        return original
    reference = [ordinary_log(i) for i in range(1, 41)]
    actual = rust.log1p_values(list(range(1, 41)))
    if [struct.pack("!d", x) for x in reference] != [struct.pack("!d", x) for x in actual]:
        return original
    kernel = rust.excerpt_window_owned

    def excerpt_window(text, query, positions, width, evidence_units, log1p, fsum):
        if (not units_certified or evidence_units is not ordinary_units
                or getattr(ordinary_units, "__code__", None) is not ordinary_code
                or log1p is not ordinary_log or fsum is not ordinary_sum
                or not lexical._native_excerpt_window_ready()):
            return original(text, query, positions, width, evidence_units, log1p, fsum)
        value = kernel(text, query, positions, width)
        if value is NotImplemented:
            return original(text, query, positions, width, evidence_units, log1p, fsum)
        return value

    native.excerpt_window = excerpt_window
    return original
