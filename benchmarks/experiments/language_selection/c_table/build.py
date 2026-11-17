"""Build only the isolated C-table control; never writes product sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shlex
import struct
import subprocess
import sys
import sysconfig


HERE = Path(__file__).resolve().parent


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--table", type=Path, default=HERE.parent / "rust/data/unicode_fold.bin")
    parser.add_argument("--output", type=Path, default=HERE / "build")
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--rust-library", type=Path)
    args = parser.parse_args()
    source = args.native_source.resolve()
    if source.is_dir():
        source /= "_native.c"
    if source.name != "_native.c" or not source.is_file():
        raise ValueError("--native-source must identify the frozen _native.c file")
    table = args.table.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Choose a new output directory; never overwrite a measured build")
    output.mkdir(parents=True)
    raw = table.read_bytes()
    meta_path = table.with_suffix(".meta.json")
    metadata = json.loads(meta_path.read_text())
    assert raw[:8] == b"MBFOLD01"
    pages, entry_pages, values_count = struct.unpack_from("<III", raw, 8)
    assert pages == 4352
    ucd_version = raw[20:36].split(b"\0", 1)[0].decode("ascii")
    entries_offset = 64 + 2 * pages
    values_offset = entries_offset + entry_pages * 256 * 4
    expected_metadata = {
        "magic": "MBFOLD01", "sha256": sha(raw), "unicode_version": ucd_version,
        "index_offset": 64, "index_count": pages, "entry_page_count": entry_pages,
        "entries_offset": entries_offset, "values_offset": values_offset,
        "values_count": values_count, "bytes": len(raw), "codepoints": 0x110000,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise ValueError(f"Shared table metadata differs: {key}")
    assert len(raw) == values_offset + values_count * 4
    for page in struct.unpack_from(f"<{pages}H", raw, 64):
        assert page == 0xffff or page < entry_pages
    for entry in struct.unpack_from(f"<{entry_pages * 256}I", raw, entries_offset):
        assert entry == 0xffffffff or (entry & 0xffffff) + (entry >> 24) <= values_count
    assert all(cp <= 0x10ffff for cp in struct.unpack_from(f"<{values_count}I", raw, values_offset))
    header = output / "fold_table.h"
    header.write_text(
        "/* Generated from the common frozen binary, not an independently generated table. */\n"
        + f'#define FOLD_TABLE_SHA256 "{sha(raw)}"\n'
        + f'#define FOLD_UCD_VERSION "{ucd_version}"\n'
        + f"#define FOLD_ENTRIES_OFFSET {entries_offset}u\n"
        + f"#define FOLD_VALUES_OFFSET {values_offset}u\n"
        + "static const unsigned char FOLD_TABLE[] = {\n"
        + "\n".join(",".join(str(value) for value in raw[i:i + 32]) + "," for i in range(0, len(raw), 32))
        + "\n};\n"
    )
    binary = output / ("_language_c_table" + sysconfig.get_config_var("EXT_SUFFIX"))
    common_flags = ["-shared", "-fPIC", "-O3", "-DNDEBUG", "-g", "-fwrapv", "-Wall"]
    command = [*shlex.split(args.cc), *common_flags,
               "-I" + sysconfig.get_path("include"), "-I" + str(source.parent),
               "-I" + str(output), str(HERE / "_language_c_table.c"), "-o", str(binary)]
    if args.rust_library:
        command += ["-DLANGUAGE_USE_RUST_TABLE", str(args.rust_library.resolve()),
                    "-Wl,--exclude-libs,ALL", "-ldl", "-lpthread", "-lm"]
    run = subprocess.run(command, capture_output=True, text=True)
    (output / "compile.log").write_text(run.stdout + run.stderr)
    manifest = {
        "candidate": "rust-table-fold" if args.rust_library else "c-table-fold",
        "status": "completed" if run.returncode == 0 else "failed",
        "command": command, "python": sys.version, "platform": platform.platform(),
        "table_path": str(table), "table_sha256": sha(raw), "table_metadata": metadata,
        "table_metadata_sha256": sha(meta_path.read_bytes()), "table_ucd_version": ucd_version,
        "control_source_sha256": sha((HERE / "_language_c_table.c").read_bytes()),
        "builder_sha256": sha(Path(__file__).read_bytes()),
        "native_reference_inputs": {str(p): sha(p.read_bytes()) for p in sorted(source.parent.glob("_native*")) if p.suffix in (".c", ".h")},
        "generated_header_sha256": sha(header.read_bytes()), "returncode": run.returncode,
        "binary_sha256": sha(binary.read_bytes()) if run.returncode == 0 else None,
        "binary_bytes": binary.stat().st_size if run.returncode == 0 else None,
        "boundary": "Only fold_excerpt_source changes. Same table and two-pass allocation as Rust. No production files are modified.",
        "compiler": subprocess.check_output([*shlex.split(args.cc), "--version"], text=True),
        "common_c_flags": common_flags,
        "rust_library": ({"path": str(args.rust_library.resolve()), "sha256": sha(args.rust_library.read_bytes())}
                         if args.rust_library else None),
    }
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if run.returncode:
        raise RuntimeError(f"C-table compilation failed; see {output / 'compile.log'}")
    print(json.dumps({"binary": str(binary), "sha256": manifest["binary_sha256"], "table_sha256": sha(raw)}))


if __name__ == "__main__":
    main()
