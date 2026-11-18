# Historical round-five evaluator inputs

These `.py.txt` files are immutable data, not tests to import or execute. They
preserve the original schema-3-era test bytes while the runnable tests continue
to check the current schema and historical registration behavior.

The files were copied from the verified baseline checkout and matched byte for
byte against `evaluator_files` in the existing, unchanged
`benchmarks/experiments/round5-c7-performance-binding.json` (evaluator commit
`259fde01a3d189cf01b55b9765457daebc953bff`). The same predecessor file hashes also
appear in the applicable earlier bindings.

| Original path under `tests/` | Original SHA-256 |
| --- | --- |
| `test_round5_covering_index.py` | `490fec5ec90c0798a73d35929089b81d20b57f0d1062c2ed5593749bb61dbc3f` |
| `test_round5_candidate_c4.py` | `f16d4de95d0f9c284963e22b7fe29383a154dd478a4acef271220a6aa1862ee7` |
| `test_round5_c4_performance.py` | `d79de421df8ea7c49809a093c382e26c0f6e50e03568b6d8ca2b2a19dea780ef` |
| `test_round5_c5_performance.py` | `4a23597dc8de9942eefe4531b4ac5cd83bb5bb2a49c2f0128c15355e430bdb43` |
| `test_round5_c6_performance.py` | `7a6f6bf014b4d75928104f1ea8abc74dad55e2fac009b6c6c1abf42b24608952` |
| `test_round5_c7_performance.py` | `03dbd55656459739ff0bfd6cdb330b86c9e87484e00dc6d42a538013e9077a19` |

The candidate-C4 test was additionally archived byte-for-byte during v0.11
development, before updating its live current-query contract. Its SHA-256 was
verified against the unchanged C5, C6 and C7 bindings above. Current queries
now retain candidates for revision comparison; the historical evaluator still
receives the exact original test input, without changes to its recorded hashes.

`tests/round5_historical_fixture.py` builds a temporary copy of the registered C6
input tree, whose C3/C4/C5 subsets serve the earlier registration unit tests. It
checks each saved or unchanged checkout file against the original binding,
along with the binding, summary and plan identities. ROOT and PLAN are redirected
only within explicitly marked historical test contexts and restored on exit.
The saved C7 test is retained as provenance for the corresponding live test edit;
it is not a C6 evaluator input.

The production registration and audit functions still read and verify their
actual checkout. They receive no fixture fallback, altered expected hashes, or
relaxed acceptance rules. Dedicated negative tests corrupt the temporary input
tree and confirm that those unchanged production functions reject the changes.
