"""Commit-bound fresh IDs; no retrieval, inference, scoring or outcome filtering.

Only the four previously scored manifests are read before the new binding.
The exact Parquet is touched only after source/evaluator/dependency/model
verification. The manifest must be committed before a scored worker loads it.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path

from benchmarks.data import Dataset
from benchmarks.hotpot_data import convert_hotpot
from benchmarks.prepare_native_data import normalize_hotpot
from scripts import round6_comparison as comparison

COUNT = 256
EXCLUDED = 896
SEED = comparison.SEED
VARIANT = "hotpot_round6_unseen_selection_v1"
VERSION = "round6-id-only-hotpot-1"
SOURCE_COLUMNS = ("id", "question", "answer", "type", "level", "context", "supporting_facts")
require = comparison.require
sha = comparison.sha
digest = comparison.reused.digest


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def exclusion_ids(manifests):
    require(len(manifests) == 4, "Require all four historical cohorts")
    values = []
    for manifest, count in zip(manifests, (128, 256, 256, 256), strict=True):
        ids = manifest["selected_ids"]
        require(isinstance(ids, list) and len(ids) == count
                and all(isinstance(value, str) and value for value in ids), "Invalid historical ID list")
        values.extend(ids)
    require(len(values) == len(set(values)) == EXCLUDED, "Require all 896 distinct historical IDs")
    return values


def select_ids(ids, excluded, prefix, count):
    require(all(isinstance(identity, str) and identity for identity in [*ids, *excluded]),
            "Source and exclusion IDs must be nonempty strings")
    require(len(ids) == len(set(ids)) and len(excluded) == len(set(excluded)), "Duplicate source/exclusion IDs")
    require(not set(excluded) - set(ids), "A historical excluded ID is absent from the exact source")
    eligible = set(ids) - set(excluded)
    require(type(count) is int and count > 0 and len(eligible) >= count, "Insufficient independent IDs")
    return sorted(eligible, key=lambda identity: (sha((prefix + identity).encode()), identity))[:count]


@dataclass(frozen=True)
class Inputs:
    plan: dict
    binding: dict
    binding_commit: str
    plan_sha256: str
    binding_sha256: str
    source: dict
    prior: list[dict]
    prior_sha256: dict


def registered_inputs(binding_path=comparison.BINDING):
    """Verify all identities and commit ordering before touching fresh text."""
    plan, binding = comparison.frozen_inputs(binding_path)
    name = Path(binding_path).resolve().relative_to(comparison.ROOT.resolve()).as_posix()
    binding_commit = comparison.git("log", "-1", "--format=%H", "--", name).decode().strip()
    require(binding_commit and binding_commit != binding["evaluator_commit"],
            "Publish a separate binding commit after the evaluator")
    comparison.require_committed(binding_path, binding_commit)
    comparison.git("merge-base", "--is-ancestor", binding["evaluator_commit"], binding_commit)
    manifests, hashes = [], {}
    for path in comparison.PRIOR_MANIFESTS:
        raw = comparison.relative_file(path).read_bytes()
        require(raw == comparison.git("show", comparison.BASELINE["commit"] + ":" + path)
                and binding["evaluator_files"].get(path) == sha(raw), "Historical cohort bytes changed: " + path)
        manifests.append(json.loads(raw))
        hashes[path] = sha(raw)
    exclusion_ids(manifests)
    return Inputs(plan, binding, binding_commit, comparison.file_sha(comparison.PLAN),
                  comparison.file_sha(binding_path), manifests[0], manifests, hashes)


def selected_dataset(parquet_path, inputs):
    """Read IDs first, then selected rows, from the verified original bytes."""
    raw = Path(parquet_path).read_bytes()
    source = inputs.source
    require(len(raw) == source["upstream_bytes"] and sha(raw) == source["upstream_sha256"],
            "Parquet bytes differ from the frozen public source")
    import pyarrow as pa
    import pyarrow.parquet as pq
    ids = pq.read_table(pa.BufferReader(raw), columns=["id"]).column("id").to_pylist()
    require(len(ids) == source["upstream_rows"], "Upstream row count changed")
    excluded = exclusion_ids(inputs.prior)
    selected = select_ids(ids, excluded, comparison.PREFIX, COUNT)
    rows = pq.read_table(pa.BufferReader(raw), filters=[("id", "in", selected)],
                        columns=list(SOURCE_COLUMNS)).to_pylist()
    actual = [row["id"] for row in rows]
    require(len(actual) == len(set(actual)) == COUNT and set(actual) == set(selected),
            "Filtered source rows differ from the frozen IDs")
    mapping = {row["id"]: row for row in rows}
    canonical_rows = normalize_hotpot([mapping[identity] for identity in selected])
    items = json.loads(canonical_rows)
    data = convert_hotpot(items, selected, {key: source[key] for key in
        ("dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})
    data.seed, data.variant = SEED, VARIANT
    data.provenance.update(selection="SHA256(prefix + ID) ascending, then ID; exclude all four historical cohorts",
        selection_prefix=comparison.PREFIX, prior_selection_overlap=0, binding_sha256=inputs.binding_sha256,
        interpretation="Fresh IDs from the same HotpotQA source, not a new domain; regression after first scoring.")
    summary = {"selected_ids": selected, "selected_ids_sha256": digest(selected),
        "excluded_prior_ids_sha256": digest(sorted(excluded)), "excluded_prior_queries": len(excluded),
        "prior_id_hashes": {path: digest(manifest["selected_ids"])
            for path, manifest in zip(comparison.PRIOR_MANIFESTS, inputs.prior, strict=True)},
        "prior_selection_overlap": 0, "unique_upstream_ids": len(ids), "unique_selected_ids": len(selected),
        "eligible_queries": len(ids) - len(excluded), "selected_canonical_sha256": sha(canonical_rows),
        "selected_canonical_bytes": len(canonical_rows),
        "selected_canonical_order": "frozen selected_ids order; normalize_hotpot compact sorted-key JSON plus newline",
        "expected_queries": len(data.queries), "dataset_sha256": data.fingerprint,
        "answerable_queries": sum(case.answerable for case in data.queries),
        "selected_context_paragraphs": len(data.sessions),
        "selected_context_count_distribution": {str(key): value for key, value in
            sorted(Counter(len(item["context"]) for item in items).items())},
        "support_annotation_count": sum(len(item["supporting_facts"]) for item in items),
        "required_evidence": sum(len(case.required) for case in data.queries),
        "source_turns": data.turn_count, "source_characters": data.source_characters,
        "source_utf8_bytes": sum(len(message["content"].encode()) for session in data.sessions for message in session["messages"])}
    require(summary["expected_queries"] == summary["answerable_queries"] == COUNT,
            "Do not silently substitute an unregistered query/answerability population")
    return data, summary


def manifest_value(inputs, summary):
    return {"schema_version": 1, "protocol": VERSION,
        "status_at_freeze": (comparison.MANIFEST_RECOVERY_STATUS if "fixture_recovery" in inputs.binding
                             else "source-and-evaluator-bound-before-selection-not-scored"),
        **({"fixture_recovery": inputs.binding["fixture_recovery"]} if "fixture_recovery" in inputs.binding else {}),
        "human_content_inspection": "ID-only selection; no questions, answers or source passages displayed; no outcome filtering.",
        "plan_sha256": inputs.plan_sha256, "binding_sha256": inputs.binding_sha256,
        "binding_commit": inputs.binding_commit, "evaluator_commit": inputs.binding["evaluator_commit"],
        "sources": {key: inputs.binding[key] for key in ("baseline", "candidate")},
        "upstream_model_identity_sha256": digest(inputs.binding["model"]),
        "prior_manifest_sha256": inputs.prior_sha256,
        **{key: inputs.source[key] for key in ("source_url", "source_revision", "upstream_sha256",
            "upstream_bytes", "upstream_rows", "canonical_sha256", "canonical_bytes", "license", "license_source")},
        "canonical_source_hash_boundary": "Historical full canonical hash is provenance; exact Parquet verified, only selected rows normalized here.",
        "selection_prefix": comparison.PREFIX, "seed": SEED, "variant": VARIANT,
        "representation": "original-sentences-v2; every supplied paragraph and original sentence retained",
        "limits": ["Same public source, not a new domain; these IDs become regression data after first scoring.",
                   "All questions are answerable; no abstention, hallucination or generated-answer score.",
                   "Native and supplied-page component boundaries are separate; no whole-product superiority claim."],
        **summary}


def freeze(parquet_path, binding_path=comparison.BINDING, manifest_path=comparison.MANIFEST):
    path = Path(manifest_path)
    require(path.resolve() == comparison.MANIFEST.resolve(), "Freeze only the registered new manifest")
    require(not path.exists(), "Never overwrite or reselect the fresh manifest")
    inputs = registered_inputs(binding_path)
    _, summary = selected_dataset(parquet_path, inputs)
    value = manifest_value(inputs, summary)
    value["frozen_at"] = comparison.reused.now()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def committed_manifest(binding_path=comparison.BINDING, manifest_path=comparison.MANIFEST):
    inputs = registered_inputs(binding_path)
    path = Path(manifest_path)
    require(path.resolve() == comparison.MANIFEST.resolve(), "Use only the registered committed manifest")
    comparison.require_committed(path)
    value = json.loads(path.read_bytes())
    require(value["binding_sha256"] == inputs.binding_sha256 and value["plan_sha256"] == inputs.plan_sha256
            and value["binding_commit"] == inputs.binding_commit
            and value["evaluator_commit"] == inputs.binding["evaluator_commit"]
            and value["sources"] == {key: inputs.binding[key] for key in ("baseline", "candidate")}
            and value["prior_manifest_sha256"] == inputs.prior_sha256
            and value["excluded_prior_queries"] == EXCLUDED and value["prior_selection_overlap"] == 0
            and value["expected_queries"] == value["unique_selected_ids"] == COUNT
            and len(value["selected_ids"]) == len(set(value["selected_ids"])) == COUNT
            and value["selected_ids_sha256"] == digest(value["selected_ids"])
            and not set(value["selected_ids"]) & set(exclusion_ids(inputs.prior)), "Manifest identity/exclusions differ")
    name = path.relative_to(comparison.ROOT).as_posix()
    manifest_commit = comparison.git("log", "-1", "--format=%H", "--", name).decode().strip()
    require(manifest_commit != inputs.binding_commit, "Publish the manifest after the binding, in a separate commit")
    comparison.git("merge-base", "--is-ancestor", inputs.binding_commit, manifest_commit)
    return inputs, value


def load(parquet_path, binding_path=comparison.BINDING, manifest_path=comparison.MANIFEST) -> Dataset:
    inputs, value = committed_manifest(binding_path, manifest_path)
    data, summary = selected_dataset(parquet_path, inputs)
    expected = manifest_value(inputs, summary)
    expected["frozen_at"] = value["frozen_at"]
    require(value == expected, "Frozen selected IDs, canonical representation or dataset fingerprint changed")
    return data
