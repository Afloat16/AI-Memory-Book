#!/usr/bin/env python3
"""Render the README's exact-data SVG figures, without third-party packages.

The committed JSON is a presentation snapshot of source-bound evidence. This
script does not execute benchmarks or replace their original reports.
"""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/readme-assets"
INK, MUTED = "#152d43", "#52677b"
TEAL, BLUE, PALE = "#087f75", "#527daf", "#a8bbce"
BG, LINE, WHITE = "#f7fafc", "#dbe5ed", "#ffffff"
AMBER = "#975c0a"


class SVG:
    def __init__(self, height: int, title: str, description: str, lang: str):
        self.text_count = 0
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" '
                      f'viewBox="0 0 960 {height}" role="img" aria-labelledby="title desc" lang="{lang}">',
                      f'<title id="title">{escape(title)}</title>',
                      f'<desc id="desc">{escape(description)}</desc>',
                      '<style>text{font-family:Inter,"Noto Sans CJK SC",Arial,sans-serif;'
                      'font-variant-numeric:tabular-nums} .kicker{letter-spacing:1.6px}</style>']
        self.rect(1, 1, 958, height - 2, BG, radius=20, stroke=LINE)

    def rect(self, x, y, w, h, fill, radius=0, stroke=None):
        self.parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" '
                          f'rx="{radius}" fill="{fill}"' + (f' stroke="{stroke}"' if stroke else '') + '/>')

    def text(self, x, y, value, size=18, fill=INK, weight=400, anchor="start", cls=""):
        self.text_count += 1
        self.parts.append(f'<text id="text-{self.text_count}" x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
                          f'font-weight="{weight}" text-anchor="{anchor}"'
                          + (f' class="{cls}"' if cls else '') + f'>{escape(str(value))}</text>')

    def line(self, x1, y1, x2, y2, color=LINE):
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"/>')

    def header(self, kicker, title, subtitle):
        self.rect(36, 26, 28, 4, TEAL, 2)
        self.text(76, 33, kicker, 13, MUTED, 650, cls="kicker")
        self.text(36, 78, title, 31, INK, 750)
        self.text(36, 109, subtitle, 17, MUTED)

    def save(self, path):
        path.write_text("\n".join(self.parts + ["</svg>", ""]), encoding="utf-8")


def coverage(data, lang):
    zh = lang == "zh-CN"
    title = "相同预算，找全更多原始证据" if zh else "More complete evidence within the same budget"
    description = ("2400 字符整块打包预算。72 个可回答问题，AI-Memory-Book 找全 72 题，"
                   "三个词法组件分别找全 64 题，共享 MiniLM 的三种配置分别找全 47 题。"
                   "这是固定合成开发语料的证据覆盖，不是模型回答准确率。") if zh else (
                   "Complete evidence under a 2,400-character whole-block budget: AI-Memory-Book 72 of 72; "
                   "billion-context, claude-mem raw FTS and Basic Memory FTS each 64 of 72; "
                   "three shared-MiniLM configurations each 47 of 72. Synthetic development evidence coverage, not LLM answer accuracy.")
    s = SVG(600, title, description, lang)
    s.header("AI-MEMORY-BOOK · EVIDENCE", title,
             "固定合成工程语料 · 80 题 / 72 题可回答 · 2400 字符整块打包预算" if zh else
             "Authored engineering fixture · 80 questions / 72 answerable · 2,400-character block budget")
    x, width = 320, 474
    s.text(36, 155, "实测组件 / 模式" if zh else "Measured component / mode", 16, MUTED, 600)
    s.text(920, 155, "完整证据 / 可回答问题" if zh else "Complete / answerable", 15, MUTED, 600, "end")
    for tick in (0, 18, 36, 54, 72):
        tx = x + width * tick / 72
        s.line(tx, 176, tx, 491)
        s.text(tx, 514, tick, 14, MUTED, anchor="middle")
    labels = {
        "book": ("AI-Memory-Book", "当前发布实现" if zh else "current release implementation"),
        "billion": ("billion-context", "固定搜索内核" if zh else "pinned search kernel"),
        "claude": ("claude-mem", "原始 observation · FTS" if zh else "raw observations · FTS"),
        "basic": ("Basic Memory", "显式 FTS" if zh else "explicit FTS"),
        "minilm": ("共享 MiniLM 配置" if zh else "Shared MiniLM modes",
                   "Mem0 / Chroma / LangGraph")}
    for index, row in enumerate(data["rows"]):
        y = 194 + index * 63
        primary, secondary = labels[row["id"]]
        if row["id"] == "book":
            s.rect(20, y - 18, 920, 58, "#e8f5f1", radius=9)
        s.text(36, y + 2, primary, 23, TEAL if index == 0 else INK, 700 if index == 0 else 600)
        s.text(36, y + 26, secondary, 15, MUTED)
        s.rect(x, y - 1, width * row["complete"] / data["answerable"], 22,
               TEAL if index == 0 else BLUE if index < 4 else "#8798b5", radius=5)
        s.text(920, y + 19, f'{row["complete"]} / {data["answerable"]}', 28,
               TEAL if index == 0 else INK, 700, "end")
    s.text(36, 550, "当前 Book 复核；外部组件沿用固定配置记录。不是完整产品排名或模型回答分数。" if zh else
           "Current Book replay; pinned external component records. Not a full-product or LLM-answer ranking.", 15, MUTED)
    s.text(36, 577, "共享组：Mem0（infer=False）、Chroma 与 LangGraph Store；各自执行，结果相关。" if zh else
           "Shared group: Mem0 (infer=False), Chroma and LangGraph Store; separate runs, correlated results.", 14, MUTED)
    return s


def metric_card(s, x, y, title, subtitle, baseline, current, unit, change, zh):
    s.rect(x, y, 436, 214, WHITE, radius=13, stroke=LINE)
    s.text(x + 22, y + 33, title, 23, INK, 650)
    s.text(x + 22, y + 59, subtitle, 16, MUTED)
    s.text(x + 22, y + 109, f'−{change:.2f}%', 42, TEAL, 750)
    s.text(x + 414, y + 107, "越低越好" if zh else "lower is better", 14, MUTED, anchor="end")
    for index, (label, value, color) in enumerate((("改进前" if zh else "Before", baseline, PALE),
                                                   ("当前" if zh else "Current", current, TEAL))):
        by = y + 142 + index * 35
        s.text(x + 22, by + 5, label, 17, MUTED)
        s.rect(x + 95, by - 9, 200 * value / baseline, 15, color, radius=4)
        digits = 2 if unit == "MB" else 3
        s.text(x + 414, by + 5, f'{value:.{digits}f} {unit}', 19, INK, 600, "end")


def runtime(data, lang):
    zh = lang == "zh-CN"
    title = "减少内存占用、重复读取和等待" if zh else "Less memory, repeated work and waiting"
    desc = ("语义检索受跟踪峰值分配减少 66.31%，模型文件读取和内容哈希字节数各减少一半，"
            "模拟模型运行时初始化耗时减少 41.50%，100 小节每节预览 20 页耗时减少 6.46%。"
            "小规模语义场景慢 1.41%，两个单小节场景慢 1.07% 和 0.42%。") if zh else (
            "Tracked semantic peak allocation falls 66.31%; model-artifact read and content-hash bytes each halve; "
            "mock-runtime initialization latency falls 41.50%; a 100-section directory with 20 previews each falls 6.46%. "
            "Retained small-case regressions are 1.41% for semantic ranking and 1.07% / 0.42% for single-section directories.")
    s = SVG(740, title, desc, lang)
    s.header("AI-MEMORY-BOOK · RUNTIME", title,
             "当前交付实现的组件实测 · 对比改进前实现 · 四轮交替 A/B" if zh else
             "Measured shipped components · compared with the prior implementation · four alternating A/B rounds")
    cards = [
        ("语义峰值分配" if zh else "Tracked peak allocation", "32768 个向量窗口 · 不等于进程 RSS" if zh else
         "32,768 vector windows · not process RSS", data["allocation"]),
        ("模型文件校验工作量" if zh else "Artifact verification work", "读取与内容哈希的字节数，各减少一半" if zh else
         "Bytes read and content-hashed, each", data["artifact_bytes"]),
        ("文件验证与初始化" if zh else "Artifact initialization", "模拟运行时 · 不包含真实模型加载" if zh else
         "Mock runtimes · real model loading excluded", data["artifact_init"]),
        ("章节目录耗时" if zh else "Chapter directory latency", "100 小节 × 每节 20 页预览" if zh else
         "100 sections × 20 page previews each", data["directory"]),
    ]
    for index, (heading, subtitle, metric) in enumerate(cards):
        x, y = 32 + (index % 2) * 460, 140 + (index // 2) * 236
        metric_card(s, x, y, heading, subtitle, metric["baseline"], metric["current"],
                    metric["unit"], metric["reduction_percent"], zh)
    s.rect(32, 611, 896, 60, "#fff6e6", radius=10)
    s.text(48, 635, "另有收益：语义排序 −6.38%；100 小节、每节 1 页的目录 −23.97%。" if zh else
           "Also measured: semantic ranking −6.38%; a 100-section / 1-page directory −23.97%.", 16, INK, 500)
    s.text(48, 659, "保留的小场景退步：语义 +1.41%；单小节目录 +1.07% / +0.42%。" if zh else
           "Small-case costs retained: semantic +1.41%; single-section directories +1.07% / +0.42%.", 16, AMBER, 550)
    s.text(36, 700, "条形为总体中位数；耗时百分比来自四轮成对比值的中位数。MB = 1,000,000 字节。" if zh else
           "Bars show pooled medians; timing percentages use median paired ratios. MB = 1,000,000 bytes.", 14, MUTED)
    s.text(36, 725, "固定热缓存组件实验；不代表完整检索、MCP、冷启动或模型推理的同比提速。" if zh else
           "Warm fixed component fixtures; no whole-recall, MCP, cold-start or model-inference speed claim.", 14, MUTED)
    return s


def native(data, lang):
    zh = lang == "zh-CN"
    title = "原生核心：更低的检索尾延迟" if zh else "Native core: lower retrieval tail latency"
    desc = ("固定 2400 字符预算，四组 p95 耗时均降低。合成语料直接检索 12.231 到 12.008 毫秒，"
            "真实 MCP 14.158 到 13.783；公开语料直接检索 4.950 到 4.663，MCP 6.714 到 6.479。"
            "这是当前沿用的原生核心的保留测量，不是本次重新对完整发布版本计时。") if zh else (
            "At 2,400 characters, p95 latency improves in all four cells: synthetic direct 12.231 to 12.008 ms, "
            "synthetic MCP 14.158 to 13.783 ms, public direct 4.950 to 4.663 ms, public MCP 6.714 to 6.479 ms. "
            "Preserved measurement of the shipped native core, not a fresh timing of the complete current release.")
    s = SVG(680, title, desc, lang)
    s.header("AI-MEMORY-BOOK · NATIVE CORE", title,
             "2400 字符 · p95 毫秒，越低越好 · 直接检索与真实 SDK stdio MCP" if zh else
             "2,400 characters · p95 milliseconds, lower is better · direct recall and real SDK stdio MCP")
    s.rect(36, 132, 18, 10, PALE, radius=3)
    s.text(63, 142, "先前原生核心" if zh else "Earlier native core", 15, MUTED)
    s.rect(257, 132, 18, 10, TEAL, radius=3)
    s.text(284, 142, "当前交付原生核心" if zh else "Shipped native core", 15, MUTED)
    s.text(920, 142, "p95 降低" if zh else "p95 reduction", 15, MUTED, 600, "end")
    x, width = 300, 420
    for tick in (0, 4, 8, 12, 16):
        tx = x + width * tick / 16
        s.line(tx, 172, tx, 533)
        s.text(tx, 559, tick, 14, MUTED, anchor="middle")
    for index, row in enumerate(data["rows"]):
        y = 188 + index * 91
        cohort = ("合成工程语料" if zh else "Synthetic engineering") if row["cohort"] == "synthetic61" else ("公开对话语料" if zh else "Public conversations")
        surface = ("直接检索" if zh else "Direct recall") if row["surface"] == "direct" else ("真实 MCP 往返" if zh else "Real MCP round trip")
        s.text(36, y + 5, cohort, 23, INK, 650)
        s.text(36, y + 30, surface, 18, MUTED)
        for position, key in enumerate(("baseline_ms", "current_ms")):
            by, value = y - 12 + position * 28, row[key]
            color = PALE if position == 0 else TEAL
            s.rect(x, by, width * value / 16, 17, color, radius=4)
            s.text(x + width * value / 16 + 9, by + 14, f'{value:.3f}', 19,
                   MUTED if position == 0 else TEAL, 600)
        s.text(920, y + 25, f'−{row["reduction_percent"]:.2f}%', 30, TEAL, 750, "end")
    s.rect(32, 584, 896, 36, "#e8f5f1", radius=9)
    s.text(48, 608, "56,784 对结果等价 · 113,568 次调用 · 原生源码保持一致" if zh else
           "56,784 equivalent result pairs · 113,568 calls · native source retained unchanged", 17, TEAL, 600)
    s.text(36, 644, "保留的原生核心测量，本次未重新计时完整版本。存在个别慢轮次与启动／内存成本。" if zh else
           "Preserved core measurement, not a new full-release timing. Slower rounds and startup / memory costs remain.", 14, MUTED)
    s.text(36, 666, "四轮交替顺序；无查询结果缓存命中；未清空 SQLite / 系统缓存；不含模型生成。" if zh else
           "Four balanced rounds; no result-cache hits; SQLite / OS caches retained; model generation excluded.", 14, MUTED)
    return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEST / "chart-data.json")
    parser.add_argument("--output", type=Path, default=DEST)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["coverage"]["answerable"] == 72
    assert all(0 <= row["complete"] <= 72 for row in data["coverage"]["rows"])
    assert all(row["baseline_ms"] > row["current_ms"] > 0 for row in data["native"]["rows"])
    args.output.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "zh-CN"):
        suffix = ".zh" if lang == "zh-CN" else ""
        for stem, render, key in (("evidence-coverage", coverage, "coverage"),
                                  ("runtime-gains", runtime, "runtime"),
                                  ("native-latency", native, "native")):
            render(data[key], lang).save(args.output / f"{stem}{suffix}.svg")
    print("Rendered six exact-data SVG charts.")


if __name__ == "__main__":
    main()
