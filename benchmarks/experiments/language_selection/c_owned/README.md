# C control for the complete native window

This isolated candidate implements the same larger boundary as `rust-owned-window`.
It is separate from the released C backend and does not edit product code.

| Preserved | Implementation |
|---|---|
| Ordinary-query domain | Unique terms ≤64, hits per term ≤40, hits ≤2560, exact integer-to-double range |
| Source representation | CPython Unicode code points, including lone surrogates |
| Observable mutation | Positions sort in place only after all unsupported-input checks |
| Window rules | Same evidence spans, candidates, unit completeness and linked term order |
| Frequency | Native `log1p` and identical partial-summation correction; no cache |
| Tie order | Coverage, completeness, frequency, negative placement, negative start |
| Adapter/fallback | The exact frozen `rust/window_adapter.py` implementation |

The C implementation uses checked native allocations, native unit/score arrays,
and `qsort` followed by in-place dedup. Rust uses its standard vector allocator
and `sort_unstable` followed by dedup. Both keep the same result ordering and
numeric operations; neither is artificially made slower to force an identical
compiler instruction sequence. Compiler and binary identities are recorded.

```sh
python build.py --native-source /absolute/frozen/src/memory_book \
  --output /absolute/new-build-directory
```

The C flags match the C-table control: `-shared -fPIC -O3 -DNDEBUG -g -fwrapv
-Wall`. Fast-math is disabled. The output module `_language_c_owned` provides
the same three interfaces used by the Rust-owned experiment. Install it with
the shared `window_adapter.install(native, lexical, candidate)` in a fresh
isolated worker; the original C module's other 21 methods remain unchanged.

The shared adapter checks builtin math and the original evidence helper against
frozen source. Ineligible preexisting overrides leave the original backend in
place without calling custom math. A host `log1p` mismatch also preserves the
original backend. A timed experiment must prove real native activation in an
untimed replay and retain all fallback samples in its metrics.

The numeric diagnostic APIs are restricted validation aids for the window's
frequency domain, not general replacements for Python's math error semantics.
