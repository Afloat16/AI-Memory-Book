# Native budget evaluation protocol

The [registered plan](../benchmarks/native_budget_plan.json) separates three delivery policies: historical full-page packing, the existing native excerpts followed by token packing, and the new native token-budget API. The first two are different baselines. A score from one must not be presented as the other.

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
