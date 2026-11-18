"""Evidence integrity checks for additional actual upstream components.

Actual-package API execution is a separate recorded smoke, not simulated here.
These tests exercise malformed/foreign native evidence and report boundaries.
"""
from __future__ import annotations

import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from benchmarks.competitors.extended_lexical import memvid_record, result_identity
from benchmarks.extended_components import fresh_output, validate_native


class ExtendedComponentIntegrityTests(unittest.TestCase):
    def memvid_fixture(self, project="scope-alpha", text="USER: valve\n\nASSISTANT: 值=17."):
        identity = "page-1"
        doc = {"id": identity, "project": project, "title": "Valve settings",
               "text": text, "created_at": "2026-01-01T09:00:00+00:00"}
        uri = f"memory-book://{quote(project, safe='')}/{identity}"
        frame = {"id": 7, "uri": uri, "title": doc["title"],
                 "timestamp": int(datetime.fromisoformat(doc["created_at"]).timestamp()),
                 "tags": [], "labels": ["text"], "extra_metadata": {
                     "page_id": json.dumps(identity), "project": json.dumps(project)}}
        indexed = (text + f"\ntitle: {doc['title']}\nuri: {uri}\nlabels: text"
                   + "\npage_id: " + json.dumps(identity) + "\nproject: " + json.dumps(project))
        hit = {"frame_id": 7, "uri": uri, "title": doc["title"], "text": " ".join(indexed.split()),
               "tags": [], "labels": ["text"], "score": 1.25}
        return doc, hit, frame

    def test_memvid_requires_entire_body_and_framing(self):
        doc, hit, frame = self.memvid_fixture()
        expected = {key: doc[key] for key in ("id", "project", "text")}
        self.assertEqual(memvid_record(hit, frame, {doc["id"]: doc}, doc["project"]), expected)
        for altered in (hit["text"] + " forged", hit["text"].replace("值=17.", "值=18."),
                        hit["text"].replace("ASSISTANT: 值=17. ", "")):
            with self.subTest(text=altered), self.assertRaises(ValueError):
                memvid_record({**hit, "text": altered}, frame, {doc["id"]: doc}, doc["project"])

    def test_memvid_no_foreign_missing_or_metadata_laundering(self):
        doc, hit, frame = self.memvid_fixture()
        variants = [({}, hit, frame), ({doc["id"]: {**doc, "project": "other"}}, hit, frame),
                    ({doc["id"]: doc}, {**hit, "frame_id": 8}, frame),
                    ({doc["id"]: doc}, hit, {**frame, "title": "foreign title"}),
                    ({doc["id"]: doc}, hit, {**frame, "timestamp": frame["timestamp"] + 1}),
                    ({doc["id"]: doc}, hit, {**frame, "extra_metadata": {
                        **frame["extra_metadata"], "unregistered": "extra"}})]
        for lookup, altered_hit, altered_frame in variants:
            with self.subTest(frame=altered_frame), self.assertRaises(ValueError):
                memvid_record(altered_hit, altered_frame, lookup, doc["project"])

    def test_memvid_project_prefix_collision_is_rejected(self):
        doc, hit, frame = self.memvid_fixture("scope-alpha/child")
        self.assertIn("scope-alpha%2Fchild", hit["uri"])
        self.assertEqual(memvid_record(hit, frame, {doc["id"]: doc}, doc["project"])["project"], doc["project"])
        with self.assertRaises(ValueError):
            memvid_record(hit, frame, {doc["id"]: doc}, "scope-alpha")

    def test_native_payload_cannot_be_replaced_by_locally_mapped_text(self):
        doc, hit, frame = self.memvid_fixture()
        native = {"hit_ids": [doc["id"]], "records": [{key: doc[key] for key in ("id", "project", "text")}],
                  "scores": [hit["score"]], "native_payload": {"engine": "tantivy", "hits": [hit]},
                  "native_frames": [frame]}
        self.assertEqual(validate_native("memvid_lex", native, {doc["id"]: doc}, doc["project"]), [doc["id"]])
        altered = copy.deepcopy(native)
        altered["native_payload"]["hits"][0]["text"] = "truncated"
        with self.assertRaises(ValueError):
            validate_native("memvid_lex", altered, {doc["id"]: doc}, doc["project"])
        altered = copy.deepcopy(native)
        altered["scores"][0] = 99
        with self.assertRaises(ValueError):
            validate_native("memvid_lex", altered, {doc["id"]: doc}, doc["project"])

    def test_stability_checks_original_body_order_and_native_score(self):
        value = {"hit_ids": ["a"], "records": [{"id": "a", "text": "one", "project": "p"}],
                 "scores": [0.5], "search_ms": 10, "native_payload": {"took_ms": 5}}
        changed_time = copy.deepcopy(value)
        changed_time["search_ms"] = 99
        self.assertEqual(result_identity(value), result_identity(changed_time))
        for key, changed in (("scores", [0.6]), ("hit_ids", ["b"]),
                             ("records", [{"id": "a", "text": "two", "project": "p"}])):
            self.assertNotEqual(result_identity(value), result_identity({**value, key: changed}))

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = fresh_output(Path(temporary) / "attempt")
            (path / "failure.json").write_text("original failure")
            with self.assertRaises(ValueError):
                fresh_output(path)
            self.assertEqual((path / "failure.json").read_text(), "original failure")


if __name__ == "__main__":
    unittest.main()
