# Native claude-mem supplied-source component comparison

This experiment executes unchanged claude-mem code at
[2cfed762](https://github.com/thedotmack/claude-mem/tree/2cfed7620c1b44db87c7f04cbf073ec37efca38d)
(package version 15.18.0). It is a **supplied-source SQLite FTS retrieval
component**, not the normal observer/Chroma/MCP workflow.

The native SessionStore creates the complete upstream schema. A harness bulk
INSERT puts each frozen original page's title in title and body in text, with
the original project/date and empty semantic fields. Synthetic parent sessions
satisfy foreign keys; they are not claimed as captured sessions. Native
SessionSearch creates the FTS tables/triggers and executes searchObservations.
The adapter does not rewrite questions, emulate ranking, or insert ground truth.

## Frozen controls

The [registered plan](../benchmarks/experiments/claude-mem-component-plan.json)
fixes all 1,015 eligible LoCoMo text questions (649 answerable), 1,339 supplied
pages, top five, three repetitions, both cl100k_base and o200k_base, and
512/1,024/2,048-token caps. Questions are already observed regression data.

The exporter must be Book commit 6f5299004642618e606d001b4c574e1bae572a7e.
Its source hash, exact page bundle hash, cohort hash and query counts are
mandatory guards. The historical Book/Billion/ai-memory quality rows are
reused only after the identical-page/cohort/packing-axis checks pass.

The common assembler adds identical source citations and packs complete
original pages in rank order. This is the historical whole-page policy,
not the newer Book native token-budget API and not claude-mem's production
progressive-disclosure presentation.

## Runtime integrity

[claude-mem-lock.json](../benchmarks/competitors/claude-mem-lock.json) pins
the source archive and official Bun 1.3.13 Linux x64 archive/executable by
SHA-256 and size. During initial preparation all 981 selected source/package/
license files were also checked against the official fixed Git tree's blob
IDs. Native SessionSearch and SessionStore built without npm dependencies
(18 and 54 input modules respectively). The runner imports original verified
TypeScript directly with Bun; it does not run a handwritten clone or a patched
ranker.

Archive extraction reads selected regular members only. Every prepared source
file must equal its pinned archive before and after evaluation. Runtime
configuration and all data stay in the chosen benchmark state directory;
the component does not start an observer, install client hooks, inherit
provider keys, or use an existing user's archive.

## Execute

Run on an otherwise idle Linux x86-64 worker using the project's benchmark
extra. Download the separate pinned LoCoMo file to the path below using the
existing data-preparation workflow; its upstream CC-BY-NC-4.0 license applies.

~~~bash
python -m pip install -e ".[benchmark]"
git fetch origin 6f5299004642618e606d001b4c574e1bae572a7e
git worktree add --detach .artifacts/claude-mem-baseline 6f5299004642618e606d001b4c574e1bae572a7e

python -m benchmarks.competitors.claude_mem \
  --cache .artifacts/competitors/claude-mem

python -m benchmarks.claude_mem_component_eval \
  --smoke --offline \
  --cache .artifacts/competitors/claude-mem \
  --state-dir .artifacts/claude-mem-smoke

python -m benchmarks.claude_mem_component_eval \
  --exporter-src .artifacts/claude-mem-baseline/src \
  --locomo-path .artifacts/data/locomo10.json \
  --cache .artifacts/competitors/claude-mem --offline \
  --state-dir .artifacts/claude-mem-public1015 \
  --output benchmarks/results/claude-mem-components-public
~~~

The smoke uses three fictional pages and tests scope, exact source preservation,
Chinese substring handling and punctuation. It is not a benchmark score.
State directories and report prefixes must be fresh. Preserve interrupted
runs as separate attempts; never blend their timing samples into a new run.

## What the report means

- Evidence recall and complete evidence require intact original annotations
  and matching source spans. They are not generated-answer scores.
- Native function latency and Python/Bun JSON roundtrip are separate.
  Startup, source/runtime preparation, native schema creation, supplied-page
  load with FTS, checkpoint, logical/file DB bytes and process RSS are separate.
  Supplied-page loading is not native observer/capture cost.
- Native returned JSON is the unmodified observation row array, which already
  contains full text. Its tokens are a component consumption surface, not a
  production MCP response and not provider billing.
- Historical comparator timings retain their original host/process metadata
  and differing boundaries. Do not calculate a full-product speedup ratio
  from historical in-process, kernel/bridge and HTTP/MCP rows.
- Chroma, observer summaries, timeline/detail selection, native MCP, host hooks,
  session injection and final answer generation remain unmeasured here.
  claude-mem can use a local OpenAI-compatible observer; missing measurements
  do not imply a commercial API key is required.
- Every attempted query is fsynced to a ledger. Failed queries stay in the
  denominators with empty evidence; errors invalidate successful measurement
  claims. Missing costs are unknown, not zero. Public reports contain only
  IDs, metrics and hashes; source/query text remains in the ignored workspace.

For the product architecture and local observer configuration see the
[official search architecture](https://github.com/thedotmack/claude-mem/blob/2cfed7620c1b44db87c7f04cbf073ec37efca38d/docs/public/architecture/search-architecture.mdx)
and
[official compatible-provider guide](https://github.com/thedotmack/claude-mem/blob/2cfed7620c1b44db87c7f04cbf073ec37efca38d/docs/public/usage/openai-compatible-provider.mdx).
