"""Artificial orchestration checks; no corpus, downloads or retrieval execute."""
from contextlib import contextmanager, ExitStack
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round5_lexical_compat_hosted as hosted


def selection():
    evidence = [{"commit": "1" * 40, "path": "benchmarks/reports/invented/review.json",
                 "sha256": "2" * 64}]
    return {"schema_version": 1, "status": "selected-after-development-before-final-evaluation",
        "baseline": dict(hosted.BASELINE),
        "candidate": {"commit": "3" * 40, "runtime_sha256": "4" * 64},
        "candidate_files_sha256": {"src/memory_book/store.py": "5" * 64},
        "development_evidence": evidence, "independent_source_review": copy.deepcopy(evidence),
        "fresh_metadata_selected": False, "fresh_content_decoded": False,
        "formal_measurement_started": False}


@contextmanager
def workspace(*, stage=True):
    old_root = hosted.ROOT
    names = ("PUBLIC", "STATE", "SELECTION", "SCOPE", "BINDING", "PARQUET",
             "PREPARATION", "DATABASE", "INTENT")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = {name: root / getattr(hosted, name).relative_to(old_root) for name in names}
        with ExitStack() as stack:
            stack.enter_context(patch.object(hosted, "ROOT", root))
            for name, value in paths.items():
                stack.enter_context(patch.object(hosted, name, value))
            if stage:
                hosted.STATE.mkdir(parents=True)
                hosted.PUBLIC.mkdir(parents=True)
                hosted.journal({"expected_remote": None})
            yield root


class LexicalHostedTests(unittest.TestCase):
    def test_selection_and_immutable_evidence_are_required(self):
        value = selection()
        self.assertIs(hosted.validate_selection(value), value)
        for key in ("candidate", "candidate_files_sha256", "development_evidence",
                    "independent_source_review", "status"):
            with self.subTest(key=key):
                changed = copy.deepcopy(value)
                del changed[key]
                with self.assertRaises(ValueError):
                    hosted.validate_selection(changed)
        for key in ("fresh_metadata_selected", "fresh_content_decoded", "formal_measurement_started"):
            for invalid in (True, 0, None, "false"):
                with self.subTest(key=key, invalid=invalid):
                    changed = copy.deepcopy(value)
                    changed[key] = invalid
                    with self.assertRaises(ValueError):
                        hosted.validate_selection(changed)

    def test_source_identity_paths_and_hashes_fail_closed(self):
        for mutation in ("baseline", "schema-bool", "source-path", "source-hash", "evidence"):
            with self.subTest(mutation=mutation):
                value = selection()
                if mutation == "baseline":
                    value["baseline"]["commit"] = "0" * 40
                elif mutation == "schema-bool":
                    value["schema_version"] = True
                elif mutation == "source-path":
                    value["candidate_files_sha256"] = {"src/memory_book/../other": "5" * 64}
                elif mutation == "source-hash":
                    value["candidate_files_sha256"] = {"src/memory_book/store.py": None}
                else:
                    value["development_evidence"][0]["path"] = "benchmarks/reports/../private"
                with self.assertRaises(ValueError):
                    hosted.validate_selection(value)

    def test_missing_selection_precedes_claim_download_and_source(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": hosted.TRIGGER}):
            with patch.object(hosted, "read", side_effect=FileNotFoundError("selection")):
                with patch.object(hosted, "remote_head") as remote, patch.object(hosted, "publish") as publish:
                    with patch.object(hosted, "download") as download, patch.object(hosted, "prepare_source") as source:
                        with self.assertRaises(FileNotFoundError):
                            hosted.run()
        for method in (remote, publish, download, source):
            method.assert_not_called()

    def test_scope_retains_original_schedule_counts_and_helper_bytes(self):
        scope = hosted.read(hosted.SCOPE)
        self.assertEqual(scope["schedule"], hosted.original.schedule())
        self.assertEqual(len(scope["schedule"]), 10)
        self.assertEqual(sum(256 * len(hosted.original.configurations(item["kind"]))
                             for item in scope["schedule"]), 5120)
        self.assertEqual(scope["calls"]["complete_payload_pairs"], 2560)
        self.assertEqual(scope["calls"]["tokens"], 3072)
        self.assertEqual(scope["calls"]["character"], 2048)
        for name, checksum in scope["untouched_files_sha256"].items():
            with self.subTest(path=name):
                self.assertEqual(hosted.sha(hosted.ROOT / name), checksum)
        self.assertEqual(scope["environment"]["packages"]["mcp"], "1.30.0")
        self.assertEqual(scope["environment"]["packages"]["pydantic"], "2.14.3")

    def test_remote_claim_and_publication_allowlist_are_narrow(self):
        head = "a" * 40
        self.assertIsNone(hosted.parse_remote(""))
        self.assertEqual(hosted.parse_remote(head + "\trefs/heads/" + hosted.BRANCH), head)
        for raw in (head, head + " refs/heads/other",
                    head + " refs/heads/" + hosted.BRANCH + " extra"):
            with self.subTest(raw=raw), self.assertRaises(hosted.PublicationError):
                hosted.parse_remote(raw)
        self.assertTrue(hosted.allowed(hosted.relative(hosted.PUBLIC) + "/worker.json.gz"))
        self.assertTrue(hosted.allowed(hosted.relative(hosted.BINDING)))
        for path in ("src/memory_book/store.py", ".artifacts/input.parquet",
                     "benchmarks/reports/another/record.json"):
            self.assertFalse(hosted.allowed(path))

    def test_conflicting_result_ref_never_attempts_a_push(self):
        with workspace():
            with patch.object(hosted, "remote_head", return_value="a" * 40):
                with patch.object(hosted, "text_git", return_value="b" * 40):
                    with patch.object(hosted.subprocess, "run") as run:
                        with self.assertRaises(hosted.PublicationError):
                            hosted.publish("invented")
                        with self.assertRaises(hosted.PublicationError):
                            hosted.publish("invented again")
            run.assert_not_called()
            marker = hosted.read(hosted.PUBLIC / "publication-failure.json")
            self.assertIsNone(marker["expected_previous"])

    def test_ambiguous_push_stops_without_advancing_journal_or_retry(self):
        with workspace():
            heads = iter(("b" * 40, "c" * 40))
            differences = iter(("", hosted.relative(hosted.PUBLIC) + "/invented.json"))
            def git(*args):
                if args == ("rev-parse", "HEAD"):
                    return next(heads)
                if args == ("diff", "--cached", "--name-only"):
                    return next(differences)
                self.fail("Unexpected Git operation")
            with patch.object(hosted, "text_git", side_effect=git):
                with patch.object(hosted, "remote_head", side_effect=[None, "d" * 40]):
                    with patch.object(hosted.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                        with self.assertRaises(hosted.PublicationError):
                            hosted.publish("invented ambiguous publication")
                        calls = run.call_count
                        with self.assertRaises(hosted.PublicationError):
                            hosted.publish("not a retry")
                        self.assertEqual(run.call_count, calls)
            self.assertIsNone(hosted.read(hosted.STATE / "publication.json")["expected_remote"])
            marker = hosted.read(hosted.PUBLIC / "publication-failure.json")
            self.assertEqual(marker["local_commit"], "c" * 40)
            self.assertEqual(marker["observed_remote"], "d" * 40)
            self.assertEqual(sum(call.args[0][:2] == ["git", "push"] for call in run.call_args_list), 1)

    def test_stage_publishes_before_launch_and_after_lossless_output(self):
        with workspace():
            output = hosted.PUBLIC / "tokens-r0-baseline.json.gz"
            ledger_raw = '{"state":"invented","note":"证据"}\n{"partial":'.encode()
            result_raw = b'{"status":"invented"}\n'
            events = []
            def publish(message):
                events.append(("publish", message))
                if len(events) > 1:
                    self.assertTrue((hosted.PUBLIC / "fixture.exit.json").is_file())
                    self.assertFalse(output.with_name(output.name + ".attempts.jsonl").exists())
                    self.assertEqual(gzip.decompress(output.with_name(
                        output.name + ".attempts.jsonl.gz").read_bytes()), ledger_raw)
                return "a" * 40
            def run(*args, **kwargs):
                self.assertEqual(len(events), 1)
                self.assertTrue((hosted.PUBLIC / "fixture.remote-intent.json").is_file())
                self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
                self.assertEqual(kwargs["env"]["PYTHONHASHSEED"], "0")
                output.write_bytes(gzip.compress(result_raw, mtime=0))
                output.with_name(output.name + ".attempts.jsonl").write_bytes(ledger_raw)
                events.append(("child", args))
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "0"}):
                with patch.object(hosted, "publish", side_effect=publish):
                    with patch.object(hosted.subprocess, "run", side_effect=run) as child:
                        hosted.run_stage("fixture", ["invented-command"], 12, (output,), worker_output=output)
            self.assertEqual([event[0] for event in events], ["publish", "child", "publish"])
            child.assert_called_once()
            receipt = hosted.read(hosted.PUBLIC / "fixture.exit.json")
            storage = receipt["worker_storage"]["files"]
            self.assertEqual(storage[output.name]["uncompressed_sha256"], hosted.digest(result_raw))
            self.assertEqual(storage[output.name + ".attempts.jsonl.gz"]["uncompressed_sha256"],
                             hosted.digest(ledger_raw))
            self.assertEqual(hosted.helper("worker", "--kind", "char")[:4],
                             [hosted.sys.executable, "-B", "scripts/round5_compatibility.py", "worker"])

    def test_failed_or_timed_out_worker_retains_partial_ledger_and_never_replays(self):
        for mode in ("failed", "timeout"):
            with self.subTest(mode=mode), workspace():
                output = hosted.PUBLIC / "char-r0-baseline.json.gz"
                raw = b'{"state":"started","query_id":"invented"}\n{"state":'
                def launch(*args, **kwargs):
                    output.write_bytes(gzip.compress(b'{"status":"running"}\n', mtime=0))
                    output.with_name(output.name + ".attempts.jsonl").write_bytes(raw)
                    if mode == "timeout":
                        raise subprocess.TimeoutExpired(["invented"], 1)
                    return SimpleNamespace(returncode=1)
                with patch.object(hosted, "publish") as publish:
                    with patch.object(hosted.subprocess, "run", side_effect=launch) as child:
                        with self.assertRaises(RuntimeError):
                            hosted.run_stage("fixture", ["invented"], 1, (output,), worker_output=output)
                        with self.assertRaises(FileExistsError):
                            hosted.run_stage("fixture", ["invented"], 1, (output,), worker_output=output)
                child.assert_called_once()
                self.assertEqual(publish.call_count, 2)
                self.assertEqual(gzip.decompress(output.with_name(
                    output.name + ".attempts.jsonl.gz").read_bytes()), raw)
                self.assertFalse(hosted.read(hosted.PUBLIC / "fixture.exit.json")["replay_permitted"])

    def test_archived_original_bytes_are_read_back_without_recompression(self):
        with workspace():
            output = hosted.PUBLIC / "char-r0-baseline.json.gz"
            raw = b'{"invented":true}\n'
            packed = gzip.compress(raw, mtime=19)
            output.write_bytes(packed)
            output.with_name(output.name + ".attempts.jsonl").write_bytes(raw + b"incomplete")
            first = hosted.preserve_worker_bytes(output)
            second = hosted.preserve_worker_bytes(output)
            self.assertEqual(first, second)
            self.assertEqual(output.read_bytes(), packed)

    def test_source_guard_rejects_bytecode_and_changed_or_missing_files(self):
        with workspace() as root:
            source = root / "invented-source"
            file = source / "src/memory_book/store.py"
            file.parent.mkdir(parents=True)
            file.write_text("# invented\n", encoding="utf-8")
            exact = hosted.inventory(source)
            identity = {"commit": "a" * 40, "runtime_sha256": "b" * 64}
            sources = {"candidate": {"source": str(source / "src"),
                "files_sha256": exact, "identity": identity}}
            frozen = {"controller_files_sha256": {}, "registry_sha256": {}, "environment": {}}
            for mutation in ("bytecode", "changed", "missing"):
                with self.subTest(mutation=mutation):
                    file.write_text("# invented\n", encoding="utf-8")
                    extra = file.parent / "__pycache__/store.cpython-312.pyc"
                    if extra.exists():
                        extra.unlink()
                    if mutation == "bytecode":
                        extra.parent.mkdir(exist_ok=True)
                        extra.write_bytes(b"unexpected bytecode")
                    elif mutation == "changed":
                        file.write_text("# changed\n", encoding="utf-8")
                    else:
                        file.unlink()
                    with self.assertRaisesRegex(ValueError, "Unknown or changed runtime files"):
                        hosted.guards(frozen, {}, sources)

    def test_completed_worker_uses_original_full_ledger_validator(self):
        from tests.test_round5_compatibility import fixture
        bound, report, ledger = fixture()
        with workspace():
            hosted.BINDING.parent.mkdir(parents=True, exist_ok=True)
            hosted.BINDING.write_text("{}\n", encoding="utf-8")
            hosted.save(hosted.INTENT, {"host": {"invented": True}})
            output = hosted.PUBLIC / hosted.original.filename({"kind": "char", "round": 0, "label": "baseline"})
            raw = b"".join(hosted.original.raw(row) for row in ledger)
            report.update(ledger_sha256=hosted.digest(raw), binding_sha256=hosted.sha(hosted.BINDING),
                intent_sha256=hosted.sha(hosted.INTENT), host={"invented": True})
            output.write_bytes(gzip.compress(hosted.original.raw(report), mtime=0))
            ledger_path = output.with_name(output.name + ".attempts.jsonl.gz")
            ledger_path.write_bytes(gzip.compress(raw, mtime=0))
            item = {"kind": "char", "round": 0, "label": "baseline"}
            hosted.verify_completed_worker(item, bound)
            changed = list(ledger)
            changed[0], changed[1] = changed[1], changed[0]
            raw = b"".join(hosted.original.raw(row) for row in changed)
            report["ledger_sha256"] = hosted.digest(raw)
            output.write_bytes(gzip.compress(hosted.original.raw(report), mtime=0))
            ledger_path.write_bytes(gzip.compress(raw, mtime=0))
            with self.assertRaisesRegex(ValueError, "Ledger order/payload differs"):
                hosted.verify_completed_worker(item, bound)

    def exercise_controller(self, failing_worker=None):
        scope = hosted.read(hosted.SCOPE)
        scope["untouched_files_sha256"] = {}
        value = selection()
        events = []
        with workspace(stage=False) as root:
            for name in hosted.FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# invented fixture\n", encoding="utf-8")
            hosted.SCOPE.write_text(json.dumps(scope), encoding="utf-8")
            hosted.SELECTION.parent.mkdir(parents=True, exist_ok=True)
            hosted.SELECTION.write_text(json.dumps(value), encoding="utf-8")
            def source(label, identity, expected_files=None):
                return {"source": str(root / "sources" / label / "src"),
                    "files_sha256": expected_files or {}, "identity": identity}
            def stage(name, command, timeout, outputs=(), worker_output=None):
                events.append((name, command))
                if name == failing_worker:
                    raise RuntimeError("invented worker failed")
                for path in outputs:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if name == "audit":
                        path.write_text(json.dumps({"status": "verified", "accepted": True,
                            "calls": 5120, "complete_payload_pairs": 2560, "workers": 10}), encoding="utf-8")
                    else:
                        path.write_text("{}", encoding="utf-8")
            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_REF": hosted.TRIGGER, "GITHUB_SHA": "f" * 40,
                    "GITHUB_RUN_ID": "invented", "PYTHONDONTWRITEBYTECODE": "1"}))
                stack.enter_context(patch.object(hosted.sys, "dont_write_bytecode", True))
                stack.enter_context(patch.object(hosted, "committed"))
                stack.enter_context(patch.object(hosted, "remote_head", return_value=None))
                stack.enter_context(patch.object(hosted, "text_git", return_value="f" * 40))
                stack.enter_context(patch.object(hosted.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
                stack.enter_context(patch.object(hosted, "publish", return_value="a" * 40))
                stack.enter_context(patch.object(hosted, "verify_registration", return_value={}))
                stack.enter_context(patch.object(hosted, "prepare_source", side_effect=source))
                stack.enter_context(patch.object(hosted, "environment", return_value={}))
                stack.enter_context(patch.object(hosted, "guards", return_value={}))
                stack.enter_context(patch.object(hosted, "verify_completed_worker"))
                stack.enter_context(patch.object(hosted, "run_stage", side_effect=stage))
                download = stack.enter_context(patch.object(hosted, "download"))
                if failing_worker is None:
                    hosted.run()
                    self.assertTrue((hosted.PUBLIC / "completion.json").exists())
                else:
                    with self.assertRaisesRegex(RuntimeError, "invented worker failed"):
                        hosted.run()
                    self.assertTrue((hosted.PUBLIC / "failure.json").exists())
                    self.assertFalse((hosted.PUBLIC / "completion.json").exists())
                download.assert_called_once()
        return events

    def test_controller_keeps_original_ten_worker_order_and_single_preparation(self):
        events = self.exercise_controller()
        self.assertEqual([command[3] for _, command in events],
            ["bind", "prepare", "intent"] + ["worker"] * 10 + ["audit"])
        actual = []
        for _, command in events:
            if command[3] == "worker":
                actual.append({key: int(command[command.index("--" + key) + 1]) if key == "round"
                    else command[command.index("--" + key) + 1] for key in ("kind", "round", "label")})
        self.assertEqual(actual, hosted.original.schedule())

    def test_controller_stops_at_failed_worker_without_retry_or_audit(self):
        failure = "char-r1-candidate"
        events = self.exercise_controller(failure)
        self.assertEqual(events[-1][0], failure)
        self.assertNotIn("audit", [name for name, _ in events])
        self.assertEqual(sum(name == failure for name, _ in events), 1)


if __name__ == "__main__":
    unittest.main()
