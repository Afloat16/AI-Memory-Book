# Durable hosted validation and interrupted attempts

The hosted controller preserves **execution status separately from benchmark
results**. A cohort becomes completed only when its registered command succeeds
and every expected public result exists. A deadline, controlled cancellation or
keyboard interrupt remains interrupted; a source-free diagnostic never establishes
completion, final-answer accuracy or safe resumability.

This change applies to future jobs using this controller. It does not change the
already launched 4193623 validation matrix, the frozen 407cda1 retrieval candidate,
registered datasets, model artifacts, prompts, budgets, repetitions or scoring.

## The hosted time limit is six hours

[GitHub's Actions limits](https://docs.github.com/en/actions/reference/limits)
set a six-hour execution limit for GitHub-hosted jobs. A larger
timeout-minutes value cannot extend that runner limit. The registered answer
manifest permits 28,800 seconds (eight hours) for each generation phase, so one
hosted job **cannot guarantee that full allowance**.

The future workflow uses the following execution envelope:

| Boundary | Limit | Meaning |
| --- | ---: | --- |
| Hosted cohort job | 360 minutes | GitHub's job ceiling |
| Execution deadline | 330 minutes from the initial reservation step | Includes environment preparation, downloads and benchmark work |
| Always finalizer | 15 minutes maximum | Export source-free diagnostics and publish Git records |
| Artifact upload | 5 minutes maximum | Additional public-report copy |
| Registered answer generation phase | 28,800 seconds | Original phase allowance; unchanged but bounded by the earlier execution deadline |

The deadline is an execution constraint, not a new model or evaluation parameter.
Its available seconds and the original generation allowance are recorded in the
cohort marker. Dependency installation has its own preparation timeout. On Linux,
an in-process timer also covers downloads or preparation that do not use the
controller's subprocess helper.

To provide the full registered eight-hour generation allowance, use a separately
available environment whose execution limit supports it, such as a suitably
configured self-hosted runner. This change neither provisions one nor silently
splits or reduces the registered cohort. An interruption does not authorize a new
model request, replay of an uncertain request, or selection of better completed
subsets.

## Durable intent, explicit interruption and one finalizer

The command writes its running marker before environment collection or model
work. With --publish, it also publishes the running intent before preparing the
cohort. The marker is:

    benchmarks/reports/hosted-<stage>-completion.json

The filename is historical; inspect its status field. Its possible execution
statuses are running, completed, failed and interrupted.

SIGTERM and SIGINT receive explicit handlers. KeyboardInterrupt is also handled.
For a controlled stop, the controller first asks its owned child to stop, allowing
existing evaluators to flush their ledgers and close their owned model servers.
It then terminates remaining processes in that child's group. An execution
deadline produces status interrupted and reason execution_deadline. Raw exception
messages are not written to the public marker. Marker fields and nested environment
metadata have their own whitelist. Legacy pip-freeze strings and command arguments
are represented by hashes; private URLs, source fields and credential values are
not copied into the new publication.

Both the controller's finally block and the workflow's always step call the same
finalizer. The latter can be invoked independently:

    python scripts/run_hosted_validation.py --stage answers-locomo --finalize --publish

Finalizing never prepares data, starts a server or makes a model request. It
turns a remaining running marker into interrupted. A missing or invalid marker
also records unknown interruption rather than assuming that no work occurred.
An existing stage marker prevents ordinary execution from silently replaying
that attempt.

## What survives publicly

The finalizer uses benchmarks/export_interrupted_validation.py to read the
private answer ledger or full-workflow checkpoint. Each changed diagnostic is
preserved under a new exact report filename:

    benchmarks/reports/hosted-<stage>-interrupted-<number>.json

Identical input evidence reuses the existing diagnostic. The exporter retains
only its explicit whitelist: observed attempt identities, permitted engine and
query identifiers, hashes, recognized statuses, numeric usage and elapsed times,
and bounded model-verification evidence. Model identities or arbitrary metadata
that cannot safely be exposed are represented by hashes. It does not copy
questions, source/context text, answers, prompts, error messages or credential
values.

A damaged JSONL file contributes its complete valid prefix. The damaged remainder
is hashed and reported as unknown; it is not treated as a successful request or a
zero-cost failure. Missing checkpoints, absent responses and missing usage remain
unknown. Full-workflow stage and model-verification records receive the same
source-free treatment.

Every diagnostic says partial_diagnostic_not_completion, reports zero exporter
model calls, and declares sufficient_for_resume false. These files support
auditing what was observed. They cannot reproduce or safely continue generation;
raw private evidence and the evaluator's original resume rules would still be
required. The finalizer does not auto-resume.

## Publication is restricted and repeatable

Each stage holds an operating-system lock through execution, finalization and
publication. A publication uses a temporary Git index; it does not commit the
checkout's ordinary index or modify its HEAD. Only the registered public results,
the exact cohort marker, and that cohort's numbered diagnostic paths may be
added. Private artifacts and symlinks are rejected.

Publications use the existing per-run branch scheme:

    validation/20261112-<stage>-<github-run-id>-<github-run-attempt>

A later finalizer loads the existing branch, verifies that it descends from the
same source checkout, and appends only when public bytes changed. An identical
cleanup does not create a second commit or push. Pushes never force-update a
branch; a competing remote writer is not overwritten. The ordinary checkout's
index may contain unrelated staged files without including them in a publication.

The workflow also uploads the explicitly public report directories. Raw datasets,
source/context packages, ledgers, model weights, server logs and credentials
remain outside the Git/public artifact allowlist.

## Remaining hard limits

No in-process handler can run after SIGKILL, loss of the host, or termination of
the complete VM. GitHub cancellation or platform failure can prevent always
steps, artifact upload or the final Git push. The early published running marker
then proves only that the attempt started. It does not reveal its last request
or establish that generation never began.

The controller leaves cleanup time before the six-hour ceiling, but this is
best-effort preservation, not a transactional guarantee from the model server
through remote Git. Network failure or revoked write permissions can still block
publication. Retained raw checkpoints are needed to determine safe recovery;
missing evidence remains unknown. A source-free report must never be used as
permission to replay an uncertain model call.

Unit tests cover the running marker, SIGTERM and KeyboardInterrupt statuses,
in-process deadline handling, refusal to replay an existing marker, finalizer
idempotence and absence of model calls. A real temporary Git remote verifies
repeatable publication, append-only ancestry, unchanged checkout HEAD/index, and
exclusion of a deliberately staged private source file.
