# Fresh v2 hosted controller

This is an implementation and artificial-correctness checkpoint. It does not select a final runtime or authorize a fresh cohort. No fresh metadata, IDs, source content, retrieval, model initialization or asset acquisition was run while implementing and testing this controller.

The source, quality, budget, provenance, span, payload and resource gates remain those of the registered native and component protocols. The controller only orders their existing actions and makes each transition durable.

## Files and version boundaries

| File | Role |
| --- | --- |
| scripts/round5_fresh_hosted.py | Standard-library authorization gate, exact source/asset preparation, single-use stage controller and Git publication |
| .github/workflows/round5-fresh-hosted.yml | One sequential Linux/Python 3.12 hosted job with sparse driver checkout and always-on evidence preservation |
| tests/test_round5_fresh_hosted.py | 13 artificial methods using invented assets and actual temporary local Git remotes |
| benchmarks/experiments/round5-fresh-hosted-scope.json | Prospective controller registration, including the exact original protocols and call counts |
| scripts/round5_title_reference_fresh_data_v2.py | Versioned original metadata selector and selected-data binding |
| scripts/round5_title_reference_fresh_v2.py | Versioned original five native workers and native gate audit |
| scripts/round5_title_reference_fresh_components_v2.py | Versioned original export, five component engines and component audit |
| scripts/round5_source_content_snapshot.py | Strict deterministic identity for independent ingests only |

The v1 helpers, evaluator, scopes and reports are retained byte for byte. The v2 repair is documented in [round5-fresh-snapshot-v2-repair.md](round5-fresh-snapshot-v2-repair.md): only four verified storage-created clock columns are excluded from cross-independent-ingest identity. All 43 other source/structure columns, row counts and schema/FK declarations remain included. Every within-worker full snapshot and copied export byte/full-snapshot check remains required.

## Required future authorization

Before any claim or source/asset/Parquet download, the controller requires both of these separately reviewed, committed files:

- benchmarks/experiments/round5-fresh-source-authorization.json
- benchmarks/experiments/round5-final-interface-certificate.json

The authorization must use schema version 1, protocol/attempt round5-fresh-hosted-1, status approved-for-first-fresh-attempt, and an integer zero for fresh_rows_decoded_before_authorization. It binds exactly one published v0.3.2 baseline and one explicitly selected final candidate. Each source needs its full commit SHA, runtime SHA256 and complete tracked src file SHA256 map.

It also binds the immutable source-selection evidence path/hash, exact certificate bytes, explicit unique additional_exclusions, and complete independent controller/evaluator file inventory. That inventory includes this controller's scope/script/workflow/artificial test, all tracked Python under scripts/benchmarks/tests, adapter code and locks, benchmark root/experiment JSON, the complete certificate generator registry and source-choice evidence. The authorization file excludes itself from its embedded map; the initial claim separately freezes its exact bytes. The original evaluator registries are not modified.

The future source-choice receipt should be committed under benchmarks/experiments/ so the registered sparse checkout materializes it. If its path is under the excluded benchmarks/reports/ directory, the initial preflight fails before claiming or downloading anything. It never expands that historical report directory or silently substitutes another source-selection record.

The standard-library preflight validates the committed certificate envelope, exact sources, canonical bytes, generator-file inventory and zero-retrieval status. The unchanged interface loader performs its complete observation/schema/reference-token verification during native binding, before metadata selection. A preflight success alone is not an interface or source-quality acceptance result.

The workflow runs the initial preflight before setup-python and package installation. It then pins mcp 1.30.0, pydantic 2.14.3, tiktoken 0.12.0, pyarrow 26.0.1 and regex 2026.11.9. Its artificial gate requires all 24 selected controller/snapshot/integration tests to execute successfully with no skips.

## Fixed progression

All measurements use one VM/boot and execute serially. There are 29 controller stages:

1. Publish an exclusive source/evaluator/host claim, prepare exact sparse detached source worktrees and verified asset bytes, then publish preparation evidence.
2. Register the original component source/evaluator/assets/paths and publish.
3. Bind the original native sources, interface, evaluators, host, Parquet and component registration, then publish.
4. Publish a single-use metadata stage intent, run the original id/type-only selector, and publish its exact selection.
5. Publish a single-use data-binding stage intent, decode only the selected rows through the existing loader, and publish the exact binding.
6. For native workers 0–4, run the original intent builder, publish its intent, then run exactly one worker consuming that private ticket. Publish its report, exit, log and ledger archive before the next intent.
7. Apply the same progression to component workers 0–5: export, final default, final title-following, claude-mem FTS, billion-context and ai-memory hybrid.
8. Run the component saved-result audit and then the native saved-result gate audit. Publish completion only after both succeed.

The preceding list groups related stages; the immutable schedule records each original intent/worker separately. Worker count, order and parameters are not chosen from intermediate outcomes.

| Boundary | Frozen count |
| --- | ---: |
| Native retrieval calls | 5 × 3072 = 15,360 |
| Component search calls | 5 engines × 1536 = 7,680 |
| Component offline quality rows | 15,360 |
| Maximum ai-memory mapped native reads | 2,560 |

No controller query probes, warmups, exploratory retrieval, model calls, hidden cohort searches or parallel measurement are added. Existing registered tokenizer preparation and adapter setup remain inside the original boundaries. All comparator strengths and limitations remain in the original reports; these counts do not establish universal quality or transport-latency superiority.

## Asset preparation

Preparation downloads and verifies bytes without starting an adapter, compiling billion-context or loading an embedding model. Each artifact has one acquisition attempt. A partial file or mismatch is preserved and stops the attempt.

Node is exactly v24.22.1. Its versioned official checksum manifest must contain one exact archive entry; the archive is verified before extracting only the registered binary. The manifest, archive, binary hashes and exact --version result are bound before metadata selection.

The existing locks fix Bun 1.3.13, the claude-mem source archive and selected regular files, each billion-context TypeScript file including its Git blob hash, and the ai-memory v3.4.5 binary plus all three all-MiniLM-L6-v2 files. Preparation uses only the unchanged pure archive/fingerprint/integrity helpers. The raw pinned Parquet file is hashed without decoding it.

Source worktrees are exact immutable commits with only src checked out. Their complete committed file inventory and runtime hash are checked; source files are made read-only. Artificial correctness tests run before those measured worktrees are created, and PYTHONDONTWRITEBYTECODE=1 prevents the earlier measured-source pyc contamination failure.

## Durable publication and failure behavior

Every stage has an exclusive public intent. Its command receives the newly verified published commit, so the original workers retain their complete-prefix and remote-intent checks. Their private random launch tickets stay local and are consumed by the unchanged worker before data/runtime setup.

Each checkpoint verifies the expected remote head and local ancestry, rejects unrelated staged changes, makes one ordinary non-force push, verifies the exact remote head, and compares every staged/public Git blob as bytes. Compressed reports and ledger archives are never decoded into text for publication.

An ambiguous push, remote advance or readback mismatch creates publication-failure.json and prevents all further measurement and automatic publication retry. A nonzero or interrupted stage preserves its actual exit, original log/report/ledger and failure receipt. No summary is reconstructed as a success. The native audit can reject the unchanged native gate after all fixed measurements have been saved; that negative result is retained.

Raw ledgers stay local and are included in the uploaded evidence. Git retains their original lossless gzip archives. If interruption leaves an absent, truncated or corrupt archive, the controller saves the raw bytes in a separate interrupted archive and leaves any original archive unchanged, including malformed deflate data.

There is no resume, reset, reselect, ticket-replacement, source-change or worker-replay option. The preserve command only saves evidence and is itself single-use after a failed attempt. It does not call a selector, retrieval worker, DB exporter or model.

The workflow always uploads the public evidence and runner/preflight/artificial-test logs, existing native worker databases, the canonical export database/bundle, and partial asset files. It does not upload private tickets, arbitrary runtime configuration or the whole private state directory.

The reserved trigger is refs/heads/ci/v033-fresh-hosted-1 and the exclusive result ref is refs/heads/validation/v033-fresh-hosted-1. Neither was triggered or created during this implementation task.

## Artificial validation and limits

Controller source/workflow/tests were committed at d84f2ddb90b1f283a7676709ca5322d65b413423 and checked by Tests run 43467721136. The versioned snapshot repair was previously checked by run 43463394230 at b4f5b97b38dc50f02fd307e16ad81fcb83bed995. The full success/failure logs and receipts are preserved under benchmarks/reports/round5-fresh-hosted-correctness/.

The new tests exercise actual local Git commits/pushes/readback, divergent remote refs, unrelated staged files, a push that succeeded remotely but returned failure, gzip binary identity, private-ticket/raw-ledger exclusion, exact sparse worktrees, strict authorization/inventory/host mutation guards, one-shot nonzero stages, single-acquisition partial downloads, and locked invented assets without adapter/model execution.

This is bounded correctness evidence. A final source choice, its actual certificate, official asset availability, actual hosted fresh execution and measured quality/performance remain unexecuted prerequisites/results. They cannot be inferred from these artificial fixtures.
