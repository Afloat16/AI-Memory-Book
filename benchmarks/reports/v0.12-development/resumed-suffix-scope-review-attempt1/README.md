# Resumed v0.12 suffix-scope review: retained blocker

An independent review of candidate `01032a691abdc4fddfd10f61c9e61f260f9decb3`
found that its Chinese old-value explanation grammar accepts arbitrary text
following `，旧值已…`. This bypasses its intended qualifier and condition checks.
The frozen v0.11 baseline is `78cc906d81818a16884de7de2e613e5a56346f93`.
No production or evaluator file was edited for this probe.

The earlier source records `Production retry_limit=3`. The two later statements
are retained exactly in `probe.py` and every raw row:

- `Production retry_limit=99，旧值已撤销，此值仅用于 staging。`
- `Production retry_limit=99，旧值已撤销，pending staging approval。`

For 8 and 104 older records, the baseline retains an original decision while
the candidate promotes the later scoped/conditional statement in `current`
mode. These are four regression configurations of two authored examples, not
four independent quality questions. With only two older records, the baseline
already promotes the problematic statement; those failures remain visible.
The corresponding explicit relevance results are unchanged in all nine
configurations. The normal causal control, `Production retry_limit=7，旧值已因延迟测试失败而弃用。`,
is also retained: the candidate recovers it in all three sizes, including two
sizes where the baseline does not.

Each arm has 18 complete responses: three statement variants × three old-record
counts × two temporal modes. Every result includes its original project-scoped
page follow-up. The probe verifies every tracked runtime file against its
worktree's exact Git HEAD before and after execution and records the imported
package and Python reference backend. The saved-record audit independently
checks the closed request matrix, source slices, excerpt coordinates, project,
context framing, result limit and 1,200-character budget. It finds four new
incorrect promotions and zero relevance-payload changes.

## Retained files and reproduction

`baseline/` and `candidate/` contain unchanged original `report.json` and
`raw.json`. `audit.json` is the unchanged original saved-record check.
`acquisition.json` records the byte-identical copy and exact original scratch
paths; report paths were not rewritten. This folder is evidence of a blocking
development result, not acceptance of the candidate or a latency experiment.

Run the unchanged probe with fresh output paths and the corresponding immutable
worktrees:

```sh
PYTHONDONTWRITEBYTECODE=1 MEMORY_BOOK_TEXT_BACKEND=python \
python benchmarks/reports/v0.12-development/resumed-suffix-scope-review-attempt1/probe.py \
  --source /absolute/path/to/v011-baseline \
  --output /absolute/path/to/new-suffix-review/baseline

PYTHONDONTWRITEBYTECODE=1 MEMORY_BOOK_TEXT_BACKEND=python \
python benchmarks/reports/v0.12-development/resumed-suffix-scope-review-attempt1/probe.py \
  --source /absolute/path/to/01032a69-candidate \
  --output /absolute/path/to/new-suffix-review/candidate
```

The original executions used the checkout paths recorded in each report under
`before.package`; all files and outputs shown here were captured in this
conversation. Future corrections require a new result directory and must keep
these failing records unchanged.
