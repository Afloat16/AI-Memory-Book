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
from types import SimpleNamespace
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


class DerivedMapMaterializationTests(unittest.TestCase):
    """Invented native rows retain duplicate values and observable failures."""

    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        for index in range(3):
            self.book.ingest({"project": "derived", "session_id": f"derived-{index}",
                "task_id": "instrument", "task_title": "Instrument archive",
                "title": "Relay notes", "created_at": "2024-01-01T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                    "The qzx17 relay calibration threshold is stable."}]})
        self.pages = [dict(row) for row in self.book.db.execute(
            "SELECT rid,id FROM pages ORDER BY id")]

    def route(self, entries):
        return [(self.pages[index]["rid"], self.pages[index]["id"], rank)
                for index, rank in entries]

    def recall_routes(self, exact, stem, *, row_type=sqlite3.Row, events=None,
                      metadata_error=None, batch_factory=None, **options):
        connection = self.book.db
        events = [] if events is None else events

        class RouteConnection:
            def __getattr__(self, name):
                return getattr(connection, name)

            def execute(self, statement, *arguments):
                if statement.startswith("SELECT p.rid,p.id,bm25("):
                    cursor = connection.execute(statement, *arguments)
                    name = "exact" if "bm25(pages_fts," in statement else "stem"
                    values = exact if name == "exact" else stem
                    rows = [row_type(cursor, row) for row in values]
                    cursor.close()
                    if batch_factory is not None:
                        rows = batch_factory(name, rows)
                    return SimpleNamespace(fetchall=lambda: rows)
                if statement.startswith("SELECT p.id,p.project_id,p.chapter_id,"):
                    events.append("metadata")
                    if metadata_error is not None:
                        raise metadata_error
                return connection.execute(statement, *arguments)

        self.book.db = RouteConnection()
        connection.row_factory = row_type
        try:
            return stable(self.book.recall("qzx17", project="derived", budget_chars=100000,
                                           use_cache=False, **options))
        finally:
            connection.row_factory = sqlite3.Row
            self.book.db = connection

    def test_duplicate_ids_keep_order_last_rank_and_final_scale(self):
        exact = self.route([(0, -100.0), (1, -4), (0, -2), (2, -1.0)])
        cases = [
            # Raw route sequences differ, but ordered deduplicated IDs agree.
            ("identical-keys", [(0, -3), (1, -1.0), (2, -2)], [4.0, 2.0, 1.0]),
            # The discarded -100 values must not enter either final scale.
            # Equal fused scores use the last exact ordinal, not first sight.
            ("fused-keys", [(1, -100), (0, -4.0), (1, 0), (2, -2)], [2.0, 2.0, 1.0]),
        ]
        for name, entries, scores in cases:
            with self.subTest(route=name):
                stem = self.route(entries)
                expected = self.recall_routes(exact, stem, row_type=RowLike)
                actual = self.recall_routes(exact, stem)
                self.assertEqual(actual, expected)
                self.assertEqual(actual["candidate_count"], 3)
                self.assertEqual([hit["id"] for hit in actual["results"]],
                                 [self.pages[index]["id"] for index in (1, 0, 2)])
                self.assertEqual([hit["score"] for hit in actual["results"]], scores)

    def test_later_nonprimitive_id_and_rank_keep_mapping_payload(self):
        class PageId(str):
            pass

        class ShiftedRank(float):
            def __neg__(self):
                return -float(self) * 3

        class UnequalType(type):
            def __eq__(cls, other):
                raise AssertionError("A rank's metaclass equality must not run")

        class OpaqueRank(metaclass=UnequalType):
            def __neg__(self):
                return 6.0

        for boundary in ("id", "rank", "bool-rank", "metaclass-rank"):
            with self.subTest(boundary=boundary):
                exact = self.route([(0, -2.0), (1, -1), (2, -0.5)])
                stem = self.route([(1, -3), (0, -1.0), (2, -2)])
                rid, page_id, rank = stem[-1]
                stem[-1] = (rid, PageId(page_id) if boundary == "id" else page_id,
                            ShiftedRank(rank) if boundary == "rank" else
                            False if boundary == "bool-rank" else
                            OpaqueRank() if boundary == "metaclass-rank" else rank)
                expected = self.recall_routes(exact, stem, row_type=RowLike)
                actual = self.recall_routes(exact, stem)
                self.assertEqual(actual, expected)
                self.assertEqual(actual["candidate_count"], 3)

    def test_later_rank_failure_precedes_metadata_and_rolls_back(self):
        class RankFailure(Exception):
            pass

        for row_type in (RowLike, sqlite3.Row):
            with self.subTest(row_type=row_type):
                events = []

                class FailingRank:
                    def __neg__(self):
                        events.append("rank-failure")
                        raise RankFailure("rank conversion precedes metadata")

                exact = self.route([(0, -2.0), (1, -1), (2, FailingRank())])
                stem = self.route([(0, -2.0), (1, -1), (2, -0.5)])
                with self.assertRaisesRegex(RankFailure, "precedes metadata"):
                    self.recall_routes(exact, stem, row_type=row_type, events=events,
                                       metadata_error=AssertionError("metadata ran first"))
                self.assertEqual(events, ["rank-failure"])
                self.assertFalse(self.book.db.in_transaction)

    def test_later_id_failure_precedes_rank_arithmetic_and_metadata(self):
        class IdFailure(Exception):
            pass

        for row_type in (RowLike, sqlite3.Row):
            with self.subTest(row_type=row_type):
                events = []

                class FailingId(str):
                    def __hash__(self):
                        events.append("id-failure")
                        raise IdFailure("all route IDs precede rank arithmetic")

                class FailingRank:
                    def __neg__(self):
                        events.append("rank-failure")
                        raise AssertionError("rank arithmetic ran first")

                exact = self.route([(0, FailingRank()), (1, -1), (2, -0.5)])
                stem = self.route([(0, -2.0), (1, -1), (2, -0.5)])
                rid, page_id, rank = stem[-1]
                stem[-1] = (rid, FailingId(page_id), rank)
                with self.assertRaisesRegex(IdFailure, "precede rank arithmetic"):
                    self.recall_routes(exact, stem, row_type=row_type, events=events,
                                       metadata_error=AssertionError("metadata ran first"))
                self.assertEqual(events, ["id-failure"])
                self.assertFalse(self.book.db.in_transaction)

    def test_custom_route_batch_keeps_original_exception_order(self):
        class BatchFailure(Exception):
            pass

        for row_type in (RowLike, sqlite3.Row):
            with self.subTest(row_type=row_type):
                events = []

                class ObservedBatch(list):
                    def __init__(self, name, values):
                        super().__init__(values)
                        self.name, self.iterations = name, 0

                    def __iter__(self):
                        events.append(self.name)
                        self.iterations += 1
                        if self.iterations == 2:
                            raise BatchFailure(self.name + " second pass")
                        return super().__iter__()

                exact = self.route([(0, -2.0), (1, -1), (2, -0.5)])
                stem = self.route([(1, -2.0), (0, -1), (2, -0.5)])
                with self.assertRaisesRegex(BatchFailure, "exact second pass"):
                    self.recall_routes(exact, stem, row_type=row_type, events=events,
                                       batch_factory=ObservedBatch,
                                       metadata_error=AssertionError("metadata ran first"))
                self.assertEqual(events, ["exact", "stem", "exact"])
                self.assertFalse(self.book.db.in_transaction)

    def test_extra_native_row_values_keep_named_route_and_metadata_payload(self):
        with self.subTest(boundary="dual-route-extra"):
            route = [(*row, -99.0) for row in self.route([(0, -2.0), (1, -1), (2, -0.5)])]
            expected = self.recall_routes(route, route, row_type=RowLike)
            actual = self.recall_routes(route, route)
            self.assertEqual(actual, expected)
            self.assertEqual([hit["score"] for hit in actual["results"]], [2.0, 1.0, 0.5])

        for boundary, strategy in (("single-route-extra", "flat"), ("metadata-extra", "book")):
            with self.subTest(boundary=boundary):
                def factory(row_type):
                    def build(cursor, values):
                        names = tuple(column[0] for column in cursor.description)
                        selected = ("rank" in names if boundary == "single-route-extra"
                                    else "chapter_title" in names and "rank" not in names)
                        return row_type(cursor, (*values, -99.0) if selected else values)
                    return build

                try:
                    self.book.db.row_factory = factory(RowLike)
                    expected = stable(self.book.recall("qzx17", project="derived", strategy=strategy,
                                                      budget_chars=100000, use_cache=False))
                    self.book.db.row_factory = factory(sqlite3.Row)
                    actual = stable(self.book.recall("qzx17", project="derived", strategy=strategy,
                                                    budget_chars=100000, use_cache=False))
                finally:
                    self.book.db.row_factory = sqlite3.Row
                self.assertEqual(actual, expected)
                self.assertEqual(actual["candidate_count"], 3)

    def test_missing_metadata_value_keeps_named_lookup_failure_and_rollback(self):
        for row_type in (RowLike, sqlite3.Row):
            for coverage in (False, True):
                with self.subTest(row_type=row_type, coverage=coverage):
                    def factory(cursor, values):
                        names = tuple(column[0] for column in cursor.description)
                        # created_at is not needed by this non-temporal query,
                        # but the original mapping still reads the named field.
                        if "chapter_title" in names and "rank" not in names:
                            self.assertEqual(names[-1], "created_at")
                            values = values[:-1]
                        return row_type(cursor, values)

                    self.book.db.row_factory = factory
                    try:
                        with self.assertRaises(IndexError):
                            self.book.recall("qzx17", project="derived", coverage=coverage,
                                             budget_chars=100000, use_cache=False)
                        self.assertFalse(self.book.db.in_transaction)
                    finally:
                        self.book.db.row_factory = sqlite3.Row


class WideCandidateMaterializationTests(unittest.TestCase):
    """Invented wide routes compare public payloads with the full mapping path."""

    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=8)
        self.addCleanup(self.book.close)
        self.sources = {}
        for index in range(192):
            name = f"wide-{index:03d}"
            form = "orbiting" if index < 96 else "orbits"
            source = {"project": "wide", "session_id": name, "task_id": "archive",
                "task_title": "Instrument archive", "title": "Shared relay notes",
                "created_at": f"2024-{index // 28 + 1:02d}-{index % 28 + 1:02d}T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                    f"The instrument {form} the moon. The qzx17 relay calibration threshold is stable. "
                    "缓存有效期是四十秒。"}]}
            self.sources[name] = source
            self.book.ingest(source)
        self.book.ingest({"project": "wide", "session_id": "semantic-only", "task_id": "receiver",
            "task_title": "Receiver archive", "title": "Receiver notes",
            "created_at": "2025-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content": "Receiver tolerance is four decibels."}]})

    def compare_full_mapping(self, query, *, book=None, **options):
        book = book or self.book
        options = {"project": "wide", "budget_chars": 100000, "use_cache": False, **options}
        book.db.row_factory = RowLike
        try:
            expected = stable(book.recall(query, **options))
        finally:
            book.db.row_factory = sqlite3.Row
        actual = stable(book.recall(query, **options))
        self.assertEqual(actual, expected)
        return actual

    def test_novelty_prefix_keeps_total_count_and_cached_payload(self):
        response = self.compare_full_mapping("qzx17 relay", limit=5)
        self.assertEqual(response["candidate_count"], 96)
        self.assertGreater(response["candidate_count"], 4 * 5)
        self.assertEqual(len(response["results"]), 5)
        self.assertTrue(response["truncated"])
        first = stable(self.book.recall("qzx17 relay", project="wide", budget_chars=100000, limit=5))
        cached = stable(self.book.recall("qzx17 relay", project="wide", budget_chars=100000, limit=5))
        self.assertEqual(first, response)
        self.assertTrue(cached.pop("cache_hit"))
        self.assertEqual(cached, {key: value for key, value in response.items() if key != "cache_hit"})

    def test_fused_union_above_96_keeps_limit_50_payload(self):
        for query, limit in (("orbiting", 5), ("orbiting", 50), ("orbiting qzx17", 50)):
            with self.subTest(query=query, limit=limit):
                response = self.compare_full_mapping(query, limit=limit)
                self.assertGreater(response["candidate_count"], 96)
                self.assertLessEqual(response["candidate_count"], 192)
                self.assertEqual(len(response["results"]), limit)
                self.assertTrue(response["truncated"])

    def test_current_limit_one_uses_the_original_four_page_prefix(self):
        # Equal body/directory scores order by page ID before temporal grouping.
        # Put the newest in-prefix date at position four, with an even newer
        # revision just outside: both shrinking and expanding the pool fail.
        rows = self.book.db.execute("""SELECT p.id,s.external_id FROM pages p
            JOIN sessions s ON s.id=p.session_pk WHERE s.external_id LIKE 'wide-%'
            ORDER BY p.id LIMIT 5""").fetchall()
        newest = rows[3]
        self.book.ingest({**self.sources[newest["external_id"]], "created_at": "2026-01-01T00:00:00Z"})
        self.book.ingest({**self.sources[rows[4]["external_id"]], "created_at": "2027-01-01T00:00:00Z"})
        response = self.compare_full_mapping("current qzx17 relay calibration threshold", limit=1)
        self.assertEqual(response["candidate_count"], 96)
        self.assertEqual(response["results"][0]["id"], newest["id"])
        self.assertNotEqual(response["results"][0]["id"], rows[0]["id"])

    def test_tiny_zero_flat_and_single_route_payloads_keep_counts(self):
        cases = [("qzx17", {"budget_chars": 1}, 96),
                 ("qzx17", {"budget_chars": 0}, 0),
                 ("qzx17", {"strategy": "flat", "limit": 1}, 96),
                 ("缓存有效期", {"limit": 5}, 96)]
        for query, options, count in cases:
            with self.subTest(query=query, options=options):
                response = self.compare_full_mapping(query, **options)
                self.assertEqual(response["candidate_count"], count)
                if options.get("budget_chars") in (0, 1):
                    self.assertEqual(response["results"], [])
                    self.assertEqual(response["truncated"], bool(count))
                    self.assertEqual(bool(response["warnings"]), bool(count))

    @unittest.skipUnless(HAS_TOKENS, "tiktoken is optional")
    def test_zero_and_small_token_budgets_keep_unselected_candidate_count(self):
        for tokenizer, budget in (("cl100k_base", 0), ("cl100k_base", 128), ("o200k_base", 128)):
            with self.subTest(tokenizer=tokenizer, budget=budget):
                response = self.compare_full_mapping("qzx17 relay", budget_tokens=budget, tokenizer=tokenizer)
                self.assertEqual(response["candidate_count"], 96)
                self.assertLessEqual(response["context_tokens"], budget)
                self.assertTrue(response["truncated"])

    def test_coverage_and_semantic_fusion_preserve_the_full_union(self):
        with MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                        min_page_chars=0, cache_size=0) as book:
            for index in range(152):
                # Twenty-four strong pages fill the novelty prefix. The weak,
                # common facet is eligible only from the retained full union.
                body = ("qzxrare gyzrare qzxrare gyzrare." if index < 24
                        else "Receiver tolerance is four decibels.")
                book.ingest({"project": "wide", "session_id": f"facet-{index:03d}",
                    "task_id": "facets", "task_title": "Instrument archive", "title": "Shared notes",
                    "created_at": "2024-01-01T00:00:00Z",
                    "messages": [{"role": "assistant", "content": body}]})
            query = "qzxrare gyzrare and receiver tolerance"
            default = book.recall(query, project="wide", limit=3, budget_chars=100000, use_cache=False)
            self.assertNotIn("Receiver tolerance is four decibels.", default["context"])
            covered = self.compare_full_mapping(query, book=book, coverage=True, limit=3)
            self.assertGreater(covered["candidate_count"], 4 * 3)
            self.assertIn("Receiver tolerance is four decibels.", covered["context"])
        semantic_row = dict(self.book.db.execute("""SELECT p.id,p.rid,p.project_id,p.chapter_id,
            c.title chapter_title,s.external_id session_id,s.title session_title,s.created_at
            FROM pages p JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk
            WHERE s.external_id='semantic-only'""").fetchone())
        semantic_row["semantic_similarity"] = 1.0
        model = SimpleNamespace(fingerprint="wide-fixture-only")
        # Only the encoder/index adapters are fixtures. The actual Q2 fusion
        # must retain all 96 lexical candidates and add its semantic-only page.
        with patch.object(self.book, "_semantic_encoder", return_value=model), \
                patch("memory_book.semantic.check_index", return_value={}), \
                patch("memory_book.semantic.rank_pages", return_value=[semantic_row]):
            response = self.compare_full_mapping("qzx17", semantic=True, limit=2)
        self.assertTrue(response["semantic"])
        self.assertEqual(response["candidate_count"], 97)
        self.assertEqual(len(response["results"]), 2)
        self.assertEqual(response["results"][1]["id"], semantic_row["id"])

    def test_missing_metadata_preserves_failure_and_rolls_back_snapshot(self):
        connection = self.book.db

        class MissingMetadataConnection:
            def __getattr__(self, name):
                return getattr(connection, name)

            def execute(self, statement, *arguments):
                cursor = connection.execute(statement, *arguments)
                if statement.startswith("SELECT p.id,p.project_id,p.chapter_id,"):
                    rows = cursor.fetchall()[1:]
                    return SimpleNamespace(fetchall=lambda: rows)
                return cursor

        self.book.db = MissingMetadataConnection()
        try:
            for factory in (sqlite3.Row, RowLike):
                with self.subTest(factory=factory):
                    connection.row_factory = factory
                    with self.assertRaisesRegex(KeyError, "chapter_title"):
                        self.book.recall("qzx17 relay", project="wide", use_cache=False)
                    self.assertFalse(connection.in_transaction)
        finally:
            connection.row_factory = sqlite3.Row
            self.book.db = connection

    def test_unexpected_native_row_shapes_keep_named_mapping_values(self):
        cases = [("metadata-rank", "rank", -17.0, "book"),
                 ("metadata-duplicate", "chapter_title", "qzx17", "book"),
                 ("route-duplicate", "project_id", "not-a-real-project", "flat")]
        for boundary, extra_name, extra_value, strategy in cases:
            with self.subTest(boundary=boundary), sqlite3.connect(":memory:") as schema:
                self.addCleanup(schema.close)
                cursors = {}

                def factory(row_type):
                    def build(cursor, values):
                        names = tuple(column[0] for column in cursor.description)
                        selected = ("rank" in names if boundary == "route-duplicate"
                                    else "chapter_title" in names and "rank" not in names)
                        if selected:
                            changed_names = (*names, extra_name)
                            if changed_names not in cursors:
                                cursors[changed_names] = schema.execute("SELECT " + ",".join(
                                    f'NULL AS "{name}"' for name in changed_names))
                            return row_type(cursors[changed_names], (*values, extra_value))
                        return row_type(cursor, values)
                    return build

                try:
                    self.book.db.row_factory = factory(RowLike)
                    expected = stable(self.book.recall("qzx17", project="wide", strategy=strategy,
                                                      budget_chars=100000, use_cache=False))
                    self.book.db.row_factory = factory(sqlite3.Row)
                    actual = stable(self.book.recall("qzx17", project="wide", strategy=strategy,
                                                    budget_chars=100000, use_cache=False))
                finally:
                    self.book.db.row_factory = sqlite3.Row
                self.assertEqual([hit["score"] for hit in actual["results"]],
                                 [hit["score"] for hit in expected["results"]])
                self.assertEqual(actual, expected)

    def test_later_reordered_native_row_keeps_named_column_boundaries(self):
        expected = stable(self.book.recall("qzx17", project="wide", budget_chars=100000,
                                          use_cache=False))
        leaders = self.book.db.execute("""SELECT p.id,p.rid FROM pages p
            JOIN sessions s ON s.id=p.session_pk WHERE s.external_id LIKE 'wide-%'
            ORDER BY p.id LIMIT 5""").fetchall()
        # The target is selected, but follows canonical rows both in route
        # order and in the metadata fetch. Checking only the first row fails.
        target = max(leaders[1:], key=lambda row: row["rid"])["id"]
        for boundary in ("route", "metadata"):
            with self.subTest(boundary=boundary), sqlite3.connect(":memory:") as schema:
                self.addCleanup(schema.close)
                cursors, counts = {}, {"canonical_before": 0, "reordered": 0}

                def row_factory(cursor, values):
                    names = tuple(column[0] for column in cursor.description)
                    selected = ("rank" in names if boundary == "route"
                                else "chapter_title" in names and "rank" not in names)
                    if selected:
                        if values[names.index("id")] == target:
                            reordered = (names[-1], *names[:-1])
                            if reordered not in cursors:
                                cursors[reordered] = schema.execute("SELECT " + ",".join(
                                    f'NULL AS "{name}"' for name in reordered))
                            counts["reordered"] += 1
                            return sqlite3.Row(cursors[reordered], (values[-1], *values[:-1]))
                        if not counts["reordered"]:
                            counts["canonical_before"] += 1
                    return sqlite3.Row(cursor, values)

                self.book.db.row_factory = row_factory
                try:
                    actual = stable(self.book.recall("qzx17", project="wide", budget_chars=100000,
                                                    use_cache=False))
                finally:
                    self.book.db.row_factory = sqlite3.Row
                self.assertGreater(counts["canonical_before"], 0)
                self.assertGreater(counts["reordered"], 0)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
