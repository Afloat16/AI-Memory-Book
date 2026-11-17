"""Experiment-only runtime registration for the Rust-owned complete window.

It changes one attribute on an isolated imported native module. No source file,
certification flag, regex, SQL, cache, limit or ranking rule is edited. The real
adapter/conversion/guard cost remains inside request timing. Untimed probes may
wrap this function separately; this adapter contains no counters.
"""
from __future__ import annotations

import math
import struct


def install(native, lexical, rust):
    original = native.excerpt_window
    ordinary_units = lexical._evidence_units
    ordinary_code = ordinary_units.__code__
    ordinary_log = math.log1p
    ordinary_sum = math.fsum
    if not all(type(fn) is type(len) and fn.__module__ == "math" and fn.__name__ == name
               for fn, name in ((ordinary_log, "log1p"), (ordinary_sum, "fsum"))):
        raise RuntimeError("Rust-owned experiment requires the original builtin math dependencies")
    reference = [ordinary_log(i) for i in range(1, 41)]
    actual = rust.log1p_values(list(range(1, 41)))
    if [struct.pack("!d", x) for x in reference] != [struct.pack("!d", x) for x in actual]:
        raise RuntimeError("Host libm log1p differs inside the accepted frequency domain")
    kernel = rust.excerpt_window_owned

    def excerpt_window(text, query, positions, width, evidence_units, log1p, fsum):
        if (evidence_units is not ordinary_units or ordinary_units.__code__ is not ordinary_code
                or log1p is not ordinary_log or fsum is not ordinary_sum):
            return original(text, query, positions, width, evidence_units, log1p, fsum)
        value = kernel(text, query, positions, width)
        if value is NotImplemented:
            return original(text, query, positions, width, evidence_units, log1p, fsum)
        return value

    native.excerpt_window = excerpt_window
    return original
