# Explicit-conjunction coverage: development selection

This is a retrospective record of development experiments, written before the
subsequent frozen validation. It is not a preregistration, an independent test
result, or a generated-answer benchmark. The machine-readable
[selection record](conjunctive-selection.json) contains source and artifact
hashes, exact parameters, per-query gains/losses, and query-plan equivalence
checks.

## Candidate and scope

The existing whole-query OR ranking could fill the result slots with repeated
evidence about one requested subject. One candidate was tried: for explicit
conjunctions, preserve the original first result and reserve a result for each
clause before returning the remaining ranked pages. There was no weight sweep.

The heuristic recognizes `and`, `和`, `以及`, and `并且`, accepts two or three
clauses with at least two lexical terms each, and applies only to `book` with
more than one result slot. Explicit current/historical time requests keep the
existing guarded ordering. Each clause uses the existing normalized exact/stem
2:1 preference over the already scoped full-query candidate union. The union
has at most 96 candidates from each route. Source text and page IDs do not
change; citation, excerpt, scope, and budget checks still apply. Schema 3 is
unchanged; the recall-cache version advances to 8.

**This is bounded candidate reranking, not a bound on all retrieval work.**
The FTS query-plan repair described below can scan matches outside the supplied
project/chapter/session scopes before filtering to the already scoped integer
page IDs. Those outside matches cannot enter the results, but they can consume
query work.

The two-term threshold and conjunction list are syntax heuristics. They can
split a single concept incorrectly, and a later clause may lack a qualifier
shared with the first clause. A development inspection found that a later
clause could promote a different milestone's page within the same project.
The full-query candidate cutoff can also omit an essential page before this
reranking runs. There is no semantic model, synonym dictionary, or claim to
solve low-overlap paraphrase retrieval.

## Source identity and parameters

The baseline is `605d74e1b76fd471def8274c2a04e96e2d095075`.
Source hashes, rather than the dirty checkout's base commit, identify the
measured candidate bytes:

| Runtime | Python source SHA-256 |
| --- | --- |
| Baseline | `c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46` |
| Candidate before SQL-plan repair | `58880ac636bafb627f9b1700bc2de7fd1303ea5f98805df0995c69df5a51e925` |
| Selected candidate | `f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa` |

Both versions ran in separate Python processes with adaptive segmentation,
900-character page caps, top five results, result caching disabled, character
budgets of 2,000 and 8,000, and one repetition. The same existing whole-block
first-fit packer applied 512/1,024/2,048-token caps to the 8,000-character
response using `tiktoken==0.12.0`, `cl100k_base`, and `o200k_base`. The packer
and evidence labels did not select results for the retriever.

Only synthetic development seed 61 with eight projects and the pinned public
development subset of 128 questions informed selection. Previously observed
heldout queries and the newly prepared independent diagnostic were not used
to tune this candidate.

## Quality observed during development

Synthetic development has 168 questions, including 152 answerable questions
and 176 required evidence items. Both character budgets increase evidence
recall from **93.18% to 94.32%**. Every measured budget gains the same two
complete multi-section questions with no complete-query loss:

| Budget | Baseline complete evidence | Candidate complete evidence | Complete gains / losses |
| --- | ---: | ---: | ---: |
| 2,000 characters | 92.11% | 93.42% | +2 / −0 |
| 8,000 characters | 92.11% | 93.42% | +2 / −0 |
| `cl100k_base`, 512 tokens | 72.37% | 73.68% | +2 / −0 |
| `cl100k_base`, 1,024 tokens | 89.47% | 90.79% | +2 / −0 |
| `cl100k_base`, 2,048 tokens | 92.11% | 93.42% | +2 / −0 |
| `o200k_base`, 512 tokens | 75.00% | 76.32% | +2 / −0 |
| `o200k_base`, 1,024 tokens | 92.11% | 93.42% | +2 / −0 |
| `o200k_base`, 2,048 tokens | 92.11% | 93.42% | +2 / −0 |

The gained IDs are `willow-journal-indigo-multi-section` and
`solstice-journal-indigo-multi-section`. There are no per-query evidence losses
at any measured budget. The 512-token settings also recover some partial
evidence; the selection JSON retains those separate evidence gains.

The public development subset has 128 questions, 83 answerable. **Each
individual question retains the same matched-evidence count and complete
status at all eight configurations.** Two queries have changed result order,
without evidence gains or losses. Complete evidence remains 54.22% at 2,000
characters, 79.52% at 8,000 characters, 71.08% at both 512-token caps, and
79.52% at both larger token caps. These small development results justify a
frozen validation attempt; they do not establish generalization.

## Query-plan defect and equivalent repair

The first implementation constrained FTS using `rowid IN (...)`. On the
measured SQLite build, `EXPLAIN QUERY PLAN` reported
`VIRTUAL TABLE INDEX 0:=M4`: FTS repeated its MATCH work across the IN-list.
The synthetic run then had approximately 140 ms p95. That initial exploratory
run briefly overlapped correctness tests and is not a controlled timing
comparison; its source/output hashes are retained in the selection record.

Changing the constraint to `+rowid IN (...)` removed the rowid-equality-driven
plan while keeping the same bound integer IDs, ranking, filter, and limit.
The observed plan became `VIRTUAL TABLE INDEX 0:M4`. A two-project diagnostic
query returned exactly the same 96 `(rowid, rank)` pairs. Its two observations
were 13.960/13.447 ms before and 0.606/0.326 ms after; this is a query-planning
diagnostic, not a general latency guarantee.

The full synthetic development rerun verified that **all 168 query-result
rows at every one of the eight configurations are identical before and after
the SQL repair**. This includes result IDs and order, source references,
source spans, evidence scores, and character/token accounting. Canonical
query-row hashes are recorded for all eight comparisons.

The corrected sequential runs still show additional clause-query cost:

| Development workload | Character cap | Baseline p95 ms | Candidate p95 ms |
| --- | ---: | ---: | ---: |
| Synthetic seed 61 | 2,000 | 11.799 | 18.331 |
| Synthetic seed 61 | 8,000 | 9.450 | 11.087 |
| Public development 128 | 2,000 | 4.756 | 5.872 |
| Public development 128 | 8,000 | 3.941 | 4.713 |

These are single-repeat development observations with warm SQLite/OS caches.
They exclude tokenizer/packing, ingestion, MCP, networking, and model inference.
Repeated frozen validation must report the cost alongside quality; these
numbers do not support an overall speedup claim.

## Checks and artifacts

Four independent fixtures passed: English and Chinese multi-fact evidence
under repeated first-subject distractions, project/chapter/session scope,
intact source spans within a 600-character budget, and preservation of the
first result. The existing 68 core, recall-quality, score-fusion, migration,
and lexical-cache tests also passed. Source stability and character/token
budget checks passed in both development reports. Correctness checks alone
do not establish the product's final answer/cost goal.

| Cohort | Report | Summary | Per-query archive |
| --- | --- | --- | --- |
| Synthetic development 61 | [report](../results/conjunctive-dev-synthetic.md) | [summary](../results/conjunctive-dev-synthetic.summary.json) | [archive](../results/conjunctive-dev-synthetic.json.gz) |
| Public development 128 | [report](../results/conjunctive-dev-public.md) | [summary](../results/conjunctive-dev-public.summary.json) | [archive](../results/conjunctive-dev-public.json.gz) |

All six published artifact hashes and the initial slow version's output
hashes are recorded in [conjunctive-selection.json](conjunctive-selection.json).
The public corpus remains separately downloaded under its own license;
published public query rows contain source IDs and metrics without corpus
utterance text.
