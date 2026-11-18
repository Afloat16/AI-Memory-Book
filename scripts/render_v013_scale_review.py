"""Rebuild run-2 tables and static figures from audited original ZIP records.

No MemoryBook import, database restoration, retrieval or performance call is
performed. Every timed output is retained, including incomplete baseline
evidence. Matplotlib is a presentation dependency, not a runtime dependency.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import platform
import statistics
from zipfile import ZipFile

RUN = 44331778554
CANDIDATE = "e0e2515f6e16404cfb9b676cd2eab01ce84b81cc"
BASELINE = "8044e4bafe18e73ea422af5eeb47ef961e65246c"
ARCHIVE_SHA = "47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac"
AUDIT_SHA = "87e57eda285804f3a358baf7d16e9b82876f4dd40c1b3f73d0715b12635755cb"
AUDIT_REPO_PATH = "benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-saved-response-review.json"
STAGES = ("age-reference-1024", "age-shift-1024", "foreign-10016", "foreign-50016",
          "own-100000", "interleaved-100000", "replacement-100000")
MODES = ("cold-result-cache", "warm-result-cache", "uncached-directory")
RECALL_CASES = ("routing-archive:current", "routing-archive:historical", "routing-core:identifier",
                "routing-core:current", "ranking-next:chinese", "training-core:multi_source",
                "attention-next:replacement")
DIRECTORY_CASES = ("routing-archive:directory", "ranking-next:directory")
ARMS = ("baseline", "candidate")
BLUE, TEAL, ORANGE, INK = "#527daf", "#087f75", "#c27137", "#152d43"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stats(values):
    ordered = sorted(values)
    require(bool(ordered), "Empty measurement group")
    return {"n": len(ordered), "p50": statistics.median(ordered),
            "p95_nearest_rank": ordered[math.ceil(.95 * len(ordered)) - 1],
            "min": ordered[0], "max": ordered[-1]}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, *, compress=False):
    require(bool(rows), "Empty CSV: " + str(path))
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = text.getvalue().encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0) if compress else raw)


def load_data(archive_path, audit_path):
    archive_bytes = archive_path.read_bytes()
    require(len(archive_bytes) == 29394152 and sha(archive_bytes) == ARCHIVE_SHA, "Original run-2 ZIP differs")
    audit_bytes = audit_path.read_bytes()
    require(sha(audit_bytes) == AUDIT_SHA, "Independent audit bytes differ")
    audit = json.loads(audit_bytes)
    require(audit["status"] == "passed_saved_record_integrity" and audit["run_id"] == RUN
            and audit["run_attempt"] == 1 and audit["memory_book_api_calls"] == 0
            and audit["archive_sha256"] == ARCHIVE_SHA, "Audit does not bind this run")
    require(audit["binding"]["runtimes"]["candidate"]["commit"] == CANDIDATE
            and audit["binding"]["runtimes"]["baseline"]["commit"] == BASELINE, "Audit runtime identity differs")
    all_groups, all_pairs, measurements, resources, quality_rows = [], [], [], [], []
    stages = {}
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        inventory = json.loads(archive.read("artifact-files.json"))["retained"]
        checked = set()

        def read(name):
            raw = archive.read(name)
            expected = inventory[name]
            require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Artifact changed: " + name)
            checked.add(name)
            return raw

        def js(name):
            return json.loads(read(name))

        manifest = js("run/manifest.json")
        require(manifest["status"] == "measurements_completed" and not manifest["interruptions"]
                and not manifest["unexecuted_or_incomplete_cells"] and not manifest["unattached_attempt_directories"],
                "Incomplete or ambiguous formal run")
        require(tuple(manifest["stages"]) == STAGES, "Checkpoint order or membership differs")
        for arm, commit in (("baseline", BASELINE), ("candidate", CANDIDATE)):
            require(manifest["binding"]["runtimes"][arm]["commit"] == commit, "Manifest runtime identity differs")
        for checkpoint in STAGES:
            stage = manifest["stages"][checkpoint]
            summary = js("run/" + checkpoint + "/summary.json")
            require(summary == stage["summary"], "Manifest and original summary differ")
            audited = audit["stages"][checkpoint]
            require(summary["quality"] == audited["quality"] and stage["spec"] == audited["spec"], "Audit stage differs")
            fingerprint = js("run/" + checkpoint + "/fingerprint.json")
            require(fingerprint == stage["build"]["result"]["fingerprint"], "Target page counts are unbound")
            stages[checkpoint] = {"spec": stage["spec"], "actual_pages": audited["actual_pages"],
                                  "target_layout": fingerprint["target_layout"], "quality": summary["quality"],
                                  "controls": audited["controls"]}
            by_group, by_round = defaultdict(list), defaultdict(list)
            for arm, rows in summary["quality_case_records"].items():
                for row in rows:
                    score = row["score"]
                    quality_rows.append({"checkpoint": checkpoint, "arm": arm, "case": row["case"],
                        "surface": row["surface"], "answerable": score["answerable"], "complete": score["complete"],
                        "required_spans": score["required_spans"], "covered_spans": score["covered_spans"],
                        "current_source_first": score["current_source_first"], "stale_before_current": score["stale_before_current"],
                        "returned_context_for_missing": score["returned_context_for_missing"],
                        "source_errors": len(score["source_errors"]), "context_chars": score["context_chars"],
                        "evidence_projection_sha256": score["evidence_projection_sha256"]})
            seen_slots = set()
            for block in stage["blocks"]:
                arm, round_number = block["arm"], block["round"]
                require((round_number, arm) not in seen_slots, "Duplicate round/arm")
                seen_slots.add((round_number, arm))
                execution = block["execution"]
                require(execution["complete"] and execution["returncode"] == 0 and not execution["timed_out"], "Incomplete block")
                attempt = PurePosixPath(execution["result_path"]).parent.name
                prefix = "run/" + checkpoint + "/" + attempt
                result = js(prefix + "/result.json")
                require(result == execution["result"] and result["status"] == "completed", "Worker result differs")
                observations = [json.loads(line) for line in read(prefix + "/observations.jsonl").splitlines()]
                require(len(observations) == result["observations"] == (222 if round_number == 0 else 150), "Block sample count differs")
                for observation in observations:
                    require(observation["error"] is None and observation["cache_mode_valid"], "Invalid timed output")
                    require(observation["arm"] == arm and observation["round"] == round_number, "Observation identity differs")
                    if observation["mode"] == "quality":
                        continue
                    score = observation["score"]
                    require(not score["source_errors"], "Source error must not be hidden by presentation")
                    row = {"checkpoint": checkpoint, "arm": arm, "round": round_number,
                           "case": observation["case"], "mode": observation["mode"],
                           "repetition": observation["repetition"], "warm_call": observation.get("warm_call"),
                           "sequence": observation["sequence"], "wall_ns": observation["wall_ns"],
                           "process_cpu_ns": observation["process_cpu_ns"], "complete": score["complete"],
                           "required_spans": score["required_spans"], "covered_spans": score["covered_spans"],
                           "current_source_first": score["current_source_first"], "stale_before_current": score["stale_before_current"],
                           "context_chars": score["context_chars"], "source_errors": len(score["source_errors"]),
                           "raw_archive_member": prefix + "/responses.jsonl.gz",
                           "raw_gzip_offset": observation["raw_gzip_offset"], "raw_gzip_bytes": observation["raw_gzip_bytes"],
                           "raw_sha256": observation["raw_sha256"]}
                    measurements.append(row)
                    by_group[arm, row["case"], row["mode"]].append(row)
                    by_round[round_number, arm, row["case"], row["mode"]].append(row)
                resource = result["resources"]
                item = {"checkpoint": checkpoint, "arm": arm, "round": round_number,
                        "quality_included": result["quality_included"], "quality_calls": 72 if result["quality_included"] else 0,
                        "performance_calls": 150, "initialization_wall_ns": result["initialization_wall_ns"],
                        **resource, "worker_cpu_seconds": resource["process_user_seconds"] + resource["process_system_seconds"]}
                for phase in ("before", "after"):
                    storage = result["storage_" + phase]
                    item["storage_" + phase + "_total_file_bytes"] = storage["total_file_bytes"]
                    for name in ("main", "-wal", "-shm"):
                        item["storage_" + phase + "_" + name.replace("-", "") + "_bytes"] = storage["files_bytes"][name]
                resources.append(item)
                audit_resource = next(r for r in audited["resources"] if r["arm"] == arm and r["round"] == round_number)
                require(audit_resource["initialization_wall_ns"] == item["initialization_wall_ns"]
                        and audit_resource["process_lifetime_peak_rss_bytes"] == item["process_lifetime_peak_rss_bytes"]
                        and audit_resource["storage_after"] == item["storage_after_total_file_bytes"], "Resource audit mismatch")
            require(seen_slots == {(r, a) for r in range(6) for a in ARMS}, "Incomplete paired slots")
            for mode in MODES:
                for case in DIRECTORY_CASES if mode == "uncached-directory" else RECALL_CASES:
                    project = case.split(":", 1)[0]
                    group = {"checkpoint": checkpoint, "case": case, "mode": mode,
                             "total_pages": stage["spec"]["total_pages"], "foreign_pages": stage["spec"]["foreign_pages"],
                             "own_pages": stage["spec"]["own_pages"], "layout": stage["spec"]["layout"],
                             "target_project_pages": fingerprint["target_layout"][project]["pages"]}
                    for arm in ARMS:
                        rows = by_group[arm, case, mode]
                        wanted = next(r for r in summary["timing"] if (r["arm"], r["case"], r["mode"]) == (arm, case, mode))
                        expected_n = 90 if mode == "warm-result-cache" else 30
                        require(len(rows) == wanted["attempted"] == expected_n and wanted["errors"] == wanted["cache_mode_mismatches"] == 0, "Wrong group cardinality")
                        group[arm + "_n"] = len(rows)
                        group[arm + "_complete_n"] = sum(r["complete"] is True for r in rows)
                        group[arm + "_incomplete_n"] = sum(r["complete"] is False for r in rows)
                        group[arm + "_current_first_n"] = sum(r["current_source_first"] is True for r in rows)
                        group[arm + "_stale_before_current_n"] = sum(r["stale_before_current"] is True for r in rows)
                        group[arm + "_context_chars_median"] = statistics.median(r["context_chars"] for r in rows)
                        for field, label in (("wall_ns", "wall_ms"), ("process_cpu_ns", "cpu_ms")):
                            values = stats([r[field] for r in rows])
                            require(values == wanted[field], "Recomputed original quantiles differ")
                            for key, value in values.items():
                                if key != "n":
                                    group[arm + "_" + label + "_" + key] = value / 1e6
                    pair_values = defaultdict(list)
                    for round_number in range(6):
                        pair = {"checkpoint": checkpoint, "case": case, "mode": mode, "round": round_number}
                        original = next(r for r in summary["paired_round_ratios"] if (r["round"], r["case"], r["mode"]) == (round_number, case, mode))
                        require(original["eligible_equal_complete_samples"], "Ineligible pair")
                        for field, label in (("wall_ns", "wall"), ("process_cpu_ns", "cpu")):
                            values = {}
                            for arm in ARMS:
                                rows = by_round[round_number, arm, case, mode]
                                require(len(rows) == (15 if mode == "warm-result-cache" else 5), "Pair count differs")
                                values[arm] = statistics.median(r[field] for r in rows)
                                pair[arm + "_n"] = len(rows)
                                pair[arm + "_" + label + "_p50_ns"] = values[arm]
                            ratio = values["candidate"] / values["baseline"]
                            require(ratio == original[field + "_candidate_over_baseline_p50"], "Paired ratio differs")
                            pair[label + "_candidate_over_baseline"] = ratio
                            pair_values[label].append(ratio)
                        all_pairs.append(pair)
                    for label in ("wall", "cpu"):
                        for metric in ("p50", "p95_nearest_rank"):
                            group[label + "_" + metric + "_candidate_over_baseline"] = group["candidate_" + label + "_ms_" + metric] / group["baseline_" + label + "_ms_" + metric]
                        group[label + "_paired_ratio_median"] = statistics.median(pair_values[label])
                        group[label + "_paired_ratio_min"] = min(pair_values[label])
                        group[label + "_paired_ratio_max"] = max(pair_values[label])
                    group["paired_rounds"] = 6
                    group["quality_boundary"] = ("baseline_incomplete_candidate_complete" if group["baseline_incomplete_n"] and not group["candidate_incomplete_n"] else "both_complete" if group["baseline_complete_n"] == group["baseline_n"] and group["candidate_complete_n"] == group["candidate_n"] else "see_complete_counts")
                    reviewed = next(r for r in audited["timing"] if r["case"] == case and r["mode"] == mode)
                    for arm in ARMS:
                        require(group[arm + "_wall_ms_p50"] == reviewed[arm + "_wall_ms"]["p50"]
                                and group[arm + "_wall_ms_p95_nearest_rank"] == reviewed[arm + "_wall_ms"]["p95_nearest_rank"], "Independent audit quantile mismatch")
                    require(group["wall_paired_ratio_median"] == reviewed["paired_round_candidate_over_baseline_p50"]["median"], "Independent audit pair mismatch")
                    all_groups.append(group)
    require(len(all_groups) == 112 and len(all_pairs) == 672 and len(measurements) == 12600
            and len(quality_rows) == 1008 and len(resources) == 84, "Presentation omitted registered data")
    directions = {}
    for mode in MODES:
        rows = [r for r in all_groups if r["mode"] == mode]
        directions[mode] = {"groups": len(rows)}
        for metric in ("wall_p50_candidate_over_baseline", "wall_p95_nearest_rank_candidate_over_baseline", "wall_paired_ratio_median"):
            directions[mode][metric] = {"faster": sum(r[metric] < 1 for r in rows),
                                        "slower": sum(r[metric] > 1 for r in rows),
                                        "equal": sum(r[metric] == 1 for r in rows)}
        require(directions[mode]["wall_p50_candidate_over_baseline"]["faster"] == audit["performance_direction_counts"][mode]["candidate_p50_faster"], "Direction count differs from audit")
    resource_summary = []
    for checkpoint in STAGES:
        for cohort, rounds in (("all_workers", tuple(range(6))), ("quality_and_performance", (0,)), ("performance_only", tuple(range(1, 6)))):
            item = {"checkpoint": checkpoint, "cohort": cohort, "rounds": ",".join(map(str, rounds)), "n_per_arm": len(rounds)}
            for field in ("initialization_wall_ns", "process_lifetime_peak_rss_bytes", "storage_after_total_file_bytes", "worker_cpu_seconds", "minor_page_faults", "major_page_faults"):
                pairs = []
                for arm in ARMS:
                    values = [r[field] for r in resources if r["checkpoint"] == checkpoint and r["arm"] == arm and r["round"] in rounds]
                    item[arm + "_" + field + "_median"] = statistics.median(values)
                    item[arm + "_" + field + "_min"] = min(values)
                    item[arm + "_" + field + "_max"] = max(values)
                for round_number in rounds:
                    values = {r["arm"]:r[field] for r in resources if r["checkpoint"] == checkpoint and r["round"] == round_number}
                    if values["baseline"]:
                        pairs.append(values["candidate"] / values["baseline"])
                item[field + "_paired_ratio_median"] = statistics.median(pairs) if len(pairs) == len(rounds) else None
            resource_summary.append(item)
    return {"binding": {"run_id": RUN, "attempt": 1, "candidate": CANDIDATE, "baseline": BASELINE,
                         "archive_sha256": ARCHIVE_SHA, "archive_bytes": len(archive_bytes), "audit_sha256": AUDIT_SHA,
                         "audit_repo_path": AUDIT_REPO_PATH, "audit_checks": audit["checks"],
                         "generator_sha256": sha(Path(__file__).read_bytes())},
            "host": audit["host"], "stages": stages, "groups": all_groups, "paired_rounds": all_pairs,
            "resources_by_block": resources, "resources_summary": resource_summary,
            "directions": directions, "quality_all_stages": audit["quality_all_stages_per_arm"],
            "counts": {"timing_groups": 112, "paired_groups": 672, "timed_calls": 12600,
                       "quality_calls": 1008, "worker_blocks": 84, "selected_zip_members_hash_checked": len(checked)},
            "limits": ["Run-2 within-host arm comparisons only; no unpaired run-1/run-2 speedup.",
                       "Cold clears recall_cache only; OS, SQLite pager and helper caches remain populated.",
                       "Directory is the complete navigation and original-page read chain.",
                       "All incomplete baseline evidence remains in timing statistics.",
                       "Quantiles are empirical single-host summaries, not service guarantees or significance tests.",
                       "RSS is process-lifetime high-water, not per-call allocation. Worker CPU includes recording, scoring and fingerprinting.",
                       "Round 0 includes 72 extra quality calls; worker resources have separate cohort summaries."]}, measurements, quality_rows


def render(data, assets, preview):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.font_manager import findfont, fontManager
    from matplotlib.lines import Line2D
    import numpy as np

    lookup = {(r["checkpoint"], r["case"], r["mode"]): r for r in data["groups"]}
    fonts = {}
    available_fonts = {entry.name for entry in fontManager.ttflist}
    chinese_font = next((family for family in ("Noto Sans CJK SC", "Noto Sans CJK JP")
                         if family in available_fonts), None)
    require(chinese_font is not None, "Install a Noto Sans CJK SC or JP font face for the Chinese figures")
    for lang in ("en", "zh-CN"):
        zh = lang == "zh-CN"
        tr = lambda en, cn: cn if zh else en
        font = chinese_font if zh else "DejaVu Sans"
        font_path = Path(findfont(font, fallback_to_default=False))
        fonts[lang] = {"family": font, "file": font_path.name, "sha256": sha(font_path.read_bytes())}
        plt.rcParams.update({"font.family": font, "font.size": 10, "axes.titlesize": 12,
            "axes.labelsize": 10, "text.color": INK, "axes.labelcolor": INK,
            "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b4c3d0",
            "grid.color": "#dbe5ed", "grid.linewidth": .7, "axes.axisbelow": True,
            "svg.hashsalt": "v013-scale-run2-44331778554", "svg.fonttype": "path"})
        arm_labels = [tr("v0.12 baseline", "v0.12 基线"), tr("v0.13 candidate", "v0.13 候选")]
        stage_labels = [tr("1,024 · reference", "1,024 · 参考"), tr("1,024 · age shift", "1,024 · 时间平移"),
                        tr("10,016 · foreign", "10,016 · 外项目增长"), tr("50,016 · foreign", "50,016 · 外项目增长"),
                        tr("100k · grouped", "100k · 分组写入"), tr("100k · interleaved", "100k · 交错写入"),
                        tr("100k · replacement", "100k · 来源替换")]

        def finish(fig, name, title, description):
            suffix = ".zh-CN" if zh else ""
            fig.text(.5, .017, "Run 44331778554/1 | baseline 8044e4ba | candidate e0e2515f",
                     ha="center", fontsize=8, color="#52687c")
            fig.savefig(assets / (name + suffix + ".svg"), metadata={"Date": None, "Title": title,
                        "Description": description, "Creator": "AI-Memory-Book audited run-2 renderer"})
            if preview:
                fig.savefig(preview / (name + suffix + ".png"), dpi=110)
            plt.close(fig)

        def legend(fig, y=.92):
            handles = [Line2D([], [], color=c, marker="o", label=label) for c, label in zip((BLUE, TEAL), arm_labels)]
            fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, y), ncol=2, frameon=False)

        fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.3))
        fig.subplots_adjust(left=.085, right=.97, top=.84, bottom=.16, hspace=.40, wspace=.24)
        title = tr("A 16-page archive still pays for other projects' growth", "16 页归档项目仍受其他项目增长影响")
        fig.suptitle(title, fontsize=17, fontweight="bold", y=.97)
        legend(fig)
        selected = (STAGES[0], STAGES[2], STAGES[3])
        panels = (("routing-archive:current", MODES[0], tr("Current query · result-cache miss", "当前约定 · 结果缓存未命中")),
                  ("routing-archive:historical", MODES[0], tr("Historical query · result-cache miss", "历史约定 · 结果缓存未命中")),
                  ("routing-archive:directory", MODES[2], tr("Directory → section → original read", "目录 → 小节 → 原文读取")),
                  ("routing-archive:current", MODES[1], tr("Current query · result-cache hit", "当前约定 · 结果缓存命中")))
        for ax, (case, mode, heading) in zip(axes.flat, panels):
            x = [data["stages"][s]["actual_pages"] for s in selected]
            for arm, color in zip(ARMS, (BLUE, TEAL)):
                rows = [lookup[s, case, mode] for s in selected]
                med = [r[arm + "_wall_ms_p50"] for r in rows]
                high = [r[arm + "_wall_ms_p95_nearest_rank"] for r in rows]
                ax.plot(x, med, color=color, marker="o", lw=2)
                ax.fill_between(x, med, high, color=color, alpha=.12)
                ax.plot(x, high, color=color, ls=":", lw=1)
            ax.set_xscale("log"); ax.set_xticks(x, ["1,024", "10,016", "50,016"])
            ax.minorticks_off(); ax.set_ylim(bottom=0); ax.grid(axis="y")
            ax.set_title(heading, loc="left"); ax.set_ylabel(tr("Wall time (ms)", "墙钟时间（ms）"))
            ax.set_xlabel(tr("Total real-ingested pages", "真实入库总页数"))
        fig.text(.085, .086, tr("Solid lines: pooled p50; dotted boundary/shading: p50 to nearest-rank p95. n=30 cold/directory; n=90 warm.",
                                 "实线为总体 p50；虚线边界和阴影为 p50 至最近秩 p95。冷查询与目录 n=30，热缓存 n=90。"), fontsize=9)
        fig.text(.085, .053, tr("Only result cache is cold. Target history stays at 16 pages; no constant-time or OS-cold claim. Run 44331778554/1.",
                                 "仅结果缓存为空；目标项目始终 16 页。未证明常数时间，也不是操作系统冷启动。运行 44331778554/1。"), fontsize=9)
        finish(fig, "v013-foreign-growth", title, "Run-2 exact-source latency; all current-query slowdowns remain visible.")

        fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.8))
        fig.subplots_adjust(left=.085, right=.97, top=.84, bottom=.17, hspace=.52, wspace=.24)
        title = tr("At 100,000 pages, layout and own-history growth matter", "10 万页规模下，写入布局与自身历史增长仍然重要")
        fig.suptitle(title, fontsize=17, fontweight="bold", y=.97); legend(fig)
        layout = ("own-100000", "interleaved-100000")
        panel_rows = (("routing-archive:current", MODES[0], layout, tr("Archive · current · cold result cache", "归档项目 · 当前约定 · 冷结果缓存")),
                      ("routing-archive:directory", MODES[2], layout, tr("Archive · complete directory/read chain", "归档项目 · 完整目录追读链")),
                      ("routing-archive:historical", MODES[0], layout, tr("Archive · historical · cold result cache", "归档项目 · 历史约定 · 冷结果缓存")),
                      ("routing-core:current", MODES[0], ("foreign-50016", *layout), tr("Active project · current · cold result cache", "活跃项目 · 当前约定 · 冷结果缓存")))
        for ax, (case, mode, selected, heading) in zip(axes.flat, panel_rows):
            x = np.arange(len(selected)); width = .34
            for offset, arm, color in zip((-.5, .5), ARMS, (BLUE, TEAL)):
                rows = [lookup[s, case, mode] for s in selected]
                med = np.array([r[arm + "_wall_ms_p50"] for r in rows])
                high = np.array([r[arm + "_wall_ms_p95_nearest_rank"] for r in rows])
                bars = ax.bar(x + offset * width, med, width, color=color, alpha=.94)
                ax.errorbar(x + offset * width, med, yerr=np.array([np.zeros(len(x)), high - med]),
                            fmt="none", color=INK, capsize=3, lw=1)
                for bar, value, top in zip(bars, med, high):
                    ax.text(bar.get_x() + width / 2, top + max(high) * .025, f"{value:.2f}", ha="center", fontsize=8)
            labels = [tr("Grouped\n100,000 total", "分组写入\n总页数 100,000"), tr("Interleaved\n100,000 total", "交错写入\n总页数 100,000")]
            if len(selected) == 3:
                labels = [tr("16 own pages\n50,016 total", "自身 16 页\n总页数 50,016"),
                          tr("8,368 own pages\ngrouped, 100k", "自身 8,368 页\n分组写入，共 100k"),
                          tr("8,368 own pages\ninterleaved, 100k", "自身 8,368 页\n交错写入，共 100k")]
            ax.set_xticks(x, labels); ax.set_title(heading, loc="left"); ax.set_ylabel(tr("Wall time (ms)", "墙钟时间（ms）"))
            ax.grid(axis="y"); ax.set_ylim(0, max(lookup[s, case, mode][a + "_wall_ms_p95_nearest_rank"] for s in selected for a in ARMS) * 1.21)
        fig.text(.085, .09, tr("Bars: pooled p50. Whiskers reach p95; n=30 per arm/cell. Grouped and interleaved 100k corpora have identical logical sources.",
                                "柱形为总体 p50，须线延伸至 p95；每格每版本 n=30。100k 的分组与交错语料逻辑来源相同。"), fontsize=9)
        fig.text(.085, .055, tr("Own growth adds 49,984 pages across six active/newcomer projects; foreign history stays at 49,888 pages. Archive stays at 16.",
                                 "自身增长轴向六个活跃或新项目增加 49,984 页；外项目历史保持 49,888 页。归档项目仍为 16 页。"), fontsize=9)
        finish(fig, "v013-layout-and-growth", title, "Mixed measured outcomes: grouped archive current and active current queries remain slower.")

        fig, axes = plt.subplots(1, 3, figsize=(16.5, 7.8), gridspec_kw={"width_ratios": [7, 7, 2]})
        fig.subplots_adjust(left=.14, right=.98, top=.80, bottom=.33, wspace=.08)
        title = tr("All 112 timing groups, including every slower group", "完整保留全部 112 个计时组，包括所有较慢组")
        fig.suptitle(title, fontsize=18, fontweight="bold", y=.97)
        fig.text(.14, .91, tr("Cell = median of six per-round p50 changes: 100 × (candidate / baseline − 1). Negative is faster.",
                              "单元格为六轮 p50 变化比例的中位数：100 ×（候选 / 基线 − 1）。负值表示更快。"), fontsize=11)
        cmap = LinearSegmentedColormap.from_list("observed_difference", [TEAL, "#ffffff", ORANGE])
        norm = Normalize(-100, 100)
        recall_labels = [tr("Archive\ncurrent", "归档\n当前"), tr("Archive\nhistorical", "归档\n历史"),
                         tr("Core\nidentifier", "活跃\n标识符"), tr("Core\ncurrent", "活跃\n当前"),
                         tr("Next\nChinese", "新项目\n中文"), tr("Core\nmulti-source\n†", "活跃\n多来源\n†"),
                         tr("Next\nreplacement", "新项目\n替换")]
        for index, (ax, mode) in enumerate(zip(axes, MODES)):
            selected = DIRECTORY_CASES if mode == MODES[2] else RECALL_CASES
            values = np.array([[100 * (lookup[s, case, mode]["wall_paired_ratio_median"] - 1) for case in selected] for s in STAGES])
            im = ax.imshow(values, cmap=cmap, norm=norm, aspect="auto")
            for y, s in enumerate(STAGES):
                for x, case in enumerate(selected):
                    ax.text(x, y, f"{values[y, x]:+.1f}", ha="center", va="center", fontsize=9,
                            color="white" if values[y, x] < -65 else INK)
            ax.set_xticks(range(len(selected)), [tr("Archive", "归档"), tr("Next", "新项目")] if index == 2 else recall_labels, fontsize=9)
            ax.set_yticks(range(7), stage_labels if index == 0 else [""] * 7)
            ax.tick_params(axis="both", length=0, pad=7)
            for spine in ax.spines.values(): spine.set_visible(False)
            counts = data["directions"][mode]
            p50 = counts["wall_p50_candidate_over_baseline"]["slower"]
            pair = counts["wall_paired_ratio_median"]["slower"]
            heading = [tr("Cold result cache", "冷结果缓存"), tr("Warm result cache", "热结果缓存"), tr("Directory", "目录")][index]
            total = len(selected) * 7
            detail = tr(f"paired slower: {pair}/{total}; pooled p50: {p50}/{total}",
                        f"配对较慢：{pair}/{total}；总体 p50：{p50}/{total}")
            if index == 2:
                detail = tr(f"paired slower: {pair}/{total}\npooled p50: {p50}/{total}",
                            f"配对较慢：{pair}/{total}\n总体 p50：{p50}/{total}")
            ax.set_title(heading + "\n" + detail, fontsize=10, loc="center", pad=12)
        cax = fig.add_axes([.37, .195, .38, .022])
        colorbar = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[-100, -50, 0, 50, 100])
        colorbar.set_label(tr("Observed paired p50 difference (%)", "观测到的配对 p50 变化（%）"), fontsize=10)
        fig.text(.14, .108, tr("† Baseline multi-source evidence is incomplete; candidate is complete. All those timings remain included.",
                               "† 基线多来源结果缺少必需证据，候选完整；这些计时全部保留。"), fontsize=10)
        fig.text(.14, .068, tr("Per arm/cell: n=30 cold/directory; n=90 warm. Rounded labels; exact p50, p95, six ratios and quality counts are in the CSVs.",
                              "每格每版本：冷查询/目录 n=30，热缓存 n=90。图中文字保留一位小数；精确数值及质量计数见 CSV。"), fontsize=10)
        finish(fig, "v013-all-performance", title, "No slower groups removed; pooled p50 and per-round paired medians are explicitly distinguished.")

        fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.6))
        fig.subplots_adjust(left=.20, right=.97, top=.84, bottom=.18, hspace=.38, wspace=.35)
        title = tr("Recorded worker resources, with their measurement boundaries", "保留资源变化，并明确测量范围")
        fig.suptitle(title, fontsize=17, fontweight="bold", y=.97); legend(fig)
        panels = (("initialization_wall_ns", 1e6, "all_workers", tr("Open / initialize · ms · 6 workers per arm", "打开与初始化 · ms · 每版本 6 进程")),
                  ("process_lifetime_peak_rss_bytes", 1048576, "all_workers", tr("Lifetime peak RSS · MiB · 6 workers", "进程终生峰值 RSS · MiB · 6 进程")),
                  ("storage_after_total_file_bytes", 1048576, "all_workers", tr("Main + WAL + SHM after checkpoint · MiB", "收尾 checkpoint 后主库 + WAL + SHM · MiB")),
                  ("worker_cpu_seconds", 1, "performance_only", tr("Whole-worker CPU · seconds · rounds 1–5", "整个 worker 的 CPU · 秒 · 第 1–5 轮")))
        for ax, (field, unit, cohort, heading) in zip(axes.flat, panels):
            rows = [next(r for r in data["resources_summary"] if r["checkpoint"] == s and r["cohort"] == cohort) for s in STAGES]
            for offset, arm, color in zip((-.12, .12), ARMS, (BLUE, TEAL)):
                values = np.array([r[arm + "_" + field + "_median"] / unit for r in rows])
                low = np.array([r[arm + "_" + field + "_min"] / unit for r in rows])
                high = np.array([r[arm + "_" + field + "_max"] / unit for r in rows])
                ax.errorbar(values, np.arange(7) + offset, xerr=np.array([values-low, high-values]),
                            fmt="o", color=color, capsize=3, markersize=4, lw=1)
            ax.set_yticks(range(7), stage_labels, fontsize=9); ax.invert_yaxis(); ax.set_xlim(left=0)
            ax.grid(axis="x"); ax.set_title(heading, loc="left", fontsize=11)
        fig.text(.06, .105, tr("Dots: median; whiskers: full recorded min–max. RSS is not per-call allocation or steady-state working set.",
                               "圆点为中位数，须线为完整最小—最大范围。RSS 不是单次调用分配量，也不等于稳态工作集。"), fontsize=10)
        fig.text(.06, .069, tr("CPU includes recording, scoring and fingerprinting. Round 0 adds 72 quality calls; retained separately in resource tables.",
                              "CPU 包含记录、评分和指纹工作。第 0 轮额外执行 72 次质量调用，在资源数表中单列保留。"), fontsize=10)
        finish(fig, "v013-resources", title, "Process-lifetime resource observations, not a memory-allocation or per-call CPU benchmark.")
    return {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "numpy": np.__version__, "fonts": fonts}


def report_markdown(data):
    out = ["# v0.13 longitudinal run 2: performance and resource review", "",
           f"Run **{RUN}/1** compares `{BASELINE}` with `{CANDIDATE}` on the same hosted runner. All statistics below come from this run; run-1 absolute times are not used as paired evidence.", "",
           "## Evidence and interpretation", "",
           f"The original ZIP SHA256 is `{ARCHIVE_SHA}`. The independent saved-response audit (`{AUDIT_SHA}`) passed {data['binding']['audit_checks']:,} checks. This renderer separately reconstructs all group quantiles and paired ratios from compact original observations and checks them against both saved summaries and the independent audit. It makes zero MemoryBook API calls and restores no database.", "",
           "There are 84 arm blocks, 12,600 timed calls, and 1,008 separate quality calls across seven checkpoints. These repeat an authored fixture; they are not 13,608 independent real-user questions. Cold clears only the result cache. Directory time includes discovery, section navigation and original-page reads. Quantiles are empirical, not confidence intervals or service guarantees.", "",
           "Candidate recall evidence is complete for 56/56 answerable cases at every checkpoint; baseline is 48/56. Candidate current-source-first remains 16/24, and all 8 missing-evidence queries still return nonempty context. Across the seven correlated checkpoints these are 392/392 versus 336/392 complete, 112/168 versus 80/168 current-first, and 56/56 nonempty missing-evidence outputs in each arm. Completeness does not imply universal answerability, abstention or first-source correctness.", "",
           "## All group directions", "",
           "Direction counts include arbitrarily small differences and are not significance tests. Paired medians and pooled medians answer different statistical questions.", "",
           "| Mode | Groups | Pooled p50 faster / slower | Pooled p95 faster / slower | Median paired p50 faster / slower |",
           "|---|---:|---:|---:|---:|"]
    for mode, d in data["directions"].items():
        values = [d[k] for k in ("wall_p50_candidate_over_baseline", "wall_p95_nearest_rank_candidate_over_baseline", "wall_paired_ratio_median")]
        out.append(f"| {mode} | {d['groups']} | " + " | ".join(f"{v['faster']} / {v['slower']}" for v in values) + " |")
    out += ["", "All seven slower warm groups are `training-core:multi_source`: baseline evidence is incomplete, candidate evidence is complete. Their timings remain in every table and chart. The 14 cold/warm multi-source groups have different evidence completeness; this is disclosed rather than filtered out.", "",
            "## Fixed archive and growth", "",
            "The inactive routing archive retains 16 pages. Across the foreign-growth axis its current-query candidate p50 rises from 10.516 ms to 13.689 ms to 25.743 ms, while complete directory-chain p50 rises from 0.769 ms to 1.579 ms to 4.930 ms. Faster directory lookup does not establish constant-time retrieval.", "",
            "At 100,000 pages, grouped archive current recall is slower (42.978 → 46.814 ms); interleaved current recall is faster (166.898 → 102.478 ms). Interleaved historical recall is 133.222 → 67.912 ms, and the directory/read chain is 159.154 → 26.707 ms. These are this run's pooled p50 values, not run-to-run speedups.", "",
            "For routing-core, own growth increases target history from 16 to 8,368 pages while the other growing projects also expand. Current-query candidate p50 grows from 25.893 ms at 50,016 total pages to 331.363 ms at grouped 100k; interleaved 100k is 338.309 ms. Baseline is 22.100, 325.212 and 332.062 ms respectively. This remains a substantial latency limit.", "",
            "## Every group with a slower observed statistic", "",
            "A group is listed when pooled p50, pooled p95, or the median paired p50 ratio exceeds the baseline. No significance threshold or performance acceptance criterion is invented. Complete counts are counts of timed outputs, not independent questions.", "",
            "| Checkpoint | Query / mode | Base p50 ms | Cand p50 ms | Base p95 ms | Cand p95 ms | Paired p50 ratio | Complete base / cand |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in data["groups"]:
        if any(r[k] > 1 for k in ("wall_p50_candidate_over_baseline", "wall_p95_nearest_rank_candidate_over_baseline", "wall_paired_ratio_median")):
            mode = {MODES[0]: "cold", MODES[1]: "warm", MODES[2]: "directory"}[r["mode"]]
            out.append(f"| {r['checkpoint']} | {r['case']} / {mode} | {r['baseline_wall_ms_p50']:.6f} | {r['candidate_wall_ms_p50']:.6f} | {r['baseline_wall_ms_p95_nearest_rank']:.6f} | {r['candidate_wall_ms_p95_nearest_rank']:.6f} | {r['wall_paired_ratio_median']:.6f} | {r['baseline_complete_n']}/{r['baseline_n']} / {r['candidate_complete_n']}/{r['candidate_n']} |")
    out += ["", "## Resource boundaries", "",
            "`resources-by-block.csv` preserves all 84 original workers. `resources-summary.csv` separates all workers (six per arm), round 0 with quality plus performance (one), and rounds 1–5 with performance only (five). Whole-worker CPU includes import/setup, recording, scoring and fingerprinting, and is not the sum of API call CPU. Per-call CPU quantiles remain separately available in `groups.csv`.", "",
            "Recorded RSS is process-lifetime high-water, not per-call allocation or steady-state working set. Most later stages report equal arm high-water values; that cannot prove zero extra allocation. Initialization medians are about 0.80–0.85 ms. Main/WAL/SHM totals after the worker's checkpoint are equal between arms at each stage; grouped/interleaved 100k are about 363.457/366.715 MiB respectively.", "",
            "## Reproduce", "",
            f"This rendering used Python {data['rendering']['python']}, Matplotlib {data['rendering']['matplotlib']} and NumPy {data['rendering']['numpy']}. English uses DejaVu Sans; Chinese uses {data['rendering']['fonts']['zh-CN']['family']}. The generator accepts a registered Noto Sans CJK SC or JP face and records the selected family and font-file hash in `analysis.json`. The presentation environment is separate from the measured runner. The generator never executes the measured runtime.", "",
            "```bash", "python scripts/render_v013_scale_review.py \\",
            "  --archive /path/to/original-artifact-44331778554-1.zip \\",
            f"  --audit {AUDIT_REPO_PATH} \\",
            "  --output-report /new/empty/report-directory \\",
            "  --output-assets /new/empty/asset-directory", "```", "",
            "`groups.csv` has all 112 wall/CPU groups and complete counts; `paired-rounds.csv` has all 672 paired records; `timed-observations.csv.gz` preserves all 12,600 compact timing rows and their original-response gzip offsets/hashes; `quality-cases.csv` retains the 1,008 quality records. Original ZIP/response data remain authoritative. The CSVs and SVGs are derived presentations, not replacement measurements.", ""]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--output-assets", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()
    report_dir, assets = args.output_report.resolve(), args.output_assets.resolve()
    require(not report_dir.exists(), "Use a new report directory")
    if assets.exists():
        require(not any(assets.glob("v013-*.svg")), "Do not overwrite existing v0.13 assets")
    data, measurements, quality = load_data(args.archive, args.audit)
    report_dir.mkdir(parents=True)
    assets.mkdir(parents=True, exist_ok=True)
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=False)
    write_csv(report_dir / "groups.csv", data["groups"])
    write_csv(report_dir / "paired-rounds.csv", data["paired_rounds"])
    write_csv(report_dir / "resources-by-block.csv", data["resources_by_block"])
    write_csv(report_dir / "resources-summary.csv", data["resources_summary"])
    write_csv(report_dir / "quality-cases.csv", quality)
    write_csv(report_dir / "timed-observations.csv.gz", measurements, compress=True)
    data["rendering"] = render(data, assets, args.preview_dir)
    write_json(report_dir / "analysis.json", data)
    (report_dir / "README.md").write_text(report_markdown(data), encoding="utf-8")
    artifacts = {}
    for category, folder, paths in (("report", report_dir, sorted(report_dir.iterdir())),
                                     ("assets", assets, sorted(assets.glob("v013-*.svg")))):
        for path in paths:
            raw = path.read_bytes()
            artifacts[category + "/" + path.relative_to(folder).as_posix()] = {"bytes": len(raw), "sha256": sha(raw)}
    write_json(report_dir / "artifact-manifest.json", {"binding": data["binding"], "artifacts": artifacts,
                                                       "previews_are_not_measurements": True})
    print(json.dumps({"status": "generated_from_audited_records", "counts": data["counts"], "directions": data["directions"],
                      "report_directory": str(report_dir), "assets_directory": str(assets)}))


if __name__ == "__main__":
    main()
