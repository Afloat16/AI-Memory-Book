# Round six: native APIs and supplied-page components

Candidate, evaluator, dependency/model and upstream source identities were committed before selecting these 256 IDs. The selection excludes all 896 IDs from Hotpot128 and the round-two, round-three and round-four Hotpot256 cohorts. It is another selection from the same HotpotQA source, not a new domain. These measurements assess returned source evidence, not generated-answer accuracy or a complete write/summarize/generate workflow.

Integrity passed for every registered query, budget and repetition. Q2 is excluded. All baseline and competitor gains and losses remain visible; integrity does not imply an advantage over another component.

## Native API

| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline-native | cl100k_base | 512 | 67.53% | 41.80% | 481.4 | 2.994 | 4.289 |
| baseline-native | cl100k_base | 1024 | 75.93% | 53.12% | 803.9 | 2.865 | 3.987 |
| baseline-native | cl100k_base | 2048 | 75.93% | 53.12% | 805.7 | 2.694 | 3.899 |
| baseline-native | o200k_base | 512 | 67.21% | 41.41% | 481.0 | 3.374 | 4.988 |
| baseline-native | o200k_base | 1024 | 75.93% | 53.12% | 802.5 | 2.977 | 4.245 |
| baseline-native | o200k_base | 2048 | 75.93% | 53.12% | 804.3 | 2.729 | 3.990 |
| candidate-native | cl100k_base | 512 | 67.53% | 41.80% | 481.4 | 3.091 | 4.415 |
| candidate-native | cl100k_base | 1024 | 75.93% | 53.12% | 803.9 | 2.885 | 4.087 |
| candidate-native | cl100k_base | 2048 | 75.93% | 53.12% | 805.7 | 2.702 | 3.923 |
| candidate-native | o200k_base | 512 | 67.21% | 41.41% | 481.0 | 3.345 | 4.819 |
| candidate-native | o200k_base | 1024 | 75.93% | 53.12% | 802.5 | 3.010 | 4.334 |
| candidate-native | o200k_base | 2048 | 75.93% | 53.12% | 804.3 | 2.782 | 4.000 |

Native calls use 8000 characters, top five, no result cache and one repetition. The independent ABBA old-data performance experiment supplies the release performance gate; these native measurements are not a substitute for that gate.

## Common whole-block projections

| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Packed-context MRR | Context tokens |
|---|---|---:|---:|---:|---:|---:|
| baseline-component | cl100k_base | 512 | 68.17% | 42.97% | 0.8451 | 452.4 |
| baseline-component | cl100k_base | 1024 | 75.93% | 53.12% | 0.8556 | 715.5 |
| baseline-component | cl100k_base | 2048 | 75.93% | 53.12% | 0.8556 | 716.4 |
| baseline-component | o200k_base | 512 | 68.17% | 43.36% | 0.8451 | 450.4 |
| baseline-component | o200k_base | 1024 | 75.93% | 53.12% | 0.8556 | 708.9 |
| baseline-component | o200k_base | 2048 | 75.93% | 53.12% | 0.8556 | 709.9 |
| candidate-component | cl100k_base | 512 | 68.17% | 42.97% | 0.8451 | 452.4 |
| candidate-component | cl100k_base | 1024 | 75.93% | 53.12% | 0.8556 | 715.5 |
| candidate-component | cl100k_base | 2048 | 75.93% | 53.12% | 0.8556 | 716.4 |
| candidate-component | o200k_base | 512 | 68.17% | 43.36% | 0.8451 | 450.4 |
| candidate-component | o200k_base | 1024 | 75.93% | 53.12% | 0.8556 | 708.9 |
| candidate-component | o200k_base | 2048 | 75.93% | 53.12% | 0.8556 | 709.9 |
| claude-mem-fts | cl100k_base | 512 | 62.04% | 35.55% | 0.7917 | 448.0 |
| claude-mem-fts | cl100k_base | 1024 | 70.60% | 48.05% | 0.8060 | 710.6 |
| claude-mem-fts | cl100k_base | 2048 | 70.60% | 48.05% | 0.8060 | 711.7 |
| claude-mem-fts | o200k_base | 512 | 62.20% | 35.94% | 0.7917 | 448.1 |
| claude-mem-fts | o200k_base | 1024 | 70.60% | 48.05% | 0.8060 | 704.2 |
| claude-mem-fts | o200k_base | 2048 | 70.60% | 48.05% | 0.8060 | 705.4 |
| ai-memory-hybrid | cl100k_base | 512 | 68.98% | 44.14% | 0.8171 | 447.9 |
| ai-memory-hybrid | cl100k_base | 1024 | 77.87% | 57.42% | 0.8279 | 715.3 |
| ai-memory-hybrid | cl100k_base | 2048 | 77.87% | 57.42% | 0.8279 | 716.4 |
| ai-memory-hybrid | o200k_base | 512 | 68.66% | 44.14% | 0.8158 | 447.2 |
| ai-memory-hybrid | o200k_base | 1024 | 77.87% | 57.42% | 0.8279 | 709.2 |
| ai-memory-hybrid | o200k_base | 2048 | 77.87% | 57.42% | 0.8279 | 710.3 |
| billion-context | cl100k_base | 512 | 69.14% | 41.80% | 0.8356 | 449.8 |
| billion-context | cl100k_base | 1024 | 80.94% | 60.55% | 0.8481 | 760.4 |
| billion-context | cl100k_base | 2048 | 80.94% | 60.55% | 0.8481 | 761.1 |
| billion-context | o200k_base | 512 | 70.11% | 42.97% | 0.8392 | 452.3 |
| billion-context | o200k_base | 1024 | 80.94% | 60.55% | 0.8481 | 752.9 |
| billion-context | o200k_base | 2048 | 80.94% | 60.55% | 0.8481 | 753.6 |

The six projections reuse the first native response. Three native search repetitions remain in raw ledgers; there are no extra diagnostic or replacement searches. ai-memory metadata hits consume original top-five slots, retain their native payload cost, and earn zero evidence credit. Packed-context MRR measures evidence order after metadata or oversized blocks are omitted; raw native positions remain recorded.

## Measured component boundaries

| Component | Search adapter p50/p95 ms | First search + all reads p50/p95 ms | Search payload cl100k/o200k | Read payload cl100k/o200k | Reads/query |
|---|---:|---:|---:|---:|---:|
| baseline-component | 2.351/3.518 | 2.354/3.535 | 3992.9/4012.9 | 0.0/0.0 | 0.00 |
| candidate-component | 2.374/3.582 | 2.362/3.573 | 3992.9/4012.9 | 0.0/0.0 | 0.00 |
| claude-mem-fts | 24.154/42.840 | 24.472/43.137 | 1634.7/1620.9 | 0.0/0.0 | 0.00 |
| ai-memory-hybrid | 31.474/40.409 | 37.212/46.338 | 1019.3/1017.7 | 1836.3/1830.8 | 5.00 |
| billion-context | 0.455/1.399 | 1.018/2.279 | 585.0/578.6 | 0.0/0.0 | 0.00 |

Search plus all reads sums each query's roundtrips before computing percentiles. Book is in-process Python including context assembly; claude-mem uses native SQLite/Bun; ai-memory uses local hybrid HTTP/MCP; billion-context uses its supplied-source search kernel/Node. These are distinct component boundaries, so no whole-product speed ratio follows. Native content, native payload and common packed context are separate token surfaces.

## Setup, RSS and state

| Mode | Setup wall ms | Setup RSS MiB | Query RSS MiB | Native state bytes |
|---|---:|---:|---:|---:|
| baseline-native | 3916.344 | 547.41 | 533.12 | 39037696 |
| candidate-native | 3890.425 | 551.45 | 537.18 | 39037696 |
| baseline-component | 840.940 | 531.80 | 511.84 | 34340864 |
| candidate-component | 843.362 | 525.79 | 504.87 | 34340864 |
| claude-mem-fts | 2444.687 | 682.05 | 594.81 | 20659514 |
| ai-memory-hybrid | 845167.166 | 706.79 | 710.69 | 74208780 |
| billion-context | 225.397 | 532.91 | 650.98 | 0 |

Native Book stages separately record fresh ingestion and initialization. Component Book stages copy one canonical archive and measure their own setup costs. Both Book modes are lexical; only ai-memory uses its locked local embedding model. RSS is sampled worker-plus-descendants every 20 ms, includes evaluator/data memory, can double-count shared pages, and provides observed lower bounds. Database main/WAL/SHM, live statistics remain in raw summaries; symlinked model caches are excluded from native state bytes.

## Low-overlap and multi-paragraph evidence

| Mode | Group at 512 cl100k | Questions | Complete evidence | Evidence recall |
|---|---|---:|---:|---:|
| baseline-native | low_lexical_overlap_le_0.25 | 7 | 0.00% | 35.29% |
| baseline-native | multiple_required_evidence | 256 | 41.80% | 67.53% |
| baseline-native | cross_session | 256 | 41.80% | 67.53% |
| baseline-native | cross_chapter | 256 | 41.80% | 67.53% |
| candidate-native | low_lexical_overlap_le_0.25 | 7 | 0.00% | 35.29% |
| candidate-native | multiple_required_evidence | 256 | 41.80% | 67.53% |
| candidate-native | cross_session | 256 | 41.80% | 67.53% |
| candidate-native | cross_chapter | 256 | 41.80% | 67.53% |
| baseline-component | low_lexical_overlap_le_0.25 | 7 | 0.00% | 29.41% |
| baseline-component | multiple_required_evidence | 256 | 42.97% | 68.17% |
| baseline-component | cross_session | 256 | 42.97% | 68.17% |
| baseline-component | cross_chapter | 256 | 42.97% | 68.17% |
| candidate-component | low_lexical_overlap_le_0.25 | 7 | 0.00% | 29.41% |
| candidate-component | multiple_required_evidence | 256 | 42.97% | 68.17% |
| candidate-component | cross_session | 256 | 42.97% | 68.17% |
| candidate-component | cross_chapter | 256 | 42.97% | 68.17% |
| claude-mem-fts | low_lexical_overlap_le_0.25 | 7 | 14.29% | 41.18% |
| claude-mem-fts | multiple_required_evidence | 256 | 35.55% | 62.04% |
| claude-mem-fts | cross_session | 256 | 35.55% | 62.04% |
| claude-mem-fts | cross_chapter | 256 | 35.55% | 62.04% |
| ai-memory-hybrid | low_lexical_overlap_le_0.25 | 7 | 28.57% | 41.18% |
| ai-memory-hybrid | multiple_required_evidence | 256 | 44.14% | 68.98% |
| ai-memory-hybrid | cross_session | 256 | 44.14% | 68.98% |
| ai-memory-hybrid | cross_chapter | 256 | 44.14% | 68.98% |
| billion-context | low_lexical_overlap_le_0.25 | 7 | 28.57% | 58.82% |
| billion-context | multiple_required_evidence | 256 | 41.80% | 69.14% |
| billion-context | cross_session | 256 | 41.80% | 69.14% |
| billion-context | cross_chapter | 256 | 41.80% | 69.14% |

Cross-session/chapter labels arise from mapping supplied encyclopedia paragraphs to sessions/chapters; they do not measure private conversational transfer. Small diagnostic groups are retained and their sample sizes limit conclusions. All selected questions are answerable, so abstention and hallucination rates are not measured.

Run: `43601518020-1`. Native calls: 3072; native component searches: 3840. Complete default payload equivalence: `True`. Q2 and project-statistics candidates are excluded. Complete default output equality is required; no quality-changing candidate is included.

Every paired annotation/query gain and loss, all budget/tokenizer groups, repeat changes, native read costs and source hashes remain in the machine-readable assessment and stage reports. After first scoring these IDs are regression data. HotpotQA source is CC BY-SA 4.0; original questions, answers and passages are downloaded separately and are not published here.

## Exact sources and upstream identities

| Role | Commit | Runtime SHA256 or locked version |
|---|---|---|
| Book baseline | `796cedfd1f5368144037a1fb72292b8d13884b8c` | `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45` |
| Book candidate | `df35007c29e4af61dd96146232fe4651cfc74391` | `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242` |
| claude-mem | `c4a9f5725f420bf9c6e866cdd3b94bd36498af09` | 15.18.1 |
| billion-context | `9674cfafbc78c50245ae0d887483d3d6ce880c15` | locked search kernel |
| ai-memory | `ee73c04c542fa41ca629b046deb4ac108518f407` | v3.4.5 |

Binding SHA256 `1cec59b1955ff1be479f58211c12077f99e62b5ebea959b04e41898e1fe6720f`; selected-ID SHA256 `916971c92eec3267011f1b4bddf181950debe292596ca0d71b3b5336d87c293e`. The exact dependency, binary, model and source-lock hashes remain in the committed binding and machine-readable assessment.

## Candidate versus every external component

Each row compares the same first-response whole-block projection. Positive complete-evidence change favors the candidate. Per-question and annotation gains and losses are retained in assessment.json; neither adverse rows nor ties are omitted.

| Comparator | Tokenizer | Cap | Candidate minus comparator complete evidence, pp | Complete question gains | Complete question losses |
|---|---|---:|---:|---:|---:|
| claude-mem-fts | cl100k_base | 512 | +7.4219 | 28 | 9 |
| claude-mem-fts | cl100k_base | 1024 | +5.0781 | 24 | 11 |
| claude-mem-fts | cl100k_base | 2048 | +5.0781 | 24 | 11 |
| claude-mem-fts | o200k_base | 512 | +7.4219 | 29 | 10 |
| claude-mem-fts | o200k_base | 1024 | +5.0781 | 24 | 11 |
| claude-mem-fts | o200k_base | 2048 | +5.0781 | 24 | 11 |
| ai-memory-hybrid | cl100k_base | 512 | -1.1719 | 27 | 30 |
| ai-memory-hybrid | cl100k_base | 1024 | -4.2969 | 16 | 27 |
| ai-memory-hybrid | cl100k_base | 2048 | -4.2969 | 16 | 27 |
| ai-memory-hybrid | o200k_base | 512 | -0.7812 | 27 | 29 |
| ai-memory-hybrid | o200k_base | 1024 | -4.2969 | 16 | 27 |
| ai-memory-hybrid | o200k_base | 2048 | -4.2969 | 16 | 27 |
| billion-context | cl100k_base | 512 | +1.1719 | 43 | 40 |
| billion-context | cl100k_base | 1024 | -7.4219 | 28 | 47 |
| billion-context | cl100k_base | 2048 | -7.4219 | 28 | 47 |
| billion-context | o200k_base | 512 | +0.3906 | 40 | 39 |
| billion-context | o200k_base | 1024 | -7.4219 | 28 | 47 |
| billion-context | o200k_base | 2048 | -7.4219 | 28 | 47 |

The registered matrix has **42 quality cells**, **6,912 native retrieval/search calls** and **1,280 separately counted ai-memory page reads**. No generated-answer call is made. Search timing is sequential and descriptive; the independent registered 10%/15%/10% balanced performance gates are assessed separately.

All native p50/p95, component first/repeat search distributions, offline packing, setup, RSS and storage values remain in the complete stage reports, including regressions. A comparison win does not establish whole-product, cross-domain or universal superiority.
