# Native budget evaluation protocol

The [registered plan](../benchmarks/native_budget_plan.json) separates three delivery policies: historical full-page packing, the existing native excerpts followed by token packing, and the new native token-budget API. The first two are different baselines. A score from one must not be presented as the other.

## Completed frozen matrix — 2026-11-12

All eight registered cohorts now have completed, published reports: **2,019
query instances and 24,228 query/configuration pairs**. The frozen candidate
`407cda1c5f1dac0e67dfe527d3c23febdad5e818` retains the source hash
`63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625`.
There are **251 complete-question configuration gains, zero complete-question
losses, 258 annotated-evidence gains, zero annotation losses, and zero losses
of previously fitting baseline blocks**. Repeated configurations are counted
separately; these totals are not numbers of distinct questions.

At 8,000 characters / 512 cl100k_base tokens, public complete evidence improves
65.33% to 66.41% (7 gains / 0 losses), while p95 rises from 7.120 to 10.076 ms.
External HotpotQA improves 34.38% to 35.16%, with p95 7.873 to 9.188 ms.
The historical whole-page 66.72% to 66.26% regression remains a separate result.

See the [public report](../benchmarks/results/native-completion-regression-public1015.md),
[external report](../benchmarks/results/native-completion-external-hotpot128.md)
and [complete result index](../benchmarks/README.md). Three older completed
cohorts retain their original checkpoints; five newly completed cohorts each
have a hosted checkpoint and publication hashes. Hosts differ across cohorts;
only the paired measurements within one cohort share a timing environment.
Final aggregation rechecks the full raw/summary/checkpoint matrix without
rerunning retrieval.

## Freeze and resume

1. Save this plan before examining candidate results. Development is synthetic seed 61 (168 questions) and the existing hash-selected LoCoMo development subset (exactly 128 questions).
2. Develop only on those cohorts. Preserve any failed or superseded run with its actual question count and measured source hash.
3. Commit the selected candidate, record the Git SHA and source SHA-256, and freeze an explicit sequential runner manifest covering source, evaluator, data and runtime inputs.
4. Run all four synthetic regression seeds, all 1,015 eligible public regression questions, the old 36-question diagnostic, and the separately frozen external transfer set. Expected-count mismatches stop execution before retrieval.
5. Keep every result, including low-overlap, multi-section, tiny-budget and tail-latency losses. A rerun after tuning is regression evidence.

`python -m benchmarks.resume --help` describes the existing atomic, locked checkpoint runner. It rejects changed source/data/commands/runtime, rechecks completed output hashes, and never marks failed validation as completed. Checkpoints and compact result summaries should be committed at each completed stage. Raw upstream data and answer-preparation packages stay outside Git under `.artifacts/` and are reproducible from pinned source manifests.

## Quality and cost boundaries

- Enforce both character and exact named-tokenizer caps on returned `context`, including citations and separators. Count outer MCP metadata separately.
- Compare every baseline native block already fitting the same caps with the candidate. Report required-annotation and complete-question gains and losses separately.
- Preserve source coordinates. Evidence labels enter only the evaluator; do not use them for ranking, extraction or packing.
- Core timing excludes ingestion and external scoring; record those separately. Actual MCP startup, first-call and immediate-repeat measurements use the real stdio boundary.
- Source evidence completeness is not generated-answer correctness. The existing paired-answer runner needs an actual named endpoint/model. Preparation and HTTP fixture tests do not constitute a generation run.
- A complete workflow comparison needs authentic ingestion/observation/summary traces for each product. Missing phases are unknown, not free. A Book-only or retrieval-only result cannot establish universal full-product superiority.

## External transfer

The new transfer cohort uses the externally authored [HotpotQA dev distractor dataset](https://github.com/hotpotqa/hotpot), licensed CC BY-SA 4.0. The fixed selection rule is independent of questions, answers and outcomes: sort original IDs by `SHA256('memory-book-transfer-v1:' + id)` and retain 128. Freeze source hashes and selected IDs before running the candidate. Index all supplied paragraphs under separate task chapters, scoped to the original problem; keep the question and labels out of the index.

This test probes cross-article evidence assembly on an outside question set. It does not represent a full archive, independently collected user conversations or a universal semantic-memory test. The old 36-question authored fixture remains separately labeled as regression. If external data is unavailable, record the block rather than relabeling synthetic data as independent evidence.

The original CMU HTTP and HTTPS data endpoints returned 503 during preparation. The pinned HuggingFace conversion in [the source manifest](../benchmarks/hotpot_manifest.json) supplies the same named dev distractor cohort; its Parquet bytes and deterministic JSON conversion are hashed separately, with no claim that the JSON bytes equal the original CMU file. The selected 128 problems contain 1,272 supplied paragraphs: 127 problems have ten, one has two. Every supplied paragraph is retained. All 128 questions are answerable, so this cohort cannot establish abstention behavior.

## Reproduce the frozen inputs

Install `pyarrow` in the evaluation environment for the one-time Parquet conversion, then run:

```bash
python -m benchmarks.prepare_native_data
python -m benchmarks.hotpot_data --path .artifacts/data/hotpotqa-dev-distractor.json
```

[The cohort freeze](../benchmarks/native_budget_dataset_freeze.json) records IDs, counts and source/evidence fingerprints for every development and final cohort. No upstream source text, questions or answers are published in these manifests.

## Run the native comparison

With a separate baseline checkout at the registered `5abc85e` revision:

```bash
python -m benchmarks.native_budget_eval \
  --baseline-src .artifacts/baseline-current/src --candidate-src src \
  --corpus locomo --locomo-path .artifacts/data/locomo10.json \
  --split development --max-queries 128 --expected-queries 128 \
  --output benchmarks/results/native-token-development
```

The default matrix is two character caps, both named tokenizers, three token caps and three repetitions. The historical policy retains its separate 100,000-character retrieval boundary. Every other policy uses each declared character cap. The compressed report keeps all per-query gains/losses, source references, source hashes and retained-block hashes. A semantic candidate can be measured separately with `--candidate-semantic-model-dir PATH`; it changes retrieval candidates, so its block losses against lexical retrieval are reported rather than treated as the token packer's preservation guarantee.

## Prepare actual generated answers

The paired runner accepts explicit per-source settings and records them with each frozen context:

```bash
python -m benchmarks.answer_eval prepare \
  --locomo-path .artifacts/data/locomo10.json --split heldout \
  --max-queries 128 --expected-queries 128 \
  --source baseline=.artifacts/baseline-current/src \
  --source token=src --source semantic=src \
  --source-options 'token={"native_token_budget":true}' \
  --source-options 'semantic={"native_token_budget":true,"semantic_model_dir":".artifacts/models/semantic"}' \
  --budget-chars 8000 --budget-tokens 512 --tokenizer cl100k_base \
  --cohort-label 'previously observed public regression; actual model comparison' \
  --output .artifacts/answer-eval/native-public128.prepared.json
```

The model directory must contain the fixed local semantic model used by the candidate. All sources remain in independent processes, and the semantic index is explicitly built and timed. Preparation does not call the answer model. Execute the frozen input using the actual endpoint's explicit URL and served model ID as described in [answer evaluation](answer-evaluation.md); record endpoint/model artifacts, all attempt errors and unknown usage. A local model's usage is its measured token count, not a hosted-provider bill or a universal quality result.
