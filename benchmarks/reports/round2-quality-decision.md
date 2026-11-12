# Q1 development decision

Q1 is a useful fusion ablation, but the current results do not justify replacing the existing semantic route for every workload. Keep `semantic=false` as the product default. Preserve this candidate and all of its results while evaluating the separately registered Q2 direction on the old development data.

The [complete comparison](round2-quality-development.md) contains all four old cohorts, all three budgets, all three modes and all three repetitions: **36,369 successful measured recalls**, with no omitted or replayed attempts. Each cohort ran on its own hosted VM; every comparison within a cohort is paired. [The fixed run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194168722) and its ordinary CI both completed successfully. This is completion of the registered experiment, not completion of general semantic memory.

## What improved

On the old 1,015-question LoCoMo regression cohort, Q1 raised complete evidence from lexical retrieval's **66.41% to 69.65% at 512 tokens**, and **72.88% to 76.43% at 1024 and 2048 tokens**. At 512 tokens there were 32 question gains and 11 losses against lexical retrieval; at each larger budget there were 27 gains and four losses. Against original RRF, the corresponding complete-evidence rates were 62.40% and 70.88%, so Q1 also recovered substantial losses caused by that fusion policy. [Paired source record](../results/round2-quality-regression-public1015.summary.json)

The same old cohort's 326 low-overlap questions improved from **46.01% to 52.15%** complete evidence at 512 tokens, and **54.91% to 59.51%** at each larger budget. Its 76 cross-session questions improved from **18.42% to 22.37%** at the larger budgets. These are overlapping diagnostic subsets of the same development cohort, not independent validation sets. Their absolute completeness remains limited. The LoCoMo representation does not provide a cross-chapter group for this run. [Diagnostic source record](../results/round2-quality-regression-public1015.summary.json)

Q1 also recovered much of the synthetic cohort's RRF regression. At 1024/2048 tokens Q1 reached **93.42%** complete evidence, compared with **92.11%** lexical and **75.66%/77.63%** original RRF. On the 36-question authored cohort, both semantic policies reached **100%** of the 30 answerable questions, versus **86.67%** lexical. [Synthetic source record](../results/round2-quality-development-synthetic61.summary.json) · [Authored source record](../results/round2-quality-regression-authored36.summary.json)

## Why Q1 is not a general replacement

At **512 tokens**, synthetic completeness is still lower than lexical: **80.92% versus 85.53%**, with two gains and nine losses. Eight losses belong to long-answer middle/late categories and one to cross-project name disambiguation. This supports further investigation of first-fit ordering and excerpt selection; it does not prove that a single mechanism explains every failure. [Full paired rows](../results/round2-quality-development-synthetic61.json.gz)

On the old 128-question HotpotQA cohort, Q1 regresses on complete evidence at every budget:

| Context cap | Lexical | Original RRF | Q1 |
|---:|---:|---:|---:|
| 512 | 35.16% | 32.81% | 30.47% |
| 1024 | 48.44% | 50.78% | 47.66% |
| 2048 | 48.44% | 50.78% | 47.66% |

All 128 questions require evidence from multiple chapters in this representation. Q1 has seven gains and ten losses against RRF at 512 tokens, and four gains/eight losses at each larger budget. Its annotation recall can remain similar while its complete-question rate drops, so annotation recall alone would hide the regression. The low-overlap subgroup contains only three questions and is too small for a broad claim. [Hotpot source record](../results/round2-quality-regression-hotpot128.summary.json)

Q1 also retains the embedding-query cost. At 512 tokens its p50 query times were **13.72/10.17/9.49/18.05 ms** on synthetic/authored/LoCoMo/Hotpot respectively; the paired lexical values were **6.46/1.58/4.37/6.90 ms**. These are separate hosts, and should be compared only within each pair. Model loading and fresh index construction are reported separately. Existing compatible indexes can be reused because the embedding/model version stays at 1 and the fusion-result-cache version is separate. [Timing, payload and preparation tables](round2-quality-development.md#query-time-and-returned-tokens)

The experiment contains no generated-answer assessment. Nonempty contexts for unsupported questions are retained as diagnostics, not relabeled as wrong generated answers. All old questions are development/regression data. The new 256-question sample remains unseen by the quality-development agent and must not be used to choose a weight or to rewrite a failed candidate.

## Next hypothesis

The next proposed experiment changes only one retrieval priority: promote the first page from the existing lexical ordering while preserving the original RRF relative order for all remaining pages. This is narrower than replacing the full ordering with normalized score margins. It still risks promoting an incorrect lexical anchor or displacing a useful fifth page. Register its exact rule and full comparison axes before measuring it; keep the Q1 reports above unchanged.
