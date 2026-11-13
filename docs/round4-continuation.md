# v0.3.2 / round-four continuation checkpoint

## Current stage

Protocol registered before development measurements at `4f239ea`. Development begins from
`ea0541326f6869cd32a9573a111134622ec6b38c`; the named baseline is published
v0.3.1 at `7b7a5d7336b9350a128f5e0a888811b1b3015e68`. Their runtime files are
identical. The first bounded v0.3.2 candidate is implemented; no formal timing
or fresh quality score exists at this checkpoint.

The v0.3.1 development profile completed all 4,732 calls. Its complete
non-timing payload hashes and source-free profiler data are preserved in
`benchmarks/reports/round4-development/baseline-manifest.json` and eight
individually compressed cell files. These timings include profiler overhead
and are not a formal performance claim. The runtime candidate retains source
reads and corruption validation inside the existing SQLite snapshot, delays
certified source parsing until needed, bisects sorted projection starts, and
reuses the exact count of the last accepted context. The first candidate
runtime SHA-256 is `ca8d2d1a227252d4048780ac4b6ed8eac7d2c931fa99b1338a238f490fc9e02f`.

All 41 token tests (17 fresh) passed, including actual SDK MCP and a concurrent
writer; both installer release-routing tests passed after the v0.3.2 bump.
Independent runtime review found no blocker and checked 30 additional
artificial baseline/candidate cases. Candidate A is committed at `cf712787`.
Its complete 4,732 profile payloads match v0.3.1; the mixed profiler timings
are retained in `candidate-a-manifest.json`. A separate sequential native
development diagnostic completed 4,096 calls (2,048 full-payload pairs) on
128 deterministically selected old queries per cohort and two balanced rounds.
All payloads match. Public token p95 gains of about 4–7% are insufficient to
freeze this candidate for the registered formal gate. Negative cells and all
timings remain in `candidate-a-paired-manifest.json` and its worker files.
No formal measurement has started and no speed gate has been relaxed.

The fresh comparison preparation, selector, evaluator, controllers and
workflows are now implemented in new round-four paths. All 35 offline fixtures
passed without dependency skips. Candidate launch values remain null while
development continues; no new IDs have been selected. Independent review is
checking the commit-before-selection and one-execution guards. These are
development checkpoints, not acceptance or release approval.

## Candidate B disposition

The pre-implementation addendum is immutable at `fbfc6c5`. Candidate B's
runtime SHA-256 is `f4d5471df44d8d04e13581e971d6d53d885919caea9f80a5a0a4ddcbc088f122`.
It adds bounded, revision-scoped indexed-body features, private metadata
dictionary reuse and bounded highlight reads. An independent audit found and
fixed invalidation on empty/flat/cache-hit paths before development timing.
All 18 fresh cache/snapshot/memory fixtures pass; 32 additional artificial
highlight pairs match. Its 4,732 complete profile payloads and 2,048 paired
native diagnostic payloads also match v0.3.1 exactly.

Candidate B is **not selected for release**: public token512 development p95
regressed by 11.82%, with mixed/noisy results elsewhere. Preserve both B
manifests and all compressed samples. Correctness alone does not justify this
cache. Next investigate exact within-request token counting at certified
separator boundaries; preregister any extension before implementing or
measuring it. No formal run, new ID selection or fresh quality scoring exists.

## Candidate C implementation checkpoint

The exact counting extension was preregistered at `e02584f`. The regressive
body-feature cache is removed. Its source, all 18 passing fixtures and all
measurements remain in candidate B's `ec45162` checkpoint; the fixture file is
also archived unchanged under `benchmarks/experiments/round4-candidate-b/`.
Two active tests retain the exact bounded highlight behavior.

C reuses only within-call token counts at the proven `\n\n[` boundary, guarded
by ordinary methods, tiktoken 0.12.0, exact regex hashes and strict UTF-8.
Unknown or overridden counters and invalid inputs use the old full-count path.
Byte bounds can prove first-fit acceptance but never replace exact final token
metadata. Both independent proof reviews found exact token-ID equality under
the certificate, including 21,952 and 19,668 artificial cases respectively.
The new sealed-count and existing token/source-work modules pass 43/43 tests.
No C dataset timing or formal source binding exists at this checkpoint.

The formal and fresh-comparison registries now pin both immutable addenda;
all original numerical, complete-output and resource gates are unchanged.
The source-free C-independent proof, historical Hotpot first-use diagnostic
and two-tokenizer Q2 compatibility helper are preserved. Q2 preparation reads
only the old 128 Hotpot IDs and old authored36, with one baseline-built vector
snapshot copied to both runtimes. The authored36 baseline workers have passed
108 calls per tokenizer. Its model and vectors are fixed; no new quality
candidate is introduced.

## Finalization before formal binding

The C1 profile preserves all 4,732 complete payloads, and its native diagnostic
preserves all 2,048 pairs. The native-only eight-cell p95 geometric mean improves
16.67%, with public token512 and token2048 p95 gains of 28.81% and 31.95%.
These are development results, not formal acceptance: the public character
p95 is 20.49% higher and the public token1024 tail gain is only 5.02%.
The final candidate therefore restores the original point-whitelist highlight
SQL; the source does not retain the speculative range specialization.

Independent audit also identified and fixed the certificate for an encoder
method replaced before its first initialization. Unknown function origins now
use full counting; both direct and functools.wraps replacements have fresh
budget-preservation fixtures. The unchanged ordinary counting algorithm and
its existing token/source tests pass 45/45 cases. The final runtime SHA-256 is
`179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
The committed selection record is now included in both evaluator registries.

The Q2 preparation-cohort guard was also strengthened before any candidate
compatibility call. The original baseline-only 216 calls and vector receipts
remain under `round4-compatibility`; new identical-vector preparations and the
final paired calls use `round4-compatibility-final` and new state directories.
No formal timing or new cohort selection has occurred. Next finish actual MCP,
historical Hotpot and paired Q2 checks, then bind one final runtime and launch
the registered formal matrix once.

The [registered plan](../benchmarks/experiments/round4-plan.json) targets
complete-output-equivalent reductions in token-budget source preparation,
projection and final counting. Actual MCP token1024 is added to the balanced
performance matrix. Quality rankings, Q2, schemas and dependencies remain
unchanged. Older project-statistics and novelty candidates remain rejected.

## Safe next steps

1. Preserve old-data development profiles and fresh correctness fixtures.
2. Implement and independently review one bounded combined candidate.
3. Commit candidate, evaluator and dependency/source binding before formal timing.
4. Execute the new claimed hosted run once, committing each completed worker.
5. Freeze component/model inputs before ID-only selection of another 256 IDs;
   exclude all three historical selections, execute one complete comparison,
   and retain costs and negative results.
6. Publish only after the fixed gates and exact-commit release checks pass.

Progress is preserved on `optimization/v0.3.2-round4`. Never overwrite original
experiment files or repeat a completed measurement to select a faster result.
Read the latest branch and this checkpoint before resuming after interruption.

## Final-source compatibility and interruption checkpoint

The final C2 source is immutable at `2d7b5e38839fb21724ad3beec6b6ebabbda45636`;
its exact nine-job CI run `43358743472` passed. The final Q2 compatibility
workers completed 1,968 calls and 984 complete non-latency payload pairs across
authored36 and historical Hotpot128, both named tokenizers and all three token
budgets. Independent offline audit verified every pair, ordered ledger event,
source/vector/model identity and recorded budget/provenance invariant without
retrieval. Reports, losslessly compressed ledgers and the paired audit live in
`benchmarks/reports/round4-compatibility-final/`. This is compatibility evidence,
not new quality or performance evidence.

The historical first-use native diagnostic lost its local execution session
after the first baseline worker completed 512 calls. The candidate worker had
zero attempted queries and an incomplete database import. Its original running
markers, raw report and ledgers are preserved losslessly under
`round4-development/final-hotpot-first-use-interrupted/`, with an explicit
interruption receipt. Do not count the incomplete attempt as paired speed
evidence or overwrite/replay its completed worker. No formal timing has run.

The independently reviewed `scripts/round4_mcp_development.py` was committed at
`6532d838` and attempted once. Its real SDK initialized and listed tools, but
this sandbox's procfs did not expose the live MCP child. The mandatory RSS
availability guard refused before any recall: zero attempted retrieval calls.
The failure report, empty ledger and source/data checks are preserved under
`round4-development/candidate-c2-mcp512-prequery-failure/` with a receipt. No
resource guard was weakened, runtime changed or diagnostic replayed.

The fixed candidate remains C2. These incomplete local diagnostics provide no
paired speed evidence. The sole registered formal run will measure all actual
MCP and resource gates on a dedicated hosted VM, committing each worker. The
formal binding pins evaluator `6532d838`, all three new runtime fixtures and
the exact C2 source. No fresh Hotpot IDs have yet been selected.

Before committing that binding, the prelaunch recovery record registers a
final-C2 4,732-call full old-cohort payload differential and one separately
identified 2,048-call first-use attempt. The latter repeats the old baseline
worker as part of a complete attempt, explicitly retaining the interrupted
512 samples without selective pooling. Both must finish correctly before
formal launch; incomplete local diagnostics are not silently waived. The
original binding draft bytes and all formal numerical gates remain unchanged.

The recovery registered at `278339fb` completed both obligations: all 4,732
final-C2 profile payloads match the preserved baseline, and all 1,024 pairs in
the separately identified 2,048-call historical first-use attempt match. The
four diagnostic p95 changes are −17.96%, −24.15%, −12.00% and −23.20%, with all
rows retained. Neither timing replaces the formal experiment. New compressed
cell/worker/ledger archives reconstruct the original reports exactly; the
initial interrupted attempt and zero-call MCP failure remain separate.

The independent `final-prelaunch-audit.json` passes all 4,732 profile pairs,
1,024 first-use pairs, 4,096 ledger events and 24 evaluator file identities.
The original binding SHA-256 remains
`d535df483cc41cc0b2381104fd99b17f4639fa2160e3b73a6661ceb8c4e58915`.
Commit that unchanged binding and launch `ci/v032-round4-performance` once.
This is launch readiness; formal performance/resource acceptance is pending.
