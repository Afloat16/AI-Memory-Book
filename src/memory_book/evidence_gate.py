"""Optional, conservative delivery gate for explicitly requested declarations.

This is not a general answerability classifier. It consumes the store's
authenticated, bounded declaration analysis and checks the *delivered* pages.
It never concludes that a fact is absent from the entire archive.
"""

from __future__ import annotations

import json
import re


_FIELD = re.compile(r"[A-Za-z_\u3400-\u9fff][A-Za-z0-9_.\-\u3400-\u9fff]{0,127}\Z")


def normalize_required_fields(fields: list[str] | None) -> list[str] | None:
    if fields is None:
        return None
    if not isinstance(fields, list) or not 1 <= len(fields) <= 16:
        raise ValueError("required_fields must be a list of 1 to 16 literal field names")
    if any(not isinstance(field, str) or not _FIELD.fullmatch(field)
           or any(not segment for segment in field.split(".")) for field in fields):
        raise ValueError("required_fields must contain literal identifiers of at most 128 characters")
    return list(dict.fromkeys(fields))


def _plain_declarations(body: str, wanted: set[tuple]) -> list[tuple] | None:
    """A deliberately closed grammar: every clause must be a declaration.

    Ranking tolerates surrounding prose; an evidence gate must not silently
    discard a quotation introducer, condition, revocation or unknown sentence.
    Quoted values and complex explanations are intentionally unsupported.
    """
    from . import store

    if (len(body) > store._MAX_DECLARATION_CHARS or store._quoted_spans(body)
            or store._has_unparsed_quotation(body) or store._NONDECLARATIVE.search(body)
            or store._REASON_RELATION.search(body) or store._REVOCATION_MENTION.search(body)
            or store._EXPLICIT_NO_DECISION.search(body)):
        return None
    declarations = []
    for raw in body.splitlines():
        if not raw.strip():
            continue
        if raw.startswith(("    ", "\t")):
            return None
        raw = re.sub(r"^ASSISTANT:\s?", "", raw)
        if re.match(r"^(USER|SYSTEM|DEVELOPER|TOOL):", raw):
            return None
        for clause in re.split(r"[。;；]|\.(?=\s|$)", raw):
            clause = clause.strip()
            if not clause:
                continue
            assignments = list(store._FIELD_REFERENCE.finditer(clause))
            prose = list(store._PROSE_BINDING.finditer(clause))
            if len(assignments) == 1 and not prose:
                binding = assignments[0]
                identity = store._field_identity(binding["name"])
                value = store._SIMPLE_ASSIGNMENT_VALUE.fullmatch(clause[binding.end("name"):])
                if value is None or value["suffix"].strip() not in ("", "!", "！"):
                    return None
                prefix = store._declaration_qualifier(clause, binding, identity, prose=False)
                literal = value["value"].strip()
            elif len(prose) == 1 and not assignments:
                binding = prose[0]
                if clause[binding.end():].strip() not in ("", "!", "！"):
                    return None
                suffixes = list(store._prose_subjects(binding["subject"]))
                identity = next((identity for _, identity in suffixes if identity in wanted), suffixes[0][1])
                prefix = store._declaration_qualifier(clause, binding, identity, prose=True)
                literal = binding["value"].strip()
            else:
                return None
            if prefix is None or (scope := store._declaration_scope(prefix)) is None:
                return None
            declarations.append((identity, scope, literal))
    return declarations or None


def declaration_support(pool: list[dict], contents: dict[int, str], references: dict[int, str],
                        complete: set[int], fields: list[str]) -> list[dict]:
    """Capture independent field-level proof or uncertainty in the read snapshot."""
    from .store import _field_identity, _field_mention_count, _MAX_DECLARATION_CHARS

    wanted = {field: _field_identity(field) for field in fields}
    records = []
    for item in pool:
        body = contents.get(item["rid"], "")
        refs = json.loads(references.get(item["rid"], "[]"))
        owner_ok = (isinstance(refs, list) and len(refs) == 1 and isinstance(refs[0], dict)
                    and refs[0].get("project") == item["project_id"]
                    and refs[0].get("session_id") == item["session_id"]
                    and type(refs[0].get("turn_index")) is int)
        parsed = (_plain_declarations(body, set(wanted.values()))
                  if item["rid"] in complete and owner_ok else None)
        common = {"page_id": item["id"], "created_at": item["created_at"],
                  "session_id": item["session_id"],
                  "turn_index": refs[0]["turn_index"] if owner_ok else -1}
        for field, identity in wanted.items():
            matches = [(scope, value) for subject, scope, value in (parsed or []) if subject == identity]
            if matches:
                records.extend({**common, "field": field, "scope": scope, "value": value,
                                "supported": True} for scope, value in matches)
            elif len(body) > _MAX_DECLARATION_CHARS or _field_mention_count(body, identity):
                records.append({**common, "field": field, "supported": False})
    return records


def apply_evidence_gate(result: dict, fields: list[str] | None, support: list[dict]) -> dict:
    """Retain evidence only if every required field has a full supported page.

    The support records originate in the same read snapshot as candidate
    retrieval. Only latest, comparable declarations authenticated against the
    complete original turn qualify. A truncated excerpt cannot borrow a
    declaration that was found elsewhere in its page or candidate pool.
    """
    if fields is None:
        return result
    # Import lazily: the store calls this after finishing its snapshot and
    # uses the same identifier identity rules for discovery and validation.
    from .store import CURRENT_QUERY, _declaration_query_terms, query_terms

    temporal = result["temporal"]
    assessment = temporal["evidence_assessment"]
    question = _declaration_query_terms(result["query"]).query
    for field in sorted(fields, key=len, reverse=True):
        question = re.sub(re.escape(field), " ", question, flags=re.IGNORECASE)
    question = CURRENT_QUERY.sub(" ", question)
    field_terms = {term for field in fields for term in query_terms(field)}
    qualifiers = set(query_terms(question)) - field_terms
    full_pages = {page["id"] for page in result["results"]
                  if not page["truncated"]
                  and page["excerpt_spans"] == [[0, page["page_chars"]]]
                  and len(page["text"]) == page["page_chars"]
                  and page["source_refs"]}
    covered: dict[str, list[str]] = {field: [] for field in fields}
    issues = {}
    for field in fields:
        eligible = [item for item in support if item["field"] == field and item["supported"]
                    and qualifiers == set(query_terms(item["scope"]))]
        if not eligible:
            continue
        if len({item["scope"] for item in eligible}) != 1:
            issues[field] = "ambiguous_declaration_scope"
            continue
        timestamp = max(item["created_at"] for item in eligible)
        latest = [item for item in eligible if item["created_at"] == timestamp]
        turns = {item["session_id"]: max(other["turn_index"] for other in latest
                                        if other["session_id"] == item["session_id"]) for item in latest}
        latest = [item for item in latest if item["turn_index"] == turns[item["session_id"]]]
        if len({item["value"] for item in latest}) > 1:
            issues[field] = "conflicting_declarations"
            continue
        uncertain = [item for item in support if item["field"] == field and not item["supported"]
                     and (item["created_at"] > timestamp or (item["created_at"] == timestamp
                          and (item["session_id"] not in turns
                               or item["turn_index"] >= turns[item["session_id"]])))]
        if uncertain:
            issues[field] = "unclassified_current_evidence"
            continue
        covered[field] = list(dict.fromkeys(item["page_id"] for item in latest if item["page_id"] in full_pages))
    missing = [field for field, pages in covered.items() if not pages]
    if temporal["resolved"] != "current" or temporal["preserve_occurrences"]:
        reason = "current_declaration_required"
    elif assessment["status"] == "potential_conflict" or "conflicting_declarations" in issues.values():
        reason = "conflicting_declarations"
    elif issues:
        reason = "unconfirmed_current_declarations"
    elif missing:
        reason = "required_declarations_not_delivered"
    else:
        reason = None
    result["evidence_gate"] = {
        "status": "abstained" if reason else "supported",
        "required_fields": fields,
        "supported_fields": [field for field in fields if covered[field]],
        "missing_fields": missing,
        "supporting_page_ids": covered,
        "reason": reason,
        "field_issues": issues,
        "scope": "returned_complete_pages_from_bounded_candidate_pool",
        "basis": ("Syntactic declarations and source timestamps only; not proof of truth, "
                  "authority, exhaustive coverage or absence from the archive."),
    }
    if reason:
        result["evidence_gate"]["withheld_page_ids"] = [page["id"] for page in result["results"]]
        result["results"] = []
        result["context"] = ""
        result["context_chars"] = 0
        result["estimated_tokens"] = 0
        if "context_tokens" in result:
            result["context_tokens"] = 0
        result["truncated"] = result["candidate_count"] > 0
        result["warnings"].append(
            "Required-field evidence was not established in complete returned declarations; "
            "context was withheld. This does not establish that the archive has no answer.")
    return result
