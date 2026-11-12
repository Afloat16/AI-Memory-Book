"""Freeze a new ID-only HotpotQA selection without displaying source questions."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from benchmarks.hotpot_data import convert_hotpot
from benchmarks.prepare_native_data import checked_download, normalize_hotpot

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/round2_plan.json"
MANIFEST = ROOT / "benchmarks/round2_hotpot256_manifest.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def select_ids(ids, excluded, prefix, count):
    if (len(ids) != len(set(ids)) or len(excluded) != len(set(excluded))
            or any(not isinstance(identity, str) or not identity for identity in ids)
            or set(excluded) - set(ids)):
        raise ValueError("Invalid source or exclusion IDs")
    eligible = set(ids) - set(excluded)
    if count <= 0 or len(eligible) < count:
        raise ValueError("Insufficient independent query IDs")
    return sorted(eligible, key=lambda identity: (hashlib.sha256((prefix + identity).encode()).hexdigest(), identity))[:count]


def source_spec():
    plan = json.loads(PLAN.read_bytes())
    original_path = ROOT / plan["cohort"]["source_manifest"]
    return plan, json.loads(original_path.read_bytes()), original_path


def prepare_data(directory):
    _, source, _ = source_spec()
    directory.mkdir(parents=True, exist_ok=True)
    parquet = directory / "hotpot-dev-distractor.parquet"
    checked_download(source["source_url"], parquet, source["upstream_sha256"], source["upstream_bytes"])
    import pyarrow.parquet as pq
    raw = normalize_hotpot(pq.read_table(parquet).to_pylist())
    if len(raw) != source["canonical_bytes"] or hashlib.sha256(raw).hexdigest() != source["canonical_sha256"]:
        raise ValueError("Canonical HotpotQA conversion differs from the fixed source")
    path = directory / "hotpot-dev-distractor.json"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("Existing private source differs; preserve it")
    if not path.exists():
        path.write_bytes(raw)
    return path


def convert(items, ids, plan, source):
    data = convert_hotpot(items, ids, {key: source[key] for key in
        ("dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})
    data.seed = plan["cohort"]["seed"]
    data.variant = "hotpot_round2_unseen_selection_v1"
    data.provenance.update(selection=plan["cohort"]["selection"],
        selection_prefix=plan["cohort"]["selection_prefix"], prior_selection_overlap=0,
        interpretation=plan["cohort"]["role"])
    return data


def read_source(path, source):
    raw = path.read_bytes()
    if len(raw) != source["canonical_bytes"] or hashlib.sha256(raw).hexdigest() != source["canonical_sha256"]:
        raise ValueError("Private source does not match the frozen canonical file")
    return json.loads(raw)


def freeze(path):
    if MANIFEST.exists():
        raise FileExistsError("The round2 cohort is already frozen; never overwrite it")
    plan, source, original_path = source_spec()
    items = read_source(path, source)
    ids = select_ids([item["_id"] for item in items], source["selected_ids"],
                     plan["cohort"]["selection_prefix"], plan["cohort"]["queries"])
    selected = {item["_id"]: item for item in items if item["_id"] in set(ids)}
    data = convert(items, ids, plan, source)
    result = {"schema_version": 1, "protocol": plan["protocol"],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "status_at_freeze": "not_scored_candidate_not_bound",
        "human_content_inspection": "No question, answer or source content displayed during selection; no outcome filtering.",
        "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        "source_manifest_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
        "canonical_sha256": source["canonical_sha256"], "canonical_bytes": source["canonical_bytes"],
        "source_url": source["source_url"], "source_revision": source["source_revision"],
        "upstream_sha256": source["upstream_sha256"], "license": source["license"],
        "license_source": source["license_source"],
        "selection_prefix": plan["cohort"]["selection_prefix"],
        "selected_ids": ids, "selected_ids_sha256": digest(ids),
        "excluded_prior_ids_sha256": digest(source["selected_ids"]),
        "excluded_prior_queries": len(source["selected_ids"]), "prior_selection_overlap": 0,
        "expected_queries": len(ids), "dataset_sha256": data.fingerprint,
        "selected_context_paragraphs": len(data.sessions),
        "selected_context_count_distribution": dict(sorted(Counter(len(selected[identity]["context"]) for identity in ids).items())),
        "required_evidence": sum(len(case.required) for case in data.queries),
        "representation": "original-sentences-v2; every supplied paragraph and original sentence retained",
        "source_turns": data.turn_count, "source_characters": data.source_characters,
        "limits": plan["interpretation"][:4]}
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


def load(path):
    plan, source, original_path = source_spec()
    manifest = json.loads(MANIFEST.read_bytes())
    if (manifest["plan_sha256"] != hashlib.sha256(PLAN.read_bytes()).hexdigest()
            or manifest["source_manifest_sha256"] != hashlib.sha256(original_path.read_bytes()).hexdigest()):
        raise ValueError("Frozen selection protocol changed")
    items = read_source(path, source)
    ids = select_ids([item["_id"] for item in items], source["selected_ids"],
                     plan["cohort"]["selection_prefix"], plan["cohort"]["queries"])
    if ids != manifest["selected_ids"] or digest(ids) != manifest["selected_ids_sha256"]:
        raise ValueError("Frozen selected IDs changed")
    data = convert(items, ids, plan, source)
    if data.fingerprint != manifest["dataset_sha256"]:
        raise ValueError("Frozen selected dataset changed")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".artifacts/round2/private")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    path = prepare_data(args.data_dir)
    value = freeze(path) if args.freeze else json.loads(MANIFEST.read_bytes())
    # Never print IDs, questions, labels or source text to implementation agents.
    print(json.dumps({key: value[key] for key in ("expected_queries", "selected_ids_sha256",
        "dataset_sha256", "prior_selection_overlap", "selected_context_paragraphs", "required_evidence")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
