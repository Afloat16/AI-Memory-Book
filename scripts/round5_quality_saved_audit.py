"""Attribute old saved evidence omissions without executing retrieval or models.

Only the already measured round-four manifest's rows are read from Parquet.
Output contains identifiers/counts/hashes, never questions, answers or passages.
Absence from returned results does not prove absence from the candidate pool.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.run import _normalized

REPORTS = ROOT / "benchmarks/results/round4-comparison-43363060062-1"
MANIFEST = ROOT / "benchmarks/experiments/round4-hotpot256-manifest.json"
KINDS = ("required_session_absent", "required_turn_absent", "required_turn_partial",
         "full_reference_but_unmatched")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_annotations(parquet, manifest):
    import pyarrow.parquet as pq
    if sha(parquet) != manifest["upstream_sha256"]:
        raise ValueError("Frozen Parquet bytes changed")
    identities = manifest["selected_ids"]
    records = pq.read_table(parquet, filters=[("id", "in", identities)],
                            columns=["id", "type", "context", "supporting_facts"]).to_pylist()
    if len(records) != len(identities) or {r["id"] for r in records} != set(identities):
        raise ValueError("Old selected rows incomplete or duplicated")
    result, originals = {}, {}
    for record in records:
        identity, context = record["id"], record["context"]
        positions = {title: i for i, title in enumerate(context["title"])}
        if len(positions) != len(context["title"]):
            raise ValueError("Duplicate paragraph title")
        for position, sentences in enumerate(context["sentences"]):
            for ordinal, sentence in enumerate(sentences):
                originals[("hotpot-" + identity, f"{identity}-article-{position}", ordinal)] = "USER: " + sentence
        required = []
        seen = set()
        facts = record["supporting_facts"]
        for title, ordinal in zip(facts["title"], facts["sent_id"], strict=True):
            position = positions[title]
            sentence = context["sentences"][position][ordinal]
            key = (position, ordinal, sentence)
            if key in seen:
                continue
            seen.add(key)
            required.append((f"{identity}-article-{position}", ordinal, sentence))
        result[identity] = required
    if sum(map(len, result.values())) != manifest["required_evidence"]:
        raise ValueError("Annotation order/count does not match frozen representation")
    return result, originals


def reference_covers(sentence, reference, original):
    lo, hi = reference["turn_start"], reference["turn_end"]
    if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi <= len(original):
        raise ValueError("Invalid saved canonical-turn coordinates")
    return _normalized(sentence) in _normalized(original[lo:hi])


def classify_missing(required, ranks, sources, project, originals):
    if len(required) != len(ranks):
        raise ValueError("Saved rank vector differs from original annotations")
    refs = [ref for block in sources for ref in block]
    counts = Counter({kind: 0 for kind in KINDS})
    missing = []
    for index, ((session, ordinal, sentence), rank) in enumerate(zip(required, ranks, strict=True)):
        if rank is not None:
            continue
        session_refs = [r for r in refs if r["project"] == project and r["session_id"] == session]
        turn_refs = [r for r in session_refs if r["turn_index"] == ordinal]
        if not session_refs:
            kind = "required_session_absent"
        elif not turn_refs:
            kind = "required_turn_absent"
        elif not any(reference_covers(sentence, r, originals[(project, session, ordinal)]) for r in turn_refs):
            kind = "required_turn_partial"
        else:
            kind = "full_reference_but_unmatched"
        counts[kind] += 1
        missing.append({"annotation_index": index, "classification": kind})
    return counts, missing


def assess(report, annotations, originals):
    cells, keyed = [], {}
    for cell in report["configurations"]:
        rows = cell["query_results"]
        if len(rows) != len(annotations) or {r["id"] for r in rows} != set(annotations):
            raise ValueError("Saved report omits or duplicates selected questions")
        counts = Counter({kind: 0 for kind in KINDS})
        by_query = []
        complete = matched = 0
        for row in rows:
            required = annotations[row["id"]]
            if row["project"] != "hotpot-" + row["id"]:
                raise ValueError("Saved project scope changed")
            for block in row["result_sources"]:
                for ref in block:
                    key = (ref["project"], ref["session_id"], ref["turn_index"])
                    if ref["project"] != row["project"] or key not in originals:
                        raise ValueError("Saved reference has wrong project/source identity")
                    reference_covers("", ref, originals[key])
            if row["required_evidence"] != len(required):
                raise ValueError("Saved required evidence count changed")
            ranks = row["evidence_ranks"]
            present = sum(rank is not None for rank in ranks)
            if present != row["matched_evidence"] or bool(present == len(required)) != row["complete"]:
                raise ValueError("Saved evidence metrics disagree with rank vector")
            for (session, ordinal, sentence), rank in zip(required, ranks, strict=True):
                if rank is None:
                    continue
                if type(rank) is not int or not 1 <= rank <= len(row["result_sources"]):
                    raise ValueError("Invalid saved evidence rank")
                if not any(ref["project"] == row["project"] and ref["session_id"] == session and
                           ref["turn_index"] == ordinal and
                           reference_covers(sentence, ref, originals[(row["project"], session, ordinal)])
                           for ref in row["result_sources"][rank - 1]):
                    raise ValueError("Matched evidence lacks its saved-rank source reference")
            classified, missing = classify_missing(required, ranks, row["result_sources"], row["project"], originals)
            counts.update(classified)
            matched += present
            complete += int(row["complete"])
            if missing:
                by_query.append({"id": row["id"], "missing": missing})
        total = sum(map(len, annotations.values()))
        if sum(counts.values()) != total - matched:
            raise ValueError("Missing-evidence accounting does not close")
        key = (cell["tokenizer"], cell["budget_tokens"])
        if key in keyed:
            raise ValueError("Duplicate configuration")
        keyed[key] = {r["id"]: r for r in rows}
        cells.append({"tokenizer": key[0], "budget_tokens": key[1], "queries": len(rows),
                      "required_annotations": total, "matched_annotations": matched,
                      "complete_questions": complete, "missing_annotations": dict(counts),
                      "incomplete_questions": by_query})
    larger_budget = []
    for encoding in ("cl100k_base", "o200k_base"):
        old, new = keyed[(encoding, 1024)], keyed[(encoding, 2048)]
        larger_budget.append({"tokenizer": encoding, "from_tokens": 1024, "to_tokens": 2048,
            "changed_evidence_vectors": sum(old[i]["evidence_ranks"] != new[i]["evidence_ranks"] for i in old),
            "changed_context_hashes": sum(old[i]["context_sha256"] != new[i]["context_sha256"] for i in old),
            "complete_gains": sum(not old[i]["complete"] and new[i]["complete"] for i in old),
            "complete_losses": sum(old[i]["complete"] and not new[i]["complete"] for i in old)})
    return {"cells": cells, "larger_budget": larger_budget}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=ROOT / ".artifacts/round4-inputs/hotpot-validation.parquet")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve the existing offline audit")
    manifest = json.loads(MANIFEST.read_bytes())
    annotations, originals = load_annotations(args.parquet, manifest)
    value = {"schema_version": 2, "status": "completed-offline-only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha(Path(__file__)), "manifest_sha256": sha(MANIFEST),
        "original_evaluator_sha256": sha(ROOT / "benchmarks/run.py"),
        "parquet_sha256": sha(args.parquet), "queries": len(annotations),
        "retrieval_calls": 0, "model_calls": 0,
        "canonical_turns": len(originals),
        "coordinate_rule": "Preserve original USER: prefix and sentence whitespace, validate project/session/turn and bounds, then use the original evaluator's case-preserving whitespace-normalized substring check. Saved matched ranks are also checked against their referenced result blocks; this does not reconstruct omitted response text.",
        "scope": "Already measured v032 round-four data only. Classification uses saved result source references and original annotation coordinates. It does not locate missing sources within an unsaved candidate pool or measure new quality/latency.",
        "stages": {}}
    for stage in ("candidate-native", "candidate-semantic-native"):
        path = REPORTS / (stage + ".json.gz")
        report = json.loads(gzip.decompress(path.read_bytes()))
        if report["status"] != "completed" or report["dataset"]["sha256"] != manifest["dataset_sha256"]:
            raise ValueError("Wrong saved report or dataset")
        value["stages"][stage] = {"report_sha256": sha(path), **assess(report, annotations, originals)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(value, output, indent=2, ensure_ascii=False)
        output.write("\n")
    for stage, assessment in value["stages"].items():
        for cell in assessment["cells"]:
            if cell["tokenizer"] == "cl100k_base":
                print(json.dumps({"stage": stage, **{k: v for k, v in cell.items() if k != "incomplete_questions"}}))
        print(json.dumps({"stage": stage, "larger_budget": assessment["larger_budget"]}))


if __name__ == "__main__":
    main()
