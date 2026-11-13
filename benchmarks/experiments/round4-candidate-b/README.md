# Rejected candidate B: bounded indexed-body features

The complete candidate and its original tests are preserved at
`ec45162a41d65b43c142fac6193f3f412617d406`. Its runtime SHA-256 is
`f4d5471df44d8d04e13581e971d6d53d885919caea9f80a5a0a4ddcbc088f122`.

All 18 correctness fixtures passed. The development profiles and sequential
paired diagnostic also preserved complete payload equality, but public
token512 p95 regressed by 11.82%. Candidate B was not selected for release;
no formal measurement or fresh quality scoring was used to make this choice.

`index_features_fixture.py` is a byte-for-byte copy of its original
`tests/test_round4_index_features.py` (SHA-256
`4b7911a2de13ef76bb4af6cf27385d70a539e81087da8e3aba2ec8961fac7ddf`).
It requires the candidate B runtime and is intentionally outside current
test discovery. To reproduce it, use the original committed checkout and
its normal `PYTHONPATH=src` unittest command. The final candidate removes the
feature cache; the exact highlight read has separate active fixtures.

Evidence manifests are under `benchmarks/reports/round4-development/`:
`candidate-b-manifest.json` and `candidate-b-paired-manifest.json`. They retain
every diagnostic cell and compressed sample, including regressions. Original
formal acceptance thresholds remain unchanged.
