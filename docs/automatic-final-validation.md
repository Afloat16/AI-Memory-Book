# Automatic collection of the fixed hosted validation run

This facility finishes reporting if the chat disconnects. It does **not** run a
benchmark, call a model, replay a request, update `main`, or change a measurement.

## Exactly which run it can collect

The collector accepts only this source identity, in both the event and GitHub's
fixed-attempt REST response:

| Field | Required value |
|---|---|
| Repository / head repository | `Afloat16/AI-Memory-Book`, ID `1453729431` |
| Workflow | `Complete registered memory validation`, ID `415712293` |
| Workflow path | `.github/workflows/complete-validation.yml` |
| Run / attempt | `43178953381` / `1` |
| Measurement source commit | `4193623a4e7453546ae49bcfaf7bdb26f7a24782` |
| Original event / branch | `push` / `ci/complete-memory-validation` |
| Run status | `completed` |

A completed run may have a failure conclusion. The original workflow records
model/consolidation failures; these are valid negative evidence when the entire
registered attempt matrix exists. The collector retains the original conclusion,
stage status and exit code. Missing records, interrupted stages, hash mismatches,
or a failed strict assessment cannot become a complete snapshot.

## Triggers and the already completed event

`.github/workflows/automatic-final-validation.yml` listens to the original
workflow's `workflow_run: completed` event. GitHub only delivers that trigger to a
workflow file present on the default branch. Its code comes from trusted
`main`, not the measured branch. The collector independently checks the
repository, workflow, run, attempt, source commit, branch and original event.

This source run finished before this listener was installed. Completion events
are not retroactive. Two explicit recovery triggers are therefore provided:

1. Run **Automatically finalize registered memory validation** with
   `workflow_dispatch` on `main`. There are no inputs that can select another run.
2. Create or push the dedicated `ci/automatic-final-aggregation` branch after
   this facility has been integrated into `main`.

Both recovery paths still check the same fixed attempt through
`GET /repos/Afloat16/AI-Memory-Book/actions/runs/43178953381/attempts/1` and
check out `main`. They never execute code from the triggering branch. The tools
branch `ci/automatic-final-aggregation-tools` triggers ordinary CI only.

If the existing manual aggregation already completed, no recovery trigger is
needed. There is no schedule, polling loop, or automatic rerun of failed model
jobs. A future source run requires an explicit reviewed change to these pins.

GitHub's relevant behavior is documented in
[workflow_run events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
and [GITHUB_TOKEN workflow triggering](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs).
A result-branch push made with `GITHUB_TOKEN` does not start another push workflow;
this finalizer directly invokes the existing strict aggregator instead.

## Public input boundary

Only these result branches are resolved, once each, to immutable commit SHAs:

- `validation/20261112-answers-locomo-43178953381-1`
- `validation/20261112-answers-hotpotqa-43178953381-1`
- `validation/20261112-workflow-transfer36-43178953381-1`

Each must descend from the fixed measurement source. Its net tree changes
relative to that source may contain only its own registered public files.
The collector uses `git cat-file` on that resolved commit; it never merges,
cherry-picks, checks out, imports Python from, or executes a result branch.

The eight imported files are:

| Cohort | Imported public files |
|---|---|
| LoCoMo answers | `benchmarks/results/local-answer-final-locomo.json.gz`; `benchmarks/results/local-answer-final-locomo.summary.json`; `benchmarks/reports/hosted-answers-locomo-completion.json` |
| HotpotQA answers | `benchmarks/results/local-answer-final-hotpotqa.json.gz`; `benchmarks/results/local-answer-final-hotpotqa.summary.json`; `benchmarks/reports/hosted-answers-hotpotqa-completion.json` |
| Native workflow | `benchmarks/results/full-workflow-transfer36.json`; `benchmarks/reports/hosted-workflow-transfer36-completion.json` |

The workflow's originally published assessment JSON and Markdown are also
checked against its marker but are not imported; trusted summarizers rebuild
those derivations. No manifest-supplied arbitrary path is fetched. A marker must
match the frozen runner's schema, stage and source commit, contain all registered
output hashes, and list no missing output. Every copied blob is a regular
`100644` file, with a one-MiB marker limit and 64-MiB report limit. Symlinks,
unexpected tree changes, oversized files, and different bytes already present
in a canonical input fail collection.

The original inputs are copied byte for byte. Their SHA256 values, resolved
result commit SHAs, measurement source commit and original statuses remain in
the collection audit. Model prompts, private attempt ledgers, model weights,
credentials and arbitrary source files are outside the whitelist.

## Strict assessment and publication

After dependency and full unit-test gates, the collector calls:

```sh
python scripts/aggregate_hosted_validation.py
```

It passes neither `--allow-partial` nor `--publish`, and does not spoof
`GITHUB_REF`. The existing aggregator requires all 80 canonical input files,
checks raw/summary/checkpoint hashes, verifies the preserved claude-mem component,
and runs all four strict summarizers. The final gates remain:

- Native: all eight cohorts and **24,228 query/configuration pairs**.
- Optional semantic: all four cohorts and all 12 budget/cohort quality rows.
- Actual generated answers: **768 attempts**, across both registered cohorts.
- Full native workflow: **72 answer attempts** and **42 captured sessions**,
  with recorded failures retained.

Cohorts' measured environments and latency boundaries remain separate. A
complete integrity audit is not a positive quality verdict or a cross-host
speed comparison.

The collector publishes with a temporary Git index and a normal, non-force push
to a new branch:

```text
validation/automatic-final-43178953381-1-COLLECTOR_RUN_ID-COLLECTOR_ATTEMPT
```

It never changes `main`, a source result branch, the current checkout commit,
or the real Git index. An already existing destination branch is rejected.

On success, this branch adds the eight exact public inputs, the eight derived
assessment/report outputs listed in
[the strict aggregation guide](final-validation-aggregation.md), the existing
`benchmarks/reports/hosted-final-aggregation.json`, and
`benchmarks/reports/automatic-final-aggregation.json`.

On failure, the job exits unsuccessfully and publishes the failure audit plus
only whole stages whose public input bytes were already verified. If strict
aggregation started, its audit is also retained. Newly generated partial
assessment reports are not staged as completed outputs. Existing historical
reports in the base commit remain historical; the failed audit does not endorse
them. The two audit files are also uploaded as Actions artifacts.

This protects against chat interruption. Runner loss before publication,
repository permission failure, or a failed checkout can still prevent a new Git
snapshot; no workflow can recover a process that never exported its records.
The collector never tries to resolve such ambiguity by replaying model calls.
