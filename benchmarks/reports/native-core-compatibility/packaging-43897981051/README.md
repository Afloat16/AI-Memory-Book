# Native v0.9.0 grouped wheel preparation

**Passed, prepare only.** No release was published by this run.

- Run: [43897981051, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43897981051).
- Source commit: `ba1bcef8d4fcf325a3403c2ff9c540312c491464`; tree: `f28f9d6847e671dd484a705c1e465e93e927cc58`.
- Runtime SHA256: `6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7`, unchanged from the formally measured compatibility candidate.
- Combined artifact: `14240632443`, 9,643,315 bytes, SHA256 `070ce0c4976f2768f7d72dd8b3ca991fd3844d8e3054c47238161dbf69d5cb43`.

Five platform jobs each executed six separate setup/build/install/test steps. The audit verifies all 30 actual steps, their interpreter identities, raw compiler and test logs, original native receipts, and exact source/run/attempt. Each platform artifact contains exactly six wheel/receipt pairs; evidence logs are separate from the release assets.

## Actual installed tests

Every cell completed the same 144 existing native test methods successfully. Counts below come from that cell's original test log, not from a fixed assumption about its Python version.

| Platform | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 | 3.15 |
| --- | --- | --- | --- | --- | --- | --- |
| linux_x86_64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| linux_aarch64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| macos_x86_64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| macos_arm64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| windows_amd64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |

Across the 30 environments: **4,320 test executions, 4,245 passed, 75 skipped**. These totals count repeated execution of the same tests across platforms. The two mandatory skips are the existing optional-token tests with the exact `Install .[tokens]` reason. The only permitted third skip is the existing shared-GIL subinterpreter testcase with the exact `_xxsubinterpreters is not available in this Python build` reason. No other skipped testcase or reason is accepted by the independent audit.

## Asset and installer checks

The combined ZIP contains 67 assets and the original installation validation report. All 65 manifest payload records and 66 checksums match the actual bytes. All 30 native wheels and the Python fallback have their complete RECORD inventories, package metadata, runtime source bytes and native binary identities independently verified in RAM. The source distribution matches the same committed build inputs.

The actual preparation job installed both native and fallback selections with default `mcp` and `clients` extras. Their observed backends were respectively `native` and `python`; all four original package checks passed. No ZIP, wheel or source distribution was written to disk by the independent audit.

## Evidence

- [Summary and per-cell hashes](summary.json)
- [Archive audit and exact auditor source](artifact-audit.json)
- [Actual jobs, all 30 cell tests and compiler/log bindings](jobs-and-cell-tests.json)
- [Original installation validation](native-packaging-validation.json)
- [Original release manifest](release-manifest.json)
- [Original per-platform compiler/test logs](raw-cell-evidence/), preserved as five unchanged ZIPs (364,720 bytes total)
- [Raw-log preservation receipt](raw-cell-evidence-retention.json), binding each Git blob to the already-audited artifact digest

The preliminary read-only parser's incorrect assumption that every cell had two skips is retained in [the correction record](../development/native-core-grouped-audit-skip-correction.json). The correction accepts only the specific pre-existing third skip above; application code, tests, the 144-test gate, and workflow attempt were unchanged, and no application test was rerun for that correction. The three preceding interrupted runner attempts are preserved separately; their successful subsets were not reused here.

A formal release still requires the final committed approval, all 11 exact-commit CI jobs, a fresh complete same-attempt wheel matrix, publication asset verification, and the actual public installer check.
