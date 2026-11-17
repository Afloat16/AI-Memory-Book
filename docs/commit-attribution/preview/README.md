# Author-attribution preview

Source main: `b6fa111a53e4395875febd2379aa719e96d1179f`. Reviewed candidate: `234891619d7bed88ddf3fae37e7f3e1b14a808b6`.

This candidate corrects 600 bot author/committer identities and changes 922 commit SHAs. All 972 source trees, messages, raw timestamps and ordered parent relationships were checked. No existing branch, release tag, asset or frozen evidence reference is replaced.

The old GitHub signature on `a0961f29dcdf3801d063e6d69bacaa1bde99e318` cannot authenticate its new parent chain; only that invalidated signature is removed. Two unaffected signed commits are retained exactly.

`commit-map.json` records every old and new SHA; `summary.json` records validation; `original-refs.json` records the local ref snapshot before preparation. The fixed source SHA and the separate remote audit define the scope; a runner's local refs are not a complete remote-branch inventory. `sha256-manifest.json` checks the report bytes.

Applying this candidate to main requires a separate explicit history-rewrite decision. The preparation script has no publication operation.
