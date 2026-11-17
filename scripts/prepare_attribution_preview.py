#!/usr/bin/env python3
"""Prepare one offline, create-only author-attribution preview; never publish it.

This is a source-bound maintenance operation, not a general history-rewrite tool.
It writes new commit objects and one new local ref, leaving all existing refs,
trees, messages and dates intact. Publication requires a separate reviewed step.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess


SOURCE = "b6fa111a53e4395875febd2379aa719e96d1179f"
PREVIEW_REF = "refs/heads/maintenance/author-attribution-preview"
BOT = b"github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
OWNER = b"Afloat <ShuffleMonkey@163.com>"
CHANGED_SIGNATURE = "a0961f29dcdf3801d063e6d69bacaa1bde99e318"
EXPECTED_COUNTS = (972, 600, 922)
OID = re.compile(r"[0-9a-f]{40}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git(repository: Path, *args: str, data: bytes | None = None) -> bytes:
    environment = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *args],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, env=environment,
    ).stdout


def ref_snapshot(repository: Path) -> dict[str, str]:
    lines = git(repository, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in lines.decode("ascii").splitlines())


def read_commits(repository: Path, identifiers: list[str]) -> dict[str, bytes]:
    payload = git(repository, "cat-file", "--batch", data=("\n".join(identifiers) + "\n").encode())
    stream = io.BytesIO(payload)
    commits = {}
    for expected in identifiers:
        fields = stream.readline().split()
        require(len(fields) == 3 and fields[1] == b"commit", "Missing or non-commit object")
        identifier = fields[0].decode("ascii")
        raw = stream.read(int(fields[2]))
        require(identifier == expected and stream.read(1) == b"\n", "Invalid batch framing")
        digest = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(digest == expected, "Original bytes do not match the Git object identity")
        commits[identifier] = raw
    require(stream.read() == b"", "Unexpected extra batch output")
    return commits


def parse_commit(raw: bytes) -> tuple[list[tuple[bytes, bytes]], bytes]:
    header, separator, message = raw.partition(b"\n\n")
    require(separator == b"\n\n", "Commit has no message boundary")
    blocks: list[bytes] = []
    for line in header.split(b"\n"):
        if line.startswith(b" "):
            require(bool(blocks) and blocks[-1].startswith(b"gpgsig "), "Unexpected continuation")
            blocks[-1] += b"\n" + line
        else:
            blocks.append(line)
    fields = []
    for block in blocks:
        key, space, value = block.partition(b" ")
        require(space == b" " and key in {b"tree", b"parent", b"author", b"committer", b"gpgsig"},
                "Unexpected commit header; manual review required")
        fields.append((key, value))
    for key in (b"tree", b"author", b"committer"):
        require(sum(k == key for k, _ in fields) == 1, "Missing or duplicate required header")
    require(sum(k == b"gpgsig" for k, _ in fields) <= 1, "Multiple signatures are unsupported")
    for key, value in fields:
        if key in (b"tree", b"parent"):
            require(bool(OID.fullmatch(value.decode("ascii"))), "Invalid object identifier")
        elif key in (b"author", b"committer"):
            identity_parts(value)
    return fields, message


def identity_parts(value: bytes) -> tuple[bytes, bytes]:
    match = re.fullmatch(rb"(.+ <[^<>\n]+>)( -?\d+ [+-]\d{4})", value)
    require(match is not None, "Unexpected identity or timestamp encoding")
    return match.group(1), match.group(2)


def serialize(fields: list[tuple[bytes, bytes]], message: bytes) -> bytes:
    return b"\n".join(key + b" " + value for key, value in fields) + b"\n\n" + message


def values(fields: list[tuple[bytes, bytes]], key: bytes) -> list[bytes]:
    return [value for name, value in fields if name == key]


def verify_pair(old: bytes, new: bytes, mapping: dict[str, str], changed: bool) -> None:
    before, old_message = parse_commit(old)
    after, new_message = parse_commit(new)
    require(old_message == new_message, "Commit message changed")
    require(values(before, b"tree") == values(after, b"tree"), "A source tree changed")
    expected_parents = [mapping[p.decode()].encode() for p in values(before, b"parent")]
    require(values(after, b"parent") == expected_parents, "Parent ordering or topology changed")
    for key in (b"author", b"committer"):
        old_identity, old_date = identity_parts(values(before, key)[0])
        new_identity, new_date = identity_parts(values(after, key)[0])
        require(new_date == old_date, "A timestamp or timezone changed")
        require(new_identity == (OWNER if old_identity == BOT else old_identity),
                "An unrelated identity changed")
    expected_keys = [k for k, _ in before if not (changed and k == b"gpgsig")]
    require([k for k, _ in after] == expected_keys, "Header order changed")
    require(values(after, b"gpgsig") == ([] if changed else values(before, b"gpgsig")),
            "Invalid signature handling")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(args: argparse.Namespace) -> dict[str, object]:
    repository = args.repository.resolve()
    output = args.output.resolve()
    require(args.source == SOURCE, "This preview is bound to one reviewed source SHA")
    require(args.preview_ref == PREVIEW_REF, "Only the fixed, new preview ref is allowed")
    require(args.expected_preview_head is None or bool(OID.fullmatch(args.expected_preview_head)),
            "Expected preview head must be an exact lowercase SHA")
    require(not output.exists(), "Output directory already exists; preserve earlier evidence")
    require(git(repository, "rev-parse", "--is-shallow-repository").strip() == b"false",
            "Complete source ancestry is required")
    require(git(repository, "rev-parse", "--show-object-format").strip() == b"sha1",
            "Unexpected Git object format")
    before_refs = ref_snapshot(repository)
    require(PREVIEW_REF not in before_refs, "Preview ref already exists; no overwrite is allowed")
    identifiers = git(repository, "rev-list", "--reverse", "--topo-order", SOURCE).decode().splitlines()
    require(len(identifiers) == EXPECTED_COUNTS[0] and len(set(identifiers)) == len(identifiers),
            "Unexpected source graph size")
    originals = read_commits(repository, identifiers)
    mapping: dict[str, str] = {}
    records = []
    removed_signatures = []
    identity_count = 0
    author_count = 0
    committer_count = 0
    for identifier in identifiers:
        fields, message = parse_commit(originals[identifier])
        require(serialize(fields, message) == originals[identifier], "Header parsing was lossy")
        replacement = []
        bot_author = False
        bot_committer = False
        parent_changed = False
        for key, value in fields:
            if key == b"parent":
                parent = value.decode("ascii")
                require(parent in mapping, "A parent is missing or the graph is not topologically ordered")
                new_value = mapping[parent].encode("ascii")
                parent_changed |= new_value != value
                value = new_value
            elif key in (b"author", b"committer"):
                identity, date = identity_parts(value)
                if identity == BOT:
                    value = OWNER + date
                    bot_author |= key == b"author"
                    bot_committer |= key == b"committer"
            replacement.append((key, value))
        require(bot_author == bot_committer, "Unexpected author-only or committer-only bot record")
        changed = bot_author or parent_changed
        signature_removed = changed and bool(values(fields, b"gpgsig"))
        if signature_removed:
            require(identifier == CHANGED_SIGNATURE and not bot_author,
                    "Unexpected signed commit would be invalidated")
            replacement = [(k, v) for k, v in replacement if k != b"gpgsig"]
            removed_signatures.append(identifier)
        new_raw = serialize(replacement, message)
        if changed:
            new_identifier = git(repository, "hash-object", "-t", "commit", "-w", "--stdin",
                                 data=new_raw).decode().strip()
            require(new_identifier != identifier, "Expected a changed commit identity")
        else:
            require(new_raw == originals[identifier], "An unchanged commit was modified")
            new_identifier = identifier
        mapping[identifier] = new_identifier
        identity_count += bot_author
        author_count += bot_author
        committer_count += bot_committer
        records.append({"old": identifier, "new": new_identifier,
                        "identity_changed": bot_author, "parents_changed": parent_changed,
                        "signature_removed": signature_removed})
    changed_count = sum(old != new for old, new in mapping.items())
    require((len(mapping), identity_count, changed_count) == EXPECTED_COUNTS, "Unexpected rewrite counts")
    require(removed_signatures == [CHANGED_SIGNATURE], "Unexpected signature effect")
    preview = mapping[SOURCE]
    require(args.expected_preview_head is None or preview == args.expected_preview_head,
            "Candidate differs from the independently reviewed local preview")
    rewritten = read_commits(repository, list(mapping.values()))
    require(len(rewritten) == len(originals), "Commit graph collapsed or duplicated")
    for old, new in mapping.items():
        verify_pair(originals[old], rewritten[new], mapping, old != new)
    actual_graph = set(git(repository, "rev-list", preview).decode().splitlines())
    require(actual_graph == set(mapping.values()), "Rewritten ancestry differs from the complete mapping")
    require(ref_snapshot(repository) == before_refs, "Another writer changed an existing ref")
    tree = values(parse_commit(originals[SOURCE])[0], b"tree")[0].decode()
    new_tree = values(parse_commit(rewritten[preview])[0], b"tree")[0].decode()
    summary = {
        "schema_version": 1, "status": "verified_preview_not_applied_to_main",
        "repository": "Afloat16/AI-Memory-Book", "source_main_sha": SOURCE,
        "preview_sha": preview, "preview_ref": PREVIEW_REF,
        "source_tree": tree, "preview_tree": new_tree,
        "total_commits": len(mapping), "identity_changed_commits": identity_count,
        "author_changes": author_count, "committer_changes": committer_count,
        "rewritten_commits": changed_count, "unchanged_commits": len(mapping) - changed_count,
        "removed_signature_original_commits": removed_signatures,
        "preserved_signed_commits": sum(bool(values(parse_commit(raw)[0], b"gpgsig"))
                                        for raw in rewritten.values()),
        "validation": {"all_commit_objects_verified": True, "all_trees_identical": True,
                       "all_messages_byte_identical": True, "all_timestamps_and_timezones_identical": True,
                       "all_nonbot_identities_preserved": True, "ordered_merge_topology_preserved": True,
                       "existing_refs_unchanged": True},
        "scope": "Only the complete ancestry of the fixed source main. No release tags, existing branches, "
                 "published assets or frozen source references are moved. Off-main histories are not rewritten.",
        "identity": {"old": BOT.decode(), "new": OWNER.decode()},
    }
    output.mkdir(parents=True)
    write_json(output / "summary.json", summary)
    write_json(output / "commit-map.json", records)
    write_json(output / "original-refs.json", before_refs)
    (output / "README.md").write_text(
        "# Author-attribution preview\n\n"
        f"Source main: `{SOURCE}`. Reviewed candidate: `{preview}`.\n\n"
        "This candidate corrects 600 bot author/committer identities and changes 922 commit SHAs. "
        "All 972 source trees, messages, raw timestamps and ordered parent relationships were checked. "
        "No existing branch, release tag, asset or frozen evidence reference is replaced.\n\n"
        f"The old GitHub signature on `{CHANGED_SIGNATURE}` cannot authenticate its new parent chain; "
        "only that invalidated signature is removed. Two unaffected signed commits are retained exactly.\n\n"
        "`commit-map.json` records every old and new SHA; `summary.json` records validation; "
        "`original-refs.json` records the local ref snapshot before preparation. The fixed source SHA "
        "and the separate remote audit define the scope; a runner's local refs are not a complete "
        "remote-branch inventory. `sha256-manifest.json` checks the report bytes.\n\n"
        "Applying this candidate to main requires a separate explicit history-rewrite decision. "
        "The preparation script has no publication operation.\n", encoding="utf-8")
    write_json(output / "sha256-manifest.json", {
        path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(output.iterdir()) if path.is_file()
    })
    git(repository, "update-ref", "--stdin", data=f"create {PREVIEW_REF} {preview}\n".encode())
    after_refs = ref_snapshot(repository)
    require(after_refs.pop(PREVIEW_REF, None) == preview and after_refs == before_refs,
            "Unexpected ref change during create-only publication")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview-ref", required=True)
    parser.add_argument("--expected-preview-head")
    args = parser.parse_args()
    summary = prepare(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
