"""Download pinned external data and reproduce the HotpotQA JSON conversion.

Requires pyarrow only for the pinned Parquet conversion. Data remains under the
ignored .artifacts directory; public manifests contain hashes and selected IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def checked_download(url, destination, expected_hash, expected_bytes):
    if destination.exists():
        raw = destination.read_bytes()
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=60) as response:
            raw = response.read()
        if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("Downloaded data does not match the frozen input")
        destination.write_bytes(raw)
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("Existing data does not match the frozen input; preserve it and select a new path")
    return raw


def normalize_hotpot(rows):
    result = []
    for row in rows:
        context, facts = row["context"], row["supporting_facts"]
        result.append({"_id": row["id"], "question": row["question"], "answer": row["answer"],
            "type": row["type"], "level": row["level"],
            "context": list(map(list, zip(context["title"], context["sentences"], strict=True))),
            "supporting_facts": list(map(list, zip(facts["title"], facts["sent_id"], strict=True)))})
    return (json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path(".artifacts/data"))
    p.add_argument("--upstream-dir", type=Path, default=Path(".artifacts/upstream"))
    args = p.parse_args()
    root = Path(__file__).parent
    locomo = json.loads((root / "locomo_split.json").read_text())
    checked_download(locomo["url"], args.data_dir / "locomo10.json", locomo["sha256"], locomo["bytes"])
    hotpot = json.loads((root / "hotpot_manifest.json").read_text())
    parquet = args.upstream_dir / "hotpot_dev_distractor_v1.parquet"
    checked_download(hotpot["source_url"], parquet, hotpot["upstream_sha256"], hotpot["upstream_bytes"])
    import pyarrow.parquet as pq
    raw = normalize_hotpot(pq.read_table(parquet).to_pylist())
    if len(raw) != hotpot["canonical_bytes"] or hashlib.sha256(raw).hexdigest() != hotpot["canonical_sha256"]:
        raise ValueError("HotpotQA conversion does not match frozen canonical bytes")
    destination = args.data_dir / "hotpotqa-dev-distractor.json"
    if destination.exists() and destination.read_bytes() != raw:
        raise ValueError("Preserve the existing different HotpotQA file before conversion")
    destination.write_bytes(raw)
    print(json.dumps({"locomo": str(args.data_dir / "locomo10.json"), "hotpotqa": str(destination),
                      "hashes_verified": True}))


if __name__ == "__main__":
    main()
