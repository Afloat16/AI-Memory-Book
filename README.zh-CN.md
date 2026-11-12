# AI-Memory-Book

**给 AI Agent 使用的后台记忆。项目成书，任务成章，AI 按需取回有出处的原文，然后继续完成任务。**

[English — 主 README](README.md) · [Agent 使用指南](docs/agent-guide.md) · [部署与后台运行](docs/deployment.md) · [客户端兼容表](docs/integrations.md) · [完整实测索引](benchmarks/README.md)

AI-Memory-Book 的主要使用者是 AI。接入客户端并选择开启采集后，后台把受支持的会话整理成可检索记忆。当任务依赖之前的决定、约束或未完成步骤时，AI 可以通过 MCP 直接取回预算内的原文和出处，接着处理当前任务。它不需要每次先读目录，也不需要加载完整历史会话。

当前为 **v0.3 开发版**，MIT 开源、实验版本。主入口是供 Agent 调用的 **MCP 工具**；后台默认无界面运行，不启动 HTTP 阅读器。网页只作为可选的检查与调试工具。核心检索不需要 API key、模型调用或向量数据库。

服务向 AI 提供按需读取策略，但是否调用工具仍由宿主和模型决定。项目不承诺每个客户端都会自动调用，也不要求每次提问都读取记忆。

## 为什么选择 AI-Memory-Book

它适合需要持续推进项目、复用先前决定、核对原始依据的 Agent 工作流：

| 优势 | 带来的能力 |
|---|---|
| **默认记忆路径不调用模型** | Python + SQLite 在本地索引和词法检索，核心不产生逐轮总结的模型费用，也无需下载 embedding 模型或部署独立数据库；回答模型由你的客户端选择。 |
| **保留原文，引用可核对** | 直接返回原始证据及项目、会话、轮次；需要时可展开精确字符区间和完整页，检查决定的依据。 |
| **一次 MCP 调用即可获得上下文** | `recall_memory` 直接组装预算内证据，可按项目、章节、会话限定范围，供 Agent 继续当前任务。 |
| **按需使用精确上下文上限** | 可选指定 tokenizer 的 token 上限，与字符上限同时生效，包含引用与分隔符；已能放入的原文块保持完整，剩余空间可补入原文语句。 |
| **可选的索引引用格式** | 用整次响应共用的会话表编码重复引用，来源身份与详细偏移均可还原；显式在 MCP 启动时启用，默认客户端的 schema 和初始化说明保持原样。 |
| **多个客户端共用本地归档** | 支持的客户端连接同一数据库；选择开启后台采集后，受支持的文本会话会增量进入记忆。 |
| **部署轻，归档易检查** | 默认后台与 MCP 均不需要 HTTP 监听；可选阅读器、导出工具和保留原文的迁移机制便于检查和维护。 |

具体行为见 [Agent 使用指南](docs/agent-guide.md)、[部署与采集说明](docs/deployment.md)和[来源保留与迁移验证](benchmarks/RESULTS-recall-score-quality.md#8-source-preserving-schema-migration)。

### 最新验证的对比结果

当前版本提供**不调用模型的默认词法模式**，以及显式启用的 **Q2 本地语义模式**。最新固定源码比较在**同一台机器**上执行两种 Book 模式和三个固定版本的上游组件，使用相同 **1,024 `cl100k_base` token 的共同上下文上限**：

| 当前检索组件 | 证据召回 ↑ | 完整证据率 ↑ | 打包上下文 MRR ↑ | 平均上下文 token | 搜索 p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| **Book，默认词法** | 75.41% | 51.95% | 0.8596 | 712.9 | 4.712 / 8.301 |
| **Book，可选 Q2 语义** | **78.66%** | **57.81%** | **0.8686** | 727.8 | 14.014 / 22.523 |
| [claude-mem 15.18.1](docs/comparison.md)，原生 SQLite FTS | 72.31% | 48.83% | 0.8348 | 704.5 | 16.254 / 29.948 |
| [ai-memory v3.4.5](docs/comparison.md)，本地混合检索 | 76.22% | 53.91% | 0.8633 | 704.0 | 25.947 / 33.251 |
| [billion-context 9674cfa](docs/comparison.md)，搜索内核 | 80.94% | 61.72% | 0.8622 | 751.3 | 0.349 / 1.092 |

此设置下，Book Q2 的完整证据率相对 claude-mem FTS **高 8.98 个百分点**，相对 ai-memory **高 3.91 个百分点**，打包上下文 MRR 也是本表最高。默认 Book 保持零模型路径，组件 p95 低于上述两个组件。**billion-context 在本组题目的证据召回、完整度和搜索耗时上领先**，当前完整结果如实保留。

**测量范围：**预先固定的 256 道可回答 HotpotQA 多跳题，保留全部 2,539 段给定资料、3,769 个标准页面和 614 条支持标注；使用相同项目范围、top-5、引用及整页打包规则。质量每题计一次，耗时测量三个真实重复；MRR 衡量打包后证据的顺序。Book 原生摘录打包另有矩阵：在 1,024 cl100k token、8,000 字符下，完整证据率为**词法 51.95% / Q2 57.42%**。

搜索耗时保留各自接口：Book Python 与原生上下文组装、claude-mem Bun/SQLite FTS、ai-memory HTTP/MCP，以及 billion-context 的 Node 搜索内核。共同打包和准备成本另列。ai-memory 按声明策略执行“首次搜索 + 全部源页读取”的 p95 为 **37.613 ms**，平均每题 **4.98 次读页**。这些是组件测量，不能换算成完整产品速度倍数或最终回答分数。[完整当前比较](docs/comparison.md)保留所有预算/tokenizer、平均及首次/重复耗时、原生返回 token、建索引、下载、RSS 和存储。**32,256 次计时调用**已通过[完整固定源码恢复验证](docs/round2-recovery.md)，第一次失败的记录也已保存。

### 速度、响应大小与运行成本

当前源码的**可选索引引用格式**已完成独立实测。在全部 1,015 道公开会话题、默认 4,000 字符上限下，实际 MCP 返回文本的 `o200k_base` token **减少 19.63%**；计入完整工具 schema、初始化说明和调用参数后，首次调用的参考 token 总量仍**减少 8.15%**。

| 当前 MCP 格式 | p50 | p95 | 平均响应文本 token | 首次调用参考 token |
|---|---:|---:|---:|---:|
| 默认 `objects` | 5.503 ms | 7.126 ms | 1,464.8 | 2,621.0 |
| **显式启用 `indexed`** | **5.466 ms** | 7.131 ms | **1,177.2** | **2,407.4** |

两行使用**相同固定实现**、官方 SDK 和源归档，交替顺序测量四轮，每次清空查询结果缓存。上下文、页 ID 和完整来源字段均可原样还原。此 encoding 下，索引格式增加 74 个初始化说明 token，工具 schema 和每次参数不增加；默认客户端不承担这项增量。1,015 题中有 1,014 题的首次调用净 token 更少。引用较少时仍可能增加；此格式也不承诺提速，表中 p95 增加 0.005 ms。参考 token 计数对应实测 SDK 文本与元数据，不是服务商账单。[全部 12 配置、两种 tokenizer、逐题损失及复现方式](docs/indexed-references.md)。

**默认核心优化**另有保持完整输出一致的成对实测：12 组“语料/接口/字符上限”配置的合并样本 p95 均降低，**进程内降低 1.32%–13.65%，真实 MCP 降低 1.25%–9.50%**。公开语料的首次写入耗时**降低 46.45%**，未变化会话的重复导入耗时**降低 61.38%**；返回 token 和来源/索引内容保持一致。[完整报告](docs/default-recall-performance.md)保留所有轮次和少数单轮的小幅耗时退步。

默认记忆写入和词法检索为**零模型调用**，无需 embedding 下载或独立数据库服务；可选语义模式另有模型、索引及查询成本。回答模型由使用者选择。[完整组件成本与部署比较](docs/comparison.md)覆盖 **claude-mem、ai-memory 和 billion-context**，分别列清原生搜索/读页、准备、存储和 RSS 边界，也依据官方来源比较 **Mem0、Graphiti、PageIndex 与 Letta**。ai-memory 默认路径同样可以零 LLM 运行；claude-mem 也支持本地模型。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

### 选择版本

| 版本 | 可用能力 | 使用方式 |
|---|---|---|
| **已发布的实验版本 v0.2.1** | 以 Agent 为主的 MCP、共享本地记忆和可选无界面后台采集 | 使用下方固定版本安装器。 |
| **已推送的 v0.3 开发源码** | 更快的本地检索与写入、可选索引引用、精确 token 预算、多事实 coverage、本地语义检索及可复现的组件/回答评测 | 按[开发版源码安装](#开发版源码安装)检出 `main`。 |

下方安装器仍使用已发布的 **v0.2.1**，目前没有可下载的 `v0.3.0` 发布标签。体验新增能力请从 `main` 安装源码。

macOS / Linux：

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.1/scripts/install.sh
bash install-memory-book.sh
```

Windows PowerShell：

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.1/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

安装器建立独立环境，默认安装 MCP 和客户端配置依赖，并打印可执行文件的绝对路径。如果 `memory-book` 尚未加入 PATH，使用显示的路径。不会修改 shell 配置或执行策略。

### 开发版源码安装

`main` 源码会继续更新，可能已包含固定评测提交之后的新改动：

```bash
git clone --branch main https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients]"
```

Windows 使用 `.venv\Scripts\Activate.ps1`，也可直接运行 `.venv\Scripts\python.exe`。复现测量时，使用[评测索引](benchmarks/README.md)中对应实验锁定的源码提交和方案；`main` 会继续更新。只需核心时可安装 `pip install -e .`。项目尚未发布到 PyPI，不使用无版本来源的 `pip install ai-memory-book`。

## 接入 AI 并启用后台记忆

```bash
# 接入 MCP，选择开启支持的会话采集和登录启动
# 默认只运行后台采集，不启动网页或 HTTP 端口
memory-book setup --client claude-code --client codex --capture --background

memory-book doctor
memory-book service status
```

配置后重启客户端或刷新 MCP 列表，随后继续在原客户端工作。预期流程是 AI 在任务需要历史时调用记忆，用来源支撑判断，再继续执行；客户端自己的信任、工具授权提示仍然生效。要主动检查接入，可以问：“使用 memory-book 查一下之前为什么选择这个缓存方案，给出出处，然后继续实现。”

`--capture` 开启对显示路径内现有和后续文本会话的读取。只执行 `memory-book setup --client claude-code` 时仅配置 MCP，记忆可来自其他采集来源或显式导入。使用 `--dry-run` 预览；`--all` 配置检测到的客户端，并明确报告哪些只有 MCP 能力。

仅采集一个工作区：

```bash
memory-book setup --client codex --capture --workspace /absolute/path/to/project \
  --project my-project --background
```

原设置会保留，变更前备份，重复执行不重复添加。JSONC 或无效配置不会自动重写，会提供手动合并片段。运行中的后台进程会重新加载配置，收窄范围或移除来源无需等待下次登录。

## AI 怎样使用这本记忆书

主流程是：**客户端接入 → 后台采集 → AI 按需调用 MCP → 得到预算内原文及出处 → 继续任务**。采集与检索分别运行。无需历史就能完成的问题可以直接处理；“继续上次实现”“之前为什么这样决定”这类任务才需要寻找历史依据。

例如，AI 继续虚构的 `atlas` 项目缓存任务时，可以向 `memory-book` 服务发送下面的 `tools/call` 参数。不同客户端显示的服务/工具前缀可能不同，实际工具名是 `recall_memory`：

```json
{
  "name": "recall_memory",
  "arguments": {
    "query": "搜索缓存最终保留多久？为什么从300秒调整？",
    "project": "atlas",
    "budget_chars": 2000,
    "limit": 5
  }
}
```

返回的 `context` 包含预算内证据，结果还提供页 ID、`project`、`session_id`、`turn_index` ；精确字符区间通过 `details: true` 或 `read_page` 按需获取。在[示例归档](examples/conversations.json)中，缓存复核记录把有效期从 300 秒改为 45 秒，并保留 revision 失效机制。AI 可以引用 `atlas / atlas-cache-review / turn 0`，核对来源时间，再据此继续实现。历史证据可能已经过时或互相冲突，不能直接当成当前指令。

引用较多的场景还可使用开发版的 `memory-book mcp --source-format indexed`。它保留相同证据，用带版本的会话表和可还原的数组表示引用。这个启动选项不会增加默认客户端的工具参数或 schema 成本；启用后会增加解码说明，引用较少或空响应可能更大。见[格式、客户端配置与实测成本](docs/indexed-references.md)。

**设置上下文预算：**Python/MCP 的 `budget_chars` 和 CLI 的 `--budget` 限制组装后上下文的字符数。开发源码现已支持**可选的精确 token 上限**：`budget_tokens` / `--budget-tokens`，可选择 `cl100k_base` 或 `o200k_base`。两个上限同时约束 `context`，均包含引用与分隔符；外层 JSON 元数据、工具 schema 和其余对话不在上限内。安装 `tokens` 依赖后即可使用：

```bash
python -m pip install -e ".[tokens]"
memory-book recall "cache expiry and retry window" --project atlas \
  --budget 4000 --budget-tokens 512 --tokenizer cl100k_base --json
```

MCP 在 `arguments` 中加入 `"budget_tokens": 512` 和 `"tokenizer": "cl100k_base"`；Python 使用相同参数名。响应返回精确的 `context_tokens` 和 tokenizer 版本；`estimated_tokens` 仍是按字符估算的字段。不传 token 上限时，原来无依赖的字符预算路径保持不变。首次加载词表可能需要公开下载，离线部署应预先缓存。[API、离线准备、原文保留约定与成本](docs/token-budget.md)。

组件对比使用共同的**整页评测打包器**；新 API 组装**原生摘录和完整原文单元**，两者基线不同，新结果不会替换历史对比口径。见[预算验证与实测取舍](#验证与可选模式)。

目录是 AI 可选的定位工具。直接召回不足以确认项目、章节或上下文时，再按需要展开：

| 层级 | 含义 | MCP 工具 |
|---|---|---|
| 书架 | 项目未知时发现项目 ID | `browse_projects` |
| 书 | 一个项目的章节目录 | `browse_book(project)` |
| 章 | 使用同一显式任务 ID 的一个或多个会话 | `browse_chapter(chapter_id)` |
| 节 | 会话中相关的连续提问 | `browse_section(section_id)` |
| 页 | 有精确来源区间的原文 | `read_page(page_id)` |

不需要按照表格逐级调用。已知项目/章节/会话时可以直接过滤检索；需要展开时使用服务返回的 ID。短追问可以保留在一起，长回答拆成续页，默认自适应页上限为 900 字符。跨会话章节仍依赖明确的 `task_id`。

[Agent 使用指南](docs/agent-guide.md)说明何时读取、如何使用引用和预算、缺少或冲突证据时怎样处理。项目不安装厂商会话 hooks，也不强制向每个请求注入上下文。

## 兼容范围

| 客户端 | Profile | MCP 自动配置 | 原生后台文本采集 |
|---|---|---|---|
| Claude Code | `claude-code` | 支持 | 支持 |
| Claude Desktop | `claude-desktop` | 支持 | 显式导入 / MCP 写入 |
| Codex CLI / 桌面 / IDE | `codex` | 支持 | 支持本地 rollout 日志 |
| Gemini CLI | `gemini` | 支持 | 当前 JSONL 与旧 JSON |
| 当前 Kimi Code | `kimi` | 支持 | 尚未验证原生格式 |
| 旧 Python Kimi CLI | `kimi-legacy` | 支持 | active context.jsonl |
| Cursor | `cursor` | 支持 | 显式导入 / MCP 写入 |
| OpenCode v2 | `opencode` | 支持严格 JSON | 显式导入 / MCP 写入 |
| GitHub Copilot CLI | `copilot-cli` | 支持 | 显式导入 / MCP 写入 |
| Qwen Code | `qwen-code` | 支持 | 显式导入 / MCP 写入 |
| LM Studio | `lm-studio` | 支持 | 显式导入 / MCP 写入 |
| 其他 MCP 宿主 | `generic-json` | 导出配置片段 | 标准导入 / MCP 写入 |

DeepSeek 等模型通过支持 MCP 的宿主接入，例如 OpenCode。项目不修改模型 API 路由或密钥，没有假定每个模型服务商都有相同的本地配置。以上依据官方文档实现并经过夹具测试，不等同于在所有厂商应用里完成了真人登录和全部端到端验证。

## 后台与数据

MCP 进程由客户端按需启动；后台服务负责增量采集。**新配置默认不启用阅读器或 HTTP 监听**，AI 检索与采集均不依赖网页。Linux 使用 `systemd --user`，macOS 使用 LaunchAgent，Windows 使用当前用户的登录计划任务，无需保存密码。

```bash
memory-book service stop
memory-book service start
memory-book service uninstall
```

停用服务或移除采集来源不会删除已归档记忆。没有用户服务管理器时可运行 `memory-book daemon`，或按需运行 `memory-book sync --once`。Docker 镜像默认命令也是无 HTTP 端口的 stdio MCP，可由客户端通过 `docker run --rm -i` 启动；容器采集宿主会话需要另外显式挂载目录和配置来源。见[Docker 部署](docs/deployment.md#docker)。

工作区元数据可用时，按工作区路径隔离项目；Gemini/旧 Kimi 的部分格式只有目录桶标识，按子目录隔离。需要跨客户端合并友好项目名时，请明确选择项目日志目录并设置 `--project`。跨会话章节仍依赖 `task_id`。

默认数据库改为系统用户数据目录，所有客户端使用同一绝对路径。可通过 `MEMORY_BOOK_HOME`、`MEMORY_BOOK_DB` 或全局 `--db` 覆盖。**v0.1 的 `.memory-book/memory.db` 不会自动迁移**，见[升级说明](docs/deployment.md#upgrading-from-v010)。

## 验证与可选模式

当前推荐使用**默认 score-aware 词法召回**。精确 token 上限、多事实 coverage 和本地语义候选，按实际工作负载与上下文预算显式选择。

| 能力 | 当前验证 |
|---|---|
| 默认检索与写入 | 56,784 次真实成对调用、四轮交替顺序；完整载荷、来源、索引一致，另测首次写入、重复导入、启动及资源 |
| 可选索引引用 | 56,784 次真实 SDK 调用、7,098 个不同的完整载荷配对、全部 6,868 条归档引用；计入完整元数据成本并保留逐题损失 |
| 可选 Q2 语义候选 | 四组既有语料、四种同组模式，48,492 次开发测量；完整保留各预算、困难分组、模型/索引成本及逐题损失 |
| 原生预算与当前对比组件 | 256 题、10 个已完成阶段、32,256 次真实调用；3,072 个词法基线/当前版问题配置的上下文全部一致，原生/组件质量、耗时、token 和资源均有完整记录 |

[完整结果与复现材料](benchmarks/README.md) · [当前组件/原生预算方案](docs/round2-validation.md) · [语义设置与实测取舍](docs/semantic-retrieval.md) · [coverage 详情](benchmarks/RESULTS-conjunctive-recall.md) · [真实回答结果](benchmarks/RESULTS-local-answers.md) · [原生流程结果](benchmarks/RESULTS-full-workflow.md) · [代码验证](docs/validation.md)。

Q2 可以改善改写问题的召回，也可能挤出有用的词法证据，并增加本地模型与索引成本。当前原生 8,000 字符、**512 o200k token** 视图中，完整度为**词法 42.19% → Q2 41.02%**，全部小预算和逐题损失保留在完整报告中。升级融合规则时可复用兼容的现有语义索引，结果缓存单独更新版本；多事实 coverage 继续通过 `coverage=True` / `--coverage` 显式启用。

生成回答和捕获/总结流程诊断保留各自的固定源码、模型设置与实测失败，与当前原文交付、无损格式测量分别说明。公开题和重复使用的问题属于回归数据；给定 HotpotQA 段落不能证明私有会话迁移或所有领域泛化。完整报告保留全部预算、错误、负结果和历史比较。

原文与缓存保存在本地未加密文件中；工具返回的证据会进入客户端模型上下文。支持文本，不恢复图片、音频或完整结构化工具日志。

## 可选：检查记忆归档

需要人工检查或调试时，单独启动本地阅读器：

```bash
memory-book serve
```

随后在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。关闭它不会影响独立运行的采集和 MCP。界面可切换 **EN / 中文**，历史原文保持原语言。[使用虚构会话的界面截图](docs/assets/reader-desktop.png)。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
