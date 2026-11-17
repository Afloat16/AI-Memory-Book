"""Artificial saved-observation audit fixtures; no product/process measurement."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import round6_audit_startup as auditor
from scripts import round6_startup as producer


def full_fixture():
    """The writer computes summaries; the independent auditor reads them."""
    plan = json.loads((auditor.ROOT / auditor.PLAN_PATH).read_text())
    binding = {"schema_version": 1, "protocol": auditor.PROTOCOL, "status": "frozen-before-measurement",
        "created_at": "2026-11-14T00:00:00+00:00",
        "plan": {"path": auditor.PLAN_PATH, "commit": auditor.PLAN_COMMIT,
                 "sha256": auditor.sha((auditor.ROOT / auditor.PLAN_PATH).read_bytes())},
        "sources": plan["sources"], "measurement": plan["matrix"], "evaluator_commit": "a" * 40,
        "evaluator_files": {name: auditor.sha((auditor.ROOT / name).read_bytes()) for name in auditor.EVALUATORS}}
    binding_raw = auditor.canonical(binding) + b"\n"
    source_paths = {engine: "/synthetic/" + engine + "/src" for engine in ("baseline", "candidate")}
    executable, helper = producer.sys.executable, str(producer.ROOT / "scripts/round6_startup.py")
    publication_key = auditor.digest({"protocol": auditor.PROTOCOL,
        "sources": {name: value["runtime_sha256"] for name, value in binding["sources"].items()}})
    run = {"binding": binding, "binding_file": {"path": "benchmarks/experiments/round6-startup-test-binding.json",
                                                "sha256": auditor.sha(binding_raw)},
        "publication": {"run_id": "123456", "attempt": "1", "workflow_commit": "b" * 40,
            "key": publication_key, "branch": "validation/v034-round6-startup-123456-1",
            "claim_branch": "validation/v034-round6-startup-claim-" + publication_key},
        "host": {"executable": executable, "python": "3.12.9 (synthetic fixture)", "platform": "Linux",
            "os_release": {"ID": "ubuntu", "VERSION_ID": "24.04"}, "packages": {"mcp": "1.30.0", "pydantic": "2.14.3"},
            "boot_sha256": "1" * 64, "cpu_count": 2, "cpu_model": "Synthetic CPU"},
        "source_paths": source_paths, "schedule": producer.schedule()}
    tables = {name: {"columns": ["value"], "rows": []} for name in auditor.EMPTY_TABLES}
    tables["meta"] = {"columns": ["key", "value"], "rows": [["revision", "0"], ["stem_revision", "0"]]}
    snapshot = {"schema_version": 3, "application_id": 0x4D424F4B, "quick_check": ["ok"],
        "schema": [["table", name, name, "CREATE TABLE " + name + "(value)"] for name in sorted(tables)],
        "tables": tables}
    empty_stats = dict.fromkeys(("projects", "chapters", "sessions", "turns", "sections", "pages",
                               "chars", "page_chars", "cache_entries", "revision"), 0)
    empty_stats.update(schema_version=3, database_bytes=159744)

    def environment(source, cwd, database):
        return {"PYTHONPATH": source, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
                "MEMORY_BOOK_HOME": cwd + "/isolated-home", "MEMORY_BOOK_DB": database}

    def api_details(engine):
        source = source_paths[engine]
        return {"module_path": source + "/memory_book/__init__.py", "store_path": source + "/memory_book/store.py",
                "class_module": "memory_book.store", "version": binding["sources"][engine]["version"],
                "database_before": None, "database_after": None, "stats": None, "timer": None}

    template_details = api_details("baseline")
    template_details.update(database_after=snapshot, stats=empty_stats)
    template_db = "/synthetic/state/fixture/book.db"
    fixture = {"purpose": "Synthetic unmeasured template", "database": template_db, "database_sha256": "2" * 64,
        "command": producer.helper_command("fixture", Path(source_paths["baseline"]), Path(template_db), "0.3.3"),
        "environment": environment(source_paths["baseline"], "/synthetic/state/fixture", template_db),
        "returncode": 0, "stderr": "", "stdout": auditor.canonical(template_details).decode() + "\n", "details": template_details}
    fixture["command"][:2] = [executable, helper]
    now = 10 ** 12
    rows = []
    tools = {"tools": [{"name": name, "inputSchema": {"type": "object", "properties": {}}}
                       for name in ("recall_memory", "browse_projects", "browse_book", "browse_chapter", "browse_section", "read_page")]}
    initialize = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "AI-Memory-Book", "version": "1.30.0"}, "instructions": "Synthetic readonly instructions"}
    for identity in producer.schedule():
        boundary, engine = identity["boundary"], identity["engine"]
        default = {"cli-help": (40, 20), "cli-version": (40, 20), "api-import": (30, 30),
                   "api-new": (25, 5), "api-existing": (6, 6.1), "mcp-initialize": (600, 600)}[boundary]
        value = default[engine == "candidate"] + identity["repetition"] / 10
        elapsed_ns = round(value * 1e6)
        value = elapsed_ns / 1e6
        wall_ns = elapsed_ns if boundary.startswith("cli-") else elapsed_ns + 5_000_000
        cwd = f'/synthetic/state/samples/{identity["sequence"]:03d}/cwd'
        database = cwd.removesuffix("/cwd") + "/book.db"
        env = environment(source_paths[engine], cwd, database)
        command = ([executable, "-m", "memory_book", "--" + boundary[4:]] if boundary.startswith("cli-") else
                   auditor.helper_command(executable, helper, boundary, source_paths[engine], database,
                                          binding["sources"][engine]["version"]))
        timer = {"start_ns": now + 1_000_000, "end_ns": now + 1_000_000 + elapsed_ns, "elapsed_ms": value}
        details = None
        if boundary.startswith("api-"):
            details = api_details(engine)
            details["timer"] = timer
            if boundary != "api-import":
                details.update(database_before=snapshot if boundary == "api-existing" else None,
                               database_after=snapshot, stats=empty_stats)
        elif boundary == "mcp-initialize":
            server_command = [executable, "-m", "memory_book", "--db", database, "mcp"]
            details = {"timer": timer, "initialize_result": initialize, "tools_result": tools,
                "initialize_identity_sha256": auditor.digest(initialize), "tools_sha256": auditor.digest(tools),
                "instructions_sha256": auditor.sha(initialize["instructions"].encode()),
                "normalization": "Only initialize_result.serverInfo.version exactly equal to the declared source version becomes <declared-product-version>; no other changes.",
                "server_command": server_command, "server_environment": env,
                "server_sample": {"pid": 9000 + identity["sequence"], "cmdline": server_command,
                    "sampled_at_ns": timer["end_ns"] + 1, "rss_bytes": 10 * 1024, "hwm_bytes": 12 * 1024,
                    "user_cpu_s": .01, "system_cpu_s": .005,
                    "scope": "Live server procfs snapshot immediately after initialize; RSS/HWM and CPU observed at this point, not whole-lifetime maxima/totals."},
                "database_before": snapshot, "database_after": snapshot}
        stdout = ("usage: memory-book [-h] [--help]\n" if boundary == "cli-help" else
                  binding["sources"][engine]["version"] + "\n" if boundary == "cli-version" else
                  auditor.canonical(details).decode() + "\n")
        process = {"command": command, "cwd": cwd, "environment": env, "returncode": 0, "timed_out": False,
            "wall_start_ns": now, "wall_end_ns": now + wall_ns, "wall_ms": wall_ns / 1e6,
            "user_cpu_s": .01, "system_cpu_s": .005, "max_rss_bytes": 20 * 1024,
            "rusage_scope": "Kernel wait4 usage for the actual child PID, with Linux ru_maxrss KiB converted to bytes; it may include descendants reaped by that child. MCP helper results are not isolated client-only usage; live server resources are separately sampled.",
            "pid": 1000 + identity["sequence"], "stdout": stdout, "stderr": "", "cwd_before": [], "cwd_after": []}
        rows.append({**identity, "status": "completed", "primary_ms": value, "process": process,
                     "details": copy.deepcopy(details), "database_exists_after": boundary in ("api-new", "api-existing", "mcp-initialize")})
        now += wall_ns + 1_000_000
    report = {"schema_version": 1, "protocol": auditor.PROTOCOL, "status": "measurements_completed",
        "run": run, "fixture": fixture, "observations": rows,
        "integrity_after": {"passed": True, "sources": {name: value["runtime_sha256"] for name, value in binding["sources"].items()},
            "evaluator_files": binding["evaluator_files"], "plan_sha256": binding["plan"]["sha256"], "binding_sha256": auditor.sha(binding_raw)}}
    refresh(report, plan)
    events = []
    for identity, row in zip(producer.schedule(), rows):
        events.extend([{"event": "started", **identity, "at": "2026-11-14T00:00:00+00:00"},
                       {"event": "finished", **identity, "at": "2026-11-14T00:00:01+00:00", "observation_sha256": auditor.digest(row)}])
    report["ledger_sha256"] = auditor.sha(ledger_bytes(events))
    return report, events, binding, plan


def refresh(report, plan):
    report["validation"] = producer.validation(report)
    report["comparisons"] = producer.comparisons(report["observations"])
    report["acceptance"] = producer.evaluate(report["comparisons"], report["validation"]["passed"], plan)
    report["adverse_observations"] = producer.adverse(report["comparisons"])


def ledger_bytes(events):
    return b"".join(auditor.canonical(event) + b"\n" for event in events)


class StartupSavedAuditTests(unittest.TestCase):
    def setUp(self):
        self.report, self.events, self.binding, self.plan = full_fixture()

    def audit(self):
        return auditor.audit_observations(self.report, self.events, self.binding, self.plan)

    def rehash(self, sequence):
        row = self.report["observations"][sequence]
        if row["details"] is not None:
            row["process"]["stdout"] = auditor.canonical(row["details"]).decode() + "\n"
        self.events[2 * sequence + 1]["observation_sha256"] = auditor.digest(row)

    def test_complete_480_writer_observations_and_960_events_pass_independent_audit(self):
        result = self.audit()
        self.assertTrue(result["passed"])
        self.assertEqual((result["samples_checked"], result["ledger_events_checked"]), (480, 960))
        self.assertTrue(result["startup_numeric_gate_passed"])
        self.assertTrue(result["original_recall_gates_unpassed"])

    def test_dropped_reordered_and_changed_original_attempts_are_rejected(self):
        original = copy.deepcopy(self.events)
        for mutation in (lambda: self.events.pop(), lambda: self.events.reverse(),
                         lambda: self.events[1].update(observation_sha256="0" * 64)):
            self.events = copy.deepcopy(original)
            mutation()
            with self.assertRaises(ValueError):
                self.audit()

    def test_recomputed_timer_and_real_metadata_do_not_trust_changed_ledger_hashes(self):
        cases = ((40, lambda row: row["details"]["timer"].update(start_ns=row["process"]["wall_start_ns"] - 1)),
                 (20, lambda row: row["process"].update(stdout="wrong version\n")),
                 (100, lambda row: row["details"]["server_sample"].update(cmdline=["wrong-server"])),
                 (60, lambda row: row["details"]["database_after"]["tables"]["pages"].update(rows=[["unexpected"]])))
        saved = copy.deepcopy(self.report)
        saved_events = copy.deepcopy(self.events)
        for sequence, mutate in cases:
            with self.subTest(sequence=sequence):
                self.report = copy.deepcopy(saved)
                self.events = copy.deepcopy(saved_events)
                mutate(self.report["observations"][sequence])
                self.rehash(sequence)
                with self.assertRaises(ValueError):
                    self.audit()

    def test_p95_acceptance_and_adverse_summary_tampering_are_rejected(self):
        saved = copy.deepcopy(self.report)
        for mutate in (lambda: self.report["comparisons"][0]["pooled"]["candidate"].update(p95_ms=0.0),
                       lambda: self.report["acceptance"].update(numeric_gate_passed=False),
                       lambda: self.report["adverse_observations"]["rounds"].pop(),
                       lambda: self.report["adverse_observations"]["rounds"].append({"made_up": True})):
            self.report = copy.deepcopy(saved)
            mutate()
            with self.assertRaises(ValueError):
                self.audit()

    def test_zero_resource_baseline_is_reviewed_and_missing_rss_is_invalid(self):
        for row in self.report["observations"]:
            if row["boundary"] == "cli-help":
                row["process"]["user_cpu_s"] = 0.0 if row["engine"] == "baseline" else .001
                self.rehash(row["sequence"])
        refresh(self.report, self.plan)
        result = self.audit()
        review = next(item for item in result["acceptance"]["resource_review"] if item["metric"] == "process.user_cpu_s")
        self.assertIsNone(review["change_percent"])
        self.assertFalse(result["original_automatic_accepted"])
        self.report["observations"][0]["process"]["max_rss_bytes"] = 0
        self.rehash(0)
        with self.assertRaises(ValueError):
            self.audit()

    def test_json_rejects_duplicate_keys_and_nonfinite_values(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                auditor.json_value(text)

    def test_exact_primary_and_secondary_thresholds(self):
        comparisons = auditor.recompute_comparisons(self.report["observations"])
        by_boundary = {row["boundary"]: row for row in comparisons}
        for metric in ("median_ms", "p95_ms"):
            row = by_boundary["cli-help"]["pooled"]
            row["baseline"][metric], row["candidate"][metric] = 25.0, 20.0
            row["change_percent"][metric], row["absolute_change_ms"][metric] = -20.0, -5.0
            row = by_boundary["api-existing"]["pooled"]
            row["baseline"][metric], row["candidate"][metric] = 10.0, 11.0
            row["change_percent"][metric], row["absolute_change_ms"][metric] = 10.0, 1.0
        self.assertTrue(auditor.recompute_acceptance(comparisons, self.plan)["numeric_gate_passed"])
        row = by_boundary["api-existing"]["pooled"]
        row["candidate"]["p95_ms"], row["absolute_change_ms"]["p95_ms"] = 11.01, 1.01
        self.assertFalse(auditor.recompute_acceptance(comparisons, self.plan)["numeric_gate_passed"])

    def test_compressed_saved_files_and_declared_ledger_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path, ledger_path, binding_path = (directory / name for name in ("report.json.gz", "attempts.jsonl.gz", "binding.json"))
            report_path.write_bytes(gzip.compress(auditor.canonical(self.report), mtime=0))
            ledger_path.write_bytes(gzip.compress(ledger_bytes(self.events), mtime=0))
            binding_path.write_bytes(auditor.canonical(self.binding) + b"\n")
            (directory / "run.json").write_bytes(auditor.canonical(self.report["run"]))
            (directory / "fixture.json").write_bytes(auditor.canonical(self.report["fixture"]))
            (directory / "execution.json").write_bytes(auditor.canonical({"protocol": auditor.PROTOCOL,
                "key": self.report["run"]["publication"]["key"], "run_sha256": auditor.digest(self.report["run"])}))
            with patch.object(auditor, "verify_git_identity", return_value=(self.binding, self.plan)):
                self.assertTrue(auditor.audit_files(report_path, ledger_path, binding_path)["passed"])
                self.report["ledger_sha256"] = "0" * 64
                report_path.write_bytes(gzip.compress(auditor.canonical(self.report), mtime=0))
                with self.assertRaisesRegex(ValueError, "ledger digest"):
                    auditor.audit_files(report_path, ledger_path, binding_path)

    def test_exact_snapshot_git_checks_reject_wrong_trigger_or_evaluator_bytes(self):
        binding_raw = auditor.canonical(self.binding) + b"\n"

        def git(*arguments):
            self.assertEqual(arguments[0], "show")
            commit, path = arguments[1].split(":", 1)
            if path == self.report["run"]["binding_file"]["path"]:
                return binding_raw
            return (auditor.ROOT / path).read_bytes()

        by_commit = {value["commit"]: value["runtime_sha256"] for value in self.binding["sources"].values()}
        with patch.object(auditor, "git", side_effect=git), \
                patch.object(auditor, "committed_runtime_hash", side_effect=lambda commit: by_commit[commit]):
            self.assertEqual(auditor.verify_git_identity(self.report, binding_raw)[0], self.binding)
            self.report["run"]["binding_file"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "exact original binding"):
                auditor.verify_git_identity(self.report, binding_raw)
            self.report["run"]["binding_file"]["sha256"] = auditor.sha(binding_raw)
            damaged = copy.deepcopy(self.binding)
            damaged["evaluator_files"][auditor.EVALUATORS[0]] = "0" * 64
            binding_raw = auditor.canonical(damaged) + b"\n"
            self.report["run"]["binding_file"]["sha256"] = auditor.sha(binding_raw)
            with self.assertRaisesRegex(ValueError, "evaluator Git/current bytes"):
                auditor.verify_git_identity(self.report, binding_raw)


if __name__ == "__main__":
    unittest.main()
