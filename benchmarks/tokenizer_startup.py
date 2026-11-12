"""Measure reference tokenizer setup in fresh processes with populated caches."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from benchmarks.token_compare import ENCODINGS, latency_summary


WORKER = r'''
import json, sys, time
before = time.perf_counter_ns()
import tiktoken
import_ms = (time.perf_counter_ns() - before) / 1e6
before = time.perf_counter_ns()
encoding = tiktoken.get_encoding(sys.argv[1])
initialize_ms = (time.perf_counter_ns() - before) / 1e6
before = time.perf_counter_ns()
count = len(encoding.encode("A short cited memory, including literal <|endoftext|> text.", disallowed_special=()))
count_ms = (time.perf_counter_ns() - before) / 1e6
print(json.dumps({"tokenizer":sys.argv[1],"version":tiktoken.__version__,
                 "import_ms":import_ms,"encoding_initialization_ms":initialize_ms,
                 "first_count_ms":count_ms,"count":count}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or args.output.exists():
        parser.error("Positive repeats and a new output path are required")
    # Explicitly populate the library vocabulary cache before timing workers.
    # Any download here is preparation and must not be claimed as measured.
    import tiktoken
    for name in ENCODINGS:
        tiktoken.get_encoding(name)
    rows = []
    for name in ENCODINGS:
        for repeat in range(args.repeats):
            before = time.perf_counter_ns()
            result = subprocess.run([sys.executable, "-c", WORKER, name], check=True,
                                    capture_output=True, text=True, timeout=60)
            wall_ms = (time.perf_counter_ns() - before) / 1e6
            rows.append({**json.loads(result.stdout), "repeat": repeat, "subprocess_wall_ms": wall_ms})
    report = {"schema_version":1,"python":platform.python_version(),"platform":platform.platform(),
        "scope":"Fresh interpreter, previously populated vocabulary cache and warm OS/filesystem. Initial network download is not measured. Core comparison workers pre-initialize reference encodings before recall timing; MCP server processes may initialize their tokenizer on the first budgeted call.",
        "cache_configuration":"TIKTOKEN_CACHE_DIR set" if os.environ.get("TIKTOKEN_CACHE_DIR") else "library default populated cache",
        "rows":rows,"summary":{name:{key:latency_summary([row[key] for row in rows if row['tokenizer']==name])
                 for key in ('import_ms','encoding_initialization_ms','first_count_ms','subprocess_wall_ms')} for name in ENCODINGS}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summary'],indent=2))


if __name__ == '__main__':
    main()
