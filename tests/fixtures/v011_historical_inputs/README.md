# Historical inputs retained during v0.11 test maintenance

These files are inert data. Do not import or execute the saved Python text.
Their exact uncompressed SHA-256 identities and originating commits/bindings
are recorded in [manifest.json](manifest.json).

* `store-v010.py.gz` contains the exact source required by the directory-v2
  prospective auditor. The live implementation has since changed. The
  directory-v2 unit fixture decompresses this file and verifies the original
  `STORE_SHA256` before constructing its artificial report. The production
  evaluator and its pinned digest are unchanged.
* `test_round5_candidate_c7.py.txt` is the exact test registered by the original
  C7 evaluator commit. The live v0.10 test had already evolved after that
  registration, so `test_round5_candidate_c7.pre-v011.py.txt` separately retains
  the live bytes before this maintenance. Both versions were verified against
  their stated provenance; the original binding was not changed.
* `test_round6_startup_audit.py.txt` retains the exact registered synthetic
  startup-audit test before replacing its dependence on the invoking host's
  interpreter path. Production audit checks and registered evidence remain
  unchanged.

The current tests check the current supported interfaces. These archives
preserve what was supplied to earlier experiments and make those two roles
explicit. No historical observation is rerun or relabelled by this maintenance.
