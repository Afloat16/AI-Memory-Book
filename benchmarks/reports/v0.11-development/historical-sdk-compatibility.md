# Historical fixture and supported-SDK test maintenance

This maintenance changes tests and inert historical inputs. It changes neither
`store.py` nor the production MCP transport, and supplies no new retrieval or
latency claim.

## Causes and corrections

| Failure | Cause | Correction |
|---|---|---|
| Directory-v2 artificial reports were rejected as incomplete | The unit fixture copied the evolving live `store.py`, while the historical prospective auditor requires SHA-256 `355687bb28eff83160b42120d7a22be1273c6405fa77e8549266f92dfe0e8b87`. | Copy and verify the exact old source as inert gzip data. A new negative test corrupts those fixture bytes and checks rejection before report construction. The auditor and its digest remain unchanged. |
| Three round-six synthetic startup cases failed the registered-host check | `sys.executable` inherited an invocation path containing `/../`; the historical auditor correctly rejects such paths. | Use explicit unexecuted `/synthetic/python` and `/synthetic/evaluator/scripts/round6_startup.py` paths. Supply that same synthetic process configuration while the unchanged writer validates its artificial rows. A regression changes the invoking interpreter path and still exercises the complete independent audit. |
| C7 default-stream guard tests and a real transcript child failed under MCP 1.29.0 | The production fast-path gate intentionally certifies only MCP 1.30.0. The tests incorrectly required all installed SDKs to qualify; an assertion in the child caused connection closure. | Assert the real installed version's automatic decision. Exercise structural negative guards under an explicitly simulated 1.30.0 unit fixture. Separately compare real SDK transcripts for automatic selection, ordinary SDK fallback, and explicit private combined-writer-helper execution. Production certification remains restricted to 1.30.0. |
| Indexed-reference CLI compatibility failed its exact instructions comparison | v0.11 intentionally added directory-discovery guidance. | Extend the approved expected instructions, verify the new tool's inputs/defaults in both formats, and retain exact comparison of every historical tool when the frozen SDK versions match. The old serialized fixture is unchanged. |

The private helper experiment uses the real installed MCP **1.29.0**, with no
version override in those child processes. All three modes exchange the same
five response messages: initialize, tools, two recalls, and page read. The
combined helper dispatches five combined writes; fallback dispatches five
writes and five flushes. Automatic 1.29.0 execution matches the fallback. Each
server closes its archive once, and stdout/buffer closing behavior matches.
This verifies compatibility of those explicit calls; it does **not** extend
production fast-path certification or claim that MCP 1.30.0 was installed and
tested in this run.

## Retained verification

The first targeted run is preserved in
[historical-sdk-compatibility-attempt1.log](historical-sdk-compatibility-attempt1.log).
It ran 35 tests and reported four errors: after the synthetic host was corrected,
the unchanged producer still constructed its expected helper command from the
real process settings. The second fixture correction supplied the same
synthetic environment during that producer validation. No validation result was
overridden and no audit condition was relaxed.

The complete second run passed **35 tests, zero failures, zero errors and zero
skips**, including genuine SDK subprocesses, negative guards and historical
audit rejection cases:
[historical-sdk-compatibility-attempt2.log](historical-sdk-compatibility-attempt2.log).

```bash
CC=gcc TMPDIR=../book-temp PYTHONPATH=src ../book-venv/bin/python -m unittest \
  tests.test_directory_runtime_v2_preserve \
  tests.test_round6_startup_audit \
  tests.test_round5_candidate_c7 \
  tests.test_indexed_references -v
```

These are targeted local tests. They are not the final exact-commit CI run,
cross-platform release matrix, historical benchmark execution, or publication
acceptance. All preserved input hashes are listed in
[the historical-input manifest](../../../tests/fixtures/v011_historical_inputs/manifest.json).
