# Round three: native APIs and supplied-page components

Candidate, evaluator, dependency/model and upstream source identities were committed before selecting these 256 IDs. The selection excludes both earlier Hotpot128 and round-two Hotpot256. It is another selection from the same HotpotQA source, not a new domain. These measurements assess returned source evidence, not generated-answer accuracy or a complete write/summarize/generate workflow.

Integrity passed for every registered query, budget and repetition. Optional Q2 gains and losses are retained; integrity does not imply a quality improvement.

## Native API

| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline-native | cl100k_base | 512 | 65.73% | 35.94% | 476.5 | 4.695 | 7.485 |
| baseline-native | cl100k_base | 1024 | 76.28% | 52.34% | 808.0 | 4.213 | 7.295 |
| baseline-native | cl100k_base | 2048 | 76.28% | 52.34% | 809.2 | 4.172 | 6.821 |
| baseline-native | o200k_base | 512 | 65.73% | 35.55% | 476.7 | 5.206 | 8.242 |
| baseline-native | o200k_base | 1024 | 76.28% | 52.34% | 806.6 | 4.684 | 7.739 |
| baseline-native | o200k_base | 2048 | 76.28% | 52.34% | 806.8 | 4.561 | 7.495 |
| candidate-native | cl100k_base | 512 | 65.73% | 35.94% | 476.5 | 3.150 | 4.316 |
| candidate-native | cl100k_base | 1024 | 76.28% | 52.34% | 808.0 | 2.707 | 3.828 |
| candidate-native | cl100k_base | 2048 | 76.28% | 52.34% | 809.2 | 2.821 | 3.919 |
| candidate-native | o200k_base | 512 | 65.73% | 35.55% | 476.7 | 3.928 | 5.306 |
| candidate-native | o200k_base | 1024 | 76.28% | 52.34% | 806.6 | 3.283 | 4.339 |
| candidate-native | o200k_base | 2048 | 76.28% | 52.34% | 806.8 | 3.174 | 4.397 |
| candidate-semantic-native | cl100k_base | 512 | 64.74% | 33.59% | 479.2 | 8.661 | 13.043 |
| candidate-semantic-native | cl100k_base | 1024 | 76.77% | 54.69% | 824.4 | 9.058 | 12.895 |
| candidate-semantic-native | cl100k_base | 2048 | 76.77% | 54.69% | 828.4 | 8.905 | 12.831 |
| candidate-semantic-native | o200k_base | 512 | 64.58% | 33.20% | 479.0 | 9.594 | 13.871 |
| candidate-semantic-native | o200k_base | 1024 | 76.77% | 54.69% | 822.3 | 9.681 | 13.523 |
| candidate-semantic-native | o200k_base | 2048 | 76.77% | 54.69% | 825.7 | 9.083 | 13.103 |

Native calls use 8000 characters, top five, no result cache and one repetition. The independent ABBA old-data performance experiment supplies the release performance gate; these native measurements are not a substitute for that gate.

## Common whole-block projections

| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Packed-context MRR | Context tokens |
|---|---|---:|---:|---:|---:|---:|
| baseline-component | cl100k_base | 512 | 67.38% | 38.28% | 0.8011 | 451.5 |
| baseline-component | cl100k_base | 1024 | 76.28% | 52.34% | 0.8132 | 719.8 |
| baseline-component | cl100k_base | 2048 | 76.28% | 52.34% | 0.8132 | 719.8 |
| baseline-component | o200k_base | 512 | 67.87% | 39.06% | 0.8024 | 453.3 |
| baseline-component | o200k_base | 1024 | 76.28% | 52.34% | 0.8132 | 712.3 |
| baseline-component | o200k_base | 2048 | 76.28% | 52.34% | 0.8132 | 712.3 |
| candidate-component | cl100k_base | 512 | 67.38% | 38.28% | 0.8011 | 451.5 |
| candidate-component | cl100k_base | 1024 | 76.28% | 52.34% | 0.8132 | 719.8 |
| candidate-component | cl100k_base | 2048 | 76.28% | 52.34% | 0.8132 | 719.8 |
| candidate-component | o200k_base | 512 | 67.87% | 39.06% | 0.8024 | 453.3 |
| candidate-component | o200k_base | 1024 | 76.28% | 52.34% | 0.8132 | 712.3 |
| candidate-component | o200k_base | 2048 | 76.28% | 52.34% | 0.8132 | 712.3 |
| candidate-semantic-component | cl100k_base | 512 | 67.55% | 37.89% | 0.8177 | 452.1 |
| candidate-semantic-component | cl100k_base | 1024 | 76.77% | 54.69% | 0.8239 | 739.0 |
| candidate-semantic-component | cl100k_base | 2048 | 76.77% | 54.69% | 0.8239 | 739.0 |
| candidate-semantic-component | o200k_base | 512 | 67.55% | 37.89% | 0.8190 | 453.0 |
| candidate-semantic-component | o200k_base | 1024 | 76.77% | 54.69% | 0.8239 | 731.2 |
| candidate-semantic-component | o200k_base | 2048 | 76.77% | 54.69% | 0.8239 | 731.2 |
| claude-mem-fts | cl100k_base | 512 | 61.29% | 33.20% | 0.7568 | 452.9 |
| claude-mem-fts | cl100k_base | 1024 | 70.68% | 45.31% | 0.7674 | 715.8 |
| claude-mem-fts | cl100k_base | 2048 | 70.68% | 45.31% | 0.7674 | 715.8 |
| claude-mem-fts | o200k_base | 512 | 61.78% | 33.98% | 0.7578 | 453.3 |
| claude-mem-fts | o200k_base | 1024 | 70.68% | 45.31% | 0.7674 | 708.2 |
| claude-mem-fts | o200k_base | 2048 | 70.68% | 45.31% | 0.7674 | 708.2 |
| ai-memory-hybrid | cl100k_base | 512 | 67.22% | 39.84% | 0.8063 | 451.1 |
| ai-memory-hybrid | cl100k_base | 1024 | 77.27% | 55.86% | 0.8182 | 716.8 |
| ai-memory-hybrid | cl100k_base | 2048 | 77.27% | 55.86% | 0.8182 | 716.8 |
| ai-memory-hybrid | o200k_base | 512 | 67.71% | 41.02% | 0.8063 | 448.6 |
| ai-memory-hybrid | o200k_base | 1024 | 77.27% | 55.86% | 0.8182 | 709.3 |
| ai-memory-hybrid | o200k_base | 2048 | 77.27% | 55.86% | 0.8182 | 709.3 |
| billion-context | cl100k_base | 512 | 65.73% | 37.50% | 0.8154 | 449.4 |
| billion-context | cl100k_base | 1024 | 78.91% | 58.20% | 0.8277 | 762.3 |
| billion-context | cl100k_base | 2048 | 78.91% | 58.20% | 0.8277 | 762.3 |
| billion-context | o200k_base | 512 | 65.90% | 37.89% | 0.8154 | 449.2 |
| billion-context | o200k_base | 1024 | 78.91% | 58.20% | 0.8277 | 754.4 |
| billion-context | o200k_base | 2048 | 78.91% | 58.20% | 0.8277 | 754.4 |

The six projections reuse the first native response. Three native search repetitions remain in raw ledgers; there are no extra diagnostic or replacement searches. ai-memory metadata hits consume original top-five slots, retain their native payload cost, and earn zero evidence credit. Packed-context MRR measures evidence order after metadata or oversized blocks are omitted; raw native positions remain recorded.

## Measured component boundaries

| Component | Search adapter p50/p95 ms | First search + all reads p50/p95 ms | Search payload cl100k/o200k | Read payload cl100k/o200k | Reads/query |
|---|---:|---:|---:|---:|---:|
| baseline-component | 3.133/5.828 | 3.165/5.942 | 3983.5/3998.4 | 0.0/0.0 | 0.00 |
| candidate-component | 1.766/2.784 | 1.756/2.818 | 3983.5/3998.4 | 0.0/0.0 | 0.00 |
| candidate-semantic-component | 7.415/11.226 | 7.365/11.046 | 4097.3/4112.5 | 0.0/0.0 | 0.00 |
| claude-mem-fts | 11.781/22.826 | 11.982/22.931 | 1641.3/1625.7 | 0.0/0.0 | 0.00 |
| ai-memory-hybrid | 21.168/27.545 | 23.966/30.532 | 1026.3/1023.4 | 1843.1/1834.9 | 5.00 |
| billion-context | 0.285/1.010 | 0.689/1.480 | 582.7/575.8 | 0.0/0.0 | 0.00 |

Search plus all reads sums each query's roundtrips before computing percentiles. Book is in-process Python including context assembly; claude-mem uses native SQLite/Bun; ai-memory uses local hybrid HTTP/MCP; billion-context uses its supplied-source search kernel/Node. These are distinct component boundaries, so no whole-product speed ratio follows. Native content, native payload and common packed context are separate token surfaces.

## Setup, RSS and state

| Mode | Setup wall ms | Setup RSS MiB | Query RSS MiB | Native state bytes |
|---|---:|---:|---:|---:|
| baseline-native | 4075.735 | 776.15 | 546.88 | 40280936 |
| candidate-native | 4235.636 | 549.47 | 533.07 | 40280936 |
| candidate-semantic-native | 115130.397 | 1286.11 | 1269.98 | 54988384 |
| baseline-component | 544.287 | 561.74 | 540.86 | 33808384 |
| candidate-component | 546.956 | 549.66 | 529.17 | 33808384 |
| candidate-semantic-component | 112553.168 | 1233.96 | 1234.28 | 54016064 |
| claude-mem-fts | 1589.911 | 675.75 | 635.18 | 20626650 |
| ai-memory-hybrid | 644734.591 | 716.75 | 714.48 | 73818921 |
| billion-context | 162.853 | 558.29 | 675.97 | 0 |

Native Book stages separately record fresh ingestion and optional model/index construction. Component Book stages copy one canonical archive and measure their own setup/index costs. Q2's persisted native/component index-vector digests match; this does not assert separately measured query-embedding identity. RSS is sampled worker-plus-descendants every 20 ms, includes evaluator/data memory, can double-count shared pages, and provides observed lower bounds. Database main/WAL/SHM, live statistics and optional TEMP-index costs remain in raw summaries; symlinked model caches are excluded from native state bytes.

## Low-overlap and multi-paragraph evidence

| Mode | Group at 512 cl100k | Questions | Complete evidence | Evidence recall |
|---|---|---:|---:|---:|
| baseline-native | low_lexical_overlap_le_0.25 | 6 | 0.00% | 33.33% |
| baseline-native | multiple_required_evidence | 256 | 35.94% | 65.73% |
| baseline-native | cross_session | 256 | 35.94% | 65.73% |
| baseline-native | cross_chapter | 256 | 35.94% | 65.73% |
| candidate-native | low_lexical_overlap_le_0.25 | 6 | 0.00% | 33.33% |
| candidate-native | multiple_required_evidence | 256 | 35.94% | 65.73% |
| candidate-native | cross_session | 256 | 35.94% | 65.73% |
| candidate-native | cross_chapter | 256 | 35.94% | 65.73% |
| candidate-semantic-native | low_lexical_overlap_le_0.25 | 6 | 0.00% | 50.00% |
| candidate-semantic-native | multiple_required_evidence | 256 | 33.59% | 64.74% |
| candidate-semantic-native | cross_session | 256 | 33.59% | 64.74% |
| candidate-semantic-native | cross_chapter | 256 | 33.59% | 64.74% |
| baseline-component | low_lexical_overlap_le_0.25 | 6 | 0.00% | 41.67% |
| baseline-component | multiple_required_evidence | 256 | 38.28% | 67.38% |
| baseline-component | cross_session | 256 | 38.28% | 67.38% |
| baseline-component | cross_chapter | 256 | 38.28% | 67.38% |
| candidate-component | low_lexical_overlap_le_0.25 | 6 | 0.00% | 41.67% |
| candidate-component | multiple_required_evidence | 256 | 38.28% | 67.38% |
| candidate-component | cross_session | 256 | 38.28% | 67.38% |
| candidate-component | cross_chapter | 256 | 38.28% | 67.38% |
| candidate-semantic-component | low_lexical_overlap_le_0.25 | 6 | 0.00% | 50.00% |
| candidate-semantic-component | multiple_required_evidence | 256 | 37.89% | 67.55% |
| candidate-semantic-component | cross_session | 256 | 37.89% | 67.55% |
| candidate-semantic-component | cross_chapter | 256 | 37.89% | 67.55% |
| claude-mem-fts | low_lexical_overlap_le_0.25 | 6 | 0.00% | 41.67% |
| claude-mem-fts | multiple_required_evidence | 256 | 33.20% | 61.29% |
| claude-mem-fts | cross_session | 256 | 33.20% | 61.29% |
| claude-mem-fts | cross_chapter | 256 | 33.20% | 61.29% |
| ai-memory-hybrid | low_lexical_overlap_le_0.25 | 6 | 16.67% | 58.33% |
| ai-memory-hybrid | multiple_required_evidence | 256 | 39.84% | 67.22% |
| ai-memory-hybrid | cross_session | 256 | 39.84% | 67.22% |
| ai-memory-hybrid | cross_chapter | 256 | 39.84% | 67.22% |
| billion-context | low_lexical_overlap_le_0.25 | 6 | 16.67% | 41.67% |
| billion-context | multiple_required_evidence | 256 | 37.50% | 65.73% |
| billion-context | cross_session | 256 | 37.50% | 65.73% |
| billion-context | cross_chapter | 256 | 37.50% | 65.73% |

Cross-session/chapter labels arise from mapping supplied encyclopedia paragraphs to sessions/chapters; they do not measure private conversational transfer. Small diagnostic groups are retained and their sample sizes limit conclusions. All selected questions are answerable, so abstention and hallucination rates are not measured.

Run: `43267797247-1`. Native calls: 4608; native component searches: 4608. Complete default payload equivalence: `True`. Optional project-statistics decision: `not-included`.

Every paired annotation/query gain and loss, all budget/tokenizer groups, repeat changes, native read costs and source hashes remain in the machine-readable assessment and stage reports. After first scoring these IDs are regression data. HotpotQA source is CC BY-SA 4.0; original questions, answers and passages are downloaded separately and are not published here.
