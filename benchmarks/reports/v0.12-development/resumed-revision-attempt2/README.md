# Corrected frozen-source declaration replay

This attempt executes the unchanged registered
`v012-declaration-scope-development-v1` evaluator against corrected source
`021a384567db5aa64fde155f090d2eb399f55c03` (`RECALL_VERSION=21`). Both the
Python reference and native candidate arms completed **304 actual requests**,
for **608 newly executed requests** in this attempt.

The same-environment baseline arms from `../resumed-revision-attempt1/` are
reused without modification. They each executed 304 requests on published
v0.11 source `78cc906d81818a16884de7de2e613e5a56346f93`. The unchanged pair
auditor independently verifies their actual source inventories against that
exact Git commit and requires the same backend, interpreter, platform and
frozen evaluator as the new candidate. No second baseline execution is claimed.

The 38-question fixture contains 32 answerable questions, two equal-time
conflicts, two missing-evidence questions and two absent-project questions.
It is authored development/regression data with repeated scenario structure
across pairs of similar projects, not an independent holdout or model-answer
accuracy test. Backends ran concurrently; no latency comparison is claimed.

## Actual result on each backend

These results apply separately at both **1,200 and 2,400 characters**:

| Auto-mode outcome | v0.11 baseline | Corrected v0.12 candidate |
|---|---:|---:|
| Expected first source, limit 1 | 22 / 32 | 30 / 32 |
| Complete required evidence, limit 1 | 22 / 32 | 30 / 32 |
| Expected first source, limit 5 | 22 / 32 | 30 / 32 |
| Complete required evidence, limit 5 | 32 / 32 | 32 / 32 |

Each backend has 32 changed scored responses, zero per-response regressions
under the frozen rule, and zero relevance-control payload changes. The eight
improved questions remain the agenda, cross-sentence facet, per-field facet
and suffix-facet scenarios, each tested in two projects.

The two remaining expected-first-source failures remain `chinese-prose:0` and
`chinese-prose:1`. For the Chinese prose statement that the production retry
count has been adjusted, limit-one recall still chooses the earlier decision;
limit five includes the required newer evidence. General Chinese revision
recognition is not established.

At both budgets, limit five includes both equally timed conflicting records;
limit one includes only one and does not resolve authority. Both missing-
evidence questions return related context. Both absent-project questions
return no results. These categories are not added to the answerable denominator.

## Evidence and audits

The two `*-candidate/` directories contain complete compressed raw responses,
original-page follow-ups, attempted/completed request journals, dataset copies,
and before/after bindings to the imported package, exact worktree source,
loaded native binary and evaluator. Driver receipts and logs retain every
executed command and its zero exit code.

`python-pair-audit.json` and `native-pair-audit.json` independently recompute
every saved request identity, source slice, page follow-up, scope, character
budget and score, and check the closed 304-response matrix. Both reports bind
the requested baseline and candidate commits explicitly.

`verified-summary.json` retains all summaries and the residual failures.
`cross-backend-audit.json` additionally checks exact equality of all 304 new
revision response pairs and all 482 new guard response pairs, including their
original pages and scores, after removing only `latency_ms`. No other response
field is ignored.

The prior source's attempt1 results are retained unchanged. This completed
diagnostic and the separate guard do not replace the engineering, directory,
full-suite, exact-commit CI or publication gates.
