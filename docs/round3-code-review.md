# Round-three product review

Reviewed on 2026-11-13 (Asia/Shanghai). Candidate integration:
`93cea9544d024708d8fa9a423914bb255b9476d1`; baseline:
`dd2f88be742ed330269e7dd5915b6f75089d7fef` (v0.3.0).
The review compared `src/memory_book/store.py` and `semantic.py` and read the
registered round-three plan, performance binding, and relevant tests.

**No blocking correctness defect was found in these product changes.** This is
a scoped code review, not acceptance of the performance or comparison gates.

## Reviewed invariants

- Project rowid bounds are read inside recall's transaction after its revision
  read. The exact project/chapter predicates remain before the candidate limit;
  session-scoped queries retain the original plan. Missing projects yield an
  empty range. The structural guard preserves the original plan for wide spans.
- The optimization retains the global FTS indexes, BM25 weights, deterministic
  ties, ranking, cache identity and complete returned payload. It introduces no
  persistent state or schema. The guard measures span, not page density, so
  measured speedups must remain workload-specific.
- Semantic initialization sets `ORT_DISABLE_TELEMETRY=1` before importing ONNX
  Runtime and disables API-controlled events before constructing the session.
  It preserves model/vector identities and inference/fusion settings. The
  [official privacy guidance](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md)
  supports this sequence. Applications that imported ORT earlier still need
  the environment setting before process startup, as the product docs explain.

## Executed checks

From the candidate checkout:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_project_rowid_bounds.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_semantic_privacy.py' -v
```

All four rowid tests and both privacy tests passed. Two additional temporary
Python checks also passed; they did not modify tracked files:

- 378 deterministic comparisons of complete payloads excluding only
  `latency_ms`, with the optimized query versus `_project_rowid_bounds` patched
  to return `None`. Fixtures used seed 31061, three projects with 28 sessions
  each and deletions in the target project. Queries covered English, stems,
  CJK, missing matches and temporal/conjunctive wording; scopes covered project,
  chapter, session, missing project and unscoped calls. Configurations included
  book, book with coverage, flat, three-result limits and 0/80/500-character
  budgets. Every pair matched.
- A WAL-backed two-connection fixture inserted new target evidence immediately
  after the reader obtained bounds. The in-flight recall exactly matched its
  pre-write payload; the next call observed a higher revision. Deleting the
  project then produced empty results.

These are correctness checks, not timing or quality measurements. Privacy
tests use fixture dependencies; actual-model compatibility belongs to the
separate saved Q2 sentinel. This review did not change frozen sources,
evaluators, bindings or results, and does not establish universal speedups or
whole-product superiority.
