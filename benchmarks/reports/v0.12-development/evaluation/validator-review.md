# Independent validator review before candidate execution

A separate read-only reviewer audited both new validators, ran their dedicated
tests and independently audited both retained baseline directories. It did not
execute retrieval quality, edit sources or write Git state. Both baseline
archives passed their closed 304-response matrix and score/source checks.

## Findings and disposition

1. **Comparison identity gate.** The frozen 38-question evaluator's `compare`
   function validates row integrity but does not itself require the registered
   baseline SHA or equal backends. Comparing the two baseline backend outputs
   therefore produces a valid zero-difference row comparison but does not
   establish candidate behavior. The original evaluator and baseline records
   remain unchanged. A separate `v012_revision_pair_audit.py` now requires
   baseline `78cc906d81818a16884de7de2e613e5a56346f93`, the actual selected
   candidate commit, matching backends, complete source identities and import
   paths, and rechecks every runtime file against the requested Git objects,
   before any candidate claim is made. Two identity-rejection tests pass.
   The actual candidate comparison remains pending.

2. **Guard metadata validation.** In-memory copies of the original 450-character
   counterexample showed that the initial guard checker accepted altered
   excerpt spans, empty or corrupt full-page references, incorrect message
   indices and jointly altered page/hit timestamps. The original source quote
   was still genuine, but those metadata contracts were not fully checked.
   Before any candidate guard execution, the checker was strengthened to
   reconstruct exact full-page references from the frozen original turns,
   validate the character excerpt and its clipped references, and require
   original message indices, integer coordinates and dates. Seven mutation
   variants are retained in `test_independent_review_metadata_counterexamples_are_rejected`.
   The four guard-evaluator tests pass after this change. No fixture, gold
   labels, original probe or saved observation was modified.

3. **Failure retention.** The frozen revision evaluator validates a reply
   before appending its complete raw row. If validation fails, its request
   journal and failed report remain, but that invalid reply is not retained.
   This cannot produce a successful run; the existing successful baseline
   matrices are complete. Do not claim unconditional retention of invalid
   replies from that frozen implementation. The not-yet-executed guard worker
   now journals requests before execution and saves a failing reply plus any
   completed original-page follow-ups before rethrowing an exception.

The reviewer found no additional score-calculation or closed-matrix blocker.
The original 482-configurations/34-complete-counterexamples evidence boundary
is preserved. Candidate source execution and the explicit identity-checked
comparison receipt remain separate gates.
