"""Lossless operator-selected references and byte-compatible default MCP."""
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
    async def test_schema_is_unchanged_and_format_is_not_a_model_argument(self):
        tools = []
        for format_name in ("objects", "indexed"):
            listed = await create_server(":memory:", source_format=format_name).list_tools()
            tools.append(ListToolsResult(tools=listed).model_dump_json(exclude_none=True))
            recall = next(tool for tool in listed if tool.name == "recall_memory")
            self.assertNotIn("source_format", recall.inputSchema["properties"])
        self.assertEqual(tools[0], tools[1])
        # Exact frozen SDK representation is version-scoped; field compatibility
        # between modes is checked above on every installed supported SDK.
        if (importlib.metadata.version("mcp") == FIXTURE["mcp"]
                and importlib.metadata.version("pydantic") == FIXTURE["pydantic"]):
            self.assertEqual(tools[0], FIXTURE["schema"])

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
                        expected = FIXTURE["instructions"] + (INDEXED_REFERENCE_INSTRUCTIONS if selected == "indexed" else "")
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
