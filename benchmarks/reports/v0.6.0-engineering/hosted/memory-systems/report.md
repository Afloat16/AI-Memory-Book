# Real memory component replay

Status: `completed`. Protocol: `engineering-memory-systems-v1`.

Authored synthetic development cases, no coding LLM and no independent holdout. Only fully completed, integrity-valid backends appear in the quality table. Failures and partial rows remain in the JSON and logs.

All backends receive the same complete original pages and unchanged questions. The project filter and top-five candidate boundary precede the unchanged common whole-block packer. This is separate from native Book excerpt packing.

| Component | Chars | Evidence recall | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|---:|
| basic_memory | 1200 | 90.00% | 88.89% | 83.33% | 0 | 948.5 |
| billion | 1200 | 90.00% | 88.89% | 83.33% | 0 | 948.5 |
| book | 1200 | 95.00% | 94.44% | 91.67% | 4 | 1048.1 |
| chroma | 1200 | 68.75% | 65.28% | 52.08% | 4 | 1036.7 |
| claude_mem | 1200 | 90.00% | 88.89% | 83.33% | 0 | 848.0 |
| langgraph | 1200 | 68.75% | 65.28% | 52.08% | 4 | 1036.7 |
| mem0 | 1200 | 68.75% | 65.28% | 52.08% | 4 | 1036.7 |
| basic_memory | 2400 | 90.00% | 88.89% | 83.33% | 0 | 1333.1 |
| billion | 2400 | 90.00% | 88.89% | 83.33% | 0 | 1955.0 |
| book | 2400 | 100.00% | 100.00% | 100.00% | 0 | 1799.2 |
| chroma | 2400 | 68.75% | 65.28% | 52.08% | 4 | 1963.0 |
| claude_mem | 2400 | 90.00% | 88.89% | 83.33% | 0 | 1488.5 |
| langgraph | 2400 | 68.75% | 65.28% | 52.08% | 4 | 1963.0 |
| mem0 | 2400 | 68.75% | 65.28% | 52.08% | 4 | 1963.0 |

## Interpretation

Basic Memory executes explicit native text search rather than its default hybrid workflow. claude-mem receives raw original observations without its LLM observer; Mem0 uses infer=False and therefore does not run its default fact extraction. Chroma and LangGraph are retrieval/store infrastructure, not complete memory products.

Chroma, LangGraph and Mem0 share the actual official MiniLM embedding model. Identical or similar rankings are correlated evidence, not three independent model-quality confirmations. Native model truncation and native query thresholds remain in force. Neither generated nor mock embeddings are used.

Native timing includes real query embedding where that backend needs it. Model preparation, indexing and process startup are separate from search and common packing. Python IPC, Bun IPC and in-process Book timers have different boundaries. No complete-product speed ratio or developer-productivity claim follows.

All budgets, missing-evidence cases, stale-only failures, native outputs and source checks are retained. A zero match under a component's documented query semantics is not a general defeat of that complete product. See the fixed protocol and per-checkpoint actual configuration.

