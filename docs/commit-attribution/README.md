# Review: correcting automated commit attribution

The repository owner confirmed that the earlier `github-actions[bot]` commits
were their own work submitted by automation with the wrong Git identity.
The verified account is **Afloat16**, whose existing accepted commit identity is
`Afloat <ShuffleMonkey@163.com>`.

**Status: preparation and review only. No existing main, release tag, or evidence
branch is authorized to move automatically.**

## Audited source

The source main is `b6fa111a53e4395875febd2379aa719e96d1179f`. The audit snapshots
all 315 original branch tips and 16 release tag tips before adding review refs.
It uses complete commit ancestry, not the ordinary development checkout's
shallow history.

The locally verified candidate is
`234891619d7bed88ddf3fae37e7f3e1b14a808b6`, with the same head tree
`bb28f814e9676b22faf020e90193047cf5684ea5` as the original main. Hosted preparation
must reproduce that exact candidate before it can create any remote preview ref.

| Scope | Unique commits | Matching bot author and committer | SHAs that would change |
|---|---:|---:|---:|
| Complete source-main ancestry | 972 | 600 | 922 |
| All original branch/tag ancestry | 1,729 | 922 | 1,671 |

An all-ref rewrite would affect 296 branch tips and 13 release tag tips. The
proposed preview is deliberately limited to source-main ancestry. An unrelated
`Codex <codex@openai.com>` identity found off main is outside the requested bot
mapping and remains unchanged.

## Concrete main-only proposal

| Item | Proposed result |
|---|---|
| Matching bot author / committer | Replace both with the owner's verified identity |
| Existing human author / committer | Preserve exactly |
| File tree at each of 972 commits | Preserve the exact tree object ID |
| Commit descriptions | Preserve the exact original bytes |
| Author and commit dates | Preserve timestamps and time-zone offsets |
| Merge graph | Preserve parent count and order, using the old-to-new map |
| GitHub signatures | Preserve the two unchanged signed commits; omit the invalidated signature on rewritten merge `a0961f29dcdf3801d063e6d69bacaa1bde99e318` |
| Release tags and original evidence branches | Keep their original refs and objects |
| Original main | Retain as `archive/main-before-attribution-b6fa111a` |
| Corrected preview | Create `maintenance/author-attribution-preview` for review |

All 600 matching bot commits are unsigned. The one removed signature belongs
to a later human merge whose parent identity changes; the original signed
object remains available through the original history.

The preview does not remove the historical bot identity from every old commit
URL or release tag. Keeping those originals preserves the published packages'
source bindings and the frozen experiment records. Existing links continue to
refer to the commits actually measured or released.

## Reproducible preparation

[`prepare_attribution_preview.py`](../../scripts/prepare_attribution_preview.py)
reads raw Git commit objects, checks the exact source and expected graph,
prepares replacement commit objects, verifies every transformed object, and
creates one new preview ref. It does not call the network or push refs. It
refuses an existing preview destination and never updates `main` or a tag.

The dedicated preparation workflow publishes only three **new** refs in one
atomic push with create-only empty leases: the archive, the preview, and a review branch containing
the complete old-to-new map and verification report. It checks that remote
`main` still equals the audited source and that all destinations are absent.
The leases reject a destination that appears during preparation; they cannot
replace an existing ref. The workflow is restricted to the preparation branch,
this repository, and attempt 1.

`source-audit.tar.gz` retains the public metadata inputs and independent audit.
`source-audit-manifest.json` describes the archive and its exact inputs. The
workflow's `preview/` directory records the proposed new head and complete
mapping after successful preparation.

[`local-preview/`](local-preview/) retains the first complete prepared map.
The separate [independent verification](independent-preview-verification.json)
checks all 972 pairs against actual raw Git objects using a different parser,
including 1,944 object SHA checks. `independent-preview-audit.tar.gz` preserves
that verifier, both original/candidate object batches and per-object results;
its separate manifest records their hashes.

## Approval boundary

The remaining action would be an explicitly approved, lease-checked replacement
of **only `refs/heads/main`**, from the audited source to the verified preview
head. This is a non-fast-forward history change. Existing clones and branches
would need to synchronize with the corrected main; they should not merge the
old history back into it.

No preparation script or workflow performs that replacement. Release tags,
published assets, original experiment references and other branches stay at
their original identities unless separately reviewed. GitHub may recalculate
profile contributions after main changes; a count of new SHA identities is
not a promise of that many additional contribution events.

Future automation should follow the repository's
[commit attribution convention](../../CONTRIBUTING.md#automated-commit-attribution).
Frozen historical publishers retain their registered bytes; reusing one with
different publication metadata requires a prospective registration, not edits
to the old evidence binding.
