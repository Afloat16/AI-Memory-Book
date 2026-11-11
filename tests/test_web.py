"""The local reader's authorization boundary and end-to-end data paths."""

from __future__ import annotations

import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from memory_book import MemoryBook
from memory_book.web import MAX_IMPORT_BYTES, make_server


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmp.name) / "book.db"
        cls.server = make_server(cls.db_path, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]
        cls.origin = f"http://127.0.0.1:{cls.port}"
        status, headers, html = cls.request("GET", "/")
        assert status == 200
        cls.token = re.search(r'name="memory-book-token" content="([^"]+)"', html.decode()).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def import_headers(self, **overrides):
        return {"Origin": self.origin, "X-Memory-Book-Token": self.token, "Content-Type": "application/json", **overrides}

    def test_html_has_local_content_policy_and_no_cors(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("script-src 'nonce-", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("记忆书", body.decode("utf-8"))
        self.assertNotIn(b"__MEMORY_BOOK_NONCE__", body)

    def test_dns_rebinding_host_is_rejected(self):
        status, _, _ = self.request("GET", "/api/projects", headers={"Host": f"attacker.example:{self.port}"})
        self.assertEqual(status, 403)

    def test_public_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            make_server(":memory:", "0.0.0.0", 0)

    def test_mutation_requires_origin_and_token(self):
        status, _, _ = self.request("POST", "/api/import", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/import", b"{}", self.import_headers(Origin="https://attacker.example"))
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/import", b"{}", self.import_headers(**{"X-Memory-Book-Token": "wrong"}))
        self.assertEqual(status, 403)

    def test_oversized_upload_is_rejected_before_reading(self):
        headers = self.import_headers(**{"Content-Length": str(MAX_IMPORT_BYTES + 1)})
        status, _, _ = self.request("POST", "/api/import", b"", headers)
        self.assertEqual(status, 413)

    def test_malformed_payloads_do_not_crash_reader(self):
        for body in (b"{", b"[]", b"null", b"\xff"):
            with self.subTest(body=body):
                status, _, raw = self.request("POST", "/api/import", body, self.import_headers())
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(raw))

    def test_query_and_pagination_validation(self):
        for path in ("/api/recall?q=", "/api/recall?q=cache&budget_chars=2", "/api/read?id=x&offset=-1", "/api/toc?project=x&limit=200", "/api/recall?q=a&q=b", "/api/section", "/api/section?id=x&offset=-1", "/api/chapter?id=x&page_limit=101"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 400)

    def test_unknown_resource_is_not_found(self):
        status, _, _ = self.request("GET", "/../../etc/passwd")
        self.assertEqual(status, 404)

    def test_import_browse_recall_and_read(self):
        payload = {
            "project": "reader-test",
            "session_id": "reader-session",
            "title": "缓存选择",
            "task_id": "cache-design",
            "task_title": "缓存设计",
            "messages": [
                {"role": "user", "content": "缓存为什么选择 SQLite？"},
                {"role": "assistant", "content": "SQLite 缓存用于离线读取，决定保留 WAL 模式。<script>alert('x')</script>"},
            ],
        }
        status, _, raw = self.request("POST", "/api/import", json.dumps(payload).encode(), self.import_headers())
        self.assertEqual(status, 200, raw)
        status, _, raw = self.request("GET", "/api/projects")
        self.assertEqual(status, 200, raw)
        projects = json.loads(raw)
        project = next(item for item in projects if item["id"] == "reader-test")
        self.assertEqual(project["sessions"], 1)
        status, _, raw = self.request("GET", "/api/toc?project=reader-test")
        self.assertEqual(status, 200, raw)
        chapter = json.loads(raw)["chapters"][0]
        status, _, raw = self.request("GET", "/api/chapter?id=" + chapter["id"])
        self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["sections"])
        status, _, raw = self.request("GET", "/api/recall?q=SQLite&project=reader-test&budget_chars=2000")
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        self.assertTrue(result["results"])
        self.assertLessEqual(result["context_chars"], 2000)
        page_id = result["results"][0]["id"]
        status, _, raw = self.request("GET", "/api/read?id=" + page_id)
        self.assertEqual(status, 200, raw)
        self.assertIn("WAL", json.loads(raw)["content"])

    def test_toc_and_chapter_continue_without_duplicate_sections(self):
        with MemoryBook(self.db_path) as book:
            for index in range(53):
                book.ingest({
                    "project": "reader-pagination",
                    "session_id": f"session-{index}",
                    "title": f"Conversation {index}",
                    "task_id": f"task-{index}",
                    "messages": [{"role": "user", "content": "A question"}, {"role": "assistant", "content": "An answer"}],
                })
            for index in range(23):
                book.ingest({
                    "project": "reader-sections",
                    "session_id": f"session-{index}",
                    "task_id": "shared-task",
                    "messages": [{"role": "user", "content": f"Question {index}"}, {"role": "assistant", "content": "An answer"}],
                })
        status, _, raw = self.request("GET", "/api/toc?project=reader-pagination")
        self.assertEqual(status, 200, raw)
        first = json.loads(raw)
        self.assertEqual(len(first["chapters"]), 50)
        self.assertEqual(first["next_offset"], 50)
        status, _, raw = self.request("GET", "/api/toc?project=reader-pagination&offset=50")
        self.assertEqual(status, 200, raw)
        second = json.loads(raw)
        self.assertEqual(len(second["chapters"]), 3)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(len({item["id"] for item in first["chapters"] + second["chapters"]}), 53)
        status, _, raw = self.request("GET", "/api/toc?project=reader-sections")
        chapter_id = json.loads(raw)["chapters"][0]["id"]
        offset, ids = 0, []
        while offset is not None:
            status, _, raw = self.request("GET", "/api/chapter?" + urlencode({"id": chapter_id, "offset": offset, "limit": 7}))
            self.assertEqual(status, 200, raw)
            part = json.loads(raw)
            self.assertLessEqual(len(part["sections"]), 7)
            ids.extend(section["id"] for section in part["sections"])
            offset = part["next_offset"]
        self.assertEqual(len(ids), 23)
        self.assertEqual(len(set(ids)), 23)

    def test_long_section_pages_are_bounded_and_fully_pageable(self):
        answer = "\n\n".join(f"Record {index}: " + "An offline cache keeps a bounded page. " * 10 for index in range(70))
        with MemoryBook(self.db_path, max_page_chars=500, min_page_chars=100) as book:
            imported = book.ingest({
                "project": "reader-long-section",
                "session_id": "long-answer",
                "messages": [{"role": "user", "content": "Describe cache records"}, {"role": "assistant", "content": answer}],
            })
        status, _, raw = self.request("GET", "/api/chapter?" + urlencode({"id": imported["chapter_id"]}))
        self.assertEqual(status, 200, raw)
        section = json.loads(raw)["sections"][0]
        self.assertGreater(section["pages_total"], 20)
        self.assertEqual(len(section["pages"]), 20)
        self.assertEqual(section["pages_next_offset"], 20)
        offset = section["pages_next_offset"]
        ids = [page["id"] for page in section["pages"]]
        while offset is not None:
            status, _, raw = self.request("GET", "/api/section?" + urlencode({"id": section["id"], "offset": offset, "limit": 7}))
            self.assertEqual(status, 200, raw)
            part = json.loads(raw)
            self.assertLessEqual(len(part["pages"]), 7)
            ids.extend(page["id"] for page in part["pages"])
            offset = part["next_offset"]
        self.assertEqual(len(ids), section["pages_total"])
        self.assertEqual(len(set(ids)), len(ids))


if __name__ == "__main__":
    unittest.main()
