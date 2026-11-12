# Local semantic retrieval: completed evidence comparison

Status: **complete-frozen-matrix**. Completed cohorts: 4/4.

The optional semantic route and lexical route use the **same measured runtime**, archive, 8000-character context cap, native token assembly and top-five page limit. The local model and rank-fusion policy were declared before scoring. Each configuration has three uncached repetitions; the mode order rotates by question and repetition.

These are **returned-source evidence scores**. They do not measure generated answers or a complete competitor memory workflow. Every loss remains in the raw reports.

## Complete evidence and evidence recall

Complete evidence is the share of answerable questions for which all required source annotations reached the budgeted context. Evidence recall uses the count of required annotations. Unsupported questions are excluded from both quality denominators and remain in latency/token statistics.

| Cohort | Token cap | Answerable | Lexical complete | Semantic complete | Change (pp) | Lexical recall | Semantic recall | Complete gains / losses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | 152 | 85.53% | 63.16% | -22.37 | 86.36% | 68.18% | 2 / 36 |
| development-synthetic61 | 1024 | 152 | 92.11% | 75.66% | -16.45 | 93.18% | 78.98% | 2 / 27 |
| development-synthetic61 | 2048 | 152 | 92.11% | 77.63% | -14.47 | 93.18% | 80.68% | 2 / 24 |
| regression-authored36 | 512 | 30 | 86.67% | 100.00% | +13.33 | 88.89% | 100.00% | 4 / 0 |
| regression-authored36 | 1024 | 30 | 86.67% | 100.00% | +13.33 | 88.89% | 100.00% | 4 / 0 |
| regression-authored36 | 2048 | 30 | 86.67% | 100.00% | +13.33 | 88.89% | 100.00% | 4 / 0 |
| regression-public1015 | 512 | 649 | 66.41% | 62.56% | -3.85 | 62.18% | 60.03% | 39 / 64 |
| regression-public1015 | 1024 | 649 | 72.88% | 71.49% | -1.39 | 69.54% | 68.78% | 37 / 46 |
| regression-public1015 | 2048 | 649 | 72.88% | 71.49% | -1.39 | 69.54% | 68.91% | 37 / 46 |
| external-hotpot128 | 512 | 128 | 35.16% | 33.59% | -1.56 | 66.99% | 63.07% | 7 / 9 |
| external-hotpot128 | 1024 | 128 | 48.44% | 50.00% | +1.56 | 74.51% | 73.20% | 13 / 11 |
| external-hotpot128 | 2048 | 128 | 48.44% | 50.00% | +1.56 | 74.51% | 73.20% | 13 / 11 |

## Declared low-overlap and cross-chapter diagnostics

Low overlap means at most 25% of the question's unique normalized lexical terms occur in the required evidence text. It is an evaluator-only grouping, not a learned semantic relevance label. Cross-chapter labels require evidence from at least two actual indexed chapter IDs; within-session `multi_section` cases are reported separately. Groups overlap and their rows must not be added together. The JSON/raw reports include every dataset category.

| Cohort | Group | Token cap | Answerable | Lexical complete | Semantic complete | Lexical recall | Semantic recall |
|---|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | low_lexical_overlap_le_0.25 | 512 | 32 | 75.00% | 68.75% | 80.00% | 75.00% |
| development-synthetic61 | cross_session | 512 | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | category:multi_section | 512 | 16 | 12.50% | 25.00% | 50.00% | 62.50% |
| development-synthetic61 | category:low_overlap_paraphrase | 512 | 8 | 0.00% | 0.00% | 0.00% | 0.00% |
| development-synthetic61 | low_lexical_overlap_le_0.25 | 1024 | 32 | 75.00% | 68.75% | 80.00% | 75.00% |
| development-synthetic61 | cross_session | 1024 | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | category:multi_section | 1024 | 16 | 75.00% | 87.50% | 87.50% | 93.75% |
| development-synthetic61 | category:low_overlap_paraphrase | 1024 | 8 | 0.00% | 0.00% | 0.00% | 0.00% |
| development-synthetic61 | low_lexical_overlap_le_0.25 | 2048 | 32 | 75.00% | 68.75% | 80.00% | 75.00% |
| development-synthetic61 | cross_session | 2048 | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | category:multi_section | 2048 | 16 | 75.00% | 87.50% | 87.50% | 93.75% |
| development-synthetic61 | category:low_overlap_paraphrase | 2048 | 8 | 0.00% | 0.00% | 0.00% | 0.00% |
| regression-authored36 | low_lexical_overlap_le_0.25 | 512 | 8 | 50.00% | 100.00% | 60.00% | 100.00% |
| regression-authored36 | cross_chapter | 512 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | cross_session | 512 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:multi_section | 512 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:low_overlap_paraphrase | 512 | 6 | 33.33% | 100.00% | 33.33% | 100.00% |
| regression-authored36 | low_lexical_overlap_le_0.25 | 1024 | 8 | 50.00% | 100.00% | 60.00% | 100.00% |
| regression-authored36 | cross_chapter | 1024 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | cross_session | 1024 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:multi_section | 1024 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:low_overlap_paraphrase | 1024 | 6 | 33.33% | 100.00% | 33.33% | 100.00% |
| regression-authored36 | low_lexical_overlap_le_0.25 | 2048 | 8 | 50.00% | 100.00% | 60.00% | 100.00% |
| regression-authored36 | cross_chapter | 2048 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | cross_session | 2048 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:multi_section | 2048 | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | category:low_overlap_paraphrase | 2048 | 6 | 33.33% | 100.00% | 33.33% | 100.00% |
| regression-public1015 | low_lexical_overlap_le_0.25 | 512 | 326 | 46.01% | 47.55% | 41.16% | 45.28% |
| regression-public1015 | cross_session | 512 | 76 | 10.53% | 15.79% | 26.74% | 31.02% |
| regression-public1015 | low_lexical_overlap_le_0.25 | 1024 | 326 | 54.91% | 57.06% | 51.33% | 54.24% |
| regression-public1015 | cross_session | 1024 | 76 | 18.42% | 19.74% | 36.90% | 37.97% |
| regression-public1015 | low_lexical_overlap_le_0.25 | 2048 | 326 | 54.91% | 57.06% | 51.33% | 54.48% |
| regression-public1015 | cross_session | 2048 | 76 | 18.42% | 19.74% | 36.90% | 38.50% |
| external-hotpot128 | low_lexical_overlap_le_0.25 | 512 | 3 | 0.00% | 33.33% | 50.00% | 66.67% |
| external-hotpot128 | cross_chapter | 512 | 128 | 35.16% | 33.59% | 66.99% | 63.07% |
| external-hotpot128 | cross_session | 512 | 128 | 35.16% | 33.59% | 66.99% | 63.07% |
| external-hotpot128 | low_lexical_overlap_le_0.25 | 1024 | 3 | 66.67% | 100.00% | 83.33% | 100.00% |
| external-hotpot128 | cross_chapter | 1024 | 128 | 48.44% | 50.00% | 74.51% | 73.20% |
| external-hotpot128 | cross_session | 1024 | 128 | 48.44% | 50.00% | 74.51% | 73.20% |
| external-hotpot128 | low_lexical_overlap_le_0.25 | 2048 | 3 | 66.67% | 100.00% | 83.33% | 100.00% |
| external-hotpot128 | cross_chapter | 2048 | 128 | 48.44% | 50.00% | 74.51% | 73.20% |
| external-hotpot128 | cross_session | 2048 | 128 | 48.44% | 50.00% | 74.51% | 73.20% |

## Query cost and context size

Times are milliseconds per uncached recall. They exclude model/index preparation, scoring and checkpoint writes. First-pass timings follow explicit model loading/indexing and are not OS/disk-cold measurements. The raw reports retain every query's repetition timings and any resume segments.

| Cohort | Token cap | Lexical mean tokens | Semantic mean tokens | Lexical p50 / p95 ms | Semantic p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | 476.8 | 490.1 | 8.033 / 17.511 | 18.894 / 30.055 |
| development-synthetic61 | 1024 | 905.5 | 936.6 | 6.360 / 17.633 | 16.006 / 29.169 |
| development-synthetic61 | 2048 | 1260.1 | 1381.6 | 5.813 / 15.048 | 15.815 / 27.725 |
| regression-authored36 | 512 | 188.5 | 454.2 | 1.539 / 2.526 | 9.478 / 14.894 |
| regression-authored36 | 1024 | 188.5 | 485.9 | 1.504 / 2.521 | 9.001 / 14.423 |
| regression-authored36 | 2048 | 188.5 | 485.9 | 1.511 / 2.517 | 8.998 / 14.446 |
| regression-public1015 | 512 | 491.9 | 492.4 | 8.078 / 10.184 | 18.074 / 22.691 |
| regression-public1015 | 1024 | 861.1 | 863.8 | 6.340 / 8.334 | 16.363 / 21.061 |
| regression-public1015 | 2048 | 867.1 | 871.9 | 6.254 / 8.127 | 15.943 / 20.353 |
| external-hotpot128 | 512 | 479.4 | 480.9 | 5.593 / 8.170 | 15.480 / 21.847 |
| external-hotpot128 | 1024 | 804.0 | 814.2 | 5.005 / 7.789 | 15.205 / 21.796 |
| external-hotpot128 | 2048 | 805.8 | 815.2 | 5.159 / 7.677 | 15.297 / 21.730 |

## One-time corpus preparation

The two modes share the canonical archive for the paired experiment. The semantic index is derived from original pages only. Model loading is separate from index construction. Vector bytes exclude SQLite overhead; database bytes are logical SQLite pages, not peak disk writes. The fixed model artifacts total 127,535,388 bytes, excluding optional Python dependencies.

| Cohort | Ingestion ms | Model load ms | Index build ms | Pages / windows | Vector bytes | Logical DB bytes |
|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 946.786 | 966.443 | 101579.978 | 1912 / 4093 | 6286848 | 28487680 |
| regression-authored36 | 32.759 | 1231.151 | 1142.000 | 42 / 42 | 64512 | 442368 |
| regression-public1015 | 1508.959 | 1270.810 | 116553.592 | 1339 / 2032 | 3121152 | 16830464 |
| external-hotpot128 | 3296.351 | 1055.701 | 106900.491 | 1915 / 2323 | 3568128 | 21504000 |

### Recovery costs

The table above shows the original successfully recorded preparation. A resumed process can load the model again; the following subtotal includes every recorded reload. Interrupted preparation or query attempts retain unknown costs. These subtotals exclude query time, scoring, checkpoint I/O, process startup and download time; they are not end-to-end wall time.

| Cohort | Process segments | Recorded reload ms | Known preparation ms | Unrecorded interrupted costs |
|---|---:|---:|---:|---|
| development-synthetic61 | 1 | 0.000 | 103493.208 | none recorded |
| regression-authored36 | 1 | 0.000 | 2405.910 | none recorded |
| regression-public1015 | 1 | 0.000 | 119333.360 | none recorded |
| external-hotpot128 | 1 | 0.000 | 111252.543 | none recorded |

## Interpretation and reproducibility

- Synthetic61 is development evidence with shared templates. The six-domain authored36 and LoCoMo1015 cohorts are known regression data.
- Hotpot128 was frozen separately before scoring. It is externally authored encyclopedia multi-hop QA in a scoped distractor setting; it is not full-Wikipedia retrieval or a representative conversation-memory population. Once scored, these IDs become regression data.
- The sentence model's pretraining overlap with the public datasets is unknown. These bounded cohorts do not establish universal semantic memory or cross-domain completion.
- Semantic ranking can displace useful lexical evidence and can return a nearest page for an unsupported question. It remains explicitly opt-in; all contexts retain original source coordinates.
- Measurement validation covers exact token/character caps, entire original-page slice projection, source references, project scope, model metadata, source stability and deterministic repeated contexts. It is not a minimum quality guarantee.
- Book's configured extractive summaries make zero model calls. Model inference for embedding has real CPU/index costs; no electricity, provider-bill or full-workflow cost advantage is inferred.

Measured runtime SHA-256: `63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625`.

The [frozen plan](semantic-final-plan.json), [original manifest](semantic-final-manifest.json), [fresh-workspace execution manifest](semantic-recovery-20261112-manifest.json), hosted execution checkpoints under reports/hosted-semantic-*-checkpoint.json, [machine-readable assessment](results/semantic-final-assessment.json) and raw reports preserve full identities and per-question gains/losses:

- development-synthetic61: [readable report](results/semantic-final-development-synthetic61.md), [summary](results/semantic-final-development-synthetic61.summary.json), [full metrics](results/semantic-final-development-synthetic61.json.gz).
- regression-authored36: [readable report](results/semantic-final-regression-authored36.md), [summary](results/semantic-final-regression-authored36.summary.json), [full metrics](results/semantic-final-regression-authored36.json.gz).
- regression-public1015: [readable report](results/semantic-final-regression-public1015.md), [summary](results/semantic-final-regression-public1015.summary.json), [full metrics](results/semantic-final-regression-public1015.json.gz).
- external-hotpot128: [readable report](results/semantic-final-external-hotpot128.md), [summary](results/semantic-final-external-hotpot128.summary.json), [full metrics](results/semantic-final-external-hotpot128.json.gz).

## Measurement hosts

The execution host can differ between cohorts. Runtime source, evaluator source, model, budgets and repeat counts must match across cohorts; both modes remain paired inside each cohort. There is no cross-host pooling or cross-cohort speed ratio. The complete recorded Python, SQLite, platform and package identities follow.

hosted-semantic-<cohort>-checkpoint.json records the individual Actions execution; original local checkpoints are retained separately.

```json
[
  {
    "cohort": "development-synthetic61",
    "python": "3.12.16",
    "sqlite": "3.45.1",
    "platform": "Linux-7.0.0-1017-azure-x86_64-with-glibc2.39",
    "packages": {
      "tiktoken": "0.12.0",
      "onnxruntime": "1.31.1",
      "tokenizers": "0.23.3",
      "numpy": "2.5.4"
    }
  },
  {
    "cohort": "regression-authored36",
    "python": "3.12.16",
    "sqlite": "3.45.1",
    "platform": "Linux-7.0.0-1017-azure-x86_64-with-glibc2.39",
    "packages": {
      "tiktoken": "0.12.0",
      "onnxruntime": "1.31.1",
      "tokenizers": "0.23.3",
      "numpy": "2.5.4"
    }
  },
  {
    "cohort": "regression-public1015",
    "python": "3.12.16",
    "sqlite": "3.45.1",
    "platform": "Linux-7.0.0-1017-azure-x86_64-with-glibc2.39",
    "packages": {
      "tiktoken": "0.12.0",
      "onnxruntime": "1.31.1",
      "tokenizers": "0.23.3",
      "numpy": "2.5.4"
    }
  },
  {
    "cohort": "external-hotpot128",
    "python": "3.12.16",
    "sqlite": "3.45.1",
    "platform": "Linux-7.0.0-1017-azure-x86_64-with-glibc2.39",
    "packages": {
      "tiktoken": "0.12.0",
      "onnxruntime": "1.31.1",
      "tokenizers": "0.23.3",
      "numpy": "2.5.4"
    }
  }
]
```


Rebuild the assessment without making model calls:

```bash
python scripts/summarize_semantic_completion.py
```
