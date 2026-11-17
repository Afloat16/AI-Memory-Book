"""Frozen component audits and create-only evidence, without performance runs."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_semantic_runtime as semantic
from scripts import comprehensive_runtime_preserve as preserve


IDENTITY = {"id": "123", "attempt": 1, "commit": "a" * 40,
            "url": "https://github.com/Afloat16/AI-Memory-Book/actions/runs/123"}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(preserve.encoded(value))


def paired(count, allocations=False):
    rows = []
    for pair, order in semantic.ordered_pairs(count):
        for position, arm in enumerate(order):
            row = {"pair": pair, "position": position, "arm": arm, "output_sha256": "f" * 64,
                   "exact_equal": True, "model_fingerprint": "e" * 64}
            value = 100 if arm == "baseline" else 50
            row.update({"peak_python_bytes": value, "retained_python_bytes": value // 2} if allocations
                       else {"elapsed_ns": value, "process_cpu_ns": value // 2})
            rows.append(row)
    field = "peak_python_bytes" if allocations else "elapsed_ns"
    result = {"observations": rows, **semantic.summary(rows, field)}
    if not allocations:
        result["process_cpu"] = semantic.summary(rows, "process_cpu_ns")
    return result


def fixture(work):
    manifest = {"protocol": preserve.PROTOCOL, "source_run": IDENTITY, "baseline_commit": preserve.BASELINE,
                "status": "frozen", "files": {}}
    for arm in ("baseline", "candidate"):
        paths = ["src/memory_book/semantic.py", "src/memory_book/store.py"]
        if arm == "candidate":
            paths.extend(preserve.EVALUATOR_PATHS)
        for path in paths:
            raw = (arm + ":" + path).encode()
            name = "frozen/" + arm + "/" + path
            preserve.write_new(work / name, raw)
            manifest["files"][name] = {**preserve.inventory(raw), "source": path,
                                      "commit": IDENTITY["commit"] if arm == "candidate" else preserve.BASELINE}
    save(work / "source-manifest.json", manifest)
    def sources(path):
        return {"baseline": {"commit": preserve.BASELINE, "source_sha256": preserve.source_hash(manifest, "baseline", path)},
                "candidate": {"head": IDENTITY["commit"], "source_status": "",
                              "source_sha256": preserve.source_hash(manifest, "candidate", path)}}
    report = {"protocol": "semantic-runtime-development-v3", "baseline_ref": preserve.BASELINE,
        "sources": sources("src/memory_book/semantic.py"),
        "script_sha256": preserve.source_hash(manifest, "candidate", "scripts/benchmark_semantic_runtime.py"),
        "plan_sha256": preserve.source_hash(manifest, "candidate", "benchmarks/semantic-runtime-plan.json"),
        "environment": {"numpy": preserve.NUMPY, "python": "3.12.12"},
        "arguments": {"windows": [4096, 32768], "pairs": 4, "memory_pairs": 2, "artifact_pairs": 4,
                      "warmups": 2, "model_bytes": 118453870, "tokenizer_bytes": 9081518}, "ranking": []}
    semantic_events = [{"event": "started", "run": copy.deepcopy({key: value for key, value in report.items() if key != "ranking"})}]
    for windows in (4096, 32768):
        case = {"fixture": {"windows": windows}, "validation": {"exact_equal": True, "cursor_closed": True,
                "batch_rows": [4096] * (windows // 4096) + [0], "maximum_vector_batch_rows": 4096,
                "output_sha256": "f" * 64}, "latency": paired(4), "allocations": paired(2, allocations=True)}
        report["ranking"].append(case)
        semantic_events.append({"event": "ranking-validated", "fixture": case["fixture"], "output_sha256": "f" * 64,
                                "batch_rows": case["validation"]["batch_rows"], "cursor_closed": True})
        for section, event in (("latency", "ranking-latency"), ("allocations", "ranking-allocations")):
            for row in case[section]["observations"]:
                semantic_events.append({"event": event + "-started", "windows": windows,
                                        **{key: row[key] for key in ("pair", "position", "arm")}})
                semantic_events.append({"event": event, "windows": windows, "observation": row})
    total = 118453870 + 9081518
    report["artifact_initialization"] = {"fixture": {"total_artifact_bytes": total},
        "validation": {arm: {"identity_equal": True, "fingerprint_equal": True, "bytes_equal": True,
                            "read_bytes": total * multiplier, "artifact_hash_bytes": total * multiplier}
                       for arm, multiplier in (("baseline", 2), ("candidate", 1))}, "latency": paired(4)}
    for arm in ("baseline", "candidate"):
        semantic_events.append({"event": "artifacts-validated", "arm": arm,
                                "validation": report["artifact_initialization"]["validation"][arm]})
    for row in report["artifact_initialization"]["latency"]["observations"]:
        semantic_events.append({"event": "artifact-latency-started", **{key: row[key] for key in ("pair", "position", "arm")}})
        semantic_events.append({"event": "artifact-latency", "observation": row})
    semantic_path = work / "reports/semantic-runtime.json"
    save(semantic_path, report)
    semantic_events.append({"event": "completed", "report_sha256": preserve.sha(semantic_path.read_bytes())})
    (work / "reports/semantic-runtime.events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in semantic_events))
    directory = {"protocol": "directory-runtime-v1", "status": "completed", "protocol_parameters_match": True,
        "native_backend_loaded": False, "sources": sources("src/memory_book/store.py"),
        "arguments": {"rounds": 4, "iterations": 20, "baseline_commit": preserve.BASELINE, "validate_only": False},
        "environment": {"github_run_id": "123", "github_run_attempt": "1"}, "configurations": []}
    directory["sources"].update(harness_sha256=preserve.source_hash(manifest, "candidate", "scripts/benchmark_directory_runtime.py"),
        protocol_sha256=preserve.source_hash(manifest, "candidate", "benchmarks/directory-runtime-plan.json"))
    directory_events = [{"event": "started", "arguments": directory["arguments"]}]
    for sections in (1, 20, 100):
        for pages in (1, 20, 100):
            config = {"id": f"sections-{sections}-pages-{pages}", "sections": sections, "page_limit": pages,
                "exact_equality": True, "audit": {arm: {"output_sha256": "b" * 64,
                    "content_length_evaluations": sections * pages, "materialized_previews": sections * pages,
                    "select_count": 3 + 3 * sections if arm == "baseline" else 5,
                    "statement_count": 3 + 3 * sections if arm == "baseline" else 5,
                    "statements": ["SELECT 1"] * (3 + 3 * sections if arm == "baseline" else 5)}
                    for arm in ("baseline", "candidate")}, "rounds": [], "summary": {}}
            directory_events.append({"event": "audit", "configuration": config["id"], "audit": config["audit"]})
            for number in range(4):
                order = ["baseline", "candidate"] if number % 2 == 0 else ["candidate", "baseline"]
                trial = {"round": number, "order": order, "arms": {}}
                for position, arm in enumerate(order):
                    value = 100 if arm == "baseline" else 50
                    trial["arms"][arm] = [{"call": call, "wall_ns": value, "process_cpu_ns": value // 2,
                        "output_sha256": "b" * 64, "exact_equality": True} for call in range(20)]
                    directory_events.extend({"event": "call", "configuration": config["id"], "round": number,
                        "order_position": position, "arm": arm, **row} for row in trial["arms"][arm])
                config["rounds"].append(trial)
                directory_events.append({"event": "round_completed", "configuration": config["id"], "round": number})
            for metric, divisor in (("wall_ns", 1), ("process_cpu_ns", 2)):
                config["summary"][metric] = {"median_per_call": {"baseline": 100 / divisor, "candidate": 50 / divisor},
                    "paired_candidate_over_baseline": [0.5] * 4, "median_paired_ratio": 0.5}
            directory["configurations"].append(config)
    directory_events.append({"event": "completed", "configurations": 9})
    save(work / "reports/directory-runtime.json", directory)
    (work / "reports/directory-runtime.events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in directory_events))
    return manifest, report, directory


class ComprehensiveAuditTests(unittest.TestCase):
    def test_complete_frozen_balanced_reports_audit_without_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            fixture(work)
            result = preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))
            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["remeasured_calls"], 0)
            self.assertEqual(result["components"]["directory"]["timed_calls"], 1440)

    def test_missing_reordered_changed_or_failed_evidence_never_passes(self):
        mutations = {
            "missing semantic pair": lambda s, d: s["ranking"][0]["latency"]["observations"].pop(),
            "unbalanced semantic order": lambda s, d: s["ranking"][0]["latency"]["observations"][0].update(position=1),
            "different semantic output": lambda s, d: s["ranking"][0]["validation"].update(exact_equal=False),
            "unbounded vectors": lambda s, d: s["ranking"][1]["validation"].update(batch_rows=[32768], maximum_vector_batch_rows=32768),
            "double artifact IO": lambda s, d: s["artifact_initialization"]["validation"]["candidate"].update(read_bytes=255070776),
            "different candidate": lambda s, d: s["sources"]["candidate"].update(head="b" * 40),
            "changed summary": lambda s, d: s["ranking"][0]["latency"].update(median_candidate_over_baseline=0.01),
            "missing directory call": lambda s, d: d["configurations"][0]["rounds"][0]["arms"]["baseline"].pop(),
            "different directory output": lambda s, d: d["configurations"][0]["rounds"][0]["arms"]["candidate"][0].update(exact_equality=False),
            "extra materialization": lambda s, d: d["configurations"][0]["audit"]["candidate"].update(content_length_evaluations=130),
            "directory native backend": lambda s, d: d.update(native_backend_loaded=True),
            "directory wrong attempt": lambda s, d: d["environment"].update(github_run_attempt="2"),
            "directory bool timing": lambda s, d: d["configurations"][0]["rounds"][0]["arms"]["candidate"][0].update(wall_ns=True),
            "directory query regression": lambda s, d: d["configurations"][0]["audit"]["candidate"].update(select_count=6),
        }
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            _, semantic_report, directory_report = fixture(work)
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    semantic_copy, directory_copy = copy.deepcopy(semantic_report), copy.deepcopy(directory_report)
                    mutate(semantic_copy, directory_copy)
                    save(work / "reports/semantic-runtime.json", semantic_copy)
                    save(work / "reports/directory-runtime.json", directory_copy)
                    events = (work / "reports/semantic-runtime.events.jsonl").read_text().splitlines()
                    events[-1] = json.dumps({"event": "completed", "report_sha256": preserve.sha((work / "reports/semantic-runtime.json").read_bytes())})
                    (work / "reports/semantic-runtime.events.jsonl").write_text("\n".join(events) + "\n")
                    result = preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))
                    self.assertEqual(result["state"], "incomplete")

    def test_source_drift_partial_ledger_and_failed_preflight_are_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            fixture(work)
            outcomes = dict.fromkeys(preserve.STEPS, "success")
            outcomes["semantic_validate"] = "failure"
            self.assertEqual(preserve.audit_snapshot(work, IDENTITY, outcomes)["state"], "incomplete")
            ledger = work / "reports/directory-runtime.events.jsonl"
            ledger.write_bytes(ledger.read_bytes() + b'{"event":"partial')
            self.assertEqual(preserve.audit_snapshot(work, IDENTITY, dict.fromkeys(preserve.STEPS, "success"))["state"], "incomplete")
            (work / "frozen/candidate/src/memory_book/semantic.py").write_bytes(b"changed")
            result = preserve.audit_snapshot(work, IDENTITY, outcomes)
            self.assertEqual(result["errors"][0]["stage"], "frozen-source")

    def test_missing_ledger_audits_round_markers_or_extra_starts_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            manifest, _, _ = fixture(work)
            for component, auditor in (("semantic", preserve.audit_semantic), ("directory", preserve.audit_directory)):
                path = work / "reports" / (component + "-runtime.events.jsonl")
                original = path.read_text().splitlines()
                for alteration in ("missing validation", "duplicate start"):
                    with self.subTest(component=component, alteration=alteration):
                        changed = original[:1] + original if alteration == "duplicate start" else [line for line in original
                            if json.loads(line)["event"] not in ("audit", "round_completed", "ranking-validated")]
                        path.write_text("\n".join(changed) + "\n")
                        with self.assertRaisesRegex(ValueError, "ledger"):
                            auditor(work, manifest, IDENTITY)

    def test_partial_files_are_preserved_verbatim_before_failing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = b'{"status":"started","observation":\xff'
            source = root / preserve.WORK_PATH / "reports/partial.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(raw)
            with patch.object(preserve, "ROOT", root), patch.object(preserve, "hosted_identity", return_value=IDENTITY), \
                 patch.object(preserve, "clean_source"), patch.object(preserve, "publish", return_value={"commit": "b" * 40}) as publish:
                with self.assertRaisesRegex(ValueError, "Evidence was preserved"):
                    preserve.preserve()
            publish.assert_called_once()
            destination = root / preserve.PRESERVATION_PATH / "evidence"
            self.assertEqual((destination / "raw/reports/partial.json").read_bytes(), raw)
            self.assertEqual(preserve.read(destination / "evidence-manifest.json")["original_files"]["raw/reports/partial.json"],
                             preserve.inventory(raw))
            self.assertEqual(preserve.read(root / preserve.PRESERVATION_PATH / "preservation-result.json")["stage"], "completed")

    def test_non_regular_files_cannot_enter_the_evidence_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "work").mkdir()
            (root / "outside").write_text("not evidence")
            (root / "work/link").symlink_to(root / "outside")
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                preserve.collect(root / "work", root / "copy")


class ComprehensiveIdentityTests(unittest.TestCase):
    def test_hosted_guard_rejects_wrong_ref_repository_event_or_attempt(self):
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": preserve.REPOSITORY,
                       "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/" + preserve.BRANCH,
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "123", "GITHUB_SHA": IDENTITY["commit"],
                       "GITHUB_WORKFLOW_SHA": IDENTITY["commit"],
                       "GITHUB_WORKFLOW_REF": preserve.REPOSITORY + "/" + preserve.WORKFLOW + "@refs/heads/" + preserve.BRANCH}
        with patch.object(preserve, "git", return_value=SimpleNamespace(stdout=(IDENTITY["commit"] + "\n").encode())):
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(preserve.hosted_identity(), IDENTITY)
            for key, value in (("GITHUB_REF", "refs/heads/main"), ("GITHUB_REPOSITORY", "elsewhere/repo"),
                               ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("GITHUB_RUN_ATTEMPT", "2"),
                               ("GITHUB_RUN_ID", "0"), ("GITHUB_SHA", "b" * 40),
                               ("GITHUB_WORKFLOW_SHA", "b" * 40), ("GITHUB_WORKFLOW_REF", "wrong-workflow")):
                with self.subTest(key=key), patch.dict(os.environ, {**environment, key: value}, clear=True):
                    with self.assertRaises(ValueError):
                        preserve.hosted_identity()

    def test_git_tree_is_parentless_create_only_and_does_not_change_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            remote = Path(temporary) / "remote.git"
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args])
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("remote", "add", "origin", str(remote))
            (root / "source.txt").write_text("candidate\n")
            (root / ".gitignore").write_text("ignored.tmp\n.artifacts/\n")
            git("add", "source.txt", ".gitignore")
            git("commit", "-qm", "fixture")
            before = git("rev-parse", "HEAD")
            destination = root / ".artifacts/evidence"
            destination.mkdir(parents=True)
            (destination / "raw.partial").write_bytes(b"incomplete\x00bytes")
            with patch.object(preserve, "ROOT", root), patch.dict(os.environ, GITHUB_RUN_ID="123"):
                preserve.clean_source()
                (root / "ignored.tmp").write_text("unexpected")
                with self.assertRaisesRegex(ValueError, "outside .artifacts"):
                    preserve.clean_source()
                (root / "ignored.tmp").unlink()
                (root / "source.txt").write_text("drift\n")
                with self.assertRaisesRegex(ValueError, "Tracked"):
                    preserve.clean_source()
                (root / "source.txt").write_text("candidate\n")
                branch = "validation/evidence-comprehensive-v010-123-1"
                published = preserve.publish(destination, branch)
                self.assertFalse(published["already_preserved"])
                self.assertEqual(git("show", "-s", "--format=%P", published["commit"]).strip(), b"")
                self.assertEqual(git("show", "-s", "--format=%an <%ae>", published["commit"]).strip(), b"Afloat <ShuffleMonkey@163.com>")
                self.assertTrue(preserve.publish(destination, branch)["already_preserved"])
                (destination / "raw.partial").write_bytes(b"replacement")
                with self.assertRaisesRegex(ValueError, "will not be overwritten"):
                    preserve.publish(destination, branch)
                self.assertEqual(git("ls-remote", "origin", "refs/heads/" + branch).split()[0].decode(), published["commit"])
                self.assertEqual(git("rev-parse", "HEAD"), before)
                self.assertEqual(git("status", "--porcelain"), b"")

    def test_workflow_runs_component_steps_independently_and_pins_the_plan(self):
        workflow = (preserve.ROOT / ".github/workflows/comprehensive-runtime-performance.yml").read_text()
        plan = preserve.read(preserve.ROOT / preserve.PLAN)
        self.assertIn("branches: ['" + plan["trigger_branch"] + "']", workflow)
        self.assertIn("github.run_attempt == 1", workflow)
        self.assertIn("--hash=sha256:" + plan["environment"]["numpy_wheel_sha256"], workflow)
        self.assertIn("--require-hashes", workflow)
        self.assertIn("--force-reinstall", workflow)
        for component in ("semantic", "directory"):
            self.assertIn(plan[component]["command"], workflow)
            condition = re.search(r"id: " + component + r"_measure\n\s+if: (.+)", workflow).group(1)
            self.assertIn("!cancelled()", condition)
            self.assertIn("steps." + component + "_validate.outcome == 'success'", condition)
            self.assertNotIn("_measure.outcome", condition)
        self.assertIn("name: comprehensive-v010-${{ github.run_id }}-${{ github.run_attempt }}", workflow)
        self.assertNotIn("continue-on-error", workflow)


class SemanticFailureLedgerTests(unittest.TestCase):
    def test_failure_keeps_completed_raw_events_and_never_overwrites_a_prior_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, ledger = root / "report.json", root / "events.jsonl"
            def failed_case(*args):
                semantic.event("ranking-latency", observation={"elapsed_ns": 100, "exact_equal": False})
                raise RuntimeError("fixture failure")
            with patch.dict(sys.modules, {"numpy": SimpleNamespace(__version__=preserve.NUMPY)}), \
                 patch.object(semantic, "modules", return_value=({}, {})), patch.object(semantic, "ranking_case", side_effect=failed_case):
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    semantic.main(["--output", str(report), "--events", str(ledger)])
                raw = ledger.read_bytes()
                events = [json.loads(line) for line in raw.splitlines()]
                self.assertEqual([row["event"] for row in events], ["started", "ranking-latency", "failed"])
                self.assertFalse(report.exists())
                with self.assertRaises(SystemExit):
                    semantic.main(["--output", str(report), "--events", str(ledger)])
                self.assertEqual(ledger.read_bytes(), raw)

    def test_failed_timed_call_retains_both_clock_observations(self):
        def fail():
            raise RuntimeError("failed call")
        with patch.object(semantic.time, "perf_counter_ns", side_effect=[100, 250]), \
             patch.object(semantic.time, "process_time_ns", side_effect=[20, 70]):
            result, measurement, error = semantic.measure(fail)
        self.assertIsNone(result)
        self.assertEqual(measurement, {"elapsed_ns": 150, "process_cpu_ns": 50})
        self.assertIsInstance(error, RuntimeError)


if __name__ == "__main__":
    unittest.main()
