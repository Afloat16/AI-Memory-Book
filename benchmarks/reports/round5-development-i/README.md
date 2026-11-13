# Candidate I development attempt 1

The exact source, unchanged helpers, old-data schedules and immutable source database bytes are fixed in `../../experiments/round5-development-attempt-i.json`. Profile and paired calls are development diagnostics, not formal release acceptance.

All 4,732 complete profile payloads equal the saved v0.3.2/C2 references. Decompress `profile.json.gz` to `profile.json`; its SHA256 is recorded in `profile-audit.json`. Every paired worker receives a remote started intent before launch and its original completed output is checkpointed before the next worker. Preserve every adverse result; never replay a started stage.

The bound runtime is unchanged by the independently tracked Python3.10 test-only authorizer cleanup repair. Its original failed CI and full log remain under `../round5-statement-cache-ci/`. Passing development checks does not waive exact-source functional CI for final acceptance.
