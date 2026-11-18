# Protected current-span guard after interruption

This attempt runs the previously committed
`v012-protected-current-span-review-v1` evaluator against the exact source
`01032a691abdc4fddfd10f61c9e61f260f9decb3`, separately with the Python reference
and native backends. It exercises the production recall path once per request;
it does not double-apply an allocation helper.

Each backend executes **482 configurations**: two short-record sizes (180 and
230 characters) and character budgets from 400 through 1,600 in steps of five.
The two actual runs total **964 requests**. These are variations of the same
authored fixture, not 964 independent questions or a measured speed result.

| Frozen guard outcome, per backend | Result |
|---|---:|
| Executed configurations | 482 |
| Prior controls with current evidence present | 434 |
| Current evidence present with protected allocation | 434 |
| Previously present controls lost | 0 |
| Original unprotected-proposal regressions | 34 |
| Original regressions recovered | 34 / 34 |

**482 completed checks does not mean 482 contexts contain the current answer.**
Forty-eight tight-budget configurations had no current evidence in the recorded
control and still have none. The guard establishes preservation of the 434
recorded positive controls and recovery of the 34 specifically observed
unprotected-allocation regressions.

The original review is retained at
`../evaluation/short-page-review-attempt1.json` with its exact pinned hash.
Complete prior response payloads exist for the 34 original regressions and are
independently checked; the other 448 original configurations contain presence
observations only. No missing original response has been reconstructed.

Each new backend directory contains its complete compressed raw responses,
original-page follow-ups, attempted/completed request journal and source-bound
report. Driver receipts and sibling logs preserve the exact commands and
return codes. The `*-independent-audit.json` records independently verify
archive and raw hashes, evaluator identity, source stability, every request,
excerpt, original-page body, timestamp, scope and full integer source mapping,
then recompute the entire 482-configuration summary using the frozen validator.

The accepted guard result is confined to this fixture. It is not a general
proof of completeness, current-decision authority or versioned publication.
