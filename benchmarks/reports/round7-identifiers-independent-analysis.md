# Round 7: independent identifier retrieval analysis

**Conclusion:** the bounded identifier-retrieval quality gate passes. The evidence supports only a narrowly described acronym retrieval improvement with an explicit latency tradeoff. It does **not** prove faster AI answers, better generated patches, or superiority over the raw-code search control. Final publication remains a separate release decision.

Candidate runtime: `e576330cc84230b0a60fc7483c098c792e9ef5784b0642ed698f5eb5dafa4c56`. Baseline runtime: `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242`. No product calls, timing experiments, source edits or reruns were performed for this analysis.

## Evidence and independent reconstruction

- [Original summary](round7-identifiers-first/summary.json), [actual binding](round7-identifiers-first/binding.json), [archive manifest](round7-identifiers-first/archive-manifest.json), and [lossless raw archive](round7-identifiers-first/raw.tar.xz).
- [Complete machine-readable paired analysis](round7-identifiers-independent-analysis.json) retains every query, all three saved timing samples, all quality gains/losses, all aggregate adverse metrics, and original artifact SHA-256 values.
- 140 source snippets, 44 target classes, four query forms, 176 distinct queries, five arms and three repetitions: **2,640 completed records / 5,280 start-completion events**. Of these, **2,112 are retrieval calls** and 528 are empty no-memory diagnostics. Both token budgets are **1,024 and 4,096**.
- Independently rebuilt every shared source context, exact token count, quality score, all 40 cells, and the registered gate from saved rows. No errors, missing cells, scope errors or token-cap violations were found. All five arms returned identical quality/ranking/context results across their three repetitions.
- The actual run uses the retained **v2 binding**, after a documented zero-score correction strengthened the raw-text control to ordered compact-name equality. Product runtime, corpus, queries, budgets, arms and acceptance thresholds were unchanged. [Correction](../experiments/round7-identifiers-pre-score-correction.json).

## Quality: every query form and both budgets

Values below are successful retained declarations out of **44 unique queries**, not counts multiplied by repetitions. A hit requires the expected source ID and declaration in the shared packed context.

| Query form | Token cap | v0.3.4 | Candidate | Raw-code search | Billion component | Candidate − v0.3.4 |
|---|---:|---:|---:|---:|---:|---:|
| exact | 1024 | 38/44 (86.36%) | 38/44 (86.36%) | 43/44 (97.73%) | 33/44 (75.00%) | +0 (+0.00 pp) |
| exact | 4096 | 43/44 (97.73%) | 43/44 (97.73%) | 43/44 (97.73%) | 42/44 (95.45%) | +0 (+0.00 pp) |
| spaced | 1024 | 22/44 (50.00%) | 31/44 (70.45%) | 43/44 (97.73%) | 21/44 (47.73%) | +9 (+20.45 pp) |
| spaced | 4096 | 28/44 (63.64%) | 37/44 (84.09%) | 43/44 (97.73%) | 25/44 (56.82%) | +9 (+20.45 pp) |
| lowercase | 1024 | 22/44 (50.00%) | 22/44 (50.00%) | 43/44 (97.73%) | 21/44 (47.73%) | +0 (+0.00 pp) |
| lowercase | 4096 | 28/44 (63.64%) | 28/44 (63.64%) | 43/44 (97.73%) | 25/44 (56.82%) | +0 (+0.00 pp) |
| question | 1024 | 20/44 (45.45%) | 29/44 (65.91%) | 43/44 (97.73%) | 15/44 (34.09%) | +9 (+20.45 pp) |
| question | 4096 | 28/44 (63.64%) | 37/44 (84.09%) | 43/44 (97.73%) | 20/44 (45.45%) | +9 (+20.45 pp) |

The registered spaced-plus-lowercase 1,024-token metric improves by **10.22727 percentage points** and passes its 10-point requirement. The entire improvement comes from spaced queries; lowercase retrieval is unchanged. Spaced questions improve too, but are separately reported rather than folded into that gate. No-memory returns no documents and has zero retrieval hits throughout; no model answer was generated in that arm.

### Unpacked first result and reciprocal rank

Top1/MRR are measured on the original ranked source list, before shared packing, so they are the same at both budgets.

| Form | v0.3.4 top1 / MRR | Candidate top1 / MRR | Raw-code top1 / MRR | Billion top1 / MRR |
|---|---:|---:|---:|---:|
| exact | 61.36% / 0.759470 | 61.36% / 0.759470 | 68.18% / 0.825758 | 47.73% / 0.654924 |
| spaced | 31.82% / 0.428030 | 40.91% / 0.570076 | 68.18% / 0.825758 | 22.73% / 0.351894 |
| lowercase | 31.82% / 0.428030 | 31.82% / 0.428030 | 68.18% / 0.825758 | 22.73% / 0.351894 |
| question | 29.55% / 0.402273 | 40.91% / 0.554924 | 68.18% / 0.825758 | 22.73% / 0.305682 |

### Paired changes, including competitor losses

Each entry is unique-query gains / losses; aggregate superiority does not erase individual losses. All per-query identities and before/after values are in the JSON.

| Comparator | Form | Cap | Hit gains / losses | Top1 gains / losses | MRR gains / losses |
|---|---|---:|---:|---:|---:|
| v0.3.4 | exact | 1024 | 0 / 0 | 0 / 0 | 0 / 0 |
| v0.3.4 | exact | 4096 | 0 / 0 | 0 / 0 | 0 / 0 |
| v0.3.4 | spaced | 1024 | 9 / 0 | 4 / 0 | 13 / 0 |
| v0.3.4 | spaced | 4096 | 9 / 0 | 4 / 0 | 13 / 0 |
| v0.3.4 | lowercase | 1024 | 0 / 0 | 0 / 0 | 0 / 0 |
| v0.3.4 | lowercase | 4096 | 0 / 0 | 0 / 0 | 0 / 0 |
| v0.3.4 | question | 1024 | 9 / 0 | 5 / 0 | 13 / 0 |
| v0.3.4 | question | 4096 | 9 / 0 | 5 / 0 | 13 / 0 |
| raw-text-search | exact | 1024 | 0 / 5 | 7 / 10 | 7 / 14 |
| raw-text-search | exact | 4096 | 0 / 0 | 7 / 10 | 7 / 14 |
| raw-text-search | spaced | 1024 | 0 / 12 | 6 / 18 | 7 / 24 |
| raw-text-search | spaced | 4096 | 0 / 6 | 6 / 18 | 7 / 24 |
| raw-text-search | lowercase | 1024 | 0 / 21 | 5 / 21 | 5 / 27 |
| raw-text-search | lowercase | 4096 | 0 / 15 | 5 / 21 | 5 / 27 |
| raw-text-search | question | 1024 | 0 / 14 | 5 / 17 | 5 / 23 |
| raw-text-search | question | 4096 | 0 / 6 | 5 / 17 | 5 / 23 |
| billion-context-component | exact | 1024 | 5 / 0 | 6 / 0 | 10 / 0 |
| billion-context-component | exact | 4096 | 1 / 0 | 6 / 0 | 10 / 0 |
| billion-context-component | spaced | 1024 | 15 / 5 | 11 / 3 | 24 / 8 |
| billion-context-component | spaced | 4096 | 15 / 3 | 11 / 3 | 24 / 8 |
| billion-context-component | lowercase | 1024 | 7 / 6 | 8 / 4 | 15 / 10 |
| billion-context-component | lowercase | 4096 | 7 / 4 | 8 / 4 | 15 / 10 |
| billion-context-component | question | 1024 | 18 / 4 | 11 / 3 | 27 / 4 |
| billion-context-component | question | 4096 | 19 / 2 | 11 / 3 | 27 / 4 |

## Exact-name regressions and changed outputs

**No exact-name query lost a retained hit, top1 success or reciprocal rank at either budget, in any repetition.** This is stronger than the aggregate exact-name gate for this specific set. It is not complete payload equivalence: three exact queries changed non-timing payload fields.

| Exact query | Changed fields | Candidate-count change | 1,024-cap token change | 4,096-cap token change |
|---|---|---:|---:|---:|
| `HTTPResponse` | candidate_count, context, context_chars, estimated_tokens, results | 3 → 5 | 933 → 933 | 1363 → 1696 |
| `HTTPServer` | candidate_count, context, context_chars, estimated_tokens, results, truncated | 4 → 7 | 573 → 855 | 573 → 1151 |
| `XMLParser` | candidate_count | 9 → 10 | 1011 → 1011 | 1011 → 1011 |

`HTTPResponse` and `HTTPServer` retain their measured answer-source success but return additional/different non-target context. `XMLParser` changes only candidate_count and still misses its declaration. These costs are retained, not relabeled as quality gains.

## Lookup latency: all query forms

All values are milliseconds. Lookup wall time includes the registered arm call plus source-ID validation; native Book latency is a separately saved inner timer. Shared packing and JSONL writing are outside this timer. These are descriptive component costs, not full model or product speed ratios.

| Form | v0.3.4 mean / median / p95 | Candidate mean / median / p95 | Mean change | p95 change | Raw-code mean / p95 | Billion mean / p95 |
|---|---:|---:|---:|---:|---:|---:|
| exact | 1.129905 / 0.967340 / 1.928552 | 2.099944 / 1.796598 / 3.548468 | +0.970039 (+85.85%) | +1.619916 (+84.00%) | 0.111210 / 0.159310 | 1.013934 / 1.331033 |
| spaced | 1.622409 / 1.568550 / 2.111757 | 6.934220 / 4.366989 / 17.091311 | +5.311811 (+327.40%) | +14.979554 (+709.34%) | 0.112773 / 0.162775 | 1.986421 / 5.159827 |
| lowercase | 1.538325 / 1.538705 / 2.160310 | 2.185225 / 1.603487 / 2.424507 | +0.646901 (+42.05%) | +0.264197 (+12.23%) | 0.107750 / 0.153430 | 0.853403 / 1.397953 |
| question | 1.673673 / 1.636653 / 2.284818 | 7.229564 / 4.648464 / 16.685872 | +5.555890 (+331.96%) | +14.401054 (+630.29%) | 0.113999 / 0.176867 | 1.000145 / 1.703673 |

### Every saved repetition

| Form | Repetition | v0.3.4 wall mean / median / p95 | Candidate wall mean / median / p95 | v0.3.4 native mean / p95 | Candidate native mean / p95 |
|---|---:|---:|---:|---:|---:|
| exact | 0 | 1.260372 / 0.957776 / 1.775471 | 2.249205 / 1.750433 / 3.548468 | 1.229975 / 1.740738 | 2.203712 / 3.504913 |
| exact | 1 | 1.052002 / 0.986920 / 1.726588 | 2.275985 / 1.851360 / 5.032640 | 1.024932 / 1.692086 | 2.209956 / 4.982526 |
| exact | 2 | 1.077342 / 0.954220 / 1.993068 | 1.774643 / 1.750379 / 2.885402 | 1.047113 / 1.971326 | 1.745268 / 2.845992 |
| spaced | 0 | 1.513977 / 1.554358 / 1.960189 | 6.766234 / 4.057048 / 16.030155 | 1.479560 / 1.925076 | 6.708836 / 15.980500 |
| spaced | 1 | 1.591597 / 1.592256 / 2.096364 | 7.388822 / 4.913702 / 17.633407 | 1.558325 / 2.061532 | 7.338029 / 17.572926 |
| spaced | 2 | 1.761652 / 1.563522 / 2.264137 | 6.647604 / 4.154736 / 14.704031 | 1.724492 / 2.218057 | 6.599666 / 14.661356 |
| lowercase | 0 | 1.544541 / 1.485840 / 2.456946 | 2.915832 / 1.593688 / 2.328322 | 1.512127 / 2.422764 | 2.791381 / 2.188952 |
| lowercase | 1 | 1.542560 / 1.584143 / 2.074521 | 1.827707 / 1.728065 / 3.297722 | 1.509247 / 2.033730 | 1.782653 / 3.247435 |
| lowercase | 2 | 1.527872 / 1.489536 / 2.063604 | 1.812138 / 1.525340 / 2.103485 | 1.492774 / 2.030575 | 1.763139 / 2.064887 |
| question | 0 | 1.656084 / 1.642396 / 2.169373 | 7.013714 / 4.533886 / 14.470920 | 1.623266 / 2.131006 | 6.964917 / 14.418091 |
| question | 1 | 1.676902 / 1.648740 / 2.089944 | 7.647851 / 5.571386 / 16.936438 | 1.642680 / 2.053810 | 7.592952 / 16.837720 |
| question | 2 | 1.688034 / 1.613733 / 2.650172 | 7.027126 / 4.613836 / 13.898591 | 1.650680 / 2.613276 | 6.982418 / 13.844840 |

Spaced and question mean/median/p95 increase in all three repetitions; exact-name lookup also costs more despite no added hit/top1/MRR success. The largest candidate lowercase wall sample is **59.236313 ms** and is retained. Its cause is unmeasured; it cannot be removed or automatically attributed to infrastructure. The original percentile definition is the sorted sample at `min(n−1, floor(0.95 × n))`, not an interpolated percentile.

## Context and setup/storage costs

| Form | Cap | v0.3.4 mean context tokens | Candidate | Change | Raw-code | Billion |
|---|---:|---:|---:|---:|---:|---:|
| exact | 1024 | 801.613636 | 808.022727 | +6.409091 | 837.863636 | 807.795455 |
| exact | 4096 | 1326.454545 | 1347.159091 | +20.704545 | 1530.318182 | 1725.318182 |
| spaced | 1024 | 800.977273 | 837.477273 | +36.500000 | 837.863636 | 849.159091 |
| spaced | 4096 | 1369.545455 | 1446.318182 | +76.772727 | 1530.318182 | 1673.795455 |
| lowercase | 1024 | 800.977273 | 800.977273 | +0.000000 | 837.863636 | 849.159091 |
| lowercase | 4096 | 1369.545455 | 1369.545455 | +0.000000 | 1530.318182 | 1673.795455 |
| question | 1024 | 858.431818 | 853.340909 | -5.090909 | 837.863636 | 843.204545 |
| question | 4096 | 1286.818182 | 1338.159091 | +51.340909 | 1530.318182 | 1623.772727 |

| Arm | Initialization + ingest, repetitions 0 / 1 / 2 (ms) | Mean (ms) | Recorded database bytes |
|---|---:|---:|---:|
| v0.3.4 | 126.068001 / 79.769240 / 223.530959 | 143.122733 | 1478656 |
| round7-candidate | 112.887493 / 123.813901 / 84.532440 | 107.077945 | 1478656 |
| raw-text-search | 25.255623 / 23.503076 / 33.411065 | 27.389921 | not recorded |
| billion-context-component | 234.319149 / 222.209450 / 202.814596 | 219.781065 | not recorded |
| no-memory | 0.008803 / 0.008964 / 0.008412 | 0.008726 | not recorded |

Book database size is identical between versions in all three stages. Initialization samples vary and measure different arm boundaries; this analysis makes no startup improvement claim. RSS, CPU, total model usage, tool retries and end-to-end answer/patch latency were not recorded. Missing competitor storage data does not mean zero storage.

## All 44 class outcomes

Each cell is `baseline 1024/4096 → candidate 1024/4096`, with 1 meaning the expected declaration survives shared packing and 0 meaning it does not. All three repetitions agree. Full source path/line/commit, all ranks and per-query timings are in the JSON.

| Class | Exact | Spaced | Lowercase | Question |
|---|---|---|---|---|
| `HTMLParser` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPSConnection` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPException` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPMessage` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPResponse` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPConnection` | 0/1 → 0/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPServer` | 1/1 → 1/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `ThreadingHTTPServer` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `BaseHTTPRequestHandler` | 0/1 → 0/1 | 1/1 → 1/1 | 1/1 → 1/1 | 0/1 → 0/1 |
| `SimpleHTTPRequestHandler` | 1/1 → 1/1 | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 |
| `CGIHTTPRequestHandler` | 1/1 → 1/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `JSONDecodeError` | 1/1 → 1/1 | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 |
| `JSONDecoder` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `JSONEncoder` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPBasicAuthHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPDigestAuthHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `AbstractHTTPHandler` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPHandler` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPSHandler` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `HTTPCookieProcessor` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `FTPHandler` | 1/1 → 1/1 | 0/1 → 1/1 | 0/1 → 0/1 | 0/1 → 1/1 |
| `CacheFTPHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `URLopener` | 1/1 → 1/1 | 0/0 → 0/1 | 0/0 → 0/0 | 0/0 → 0/1 |
| `FancyURLopener` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPErrorProcessor` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPDefaultErrorHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPRedirectHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPPasswordMgr` | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 |
| `HTTPPasswordMgrWithDefaultRealm` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `HTTPPasswordMgrWithPriorAuth` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `XMLPullParser` | 1/1 → 1/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `XMLParser` | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `C14NWriterTarget` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `QName` | 1/1 → 1/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `SimpleXMLRPCDispatcher` | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 |
| `SimpleXMLRPCRequestHandler` | 0/1 → 0/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `SimpleXMLRPCServer` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `MultiPathXMLRPCServer` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `CGIXMLRPCRequestHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 0/1 → 0/1 |
| `ServerHTMLDoc` | 1/1 → 1/1 | 0/0 → 1/1 | 0/0 → 0/0 | 0/0 → 1/1 |
| `XMLRPCDocGenerator` | 1/1 → 1/1 | 0/0 → 0/0 | 0/0 → 0/0 | 0/0 → 0/0 |
| `DocXMLRPCRequestHandler` | 1/1 → 1/1 | 0/1 → 0/1 | 0/1 → 0/1 | 0/1 → 0/1 |
| `DocXMLRPCServer` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| `DocCGIXMLRPCRequestHandler` | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 | 1/1 → 1/1 |

## Remaining failures and interpretation

| Form | Cap | Expected source absent from top five | Expected source excluded by shared packing | Retained declaration |
|---|---:|---:|---:|---:|
| exact | 1024 | 1 | 5 | 38 |
| exact | 4096 | 1 | 0 | 43 |
| spaced | 1024 | 7 | 6 | 31 |
| spaced | 4096 | 7 | 0 | 37 |
| lowercase | 1024 | 16 | 6 | 22 |
| lowercase | 4096 | 16 | 0 | 28 |
| question | 1024 | 7 | 8 | 29 |
| question | 4096 | 7 | 0 | 37 |

- **Observed:** lowercase quality does not improve, consistent with the deliberate uppercase eligibility boundary.
- **Observed:** `HTTP Server` and its question form still fail to locate the `HTTPServer` definition in the top five. Returned code can mention a symbol without being its definition. **Inference:** source-word occurrence and lexical/original-form preference are insufficient to resolve declaration identity; no internal candidate/branch trace was recorded.
- **Observed:** several 1,024-token misses become hits at 4,096 because the expected source was already ranked but the shared whole-block packer excluded it. This must not be diagnosed as a tokenizer failure or a native Book token-assembly regression.
- **Observed:** extra lookup costs are consistent across repetitions for the affected forms. **Inference:** supplemental SQL and source-word checking explain plausible work sources, but no profile isolates their shares.
- **Observed:** raw-code search wins aggregate hit rate and lookup cost in this pilot, while candidate Book wins the aggregate quality cells against the pinned Billion component. Every per-query loss against either control remains in the paired JSON.

## Decision and next iteration

A limited release may accurately claim improved recovery for certain acronym spellings on this fixed code-source pilot, unchanged exact-name success in the tested set, existing-index compatibility, and an explicitly larger lookup cost. It cannot claim improved AI answer completion speed, general multi-project engineering quality, temporal/branch resolution, or leading every competitor. The raw summary still has `release_approved=false`; publication and exact-commit CI/install gates remain the release owner’s decision.

The next investigation should distinguish declarations from mentions and measure the source of repeated parsing cost. Any change must use new preregistered confirmation data. This entire pilot is now regression/development material. A fixed-model task or patch evaluation is still required to measure answer correctness, valid repairs, context/tool retries, model tokens and elapsed task completion.

No changes were applied to runtime, evaluator, queries, original observations or acceptance thresholds while producing this analysis.
