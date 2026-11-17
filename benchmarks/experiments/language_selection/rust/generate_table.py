"""Freeze exact interpreter per-codepoint NFKD/casefold/Mn behavior.

The binary is shared by C and Rust larger-boundary candidates, so a table-driven
win cannot be attributed to Rust alone. No production file is read or modified.
All Unicode code points, including lone surrogates, are included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import unicodedata as ucd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("Refuse to replace a frozen table directory")
    args.output_dir.mkdir(parents=True)
    indices, pages, values = [], [], []
    changed, empty, maximum = 0, 0, 0
    for page in range(0x1100):
        entries = [0xffffffff] * 256
        touched = False
        for low in range(256):
            cp = page * 256 + low
            original = chr(cp)
            folded = "".join(ch for ch in ucd.normalize("NFKD", original).casefold() if ucd.category(ch) != "Mn")
            if folded == original:
                continue
            mapped = list(map(ord, folded))
            assert len(mapped) < 256 and len(values) < (1 << 24)
            entries[low] = (len(mapped) << 24) | len(values)
            values.extend(mapped)
            touched = True
            changed += 1
            empty += not mapped
            maximum = max(maximum, len(mapped))
        if touched:
            indices.append(len(pages) // 256)
            pages.extend(entries)
        else:
            indices.append(0xffff)
    header = bytearray(64)
    header[:8] = b"MBFOLD01"
    struct.pack_into("<III", header, 8, len(indices), len(pages) // 256, len(values))
    version = ucd.unidata_version.encode("ascii")
    assert len(version) < 16
    header[20:20+len(version)] = version
    index_offset = 64
    entries_offset = index_offset + len(indices)*2
    values_offset = entries_offset + len(pages)*4
    raw = bytes(header) + struct.pack(f"<{len(indices)}H", *indices) + struct.pack(f"<{len(pages)}I", *pages) + struct.pack(f"<{len(values)}I", *values)
    path = args.output_dir / "unicode_fold.bin"
    path.write_bytes(raw)
    metadata = {
        "schema_version": 1, "magic": "MBFOLD01", "unicode_version": ucd.unidata_version,
        "python": sys.version, "python_executable": sys.executable,
        "codepoints": 0x110000, "changed": changed, "empty": empty, "max_expansion": maximum,
        "index_offset": index_offset, "index_count": len(indices),
        "entries_offset": entries_offset, "entry_page_count": len(pages)//256,
        "values_offset": values_offset, "values_count": len(values),
        "identity_page": 65535, "identity_entry": 4294967295,
        "entry_encoding": "(length << 24) | values_index; all unsigned little endian",
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "semantics": "For each Python Unicode code point: normalize('NFKD', character).casefold(), then remove category exactly Mn; code-point source offsets; no cross-character normalization.",
    }
    (args.output_dir / "unicode_fold.meta.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
