# Isolated Rust language candidates

These files are experiments. They do not replace a released backend, modify
product sources, or establish a recommendation without the paired end-to-end
measurements performed by the parent evaluator.

| Candidate | Changed boundary | Kept identical |
|---|---|---|
| `rust_same_boundary` | Six current C loops translated to Rust through `pyo3-ffi` | CPython strings/objects, code-point indexes (including lone surrogates), callbacks, stop membership, local cache, per-term 40-match limit, exceptions and all other 16 C entry points |
| `rust-table-fold` | Per-codepoint Unicode callbacks replaced by a frozen complete mapping and two native passes | Exact Python UCD NFKD → casefold → category `Mn` removal; shared C-table guard; source coordinates; custom callable fallback |
| `rust-owned-window` | Complete ordinary-query evidence scan, window candidates, numeric scores and rendering | Same candidates, stable hit sort, term insertion/deletion order, complete-unit masks, frequency/placement tie order and code-point slices |

The table variant is compared with **the same table and allocation strategy in
C**. Its gain must not be reported as an inherent Rust language gain. The owned
window changes the representation of an entire computation stage. A win over
the current C implementation would not prove that an equally redesigned C
implementation could not match it.

## Build

Use the experiment's pinned Rust toolchain, Python interpreter, `Cargo.lock`,
and `pyo3-ffi` lockfile. Set `PYO3_PYTHON` to that exact interpreter and compile
release mode. This candidate assumes GIL-enabled CPython and a Unix host with
the matching CPython development headers.

```sh
python build.py --package-source /absolute/frozen/src/memory_book \
  --output-dir /absolute/new-output --cargo /absolute/cargo
```

The output contains the independent `_language_rust` module and a combined
`_native` module. The generated `link.c` includes unchanged product C source and
changes exactly six actual function pointers before its ordinary module
initialization. The original module state and all 22 API names remain intact.
It does not modify Python certification flags or forge function metadata.

Read the untimed `language_rust_manifest()` C export with `ctypes.PyDLL` and
`restype=ctypes.py_object` to verify all 22 original/effective addresses and
flags. Only the declared six entries may differ. A build manifest records
source hashes, commands, compiler flags, binary hashes and byte sizes.

The complete window module is separately enabled by
`--features owned-window`. Import its `_language_rust` module and use
`window_adapter.install(native, lexical, rust)` in an isolated worker. The
adapter preserves custom dependency calls through the original C function;
unsupported values return before in-place position sorting. An ordinary query
has unique query terms (at most 64), at most 40 positions per term and a maximum
position sum exactly representable as a binary64 integer. Other input domains
retain the original C path. Host `log1p(1..40)` is checked bit for bit at setup,
and no result lookup table or frequency cache is installed.

The Unicode table archive is built with `cargo build --release --locked
--features table`. The sibling `c_table/build.py --rust-library ...` links it
through the identical guard used by the C-table control. That guard validates
the exact original Unicode callables and interpreter UCD version. The Rust
table assumes its C caller has already validated the exact string argument;
all embedded table offsets/ranges/code points are checked at compile time.

## Verification

`check.py` runs the existing independent Python reference tests against the
Rust-only six-function module. They include all Unicode code points, all ASCII
pairs, source coordinates, custom stop membership/callback exceptions, identity
preservation for source mappings, and empty literals.

`check_window.py` checks the owned stage against the released C window, validates
frequency summation bit for bit, compares in-place sorting, and checks that
unsupported inputs are unchanged. The shared C-table checker exhaustively
compares all code points and contextual sequences for both C and Rust.

End-to-end evidence must additionally confirm unchanged indexing/page IDs and
full recall/MCP payloads, record actual variant dispatch, retain fallback
counts, and include the adapter's cost. These checks do not certify every
platform, free-threaded Python, adversarial allocation failure, or the
performance of an unwritten full Rust application.
