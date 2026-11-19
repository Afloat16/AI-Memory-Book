# Public engineering-source transfer holdout, protocol v2

This is a retrieval-only transfer test, frozen before either runtime arm is
queried. It uses 16 real source files from eight immutable upstream commits:
two historically released snapshots each of HTTPX, HTTPCore, Requests and
urllib3. The manifest records the exact Git commit, source URL, capture size,
SHA-256 and Git blob SHA. Every captured byte is checked against both hashes.
The eight corresponding upstream license files are retained beside the code.

The source is real; the 48 questions are independently authored for this
evaluation. They are not private engineering conversations, independent user
questions, production incidents or end-to-end LLM answers. "Current" means
the newer captured snapshot, not the latest upstream release. Runtime owners
were asked not to inspect this corpus before freezing their implementations.
If a failure later informs tuning, this set becomes development evidence.

## Frozen workload

Source files are sliced at whole-line boundaries near 700 characters. Concatenating
the slices must reproduce every original file exactly. Each slice becomes one
ordinary user-message turn through `MemoryBook.ingest`; the engine's `USER: `
prefix is part of its independently verified original-turn mapping. Source
versions keep their actual commit timestamps, filenames, projects and task
identities. No expected answer is passed to retrieval.

There are 609 target turns in four projects. Eight separately scoped copies of
the real-source corpus provide deliberately identical distractor projects,
bringing the workload to 5,481 pages across 36 projects. The copies are artificial
interference controls and are never described as 32 additional real projects.
The named target project remains exact for every query and source follow-up.

Each runtime/backend executes 48 questions at both 1,200 and 2,400 character
budgets, limit five, book strategy, temporal auto, result cache disabled: 96
responses per arm. Cases comprise 32 current-source requests, four multi-file
requests, four historical-source requests, and eight missing-field requests.
Some differently worded requests share a fact, so 96 measurements are not 96
independent facts. The scorer verifies all page/source coordinates, original
text, timestamps and final citation framing before scoring required quotes.
Missing fields exist in other projects but not in the requested target source.

All raw responses and original-page follow-ups are saved. Completeness,
required-span coverage, source errors and evidence-coverage diagnostics are
reported separately. A related nonempty context is not automatically a wrong
answer; a literal field mention is not automatically sufficient evidence.
This protocol does not establish model answer accuracy or absence from all
possible project records. Wall time here is diagnostic only, not a formal
latency comparison; the separate longitudinal protocol owns performance claims.

## Reproduction and integrity

Run `python -m benchmarks.v014_public_holdout describe` without executing
retrieval. Before formal runs, commit this fixture, evaluator, capture helper
and `tests/test_v014_public_holdout.py` and record that protocol commit.

```sh
python -m benchmarks.v014_public_holdout run \
  --source /absolute/runtime/checkout --commit EXACT_RUNTIME_SHA \
  --protocol-commit EXACT_PROTOCOL_SHA --backend native \
  --output /absolute/new/attempt
```

The runner starts a fresh subprocess with the selected source path and backend,
requires committed runtime bytes, checks the protocol against its commit, and
retains failure receipts. It never overwrites an existing attempt directory.
The six integrity tests use source validation and fabricated response mutations;
they do not execute holdout queries and do not enter quality denominators.

The first direct network capture attempt received HTTP 403 before obtaining
any source. The successful capture used the connected GitHub reader at the
same immutable commits. The reusable capture helper remains suitable for an
environment permitted to read GitHub's public API directly; it refuses to
overwrite an existing capture. The manifest identifies the actual method used.

## Pre-measurement independent review

Protocol v1 was preserved in remote commit
`a5705ce3f94b0ff5764ac799f44abe734e7d559d`. Before any holdout retrieval,
independent review identified three evaluator defects. Protocol v2 retains
all source bytes, questions, gold quotes and budgets, and fixes only their
validation: failed scoring retains the original response; a missing-field
signal needs the correct identifier and `returned_excerpts` scope; and the
source-identity helper plus end-of-run native/evaluator identities are bound.
The added adversarial metadata test prevents unrelated or global-absence
signals from receiving credit. No runtime tuning followed a holdout result.
