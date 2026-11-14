"""Render C6 READMEs only through the shared explicit acceptance validator.

The source/runtime/run/binding placeholders live in finish_round5_c6_release_docs.
Importing this module, or that validator module, never writes product documents.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validator_module():
    path = ROOT / "scripts/finish_round5_c6_release_docs.py"
    spec = importlib.util.spec_from_file_location("c6_release_docs_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_readmes(e, validator):
    root = ROOT
    a, h, run = e["a"], e["h"], e["run"]
    require = validator.require
    change_en, change_zh = validator.C6_CHANGE_SUMMARY, validator.C6_CHANGE_SUMMARY_ZH
    c5_mcp_gain = e["c5"]["acceptance"]["public_mcp_token1024_p95_improvement_percent"]
    outputs = {}
    def stage(path, text):
        require(path not in outputs, "Duplicate README output")
        outputs[path] = text
    g=a['acceptance_recomputed']; cells={(c['cohort'],c['id']):c for c in a['cells']}
    def cell(k): return cells['public1015',k]
    def gain(k): return -cell(k)['candidate_change_percent']['p95_ms']
    def p95(k,label): return cell(k)[label]['latency']['p95_ms']
    worst=max(g['resource_comparisons'],key=lambda r:r['mean_change_percent'])
    agg=g['geometric_mean_p95_improvement_percent']; maxres=worst['mean_change_percent']
    reg=[r for r in a['all_pooled_adverse_latency_metrics'] if r['metric'] in ('p50_ms','p95_ms')]
    strict_improvement=all(c['candidate_change_percent'][metric] < 0 for c in a['cells'] for metric in ('p50_ms','p95_ms'))
    latency_en='All twelve pooled p50 and p95 values improve.' if strict_improvement else 'Every pooled p50/p95 regression remains within the fixed 5% ceiling; every adverse cell is retained in the review.'
    latency_zh='十二组设置的合并 p50 和 p95 均降低。' if strict_improvement else '所有合并 p50/p95 退步均未超过固定的 5% 上限；全部不利结果保留在复核报告中。'
    en=f'''## Measured results

    **v0.3.3 passes its registered performance test against published v0.3.2 while preserving complete default retrieval output.** The single frozen run completed 56,784 calls; two separate saved-result audits verify its arithmetic and original call ledgers. [Formal review](docs/round5-c6-performance-review.md) · [Source and development record](docs/optimization-round5.md) · [Benchmark index](benchmarks/README.md).

    ### v0.3.3 efficiency and compatibility

    | Verified result | Measurement | Evidence |
    |---|---|---|
    | **Lower aggregate tail latency** | Pooled p95 geometric mean **−{agg:.2f}%** | 56,784 calls, two historical corpora, native/actual SDK MCP, character/token budgets and four balanced rounds. [All cells](docs/round5-c6-performance-review.md) |
    | **Faster public native token recall** | p95 **−{gain('native-token512'):.2f}% / −{gain('native-token1024'):.2f}% / −{gain('native-token2048'):.2f}%** at 512 / 1,024 / 2,048 tokens | 1,015 public-conversation questions; 4,060 samples per version/setting. [Saved report](benchmarks/reports/round5-c6-performance-{run}/report.summary.json) |
    | **Faster actual MCP token recall** | p95 **{p95('mcp-token1024','baseline'):.3f} → {p95('mcp-token1024','candidate'):.3f} ms (−{gain('mcp-token1024'):.2f}%)** | Official SDK stdio, 1,024-token cap, normal server cache writes and transport included. [Timing boundary](docs/round5-c6-performance-review.md) |
    | **Historical comparison output retained** | **2,304 / 2,304** complete default outputs match v0.3.2 | Old Hotpot256, two tokenizers, three native token caps and the component ranker. [Compatibility report](benchmarks/reports/round5-c6-hotpot-regression.summary.json) |

    All **28,392 baseline/candidate observations** match on complete non-timing output. {latency_en} **All fixed numerical gates pass, with no resource exception:** the largest registered resource mean increase is **{maxres:.2f}%**, below the 10% review trigger. [Independent arithmetic audit](benchmarks/reports/round5-c6-performance-independent-audit.json) · [Strict saved-ledger audit](benchmarks/reports/round5-c6-performance-local-audit.json) · [Full report](benchmarks/reports/round5-c6-performance-{run}/report.json.gz).

    {change_en} Earlier improvements in narrower database metadata reads, reduced Python work and certified exact token-count reuse remain in the candidate. A historical C3 probe of its derived metadata index recorded **196 KiB / 148 KiB** in two existing archives; their one-sample first opens rise **0.910 → 5.419 ms / 0.844 → 4.502 ms**. Those historical probes are not new C6 upgrade measurements. The connection-local SQLite pager target is **4 MiB**. The exact-count memo retains at most **2,048 entries / 2 MiB of text objects** per connection, shared by both tokenizers; container/key/value/encoder overhead is additional. Neither is a process-memory limit. Connections start empty, later native configurations reuse counts naturally, and actual MCP configurations each start a new server process. Query-result caches are disabled or cleared before timing; derived count reuse is enabled. Formal memory, initialization, ingestion and storage observations are all retained in the [cost review](docs/round5-c6-performance-review.md). Source text, citation fields and returned token totals are preserved; this version claims no new output-token savings.

    These are repeated old queries on one host, with no statistical-significance, unseen-quality or universal-speedup claim. The paired performance test compares Book versions; competitors were not remeasured. Historical v0.3.2 versus v0.3.1 aggregate p95 **−10.13%**, and v0.3.1 versus v0.3.0 **−11.36%**, remain separate measurements in the [round-four](docs/round4-performance-review.md) and [round-three](docs/round3-performance-review.md) reports; their percentages are not added to this run.

    Optional indexed references retain their separate historical **19.63% response-text token reduction** and **8.15% first-call reference-total reduction** (`o200k_base`, 1,015 questions, 4,000 characters). That option was not remeasured for v0.3.3. Counts include specified schema/instructions/arguments where stated, are not provider bills, and sparse references can cost more. [Format measurement](docs/indexed-references.md).

    The complete [C3 rejection](docs/round5-performance-review.md) and [C5 rejection](docs/round5-c5-performance-review.md) remain unchanged. C5 achieved only {c5_mcp_gain:.6f}% public actual-MCP p95 improvement against the 10% requirement; its `accepted:false` is retained. This release uses C6's separately bound accepted evidence and does not relabel C5 as passed.

    ### Historical open-source component comparison

    **The table below retains its original v0.3.2 measurements.** The v0.3.3 regression check reproduces all 1,536 native and 768 component default-output hashes on these same questions, preserving the old default evidence-quality result. It is not a new competitor timing or Q2 evaluation.

    '''
    zh=f'''## 实测结果

    **v0.3.3 已通过相对已发布 v0.3.2 的预先登记性能验收，并保持完整默认检索输出一致。** 唯一一次冻结正式测量完成了 56,784 次调用；两项独立的保存结果检查分别复核数值和原始逐次调用日志。[正式复核](docs/round5-c6-performance-review.md) · [源码与开发记录](docs/optimization-round5.md) · [基准索引](benchmarks/README.md)。

    ### v0.3.3 效率与兼容性

    | 已验证结果 | 测量结果 | 证据 |
    |---|---|---|
    | **综合尾部延迟降低** | 合并 p95 几何均值**降低 {agg:.2f}%** | 56,784 次调用，两组历史语料，原生与真实 SDK MCP，字符与 token 预算，四轮平衡测试。[全部设置](docs/round5-c6-performance-review.md) |
    | **公开会话原生 token 检索更快** | 512 / 1,024 / 2,048 token 下，p95 **降低 {gain('native-token512'):.2f}% / {gain('native-token1024'):.2f}% / {gain('native-token2048'):.2f}%** | 1,015 道公开会话问题；每个版本、每组设置 4,060 个样本。[保存报告](benchmarks/reports/round5-c6-performance-{run}/report.summary.json) |
    | **真实 MCP token 检索更快** | p95 **{p95('mcp-token1024','baseline'):.3f} → {p95('mcp-token1024','candidate'):.3f} ms（−{gain('mcp-token1024'):.2f}%）** | 官方 SDK stdio、1,024-token 上限，包含正常服务端缓存写入和传输开销。[计时边界](docs/round5-c6-performance-review.md) |
    | **历史竞品样本输出保留** | **2,304 / 2,304** 次完整默认输出与 v0.3.2 相同 | 原 Hotpot256，两种 tokenizer、三种原生 token 预算及组件排序器。[兼容性报告](benchmarks/reports/round5-c6-hotpot-regression.summary.json) |

    全部 **28,392 对版本观测**的完整非计时输出相同。{latency_zh}**固定数值门槛全部通过，没有资源例外：**登记的资源均值最大增幅为 **{maxres:.2f}%**，低于 10% 复核阈值。[独立数值审计](benchmarks/reports/round5-c6-performance-independent-audit.json) · [严格原始日志审计](benchmarks/reports/round5-c6-performance-local-audit.json) · [完整报告](benchmarks/reports/round5-c6-performance-{run}/report.json.gz)。

    {change_zh} 较早加入的更窄数据库元数据读取、减少重复 Python 工作及已验证的精确 token 计数复用继续保留。历史 C3 的两份旧库索引观察记录了 **196 KiB / 148 KiB**；单次首次打开耗时从 **0.910 → 5.419 ms / 0.844 → 4.502 ms**。这些旧探针不是新的 C6 升级测量。每个连接使用 **4 MiB** 的 SQLite 页缓存目标，并在两种 tokenizer 间共享最多 **2,048 项 / 2 MiB 文本对象**的精确计数缓存；容器、键和值等开销另计，两者都不是整个进程的内存上限。连接从空缓存开始；同一原生连接的后续配置会自然复用计数，真实 MCP 的每组配置则启动新服务进程。检索结果缓存按原规则禁用或在计时前清空，派生计数复用保持启用。正式内存、初始化、导入和存储观测均保留在[成本复核](docs/round5-c6-performance-review.md)中。原文、引用字段及返回 token 数保持一致，本版没有新增输出 token 节省声明。

    这些结果来自单机上的历史问题重复测量，不构成统计显著性、新样本质量或所有场景加速的证明。本轮性能测试比较 Book 的两个版本，未重测竞品。历史 v0.3.2 相对 v0.3.1 的总体 p95 **降低 10.13%**、v0.3.1 相对 v0.3.0 **降低 11.36%**，仍分别保留在[第四轮](docs/round4-performance-review.md)和[第三轮](docs/round3-performance-review.md)报告中，不与本轮百分比相加。

    可选精简引用保留其历史**响应文本 token 减少 19.63%**、**首次调用参考总量减少 8.15%**的独立测量（`o200k_base`、1,015 题、4,000 字符）。该选项未在 v0.3.3 重测。相关计数按报告边界包含 schema、指令和参数，不是服务商账单；稀疏引用可能更贵。[格式测量](docs/indexed-references.md)。

    完整的 [C3 拒绝记录](docs/round5-performance-review.md)和 [C5 拒绝记录](docs/round5-c5-performance-review.md)保持原样。C5 的公开语料真实 MCP p95 仅改善 {c5_mcp_gain:.6f}%，未达到 10% 要求，其 `accepted:false` 保留。本次发布只能使用独立绑定且通过验收的 C6 证据，不会把 C5 改写为通过。

    ### 历史开源组件对比

    **下表保留原来的 v0.3.2 测量身份。** v0.3.3 在同一批问题上重现了全部 1,536 次原生及 768 次组件默认输出哈希，保留原默认模式的证据质量结果。这不是新的竞品计时，也不是本轮 Q2 评估。

    '''
    for name,body,start,end in [('README.md',en,'## Measured results','A frozen **256-question'),('README.zh-CN.md',zh,'## 实测结果','冻结的 **256 道')]:
        p=root/name;t=p.read_text(); begin=t.index(start); finish=t.index(end,begin); t=t[:begin]+body+t[finish:]
        t=t.replace('**The fresh comparison also retains a regression against v0.3.1.**','**The historical round-four comparison also retains a regression against v0.3.1.**')
        t=t.replace('**新样本对比也保留了相对 v0.3.1 的退步。**','**历史第四轮对比也保留了相对 v0.3.1 的退步。**')
        stage(p, t)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="Optional cross-check; the run is derived from the verified evidence")
    args = parser.parse_args()
    validator = validator_module()
    evidence = validator.load_accepted_evidence()
    validator.require(args.run is None or args.run == evidence["run"], "Requested run differs from bound C6 evidence")
    outputs = render_readmes(evidence, validator)
    validator.write_outputs(outputs)
    print(json.dumps({"written": [str(p.relative_to(ROOT)) for p in outputs], "candidate": validator.SOURCE,
        "run": evidence["run"], "runtime_approval_changed": False}))


if __name__ == "__main__":
    main()
