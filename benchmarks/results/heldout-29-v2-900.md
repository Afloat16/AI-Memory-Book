# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

**Release stage:** final.

Fresh Python process: True; package source unchanged during run: True; per-query quality differences from pre-release: 0.

## Dataset and runtime

- Dataset: version 2.0, `heldout`, seed `29`.
- Fingerprint: `b607522315198671e26bfd35379c9aeb28368fd800d9cad7e085cc86a12eee07`.
- Size: 8 projects, 112 sessions, 1408 user turns, 1,143,343 source characters, 168 queries (152 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Engine Python source fingerprint: `57c1d2d0ac42530b17757ea5b0278bf394ebc3e631ca541c832117edc2371a60`.
- Run: 2026-11-11T08:49:54.854764+00:00 to 2026-11-11T08:53:40.683779+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=900, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

Both ranking strategies use the same metadata-aware FTS index. `book` adds soft directory-overlap reranking to `flat`; this experiment does not compare hierarchy against an index stripped of all directory metadata.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 68.8% | 73.0% | 0.671 | 1,903 | 53.793 | 106.337 |
| session | book | 2000 | 68.8% | 73.0% | 0.678 | 1,903 | 53.538 | 107.365 |
| session | flat | 8000 | 69.9% | 74.3% | 0.662 | 5,379 | 60.821 | 119.987 |
| session | book | 8000 | 69.9% | 74.3% | 0.674 | 5,411 | 56.583 | 112.869 |
| turn | flat | 2000 | 56.2% | 54.6% | 0.588 | 1,708 | 5.563 | 22.959 |
| turn | book | 2000 | 56.2% | 54.6% | 0.588 | 1,706 | 5.639 | 23.610 |
| turn | flat | 8000 | 65.3% | 60.5% | 0.657 | 3,888 | 4.648 | 23.357 |
| turn | book | 8000 | 65.3% | 60.5% | 0.657 | 3,879 | 4.573 | 22.406 |
| adaptive | flat | 2000 | 72.7% | 73.7% | 0.739 | 1,949 | 6.022 | 9.940 |
| adaptive | book | 2000 | 72.7% | 73.7% | 0.739 | 1,949 | 5.771 | 9.904 |
| adaptive | flat | 8000 | 77.3% | 78.9% | 0.765 | 3,716 | 4.714 | 8.052 |
| adaptive | book | 8000 | 77.3% | 78.9% | 0.765 | 3,706 | 4.372 | 7.415 |

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
| session | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
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
| session | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
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
| turn | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
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
| turn | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
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
| adaptive | flat | 2000 | topic_change | 16 | 81.2% | 81.2% |
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
| adaptive | book | 2000 | topic_change | 16 | 81.2% | 81.2% |
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
| session | 112 | 10,470 | 536.07 | 208.93 | 14,998,512 |
| turn | 1408 | 831 | 712.77 | 157.13 | 16,873,504 |
| adaptive | 1912 | 612 | 1,008.47 | 111.06 | 19,579,576 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| session | flat | 2000 | 64.065 | 0.164 | 0.295 | 100.0% |
| session | book | 2000 | 50.079 | 0.179 | 0.379 | 100.0% |
| session | flat | 8000 | 54.974 | 0.232 | 0.466 | 100.0% |
| session | book | 8000 | 55.171 | 0.240 | 0.404 | 100.0% |
| turn | flat | 2000 | 15.911 | 0.137 | 0.359 | 100.0% |
| turn | book | 2000 | 15.760 | 0.144 | 0.235 | 100.0% |
| turn | flat | 8000 | 17.211 | 0.147 | 0.234 | 100.0% |
| turn | book | 8000 | 17.108 | 0.168 | 0.334 | 100.0% |
| adaptive | flat | 2000 | 10.745 | 0.144 | 0.262 | 100.0% |
| adaptive | book | 2000 | 9.244 | 0.147 | 0.274 | 100.0% |
| adaptive | flat | 8000 | 7.677 | 0.156 | 0.233 | 100.0% |
| adaptive | book | 8000 | 7.169 | 0.159 | 0.277 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Each retrieved unit contributes one query-centered excerpt. A separately optimized multi-window whole-session retriever is not tested.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](heldout-29-v2-900.json.gz) · [Compact machine-readable summary](heldout-29-v2-900.summary.json)
