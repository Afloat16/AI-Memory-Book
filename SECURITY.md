# Security and data boundaries

AI-Memory-Book is a local, single-user tool. It does not implement authentication or authorization between projects. Do not expose its HTTP reader publicly or to an untrusted network.

The reader binds only to loopback, validates Host, and requires a same-origin Origin plus a per-start token for imports. Historical content is rendered as text. The MCP service uses stdio and is read-only unless `--allow-write` is supplied. It has no deletion tool.

Transcripts and query caches are stored locally in ordinary SQLite files; this is not encrypted storage. The core makes no external requests and has no telemetry. Model hosts may send retrieved evidence to their configured model provider; that behavior belongs to the host.

Imported conversations can contain adversarial instructions. Treat them as historical evidence, never fresh instructions or commands. The software does not execute transcript text.

For suspected vulnerabilities, use GitHub's private vulnerability reporting if enabled. If unavailable, contact the repository owner through an available private channel; do not post credentials or real private transcripts in a public issue. Safe minimal reproductions are encouraged.
