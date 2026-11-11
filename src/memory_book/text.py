"""Shared lexical analysis, conservative size accounting, and extractive excerpts.

FTS receives pre-tokenized text. CJK bigrams make Chinese searchable without an
external segmenter; they are lexical features, not semantic embeddings.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from itertools import islice

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
RUNS = re.compile(rf"[{CJK}]+|[^\W_{CJK}]+(?:[_./:-][^\W_{CJK}]+)*", re.UNICODE)
CJK_RUN = re.compile(rf"^[{CJK}]+$")
STOP = frozenset("a an the is are was were be been to of in on at for from and or it this that these those with as by what which who when where why how do does did can could would should please tell me we our you your i my about now current latest final s t re ve ll d m".split())
ZH_STOP = frozenset("什么 怎么 如何 为什么 哪个 哪些 是否 现在 当前 最后 最终 我们 这个 那个 一个 一下 请问 告诉 多少 了吗 的是 是什 么的 如何 何时 怎样".split())


def terms(text: str, *, query: bool = False) -> list[str]:
    """NFKC text -> English words/identifier pieces and Chinese bigrams."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).casefold()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if unicodedata.category(c) != "Mn")
    if query:
        # Remove complete Chinese question phrases before bigramming; otherwise
        # 为什么 leaves the meaningless fragment 为什 as a retrieval feature.
        text = re.sub(r"为什么|请告诉我|请问|是什么|什么|怎么样|怎么|如何|多少|哪些|哪个|是否", " ", text)
    result: list[str] = []
    for match in RUNS.finditer(text):
        value = match.group()
        if CJK_RUN.fullmatch(value):
            parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
            result.extend(p for p in parts if not query or p not in ZH_STOP)
        else:
            parts = re.split(r"[_./:-]+", value)
            # Indexed identifiers share the same split with queries; FTS syntax is
            # never passed through, even for user input containing quotes or OR.
            result.extend(p for p in parts if p and (not query or p not in STOP))
    return result


def index_text(text: str) -> str:
    return " ".join(terms(text))


def query_terms(text: str) -> list[str]:
    # Bound SQL expression complexity and preserve repeated-word neutrality.
    return list(dict.fromkeys(terms(text, query=True)))[:64]


def estimate_tokens(text: str) -> int:
    """Size heuristic only. Never presented as a model tokenizer's exact count."""
    cjk = sum(bool(CJK_RUN.fullmatch(c)) for c in text)
    return cjk + math.ceil((len(text) - cjk) / 4)


def headline(text: str, limit: int = 88) -> str:
    clean = " ".join(text.split())
    return clean[:limit].rstrip() + ("…" if len(clean) > limit else "")


def similarity(left: str, right: str) -> float:
    a, b = set(terms(left, query=True)), set(terms(right, query=True))
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def is_followup(question: str) -> bool:
    q = question.strip().casefold()
    return bool(re.match(r"^(那|它|这个|这项|该|继续|还有|为什么|那么|是否|可以|再|and\b|what about\b|why\b|how about\b|then\b|that\b|it\b|can we\b)", q))


def excerpt(text: str, query: str, max_chars: int) -> tuple[str, list[tuple[int, int]]]:
    """Return one bounded original-text window and exact character offsets.

    Every segmentation baseline uses the same function. Whole-session baselines
    therefore get relevance-centered windows, not a deliberately weak prefix.
    """
    if max_chars <= 0:
        return "", []
    if len(text) <= max_chars:
        return text, [(0, len(text))]
    if max_chars < 8:
        return text[:max_chars], [(0, max_chars)]
    width = max_chars - 2  # reserve potential leading and trailing ellipses
    q = query_terms(query)
    # Keep a source map through accent folding and expansions such as ß -> ss.
    folded, source_positions = [], []
    for index, character in enumerate(text):
        piece = "".join(c for c in unicodedata.normalize("NFKD", character).casefold() if unicodedata.category(c) != "Mn")
        folded.append(piece)
        source_positions.extend([index] * len(piece))
    lower = "".join(folded)
    positions: list[tuple[int, str]] = []
    for term in q:
        for match in islice(re.finditer(re.escape(term), lower), 40):
            positions.append((source_positions[match.start()], term))
    starts = {0, max(0, len(text) - width)}
    for pos, _ in positions:
        starts.add(max(0, min(len(text) - width, pos - width // 3)))
    best_start, best_score = 0, (-1.0, -1)
    for start in sorted(starts):
        inside = Counter(t for p, t in positions if start <= p < start + width)
        score = (sum(1 + math.log1p(n) * 0.08 for n in inside.values()), -start)
        if score > best_score:
            best_start, best_score = start, score
    end = min(len(text), best_start + width)
    return ("…" if best_start else "") + text[best_start:end] + ("…" if end < len(text) else ""), [(best_start, end)]
