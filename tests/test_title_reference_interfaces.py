"""Artificial CLI and official MCP cases for the explicit title-hop option."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.cli import main, parser
from memory_book.mcp_server import _json, create_server, recall_payload


HAS_MCP = importlib.util.find_spec("mcp") is not None
HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
FIXTURE = json.loads((Path(__file__).parent / "fixtures/mcp-object-reference-baseline.json").read_text())


def seed(database):
    """Two linked source titles plus a same-ID/title source outside the project."""
    with MemoryBook(database, segmentation="turn", min_page_chars=0, cache_size=0) as book:
        for project, identity, title, content in (
            ("lab", "anchor", "Calibration memo", "quartzsignal points to STRAẞE\u00a0\t Laboratory. quartzsignal is documented here."),
            ("lab", "target", "Straße Laboratory", "It stands beside the northern inlet. 中文资料。"),
            ("outside", "target", "Straße Laboratory", "outsidecanary is private to another project."),
        ):
            book.ingest({"project": project, "session_id": identity, "title": title,
                         "task_id": "archive", "task_title": "Evidence archive",
                         "created_at": "2025-01-01T00:00:00Z",
                         "messages": [{"role": "user", "content": content}]})


def native(database, **options):
    arguments = {"project": "lab", "budget_chars": 2000, "limit": 5, "use_cache": False}
    arguments.update(options)
    with MemoryBook(database, cache_size=0) as book:
        return book.recall("quartzsignal", **arguments)


def without_timing(value):
    return {key: item for key, item in value.items() if key != "latency_ms"}


def decode_indexed(value):
    """Decode the documented wire representation independently of its encoder."""
    if value.get("source_format") != "indexed-v1":
        return value
    result = {key: item for key, item in value.items() if key not in ("source_sessions", "source_format")}
    result["results"] = []
    for hit in value["results"]:
        refs = []
        for entry in hit["source_refs"]:
            project, session = value["source_sessions"][entry[0]]
            refs.append({"project": project, "session_id": session, "turn_index": entry[1],
                         **(entry[2] if len(entry) == 3 else {})})
        result["results"].append({**hit, "source_refs": refs})
    return result


def clear_result_cache(database):
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM recall_cache")


class TitleReferenceCLITests(unittest.TestCase):
    def test_flag_is_boolean_opt_in_and_incompatible_modes_are_rejected(self):
        self.assertIs(parser().parse_args(["recall", "quartzsignal"]).follow_titles, False)
        self.assertIs(parser().parse_args(["recall", "quartzsignal", "--follow-titles"]).follow_titles, True)
        for extra in (["--follow-titles", "false"], ["--follow-titles=1"],
                      ["--follow-titles", "--flat"], ["--follow-titles", "--coverage"]):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                parser().parse_args(["recall", "quartzsignal", *extra])
            self.assertEqual(caught.exception.code, 2)

    def test_json_and_plain_context_match_the_native_selected_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            seed(database)
            command = ["--db", database, "recall", "quartzsignal", "--project", "lab", "--budget", "2000", "--no-cache"]
            for enabled in (False, True):
                extra = ["--follow-titles"] if enabled else []
                expected = native(database, follow_titles=enabled)
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    self.assertEqual(main([*command, *extra, "--json"]), 0)
                actual = json.loads(output.getvalue())
                self.assertEqual(without_timing(actual), without_timing(expected))
                if enabled:
                    self.assertTrue(actual["title_reference"]["applied"])
                    self.assertEqual(actual["title_reference"]["target"]["session_id"], "target")
                    self.assertIn("northern inlet", actual["context"])
                else:
                    self.assertNotIn("title_reference", actual)
                    self.assertNotIn("northern inlet", actual["context"])
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    self.assertEqual(main([*command, *extra]), 0)
                self.assertEqual(output.getvalue(), expected["context"] + "\n")

    def test_semantic_combination_fails_before_model_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["--db", str(Path(directory) / "book.db"), "recall", "quartzsignal",
                             "--follow-titles", "--semantic", "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("follow_titles cannot be combined", error.getvalue())
            self.assertNotIn("semantic_model_dir", error.getvalue())


class TitleReferenceProjectionTests(unittest.TestCase):
    def test_default_payloads_keep_frozen_compact_and_detailed_json_bytes(self):
        original = copy.deepcopy(FIXTURE["native_result"])
        for details, key in ((False, "compact_json"), (True, "details_json")):
            self.assertEqual(_json(recall_payload(original, details=details)), FIXTURE[key])
            self.assertNotIn("title_reference", recall_payload(original, details=details))
        self.assertEqual(original, FIXTURE["native_result"])

    def test_full_native_provenance_survives_every_projection_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            seed(database)
            original = native(database, follow_titles=True)
            preserved = copy.deepcopy(original)
            self.assertTrue(original["title_reference"]["applied"])
            for details in (False, True):
                objects = recall_payload(original, details=details)
                for source_format in ("objects", "indexed"):
                    projected = recall_payload(original, details=details, source_format=source_format)
                    self.assertEqual(decode_indexed(projected), objects)
                    self.assertEqual(projected["context"], original["context"])
                    self.assertEqual(projected["title_reference"], original["title_reference"])
            self.assertEqual(original, preserved)
            meta = original["title_reference"]
            with MemoryBook(database) as book:
                page = book.read(meta["anchor"]["page_id"])["content"]
                lo, hi = meta["mention"]["page_span"]
                self.assertEqual(page[lo:hi], "STRAẞE\u00a0\t Laboratory")

    def test_inactive_provenance_remains_visible_without_fabricated_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "book.db")
            seed(database)
            for options, reason in (({"project": None}, "project_required"),
                                    ({"limit": 1}, "limit_below_two"),
                                    ({"budget_chars": 0}, "zero_character_budget")):
                result = native(database, follow_titles=True, **options)
                for details in (False, True):
                    meta = recall_payload(result, details=details)["title_reference"]
                    self.assertEqual(meta, result["title_reference"])
                    self.assertFalse(meta["applied"])
                    self.assertEqual(meta["reason"], reason)
                    self.assertIsNone(meta.get("target_initial_page_in_pool"))
                    self.assertIsNone(meta.get("target_initial_session_in_pool"))


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for official MCP title-reference checks")
class TitleReferenceMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / "book.db")
        seed(self.database)

    def parameters(self, source_format="objects"):
        from mcp import StdioServerParameters
        source = str(Path(__file__).resolve().parents[1] / "src")
        environment = {"PYTHONPATH": os.pathsep.join(filter(None, (source, os.environ.get("PYTHONPATH")))),
                       "PYTHONUNBUFFERED": "1"}
        if "TIKTOKEN_CACHE_DIR" in os.environ:
            environment["TIKTOKEN_CACHE_DIR"] = os.environ["TIKTOKEN_CACHE_DIR"]
        return StdioServerParameters(command=sys.executable,
            args=["-m", "memory_book", "--db", self.database, "mcp", "--source-format", source_format],
            env=environment)

    async def test_real_stdio_strict_boolean_default_and_complete_projection_parity(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        expected = {flag: native(self.database, follow_titles=flag) for flag in (False, True)}
        for source_format in ("objects", "indexed"):
            async with stdio_client(self.parameters(source_format)) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    tool = next(tool for tool in tools.tools if tool.name == "recall_memory")
                    self.assertEqual(tool.inputSchema["properties"]["follow_titles"],
                                     {"default": False, "title": "Follow Titles", "type": "boolean"})
                    self.assertNotIn("follow_titles", tool.inputSchema.get("required", []))
                    self.assertIn("follow_titles", tool.description)
                    for invalid in ("true", "false", "", 0, 1, 0.0, 1.0, None, [], {}):
                        bad = await client.call_tool("recall_memory", {"query": "quartzsignal", "follow_titles": invalid})
                        self.assertTrue(bad.isError, (invalid, bad))
                    for enabled in (None, False, True):
                        for details in (False, True):
                            clear_result_cache(self.database)
                            args = {"query": "quartzsignal", "project": "lab", "budget_chars": 2000, "details": details}
                            if enabled is not None:
                                args["follow_titles"] = enabled
                            result = await client.call_tool("recall_memory", args)
                            self.assertFalse(result.isError, result)
                            self.assertIsNone(result.structuredContent)
                            self.assertEqual(len(result.content), 1)
                            actual = decode_indexed(json.loads(result.content[0].text))
                            wanted = recall_payload(expected[bool(enabled)], details=details)
                            self.assertEqual(without_timing(actual), without_timing(wanted))
                            self.assertNotIn("outsidecanary", actual["context"])

    async def test_official_sdk_rejects_incompatible_modes_and_preserves_session_scope(self):
        server = create_server(self.database)
        for option in ("semantic", "coverage"):
            with self.subTest(option=option), self.assertRaisesRegex(Exception, "follow_titles cannot be combined"):
                await server.call_tool("recall_memory", {"query": "quartzsignal", "project": "lab",
                    "follow_titles": True, option: True})
        for options in ({"session": "anchor"}, {"project": "outside"}, {"project": None}):
            args = {"query": "quartzsignal", "project": "lab", "budget_chars": 2000,
                    "follow_titles": True, "details": True, **options}
            clear_result_cache(self.database)
            response = await server.call_tool("recall_memory", args)
            value = json.loads(response[0].text)
            expected = native(self.database, follow_titles=True, **options)
            self.assertEqual(without_timing(value), without_timing(recall_payload(expected, details=True)))
            self.assertFalse(value["title_reference"]["applied"])

    async def test_provenance_and_context_are_preserved_by_the_normal_result_cache(self):
        server = create_server(self.database)
        args = {"query": "quartzsignal", "project": "lab", "budget_chars": 2000,
                "follow_titles": True, "details": True}
        first = json.loads((await server.call_tool("recall_memory", args))[0].text)
        second = json.loads((await server.call_tool("recall_memory", args))[0].text)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        second["cache_hit"] = False
        self.assertEqual(without_timing(first), without_timing(second))
        default = json.loads((await server.call_tool("recall_memory", {**args, "follow_titles": False}))[0].text)
        self.assertFalse(default["cache_hit"])
        self.assertNotIn("title_reference", default)
        self.assertNotIn("northern inlet", default["context"])

    @unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact token-cap checks")
    async def test_both_tokenizers_zero_tiny_and_normal_caps_keep_native_provenance(self):
        from memory_book.token_budget import TokenCounter
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            for budget in (0, 48, 256):
                options = {"budget_tokens": budget, "tokenizer": tokenizer, "follow_titles": True}
                expected = native(self.database, **options)
                for source_format in ("objects", "indexed"):
                    server = create_server(self.database, source_format=source_format)
                    for details in (False, True):
                        clear_result_cache(self.database)
                        response = await server.call_tool("recall_memory", {
                            "query": "quartzsignal", "project": "lab", "budget_chars": 2000,
                            "details": details, **options})
                        actual = decode_indexed(json.loads(response[0].text))
                        self.assertEqual(without_timing(actual), without_timing(recall_payload(expected, details=details)))
                        self.assertEqual(actual["context_tokens"], counter.count(actual["context"]))
                        self.assertLessEqual(actual["context_tokens"], budget)
                        self.assertLessEqual(actual["context_chars"], 2000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
