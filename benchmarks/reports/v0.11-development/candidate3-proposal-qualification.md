# Candidate 3: qualify chronological supplements before ordering

This is a development and adversarial-review report. The examples were authored
after examining the implementation. They are regression diagnostics, not a
holdout, an external-product comparison, or a release-acceptance result.

The candidate 3 `store.py` SHA-256 is
`aced6d478ac01ae1612678564e585be6201f37945fb6c228631c37c38fd763cd`.
`RECALL_VERSION` changed from 17 to 18 to invalidate cached candidate 2 ordering.
The package version remains 0.11.0.

## Preserved failure and correction

Candidate 2 promoted a later meeting agenda over an earlier recorded decision
when neither source exposed a recognized field declaration. Its exact-term
fallback transferred a positive relevance slot to the agenda. The independent
review reproduced this with both 8 and 120 earlier sessions. The smaller case
was already in the FTS top 96, but outside the original four-item comparison
pool; its `new_candidates=0` did not make it safe.

The complete input sessions, raw baseline/candidate 2 responses, selected-page
reads, source coordinates, and runtime hashes remain in
[unclassified-proposal-review-attempt1](unclassified-proposal-review-attempt1/report.json).
Before changing production code, the new regression module produced 7 failing
subcases across 8 test methods; the complete original log is
[proposal-qualification-candidate2-failures.log](proposal-qualification-candidate2-failures.log).
Its additional failures included semantic fusion, occurrence queries, cross-chapter
anchors, rejected examples changing original grouping, and duplicate page text
whose original source was deliberately corrupted after ingestion.

Candidate 3 changes the following behavior:

- Every addition to the original comparison pool is copied and marked as a
  proposal, including a page already present in the ordinary relevance tail.
- Before any score permutation or duplicate-text preference, a proposal needs
  an independently authenticated complete original turn, nonempty declared
  fields, and an original-pool anchor with the same chapter, field set, and
  remaining query facets. Another proposal cannot serve as that anchor.
- Rejected text is removed from field discovery and matching inputs. The
  smaller input is reanalyzed until no additional proposal loses eligibility.
  This prevents a rejected code example from supplying the only identifier
  spelling that appeared to qualify another prose proposal.
- Rejected copies leave the original tail's scores and order intact. Tail IDs
  are removed only when their admitted copies remain in the final pool.
- Original-pool unclassified prose keeps its existing fallback. Relevance,
  historical, flat, scope, and source-authentication contracts remain in place.

This does not turn timestamps or syntax into authority. A valid natural-language
revision outside the original pool can still be missed when no comparable
declaration can be established. An unclassified page already in the original
pool can still participate in that pool's older exact-term fallback; one test
explicitly preserves that limitation.

## Verification on this source

The first candidate 3 run passed 34 targeted tests. Two further test methods
then checked original-tail score/order preservation and cascading rejection of
field spellings. The expanded run covered 109 tests across current candidates,
declarations, turns, exact token budgets, temporal intent, semantic routing,
and project-scoped interfaces:

| Backend | Observed result | Retained log |
|---|---|---|
| Native | 109 passed, no skips | [native tests](proposal-qualification-candidate3-native-tests.log) |
| Python | 108 passed, 1 conditional native-comparison test skipped | [Python tests](proposal-qualification-candidate3-python-tests.log) |

The skipped test disables itself when the Python backend intentionally sets
`store._NATIVE` to `None`; the same test passed in the native run. These are
targeted tests, not the complete release suite.

The original crowding probe was rerun without changing its fixture or command
shape. [freshness-candidate3.json](freshness-candidate3.json) retains all 36 calls:
18 current and 18 relevance calls, from six configurations repeated three times.
All 18 current calls included the short new assignment. All 36 candidate 3
evidence payloads matched candidate 2 after removing latency and the changed
candidate-expansion diagnostics. All 18 relevance payloads also matched the
original baseline. These repetitions are not 18 independent questions.

The unchanged six-case work probe is preserved separately in
[current-work-candidate3.json](current-work-candidate3.json). Its actual source
checks were 5, 5, 96, 96, 100, and 114 pages, each independently certified.
Each case used one qualification pass and two declaration-clause parses;
application SELECT counts were 9, 9, 11, 11, 11, and 11. These measured counts
match candidate 2 for these particular valid-declaration fixtures.

Three-repeat median wall times from the uninstrumented original probe follow.
Runs occurred at different times on the same development workspace; they are
descriptive observations and do not establish a speed advantage or regression.

| Earlier sessions | Result limit | Original baseline, ms | Candidate 2, ms | Candidate 3, ms |
|---:|---:|---:|---:|---:|
| 4 | 1 | 1.261 | 0.864 | 0.710 |
| 4 | 5 | 1.674 | 1.521 | 0.806 |
| 100 | 1 | 2.880 | 4.729 | 3.252 |
| 100 | 5 | 4.835 | 3.845 | 3.202 |
| 1,000 | 1 | 13.951 | 8.561 | 11.990 |
| 1,000 | 5 | 29.818 | 8.982 | 11.009 |

## Rejection work and remaining bounds

A separate authored review probe records the cases that require rejection or
reanalysis, with all input sessions, optional corruption instructions, raw
responses, source hashes, work counts, and three uninstrumented timings:

- [qualification-work-candidate3-native.json](qualification-work-candidate3-native.json)
- [qualification-work-candidate3-python.json](qualification-work-candidate3-python.json)
- [reproduction script](../../experiments/v011-proposal-qualification-work-probe.py)

All 24 paired response payloads across these six cases were identical between
Python and native after removing only `latency_ms` (three ordinary calls and
one instrumented call per case). Instrumented elapsed times are not used as
latency measurements.

| Authored review case | Qualification passes | Source checks, total / unique | Certified checks, total / unique | Clause parses | Application SELECTs |
|---|---:|---:|---:|---:|---:|
| Agenda after 8 old sessions | 2 | 0 / 0 | 0 / 0 | 0 | 8 |
| Agenda after 120 old sessions | 2 | 0 / 0 | 0 / 0 | 0 | 9 |
| Rejected field example | 3 | 10 / 10 | 10 / 10 | 3 | 9 |
| Rejected spelling invalidates another prose proposal | 3 | 10 / 10 | 10 / 10 | 3 | 9 |
| Comparable assignment | 1 | 97 / 97 | 97 / 97 | 2 | 11 |
| Identical text with deliberately damaged original turn | 2 | 193 / 97 | 192 / 96 | 4 | 13 |

The agenda cases fail the declaration-spelling requirement before any original
turn authentication is needed; zero checks do not mean the agenda was certified.
The damaged-source case demonstrates an actual extra pass: the invalid page is
never certified, while retained pages are rechecked under the same read snapshot.

At most 96 supplemental chronology rows are retained across leading chapters.
Each non-final qualification pass removes at least one proposal, so this step
can perform up to one more analysis than the number of proposals; that is a
resource bound, not constant work. Reanalysis can repeat source checks and pure
parsing. SQLite's chronological FTS query can still scan and sort more than the
96 rows returned. Neither the retained-candidate cap nor the six original work
fixtures establishes a fixed database-scan, CPU, or latency bound.

Candidate 1/2 observations and the candidate 2 rejection evidence are retained.
Independent replay and the final release gates must use the eventual committed
candidate 3 source rather than reusing candidate 2 acceptance results.
