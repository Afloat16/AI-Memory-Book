# Identifier coverage in returned evidence

Recall can find related project history while omitting the specific field the
question asks for. For example, a query for `lease_duration` may retrieve an
approved `worker_count` declaration because both mention approved deployment
configuration. Returning that original context is useful, but it is not a
recorded value for `lease_duration`.

The optional `evidence_coverage` diagnostic makes this limited gap explicit.
It inspects only the final original source excerpts, after character and token
budgets have been applied. It never changes ranking, removes context, rewrites
source bytes or performs another database search. Its work depends on the
request and delivered evidence size, not archive age or page count. Recall
cache version 27 separates these responses from older cached payloads.

## Response contract

The Python, CLI, HTTP, compact MCP and detailed MCP responses retain the same
object, including indexed reference transport:

```json
{
  "evidence_coverage": {
    "status": "insufficient_evidence",
    "scope": "returned_excerpts",
    "requested_identifiers": ["worker_count", "lease_duration"],
    "missing_identifiers": ["lease_duration"],
    "basis": "Only whole identifier mentions in returned source excerpts were checked, with case-folded snake/camel/prose aliases and preserved namespaces. Missing mentions do not prove archive absence; present mentions do not establish a value, authority, semantic answer, or completeness."
  }
}
```

| Status | Meaning |
|---|---|
| `insufficient_evidence` | At least one requested name has no recognized mention in the actual delivered source excerpts. Related context remains available. |
| `identifier_mentions_present` | Every requested name has a recognized mention. This makes no claim about the requested value, answerability, approval, authority, freshness or complete evidence. |
| `not_assessed` | Alternatives, exclusions or syntax limits prevent the check from inferring a coverage requirement. An empty missing list in this state is not a pass. |

Queries without recognized explicit identifiers omit the object. Unlike the
current-declaration assessment, this diagnostic can run for relevance,
historical and occurrence queries. Existing `temporal.evidence_assessment`
statuses retain their separate meaning. A field mentioned on a review agenda
can have `identifier_mentions_present` and `no_comparable_declaration` at the
same time. An unresolved conflict remains unresolved even if every field name
is mentioned.

When identifiers are missing, the warning recommends a focused recall or
directory follow-up in the same project and original-page reads using returned
IDs. Missing mentions may be caused by query scope, a page limit, an excerpt or
token budget, unsupported phrasing, or a retrieval miss. They do not prove that
the project or archive lacks an answer. An empty response under a zero budget
is checked as empty returned evidence even when an answer exists in storage.

## Matching boundary

Recognized query names use ASCII snake case, qualified dotted names, internal
camel case, or one complete identifier inside single backticks. Ordinary
unmarked words, numeric dates, version numbers, URLs and email addresses do not
create identifier requirements. Multiple-backtick prose is not interpreted as
a plain quoted name. At most 32 distinct normalized identifiers, each with at
most 32 word parts, are assessed. Requests containing explicit alternatives or
exclusions remain `not_assessed`; the checker does not decide which option the
user intended to require.

Matching preserves complete words, dotted namespace segments, and leading or
trailing underscore markers. Thus `cache.timeout` does not match
`other.timeout`, `user.id` does not match `user_id`, and `retry_limit` does not
match `max_retry_limit` or `retry_limit_extra`. Case folding and complete
snake/camel/prose word aliases recognize mentions such as `RetryLimit`,
`retry_limit` and adjacent `retry limit`. These are lexical matches only:
case-sensitive program symbols are not declared interchangeable. Semantic
paraphrases, renames and unsupported spelling conventions can remain
unrecognized. Chinese surrounding text is supported, but plain Chinese field
names have no special identifier inference in this check.

Only `results[].text` is inspected. Navigation titles, breadcrumbs, citation
headers, metadata and fields found in another project cannot satisfy the
check. A phrase interrupted by an excerpt ellipsis cannot be reassembled into
a purported whole mention. Diagnostic metadata and warnings are outside the
context character/token budget, as with the existing declaration assessment.

## Validation scope

The new regression tests cover related-but-missing evidence, partial
multi-field requests, namespace collisions, private markers, supported
lexical aliases, undecided values, titles and other projects, old evidence,
budget omission, cache invalidation, source replacement and deletion, syntax
limits, and actual compact stdio MCP follow-up. The original v0.13 missing
query reproduction is preserved separately from new development outputs.
These are targeted diagnostics, not a calibrated abstention model, semantic
answerability benchmark or independent real-project holdout.
