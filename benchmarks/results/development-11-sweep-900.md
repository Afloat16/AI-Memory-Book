# AI-Memory-Book synthetic retrieval benchmark

This is a reproducible local microbenchmark on generated conversations. It is **not** a benchmark of claude-mem, billion-context, ai-memory, or real user workloads, and it does not measure LLM answer quality.

## Dataset and runtime

- Dataset: version 2.0, `development`, seed `11`.
- Fingerprint: `4fa1e2556205411227f0216e20a6187ec2289c55c0c95c216236806f4b65c67f`.
- Size: 8 projects, 112 sessions, 1408 user turns, 1,143,305 source characters, 168 queries (152 answerable).
- Python 3.12.14; SQLite 3.53.1; Linux-6.18.57-x86_64-with-glibc2.41.
- Engine Python source fingerprint: `c36022d40452c009b559bfa3c2a6524494d89297e6539ec74679c15f4c7d286a`.
- Run: 2026-11-11T08:36:18.232323+00:00 to 2026-11-11T08:36:26.529770+00:00.
- Result limit: 5; uncached repeats: 3; page settings: max=900, min=400, similarity=0.12.

Task identifiers are supplied input metadata. Every configuration uses the same source records, tokenizer/search implementation, project scope and context budget. Source evidence, rather than generated page IDs, determines correctness.

Both ranking strategies use the same metadata-aware FTS index. `book` adds soft directory-overlap reranking to `flat`; this experiment does not compare hierarchy against an index stripped of all directory metadata.

## Main results

Recall counts required facts that are present in the actual returned context **and** traceable to the expected original session and turn. Complete means all required facts for an answerable query were returned. Mean characters includes unanswerable queries and citation metadata.

| Segmentation | Retrieval | Budget (chars) | Evidence recall | Complete | MRR | Mean chars | Uncached p50 ms | Uncached p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| adaptive | book | 2000 | 81.8% | 84.2% | 0.816 | 1,911 | 5.396 | 8.601 |
| adaptive | book | 8000 | 92.6% | 91.4% | 0.902 | 3,648 | 4.700 | 7.100 |

## Failure diagnostics

A nonempty result for an unanswerable question is a retrieval diagnostic, not proof that a model would fabricate an answer. Stale-only means old evidence was returned without current evidence for a current-state query.

| Segmentation | Retrieval | Budget | Unanswerable nonempty | Latest stale-only | Old before current | Budget violations | Size mismatches |
|---|---|---:|---:|---:|---:|---:|---:|
| adaptive | book | 2000 | 75.0% | 0.0% | 0.0% | 0 | 0 |
| adaptive | book | 8000 | 75.0% | 0.0% | 0.0% | 0 | 0 |

## Evidence recall by category

The same category is measured for all configurations; low lexical overlap and short follow-ups are retained even when they fail.

| Segmentation | Retrieval | Budget | Category | Queries | Evidence recall | Complete |
|---|---|---:|---|---:|---:|---:|
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
| adaptive | 1912 | 612 | 825.53 | 135.67 | 19,575,408 |

## Cache and measurement boundaries

Main latency measurements disable the result cache. They run in one Python process; SQLite and OS page caches are not flushed. The first-query column is therefore **not a cold-process or cold-OS-cache benchmark**. The hot-cache test immediately repeats each query and represents a best-case cache hit, not typical traffic.

| Segmentation | Retrieval | Budget | First query ms | Immediate-repeat p50 ms | Immediate-repeat p95 ms | Cache hit rate |
|---|---|---:|---:|---:|---:|---:|
| adaptive | book | 2000 | 8.395 | 0.147 | 0.245 | 100.0% |
| adaptive | book | 8000 | 6.754 | 0.164 | 0.280 | 100.0% |

## Interpretation limits

- Synthetic source and question templates; no real user conversations or external project engines are benchmarked.
- Task identifiers are supplied metadata, not inferred clustering accuracy.
- Directory strategy and page segmentation are separate factors; superiority is not assumed.
- Split labels are caller-selected. Any split used to tune parameters must be treated as development evidence.
- No LLM, network, embedding, agent orchestration, cold-process startup, or end-to-end answer latency is measured.
- Source interval overlap is not semantic redundancy; paraphrase evaluation is limited to the included templates.

All timing values above are measured, not projected. The JSON companion includes per-query evidence ranks, references, categories, and measured latency distributions for inspection.

[Complete raw results (gzip)](development-11-sweep-900.json.gz) · [Compact machine-readable summary](development-11-sweep-900.summary.json)
