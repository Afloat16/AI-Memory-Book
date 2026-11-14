# Changelog

## 0.3.4 — Unreleased; startup scope accepted

A candidate focused on startup performance and initialization correctness,
using the exact A runtime selected for this confirmation. The prospective
startup study and its disclosed resource tradeoff are accepted under the
original review policy. The fresh component comparison and final release checks
remain separate. No publication or final-CI success is claimed at this checkpoint.

### Initialization and command loading

- Put initial schema and FTS setup in one transaction, preserving rollback on
  setup failure and competing-initializer behavior. The later covering-index
  and connection PRAGMA steps retain their existing boundaries; this is not a
  claim that every constructor side effect shares that transaction.
- Load command metadata without importing archive/client machinery. Preserve
  the public `MemoryBook` class, its identity, full explicit API import and
  existing command behavior. Keep schema 3 and the existing dependency floor.
- Retain A's request-local metadata reuse with complete-output compatibility.
  Exclude B's unsupported dense-project ranking implementation.

### Prospective startup confirmation and disclosed costs

- Complete the unique registered 480-sample startup matrix: six boundaries,
  four balanced AB/BA/BA/AB rounds, and forty observations per source/boundary.
  Independent offline auditing verifies every original sample and all 960
  start/finish events, source/evaluator identities, protocol output and state.
- New empty-archive constructor median improves **24.518 → 4.164 ms
  (−83.02%)** and p95 **27.374 → 6.358 ms (−76.77%)**. Real CLI help median
  improves **102.903 → 48.750 ms** and p95 **104.104 → 49.547 ms**; real CLI
  version median improves **101.346 → 47.479 ms** and p95 **103.116 → 48.259 ms**.
  All three primary targets pass their original percentage and absolute gates.
- Preserve the complete API-import slowdown: median **33.506 → 33.920 ms
  (+1.24%)**, p95 **33.822 → 34.433 ms (+1.81%)**. Existing-archive constructor
  median/p95 are **0.640 → 0.632 / 0.668 → 0.666 ms**; actual official-SDK
  initialization median/p95 are **627.601 → 620.104 / 632.233 → 624.837 ms**.
  All registered secondary regression guards pass.
- Keep the original automatic `accepted:false`: existing-archive whole-helper
  system CPU increases **18.646 → 21.121 ms (+2.474 ms, +13.2703%)**, triggering
  the original resource-review rule. Whole-helper wall time increases
  **138.762 → 139.996 ms (+0.8891%)**. The increase occurs in every round;
  its phase-specific causal allocation is not established by saved data.
  Two independent reviews and the [explicit startup decision](benchmarks/experiments/round6-startup-decision.json)
  accept this disclosed tradeoff under the original resource policy. The raw
  automatic verdict and original workflow `failure` remain unchanged.
- Retain all **6 pooled / 26 round timing increases** and **9 pooled / 27 round
  resource increases**. Kernel child-usage records and sampled MCP RSS/HWM
  retain their stated boundaries and do not establish isolated product-memory
  savings. No samples were discarded or timing repeated.

### Retrieval evidence and limits

- Preserve all **2,304** historical Hotpot256 complete default outputs against
  v0.3.3, with **4,608** audited start/finish events, on A's exact final runtime.
- Disclose that A's roughly **1%** development recall gains did not justify
  advancing to the original **10% / 15% / 10%** formal recall targets. That
  four-round formal matrix was **not run or accepted**. B regressed public
  native p95 by approximately **19–29%** and actual-MCP p95 by **23.9246%**;
  its implementation is excluded and its complete experiment remains saved.
- The separately frozen fresh comparison and exact final CI/package/public
  installer checks are pending. Historical C7 and Q2 numbers are not new
  v0.3.4 improvements; no whole-product or all-dimensions superiority is claimed.

[Startup review and every adverse observation](benchmarks/reports/round6-startup-43598913606-1-local-audit/review.md) ·
[Original startup plan](benchmarks/experiments/round6-startup-plan.json) ·
[Source selection and experiments](docs/optimization-round6.md) ·
[Release notes and remaining checks](docs/releases/v0.3.4.md)

## 0.3.3 — 2026-11-14

A normal GitHub release that reduces retrieval metadata, exact token-counting
work and certified MCP output dispatch while preserving complete default evidence.
All fixed numerical performance gates pass against published v0.3.2; a separate
independent resource review accepts three disclosed startup costs.

### Retrieval, exact counts and MCP output

- C7 combines the official MCP SDK's native stdout write and immediate flush in one worker dispatch, reducing dispatch overhead while preserving complete messages, serialization and lifecycle.
- On the certified official SDK 1.30.0 standard-stream path, combine each
  native UTF-8 write and its immediate flush in one default worker dispatch.
  Keep official JSON serialization, framing, stdin, lowlevel initialization,
  lifespan and ordinary result-cache writes. Unsupported/custom paths retain
  FastMCP's original stdio execution. No response batching or text buffering.
- Add a narrow derived metadata index and batch shared chapter/session rows.
  Validate every referenced directory before pruning; use a strict title-score
  upper bound to skip candidates that cannot enter the existing ranking pool.
  Retain ties, full candidate counts and custom/semantic/coverage fallbacks.
- Reuse identical ordered lexical routes and per-query directory overlaps.
  Reuse certified sealed-block suffix counts and reject impossible supplemental
  pages after the existing source-map checks.
- Add a lazy per-connection exact-count memo, shared by both tokenizers and
  bounded by 2,048 entries / 2 MiB of retained text objects. Charge Unicode text
  after encoding, preserve complete string keys and exact encoder/core/method
  receiver identities, and release retained text when the connection closes.
- Keep query-result cache controls, source reads, corruption checks, ranking,
  citations, context limits, schema 3 and dependency requirements unchanged.
  Unknown/custom tokenizer cases retain complete exact counting.
- Set a separate 4 MiB SQLite pager target. The index has first-open and storage
  costs, and memo container/key/value overhead is additional to its text cap.
  Neither memory setting is a whole-process limit.

### Accepted performance and compatibility

- Complete the single frozen 56,784-call comparison, sixteen sequential workers,
  four balanced AB/BA/BA/AB rounds and twelve pooled cells. All 28,392 complete
  non-timing output pairs and source/scope/budget/cache invariants match.
- Pooled p95 geometric mean improves **14.7976%** against published v0.3.2. Public native token512/token1024/token2048 p95 changes **-15.1867% / -14.2362% / -15.7406%**. Actual public SDK MCP token1024 p95 is **6.711 → 5.894 ms**, an improvement of **12.1734%**.
- All twelve pooled p50 and p95 values improve. All per-round observations are retained.
- All fixed numerical gates pass. The original automated verdict remains `accepted:false` because three startup resource increases required review: import means rise 3.197 / 2.990 ms, and public-labeled fresh-empty-database opening rises 5.100 ms (21.4109%). A [separate resource review](docs/round5-c7-resource-review.md) accepts these startup costs with all samples and attribution limits retained. No timing was repeated, threshold lowered or original automatic verdict rewritten.
- Reproduce all 2,304 saved default outputs on historical Hotpot256: 1,536
  native calls over both tokenizers and three caps, plus 768 component calls.
  This retains old default quality results without a new competitor or Q2 run.
- Preserve the complete rejected C3, C5 and C6 formal runs, every earlier
  development candidate and all C4/C5/C6/C7 development observations. C5 and C6
  retain their actual-MCP p95 failures (6.673181% and 5.798911%
  against the unchanged 10% gate). Commit formal source,
  evaluator, binding and each worker checkpoint before progressing.
- Publish through the explicit normal GitHub release channel, preserving older
  prerelease metadata and existing exact-source CI, package and installer gates.

[Release notes](docs/releases/v0.3.3.md) · [Full performance review](docs/round5-c7-performance-review.md) ·
[Source and decisions](docs/optimization-round5.md) · [Upgrade guide](docs/deployment.md#upgrading)

## 0.3.2 — 2026-11-13

An experimental release that reduces repeated token-budget assembly work while
preserving complete default evidence. Formal performance and the fresh
comparison have completed with strict saved-result audits.

### Recall assembly and token budgets

- Defer source-unit parsing for pages with a full mapped-segment equality
  certificate while preserving the original eager checks for uncertified maps.
  Original turns remain captured inside the database snapshot; deferred work
  performs no later database reads. Use bisection to narrow projection scans
  without changing containment, source equality or overlapping-unit behavior.
- Reuse the exact count of the last accepted context and an already private
  candidate dictionary. Preserve first-fit order and rejection behavior.
- Reuse sealed citation-block token counts within one call for the inspected
  tiktoken 0.12.0 `cl100k_base`/`o200k_base` patterns. Keep exact final counts and
  the historical fallback for custom counters, unknown encoder origins,
  unsupported patterns and invalid text boundaries.
- Preserve lexical ranking, global BM25, scopes, source coordinates, MCP formats
  and Q2 model/vector/fusion behavior. Retain schema 3 and existing dependency
  requirements. Exclude the rejected body-feature cache and proposed highlight
  query specialization; preserve their source and negative development results.

### Performance and compatibility

- Complete the sole registered 56,784-call formal run over sixteen workers,
  four balanced rounds and twelve pooled cells. Complete outputs and recorded
  invariants match v0.3.1. Pooled p95 geometric mean improves 10.13%; public
  native token512/token1024/token2048 p95 improves 19.07%/18.41%/18.20%, and
  actual public SDK MCP token1024 p95 improves 10.80%.
- Retain the public MCP character-budget p95 increase of 1.44% and all adverse
  round-level cells. The largest registered resource mean increase is 6.02%
  for public token MCP startup. The original automatic verdict is accepted
  with no resource exception. The aggregate passes its 10% gate by only
  0.1294 percentage points; no statistical-significance claim is made.
- Audit 1,968 completed Q2 calls and 984 matching complete non-latency payload
  pairs against v0.3.1 on authored36 and historical Hotpot128, both tokenizers
  and 512/1,024/2,048-token budgets. Identical saved vectors, source identities
  and attempt ledgers are verified. These regression cohorts establish
  compatibility, not new quality or performance gains.
- Complete the new 256-question comparison, excluding all 640 historical IDs
  with zero overlap. All 9,216 calls and 54 quality cells pass integrity checks;
  1,536 native and 768 component default-payload pairs match. Independent offline
  arithmetic verifies the saved records without repeating retrieval.
- At 1,024 cl100k tokens, default complete evidence is 53.91% versus claude-mem
  FTS 44.53%; optional Q2 reaches 55.08%. ai-memory remains higher at 55.86%
  and billion-context at 60.55%. Default search-adapter p95 is 3.488 ms versus
  34.655 ms and 39.925 ms for the tested claude-mem and ai-memory adapters;
  their interface boundaries differ. Q2 has the highest packed MRR in this
  view, while retaining native 512-token completeness losses.
- Retain the separate fresh 100,000-character component p95 regression of
  5.56% and sampled setup process-tree RSS rise from 548.65 to 943.53 MiB.
  Native lexical finalization RSS also rises from 655.16 to 1,107.09 MiB.
  These unbalanced descriptive observations include the evaluator and corpus;
  their cause is unresolved. They are separate from the formal balanced gate.
- Preserve all development profiles, adverse cells and interruption receipts.
  Update v0.3.2 installer defaults and examples, retaining the archive, prior
  environments and historical release instructions. Pin packaging to the
  accepted runtime and preserve the independently merged historical audit tools.

[Release notes](docs/releases/v0.3.2.md) · [Round-four decisions and evidence](docs/optimization-round4.md) ·
[Upgrade guide](docs/deployment.md#upgrading)

## 0.3.1 — 2026-11-13

An experimental release that reduces project-scoped query work while preserving
the existing default retrieval policy, source references and context budgets.

### Recall performance

- For eligible project-scoped requests, use indexed project rowid bounds and an
  explicit FTS outer loop to skip unrelated postings. Project envelopes exceeding half the archive range, and
  session-scoped recalls, retain the original query plan. Global BM25 statistics, scope filters,
  deterministic ordering, candidate limits and default cache identity stay intact.
- Complete all 47,320 registered calls over two old corpora, five settings and
  four balanced rounds. Full non-timing outputs match. The geometric mean of
  pooled p95 across ten cells improves 11.36% versus v0.3.0.
- On the 1,015-question public corpus at 4,000 characters, native p95 falls
  5.054 → 3.737 ms (26.05%) and actual SDK MCP p95 falls
  7.409 → 5.937 ms (19.87%). Keep the synthetic 512-token p95 increase of 0.125%.
- Accept a documented startup tradeoff after independent review: the public workers' mean
  fresh empty-database opening time increases 4.838 ms (14.04%). The original performance report
  retains its automatic resource-review flag and `accepted: false`; the explicit
  review is a separate decision, not a rewritten benchmark result.

### Evidence and experiment recovery

- Restore and audit all eight workers and 8,082 calls of the registered
  project-statistics screen with zero retrieval replays. Preserve original
  worker/ledger bytes, aggregate identities and the interruption record.
  Fourteen loss checks reject the candidate; it is not included in this release.
- Complete the single registered new-256 comparison, run `43267797247-1`:
  4,608 native calls and 4,608 component searches pass integrity checks.
  Baseline/default outputs match across 1,536 native pairs and 768 component
  pairs after removing only `latency_ms`. The selection excludes all 384 earlier
  question IDs. At 1,024 `cl100k_base` tokens, default lexical complete evidence
  is 52.34% versus claude-mem FTS 45.31%; optional Q2 reaches 54.69%.
  ai-memory remains higher at 55.86%, and billion-context leads at 58.20%.
  Retain Q2's native 512-token completeness regressions under both tokenizers,
  every per-question loss, separate search/read costs and the original run's
  exact binding. Separate unexecuted registrations do not replace that binding.

### Local model behavior and installation

- Opt out of ONNX Runtime telemetry before its import and through its runtime
  API when initializing Book's optional Q2 model.
- Retain the small universal-wheel installer, one-command MCP setup and optional
  background capture. Pin installer examples and defaults to v0.3.1; the core
  adds no required dependencies or database-schema migration.
- Keep source/plan checkpoints and completed-worker evidence in Git, including
  failed attempts. Model and dataset downloads remain explicit preparation steps.

[Release notes](docs/releases/v0.3.1.md) · [Round-three protocol and results](docs/optimization-round3.md) ·
[Performance and resource review](docs/round3-performance-review.md) ·
[Current component comparison](docs/comparison.md) · [Upgrade guide](docs/deployment.md#upgrading)

## 0.3.0 — 2026-11-12

An experimental release of the verified round-two implementation. Default
retrieval stays lexical; semantic fusion, multi-fact coverage, exact token caps
and indexed MCP references are explicit options.

### Retrieval and evidence

- Add local Porter word-form candidates alongside exact FTS, preserving ranking
  margins, applying project/chapter/session scopes before candidate limits, and
  packing intact original source units within the context budget.
- Add optional exact `cl100k_base` / `o200k_base` limits in Python, CLI and MCP.
  Citations and separators count toward the context limit; outer protocol
  metadata remains separately accounted for.
- Add opt-in Q2 local semantic retrieval and explicit multi-fact coverage.
  Compatible semantic indices are reused; retrieval caches are versioned
  independently. Small-budget and per-question regressions remain documented.
- Upgrade older database schemas transactionally to schema 3 while preserving
  original source rows, page addresses and source spans. Keep cross-process
  revision invalidation and repair derived indices after an older writer changes
  the archive.

### Performance and MCP

- Reuse lexical preparation, normalized directory text and the MCP connection;
  preserve Unicode/source offsets and fetch selected pages in a batch. The final
  core optimization lowers pooled actual-MCP p95 by 1.25%–9.50% in the paired
  measurement, with identical full non-timing payloads. Public-corpus ingestion
  and unchanged-session replay times fall 46.45% and 61.38% respectively.
- Return compact JSON MCP text with source identities by default; full source
  coordinates remain available through `details: true` and `read_page`.
- Add startup-only `mcp --source-format indexed`. Its response-wide session table
  reversibly encodes repeated references. In the documented public 4,000-character
  setting, response-text tokens fall 19.63% and first-call reference tokens fall 8.15%.
  Default clients keep their existing schemas and initialization instructions.

### Installation and documentation

- Pin all three installers to v0.3.0 and install its small universal wheel by
  default. Historical tags, exact commits and explicit local sources retain their
  existing routes. Managed installation preserves the archive and old environment.
- Publish wheel/source distributions, installer files, SHA-256 checksums and
  source/build provenance. Publication requires all nine exact-commit CI jobs,
  linked from the release notes.
- Replace the long READMEs with bilingual workflow diagrams, one quick-start path,
  current results and links to detailed operating and evaluation guides.

### Validation and limits

- Preserve complete paired performance, actual MCP, semantic-development and
  256-question native/component results, including claude-mem 15.18.1,
  ai-memory v3.4.5 and the pinned billion-context kernel. Retain preparation,
  token, latency, memory/storage boundaries, failed attempts and independent audits.
- Retain real generated-answer and capture/consolidation diagnostics under their
  original source/model identities. They are not final-answer scores for this
  release's Q2 or indexed-reference options.
- Reject both bounded novelty-ranking experiments; the qualified production
  runtime is unchanged. No universal quality, speed or cross-domain claim is made.

[Release notes](docs/releases/v0.3.0.md) · [Full current comparison](docs/comparison.md) ·
[Benchmark protocols and artifacts](benchmarks/README.md) · [Upgrade guide](docs/deployment.md#upgrading)

## 0.2.1 — 2026-11-11

### Agent-first operation

- Reframed the primary workflow around AI clients using stdio MCP and optional background capture. Added an agent operating guide covering direct, project-scoped recall, evidence budgets and references, focused follow-up reads, and source trust boundaries. The browser reader remains an optional inspection utility.
- Refined the existing MCP initialization instructions to make the agent workflow explicit: recall only when prior work matters, use a known project ID, and browse or read further only when needed. Initialization does not preload the memory directory or conversation history. Hosts and models still control tool invocation.
- Clarified the instructions for explicitly enabled writes: `remember_session` replaces a complete session, so a fragment must not overwrite a stored conversation. Extended real MCP client/server protocol checks to inspect initialization instructions for read-only and write-enabled connections.

### Headless defaults and upgrades

- Changed new background configurations, and configurations without `reader_enabled`, to default to `false`. Daemons and user services therefore run capture without starting an HTTP reader unless the configuration enables it. One-pass and continuous `sync` remain headless.
- Preserved existing explicit reader preferences during upgrades and repeated setup. Users can inspect sources through `memory-book serve` or opt in to a daemon reader with `reader_enabled: true`.
- Updated pinned installer defaults and installation examples to v0.2.1. Retained previous release measurements and validation evidence under their original versions; this patch makes no new retrieval-quality or latency claim.

## 0.2.0 — 2026-11-11

### English-first documentation and reader

- Made the English README the repository landing page, retained a Chinese quickstart, and added English deployment and compatibility guides.
- Added English/Chinese reader controls with browser-language defaults and a saved locale preference. Original titles and conversation evidence keep their source language.
- Added real-browser checks for locale switching, source-text preservation, an English default, and desktop/mobile layouts.

### Installation and client integration

- Added an isolated Python installer with shell and PowerShell entry points, pinned release/commit sources, and local source/wheel installation support.
- Added `setup`, `clients`, `disconnect`, and `doctor`, with client-specific MCP configuration plans, dry runs, backups, conflict checks, and atomic merges. Unsupported JSONC is left for a manual merge; Codex TOML uses the optional `clients` dependency to preserve comments.
- Added MCP profiles for Claude Code/Desktop, Codex, Gemini CLI, current and legacy Kimi, Cursor, OpenCode v2, Copilot CLI, Qwen Code, and LM Studio, plus a generic export-only snippet. Profiles represent supported configuration schemas, not an end-to-end certification of every vendor application.
- Changed the default database to a shared per-user data directory so CLI, clients, and background services use the same archive. Added `MEMORY_BOOK_HOME` and configuration-path overrides. Existing v0.1 working-directory databases are detected but never moved automatically; explicit `--db` remains available.

### Optional background capture

- Added explicit watched sources, `watch` management, `sync --once`, and a foreground daemon with optional local reader. MCP setup alone does not collect history; `--capture` opts in to existing and future supported text transcripts.
- Added metadata/hash-based incremental skipping, stable fallback session IDs, transactional session replacement, trailing partial JSONL/UTF-8 handling, per-file error isolation and retry, size limits, and metadata-only capture logs.
- Bound manifest state to the database path, generation, and revision so switching or recreating a database triggers reimport. Removed sources release ownership without deleting archived memory; active duplicate session identities produce a conflict.
- Added deterministic workspace/bucket project mapping, exact workspace filtering where supported, symlink/artifact exclusions, state-file worker locks, interruptible polling, and daemon configuration reloads. Reduced or invalid capture configurations stop the previous capture scope.
- Added current-user service management through Linux `systemd --user`, macOS LaunchAgents, and Windows login Scheduled Tasks. Service installation is opt-in and keeps memory data when uninstalled.
- Added Gemini legacy JSON and append-only JSONL replay, including patches and rewinds, plus the verified legacy Python Kimi `context.jsonl` importer. Current Kimi Code has an MCP profile but no native transcript-capture claim.

### Containers and evidence

- Added a non-root Docker image and persistent-volume Compose examples for the local reader and stdio MCP. Internal `0.0.0.0` binding requires `--container-bind`; the supplied host port mapping remains loopback-only. Public multi-user hosting is not supported.
- Added focused regression coverage for importer replay, incremental capture/recovery/isolation, configuration safety, service generation, and daemon lifecycle, plus installer/container validation workflows.
- Retained the published v0.1 retrieval reports and their original source hashes as historical measurements. Those timings do not include v0.2 watcher, installer, client, or service overhead; this release makes no new retrieval-quality or competitor-performance claim.

The archive and query caches remain unencrypted local data. MCP retrieval and native transcript capture are separate capabilities. Semantic embeddings, authoritative fact-version resolution, and guaranteed automatic context injection remain unimplemented.

## 0.1.0 — 2026-11-11

- Local SQLite source archive and project/task/session-section/page hierarchy.
- Direct, character-budgeted recall with CJK/English FTS, exact source intervals, and persistent cache invalidation.
- Adaptive question grouping and long-turn pagination, with whole-session and per-turn evaluation baselines.
- CLI, loopback web reader, paginated directories, source JSON and Markdown book export.
- Text importers for canonical JSON, ChatGPT current branches, Claude Code JSONL, and Codex rollout JSONL.
- Optional official-SDK MCP stdio integration with read-only defaults and explicit write enablement.
- Reproducible bilingual synthetic evaluation, development parameter sweep, and untouched-seed evaluation reports.
- Regression coverage for transactional updates, cache invalidation, isolation, provenance, Unicode, unsafe export destinations, pagination, and actual MCP client/server communication.

At the time of this experimental initial release, semantic embeddings, automatic host capture, authoritative fact-version resolution, and multi-user hosting were not implemented. The optional capture functionality was added in v0.2.0 as described above.
