"""Post-run Memvid API diagnosis; never a replacement engineering score.

The formal attempt1 remains unchanged. This probe retains every input and full
native result while distinguishing scope/indexing from query-parser behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import traceback

from benchmarks import engineering_workflow as workflow
from benchmarks.competitors.extended_lexical import MemvidLexical, memvid_record, package_identity
from benchmarks.competitors.memory_systems import write_json
from benchmarks.competitors.memory_systems_worker import block_python_network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    documents = json.loads(args.documents.read_text(encoding="utf-8"))
    queries = [
        "What is the current edge_policy for this routing kernel?",
        "edge_policy", "routing", "current edge_policy",
        "What is the current edge_policy for this routing kernel",
        '"edge_policy"', "edge_policy routing kernel",
    ]
    report = {"status": "started", "evidence_level": "post-run API diagnosis, not a quality evaluation",
              "formal_attempt": "attempt1 is unchanged; these observations never enter its quality table",
              "documents_sha256": workflow.sha(documents),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "queries": queries, "scopes": ["memory-book://routing-online/", None], "samples": []}
    write_json(args.output / "report.json", report)
    memory = None
    try:
        report["packages"] = package_identity()
        attempts = block_python_network()
        state = args.output / "state"
        state.mkdir()
        memory = MemvidLexical(documents, state)
        report["metadata"] = memory.metadata
        lookup = {doc["id"]: doc for doc in documents}
        for query in queries:
            for scope in report["scopes"]:
                sample = {"query": query, "scope": scope}
                report["samples"].append(sample)
                write_json(args.output / "report.json", report)
                try:
                    native = memory.memory.find(query, k=5, mode="lex", snippet_chars=100000, scope=scope)
                    sample["native"] = native
                    frames = [memory.memory.frame(hit["uri"]) for hit in native["hits"]]
                    sample["native_frames"] = frames
                    write_json(args.output / "report.json", report)
                    sample["mapped_records"] = [memvid_record(
                        hit, frame, lookup, json.loads(frame["extra_metadata"]["project"]))
                        for hit, frame in zip(native["hits"], frames)]
                    sample["source_mapping_valid"] = True
                except Exception:
                    sample["error"] = traceback.format_exc()
                write_json(args.output / "report.json", report)
        report["python_network_attempts"] = attempts
        report["status"] = "completed"
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
    finally:
        if memory is not None:
            memory.close()
        write_json(args.output / "report.json", report)
    print(json.dumps({"status": report["status"], "samples": [
        {key: sample.get(key) for key in ("query", "scope", "error")} |
        {"native_hits": len(sample.get("native", {}).get("hits", []))}
        for sample in report["samples"]]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
