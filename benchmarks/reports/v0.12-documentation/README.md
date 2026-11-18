# v0.12 documentation checks

This record tracks the source-documentation and completed-delivery checkpoints.
Its documentation audits make no new retrieval, upstream, model or speed
measurement. Published delivery is established by the separately retained
[original release evidence and independent audit](../v0.12-publication/README.md).

## Source-documentation checkpoint

`claims-audit-attempt1.json` records the successful offline documentation audit.
The independent source scorer recomputed all 1,600 saved baseline/candidate
engineering responses and 320 saved LanceDB/Whoosh packed responses. It verified
all 19 acceptance-bound evidence files, every retained search archive member,
six byte-identical Book/external page bundles, the two README comparison tables,
all 18 current common-block result rows, nine chart values and the 26-family
architecture table. Earlier external scores retain their original executions;
they were not searched again.

Run the same audit into a new path after any documentation update:

```sh
python scripts/audit_v012_readme_claims.py --output /absolute/path/to/new-audit.json
```

The historical `scripts/verify_current_readme_results.py` and all frozen quality
evaluators remain unchanged. This new checker is a documentation/saved-record
audit, not a replacement evaluator or new acceptance definition.

Both English and Chinese evidence charts were rendered from their committed
SVGs with Inkscape and visually inspected at 960 × 878 pixels. The nine component
rows, values, footer qualifications and legend text are visible without overlaps
or clipping. The figures explicitly show the Book/BM25S/Whoosh evidence tie and
Whoosh's smaller mean context. Their reproducible source is
`scripts/render_readme_charts.py` and `docs/readme-assets/chart-data.json`.

The historical runtime figure's Chinese subtitle was updated from “not rerun on
v0.11” to “not rerun on v0.12”. Its historical numbers, bars and layout are
unchanged; it is not a fresh performance measurement. The native-latency figures
remain unchanged. The prior current-results document is archived as
`docs/v0.11.0-readme-results.md`; original measured records remain intact.

At the first documentation checkpoint, v0.12 was source accepted and its
publication checks were pending; the quick start therefore targeted verified
v0.11.0. `claims-audit-attempt1.json` remains unchanged as that historical
checkpoint. It is not a statement of the current delivery status.

## Completed-delivery documentation checkpoint

The published v0.12.0 source is
`62508a1ce681111ec5702c88e3aa42f67b9fc9c0`, retaining accepted runtime digest
`2842f78c288454ea7348cb81cb6bd6a972cb26e003faaac64eb81f78b2ffa38b`.
CI run `44275753683`, attempt 1 passed all 11 jobs. Release run
`44275753685`, attempt 1 completed 30 native build/install cells and the real
public-URL installer. The independent audit verifies 4,245 native passes plus
75 explicitly permitted skips, 67 public assets, 65 manifest payloads and
66 checksum entries. These are the actual new release records, not copied
v0.11 results.

Both READMEs now install v0.12.0, report its verified delivery and retain the
v0.11 delivery table as explicitly historical. `current-results.md`, the
v0.12 validation page, deployment instructions and release notes link the new
publication proof. The source-acceptance record and its original pending-gate
list remain unchanged; the later proof closes those gates. Quality numbers,
source hashes, original failures and chart values are unchanged.

`claims-audit-attempt2.json` records the same successful offline numeric audit
after this documentation update. `delivery-documentation-audit.json` separately
binds the published proof, source and run identities to the updated installation
links and delivery sections. It does not rerun installation or publication.
The passing publication proof has SHA-256
`163894d932d34e9957a048663f2afbf1041338dffac42315178b0be4408beb05`;
restoring the original evidence and using the same frozen auditor reproduces
that exact proof. [Full preservation and restoration record](../v0.12-publication/README.md).
