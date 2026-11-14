"""Pure preregistration, source-boundary and gate fixtures; no timed retrieval."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round6_performance as benchmark


def plan_fixture():
    return {"schema_version": 1, "baseline": benchmark.BASELINE,
        "performance_candidate": {"formal": {"cohorts": list(benchmark.COHORTS), "configs": list(benchmark.CONFIGURATIONS),
            "rounds": 4, "engine_order": benchmark.ORDERS, "calls": 56784}},
        "thresholds_percent": benchmark.THRESHOLDS,
        "cohorts": [{"name": name, **value} for name, value in benchmark.COHORTS.items()]}


def set_nested(value, path, item):
    parts = path.split(".")
    for part in parts[:-1]:
        value = value.setdefault(part, {})
    value[parts[-1]] = item


def acceptance_fixture():
    spec = benchmark.measurement_spec(plan_fixture(), "formal")
    workers = []
    for item in benchmark.schedule(spec):
        worker = dict(item)
        for field in benchmark.resource_fields(spec):
            set_nested(worker, field, 100)
        workers.append(worker)
    compared = []
    for cohort in spec["cohorts"]:
        for config in spec["configs"]:
            compared.append({"cohort": cohort, **config,
                "baseline": {"latency": {"p50_ms": 100, "p95_ms": 100, "mean_ms": 100}},
                "candidate": {"latency": {"p50_ms": 80, "p95_ms": 80, "mean_ms": 80}},
                "candidate_change_percent": {"p50_ms": -20, "p95_ms": -20, "mean_ms": -20}})
    return {"validation": {"passed": True}, "run": {"stage": "formal", "measurement": spec}, "workers": workers}, compared


def memo_snapshot(**changes):
    result = {"available": True, **dict.fromkeys(benchmark.MEMO_FIELDS, 0), "entry_limit": 2048, "text_byte_limit": 2097152}
    result.update(changes)
    return result


class RoundSixPlanTests(unittest.TestCase):
    def test_registered_matrix_and_balanced_diagnostics(self):
        plan = benchmark.validate_plan(plan_fixture())
        for stage, calls, workers in (("formal", 56784, 16), ("development-native", 18928, 8), ("development-mcp", 4060, 4)):
            with self.subTest(stage=stage):
                spec = benchmark.measurement_spec(plan, stage)
                self.assertEqual(spec["calls"], calls)
                self.assertEqual(sum(benchmark.COHORTS[c]["queries"] for c in spec["cohorts"]) * len(spec["configs"]) * spec["rounds"] * 2, calls)
                self.assertEqual(len(benchmark.schedule(spec)), workers)
                for cohort in spec["cohorts"]:
                    order = [x["label"] for x in benchmark.schedule(spec) if x["cohort"] == cohort]
                    self.assertEqual(order, [label for pair in spec["engine_order"] for label in pair])

    def test_matrix_cannot_drop_mcp_or_shrink_budget_axis(self):
        for change in (lambda p: p["performance_candidate"]["formal"]["configs"].pop(),
                       lambda p: p["thresholds_percent"].update(geometric_mean_p95_improvement=9),
                       lambda p: p["cohorts"][0].update(queries=61),
                       lambda p: p["baseline"].update(commit="a" * 40)):
            plan = deepcopy(plan_fixture())
            change(plan)
            with self.assertRaises(ValueError):
                benchmark.validate_plan(plan)

    def test_actual_plan_matches_public_preregistration_shape(self):
        benchmark.validate_plan(json.loads(benchmark.PLAN.read_bytes()))

    def test_storage_and_each_actual_mcp_process_are_reviewed(self):
        fields = benchmark.resource_fields(benchmark.measurement_spec(plan_fixture(), "formal"))
        self.assertEqual(len(fields), len(set(fields)))
        for name in ("mcp-char4000", "mcp-token1024"):
            self.assertIn("mcp_sessions." + name + ".mcp_startup_to_initialize_ms", fields)
            self.assertIn("mcp_sessions." + name + ".mcp_server_memory_after_calls.hwm_bytes", fields)
            self.assertIn("mcp_sessions." + name + ".storage_after_mcp_live.files_bytes.wal", fields)
        self.assertIn("storage_after_checkpoint.logical_db_bytes", fields)

    def test_claim_identity_is_independent_of_binding_filename(self):
        binding = {"stage": "formal", "sources": {"baseline": benchmark.BASELINE, "candidate": {"commit": "b" * 40, "runtime_sha256": "c" * 64}}}
        args = SimpleNamespace(publish_branch="validation/v034-round6-performance-123-1",
            output=benchmark.ROOT / "benchmarks/reports/round6-performance-123-1/report.json.gz",
            state_dir=benchmark.ROOT / ".artifacts/round6-performance-123-1", binding=Path("old-binding.json"))
        environment = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book",
                       "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/ci/v034-round6-performance", "GITHUB_SHA": "f" * 40}
        with patch.dict(benchmark.os.environ, environment), patch.object(benchmark, "git", side_effect=lambda *args: ("f" * 40).encode() if args == ("rev-parse", "HEAD") else b"https://github.com/Afloat16/AI-Memory-Book.git\n"):
            first = benchmark.publication_identity(args, binding)
            args.binding = Path("renamed-binding.json")
            second = benchmark.publication_identity(args, binding)
            self.assertEqual(first["claim_branch"], second["claim_branch"])
            self.assertEqual(first["workflow_commit"], environment["GITHUB_SHA"])
            with patch.dict(benchmark.os.environ, {"GITHUB_SHA": "e" * 40}):
                with self.assertRaisesRegex(ValueError, "exact triggering"):
                    benchmark.publication_identity(args, binding)
            with patch.dict(benchmark.os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
                with self.assertRaises(ValueError):
                    benchmark.publication_identity(args, binding)


class RoundSixGateTests(unittest.TestCase):
    def test_all_numerical_gates_pass_with_exact_resources(self):
        report, compared = acceptance_fixture()
        value = benchmark.acceptance(report, compared)
        self.assertTrue(value["accepted"])
        self.assertTrue(value["numeric_gate_passed"])
        self.assertAlmostEqual(value["geometric_mean_p95_improvement_percent"], 20)

    def test_resource_increase_never_automatically_waives_raw_failure(self):
        report, compared = acceptance_fixture()
        for worker in report["workers"]:
            if worker["cohort"] == "public1015" and worker["label"] == "candidate":
                worker["native_open_ms"] = 111
        value = benchmark.acceptance(report, compared)
        self.assertTrue(value["numeric_gate_passed"])
        self.assertFalse(value["accepted"])
        self.assertEqual([(x["cohort"], x["metric"]) for x in value["resource_review"]], [("public1015", "native_open_ms")])

    def test_zero_to_nonzero_storage_requires_review(self):
        report, compared = acceptance_fixture()
        for worker in report["workers"]:
            set_nested(worker, "storage_after_checkpoint.files_bytes.wal", 0 if worker["label"] == "baseline" else 1)
        value = benchmark.acceptance(report, compared)
        self.assertTrue(value["numeric_gate_passed"])
        self.assertFalse(value["accepted"])
        self.assertTrue(all(x["mean_change_percent"] is None for x in value["resource_review"]))

    def test_each_speed_gate_is_required(self):
        for axis in ("aggregate", "native", "mcp"):
            report, compared = acceptance_fixture()
            for cell in compared:
                affected = axis == "aggregate" or (axis == "native" and cell["cohort"] == "public1015" and cell["surface"] == "native" and cell["budget_tokens"] is not None) or (axis == "mcp" and cell["cohort"] == "public1015" and cell["id"] == "mcp-token1024")
                if affected:
                    candidate = 90.01 if axis in ("aggregate", "mcp") else 85.01
                    cell["candidate"]["latency"]["p95_ms"] = candidate
                    cell["candidate_change_percent"]["p95_ms"] = candidate - 100
            with self.subTest(axis=axis):
                self.assertFalse(benchmark.acceptance(report, compared)["numeric_gate_passed"])

    def test_one_pooled_regression_rejects_even_with_large_aggregate_gain(self):
        report, compared = acceptance_fixture()
        compared[0]["candidate_change_percent"]["p50_ms"] = 5.01
        compared[0]["candidate"]["latency"]["p50_ms"] = 105.01
        self.assertFalse(benchmark.acceptance(report, compared)["numeric_gate_passed"])

    def test_diagnostics_do_not_become_release_acceptance(self):
        report, compared = acceptance_fixture()
        report["run"]["stage"] = "development-native"
        value = benchmark.acceptance(report, compared)
        self.assertFalse(value["accepted"])
        self.assertIsNone(value["numeric_gate_passed"])
        self.assertFalse(value["formal_acceptance_evaluated"])


class RoundSixMemoTests(unittest.TestCase):
    def record(self):
        configs = [{**dict(benchmark.CONFIGURATIONS[0]), "rows": [{"query_id": "q"}]}]
        snapshots = {k: memo_snapshot() for k in ("before", "after_first_call", "after")}
        report = {"native_token_count_memo": {**benchmark.memo_diagnostics(), "configurations": [{"id": "native-char4000", "first_query_id": "q", **snapshots}]}}
        return report, configs

    def test_both_sources_use_empty_bounded_memo(self):
        for label in ("baseline", "candidate"):
            report, configs = self.record()
            report["label"] = label
            benchmark.verify_native_memo(report, configs)

    def test_memo_cannot_be_prewarmed_or_character_warmed(self):
        for field in ("before", "after_first_call", "after"):
            report, configs = self.record()
            report["native_token_count_memo"]["configurations"][0][field] = memo_snapshot(allocated=1, entries=1, text_bytes=10)
            with self.assertRaises(ValueError):
                benchmark.verify_native_memo(report, configs)

    def test_memo_limits_and_absent_baseline_diagnostics_rejected(self):
        for snapshot in (memo_snapshot(allocated=1, entries=2049), memo_snapshot(allocated=1, text_bytes=2097153), {"available": False}):
            with self.assertRaises(ValueError):
                benchmark.check_memo_snapshot(snapshot)


class RoundSixSourceBoundaryTests(unittest.TestCase):
    def database(self, stamp):
        from scripts.round6_audit_performance import SOURCE_COLUMNS
        db = sqlite3.connect(":memory:")
        for table, retained in SOURCE_COLUMNS.items():
            fields = retained + benchmark.HOST_TIMESTAMP_COLUMNS.get(table, [])
            db.execute(f"CREATE TABLE {table} (" + ",".join('"' + name + '" TEXT' for name in fields) + ")")
            values = [stamp if name in benchmark.HOST_TIMESTAMP_COLUMNS.get(table, []) else name + "-content" for name in fields]
            db.execute(f"INSERT INTO {table} VALUES (" + ",".join("?" for _ in fields) + ")", values)
        return db

    def test_only_declared_host_timestamps_are_omitted_cross_archive(self):
        with self.database("old-host-time") as old, self.database("new-host-time") as new:
            self.assertEqual(benchmark.source_semantics(old), benchmark.source_semantics(new))
            self.assertNotEqual(benchmark.source_snapshot(old), benchmark.source_snapshot(new))
            new.execute("UPDATE sessions SET created_at='changed-source-date'")
            self.assertNotEqual(benchmark.source_semantics(old), benchmark.source_semantics(new))

    def test_project_names_and_any_new_source_column_remain_visible(self):
        with self.database("host-time") as db:
            original = benchmark.source_semantics(db)
            db.execute("UPDATE projects SET name='changed-project-name'")
            self.assertNotEqual(original, benchmark.source_semantics(db))
            db.execute("ALTER TABLE turns ADD COLUMN extra_source TEXT")
            self.assertIn("extra_source", benchmark.source_semantics(db)["turns"]["columns"])


if __name__ == "__main__":
    unittest.main()
