# Historical memory attribution: registered diagnostic

## Status

The [round-five resource plan](../benchmarks/experiments/round5-resource-plan.json)
is prepared for its first registered hosted execution. No new resource result is
claimed at this checkpoint. The diagnostic compares the already published
v0.3.1 and v0.3.2 sources on old round-four data; it does not measure a v0.3.3
candidate or introduce a new quality claim.

## What the existing evidence establishes

The source-free summaries in
[`round4-comparison-43363060062-1`](../benchmarks/results/round4-comparison-43363060062-1/)
retain these observations:

| Metric | v0.3.1 | v0.3.2 C2 | Change |
|---|---:|---:|---:|
| Native worker whole-process high-water RSS | 654.98 MiB | 666.20 MiB | +1.71% |
| Native query tree RSS | 535.88 MiB | 541.79 MiB | +1.10% |
| Native finalization tree RSS | 655.16 MiB | 1,107.09 MiB | +68.98% |
| Component worker whole-process high-water RSS | 646.48 MiB | 643.49 MiB | −0.46% |
| Component query tree RSS | 529.77 MiB | 524.91 MiB | −0.92% |
| Component setup tree RSS | 548.65 MiB | 943.53 MiB | +71.97% |
| Component finalization tree RSS | 1,067.34 MiB | 1,061.41 MiB | −0.55% |

The affected setup/finalization phases observed two processes, whereas lexical
query phases observed one. C2's two adverse tree peaks exceed its corresponding
worker's whole-run high-water RSS by about 300 MiB and 441 MiB. These numbers
cannot be interpreted as an equally large increase in Book's own allocation.
They also cannot identify the child present at either peak: the old sampler
retained maxima/counts, not per-PID traces or phase-aligned worker high water.

Source inspection identifies substantial evaluator work inside those phases.
The sampler starts before Parquet/PyArrow loading; both reference encoders are
loaded, and runtime provenance checks spawn Git subprocesses. Finalization
includes source/index snapshots, offline component packing/scoring, 78 evaluator
`git show` checks and another model verification. The legacy `file_sha()` reads
an entire file into bytes, including the 118,453,870-byte ONNX file even for
lexical stages. These are known costs, but the old summaries do not establish
which operation caused their largest tree peaks.

Each stage uses a fresh worker process and the controller waits for it to exit.
Earlier workers and the controller are outside the next worker's descendant
tree. The runtime explicitly closes SQLite, clears its bounded directory cache
and drops the semantic model; the v0.3.2 source-unit and assembly caches are
local to a recall. No runtime leak has been demonstrated by this inspection.
The original adverse results remain unchanged.

## New diagnostic boundaries

The supervisor verifies the same full 2,548-session / 10,693-turn corpus and
prepares private normalized JSONL. A deterministic hash selection chooses 32
of the 256 already scored IDs. Eight fresh product workers run in four balanced
rounds: baseline/candidate, candidate/baseline, candidate/baseline,
baseline/candidate. Each ingests the full corpus and executes the same 32
character-budget recalls, for exactly 256 calls. Complete non-timing payload
hashes must match across versions and rounds.

The normalized input hashes are recorded once during preparation, then checked
before and after every worker. Commands pass those original hashes unchanged;
the controller cannot accept a changed input by recomputing its expected hash.

Product workers stream that JSONL and contain the standard-library wrapper and
the pinned Book runtime. They do not load PyArrow, reference tokenizers, Git
provenance processes or the semantic model. Initialization, ingestion, queries
and close have separate phases. No forced garbage collection or allocator
trimming is used.

One additional evaluator-only worker loads the old corpus, initializes both
reference tokenizers, performs runtime/evaluator provenance checks and reproduces
the legacy full-file model hashing. It executes zero retrieval or inference
calls. Model/corpus download and preparation happens before the observed worker;
public model files are verified against their frozen identities without building
an index. The pinned tokenizer may fetch reference-encoder data inside its own
phase if that data is not cached; this phase is not isolated encoding-load timing.

An external observer samples every live worker descendant at a target interval
of 20 ms, traversing children created by all observed threads. Every saved row
contains timestamps, PID/parent/start identity, command category, RSS and, where
readable, PSS/private memory. Root and descendant RSS remain separate alongside
the inclusive sum. Missing PSS is explicit; a partial sum is never called the
whole tree's PSS. Task enumeration, thread-children read and post-record identity
errors mark discovery incomplete and suppress a whole-tree PSS total. Root
identity and parent checks guard PID reuse.

Start/end observer acknowledgements capture boundary samples even when a close
operation lasts less than 20 ms. These pauses are recorded and are not latency
measurements. Continuous samples crossing a phase event are labeled transition.
The spawn boundary is retained separately, including possible inherited mappings
before execution of the fresh interpreter. Short-lived children or peaks can
still be missed, and summing RSS can count shared mappings more than once.

## Execution and interpretation

The dedicated workflow accepts only its registered push branch and first Actions
attempt. An immutable claim keyed by the plan hash is committed before preparation.
Each exact worker intent is committed before launch, followed by its compressed
raw trace, phase/query events and summary before another worker starts. Any
failed stage stops the sequence; partial outputs remain in the result branch and
the workflow's always-uploaded source-free artifact. Corpus and query text stay
in private working files and are not included in public artifacts.

The observer uses nonblocking raw pipes and a selector. Cleanup sends bounded
TERM/KILL signals to its dedicated process group even when the original worker
already exited, so a descendant retaining stdout cannot strand a reader thread
or block a buffered-stream close. Cleanup outcomes are retained in the summary.

## Pre-execution review fixes

Independent review found three issues before any diagnostic execution: a child
retaining stdout after leader exit could defeat cleanup; incomplete child
discovery could incorrectly label a PSS sum complete; and recomputing expected
input hashes for each command could silently accept changed preparation files.
The current implementation addresses all three. New fixtures use an isolated
synthetic process with no Book/retrieval, artificial proc records, and mutated
temporary input files. Earlier offline parser/protocol fixtures remain intact.

All **17 focused fixtures pass** after these repairs. The
[retained fixture log](../benchmarks/reports/round5-resource-fixtures.log)
includes the watchdog-protected inherited-stdout test, three discovery-failure
cases and the normalized-input mutation check. This is functional verification;
no registered resource worker, Book recall or inference was executed.

The new trace may establish which processes consume memory in this diagnostic.
It cannot retrospectively identify a child that was not recorded in the old
run, and it does not replace the original +71.97% / +68.98% observations. Product
memory and evaluator overhead will be reported separately, with retained
inclusive values and missing-PSS limits. No speed, quality, leak or memory-saving
claim is accepted merely because the diagnostic completes.

Implementation: [controller and observer](../scripts/round5_resource_diagnostic.py),
[offline fixtures](../tests/test_round5_resource_diagnostic.py),
[dedicated workflow](../.github/workflows/round5-resource-diagnostic.yml).
