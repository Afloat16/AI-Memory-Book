# Release validation

This document separates measured behavior from configuration compatibility.
Product fixtures, examples, screenshots, and capture measurements are synthetic;
v0.3.0 also evaluates an independently published LoCoMo text corpus. No private
user conversation history was used in development or published.

## Current candidate: v0.3.1 third-round completion — 2026-11-13

The candidate's runtime SHA-256 is
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`,
matching measured commit
[`2d199b9`](https://github.com/Afloat16/AI-Memory-Book/commit/2d199b93f650eccd3dd239178822b31001b880e3).
Final documentation and packaging changes do not change those runtime bytes.

| Validation | Completed result | Evidence |
|---|---|---|
| Formal performance | 47,320 calls / 16 workers; numeric gate passes; full non-timing output unchanged; all ten cells retained | [Optimization report](optimization-round3.md), [original run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515) |
| Original startup flag | Original automatic `accepted=false` preserved; disclosed +4.838 ms / +14.04% accepted in a separate review after 80 fresh startup diagnostics | [Resource review](round3-startup-resource-review.md), [diagnostic run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43266672875) |
| Interrupted quality experiment | Original 8,082 calls / eight workers reconstructed from intact chunks, audited without new retrieval, candidate rejected | [Decision](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/decision.json), [recovery run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43266603949) |
| New frozen comparison | All ten stages complete; 4,608 native calls + 4,608 component searches; no budget/source/scope failures; 1,536 native and 768 component payload pairs identical | [Assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json), [run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247) |

The new 256-question selection excludes the prior 384 question IDs. It uses
607 support annotations from the same public HotpotQA source, all answerable.
It measures retrieval evidence, not generated-answer accuracy, abstention or
generalization. The [full comparison](round3-comparison.md) retains both the
advantage over claude-mem FTS and the quality/latency losses against other
components, including Q2's small-budget regressions.

Final integration checks use all nine normal CI jobs, the
[read-only evidence audit](../.github/workflows/round3-final-audit.yml) and
[prepare-only packages](../.github/workflows/release-prepare.yml).
The audit pins original result Git blobs and input SHA-256 values, runs the
original report auditors, and verifies that it changed no inputs and executed
no retrieval/model/timing calls. Packaging binds the runtime hash, checks the
wheel and sdist in separate clean environments, and installs the produced wheel
with MCP/client extras. The delivery PR records the exact final source commit,
Actions results and artifact. This candidate documentation does not imply that
a public v0.3.1 tag or release already exists.

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

## Historical recall-quality continuation

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
