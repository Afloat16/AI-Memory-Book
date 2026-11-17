"""Audit one published native release using staged evidence; never build or fetch.

See docs/comprehensive-release-audit.md for the acquisition layout and proof
schema. The caller supplies the expected version, source, runtime digest and
workflow attempt independently of the downloaded artifacts. Git object reads
and archive inspection do not execute package code or native binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_native_release_cell as cell
from scripts import native_release as native

release = native.legacy
require, sha, unique_json = native.require, native.sha, native._unique_json
VALIDATORS = ("scripts/release.py", "scripts/native_release.py",
              "scripts/build_native_release_cell.py", "scripts/audit_comprehensive_release.py")
WORKFLOW = ".github/workflows/release.yml"
FROZEN_AUDITOR = "scripts/audit_native_core_grouped_packaging.py"
PUBLISHED_STEP = "Install through the real public URL and default release-wheel path"
PUBLISHED_MARKER = "Verified public installer URL, release wheel, version and default MCP/client extras."
MAX_EVIDENCE_BYTES = 128 * 1024 * 1024


def safe_relative(name):
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and ".." not in path.parts
            and "\\" not in name and str(path) == name.rstrip("/"),
            "Unsafe evidence path: " + name)
    return path


def zip_members(raw):
    require(len(raw) <= MAX_EVIDENCE_BYTES, "Oversized artifact ZIP")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len({info.filename for info in infos}) == len(infos), "Duplicate artifact member")
        require(sum(info.file_size for info in infos) <= MAX_EVIDENCE_BYTES,
                "Oversized artifact ZIP expansion")
        result = {}
        for info in infos:
            safe_relative(info.filename)
            kind = stat.S_IFMT(info.external_attr >> 16)
            require(kind in (0, stat.S_IFREG, stat.S_IFDIR), "Linked or special artifact member")
            if info.is_dir():
                require(info.file_size == 0 and kind in (0, stat.S_IFDIR), "Invalid ZIP directory")
            else:
                require(kind != stat.S_IFDIR, "Invalid ZIP file metadata")
                result[info.filename] = archive.read(info)
        return result


class Evidence:
    """Read ordinary staged files and retain their exact byte hashes in proof."""

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.inventory = {}

    def path(self, name):
        path = self.root
        for part in safe_relative(name).parts:
            path = path / part
            require(not path.is_symlink(), "Linked evidence path: " + name)
        require(path.is_file(), "Missing ordinary evidence file: " + name)
        return path

    def read(self, name, limit=MAX_EVIDENCE_BYTES):
        path = self.path(name)
        require(path.stat().st_size <= limit, "Oversized evidence file: " + name)
        raw = path.read_bytes()
        record = {"bytes": len(raw), "sha256": sha(raw)}
        require(name not in self.inventory or self.inventory[name] == record,
                "Evidence changed during audit: " + name)
        self.inventory[name] = record
        return raw

    def json(self, name):
        return unique_json(self.read("metadata/" + name + ".json"))


def source_snapshot(root, commit, version, runtime_sha256, native_baseline):
    """Read exact Git objects without changing HEAD, index or working files."""
    root = Path(root)
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected full source commit SHA")
    require(re.fullmatch(r"[0-9a-f]{40}", native_baseline), "Expected full native baseline SHA")
    require(re.fullmatch(r"\d+\.\d+\.\d+", version), "Unexpected version")
    require(re.fullmatch(r"[0-9a-f]{64}", runtime_sha256), "Expected runtime SHA-256")
    require(release.git(root, "rev-parse", commit + "^{commit}").decode().strip() == commit,
            "Source is not the expected commit object")
    tree = release.git(root, "rev-parse", commit + "^{tree}").decode().strip()
    entries = {}
    for entry in release.git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            entries[name.decode("utf-8")] = (mode, kind, blob)
    names = {name for name in entries if name.startswith("src/memory_book/")}
    names.update(native.BUILD_INPUTS)
    names.update("scripts/" + name for name in release.INSTALLERS)
    names.update(VALIDATORS)
    names.update((WORKFLOW, FROZEN_AUDITOR))
    names.update(suite.replace(".", "/") + ".py" for suite in cell.SUITES)
    files, blobs = {}, {}
    for name in sorted(names):
        require(name in entries and entries[name][0] in ("100644", "100755")
                and entries[name][1] == "blob", "Missing or linked committed source: " + name)
        raw = release.git(root, "show", commit + ":" + name)
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == entries[name][2], "Git source blob differs: " + name)
        files[name], blobs[name] = raw, blob
    for name in VALIDATORS:
        require((ROOT / name).read_bytes() == files[name],
                "Auditing code differs from release source: " + name)
    project = files["pyproject.toml"].decode("utf-8")
    section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", project)
    require(section and re.search(r'^name\s*=\s*"ai-memory-book"\s*$', section[1], re.M)
            and re.search(r'^version\s*=\s*"' + re.escape(version) + r'"\s*$', section[1], re.M),
            "Committed package version differs")
    sources = {name.removeprefix("src/"): raw for name, raw in files.items()
               if name.startswith("src/memory_book/")}
    require("memory_book/static/index.html" in sources
            and f'__version__ = "{version}"'.encode() in sources["memory_book/__init__.py"],
            "Committed runtime/reader version differs")
    hasher = hashlib.sha256()
    for name, raw in sorted(sources.items()):
        if name.endswith((".py", ".c", ".h", ".rs")):
            hasher.update(name.removeprefix("memory_book/").encode() + b"\0" + raw + b"\0")
    require(hasher.hexdigest() == runtime_sha256
            == release.APPROVED_RUNTIME_SHA256.get(version), "Unapproved runtime aggregate")
    native_names = sorted(name for name in files if name.startswith("src/memory_book/_native")
                          and name.endswith((".c", ".h")))
    require(len(native_names) == 6, "Expected six frozen native source/header files")
    for name in [*native_names, FROZEN_AUDITOR]:
        require(files[name] == release.git(root, "show", native_baseline + ":" + name),
                "Frozen native source or historical auditor changed: " + name)
    identity = {"version": version, "tag": "v" + version, "commit": commit, "tree": tree,
                "epoch": int(release.git(root, "show", "-s", "--format=%ct", commit)),
                "runtime_sha256": runtime_sha256}
    inputs = {name: raw for name, raw in files.items()
              if name.startswith("src/memory_book/") or name in native.BUILD_INPUTS}
    return identity, sources, inputs, files, blobs


def collection(document, key):
    values = document[key]
    require(type(document["total_count"]) is int and document["total_count"] == len(values),
            "Incomplete paginated " + key + " response")
    require(len({value["id"] for value in values}) == len(values), "Duplicate " + key + " ID")
    return values


def successful_step(job, name):
    steps = [step for step in job["steps"] if step["name"] == name]
    require(len(steps) == 1 and steps[0]["status"] == "completed"
            and steps[0]["conclusion"] == "success", "Required step did not succeed: " + name)
    return steps[0]


def timestamp_free(text):
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r\n", "\n")
    return re.sub(r"(?m)^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z ", "", plain)


def audit_jobs(evidence, identity, run_id, attempt):
    run = evidence.json("run")
    require((run["id"], run["run_attempt"], run["head_sha"])
            == (run_id, attempt, identity["commit"]), "Release run identity differs")
    require(run["status"] == "completed" and run["conclusion"] == "success"
            and run["event"] == "push" and run["head_branch"] == "release/" + identity["tag"]
            and run["path"] == WORKFLOW
            and run["head_repository"]["full_name"] == release.REPOSITORY,
            "Release run is not a successful publication from this repository")
    jobs = collection(evidence.json("jobs"), "jobs")
    expected = {"preflight", "release", "published-install"}
    expected.update("native-wheel (" + target + ")" for target in native.TARGETS)
    by_name = {job["name"]: job for job in jobs}
    require(len(by_name) == len(jobs) and set(by_name) in (expected, expected | {"prepare-only"}),
            "Unexpected release job inventory")
    for job in jobs:
        require((job["run_id"], job["run_attempt"], job["head_sha"])
                == (run_id, attempt, identity["commit"]), "Job belongs to another source/run/attempt")
        require(job["status"] == "completed" and job["conclusion"]
                == ("skipped" if job["name"] == "prepare-only" else "success"),
                "Release job did not finish as required: " + job["name"])
    successful_step(by_name["preflight"], "Require the exact approved main commit and complete CI")
    successful_step(by_name["release"], "Verify existing CI, build, check and publish")
    successful_step(by_name["release"], "Preserve release assets and checksums")
    successful_step(by_name["published-install"], PUBLISHED_STEP)
    logs = {name: timestamp_free(evidence.read("logs/" + str(job["id"]) + ".log").decode("utf-8"))
            for name, job in by_name.items() if name != "prepare-only"}
    for target in native.TARGETS:
        job = by_name["native-wheel (" + target + ")"]
        names = [step["name"] for step in job["steps"]]
        require(len(names) == len(set(names)), "Duplicate native job step")
        numbers = [successful_step(job, prefix + version)["number"]
                   for version in native.PYTHON_VERSIONS
                   for prefix in ("Set up CPython ", "Build install and verify CPython ")]
        require(numbers == sorted(set(numbers)), "Native setup/build steps are not sequential")
        require(sum(name.startswith("Set up CPython ") for name in names) == 6
                and sum(name.startswith("Build install and verify CPython ") for name in names) == 6,
                "Unexpected native interpreter step inventory")
        for name in ("Retain each successfully tested wheel and receipt",
                     "Preserve all six native cell logs and validation records"):
            successful_step(job, name)
    ci_runs = collection(evidence.json("ci-runs"), "workflow_runs")
    ci_run = release.successful_ci(ci_runs, identity["commit"])
    require(ci_run["path"] == ".github/workflows/ci.yml", "Incorrect CI workflow")
    ci_jobs = collection(evidence.json("ci-jobs"), "jobs")
    release.verify_jobs(ci_jobs, ci_run["id"], identity["commit"])
    require(all(job["run_attempt"] == ci_run["run_attempt"] for job in ci_jobs),
            "CI jobs mix workflow attempts")
    return run, by_name, logs, {"run_id": ci_run["id"], "run_attempt": ci_run["run_attempt"],
                               "jobs": [{"id": job["id"], "name": job["name"]} for job in ci_jobs]}


def audit_artifacts(evidence, identity, run_id, attempt):
    artifacts = collection(evidence.json("artifacts"), "artifacts")
    suffix = str(run_id) + "-" + str(attempt)
    expected = {"release-" + suffix}
    expected.update(prefix + suffix + "-" + target for target in native.TARGETS
                    for prefix in ("native-wheel-", "native-cell-evidence-"))
    chosen = [item for item in artifacts if item["name"] in expected]
    require(len(chosen) == 11 and {item["name"] for item in chosen} == expected,
            "Missing or duplicate current-attempt artifacts")
    files, records = {}, []
    for item in chosen:
        require(not item["expired"] and item["workflow_run"]["id"] == run_id
                and item["workflow_run"]["head_sha"] == identity["commit"],
                "Artifact is expired or belongs to another source/run")
        raw = evidence.read("artifacts/" + str(item["id"]) + ".zip")
        require(len(raw) == item["size_in_bytes"] and item["digest"] == "sha256:" + sha(raw),
                "Artifact archive size/digest differs from API: " + item["name"])
        files[item["name"]] = zip_members(raw)
        records.append({"id": item["id"], "name": item["name"], "bytes": len(raw),
                        "sha256": sha(raw), "file_count": len(files[item["name"]])})
    return files, sorted(records, key=lambda item: item["name"])


def audit_public_assets(evidence, identity, sources, inputs, source_files, archives, run_id, attempt):
    suffix = str(run_id) + "-" + str(attempt)
    outer = archives["release-" + suffix]
    assets = {name.removeprefix("release-assets/"): raw for name, raw in outer.items()
              if name.startswith("release-assets/")}
    require(len(assets) == 67 and set(outer) == {"release-notes.md"}
            | {"release-assets/" + name for name in assets}, "Unexpected release artifact inventory")
    require(all(PurePosixPath(name).name == name for name in assets), "Nested release asset")
    document = evidence.json("release")
    require(document["tag_name"] == identity["tag"] and document["target_commitish"] == identity["commit"]
            and document["draft"] is False
            and document["prerelease"] is release.release_prerelease(identity["tag"]),
            "Public release identity/state differs")
    require(document["body"].replace("\r\n", "\n").strip()
            == outer["release-notes.md"].decode("utf-8").replace("\r\n", "\n").strip(),
            "Published release notes differ from the retained artifact")
    latest = evidence.json("latest-release")
    require(latest["id"] == document["id"] and latest["tag_name"] == identity["tag"]
            and latest["target_commitish"] == identity["commit"] and latest["draft"] is False,
            "Published stable release is not latest")
    api_assets = document["assets"]
    require(len(api_assets) == 67 and len({item["id"] for item in api_assets}) == 67
            and {item["name"] for item in api_assets} == set(assets), "Public API asset inventory differs")
    public = {}
    for item in api_assets:
        name = item["name"]
        raw = evidence.read("public-assets/" + name, native.legacy.MAX_ARCHIVE_BYTES)
        require(item["state"] == "uploaded" and item["size"] == len(raw)
                and item["digest"] == "sha256:" + sha(raw) and raw == assets[name],
                "Public asset differs from API or original release artifact: " + name)
        require(item["browser_download_url"] == "https://github.com/" + release.REPOSITORY
                + "/releases/download/" + identity["tag"] + "/" + name,
                "Unexpected public asset URL")
        public[name] = raw
    manifest = unique_json(public["release-manifest.json"])
    require(manifest["schema_version"] == 2 and manifest["repository"] == release.REPOSITORY
            and manifest["project"] == "ai-memory-book"
            and all(manifest.get(key) == value for key, value in identity.items()),
            "Manifest source/version/runtime identity differs")
    require(manifest["prerelease"] is release.release_prerelease(identity["tag"])
            and manifest["build_tools"] == release.BUILD_TOOLS
            and manifest["native_build_run"] == {"run_id": str(run_id), "run_attempt": attempt},
            "Manifest build provenance differs")
    require(manifest["runtime_files_sha256"] == native.file_hashes(sources)
            and manifest["source_files_sha256"] == native.file_hashes(inputs), "Manifest source hash inventory differs")
    require(set(manifest["assets"]) == set(public) - {"release-manifest.json", "SHA256SUMS"},
            "Manifest payload inventory differs")
    for name, record in manifest["assets"].items():
        require(record == {"bytes": len(public[name]), "sha256": sha(public[name])},
                "Manifest payload hash/size differs: " + name)
    sums = {}
    for line in public["SHA256SUMS"].decode("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        require(re.fullmatch(r"[0-9a-f]{64}", digest) and name not in sums, "Invalid or duplicate checksum")
        sums[name] = digest
    require(sums == {name: sha(raw) for name, raw in public.items() if name != "SHA256SUMS"},
            "Release checksum inventory differs")
    for name in release.INSTALLERS:
        require(public[name] == source_files["scripts/" + name], "Published installer source differs: " + name)
    require(evidence.read("public-install.py") == public["install.py"], "Public tagged installer source differs")
    fallback = f"ai_memory_book-{identity['version']}-py3-none-any.whl"
    sdist = f"ai_memory_book-{identity['version']}.tar.gz"
    require(manifest["python_fallback_wheel"] == fallback and manifest["source_distribution"] == sdist,
            "Fallback/source filenames differ")
    fallback_record = native.inspect_wheel(evidence.path("public-assets/" + fallback), identity, sources)
    native.inspect_sdist(evidence.path("public-assets/" + sdist), identity, sources, inputs)
    records, receipts = {}, {}
    require(len(manifest["native_wheels"]) == 30, "Expected exactly 30 native wheels")
    for declared in manifest["native_wheels"]:
        wheel_path = evidence.path("public-assets/" + declared["filename"])
        receipt_path = evidence.path("public-assets/" + declared["receipt"])
        actual, build = native.validate_receipt(receipt_path, wheel_path, identity, sources, inputs,
                                                run_id=run_id, run_attempt=attempt)
        require(actual == declared, "Manifest native wheel differs from inspected wheel/receipt")
        key = (build["python_version"], build["target"])
        require(key not in records, "Duplicate native matrix cell")
        records[key], receipts[key] = actual, unique_json(public[actual["receipt"]])
    require(set(records) == native.EXPECTED_MATRIX, "Native wheel matrix is incomplete")
    expected_assets = {fallback, sdist, "release-manifest.json", "SHA256SUMS", *release.INSTALLERS}
    expected_assets.update(record[key] for record in records.values() for key in ("filename", "receipt"))
    require(set(public) == expected_assets, "Unexpected public payload")
    for target in native.TARGETS:
        expected = {record[key]: public[record[key]] for (version, platform), record in records.items()
                    if platform == target for key in ("filename", "receipt")}
        require(len(expected) == 12 and archives["native-wheel-" + suffix + "-" + target] == expected,
                "Grouped wheel artifact differs from the six published wheel/receipt pairs")
    return document, manifest, records, receipts, public, fallback_record


def platform_path(value, target):
    path = PureWindowsPath(value) if target == "windows_amd64" else PurePosixPath(value)
    require(path.is_absolute(), "Cell subprocess path is not absolute")
    return str(path).replace("\\", "/")


def command_contract(commands, executable, target, version, record):
    by_phase = {entry["phase"]: entry for entry in commands}
    require(by_phase["build-tools"]["command"] == [executable, "-m", "pip", "install",
            "setuptools==80.9.0", "wheel==0.45.1", "build==1.3.0"], "Build tool command differs")
    cp = "cp" + version.replace(".", "")
    compile_args = by_phase["compile-wheel"]["command"]
    require(len(compile_args) == 10 and compile_args[:8] == [executable, "-m", "pip", "wheel",
            "--verbose", "--no-deps", "--no-build-isolation", "--wheel-dir"] and compile_args[-1] == ".",
            "Native compile command differs")
    require(platform_path(compile_args[8], target).endswith("/native-build-cells/" + target + "/" + cp + "/raw"),
            "Cell raw build directory differs")
    install_args = by_phase["install-wheel"]["command"]
    require(len(install_args) == 7 and install_args[:6] == [executable, "-m", "pip", "install",
            "--no-deps", "--force-reinstall"], "Installed wheel command differs")
    require(platform_path(install_args[6], target).endswith("/native-build-cells/" + target
            + "/" + cp + "/repaired/" + record["filename"]), "Installed cell wheel differs")
    require(by_phase["isolated-native-import"]["command"] == [executable, "-I", "-c",
            "from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'"],
            "Isolated native import command differs")
    require(by_phase["installed-native-tests"]["command"] == [executable, "-m", "unittest", *cell.SUITES, "-v"],
            "Installed native suite selection differs")
    require(by_phase["installed-native-smoke-and-receipt"]["command"] == [executable,
            "scripts/native_release.py", "receipt", "--wheel", install_args[6], "--output",
            install_args[6] + ".receipt.json", "--target", target], "Original smoke/receipt command differs")
    if target.startswith("linux_"):
        require(by_phase["abi-tools"]["command"] == [executable, "-m", "pip", "install",
                "auditwheel==6.4.2", "patchelf==0.17.2.4"], "Linux ABI tool command differs")
        repair = by_phase["repair-wheel"]["command"]
        require(len(repair) == 10 and repair[:8] == [executable, "-m", "auditwheel", "repair",
                "--only-plat", "--plat", "manylinux_2_17_" + target.removeprefix("linux_"), "--wheel-dir"]
                and platform_path(repair[8], target) == platform_path(install_args[6], target).rsplit("/", 1)[0]
                and platform_path(repair[9], target).rsplit("/", 1)[0] == platform_path(compile_args[8], target),
                "Linux repair command or cell directory differs")


def audit_cells(identity, manifest, records, receipts, public, archives, jobs, logs, run_id, attempt):
    cells = []
    suffix = str(run_id) + "-" + str(attempt)
    for target in native.TARGETS:
        name = "native-wheel (" + target + ")"
        job, plain_job = jobs[name], logs[name]
        files = archives["native-cell-evidence-" + suffix + "-" + target]
        starts = list(re.finditer(r"(?m)^##\[group\]Run [^\n]*scripts/build_native_release_cell\.py"
                                 r" --expected-python (3\.\d+) --target[^\n]*$", plain_job))
        require([match[1] for match in starts] == list(native.PYTHON_VERSIONS),
                "Job log lacks six sequential explicit interpreter invocations")
        blocks = {}
        for match in starts:
            end = re.search(r"(?m)^##\[group\]Run ", plain_job[match.end():])
            blocks[match[1]] = plain_job[match.start():match.end() + end.start() if end else len(plain_job)]
        expected_names = set()
        for version in native.PYTHON_VERSIONS:
            key = (version, target)
            cp, step = "cp" + version.replace(".", ""), "cell" + version.replace(".", "")
            prefix = cp + "/"
            build_log = "native-build-" + target + "-" + cp + ".log"
            log_names = {"tools.log", build_log, "install.log", "native-import.log", "test.log", "receipt.log"}
            phases = ["build-tools"]
            if target.startswith("linux_"):
                log_names.update(("abi-tools.log", "repair.log"))
                phases.append("abi-tools")
            phases.append("compile-wheel")
            if target.startswith("linux_"):
                phases.append("repair-wheel")
            if target.startswith("macos_"):
                log_names.add("architecture.log")
                phases.append("macho-slices")
            phases += ["install-wheel", "isolated-native-import", "installed-native-tests",
                       "installed-native-smoke-and-receipt"]
            expected_names.update(prefix + name for name in log_names | {"validation.json"})
            require(all(prefix + name in files for name in log_names | {"validation.json"}), "Missing cell evidence")
            report = unique_json(files[prefix + "validation.json"])
            record, receipt = records[key], receipts[key]
            require(report["schema_version"] == 1 and report["status"] == "passed"
                    and (report["expected_python"], report["target"], report["step_id"]) == (version, target, step),
                    "Cell result/interpreter/step differs")
            require(report["run_id"] == str(run_id) and report["run_attempt"] == str(attempt)
                    and report["runner_name"] == job["runner_name"] and bool(report["runner_name"]),
                    "Cell run/attempt/runner differs")
            require(report["source"] == {key: identity[key] for key in ("version", "tag", "commit", "tree")}
                    | {"files_sha256": manifest["source_files_sha256"]}, "Cell source/build hashes differ")
            interpreter = report["interpreter"]
            require(interpreter["implementation"] == "cpython" and interpreter["python_version"] == version
                    and re.match(re.escape(version) + r"\.", interpreter["setup_python_version"])
                    and interpreter["version"].startswith(interpreter["setup_python_version"] + " "),
                    "Cell resolved interpreter version differs")
            executable = interpreter["executable"]
            platform_path(executable, target)
            platform_path(interpreter["setup_python_path"], target)
            block_lines = {line.strip() for line in blocks[version].splitlines()}
            require({"NATIVE_CELL_PYTHON: " + interpreter["setup_python_path"],
                     "NATIVE_CELL_RESOLVED_VERSION: " + interpreter["setup_python_version"],
                     "NATIVE_CELL_STEP: " + step, "WHEEL_TARGET: " + target} <= block_lines,
                    "Actual step environment differs from setup-python/cell identity")
            commands = report["commands"]
            require(report["build_log"] == build_log and [entry["phase"] for entry in commands] == phases
                    and len({entry["log"] for entry in commands}) == len(commands)
                    and {entry["log"] for entry in commands} == log_names, "Cell command/log inventory differs")
            actual_commands = [(match[1], unique_json(match[2])) for match in re.finditer(
                r"(?m)^CELL COMMAND ([a-z-]+) (\[[^\n]+\])$", blocks[version])]
            require(actual_commands == [(entry["phase"], entry["command"]) for entry in commands],
                    "Job command transcript differs from cell validation")
            for entry in commands:
                require(entry["returncode"] == 0 and isinstance(entry["elapsed_seconds"], (int, float))
                        and entry["elapsed_seconds"] >= 0 and entry["cwd"] == commands[0]["cwd"],
                        "Cell subprocess failed or changed working directory")
                platform_path(entry["cwd"], target)
                raw = files[prefix + entry["log"]]
                require(entry["log_bytes"] == len(raw) and entry["log_sha256"] == sha(raw),
                        "Cell command log bytes/hash differ")
                require(entry["phase"] == "macho-slices" or entry["command"][0] == executable,
                        "Cell subprocess uses another interpreter")
                printed = timestamp_free(raw.decode("utf-8")).strip("\n")
                require(not printed or printed in blocks[version], "Cell raw output absent from actual step log")
            command_contract(commands, executable, target, version, record)
            raw_build = files[prefix + build_log]
            build = receipt["build"]["build_log"]
            require(build["filename"] == build_log and build["bytes"] == len(raw_build)
                    and build["sha256"] == sha(raw_build), "Receipt compiler log hash/size differs")
            compiler = re.compile(r"\b(?:gcc(?:-\d+)?|g\+\+|cc|clang(?:-cl)?|cl\.exe|link\.exe)\b", re.I)
            lines = [line.strip() for line in raw_build.decode("utf-8").splitlines()
                     if "_native" in line and compiler.search(line)
                     and re.search(r"(?:^|\s)(?:-c|-shared|-bundle|/c|/DLL)(?:\s|$)", line, re.I)]
            require(lines and lines == build["commands"], "Receipt compiler commands differ from retained compilation")
            tests = cell.test_summary(files[prefix + "test.log"].decode("utf-8"))
            cell.validate_test_result(tests, 0)
            require(report["tests"] == {**tests, "returncode": 0, "suites": list(cell.SUITES),
                    "log": "test.log", "log_sha256": sha(files[prefix + "test.log"])},
                    "Declared cell tests differ from the current validator's actual log result")
            if target.startswith("macos_"):
                arch = target.removeprefix("macos_")
                require(report["macos_build"]["architecture"] == arch
                        and report["macos_build"]["observed_slices"] == [arch]
                        and files[prefix + "architecture.log"].decode("utf-8").split() == [arch],
                        "Mach-O slice evidence differs")
                macho = next(entry["command"] for entry in commands if entry["phase"] == "macho-slices")
                require(len(macho) == 3 and macho[:2] == ["lipo", "-archs"]
                        and PurePosixPath(macho[2]).name == PurePosixPath(record["native_member"]).name,
                        "Mach-O inspection command differs")
            require(report["wheel"] == {key: record[key] for key in
                    ("filename", "bytes", "sha256", "native_sha256")}
                    and report["receipt"] == {"filename": record["receipt"], "sha256": sha(public[record["receipt"]])}
                    and report["runtime_smoke"] == receipt["runtime_smoke"],
                    "Cell wheel/receipt/native smoke differs from published bytes")
            cells.append({"python_version": version, "target": target, "job_id": job["id"],
                          "step_id": step, "runner_name": report["runner_name"], "interpreter": interpreter,
                          "setup_step_number": successful_step(job, "Set up CPython " + version)["number"],
                          "build_step_number": successful_step(job, "Build install and verify CPython " + version)["number"],
                          "validation_sha256": sha(files[prefix + "validation.json"]),
                          "wheel": report["wheel"], "receipt": report["receipt"],
                          "tests": {**report["tests"], "passed": cell.EXPECTED_TESTS - tests["skipped"]},
                          "compiler_log": build, "runtime_smoke": report["runtime_smoke"],
                          "commands": [{key: entry[key] for key in
                                       ("phase", "command", "returncode", "log", "log_bytes", "log_sha256")}
                                       for entry in commands]})
        require(set(files) == expected_names, "Unexpected grouped cell evidence file inventory")
    require(len(cells) == 30 and {(item["python_version"], item["target"]) for item in cells}
            == native.EXPECTED_MATRIX, "Incomplete independently tested cell matrix")
    return cells


def published_installer_proof(workflow, job, plain_log, identity):
    """Bind the successful job to its exact committed public-install script."""
    tail = workflow.decode("utf-8").split("      - name: " + PUBLISHED_STEP + "\n")
    require(len(tail) == 2, "Published installer step is not unique in committed workflow")
    script = tail[1].split("        run: |\n", 1)[1]
    lines = []
    for line in script.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:] if line else "")
    require(lines, "Committed public installer script is empty")
    groups = list(re.finditer(r"(?m)^##\[group\]Run [^\n]*$", plain_log))
    matches = []
    for index, group in enumerate(groups):
        block = plain_log[group.start():groups[index + 1].start() if index + 1 < len(groups) else len(plain_log)]
        command, separator, output = block.partition("\n##[endgroup]\n")
        if (separator and command.splitlines()[0] == "##[group]Run " + lines[0]
                and "\n".join(lines[1:]).strip() in command):
            matches.append((command, output))
    require(len(matches) == 1, "Actual public installer command differs from committed workflow")
    command, output = matches[0]
    environment = re.findall(r"(?m)^\s*(RELEASE_TAG|RELEASE_VERSION|RELEASE_COMMIT): ([^\n]*)$", command)
    expected = {"RELEASE_TAG": identity["tag"], "RELEASE_VERSION": identity["version"],
                "RELEASE_COMMIT": identity["commit"]}
    require(len(environment) == 3 and dict(environment) == expected,
            "Public installer step environment differs from audited release identity")
    require(output.splitlines().count(PUBLISHED_MARKER) == 1
            and "Default text backend: native" in output,
            "Actual public installer did not report the successful native default installation")
    return {"job_id": job["id"], "step_number": successful_step(job, PUBLISHED_STEP)["number"],
            "script_sha256": sha(("\n".join(lines).rstrip() + "\n").encode()),
            "release_environment": expected,
            "terminal_result": PUBLISHED_MARKER,
            "scope": "Existing hosted public-URL installer and default native-wheel/MCP/client checks; not rerun by this audit."}


def audit(evidence, snapshot, run_id, attempt, native_baseline):
    identity, sources, inputs, source_files, blobs = snapshot
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0,
            "Expected positive run ID and attempt")
    commit = evidence.json("commit")
    require(commit["sha"] == identity["commit"] and commit["commit"]["tree"]["sha"] == identity["tree"],
            "GitHub commit/tree differs from exact Git objects")
    for filename, reference in (("main-ref", "refs/heads/main"), ("tag-ref", "refs/tags/" + identity["tag"])):
        value = evidence.json(filename)
        require(value["ref"] == reference and value["object"]["type"] == "commit"
                and value["object"]["sha"] == identity["commit"], "Published main/tag source differs")
    run, jobs, logs, ci = audit_jobs(evidence, identity, run_id, attempt)
    archives, artifacts = audit_artifacts(evidence, identity, run_id, attempt)
    document, manifest, records, receipts, public, fallback = audit_public_assets(
        evidence, identity, sources, inputs, source_files, archives, run_id, attempt)
    cells = audit_cells(identity, manifest, records, receipts, public, archives, jobs, logs, run_id, attempt)
    installer = published_installer_proof(source_files[WORKFLOW], jobs["published-install"],
                                          logs["published-install"], identity)
    # Re-read every input after inspection: reject accidental staged-file changes.
    for name in list(evidence.inventory):
        evidence.read(name)
    return {"schema_version": 1, "status": "passed", "published": True, "source": identity,
            "native_baseline_commit": native_baseline, "source_git_blobs": blobs,
            "source_files_sha256": native.file_hashes(inputs),
            "audit_code_sha256": {name: sha(source_files[name]) for name in (*VALIDATORS, WORKFLOW)},
            "release": {key: document[key] for key in
                        ("id", "tag_name", "target_commitish", "html_url", "draft", "prerelease", "published_at")},
            "workflow": {key: run[key] for key in
                         ("id", "run_attempt", "head_sha", "head_branch", "path", "status", "conclusion", "html_url")},
            "ci": ci, "jobs": [{key: job[key] for key in
                    ("id", "name", "run_id", "run_attempt", "head_sha", "status", "conclusion", "html_url")}
                    for job in jobs.values()],
            "artifacts": artifacts, "assets": {name: {"bytes": len(raw), "sha256": sha(raw)}
                                                for name, raw in sorted(public.items())},
            "counts": {"native_cells": len(cells), "native_test_outcomes": len(cells) * cell.EXPECTED_TESTS,
                       "native_passed": sum(item["tests"]["passed"] for item in cells),
                       "native_skipped": sum(item["tests"]["skipped"] for item in cells),
                       "public_assets": len(public), "manifest_payloads": len(manifest["assets"]),
                       "checksum_entries": len(public) - 1},
            "native_cells": cells, "fallback_wheel": fallback, "published_installer": installer,
            "staged_evidence": dict(sorted(evidence.inventory.items())),
            "scope": "Offline read-only verification of staged GitHub API responses, original artifacts, decoded job logs, "
                     "public release bytes and exact Git source. Acquisition authenticity relies on the caller's "
                     "GitHub downloads. No builds, package installation, native execution, performance measurement, "
                     "workflow retry or publication occurred in this audit."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--native-baseline", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path,
                        help="New proof JSON; refuse to overwrite any previous result")
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Never overwrite an existing audit result")
    snapshot = source_snapshot(args.repo_root, args.source_commit, args.version,
                               args.runtime_sha256, args.native_baseline)
    proof = audit(Evidence(args.evidence), snapshot, args.run_id, args.run_attempt, args.native_baseline)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": proof["status"], "source": proof["source"], "counts": proof["counts"],
                      "proof": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
