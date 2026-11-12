"""Recover a completed eight-worker screen from an interrupted Git upload.

This command performs no retrieval, data loading, tuning or timing. Original
worker gzip files are CRC-checked, matched to their ledgers by SHA256, checked
against the registered evaluator, and kept unchanged. The incomplete aggregate
is retained, and every available decompressed byte must match reconstruction.
"""
from __future__ import annotations

import argparse
import codecs
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import round3_project_stats as frozen

INPUTS = ROOT / "benchmarks/experiments/round3-quality-recovery-inputs.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def pinned_file(commit, entry):
    raw = subprocess.check_output(["git", "show", commit + ":" + entry["path"]], cwd=ROOT)
    require(len(raw) == entry["size"] and git_blob(raw) == entry["git_blob_sha"],
            "Pinned input content differs: " + entry["path"])
    return raw


def join_group(parts, *, truncated=False):
    ordered = sorted(parts)
    require([index for index, raw in ordered] == list(range(len(parts))),
            "Missing or duplicate chunk index")
    require(bool(ordered) and all(len(raw) == 196608 for index, raw in ordered[:-1]),
            "Invalid interior chunk size")
    require(len(ordered[-1][1]) == 196608 if truncated else len(ordered[-1][1]) < 196608,
            "Unexpected transfer tail")
    return b"".join(raw for index, raw in ordered)


def controller_prefix(raw):
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    decoded = inflater.decompress(raw)
    require(not inflater.eof, "Group 08 was expected to be incomplete")
    # Only tolerate an incomplete final UTF-8 code point, not invalid input.
    text = codecs.getincrementaldecoder("utf-8")().decode(decoded, final=False)
    decoder = json.JSONDecoder()
    require(text.startswith("{"), "Aggregate is not a JSON object")
    values, position = {}, 1
    while True:
        key, position = decoder.raw_decode(text, position)
        require(isinstance(key, str) and key not in values, "Duplicate or invalid controller key")
        require(text[position:position + 1] == ":", "Expected canonical key delimiter")
        position += 1
        if key == "workers":
            require(text[position:position + 1] == "[", "Expected original workers array")
            return values, decoded
        value, position = decoder.raw_decode(text, position)
        values[key] = value
        require(text[position:position + 1] == ",", "Incomplete controller metadata")
        position += 1


def assert_original_prefix(raw, prefix):
    require(raw.startswith(prefix), "Reconstruction disagrees with available original aggregate bytes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output_dir = args.output_dir.resolve()
    require(output_dir.is_relative_to(ROOT / "benchmarks/reports")
            and not output_dir.exists(), "Use a new report directory")
    declaration, binding = frozen.registered(frozen.BINDING)
    inputs = json.loads(INPUTS.read_text())
    require(inputs["schema_version"] == 1
            and len(inputs["original_files"]) == 8
            and len(inputs["transfer_chunks"]) == 48, "Frozen recovery inventory differs")
    output_dir.mkdir(parents=True)
    original_bytes, groups, preserved = {}, defaultdict(list), []
    for entry in inputs["original_files"]:
        raw = pinned_file(inputs["results_commit"], entry)
        name = Path(entry["path"]).name
        original_bytes[name] = raw
        (output_dir / name).write_bytes(raw)
        preserved.append({**entry, "commit": inputs["results_commit"], "sha256": frozen.sha(raw)})
    for entry in inputs["transfer_chunks"]:
        raw = pinned_file(inputs["upload_commit"], entry)
        group, index = Path(entry["path"]).stem.split("-")
        groups[int(group)].append((int(index), raw))
        preserved.append({**entry, "commit": inputs["upload_commit"], "sha256": frozen.sha(raw)})
    require(set(groups) == set(range(9)), "Transfer group inventory differs")

    complete_groups = {group: join_group(parts) for group, parts in groups.items() if group != 8}
    partial = join_group(groups[8], truncated=True)
    partial_path = output_dir / "original-incomplete-aggregate-prefix.json.gz.part"
    partial_path.write_bytes(partial)
    metadata, decoded_prefix = controller_prefix(partial)
    require(metadata["protocol"] == frozen.PROTOCOL and metadata["plan"] == declaration
            and metadata["binding"] == binding and metadata["binding_sha256"] == frozen.sha(frozen.BINDING.read_bytes())
            and metadata["evaluator_hashes"] == frozen.helper_hashes()
            and metadata["evaluator_commit"] == inputs["original_evaluator_commit"],
            "Original controller identity differs")
    expected = frozen.expected_order()
    attempts = metadata["attempted_workers"]
    require([(a["cohort"], a["mode"]) for a in attempts] == expected
            and all(a["status"] == "completed" and a["exit_code"] == 0 for a in attempts)
            and metadata["error"] is None and metadata["evaluator_unchanged"],
            "Original worker completion records are absent or invalid")

    workers_by_identity, ledgers_by_hash = {}, {}
    all_objects = [("original:" + name, raw) for name, raw in original_bytes.items()]
    all_objects += [("group:" + str(group), raw) for group, raw in sorted(complete_groups.items())]
    object_inventory = []
    for origin, raw in all_objects:
        if raw.startswith(b"\x1f\x8b"):
            # gzip.decompress validates CRC, complete member length and trailer.
            worker = json.loads(gzip.decompress(raw))
            identity = (worker["cohort"], worker["mode"])
            require(identity in expected and identity not in workers_by_identity
                    and worker["status"] == "completed" and worker["error"] is None,
                    "Invalid or duplicate complete worker")
            workers_by_identity[identity] = (worker, raw, origin)
            object_inventory.append({"origin": origin, "kind": "worker", "cohort": identity[0],
                                     "mode": identity[1], "sha256": frozen.sha(raw), "bytes": len(raw)})
        else:
            lines = raw.splitlines()
            require(bool(lines) and all(isinstance(json.loads(line), dict) for line in lines),
                    "Transferred object is neither a complete worker nor JSONL ledger")
            digest = frozen.sha(raw)
            require(digest not in ledgers_by_hash, "Duplicate ledger transfer")
            ledgers_by_hash[digest] = (raw, origin)
            object_inventory.append({"origin": origin, "kind": "ledger", "sha256": digest, "bytes": len(raw)})
    require(set(workers_by_identity) == set(expected) and len(ledgers_by_hash) == 8,
            "All eight original workers and ledgers are required")

    output = output_dir / (inputs["original_prefix"] + ".json.gz")
    workers, used_ledgers = [], set()
    for identity, attempt in zip(expected, attempts):
        worker, raw, origin = workers_by_identity[identity]
        ledger_sha = worker["ledger_sha256"]
        require(ledger_sha in ledgers_by_hash and ledger_sha not in used_ledgers,
                "Worker has no unique matching original ledger")
        used_ledgers.add(ledger_sha)
        ledger, ledger_origin = ledgers_by_hash[ledger_sha]
        raw_path, ledger_path = frozen.worker_paths(output, *identity)
        for path, content in ((raw_path, raw), (ledger_path, ledger)):
            require(not path.exists() or path.read_bytes() == content, "Existing original bytes differ")
            path.write_bytes(content)
        adopted = frozen.adopt_worker(raw_path, ledger_path, attempt["exit_code"])
        frozen.verify_worker_files(adopted, output_dir)
        workers.append(adopted)
    report = {**metadata, "workers": workers}
    validation = frozen.validate(report, ledger_root=output_dir)
    require(validation == report["validation"] and validation["passed"]
            and validation["calls"] == 8082 and validation["workers"] == 8,
            "Recovered original matrix is incomplete or invalid")
    comparisons = frozen.comparisons(report)
    require(comparisons == report["comparisons"], "Original paired metrics disagree with worker rows")
    screening = frozen.screen(comparisons, valid=True)
    require(screening == report["screening"], "Original screening decision disagrees with registered gate")
    raw = (frozen.canonical(report) + "\n").encode()
    assert_original_prefix(raw, decoded_prefix)

    frozen.save_report(output, report)
    require(gzip.decompress(output.read_bytes()) == raw, "Saved reconstruction changed original report")
    frozen.audit(output, frozen.BINDING)
    recovery_manifest = output_dir / "recovery-manifest.json"
    frozen.write_json(recovery_manifest, {
        "schema_version": 1, "status": "recovered_and_original_frozen_audit_passed",
        "inputs": inputs, "inputs_sha256": frozen.sha(INPUTS.read_bytes()),
        "preserved_inputs": preserved, "objects": object_inventory,
        "original_incomplete_aggregate": {
            "path": partial_path.relative_to(ROOT).as_posix(), "group": 8,
            "compressed_prefix_bytes": len(partial), "compressed_prefix_sha256": frozen.sha(partial),
            "decoded_prefix_bytes": len(decoded_prefix), "decoded_prefix_sha256": frozen.sha(decoded_prefix),
            "all_available_decoded_bytes_equal_reconstruction": True,
            "original_complete_gzip_available": False,
            "interpretation": "The old complete aggregate gzip is unavailable. This new aggregate is reconstructed from intact original workers, original attempt metadata and original ledgers; no missing record is inferred and no query is rerun."
        },
        "original_measurement_environment": metadata["environment"],
        "recovery_environment": {"python": platform.python_version(), "platform": platform.platform()},
        "original_evaluator_commit": metadata["evaluator_commit"],
        "recovery_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "original_finished_at": metadata["finished_at"],
        "new_measurement_calls": 0, "validation": validation, "screening": screening,
        "reconstructed_report_sha256": frozen.sha(raw),
        "reconstructed_gzip_sha256": frozen.sha(output.read_bytes()),
        "preserved_original_worker_count": 8, "preserved_original_ledger_count": 8
    })
    _, summary_path, markdown_path = frozen.result_paths(output)
    decision = {
        "schema_version": 1, "status": screening["status"],
        "validation_passed": validation["passed"], "calls": validation["calls"],
        "workers": validation["workers"], "qualified": screening["qualified"],
        "report_path": output.relative_to(ROOT).as_posix(),
        "summary_path": summary_path.relative_to(ROOT).as_posix(),
        "markdown_path": markdown_path.relative_to(ROOT).as_posix(),
        "recovery_manifest_path": recovery_manifest.relative_to(ROOT).as_posix(),
        "preserved_partial_group": 8,
        "preserved_partial_path": partial_path.relative_to(ROOT).as_posix(),
        "new_measurement_calls": 0, "original_evaluator_audit": "passed",
        "loss_checks": len(screening["losses"]), "gain_checks": len(screening["gains"]),
        "runtime_commit": frozen.CANDIDATE_COMMIT,
        "recovery_binding_sha256": frozen.sha(INPUTS.read_bytes()),
        "action": "keep_out_of_release_and_new_cohort" if not screening["qualified"] else "eligible_for_independent_validation",
    }
    frozen.write_json(output_dir / "decision.json", decision)
    print(frozen.canonical(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
