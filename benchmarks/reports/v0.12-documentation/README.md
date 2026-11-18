# v0.12 documentation checks

This record verifies the pending-publication documentation against retained
source-bound evidence. It makes no new retrieval, upstream, model, speed,
package-installation or release claim.

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

At this documentation checkpoint v0.12 is source accepted, with publication
checks still pending. The quick start continues to target verified v0.11.0.
Any later delivery update needs its own actual release evidence and a new
claims-audit output; the first audit must not be overwritten.
