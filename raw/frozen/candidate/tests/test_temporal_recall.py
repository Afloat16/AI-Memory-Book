"""Explicit time intent and provenance wording across developer interfaces.

These independent queue configuration fixtures are not benchmark questions.
Semantic fixture ranks test routing/ordering, not embedding quality.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from memory_book import MemoryBook
from memory_book.cli import main, parser
from memory_book.token_budget import TokenCounter


TOPIC = "worker prefetch window"


def revision(name="old", *, project="workers", task="queue", value=12,
             date="2026-01-01T00:00:00Z", repeats=12):
    return {"project": project, "session_id": name, "task_id": task,
            "title": "Worker prefetch window", "created_at": date,
            "messages": [
                {"role": "user", "content": "Worker prefetch window?"},
                {"role": "assistant", "content": f"Worker prefetch window is {value}. "
                 + "worker prefetch window. " * repeats}]}


def seed(book):
    old = book.ingest(revision())
    book.ingest(revision("new", value=3, date="2026-02-01T00:00:00Z", repeats=0))
    return old["chapter_id"]


class TemporalRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:")
        self.addCleanup(self.book.close)
        self.chapter = seed(self.book)

    def recall(self, query=TOPIC, **options):
        return self.book.recall(query, project="workers", limit=1,
                                budget_chars=600, **options)

    def test_explicit_modes_control_evidence_without_rewriting_query(self):
        for query in (TOPIC, "current " + TOPIC, "current " + TOPIC + " as of 2026"):
            with self.subTest(query=query):
                current = self.recall(query, temporal="current")
                relevance = self.recall(query, temporal="relevance")
                self.assertIn("window is 3", current["context"])
                self.assertIn("window is 12", relevance["context"])
                self.assertEqual(current["query"], query)
                self.assertEqual(current["temporal"]["resolved"], "current")
                self.assertEqual(relevance["temporal"]["resolved"], "relevance")
                self.assertEqual(current["temporal"]["basis"], "explicit_override")
                self.assertTrue(current["warnings"])

    def test_auto_provenance_and_dataset_labels_keep_current_intent(self):
        for query in (
            "current worker prefetch window with original source evidence",
            "latest worker prefetch window; cite the original technical decision",
            "当前 worker prefetch window 的配置？请找出原始工程决策。",
            "当前 worker prefetch window，请引用原始的技术决策记录",
            "当前 worker prefetch window 的原始证据",
            "current worker prefetch window for dataset 2026",
            "current worker prefetch window for the 2026 data set",
            "当前 worker prefetch window，数据集：2026",
        ):
            with self.subTest(query=query):
                result = self.recall(query)
                self.assertIn("window is 3", result["context"])
                self.assertEqual(result["temporal"]["resolved"], "current")
                self.assertTrue(result["temporal"]["provenance_or_dataset_labels"])

    def test_auto_genuine_history_and_ambiguous_comparisons_stay_relevance(self):
        for query in (
            "original worker prefetch window",
            "current worker prefetch window as of 2026",
            "current worker prefetch window before migration",
            "current worker prefetch window and the original decision",
            "current worker prefetch window compared with the original source",
            "current worker prefetch window versus original source evidence",
            "not the current worker prefetch window; cite original source evidence",
            "current worker prefetch window for dataset 2026 before migration",
            "current worker prefetch window for dataset 2026-03-01",
            "current worker prefetch window with original source evidence from 2026",
            "当前 worker prefetch window 和最初的决策",
            "当前 worker prefetch window，请引用原始证据并解释之前的配置",
            "当前 worker prefetch window 与原始工程决策的对比",
            "不要当前 worker prefetch window，请找出原始工程决策",
        ):
            with self.subTest(query=query):
                result = self.recall(query)
                self.assertIn("window is 12", result["context"])
                self.assertEqual(result["temporal"]["resolved"], "relevance")
                self.assertTrue(result["temporal"]["historical_cues"])
                if result["temporal"].get("current_cues"):
                    self.assertEqual(result["temporal"]["basis"], "mixed_temporal_cues")
                    self.assertTrue(any("both present" in warning for warning in result["warnings"]))

    def test_mode_cache_keys_and_revision_invalidation(self):
        for mode, expected in (("auto", 12), ("current", 3), ("relevance", 12)):
            with self.subTest(mode=mode):
                first = self.recall(temporal=mode)
                cached = self.recall(temporal=mode)
                self.assertFalse(first["cache_hit"])
                self.assertTrue(cached["cache_hit"])
                self.assertEqual(first["context"], cached["context"])
                self.assertEqual(cached["temporal"]["requested"], mode)
                self.assertIn(f"window is {expected}", cached["context"])
        self.book.ingest(revision("new", value=2, date="2026-03-01T00:00:00Z", repeats=0))
        result = self.recall(temporal="current")
        self.assertFalse(result["cache_hit"])
        self.assertIn("window is 2", result["context"])

    def test_scope_is_applied_before_explicit_current_ordering(self):
        self.book.ingest(revision("new", project="foreign", value=99,
                                  date="2026-06-01T00:00:00Z", repeats=0))
        self.book.ingest(revision("different-task", task="another", value=77,
                                  date="2026-05-01T00:00:00Z", repeats=0))
        result = self.recall(temporal="current", chapter=self.chapter)
        self.assertIn("window is 3", result["context"])
        self.assertTrue(all(ref["project"] == "workers" for hit in result["results"]
                            for ref in hit["source_refs"]))
        earlier = self.recall(temporal="current", chapter=self.chapter, session="old")
        self.assertIn("window is 12", earlier["context"])
        self.assertEqual({ref["session_id"] for hit in earlier["results"]
                          for ref in hit["source_refs"]}, {"old"})

    def test_event_queries_keep_repeated_sources_even_with_override(self):
        with MemoryBook(":memory:") as book:
            for index in range(3):
                book.ingest(revision(str(index), repeats=0,
                                     date=f"2026-01-0{index + 1}T00:00:00Z"))
            for mode in ("auto", "current", "relevance"):
                for phrase in ("how many times", "event timeline", "出现次数"):
                    result = book.recall(f"current {TOPIC} {phrase}", project="workers",
                                          temporal=mode, limit=3, budget_chars=1800)
                    self.assertTrue(result["temporal"]["preserve_occurrences"])
                    self.assertEqual(len(result["results"]), 3)
                    self.assertEqual(len({ref["session_id"] for hit in result["results"]
                                          for ref in hit["source_refs"]}), 3)

    def test_invalid_mode_fails_before_optional_runtime_or_database_work(self):
        before = self.book.revision
        with patch.object(self.book, "_semantic_encoder", side_effect=AssertionError("loaded model")):
            for value in (None, True, 0, 1, [], {}, "", "historical", "CURRENT"):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "temporal must be"):
                    self.recall(temporal=value, semantic=True, budget_tokens=20)
        self.assertEqual(self.book.revision, before)
        self.assertEqual(self.book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)

    def test_empty_budget_and_flat_explain_effective_order(self):
        empty = self.book.recall("", budget_chars=0, temporal="current")
        self.assertEqual(empty["results"], [])
        self.assertEqual(empty["temporal"]["resolved"], "current")
        flat = self.recall("current " + TOPIC, strategy="flat")
        self.assertEqual(flat["temporal"]["resolved"], "relevance")
        self.assertEqual(flat["temporal"]["basis"], "flat_strategy")
        with self.assertRaisesRegex(ValueError, "book strategy"):
            self.recall(strategy="flat", temporal="current")


@unittest.skipUnless(importlib.util.find_spec("tiktoken"), "optional real tokenizers are not installed")
class TemporalTokenTests(unittest.TestCase):
    def test_explicit_current_preserves_latest_authenticated_turn_at_exact_cap(self):
        with MemoryBook(":memory:") as book:
            source = revision()
            source["messages"] += revision("new", value=3, repeats=0)["messages"]
            self.assertEqual(book.ingest(source)["pages"], 1)
            full = book.recall(TOPIC, project="workers", temporal="current", limit=1, budget_chars=4000)
            page = book.read(full["results"][0]["id"])
            latest = next(ref for ref in page["source_refs"] if ref["turn_index"] == 1)
            header = full["context"].split("\n", 1)[0] + "\n"
            expected = "…" + page["content"][latest["start"]:latest["end"]]
            for tokenizer in ("cl100k_base", "o200k_base"):
                counter = TokenCounter(tokenizer)
                cap = counter.count(header + expected)
                ordinary = book.recall(TOPIC, project="workers", limit=1,
                                       budget_chars=4000, budget_tokens=cap, tokenizer=tokenizer)
                for mode in ("current", "relevance"):
                    with self.subTest(tokenizer=tokenizer, mode=mode):
                        result = book.recall(TOPIC, project="workers", temporal=mode, limit=1,
                                             budget_chars=4000, budget_tokens=cap, tokenizer=tokenizer)
                        self.assertEqual(result["context_tokens"], counter.count(result["context"]))
                        self.assertLessEqual(result["context_tokens"], cap)
                        self.assertLessEqual(len(result["context"]), 4000)
                        turns = {ref["turn_index"] for hit in result["results"] for ref in hit["source_refs"]}
                        if mode == "current":
                            self.assertEqual(turns, {1})
                            self.assertIn("window is 3", result["context"])
                            self.assertNotIn("window is 12", result["context"])
                        else:
                            # Relevance is not "oldest": an ordinary budget
                            # allocator may prefer the smaller complete turn.
                            self.assertEqual(result["context"], ordinary["context"])
                            self.assertEqual(result["results"], ordinary["results"])
                        for hit in result["results"]:
                            for ref in hit["source_refs"]:
                                original = book.db.execute("SELECT content FROM turns WHERE ordinal=?",
                                                           (ref["turn_index"],)).fetchone()[0]
                                self.assertEqual(page["content"][ref["start"]:ref["end"]],
                                                 original[ref["turn_start"]:ref["turn_end"]])

    def test_token_only_mode_override_changes_the_selected_correction(self):
        from tests.test_current_turn_recall import same_page_session
        with MemoryBook(":memory:") as book:
            book.ingest(same_page_session())
            for tokenizer in ("cl100k_base", "o200k_base"):
                for mode, expected, turn in (("current", "steps are now 2", 1),
                                              ("relevance", "steps are 8", 0)):
                    result = book.recall("gradient accumulation steps", project="trainer",
                                         temporal=mode, limit=1, budget_chars=4000,
                                         budget_tokens=90, tokenizer=tokenizer)
                    self.assertIn(expected, result["context"])
                    self.assertEqual({ref["turn_index"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {turn})
                    self.assertLessEqual(TokenCounter(tokenizer).count(result["context"]), 90)


class TemporalSemanticTests(unittest.TestCase):
    def test_semantic_fusion_cannot_reverse_comparable_current_revisions(self):
        from tests.test_semantic import FixtureEncoder
        with MemoryBook(":memory:", semantic_model_dir="/fixture") as book:
            book._semantic_model = FixtureEncoder()
            seed(book)
            book.ingest(revision("middle", value=6, date="2026-01-15T00:00:00Z", repeats=3))
            book.build_semantic_index()
            rows = [dict(row) for row in book.db.execute(
                "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
                "s.external_id session_id,s.title session_title,s.created_at "
                "FROM pages p JOIN chapters c ON c.id=p.chapter_id "
                "JOIN sessions s ON s.id=p.session_pk ORDER BY s.created_at")]
            ranked = [{**row, "semantic_similarity": 1 - i / 10} for i, row in enumerate(rows)]
            with patch("memory_book.semantic.rank_pages", return_value=ranked):
                current = book.recall(TOPIC, project="workers", temporal="current", semantic=True,
                                      limit=3, budget_chars=2400)
                relevance = book.recall(TOPIC, project="workers", temporal="relevance", semantic=True,
                                        limit=3, budget_chars=2400)
                order = lambda result: [hit["source_refs"][0]["session_id"] for hit in result["results"]]
                self.assertEqual(order(current), ["new", "middle", "old"])
                self.assertEqual(order(relevance)[0], "old")
                self.assertTrue(current["semantic"])
                self.assertFalse(relevance["cache_hit"])
                self.assertTrue(book.recall(TOPIC, project="workers", temporal="current", semantic=True,
                                            limit=3, budget_chars=2400)["cache_hit"])
                # A semantic-only match does not establish a factual revision:
                # recency must not advance unrelated text on date alone.
                only_semantic = book.recall("unrelatedword", project="workers", temporal="current",
                                            semantic=True, limit=3, budget_chars=2400)
                self.assertEqual(order(only_semantic), ["old", "middle", "new"])


class TemporalInterfaceTests(unittest.TestCase):
    def test_cli_forwards_mode_and_rejects_invalid_values(self):
        self.assertEqual(parser().parse_args(["recall", TOPIC]).temporal, "auto")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["recall", TOPIC, "--temporal", "historical"])
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            with MemoryBook(database) as book:
                seed(book)
            for mode, value in (("current", 3), ("relevance", 12)):
                output = io.StringIO()
                with redirect_stdout(output):
                    status = main(["--db", database, "recall", TOPIC, "--project", "workers",
                                   "--limit", "1", "--json", "--temporal", mode])
                self.assertEqual(status, 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["temporal"]["resolved"], mode)
                self.assertIn(f"window is {value}", result["context"])

    def test_local_http_service_forwards_and_validates_mode(self):
        from memory_book.web import make_server
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "book.db"
            with MemoryBook(database) as book:
                seed(book)
            server = make_server(database, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for mode, expected in (("current", 3), ("relevance", 12), ("historical", None)):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    try:
                        connection.request("GET", "/api/recall?" + urlencode({
                            "q": TOPIC, "project": "workers", "limit": 1, "temporal": mode}))
                        response = connection.getresponse()
                        result = json.loads(response.read())
                        self.assertEqual(response.status, 200 if expected else 400)
                        if expected:
                            self.assertIn(f"window is {expected}", result["context"])
                            self.assertEqual(result["temporal"]["resolved"], mode)
                    finally:
                        connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK is not installed")
class TemporalMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_schema_forwarding_diagnostics_and_compact_projection(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            with MemoryBook(database) as book:
                seed(book)
            parameters = StdioServerParameters(command=sys.executable,
                args=["-m", "memory_book", "--db", database, "mcp"],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONUNBUFFERED": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                    await client.initialize()
                    listed = await client.list_tools()
                    tool = next(tool for tool in listed.tools if tool.name == "recall_memory")
                    self.assertEqual(set(tool.inputSchema["properties"]["temporal"]["enum"]),
                                     {"auto", "current", "relevance"})
                    arguments = {"query": TOPIC, "project": "workers", "limit": 1}
                    for mode, expected in (("auto", 12), ("current", 3), ("relevance", 12)):
                        for details in (False, True):
                            response = await client.call_tool("recall_memory", {
                                **arguments, "temporal": mode, "details": details})
                            self.assertFalse(response.isError, response)
                            result = json.loads("".join(part.text for part in response.content if part.type == "text"))
                            self.assertIn(f"window is {expected}", result["context"])
                            if details:
                                self.assertEqual(result["temporal"]["requested"], mode)
                            else:
                                self.assertNotIn("temporal", result)
                    for invalid in ("historical", "CURRENT", "", True, 1, None, []):
                        response = await client.call_tool("recall_memory", {**arguments, "temporal": invalid})
                        self.assertTrue(response.isError, (invalid, response))


if __name__ == "__main__":
    unittest.main()
