"""Reassemble the exact original run-2 ZIP; never overwrite an existing file."""
from pathlib import Path
import argparse
import hashlib
import json

root = Path(__file__).resolve().parents[3]
manifest = json.loads(Path(__file__).with_name("manifest.json").read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
whole = hashlib.sha256()
size = 0
with args.output.open("xb") as destination:
    for part in manifest["parts"]:
        data = (root / part["path"]).read_bytes()
        if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
            raise ValueError("Corrupt or missing original artifact part: " + part["path"])
        destination.write(data)
        whole.update(data)
        size += len(data)
if size != manifest["original_bytes"] or whole.hexdigest() != manifest["original_sha256"]:
    raise ValueError("Reconstructed ZIP identity differs from the original GitHub artifact")
print(json.dumps({"bytes": size, "sha256": whole.hexdigest(), "output": str(args.output)}))
