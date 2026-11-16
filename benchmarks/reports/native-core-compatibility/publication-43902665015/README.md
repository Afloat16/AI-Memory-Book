# v0.9.0 final publication verification

**Passed.** [v0.9.0](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.9.0) is a published formal release and is Latest. The actual public default installer completed successfully with the native backend and `mcp` / `clients` extras.

- Final main and direct tag commit: `238c8058f723a203eaca99f94d924ab77de4c0b3`.
- Tree: `0a608bf9b28679e4f718a34d5546696346427179`.
- Runtime SHA256: `6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7`, unchanged from the formally measured compatibility candidate.
- [Release workflow 43902665015](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43902665015), attempt 1: eight successful jobs; prepare-only correctly skipped.
- Publication notes bind the actual [11-job CI 43902664791](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43902664791) on this exact commit.
- Final artifact `14244153824`: 9,654,024 bytes, SHA256 `8c87689bd8385bfe94355c55231946fe9553638b37c621531554b5136ccfe724`.

## Fresh installed native matrix

All five platform jobs executed six separate interpreter setup/build/install/test steps in this final run and attempt. Each cell reported 144 testcase outcomes with an **OK suite result**. This matrix was rebuilt from the final commit; no wheel or receipt from the preparation run was reused.

| Platform | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 | 3.15 |
| --- | --- | --- | --- | --- | --- | --- |
| linux_x86_64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| linux_aarch64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| macos_x86_64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| macos_arm64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |
| windows_amd64 | 142 passed / 2 skipped | 142 passed / 2 skipped | 142 passed / 2 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped | 141 passed / 3 skipped |

The 30 environments report **4,320 testcase outcomes: 4,245 passed and 75 skipped**. Skipped cases are not counted as executed tests. Only the two exact optional-token testcases with `Install .[tokens]`, and the optional original shared-GIL subinterpreter testcase with `_xxsubinterpreters is not available in this Python build`, are accepted as skips. Every count and reason is read from its original cell log.

## Public assets and installation

The final ZIP contains 67 release assets plus the generated release notes. All 65 manifest payload records and 66 checksums match their bytes. The complete native/fallback wheel RECORD inventories, package/source bytes, metadata, native identities and source distribution inputs were independently checked in RAM. Every one of the 67 public asset API SHA256 digests and sizes matches the corresponding audited artifact bytes.

The successful pinned publisher additionally downloaded and hashed every remote asset before and after publication. This audit does not claim a second independent download of all 67 public assets. It independently verifies their API digests, final identity, actual publication completion log, and the successful public installer job `133434569312`.

All 30 original native receipts, compiler logs, installed test logs and source inventories bind the same final commit/tree/run/attempt. Five original cell-evidence ZIPs, containing 246 log/validation files, were retained on the first RAM read and saved unchanged before the audit process exited. No native wheel binaries were committed by this audit, and no application tests or performance measurements were rerun.

## Durable evidence

- [Compact summary and each cell's hashes](summary.json)
- [Final archive audit and the exact auditor source](artifact-audit.json)
- [Actual jobs, 30 cell tests and compiler/log bindings](jobs-and-cell-tests.json)
- [Public release, 67 API asset digests, refs and exact publication CI](public-release.json)
- [Original release manifest](release-manifest.json)
- [Original generated release notes](release-notes.md)
- [Raw evidence artifact and Git blob mapping](raw-cell-evidence-retention.json)
