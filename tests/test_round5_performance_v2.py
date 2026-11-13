"""Artificial interface failures and unchanged formal gates; no retrieval."""
import ast
import copy
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from scripts import round5_interface_certificate as certificate
from scripts import round5_performance as original
from scripts import round5_performance_v2 as bench
from tests.test_round5_performance import fixture as original_fixture, ledger_bytes


class ArtificialCounter:
    def __init__(self, offset):
        self.offset = offset

    def count(self, value):
        return len(value.encode()) + self.offset


def counters():
    return {name: ArtificialCounter(index) for index, name in enumerate(original.ENCODINGS)}


def schemas():
    old = {"tools": [
        {"name": "recall_memory", "description": "Recall exact sources.\n        ",
         "inputSchema": {"type": "object", "title": "recallArguments",
                         "properties": {"query": {"title": "Query", "type": "string"},
                                        "limit": {"type": "integer", "default": 5}},
                         "required": ["query"]},
         "annotations": {"readOnlyHint": True}, "outputSchema": {"type": "object"}},
        {"name": "read_memory", "description": "Read a page.",
         "inputSchema": {"properties": {"id": {"type": "string"}}, "required": ["id"], "type": "object"}}
    ], "_meta": {"artificial": True}}
    new = copy.deepcopy(old)
    new["tools"][0]["inputSchema"]["properties"]["follow_titles"] = copy.deepcopy(certificate.PROPERTY)
    new["tools"][0]["description"] += certificate.DESCRIPTION_SUFFIX
    return old, new


def artificial_certificate(sources):
    old, new = schemas()
    observations = {label: certificate.observation(json.dumps(value), "Same instructions.\n", counters())
                    for label, value in (("baseline", old), ("candidate", new))}
    return {"schema_version": 1, "evaluator": certificate.VERSION,
        "status": "verified-before-formal-measurement-and-fresh-selection", "created_at": "artificial",
        "sources": copy.deepcopy(sources), "packages": original.PACKAGES,
        "server_packages": {label: dict(original.PACKAGES) for label in ("baseline", "candidate")},
        "scope_sha256": certificate.SCOPE_SHA256,
        "generator_commit": "b" * 40, "generator_files": {"artificial": "c" * 64},
        "observations": observations,
        "projection": certificate.schema_projection(json.dumps(old), json.dumps(new)),
        "initialization_token_delta": certificate.initialization_delta(observations),
        "retrieval_calls_executed": 0}


def fixture(factor=.85):
    report = original_fixture(factor)
    run = report["run"]
    value = artificial_certificate(run["binding"]["sources"])
    run["binding"].update(interface_scope_sha256=certificate.SCOPE_SHA256,
        interface_certificate=value, interface_certificate_sha256=bench.sha(bench.json_bytes(value)))
    report.update(interface_scope_sha256=certificate.SCOPE_SHA256,
                  interface_certificate_sha256=run["binding"]["interface_certificate_sha256"])
    for worker in report["workers"]:
        expected = value["observations"][worker["label"]]
        worker.update(run_identity_sha256=bench.digest(run),
            mcp_tool_schema_json=expected["tool_schema_json"], mcp_instructions=expected["instructions"],
            mcp_tool_schema_sha256=expected["tool_schema_sha256"],
            mcp_instructions_sha256=expected["instructions_sha256"],
            mcp_initialization_tokens=copy.deepcopy(expected["initialization_tokens"]))
        for session in worker["mcp_sessions"].values():
            for key in ("mcp_tool_schema_json", "mcp_instructions", "mcp_tool_schema_sha256",
                        "mcp_instructions_sha256", "mcp_initialization_tokens"):
                session[key] = copy.deepcopy(worker[key])
    report["validation"] = bench.validation(report)
    return report


def nodes(path):
    return {node.name: node for node in ast.parse(path.read_text()).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


class InterfaceProjectionTests(unittest.TestCase):
    def test_exact_only_addition_preserves_full_schema_and_real_cost_delta(self):
        report = fixture()
        value = report["run"]["binding"]["interface_certificate"]
        self.assertIs(certificate.verify_certificate(value, report["run"]["binding"]["sources"], counters()), value)
        self.assertTrue(report["validation"]["passed"])
        costs = bench.initialization_comparison(report["run"]["binding"])
        for name in original.ENCODINGS:
            self.assertGreater(costs["candidate_minus_baseline"][name]["tool_schema"], 0)
            self.assertEqual(costs["candidate_minus_baseline"][name]["instructions"], 0)
        self.assertNotEqual(costs["baseline"], costs["candidate"])

    def test_exact_property_rejects_bool_numeric_coercion_default_type_title_and_extras(self):
        old, new = schemas()
        for bad in ({"default": 0, "title": "Follow Titles", "type": "boolean"},
                    {"default": True, "title": "Follow Titles", "type": "boolean"},
                    {"default": False, "title": "Follow Titles", "type": "string"},
                    {"default": False, "title": "Follow titles", "type": "boolean"},
                    {"default": False, "title": "Follow Titles", "type": "boolean", "nullable": True}):
            with self.subTest(property=bad):
                changed = copy.deepcopy(new)
                changed["tools"][0]["inputSchema"]["properties"]["follow_titles"] = bad
                with self.assertRaisesRegex(ValueError, "exact boolean/default-False"):
                    certificate.schema_projection(json.dumps(old), json.dumps(changed))

    def test_full_projection_rejects_every_other_tool_schema_field_change(self):
        old, new = schemas()
        mutations = {
            "other_tool_description": lambda x: x["tools"][1].update(description="Changed"),
            "old_default": lambda x: x["tools"][0]["inputSchema"]["properties"]["limit"].update(default=4),
            "old_default_bool": lambda x: x["tools"][0]["inputSchema"]["properties"]["limit"].update(default=True),
            "old_property": lambda x: x["tools"][0]["inputSchema"]["properties"].pop("query"),
            "extra_property": lambda x: x["tools"][0]["inputSchema"]["properties"].update(other={"type": "boolean"}),
            "required": lambda x: x["tools"][0]["inputSchema"]["required"].append("limit"),
            "output": lambda x: x["tools"][0]["outputSchema"].update(type="array"),
            "annotation": lambda x: x["tools"][0]["annotations"].update(readOnlyHint=False),
            "metadata": lambda x: x["_meta"].update(artificial=1),
            "extra_root": lambda x: x.update(extra=True),
            "tool_order": lambda x: x["tools"].reverse(),
            "missing_tool": lambda x: x["tools"].pop(),
            "duplicate_tool": lambda x: x["tools"].append(copy.deepcopy(x["tools"][0])),
        }
        for name, mutate in mutations.items():
            with self.subTest(field=name):
                changed = copy.deepcopy(new)
                mutate(changed)
                with self.assertRaises(ValueError):
                    certificate.schema_projection(json.dumps(old), json.dumps(changed))

    def test_description_requires_exact_suffix_and_optional_new_property(self):
        old, new = schemas()
        for suffix in ("", certificate.DESCRIPTION_SUFFIX.rstrip(),
                       certificate.DESCRIPTION_SUFFIX + "Extra", certificate.DESCRIPTION_SUFFIX.replace("disabled", "enabled")):
            changed = copy.deepcopy(new)
            changed["tools"][0]["description"] = old["tools"][0]["description"] + suffix
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "exact approved append-only"):
                certificate.schema_projection(json.dumps(old), json.dumps(changed))
        new["tools"][0]["inputSchema"]["required"].append("follow_titles")
        with self.assertRaisesRegex(ValueError, "remain optional"):
            certificate.schema_projection(json.dumps(old), json.dumps(new))

    def test_duplicate_json_fields_and_nonfinite_values_cannot_disappear_in_projection(self):
        for raw in ('{"tools":[],"tools":[]}', '{"tools":[],"x":NaN}', '{"tools":[],"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                certificate.strict_json(raw)

    def test_certificate_rejects_source_scope_packages_instructions_counts_and_hash_drift(self):
        report = fixture()
        base = report["run"]["binding"]["interface_certificate"]
        mutations = {
            "source": lambda x: x["sources"]["candidate"].update(commit="c" * 40),
            "scope": lambda x: x.update(scope_sha256="0" * 64),
            "package": lambda x: x["packages"].update(mcp="1.29.0"),
            "server_package": lambda x: x["server_packages"]["candidate"].update(pydantic="2.13.4"),
            "instructions": lambda x: x["observations"]["candidate"].update(instructions="Changed"),
            "schema_hash": lambda x: x["observations"]["candidate"].update(tool_schema_sha256="0" * 64),
            "count": lambda x: x["observations"]["candidate"]["initialization_tokens"]["cl100k_base"].update(tool_schema=1),
            "count_bool": lambda x: x["observations"]["candidate"]["initialization_tokens"]["cl100k_base"].update(instructions=False),
            "delta": lambda x: x["initialization_token_delta"]["cl100k_base"].update(tool_schema=0),
            "projection": lambda x: x["projection"].update(verified=False),
            "database": lambda x: x["observations"]["baseline"].update(database_created=True),
            "retrieval": lambda x: x.update(retrieval_calls_executed=1),
        }
        for name, mutate in mutations.items():
            with self.subTest(field=name):
                value = copy.deepcopy(base)
                mutate(value)
                with self.assertRaises(ValueError):
                    certificate.verify_certificate(value, report["run"]["binding"]["sources"], counters())

    def test_equal_rehashed_changed_instructions_are_still_rejected_cross_source(self):
        report = fixture()
        value = report["run"]["binding"]["interface_certificate"]
        item = value["observations"]["candidate"]
        value["observations"]["candidate"] = certificate.observation(item["tool_schema_json"], "New instructions", counters())
        with self.assertRaisesRegex(ValueError, "instructions changed"):
            certificate.verify_certificate(value, report["run"]["binding"]["sources"], counters())

    def test_every_actual_mcp_session_must_match_its_certified_source_bytes(self):
        for field, bad in (("mcp_tool_schema_json", "{}"), ("mcp_tool_schema_sha256", "0" * 64),
                           ("mcp_instructions", "Changed"), ("mcp_instructions_sha256", "0" * 64)):
            report = fixture()
            worker = next(w for w in report["workers"] if w["label"] == "candidate")
            worker["mcp_sessions"]["mcp-token1024"][field] = bad
            with self.subTest(field=field):
                self.assertFalse(bench.validation(report)["passed"])
        report = fixture()
        worker = next(w for w in report["workers"] if w["label"] == "candidate")
        worker["mcp_sessions"]["mcp-token1024"]["mcp_initialization_tokens"]["o200k_base"]["tool_schema"] -= 1
        self.assertFalse(bench.validation(report)["passed"])

    def test_binding_digest_and_missing_or_stale_certificate_fail(self):
        report = fixture()
        original_binding = report["run"]["binding"]
        for mutate in (lambda x: x.pop("interface_certificate"),
                       lambda x: x.update(interface_certificate_sha256="0" * 64),
                       lambda x: x.update(interface_scope_sha256="0" * 64),
                       lambda x: x["sources"]["candidate"].update(commit="c" * 40)):
            value = copy.deepcopy(original_binding)
            mutate(value)
            with self.assertRaises((ValueError, KeyError)):
                bench.verify_bound_interface(value)

    def test_published_certificate_must_keep_complete_original_bytes_and_registration(self):
        report = fixture()
        value = report["run"]["binding"]["interface_certificate"]
        with tempfile.TemporaryDirectory(dir=bench.ROOT) as directory:
            path = Path(directory) / "certificate.json"
            path.write_bytes(bench.json_bytes(value))
            with patch.object(certificate, "CERTIFICATE", path), \
                    patch.object(original, "git", return_value=b"different committed bytes"):
                with self.assertRaisesRegex(ValueError, "Commit the exact interface certificate"):
                    certificate.load_certificate(report["run"]["binding"]["sources"])
        with patch.object(certificate, "registration_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "evaluator registration changed"):
                certificate.verify_registration(value)

    def test_generation_wrong_dependencies_preserves_failure_without_sdk_or_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "certificate.json"
            args = SimpleNamespace(output=output, baseline_src=root / "baseline", candidate_src=root / "candidate")
            with patch.object(certificate, "ROOT", root), patch.object(certificate, "CERTIFICATE", output), \
                    patch.object(certificate.importlib.metadata, "version", return_value="wrong"), \
                    patch.object(certificate, "collect") as sdk:
                # load_scope reads the frozen actual scope; no source or SDK process is started.
                with patch.object(certificate, "load_scope", return_value={}):
                    with self.assertRaisesRegex(ValueError, "exact registered SDK"):
                        certificate.generate(args)
                sdk.assert_not_called()
            failures = list((root / ".artifacts/round5-interface-certificate").glob("*/failed.json"))
            self.assertEqual(len(failures), 1)
            failed = json.loads(failures[0].read_bytes())
            self.assertEqual(failed["status"], "failed_or_interrupted")
            self.assertEqual(failed["retrieval_calls_executed"], 0)
            self.assertFalse(output.exists())
            self.assertTrue(failures[0].with_name("started.json").exists())

    def test_generation_never_overwrites_existing_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "certificate.json"
            output.write_bytes(b"preserve original")
            with patch.object(certificate, "CERTIFICATE", output):
                with self.assertRaisesRegex(ValueError, "never be overwritten"):
                    certificate.generate(SimpleNamespace(output=output))
            self.assertEqual(output.read_bytes(), b"preserve original")

    def test_child_dependency_probe_cannot_inherit_only_parent_version_claim(self):
        environment = {"PYTHONPATH": "/invented/bound/src"}
        with patch.object(certificate.subprocess, "check_output", return_value=bench.json_bytes(original.PACKAGES)) as probe:
            self.assertEqual(certificate.server_packages(environment, Path("/invented/work")), original.PACKAGES)
            self.assertEqual(probe.call_args.kwargs["env"], environment)
            self.assertEqual(probe.call_args.kwargs["cwd"], Path("/invented/work"))
        different = {**original.PACKAGES, "pydantic": "2.13.4"}
        with patch.object(certificate.subprocess, "check_output", return_value=bench.json_bytes(different)):
            with self.assertRaisesRegex(ValueError, "Actual stdio server.*2.13.4"):
                certificate.server_packages(environment, Path("/invented/work"))

    def test_failed_second_schema_preserves_completed_first_observation_and_never_publishes_certificate(self):
        report = fixture()
        value = report["run"]["binding"]["interface_certificate"]
        sources = value["sources"]
        source_hashes = {"registered": bench.sha(b"frozen")}
        commit = "d" * 40

        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return commit.encode()
            if args == ("show", commit + ":registered"):
                return b"frozen"
            self.fail("Unexpected Git command: " + repr(args))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "certificate.json"
            args = SimpleNamespace(output=output, baseline_src=root / "baseline", candidate_src=root / "candidate")
            first = {"observation": value["observations"]["baseline"], "packages": dict(original.PACKAGES)}
            with patch.object(certificate, "ROOT", root), patch.object(certificate, "CERTIFICATE", output), \
                    patch.object(certificate, "load_scope", return_value={}), \
                    patch.object(certificate.importlib.metadata, "version", side_effect=original.PACKAGES.__getitem__), \
                    patch.object(certificate, "registration_hashes", return_value=source_hashes), \
                    patch.object(original, "git", side_effect=git), \
                    patch.object(original, "source_identity", side_effect=lambda path: sources[path.name]), \
                    patch.object(certificate, "reference_counters", return_value=counters()), \
                    patch.object(certificate, "collect", new=AsyncMock(side_effect=[first, RuntimeError("artificial disconnect")])):
                with self.assertRaisesRegex(RuntimeError, "artificial disconnect"):
                    certificate.generate(args)
            attempts = list((root / ".artifacts/round5-interface-certificate").iterdir())
            self.assertEqual(len(attempts), 1)
            failed = json.loads((attempts[0] / "failed.json").read_bytes())
            self.assertEqual(failed["observations"], {"baseline": first["observation"]})
            self.assertEqual(json.loads((attempts[0] / "baseline.json").read_bytes()), first)
            self.assertEqual(failed["retrieval_calls_executed"], 0)
            self.assertFalse(output.exists())


class FormalGatePreservationTests(unittest.TestCase):
    def test_original_files_and_scope_are_byte_frozen(self):
        scope = certificate.load_scope()
        self.assertEqual(bench.CONFIGURATIONS, original.CONFIGURATIONS)
        self.assertEqual(bench.GATES, original.GATES)
        self.assertEqual(bench.INVARIANTS, original.INVARIANTS)
        self.assertEqual(bench.RESOURCE_FIELDS, original.RESOURCE_FIELDS)
        self.assertEqual(bench.PACKAGES, original.PACKAGES)
        self.assertEqual(scope["formal_measurement_unchanged"]["calls"], 66248)
        self.assertEqual(len(bench.schedule(json.loads(bench.PLAN.read_bytes()))), 16)
        self.assertTrue(set(original.EVALUATORS).issubset(bench.EVALUATORS))
        self.assertIn(certificate.CERTIFICATE.relative_to(bench.ROOT).as_posix(), bench.EVALUATORS)

    def test_gate_ledger_schedule_payload_and_hosted_claim_functions_are_exact_original_ast(self):
        old = nodes(bench.ROOT / "scripts/round5_performance.py")
        new_source = (bench.ROOT / "scripts/round5_performance_v2.py").read_text()
        new_source = new_source.replace("round5-performance-v2", "round5-performance")
        new = {n.name: n for n in ast.parse(new_source).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        unchanged = ("load_plan", "load_addendum", "load_canonical_addendum", "load_derived_addendum",
            "source_identity", "host_identity", "dataset", "schedule", "query_order", "make_row", "Ledger",
            "stable_row", "nested", "comparisons", "acceptance", "summary", "load_completed", "artifact_hashes",
            "resume_prefix", "publication_identity", "publication_state", "verify_worker_claim", "export_checkpoint",
            "preserve_publication_failure", "claim_execution", "publish_checkpoint", "checkpoint", "controller", "main")
        for name in unchanged:
            with self.subTest(function=name):
                self.assertEqual(ast.dump(new[name]), ast.dump(old[name]))

    def test_native_and_actual_mcp_timing_calls_are_unchanged_except_certificate_argument(self):
        old = nodes(bench.ROOT / "scripts/round5_performance.py")
        new = nodes(bench.ROOT / "scripts/round5_performance_v2.py")
        worker = copy.deepcopy(new["worker"])
        calls = [n for n in ast.walk(worker) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "mcp_configuration"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0].args.pop()), "binding['interface_certificate']['observations'][item['label']]")
        self.assertEqual(ast.dump(worker), ast.dump(old["worker"]))
        mcp = copy.deepcopy(new["mcp_configuration"])
        self.assertEqual(mcp.args.args.pop().arg, "certified_interface")

        class RemoveCertificateObservations(ast.NodeTransformer):
            def visit_Assign(self, node):
                target = ast.unparse(node.targets[0])
                if target in ("session_record['mcp_tool_schema_json']", "session_record['mcp_instructions']"):
                    return None
                return self.generic_visit(node)

            def visit_Expr(self, node):
                if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == "interface.verify_session":
                    return None
                return self.generic_visit(node)

        mcp = RemoveCertificateObservations().visit(mcp)
        self.assertEqual(ast.dump(mcp), ast.dump(old["mcp_configuration"]))

    def test_workflow_keeps_original_permissions_sdk_claim_checkpoints_and_failure_exports(self):
        old = (bench.ROOT / ".github/workflows/round5-performance.yml").read_text()
        new = (bench.ROOT / ".github/workflows/round5-performance-v2.yml").read_text()
        new = new.replace(" with certified interface", "")
        new = new.replace("round5-performance-v2", "round5-performance")
        new = new.replace("tests.test_round5_performance tests.test_round5_performance_v2", "tests.test_round5_performance_v2")
        new = new.replace("round5_performance_v2", "round5_performance")
        self.assertEqual(new, old)

    def test_same_payload_schema_addition_passes_but_original_failure_axes_still_fail(self):
        self.assertTrue(fixture()["validation"]["passed"])
        def row(report):
            return report["workers"][1]["configurations"][0]["rows"][0]
        mutations = {
            "full_payload": lambda x: row(x).update(payload_sha256="a" * 64),
            "metadata": lambda x: row(x)["invariants"].update(metadata_error=1),
            "scope": lambda x: row(x)["invariants"].update(source_scope_errors=1),
            "source": lambda x: row(x).update(engine_source_sha256="0" * 64),
            "cache": lambda x: row(x).update(cache_rows_before=1),
            "chars": lambda x: row(x).update(context_chars=4001),
            "token": lambda x: row(x)["tokens"]["cl100k_base"].update(context=-1),
            "order": lambda x: x["workers"][1]["configurations"][0]["rows"].reverse(),
            "missing_worker": lambda x: x["workers"].pop(),
            "failed": lambda x: x.update(error={"type": "fixture"}),
        }
        for name, mutate in mutations.items():
            with self.subTest(axis=name):
                value = fixture()
                mutate(value)
                self.assertFalse(bench.validation(value)["passed"])

    def test_all_original_numeric_and_resource_gates_remain_required(self):
        report = fixture()
        compared = bench.comparisons(report)
        self.assertTrue(bench.acceptance(report, compared)["accepted"])
        slow = fixture(1.01)
        self.assertFalse(bench.acceptance(slow, bench.comparisons(slow))["numeric_gate_passed"])
        for suffix in ("native-char4000", "mcp-char4000", "native-char100000"):
            altered = copy.deepcopy(compared)
            cell = next(c for c in altered if c["cohort"] == "public1015" and c["id"] == suffix)
            cell["candidate"]["latency"]["p95_ms"] = cell["baseline"]["latency"]["p95_ms"] * 1.06
            cell["candidate_change_percent"]["p95_ms"] = 6.0
            with self.subTest(cell=suffix):
                self.assertFalse(bench.acceptance(report, altered)["numeric_gate_passed"])
        for worker in report["workers"]:
            if worker["label"] == "candidate":
                worker["mcp_sessions"]["mcp-token1024"]["mcp_startup_to_initialize_ms"] *= 1.11
        decision = bench.acceptance(report, compared)
        self.assertTrue(decision["numeric_gate_passed"])
        self.assertFalse(decision["accepted"])
        self.assertTrue(any(r["metric"] == "mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms"
                            for r in decision["resource_review"]))

    def test_every_raw_started_finished_row_still_matches_immutable_worker(self):
        report = fixture()
        worker = report["workers"][0]
        raw = ledger_bytes(worker)
        self.assertEqual(bench.verify_worker(worker, report["run"], report["plan"], ledger=raw), 14)
        with self.assertRaisesRegex(ValueError, "ledger bytes changed"):
            bench.verify_worker(worker, report["run"], report["plan"], ledger=raw[:-1])

    def test_reports_preserve_actual_schema_and_nonzero_token_delta(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json.gz"
            bench.save_report(path, report)
            saved = json.loads(gzip.decompress(path.read_bytes()))
            summary = json.loads(path.with_name("report.summary.json").read_bytes())
            self.assertEqual(saved["interface_initialization"], summary["interface_initialization"])
            self.assertEqual(saved["workers"][1]["mcp_tool_schema_json"], report["workers"][1]["mcp_tool_schema_json"])
            self.assertGreater(summary["interface_initialization"]["candidate_minus_baseline"]["cl100k_base"]["tool_schema"], 0)

    def test_unclaimed_formal_controller_and_worker_are_not_local_bypasses(self):
        with patch.object(bench, "host_identity") as host:
            with self.assertRaisesRegex(ValueError, "hosted execution claim"):
                bench.controller(SimpleNamespace(publish_branch=None), {}, {})
            host.assert_not_called()
        with self.assertRaisesRegex(ValueError, "preserved hosted publication and execution claim"):
            bench.verify_worker_claim(SimpleNamespace(), {}, {}, {})


if __name__ == "__main__":
    unittest.main()
