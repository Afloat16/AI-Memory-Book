# v0.3.4 optimization and recovery checkpoint

Status: candidate A completed its source CI, development comparison and all 2,304 historical compatibility calls. Its roughly 1% recall improvement is insufficient for the registered formal goals, so A will not advance. Candidate B implementation and directed correctness checks are complete; its source is being frozen before any B performance measurement. Published v0.3.3 remains the baseline and current release; no v0.3.4 runtime is approved.

## User goal and immutable baseline

The user requests another measurable improvement, continuing progress against comparison repositories, and frequent remote commits so conversation/blob interruptions do not lose the work. Baseline tag `v0.3.3` identifies source `796cedfd1f5368144037a1fb72292b8d13884b8c`, runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`. Main starts at its publication-receipt commit `e51498d3c797146e5a1ce94461f0d767fc732541`.

## Work and acceptance

The [round-six plan](../benchmarks/experiments/round6-plan.json) retains the fixed 56,784-call, four-round, twelve-cell paired native/actual-MCP matrix. Numerical gates remain 10% aggregate p95, 15% at least one public native-token p95, and 10% public actual-MCP token1024 p95 improvement; no pooled p50/p95 regression may exceed 5%. Both versions now contain the same bounded exact-count memo, so both start naturally empty and both are observed. Every resource mean and adverse sample is retained; increases over 10% require separate cause assessment and independent review.

Initial code-supported targets are atomic new-database schema creation, repeated request-local retrieval work identified from old-data profiles, and optional command-specific lazy imports. Atomic schema creation must preserve rollback, unrelated-database rejection, existing-archive behavior and complete initial schema. No implementation or version-only edit is an accepted speed result.

Historical Hotpot256 output compatibility is checked against all 2,304 previously reproduced complete hashes. A new third-party component comparison requires a separate plan, exact source/evaluator/dependency freeze and fresh deterministic ID-only selection before any scoring. Historical competing quality and speed advantages remain visible. Claims must follow the new measured boundaries, not the user's desired result.

## Ownership and durable execution

- Runtime work: `store.py` and focused new regression cases, after concrete hypothesis review.
- Measurement work: new round6 controllers, independent audits, ledgers and hosted checkpoint workflows; immutable round4 primitives may be reused.
- Comparative evidence: new round6 fresh-selection/comparison controls and fair adapter boundaries.
- Coordinator: version changes, explicit preregistration, review, remote commits, exact-source CI and any accepted release.

Incremental work is checkpointed on `validation/v034-round6-work`. This branch avoids rerunning the full CI matrix for each report-only checkpoint; the final candidate will be sent to `optimization/round6-v0.3.4` for all nine exact-source CI jobs. Main and release tags advance only after applicable acceptance and package gates. Existing tags, raw benchmark reports and original acceptance decisions are immutable.

## Recovery instructions

Read this file and the plan, then inspect the latest remote work-branch commit and any new round6 binding/run records. Do not replay an already claimed unchanged formal experiment or select a favorable repeat. Resume incomplete work from retained per-worker ledgers only when the original controller permits it; otherwise preserve the interruption and register a materially justified continuation. Keep newly completed work in remote Git before starting long measurements.


## Command loading checkpoint

The package exposes the same `MemoryBook` class lazily, keeping its original identity, star import and discovery. CLI help/version now load only command metadata; transcript format names live in a lightweight shared module, and archive, capture configuration and command-specific helpers load only when used. Explicit database commands avoid unrelated capture configuration. The [correctness receipt](../benchmarks/reports/round6-command-correctness.json) records 92 passing tests, including four isolated process checks of imports, type hints, class overrides and real database creation. This is an implementation/correctness checkpoint, not a measured CLI speed claim or final-source release approval.


## Candidate A source checkpoint

Version metadata and installers now identify candidate v0.3.4. Runtime SHA256 is `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242` (17 Python files). The new archive schema runs under one immediate transaction with a locked empty/schema recheck; partial failures roll back and close, and competing initializers safely recheck. Native FTS results carry already-read narrow metadata within the same recall, avoiding a second union query. All candidate-directory checks remain; custom factories and restrictive/uninspectable SQLite limits keep the original query path. Python 3.10 uses that conservative metadata fallback.

[Candidate correctness](../benchmarks/reports/round6-candidate-a-correctness.json) records the overlapping 40-test protocol/release/startup check and final 10-test atomic/metadata suite. [Baseline diagnostics](../benchmarks/reports/round6-development/baseline-profile/manifest.json) preserve all 4,732 old-data cProfile calls and 1,183 operation-count calls, including preflight failure evidence. These are diagnostic observations, not an accepted speed result.

The frozen source commit is `df35007c29e4af61dd96146232fe4651cfc74391`. [Source CI receipt](../benchmarks/reports/round6-source-ci.json) records all nine jobs passing, including Python 3.10/3.12/3.13, actual MCP, three installer platforms, reader browser and container. [Candidate diagnostics](../benchmarks/reports/round6-development/candidate-a-profile/manifest.json) preserve all 4,732 complete payload matches and all eight positive/negative cProfile cells. Across those four configurations the candidate removes 4,244 execute calls and 4,244 fetchall calls; this is an operation-count observation, not a latency gate.

Development bindings were committed remotely at `06087c7442463f84ed5313f35ea22b7050cf1863` before the single hosted run [43592983218](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43592983218). Native and actual-MCP stages publish their own per-worker ledgers and independent audits to `validation/v034-round6-development-<surface>-<run>-1` branches. The [historical zero-call preflight](../benchmarks/reports/round6-development/hotpot-preflight/zero-call-verification.json) verified all fixed inputs without consuming the actual compatibility claim. The sole actual [historical compatibility run](../benchmarks/reports/round6-hotpot-compatibility.summary.json) then matched all 2,304 complete outputs (1,536 native and 768 component); its [independent saved-ledger audit](../benchmarks/reports/round6-hotpot-compatibility.audit.json) verifies all 4,608 start/finish events and unchanged source/index records without repeating retrieval. The original claim and compressed raw report/ledger are preserved.

Fresh-comparison control tests now cover independent source/evaluator/asset/ID-manifest commits and adverse results. No new question IDs have been selected or scored. Runtime release approval remains absent. Next: preserve and inspect development measurements, then bind the independent formal comparison under the original 10/15/10 gates. The final release commit still needs its own nine-job CI and package/public-installer verification.


## Candidate A result and candidate B registration

The single development run completed and both hosted and local saved-result audits passed: 22,988 calls, 11,494 complete output pairs and 45,976 ledger events. [Complete development review](../benchmarks/reports/round6-development-43592983218-review.json) retains all nine latency cells, all 55 resource comparisons, every worker sample and every adverse observation. The native eight-cell geometric p95 improvement is 0.9473%; best public native-token p95 improves 1.2411%; actual public MCP token1024 p95 is 6.124870 to 6.061988 ms (1.0267%). These two-round diagnostics do not satisfy or evaluate the formal four-round gates. A is not approved, and no A formal timing will be run.

A does establish an empty-database creation improvement: native means drop from 26.333329 to 5.395540 ms for the synthetic cohort and 23.158578 to 5.471238 ms for the public cohort; the separate MCP-stage construction means drop 25.265979 to 4.238660 ms. Actual MCP initialization improves only 0.6194%, which is a different boundary. The two small synthetic pooled p95 regressions and all eight native round-level adverse metrics remain recorded. No resource mean crosses the 10% review threshold.

The [candidate B plan](../benchmarks/experiments/round6-candidate-b-plan.json) proposes a narrow two-stage FTS route for demonstrably dense project rowid intervals. It preserves global BM25 and full cutoff ties, leaving final page-ID sorting and metadata decoding to SQLite. Actual schema validation and customization guards are prerequisites, including trace callbacks that could reenter and mutate the connection. Unknown or uncertified cases retain the old route. This is a performance hypothesis, not a measured B improvement.

The two workflows now name separate B bindings explicitly. A's original binding files, claims, controller identity and result branches remain unchanged. B must have materially different frozen runtime source before its own single development run, historical compatibility and any formal run. The original 10/15/10 thresholds and all evidence-preservation rules remain unchanged.


## Candidate B correctness checkpoint

B runtime SHA256 is `01ce749679af461d03c3499d5423ffa82d73fe190fb318327301b58a643edf52` across 17 Python files. [Implementation verification](../benchmarks/reports/round6-candidate-b-correctness.json) retains the initial custom-connector regression, its native-factory identity fix, and all directed reruns: the final 14 core cases pass. The independent [guard audit](../benchmarks/reports/round6-candidate-b-guard-audit.json) adds five tests covering ten concrete cases, including late global adapters, real non-rowid-alias schema, external factories and a concurrent WAL writer between the two ranking stages. A second route-entry guard closes the late-customization gap found by that review. Test totals overlap and must not be summed as unique tests.

No B profile, development measurement, formal measurement or fresh competitor scoring has run at this correctness checkpoint. Freeze this exact source, run its full CI, create separately committed B development bindings and retain the complete results before deciding whether to advance.


## Candidate B frozen development checkpoint

Source `e89737ce82baffd349e84d01184113142c0de602` is frozen at runtime `01ce749679af461d03c3499d5423ffa82d73fe190fb318327301b58a643edf52`. Its [nine-job source CI](../benchmarks/reports/round6-candidate-b-source-ci.json) passed. The two B bindings were committed at `4be120e1401282e3cdf2212191f64a9ec4e76620` before the single [hosted development run 43595785770](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43595785770).

The [B non-scored profile](../benchmarks/reports/round6-development/candidate-b-profile/manifest.json) completed all 4,732 old-data calls with identical complete payload hashes. It preserves all eight instrumented cells, including public diagnostic-time increases of approximately 25.30%, 10.42%, 31.07% and 23.79%; profiler overhead and the unbalanced diagnostic order mean these are not formal latency estimates. The new route is active in all 2,030 public route calls per configuration, so an inactive optimization is not being mistaken for compatibility.

The separately claimed [B historical compatibility check](../benchmarks/reports/round6-hotpot-compatibility-b.summary.json) reproduced all 2,304 saved output hashes, and its [saved-ledger audit](../benchmarks/reports/round6-hotpot-compatibility-b.audit.json) verified every one of 4,608 events. All preflight, claim, raw report and compressed ledger evidence is retained. No B formal performance run or fresh competitor scoring has started. The balanced hosted measurements will determine whether the additional SQL/Python work is justified.
