# Exact local source history after scale run 1

These bundles preserve the actual local commit IDs named by the development
records. The remote recovery checkpoint may have a different commit ID with
the same final file tree. Do not replace an experiment's original source SHA
with the recovery checkpoint SHA.

Both bundles require the public run-1 candidate
`9ea37a7c72aec21b6f106d9631d72d72199e283b`. Their exact byte counts, SHA-256
hashes, heads and contained commits are in [manifest.json](manifest.json).
Each bundle was checked with `git bundle verify` in the existing repository.

| Bundle | Head | Boundary |
|---|---|---|
| `accuracy-ab-development.bundle` | `660995077ba6165872e6644be3e21c00c525fc1a` | Original A/B development, including rejected quoted/conditional/negated-reference and Unicode-quotation attempts. Multi-source failure is still unresolved at this checkpoint; this is not an accepted source. |
| `sparse-performance.bundle` | `0442e1238ac8ea653460bc708c4fcb4dabc6903a` | Performance source `f3b7e31` plus its original build/134-test-per-backend records. No formal speed claim is made by those tests. |

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
