# Language suitability experiment — completed recovery and decision

## Current continuation point

The interrupted experiment has been recovered and reviewed on 2026-11-17.
Formal run [44061948774](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44061948774)
completed successfully. Its frozen source remains
`40a8ce42b4131b511dcacd446d175b878b74a6f8`; its original evidence remains
`351770ce9950ba60f77e04847a1de386c44dac2c` on
`validation/language-selection-results-44061948774`. No timing worker was rerun
or replaced during recovery.

The original analyzer passed all 18 self-test groups again. A fresh offline
audit of all saved worker reports and ledgers reproduced the original analysis
exactly apart from the two explicitly different host-local byte-verification
fields. The result is 186/186 workers, 626,100 timed calls, 558,618 paired
complete-output comparisons, 1,252,200 ledger events, and zero mismatches or
audit errors. Recovery additionally verified 192 frozen source bindings from
Git. The original runner checked all 209 frozen files; the other 17 original
runtime/build/dataset inputs were not independently reread on this machine.

**Decision:** retain Python + C as the product architecture; do not start a
whole-project Rust rewrite on this evidence. Both `c_table` and `rust_table`
passed the registered ordinary-workload benefit gate, so preserve the shared
Unicode-table strategy as a local optimization candidate. None of the 99
same-strategy Rust/C comparisons met the registered material-benefit rule.
The other Rust candidates did not pass the ordinary benefit gate. This is a
performance-based decision, not a rejection based on implementation effort.
An independent full Rust service remains unimplemented and unmeasured.

Completed deliverables:

- [Chinese decision and recovery record](../../reports/language-selection-review-20261117/DECISION.zh.md).
- [Complete Chinese report and CSV tables](../../reports/language-selection-review-20261117/full-report/report.zh.md).
- [Formal figures](../../reports/language-selection-review-20261117/figures/).
- [Offline recovery verification](../../reports/language-selection-review-20261117/recovery-verification.json).
- [Independent statistics review](../../reports/language-selection-review-20261117/independent-statistical-review.json).
- [Independent correctness and scope review](../../reports/language-selection-review-20261117/independent-correctness-review.json).

There is no unfinished measurement or remaining decision gate for this research
run. Any production integration of the table strategy is a separate follow-up:
keep the production source, packaging, release tags, main and public README
unchanged in this experiment. Do not move the frozen formal/results branches
or reuse favorable cells as a new language-speed claim. The reproduction
commands and exact verification limits are in the decision document.

## Pre-completion checkpoint (historical)

At the preceding checkpoint, the formal six-round run was active:
[run 44061948774](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44061948774),
job `133965795078`, started 2026-11-17 10:07:57 UTC (18:07:57 Asia/Shanghai).
Its branch is `validation/language-selection-formal-1`, frozen at
`40a8ce42b4131b511dcacd446d175b878b74a6f8`. Do not move that branch or tune
candidates from intermediate numbers. Report-only commits on the research
branch do not change this run's source or evaluator.

The ten-arm preflight passed in
[run 44057893040](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44057893040):
30/30 workers, 51,160 calls, 46,044 paired complete outputs, 102,320 ledger events,
209 frozen file byte checks, zero mismatches and zero audit errors. All raw
evidence is saved at `e45ed136ea01647afec5c62783f57ac3bf55aa30`, branch
`validation/language-selection-results-44057893040`. It remains nonformal.
Both metadata candidates actually completed 120 / 1,009 / 96 calls across
synthetic / public / Unicode cohorts, with zero entry fallback.

Before report-only additions, all 69 experimental files in the hosted lab
matched the frozen source. Independent pre-launch review found no blocking
integration, timing-probe, scheduling or adoption-gate issue. The Chinese report
and figure utilities are prepared separately. See [SCOPE.zh.md](SCOPE.zh.md)
for the interpretation boundary, including the unmeasured full-service rewrite.

The original eight-arm preflight completed successfully in
[run 44054083791](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44054083791).
Its evidence commit is `cab30fdcd583deff1c39e2d3ce2f1de5daef3039`: 24 workers,
40,928 calls, 35,812 paired complete outputs, and zero audit errors. It is
explicitly nonformal and cannot establish adoption or a language speed ranking.

The ten-arm matrix adds `rust_metadata` and `c_metadata` for the full
bounded candidate metadata method. The eight earlier candidates remain in the
comparison. Both new kernels and their shared correctness checks are complete:
13 existing regressions, 128 direct cases, 11 SQL callback cases, 13 pre-install
guards, and the synthetic/public corpora pass for both. The integrated worker
also passes all 96 Unicode stress queries for each new candidate, with 96 native
completions and zero fallback. The full ten-arm candidate set has now passed the
hosted preflight and entered formal measurement.

The frozen ten-arm formal schedule has 186 workers and 626,100 timed calls,
including A/A controls. Main remains untouched.

The production baseline remains `234891619d7bed88ddf3fae37e7f3e1b14a808b6`.
This branch adds isolated experiments. It does not modify product sources,
the public README, main, release tags, retrieval rules, or database schema.

## Evidence status

- Equivalent Rust loops, C/Rust table implementations, and C/Rust complete
  window implementations were built and checked locally.
- The Node implementation includes pure-computation and persistent-bridge
  interfaces, exact Python code-point transport, and a pinned Unicode table.
- Complete local corpus replays matched the current implementation for the
  candidates tested before the execution environment became unavailable.
- The local executor then went offline before formal performance measurement.
  No local diagnostic timing is an adoption result.
- Unpublished source changes have been recovered through Git blobs. Some files
  match previously recorded hashes exactly; reconstructed host/evaluator files
  require fresh runner validation. Local predecessor checks are not proof that
  every recovered byte has already run.
- The local executor subsequently recovered. The restored analyzer passed its
  synthetic complete-matrix tests and deliberate rejection cases; these are
  evaluator tests, not product performance measurements.
- [Preflight 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44052140234)
  stopped before correctness replay or performance timing because Cargo's table
  build and the shared table shim had the same output directory/log name.
  The Cargo directory is now `rust-core-table`. The failed attempt remains on
  `validation/language-selection-results-44052140234`, commit
  `59afff7f8d5d40d8e7cc10a352e7a020fefb7bef`.
- Preflight 3 included the complete eight-arm matrix, Bash diagnostics,
  and a TypeScript type-erasure/runtime identity check. No candidate is adopted.
- [Preflight 2](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44053025545)
  passed the Rust, C-table, Rust-table, C/Rust owned-window, and full Node kernel
  checks. A Node guard report then attempted to read an older local report
  schema. The guard now explicitly requires this run's `checks/node.json`,
  checks its source, binary, and runtime identities, and rejects stale input.
  No timing worker ran. Evidence is retained at
  `767b591d4c3e80ec84ff9d9f85fb7374f71f7990`.

## Registered comparison

| Layer | Candidates |
| --- | --- |
| Current implementation | Python with the existing 22 C entry points |
| Same interface translation | Six equivalent Rust functions |
| Unicode processing organization | C-table and Rust-table using the same frozen mapping |
| Complete window computation | C-owned and Rust-owned with the same compatibility adapter |
| Complete bounded candidate metadata | C and Rust with identical SQL, parameter order, mutation and callback behavior |
| JavaScript | Warm kernel measurements and actual persistent Python/Node integration |
| TypeScript | Types-only facade, checking the identities of the executed JavaScript functions |
| Shell | Equivalent ASCII kernels in Bash; RPC, amortized batch cost, and cold start reported separately |
| Reference | Existing pure Python backend for output equivalence |

The formal whole-workload matrix uses six balanced rounds, two passes per
configuration, synthetic61, public1015, and a separately labeled Unicode stress
cohort. It includes direct and official-SDK MCP recall at character and token
budgets, fresh/unchanged/changed ingestion, process resources, startup, and A/A
controls. Ordinary and stress-only adoption decisions are separate.
A/A pairs precede main rounds 0, 2, and 4. Helper diagnostics run after the
whole-workload matrix and cannot trigger the production adoption gate.

## Historical continuation (superseded)

1. Read the active formal run above, `plan.json`, and `SCOPE.zh.md`.
2. If it is still active, let the registered run finish. Do not restart it or
   modify its frozen branch from partial timings.
3. Read the resulting `analysis.json` on
   `validation/language-selection-results-44061948774`. Check `audit.passed`,
   `audit.errors`, all expected workers, dispatch and hashes. A green workflow
   step alone is insufficient because partial evidence is deliberately saved.
4. Independently review paired statistics, A/A noise, key regressions and
   resources; preserve every failed attempt and unfavorable scenario.
5. Use `render_report.py` and `plot_report.py` on the real formal analysis to
   produce the Chinese research report, full tables and two main figures.
6. Save findings and the next continuation point under the user's Git identity.
   Never update production from an incomplete matrix or unresolved A/A noise.

All evidence branches use Afloat's verified commit identity. Shell diagnostics,
when present, remain separate from the ten whole-workload variants.
