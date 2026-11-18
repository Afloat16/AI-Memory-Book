# Declaration and scope development diagnosis

The prospective protocol and 38-question fixture were committed at
`2d8edb5de4a259e6902bcec55072f5cd8b804f47` before these quality executions.
The fixture was authored after reviewing v0.11 limitations. It is development
evidence, not an independent holdout, an external-product score, an LLM answer
evaluation or a speed experiment. No gold labels or questions were changed
after the baseline results became visible.

## Retained baseline

Both actual backends executed source
`78cc906d81818a16884de7de2e613e5a56346f93` in a separate Git worktree:

| Backend | Responses | Independently checked matrix/source/budget | Auto first expected session |
|---|---:|---|---:|
| Python reference | 304 | Passed | 22/32 in each setting |
| Native | 304 | Passed | 22/32 in each setting |

The four settings are 1 or 5 results and 1,200 or 2,400 characters. Each has
38 original questions in both automatic and explicit relevance modes. The
32 answerable questions are counted once per setting; repeated settings and
backend executions are not independent quality questions.

For automatic mode, complete original evidence is present in 22/32 answerable
cases at limit 1 and 32/32 at limit 5, on both budgets and backends. The ten
incorrect first-session choices occur in the two project variants of each of
these scenarios: Chinese prose, unclassified agenda, cross-sentence qualifier,
per-field qualifier and ambiguous suffix qualifier.

The two unknown project requests return empty results in every setting. The
two missing-evidence questions return related context in every setting; this
does not measure generated answers or abstention. The two equal-time conflict
questions retain both declarations at limit 5, and only one declaration at
limit 1, which cannot contain both separate pages. No authority resolution is
claimed. Conflict coverage is reported separately from ordinary answerable
questions.

Each backend directory retains the exact dataset, all full replies and
project-scoped original-page follow-ups in `raw.jsonl.gz`, a pre-call journal,
source/import/backend/native-extension identities, the complete report and
the independent saved-record audit. Both original execution logs remain beside
the directories. No algorithmic quality failure is discarded.

## Candidate status

A candidate run will use a new directory after the candidate source is
committed. Current baseline observations do not establish candidate quality.
Comparisons must preserve all cases and disclose any first-session or evidence
regression, as well as explicit relevance-control payload changes.

## Retained short-page allocation review

An additional development review checks a specific interaction between short
source completion and the existing complete-current-turn excerpt route. It
uses the unchanged `same_page_session` fixture, two 180- or 230-character
supporting notes, and budgets 400 through 1,600 in increments of five:
482 configurations of two small constructed archives, not 482 independent
questions. This is separate from the frozen 38-question diagnostic.

The unguarded postprocessor loses a previously returned current turn in
34 configurations. At 450 characters with 180-character notes, the ordinary
allocation returns a 147-character excerpt of turn 1 containing the revision;
the postprocessor reallocates its space to a supporting note and returns a
124-character excerpt of turn 0 instead. Source hashes were unchanged during
that review. These are working-tree development observations, not measurements
of a released source or a performance comparison.

`short-page-review-attempt1.json` retains all 482 presence observations and the
complete before/after responses plus original-page reads for all 34
regressions. The other 448 original payloads were not retained; they are not
reconstructed or claimed independently reverified. The new guard evaluator
independently verifies all 34 complete original counterexamples, pins the
original probe/fixture/report, and will retain every new production response
on committed source. Guard verification remains pending until that run.
