# v0.13 longitudinal experiment: independent run2 review

The candidate recovered complete required evidence for every answerable recall configuration in this frozen synthetic workload. Speed is mixed: 37 of 49 cold-result-cache groups and 7 of 49 warm-result-cache groups have a higher candidate pooled p50; all 14 directory-navigation groups have a lower candidate pooled p50. Missing-answer queries still return context. These results do not establish universal correctness, reliable abstention, or superiority over other products.

All numbers below are derived from the original ZIP and the unchanged, independently executed [saved-response auditor](audit_scale_zip_v2.py). The [complete audit JSON](scale-run2-saved-response-review.json), [source/archive binding](scale-run2-review-binding.json), and [review receipt](scale-run2-review-receipt.json) retain exact hashes and definitions. Run1 and its failed attempts remain separate evidence.

## Identity and integrity

| Item | Observed identity |
| --- | --- |
| Run / attempt | 44331778554 / 1 |
| GitHub artifact ID | 14439324717 |
| Candidate | e0e2515f6e16404cfb9b676cd2eab01ce84b81cc |
| Baseline | 8044e4bafe18e73ea422af5eeb47ef961e65246c |
| Frozen protocol commit | b3fd165cb632c439ff28873fdba7f33e9d258178 |
| Original ZIP bytes | 29,394,152 |
| Original ZIP SHA256 | 47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac |
| ZIP members / uncompressed bytes | 570 / 85,698,042 |
| Retained inventory files verified | 569 |
| Independent integrity checks | 166,409 |
| Original API measurements | 13,608 = 1,008 quality + 12,600 performance |
| Accepted arm blocks / original source references | 84 / 66,136 |
| New MemoryBook calls during this review | 0 |

The audit reconstructed source page IDs, source coordinates, frozen scores, navigation/read chains, sample schedules, medians, nearest-rank p95 values, and paired-round ratios. All 84 accepted blocks completed without missing calls, API errors, cache-mode mismatches or unindexed raw tails. The original records show every arm restored from its baseline snapshot and no overlapping measured worker processes. This saved-response review did not restore a database or rebuild the historical hosted binaries; native import paths and binary hashes were checked against the retained worker identities.

## Correctness: retain the denominators

| Metric | Baseline | Candidate |
| --- | --- | --- |
| Recall configurations | 448 | 448 |
| Complete answerable recall | 336/392 | 392/392 |
| Required recall evidence spans covered | 392/448 | 448/448 |
| Current-source-first recall | 80/168 | 112/168 |
| Recall with stale evidence before current | 32 | 0 |
| Missing-answer queries returning context | 56/56 | 56/56 |
| Complete directory navigation/read queries | 56/56 | 56/56 |
| Quality outputs with source errors | 0 | 0 |
| Performance calls with incomplete evidence | 840 | 0 |

There are 64 recall questions and 8 directory questions reused across seven checkpoints per arm, not 504 independent new questions. Of the 64 recall questions, 56 are answerable and 8 deliberately lack the requested answer. The 392/392 result is 56 answerable questions times seven checkpoints; it does not turn the 56 nonempty missing-answer outputs into successful abstentions.

All 56 baseline incomplete quality configurations are the eight multi-source questions repeated across the seven stages. They become complete in the candidate. All 56 candidate multi-source outputs retain required ranks `[2, 1]`: the boundary evidence is first and the current policy is second. Thus current-source-first remains 112/168, not 168/168. The 32 early stale-first current-question configurations improve; no previously complete answerable case becomes incomplete and no previously correct current-first case regresses under the frozen scoring criteria. The exact changed case IDs are retained in the binding JSON.

| Checkpoint | Real pages | Baseline complete | Candidate complete | Baseline current first | Candidate current first | Directory complete |
| --- | --- | --- | --- | --- | --- | --- |
| age-reference-1024 | 1,024 | 48/56 | 56/56 | 8/24 | 16/24 | 8/8 each |
| age-shift-1024 | 1,024 | 48/56 | 56/56 | 8/24 | 16/24 | 8/8 each |
| foreign-10016 | 10,016 | 48/56 | 56/56 | 8/24 | 16/24 | 8/8 each |
| foreign-50016 | 50,016 | 48/56 | 56/56 | 8/24 | 16/24 | 8/8 each |
| own-100000 | 100,000 | 48/56 | 56/56 | 16/24 | 16/24 | 8/8 each |
| interleaved-100000 | 100,000 | 48/56 | 56/56 | 16/24 | 16/24 | 8/8 each |
| replacement-100000 | 100,000 | 48/56 | 56/56 | 16/24 | 16/24 | 8/8 each |

The source checks found no cross-project source error in either arm. That is evidence of preserved isolation in the measured cases, not a new isolation advantage over the baseline. Original baseline failures remain in `quality_failures`, including archive member names, gzip offsets, byte counts and response hashes. The 840 baseline performance calls missing required multi-source evidence remain in the timing tables; correctness is not traded for a faster label.

## Growth, age and layout controls

| Checkpoint | Foreign pages | Additional target-history pages | Projects | Sessions | SQLite snapshot bytes |
| --- | --- | --- | --- | --- | --- |
| age-reference-1024 | 896 | 0 | 22 | 156 | 4030464 |
| age-shift-1024 | 896 | 0 | 22 | 156 | 4030464 |
| foreign-10016 | 9888 | 0 | 163 | 437 | 36171776 |
| foreign-50016 | 49888 | 0 | 788 | 1687 | 180170752 |
| own-100000 | 49888 | 49984 | 788 | 3249 | 381079552 |
| interleaved-100000 | 49888 | 49984 | 788 | 3249 | 384495616 |
| replacement-100000 | 49888 | 49984 | 788 | 3249 | 384495616 |

The corpus was built through actual MemoryBook.ingest calls with explicit turn segmentation. The initial target histories have 16 pages each; two inactive target histories remain fixed while six active or newcomer histories grow. The peak corpus has 100,000 pages across 788 exact projects. This is a deterministic synthetic engineering history, not a production trace, a default-adaptive-segmentation measurement, a million-page test, or a scale comparison with the historical external baselines. The optional 200,000-page profile was not executed.

The age pair uses fresh databases with the same content and ingest order, shifting all source dates by 3,650 days. The layout pair preserves the final logical corpus and source IDs while changing physical ingest order. For each pair and each arm, all 72 evidence projections are unchanged. The replacement stage updates six source histories at fixed total size. The original control checks and fingerprints are retained in the audit and ZIP.

The fixed inactive project is not constant-cost as unrelated projects grow: its candidate directory-chain p50 rises from 0.7692 ms at 1,024 total pages to 1.5787 ms at 10,016 and 4.9298 ms at 50,016. Global FTS work and physical layout still matter.

| Case | Mode | Clustered baseline p50 ms | Clustered candidate p50 ms | Interleaved baseline p50 ms | Interleaved candidate p50 ms |
| --- | --- | --- | --- | --- | --- |
| routing-archive:current | cold-result-cache | 42.9783 | 46.8141 | 166.8983 | 102.4775 |
| routing-archive:historical | cold-result-cache | 24.5839 | 24.5602 | 133.2222 | 67.9124 |
| routing-archive:directory | uncached-directory | 157.3066 | 9.9580 | 159.1539 | 26.7068 |
| ranking-next:directory | uncached-directory | 257.9543 | 127.2897 | 264.4649 | 129.5896 |

The unchanged output projections do not imply equal performance across layouts. Both layouts are shown so the best contiguous-project result cannot hide the cost of an old project whose rows are interleaved with similar projects.

## Performance definitions and every group

The six arm orders are AB, BA, BA, AB, AB, BA. Each performance recall question has 30 cold-result-cache and 90 warm-result-cache samples per arm per checkpoint; each directory chain has 30 samples. The p95 is the nearest-rank empirical quantile. These are single-host observations, not confidence intervals or general service-level guarantees. Initialization, snapshot restoration, scoring and raw journaling are outside each API timer. A directory sample times the complete locator → section → source-read chain.

Cold means the recall-result cache was cleared before the call. It does not flush SQLite pager state, OS page cache or helper caches. Warm means a verified hit of the saved recall-result cache. Each paired-round ratio divides that round’s candidate median by its baseline median; the median of those six ratios is separate from the ratio of pooled p50 values.

| Mode | Groups | Pooled p50 faster / slower | Median paired p50 faster / slower | p95 faster / slower |
| --- | --- | --- | --- | --- |
| cold-result-cache | 49 | 12 / 37 | 14 / 35 | 22 / 27 |
| warm-result-cache | 49 | 42 / 7 | 42 / 7 | 40 / 9 |
| uncached-directory | 14 | 14 / 0 | 14 / 0 | 14 / 0 |

All seven warm groups with a higher candidate pooled p50 are `training-core:multi_source`, one at each checkpoint. Those baseline responses are incomplete and the candidate responses are complete; both timings are retained without treating unequal evidence quality as equivalent work. The largest cold pooled p50 ratio is approximately 1.564, so the candidate is not uniformly faster. Differences very close to 1 are reported as measured signs, not statistical significance claims.

### cold-result-cache

All groups are included. B = baseline, C = candidate. C/B below 1 means lower candidate latency; above 1 means higher latency. Times are milliseconds.

| Checkpoint | Case | n/arm | B p50 | C p50 | B p95 | C p95 | Pooled C/B | Median paired C/B | Candidate p50 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| age-reference-1024 | attention-next:replacement | 30 | 2.0443 | 2.0575 | 2.1857 | 2.1827 | 1.006463 | 1.008694 | higher |
| age-reference-1024 | ranking-next:chinese | 30 | 2.2648 | 2.2624 | 2.3631 | 2.3522 | 0.998933 | 0.998397 | lower |
| age-reference-1024 | routing-archive:current | 30 | 6.7263 | 10.5163 | 16.0263 | 20.4855 | 1.563455 | 1.555472 | higher |
| age-reference-1024 | routing-archive:historical | 30 | 1.4738 | 1.4875 | 1.5592 | 1.5221 | 1.009251 | 1.009712 | higher |
| age-reference-1024 | routing-core:current | 30 | 6.7577 | 10.4810 | 6.8562 | 10.9587 | 1.550965 | 1.553834 | higher |
| age-reference-1024 | routing-core:identifier | 30 | 1.5452 | 1.5529 | 1.7330 | 1.7649 | 1.004982 | 1.008897 | higher |
| age-reference-1024 | training-core:multi_source | 30 | 7.2352 | 11.3162 | 7.5952 | 11.6742 | 1.564047 | 1.561190 | higher |
| age-shift-1024 | attention-next:replacement | 30 | 2.0547 | 2.0591 | 2.1762 | 2.1694 | 1.002133 | 0.996350 | higher |
| age-shift-1024 | ranking-next:chinese | 30 | 2.2564 | 2.2643 | 2.7398 | 2.3914 | 1.003470 | 1.003510 | higher |
| age-shift-1024 | routing-archive:current | 30 | 6.7655 | 10.4865 | 16.0505 | 20.3407 | 1.549992 | 1.561061 | higher |
| age-shift-1024 | routing-archive:historical | 30 | 1.4818 | 1.4893 | 1.5428 | 1.5287 | 1.005115 | 1.003957 | higher |
| age-shift-1024 | routing-core:current | 30 | 6.7443 | 10.5126 | 6.9198 | 10.6497 | 1.558742 | 1.559975 | higher |
| age-shift-1024 | routing-core:identifier | 30 | 1.5547 | 1.5494 | 1.7119 | 1.7470 | 0.996575 | 0.997301 | lower |
| age-shift-1024 | training-core:multi_source | 30 | 7.2592 | 11.3151 | 7.5533 | 11.7451 | 1.558735 | 1.559698 | higher |
| foreign-10016 | attention-next:replacement | 30 | 7.5577 | 7.5412 | 8.0260 | 7.8870 | 0.997812 | 0.996690 | lower |
| foreign-10016 | ranking-next:chinese | 30 | 5.8746 | 5.9272 | 6.0011 | 6.1262 | 1.008947 | 1.010164 | higher |
| foreign-10016 | routing-archive:current | 30 | 9.9540 | 13.6895 | 19.4430 | 23.8533 | 1.375274 | 1.376895 | higher |
| foreign-10016 | routing-archive:historical | 30 | 3.6879 | 3.6946 | 3.8547 | 3.8031 | 1.001837 | 1.001887 | higher |
| foreign-10016 | routing-core:current | 30 | 9.9636 | 13.7045 | 10.2681 | 14.1428 | 1.375451 | 1.374697 | higher |
| foreign-10016 | routing-core:identifier | 30 | 4.2688 | 4.2694 | 4.8041 | 4.6138 | 1.000138 | 1.000571 | higher |
| foreign-10016 | training-core:multi_source | 30 | 9.5157 | 13.5708 | 10.2744 | 14.0804 | 1.426142 | 1.423244 | higher |
| foreign-50016 | attention-next:replacement | 30 | 28.1523 | 28.1908 | 29.3734 | 29.3672 | 1.001364 | 1.000356 | higher |
| foreign-50016 | ranking-next:chinese | 30 | 13.8781 | 13.8801 | 14.1973 | 14.2809 | 1.000139 | 0.998162 | higher |
| foreign-50016 | routing-archive:current | 30 | 21.9719 | 25.7426 | 32.0201 | 36.6137 | 1.171616 | 1.170944 | higher |
| foreign-50016 | routing-archive:historical | 30 | 11.0231 | 11.0283 | 11.3289 | 11.2423 | 1.000471 | 1.003633 | higher |
| foreign-50016 | routing-core:current | 30 | 22.0995 | 25.8927 | 23.1665 | 29.0618 | 1.171642 | 1.165731 | higher |
| foreign-50016 | routing-core:identifier | 30 | 14.1752 | 14.2382 | 15.3783 | 14.7776 | 1.004445 | 1.002660 | higher |
| foreign-50016 | training-core:multi_source | 30 | 17.0103 | 21.0750 | 17.9816 | 21.7147 | 1.238953 | 1.240634 | higher |
| own-100000 | attention-next:replacement | 30 | 222.8211 | 223.8569 | 227.1288 | 226.0921 | 1.004648 | 1.003592 | higher |
| own-100000 | ranking-next:chinese | 30 | 164.3650 | 162.9954 | 168.7087 | 166.1839 | 0.991668 | 0.991534 | lower |
| own-100000 | routing-archive:current | 30 | 42.9783 | 46.8141 | 52.6526 | 57.0011 | 1.089249 | 1.089158 | higher |
| own-100000 | routing-archive:historical | 30 | 24.5839 | 24.5602 | 25.5530 | 25.5873 | 0.999035 | 0.992676 | lower |
| own-100000 | routing-core:current | 30 | 325.2124 | 331.3628 | 333.5485 | 335.9897 | 1.018912 | 1.014963 | higher |
| own-100000 | routing-core:identifier | 30 | 163.7912 | 164.0075 | 169.2043 | 166.1624 | 1.001320 | 1.002110 | higher |
| own-100000 | training-core:multi_source | 30 | 280.7814 | 288.1761 | 292.7512 | 290.0475 | 1.026336 | 1.025175 | higher |
| interleaved-100000 | attention-next:replacement | 30 | 227.6266 | 227.8923 | 230.9257 | 231.2895 | 1.001167 | 1.001712 | higher |
| interleaved-100000 | ranking-next:chinese | 30 | 167.1615 | 166.1892 | 170.8684 | 168.7381 | 0.994184 | 0.996037 | lower |
| interleaved-100000 | routing-archive:current | 30 | 166.8983 | 102.4775 | 175.2180 | 113.1445 | 0.614012 | 0.614948 | lower |
| interleaved-100000 | routing-archive:historical | 30 | 133.2222 | 67.9124 | 134.9915 | 69.0782 | 0.509768 | 0.509942 | lower |
| interleaved-100000 | routing-core:current | 30 | 332.0618 | 338.3089 | 337.1343 | 341.4026 | 1.018813 | 1.016352 | higher |
| interleaved-100000 | routing-core:identifier | 30 | 166.4661 | 166.1774 | 169.7320 | 168.0137 | 0.998266 | 0.998729 | lower |
| interleaved-100000 | training-core:multi_source | 30 | 286.8683 | 294.0061 | 291.3475 | 297.5974 | 1.024882 | 1.024227 | higher |
| replacement-100000 | attention-next:replacement | 30 | 226.9887 | 230.0740 | 229.6588 | 251.9685 | 1.013592 | 1.011235 | higher |
| replacement-100000 | ranking-next:chinese | 30 | 165.7100 | 166.5849 | 168.1146 | 169.1646 | 1.005280 | 1.006627 | higher |
| replacement-100000 | routing-archive:current | 30 | 165.8886 | 102.3304 | 176.6963 | 112.6373 | 0.616862 | 0.615435 | lower |
| replacement-100000 | routing-archive:historical | 30 | 131.5384 | 67.7397 | 134.7191 | 70.1264 | 0.514980 | 0.514023 | lower |
| replacement-100000 | routing-core:current | 30 | 329.6534 | 337.1246 | 332.3569 | 346.2301 | 1.022664 | 1.024267 | higher |
| replacement-100000 | routing-core:identifier | 30 | 166.7085 | 166.4002 | 169.1992 | 169.2706 | 0.998150 | 0.997814 | lower |
| replacement-100000 | training-core:multi_source | 30 | 285.1522 | 294.1989 | 290.8213 | 301.3578 | 1.031726 | 1.030367 | higher |

### warm-result-cache

All groups are included. B = baseline, C = candidate. C/B below 1 means lower candidate latency; above 1 means higher latency. Times are milliseconds.

| Checkpoint | Case | n/arm | B p50 | C p50 | B p95 | C p95 | Pooled C/B | Median paired C/B | Candidate p50 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| age-reference-1024 | attention-next:replacement | 90 | 0.1620 | 0.1484 | 0.1963 | 0.1828 | 0.916100 | 0.912124 | lower |
| age-reference-1024 | ranking-next:chinese | 90 | 0.2194 | 0.1820 | 0.2567 | 0.2160 | 0.829827 | 0.832595 | lower |
| age-reference-1024 | routing-archive:current | 90 | 0.2035 | 0.1909 | 0.2458 | 0.2284 | 0.937903 | 0.931507 | lower |
| age-reference-1024 | routing-archive:historical | 90 | 0.1759 | 0.1646 | 0.2112 | 0.2002 | 0.935532 | 0.934069 | lower |
| age-reference-1024 | routing-core:current | 90 | 0.2021 | 0.1903 | 0.2367 | 0.2252 | 0.941360 | 0.944525 | lower |
| age-reference-1024 | routing-core:identifier | 90 | 0.1532 | 0.1407 | 0.1867 | 0.1776 | 0.918279 | 0.916671 | lower |
| age-reference-1024 | training-core:multi_source | 90 | 0.1897 | 0.2025 | 0.2248 | 0.2400 | 1.067134 | 1.070522 | higher |
| age-shift-1024 | attention-next:replacement | 90 | 0.1626 | 0.1481 | 0.1949 | 0.1807 | 0.911094 | 0.908079 | lower |
| age-shift-1024 | ranking-next:chinese | 90 | 0.2194 | 0.1819 | 0.2807 | 0.2183 | 0.828889 | 0.827793 | lower |
| age-shift-1024 | routing-archive:current | 90 | 0.2044 | 0.1914 | 0.2377 | 0.2269 | 0.936132 | 0.939672 | lower |
| age-shift-1024 | routing-archive:historical | 90 | 0.1758 | 0.1647 | 0.2077 | 0.1998 | 0.936705 | 0.934176 | lower |
| age-shift-1024 | routing-core:current | 90 | 0.2015 | 0.1906 | 0.2362 | 0.2248 | 0.945957 | 0.945774 | lower |
| age-shift-1024 | routing-core:identifier | 90 | 0.1538 | 0.1418 | 0.1886 | 0.1741 | 0.921652 | 0.917297 | lower |
| age-shift-1024 | training-core:multi_source | 90 | 0.1895 | 0.2018 | 0.2253 | 0.2405 | 1.065008 | 1.067986 | higher |
| foreign-10016 | attention-next:replacement | 90 | 0.1615 | 0.1472 | 0.1938 | 0.1859 | 0.911202 | 0.912738 | lower |
| foreign-10016 | ranking-next:chinese | 90 | 0.2184 | 0.1820 | 0.2524 | 0.2180 | 0.833513 | 0.832819 | lower |
| foreign-10016 | routing-archive:current | 90 | 0.2028 | 0.1908 | 0.2427 | 0.2226 | 0.940737 | 0.939353 | lower |
| foreign-10016 | routing-archive:historical | 90 | 0.1773 | 0.1666 | 0.2113 | 0.2009 | 0.940029 | 0.940513 | lower |
| foreign-10016 | routing-core:current | 90 | 0.2034 | 0.1916 | 0.2394 | 0.2236 | 0.942264 | 0.941629 | lower |
| foreign-10016 | routing-core:identifier | 90 | 0.1544 | 0.1416 | 0.1880 | 0.1730 | 0.917309 | 0.919758 | lower |
| foreign-10016 | training-core:multi_source | 90 | 0.1903 | 0.2052 | 0.2244 | 0.2408 | 1.078242 | 1.082461 | higher |
| foreign-50016 | attention-next:replacement | 90 | 0.1636 | 0.1486 | 0.2009 | 0.1827 | 0.908050 | 0.901138 | lower |
| foreign-50016 | ranking-next:chinese | 90 | 0.2200 | 0.1834 | 0.2583 | 0.2221 | 0.833886 | 0.830189 | lower |
| foreign-50016 | routing-archive:current | 90 | 0.2042 | 0.1914 | 0.2395 | 0.2298 | 0.937209 | 0.933577 | lower |
| foreign-50016 | routing-archive:historical | 90 | 0.1777 | 0.1658 | 0.2170 | 0.2040 | 0.932582 | 0.932560 | lower |
| foreign-50016 | routing-core:current | 90 | 0.2026 | 0.1913 | 0.2408 | 0.2716 | 0.944184 | 0.937620 | lower |
| foreign-50016 | routing-core:identifier | 90 | 0.1552 | 0.1418 | 0.1878 | 0.1765 | 0.913489 | 0.912754 | lower |
| foreign-50016 | training-core:multi_source | 90 | 0.1899 | 0.2023 | 0.2307 | 0.2371 | 1.065165 | 1.061165 | higher |
| own-100000 | attention-next:replacement | 90 | 0.1747 | 0.1573 | 0.2046 | 0.2019 | 0.900473 | 0.880870 | lower |
| own-100000 | ranking-next:chinese | 90 | 0.2376 | 0.1967 | 0.2739 | 0.2492 | 0.828045 | 0.847310 | lower |
| own-100000 | routing-archive:current | 90 | 0.2070 | 0.1944 | 0.2475 | 0.2301 | 0.939345 | 0.939300 | lower |
| own-100000 | routing-archive:historical | 90 | 0.1772 | 0.1671 | 0.2166 | 0.2056 | 0.942956 | 0.942538 | lower |
| own-100000 | routing-core:current | 90 | 0.2118 | 0.1924 | 0.2565 | 0.2438 | 0.908305 | 0.921760 | lower |
| own-100000 | routing-core:identifier | 90 | 0.1688 | 0.1484 | 0.2096 | 0.1978 | 0.879214 | 0.869746 | lower |
| own-100000 | training-core:multi_source | 90 | 0.1980 | 0.2106 | 0.2293 | 0.2455 | 1.063635 | 1.043998 | higher |
| interleaved-100000 | attention-next:replacement | 90 | 0.1737 | 0.1574 | 0.2131 | 0.1881 | 0.906016 | 0.927104 | lower |
| interleaved-100000 | ranking-next:chinese | 90 | 0.2335 | 0.1915 | 0.2793 | 0.2303 | 0.820014 | 0.816640 | lower |
| interleaved-100000 | routing-archive:current | 90 | 0.2155 | 0.1941 | 0.2488 | 0.2378 | 0.900716 | 0.906996 | lower |
| interleaved-100000 | routing-archive:historical | 90 | 0.1861 | 0.1698 | 0.2262 | 0.2186 | 0.912482 | 0.913524 | lower |
| interleaved-100000 | routing-core:current | 90 | 0.2088 | 0.1973 | 0.2462 | 0.2556 | 0.944632 | 0.930105 | lower |
| interleaved-100000 | routing-core:identifier | 90 | 0.1688 | 0.1562 | 0.2029 | 0.1874 | 0.925565 | 0.913659 | lower |
| interleaved-100000 | training-core:multi_source | 90 | 0.1915 | 0.2094 | 0.2329 | 0.2492 | 1.093338 | 1.081506 | higher |
| replacement-100000 | attention-next:replacement | 90 | 0.1706 | 0.1586 | 0.2072 | 0.2014 | 0.929987 | 0.893757 | lower |
| replacement-100000 | ranking-next:chinese | 90 | 0.2343 | 0.1911 | 0.2697 | 0.2287 | 0.815667 | 0.829987 | lower |
| replacement-100000 | routing-archive:current | 90 | 0.2099 | 0.1960 | 0.2512 | 0.2311 | 0.933938 | 0.932862 | lower |
| replacement-100000 | routing-archive:historical | 90 | 0.1836 | 0.1695 | 0.2262 | 0.2020 | 0.923179 | 0.934917 | lower |
| replacement-100000 | routing-core:current | 90 | 0.2122 | 0.1984 | 0.2522 | 0.2391 | 0.934902 | 0.927436 | lower |
| replacement-100000 | routing-core:identifier | 90 | 0.1650 | 0.1526 | 0.2079 | 0.1826 | 0.924963 | 0.910303 | lower |
| replacement-100000 | training-core:multi_source | 90 | 0.1927 | 0.2085 | 0.2419 | 0.2427 | 1.082030 | 1.095836 | higher |

### uncached-directory

All groups are included. B = baseline, C = candidate. C/B below 1 means lower candidate latency; above 1 means higher latency. Times are milliseconds.

| Checkpoint | Case | n/arm | B p50 | C p50 | B p95 | C p95 | Pooled C/B | Median paired C/B | Candidate p50 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| age-reference-1024 | ranking-next:directory | 30 | 1.5532 | 0.7878 | 1.7403 | 0.8463 | 0.507208 | 0.507876 | lower |
| age-reference-1024 | routing-archive:directory | 30 | 1.5367 | 0.7692 | 4.1758 | 3.7467 | 0.500574 | 0.501276 | lower |
| age-shift-1024 | ranking-next:directory | 30 | 1.5580 | 0.7773 | 1.7613 | 0.8484 | 0.498921 | 0.499116 | lower |
| age-shift-1024 | routing-archive:directory | 30 | 1.5385 | 0.7614 | 4.1343 | 3.7147 | 0.494885 | 0.499022 | lower |
| foreign-10016 | ranking-next:directory | 30 | 14.7934 | 1.5911 | 15.7219 | 1.7095 | 0.107555 | 0.107958 | lower |
| foreign-10016 | routing-archive:directory | 30 | 14.6778 | 1.5787 | 18.0372 | 4.6758 | 0.107557 | 0.107724 | lower |
| foreign-50016 | ranking-next:directory | 30 | 72.8902 | 4.9551 | 74.2771 | 5.3707 | 0.067981 | 0.067650 | lower |
| foreign-50016 | routing-archive:directory | 30 | 72.4150 | 4.9298 | 75.4447 | 8.2040 | 0.068077 | 0.068049 | lower |
| own-100000 | ranking-next:directory | 30 | 257.9543 | 127.2897 | 264.1468 | 129.6854 | 0.493458 | 0.493014 | lower |
| own-100000 | routing-archive:directory | 30 | 157.3066 | 9.9580 | 161.9905 | 13.7706 | 0.063303 | 0.062859 | lower |
| interleaved-100000 | ranking-next:directory | 30 | 264.4649 | 129.5896 | 268.2618 | 131.0966 | 0.490007 | 0.490080 | lower |
| interleaved-100000 | routing-archive:directory | 30 | 159.1539 | 26.7068 | 163.4956 | 30.7495 | 0.167805 | 0.168230 | lower |
| replacement-100000 | ranking-next:directory | 30 | 263.0658 | 128.9236 | 265.6809 | 134.1989 | 0.490081 | 0.491012 | lower |
| replacement-100000 | routing-archive:directory | 30 | 158.1085 | 26.6167 | 162.2982 | 30.8237 | 0.168344 | 0.167465 | lower |

## Host and resource boundary

Host: AMD EPYC 7763 64-Core Processor, 4 logical CPUs, Linux-7.0.0-1017-azure-x86_64-with-glibc2.39; Python 3.12.16 (main, Oct 26 2026, 02:50:49) [GCC 13.3.0]; SQLite 3.45.1. The workflow uses Ubuntu 24.04. The measurement manifest started at 2026-11-18T15:06:53.475154+00:00 and last saved at 2026-11-18T15:21:25.488749+00:00; that interval includes construction, restoration and orchestration, so it is not a per-query latency measurement.

| Arm | Worker processes | Minimum lifetime peak RSS MiB | Maximum lifetime peak RSS MiB |
| --- | --- | --- | --- |
| baseline | 42 | 34.918 | 56.898 |
| candidate | 42 | 36.996 | 56.898 |

RSS is a worker process lifetime high-water mark, not isolated per-call memory allocation. Round 0 also executes 72 quality calls before its timed work; later rounds do not. SQLite snapshot sizes appear above, and worker storage/initialization records remain in the full audit JSON. The saved-response review checks the recorded restoration hashes; it does not independently restore excluded database snapshots.

Run1 used an Intel Xeon host, while this run uses AMD EPYC. Performance benefits here are computed only against the baseline paired within run2. Absolute run1-to-run2 latency changes are not attributed to the candidate. Run2 was executed after inspecting run1 failures and developing fixes; the protocol and gold stayed frozen, but the workload is no longer unseen. Older 38/62-question, engineering, short-page, directory-contract, CI and external-library results retain their separate sources and denominators.

## Reproduce the saved-record audit

Obtain the exact original ZIP matching the SHA256 above, then run the frozen auditor with these arguments. This command reads saved records and does not execute retrieval:

```sh
python benchmarks/reports/v0.13-development/scale-run2-review/audit_scale_zip_v2.py \
  --repo-root /path/to/AI-Memory-Book \
  --archive /path/to/original-artifact-44331778554-1.zip \
  --output /path/to/new-independent-review.json \
  --expected-zip-sha256 47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac \
  --run-id 44331778554 --run-attempt 1 \
  --candidate e0e2515f6e16404cfb9b676cd2eab01ce84b81cc
```

The output path must be new: the auditor deliberately refuses to overwrite a previous report. The frozen source commits must be available locally, and the registered protocol/score files must retain their recorded bytes.
