"""Lossless references and frozen MCP compatibility except approved API changes."""
from __future__ import annotations

import copy
from datetime import timedelta
import importlib.metadata
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest

from memory_book.mcp_server import (INDEXED_REFERENCE_INSTRUCTIONS, _json,
                                   create_server, recall_payload)
from scripts.prototype_indexed_references import decode

FIXTURE = json.loads((Path(__file__).parent / "fixtures/mcp-object-reference-baseline.json").read_text())
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import ListToolsResult
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class IndexedReferenceValueTests(unittest.TestCase):
    def test_default_and_explicit_objects_preserve_frozen_json_bytes(self):
        result = copy.deepcopy(FIXTURE["native_result"])
        original = _json(result)
        for details, key in ((False, "compact_json"), (True, "details_json")):
            self.assertEqual(_json(recall_payload(result, details=details)), FIXTURE[key])
            self.assertEqual(_json(recall_payload(result, details=details, source_format="objects")), FIXTURE[key])
        self.assertEqual(_json(result), original)

    def test_indexed_preserves_all_fields_duplicates_and_project_scope(self):
        result = copy.deepcopy(FIXTURE["native_result"])
        original = _json(result)
        for details in (False, True):
            objects = recall_payload(result, details=details)
            indexed = recall_payload(result, details=details, source_format="indexed")
            self.assertEqual(decode(indexed), objects)
            self.assertEqual(indexed["source_sessions"], [["p1", "same"], ["p2", "same"]])
            self.assertEqual(indexed["source_format"], "indexed-v1")
            self.assertEqual(indexed["context"], objects["context"])
            self.assertEqual(indexed["warnings"], objects["warnings"])
            self.assertEqual([r["id"] for r in indexed["results"]], [r["id"] for r in objects["results"]])
            self.assertEqual(len(indexed["results"][0]["source_refs"]), 2 if details else 1)
        self.assertEqual(_json(result), original)

    def test_unknown_extra_fields_unicode_and_repeated_sessions_roundtrip(self):
        rng = random.Random(729)
        result = copy.deepcopy(FIXTURE["native_result"])
        for _ in range(50):
            references = []
            for i in range(rng.randrange(1, 40)):
                references.append({"project": rng.choice(["项目", "p2"]),
                    "session_id": rng.choice(["déjà", "same", "会话"]), "turn_index": i % 4,
                    "start": i, "end": i + 3, "turn_start": i + 20, "turn_end": i + 23,
                    "role": "tool", "message_indices": [i, i + 1],
                    "future_field": {"text": "ß😀", "values": [True, None, i]}})
            result["results"][0]["source_refs"] = references
            objects = recall_payload(result, details=True)
            self.assertEqual(decode(recall_payload(result, details=True, source_format="indexed")), objects)

    def test_empty_result_retains_version_and_is_reversible(self):
        result = {**copy.deepcopy(FIXTURE["native_result"]), "results": [], "context": "", "context_chars": 0}
        for details in (False, True):
            indexed = recall_payload(result, details=details, source_format="indexed")
            self.assertEqual(indexed["source_sessions"], [])
            self.assertEqual(decode(indexed), recall_payload(result, details=details))

    def test_invalid_operator_format_fails_before_opening_a_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "not-created.db"
            for value in ("unknown", None, True, [], {}):
                with self.assertRaises(ValueError):
                    create_server(database, source_format=value)
                with self.assertRaises(ValueError):
                    recall_payload(FIXTURE["native_result"], source_format=value)
            self.assertFalse(database.exists())


@unittest.skipUnless(HAS_MCP, "Install .[mcp] for official SDK compatibility tests")
class IndexedReferenceSDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_only_adds_approved_defaults_and_temporal_control(self):
        tools = []
        for format_name in ("objects", "indexed"):
            listed = await create_server(":memory:", source_format=format_name).list_tools()
            tools.append(ListToolsResult(tools=listed).model_dump_json(exclude_none=True))
            recall = next(tool for tool in listed if tool.name == "recall_memory")
            self.assertNotIn("source_format", recall.inputSchema["properties"])
            self.assertNotIn("ranking_scope", recall.inputSchema["properties"])
            self.assertEqual(recall.inputSchema["properties"]["required_fields"], {
                "anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}],
                "default": None, "title": "Required Fields"})
            self.assertNotIn("required_fields", recall.inputSchema.get("required", []))
            directory = next(tool for tool in listed if tool.name == "search_directory")
            self.assertEqual(set(directory.inputSchema["properties"]), {"query", "project", "chapter", "limit", "offset"})
            self.assertEqual(directory.inputSchema["required"], ["query"])
            self.assertEqual(directory.inputSchema["properties"]["limit"]["default"], 10)
            self.assertEqual(directory.inputSchema["properties"]["offset"]["default"], 0)
        self.assertEqual(tools[0], tools[1])
        # Exact frozen SDK representation is version-scoped; field compatibility
        # between modes is checked above on every installed supported SDK.
        if (importlib.metadata.version("mcp") == FIXTURE["mcp"]
                and importlib.metadata.version("pydantic") == FIXTURE["pydantic"]):
            # Preserve the historical fixture and its source bytes. v0.4.0
            # changed recall's omitted budget; v0.5.0 adds explicit temporal
            # control and its documentation. v0.7.0 allows a bound connection
            # to supply browse_book's project and adds explicit project
            # assertions to follow-up navigation. v0.13 documents the bounded
            # assessment already returned to current requests. The current
            # optional required_fields gate adds one nullable string-array
            # parameter and its bounded-support explanation; omitted/null
            # retains the original behavior. Every other serialized field
            # must still match the approved historical representation.
            expected = json.loads(FIXTURE["schema"])
            compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            self.assertEqual(compact(expected), FIXTURE["schema"])
            recall_schema = next(tool for tool in expected["tools"] if tool["name"] == "recall_memory")
            budget_schema = recall_schema["inputSchema"]["properties"]["budget_chars"]
            self.assertEqual(budget_schema["default"], 4000)
            budget_schema["default"] = 2400
            recall_schema["inputSchema"]["properties"]["temporal"] = {
                "default": "auto", "enum": ["auto", "current", "relevance"],
                "title": "Temporal", "type": "string"}
            self.assertNotIn("required_fields", recall_schema["inputSchema"]["properties"])
            recall_schema["inputSchema"]["properties"]["required_fields"] = {
                "anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}],
                "default": None, "title": "Required Fields"}
            recall_schema["description"] = recall_schema["description"].rstrip() + (
                "\n        temporal=auto distinguishes current requests from historical queries;"
                "\n        current explicitly prefers comparable recent evidence, and relevance"
                "\n        keeps relevance ordering. This is not an as-of state resolver. Repeated"
                "\n        event evidence is retained. Assessed current requests include the bounded"
                "\n        evidence_assessment status and conflict page IDs even in compact output;"
                "\n        these do not establish truth or exhaustive absence. details=true adds"
                "\n        the resolution basis and assessment counts."
                "\n        required_fields optionally names literal fields whose complete current"
                "\n        declarations must all survive in the returned pages. It requires a"
                "\n        project and withholds context when support is missing, truncated or"
                "\n        conflicting. This conservative gate does not prove archive-wide absence"
                "\n        or answerability for arbitrary prose; evidence_gate explains its result."
                "\n        ")
            project_schema = {"anyOf": [{"type": "string"}, {"type": "null"}],
                              "default": None, "title": "Project"}
            book_schema = next(tool for tool in expected["tools"]
                               if tool["name"] == "browse_book")["inputSchema"]
            self.assertEqual(book_schema["properties"]["project"],
                             {"title": "Project", "type": "string"})
            self.assertEqual(book_schema["required"], ["project"])
            book_schema["properties"]["project"] = copy.deepcopy(project_schema)
            del book_schema["required"]
            for name, identity in (("browse_chapter", "chapter_id"),
                                   ("browse_section", "section_id"),
                                   ("read_page", "page_id")):
                navigation = next(tool for tool in expected["tools"]
                                  if tool["name"] == name)["inputSchema"]
                self.assertNotIn("project", navigation["properties"])
                self.assertEqual(navigation["required"], [identity])
                navigation["properties"]["project"] = copy.deepcopy(project_schema)
            # v0.11 adds one independently checked navigation tool. Every
            # historical tool still has the exact approved representation.
            existing = json.loads(tools[0])
            self.assertEqual(sum(tool["name"] == "search_directory" for tool in existing["tools"]), 1)
            existing["tools"] = [tool for tool in existing["tools"] if tool["name"] != "search_directory"]
            self.assertEqual(compact(existing), compact(expected))

    async def test_required_fields_is_optional_and_rejects_invalid_runtime_values(self):
        from memory_book import MemoryBook
        from mcp.server.fastmcp.exceptions import ToolError

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            with MemoryBook(database, segmentation="turn") as book:
                book.ingest({"project": "engine", "session_id": "configuration",
                    "created_at": "2025-01-01T00:00:00Z",
                    "messages": [{"role": "assistant", "content": "Production retry_limit=12."}]})
            for source_format in ("objects", "indexed"):
                server = create_server(database, source_format=source_format)
                arguments = {"query": "current production retry_limit", "project": "engine"}

                async def call(extra):
                    result = await server.call_tool("recall_memory", {**arguments, **extra})
                    return json.loads("".join(part.text for part in result if part.type == "text"))

                omitted, explicit_null = await call({}), await call({"required_fields": None})
                self.assertEqual(omitted, explicit_null)
                self.assertNotIn("evidence_gate", omitted)
                supported = await call({"required_fields": ["retry_limit"]})
                self.assertEqual(supported["context"], omitted["context"])
                self.assertEqual(supported["evidence_gate"]["status"], "supported")
                for invalid in ("retry_limit", [], [False], [""], ["retry limit"],
                                ["worker..retry_limit"], ["x" * 129], ["x"] * 17):
                    with self.subTest(source_format=source_format, invalid=invalid), \
                            self.assertRaisesRegex(ToolError, "required_fields"):
                        await call({"required_fields": invalid})
                with self.assertRaisesRegex(ToolError, "required_fields requires an explicit project"):
                    await call({"project": None, "required_fields": ["retry_limit"]})

    async def test_real_cli_modes_preserve_defaults_and_full_provenance(self):
        from memory_book import MemoryBook
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            with MemoryBook(database) as book:
                for project in ("p1", "p2"):
                    book.ingest({"project": project, "session_id": "same", "created_at": "2025-01-01T00:00:00Z",
                        "messages": [{"role": "user", "content": "What calibration policy was selected?"},
                                     {"role": "assistant", "content": "Calibration uses a 45 second delay. Preserve accents: déjà, ß, 中文."}]})
            modes = {}
            for selected in (None, "objects", "indexed"):
                extra = [] if selected is None else ["--source-format", selected]
                params = StdioServerParameters(command=sys.executable,
                    args=["-m", "memory_book", "--db", str(database), "mcp", *extra],
                    env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
                outputs = []
                async with stdio_client(params) as (reader, writer):
                    async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as client:
                        initialized = await client.initialize()
                        # Apply only the explicitly approved temporal,
                        # bounded-assessment and navigation explanations. The
                        # stored evidence and historical fixture stay unchanged.
                        old = "diagnostics. read_page also supplies full provenance. Empty results prove no\n"
                        self.assertEqual(FIXTURE["instructions"].count(old), 1)
                        expected = FIXTURE["instructions"].replace(old,
                            "diagnostics, including the resolved temporal mode. temporal=auto infers time\n"
                            "intent conservatively; current prefers comparable recent evidence; relevance\n"
                            "keeps relevance ordering. Neither resolves authority or an as-of state.\n"
                            "read_page also supplies full provenance. Empty results prove no\n", 1)
                        assessment_anchor = "keeps relevance ordering. Neither resolves authority or an as-of state.\n"
                        self.assertEqual(expected.count(assessment_anchor), 1)
                        expected = expected.replace(assessment_anchor, assessment_anchor +
                            "For assessed current queries, read evidence_assessment even in compact output.\n"
                            "potential_conflict means unresolved comparable sources: inspect its page_ids\n"
                            "within the same project. no_comparable_declaration means the bounded inspected\n"
                            "pool did not establish a comparable declaration, not that the archive proves\n"
                            "absence. No assessment status is a truth or confidence score.\n", 1)
                        navigation = "Use context and source_refs to cite session_id/turn_index. Read selected page IDs\n"
                        self.assertEqual(expected.count(navigation), 1)
                        expected = expected.replace(navigation,
                            "Use search_directory when you know a task title or question but not its address;\n"
                            "it returns chapter/section navigation, not answer evidence. Keep the same project\n"
                            "when following those addresses with browse_chapter, browse_section or read_page.\n" + navigation, 1)
                        expected += INDEXED_REFERENCE_INSTRUCTIONS if selected == "indexed" else ""
                        self.assertEqual(initialized.instructions, expected)
                        listed = await client.list_tools()
                        schemas = listed.model_dump_json(exclude_none=True)
                        for details in (False, True):
                            with sqlite3.connect(database) as connection:
                                connection.execute("DELETE FROM recall_cache")
                            response = await client.call_tool("recall_memory", {"query": "calibration policy",
                                "budget_chars": 4000, "limit": 5, "details": details})
                            self.assertFalse(response.isError)
                            self.assertIsNone(response.structuredContent)
                            self.assertEqual(len(response.content), 1)
                            text = response.content[0].text
                            body = json.loads(text)
                            if selected == "indexed":
                                self.assertEqual(body["source_format"], "indexed-v1")
                                body = decode(body)
                            else:
                                self.assertNotIn("source_format", body)
                            self.assertTrue(body["results"])
                            if details:
                                self.assertFalse(body["cache_hit"])
                                self.assertTrue(body["results"][0]["source_refs"][0]["message_indices"])
                                body.pop("latency_ms")  # Independent actual calls have different elapsed diagnostics.
                            outputs.append({"text": text if not details else None, "value": body})
                        page = await client.call_tool("read_page", {"page_id": body["results"][0]["id"]})
                        read = json.loads(page.content[0].text)
                        self.assertIsInstance(read["source_refs"][0], dict)
                modes[selected] = {"schema": schemas, "outputs": outputs}
            self.assertEqual(modes[None], modes["objects"])
            self.assertEqual(modes[None]["schema"], modes["indexed"]["schema"])
            self.assertEqual([r["value"] for r in modes[None]["outputs"]],
                             [r["value"] for r in modes["indexed"]["outputs"]])


if __name__ == "__main__":
    unittest.main()
