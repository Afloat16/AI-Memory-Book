# Client integrations and import formats

AI-Memory-Book provides local **stdio MCP tools** and optional transcript import.
Connecting MCP gives a client access to stored memory;
[background capture](deployment.md#background-capture) imports supported files
only after you enable it. These are separate capabilities.

## Connect a client

Install the MCP and client extras using the [release installer](deployment.md),
then inspect and apply a configuration:

```bash
memory-book clients
memory-book setup --client claude-code --dry-run
memory-book setup --client claude-code
```

Repeat `--client` to share one database across clients. `--all` selects detected
clients; detection checks known config paths and executables without reading
conversation history. It is a discovery hint, not a version check.

```bash
memory-book setup --client claude-code --client codex
memory-book setup --all --dry-run
```

Restart the host or refresh its MCP servers. Connection approval, project trust,
tool allowlists, and model tool support remain controlled by the host. The server
is named `memory-book`.

## Supported profiles

Paths below are defaults for the current user; `~` means the user's home on each
platform. A profile supports configuration generation and merging, not an
interactive end-to-end guarantee for every application version.

| Profile | Default MCP configuration | Schema | Native background capture |
|---|---|---|---|
| [`claude-code`](https://code.claude.com/docs/en/mcp) | `~/.claude.json` | JSON `mcpServers`, stdio | Claude Code JSONL |
| [`claude-desktop`](https://modelcontextprotocol.io/docs/develop/connect-local-servers) | Platform paths below | JSON `mcpServers` | No adapter |
| [`codex`](https://developers.openai.com/codex/mcp/) | `~/.codex/config.toml` | TOML `mcp_servers` | Local rollout JSONL |
| [`gemini`](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md) | `~/.gemini/settings.json` | JSON `mcpServers` | Current JSONL and legacy JSON |
| [`kimi`](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp) | `~/.kimi-code/mcp.json` | JSON `mcpServers` | No verified current-format adapter |
| [`kimi-legacy`](https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/customization/mcp.md) | `~/.kimi/mcp.json` | JSON `mcpServers` | Legacy Python `context.jsonl` |
| [`cursor`](https://cursor.com/docs/mcp) | `~/.cursor/mcp.json` | JSON `mcpServers`, stdio | No adapter |
| [`opencode`](https://opencode.ai/docs/mcp-servers/) | `~/.config/opencode/opencode.json` or existing `.jsonc` | **v2** JSON `mcp.servers`, local command array | No adapter |
| [`copilot-cli`](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) | `~/.copilot/mcp-config.json` | JSON `mcpServers`, `type: local` | No adapter |
| [`qwen-code`](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/) | `~/.qwen/settings.json` | JSON `mcpServers` | No adapter |
| [`lm-studio`](https://lmstudio.ai/docs/app/mcp) | `~/.lmstudio/mcp.json` | JSON `mcpServers` | No adapter |
| `generic-json` | No file is edited | Export a `mcpServers` snippet | Canonical import only |

Claude Desktop paths are:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`.
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`.
- Linux: `~/.config/Claude/claude_desktop_config.json`.

The corresponding profiles honor `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
`KIMI_CODE_HOME`, `COPILOT_HOME`, and OpenCode's `XDG_CONFIG_HOME`. When
`CLAUDE_CONFIG_DIR` is set, its `.claude.json` is selected. Use `--client-config`
for a different location or an explicitly selected project config:

```bash
memory-book setup --client claude-code --client-config /absolute/project/.mcp.json
memory-book setup --client cursor --client-config /absolute/project/.cursor/mcp.json
```

`--client-config` requires one client and differs from `--config`, which selects
AI-Memory-Book's background configuration. OpenCode v1's direct `mcp` server map
is not converted automatically. If both OpenCode config filenames exist, select
one explicitly. Copilot CLI's profile is separate from VS Code's configuration.

### Kimi version boundary

Current Kimi Code uses `~/.kimi-code`, while the legacy Python CLI uses `~/.kimi`.
Choose `kimi` or `kimi-legacy` accordingly; a shared `kimi` executable does not
prove that the legacy edition is installed. The current CLI's documented
`session_index.jsonl` contains metadata and is **not** treated as a conversation.
Current Kimi has MCP configuration support here; native capture is limited to
the separately named legacy format. See the official
[current data locations](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/data-locations.html)
and [legacy context implementation](https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/soul/context.py).

### DeepSeek and other model providers

Choose the MCP-capable host where you use the model, for example OpenCode, and
leave its provider configuration in place. AI-Memory-Book does not change model
credentials or API routing. The official [DeepSeek documentation](https://api-docs.deepseek.com/)
also links the DeepSeek Harness developer preview. Its own MCP configuration
schema has not been verified for this release, so there is no automatic
`deepseek` profile. This does not imply that DeepSeek has no official local tooling.

For another host, generate a snippet and adapt it to the host's official schema:

```bash
memory-book setup --client generic-json --dry-run
```

An `mcpServers` snippet is not interchangeable with TOML, VS Code's `servers`
layout, or OpenCode's `mcp.servers`. Hosts without a verified profile require
manual configuration.

## Configuration changes and removal

Setup invokes the current **absolute Python executable** with
`-m memory_book --db /absolute/path/memory.db mcp`. This avoids dependence on a GUI
application's PATH or working directory. `--allow-write` adds the optional write
tool; read-only is the default.

```bash
memory-book setup --client codex --allow-write --dry-run
memory-book --db /absolute/path/memory.db setup --client codex
```

Existing unrelated settings and environment variables are preserved. Changed
existing client files receive timestamped `.bak` backups, and replacement is
atomic. An unchanged setup does not rewrite the file or create another backup.
TOML updates preserve comments through `tomlkit`; JSON formatting may be
normalized. Dry-run output shows generated fields, not existing API keys or the
complete original configuration.

The generated entry has an ownership marker. An unrelated entry already named
`memory-book` is left alone unless you pass `--replace`; its file is backed up.
A config changed after planning is rejected rather than overwritten from an
outdated plan.

**JSONC is not automatically merged.** Comments, trailing commas, duplicate keys,
and malformed JSON cause a refusal with a manual snippet. Existing settings are
left untouched. A `.jsonc` filename containing strict JSON can be merged; actual
JSONC syntax requires a manual edit. Symlinked configuration files also require
selecting their real target explicitly. Do not overwrite an entire host config
with the small snippet.

```bash
memory-book disconnect --client codex --dry-run
memory-book disconnect --client codex
```

Disconnect removes only a recognized managed MCP entry and preserves other
servers and settings. It does not remove archived memory, watched sources, or the
background service; use `watch remove` and `service uninstall` separately.

## MCP behavior

The server uses the official Python SDK v1 maintenance line, pinned to
`mcp>=1.28,<2`; protocol tests use an actual SDK client and stdio subprocess.
See the [official SDK v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/).

| Tool | Behavior |
|---|---|
| `recall_memory` | Search evidence directly, with optional project, chapter, and session filters |
| `browse_projects` | List the project bookshelf |
| `browse_book` | Page through a project's chapters |
| `browse_chapter` | Page through sections and bounded page previews |
| `browse_section` | Continue through a long section's page directory |
| `read_page` | Read an exact page with character pagination and provenance |
| `remember_session` | Only with `--allow-write`: add or atomically replace a canonical session |

Ask the host to call `recall_memory` when a question needs earlier work; browsing
the whole directory first is optional. For example:

```json
{"query":"Why did we choose a 45-second cache expiry?","project":"atlas","budget_chars":2000,"limit":5}
```

The server tells the model to treat historical text as evidence rather than
instructions. Hits retain source session IDs and zero-based `turn_index` values;
page reads expose source spans. `budget_chars` bounds the assembled evidence
context, including citation headings. It does **not** bound outer JSON metadata,
tool declarations, or exact model tokens. Recall returns one copy of the context
rather than duplicating it in text and structured content.

`remember_session` replaces the full session identified by `(project,
session_id)`; it is not an append-one-message operation. MCP exposes no deletion
tool. Starting MCP alone does not collect host histories or guarantee automatic
context injection on every question. Background file capture is separate from
the MCP write permission.

## Import formats

| `--format` | Accepted text and behavior |
|---|---|
| `canonical` | One session object, an array, or a `{ "sessions": [...] }` container |
| `chatgpt` | Export `mapping`; follows the `current_node` ancestor chain without mixing abandoned branches |
| `claude-code` | JSONL `sessionId` and known text in `message.role` / `message.content` |
| `codex` | Rollout `session_meta` and `response_item` messages; skips duplicate `event_msg` records |
| `gemini` | Legacy JSON and current JSONL, replaying supported set/patch/rewind records |
| `kimi-legacy` | Legacy Python CLI's active `context.jsonl`; recognized internal metadata is excluded |
| `auto` | Detects recognized structures; arbitrary JSON is not an empty successful import |

```bash
memory-book import ./export.json --format chatgpt --project atlas
memory-book import ./session.jsonl --format claude-code --project atlas --task cache-design
```

Adapters are tested with representative synthetic records, not every historical
vendor version. Source implementations include Gemini's
[record types](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingTypes.ts)
and [recording service](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts),
and legacy Kimi's [message types](https://github.com/MoonshotAI/kimi-cli/blob/main/packages/kosong/src/kosong/message.py).
Report unsupported formats using a small sanitized example, not a private archive.

Files must be UTF-8, with an optional BOM. CLI imports allow up to 64 MiB per
file; the core limits each session's text to 8 million characters. The reader
accepts one canonical object per upload, up to 8 MiB. Images, audio, thinking
blocks, and structured tool calls/results are not reconstructed; ordinary text
messages with the `tool` role can be retained.

An import needs a project in the input or an explicit `--project`; `--project`
and `--task` override input assignments. Projects are namespaces, not paths to
read. One-off imports without a native stable ID use a filename/content-derived
snapshot ID. The watcher supplies a stable source-path fallback so file changes
can replace the same imported session.

Each session write is atomic, and repeat imports skip unchanged content. A
multi-file import is not one overall transaction: successful earlier writes
remain if a later session fails. Repair the failing input and retry.

### Canonical session fields

| Field | Requirement and meaning |
|---|---|
| `project` | Required project ID, or supplied by the importer option |
| `session_id` | Stable ID within a project; required by the core API, with importer fallbacks as above |
| `messages` | Messages with `role` and string `content`; roles: `user`, `assistant`, `system`, `developer`, `tool` |
| `title` | Optional session display title |
| `project_name` | Optional project display name |
| `task_id` / `task_title` | Optional shared task ID and chapter title for related sessions |
| `created_at` | Optional ISO 8601 source time, normalized to UTC |

Exported source JSON preserves normalized text, not every vendor-specific field
or the original file's bytes. Code and commands in stored messages remain text.

## Check the connection

```bash
memory-book doctor
memory-book stats
memory-book recall "a phrase from an imported session" --json
```

If local recall works but the host cannot find the tool, refresh its MCP server,
check its permission prompts, and confirm the executable still exists. After
changing Python environments, [rerun setup](deployment.md#upgrading).

The [release validation record](validation.md) distinguishes schema fixtures,
real MCP protocol tests, and installers from vendor application acceptance. No
claim is made that every listed host was launched and authenticated, or that all
native login services were exercised end to end.
