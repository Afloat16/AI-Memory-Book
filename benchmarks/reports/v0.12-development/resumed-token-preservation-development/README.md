# Exact-token preservation regression and correction

The complete frozen-candidate suite exposed a real compatibility regression in
`test_every_old_packed_block_and_metadata_are_preserved`. This was not a change
in the test's intended contract: every character-only evidence block accepted
by rank-order first-fit token packing must remain byte-for-byte identical,
including its returned metadata, when exact-token recall uses the same query
and character budget.

## Reproduction retained

`attempt1-before/` reran that unchanged test on both the Python and native
backends using the real optional tokenizers. Both executions failed. Their
complete logs, exact commands, return codes and runtime/test hashes remain.
The working files were unchanged throughout those two reproductions.

The short-page completion pass ran only when `token_counter is None`. Thus the
character-only API could expose a completed short record while exact-token
recall constructed its supposedly equivalent `legacy` input from the older
allocation. The token assembler then retained or supplemented a different
excerpt even when the complete character-only block fit the token cap.

## Minimal production correction

Both recall routes now construct the same protected character allocation
before building `legacy` blocks. The existing exact-token assembler still
applies its original rank-order first-fit and intact-source-unit supplementation
to those blocks. `token_budget.py` is unchanged.

The `current_spans` protection remains active for both routes: an allowance
already containing an authenticated current turn cannot donate its space, and
its fixed excerpt cannot receive space it will not render. Source selection,
citations, token counting and source-unit restrictions are not relaxed.

This intentionally corrects exact-token output when the new character
completion pass is active. The initial v0.12 plan's statement that optional
token recall retained its prior allocation is no longer the final behavior;
the preserved public contract is compatibility with the actual current
character-only response. No old token-budget experiment is retroactively
relabelled as a measurement of these new runtime bytes.

## Focused verification

`attempt2-after/` ran these seven modules on each backend:

- `tests.test_token_budget`
- `tests.test_current_token_recall`
- `tests.test_current_turn_recall`
- `tests.test_context_budget`
- `tests.test_token_budget_mcp`
- `tests.test_native_budget_eval`
- `tests.test_short_page_token_preservation`

**Python: 57 passed, zero skips. Native: 57 passed, zero skips.** Both real
`cl100k_base` and `o200k_base` tokenizers were exercised. The working runtime and
tracked test bytes remained unchanged during the complete pair of runs.
Independent declaration-parser fixes present in that working tree are bound
by the saved `store.py` hash; these are development checks, not final immutable
source acceptance.

The new integration tests specifically cover a completed short page with an
exact-fitting or generous token cap, and a same-page current correction
alongside a short memo and a long potential donor. They require identical
fitting legacy blocks and metadata, exact counts and both caps, and prevent
token supplementation from returning the old turn. The old regression test
and its expected results were not weakened or edited.

The complete source gates must be rerun after committing the combined fixes.
