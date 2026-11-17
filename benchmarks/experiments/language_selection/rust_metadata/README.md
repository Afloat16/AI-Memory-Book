# Bounded candidate metadata: complete Rust/C method experiment

This candidate translates the ordinary execution of
`MemoryBook._bounded_candidate_metadata` into Rust. The independent C control is
in `../c_metadata/`; both use the same registration adapter, input domain, SQL
continuations, and correctness driver. Product source and the previously frozen
eight-candidate experiment are unchanged by these files.

## Why this boundary

The existing development profile identifies candidate construction and directory
metadata validation as appreciable remaining Python work. This experiment covers
the complete bounded-metadata method: its guards, relevance floor and retained
set, request-local carried metadata or original light query, stable directory
pair construction, original directory query, validation, in-place candidate
updates, and ordered result construction. It does not treat the six earlier
Rust kernels as a representative test of the whole Python implementation.

SQL is still executed through the same Python SQLite connection API. This is a
larger native method inside the existing architecture, not an independent Rust
server or a different database implementation. It does not measure removing
CPython from SQLite row materialization, MCP, or the complete request pipeline.

## Shared contract

```python
native.bounded_metadata(book, rows, relevance, count, env)
adapter.install(store_module, native_module) -> bool
```

| Part | Rule |
| --- | --- |
| Native result | The original ordered dictionary or `None`. `NotImplemented` is permitted only before any SQL or candidate mutation. |
| Fresh candidate domain | Exact ordinary `MemoryBook`, SQLite connection, dictionary or certified `_RecallCandidates`; exact string keys, exact float relevance, exact positive integer count, and candidate dictionaries with exactly `rid`, `id`, `rank` and an exact integer `rid`. |
| Unsupported entry | The shared wrapper calls the original Python method exactly once. Already populated or customized dictionaries retain their original behavior. |
| SQL | Original statement text, bound parameter order, number and position of calls, and existing read snapshot are retained. The second statement reads `book.db` again. |
| Carried metadata | Preserve the original `dict_values` live view; do not freeze its contents across SQL callbacks. |
| Ranking bound | Sort finite scores only to obtain the same kth floor; apply the original `value * 1.15 >= floor` test. Candidate and output ordering remain the original dictionary order. |
| In-place updates | Preserve candidate object identity. Fresh rows avoid changing the evaluation order of overwritten objects with custom finalizers. |
| SQL callback customization | Continue from the exact original Python statements after the already completed query. Never rerun the method or repeat SQL. |
| Dependency authentication | Freeze the store source digest and original method code; authenticate builtins, ordinary class slots and dictionaries, cache objects, and `math.isfinite`. A preinstallation replacement is not accepted as the original implementation. |

`env` contains `store`, `ordinary_ready`, `after_light`,
`after_directories`, and the ordinary cache type. The shared adapter compiles the
two continuations from the exact frozen method AST and binds them to the original
module's live globals. A callback deleting or replacing a previously used
dependency causes the guard to return false without invoking a module getter;
the appropriate continuation then keeps the original remaining behavior.

The wrapper function is named `bounded_metadata_wrapper`. Its local `result`
allows an untimed `sys.setprofile` observer to distinguish native completion from
entry fallback. The module entry itself is an ordinary real C-ABI builtin, so
`c_call` observations prove that the compiled implementation was actually called.
All such observers must be absent from timed runs.

## Build and verify

The toolchain and Python dependencies must be the same frozen versions as the
parent experiment. Use a new output directory each time:

```sh
python benchmarks/experiments/language_selection/rust_metadata/build.py \
  --python-source /path/to/current/src \
  --output /path/to/new-rust-metadata-build

python benchmarks/experiments/language_selection/rust_metadata/check.py \
  --python-source /path/to/current/src \
  --binary /path/to/new-rust-metadata-build/_language_rust_metadata.cpython-312-x86_64-linux-gnu.so \
  --module _language_rust_metadata \
  --locomo /path/to/frozen/locomo10.json \
  --output /path/to/new-rust-metadata-correctness.json
```

For the C control, pass its binary and `--module _language_c_metadata` to the
same checker. `--locomo` is optional; the synthetic development corpus always
runs. Builds and reports refuse to overwrite earlier evidence. Build manifests
bind the compiler, dependency lock, source, adapter, store, and binary hashes.

## Correctness coverage

The driver runs the existing 13 C4 regression tests, 128 direct differential
cases, 11 SQL callback scenarios, and 13 preinstallation override guards. It
compares SQL traces, ordered returns, in-place rows, candidate identity, exception
type/arguments, and partial mutation. Callback scenarios include switching the
connection between queries, changing the live carried metadata, replacing a row
class or update method, replacing or deleting module dependencies, and changing
the row factory. Real synthetic/public corpus replays compare the full recall
payload and require positive compiled-native and successful-pruning counts.

The checker uses no performance timers. Its results establish compatibility and
activation only. Selection or adoption still requires the separate frozen
end-to-end measurement against current Python/C and the matched C control.
