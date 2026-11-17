# Offline audit of a published comprehensive release

`scripts/audit_comprehensive_release.py` verifies a completed publication from
staged evidence. It reads exact Git objects and downloaded bytes. It does not
download, build, install, execute native binaries, rerun tests, measure
performance, retry workflows, or publish. Its only output is a new proof JSON.
The historical `audit_native_core_grouped_packaging.py` remains unchanged.

The caller supplies the final source commit, version, approved runtime digest,
release run ID and attempt independently of the artifacts. The script requires
its own bytes and the current release/receipt/cell validators to match that Git
commit. The final commit must already register the runtime digest in
`scripts/release.py`. The working checkout need not be switched to that commit;
the object database must contain it and the native baseline.

## Acquisition contract

Use the GitHub API and public download URLs to acquire the files below. Save
responses as ordinary local files under one evidence directory. JSON files
contain the API document itself, without connector wrappers. Preserve original
archive and asset bytes. Keep decoded job logs as UTF-8 without changing
timestamps, ANSI sequences, line endings or whitespace. The auditor hashes
those retained bytes before normalizing log text for comparisons.

Here `REPO` is `Afloat16/AI-Memory-Book`, `S` is the final source commit, `V` is
the version without `v`, `R` is the release workflow run, and `A` is its chosen
attempt. API paths are relative to `https://api.github.com/repos/REPO/`.

| Local path | Acquisition endpoint or source |
| --- | --- |
| `metadata/commit.json` | `commits/S` (the REST commit response, with `commit.tree.sha`) |
| `metadata/main-ref.json` | `git/ref/heads/main` |
| `metadata/tag-ref.json` | `git/ref/tags/vV` |
| `metadata/run.json` | `actions/runs/R/attempts/A` |
| `metadata/jobs.json` | All pages of `actions/runs/R/attempts/A/jobs?per_page=100` |
| `metadata/artifacts.json` | All pages of `actions/runs/R/artifacts?per_page=100` |
| `metadata/release.json` | `releases/tags/vV` |
| `metadata/latest-release.json` | `releases/latest` |
| `metadata/ci-runs.json` | All pages of `actions/workflows/ci.yml/runs?event=push&head_sha=S&per_page=100` |
| `metadata/ci-jobs.json` | All pages of `actions/runs/C/attempts/B/jobs?per_page=100`, where `C`/`B` identify the newest completed push CI in `ci-runs.json` |
| `artifacts/ID.zip` | The original ZIP returned by `actions/artifacts/ID/zip` for each selected artifact below |
| `logs/JOB_ID.log` | `actions/jobs/JOB_ID/logs` for each of the eight successful release jobs below |
| `public-assets/NAME` | Every one of the 67 assets using its public `browser_download_url` from `release.json` |
| `public-install.py` | `https://raw.githubusercontent.com/REPO/vV/scripts/install.py` |

For paginated collections, merge the array from every page into one document;
retain the API's `total_count`. The auditor requires `total_count` to equal the
merged array length and rejects duplicate IDs. Do not silently truncate a
collection or substitute the latest-attempt jobs endpoint for the selected
attempt's endpoint. Native receipts and cell reports also have to identify
that exact attempt.

The 11 selected artifact names are:

- `release-R-A`;
- `native-wheel-R-A-TARGET`, once for each of the five targets;
- `native-cell-evidence-R-A-TARGET`, once for each of the five targets.

The targets are `linux_x86_64`, `linux_aarch64`, `macos_x86_64`, `macos_arm64` and
`windows_amd64`. Older attempts may remain in the run-level artifacts response;
their archives are not substituted or required. Each selected archive's exact
byte count and SHA-256 must match its API record. The release archive must
contain `release-notes.md` and exactly 67 files under `release-assets/`.

The successful jobs are `preflight`, `release`, `published-install` and the five
`native-wheel (TARGET)` jobs. `prepare-only` must be absent or skipped. No
additional preparation run is needed. The release itself already aggregated
the 30 wheels and tested fallback packages before publication.

Capture main, tag, latest release and public asset responses after publication
has completed and before main advances. The release script creates a direct
commit tag; the auditor enforces the same contract. If acquisition fails, retain
the partial evidence and finish the missing reads. Do not reconstruct a missing
CI log or receipt, modify a receipt, or rerun builds to fill an evidence gap.

## Invocation

Run from a checkout containing the final auditor and validators. Replace the
capitalized placeholders with the independently established final values:

```sh
python -B scripts/audit_comprehensive_release.py \
  --evidence /absolute/path/to/release-evidence \
  --repo-root /absolute/path/to/AI-Memory-Book \
  --source-commit FINAL_SOURCE_COMMIT \
  --version 0.10.0 \
  --runtime-sha256 APPROVED_RUNTIME_SHA256 \
  --native-baseline 238c8058f723a203eaca99f94d924ab77de4c0b3 \
  --run-id RELEASE_RUN_ID \
  --run-attempt RELEASE_ATTEMPT \
  --output /absolute/path/to/comprehensive-release-audit.json
```

The output path must not exist. Any failed check exits unsuccessfully without
writing a passed proof. Input files are read again before the proof is returned
to catch accidental changes during inspection. No archive is extracted into the
source tree or evidence directory.

## Acceptance checks and proof schema

The driver calls current `native_release.inspect_wheel`, `inspect_sdist` and
`validate_receipt`. It reparses every installed-test log through current
`build_native_release_cell.test_summary` and `validate_test_result`. Each cell
must have exactly one successful 144-test outcome and only a unique subset of
the explicitly allowed optional skips. It does not impose the historical
auditor's narrower combination of skipped tests.

For every CPython 3.10–3.15/target cell, the proof connects its successful setup
and build steps, setup-python executable/version, actual command transcript,
raw command logs, compiler commands and log digest, original receipt, installed
native smoke digest, wheel contents, manifest, and public asset bytes. The six
native `.c`/`.h` files and frozen historical auditor must still match the supplied
native baseline. The current runtime, reader and build inputs must match the
final Git commit; native binary hashes are the hashes produced by this release,
not hashes copied from an earlier release.

The published-installer proof requires the actual successful job's transcript
to contain the committed workflow's public-install script and its executed
terminal success marker. The same command group must log exactly one matching
`RELEASE_TAG`, `RELEASE_VERSION` and `RELEASE_COMMIT`; values in other steps do
not substitute for those inputs. That script downloads the tagged helper and public
manifest, uses the default release-wheel installation path, verifies native
selection and selected wheel digest, and checks the version and default
MCP/client extras. This audit does not perform another installation.

The output uses `schema_version: 1` with these principal fields:

| Field | Meaning |
| --- | --- |
| `status`, `published`, `source` | Passed publication status and exact version/tag/commit/tree/epoch/runtime digest |
| `native_baseline_commit`, `source_git_blobs`, `source_files_sha256`, `audit_code_sha256` | Source and validator provenance |
| `release`, `workflow`, `ci`, `jobs` | Public release identity and successful source/attempt-bound jobs |
| `artifacts` | IDs, names, byte sizes, hashes and file counts of the 11 original ZIPs |
| `assets` | Exact byte size and hash of all 67 independently downloaded public assets |
| `counts` | 30 native cells, 4,320 test outcomes, actual pass/skip totals, 67 assets, 65 manifest payloads and 66 checksum entries |
| `native_cells` | All 30 interpreter, command, test, compiler, receipt and native-smoke records |
| `fallback_wheel`, `published_installer` | Inspected compiler-free wheel and existing hosted public-installer evidence |
| `staged_evidence` | Exact byte count and hash of every input file the auditor consumed |
| `scope` | Explicit statement that this is an offline evidence audit, with no rebuilding or performance measurement |

The proof binds staged data consistently; it is not an independent signature
from GitHub. Acquisition authenticity relies on the caller obtaining the API
responses, logs and bytes from the stated GitHub endpoints. Synthetic auditor
tests use dummy extension bytes and do not establish real native execution.
Only the retained hosted build/test/smoke evidence supports that claim.
