#!/usr/bin/env python3
"""Static paired-round forest plots for the isolated language experiment.

Formal charts require an audited six-round analysis. --preview is mandatory for
preflight, partial or artificial inputs; preview labels cannot be disabled.
No benchmark, candidate, runner or README is changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

NAMES = {"rust_same":"Rust · 同边界", "c_table":"C · Unicode表", "rust_table":"Rust · Unicode表",
    "rust_window":"Rust · 选窗整阶段", "c_window":"C · 选窗整阶段",
    "node_window":"Node · 选窗桥接", "node_small":"Node · 小函数桥接",
    "rust_metadata":"Rust · 元数据整方法", "c_metadata":"C · 元数据整方法"}
CONTROL = {"rust_table":"共享Unicode表：Rust / C", "rust_window":"选窗整阶段：Rust / C",
           "rust_metadata":"元数据整方法：Rust / C"}
COHORTS = {"synthetic61":"合成工程语料", "public1015":"公开语料", "unicode_stress":"Unicode压力语料"}
CONFIGS = {"direct-char2400":"直接调用 · 2400字符", "mcp-char2400":"MCP · 2400字符",
           "direct-token1024":"直接调用 · 1024 token", "mcp-token1024":"MCP · 1024 token"}
INGESTION = {"fresh_ingestion_ms":("首次导入","fresh"),
             "unchanged_ingestion_ms":("无变更重复导入","unchanged"),
             "changed_ingestion_ms":("内容变更导入","changed")}
BG, INK, MUTED = "#f5f7fb", "#172b46", "#63748b"
POSITIVE, NEGATIVE, NEUTRAL = "#147d79", "#c44851", "#536a9b"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)

def six_rounds(row):
    pairs = row.get("paired_rounds", [])
    return (row.get("expected_rounds") == 6 and row.get("complete_rounds") is True
            and len(pairs) == 6 and sorted(p.get("round") for p in pairs) == list(range(6)))

def valid_ci(row):
    values = row.get("ci95_percent", [])
    return len(values) == 2 and all(numeric(v) for v in values) and values[0] <= values[1]

def prepare_font(path=None):
    choices = [Path(path)] if path else [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf")]
    found = next((p for p in choices if p.is_file()), None)
    if found is None:
        raise ValueError("A Chinese font is required; supply --font with a local font file")
    font_manager.fontManager.addfont(str(found))
    family = font_manager.FontProperties(fname=str(found)).get_name()
    plt.rcParams.update({"font.family":family,"font.size":11,"axes.unicode_minus":False,
        "axes.titleweight":"bold","svg.fonttype":"path","savefig.facecolor":BG})
    return {"path":str(found),"sha256":sha(found),"family":family}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--fixture",action="store_true")
    parser.add_argument("--font",type=Path)
    parser.add_argument("--dpi",type=int,default=150)
    parser.add_argument("--formats",default="png,svg")
    parser.add_argument("--appendix",action="store_true",help="Also render p50, token, stress and ingestion figures")
    args = parser.parse_args()
    data = json.loads(args.analysis.read_bytes())
    artifact_hash = sha(args.analysis)
    artificial = args.fixture or data.get("experiment_commit") == "a"*40 or data.get("synthetic_fixture") is True
    audited = data.get("audit",{}).get("passed") is True
    formal = data.get("formal") is True and data.get("status") == "completed" and audited and not artificial
    if not args.preview and not formal:
        parser.error("Nonformal, artificial or unaudited evidence requires --preview")
    rows = data.get("comparisons",[])
    controls = data.get("control_comparisons",[])
    if not rows:
        parser.error("No comparison rows; no data chart can be made")
    if not args.preview:
        if data.get("method",{}).get("bootstrap_resamples") != 10000:
            parser.error("Formal plots require the frozen 10,000 paired-round bootstrap")
        if not all(six_rounds(row) and valid_ci(row)
                   and numeric(row.get("mean_paired_improvement_percent")) for row in rows+controls):
            parser.error("Formal plots require every displayed comparison to contain all six paired rounds and finite CI")
    formats = args.formats.split(",")
    if not formats or any(x not in ("png","svg","pdf") for x in formats):
        parser.error("--formats accepts png,svg,pdf")
    if not 80 <= args.dpi <= 400:
        parser.error("--dpi must be between 80 and 400")
    args.output.mkdir(parents=True,exist_ok=False)
    font = prepare_font(args.font)
    plt.rcParams["svg.hashsalt"] = artifact_hash
    variants = list(dict.fromkeys([r["variant"] for r in data.get("adoption",[])] +
                                 [r["variant"] for r in rows]))
    control_variants = list(dict.fromkeys(r["variant"] for r in controls))
    noise = data.get("aa_noise_flags",{})
    context = {"preview":args.preview,"synthetic_fixture":artificial,"formal_input":data.get("formal"),
               "audit_passed":audited,"analysis_status":data.get("status")}
    banner = ("人工数据 · 排版预览 · 不是实测结果" if artificial else
              "预跑 / 部分证据 · 仅供预览 · 不构成性能结论") if args.preview else (
              "正式测量 · A/A查询噪声未排除，不得用于采用" if noise.get("query_timing_noise_unresolved") else
              "正式测量 · 6轮成对比较 · 95%轮次置信区间")
    outputs, plotted = {}, []
    missing_count = 0

    def plot(name, title, panels, choices, *, control=False, metric=None):
        nonlocal missing_count
        if not panels:
            return
        ncols = min(2,len(panels))
        nrows = math.ceil(len(panels)/ncols)
        # Physical margins keep long Chinese labels, value columns and notes
        # separate even when metadata candidates add more rows.
        axis_height = max(1.7, .39*len(choices)+.35)
        panel_height, row_gap = axis_height+.93, .45
        width = 15.35 if ncols==2 else 7.9
        height = 1.6+nrows*panel_height+(nrows-1)*row_gap+.98
        fig = plt.figure(figsize=(width,height),facecolor=BG)
        axes = []
        for index in range(len(panels)):
            row, col = divmod(index,ncols)
            left = .4+col*7.45+2.05
            top = height-1.6-row*(panel_height+row_gap)-.4
            axes.append(fig.add_axes([left/width,(top-axis_height)/height,
                                     3.65/width,axis_height/height]))
        all_values = [0.0]
        show_ci = {}
        for panel_title, records in panels:
            found = {r["variant"]:r for r in records}
            for variant in choices:
                row = found.get(variant)
                if not row or not numeric(row.get("mean_paired_improvement_percent")):
                    continue
                all_values.append(row["mean_paired_improvement_percent"])
                enabled = six_rounds(row) and valid_ci(row) and (not args.preview or artificial or formal)
                show_ci[panel_title,variant] = enabled
                if enabled:
                    all_values.extend(row["ci95_percent"])
        if not control:
            all_values.extend([-3.0,5.0])
        low, high = min(all_values),max(all_values)
        span = max(10.0,high-low)
        bounds = (low-.10*span,high+.12*span)
        fig.suptitle(title,ha="left",x=.4/width,y=1-.15/height,fontsize=20,color=INK,fontweight="bold")
        fig.text(.4/width,1-.65/height,banner,va="top",fontsize=12,color="#9b4a0c" if args.preview else INK,
                 bbox={"facecolor":"#ffedcf" if args.preview else "#e6edf8","edgecolor":"none","pad":7})
        direction = "正值：Rust比同策略C快；负值：Rust更慢" if control else (
                    "正值：相对当前C/Python耗时降低；负值：耗时增加")
        fig.text(.4/width,1-1.12/height,direction,va="top",fontsize=10.5,color=MUTED)
        for index, ax in enumerate(axes):
            panel_title, records = panels[index]
            found = {r["variant"]:r for r in records}
            ax.set_facecolor("white")
            ax.set_xlim(bounds)
            ax.set_ylim(len(choices)-.4,-.6)
            for y in range(len(choices)):
                if y%2==0:
                    ax.axhspan(y-.5,y+.5,color="#f1f4f9",zorder=0)
            ax.axvline(0,color="#738297",lw=1.15,zorder=1)
            if not control:
                ax.axvline(5,color="#7caeaa",lw=.8,ls=(0,(4,4)),zorder=1)
                ax.axvline(-3,color="#d5a0a4",lw=.8,ls=(0,(2,4)),zorder=1)
            ax.grid(axis="x",color="#dce3ed",lw=.65,zorder=0)
            ax.set_axisbelow(True)
            for spine in ("top","right","left"):
                ax.spines[spine].set_visible(False)
            ax.spines["bottom"].set_color("#cad3e0")
            ax.tick_params(axis="y",length=0,pad=8,labelsize=11)
            ax.tick_params(axis="x",colors=MUTED,labelsize=9)
            ax.set_yticks(range(len(choices)),[(CONTROL if control else NAMES).get(v,v) for v in choices])
            ax.set_title(panel_title,loc="left",fontsize=12,color=INK,pad=18)
            ax.set_xlabel("每轮相对改善的均值（%）",fontsize=10,color=MUTED)
            ax.text(1.035,1.015,"均值 / 改善轮",transform=ax.transAxes,color=MUTED,fontsize=9)
            for y, variant in enumerate(choices):
                row = found.get(variant)
                if not row or not numeric(row.get("mean_paired_improvement_percent")):
                    missing_count += 1
                    ax.text(.5,y,"缺失 / 未完成",transform=ax.get_yaxis_transform(),
                            ha="center",va="center",color=MUTED,fontsize=10)
                    plotted.append({"figure":name,"panel":panel_title,"variant":variant,"missing":True})
                    continue
                value = row["mean_paired_improvement_percent"]
                enabled = show_ci.get((panel_title,variant),False)
                color = NEUTRAL
                if enabled and not args.preview:
                    lo,hi = row["ci95_percent"]
                    color = POSITIVE if lo>0 else NEGATIVE if hi<0 else NEUTRAL
                if enabled:
                    lo,hi = row["ci95_percent"]
                    ax.hlines(y,lo,hi,color=color,lw=2,zorder=3)
                    ax.vlines([lo,hi],y-.085,y+.085,color=color,lw=1.2,zorder=3)
                ax.scatter([value],[y],s=40,color=color,edgecolor="white",linewidth=.7,zorder=4)
                count = len(row.get("paired_rounds",[]))
                text = f'{value:+.2f}%  {row.get("improving_rounds",0)}/{count}'
                ax.text(1.035,y,text,transform=ax.get_yaxis_transform(),va="center",
                        fontsize=9.5,color=color,clip_on=False)
                plotted.append({"figure":name,"panel":panel_title,"variant":variant,
                    "baseline":row.get("baseline"),"cohort":row.get("cohort"),
                    "configuration":row.get("configuration"),"metric":row.get("metric"),
                    "mean_percent":value,"ci95_percent":row.get("ci95_percent"),
                    "ci_drawn":enabled,"paired_rounds":count,"missing":False,
                    "axis_bounds":list(bounds),"axis_scale":"linear"})
            if args.preview:
                ax.text(.97,1.075,"人工预览" if artificial else "预跑预览",transform=ax.transAxes,
                    ha="right",va="bottom",color="#ad5b18",fontsize=8,
                    bbox={"facecolor":"#fff2db","edgecolor":"none","alpha":.95,"pad":3})
        if args.preview:
            fig.text(.52,.48,"人工数据 · 非实测" if artificial else "预跑 · 非正式结论",
                     ha="center",va="center",fontsize=32,rotation=24,color="#b97837",alpha=.12,zorder=2)
        any_ci = any(r["ci_drawn"] for r in plotted if r["figure"]==name and not r["missing"])
        note = ("点=6轮成对相对改善均值；线=整轮bootstrap的95%CI；右列=改善轮数。"
                if any_ci else "点=已有轮次的相对变化；预跑不绘制置信区间，也不判断统计收益。")
        if artificial:
            note = "人工fixture的模拟数值；CI仅用于验证布局，不是实测证据。"
        if not control:
            note += "\n虚线：+5%收益参考 / −3%退化参考；最终采用仍由完整审计决定。"
        if metric in noise.get("ingestion_metrics_with_unresolved_noise",[]):
            note += " 此导入指标A/A噪声未排除。"
        note += "\n所有候选及负值完整保留；来源 analysis.json SHA256 "+artifact_hash[:16]+"…"
        fig.text(.4/width,.15/height,note,ha="left",va="bottom",fontsize=9,color=MUTED,linespacing=1.6)
        for extension in formats:
            path = args.output/(name+"."+extension)
            metadata = {"Date":None} if extension=="svg" else None
            fig.savefig(path,dpi=args.dpi,bbox_inches="tight",metadata=metadata)
            outputs[path.name] = sha(path)
        plt.close(fig)

    def scenarios(records, metric, kind):
        groups = []
        for cohort in COHORTS:
            for config in CONFIGS:
                selected = (config.endswith("char2400") and cohort!="unicode_stress") if kind=="ordinary" else (
                    config.endswith("char2400") and cohort=="unicode_stress") if kind=="stress" else config.endswith("token1024")
                if selected:
                    match = [r for r in records if r.get("metric")==metric and r.get("cohort")==cohort
                             and r.get("configuration")==config]
                    if match:
                        groups.append((COHORTS[cohort]+" / "+CONFIGS[config],match))
        return groups
    for metric in ("p50_ms","p95_ms"):
        if not args.appendix and metric!="p95_ms":
            continue
        display = "p50" if metric=="p50_ms" else "p95"
        for kind, title in (("ordinary","默认字符预算"),("stress","Unicode压力场景"),("token","Token预算")):
            if not args.appendix and kind!="ordinary":
                continue
            plot("latency-"+kind+"-"+display,title+" · "+display+" 相对耗时",scenarios(rows,metric,kind),variants)
            if controls:
                plot("control-"+kind+"-"+display,"同策略Rust / C对照 · "+display,
                     scenarios(controls,metric,kind),control_variants,control=True)
    for metric,(title,slug) in INGESTION.items():
        if not args.appendix:
            continue
        for records, choices, prefix, is_control in ((rows,variants,"ingestion-",False),
                                                    (controls,control_variants,"control-ingestion-",True)):
            panels = [(COHORTS[cohort],[r for r in records if r.get("cohort")==cohort
                       and r.get("configuration")=="ingestion" and r.get("metric")==metric]) for cohort in COHORTS]
            panels = [p for p in panels if p[1]]
            plot(prefix+slug,("同策略Rust / C · " if is_control else "")+title,panels,choices,
                 control=is_control,metric=metric)
    manifest = {"schema_version":1,"context":context,"source_analysis_sha256":artifact_hash,
        "plot_source_sha256":sha(Path(__file__)),"python":platform.python_version(),"matplotlib":matplotlib.__version__,
        "font":font,"outputs":outputs,"plotted_records":plotted,"missing_records":missing_count,
        "candidate_order":variants,"control_order":control_variants,"no_timings_collected":True,
        "limits":["CI来自冻结分析器的整轮bootstrap，不按查询重算。",
                  "所有轴均为完整线性范围，不裁剪负值或置信区间。",
                  "预览不能作为收益或采用证据；人工fixture不属于实测。",
                  "阶段或桥接实现的结果不能直接归因于完整语言迁移。"]}
    (args.output/"plot-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"output":str(args.output),"figures":len(outputs)//len(formats),
        "plotted_records":len(plotted),"missing_records":missing_count,"context":context,
        "no_timings_collected":True},ensure_ascii=False))

if __name__=="__main__":
    main()
