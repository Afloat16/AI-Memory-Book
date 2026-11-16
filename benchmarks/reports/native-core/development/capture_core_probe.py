"""Capture native-core wrapper identity only; never collect performance samples."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

EVALUATOR_COMMIT = "07e981d1ac99cb284a399aa46dd00111bb9c75da"
BASELINE_COMMIT = "56eccd8c3a6f1d5637664607936da2595ce50c62"
# The actual expected output is supplied explicitly by the caller when desired.
CHILD = r'''
import json, pathlib, sys
repo, source, label = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
sys.path[:0] = [str(source), str(repo)]
from scripts import native_core_performance as perf
import memory_book
from memory_book import _text_backend, text, store, segmentation, token_budget
assert pathlib.Path(memory_book.__file__).resolve().parent == source.resolve() / "memory_book"
assert _text_backend.REQUESTED_BACKEND == _text_backend.BACKEND_NAME == "native"
native = _text_backend.NATIVE
assert native is not None
binary = pathlib.Path(native.__file__).resolve()
assert binary.parent == source.resolve() / "memory_book"
available = sorted(name for name in dir(native) if not name.startswith("_"))
assert available == sorted(perf.PROBE_HELPERS[label])
outputs = perf.common_probe_suite()
probe = perf.dispatch_probe(text, native, None)
assert perf.digest(outputs) == probe["outputs_sha256"]
modules = {"text": text, "store": store, "segmentation": segmentation, "token_budget": token_budget}
bindings = {name: getattr(module, "_NATIVE") is native for name, module in modules.items() if hasattr(module, "_NATIVE")}
assert bindings == dict.fromkeys(("text",) if label == "baseline" else tuple(modules), True)
print(perf.dump({"backend": "native", "available_functions": available, "wrapper_bindings": bindings,
                "binary_sha256": perf.sha(binary.read_bytes()), "dispatch_probe": probe,
                "public_wrapper_outputs": outputs}))
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--expected-output")
    args = parser.parse_args()
    if args.expected_output is not None and (len(args.expected_output) != 64
            or any(character not in "0123456789abcdef" for character in args.expected_output)):
        parser.error("--expected-output must be exactly 64 lowercase hexadecimal characters")
    root, work = args.repository.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root)
    if git("rev-parse", "HEAD").decode().strip() != EVALUATOR_COMMIT:
        raise RuntimeError("Capture evaluator checkout differs")
    sys.path.insert(0, str(root))
    from scripts import native_core_performance as perf
    if (root / "scripts/native_core_performance.py").read_bytes() != git("show", EVALUATOR_COMMIT + ":scripts/native_core_performance.py"):
        raise RuntimeError("Capture evaluator bytes differ from frozen development checkpoint")
    environment = os.environ.copy()
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    environment.update(CC="gcc", MEMORY_BOOK_BUILD_NATIVE="1", MEMORY_BOOK_TEXT_BACKEND="native",
                       PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", TMPDIR=str(work))
    sources = {"baseline": BASELINE_COMMIT}
    if args.candidate:
        if len(args.candidate) != 40 or any(c not in "0123456789abcdef" for c in args.candidate):
            raise ValueError("Use an exact candidate source commit")
        sources["candidate"] = args.candidate
    report = {"schema": "native-core-development-probe-capture-v1",
        "purpose": "Untimed wrapper equivalence and helper identity capture only; no performance result",
        "capture_runner_sha256": sha(Path(__file__).read_bytes()), "evaluator_commit": EVALUATOR_COMMIT,
        "requested_expected_output": args.expected_output, "requested_candidate": args.candidate,
        "evaluator_sha256": sha((root / "scripts/native_core_performance.py").read_bytes()),
        "environment": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                        "compiler": subprocess.check_output(["gcc", "--version"], text=True)},
        "sources": {}, "status": "running", "error": None}
    try:
        for label, commit in sources.items():
            destination = work / label
            destination.mkdir()
            names = git("ls-tree", "-r", "--name-only", commit, "src/memory_book", *perf.BUILD_FILES).decode().splitlines()
            for name in names:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git("show", commit + ":" + name))
            before = {name: sha((destination / name).read_bytes()) for name in names}
            record = {"commit": commit, "source_files_before": before, "status": "building"}
            report["sources"][label] = record
            command = [sys.executable, "setup.py", "build_ext", "--inplace",
                       "--build-temp", str(work / ("build-temp-" + label))]
            record["build_command"] = command
            with (destination / "build.log").open("xb") as log:
                built = subprocess.run(command, cwd=destination, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=180)
            record.update(build_returncode=built.returncode,
                          build_log_sha256=sha((destination / "build.log").read_bytes()))
            if built.returncode != 0:
                raise RuntimeError("Native capture build failed: " + label)
            manifest = perf.source_manifest(destination / "src", {"commit": commit, "backend": "native"})
            record["source_manifest_before"] = manifest
            record["status"] = "probing"
            with (destination / "probe.json").open("xb") as output, (destination / "probe.log").open("xb") as log:
                measured = subprocess.run([sys.executable, "-c", CHILD, str(root), str(destination / "src"), label],
                    cwd=root, env=environment, stdout=output, stderr=log, timeout=180)
            record.update(probe_returncode=measured.returncode,
                          probe_sha256=sha((destination / "probe.json").read_bytes()),
                          probe_log_sha256=sha((destination / "probe.log").read_bytes()))
            if measured.returncode != 0:
                raise RuntimeError("Native capture probe failed: " + label)
            probe = perf.read(destination / "probe.json")
            record["probe"] = probe
            record["source_manifest_after"] = perf.source_manifest(destination / "src", {"commit": commit, "backend": "native"})
            record["source_and_binary_unchanged"] = record["source_manifest_after"] == manifest
            if not record["source_and_binary_unchanged"] or before != record["source_manifest_after"]["source_files"]:
                raise RuntimeError("Capture source or binary changed")
            if probe["binary_sha256"] not in manifest["native_binaries"].values():
                raise RuntimeError("Capture loaded an unbound native binary")
            record["status"] = "completed"
        output_hashes = {record["probe"]["dispatch_probe"]["outputs_sha256"] for record in report["sources"].values()}
        report["complete_wrapper_output_equivalence"] = len(output_hashes) == 1
        if len(output_hashes) != 1:
            raise RuntimeError("Baseline and candidate wrapper outputs differ")
        if args.expected_output and output_hashes != {args.expected_output}:
            raise RuntimeError("Wrapper outputs differ from the explicitly requested diagnostic digest")
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        with (work / "capture.json").open("xb") as output:
            output.write(raw)
        print(json.dumps({"status": report["status"], "output": str(work / "capture.json"),
                          "sha256": sha(raw), "bytes": len(raw)}))


if __name__ == "__main__":
    main()
