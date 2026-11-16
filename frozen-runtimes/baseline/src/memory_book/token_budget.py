"""Optional exact context budgeting, preserving already deliverable evidence.

Only the caller's explicitly selected tokenizer is used. This module never
substitutes a character estimate for an exact count and never generates facts.
"""

from __future__ import annotations

import hashlib
import re
import sys
from bisect import bisect_left
from collections import OrderedDict
from functools import lru_cache
from typing import Any, Callable

from .text import terms

TOKENIZERS = ("cl100k_base", "o200k_base")
_SEALED_PATTERNS = {
    "cl100k_base": "f021c3d976978e62ee64cdad150cc3405c2e3d6e3b40407850bb9e8d9eb65899",
    "o200k_base": "2d1b8dc11e89af71459b36004f698ab3693f59fd84f63e8ec2b49564ab857420",
}
_ENCODER_METHOD_NAMES = ("encode_ordinary", "encode_with_unstable", "decode_bytes")
_ORDINARY_ENCODER_METHODS: tuple | None = None
_ENCODING_ORIGINS: dict[str, tuple] = {}
_ROLE = re.compile(r"^(?:USER|ASSISTANT|SYSTEM|DEVELOPER|TOOL):[ \t]*")
_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_SENTENCE = re.compile(r"[。！？]|[.!?](?=\s|$)")


def _trusted_encoder_methods(tiktoken) -> tuple | None:
    """Recognize the installed implementation before retaining identities.

    A method replaced before the first TokenCounter is still a custom method.
    functools.wraps can copy its public name/module, but not the code's actual
    name and source origin. Unknown or unavailable origins use full counting.
    Deliberately forged package code/private metadata is outside this contract.
    """
    from pathlib import Path
    from types import FunctionType
    try:
        from tiktoken import core
        module_file = getattr(core, "__file__", None)
        if (not isinstance(module_file, str) or not module_file
                or tiktoken.Encoding is not core.Encoding
                or tiktoken.Encoding.__module__ != "tiktoken.core"):
            return None
        origin = Path(module_file).resolve()
        if not origin.is_file():
            return None
        methods = tuple(getattr(tiktoken.Encoding, name, None) for name in _ENCODER_METHOD_NAMES)
        for name, method in zip(_ENCODER_METHOD_NAMES, methods):
            if (type(method) is not FunctionType or method.__module__ != "tiktoken.core"
                    or method.__name__ != name or method.__qualname__ != "Encoding." + name
                    or method.__code__.co_name != name
                    or Path(method.__code__.co_filename).resolve() != origin):
                return None
        return methods
    except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None


@lru_cache(maxsize=2)
def _encoding(name: str):
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError('Exact token budgets require the tokens extra; from a source checkout run: pip install -e ".[tokens]"') from exc
    global _ORDINARY_ENCODER_METHODS
    if _ORDINARY_ENCODER_METHODS is None:
        # Validate origin before the initial capture; later overrides must
        # also retain these exact identities to use the sealed certificate.
        _ORDINARY_ENCODER_METHODS = _trusted_encoder_methods(tiktoken)
    encoding = tiktoken.get_encoding(name)
    version = tiktoken.__version__
    certified = None
    try:
        from tiktoken import _tiktoken
        if name in TOKENIZERS and type(encoding) is tiktoken.Encoding:
            core = getattr(encoding, "_core_bpe", None)
            if type(core) is _tiktoken.CoreBPE:
                # At most one original pair per registered name. Clearing the
                # loader must not recertify a replaced private core merely
                # because stale Python pattern/name metadata still look normal.
                original = _ENCODING_ORIGINS.setdefault(name, (encoding, core))
                certified = core if original[0] is encoding and original[1] is core else None
    except Exception:
        # Optional implementation inspection must not break a custom encoder's
        # existing public exact-count path. Actual encode errors still propagate.
        pass
    return encoding, version, certified


class _ExactTokenMemo:
    """Connection-owned exact counts; plain text, not query/result entries."""

    def __init__(self):
        self.entry_limit, self.text_byte_limit = 2048, 2097152
        self.entries = OrderedDict()
        self.identities = {}
        self.text_bytes = 0
        self.hits = self.misses = self.evictions = self.invalidations = 0
        self.oversized_bypasses = self.uncertified_bypasses = 0

    def clear(self):
        self.entries.clear()
        self.identities.clear()
        self.text_bytes = 0

    def invalidate(self):
        if self.entries or self.identities:
            self.invalidations += 1
            self.clear()

    def lookup(self, identity, text):
        name, encoding, core = identity
        previous = self.identities.get(name)
        if previous is not None and (previous[0] is not encoding or previous[1] is not core):
            self.invalidate()
        # At most the two registered names, one current object pair each.
        self.identities[name] = (encoding, core)
        key = (name, text)
        value = self.entries.get(key)
        if value is None:
            self.misses += 1
            return None
        self.entries.move_to_end(key)
        self.hits += 1
        return value[0]

    def store(self, identity, text, count):
        # Encoding may allocate a UTF-8 side buffer on a Unicode str. Charge
        # the retained object only after the successful ordinary encode.
        size = sys.getsizeof(text)
        if size > self.text_byte_limit:
            self.oversized_bypasses += 1
            return
        while self.entries and (len(self.entries) >= self.entry_limit or
                                self.text_bytes + size > self.text_byte_limit):
            _, (_, old_size) = self.entries.popitem(last=False)
            self.text_bytes -= old_size
            self.evictions += 1
        self.entries[(identity[0], text)] = (count, size)
        self.text_bytes += size

    def snapshot(self):
        return {"allocated": 1, "entry_limit": self.entry_limit, "text_byte_limit": self.text_byte_limit,
                "entries": len(self.entries), "text_bytes": self.text_bytes,
                **{name: getattr(self, name) for name in ("hits", "misses", "evictions", "invalidations",
                    "oversized_bypasses", "uncertified_bypasses")}}


def _attach_count_memo(counter, memo):
    if type(counter) is _ORDINARY_COUNTER_TYPE:
        counter._memo = memo
        # An immutable pattern identity avoids rehashing the same approved
        # pattern for every block; mutable implementation identities remain
        # checked on each lookup and again after a miss is encoded.
        counter._memo_pattern = None
        if _can_seal_blocks(counter):
            counter._memo_pattern = getattr(counter.encoding, "_pat_str", None)


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
        self.encoding, self.version, self._certified_core = _encoding(name)
        self._certified_encoding, self._certified_name = self.encoding, name
        self._memo = None
        self._memo_pattern = None

    def count(self, text: str) -> int:
        # Historical text may literally contain <|endoftext|> or similar
        # strings. They are evidence, not privileged tokenizer control tokens.
        memo = getattr(self, "_memo", None)
        if memo is not None:
            previous = memo.identities.get(getattr(self, "name", None))
            if previous is not None and (previous[0] is not self.encoding or
                    previous[1] is not getattr(self.encoding, "_core_bpe", None)):
                memo.invalidate()
            # Do not invoke overridden str hashing, slicing or sizeof methods.
            eligible = type(text) is str and text.startswith("[")
            newline = text.find("\n") if eligible else -1
            eligible = eligible and 0 <= newline < len(text) - 1
            identity = _memo_identity(self) if eligible else None
            if identity is not None:
                known = memo.lookup(identity, text)
                if known is not None:  # Zero is a valid exact count.
                    return known
                count = len(self.encoding.encode_ordinary(text))
                after = _memo_identity(self)
                if (after is not None and after[0] == identity[0]
                        and after[1] is identity[1] and after[2] is identity[2]):
                    memo.store(identity, text, count)
                else:
                    memo.invalidate()
                return count
            memo.uncertified_bypasses += 1
            if eligible:
                memo.invalidate()
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


# Retain the ordinary methods themselves: subclasses and monkeypatched test or
# application counters keep their historical complete-context calls.
_ORDINARY_COUNT = TokenCounter.count
_ORDINARY_COUNT_AFTER = TokenCounter.count_after
_ORDINARY_COUNTER_TYPE = TokenCounter


def _ordinary_encoding(counter: TokenCounter):
    if (type(counter) is not _ORDINARY_COUNTER_TYPE
            or getattr(counter.count, "__func__", None) is not _ORDINARY_COUNT
            or getattr(counter.count, "__self__", None) is not counter
            or getattr(counter.count_after, "__func__", None) is not _ORDINARY_COUNT_AFTER
            or getattr(counter.count_after, "__self__", None) is not counter
            or getattr(counter, "version", None) != "0.12.0"):
        return None
    import tiktoken
    encoding = getattr(counter, "encoding", None)
    name = getattr(counter, "name", None)
    if (tiktoken.__version__ != "0.12.0" or type(encoding) is not tiktoken.Encoding
            or name not in _SEALED_PATTERNS or getattr(encoding, "name", None) != name
            or encoding is not getattr(counter, "_certified_encoding", None)
            or name != getattr(counter, "_certified_name", None)
            or getattr(encoding, "_core_bpe", None) is not getattr(counter, "_certified_core", None)
            or getattr(counter, "_certified_core", None) is None):
        return None
    if _ORDINARY_ENCODER_METHODS is None:
        return None
    for method, ordinary in zip(_ENCODER_METHOD_NAMES, _ORDINARY_ENCODER_METHODS):
        actual = getattr(encoding, method, None)
        if (getattr(actual, "__func__", None) is not ordinary
                or getattr(actual, "__self__", None) is not encoding):
            return None
    return encoding


def _memo_identity(counter: TokenCounter):
    encoding = _ordinary_encoding(counter)
    if (encoding is None or getattr(counter, "_memo_pattern", None) is None
            or getattr(encoding, "_pat_str", None) is not counter._memo_pattern):
        return None
    return counter.name, encoding, encoding._core_bpe


def _can_seal_blocks(counter: TokenCounter) -> bool:
    """Certify ordinary methods, the captured native core and inspected pattern.

    With these exact patterns, a piece ending in LF cannot consume the next
    '['. cl100k's EOF whitespace branch consumes the same bytes as its newline
    branch at this boundary. Replacing even a native core invalidates this
    certificate: its actual vocabulary/pattern need not match Python metadata.
    """
    encoding = _ordinary_encoding(counter)
    if encoding is None:
        return False
    name = counter.name
    pattern = getattr(encoding, "_pat_str", None)
    if not isinstance(pattern, str):
        return False
    try:
        return hashlib.sha256(pattern.encode("utf-8")).hexdigest() == _SEALED_PATTERNS[name]
    except UnicodeEncodeError:
        return False


def _ascii_sealing_suffix(block: str) -> str | None:
    """Find a small suffix separated from its prefix in both pinned patterns.

    After the last ASCII letter or digit, an all-ASCII punctuation/whitespace
    suffix cannot extend a preceding letter, number or contraction piece in
    either inspected tokenizer pattern. Appending two LF characters therefore
    changes only this suffix's pieces. Combining marks or other non-ASCII tail
    characters are deliberately uncertified. This helper is used only after
    the existing tokenizer/version/method-origin certificate has succeeded.
    """
    for offset in range(1, min(len(block), 65) + 1):
        character = block[-offset]
        if ("a" <= character <= "z" or "A" <= character <= "Z" or
                "0" <= character <= "9"):
            return block[len(block) - offset + 1:]
        if not character.isascii():
            return None
    return None


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


_ORDINARY_PREPARE_SOURCE_UNITS = prepare_source_units


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
    """Pack exactly as ``assemble`` with per-call certified prefix work reuse."""
    kept: list[tuple[dict, str, str, list[tuple[int, int]]]] = []
    blocks: list[str] = []
    block_token_counts: list[int | None] = []
    separator_deltas: dict[str, int] = {}
    seen: set[str] = set()
    term_cache: dict[str, set[str]] = {}
    accepted_tokens: int | None = 0
    accepted_prefix_tokens = 0
    block_chars = 0
    sealed_tokens, sealed_blocks = 0, 0
    can_seal = _can_seal_blocks(counter)

    def certified_bytes(header: str, block: str) -> int | None:
        nonlocal can_seal
        if can_seal:
            if header.startswith("["):
                try:
                    return len(block.encode("utf-8"))
                except UnicodeEncodeError:
                    pass
            # Stay on the old path for the remainder of this call. In
            # particular, a prior surrogate must still reach the original
            # count_after(full_prefix) error if that lazy path is requested.
            can_seal = False
        return None

    def prefix_tokens() -> int:
        nonlocal sealed_tokens, sealed_blocks
        # Only accepted blocks are sealed, once each, and only when needed by
        # a later candidate. Their counts include the exact two-LF separator.
        while sealed_blocks < len(blocks):
            block = blocks[sealed_blocks]
            known = block_token_counts[sealed_blocks]
            suffix = _ascii_sealing_suffix(block) if known is not None else None
            if suffix is None:
                sealed_tokens += counter.count(block + "\n\n")
            else:
                if suffix not in separator_deltas:
                    separator_deltas[suffix] = (counter.count(suffix + "\n\n") -
                                                counter.count(suffix))
                sealed_tokens += known + separator_deltas[suffix]
            sealed_blocks += 1
        return sealed_tokens

    def fitting_count(header: str, block: str) -> tuple[int | None, int] | None:
        if block_chars + 2 * len(blocks) + len(block) > budget_chars:
            return None
        byte_count = certified_bytes(header, block)
        if byte_count is not None:
            base = prefix_tokens()
            # Ordinary BPE tokens each represent at least one UTF-8 byte.
            # This sufficient acceptance bound never estimates final metadata.
            if base + byte_count <= budget_tokens:
                return None, base
            count = base + counter.count(block)
        else:
            base = 0
            count = counter.count("\n\n".join([*blocks, block]))
        return (count, base) if count <= budget_tokens else None

    def final_count() -> int:
        # A later rejection cannot replace this last accepted context/count.
        # When the byte bound accepted it, only its final unsealed block still
        # needs an exact encode; all preceding blocks have an exact certificate.
        if accepted_tokens is None:
            return accepted_prefix_tokens + counter.count(blocks[-1])
        return accepted_tokens

    for entry in legacy:
        row, header, text, _ = entry
        block = header + text if text else ""
        fit = fitting_count(header, block) if text else None
        if fit is not None:
            kept.append(entry)
            blocks.append(block)
            block_chars += len(block)
            seen.add(row["id"])
            accepted_tokens, accepted_prefix_tokens = fit
            block_token_counts.append(None if accepted_tokens is None else
                                      accepted_tokens - accepted_prefix_tokens)
    if budget_tokens == 0:
        return kept, final_count()

    for row in pages:
        if row["id"] in seen:
            continue
        header = f'[{row["id"]}] {row["project_id"]} / {row["session_id"]} | {row["created_at"]}\n'
        remaining_chars = budget_chars - block_chars - 2 * len(blocks) - len(header)
        if remaining_chars <= 0:
            continue
        if (can_seal and certified_bytes(header, header) is not None and
                _ascii_sealing_suffix(header) == "\n"):
            # The final ASCII letter/number piece is terminated by LF in both
            # certified patterns, even when arbitrary evidence follows it.
            # Count only that stable header prefix, not the trailing LF: the
            # latter may merge with a following whitespace/punctuation piece.
            # If this lower bound already exceeds the cap, no source unit can
            # fit and parsing/ranking every supplemental span is unnecessary.
            # Source-map validation has already run under the read snapshot.
            base = prefix_tokens()
            if base >= budget_tokens or base + counter.count(header[:-1]) > budget_tokens:
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
        byte_count = certified_bytes(header, header)
        base = prefix_tokens() if byte_count is not None else 0
        prefix = header if byte_count is not None else "\n\n".join([*blocks, header])
        count_after_prefix = None
        for index, (_, _, start, end, text) in enumerate(choices[:96]):
            # Character fit was checked above. Preserve the exact full-context
            # token boundary while avoiding repeated work on accepted blocks.
            # A first-choice success needs one ordinary encode. Prepare reusable
            # tokens only after rejection, when several fit checks remain.
            block = header + text
            was_sealed = can_seal
            byte_count = certified_bytes(header, block)
            restart_full_prefix = was_sealed and not can_seal
            if restart_full_prefix:
                # A later candidate can be the first invalid UTF-8 input.
                # Recreate the historical prefix counter if it was already
                # requested, instead of mixing a header-only suffix with it.
                base = 0
                prefix = "\n\n".join([*blocks, header])
                count_after_prefix = None
            if (index == 1 or (restart_full_prefix and index > 1)) and len(choices) > 3:
                count_after_prefix = counter.count_after(prefix)
                # Every remaining prepared count adds a nonnegative suffix.
                # Preserve the first full count and existing lazy setup rule.
                if base + count_after_prefix.minimum_tokens > budget_tokens:
                    break
            if byte_count is not None and base + byte_count <= budget_tokens:
                count = None  # Proved fit; exact final count remains lazy.
            else:
                count = base + (count_after_prefix(text) if count_after_prefix is not None
                                else counter.count(prefix + text))
            if count is None or count <= budget_tokens:
                kept.append((row, header, text, [(start, end)]))
                blocks.append(block)
                block_chars += len(block)
                seen.add(row["id"])
                accepted_tokens, accepted_prefix_tokens = count, base
                block_token_counts.append(None if count is None else count - base)
                break
    return kept, final_count()
