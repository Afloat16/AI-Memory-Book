# Resumed unchanged crowding and relevance controls

The unchanged `scripts/validate_v012_revision_recovery.py` driver completed all
four source/backend arms with 144 original probe responses in total. It binds
the complete tracked runtime, worktree HEAD, actual import, backend and loaded
native binary before and after each arm; source and binary identities remained
stable. The original probe's SHA-256 is
`0f699741b6c75bb51e9829323e29d8b3ee6f06ba25be6852efa13897ba2d21a8`.

| Identity | Commit |
| --- | --- |
| Published v0.11 baseline | `78cc906d81818a16884de7de2e613e5a56346f93` |
| Frozen v0.12 candidate | `01032a691abdc4fddfd10f61c9e61f260f9decb3` |

| Backend | Baseline current recovery | Candidate current recovery | Relevance payload differences |
| --- | ---: | ---: | ---: |
| Python | 18/18 | 18/18 | 0/18 |
| Native | 18/18 | 18/18 | 0/18 |

Each arm has 18 current-mode and 18 relevance-mode calls. The 18 observations
per mode are six authored configurations (4, 100 or 1,000 older records; limits
1 or 5), repeated three times. They are not 18 independently authored questions.
Relevance comparison excludes only `latency_ms`; complete remaining payloads
agree. Original text, exact project, page coordinates, budgets and the complete
response matrix are checked, independently of producer recovery labels.

This result retains published v0.11 recovery. It is **18/18 to 18/18**, not a new
3/18 to 18/18 gain; the latter belongs to the older v0.10-to-v0.11 experiment.
Recorded latency is diagnostic only. No new speed advantage is established.

`report.json` records `status=completed` and `accepted=true` for this frozen
probe only. Each arm folder retains its `identity.json`, `raw.json` and worker
log. The parent directory's `resumed-crowding-attempt1.execution.json` and
`resumed-crowding-attempt1.log` preserve the command, outer exit code and output.

The independent saved-data/source-coordinate audit is retained in the sibling
[directory attempt](../resumed-directory-attempt1/README.md), with a passing
[machine-readable proof](../resumed-directory-attempt1/offline-audit.json).
These checks do not substitute for the other v0.12 source acceptance, complete
test-suite, exact-commit CI or publication requirements.
