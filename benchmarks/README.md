# Retrieval experiments

This harness compares `session`, `turn`, and `adaptive` segmentation, each with
`flat` and `book` ranking. It exercises the same `MemoryBook.recall` implementation
and budgets for all six configurations. It does **not** execute external memory
projects, call a language model, or claim to represent real user workloads.

## Run

From the repository root, after installing the package (or with `PYTHONPATH=src`):

```bash
python -m benchmarks.run --split development --seed 11 --projects 8 \
  --budget-chars 2000 8000 --repeats 3 \
  --output benchmarks/results/development-11
```

After finalizing parameters, use fresh seeds and the heldout wording bank:

```bash
python -m benchmarks.run --split heldout --seed 29 --projects 8 \
  --budget-chars 2000 8000 --repeats 3 \
  --output benchmarks/results/heldout-29

python -m benchmarks.run --split heldout --seed 47 --projects 8 \
  --budget-chars 2000 8000 --repeats 3 \
  --output benchmarks/results/heldout-47
```

The commands write a gzip-compressed complete JSON report with per-query evidence
outcomes, a smaller `.summary.json` with aggregate and category metrics, and a
Markdown report linking both. Gzip headers omit filenames and use a zero timestamp;
decompression is checked before writing. No evidence rows are removed from the
complete archive. The summary records its uncompressed SHA-256 checksum.
`--dump-dataset path.json` additionally exports synthetic sessions and independent
evidence labels. A nonzero exit status signals a context budget or size-accounting
violation; low recall is a reported result rather than an artificial pass/fail
threshold. `--projects 2 --repeats 1 --no-cache-measurement` makes a smaller smoke
run. `--max-page-chars` (default 900), `--min-page-chars`, and `--similarity-threshold` support
parameter experiments on development data. A narrow development sweep can use
`--segmentation adaptive --strategy book`; the final comparison should keep all
three segmentations and both retrieval strategies.

## Dataset

The original short-session portion contains four explicit tasks with three dated sessions and four
user turns per session: quote caching, authentication, release rollback, and
background workers. Half of the projects use Chinese and half use English.
The long-answer cases place evidence in the middle of an operational runbook.
The same component names recur across projects, which tests scope handling.
Explicit task identifiers are input metadata, not hidden labels available only
to the book strategy.

Dataset v2 additionally gives each project two mixed-topic engineering journals
with 64 user questions each. Twenty independently authored domain procedures
cover webhook recovery, backups, schema migration, indexing, quotas, scheduling,
attachment processing, auditing, billing, feature rollout, CDN behavior,
connection pools, exports, leases, notifications, pagination, tracing,
accessibility, configuration changes, and deletion propagation. The procedures
include code and operational review notes. A long single answer assembles these
procedures into a disaster recovery manual with evidence in the middle and near
the end. Another query requires two facts 47 turns apart in one journal.

The default eight-project development corpus exceeds one million source
characters and contains 112 sessions, 1,408 user turns and 168 queries. The
source text remains templated synthetic data: scale and varied procedures do
not make it a real-world evaluation. `--short-sessions` reproduces the original
v1 corpus; its development report is retained separately so corpus changes are
not presented as algorithm-only gains.

Cases cover factual lookup, similar terminology, project disambiguation,
cross-session evidence, original and revised decisions, short follow-up
questions, long answers, low-overlap paraphrases, and unanswerable questions.
The dataset version, complete content fingerprint, random seed, and source size
are recorded in each report. Development and heldout use separate phrasing banks.

These are generated examples with a limited set of software-task templates.
Different seeds change names, values, ordering and filler, but do not establish
generalization to arbitrary real conversations. A split is heldout only until
its results are used for tuning; the CLI cannot enforce research discipline.

## Evidence and cost

Ground truth names the **original session and zero-based user turn**, plus the
required fact text. It does not name a generated section or page. A fact counts
only if its text appears in a returned hit with the correct source reference and
survives into the actual, budgeted context. The evaluator also checks that the
reported original-turn character interval actually contains the fact, and that
the project matches the requested scope. Thus a whole-session hit does not get
credit for facts removed by excerpting. Cross-session queries require all facts
for the complete-evidence metric.

Character budgets include citation headers. Actual characters and UTF-8 bytes
are exact; engine token estimates are not tokenizer measurements. Overlapping
source content is measured using original turn coordinates, not page-local
coordinates or semantic similarity. A no-answer query returning some context is
reported as `unanswerable_nonempty_rate`; this is not an answer-generation or
hallucination metric. Old evidence returned without the requested current
evidence is reported separately from returning both versions.

## Timing boundaries

Main timings wrap the `recall` API with `perf_counter_ns()` and disable result
caching. Query order is shuffled reproducibly on each repetition. SQLite and OS
page caches are not flushed. The first query per configuration still runs in the
same Python process, so its timing is **not cold-process startup latency**.

Hot-cache timings immediately repeat a warmed query. They describe best-case
cache hits, not a mixed workload or cache-eviction performance. Import time,
MCP transport, network access, model inference and end-to-end answer time are
outside this benchmark. Hardware, runtime versions and the engine Python-source
fingerprint are recorded for interpreting the observed numbers.

Evaluator v1.2 also hashes the package's Python source after the run and reports
whether it remained unchanged. Final release measurements use a fresh Python
process for each seed, so previously imported modules cannot outlive a source
update. A source change during a run produces a nonzero CLI exit status.

## Evaluator tests

```bash
python -m unittest discover -s tests -p test_benchmark.py -v
```

Tests check deterministic generation, original-source label integrity, separate
phrasing banks, budget enforcement, exact provenance matching, partial
cross-session evidence, stale-result accounting, and continuation-page offsets.
They do not assert that the new approach must outperform a baseline.
