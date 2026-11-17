"""Build, install and verify one native release matrix cell.

The workflow calls this once with each setup-python executable. This helper
does not publish, retry a cell, alter the runtime or change receipt acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import native_release

SUITES = (
    "tests.test_native_backend",
    "tests.test_native_identifier_backend",
    "tests.test_native_excerpt_backend",
    "tests.test_native_lexical_backend",
    "tests.test_native_window_backend",
    "tests.test_native_ranking_backend",
    "tests.test_native_source_backend",
    "tests.test_native_segmentation_backend",
)
EXPECTED_TESTS = 144
# These optional dependencies are not installed by the release cell. Required
# native tests must never disappear behind a broad extension-availability skip.
ALLOWED_SKIPS = (
    ("test_token_caps_keep_complete_payload_counts_and_source_spans",
     "tests.test_native_backend.NativeMemoryBookEquivalenceTests", "Install .[tokens]"),
    ("test_both_token_encoders_keep_exact_budgets_and_source_refs",
     "tests.test_native_ranking_backend.NativeStoreEquivalenceTests", "Install .[tokens]"),
    ("test_available_shared_gil_subinterpreters_keep_main_module_working",
     "tests.test_native_segmentation_backend.NativeSegmentationModuleStateTests",
     "_xxsubinterpreters is not available in this Python build"),
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_report(path, report):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def test_summary(output):
    """Describe only the unittest results actually present in captured output."""
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output).replace("\r\n", "\n")
    counts = re.findall(r"^Ran (\d+) tests? in [^\r\n]+$", plain, re.MULTILINE)
    endings = re.findall(r"^(OK(?: \([^\r\n]*\))?|FAILED(?: \([^\r\n]*\))?)$",
                         plain, re.MULTILINE)
    ending = endings[-1] if endings else None
    skipped = None
    if ending:
        match = re.search(r"\bskipped=(\d+)", ending)
        skipped = int(match.group(1)) if match else 0
    return {
        "tests_run": int(counts[-1]) if counts else None,
        "test_summary_count": len(counts),
        "outcome_summary_count": len(endings),
        "skipped": skipped,
        "summary": ending,
        "successful_summary": bool(ending and ending.startswith("OK")),
        "skipped_test_lines": [line for line in plain.splitlines() if "... skipped " in line],
        "failure_lines": [line for line in plain.splitlines()
                          if re.match(r"^(?:ERROR|FAIL|UNEXPECTED SUCCESS): ", line)
                          or "ERROR: AddressSanitizer" in line],
    }


def validate_test_result(summary, returncode):
    """Require one complete run with only explicitly allowed optional skips."""
    require(returncode == 0 and summary["successful_summary"]
            and summary["tests_run"] == EXPECTED_TESTS,
            f"The installed native test run must complete all {EXPECTED_TESTS} tests successfully")
    require(summary["test_summary_count"] == summary["outcome_summary_count"] == 1,
            "Expected exactly one installed native test run and outcome")
    require(re.fullmatch(r"OK(?: \(skipped=[0-9]+\))?", summary["summary"]) is not None
            and not summary["failure_lines"],
            "Native tests must not contain failures, expected failures or unexpected successes")
    require(len(summary["skipped_test_lines"]) == summary["skipped"],
            "Native skipped-test lines and summary count differ")
    observed = set()
    for line in summary["skipped_test_lines"]:
        matches = [index for index, (method, cls, reason) in enumerate(ALLOWED_SKIPS)
                   if line in (f"{method} ({cls}) ... skipped {reason!r}",
                               f"{method} ({cls}.{method}) ... skipped {reason!r}")]
        require(len(matches) == 1 and matches[0] not in observed,
                "Unexpected or duplicate skipped native testcase: " + line)
        observed.add(matches[0])


def clean_generated(root):
    """Clear only untracked build products; preserve earlier cell evidence."""
    paths = [root / "build", *root.glob("*.egg-info"), *(root / "src").glob("*.egg-info")]
    package = root / "src" / "memory_book"
    paths += list(package.glob("_native*.so")) + list(package.glob("_native*.pyd"))
    removed = []
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        require(not native_release.legacy.git(root, "ls-files", "--", name),
                "Refuse to remove a tracked build path: " + name)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(name)
    return removed


def run_command(argv, phase, log_path, report, report_path, env, *, check=True):
    entry = {"phase": phase, "command": list(map(str, argv)), "cwd": str(ROOT),
             "started_at_utc": utc(), "returncode": None, "log": log_path.name}
    report["commands"].append(entry)
    save_report(report_path, report)
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=ROOT, env=env, text=True, encoding="utf-8",
                                errors="replace", capture_output=True)
    except OSError as error:
        entry.update(finished_at_utc=utc(), error=str(error))
        log_path.write_text(str(error) + "\n", encoding="utf-8")
        entry.update(log_bytes=log_path.stat().st_size, log_sha256=digest(log_path))
        save_report(report_path, report)
        raise
    output = result.stdout + result.stderr
    log_path.write_text(output, encoding="utf-8")
    entry.update(returncode=result.returncode, finished_at_utc=utc(),
                 elapsed_seconds=time.monotonic() - started,
                 log_bytes=log_path.stat().st_size, log_sha256=digest(log_path))
    save_report(report_path, report)
    print("CELL COMMAND", phase, json.dumps(entry["command"]), flush=True)
    print(output, end="" if output.endswith("\n") else "\n", flush=True)
    if check:
        require(result.returncode == 0, phase + " failed; retained log: " + str(log_path))
    return result, output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-python", required=True, choices=native_release.PYTHON_VERSIONS)
    parser.add_argument("--target", required=True, choices=native_release.TARGETS)
    args = parser.parse_args(argv)
    cell = "cp" + args.expected_python.replace(".", "")
    evidence = ROOT / ".artifacts" / "native-cell-evidence" / args.target / cell
    work = ROOT / ".artifacts" / "native-build-cells" / args.target / cell
    # A repeated invocation must not overwrite a previous cell's result.
    evidence.mkdir(parents=True, exist_ok=False)
    report_path = evidence / "validation.json"
    report = {
        "schema_version": 1, "status": "started", "started_at_utc": utc(),
        "expected_python": args.expected_python, "target": args.target,
        "step_id": os.environ.get("NATIVE_CELL_STEP"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "interpreter": {"executable": sys.executable, "version": sys.version,
                        "implementation": sys.implementation.name,
                        "python_version": ".".join(map(str, sys.version_info[:2])),
                        "setup_python_path": os.environ.get("NATIVE_CELL_PYTHON"),
                        "setup_python_version": os.environ.get("NATIVE_CELL_RESOLVED_VERSION")},
        "commands": [], "tests": None, "receipt": None,
    }
    save_report(report_path, report)
    try:
        actual = ".".join(map(str, sys.version_info[:2]))
        require(actual == args.expected_python, "The selected interpreter differs from --expected-python")
        require(sys.implementation.name == "cpython", "The cell requires CPython")
        requested = os.environ.get("NATIVE_CELL_PYTHON")
        require(requested and Path(requested).is_absolute()
                and os.path.samefile(requested, sys.executable),
                "The running executable differs from setup-python's absolute output")
        require(native_release._host_target() == args.target, "Native runner architecture differs")
        require(os.environ.get("MEMORY_BOOK_BUILD_NATIVE") == "1", "Native compilation must be required")
        identity, sources, inputs = native_release._portable_identity(ROOT)
        require(identity["commit"] == os.environ.get("GITHUB_SHA"), "Source differs from workflow head")
        report["source"] = {**identity, "files_sha256": native_release.file_hashes(inputs)}
        work.mkdir(parents=True, exist_ok=False)
        raw, repaired = work / "raw", work / "repaired"
        raw.mkdir()
        repaired.mkdir()
        report["cleared_generated_paths"] = clean_generated(ROOT)
        env = os.environ.copy()
        build_log = evidence / ("native-build-" + args.target + "-" + cell + ".log")
        env["NATIVE_BUILD_LOG"] = str(build_log)
        report["build_log"] = build_log.name
        save_report(report_path, report)

        run_command([sys.executable, "-m", "pip", "install", "setuptools==80.9.0",
                     "wheel==0.45.1", "build==1.3.0"],
                    "build-tools", evidence / "tools.log", report, report_path, env)
        if sys.platform == "linux":
            run_command([sys.executable, "-m", "pip", "install",
                         "auditwheel==6.4.2", "patchelf==0.17.2.4"],
                        "abi-tools", evidence / "abi-tools.log", report, report_path, env)
        if sys.platform == "darwin":
            architecture = "arm64" if args.target == "macos_arm64" else "x86_64"
            minimum = (11, 0) if architecture == "arm64" else (10, 9)
            configured = tuple(int(part) for part in
                               sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET").split(".")[:2])
            deployment = ".".join(map(str, max(minimum, configured)))
            env.update(ARCHFLAGS="-arch " + architecture, MACOSX_DEPLOYMENT_TARGET=deployment,
                       _PYTHON_HOST_PLATFORM="macosx-" + deployment + "-" + architecture)
            report["macos_build"] = {"architecture": architecture, "deployment_target": deployment}
        run_command([sys.executable, "-m", "pip", "wheel", "--verbose", "--no-deps",
                     "--no-build-isolation", "--wheel-dir", str(raw), "."],
                    "compile-wheel", build_log, report, report_path, env)
        wheels = list(raw.glob("*.whl"))
        require(len(wheels) == 1 and "none-any" not in wheels[0].name,
                "Expected exactly one newly compiled native wheel")
        if sys.platform == "linux":
            architecture = "aarch64" if args.target == "linux_aarch64" else "x86_64"
            run_command([sys.executable, "-m", "auditwheel", "repair", "--only-plat",
                         "--plat", "manylinux_2_17_" + architecture, "--wheel-dir",
                         str(repaired), str(wheels[0])],
                        "repair-wheel", evidence / "repair.log", report, report_path, env)
        else:
            shutil.copy2(wheels[0], repaired / wheels[0].name)
        wheels = list(repaired.glob("*.whl"))
        require(len(wheels) == 1, "Expected one repaired native wheel")
        wheel = wheels[0]
        if sys.platform == "darwin":
            with zipfile.ZipFile(wheel) as archive, tempfile.TemporaryDirectory(prefix="native-macho-") as location:
                binaries = [name for name in archive.namelist()
                            if name.startswith("memory_book/_native.") and name.endswith(".so")]
                require(len(binaries) == 1, "Expected one Mach-O extension")
                binary = Path(location) / Path(binaries[0]).name
                binary.write_bytes(archive.read(binaries[0]))
                result, _ = run_command(["lipo", "-archs", str(binary)], "macho-slices",
                                        evidence / "architecture.log", report, report_path, env)
                slices = result.stdout.split()
                require(slices == [architecture], "Mach-O slices differ from the native target")
                report["macos_build"]["observed_slices"] = slices
        run_command([sys.executable, "-m", "pip", "install", "--no-deps",
                     "--force-reinstall", str(wheel)],
                    "install-wheel", evidence / "install.log", report, report_path, env)
        run_command([sys.executable, "-I", "-c",
                     "from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'"],
                    "isolated-native-import", evidence / "native-import.log", report, report_path, env)
        result, output = run_command([sys.executable, "-m", "unittest", *SUITES, "-v"],
                                     "installed-native-tests", evidence / "test.log",
                                     report, report_path, env, check=False)
        report["tests"] = {**test_summary(output), "returncode": result.returncode,
                           "suites": list(SUITES), "log": "test.log",
                           "log_sha256": digest(evidence / "test.log")}
        save_report(report_path, report)
        validate_test_result(report["tests"], result.returncode)
        receipt = wheel.with_name(wheel.name + ".receipt.json")
        # The existing receipt command performs its isolated native/source smoke
        # before writing a receipt. Do not change its validator or schema.
        run_command([sys.executable, "scripts/native_release.py", "receipt", "--wheel",
                     str(wheel), "--output", str(receipt), "--target", args.target],
                    "installed-native-smoke-and-receipt", evidence / "receipt.log",
                    report, report_path, env)
        document = json.loads(receipt.read_text(encoding="utf-8"))
        native_release.validate_receipt(receipt, wheel, identity, sources, inputs,
                                        run_id=report["run_id"], run_attempt=report["run_attempt"])
        final = ROOT / ".artifacts" / "native-wheels"
        final.mkdir(exist_ok=True)
        for artifact in (wheel, receipt):
            destination = final / artifact.name
            require(not destination.exists(), "Never overwrite a completed native artifact")
            shutil.copy2(artifact, destination)
        report.update(status="passed", wheel={"filename": wheel.name, "bytes": wheel.stat().st_size,
                      "sha256": digest(wheel), "native_sha256": document["wheel"]["native_sha256"]},
                      receipt={"filename": receipt.name, "sha256": digest(receipt)},
                      runtime_smoke=document["runtime_smoke"])
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        print("Native cell failed:", type(error).__name__, str(error), file=sys.stderr, flush=True)
        returncode = 1
    else:
        returncode = 0
    finally:
        report["finished_at_utc"] = utc()
        save_report(report_path, report)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
