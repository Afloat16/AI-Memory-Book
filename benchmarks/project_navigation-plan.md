# v0.7.0 project isolation and book navigation protocol

Protocol registered before quality execution or inspection of this workload's
retrieval scores. Authored synthetic development fixtures are not a real-user
study, an LLM coding benchmark, or a complete memory-product comparison. A
runtime and protocol/source manifest must be frozen and published before the
quality runs. Adapter installation and tiny, separate API contracts may run first.

## Fixed cohorts and identities

The unchanged `engineering_workflow.workload()` remains a separate 80-case
regression cohort. Its v0.6.0 records retain their original version and runtime
identity. Current v0.7.0 claims require a current-runtime replay; neither old
scores nor equivalent outputs are described as newly measured old timings.

The new `project_navigation_data.workload()` is `same-topic-project-isolation-v1`:
four chronological checkpoints, eight project books, 80 cases, 64 answerable
cases, 72 required evidence spans, 40 fixed policy-consumer cases and 16
unanswerable cases. Eight of the latter have no evidence anywhere; eight have
the requested fact in a neighboring project but not in the requested project.

Exact project IDs, in fixed order:

1. `route-kernel`
2. `route_kernel`
3. `Route-Kernel`
4. `route-kernel-v2`
5. `route-kernel-tests`
6. `route-kernel-prod`
7. `route-kernel-eu`
8. `route-kernel-us`

Every display name is `Routing Kernel`. Session IDs, titles and code symbols
collide across books. The `routing-kernel` and `routing_kernel` task IDs also
share the same task title. Project IDs are exact strings: case, underscore,
hyphen, suffix and prefix are not aliases for project identity. These are
engineering scope guards, not an authentication or access-control boundary.

| Checkpoint | Case categories | Cases | Answerable | Required spans | Fixed consumer |
|---|---|---:|---:|---:|---:|
| 1 | Initial policy; code identifier | 16 | 16 | 16 | 8 |
| 2 | Replacement policy; historical policy; same-source replacement | 24 | 24 | 24 | 16 |
| 3 | Multiple constraints; failed prototype | 16 | 16 | 24 | 8 |
| 4 | Bilingual long-gap recall; globally missing; missing only in selected project | 24 | 8 | 8 | 8 |

All books concern the same production routing kernel. Neighboring books have
opposite `edge_policy` decisions, and each has a different
`routing.relaxation_limit`. Replacing `active-config` changes that exact
project/session pair. The two alternating neighbor-only fields are
`routing.cache_alignment_bytes` and `routing.prefetch_window_entries`.
Every neighbor-negative case retains an explicit evaluator-only witness of the
foreign fact, so an empty target project is distinguishable from absent data.
Each checkpoint has two maintenance notes per project, without chosen values.
Source insertion is deterministically interleaved across projects. No random
seed, query, evidence label, source length or case is changed after scores.

## Shared ranked retrieval track

Run Book and the six already executed external modes at their existing pinned
versions/configurations: billion-context, claude-mem supplied-observation FTS,
Basic Memory explicit SQLite FTS, Chroma, indexed LangGraph InMemoryStore, and
Mem0 `infer=False` with local Chroma. The original component evaluator, scorer,
data, lock files, adapters and three v0.6.0 runners remain unchanged.

The new driver imports the existing adapter operations, `export_documents`,
`common_pack` and source-grounded `score`; it supplies a cohort explicitly.
Every backend receives the same complete visible source bodies, unmodified
query, exact project ID and native top-five limit. Do not include case category,
gold policy, expected quote, neighbor witness or future source in adapter input.
Native ordering is retained. Shared whole-block packing uses 1200 and 2400
characters, including citations; it skips blocks that do not fit. It does not
truncate bodies, supplement candidates or impose an answer-dependent filter.
Book native excerpts remain a separate regression track.

Three native repetitions measure repeat stability and timing, not three
independent quality cases. Source/project mapping is validated before scoring.
Failures retain their error and partial records, and are never treated as
successful empty responses. Report source errors, cross-project returns,
complete evidence, evidence recall, stale-only, fixed-consumer results, budget
violations and both kinds of missing-evidence behavior separately. Nonempty
retrieval on an unanswerable case does not by itself establish a fabricated
answer: there is no generative answer model in this track.

Chroma, LangGraph and Mem0 still share the same genuine locked MiniLM model.
Their correlated rankings are not three independent model-quality results.
Keep all native setup/embedding, query, process roundtrip and common-pack
measurement boundaries visible. Repetitions reuse native feature caches while
Book's result cache is disabled.

### Pre-quality amendment: native claude-mem project spelling semantics

The retained first preparation attempt, published before any v0.7 quality run
at `benchmarks/reports/v0.7.0-engineering/preparation-attempt1`, executed all
eight native adapters. ReMe and the other six modes passed; the fixed
claude-mem component raised `Native project scope violation` for the separate
tiny fixture. That attempt did not retain the offending native row, and its
exception alone is insufficient to approve continuation.

At the unchanged pin `c4a9f5725f420bf9c6e866cdd3b94bd36498af09`,
[`SessionSearch.buildFilterClause`](https://github.com/thedotmack/claude-mem/blob/c4a9f5725f420bf9c6e866cdd3b94bd36498af09/src/services/sqlite/SessionSearch.ts)
uses the official
[`projectScopeSql`](https://github.com/thedotmack/claude-mem/blob/c4a9f5725f420bf9c6e866cdd3b94bd36498af09/src/services/sqlite/project-read-keys.ts),
which explicitly applies `COLLATE NOCASE` to project reads. This intended
native spelling convention is incompatible with this experiment's exact,
case-sensitive project-ID contract. It is not evidence that the full product
lacks project isolation or an access-control vulnerability.

This amendment was authorized in the project task after that preparation
failure and pinned-source review, before any quality result was available.
It changes only evidence retention and execution continuation. No source,
query, scope, ranking, top-five parameter, frozen adapter, workload or scorer
is changed. A transparent observer of the claude adapter's `_request` records
the complete native response before the unchanged validator rejects it. The
original return object is preserved. A top-level snapshot and list append
add a small observation cost to the outer bridge/call timing; JSON encoding
and disk writes occur after the measured call, and native worker timing is
unchanged. All four original tiny project requests are attempted and retained.

The smoke status remains **failed**. A separate execution-eligibility record
may permit continuation only when all other native smokes passed and the
retained original response authenticates the exact fixed source pin, original
title/text/project, request/query/top-five arguments, and foreign project IDs
that differ only by SQLite's ASCII case comparison. The only eligible error
is the unchanged validator's `ValueError: Native project scope violation`.
Missing raw evidence, a prefix collision, changed source, another scope
mismatch, setup/cleanup error or different failure blocks continuation. The
second preparation run must obtain this evidence before quality is allowed.

Both full cohorts still attempt all eight registered modes. If the same
incompatibility occurs in the same-topic cohort, retain the original failure
and any earlier valid records, stop that backend at its first failed query,
and continue other modes. The failed backend receives no complete-cohort
quality score, zero score or paired quality comparison. Diagnostic partial
records remain inspectable. Its engineering-regression scores are eligible
only if that separate cohort completes every case with source integrity.
The independent final audit rechecks the raw failure and exact partial
coverage; it must reject unregistered or unexplained missing records.

## Additional ReMe component, subject to actual API smoke

The seventh external implementation is ReMe at a source/wheel identity pinned
in its separate `reme-lock.json` and isolated hash-locked dependency environment.
Use the official `DefaultFileChunker` for complete UTF-8 `.txt` source pages,
the actual `LocalFileStore` and its native BM25 retrieval, with embeddings
disabled. Use the native exact `paths` membership filter before ranking/limit;
the eligible paths come solely from the source page's exact project field.
Prefix filtering is not exact project isolation and is not used here.

The registered short pages must each produce one native chunk whose text equals
the complete supplied original body. A different or multiple-chunk outcome is
an adapter-contract failure, not permission to change chunk sizes or fetch
extra candidates. Query preprocessing and BM25 remain upstream. Record native
file/chunk IDs, path mappings, raw results, source and dependency hashes. An
actual setup/filter/source smoke must pass before the quality run. A failed
installation or API is reported as unavailable/failed, not as a zero quality
score. No inference client may call a network service.

This file-based component mode is not ReMe's complete summarizing or agent
workflow. Official MCP Memory's substring search is excluded from this ranked
matrix; no new archive-only adapter is required for this release.

## Book directory and source-navigation contracts

These are separately labeled native Book engineering contracts. They do not
turn unsupported competitor interfaces into zero scores or use harness scope
selection/rejection as evidence of a competitor's native safety behavior.
Basic Memory and other systems may expose their own project and directory APIs;
the earlier FTS/vector component adapters did not evaluate those product APIs.

Use the final same-topic archive for 32 fixed metadata-only directory requests:
eight exact projects, each with a title query, a task-title query, a unique
body-only sentinel query and an absent metadata query. `search_directory` may
return addresses, titles, counts, timestamps and provenance. It must not return
original body text or match a sentinel that occurs only in the body. Record the
entire response, serialized characters/UTF-8 bytes, bounded result counts and
continuation offsets. Use `limit=2` and follow native pagination. Duplicate or
missing addresses and scope mismatches fail the contract.

For each of eight projects, exercise a directory-to-original roundtrip using
only the caller's exact project/task/session descriptor and IDs actually
returned by the native directory. Traverse paginated project TOC, chapter and
section entries; read the selected page with an expected project guard; follow
its real source reference into `read_turn` with 128-character pagination.
Concatenated text and references must reconstruct the original normalized turn.
The driver never reads answer labels to choose a directory address. Measure
actual metadata traffic, read traffic and API call count separately. These
scripts measure addressable navigation, not an autonomous agent's ability to
infer an unknown intended project.

For 24 wrong-book address probes, use each project's neighboring book's real
chapter, section and page ID with the requested project's explicit guard.
Validate the corresponding same-book operation first; an unsupported argument
must not count as a successful guard. Wrong-book operations must return a
clear refusal/error without foreign source content. Keep the actual responses.
The older release already supported directory traversal and full source access
through `get_session`; this track measures the new guards, directory search and
bounded direct-turn interface, not an invented absence of older navigation.

Scope-selection contracts use small separate fixtures: empty archive; one
book; multiple books without scope; multiple books with `limit=1`; session-only
without project; a known chapter whose owner is unambiguous; intentional global
search using `all_projects=True`; explicit empty/whitespace project strings;
unknown exact project; conflicting project/chapter; and project plus
`all_projects=True`. Their accepted behavior follows the frozen public API.
No hidden expected project is guessed from a natural-language topic or display
name. Report any scoped source leakage independently of retrieval quality.

## Hosted execution and independent audit

Use `.github/workflows/project-navigation-comparison.yml`, branch trigger
`validation/project-navigation-v070*`, read-only repository permission and
artifact root `.artifacts/v070-evidence`. Install the existing 206-dependency
lock unchanged, install ReMe in a separate environment, verify public assets,
then run tiny API smokes. Use fresh state under the cache for every run.

A branch ending in `-prepare` executes only installation, protocol unit
contracts, verified asset preparation and tiny adapter smokes. It explicitly
skips every quality cohort, navigation-cohort contract, default-profile replay
and final comparison audit. A full run additionally requires the published,
approved `project-navigation-freeze.json` to match the current runtime,
evaluator, both dataset hashes, all eight backends, three repetitions and both
character caps. The freeze file is not part of its own evaluator hash.

Replay the three unchanged legacy runners on the current frozen runtime.
Run the new driver on both the original engineering cohort and the new
same-topic cohort, with the same registered backends. Also retain Book directory
and scope contracts, current default-vs-explicit 2400/5 validation, logs and
failed attempts. Preparation and the model cache may be reused; observed
quality results may not guide parameter selection.

The independent auditor rechecks each cohort's exact matrix, three repeats,
source visibility, all raw scores and every packed-response field. On the old
cohort, all seven pre-existing modes' complete packed responses must equal the
unchanged legacy matrix (including the Book/billion two-component bridge).
Compare current-runtime old-cohort Book results with v0.6.0 using case-paired
gains/losses and stale-only changes. Keep the new cohort's denominator separate.
Hash inputs, scripts, runtime, protocol, adapters, locks and downloaded artifacts.
Never overwrite a retained result, hide a failed attempt or let Actions create
a source/results commit.
