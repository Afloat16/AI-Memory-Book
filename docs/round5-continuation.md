# v0.3.3 / round-five continuation checkpoint

## Current goal and status — user clarification on 2026-11-13

The user explicitly requires improvements in retrieval effectiveness, accuracy
and speed, with frequent remote Git checkpoints. Exact-output optimization
alone cannot establish a quality gain. The retained A–D development candidates
have not qualified for the original formal performance run; D evidence is at
`2d381b49a36bf64820635887ac886f62b5c1b8cc`. The independently reviewed E lifetime
scope is registered at `10b04c8fdcfd0ecc95492e17b2a764c62a0651f1` and has not yet
executed its corpus diagnostic at this checkpoint.

Parallel quality diagnosis now examines only already saved v032 outputs and
their old source annotations. The new
[offline evidence audit](../benchmarks/reports/round5-quality/saved-v032-evidence-diagnosis-v2.summary.json)
makes zero retrieval or model calls. On the old 256-question Hotpot cohort at
1,024 cl100k tokens, lexical retrieval delivers 481 of 635 annotations. Of the
154 omissions, 142 have no returned result from the required source session,
and 12 have the session but not the required turn. None is merely a partial
returned turn under the saved coordinates. Increasing to 2,048 tokens changes
no evidence-rank vector and gains no complete question. The saved Q2 path also
has no 1,024-to-2,048 evidence gain. This supports investigating source selection
and cross-reference retrieval, not simply increasing the context budget.

The audit does not establish whether an absent source was outside the original
candidate pool, ranked below top five, or omitted by packing. No new ranking
policy has been selected, implemented or evaluated. A quality change requires
its own prospective scope, source freeze and independently held-out validation;
original performance registrations, adverse results and release gates remain
unchanged. Gains from different runtimes cannot be combined into a claim about
one shipped version. Generated-answer accuracy requires a separate actual
answer evaluation and is not inferred from delivered evidence.

## Initial registration — before new measurements

The user requested continuation after the completed v0.3.2 release. Main is
`de6e2652572c4867cda2aac5637a4a6630638c7e`; the baseline release remains at
`692fb959ddf8934c5f516ba3d74ceb4385a2fa82`, runtime SHA-256
`179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
The new development branch is `optimization/v0.3.3-round5`.

Read-only profile inspection identifies candidate dictionary materialization
and repeated directory score-factor work as a bounded exact-output target.
At this registration no new implementation, development measurement or scored run existed.
The [registered plan](../benchmarks/experiments/round5-plan.json) fixes the
scope, baseline and a 66,248-call, fourteen-cell formal matrix before work.
The existing 100,000-character path gets explicit formal coverage.

The large round-four sampled tree-RSS increases remain preserved. Saved worker
high-water marks show much smaller changes, and affected phases include a
second process plus evaluator work. Provenance checks spawn Git processes;
finalization also hashes the full 118,453,870-byte model file in memory. These
are documented diagnostic leads, not proof of a harmless measurement artifact
or a demonstrated product leak. A separate frozen phase/PID trace diagnostic
will distinguish these costs without changing the historical reports.

## Next work

1. Commit the plan and this checkpoint before implementing/measuring candidate A.
2. Implement and independently review bounded materialization/factor reuse.
3. Preserve full old-cohort payload, exact-count, source-snapshot and Q2 checks.
4. Freeze one candidate and new round-five evaluator; run the formal matrix once.
5. Audit saved results and resource diagnosis, then release only if gates pass.

All round-four and earlier source tags, evaluators, reports and failed attempts
remain immutable. New diagnostics use new filenames and record intent before
execution. Save every completed stage remotely; never select the fastest retry
or turn historical component results into a new competitor measurement.

## Candidate A implementation checkpoint

The registered candidate now retains route rows until union materialization,
avoids temporary metadata dictionaries and reuses per-call directory score
factors. All SQL and transaction literals remain unchanged. Its runtime hash is
`1befe0619785df3a468705f1042c7f6e7dccb63d6ca6134d51e53211cdc90acd`.
The new invented-response fixtures were first captured and passed against the
released store. The candidate passes 47 focused runtime fixtures and both
installer routing tests; the next-version defaults are 0.3.3 and all older
wheel routes remain available. The correctness log and receipt are retained
under `benchmarks/reports/round5-development/`. No speed measurement has run.

## Premeasurement compatibility repair

Independent review found that an `isinstance` fast-path guard also accepted
SQLite Row subclasses with overridden mapping access. The new fixture first
reproduced both route and metadata failures on committed candidate `1a9d1c1`,
then passed against the released baseline. Both guards now require exact Row
type; subclasses retain the mapping path. All ten fresh fixtures pass. The
initial correctness receipt remains untouched and the additional failed/passing
checks are preserved in `candidate-a-subclass-correctness.log`. No development
or formal measurement preceded this repair. The repaired runtime hash is
`25d67aa37690e407200a759e6a5573eed852a53049b4aad2a4b39164bda4ddbb`.

## Candidate A development disposition

The repaired candidate at `2de18efd` completed all 4,732 profile calls; every
complete non-timing payload matches the saved v0.3.2 profile. Its separate
4,096-call, two-round native diagnostic also preserves all 2,048 payload pairs.
The eight-cell development p95 geometric gain is only 0.7283%; public character
p95 rises 24.3380%, and synthetic character p95 rises 6.0709%. Public token1024
p95 improves 11.6184%, but these mixed short diagnostics do not establish the
registered aggregate/character improvement. Every row and loss remains in the
new lossless archives and paired audit. Candidate A is not selected for formal
measurement or release. No formal run or historical compatibility run has begun.

The next bounded hypothesis is later materialization of the default lexical
rerank prefix. All route rows still participate in exactly the same scoring
and tie order, with the full original candidate count retained in the response.
Coverage, semantic and custom row paths keep full materialization. Register a
separate addendum before implementing/measuring that variant; all original
formal gates remain unchanged.

## Candidate B and resource diagnostics registered

The full candidate-A development evidence and the bounded materialization
addendum are committed at `9042570d8cff01be7c95cd01f8698e166fc7d313`.
Independent source tracing confirms that the default lexical rerank consumes
only its original prefix; complete scoring/sorting and full candidate counts
must still be retained, with full fallback for optional/custom-row paths.
Candidate B implementation is in progress; no B timing or formal attempt has run.

The new formal and historical-compatibility evaluators bind the addendum
separately from the unchanged original plan. Their updated offline fixtures
pass 36 and 14 tests respectively. They neither retrieve nor perform inference.

The separately reviewed resource diagnostic, 17 functional fixtures and review
receipt are committed at `d67e6c695aa586bbcbc9f0e134c769980d8e09ef`. Its dedicated
first hosted attempt has been triggered at that exact source. It measures old
v0.3.1/v0.3.2 sources only and retains phase/PID traces plus original inclusive
RSS. Completion alone is not a product memory-saving claim.

## Candidate B implementation ready

The bounded default lexical prefix implementation is complete, with runtime
SHA-256 `1f0c8a27108fed25c043d1439a8cb52bcb12422a4759a05423de33665e02a487`.
All 18 materialization fixtures pass against released v0.3.2; B passes all
68 materialization/adjacent tests with zero skips. Exact ordered SQL column
shapes preserve the custom mapping, duplicate-column and metadata-overlay
contracts. Three premeasurement shape failures and their repair are retained
in the complete correctness log. Independent review approves the final hashes;
all 107 SQL execute/executemany expressions remain unchanged. No B development
or formal measurement has run at this implementation checkpoint.

## Candidate B development retained; C registered

B preserves all4,732 profile payloads and all2,048 paired payloads from4,096
development calls. Its eight-cell p95 geometric improvement is5.6984percent;
public character p95 improves8.7411percent, while synthetic character p95
rises2.3670percent. This improves on A but does not establish the original
10percent target. All original samples, including slower cells, are preserved.
No formal attempt has run. The next registered refinement reduces temporary
shape-check allocations and repeated canonical Row name lookups while keeping
every per-row guard, exact fallback, score/sort and count rule.

The historical memory diagnostic completed at result commit
`2511be109e2877e86d4d452525754d399e514789`; its independent audit verifies30files,
21checkpoint commits,9workers,256calls/128pairs and1,846samples. Six missing-PSS
samples remain explicit. This is old-source attribution, not v033 memory evidence.
The reviewed Q2 reuse driver has19passing artificial fixtures and retains the
original v031 vector builder, fixed old cohorts and a strict1,968-call schedule.
It has not yet bound or executed a real Q2 worker.

## Candidate C implementation and clean-checkout repair

C runtime `9ac5a2ab23ddf5ceca80ce2e7eb7df3d0f4a99c82003ba3ced40e7ed40caf1b6`
now uses ordered list guards, exact positional reads after complete validation,
and fixed zip column sequences. Independent review and69functional tests pass;
107SQL call expressions and7rank-map/scale/fusion assignments remain unchanged.
A later reordered-row fixture passes released v032, B and C. No C development
measurement preceded this checkpoint. All three evaluation drivers now bind
the separately committed C scope without changing any original gate.

CI run43379997683 exposed an artificial Q2 fixture assumption about an existing
local artifact directory. The complete core312 failure log and both-job receipt
are retained. The fixture parents now use the existing repository root; an
isolated stdlib-only checkout reproduced18errors before repair and passed all
24tests afterward. New hosted CI will verify the committed repair. Runtime and
benchmark acceptance rules were not changed for this repair.

## Candidate C profile preserved

Candidate C source at `59b92482d1c7334fb134d9d4ae9b0202c9b3b98a`
passes all nine hosted CI jobs in run `43380819086`, including the clean-checkout
fixture repair. Its registered profile completes all 4,732 calls. Every complete
payload equals the saved v0.3.2 payload; eight compressed cells reconstruct the
original report byte for byte. These noncontemporaneous profiles include
profiler overhead and make no speed claim. The registered 4,096-call paired
development diagnostic has not started at this checkpoint.

## Candidate C paired disposition

The registered C diagnostic completed all 4,096 calls and all 2,048 complete
payload pairs match v0.3.2. Its eight-cell pooled p95 geometric improvement is
-0.3607 percent (a regression). Public character p95 improves 8.7785 percent,
while synthetic token1024 p50 regresses 6.0566 percent. Six of eight pooled p95
cells regress. The full original records reconstruct byte for byte from the
eight compressed worker archives. C is not selected for formal measurement or
release. No formal or historical/Q2 compatibility attempt has begun. A further
bounded change requires a separately committed scope before implementation;
the original acceptance thresholds remain fixed.

## Candidate D scope prepared

Three independent reviews support a bounded derived-map experiment within the
original plan's unused-structure allowance. The separately registered scope
requires complete per-row native shape and exact primitive ID/rank checks before
combined bookkeeping; all ineligible paths keep C's complete original map/read
and exception order. Duplicate-ID first insertion and last-value semantics,
score scales from final maps and ordered deduplicated fusion detection remain
fixed. Coverage and Q2 keep the existing route computation. Saved profiles show
the public workload is mostly fused, so unused-score deferral alone is not
expected to establish the ten-percent target. No D implementation or measurement
has started at this registration checkpoint.

The D registration is committed at `0e933580a2a7d28f24b0ac7a8a2f5db4acfb762d`.
All three evaluation drivers now require its exact original commit, bytes and
registration links. Artificial evaluator checks pass 42 formal, 18 historical
lexical and 27 Q2 tests; Q2 also passes in a clean stdlib-only checkout without
local artifact directories. Root and cross-review confirm that schedules,
acceptance thresholds and old helpers remain unchanged. These are evaluator
checks only; the real compatibility and formal executions have not started.

The evaluator checkpoint `e7abb9fd2dfd097262407eff61d68412a3de4570` also passes
all nine hosted CI jobs in run `43382911482`; its runtime is still C. Four new
invented D-boundary fixtures pass against both exact v0.3.2 and unmodified C
(eight checks, no failures or skips). Their preimplementation log and fixture
hash are preserved separately before the D runtime edit. Duplicate primitive
IDs, later custom ID/rank values and error order before metadata are covered.

## Candidate D premeasurement length failure retained

D runtime `0ef0fe3cc9d49edd83c20024cf1e57fcbb4d7cfbc52472b388c0f281a7389863`
passes 74 existing checks, including new custom-batch and metaclass cases, but
independent root/evaluator review found an additional inherited C regression.
A native Row can have the correct three column names and four values. The
derived-map guard rejects it, while the old late-materialization guard admits
it again and reads the last value as rank. An invented three-page reproduction
returns correct scores `[2, 1, 0.5]` on released v0.3.2 and incorrect `[99, 99, 99]`
on C and this D source. The full source, earlier checks and new failure are
preserved before repair. No D development or formal measurement has run. The
published v0.3.2 release is unaffected; C was never selected or released.

The length repair now gates all four positional/zip boundaries with complete
value counts. New invented tests first pass v0.3.2 and reproduce two payload and
two exception-type failures on C and the preserved D source. The repaired
runtime `93a69a06a1d2e618173f55b10250e35dc9962e48eba78e032f22bac5c5fd2df5`
passes 76 functional checks, with all 107 SQL ASTs unchanged. This checkpoint is
still awaiting a separate full-mapping review: original metadata batch merging
and the position of route dictionary conversion may expose other inherited
custom-row regressions. No D development measurement or final approval has run.

The length-repaired source is durably stored at
`453bf7b789c68dfb03aa8899f0479136774d277c`. A separate reviewer reproduced three
additional inherited mapping regressions in nine fresh artificial processes:
unknown metadata IDs are ignored instead of raising KeyError, repeated metadata
partial updates lose an earlier extra rank, and route mapping exceptions occur
after metadata SQL instead of before it. Released v0.3.2 passes all three;
C and this D source fail all three. The original reproduction script/log and
ten permanent boundary fixtures are preserved; those fixtures pass v0.3.2 and
retain eight failing subcases on this D source. The next repair restores the
complete original named-mapping fallback and only admits fully validated raw
batches to delayed materialization. No benchmark or model call was used here.

## Candidate D implementation reviewed

The final D runtime is
`bdfb117368c937ad4da9076c71a2f454eba49ae85ed0057872eac199c3022c16`.
It restores original eager dictionary construction and sequential metadata
updates on every ineligible path. Only fully validated canonical route and raw
metadata batches can use combined rank/union construction, unused-score deferral
and delayed prefix materialization. All 79 functional checks pass with no skips.
Independent source review confirms unchanged 107 SQL ASTs, original seven
fallback assignments and exact v0.3.2 route/metadata mapping operations. Every
premeasurement failure and repair remains in prior commits and the complete
correctness log. D development timing has not started at this source checkpoint.

## Candidate D profile completed

Final source `c67757305d6334b74d98c34ffbfab9b8ebdd6e27` passes all nine hosted
CI jobs in run `43386089073`. Development intent
`46d59045d7da09b6413889c403a04f0b5fb100c2` preceded the fixed profile. All 4,732
complete payload hashes match the saved v0.3.2 profile, and the eight compressed
cells reconstruct the original report byte for byte. The profile includes
profiler overhead and an earlier baseline; no elapsed-speed claim is made.
The separate registered 4,096-call paired diagnostic has not started at this
checkpoint. No formal or historical/Q2 compatibility attempt has started.

## Candidate D paired disposition

D completes all 4,096 registered calls with all 2,048 full non-timing payload
pairs equal. Independent reconstruction verifies every original worker and
all eight compressed archives. Its eight-cell pooled p95 geometric improvement
is 6.9853 percent, and public character p95 improves 8.9674 percent. Both remain
below the original ten-percent target. Synthetic token1024 p50 regresses
16.0810 percent; the two rounds separately regress 10.1865 and 13.5953 percent.
This is not only a pooled-percentile artifact. All slower cells remain visible.
D is not selected for formal measurement or release. Its correctness repairs
and full evidence remain preserved. Any further diagnosis or implementation
requires a separate fixed scope before execution; no D timing replay or gate
change is permitted. No formal or historical/Q2 attempt has begun.

## Candidate E lifetime diagnosis registered

The D paired evidence is durably stored at
`2d381b49a36bf64820635887ac886f62b5c1b8cc`. Three reviewers agree that the private
ranking tuples have no readers after prefix materialization and that all their
Row values remain owned by the existing route/metadata containers. A separate
prospective E scope permits only clearing this consumed list, uniformly across
budgets. No GC cause or speed improvement is established by that static proof.
The next step is a separately bound, non-timing diagnostic for v032, D and E:
all original 4,732 profile queries/configurations per source, every payload hash,
and generation/phase collection counts. Artificial lifetime inspection is kept
in separate processes. No runtime edit or diagnostic execution precedes this
registration; the original formal and release requirements remain unchanged.

## Candidate E source checkpoint

The E runtime is
`5caa9a72d73eef7121e81f4823f583dc35fc246a1b61b792829bdd275787127b`.
Its sole change from final D is `ranked_rows.clear()` immediately after prefix
materialization. Removing that one line restores D bytes and AST exactly; the
other 15 runtime Python files and all 107 SQL expressions are unchanged.
All 79 existing functional checks pass once, with no failures or skips. Root
independently verifies the source diff and complete log. No E lifetime probe,
corpus GC-frequency diagnostic or timing run has started at this checkpoint.

## Offline quality diagnosis coordinate correction

Independent review found that the initial offline classifier assumed sentence
coordinates started at zero, while canonical Hotpot turns contain `USER: `
before the original sentence and preserve its whitespace. The corrected helper
uses the original evaluator's normalized-substring rule inside valid canonical
source-reference ranges. Five invented coordinate regressions pass. Independent
recomputation validates all 36,574 saved reference occurrences and matched-rank
references; all twelve cells' per-query classifications remain identical.
Every actual omission in this saved sample lacks a same-turn reference, so the
initial coordinate error did not affect these counts. The original commit and
archives remain preserved, with separate v2 output and a
[correction receipt](../benchmarks/reports/round5-quality/saved-v032-evidence-correction.json).
No retrieval or model call was executed for either derived audit.

The exact E source also passes all nine hosted CI jobs in run `43390867313`.

## E diagnostic evaluator reviewed before execution

The separate GC diagnostic driver and 23 passing artificial fixtures are ready
for an exact binding. Two preexecution defects were caught and repaired: prior
reports could have remained live in later workers, and v032 lacks the newer
candidate_count local inspected by the probe. The controller now validates and
claims each job before exec creates a fresh interpreter; the actual worker
never reads previous diagnostic reports. The v032-only local fallback is
explicit. Root and a separate evaluator reviewer approve the fixed source.
Bindings are compact, and complete worker reports use deterministic gzip.
No actual probe or corpus diagnostic has run at this evaluator checkpoint.

The first binding command stopped at its Git-environment check: the local
optimization branch had no upstream, and origin's fetch mapping tracked only
main. No binding, state directory, report or retrieval attempt was created.
The zero-call block is preserved separately. Repair only adds the authorized
branch's local tracking configuration; all evaluator checks remain intact.
The subsequent binding uses new `-v2` paths, with no measurement replay.
