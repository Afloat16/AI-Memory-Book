"""Complete short source records within an existing character allocation.

This does not select, rank, merge or rewrite evidence. The caller supplies its
ordinary allocations, including citation costs. Already complete pages and
page order are preserved. Optional exact-token assembly keeps its own policy.
"""
from __future__ import annotations

MIN_BODY_CHARS = 120
SHORT_PAGE_CHARS = 2 * MIN_BODY_CHARS


def complete_short_pages(allocations: list[tuple[dict, str, int]], *,
                         protected_ids: frozenset[str] = frozenset()) -> list[tuple[dict, str, int]]:
    """Trade long-page excerpt slack for complete, short original pages.

    A long page retains at least the ordinary 120-character excerpt floor.
    Only pages longer than two such excerpts can donate; short pages never
    lose space. Small deficits are completed first, with relevance order as
    the tie breaker. Donations come from the lowest-ranked eligible page.
    The total allowance and every citation are unchanged. No query, source
    labels, dates or expected answer are inspected. A page whose allowance
    already admits an authenticated current turn must be protected by its
    caller, so shortening another excerpt cannot resurrect an obsolete turn.
    """
    lengths = [len(row["content"]) for row, _, _ in allocations]
    allowances = [allowance for _, _, allowance in allocations]
    donors = [i for i in reversed(range(len(allocations)))
              if lengths[i] > SHORT_PAGE_CHARS and MIN_BODY_CHARS < allowances[i] < lengths[i]
              and allocations[i][0]["id"] not in protected_ids]
    available = sum(allowances[i] - MIN_BODY_CHARS for i in donors)
    if not available:
        return allocations
    candidates = sorted((lengths[i] - allowances[i], i) for i in range(len(allocations))
                        if allowances[i] < lengths[i] <= SHORT_PAGE_CHARS
                        and allocations[i][0]["id"] not in protected_ids)
    for needed, index in candidates:
        if needed > available:
            break
        allowances[index] += needed
        available -= needed
        for donor in donors:
            amount = min(needed, allowances[donor] - MIN_BODY_CHARS)
            allowances[donor] -= amount
            needed -= amount
            if not needed:
                break
    return [(row, header, allowances[i]) for i, (row, header, _) in enumerate(allocations)]
