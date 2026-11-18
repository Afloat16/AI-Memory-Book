# v0.13 longitudinal run 2: performance and resource review

Run **44331778554/1** compares `8044e4bafe18e73ea422af5eeb47ef961e65246c` with `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc` on the same hosted runner. All statistics below come from this run; run-1 absolute times are not used as paired evidence.

## Evidence and interpretation

The original ZIP SHA256 is `47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac`. The independent saved-response audit (`87e57eda285804f3a358baf7d16e9b82876f4dd40c1b3f73d0715b12635755cb`) passed 166,409 checks. This renderer separately reconstructs all group quantiles and paired ratios from compact original observations and checks them against both saved summaries and the independent audit. It makes zero MemoryBook API calls and restores no database.

There are 84 arm blocks, 12,600 timed calls, and 1,008 separate quality calls across seven checkpoints. These repeat an authored fixture; they are not 13,608 independent real-user questions. Cold clears only the result cache. Directory time includes discovery, section navigation and original-page reads. Quantiles are empirical, not confidence intervals or service guarantees.

Candidate recall evidence is complete for 56/56 answerable cases at every checkpoint; baseline is 48/56. Candidate current-source-first remains 16/24, and all 8 missing-evidence queries still return nonempty context. Across the seven correlated checkpoints these are 392/392 versus 336/392 complete, 112/168 versus 80/168 current-first, and 56/56 nonempty missing-evidence outputs in each arm. Completeness does not imply universal answerability, abstention or first-source correctness.

## All group directions

Direction counts include arbitrarily small differences and are not significance tests. Paired medians and pooled medians answer different statistical questions.

| Mode | Groups | Pooled p50 faster / slower | Pooled p95 faster / slower | Median paired p50 faster / slower |
|---|---:|---:|---:|---:|
| cold-result-cache | 49 | 12 / 37 | 22 / 27 | 14 / 35 |
| warm-result-cache | 49 | 42 / 7 | 40 / 9 | 42 / 7 |
| uncached-directory | 14 | 14 / 0 | 14 / 0 | 14 / 0 |

All seven slower warm groups are `training-core:multi_source`: baseline evidence is incomplete, candidate evidence is complete. Their timings remain in every table and chart. The 14 cold/warm multi-source groups have different evidence completeness; this is disclosed rather than filtered out.

## Fixed archive and growth

The inactive routing archive retains 16 pages. Across the foreign-growth axis its current-query candidate p50 rises from 10.516 ms to 13.689 ms to 25.743 ms, while complete directory-chain p50 rises from 0.769 ms to 1.579 ms to 4.930 ms. Faster directory lookup does not establish constant-time retrieval.

At 100,000 pages, grouped archive current recall is slower (42.978 → 46.814 ms); interleaved current recall is faster (166.898 → 102.478 ms). Interleaved historical recall is 133.222 → 67.912 ms, and the directory/read chain is 159.154 → 26.707 ms. These are this run's pooled p50 values, not run-to-run speedups.

For routing-core, own growth increases target history from 16 to 8,368 pages while the other growing projects also expand. Current-query candidate p50 grows from 25.893 ms at 50,016 total pages to 331.363 ms at grouped 100k; interleaved 100k is 338.309 ms. Baseline is 22.100, 325.212 and 332.062 ms respectively. This remains a substantial latency limit.

## Every group with a slower observed statistic

A group is listed when pooled p50, pooled p95, or the median paired p50 ratio exceeds the baseline. No significance threshold or performance acceptance criterion is invented. Complete counts are counts of timed outputs, not independent questions.

| Checkpoint | Query / mode | Base p50 ms | Cand p50 ms | Base p95 ms | Cand p95 ms | Paired p50 ratio | Complete base / cand |
|---|---|---:|---:|---:|---:|---:|---:|
| age-reference-1024 | routing-archive:current / cold | 6.726330 | 10.516317 | 16.026323 | 20.485461 | 1.555472 | 30/30 / 30/30 |
| age-reference-1024 | routing-archive:historical / cold | 1.473846 | 1.487481 | 1.559245 | 1.522056 | 1.009712 | 30/30 / 30/30 |
| age-reference-1024 | routing-core:identifier / cold | 1.545160 | 1.552858 | 1.733000 | 1.764870 | 1.008897 | 30/30 / 30/30 |
| age-reference-1024 | routing-core:current / cold | 6.757730 | 10.481006 | 6.856199 | 10.958659 | 1.553834 | 30/30 / 30/30 |
| age-reference-1024 | training-core:multi_source / cold | 7.235193 | 11.316183 | 7.595241 | 11.674227 | 1.561190 | 0/30 / 30/30 |
| age-reference-1024 | attention-next:replacement / cold | 2.044329 | 2.057542 | 2.185717 | 2.182690 | 1.008694 | 30/30 / 30/30 |
| age-reference-1024 | training-core:multi_source / warm | 0.189741 | 0.202479 | 0.224791 | 0.239971 | 1.070522 | 0/90 / 90/90 |
| age-shift-1024 | routing-archive:current / cold | 6.765501 | 10.486470 | 16.050544 | 20.340719 | 1.561061 | 30/30 / 30/30 |
| age-shift-1024 | routing-archive:historical / cold | 1.481766 | 1.489345 | 1.542845 | 1.528659 | 1.003957 | 30/30 / 30/30 |
| age-shift-1024 | routing-core:identifier / cold | 1.554698 | 1.549373 | 1.711942 | 1.746967 | 0.997301 | 30/30 / 30/30 |
| age-shift-1024 | routing-core:current / cold | 6.744257 | 10.512554 | 6.919811 | 10.649735 | 1.559975 | 30/30 / 30/30 |
| age-shift-1024 | ranking-next:chinese / cold | 2.256425 | 2.264254 | 2.739773 | 2.391372 | 1.003510 | 30/30 / 30/30 |
| age-shift-1024 | training-core:multi_source / cold | 7.259159 | 11.315103 | 7.553254 | 11.745076 | 1.559698 | 0/30 / 30/30 |
| age-shift-1024 | attention-next:replacement / cold | 2.054688 | 2.059070 | 2.176240 | 2.169397 | 0.996350 | 30/30 / 30/30 |
| age-shift-1024 | training-core:multi_source / warm | 0.189485 | 0.201802 | 0.225271 | 0.240510 | 1.067986 | 0/90 / 90/90 |
| foreign-10016 | routing-archive:current / cold | 9.953997 | 13.689474 | 19.443005 | 23.853319 | 1.376895 | 30/30 / 30/30 |
| foreign-10016 | routing-archive:historical / cold | 3.687864 | 3.694637 | 3.854746 | 3.803091 | 1.001887 | 30/30 / 30/30 |
| foreign-10016 | routing-core:identifier / cold | 4.268782 | 4.269369 | 4.804116 | 4.613802 | 1.000571 | 30/30 / 30/30 |
| foreign-10016 | routing-core:current / cold | 9.963639 | 13.704497 | 10.268068 | 14.142838 | 1.374697 | 30/30 / 30/30 |
| foreign-10016 | ranking-next:chinese / cold | 5.874646 | 5.927206 | 6.001132 | 6.126155 | 1.010164 | 30/30 / 30/30 |
| foreign-10016 | training-core:multi_source / cold | 9.515712 | 13.570754 | 10.274441 | 14.080446 | 1.423244 | 0/30 / 30/30 |
| foreign-10016 | training-core:multi_source / warm | 0.190281 | 0.205169 | 0.224410 | 0.240820 | 1.082461 | 0/90 / 90/90 |
| foreign-50016 | routing-archive:current / cold | 21.971908 | 25.742641 | 32.020148 | 36.613745 | 1.170944 | 30/30 / 30/30 |
| foreign-50016 | routing-archive:historical / cold | 11.023089 | 11.028282 | 11.328860 | 11.242250 | 1.003633 | 30/30 / 30/30 |
| foreign-50016 | routing-core:identifier / cold | 14.175154 | 14.238167 | 15.378252 | 14.777571 | 1.002660 | 30/30 / 30/30 |
| foreign-50016 | routing-core:current / cold | 22.099505 | 25.892708 | 23.166457 | 29.061780 | 1.165731 | 30/30 / 30/30 |
| foreign-50016 | ranking-next:chinese / cold | 13.878149 | 13.880073 | 14.197257 | 14.280852 | 0.998162 | 30/30 / 30/30 |
| foreign-50016 | training-core:multi_source / cold | 17.010347 | 21.075020 | 17.981570 | 21.714680 | 1.240634 | 0/30 / 30/30 |
| foreign-50016 | attention-next:replacement / cold | 28.152344 | 28.190757 | 29.373412 | 29.367151 | 1.000356 | 30/30 / 30/30 |
| foreign-50016 | routing-core:current / warm | 0.202559 | 0.191252 | 0.240800 | 0.271618 | 0.937620 | 90/90 / 90/90 |
| foreign-50016 | training-core:multi_source / warm | 0.189880 | 0.202253 | 0.230681 | 0.237093 | 1.061165 | 0/90 / 90/90 |
| own-100000 | routing-archive:current / cold | 42.978263 | 46.814051 | 52.652579 | 57.001092 | 1.089158 | 30/30 / 30/30 |
| own-100000 | routing-archive:historical / cold | 24.583925 | 24.560208 | 25.552984 | 25.587330 | 0.992676 | 30/30 / 30/30 |
| own-100000 | routing-core:identifier / cold | 163.791234 | 164.007499 | 169.204311 | 166.162389 | 1.002110 | 30/30 / 30/30 |
| own-100000 | routing-core:current / cold | 325.212388 | 331.362813 | 333.548539 | 335.989690 | 1.014963 | 30/30 / 30/30 |
| own-100000 | training-core:multi_source / cold | 280.781358 | 288.176054 | 292.751239 | 290.047453 | 1.025175 | 0/30 / 30/30 |
| own-100000 | attention-next:replacement / cold | 222.821135 | 223.856905 | 227.128848 | 226.092068 | 1.003592 | 30/30 / 30/30 |
| own-100000 | training-core:multi_source / warm | 0.197981 | 0.210579 | 0.229268 | 0.245459 | 1.043998 | 0/90 / 90/90 |
| interleaved-100000 | routing-core:current / cold | 332.061827 | 338.308937 | 337.134324 | 341.402597 | 1.016352 | 30/30 / 30/30 |
| interleaved-100000 | training-core:multi_source / cold | 286.868283 | 294.006139 | 291.347451 | 297.597370 | 1.024227 | 0/30 / 30/30 |
| interleaved-100000 | attention-next:replacement / cold | 227.626620 | 227.892272 | 230.925708 | 231.289480 | 1.001712 | 30/30 / 30/30 |
| interleaved-100000 | routing-core:current / warm | 0.208821 | 0.197259 | 0.246221 | 0.255558 | 0.930105 | 90/90 / 90/90 |
| interleaved-100000 | training-core:multi_source / warm | 0.191493 | 0.209367 | 0.232866 | 0.249226 | 1.081506 | 0/90 / 90/90 |
| replacement-100000 | routing-core:identifier / cold | 166.708521 | 166.400180 | 169.199183 | 169.270620 | 0.997814 | 30/30 / 30/30 |
| replacement-100000 | routing-core:current / cold | 329.653357 | 337.124585 | 332.356917 | 346.230132 | 1.024267 | 30/30 / 30/30 |
| replacement-100000 | ranking-next:chinese / cold | 165.710034 | 166.584914 | 168.114569 | 169.164598 | 1.006627 | 30/30 / 30/30 |
| replacement-100000 | training-core:multi_source / cold | 285.152246 | 294.198932 | 290.821273 | 301.357803 | 1.030367 | 0/30 / 30/30 |
| replacement-100000 | attention-next:replacement / cold | 226.988750 | 230.073981 | 229.658763 | 251.968474 | 1.011235 | 30/30 / 30/30 |
| replacement-100000 | training-core:multi_source / warm | 0.192735 | 0.208545 | 0.241902 | 0.242663 | 1.095836 | 0/90 / 90/90 |

## Resource boundaries

`resources-by-block.csv` preserves all 84 original workers. `resources-summary.csv` separates all workers (six per arm), round 0 with quality plus performance (one), and rounds 1–5 with performance only (five). Whole-worker CPU includes import/setup, recording, scoring and fingerprinting, and is not the sum of API call CPU. Per-call CPU quantiles remain separately available in `groups.csv`.

Recorded RSS is process-lifetime high-water, not per-call allocation or steady-state working set. Most later stages report equal arm high-water values; that cannot prove zero extra allocation. Initialization medians are about 0.80–0.85 ms. Main/WAL/SHM totals after the worker's checkpoint are equal between arms at each stage; grouped/interleaved 100k are about 363.457/366.715 MiB respectively.

## Reproduce

This rendering used Python 3.12.14, Matplotlib 3.10.8 and NumPy 2.3.5. English uses DejaVu Sans; Chinese uses Noto Sans CJK JP. The generator accepts a registered Noto Sans CJK SC or JP face and records the selected family and font-file hash in `analysis.json`. The presentation environment is separate from the measured runner. The generator never executes the measured runtime.

```bash
python scripts/render_v013_scale_review.py \
  --archive /path/to/original-artifact-44331778554-1.zip \
  --audit benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-saved-response-review.json \
  --output-report /new/empty/report-directory \
  --output-assets /new/empty/asset-directory
```

`groups.csv` has all 112 wall/CPU groups and complete counts; `paired-rounds.csv` has all 672 paired records; `timed-observations.csv.gz` preserves all 12,600 compact timing rows and their original-response gzip offsets/hashes; `quality-cases.csv` retains the 1,008 quality records. Original ZIP/response data remain authoritative. The CSVs and SVGs are derived presentations, not replacement measurements.
