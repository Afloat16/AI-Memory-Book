# Changelog

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
  source/CI provenance. Publication requires all nine exact-commit CI jobs.
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
