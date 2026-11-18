# Independent v0.13 source acceptance and presentation review

**Result: the reviewed source decision is supported within its stated scope; final delivery remains pending.**

This record reviews commit `8f889647b159ec8078952b42cb0402d2ec583154`. It does not run retrieval, performance, a test suite, database restoration, package builds or publication. The measured runtime remains `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc`. This is a source and saved-evidence review, not proof that every project goal has been achieved.

The later remote checkpoint `4977ebc13e9da10a8fa4cb95f39e2c533aabe790` preserves every reviewed document, runtime and accepted evidence file byte-for-byte. Its only additions/changes are generator source-recovery records; it does not change the measurements or delivery status.

## Source and evidence binding

- All **8** evidence files named by the source acceptance record match their stored byte counts and SHA-256 values, including the original ZIP manifest and restoration receipt read directly from Git.
- All **4** protocol files remain byte-identical to freeze `b3fd165cb632c439ff28873fdba7f33e9d258178`.
- All **29** tracked runtime files, including the reader asset, equal the measured source. The release digest includes **28** `.py/.c/.h/.rs` files and recomputes to `a7492a74a94170b87a2fd54ada421866b9d737f46dce2ff3a3bc21d6debb9da1`. The six native C/header files equal baseline `8044e4bafe18e73ea422af5eeb47ef961e65246c`.
- Package and installer versions, schema 4, recall-cache version 26, native-release registration and release-channel registration agree. The existing 71-test release-contract log is hash-verified at its original source `210ec272675b5357f658d994e91d902eb269a924`; reviewed release code and fixtures match that tested source. Those tests were **not rerun** and are not native-delivery evidence.
- The earlier final-source legacy audit remains a **4,716-check** record for `91412b438a0da95549cc9a3b85eccb4915359a2d`. Its complete Git tree equals the measured remote source; the old record is not relabelled as a new execution.

## Independent saved-presentation checks

The complete original run-2 ZIP hash is `47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac`. The existing full saved-response audit remains `87e57eda285804f3a358baf7d16e9b82876f4dd40c1b3f73d0715b12635755cb`, with 166,409 checks. This review adds no new runtime calls and does not replace that audit.

The renderer source hash `96051fa0c32c53ac325f436fa46b4ef403475c0b6496c2db45eb6e97cdaf92c6` and all **16** derived artifact hashes match. Every **12,600** timing row and **1,008** quality row was independently matched to its original compact ZIP observation, including source-response pointers/hashes and completeness fields. The original compact files and 84 worker results were checked against the retained ZIP inventory.

All **112** groups' wall/CPU quantiles, all **672** paired round records, **84** resource records and **21** resource cohorts were independently recomputed or compared. Sample counts are 30 cold, 90 warm and 30 full-directory observations per query/arm/checkpoint; p95 uses nearest rank. The same wall/CPU statistics agree with the earlier independent raw-response audit. No slower group or incomplete baseline response was discarded.

| Mode | Groups | Pooled p50 faster / slower | Median paired p50 faster / slower | P95 faster / slower |
| --- | ---: | ---: | ---: | ---: |
| Cold-result-cache recall | 49 | 12 / 37 | 14 / 35 | 22 / 27 |
| Warm-result-cache recall | 49 | 42 / 7 | 42 / 7 | 40 / 9 |
| Complete directory/read chain | 14 | 14 / 0 | 14 / 0 | 14 / 0 |

All **840** incomplete baseline performance responses remain in the timing data; the candidate has zero such failures under the frozen scoring. Baseline/candidate complete answerable configurations remain **336/392 versus 392/392**. Candidate current-first is **112/168**, and all **56/56** missing-answer configurations still return context. Repeated checkpoints are not independent new questions.

The resource display separates six worker high-water values from per-call resources. At the small reference checkpoint, baseline/candidate medians are **35.283/37.100 MiB**, while maxima are **41.547/40.297 MiB**. Round zero includes 72 additional quality calls per worker. The renderer owner's separate visual inspection is not represented as a new independent visual certification here.

## Corrected wording

Three findings were resolved before this record: the release notes now distinguish paired summaries from the separately linked 672 individual records; the validation document distinguishes median-of-six RSS from group maxima; and the multi-source paragraph clearly states incomplete baseline versus complete candidate without reversing which arm became slower.

## What this acceptance supports

The recorded experiment supports improved evidence completeness on the frozen authored workload, preserved measured source/project isolation and legacy contracts, and faster complete directory navigation in the measured 14 groups. It also supports selected warm and interleaved archived-project gains. The retained cold-recall costs are explicitly accepted, with accuracy and completeness taking priority.

It does **not** establish uniform performance gains, constant old-project response time as unrelated history grows, universal memory reduction, reliable abstention, complete authority/conflict resolution in arbitrary prose, unseen production accuracy, LLM answer quality, a 200k/million-page execution or superiority over every open-source product. External comparison pins remain historical and were not run at 100k. Run 2 is a post-diagnosis retest of the same frozen questions, not an independent holdout; its host differs from run 1, so absolute cross-run timing is not a paired comparison.

## Delivery boundary

The reviewed deployment and validation text explicitly describes v0.13 release preparation. The following remain separate gates: the exact eventual release-source commit's 11 CI jobs; that source on main; all 30 native cells and package checks; a real public-URL installer in the same complete release attempt; and an independent, restorable audit of original delivery evidence. No v0.12 delivery count is reused as v0.13 proof.

The detailed machine-readable record is [source-acceptance-review.json](source-acceptance-review.json), SHA-256 `940fa316b42d6efd56ded1e18fcf9d772c3085ffdd1ca0ff18e8a0b1ba818ca2`. It binds every reviewed document, runtime file and referenced evidence item, and labels the assertions as saved-evidence checks rather than tests or new measurements.
