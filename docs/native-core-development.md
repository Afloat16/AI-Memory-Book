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

## Development verification (ongoing)

The first integrated 17-helper candidate compiled successfully. Its initial
59-test differential run exposed Unicode translation deletion semantics,
Counter method certification and a SQLite internal-cache trace comparison;
these findings were fixed rather than removed from the checks. Checkpoint
`5ebb695d9635134d9bad3ccf643dc3720c10236c` then passed 62 of 63 focused
tests, with one token-extra test skipped locally. The full hosted core and MCP
jobs each ran 1,312 tests and identified one test subprocess path error: it
forced native imports from an unbuilt checkout instead of the actual installed
package. The token-dependent ranking tests passed in the MCP job.

Independent review also found that a pre-import `functools.wraps` modification
of `Counter.__missing__` could change the Python excerpt but be incorrectly
certified for native execution. Certification now checks actual code origin
and globals, and the regression covers pre-import replacements. Unknown
implementations retain the original Python path.

The local workspace was replaced during development. Recovery used committed
Git checkpoints and saved blobs; all post-recovery local measurements are
correctness diagnostics, not speed comparisons against the earlier host.
Segmentation integration, hosted performance acceptance and the complete
native wheel matrix are still pending. Main remains the released v0.8.1.
