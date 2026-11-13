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

### First implementation checkpoint

The candidate skips pagination and a reserved write lock for unchanged
imports, after checking inherited metadata, settings, stored content hash,
counts and revision in one SQLite SELECT snapshot. A miss still executes the
original checked write transaction. The returned revision is the revision of
that read snapshot; an overlapping writer may commit later. It is not a
promise to return the latest revision after another connection commits.

Default recall now builds fusion dictionaries only when the exact and stem
routes differ, and computes each repeated directory weight once per call.
Supplemental token evidence is scored from its original span, avoiding
Unicode normalization triggered solely by presentation ellipses. Ranking,
rendered text, source coordinates and token counting are unchanged.

The first targeted runs passed 95 runtime tests and 56 token tests. Artificial
differential checks preserve all 300 complete recall payloads and all 540
token-assembly outcomes against the baseline. These are development checks,
not corpus performance measurements. Their hashes, microdiagnostics and
logs are retained in `benchmarks/reports/round5-development/`.

The initial broad environment check was not a valid candidate test: a sparse
checkout lacked historical report fixtures, and a separately imported
baseline did not identify the working checkout under provenance guards.
Those failures are retained locally; hydrate the required fixtures and run
the complete suite against an exact committed candidate before acceptance.

### Candidate A development diagnostic

Candidate A is saved at `ee048f39a28cc944aafce938811f4b71ed8efb4d`, runtime
SHA-256 `1db3d52ae8b3324bf0a0822427b3bedc25825e5ea195f51efe5be3ce4bfe0c3f`.
The fixed earlier native diagnostic completed all 4,096 calls (128 old
queries per cohort, four budgets, AB/BA). All 2,048 paired complete outputs
match. The complete raw observations are retained in
`benchmarks/reports/round5-development/native-pair.json.gz.b64`, with an
uncompressed summary beside them.

Results are mixed: public native token512/1024/2048 p95 changes are
-12.46%/-8.07%/-15.98%, while public char4000 p95 is +23.06% and synthetic
char4000 is +8.84%. Public char4000 p50 is approximately +0.87%. These small
development samples do not establish the cause of the tail variation or a
release speedup. Preserve every cell. A further mechanically justified
candidate may reduce SQLite-row materialization costs before final binding;
do not repeat this diagnostic to select a favorable run.

### Candidate B selection before the fixed comparison

B keeps the previous changes and iterates the wide SQLite row projections
instead of repeatedly looking up every column name. The narrow three-column
route is unchanged. SQL, scope, limits, ordering, source snapshots and floating
point calculations are unchanged. Its runtime SHA-256 is
`5c005e1ad30c3fe9441bb0ee1c79dac6a2536d93e6a9ab9b7fbcbe71ef00c790`.

The isolated wide-row conversion diagnostics reduce that operation's time,
but the single 128-query cProfile run has **5.31% higher total time**. This is
not evidence of end-to-end acceleration. The narrower Python work and simple
implementation justify testing B as the final candidate; they do not justify
assuming it passes. All A/B profiles, microtimings and negative observations
are retained under `benchmarks/reports/round5-development/candidate-b/`.
All 128 public profile payloads match A, all 300 artificial payloads match
v0.3.2, and 81 targeted tests pass. No quality selection has been changed.

The fixed comparison will retain all **66,248 calls**, using four balanced
AB/BA/BA/AB rounds, both old cohorts, five native configurations (4,000 and
100,000 characters; 512, 1,024 and 2,048 tokens), and actual MCP character and
1,024-token calls. Each worker's claim and completed raw results will be
committed on `validation/round5-performance-20261114`. This follows the
repository's existing `validation/**` convention so raw-result checkpoints
do not launch a new nine-job application CI run each time.
