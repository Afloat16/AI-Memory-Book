"""Source-free reproduction of J's post-correctness inventory guard failure.

Only the unchanged artificial correctness fixtures execute. No development
corpus, profile, paired worker, model or fresh data is opened by this program.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from scripts import round5_j_development as original

ATTEMPT = "round5-j-source-inventory-1"
BRANCH = "validation/v033-j-source-inventory-1"
PUBLIC = ROOT / "benchmarks/reports" / ATTEMPT
STATE = ROOT / ".artifacts" / ATTEMPT
SCOPE = ROOT / "benchmarks/experiments/round5-j-source-inventory-scope.json"
SOURCE = "910ba8904523ad81cb7d68073af77580942496eb"
BINDING_SHA = "c7a5857628cd1b9d391522c6cd50794a8c486e3959e08c924f520e3a48a9342a"
FLAGS = ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "PYTHONHASHSEED", "PYTHONUNBUFFERED")


class PublicationError(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def parse_remote(raw):
    fields = raw.split()
    if not fields:
        return None
    if len(fields) != 2 or fields[1] != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise PublicationError("Unexpected remote result-ref response")
    return fields[0]


def remote_head():
    return parse_remote(git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH))


def publish(message):
    """One non-force push; reject divergent refs and never retry ambiguous writes."""
    journal = STATE / "publication.json"
    if (PUBLIC / "publication-failure.json").exists():
        raise PublicationError("Publication already failed; artifact-only preservation")
    expected = read(journal)["expected_remote"]
    parent = git("rev-parse", "HEAD")
    try:
        if remote_head() != expected:
            raise PublicationError("Another writer owns or advanced the result ref")
        if expected is not None and parent != expected:
            raise PublicationError("Local result ancestry changed")
        if git("diff", "--cached", "--name-only"):
            raise PublicationError("Unrelated staged changes")
        subprocess.run(["git", "add", "--sparse", "--", str(PUBLIC.relative_to(ROOT))], cwd=ROOT, check=True)
        staged = git("diff", "--cached", "--name-only").splitlines()
        prefix = str(PUBLIC.relative_to(ROOT)) + "/"
        if not staged or any(not path.startswith(prefix) for path in staged):
            raise PublicationError("Checkpoint contains missing or unrelated files")
        subprocess.run(["git", "commit", "-m", message + " [skip ci]"], cwd=ROOT, check=True)
        head = git("rev-parse", "HEAD")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH],
                                cwd=ROOT, capture_output=True, text=True)
        observed = remote_head()
        if pushed.returncode or observed != head:
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected, "local_commit": head,
                "observed_remote": observed, "push_returncode": pushed.returncode,
                "stdout": pushed.stdout, "stderr": pushed.stderr,
                "policy": "No automatic write or measurement retry; retain artifacts."})
            raise PublicationError("Push failed or did not verify at the expected commit")
        save(journal, {"expected_remote": head})
        print(json.dumps({"checkpoint": head, "branch": BRANCH, "message": message}), flush=True)
    except BaseException as error:
        if not (PUBLIC / "publication-failure.json").exists():
            save(PUBLIC / "publication-failure.json", {
                "created_at": stamp(), "expected_previous": expected,
                "error": type(error).__name__ + ": " + str(error),
                "policy": "No automatic retry; inspect remote ref and artifact evidence."})
        raise



def difference(actual, frozen):
    return {
        "added": {name: actual[name] for name in sorted(set(actual) - set(frozen))},
        "missing": {name: frozen[name] for name in sorted(set(frozen) - set(actual))},
        "changed": {name: {"expected": frozen[name], "actual": actual[name]}
                    for name in sorted(set(actual) & set(frozen)) if actual[name] != frozen[name]},
    }


def export(directory, binding):
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory.with_suffix(".tar")
    subprocess.run(["git", "archive", "--format=tar", "--output=" + str(archive),
                    SOURCE, "src", "tests"], cwd=ROOT, check=True)
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            if (not member.name or Path(member.name).parts[0] not in ("src", "tests")
                    or ".." in Path(member.name).parts or not (member.isdir() or member.isfile())):
                raise ValueError("Unexpected source archive member")
        stream.extractall(directory)
    archive.unlink()
    actual = original.source_files(directory)
    if actual != binding["files_sha256"]:
        raise ValueError("Independent export differs from frozen source")
    original.verify_files(binding["correctness_files_sha256"], directory)
    return actual


def child(source):
    """Same suite, cwd, source bytes and environment as the failed correctness step."""
    binding = read(original.SOURCE_BINDING)
    frozen = binding["files_sha256"]
    save(PUBLIC / "before-suite.json", original.source_files(source))
    if original.source_files(source) != frozen:
        raise ValueError("Artificial suite did not start from the frozen file inventory")
    current_test = [None]

    def observe_subprocess(event, args):
        if event != "subprocess.Popen":
            return
        executable, arguments, cwd, environment = args
        arguments = [os.fsdecode(value) for value in arguments]
        if "-m" not in arguments or "memory_book" not in arguments:
            return
        effective = os.environ if environment is None else environment
        append(PUBLIC / "mcp-subprocesses.jsonl", {
            "test": current_test[0], "executable": os.fsdecode(executable),
            "argv": arguments, "cwd": None if cwd is None else os.fsdecode(cwd),
            "environment_supplied_explicitly": environment is not None,
            "selected_environment": {key: effective.get(key) for key in FLAGS},
        })

    # Observation only: the hook does not replace subprocess, fixture or SDK code.
    sys.addaudithook(observe_subprocess)
    modules = list(original.CORRECTNESS_MODULES)
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    origins = {}
    for name in modules:
        path = Path(sys.modules[name].__file__).resolve()
        expected = source / (name.replace(".", "/") + ".py")
        if path != expected.resolve() or sha(path) != binding["correctness_files_sha256"][name.replace(".", "/") + ".py"]:
            raise ValueError("A correctness module loaded from another source")
        origins[name] = {"path": str(path), "sha256": sha(path)}
    import memory_book
    if Path(memory_book.__file__).resolve().parent != source / "src/memory_book":
        raise ValueError("Artificial suite imported another runtime")
    save(PUBLIC / "suite-origins.json", origins)
    save(PUBLIC / "after-suite-load.json", original.source_files(source))

    import mcp.client.stdio as sdk
    from tests.test_title_reference_interfaces import TitleReferenceMCPTests
    case = TitleReferenceMCPTests("test_real_stdio_strict_boolean_default_and_complete_projection_parity")
    case.database = str(STATE / "invented-parameter-inspection.db")
    parameters = case.parameters()
    defaults = sdk.get_default_environment()
    save(PUBLIC / "sdk-environment.json", {
        "mcp_version": importlib.metadata.version("mcp"),
        "sdk_module_sha256": sha(Path(sdk.__file__)),
        "default_environment_function_sha256": hashlib.sha256(
            inspect.getsource(sdk.get_default_environment).encode()).hexdigest(),
        "default_keys": sorted(defaults),
        "fixture_explicit_keys": sorted(parameters.env),
        "parent_selected_environment": {key: os.environ.get(key) for key in FLAGS},
        "sdk_default_selected_environment": {key: defaults.get(key) for key in FLAGS},
        "fixture_explicit_selected_environment": {key: parameters.env.get(key) for key in FLAGS},
        "interpretation": "Values outside the selected nonsecret Python flags are not recorded.",
    })
    previous = [original.source_files(source)]

    class InventoryResult(unittest.TextTestResult):
        def startTest(self, test):
            current_test[0] = test.id()
            super().startTest(test)

        def stopTest(self, test):
            actual = original.source_files(source)
            append(PUBLIC / "per-test-inventory.jsonl", {
                "test": test.id(), "inventory": actual,
                "difference_from_frozen": difference(actual, frozen),
                "difference_from_previous": difference(actual, previous[0]),
            })
            previous[0] = actual
            super().stopTest(test)
            current_test[0] = None

    expected = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2, resultclass=InventoryResult).run(suite)
    actual = original.source_files(source)
    delta = difference(actual, frozen)
    bytecode = {}
    for name in delta["added"]:
        path = source / name
        if path.suffix == ".pyc" and path.parent.name == "__pycache__":
            source_file = path.parent.parent / (path.name.split(".cpython-", 1)[0] + ".py")
            raw = path.read_bytes()
            bytecode[name] = {
                "sha256": sha(path), "bytes": len(raw), "header_hex": raw[:16].hex(),
                "magic_matches_interpreter": raw[:4] == importlib.util.MAGIC_NUMBER,
                "compiled_source": str(source_file.relative_to(source)),
                "compiled_source_sha256": sha(source_file) if source_file.is_file() else None,
            }
    save(PUBLIC / "after-suite.json", actual)
    save(PUBLIC / "bytecode.json", bytecode)
    save(PUBLIC / "correctness.json", {
        "modules": modules, "expected": expected, "tests": result.testsRun,
        "errors": len(result.errors), "failures": len(result.failures),
        "skipped": len(result.skipped), "passed": result.wasSuccessful(),
        "difference": delta, "bytecode_added": len(bytecode),
        "all_added_are_recognized_bytecode": bool(delta["added"]) and set(bytecode) == set(delta["added"])
            and all(value["magic_matches_interpreter"] for value in bytecode.values()),
        "development_corpus_calls": 0, "profile_calls": 0, "paired_calls": 0,
    })
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun == expected else 1


def run():
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1" or os.environ.get("GITHUB_REF") != "refs/heads/diagnostic/v033-j-source-inventory-1":
        raise ValueError("Only this registered first artificial diagnostic may execute")
    if sha(original.SOURCE_BINDING) != BINDING_SHA:
        raise ValueError("Frozen J source binding changed")
    binding = read(original.SOURCE_BINDING)
    if binding["commit"] != SOURCE or original.frozen_source()["files_sha256"] != binding["files_sha256"]:
        raise ValueError("Wrong exact source")
    for path in (Path(__file__), SCOPE, original.SOURCE_BINDING, Path(original.__file__)):
        if subprocess.check_output(["git", "show", "HEAD:" + str(path.relative_to(ROOT))], cwd=ROOT) != path.read_bytes():
            raise ValueError("Diagnostic input differs from its committed blob")
    if STATE.exists() or PUBLIC.exists() or remote_head() is not None:
        raise ValueError("Artificial diagnostic already claimed; no automatic replay")
    STATE.mkdir(parents=True)
    PUBLIC.mkdir(parents=True)
    save(STATE / "publication.json", {"expected_remote": None})
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    save(PUBLIC / "intent.json", {
        "status": "started", "created_at": stamp(), "source": SOURCE,
        "scope_sha256": sha(SCOPE), "source_binding_sha256": BINDING_SHA,
        "original_driver_sha256": sha(Path(original.__file__)), "diagnostic_script_sha256": sha(Path(__file__)),
        "run_id": os.environ["GITHUB_RUN_ID"], "workflow_commit": os.environ["GITHUB_SHA"],
        "development_corpus_calls": 0, "model_downloads": 0, "fresh_rows_decoded": 0,
    })
    publish("bench: claim source-free J inventory diagnosis")
    try:
        subprocess.run(["git", "fetch", "--filter=blob:none", "--depth=1", "--no-tags",
                        "origin", SOURCE], cwd=ROOT, check=True)
        source = STATE / "tested-export"
        before = export(source, binding)
        save(PUBLIC / "export.json", {"source": SOURCE, "inventory": before,
            "environment": {key: os.environ.get(key) for key in FLAGS}})
        publish("bench: bind clean J artificial fixture export before execution")
        env = dict(os.environ, PYTHONPATH=str(source / "src") + os.pathsep + str(ROOT))
        bootstrap = "import runpy,sys; path=sys.argv.pop(1); runpy.run_path(path,run_name='__main__')"
        command = [sys.executable, "-c", bootstrap, str(Path(__file__).resolve()), "child", "--source", str(source)]
        returncode, error_text = None, None
        try:
            with (PUBLIC / "correctness.log").open("xb") as log:
                returncode = subprocess.run(command, cwd=source, env=env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=300).returncode
        except BaseException as error:
            error_text = type(error).__name__ + ": " + str(error)
        save(PUBLIC / "exit.json", {"returncode": returncode, "error": error_text, "finished_at": stamp()})
        publish("bench: preserve J artificial suite inventory observations")
        if error_text or returncode:
            raise RuntimeError("Artificial correctness execution did not complete")
        result = read(PUBLIC / "correctness.json")
        independent = export(STATE / "independent-clean-export", binding)
        save(PUBLIC / "independent-export.json", {
            "source": SOURCE, "inventory": independent,
            "difference": difference(independent, binding["files_sha256"]),
            "original_all_files_guard_passes": independent == binding["files_sha256"],
            "fixtures_or_corpus_executed_on_this_export": 0,
        })
        events = [json.loads(line) for line in (PUBLIC / "mcp-subprocesses.jsonl").read_text().splitlines()]
        delta = result["difference"]
        explained = (result["passed"] and not result["errors"] and not result["failures"] and not result["skipped"]
                     and not delta["missing"] and not delta["changed"]
                     and result["all_added_are_recognized_bytecode"]
                     and events and all(event["selected_environment"]["PYTHONDONTWRITEBYTECODE"] is None for event in events))
        save(PUBLIC / "diagnosis.json", {
            "status": "completed", "source": SOURCE, "runtime_sha256": binding["runtime_sha256"],
            "correctness_tests": result["tests"], "added_files": len(delta["added"]),
            "missing_bound_files": len(delta["missing"]), "changed_bound_files": len(delta["changed"]),
            "mcp_subprocesses_observed": len(events),
            "reproduced_missing_mcp_bytecode_flag_and_generated_bytecode": bool(explained),
            "original_all_files_guard_rejects_tested_export": original.source_files(source) != binding["files_sha256"],
            "independent_exact_export_passes_same_inventory_guard": independent == binding["files_sha256"],
            "original_attempt_inventory_recovered": False,
            "evidence_limit": "This new artificial reproduction identifies a causal failure mechanism. The failed development VM did not publish its actual differing inventory, so its exact files cannot be reconstructed retrospectively.",
            "proposal": "Register recovery2 separately. Run fixtures on an isolated exact correctness export; preserve its explicit inventory differences. Export fresh exact runtime bytes for measurement and retain the strict full-file guard. Do not edit source910ba, old driver, existing reports, gates or attempt1.",
            "development_corpus_calls": 0, "profile_calls": 0, "paired_calls": 0, "fresh_rows_decoded": 0,
        })
        publish("bench: preserve source-free J diagnosis and independent export proof")
        if not explained:
            raise RuntimeError("Reproduction did not establish the registered bytecode mechanism")
    except BaseException as error:
        save(PUBLIC / "failure.json", {"status": "failed_or_incomplete",
            "created_at": stamp(), "error": type(error).__name__ + ": " + str(error),
            "development_corpus_calls": 0, "replay_permitted": False})
        if not (PUBLIC / "publication-failure.json").exists():
            publish("bench: preserve incomplete source-free J diagnosis")
        raise


def preserve():
    if not PUBLIC.exists() or not (STATE / "publication.json").exists():
        return
    log = ROOT / ".artifacts" / (ATTEMPT + "-runner.log")
    if log.exists():
        shutil.copyfile(log, PUBLIC / "runner.log")
    save(PUBLIC / "workflow-outcome.json", {"created_at": stamp(),
        "outcome": os.environ.get("DIAGNOSTIC_OUTCOME"), "development_corpus_calls": 0})
    if not (PUBLIC / "publication-failure.json").exists():
        publish("bench: preserve J diagnosis workflow logs and partial evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "child", "preserve"))
    parser.add_argument("--source", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "run":
        run()
    elif arguments.mode == "preserve":
        preserve()
    else:
        if arguments.source is None:
            parser.error("Child needs exact source export")
        raise SystemExit(child(arguments.source.resolve()))
