# Q2 development decision

**Select Q2 as the frozen candidate for the next single blind validation and as the candidate replacement of original RRF in the optional `semantic=true` route. Keep `semantic=false` as the product default.** Q1 remains a research comparison, not the default semantic policy. Q2 has a more consistent old-cohort result than the full score-fusion Q1 replacement, but it does not outperform lexical retrieval on every workload or budget. Selection for blind validation is not a claim of new-domain generalization.

The [complete four-mode report](round2-anchor-development.md) contains all registered old cohorts, all three token budgets and all three repetitions: **48,492 completed measured recalls**, without omitted or replayed attempts. The [hosted run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43196880064) completed successfully, as did its source's ordinary CI. Runtime source is `cce621cbe62b0e8d7a94fbdb023372e0ff2004ca390e2ffd5c01863596059b43` at commit `6286564e33f09db9863a80613771722c32ba363b`.

Q2 promotes only the first candidate from the existing lexical order. Every other page retains its original RRF relative order, and each page retains its own original RRF score. It adds no model operation, threshold, learned rule, source rewrite or dataset-specific routing. The lexical route's existing novelty/current/coverage ordering supplies the anchor; Q2 does not reconstruct the leader from raw BM25 magnitude. Compatible embedding indexes retain version 1, while semantic result-cache version 3 separates this ordering from previous results.

## Same-run complete-evidence results

The table uses the four modes measured together in the Q2 run. All percentages use answerable questions as their denominator; total cohort sizes also include unsupported questions where applicable.

| Old cohort | Context cap | Lexical | Original RRF | Q1 control | Q2 |
|---|---:|---:|---:|---:|---:|
| Synthetic, seed 61; 168 questions | 512 | 85.53% | 63.16% | 80.92% | 81.58% |
| Synthetic, seed 61; 168 questions | 1024 | 92.11% | 75.66% | 93.42% | 92.11% |
| Synthetic, seed 61; 168 questions | 2048 | 92.11% | 77.63% | 93.42% | 92.11% |
| Authored; 36 questions | 512 | 86.67% | 100.00% | 100.00% | 100.00% |
| Authored; 36 questions | 1024 | 86.67% | 100.00% | 100.00% | 100.00% |
| Authored; 36 questions | 2048 | 86.67% | 100.00% | 100.00% | 100.00% |
| LoCoMo regression; 1,015 questions | 512 | 66.41% | 62.40% | 69.65% | 68.10% |
| LoCoMo regression; 1,015 questions | 1024 | 72.88% | 70.88% | 76.43% | 74.27% |
| LoCoMo regression; 1,015 questions | 2048 | 72.88% | 70.88% | 76.43% | 74.27% |
| HotpotQA regression; 128 questions | 512 | 35.16% | 33.59% | 32.03% | 34.38% |
| HotpotQA regression; 128 questions | 1024 | 48.44% | 50.00% | 46.88% | 50.78% |
| HotpotQA regression; 128 questions | 2048 | 48.44% | 50.00% | 46.88% | 50.78% |

Q2 is no worse than original RRF on both aggregate complete evidence and annotation recall in these **12 old cohort/budget combinations**. This aggregate observation does not extend to every question or diagnostic subset. Every paired question/annotation gain and loss is preserved in the full reports. [Synthetic](../results/round2-anchor-development-synthetic61.summary.json) · [Authored](../results/round2-anchor-regression-authored36.summary.json) · [LoCoMo](../results/round2-anchor-regression-public1015.summary.json) · [HotpotQA](../results/round2-anchor-regression-hotpot128.summary.json)

Q1 still has higher aggregate LoCoMo completeness than Q2: 69.65% versus 68.10% at 512 tokens, and 76.43% versus 74.27% at larger budgets. Q2 retains stronger multi-chapter Hotpot results in the same run: 50.78% versus Q1's 46.88% at larger budgets. These tradeoffs support testing the narrower Q2 intervention; they do not support selecting different policies using knowledge of a question's dataset or its expected answer. The [entire earlier Q1 record](round2-quality-development.md) remains available, including its gains and regressions.

## Remaining quality limits

At 512 tokens, Q2 is still **3.95 percentage points below lexical retrieval on the synthetic cohort**, with one complete-question gain and seven losses. On Hotpot it is **0.78 points below lexical**, with nine gains and ten losses. Q2 does not solve the small-budget preservation problem for every question.

On the old LoCoMo low-overlap group of 326 questions, complete evidence is **50.00% at 512 tokens and 57.98% at larger budgets**, versus lexical's 46.01%/54.91%. Its 76 cross-session questions reach **11.84%/18.42%**, versus lexical's 10.53%/18.42%. **At 512 tokens the cross-session group loses one net complete question against original RRF: 9/76 versus 10/76 (11.84% versus 13.16%), with one gain and two losses.** On the synthetic low-overlap group, Q2 remains at 68.75%, below lexical and Q1 at 75%. Groups overlap and are not independent test sets. [All diagnostic groups](round2-anchor-development.md#low-overlap-and-evidence-combination)

All 128 old Hotpot questions require evidence from multiple chapters in this representation. A 50.78% complete-evidence result remains a substantial limitation. Its low-overlap subgroup contains only three questions, so its 100% larger-budget value cannot establish a broad semantic-retrieval capability. No generated answers are assessed by this experiment.

## Cost and repeatability

Each semantic mode made exactly **12,123 actual `encode_query` calls**; lexical made zero. Thus Q2 does not increase the per-query embedding-operation count relative to original RRF or Q1. It retains embedding latency and index/model preparation costs. This is not a speed-improvement claim.

At 512 tokens, paired Q2 versus lexical p50 query times were **21.52 versus 8.94 ms** on synthetic, **5.50 versus 0.91 ms** on authored, **13.53 versus 5.85 ms** on LoCoMo, and **15.06 versus 5.52 ms** on Hotpot. Each pair shares its own cohort VM; absolute timings across cohorts or separate runs must not be pooled. Some Q2 tail timings are higher than original RRF, including synthetic p95 at 512 tokens, so the report retains p50/p95/p99, first/repeat passes, returned context tokens and full response-payload tokens for every configuration. [Full cost tables](round2-anchor-development.md#query-time-and-returned-tokens)

The repeated lexical/RRF/Q1 controls were compared with the earlier Q1 experiment. Synthetic and LoCoMo control contexts and evidence reproduce exactly, as do lexical contexts on every cohort. Authored semantic controls have some tail-order changes without changed evidence presence. Hotpot semantic controls have some changed evidence presence and complete questions. Verified model identity, recorded package/platform identity and indexed page-text/ID hashes agree; the records do not establish the cause of the semantic differences. Full source snapshots also include lifecycle timestamps. Cross-run semantic differences are retained as diagnostics, not attributed to Q2. The main quality conclusions above use the four modes sharing one actual index within the Q2 run. [Cross-run control audit](round2-anchor-development.md#repeated-controls-across-experiments)

All old questions remain development/regression data. The new 256-question validation sample was not read by the quality-development agent. Freeze the selected source and settings before that single validation and retain its outcome without retuning against it.
