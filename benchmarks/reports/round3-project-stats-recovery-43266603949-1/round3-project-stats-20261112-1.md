# Project-local FTS statistics: registered old-data screen

One opt-in candidate; unchanged global default. Four old development/regression cohorts, 8,000 characters, top 5 and cl100k_base token limits. These are strict source-evidence measurements, not answer accuracy or a new-domain/generalization claim. The eight unscoped synthetic queries remain in every budget and use the unchanged global path in both modes; no project is inferred.

Integrity: **PASS**. Gate: **rejected_loss_or_no_gain**.

| Cohort | Tokens | Complete global / local | Evidence global / local | Complete gains / losses | Annotation gains / losses | p50 global / local ms | p95 global / local ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | 512 | 85.53% / 82.24% | 86.36% / 83.52% | 0 / 5 | 4 / 9 | 5.473 / 24.655 | 12.622 / 52.055 |
| synthetic61 | 1024 | 92.11% / 91.45% | 93.18% / 92.61% | 0 / 1 | 0 / 1 | 5.062 / 25.723 | 14.961 / 53.041 |
| synthetic61 | 2048 | 92.11% / 91.45% | 93.18% / 92.61% | 0 / 1 | 0 / 1 | 4.021 / 23.980 | 12.250 / 44.876 |
| authored36 | 512 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 | 0 / 0 | 0.796 / 1.257 | 1.285 / 2.439 |
| authored36 | 1024 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 | 0 / 0 | 0.700 / 1.122 | 1.317 / 1.667 |
| authored36 | 2048 | 86.67% / 86.67% | 88.89% / 88.89% | 0 / 0 | 0 / 0 | 0.721 / 1.241 | 1.229 / 2.315 |
| public1015 | 512 | 66.41% / 65.64% | 62.18% / 62.18% | 13 / 18 | 22 / 22 | 3.335 / 13.063 | 5.672 / 23.608 |
| public1015 | 1024 | 72.88% / 74.27% | 69.54% / 70.94% | 13 / 4 | 18 / 7 | 2.798 / 12.513 | 4.801 / 20.910 |
| public1015 | 2048 | 72.88% / 74.27% | 69.54% / 71.07% | 13 / 4 | 19 / 7 | 2.864 / 12.069 | 5.068 / 17.843 |
| hotpot128 | 512 | 35.16% / 50.78% | 66.99% / 74.84% | 28 / 8 | 40 / 16 | 3.501 / 3.763 | 6.270 / 6.458 |
| hotpot128 | 1024 | 48.44% / 67.19% | 74.51% / 83.99% | 28 / 4 | 37 / 8 | 2.688 / 3.219 | 4.382 / 5.769 |
| hotpot128 | 2048 | 48.44% / 67.19% | 74.51% / 83.99% | 28 / 4 | 37 / 8 | 2.750 / 3.073 | 4.254 / 4.379 |

## Costs and their boundaries

Recall wall time includes every cold build, switch/rebuild and marker update. Diagnostic build times exclude the final marker write/savepoint release; complete recall timing includes them. Tokenizers are initialized before calls. All states, individual call times and small/negative groups remain in raw records. This one-pass quality development run is not formal performance evidence.

Native payload tokens count the complete canonical JSON response, including latency/cache metadata and the opt-in flag. Context tokens remain separate; neither is an MCP envelope or provider bill. CLI stats is a real new-process startup/connection/stats measurement, not an opt-in recall command. TEMP bytes mean SQLite logical allocated/live pages, not physical disk or process RSS.

| Cohort | Mode | Connection ms | CLI stats ms | Ingestion ms | Derived builds / switches | Total build ms | Peak TEMP allocated bytes | Process HWM bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | global_default | 22.790 | 44.586 | 426.304 | 0 / 0 | 0.000 | 0 | 194580480 |
| synthetic61 | project_local_fts_statistics | 20.507 | 53.019 | 367.012 | 438 / 437 | 8395.863 | 5570560 | 197361664 |
| authored36 | project_local_fts_statistics | 76.778 | 177.602 | 33.822 | 105 / 104 | 44.785 | 159744 | 153792512 |
| authored36 | global_default | 93.861 | 55.687 | 23.589 | 0 / 0 | 0.000 | 0 | 152825856 |
| public1015 | global_default | 17.175 | 47.099 | 381.063 | 0 / 0 | 0.000 | 0 | 249622528 |
| public1015 | project_local_fts_statistics | 18.760 | 55.437 | 365.717 | 2637 / 2636 | 25028.178 | 2568192 | 254619648 |
| hotpot128 | project_local_fts_statistics | 25.814 | 67.779 | 1623.361 | 384 / 383 | 409.313 | 475136 | 200941568 |
| hotpot128 | global_default | 46.063 | 50.375 | 1410.067 | 0 / 0 | 0.000 | 0 | 200286208 |

## Registered decision

Every one of the 12 cells must preserve complete evidence and annotation recall; unsupported nonempty responses cannot increase. At 512 tokens, primary groups with at least 10 questions must also preserve both metrics. At least one aggregate metric must improve. Per-question losses are retained and are not silently cancelled in reporting; the registered rule is an aggregate/group gate, not individual zero-loss.

Declared loss checks: 14; aggregate improvements: 10.
A rejection ends this candidate under the registered protocol. No new threshold, novelty variant, source update or new-selection inspection is permitted by this runner.
