"""Build isolated Rust kernels and a mixed C/Rust _native without editing sources.

The generated translation unit includes the unchanged released C source. Its
module definition/state/22 public names are preserved. Exactly six method-table
function pointers are replaced with real Rust C-ABI exports before initialization.
The C-exported language_rust_manifest() exposes all original/replacement pointers
and flags for untimed audit; no trace/probe is installed in timed calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig

HERE = Path(__file__).resolve().parent
NAMES = ("terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions", "fold_excerpt_source", "evidence_units")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--features", default="")
    args = parser.parse_args()
    source = args.package_source.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit("Choose a new output directory; never overwrite a measured build")
    output.mkdir(parents=True)
    env = os.environ.copy()
    env["PYO3_PYTHON"] = sys.executable
    command = [args.cargo, "build", "--release", "--locked", "--manifest-path", str(HERE / "Cargo.toml")]
    if args.features:
        command += ["--features", args.features]
    with (output / "cargo.log").open("w") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    methods = re.findall(r'\{"([a-z_]+)",\s*(native_[a-z_]+),\s*METH_VARARGS,', (source / "_native.c").read_text())
    if len(methods) != 22 or not set(NAMES).issubset(dict(methods)):
        raise SystemExit("Frozen method table does not have the expected 22 entries")
    declarations = "\n".join(f"extern PyObject *rust_{name}(PyObject *, PyObject *);" for name in NAMES)
    originals = ",\n".join(f"    {symbol}" for _, symbol in methods)
    replacements = "\n".join(f'    if (strcmp(native_methods[i].ml_name, "{name}") == 0) native_methods[i].ml_meth = rust_{name};' for name in NAMES)
    shim = f'''/* Generated experimental link unit; no product source edit. */
#define PyInit__native language_original_PyInit__native
#include {json.dumps(str(source / "_native.c"))}
#undef PyInit__native
#include <stdint.h>
{declarations}
static PyCFunction language_original_methods[] = {{
{originals}
}};
PyMODINIT_FUNC PyInit__native(void) {{
    for (int i = 0; native_methods[i].ml_name; i++) {{
{replacements}
    }}
    return language_original_PyInit__native();
}}
PyObject *language_rust_manifest(void) {{
    PyObject *rows = PyList_New(0);
    if (!rows) return NULL;
    for (int i = 0; native_methods[i].ml_name; i++) {{
        PyObject *row = Py_BuildValue("{{s:s,s:K,s:K,s:i,s:i}}",
            "name", native_methods[i].ml_name,
            "original_address", (unsigned long long)(uintptr_t)language_original_methods[i],
            "effective_address", (unsigned long long)(uintptr_t)native_methods[i].ml_meth,
            "flags", native_methods[i].ml_flags,
            "replaced", native_methods[i].ml_meth != language_original_methods[i]);
        if (!row || PyList_Append(rows, row) < 0) {{ Py_XDECREF(row); Py_DECREF(rows); return NULL; }}
        Py_DECREF(row);
    }}
    return rows;
}}
'''
    (output / "link.c").write_text(shim)
    ext = sysconfig.get_config_var("EXT_SUFFIX")
    release = Path(env.get("CARGO_TARGET_DIR", HERE / "target")) / "release"
    independent = output / ("_language_rust" + ext)
    shutil.copyfile(release / "liblanguage_rust.so", independent)
    native = output / ("_native" + ext)
    flags = ["-shared", "-fPIC", "-O3", "-DNDEBUG", "-g", "-fwrapv", "-Wall", "-I" + sysconfig.get_path("include")]
    compiler = shlex.split(env.get("CC", "gcc"))
    cc_command = compiler + flags + [str(output / "link.c"), str(release / "liblanguage_rust.a"), "-ldl", "-lpthread", "-lm", "-o", str(native)]
    with (output / "cc.log").open("w") as log:
        subprocess.run(cc_command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)
    inputs = {str(p.relative_to(source)): sha(p) for p in sorted(source.glob("_native*")) if p.suffix in {".c", ".h"}}
    manifest = {
        "schema_version": 1, "variant": "rust_same_boundary", "features": args.features,
        "replaced_methods": list(NAMES),
        "unmodified_method_names": [n for n, _ in methods if n not in NAMES],
        "method_count": 22, "package_source": str(source), "native_source_sha256": inputs,
        "rust_sources_sha256": {str(p.relative_to(HERE)): sha(p) for p in sorted((HERE / "src").rglob("*.rs"))},
        "cargo_toml_sha256": sha(HERE / "Cargo.toml"), "cargo_lock_sha256": sha(HERE / "Cargo.lock"),
        "build_script_sha256": sha(__file__), "link_source_sha256": sha(output / "link.c"),
        "commands": [command, cc_command], "python": sys.version, "python_executable": sys.executable,
        "cargo": subprocess.check_output([args.cargo, "--version"], env=env, text=True).strip(),
        "compiler": subprocess.check_output(compiler + ["--version"], env=env, text=True).splitlines()[0],
        "native_sha256": sha(native), "independent_sha256": sha(independent),
        "native_bytes": native.stat().st_size, "independent_bytes": independent.stat().st_size,
        "build_options": {"rust_opt_level": 3, "rust_lto": "thin", "rust_codegen_units": 1, "rust_panic": "abort", "c_flags": flags},
    }
    (output / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output_dir": str(output), "native_sha256": manifest["native_sha256"], "independent_sha256": manifest["independent_sha256"]}))


if __name__ == "__main__":
    main()
