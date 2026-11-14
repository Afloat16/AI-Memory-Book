# C5 complete native development evidence

This is the sole registered 18,928-call C5 development comparison against published v0.3.2. The saved-data audit verifies the complete observations and outputs. **It is not release acceptance.** The original formal matrix, actual MCP timing, RSS review and all numerical gates still have to pass.

## Decision boundary

All eight pooled native cells improve in mean, p50 and p95. The eight-cell development geometric p95 improvement is **13.4297046175%**. Public token512/token1024/token2048 pooled p95 improvements are **11.1410534215% / 14.1447460172% / 11.3644353178%**. The best remains **0.8552539828 percentage points below** the fixed formal public-native-token target of 15%. These two-round development figures neither pass nor replace the four-round, twelve-cell formal gates.

There is one adverse per-round metric: public1015 native-char4000 round 1 p95 rises from **2.7076633 ms to 2.7507467 ms (+1.5911653417%)**. It is retained in the tables, JSON summary and raw samples. Public token1024 round p95 gains also differ substantially: 18.492957% and 9.277594%. No source was rerun to select a favorable sample, and no sample was dropped.

## Sources and complete checks

| Source | Commit | Runtime SHA256 |
|---|---|---|
| baseline | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| candidate | `8dc6604fa32df18d53286110b215fc6657243656` | `6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be` |

Development helper SHA256: `377cf71ecfac391a3e1a203bdcaa6a04d72439306962a7c9640648142a8cbda0`.
Registered development-plan SHA256: `53ffcf7b605ce33616208eadc095008c046fd7e20fb89998f07682f9bb31e989`.
C5 addendum SHA256: `3329b2605103e2e52623fd8b463dc551f39ab4d3697b438c41d5cf1cc193d170`.
Original aggregate JSON SHA256: `c7e8150a286d5bd50c082b87cdcdf19e1d74844ae86bc8ea16f9988c9afa0a26`.

- Eight complete workers; synthetic61 has all 168 original queries and public1015 all 1,015, with four native configurations and both AB/BA rounds.
- All 18,928 timing samples are finite and positive. Every fixed query ID, deterministic shuffled order and per-worker invariant count was checked.
- All 9,464 baseline/candidate complete payload-digest pairs match. The sole excluded product response field is latency_ms; recorded token, character, cache and revision checks all pass.
- Source/index/revision projections remain unchanged within every worker and identical across sources for each cohort. Query-result cache stays empty.
- Original aggregate and individual worker JSON objects agree exactly. All nine JSON files were compressed without changing any uncompressed byte.
- The offline audit performs no retrieval, encoding, test or timing run. Its standard-library code is retained as audit_saved.py and c5_development_memo_verifier.py. The memo verifier function is copied unchanged from the independent C5 auditor; function SHA256 is `70bf9a89d386d5caf7960e6a4f0f81a3bfefb26627066882799de0d4d7773648`.

## Complete pooled results

Changes are `(C5 / baseline - 1) × 100`; negative values mean lower latency. Each synthetic cell has 336 observations per source; each public cell has 2,030. Statistics use every saved row and linear quantiles at `(N - 1) × q`. Full-precision values are in summary.json.

| Cohort | Configuration | p50 ms, baseline → C5 | p50 change | p95 ms, baseline → C5 | p95 change | Mean ms, baseline → C5 | Mean change |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 3.007167 → 2.872990 | -4.461908% | 9.292029 → 8.706858 | -6.297562% | 3.891064 → 3.626211 | -6.806688% |
| synthetic61 | native-token512 | 5.887977 → 4.574210 | -22.312704% | 15.014993 → 12.529839 | -16.551147% | 7.036241 → 6.189138 | -12.039134% |
| synthetic61 | native-token1024 | 4.845989 → 3.336762 | -31.143836% | 15.387471 → 10.810789 | -29.742908% | 6.046616 → 4.253720 | -29.651229% |
| synthetic61 | native-token2048 | 3.651340 → 3.122891 | -14.472767% | 13.021087 → 11.248996 | -13.609390% | 5.079753 → 4.420792 | -12.972308% |
| public1015 | native-char4000 | 2.072719 → 2.019014 | -2.591041% | 2.722016 → 2.675702 | -1.701438% | 2.166221 → 2.113866 | -2.416917% |
| public1015 | native-token512 | 3.268318 → 2.523073 | -22.802108% | 4.226405 → 3.755539 | -11.141053% | 3.433684 → 2.787833 | -18.809264% |
| public1015 | native-token1024 | 2.697861 → 2.356112 | -12.667406% | 3.565483 → 3.061155 | -14.144746% | 2.850298 → 2.450255 | -14.035129% |
| public1015 | native-token2048 | 2.593438 → 2.270517 | -12.451462% | 3.243871 → 2.875224 | -11.364435% | 2.677737 → 2.334668 | -12.811905% |

## Every per-round result

| Cohort | Configuration | Round | p50 ms, baseline → C5 | p50 change | p95 ms, baseline → C5 | p95 change | Mean ms, baseline → C5 | Mean change |
|---|---|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 0 | 3.099465 → 2.886871 | -6.859086% | 9.696336 → 8.885350 | -8.363834% | 4.008906 → 3.641215 | -9.171847% |
| synthetic61 | native-char4000 | 1 | 2.938549 → 2.852353 | -2.933251% | 8.876031 → 8.407291 | -5.280956% | 3.773223 → 3.611208 | -4.293797% |
| synthetic61 | native-token512 | 0 | 5.917047 → 4.617521 | -21.962416% | 15.227290 → 12.745538 | -16.298052% | 7.003000 → 6.386717 | -8.800270% |
| synthetic61 | native-token512 | 1 | 5.825489 → 4.496564 | -22.812250% | 14.599140 → 12.086167 | -17.213160% | 7.069482 → 5.991560 | -15.247540% |
| synthetic61 | native-token1024 | 0 | 4.804907 → 3.395446 | -29.333794% | 15.373818 → 10.792614 | -29.798739% | 6.147303 → 4.288870 | -30.231677% |
| synthetic61 | native-token1024 | 1 | 4.920896 → 3.267508 | -33.599335% | 15.409826 → 10.798709 | -29.923229% | 5.945928 → 4.218569 | -29.051123% |
| synthetic61 | native-token2048 | 0 | 3.609558 → 3.365906 | -6.750189% | 12.855674 → 11.503507 | -10.518057% | 5.087557 → 4.657109 | -8.460808% |
| synthetic61 | native-token2048 | 1 | 3.669272 → 2.994357 | -18.393703% | 13.125257 → 10.879611 | -17.109352% | 5.071949 → 4.184475 | -17.497691% |
| public1015 | native-char4000 | 0 | 2.067973 → 1.990226 | -3.759575% | 2.732551 → 2.617712 | -4.202641% | 2.196244 → 2.132345 | -2.909492% |
| public1015 | native-char4000 | 1 | 2.084778 → 2.046440 | -1.838949% | 2.707663 → 2.750747 | +1.591165% | 2.136198 → 2.095386 | -1.910497% |
| public1015 | native-token512 | 0 | 3.243111 → 2.523358 | -22.193289% | 4.226085 → 3.913261 | -7.402204% | 3.473909 → 2.850420 | -17.947772% |
| public1015 | native-token512 | 1 | 3.291494 → 2.522727 | -23.356172% | 4.222782 → 3.657695 | -13.381872% | 3.393459 → 2.725247 | -19.691179% |
| public1015 | native-token1024 | 0 | 2.679823 → 2.324478 | -13.260018% | 3.608902 → 2.941510 | -18.492957% | 2.826036 → 2.395877 | -15.221271% |
| public1015 | native-token1024 | 1 | 2.717230 → 2.399472 | -11.694189% | 3.503721 → 3.178660 | -9.277594% | 2.874561 → 2.504633 | -12.869011% |
| public1015 | native-token2048 | 0 | 2.533754 → 2.296046 | -9.381653% | 3.099487 → 2.927484 | -5.549390% | 2.644600 → 2.389647 | -9.640506% |
| public1015 | native-token2048 | 1 | 2.659733 → 2.242415 | -15.690222% | 3.349223 → 2.816711 | -15.899546% | 2.710874 → 2.279689 | -15.905772% |

## Native memo state and limits

All four candidate connections start with an unallocated, empty memo. Character recalls leave it unallocated. Native token512 therefore starts empty; later native token configurations retain the same book’s naturally accumulated counts. Before/after-first-call/after observations have continuous state between configurations and monotone cumulative counters. The first queries remain included in every applicable latency statistic. Baseline observations explicitly state that the new memo does not exist.

Every recorded candidate snapshot respects the fixed 2,048-entry and 2,097,152-byte retained-text-object limits. The maximum observed retained text size is 1,749,265 bytes; public workers reach the 2,048-entry cap and record real LRU evictions. These observations are snapshots, not a continuous allocation trace. Container/key/value/encoder overhead and process RSS are outside this text-object cap. This development helper does not measure total RSS or actual MCP latency.

| Candidate worker | Final entries | Final text-object bytes | Hits | Misses | Evictions | Uncertified bypasses |
|---|---:|---:|---:|---:|---:|---:|
| synthetic61-0-candidate | 1117 | 1749265 | 2314 | 1117 | 0 | 3995 |
| synthetic61-1-candidate | 1117 | 1749265 | 2314 | 1117 | 0 | 3995 |
| public1015-0-candidate | 2048 | 1513152 | 13206 | 3319 | 1271 | 12132 |
| public1015-1-candidate | 2048 | 1518772 | 13189 | 3336 | 1288 | 12132 |

Final invalidation and oversized-bypass counters are zero in all four candidate workers. Counts describe memo operations, not numbers of queries. Full before/first/after records and all 32 first-query timings are preserved in summary.json; they do not establish cold-OS latency or MCP hit rates.

## Evidence and reproduction

- `manifest.json.gz` preserves the original aggregate JSON bytes.
- Eight `COHORT-ROUND-SOURCE.json.gz` files preserve each original worker JSON.
- `summary.json` contains every pooled and per-round statistic, every adverse metric, complete-count checks, memo observations and interpretation limits.
- `receipt.json` records compressed and uncompressed hashes plus every archived file checksum except its own.
- `audit_saved.py` and `c5_development_memo_verifier.py` reproduce the offline checks using only saved rows. Run from the repository root with a new, nonexistent output directory; existing evidence is never overwritten.

```bash
python benchmarks/reports/round5-development/candidate-c5-full/audit_saved.py \
  --root . \
  --manifest benchmarks/reports/round5-development/candidate-c5-full/manifest.json.gz \
  --state-dir benchmarks/reports/round5-development/candidate-c5-full \
  --archive-dir .artifacts/c5-saved-data-reproduction
```

The repository must contain the frozen helper/registration/plan and the preserved C3 run.json used only to verify the original query IDs. Reproduction reads the archived data; it never starts another benchmark.

This comparison uses old regression questions on one local host. It supports exact compatibility and observed native improvement on that workload; it does not establish statistical significance, generalization, fresh-question quality or a new competitor advantage.
