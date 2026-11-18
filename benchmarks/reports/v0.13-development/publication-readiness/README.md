# v0.13 publication readiness review

This is a preparation record, not source acceptance or publication evidence.
It inspects the existing release path and prepares version-parameterized helper
copies. No runtime registration, build, installation, workflow retry, network
download, tag, release or release-body edit was performed.

## Current identities

- The formal scale candidate is remote source
  `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc`, whose tree is reported by the
  coordinator to equal local `91412b438a0da95549cc9a3b85eccb4915359a2d`.
- Run `44331778554`, attempt `1`, is the second scale experiment. It is not a
  release run. Its results must be independently audited before acceptance.
- The coordinator reported that exact-source Tests run `44331775791`, attempt
  `1`, completed all 11 jobs successfully. This preparation did not reacquire
  that API response; the coordinator retains the original CI evidence.
- A read-only recomputation using `scripts.release.source_identity`'s hash
  definition gives candidate runtime digest
  `a7492a74a94170b87a2fd54ada421866b9d737f46dce2ff3a3bc21d6debb9da1` for local
  `91412b438a0da95549cc9a3b85eccb4915359a2d`. It is **not registered or accepted**
  by this review. Recompute if any runtime byte changes.

The release source, called `S` below, will be a later commit containing accepted
evidence, registration and release notes. It needs its own complete CI even if
the runtime digest is unchanged. The final release run/attempt, called `R/A`,
must not be filled with the scale run or the earlier CI run.

## Reuse and required updates

`scripts/release.py`, `scripts/native_release.py`,
`scripts/build_native_release_cell.py`, `scripts/audit_comprehensive_release.py`,
the release workflow and all eight native release test suites are byte-identical
between the v0.12 release source `62508a1ce681111ec5702c88e3aa42f67b9fc9c0` and
the inspected local v0.13 candidate. The six native C/header files and the
historical grouped-packaging auditor also still match native baseline
`238c8058f723a203eaca99f94d924ab77de4c0b3`.

| Item | Current state | Required action after source acceptance |
| --- | --- | --- |
| Package version and three installers | Already `0.13.0` / `v0.13.0`; installer contract test also updated | Preserve consistency |
| `APPROVED_RUNTIME_SHA256` | No `0.13.0` entry | Register only the accepted runtime digest |
| `RELEASE_PRERELEASE` | No `v0.13.0` entry | Register the reviewed normal channel as `False` |
| `NATIVE_RELEASE_TAGS` | Does not include `v0.13.0` | Add the accepted native release version |
| Acceptance record | v0.12 is historical; v0.13 scale run 2 is still under examination | Create a new v0.13 record linking exact sources, all raw results, retained failures, costs and remaining delivery gates |
| Release notes and changelog | New v0.13 release entry required | State measured source results and limits accurately |
| Current README/deployment links | Deliberately point to published v0.12 | Update their installation target and current-release status in the coordinated release preparation |
| Workflow, native validators and comprehensive auditor | Already parameterized | Reuse their strict source/run/attempt contracts |

Do not globally replace `0.12.0`: that would corrupt historical evidence and the
unrelated pinned `tiktoken==0.12.0` dependency. Historical fixtures retain their
original identities. The existing contract suites to run after registration are:

```sh
python -m unittest tests.test_release tests.test_native_release \
  tests.test_native_release_cell tests.test_native_release_workflow \
  tests.test_installer_release tests.test_comprehensive_release_audit -v
```

## Release order

1. Audit the completed second scale run under its unchanged protocol; record
   accuracy, latency, resource costs and every remaining failure. Keep run 1.
2. Commit the new acceptance record, the three registration entries and release
   documentation. Keep author and committer Afloat, verified through the
   coordinator's existing GitHub transport.
3. Push final source `S` on a CI-enabled ref and wait for all 11 Tests jobs.
   **`ci.yml` excludes `validation/**` push branches.** A `review/*`, `prep/*`
   or main push can supply the required push CI; a PR-only result does not
   replace it.
4. Advance main to exactly `S`; create `release/v0.13.0` at exactly `S` only
   after the complete same-source CI gate exists. The formal release workflow
   performs its own preflight, 30 native cells, package checks and public install.
   A separate prepare-only 30-cell run is optional, not a publication requirement.
5. Require successful preflight, the five native platform jobs, release and
   published-install in the same successful release attempt. Keep main at `S`
   until all publication metadata, original archives, logs and public bytes
   have been captured.
6. Run the frozen offline auditor; archive every captured file; restore to a
   separate temporary directory and require an identical second proof. Only
   then update the main-branch delivery summary and checkpoint the proof.

The release notes become the public body and must match `release-notes.md` in
the original release ZIP. Use absolute `https://github.com/Afloat16/AI-Memory-Book/blob/v0.13.0/...`
links so they work in that body. Describe source acceptance and point to the
workflow/current validation for delivery results. Avoid an unqualified
"publication has not run" statement that would remain in the immutable public
body. The workflow appends actual source, CI and release-run links. Existing
public release bodies and assets remain unchanged.

## Capture layout and exact inventories

Use new paths, for example:

- raw capture: `/workspace/scratch/428c08bef2bc/release-evidence-v013`;
- temporary work: `/workspace/scratch/428c08bef2bc/release-evidence-v013-work`;
- final package: `AI-Memory-Book/benchmarks/reports/v0.13-publication`.

The original acquisition contract is in
`docs/comprehensive-release-audit.md`. Capture its 10 mandatory metadata JSON
documents, eight original successful job logs, 11 original ZIPs, 67 independently
downloaded public assets and tagged `public-install.py`: 97 direct audit inputs.
Retain additional API responses, pagination records, download receipts and
acquisition provenance too; their count is not fixed.

The 11 selected ZIP names are `release-R-A` plus
`native-wheel-R-A-TARGET` and `native-cell-evidence-R-A-TARGET` for each of the
five targets. Save them by original artifact ID, verify API size/digest, and
keep the complete paginated artifacts metadata even when it includes older
attempts. Public assets must come from their public URLs, not copies of ZIP
members. Preserve decoded job log BOM/CR/LF/ANSI bytes before inspection.

Expected inventories remain 30 native wheels, 30 receipts, two fallback/source
packages, three installers, one manifest and one checksum file: 67 public assets,
65 manifest payloads and 66 checksum entries. The native suites still discover
144 tests per cell, so 4,320 outcomes are expected; actual pass/skip totals must
come from the new logs. v0.12's 4,245 passes and 75 skips are historical facts,
not v0.13 results.

## Prepared helper copies

- `download_public_assets.py` now requires independent version, full source SHA
  and release ID inputs; it refuses a mismatching saved release document.
- `audit_and_package.py` now requires explicit version/source/runtime/native
  baseline arguments and a temporary root outside the capture/package trees.
  Its audit, archive, part hashing and restored-proof comparison logic is reused.
- `restore_evidence.py` is byte-identical to the v0.12 helper. The old helpers and
  historical package remain untouched.

Only syntax/CLI-help checks were performed on these new copies. Their first
real capture/packaging execution remains part of the future publication task.
Do not run the templates below until `S`, `D`, `R`, `A` and `I` are known from
the accepted release, where `D` is its approved runtime digest and `I` its
public release ID.

```sh
python download_public_assets.py \
  --version 0.13.0 --source-commit S --release-id I \
  --release-json /absolute/release-evidence-v013/metadata/release.json \
  --target /absolute/release-evidence-v013/public-assets \
  --record /absolute/release-evidence-v013/public-assets-downloads.json
```

```sh
python -B audit_and_package.py \
  --repo-root /absolute/AI-Memory-Book \
  --evidence /absolute/release-evidence-v013 \
  --output /absolute/AI-Memory-Book/benchmarks/reports/v0.13-publication \
  --temporary-root /absolute/release-evidence-v013-work \
  --source-commit S --version 0.13.0 --runtime-sha256 D \
  --native-baseline 238c8058f723a203eaca99f94d924ab77de4c0b3 \
  --run-id R --run-attempt A
```

The underlying independent command remains:

```sh
python -B scripts/audit_comprehensive_release.py \
  --repo-root /absolute/AI-Memory-Book --evidence /absolute/release-evidence-v013 \
  --source-commit S --version 0.13.0 --runtime-sha256 D \
  --native-baseline 238c8058f723a203eaca99f94d924ab77de4c0b3 \
  --run-id R --run-attempt A --output /absolute/new-publication-proof.json
```

## Disk plan and recovery boundary

The v0.12 capture retained 116 files totaling 32,824,771 bytes. Its lossless
archive was 16,696,084 bytes in 64 parts. The auditor reads ZIP members in
memory; it needs no extracted copy of all release assets. Native wheels are
built on hosted runners, so this workspace needs no local 30-cell build tree.

Let `E` be new raw evidence size and `C` its compressed archive size. Peak
packaging disk consumption is approximately `2E + 3C`: original capture,
restored capture, packaging archive, output parts and the restorer's temporary
archive can coexist. For v0.12 sizes that is about 116 MB. Git preservation and
the new scale ZIP add further space. Reserve roughly 200–250 MiB while actual
sizes are observed; the workspace reported about 438 MiB available during this
review. No historical evidence deletion is required or authorized by this plan.

Failed output directories and original receipts are preserved; use a new
attempt directory rather than overwrite them. `docs/releasing.md` permits
rerunning only a failed published-install job after publication. The existing
comprehensive auditor, however, requires all eight successful jobs and all
11 ZIPs to share one attempt. An installer-only retry does not create new native
or release ZIPs, so that recovery needs separately reviewed evidence handling;
it cannot be represented as a new complete native attempt. This is a verified
tool boundary, not an observed v0.13 publication failure. It does not block a
normal release whose first complete attempt succeeds.
