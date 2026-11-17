# Isolated shared-table C / Rust fold controls

These are experiment inputs, not product changes. The original product source,
build configuration, public wrappers, and main branch are unchanged.

The existing C implementation calls Python's Unicode normalization and category
functions for each distinct character within an invocation. The table candidates
replace those callbacks with one immutable, version-bound Unicode table and
preallocate the exact output string and list. **This is a change in execution and
data organization. A win against the original C helper would not by itself be a
Rust language win.** The C and Rust table variants use the same input bytes,
lookup layout, two-pass output sizing, allocation strategy, and shared C wrapper.

## Reproduce

Use the same Python interpreter for table generation, the baseline native build,
both candidate builds, and checks. The common generator and binary live in the
sibling `rust/` experiment directory.

```sh
python benchmarks/experiments/language_selection/c_table/build.py \
  --native-source src/memory_book/_native.c \
  --output benchmarks/experiments/language_selection/c_table/build/c

python benchmarks/experiments/language_selection/c_table/build.py \
  --native-source src/memory_book/_native.c \
  --rust-library benchmarks/experiments/language_selection/rust/target/release/liblanguage_rust.a \
  --output benchmarks/experiments/language_selection/c_table/build/rust

python benchmarks/experiments/language_selection/c_table/check.py \
  --source /absolute/path/to/frozen/baseline/src \
  --build benchmarks/experiments/language_selection/c_table/build/c \
  --exhaustive --report benchmarks/experiments/language_selection/c_table/build/c/correctness.json
```

Run the checker against `build/rust` as well. The Python module name is
`_language_c_table` for both variants; import from the selected directory in a
fresh process. `describe()` distinguishes the implementation and table identity.

## Experimental installation boundary

Import `memory_book._native`, then the selected `_language_c_table`, and call
`control.install_into(native)` before importing `memory_book.text` or
`MemoryBook`. Only the `fold_excerpt_source` attribute is replaced; the other 21
native functions retain their original objects. The replacement remains honestly
bound to its own `_language_c_table` module. No readiness or certification flags
are written. The installer returns the original function for explicit inspection
or restoration outside a measured worker.

The shared wrapper checks the original argument types and callable requirements.
It accepts the fast table path only for the original built-in `unicodedata`
functions bound to the imported Unicode module, the identical stored callable
objects, and the table's Unicode database version. Custom callbacks and a
different Unicode version use the original C fold helper included from the
frozen source. Its callback order, invocation-local memoization, exceptions,
surrogate handling, and return shape remain available for those cases.

The table supports all Python Unicode code points, including isolated surrogates.
It preserves the existing per-character NFKD, casefold, and category-Mn removal
order. Whole-string normalization is deliberately not substituted. Expansion
indices share one Python integer per original input position as in the reference.
No query-result or per-text cache is added. The version-bound immutable table is
new retained data and its size, startup cost, and process memory must be reported.

The original C fallback is included as a private compilation dependency.
Unreferenced original functions and its private initializer are removed by
optimization; this module does not initialize a second copy of the production
extension. The build manifest binds all reference C/header files, the common
table, generated header, control source, Rust static library when selected,
compiler command, and output binary.

## Limits

- These controls replace one measured stage. They are not full C or Rust engines.
- The guards establish the ordinary CPython dependency contract used by this
  experiment, not cryptographic authentication of arbitrary hostile extensions.
- Correctness checks include every single code point when requested, randomized
  sequences, expansion/empty/surrogate cases, custom callback call order,
  signature failures, pre-import overrides, and unchanged unrelated dispatch.
- Performance must be measured separately after probes/checkers are absent.
  Building or passing this checker is not evidence of an execution-time gain.
- The C and Rust table variants must be compared directly as well as against the
  existing C implementation. Their result must be reported separately from a
  same-interface Rust translation retaining Python callbacks.
