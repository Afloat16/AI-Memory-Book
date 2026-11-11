# Score-aware fusion development selection

One fixed experiment was evaluated after the first frozen evaluation. It replaces
ordinal rank fusion with per-route max-normalized BM25 scores, using the same
2:1 exact/stem preference. The formula and three independent fixtures were fixed
before running either development comparison. No weight search followed.

For each candidate, let `E = max(0, -bm25_exact)` and
`S = max(0, -bm25_stem)`. When the ordered routes differ, relevance is
`2 * E / max(E) + S / max(S)`. An absent route contributes zero; an empty or
zero-score route uses denominator one. Identical-route behavior, scope filters,
candidate caps, directory weighting, novelty selection and excerpts stay unchanged.

| Development population | Character budget | Evidence recall, frozen → variant | Complete evidence, frozen → variant | Complete queries lost |
|---|---:|---:|---:|---:|
| Synthetic seed 61, 168 queries | 2,000 | 92.61% → 93.18% | 91.45% → 92.11% | 0 |
| Synthetic seed 61, 168 queries | 8,000 | 92.61% → 93.18% | 91.45% → 92.11% | 0 |
| LoCoMo development, 128 queries | 2,000 | 52.34% → 52.34% | 54.22% → 54.22% | 0 |
| LoCoMo development, 128 queries | 8,000 | 75.70% → 77.57% | 78.31% → 79.52% | 0 |

All three independent fixtures and the budget/source invariants passed. The
predeclared gate required no individual complete-query loss and no aggregate
evidence recall decrease at either character budget. These data passed that gate,
and adoption into the next candidate was subsequently authorized. Recall-cache
version 7 invalidates previous ranking results. This is a development selection;
it does not establish generalization, resolve the earlier synthetic regression,
or prove the user's overall latency/token/quality target.

Each experiment used one repetition while other report preparation continued.
Its timings are exploratory, not final performance evidence. The development
lookup category already passed 24/24 queries before this experiment.

The [selection record](score-aware-fusion-selection.json) retains the predeclared
gate, formula, source hashes and all gain/loss IDs. The
[patch](score-aware-fusion.patch) reproduces the isolated source variant and fixtures
on commit `6f5299004642618e606d001b4c574e1bae572a7e`.
The baseline archive's source hash matches that commit's frozen source bytes;
its ignored working path is why Git provenance records `source_dirty`.

Full development records:

- [Synthetic](../results/recall-score-fusion-synthetic-development.md)
- [Public](../results/recall-score-fusion-public-development.md)
