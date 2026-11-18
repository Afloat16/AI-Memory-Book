# Additional actual search components

Status: `completed`. Protocol: `engineering-v012-search-components-v1`.

LanceDB native FTS and Whoosh BM25F with an explicitly declared OR parser. Authored development data; 80 original questions, six checkpoints and a fixed common whole-block packer. No generated answers, held-out generalization or full-product ranking.

| Actual component | Chars | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|---:|
| lancedb_fts | 1200 | 90.00% | 88.89% | 83.33% | 4 | 1035.8 |
| whoosh_bm25f_or | 1200 | 100.00% | 100.00% | 100.00% | 0 | 884.5 |
| lancedb_fts | 2400 | 90.00% | 88.89% | 83.33% | 4 | 1876.7 |
| whoosh_bm25f_or | 2400 | 100.00% | 100.00% | 100.00% | 0 | 1457.8 |

Each native query is sent unchanged, with exact project scope applied before the five-result limit. Complete original stored fields and native scores are preserved and verified before packing. Three repeats are stability observations, not new independent questions. Setup/search/transport timings are retained for diagnosis; no speed claim is registered.

Whoosh's OrGroup is an explicit configuration; its QueryParser default is AND. Neither component is a complete engineering-memory product. Empty original native results are preserved without rewritten replacement queries or adapter-level score thresholds.
