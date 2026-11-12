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
| **创建与检索记忆不调用模型** | Python + SQLite 在本地索引和检索，核心不产生逐轮总结的模型费用，也无需下载 embedding 模型或部署独立数据库；回答模型由你的客户端选择。 |
| **保留原文，引用可核对** | 直接返回原始证据及项目、会话、轮次；需要时可展开精确字符区间和完整页，检查决定的依据。 |
| **一次 MCP 调用即可获得上下文** | `recall_memory` 直接组装预算内证据，可按项目、章节、会话限定范围，供 Agent 继续当前任务。 |
| **按需使用精确上下文上限** | 可选指定 tokenizer 的 token 上限，与字符上限同时生效，包含引用与分隔符；已能放入的原文块保持完整，剩余空间可补入原文语句。 |
| **多个客户端共用本地归档** | 支持的客户端连接同一数据库；选择开启后台采集后，受支持的文本会话会增量进入记忆。 |
| **部署轻，归档易检查** | 默认后台与 MCP 均不需要 HTTP 监听；可选阅读器、导出工具和保留原文的迁移机制便于检查和维护。 |

具体行为见 [Agent 使用指南](docs/agent-guide.md)、[部署与采集说明](docs/deployment.md)和[来源保留与迁移验证](benchmarks/RESULTS-recall-score-quality.md#8-source-preserving-schema-migration)。

### 最新验证的对比结果

在相同 **1,024 `cl100k_base` token 上限**下，Book 的完整原文证据率高于三个已执行的原生检索组件：

| 检索组件 | 证据召回 ↑ | 完整证据率 ↑ | 平均上下文 token ↓ |
|---|---:|---:|---:|
| **AI-Memory-Book，score-aware** | **69.54%** | **72.88%** | 827.2 |
| [claude-mem](docs/claude-mem-component-evaluation.md)，原生 SQLite FTS | 66.24% | 70.11% | 804.8 |
| [billion-context](docs/comparison.md)，搜索内核 | 65.48% | 68.72% | 862.6 |
| [ai-memory](docs/comparison.md)，本地混合检索 | 64.47% | 66.72% | **779.3** |

Book 的完整证据率相对 claude-mem FTS **高 2.77 个百分点**，相对 billion-context **高 4.16 个百分点**，相对 ai-memory **高 6.16 个百分点**。这一设置下，上下文 token 比 billion-context 少 4.1%；claude-mem 和 ai-memory 的上下文 token 比 Book 更少。

**测量范围：**全部 1,015 道适用的 LoCoMo 纯文本题、相同 1,339 个源页面、项目范围、top-5 和带引用的整页打包规则。完整证据率以 649 道可回答题为分母，证据召回以 788 条必需原文为分母，平均 token 以全部 1,015 题为分母。证据必须完整保留并匹配原始来源范围。这些指标衡量原文交付，生成回答和完整产品流程另行评测。

[完整比较](docs/comparison.md)保留确切版本、六组 tokenizer/预算、MRR 和无答案问题行为。最新补齐的 claude-mem 实测直接执行未修改的上游 `SessionStore` / `SessionSearch`，完成 **3,045 次成功原生调用**；observer、Chroma、宿主注入和生成回答不在该组件实验内。原生 token API 使用独立打包策略，另有对应报告。

### 速度、响应大小与运行成本

| 实际执行的操作 | p50 | p95 | 平均返回 `o200k_base` token | 边界 |
|---|---:|---:|---:|---|
| Book 进程内召回 | 2.945 ms | 4.555 ms | — | 检索及原生上下文组装 |
| **Book 实际 MCP 召回** | **5.764 ms** | **9.181 ms** | **1,465.1** | 官方 SDK、子进程 stdio、JSON 与证据 |
| billion-context 搜索及桥接 | 1.298 ms | 2.413 ms | 569.2 | 搜索预览；不含解压 |
| ai-memory 本地混合检索 | 29.720 ms | 37.315 ms | 942.5 | HTTP/MCP 搜索；不含后续读页 |
| claude-mem 原生 FTS 及 Bun 桥接 | 59.664 ms | 100.450 ms | 1,691.3 | 完整 observation 行 JSON；不含 MCP/observer |

上述原生返回大小与上方有预算的公共上下文分别计量。billion-context 在其被测搜索边界更快；宿主、接口及省略阶段不同，不能据此换算完整产品快多少倍。另行测量的 ai-memory“读取全部五个结果”策略增加 1,913.7 payload token，合计 2,856.2；Agent 少读页面时可以更低。

Book 的**默认记忆写入和检索为零模型调用**：本地 Python 与 SQLite，无强制 embedding 下载、生成式总结或独立数据库服务；回答模型由使用者选择。可选精确 token 预算包含引用和分隔符，原始来源地址可随时核对。

[完整成本指标](docs/comparison.md#returned-tokens-follow-up-reads-preparation-and-storage)还列出写入/建索引、模型准备、原生响应、存储和已测 RSS，逐项说明范围。[项目比较](docs/comparison.md#popular-projects-and-the-workload-they-address)进一步覆盖 **Mem0、Graphiti、PageIndex 和 Letta**，提供官方来源及带日期的热度记录。ai-memory 默认路径同样可以零 LLM 运行；claude-mem 也支持本地模型。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

### 选择版本

| 版本 | 可用能力 | 使用方式 |
|---|---|---|
| **已发布的实验版本 v0.2.1** | 以 Agent 为主的 MCP、共享本地记忆和可选无界面后台采集 | 使用下方固定版本安装器。 |
| **已推送的 v0.3 开发源码** | Score-aware 检索、紧凑的带出处证据、可选精确 token 预算、多事实 coverage、可选本地语义检索和配对回答评测工具 | 按[开发版源码安装](#开发版源码安装)检出 `main`。 |

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

Windows 使用 `.venv\Scripts\Activate.ps1`，也可直接运行 `.venv\Scripts\python.exe`。复现上方固定结果时，在安装前执行 `git checkout 0ab49d4f2be6aabe5e51c3314bb9369041af5369`，再按[评测准备与运行说明](benchmarks/RESULTS-recall-score-quality.md#11-reproduction-and-artifact-index)准备数据。只需核心时可安装 `pip install -e .`。项目尚未发布到 PyPI，不使用无版本来源的 `pip install ai-memory-book`。

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

最新 token 组装优化在开发集的**四个 512-token 配置中均降低 p95，幅度为 7.73%–14.45%**；与固定参考实现比较，**2,016 组完整返回载荷全部一致**（仅排除耗时）。[完整 12 配置性能报告](docs/token-prefix-performance.md)保留源码身份、复现方式及大预算下的取舍。

当前推荐使用**默认 score-aware 词法召回**。精确 token 上限、多事实 coverage 和本地语义候选，按实际工作负载与上下文预算显式选择。

原生 token 预算已覆盖 **8 组、2,019 个问题实例、24,228 个问题/配置配对**，记录 **251 个完整证据获益、完整问题零损失、原先已容纳的证据块零丢失**。这些是配置级计数；来源、精确预算、上下文大小和重复一致性检查通过。更充分利用小预算会增加计算，各报告保留同组配对耗时。

| 能力 | 当前验证 |
|---|---|
| 精确 token 预算 | 两种 tokenizer、三个 token 上限、两个字符上限，保留来源的组装及完整配对结果 |
| 可选语义候选 | 四组真实本地模型实验；质量/成本取决于任务，默认继续使用词法模式 |
| 可选多事实 coverage | 显式 `coverage=True` / `--coverage`，默认/可选模式等价核验及分类结果已公开 |
| 原生对比组件 | 实际执行固定版本的 claude-mem FTS、ai-memory 混合检索及 billion-context 搜索 |
| 真实生成回答 | 两组固定题目，768 次已完成调用；模型身份、usage 与逐题评分均已验证 |
| 原生完整流程诊断 | 42 个捕获会话、42 次整合尝试及 72 次回答；原生失败及成本全部保留 |

[完整结果与复现材料](benchmarks/README.md) · [原生预算方案](docs/native-budget-evaluation.md) · [语义设置与实测取舍](docs/semantic-retrieval.md) · [coverage 详情](benchmarks/RESULTS-conjunctive-recall.md) · [真实回答结果](benchmarks/RESULTS-local-answers.md) · [原生流程结果](benchmarks/RESULTS-full-workflow.md) · [完成审计](docs/continuation-status.md) · [代码验证](docs/validation.md)。

上方对比使用固定的共同页面打包规则；原生 API、语义排名、生成回答和捕获/总结流程分别测量。公开题与重复模板属于回归数据，外部独立编写的 HotpotQA 诊断提供限定范围的补充。完整评测文档保留限制、无答案题、错误、负结果与历史对比。

原文与缓存保存在本地未加密文件中；工具返回的证据会进入客户端模型上下文。支持文本，不恢复图片、音频或完整结构化工具日志。

## 可选：检查记忆归档

需要人工检查或调试时，单独启动本地阅读器：

```bash
memory-book serve
```

随后在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。关闭它不会影响独立运行的采集和 MCP。界面可切换 **EN / 中文**，历史原文保持原语言。[使用虚构会话的界面截图](docs/assets/reader-desktop.png)。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
