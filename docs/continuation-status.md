# Resumable validation status — 2026-11-12

This record is a recovery entry point, not a benchmark result. Follow the exact
committed reports before making quality, speed or cost claims.

## Fresh-workspace recovery checkpoint

On 2026-11-12 this continuation recovered remote `main` at `794489f` and
`feat/semantic-memory-validation` at `4356339` (six additional commits, zero
behind). The latter's CI run `43169559387` passed all nine jobs. Those six
commits were already safely published; no uncommitted previous workspace was
available to recover.

The current run re-created the exact baseline `5abc85e` and candidate
`407cda1` checkouts and verified the pinned public datasets, semantic model,
answer model, and native comparator downloads. The prior synthetic61
completion report and both historical checkpoints remain immutable. The
seven still-pending native cohorts are registered in
`benchmarks/native-continuation-manifest.json`; its new checkpoint is
`benchmarks/reports/native-continuation-checkpoint.json`. Final aggregation
still covers all eight stages from the original completion manifest.

Actual semantic, answer, and workflow results must be read from completed
reports, not inferred from downloads or runner implementation. Runtime fixes
and new evidence are checkpointed on the feature branch before integration.

## Recovered and published

- `main` was advanced from `ce7837f` to `794489f` without rewriting history.
  The latter preserves optional local semantic retrieval, its Python/CLI/MCP
  interfaces, the prior native-token development matrix, and frozen plans.
- Both workflows for `794489f` completed successfully before this promotion.
- The historical native checkpoint is intentionally retained. It has only the
  synthetic61 development stage completed; a stale `running` state for
  synthetic211 is not a completed result.
- Pinned MiniLM ONNX, Qwen2.5-0.5B GGUF, llama.cpp b12110, LoCoMo and HotpotQA
  artifacts have been downloaded anew and verified against the existing hashes.

## Work to finish in this continuation

The runtime is now frozen at `407cda1c5f1dac0e67dfe527d3c23febdad5e818`
(source SHA-256 `63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625`).
Both performance candidates preserve all 2,016 complete development payloads,
excluding only their measured latency. Both original development reports are
retained; some tail-latency regressions remain and are not hidden. The local
integrated worktree passed 323 tests before native workflow locking was added;
the exact frozen runtime's [CI run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43168645993)
also passed. The eight-stage `native-completion-manifest.json` is now running
against a detached candidate snapshot; its new checkpoint must not be confused
with the old interrupted checkpoint.

1. **Native budgets:** preserve token/character/source invariants, verify any
   performance optimization against complete prior outputs on development
   data, then finish the preregistered eight-cohort regression/transfer matrix.
2. **Semantic candidates:** compare lexical and semantic modes with identical
   packing on the four explicitly classified cohorts in
   `benchmarks/semantic-final-plan.json`. Preserve gains, losses and costs.
3. **Real answers:** run the existing frozen Qwen plan on 128 LoCoMo and 128
   HotpotQA questions with the three registered retrieval modes. Keep raw
   licensed source data outside Git and publish trace hashes and measurements.
4. **Native workflow:** separately preregister and measure Book versus the
   executable ai-memory observer/consolidation/retrieval/answer path using the
   existing six-domain diagnostic. Different context settings and this cohort
   must not be mixed with the frozen answer experiment.
5. **Documentation:** update both primary READMEs and validation notes with
   actual measurements, immutable source identities, reproduction commands,
   comparator scope, and limitations. Merge verified work to `main`.

The model answer runner now supports explicit `--resume` with exact experiment
identity checks. Completed calls are retained. Interrupted in-flight requests
remain unknown-cost failures and are never silently retried. A corrupt partial
ledger fails closed. Reuse the existing output prefix only for this explicit
resume mode, and preserve all old reports.

## Interpretation rules

The old public/synthetic/authored questions are regression data. The frozen
HotpotQA cohort supplies an external diagnostic, then becomes regression data
after its first scoring. Evidence completeness, generated-answer quality and
end-to-end workflow costs are distinct measurements. Negative results remain
part of the report. Completing this validation does not establish universal
semantic memory or broad generalization.

## Published progress in this recovery

- Recovery plan published at `3bb9541`; model/process identity and workflow gate fixes at `e5e3ef1`. The latter passed all nine CI jobs in run `43172009568`.
- Native synthetic211 is complete with all registered validation gates passing. The already saved synthetic61 report remains unchanged; six further native stages are still pending.
- Semantic, actual answer, and native-workflow scoring have not started in this recovery at this checkpoint.
