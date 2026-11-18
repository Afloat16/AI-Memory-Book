# Candidate 4: associate extra query facets with individual declarations

This report records authored regression tests and development work diagnostics.
The cases were created after reviewing candidates 2 and 3. They are not a
holdout, an external-product comparison, or final release acceptance.

The tested `store.py` SHA-256 is
`a68a4b3580ec76dc92bc64b7913deae4803777e4f5170658dcc6503307d69d9c`.
`RECALL_VERSION` is now 19, so cached candidate 3 ordering cannot be reused.
The package version remains 0.11.0.

## Failure retained before the change

Candidate 3 compared remaining query facets using tokens from the whole page.
For `current production lease_duration`, a page declaring a staging value could
therefore qualify because a separate sentence mentioned production. Independent
review reproduced the failure with 8 and 104 old production sessions; the
unexpanded original candidate path retained the earlier production declaration.

The original source snapshot, complete input sessions, baseline/candidate 3
responses, selected-page reads, coordinates, and hashes are preserved in
[facet-association-review-attempt1](facet-association-review-attempt1/report.json).
Before editing production code, the new test module produced 20 failing
subcases across 10 methods. Its original output is retained in
[proposal-facets-candidate3-failures.log](proposal-facets-candidate3-failures.log).

## Conservative admission rule

The new rule applies to supplements to the original comparison pool. The
original pool keeps its existing declaration and unclassified-prose ordering.
When no extra query facets remain after accounting for the declared fields,
candidate 3's authenticated same-field admission path is preserved.

When extra facets remain, every compared field needs one simple declaration
with an adjacent qualifier. Both the proposed page and its original-pool anchor
must satisfy this rule independently. Supported examples include
`Production lease_duration=12`, `Production: lease_duration=12`, and
`Production lease duration is now 12`.

The adjacent qualifier's terms must exactly match the remaining query facets.
Removing stop words cannot turn a relational phrase into a direct qualifier.
The complete simple declaration must end after its value; a free-form suffix
is not interpreted. Multiple declarations of the same field, or multiple
assignments in one clause, do not qualify a supplementary page for such a query.
Each field in a multi-field contract must carry its own qualifier. A production
label on one field cannot qualify a staging declaration of another field.

The implementation does not contain a production/staging vocabulary list and
does not infer natural-language truth. It rejects ambiguous additions instead
of interpreting questions, other sentences, other fields, or broad discussion
as scope. Complex but valid revisions can consequently remain outside the
extended comparison pool; ordinary retrieval remains available.

Source authentication still precedes all reuse of parsing for identical body
text. The shared qualifier map contains only syntax derived from that body;
each source page is checked against its own complete original turn. Rejected
proposals are still removed before any score permutation or duplicate-text
preference, and the retained input is reanalyzed without their field spellings.

## Targeted verification

The first candidate 4 test run passed the candidate, declaration, and new facet
modules: 45 passed and one native-only comparison skipped under the Python
backend. Expanded boundary verification then covered 119 tests across eleven
modules:

| Backend | Observed result | Retained output |
|---|---|---|
| Native | 119 passed, no skips | [native boundary tests](proposal-facets-candidate4-native-tests.log) |
| Python | 118 passed, one native-only comparison skipped | [Python boundary tests](proposal-facets-candidate4-python-tests.log) |

That native comparison passed in the native run. Two additional suffix-negative
examples were then added to the existing facet test method; the complete
10-method facet module passed again in
[proposal-facets-candidate4-suffix-tests.log](proposal-facets-candidate4-suffix-tests.log).

The tests cover both review reproductions, sentence and punctuation boundaries,
discussion prefixes, user questions, other fields, repeated field declarations,
the original anchor's own scope, semantic fusion, ordinary adjacent assignment
and prose positives, and multi-field positive/negative controls. Existing tests
also cover more than 96 old matches, small result limits, project/task/session
scopes, same-session corrections, incomplete pages, deliberately damaged source
turns, retained tail ordering, occurrence queries, and noncurrent modes.

These targeted results do not replace the complete final suite or the separately
frozen baseline/final replay.

## Work counts and backend separation

The unchanged original six-case work probe was rerun explicitly with
`MEMORY_BOOK_TEXT_BACKEND=python`, matching the backend recorded by the earlier
candidate 2 diagnostic. The complete output is
[current-work-candidate4-python.json](current-work-candidate4-python.json).
Each case used one qualification pass and two declaration-clause parses.
Independent declaration-source checks were 5, 5, 96, 96, 100, and 114 pages;
application SELECT counts were 9, 9, 11, 11, 11, and 11. These particular work
counts match the earlier Python diagnostic; no elapsed-time conclusion follows.

The new [facet work probe](../../experiments/v011-facet-qualification-work-probe.py)
retains all inputs, instrumented responses, actual imported `store.py` path and
hash, and parser/source/SQL counts in separate
[Python](facet-work-candidate4-python.json) and
[native](facet-work-candidate4-native.json) files. All six paired response
payloads were identical after removing only `latency_ms`. Instrumented latency
is not used as a performance measurement.

| Authored case | Qualification passes | Declaration-source checks, total / unique | Clause parses | Qualifier parses | Application SELECTs |
|---|---:|---:|---:|---:|---:|
| Other-sentence qualifier, 8 old sessions | 2 | 17 / 9 | 3 | 3 | 10 |
| Direct adjacent qualifier, 8 old sessions | 1 | 9 / 9 | 2 | 2 | 9 |
| Other-sentence qualifier, 104 old sessions | 2 | 193 / 97 | 3 | 3 | 13 |
| Direct adjacent qualifier, 104 old sessions | 1 | 97 / 97 | 2 | 2 | 11 |
| Original anchor's qualifier is unassociated | 2 | 13 / 9 | 3 | 2 | 10 |
| Multiple declarations of one field | 2 | 17 / 9 | 3 | 4 | 10 |

All source checks in these six cases certified complete original turns. The
rejected pages were genuine source text with insufficient declaration/facet
comparability, not unauthenticated text. These counts refer specifically to
`_complete_declaration_pages`; ordinary page and excerpt reads are separate.

Repeated qualification adds work: the 104-old-session negative checks 97
different pages 193 times across two passes. The at-most-96 supplemental-row
limit bounds retained candidates, not SQLite's FTS scan/sort or total CPU time.
The finite reanalysis loop can perform additional passes as proposals are
removed. These diagnostics support that cost disclosure, not a speed claim.

Earlier candidate 3 timings used native while the original baseline/candidate
1/2 probes used Python. They must not be presented as an algorithm-only timing
comparison. The final paired 36-call replay is handled by a separate driver
that verifies actual import paths, complete source inventories, backend/native
hashes, and immutable snapshot working directories. Its eventual results must
be reported separately from the development observations above.
