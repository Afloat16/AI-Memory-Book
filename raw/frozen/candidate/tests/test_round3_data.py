"""Artificial IDs, Git identities and Parquet only; no real source is opened."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import round3_data as data


def model_plan():
    return {"model": {
        "repository": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        "files": [
            {"path": "onnx/model_quint8_avx2.onnx", "bytes": 118453870,
             "sha256": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"},
            {"path": "tokenizer.json", "bytes": 9081518,
             "sha256": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"}],
        "dimensions": 384, "max_sequence_tokens": 128}, "index": {"overlap_tokens": 32}}


def source_spec(ids):
    return {"dataset": "Artificial fixture only", "source_url": "https://example.invalid/fixture",
        "source_revision": "fixture", "upstream_bytes": 1, "upstream_sha256": data.sha(b"x"),
        "upstream_rows": len(ids), "canonical_sha256": data.sha(b"historical provenance"),
        "canonical_bytes": 42, "license": "fixture", "license_source": "https://example.invalid/license",
        "expected_queries": 128, "selected_ids": ids[:128]}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(data, "ROOT", self.root).start()
        self.blobs = {}
        self.evaluator = "a" * 40
        self.candidate = "b" * 40
        self.candidate_hash = "c" * 64
        self.ids = [f"fixture-{index:04d}" for index in range(700)]
        source = source_spec(self.ids)
        prior = {"expected_queries": 256, "selected_ids": self.ids[128:384]}
        old = {data.ORIGINAL: data.canonical(source), data.PRIOR: data.canonical(prior),
               data.MODEL_PLAN: data.canonical(model_plan())}
        old.update({path: data.canonical({"lock": path}) for path in sorted(data.LOCK_PATHS)})
        for index in range(58 - len(old)):
            old[f"benchmarks/fixture_helper_{index}.py"] = b"# artificial frozen helper\n"
        historical = {name: data.sha(raw) for name, raw in old.items()}
        for name, raw in old.items():
            self.write(name, raw)
            self.blobs[data.BASELINE, name] = raw
        history = data.canonical({"historical_files_sha256": historical})
        self.write(data.HISTORICAL, history)
        self.blobs[data.BASELINE, data.HISTORICAL] = history
        self.write(data.LEGACY_EXTRA, b"# artificial legacy projection\n")
        self.blobs[data.BASELINE, data.LEGACY_EXTRA] = (self.root / data.LEGACY_EXTRA).read_bytes()
        plan = {"baseline": {"commit": data.BASELINE, "runtime_sha256": data.BASELINE_HASH},
            "independent_validation": {"cohort": {"count": data.COUNT, "selection_prefix": data.PREFIX}}}
        self.write(data.PLAN, data.canonical(plan))
        self.blobs[data.PLAN_COMMIT, data.PLAN] = data.canonical(plan)
        for name in data.NEW_EVALUATORS:
            self.write(name, b"# artificial new evaluator\n")
        names = [*old, data.LEGACY_EXTRA, data.PLAN, *data.NEW_EVALUATORS]
        files = {name: data.sha((self.root / name).read_bytes()) for name in names}
        for name in names:
            self.blobs[self.evaluator, name] = (self.root / name).read_bytes()
        self.binding = {"schema_version": 1, "status": "frozen-before-selection",
            "plan_sha256": data.sha(data.canonical(plan)),
            "baseline": {"commit": data.BASELINE, "source_sha256": data.BASELINE_HASH},
            "candidate": {"commit": self.candidate, "source_sha256": self.candidate_hash},
            "optional_semantic": True, "optional_project_statistics": False,
            "upstream_locks": {str(index): name for index, name in enumerate(sorted(data.LOCK_PATHS))},
            "evaluator_commit": self.evaluator, "evaluator_files": files,
            "model": {"identity": data.model_identity(model_plan()), "fingerprint": data.MODEL_FINGERPRINT}}
        self.binding_path = self.root / data.BINDING
        self.save_binding()
        patch.object(data, "git", side_effect=self.git).start()
        patch.object(data, "runtime_hash", side_effect=lambda commit:
                     data.BASELINE_HASH if commit == data.BASELINE else self.candidate_hash).start()

    def write(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def save_binding(self, committed=True):
        raw = data.canonical(self.binding)
        self.write(data.BINDING, raw)
        if committed:
            self.blobs["HEAD", data.BINDING] = raw

    def git(self, *args):
        if args[0] == "show":
            ref, name = args[1].split(":", 1)
            if (ref, name) not in self.blobs:
                raise ValueError("Artificial commit does not contain requested file")
            return self.blobs[ref, name]
        if args[0] == "rev-parse":
            return (args[1].split("^")[0] + "\n").encode()
        raise AssertionError("Unexpected Git operation")

    def test_complete_binding_accepts_only_artificial_committed_identities(self):
        result = data.registered_inputs(self.binding_path)
        self.assertEqual(result.binding_sha256, data.sha(self.binding_path.read_bytes()))
        self.assertEqual(result.source["selected_ids"], self.ids[:128])
        self.assertEqual(result.prior["selected_ids"], self.ids[128:384])

    def test_uncommitted_binding_and_evaluator_edits_are_rejected(self):
        self.binding["optional_project_statistics"] = True
        self.save_binding(committed=False)
        with self.assertRaisesRegex(ValueError, "Commit the exact file"):
            data.registered_inputs(self.binding_path)
        self.save_binding()
        self.write(data.NEW_EVALUATORS[0], b"# uncommitted modification\n")
        with self.assertRaisesRegex(ValueError, "Changed or uncommitted evaluator"):
            data.registered_inputs(self.binding_path)

    def test_missing_legacy_or_new_entry_and_self_references_fail(self):
        for missing in (data.LEGACY_EXTRA, data.NEW_EVALUATORS[2], data.ORIGINAL):
            saved = self.binding["evaluator_files"].pop(missing)
            self.save_binding()
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "Incomplete evaluator"):
                data.registered_inputs(self.binding_path)
            self.binding["evaluator_files"][missing] = saved
        for name in (data.BINDING, data.MANIFEST):
            self.binding["evaluator_files"][name] = "1" * 64
            self.save_binding()
            with self.subTest(cycle=name), self.assertRaisesRegex(ValueError, "own evaluator"):
                data.registered_inputs(self.binding_path)
            del self.binding["evaluator_files"][name]

    def test_changed_source_model_and_upstream_lock_are_rejected(self):
        mutations = [
            (lambda value: value["candidate"].update(source_sha256="d" * 64), "Runtime commit/hash"),
            (lambda value: value["model"]["identity"].update(dimensions=385), "Bound model"),
            (lambda value: value["upstream_locks"].update({"0": "different-lock.json"}), "Upstream component"),
            (lambda value: value.update(optional_semantic=False), "Optional mode")]
        original = copy.deepcopy(self.binding)
        for mutation, message in mutations:
            self.binding = copy.deepcopy(original)
            mutation(self.binding)
            self.save_binding()
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                data.registered_inputs(self.binding_path)

    def test_same_digest_in_binding_cannot_replace_frozen_helper(self):
        name = next(name for name in self.binding["evaluator_files"] if "fixture_helper" in name)
        raw = b"# different but coherently rebound content\n"
        self.write(name, raw)
        self.blobs[self.evaluator, name] = raw
        self.binding["evaluator_files"][name] = data.sha(raw)
        self.save_binding()
        with self.assertRaisesRegex(ValueError, "Frozen evaluator identity"):
            data.registered_inputs(self.binding_path)

    def test_git_committed_manifest_and_safe_paths(self):
        name = data.MANIFEST
        self.write(name, b"{}\n")
        with self.assertRaisesRegex(ValueError, "Artificial commit"):
            data.committed_bytes(self.root / name)
        self.blobs["HEAD", name] = b"{}\n"
        self.assertEqual(data.committed_bytes(self.root / name), b"{}\n")
        self.write(name, b"{\"changed\":true}\n")
        with self.assertRaisesRegex(ValueError, "Commit the exact file"):
            data.committed_bytes(self.root / name)
        for unsafe in ("../escape", "/absolute", "a/../b", "a//b"):
            with self.subTest(path=unsafe), self.assertRaises(ValueError):
                data.file_path(unsafe)


class SelectionTests(unittest.TestCase):
    def test_deterministic_id_order_exclusion_and_hash_collision_tiebreak(self):
        ids = ["z", "b", "a", "old"]
        expected = sorted(ids[:3], key=lambda value: (hashlib.sha256(("prefix" + value).encode()).hexdigest(), value))[:2]
        self.assertEqual(data.select_ids(ids, ["old"], "prefix", 2), expected)
        self.assertEqual(data.select_ids(list(reversed(ids)), ["old"], "prefix", 2), expected)
        with patch.object(data, "sha", return_value="collision"):
            self.assertEqual(data.select_ids(ids, ["old"], "prefix", 2), ["a", "b"])

    def test_invalid_ids_exclusion_overlap_and_insufficient_pool_fail(self):
        for ids, excluded, count in ((["a", "a"], [], 1), (["a", None], [], 1),
                (["a", ""], [], 1), (["a", "b"], ["a", "a"], 1),
                (["a", "b"], ["missing"], 1), (["a", "b"], ["a"], 2),
                (["a", "b"], [], True)):
            with self.subTest(ids=ids, excluded=excluded), self.assertRaises(ValueError):
                data.select_ids(ids, excluded, "prefix", count)

    def test_runtime_hash_matches_path_and_bytes_convention_without_import(self):
        commit = "c" * 40
        blobs = {"src/memory_book/z.py": b"raise RuntimeError('must not import')\n",
                 "src/memory_book/a.py": b"# a\n"}
        expected = hashlib.sha256()
        for name in sorted(blobs):
            expected.update(name.removeprefix("src/memory_book/").encode() + b"\0" + blobs[name] + b"\0")
        def git(*args):
            if args[0] == "rev-parse":
                return (commit + "\n").encode()
            if args[0] == "ls-tree":
                return "\0".join([*blobs, "src/memory_book/non-python.txt", ""]).encode()
            return blobs[args[1].split(":", 1)[1]]
        with patch.object(data, "git", side_effect=git):
            self.assertEqual(data.runtime_hash(commit), expected.hexdigest())


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "optional PyArrow is needed for artificial Parquet")
class ParquetTests(unittest.TestCase):
    def setUp(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(data, "ROOT", self.root).start()
        self.ids = [f"artificial-{index:04d}" for index in range(700)]
        self.selected = data.select_ids(self.ids, self.ids[:384], data.PREFIX, data.COUNT)
        selected = set(self.selected)
        rows = []
        for identity in self.ids:
            # Invalid unselected text proves normalize/convert never receives it.
            included = identity in selected
            rows.append({"id": identity, "question": "Artificial question?" if included else None,
                "answer": "Artificial answer" if included else None,
                "type": "bridge", "level": "medium",
                "context": {"title": ["Support", "Distractor"],
                    "sentences": [["Original α sentence.", "Another original sentence."], ["Distractor retained."]]}
                    if included else None,
                "supporting_facts": {"title": ["Support", "Support", "Support"], "sent_id": [0, 0, 1]}
                    if included else None})
        self.parquet = self.root / "artificial.parquet"
        pq.write_table(pa.Table.from_pylist(rows), self.parquet, row_group_size=32)
        source = source_spec(self.ids)
        raw = self.parquet.read_bytes()
        source.update(upstream_sha256=data.sha(raw), upstream_bytes=len(raw))
        binding = {"evaluator_commit": "a" * 40,
            "baseline": {"commit": data.BASELINE, "source_sha256": data.BASELINE_HASH},
            "candidate": {"commit": "b" * 40, "source_sha256": "c" * 64},
            "model": {"fingerprint": data.MODEL_FINGERPRINT}, "evaluator_files": {}}
        self.inputs = data.Inputs({}, source, {"selected_ids": self.ids[128:384]}, binding,
                                  "1" * 64, "2" * 64, "3" * 64, "4" * 64)
        self.manifest = self.root / data.MANIFEST
        self.binding = self.root / data.BINDING

    def test_id_column_precedes_filtered_conversion_and_all_context_is_retained(self):
        import pyarrow.parquet as pq
        with patch.object(pq, "read_table", wraps=pq.read_table) as reader:
            dataset, summary = data.selected_dataset(self.parquet, self.inputs)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(reader.call_args_list[0].kwargs, {"columns": ["id"]})
        self.assertEqual(reader.call_args_list[1].kwargs,
            {"filters": [("id", "in", self.selected)], "columns": list(data.SOURCE_COLUMNS)})
        self.assertEqual([case.id for case in dataset.queries], self.selected)
        self.assertEqual(dataset.seed, 31061)
        self.assertEqual(dataset.variant, "hotpot_round3_unseen_selection_v1")
        self.assertEqual(summary["excluded_prior_queries"], 384)
        self.assertEqual(summary["prior_selection_overlap"], 0)
        self.assertEqual(summary["selected_context_count_distribution"], {"2": 256})
        self.assertEqual(summary["source_turns"], 768)
        self.assertEqual(summary["support_annotation_count"], 768)
        self.assertEqual(summary["required_evidence"], 512)
        self.assertEqual(summary["dataset_sha256"], dataset.fingerprint)
        self.assertTrue(all(session["messages"][0]["content"] == "Distractor retained."
                            for session in dataset.sessions[1::2]))

    def test_verified_byte_snapshot_survives_path_replacement_between_reads(self):
        import pyarrow.parquet as pq
        original = pq.read_table
        calls = []
        def read(*args, **kwargs):
            calls.append(kwargs)
            result = original(*args, **kwargs)
            if len(calls) == 1:
                self.parquet.write_bytes(b"replaced after ID read")
            return result
        with patch.object(pq, "read_table", side_effect=read):
            dataset, _ = data.selected_dataset(self.parquet, self.inputs)
        self.assertEqual(len(dataset.queries), 256)
        self.assertEqual(len(calls), 2)

    def test_file_hash_failure_prevents_any_parquet_decode(self):
        import pyarrow.parquet as pq
        self.parquet.write_bytes(b"changed bytes")
        with patch.object(pq, "read_table") as reader:
            with self.assertRaisesRegex(ValueError, "Parquet bytes"):
                data.selected_dataset(self.parquet, self.inputs)
        reader.assert_not_called()

    def test_wrong_or_duplicate_filtered_rows_fail_before_converter(self):
        import pyarrow.parquet as pq
        original = pq.read_table
        def read(*args, **kwargs):
            table = original(*args, **kwargs)
            return table.slice(0, 255) if "filters" in kwargs else table
        with patch.object(pq, "read_table", side_effect=read), patch.object(data, "normalize_hotpot") as normalize:
            with self.assertRaisesRegex(ValueError, "Filtered Parquet rows"):
                data.selected_dataset(self.parquet, self.inputs)
        normalize.assert_not_called()

    def test_freeze_load_requires_committed_manifest_and_recomputes_all_fields(self):
        with patch.object(data, "registered_inputs", return_value=self.inputs):
            value = data.freeze(self.parquet, self.binding, self.manifest)
            committed = self.manifest.read_bytes()
            with patch.object(data, "git", return_value=committed):
                dataset = data.load(self.parquet, self.binding, self.manifest)
                self.assertEqual(dataset.fingerprint, value["dataset_sha256"])
                for field, replacement in (("selected_ids", list(reversed(self.selected))),
                    ("selected_canonical_sha256", "f" * 64), ("required_evidence", 511),
                    ("source_turns", 767), ("excluded_prior_queries", 383)):
                    tampered = copy.deepcopy(value)
                    tampered[field] = replacement
                    self.manifest.write_bytes(data.canonical(tampered))
                    # Even a coherently committed altered manifest must fail recomputation.
                    with self.subTest(field=field), patch.object(data, "git", return_value=self.manifest.read_bytes()):
                        with self.assertRaisesRegex(ValueError, "Frozen selection"):
                            data.load(self.parquet, self.binding, self.manifest)
                self.manifest.write_bytes(data.canonical({**value, "binding_sha256": "f" * 64}))
                with self.assertRaisesRegex(ValueError, "Commit the exact file"):
                    data.load(self.parquet, self.binding, self.manifest)

    def test_overwrite_and_binding_mismatch_stop_before_private_input_read(self):
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_bytes(b"{}")
        with patch.object(data, "registered_inputs") as registered, patch.object(data, "selected_dataset") as selected:
            with self.assertRaises(FileExistsError):
                data.freeze(self.parquet, self.binding, self.manifest)
            registered.assert_not_called()
            selected.assert_not_called()
        wrong = {"binding_sha256": "f" * 64, "plan_sha256": self.inputs.plan_sha256}
        self.manifest.write_bytes(data.canonical(wrong))
        with patch.object(data, "registered_inputs", return_value=self.inputs), \
                patch.object(data, "git", return_value=self.manifest.read_bytes()), \
                patch.object(data, "selected_dataset") as selected:
            with self.assertRaisesRegex(ValueError, "different frozen binding"):
                data.load(self.parquet, self.binding, self.manifest)
            selected.assert_not_called()


if __name__ == "__main__":
    unittest.main()
