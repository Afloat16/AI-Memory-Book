# Pure Bash ASCII helper experiment

This isolated candidate implements `terms_ascii` and `ascii_tokens` using Bash
builtins, indexed arrays, associative arrays, integer arithmetic, and loops.
It does not invoke Python, C, `awk`, `sed`, or `tr` to compute tokens. The Python
client only frames input, receives output, and compares or measures results.

## Scope and contract

| Item | Preserved behavior or explicit limit |
| --- | --- |
| Input | Exact Python ASCII strings are encoded as integer code points; NUL and DEL survive transport. |
| `terms_ascii` | Split lowercase-to-uppercase boundaries, accept ASCII letters/digits, lowercase uppercase characters, preserve token order and duplicates. |
| `ascii_tokens` | Scan `[a-z0-9]+` without extra case folding; uppercase characters delimit tokens. |
| Query mode | Apply the current frozen ordinary STOP set; exact Boolean only. |
| Process lifetime | One persistent Bash worker receives repeated calls. The ordinary STOP set is loaded once. No query-result cache exists. |
| Unsupported scope | No Unicode lexical helpers, arbitrary stop-container callbacks, full database, ingestion, retrieval, MCP server, or full Shell application. |

These two kernels are a diagnostic screening candidate. Their measurements
cannot establish the performance of a complete Shell rewrite or replace the
project's end-to-end language-selection gate.

## Correctness

Run against the same compiled baseline and captured corpus as the other
experiments:

```sh
python benchmarks/experiments/language_selection/shell/check.py \
  --source /path/to/current/src \
  --inputs benchmarks/experiments/language_selection/javascript/captured-inputs.json \
  --output /path/to/new-shell-correctness.json
```

The checker compares Bash with both the current C helpers and an independent
Python regex reference. It includes all 128 ASCII code points, NUL, DEL,
camel-case/acronym/digit boundaries, duplicate and stop tokens, empty strings,
247 fixed/random texts, both Boolean modes, repeated batches, and every supported
captured ASCII input. It records input, source, native-binary, and result hashes.
The source itself is unchanged by this command.

The local diagnostic run passed **1,062 RPC checks**, including **42 captured
inputs with no omissions**. That result is recorded in
[`correctness-local.json`](correctness-local.json). This is correctness evidence
only. The CI host must rerun it before timing; no performance conclusion is
claimed by this directory.

## Optional isolated measurement

Reserve the same measurement host/CPU window as the parent experiment. This
command refuses to time anything unless `--measure` is explicit:

```sh
python benchmarks/experiments/language_selection/shell/bench.py \
  --source /path/to/current/src \
  --inputs benchmarks/experiments/language_selection/javascript/captured-inputs.json \
  --output /path/to/new-shell-diagnostic.json \
  --measure --rounds 6 --iterations 3 --warmup 1 --cold-starts 3
```

| Arm | Timed boundary |
| --- | --- |
| `current-c` | Existing Python-to-C call and Python result construction in an already-running interpreter. |
| `shell-rpc` | Integer encoding, persistent-worker IPC, actual Bash token scan, and result decoding on every call. |
| `shell-batch` | The scanner really recomputes the same input N times; one frame's encoding, parse, IPC, and decoding are amortized over N calls. This remains an optimistic protocol diagnostic, not a pure kernel timer. |
| Cold worker, separately | Process launch and STOP loading, then first RPC. This is not compared with a C cold-start number. |

All selected captured cases are checked before the first timer starts. Every
timed record is checked again afterward. Six cyclic/alternating rounds balance
the three arms' positions. The output retains individual samples, order,
cohort/phase, case IDs, sinks, and result hashes. Failed runs retain their partial
data and failure status. An explicit `--limit-cases` records each omitted case;
the default uses all supported captured cases. Earlier output files are never
silently replaced. The resolved Bash executable path and binary SHA256 are bound
to the report, and that exact executable starts every worker in the run.

There are no local timing results committed here.

## Integer protocol

All commands and responses are newline-delimited ASCII. Text does not appear
literally in a request, avoiding Bash's inability to store NUL bytes.

| Frame | Meaning |
| --- | --- |
| `READY 1` | Worker version/ready handshake. |
| `S count len cp ... len cp ...` | Load the ordinary stop strings; receive `ACK STOP`. |
| `Q original query len cp ...` | Scan once; `original=1` means `terms_ascii`, `0` means `ascii_tokens`. |
| `R repetitions original query len cp ...` | Repeat the actual scanner; receive the final computed result. |
| `OK count token ...` | Ordered ASCII alphanumeric tokens. |
| `X` / `BYE` | Close the worker. |
| `ERR reason` | Reject malformed, unconfigured, oversized, or non-ASCII input. |

Numeric fields must be canonical nonnegative decimals before Bash arithmetic
uses them. The worker caps text at 1,000,000 code points, batches at 100,000
repetitions, stop count at 10,000, and each stop string at 4,096 code points.
The client removes inherited Bash startup scripts/functions, selects the C
locale, and applies a response timeout. These protocol bounds are part of the
diagnostic domain, not replacements for the product's Python API semantics.
