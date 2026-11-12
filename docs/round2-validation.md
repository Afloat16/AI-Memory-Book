# Round two: frozen selection and fair component boundaries

The new protocol is registered in [`round2_plan.json`](../benchmarks/round2_plan.json). Its 256-question HotpotQA selection excludes every ID from the previous 128-question evaluation. The selection and data hashes were published before candidate binding or any scored retrieval. Source content remains in ignored local files; the public manifest contains only IDs, counts, hashes and provenance.

The IDs are sorted by SHA256 of a fixed prefix and ID after excluding the previous set. There is no question, answer, difficulty or outcome filtering. All 2,539 supplied paragraphs and 614 support annotations remain in the denominators. This is a new selection from the same external distractor corpus. It does not establish generalization to a new domain or private conversational memory. Model pretraining overlap is unknown.

## What is fixed

| Surface | Registered measurement |
|---|---|
| Native Book baseline and candidate | 256 queries × 2 character caps × 2 tokenizers × 3 token caps × 3 repetitions per runtime |
| Native paired quality | 3,072 distinct query/configuration pairs; repetitions are timing samples, not additional questions |
| Common-page components | Book baseline, Book candidate, claude-mem native FTS, ai-memory local hybrid, billion-context native search kernel |
| Optional semantic route | Bind enabled or disabled before scoring; if enabled, add a separate candidate native stage and component stage |
| Component quality | Identical supplied pages, project scope, top-five limit, citation format and whole-block packer; 6 token configurations |
| Quality diagnostics | Complete evidence, evidence recall, MRR, annotation/query gains and losses, frozen-baseline low-overlap and source-hierarchy groups |
| Latency | Native and adapter p50/p95/mean, first and repeated passes, independent packing, declared search plus all reads |
| Tokens | Exact final context for both tokenizers; native returned envelope, native text and full-read envelope/text separately |
| Preparation | Downloads and cache bytes; native source ingestion, startup/setup, optional embedding/index build |
| Resources | 20 ms sampled worker-plus-descendant RSS by phase; worker peak RSS; regular state bytes and SQLite main/WAL/SHM bytes |

The baseline runtime is pinned in the plan. Current upstream revisions are registered separately in [`round2-upstream-registration.json`](../benchmarks/experiments/round2-upstream-registration.json), preserving the already published selection/plan bytes. The new claude-mem and billion-context locks are explicitly passed to the existing adapters. Historical defaults and reports retain their original pins. ai-memory uses its pinned v3.4.5 release and local hybrid mode.

## Freeze and run

Development must finish before binding. In a clean checkout containing every evaluator file, create the binding with an exact committed candidate checkout:

```sh
python scripts/bind_round2_candidate.py \
  --candidate-commit <full-commit-sha> \
  --candidate-src <candidate-checkout>/src
# Add --optional-semantic only if that separately reported mode is frozen for this run.
git add benchmarks/round2_candidate.json
git commit -m "bench: freeze round two candidate before scoring"
```

The binder refuses an existing binding, uncommitted evaluator files or a candidate whose source bytes do not identify the declared commit. Each worker independently checks the committed binding, exact evaluator/file hashes, full dataset hash and runtime commit/source hash. An absent binding cannot run a score. Do not edit the evaluator after binding and silently treat the resulting run as the same registered measurement.

The dedicated workflow runs only when the sealed commit is pushed to `ci/round2-validation-run`, or through an explicit manual dispatch. Publishing the tools on `ci/round2-validation` does not trigger measurement. The workflow installs local dependencies, runs unit tests, validates the binding and runs every engine sequentially on one Linux host with a fresh worker/state for each stage. No generative model endpoint is configured. The new cohort is not used by unit tests or smoke checks.

Run order is export, native baseline, native candidate, the five registered components, then the two optional semantic stages if bound. A failed stage stops the run and preserves its audit. After the first scored retrieval this cohort becomes regression data; do not tune from its failures and label another run as the same unseen validation.

## Interruption and durable results

The controller creates a separate result identity for each Actions run/attempt. Before preparation, before each stage and after every completed stage, it commits a checkpoint and only the public output whitelist to `validation/round2-<run-id>-<attempt>`. Updates use a temporary Git index and non-force pushes; main is never modified. A changed remote branch head fails publication rather than overwriting another writer.

Each worker fsyncs a started intent before a query call and a finished source-free sample afterward. It exports the full attempt sequence, timing samples, per-query evidence outcomes, context/payload hashes and aggregate metrics into compressed JSON. Original questions, answers, pages, native payload text, downloaded models and private logs are never in the publication whitelist. The Actions artifact is a second public-output copy. Interrupted attempts and incomplete output sets cannot pass the final assessment.

The public files for one run are:

- `benchmarks/reports/round2-<run-id>-<attempt>-checkpoint.json`.
- `benchmarks/results/round2-<run-id>-<attempt>/<stage>.json.gz` and `<stage>.summary.json` for every registered stage.
- `benchmarks/results/round2-<run-id>-<attempt>/assessment.json` and `report.md` after strict assessment.

The strict summarizer verifies every required stage, axis, query and repetition; ledger and raw/summary hashes; exact scope/source/token invariants; runtime pins; same-host identity; resource samples and preparation completion. It recomputes quality aggregates and latency summaries from the published rows. Missing engines or configurations fail; negative retrieval quality does not disappear behind an integrity pass.

An incomplete run can be diagnosed from its saved branch. There is no implicit replay or pooling of measurements from another host. A deliberately started recovery must keep its own identity and timing attribution. The current runner requires a new explicit run; it does not fill missing stages under an old same-host label.

## Interpreting the comparison

Native Book includes its in-process context assembly and token counting. Its component route opens a copy of the same baseline-ingested archive, checks the complete page digest and retains native hierarchy metadata. Copy/open time is reported separately; full source ingestion is measured by the native stages. All rankers use the same supplied original pages, but their product interfaces remain different.

claude-mem executes unchanged native SQLite FTS through a Bun bridge. ai-memory executes local hybrid search through its native HTTP/MCP interface. billion-context executes its unchanged native search kernel through Node, with an in-memory supplied corpus. These are component comparisons and do not represent each product's complete write/summarize/retrieve/answer workflow. No whole-product speed multiplier follows from this table.

ai-memory reads every mapped top-five result on the first pass and checks the full body against the supplied original bytes. Its combined first-pass latency is calculated per query as adapter search roundtrip plus the sum of its read roundtrips, then summarized; two percentiles are never added together. It excludes evaluator verification, reference token counting and common packing. An application could choose fewer reads. Native envelope tokens and text-only tokens describe different surfaces and are not interchangeable with the common evidence budget.

Native ai-memory metadata pages have no mapping to a supplied original page. They still consume their original top-five positions and native payload tokens; the raw report retains null mapping positions and native ID hashes, and the summary counts every such hit. They earn zero source-evidence credit, are not expanded as full source pages, and never cause the evaluator to retrieve replacements. Unknown non-null IDs, duplicate identities and cross-scope results remain hard errors. This policy is fixed before scoring and follows the historical component evaluator's metadata-page treatment.

RSS includes the evaluator and loaded source corpus. Sampling observes a lower bound; summed process RSS can count shared mappings more than once. This is not unique physical memory. State bytes exclude the harness attempt ledger and symlinked model caches; cache/model downloads remain separately accounted. Zero persisted state for a kernel does not imply zero in-memory index cost.

All selected HotpotQA questions are answerable. Retrieval completeness is not final-answer accuracy, abstention quality or hallucination rate. Structural evidence-attainability diagnostics are kept without filtering cases. [HotpotQA's official license](https://github.com/hotpotqa/hotpot#license) is CC BY-SA 4.0 for the data; original text is downloaded separately and is not committed with these reports.
