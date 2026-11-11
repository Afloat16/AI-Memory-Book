from __future__ import annotations

import copy
import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from memory_book import MemoryBook
from memory_book.cli import export_book, main
from memory_book.segmentation import make_turns, segment
from memory_book.text import excerpt, query_terms


def session(project="alpha", sid="s1", task="cache", answer="缓存有效期设为45秒。"):
    return {"project": project, "session_id": sid, "task_id": task, "task_title": "报价缓存", "title": "缓存设计", "created_at": "2026-10-01T08:00:00Z", "messages": [{"role": "user", "content": "报价缓存多久失效？"}, {"role": "assistant", "content": answer}]}


class BookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "book.db"
        self.book = MemoryBook(self.path)

    def tearDown(self):
        self.book.close()
        self.temp.cleanup()

    def test_idempotent_ingestion(self):
        first = self.book.ingest(session())
        second = self.book.ingest(session())
        self.assertFalse(first["skipped"])
        self.assertTrue(second["skipped"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(self.book.stats()["pages"], 1)

    def test_chinese_recall_and_source(self):
        self.book.ingest(session())
        result = self.book.recall("报价缓存有效期", project="alpha")
        hit = result["results"][0]
        self.assertIn("45秒", hit["text"])
        self.assertEqual(hit["source_refs"][0]["turn_index"], 0)
        self.assertEqual(hit["source_refs"][0]["session_id"], "s1")
        self.assertEqual([c["kind"] for c in hit["breadcrumb"]], ["project", "chapter", "section", "page"])
        self.assertEqual(self.book.read(hit["id"])["content"], hit["text"])

    def test_project_filter_applied_before_candidate_limit(self):
        self.book.ingest(session(answer="报价缓存使用specialtarget策略。"))
        for i in range(105):
            self.book.ingest(session("other", f"s{i}", answer="报价缓存多久失效？报价缓存多久失效？45秒。"))
        result = self.book.recall("报价缓存", project="alpha")
        self.assertEqual(len(result["results"]), 1)
        self.assertIn("specialtarget", result["context"])
        self.assertTrue(all(r["project"] == "alpha" for h in result["results"] for r in h["source_refs"]))

    def test_cross_session_explicit_task(self):
        first = self.book.ingest(session())
        second = self.book.ingest(session(sid="s2", answer="报价每分钟更新两次。"))
        self.assertEqual(first["chapter_id"], second["chapter_id"])
        self.assertEqual(self.book.toc("alpha")["chapters"][0]["sessions"], 2)
        result = self.book.recall("报价缓存失效", project="alpha")
        self.assertEqual({r["session_id"] for h in result["results"] for r in h["source_refs"]}, {"s1", "s2"})

    def test_no_implicit_cross_session_merge(self):
        self.book.ingest(session(task=""))
        self.book.ingest(session(sid="s2", task=""))
        self.assertEqual(self.book.stats()["chapters"], 2)

    def test_cache_persists_and_updates_invalidate_other_connections(self):
        self.book.ingest(session())
        self.assertFalse(self.book.recall("缓存")["cache_hit"])
        self.assertTrue(self.book.recall("缓存")["cache_hit"])
        with MemoryBook(self.path) as other:
            self.assertTrue(other.recall("缓存")["cache_hit"])
            other.ingest(session(answer="缓存已调整为72秒。"))
        result = self.book.recall("缓存")
        self.assertFalse(result["cache_hit"])
        self.assertIn("72秒", result["context"])
        self.assertNotIn("45秒", result["context"])

    def test_updated_page_address_does_not_resolve_to_new_text(self):
        self.book.ingest(session())
        old = self.book.recall("缓存")["results"][0]["id"]
        self.book.ingest(session(answer="缓存有效期调整为70秒。"))
        with self.assertRaises(KeyError):
            self.book.read(old)

    def test_delete_cascades_fts_and_cache(self):
        self.book.ingest(session())
        self.book.recall("缓存")
        self.assertTrue(self.book.delete_session("alpha", "s1"))
        self.assertEqual(self.book.recall("缓存")["results"], [])
        self.assertEqual(self.book.db.execute("SELECT COUNT(*) FROM pages_fts").fetchone()[0], 0)
        self.assertEqual(self.book.stats()["chapters"], 0)
        self.assertFalse(self.book.delete_session("alpha", "s1"))

    def test_project_delete_is_scoped(self):
        self.book.ingest(session())
        self.book.ingest(session("beta"))
        self.assertTrue(self.book.delete_project("alpha"))
        self.assertEqual(self.book.stats()["projects"], 1)
        self.assertEqual(self.book.recall("缓存", project="alpha")["results"], [])
        self.assertEqual(len(self.book.recall("缓存", project="beta")["results"]), 1)

    def test_budget_includes_citations(self):
        self.book.ingest(session(answer="报价缓存文档。" * 900))
        for budget in (0, 1, 50, 150, 250, 1000, 4000):
            result = self.book.recall("报价缓存", budget_chars=budget, use_cache=False)
            self.assertLessEqual(len(result["context"]), budget)
            self.assertEqual(len(result["context"]), result["context_chars"])
            for hit in result["results"]:
                self.assertIn(hit["id"], result["context"])

    def test_long_answer_reconstructs_without_losing_characters(self):
        payload = session(answer="前段信息\n\n" * 300 + "关键结论targetvalue\n" + "尾部说明" * 500)
        self.book.ingest(payload)
        chapter = self.book.chapter(self.book.toc("alpha")["chapters"][0]["id"])
        pages = [self.book.read(p["id"])["content"] for s in chapter["sections"] for p in s["pages"]]
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(p) <= 1800 for p in pages))
        self.assertEqual("".join(pages), make_turns(payload["messages"])[0].content)
        result = self.book.recall("targetvalue", budget_chars=1500)
        self.assertIn("targetvalue", result["context"])

    def test_read_pagination(self):
        self.book.ingest(session(answer="缓存" * 400))
        page_id = self.book.recall("缓存")["results"][0]["id"]
        full = self.book.read(page_id)["content"]
        a = self.book.read(page_id, limit=17)
        b = self.book.read(page_id, offset=a["next_offset"], limit=10000)
        self.assertEqual(a["content"] + b["content"], full)

    def test_export_round_trip(self):
        self.book.ingest(session())
        self.book.ingest(session(sid="s2"))
        raw = self.book.export()
        with MemoryBook(":memory:") as other:
            for payload in raw:
                other.ingest(payload)
            self.assertEqual(other.export(), raw)
            self.assertEqual(other.recall("缓存")["context"], self.book.recall("缓存")["context"])

    def test_markdown_export_is_complete(self):
        self.book.ingest(session())
        output = Path(self.temp.name) / "export"
        info = export_book(self.book, "alpha", str(output))
        self.assertEqual(info["pages"], 1)
        self.assertIn("报价缓存", (output / "INDEX.md").read_text())
        self.assertEqual(len(json.loads((output / "sessions.json").read_text())), 1)
        self.assertIn("45秒", next((output / "pages").glob("*.md")).read_text())

    def test_long_section_directory_and_export_page_everything(self):
        self.book.ingest(session(answer="缓存详细说明。" * 6000))
        chapter = self.book.chapter(self.book.toc("alpha")["chapters"][0]["id"])
        section = chapter["sections"][0]
        self.assertEqual(len(section["pages"]), 20)
        self.assertGreater(section["pages_total"], 20)
        next_part = self.book.section(section["id"], offset=section["pages_next_offset"])
        self.assertEqual(len(section["pages"]) + len(next_part["pages"]), section["pages_total"])
        info = export_book(self.book, "alpha", str(Path(self.temp.name) / "long-export"))
        self.assertEqual(info["pages"], self.book.stats()["pages"])

    def test_invalid_import_leaves_existing_data_unchanged(self):
        self.book.ingest(session())
        before = self.book.stats()
        payload = session()
        payload["messages"][0]["content"] = {"bad": "not text"}
        with self.assertRaises(ValueError):
            self.book.ingest(payload)
        self.assertEqual(before, self.book.stats())

    def test_invalid_role_is_a_validation_error(self):
        payload = session()
        payload["messages"][0]["role"] = []
        with self.assertRaises(ValueError):
            self.book.ingest(payload)

    def test_default_timestamp_survives_export_import(self):
        payload = session()
        del payload["created_at"]
        self.book.ingest(payload)
        exported = self.book.export()[0]
        self.assertTrue(exported["created_at"])
        with MemoryBook(":memory:") as other:
            other.ingest(exported)
            self.assertEqual(other.export()[0]["created_at"], exported["created_at"])
            self.assertEqual(other.recall("缓存")["context"], self.book.recall("缓存")["context"])

    def test_omitted_names_preserve_existing_names(self):
        original = session()
        original.update(project_name="Friendly project", task_title="Named cache chapter")
        self.book.ingest(original)
        followup = session(sid="followup")
        del followup["task_title"]
        self.book.ingest(followup)
        self.assertEqual(self.book.projects()[0]["name"], "Friendly project")
        self.assertEqual(self.book.toc("alpha")["chapters"][0]["title"], "Named cache chapter")

    def test_chapter_rename_reindexes_existing_pages(self):
        self.book.ingest(session())
        payload = session(sid="followup")
        payload["task_title"] = "Renamed cache"
        self.book.ingest(payload)
        directories = self.book.db.execute("SELECT directory FROM pages_fts").fetchall()
        self.assertTrue(all("renamed" in row[0] for row in directories))

    def test_link_preserves_segmentation_and_page_ids(self):
        payload = session()
        payload["messages"] *= 3
        with MemoryBook(self.path, segmentation="turn", max_page_chars=900) as importer:
            importer.ingest(payload)
        before = [r[0] for r in self.book.db.execute("SELECT id FROM pages ORDER BY id")]
        self.book.link_session("alpha", "s1", "other", title="Another task")
        after = [r[0] for r in self.book.db.execute("SELECT id FROM pages ORDER BY id")]
        self.assertEqual(before, after)
        self.assertEqual(len(after), 3)

    def test_link_preserves_current_project_and_target_chapter_names(self):
        old = session()
        old.update(project_name="Old project", task_title="Old chapter")
        self.book.ingest(old)
        target = session(sid="s2", task="target")
        target.update(project_name="Current project", task_title="Target friendly name")
        self.book.ingest(target)
        self.book.link_session("alpha", "s1", "target")
        self.assertEqual(self.book.projects()[0]["name"], "Current project")
        self.assertEqual(self.book.toc("alpha")["chapters"][0]["title"], "Target friendly name")

    def test_v1_migration_keeps_timestamps_pages_and_rebuilds_lexical_index(self):
        from memory_book.store import SCHEMA
        legacy_path = Path(self.temp.name) / "legacy.db"
        legacy = sqlite3.connect(legacy_path, isolation_level=None)
        schema = SCHEMA.replace(" settings_json TEXT NOT NULL DEFAULT '{}',\n", "").replace("PRAGMA user_version = 2;", "PRAGMA user_version = 1;")
        legacy.executescript(schema)
        stamp = "2025-01-02T03:04:05+00:00"
        payload = session(answer="OAuth认证使用café测试账户。")
        payload["created_at"] = ""
        legacy.execute("INSERT INTO projects VALUES('alpha','alpha',?,?)", (stamp,stamp))
        legacy.execute("INSERT INTO chapters VALUES('c','alpha','task:cache','cache','',?)", (stamp,))
        legacy.execute("INSERT INTO sessions VALUES('s','s1','alpha','c','title',?,?, 'oldhash',?,'adaptive',2,1,30)", (stamp,stamp,json.dumps(payload)))
        legacy.execute("INSERT INTO sections VALUES('sec','s','c','section','',0)")
        legacy.execute("INSERT INTO pages VALUES(1,'legacy-page','sec','s','c','alpha','title','OAuth认证','OAuth认证使用café测试账户。','[]',0)")
        legacy.execute("INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(1,'title','oauth认证','oauth认证','cache')")
        legacy.close()
        with MemoryBook(legacy_path) as migrated:
            self.assertEqual(migrated.stats()["schema_version"], 2)
            self.assertEqual(migrated.export()[0]["created_at"], stamp)
            self.assertEqual(migrated.read("legacy-page")["content"], "OAuth认证使用café测试账户。")
            self.assertIn("OAuth", migrated.recall("认证")["context"])

    def test_cli_export_cannot_overwrite_database_or_symlink(self):
        self.book.ingest(session())
        alias = Path(self.temp.name) / "alias.json"
        alias.symlink_to(self.path)
        for output in (self.path, alias, Path(str(self.path) + "-wal")):
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["--db", str(self.path), "export", "--output", str(output)])
            self.assertEqual(code, 2)
        self.assertIn("45秒", self.book.recall("缓存")["context"])

    def test_mixed_script_and_accent_recall(self):
        payload = session(answer="OAuth认证使用café测试账户。")
        self.book.ingest(payload)
        for query in ("认证", "OAuth", "cafe", "café"):
            self.assertIn("café", self.book.recall(query)["context"])

    def test_directory_only_match_is_not_evidence(self):
        payload = session(answer="Only ordinary body text.")
        payload.update(task_title="absentkeyword")
        self.book.ingest(payload)
        self.assertFalse(self.book.recall("absentkeyword")["results"])

    def test_long_prompt_index_metadata_is_bounded(self):
        payload = session()
        payload["messages"][0]["content"] = "needle " * 15000
        self.book.ingest(payload)
        counts = self.book.db.execute("SELECT SUM(length(question)), SUM(length(content)), COUNT(*) FROM pages").fetchone()
        self.assertLess(counts[0], counts[1])
        self.assertGreater(counts[2], 50)

    def test_transaction_rolls_back_derived_index_failure(self):
        self.book.ingest(session())
        before = self.book.export()
        self.book.db.execute("CREATE TRIGGER simulated_failure BEFORE INSERT ON pages BEGIN SELECT RAISE(ABORT, 'simulated'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.book.ingest(session(answer="缓存新值99秒"))
        self.assertEqual(self.book.export(), before)
        self.assertIn("45秒", self.book.recall("缓存")["context"])

    def test_relink_prunes_old_chapter(self):
        self.book.ingest(session(task="old"))
        before = self.book.toc("alpha")["chapters"][0]["id"]
        self.book.ingest(session(task="new"))
        self.assertEqual(self.book.stats()["chapters"], 1)
        with self.assertRaises(KeyError):
            self.book.chapter(before)

    def test_fts_input_is_not_query_language(self):
        self.book.ingest(session())
        for query in ('" OR * NOT NEAR() -', "'; DROP TABLE pages; --", "缓存 OR \"", "", "   ", "💭"):
            self.book.recall(query)
        self.assertEqual(self.book.stats()["pages"], 1)

    def test_unknown_fields_and_parameters(self):
        for kwargs in ({"budget_chars": -1}, {"budget_chars": True}, {"limit": 0}, {"strategy": "anything"}):
            with self.assertRaises(ValueError):
                self.book.recall("cache", **kwargs)
        with self.assertRaises(ValueError):
            MemoryBook(":memory:", max_page_chars=50)
        with self.assertRaises(KeyError):
            self.book.toc("missing")

    def test_bounded_persistent_cache(self):
        self.book.cache_size = 2
        self.book.ingest(session())
        for q in ("缓存", "报价", "有效期", "unknown"):
            self.book.recall(q)
        self.assertEqual(self.book.stats()["cache_entries"], 2)

    def test_concurrent_reader_writer_consistency(self):
        self.book.ingest(session())
        errors = []
        def writer():
            try:
                with MemoryBook(self.path) as book:
                    for i in range(10):
                        book.ingest(session(answer=f"缓存版本{i}，值保持一致。"))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=writer)
        thread.start()
        for _ in range(10):
            result = self.book.recall("缓存")
            self.assertLessEqual(result["context_chars"], 4000)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertIn("版本9", self.book.recall("缓存")["context"])

    def test_rejects_unrelated_database(self):
        other_path = Path(self.temp.name) / "unrelated.db"
        conn = sqlite3.connect(other_path)
        conn.execute("CREATE TABLE example (value TEXT)")
        conn.close()
        with self.assertRaises(ValueError):
            MemoryBook(other_path)


class TextTests(unittest.TestCase):
    def test_source_span_matches_excerpt(self):
        text = "noise " * 100 + "target details essential" + " suffix" * 100
        value, spans = excerpt(text, "target details", 120)
        self.assertIn("target", value)
        self.assertLessEqual(len(value), 120)
        self.assertEqual(value.strip("…"), text[spans[0][0]:spans[0][1]])

    def test_tokenize_chinese_and_identifiers(self):
        self.assertIn("缓存", query_terms("为什么缓存失效？"))
        self.assertIn("connection", query_terms("database_connection_timeout"))
        self.assertIn("timeout", query_terms("connectionTimeout"))

    def test_question_and_possessive_fragments_do_not_route_queries(self):
        self.assertNotIn("s", query_terms("What is Jupiter's diameter?"))
        self.assertNotIn("为什", query_terms("为什么缓存失效？"))
        self.assertNotIn("re", query_terms("We're asking about cache"))

    def test_three_modes_and_followup(self):
        messages = [{"role": "user", "content": "How long is the cache?"}, {"role": "assistant", "content": "45 seconds."}, {"role": "user", "content": "And why?"}, {"role": "assistant", "content": "Updates are frequent."}]
        turns = make_turns(messages)
        self.assertEqual(len(segment(turns, "turn", 1800, 400, .12)), 2)
        for mode in ("adaptive", "session"):
            sections = segment(turns, mode, 1800, 400, .12)
            self.assertEqual(len(sections), 1)
            self.assertEqual({ref["turn_index"] for p in sections[0].pages for ref in p.refs}, {0, 1})


if __name__ == "__main__":
    unittest.main()
