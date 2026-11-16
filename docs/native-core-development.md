# Broader native core migration after v0.8.1

The user requested a substantially wider rewrite after the two additional
helpers released in v0.8.1. This round starts from native release
`56eccd8c3a6f1d5637664607936da2595ce50c62`, with seven native helpers already
active. Earlier Python-to-native and v0.8.0-to-v0.8.1 results remain separate,
immutable experiments.

The [development plan](../benchmarks/experiments/native_core_plan.json) defines
the boundary. The proposed v0.9.0 expands complete computational function
families: excerpt windows; candidate scoring, selection and context allocation;
conversation segmentation and pagination; and source units used by exact-token
packing. SQL, transaction/schema control, public interfaces, ranking policies,
scope, source identities, budgets and caches retain their existing behavior.

## Implementation direction

One optional CPython extension will contain separate native implementation units
for these families. It keeps Python Unicode code-point coordinates and uses
the existing Python objects at public boundaries. Exact Python reference bodies
remain available for portability, differential verification and supported
customizations. Keeping those references in the repository is intentional;
repository language percentages are not measurements of executed work.

Source-preserving grouping must keep identical page boundaries and IDs. Ranking
must retain arithmetic order, insertion/tie ordering and existing scores.
Excerpt selection must preserve integer position sums and the original
`math.log1p`/`math.fsum` behavior. Token source units must retain fences, sentence
boundaries, invalid-map errors and exact reconstruction. Unsupported types or
changed dynamic dependencies must take the reference path before observable
work can be duplicated.

## Validation and checkpoints

First freeze a read-only native v0.8.1 profile, including source and binary
identities. Add independent oracle tests and normal-path dispatch checks while
the implementation develops. Freeze the resulting candidate and a new formal
protocol before hosted A/B measurements. Keep all old and new evidence,
including failed attempts and regressions. Rebuild and verify the complete
cross-platform package matrix before an acceptance decision and public release.

This initial checkpoint is a development plan, not a performance result or
runtime approval. The current released main remains v0.8.1 until the wider
candidate completes its own acceptance gates.
