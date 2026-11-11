# Release validation

This document separates functional checks, measured retrieval behavior, and the
limits of what was tested. All fixtures and published examples are synthetic.
No private user conversation history was read or published.

## Core and integrations

The release source passed **83 unittest cases** with the optional official MCP
SDK installed. The suite covers transactional import and replacement, source
provenance, pagination, scoped retrieval, budgets, persistent cache invalidation,
database migration, export round trips, importer formats, HTTP protections,
directory pagination, and evaluator accounting. MCP tests launch the real stdio
server and use the official SDK client; they do not only call tool functions in
process. Without the optional SDK, the four MCP cases are skipped.

The first published core commit passed the GitHub Actions matrix on Python
**3.10, 3.12 and 3.13**, plus the separate MCP job:
[verified core run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42990594538).
The repository [workflow](../.github/workflows/ci.yml) runs these checks on each
push and pull request.

```bash
python -m pip install -e '.[mcp]'
python -m unittest discover -s tests -v
```

A wheel was also built, installed into an isolated target without dependencies,
and used to import the example conversations and retrieve a cited answer. Its
installed Python and static-reader files were compared with the release source.
This verifies packaging of the core and reader; there is no PyPI publication.

## Browser checks

The `reader-browser` CI job launches the real HTTP server over a temporary
synthetic database and operates Chrome/Chromium with Playwright. It exercises
desktop project selection, chapter browsing across sessions, project-scoped
Chinese search, source reading, keyboard focus restoration, import preview and
confirmation, inert rendering of script-like source text, and the 390px mobile
table of contents. Horizontal overflow, page exceptions, console errors, failed
requests, and unexpected dialogs fail the check.

The job publishes desktop/mobile PNGs and a machine-readable check report as
the `reader-browser` workflow artifact. Artifacts expire after seven days.
The browser script is intentionally outside unittest discovery so Playwright
is not required by the dependency-free core.

```bash
python -m pip install . playwright
python -m playwright install --with-deps chromium
python tests/browser_smoke.py
```

## Retrieval measurements

The [experiment record](../benchmarks/EXPERIMENTS.md) includes the initial short
corpus, development page-size sweep, all six segmentation/ranking combinations,
two final heldout seeds, and unsuccessful categories. Complete per-query output
is retained in compressed JSON alongside readable reports. Source fingerprints
before and after both final runs match; the processes were restarted after
release fixes.

Reported recall requires the exact annotated original evidence to survive into
the budgeted context with the correct source span. It is not an LLM answer
score. Latency measures local retrieval, without result caching, and does not
include process startup, network transfer, MCP transport or model inference.

## Remaining evidence gaps

- Generated engineering conversations do not establish performance on real user
  histories, other domains, or hundreds of millions of characters.
- Import adapters are tested against representative synthetic export fixtures,
  not every historical client export version or multimodal format.
- Browser checks cover Chrome/Chromium at two viewport sizes, not every browser,
  mobile device or assistive technology.
- Current evidence does not establish a semantic-search, authoritative-version,
  or end-to-end answer-quality guarantee.
- External memory projects were researched, not installed and benchmarked against
  this implementation. No competitor performance claim is made.
