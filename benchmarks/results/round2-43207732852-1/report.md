# Round two: fixed-candidate protocol recovery on one host

The original run stopped at the first claude-mem request because the evaluator expected another adapter's response field. The complete matrix below was rerun on one new host after a registered interface-only correction. The candidate, source versions, 256 IDs, all budgets and repetitions remain exactly as first frozen; the selection had already been scored and this report is not an unseen tuning validation. The prior incomplete results and their timing attribution are retained, without pooling or choosing faster rows. Original run: `43201620535`; preserved results: `150d37799098aa1fb1ddcebe5b42b18954adc035`.

Integrity checks passed for every registered engine, configuration and repetition. This does not declare a quality improvement. Every selected paragraph and support annotation remains in the denominators.

## Native API: complete evidence and latency

| Mode | Characters | Tokenizer | Tokens | Evidence recall | Complete evidence | Context tokens | p50 ms | p95 ms |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| baseline-native | 2000 | cl100k_base | 512 | 55.37% | 24.22% | 484.7 | 8.957 | 14.347 |
| baseline-native | 2000 | cl100k_base | 1024 | 59.12% | 28.52% | 674.1 | 8.376 | 13.642 |
| baseline-native | 2000 | cl100k_base | 2048 | 59.12% | 28.52% | 674.1 | 8.343 | 13.683 |
| baseline-native | 2000 | o200k_base | 512 | 55.54% | 24.22% | 482.9 | 9.693 | 15.277 |
| baseline-native | 2000 | o200k_base | 1024 | 59.12% | 28.52% | 674.5 | 8.856 | 14.187 |
| baseline-native | 2000 | o200k_base | 2048 | 59.12% | 28.52% | 674.5 | 8.810 | 14.099 |
| baseline-native | 8000 | cl100k_base | 512 | 68.73% | 41.41% | 478.5 | 7.140 | 10.808 |
| baseline-native | 8000 | cl100k_base | 1024 | 75.57% | 51.95% | 801.7 | 6.456 | 10.029 |
| baseline-native | 8000 | cl100k_base | 2048 | 75.57% | 51.95% | 802.8 | 6.493 | 10.116 |
| baseline-native | 8000 | o200k_base | 512 | 69.06% | 42.19% | 478.7 | 8.049 | 11.921 |
| baseline-native | 8000 | o200k_base | 1024 | 75.57% | 51.95% | 799.7 | 7.078 | 10.667 |
| baseline-native | 8000 | o200k_base | 2048 | 75.57% | 51.95% | 801.3 | 7.176 | 10.741 |
| candidate-native | 2000 | cl100k_base | 512 | 55.37% | 24.22% | 484.7 | 8.449 | 13.849 |
| candidate-native | 2000 | cl100k_base | 1024 | 59.12% | 28.52% | 674.1 | 7.931 | 13.325 |
| candidate-native | 2000 | cl100k_base | 2048 | 59.12% | 28.52% | 674.1 | 7.941 | 13.236 |
| candidate-native | 2000 | o200k_base | 512 | 55.54% | 24.22% | 482.9 | 9.214 | 14.606 |
| candidate-native | 2000 | o200k_base | 1024 | 59.12% | 28.52% | 674.5 | 8.424 | 13.698 |
| candidate-native | 2000 | o200k_base | 2048 | 59.12% | 28.52% | 674.5 | 8.411 | 13.705 |
| candidate-native | 8000 | cl100k_base | 512 | 68.73% | 41.41% | 478.5 | 6.781 | 10.442 |
| candidate-native | 8000 | cl100k_base | 1024 | 75.57% | 51.95% | 801.7 | 6.150 | 9.841 |
| candidate-native | 8000 | cl100k_base | 2048 | 75.57% | 51.95% | 802.8 | 6.105 | 9.863 |
| candidate-native | 8000 | o200k_base | 512 | 69.06% | 42.19% | 478.7 | 7.664 | 11.568 |
| candidate-native | 8000 | o200k_base | 1024 | 75.57% | 51.95% | 799.7 | 6.726 | 10.265 |
| candidate-native | 8000 | o200k_base | 2048 | 75.57% | 51.95% | 801.3 | 6.748 | 10.259 |
| candidate-semantic-native | 2000 | cl100k_base | 512 | 55.05% | 24.22% | 487.6 | 17.775 | 28.976 |
| candidate-semantic-native | 2000 | cl100k_base | 1024 | 60.75% | 32.81% | 674.6 | 17.177 | 28.208 |
| candidate-semantic-native | 2000 | cl100k_base | 2048 | 60.75% | 32.81% | 674.6 | 17.074 | 27.704 |
| candidate-semantic-native | 2000 | o200k_base | 512 | 54.72% | 23.83% | 486.3 | 18.398 | 29.377 |
| candidate-semantic-native | 2000 | o200k_base | 1024 | 60.75% | 32.81% | 675.1 | 17.519 | 28.395 |
| candidate-semantic-native | 2000 | o200k_base | 2048 | 60.75% | 32.81% | 675.1 | 17.500 | 28.212 |
| candidate-semantic-native | 8000 | cl100k_base | 512 | 68.24% | 41.41% | 477.1 | 15.902 | 24.848 |
| candidate-semantic-native | 8000 | cl100k_base | 1024 | 78.50% | 57.42% | 816.2 | 15.517 | 24.227 |
| candidate-semantic-native | 8000 | cl100k_base | 2048 | 78.66% | 57.81% | 819.1 | 15.499 | 23.994 |
| candidate-semantic-native | 8000 | o200k_base | 512 | 68.24% | 41.02% | 477.7 | 16.899 | 25.978 |
| candidate-semantic-native | 8000 | o200k_base | 1024 | 78.50% | 57.42% | 814.9 | 16.068 | 25.036 |
| candidate-semantic-native | 8000 | o200k_base | 2048 | 78.66% | 57.81% | 817.8 | 16.075 | 24.876 |

## Shared-page component quality

Identical supplied pages, project scope, top-five limit, citation format and whole-block packer. Component quality is measured on the first pass; all three repetitions' native hits, timings and any repeat differences remain in the raw reports.

| Component | Tokenizer | Tokens | Evidence recall | Complete evidence | Packed-context MRR | Context tokens |
|---|---|---:|---:|---:|---:|---:|
| baseline-component | cl100k_base | 512 | 68.89% | 41.41% | 0.8516 | 450.5 |
| baseline-component | cl100k_base | 1024 | 75.41% | 51.95% | 0.8596 | 712.9 |
| baseline-component | cl100k_base | 2048 | 75.57% | 51.95% | 0.8604 | 713.6 |
| baseline-component | o200k_base | 512 | 69.22% | 41.80% | 0.8525 | 447.3 |
| baseline-component | o200k_base | 1024 | 75.41% | 51.95% | 0.8596 | 706.2 |
| baseline-component | o200k_base | 2048 | 75.57% | 51.95% | 0.8604 | 706.9 |
| candidate-component | cl100k_base | 512 | 68.89% | 41.41% | 0.8516 | 450.5 |
| candidate-component | cl100k_base | 1024 | 75.41% | 51.95% | 0.8596 | 712.9 |
| candidate-component | cl100k_base | 2048 | 75.57% | 51.95% | 0.8604 | 713.6 |
| candidate-component | o200k_base | 512 | 69.22% | 41.80% | 0.8525 | 447.3 |
| candidate-component | o200k_base | 1024 | 75.41% | 51.95% | 0.8596 | 706.2 |
| candidate-component | o200k_base | 2048 | 75.57% | 51.95% | 0.8604 | 706.9 |
| claude-mem-fts | cl100k_base | 512 | 64.33% | 38.67% | 0.8213 | 451.8 |
| claude-mem-fts | cl100k_base | 1024 | 72.31% | 48.83% | 0.8348 | 704.5 |
| claude-mem-fts | cl100k_base | 2048 | 72.31% | 48.83% | 0.8348 | 705.6 |
| claude-mem-fts | o200k_base | 512 | 63.84% | 37.89% | 0.8213 | 449.6 |
| claude-mem-fts | o200k_base | 1024 | 72.31% | 48.83% | 0.8348 | 698.0 |
| claude-mem-fts | o200k_base | 2048 | 72.31% | 48.83% | 0.8348 | 699.1 |
| ai-memory-hybrid | cl100k_base | 512 | 68.89% | 41.41% | 0.8568 | 452.0 |
| ai-memory-hybrid | cl100k_base | 1024 | 76.22% | 53.91% | 0.8633 | 704.0 |
| ai-memory-hybrid | cl100k_base | 2048 | 76.38% | 53.91% | 0.8641 | 704.8 |
| ai-memory-hybrid | o200k_base | 512 | 69.06% | 41.80% | 0.8558 | 451.6 |
| ai-memory-hybrid | o200k_base | 1024 | 76.22% | 53.91% | 0.8633 | 697.7 |
| ai-memory-hybrid | o200k_base | 2048 | 76.38% | 53.91% | 0.8641 | 698.4 |
| billion-context | cl100k_base | 512 | 71.01% | 46.48% | 0.8535 | 452.2 |
| billion-context | cl100k_base | 1024 | 80.94% | 61.72% | 0.8622 | 751.3 |
| billion-context | cl100k_base | 2048 | 80.94% | 61.72% | 0.8622 | 752.4 |
| billion-context | o200k_base | 512 | 70.85% | 46.48% | 0.8522 | 452.1 |
| billion-context | o200k_base | 1024 | 80.94% | 61.72% | 0.8622 | 744.6 |
| billion-context | o200k_base | 2048 | 80.94% | 61.72% | 0.8622 | 745.7 |
| candidate-semantic-component | cl100k_base | 512 | 69.38% | 42.19% | 0.8610 | 453.8 |
| candidate-semantic-component | cl100k_base | 1024 | 78.66% | 57.81% | 0.8686 | 727.8 |
| candidate-semantic-component | cl100k_base | 2048 | 78.66% | 57.81% | 0.8686 | 729.9 |
| candidate-semantic-component | o200k_base | 512 | 69.38% | 42.19% | 0.8610 | 451.0 |
| candidate-semantic-component | o200k_base | 1024 | 78.66% | 57.81% | 0.8686 | 721.3 |
| candidate-semantic-component | o200k_base | 2048 | 78.66% | 57.81% | 0.8686 | 723.4 |

## Search and returned-payload boundaries

| Component | Adapter p50 ms | Adapter p95 ms | First search + reads p50 / p95 ms | Search payload o200k | Full-read payload o200k | Reads/question | Mean full-read ms | Metadata hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline-component | 5.078 | 8.489 | 5.116 / 8.523 | 4001.8 | 0.0 | 0.00 | 0.000 | 0 |
| candidate-component | 4.712 | 8.301 | 4.713 / 8.396 | 4001.8 | 0.0 | 0.00 | 0.000 | 0 |
| claude-mem-fts | 16.254 | 29.948 | 16.218 / 30.056 | 1612.3 | 0.0 | 0.00 | 0.000 | 0 |
| ai-memory-hybrid | 25.947 | 33.251 | 30.292 / 37.613 | 1016.3 | 1811.5 | 4.98 | 4.294 | 0 |
| billion-context | 0.349 | 1.092 | 0.756 / 1.410 | 579.3 | 0.0 | 0.00 | 0.000 | 0 |
| candidate-semantic-component | 14.014 | 22.523 | 13.895 / 22.530 | 4099.1 | 0.0 | 0.00 | 0.000 | 0 |

Book is in-process Python including its native context assembly; claude-mem is SQLite FTS through Bun; ai-memory is local hybrid through HTTP/MCP; billion-context is its native search kernel through Node. Timings share a host but do not establish a whole-product speed multiplier. ai-memory reads every mapped top-five page on the first pass under a fixed policy; an agent could choose fewer reads. Native payload, text-only content and common packed evidence are distinct token surfaces.

## Low-overlap and multi-hop groups

Below is the registered 512-token cl100k view (8,000 characters for native APIs). All other group/budget rows remain in each machine-readable summary.

| Mode | Group | Questions | Complete evidence | Evidence recall |
|---|---|---:|---:|---:|
| baseline-native | low_lexical_overlap_le_0.25 | 9 | 0.00% | 33.33% |
| baseline-native | multiple_required_evidence | 256 | 41.41% | 68.73% |
| baseline-native | cross_session | 256 | 41.41% | 68.73% |
| baseline-native | cross_chapter | 256 | 41.41% | 68.73% |
| candidate-native | low_lexical_overlap_le_0.25 | 9 | 0.00% | 33.33% |
| candidate-native | multiple_required_evidence | 256 | 41.41% | 68.73% |
| candidate-native | cross_session | 256 | 41.41% | 68.73% |
| candidate-native | cross_chapter | 256 | 41.41% | 68.73% |
| baseline-component | low_lexical_overlap_le_0.25 | 9 | 0.00% | 33.33% |
| baseline-component | multiple_required_evidence | 256 | 41.41% | 68.89% |
| baseline-component | cross_session | 256 | 41.41% | 68.89% |
| baseline-component | cross_chapter | 256 | 41.41% | 68.89% |
| candidate-component | low_lexical_overlap_le_0.25 | 9 | 0.00% | 33.33% |
| candidate-component | multiple_required_evidence | 256 | 41.41% | 68.89% |
| candidate-component | cross_session | 256 | 41.41% | 68.89% |
| candidate-component | cross_chapter | 256 | 41.41% | 68.89% |
| claude-mem-fts | low_lexical_overlap_le_0.25 | 9 | 11.11% | 38.89% |
| claude-mem-fts | multiple_required_evidence | 256 | 38.67% | 64.33% |
| claude-mem-fts | cross_session | 256 | 38.67% | 64.33% |
| claude-mem-fts | cross_chapter | 256 | 38.67% | 64.33% |
| ai-memory-hybrid | low_lexical_overlap_le_0.25 | 9 | 11.11% | 38.89% |
| ai-memory-hybrid | multiple_required_evidence | 256 | 41.41% | 68.89% |
| ai-memory-hybrid | cross_session | 256 | 41.41% | 68.89% |
| ai-memory-hybrid | cross_chapter | 256 | 41.41% | 68.89% |
| billion-context | low_lexical_overlap_le_0.25 | 9 | 11.11% | 38.89% |
| billion-context | multiple_required_evidence | 256 | 46.48% | 71.01% |
| billion-context | cross_session | 256 | 46.48% | 71.01% |
| billion-context | cross_chapter | 256 | 46.48% | 71.01% |
| candidate-semantic-native | low_lexical_overlap_le_0.25 | 9 | 11.11% | 38.89% |
| candidate-semantic-native | multiple_required_evidence | 256 | 41.41% | 68.24% |
| candidate-semantic-native | cross_session | 256 | 41.41% | 68.24% |
| candidate-semantic-native | cross_chapter | 256 | 41.41% | 68.24% |
| candidate-semantic-component | low_lexical_overlap_le_0.25 | 9 | 0.00% | 33.33% |
| candidate-semantic-component | multiple_required_evidence | 256 | 42.19% | 69.38% |
| candidate-semantic-component | cross_session | 256 | 42.19% | 69.38% |
| candidate-semantic-component | cross_chapter | 256 | 42.19% | 69.38% |

## Preparation, memory and storage

| Mode | Setup wall ms | Setup RSS peak MiB | Query RSS peak MiB | Native-state bytes | SQLite main / WAL / SHM bytes |
|---|---:|---:|---:|---:|---|
| baseline-native | 6569.520 | 333.63 | 280.66 | 37222984 | 31821824/5368392/32768 |
| candidate-native | 4941.237 | 333.63 | 280.68 | 37222984 | 31821824/5368392/32768 |
| baseline-component | 225.417 | 333.48 | 224.10 | 32104448 | 32071680/0/32768 |
| candidate-component | 226.361 | 333.62 | 224.00 | 32104448 | 32071680/0/32768 |
| claude-mem-fts | 2005.361 | 415.58 | 377.07 | 20059746 | 8507392/11519552/32768 |
| ai-memory-hybrid | 679306.927 | 469.82 | 469.20 | 70691093 | 17997824/4268352/32768 |
| billion-context | 173.227 | 333.51 | 401.94 | 0 | n/a/n/a/n/a |
| candidate-semantic-native | 213432.411 | 1012.74 | 1041.29 | 55396480 | 41635840/13727872/32768 |
| candidate-semantic-component | 208928.801 | 969.62 | 970.07 | 51309440 | 41635840/9640832/32768 |

Setup is outside query timing. Native Book reports separate source ingestion and optional index construction; component Book opens a common frozen archive. Upstream metadata separately records native write/index/startup phases when available. Billion's supplied-source component keeps its index in memory. Preparation download/cache sizes and elapsed time are retained in the run checkpoint. No model generation calls are configured.

RSS is the worker plus its descendants sampled every 20 ms, including the evaluator and loaded corpus. Sampling yields an observed lower bound and summed RSS can double-count shared pages; this is not unique physical memory. Native-state bytes exclude the harness attempt ledger and symlinked model caches. Full phase metadata, vector bytes and database statistics remain in the raw/summary reports.

Native ai-memory metadata pages retain their original top-k slots and complete native payload cost. Their missing supplied-document mapping is recorded as null and earns zero evidence credit; the evaluator does not replace them with extra hits. Unknown non-null supplied IDs, duplicated identities and scope mismatches fail integrity checks. MRR describes evidence order in the packed context, after omitted metadata or oversized blocks; original native top-five positions remain in the raw hit records.

## Provenance and limitations

- Run: `43207732852-1`; source: `cb64db805f8f822fee00cc453c523cfa06c2ce8f`.
- Dataset SHA256: `19aa783140212cc6532581c2791e6384769b0647dd4f08e2db29687400a798ae`; selected-ID SHA256: `912e3c8d0f26f1a247de321709a9528e76d08f8ad70f9d7c9169b97c638be11a`.
- Native baseline/candidate paired query/configuration cases: **3072**.
- Required source annotations: **614**; supplied paragraphs: **2539**.
- All cases are answerable; this selection does not measure abstention, hallucination or final-answer accuracy.
- HotpotQA is licensed CC BY-SA 4.0. Original questions, answers and source passages are downloaded separately and are not committed in these reports.
- Low-overlap membership uses frozen baseline term analysis, and evidence labels remain outside ranking/indexing/packing.
- Once scored, this selection becomes regression data. No outcome-driven retuning is claimed as the same heldout test.
- A structural evidence-attainability diagnostic is retained in the export report; affected cases are never dropped.
- Product source revisions, host/package details, input/output hashes and all failed/started intent records are preserved in the corresponding raw report and checkpoint.
