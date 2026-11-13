# Round-five recovery — 2026-11-13

## Latest checkpoint — NO development and exact integration

The current machine-readable recovery entry is [round5-current-state-20261113.json](round5-current-state-20261113.json). Earlier sections below retain historical decisions and failures; they do not override a later checkpoint.

The unique NO development run [43488212773](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43488212773) completed once on frozen source `4a0ad4dc6aec33a91231d419239b7e90b160c695`, runtime `77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32`. Final raw result commit is `a2a7b4fa61b9d930b6ea16a6599e9af6e96675a9`. Controller `8b7c721fb033c69ecb3ce07c55385f742b41c20f` was frozen after 31 artificial protocol checks and independent launch review.

Independent audits reproduced all 4,096 timings, 2,048 full non-timing payload digest pairs and 32 premeasurement query-order hashes, with no mismatch. A separate read-only audit compared all 4,732 profile payload digests with the eight frozen v0.3.2/C2 reference artifacts; all matched. Complete reports are committed at `986633dc77bcff54292050f942c929ac960b48aa` in [independent-raw-audit.json](../benchmarks/reports/round5-candidate-no-development-1/independent-raw-audit.json). The profile audit is independently stored at `68a2de797842a3a611755f9785ae5f69703f648b`.

All eight development cells improved in both p50 and p95 against v0.3.2 in this paired run:

| Cohort | Configuration | p50 reduction | p95 reduction |
|---|---|---:|---:|
| synthetic61 | native-char4000 | 9.5739% | 4.1409% |
| synthetic61 | native-token512 | 10.1816% | 18.1386% |
| synthetic61 | native-token1024 | 5.7959% | 18.2440% |
| synthetic61 | native-token2048 | 6.3814% | 14.5558% |
| public1015 | native-char4000 | 10.1519% | 8.7630% |
| public1015 | native-token512 | 5.3281% | 6.9237% |
| public1015 | native-token1024 | 8.9138% | 8.6081% |
| public1015 | native-token2048 | 8.4519% | 9.3358% |

The geometric pooled p95 reduction is **11.2264%**. Public native char4000 p95 reduction is **8.7630%**, still below the separate formal 10% target; its individual rounds improved 8.8278% and 7.4370%. These are development observations, not formal acceptance, and cannot be added to or subtracted from other hosts' candidate timings. N/O were not separately timed.

The bounded next step is the already registered single LM SQLite attribution diagnostic. Its exact observer/controller at `108124188381a199735022abf21b9a0b9c812a54` passed 35 artificial fixtures and independent implementation reviews. The real native-wrapper counterexample, previous publisher-handoff defect and raw-span-topology gap remain recorded. Final source binding and root launch review are required before the sole diagnostic trigger. Partial observed native C spans cannot be described as full SQL cost; the residual includes Python, unobserved SQLite, scheduling and observation overhead. This diagnostic is used only to identify a possible narrow optimization, with no replay of NO or change to formal gates.

### Control integration is exact and tested

Copying the 36 reviewed source/proof files at `d4aa4beab656ce9b646e64a664fe2e11f3b2c720` initially left an old, excluded F module in the control branch. Both the complete source-tree audit and an existing source-inventory test rejected it. The fixed NO measurement source never contained that module.

Prospective repair `6be287b0fc48a5e8cebd5990677ed2ca0f1bd9f0` and implementation `af5ac6a9bc89c158abca02c0445cfb8ea28809b4` move its exact bytes to `tests/fixtures/round5_rejected_query_overlap.txt`, retain all 13 original historical/consumer assertions, and load the SHA-pinned fixture only from the test harness. The entire `src` Git subtree then equals the measured donor: `0f60fb1a6f7207261c44f129ce5b1d8ac2b25fd5`.

The integration also needed the already-tested donor revision of `tests/test_indexed_references.py`, which checks the exact approved T1 opt-in schema addition while preserving all old schema fields and the historical fixture. That exact blob was copied at `8a2323ef0419a360937edb618b85c4a4dc3de866`; no runtime code or new relaxed assertion was authored. The earlier integration CI failures and their raw logs remain in `benchmarks/reports/round5-no-control-integration-ci/`.

[Integrated CI 43490569140](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43490569140) passed all nine jobs at exact `8a2323e`. The MCP job ran 1,211 tests with 15 declared optional skips, including all 218 registered NO cases with zero skips, all 13 retained F cases and the exact schema/source-inventory checks. The passing raw log and receipt were preserved at `4f52de82840e044da09e8256d942b1a39a49c162`.

No final runtime selection, formal timing, fresh metadata/content access, main update, tag or release has occurred. The existing formal 66,248-call/14-cell gates, resource review, historical 5,120-call lexical and 1,968-call Q2 checks, fresh quality/cost/component evaluation and release checks remain unchanged.


## Durable starting point

Resume `optimization/v0.3.3-round5` at `1b2e7df01dde509c5a8e02dc465daca63090b3a1`.
Released comparison baseline remains v0.3.2 at `692fb959ddf8934c5f516ba3d74ceb4385a2fa82`.
No v0.3.3 release or all-dimensions competitor advantage is claimed by this checkpoint.

## Interruption evidence

Candidate I's completed 4,732-call profile and `synthetic61-r0-baseline.json` are preserved in `benchmarks/reports/round5-development-i/`.
The remote tree has `synthetic61-r0-candidate.intent.json` without a corresponding completed worker report. No active GitHub workflow was found for that worker. Its outcome is unavailable; it must not be silently replayed, overwritten, or counted as a completed comparison. The original I binding, failed CI receipts, and all rejected candidates remain unchanged.

The current session's first full Git checkout failed with `No space left on device`. This was a newly downloaded duplicate, with no code edits or new retrieval calls. The local sandbox cannot now start commands, its elevated cleanup request is disallowed by the configured approval policy, and the desktop runtime is unavailable. Existing remote repository data is intact. Recovery will use connected GitHub text/tree commits and hosted CI where possible, with small staged checkpoints. No runtime, measured output, or dataset was modified during recovery.

## Next work

1. Preserve a source-only Python 3.10 fixture cleanup repair while retaining every assertion and the original failed CI evidence.
2. Register any separately identified hosted recovery diagnostic before its first measured call; never represent it as the interrupted original I attempt.
3. Evaluate the source and necessary existing contracts, then freeze a combined default-performance and opt-in title-reference candidate before applicable formal validation.
4. Keep the existing 14-cell/66,248-call formal performance gates and all quality, resource, default-output and no-replay requirements.
5. Do not select/decode fresh512 content until all source/evaluator/competitor bindings and artificial fixtures are ready and committed.

## Current evidence boundary

T1's saved development-v2 results establish a development improvement in delivered supporting evidence only. Fresh acceptance, final combined performance, same-cohort competitor results, and generated-answer accuracy remain unproven. Every adverse result and interruption will remain in the repository.

## Hosted I recovery completed

The independently identified `round5-recovery-i-hosted-1` completed all eight workers / 4,096 calls on one hosted VM. Exact saved evidence is at commit `7e44a340d903f1f4ecfc589c7cef51d63db8462c`, branch `validation/v033-recovery-i-hosted-1`, directory `benchmarks/reports/round5-recovery-i-hosted-1/` (run `43455864142`). All 2,048 complete non-timing payload pairs match; every pooled native p50/p95 improves and none regresses more than 5%. Independent raw-only recomputation agrees with the runner: pooled eight-cell p95 geometric improvement is 3.4704456461560396%, and public native char4000 p95 improvement is 7.063512570933305%. These miss the original 10% targets. I is not selected as satisfying the formal speed goal. Do not repeat this completed attempt or its profile.

The unchanged I runtime now has portable mechanism fixtures at `21b6f4196e42167f8532feafc30457f5684d25cf`, with nine of nine CI jobs successful in run `43454967566`. Both newly observed Python3.10 fixture failures, exact logs, and CPython cache implementation findings remain preserved in that source branch. Runtime source is still the original I hash `71977e56c9f531b45581fabef8c12f28860937961e2788a9ad798d72fb749340`.

An unselected I+T1 integration is independently committed at `d730a620bc0b7afac4de856d2a0fd01a46820c8a`, branch `staging/v033-integrated-it1`. Its default path retains I; active title following uses the complete lexical Row path and preserves provenance. E/F/H are not reintroduced. At this checkpoint eight of nine CI jobs have passed; macOS installation is queued. No combined corpus performance or quality claim follows from these artificial tests.

## Next implementation direction

Candidate J will test a narrowly scoped FTS5 hidden-rank query in the native default stem routes, using unchanged BM25 weights, scope-before-limit and exact tie ordering. It must be independently registered and reviewed before implementation or corpus calls. A bounded 97-row probe must fall back to the old SQL when the 96th/97th ranks tie or any eligibility/compatibility requirement fails; it must never truncate boundary ties or change the top-96 candidate set. This is a mechanism hypothesis, not a measured speed improvement. The registered 14-cell/66,248-call formal gates remain unchanged.

The new candidate's exact source, artificial correctness and source/helper/data binding must be committed before its one fixed 4,732-call development profile and 4,096-call native paired diagnostic. Previously preserved v032/C2 full payload hashes are the profile reference. No fresh512 ID/content has been selected in this session, and no formal performance attempt or v0.3.3 release has occurred.

## Candidate J source frozen and first hosted attempt launched

J source is committed at `910ba8904523ad81cb7d68073af77580942496eb`, branch `staging/v033-ranked-route-j`, on the preserved I+T1 integration. Runtime SHA256 is `740ab3a1729811883e10de4a773c3907cf31f8a77b62ad00b00ce079543358e1`. Its Tests run `43459086769` completed all nine jobs successfully. The new 18 invented J fixtures pass without skips on Python3.10/3.12/3.13, including real SQLite cutoff ties/scopes, rank-route EXPLAIN, closed-cursor Row reconstruction, invalid-UTF8 lookahead, native factories/adapters and complete non-timing payload comparison.

The independent source review is separately preserved at `dfb795cd32ec3d9b505c229e834fcf1c71dd5fd9`, file `benchmarks/reports/round5-ranked-route-j/independent-source-review.json`. This permits old-data development, not performance or release acceptance. Integrated I+T1's earlier run `43455545066` also ultimately completed nine of nine successfully.

The J development controller `08d165878866d6b18b2b76a430867c137fc0438d` passed nine of nine CI jobs at `43457477423`. Its exact source inventory and 13 correctness module hashes were frozen in `a4bb0b400ec07b707170cf0a55e3d968e64ab48d`; binding SHA256 is `c7a5857628cd1b9d391522c6cd50794a8c486e3959e08c924f520e3a48a9342a`.

The binding commit used `[skip ci]`; creating the trigger ref there produced zero workflow runs and no execution claim. Explicit launch receipt `ba99a39cf6a062d3d2edef13f9ee46f7cd92282d` changes no source, binding, evaluator, schedule or threshold. First hosted J run `43460362301` is now executing. Its fixed output ref is `validation/v033-candidate-j-development-1`: 4,732 profile calls must match every saved v032/C2 non-timing payload before 4,096 AB/BA paired calls. Each stage retains its remote intent, raw output and exit receipt before the next stage. No J speed result is available at this checkpoint.

## Additional recovery and prospective evaluator work

A reproducible compressed-report API error was isolated: fetching gzip as UTF-8 raises a decoding error. Explicit `encoding: base64` reads succeed and the bytes are losslessly decompressed for independent audit. This is a verified workaround for that error, not a claim that all previous task interruptions had the same cause.

Related round4 Actions artifacts and actual upload paths do not contain the original Q2 prepared databases. The original reports/scripts are preserved. A separately registered hosted recovery is being implemented on `staging/v033-q2-recovery-hosted` (scope checkpoint `0f9303d923fda0611b5b6e27259ac0c50e54bcc7`). It will identify newly built originals honestly and require exact historical persisted-vector identity before any query. It has not downloaded models/data or run Q2.

A source-free final-freeze controller is independently staged at `417a4e3fef84dfa12c38a3bfceaf4fb18d49a8f0` on `staging/v033-final-freeze-hosted`. It can only generate the existing approved MCP initialize/list_tools certificate, publish it, then generate the unchanged formal binding. Missing final-source selection prevents execution before claim. It has not been triggered.

Static review found an existing fresh-evaluator cross-worker identity issue before any fresh metadata was read: independently ingested databases contain new storage timestamps, while the old audit compares full six-table source digests across workers/export. A minimal, separately registered prospective correction is being designed and tested with invented data. Within-worker full originals immutability, every original source/structure field, exact default/repeat payload parity, all quality/cost gates and comparator boundaries must remain enforced. No fake ingestion time, database rewrite or silent weakening is permitted. Original v1 evaluator files and evidence remain intact. Fresh512 remains entirely unselected and uninspected.

## Hosted checkpoints — 2026-11-13 16:42 UTC

This section supersedes the earlier J launch status; no release/final benchmark acceptance is implied.

- J1 `43460362301` stopped before its first profile/paired query at the strict source-inventory guard. All 161 correctness fixtures passed. The complete seven-file failed attempt is preserved at `da2f3b30d11093dda85ea244b2609b8e7fe6625b` on `validation/v033-candidate-j-development-1`; do not replay it.
- A separately registered artificial diagnostic at `1bad47e1730b46996924386b3be23724ae7d1320` preserved raw results at `a54ab21b6369bc121dbc325a315841c09a90b33d`. All 18 bound source files stayed identical; one MCP fixture's two children lacked PYTHONDONTWRITEBYTECODE and created 12 valid CPython cache files. Original J1 did not retain its differing bytes, so this is a reproduced mechanism, not recovered J1 inventory.
- The diagnostic's top predicate misclassified one ordinary CLI child. The original failure remains; read-only saved-evidence classification audit `b47ec670e9f37521a9dafb7271bfaefae2c14462` corrects that mistake without rerunning tests. Audit SHA256: `a46e32c9dd5a6e4f9f3661812c4410c977db4bd99f000ea1a41af37a99bf5c39`.
- J2 scope `da7471042796a00e941708d833d60716141bfe2a` and controller `be8aa9d0b34e38884d10ac1b01a67cefcd298f09` are on `staging/v033-candidate-j-development-2`. Dedicated artificial CI `43463913539` passed 17 tests; recovery was skipped. Correctness runs in one exact source export, which is preserved completely, and timing uses independently exported exact source copies with the original strict inventory guards. Runtime `910ba8904523ad81cb7d68073af77580942496eb`, original binding, 4,732 profile calls, 4,096 paired calls, helpers and gates remain unchanged. A narrow exact-cache-path allowlist improvement is pending before root creates the distinct `ci/v033-candidate-j-development-2` trigger. No J2 measurement has begun at this checkpoint.
- Candidate K prospectively registered at `d40b2a4398d177cb230c3e497cea822337cb06d8`, current source `df526ae6b01498d26db879626e899b4782b7fea5` on `staging/v033-normalization-identity-k`. It bypasses Unicode normalization only for an exhaustively tested identity alphabet and recognized Unicode versions; all other inputs retain the previous path. No new cache, dependency, ranking/index semantics or storage format. Full CI `43463067291` passed all nine jobs including Python 3.10/3.12/3.13 and MCP. Independent review is pending; no K corpus calls or timing yet.
- Source-free final freezer `f6eafe291680dfae1b40e30ed42d76e79e4084ba` on `staging/v033-final-freeze-hosted` passed all nine jobs in `43460991201`, including 12 artificial protocol fixtures. It fails before claim unless a separately committed exact final selection exists. No selected runtime, certificate, final binding, or formal run exists yet.
- Lexical compatibility controller `65742c005290ae78702f6c9ff24613efd3616311` on `staging/v033-lexical-compat-hosted` adds only scope/controller/workflow/14 fixtures; original 5,120-call helper and all gates are unchanged. CI/review pending; no trigger or corpus execution.
- Q2 recovery scope remains `0f9303d923fda0611b5b6e27259ac0c50e54bcc7` on `staging/v033-q2-recovery-hosted`. New shared persisted-vector snapshots must reproduce historical vectors exactly before any of the 1,968 calls; newly generated storage timestamps will never be represented as the missing historical DB bytes. Controller implementation resumes after J2 orchestration is ready.
- Fresh v2 cross-ingest snapshot correction is at `b4f5b97b38dc50f02fd307e16ad81fcb83bed995` on `staging/v033-fresh-hosted`; full CI `43463394230` passed. It excludes only four newly generated internal timestamps from cross-ingest content identity, retaining all original source fields, normalized session creation times, within-worker full snapshots, copied-DB byte identity, old v1 files and all quality/cost gates. Both artificial fixture failures and their logs are preserved. Hosted controller is being built and independently reviewed. Fresh512 metadata, IDs and content remain unselected/uninspected.

Continue to checkpoint every claim/result and preserve all negative/partial evidence. Main and v0.3.2 remain unchanged. Do not pool timings across VMs, reuse a claimed attempt, silently adjust thresholds, or state broad competitor superiority from these development tests.

## Isolated K execution checkpoint — 2026-11-13 16:54:35 UTC

J2 is complete and rejected for speed; this supersedes its pending launch and all earlier optimism about the hidden-rank route.

- J2 run `43464982014`, execution `197145975c305bf43da039dacc71aab70af165fe`, immutable result `eeb8217084f32eb01c478345effd37935bbc3dc0`: 161 fixtures pass, 4,732 profile calls match saved C2, 4,096 paired calls / 2,048 complete payload pairs match. Every timing cell regressed. P95 geometric-mean improvement is **-38.04178031080472%**; public native char4000 p95 change is **+33.129787666751454%**. All 8 cells violate the5% regression boundary. Do not select J, rerun it, or pool these timings.
- Root independently recomputed all 4,096 raw timing observations, exact worker SHA256, aligned query IDs, all 2,048 payload digests and every pooled p50/p95. Saved read-only audit: `dca3c856d53bc5f12de70ee36968de408cf58b18`, branch `validation/v033-candidate-j-independent-audit`, path `benchmarks/reports/round5-candidate-j-development-2/independent-raw-audit.json`, SHA256 `f0d443e917e539bdaef4e83c996e94a543dfb86f34ca5ee429dab87e262648b2`.
- Independent K review identified a stateful str-subclass isascii truth-evaluation counterexample before any K corpus call. Fix `3e5473e2b2c7c97a0b98489d798a45181b300c9c` restores exactly one historical truth evaluation and adds a literal pre-K terms reference plus targeted fixture. Earlier source/tests remain in Git.
- K was prospectively isolated from the rejected J route: base-selection scope `ab94e51311a7374faa9fd72d36d2d9af747869ca`; current source `4720728e47d53fc6c345fa89a2b5b739a67a1069` on `staging/v033-normalization-identity-k-isolated`. Relative to I+T1 `d730a620bc0b7afac4de856d2a0fd01a46820c8a`, only `src/memory_book/text.py` changes in the runtime. Runtime SHA256 `90079d629d101370e6960a10e5391265802b1a053f65438e9b667b662638b251`. Complete18-file inventory and17-Python aggregate were independently recomputed by root and the runtime reviewer. All9 source CI jobs `43465851432` passed; MCP ran all11 K proof methods including tokenizer/subclass checks.
- K independent source review is `6d6ac342cbca88ac5b5b4939f426b7cbe48deeb1`, `benchmarks/reports/round5-normalization-k-independent-source-review.json`, SHA256 `fbd51258333640040510845b1e550d3658634b087b9db05733e73c11456df430`. It accepts source correctness review only, with no performance/fresh/release claim.
- K development scope was committed first at `ec323f6753eca32d992e16f20477d16e264dec41`. Controller and exact source binding are `04366aa4fc34d68e6ce23c55efa7aadef3dca04a` on `staging/v033-candidate-k-development`. Scope SHA `0580c895f8c756e8d8688c446bf95445791c53d5950106b5bb6b6da9c063045a`; source binding SHA `416caf9fea33d41197bf8094de8d2a5545a49b619fd510864c8411895ac8b8fd`. The independent orchestration reviewer verified original helpers, statistics, 4,732+4,096 calls, source isolation, exact preclaim review/rejection evidence and unique namespaces. Dedicated artificial CI `43466817953` passed25 tests, with measurement skipped on staging.
- Root created **`ci/v033-candidate-k-development-1` at04366** only after both result/trigger refs were absent and both independent reviews/CI had passed. Fixed result ref: **`validation/v033-candidate-k-development-1`**. Check this execution before any further action. Never replay this attempt or treat a completed development run as formal acceptance.
- Historical lexical controller `65742c005290ae78702f6c9ff24613efd3616311` passed CI `43464110663`; root reviewed exact sources, unchanged original helper/5,120 calls, full ledgers, host/DB guards and publication failures without a blocker. No final selection or trigger yet.
- Q2 controller `25e7ea32b34e5a8dc08b0931c6b3840e9f3fffb0` on `staging/v033-q2-recovery-hosted` passed dedicated artificial CI `43466426848` (10 fixtures, measurement skipped); root reviewed the full preclaim/source/model/vector/two-snapshot/8-worker/original-C2 audit flow without a blocker. Candidate Q2 binding remains absent. Historical vector bytes must match exactly before the first query; no retries/tolerances or original timestamp rewrite.
- Fresh v2 successful CI evidence is checkpointed at `794a26c` on `staging/v033-fresh-hosted`; full evaluator repair still `b4f5b97b38dc50f02fd307e16ad81fcb83bed995`. Root compared v1/v2 function bodies: score, schedule, statistical quality and cost gates are unchanged; changes are the explicitly registered cross-ingest content snapshot plus within-worker checks and versioned registries. Hosted controller remains under implementation with missing final authorization, no selection or fresh data access.

Final source-free freezer remains `f6eafe291680dfae1b40e30ed42d76e79e4084ba`. No final runtime, interface certificate, formal binding, formal66,248-call matrix, fresh512 cohort or release has been selected/executed. Main/release v0.3.2 are unchanged. Investigate new performance ideas only in separately registered candidates while preserving all accepted contracts and adverse evidence.

## 2026-11-13 17:41:43 UTC: LM complete; continue targeted development

- Exact LM source `49f10e7dec006e3a5760c93623a650dc7b6338d6` combines only the reviewed L store and M normalization changes on K. Combined CI `43471535987` passed all9 jobs; independent source review is `41e26421eccc281ea9639c882be1a9e2e787ec4a`. Its15-module pinned suite ran183 tests with zero skips/errors/failures.
- Controller `8df838aa47e009caa8173b2ccb32fad93e4b8f90` and its immutable source binding passed27 artificial protocol tests before the unique run `43473326005`. Original K/J helpers, counts, export guards, complete-payload comparators and numerical gates remain unchanged.
- Complete result `ec296d79fc1a2ec9c4e3cadb48bddfd34cdb0213`, branch `validation/v033-candidate-lm-development-1`:4732 profile calls agree with saved v032/C2;4096 paired calls/2048 complete payload pairs agree. Independent raw-only audit `128952ffd4f53a30f225feb98853a7f7f6ea7121` (SHA256 `eb7c9fd7b032409e7ff4d39b3ce8b03838f1901abfc3b4806fd21a8f398fdb42`) rechecks every worker byte/sample and reproduces pooled p50/p95/GM. GMp95 improvement is4.791840281283378%; public native char4000 p95 improvement5.430823483528835%. Both remain below original10% goals. No final source/release is accepted.
- Retain the within-gate adverse values: synthetic token512 p50+3.2743303750706554%, synthetic token1024 p50+1.2183569886350831%, public token512 p50+2.6723935259700182% and p95+3.7551366648520768%. No cell exceeds5%, but it is incorrect to say every metric improves. Do not replay this complete run or compare/subtract absolute/percentage timings across K/LM hosts.
- N prospective scope `8e8c4b30a2f56f7b3aaaadb8f500a563be7ce5ef` is registered on exact LM before source edits: scan the same97 compatibility scalars as maximal runs and translate only those runs, retaining every existing guard, fallback, normalization order and all15 proof modules. No N corpus calls or microbenchmarks are authorized by the source-only phase. A separate source-unchanged SQL-attribution diagnostic is only being designed; no diagnostic has started.
- Reviewed hosted orchestration was integrated without runtime changes at`1190d95343871f0d5ddc6893f93c044eaa36089f`. Its general CI`43471938589` ends with8 successful jobs and macOS installer`132045790466` cancelled; this is not9/9 acceptance and is not replayed. Exact component CI/reviews remain separately preserved. Later final-source CI must complete all9 jobs.
- Resource-chain audit `a1198d33b41a27af7ddce08645fb2f6ee0527a88` confirms the original16-worker formal run already samples final-source resources:14 fields×2 cohorts, plus all four raw storage boundaries. Storage is not part of the automatic resource-field gate and needs same-run raw review. The historical v031/v032 resource diagnostic must not be reused. Lexical5120 already includes3072 token calls and2048 char100000 calls; the latter are not an additional run beyond5120.
