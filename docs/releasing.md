# Publishing a verified release

The release workflow publishes an exact commit using an explicitly registered
release channel. **Native releases from v0.8.0 onward require all 30 native
wheel cells from one source commit, workflow run and attempt**, the complete
11-job CI gate, and a real public-installer check. Registered normal releases
use `prerelease=false` and are marked Latest when first published. v0.3.0
through v0.3.2 retain their original prerelease channels. Unknown versions are
rejected until their channel and accepted runtime hash are registered in
[`scripts/release.py`](../scripts/release.py); a new native version also needs
an entry in `NATIVE_RELEASE_TAGS`. This workflow does not publish to PyPI or
enable GitHub's immutable-release repository setting.
Only accepted, source-bound runtime improvements enter a release; rejected
research candidates are not enabled by packaging. Published tags stay fixed.

## Prepare and authorize the source

Update `pyproject.toml`, `memory_book.__version__`, the three installer defaults,
README installation links and `docs/releases/vVERSION.md` together. Commit all
changes, including the release tooling, on a preparation branch. Wait for the
existing **Tests** workflow to complete all **11 jobs** successfully on that
exact commit:

| Jobs | Required coverage |
| --- | --- |
| Five `core` jobs | CPython 3.10, 3.12, 3.13, 3.14 and 3.15 |
| `mcp` | Installed MCP/client/benchmark extras and the test suite |
| `reader-browser` | The reader in a real browser |
| Three `installers` jobs | Ubuntu, macOS and Windows |
| `container` | Image build, MCP, reader and persistent storage |

The job names are enforced by `EXPECTED_JOBS` in `scripts/release.py` and must
match [the CI workflow](../.github/workflows/ci.yml). Evidence acceptance precedes
this packaging gate and is scoped to the version's committed release notes.
Historical acceptance decisions remain version-specific:
v0.7.0 accepts the project assertions and bound-connection behavior documented in
[its validation record](v0.7.0-project-scope-validation.md), with an unchanged
native engineering replay. It adds no external-component measurement or speed
claim. Retained initial failures and corrected test expectations do not waive
the exact-source CI, packaging or public-installer gates.
v0.4.0 selects the 2,400-character engineering profile: default calls must match
the explicit selected configuration, retain the saved development quality, and
pass source, scope and budget checks. Its reported local p95 cost and other
budget results remain in the complete engineering report; it is not a release
claim of universal speed or real-LLM productivity. Register its runtime hash
only after that validation and the requested release scope are recorded.
The historical v0.3.3 round-five performance/resource requirements and v0.3.4
startup decision retain their original version-specific records. Packaging
never repeats or reinterprets those benchmarks.

Fast-forward `main` to that same tested commit. Only after it is ready, create
the branch `release/vVERSION` at exactly that SHA. The push starts
`.github/workflows/release.yml`. Do not use `release/v*` as a development branch.

The script refuses publication unless the repository is
`Afloat16/AI-Memory-Book`, the event is `push`, the ref matches the package version,
`GITHUB_SHA` matches the checkout, and the current `main` points to that same SHA.
It reads the existing `ci.yml` push runs for the exact SHA, requires the newest
completed run to have succeeded, and checks the names, status, conclusion and
commit of all 11 jobs in that CI run's exact attempt. A still-running same-commit
run does not replace a completed gate. The workflow never waits for CI, reruns CI or accepts a partial
matrix. If no qualifying completed run exists, it stops before creating a tag.

The publishing job has only `contents: write` and `actions: read`. Actions are
pinned to complete commit IDs. Build and installation subprocesses do not receive
`GH_TOKEN` or `GITHUB_TOKEN`.

## Native matrix, receipts and artifacts

[The release workflow](../.github/workflows/release.yml) uses five platform jobs.
Each independently builds, installs and tests CPython 3.10, 3.11, 3.12, 3.13,
3.14 and 3.15, for 30 cells total. The native matrix includes Python 3.11 even
though it is not a separate core CI job.

| Target | Hosted runner |
| --- | --- |
| `linux_x86_64` | `ubuntu-24.04` |
| `linux_aarch64` | `ubuntu-24.04-arm` |
| `macos_x86_64` | `macos-15-intel` |
| `macos_arm64` | `macos-26` |
| `windows_amd64` | `windows-2022` |

Each cell uses the absolute interpreter returned by its own `setup-python`
step. [`build_native_release_cell.py`](../scripts/build_native_release_cell.py)
requires native compilation, installs the resulting wheel, checks the isolated
native import, and captures one complete 144-test run. A zero exit alone is not
sufficient: exactly one test summary and one successful outcome are required.
Only the two named optional tokenizer tests and the named optional
`_xxsubinterpreters` test may be skipped, with their exact recorded reasons.
Unexpected skips, duplicate or inconsistent summaries, expected failures and
other failures stop the cell before receipt generation or wheel collection.
The validation record reports actual skipped counts; 144 discovered tests does
not mean 144 executed passes when these optional tests are skipped.

The receipt then binds the committed source/build inputs, CPython and platform
tags, compiler-log provenance, wheel and extension hashes, and an installed
native ingest/recall/source smoke. [`native_release.py`](../scripts/native_release.py)
requires exactly one wheel/receipt pair for every cell, all from the current
workflow run and attempt. Incomplete matrices, duplicate cells, mixed sources,
mixed runs and mixed attempts are rejected.

Artifacts are named `native-wheel-RUN_ID-RUN_ATTEMPT-TARGET` and
`native-cell-evidence-RUN_ID-RUN_ATTEMPT-TARGET`. Both the publishing and
prepare-only aggregators download only
`native-wheel-RUN_ID-RUN_ATTEMPT-*` for their current attempt. Full reruns create
new artifact names; previous artifacts are retained without overwrite or
deletion. This follows the pinned
[upload-artifact v4 immutability contract](https://github.com/actions/upload-artifact/blob/ea165f8d65b6e75b540449e92b4886f43607fa02/README.md).
Successful cells from an earlier attempt cannot fill missing cells in a retry.
Historical evidence and its frozen auditors retain their original names and
source bindings.

## What is built and checked

The native cells and Python 3.12 aggregator use `build==1.3.0`,
`setuptools==80.9.0` and `wheel==0.45.1`. Linux cells also use
`auditwheel==6.4.2` and `patchelf==0.17.2.4` to produce the declared manylinux
wheels. After validating the complete native matrix, a fresh staging directory
receives only `pyproject.toml`, `setup.py`, `README.md`, `LICENSE` and the
Git-tracked runtime files under `src/memory_book`.
The sdist is an installable product source package; the repository's research
reports, benchmark tooling, tests, private archives and models are not package
inputs. Installer entry points are separate release assets.

With native compilation disabled, `python -m build --no-isolation` builds an
sdist and then the Python fallback wheel **from that sdist**. Every actual
archive member is inspected. Both formats must contain
exactly the committed runtime and reader bytes; unexpected packages, research
directories, database/model files, traversal paths and excessive archive sizes
are rejected. Historical versions retain their original approval hashes.
For `v0.3.0`, the runtime Python-source SHA must remain
`d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`.
For `v0.3.1`, it must remain
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`,
matching frozen candidate commit `2d199b93f650eccd3dd239178822b31001b880e3`.
A later documentation or packaging commit may carry those same runtime bytes;
a committed runtime change still fails preparation under either frozen version.

The commit timestamp is used as `SOURCE_DATE_EPOCH`. Tar/gzip and ZIP metadata
are normalized deterministically for the fallback wheel and sdist; source
files and wheel `RECORD` contents are not rewritten. The supplied native wheel
bytes are copied unchanged after verification, never rebuilt during aggregation.
The fallback wheel and sdist are each installed in a separate fresh virtual
environment, outside the source checkout's import path. Each installation must
report the expected package and console version, contain the reader HTML, and
pass a tiny original-source ingest/recall fixture. The core smoke needs no
provider, real model or user archive. The sdist smoke uses the pinned backend.

With the current 30-cell matrix, exactly **67 assets** are published:

| Assets | Count |
| --- | ---: |
| Native wheels, one per Python/platform cell | 30 |
| Matching `WHEEL.whl.receipt.json` files | 30 |
| `ai_memory_book-VERSION-py3-none-any.whl` | 1 |
| `ai_memory_book-VERSION.tar.gz` | 1 |
| `install.py`, `install.sh`, `install.ps1` | 3 |
| `release-manifest.json` | 1 |
| `SHA256SUMS` | 1 |

The source/build manifest records the commit, Git tree, runtime hashes, pinned
build tools, package/installer sizes and hashes, the native matrix's run and
attempt, and completed packaging checks. Its asset inventory covers the 65
payload files. `SHA256SUMS` covers those payloads plus the manifest, 66 files;
it does not hash itself. Compiler and test logs remain in the cell evidence
artifacts. Native receipts record workflow build provenance, not a claim that
independent native rebuilds reproduce identical bytes.
The release body uses the committed notes file and appends the actual source SHA,
the successful CI URL and the release workflow URL. This is a **source/build
manifest plus linked CI**, not an attestation or a provider billing record.

## Publication, interruption and recovery

No tag or draft is created until source, CI, package and clean-install checks
pass. The tag must identify exactly the tested commit; existing tags are never
forced or moved. An existing public release is never edited. An existing draft
can be continued only if it belongs to the same exact SHA.
Existing-draft discovery uses the authenticated, paginated release list and
rejects duplicate tags. A newly created draft uses the ID returned directly by
the [Release API](https://docs.github.com/en/rest/releases/releases#create-a-release),
without depending on immediate list visibility. Subsequent checks address that
unique ID. After writes, only GET visibility is polled, at 1, 2 and 4 seconds;
tag/source mismatches fail immediately. Creation and uploads are never blindly
repeated. Failure messages include the stage, exit code and available HTTP
status without exposing response bodies or credentials; the workflow records
the GitHub CLI version.

Before resuming a draft, every existing asset must have an expected name, an
uploaded state, the expected size and the exact downloaded SHA-256. Extra,
partial or different assets fail closed and remain available for inspection.
Only missing assets are uploaded, without `--clobber`. After all 67 native-release
assets are downloaded and verified, the draft is made public in its registered channel.
The script then checks the published state, tag and downloaded asset bytes
again. A new normal release also receives a bounded GET-only Latest check;
no failed visibility check causes a second publication write.

The workflow preserves built assets and final notes through an `always()`
artifact step. Recovery depends on the phase that failed:

| Failure point | Native-release recovery |
| --- | --- |
| Preflight, native cells, or prepare-only aggregation | Fix the cause, then rerun the full workflow so all 30 cells and the aggregator share the new attempt. A failed-jobs-only rerun cannot reuse older successful cells. |
| Publishing failed before any release asset was uploaded | Inspect the exact tag/draft state first. A full workflow rerun can proceed only while `main`, the tag and any empty draft still identify the same source commit and all normal gates pass. |
| A draft already contains uploaded assets | Preserve the draft and original run's artifacts for inspection. The generic workflow has no automatic same-attempt recovery for this case; a publishing-job-only rerun cannot pass the receipt gate. |
| The release is public but publishing verification or job outputs were interrupted | Keep the public release unchanged. Verify it read-only against its original manifest and retained assets. The generic workflow cannot promise to restore outputs by rebuilding a new native attempt. |
| Only `published-install` failed after a successful publishing job | Rerun only `published-install`, using the already published release and the successful publishing job's outputs. |

New attempts have different receipt provenance and can produce different native
binary bytes. They must not be represented as the original attempt or used to
replace its receipts. Existing remote assets must still match byte for byte;
do not delete, overwrite or rename mismatched evidence to make a retry pass.
Resuming a partially uploaded native release or recovering interrupted outputs
requires a separately reviewed recovery procedure that preserves those original
bindings. Until then, that release remains blocked at its failed gate.

The older pure-Python release path can rebuild its deterministic seven assets
when retrying a matching draft, or perform read-only reconciliation of an
already public release. Those historical retry instructions do not waive the
native path's same-run, same-attempt requirement.

After publication, a separate job with only `contents: read` downloads the real
public tagged `install.py`, checks its hash against the published manifest, and
runs its default release-wheel installation in `RUNNER_TEMP`. It verifies the
version, console command, native wheel selection and default MCP/client extras
without configuring a client or capture. If this final network-dependent smoke fails, rerun **only
that failed job**; publishing has already completed and must not be repeated.

## Prepare native packages without publishing

Push an exact committed source to `validation/native-language-wheels-*` to use
the prepare-only branch of the same workflow. It builds and verifies all 30
native cells, assembles the fallback and source package, and exercises both a
matching native wheel and the fallback through the installer with default MCP
and client extras. It has no publication job on that branch and creates no tag
or release. The naming prefix is retained for workflow compatibility; this is
the current native packaging validation path.

Local preparation also requires a clean committed checkout, the pinned build
tools, and all 30 wheel/receipt pairs from one exact-source run and attempt.
This command validates those supplied native artifacts; it does not build a
cross-platform matrix on the local machine or invoke the publication API:

```bash
python -m pip install build==1.3.0 setuptools==80.9.0 wheel==0.45.1
```

```bash
NATIVE_WHEEL_DIR=/absolute/path/to/complete-native-wheels \
python scripts/release.py --prepare-only \
  --source-root /absolute/path/to/clean-checkout \
  --output /absolute/path/to/new-release-assets
```

Inside Actions, the receipts must additionally match the current
`GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT`. Never change those variables to reuse
older successful subsets. The output directory must not already exist. Inspect
`release-manifest.json` and `SHA256SUMS`; exact file sizes and hashes come from the built assets, not a
repository-size estimate. The release unit fixtures cover CI failure gates,
matrix/receipt integrity, attempt-specific artifact selection, failure before
receipt creation, archive normalization, bounded GET-only visibility polling,
historical interruption reconciliation, and refusal to overwrite or accept
mismatched remote assets. Run them without building or publishing an app:

```bash
python -m unittest tests.test_release tests.test_native_release \
  tests.test_native_release_cell tests.test_native_release_workflow \
  tests.test_installer_release -v
```

## Historical pure-Python preparation

The [v0.3.1 prerelease](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.1)
retains its original seven-asset packaging path. Preparing packages from a later
documentation or tooling commit binds them to that new commit; it does not
replace the existing tag or public release assets. Historical versions use the
same `--prepare-only` command without `NATIVE_WHEEL_DIR` and retain their
version-specific source and runtime approval checks.

The separate `Prepare v0.3.1 release assets` workflow runs on preparation branches
`prep/v0.3.1-packaging` and `prep/v0.3.1-packaging-*`. It has only
`contents: read`, invokes `--prepare-only`, verifies the frozen runtime hash,
and installs the produced local wheel with the default MCP/client extras in a
disposable prefix. Its artifact includes the seven prepared payload/checksum
files and an installation smoke report. It creates no tag, draft, release or
repository commit. This historical workflow is not the current native release
gate. The current 11-job CI and final release gates remain required on the exact
final source commit. After README or other package inputs change, prepare a new
artifact for that new commit; an earlier artifact records
only the source commit in its manifest.
