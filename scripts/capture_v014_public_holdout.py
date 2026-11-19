"""Capture pinned, licensed upstream source files for a retrieval-only holdout.

No query is executed here. Never overwrite a frozen capture with live sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

REVISIONS = (
    ("httpx", "encode/httpx", "old", "0.13.3", "56d880030e37d64c273ea23b92e24dc00b586c3b", ("httpx/_config.py", "httpx/_client.py"), "LICENSE.md"),
    ("httpx", "encode/httpx", "current", "0.28.1", "26d48e0634e6ee9cdc0533996db289ce4b430177", ("httpx/_config.py", "httpx/_client.py"), "LICENSE.md"),
    ("httpcore", "encode/httpcore", "old", "0.9.1", "888c163bb385dc89fc802a7a01aa8420ded55774", ("httpcore/_sync/connection_pool.py", "httpcore/_sync/http11.py"), "LICENSE.md"),
    ("httpcore", "encode/httpcore", "current", "1.0.9", "98209758cc14e1a5f966fe1dfdc1064b94055d8c", ("httpcore/_sync/connection_pool.py", "httpcore/_sync/http11.py"), "LICENSE.md"),
    ("requests", "psf/requests", "old", "v2.22.0", "aeda65bbe57ac5edbcc2d80db85d010befb7d419", ("requests/adapters.py", "requests/sessions.py"), "LICENSE"),
    ("requests", "psf/requests", "current", "v2.32.3", "0e322af87745eff34caffe4df68456ebc20d9068", ("src/requests/adapters.py", "src/requests/sessions.py"), "LICENSE"),
    ("urllib3", "urllib3/urllib3", "old", "1.25.11", "9b95f29c575d73260ec4f5a8c0ea368cf242019e", ("src/urllib3/util/retry.py", "src/urllib3/connectionpool.py"), "LICENSE.txt"),
    ("urllib3", "urllib3/urllib3", "current", "2.2.3", "2458bfcd3dacdf6c196e98d077fc6bb02a5fc1df", ("src/urllib3/util/retry.py", "src/urllib3/connectionpool.py"), "LICENSE.txt"),
)


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "AI-Memory-Book-source-holdout"}), timeout=45) as response:
        return response.read()


def capture(destination):
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for project, repo, phase, tag, commit, paths, license_path in REVISIONS:
        metadata = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{commit}"))
        if metadata["sha"] != commit:
            raise ValueError("Upstream resolved a different commit")
        for path in (*paths, license_path):
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
            raw = fetch(url)
            raw.decode("utf-8")
            filename = f"{project}-{phase}-{path.replace('/', '__')}.txt"
            (destination / filename).write_bytes(raw)
            rows.append({"project": "public-" + project, "repo": repo, "phase": phase,
                         "tag": tag, "commit": commit, "upstream_path": path,
                         "created_at": metadata["commit"]["committer"]["date"],
                         "url": url, "source_url": f"https://github.com/{repo}/blob/{commit}/{path}",
                         "file": filename, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                         "kind": "license" if path == license_path else "source"})
            print(filename, len(raw), flush=True)
    manifest = {"schema_version": 1, "protocol": "v014-public-source-holdout-v2",
                "scope": "Pinned public source-code snapshots; independently authored retrieval questions, not real user transcripts or end-to-end coding success.",
                "sources": rows}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    capture(parser.parse_args().destination)
