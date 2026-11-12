"""Build audited small packages, then publish one exact-commit experimental release.

Publication requires the dedicated push ref, the exact current main commit and
an already successful nine-job CI run. --prepare-only builds/checks local assets
without reading GitHub credentials or creating a tag, draft or release.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Afloat16/AI-Memory-Book"
BUILD_TOOLS = {"build": "1.3.0", "setuptools": "80.9.0", "wheel": "0.45.1"}
EXPECTED_JOBS = {"core (3.10)", "core (3.12)", "core (3.13)", "mcp", "reader-browser",
                 "installers (ubuntu-latest)", "installers (macos-latest)",
                 "installers (windows-latest)", "container"}
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
INSTALLERS = ("install.py", "install.sh", "install.ps1")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clean_environment():
    env = os.environ.copy()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def command(argv, *, cwd=ROOT, env=None, data=None, check=True):
    result = subprocess.run(argv, cwd=cwd, env=env, input=data, capture_output=True, timeout=300)
    if check and result.returncode:
        if env is not None and "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env:
            tail = result.stderr[-5000:].decode(errors="replace")
            tail = re.sub(r"https?://\S+", "[URL]", tail)
            for name in ("GH_TOKEN", "GITHUB_TOKEN"):
                if os.environ.get(name):
                    tail = tail.replace(os.environ[name], "[redacted]")
            print(tail, file=sys.stderr)
        # GitHub responses, credential URLs and headers are never echoed.
        raise RuntimeError("Command failed: " + Path(argv[0]).name + " " + str(argv[1]))
    return result


def git(root, *args):
    return command(["git", *args], cwd=root).stdout


def api(path, *, body=None, missing=False):
    argv = ["gh", "api", "repos/" + REPOSITORY + "/" + path]
    data = None
    if body is not None:
        argv += ["--method", "POST", "--input", "-"]
        data = json.dumps(body).encode()
    result = command(argv, data=data, check=False)
    if result.returncode and missing and b"HTTP 404" in result.stderr:
        return None
    require(result.returncode == 0, "GitHub API request failed: " + path.split("?")[0])
    return json.loads(result.stdout)


def find_release(tag):
    """Authenticated listing includes drafts; the tag endpoint is published-only."""
    matches, page = [], 1
    while True:
        batch = api(f"releases?per_page=100&page={page}")
        require(isinstance(batch, list), "Unexpected release-list response")
        matches.extend(item for item in batch if item["tag_name"] == tag)
        require(len(matches) <= 1, "Multiple releases use this tag; refuse an ambiguous draft")
        if len(batch) < 100:
            return matches[0] if matches else None
        page += 1


def release_by_id(release_id, tag, head, *, draft):
    require(type(release_id) is int and release_id > 0, "Expected a release ID")
    value = api(f"releases/{release_id}")
    require(value["id"] == release_id and value["tag_name"] == tag
            and value["target_commitish"] == head and value["draft"] is draft,
            "Release ID/tag/source/state differs")
    return value


def successful_ci(runs, head):
    completed = [r for r in runs if r.get("head_sha") == head and r.get("event") == "push"
                 and r.get("status") == "completed" and r.get("head_repository", {}).get("full_name") == REPOSITORY]
    require(completed, "No completed push CI exists for this exact commit; finish CI before publishing")
    run = max(completed, key=lambda r: r["id"])
    require(run["conclusion"] == "success", "The newest completed push CI for this commit did not succeed")
    return run


def verify_jobs(jobs, run_id, head):
    require(len(jobs) == 9 and {j["name"] for j in jobs} == EXPECTED_JOBS,
            "CI must contain exactly the nine expected jobs")
    require(all(j["status"] == "completed" and j["conclusion"] == "success"
                and j["run_id"] == run_id and j["head_sha"] == head for j in jobs),
            "Every expected job must succeed for this exact commit")


def ci_gate(head):
    runs = api("actions/workflows/ci.yml/runs?event=push&head_sha=" + head + "&per_page=100")["workflow_runs"]
    run = successful_ci(runs, head)
    jobs = api(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100")["jobs"]
    verify_jobs(jobs, run["id"], head)
    return run


def source_identity(root):
    import tomllib  # Release preparation uses Python 3.12; unit fixtures need no TOML dependency.
    head = git(root, "rev-parse", "HEAD").decode().strip()
    require(not git(root, "status", "--porcelain", "--untracked-files=no"), "Tracked source changes must be committed")
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = project["version"]
    require(project["name"] == "ai-memory-book" and re.fullmatch(r"\d+\.\d+\.\d+", version), "Unexpected project/version")
    names = git(root, "ls-tree", "-r", "--name-only", head, "src/memory_book").decode().splitlines()
    files = {}
    for name in names:
        path = root / name
        require(path.is_file() and not path.is_symlink(), "Unexpected runtime source entry")
        data = path.read_bytes()
        require(data == git(root, "show", head + ":" + name), "Source bytes differ from the release commit")
        files[name.removeprefix("src/")] = data
    require(files and "memory_book/static/index.html" in files, "Missing runtime or reader asset")
    hasher = hashlib.sha256()
    for name, data in sorted(files.items()):
        if name.endswith(".py"):
            hasher.update(name.removeprefix("memory_book/").encode() + b"\0" + data + b"\0")
    if version == "0.3.0":
        require(hasher.hexdigest() == "d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57",
                "v0.3.0 runtime differs from the approved source")
    require(f'__version__ = "{version}"' in files["memory_book/__init__.py"].decode(), "Package version differs")
    return {"version": version, "tag": "v" + version, "commit": head,
            "tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
            "epoch": int(git(root, "show", "-s", "--format=%ct", head)),
            "runtime_sha256": hasher.hexdigest()}, files


def safe_member(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in name, "Unsafe archive member")
    require(not ({"benchmarks", ".artifacts", ".git", ".memory-book", "models"} & set(path.parts)),
            "Research, private or model directory entered the package")
    require(not re.search(r"(?:\.db(?:-|$)|\.sqlite|\.onnx$|\.safetensors$|\.pth$|\.pyc$)", name, re.I),
            "Database, model or generated runtime file entered the package")


def canonicalize_and_check(path, identity, sources):
    """Inspect every member and normalize only archive metadata for repeatability."""
    require(path.stat().st_size <= MAX_ARCHIVE_BYTES, "Unexpectedly large package")
    epoch = identity["epoch"]
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            require(sum(info.file_size for info in archive.infolist()) <= MAX_ARCHIVE_BYTES, "Unexpected wheel expansion size")
            members = {info.filename: archive.read(info) for info in archive.infolist()}
            require(len(members) == len(archive.infolist()), "Duplicate wheel member")
        info_root = "ai_memory_book-" + identity["version"] + ".dist-info/"
        require(all(n.startswith("memory_book/") or n.startswith(info_root) for n in members), "Unexpected wheel package")
        actual = {n: data for n, data in members.items() if n.startswith("memory_book/")}
        buffer = io.BytesIO()
        timestamp = datetime.datetime.fromtimestamp(max(epoch, 315532800), datetime.timezone.utc).timetuple()[:6]
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(members.items()):
                info = zipfile.ZipInfo(name, timestamp)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
    else:
        prefix = "ai_memory_book-" + identity["version"] + "/"
        with tarfile.open(path, "r:gz") as archive:
            entries = archive.getmembers()
            require(sum(e.size for e in entries) <= MAX_ARCHIVE_BYTES, "Unexpected source archive expansion size")
            require(all(e.isfile() or e.isdir() for e in entries), "Source archive contains links or special files")
            members = {e.name: archive.extractfile(e).read() for e in entries if e.isfile()}
            require(len({e.name for e in entries}) == len(entries), "Duplicate source archive member")
        require(all(n.startswith(prefix) for n in members), "Unexpected source archive root")
        relative = {n.removeprefix(prefix): data for n, data in members.items()}
        require(all(n in {"README.md", "LICENSE", "PKG-INFO", "pyproject.toml", "setup.cfg"}
                    or n.startswith("src/memory_book/") or n.startswith("src/ai_memory_book.egg-info/")
                    for n in relative), "Unexpected source archive content")
        actual = {n.removeprefix("src/"): data for n, data in relative.items() if n.startswith("src/memory_book/")}
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(members.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), 0o644, epoch
                    archive.addfile(info, io.BytesIO(data))
    for name in members:
        safe_member(name)
    require(sum(map(len, members.values())) <= MAX_ARCHIVE_BYTES, "Unexpected package expansion size")
    require(actual == sources, "Package runtime/reader files differ from committed src bytes")
    path.write_bytes(buffer.getvalue())


def install_smoke(artifact, identity, workspace):
    env = clean_environment()
    with tempfile.TemporaryDirectory(prefix="install-", dir=workspace) as directory:
        install_dir = Path(directory)
        command([sys.executable, "-m", "venv", str(install_dir / "venv")], env=env)
        python = install_dir / "venv/bin/python"
        if artifact.name.endswith(".tar.gz"):
            command([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check",
                     "setuptools==" + BUILD_TOOLS["setuptools"], "wheel==" + BUILD_TOOLS["wheel"]], env=env)
        command([str(python), "-I", "-m", "pip", "install", "--no-deps", "--no-build-isolation", str(artifact)], env=env)
        code = '''import importlib.metadata, importlib.resources, memory_book
from memory_book import MemoryBook
assert memory_book.__version__ == importlib.metadata.version("ai-memory-book") == VERSION
assert importlib.resources.files("memory_book").joinpath("static/index.html").is_file()
with MemoryBook(":memory:") as book:
    book.ingest({"project":"release-check", "session_id":"one", "created_at":"2026-01-01T00:00:00Z",
                 "messages":[{"role":"user","content":"Release verification marker atlas-heron-791."}]})
    result=book.recall("atlas heron 791", project="release-check", use_cache=False)
    assert "atlas-heron-791" in result["context"] and result["results"][0]["source_refs"]
'''.replace("VERSION", repr(identity["version"]))
        command([str(python), "-I", "-c", code], cwd=install_dir, env=env)
        version = command([str(install_dir / "venv/bin/memory-book"), "--version"], cwd=install_dir, env=env).stdout.decode().strip()
        require(version == identity["version"], "Installed console command has another version")


def prepare(root, output):
    identity, sources = source_identity(root)
    require(not output.exists(), "Choose a fresh asset directory; never overwrite a previous local build")
    require({name: importlib.metadata.version(name) for name in BUILD_TOOLS} == BUILD_TOOLS, "Build tool versions differ")
    output.mkdir(parents=True)
    env = clean_environment()
    env["SOURCE_DATE_EPOCH"] = str(identity["epoch"])
    with tempfile.TemporaryDirectory(prefix="release-build-", dir=output.parent) as directory:
        stage = Path(directory)
        # Stage only the distribution inputs. Research records remain in Git,
        # and installer entry points are separate release assets.
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copyfile(root / name, stage / name)
        for name, data in sources.items():
            target = stage / "src" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        command([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output), str(stage)], cwd=stage, env=env)
        expected = {f"ai_memory_book-{identity['version']}-py3-none-any.whl", f"ai_memory_book-{identity['version']}.tar.gz"}
        require({p.name for p in output.iterdir()} == expected, "Expected one pure-Python wheel and one source distribution")
        for artifact in sorted(output.iterdir()):
            canonicalize_and_check(artifact, identity, sources)
            install_smoke(artifact, identity, stage)
    for name in INSTALLERS:
        data = (root / "scripts" / name).read_bytes()
        require(data == git(root, "show", identity["commit"] + ":scripts/" + name), "Installer is not committed")
        require(identity["tag"].encode() in data, "Installer does not refer to this release")
        (output / name).write_bytes(data)
    payloads = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in sorted(output.iterdir())}
    manifest = {"schema_version": 1, **identity, "build_tools": BUILD_TOOLS, "assets": payloads,
        "runtime_files_sha256": {n: sha(b) for n, b in sorted(sources.items())},
        "checks": {"wheel_and_sdist_installed_in_separate_clean_environments": True,
                   "runtime_and_reader_bytes_match_source": True, "large_research_data_excluded": True},
        "scope": "Experimental GitHub release; no PyPI publication, model download or benchmark execution."}
    (output / "release-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "SHA256SUMS").write_text("".join(sha(p.read_bytes()) + "  " + p.name + "\n" for p in sorted(output.iterdir())))
    return identity


def verify_remote_assets(release, output, *, complete):
    expected = {p.name: p for p in output.iterdir() if p.is_file()}
    assets = release["assets"]
    require(len({a["name"] for a in assets}) == len(assets), "Duplicate remote release asset")
    require({a["name"] for a in assets} <= expected.keys(), "Unexpected asset already exists; never overwrite")
    if complete:
        require({a["name"] for a in assets} == expected.keys() and len(assets) == 7, "Release asset set is incomplete")
    with tempfile.TemporaryDirectory(prefix="release-verify-", dir=output.parent) as directory:
        for asset in assets:
            target = expected[asset["name"]]
            require(asset["state"] == "uploaded" and asset["size"] == target.stat().st_size, "Remote asset size/state differs")
            command(["gh", "release", "download", release["tag_name"], "--repo", REPOSITORY,
                     "--pattern", asset["name"], "--dir", directory])
            require(sha((Path(directory) / asset["name"]).read_bytes()) == sha(target.read_bytes()), "Remote asset bytes differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/release-assets")
    args = parser.parse_args()
    root, output = args.source_root.resolve(), args.output.resolve()
    if args.prepare_only:
        identity = prepare(root, output)
        print(json.dumps({"prepared_only": True, "commit": identity["commit"], "assets": sorted(p.name for p in output.iterdir())}))
        return
    require(root == ROOT and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and os.environ.get("GITHUB_EVENT_NAME") == "push",
            "Publication is restricted to this repository's dedicated push workflow")
    identity, _ = source_identity(root)
    head, tag = identity["commit"], identity["tag"]
    require(os.environ.get("GITHUB_SHA") == head and os.environ.get("GITHUB_REF") == "refs/heads/release/" + tag,
            "Release ref/version/head mismatch")
    require(api("git/ref/heads/main")["object"]["sha"] == head, "main must point to the exact release commit")
    run = ci_gate(head)
    release = find_release(tag)
    require(release is None or (release["draft"] and release["target_commitish"] == head),
            "Refuse a public release or a draft belonging to another commit")
    ref = api("git/ref/tags/" + quote(tag), missing=True)
    require(ref is None or (ref["object"]["sha"] == head and ref["object"]["type"] == "commit"),
            "Existing tag must directly identify this exact commit; never move tags")
    notes = root / "docs/releases" / (tag + ".md")
    require(notes.is_file(), "Committed release notes are required")
    prepare(root, output)
    require(api("git/ref/heads/main")["object"]["sha"] == head, "main advanced during preparation; no publication")
    if release:
        verify_remote_assets(release, output, complete=False)
    if ref is None:
        api("git/refs", body={"ref": "refs/tags/" + tag, "sha": head})
    final_notes = output.parent / "release-notes.md"
    final_notes.write_text(notes.read_text() + f"\n\nSource commit: `{head}`.\n\nCI: {run['html_url']}\n\n"
                          + "Release workflow: https://github.com/" + REPOSITORY + "/actions/runs/" + os.environ["GITHUB_RUN_ID"] + "\n")
    if release is None:
        command(["gh", "release", "create", tag, "--repo", REPOSITORY, "--verify-tag", "--target", head,
                 "--title", tag, "--draft", "--prerelease", "--notes-file", str(final_notes)])
        release = find_release(tag)
        require(release is not None, "New draft was not found in the authenticated release list")
    release_id = release["id"]
    release = release_by_id(release_id, tag, head, draft=True)
    present = {a["name"] for a in release["assets"]}
    for artifact in sorted(output.iterdir()):
        if artifact.name not in present:
            command(["gh", "release", "upload", tag, str(artifact), "--repo", REPOSITORY])
    release = release_by_id(release_id, tag, head, draft=True)
    verify_remote_assets(release, output, complete=True)
    command(["gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--prerelease",
             "--notes-file", str(final_notes)])
    release = release_by_id(release_id, tag, head, draft=False)
    require(release["prerelease"], "Published release must remain experimental")
    require(api("git/ref/tags/" + quote(tag))["object"]["sha"] == head, "Published tag identity differs")
    verify_remote_assets(release, output, complete=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"tag={tag}\nversion={identity['version']}\ncommit={head}\n")
    print(json.dumps({"published": release["html_url"], "tag": tag, "commit": head, "assets": 7}))


if __name__ == "__main__":
    main()
