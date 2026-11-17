#!/usr/bin/env python3
"""Render audited experiment JSON as Chinese research Markdown/CSV, never timings."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

VARIANTS = {"current":"当前 C/Python", "rust_same":"Rust：同一接口", "c_table":"C：共享 Unicode 表",
    "rust_table":"Rust：共享 Unicode 表", "rust_window":"Rust：完整选窗阶段", "c_window":"C：完整选窗阶段",
    "node_window":"Node：完整选窗桥接", "node_small":"Node：小函数桥接",
    "rust_metadata":"Rust：完整候选元数据", "c_metadata":"C：完整候选元数据", "aa_current":"A/A 当前实现"}
COHORTS = {"synthetic61":"合成工程语料", "public1015":"公开语料", "unicode_stress":"Unicode 压力语料",
           "unicode-long-stress":"Unicode 长文本压力样例"}
CONFIGS = {"direct-char2400":"直接调用 · 2400 字符", "mcp-char2400":"MCP · 2400 字符",
           "direct-token1024":"直接调用 · 1024 token", "mcp-token1024":"MCP · 1024 token"}
INGESTION = {"fresh_ingestion_ms":"首次导入", "unchanged_ingestion_ms":"无变更重复导入",
             "changed_ingestion_ms":"内容变更导入"}
BOUNDARIES = {"rust_same":"保持原生接口，仅替换其中六个函数",
    "c_table":"C共享表策略对照；同时改变了数据与执行组织",
    "rust_table":"与C使用相同共享表策略，另作直接对照",
    "rust_window":"原生持有完整选窗计算阶段，不含上游归一化与命中查找",
    "c_window":"与Rust采用相同完整选窗阶段，不含上游归一化与命中查找",
    "node_window":"Python与常驻Node之间的完整选窗阶段桥接，不含上游归一化与命中查找，未实现全Node应用",
    "node_small":"Python与常驻Node之间的小函数桥接，未实现全Node应用",
    "rust_metadata":"完整有界候选元数据方法，保留原SQL和原地更新语义",
    "c_metadata":"与Rust采用相同完整候选元数据阶段"}

def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def fmt(value, digits=3, signed=False):
    return format(value, ("+" if signed else "") + "." + str(digits) + "f") if number(value) else "—"

def average(values):
    values = [v for v in values if number(v)]
    return statistics.fmean(values) if values else None

def median(values):
    values = [v for v in values if number(v)]
    return statistics.median(values) if values else None

def maximum(values):
    values = [v for v in values if number(v)]
    return max(values) if values else None

def cell(value):
    if type(value) is bool:
        return "是" if value else "否"
    return str(value if value is not None else "—").replace("|", r"\|").replace("\n", " / ").replace("\r", "")

def table(headers, rows):
    rows = list(rows)
    if not rows:
        return "_没有该类记录；不补造数值。_\n"
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                     "| " + " | ".join("---" for _ in headers) + " |"] +
                    ["| " + " | ".join(map(cell, row)) + " |" for row in rows]) + "\n"

def label(mapping, value):
    return mapping.get(value, value or "未标识")

def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flatten(child, prefix + "." + key if prefix else key))
    elif number(value):
        result[prefix] = value
    return result

def worker_key(worker):
    identity = worker.get("identity")
    variant = identity.get("variant", "unknown") if isinstance(identity, dict) else "unknown"
    match = re.fullmatch(r"(main|aa)-r(\d+)-(.+)-" + re.escape(variant), worker.get("key", ""))
    return (match.group(1), int(match.group(2)), match.group(3), variant) if match else (
        "unknown", None, "unknown", variant)

def export_csv(directory, name, records, context):
    records = [{**row, **context} for row in records]
    fields = list(context)
    for row in records:
        fields.extend(key for key in row if key not in fields)
    with (directory / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list))
                             else v for k, v in row.items()})

def diagnostics(paths):
    documents, bindings, files = [], {}, []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in sorted(path.glob("*.json")) if p.name != "files.json")
            ledger = path / "files.json"
            if ledger.exists():
                for name, expected in read(ledger).items():
                    if not (path/name).resolve().is_relative_to(path.resolve()):
                        raise ValueError("Diagnostic hash path escapes its directory")
                    if sha(path / name) != expected:
                        raise ValueError("Diagnostic hash differs: " + str(path / name))
                bindings[str(ledger)] = sha(ledger)
        else:
            files.append(path)
    for path in dict.fromkeys(p.resolve() for p in files):
        value = read(path)
        if not isinstance(value, dict) or not isinstance(value.get("records"), list):
            raise ValueError("Expected diagnostic records: " + str(path))
        documents.append((path, value))
        bindings[str(path)] = sha(path)
    return documents, bindings

def diagnostic_views(documents):
    raw, summaries, omissions, cold = [], [], [], []
    for path, doc in documents:
        source, rows = path.name, doc["records"]
        baseline = {(r["round"], r["case_id"]): r for r in rows if r["backend"] == "current-c"}
        groups = defaultdict(list)
        for row in rows:
            raw.append({"source_file":source, "diagnostic_status":doc.get("status"), **row})
            if row["backend"] != "current-c":
                groups[row["backend"], row.get("cohort"), row.get("phase"), row["function"]].append(row)
        for (backend, cohort, phase, function), values in sorted(groups.items(), key=lambda item:tuple(map(str,item[0]))):
            pairs = [(baseline.get((r["round"], r["case_id"])), r) for r in values]
            pairs = [(a,b) for a,b in pairs if a and number(a.get("ns_per_call")) and number(b.get("ns_per_call"))]
            a, b = average([x["ns_per_call"] for x,_ in pairs]), average([x["ns_per_call"] for _,x in pairs])
            summaries.append({"source_file":source, "diagnostic_status":doc.get("status"),
                "backend":backend, "cohort":cohort, "phase":phase, "function":function,
                "matched_cases":len({r["case_id"] for _,r in pairs}), "paired_case_rounds":len(pairs),
                "rounds_present":len({r["round"] for _,r in pairs}),
                "baseline_case_round_mean_ns":a, "candidate_case_round_mean_ns":b,
                "candidate_over_baseline":b/a if a and b is not None else None,
                "unpaired_records":len(values)-len(pairs)})
        omissions.extend({"source_file":source, **value} for value in doc.get("omissions", []))
        cold.extend({"source_file":source, **value} for value in doc.get("cold_starts", []))
    return raw, summaries, omissions, cold

def render(args):
    analysis = read(args.analysis)
    docs, input_hashes = diagnostics(args.diagnostics)
    input_hashes[str(args.analysis.resolve())] = sha(args.analysis)
    artificial = args.fixture or analysis.get("experiment_commit") == "a"*40
    audit = analysis.get("audit", {})
    formal = analysis.get("formal") is True
    eligible = formal and audit.get("passed") is True and analysis.get("status") == "completed" and not artificial
    invalid = not audit.get("passed") or analysis.get("status") not in ("completed","preflight-completed-not-adoptable")
    state = ("人工数据演示，禁止作为实测结果"+("；不完整或审计未通过" if invalid else "")) if artificial else (
        "不完整或审计未通过，禁止采用" if invalid else (
        "正式测量" if eligible else "预跑，仅验证流程，禁止作性能收益结论"))
    context = {"report_state":state, "formal":formal, "audit_passed":audit.get("passed"),
               "synthetic_fixture":artificial, "adoption_interpretation_allowed":eligible}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lines = ["# 语言实现对照研究报告", "", "> **"+state+"。**", "",
        "本报告保留有利和不利结果。比较对象是明确边界下的候选实现与语料，不能据此证明某种语言在所有实现中最优。",
        "正的改善百分比表示耗时降低；负值表示变慢。合并全部调用的p50/p95只是描述值；区间按整轮成对差异计算，不把每条查询当作独立样本。", ""]
    if not eligible:
        lines += ["**本页数值只用于核查数据和报告流程；不展示可用于推断收益的置信区间，不生成采用建议。**", ""]
    def section(title, description=""):
        lines.extend(["## "+title, ""])
        if description:
            lines.extend([description, ""])
    def emit(headers, rows):
        lines.extend([table(headers, rows), ""])
    def interval(row):
        ci = row.get("ci95_percent", [None,None])
        minimum = 3 if row.get("phase") == "aa" else 6
        return "["+fmt(ci[0],2,True)+", "+fmt(ci[1],2,True)+"]" if (
            eligible and len(row.get("paired_rounds",[])) == minimum and all(number(v) for v in ci)) else "不作区间推断"
    def improvement(row):
        return fmt(row.get("mean_paired_improvement_percent"),2,True)+"%；"+interval(row)
    def query_tables(rows, title, select):
        section(title)
        groups = defaultdict(dict)
        for row in rows:
            if row.get("metric") in ("p50_ms","p95_ms") and select(row):
                groups[row["cohort"],row["configuration"],row["baseline"]].setdefault(row["variant"],{})[row["metric"]] = row
        for (cohort,config,baseline), variants in sorted(groups.items()):
            lines.extend(["### "+label(COHORTS,cohort)+" / "+label(CONFIGS,config)+"；基线："+label(VARIANTS,baseline), ""])
            values = []
            for variant, metrics in variants.items():
                cells = [label(VARIANTS,variant)]
                for metric in ("p50_ms","p95_ms"):
                    row = metrics.get(metric,{})
                    a = (row.get("pooled_baseline") or {}).get(metric)
                    b = (row.get("pooled_candidate") or {}).get(metric)
                    cells += [fmt(a)+" → "+fmt(b), improvement(row),
                              cell(row.get("improving_rounds"))+"/"+cell(row.get("expected_rounds"))]
                values.append(cells)
            emit(["候选","p50 基线→候选 ms","p50 成对改善 / 95%区间","p50 改善轮",
                  "p95 基线→候选 ms","p95 成对改善 / 95%区间","p95 改善轮"], values)
    def ingestion_table(rows):
        emit(["语料","基线","候选","指标","各轮均值：基线→候选 ms","成对改善 / 95%区间","改善轮"],
             ([label(COHORTS,r["cohort"]),label(VARIANTS,r["baseline"]),label(VARIANTS,r["variant"]),
               label(INGESTION,r["metric"]),
               fmt(average([p["baseline_ms"] for p in r["paired_rounds"]]))+" → "+
               fmt(average([p["candidate_ms"] for p in r["paired_rounds"]])),improvement(r),
               str(r["improving_rounds"])+"/"+str(r["expected_rounds"])]
              for r in rows if r.get("configuration") == "ingestion"))
    section("证据状态")
    emit(["项目","值"], [("分析状态",analysis.get("status")),("正式运行",formal),("人工数据",artificial),
        ("审计通过",audit.get("passed")),("审计错误数",len(audit.get("errors",[]))),
        ("完整 workers / 预期",str(audit.get("completed_workers_loaded"))+"/"+str(audit.get("expected_workers"))),
        ("已完成报告调用数",audit.get("attempted_calls_in_completed_reports")),
        ("成对候选调用数",audit.get("paired_candidate_calls")),("Ledger 事件",audit.get("ledger_events_in_completed_reports")),
        ("基线提交",analysis.get("baseline_commit")),("实验提交",analysis.get("experiment_commit")),
        ("分析器 SHA256",analysis.get("analysis_source_sha256"))])
    if audit.get("errors"):
        emit(["审计错误","详情"], ((r.get("code"),json.dumps(r.get("detail"),ensure_ascii=False)) for r in audit["errors"]))
    section("计时边界与缓存")
    emit(["项目","本次测量边界"], [
        ("查询前的数据准备","每个worker使用新数据库，先完成首次导入和无变更重复导入；两种导入各自计时，随后进行查询。"),
        ("直接调用计时","从调用book.recall开始，到返回dict为止；后续JSON序列化、输出校验和ledger写入不计入查询耗时。"),
        ("MCP服务生命周期","每个MCP配置启动新的服务端；从启动到initialize完成的耗时单列，不计入单次查询。"),
        ("MCP查询计时","覆盖client.call_tool的stdio传输、SDK处理、服务端输出及正常recall_cache写入；返回后的结果校验不计入。"),
        ("查询结果缓存","直接调用设置use_cache=False；每次MCP调用前执行DELETE FROM recall_cache并提交，删除操作在查询计时之外。"),
        ("SQLite与操作系统缓存","不清空SQLite或操作系统缓存；新数据库不等于冷缓存查询。"),
        ("Token词表准备","direct及驱动进程在查询计时外准备cl100k_base词表；MCP服务端是新进程，不保证其首次token调用已预热。"),
        ("额外查询预热与计数","没有额外warmup查询，不丢弃最初调用；全部计划attempts纳入计时及ledger核对。"),
        ("激活指标","experimental_activation_ms仅计实验后端激活，不代表包含进程启动的完整CLI冷启动。")])
    section("候选边界与采用门槛","常规采用需预声明目标改善至少5%、整轮95%区间排除零、至少5/6轮改善，且没有关键场景超过3%的重复退化；压力语料获益单列。所有采用判断仍须服从审计和A/A控制。")
    emit(["候选","普通语料门槛","仅压力场景门槛","关键退化场景数","解释"],
         ([label(VARIANTS,r["variant"]),r.get("ordinary_production_gate") if eligible else "不适用",
           r.get("stress_only_gate") if eligible else "不适用",len(r.get("blocking_key_regressions",[])) if eligible else "不适用",
           BOUNDARIES.get(r["variant"],r.get("classification"))] for r in analysis.get("adoption",[])))
    comparisons, controls = analysis.get("comparisons",[]), analysis.get("control_comparisons",[])
    query_tables(comparisons,"默认字符预算：四类普通语料场景",
                 lambda r:r["cohort"] != "unicode_stress" and r["configuration"].endswith("char2400"))
    query_tables(comparisons,"Unicode 压力场景：单独解释",
                 lambda r:r["cohort"] == "unicode_stress" and r["configuration"].endswith("char2400"))
    query_tables(comparisons,"Token 预算：完整附表",lambda r:r["configuration"].endswith("token1024"))
    section("导入：首次、无变更、内容变更")
    ingestion_table(comparisons)
    query_tables(controls,"Rust / C 同策略直接对照",lambda r:True)
    lines += ["共享表或完整阶段相对当前实现的收益不能单独归因于Rust；以上同策略C/Rust对照用于区分实现组织与语言差异。", ""]
    ingestion_table(controls)
    section("A/A 与运行噪声","A/A采用相同二进制。查询噪声阻断采用；某个导入指标的A/A噪声阻断该指标收益。预跑没有A/A时，不把“未发现标记”当成“已排除噪声”。")
    emit(["查询噪声未解决","存在噪声的导入指标"], [(analysis.get("aa_noise_flags",{}).get("query_timing_noise_unresolved")
         if analysis.get("aa_comparisons") else "未测量；没有A/A记录",
         "、".join(analysis.get("aa_noise_flags",{}).get("ingestion_metrics_with_unresolved_noise",[])) or "未记录")])
    emit(["配置","指标","成对均值变化","95%区间","轮数"],
         ([r["configuration"],r["metric"],fmt(r.get("mean_paired_improvement_percent"),2,True)+"%",interval(r),
           len(r.get("paired_rounds",[]))] for r in analysis.get("aa_comparisons",[])))
    resources, worker_groups, mcp_groups = [], defaultdict(list), defaultdict(list)
    for worker in analysis.get("worker_resources",[]):
        phase,round_number,cohort,variant = worker_key(worker)
        base = {"worker":worker.get("key"),"phase":phase,"round":round_number,"cohort":cohort,"variant":variant,
                "worker_status":worker.get("status")}
        resources += [{**base,"resource_path":key,"value":value} for key,value in flatten(
            {"worker":worker.get("resources",{}),"configurations":worker.get("configurations",{})}).items()]
        if phase == "main":
            worker_groups[cohort,variant].append(worker.get("resources",{}))
            for config,value in worker.get("configurations",{}).items():
                if config.startswith("mcp-"):
                    mcp_groups[cohort,config,variant].append(value.get("resources",{}))
    def measured(values,path,reduction=median,divisor=1):
        result = reduction([flatten(x).get(path) for x in values])
        return fmt(result/divisor if result is not None else None)
    section("启动与进程资源","下表为跨轮中位数；HWM列取各进程记录的最大值。父进程与Node子进程分列，不能把不同时间的高水位相加称为同时峰值。worker末尾采样包含后续变更导入，不代表单次查询峰值。")
    emit(["语料","候选","激活 ms","新数据库 ms","父RSS MiB","Node RSS MiB","父HWM最大 MiB","Node HWM最大 MiB"],
         ([label(COHORTS,c),label(VARIANTS,v),measured(x,"experimental_activation_ms"),measured(x,"new_database_ms"),
           measured(x,"parent_after.rss_bytes",divisor=2**20),measured(x,"node_after.rss_bytes",divisor=2**20),
           measured(x,"parent_after.hwm_bytes",maximum,2**20),measured(x,"node_after.hwm_bytes",maximum,2**20)]
          for (c,v),x in sorted(worker_groups.items())))
    emit(["语料","MCP配置","候选","初始化 ms","服务端RSS MiB","Node RSS MiB","服务端HWM最大 MiB","Node HWM最大 MiB"],
         ([label(COHORTS,c),label(CONFIGS,k),label(VARIANTS,v),measured(x,"startup_to_initialize_ms"),
           measured(x,"server_after.rss_bytes",divisor=2**20),measured(x,"node_after.rss_bytes",divisor=2**20),
           measured(x,"server_after.hwm_bytes",maximum,2**20),measured(x,"node_after.hwm_bytes",maximum,2**20)]
          for (c,k,v),x in sorted(mcp_groups.items())))
    lines += ["**CPU边界：** calling_process_cpu_ms仅是调用进程CPU；MCP中指客户端，Node桥接时不含Node计算。服务端/Node的前后CPU采样可在CSV逐项核对，不能把父进程CPU称为总CPU。RSS是采样值；MCP服务端与其Node子进程不含完整驱动进程树。", ""]
    raw, helper_summary, omissions, cold = diagnostic_views(docs)
    for title,predicate in (("原生内核诊断",lambda b:b not in ("node-kernel","node-bridge","shell-rpc","shell-batch")),
                            ("Node：内部计算与桥接分列",lambda b:b in ("node-kernel","node-bridge")),
                            ("Shell：RPC 与批量摊销分列",lambda b:b in ("shell-rpc","shell-batch"))):
        section(title,"数值是匹配样例×轮次的平均调用成本，不是逐调用p95，也没有生产调用频率权重。不同来源文件的baseline各自配对，不合并成一个比较。")
        emit(["来源","语料 / 阶段","函数","后端","匹配样例 / 成对记录","当前C→候选 µs/次","候选/当前C成本比"],
             ([r["source_file"],label(COHORTS,r["cohort"])+" / "+str(r["phase"]),r["function"],r["backend"],
               str(r["matched_cases"])+"/"+str(r["paired_case_rounds"]),
               fmt(r["baseline_case_round_mean_ns"]/1000 if r["baseline_case_round_mean_ns"] is not None else None)+" → "+
               fmt(r["candidate_case_round_mean_ns"]/1000 if r["candidate_case_round_mean_ns"] is not None else None),
               fmt(r["candidate_over_baseline"],2)+"×"] for r in helper_summary if predicate(r["backend"])))
    lines += ["current-c包含Python到C调用；node-kernel排除JSON、IPC和Python重建，因此两者不是相同边界的语言对照。node-bridge包含这些实际开销；尚未测量完整Node应用。", "",
              "shell-rpc包含逐次编码、IPC、Bash扫描和解码；shell-batch只摊销一个帧的成本，仍不是纯内核计时。Shell只实现两个ASCII函数，没有完整检索、数据库或MCP实现。", ""]
    emit(["Shell启动样例","worker启动+STOP加载 ms","首次RPC ms","二者合计 ms"],
         ([r.get("index"),fmt(r["worker_startup_and_stop_load_ns"]/1e6),fmt(r["first_rpc_ns"]/1e6),
           fmt(r["startup_plus_first_rpc_ns"]/1e6)] for r in cold))
    section("遗漏、回退与原始数据","缺失输入不算零耗时。所有backend遗漏、逐轮数据、实际dispatch和资源原始字段均导出CSV；fallback数量保留，不将“已加载”当成“已执行”。")
    emit(["来源","遗漏记录数"], [(p.name,len(d.get("omissions",[]))) for p,d in docs])
    exports = {"comparisons.csv":comparisons,"controls.csv":controls,"aa.csv":analysis.get("aa_comparisons",[]),
        "adoption.csv":analysis.get("adoption",[]),"resources.csv":resources,
        "resource-comparisons.csv":analysis.get("resource_comparisons",[]),
        "dispatch.csv":analysis.get("dispatch_probes",[]),"diagnostic-records.csv":raw,
        "diagnostic-summary.csv":helper_summary,"diagnostic-omissions.csv":omissions,"shell-startup.csv":cold}
    for name,records in exports.items():
        export_csv(output,name,records,context)
    emit(["CSV","记录数"], [("["+name+"]("+name+")",len(records)) for name,records in exports.items()])
    section("来源与复核")
    for path,value in [(args.analysis,analysis),*docs]:
        relative = ("diagnostics/" if path != args.analysis else "")+path.name
        link = args.evidence_url.rstrip("/")+"/"+relative if args.evidence_url else "sandbox:"+str(path.resolve())
        lines += ["- ["+relative+"]("+link+")；SHA256 "+sha(path)+"；状态 "+str(value.get("status"))+"。"]
    lines += ["", "适用范围与限制：", "",
        "- 某个已审计候选在本语料获益，不证明该语言在所有可能实现中最快。",
        "- 共享表改变了数据和执行组织；完整阶段也改变了跨语言调用边界，应使用同策略C/Rust直接对照。",
        "- Node内部计算和Python桥接是不同边界；没有测量完整Node应用。",
        "- RSS为采样值；不同进程HWM不可相加后当作同时峰值。",
        "- 输出等价只排除时间诊断字段，仍要求payload、MCP envelope、来源坐标、索引和归档一致。",
        "- 下载证据可核对记录中的前后哈希；不能据此声称重新读取了原运行器上的所有源码与二进制。",
        "- 任一缺失、失败、不变量或审计错误都阻断采用；已完成的部分证据仍保留。",
        "- A/A导入噪声按指标阻断导入收益，A/A查询噪声阻断采用；关键重复退化持续保留。",
        "- 每场景区间没有进行跨多目标搜索的多重比较校正；压力场景改善不能代表普通语料改善。",
        "- 重建分析器必须有当前字节的自测；完整原始限制保留在analysis.json及CSV关联证据中。"]
    (output/"report.zh.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    manifest = {"renderer_sha256":sha(Path(__file__)),"context":context,"input_sha256":input_hashes,
        "output_sha256":{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        "csv_rows":{name:len(rows) for name,rows in exports.items()},"no_timings_collected":True}
    (output/"render-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--diagnostics",type=Path,action="append",default=[])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fixture",action="store_true")
    parser.add_argument("--evidence-url")
    args = parser.parse_args()
    result = render(args)
    print(json.dumps({"output":str(args.output),"state":result["context"]["report_state"],
                      "csv_rows":result["csv_rows"],"no_timings_collected":True},ensure_ascii=False))

if __name__ == "__main__":
    main()
