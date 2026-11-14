# Engineering agent evaluation: preparation and execution boundary

`benchmarks.engineering_agent` prepares reproducible engineering task inputs.
It does **not** currently execute a model or produce task-quality scores.
`prepare` and `inspect` work offline; `run` returns `status: blocked` and exit
code 2. This is an infrastructure blocker, not a failed agent task.

During the initial Round7 environment review, the installed Codex CLI exposed
noninteractive execution and JSON events, but its read-only login status was
`Not logged in` (exit 1). No login, model request or model download was performed
for this preparation layer. A later successful login would satisfy only the
authentication check; it would not verify the model, budgets or filesystem
isolation.

## What is implemented

- Explicit, allowlisted snapshot files copied independently into each condition's
  workspace, plus a separate empty memory-state directory. Copies do not share
  writable source inodes. Git history and symlink inputs are rejected.
- A frozen specification containing the episode, window, project, visible-history
  cutoff, model identity, condition identities, prompt, tool policy and budgets.
  File contents, executable bits and preparation code are hashed and checked.
- An optional read-only `codex login status` check. Only its exit status is
  retained. The runner does not read authentication files or retain status text.
- A reusable byte-preserving JSONL collector with an exclusive lock, fsynced
  intent before invoking its event-source callback, and no replay of any existing
  attempt directory. Incomplete and malformed output remains available.

The collector labels every imported stream `captured_unverified` or
`invalid_events`, with `quality_evidence: false`. JSON that looks like a model's
output is not proof that a model ran. Reported numeric usage is kept per event;
missing usage and complete model-call counts remain unknown. The collector does
not infer that multiple usage events are disjoint, add them into a bill, or
interpret a `turn.completed` event as a successful engineering task.

## Prepare one window

Create a separate snapshot directory containing only material available at the
chosen time. The specification lists every file to expose. Unlisted files are
not copied, but the preparation layer cannot determine whether an allowed file
contains future information or an answer: the registered data protocol and its
independent review must establish that.

The following is a format example, **not an experiment registration or result**:

```json
{
  "schema_version": 1,
  "episode_id": "example",
  "window_id": "w1",
  "project": "project-a",
  "visible_until": "2026-01-01T00:00:00Z",
  "workspace_files": ["app.py", "tests/test_visible.py"],
  "conditions": [
    {"id": "no_memory", "memory_policy": "none", "implementation_sha256": null},
    {"id": "book_v034", "memory_policy": "book", "implementation_sha256": null}
  ],
  "model": null,
  "budgets": {
    "wall_seconds": 600,
    "model_calls": 12,
    "tool_calls": 24,
    "input_tokens": 48000,
    "output_tokens": 8000
  },
  "tool_policy": {
    "network": "disabled",
    "tools": ["read", "search", "edit", "visible-test"],
    "history_visibility": "at-or-before-window-cutoff"
  },
  "prompt": "Replace this with the independently authored current task."
}
```

Use separate, nonoverlapping snapshot and preparation directories:

```bash
python -m benchmarks.engineering_agent prepare \
  --snapshot /path/to/visible-snapshot \
  --specification /path/to/window-specification.json \
  --output /path/to/new-preparation

python -m benchmarks.engineering_agent inspect \
  --prepared /path/to/new-preparation

python -m benchmarks.engineering_agent inspect \
  --prepared /path/to/new-preparation --check-auth
```

Model and memory implementation hashes may be `null` during preparation and are
reported as additional execution blockers. A chosen model uses an explicit
`{"id": "...", "cli_version": "..."}` object. These fields record intended
identity; they do not prove which model served a request. Specification and
runner changes require a new preparation. An existing output directory,
including a partially prepared one, is never overwritten.

Inspection is a **pre-attempt** integrity check: modified workspaces, added files,
populated initial memory state or changed evaluator bytes are rejected. This
version prepares each window separately. It does not yet restore prior window
state, ingest history, resolve memory endpoints or enforce a chronology.

## Why execution remains blocked

A separate directory or Git worktree does not hide an answer file, a future
commit, another condition's state or the evaluator from a process running as the
same user. A CLI sandbox label and JSON events also do not establish that hidden
tests were inaccessible.

Before a future execution backend can be connected, it must verify an enforced
view of the filesystem, credentials and network, with hidden tests and future
history unavailable to the agent. The evaluator runs those tests separately on
the submitted patch. The backend must also enforce the registered wall-time,
model-call, tool-call and token limits and bind the actual CLI/model identity.
The budgets currently in the preparation are records, not enforced limits.

There is no `--force`, sandbox-claim override, receipt file or fixture mode that
can authorize a formal run. Even a specification claiming
`"sandbox_verified": true` cannot bypass the built-in blocker. Running

```bash
python -m benchmarks.engineering_agent run --prepared /path/to/new-preparation
```

performs preparation checks and the read-only authentication probe, then returns
the blockers without starting `codex exec`, creating a model-attempt intent or
assigning a quality score.

## Durable event capture for a future verified backend

`capture_cli_events(prepared, condition, attempt_id, stream_factory)` is a Python
primitive. It calls `stream_factory` only after writing and flushing its intent.
The callback returns an iterator of complete byte lines. A later verified
backend can launch its owned CLI process inside that callback and feed its JSONL
stdout to this collector. That backend must additionally own process cleanup,
stderr capture, deadlines and the isolated agent environment; those facilities
are not claimed by the present collector.

The original bytes are saved as `stdout.jsonl`; event identities and validity are
recorded in `ledger.jsonl`. A normal capture also saves `capture.json`. If the
callback raises or iteration is interrupted, the existing bytes and intent
remain, and that attempt ID cannot be used again. An uncertain attempt is not
silently resumed or replaced. Imported events remain unverified even when every
line parses successfully.

The unit tests use artificial events solely to verify this plumbing. They make
zero product or model calls and supply no evidence about memory quality.

## Formal comparison requirements

The [Round7 intent](../benchmarks/experiments/round7-intent.json) and
[engineering-memory goals](engineering-memory-goals.md) remain the governing
scope. Before scoring, freeze concrete data, model, candidate, baseline,
comparators, evaluator, selection and acceptance rules.

Include a current-repository/no-persistent-memory condition, competent raw-history
search, released Book, the candidate, and an applicable pinned comparator. Give
them the same historical cutoff, current code, project/version metadata, model,
tool policy and total budget. Account for complete memory tool payloads and all
ingest, consolidation, read, write and model costs. Native product workflows and
supplied-page component comparisons remain distinct.

Use actual executable task checks and unaffected regression tests. Preserve
cross-project mistakes, obsolete-version answers, unsupported claims, failures,
timeouts and unknown usage. Report unconditional task success and elapsed time;
successful-task-only timing is supplementary. Treat episodes or independent
projects as the statistical unit, rather than counting dependent tool calls as
independent observations. Retrieval hits, authored fixtures and startup speed
cannot substitute for actual model task completion.
