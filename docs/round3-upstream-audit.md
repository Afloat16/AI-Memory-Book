# Round-three upstream snapshot and measurement reuse

This audit records official GitHub metadata read on **2026-11-12**, before
round-three scoring or formal timing. Stars are a dated snapshot, not a quality
metric. Default-branch commits and released versions are separate identities.
No upstream archive, model, or benchmark dataset was downloaded for this audit.

## Release and default-branch identities

| Repository | Stars at inspection | Latest relevant release | Release tag resolved to commit | Inspected default-branch commit |
| --- | ---: | --- | --- | --- |
| [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 116,429 | [v15.18.1](https://github.com/thedotmack/claude-mem/releases/tag/v15.18.1) | `2bb98bd08a73c3c4be18cc797ed7c2a43ed2d97b` | `c4a9f5725f420bf9c6e866cdd3b94bd36498af09` |
| [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) | 15,714 | [v3.4.5](https://github.com/akitaonrails/ai-memory/releases/tag/v3.4.5) | `ee73c04c542fa41ca629b046deb4ac108518f407` | `57dac7348e739dbb552c059a55c103e4ca5cfd27` |
| [ranxianglei/billion-context](https://github.com/ranxianglei/billion-context) | 7,007 | [v0.1.213](https://github.com/ranxianglei/billion-context/releases/tag/v0.1.213) | `133f3525c628c4b959bb79ece82af6df82e131a3` | `873715d40a3de24fa0f096c97a21a473c0c51102` |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | 68,867 | [Python v2.2.1](https://github.com/mem0ai/mem0/releases/tag/v2.2.1) | `94c3fe9f238f3dbf29c9ce98643bd71eb13077cd` | `f1791daa86d469249c9b002f62644d58a1eb96a0` |
| [getzep/graphiti](https://github.com/getzep/graphiti) | 32,771 | [v0.31.2](https://github.com/getzep/graphiti/releases/tag/v0.31.2) | `d72407dcedac911e1be9fc15b55e8c05a3efcc36` | `ebef986a0b2360211b65751c111cacb4a7d790eb` |
| [letta-ai/letta](https://github.com/letta-ai/letta) | 25,424 | [0.16.8](https://github.com/letta-ai/letta/releases/tag/0.16.8) | `1131535716e8a31c9a437f8695e25ac98f203a24` | `8816d3a8516893bfdc0fa14bfb1235226012e295` |

Primary metadata came from `https://api.github.com/repos/OWNER/REPO`, its
`commits/DEFAULT_BRANCH`, `releases?per_page=5`, and `git/ref/tags/TAG` endpoints.
Annotated tags were resolved through `git/tags/TAG_OBJECT_SHA`: claude-mem's
`5058bbf29b36704b09082923cec08f5497cb2b04` and ai-memory's
`1f6e2ec4c1fa6e7bad7424bb20d125d35837419f`.

The inspected claude-mem main commit promotes version 15.18.1 for auto-update;
it equals the existing `claude-mem-round2-lock.json` component source, but is
not the release-tag commit. ai-memory's current main is 173 commits ahead of the
locked v3.4.5 release. The existing official binary remains the latest release
at inspection; testing it does not test every unreleased main-branch change.
The [official comparison](https://github.com/akitaonrails/ai-memory/compare/ee73c04c542fa41ca629b046deb4ac108518f407...57dac7348e739dbb552c059a55c103e4ca5cfd27)
records that distinction.

## Billion search component: all locked blobs unchanged

The [inspected default branch](https://github.com/ranxianglei/billion-context/tree/873715d40a3de24fa0f096c97a21a473c0c51102)
is 68 commits ahead of the earlier component pin
`9674cfafbc78c50245ae0d887483d3d6ce880c15`. The
[official comparison](https://github.com/ranxianglei/billion-context/compare/9674cfafbc78c50245ae0d887483d3d6ce880c15...873715d40a3de24fa0f096c97a21a473c0c51102)
contains changes outside the locked kernel files. More directly, the
[complete recursive Git tree](https://api.github.com/repos/ranxianglei/billion-context/git/trees/873715d40a3de24fa0f096c97a21a473c0c51102?recursive=1)
returned 2,440 entries with `truncated=false`. All **16 of 16** paths in
`benchmarks/competitors/billion-round2-lock.json` had exactly the following
locked Git blob IDs; there were zero missing paths or mismatches.

| Locked file | Git blob SHA |
| --- | --- |
| `LICENSE` | `eba0939b44fcea224b18b508937a133c51a47d21` |
| `kernel/package.json` | `c130a693b87601a06adb1abc7653ae3c128b06ca` |
| `kernel/src/search.ts` | `c191f04696ca1485de124d8b380d30359bbf6ee2` |
| `kernel/src/search/algorithms/bm25.ts` | `56fd7225d7e1f268c3c9660ee107d09b2e312668` |
| `kernel/src/search/algorithms/fuzzy.ts` | `c6a6d219af29ab22762e5d507a37e0a5db088b0d` |
| `kernel/src/search/algorithms/hybrid.ts` | `dce30c55386efe2162284089af2a9ab2f1fdeffa` |
| `kernel/src/search/algorithms/semantic.ts` | `c6309e9ad05849af2f969beb76e7c13109bc0825` |
| `kernel/src/search/algorithms/substring.ts` | `5b64c689ad2dff12012892e8d342decfb586a396` |
| `kernel/src/search/doc-cache.ts` | `63d46002a42e6cfab911e23e853d338c81fae907` |
| `kernel/src/search/index.ts` | `ad6c778af1d63aa8c26c9367f7f612b3991aec8b` |
| `kernel/src/search/registry.ts` | `98dd1944f85519e51a34585f883af4311bbe66e3` |
| `kernel/src/search/stemmer.ts` | `c17078129dd071ce703e92717b66661d3e99534d` |
| `kernel/src/search/tokenizer.ts` | `34d770802cac1e1975f914eae01212f766ddf083` |
| `kernel/src/search/types.ts` | `d91a08a7f30e410d470569003a84ddd4c88ef359` |
| `kernel/src/truncate.ts` | `0121ffab173bf20540e76a569fd9447c8de1abcd` |
| `kernel/src/types.ts` | `7e7b4f4699901bf5f9d7b8cabc2ed864295c992a` |

This proves source identity for the supplied-source kernel boundary. It does
not establish equality of the whole billion-context product or measure its
storage, observation, compression, model calls, or final answers. Its license
continues to include the additional product-surface attribution term recorded
in the existing lock. No upstream implementation was copied into product code.

## Round-three performance controller

The authority is `benchmarks/experiments/round3-plan.json` at
`2ce405408d323aac61fa9e9f536a704dd5f2b372`. The new
`scripts/round3_performance.py` reuses frozen pure helpers without changing the
58-file round-two binding. It accepts only old synthetic61/public1015 inputs,
16 sequential workers, the registered ABBA schedule, all five configurations,
and all 47,320 timed calls. Both reference-tokenizer counts are computed after
each timed request; they do not multiply the number of retrieval calls.

The native payload hash excludes only `latency_ms`. The official SDK MCP text
and full envelope are hashed without deleting fields. MCP's committed cache
clear happens before timing, and its normal cache write remains included.
The exact full provenance record written by that same request is audited for
source spans, page projection, scope, token/character bounds and default-policy
identity; no second recall is used. Native and MCP full default provenance must
agree. Every worker measures fresh ingestion and unchanged reingestion and must
produce identical indexed-content digests. This preserves the registered write
cost boundary rather than replacing ingestion with a database-copy time.

The source-binding template deliberately has no candidate. After committing the
evaluator and tests and freezing the final runtime, generate a new binding:

```bash
python scripts/round3_performance.py --bind benchmarks/experiments/round3-performance-binding.json \
  --baseline-src /absolute/v030/src --candidate-src /absolute/candidate/src
```

Commit the resulting binding before running. The source checkouts must identify
their committed Python bytes. The evaluator checkout needs the registered plan
commit and baseline objects available to `git show`; fetch those exact SHAs
when using a shallow checkout. Use Python 3.12, `mcp==1.30.0`,
`pydantic==2.14.3`, and `tiktoken==0.12.0`, with tokenizers already cached. No
installed model or generated-answer endpoint is used.

```bash
python scripts/round3_performance.py \
  --binding benchmarks/experiments/round3-performance-binding.json \
  --baseline-src /absolute/v030/src --candidate-src /absolute/candidate/src \
  --locomo-path /absolute/verified/locomo10.json \
  --state-dir .artifacts/round3-performance-UNIQUE \
  --output benchmarks/reports/round3-performance-UNIQUE.json.gz

python scripts/round3_performance.py --audit benchmarks/reports/round3-performance-UNIQUE.json.gz \
  --state-dir .artifacts/round3-performance-UNIQUE
```

Each request has a flushed/fsynced start and finish record. Each completed
worker is immutable and has a compressed raw report plus original/compressed
source-free attempt ledgers. The controller checkpoints after every worker and
preserves failure records. `--resume` accepts only a fully verified completed
worker prefix with the exact same source, binding, corpus, evaluator, packages,
paths and machine boot. It refuses an incomplete worker rather than repeating
calls. Previous partial aggregates and controller failure markers remain in
`controller-attempts/`; an OS lock prevents two controllers resuming at once.

Exit 0 means integrity and the registered performance/resource gate pass.
Exit 2 means incomplete or invalid measurement. Exit 3 means measurements are
complete but the numeric gate failed or an over-10% resource increase needs
explicit review. The read-only `--audit` recomputes all saved metrics and hashes;
a successful audit does not turn a rejected speed/resource result into an
accepted optimization. Preserve the raw report, summary, checkpoint, worker
reports, ledgers and controller-attempt history in a new result branch.
The audit checks both the aggregate and the saved original worker/ledger bytes;
it cannot be satisfied with a rewritten summary alone.

The comparison reports every cell and every round, first versus later rounds,
negative results, initialization/ingestion/replay costs and memory/storage.
Process RSS snapshots include the explicitly labeled evaluator imports; they
are not unique physical memory allocations or provider invoices. Warm OS/SQLite
caches are expected. Neither these measurements nor the high-star architecture
table establishes whole-product superiority, generated-answer accuracy, or a
complete write/summarize/retrieve/generate cost comparison.
