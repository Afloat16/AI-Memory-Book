# Round three: fresh Hotpot256 native and component comparison

Run [43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247) completed successfully with **10/10 registered stages**, **4,608 native recall calls**, **4,608 component searches** and **1,280 additional native ai-memory page reads**. The [assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json) is `complete-verified`; all strict source, scope and budget checks passed.

The v0.3.1 runtime candidate preserves the baseline's complete lexical payload in **1,536 native pairs and 768 component pairs**. Its default optimization improves execution rather than changing retrieval quality. The separate [47,320-call performance experiment and startup review](optimization-round3.md) remain the basis for the formal speed claim.

On this fresh cohort, Book has a clear measured quality advantage over the tested claude-mem supplied-source FTS component in every budget/tokenizer cell. It does **not** lead every compared component: ai-memory and billion-context retrieve more complete evidence at 1,024/2,048 tokens, while billion-context also has lower measured search-kernel latency. Existing optional Q2 improves Book's complete-evidence rate at the larger budgets but loses at 512 tokens and adds model/index/query costs.

## Reference view and supported claims

The following 1,024-token view is a compact presentation of one of the six registered cells, not a newly selected acceptance criterion. Both tokenizers have the same quality at 1,024 and 2,048 in this run; their token counts differ. All six cells follow below.

| Component, common cl100k 1024 | Evidence recall | Complete evidence | Packed MRR | Adapter p95 ms |
|---|---|---|---|---|
| v0.3.0 lexical | 76.28% | 52.34% | 0.8132 | 5.828 |
| v0.3.1 lexical | 76.28% | 52.34% | 0.8132 | 2.784 |
| v0.3.1 Q2 | 76.77% | 54.69% | 0.8239 | 11.226 |
| claude-mem FTS | 70.68% | 45.31% | 0.7674 | 22.826 |
| ai-memory local hybrid | 77.27% | 55.86% | 0.8182 | 27.545 |
| billion-context kernel | 78.91% | 58.20% | 0.8277 | 1.010 |

Positive differences below favor Book; all values are **percentage points**, calculated from exact unrounded counts at the common 1,024/2,048-token cells.

| Comparator | Lexical recall difference | Lexical complete difference | Q2 recall difference | Q2 complete difference |
|---|---|---|---|---|
| claude-mem FTS | +5.60 | +7.03 | +6.10 | +9.38 |
| ai-memory local hybrid | -0.99 | -3.52 | -0.49 | -1.17 |
| billion-context kernel | -2.64 | -5.86 | -2.14 | -3.52 |

Book lexical exceeds claude-mem here by **5.60 points of evidence recall and 7.03 points of complete evidence**, with a measured adapter p95 of 2.784 versus 22.826 ms. Against ai-memory, lexical has lower measured latency but loses **0.99 recall points and 3.52 complete-evidence points**; Q2 still falls short of ai-memory by 0.49 and 1.17 points. Against billion-context, lexical loses **2.64 recall points and 5.86 complete-evidence points** at these budgets, and the kernel's adapter p95 is lower.

At 512 tokens, lexical Book's complete evidence is 98 versus 96 questions for billion-context with cl100k, and 100 versus 97 with o200k; annotation recall is also higher. Against ai-memory at 512, Book matches one additional annotation in each tokenizer but completes fewer questions (98 versus 102 and 100 versus 105). These are budget-specific tradeoffs, not an overall product ranking.

Cross-component timing has different execution boundaries. No whole-product speed multiplier follows from the table. The measurements exclude observer/generation workflows and do not score generated answers.

## Frozen selection and implementation identities

The [registered plan](../benchmarks/experiments/round3-plan.json), [runtime/evaluator binding](../benchmarks/experiments/round3-validation-binding.json) and [freeze asset verification](../benchmarks/reports/round3-freeze-43267320737-1/asset-verification.json) were committed before selecting this cohort. The resulting [selection manifest](../benchmarks/experiments/round3-hotpot256-manifest.json) was then committed before any scoring. The freeze run was [43267320737](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267320737).

| Item | Identity |
|---|---|
| Baseline | Published v0.3.0, `dd2f88be742ed330269e7dd5915b6f75089d7fef` |
| Candidate runtime source | `2d199b93f650eccd3dd239178822b31001b880e3` |
| Baseline runtime SHA-256 | `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57` |
| Candidate runtime SHA-256 | `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46` |
| Evaluator freeze commit | `3d8583b22ae73ec69b368d03ce735657f92f1edb` |
| Execution trigger commit | `a0d67b35d074077f43b5cea77954921802d51f44` |
| Binding SHA-256 | `740361f1767a942887bdb7639b1be0223ae1c6dc2fc3b941f845d038884f842f` |
| Cohort manifest SHA-256 | `b29545eb90f89744d86e3f8822b838c44a1846be057161b1905f6c977b7b1ae5` |
| Converted dataset SHA-256 | `8470e4913f858788809b421acbc6a07bb0701daadc11062909b45d102dd9f79a` |
| Canonical supplied-pages SHA-256 | `8d15147b897b27accb572e8b8d0de096aff11aa9f109012f255f482ba85ea178` |

The input is HotpotQA dev distractor, pinned to [source revision 1908d6a](https://huggingface.co/datasets/hotpotqa/hotpot_qa/tree/1908d6afbbead072334abe2965f91bd2709910ab), licensed CC BY-SA 4.0. Selection reads IDs first, excludes the union of the prior Hotpot128 and round-two Hotpot256 selections, then orders eligible IDs by the fixed salted SHA-256 rule. The new **256 IDs have zero overlap with the 384 prior IDs**. There was no question, answer, difficulty or score-based selection.

This is a new selection from the **same source**, not an unseen domain. These IDs became regression data after this first score. The code, models and ranking parameters were not retuned on their results.

| Cohort property | Count |
|---|---:|
| Questions / answerable questions | 256 / 256 |
| Supporting-evidence annotations | 607 |
| Bridge / comparison questions | 199 / 57 |
| Supplied context paragraphs | 2,559 |
| Original sentence turns | 10,625 |
| Projects / chapters / sessions | 256 / 2,559 / 2,559 |
| Canonical sections / pages | 3,893 / 3,896 |
| Original source characters / UTF-8 bytes | 1,417,142 / 1,421,846 |
| Complete annotations attainable within one source page | 607 / 607 |
| Low lexical-overlap diagnostic questions | 6 |

Every supplied paragraph is its own chapter/session; every original sentence is a canonical user turn; one problem is one project. No question or QA labels are indexed. Dates are fixed synthetic values for neutral ordering, not article publication dates. All supplied distractor contexts are indexed, rather than searching all of Wikipedia. All engines receive the same canonical pages and project scope.

The [export summary](../benchmarks/results/round3-comparison-43267797247-1/export.summary.json) verifies that all 607 complete annotations fit a source-page span; the largest annotation has 762 characters. No unattainable annotation was dropped. A match requires the complete annotation and its valid original source span; assembling a sentence from fragments across pages earns no complete-annotation credit.

### Compared upstream components

| Component | Frozen version | Executed boundary |
|---|---|---|
| AI-Memory-Book baseline/candidate lexical | Exact commits above | Native Python recall, including hierarchy/context assembly; no model |
| AI-Memory-Book candidate Q2 | Same candidate plus frozen existing model/fusion | Native Python recall with local dense embeddings |
| [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 15.18.1, `c4a9f5725f420bf9c6e866cdd3b94bd36498af09` | Unchanged SessionStore schema and SessionSearch.searchObservations through SQLite/Bun, supplied-source FTS |
| [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) | Released v3.4.5 binary, `ee73c04c542fa41ca629b046deb4ac108518f407` | Local hybrid search through actual HTTP/MCP plus full reads of mapped top-five pages |
| [ranxianglei/billion-context](https://github.com/ranxianglei/billion-context) | Search kernel at `9674cfafbc78c50245ae0d887483d3d6ce880c15` | Locked native search source through Node; supplied pages, not the full product |

The billion-context adapter uses the kernel's default hybrid algorithm with substring, BM25 and fuzzy routes; this run does not add a dense semantic model. Its supplied documents all use the same message kind and assistant role, not QA-derived labels.

The immutable [claude-mem](../benchmarks/competitors/claude-mem-round2-lock.json), [ai-memory](../benchmarks/competitors/ai-memory-lock.json) and [billion-context](../benchmarks/competitors/billion-round2-lock.json) locks contain file/archive hashes and attribution. The billion-context license includes an additional product-surface attribution term; [acp-kernel](https://github.com/ranxianglei/acp-kernel) is also credited in that lock. These results concern the executed components and pins; they do not claim to test every current upstream feature.

Q2 uses `paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, with the pinned quantized ONNX model. It has 384 dimensions, 128-token windows with 32-token overlap, attention-mask mean pooling and L2 normalization, and one inference thread. Its fingerprint is `2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25`. The ai-memory binary uses its own pinned local `all-MiniLM-L6-v2` files. Models and inference stacks differ by design; no claim of equivalent model compute is made.

### Measurement surfaces

There are two separate experiments within this run:

1. **Native API:** baseline lexical, candidate lexical and candidate Q2 each make 256 calls at all six tokenizer/budget combinations, giving **4,608 actual recall calls**. Each call uses top five, an 8,000-character cap, one of 512/1,024/2,048 tokens, result caching disabled and one repetition. Timing includes native context construction and token-budget enforcement. Fresh source ingestion and optional semantic indexing are outside query timing and reported separately.
2. **Common supplied-page components:** six modes each perform 256 searches three times, giving **4,608 actual search calls**. All six tokenizer/budget projections reuse the **first native response**, with common whole-page/block packing performed offline. Search is not repeated to generate a more favorable packing result. The three actual search repetitions measure timing and hit stability; they do not create 768 independent quality questions.

Book component calls use a 100,000-character internal recall cap and still include its native hierarchy/context assembly. The common packer then rebuilds a source-page context under each reference token cap. These component scores are therefore a distinct protocol from the Book native API's own 8,000-character and token-budget packing.

For ai-memory, metadata hits occupy their original top-five slots, earn zero evidence credit and are not replaced. On the first repetition, the adapter actually reads **every mapped top-five page in full**, even if a later budget projection does not fit that page. It records native search cost, native payloads, each read and per-question search-plus-all-reads time. Other tested components do not need an additional page-read call for this projection.

The resource/timing boundaries differ: Book is in-process Python, claude-mem runs native SQLite/Bun through a JSON bridge, ai-memory uses a released local service with HTTP/MCP, and billion-context runs a Node search kernel. Native search, adapter roundtrip and first search plus all reads are separate metrics. A table of these measurements is not a whole-product speed ratio or a full write/observe/summarize/generate comparison.

### Metrics and statistical scope

**Evidence recall** is matched complete annotations divided by 607. **Complete evidence** is questions with every required annotation present divided by 256. **MRR** is mean reciprocal position of the first supporting item in the returned/packed context. For common packing, metadata or oversized blocks may be omitted, so packed-context MRR is not raw native top-five MRR.

Token counts are measured with tiktoken 0.12.0 using `cl100k_base` and `o200k_base`. Native content, serialized native payload, full-read content/payload and common packed context are distinct surfaces. They are not provider billing estimates.

The unit for quality is the question, with annotations nested within questions. The six budget/tokenizer cells and three timing repetitions are correlated views of those same 256 questions. Reported differences are descriptive results for this frozen cohort; no post hoc significance test or universal population advantage is claimed. A larger token cap can leave scores unchanged when the top-five pages already fit, and it cannot recover an absent hit.

All questions are answerable. This cohort cannot measure unsupported-answer abstention, hallucination prevention or generated-answer accuracy. The small low-overlap diagnostic has only six questions and must not carry a broad semantic-generalization claim. Cross-session/chapter labels arise from the synthetic paragraph mapping; they are not evidence of transfer to private conversational memory.


## Native API results: all six configurations

Sources: [baseline lexical](../benchmarks/results/round3-comparison-43267797247-1/baseline-native.summary.json), [candidate lexical](../benchmarks/results/round3-comparison-43267797247-1/candidate-native.summary.json), [candidate Q2](../benchmarks/results/round3-comparison-43267797247-1/candidate-semantic-native.summary.json). These same summaries provide the native timing, setup and resource measurements below.

The baseline and candidate lexical rows are intentionally both shown. Their identical aggregate quality is backed by complete payload equality, rather than inferred from rounded scores. Q2 uses the existing optional model and fusion rules. Every mean context token value uses that row's tokenizer.

| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | MRR | Mean context tokens |
|---|---|---|---|---|---|---|
| v0.3.0 lexical | cl100k | 512 | 399/607 (65.73%) | 92/256 (35.94%) | 0.7998 | 476.5 |
| v0.3.0 lexical | cl100k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 808.0 |
| v0.3.0 lexical | cl100k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 809.2 |
| v0.3.0 lexical | o200k | 512 | 399/607 (65.73%) | 91/256 (35.55%) | 0.8008 | 476.7 |
| v0.3.0 lexical | o200k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 806.6 |
| v0.3.0 lexical | o200k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 806.8 |
| v0.3.1 lexical | cl100k | 512 | 399/607 (65.73%) | 92/256 (35.94%) | 0.7998 | 476.5 |
| v0.3.1 lexical | cl100k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 808.0 |
| v0.3.1 lexical | cl100k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 809.2 |
| v0.3.1 lexical | o200k | 512 | 399/607 (65.73%) | 91/256 (35.55%) | 0.8008 | 476.7 |
| v0.3.1 lexical | o200k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 806.6 |
| v0.3.1 lexical | o200k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 806.8 |
| v0.3.1 Q2 | cl100k | 512 | 393/607 (64.74%) | 86/256 (33.59%) | 0.8171 | 479.2 |
| v0.3.1 Q2 | cl100k | 1024 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 824.4 |
| v0.3.1 Q2 | cl100k | 2048 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 828.4 |
| v0.3.1 Q2 | o200k | 512 | 392/607 (64.58%) | 85/256 (33.20%) | 0.8171 | 479.0 |
| v0.3.1 Q2 | o200k | 1024 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 822.3 |
| v0.3.1 Q2 | o200k | 2048 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 825.7 |

### Native query time

Each entry contains **mean / p50 / p95 milliseconds**, with n=256 per cell. These fresh-cohort measurements run each native mode once per configuration. They are descriptive timing observations on this host, not another balanced performance gate or replacements for the earlier ABBA measurements.

| Tokenizer | Cap | v0.3.0 lexical | v0.3.1 lexical | v0.3.1 Q2 | Lexical p95 change |
|---|---|---|---|---|---|
| cl100k | 512 | 4.841 / 4.695 / 7.485 | 3.209 / 3.150 / 4.316 | 9.163 / 8.661 / 13.043 | -42.34% |
| cl100k | 1024 | 4.461 / 4.213 / 7.295 | 2.784 / 2.707 / 3.828 | 9.367 / 9.058 / 12.895 | -47.53% |
| cl100k | 2048 | 4.295 / 4.172 / 6.821 | 2.880 / 2.821 / 3.919 | 9.315 / 8.905 / 12.831 | -42.55% |
| o200k | 512 | 5.406 / 5.206 / 8.242 | 3.952 / 3.928 / 5.306 | 10.171 / 9.594 / 13.871 | -35.62% |
| o200k | 1024 | 4.812 / 4.684 / 7.739 | 3.358 / 3.283 / 4.339 | 9.970 / 9.681 / 13.523 | -43.93% |
| o200k | 2048 | 4.723 / 4.561 / 7.495 | 3.242 / 3.174 / 4.397 | 9.732 / 9.083 / 13.103 | -41.34% |

### Q2 paired gains and losses

Every paired change is retained in the [assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json), including query IDs and annotation positions. The counts below are actual gains and losses, not just net changes. A question can change context without changing its complete-evidence status. Annotation changes and complete-question changes have different denominators.

| Surface | Tokenizer | Cap | Annotations gained / lost | Complete questions gained / lost | Recall change pp | Complete change pp | Changed contexts |
|---|---|---|---|---|---|---|---|
| Native API | cl100k | 512 | 41 / 47 | 22 / 28 | -0.99 | -2.34 | 213 |
| Native API | cl100k | 1024 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Native API | cl100k | 2048 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Native API | o200k | 512 | 41 / 48 | 22 / 28 | -1.15 | -2.34 | 211 |
| Native API | o200k | 1024 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Native API | o200k | 2048 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Common packing | cl100k | 512 | 45 / 44 | 22 / 23 | +0.16 | -0.39 | 216 |
| Common packing | cl100k | 1024 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Common packing | cl100k | 2048 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Common packing | o200k | 512 | 44 / 46 | 21 / 24 | -0.33 | -1.17 | 220 |
| Common packing | o200k | 1024 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |
| Common packing | o200k | 2048 | 33 / 30 | 24 / 18 | +0.49 | +2.34 | 253 |

At native 512 tokens, both tokenizers lose six complete questions net: 22 gains and 28 losses. cl100k loses six annotations net, and o200k loses seven. At native 1,024/2,048, Q2 gains six complete questions net (24 gains, 18 losses) and three annotations net (33 gains, 30 losses). A favorable aggregate therefore does not imply zero individual regressions.

The common packer also retains 512-token Q2 losses: complete questions fall 98 → 97 with cl100k and 100 → 97 with o200k. The distinct native and component packing policies explain why their small-budget scores differ. Integrity passing does not turn Q2 into a uniformly better mode.

## Common supplied-page quality: all six configurations

Sources: [baseline lexical](../benchmarks/results/round3-comparison-43267797247-1/baseline-component.summary.json), [candidate lexical](../benchmarks/results/round3-comparison-43267797247-1/candidate-component.summary.json), [candidate Q2](../benchmarks/results/round3-comparison-43267797247-1/candidate-semantic-component.summary.json), [claude-mem](../benchmarks/results/round3-comparison-43267797247-1/claude-mem-fts.summary.json), [ai-memory](../benchmarks/results/round3-comparison-43267797247-1/ai-memory-hybrid.summary.json), [billion-context](../benchmarks/results/round3-comparison-43267797247-1/billion-context.summary.json). They also supply the component latency, read/token, setup, storage and resource tables below.

Three actual native search repetitions were retained for each component. **Zero repeated-hit changes** were observed for all six modes. The quality rows use the first response only, so none of the three repetitions is selected for a better score. In this run ai-memory had **zero unmapped metadata hits**; the registered zero-credit/no-replacement rule still applies.

MRR below is packed-context MRR, after common whole-block packing. The raw native result positions remain in the full stage reports.

| Mode | Tokenizer | Cap | Evidence recall | Complete evidence | MRR | Mean context tokens |
|---|---|---|---|---|---|---|
| v0.3.0 lexical | cl100k | 512 | 409/607 (67.38%) | 98/256 (38.28%) | 0.8011 | 451.5 |
| v0.3.0 lexical | cl100k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 719.8 |
| v0.3.0 lexical | cl100k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 719.8 |
| v0.3.0 lexical | o200k | 512 | 412/607 (67.87%) | 100/256 (39.06%) | 0.8024 | 453.3 |
| v0.3.0 lexical | o200k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 712.3 |
| v0.3.0 lexical | o200k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 712.3 |
| v0.3.1 lexical | cl100k | 512 | 409/607 (67.38%) | 98/256 (38.28%) | 0.8011 | 451.5 |
| v0.3.1 lexical | cl100k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 719.8 |
| v0.3.1 lexical | cl100k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 719.8 |
| v0.3.1 lexical | o200k | 512 | 412/607 (67.87%) | 100/256 (39.06%) | 0.8024 | 453.3 |
| v0.3.1 lexical | o200k | 1024 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 712.3 |
| v0.3.1 lexical | o200k | 2048 | 463/607 (76.28%) | 134/256 (52.34%) | 0.8132 | 712.3 |
| v0.3.1 Q2 | cl100k | 512 | 410/607 (67.55%) | 97/256 (37.89%) | 0.8177 | 452.1 |
| v0.3.1 Q2 | cl100k | 1024 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 739.0 |
| v0.3.1 Q2 | cl100k | 2048 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 739.0 |
| v0.3.1 Q2 | o200k | 512 | 410/607 (67.55%) | 97/256 (37.89%) | 0.8190 | 453.0 |
| v0.3.1 Q2 | o200k | 1024 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 731.2 |
| v0.3.1 Q2 | o200k | 2048 | 466/607 (76.77%) | 140/256 (54.69%) | 0.8239 | 731.2 |
| claude-mem FTS | cl100k | 512 | 372/607 (61.29%) | 85/256 (33.20%) | 0.7568 | 452.9 |
| claude-mem FTS | cl100k | 1024 | 429/607 (70.68%) | 116/256 (45.31%) | 0.7674 | 715.8 |
| claude-mem FTS | cl100k | 2048 | 429/607 (70.68%) | 116/256 (45.31%) | 0.7674 | 715.8 |
| claude-mem FTS | o200k | 512 | 375/607 (61.78%) | 87/256 (33.98%) | 0.7578 | 453.3 |
| claude-mem FTS | o200k | 1024 | 429/607 (70.68%) | 116/256 (45.31%) | 0.7674 | 708.2 |
| claude-mem FTS | o200k | 2048 | 429/607 (70.68%) | 116/256 (45.31%) | 0.7674 | 708.2 |
| ai-memory local hybrid | cl100k | 512 | 408/607 (67.22%) | 102/256 (39.84%) | 0.8063 | 451.1 |
| ai-memory local hybrid | cl100k | 1024 | 469/607 (77.27%) | 143/256 (55.86%) | 0.8182 | 716.8 |
| ai-memory local hybrid | cl100k | 2048 | 469/607 (77.27%) | 143/256 (55.86%) | 0.8182 | 716.8 |
| ai-memory local hybrid | o200k | 512 | 411/607 (67.71%) | 105/256 (41.02%) | 0.8063 | 448.6 |
| ai-memory local hybrid | o200k | 1024 | 469/607 (77.27%) | 143/256 (55.86%) | 0.8182 | 709.3 |
| ai-memory local hybrid | o200k | 2048 | 469/607 (77.27%) | 143/256 (55.86%) | 0.8182 | 709.3 |
| billion-context kernel | cl100k | 512 | 399/607 (65.73%) | 96/256 (37.50%) | 0.8154 | 449.4 |
| billion-context kernel | cl100k | 1024 | 479/607 (78.91%) | 149/256 (58.20%) | 0.8277 | 762.3 |
| billion-context kernel | cl100k | 2048 | 479/607 (78.91%) | 149/256 (58.20%) | 0.8277 | 762.3 |
| billion-context kernel | o200k | 512 | 400/607 (65.90%) | 97/256 (37.89%) | 0.8154 | 449.2 |
| billion-context kernel | o200k | 1024 | 479/607 (78.91%) | 149/256 (58.20%) | 0.8277 | 754.4 |
| billion-context kernel | o200k | 2048 | 479/607 (78.91%) | 149/256 (58.20%) | 0.8277 | 754.4 |

At fixed top five, the 2,048-token common contexts match the 1,024-token quality and token counts in this cohort. This does not establish that 2,048 tokens never helps other corpora or result limits.

## Query latency, page reads and token surfaces

Native search and adapter roundtrip each contain **768 measured searches per component**. The common-packing timing column is a separate offline operation at cl100k/1,024, included to expose its cost rather than adding it to native search. All six packing-time distributions remain in the summaries.

| Component | Native search mean / p50 / p95 ms | Adapter roundtrip mean / p50 / p95 ms | Common packing mean / p95 ms, cl100k 1024 |
|---|---|---|---|
| v0.3.0 lexical | 3.273 / 3.133 / 5.828 | 3.273 / 3.133 / 5.828 | 0.599 / 0.738 |
| v0.3.1 lexical | 1.852 / 1.766 / 2.784 | 1.852 / 1.766 / 2.784 | 0.606 / 0.759 |
| v0.3.1 Q2 | 7.780 / 7.415 / 11.226 | 7.780 / 7.415 / 11.226 | 0.611 / 0.743 |
| claude-mem FTS | 12.389 / 11.494 / 22.484 | 12.738 / 11.781 / 22.826 | 0.558 / 0.692 |
| ai-memory local hybrid | 21.820 / 21.168 / 27.545 | 21.820 / 21.168 / 27.545 | 0.657 / 0.814 |
| billion-context kernel | 0.316 / 0.189 / 0.793 | 0.457 / 0.285 / 1.010 | 0.698 / 0.844 |

The next table separates the first pass from the two subsequent passes. For search plus reads, each question's actual search roundtrip is added to all its page-read roundtrips **before** percentiles are computed; it is not a sum of unrelated p95 values.

| Component | First search mean / p50 / p95 ms (n=256) | Repeat search mean / p50 / p95 ms (n=512) | First search + all reads mean / p50 / p95 ms (n=256) |
|---|---|---|---|
| v0.3.0 lexical | 3.305 / 3.165 / 5.942 | 3.257 / 3.114 / 5.783 | 3.305 / 3.165 / 5.942 |
| v0.3.1 lexical | 1.856 / 1.756 / 2.818 | 1.850 / 1.770 / 2.774 | 1.856 / 1.756 / 2.818 |
| v0.3.1 Q2 | 7.721 / 7.365 / 11.046 | 7.810 / 7.469 / 11.263 | 7.721 / 7.365 / 11.046 |
| claude-mem FTS | 12.875 / 11.982 / 22.931 | 12.669 / 11.693 / 22.740 | 12.875 / 11.982 / 22.931 |
| ai-memory local hybrid | 21.406 / 20.488 / 26.623 | 22.026 / 21.377 / 27.592 | 25.006 / 23.966 / 30.532 |
| billion-context kernel | 0.842 / 0.689 / 1.480 | 0.265 / 0.248 / 0.372 | 0.842 / 0.689 / 1.480 |

The billion-context kernel's first-pass and repeated timing differ substantially, which is why both remain visible. This run does not claim OS-cold-cache behavior or equal internal caching policies across products.

All token values below are means over the first 256 responses; `cl/o` means cl100k_base / o200k_base. A dash means that surface was not separately instrumented, not zero tokens. Payloads include each adapter's recorded native response serialization. The claude-mem surface is its canonical row-array JSON, rather than an unmeasured MCP/viewer envelope.

| Component | Search content tokens cl/o | Search payload tokens cl/o | Read content tokens cl/o | Read payload tokens cl/o | Reads/query | Read mean ms/query |
|---|---|---|---|---|---|---|
| v0.3.0 lexical | 809.2 / 806.8 | 3983.5 / 3998.4 | 0.0 / 0.0 | 0.0 / 0.0 | 0.00 | 0.000 |
| v0.3.1 lexical | 809.2 / 806.8 | 3983.5 / 3998.4 | 0.0 / 0.0 | 0.0 / 0.0 | 0.00 | 0.000 |
| v0.3.1 Q2 | 828.4 / 825.7 | 4097.3 / 4112.5 | 0.0 / 0.0 | 0.0 / 0.0 | 0.00 | 0.000 |
| claude-mem FTS | — | 1641.3 / 1625.7 | 0.0 / 0.0 | 0.0 / 0.0 | 0.00 | 0.000 |
| ai-memory local hybrid | 962.6 / 957.7 | 1026.3 / 1023.4 | 1626.5 / 1613.4 | 1843.1 / 1834.9 | 5.00 | 3.600 |
| billion-context kernel | — | 582.7 / 575.8 | 0.0 / 0.0 | 0.0 / 0.0 | 0.00 | 0.000 |

ai-memory made five native full-page reads per question, or **1,280 reads**. It performed those reads even when later common packing omitted a page. Read payloads are therefore not interchangeable with the smaller final context. Book's rich native response also contains metadata beyond its context, so its native payload is larger than the common context.

These figures do not support a claim that Book always sends fewer tokens than every comparator. For example, its lexical serialized search payload is larger than the other tested native payload surfaces in this run. No provider model, final generation call, or billing policy is measured. All stages configured **zero generative model calls**; Book Q2 and ai-memory still use local embedding models. Zero-LLM operation is not unique to Book.

## Setup, model preparation, memory and storage

All modes ran sequentially on the same four-logical-CPU Linux runner. The host record pins Python 3.12.16, Python SQLite 3.45.1, tiktoken 0.12.0, onnxruntime 1.31.1, tokenizers 0.23.3, numpy 2.5.4 and pyarrow 26.0.1. claude-mem uses Bun 1.3.13 / SQLite 3.51.2; billion-context uses Node 24.22.1. Different native stacks are part of these boundaries.

### Asset preparation

The [checkpoint](../benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json) records all six preparation stages. Each started with an empty task cache. Prepared sizes are regular-file content lengths and may include archives/extracted files; they are **not network transfer sizes**. Python/Node package installation and the runner's base environment are outside this table.

| Prepared asset | Wall ms | Prepared regular-file bytes | Files |
|---|---|---|---|
| Pinned HotpotQA Parquet | 1123.657 | 27452575 | 1 |
| Two reference tokenizers | 448.366 | 5295048 | 2 |
| ai-memory binary and local model | 2039.484 | 174868526 | 6 |
| claude-mem source and Bun | 4418.134 | 178639496 | 986 |
| billion-context locked kernel | 2299.463 | 163611 | 31 |
| Book Q2 model and tokenizer | 2073.302 | 127535388 | 2 |

An empty task asset cache does not establish a cold OS/page cache. The ai-memory setup metadata reports zero new model-download bytes because the pinned files were prepared in the stage above. That zero is not a zero-download installation claim.

### Engine setup and observed memory

RSS is sampled for the Python evaluator worker plus its live descendants every 20 ms. It includes loaded corpus/evaluator memory, can count shared mappings more than once, and records observed lower bounds rather than unique physical-memory peaks. Worker peak is the worker's own high-water mark, not an additional amount to add to the sampled process tree. Finalization is shown because serialization/subprocess overlap can produce a larger observation than query execution.

| Mode / surface | Setup wall ms | Setup RSS MiB | Query RSS MiB | Finalization RSS MiB | Worker peak MiB |
|---|---|---|---|---|---|
| v0.3.0 lexical / native | 4075.735 | 776.15 | 546.88 | 666.52 | 666.18 |
| v0.3.1 lexical / native | 4235.636 | 549.47 | 533.07 | 1074.07 | 649.08 |
| v0.3.1 Q2 / native | 115130.397 | 1286.11 | 1269.98 | 1305.11 | 1337.09 |
| v0.3.0 lexical / component | 544.287 | 561.74 | 540.86 | 1093.13 | 659.06 |
| v0.3.1 lexical / component | 546.956 | 549.66 | 529.17 | 647.12 | 647.01 |
| v0.3.1 Q2 / component | 112553.168 | 1233.96 | 1234.28 | 1287.73 | 1287.40 |
| claude-mem FTS / component | 1589.911 | 675.75 | 635.18 | 650.86 | 719.51 |
| ai-memory local hybrid / component | 644734.591 | 716.75 | 714.48 | 1013.11 | 619.12 |
| billion-context kernel / component | 162.853 | 558.29 | 675.97 | 675.97 | 617.63 |

Native Book stages build a fresh archive from the original sentence turns. Source ingestion was 4,055.717 ms for baseline lexical, 4,213.831 ms for candidate lexical and 4,147.982 ms for candidate Q2; runtime imports were separately recorded at 27.476, 29.094 and 36.581 ms. The export step itself ingested the canonical archive once in 4,163.849 ms.

Book component stages copy the same already-ingested archive and measure their own setup; they do not repeat source ingestion. Candidate lexical component copying took 9.180 ms and existing-database opening 0.800 ms; the full reported setup includes additional initialization/verification. These costs are not substitutes for the fresh empty-database startup metric in the independent performance review.

Q2 native model load took **862.685 ms**, followed by **110,093.745 ms** to build its semantic index. Total native setup was **115,130.397 ms**, versus 4,235.636 ms for lexical. The component run separately loaded the model in 844.462 ms and built the index in 111,079.932 ms. Both produced **4,831 windows and 7,420,416 raw vector bytes** over 3,896 pages. Their persisted index/vector digest is identical: `392801730b3c8ea5e30687359ba6a2b4b958564d5ed228de080517316838824f`. This verifies persisted index identity, not separately measured query-embedding identity.

claude-mem initialized its native schema in 28.268 ms and loaded the supplied pages with FTS triggers in 509.384 ms; full adapter setup was 1,589.911 ms. This is a bulk supplied-source index, excluding its observer workflow. ai-memory used native HTTP writes with local embeddings: startup 875.437 ms, ingestion 643,023.189 ms and a final embedding backfill check of 828.548 ms. That check reported 0 newly embedded, 3,896 skipped and 0 failures, consistent with embeddings already created during writes. Its total engine setup was **644,734.591 ms**. billion-context's in-memory search-kernel setup was **162.853 ms**.

These setup boundaries differ substantially: fresh archive ingestion, copied archive, bulk FTS insertion, native writes with embeddings, and in-memory kernel loading are not identical operations. Their measured costs are all disclosed, without treating them as end-to-end product ratios.

### Native state

State sizes below are regular-file content lengths excluding symlinked model caches and the harness attempt ledger. They are not filesystem allocated blocks. State may include native source-page Markdown and logs in addition to SQLite files. Model/cache sizes remain in the preparation table.

| Mode / surface | Live state bytes | Main SQLite bytes | Live WAL bytes | Live SHM bytes | State bytes after close |
|---|---|---|---|---|---|
| v0.3.0 lexical / native | 40280936 | 33775616 | 6472552 | 32768 | 40280936 |
| v0.3.1 lexical / native | 40280936 | 33775616 | 6472552 | 32768 | 40280936 |
| v0.3.1 Q2 / native | 54988384 | 43782144 | 11173472 | 32768 | 54988384 |
| v0.3.0 lexical / component | 33808384 | 33775616 | 0 | 32768 | 33808384 |
| v0.3.1 lexical / component | 33808384 | 33775616 | 0 | 32768 | 33808384 |
| v0.3.1 Q2 / component | 54016064 | 43782144 | 10201152 | 32768 | 54016064 |
| claude-mem FTS / component | 20626650 | 8790016 | 11803832 | 32768 | 8822818 |
| ai-memory local hybrid / component | 73818921 | 18669568 | 4503192 | 32768 | 0 (cleaned up) |
| billion-context kernel / component | 0 | — | — | — | 0 |

ai-memory's after-close zero means the adapter cleaned up its temporary native state; its measured live footprint is **73,818,921 bytes**, not zero. billion-context's zero is the absence of persistent corpus state in this in-memory kernel experiment, not a measurement of a complete persistent product. claude-mem's WAL is checkpointed on close. Book rows retain their recorded main/WAL/SHM snapshots; no hypothetical post-checkpoint size replaces them.

## Diagnostic groups and remaining weaknesses

Every selected question requires multiple evidence annotations and crosses the synthetic chapter/session boundary. Those three labels each contain the same 256 questions, rather than independent corroborating samples. Bridge questions number 199 and comparison questions 57; all category/tokenizer/budget metrics remain in the per-stage summaries.

The smallest registered diagnostic, lexical overlap ≤0.25, has n=6 and 12 evidence annotations. Both budgets below use cl100k. Showing the denominator prevents its larger percentage changes from being mistaken for a broad result.

| Mode / surface | Questions | Recall at 512 | Complete at 512 | Recall at 1024 | Complete at 1024 |
|---|---|---|---|---|---|
| v0.3.0 lexical / native | 6 | 4/12 (33.33%) | 0/6 | 6/12 (50.00%) | 0/6 |
| v0.3.1 lexical / native | 6 | 4/12 (33.33%) | 0/6 | 6/12 (50.00%) | 0/6 |
| v0.3.1 Q2 / native | 6 | 6/12 (50.00%) | 0/6 | 7/12 (58.33%) | 1/6 |
| v0.3.0 lexical / component | 6 | 5/12 (41.67%) | 0/6 | 6/12 (50.00%) | 0/6 |
| v0.3.1 lexical / component | 6 | 5/12 (41.67%) | 0/6 | 6/12 (50.00%) | 0/6 |
| v0.3.1 Q2 / component | 6 | 6/12 (50.00%) | 0/6 | 7/12 (58.33%) | 1/6 |
| claude-mem FTS / component | 6 | 5/12 (41.67%) | 0/6 | 6/12 (50.00%) | 0/6 |
| ai-memory local hybrid / component | 6 | 7/12 (58.33%) | 1/6 | 7/12 (58.33%) | 1/6 |
| billion-context kernel / component | 6 | 5/12 (41.67%) | 1/6 | 7/12 (58.33%) | 1/6 |

In particular, Q2's native 512-token low-overlap recall rises from 4/12 to 6/12 annotations while complete evidence remains 0/6. That subgroup does not reverse the aggregate 512-token loss. ai-memory completes 1/6 in that small 512-token group; the data do not establish that Book's optional semantic mode dominates the compared hybrid engine.

The two Book modes still miss all required evidence for many questions: lexical completes 134/256 and Q2 140/256 at the larger budgets. All external quality losses shown above remain part of the conclusion. Top-five retrieval, source-page construction, strict complete-sentence matching and downstream packing each limit the measured outcome.

The earlier project-local statistics candidate was rejected on its old-data gate and was not included here. `project_statistics_gate.status=not-included` with `qualified=null` is not a pass; the [separate recovered decision](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/decision.json) is explicitly false. No fresh-cohort failure was used to tune it or reopen the closed novelty experiments.

## Integrity, evidence and reproducibility

The registered evaluator audited all ten stage reports and their started/completed ledgers, required exact source/host/plan/binding/manifest/corpus identities, checked all 607/256 denominators and all source/scope/budget invariants, compared complete default payload hashes, and verified the Q2 persisted index identity. The final checkpoint and assessment are both `complete-verified`.

An independent review additionally checked all **54 quality cells**, the common denominators/invariant totals, all **12 Q2 paired-gain/loss net differences**, and the measurement boundaries against the frozen evaluator. No arithmetic inconsistency was found. That review does not replace the raw-report audit or turn descriptive differences into statistical guarantees.

| Evidence | Location |
|---|---|
| Successful workflow | [43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247) |
| Final result branch / exact commit | `validation/round3-comparison-43267797247-1` / `c99f20531053b1c164fc5a5d3fa8e0c831eeb4de` |
| Final checkpoint and output hashes | [checkpoint JSON](../benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json) |
| Cross-stage audit and every Q2 gain/loss | [assessment.json](../benchmarks/results/round3-comparison-43267797247-1/assessment.json) |
| Unmodified generated report | [report.md](../benchmarks/results/round3-comparison-43267797247-1/report.md) |
| Source-free stage artifacts | [results directory](../benchmarks/results/round3-comparison-43267797247-1/) |
| Frozen runner/evaluator | [run_round3_comparison.py](../scripts/run_round3_comparison.py), [round3_comparison.py](../scripts/round3_comparison.py) |
| Formal default performance and startup decision | [optimization-round3.md](optimization-round3.md), [round3-startup-resource-review.md](round3-startup-resource-review.md) |

Each stage has a small `.summary.json`, a complete `.json.gz` and a `.attempts.jsonl.gz` under that directory. The compressed reports retain per-query evidence ranks, source/payload hashes, timings and resource metadata. Original questions, answers and passages are fetched from the separately pinned public source; they are not reproduced in these reports.

A read-only verification uses the frozen evaluator, binding, manifest, complete stage reports and existing checkpoint:

```bash
python scripts/round3_comparison.py audit \
  --checkpoint benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json \
  --verify-existing
```

Use the pinned dependencies and exact evaluator files recorded in the binding. The audit recomputes the assessment from recorded reports and checks the existing Markdown; it does not rerun retrieval. Do not overwrite these historical artifacts or rerun selectively to replace unfavorable samples.

This report establishes a verified implementation with specific measured strengths and disclosed tradeoffs. It does not announce a v0.3.1 tag or public release.
