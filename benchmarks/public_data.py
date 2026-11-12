"""Read an externally downloaded, pinned LoCoMo corpus without redistributing it.

The dataset's CC BY-NC 4.0 license is separate from this repository's MIT code
license. Our published reports contain aggregate metrics and source IDs only.
This adapter measures full annotated text-evidence retrieval, not the original
benchmark's generated-answer accuracy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from benchmarks.data import Dataset, Evidence, QueryCase


MANIFEST = Path(__file__).with_name("locomo_split.json")
IMAGE_KEYS = frozenset({"img_url", "image_url", "image", "blip_caption"})


@dataclass
class PublicDataset(Dataset):
    provenance: dict = field(default_factory=dict)

    def description(self) -> dict:
        description = super().description()
        description.update(kind="public", version="locomo-text-evidence-1.0",
                           provenance=self.provenance)
        return description


def convert_locomo(items: list[dict], *, sample_ids: list[str], split: str,
                   max_queries: int = 0, source_metadata: dict | None = None) -> PublicDataset:
    """Convert a selected conversation split; injectable for tiny synthetic tests.

    Dialogue utterances are indexed as individual canonical user-role turns
    with their original speaker names. No answers, event summaries, observations,
    image captions, or dataset evidence labels enter the retrieval corpus.
    """
    if split not in {"development", "heldout"} or max_queries < 0:
        raise ValueError("Invalid split or query limit")
    by_id = {item["sample_id"]: item for item in items}
    if len(by_id) != len(items) or len(set(sample_ids)) != len(sample_ids):
        raise ValueError("Conversation identifiers must be unique")
    if set(sample_ids) - by_id.keys():
        raise ValueError("A frozen conversation ID is absent from the dataset")
    dataset = PublicDataset(seed=20261111, split=split, variant="locomo_text_evidence_v1")
    excluded, category_counts = Counter(), Counter()
    total_queries = 0
    for sample_id in sample_ids:
        item = by_id[sample_id]
        conversation = item["conversation"]
        project = f"locomo-{sample_id}"
        dialogue = {}
        sessions = sorted((key for key, value in conversation.items()
                           if key.startswith("session_") and isinstance(value, list)),
                          key=lambda value: int(value.split("_")[1]))
        for name in sessions:
            session_id = f"{sample_id}-{name}"
            # The source provides a local date/time without a timezone. UTC is
            # a deterministic indexing convention, not a claim about its zone.
            date_text = conversation[f"{name}_date_time"]
            created = datetime.strptime(date_text, "%I:%M %p on %d %B, %Y").replace(tzinfo=timezone.utc)
            messages = []
            for turn_index, entry in enumerate(conversation[name]):
                dia_id, text = entry["dia_id"], entry["text"]
                if dia_id in dialogue:
                    raise ValueError("Duplicate dialogue ID within a conversation")
                dialogue[dia_id] = (session_id, turn_index, text,
                                     bool(IMAGE_KEYS.intersection(entry)))
                messages.append({"role": "user", "content": f"{entry['speaker']}: {text}"})
            dataset.sessions.append({"project": project, "session_id": session_id,
                                     "title": f"{sample_id} {name}", "task_id": "conversation",
                                     "task_title": "Conversation", "created_at": created.isoformat(),
                                     "messages": messages})
        for index, qa in enumerate(item["qa"]):
            total_queries += 1
            category = int(qa["category"])
            category_counts[str(category)] += 1
            qid = f"{sample_id}-q{index:04d}"
            if category == 5:
                # Category 5 is the source benchmark's unanswerable category.
                # Retrieval nonemptiness is diagnostic, not model hallucination.
                dataset.queries.append(QueryCase(qid, qa["question"], "locomo_category_5",
                                                  project, answerable=False))
                continue
            evidence_ids = list(dict.fromkeys(qa.get("evidence", [])))
            if not evidence_ids:
                excluded["missing_evidence"] += 1
                continue
            if any(dia_id not in dialogue for dia_id in evidence_ids):
                excluded["invalid_evidence_id"] += 1
                continue
            if any(dialogue[dia_id][3] for dia_id in evidence_ids):
                excluded["image_bearing_evidence"] += 1
                continue
            required = tuple(Evidence(*dialogue[dia_id][:3]) for dia_id in evidence_ids)
            if any(not evidence.needle for evidence in required):
                excluded["empty_evidence_text"] += 1
                continue
            dataset.queries.append(QueryCase(qid, qa["question"], f"locomo_category_{category}",
                                              project, required))
    eligible_count = len(dataset.queries)
    dataset.queries.sort(key=lambda case: hashlib.sha256(
        ("locomo-query-order-v1:" + case.id).encode()).hexdigest())
    if max_queries:
        dataset.queries = dataset.queries[:max_queries]
    dataset.provenance = {**(source_metadata or {}), "sample_ids": sample_ids,
                          "all_qa_in_split": total_queries, "all_qa_categories": dict(category_counts),
                          "eligible_qa_in_split": eligible_count, "selected_queries": len(dataset.queries),
                          "max_queries": max_queries, "excluded_qa": dict(sorted(excluded.items())),
                          "selection": "sha256(locomo-query-order-v1: + query_id) ascending",
                          "evidence_metric": "complete annotated utterance text and original source span",
                          "indexing": "one dialogue utterance per canonical user-role turn; speaker prefix; text only",
                          "date_time_convention": "source local clock represented as UTC for deterministic ordering"}
    return dataset


def load_locomo(path: Path, *, split: str = "heldout", max_queries: int = 0) -> PublicDataset:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if len(raw) != manifest["bytes"] or hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
        raise ValueError("LoCoMo data does not match the pinned file SHA-256 and size")
    if split not in {"development", "heldout"}:
        raise ValueError("Unknown conversation split")
    metadata = {key: manifest[key] for key in
                ("dataset", "repository", "commit", "url", "sha256", "bytes", "license", "license_url", "split_seed")}
    return convert_locomo(json.loads(raw), sample_ids=manifest[split], split=split,
                          max_queries=max_queries, source_metadata=metadata)
