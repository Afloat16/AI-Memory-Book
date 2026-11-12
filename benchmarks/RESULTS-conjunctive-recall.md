# Explicit-conjunction recall — frozen automatic-clause experiment

**Completed frozen experiment.** All eleven registered stages completed. The
[integrity record](reports/conjunctive-integrity.json) verifies all 29 declared
output hashes and all 68 frozen input hashes before the later opt-in API change.
This report includes favorable results, individual evidence losses, unchanged
transfer scores and measured cost regressions. The final default-preserving
interface is checked separately below; it does not replace the measured runtime.

The change addresses one concrete failure: an explicit question asking for two
or three facts could receive several pages about its first subject and miss a
later subject. A bounded reranking step preserves the original first result and
prioritizes clause-leading pages from the already scoped candidate union,
within the available result slots. It adds no model, embedding service or new
storage schema.

The completed synthetic regression runs show a useful but limited improvement.
At 8,000 characters, complete evidence rises from **84.21% to 89.47%** on each
of four previously observed seeds. Multi-section complete evidence rises from
**0/16 to 8/16** per seed. However, at a **512-token `o200k_base` cap**, overall
complete evidence falls from **73.68% to 71.05%** on each of those same seeds.
Low-overlap paraphrases remain unretrieved there. The new 36-question cross-domain
diagnostic has **86.67% complete evidence in both versions**, so it does not show
a transfer or semantic-retrieval gain.

On all 1,015 public regression questions, 8,000-character evidence recall rises
only **69.54% → 69.67%**, with complete evidence unchanged at **72.88%**. Repacking
the native excerpts at 512 tokens loses complete evidence under both tokenizers.
The actual public MCP response is 0.24 tokens smaller on average, while observed
first-call p95 grows from **9.564 to 13.510 ms**. That is not a general quality
and cost improvement.

**Adoption decision: keep the score-aware path as the default.** The frozen
candidate applies clause handling automatically, but its quality and tail-cost
tradeoffs do not justify promoting that behavior for every query. The final
interface exposes it as the explicit experimental `coverage` option. Independent
checks compare 2,774 complete recall payloads for each mode against its intended
frozen source, with zero differences after excluding only `latency_ms`. The
frozen results and original runtime are retained unchanged.

These are results for delivered original source evidence. Generated-answer
quality, total agent cost and universal superiority remain unestablished.

## 1. Runtime identities and selection

| Role | Identity | Meaning |
|---|---|---|
| Primary baseline | [`605d74e1b76fd471def8274c2a04e96e2d095075`](https://github.com/Afloat16/AI-Memory-Book/commit/605d74e1b76fd471def8274c2a04e96e2d095075) | Prior completed score-aware continuation; runtime bytes match its measured `0ab49d4` source |
| Earlier first-round baseline | [`6f5299004642618e606d001b4c574e1bae572a7e`](https://github.com/Afloat16/AI-Memory-Book/commit/6f5299004642618e606d001b4c574e1bae572a7e) | Separate historical comparison for the previously reported small-budget regression |
| Local runtime freeze | `1cdaf8f36436087b72eb8c9fbd17880cac356f21` | Selected conjunction runtime before the frozen validation |
| Published source snapshot | [`7a472ce35698360382d8d15a1be101343d8a2c3b`](https://github.com/Afloat16/AI-Memory-Book/commit/7a472ce35698360382d8d15a1be101343d8a2c3b) | GitHub API mirror of the local runtime freeze, with the same Git tree |

The local freeze and published snapshot share Git tree
`61ebe9c3995ec09da34606f404d29132b9f3e483`. Commit IDs differ because the snapshot
was published through a separate Git commit operation. Runtime identity is
checked against the actual Python source bytes:

| Runtime | Python source SHA-256 |
|---|---|
| Prior score-aware baseline | `c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46` |
| Conjunction candidate | `f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa` |
| Final product with explicit coverage mode | `88f5f749be55dd4f1094d236340bec645edb6b9306fd45c720dbebac91767e57` |

Later registration or documentation commits can appear in checkout provenance;
they are not new runtime measurements when the source hash is unchanged. The
package version string alone does not distinguish these v0.3 development states.

### What changed, and what did not

The frozen automatic-clause experiment recognizes explicit `and`, `和`, `以及` and `并且` conjunctions,
accepts two or three clauses containing at least two lexical terms each, and
applies only to book ranking with more than one result slot. Explicit
current/historical requests retain their existing guarded ordering. Each clause
uses the existing normalized exact/stem 2:1 score preference within the scoped
full-query candidate union. The original first result remains first; clause
leaders precede remaining ranked pages. Source text, page IDs, scope checks and
excerpt/source-span rules are retained. Schema 3 remains unchanged; the recall
cache version becomes 8.

The union is capped at 96 candidates per exact/stem route. **This bounds the
reranking candidates, not all retrieval work.** FTS may scan matches outside a
supplied scope before filtering to the scoped page IDs. Those matches cannot
enter the returned results, but can consume query work. The development SQL-plan
repair, its identical result rows, and the initially slow attempt are preserved
in the [development selection record](experiments/conjunctive-selection.md).

Only synthetic development seed 61 and the 128-question public development
subset informed selection. One reranking candidate was tried, without a weight
sweep. The selection record is retrospective, written before frozen validation;
it is not described as a preregistration. Development results gained two complete
synthetic questions at every measured budget and retained every public
development evidence/complete outcome. The same record also shows additional
clause-query latency. It does not claim that the change makes retrieval faster.

The syntax heuristic can split a single concept incorrectly, omit a qualifier
shared with a later clause, or fail because needed evidence never enters the
full-query candidate union. It is not semantic paraphrase retrieval.

## 2. Populations, budgets and measurement boundaries

The [registered validation plan](conjunctive_plan.json),
[corpus list](conjunctive_corpora.json) and [runner manifest](conjunctive_manifest.json)
define the frozen run.

| Population | Size | Exposure in this continuation |
|---|---|---|
| Synthetic development seed 61 | 168 questions, eight projects | Used for selection; development measurements are reported separately |
| Public development subset | 128 questions, two conversations | Used for selection; not new validation evidence |
| Synthetic seeds 211, 509, 883 and 1297 | 168 questions per seed; 152 answerable and 176 required evidence items | All were measured in the preceding continuation; regression populations sharing templates |
| Public LoCoMo verification | All 1,015 eligible text-only questions; 649 answerable | Previously measured regression population, including the earlier 256 and the additional 759 |
| Newly authored transfer diagnostic | 36 questions, six projects, 42 short fictional conversations; 30 answerable | Frozen before its first candidate scoring; not used for algorithm selection |

Each large synthetic seed contains 112 sessions, 1,408 user turns and about
1.143 million source characters. The new transfer set contains only 5,709 source
characters. It was separately authored by the same assistant team, outside the
existing long-session template generator. It is not a random sample of real
users or independent human annotation. Its [manifest](transfer_manifest.json)
states that all 36 cases are retained and future use is regression use.

**Evidence recall** counts required original source text delivered intact with
matching source spans. **Complete evidence** requires all annotated evidence
for an answerable question. Unsupported questions returning nonempty context
are reported separately; that diagnostic is not a generated-answer hallucination
or abstention score.

Paired runs use independent Python processes, the same canonical history and
scope, adaptive segmentation with 900-character page caps, top-five results,
2,000/8,000-character context caps and three shuffled repetitions. Result caching
is disabled; SQLite and operating-system caches are not flushed. Core timings
exclude ingestion, token counting/packing, MCP, networking and model inference.
The recorded runtime is Python 3.12.14 and SQLite 3.53.1 on Linux x86-64.

Token curves apply the same rank-order whole-block packer to the 8,000-character
response, with `tiktoken==0.12.0`, both `cl100k_base` and `o200k_base`, and caps of
512/1,024/2,048. These are reference-token measurements, not a production native
token-budget API or provider-billed token totals. The native-component comparison
uses a separate full-page assembly policy and must not be conflated with paired
native excerpts.

## 3. Synthetic regression quality and small-budget losses

The following quality values are identical on **each** of seeds 211, 509, 883
and 1297. They are shown once for readability, not averaged across populations.
Every arrow compares the prior score-aware baseline with the frozen conjunction
candidate.

| Delivery budget | Evidence recall | Complete evidence |
|---|---:|---:|
| 2,000 characters | 79.55% → 87.50% | 81.58% → 86.84% |
| 8,000 characters | 81.82% → 89.77% | 84.21% → 89.47% |
| `cl100k_base`, 512 tokens | 68.18% → 71.59% | 68.42% → 68.42% |
| `cl100k_base`, 1,024 tokens | 81.82% → 89.77% | 84.21% → 89.47% |
| `cl100k_base`, 2,048 tokens | 81.82% → 89.77% | 84.21% → 89.47% |
| `o200k_base`, 512 tokens | 72.73% → 73.86% | **73.68% → 71.05%** |
| `o200k_base`, 1,024 tokens | 81.82% → 89.77% | 84.21% → 89.47% |
| `o200k_base`, 2,048 tokens | 81.82% → 89.77% | 84.21% → 89.47% |

At 8,000 characters, each seed delivers 158/176 evidence items versus 144/176,
and completes 136/152 answerable questions versus 128/152. Multi-section coverage
rises from 8/32 to 22/32 required items (**25% → 68.75%**) and from 0/16 to 8/16
complete questions. The 24 lookup questions remain complete. All eight
low-overlap paraphrase questions still have zero recall.

The [per-query assessment](results/conjunctive-analysis.json) checks annotation
positions and complete-question transitions, not just aggregate differences.
On each seed, both character caps and all 1,024/2,048-token settings gain 14
previously absent annotations, lose none, and gain eight complete questions
without losing any. At 512 `cl100k_base` tokens there are six annotation gains,
no annotation losses and no complete-question gains or losses. At 512
`o200k_base` tokens there are six annotation gains, **four annotation losses and
four lost complete questions**, with no newly complete question. The larger-budget
result therefore does not establish a solution to the small-budget objective.

### Context size and observed core latency

Mean context tokens below use `o200k_base`; quality has its own table above.
All latency values retain the same in-process, uncached-result boundary.

| Seed | Character cap | Mean context tokens, baseline → candidate | Core p50 ms, baseline → candidate | Core p95 ms, baseline → candidate |
|---|---:|---:|---:|---:|
| 211 | 2,000 | 770.5 → 770.8 | 4.715 → 5.370 | 13.484 → 16.186 |
| 211 | 8,000 | 1,219.7 → 1,220.9 | 3.499 → 4.313 | 8.683 → 11.545 |
| 509 | 2,000 | 773.1 → 773.6 | 4.647 → 5.311 | 13.434 → 15.402 |
| 509 | 8,000 | 1,224.0 → 1,225.4 | 6.239 → 4.237 | 17.277 → 11.150 |
| 883 | 2,000 | 774.9 → 775.3 | 5.244 → 5.251 | 15.684 → 15.149 |
| 883 | 8,000 | 1,229.5 → 1,230.8 | 4.671 → 3.872 | 11.670 → 10.260 |
| 1297 | 2,000 | 770.1 → 770.4 | 5.132 → 4.954 | 15.242 → 14.306 |
| 1297 | 8,000 | 1,218.2 → 1,219.3 | 3.923 → 4.025 | 10.233 → 10.868 |

The timings vary in both directions, including slower candidate p95 on seed 211
and an unusually high baseline observation on seed 509 at 8,000 characters.
These single-machine observations do not isolate algorithmic causality or show
uniform speed. Extra clause queries add work. The complete timing distributions
remain in the artifacts; no favorable-seed average replaces the table.

All 16 unsupported questions in each synthetic regression seed return nonempty
context in both versions. Retrieval does not itself establish whether an
answering model would decline to answer them.

## 4. New cross-domain diagnostic: no measured transfer gain

The small authored diagnostic retains the same aggregate evidence and complete
rates in both versions at both character caps and all six token settings:

| Diagnostic | Baseline | Candidate |
|---|---:|---:|
| Required evidence delivered | 32/36 (88.89%) | 32/36 (88.89%) |
| Answerable questions with complete evidence | 26/30 (86.67%) | 26/30 (86.67%) |
| Low-overlap paraphrase questions complete | 2/6 | 2/6 |
| Multi-section questions complete | 6/6 | 6/6 |
| Lookup/current-decision/scoped-lookup questions complete | 18/18 | 18/18 |
| Unsupported questions with nonempty context | 2/6 | 2/6 |
| Mean context tokens, `cl100k_base` | 188.5 | 188.5 |
| Mean context tokens, `o200k_base` | 172.9 | 172.9 |

The existing baseline already completes all six of the short multi-section
cases. Four of six paraphrases fail in both versions. The new diagnostic thus
adds a corpus outside the old templates but provides **no evidence of an
incremental semantic or cross-domain quality gain**. Its small size, short
histories and common author team limit generalization claims. It becomes
regression data after this evaluation.

The per-query assessment confirms zero annotation or complete-question
transitions at all eight settings. Equal aggregate scores here do not conceal
offsetting quality gains and losses.

At 8,000 characters, observed p50 is 0.675 → 0.614 ms and p95 is
1.479 → 1.693 ms; preparation and model inference are excluded. These small
timings are not an end-to-end cost comparison. See the [transfer report](results/conjunctive-transfer.md)
and [full summary](results/conjunctive-transfer.summary.json).

## 5. Public regression and first-round comparison

All 1,015 eligible public questions are retained, including 649 answerable and
366 unsupported questions. Required source annotations total 788. Every question
was already measured in the prior continuation, so this is regression evidence.

### Native excerpts under character caps

Every arrow in this table starts from the **prior score-aware baseline**.
Mean context tokens use `o200k_base` across all selected queries.

| Character cap | Evidence recall | Complete evidence | Mean context tokens | Core p50 ms | Core p95 ms |
|---|---:|---:|---:|---:|---:|
| 2,000 | 47.59% → 47.72% | 50.23% → 50.23% | 594.9 → 594.9 | 3.636 → 3.816 | 5.658 → 6.535 |
| 8,000 | 69.54% → 69.67% | 72.88% → 72.88% | 845.0 → 844.7 | 3.160 → 3.074 | 4.889 → 5.545 |

The aggregate gain is one required annotation at each cap: 375 → 376 at 2,000
characters and 548 → 549 at 8,000. Complete counts remain 326/649 and 473/649,
respectively. Per-query comparison confirms one annotation gained, none lost,
and no complete-question gains or losses at either character cap.

### Small-token native-excerpt curves

These curves pack the actual 8,000-character native excerpt response. **They
are not the full-page native-component policy used for the earlier 66.72% →
66.26% `cl100k_base` result.** Each table must keep its own assembly policy and
baseline. Native-component results are reported separately in the next section.

| Tokenizer / cap | First-round complete | Prior score-aware complete | Automatic-clause complete | Recall, score-aware → automatic | Mean tokens, score-aware → automatic |
|---|---:|---:|---:|---:|---:|
| `cl100k_base` / 512 | 65.95% | 65.33% | **64.87%** | 61.17% → 60.91% | 444.5 → 444.6 |
| `cl100k_base` / 1,024 | 71.96% | 72.88% | 72.88% | 69.54% → 69.67% | 855.5 → 855.3 |
| `cl100k_base` / 2,048 | 71.96% | 72.88% | 72.88% | 69.54% → 69.67% | 867.1 → 866.8 |
| `o200k_base` / 512 | 66.41% | 65.95% | **65.49%** | 62.06% → 61.80% | 446.6 → 447.0 |
| `o200k_base` / 1,024 | 71.96% | 72.88% | 72.88% | 69.54% → 69.67% | 839.3 → 839.1 |
| `o200k_base` / 2,048 | 71.96% | 72.88% | 72.88% | 69.54% → 69.67% | 845.0 → 844.7 |

At 512 tokens the automatic experiment gains one annotation but loses three,
and loses three complete questions without gaining any, relative to the prior
score-aware baseline under either tokenizer. At 1,024 and 2,048 tokens it gains
one annotation with no annotation losses and no complete-question transitions.
Relative to the first round, the 512-token complete transitions are nine gains
and 16 losses with `cl100k_base`, and nine gains and 15 losses with `o200k_base`.
Atomic recall also declines versus the immediate baseline at these caps.
Larger-cap complete scores do not offset or conceal this failure of the
small-budget objective.

### Public category results at 8,000 characters

| Upstream category | Answerable questions | Evidence recall, prior → automatic | Complete evidence, prior → automatic |
|---|---:|---:|---:|
| Category 1 | 65 | 38.85% → 39.49% | 20.00% → 20.00% |
| Category 2 | 126 | 72.46% → 72.46% | 76.19% → 76.19% |
| Category 3 | 24 | 42.11% → 42.11% | 33.33% → 33.33% |
| Category 4 | 434 | 81.54% → 81.54% | 82.03% → 82.03% |

Category 1 gains the one annotation, while its complete rate remains low.
All 366 unsupported questions return nonempty context in both versions. This
experiment does not measure whether a model would use that context appropriately.

The separately rerun **first-round → automatic** comparison has 2,000-character
recall 46.83% → 47.72% and complete evidence 49.46% → 50.23%; at 8,000 characters
the rates are 68.78% → 69.67% and 71.96% → 72.88%. Most of those historical gains
already belonged to score-aware fusion. They are not attributed to this clause
change. At 8,000 characters the first-round comparison contains 13 annotation
gains and six losses, and eight complete-question gains and two losses; even
its positive aggregate score retains individual regressions. See
[the primary public report](results/conjunctive-public.md) and
[the historical-baseline report](results/conjunctive-public-vs-first.md).

## 6. Native retrieval components and actual MCP costs

### Actual Book MCP responses

The official SDK launches real stdio subprocesses and calls `recall_memory`.
Each workload has three repetitions. The synthetic workload is seed 61 with two
projects and **42 questions** at 2,000 characters; it is distinct from the
eight-project core regressions. Public MCP retains all **1,015 query IDs** at
8,000 characters. Response-text tokens count actual tool JSON and metadata with
`o200k_base`, not the host's private wrapper or provider billing.

| Workload | Runtime | Mean response tokens | First-call p50 ms | First-call p95 ms |
|---|---|---:|---:|---:|
| Synthetic 42 | Prior score-aware | 1,176.81 | 5.285 | 11.134 |
| Synthetic 42 | Automatic-clause | 1,176.38 | 5.109 | 11.237 |
| Public 1,015 | Prior score-aware | 1,465.07 | 5.757 | 9.564 |
| Public 1,015 | Automatic-clause | 1,464.83 | 6.536 | 13.510 |

The public response-token change is less than **0.02%**, while observed p50
increases about **13.5%** and p95 about **41.3%**. The synthetic p50 falls but p95
rises slightly. These observations do not support adopting the automatic
experiment for lower general retrieval cost.

First calls have no prior query-result entries, while OS/SQLite caches remain
warm. Public input contains 1,010 distinct query/project pairs; all 1,015 IDs
are retained and each engine records 15 separate cache clears for the repeated
pairs across three repetitions. Immediate hot repeats and startup are reported
separately. The measured environment uses MCP 1.30.0 and tiktoken 0.12.0.

Both versions verify compact/detailed context equality for all 1,057 questions
across these workloads. Startup has only three process samples per version and
workload, so it is not promoted to a general guarantee. The public first-call
maxima are 417.3 and 450.4 ms; distributions and immediate repeats remain in the
[public summary](reports/conjunctive-mcp-public.summary.json) and
[synthetic summary](reports/conjunctive-mcp-synthetic.summary.json).

The MCP harness fingerprints paths relative to the checkout, while the paired
core harness fingerprints paths relative to `src/memory_book`. Consequently
their SHA-256 strings differ even for identical source bytes; final integrity
checks must use each harness's defined scheme.

### Native components under common full-page assembly

This completed stage runs the actual pinned Billion `searchBlocks` kernel and
the official ai-memory hybrid binary alongside both Book runtimes. Every
component receives the same **1,339 original pages across eight projects**, the
same queries, scope and top-five limit. The exported-page SHA-256 is
`54aa61fd41b7b4058d07fd018bb6d99c6d34a7d73134fb567b67c56536df972a`, matching
the prior score-aware native-component evaluation. Billion is pinned to
`dc041dd1ab1a014efa352ba47a6f31fc47f55284`; ai-memory v3.4.5 is pinned to
`ee73c04c542fa41ca629b046deb4ac108518f407` with its local MiniLM embeddings ready.
No answer labels enter a backend.

For the following tables, the harness expands each selected page ID to its
**complete original page**, adds the same citation and uses the same whole-block
token packer. The values therefore describe common assembly after each native
retriever, not native previews or complete products. Book retains its hierarchy
and FTS fields; the external components index exported titles, bodies and project
scope. Identical page granularity does not imply identical indexed features.

#### `cl100k_base` full-page curves

| Token cap | Retriever | Evidence recall | Complete evidence | Mean context tokens |
|---|---|---:|---:|---:|
| 512 | Prior score-aware Book | 62.44% | 66.26% | 447.6 |
| 512 | Automatic-clause Book | 62.18% | **65.79%** | 447.4 |
| 512 | Billion native kernel | 58.88% | 62.71% | 442.8 |
| 512 | ai-memory native hybrid | 56.60% | 58.86% | 451.1 |
| 1,024 | Prior score-aware Book | 69.54% | 72.88% | 827.2 |
| 1,024 | Automatic-clause Book | 69.67% | 72.88% | 826.9 |
| 1,024 | Billion native kernel | 65.48% | 68.72% | 862.6 |
| 1,024 | ai-memory native hybrid | 64.47% | 66.72% | 779.3 |
| 2,048 | Prior score-aware Book | 69.54% | 72.88% | 832.1 |
| 2,048 | Automatic-clause Book | 69.67% | 72.88% | 831.8 |
| 2,048 | Billion native kernel | 65.48% | 68.72% | 871.0 |
| 2,048 | ai-memory native hybrid | 64.59% | 66.87% | 782.4 |

#### `o200k_base` full-page curves

| Token cap | Retriever | Evidence recall | Complete evidence | Mean context tokens |
|---|---|---:|---:|---:|
| 512 | Prior score-aware Book | 62.94% | 66.72% | 451.5 |
| 512 | Automatic-clause Book | 62.69% | **66.26%** | 450.9 |
| 512 | Billion native kernel | 59.39% | 63.02% | 445.8 |
| 512 | ai-memory native hybrid | 56.98% | 59.17% | 451.8 |
| 1,024 | Prior score-aware Book | 69.54% | 72.88% | 809.2 |
| 1,024 | Automatic-clause Book | 69.67% | 72.88% | 808.9 |
| 1,024 | Billion native kernel | 65.48% | 68.72% | 844.6 |
| 1,024 | ai-memory native hybrid | 64.47% | 66.72% | 760.4 |
| 2,048 | Prior score-aware Book | 69.54% | 72.88% | 810.0 |
| 2,048 | Automatic-clause Book | 69.67% | 72.88% | 809.8 |
| 2,048 | Billion native kernel | 65.48% | 68.72% | 848.5 |
| 2,048 | ai-memory native hybrid | 64.59% | 66.87% | 762.4 |

Each Book variant exceeds both components on evidence recall and complete
evidence in **12/12** comparisons: two tokenizers × three caps × two competing
components. Each uses fewer mean context tokens in **6/12**, so this is not
universal token superiority. At 1,024 `cl100k_base` tokens, the preserved default
leads complete evidence by **4.16 percentage points** over Billion and **6.16
points** over ai-memory. Its mean context is **4.1% smaller than Billion's**;
ai-memory's context is smaller still, with a lower complete-evidence rate.

Against the prior score-aware version, automatic clauses add one annotation
at 1,024/2,048 tokens without changing any complete-question outcome. At 512
tokens under either tokenizer, they gain one annotation, lose three, and lose
three complete questions without gaining any. All transition IDs are retained
in the [per-query assessment](results/conjunctive-analysis.json).

#### The originally reported 512-token gap is still open

This is the same **common full-page** policy as the user's earlier
66.72% → 66.26% observation. Keeping its baseline and assembly policy explicit:

| Tokenizer / cap | Historical first round | Prior score-aware, rerun here | Frozen automatic clauses |
|---|---:|---:|---:|
| `cl100k_base` / 512, complete evidence | 66.72% | 66.26% | 65.79% |
| `o200k_base` / 512, complete evidence | 67.03% | 66.72% | 66.26% |

The first-round values come from the preserved
[prior native-component summary](results/recall-final-components-public.summary.json),
whose exported-page hash matches this run. They are not a fresh first-round
timing measurement. Leaving coverage off avoids this experiment's additional
three-question loss; it does **not** repair the original score-aware
small-budget deficit. The separate native-excerpt curves in section 5 have
different values because their delivered blocks differ.

### Native latency and response costs: retain the boundary

| Operation | Observed p50 ms | Observed p95 ms | Measured boundary |
|---|---:|---:|---|
| Prior score-aware Book | 2.938 | 4.674 | In-process recall, including its context assembly |
| Automatic-clause Book | 2.929 | 4.736 | Same in-process boundary |
| Billion `searchBlocks` | 0.986 | 1.774 | Kernel only |
| Billion bridge | 1.173 | 2.067 | Kernel plus JSON IPC roundtrip |
| ai-memory hybrid search | 32.233 | 48.692 | Persistent loopback HTTP/MCP query roundtrip |
| Automatic-clause Book MCP | 6.536 | 13.510 | Separate real stdio workload from the table above |

Billion is faster on this measured retrieval kernel. Transport, native context
assembly and setup differ, so these rows are not interchangeable product-speed
measurements. In particular, comparing Book's in-process row with a competitor's
HTTP row does not establish an end-to-end speed multiplier.

The fixed ai-memory native-cost policy performs **one search plus full reads of
every mapped top-five page**. Its mean `o200k_base` content cost is **878.9 search
tokens + 1,700.4 full-read tokens = 2,579.4 tokens**; the separately measured
Book automatic MCP response averages **1,464.8**, or **43.2% fewer under those
explicit policies**. This is not an equal-cap native comparison or ai-memory's
minimum necessary read cost. A preview-only or selective-read consumer may spend
less. Canonical full JSON payload counts are also recorded separately and must
not be substituted for this content-token denominator. Actual ai-memory full
reads are checked against the shared page text and add an observed 6.6 ms mean
per query across the mapped reads.

Billion's native search previews average 569.2 tokens; expanding its selected
IDs to original pages is a harness-side lookup, not a measured native fetch or
decompression API. None of these response totals includes model inference,
provider chat wrappers, capture, summarization, tool definitions or initialization.

Setup also remains separate: the frozen Book corpus ingestion takes 1,009.2 ms;
the Billion document-list bridge setup takes 303.8 ms; ai-memory setup takes
157,881.0 ms, including 155,637.0 ms of page ingestion. ai-memory uses cached
model assets with no download in the run, and its embedding backfill reports
1,339 already-ready pages and zero failures. These operations are different and
do not establish a cross-product write-cost ratio. Full methodology, provenance
and native cost fields are in the [component report](results/conjunctive-components-public.md)
and [summary](results/conjunctive-components-public.summary.json).

## 7. Correctness, answer-evaluation readiness and remaining objectives

All eleven registered stages completed, with **29/29 declared output hashes**
and **68/68 frozen input hashes** verified before the final mode change. The
preflight retains ten corpus checks with zero unattainable evidence labels.
The stage summaries pass their source-stability, character/token-budget and
context-size consistency checks. The post-run per-query assessment additionally
checks the uncompressed report hash for all eight quality archives before
comparing required annotation positions and complete-question outcomes.

The final opt-in build passes **266 local tests**, with no failures or skips.
Its independent mode-equivalence checks are recorded in section 8. The
[current PR checks](https://github.com/Afloat16/AI-Memory-Book/pull/1/checks)
track CI for the published branch head; earlier CI remains historical validation.
See [the execution checkpoint](reports/conjunctive-checkpoint.json),
[integrity record](reports/conjunctive-integrity.json) and
[validation details](../docs/validation.md). Correctness gates do not establish
quality superiority.

A separate [real-endpoint answer runner](../docs/answer-evaluation.md) prepares
fixed contexts for paired Book versions, excludes answer labels from the index
and model inputs, and records provider usage independently from reference-token
counts. It preserves failed attempts, unknown costs, reported model identity
and explicit lack of full-workflow coverage. Its HTTP fixtures establish
transport behavior only.

The [answer-readiness record](reports/answer-eval-readiness.json) verifies
prepared contexts for **128 previously observed public development questions**:
83 answerable and 45 unsupported. It pairs the first-round runtime with the final
default, at 8,000 characters followed by a 1,024-token `cl100k_base` cap. Its
private prepared package retains the licensed source/answer material outside
git; the public record publishes hashes and counts only. Both retrieval sources
remain stable during preparation. **Actual model calls: zero.** No real endpoint
and served model were configured, so generated-answer scores, provider usage
and full-workflow cost are explicitly unmeasured, not zero. Authentic competitor
observer/compression traces are also absent. The runner and prepared inputs
close an execution-preparation gap, not the answer-quality or total-cost gap.

| Original objective | What this continuation establishes | Still unresolved |
|---|---|---|
| Combine evidence across sections | Eight additional complete multi-section questions per large synthetic seed | Half remain incomplete; short transfer cases show no gain; low-overlap paraphrase retrieval is not solved |
| Improve extremely small budgets | Atomic recall rises on synthetic 512-token settings; default behavior is preserved | Complete evidence falls with synthetic `o200k_base` and both public tokenizers under native-excerpt and common-full-page policies; the original 512-token gap remains |
| Validate generated answers and total cost | A runnable real-endpoint protocol, prepared 128-question paired inputs, explicit cost/identity accounting | Actual paired model experiment and authentic full competitor workflows |
| Check generalization beyond reused templates | A frozen 36-question authored diagnostic outside the original generator | No quality gain on it; insufficient breadth or independent annotation for generalization claims |

### Next priorities supported by the measurements

The next small-budget experiment should test native token-aware sentence/span
assembly while retaining exact original text, source spans, citations and the
strict cap. A [read-only development diagnosis](experiments/small-budget-diagnosis.json)
compares the existing baseline's 8,000-character output with its 512-token
whole-block packed view. Among answerable queries, mean unused tokens are
149.2/147.8 on synthetic seed 61 and 80.5/72.6 on public development, for
`cl100k_base`/`o200k_base` respectively. Sixteen of 152 synthetic answerable
queries go from nonempty to empty under either encoding; seven of 83 public
development questions lose complete evidence under either encoding. This
identifies a concrete packing limitation worth testing. It does not prove that
a new assembler succeeds or explain the causal source of this experiment's
three public losses.

Low-overlap retrieval needs a separately frozen candidate and corpus broad
enough to challenge lexical heuristics; repeatedly reusing the current cases
would only add regression evidence. The available answer runner should then
measure the effect on actual answers, reported usage and failures with a real
served model. Full-workflow comparisons additionally require authentic native
capture/observation and summary records from the competing products. These
remain future experiments with explicit acceptance criteria, not benefits
claimed by this release.

## 8. Product decision: explicit coverage mode

The experiment can recover missing clauses, but it can also displace useful
evidence under very small token budgets and adds clause-query work. Those
tradeoffs are kept in the result. **The final product retains the prior
score-aware behavior by default and exposes this experiment only when requested:**

| Interface | Default | Explicit experiment |
|---|---|---|
| Python `MemoryBook.recall` | `coverage=False` | `coverage=True` |
| MCP `recall_memory` | `coverage: false` or omitted | `coverage: true` |
| CLI `memory-book recall` | No coverage flag | `--coverage` |

The final interface uses recall-cache version 9 and includes the coverage flag
in the cache key. Entries from the frozen automatic version 8 are not reused.

This is an opt-in product decision made after inspecting the frozen validation,
not a new claim that the measured candidate was the default version users
already installed. No old output or checkpoint is rewritten to imply otherwise.

The [independent equivalence record](reports/coverage-mode-equivalence.json)
compares complete recall payload hashes in separate processes, excluding only
the nondeterministic `latency_ms` field:

| Final mode | Frozen reference | Complete payloads compared | Differences |
|---|---|---:|---:|
| Default, `coverage=False` | Prior score-aware `605d74e` source | 2,774 | 0 |
| Explicit `coverage=True` | Automatic-clause `1cdaf8f` / published `7a472ce` source | 2,774 | 0 |

Each comparison covers 1,387 query IDs at both 2,000- and 8,000-character caps:
synthetic development seed 61 (168), synthetic regression seed 211 (168), all
1,015 public regression questions and the 36-question transfer diagnostic.
Every worker retains an unchanged source hash before and after execution.
This checks full returned evidence, context, ordering and accounting on these
cohorts, not only equal summary scores. It does not prove identity for every
possible input. The option requires book ranking; combining it with flat
ranking is rejected.

Timing results for the frozen automatic experiment are not measurements of the
subsequently wired opt-in build, even though its returned payloads match on the
checked cohorts. The final build has its own source hash in section 1. Historical
artifacts and execution checkpoints remain attached to the automatic runtime
that actually produced them.

## 9. Reproduction and artifact index

Use this continuation's registered manifest and evaluator files, together with
the frozen automatic-clause runtime bytes. The final product defaults to
`coverage=False`, so running its default source directly would not reproduce
this automatic experiment. From the final publication checkout, create a
separate replay worktree and restore only the frozen runtime:

```bash
git worktree add --detach ../conjunctive-reproduction HEAD
git -C ../conjunctive-reproduction restore --source 7a472ce35698360382d8d15a1be101343d8a2c3b -- src
cd ../conjunctive-reproduction
```

Keep the publication's manifest and evaluator files in that replay checkout.
The restored source is intentionally different from the final product commit;
its Python source hash must equal `f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa`.
The harness records that source difference instead of attributing the bytes to
the final product commit. Create the adjacent baseline worktrees if they are
not already present with the correct source:

```bash
git worktree add --detach ../baseline-score 605d74e1b76fd471def8274c2a04e96e2d095075
git worktree add --detach ../baseline-recall 6f5299004642618e606d001b4c574e1bae572a7e
```

For the automatic-clause candidate use the reachable published source snapshot
`7a472ce35698360382d8d15a1be101343d8a2c3b`. The plan's local IDs `1cdaf8f` (runtime)
and `917bf88` (diagnostic freeze) are provenance records; reproduction does not
assume those local commits are available from GitHub. The source snapshot
contains the frozen runtime and diagnostic content; the final publication
supplies the registered manifest/evaluator files. The runtime tree/hash mapping
in section 1 and the diagnostic file hash in its manifest identify their bytes.

Prepare `.[mcp,clients,benchmark]`, the pinned LoCoMo corpus, Node and verified
competitor/tokenizer caches before running. Set `TIKTOKEN_CACHE_DIR` to the
prepared cache; the native-component stage is offline. The [benchmark guide](README.md)
and [competitor adapter guide](competitors/README.md) describe required assets
and version pins. The raw LoCoMo corpus is not redistributed with the package.

```bash
python -m benchmarks.resume \
  --manifest benchmarks/conjunctive_manifest.json \
  --checkpoint .artifacts/conjunctive-reproduction.json
```

Re-run the same command to resume only source/runtime/output-consistent stages.
A different machine needs a new checkpoint. Preserve any failed record and
record a corrected continuation explicitly if a stage cannot be resumed; do
not turn an incomplete checkpoint into a completed one by editing its status.

| Measurement | Human-readable report | Aggregate/category summary | Complete per-query archive |
|---|---|---|---|
| Synthetic regression 211 | [report](results/conjunctive-synthetic-211.md) | [summary](results/conjunctive-synthetic-211.summary.json) | [archive](results/conjunctive-synthetic-211.json.gz) |
| Synthetic regression 509 | [report](results/conjunctive-synthetic-509.md) | [summary](results/conjunctive-synthetic-509.summary.json) | [archive](results/conjunctive-synthetic-509.json.gz) |
| Synthetic regression 883 | [report](results/conjunctive-synthetic-883.md) | [summary](results/conjunctive-synthetic-883.summary.json) | [archive](results/conjunctive-synthetic-883.json.gz) |
| Synthetic regression 1297 | [report](results/conjunctive-synthetic-1297.md) | [summary](results/conjunctive-synthetic-1297.summary.json) | [archive](results/conjunctive-synthetic-1297.json.gz) |
| Authored transfer diagnostic | [report](results/conjunctive-transfer.md) | [summary](results/conjunctive-transfer.summary.json) | [archive](results/conjunctive-transfer.json.gz) |
| Public vs prior score-aware | [report](results/conjunctive-public.md) | [summary](results/conjunctive-public.summary.json) | [archive](results/conjunctive-public.json.gz) |
| Public vs first round | [report](results/conjunctive-public-vs-first.md) | [summary](results/conjunctive-public-vs-first.summary.json) | [archive](results/conjunctive-public-vs-first.json.gz) |
| Shared-page native components | [report](results/conjunctive-components-public.md) | [summary](results/conjunctive-components-public.summary.json) | [archive](results/conjunctive-components-public.json.gz) |

The actual MCP archives are [public](reports/conjunctive-mcp-public.json.gz) and
[synthetic](reports/conjunctive-mcp-synthetic.json.gz), with corresponding
[public](reports/conjunctive-mcp-public.summary.json) and
[synthetic](reports/conjunctive-mcp-synthetic.summary.json) summaries. Supporting
audit records are:

- [Preflight checks](results/conjunctive-preflight.json),
  [completed execution checkpoint](reports/conjunctive-checkpoint.json) and
  [verified integrity record](reports/conjunctive-integrity.json).
- [Per-query gains/losses and archive hash checks](results/conjunctive-analysis.json),
  retaining query IDs and annotation positions without source text or answers.
- [Final default/coverage payload equivalence](reports/coverage-mode-equivalence.json)
  and [real-answer preparation status](reports/answer-eval-readiness.json).
- [Development-only small-budget diagnosis](experiments/small-budget-diagnosis.json),
  a post-run reading of existing artifacts, not a new retrieval measurement.

The [prior score-aware report](RESULTS-recall-score-quality.md) and
[first frozen round](RESULTS-recall-quality.md) remain separate historical
evidence; their numbers have not been overwritten by this continuation.
