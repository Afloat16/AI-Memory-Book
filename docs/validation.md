# Release validation

This document separates measured behavior from configuration compatibility.
Product fixtures, examples, screenshots, and capture measurements are synthetic;
the published experiments also evaluate LoCoMo and HotpotQA text corpora. No private
user conversation history was used in development or published.

## Current: v0.3.2 completed fourth-round methods and evidence

The [registered plan](../benchmarks/experiments/round4-plan.json),
[development addendum](../benchmarks/experiments/round4-development-addendum.json)
and [exact-counting addendum](../benchmarks/experiments/round4-counting-addendum.json)
retain the published v0.3.1 baseline and freeze each extension before its
measurements. The final C2 runtime is commit
`2d7b5e38839fb21724ad3beec6b6ebabbda45636`, SHA256
`179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
Ranking, indexed content, schemas, Q2 model/vector policy and fusion remain
unchanged. Complete-payload comparisons exclude only `latency_ms`.

The [C2 profile](../benchmarks/reports/round4-development/candidate-c2-manifest.json)
preserves 4,732 complete payload matches on the two old cohorts. The separate
[historical first-use recovery](../benchmarks/reports/round4-development/final-hotpot-first-use-recovery-manifest.json)
preserves 2,048 calls, 1,024 exact pairs and every start/finish event. Its four
fresh workers each reuse a connection across four configurations; neither
profiled timings nor these first-use diagnostics establish an OS-cold or formal
speed result. The [Q2 audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json)
verifies 1,968 calls, 984 exact pairs, both tokenizers and all three budgets,
alongside committed source/evaluator bytes, model files and unchanged persisted
vectors/originals. Recorded source, projection, scope, token and metadata
errors are zero. Saved hashes support equality and ledger integrity; omitted
response bodies cannot be independently re-tokenized by the offline audit.

The [prelaunch recovery registration](../benchmarks/experiments/round4-prelaunch-recovery.json)
and [independent prelaunch audit](../benchmarks/reports/round4-development/final-prelaunch-audit.json)
preserve the original interrupted 512-call attempt and local MCP failure before
any recall, together with earlier rejected candidates and adverse cells. No
favorable-round pooling or replacement of those records is permitted.

**Formal performance and the complete fresh 256-question comparison passed.**
[Run 43361086255](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43361086255)
used the committed [formal binding](../benchmarks/experiments/round4-performance-binding.json)
and triggering source `f8f1653c0653654ed574569fff1aaf4dbaeef6d1`. The
[full report](../benchmarks/reports/round4-performance-43361086255-1/report.json.gz),
[summary](../benchmarks/reports/round4-performance-43361086255-1/report.summary.json)
and [independent arithmetic audit](../benchmarks/reports/round4-performance-independent-audit.json)
verify all **56,784 calls**, 16 sequential workers, four balanced rounds and
twelve pooled cells. Complete native/MCP outputs and source/scope/cache/budget
invariants pass. Actual SDK MCP includes roundtrip and normal cache-write cost;
persistent cache clearing is outside query timers.

Pooled p95 geometric mean improves **10.1294%**. Public native token512/1024/2048
p95 improves **19.0736% / 18.4102% / 18.2009%**, and public MCP token1024 improves
**10.8021%**. The adverse public MCP character-budget p95 change, **+1.4445%**,
remains recorded. The largest registered resource mean increase is **+6.0231%**;
none exceeds the 10% review trigger, so **no resource exception or waiver** was
needed. The [performance review](round4-performance-review.md) retains all
individual-round regressions and resource samples. The aggregate pass has a
narrow 0.1294-percentage-point margin; it is not a statistical-significance or
universal-speedup result.

The [independent freeze audit](../benchmarks/reports/round4-freeze-independent-audit.json)
reconstructs the exact ordered 256 IDs after excluding all 640 historical IDs,
with zero overlap, and verifies candidate/assets/evaluator/binding/manifest Git
ordering. The [existing selection verifier](../benchmarks/reports/round4-selection-local-audit.json)
also checks the filtered canonical content and dataset fingerprint; the frozen
cohort records 635 required annotations and 2,548 supplied paragraphs. This
distinguishes independently checked IDs/history from hosted asset receipts and
the separate content verifier.

[Fresh scoring](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43363060062)
completed all ten stages, **4,608 native calls and 4,608 component searches**,
at [`eff3941`](https://github.com/Afloat16/AI-Memory-Book/commit/eff394119105d59186c730e2480d86d1436401a6).
The [assessment](../benchmarks/results/round4-comparison-43363060062-1/assessment.json)
is `complete-verified`, with no failures. All **1,536 native and 768 component
complete default-payload pairs** match. Six whole-block budget/tokenizer
projections reuse each component's first response; they add no searches.

The [offline audit](../benchmarks/reports/round4-comparison-independent-audit.json)
ran the unchanged `scripts/round4_comparison.py audit --verify-existing` once
and exactly reproduced the published assessment and Markdown. Independent
arithmetic then checked all **54 quality cells / 13,824 quality rows**, all
**12 Q2 delta cells**, **18,432 attempt events**, output hashes and source
identities. All 32 result artifacts plus the checkpoint match the immutable
result commit. This distinguishes reusing the original strict verifier from
independently implemented arithmetic; it repeats no retrieval or inference.
Saved payload hashes and reported invariants cannot reconstruct omitted text
or independently re-tokenize original responses.

At the common 1,024-cl100k cap, default complete evidence is 53.91% versus
claude-mem's 44.53%; Q2 reaches 55.08%, ai-memory 55.86% and billion-context
60.55%. Native Q2 retains 512-token completeness losses under both encoders.
The fresh 100,000-character component path has **+5.56% p95 / +5.12% p50**,
and setup tree RSS rises **548.65 → 943.53 MiB** against v0.3.1. Native lexical
finalization tree RSS also rises **655.16 → 1,107.09 MiB**. All 27 saved
setup/query/finalization phases for the nine measured modes are retained. Their sampled process
trees include evaluator/data memory; causes are not established, and these
unbalanced fresh observations are separate from the formal resource means.

The [full comparison guide](comparison.md) retains all costs and competitor
strengths. New selection does not mean a new domain; all questions are
answerable, and generated answers/abstention are outside this experiment.
Native API, component adapter, complete-read and resource costs remain distinct.
Release publication additionally requires exact-commit CI and package checks.

## Historical: v0.3.1 completed measurement and recovery

The [round-three checkpoint](../benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json)
is **complete-verified**: ten completed stages, 4,608 native calls and 4,608
component searches. All 1,536 complete default native payload pairs and 768
component payload pairs match. Independent offline recomputation verifies the
original assessment and report, all 32 result blobs and all 71 prebound
evaluator file hashes, with no retrieval replay. The
[independent verification](../benchmarks/reports/round3-recovery/comparison-cross-verification.json)
retains every Q2 gain/loss cell and exact report/checkpoint identities.

The separate [formal performance review](round3-performance-review.md) checks
47,320 original calls from four balanced rounds and ten configurations. Its
query-speed and exact-output checks pass. Original startup mean +14.04%, the
automatic `accepted: false` flag and all individual regressions stay intact;
the explicit resource review accepts the guarded query change with that cost
disclosed. The existing startup-only diagnostic is independently reconstructed
from all 80 original samples, not a replacement performance run.

The [quality-screen recovery](round3-quality-review.md) reconstructs 8,082
original calls from preserved workers without scoring again. All 20 recovered
files match the canonical hosted recovery. The project-local statistics
candidate fails 14 registered checks and remains excluded from the release.
See [source/code review](round3-code-review.md),
[registration reconciliation](round3-reconciliation.md), and the
[full result index](../benchmarks/README.md).

The published v0.3.1 source is `7b7a5d7336b9350a128f5e0a888811b1b3015e68`.
[All nine exact-commit Tests jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43273167370)
passed. The [release workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43273455233)
verified all seven assets and their downloaded hashes, then successfully
installed through the actual public tagged URL in a clean environment.
The [release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.1)
includes its exact source SHA and successful CI link. The supplemental offline
audit used the original executed evaluator. A separate
[published-source comparison](../benchmarks/reports/round3-recovery/published-release-cross-verification.json)
confirms all 71 bound evaluator files and 17 runtime/static files are identical
to the audited checkout. See
[audit provenance](round3-continuation.md#published-release-and-supplemental-audit)
and [publishing procedure](releasing.md).

The dated sections below retain evidence for their historical source pins.

## Historical completed continuation — 2026-11-12

The [strict final audit](../benchmarks/reports/hosted-final-aggregation.json)
has status `complete-verified-snapshot`: 80 fixed inputs checked, eight
derived reports verified, all four summarizers successful. It covers eight
native-budget cohorts, four semantic cohorts, 768 actual generated answers,
the 42-session/72-answer native workflow, and the completed claude-mem
component experiment.

The latest source includes a separate exact-output token-counting optimization:
2,016 development payloads match the frozen reference, while all four
512-token configurations improve p95 by 7.73%–14.45%. All 12 settings,
including larger-budget regressions, remain in the
[performance report](token-prefix-performance.md).

The integrated runtime/report tools passed
[all nine CI jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554873).
The [final aggregation job](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554831)
also succeeded after testing its verification code. The separately reviewed
automatic recovery collector passed
[all nine jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43186469865).
[Current main CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)
records the final integrated head.

The native workflow is a complete measurement **with failures**: 42/42
capture sessions and all 72 answer requests completed; 35 of 42 native
consolidations were rejected after the fixed model reached its 1,000-token
output limit. Their full usage and later answer scores remain counted.
Integrity/completeness gates do not assert that every quality metric improved.

[Completed result index](../benchmarks/README.md) ·
[Source identities and recovery record](continuation-status.md) ·
[Exact final aggregation](final-validation-aggregation.md).

The dated sections below describe the evidence available at those older commits.

## Historical checkpoint: recall-quality continuation, then unreleased

### Recovered native-budget checkpoint: e70bc3d

The interrupted continuation was already preserved on the remote branch at
[`e70bc3d2581ff96959711509b3eef11ab14f564d`](https://github.com/Afloat16/AI-Memory-Book/commit/e70bc3d2581ff96959711509b3eef11ab14f564d).
It includes the native token-budget API from
[`c73b5f8`](https://github.com/Afloat16/AI-Memory-Book/commit/c73b5f8aa086e597a3c921bf6340c385b350e332),
registered semantic and local-answer plans, the external HotpotQA input freeze,
and the native-budget development report. Those plans are not implementation or
model-result claims.

For that exact head, both the
[push workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152979344)
and [pull-request workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152987680)
completed **9/9 jobs successfully**: Python 3.10/3.12/3.13 core checks, actual
MCP stdio, the browser reader, Linux/macOS/Windows installers, and container
persistence. The [push MCP job](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152979344/job/130966302150)
records **294 tests in 17.972 seconds, OK**. This exact committed-tree count
supersedes neither the earlier 266-test snapshot nor an uncommitted-workspace
count mentioned in the checkpoint message.

The checked continuation was merged into `main` through
[PR #1](https://github.com/Afloat16/AI-Memory-Book/pull/1), at merge commit
[`ce7837f`](https://github.com/Afloat16/AI-Memory-Book/commit/ce7837fb8db7c221f39e27a531f2383385782eb1).
The CI links above identify the reviewed `e70bc3d` source head, not a claim about
every future `main` revision. The published installer remains pinned to v0.2.1.

The token API's focused checks cover citation-inclusive character and token
caps, both supported encodings, old-block preservation, source reconstruction,
code-fence boundaries, literal special-token strings, isolated caches and strict
numeric validation over real MCP stdio. See
[token API tests](../tests/test_token_budget.py),
[MCP token tests](../tests/test_token_budget_mcp.py), and
[API contract](token-budget.md).

The [frozen 128-question development report](../benchmarks/results/native-token-dev128-frozen.md)
passes its measurement gates and retains every per-query change. At 8,000
characters and 512 tokens, complete evidence rises 71.08% → 73.49% against the
prior native-excerpt packer in both tokenizers: two complete-question gains,
zero losses and zero missing previously accepted blocks. Total local p95 rises
4.690 → 11.460 ms (`cl100k_base`) and 4.728 → 17.230 ms (`o200k_base`). The
separate historical whole-page policy achieves 75.90% on this development
subset. These are distinct policies; this result cannot be substituted for the
full-public 66.72% → 66.26% historical comparison.

The [external sentence preflight](../benchmarks/reports/hotpot-sentence-preflight.json)
checks all 128 frozen HotpotQA problems and all 306 supporting facts. It records
1,272 sessions, 5,195 original sentence turns and 1,915 pages, with no supporting
fact structurally unattainable by the strict single-page metric. It is a source
attainability check performed before candidate scoring, not a retrieval or
generated-answer result. The [registered protocol](native-budget-evaluation.md)
separates regression, external transfer, generation and complete workflow costs.

### Optional coverage and real-answer evaluation

The final wrapper uses runtime SHA-256
`88f5f749be55dd4f1094d236340bec645edb6b9306fd45c720dbebac91767e57`.
Its full local suite passes **266 tests with no failures or skips** with MCP,
client and benchmark extras. The recorded run took 16.969 seconds while a
separate equivalence check was running; this is a test-run observation, not a
product performance result. New checks include actual MCP stdio and CLI
coverage opt-in, mode-specific caches, invalid parameters, provider errors,
credential echoes, HTTP disconnects, missing usage and model identity changes.

The [complete-payload equivalence check](../benchmarks/reports/coverage-mode-equivalence.json)
compares 1,387 queries at two character caps for each mode. All **2,774 default
payloads** equal the score-aware baseline; all **2,774 opt-in payloads** equal
the frozen automatic-clause experiment. Only `latency_ms` is excluded; source
text, scores, result ordering, references, warnings and truncation participate.
The query sets are regression checks, not new heldout evidence.

The earlier automatic-clause runtime is publicly preserved at
[`7a472ce`](https://github.com/Afloat16/AI-Memory-Book/commit/7a472ce35698360382d8d15a1be101343d8a2c3b).
Its Git tree equals locally measured `1cdaf8f`; this API publication changes the
commit identity, not the source bytes. Its **11 sequential stages, 29 output
hashes and 68 frozen input hashes** are recorded in the
[integrity record](../benchmarks/reports/conjunctive-integrity.json).
The experiment's timings describe that frozen automatic variant. They are not
relabeled as timings of the final opt-in API. See the
[full report](../benchmarks/RESULTS-conjunctive-recall.md).

[Answer-evaluation readiness](../benchmarks/reports/answer-eval-readiness.json)
records 128 paired public-development contexts (83 answerable, 45 unsupported)
and **zero actual generation calls**. HTTP test fixtures verify plumbing only.
Generated answers, native observer workflows and full memory costs remain
unmeasured. The older CI links below refer to their named historical snapshots;
the publication's GitHub Actions runs must be checked separately.

### Score-aware continuation

The second-round runtime is frozen at
**`0ab49d4f2be6aabe5e51c3314bb9369041af5369`**. Its full local suite completed
**244 tests in 26.498 seconds**, with no failures or skips. The ranker combines
normalized BM25 relevance from the exact and Porter routes with a fixed **2:1
exact-route preference**. `RECALL_VERSION = 7` gives the changed ranking its own
recall-cache identity, so earlier cached rankings are not reused.

Three [independent regression fixtures](../tests/test_score_fusion.py), fixed
before the score-aware development comparison, verify that a multi-term exact
fact survives Porter word collisions, an inflected query still returns the
original source evidence, and stronger matches in another project cannot enter
scoped results. Each fixture also checks delivered character budgets and source
spans. These correctness checks are separate from the measured quality and cost
interpretation in the
[score-aware continuation results](../benchmarks/RESULTS-recall-score-quality.md).

For this exact head, the
[push run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044441657)
and [pull-request run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044450305)
both completed **9 of 9 jobs successfully**: core Python 3.10/3.12/3.13, MCP,
Linux/macOS/Windows installers, Docker, and reader-browser. Both actual browser
logs recorded **13 successful checks**, including scoped Chinese search,
English/Chinese source-text preservation, import confirmation, keyboard focus,
390px mobile layout, and no page, console, request, or unexpected-dialog errors.
The same immutable Noto font pin and hashes documented below were verified in
both runs. Their screenshots and browser reports are retained in the
[push artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044441657/artifacts/13865718642)
and [pull-request artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044450305/artifacts/13866836901).

### First-round continuation

The final local suite with MCP, client, and benchmark extras completed
**241 tests in 18.420 seconds**, with no failures or skips. This continues the
preserved performance work with bounded word-form retrieval, intact evidence
selection, connection reuse, and reproducible evaluation. Quality, latency,
token costs, and remaining limitations are reported separately in the
[recall-quality continuation results](../benchmarks/RESULTS-recall-quality.md).

The recorded CI head is **`bfb09d46f41a6a734bb8e434688f196fe8723c9d`**.
Both its [push run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041835462)
and [pull-request run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041847121)
completed **9 of 9 jobs successfully**: core Python 3.10/3.12/3.13, MCP,
Linux/macOS/Windows installers, Docker, and the actual browser reader.
These links identify the verified head rather than an unspecified latest run.

| Area | Verified behavior |
|---|---|
| MCP connection lifetime | One lazy connection is reused on its owning transport thread, closes on normal or exceptional lifespan exit, and preserves response content and tool declarations. Direct SDK calls, foreign threads, and unavailable file identities use temporary connections. |
| External changes and isolation | Real stdio recall observes another writer's revision and invalidates cached evidence. Replacing the database file reopens the connection. Separate servers retain their own databases and write permissions. |
| Bounded cached work | Directory-token caching is bounded, immutable, and connection-local; warmed and cold paths return identical evidence after a rename. Persistent recall-cache limits and invalidation across connections remain covered. |
| Evidence and storage integrity | Scoped word-form recall, complete fitting lines/sentences, citation-inclusive budgets, Unicode source offsets, original-turn spans, and tiny-budget behavior are checked. Schema upgrades preserve source rows and page addresses, roll back failures, and remain compatible with an already-open legacy writer. |
| Evaluation and recovery | Recorded source changes and character/token accounting failures produce failed diagnostic reports. Sequential resumption checks source, dataset, runtime, manifest, and output hashes; rejects stale or invalid reports; and reruns an invalidated suffix. Real subprocess tests cover SIGTERM recovery and POSIX process-group cleanup when a failed leader leaves a worker that ignores SIGTERM. |

The corresponding focused tests are
[MCP lifecycle](../tests/test_mcp_lifecycle.py),
[lexical caching](../tests/test_lexical_cache.py),
[recall budgets and word forms](../tests/test_recall_quality.py),
[excerpt boundaries](../tests/test_excerpt_boundaries.py),
[index migration](../tests/test_index_migration.py),
[measurement gates](../tests/test_benchmark_gates.py), and
[resumption](../tests/test_benchmark_resume.py).

### First-round browser and font verification

The same browser smoke script executed **13 successful checks** in both CI runs.
It covered desktop project/chapter navigation, scoped Chinese search, source
reading and keyboard-focus restoration, English/Chinese text preservation,
JSON preview followed by confirmed import, inert imported content, and 390px
mobile navigation. Desktop and mobile layouts had no horizontal overflow; the
run recorded no page errors, console errors, failed requests, or unexpected
dialogs. Each run uploaded three screenshots and the browser JSON report:
[push artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041835462/artifacts/13865502206)
and [pull-request artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041847121/artifacts/13865137770).
CI artifacts expire after seven days; the earlier checked-in browser images
below remain historical evidence for their documented release.

The font preparation uses the official `notofonts/noto-cjk` commit
[`f8d157532fbfaeda587e826d4cd5b21a49186f7c`](https://github.com/notofonts/noto-cjk/commit/f8d157532fbfaeda587e826d4cd5b21a49186f7c),
with bounded download retries and timeouts. Both CI logs verified
`NotoSansCJKsc-Regular.otf` at **16,437,364 bytes**, Git blob
`dc15562470b4f842321894787a0d066879ccff8b`, and SHA-256
`2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`.
The SHA-256 comes from that commit's
[official SPDX manifest](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/_manifest/spdx_2.2/manifest.spdx.json).
The checked OFL license accompanies the font in the user font directory;
`fc-cache` and `fc-match` must succeed before browser testing starts.

## v0.3.0: retrieval and actual response costs

The complete local suite passed **174 tests** with MCP, client, and benchmark
extras, including real-tokenizer CJK/Unicode packing checks. Current CI status is
available in [GitHub Actions](https://github.com/Afloat16/AI-Memory-Book/actions).
Measured quality, response cost, and regressions are in the
[v0.3.0 results](../benchmarks/RESULTS-v0.3.0.md).

The retrieval changes are covered by source-offset, complementary-evidence,
current-versus-historical, and excerpt-boundary regressions. Actual official-SDK
stdio checks verify that compact and detailed recall return identical evidence,
that detailed mode retains exact provenance, and that responses do not duplicate
the context in `structuredContent`.

The new evaluation separates paired core retrieval, fresh-process CLI startup,
actual MCP subprocess calls, and external retrieval components. It uses exact
named tokenizers, frozen sources, new synthetic seeds, and an independent public
conversation split. The external adapters execute pinned upstream code or release
binaries; ai-memory's local MiniLM embeddings are active and completely indexed.
See [the comparison protocol](comparison-protocol.md) and
[reproduction commands](../benchmarks/README.md) for metric and transport limits.

The public text-evidence scores require full annotated utterances and matching
source coordinates. They are not generated-answer accuracy. External shared-page
scores preserve each ranker's implementation while controlling page content,
project scope, candidate count, and packing; they do not evaluate each product's
capture or summarization pipeline. Native ai-memory cost totals use the explicit
policy of reading every mapped top-k page once, not an optimized agent's minimum
required follow-up calls.

## v0.2.1: agent workflow and headless default

The updated local suite passed **159 tests** with MCP and client extras. A new
official-SDK stdio test performs the agent workflow end to end:
`remember_session` → `recall_memory` with a bounded project query → `read_page`
using the returned page ID. It verifies the write-enabled initialization policy,
the remembered fact, character budget, and source identity without a browser.
The read-only handshake verifies its distinct instructions and tool visibility.

The real-daemon regression now leaves `reader_enabled` at its default while
another socket occupies the configured reader port. Capture, configuration
reload, explicit database selection, and clean termination still succeed. This
checks that new background configurations do not require an HTTP listener.
Existing saved reader preferences remain explicit configuration values.

These checks establish the MCP protocol path and headless behavior. They do not
establish that every host model chooses the right tool without prompting; host
approval policies and model tool selection still apply. The
[agent operating guide](agent-guide.md) documents the actual contract.

## v0.2.0: verified implementation

The release candidate at `1d6a881faeb811504941d9bbb0682f587d5de344` passed
**all nine GitHub Actions jobs**:
[complete CI run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672).
The full suite with the MCP and client extras installed ran **158 tests with no
failures or skips**, both locally and in the separate MCP CI job. The dependency-free
core also passed on Python **3.10, 3.12, and 3.13**, skipping optional-dependency
cases when their extras were absent.

| Area | What actually ran |
|---|---|
| Core and source integrity | Transactional import/replacement, exact provenance, scoped retrieval, character budgets, cache invalidation, export round trips, safe paths, and HTTP protections |
| Client configuration | Schema fixtures, preservation of unrelated settings and credentials, backups, ownership, repeat setup/removal, stale-plan rejection, malformed JSON/JSONC fallback, TOML preservation, and path collisions |
| Background capture | Incremental identity and hashing, database replacement/generation, moved/removed sources, partial JSONL/UTF-8, retry deadlines, repaired files, workspace isolation, cross-process locks, metadata-only logs, and worker shutdown |
| Actual daemon process | A subprocess imported a fixture, honored an explicit database, reloaded a removed source, stopped importing its files, and exited cleanly on SIGTERM |
| MCP protocol | The official SDK client initialized a real stdio subprocess, listed tools, recalled evidence, and checked explicit write enablement |
| Linux/macOS/Windows installers | Each OS ran its shell/PowerShell wrapper, installed a local wheel into paths with spaces and Unicode, exercised reinstall and failed-install recovery, preserved existing data, refused an unrelated launcher, and installed the normal MCP/client extras |
| Docker | Built the image, ran as the non-root user, initialized MCP over container stdio, read persisted evidence, served the reader through host loopback, checked Host validation, and retained data after a container restart |
| Browser | Chrome operated the actual reader, exercised English/Chinese UI and imports, and checked desktop/mobile layouts and source-text preservation |

The installer jobs use a wheel built from the candidate source; they test the
installation mechanism and its dependencies. The project is distributed through
GitHub source releases and is not published to PyPI.

```bash
python -m pip install -e ".[mcp,clients]"
python -m unittest discover -s tests -v
python tests/installer_smoke.py --with-extras
```

## Browser evidence

The candidate used **Python 3.12.16 and Chrome 156.0.8078.79**. Its report records
**13 successful checks**, zero page exceptions, console errors, failed requests,
or unexpected dialogs. Desktop document width equals its 1440px viewport; the
mobile document width equals its 390px viewport. A fresh `en-US` browser context
selects English, and changing UI language preserves the exact conversation text
and titles.

The checked flow covers project selection, cross-session chapter browsing,
project-scoped Chinese search, source reading, focus restoration, canonical JSON
preview and confirmation, and inert display of script-like imported text. The
screenshots are actual browser captures, not design mockups:

- [English desktop](assets/reader-desktop-en.png)
- [Chinese desktop](assets/reader-desktop.png)
- [Mobile](assets/reader-mobile.png)
- [Machine-readable browser report](assets/reader-browser.json)

These files are preserved in the repository because CI artifacts expire after
seven days. The browser check intentionally lives outside unittest discovery,
so the dependency-free core does not require Playwright.

```bash
python -m pip install . playwright
python -m playwright install --with-deps chromium
python tests/browser_smoke.py
```

## v0.2.0 capture overhead sample

The reproducible [capture smoke measurement](../benchmarks/capture_smoke.py)
used **300 synthetic canonical files** across three projects and 30 chapters,
totaling **246,192 source bytes**. On the recorded Linux environment with
Python 3.12.14 and SQLite 3.53.1:

| Stage | Measured wall time | Actual import result |
|---|---:|---|
| Initial import into a new database | 435.83 ms | 300 files imported; 300 sessions updated |
| Eight unchanged scans | Median 36.95 ms; maximum 51.21 ms | Each skipped 300 files and imported/updated zero sessions |
| One changed file | 30.06 ms | One session updated; 299 files skipped |
| Next unchanged scan | 26.16 ms | 300 files skipped; zero sessions updated |

[Raw timings, counts, environment, and implementation fingerprint](../benchmarks/reports/capture-v0.2.0.json)
are retained. Run it from the repository with:

```bash
PYTHONPATH=src python benchmarks/capture_smoke.py
```

These are consecutive `sync_once` calls with warm filesystem caches, without
the normal polling sleep. The measurement includes state loading and locking.
Unchanged scans still update the manifest and heartbeat; zero imports do not
mean zero disk writes. This small sample does not measure resident CPU, RAM,
battery use, vendor-client latency, or performance at other scales.

## Historical v0.1.0 retrieval measurements

The [experiment record](../benchmarks/EXPERIMENTS.md) retains the initial short
corpus, development page-size sweep, all six segmentation/ranking combinations,
two untouched-seed evaluations, and unsuccessful query categories. Complete
per-query output is retained in compressed JSON next to readable reports. Source
fingerprints before and after those final runs match their original version.

These are **v0.1.0 measurements**, retained as historical evidence rather than
presented as a new v0.2.0 benchmark. Recall requires the exact annotated evidence
to survive into the budgeted context with its correct source span; it is not an
LLM answer score. Local latency excludes process startup, transcript capture,
MCP transport, networking, and inference. Result caching was disabled while
SQLite/OS page caches remained available.

The original v0.1 core and browser evidence is also available in its
[core run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42990594538)
and [browser run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42991673979).

## What these checks do not establish

- Client profiles follow official configuration schemas and have fixture tests;
  every vendor application was not interactively launched and authenticated.
- Native service definitions and command flows have focused tests. The installer
  matrix does not exercise real login/logout, sleep/resume, or long-running user
  sessions under systemd, launchd, and Task Scheduler.
- Import formats are covered by representative synthetic records, not every
  historical vendor version or multimodal format. Current Kimi Code has MCP
  configuration support; native capture is limited to the separately named
  legacy Python Kimi format.
- Generated histories and a small local capture measurement do not establish
  performance on a large personal archive, network disk, or every operating
  system. Browser coverage is Chrome/Chromium at the stated sizes.
- Lexical retrieval does not guarantee semantic recall, authoritative conflict
  resolution, automatic host injection, or end-to-end model answer quality.
- Component comparisons cover pinned implementations and common supplied pages.
  claude-mem's observer/Chroma workflow and billion-context's full proxy
  compression/decompression remain unmeasured. The separate Book/ai-memory
  workflow does measure native capture, explicitly enabled consolidation and
  answers under its fixed small model, including native truncation failures.
  These results do not establish another configuration's quality or cost,
  and the declared transport boundaries differ.
