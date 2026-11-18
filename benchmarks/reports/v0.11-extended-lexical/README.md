# v0.11 additional upstream lexical components

This is a supplied-page retrieval-component experiment on the existing authored
engineering development fixture. The run contains 80 original questions, three
backends, three native repetitions and two context budgets. Its independent
offline audit verified 720 native calls and 480 packed responses. Repetitions
are stability observations, not additional questions. No generated answer or
whole-product quality is measured.

## Scope and results

The expanded project review covers **21 external project families**, including
**four retrieval/store libraries or frameworks**: Chroma, LangGraph, Haystack
and BM25S. This is a documentation-coverage count, not 21 memory products
executed end to end. LangMem remains grouped with LangGraph, and Haystack and
BM25S add two families to the previous 19. Memvid was already in that review.
The [comparison review](../../../docs/open-source-memory-comparison.md) and
[registered extension protocol](../../competitors/extended-lexical-plan.md)
describe the individual scopes and configurations.

| Executed component | Budget, characters | Required spans | Complete cases | Fixed-policy checks | Mean characters |
|---|---:|---:|---:|---:|---:|
| BM25S 0.3.16 | 1,200 | 80/80 | 72/72 | 48/48 | 1,045.25 |
| BM25S 0.3.16 | 2,400 | 80/80 | 72/72 | 48/48 | 1,846.65 |
| Haystack 3.5.0 BM25 | 1,200 | 74/80 | 66/72 | 42/48 | 969.8625 |
| Haystack 3.5.0 BM25 | 2,400 | 74/80 | 66/72 | 42/48 | 1,884.6625 |

Both components have zero stale-only cases and return nonempty context for all
eight missing-evidence questions. BM25S matches Book's shared whole-block
counts at 2,400 characters and exceeds its counts at 1,200. These measurements
do not support universal superiority for Book. All six visible source-page
bundles match the previous memory-systems experiment exactly, with 24, 56, 80,
104, 120 and 144 pages respectively. Timing was recorded in separate runs and
does not establish a unified speed ranking.

The unchanged natural-language queries produced empty native Tantivy results
in all 80 cases for **Memvid SDK 2.0.160 explicit lexical mode**. These real
outputs remain in the formal attempt; they are not used as a headline zero
score or a claim about Memvid's complete product. A separately labeled
[post-run diagnosis](memvid-query-diagnostic-1/report.json) retains 14 actual
calls: the original long query returns no hits with and without scope, while
`edge_policy`, `routing`, a quoted `edge_policy`, and
`edge_policy routing kernel` return verified hits. This narrows the problem to
the tested query/configuration behavior; it does not prove a particular parser
implementation or establish results after retuning. All complete body/frame
mappings for diagnostic positive controls passed.

Memvid's published wheel has one internal RECORD mismatch. The original
published artifact hash was independently checked against official PyPI, and
the installed native member matches that wheel byte for byte. The strictly
limited exception and the first failed check remain in
[preparation evidence](preparation/memvid-wheel-record-audit.json) and
[official artifact verification](preparation/memvid-pypi-artifact.json).
This is not a claim that every upstream RECORD entry passed unchanged.

## Lossless raw-record archive

Only the completed, audited attempt's three JSONL files exceeded 250,000 bytes
and were compressed. The report, original audit, source bundles, failure logs
and smaller diagnostic JSON remain unchanged. The `.mv2` file contains only
the supplied synthetic fixture used by the diagnostic probe.

- [Formal report](attempt1/report.json) and [original audit](attempt1/audit.json).
- [Exact integer metrics](verified-metrics.json).
- [Raw archive manifest](raw-manifest.json): original path, byte count and
  SHA-256, plus gzip path, byte count and SHA-256 for every archived file.
- [Attempts](archives/attempt1/attempts.jsonl.gz),
  [complete native results](archives/attempt1/native.jsonl.gz), and
  [packed responses and scores](archives/attempt1/raw.jsonl.gz).
- [Archive and restored-audit verification](archive-verification.json).

The original report and audit retain their original uncompressed hashes.
Archive storage does not change any query, native output, source identity,
metric, or frozen evaluator file. Gzip members use an empty filename and zero
mtime. SHA-256 checks prove consistency with this saved manifest; provenance
also depends on the repository commit preserving the manifest.

### Reproduce the independent audit

Run from the repository root with Python 3.12. Choose output/worktree paths that
do not already exist. The restore helper needs only the standard library. It
verifies all archived and preserved bytes before copying evidence to a new
directory, restores the exact original JSONL bytes, and refuses existing output
paths. It does not write to this evidence directory.

```bash
python benchmarks/experiments/restore_extended_raw.py \
  --manifest benchmarks/reports/v0.11-extended-lexical/raw-manifest.json \
  --verify-only
python benchmarks/experiments/restore_extended_raw.py \
  --manifest benchmarks/reports/v0.11-extended-lexical/raw-manifest.json \
  --output ../v011-extended-restored
git worktree add --detach ../v011-frozen-evaluator \
  db96c704a26be944399ec491630da73de8c5dd71
cd ../v011-frozen-evaluator
PYTHONPATH=src python -m benchmarks.extended_components --audit \
  --output ../v011-extended-restored/attempt1
```

The offline audit uses saved native outputs and requires no upstream backend
installation or new model/search calls. It writes only the restored copy's
`audit.json`; the committed original audit remains unchanged. Expected output
is `status: verified`, `packed_responses: 480`, `native_calls: 720`, with evaluator
closure `249556338fef641eb6221daf5796cba792dbe10047f795f7e323a2d6bcca933a`.
The earlier original-page materialization used the immutable v0.10 baseline;
it is not rerun by this offline audit.
