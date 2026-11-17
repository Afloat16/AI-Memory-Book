"""Build the isolated C control for the bounded candidate metadata experiment."""
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
    parser.add_argument("--python-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    package = args.python_source.resolve() / "memory_book"
    if not (package / "store.py").is_file():
        raise ValueError("--python-source must contain the frozen memory_book package")
    if sys.implementation.name != "cpython" or sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise ValueError("The experiment requires GIL-enabled CPython")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Choose a new build directory; do not overwrite experimental evidence")
    output.mkdir(parents=True)
    binary = output / ("_language_c_metadata" + sysconfig.get_config_var("EXT_SUFFIX"))
    flags = ["-shared", "-fPIC", "-O3", "-DNDEBUG", "-g", "-fwrapv", "-Wall"]
    compiler = shlex.split(args.cc)
    command = compiler + flags + ["-I" + sysconfig.get_path("include"),
        str(HERE / "_language_c_metadata.c"), "-lm", "-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True)
    (output / "compile.log").write_text(result.stdout + result.stderr)
    manifest = {
        "candidate": "c-bounded-metadata", "status": "completed" if result.returncode == 0 else "failed",
        "command": command, "common_c_flags": flags, "fast_math": False,
        "compiler": subprocess.check_output(compiler + ["--version"], text=True),
        "python": sys.version, "platform": platform.platform(),
        "source_sha256": sha(HERE / "_language_c_metadata.c"), "builder_sha256": sha(__file__),
        "reference_store_sha256": sha(package / "store.py"),
        "binary_sha256": sha(binary) if result.returncode == 0 else None,
        "binary_bytes": binary.stat().st_size if result.returncode == 0 else None,
        "returncode": result.returncode,
    }
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if result.returncode:
        raise RuntimeError("Compilation failed; see " + str(output / "compile.log"))
    print(json.dumps({"binary": str(binary), "sha256": manifest["binary_sha256"]}))


if __name__ == "__main__":
    main()
