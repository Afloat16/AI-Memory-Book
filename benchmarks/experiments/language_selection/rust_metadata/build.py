"""Build the isolated Rust translation of bounded candidate metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Choose a new build directory; never replace an earlier build")
    source = args.python_source.resolve()
    if not (source / "memory_book/store.py").is_file():
        raise SystemExit("--python-source must contain memory_book/store.py")
    output.mkdir(parents=True)
    env = os.environ.copy()
    env["PYO3_PYTHON"] = sys.executable
    env["CARGO_TARGET_DIR"] = str(output / "target")
    command = [args.cargo, "build", "--release", "--locked", "--manifest-path", str(HERE / "Cargo.toml")]
    with (output / "cargo.log").open("w") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = output / ("_language_rust_metadata" + sysconfig.get_config_var("EXT_SUFFIX"))
    shutil.copyfile(output / "target/release/liblanguage_rust_metadata.so", binary)
    manifest = {
        "schema_version": 1, "candidate": "rust-bounded-candidate-metadata",
        "scope": "Complete existing method with identical Python SQLite calls and ordinary-domain fallback",
        "source": str(source), "store_sha256": sha(source / "memory_book/store.py"),
        "binary": str(binary), "binary_sha256": sha(binary), "binary_bytes": binary.stat().st_size,
        "source_sha256": {str(path.relative_to(HERE)): sha(path) for path in
            [HERE / "src/lib.rs", HERE / "Cargo.toml", HERE / "Cargo.lock", HERE / "adapter.py", Path(__file__)]},
        "command": command, "python": sys.version, "python_executable": sys.executable,
        "cargo": subprocess.check_output([args.cargo, "--version"], env=env, text=True).strip(),
        "rustc": subprocess.check_output(["rustc", "--version"], env=env, text=True).strip(),
        "opt_level": 3, "lto": "thin", "codegen_units": 1, "panic": "abort",
    }
    (output / "build.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "binary": str(binary), "sha256": manifest["binary_sha256"]}))


if __name__ == "__main__":
    main()
