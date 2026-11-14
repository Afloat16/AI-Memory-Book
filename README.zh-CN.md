# AI-Memory-Book

**让 AI 共享一份本地记忆，找回原始证据，带着出处继续工作。**

项目是书，任务是章，之前的决定可以跨会话、跨客户端保留。AI 通过一次 MCP 调用，取得预算范围内的相关原文，用来继续当前任务。

[English](README.md) · [快速开始](#快速开始) · [实测结果](#实测结果) · [文档导航](#文档导航) · [v0.3.3 发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.3)

**v0.3.3 · 正式发布 · MIT · Python 3.10+ · 本地 SQLite**

## 如何运作

```mermaid
flowchart TD
    H["支持的会话记录"] -->|"主动开启采集或手动导入"| B["本地归档：原文 + 来源地址"]
    T["AI 需要之前的工作记录"] -->|"一次限定范围的 MCP 调用"| R["查询 + 项目范围"]
    B --> R
    R --> L["默认：本地词法检索"]
    R -.-> S["可选：Q2 词法 + 语义融合"]
    L --> E["预算内的证据 + 来源引用"]
    S --> E
    E --> A["你的 AI 模型继续任务"]
```

后台采集独立更新归档；AI 可以直接检索，在需要更多细节时再读取原始页面。书架和章节提供可选导航，不必每次先遍历目录。[AI 使用指南](docs/agent-guide.md)。

## 核心亮点

- **默认轻量运行。** 记忆写入和词法检索零模型调用，核心只需 Python 与 SQLite，无需下载嵌入模型、启动数据库服务器或配置记忆服务 API Key。
- **原文可追溯。** 保留项目、会话、轮次和精确来源区间；内置字符预算，可选精确 tokenizer 上限，连同上下文中的引用和分隔符一起计数。
- **多个客户端共用记忆。** 支持 Claude Code/Desktop、Codex、Gemini、Cursor 等 MCP 配置；主动开启后可后台采集支持的会话，默认不启动网页服务。
- **效率有实测依据。** 当前核心在输出相同证据的同时降低延迟；可选精简引用减少重复来源元数据，具体结果与适用范围见下文。

## 快速开始

准备 **Python 3.10+，且 SQLite 支持 FTS5**。安装器将发布版 wheel 装入独立环境，并包含 MCP 和客户端配置依赖；无需克隆仓库或安装 Node.js。

**macOS / Linux**

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.3.3/scripts/install.sh
bash install-memory-book.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.3.3/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

**接入 AI**

```bash
memory-book setup --client claude-code --capture --background
memory-book doctor
```

若终端还找不到 `memory-book`，使用安装器输出的完整启动路径。重启客户端后，可以让 AI：**“找回我们之前对这个任务的决定，引用来源，然后继续完成。”**

把 `claude-code` 换成你的[客户端配置名](docs/integrations.md#supported-profiles)，或重复 `--client` 接入多个客户端。`--capture` 主动开启对既有和未来受支持文本会话的采集；省略它则仅配置 MCP。原生采集支持 Claude Code、Codex、Gemini 和旧版 Python Kimi；其他配置通过显式导入或开启 MCP 写入积累记忆。工具是否调用仍由宿主权限与模型决定。

**升级已有安装：**重新运行安装器，再以原来的客户端和采集选项执行 `setup`，使 MCP 和已有后台服务指向新环境。已有记忆和旧环境会保留。[升级说明](docs/deployment.md#upgrading)。

## 实测结果

**v0.3.3 已通过相对已发布 v0.3.2 的全部固定数值性能门槛，并保持完整默认检索输出一致。** 三项启动成本已按原计划完成单独的独立资源复核并获接受。唯一一次冻结正式测量完成了 56,784 次调用；两项独立的保存结果检查分别复核数值和原始逐次调用日志。[正式复核](docs/round5-c7-performance-review.md) · [源码与开发记录](docs/optimization-round5.md) · [基准索引](benchmarks/README.md)。

### v0.3.3 效率与兼容性

| 已验证结果 | 测量结果 | 证据 |
|---|---|---|
| **综合尾部延迟降低** | 合并 p95 几何均值**降低 14.80%** | 56,784 次调用，两组历史语料，原生与真实 SDK MCP，字符与 token 预算，四轮平衡测试。[全部设置](docs/round5-c7-performance-review.md) |
| **公开会话原生 token 检索** | 512 / 1,024 / 2,048 token 下，p95 **变化 -15.19% / -14.24% / -15.74%** | 1,015 道公开会话问题；每个版本、每组设置 4,060 个样本。[保存报告](benchmarks/reports/round5-c7-performance-43563390252-1/report.summary.json) |
| **真实 MCP token 检索更快** | p95 **6.711 → 5.894 ms（−12.17%）** | 官方 SDK stdio、1,024-token 上限，包含正常服务端缓存写入和传输开销。[计时边界](docs/round5-c7-performance-review.md) |
| **历史竞品样本输出保留** | **2,304 / 2,304** 次完整默认输出与 v0.3.2 相同 | 原 Hotpot256，两种 tokenizer、三种原生 token 预算及组件排序器。[兼容性报告](benchmarks/reports/round5-c7-hotpot-regression.summary.json) |

全部 **28,392 对版本观测**的完整非计时输出相同。十二组设置的合并 p50 和 p95 均降低。[独立数值审计](benchmarks/reports/round5-c7-performance-independent-audit.json) · [严格原始日志审计](benchmarks/reports/round5-c7-performance-local-audit.json) · [完整报告](benchmarks/reports/round5-c7-performance-43563390252-1/report.json.gz)。

固定数值门槛全部通过。原始自动结论仍保留 `accepted:false`，因为三项启动资源增幅触发了复核：两组语料的导入均值分别增加 3.197 / 2.990 ms，公开语料标记下的空库首次打开增加 5.100 ms（21.4109%）。[单独的资源复核](docs/round5-c7-resource-review.md)在保留全部样本和归因限制后接受这些启动成本；没有重跑计时、降低门槛或改写原始自动结论。
[明确的资源决定](benchmarks/experiments/round5-c7-resource-decision.json)将两份独立复核绑定到未改动的原始报告与源码。

C7 将官方 MCP SDK 的原生 stdout 写入与立即 flush 合并到一次工作线程调度，减少调度开销，同时保留完整消息、序列化和生命周期。 stdout 优化仅适用于已验证的官方 SDK 1.30.0 方法和原生标准流；每条成功消息仍立即 flush，保留官方序列化与生命周期。未知或自定义环境回退原 FastMCP stdio 路径。较早加入的更窄数据库元数据读取、减少重复 Python 工作及已验证的精确 token 计数复用继续保留。历史 C3 的两份旧库索引观察记录了 **196 KiB / 148 KiB**；单次首次打开耗时从 **0.910 → 5.419 ms / 0.844 → 4.502 ms**。这些旧探针不是新的 C7 升级测量。每个连接使用 **4 MiB** 的 SQLite 页缓存目标，并在两种 tokenizer 间共享最多 **2,048 项 / 2 MiB 文本对象**的精确计数缓存；容器、键和值等开销另计，两者都不是整个进程的内存上限。连接从空缓存开始；同一原生连接的后续配置会自然复用计数，真实 MCP 的每组配置则启动新服务进程。检索结果缓存按原规则禁用或在计时前清空，派生计数复用保持启用。正式内存、初始化、导入和存储观测均保留在[成本复核](docs/round5-c7-performance-review.md)中。原文、引用字段及返回 token 数保持一致，本版没有新增输出 token 节省声明。

这些结果来自单机上的历史问题重复测量，不构成统计显著性、新样本质量或所有场景加速的证明。本轮性能测试比较 Book 的两个版本，未重测竞品。历史 v0.3.2 相对 v0.3.1 的总体 p95 **降低 10.13%**、v0.3.1 相对 v0.3.0 **降低 11.36%**，仍分别保留在[第四轮](docs/round4-performance-review.md)和[第三轮](docs/round3-performance-review.md)报告中，不与本轮百分比相加。

可选精简引用保留其历史**响应文本 token 减少 19.63%**、**首次调用参考总量减少 8.15%**的独立测量（`o200k_base`、1,015 题、4,000 字符）。该选项未在 v0.3.3 重测。相关计数按报告边界包含 schema、指令和参数，不是服务商账单；稀疏引用可能更贵。[格式测量](docs/indexed-references.md)。

完整的 [C3 拒绝记录](docs/round5-performance-review.md)、[C5 拒绝记录](docs/round5-c5-performance-review.md)和 [C6 拒绝记录](docs/round5-c6-performance-review.md)保持原样。C5 和 C6 的公开语料真实 MCP p95 分别仅改善 6.673181% 和 5.798911%，未达到 10% 要求，两者均保留 `accepted:false`。本次发布只能使用独立绑定且通过验收的 C7 证据，不会把较早候选改写为通过。

### 历史开源组件对比

**下表保留原来的 v0.3.2 测量身份。** v0.3.3 在同一批问题上重现了全部 1,536 次原生及 768 次组件默认输出哈希，保留原默认模式的证据质量结果。这不是新的竞品计时，也不是本轮 Q2 评估。

冻结的 **256 道 HotpotQA 问题**排除了全部 **640 个历史问题 ID**，重叠数为零。源码、评估器、依赖和模型在选题前完成绑定，题目清单在首次评分前发布。完整对比保留 **9,216 次实测调用，其中原生调用和组件搜索各 4,608 次**，对应 **635 条必需证据标注**。下表采用相同原始页面、前五条结果及统一的完整块打包器，预算为 **1,024 个 `cl100k_base` token**，测量返回的来源证据。[完整报告](benchmarks/results/round4-comparison-43363060062-1/report.md)保留所有预算、原生调用及逐题得失。

| 实测组件 | 证据召回率 | 完整证据率 | 打包后 MRR | 平均上下文 token | 搜索适配器 p95 |
|---|---:|---:|---:|---:|---:|
| **Book v0.3.2 · 默认词法** | 75.75% | 53.91% | 0.8578 | 714.8 | 3.488 ms |
| **Book v0.3.2 · 可选 Q2** | 76.69% | 55.08% | **0.8663** | 730.0 | 20.406 ms |
| claude-mem 15.18.1 · 原生 FTS | 70.39% | 44.53% | 0.8280 | 709.4 | 34.655 ms |
| ai-memory v3.4.5 · 本地混合检索 | 77.48% | 55.86% | 0.8400 | 709.9 | 39.925 ms |
| billion-context `9674cfa` · 搜索内核 | **80.94%** | **60.55%** | 0.8606 | 757.4 | **1.449 ms** |

在这个切片上，Book 默认词法的完整证据率比 claude-mem FTS **高 9.375 个百分点**，其已测搜索适配器 p95 相对 claude-mem **低 89.94%**、相对 ai-memory **低 91.26%**；Q2 的 p95 也低于两者，且在这五个组件中具有最高的打包后 MRR。**ai-memory 的证据召回率和完整率高于 Book 的两种模式；billion-context 的召回率、完整率和搜索延迟领先。** 这些优势具有明确的测量范围，不据此宣称总体胜出。

搜索 p95 合并每题三次搜索，不包含离线统一打包及额外原文读取。适配器分别跨越 Python 检索与组装、SQLite/Bun、HTTP/MCP 和 Node 等不同边界，因此不能据此推导整套产品的倍数优势。ai-memory 首次搜索加全部五次原文读取的 p95 为 **45.897 ms**；读取响应、原始命中位置与初始化成本另行记录。打包后 MRR 衡量统一打包器省略元数据或超大块之后的证据排序。

这个预算下，Q2 相对默认词法的完整率提高 **1.171875 个百分点**：**26 道题获得完整证据、23 道题失去完整证据**，净增加三道。在原生 API 的 512-token 预算下，`cl100k_base` 完整率从 **39.45% 降至 36.33%**（19 题改善、27 题退步），`o200k_base` 从 **39.45% 降至 36.72%**（19 题改善、26 题退步）。Q2 组件初始化耗时 **277.60 秒**，其中索引构建为 **275.43 秒**；查询阶段采样得到的进程树峰值 RSS 为 **1,247.69 MiB**。其搜索 p95 为 20.406 ms，也高于默认词法的 3.488 ms，因此保持主动开启。[完整得失与成本](benchmarks/results/round4-comparison-43363060062-1/report.md)

**历史第四轮对比也保留了相对 v0.3.1 的退步。** 组件排序器使用 100,000 字符上限时，默认 Book 的 p95 从 **3.304 升至 3.488 ms（+5.56%）**，p50 从 **2.239 升至 2.353 ms（+5.12%）**。初始化阶段采样得到的进程树峰值 RSS 从 **548.65 升至 943.53 MiB**，查询阶段峰值则从 **529.77 降至 524.91 MiB**。这些是按顺序执行、未经平衡排列的组件描述性观测，与上方预先登记的 ABBA 性能门槛分别报告。RSS 包含评估器、语料和子进程内存，共享映射可能被重复计算；这些数据没有确立初始化内存增加的原因。[详细证据与限制](docs/optimization-round4.md)

![v0.3.2 完整证据率、搜索适配器延迟与独立配对性能测量](docs/assets/v0.3.2-comparison.svg)

图表使用与表格相同的已保存测量。完整评估验证了 Book 两个版本间 **1,536 对原生调用和 768 对组件调用**的完整输出相同。[离线审计](benchmarks/reports/round4-comparison-independent-audit.json) · [完整对比与原始结果](benchmarks/results/round4-comparison-43363060062-1/report.md) · [已归档的 v0.3.1 对比及限制](docs/round3-continuation.md#published-release-and-supplemental-audit)。

所有题目都有答案，且来自同一公开 HotpotQA 数据源；ID 不重叠不能证明跨数据域泛化。这些已评分的 ID 现已成为回归数据。这些结果衡量返回的证据，不衡量答案生成、幻觉或私人会话迁移能力。本次对比没有调用生成式模型。

[部署与架构对比](docs/comparison.md#popular-projects-and-the-workload-they-address)还包括 **Mem0、Graphiti、PageIndex 和 Letta**，与实跑基准明确区分。ai-memory 也支持默认零 LLM 路径；claude-mem 支持本地模型供应端。

## 文档导航

| 你想做什么 | 入口 |
|---|---|
| 接入其他客户端、导入会话 | [客户端与导入格式](docs/integrations.md) |
| 安装、升级、Docker、管理后台采集 | [部署指南](docs/deployment.md) |
| 了解何时检索、引用原文、处理缺失证据 | [AI 使用指南](docs/agent-guide.md) |
| 开启精确 token 上限、Q2 语义或精简引用 | [Token 预算](docs/token-budget.md) · [语义检索](docs/semantic-retrieval.md) · [精简引用](docs/indexed-references.md) |
| 在浏览器检查归档 | 运行 `memory-book serve`，打开 [127.0.0.1:8765](http://127.0.0.1:8765) |
| 查看完整实验或参与开发 | [基准索引](benchmarks/README.md) · [验证记录](docs/validation.md) · [贡献指南](CONTRIBUTING.md) · [更新日志](CHANGELOG.md) |

可选 Q2 运行时会主动退出 ONNX Runtime 遥测。归档是本地未加密数据；返回给 AI 客户端的证据会进入该客户端的模型上下文。网页阅读器用于检查归档，正常 MCP 和采集无需 HTTP 端口。[数据与配置位置](docs/deployment.md#data-and-configuration-paths)。

[CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)覆盖 Python 3.10/3.12/3.13、真实 MCP stdio、网页阅读器、Linux/macOS/Windows 安装器和容器持久化。配置样本测试不代表每款厂商应用都完成交互认证。项目独立实现，采用 [MIT 许可证](LICENSE)。
