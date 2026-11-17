# Language suitability experiment — preflight checkpoint

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
- The next preflight includes the complete eight-arm matrix, Bash diagnostics,
  and a TypeScript type-erasure/runtime identity check. No candidate is adopted.

## Registered comparison

| Layer | Candidates |
| --- | --- |
| Current implementation | Python with the existing 22 C entry points |
| Same interface translation | Six equivalent Rust functions |
| Unicode processing organization | C-table and Rust-table using the same frozen mapping |
| Complete window computation | C-owned and Rust-owned with the same compatibility adapter |
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
when present, remain separate from the eight whole-workload variants.
