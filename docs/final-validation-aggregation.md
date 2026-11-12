# Aggregate the completed memory validation

This reporting workflow reads already published evidence. It never runs retrieval,
downloads a dataset/model, starts a native comparator, or makes a model request.
A missing cohort prevents all four summaries from running. Valid negative results
and complete attempt matrices containing failures remain visible; passing the
integrity audit does not mean retrieval or answer quality improved.

## Safe activation

The workflow is `.github/workflows/aggregate-validation.yml`. It runs only on
pushes to **`ci/aggregate-memory-validation`**. Saving the facility on
`ci/final-aggregation-tools` runs ordinary CI tests only. After integrating all
completed result branches and these reporting tools, create/advance the dedicated
aggregation branch to that reviewed commit. Do not point it to a partial snapshot.
The workflow cannot trigger the separate twelve-cohort measurement workflow.

The job runs the full unit-test suite, then invokes
`python scripts/aggregate_hosted_validation.py --publish`. It calls:

```bash
python scripts/summarize_native_completion.py
python scripts/summarize_semantic_completion.py
python scripts/summarize_local_answers.py
python scripts/summarize_workflow.py
```

No partial option is supplied. Native completion must contain all eight cohorts
and **24,228 paired query/configuration records**. Semantic completion requires
all four cohorts. Actual answering requires **768 attempts** across the two
registered cohorts and three modes; the native workflow requires **72 answer
attempts** and **42 captured-session attempts**. Failed model/native operations
retain their actual status and zero credit where required by the registered
scorer. Evidence completeness and generated-answer quality remain distinct.

The preserved claude-mem result receives only byte/hash, source, budget,
repetition and published-ledger-projection checks. It is the pinned supplied-source
FTS component, not an observer/full-product workflow. Original source/model and
runtime attribution are preserved; no current evaluator hash is imposed on a
previously recorded source version.

Each cohort keeps its own measured host/process identity. Both modes were paired
inside their respective cohort. The aggregation host does not create new latency
observations, and the tool never pools latency samples across hosts.

## Publication and failure behavior

All canonical inputs are hashed before and after aggregation. Each hosted
native/semantic checkpoint must authenticate the complete output bytes and exact
registered command; published output hashes must match the completion marker.
The strict assessors then validate the raw reports and complete matrices.

A successful job publishes only the nine files listed below to
`validation/final-memory-<run-id>-<attempt>`. It never updates `main` or a
measurement branch. A failed aggregation publishes only its failure audit to
that separate branch; partially derived reports are not staged as a successful
snapshot. The workflow also retains the reporting diagnostics as an Actions
artifact. If testing fails before aggregation begins, no success audit is made.

## Exact required input inventory

The following 80 files must exist in the reviewed snapshot. Raw source
corpora, model weights and private preparation directories are not needed.
The list can be reproduced without writing any report:

```bash
python scripts/aggregate_hosted_validation.py --inventory
```

```text
benchmarks/experiments/claude-mem-component-plan.json
benchmarks/experiments/full-workflow-answers.json
benchmarks/experiments/full-workflow-plan.json
benchmarks/experiments/local-answer-execution.json
benchmarks/experiments/local-answer-plan.json
benchmarks/hosted-validation-plan.json
benchmarks/native-completion-manifest.json
benchmarks/reports/claude-mem-native-smoke.json
benchmarks/reports/hosted-answers-hotpotqa-completion.json
benchmarks/reports/hosted-answers-locomo-completion.json
benchmarks/reports/hosted-claude-mem-completion.json
benchmarks/reports/hosted-native-external-hotpot128-checkpoint.json
benchmarks/reports/hosted-native-external-hotpot128-completion.json
benchmarks/reports/hosted-native-regression-authored36-checkpoint.json
benchmarks/reports/hosted-native-regression-authored36-completion.json
benchmarks/reports/hosted-native-regression-public1015-checkpoint.json
benchmarks/reports/hosted-native-regression-public1015-completion.json
benchmarks/reports/hosted-native-regression-synthetic1297-checkpoint.json
benchmarks/reports/hosted-native-regression-synthetic1297-completion.json
benchmarks/reports/hosted-native-regression-synthetic883-checkpoint.json
benchmarks/reports/hosted-native-regression-synthetic883-completion.json
benchmarks/reports/hosted-semantic-development-synthetic61-checkpoint.json
benchmarks/reports/hosted-semantic-development-synthetic61-completion.json
benchmarks/reports/hosted-semantic-external-hotpot128-checkpoint.json
benchmarks/reports/hosted-semantic-external-hotpot128-completion.json
benchmarks/reports/hosted-semantic-regression-authored36-checkpoint.json
benchmarks/reports/hosted-semantic-regression-authored36-completion.json
benchmarks/reports/hosted-semantic-regression-public1015-checkpoint.json
benchmarks/reports/hosted-semantic-regression-public1015-completion.json
benchmarks/reports/hosted-workflow-transfer36-completion.json
benchmarks/reports/native-completion-checkpoint.json
benchmarks/reports/native-continuation-checkpoint.json
benchmarks/reports/native-recovery-checkpoint.json
benchmarks/results/claude-mem-components-public.json.gz
benchmarks/results/claude-mem-components-public.md
benchmarks/results/claude-mem-components-public.summary.json
benchmarks/results/full-workflow-transfer36.json
benchmarks/results/local-answer-final-hotpotqa.json.gz
benchmarks/results/local-answer-final-hotpotqa.summary.json
benchmarks/results/local-answer-final-locomo.json.gz
benchmarks/results/local-answer-final-locomo.summary.json
benchmarks/results/native-completion-development-synthetic61.json.gz
benchmarks/results/native-completion-development-synthetic61.md
benchmarks/results/native-completion-development-synthetic61.summary.json
benchmarks/results/native-completion-external-hotpot128.json.gz
benchmarks/results/native-completion-external-hotpot128.md
benchmarks/results/native-completion-external-hotpot128.summary.json
benchmarks/results/native-completion-regression-authored36.json.gz
benchmarks/results/native-completion-regression-authored36.md
benchmarks/results/native-completion-regression-authored36.summary.json
benchmarks/results/native-completion-regression-public1015.json.gz
benchmarks/results/native-completion-regression-public1015.md
benchmarks/results/native-completion-regression-public1015.summary.json
benchmarks/results/native-completion-regression-synthetic1297.json.gz
benchmarks/results/native-completion-regression-synthetic1297.md
benchmarks/results/native-completion-regression-synthetic1297.summary.json
benchmarks/results/native-completion-regression-synthetic211.json.gz
benchmarks/results/native-completion-regression-synthetic211.md
benchmarks/results/native-completion-regression-synthetic211.summary.json
benchmarks/results/native-completion-regression-synthetic509.json.gz
benchmarks/results/native-completion-regression-synthetic509.md
benchmarks/results/native-completion-regression-synthetic509.summary.json
benchmarks/results/native-completion-regression-synthetic883.json.gz
benchmarks/results/native-completion-regression-synthetic883.md
benchmarks/results/native-completion-regression-synthetic883.summary.json
benchmarks/results/semantic-final-development-synthetic61.json.gz
benchmarks/results/semantic-final-development-synthetic61.md
benchmarks/results/semantic-final-development-synthetic61.summary.json
benchmarks/results/semantic-final-external-hotpot128.json.gz
benchmarks/results/semantic-final-external-hotpot128.md
benchmarks/results/semantic-final-external-hotpot128.summary.json
benchmarks/results/semantic-final-regression-authored36.json.gz
benchmarks/results/semantic-final-regression-authored36.md
benchmarks/results/semantic-final-regression-authored36.summary.json
benchmarks/results/semantic-final-regression-public1015.json.gz
benchmarks/results/semantic-final-regression-public1015.md
benchmarks/results/semantic-final-regression-public1015.summary.json
benchmarks/semantic-final-plan.json
benchmarks/semantic-recovery-20261112-manifest.json
benchmarks/transfer_cases.json
```

## Exact outputs

```text
benchmarks/reports/native-completion-assessment.json
benchmarks/RESULTS-native-token-budget.md
benchmarks/results/semantic-final-assessment.json
benchmarks/RESULTS-semantic-retrieval.md
benchmarks/results/local-answer-final-assessment.json
benchmarks/RESULTS-local-answers.md
benchmarks/results/full-workflow-transfer36-assessment.json
benchmarks/RESULTS-full-workflow.md
benchmarks/reports/hosted-final-aggregation.json
```

The four summarizer scripts, their imported benchmark code, and the aggregation
script are versioned code inputs. Their source commit and summarizer hashes are
recorded in the final audit; the inventory above lists the canonical evidence and
plan/checkpoint files. Install the declared project verification extras as the
workflow does; no model or native-product installation is performed.
