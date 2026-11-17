# Language suitability experiment — recovery checkpoint

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

## Registered comparison

| Layer | Candidates |
| --- | --- |
| Current implementation | Python with the existing 22 C entry points |
| Same interface translation | Six equivalent Rust functions |
| Unicode processing organization | C-table and Rust-table using the same frozen mapping |
| Complete window computation | C-owned and Rust-owned with the same compatibility adapter |
| JavaScript | Warm kernel measurements and actual persistent Python/Node integration |
| Reference | Existing pure Python backend for output equivalence |

The formal whole-workload matrix uses six balanced rounds, two passes per
configuration, synthetic61, public1015, and a separately labeled Unicode stress
cohort. It includes direct and official-SDK MCP recall at character and token
budgets, fresh/unchanged/changed ingestion, process resources, startup, and A/A
controls. Ordinary and stress-only adoption decisions are separate.

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
