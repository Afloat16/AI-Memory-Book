"""Pure write-cost protocol checks; these do not open or time a memory archive."""

from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import v014_write_costs as costs


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def seal(location):
    completion = costs.read_json(location / "complete.json")
    completion["evidence_sha256"] = {name: hashlib.sha256((location / name).read_bytes()).hexdigest()
                                    for name in completion["evidence_sha256"]}
    save(location / "complete.json", completion)


def artifact_fixture(root):
    """Synthetic saved records only: no MemoryBook, SQLite, subprocess or timer."""
    sequence = costs.operations()
    binding = {"protocol": costs.PROTOCOL, "protocol_commit": "f" * 40,
               "protocol_files": {path: "f" * 64 for path in costs.PROTOCOL_PATHS},
               "backend": "native", "order": [list(pair) for pair in costs.ORDER],
               "executable": "/venv/bin/python", "python_prefix": "/venv", "python": "fixture-python",
               "runtime_roots": {arm: "/runtime/" + arm for arm in ("baseline", "candidate")}, "runtimes": {}}
    for arm, digit in (("baseline", "a"), ("candidate", "b")):
        files = {"src/memory_book/store.py": digit * 64}
        binding["runtimes"][arm] = {"commit": digit * 40, "runtime_files": files,
            "runtime_sha256": costs.digest(files), "native_files": {"_native.so": digit * 64}}
    save(root / "binding.json", binding)
    for number, order in enumerate(costs.ORDER):
        for arm in order:
            directory = root / f"round-{number:02}-{arm}"
            directory.mkdir()
            source = binding["runtimes"][arm]
            proof = {"source": source, "backend": binding["backend"],
                "native": {"path": f"/runtime/{arm}/src/memory_book/_native.so", "sha256": source["native_files"]["_native.so"]},
                "protocol_commit": binding["protocol_commit"], "protocol_files": binding["protocol_files"]}
            save(directory / "identity.json", {**proof, "protocol": costs.PROTOCOL, "arm": arm, "round": number,
                "environment": {"executable": binding["executable"], "prefix": binding["python_prefix"], "python": binding["python"]}})
            save(directory / "identity-after.json", proof)
            records = [{"stage": "initialize", "wall_ns": 10, "cpu_ns": 8, "resources": {}}]
            starts, revision = [{"stage": "initialize"}], 0
            for index, (stage, method, payload) in enumerate(sequence):
                labels = {"index": index, "stage": stage, "method": method, "request_sha256": costs.digest(payload)}
                starts.append(labels)
                if stage != "skip":
                    revision += 1
                if method in {"ingest", "link_session"}:
                    project, session = ((payload["project"], payload["session_id"]) if method == "ingest" else payload[:2])
                    response = {"project": project, "session_id": session, "pages": 32,
                                "revision": revision, "skipped": stage == "skip"}
                else:
                    response = True
                records.append({**labels, "response": response, "wall_ns": 10, "cpu_ns": 8, "resources": {}})
                if index + 1 == len(sequence) or sequence[index + 1][0] != stage:
                    pages = costs.STAGE_PAGES[stage]
                    tables = {name: {"rows": pages // 32 if name == "sessions" else pages, "sha256": "d" * 64}
                              for name in costs.SOURCE_COLUMNS}
                    snapshot = {"tables": tables, "revision": revision, "logical_sources_sha256": "c" * 64,
                        "combined_sha256": costs.digest(tables), "fts_term_column_statistics": {
                            name: {"rows": 10, "sha256": "e" * 64} for name in ("pages_fts", "pages_stem_fts")}}
                    save(directory / f"source-{stage}.json", {"stage": stage, "after_operation": index,
                                                              "source_snapshot": snapshot, "resources": {}})
            records.append({"stage": "close", "wall_ns": 10, "cpu_ns": 8, "resources": {}})
            starts.append({"stage": "close"})
            for name, values in (("operations.jsonl", records), ("operation-starts.jsonl", starts)):
                (directory / name).write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")
            names = {"identity.json", "identity-after.json", "operations.jsonl", "operation-starts.jsonl",
                     *(f"source-{stage}.json" for stage in costs.STAGE_PAGES)}
            save(directory / "complete.json", {"status": "complete", "protocol": costs.PROTOCOL,
                "operations": len(sequence), "initial_pages": 5120, "final_pages": 4544,
                "evidence_sha256": dict.fromkeys(names, "")})
            seal(directory)
            # This is deliberately not a SQLite database or generated memory.
            (directory / "working.db").write_text("PURE AUDITOR FIXTURE", encoding="utf-8")
            for label in ("stdout", "stderr"):
                (root / f"round-{number:02}-{arm}.{label}").write_bytes(b"")
            save(root / f"receipt-{number:02}-{arm}.json", {"round": number, "arm": arm, "returncode": 0,
                "stdout_sha256": hashlib.sha256(b"").hexdigest(), "stderr_sha256": hashlib.sha256(b"").hexdigest()})
    return binding


class WriteCostProtocolTests(unittest.TestCase):
    def test_real_source_workload_counts_and_project_boundaries(self):
        sources = costs.initial_sources()
        self.assertEqual(len(sources), 160)
        self.assertEqual(len({(source["project"], source["session_id"]) for source in sources}), 160)
        self.assertEqual(Counter(source["project"] for source in sources),
                         {f"worker-{project:03}": 8 for project in range(20)})
        self.assertEqual(sum(len(source["messages"]) // 2 for source in sources), 5120)
        self.assertTrue(all(len(source["messages"]) == 64 for source in sources))
        self.assertEqual(len({source["project"] for source in sources[:20]}), 20)
        self.assertNotEqual(sources[0]["messages"][1]["content"], sources[1]["messages"][1]["content"])

    def test_mutations_reference_existing_sources_and_preserve_final_counts(self):
        sequence = costs.operations()
        self.assertEqual(len(sequence), 206)
        self.assertEqual(Counter(stage for stage, _, _ in sequence),
                         {"ingest": 160, "skip": 20, "replacement": 10,
                          "relink": 5, "delete_session": 10, "delete_project": 1})
        active = {}
        for stage, _, payload in sequence:
            if stage in {"ingest", "skip", "replacement"}:
                identity = (payload["project"], payload["session_id"])
                if stage == "skip":
                    self.assertEqual(payload, active[identity])
                if stage == "replacement":
                    self.assertIn(identity, active)
                    self.assertNotEqual(payload["messages"], active[identity]["messages"])
                active[identity] = payload
            elif stage == "relink":
                self.assertIn(tuple(payload[:2]), active)
            elif stage == "delete_session":
                self.assertIn(tuple(payload), active)
                del active[tuple(payload)]
            else:
                self.assertTrue(any(project == payload[0] for project, _ in active))
                active = {key: value for key, value in active.items() if key[0] != payload[0]}
        self.assertEqual(len(active) * costs.TURNS_PER_SESSION, 4544)

    def test_plan_and_balanced_schedule_match_the_runner(self):
        path = Path(__file__).resolve().parents[1] / "benchmarks/experiments/v014-write-costs-plan.json"
        plan = json.loads(path.read_text())
        self.assertEqual(plan["protocol"], costs.PROTOCOL)
        self.assertEqual(plan["schedule"]["order"], [list(pair) for pair in costs.ORDER])
        self.assertEqual(plan["schedule"]["timed_mutation_calls"], 2 * len(costs.ORDER) * len(costs.operations()))
        self.assertEqual(Counter(pair[0] for pair in costs.ORDER), {"baseline": 2, "candidate": 2})
        self.assertEqual(plan["workload"]["operations_per_arm"], len(costs.operations()))
        self.assertEqual(plan["workload"]["expected_stage_pages"], costs.STAGE_PAGES)

    def test_generator_is_deterministic_and_query_free(self):
        self.assertEqual(costs.digest(costs.operations()), costs.digest(costs.operations()))
        self.assertEqual(costs.digest({"a": 1, "b": 2}), costs.digest({"b": 2, "a": 1}))
        self.assertTrue(all(method in {"ingest", "link_session", "delete_session", "delete_project"}
                            for _, method, _ in costs.operations()))

    def test_interpreter_normalization_preserves_the_venv_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "base-python"
            target.write_bytes(b"fixture")
            link = directory / "venv-python"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            relative = os.path.relpath(link)
            with patch.object(costs.sys, "executable", relative):
                self.assertEqual(costs.interpreter_path(), str(link))
                self.assertNotEqual(Path(costs.interpreter_path()).resolve(), Path(costs.interpreter_path()))


class WriteCostSavedAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binding = artifact_fixture(self.root)
        frozen = {key: self.binding[key] for key in ("protocol_commit", "protocol_files")}
        guard = patch.object(costs, "protocol_identity", return_value=frozen)
        guard.start()
        self.addCleanup(guard.stop)
        self.arm = self.root / "round-00-candidate"

    def test_valid_complete_fixture_has_all_operations_and_separate_close_costs(self):
        result = costs.summarize(self.root)
        self.assertEqual(result["total_operations"], 1648)
        self.assertEqual(result["source_equal_stage_pairs"], 24)
        self.assertEqual(len(result["wall_time_groups"]), 16)
        self.assertTrue(all(row["n"] == 4 for row in result["wall_time_groups"] if row["stage"] == "close"))
        self.assertTrue((self.arm / "working.db").exists())

    def test_resealed_wrong_request_identity_is_rejected(self):
        path = self.arm / "operations.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[1]["request_sha256"] = "0" * 64
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        seal(self.arm)
        with self.assertRaisesRegex(ValueError, "operation order, method, stage or request"):
            costs.summarize(self.root)

    def test_resealed_duplicate_operation_is_rejected_without_changing_record_count(self):
        path = self.arm / "operations.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[2] = copy.deepcopy(rows[1])
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        seal(self.arm)
        with self.assertRaisesRegex(ValueError, "operation order, method, stage or request"):
            costs.summarize(self.root)

    def test_resealed_source_or_native_drift_is_rejected(self):
        path = self.arm / "identity-after.json"
        original = costs.read_json(path)
        for change in ("source", "native", "protocol"):
            updated = copy.deepcopy(original)
            if change == "source":
                updated["source"]["commit"] = "0" * 40
            elif change == "native":
                updated["native"]["sha256"] = "0" * 64
            else:
                updated["protocol_files"][costs.PROTOCOL_PATHS[0]] = "0" * 64
            save(path, updated)
            seal(self.arm)
            with self.subTest(change=change), self.assertRaises(ValueError):
                costs.summarize(self.root)
        save(path, original)

    def test_equal_but_wrong_source_counts_are_not_accepted(self):
        for arm in ("baseline", "candidate"):
            directory = self.root / f"round-00-{arm}"
            path = directory / "source-ingest.json"
            record = costs.read_json(path)
            snapshot = record["source_snapshot"]
            snapshot["tables"]["pages"]["rows"] = 1
            snapshot["combined_sha256"] = costs.digest(snapshot["tables"])
            save(path, record)
            seal(directory)
        with self.assertRaisesRegex(ValueError, "source/FTS stage counts"):
            costs.summarize(self.root)

    def test_failed_process_and_interrupted_journal_retain_working_databases(self):
        receipt = self.root / "receipt-00-candidate.json"
        original = costs.read_json(receipt)
        save(receipt, {**original, "returncode": -15})
        with self.assertRaisesRegex(ValueError, "worker did not complete"):
            costs.cleanup_databases(self.root)
        self.assertEqual(len(list(self.root.glob("round-*/working.db"))), 8)
        save(receipt, original)
        path = self.arm / "operation-starts.jsonl"
        path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
        seal(self.arm)
        with self.assertRaisesRegex(ValueError, "missing or extra operation/start"):
            costs.cleanup_databases(self.root)
        self.assertEqual(len(list(self.root.glob("round-*/working.db"))), 8)

    def test_source_mismatch_blocks_cleanup_but_accepted_summary_allows_it(self):
        path = self.arm / "source-ingest.json"
        original = costs.read_json(path)
        changed = copy.deepcopy(original)
        changed["source_snapshot"]["logical_sources_sha256"] = "0" * 64
        save(path, changed)
        seal(self.arm)
        with self.assertRaisesRegex(ValueError, "original-source mismatch"):
            costs.cleanup_databases(self.root)
        self.assertEqual(len(list(self.root.glob("round-*/working.db"))), 8)
        save(path, original)
        seal(self.arm)
        save(self.root / "summary.json", costs.summarize(self.root))
        costs.cleanup_databases(self.root)
        self.assertFalse(list(self.root.glob("round-*/working.db")))
        self.assertTrue(costs.read_json(self.root / "working-databases-removed.json")["after_full_paired_acceptance"])

    def test_raw_record_changes_without_new_capture_hash_are_rejected(self):
        path = self.arm / "operations.jsonl"
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "captured evidence hash"):
            costs.summarize(self.root)


if __name__ == "__main__":
    unittest.main()
