"""Prepare the registered fixture-only recovery without reading question data.

Commit this helper/evaluator first. Run ``bind`` and commit its new output;
then run ``manifest`` and commit its separate copy. Neither phase opens
Parquet, selects IDs, retrieves, infers, scores or times product operations.
The original binding, manifest and all their Git snapshots remain intact.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import round6_comparison as comparison

PROTOCOL = "v034-round6-comparison-fixture-recovery-v1"
POLICY = ("Retain the original selected IDs and content; commit the corrected evaluator, "
          "a separate recovery binding, then the copied manifest before first scoring. "
          "One claimed execution, no implicit replay or reselection.")
CHANGED_ORIGINAL_INPUTS = {"scripts/round6_comparison.py", "scripts/round6_comparison_data.py",
                           "tests/test_round6_comparison.py"}
require = comparison.require


def original_inputs(plan=None):
    """Read exact committed registration/metadata and original source snapshots."""
    plan = comparison.registered_plan() if plan is None else plan
    path = comparison.relative_file(comparison.RECOVERY_ADDENDUM)
    comparison.require_committed(path)
    raw = path.read_bytes()
    require(raw == comparison.git("show", comparison.RECOVERY_COMMIT + ":" + comparison.RECOVERY_ADDENDUM),
            "Registered fixture recovery changed")
    registration = json.loads(raw)
    require(registration["schema_version"] == 1 and registration["protocol"] == PROTOCOL
            and registration["status"] == "registered-before-recovery-implementation-and-first-scoring"
            and registration["new_artifacts"] == {
                "binding": comparison.BINDING.relative_to(comparison.ROOT).as_posix(),
                "manifest": comparison.MANIFEST.relative_to(comparison.ROOT).as_posix(),
                "preparation_helper": "scripts/round6_comparison_recovery.py",
                "evaluator": comparison.VERSION, "binding_status": comparison.BINDING_STATUS},
            "Unregistered recovery path, evaluator or status")
    frozen = registration["original_freeze"]
    require(frozen["binding_path"] == comparison.ORIGINAL_BINDING
            and frozen["manifest_path"] == comparison.ORIGINAL_MANIFEST
            and frozen["status"] == "frozen-not-scored" and frozen["measurement_calls"] == 0,
            "Recovery must preserve the original unscored freeze")
    values = {}
    for kind in ("binding", "manifest"):
        name = frozen[kind + "_path"]
        current = comparison.relative_file(name)
        comparison.require_committed(current)
        content = current.read_bytes()
        require(comparison.sha(content) == frozen[kind + "_sha256"]
                and content == comparison.git("show", frozen["result_commit"] + ":" + name),
                "Original frozen bytes changed: " + kind)
        values[kind] = json.loads(content)
    binding, manifest = values["binding"], values["manifest"]
    require(comparison.git("show", frozen["binding_commit"] + ":" + comparison.ORIGINAL_BINDING)
            == comparison.relative_file(comparison.ORIGINAL_BINDING).read_bytes(),
            "Original binding commit differs")
    for earlier, later in ((frozen["evaluator_commit"], frozen["binding_commit"]),
                           (frozen["binding_commit"], frozen["result_commit"]),
                           (frozen["result_commit"], comparison.RECOVERY_COMMIT),
                           (comparison.RECOVERY_COMMIT, "HEAD")):
        comparison.git("merge-base", "--is-ancestor", earlier, later)
    sources = {"baseline": comparison.BASELINE, "candidate": comparison.requested_candidate(plan)}
    require(binding["evaluator"] == "round6-native-component-comparison-1"
            and binding["status"] == "frozen-before-selection"
            and binding["evaluator_commit"] == frozen["evaluator_commit"]
            and binding["plan_sha256"] == comparison.file_sha(comparison.PLAN)
            and {key: binding[key] for key in sources} == sources
            and manifest["sources"] == sources
            and manifest["binding_commit"] == frozen["binding_commit"]
            and manifest["evaluator_commit"] == frozen["evaluator_commit"]
            and manifest["binding_sha256"] == frozen["binding_sha256"],
            "Original source/evaluator/binding identity differs")
    require(len(binding["evaluator_files"]) == 71, "Keep all 71 original evaluator snapshots")
    for name, expected in binding["evaluator_files"].items():
        require(comparison.sha(comparison.git("show", frozen["evaluator_commit"] + ":" + name)) == expected,
                "Original evaluator snapshot changed: " + name)
        if name not in CHANGED_ORIGINAL_INPUTS:
            require(comparison.file_sha(comparison.relative_file(name)) == expected,
                    "Undeclared evaluator change during fixture recovery: " + name)
    for source in sources.values():
        require(comparison.runtime_hash(source["commit"]) == source["source_sha256"],
                "Original product runtime changed")
    locks = {key: comparison.file_sha(comparison.ROOT / name)
             for key, name in comparison.UPSTREAM_LOCKS.items()}
    receipt = binding["asset_verification"]
    require(binding["upstream_lock_sha256"] == locks
            and binding["extra_evaluator_files"] == [receipt["path"]]
            and binding["evaluator_files"].get(receipt["path"]) == receipt["sha256"],
            "Original asset receipt or locks changed")
    comparison.verify_asset_receipt(json.loads(comparison.relative_file(receipt["path"]).read_bytes()), sources, locks)
    require(len(manifest["selected_ids"]) == len(set(manifest["selected_ids"])) == frozen["queries"] == 256
            and comparison.reused.digest(manifest["selected_ids"]) == manifest["selected_ids_sha256"]
            and all(manifest[key] == frozen[key] for key in
                    ("selected_ids_sha256", "dataset_sha256", "selected_canonical_sha256", "excluded_prior_queries"))
            and manifest["prior_selection_overlap"] == frozen["overlap"] == 0,
            "Original selected IDs, content or exclusions changed")
    provenance = {"protocol": PROTOCOL,
        "registration": {"path": comparison.RECOVERY_ADDENDUM, "commit": comparison.RECOVERY_COMMIT,
                         "sha256": comparison.sha(raw)},
        "original_freeze": frozen, "original_asset_verification": receipt,
        "original_evaluator_files_sha256": comparison.reused.digest(binding["evaluator_files"]),
        "original_frozen_at": manifest["frozen_at"], "same_selected_ids": True,
        "selection_repeated": False, "question_content_read": False, "measurement_calls": 0,
        "scope": "Fixture correction after original ID selection, before first scoring; original content and statistics retained."}
    return binding, manifest, provenance


def verify_binding(binding, original, provenance):
    changed = {"evaluator", "status", "created_at", "evaluator_commit", "evaluator_files", "policy"}
    require(set(binding) == set(original) | {"fixture_recovery"}
            and all(binding[name] == value for name, value in original.items() if name not in changed)
            and binding["fixture_recovery"] == provenance and binding["policy"] == POLICY,
            "Recovery binding changed undeclared inputs or provenance")


def manifest_copy(original, binding, binding_sha256, binding_commit):
    value = copy.deepcopy(original)
    value.update(binding_sha256=binding_sha256, binding_commit=binding_commit,
                 evaluator_commit=binding["evaluator_commit"],
                 status_at_freeze=comparison.MANIFEST_RECOVERY_STATUS,
                 fixture_recovery=copy.deepcopy(binding["fixture_recovery"]))
    return value


def verify_manifest(value, original, binding, binding_sha256, binding_commit):
    require(value == manifest_copy(original, binding, binding_sha256, binding_commit),
            "Recovery must retain every original selected ID, content statistic and frozen_at")


def copy_manifest():
    from scripts import round6_comparison_data as data
    path = comparison.MANIFEST
    require(not path.exists(), "Never overwrite the copied recovery manifest")
    inputs = data.registered_inputs(comparison.BINDING)
    _, original, provenance = original_inputs(inputs.plan)
    require(inputs.binding["fixture_recovery"] == provenance, "Recovery binding provenance changed")
    value = manifest_copy(original, inputs.binding, inputs.binding_sha256, inputs.binding_commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data.canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="phase", required=True)
    bind = sub.add_parser("bind")
    bind.add_argument("--baseline-src", type=Path, required=True)
    bind.add_argument("--candidate-src", type=Path, required=True)
    bind.add_argument("--evaluator-commit", required=True)
    sub.add_parser("manifest")
    args = parser.parse_args(argv)
    if args.phase == "bind":
        original = json.loads(comparison.relative_file(comparison.ORIGINAL_BINDING).read_bytes())
        args.output = comparison.BINDING
        args.asset_verification = comparison.ROOT / original["asset_verification"]["path"]
        comparison.bind(args)
        path = comparison.BINDING
    else:
        copy_manifest()
        path = comparison.MANIFEST
    print(json.dumps({"phase": args.phase, "path": path.relative_to(comparison.ROOT).as_posix(),
                      "sha256": comparison.file_sha(path), "selection_repeated": False,
                      "question_content_read": False, "measurement_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
