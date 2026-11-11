# Changelog

## Unreleased — recall quality continuation

- Continue the preserved v0.3.0 performance branch with bounded English word-form retrieval. Keep exact FTS and add SQLite's local Porter index. When the routes differ, combine their max-normalized BM25 scores with a fixed 2:1 exact/stem weight, preserving score margins that rank-only fusion discarded; invalidate prior recall caches with retrieval version 7. No model, embedding package, network request, or provider key is added to the core.
- Preserve intact source lines or sentences when equally relevant excerpts fit. Reuse a sliding match window, reserve citations before sharing the body budget, and return unused short-page space to longer selected pages.
- Prefer distinct query-term coverage and complete source units before repetition frequency, so a repeated keyword fragment cannot displace an equally covered intact fact. Increment the recall-cache version for this behavior change.
- Reuse immutable directory tokens in a bounded connection-local cache and precompile lexical regular expressions without changing normalization or ranking. Clear retained directory text when the connection closes.
- Reuse one lazy SQLite connection within an MCP transport lifespan, with owner-thread checks, file-replacement detection, lifecycle cleanup and temporary-connection fallback. Tool declarations and compact/detailed payload contracts are unchanged; external writes still invalidate cached results through the database revision.
- Apply project/chapter/session scopes before each candidate cap and defer directory/display metadata until needed. Identical ordered retrieval routes retain the original BM25 scale and behavior.
- Upgrade schema 1/2 to schema 3 transactionally without changing schema-2 source rows, page addresses, or source spans. A revision guard repairs the stem index if an already-open old writer commits after upgrade; current writers keep incremental index updates.
- Separate retrieval cache versions from source/index settings. Only truncated pages need word-form highlight work; full-page reads and compact/detailed MCP contracts remain available.
- Correct benchmark version labels and record the measured source bytes, Git identity, and uncommitted or ignored Python changes. Add a repeatable index-upgrade cost and source-preservation measurement.
- Make budget, source-stability and size-accounting failures fail evaluation while preserving diagnostics. Add explicit corpus plans and a sequential checkpointed runner that validates source/data/runtime identity and completed artifacts before resuming.
- See [the continuation report](benchmarks/RESULTS-recall-quality.md) for measured quality, costs, regressions, and the distinction between retrieval evidence and generated answers.

## 0.3.0 — 2026-11-11

### Retrieval and context cost

- Reused lexical preparation across excerpts, added offset-preserving ASCII/Unicode fast paths, cached repeated title normalization within a recall, and fetched selected pages in one SQL query. Original text, source IDs, and exact source spans remain available.
- Shortened context citation headers while retaining page, project, session, and date identity. Full hierarchy titles remain in page metadata and directory tools.
- Improved equal-coverage excerpt placement so text following a matching topic is less likely to be cut off. Added a bounded query-term novelty bonus to reduce redundant pages crowding out complementary evidence.
- Added conservative timestamp preference for explicit current/latest queries within the same chapter and identical lexical coverage. Historical/date-bound queries keep relevance order; this heuristic does not resolve conflicting facts authoritatively.
- Incremented the retrieval cache version to invalidate old results. The database schema remains version 2; no source migration or reindex is needed.

### MCP response contract

- All tools now return one compact JSON text block, avoiding SDK pretty-printing overhead. `browse_projects` contains a JSON array in that block.
- `recall_memory` defaults to compact `project`/`session_id`/`turn_index` references. Pass `details: true` to obtain exact source coordinates, excerpt spans, and diagnostics. `read_page` keeps full provenance; CLI and HTTP JSON responses retain their detailed fields.
- Shortened initialization instructions without removing source trust, scope, optional navigation, or write-replacement rules. Added actual stdio checks that compact and detailed modes preserve identical evidence.

### Reproducible evaluation

- Added paired v0.2.1/current evaluation with exact `cl100k_base` and `o200k_base` token counting, shared whole-evidence token caps, fresh-process measurements, and actual MCP stdio cost measurement. Tokenizers are an optional benchmark dependency, not a runtime requirement.
- Added pinned, hash-verified LoCoMo data loading, download instructions, and a conversation-level development/heldout split. Public data, expected answers, model weights, and competitor binaries are not bundled in the MIT package.
- Added adapters that execute the actual pinned billion-context search kernel and ai-memory v3.4.5 native APIs, including its local MiniLM hybrid MCP mode. Shared-page results distinguish ranking, native payload/read cost, and transport boundaries. claude-mem remains unmeasured.
- Published complete result curves and category failures in the release evaluation report; retrieval evidence coverage is not an LLM answer-quality score or a universal product-performance claim.

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
