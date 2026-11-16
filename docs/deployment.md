# Installation and background operation

AI-Memory-Book runs behind your AI client. The client starts its **stdio MCP
server** to retrieve relevant project evidence; an optional capture worker keeps
the same local archive up to date. Neither process requires a browser. New
background configurations are headless by default, with no HTTP listener.

AI-Memory-Book needs **Python 3.10+ with SQLite FTS5**. The release installer
creates an isolated environment with the `mcp` and `clients` extras. It does not
require Node.js, an embedding server, a database server, or a memory-service API
key. Your AI client's own model and account requirements remain separate.

<a id="install-v060"></a>

## Install v0.7.0

Download the pinned installer, run it, and connect your AI
client. The installer uses the small **v0.7.0 wheel** from the
[GitHub release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.7.0),
so you do not need Git or a source checkout. The wheel excludes the repository's
historical benchmark reports. MCP and client configuration dependencies are
included in the installation; capture and the browser reader remain optional.

### macOS / Linux

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.sh
bash install-memory-book.sh
```

### Windows PowerShell

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

The shared Python installer also works on macOS/Linux. A PowerShell wrapper is
available at [the v0.7.0 `scripts/install.ps1`](https://github.com/Afloat16/AI-Memory-Book/blob/v0.7.0/scripts/install.ps1). Neither wrapper
changes your shell profile or PowerShell execution policy. Use Python 3.10 or
newer; some Linux distributions package `venv` separately.

The installer prints the exact launcher path and any required PATH instructions.
Use that full path if `memory-book` is not yet found. By default, environments
live under the data directory's `install` subdirectory. The usual POSIX launcher
is `~/.local/bin/memory-book`; Windows uses the data directory's `bin` directory.
Custom `--prefix`, `--bin-dir`, or `MEMORY_BOOK_HOME` can change these locations.

The downloaded helper defaults to `--version v0.7.0`. It also accepts an older
release tag, a full commit SHA, or `--source /absolute/path/to/checkout-or-wheel`.
`--without-extras` installs only
the core and therefore omits MCP/client integration. Installation stages a new
environment before switching its managed launcher; previous environments and
memory data are retained. An unrelated existing launcher is not overwritten.
The v0.3.0 through v0.3.4, v0.4.0, v0.5.0, v0.6.0, and v0.7.0 routes use their pinned release wheels;
other release tags and commit SHAs keep the source-archive installation path.

Once installed:

```bash
memory-book --version
memory-book setup --client claude-code
memory-book doctor
```

The version should be `0.7.0`. Replace `claude-code` with your client profile,
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

### Recall defaults in v0.7.0

An omitted recall budget means **2,400 characters**, including citation
headings, with up to **five results**. The default remains the local lexical
`book` strategy: semantic retrieval and coverage expansion are opt in, and no
exact token cap is imposed unless requested. MCP keeps compact source
references by default; `details=true` exposes full source coordinates. Python,
CLI and HTTP responses retain their detailed source fields.

The 2,400-character setting was selected from the 1,200/2,400-character
engineering development comparison. Those results do not establish an optimal
budget for every project. Supply `budget_chars` explicitly when a task needs a
different allowance; for example, Python/MCP `budget_chars=4000` or CLI
`memory-book recall "query" --project project-id --budget 4000` uses that explicit
character allowance. Limits on the context text do not cap all
protocol metadata or model tokens. See the [release scope](releases/v0.7.0.md)
and [token budgets](token-budget.md).

### Keep a client connection inside one project

List the stored project IDs, then choose the exact book for this connection:

```bash
memory-book projects
memory-book setup --client codex --mcp-project service-alpha --dry-run
memory-book setup --client codex --mcp-project service-alpha
```

Replace `service-alpha` with an actual ID. Restart the client after setup. Its
MCP connection now inherits that project for omitted scopes and rejects
conflicting scopes and foreign chapter, section or page IDs. This setting belongs
to the configured connection; it does not follow the terminal's working directory.
Use separate client configurations or explicit connections for different books.

Ordinary setup preserves an existing managed binding. Select a different ID with
`--mcp-project OTHER_ID`, or explicitly return to archive-wide access with
`--clear-mcp-project`. An unbound connection keeps its existing behavior.
`setup --project` still controls capture mapping and requires `--capture`; it is
not an alias for `--mcp-project`. When writes are enabled, `remember_session`
still requires a matching explicit `payload.project`.
See [bound-project operation](agent-guide.md#bound-project-connections) for the
read path and its limits. These scope assertions are not user authentication.

## Alternative installation methods

### uv or pipx

Use a persistent tool environment and the same pinned release wheel:

```bash
uv tool install "ai-memory-book[mcp,clients] @ https://github.com/Afloat16/AI-Memory-Book/releases/download/v0.7.0/ai_memory_book-0.7.0-py3-none-any.whl"
```

Or:

```bash
pipx install "ai-memory-book[mcp,clients] @ https://github.com/Afloat16/AI-Memory-Book/releases/download/v0.7.0/ai_memory_book-0.7.0-py3-none-any.whl"
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
git clone --branch v0.7.0 https://github.com/Afloat16/AI-Memory-Book.git
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

<a id="current-main-and-schema-4"></a>

## Schema 4 upgrade

**v0.7.0 includes schema 4**, identifier-aware lexical retrieval, temporal recall
controls, verified database backup, and read-only archive checks. The release
installer and a checkout of the release tag provide the same runtime features;
a development checkout is no longer required for these capabilities.
This migration procedure applies to earlier schemas. An archive already on
schema 4 needs no new schema migration for v0.7.0.

Before moving an existing archive to schema 4:

1. Stop background capture and close all old MCP servers and other writers.
   Install or prepare the v0.7.0 environment without opening the archive
   through ordinary commands.
2. Use the **v0.7.0** launcher to run `backup --output NEW_PATH` against
   the existing database. This maintenance path reads the old schema without
   migrating it. `check-database` reports `migration_required` while preserving
   the snapshot and source. Keep that pre-migration snapshot.
3. Open the working archive with a normal v0.7.0 command, such as
   `memory-book stats`. The schema-3-to-4 migration transactionally rebuilds the
   derived exact and stem FTS indexes. Original normalized source text, page IDs
   and source content hashes remain intact. The source-hashing `INDEX_VERSION`
   stays unchanged so an unchanged transcript is not resegmented on its next
   import. The database revision advances and old recall caches are invalidated.
   Existing optional semantic indexes become stale under their normal revision
   check and must be explicitly rebuilt; default lexical recall is ready after
   migration without an embedding model.
4. Update **every writer's** environment and client/service configuration to the
   v0.7.0 launcher, preserving the database, background configuration
   and intended capture/write settings. Reinstall the user service with the new
   launcher where needed, then restart all clients and capture workers.

Do not mix writer generations after migration. An older connection that was
already open cannot produce the new identifier index: its next revision update
is explicitly rejected, and the complete write transaction rolls back. An older
binary without schema-4 support cannot reopen a schema-4 archive. For rollback, use the preserved
pre-migration snapshot with its matching runtime at a separate working path;
there is no automatic downgrade of the migrated file.

## Back up and check the archive

These commands are included in [v0.7.0](#install-v070).

Create a verified database snapshot with:

```bash
memory-book backup --output ./backups/memory-snapshot.db
memory-book --db ./backups/memory-snapshot.db check-database
```

Both commands select the same configured database as ordinary CLI commands;
an explicit `--db PATH` before the subcommand or `MEMORY_BOOK_DB` overrides it.
An explicit database also lets maintenance run when the background configuration
cannot be read. The source must already exist: a mistyped path does not create
an empty archive.

`backup` uses SQLite's online backup API, including committed data still in the
source's WAL. Existing MCP connections and capture can keep running. It copies
into a private temporary location, checks the completed snapshot, and publishes
one standalone SQLite file. Source sessions, page IDs, source spans, indexes,
database revision and schema are preserved. This is a database snapshot, whereas
`export` produces normalized source JSON for re-import and can rebuild different
pages and indexes.

**Choose a new output path for each snapshot.** Backup never overwrites an
existing file or directory, including symbolic links, and refuses the source
database and its `-wal`, `-shm` and `-journal` paths. Existing journal files beside
the proposed output also cause a refusal. Source WAL files are supported and
remain in place; they are read through SQLite rather than copied individually.
Source symbolic links are resolved. A source with hard-link aliases is refused
because different pathnames can associate the same database with different WAL
files; resolve those aliases and use the original archive path. POSIX output
filesystems must support hard links for atomic publication without overwriting;
Windows uses a non-overwriting rename. Unsupported publication fails safely.

`check-database` opens the archive read-only. It verifies the application/schema
identity and expected tables, runs SQLite's `integrity_check` and
`foreign_key_check`, and returns JSON with revision, record counts and check
results. It recognizes supported older schemas without migrating them.
`ok` reports the structural, integrity and foreign-key checks. The separate
`runtime_state` describes compatibility and repairable index metadata:

| Runtime state | Meaning |
|---|---|
| `ready` | The current schema has the expected lexical-index version, matching lexical/stem revision markers and both revision guards |
| `migration_required` | A supported older schema was preserved; ordinary use with the current runtime requires migration |
| `repair_required` | The current schema has missing or inconsistent lexical/stem markers or a missing revision guard; warnings identify the condition |

A structurally valid archive can have `ok: true` and still require migration or
runtime repair. Such a condition does not block making a faithful backup before
any repair. Maintenance never repairs the source, and these metadata checks do
not certify the factual correctness of stored text or the semantic consistency
of every retrieval-index entry. `doctor` remains the separate runtime,
configuration and client diagnostic.

Both maintenance commands default to a **30-second SQLite processing deadline**;
increase it for a large archive when necessary:

```bash
memory-book check-database --timeout 120
memory-book backup --output ./backups/large-snapshot.db --timeout 120
```

The deadline covers backup progress and SQL verification, including cancellation
of long-running checks; filesystem operations still depend on the operating
system. Exit status is `0` for success, `1` for a completed check that finds
integrity/foreign-key failures, `2` for an invalid source or other operation
error, and `130` for keyboard interruption. Runtime warnings alone retain exit
status `0`; automation that requires a ready current archive must also check
`runtime_state == "ready"`. Failed or interrupted backups do not publish an
incomplete snapshot. JSON counts and revision come from the verified copy,
rather than combining values observed at different times on a live source.

Snapshots contain the same unencrypted conversation text and cached evidence as
the database. They do not include capture configuration, sync state/logs, client
configuration, original transcript files or optional model files. Keep those
separately when moving a complete installation.

### Verify recovery at a new path

Preserve the snapshot and first create a separate working copy:

```bash
memory-book --db ./backups/memory-snapshot.db backup --output ./recovery/memory.db
memory-book --db ./recovery/memory.db check-database
memory-book --db ./recovery/memory.db stats
memory-book --db ./recovery/memory.db recall "a known engineering decision" --project your-project-id
```

Use a real project ID and a decision whose original evidence you can verify.
Opening the recovered working copy with normal commands may migrate an older
schema; the preserved snapshot is unchanged. There is no in-place restore or
overwrite option.

After verification, stop background capture and close existing client MCP
connections, then use `setup` with the new absolute database path and the clients
you use. Preserve your existing background config and source settings, and
restart the clients and capture service when ready. The existing
[database selection controls](#data-and-configuration-paths) apply.

Reconnecting capture can import current transcript contents into the recovered
archive. A changed database path, generation or older revision invalidates the
worker's skip state; a snapshot is not a permanent freeze of the watched files.
Verify the recovered evidence before resuming capture if you need to inspect a
particular point in history.

## Upgrading

v0.7.0 keeps schema 4, existing source IDs and the v0.6.0 recall/cache behavior.
An archive already on schema 4 needs no new schema migration for this release.

To upgrade to **v0.7.0**, first follow the [schema 4 procedure](#schema-4-upgrade)
when your working archive uses an earlier schema. For that migration, stop older
writers, install the new runtime without opening the archive, and create a
verified snapshot with the new launcher's existing `backup` command before
normal commands migrate the working database.

Download and run the v0.7.0 installer shown above, using the same `--prefix`,
`--bin-dir`, or `MEMORY_BOOK_HOME` overrides if you originally selected them.
Download the new helper rather than reusing one that defaults to another release.
For uv, pipx, or a source checkout, use the corresponding pinned v0.7.0 URL or tag.
Update every client and background worker to the new launcher, then restart them.

The default remains **2,400 characters and five results**. `temporal=auto` infers
whether current-evidence ordering is appropriate; `current` explicitly requests
it, and `relevance` keeps relevance ordering. Neither mode computes historical
state as of an arbitrary date or decides which source is authoritative. The existing
recall-cache identity separates these modes. v0.7.0 does not change recall ranking
or its cache version relative to v0.6.0.
Character and optional token budgets continue to apply together.

A CLI import validates every parsed session before opening or migrating the
archive. Predictable input errors leave the archive untouched; storage failures
still have per-session transaction boundaries, so retry the full input after
repair. Omitted project/task metadata and creation time keep their existing
inheritance behavior.

`export-book` reads one SQLite snapshot and stages the complete Markdown book
and normalized source JSON before publication. A failed export removes its own
staging files, allowing a retry to the same absent or empty target; existing
nonempty targets and the current working directory itself are rejected; choose
a new child directory for a handoff. See the [v0.7.0 release notes](releases/v0.7.0.md)
for validation evidence and the exact scope of the changes.

Each MemoryBook connection uses a **4096 KiB SQLite pager cache target**.
The cache is filled on demand. This connection-local target applies to cached
database pages; it is not a memory limit for the entire process. See SQLite's
[cache_size documentation](https://www.sqlite.org/pragma.html#pragma_cache_size)
for its allocation and session lifetime.

Exact token budgets add a separate, lazy **per-`MemoryBook` exact-count memo**.
It is allocated only on the token-budget path; character-only operation neither
allocates this memo nor loads tiktoken. `cl100k_base` and `o200k_base` share its
**2,048-entry / 2 MiB retained-text limit**. The text charge is the native Python
`str` object's size measured after successful encoding, not just its UTF-8 byte
length. Container, key/value and encoder-reference overhead is additional, and
the tokenizer vocabulary has its own memory cost. Neither this text limit nor
the SQLite pager target is a whole-process memory ceiling.

The memo retains complete unchanged citation-and-evidence strings only when
their encoder implementation and object identities are certified. Custom or
unknown implementations use the original exact-count path; oversized texts
are counted without storage, and encoding failures are not cached. Each new
book starts empty. `MemoryBook.close()` releases its retained text and identity
references, including exceptional cleanup; a process allocator or tiktoken may
retain separate memory afterward. Counts are not persisted to the database or
shared between MCP processes. See [exact-count behavior](token-budget.md#exact-count-reuse-in-v033).

The Python `cache_size` constructor argument and recall's `use_cache` option
still control the retrieval-result cache. Setting `cache_size=0` or
`use_cache=False` does not disable the exact-count memo or the SQLite pager.
Retrieval with those settings still reads original source text and performs
source validation; memo hits reuse only exact token counts. The derived
metadata index described above remains a separate on-disk and write-maintenance
cost, with no change to original stored evidence.

Token-budget recall can also batch original-turn reads from multiple sessions
inside its existing read snapshot and reuse parsed references within that call.
This adds no persistent source/reference cache or new deployment setting.
Batching requires the standard SQLite connection and supported, sufficient
connection limits; Python 3.10, restrictive limits, custom implementations and
requests beyond the 400-pair / 800-parameter bound keep the original read path.
Source validation remains complete. Single-span reference reuse is consumed
once per page, preserving independent nested values when a page is returned
more than once. See the [source-read and reference compatibility boundaries](token-budget.md#source-reads-and-references-in-v033).

When upgrading from a version before v0.3.0, back up the archive before opening
it with the new binary: the source-preserving schema 3 migration introduced in v0.3.0 has no
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

Confirm that the new launcher prints `0.7.0`. If you already use background
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
