# Round five: v0.3.3 development and recovery record

## Baseline and scope

Work starts from `de6e2652572c4867cda2aac5637a4a6630638c7e` (the
publication receipt for v0.3.2). The immutable published release is
`692fb959ddf8934c5f516ba3d74ceb4385a2fa82`. Comparisons in this round must use
v0.3.2 as the preceding version, not v0.3.1. All earlier tags, experiment
bindings, failed attempts, and raw measurements remain historical evidence.

The user's requested direction is better performance and stronger competitive
results, with small, frequent remote Git checkpoints to survive interrupted
sessions. This checkpoint contains a plan, not a performance result.

## Proposed work

1. Remove avoidable work on unchanged session imports, while preserving
   normalization, inherited metadata, source addresses, revision behavior,
   transaction correctness, and exact public responses.
2. Profile and reduce repeated default lexical recall and token assembly work.
   Require complete non-timing output equality against v0.3.2, including
   scores, result order, source spans, warnings, budgets, and cache behavior.
3. Keep zero-dependency lexical operation, existing storage compatibility,
   and opt-in semantic behavior. Do not introduce a persistent unbounded cache.
4. Measure changed and unchanged imports, uncached native recall, and actual
   official-SDK MCP calls separately. Preserve setup, storage and memory costs.

## Evidence policy

Use the existing synthetic61 and public1015 cohorts as **old regression data**.
They are not a fresh quality holdout. Development profiles identify work and
are not speed claims. After selecting and committing a candidate, execute a
fixed balanced baseline/candidate comparison, retaining every sample, attempt,
negative cell and complete-output hash. Do not restart successful cells to
choose faster measurements. Publish the environment, exact source identities,
query counts and all measured configurations with the results.

The intended substantive gain is at least 20% lower unchanged-import time,
and an observable reduction in recall overhead without quality loss. Actual
recall improvements, regressions and uncertainty will be reported per setting;
there is no assumed aggregate performance pass before measurement. Source,
scope, token/character caps and full-output correctness are mandatory gates.

The frozen competitor cohort previously measured claude-mem 15.18.1
(`c4a9f5725f420bf9c6e866cdd3b94bd36498af09`), ai-memory v3.4.5
(`ee73c04c542fa41ca629b046deb4ac108518f407`), and billion-context
(`9674cfafbc78c50245ae0d887483d3d6ce880c15`). Those historical measurements
cannot be relabeled v0.3.3 or used to claim new whole-product speed ratios.
Exact-output improvements preserve measured evidence quality; they do not
establish improved recall or universal superiority over other repositories.
In particular, billion-context still leads the last measured component's
recall, completeness and adapter latency. Any quality-changing candidate
needs separate evaluation; all 896 scored Hotpot IDs are development data.

## Checkpoint and interruption procedure

- Branch: `optimization/round5-20261114`.
- Save the plan first; commit each coherent implementation and correctness
  checkpoint before starting long measurements.
- Save measurement ledgers incrementally and commit completed worker results.
- Prefer ordinary Git transport. If unavailable, use bounded Git tree/content
  operations with explicit parent and expected ref, and verify the remote SHA.
- Preserve failed/incomplete attempts. Resume only work that has not already
  completed; never overwrite an earlier performance record.
- Keep the repository usable at every checkpoint. Record source SHAs and the
  next exact action here so another session can resume from the remote branch.

## Current status

Baseline and earlier evidence recovered. Implementation and validation are in
progress; no v0.3.3 benchmark, quality improvement, or release is claimed yet.
