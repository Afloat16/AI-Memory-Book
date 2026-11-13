# Candidate H development attempt 1

The fixed source, helpers, old cohorts, snapshot bytes and schedule are in
`../../experiments/round5-development-attempt-h.json`. The complete original
profile is stored losslessly as `profile.json.gz`; decompress to `profile.json`
and verify its SHA256 against `profile-audit.json` before reconstruction.
The profile contains every non-timing payload hash and profiler diagnostic,
without question or source text. Its timings are not speed evidence.

Each paired worker uses its own fresh database copied from the same frozen
recovery snapshot. Read the corresponding intent before continuation. A
remote started marker without a complete result is an interrupted stage and
must not be silently replayed. Every result, including regressions, is retained.

All eight workers completed: 4,096 calls and 2,048 equal full non-timing
payload pairs. `paired-audit.json` and `paired-independent-audit.json` both
report a pooled p95 geometric improvement of 5.2895176599741305 percent,
with regressions above 5 percent in three cells. H is not selected for formal
performance execution or release. Passing functional CI does not change this.

`paired.json.gz` contains the original workers in the frozen order. Decompress
it to `paired.json`; the SHA256 of the restored bytes must be
`9a0f698b44c8bb3b7f114abbf1aeb5b9b318e7610e038937911a1bbd562bf521`.
Audits use saved data only and execute zero retrieval calls. Do not rerun the
completed profile or paired workers.
