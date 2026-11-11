# Experiment record and default selection

All measurements in this record use synthetic conversations authored for this
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

Heldout reports and their final interpretation are recorded below after the
measurements finish.
