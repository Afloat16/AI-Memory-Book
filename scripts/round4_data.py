"""Commit-bound, ID-only selection for the registered round-four Hotpot cohort.

This module performs no retrieval, model inference or downloads. It imports only
the historical pure data converters, never a candidate product package. Freeze
is deliberately separate from load: commit the binding before freezing, then
commit the new manifest before any evaluator can load the selected dataset.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.data import Dataset
from benchmarks.hotpot_data import convert_hotpot
from benchmarks.prepare_native_data import normalize_hotpot

PLAN = "benchmarks/experiments/round4-plan.json"
PLAN_COMMIT = "4f239eaab6e1ab7bfb8910819a74a6fab195629c"
ADDENDUM = "benchmarks/experiments/round4-development-addendum.json"
ADDENDUM_COMMIT = "fbfc6c56ae047abfd765e6149ba748c9e18adc42"
COUNTING_ADDENDUM = "benchmarks/experiments/round4-counting-addendum.json"
COUNTING_ADDENDUM_COMMIT = "e02584fd20d2626777449bc64322703de6df6948"
BASELINE = "7b7a5d7336b9350a128f5e0a888811b1b3015e68"
BASELINE_HASH = "9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46"
BINDING = "benchmarks/experiments/round4-validation-binding.json"
MANIFEST = "benchmarks/experiments/round4-hotpot256-manifest.json"
ORIGINAL = "benchmarks/hotpot_manifest.json"
PRIOR = "benchmarks/round2_hotpot256_manifest.json"
PRIOR_ROUND3 = "benchmarks/experiments/round3-hotpot256-manifest.json"
HISTORICAL = "benchmarks/experiments/novelty-cap-qualification-binding.json"
MODEL_PLAN = "benchmarks/experiments/semantic-local-plan.json"
MODEL_FINGERPRINT = "2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25"
LEGACY_EXTRA = "scripts/benchmark_default_recall.py"
NEW_EVALUATORS = ("scripts/round4_data.py", "tests/test_round4_data.py",
                  "scripts/round4_comparison.py", "tests/test_round4_comparison.py",
                  "scripts/run_round4_comparison.py", "tests/test_round4_comparison_controller.py",
                  "scripts/freeze_round4_validation.py", ".github/workflows/round4-freeze.yml",
                  ".github/workflows/round4-comparison.yml",
                  "benchmarks/experiments/round4-freeze-plan.json", ADDENDUM, COUNTING_ADDENDUM)
LOCK_PATHS = {"benchmarks/competitors/claude-mem-round2-lock.json",
              "benchmarks/competitors/ai-memory-lock.json",
              "benchmarks/competitors/billion-round2-lock.json"}
PREFIX = "AI-Memory-Book/v032/round4/2026-11-13/"
COUNT = 256
SEED = 41061
VARIANT = "hotpot_round4_unseen_selection_v1"
VERSION = "round4-id-only-hotpot-1"
PACKAGES = {"tiktoken": "0.12.0", "onnxruntime": "1.31.1", "tokenizers": "0.23.3", "numpy": "2.5.4", "pyarrow": "26.0.1"}
SOURCE_COLUMNS = ("id", "question", "answer", "type", "level", "context", "supporting_facts")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30,
                                       stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise ValueError("Required committed identity is unavailable; fetch the exact commits") from exc


def file_path(name):
    require(isinstance(name, str) and bool(name), "Invalid evaluator path")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.as_posix() == name and
            all(part not in (".", "..") for part in relative.parts), "Unsafe evaluator path")
    path = ROOT / name
    require(path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink(),
            "Evaluator path escapes the checkout")
    return path


def relative_path(path):
    try:
        name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Binding and manifest must be inside the evaluator checkout") from exc
    file_path(name)
    return name


def committed_bytes(path, commit="HEAD"):
    name = relative_path(path)
    raw = Path(path).read_bytes()
    require(raw == git("show", commit + ":" + name), "Commit the exact file before use: " + name)
    return raw


def baseline_bytes(name):
    raw = file_path(name).read_bytes()
    require(raw == git("show", BASELINE + ":" + name), "Historical file changed: " + name)
    return raw


def runtime_hash(commit):
    require(isinstance(commit, str) and re.fullmatch("[0-9a-f]{40}", commit), "Invalid runtime commit")
    require(git("rev-parse", commit + "^{commit}").decode().strip() == commit,
            "Runtime identity must name the exact commit")
    prefix = "src/memory_book/"
    names = git("ls-tree", "-r", "-z", "--name-only", commit, "--", prefix).decode().split("\0")
    paths = sorted(name for name in names if name.startswith(prefix) and name.endswith(".py"))
    require(bool(paths), "Runtime commit has no product Python files")
    value = hashlib.sha256()
    for name in paths:
        value.update(name[len(prefix):].encode())
        value.update(b"\0")
        value.update(git("show", commit + ":" + name))
        value.update(b"\0")
    return value.hexdigest()


def model_identity(plan):
    model = plan["model"]
    identity = {key: model[key] for key in
                ("repository", "revision", "files", "dimensions", "max_sequence_tokens")}
    identity.update(overlap_tokens=plan["index"]["overlap_tokens"], semantic_version=1,
                    pooling="attention-mask mean pooling followed by L2 normalization")
    require(digest(identity) == MODEL_FINGERPRINT, "Registered model identity changed")
    return identity


@dataclass(frozen=True)
class Inputs:
    plan: dict
    source: dict
    prior: dict
    prior_round3: dict
    binding: dict
    plan_sha256: str
    binding_sha256: str
    source_manifest_sha256: str
    prior_manifest_sha256: str
    prior_round3_manifest_sha256: str


def registered_inputs(binding_path) -> Inputs:
    """Verify every public identity before touching the private Parquet file."""
    plan_raw = file_path(PLAN).read_bytes()
    require(plan_raw == git("show", PLAN_COMMIT + ":" + PLAN), "Registered round-four plan changed")
    plan = json.loads(plan_raw)
    addendum_raw = file_path(ADDENDUM).read_bytes()
    require(addendum_raw == git("show", ADDENDUM_COMMIT + ":" + ADDENDUM),
            "Registered development addendum changed")
    addendum = json.loads(addendum_raw)
    require(addendum["schema_version"] == 1
            and addendum["status"] == "registered-before-candidate-b-implementation-and-measurement"
            and addendum["original_plan_commit"] == PLAN_COMMIT, "Development addendum belongs to another protocol")
    counting_raw = file_path(COUNTING_ADDENDUM).read_bytes()
    require(counting_raw == git("show", COUNTING_ADDENDUM_COMMIT + ":" + COUNTING_ADDENDUM),
            "Registered counting addendum changed")
    counting = json.loads(counting_raw)
    require(counting["schema_version"] == 1
            and counting["status"] == "registered-before-candidate-c-implementation-and-measurement"
            and counting["original_plan_commit"] == PLAN_COMMIT
            and counting["prior_addendum_commit"] == ADDENDUM_COMMIT,
            "Counting addendum belongs to another protocol")
    require(plan["baseline"]["commit"] == BASELINE and
            plan["baseline"]["runtime_sha256"] == BASELINE_HASH, "Registered baseline changed")
    cohort = plan["independent_validation"]["cohort"]
    require(cohort["count"] == COUNT and cohort["selection_prefix"] == PREFIX,
            "Registered selection changed")
    binding_raw = committed_bytes(Path(binding_path))
    binding = json.loads(binding_raw)
    require(type(binding["schema_version"]) is int and binding["schema_version"] == 1 and
            binding["status"] == "frozen-before-selection", "Binding was not frozen before selection")
    require(binding["plan_sha256"] == sha(plan_raw), "Binding identifies a different plan")
    require(binding["development_addendum"] == {"path": ADDENDUM, "commit": ADDENDUM_COMMIT,
            "sha256": sha(addendum_raw)}, "Binding identifies a different development addendum")
    require(binding.get("counting_addendum") == {"path": COUNTING_ADDENDUM, "commit": COUNTING_ADDENDUM_COMMIT,
            "sha256": sha(counting_raw)}, "Binding identifies a different counting addendum")
    require(binding["optional_semantic"] is True and binding["optional_project_statistics"] is False
            and "project_statistics_old_gate" not in binding,
            "Optional mode identity differs; no quality/statistics candidate is registered")
    require(binding["packages"] == PACKAGES, "Registered dependency pins changed")
    require(binding["baseline"] == {"commit": BASELINE, "source_sha256": BASELINE_HASH},
            "Binding baseline differs from v0.3.1")
    for label in ("baseline", "candidate"):
        source = binding[label]
        require(set(source) == {"commit", "source_sha256"} and
                isinstance(source["source_sha256"], str) and
                re.fullmatch("[0-9a-f]{64}", source["source_sha256"]), "Invalid source identity")
        require(runtime_hash(source["commit"]) == source["source_sha256"],
                "Runtime commit/hash mismatch: " + label)
    evaluator_commit = binding["evaluator_commit"]
    require(isinstance(evaluator_commit, str) and re.fullmatch("[0-9a-f]{40}", evaluator_commit),
            "Evaluator commit must be exact")
    require(git("rev-parse", evaluator_commit + "^{commit}").decode().strip() == evaluator_commit,
            "Invalid evaluator commit")
    historical = json.loads(baseline_bytes(HISTORICAL))["historical_files_sha256"]
    require(len(historical) == 58, "Historical evaluator registry changed")
    files = binding["evaluator_files"]
    require(isinstance(files, dict) and set(historical).issubset(files) and
            {PLAN, LEGACY_EXTRA, PRIOR_ROUND3, *NEW_EVALUATORS}.issubset(files), "Incomplete evaluator binding")
    require(relative_path(binding_path) not in files and BINDING not in files and MANIFEST not in files,
            "Binding or future manifest must not be included in its own evaluator identity")
    for name, expected in files.items():
        require(isinstance(expected, str) and re.fullmatch("[0-9a-f]{64}", expected),
                "Invalid evaluator SHA-256")
        require(sha(file_path(name).read_bytes()) == expected and
                sha(git("show", evaluator_commit + ":" + name)) == expected,
                "Changed or uncommitted evaluator: " + name)
        if name in historical:
            require(expected == historical[name] and sha(baseline_bytes(name)) == expected,
                    "Frozen evaluator identity changed: " + name)
    require(sha(baseline_bytes(LEGACY_EXTRA)) == files[LEGACY_EXTRA], "Legacy projection helper changed")
    require(sha(baseline_bytes(PRIOR_ROUND3)) == files[PRIOR_ROUND3], "Round-three exclusion manifest changed")
    locks = binding["upstream_locks"]
    require(isinstance(locks, dict) and len(locks) == 3 and
            all(isinstance(key, str) and key for key in locks) and set(locks.values()) == LOCK_PATHS,
            "Upstream component lock identities changed")
    identity = model_identity(json.loads(baseline_bytes(MODEL_PLAN)))
    require(binding["model"] == {"identity": identity, "fingerprint": MODEL_FINGERPRINT},
            "Bound model identity differs from the registered model")
    preflight = binding["asset_verification"]
    require(set(preflight) == {"path", "sha256"} and preflight["path"] in files
            and preflight["sha256"] == files[preflight["path"]], "Missing bound asset verification")
    assets = json.loads(file_path(preflight["path"]).read_bytes())
    require(assets["status"] == "all-assets-verified-before-selection"
            and assets["sources"] == {key: binding[key] for key in ("baseline", "candidate")}
            and assets["model"] == identity and assets["packages"] == PACKAGES
            and assets["upstream_locks_sha256"] == binding["upstream_lock_sha256"]
            and assets["question_content_read"] is False and assets["measurement_calls"] == 0,
            "Assets were not verified before selection")
    original_raw, prior_raw, third_raw = (baseline_bytes(name) for name in (ORIGINAL, PRIOR, PRIOR_ROUND3))
    source, prior, third = (json.loads(raw) for raw in (original_raw, prior_raw, third_raw))
    require(source["expected_queries"] == 128 and prior["expected_queries"] == 256 and
            third["expected_queries"] == 256 and len(source["selected_ids"]) == 128 and
            len(prior["selected_ids"]) == len(third["selected_ids"]) == 256,
            "Prior cohort counts changed")
    excluded = [*source["selected_ids"], *prior["selected_ids"], *third["selected_ids"]]
    require(len(excluded) == len(set(excluded)) == 640, "The three prior selections must contain 640 distinct IDs")
    return Inputs(plan, source, prior, third, binding, sha(plan_raw), sha(binding_raw),
                  sha(original_raw), sha(prior_raw), sha(third_raw))


def select_ids(ids, excluded, prefix, count):
    require(all(isinstance(identity, str) and identity for identity in [*ids, *excluded]),
            "Source and exclusion IDs must be nonempty strings")
    require(len(ids) == len(set(ids)) and len(excluded) == len(set(excluded)),
            "Duplicate source or exclusion IDs")
    require(not set(excluded) - set(ids), "An excluded prior ID is absent from the source")
    eligible = set(ids) - set(excluded)
    require(type(count) is int and count > 0 and len(eligible) >= count,
            "Insufficient independent query IDs")
    return sorted(eligible, key=lambda identity: (sha((prefix + identity).encode()), identity))[:count]


def selected_dataset(parquet_path, inputs):
    """Decode IDs first, then only selected rows, from one verified byte snapshot."""
    raw = Path(parquet_path).read_bytes()
    source = inputs.source
    require(len(raw) == source["upstream_bytes"] and sha(raw) == source["upstream_sha256"],
            "Parquet bytes differ from the original frozen source")
    import pyarrow as pa
    import pyarrow.parquet as pq
    ids = pq.read_table(pa.BufferReader(raw), columns=["id"]).column("id").to_pylist()
    require(len(ids) == source["upstream_rows"], "Upstream row count changed")
    excluded = [*source["selected_ids"], *inputs.prior["selected_ids"], *inputs.prior_round3["selected_ids"]]
    require(len(excluded) == len(set(excluded)) == 640, "Require all 640 distinct prior selected IDs")
    selected = select_ids(ids, excluded, PREFIX, COUNT)
    rows = pq.read_table(pa.BufferReader(raw), filters=[("id", "in", selected)],
                         columns=list(SOURCE_COLUMNS)).to_pylist()
    actual = [row["id"] for row in rows]
    require(len(actual) == COUNT and len(set(actual)) == COUNT and set(actual) == set(selected),
            "Filtered Parquet rows differ from the selected IDs")
    mapping = {row["id"]: row for row in rows}
    canonical_rows = normalize_hotpot([mapping[identity] for identity in selected])
    items = json.loads(canonical_rows)
    data = convert_hotpot(items, selected, {key: source[key] for key in
        ("dataset", "source_url", "source_revision", "upstream_sha256", "canonical_sha256", "license")})
    data.seed, data.variant = SEED, VARIANT
    data.provenance.update(selection="SHA256(prefix + ID) ascending, then ID; exclude all three prior cohorts",
        selection_prefix=PREFIX, prior_selection_overlap=0, binding_sha256=inputs.binding_sha256,
        interpretation="New selection from the same HotpotQA source, not a new domain; regression after first scoring.")
    summary = {"selected_ids": selected, "selected_ids_sha256": digest(selected),
        "excluded_prior_ids_sha256": digest(sorted(excluded)), "excluded_prior_queries": len(excluded),
        "prior128_ids_sha256": digest(source["selected_ids"]),
        "prior256_ids_sha256": digest(inputs.prior["selected_ids"]),
        "prior_round3_256_ids_sha256": digest(inputs.prior_round3["selected_ids"]),
        "prior_selection_overlap": 0, "prior_cohort_overlap": 0,
        "unique_upstream_ids": len(ids), "unique_selected_ids": len(selected),
        "eligible_queries": len(ids) - len(excluded),
        "selected_canonical_sha256": sha(canonical_rows), "selected_canonical_bytes": len(canonical_rows),
        "selected_canonical_order": "frozen selected_ids order; normalize_hotpot compact sorted-key JSON plus newline",
        "expected_queries": len(data.queries), "dataset_sha256": data.fingerprint,
        "answerable_queries": sum(case.answerable for case in data.queries),
        "selected_context_paragraphs": len(data.sessions),
        "selected_context_count_distribution": {str(key): value for key, value in
            sorted(Counter(len(item["context"]) for item in items).items())},
        "support_annotation_count": sum(len(item["supporting_facts"]) for item in items),
        "required_evidence": sum(len(case.required) for case in data.queries),
        "source_turns": data.turn_count, "source_characters": data.source_characters,
        "source_utf8_bytes": sum(len(message["content"].encode()) for session in data.sessions
                                 for message in session["messages"])}
    return data, summary


def manifest_value(inputs, summary):
    source = inputs.source
    return {"schema_version": 1, "protocol": VERSION,
        "status_at_freeze": "source-and-evaluator-bound-before-selection-not-scored",
        "human_content_inspection": "ID-only selection; no questions, answers or source passages displayed; no outcome filtering.",
        "plan_sha256": inputs.plan_sha256, "binding_sha256": inputs.binding_sha256,
        "development_addendum": inputs.binding["development_addendum"],
        "counting_addendum": inputs.binding["counting_addendum"],
        "evaluator_commit": inputs.binding["evaluator_commit"],
        "sources": {key: inputs.binding[key] for key in ("baseline", "candidate")},
        "model_fingerprint": inputs.binding["model"]["fingerprint"],
        "source_manifest_sha256": inputs.source_manifest_sha256,
        "prior_manifest_sha256": inputs.prior_manifest_sha256,
        "prior_round3_manifest_sha256": inputs.prior_round3_manifest_sha256,
        **{key: source[key] for key in ("source_url", "source_revision", "upstream_sha256",
            "upstream_bytes", "upstream_rows", "canonical_sha256", "canonical_bytes", "license", "license_source")},
        "canonical_source_hash_boundary": "Historical full canonical hash retained as provenance; exact Parquet bytes verified, only selected rows normalized here.",
        "selection_prefix": PREFIX, "seed": SEED, "variant": VARIANT,
        "representation": "original-sentences-v2; every supplied paragraph and original sentence retained",
        "limits": ["A new selection from the same public HotpotQA source, not a new domain.",
                   "All questions are answerable; this cohort does not measure abstention.",
                   "After first scoring these IDs are regression data.",
                   "Evidence retrieval, not generated-answer accuracy or whole-product workflow cost."],
        **summary}


def freeze(parquet_path, binding_path, manifest_path=None):
    path = Path(manifest_path) if manifest_path is not None else ROOT / MANIFEST
    relative_path(path)
    if path.exists():
        raise FileExistsError("The round-four manifest already exists; never overwrite it")
    inputs = registered_inputs(binding_path)
    require(relative_path(path) not in inputs.binding["evaluator_files"], "Future manifest creates a binding cycle")
    _, summary = selected_dataset(parquet_path, inputs)
    value = manifest_value(inputs, summary)
    value["frozen_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def load(parquet_path, binding_path, manifest_path=None) -> Dataset:
    path = Path(manifest_path) if manifest_path is not None else ROOT / MANIFEST
    inputs = registered_inputs(binding_path)
    require(relative_path(path) not in inputs.binding["evaluator_files"], "Manifest creates a binding cycle")
    value = json.loads(committed_bytes(path))
    require(value.get("binding_sha256") == inputs.binding_sha256 and
            value.get("plan_sha256") == inputs.plan_sha256, "Manifest belongs to a different frozen binding")
    require(value.get("development_addendum") == inputs.binding["development_addendum"]
            and value.get("counting_addendum") == inputs.binding["counting_addendum"],
            "Frozen selection addenda differ from the binding")
    timestamp = value.get("frozen_at")
    require(isinstance(timestamp, str), "Missing freeze time")
    parsed = datetime.fromisoformat(timestamp)
    require(parsed.utcoffset() == timezone.utc.utcoffset(parsed), "Freeze time must be UTC")
    data, summary = selected_dataset(parquet_path, inputs)
    expected = manifest_value(inputs, summary)
    expected["frozen_at"] = timestamp
    require(value == expected, "Frozen selection, representation or dataset identity changed")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True, type=Path)
    parser.add_argument("--binding", type=Path, default=ROOT / BINDING)
    parser.add_argument("--manifest", type=Path, default=ROOT / MANIFEST)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        value = freeze(args.parquet, args.binding, args.manifest)
    else:
        load(args.parquet, args.binding, args.manifest)
        value = json.loads(args.manifest.read_bytes())
    # Deliberately do not print selected IDs, questions, answers or source text.
    print(json.dumps({key: value[key] for key in ("expected_queries", "selected_ids_sha256",
        "dataset_sha256", "binding_sha256", "prior_selection_overlap", "selected_context_paragraphs",
        "required_evidence")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
