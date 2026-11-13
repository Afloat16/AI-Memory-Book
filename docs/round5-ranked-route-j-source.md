# Candidate J source checkpoint — not validated or selected

This commit preserves the initial runtime draft before its artificial fixtures and independent review. It is not authorized for corpus measurement, a performance claim, or release.

The sole runtime change from integrated I+T1 `d730a620bc0b7afac4de856d2a0fd01a46820c8a` is a private native/stem route helper and its guarded call. Reversing those two edits restores that store file exactly. All other runtime blobs, I's fixed statement cache and the T1 feature remain unchanged. The prospective registration is `4042559de1e6ec1d1c205029ef57b34e40afe17d`.

The draft uses a 97-row scoped hidden-rank inner query, then SQLite's original rank/id ordering over only that bounded result. A cutoff tie or uncertified result falls back to the original query. No heap, epsilon, changed weights, local BM25 corpus, new result cache or persistent configuration is introduced. Native parameter adapters are excluded because a probe plus fallback could bind twice.

Tests and review must establish exact ordering, scope-before-limit, both FTS routes, cursor release/restoration, invalid UTF8 lookahead behavior, custom factories/adapters/functions, optional-path exclusion and complete non-timing payload parity. SQL trace and authorizer observations necessarily see a different query plan; this does not promise identical operation sequences for arbitrary stateful callbacks. Authorization, interruption and other SQLite errors are not broadly caught. Only explicit native ID-column decoding errors may return to the original query to determine its original outcome.

No J corpus retrieval, held-out selection, benchmark, model call or performance comparison has run. The next checkpoint adds `tests/test_round5_ranked_route.py` and triggers the existing Tests workflow. Every failure remains preserved before repair.
