"""Protocol checks with artificial fixtures; these are not quality results."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import engineering_identifiers as bench


class IdentifierProtocolTests(unittest.TestCase):
    def test_original_source_and_conditional_class_selection(self):
        text = b'if enabled:\n    class HTTPServer:\n        """original-only clue"""\n        pass\n\ndef worker():\n    return 1\n'
        plan = {"protocol": "fixture", "upstream": {"paths": ["module.py"],
                "license_path": "LICENSE", "commit": "f" * 40}}
        data = bench.build_dataset({"module.py": text, "LICENSE": b"fixture license"}, plan)
        self.assertEqual(len(data["documents"]), 2)
        self.assertEqual(len(data["queries"]), 4)
        source = data["documents"][0]
        self.assertEqual(source["text"], text.decode().split("\n\ndef worker")[0].split("if enabled:\n")[1] + "\n")
        self.assertNotIn("HTTP Server", source["text"])
        self.assertEqual(data["queries"][1]["query"], "HTTP Server")
        self.assertEqual(source["source"]["start_line"], 2)

    def test_search_baseline_handles_acronym_and_rejects_fragment_as_full_name(self):
        docs = [
            {"id": "a", "project": "p", "text": "generic HTTP transport and server logs"},
            {"id": "b", "project": "p", "text": "class HTTPServer: pass"},
            {"id": "c", "project": "p", "text": "class HTTPServerless: pass"}]
        index = bench.raw_index(docs)
        for query in ("HTTPServer", "HTTP Server", "http server", "Where is HTTP Server defined?"):
            self.assertEqual(bench.raw_search(query, index, 3)[0], "b")

    def test_whole_block_budget_never_substitutes_a_later_source(self):
        class Characters:
            def encode(self, text):
                return list(text)
        docs = {"long": {"project": "p", "source": {"commit": "x"}, "text": "A" * 100},
                "short": {"project": "p", "source": {"commit": "x"}, "text": "b"}}
        ids, context, tokens = bench.pack(["long", "short"], docs, 40, Characters())
        self.assertEqual((ids, context, tokens), ([], "", 0))
        ids, context, tokens = bench.pack(["short"], docs, 40, Characters())
        self.assertEqual(ids, ["short"])
        self.assertLessEqual(tokens, 40)

    def test_missing_attempts_are_failures_in_fixed_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            dataset = root / "dataset.json"
            bench.write_json(plan, {"common_controls": {"repetitions": 3, "token_budgets": [1024]}})
            bench.write_json(dataset, {"queries": [{"id": "q1", "variant": "exact"},
                                                   {"id": "q2", "variant": "spaced"}]})
            bench.write_json(root / "attempts.json", [{"state": "missing", "returncode": 1}])
            binding = {"protocol": "fixture", "quality_calls": 30}
            with patch.object(bench, "PLAN", plan), patch.object(bench, "DATASET", dataset):
                report = bench.summarize(root, binding)
            self.assertFalse(report["completed"])
            self.assertFalse(report["bounded_numerical_gate_passed"])
            self.assertEqual(len(report["cells"]), 10)
            for cell in report["cells"]:
                self.assertEqual(cell["hit_rate"], 0)
                self.assertEqual(cell["expected_observations"], 3)
                self.assertEqual(cell["errors"], 3)
                self.assertIsNone(cell["mean_lookup_ms"])

    def test_intent_file_cannot_be_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binding.json"
            bench.write_json(path, {"first": True}, exclusive=True)
            with self.assertRaises(FileExistsError):
                bench.write_json(path, {"first": False}, exclusive=True)
            self.assertEqual(json.loads(path.read_text()), {"first": True})

    def test_source_cache_must_match_independent_upstream_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "lock.json"
            raw = b"original upstream source\n"
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            bench.write_json(lock, {"repository": "upstream", "commit": "a" * 40,
                "truncated": False, "files": [{"path": "x.py", "bytes": len(raw), "git_blob_sha": blob}]})
            plan = {"upstream": {"repository": "upstream", "commit": "a" * 40}}
            with patch.object(bench, "SOURCE_LOCK", lock):
                bench.verify_source_bytes({"x.py": raw}, plan)
                with self.assertRaisesRegex(ValueError, "Git blob"):
                    bench.verify_source_bytes({"x.py": raw.replace(b"original", b"modified")}, plan)

    def test_duplicate_completion_cannot_replace_missing_query_or_partial_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, dataset = root / "plan.json", root / "dataset.json"
            cases = [{"id": name, "query": name, "variant": variant, "expected_id": "doc"}
                     for name, variant in (("q1", "exact"), ("q2", "spaced"))]
            bench.write_json(plan, {"common_controls": {"repetitions": 1, "token_budgets": [1024]}})
            bench.write_json(dataset, {"queries": cases})
            stage = root / "stage"
            stage.mkdir()
            bench.write_json(root / "attempts.json", [{"state": "stage", "arm": "v0.3.4", "repetition": 0, "returncode": 0}])
            base = {"arm": "v0.3.4", "repetition": 0, "query_id": "q1"}
            bench.append(stage / "events.jsonl", {**base, "event": "started"})
            completed = {**base, "event": "completed", "query": "q1", "variant": "exact",
                "expected_id": "doc", "error": None, "lookup_wall_ms": 1,
                "scores": [{"budget_tokens": 1024, "hit": True, "top1": True,
                            "reciprocal_rank": 1, "context_tokens": 1, "budget_violation": False}]}
            bench.append(stage / "events.jsonl", completed)
            bench.append(stage / "events.jsonl", completed)
            with (stage / "events.jsonl").open("ab") as stream:
                stream.write(b'{"event":')
            with patch.object(bench, "PLAN", plan), patch.object(bench, "DATASET", dataset), patch.object(bench, "ARMS", ("v0.3.4", "round7-candidate")):
                report = bench.summarize(root, {"protocol": "fixture", "quality_calls": 4})
            self.assertFalse(report["completed"])
            self.assertEqual(report["observed_calls"], 1)
            self.assertEqual(len(report["protocol_errors"]), 2)
            self.assertEqual(report["missing_completed_cells"], 3)


if __name__ == "__main__":
    unittest.main()
