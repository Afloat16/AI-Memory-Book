# Corrected frozen-source current-span allocation guard

The unchanged `v012-protected-current-span-review-v1` evaluator ran against
`021a384567db5aa64fde155f090d2eb399f55c03`, separately with the Python reference
and native backends. Each executed **482 actual production recall requests**:
two short-record sizes and budgets from 400 through 1,600 characters in steps
of five. This attempt therefore contains **964 new requests**, without replaying
or overwriting the original failed proposal or attempt1 evidence.

| Outcome, independently on each backend | Result |
|---|---:|
| Configurations completed | 482 |
| Original controls with current evidence present | 434 |
| Current evidence present after protected allocation | 434 |
| Previously present controls lost | 0 |
| Original unprotected-proposal regressions | 34 |
| Original regressions recovered | 34 / 34 |

The result is preservation of all 434 recorded positive controls and recovery
of the 34 previously observed allocation regressions. **It is not 482 / 482
answer completeness:** 48 tight-budget controls originally lacked the current
evidence and still do. These are configurations of one authored fixture,
not independent quality questions, a holdout or a speed benchmark.

The original review's exact pinned bytes remain in
`../evaluation/short-page-review-attempt1.json`. Only the 34 original regressions
have complete prior response payloads, which the frozen validator independently
checks. The other 448 original configurations have presence observations only;
no absent original payload has been reconstructed.

Both new backend directories retain every full compressed response and original
page follow-up, request journals, source/evaluator/native-binary identities and
completed reports. The saved driver receipts and logs identify actual commands
and return codes. The `*-independent-audit.json` files recheck compressed/raw
SHA-256, source stability, evaluator binding, every full row and its original
source coordinates, and recompute the 482-configuration summaries.

The cross-backend audit in `../resumed-revision-attempt2/` confirms exact equality
of all 482 guard response pairs after removing only `latency_ms`, with original
pages and other row fields unchanged. All earlier attempts remain available.
These guard passes do not themselves establish complete source acceptance,
general current-decision authority, or release/publication success.
