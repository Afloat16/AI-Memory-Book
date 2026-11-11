# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

**Release stage:** pre-release.

These two seeds ran sequentially in one Python process while release correctness fixes were made on disk. MemoryBook remained loaded from the first run. The recorded source hash is a workspace snapshot at each run start and may not describe every loaded module. Final release measurements rerun each seed in a fresh process with before/after source-hash checks.

## Dataset and runtime

- Dataset: version 2.0, `heldout`, seed `47`.
- Fingerprint: `a9d311f84a7f1c5f174ddddc91409b77c0bf08329f78eeb03a603acf57c50b7a`.
- Size: 8 projects, 112 sessions, 1408 user turns, 1,143,318 source characters, 168 queries (152 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Engine Python source fingerprint: `a9e6def2a3635b7e8dd2a6b8613f56dc6d1718b2653b3bff3b01d4f3f6f1fe49`.
- Run: 2026-11-11T08:45:22.698226+00:00 to 2026-11-11T08:49:06.507432+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=900, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

Both ranking strategies use the same metadata-aware FTS index. `book` adds soft directory-overlap reranking to `flat`; this experiment does not compare hierarchy against an index stripped of all directory metadata.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 68.8% | 73.0% | 0.671 | 1,904 | 52.282 | 108.634 |
| session | book | 2000 | 68.8% | 73.0% | 0.678 | 1,904 | 52.336 | 109.278 |
| session | flat | 8000 | 69.3% | 73.7% | 0.656 | 5,379 | 56.285 | 116.986 |
| session | book | 8000 | 69.3% | 73.7% | 0.667 | 5,411 | 56.191 | 108.478 |
| turn | flat | 2000 | 56.2% | 54.6% | 0.588 | 1,708 | 5.454 | 22.272 |
| turn | book | 2000 | 56.2% | 54.6% | 0.588 | 1,706 | 5.433 | 22.465 |
| turn | flat | 8000 | 64.8% | 59.9% | 0.650 | 3,891 | 4.887 | 22.893 |
| turn | book | 8000 | 64.8% | 59.9% | 0.650 | 3,881 | 4.260 | 22.246 |
| adaptive | flat | 2000 | 71.6% | 72.4% | 0.726 | 1,948 | 5.479 | 8.673 |
| adaptive | book | 2000 | 71.6% | 72.4% | 0.726 | 1,948 | 5.333 | 8.493 |
| adaptive | flat | 8000 | 77.3% | 78.9% | 0.765 | 3,711 | 4.488 | 7.157 |
| adaptive | book | 8000 | 77.3% | 78.9% | 0.765 | 3,701 | 4.243 | 6.992 |

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
| session | 112 | 10,470 | 478.31 | 234.16 | 14,994,440 |
| turn | 1408 | 831 | 687.65 | 162.87 | 16,712,848 |
| adaptive | 1912 | 612 | 873.22 | 128.26 | 19,567,216 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| session | flat | 2000 | 49.300 | 0.182 | 0.312 | 100.0% |
| session | book | 2000 | 54.202 | 0.180 | 0.248 | 100.0% |
| session | flat | 8000 | 60.645 | 0.249 | 0.384 | 100.0% |
| session | book | 8000 | 68.277 | 0.239 | 0.428 | 100.0% |
| turn | flat | 2000 | 7.369 | 0.128 | 0.184 | 100.0% |
| turn | book | 2000 | 6.950 | 0.142 | 0.223 | 100.0% |
| turn | flat | 8000 | 6.411 | 0.152 | 0.226 | 100.0% |
| turn | book | 8000 | 5.669 | 0.155 | 0.241 | 100.0% |
| adaptive | flat | 2000 | 8.962 | 0.144 | 0.239 | 100.0% |
| adaptive | book | 2000 | 7.499 | 0.142 | 0.182 | 100.0% |
| adaptive | flat | 8000 | 6.088 | 0.153 | 0.209 | 100.0% |
| adaptive | book | 8000 | 5.867 | 0.159 | 0.304 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](heldout-47-v2-900-pre-release.json.gz) · [Compact machine-readable summary](heldout-47-v2-900-pre-release.summary.json)
