# Engineering supplied-page component comparison

**Authored synthetic development data; fixed consumer; no LLM or full memory product evaluation.**

Status: `completed`. Runtime: `4f84e9f8e7fa0ee7c9abe1910f2df5622d0414fb5f3b6e218544161f8a25dd81`. Evaluator closure: `52c12368a87881bbc4403d67ed273fffc82d6b64b135888c99801968eddbc318`.

Both rankers see the same complete source-page bodies, project filter and top-five limit. A common packer ignores native excerpts, retains native ordering, and skips whole blocks that exceed the character cap. Characters are not exact model tokens.

Book retains native hierarchy/FTS metadata; Billion receives uniform assistant-role messages with supplied title/body/project. Common representation does not mean identical indexed features.

| Component | Chars | Evidence recall | Complete evidence | Fixed-consumer pass | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|---:|
| billion | 1200 | 90.0% | 88.9% | 83.3% | 0 | 948.5 |
| book | 1200 | 65.0% | 61.1% | 41.7% | 0 | 1028.2 |
| billion | 2400 | 90.0% | 88.9% | 83.3% | 0 | 1955.0 |
| book | 2400 | 65.0% | 61.1% | 41.7% | 0 | 1954.6 |

## Timing boundaries

Book timing is in-process Python recall including its native context assembly. Billion separately reports searchBlocks kernel time and persistent JSON process roundtrip. The common pack timer is an in-memory supplied-fixture lookup and assembly; it does not measure Billion's host decompression or native follow-up reads. These boundaries cannot establish a whole-product speed ratio, end-to-end model latency, or time to a correct patch.

Native searches are reused across both character caps; repetitions measure timing, not independent quality cases. The process is restarted for each chronological checkpoint; native document-feature caches evolve normally within that checkpoint. Book result caching is disabled. First searches and later repetitions are retained separately in report.json.

The benchmark preserves complete native responses for every repetition in native.jsonl; raw.jsonl records every common-budget context and evidence/consumer score. Checkpoint page bundles and dataset.json permit provenance validation. Setup and source ingestion costs are recorded separately and use different backend operations, not a product-lifecycle comparison.

## Upstream attribution

This benchmark executes [billion-context](https://github.com/ranxianglei/billion-context) and its [acp-kernel](https://github.com/ranxianglei/acp-kernel) search implementation at `9674cfafbc78c50245ae0d887483d3d6ce880c15`. Its license is MIT text plus an additional product-surface attribution condition. Original files are digest-verified before Node's syntax-only TypeScript erasure; no ranking implementation is rewritten here.
