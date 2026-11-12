# Retrieval experiments

## Current: v0.3.1 / round three

The accepted runtime is
[`2d199b9`](https://github.com/Afloat16/AI-Memory-Book/commit/2d199b93f650eccd3dd239178822b31001b880e3),
Python-source SHA-256 `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.
Default lexical ranking is unchanged; a guarded project rowid range reduces
FTS work. Q2 and indexed MCP references remain optional. The project-local
statistics candidate is rejected and is not shipped.

| Experiment | Verified measurement | Complete evidence |
|---|---|---|
| Default performance | 47,320 calls, 16 workers, four balanced rounds, ten cells; strict full-payload audit passes; geometric mean pooled p95 improvement 11.36% | [Independent resource/performance review](../docs/round3-performance-review.md), [original summary](reports/round3-performance-43246417515-1/report.summary.json) |
| Startup resource exception | Original public startup mean +14.04% and automatic rejection remain intact; existing 80-sample diagnostic independently verified | [Original and supplemental evidence](../docs/round3-startup-resource-review.md), [independent 80-sample verification](reports/round3-recovery/startup-diagnostic-cross-verification.json) |
| Project-local statistics quality screen | 8,082 original calls recovered without replay; 14 registered checks fail; candidate excluded | [Recovery and decision](../docs/round3-quality-review.md), [byte comparison](reports/round3-recovery/quality-cross-verification.json) |
| New 256-question comparison | Ten complete stages, 4,608 native calls plus 4,608 component searches; all 1,536 native and 768 component default payload pairs match | [Full report](results/round3-comparison-43267797247-1/report.md), [assessment](results/round3-comparison-43267797247-1/assessment.json), [checkpoint](reports/round3-comparison-43267797247-1-checkpoint.json), [independent offline verification](reports/round3-recovery/comparison-cross-verification.json) |

The new comparison has status **complete-verified**. Source, evaluator, model,
dependencies and upstream revisions were bound before selection. These 256
HotpotQA questions exclude both previous selections but use the same source;
after scoring they are regression data. No generated-answer call is configured.

At the common 1,024-cl100k whole-block view, complete evidence is **52.34% Book
default, 54.69% Book Q2, 45.31% claude-mem, 55.86% ai-memory and 58.20%
billion-context**. Book default has lower recorded component search p95 than
claude-mem and ai-memory; billion-context leads the displayed quality and
search-speed measures. Q2 loses native completeness at both 512-token settings.
All costs, individual losses and interface boundaries stay in the full report.

The original authoritative hosted registration appeared during recovery. Its
one existing comparison was adopted; the later local binding/selection was
archived unused and no duplicate scoring run was started. See
[reconciliation](../docs/round3-reconciliation.md),
[completion checkpoint](../docs/round3-continuation.md), and the
[current comparison](../docs/comparison.md#v031-comparison).

## Historical: v0.3.0 / round-two implementation and measurements

The “current” labels within this historical section refer to its named
round-two source and measurement, not the v0.3.1 comparison above.

The selected runtime is
[`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba),
source SHA-256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`.
The default remains lexical with object-form MCP references. Q2 semantic
fusion and indexed references are separate, explicit options.

| Current experiment | Verified measurement | Complete evidence and costs |
|---|---|---|
| Default retrieval and ingestion | 56,784 actual calls; four balanced rounds; 12 configurations; complete payloads and source/index content unchanged | [Performance, ingestion, replay, memory and individual-round losses](../docs/default-recall-performance.md) |
| Optional Q2 semantic fusion | 48,492 actual recalls; four old cohorts, three budgets, four paired modes, three repetitions | [Full development matrix](reports/round2-anchor-development.md), [selection and losses](reports/round2-anchor-decision.md), [current semantic setup](../docs/semantic-retrieval.md) |
| Indexed MCP references | 56,784 actual SDK calls; 7,098 distinct complete payload pairs; every one of 6,868 archived reference entries checked | [Both tokenizers, complete metadata costs, all 12 timing configurations and per-question losses](../docs/indexed-references.md) |
| Current native components | 10 completed stages, 32,256 timed calls, 256 questions; current pinned claude-mem FTS, ai-memory local hybrid and billion-context kernel | [Complete matrix](results/round2-43207732852-1/report.md), [assessment](results/round2-43207732852-1/assessment.json), [run 43207732852](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207732852) |

The initial 256-question run stopped at an evaluator response-field error;
its [failed checkpoint](reports/round2-43201620535-1-checkpoint.json) and all 13
public output files remain preserved. The completed registered recovery keeps
the original candidate, data and settings, runs every stage on one new host,
and does not pool or select timings from different runs. All 23 final files
were [independently verified](reports/round2-recovery-independent-verification.json).
The [numeric cost audit](reports/round2-43207732852-1-component-cost-audit.md)
passes all six components and 1,536 first-pass records. The separate
[cross-run audit](../docs/round2-recovery-audit.md) preserves the difference in
the full original-store snapshot hash while showing identical supplied pages,
9,216 complete query/configuration rows and 19,968 repeated non-timing samples.
That selection is already scored and must not become a tuning set labeled as
unseen validation.

Default lexical quality is unchanged in all 3,072 native baseline/candidate
query/configuration pairs. Current Q2 improves several completeness settings,
with small-budget losses retained. In the 1,024-cl100k component view, Q2
complete evidence is 57.81%, claude-mem FTS 48.83%, ai-memory 53.91%, and
billion-context 61.72%. The current implementation is not the best component
on every metric; the complete comparison retains that result and all costs.

[Current comparison and project landscape](../docs/comparison.md) ·
[Round-two status and source identities](../docs/optimization-round2.md).

## Separate research: bounded novelty

The [complete old-data probe](../docs/novelty-probe.md) preserves **12,123
calls** across four old cohorts, three budgets and three fixed formulas.
Removing the query-term novelty bonus loses evidence and fails an existing
complementary-facet test. Capping its bonus at 0.25 gains three complete
LoCoMo questions at 512 tokens, with no observed complete-question or
annotation losses in the twelve development settings. Other quality values
are unchanged; some contexts, payload costs and single-pass timings change.
The subsequent [strict regression qualification](../docs/novelty-cap-qualification.md)
completed 4,096 small-budget calls and **rejected the cap**: every one of eight
paired default/Q2 settings loses complete questions. The 1,024/2,048-token
phase was not run under the registered stop rule. Neither experimental formula
is adopted; the current product and README comparison remain unchanged.

The original measurement files and failed final presentation audit remain
unchanged. An [independent supplemental audit](reports/novelty-probe-43214192647-1.supplemental-audit.json)
recomputes the full numerical matrix and proves the Markdown difference is
only the order of two final candidate notes. No retrieval was rerun to repair it.

## Historical: earlier completed memory validation

The earlier 2026-11-12 continuation is **complete for its named source pins**. The
[final strict audit](reports/hosted-final-aggregation.json) verifies 80 fixed
input files and eight derived reports; all four summarizers passed. Completed
source results retain their original hashes and independent Git branches.

| Experiment | Completed measurement | Full report |
|---|---|---|
| Native token budgets | 8 cohorts; 24,228 paired query/configuration cases; 251 complete-case gains and zero losses | [Evidence and cost matrix](RESULTS-native-token-budget.md) |
| Optional local semantics | 4 cohorts; 24,246 actual recalls; all gains and losses retained | [Semantic results](RESULTS-semantic-retrieval.md) |
| Actual generated answers | 768 calls over 128 LoCoMo and 128 HotpotQA questions, each in three modes | [Answer scores, latency and usage](RESULTS-local-answers.md) |
| Book / ai-memory native workflow | 42 captured sessions; 42 native model consolidations; 72 answers; complete with recorded failures | [Full workflow](RESULTS-full-workflow.md) |
| claude-mem native FTS | 1,015 questions × 3 actual native calls; all six context configurations verified | [Component report](results/claude-mem-components-public.md) |
| Earlier exact-output prefix optimization | 2,016 identical payloads; 6,048 calls per source; all 12 timing settings retained | [Performance report](../docs/token-prefix-performance.md) |

The native workflow's 35 failed consolidations are actual native
`truncated-response` errors under the fixed 0.5B model / 1,000-output-token
configuration; all requests, failed usage and later answers remain counted.
A passing integrity audit does not turn these into successful consolidations
or assert a universal quality improvement.

[Completion record and source identities](../docs/continuation-status.md) ·
[Four-component and high-star project comparison](../docs/comparison.md) ·
[Exact aggregate inventory](../docs/final-validation-aggregation.md) ·
[Interruption recovery](../docs/hosted-validation-recovery.md).

The default remains lexical. Semantic results, generated answers and complete
workflow costs have distinct boundaries. Historical records below retain the
findings available at their named source versions.

## Historical: optional coverage and answer readiness

The [coverage report](RESULTS-conjunctive-recall.md) retains the complete frozen
automatic-clause experiment and explains the final opt-in API decision. All
eleven stages completed: four existing synthetic regressions, the new authored
transfer diagnostic, public comparisons, real MCP calls and both pinned native
competitors. Gains and small-budget/latency losses remain visible.

Final `coverage=False` restores the previous score-aware default. The mode
[equivalence record](reports/coverage-mode-equivalence.json) verifies 2,774
complete non-timing payloads for each of default and explicit coverage against
their corresponding frozen runtimes. See the report's reproduction section:
running `conjunctive_manifest.json` against the final default source would test
a different mode from the original automatic-clause experiment. Its original
checkpoint is immutable evidence and cannot be resumed after changing source.

The [real-answer guide](../docs/answer-evaluation.md) documents `prepare` and
`run`, exact/reference token accounting, missing usage, errors and model
identity. At that historical checkpoint, the
[readiness record](reports/answer-eval-readiness.json) contained 128 prepared
development cases and no model calls. It records preparation only. The later
768 real answer attempts and their failures are documented in the
[completed answer evaluation](../docs/answer-evaluation.md).

## Previous score-aware continuation

The [score-aware report](RESULTS-recall-score-quality.md) evaluates runtime
`0ab49d4f2be6aabe5e51c3314bb9369041af5369`. It preserves the first frozen round
below and evaluates the single development-selected score-aware fusion rule.
Seeds 211/509 and all public heldout questions are now regression data; seeds
883/1297 were reserved before this second run. These generated templates are
not an independent domain test.

Use [the corrected full manifest](recall_score_quality_manifest_v2.json) for a
fresh reproduction. Prepare the two historical baseline worktrees described
below, plus the first-round runtime:

```bash
git worktree add --detach ../baseline-recall 6f5299004642618e606d001b4c574e1bae572a7e
```

Install `.[mcp,clients,benchmark]`, Node 24+, and the pinned corpus/competitor
caches below before starting. Plotting additionally requires `matplotlib`;
install it before a frozen run if charts will be reproduced, because dependency
changes deliberately invalidate a live execution checkpoint. Then run:

```bash
export TIKTOKEN_CACHE_DIR="$PWD/.artifacts/tiktoken"
python -m benchmarks.resume \
  --manifest benchmarks/recall_score_quality_manifest_v2.json \
  --checkpoint .artifacts/score-full-checkpoint.json
PYTHONPATH=. python scripts/assess_score_quality.py \
  --full-checkpoint .artifacts/score-full-checkpoint.json
python scripts/plot_recall_quality.py \
  --assessment benchmarks/results/recall-score-final-assessment.json
```

The measured execution used eleven completed stages from the initial manifest
and five stages from [the cost continuation](recall_score_cost_manifest.json).
The initial migration step correctly refused a schema-3-to-schema-3 comparison;
the corrected migration baseline is preserved v0.3, which supplies schema 2.
The [failure and recovery record](reports/recall-score-recovery.json) retains the
original failed stage. Neither evaluator assertions nor runtime code were
changed to make it pass. The assessment checks all stage arguments and output
hashes against the corrected full manifest, together with matching runtime and
source/data/evaluator identities. Its combined execution index is an audit
record, not a checkpoint to feed back into the runner.

For the recorded split execution, the assessor's default mode reads the two
original checkpoints and verifies their lineage; a fresh full reproduction uses
`--full-checkpoint` as shown above. The figures use separate filenames so the
first-round chart remains attributable to its own runtime.

## First frozen recall-quality round

The [first-round report](RESULTS-recall-quality.md) records the first 13-stage
continuation of the interrupted `perf/recall-quality-budget` work at runtime
`6f5299004642618e606d001b4c574e1bae572a7e`. Its source identity, development choices,
reserved seeds, public regression/expansion cohorts, native component costs and
remaining limitations are separate from the historical v0.3.0 records below.

[recall_quality_plan.json](recall_quality_plan.json) records the evaluation
rules and seeds 211/509 selected before their results.
[recall_quality_corpora.json](recall_quality_corpora.json) lists the exact six
corpus selections for structural preflight. The full public split includes the
previous 256-query regression sample; the report separates the remaining 759
queries and does not call the whole split unseen data.

[recall_quality_manifest.json](recall_quality_manifest.json) executes all final
measurements sequentially. From this checkout, prepare sibling baseline
worktrees at `../baseline-v0.3` (commit
`3ee40946c5407e65fd375a8d47472066a82ae472`) and `../baseline-v0.2` (commit
`a05f88a79ce20be3fd5912c62fc020f8b11ba4a9`). Install `.[mcp,clients,benchmark]`,
use Node 24+, and download the pinned LoCoMo file described below to
`.artifacts/data/locomo10.json`. Prepare the optional competitor cache once:

```bash
python - <<'PY'
from pathlib import Path
from benchmarks.competitors.billion import prepare as prepare_billion
from benchmarks.competitors.ai_memory import prepare, prepare_models
cache = Path('.artifacts/competitors')
prepare_billion(cache / 'billion-context')
prepare(cache)
prepare_models(cache)
PY
export TIKTOKEN_CACHE_DIR="$PWD/.artifacts/tiktoken"
python -m benchmarks.resume \
  --manifest benchmarks/recall_quality_manifest.json \
  --checkpoint .artifacts/recall-quality-checkpoint.json
```

The same command resumes an interrupted run. Completed stages are reused only
after their output hashes and JSON validation pass. Missing/corrupt reports
invalidate the affected stage and its successors. Source, corpus, manifest,
Python, installed dependency, SQLite or Node changes require a new checkpoint;
results from different implementations must not be mixed. The checkpoint uses
an atomic write and an operating-system lock. On POSIX, failed/interrupted
stage process groups are cleaned up before another stage can start.

Paired and component reports retain diagnostic output but exit unsuccessfully
for recorded source changes or context/token-budget violations. Passing these
invariants does not mean a quality target passed. Full-corpus MCP timing retains
duplicate query IDs and clears the result cache outside timing before repeated
query/scope pairs, preserving an uncached first call and a separately measured
immediate repeat for each row.

## v0.3.0 measurement records

The [release interpretation](RESULTS-v0.3.0.md) discusses improvements, remaining
failures, and comparison limits. Complete curves and per-query records are
retained in these reports:

- Paired synthetic heldout 113: [report](results/paired-heldout-113.md),
  [summary](results/paired-heldout-113.summary.json), [full records](results/paired-heldout-113.json.gz).
- Paired synthetic heldout 307: [report](results/paired-heldout-307.md),
  [summary](results/paired-heldout-307.summary.json), [full records](results/paired-heldout-307.json.gz).
- Paired public LoCoMo heldout: [report](results/paired-locomo-heldout.md),
  [summary](results/paired-locomo-heldout.summary.json), [full records](results/paired-locomo-heldout.json.gz).
- Actual shared-page components, public development: [report](results/components-locomo-development.md),
  [summary](results/components-locomo-development.summary.json), [full records](results/components-locomo-development.json.gz).
- Actual shared-page components, public heldout: [report](results/components-locomo-heldout.md),
  [summary](results/components-locomo-heldout.summary.json), [full records](results/components-locomo-heldout.json.gz).
- [Evidence-structure preflight](results/evidence-preflight.json) verifies zero
  annotations split across canonical pages in every newly evaluated corpus,
  for both baseline and candidate. No labels were removed to obtain that result.

Each report has a matching `.summary.json` and complete `.json.gz` beside it.
Synthetic tests are controlled regressions; public LoCoMo is a text-evidence
adaptation; upstream tests are bounded retrieval-component comparisons. None
is a generated-answer accuracy benchmark or proof of universal superiority.

## Version, tokenizer, and public-data comparison

The new `token_compare` harness runs an immutable baseline and the candidate in
independent Python processes. It measures the returned context with actual
`tiktoken==0.12.0` encodings (`cl100k_base` and `o200k_base`), with no character
estimate fallback. These are reference encodings, not all providers' tokenizers
or billed API usage. The production package still has no tokenizer dependency.

```bash
python -m pip install tiktoken==0.12.0
git archive a05f88a79ce20be3fd5912c62fc020f8b11ba4a9 | tar -x -C /path/to/frozen-v0.2.1
python -m benchmarks.token_compare \
  --baseline-src /path/to/frozen-v0.2.1/src --candidate-src src \
  --split development --seed 61 --projects 8 --repeats 3 \
  --budget-chars 2000 8000 --token-budgets 512 1024 2048 \
  --output benchmarks/results/paired-development-61
```

Create the destination directory before `git archive`. Tokenizer downloads may
occur on first use; set `TIKTOKEN_CACHE_DIR` to reuse a prepopulated cache offline.
Source fingerprints before and after each worker detect edits during a run.
Synthetic seeds **113 and 307** were reserved before this optimization round;
seed **61** is development. The older 11/29/47 experiments below are historical
development evidence and must not be reused as fresh heldout evidence.

The paired report separates two questions. The same character caps compare
the real retrieval API directly. A second, explicitly additional stage applies
the identical whole-evidence-block token packer to each engine's single
8,000-character retrieval. It retains blocks in rank order when they fit, may
skip a large block to fit a later one, and never consults evidence labels. It
does not trim source spans or make additional recall calls. Packing latency is
reported separately. This is an evaluation policy, not a native production
token-budget feature.

Recall timings exclude ingestion, token counting, startup, MCP transport, and
model inference. Separate fresh Python CLI timings include startup/imports,
database open, recall, and JSON serialization, with warm OS/disk caches. Real
MCP initialization, tool definitions, and full serialized responses are
measured separately by `benchmarks.mcp_costs`; neither core API JSON nor context
alone is a substitute for those costs.

### External LoCoMo corpus

[LoCoMo](https://github.com/snap-research/locomo) by Maharana et al. provides an
independent public benchmark of persona-agent-generated conversations. These
are generated dialogues, not genuine human-user histories. The upstream data has a
[CC BY-NC 4.0 license](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/LICENSE.txt),
which is separate from this repository's MIT code license. Download it outside
this repository, in accordance with that license. No dataset text is vendored
or included in our result files.

```bash
curl -L https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json \
  -o /path/to/locomo10.json
python -m benchmarks.token_compare \
  --baseline-src /path/to/frozen-v0.2.1/src --candidate-src src \
  --corpus locomo --locomo-path /path/to/locomo10.json \
  --split heldout --max-queries 256 --repeats 3 \
  --output benchmarks/results/paired-locomo-heldout
```

The loader verifies the pinned file's SHA-256 and size. `locomo_split.json`
records the upstream commit and the conversation-level split, frozen before
outcomes were inspected: two development conversations and eight heldout
conversations. Bounded query selection sorts the SHA-256 hashes of stable query
IDs; it does not select favorable questions or outcomes. `--max-queries 0` uses
all eligible questions. Reports contain IDs, counts, and metrics, never raw
questions, answers, or source quotes.

This is a **text-evidence retrieval adaptation**, not the original LoCoMo
generated-answer benchmark. Each dialogue utterance becomes one source turn
with its speaker name; summaries, answer labels, image captions, and images are
not indexed. We exclude answerable questions with missing/invalid evidence IDs
or image-bearing required evidence, and report every exclusion count. A hit
requires the complete annotated utterance and correct source span; this is
stricter than simply retrieving a relevant page and does not measure whether an
LLM could answer from a smaller fragment. Category 5 questions are retained as
unanswerable diagnostics. The other category IDs remain the upstream IDs.
Source date/time lacks a timezone; UTC is used only as a deterministic indexing
convention. Public conversations, independent wording, and conversation-level
splits reduce synthetic-template leakage but do not establish performance for
every domain or client.

### Actual upstream retrieval components

`component_eval` exports the frozen baseline's adaptive pages once and executes
the pinned Billion-context search kernel and the official ai-memory release
against the same pages and project scopes. It also runs MemoryBook against a
copy of that frozen database. Every selected page passes through the same full
source-page assembler and whole-block token packer. The book keeps its native
hierarchy/FTS fields, so only page granularity and source content are shared;
this does not remove every indexing-feature difference.

```bash
python -m benchmarks.component_eval \
  --baseline-src /path/to/frozen-v0.2.1/src --candidate-src src \
  --engines candidate billion-context ai-memory-hybrid \
  --cache /path/to/competitor-cache \
  --corpus locomo --locomo-path /path/to/locomo10.json \
  --split development --max-queries 128 --repeats 3 \
  --output benchmarks/results/components-locomo-development
```

The first execution downloads verified pinned upstream code/binaries and, for
ai-memory hybrid, the default local MiniLM model. `--offline` requires those
cache files to exist and prevents downloads. See
[competitor adapter documentation](competitors/README.md) for pins, setup,
native search routes, and model verification. No provider keys or paid model
calls are used. The shipped native embedding backfill must finish without
errors before retrieval. A separate post-measurement diagnostic verifies the
active native search streams, without adding explain fields to measured
payloads.

This comparison reports source coverage under a common context budget, native
preview payload costs, and actual ai-memory full-read costs separately. A short
preview does not receive credit for evidence available only after a read.
The native read-cost policy always reads all mapped top-k pages, even if a
preview already contains enough evidence. It is a fixed, reproducible policy,
not a minimum-read strategy or a token-budget-adaptive native policy; a
preview-only consumer can spend less.
Native auto-generated metadata pages consume top-k positions and tokens but
earn no evidence. MemoryBook timing includes in-process recall/context
assembly; Billion exposes kernel and IPC roundtrip timings; ai-memory uses its
actual HTTP/MCP transport. These boundaries differ. It does not benchmark
Billion's summarization/proxy workflow, Claude-mem's full pipeline, paid model
inference, or end-to-end agent answer quality. Lower tokens in a preview alone
cannot establish a superior complete memory system.

## Historical segmentation experiments

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
