# v0.12.0 original publication proof

The frozen publication auditor passed against the original release evidence.
The evidence was then archived, restored and audited again with the same
source-bound validators. The original and restored proof JSON bytes match.
No build, native test, installation, quality evaluation or performance
experiment was rerun for this proof.

| Bound identity | Value |
| --- | --- |
| Published source | `62508a1ce681111ec5702c88e3aa42f67b9fc9c0` |
| Version and tag | `0.12.0`, `v0.12.0` |
| Release runtime SHA-256 | `2842f78c288454ea7348cb81cb6bd6a972cb26e003faaac64eb81f78b2ffa38b` |
| Native-source baseline | `238c8058f723a203eaca99f94d924ab77de4c0b3` |
| Publication run / attempt | `44275753685` / `1` |
| Public release ID | `449762403` |

The audit verifies **30 native cells**, **4,320
discovered native-test outcomes**, comprising **4,245 passes** and
**75 explicitly permitted optional skips**, and
**67 independently downloaded public assets**. The 30 cells share
the same source, release run and attempt. The original public-installer job
verifies the native wheel, version and default MCP/client dependencies.
Skips are recorded separately from passes.

- [audit.json](audit.json) contains all source, workflow, cell, receipt, log,
  public-asset and input hashes.
- [evidence-manifest.json](evidence-manifest.json) records the original archive
  digest and every file/part hash. All **116 files** are retained,
  including **97 original auditor inputs**.
- [evidence-parts](evidence-parts) contains **64 ordered parts** of at
  most 262,144 bytes. The complete archive is reconstructed only when needed;
  no duplicate full archive is stored here.
- [restore_evidence.py](restore_evidence.py) verifies parts, archive and all
  restored files before making a new output directory available.
- [restoration-verification.json](restoration-verification.json) records the
  successful byte-for-byte restoration and identical second audit.

The acquisition metadata and additional original collection responses, when
supplied by the collector, are preserved inside the archive. This audit checks
the consistency of acquired GitHub evidence. It is not an independently signed
attestation or a claim that native binaries were reproducibly rebuilt.

## Reproduce the offline audit

Restore to a new directory whose parent already exists:

```sh
python restore_evidence.py --output /absolute/path/to/restored-evidence
```

From a checkout containing the frozen auditor and validators at the published
source, with the native-baseline Git object available, run:

```sh
python -B scripts/audit_comprehensive_release.py \
  --evidence /absolute/path/to/restored-evidence \
  --repo-root /absolute/path/to/AI-Memory-Book \
  --source-commit 62508a1ce681111ec5702c88e3aa42f67b9fc9c0 \
  --version 0.12.0 \
  --runtime-sha256 2842f78c288454ea7348cb81cb6bd6a972cb26e003faaac64eb81f78b2ffa38b \
  --native-baseline 238c8058f723a203eaca99f94d924ab77de4c0b3 \
  --run-id 44275753685 \
  --run-attempt 1 \
  --output /absolute/path/to/new-audit.json
```

The output must not already exist. The auditor reads and checks the original
bytes; it performs no network requests, package installation or native execution.
