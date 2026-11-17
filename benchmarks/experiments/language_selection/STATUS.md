# Language suitability experiment — preflight checkpoint

## Current continuation point

The ten-arm preflight is running in
[run 44057893040](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44057893040),
job `133951846014`, from frozen candidate/evaluator commit
`40a8ce42b4131b511dcacd446d175b878b74a6f8`. All 69 experimental source files
in the hosted lab match that commit. Independent pre-launch review found no
blocking integration, timing-probe, scheduling or adoption-gate issue.
The report and figure utilities are being prepared separately; they do not
change the frozen candidates or evaluator. See [SCOPE.zh.md](SCOPE.zh.md)
for the interpretation boundary, including the unmeasured full-service rewrite.

The original eight-arm preflight completed successfully in
[run 44054083791](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44054083791).
Its evidence commit is `cab30fdcd583deff1c39e2d3ce2f1de5daef3039`: 24 workers,
40,928 calls, 35,812 paired complete outputs, and zero audit errors. It is
explicitly nonformal and cannot establish adoption or a language speed ranking.

The next prospective matrix adds `rust_metadata` and `c_metadata` for the full
bounded candidate metadata method. The eight earlier candidates remain in the
comparison. Both new kernels and their shared correctness checks are complete:
13 existing regressions, 128 direct cases, 11 SQL callback cases, 13 pre-install
guards, and the synthetic/public corpora pass for both. The integrated worker
also passes all 96 Unicode stress queries for each new candidate, with 96 native
completions and zero fallback. Do not start the formal branch until the ten-arm
candidate set passes the hosted preflight.

The planned ten-arm formal schedule has 186 workers and 626,100 timed calls,
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

## Continuation

1. Read `plan.json`, the candidate READMEs, and the workflow.
2. Commit and review the complete recovered evaluator and candidates.
3. Push a new `validation/language-selection-preflight-*` branch to execute
   the preflight protocol. It has one round and never yields adoption claims.
4. Review all correctness, actual-dispatch, whole-output, and preservation
   evidence before starting `validation/language-selection-formal-1`.
5. Keep all failed attempts and raw ledgers. Never update production on an
   incomplete matrix or a result explained by A/A noise.

All evidence branches use Afloat's verified commit identity. Shell diagnostics,
when present, remain separate from the ten whole-workload variants.
