# Experiment record and default selection

This file preserves the historical v0.2 segmentation/default-selection record.
The v0.3 paired-version, exact-tokenizer, independent public-corpus, and actual
upstream-component protocol is documented in [the benchmark guide](README.md).
The historical heldout seeds below became prior evidence for later work and
are not fresh heldout evaluation of v0.3.

All measurements in this historical record use synthetic conversations authored for this
project. They test the local retrieval implementation, not an LLM's answer
quality and not the performance of other open-source memory systems. The full
per-query evidence records are retained in deterministic gzip archives beside
the human-readable reports.

## What is actually compared

The segmentation factor has three levels: one page per session, one page per
user question and its answer, and adaptive sections with bounded continuation
pages. The retrieval factor has two levels: shared metadata-aware FTS ranking
(`flat`) and that same ranking with a soft directory-overlap adjustment (`book`).
Both have the same tokenizer, original transcripts, project scope, task
metadata, result limit, context budget, and query-centered excerpt algorithm.
The session baseline is allowed to find a relevant window inside a long
session; it is not restricted to reading the first paragraph.

Every retrieved unit contributes one query-centered window. A different
whole-session retriever that extracts several independent windows could
recover some of the multi-section gap; that alternative is not implemented or
measured here. The results support this implementation choice, not an inherent
lower bound on whole-session retrieval.

Evidence must appear in the budgeted context, belong to the expected original
project/session/turn, and fall inside the returned original-turn source span.
The budgets below include citation headings. They do not include all JSON
metadata on a transport wire. Main latency measurements disable result caching
but do not flush SQLite or operating-system page caches. A separate hot-cache
measurement immediately repeats each warmed query.

## Development stage 1: short sessions were insufficient

The original corpus used 8 projects, 96 sessions, 384 user turns and 104 queries,
with 74,502 source characters. At a 2,000-character budget, adaptive and whole
session segmentation both retrieved 91.67% of the required evidence. Their mean
context sizes were approximately 1,711 and 1,713 characters. The directory
ranking adjustment did not change aggregate accuracy.

This did **not** support a claim that adaptive segmentation substantially reduced
reading. Most sessions were already short enough to fit a useful excerpt.
Turn segmentation lost some cross-session facts and short follow-up answers,
which supported preserving short contextual sequences rather than blindly
splitting every question.

The [v1 short-session report](results/development-11-short-sessions-v1.md) is
retained. Its core code preceded later tokenizer and retrieval optimizations,
so differences between v1 and v2 must not be presented as algorithm-only gains.
The corpus itself remains reproducible with `--short-sessions --seed 11
--split development`; its content fingerprint is unchanged.

## Development stage 2: mixed long conversations

Dataset v2 retains the short-session cases and adds two 64-question engineering
journals per project. Twenty independently authored technical procedures and
code snippets introduce topic changes, repeated engineering vocabulary and
large single answers. Some queries need facts 47 questions apart in one
conversation. Others need facts in the middle or near the end of a disaster
recovery manual.

The development seed 11 corpus contains 112 sessions, 1,408 user turns,
1,143,305 source characters and 168 queries. Of these, 152 are answerable and
require 176 atomic evidence spans. The source templates, ground truth and
question templates are all inspectable. More text and more topics do not turn
this into a real-world dataset.

## Page-size sweep on development data

The following runs vary only the adaptive page cap. The minimum section size
remains 400 characters, the similarity threshold 0.12, and retrieval uses
`book`, limit 5, three uncached repetitions per query and the same seed 11
corpus. Heldout outcomes were not consulted to choose the cap.

| Page cap | Budget | Evidence recall | Complete evidence | Mean context chars | Uncached p95 ms |
|---:|---:|---:|---:|---:|---:|
| 900 | 2,000 | 81.82% | 84.21% | 1,911 | 8.60 |
| 1,800 | 2,000 | 76.14% | 78.95% | 1,911 | 9.64 |
| 3,600 | 2,000 | 77.84% | 78.95% | 1,909 | 12.26 |
| 900 | 8,000 | 92.61% | 91.45% | 3,648 | 7.10 |
| 1,800 | 8,000 | 89.20% | 88.16% | 5,654 | 11.62 |
| 3,600 | 8,000 | 86.36% | 88.16% | 6,251 | 14.97 |

The chosen default is **900 characters per adaptive page**. On this development
set it gives the strongest evidence coverage while reading less text at the
larger context budget. This costs more pages and indexing work: 1,912 pages and
about 14.2 MB of database pages, versus 928 pages and 12.3 MB at a cap of 1,800.
Measured ingestion was about 826 ms versus 687 ms. These are workload-specific
tradeoffs, not a proof that 900 is universally optimal.

The complete sweep reports are [900](results/development-11-sweep-900.md),
[1,800](results/development-11-sweep-1800.md), and
[3,600](results/development-11-sweep-3600.md).

## Full development comparison at the selected cap

Each segmentation uses the same selected cap parameter; `session` and `turn`
intentionally keep their entire retrieval units, while `adaptive` splits long
units into continuation pages. Flat and book produced the same aggregate
evidence recall in this run. The table shows book values; both strategies and
every category remain in the full report.

| Segmentation | Budget | Evidence recall | Complete evidence | Mean context chars | Uncached p95 ms |
|---|---:|---:|---:|---:|---:|
| Session | 2,000 | 70.45% | 76.32% | 1,857 | 109.43 |
| Turn | 2,000 | 75.00% | 76.32% | 1,648 | 22.04 |
| Adaptive | 2,000 | 81.82% | 84.21% | 1,911 | 8.08 |
| Session | 8,000 | 75.00% | 76.97% | 5,297 | 110.02 |
| Turn | 8,000 | 86.36% | 84.21% | 3,600 | 23.77 |
| Adaptive | 8,000 | 92.61% | 91.45% | 3,648 | 6.82 |

The [full development report](results/development-11-v2-900.md) shows that the
benefit here comes from retrieval granularity and bounded excerpt work. The
directory ranking adjustment has no demonstrated aggregate recall benefit.
The turn baseline uses slightly less context at the larger budget and does
better on some multi-section queries; adaptive is not best on every category.

Low-overlap paraphrases still fail in this lexical implementation. Related
unanswerable questions often return related material, which is not equivalent
to evidence that answers them. A consuming model must check the evidence and
avoid inferring an answer from topical similarity alone. Current-versus-old
decision cases also test retrieval, not authoritative conflict resolution.

## Heldout protocol

After choosing the default on seed 11, seeds 29 and 47 use the separate heldout
wording bank with the selected parameters frozen at 900 / 400 / 0.12. Every seed
runs all six configurations, both context budgets, three uncached repetitions,
and the separate hot-cache diagnostic. No algorithm changes are selected from
these results. The supplied task identifiers and the limited set of synthetic
source templates remain limitations even when seeds and query wording differ.

### Release verification versus parameter tuning

Release review found additional correctness issues in preserving project/chapter
display names and migrating older database schemas. It also moved an invariant
heading computation outside a continuation-page loop, eliminating unnecessary
work on unusually long questions without changing the generated pages. These
changes were not selected from heldout scores or used to tune retrieval.

The early heldout runs are preserved as
[seed 29 pre-release](results/heldout-29-v2-900-pre-release.md) and
[seed 47 pre-release](results/heldout-47-v2-900-pre-release.md). Because those runs
shared imported modules while source files changed on disk, they are explicitly
labelled pre-release and are not the final release timing evidence.

The final runs use a separate fresh Python process for each seed, hash package
Python source before and after the experiment, and compare per-query quality
against the corresponding pre-release record. The published final tables use
those release measurements. Full reports include `release_verification` and
`engine_source_unchanged_during_run` so these checks can be inspected.

## Final heldout results

Each heldout seed contains 8 projects, 112 sessions, 1,408 user turns and 168
queries, with approximately 1.143 million source characters. Both final runs
verified unchanged package source with SHA-256
`57c1d2d0ac42530b17757ea5b0278bf394ebc3e631ca541c832117edc2371a60`.
There were zero per-query quality differences from their pre-release counterparts.
Both seeds had zero context-budget violations and zero context-size mismatches.

The table shows `book`; `flat` again had the same aggregate evidence recall and
complete-evidence rates. This does not establish a separate accuracy benefit
from the directory-overlap ranking adjustment.

| Seed | Segmentation | Budget | Evidence recall | Complete evidence | Mean context chars | Uncached p95 ms |
|---:|---|---:|---:|---:|---:|---:|
| 29 | Session | 2,000 | 68.75% | 73.03% | 1,903 | 107.37 |
| 29 | Turn | 2,000 | 56.25% | 54.61% | 1,706 | 23.61 |
| 29 | Adaptive | 2,000 | 72.73% | 73.68% | 1,949 | 9.90 |
| 47 | Session | 2,000 | 68.75% | 73.03% | 1,904 | 161.23 |
| 47 | Turn | 2,000 | 56.25% | 54.61% | 1,706 | 26.00 |
| 47 | Adaptive | 2,000 | 71.59% | 72.37% | 1,948 | 10.17 |
| 29 | Session | 8,000 | 69.89% | 74.34% | 5,411 | 112.87 |
| 29 | Turn | 8,000 | 65.34% | 60.53% | 3,879 | 22.41 |
| 29 | Adaptive | 8,000 | 77.27% | 78.95% | 3,706 | 7.42 |
| 47 | Session | 8,000 | 69.32% | 73.68% | 5,411 | 141.15 |
| 47 | Turn | 8,000 | 64.77% | 59.87% | 3,881 | 24.03 |
| 47 | Adaptive | 8,000 | 77.27% | 78.95% | 3,701 | 7.46 |

At the 8,000-character budget, adaptive segmentation uses about 31.5% less
context than the session baseline while retrieving more required evidence.
Its observed uncached p95 is 7.42–7.46 ms, versus 112.87–141.15 ms for session
segmentation in these runs. These are local API timings on this generated
workload, not end-to-end model latency or a promise for other hardware.
The immediately repeated adaptive hot-cache p95 is 0.277–0.309 ms; that is a
best-case cache-hit diagnostic and should not replace uncached figures.

At the smaller 2,000-character budget, adaptive returns slightly more text than
the session baseline. Its complete-evidence rate is slightly higher for seed
29 and slightly lower for seed 47. There is no universal win at every budget
or on every quality metric.

The heldout adaptive evidence recall of 77.27% is substantially below the
92.61% development result. The separate wording bank exposes limited lexical
generalization. Low-overlap paraphrases have zero recall; the two-fact
`multi_section` category recovers only 25% of its required evidence and completes
none of those two-fact queries; and the
natural long-answer middle category recovers 75%. These failures are retained
in the raw records, not removed from the reported average.

All unanswerable heldout questions return nonempty context. That demonstrates
the need to distinguish related material from evidence of an answer; this
benchmark does not measure a model's hallucination rate. In half of the
current-decision queries, adaptive ranks old evidence before current evidence,
although it returns the current fact as well. Source dates are therefore
necessary, and authoritative version resolution remains outside this lexical
retriever's guarantees.

Full results: [heldout seed 29](results/heldout-29-v2-900.md) and
[heldout seed 47](results/heldout-47-v2-900.md). Each report links the complete
gzip archive and a compact JSON summary. The published default is supported by
the development tradeoff and these bounded heldout observations; it is not a
claim that directory organization alone solves semantic memory retrieval.
