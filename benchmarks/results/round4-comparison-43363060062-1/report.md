# Round four: native APIs and supplied-page components

Candidate, evaluator, dependency/model and upstream source identities were committed before selecting these 256 IDs. The selection excludes all 640 IDs from Hotpot128, round-two Hotpot256 and round-three Hotpot256. It is another selection from the same HotpotQA source, not a new domain. These measurements assess returned source evidence, not generated-answer accuracy or a complete write/summarize/generate workflow.

Integrity passed for every registered query, budget and repetition. Optional Q2 gains and losses are retained; integrity does not imply a quality improvement.

## Native API

| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline-native | cl100k_base | 512 | 67.87% | 39.45% | 478.6 | 4.690 | 6.118 |
| baseline-native | cl100k_base | 1024 | 75.75% | 53.91% | 803.6 | 3.907 | 5.182 |
| baseline-native | cl100k_base | 2048 | 75.75% | 53.91% | 805.4 | 3.884 | 5.257 |
| baseline-native | o200k_base | 512 | 67.87% | 39.45% | 478.1 | 6.001 | 7.659 |
| baseline-native | o200k_base | 1024 | 75.75% | 53.91% | 802.6 | 4.705 | 6.079 |
| baseline-native | o200k_base | 2048 | 75.75% | 53.91% | 804.1 | 4.789 | 6.160 |
| candidate-native | cl100k_base | 512 | 67.87% | 39.45% | 478.6 | 3.313 | 4.411 |
| candidate-native | cl100k_base | 1024 | 75.75% | 53.91% | 803.6 | 2.918 | 4.105 |
| candidate-native | cl100k_base | 2048 | 75.75% | 53.91% | 805.4 | 2.917 | 4.235 |
| candidate-native | o200k_base | 512 | 67.87% | 39.45% | 478.1 | 3.774 | 4.946 |
| candidate-native | o200k_base | 1024 | 75.75% | 53.91% | 802.6 | 3.195 | 4.364 |
| candidate-native | o200k_base | 2048 | 75.75% | 53.91% | 804.1 | 3.073 | 4.199 |
| candidate-semantic-native | cl100k_base | 512 | 66.14% | 36.33% | 479.8 | 14.474 | 21.161 |
| candidate-semantic-native | cl100k_base | 1024 | 76.69% | 55.08% | 818.1 | 13.998 | 21.022 |
| candidate-semantic-native | cl100k_base | 2048 | 76.69% | 55.08% | 820.6 | 13.927 | 20.882 |
| candidate-semantic-native | o200k_base | 512 | 66.30% | 36.72% | 479.4 | 14.825 | 21.970 |
| candidate-semantic-native | o200k_base | 1024 | 76.69% | 55.08% | 816.5 | 14.122 | 21.465 |
| candidate-semantic-native | o200k_base | 2048 | 76.69% | 55.08% | 819.2 | 14.195 | 21.840 |

Native calls use 8000 characters, top five, no result cache and one repetition. The independent ABBA old-data performance experiment supplies the release performance gate; these native measurements are not a substitute for that gate.

## Common whole-block projections

| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Packed-context MRR | Context tokens |
|---|---|---:|---:|---:|---:|---:|
| baseline-component | cl100k_base | 512 | 68.66% | 41.02% | 0.8522 | 446.1 |
| baseline-component | cl100k_base | 1024 | 75.75% | 53.91% | 0.8578 | 714.8 |
| baseline-component | cl100k_base | 2048 | 75.75% | 53.91% | 0.8578 | 715.9 |
| baseline-component | o200k_base | 512 | 68.98% | 41.41% | 0.8535 | 447.2 |
| baseline-component | o200k_base | 1024 | 75.75% | 53.91% | 0.8578 | 708.3 |
| baseline-component | o200k_base | 2048 | 75.75% | 53.91% | 0.8578 | 709.4 |
| candidate-component | cl100k_base | 512 | 68.66% | 41.02% | 0.8522 | 446.1 |
| candidate-component | cl100k_base | 1024 | 75.75% | 53.91% | 0.8578 | 714.8 |
| candidate-component | cl100k_base | 2048 | 75.75% | 53.91% | 0.8578 | 715.9 |
| candidate-component | o200k_base | 512 | 68.98% | 41.41% | 0.8535 | 447.2 |
| candidate-component | o200k_base | 1024 | 75.75% | 53.91% | 0.8578 | 708.3 |
| candidate-component | o200k_base | 2048 | 75.75% | 53.91% | 0.8578 | 709.4 |
| candidate-semantic-component | cl100k_base | 512 | 68.19% | 39.84% | 0.8626 | 447.7 |
| candidate-semantic-component | cl100k_base | 1024 | 76.69% | 55.08% | 0.8663 | 730.0 |
| candidate-semantic-component | cl100k_base | 2048 | 76.69% | 55.08% | 0.8663 | 731.1 |
| candidate-semantic-component | o200k_base | 512 | 68.35% | 40.62% | 0.8626 | 448.2 |
| candidate-semantic-component | o200k_base | 1024 | 76.69% | 55.08% | 0.8663 | 723.4 |
| candidate-semantic-component | o200k_base | 2048 | 76.69% | 55.08% | 0.8663 | 724.5 |
| claude-mem-fts | cl100k_base | 512 | 62.36% | 31.25% | 0.8239 | 446.3 |
| claude-mem-fts | cl100k_base | 1024 | 70.39% | 44.53% | 0.8280 | 709.4 |
| claude-mem-fts | cl100k_base | 2048 | 70.39% | 44.53% | 0.8280 | 710.4 |
| claude-mem-fts | o200k_base | 512 | 62.68% | 31.64% | 0.8239 | 447.2 |
| claude-mem-fts | o200k_base | 1024 | 70.39% | 44.53% | 0.8280 | 702.8 |
| claude-mem-fts | o200k_base | 2048 | 70.39% | 44.53% | 0.8280 | 703.9 |
| ai-memory-hybrid | cl100k_base | 512 | 66.30% | 36.72% | 0.8340 | 449.4 |
| ai-memory-hybrid | cl100k_base | 1024 | 77.48% | 55.86% | 0.8400 | 709.9 |
| ai-memory-hybrid | cl100k_base | 2048 | 77.48% | 55.86% | 0.8400 | 710.8 |
| ai-memory-hybrid | o200k_base | 512 | 67.09% | 38.28% | 0.8340 | 452.1 |
| ai-memory-hybrid | o200k_base | 1024 | 77.48% | 55.86% | 0.8400 | 703.6 |
| ai-memory-hybrid | o200k_base | 2048 | 77.48% | 55.86% | 0.8400 | 704.5 |
| billion-context | cl100k_base | 512 | 68.82% | 41.80% | 0.8490 | 454.0 |
| billion-context | cl100k_base | 1024 | 80.94% | 60.55% | 0.8606 | 757.4 |
| billion-context | cl100k_base | 2048 | 80.94% | 60.55% | 0.8606 | 759.5 |
| billion-context | o200k_base | 512 | 69.13% | 42.19% | 0.8490 | 453.8 |
| billion-context | o200k_base | 1024 | 80.94% | 60.55% | 0.8606 | 751.4 |
| billion-context | o200k_base | 2048 | 80.94% | 60.55% | 0.8606 | 752.4 |

The six projections reuse the first native response. Three native search repetitions remain in raw ledgers; there are no extra diagnostic or replacement searches. ai-memory metadata hits consume original top-five slots, retain their native payload cost, and earn zero evidence credit. Packed-context MRR measures evidence order after metadata or oversized blocks are omitted; raw native positions remain recorded.

## Measured component boundaries

| Component | Search adapter p50/p95 ms | First search + all reads p50/p95 ms | Search payload cl100k/o200k | Read payload cl100k/o200k | Reads/query |
|---|---:|---:|---:|---:|---:|
| baseline-component | 2.239/3.304 | 2.258/3.366 | 3972.6/3992.3 | 0.0/0.0 | 0.00 |
| candidate-component | 2.353/3.488 | 2.359/3.498 | 3972.6/3992.3 | 0.0/0.0 | 0.00 |
| candidate-semantic-component | 12.832/20.406 | 12.841/20.318 | 4079.4/4098.5 | 0.0/0.0 | 0.00 |
| claude-mem-fts | 18.379/34.655 | 18.579/35.139 | 1634.3/1620.3 | 0.0/0.0 | 0.00 |
| ai-memory-hybrid | 31.712/39.925 | 37.748/45.897 | 1016.2/1014.4 | 1830.3/1823.9 | 5.00 |
| billion-context | 0.462/1.449 | 1.056/2.080 | 583.8/577.7 | 0.0/0.0 | 0.00 |

Search plus all reads sums each query's roundtrips before computing percentiles. Book is in-process Python including context assembly; claude-mem uses native SQLite/Bun; ai-memory uses local hybrid HTTP/MCP; billion-context uses its supplied-source search kernel/Node. These are distinct component boundaries, so no whole-product speed ratio follows. Native content, native payload and common packed context are separate token surfaces.

## Setup, RSS and state

| Mode | Setup wall ms | Setup RSS MiB | Query RSS MiB | Native state bytes |
|---|---:|---:|---:|---:|
| baseline-native | 3899.084 | 552.54 | 535.88 | 39045752 |
| candidate-native | 3796.309 | 558.42 | 541.79 | 39045752 |
| candidate-semantic-native | 282970.296 | 1294.50 | 1278.19 | 55994000 |
| baseline-component | 839.246 | 548.65 | 529.77 | 33955840 |
| candidate-component | 835.078 | 943.53 | 524.91 | 33955840 |
| candidate-semantic-component | 277600.186 | 1247.69 | 1247.69 | 53913400 |
| claude-mem-fts | 2443.182 | 703.64 | 618.37 | 20832050 |
| ai-memory-hybrid | 853967.359 | 755.09 | 750.41 | 74580855 |
| billion-context | 230.903 | 542.07 | 661.25 | 0 |

Native Book stages separately record fresh ingestion and optional model/index construction. Component Book stages copy one canonical archive and measure their own setup/index costs. Q2's persisted native/component index-vector digests match; this does not assert separately measured query-embedding identity. RSS is sampled worker-plus-descendants every 20 ms, includes evaluator/data memory, can double-count shared pages, and provides observed lower bounds. Database main/WAL/SHM, live statistics remain in raw summaries; symlinked model caches are excluded from native state bytes.

## Low-overlap and multi-paragraph evidence

| Mode | Group at 512 cl100k | Questions | Complete evidence | Evidence recall |
|---|---|---:|---:|---:|
| baseline-native | low_lexical_overlap_le_0.25 | 4 | 25.00% | 37.50% |
| baseline-native | multiple_required_evidence | 256 | 39.45% | 67.87% |
| baseline-native | cross_session | 256 | 39.45% | 67.87% |
| baseline-native | cross_chapter | 256 | 39.45% | 67.87% |
| candidate-native | low_lexical_overlap_le_0.25 | 4 | 25.00% | 37.50% |
| candidate-native | multiple_required_evidence | 256 | 39.45% | 67.87% |
| candidate-native | cross_session | 256 | 39.45% | 67.87% |
| candidate-native | cross_chapter | 256 | 39.45% | 67.87% |
| candidate-semantic-native | low_lexical_overlap_le_0.25 | 4 | 0.00% | 37.50% |
| candidate-semantic-native | multiple_required_evidence | 256 | 36.33% | 66.14% |
| candidate-semantic-native | cross_session | 256 | 36.33% | 66.14% |
| candidate-semantic-native | cross_chapter | 256 | 36.33% | 66.14% |
| baseline-component | low_lexical_overlap_le_0.25 | 4 | 25.00% | 50.00% |
| baseline-component | multiple_required_evidence | 256 | 41.02% | 68.66% |
| baseline-component | cross_session | 256 | 41.02% | 68.66% |
| baseline-component | cross_chapter | 256 | 41.02% | 68.66% |
| candidate-component | low_lexical_overlap_le_0.25 | 4 | 25.00% | 50.00% |
| candidate-component | multiple_required_evidence | 256 | 41.02% | 68.66% |
| candidate-component | cross_session | 256 | 41.02% | 68.66% |
| candidate-component | cross_chapter | 256 | 41.02% | 68.66% |
| candidate-semantic-component | low_lexical_overlap_le_0.25 | 4 | 25.00% | 50.00% |
| candidate-semantic-component | multiple_required_evidence | 256 | 39.84% | 68.19% |
| candidate-semantic-component | cross_session | 256 | 39.84% | 68.19% |
| candidate-semantic-component | cross_chapter | 256 | 39.84% | 68.19% |
| claude-mem-fts | low_lexical_overlap_le_0.25 | 4 | 25.00% | 50.00% |
| claude-mem-fts | multiple_required_evidence | 256 | 31.25% | 62.36% |
| claude-mem-fts | cross_session | 256 | 31.25% | 62.36% |
| claude-mem-fts | cross_chapter | 256 | 31.25% | 62.36% |
| ai-memory-hybrid | low_lexical_overlap_le_0.25 | 4 | 25.00% | 50.00% |
| ai-memory-hybrid | multiple_required_evidence | 256 | 36.72% | 66.30% |
| ai-memory-hybrid | cross_session | 256 | 36.72% | 66.30% |
| ai-memory-hybrid | cross_chapter | 256 | 36.72% | 66.30% |
| billion-context | low_lexical_overlap_le_0.25 | 4 | 25.00% | 37.50% |
| billion-context | multiple_required_evidence | 256 | 41.80% | 68.82% |
| billion-context | cross_session | 256 | 41.80% | 68.82% |
| billion-context | cross_chapter | 256 | 41.80% | 68.82% |

Cross-session/chapter labels arise from mapping supplied encyclopedia paragraphs to sessions/chapters; they do not measure private conversational transfer. Small diagnostic groups are retained and their sample sizes limit conclusions. All selected questions are answerable, so abstention and hallucination rates are not measured.

Run: `43363060062-1`. Native calls: 4608; native component searches: 4608. Complete default payload equivalence: `True`. No quality or project-statistics candidate is included.

Every paired annotation/query gain and loss, all budget/tokenizer groups, repeat changes, native read costs and source hashes remain in the machine-readable assessment and stage reports. After first scoring these IDs are regression data. HotpotQA source is CC BY-SA 4.0; original questions, answers and passages are downloaded separately and are not published here.
