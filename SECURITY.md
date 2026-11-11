# Security and data boundaries

AI-Memory-Book v0.2 is a local, single-user tool. It does not implement user authentication or authorization between projects. Project namespaces organize retrieval; they are not access-control boundaries. Anyone who can access the database or its local tools may be able to read every project.

## Explicit capture and client setup

Installation does not enable transcript capture or install a login service. `setup` configures the selected client's MCP connection; `--capture` separately opts in to reading **existing and future** supported text transcripts in the displayed source paths. `--background` installs and starts a current-user service. Use `--dry-run` to inspect the configuration and scope first.

Client configuration changes preserve unrelated settings, create a backup, and compare the file again before replacement. Unsupported JSONC or unsafe merges return a manual configuration snippet. Configuration plans display only the proposed Memory Book entry, not the rest of the client's settings. Configuration backups can still contain the original client's credentials and deserve the same filesystem protection as that configuration. Setup does not disable a client's own trust or tool-permission controls.

The worker scans only explicitly configured directories and supported filename/format rules. Project mapping uses explicit assignments, recorded workspaces, or configured workspace buckets; uncertain metadata does not silently collapse every source into one project. A broad source with an explicit project assignment intentionally places its selected sessions in that project, so choose a narrow source when limiting capture scope.

Symlinks within the selected tree, database/state artifacts, known credential/configuration filenames, and unrelated formats are excluded. Files are bounded in size, and malformed files are isolated and retryable. These controls are not secret redaction: a password, access token, or confidential document pasted into a valid conversation can be imported as text.

A running daemon detects configuration changes and stops the previous worker before loading the replacement configuration. Scope changes take effect after the file currently being processed finishes. An invalid or deleted configuration stops the old capture scope. Stopping or uninstalling the service, removing a watched source, or removing a source file does not delete archived memory. Explicitly delete archived sessions/projects when that is required; a configured source can import them again on a subsequent changed or forced synchronization.

## Local data, logs, and processes

Normalized transcripts, retrieved query caches, SQLite journals, exports, and backups are ordinary local files. **They are not encrypted by this application**, and importing does not erase the source transcript. Use appropriate OS account permissions and encrypted storage for sensitive material. Deletion is not a secure-erasure guarantee for database pages, journals, exported files, backups, or the original client history.

The sync manifest stores source paths, file metadata, hashes, session identities, and progress, but no transcript text. Capture logs contain event/count metadata and bounded error codes, not message bodies or raw parser exception text. Metadata can still reveal workspace names, source identities, and activity. Config, manifest, and log paths are configurable. Do not upload them without reviewing their contents.

Manifest skip state is tied to the database path and a persistent database-generation identifier. A replacement or newly selected database triggers reimport rather than incorrectly treating existing transcripts as already archived. An operating-system lock prevents two workers from using one state file concurrently. This is a correctness control, not protection against an adversarial process running as the same OS user.

Native background services use `systemd --user`, a macOS LaunchAgent, or a limited Windows task triggered at the current user's login. They do not require a stored account password or a privileged system service. On systems without a usable user service manager, run the foreground daemon with a supervisor you control. No background service is installed merely by importing the Python package.

The indexing, capture, and retrieval core makes no external requests and has no telemetry. Installing dependencies may access package/release servers. Model hosts may send retrieved evidence to their configured provider; that behavior belongs to the host. MCP compatibility does not imply access to a client's native transcript format or automatic injection into every model request.

## HTTP, containers, and MCP

The HTTP reader binds to loopback by default, validates the `Host` header, and requires a same-origin `Origin` plus a per-start token for imports. Historical content is rendered as text. These measures reduce browser-origin attacks; they do not authenticate local users. Do not expose the reader publicly or to an untrusted network.

Containers may explicitly opt in to an internal `0.0.0.0` bind using `--container-bind`. The supplied Compose configuration publishes the port on **host loopback only**, `127.0.0.1:8765:8765`, while retaining local Host/Origin checks. An unrestricted port publication, a public reverse proxy, or additional peers on the container network changes the exposure boundary. The flag adds no authentication, project authorization, or TLS and is not a public or multi-user hosting mode. Docker also requires explicit mounts and capture configuration before it can read host transcripts; use narrowly scoped, read-only source mounts.

The MCP server communicates over stdio and is read-only unless `--allow-write` is supplied. It has no deletion tool. A host allowed to call its tools can read the database available to that process; enabling write access also allows supported imports and task-link operations. Retain the host's normal tool-approval policies when selecting access.

## Untrusted historical content

Imported conversations can contain adversarial instructions. Treat them as historical evidence, never fresh instructions or commands. The software does not execute transcript text. A consuming model or automation must preserve that distinction; correct source citations do not make instructions inside a source trustworthy.

Native client formats can change independently. Unsupported records are not evidence of full-fidelity capture. In particular, current Kimi Code MCP configuration is separate from the verified legacy Python Kimi `context.jsonl` importer; a session index is not a conversation archive.

## Reporting a vulnerability

For suspected vulnerabilities, use GitHub's private vulnerability reporting if enabled. If unavailable, contact the repository owner through an available private channel; do not post credentials or real private transcripts in a public issue. Safe minimal reproductions are encouraged.
