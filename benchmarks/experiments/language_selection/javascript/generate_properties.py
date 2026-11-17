"""Reproduce or verify the frozen Python Unicode-property ranges for Node."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unicodedata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("unicode-properties.json"))
    args = parser.parse_args()
    ranges, start = [], None
    for cp in range(0x110001):
        matched = cp < 0x110000 and chr(cp).isalnum()
        if matched and start is None:
            start = cp
        if not matched and start is not None:
            ranges.append([start, cp])
            start = None
    record = {"unicode_version": unicodedata.unidata_version,
              "property": "Python str.isalnum, excluding no additional codepoints",
              "range_format": "half-open", "ranges": ranges}
    raw = (json.dumps(record, separators=(",", ":")) + "\n").encode()
    if args.output.exists():
        if args.output.read_bytes() != raw:
            raise SystemExit("Existing Unicode property table differs; choose a separate output path")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print(json.dumps({"output": str(args.output), "bytes": len(raw), "ranges": len(ranges),
                      "unicode": unicodedata.unidata_version, "sha256": hashlib.sha256(raw).hexdigest()}))


if __name__ == "__main__":
    main()
