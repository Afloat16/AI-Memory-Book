"""Artificial startup protocol counterexamples; no product/process timing."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import round6_startup as runner


def fake_report():
    """Invented, explicitly non-measured data exercises every evidence branch."""
    tables = {name: {"columns": [], "rows": []} for name in
              ("projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache", "pages_fts", "pages_stem_fts")}
    tables["meta"] = {"columns": ["key", "value"], "rows": [["revision", "0"], ["stem_revision", "0"]]}
    snapshot = {"schema_version": 3, "application_id": 0x4D424F4B, "quick_check": ["ok"], "schema": [], "tables": tables}
    run = {"schedule": runner.schedule(), "source_paths": {label: "/invented/" + label + "/src" for label in ("baseline", "candidate")},
           "binding": {"sources": {"baseline": {"version": "0.3.3"}, "candidate": {"version": "0.3.4"}}},
           "host": {"executable": sys.executable}}
    fixture = {"details": {"database_after": snapshot, "stats": {"database_bytes": 159744}}}
    rows = []
    for item in run["schedule"]:
        source = run["source_paths"][item["engine"]]
        version = run["binding"]["sources"][item["engine"]]["version"]
        boundary = item["boundary"]
        candidate = item["engine"] == "candidate"
        primary = ((60 if candidate else 100) if boundary.startswith("cli-") else
                   ((5 if candidate else 20) if boundary == "api-new" else 10))
        wall = primary if boundary.startswith("cli-") else 200
        start = 1_000_000_000 + item["sequence"] * 1_000_000_000
        cwd = Path("/invented/samples") / str(item["sequence"]) / "cwd"
        db = cwd.parent / "book.db"
        env = runner.process_environment(source, cwd, db)
        process = {"command": [sys.executable, "-m", "memory_book", "--" + boundary.split("-", 1)[1]] if boundary.startswith("cli-")
                   else runner.helper_command(boundary, source, db, version),
                   "cwd": str(cwd), "environment": env, "returncode": 0, "wall_start_ns": start,
                   "wall_end_ns": start + int(wall * 1e6), "wall_ms": wall, "user_cpu_s": .01,
                   "system_cpu_s": .01, "max_rss_bytes": 16_000_000, "timed_out": False,
                   "stdout": version + "\n" if boundary == "cli-version" else "identical artificial help\n",
                   "stderr": "", "cwd_before": [], "cwd_after": []}
        details = None
        if not boundary.startswith("cli-"):
            timer = {"start_ns": start + 1_000_000, "end_ns": start + 1_000_000 + int(primary * 1e6), "elapsed_ms": primary}
            if boundary.startswith("api-"):
                details = {"module_path": source + "/memory_book/__init__.py", "store_path": source + "/memory_book/store.py",
                    "class_module": "memory_book.store", "version": version, "timer": timer,
                    "database_before": snapshot if boundary == "api-existing" else None,
                    "database_after": snapshot if boundary != "api-import" else None,
                    "stats": {**dict.fromkeys(("projects", "chapters", "sessions", "turns", "sections", "pages", "chars", "page_chars", "cache_entries", "revision"), 0), "schema_version": 3, "database_bytes": 159744}}
            else:
                initialized = {"serverInfo": {"name": "artificial", "version": "1.30.0"}, "instructions": "same"}
                tools = {"tools": []}
                command = [sys.executable, "-m", "memory_book", "--db", str(db), "mcp"]
                details = {"timer": timer, "initialize_result": initialized, "tools_result": tools,
                    "initialize_identity_sha256": runner.digest(initialized), "tools_sha256": runner.digest(tools),
                    "instructions_sha256": runner.sha(b"same"), "server_command": command, "server_environment": env,
                    "database_before": snapshot, "database_after": snapshot,
                    "server_sample": {"pid": 123, "cmdline": command, "sampled_at_ns": timer["end_ns"] + 1,
                        "rss_bytes": 32_000_000, "hwm_bytes": 33_000_000, "user_cpu_s": .1, "system_cpu_s": .02}}
            process["stdout"] = json.dumps(details)
        rows.append({**item, "status": "completed", "primary_ms": primary, "process": process, "details": details,
                     "database_exists_after": boundary in ("api-new", "api-existing", "mcp-initialize")})
    return {"run": run, "fixture": fixture, "observations": rows, "integrity_after": {"passed": True}}


class StartupProtocolTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((runner.ROOT / runner.PLAN_PATH).read_bytes())

    def test_complete_matrix_is_fixed_balanced_and_interpolation_is_not_nearest_rank(self):
        expected = runner.schedule()
        self.assertEqual(len(expected), 480)
        for number, order in enumerate(runner.ORDERS):
            for boundary in runner.BOUNDARIES:
                engines = [item["engine"] for item in expected if item["round"] == number and item["boundary"] == boundary]
                self.assertEqual(engines, [order[0]] * 10 + [order[1]] * 10)
        self.assertAlmostEqual(runner.percentile(list(range(40)), .95), 37.05)

    def test_complete_artificial_evidence_validates_and_exact_percent_thresholds_pass(self):
        report = fake_report()
        self.assertTrue(runner.validation(report)["passed"])
        compared = runner.comparisons(report["observations"])
        self.assertTrue(runner.evaluate(compared, True, self.plan)["accepted"])
        for row in report["observations"]:
            if row["engine"] == "candidate" and row["boundary"].startswith("cli-"):
                row["primary_ms"] = 80
            if row["engine"] == "candidate" and row["boundary"] == "api-new":
                row["primary_ms"] = 10
        accepted = runner.evaluate(runner.comparisons(report["observations"]), True, self.plan)
        self.assertTrue(accepted["numeric_gate_passed"])
        for row in report["observations"]:
            if row["engine"] == "candidate" and row["boundary"] == "cli-help":
                row["primary_ms"] = 80.001
        self.assertFalse(runner.evaluate(runner.comparisons(report["observations"]), True, self.plan)["numeric_gate_passed"])

    def test_secondary_requires_both_materiality_conditions_and_keeps_small_adverse(self):
        report = fake_report()
        for value, passed in ((11, True), (11.001, False)):
            for row in report["observations"]:
                if row["engine"] == "candidate" and row["boundary"] == "api-existing":
                    row["primary_ms"] = value
            compared = runner.comparisons(report["observations"])
            self.assertEqual(runner.evaluate(compared, True, self.plan)["numeric_gate_passed"], passed)
            adverse = runner.adverse(compared)
            self.assertEqual(len([row for row in adverse["pooled"] if row["boundary"] == "api-existing"]), 5)
            self.assertEqual(len([row for row in adverse["rounds"] if row["boundary"] == "api-existing"]), 20)

    def test_resource_review_does_not_erase_numeric_pass_or_zero_baseline(self):
        report = fake_report()
        for row in report["observations"]:
            if row["boundary"] == "api-new":
                row["process"]["system_cpu_s"] = .1 if row["engine"] == "candidate" else 0
        result = runner.evaluate(runner.comparisons(report["observations"]), True, self.plan)
        self.assertTrue(result["numeric_gate_passed"])
        self.assertFalse(result["accepted"])
        self.assertTrue(result["original_recall_gates_unpassed"])
        self.assertEqual(result["resource_review"][0]["change_percent"], None)
        self.assertFalse(runner.evaluate([], False, self.plan)["accepted"])

    def test_rejects_wrapper_changed_source_timers_side_effects_and_missing_resources(self):
        report = fake_report()
        cases = [
            (0, lambda row: row["process"]["command"].insert(1, "wrapper")),
            (0, lambda row: row["process"]["environment"].update(PYTHONPATH="/wrong")),
            (0, lambda row: row["process"].update(cwd_after=["created.db"])),
            (0, lambda row: row["process"].update(max_rss_bytes=None)),
            (40, lambda row: row["details"]["timer"].update(end_ns=row["process"]["wall_end_ns"] + 1)),
            (60, lambda row: row["details"]["stats"].update(pages=1)),
            (100, lambda row: row["details"]["server_sample"].update(cmdline=["unrelated"])),
        ]
        for index, mutate in cases:
            with self.subTest(index=index, mutation=cases.index((index, mutate))):
                changed = copy.deepcopy(report)
                mutate(changed["observations"][index])
                self.assertFalse(runner.validation(changed)["passed"])
        for mutate in (lambda rows: rows.pop(), lambda rows: rows.reverse(), lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0]))):
            changed = copy.deepcopy(report)
            mutate(changed["observations"])
            self.assertFalse(runner.validation(changed)["passed"])

    def test_only_declared_server_version_can_be_normalized(self):
        original = {"serverInfo": {"version": "0.3.4"}, "instructions": "0.3.4 stays literal"}
        normalized = runner.normalized_initialize(original, "0.3.4")
        self.assertEqual(normalized["serverInfo"]["version"], "<declared-product-version>")
        self.assertEqual(normalized["instructions"], original["instructions"])
        self.assertEqual(runner.normalized_initialize(original, "0.3.3"), original)
        self.assertEqual(original["serverInfo"]["version"], "0.3.4")

    def test_exact_trigger_sha_and_first_attempt_are_required(self):
        environment = {"GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book", "GITHUB_EVENT_NAME": "push",
                       "GITHUB_REF": "refs/heads/ci/v034-round6-startup", "GITHUB_RUN_ID": "123",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
        binding = {"sources": {label: {"runtime_sha256": label} for label in ("baseline", "candidate")}}
        def command(*args):
            return (("a" * 40) if args[0] == "rev-parse" else "https://github.com/Afloat16/AI-Memory-Book.git").encode()
        with patch.dict(runner.os.environ, environment, clear=True), patch.object(runner, "git", side_effect=command):
            self.assertEqual(runner.publication_identity(binding)["run_id"], "123")
            with patch.dict(runner.os.environ, {"GITHUB_SHA": "b" * 40}):
                with self.assertRaises(ValueError):
                    runner.publication_identity(binding)

    def test_ambiguous_checkpoint_and_existing_claim_block_all_further_publication(self):
        for existing_claim in (False, True):
            with self.subTest(existing_claim=existing_claim), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                public, state = root / "public", root / "state"
                public.mkdir(); state.mkdir()
                identity = {"workflow_commit": "a" * 40, "branch": "result", "claim_branch": "claim"}
                calls = []

                def fake_git(*args, **_kwargs):
                    calls.append(args)
                    if args[:2] == ("ls-remote", "--heads"):
                        return b"already claimed" if existing_claim and args[-1] == "refs/heads/claim" else b""
                    if args[0] == "write-tree":
                        return b"b" * 40
                    if "commit-tree" in args:
                        return b"c" * 40
                    if args[0] == "push" and args[-1].endswith(":refs/heads/result"):
                        raise ValueError("ambiguous network result")
                    return b""

                with patch.object(runner, "ROOT", root), patch.object(runner, "git", side_effect=fake_git):
                    with self.assertRaises(runner.PublicationFailure):
                        runner.publish(public, state, identity, "claim", claim=True)
                    self.assertTrue((public / "publication-failure.json").exists())
                    self.assertFalse((state / "publication-parent.json").exists())
                    before = len(calls)
                    with self.assertRaises(ValueError):
                        runner.publish(public, state, identity, "do not retry")
                    self.assertEqual(len(calls), before)
                pushes = [args for args in calls if args[0] == "push"]
                self.assertEqual(len(pushes), 0 if existing_claim else 2)

    def test_procfs_uses_exact_child_argv_and_correct_cpu_tick_columns(self):
        command = ["/python", "-m", "memory_book", "--db", "/sample/book.db", "mcp"]
        fields = ["S"] + ["0"] * 30
        fields[11], fields[12] = "30", "7"
        text = {"/proc/self/task/5/children": "99 88", "/proc/99/status": "VmRSS:\t100 kB\nVmHWM:\t120 kB\n",
                "/proc/99/stat": "99 (python) " + " ".join(fields)}
        blobs = {"/proc/99/cmdline": b"\0".join(part.encode() for part in command) + b"\0",
                 "/proc/88/cmdline": b"unrelated\0"}
        with patch.object(Path, "iterdir", new=lambda _path: iter([Path("/proc/self/task/5")])), \
             patch.object(Path, "read_text", new=lambda path: text[str(path)]), \
             patch.object(Path, "read_bytes", new=lambda path: blobs[str(path)]), \
             patch.object(runner.os, "sysconf", return_value=100), \
             patch.object(runner.time, "perf_counter_ns", return_value=123):
            value = runner.server_sample(command)
            self.assertEqual((value["pid"], value["rss_bytes"], value["hwm_bytes"]), (99, 102400, 122880))
            self.assertEqual((value["user_cpu_s"], value["system_cpu_s"]), (.3, .07))
            blobs["/proc/88/cmdline"] = blobs["/proc/99/cmdline"]
            with self.assertRaises(ValueError):
                runner.server_sample(command)
            with patch.dict(runner.os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
                with self.assertRaises(ValueError):
                    runner.publication_identity(binding)


if __name__ == "__main__":
    unittest.main()
