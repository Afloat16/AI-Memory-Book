"""Recover the completed v0.3.1 quality screen from its interrupted Git upload.

This is byte reconstruction and a frozen offline audit, never a retrieval run.
All source commits, part inventories, original file hashes and decision counts
are fixed in the recovery manifest. A missing/corrupt part fails closed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / "benchmarks/experiments/round3-quality-recovery.json"
OUTPUT = ROOT / "benchmarks/reports/round3-project-stats-recovered"
COMMITS = {
    "first_four_workers": "36dbd82c4070968bfb7d7e2b93e1e4793907145e",
    "interrupted_transfer": "2bd5f27d1ae478c1735f36b5354fddd81114182b",
}
PROTOCOL = "v031-quality-transfer-recovery-v1"
RUN = "round3-project-stats-20261112-1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args, input=None):
    return subprocess.run(["git", *args], cwd=ROOT, input=input,
                          check=True, capture_output=True, timeout=180).stdout


def verify_bytes(raw, expected, label):
    require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"],
            "Missing, truncated or changed bytes: " + label)
    if "git_blob_sha1" in expected:
        identity = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        require(identity == expected["git_blob_sha1"], "Git blob identity differs: " + label)


def complete_prefix_fields(raw):
    """Decode only complete top-level fields before the truncated workers list."""
    text = raw.decode("utf-8")
    require(text.startswith("{"), "Aggregate prefix is not an object")
    decoder, fields, position = json.JSONDecoder(), {}, 1
    while position < len(text):
        while position < len(text) and (text[position].isspace() or text[position] == ","):
            position += 1
        key, position = decoder.raw_decode(text, position)
        require(isinstance(key, str) and key not in fields, "Duplicate or invalid aggregate field")
        while position < len(text) and text[position].isspace():
            position += 1
        require(text[position] == ":", "Aggregate field is missing its separator")
        position += 1
        while position < len(text) and text[position].isspace():
            position += 1
        if key == "workers":
            require(text[position] == "[", "Aggregate workers must be an array")
            return fields
        value, position = decoder.raw_decode(text, position)
        fields[key] = value
    raise ValueError("Aggregate prefix does not reach the original workers list")


def validate_manifest(value):
    require(value["schema_version"] == 1 and value["protocol"] == PROTOCOL
            and value["source_commits"] == COMMITS and value["original_run"] == RUN
            and value["repository"] == "Afloat16/AI-Memory-Book", "Recovery identity differs")
    expected = {(cohort, mode, kind)
                for cohort in ("synthetic61", "authored36", "public1015", "hotpot128")
                for mode in ("global_default", "project_local_fts_statistics")
                for kind in ("worker", "ledger")}
    require(len(value["files"]) == 16 and
            {(f["cohort"], f["mode"], f["kind"]) for f in value["files"]} == expected,
            "Require all eight original workers and their ledgers")
    names, parts = set(), []
    for entry in value["files"]:
        suffix = ".worker.json.gz" if entry["kind"] == "worker" else ".ledger.jsonl"
        name = RUN + "-" + entry["cohort"] + "-" + entry["mode"] + suffix
        require(entry["name"] == name and name not in names and entry["parts"], "Worker file identity differs")
        names.add(name)
        parts.extend(entry["parts"])
    parts.extend(value["aggregate_prefix"]["parts"])
    require(len(parts) == 56 and len({(p["commit"], p["path"]) for p in parts}) == 56,
            "Require the exact 56 original Git objects")
    transfer_names = []
    for part in parts:
        if part["commit"] == COMMITS["first_four_workers"]:
            require(part["path"] == "benchmarks/reports/" + Path(part["path"]).name
                    and Path(part["path"]).name in names, "Worker part escapes its registered source")
        else:
            require(part["commit"] == COMMITS["interrupted_transfer"] and part["path"] ==
                    "benchmarks/transfers/" + RUN + "/chunks/" + Path(part["path"]).name,
                    "Transfer part escapes its registered source")
            transfer_names.append(Path(part["path"]).name)
    require(set(transfer_names) == {f"{group:02d}-{part:03d}.bin"
            for group, count in enumerate((1, 2, 1, 2, 6, 12, 6, 12, 6))
            for part in range(count)}, "Transfer has a missing, duplicate or unexpected chunk")
    return parts


def fetch_parts(parts, *, offline):
    if not offline:
        origin = git("remote", "get-url", "origin").decode().strip()
        require(origin in ("https://github.com/Afloat16/AI-Memory-Book.git",
                           "https://github.com/Afloat16/AI-Memory-Book",
                           "git@github.com:Afloat16/AI-Memory-Book.git"), "Unexpected recovery origin")
        git("fetch", "origin", "--no-tags", "--no-write-fetch-head", "--filter=blob:none", *COMMITS.values())
        # Prefetch exact reachable objects together; lazy one-at-a-time blob
        # reads caused the interrupted upload/recovery to be unnecessarily slow.
        ids = sorted({p["git_blob_sha1"] for p in parts})
        git("-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags",
            "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none",
            "--stdin", input=("\n".join(ids) + "\n").encode())
    contents = {}
    for part in parts:
        tree = git("ls-tree", "-z", part["commit"], "--", part["path"])
        expected = f"100644 blob {part['git_blob_sha1']}\t{part['path']}\0".encode()
        require(tree == expected, "Source commit/tree identity differs: " + part["path"])
        raw = git("cat-file", "blob", part["git_blob_sha1"])
        verify_bytes(raw, part, part["path"])
        contents[(part["commit"], part["path"])] = raw
    return contents


def assemble(entry, contents):
    raw = b"".join(contents[(part["commit"], part["path"])] for part in entry["parts"])
    verify_bytes(raw, entry, entry.get("name", "original aggregate prefix"))
    return raw


def exclusive(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def recover(output=OUTPUT, *, offline=False):
    from scripts import round3_project_stats as frozen

    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    parts = validate_manifest(manifest)
    require(not output.exists(), "Preserve the existing recovery; use a fresh output directory")
    declaration, binding = frozen.registered(frozen.BINDING)
    require(sha(frozen.BINDING.read_bytes()) == manifest["binding_sha256"], "Frozen quality binding changed")
    contents = fetch_parts(parts, offline=offline)
    restored = {entry["name"]: assemble(entry, contents) for entry in manifest["files"]}
    prefix = assemble(manifest["aggregate_prefix"], contents)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    plain_prefix = decoder.decompress(prefix)
    require(not decoder.eof and len(plain_prefix) == manifest["aggregate_prefix"]["decompressed_bytes"],
            "The registered interrupted aggregate prefix differs")
    report = complete_prefix_fields(plain_prefix)
    require(report["plan"] == declaration and report["binding"] == binding
            and report["binding_sha256"] == manifest["binding_sha256"]
            and report["evaluator_hashes"] == frozen.helper_hashes(), "Original aggregate identities differ")
    output.mkdir(parents=True)
    for name, raw in restored.items():
        exclusive(output / name, raw)
    report_path = output / manifest["expected_aggregate"]["name"]
    report["workers"] = []
    for cohort, mode in frozen.expected_order():
        raw_path, ledger = frozen.worker_paths(report_path, cohort, mode)
        worker = frozen.adopt_worker(raw_path, ledger, 0)
        frozen.verify_worker_files(worker, output)
        report["workers"].append(worker)
    validation = frozen.validate(report, ledger_root=output)
    require(report["validation"] == validation and validation["passed"], "Original matrix failed the frozen validator")
    require(report["comparisons"] == frozen.comparisons(report), "Original comparisons changed")
    require(report["screening"] == frozen.screen(report["comparisons"], valid=True), "Original screening changed")
    expected = manifest["expected_decision"]
    decision = report["screening"]
    require((validation["workers"], validation["calls"], decision["status"], decision["qualified"],
             len(decision["losses"]), len(decision["gains"])) ==
            (expected["workers"], expected["calls"], expected["status"], expected["qualified"],
             expected["loss_checks"], expected["aggregate_improvements"]), "Recovered decision differs")
    raw = (frozen.canonical(report) + "\n").encode()
    packed = gzip.compress(raw, mtime=0)
    identity = manifest["expected_aggregate"]
    require(len(raw) == identity["uncompressed_bytes"] and sha(raw) == identity["uncompressed_sha256"]
            and len(packed) == identity["compressed_bytes"] and sha(packed) == identity["compressed_sha256"],
            "Reconstructed aggregate bytes differ; use the registered Python 3.12 gzip runtime")
    require(raw.startswith(plain_prefix) and packed.startswith(prefix), "Original aggregate byte prefix changed")
    exclusive(report_path, packed)
    _, summary_path, markdown_path = frozen.result_paths(report_path)
    exclusive(summary_path, (frozen.canonical(frozen.summary(report, raw, packed)) + "\n").encode())
    exclusive(markdown_path, frozen.markdown(report).encode())
    frozen.audit(report_path, frozen.BINDING)
    exclusive(output / "original-aggregate-prefix.bin", prefix)
    exclusive(output / "recovery-inputs.json", manifest_raw)
    files = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
             for p in sorted(output.iterdir()) if p.is_file()}
    proof = {"schema_version": 1, "protocol": PROTOCOL, "status": "recovered-and-audited",
        "replayed_calls": 0, "frozen_audit_passed": True, "source_commits": COMMITS,
        "manifest_sha256": sha(manifest_raw), "original_metadata_retained": True,
        "original_gzip_prefix_exact": True, "original_json_prefix_exact": True,
        "original_gzip_prefix_bytes": len(prefix), "original_json_prefix_bytes": len(plain_prefix),
        "full_report_sha256": sha(raw), "compressed_report_sha256": sha(packed),
        "validation": validation, "screening": decision, "files": files,
        "scope": "Saved bytes reconstructed and independently audited. No retrieval/model calls were replayed. The rejected optional statistics candidate remains excluded."}
    exclusive(output / "recovery-proof.json", (json.dumps(proof, indent=2) + "\n").encode())
    print(json.dumps({"recovery": proof["status"], "output": str(output), "replayed_calls": 0,
                      "validation": validation, "screen": decision["status"], "loss_checks": len(decision["losses"])}))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--offline", action="store_true", help="Use already fetched, verified Git objects")
    args = parser.parse_args()
    recover(args.output_dir, offline=args.offline)


if __name__ == "__main__":
    main()
