# v0.11.0 original publication proof

The unchanged publication auditor passed against the original release evidence.
No workflow, native build, installation, quality test or performance experiment
was rerun to produce this proof.

| Bound identity | Value |
| --- | --- |
| Published source | `78cc906d81818a16884de7de2e613e5a56346f93` |
| Version and tag | `0.11.0`, `v0.11.0` |
| Release runtime SHA-256 | `64f36bbf9cb59ca338a41c623b516f3c46b97a53cae05f31976d50d13bf0aa75` |
| Native-source baseline | `238c8058f723a203eaca99f94d924ab77de4c0b3` |
| Publication run / attempt | `44233642151` / `1` |
| Public release ID | `449507762` |
| Original preparation CI | `44233236683` / `1`, 11 successful jobs |
| Latest completed same-source CI at capture | `44238673693` / `1`, 11 successful jobs |

The audit verifies **30 native cells**, **4,320 discovered native-test outcomes**
comprising **4,245 passes and 75 explicitly permitted optional skips**, and
**67 independently downloaded public assets**. All 30 cells belong to the same
source, release run and attempt. The original public-installer job verifies
native wheel selection, version and default MCP/client dependencies. Skipped
tests are recorded separately from passes.

- [audit.json](audit.json) is the complete machine-readable proof, including
  each cell, compiler/test/receipt binding, public asset hash and input hash.
- [evidence-parts](evidence-parts) retains the original artifact ZIPs, all public
  assets, API metadata, decoded job logs and tagged installer as ordered pieces
  of the original `original-evidence.tar.xz`. Each piece is at most 262,144 bytes;
  reconstruction preserves the exact original whole-archive SHA-256. The large
  combined archive is not also stored in Git. No bearer credentials or expiring
  download URLs are included.
- [evidence-manifest.json](evidence-manifest.json) records the archive hash and
  the exact hash/size of every restored file. The archive was read back and
  checked losslessly against every auditor input before being saved.
- [acquisition-provenance.json](acquisition-provenance.json) records acquisition
  boundaries and the transparent CI-run derivation described below.
- [preparation-ci-jobs.json](preparation-ci-jobs.json) additionally preserves
  the original preparation run's 11 successful attempt-1 job records. Its
  original API endpoint and byte hash are listed in `evidence-manifest.json`.

## Acquisition and CI selection

The connected repository reader supplied API documents and decoded job logs.
Original artifact ZIP bytes came from its artifact-download operation. All 67
public release assets were downloaded separately through their returned public
download URLs; they are not copies extracted from the Actions release archive.
Windows log carriage returns, decoded UTF-8 BOMs and terminal newlines were
preserved. Main, the direct release tag and Latest were captured while all still
identified this publication.

The connected reader rejected the workflow-specific run-list endpoint. The
original complete repository run collection, scoped to the exact source SHA
and `event=push`, is retained as `metadata/source-runs.json`. It contains five
runs. `metadata/ci-runs.json` derives the four records whose path is
`.github/workflows/ci.yml` and workflow ID is `414432715`, preserving every
selected record unchanged and recording the selected count. It is explicitly a
derived collection, not an unmodified response from a different endpoint.
The auditor selects the newest completed record and checks all 11 jobs from
that exact attempt. The original preparation CI is also present in the complete
run collection.

The remaining metadata, eight successful-job logs, 11 original artifact ZIPs,
public assets and installer follow the
[published acquisition contract](../../../docs/comprehensive-release-audit.md).
The proof establishes consistency of downloaded GitHub evidence; it is not a
separately signed attestation or a claim of reproducible native binary builds.

## Reproduce the offline audit

Use the published source checkout at
`78cc906d81818a16884de7de2e613e5a56346f93`, with the native-baseline Git object
available. A later release may change the validators, so its working files must
not silently replace the frozen auditor. From this evidence package, restore
the parts into a new directory with an existing parent:

```sh
python restore_evidence.py --output /absolute/path/to/restored-evidence
```

The restorer checks each piece, the reconstructed archive and every restored
file against `evidence-manifest.json`, including the 97 original audit inputs.
It rejects an existing destination and commits the restored directory only
after all checks pass. No network access or native code execution is required.

Run from the frozen source checkout, replacing the three absolute paths below:

```sh
python -B scripts/audit_comprehensive_release.py \
  --evidence /absolute/path/to/restored-evidence \
  --repo-root /absolute/path/to/published-source \
  --source-commit 78cc906d81818a16884de7de2e613e5a56346f93 \
  --version 0.11.0 \
  --runtime-sha256 64f36bbf9cb59ca338a41c623b516f3c46b97a53cae05f31976d50d13bf0aa75 \
  --native-baseline 238c8058f723a203eaca99f94d924ab77de4c0b3 \
  --run-id 44233642151 \
  --run-attempt 1 \
  --output /absolute/path/to/new-audit.json
```

The new output must match `audit.json` as a JSON document. The auditor refuses
to overwrite an existing proof and performs no network access, builds or
installation. The original public release remains unchanged.
