# Real memory component replay

Status: `completed`. Protocol: `engineering-memory-systems-v1`.

Authored synthetic development cases, no coding LLM and no independent holdout. Only fully completed, integrity-valid backends appear in the quality table. Failures and partial rows remain in the JSON and logs.

All backends receive the same complete original pages and unchanged questions. The project filter and top-five candidate boundary precede the unchanged common whole-block packer. This is separate from native Book excerpt packing.

| Component | Chars | Evidence recall | Complete evidence | Fixed-policy pass | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|---:|
| book | 1200 | 95.00% | 94.44% | 91.67% | 4 | 1048.1 |
| book | 2400 | 100.00% | 100.00% | 100.00% | 0 | 1799.2 |

## Interpretation

Basic Memory executes explicit native text search rather than its default hybrid workflow. claude-mem receives raw original observations without its LLM observer; Mem0 uses infer=False and therefore does not run its default fact extraction. Chroma and LangGraph are retrieval/store infrastructure, not complete memory products.

Chroma, LangGraph and Mem0 share the actual official MiniLM embedding model. Identical or similar rankings are correlated evidence, not three independent model-quality confirmations. Native model truncation and native query thresholds remain in force. Neither generated nor mock embeddings are used.

Native timing includes real query embedding where that backend needs it. Model preparation, indexing and process startup are separate from search and common packing. Python IPC, Bun IPC and in-process Book timers have different boundaries. No complete-product speed ratio or developer-productivity claim follows.

All budgets, missing-evidence cases, stale-only failures, native outputs and source checks are retained. A zero match under a component's documented query semantics is not a general defeat of that complete product. See the fixed protocol and per-checkpoint actual configuration.

