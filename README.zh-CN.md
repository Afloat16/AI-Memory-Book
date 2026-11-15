# AI-Memory-Book

**给编程 AI 一份可核对、可延续的工程记忆。**

项目是书，任务是章，证据是页。AI-Memory-Book 保存规范化的原始文本会话，让 AI 在换会话、换客户端后，仍能找回工程约束、参数修正和失败尝试，引用来源后继续工作。

[English](README.md) · [快速开始](#快速开始) · [2400 字符实测](#2400-字符实测) · [开源方案对比](#开源方案对比)

**当前 main 源码 · MIT · Python 3.10+ · 本地 SQLite / FTS5**

## 工程中的优势

- **把决策与理由一起找回来。** 按项目、任务、会话和原始轮次定位证据，保留页面 ID 与来源；需要核对边界条件、错误信息或某次失败原因时，可以继续读原页，便于代码评审和任务交接。
- **跨命名方式找回代码约定。** `http_parser`、`JSONLReader`、`kv_cache` 等查询可以匹配对应的缩写、驼峰及下划线形式。词法索引补充别名，保留原始拼写、来源坐标与项目边界，便于恢复接口和算法实现约束。
- **兼顾当前修正与历史依据。** 明确询问“当前/current/latest”时，结合可比较的同会话轮次寻找后续修正，覆盖只有 token 上限触发截断的情况。询问历史决定则保留历史查询语义；排序不等于自动判断哪条决定权威。
- **让有限上下文用于工程约束。** 先按项目过滤，再检索和组装证据；默认 2400 字符、最多五条，缺什么再补读，便于同时恢复实现约定、数据划分和边界条件。
- **在已有客户端之间接续任务。** Claude Code、Codex、Gemini 等受支持客户端可以配置同一数据库。切换工具后仍可查询同一项目归档；客户端接入与原生历史采集的支持范围分别列在[集成指南](docs/integrations.md#supported-profiles)。
- **降低记忆层的部署与维护负担。** 默认写入和词法检索不调用模型，无需嵌入模型、数据库服务器或记忆服务 API Key。后台采集跳过未变文件，以稳定会话 ID 和内容哈希避免重复灌入；变更会话事务性替换，修改已有客户端配置前会创建备份。
- **让长期归档可检查、可恢复。** 在线 SQLite 备份包含 WAL 中已提交数据，校验完成后才生成新快照；只读检查提供完整性与运行状态，不迁移源库。派生索引升级保留已有页面地址，旧写入进程的不兼容操作会整笔回滚。

接续长期任务时，可以先问“当前实现必须遵守哪些约束？”，再按引用核对后续修正和失败尝试，最后继续修改代码。这类“恢复约定—核对出处—继续实现”的工作流，为任务交接提供明确的证据入口。[来源语义与使用方法](docs/agent-guide.md)。

## 快速开始

需要 **Python 3.10+ 与 SQLite FTS5**。本页新增的标识符检索、token 修正与数据库维护能力，请从当前源码安装：

~~~bash
git clone https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients,tokens]"
~~~

Windows 使用 `.venv\Scripts\Activate.ps1` 激活环境。精确 token 计数是可选能力。打开已有归档前，按 [schema 4 源码升级步骤](docs/deployment.md#current-main-and-schema-4)先保存快照，再统一升级、重启所有写入进程。

**已发布安装器：**下列命令安装当前发布版 v0.4.0；上述 main 新能力尚待发布。安装器使用隔离环境并包含 MCP/客户端依赖，无需克隆仓库或安装 Node.js。

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
~~~

**接入并检查**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

将 `claude-code` 换成[客户端配置名](docs/integrations.md#supported-profiles)，可重复 `--client` 接入多个客户端。只有支持原生采集的客户端才保留上述采集参数；其他客户端同时省略 `--capture` 和 `--background`。找不到命令时使用安装器输出的完整路径，然后重启客户端。

`--capture` 主动开启既有及未来受支持文本会话的采集，`--background` 安装并启动用户后台服务。仅配置 MCP 时同时省略这两个参数。工具调用由宿主和模型决定，MCP 接入本身不保证自动召回。升级应沿用相应安装方式，再刷新 setup 并重启客户端，详见[部署指南](docs/deployment.md#current-main-and-schema-4)。

## 算法与工程开发示例

[可运行示例](examples/engineering-workflow.json)包含四个项目、五段合成会话：负边最短路修正、训练数据切分约束、HTTP 解析约定、推理配置变更，以及另一项目中的冲突数值。无需模型 API，即可验证原文查询和项目隔离。

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db recall "jsonl_reader input contract and split" --project training-demo
memory-book --db ./demo-memory.db recall "current kv_cache block_size" --project inference-demo
memory-book --db ./demo-memory.db backup --output ./backups/demo-snapshot.db
memory-book --db ./backups/demo-snapshot.db check-database
~~~

在上述源码目录执行，并选择新的数据库和快照路径。[开发工作流指南](docs/engineering-workflows.md)讲解算法约束、失败尝试、标识符检索、Python 接入、精确 token 预算、来源核对及恢复操作。示例中的参数用于演示，不代表生产配置建议。

## 默认配置

默认使用**原生词法检索、2400 字符、最多五条结果**，无额外 token 上限。字符预算包含 `context` 内的引用头与分隔符，不是整个 JSON 响应或模型 token 的上限。

MCP 工具 `recall_memory` 示例：

~~~json
{
  "query": "当前梯度累积步数",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5
}
~~~

将项目 ID 替换为真实值；证据不足时使用返回的页面 ID 补读。CLI 同样可用：

~~~bash
memory-book projects
memory-book recall "当前梯度累积步数" --project your-project-id --budget 2400 --limit 5
~~~

## 2400 字符实测

### 工程回放：与常见策略比较

数据覆盖 **8 个项目、4 类算法、6 个时间检查点、80 个问题**，只摄取提问前的历史。其中 72 题有答案证据，共 80 条必需证据片段；48 题检查恢复的工程策略，另有 8 题缺证据。算法包括负边最短路、Top-k 同分、数据切分和全遮罩 softmax。

当前源码已重新运行未改动的 80 题工作负载，默认入口的完整非计时响应与显式 2400/5 调用及本轮保存输出逐题一致。重复调用只增加计时样本，不增加独立质量案例。[默认一致性验证](benchmarks/reports/developer-engineering-20261115/default-profile/report.json)。

| 策略 | 证据片段召回 | 完整证据 | 策略检查通过 | 平均字符 |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **78/80 · 97.50%** | **70/72 · 97.22%** | **46/48 · 95.83%** | **1818.9** |
| 同项目平铺 FTS | 60/80 · 75.00% | 52/72 · 72.22% | 28/48 · 58.33% | 1801.3 |
| 预算内最近历史 | 64/80 · 80.00% | 56/72 · 77.78% | 32/48 · 66.67% | 2260.9 |

Book 比平铺 FTS 多找全 **18 题**，完整证据率高 **25 个百分点**；比最近历史多找全 **14 题**，平均上下文少约 **19.6%**。FTS 是本仓库同范围、同索引和打包器的策略；最近历史使用内存文本、更短引用头且不限制前五条，是实用策略对照。[原生回放数据](benchmarks/reports/developer-engineering-20261115/current-workflow/report.json)。

### 哪些工程场景受益

以下是 2400 字符下的完整证据案例数，保留全部九类可答场景：

| 场景 | Book | 平铺 FTS | 最近历史 |
|---|---:|---:|---:|
| 后续决定修正 | **8/8** | 2/8 | 8/8 |
| 长间隔后恢复 | **8/8** | 2/8 | 0/8 |
| 多项约束共同恢复 | **8/8** | 2/8 | 8/8 |
| 回查历史决定 | **8/8** | 8/8 | 0/8 |
| 中英双语查询 | 6/8 | 6/8 | **8/8** |
| 初始决定、代码标识、失败尝试、来源替换合计 | 32/32 | 32/32 | 32/32 |

优势集中在较早证据被新消息推远、决定发生修正，以及需要同时恢复多项约束时。两条双语 `split_policy` 查询仍未找到当前证据，并只返回较早决定；Book **仅命中过时证据为 2 题**，平铺 FTS 为 14 题。来源引用有助于检查这个失败，不代表内容已经正确。

本次本机回放在 2400 字符下记录了 240 次调用，检索与上下文组装 **p50 / p95 为 1.573 / 2.700 ms**；结果缓存关闭，SQLite/系统缓存未清空，不包含摄取和模型生成。这是单环境诊断计时，不是受控加速结论或生产延迟保证。[本轮验证与边界](docs/developer-engineering-validation.md)。

### 与开源搜索组件的实跑对照

实际运行 [billion-context 固定搜索内核](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15)。双方得到**相同完整页面、项目范围、前五条限制和 2400 字符整块打包规则**；该轨道与上面的原生摘录轨道分别记录。

| 指标 | Book | billion-context 内核 |
|---|---:|---:|
| 证据片段召回 | **78/80 · 97.50%** | 72/80 · 90.00% |
| 完整证据 | **70/72 · 97.22%** | 64/72 · 88.89% |
| 策略检查通过 | **46/48 · 95.83%** | 40/48 · 83.33% |
| 平均字符 | **1818.9** | 1955.0 |
| 仅命中过时证据 | 2 | **0** |
| 预算违规 / 来源校验失败 | 0 / 0 | 0 / 0 |

在这项组件对照中，完整证据率高 **8.33 个百分点**，策略检查高 **12.50 个百分点**，平均上下文少 **6.96%**。逐题有 **8 个收益、2 个损失**：收益来自历史决定回查，损失来自双语查询。[组件数据与计时边界](benchmarks/reports/developer-engineering-20261115/current-components/report.json)。

这是固定组件结果；Book 保留层级/FTS 元数据，双方计时接口不同，不能推导完整产品加速。更小的 1200 字符整块预算下，Book 完整证据为 80.56%，对方为 88.89%；全部预算与失败案例均保留在[详细报告](docs/developer-engineering-validation.md)。

**实验边界：**这些是参与开发的合成案例，未调用编码 LLM，也不是独立测试集。策略检查由固定消费者提取记录中的配置，再执行手写算法，不能当作代码生成准确率。8 个缺证据问题仍返回相关上下文，需继续核实或明确缺证据。真实任务完成时间、补丁成功率与总模型成本尚未测量。[评测协议](docs/engineering-memory-evaluation.md) · [原始记录](benchmarks/reports/developer-engineering-20261115/)。

## 开源方案对比

下表依据各项目官方文档核对工程定位；除上述固定内核外，本轮未进行它们的同场景性能实测。

| 方案 | 主要工作方式 | Book 的适用优势 |
|---|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | 模型代理与客户端插件，模型驱动可逆压缩、解压和上下文搜索 | 独立归档并按项目查原始证据，通过 MCP 接入现有客户端，无需改变模型 API 路由 |
| [claude-mem](https://github.com/thedotmack/claude-mem) | hooks 采集，observer 生成 observations/摘要，本地 HTTP worker、SQLite，可选 Chroma | 默认采集和词法查询不增加摘要模型调用；stdio MCP 与采集无需 HTTP 监听 |
| [Mem0](https://docs.mem0.ai/open-source/python-quickstart) | 面向应用的用户/agent 记忆，默认模型抽取事实并使用 embedding，可配置本地存储 | 工程会话直接形成原文证据，不必配置额外的事实抽取与嵌入模型 |
| [Letta Code](https://github.com/letta-ai/letta-code) | 有状态 agent，自主管理记忆、技能及 Git 支持的 MemFS，可本地或云端运行 | 给现有编程客户端增加共享证据层，保留已有工具与工作流程 |

多客户端、来源查询和本地运行并非本项目独有。Book 的选择理由是将**原文证据、项目范围、预算控制和低附加推理依赖**集中到轻量记忆层，适合长期开发、故障复盘与跨客户端任务接续。

## 文档与数据边界

[开发工作流](docs/engineering-workflows.md) · [集成](docs/integrations.md) · [部署与 Docker](docs/deployment.md) · [AI 使用指南](docs/agent-guide.md) · [Token 预算](docs/token-budget.md) · [可选语义检索](docs/semantic-retrieval.md) · [贡献指南](CONTRIBUTING.md)

运行 `memory-book serve` 可在 [127.0.0.1:8765](http://127.0.0.1:8765) 检查归档。归档是本地未加密数据，召回证据会进入所用客户端的模型上下文；项目过滤不是多用户权限控制。客户端配置备份不等于数据库自动备份，详见[数据位置与维护](docs/deployment.md#data-and-configuration-paths)。

项目独立实现，采用 [MIT 许可证](LICENSE)。[当前发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.4.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)。
