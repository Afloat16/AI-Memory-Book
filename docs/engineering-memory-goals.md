# Engineering memory: the product goal and acceptance boundaries

The primary user goal is to improve the speed and correctness of AI assistance across several similar, long-running algorithm and software projects. The unit of value is a correctly completed engineering task after returning to a project, switching projects, or following a version change.

The v0.3.4 startup improvement remains valid within its measured scope. Startup time, retrieval microseconds and encyclopedic evidence recall do not by themselves establish faster or better engineering assistance.

## Workloads that must be represented

| Situation | Required behavior | Failure to retain |
|---|---|---|
| Return after a long interruption | Recover decisions, constraints, code locations and verification steps with source references | Repeated discovery, unsupported reconstruction of earlier work |
| Switch between similar projects | Apply the active project's actual conventions, versions and constraints | Importing another repository's similarly worded decision |
| Move between revisions or branches | Distinguish current, historical and superseded evidence | Recommending an obsolete API or treating a past state as current |
| Investigate an algorithm defect | Locate exact identifiers and relevant prior experiments; verify a proposed change | Approximate name matches, missing counterexamples, untested fixes |
| Reuse a lesson elsewhere | Explain which assumptions transfer and which require verification | Copying a fix whose preconditions do not hold |
| Encounter missing or contradictory history | State the gap or conflict and gather evidence | Confident invention, treating an empty search as proof of absence |
| Grow and resume a memory archive | Preserve source identity and usable incremental checkpoints | Lost evidence, stale caches, unbounded maintenance cost |

## Separate evidence levels

1. **Artificial correctness fixtures.** Small authored examples expose implementation bugs and validate protocol behavior. They are not real-user or held-out engineering results.
2. **Real repository history replay.** Fixed upstream source/docs/issues/tests, time cutoffs and version identities test evidence retrieval and context assembly. Authored queries or reconstructed sessions are explicitly identified; real source files do not turn generated conversations into authentic transcripts.
3. **Actual AI engineering execution.** The same answering model, task workspace, tool policy and budget produce an answer or patch. Executable task checks and unaffected regression tests determine success. Complete observed task wall time and actual model/tool usage are recorded; retrieval-only results cannot be promoted to this level.
4. **External longitudinal validation.** Repeated project work and unseen repositories/users are required for broad practitioner/generalization claims. A small local replay cannot establish superiority across all repositories or workloads.

## Comparison policy

Include the released Book baseline, no memory, a competent text/code search baseline, and applicable pinned open-source memory implementations. Equal evidence availability, project/version metadata, query cutoff and downstream model/tool budgets are mandatory. Native capture/consolidation workflows and supplied-page retrieval components are reported separately. Opponents receive their documented capabilities; missing a measurement is not a competitor failure.

Primary end-to-end outcomes are task correctness and time to a validated answer or patch. First-token time, memory lookup time, prompt and native tool payload sizes, total model calls, writes/indexing, restarts, RSS and storage are secondary costs. Failures and timeouts stay in the denominators; time among only successful tasks is a secondary view, not the sole speed score. Unknown usage stays unknown.

## Development and confirmation

Record the protocol, selection rule, data/model/runtime identities, scoring code and intended exclusions before first scoring. Keep development cases separate from later confirmation. Once results are observed, those cases are regression data. Preserve original attempts and unfavorable results, bind each candidate to its actual bytes, and publish Git checkpoints after coherent stages.

Do not widen recency heuristics without evidence of supersession. Preserve original source text; prefer explicit, verifiable project/version/time provenance to inferred certainty. Changes to indexing, schema, public tools or capture need compatibility and recovery checks.

## Method references

- [SWE-bench evaluation](https://www.swebench.com/SWE-bench/guides/evaluation/): evaluate generated patches against actual repository tests; distinguish task resolution from a harness that merely ran.
- [SWE-bench harness](https://www.swebench.com/SWE-bench/api/harness/): retain both FAIL_TO_PASS and PASS_TO_PASS checks and invalid/missing test execution.
- [LongMemEval](https://github.com/xiaowu0162/LongMemEval): useful memory dimensions include multi-session reasoning, temporal reasoning, updates and abstention; this does not make its questions coding tasks.

Round-seven data, model selection, measured results and candidate decisions will be recorded separately. This goal document contains no new performance result or universal superiority claim.
