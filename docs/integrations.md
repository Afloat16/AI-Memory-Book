# Agent MCP integrations and import formats

AI-Memory-Book is a memory service for **AI agents**. Its primary interface is
local **stdio MCP**: an agent requests a small amount of relevant earlier context
and receives original evidence with source references. The book hierarchy helps
address that evidence without making the agent read an entire directory or
conversation before each question.

The intended runtime workflow is:

1. Use the current conversation when it already contains the needed information.
2. When earlier work matters, call `recall_memory` once with a focused query and
   the known project ID.
3. Use the returned evidence and source IDs. Read a particular page or navigate a
   section only if the answer still needs more evidence.

See the [agent operating guide](agent-guide.md) for exact tool arguments, source
semantics, and write rules. It is guidance for the connected agent; setup does
not edit global `AGENTS.md` files or install automatic prompt-injection hooks.
The host and model decide when to call tools, so MCP connection alone cannot
guarantee that recall runs automatically.

Memory ingestion is separate: [background capture](deployment.md#background-capture)
imports supported files only after opt-in, while explicit imports and the
optional `remember_session` tool provide other write paths. The browser reader
is an optional inspection utility, started with `memory-book serve`; agents do
not need it for capture, retrieval, or MCP communication.

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

Restart the host or refresh its MCP servers. The host starts the `memory-book`
stdio subprocess when connecting; no HTTP endpoint or browser process is needed.
Connection approval, project trust, tool allowlists, and model tool support
remain controlled by the host.

The foreground MCP command used by a manually configured host is:

```bash
/absolute/path/to/python -m memory_book --db /absolute/path/memory.db mcp
```

This command waits for MCP messages on standard input; it is not a chat prompt.
Ordinary use lets the client manage the process. After connection, a useful
check is to ask the agent to recall a known earlier decision and cite the
returned session and turn.

## Bind a client to one project

For similar engineering projects, v0.7.0 can fix the scope of a configured MCP
connection. Discover the actual project ID, inspect the planned configuration,
then apply it:

```bash
memory-book projects
memory-book setup --client claude-code --mcp-project inference-demo --dry-run
memory-book setup --client claude-code --mcp-project inference-demo
```

Replace the example ID with one in your archive. Setup adds
`--project=inference-demo` to the generated `mcp` launch arguments and reports
the selected `mcp_project` in its client plan. Restart or reconnect the host to
use the changed launch command. The binding applies to that server entry in
that client configuration; it does **not** follow the host's current working
directory or infer a repository from a task title.

The default configuration paths in the next section are user-wide. When the
host supports a project configuration, select it explicitly for a project-local
entry, for example:

```bash
memory-book setup --client claude-code --client-config /absolute/inference-project/.mcp.json --mcp-project inference-demo
```

Another project can use its own supported configuration and another explicit
ID while sharing the archive. Host precedence and trust rules still determine
which entry it starts. A manually configured host can launch:

```bash
/absolute/path/to/python -m memory_book --db /absolute/path/memory.db mcp --project inference-demo
```

On that connection, `recall_memory`, `browse_chapter`, `browse_section` and
`read_page` inherit the binding when their optional `project` is absent or
`null`. A different explicit project is rejected, and a foreign chapter,
section or page ID cannot bypass the bound scope. `browse_projects` exposes
only the selected project when it exists. `browse_book` also inherits the
binding when `project` is omitted or `null`; on an unbound connection it still
requires an explicit project. If writes are enabled, `remember_session` still
requires an explicit matching `payload.project`.

Refreshing a **recognized managed entry** without `--mcp-project` preserves
its existing binding. To deliberately return it to the unbound mode:

```bash
memory-book setup --client claude-code --clear-mcp-project
```

Include the original `--client-config` when using a custom path.
`--clear-mcp-project` and `--mcp-project` are mutually exclusive. A new entry
without a binding retains the existing cross-project discovery/search behavior;
unbound callers can still supply `project` on each follow-up read.

### Capture mapping and MCP binding are separate

| Setup option | Controls | Requires `--capture`? |
|---|---|---|
| `--project` | The project destination for the selected capture source | Yes |
| `--workspace` | Which recorded workspace the capture source accepts, when supported by its adapter | Yes |
| `--mcp-project` | The project visible through the configured MCP connection | No |
| `--clear-mcp-project` | Explicit removal of an existing managed MCP binding | No |

Binding does not rename stored projects, move sessions, start capture, or
automatically change a capture source's destination. Capture can continue to
populate a shared archive while one connection reads a single project.
`--allow-write` controls whether the MCP write tool exists; it is separate
from both capture and project binding. These scope checks prevent accidental
project mixing; they are not authentication or a per-user ACL for database
contents. The [agent guide](agent-guide.md#bound-project-connections) gives the
per-tool contract and the book → chapter → section → page workflow.

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
tool; read-only is the default. With `--mcp-project`, the generated command also
contains the exact `--project=...` binding described above.

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
| `browse_chapter` | Page through sections and bounded page previews; optional exact `project` assertion |
| `browse_section` | Continue through a long section's page directory; optional exact `project` assertion |
| `read_page` | Read an exact page with character pagination, provenance and an optional `project` assertion |
| `remember_session` | Only with `--allow-write`: add or atomically replace a canonical session |

For a question that needs earlier work, start with one `recall_memory` call.
Pass the known project ID; `chapter` and `session` can narrow an already known
scope. No initial `browse_*` sequence is required. For example:

```json
{"query":"Why did we choose a 45-second cache expiry?","project":"atlas","budget_chars":2400,"limit":5}
```

If the response is sufficient, answer from it without loading more history.
Use `read_page` with a returned page ID only for a missing detail, truncated
passage, or source check. Use the browse tools when navigation itself is needed,
such as identifying an unknown project or locating a neighboring section. An
empty result is not proof that an earlier conversation never happened; the
lexical index can miss differently worded evidence. The
[agent guide](agent-guide.md#when-evidence-is-insufficient) describes targeted
follow-up rather than repeated broad reads.

The server tells the model to treat historical text as untrusted evidence rather
than instructions. Hits retain project/session IDs and zero-based `turn_index`
values; page reads expose source spans. `budget_chars` defaults to 2,400 and
bounds the assembled evidence context, including citation headings. It does
**not** bound outer JSON metadata, tool declarations, or exact model tokens.
Recall returns one copy of the context rather than duplicating it in text and
structured content. All MCP tools return one compact JSON text
block. Default recall references contain `project`, `session_id`, and
`turn_index`; pass `"details": true` for exact offsets, message indices,
excerpt ranges, and retrieval diagnostics. `read_page` retains full provenance.
`browse_projects` returns a JSON array within its single text block. Consumers
that depended on v0.2.x's detailed recall fields should request `details`.
Check conflicting source dates and statements instead of
assuming the top result is the current authoritative decision.

`recall_memory` also accepts `"temporal": "auto"` (the default), `"current"`, or
`"relevance"`. Use `current` when the caller explicitly needs the latest matching
evidence and `relevance` to disable current-evidence ordering. Automatic inference
keeps real historical/as-of questions conservative while recognizing provenance
phrases and dataset-year labels. The modes are ordering controls, not an as-of
state resolver; full diagnostics are available with `details=true`.

`remember_session` replaces the full session identified by `(project,
session_id)`; it is not an append-one-message operation. MCP exposes no deletion
tool. Writes require an explicitly enabled write workflow: `--allow-write` for
agent calls, `--capture`/watch configuration for native file ingestion, or an
explicit import. Starting MCP alone does not collect host histories or guarantee
automatic context injection on every question. Background file capture is
separate from the MCP write permission and does not require a read-write MCP
connection.

The Python, CLI and HTTP interfaces also accept explicit project assertions on
exact follow-up reads. Python uses `book.chapter(id, project=...)`,
`book.section(id, project=...)` and `book.read(id, project=...)`; CLI uses
`chapter`, `section` and `read` with `--project`. The HTTP `/api/chapter`,
`/api/section` and `/api/read` endpoints accept a `project` query parameter.
Use an actual resource ID and URL-encode the project value when constructing an
HTTP request. An unrelated resource ID returns not found in that project.
The optional HTTP reader remains an archive-wide inspection server; this release
does not add a `serve --project` binding. Its UI sends the selected project's ID
on follow-up requests. See [a scoped directory example](engineering-workflows.md#navigate-one-project-book).

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
CLI import parses and validates every session before opening or migrating the
archive. Invalid dates, excessive field lengths and unsupported message content
therefore fail before any session is replaced. Errors from this validation name
the file and session position. A multi-file import still has per-session storage
transactions: an I/O failure can leave earlier successful writes committed.
Repair the storage problem and retry; omitted metadata keeps its inheritance
behavior.

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
