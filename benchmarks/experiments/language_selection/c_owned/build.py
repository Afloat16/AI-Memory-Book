"""Compile an isolated C-owned window control, without editing product sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import sysconfig


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    source = args.native_source.resolve()
    if source.is_dir():
        source /= "_native.c"
    if source.name != "_native.c" or not source.is_file():
        raise ValueError("--native-source must identify the frozen _native.c file")
    if sys.implementation.name != "cpython" or sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise ValueError("This experiment requires GIL-enabled CPython")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Choose a new output directory; never overwrite a measured build")
    output.mkdir(parents=True)
    binary = output / ("_language_c_owned" + sysconfig.get_config_var("EXT_SUFFIX"))
    common_flags = ["-shared", "-fPIC", "-O3", "-DNDEBUG", "-g", "-fwrapv", "-Wall"]
    command = [*shlex.split(args.cc), *common_flags,
               "-I" + sysconfig.get_path("include"), "-I" + str(source.parent),
               str(HERE / "_language_c_owned.c"), "-lm", "-o", str(binary)]
    run = subprocess.run(command, capture_output=True, text=True)
    (output / "compile.log").write_text(run.stdout + run.stderr)
    manifest = {
        "candidate": "c-owned-window", "status": "completed" if run.returncode == 0 else "failed",
        "command": command, "common_c_flags": common_flags, "fast_math": False,
        "python": sys.version, "platform": platform.platform(),
        "source_sha256": sha(HERE / "_language_c_owned.c"), "builder_sha256": sha(__file__),
        "native_reference_inputs": {str(p): sha(p) for p in sorted(source.parent.glob("_native*")) if p.suffix in (".c", ".h")},
        "shared_window_adapter_sha256": sha(HERE.parent / "rust/window_adapter.py"),
        "rust_window_comparison_source_sha256": sha(HERE.parent / "rust/src/window.rs"),
        "compiler": subprocess.check_output([*shlex.split(args.cc), "--version"], text=True),
        "returncode": run.returncode,
        "binary_sha256": sha(binary) if run.returncode == 0 else None,
        "binary_bytes": binary.stat().st_size if run.returncode == 0 else None,
        "entry_points": ["excerpt_window_owned", "log1p_values", "positive_fsum"],
        "ordinary_domain": {"unique_terms_max": 64, "hits_per_term_max": 40, "hits_max": 2560,
                            "position_sum_max": "min(2**53-1, PY_SSIZE_T_MAX)", "exact_codepoint_semantics": True},
        "boundary": "Complete ordinary-query evidence units, window candidates, native frequency/placement scores, and rendering; same shared adapter as Rust-owned; other 21 production C methods unchanged.",
        "implementation": {"native_allocation": "malloc/realloc with checked capacity, no Python score/unit objects",
                           "frequency": "native libm log1p + error-free partial summation; no frequency cache",
                           "starts_sort": "C qsort and in-place dedup, same numerical ordering as Rust sort_unstable/dedup"},
    }
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if run.returncode:
        raise RuntimeError(f"C-owned compilation failed; see {output / 'compile.log'}")
    print(json.dumps({"binary": str(binary), "sha256": manifest["binary_sha256"], "bytes": manifest["binary_bytes"]}))


if __name__ == "__main__":
    main()
