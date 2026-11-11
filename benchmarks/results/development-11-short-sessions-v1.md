# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

## Dataset and runtime

- Dataset: version 1.0, `development`, seed `11`.
- Fingerprint: `7c4bff5efb192ea2ac5a7e42603d6df1f7b0f97fbe8931cb025320fbaac8adeb`.
- Size: 8 projects, 96 sessions, 384 user turns, 74,502 source characters, 104 queries (88 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Run: 2026-11-11T08:25:49.292738+00:00 to 2026-11-11T08:25:59.253976+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=1800, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 91.7% | 90.9% | 0.833 | 1,713 | 1.490 | 5.076 |
| session | book | 2000 | 91.7% | 90.9% | 0.833 | 1,713 | 1.359 | 3.797 |
| session | flat | 8000 | 91.7% | 90.9% | 0.833 | 2,991 | 1.306 | 4.311 |
| session | book | 8000 | 91.7% | 90.9% | 0.833 | 2,991 | 1.287 | 3.913 |
| turn | flat | 2000 | 75.0% | 72.7% | 0.678 | 1,184 | 1.045 | 3.765 |
| turn | book | 2000 | 75.0% | 72.7% | 0.678 | 1,184 | 0.938 | 3.712 |
| turn | flat | 8000 | 75.0% | 72.7% | 0.678 | 2,071 | 0.940 | 3.596 |
| turn | book | 8000 | 75.0% | 72.7% | 0.678 | 2,071 | 0.966 | 3.762 |
| adaptive | flat | 2000 | 91.7% | 90.9% | 0.881 | 1,711 | 1.250 | 4.025 |
| adaptive | book | 2000 | 91.7% | 90.9% | 0.881 | 1,711 | 1.302 | 4.194 |
| adaptive | flat | 8000 | 91.7% | 90.9% | 0.881 | 2,595 | 1.218 | 3.926 |
| adaptive | book | 8000 | 91.7% | 90.9% | 0.881 | 2,595 | 1.261 | 4.237 |

## Failure diagnostics

A nonempty result for an unanswerable question is a retrieval diagnostic, not proof that a model would fabricate an answer. Stale-only means old evidence was returned without current evidence for a current-state query.

| Segmentation | Retrieval | Budget | Unanswerable nonempty | Latest stale-only | Old before current | Budget violations | Size mismatches |
|---|---|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | flat | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| turn | flat | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| turn | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| turn | flat | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| turn | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | flat | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | flat | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |

## Evidence recall by category

The same category is measured for all configurations; low lexical overlap and short follow-ups are retained even when they fail.

| Segmentation | Retrieval | Budget | Category | Queries | Evidence recall | Complete |
|---|---|---:|---|---:|---:|---:|
| session | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 2000 | cross_session | 8 | 100.0% | 100.0% |
| session | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| session | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 2000 | cross_session | 8 | 100.0% | 100.0% |
| session | book | 2000 | historical | 8 | 100.0% | 100.0% |
| session | book | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| session | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 8000 | cross_session | 8 | 100.0% | 100.0% |
| session | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| session | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 8000 | cross_session | 8 | 100.0% | 100.0% |
| session | book | 8000 | historical | 8 | 100.0% | 100.0% |
| session | book | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| session | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | cross_session | 8 | 50.0% | 0.0% |
| turn | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| turn | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | short_followup | 8 | 50.0% | 50.0% |
| turn | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | book | 2000 | cross_session | 8 | 50.0% | 0.0% |
| turn | book | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| turn | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 2000 | short_followup | 8 | 50.0% | 50.0% |
| turn | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | cross_session | 8 | 50.0% | 0.0% |
| turn | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| turn | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | short_followup | 8 | 50.0% | 50.0% |
| turn | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | book | 8000 | cross_session | 8 | 50.0% | 0.0% |
| turn | book | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| turn | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 8000 | short_followup | 8 | 50.0% | 50.0% |
| turn | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | similar_task | 8 | 100.0% | 100.0% |

## Ingestion and storage

Mean page characters uses the engine's stored page text, including speaker labels but excluding separately stored title metadata. File size includes SQLite WAL/SHM files present after ingestion.

| Segmentation | Pages | Mean page chars | Ingest ms | Sessions/sec | DB + WAL bytes |
|---|---:|---:|---:|---:|---:|
| session | 96 | 858 | 93.56 | 1,026.12 | 5,361,744 |
| turn | 384 | 213 | 92.68 | 1,035.87 | 5,427,424 |
| adaptive | 136 | 605 | 79.90 | 1,201.55 | 5,468,408 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| session | flat | 2000 | 4.400 | 0.121 | 0.155 | 100.0% |
| session | book | 2000 | 3.378 | 0.129 | 0.309 | 100.0% |
| session | flat | 8000 | 3.582 | 0.137 | 0.310 | 100.0% |
| session | book | 8000 | 3.448 | 0.132 | 0.217 | 100.0% |
| turn | flat | 2000 | 1.410 | 0.095 | 0.175 | 100.0% |
| turn | book | 2000 | 0.978 | 0.093 | 0.121 | 100.0% |
| turn | flat | 8000 | 0.787 | 0.114 | 0.266 | 100.0% |
| turn | book | 8000 | 0.956 | 0.100 | 0.170 | 100.0% |
| adaptive | flat | 2000 | 1.576 | 0.127 | 0.207 | 100.0% |
| adaptive | book | 2000 | 1.623 | 0.128 | 0.198 | 100.0% |
| adaptive | flat | 8000 | 1.445 | 0.132 | 0.212 | 100.0% |
| adaptive | book | 8000 | 1.589 | 0.134 | 0.207 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](development-11-short-sessions-v1.json.gz) · [Compact machine-readable summary](development-11-short-sessions-v1.summary.json)
