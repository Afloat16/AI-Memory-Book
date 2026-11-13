"""Optional exact context budgeting, preserving already deliverable evidence.

Only the caller's explicitly selected tokenizer is used. This module never
substitutes a character estimate for an exact count and never generates facts.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from functools import lru_cache
from typing import Any, Callable

from .text import terms

TOKENIZERS = ("cl100k_base", "o200k_base")
_ROLE = re.compile(r"^(?:USER|ASSISTANT|SYSTEM|DEVELOPER|TOOL):[ \t]*")
_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_SENTENCE = re.compile(r"[。！？]|[.!?](?=\s|$)")


@lru_cache(maxsize=2)
def _encoding(name: str):
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError('Exact token budgets require the tokens extra; from a source checkout run: pip install -e ".[tokens]"') from exc
    return tiktoken.get_encoding(name), tiktoken.__version__


class _PrefixTokenCounter:
    """An exact append counter with a conservative nonnegative lower bound."""

    __slots__ = ("minimum_tokens", "_count", "_prefix")

    def __init__(self, count: Callable[[str], int], prefix: str,
                 minimum_tokens: int = 0):
        self.minimum_tokens = minimum_tokens
        self._count = count
        self._prefix = prefix

    def __call__(self, text: str) -> int:
        return self.minimum_tokens + self._count(self._prefix + text)


class TokenCounter:
    def __init__(self, name: str):
        if not isinstance(name, str) or name not in TOKENIZERS:
            raise ValueError("tokenizer must be cl100k_base or o200k_base")
        self.name = name
        self.encoding, self.version = _encoding(name)

    def count(self, text: str) -> int:
        # Historical text may literally contain <|endoftext|> or similar
        # strings. They are evidence, not privileged tokenizer control tokens.
        return len(self.encoding.encode_ordinary(text))

    def count_after(self, prefix: str) -> _PrefixTokenCounter:
        """Count appended text exactly without encoding the stable prefix again.

        Token counts are not generally additive: an appended character can
        change a token at the boundary. Ask the pinned tokenizer for its stable
        prefix, and re-encode its remaining suffix together with each candidate.
        This cache lives for one page's fit checks, never across recall calls.
        Its minimum_tokens counts only certified stable tokens; fallback paths
        expose zero, since a full prefix's token count is not a safe bound.
        """
        stable, _ = self.encoding.encode_with_unstable(prefix, disallowed_special=())
        prefix_bytes = prefix.encode("utf-8")
        stable_bytes = self.encoding.decode_bytes(stable)
        # The stable API promises a byte prefix, but keep a conservative full
        # count fallback if a future tokenizer returns a partial code point.
        try:
            tail = prefix_bytes[len(stable_bytes):].decode("utf-8")
        except UnicodeDecodeError:
            return _PrefixTokenCounter(self.count, prefix)
        if not prefix_bytes.startswith(stable_bytes):
            return _PrefixTokenCounter(self.count, prefix)
        stable_count = len(stable)
        return _PrefixTokenCounter(self.count, tail, stable_count)


def source_units(text: str) -> list[tuple[int, int]]:
    """Find intact source lines/sentences and atomic closed fenced blocks.

    Parse the original turn, before projecting into pages. A page boundary may
    fall inside a sentence or a code block; such partial units are not offered
    as new evidence. Role prefixes are recognized only on opening fences.
    Inside a fence, ``USER: ``` `` is ordinary code and cannot close the fence.
    Unclosed fenced blocks are not offered as supplemental units.
    """
    primary: list[tuple[int, int]] = []
    sentences: list[tuple[int, int]] = []
    offset = 0
    fence: tuple[str, int, int] | None = None
    for line in text.splitlines(keepends=True):
        value = line.rstrip("\r\n")
        lo, hi = offset, offset + len(value)
        offset += len(line)
        if fence is not None:
            character, size, start = fence
            if re.fullmatch(r"[ \t]{0,3}" + re.escape(character) + "{" + str(size) + r",}[ \t]*", value):
                primary.append((start, hi))
                fence = None
            continue
        opening = _OPEN.fullmatch(_ROLE.sub("", value, count=1))
        if opening and (opening[1][0] != "`" or "`" not in opening[2]):
            fence = (opening[1][0], len(opening[1]), lo)
            continue
        if not value.strip():
            continue
        start = lo + len(value) - len(value.lstrip())
        end = hi - len(value) + len(value.rstrip())
        primary.append((start, end))
        cursor = start
        for match in _SENTENCE.finditer(text[start:end]):
            stop = start + match.end()
            if cursor < stop:
                sentences.append((cursor, stop))
            cursor = stop
            while cursor < end and text[cursor].isspace():
                cursor += 1
        if cursor < end:
            sentences.append((cursor, end))
    # Neighbouring utterances can supply a question's answer or qualification.
    # Preserve all intervening bytes, including whitespace, rather than joining
    # source sentences into a new assertion.
    spans = set(primary + sentences)
    for i, (start, _) in enumerate(primary):
        for j in range(i + 1, min(i + 3, len(primary))):
            spans.add((start, primary[j][1]))
    if fence is None and text:
        spans.add((0, len(text)))
    return sorted(spans)


def projected_units(row: dict[str, Any], turns: dict[tuple[str, int], str],
                    unit_cache: dict[tuple[str, int], list[tuple[int, int]]]) -> list[tuple[int, int]]:
    """Project complete original-turn units through the page's source map."""
    import json

    return _projected_units(row, turns, unit_cache, json.loads(row["source_refs"]))


def _projected_units(row: dict[str, Any], turns: dict[tuple[str, int], str],
                     unit_cache: dict[tuple[str, int], list[tuple[int, int]]],
                     refs: list[dict]) -> list[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for ref in refs:
        key = (row["session_pk"], ref["turn_index"])
        original = turns[key]
        if key not in unit_cache:
            unit_cache[key] = source_units(original)
        units = unit_cache[key]
        # Units are sorted by (start, end). A start outside this source segment
        # cannot be contained in it; nested units still need the end check.
        # Retain the original comparisons for malformed noninteger maps.
        if isinstance(ref.get("turn_start"), int) and isinstance(ref.get("turn_end"), int):
            first = bisect_left(units, (ref["turn_start"],))
            stop = bisect_left(units, (ref["turn_end"],))
            candidates = (units[i] for i in range(first, stop))
        else:
            candidates = iter(units)
        for start, end in candidates:
            if ref["turn_start"] <= start < end <= ref["turn_end"]:
                lo = ref["start"] + start - ref["turn_start"]
                hi = ref["start"] + end - ref["turn_start"]
                if row["content"][lo:hi] != original[start:end]:
                    raise ValueError("Page source coordinates do not match the original turn")
                spans.add((lo, hi))
    return sorted(spans)


def _source_map_matches(row: dict[str, Any], turns: dict[tuple[str, int], str],
                        refs: list[dict]) -> bool:
    """Affirm that every possible projected unit must match its source.

    This is a sufficient certificate, not a replacement corruption policy.
    Uncertified maps use the old unit-by-unit validation, including maps where
    a difference falls only in a partial sentence or an unfinished fence.
    """
    content = row["content"]
    for ref in refs:
        original = turns.get((row["session_pk"], ref["turn_index"]))
        start, end = ref.get("start"), ref.get("end")
        turn_start, turn_end = ref.get("turn_start"), ref.get("turn_end")
        if (original is None or
                not all(isinstance(value, int) for value in (start, end, turn_start, turn_end)) or
                not (0 <= start <= end <= len(content) and 0 <= turn_start <= turn_end <= len(original)) or
                end - start != turn_end - turn_start or
                content[start:end] != original[turn_start:turn_end]):
            return False
    return True


def prepare_source_units(pages: list[dict], turns: dict[tuple[str, int], str],
                         refs_by_page: dict[str, list[dict]]) -> Callable[[dict], list[tuple[int, int]]]:
    """Validate captured source maps, then lazily project immutable turn text.

    Call this under the recall read snapshot. Uncertified maps retain eager
    projection and its historical errors. Certified pages need no parsing
    until packing requests supplemental evidence; the resolver never reads
    the database and all its caches live for this recall only.
    """
    unit_cache: dict[tuple[str, int], list[tuple[int, int]]] = {}
    prepared: dict[str, list[tuple[int, int]]] = {}
    for row in pages:
        refs = refs_by_page[row["id"]]
        if not _source_map_matches(row, turns, refs):
            prepared[row["id"]] = _projected_units(row, turns, unit_cache, refs)

    def resolve(row: dict) -> list[tuple[int, int]]:
        identity = row["id"]
        if identity not in prepared:
            prepared[identity] = _projected_units(row, turns, unit_cache, refs_by_page[identity])
        return prepared[identity]

    return resolve


def _render(text: str, start: int, end: int) -> str:
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def assemble(
    legacy: list[tuple[dict, str, str, list[tuple[int, int]]]],
    pages: list[dict],
    query_terms: list[str],
    *,
    budget_chars: int,
    budget_tokens: int,
    counter: TokenCounter,
) -> list[tuple[dict, str, str, list[tuple[int, int]]]]:
    """Keep rank-order first-fit legacy blocks, then add intact source units.

    Baseline blocks that fit are immutable. Supplemental evidence comes only
    from the same top-limit pages, with at most one result per page. Exact full
    context counts include citation headers and separators at every acceptance.
    Candidate selection uses source/query text only, never answer labels.
    """
    return assemble_with_count(legacy, pages, query_terms, budget_chars=budget_chars,
                               budget_tokens=budget_tokens, counter=counter)[0]


def assemble_with_count(
    legacy: list[tuple[dict, str, str, list[tuple[int, int]]]],
    pages: list[dict],
    query_terms: list[str],
    *,
    budget_chars: int,
    budget_tokens: int,
    counter: TokenCounter,
    source_units_for: Callable[[dict], list[tuple[int, int]]] | None = None,
) -> tuple[list[tuple[dict, str, str, list[tuple[int, int]]]], int]:
    """Pack exactly as ``assemble`` and retain the last accepted token count."""
    kept: list[tuple[dict, str, str, list[tuple[int, int]]]] = []
    blocks: list[str] = []
    seen: set[str] = set()
    term_cache: dict[str, set[str]] = {}
    accepted_tokens = 0

    def fitting_count(block: str) -> int | None:
        proposed = "\n\n".join([*blocks, block])
        if len(proposed) > budget_chars:
            return None
        count = counter.count(proposed)
        return count if count <= budget_tokens else None

    for entry in legacy:
        row, header, text, _ = entry
        count = fitting_count(header + text) if text else None
        if count is not None:
            kept.append(entry)
            blocks.append(header + text)
            seen.add(row["id"])
            accepted_tokens = count
    if budget_tokens == 0:
        return kept, accepted_tokens

    for row in pages:
        if row["id"] in seen:
            continue
        header = f'[{row["id"]}] {row["project_id"]} / {row["session_id"]} | {row["created_at"]}\n'
        remaining_chars = budget_chars - sum(map(len, blocks)) - 2 * len(blocks) - len(header)
        if remaining_chars <= 0:
            continue
        qset = set(row.get("excerpt_terms", query_terms))
        choices = []
        units = source_units_for(row) if source_units_for is not None else row.get("token_source_units", [])
        for start, end in units:
            text = _render(row["content"], start, end)
            if len(text) > remaining_chars:
                continue
            if text not in term_cache:
                term_cache[text] = set(terms(text, query=True))
            overlap = len(qset.intersection(term_cache[text]))
            choices.append((overlap, end - start, start, end, text))
        # Prefer the most relevant complete span, then retain as much of its
        # original surrounding evidence as fits. Bound expensive tokenization.
        choices.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
        if not choices:
            continue
        prefix = "\n\n".join([*blocks, header])
        count_after_prefix = None
        for index, (_, _, start, end, text) in enumerate(choices[:96]):
            # Character fit was checked above. Preserve the exact full-context
            # token boundary while avoiding repeated work on accepted blocks.
            # A first-choice success needs one ordinary encode. Prepare reusable
            # tokens only after rejection, when several fit checks remain.
            if index == 1 and len(choices) > 3:
                count_after_prefix = counter.count_after(prefix)
                # Every remaining prepared count adds a nonnegative suffix.
                # Preserve the first full count and existing lazy setup rule.
                if count_after_prefix.minimum_tokens > budget_tokens:
                    break
            count = (count_after_prefix(text) if count_after_prefix is not None
                     else counter.count(prefix + text))
            if count <= budget_tokens:
                kept.append((row, header, text, [(start, end)]))
                blocks.append(header + text)
                seen.add(row["id"])
                accepted_tokens = count
                break
    return kept, accepted_tokens
