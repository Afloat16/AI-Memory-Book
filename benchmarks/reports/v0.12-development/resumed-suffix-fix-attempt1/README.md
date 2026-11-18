# Declaration suffix and reporting-label correction

This development fix responds to the retained
[`resumed-suffix-scope-review-attempt1`](../resumed-suffix-scope-review-attempt1/)
and the original core regression in `resumed-full-suite-attempt1`. It does not
change either historical gold data or the old core test's expectations.

## Changes

- Chinese old-value explanations now require a complete withdrawal ending.
  An optional `因 … 而` reason uses the same no-new-binding/condition/scope checks
  as an English `because` reason. Arbitrary text after `旧值已…`, additional
  comma-separated clauses and trailing scope qualifiers cannot establish
  comparability. Unsupported text remains available by ordinary relevance.
- Complete standalone reporting labels such as `Original`, `Corrected`,
  `Initial` and `Revised` no longer split otherwise equivalent field
  declarations. This is an exact whole-prefix grammar; it does not remove
  arbitrary words from a production/staging/environment qualifier.
- New production-recall regressions cover Chinese and ASCII commas, assignment
  and prose declarations, original-pool and supplemental candidates, explicit
  scope/condition suffixes, legitimate causal updates, and distinct environments.

## Actual checks

`before.log` retains the failing check against the unfixed parser: six test
methods (five new methods plus the unchanged core case), with 43 failed
subcases/assertions. These failures are not 43 independent benchmark questions.
`after-python.log` passes those six methods after the correction.

`focused-native.log` passes 84 methods across suffix/authority/proposal/core
checks. The subsequent wider relevant checks use the real Python reference
and native backends:

| Execution | Discovered | Passed | Skipped | Failed/errors |
|---|---:|---:|---:|---:|
| `extended-native` | 128 | 128 | 0 | 0 |
| `extended-python` | 128 | 127 | 1 | 0 |

The one Python skip is the existing native-only comparison. Each `extended-*.json`
records the exact command and the store, budget helper and test-file hashes
before and after execution; those files were unchanged during each run. The
store snapshot includes the concurrent exact-token allocation correction, so
these results describe the recorded integrated working tree. They are not a
claim that a release commit has passed its complete suite.

Afterwards, one over-restrictive subcase about different reporting labels on
the same actual environment was removed from the new test; the three genuinely
different-environment cases remain. `final-scope-tests.log` passes all five new
test methods with that final test content. No previously existing test was
changed. Final committed-source replays, complete-suite checks and delivery
gates remain separate.
