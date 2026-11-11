# Release validation

This document separates measured behavior from configuration compatibility. All
fixtures, examples, screenshots, and capture measurements are synthetic. No
private user conversation history was used in development or published.

## v0.2.1: agent workflow and headless default

The updated local suite passed **159 tests** with MCP and client extras. A new
official-SDK stdio test performs the agent workflow end to end:
`remember_session` → `recall_memory` with a bounded project query → `read_page`
using the returned page ID. It verifies the write-enabled initialization policy,
the remembered fact, character budget, and source identity without a browser.
The read-only handshake verifies its distinct instructions and tool visibility.

The real-daemon regression now leaves `reader_enabled` at its default while
another socket occupies the configured reader port. Capture, configuration
reload, explicit database selection, and clean termination still succeed. This
checks that new background configurations do not require an HTTP listener.
Existing saved reader preferences remain explicit configuration values.

These checks establish the MCP protocol path and headless behavior. They do not
establish that every host model chooses the right tool without prompting; host
approval policies and model tool selection still apply. The
[agent operating guide](agent-guide.md) documents the actual contract.

## v0.2.0: verified implementation

The release candidate at `1d6a881faeb811504941d9bbb0682f587d5de344` passed
**all nine GitHub Actions jobs**:
[complete CI run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672).
The full suite with the MCP and client extras installed ran **158 tests with no
failures or skips**, both locally and in the separate MCP CI job. The dependency-free
core also passed on Python **3.10, 3.12, and 3.13**, skipping optional-dependency
cases when their extras were absent.

| Area | What actually ran |
|---|---|
| Core and source integrity | Transactional import/replacement, exact provenance, scoped retrieval, character budgets, cache invalidation, export round trips, safe paths, and HTTP protections |
| Client configuration | Schema fixtures, preservation of unrelated settings and credentials, backups, ownership, repeat setup/removal, stale-plan rejection, malformed JSON/JSONC fallback, TOML preservation, and path collisions |
| Background capture | Incremental identity and hashing, database replacement/generation, moved/removed sources, partial JSONL/UTF-8, retry deadlines, repaired files, workspace isolation, cross-process locks, metadata-only logs, and worker shutdown |
| Actual daemon process | A subprocess imported a fixture, honored an explicit database, reloaded a removed source, stopped importing its files, and exited cleanly on SIGTERM |
| MCP protocol | The official SDK client initialized a real stdio subprocess, listed tools, recalled evidence, and checked explicit write enablement |
| Linux/macOS/Windows installers | Each OS ran its shell/PowerShell wrapper, installed a local wheel into paths with spaces and Unicode, exercised reinstall and failed-install recovery, preserved existing data, refused an unrelated launcher, and installed the normal MCP/client extras |
| Docker | Built the image, ran as the non-root user, initialized MCP over container stdio, read persisted evidence, served the reader through host loopback, checked Host validation, and retained data after a container restart |
| Browser | Chrome operated the actual reader, exercised English/Chinese UI and imports, and checked desktop/mobile layouts and source-text preservation |

The installer jobs use a wheel built from the candidate source; they test the
installation mechanism and its dependencies. The project is distributed through
GitHub source releases and is not published to PyPI.

```bash
python -m pip install -e ".[mcp,clients]"
python -m unittest discover -s tests -v
python tests/installer_smoke.py --with-extras
```

## Browser evidence

The candidate used **Python 3.12.16 and Chrome 156.0.8078.79**. Its report records
**13 successful checks**, zero page exceptions, console errors, failed requests,
or unexpected dialogs. Desktop document width equals its 1440px viewport; the
mobile document width equals its 390px viewport. A fresh `en-US` browser context
selects English, and changing UI language preserves the exact conversation text
and titles.

The checked flow covers project selection, cross-session chapter browsing,
project-scoped Chinese search, source reading, focus restoration, canonical JSON
preview and confirmation, and inert display of script-like imported text. The
screenshots are actual browser captures, not design mockups:

- [English desktop](assets/reader-desktop-en.png)
- [Chinese desktop](assets/reader-desktop.png)
- [Mobile](assets/reader-mobile.png)
- [Machine-readable browser report](assets/reader-browser.json)

These files are preserved in the repository because CI artifacts expire after
seven days. The browser check intentionally lives outside unittest discovery,
so the dependency-free core does not require Playwright.

```bash
python -m pip install . playwright
python -m playwright install --with-deps chromium
python tests/browser_smoke.py
```

## v0.2.0 capture overhead sample

The reproducible [capture smoke measurement](../benchmarks/capture_smoke.py)
used **300 synthetic canonical files** across three projects and 30 chapters,
totaling **246,192 source bytes**. On the recorded Linux environment with
Python 3.12.14 and SQLite 3.53.1:

| Stage | Measured wall time | Actual import result |
|---|---:|---|
| Initial import into a new database | 435.83 ms | 300 files imported; 300 sessions updated |
| Eight unchanged scans | Median 36.95 ms; maximum 51.21 ms | Each skipped 300 files and imported/updated zero sessions |
| One changed file | 30.06 ms | One session updated; 299 files skipped |
| Next unchanged scan | 26.16 ms | 300 files skipped; zero sessions updated |

[Raw timings, counts, environment, and implementation fingerprint](../benchmarks/reports/capture-v0.2.0.json)
are retained. Run it from the repository with:

```bash
PYTHONPATH=src python benchmarks/capture_smoke.py
```

These are consecutive `sync_once` calls with warm filesystem caches, without
the normal polling sleep. The measurement includes state loading and locking.
Unchanged scans still update the manifest and heartbeat; zero imports do not
mean zero disk writes. This small sample does not measure resident CPU, RAM,
battery use, vendor-client latency, or performance at other scales.

## Historical v0.1.0 retrieval measurements

The [experiment record](../benchmarks/EXPERIMENTS.md) retains the initial short
corpus, development page-size sweep, all six segmentation/ranking combinations,
two untouched-seed evaluations, and unsuccessful query categories. Complete
per-query output is retained in compressed JSON next to readable reports. Source
fingerprints before and after those final runs match their original version.

These are **v0.1.0 measurements**, retained as historical evidence rather than
presented as a new v0.2.0 benchmark. Recall requires the exact annotated evidence
to survive into the budgeted context with its correct source span; it is not an
LLM answer score. Local latency excludes process startup, transcript capture,
MCP transport, networking, and inference. Result caching was disabled while
SQLite/OS page caches remained available.

The original v0.1 core and browser evidence is also available in its
[core run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42990594538)
and [browser run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42991673979).

## What these checks do not establish

- Client profiles follow official configuration schemas and have fixture tests;
  every vendor application was not interactively launched and authenticated.
- Native service definitions and command flows have focused tests. The installer
  matrix does not exercise real login/logout, sleep/resume, or long-running user
  sessions under systemd, launchd, and Task Scheduler.
- Import formats are covered by representative synthetic records, not every
  historical vendor version or multimodal format. Current Kimi Code has MCP
  configuration support; native capture is limited to the separately named
  legacy Python Kimi format.
- Generated histories and a small local capture measurement do not establish
  performance on a large personal archive, network disk, or every operating
  system. Browser coverage is Chrome/Chromium at the stated sizes.
- Lexical retrieval does not guarantee semantic recall, authoritative conflict
  resolution, automatic host injection, or end-to-end model answer quality.
- Related memory projects were researched, not installed and benchmarked against
  this implementation. No competitor performance claim is made.
