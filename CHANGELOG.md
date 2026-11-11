# Changelog

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
