"""Verify and preserve the existing first-attempt native experiment; never time it again."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".artifacts/native-language-evidence"
DESTINATION = WORK / "evidence"
REPOSITORY = "Afloat16/AI-Memory-Book"
TRIGGER_BRANCH = "validation/native-language-evidence-1"
EVIDENCE_BRANCH = "evidence/native-language-formal-43822446202"
RUN_ID = 43822446202
ARTIFACT_ID = 14205446971
ARTIFACT_NAME = "native-language-formal-43822446202-1"
ARTIFACT_BYTES = 38192300
ARTIFACT_SHA256 = "9c8a2b32458d08d2009011d915e4b6f8c21c49a27d0ddf684bbb8334b54ef0a3"
EXTRACTED_BYTES = 39858305
EVALUATOR_COMMIT = "b0d3e6157394bda44d5abb468d75dff6472a1692"
EVALUATOR_SHA256 = "d5006aa33565f752a80122e128cef310750edbda1bec513bc3bb6e1e6788f023"
BASELINE_COMMIT = "b1434ca8b218d096d5506aaea02631ca31306d21"
CANDIDATE_COMMIT = "22a29df0a920e526d3af594db92728d9b9c16d57"
REPORT_PATH = "benchmarks/reports/native-language/formal-run-1"
BUILD_PATH = ".artifacts/native-language-formal"
BINARY_PATH = "candidate/src/memory_book/_native.cpython-312-x86_64-linux-gnu.so"
EVALUATOR_PATHS = {
    ".github/workflows/native-language-performance.yml", "benchmarks/__init__.py",
    "benchmarks/data.py", "benchmarks/public_data.py", "benchmarks/run.py",
    "benchmarks/locomo_split.json", "benchmarks/experiments/native_language_formal_plan.json",
    "scripts/native_language_performance.py", "scripts/native_language_host.py",
    "tests/test_native_language_performance.py",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def checkpoint(stage, **details):
    WORK.mkdir(parents=True, exist_ok=True)
    value = {"stage": stage, "source_run_id": RUN_ID, "artifact_id": ARTIFACT_ID,
             "preservation_run_id": os.environ.get("GITHUB_RUN_ID"),
             "preservation_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), **details}
    (WORK / "checkpoint.json").write_bytes(json_bytes(value))
    print(json.dumps(value, sort_keys=True), flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def api_response(endpoint, token):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/{endpoint}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "AI-Memory-Book-evidence"})
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=60)


def api_json(endpoint, token):
    with api_response(endpoint, token) as response:
        return json.load(response)


def download_archive(token, target):
    # The authenticated API request cannot follow redirects. The signed storage
    # request is a new request with no Authorization header or token parameter.
    try:
        response = api_response(f"actions/artifacts/{ARTIFACT_ID}/zip", token)
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise RuntimeError(f"Artifact API returned HTTP {error.code}") from None
        location = error.headers.get("Location", "")
        error.close()
        require(urllib.parse.urlsplit(location).scheme == "https", "Artifact redirect is not HTTPS")
        try:
            # GitHub's signed storage URL is consumed once and is never logged.
            response = urllib.request.build_opener(NoRedirect()).open(
                urllib.request.Request(location, headers={"User-Agent": "AI-Memory-Book-evidence"}), timeout=60)
        except (OSError, urllib.error.URLError):
            raise RuntimeError("Signed artifact download failed") from None
    total, digest = 0, hashlib.sha256()
    with response, target.open("xb") as output:
        while block := response.read(1024 * 1024):
            total += len(block)
            require(total <= ARTIFACT_BYTES, "Artifact exceeds its frozen byte count")
            digest.update(block)
            output.write(block)
    require(total == ARTIFACT_BYTES and digest.hexdigest() == ARTIFACT_SHA256,
            "Artifact size or SHA-256 differs from the frozen first attempt")


def verify_provenance(artifact, run):
    require(artifact.get("id") == ARTIFACT_ID and artifact.get("name") == ARTIFACT_NAME
            and artifact.get("size_in_bytes") == ARTIFACT_BYTES and not artifact.get("expired"),
            "Artifact metadata differs or has expired")
    require(artifact.get("digest") == "sha256:" + ARTIFACT_SHA256, "Artifact metadata digest differs")
    require(artifact.get("workflow_run", {}).get("id") == RUN_ID
            and artifact["workflow_run"].get("head_sha") == EVALUATOR_COMMIT,
            "Artifact belongs to a different workflow run or commit")
    require(run.get("id") == RUN_ID and run.get("run_attempt") == 1
            and run.get("head_sha") == EVALUATOR_COMMIT and run.get("event") == "push"
            and run.get("head_branch") == "validation/native-language-formal-1"
            and run.get("conclusion") == "success" and run.get("status") == "completed"
            and run.get("path") == ".github/workflows/native-language-performance.yml"
            and run.get("repository", {}).get("full_name") == REPOSITORY,
            "Original workflow provenance differs from the frozen successful first attempt")


def expected_members():
    files = {f"{REPORT_PATH}/run.json", f"{REPORT_PATH}/summary.json",
             f"{BUILD_PATH}/build.log", f"{BUILD_PATH}/build-manifest.json", f"{BUILD_PATH}/{BINARY_PATH}"}
    for round_ in range(4):
        for cohort in ("synthetic61", "public1015"):
            for label in ("baseline", "candidate"):
                stem = f"{REPORT_PATH}/r{round_}-{cohort}-{label}"
                files.update(stem + suffix for suffix in (".json.gz", ".attempts.jsonl.gz", ".started.json", ".log"))
    return files


def validate_members(infos):
    names = [item.filename for item in infos]
    require(len(infos) == 69 and len(set(names)) == 69 and set(names) == expected_members(),
            "ZIP does not contain exactly the 69 frozen evidence members")
    require(sum(item.file_size for item in infos) == EXTRACTED_BYTES, "Uncompressed evidence byte count differs")
    for item in infos:
        path = PurePosixPath(item.filename)
        mode = item.external_attr >> 16
        require(not path.is_absolute() and path.as_posix() == item.filename
                and ".." not in path.parts and "\\" not in item.filename
                and not item.is_dir() and not stat.S_ISLNK(mode)
                and stat.S_IFMT(mode) in (0, stat.S_IFREG) and not item.flag_bits & 1,
                "ZIP contains an unsafe path or unsupported member type")


def extract_archive(archive_path):
    inventory = {}
    DESTINATION.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        validate_members(infos)
        for item in infos:
            raw = archive.read(item)  # ZipFile verifies each member's original CRC.
            require(len(raw) == item.file_size, "ZIP member byte count differs")
            target = DESTINATION / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            inventory[item.filename] = {"bytes": len(raw), "sha256": sha(raw)}
    return inventory


def git(*args, input=None, env=None, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT, input=input, env=env,
                            capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Git {args[0]} failed with exit {result.returncode}")
    return result


def preserve_evaluator(run):
    require(run.get("evaluator_commit") == EVALUATOR_COMMIT
            and set(run.get("evaluator", {})) == EVALUATOR_PATHS
            and run["evaluator"]["scripts/native_language_performance.py"] == EVALUATOR_SHA256,
            "Frozen evaluator identity differs")
    git("fetch", "--filter=blob:none", "--depth=1", "origin", EVALUATOR_COMMIT)
    inventory = {}
    for path, expected in sorted(run["evaluator"].items()):
        raw = git("show", EVALUATOR_COMMIT + ":" + path).stdout
        require(sha(raw) == expected, "Frozen evaluator source hash differs: " + path)
        name = "frozen-evaluator/" + path
        target = DESTINATION / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        inventory[name] = {"bytes": len(raw), "sha256": sha(raw)}
    plan = DESTINATION / "frozen-evaluator/benchmarks/experiments/native_language_formal_plan.json"
    require(sha(plan.read_bytes()) == run["plan_sha256"] and json.loads(plan.read_bytes()) == run["plan"],
            "Frozen plan bytes or contents differ")
    return inventory


def audit_evidence():
    report_dir = DESTINATION / REPORT_PATH
    run = json.loads((report_dir / "run.json").read_bytes())
    original_summary = json.loads((report_dir / "summary.json").read_bytes())
    require(run["plan"]["sources"] == {
        "baseline": {"commit": BASELINE_COMMIT, "backend": "python"},
        "candidate": {"commit": CANDIDATE_COMMIT, "backend": "native"}}, "Frozen runtime identities differ")
    build_bytes = (DESTINATION / BUILD_PATH / "build-manifest.json").read_bytes()
    build = json.loads(build_bytes)
    require(sha(build_bytes) == run["build_manifest_sha256"] and build == run["build_manifest"],
            "Build manifest differs from the measured run")
    require(build["workflow_commit"] == EVALUATOR_COMMIT and build["workflow_run_id"] == str(RUN_ID)
            and build["workflow_run_attempt"] == 1
            and sha((DESTINATION / BUILD_PATH / "build.log").read_bytes()) == build["build_log_sha256"],
            "Build log or workflow provenance differs")
    binary = (DESTINATION / BUILD_PATH / BINARY_PATH).read_bytes()
    require(run["sources"]["candidate"]["native_binaries"] == {
        BINARY_PATH.removeprefix("candidate/"): sha(binary)}, "Measured extension SHA-256 differs")
    evaluator_inventory = preserve_evaluator(run)
    environment = {key: value for key, value in os.environ.items() if key not in {"GITHUB_TOKEN", "GH_TOKEN", "PYTHONPATH"}}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([sys.executable,
        str(DESTINATION / "frozen-evaluator/scripts/native_language_performance.py"),
        "--audit", str(report_dir)], cwd=DESTINATION, env=environment, capture_output=True, check=False)
    require(completed.returncode == 0, "Original frozen evaluator rejected the preserved evidence")
    audited = json.loads(completed.stdout)
    require(audited == original_summary, "Audit does not exactly reproduce the original summary")
    require(audited["status"] == "completed" and audited["attempted_calls"] == 113568
            and audited["paired_calls"] == 56784
            and audited["comparison"]["complete_output_and_archive_equivalence"]
            and not audited["comparison"]["differences"], "Frozen call counts or equivalence differ")
    for item in run["schedule"]:
        intent = json.loads((report_dir / (item["key"] + ".started.json")).read_bytes())
        require(intent["worker"] == item and intent["run_sha256"] == audited["run_sha256"],
                "Original worker-start intent differs")
    return evaluator_inventory, {
        "original_summary_exactly_reproduced": True, "attempted_calls": audited["attempted_calls"],
        "paired_calls": audited["paired_calls"], "complete_output_and_archive_equivalence": True,
        "run_sha256": audited["run_sha256"], "evaluator_sha256": EVALUATOR_SHA256,
        "original_summary_sha256": sha((report_dir / "summary.json").read_bytes()),
        "measured_binary_sha256": sha(binary), "remeasured_calls": 0,
    }


def readme():
    return f"""# Frozen native-language experiment evidence

This branch preserves all 69 files, byte for byte, from the successful first
attempt of [run {RUN_ID}](https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}).
No performance call was repeated and no timing sample or original summary was replaced.
The ZIP container itself is not duplicated in Git; its identity and every extracted
member's SHA-256 are recorded in `evidence-manifest.json`.

- Artifact: `{ARTIFACT_NAME}` (ID `{ARTIFACT_ID}`; {ARTIFACT_BYTES:,} bytes).
- Artifact SHA-256: `{ARTIFACT_SHA256}`.
- Python baseline: `{BASELINE_COMMIT}`.
- Native runtime: `{CANDIDATE_COMMIT}`.
- Frozen evaluator: `{EVALUATOR_COMMIT}`.
- Verified: 113,568 timed calls, 56,784 paired calls, complete output/archive equivalence.

`{REPORT_PATH}/` contains the original run, summary, workers, attempt ledgers,
start intents and logs. `{BUILD_PATH}/` contains the original build log,
build manifest and measured extension. The extension is retained as evidence;
it is not a supported distributable wheel and does not need to execute to audit results.

## Offline audit

With Python 3.12, from this branch's root, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python frozen-evaluator/scripts/native_language_performance.py --audit {REPORT_PATH}
```

The audit uses only the standard library and retained report bytes. It does not
download the dataset, load the measured extension, invoke MCP, or remeasure queries.
Compare its JSON result with the original `{REPORT_PATH}/summary.json`.
`frozen-evaluator/` retains every evaluator-manifest file at its measured SHA-256.
`audit.json` records the successful exact-summary check performed before this branch
was created. Keep native and MCP timing boundaries distinct and retain negative
secondary results when interpreting the original summary.
"""


def publish():
    index = WORK / "evidence.index"
    environment = {**os.environ, "GIT_INDEX_FILE": str(index),
                   "GIT_AUTHOR_NAME": "Afloat", "GIT_AUTHOR_EMAIL": "ShuffleMonkey@163.com",
                   "GIT_COMMITTER_NAME": "Afloat", "GIT_COMMITTER_EMAIL": "ShuffleMonkey@163.com"}
    git("read-tree", "--empty", env=environment)
    entries = []
    for path in sorted(DESTINATION.rglob("*")):
        if path.is_file():
            name = path.relative_to(DESTINATION).as_posix()
            blob = git("hash-object", "-w", "--stdin", input=path.read_bytes(), env=environment).stdout.decode().strip()
            entries.append(f"100644 {blob}\t{name}\0".encode())
    git("update-index", "-z", "--index-info", input=b"".join(entries), env=environment)
    tree = git("write-tree", env=environment).stdout.decode().strip()
    ref = "refs/heads/" + EVIDENCE_BRANCH
    existing = git("ls-remote", "--exit-code", "origin", ref, check=False)
    require(existing.returncode in (0, 2), "Could not determine whether the evidence branch already exists")
    if existing.returncode == 0:
        commit = existing.stdout.decode().split()[0]
        git("fetch", "--filter=blob:none", "--depth=1", "origin", commit)
        require(git("rev-parse", commit + "^{tree}").stdout.decode().strip() == tree,
                "Existing evidence branch differs; it will not be overwritten")
        return {"commit": commit, "tree": tree, "already_preserved": True}
    commit = git("commit-tree", tree, "-m", f"evidence: preserve verified native language run {RUN_ID}",
                 env=environment).stdout.decode().strip()
    # No force or parent replacement: a concurrent different branch creation fails.
    git("push", "origin", commit + ":" + ref)
    observed = git("ls-remote", "--exit-code", "origin", ref).stdout.decode().split()[0]
    require(observed == commit, "Published evidence ref does not match the verified commit")
    return {"commit": commit, "tree": tree, "already_preserved": False}


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/" + TRIGGER_BRANCH,
            "Use only the dedicated evidence-preservation workflow")
    require(not WORK.exists(), "Preserve the previous work directory; do not replace it")
    checkpoint("checking_original_provenance")
    try:
        token = os.environ["GITHUB_TOKEN"]
        artifact = api_json(f"actions/artifacts/{ARTIFACT_ID}", token)
        run = api_json(f"actions/runs/{RUN_ID}/attempts/1", token)
        verify_provenance(artifact, run)
        checkpoint("downloading_original_artifact")
        archive = WORK / "original-artifact.zip"
        download_archive(token, archive)
        checkpoint("extracting_verified_artifact", artifact_sha256=ARTIFACT_SHA256)
        original_files = extract_archive(archive)
        checkpoint("auditing_frozen_evidence", original_members=len(original_files))
        evaluator_files, audit = audit_evidence()
        (DESTINATION / "audit.json").write_bytes(json_bytes(audit))
        (DESTINATION / "README.md").write_text(readme(), encoding="utf-8")
        manifest = {"schema_version": 1, "purpose": "Exact preservation of the original first attempt; no remeasurement",
                    "repository": REPOSITORY, "evidence_branch": EVIDENCE_BRANCH,
                    "artifact": {"id": ARTIFACT_ID, "name": ARTIFACT_NAME, "bytes": ARTIFACT_BYTES,
                                 "sha256": ARTIFACT_SHA256, "members": 69, "extracted_bytes": EXTRACTED_BYTES},
                    "original_run": {"id": RUN_ID, "attempt": 1, "commit": EVALUATOR_COMMIT,
                                     "branch": "validation/native-language-formal-1", "conclusion": "success",
                                     "url": f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}"},
                    "original_files": original_files, "frozen_evaluator_files": evaluator_files, "audit": audit}
        (DESTINATION / "evidence-manifest.json").write_bytes(json_bytes(manifest))
        checkpoint("publishing_verified_evidence", audit=audit)
        result = publish()
        checkpoint("completed", branch=EVIDENCE_BRANCH, audit=audit, **result)
    except Exception as error:
        # Never serialize request URLs, headers or signed-URL exceptions.
        checkpoint("failed", error_type=type(error).__name__)
        raise


if __name__ == "__main__":
    main()
