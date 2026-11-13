# Candidate G development attempt 1

The fixed source, helpers, old cohorts, snapshot bytes and schedule are in
`../../experiments/round5-development-attempt-g.json`. The complete original
profile is stored losslessly as `profile.json.gz`; decompress to `profile.json`
and verify its SHA256 against `profile-audit.json` before reconstruction.
The profile contains every non-timing payload hash and profiler diagnostic,
without question or source text. Its timings are not speed evidence.

Each paired worker uses its own fresh database copied from the same frozen
recovery snapshot. Read the corresponding intent before continuation. A
remote started marker without a complete result is an interrupted stage and
must not be silently replayed. Every result, including regressions, is retained.
