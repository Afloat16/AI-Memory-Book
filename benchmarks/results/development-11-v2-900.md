# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

## Dataset and runtime

- Dataset: version 2.0, `development`, seed `11`.
- Fingerprint: `4fa1e2556205411227f0216e20a6187ec2289c55c0c95c216236806f4b65c67f`.
- Size: 8 projects, 112 sessions, 1408 user turns, 1,143,305 source characters, 168 queries (152 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Run: 2026-11-11T08:37:34.036216+00:00 to 2026-11-11T08:41:00.241731+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=900, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

Both ranking strategies use the same metadata-aware FTS index. `book` adds soft directory-overlap reranking to `flat`; this experiment does not compare hierarchy against an index stripped of all directory metadata.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 70.5% | 76.3% | 0.721 | 1,857 | 48.345 | 103.464 |
| session | book | 2000 | 70.5% | 76.3% | 0.722 | 1,857 | 49.427 | 109.430 |
| session | flat | 8000 | 75.0% | 77.0% | 0.774 | 5,328 | 52.531 | 108.819 |
| session | book | 8000 | 75.0% | 77.0% | 0.775 | 5,297 | 52.558 | 110.023 |
| turn | flat | 2000 | 75.0% | 76.3% | 0.737 | 1,649 | 5.126 | 21.988 |
| turn | book | 2000 | 75.0% | 76.3% | 0.737 | 1,648 | 5.028 | 22.038 |
| turn | flat | 8000 | 86.4% | 84.2% | 0.833 | 3,553 | 3.953 | 21.108 |
| turn | book | 8000 | 86.4% | 84.2% | 0.833 | 3,600 | 4.916 | 23.770 |
| adaptive | flat | 2000 | 81.8% | 84.2% | 0.816 | 1,911 | 5.509 | 8.197 |
| adaptive | book | 2000 | 81.8% | 84.2% | 0.816 | 1,911 | 5.383 | 8.081 |
| adaptive | flat | 8000 | 92.6% | 91.4% | 0.902 | 3,648 | 4.413 | 6.580 |
| adaptive | book | 8000 | 92.6% | 91.4% | 0.902 | 3,648 | 4.638 | 6.821 |

## Failure diagnostics

A nonempty result for an unanswerable question is a retrieval diagnostic, not proof that a model would fabricate an answer. Stale-only means old evidence was returned without current evidence for a current-state query.

| Segmentation | Retrieval | Budget | Unanswerable nonempty | Latest stale-only | Old before current | Budget violations | Size mismatches |
|---|---|---:|---:|---:|---:|---:|---:|
| session | flat | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | flat | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| session | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| turn | flat | 2000 | 75.0% | 0.0% | 50.0% | 0 | 0 |
| turn | book | 2000 | 75.0% | 50.0% | 50.0% | 0 | 0 |
| turn | flat | 8000 | 75.0% | 0.0% | 50.0% | 0 | 0 |
| turn | book | 8000 | 75.0% | 50.0% | 50.0% | 0 | 0 |
| adaptive | flat | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | flat | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |

## Evidence recall by category

The same category is measured for all configurations; low lexical overlap and short follow-ups are retained even when they fail.

| Segmentation | Retrieval | Budget | Category | Queries | Evidence recall | Complete |
|---|---|---:|---|---:|---:|---:|
| session | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 2000 | cross_session | 8 | 75.0% | 50.0% |
| session | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| session | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | flat | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 2000 | multi_section | 16 | 0.0% | 0.0% |
| session | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | flat | 2000 | topic_change | 16 | 50.0% | 50.0% |
| session | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 2000 | cross_session | 8 | 75.0% | 50.0% |
| session | book | 2000 | historical | 8 | 100.0% | 100.0% |
| session | book | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| session | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | book | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 2000 | multi_section | 16 | 0.0% | 0.0% |
| session | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 2000 | topic_change | 16 | 50.0% | 50.0% |
| session | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | flat | 8000 | cross_session | 8 | 75.0% | 50.0% |
| session | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| session | flat | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| session | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | flat | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | flat | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | flat | 8000 | multi_section | 16 | 21.9% | 0.0% |
| session | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| session | flat | 8000 | topic_change | 16 | 56.2% | 56.2% |
| session | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| session | book | 8000 | cross_session | 8 | 75.0% | 50.0% |
| session | book | 8000 | historical | 8 | 100.0% | 100.0% |
| session | book | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| session | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| session | book | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| session | book | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| session | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| session | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| session | book | 8000 | multi_section | 16 | 21.9% | 0.0% |
| session | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| session | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| session | book | 8000 | topic_change | 16 | 56.2% | 56.2% |
| turn | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | cross_session | 8 | 75.0% | 50.0% |
| turn | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | flat | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| turn | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| turn | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 2000 | multi_section | 16 | 50.0% | 50.0% |
| turn | flat | 2000 | short_followup | 8 | 50.0% | 50.0% |
| turn | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 2000 | topic_change | 16 | 50.0% | 50.0% |
| turn | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | book | 2000 | cross_session | 8 | 75.0% | 50.0% |
| turn | book | 2000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 2000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | book | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| turn | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| turn | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 2000 | multi_section | 16 | 50.0% | 50.0% |
| turn | book | 2000 | short_followup | 8 | 50.0% | 50.0% |
| turn | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 2000 | topic_change | 16 | 50.0% | 50.0% |
| turn | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | cross_session | 8 | 75.0% | 50.0% |
| turn | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | flat | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| turn | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| turn | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | flat | 8000 | multi_section | 16 | 87.5% | 75.0% |
| turn | flat | 8000 | short_followup | 8 | 50.0% | 50.0% |
| turn | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | flat | 8000 | topic_change | 16 | 100.0% | 100.0% |
| turn | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| turn | book | 8000 | cross_session | 8 | 75.0% | 50.0% |
| turn | book | 8000 | historical | 8 | 100.0% | 100.0% |
| turn | book | 8000 | latest_decision | 8 | 50.0% | 50.0% |
| turn | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| turn | book | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| turn | book | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| turn | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| turn | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| turn | book | 8000 | multi_section | 16 | 87.5% | 75.0% |
| turn | book | 8000 | short_followup | 8 | 50.0% | 50.0% |
| turn | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| turn | book | 8000 | topic_change | 16 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | flat | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| adaptive | flat | 2000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | flat | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 2000 | multi_section | 16 | 50.0% | 50.0% |
| adaptive | flat | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 2000 | topic_change | 16 | 50.0% | 50.0% |
| adaptive | book | 2000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | book | 2000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| adaptive | book | 2000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | book | 2000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 2000 | multi_section | 16 | 50.0% | 50.0% |
| adaptive | book | 2000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 2000 | topic_change | 16 | 50.0% | 50.0% |
| adaptive | flat | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | flat | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| adaptive | flat | 8000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | flat | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | flat | 8000 | multi_section | 16 | 84.4% | 68.8% |
| adaptive | flat | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | flat | 8000 | topic_change | 16 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_project_name | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | cross_session | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | historical | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | latest_decision | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_middle | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_natural_late | 16 | 100.0% | 100.0% |
| adaptive | book | 8000 | long_answer_natural_middle | 16 | 100.0% | 100.0% |
| adaptive | book | 8000 | lookup | 24 | 100.0% | 100.0% |
| adaptive | book | 8000 | low_overlap_paraphrase | 8 | 0.0% | 0.0% |
| adaptive | book | 8000 | multi_section | 16 | 84.4% | 68.8% |
| adaptive | book | 8000 | short_followup | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | similar_task | 8 | 100.0% | 100.0% |
| adaptive | book | 8000 | topic_change | 16 | 100.0% | 100.0% |

## Ingestion and storage

Mean page characters uses the engine's stored page text, including speaker labels but excluding separately stored title metadata. File size includes SQLite WAL/SHM files present after ingestion.

| Segmentation | Pages | Mean page chars | Ingest ms | Sessions/sec | DB + WAL bytes |
|---|---:|---:|---:|---:|---:|
| session | 112 | 10,470 | 536.64 | 208.71 | 14,994,416 |
| turn | 1408 | 831 | 678.68 | 165.03 | 16,791,128 |
| adaptive | 1912 | 612 | 904.22 | 123.86 | 19,575,408 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| session | flat | 2000 | 108.326 | 0.174 | 0.278 | 100.0% |
| session | book | 2000 | 100.122 | 0.177 | 0.254 | 100.0% |
| session | flat | 8000 | 101.964 | 0.235 | 0.863 | 100.0% |
| session | book | 8000 | 103.729 | 0.248 | 0.356 | 100.0% |
| turn | flat | 2000 | 22.718 | 0.130 | 0.241 | 100.0% |
| turn | book | 2000 | 23.096 | 0.132 | 0.180 | 100.0% |
| turn | flat | 8000 | 22.058 | 0.160 | 0.305 | 100.0% |
| turn | book | 8000 | 24.541 | 0.152 | 0.245 | 100.0% |
| adaptive | flat | 2000 | 8.864 | 0.141 | 0.177 | 100.0% |
| adaptive | book | 2000 | 7.321 | 0.146 | 0.191 | 100.0% |
| adaptive | flat | 8000 | 6.394 | 0.157 | 0.219 | 100.0% |
| adaptive | book | 8000 | 6.437 | 0.160 | 0.226 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](development-11-v2-900.json.gz) · [Compact machine-readable summary](development-11-v2-900.summary.json)
