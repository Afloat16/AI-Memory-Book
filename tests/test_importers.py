from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_book.importers import MAX_IMPORT_BYTES, load_sessions, parse_sessions, transcript_info


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "transcript.json"

    def write(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return self.path

    def jsonl(self, *records):
        self.path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8"
        )
        return self.path

    @staticmethod
    def canonical(**changes):
        data = {
            "project": "支付服务",
            "session_id": "session-1",
            "title": "支付回调",
            "task_id": "callbacks",
            "messages": [
                {"role": "user", "content": "回调怎样去重？"},
                {"role": "assistant", "content": "按 event_id 去重。"},
            ],
        }
        data.update(changes)
        return data

    def test_canonical_single_list_and_wrapper(self):
        session = self.canonical()
        for representation in (session, [session], {"sessions": [session]}):
            with self.subTest(representation=type(representation).__name__):
                result = load_sessions(self.write(representation))
                self.assertEqual(result, [session])

    def test_project_and_task_override_are_explicit(self):
        result = load_sessions(self.write(self.canonical()), project="另一个项目", task_id="new-task")
        self.assertEqual(result[0]["project"], "另一个项目")
        self.assertEqual(result[0]["task_id"], "new-task")

    def test_export_shape_preserves_project_name_and_accepts_empty_task(self):
        source = self.canonical(project_name="Friendly project", task_id="", task_title="")
        result = load_sessions(self.write(source))[0]
        self.assertEqual(result["project_name"], "Friendly project")
        self.assertNotIn("task_id", result)
        self.assertNotIn("task_title", result)
        with self.assertRaises(ValueError):
            load_sessions(self.path, task_id="")

    def test_missing_project_must_be_supplied(self):
        source = self.canonical()
        del source["project"]
        self.write(source)
        with self.assertRaisesRegex(ValueError, "Project is missing"):
            load_sessions(self.path)
        self.assertEqual(load_sessions(self.path, project="explicit")[0]["project"], "explicit")

    def test_canonical_keeps_text_roles_and_does_not_execute_them(self):
        messages = [
            {"role": role, "content": "literal $(do-not-execute) `command` <script>\ntext"}
            for role in ("system", "developer", "user", "assistant", "tool")
        ]
        result = load_sessions(self.write(self.canonical(messages=messages)))
        self.assertEqual(result[0]["messages"], messages)

    def test_missing_identity_gets_stable_snapshot_id(self):
        source = self.canonical()
        del source["session_id"]
        self.write(source)
        first = load_sessions(self.path)[0]["session_id"]
        self.assertEqual(first, load_sessions(self.path)[0]["session_id"])
        source["messages"].append({"role": "user", "content": "new question"})
        self.assertNotEqual(first, load_sessions(self.write(source))[0]["session_id"])

    def test_invalid_canonical_fields_fail(self):
        invalid = (
            {"messages": [{"role": "unknown", "content": "x"}]},
            {"messages": [{"role": [], "content": "x"}]},
            {"messages": [{"role": "user", "content": {"text": "x"}}]},
            {"messages": []},
            {"messages": [{"role": "user", "content": "  "}]},
            {"session_id": 123},
            {"session_id": ""},
            {"project": []},
            {"task_id": False},
            {"created_at": {}},
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    load_sessions(self.write(self.canonical(**fields)))

    def test_batch_is_validated_before_return(self):
        self.write({"sessions": [self.canonical(), {"messages": "not an array"}]})
        with self.assertRaises(ValueError):
            load_sessions(self.path)

    @staticmethod
    def chatgpt():
        def message(role, *parts):
            return {"author": {"role": role}, "content": {"parts": list(parts)}}
        return {
            "id": "export-id", "title": "Active branch", "create_time": 1700000000,
            "current_node": "chosen",
            "mapping": {
                "root": {"parent": None, "message": None},
                "question": {"parent": "root", "message": message("user", "Which value?", {"type": "image_asset_pointer", "asset_pointer": "ignored"})},
                "old": {"parent": "question", "message": message("assistant", "obsolete branch")},
                "chosen": {"parent": "question", "message": message("assistant", "active answer", "next paragraph")},
            },
        }

    def test_chatgpt_only_imports_current_branch_and_text(self):
        result = load_sessions(self.write([self.chatgpt()]), project="project")[0]
        self.assertEqual(result["session_id"], "export-id")
        self.assertEqual([item["content"] for item in result["messages"]], ["Which value?", "active answer\nnext paragraph"])
        self.assertTrue(result["created_at"].endswith("+00:00"))

    def test_chatgpt_refuses_ambiguous_broken_or_cyclic_branch(self):
        source = self.chatgpt()
        del source["current_node"]
        with self.assertRaisesRegex(ValueError, "current_node"):
            load_sessions(self.write(source), project="project")
        source = self.chatgpt()
        source["mapping"]["question"]["parent"] = "missing"
        with self.assertRaisesRegex(ValueError, "missing parent"):
            load_sessions(self.write(source), project="project")
        source["mapping"]["question"]["parent"] = "chosen"
        with self.assertRaisesRegex(ValueError, "cycle"):
            load_sessions(self.write(source), project="project")

    def test_claude_jsonl_groups_sessions_and_ignores_tool_blocks(self):
        self.jsonl(
            {"type": "user", "sessionId": "claude-1", "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": "Fix callback retry"}},
            {"type": "assistant", "sessionId": "claude-1", "message": {"role": "assistant", "content": [{"type": "text", "text": "Use exponential backoff."}, {"type": "tool_use", "name": "Bash", "input": {"command": "ignored"}}]}},
            {"type": "user", "sessionId": "claude-1", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ignored tool result"}]}},
            {"type": "user", "sessionId": "claude-2", "message": {"role": "user", "content": "New session"}},
            {"type": "progress", "data": "ignored"},
        )
        sessions = load_sessions(self.path, project="project", task_id="retry")
        self.assertEqual([s["session_id"] for s in sessions], ["claude-1", "claude-2"])
        self.assertEqual(len(sessions[0]["messages"]), 2)
        self.assertEqual(sessions[0]["messages"][1]["content"], "Use exponential backoff.")
        self.assertTrue(all(s["task_id"] == "retry" for s in sessions))

    def test_codex_response_items_are_not_duplicated_by_events(self):
        self.jsonl(
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z", "payload": {"id": "codex-1", "cwd": "/never-read-this-directory"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "Duplicate question"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Where is the key?"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "In the environment."}]}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "Duplicate answer"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "output": "ignored"}},
        )
        result = load_sessions(self.path, project="project")[0]
        self.assertEqual(result["session_id"], "codex-1")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][0]["content"], "Where is the key?")

    def test_no_supported_native_messages_is_an_error(self):
        for kind, record in (
            ("codex", {"type": "session_meta", "payload": {"id": "empty"}}),
            ("claude-code", {"type": "assistant", "sessionId": "empty", "message": {"role": "assistant", "content": [{"type": "tool_use"}]}}),
        ):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "no supported textual messages"):
                    load_sessions(self.write(record), format=kind, project="project")

    def test_arbitrary_empty_and_malformed_files_are_not_success(self):
        for source in (None, [], {}, {"random": "object"}, "unrelated text", 123):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    load_sessions(self.write(source), project="project")
        self.path.write_text("   \n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty"):
            load_sessions(self.path)
        self.path.write_text('{"type":"progress"}\nnot valid\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line 2"):
            load_sessions(self.path)

    def test_format_and_encoding_boundaries(self):
        self.write(self.canonical())
        with self.assertRaisesRegex(ValueError, "Unknown import format"):
            load_sessions(self.path, format="guess-silently")
        with self.assertRaises(ValueError):
            load_sessions(self.path, format="chatgpt")
        self.path.write_bytes(b"\xff\xfe\xff")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            load_sessions(self.path)
        self.path.write_text("\ufeff" + json.dumps(self.canonical()), encoding="utf-8")
        self.assertEqual(load_sessions(self.path)[0]["session_id"], "session-1")

    def test_oversized_file_fails_before_reading(self):
        with self.path.open("wb") as stream:
            stream.truncate(MAX_IMPORT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "64 MiB"):
            load_sessions(self.path)

    def test_text_parser_has_stable_watcher_fallback_without_opening_path(self):
        source = self.canonical()
        del source["session_id"]
        first = parse_sessions(json.dumps(source), "/never-open/transcript.json", fallback_id="stable-file")
        source["messages"].append({"role": "user", "content": "appended"})
        second = parse_sessions(json.dumps(source), "/never-open/transcript.json", fallback_id="stable-file")
        self.assertEqual(first[0]["session_id"], second[0]["session_id"])
        self.assertEqual(first[0]["session_id"], "stable-file")
        source["session_id"] = "native-id"
        self.assertEqual(parse_sessions(json.dumps(source), "unused.json", fallback_id="stable-file")[0]["session_id"], "native-id")

    @staticmethod
    def gemini_metadata():
        return {"sessionId": "gemini-1", "projectHash": "project-bucket",
                "startTime": "2026-01-01T00:00:00Z", "directories": ["/team/project"]}

    def test_gemini_legacy_json_uses_only_conversation_text(self):
        value = {**self.gemini_metadata(), "messages": [
            {"id": "u", "type": "user", "content": [{"text": "Question"}, {"inlineData": {"data": "ignored"}}]},
            {"id": "a", "type": "gemini", "content": [{"text": "Answer"}, {"text": "private reasoning", "thought": True}, {"functionCall": {"name": "ignored"}}]},
            {"id": "notice", "type": "warning", "content": "not conversation"},
        ]}
        result = load_sessions(self.write(value), project="project")[0]
        self.assertEqual(result["session_id"], "gemini-1")
        self.assertEqual(result["messages"], [{"role": "user", "content": "Question"}, {"role": "assistant", "content": "Answer"}])
        self.assertEqual(transcript_info(json.dumps(value))["workspaces"], ["/team/project"])

    def test_gemini_jsonl_replays_content_patches_deletion_and_order(self):
        records = [self.gemini_metadata(),
                   {"id": "u1", "type": "user", "content": "first"},
                   {"id": "a1", "type": "gemini", "content": "obsolete"},
                   {"id": "u2", "type": "user", "content": "second"},
                   {"id": "a2", "type": "gemini", "content": "remove this"},
                   {"$patch": {"id": "a1", "content": "patched", "updates": [{"id": "u2", "content": [{"text": "revised question"}]}],
                               "removeIds": ["a2"], "orderIds": ["u2", "a1"]}}]
        text = "\n".join(json.dumps(record) for record in records)
        result = parse_sessions(text, "session-test.jsonl", project="project")[0]
        self.assertEqual([message["content"] for message in result["messages"]], ["first", "revised question", "patched"])

    def test_gemini_rewind_removes_target_and_following_messages(self):
        records = [self.gemini_metadata(), {"id": "u1", "type": "user", "content": "keep"},
                   {"id": "a1", "type": "gemini", "content": "remove answer"},
                   {"id": "u2", "type": "user", "content": "remove later question"},
                   {"$rewindTo": "a1"}, {"id": "a-new", "type": "gemini", "content": "replacement"}]
        text = "\n".join(json.dumps(record) for record in records)
        result = parse_sessions(text, "session-test.jsonl", project="project")[0]
        self.assertEqual([message["content"] for message in result["messages"]], ["keep", "replacement"])
        records += [{"$rewindTo": "missing"}, {"id": "fresh", "type": "user", "content": "fresh branch"}]
        result = parse_sessions("\n".join(json.dumps(record) for record in records), "session-test.jsonl", project="project")[0]
        self.assertEqual([message["content"] for message in result["messages"]], ["fresh branch"])

    def test_gemini_set_replaces_messages_and_duplicate_id_updates_in_place(self):
        records = [self.gemini_metadata(), {"id": "old", "type": "user", "content": "discard"},
                   {"$set": {"messages": [{"id": "u", "type": "user", "content": "new question"},
                                          {"id": "a", "type": "gemini", "content": "first answer"}],
                             "directories": ["/another/project"]}},
                   {"id": "a", "type": "gemini", "content": "final answer"}]
        text = "\n".join(json.dumps(record) for record in records)
        result = parse_sessions(text, "session-test.jsonl", project="project")[0]
        self.assertEqual([message["content"] for message in result["messages"]], ["new question", "final answer"])
        self.assertEqual(transcript_info(text)["workspaces"], ["/another/project"])

    def test_gemini_malformed_patch_and_complete_line_are_rejected(self):
        for patch in ({"updates": None}, {"removeIds": False}, {"orderIds": "bad"}):
            text = json.dumps(self.gemini_metadata()) + "\n" + json.dumps({"$patch": patch})
            with self.assertRaises(ValueError):
                parse_sessions(text, "session-test.jsonl", project="project")
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_sessions(json.dumps(self.gemini_metadata()) + "\nnot valid\n", "session-test.jsonl", project="project")

    def test_kimi_legacy_context_skips_bookkeeping_and_thinking(self):
        records = [{"role": "_system_prompt", "content": "not user memory"},
                   {"role": "_usage", "token_count": 40}, {"role": "_checkpoint", "id": 2},
                   {"role": "user", "content": "User question"},
                   {"role": "assistant", "content": [{"type": "think", "think": "not imported"}, {"type": "text", "text": "Visible answer"}]},
                   {"role": "tool", "content": "Plain tool output"}]
        result = parse_sessions("\n".join(json.dumps(record) for record in records),
                                "/legacy/project/session-42/context.jsonl", project="legacy")[0]
        self.assertEqual(result["session_id"], "session-42")
        self.assertEqual([message["content"] for message in result["messages"]], ["User question", "Visible answer", "Plain tool output"])

    def test_current_kimi_index_is_not_a_transcript(self):
        with self.assertRaises(ValueError):
            parse_sessions('{"sessionId":"id","sessionDir":"/path","workDir":"/project"}',
                           "/unused/session_index.jsonl", project="project")


if __name__ == "__main__":
    unittest.main()
