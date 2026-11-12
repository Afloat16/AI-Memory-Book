# Actual capture, consolidation, retrieval and answer workflow

Status: **completed_with_failures**. The complete registered matrix contains **72 actual answer attempts**, using all 36 previously authored questions (30 answerable and 6 unsupported) across six fictional domains and 42 source sessions.

Book's default lexical path is compared with the official ai-memory **v3.4.5** binary, native hooks, explicitly enabled model consolidation, local embeddings, MCP queries and full reads. Both answer with the same pinned Qwen2.5-0.5B Q4_K_M model, a 512-token cl100k_base evidence cap, 8000-character cap and maximum 128 answer tokens. Native consolidation uses the separately preregistered 16,384-token model context. No synthetic replacement summaries are supplied.

Current ai-memory also supports a zero-LLM default path. This experiment measures the explicitly configured v3.4.5 generative workflow, not a required charge for all ai-memory deployments.

## Answer quality and failures

| Engine | EM | Lexical F1 | Exact abstention | Successful answers | Truncated answers |
|---|---:|---:|---:|---:|---:|
| book | 13.33% | 40.37% | 0.00% | 36 / 36 | 1 |
| ai-memory | 0.00% | 10.99% | 0.00% | 36 / 36 | 1 |

EM/F1 use all 30 answerable questions; exact abstention uses all 6 unsupported questions. Failures retain zero credit. These lexical metrics are not a human or model semantic judge.

## Phase costs

These are sequential phase observations with different native transport boundaries. Book uses its Python API; ai-memory uses authenticated HTTP/MCP and full reads. The table does not imply a same-boundary search-kernel speed ratio.

| Engine | Phase | Successful operations | Known phase ms | Complete total ms |
|---|---|---:|---:|---:|
| book | book-ingest | 42 / 42 | 46.24 | 46.24 |
| ai-memory | native-capture | 42 / 42 | 10,147.88 | 10,147.88 |
| ai-memory | native-consolidate | 7 / 42 | 1,981,084.49 | 1,981,084.49 |
| ai-memory | native-embed | 1 / 1 | 22.98 | 22.98 |

| Engine | Retrieval p50 / p95 / p99 ms | Answer p50 / p95 / p99 ms | Mean context tokens | Mean native returned tokens | Search / follow-up reads |
|---|---:|---:|---:|---:|---:|
| book | 2.27 / 15.05 / 23.54 | 3,713.90 / 5,365.71 / 5,928.41 | 269.11 | 1,392.53 | 36 / 0 |
| ai-memory | 147.12 / 158.91 / 160.87 | 4,975.25 / 5,514.40 / 6,904.43 | 498.08 | 5,116.67 | 36 / 180 |

## Actual model usage

Local server usage counts are not dollar charges or energy estimates. Unknown usage is preserved; a known subtotal must not be presented as a complete total.

| Engine | Phase | Model calls | Prompt tokens | Output tokens | Total tokens |
|---|---|---:|---:|---:|---:|
| book | consolidation | 0 | 0.00 | 0.00 | 0.00 |
| book | answers | 36 | 14,877.00 | 982.00 | 15,859.00 |
| ai-memory | consolidation | 42 | 103,797.00 | 36,706.00 | 140,503.00 |
| ai-memory | answers | 36 | 25,827.00 | 680.00 | 26,507.00 |

Native capture accepted **42 / 42** sessions. Native consolidation produced **7 / 42** validated pages. The native model proxy recorded **42** attempts and **42** completed HTTP responses.

## Storage and reproducibility

```json
{
  "book": {
    "boundary": "Stable filesystem sizes; no explicit WAL checkpoint; not peak disk usage or bytes written.",
    "files_bytes": {
      "database": 376832,
      "shm": 0,
      "wal": 0
    },
    "present": {
      "database": true,
      "shm": false,
      "wal": false
    },
    "total_bytes": 376832
  },
  "native_boundary": "Persistent native sandbox including logs, SQLite and wiki Git history; shared embedding model symlink excluded.",
  "native_directory_bytes": 2243214
}
```

The native directory includes its logs and wiki Git history; the shared embedding-model symlink is excluded. Book storage counts its closed SQLite files. These are declared storage boundaries, not interchangeable engine-only footprints.

The [raw public report](results/full-workflow-transfer36.json) retains actual fictional contexts, native summary outputs, capture acknowledgments, per-attempt answers and scores, phase status, model usage and process hashes. The [assessment](results/full-workflow-transfer36-assessment.json) is derived by `python scripts/summarize_workflow.py` without another model request. The [frozen plan](experiments/full-workflow-plan.json) defines the exact replay and read policy.

This is a previously observed six-domain diagnostic with one small quantized CPU model. Interactive host hooks, filesystem watcher overhead, adaptive agent reads, provider billing and electricity are unmeasured. claude-mem observer and billion-context compression workflows are outside this experiment. Larger-model answer quality, production concurrency and broad generalization remain unestablished.
