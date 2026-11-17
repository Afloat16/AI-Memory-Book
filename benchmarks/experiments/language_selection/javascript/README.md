# JavaScript / TypeScript language experiment

This directory is an isolated candidate for the frozen AI-Memory-Book baseline.
It does not install a new product backend or change production sources. Performance
and adoption conclusions require the separately audited host experiment.

## Implemented boundaries

| Candidate | Work inside Node | Comparison scope |
|---|---|---|
| Small helpers | ASCII terms, ASCII tokens, context allocation | Same inputs and outputs, including Python page-object identity restored by result index |
| Unicode tokens | Python-compatible alphanumeric classification and code-point scanning | Frozen Python Unicode data; Node's different Unicode database is not substituted |
| Literal positions | Non-overlapping literal matching, capped at 40 hits per term | Exact Python code-point coordinates |
| Owned excerpt window | Candidate construction, evidence masks, scoring, selection and rendering | Complete pure computation stage; Python callbacks use the original C fallback |
| Coarse excerpt selection | Literal matching and the owned window | Kernel experiment only; normalization remains outside this boundary |
| Table fold | Shared immutable Unicode table and two-pass output | Data and execution organization control, not evidence of a language-only advantage |

TypeScript can describe these interfaces, but erasing its type annotations produces
the same JavaScript runtime work. This experiment evaluates the Node runtime; it
does not invent a separate TypeScript performance number. Shell can orchestrate
builds and tests but has no demonstrated equivalent computation advantage here.

## Compatibility safeguards

Python strings are indexed by Unicode code point. Ordinary scalar strings travel
as JSON strings; explicit surrogate code points use a tagged code-point sequence
so a literal surrogate pair cannot be confused with one astral character.
Matching offsets, empty-needle advancement, budgets and slicing preserve the
Python conventions. Original Python source-map objects never cross the process
boundary.

The owned stage preserves insertion order when counts disappear and reappear,
stable candidate ordering, integer-domain checks and the positive-value
compensated summation used for scores. The measured Node/Python runtime pair
agreed bit for bit for log1p frequencies 1 through 40. There were one-ULP
differences at 175 and 184 when checking the larger 1..2560 domain, so that larger
domain is not certified. Calls outside the ordinary domain use the original
native implementation, with dispatch counts recorded.

Callback certification checks built-in callable identity, module and name. The
evidence callback is additionally checked against compiled bytes of the frozen
text.py source and rechecked before use. A pre-existing or later replacement of
its __code__ must not become an ordinary Node fast path. A lock serializes each
persistent JSONL request/response exchange. This is not a complete certification
of every possible concurrency or interruption condition.

## Drivers and evidence

| File | Purpose |
|---|---|
| verify.py | Differential helper, Unicode, numeric and boundary checks |
| check_window_guards.py | Original, pre-construction and post-construction evidence-code regressions |
| capture_inputs.py | Captures fixed real-corpus inputs without changing readiness guards |
| captured-inputs.json | Frozen 179-case helper sample spanning ordinary and Unicode-stress inputs |
| kernel_bench.py | Serial native-call, Node-internal and Python-to-Node bridge measurements |
| client.py / worker.mjs | Persistent bridge and runtime identity |
| kernels.mjs | Node computation kernels |
| unicode-properties.json | Frozen Python character-property ranges |

The retained local predecessor correctness report contains 75,199 checks and
covers all 1,114,112 Unicode code points in blocks. These are separate counting
units. It records no performance conclusion. The subsequent callback-code
certificate regression changed only client-side eligibility; the kernel and
worker bytes remained unchanged.

The prior execution environment was lost before all experiment artifacts were
committed. The restored client.py and check_window_guards.py were reconstructed
with exact SHA-256 matches to their locally checked versions. This README is a
new reconstruction, not a claim that the missing earlier README was recovered
byte for byte. Remote CI must run correctness again for the committed complete
source set before formal timings.

## Measuring the relevant costs

The driver accepts --source, --inputs, --output and optional repeated
--native-backend LABEL=DIR=MODULE arguments. Its defaults are six serial rounds,
64 timed calls per input and 256 warmup calls per input. Native modules with the
same module name must run in separate processes. A missing native helper is an
explicit omission, never a silently substituted C measurement.

| Measurement | Included | Excluded |
|---|---|---|
| current-c / native candidate | Python-to-native invocation and result creation | Corpus retrieval and MCP |
| node-kernel | Computation inside the persistent Node process | JSON, IPC and Python reconstruction |
| node-bridge | Serialization, IPC, Node computation and Python reconstruction | Corpus retrieval and MCP |
| Formal direct / MCP matrix | Actual retrieval, budgets, source coordinates, database and optional bridge overhead | Model answer generation |

Window-only benchmarks restore the incoming hit list each iteration because the
current C entry sorts it in place. Coarse selection naturally creates new hits.
There is no hidden worker result cache. Both favorable and unfavorable results
must be reported. IPC overhead alone cannot establish the performance of a
complete Node application, and a fast isolated helper cannot establish a whole
application speedup.

The formal host analysis compares all complete outputs and database snapshots,
audits actual dispatch, source and binary identities, and uses paired rounds for
uncertainty. Node child RSS and startup are retained. No benchmark has yet
established that rewriting the whole application in JavaScript or TypeScript is
the best choice.
