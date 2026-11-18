# Additional lexical components: fixed protocol

Protocol: `engineering-extended-lexical-v1`, registered 2026-11-18 before any
engineering quality replay by these adapters. The API fixtures used to check
installation contain only three arbitrary marker pages. No engineering result
was used to select parameters.

## Question and scope

Compare additional **actual upstream lexical ranking components** on the same
authored engineering development workload already used in this repository.
This extends component coverage. It does not establish a ranking of complete
memory products, model answers, real coding productivity, or independent
generalization. BM25S is a retrieval library; Haystack is a framework; Memvid is
a memory backend tested only in explicit lexical mode. They must retain these
labels in any resulting comparison table.

The original `engineering_workflow.workload`, `engineering_components.common_pack`
and `engineering_workflow.score` are imported without edits. The complete
evaluator closure is SHA-256 bound before the run. All 80 unchanged questions,
including eight missing-evidence cases, are retained. A missing-evidence query
that returns context is not called an incorrect generated answer or a measured
failure to abstain.

## Frozen configurations

| Backend | Exact package | Real upstream API | Scope and text representation |
|---|---|---|---|
| Haystack BM25 | `haystack-ai==3.5.0` | `InMemoryDocumentStore` and `InMemoryBM25Retriever.run` | Native equality filter on `meta.project`; complete original bodies; titles stored as metadata |
| BM25S | `bm25s==0.3.16` | `bm25s.tokenize`, `BM25.index`, `BM25.retrieve` | One native index per project selected before retrieval; full original bodies; corpus payload retains metadata |
| Memvid lexical | `memvid-sdk==2.0.160` | `Memvid.put`, `Memvid.find(mode="lex")`, `Memvid.frame` | One shared `.mv2` store; native URI-prefix scope; complete original body plus native title/URI/metadata framing |

Haystack keeps its native default BM25L algorithm, tokenizer and parameters.
BM25S keeps native defaults: Lucene BM25, `k1=1.5`, `b=0.75`, `delta=0.5`,
float32/NumPy scoring and default English stopwords, without a stemmer. Its
native zero-score results are retained; no adapter relevance threshold is
invented. Memvid explicitly disables automatic tags, date extraction and
embeddings; `search_text` is the unchanged original body. Source creation times
are converted from ISO timestamps to epoch seconds for its supported API.
These choices fix the supplied-source comparison boundary, rather than tuning
per backend or per query. Native indexed features are not claimed identical.

All queries are sent verbatim. All backends return at most five native
candidates. Invalid/foreign/duplicate/unmapped candidates are integrity failures;
the adapter must not silently discard them or refill a result list. Each native
ordering is reused at 1200 and 2400 characters using the unchanged common
whole-block packer, which skips complete blocks that do not fit and never adds
new candidates. No Book native excerpt score is substituted into this protocol.

## Memvid source mapping, explicitly limited

In the pinned SDK, text ingestion's lexical result normalizes whitespace and
adds metadata framing. Its `blob` is empty in the API fixture. This experiment
therefore **does not claim byte-exact native source reading**.

Before any common-pack mapping, verify native frame ID, URI, project, page ID,
title, timestamp, empty tags and `text` label. Compare the **entire** native
indexed text against the complete original body plus the known native framing,
after whitespace normalization on both sides. Mere substring/prefix matching is
insufficient. Reject any missing, changed or additional body/framing content.
Only then may the common packer recover exact whitespace from the frozen
supplied-page bundle. Both full native hits and frame metadata are retained, so
the complete mapping can be rechecked offline. The bundle contains original
body bytes, source offsets and source identities, with recorded SHA-256 hashes.

The project component of each URI is percent-encoded with no safe separator;
`scope-alpha` and `scope-alpha/child` must remain separate namespaces. This is a
test of the configured URI mapping and native scope behavior, not a general
authorization or tenancy guarantee.

## Execution and evidence

Use a separate CPython 3.12/Linux x86_64 virtual environment. The lock and
requirements record all 43 resolved package versions and exact wheel hashes,
including the compiled Memvid extension and NumPy runtime. Before every worker
starts, verify installed hashed files against their wheel RECORD, with the one
precisely pinned original-archive exception below, and retain the canonical
file-manifest digest plus native-library digests. Packages remain unmodified.
Their public source repositories are:

- [Haystack](https://github.com/deepset-ai/haystack), with its
  [BM25 retriever API](https://docs.haystack.deepset.ai/docs/inmemorybm25retriever).
- [BM25S](https://github.com/xhluca/bm25s).
- [Memvid](https://github.com/memvid/memvid), distributed as
  [memvid-sdk 2.0.160](https://pypi.org/project/memvid-sdk/2.0.160/).

Each worker receives only public fixture pages and queries, not answer labels.
It has a small allowlisted environment, telemetry opt-outs, no model/service
configuration and a Python socket tripwire. That tripwire is not an OS-level
network sandbox and does not prove interception of Rust syscalls.

At each chronological checkpoint, rebuild the external indexes from exactly
the currently visible pages; future/deleted/replaced sources must be absent.
This measures ranking on current snapshots, not native update/delete semantics.
Run three repetitions per query/backend, alternating forward/reverse backend
order. Repetitions are stability/timing observations, not extra quality cases.

Write the dataset and initial binding before execution. Flush an attempt journal
before every setup/search and immediately after it completes; preserve all full
native outputs, normalized source mappings, packed contexts, scores, checkpoint
metadata, logs and failures. A failed backend stays failed for the rest of that
attempt and is excluded from the completed quality table. Do not rerun or
overwrite a partial directory. Any new attempt needs a new output path and its
relationship to the earlier failure must be reported.

Report evidence recall, complete-evidence rate, the original fixed-policy
consumer checks, stale-only cases, missing-evidence nonempty contexts, source
and budget failures, context length and native output stability. Retain
setup/index, in-worker search and process roundtrip timings only as diagnostic
observations. Do not derive a speed ranking: these backend operations and
representations differ, and this extension is not a performance experiment.

Record the source and loaded native runtime used to materialize fixture pages.
No Book recall runs inside this extension. The resulting external rows can be
compared with Book only when the exact workload, supplied-page digest, candidate
limit and common packing conditions are verified to agree.

## Pre-quality API findings retained

The initial combined installation was interrupted after repeated read timeouts
on the 99.8 MB Memvid wheel. A separate wheel download and hash-bound local
installation succeeded. No quality calls occurred during installation.

Tiny Memvid API probes found that this workspace has no writable `/tmp`, so
each worker receives its own writable `TMPDIR`; the original create call raised
`MV999: failed to allocate Tantivy work directory`. A supplied ISO timestamp was
rejected by the pinned SDK; epoch seconds preserve the same instant. Text-only
`blob` output was empty, leading to the explicit full-normalized-text validation
above. These are API/preparation findings, not quality misses or hidden reruns.

`api-smoke-1` failed before any searches because the published Memvid Linux wheel
has one inconsistent internal RECORD entry. The archive's `_lib.abi3.so` is
54,879,872 bytes, while its RECORD declares 54,863,968 bytes and a different
digest. Checking all 33 hashed archive members found exactly this discrepancy;
the installed binary exactly matches the original archive member. The original
failure and [member audit](../../benchmarks/reports/v0.11-extended-lexical/preparation/memvid-wheel-record-audit.json)
remain intact. The wheel's full SHA-256 was independently checked against the
[official PyPI artifact metadata](https://pypi.org/pypi/memvid-sdk/2.0.160/json),
and the retrieved artifact record is retained beside that audit.

For this exact file only, validate the unchanged original declared hash/size
and the installed bytes against the pinned original-wheel member hash/size.
Reject missing members, changed RECORD values or any other mismatch. This is
verification against the original published archive, **not a complete RECORD
pass**, and does not modify or rebuild upstream code.

`api-smoke-2` also retains the adapter's initial Haystack serialization error:
native `Document.to_dict()` flattens metadata by default; the validator now reads
that actual flattened output. Memvid returned the correct page for all three
present namespaces, including the percent-encoded slash name. Its absent-scope
query raised `MV004: Lexical index is not enabled` rather than returning an empty
list. Later API smoke records this exact native error as a limitation; it never
substitutes an empty native response. The fixed engineering workload queries
only present project namespaces. If Memvid raises during that quality run,
the backend fails normally and does not enter the completed quality table.

## Reproduction

```bash
python -m venv .artifacts/extended-env
.artifacts/extended-env/bin/python -m pip install --require-hashes --only-binary=:all: \
  -r benchmarks/competitors/extended-lexical-requirements.txt
PYTHONPATH=src python -m benchmarks.extended_components --self-test \
  --backend-python .artifacts/extended-env/bin/python --output .artifacts/extended-smoke-1
PYTHONPATH=src python -m benchmarks.extended_components \
  --backend-python .artifacts/extended-env/bin/python --output .artifacts/extended-quality-1
PYTHONPATH=src python -m benchmarks.extended_components --audit \
  --output .artifacts/extended-quality-1
```

The offline audit needs no upstream packages: it checks complete native response
mapping, source/budget constraints and every independently recomputed score and
summary from the saved evidence. Install/smoke success is not a quality result.
