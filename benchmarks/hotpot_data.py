"""Externally authored HotpotQA transfer cohort with source-only indexing.

The public manifest freezes original IDs and source hashes before scoring.
Original questions/answers and encyclopedia text are downloaded separately.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from benchmarks.data import Dataset, Evidence, QueryCase


MANIFEST = Path(__file__).with_name("hotpot_manifest.json")
SELECTION_PREFIX = "memory-book-transfer-v1:"
REPRESENTATION = "original-sentences-v2"


@dataclass
class HotpotDataset(Dataset):
    provenance: dict = field(default_factory=dict)

    def description(self):
        result = super().description()
        result.update(kind="public", version="hotpot-transfer-2", provenance=self.provenance)
        return result


def selected_ids(items, count=128):
    ids = [item["_id"] for item in items]
    if not all(isinstance(identity, str) and identity for identity in ids) or len(ids) != len(set(ids)):
        raise ValueError("HotpotQA IDs must be unique nonempty strings")
    if len(ids) < count:
        raise ValueError("Not enough HotpotQA questions for the frozen cohort")
    return sorted(ids, key=lambda identity: hashlib.sha256((SELECTION_PREFIX + identity).encode()).hexdigest())[:count]


def convert_hotpot(items, ids, provenance=None):
    mapping = {item["_id"]: item for item in items}
    if len(mapping) != len(items) or len(ids) != len(set(ids)) or set(ids) - mapping.keys():
        raise ValueError("Invalid source or selected HotpotQA IDs")
    dataset = HotpotDataset(seed=20261112, split="heldout", variant="hotpot_external_transfer_v2")
    for identity in ids:
        item = mapping[identity]
        project = "hotpot-" + identity
        articles = {}
        for index, (title, sentences) in enumerate(item["context"]):
            if title in articles or not isinstance(title, str) or not title:
                raise ValueError("Paragraph titles must be unique within each problem")
            if not sentences or any(not isinstance(sentence, str) for sentence in sentences):
                raise ValueError("Paragraphs need original sentence strings")
            sid = f"{identity}-article-{index}"
            articles[title] = (sid, sentences)
            # Every original sentence becomes one canonical turn, uniformly
            # for supporting and distractor articles. This preserves source
            # sentence boundaries without consulting labels or query results.
            dataset.sessions.append({"project": project, "session_id": sid,
                "title": title, "task_id": f"article-{index}", "task_title": title,
                "created_at": "2000-01-01T00:00:00Z",
                "messages": [{"role": "user", "content": sentence} for sentence in sentences]})
        required = []
        for title, index in item["supporting_facts"]:
            if title not in articles or type(index) is not int:
                raise ValueError("Supporting fact refers to an absent article or invalid sentence index")
            sid, sentences = articles[title]
            if not 0 <= index < len(sentences) or not sentences[index].strip():
                raise ValueError("Supporting fact refers to an absent/empty sentence")
            evidence = Evidence(sid, index, sentences[index])
            if evidence not in required:
                required.append(evidence)
        if not required:
            raise ValueError("Each selected question needs supporting-fact labels")
        dataset.queries.append(QueryCase(identity, item["question"], "hotpot_" + item["type"],
                                         project, tuple(required), answerable=True))
    dataset.provenance = {**(provenance or {}), "selection": SELECTION_PREFIX + " SHA-256 ascending",
        "selected_ids": ids, "selected_queries": len(ids),
        "representation": REPRESENTATION,
        "indexing": "every supplied paragraph in its own chapter/session; every original sentence is one canonical user turn; one project per problem; no query or QA labels indexed",
        "date_convention": "fixed synthetic date for neutral ordering; not article publication dates",
        "limits": ["Externally authored encyclopedia multi-hop QA, not user conversation memory.",
                   "Scoped distractor setting; all supplied contexts indexed, not full Wikipedia retrieval.",
                   "All cases are answerable; this cohort does not measure abstention.",
                   "Strict complete-sentence evidence metric may be unattainable when a sentence crosses a canonical page boundary; report preflight failures without dropping cases.",
                   "After first evaluation these IDs become regression data."]}
    return dataset


def load_hotpot(path: Path):
    manifest = json.loads(MANIFEST.read_text())
    raw = path.read_bytes()
    if len(raw) != manifest["canonical_bytes"] or hashlib.sha256(raw).hexdigest() != manifest["canonical_sha256"]:
        raise ValueError("HotpotQA file differs from frozen canonical source")
    items = json.loads(raw)
    ids = selected_ids(items, manifest["expected_queries"])
    if ids != manifest["selected_ids"]:
        raise ValueError("HotpotQA selected IDs differ from the preregistered ordering")
    return convert_hotpot(items, ids, {key: manifest[key] for key in
        ("dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--answer-cases", type=Path, help="Optional private paired-answer input, contains licensed source text")
    args = parser.parse_args()
    dataset = load_hotpot(args.path)
    print(json.dumps(dataset.description(), ensure_ascii=False))
    if args.answer_cases:
        items = {item["_id"]: item for item in json.loads(args.path.read_bytes())}
        payload = {"sessions": dataset.sessions, "queries": [{"id": case.id, "query": case.query,
            "project": case.project, "answerable": True, "answers": [str(items[case.id]["answer"])],
            "category": case.category} for case in dataset.queries], "provenance": dataset.provenance}
        args.answer_cases.parent.mkdir(parents=True, exist_ok=True)
        with args.answer_cases.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
