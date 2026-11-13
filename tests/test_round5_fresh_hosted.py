"""Artificial controller fixtures only: local Git remotes and invented assets/DB-free identities."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import round5_fresh_hosted as h


def initialize(path, bare=False):
    path.mkdir(parents=True, exist_ok=True)
    h.git(path, "init", *(["--bare"] if bare else []))
    h.git(path, "config", "user.name", "Artificial fixture")
    h.git(path, "config", "user.email", "fixture@example.invalid")
    return path


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else h.raw(value))
    return path


def commit(root):
    h.git(root, "add", ".")
    h.git(root, "commit", "-m", "invented fixture")
    return h.git(root, "rev-parse", "HEAD").decode().strip()


def authorization_fixture(root):
    """Only the preflight envelope is synthetic; the actual certificate loader is unchanged."""
    initialize(root)
    scope = h.read(h.ROOT / h.SCOPE)
    scope["protocols"]["preserved_original_files_sha256"] = {
        "scripts/legacy.py": hashlib.sha256(b"# preserved artificial legacy\n").hexdigest()}
    for path in scope["files"].values():
        write(root, path, b"# artificial registered file\n")
    write(root, h.SCOPE, scope)
    write(root, "scripts/legacy.py", b"# preserved artificial legacy\n")
    write(root, "scripts/generator.py", b"# artificial certificate generator\n")
    evidence = "benchmarks/experiments/artificial-source-choice.json"
    write(root, evidence, {"fixture": "invented selection evidence; no real candidate choice"})
    sources = {"baseline": h.BASELINE, "candidate": {"commit": "b" * 40, "runtime_sha256": "b" * 64}}
    certificate = {"schema_version": 1, "evaluator": "round5-final-interface-certificate-1",
        "status": "verified-before-formal-measurement-and-fresh-selection", "sources": sources,
        "packages": h.CERT_PACKAGES, "server_packages": {label: h.CERT_PACKAGES for label in sources},
        "generator_commit": "c" * 40,
        "generator_files": {"scripts/generator.py": h.sha(root / "scripts/generator.py")},
        "observations": {label: {"artificial_envelope_only": True} for label in sources},
        "retrieval_calls_executed": 0}
    write(root, h.CERTIFICATE, certificate)
    files = [path.relative_to(root).as_posix() for path in root.rglob("*")
             if path.is_file() and ".git" not in path.parts]
    names = h.inventory_names(files, scope, certificate, evidence)
    authorization = {"schema_version": 1, "protocol": h.ATTEMPT, "status": "approved-for-first-fresh-attempt",
        "attempt": h.ATTEMPT, "sources": sources,
        "source_files_sha256": {label: {"src/memory_book/__init__.py": "a" * 64} for label in sources},
        "selection_evidence": {"path": evidence, "sha256": h.sha(root / evidence)},
        "interface_certificate": {"path": h.CERTIFICATE, "sha256": h.sha(root / h.CERTIFICATE)},
        "frozen_files_sha256": {name: h.sha(root / name) for name in names},
        "additional_exclusions": [], "fresh_rows_decoded_before_authorization": 0}
    write(root, h.AUTH, authorization)
    commit(root)
    return scope, authorization, certificate


def publisher_fixture(directory):
    root, remote = initialize(directory / "checkout"), initialize(directory / "origin.git", True)
    write(root, "README.md", b"Only invented data.\n")
    write(root, ".gitignore", b".artifacts/\n")
    commit(root)
    h.git(root, "remote", "add", "origin", str(remote))
    public, state = root / h.PUBLIC, root / h.PRIVATE
    public.mkdir(parents=True)
    h.save(state / "publication.json", {"expected_remote": None})
    return h.Publisher(root, public, state), remote


class FreshHostedTests(unittest.TestCase):
    def test_missing_authorization_or_certificate_precedes_claim_download_or_git_fetch(self):
        for omitted in (h.AUTH, h.CERTIFICATE):
            with self.subTest(omitted=omitted), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                write(root, h.SCOPE, {})
                if omitted == h.CERTIFICATE:
                    write(root, h.AUTH, {})
                controller = h.Controller(root)
                with patch.object(h.Publisher, "remote", side_effect=AssertionError("remote touched")), \
                     patch.object(h, "prepare_sources", side_effect=AssertionError("source download")), \
                     patch.object(h, "prepare_assets", side_effect=AssertionError("asset download")):
                    with self.assertRaisesRegex(ValueError, "authorization/certificate missing"):
                        controller.start()
                self.assertFalse((root / h.PUBLIC).exists())
                self.assertFalse((root / h.PRIVATE).exists())

    def test_exact_committed_manifest_and_preserved_bytes_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scope, authorization, certificate = authorization_fixture(root)
            self.assertEqual(h.preflight(root)["authorization"], authorization)
            original = (root / "scripts/legacy.py").read_bytes()
            (root / "scripts/legacy.py").write_bytes(original + b"# changed\n")
            with self.assertRaisesRegex(ValueError, "Frozen file changed"):
                h.preflight(root)
            (root / "scripts/legacy.py").write_bytes(original)
            write(root, "scripts/unregistered.py", b"# new evaluator\n")
            h.git(root, "add", "scripts/unregistered.py")
            with self.assertRaisesRegex(ValueError, "inventory incomplete"):
                h.preflight(root)
            h.git(root, "reset", "--", "scripts/unregistered.py")
            changed = copy.deepcopy(authorization)
            changed["frozen_files_sha256"]["../escape.py"] = "a" * 64
            with self.assertRaises(ValueError):
                h.validate_documents(root, scope, changed, certificate, h.tracked(root))

    def test_source_choice_certificate_and_zero_decode_envelopes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scope, authorization, certificate = authorization_fixture(root)
            for key, value in (("status", "candidate-ready"), ("fresh_rows_decoded_before_authorization", False),
                               ("fresh_rows_decoded_before_authorization", 1),
                               ("additional_exclusions", ["same", "same"])):
                changed = copy.deepcopy(authorization)
                changed[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    h.validate_documents(root, scope, changed, certificate, h.tracked(root))
            for mutation in ("wrong_source", "retrieval", "missing_generator"):
                changed = copy.deepcopy(certificate)
                if mutation == "wrong_source":
                    changed["sources"]["candidate"]["runtime_sha256"] = "d" * 64
                elif mutation == "retrieval":
                    changed["retrieval_calls_executed"] = 1
                else:
                    changed["generator_files"] = {}
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    h.validate_documents(root, scope, authorization, changed, h.tracked(root))

    def test_schedule_and_cli_arguments_preserve_all_original_worker_boundaries(self):
        specs = h.schedule()
        self.assertEqual(len(specs), 29)
        self.assertEqual([item[1] for item in specs[:5]], ["prepare", "register", "bind", "select", "prepare-data"])
        self.assertEqual([item[2] for item in specs if item[1] == "native-worker"], list(range(5)))
        self.assertEqual([item[2] for item in specs if item[1] == "component-worker"], list(range(6)))
        self.assertEqual([item[1] for item in specs[-2:]], ["component-audit", "native-audit"])
        scope = h.read(h.ROOT / h.SCOPE)
        self.assertEqual(scope["schedule"]["native_calls"], 5 * 3072)
        self.assertEqual(scope["schedule"]["component_search_calls"], 5 * 1536)
        self.assertEqual(scope["schedule"]["component_quality_rows"], 15360)
        self.assertEqual(scope["schedule"]["component_workers"], list(h.WORKERS))
        root = Path("/artificial")
        for _, action, index in specs[1:]:
            argv = h.command(root, root / h.PRIVATE, root / h.PUBLIC, action, index, "a" * 40)
            self.assertEqual(argv[0], h.sys.executable)
            self.assertEqual(argv[1], str(root / (h.COMPONENT if action.startswith("component") or action == "register" else h.NATIVE)))
            if action not in {"register", "bind"}:
                self.assertEqual(argv[argv.index("--published-commit") + 1], "a" * 40)
            if action.endswith("-worker"):
                self.assertEqual(argv[argv.index("--worker") + 1], str(index))
                self.assertIn("--parquet", argv)
                if action == "native-worker" or index <= 2:
                    self.assertEqual(argv[argv.index("--source") + 1],
                        str(root / h.PRIVATE / "sources" / ("baseline" if index == 0 else "candidate") / "src"))
                else:
                    self.assertNotIn("--source", argv)

    def test_nonzero_stage_preserves_original_exit_and_blocks_every_following_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = h.Controller(Path(temp))
            controller.public.mkdir(parents=True)
            h.save(controller.state / "progress.json", {"next_stage": 0})
            publications = []
            controller.publisher.expected = lambda: "a" * 40
            controller.publisher.publish = lambda message: publications.append(message)
            controller.guard = lambda: h.require(not (controller.state / "stopped.json").exists(), "stopped")
            def fail(argv, path):
                path.write_bytes(b"original artificial process stderr\n")
                return 17
            with patch.object(h, "execute", side_effect=fail) as executed:
                with self.assertRaisesRegex(ValueError, "returned 17"):
                    controller.stage(0, ("register-components", "register", None))
                with self.assertRaises(ValueError):
                    controller.stage(0, ("register-components", "register", None))
                with self.assertRaises(ValueError):
                    controller.stage(1, ("bind-native", "bind", None))
                self.assertEqual(executed.call_count, 1)
            self.assertEqual(len(publications), 1)  # Start was published; no later success/start checkpoint.
            exit_record = h.read(controller.public / "register-components.exit.json")
            self.assertEqual(exit_record["returncode"], 17)
            self.assertEqual(exit_record["status"], "failed_or_interrupted")
            self.assertIn("Original stage returned", exit_record["error"]["traceback"])
            self.assertEqual((controller.public / "register-components.log").read_bytes(),
                             b"original artificial process stderr\n")

    def test_source_or_host_mutation_is_rejected_after_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = h.Controller(root)
            write(root, h.AUTH, {"fixture": True})
            write(root, "scripts/frozen.py", b"# original\n")
            controller.claim = {"frozen_files_sha256": {"scripts/frozen.py": h.sha(root / "scripts/frozen.py")},
                "authorization_sha256": h.sha(root / h.AUTH), "host": {"boot": "invented"},
                "sources": {}, "source_files_sha256": {}}
            with patch.object(h, "host_identity", return_value={"boot": "invented"}):
                controller.guard()
                write(root, "scripts/frozen.py", b"# changed after selection\n")
                with self.assertRaisesRegex(ValueError, "Frozen file changed"):
                    controller.guard()
                write(root, "scripts/frozen.py", b"# original\n")
            with patch.object(h, "host_identity", return_value={"boot": "other"}):
                with self.assertRaisesRegex(ValueError, "host/boot changed"):
                    controller.guard()

    def test_real_local_git_checkpoint_preserves_binary_gzip_and_excludes_raw_ledgers_tickets(self):
        with tempfile.TemporaryDirectory() as temp:
            publisher, remote = publisher_fixture(Path(temp))
            binary = gzip.compress(b'{"fixture":"invented"}\n\x00\xff', mtime=0)
            write(publisher.public, "worker.json.gz", binary)
            write(publisher.public, "worker.attempts.jsonl", b'{"event":"invented"}\n')
            write(publisher.state, "tickets/worker.ticket", b"private artificial ticket")
            head = publisher.publish("artificial binary checkpoint")
            self.assertEqual(publisher.remote(), head)
            self.assertEqual(h.git(remote, "show", head + ":" + h.PUBLIC + "/worker.json.gz"), binary)
            paths = h.git(remote, "ls-tree", "-r", "--name-only", head).decode().splitlines()
            self.assertFalse(any(path.endswith(".attempts.jsonl") or path.endswith(".ticket") for path in paths))
            write(publisher.public, "next.json", {"complete": True})
            next_head = publisher.publish("artificial next checkpoint")
            self.assertEqual(h.git(remote, "rev-parse", next_head + "^").decode().strip(), head)
            self.assertEqual(publisher.expected(), next_head)

    def test_changed_remote_or_unrelated_index_blocks_before_push(self):
        for conflict in ("remote", "index"):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as temp:
                publisher, remote = publisher_fixture(Path(temp))
                write(publisher.public, "claim.json", {"invented": True})
                head = publisher.publish("artificial claim")
                write(publisher.public, "next.json", {"invented": "next"})
                if conflict == "remote":
                    tree = h.git(remote, "rev-parse", head + "^{tree}").decode().strip()
                    other = h.git(remote, "commit-tree", tree, "-p", head, "-m", "other fixture writer").decode().strip()
                    h.git(remote, "update-ref", h.RESULT_REF, other)
                else:
                    write(publisher.root, "unrelated.txt", b"must not publish\n")
                    h.git(publisher.root, "add", "unrelated.txt")
                old_head = publisher.head()
                with self.assertRaises(h.PublicationError):
                    publisher.publish("must fail before commit")
                self.assertEqual(publisher.head(), old_head)
                self.assertTrue((publisher.public / "publication-failure.json").exists())
                with self.assertRaisesRegex(h.PublicationError, "no write/measurement retry"):
                    publisher.publish("never retry")

    def test_ambiguous_successful_push_is_never_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            publisher, _remote = publisher_fixture(Path(temp))
            write(publisher.public, "claim.json", {"invented": True})
            original_run, push_calls = subprocess.run, []
            def ambiguous(argv, *args, **kwargs):
                result = original_run(argv, *args, **kwargs)
                if argv[:2] == ["git", "push"]:
                    push_calls.append(argv)
                    self.assertNotIn("--force", argv)
                    self.assertNotIn("--force-with-lease", argv)
                    return subprocess.CompletedProcess(argv, 1, result.stdout, b"connection lost after actual local push")
                return result
            with patch.object(h.subprocess, "run", side_effect=ambiguous):
                with self.assertRaises(h.PublicationError):
                    publisher.publish("artificial ambiguous push")
                with self.assertRaises(h.PublicationError):
                    publisher.publish("never repeat")
            self.assertEqual(len(push_calls), 1)
            self.assertEqual(publisher.remote(), publisher.head())
            self.assertIsNone(publisher.expected())
            self.assertIn("connection lost", h.read(publisher.public / "publication-failure.json")["error"])

    def test_download_is_single_acquisition_with_partial_evidence_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invented.bin"
            with patch.object(h.urllib.request, "urlopen", return_value=io.BytesIO(b"invented wrong bytes")) as fetch:
                with self.assertRaisesRegex(ValueError, "verification failed"):
                    h.download_once("https://example.invalid/frozen", path, "a" * 64, 7)
                with self.assertRaisesRegex(ValueError, "never retry"):
                    h.download_once("https://example.invalid/frozen", path, "a" * 64, 7)
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(path.with_name(path.name + ".partial").read_bytes(), b"invented wrong bytes")
            self.assertFalse(path.exists())
            expected = hashlib.sha256(b"invented correct").hexdigest()
            other = Path(temp) / "other.bin"
            with patch.object(h.urllib.request, "urlopen", return_value=io.BytesIO(b"invented correct")):
                h.download_once("https://example.invalid/other", other, expected, len(b"invented correct"))
            self.assertEqual(other.read_bytes(), b"invented correct")
            self.assertEqual(h.node_checksum((expected + "  exact.tar.xz\n").encode(), "exact.tar.xz"), expected)
            with self.assertRaises(ValueError):
                h.node_checksum(((expected + "  exact.tar.xz\n") * 2).encode(), "exact.tar.xz")

    def test_asset_preparation_downloads_locked_invented_bytes_without_adapter_or_model_execution(self):
        def tar_bytes(files, mode):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode=mode) as archive:
                for name, data in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            return output.getvalue()
        def spec(url, name, content):
            return {"url": url, "name": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scope = h.read(h.ROOT / h.SCOPE)
            node = scope["assets"]["node"]
            node_archive = tar_bytes({node["binary_member"]: b"invented node binary"}, "w:xz")
            cm_source = tar_bytes({"repo/" + name: b"invented source" for name in
                ("src/services/sqlite/SessionSearch.ts", "src/services/sqlite/SessionStore.ts", "package.json", "LICENSE")}, "w:gz")
            bun_bytes = b"invented bun binary"
            zipped = io.BytesIO()
            with zipfile.ZipFile(zipped, "w") as archive:
                archive.writestr("bun-linux-x64/bun", bun_bytes)
            cm = {"source_archive": spec("https://example.invalid/source", "source.tar.gz", cm_source),
                  "runtime": {**spec("https://example.invalid/bun", "bun.zip", zipped.getvalue()),
                    "member": "bun-linux-x64/bun", "binary_sha256": hashlib.sha256(bun_bytes).hexdigest(),
                    "binary_bytes": len(bun_bytes)}}
            source = b"invented billion typescript"
            billion = {"repository": "fixture/only", "commit": "a" * 40,
                "files": [{"path": "kernel/source.ts", "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest(),
                    "git_blob_sha": hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()}]}
            binary = b"invented ai binary"
            ai_archive = tar_bytes({"ai-memory": binary, "LICENSE": b"invented license"}, "w:gz")
            ai = {"version": "v-fixture", "asset_url": "https://example.invalid/ai",
                "archive_bytes": len(ai_archive), "archive_sha256": hashlib.sha256(ai_archive).hexdigest(),
                "binary_sha256": hashlib.sha256(binary).hexdigest(),
                "embedding_model": {"name": "invented-model", "base_url": "https://example.invalid/model",
                    "files": [{"name": name, "sha256": hashlib.sha256(name.encode()).hexdigest(), "bytes": len(name)}
                              for name in ("model.safetensors", "tokenizer.json", "config.json")]}}
            upstream = {"source_url": "https://example.invalid/not-parquet", "upstream_bytes": len(b"not a parquet: invented"),
                        "upstream_sha256": hashlib.sha256(b"not a parquet: invented").hexdigest()}
            for name, value in (("claude-mem-round2-lock.json", cm), ("billion-round2-lock.json", billion),
                                ("ai-memory-lock.json", ai)):
                write(root, "benchmarks/competitors/" + name, value)
            write(root, "benchmarks/hotpot_manifest.json", upstream)
            assets = {node["checksums_url"]: (hashlib.sha256(node_archive).hexdigest() + "  " + node["archive_name"] + "\n").encode(),
                node["archive_url"]: node_archive, cm["source_archive"]["url"]: cm_source,
                cm["runtime"]["url"]: zipped.getvalue(), ai["asset_url"]: ai_archive,
                upstream["source_url"]: b"not a parquet: invented",
                "https://raw.githubusercontent.com/fixture/only/" + "a" * 40 + "/kernel/source.ts": source}
            assets.update({ai["embedding_model"]["base_url"] + "/" + entry["name"]: entry["name"].encode()
                           for entry in ai["embedding_model"]["files"]})
            acquisitions = []
            def download(url, path, expected=None, size=None):
                acquisitions.append(url)
                return h.write_asset(path, assets[url], expected, size)
            with patch.object(h, "download_once", side_effect=download), \
                 patch.object(h.subprocess, "check_output", return_value="v24.22.1\n") as launch, \
                 patch("benchmarks.competitors.billion.prepare", side_effect=AssertionError("compiler ran")), \
                 patch("benchmarks.competitors.claude_mem.prepare", side_effect=AssertionError("adapter ran")), \
                 patch("benchmarks.competitors.ai_memory.prepare_models", side_effect=AssertionError("model ran")):
                result = h.prepare_assets(root, root / h.PRIVATE, scope)
            self.assertEqual(len(acquisitions), len(set(acquisitions)))
            self.assertEqual(set(acquisitions), set(assets))
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.args[0][1:], ["--version"])
            self.assertEqual(result["fresh_rows_decoded"], 0)
            self.assertEqual(result["engines_initialized"], 0)
            h.verify_manifest(root, result["files_sha256"])

    def test_partial_or_corrupt_ledger_archive_is_preserved_without_replacement(self):
        corruptions = [b"original interrupted corrupt archive",
                       b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8]
        for corruption in corruptions:
            with self.subTest(corruption=corruption.hex()), tempfile.TemporaryDirectory() as temp:
                public = Path(temp)
                ledger = write(public, "worker.attempts.jsonl", b'{"started":0}\npartial')
                archive = write(public, "worker.attempts.jsonl.gz", corruption)
                h.preserve_ledgers(public)
                self.assertEqual(archive.read_bytes(), corruption)
                saved = public / "worker.attempts.jsonl.interrupted.gz"
                self.assertEqual(gzip.decompress(saved.read_bytes()), ledger.read_bytes())
                first = saved.read_bytes()
                h.preserve_ledgers(public)
                self.assertEqual(saved.read_bytes(), first)

    def test_exact_sparse_worktrees_use_artificial_commits_and_reject_added_source_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = initialize(Path(temp) / "driver")
            write(root, "src/memory_book/__init__.py", b"VERSION = 'invented'\n")
            write(root, "src/memory_book/store.py", b"# invented source, no data or engine\n")
            write(root, "README.md", b"Should not enter sparse source checkout\n")
            first = commit(root)
            manifest = h.source_manifest(root)
            digest = hashlib.sha256()
            for path in sorted((root / "src/memory_book").rglob("*.py")):
                digest.update(path.relative_to(root / "src/memory_book").as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
            identity = {"commit": first, "runtime_sha256": digest.hexdigest()}
            write(root, "benchmarks/experiments/artificial-native-scope.json", {"original_plan": {"commit": first}})
            frozen = {"scope": {"protocols": {"native_scope": "benchmarks/experiments/artificial-native-scope.json"}},
                "certificate": {"generator_commit": first},
                "authorization": {"sources": {"baseline": identity, "candidate": identity},
                                  "source_files_sha256": {"baseline": manifest, "candidate": manifest}}}
            state = root / h.PRIVATE
            h.prepare_sources(root, state, frozen)
            for label in ("baseline", "candidate"):
                directory = state / "sources" / label
                h.verify_source(directory, identity, manifest)
                self.assertFalse((directory / "README.md").exists())
            directory = state / "sources/candidate"
            write(directory, "src/memory_book/unexpected.pyc", b"invented pyc")
            with self.assertRaisesRegex(ValueError, "inventory or bytes changed"):
                h.verify_source(directory, identity, manifest)


if __name__ == "__main__":
    unittest.main()
