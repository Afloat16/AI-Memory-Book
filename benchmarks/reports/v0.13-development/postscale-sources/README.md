# Exact local source history after scale run 1

These bundles preserve the actual local commit IDs named by the development
records. The remote recovery checkpoint may have a different commit ID with
the same final file tree. Do not replace an experiment's original source SHA
with the recovery checkpoint SHA.

The individual development bundles require the public run-1 candidate
`9ea37a7c72aec21b6f106d9631d72d72199e283b`. The integrated `0a48` source bundle
instead requires recovery checkpoint
`1986fd8ec0f5bedb28041dda4033e573206af677`. Exact byte counts, SHA-256 hashes,
heads, per-bundle prerequisites and contained commits are in [manifest.json](manifest.json).
Each bundle was checked with `git bundle verify` in the existing repository.

| Bundle | Head | Boundary |
|---|---|---|
| `accuracy-ab-development.bundle` | `660995077ba6165872e6644be3e21c00c525fc1a` | Original A/B development, including rejected quoted/conditional/negated-reference and Unicode-quotation attempts. Multi-source failure is still unresolved at this checkpoint; this is not an accepted source. |
| `sparse-performance.bundle` | `0442e1238ac8ea653460bc708c4fcb4dabc6903a` | Performance source `f3b7e31` plus its original build/134-test-per-backend records. No formal speed claim is made by those tests. |
| `accuracy-abc-development.bundle` | `b7c8ed693c8bcbc68537069181061a87bc6c415d` | A/B/C source, original failed attempts, 1,024-page reproductions and the original integrated diagnostic outputs. Later quotation and checklist-fact counterexamples block acceptance of this intermediate source. |
| `integrated-0a48-source.bundle` | `0a48eadd563a1d6622d03cbaf5d5ef274ef8aac7` | Exact integrated source used by the second legacy gate replay and the 62/38/64 diagnostics. Its tree was saved remotely at `2bcf7f3`; original measurements retain the actual local SHA. |
| `accuracy-final-development.bundle` | `e6c799267ef6781fd5e6f48b818eca5ac8908122` | Complete correctness development history, final `1122946` guards and the original `4e4a8eb` diagnostic evidence; requires `9ea37a7`. |
| `integrated-4e4-source.bundle` | `4e4a8eb2fefe31a136033a37fcc844c36162ffae` | Recall-version-26 integrated source measured by the final declaration diagnostics; requires `28e558b`. Its complete tree equals remote `c7fa5c2`, as recorded in the equivalence receipt. |
| `chapter-planner-fix.bundle` | Source `c0aa790`; evidence `2ec6ada` | Preserves both branches, including the original planner-test failure and its narrow source fix; requires `28e558b`. Full SHA identities are in the manifest. |
| `run2-local-source.bundle` | `91412b438a0da95549cc9a3b85eccb4915359a2d` | Exact final local source used by the last legacy replay; requires `c7fa5c2`. Its complete tree equals the formal run-2 source `e0e2515`. |

To inspect a bundle from a clone containing the prerequisite commit:

```sh
git bundle verify benchmarks/reports/v0.13-development/postscale-sources/accuracy-ab-development.bundle
git fetch benchmarks/reports/v0.13-development/postscale-sources/accuracy-ab-development.bundle refs/heads/evidence/v013-ab-development
git show 660995077ba6165872e6644be3e21c00c525fc1a:src/memory_book/store.py
```

The parallel performance bundle exposes
`refs/heads/evidence/v013-sparse-performance`. Fetching it recovers both its
source and result commits. Original raw response files are also present in
the corresponding report directories. Later corrections should add their own
source recovery bundle and retain these original attempts.

The later bundles expose `refs/heads/evidence/v013-abc-development` and
`refs/heads/evidence/v013-integrated-0a48`, respectively. Each can be inspected
using the same `git bundle verify`, `git fetch` and exact-commit `git show`
sequence with its own file/ref/prerequisite.

The final accuracy and integrated bundles expose
`refs/heads/evidence/v013-accuracy-final` and
`refs/heads/evidence/v013-integrated-4e4`. The planner bundle exposes both
`refs/heads/evidence/v013-chapter-plan-source` and
`refs/heads/evidence/v013-chapter-plan-evidence`.
The run-2 local source bundle exposes `refs/heads/evidence/v013-run2-local`.
`final-planner-scope.diff` and its review identify the only runtime change
after the `4e4a8eb` accuracy replay; those old measurements are not relabeled
as fresh measurements of the planner correction.
