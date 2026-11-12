# Fixed-candidate recovery of the round-two protocol

**Completed:** [run 43207732852](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207732852)
passed the complete 10-stage matrix and strict assessment, with 32,256 started
and finished timed searches. All 23 public files are saved at
[`057b814`](https://github.com/Afloat16/AI-Memory-Book/commit/057b814ab809dec57d4fa4c75fe540d59a0f0027).
The [independent strict verification and cross-run analysis](round2-recovery-audit.md)
retain identical evidence/query records and the differing full original-store
snapshot hash. The [separate cost audit](../benchmarks/reports/round2-43207732852-1-component-cost-audit.md)
recomputes every recorded native cost mean for all six components.

The first run, [43201620535](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43201620535), stopped at the first claude-mem query. Its evaluator assumed every adapter returned `results`, while the existing claude-mem adapter returns its unchanged observation rows in `native_payload`. An eagerly evaluated fallback also accessed the missing field. This was an evaluator interface error; the native process loaded all 3,769 pages, passed its FTS check, preserved all 983 verified source files, and exited normally.

All 13 public files from that run remain at commit `150d37799098aa1fb1ddcebe5b42b18954adc035`. The independent interruption audit verifies the raw/summary hashes and complete matrices for export, baseline native, candidate native and both Book components. The failed claude-mem stage retains one started intent and zero finished samples. It is not a completed component comparison.

## What changes in recovery

- Read claude-mem's native rows from its existing `native_payload` array. Read Book, ai-memory and billion-context rows from `results`; Book/ai-memory payload envelopes are not row arrays.
- Select the native payload with an explicit conditional, avoiding evaluation of a missing fallback field.
- Add an explicit recovery registration and binder, preserve the initial binding byte for byte, and label the recovered report as a fixed-candidate protocol recovery.

No runtime algorithm, ranking policy, scoring formula, dataset, selected ID, upstream version, budget, repeat count or optional-mode choice changes. Candidate `cbf626037b42f11f8bc5b6d46f56caac771e54ba` retains runtime SHA256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`; optional semantic remains enabled for separate measurement, coverage remains false, and the product default remains lexical.

The recovery runs the complete 10-stage matrix on one new host. Prior timings are retained with their original host and are never pooled, substituted or selected because they are faster. The cohort has already been scored by the incomplete run, so recovery is not described as a new unseen tuning validation. The fixed candidate was selected before its first score and is not retuned from these outcomes.

## Checks before another formal run

The fictional smoke test traverses each real external adapter's complete `component()` path: search, ID/scope checks, payload token counts, declared full reads, all six packer configurations, attempt ledger, raw/summary export and strict metric/latency verification. Each adapter receives two invented scoped questions and three repetitions; no Hotpot content is loaded. Book's actual native/component path and all four response shapes are also covered by unit fixtures, including empty result lists and unknown scope rejection.

The first fictional smoke's hand-written source references omitted the canonical `USER: ` prefix from their offsets. Strict source-span checks correctly rejected all three adapters' packed outputs. Its seven files remain in `benchmarks/results/round2-recovery-smoke/`. The fixture offsets were corrected by six characters, without relaxing the scorer; the fresh second smoke and its seven files are in `benchmarks/results/round2-recovery-smoke-2/`.

The explicit recovery binder verifies the original binding against its immutable Git commit, the failed checkpoint against its original results commit, all 13 original output hashes, unchanged candidate bytes and parameters, and the registered helper diff hashes. It refuses a second implicit replacement. The normal `frozen_inputs()` gate validates this recovery identity before any scoring worker starts.

The final assessment preserves the recovery attribution. A separate read-only audit compares per-query/context/evidence/native-hit hashes and quality counts for the five stages present in both runs. Any differences remain visible; timing values stay separate. Component MRR refers to evidence order after budget packing, while original top-five positions remain in raw native hit records.
