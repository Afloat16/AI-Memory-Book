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
