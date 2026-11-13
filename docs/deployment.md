# Installation and background operation

AI-Memory-Book runs behind your AI client. The client starts its **stdio MCP
server** to retrieve relevant project evidence; an optional capture worker keeps
the same local archive up to date. Neither process requires a browser. New
background configurations are headless by default, with no HTTP listener.

AI-Memory-Book needs **Python 3.10+ with SQLite FTS5**. The release installer
creates an isolated environment with the `mcp` and `clients` extras. It does not
require Node.js, an embedding server, a database server, or a memory-service API
key. Your AI client's own model and account requirements remain separate.

## Install v0.3.2

**Release preparation: v0.3.2 is not published yet.** Formal performance has
passed; the new comparison and final release/install verification are pending. The
v0.3.2 URLs below are target installation URLs and become usable after publication.
The [published v0.3.1 guide](https://github.com/Afloat16/AI-Memory-Book/blob/v0.3.1/docs/deployment.md)
remains available for the current release.

After publication, download the pinned installer, run it, and connect your AI
client. The installer uses the small **v0.3.2 wheel** from the
[GitHub release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.2),
so you do not need Git or a source checkout. The wheel excludes the repository's
historical benchmark reports. MCP and client configuration dependencies are
included in the installation; capture and the browser reader remain optional.

### macOS / Linux

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.3.2/scripts/install.sh
bash install-memory-book.sh
```

### Windows PowerShell

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.3.2/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

The shared Python installer also works on macOS/Linux. A PowerShell wrapper is
available at [the v0.3.2 `scripts/install.ps1`](https://github.com/Afloat16/AI-Memory-Book/blob/v0.3.2/scripts/install.ps1). Neither wrapper
changes your shell profile or PowerShell execution policy. Use Python 3.10 or
newer; some Linux distributions package `venv` separately.

The installer prints the exact launcher path and any required PATH instructions.
Use that full path if `memory-book` is not yet found. By default, environments
live under the data directory's `install` subdirectory. The usual POSIX launcher
is `~/.local/bin/memory-book`; Windows uses the data directory's `bin` directory.
Custom `--prefix`, `--bin-dir`, or `MEMORY_BOOK_HOME` can change these locations.

The downloaded helper defaults to `--version v0.3.2`. It also accepts an older
release tag, a full commit SHA, or `--source /absolute/path/to/checkout-or-wheel`.
`--without-extras` installs only
the core and therefore omits MCP/client integration. Installation stages a new
environment before switching its managed launcher; previous environments and
memory data are retained. An unrelated existing launcher is not overwritten.
The v0.3.0, v0.3.1 and v0.3.2 routes use their pinned release wheels; other release tags
and commit SHAs keep the source-archive installation path.

Once installed:

```bash
memory-book --version
memory-book setup --client claude-code
memory-book doctor
```

The version should be `0.3.2`. Replace `claude-code` with your client profile,
such as `codex`; add `--dry-run` to setup if you want to preview configuration
changes. Restart the selected client so it loads the new MCP connection. The
server sends concise operating instructions at initialization; it does not preload your
memory directory or conversation history. The agent can call `recall_memory`
directly for a relevant past decision and read exact pages only when more
evidence is needed. Host approvals and the model's tool choices still apply.

See the [AI agent operating guide](agent-guide.md) for the retrieval policy and
[client compatibility](integrations.md) for all 12 profiles, custom config
paths, backups, and manual handling of JSONC. Installing the package does not
itself enable transcript capture.

Already installed? Follow [Upgrading](#upgrading) to keep your existing database
and reconnect clients to the new environment.

## Alternative installation methods

### uv or pipx

Use a persistent tool environment and the same pinned release wheel:

```bash
uv tool install "ai-memory-book[mcp,clients] @ https://github.com/Afloat16/AI-Memory-Book/releases/download/v0.3.2/ai_memory_book-0.3.2-py3-none-any.whl"
```

Or:

```bash
pipx install "ai-memory-book[mcp,clients] @ https://github.com/Afloat16/AI-Memory-Book/releases/download/v0.3.2/ai_memory_book-0.3.2-py3-none-any.whl"
```

These wheel URLs do not require Git. The persistent tool workflows are described
in the official
[uv tool guide](https://docs.astral.sh/uv/guides/tools/) and
[pipx installation guide](https://pipx.pypa.io/stable/how-to/install-pipx.html).
Use an installed environment for permanent MCP/service configuration: disposable
`uvx` or `pipx run` environments can disappear while a client still references
their absolute Python path.

The project is distributed from GitHub and is not published to PyPI. An
unqualified `pip install ai-memory-book` is not the documented route. Optional
dependencies are still installed through the package manager's configured
indexes; this is not an offline installation promise.

### Source checkout

```bash
git clone --branch v0.3.2 https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients]"
memory-book doctor
```

On Windows, use `.venv\Scripts\Activate.ps1` or invoke
`.venv\Scripts\python.exe` directly. The dependency-free core can be installed
with `python -m pip install -e .`; TOML merging needs the `clients` extra and MCP
needs the `mcp` extra.

For a managed launcher from an existing local checkout, run its helper with an
explicit source:

```bash
python scripts/install.py --source .
```

After changing the installed environment, re-run `setup` and reinstall any
configured background service so their absolute Python paths point to that
environment.

## Data and configuration paths

| Platform | Default data directory |
|---|---|
| Linux | `$XDG_DATA_HOME/ai-memory-book`, otherwise `~/.local/share/ai-memory-book` |
| macOS | `~/Library/Application Support/AI-Memory-Book` |
| Windows | `%LOCALAPPDATA%\AI-Memory-Book` |

The directory normally contains `memory.db`, background `config.json`,
`sync-state.json`, and `sync.log.jsonl`. All configured clients receive the same
absolute database path, independent of their working directory.

| Override | Purpose |
|---|---|
| `MEMORY_BOOK_HOME` | Change the shared data directory |
| `MEMORY_BOOK_DB` | Select a database |
| `MEMORY_BOOK_CONFIG` | Select a background configuration file |
| `--db PATH` before a subcommand | Select that command's database |
| `--config PATH` on setup/watch/sync/daemon/service/doctor | Select background configuration |

An existing background config records its database. `doctor` reports the active
paths. To change the database used by client connections and persistent capture,
run setup with the explicit path and the same background config:

```bash
memory-book --db /absolute/data/memory.db setup --client codex --capture
```

Changing a shell environment variable does not rewrite already generated client
or service definitions. Do not place a client config, the background config, the
database, or state/log files at the same path; setup rejects such collisions.

## Background capture

Capture is **opt in**. `--capture` authorizes importing existing and future
supported text transcripts from the displayed source paths. Without it, setup
only connects MCP. Preview the scope before enabling a background service:

```bash
memory-book setup --client claude-code --capture --background --dry-run
memory-book setup --client claude-code --capture --background
```

| Profile | Default source root | Recognized files and scope |
|---|---|---|
| `claude-code` | `~/.claude/projects` | `*.jsonl`; recorded workspace metadata |
| `codex` | `~/.codex/sessions` | `rollout-*.jsonl`; recorded workspace metadata |
| `gemini` | `~/.gemini/tmp` | `session-*.jsonl` and legacy `session-*.json`; project directory buckets |
| `kimi-legacy` | `~/.kimi/sessions` | Active `context.jsonl`; working-directory buckets |

Claude and Codex roots honor `CLAUDE_CONFIG_DIR` and `CODEX_HOME`; legacy Kimi's
capture root honors `KIMI_SHARE_DIR`. The Codex default does not include
`archived_sessions`; add that directory explicitly if wanted. These locations
follow the official [Claude sessions](https://code.claude.com/docs/en/sessions),
[Codex troubleshooting](https://learn.chatgpt.com/docs/reference/troubleshooting),
[Gemini session management](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/session-management.md),
and [legacy Kimi changelog](https://github.com/MoonshotAI/kimi-cli/blob/main/CHANGELOG.md).

For Claude Code or Codex, restrict collection by recorded workspace and choose a
readable project ID:

```bash
memory-book setup --client codex --capture \
  --workspace /absolute/path/to/project --project atlas --background
```

Gemini and legacy Kimi do not reliably supply the workspace path needed for this
filter. Choose that workspace's actual transcript directory with `--source` and
assign `--project` instead; `--workspace` is rejected for those adapters.

```bash
memory-book setup --client gemini --capture \
  --source /absolute/path/to/project-chats --project atlas --background
```

`--source` requires one selected client. Repeating setup replaces that client's
setup-managed source, so narrowing its scope does not leave the previous broader
source active. Separately added watch sources remain independent. With
`--all --capture`, detected hosts without a capture adapter receive MCP setup
only, with a note. Explicitly requesting unsupported capture fails before edits.

You can also watch an export directory without a native client adapter:

```bash
memory-book watch add /absolute/path/to/exports --id atlas-exports \
  --format canonical --project atlas
memory-book watch list
memory-book sync --once
memory-book watch remove atlas-exports
```

Removing a source stops future capture without deleting stored memory. The
worker polls changed files, retries incomplete active logs, skips symlinks and
known credential/config files, and isolates malformed files. It does not delete
memory because a source file disappears. Stable IDs allow revised transcripts
to replace their previous indexed content. Status logs record operational
metadata and error codes rather than conversation text.

The worker does not call an LLM to summarize each turn. Source text stays in the
local database; evidence returned to a model through MCP enters that client's
model context. Native vendor log formats can change; see
[import coverage and limits](integrations.md#import-formats).

## User services and foreground operation

`--background` installs and starts a current-user service. After watch sources
are configured, the same service can be managed independently:

```bash
memory-book service install --dry-run
memory-book service install
memory-book service status
memory-book service stop
memory-book service start
memory-book service uninstall
```

| Platform | Service mechanism | Scope |
|---|---|---|
| Linux | `systemd --user`, `ai-memory-book.service` | User manager; no automatic lingering setup |
| macOS | `~/Library/LaunchAgents/com.ai-memory-book.agent.plist` | Logged-in user's GUI session |
| Windows | Task Scheduler task `AI-Memory-Book` | Current interactive user at logon, limited privileges, no stored password |

These are user/login services, not privileged system services guaranteed to run
before login. Uninstall removes the managed service but keeps memory, watch
configuration, and client MCP entries. The service launches the capture daemon.
With a new configuration, it runs **headlessly**: `reader_enabled` is
`false`, and no reader port is opened. Each AI client starts its own stdio MCP
process against the shared database; it does not connect to this daemon over
HTTP.

If no usable user service manager is available, run the daemon under your own
supervisor or use one-pass sync:

```bash
# Continuous capture with configuration reloads; headless by default.
memory-book daemon --config /absolute/path/config.json

# One capture pass, with no reader.
memory-book sync --once --config /absolute/path/config.json
```

`memory-book sync` without `--once` polls continuously without starting the
reader, even if the configuration enables the optional daemon reader. A running
daemon reloads changes to its config, including removed or narrowed sources. An
invalid or deleted config stops the old capture cycle rather than continuing
with stale scope.

The v0.2.0 release candidate [CI run 42998379672](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672)
passed actual installer jobs on Linux, macOS, and Windows, plus MCP, Docker,
browser, and core checks. Installer jobs used a locally built wheel and tested
extras, reinstall, failed-install recovery, and paths containing spaces/Unicode.
Native service definitions and command flows have focused tests, and a real
daemon subprocess was tested. Actual login/logout service execution across all
three operating systems and interactive acceptance by every vendor client were
**not** tested. See [validation details](validation.md).

## Optional browser inspection

The reader helps a person inspect imported sources and the book structure. AI
retrieval uses MCP directly and does not require it. To open a separate local
reader explicitly, run:

```bash
memory-book serve
```

Open `http://127.0.0.1:8765` while that process is running. If you use a custom
database, select the same path with
`memory-book --db /absolute/data/memory.db serve`. Closing the reader process
does not stop a separately running capture worker or an AI client's MCP server.

Alternatively, let the daemon run the reader by editing the following fields
in its **existing** background configuration, preserving its database, state,
and sources. This is a fragment, not a replacement configuration:

```json
{
  "reader_enabled": true,
  "reader_host": "127.0.0.1",
  "reader_port": 8765
}
```

The daemon reloads the change. Set `reader_enabled` back to `false` to return it
to headless operation. Run one reader per port; a separate `serve` process is
unnecessary when the daemon already provides that reader.

## Upgrading

After publication, to upgrade to **v0.3.2**, download and run the v0.3.2 installer shown above,
using the same `--prefix`, `--bin-dir`, or `MEMORY_BOOK_HOME` overrides if you
originally selected them. Download the new helper rather than reusing a helper
that defaults to an older release. For uv, pipx, or a source checkout, use your
original installation method with the pinned v0.3.2 URL or tag.

v0.3.2 retains schema 3 and introduces no new schema migration. When upgrading
from a version before v0.3.0, back up the archive before opening it with the new
binary: the source-preserving schema 3 migration introduced in v0.3.0 has no
automatic downgrade, and a pre-v0.3.0 binary needs the pre-upgrade database backup
for rollback. Use SQLite's backup facility for a consistent snapshot, including
data still in the WAL.

The bundled installer retains older environments and preserves your memory
directory. Client and service definitions contain absolute Python paths, so a
new environment does not automatically move existing connections to it.

Run the **new launcher's** setup for the clients you already use, keeping the
same database/config and any explicit write preference:

```bash
memory-book --version
memory-book setup --client claude-code --client codex
memory-book doctor
```

Confirm that the new launcher prints `0.3.2`. If you already use background
capture, update its service to the new environment:

```bash
memory-book service install
```

Existing watch sources remain in the background config; repeating
`--capture` is unnecessary unless changing their scope. Preserve custom
`--client-config` or `--config` paths when rerunning setup. Restart the clients to
release old MCP processes. Do not remove an old environment while a client or
service still references it.

### Upgrading from v0.2.0

Since v0.2.1, **new** configurations and configurations without a
`reader_enabled` field default to `false`. An existing explicit `true` or `false`
remains in effect; the installer and repeated setup do not silently change that
choice. A configuration created by v0.2.0 may therefore still start the reader.
Set its `reader_enabled` to `false` if you want capture to run headlessly. This
changes only the optional reader; capture sources, the archive, and MCP remain
available.

### Upgrading from v0.1.0

v0.1 commonly used `.memory-book/memory.db` relative to a working directory.
v0.2 uses a stable per-user directory. **No database is moved automatically.**
`doctor` warns about the old path when it exists in the current directory.

To keep using the existing database, pass its absolute path:

```bash
memory-book --db /absolute/old-project/.memory-book/memory.db stats
memory-book --db /absolute/old-project/.memory-book/memory.db setup --client codex
```

To populate a new shared database, stop writers and export/import normalized
sources with explicit old and new paths:

```bash
memory-book --db /absolute/old-project/.memory-book/memory.db export --output memory-export.json
memory-book --db /absolute/new-data/memory.db import memory-export.json --format canonical
memory-book --db /absolute/new-data/memory.db setup --client codex
```

Keep the original database until project/session counts and a few known recalls
match. Import rebuilds derived pages and indexes using the current configuration;
page IDs and segmentation can differ. The export contains conversation text, so
store it with the same care as the database.

## Docker

Build the image from the pinned source checkout:

```bash
docker build -t ai-memory-book:local .
```

The image's default command is read-only **stdio MCP**, with no HTTP listener or
port mapping. It runs as UID/GID `10001`, includes MCP/client dependencies, and
defaults to `/data/memory.db`. The examples share the persistent named volume
**`ai-memory-book-data`**, mounted at `/data`.

An MCP host starts a container against that volume. This is a manual
`mcpServers` example; adapt the host schema and Docker executable path:

```json
{
  "mcpServers": {
    "memory-book": {
      "command": "/absolute/path/to/docker",
      "args": ["run", "--rm", "-i", "-v", "ai-memory-book-data:/data", "ai-memory-book:local", "mcp"]
    }
  }
}
```

Use `-i` without a pseudo-terminal (`-t`) for MCP. Native `setup` generates a
Python invocation, not this Docker command. To import a host export, mount its
directory explicitly read-only:

```bash
docker run --rm \
  -v ai-memory-book-data:/data \
  --mount type=bind,source=/absolute/path/to/exports,target=/imports,readonly \
  ai-memory-book:local import /imports/session.json --format canonical --project atlas
```

Docker has **no automatic access to host transcripts**, and the default Compose
services do not start a capture worker. Container capture requires explicit
read-only source mounts, a background config using container paths, and a
`daemon` command. Ensure bind-mount permissions allow UID `10001` to read sources
and write its database directory. The supplied named volume avoids a host-home
mount by default.

For optional browser inspection, start the Compose reader explicitly:

```bash
docker compose up -d --build reader
```

That service shares the same named volume and publishes only host loopback at
`127.0.0.1:8765`. Its explicit command overrides the image's MCP default with
`serve --host 0.0.0.0 --container-bind`; the host-facing port remains local.

`docker compose down` retains the named volume; adding `--volumes` deletes it.
The reader is a local single-user interface, not a public multi-user deployment.

## Troubleshooting

| Symptom | Next step |
|---|---|
| `memory-book` is not found | Use the full launcher path printed by the installer, then follow its PATH instructions |
| MCP cannot start after an upgrade | Rerun setup with the new launcher and restart the client |
| JSONC/config merge refused | Keep the existing file; merge the printed snippet manually using the host's documented layout |
| No new memory appears | Check `watch list`, run `sync --once`, and inspect `doctor`; MCP setup alone does not enable capture |
| Background service is unavailable | Run `daemon` under your supervisor or use `sync --once` |
| No reader opens after background setup | Expected for a new headless configuration; use MCP in your AI client, or run `memory-book serve` for optional inspection |
| Reader port is already in use | Stop the duplicate reader or change `reader_port` in the background config |
| Old project appears empty after upgrade | Select the old database explicitly or perform the v0.1 export/import above |
| Host sees no tools despite successful local recall | Refresh MCP, inspect host approvals, and check its tool-capable model/configuration |
