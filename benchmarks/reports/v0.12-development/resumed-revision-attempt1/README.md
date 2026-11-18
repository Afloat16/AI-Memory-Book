# Frozen v0.12 declaration replay after interruption

This attempt ran the already committed `v012-declaration-scope-development-v1`
protocol without changing its questions, gold labels, source checks or scoring.
It is an authored development/regression diagnosis, not an independent holdout,
generated-answer evaluation, external-product comparison or speed benchmark.

## Actual execution

- Baseline: `78cc906d81818a16884de7de2e613e5a56346f93` (v0.11.0).
- Candidate: `01032a691abdc4fddfd10f61c9e61f260f9decb3` (v0.12 candidate).
- Both Python and native backends ran both arms in the restored environment.
- Each arm has 38 questions × two budgets × two result limits × two temporal
  modes = **304 actual requests**; four arms total **1,216 requests**.
- The question inventory is 32 answerable, two conflicting-record, two
  missing-evidence and two absent-project questions. Several scenarios reuse
  a question across two similar project IDs; these are not independent tasks.
- Backends ran concurrently. Diagnostic timings are retained, with no latency
  comparison or performance claim.

The previous baseline outputs in `../evaluation/` remain unchanged. These new
baseline executions permit same-environment pair audits against real current
worktrees; no old absolute source path or result has been rewritten.

## Result on each backend

The following applies separately at **1,200 and 2,400 characters**:

| Auto-mode result | Baseline | Candidate |
|---|---:|---:|
| Expected first source, limit 1 | 22 / 32 | 30 / 32 |
| Complete required evidence, limit 1 | 22 / 32 | 30 / 32 |
| Expected first source, limit 5 | 22 / 32 | 30 / 32 |
| Complete required evidence, limit 5 | 32 / 32 | 32 / 32 |

Each backend has 32 changed scored responses, **zero per-response regressions**
under the frozen comparison rule, and **zero changes to the full relevance
control payloads** (`results`, `context`, `candidate_count`). The eight improved
questions are four scenarios across two project IDs each: a nondecision agenda,
an unrelated sentence supplying a query facet, different scopes attached to
different fields, and a contradictory suffix qualifier.

The remaining two expected-first-source failures are the Chinese prose
scenario (`chinese-prose:0`, `chinese-prose:1`). The latest text says the retry
count has been adjusted, but limit-one recall still selects the earlier
decision. Limit-five recall includes its required latest evidence. The replay
does not establish general Chinese natural-language revision recognition.

Both equally timed conflicting declarations are present at limit five; limit
one returns one declaration and does not resolve authority. Both missing-
evidence queries return related context. Both absent-project queries return no
results. These categories stay separate from the 32 answerable questions.

## Evidence and independent checks

Each arm contains `report.json`, `dataset.json`, `journal.jsonl`, and the
losslessly compressed complete `raw.jsonl.gz`. Reports bind the real imported
package, worktree commit, every tracked runtime file, loaded native binary,
interpreter/platform and frozen evaluator before and after execution.

`python-pair-audit.json` and `native-pair-audit.json` were produced by the
unchanged `benchmarks.v012_revision_pair_audit` command after it independently
recomputed every source slice, original-page read, request identity, budget,
scope, score and complete response matrix. `execution.json`, the per-backend
driver receipts and sibling logs preserve the commands and return codes.

`verified-summary.json` records the audited summaries and guard results from
the separate `../resumed-short-page-guard-attempt1/` attempt. A further
cross-backend inspection found identical complete response objects, original
pages and scores in all 304 baseline pairs and all 304 candidate pairs after
removing only `latency_ms`; its saved record is `cross-backend-audit.json`.

This completed diagnostic does not by itself accept the v0.12 source or pass
the engineering, directory, full-suite, CI, packaging or publication gates.
