# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

**Release stage:** final.

Fresh Python process: True; package source unchanged during run: True; per-query quality differences from pre-release: 0.

## Dataset and runtime

- Dataset: version 2.0, `heldout`, seed `47`.
- Fingerprint: `a9d311f84a7f1c5f174ddddc91409b77c0bf08329f78eeb03a603acf57c50b7a`.
- Size: 8 projects, 112 sessions, 1408 user turns, 1,143,318 source characters, 168 queries (152 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Engine Python source fingerprint: `57c1d2d0ac42530b17757ea5b0278bf394ebc3e631ca541c832117edc2371a60`.
- Run: 2026-11-11T08:53:42.535880+00:00 to 2026-11-11T08:57:57.340423+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=900, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

Both ranking strategies use the same metadata-aware FTS index. `book` adds soft directory-overlap reranking to `flat`; this experiment does not compare hierarchy against an index stripped of all directory metadata.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 68.8% | 73.0% | 0.671 | 1,904 | 60.214 | 126.211 |
| session | book | 2000 | 68.8% | 73.0% | 0.678 | 1,904 | 63.533 | 161.234 |
| session | flat | 8000 | 69.3% | 73.7% | 0.656 | 5,379 | 75.944 | 134.942 |
| session | book | 8000 | 69.3% | 73.7% | 0.667 | 5,411 | 66.503 | 141.150 |
| turn | flat | 2000 | 56.2% | 54.6% | 0.588 | 1,708 | 5.697 | 22.701 |
| turn | book | 2000 | 56.2% | 54.6% | 0.588 | 1,706 | 5.947 | 25.997 |
| turn | flat | 8000 | 64.8% | 59.9% | 0.650 | 3,891 | 5.413 | 25.795 |
| turn | book | 8000 | 64.8% | 59.9% | 0.650 | 3,881 | 5.254 | 24.034 |
| adaptive | flat | 2000 | 71.6% | 72.4% | 0.726 | 1,948 | 6.001 | 11.730 |
| adaptive | book | 2000 | 71.6% | 72.4% | 0.726 | 1,948 | 5.779 | 10.170 |
| adaptive | flat | 8000 | 77.3% | 78.9% | 0.765 | 3,711 | 4.661 | 7.918 |
| adaptive | book | 8000 | 77.3% | 78.9% | 0.765 | 3,701 | 4.600 | 7.456 |

## Failure diagnostics

A nonempty result for an unanswerable question is a retrieval diagnostic, not proof that a model would fabricate an answer. Stale-only means old evidence was returned without current evidence for a current-state query.

| Segmentation | Retrieval | Budget | Unanswerable nonempty | Latest stale-only | Old before current | Budget violations | Size mismatches |
|---|---|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| session | book | 2000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| session | flat | 8000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| session | book | 8000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| turn | flat | 2000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| turn | book | 2000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| turn | flat | 8000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| turn | book | 8000 | 100.0% | 50.0% | 0.0% | 0 | 0 |
| adaptive | flat | 2000 | 100.0% | 0.0% | 50.0% | 0 | 0 |
| adaptive | book | 2000 | 100.0% | 0.0% | 50.0% | 0 | 0 |
| adaptive | flat | 8000 | 100.0% | 0.0% | 50.0% | 0 | 0 |
| adaptive | book | 8000 | 100.0% | 0.0% | 50.0% | 0 | 0 |

## Evidence recall by category

The same category is measured for all configurations; low lexical overlap and short follow-ups are retained even when they fail.

| Segmentation | Retrieval | Budget | Category | Queries | Evidence recall | Complete |
|---|---|---:|---|---:|---:|---:|
| session | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 2000 | cross_session | 8 | 75.0% | 50.0% |
| session | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| session | flat | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| session | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | flat | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 2000 | multi_section | 16 | 6.2% | 0.0% |
| session | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | flat | 2000 | topic_change | 16 | 50.0% | 50.0% |
| session | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 2000 | cross_session | 8 | 75.0% | 50.0% |
| session | book | 2000 | historical | 8 | 100.0% | 100.0% |
| session | book | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| session | book | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| session | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | book | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 2000 | multi_section | 16 | 6.2% | 0.0% |
| session | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 2000 | topic_change | 16 | 50.0% | 50.0% |
| session | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 8000 | cross_session | 8 | 100.0% | 100.0% |
| session | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| session | flat | 8000 | long_answer_middle | 8 | 87.5% | 87.5% |
| session | flat | 8000 | long_answer_natural_late | 16 | 93.8% | 93.8% |
| session | flat | 8000 | long_answer_natural_middle | 16 | 93.8% | 93.8% |
| session | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 8000 | multi_section | 16 | 6.2% | 0.0% |
| session | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| session | flat | 8000 | topic_change | 16 | 43.8% | 43.8% |
| session | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 8000 | cross_session | 8 | 100.0% | 100.0% |
| session | book | 8000 | historical | 8 | 100.0% | 100.0% |
| session | book | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| session | book | 8000 | long_answer_middle | 8 | 87.5% | 87.5% |
| session | book | 8000 | long_answer_natural_late | 16 | 93.8% | 93.8% |
| session | book | 8000 | long_answer_natural_middle | 16 | 93.8% | 93.8% |
| session | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 8000 | multi_section | 16 | 6.2% | 0.0% |
| session | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 8000 | topic_change | 16 | 43.8% | 43.8% |
| turn | flat | 2000 | cross_project_name | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | cross_session | 8 | 75.0% | 50.0% |
| turn | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | latest_decision | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| turn | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | flat | 2000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| turn | flat | 2000 | lookup | 24 | 83.3% | 83.3% |
| turn | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | multi_section | 16 | 25.0% | 0.0% |
| turn | flat | 2000 | short_followup | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | topic_change | 16 | 50.0% | 50.0% |
| turn | book | 2000 | cross_project_name | 8 | 0.0% | 0.0% |
| turn | book | 2000 | cross_session | 8 | 75.0% | 50.0% |
| turn | book | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 2000 | latest_decision | 8 | 0.0% | 0.0% |
| turn | book | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| turn | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | book | 2000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| turn | book | 2000 | lookup | 24 | 83.3% | 83.3% |
| turn | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 2000 | multi_section | 16 | 25.0% | 0.0% |
| turn | book | 2000 | short_followup | 8 | 0.0% | 0.0% |
| turn | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 2000 | topic_change | 16 | 50.0% | 50.0% |
| turn | flat | 8000 | cross_project_name | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | cross_session | 8 | 75.0% | 50.0% |
| turn | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | latest_decision | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | long_answer_middle | 8 | 87.5% | 87.5% |
| turn | flat | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | flat | 8000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| turn | flat | 8000 | lookup | 24 | 83.3% | 83.3% |
| turn | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | multi_section | 16 | 46.9% | 0.0% |
| turn | flat | 8000 | short_followup | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | topic_change | 16 | 100.0% | 100.0% |
| turn | book | 8000 | cross_project_name | 8 | 0.0% | 0.0% |
| turn | book | 8000 | cross_session | 8 | 75.0% | 50.0% |
| turn | book | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 8000 | latest_decision | 8 | 0.0% | 0.0% |
| turn | book | 8000 | long_answer_middle | 8 | 87.5% | 87.5% |
| turn | book | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | book | 8000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| turn | book | 8000 | lookup | 24 | 83.3% | 83.3% |
| turn | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 8000 | multi_section | 16 | 46.9% | 0.0% |
| turn | book | 8000 | short_followup | 8 | 0.0% | 0.0% |
| turn | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 8000 | topic_change | 16 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_session | 8 | 75.0% | 50.0% |
| adaptive | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| adaptive | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| adaptive | flat | 2000 | lookup | 24 | 83.3% | 83.3% |
| adaptive | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 2000 | multi_section | 16 | 25.0% | 0.0% |
| adaptive | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | topic_change | 16 | 68.8% | 68.8% |
| adaptive | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | cross_session | 8 | 75.0% | 50.0% |
| adaptive | book | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_middle | 8 | 87.5% | 87.5% |
| adaptive | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| adaptive | book | 2000 | lookup | 24 | 83.3% | 83.3% |
| adaptive | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 2000 | multi_section | 16 | 25.0% | 0.0% |
| adaptive | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | topic_change | 16 | 68.8% | 68.8% |
| adaptive | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| adaptive | flat | 8000 | lookup | 24 | 83.3% | 83.3% |
| adaptive | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 8000 | multi_section | 16 | 25.0% | 0.0% |
| adaptive | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | topic_change | 16 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_natural_middle | 16 | 75.0% | 75.0% |
| adaptive | book | 8000 | lookup | 24 | 83.3% | 83.3% |
| adaptive | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 8000 | multi_section | 16 | 25.0% | 0.0% |
| adaptive | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | topic_change | 16 | 100.0% | 100.0% |

## Ingestion and storage

Mean page characters uses the engine's stored page text, including speaker labels but excluding separately stored title metadata. File size includes SQLite WAL/SHM files present after ingestion.

| Segmentation | Pages | Mean page chars | Ingest ms | Sessions/sec | DB + WAL bytes |
|---|---:|---:|---:|---:|---:|
| session | 112 | 10,470 | 552.53 | 202.70 | 14,994,440 |
| turn | 1408 | 831 | 682.27 | 164.16 | 16,712,848 |
| adaptive | 1912 | 612 | 882.82 | 126.87 | 19,567,216 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| session | flat | 2000 | 56.232 | 0.226 | 0.349 | 100.0% |
| session | book | 2000 | 51.534 | 0.185 | 0.532 | 100.0% |
| session | flat | 8000 | 54.751 | 0.251 | 1.252 | 100.0% |
| session | book | 8000 | 52.006 | 0.265 | 1.171 | 100.0% |
| turn | flat | 2000 | 7.309 | 0.137 | 0.248 | 100.0% |
| turn | book | 2000 | 12.855 | 0.143 | 0.256 | 100.0% |
| turn | flat | 8000 | 6.928 | 0.174 | 0.380 | 100.0% |
| turn | book | 8000 | 6.197 | 0.160 | 0.263 | 100.0% |
| adaptive | flat | 2000 | 8.199 | 0.150 | 0.277 | 100.0% |
| adaptive | book | 2000 | 10.019 | 0.153 | 0.260 | 100.0% |
| adaptive | flat | 8000 | 6.399 | 0.162 | 0.256 | 100.0% |
| adaptive | book | 8000 | 7.672 | 0.161 | 0.309 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Each retrieved unit contributes one query-centered excerpt. A separately optimized multi-window whole-session retriever is not tested.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](heldout-47-v2-900.json.gz) · [Compact machine-readable summary](heldout-47-v2-900.summary.json)
