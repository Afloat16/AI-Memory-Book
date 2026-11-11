"""Run the real reader in Chromium; intentionally outside unittest discovery.

    python -m pip install . playwright
    python -m playwright install --with-deps chromium  # unless Chrome is installed
    python tests/browser_smoke.py

Only synthetic conversations are used. Screenshots and a machine-readable report
are written to .artifacts/ so CI can retain evidence of the actual rendered UI.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import tempfile
import threading
from pathlib import Path

from memory_book import MemoryBook
from memory_book.web import make_server


def seed_book(path: Path) -> None:
    sessions = [
        {
            "project": "star-notes",
            "project_name": "星河笔记",
            "session_id": "sync-design",
            "title": "确定同步重试间隔",
            "task_id": "sync-retry",
            "task_title": "同步与重试",
            "created_at": "2026-11-01T09:00:00+08:00",
            "messages": [
                {"role": "user", "content": "笔记同步失败后，应该隔多久再试？"},
                {"role": "assistant", "content": "这份演示方案把重试间隔定为45秒。离线笔记继续保留在本机，恢复网络后增量同步，避免连续请求影响阅读体验。"},
            ],
        },
        {
            "project": "star-notes",
            "project_name": "星河笔记",
            "session_id": "sync-followup",
            "title": "补充同步的边界条件",
            "task_id": "sync-retry",
            "task_title": "同步与重试",
            "created_at": "2026-11-02T10:00:00+08:00",
            "messages": [
                {"role": "user", "content": "上次说的45秒重试，断网时也要一直执行吗？"},
                {"role": "assistant", "content": "不需要。断网时暂停请求；恢复网络后重新开始45秒的重试计时。这个结论延续同一任务的上一段会话。"},
            ],
        },
        {
            "project": "star-notes",
            "project_name": "星河笔记",
            "session_id": "offline-reading",
            "title": "让笔记可以离线阅读",
            "task_id": "offline-cache",
            "task_title": "离线阅读与缓存",
            "created_at": "2026-11-03T09:00:00+08:00",
            "messages": [
                {"role": "user", "content": "离线笔记保存在哪里？"},
                {"role": "assistant", "content": "演示决定：用 SQLite 保存本机笔记，保留修改记录，待网络恢复后同步。"},
            ],
        },
        {
            "project": "star-notes",
            "project_name": "星河笔记",
            "session_id": "release-checklist",
            "title": "首次发布前的检查",
            "task_id": "first-release",
            "task_title": "发布与回顾",
            "created_at": "2026-11-04T09:00:00+08:00",
            "messages": [
                {"role": "user", "content": "第一次发布需要确认什么？"},
                {"role": "assistant", "content": "先验证离线读取和冲突恢复，再确认导出文件可以重新导入。"},
            ],
        },
        {
            "project": "memory-book",
            "project_name": "AI Memory Book",
            "session_id": "book-design",
            "title": "设计问答记忆页",
            "task_id": "retrieval",
            "task_title": "检索与阅读预算",
            "created_at": "2026-11-05T09:00:00+08:00",
            "messages": [
                {"role": "user", "content": "怎样让检索返回的内容更集中？"},
                {"role": "assistant", "content": "保留问题的出处，把相关问答放在相邻页，并按阅读预算返回有用的片段。"},
            ],
        },
        {
            "project": "garden-notes",
            "project_name": "周末花园",
            "session_id": "garden-timer",
            "title": "记录花园的小事",
            "task_id": "garden",
            "task_title": "观察与记录",
            "created_at": "2026-11-06T09:00:00+08:00",
            "messages": [
                {"role": "user", "content": "演示计时器的时长是多少？"},
                {"role": "assistant", "content": "另一个项目的演示计时器是45秒。这段内容不应出现在星河笔记的限定项目检索中。"},
            ],
        },
    ]
    with MemoryBook(path) as book:
        for session in sessions:
            book.ingest(session)


def run(artifacts: Path, browser_executable: str | None = None) -> None:
    from playwright.sync_api import expect, sync_playwright

    artifacts.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running",
        "python": platform.python_version(),
        "fixture": "synthetic conversations; no user data",
        "checks": [],
        "page_errors": [],
        "console_errors": [],
        "unexpected_dialogs": [],
        "failed_requests": [],
    }
    executable = browser_executable or shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    report["browser_executable"] = executable or "Playwright-managed Chromium"
    page = None

    def checked(name: str) -> None:
        report["checks"].append(name)
        print(f"PASS: {name}", flush=True)

    def layout_check(name: str) -> None:
        widths = page.evaluate("""() => ({
            viewport: innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth
        })""")
        report[name] = widths
        assert widths["document"] <= widths["viewport"], f"Horizontal document overflow: {widths}"
        assert widths["body"] <= widths["viewport"], f"Horizontal body overflow: {widths}"
        checked(f"{name}: no horizontal overflow")

    try:
        with tempfile.TemporaryDirectory(prefix="memory-book-browser-") as temporary:
            db = Path(temporary) / "book.db"
            seed_book(db)
            server = make_server(db, port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with sync_playwright() as playwright:
                    options = {"headless": True}
                    if executable:
                        options["executable_path"] = executable
                    browser = playwright.chromium.launch(**options)
                    report["browser_version"] = browser.version
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000},
                        device_scale_factor=1,
                        locale="zh-CN",
                        color_scheme="light",
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    page.set_default_timeout(15_000)
                    page.on("pageerror", lambda exc: report["page_errors"].append(str(exc)))
                    page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
                    page.on("requestfailed", lambda request: report["failed_requests"].append({"url": request.url, "failure": request.failure}))

                    def unexpected_dialog(dialog) -> None:
                        report["unexpected_dialogs"].append(dialog.message)
                        dialog.dismiss()

                    page.on("dialog", unexpected_dialog)
                    try:
                        page.goto(server.reader_url, wait_until="networkidle")
                        expect(page.locator("#book-list .book-button")).to_have_count(4)
                        page.locator("#book-list .book-button").filter(has_text="星河笔记").click()
                        expect(page.locator("#page-title")).to_have_text("星河笔记")
                        expect(page.locator("#toc-list .chapter-button")).to_have_count(3)
                        checked("desktop project selection and table of contents")

                        page.locator("#toc-list .chapter-button").filter(has_text="同步与重试").click()
                        expect(page.locator("#results-title")).to_have_text("同步与重试")
                        expect(page.locator("#results .section")).to_have_count(2)
                        expect(page.locator("#results .page-row").first).to_be_visible()
                        checked("desktop chapter opens both source sessions")

                        page.locator("#query").fill("45秒")
                        page.locator("#search-button").click()
                        expect(page.locator("#results-title")).to_have_text("与这个问题有关的记忆")
                        expect(page.locator("#results .result-card")).to_have_count(2)
                        for excerpt in page.locator("#results .excerpt").all():
                            expect(excerpt).to_contain_text("45秒")
                        for crumbs in page.locator("#results .breadcrumb").all():
                            expect(crumbs).to_contain_text("星河笔记")
                            expect(crumbs).not_to_contain_text("周末花园")
                        expect(page.locator("#error-banner")).to_be_hidden()
                        checked("Chinese 45秒 search returns scoped evidence")

                        source_button = page.locator("#results .read-button").first
                        source_button.click()
                        expect(page.locator("#reader-overlay")).to_be_visible()
                        expect(page.locator("#reader-text")).to_contain_text("45秒")
                        expect(page.locator("#reader-error")).to_be_hidden()
                        assert page.locator(".shell").evaluate("node => node.inert")
                        page.locator("#reader-close").click()
                        expect(page.locator("#reader-overlay")).to_be_hidden()
                        expect(source_button).to_be_focused()
                        checked("source reader opens, closes, and restores keyboard focus")

                        page.screenshot(path=str(artifacts / "reader-desktop.png"), full_page=True, animations="disabled")
                        layout_check("desktop_layout")

                        # Translate only interface chrome; stored source text and
                        # user-provided titles must remain byte-for-byte identical.
                        original_excerpts = page.locator("#results .excerpt").all_text_contents()
                        original_titles = page.locator("#results .result-heading h3").all_text_contents()
                        page.locator("#language-toggle").click()
                        expect(page.locator("html")).to_have_attribute("lang", "en")
                        expect(page.locator("#search-button")).to_have_text("Find memories")
                        expect(page.locator("#results-title")).to_have_text("Memories related to your question")
                        expect(page.locator("#page-title")).to_have_text("星河笔记")
                        assert page.locator("#results .excerpt").all_text_contents() == original_excerpts
                        assert page.locator("#results .result-heading h3").all_text_contents() == original_titles
                        expect(page.locator("#results .read-button").first).to_have_text("Read source ↗")
                        page.screenshot(path=str(artifacts / "reader-desktop-en.png"), full_page=True, animations="disabled")
                        layout_check("english_desktop_layout")
                        page.locator("#language-toggle").click()
                        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
                        expect(page.locator("#search-button")).to_have_text("查找记忆")
                        assert page.locator("#results .excerpt").all_text_contents() == original_excerpts
                        checked("English/Chinese toggle preserves source text and titles")

                        imported = {
                            "project": "browser-import",
                            "project_name": "浏览器导入样例",
                            "session_id": "imported-session",
                            "title": "从浏览器收录一段对话",
                            "task_id": "import-flow",
                            "task_title": "导入与原文验证",
                            "messages": [
                                {"role": "user", "content": "怎样确认这段对话已经保存？"},
                                {"role": "assistant", "content": "导入标记：海盐书签。原文也可以包含 <script>window.__memoryBookInjected = true</script>，这些字符应该作为文本显示。"},
                            ],
                        }
                        page.locator("#import-open").click()
                        expect(page.locator("#import-overlay")).to_be_visible()
                        expect(page.locator("#import-submit")).to_be_disabled()
                        page.locator("#import-json").fill(json.dumps(imported, ensure_ascii=False, indent=2))
                        expect(page.locator("#import-preview")).to_be_visible()
                        expect(page.locator("#import-preview")).to_contain_text("browser-import")
                        expect(page.locator("#import-preview")).to_contain_text("消息：2 条")
                        expect(page.locator("#import-submit")).to_be_enabled()
                        with MemoryBook(db) as book:
                            assert not any(project["id"] == "browser-import" for project in book.projects()), "Preview unexpectedly wrote to the database"
                        page.locator("#import-submit").click()
                        expect(page.locator("#import-overlay")).to_be_hidden()
                        expect(page.locator("#page-title")).to_have_text("浏览器导入样例")
                        expect(page.locator("#toc-list .chapter-button")).to_have_count(1)
                        with MemoryBook(db) as book:
                            assert any(project["id"] == "browser-import" for project in book.projects())
                        checked("canonical JSON previews without mutation, then imports on confirmation")

                        page.locator("#toc-list .chapter-button").click()
                        expect(page.locator("#results .page-row")).to_have_count(1)
                        page.locator("#results .page-row").click()
                        expect(page.locator("#reader-text")).to_contain_text("海盐书签")
                        expect(page.locator("#reader-text")).to_contain_text("<script>")
                        expect(page.locator("#reader-text script")).to_have_count(0)
                        assert page.evaluate("window.__memoryBookInjected === undefined")
                        page.keyboard.press("Escape")
                        expect(page.locator("#reader-overlay")).to_be_hidden()
                        checked("imported source stays inert text and Escape closes the reader")

                        page.set_viewport_size({"width": 390, "height": 844})
                        page.locator("#book-list .book-button").filter(has_text="星河笔记").click()
                        expect(page.locator("#page-title")).to_have_text("星河笔记")
                        expect(page.locator("#mobile-contents")).to_be_visible()
                        expect(page.locator("#mobile-contents .chapter-button")).to_have_count(3)
                        expect(page.locator("#toc-list")).to_be_hidden()
                        expect(page.locator("#toast")).to_be_hidden(timeout=7_000)
                        page.screenshot(path=str(artifacts / "reader-mobile.png"), full_page=True, animations="disabled")
                        layout_check("mobile_layout")
                        page.locator("#mobile-contents .chapter-button").filter(has_text="同步与重试").click()
                        expect(page.locator("#results-title")).to_have_text("同步与重试")
                        expect(page.locator("#results .section")).to_have_count(2)
                        checked("390px mobile table of contents opens a chapter")

                        # A fresh browser profile must follow navigator.language,
                        # independently of the first profile's saved preference.
                        english_context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1000})
                        try:
                            english_page = english_context.new_page()
                            english_page.on("pageerror", lambda exc: report["page_errors"].append("English profile: " + str(exc)))
                            english_page.on("console", lambda message: report["console_errors"].append("English profile: " + message.text) if message.type == "error" else None)
                            english_page.goto(server.reader_url, wait_until="networkidle")
                            expect(english_page.locator("html")).to_have_attribute("lang", "en")
                            expect(english_page.locator("#search-button")).to_have_text("Find memories")
                            expect(english_page.locator("#language-toggle")).to_have_text("中文")
                            english_page.set_viewport_size({"width": 390, "height": 844})
                            english_page.locator("#book-list .book-button").filter(has_text="星河笔记").click()
                            expect(english_page.locator("#mobile-contents")).to_be_visible()
                            assert english_page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "English mobile layout overflows"
                            checked("fresh English browser defaults to English and fits a 390px viewport")
                        finally:
                            english_context.close()

                        assert not report["page_errors"], f"JavaScript page errors: {report['page_errors']}"
                        assert not report["console_errors"], f"Browser console errors: {report['console_errors']}"
                        assert not report["unexpected_dialogs"], f"Unexpected browser dialogs: {report['unexpected_dialogs']}"
                        assert not report["failed_requests"], f"Failed browser requests: {report['failed_requests']}"
                        checked("no page errors, console errors, unexpected dialogs, or failed requests")
                    except BaseException:
                        if page and not page.is_closed():
                            try:
                                page.screenshot(path=str(artifacts / "reader-failure.png"), full_page=True, animations="disabled")
                            except Exception as screenshot_error:
                                report["failure_screenshot_error"] = str(screenshot_error)
                        raise
                    finally:
                        context.close()
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (artifacts / "reader-browser.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, default=Path(".artifacts"))
    parser.add_argument("--browser-executable", help="Optional existing Chrome or Chromium executable")
    arguments = parser.parse_args()
    run(arguments.artifacts_dir, arguments.browser_executable)


if __name__ == "__main__":
    main()
