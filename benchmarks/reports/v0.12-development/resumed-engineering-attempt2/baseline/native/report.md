# Chronological engineering-memory development diagnostic

**Synthetic authored regression data. No language model, real user workflow, or external memory product was evaluated.**

The fixed consumer selects a configuration policy from returned source text and runs handwritten algorithm variants. Its pass rate is not generated-code accuracy.

Workload SHA-256: `87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3`. Imported runtime SHA-256: `00eaa1662f5c3a934ac2f339420a5a7098a5801052097bdbd08b9b82cf529992`.

All backends see the same chronological prefix and project scope. Character caps include citation text; they are not token caps. Result caching is disabled. Reported latency surrounds only local retrieval/context construction, excluding ingestion, scoring, executable checks and model generation. Repetitions are timing samples, not independent quality cases.

| Backend | Character cap | Evidence recall | Complete evidence | Fixed consumer passes | Stale-only | p50 / p95 ms | Mean chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| book | 1200 | 95.0% | 94.4% | 100.0% | 0 | 2.227 / 4.426 | 1195.9 |
| flat | 1200 | 70.0% | 66.7% | 58.3% | 14 | 0.735 / 1.207 | 1154.0 |
| no_memory | 1200 | 0.0% | 0.0% | 0.0% | 0 | 0.001 / 0.001 | 0.0 |
| recent_history | 1200 | 50.0% | 44.4% | 33.3% | 0 | 0.029 / 0.054 | 1184.0 |
| book | 2400 | 100.0% | 100.0% | 100.0% | 0 | 1.638 / 3.759 | 1799.2 |
| flat | 2400 | 75.0% | 72.2% | 58.3% | 14 | 0.614 / 1.065 | 1801.3 |
| no_memory | 2400 | 0.0% | 0.0% | 0.0% | 0 | 0.001 / 0.001 | 0.0 |
| recent_history | 2400 | 80.0% | 77.8% | 66.7% | 0 | 0.034 / 0.063 | 2260.9 |

## Interpretation limits

- These fixtures are development data from their first use. They do not establish generalization, significance, real coding productivity, hallucination rates or superiority over another open-source product.
- `flat` is this repository's scoped exact FTS route with the same source index and packer; it is not an implementation of another product. `recent_history` uses already resident transcript text and different storage work.
- A nonempty context for a missing-answer query is a retrieval diagnostic, not evidence of an incorrect generated answer. Stale and current evidence can coexist legitimately; stale-only and executable policy checks are reported separately.
- Gold quotes must survive into the returned context and the cited original source slice. Private history, credentials, model calls and network downloads are not required.
- The raw JSONL retains each case, context, source references, repeated latency samples and output digests. The dataset JSON retains chronology, labels and source replacements.
