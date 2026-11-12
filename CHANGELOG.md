# Changelog

## 0.3.1 candidate — 2026-11-13

This candidate completes the third optimization round. Its measured runtime is
`2d199b93f650eccd3dd239178822b31001b880e3`, SHA-256
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.
Default retrieval stays lexical. A candidate build is not a published tag.

### Retrieval performance

- Narrow FTS work with a safe project rowid envelope only when it is selective.
  Keep scope predicates before the 96-candidate limit, global BM25 statistics,
  deterministic ordering and all evidence/source fields. Session-scoped and
  nonselective layouts retain the previous query path.
- Compute bounds inside the existing read transaction without caching them;
  cover cross-process insert/delete/relink, interleaved projects, Unicode and
  candidate-limit behavior in tests.
- Preserve complete non-timing output in the registered 47,320-call, four-round
  ABBA matrix. Ten pooled p95 ratios improve by 11.36% geometrically on average;
  public native p95 improves 26.05% and actual MCP p95 19.87%. The synthetic
  512-token cell regresses 0.125%. No pooled p50/p95 cell regresses over 5%.
- Retain the original empty-database startup flag: +4.838 ms / +14.04%.
  The original report still says `accepted=false`; a separate, documented
  resource decision accepts that cost after 80 fresh startup diagnostics.
  No original retrieval call was repeated or replaced.
- Disable ONNX Runtime telemetry before optional model initialization.
  No schema migration, new core dependency or default semantic mode is added.

### Completed evidence and rejected work

- Recover all eight original project-statistics workers and 8,082 calls from
  intact uploaded chunks and ledgers. Preserve the interrupted aggregate prefix,
  verify it against the reconstruction, and execute zero new retrievals.
  The candidate fails the registered no-loss screen and remains excluded.
- Freeze candidate/evaluator/model/upstream identities before selecting 256
  additional HotpotQA IDs with zero overlap against the prior 384. Complete all
  ten stages: 4,608 native calls, 4,608 component searches and 1,280 additional
  ai-memory page reads. All source and budget checks pass; 1,536 native and 768
  component default payload pairs match v0.3.0 after removing timing only.
- On common top-five, 1,024-token packing, default Book completeness is 52.34%
  versus claude-mem FTS 45.31%, with measured search roundtrip p95 2.784 ms
  versus 22.826 ms. ai-memory (55.86%) and billion-context's search kernel
  (58.20%) lead Book completeness here; billion is also faster. Preserve every
  budget, subgroup, Q2 loss and component interface boundary.
- Keep Q2 optional: it has a net gain of six complete questions at 1,024/2,048-token native
  caps and a net loss of six at 512 under each tokenizer on this new selection.
  These are evidence retrieval results, not final-answer or abstention scores.
- Add a read-only final evidence audit with immutable result blobs, exact-HEAD
  runtime hashing, original auditors and zero retrieval/model/timing calls.

### Packaging and documentation

- Set package and installer versions to 0.3.1 and bind release preparation to
  the measured runtime hash. Reject changed runtime bytes before packaging.
- Prepare seven small release assets, verify wheel and sdist in separate clean
  environments, and install the produced wheel with default MCP/client extras.
  Preparation-only workflows do not publish GitHub releases.
- Update English/Chinese README, release notes, deployment and comparison
  documentation with current evidence and explicit historical labels.
  No source/index/archive migration is needed for this runtime change.

See [optimization and all ten timing cells](docs/optimization-round3.md),
[new component comparison](docs/round3-comparison.md),
[startup resource decision](docs/round3-startup-resource-review.md) and
[candidate installation](docs/deployment.md#try-the-v031-candidate-before-publication).

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
