# Exact development source snapshots

The two Git bundles preserve the exact local commits referenced by the
separate accuracy and scoped-query development reports. Later integration
commits combine these changes and do not replace their original identities.
The prerequisite commits are already saved in the public repository. Bundle
sizes, SHA-256 hashes, source commits and result tips are in `manifest.json`.

From a checkout with those prerequisite commits available, verify and fetch
the retained branches without changing the current worktree:

```sh
git bundle verify benchmarks/reports/v0.13-development/development-sources/accuracy.bundle
git fetch benchmarks/reports/v0.13-development/development-sources/accuracy.bundle refs/heads/work/v013-accuracy-source:refs/heads/reproduce/v013-accuracy
git bundle verify benchmarks/reports/v0.13-development/development-sources/performance.bundle
git fetch benchmarks/reports/v0.13-development/development-sources/performance.bundle refs/heads/work/v013-performance:refs/heads/reproduce/v013-performance
```

Use a separate worktree at the exact runtime commit listed in the manifest
when reproducing its report. Native extensions are rebuilt locally and their
actual paths/hashes are recorded; these source bundles do not claim a
bit-identical compiler output. Setup failures and unsuccessful development
tests remain in the original result directories.

These are development observations. The final combined runtime still needs
its own frozen-source correctness checks and the registered large-scale run.
