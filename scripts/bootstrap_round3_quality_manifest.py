"""Rebuild the lost small recovery manifest from fixed, already-scored Git data.

This bootstrap is new recovery code and must pass Hosted verification before
use. It never imports or calls the memory runtime. It preserves the registered
old experiment and reconstructs its known complete JSON, not a new score run.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import recover_round3_quality as recovery
from scripts import round3_project_stats as frozen

RAW_SHA256 = "5319394dbff4ba833ac7795219947ae26a550bb2010620aab38a2c037fd07f9b"
RAW_BYTES = 45402100
GZIP_BYTES = 5789429
PREFIX_BYTES = 1179648
PREFIX_JSON_BYTES = 9401417
MANIFEST_BYTES = 27269
MODE_NAMES = ("global_default", "project_local_fts_statistics")
COUNTS = {"synthetic61": 168, "authored36": 36, "public1015": 1015, "hotpot128": 128}
GROUPS = {
    ("hotpot128", "global_default"): 0,
    ("hotpot128", "project_local_fts_statistics"): 2,
    ("public1015", "global_default"): 4,
    ("public1015", "project_local_fts_statistics"): 6,
}


def require(condition, message):
    recovery.require(condition, message)


def read_sources():
    """Read exact regular blobs through immutable commit trees, with no globs."""
    worker_commit = recovery.COMMITS["first_four_workers"]
    transfer_commit = recovery.COMMITS["interrupted_transfer"]
    origin = recovery.git("remote", "get-url", "origin").decode().strip()
    require(origin in ("https://github.com/Afloat16/AI-Memory-Book",
                       "https://github.com/Afloat16/AI-Memory-Book.git",
                       "git@github.com:Afloat16/AI-Memory-Book.git"), "Unexpected recovery origin")
    recovery.git("fetch", "origin", "--no-tags", "--no-write-fetch-head",
                 "--filter=blob:none", worker_commit, transfer_commit)
    expected = []
    for cohort in ("synthetic61", "authored36"):
        for mode in MODE_NAMES:
            for suffix in (".worker.json.gz", ".ledger.jsonl"):
                expected.append((worker_commit, "benchmarks/reports/" + recovery.RUN + "-" + cohort + "-" + mode + suffix))
    base = "benchmarks/transfers/" + recovery.RUN + "/chunks/"
    for group, count in enumerate((1, 2, 1, 2, 6, 12, 6, 12, 6)):
        expected.extend((transfer_commit, base + f"{group:02d}-{part:03d}.bin") for part in range(count))
    identities = {}
    for commit, path in expected:
        tree = recovery.git("ls-tree", "-z", commit, "--", path)
        require(tree.endswith(b"\0") and tree.count(b"\0") == 1, "Missing or ambiguous fixed source path")
        metadata, found_path = tree[:-1].decode().split("\t")
        mode, kind, blob = metadata.split()
        require((mode, kind, found_path) == ("100644", "blob", path)
                and re.fullmatch(r"[0-9a-f]{40}", blob), "Unexpected source tree entry")
        identities[(commit, path)] = blob
    recovery.git("-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags",
                 "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none",
                 "--stdin", input=("\n".join(sorted(set(identities.values()))) + "\n").encode())
    parts, contents = {}, {}
    for (commit, path), blob in identities.items():
        raw = recovery.git("cat-file", "blob", blob)
        require(hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == blob,
                "Corrupt Git source blob")
        parts[(commit, path)] = {"commit": commit, "path": path, "git_blob_sha1": blob,
                                "bytes": len(raw), "sha256": recovery.sha(raw)}
        contents[(commit, path)] = raw
    require(len(parts) == 56, "Require the original 56 source objects")
    return parts, contents


def bootstrap():
    require(not recovery.MANIFEST.exists(), "Preserve the existing committed recovery manifest")
    declaration, binding = frozen.registered(frozen.BINDING)
    parts, contents = read_sources()
    worker_commit = recovery.COMMITS["first_four_workers"]
    transfer_commit = recovery.COMMITS["interrupted_transfer"]
    base = "benchmarks/transfers/" + recovery.RUN + "/chunks/"
    files, restored = [], {}
    identities = sorted((cohort, mode) for cohort in COUNTS for mode in MODE_NAMES)
    for cohort, mode in identities:
        for kind, suffix in (("worker", ".worker.json.gz"), ("ledger", ".ledger.jsonl")):
            name = recovery.RUN + "-" + cohort + "-" + mode + suffix
            if cohort in ("synthetic61", "authored36"):
                selected = [parts[(worker_commit, "benchmarks/reports/" + name)]]
            else:
                group = GROUPS[(cohort, mode)] + int(kind == "worker")
                selected = [entry for (commit, path), entry in sorted(parts.items())
                            if commit == transfer_commit and path.startswith(base + f"{group:02d}-")]
            raw = b"".join(contents[(part["commit"], part["path"])] for part in selected)
            require(raw, "An original worker or ledger is missing")
            if kind == "worker":
                worker = json.loads(gzip.decompress(raw))
                require((worker["cohort"], worker["mode"], worker["status"]) == (cohort, mode, "completed")
                        and [len(config["rows"]) for config in worker["configurations"]] == [COUNTS[cohort]] * 3,
                        "An original completed worker identity or row count differs")
            else:
                require(recovery.sha(raw) == worker["ledger_sha256"], "Original worker/ledger hash differs")
            restored[name] = raw
            files.append({"name": name, "kind": kind, "cohort": cohort, "mode": mode,
                          "bytes": len(raw), "sha256": recovery.sha(raw), "parts": selected})
    selected = [entry for (commit, path), entry in sorted(parts.items())
                if commit == transfer_commit and path.startswith(base + "08-")]
    prefix = b"".join(contents[(part["commit"], part["path"])] for part in selected)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    plain_prefix = decoder.decompress(prefix)
    require(len(prefix) == PREFIX_BYTES and len(plain_prefix) == PREFIX_JSON_BYTES and not decoder.eof,
            "Interrupted aggregate prefix differs")
    report = recovery.complete_prefix_fields(plain_prefix)
    require(report["plan"] == declaration and report["binding"] == binding
            and report["binding_sha256"] == recovery.sha(frozen.BINDING.read_bytes())
            and report["evaluator_hashes"] == frozen.helper_hashes(), "Original aggregate/source bindings differ")
    with tempfile.TemporaryDirectory(prefix="v031-quality-manifest-") as temporary:
        directory = Path(temporary)
        for name, raw in restored.items():
            (directory / name).write_bytes(raw)
        output = directory / (recovery.RUN + ".json.gz")
        report["workers"] = []
        for cohort, mode in frozen.expected_order():
            raw_path, ledger_path = frozen.worker_paths(output, cohort, mode)
            worker = frozen.adopt_worker(raw_path, ledger_path, 0)
            frozen.verify_worker_files(worker, directory)
            report["workers"].append(worker)
        validation = frozen.validate(report, ledger_root=directory)
        require(validation == report["validation"] and validation["passed"]
                and validation["workers"] == 8 and validation["calls"] == 8082,
                "Original eight-worker matrix failed validation")
        require(report["comparisons"] == frozen.comparisons(report)
                and report["screening"] == frozen.screen(report["comparisons"], valid=True),
                "Original comparisons or screen changed")
        screen = report["screening"]
        require(screen["status"] == "rejected_loss_or_no_gain" and screen["qualified"] is False
                and len(screen["losses"]) == 14 and len(screen["gains"]) == 10, "Original rejection differs")
        raw = (frozen.canonical(report) + "\n").encode()
        packed = gzip.compress(raw, mtime=0)
        require(len(raw) == RAW_BYTES and recovery.sha(raw) == RAW_SHA256 and len(packed) == GZIP_BYTES
                and raw.startswith(plain_prefix) and packed.startswith(prefix),
                "Known complete aggregate or byte prefix differs; do not weaken the pins")
    manifest = {
        "schema_version": 1, "protocol": recovery.PROTOCOL, "repository": "Afloat16/AI-Memory-Book",
        "original_run": recovery.RUN, "source_commits": recovery.COMMITS,
        "frozen_evaluator_commit": "3b039c53dd2ee6a75be8c28aee9dcf202889958c",
        "binding_sha256": recovery.sha(frozen.BINDING.read_bytes()), "files": files,
        "aggregate_prefix": {"bytes": len(prefix), "sha256": recovery.sha(prefix),
                             "decompressed_bytes": len(plain_prefix), "parts": selected},
        "expected_aggregate": {"name": recovery.RUN + ".json.gz", "uncompressed_bytes": len(raw),
                               "uncompressed_sha256": recovery.sha(raw), "compressed_bytes": len(packed),
                               "compressed_sha256": recovery.sha(packed)},
        "expected_decision": {"workers": 8, "calls": 8082, "status": "rejected_loss_or_no_gain",
                              "qualified": False, "loss_checks": 14, "aggregate_improvements": 10},
        "policy": "Recover saved bytes only. No retrieval, generation, threshold search, failed-worker replay or source modification. Original metadata and every completed worker/ledger are preserved. Both original compressed and decompressed aggregate prefixes must match. Frozen strict audit is mandatory.",
    }
    recovery.validate_manifest(manifest)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    require(len(manifest_bytes) == MANIFEST_BYTES, "Original manifest structure/size differs")
    recovery.exclusive(recovery.MANIFEST, manifest_bytes)
    print(json.dumps({"bootstrap": "verified-existing-evidence", "manifest": str(recovery.MANIFEST),
                      "manifest_sha256": recovery.sha(manifest_bytes), "source_objects": len(parts),
                      "replayed_calls": 0, "raw_json_sha256": recovery.sha(raw),
                      "compressed_sha256": recovery.sha(packed), "original_gzip_prefix_exact": True}))


if __name__ == "__main__":
    bootstrap()
