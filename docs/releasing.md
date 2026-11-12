# Publishing an experimental release

The release workflow publishes an exact commit as a GitHub **prerelease**. It
does not publish to PyPI or enable GitHub's immutable-release repository setting.
The current `v0.3.0` runtime remains the verified lexical/Q2 implementation;
rejected research candidates are not enabled by packaging.

## Prepare and authorize the source

Update `pyproject.toml`, `memory_book.__version__`, the three installer defaults,
README installation links and `docs/releases/vVERSION.md` together. Commit all
changes, including the release tooling, on a preparation branch. Wait for the
existing **Tests** workflow to complete all nine jobs successfully on that exact
commit. These include three core Python versions, MCP, the browser, three
platform installers and the container. No benchmark is part of this release gate.

Fast-forward `main` to that same tested commit. Only after it is ready, create
the branch `release/vVERSION` at exactly that SHA. The push starts
`.github/workflows/release.yml`. Do not use `release/v*` as a development branch.

The script refuses publication unless the repository is
`Afloat16/AI-Memory-Book`, the event is `push`, the ref matches the package version,
`GITHUB_SHA` matches the checkout, and the current `main` points to that same SHA.
It reads the existing `ci.yml` push runs for the exact SHA, requires the newest
completed run to have succeeded, and checks the names, status, conclusion and
commit of all nine jobs. A still-running same-commit run does not replace a
completed gate. The workflow never waits for CI, reruns CI or accepts a partial
matrix. If no qualifying completed run exists, it stops before creating a tag.

The publishing job has only `contents: write` and `actions: read`. Actions are
pinned to complete commit IDs. Build and installation subprocesses do not receive
`GH_TOKEN` or `GITHUB_TOKEN`.

## What is built and checked

The build uses Python 3.12 with `build==1.3.0`, `setuptools==80.9.0` and
`wheel==0.45.1`. A fresh staging directory receives only `pyproject.toml`,
`README.md`, `LICENSE` and the Git-tracked runtime files under `src/memory_book`.
The sdist is an installable product source package; the repository's research
reports, benchmark tooling, tests, private archives and models are not package
inputs. Installer entry points are separate release assets.

`python -m build --no-isolation` builds an sdist and then a wheel **from that
sdist**. Every actual archive member is inspected. Both formats must contain
exactly the committed runtime and reader bytes; unexpected packages, research
directories, database/model files, traversal paths and excessive archive sizes
are rejected. For `v0.3.0`, the runtime Python-source SHA must remain
`d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`.

The commit timestamp is used as `SOURCE_DATE_EPOCH`. Tar/gzip and ZIP metadata
are normalized deterministically; source files and wheel `RECORD` contents are
not rewritten. The wheel and sdist are each installed in a separate fresh virtual
environment, outside the source checkout's import path. Each installation must
report the expected package and console version, contain the reader HTML, and
pass a tiny original-source ingest/recall fixture. The core smoke needs no
provider, real model or user archive. The sdist smoke uses the pinned backend.

Exactly seven assets are published:

- `ai_memory_book-VERSION-py3-none-any.whl`
- `ai_memory_book-VERSION.tar.gz`
- `install.py`, `install.sh`, `install.ps1`
- `release-manifest.json`
- `SHA256SUMS`

The source/build manifest records the commit, Git tree, runtime hashes, pinned
build tools, package/installer sizes and hashes, and completed packaging checks.
`SHA256SUMS` covers the five payloads plus the manifest; it does not hash itself.
The release body uses the committed notes file and appends the actual source SHA,
the successful CI URL and the release workflow URL. This is a **source/build
manifest plus linked CI**, not an attestation or a provider billing record.

## Publication, interruption and recovery

No tag or draft is created until source, CI, package and clean-install checks
pass. The tag must identify exactly the tested commit; existing tags are never
forced or moved. An existing public release is never edited. An existing draft
can be continued only if it belongs to the same exact SHA.

Before resuming a draft, every existing asset must have an expected name, an
uploaded state, the expected size and the exact downloaded SHA-256. Extra,
partial or different assets fail closed and remain available for inspection.
Only missing assets are uploaded, without `--clobber`. After all seven are
downloaded and verified, the draft is made public as a prerelease. The script
then checks the published state, tag and downloaded asset bytes again.

The workflow preserves built assets and final notes through an `always()`
artifact step. If publication fails while the release is still a matching draft,
rerun the failed publishing job after fixing the external problem; deterministic
rebuilding must match existing bytes. Do not delete or replace mismatched assets
to bypass the check. A public release cannot be republished by this script.

After publication, a separate job with only `contents: read` downloads the real
public tagged `install.py`, checks its hash against the published manifest, and
runs its default release-wheel installation in `RUNNER_TEMP`. It verifies the
version, console command and default MCP/client extras without configuring a
client or capture. If this final network-dependent smoke fails, rerun **only
that failed job**; publishing has already completed and must not be repeated.

For local packaging preparation, use a clean committed checkout and the pinned
build tools. This command makes no GitHub request and cannot publish:

```bash
python scripts/release.py --prepare-only \
  --source-root /absolute/path/to/clean-checkout \
  --output /absolute/path/to/new-release-assets
```

The output directory must not already exist. Inspect `release-manifest.json`
and `SHA256SUMS`; exact file sizes and hashes come from the built assets, not a
repository-size estimate. The small unit fixtures in `tests/test_release.py`
check CI failure gates, lossless archive normalization and refusal to overwrite
or accept mismatched remote assets.
