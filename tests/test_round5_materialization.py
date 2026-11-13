"""Fresh public-response fixtures for round-five candidate materialization.

The expected signatures were captured from the released v0.3.2 store before
implementing candidate A, using only the invented records below. All response
fields except latency are checked. Scores are checked separately with a tight
tolerance so SQLite/compiler rounding does not make the cross-platform fixture
brittle. No test depends on Git history or a measured benchmark corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
BASELINE_STORE_SHA256 = "090174302619d06baeccb8d3266ff4fad5ef033d30b63cd709d88d2b3dd73835"


def fixture_sources():
    definitions = [
        ("lab", "orbiting", "flight", "Flight records", "Relay observations",
         "2024-01-01T00:00:00Z", "The relay is orbiting the quiet moon. Orbiting relay calibration is stable. " +
         "The technician preserved the original flight observation and its supporting notes. " * 26),
        ("lab", "orbits", "flight", "Flight records", "Relay observations",
         "2024-02-01T00:00:00Z", "The relay orbits the quiet moon. The receiver uses a blue channel."),
        ("lab", "orbit", "flight", "Flight records", "Relay observations",
         "2024-03-01T00:00:00Z", "The relay orbit changed after inspection. A second orbit register is archived."),
        ("lab", "receiver", "receiver", "Receiver tolerance", "Receiver observations",
         "2024-04-01T00:00:00Z", "Receiver tolerance is 0.7 decibels. The receiver is stored in a sealed case."),
        ("lab", "policy-old", "policy", "Relay calibration", "Calibration log",
         "2023-01-01T00:00:00Z", "The relay calibration threshold is 41 millivolts. Record this approved threshold."),
        ("lab", "policy-new", "policy", "Relay calibration", "Calibration log",
         "2025-01-01T00:00:00Z", "The relay calibration threshold is 43 millivolts. Record this approved threshold."),
        ("lab", "tie-a", "identifiers", "Identifier records", "Cabinet inventory",
         "2024-05-01T00:00:00Z", "The qzx17 instrument is held in cabinet 12."),
        ("lab", "tie-b", "identifiers", "Identifier records", "Cabinet inventory",
         "2024-05-01T00:00:00Z", "The qzx17 instrument is held in cabinet 12."),
        ("lab", "chinese", "access", "访问设置", "缓存记录",
         "2024-06-01T00:00:00Z", "缓存有效期是四十秒。缓存失效后重新读取原始记录。接收器公差是零点七分贝。"),
        ("outside", "orbits", "flight", "Flight records", "Relay observations",
         "2025-02-01T00:00:00Z", "Orbiting relay calibration belongs to an unrelated station. Its threshold is 99 millivolts."),
    ]
    return [
        {"project": project, "session_id": sid, "task_id": task,
         "task_title": task_title, "title": title, "created_at": created,
         "messages": [
             {"role": "user", "content": "Recorded instrument observation"},
             {"role": "assistant", "content": body},
             {"role": "user", "content": "Supplementary archive note"},
             {"role": "assistant", "content": "Keep the original instrument manual available for inspection."},
         ]}
        for project, sid, task, task_title, title, created, body in definitions
    ]


def seed(book):
    return {(source["project"], source["session_id"]): book.ingest(source)
            for source in fixture_sources()}


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


def signature(response):
    payload = stable(response)
    scores = [item["score"] for item in payload["results"]]
    payload["results"] = [
        {key: value for key, value in item.items() if key != "score"}
        for item in payload["results"]
    ]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {"payload_sha256_without_scores": digest, "scores": scores}


EXPECTED = {'fused-char4000': {'payload_sha256_without_scores': '347d59e5a9ffa5037f7408237bb3e4ba3502cefe717e48640ff0818292487fc9',
                    'scores': [2.5046767024308014,
                               1.953642462623987,
                               1.7467330269378745,
                               1.0963646308153454,
                               1.0963646308153454]},
 'fused-char100000': {'payload_sha256_without_scores': '3a63596913502bb4b9772824659be4f86ba226ea2ec6d97fb9e5a26d9bdd75a5',
                      'scores': [2.5046767024308014,
                                 1.953642462623987,
                                 1.7467330269378745,
                                 1.0963646308153454,
                                 1.0963646308153454]},
 'identical-routes': {'payload_sha256_without_scores': '0874a63b8197b4d3a7d9fcfd5a4b60939a0c6f997656d809a2986541efbee516',
                      'scores': [4.847121633161934, 4.847121633161934]},
 'single-chinese': {'payload_sha256_without_scores': '954eb3c002765054d8d64b4bc7ecc35ec62cd455285ba99f9feb69f172c2cfe8',
                    'scores': [21.247576703470042]},
 'single-flat': {'payload_sha256_without_scores': 'fb703136c3254c079a250a1b738f0d398e9e52cfac30753da0ad61a3d8bf33e9',
                 'scores': [2.265268380718882,
                            0.9367898354282952,
                            0.9367898354282952,
                            0.9257492969949258,
                            0.9257492969949258]},
 'chapter-scope': {'payload_sha256_without_scores': 'dedfe5cc1a0269a6b7a31f8565ef7df94e286ab7a9a30e452251ae08dc09bf36',
                   'scores': [2.5046767024308014, 1.953642462623987, 1.7467330269378745]},
 'session-scope': {'payload_sha256_without_scores': '33f386f5e988a2c5704216c95db3a60141989b6e88c7732c26160b28930363b9',
                   'scores': [3.212478160047448, 1.43821875644367]},
 'combined-scope': {'payload_sha256_without_scores': 'bc4c09700225477bbb7afe329002cab9d565cb3d826cb538d75002bccfca3d09',
                    'scores': [0.9951804942695452]},
 'absent-scope': {'payload_sha256_without_scores': 'f8e31dc3cb6159c34b35dba418f9f860b213c60a97ed26e8d405be87702c59cc',
                  'scores': []},
 'current': {'payload_sha256_without_scores': 'd67cb25169992d0f1977f29dc8a3bc19e8ff640db8e074ef3ff44b315ee238a0',
             'scores': [9.3222076562574,
                        9.3222076562574,
                        0.9796916129704024,
                        0.9720367618446721,
                        0.9720367618446721]},
 'historical': {'payload_sha256_without_scores': '13075220d84c30f28ba372a1f3cf1ddc9813f10fe20071ae6dc06767e3bd884a',
                'scores': [9.110339300433367,
                           9.110339300433367,
                           0.9680321782378902,
                           0.9604648956322356,
                           0.9604648956322356]},
 'coverage': {'payload_sha256_without_scores': '6b59eb4ed13070ba42c46251371f80846cdfe4df8a99accfa608c7df9ad94b41',
              'scores': [11.59565418887478, 8.983218286938948, 8.983218286938948]},
 'cl100k_base-512': {'payload_sha256_without_scores': 'db82c74e0e9c628776f09bf618021fab5f3804178dda792b27982fc7527d5b59',
                     'scores': [2.5046767024308014, 1.953642462623987, 1.7467330269378745]},
 'cl100k_base-1024': {'payload_sha256_without_scores': 'c672cd4a86969b647ffc07bb30ebb6751e4c8a5ba5192967f667a81970101258',
                      'scores': [2.5046767024308014,
                                 1.953642462623987,
                                 1.7467330269378745,
                                 1.0963646308153454,
                                 1.0963646308153454]},
 'cl100k_base-2048': {'payload_sha256_without_scores': '7b2f114cdf70217925f9e09bb70ba2a1374e6d512ea6b183e131ca1b938f0b95',
                      'scores': [2.5046767024308014,
                                 1.953642462623987,
                                 1.7467330269378745,
                                 1.0963646308153454,
                                 1.0963646308153454]},
 'o200k_base-512': {'payload_sha256_without_scores': 'b365b9c2b1635527948a9027c84e8d9dabd587ea1c97e0b5be1d324240ab1b44',
                    'scores': [2.5046767024308014, 1.953642462623987, 1.7467330269378745]},
 'o200k_base-1024': {'payload_sha256_without_scores': '0c263da20070e7c670386b5a8ca79d1bf7ab5a0416e96f5a2d58116e2048117d',
                     'scores': [2.5046767024308014,
                                1.953642462623987,
                                1.7467330269378745,
                                1.0963646308153454,
                                1.0963646308153454]},
 'o200k_base-2048': {'payload_sha256_without_scores': 'f2c6a386635e213f3caa1c9d7f5ca50c10817406015b0ceb800a160c4a9039a2',
                     'scores': [2.5046767024308014,
                                1.953642462623987,
                                1.7467330269378745,
                                1.0963646308153454,
                                1.0963646308153454]},
 'renamed-directory': {'payload_sha256_without_scores': '7b74628a6fec8d98da1025dd1b5fe84737f18fb9ae6f1ae0d1e851a7b7b55712',
                       'scores': [3.083974304508117,
                                  2.691310229795722,
                                  2.63002061488299,
                                  1.5025863671797013,
                                  1.5025863671797013]}}


def scenarios(records):
    return {
        "fused-char4000": ("orbiting relay", {"project": "lab", "budget_chars": 4000}),
        "fused-char100000": ("orbiting relay", {"project": "lab", "budget_chars": 100000}),
        "identical-routes": ("qzx17", {"project": "lab", "budget_chars": 100000}),
        "single-chinese": ("缓存有效期", {"project": "lab", "budget_chars": 4000}),
        "single-flat": ("orbiting relay", {"project": "lab", "strategy": "flat"}),
        "chapter-scope": ("orbiting relay", {"chapter": records[("lab", "orbit")]["chapter_id"]}),
        "session-scope": ("orbiting relay", {"session": "orbits"}),
        "combined-scope": ("orbiting relay", {"project": "lab", "session": "orbits"}),
        "absent-scope": ("orbiting relay", {"project": "missing"}),
        "current": ("current relay calibration threshold", {"project": "lab"}),
        "historical": ("original relay calibration threshold", {"project": "lab"}),
        "coverage": ("relay calibration threshold and receiver tolerance",
                     {"project": "lab", "coverage": True, "limit": 3, "budget_chars": 1100}),
    }


class RowLike:
    """A supported row-shaped object with name and integer indexing."""

    def __init__(self, cursor, values):
        self.names = tuple(column[0] for column in cursor.description)
        self.values = values

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[key if isinstance(key, int) else self.names.index(key)]

    def __iter__(self):
        return iter(self.values)


class NamedLookupRow(sqlite3.Row):
    """A Row subclass whose mapping view intentionally differs from iteration."""

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if key == "chapter_title":
            return "orbiting relay " + value
        if key == "rank":
            return value * 2
        return value

    def __iter__(self):
        raise AssertionError("A Row subclass must retain its named mapping lookups")


class CandidateMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        self.records = seed(self.book)

    def assert_fixture(self, name, response):
        actual, expected = signature(response), EXPECTED[name]
        self.assertEqual(actual["payload_sha256_without_scores"],
                         expected["payload_sha256_without_scores"])
        self.assertEqual(len(actual["scores"]), len(expected["scores"]))
        for actual_score, expected_score in zip(actual["scores"], expected["scores"]):
            self.assertAlmostEqual(actual_score, expected_score,
                                   delta=max(1e-15, abs(expected_score) * 1e-12))

    def call_scenario(self, name):
        query, options = scenarios(self.records)[name]
        response = self.book.recall(query, use_cache=False, **options)
        self.assert_fixture(name, response)
        return response

    def test_fused_routes_repeated_directories_keep_complete_responses(self):
        for name in ("fused-char4000", "fused-char100000"):
            with self.subTest(name=name):
                response = self.call_scenario(name)
                sessions = {ref["session_id"] for hit in response["results"]
                            for ref in hit["source_refs"]}
                self.assertIn("orbiting", sessions)
                self.assertIn("orbits", sessions)

    def test_identical_routes_retain_scores_and_deterministic_ties(self):
        response = self.call_scenario("identical-routes")
        self.assertEqual(len(response["results"]), 2)
        self.assertEqual([hit["id"] for hit in response["results"]],
                         sorted(hit["id"] for hit in response["results"]))
        self.assertEqual(response["results"][0]["score"], response["results"][1]["score"])

    def test_single_route_chinese_and_flat_keep_complete_responses(self):
        for name in ("single-chinese", "single-flat"):
            with self.subTest(name=name):
                statements = []
                self.book.db.set_trace_callback(statements.append)
                try:
                    self.call_scenario(name)
                finally:
                    self.book.db.set_trace_callback(None)
                self.assertFalse(any("pages_stem_fts" in statement for statement in statements))

    def test_scopes_retain_external_session_disambiguation(self):
        for name in ("chapter-scope", "session-scope", "combined-scope", "absent-scope"):
            with self.subTest(name=name):
                response = self.call_scenario(name)
                if name == "combined-scope":
                    self.assertTrue(all(ref["project"] == "lab" and ref["session_id"] == "orbits"
                                        for hit in response["results"] for ref in hit["source_refs"]))
                if name == "absent-scope":
                    self.assertEqual(response["results"], [])

    def test_temporal_and_clause_coverage_keep_complete_responses(self):
        current = self.call_scenario("current")
        self.assertEqual(current["results"][0]["source_refs"][0]["session_id"], "policy-new")
        self.call_scenario("historical")
        covered = self.call_scenario("coverage")
        self.assertIn("Receiver tolerance is 0.7 decibels.", covered["context"])

    def test_directory_rename_changes_only_the_new_call(self):
        before = self.call_scenario("fused-char4000")
        source = next(source for source in fixture_sources() if source["session_id"] == "orbit")
        self.book.ingest({**source, "title": "Orbiting relay", "task_title": "Orbiting relay calibration"})
        after = self.book.recall("orbiting relay", project="lab", use_cache=False)
        self.assert_fixture("renamed-directory", after)
        self.assertGreater(after["revision"], before["revision"])
        self.assertNotEqual(after["results"], before["results"])

    def test_generic_row_shape_preserves_the_default_factory_response(self):
        expected = stable(self.call_scenario("fused-char4000"))
        self.book.db.row_factory = RowLike
        actual = stable(self.book.recall("orbiting relay", project="lab", use_cache=False))
        self.assertEqual(actual, expected)

    def test_row_subclasses_keep_named_lookup_for_routes_and_metadata(self):
        # Exercise both conversions independently. The original dict(Row)
        # conversion honors __getitem__; a value-iteration shortcut does not.
        for boundary in ("route", "metadata"):
            with self.subTest(boundary=boundary):
                options = {"project": "lab", "session": "orbiting", "use_cache": False,
                           "strategy": "flat" if boundary == "route" else "book"}
                expected = stable(self.book.recall("orbiting relay", **options))

                def row_factory(cursor, values):
                    names = {column[0] for column in cursor.description}
                    selected = ("rank" in names if boundary == "route"
                                else "chapter_title" in names and "rank" not in names)
                    return (NamedLookupRow if selected else sqlite3.Row)(cursor, values)

                self.book.db.row_factory = row_factory
                try:
                    actual = stable(self.book.recall("orbiting relay", **options))
                finally:
                    self.book.db.row_factory = sqlite3.Row
                self.assertEqual(len(actual["results"]), len(expected["results"]))
                for actual_hit, expected_hit in zip(actual["results"], expected["results"]):
                    expected_hit["breadcrumb"][1]["title"] = (
                        "orbiting relay " + expected_hit["breadcrumb"][1]["title"])
                    original_score = expected_hit.pop("score")
                    # Flat route mapping doubles its rank. The metadata-only
                    # mapping adds both query words to the directory: overlap
                    # changes from one of two words to both, without rank edits.
                    expected_score = (original_score * 2 if boundary == "route"
                                      else original_score / 1.075 * 1.15)
                    self.assertAlmostEqual(actual_hit.pop("score"), expected_score,
                                           delta=max(1e-15, abs(expected_score) * 1e-12))
                self.assertEqual(actual, expected)

    @unittest.skipUnless(HAS_TOKENS, "tiktoken is optional")
    def test_both_tokenizers_preserve_budgeted_payloads(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (512, 1024, 2048):
                with self.subTest(tokenizer=tokenizer, budget=budget):
                    response = self.book.recall("orbiting relay", project="lab", budget_chars=8000,
                                                budget_tokens=budget, tokenizer=tokenizer, use_cache=False)
                    self.assert_fixture(f"{tokenizer}-{budget}", response)
                    self.assertLessEqual(response["context_tokens"], budget)

    def test_concurrent_rename_keeps_metadata_and_sources_in_one_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with MemoryBook(path, segmentation="turn", max_page_chars=3000,
                            min_page_chars=0, cache_size=0) as reader:
                seed(reader)
                expected = stable(reader.recall("orbiting relay", project="lab", use_cache=False))
                with MemoryBook(path, segmentation="turn", max_page_chars=3000,
                                min_page_chars=0, cache_size=0) as writer:
                    original_tokens = reader._directory_tokens
                    committed = False
                    source = next(source for source in fixture_sources() if source["session_id"] == "orbit")

                    def rename_during_score(text):
                        nonlocal committed
                        if not committed:
                            writer.ingest({**source, "title": "Orbiting relay",
                                           "task_title": "Orbiting relay calibration"})
                            committed = True
                        return original_tokens(text)

                    with patch.object(reader, "_directory_tokens", side_effect=rename_during_score):
                        actual = stable(reader.recall("orbiting relay", project="lab", use_cache=False))
                    self.assertTrue(committed)
                    self.assertEqual(actual, expected)
                    fresh = reader.recall("orbiting relay", project="lab", use_cache=False)
                    self.assertGreater(fresh["revision"], actual["revision"])
                    self.assertNotEqual(fresh["results"], actual["results"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
