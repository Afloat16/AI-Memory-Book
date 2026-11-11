# AI-Memory-Book

**给 AI Agent 使用的后台记忆。项目成书，任务成章，AI 按需取回有出处的原文，然后继续完成任务。**

[English — 主 README](README.md) · [Agent 使用指南](docs/agent-guide.md) · [部署与后台运行](docs/deployment.md) · [客户端兼容表](docs/integrations.md) · [新版实测](benchmarks/RESULTS-recall-score-quality.md)

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
| **多个客户端共用本地归档** | 支持的客户端连接同一数据库；选择开启后台采集后，受支持的文本会话会增量进入记忆。 |
| **部署轻，归档易检查** | 默认后台与 MCP 均不需要 HTTP 监听；可选阅读器、导出工具和保留原文的迁移机制便于检查和维护。 |

具体行为见 [Agent 使用指南](docs/agent-guide.md)、[部署与采集说明](docs/deployment.md)和[来源保留与迁移验证](benchmarks/RESULTS-recall-score-quality.md#8-source-preserving-schema-migration)。

### 与对比仓库的实测优势

固定开发版本 [`0ab49d4`](https://github.com/Afloat16/AI-Memory-Book/commit/0ab49d4f2be6aabe5e51c3314bb9369041af5369) 在相同 **1,024 `cl100k_base` token 上限**下，完整证据率高于两个已测原生检索组件：

| 原生检索组件 | 证据召回 ↑ | 完整证据率 ↑ | 公共上下文平均 token ↓ |
|---|---:|---:|---:|
| **AI-Memory-Book** | **69.54%** | **72.88%** | 827.2 |
| [billion-context](https://github.com/ranxianglei/billion-context/tree/dc041dd1ab1a014efa352ba47a6f31fc47f55284) 搜索内核 | 65.48% | 68.72% | 862.6 |
| [ai-memory](https://github.com/akitaonrails/ai-memory/tree/ee73c04c542fa41ca629b046deb4ac108518f407) v3.4.5 本地混合检索 | 64.47% | 66.72% | **779.3** |

对应的完整证据率分别领先 **4.16 个百分点**和 **6.16 个百分点**；这一设置下，平均上下文 token 还比 billion-context 少 **4.1%**。扩展到两种 tokenizer、512 / 1,024 / 2,048 三个上限后，两个证据指标在 **12/12 组对比中领先**，平均上下文 token 在 **6/12 组更少**。

**指标含义与范围：**全部 1,015 个适用的 LoCoMo 纯文本问题，其中 649 个可回答；输入页面、项目范围、top-5 及带引用的整页打包规则一致。证据召回要求必要的原文语句完整保留，完整证据率要求可回答问题的全部必要原文都已返回。这是回归数据上的原文证据检索比较；各组件原生索引与传输边界仍有差别，尚未测量生成回答准确率或完整记忆流程。billion-context 的被测搜索边界更快；ai-memory 在 1,024/2,048 token 设置下使用更少公共上下文。[完整曲线、版本固定、原生成本与逐题结果](benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries)。

同一固定版本在公开集上，相对本项目原主线 v0.2.1 的**实际 MCP 响应 token 减少 54.7%**（`o200k_base`：3,233.5 → 1,465.1），首次调用耗时中位数 **8.371 → 5.764 ms**。这是相同真实 stdio 边界下的版本比较，详见下方[实测与限制](#实测与限制)。

开发分支继续默认使用 score-aware 检索，同时新增供多事实问题显式开启的[实验性 coverage 选项](#可选多事实证据覆盖)，其效果和取舍单独记录。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

以下命令安装**已发布的实验版本 v0.2.1**。上方实测改进属于**尚未发布的 v0.3 开发分支**，需要使用后面的[开发版源码安装](#开发版源码安装)。目前没有可下载的 `v0.3.0` 发布标签。

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

开发分支会继续更新，可能已包含固定评测提交之后的新改动：

```bash
git clone --branch perf/recall-quality-budget https://github.com/Afloat16/AI-Memory-Book.git
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

## 实测与限制

**第二轮固定版本进一步提升了公开样本的证据召回。** 该轮测得：相对原主线 v0.2.1，实际 MCP 响应 token 减少 **54.7%**、首次调用中位耗时减少 **31.1%**；相对已经优化过的 v0.3 分支，token 增加 **0.38%**，中位耗时减少 **15.5%**。这两个基线不能混用；这些数字属于 `0ab49d4`，后续开发提交需要各自验证。

上述第二轮 score-aware 比较的固定运行时代码为 [`0ab49d4`](https://github.com/Afloat16/AI-Memory-Book/commit/0ab49d4f2be6aabe5e51c3314bb9369041af5369)。公开测试覆盖八个留出会话中全部 **1,015 个适用的纯文本问题**，其中 649 个可回答。它包含此前的 256 题和相同会话中的其余 759 题，这全部问题已在第一轮测过，因此第二轮中均属于回归数据，不能称为全新的独立留出集。

| 公开集实测项 | 原主线 v0.2.1 | 保留的 v0.3 | 第二轮 score-aware |
|---|---:|---:|---:|
| 2,000 字符预算的证据召回 | 23.10% | 39.97% | **47.59%** |
| 8,000 字符预算的证据召回 | 66.37% | 66.24% | **69.54%** |
| 8,000 字符预算的完整证据率 | 70.42% | 70.11% | **72.88%** |
| 实际 MCP 返回平均 token，8,000 字符预算 | 3,233.5 | **1,459.6** | 1,465.1 |
| MCP 首次调用耗时中位数 | 8.371 ms | 6.823 ms | **5.764 ms** |
| MCP 首次调用耗时 P95 | 13.610 ms | 10.722 ms | **9.181 ms** |

数据来自独立公开、由 persona agents 生成的 LoCoMo，不是用户私人会话。证据召回要求完整标注语句和正确来源区间，**不等于大模型回答准确率**。Token 按 `o200k_base` 统计实际返回的 JSON 文本与元数据，不是厂商账单。真实 SDK stdio 测量重复三次，每次首次调用前确保没有结果缓存；不清除操作系统和 SQLite 缓存。启动和立即重复调用另行报告。全部 1,015 个问题 ID 均保留，包括五组重复查询；公开集和 42 题合成 MCP 样本均验证了紧凑/详细模式的证据完全一致。

外部对照实际运行了固定版本的 billion-context 搜索内核和 ai-memory v3.4.5 原生 MiniLM 混合检索，控制相同页面、作用域、top-5 和 512 / 1,024 / 2,048 token 打包上限。公共上下文与原生搜索、后续读页的 token 分开统计；不同组件和传输边界的计时不能直接证明完整产品更快。**claude-mem 和生成答案质量仍未实测。**

[首页对比表](#与对比仓库的实测优势)列出了 1,024-token 的结果。Token 优势随预算变化：两种 tokenizer 下，相对 billion-context，在 1,024/2,048 上限时更少、512 时更多；相对 ai-memory，在 512 时更少、1,024/2,048 时更多。公共上下文不包含原生协议元数据，上方实际 MCP 数字包含元数据。

另外，在固定的 **ai-memory 一次搜索 + 读取全部已映射 top-5 页面**策略下，实际返回内容平均为 2,574.6 `o200k_base` token；Book 一次 MCP 召回平均 1,465.1，**按这两个策略计算少 43.1%**。若 Agent 仅使用已足够的预览，或少读几页，ai-memory 的成本可以更低。billion-context 原生预览平均 569.2 token，尚未包含未测的解压成本。上述数字保留各自的读取策略，不能代表其他产品的最低成本或最终答案质量。

新规则保留精确 BM25 匹配的分数差距，再给予词形路由有限加分。它先通过开发集门槛，再验证两个新预留种子 883/1297：8,000 字符预算的完整证据率从第一轮的 **81.58% 提升至 84.21%**，精确查找恢复到 24/24；已观察过的 211/509 回归集也恢复了这部分命中。

### 继续优化的四项差距

固定评测保留了下面的失败和待验证范围，后续工作将据此逐项检查：

| 差距 | 已记录结果与下一步验证 |
|---|---|
| 低词面重叠与远距离证据组合 | 每个验证种子的 8 个低重叠问题召回均为零；多段查询的部分覆盖从 34.375% 降至 25%，没有完整找齐的问题。新检索路线需要按类别和逐题检查。 |
| 极小预算 | 相对第一轮 Book，512 token 下完整证据率在 `cl100k_base` 中从 66.72% 降至 **66.26%**，在 `o200k_base` 中从 67.03% 降至 **66.72%**。预算优化需同时列出获益与退步。 |
| 最终回答与全流程成本 | 尚未测量固定生成模型，也缺少完整原生捕获/总结轨迹；需要统一回答评分，并计入写入、总结、检索、后续读页和生成回答。 |
| 泛化 | 1,015 个公开问题已是回归数据，新预留合成种子仍共享模板；还需独立语料及独立编写的问题类型。 |

公开集核心检索和合成 MCP P95 相对保留 v0.3 的退步也仍然保留。全部公开不可回答问题会返回非空上下文，这不等于模型的拒答或幻觉率。当前状态排序仍是保守启发式。[分类结果、逐题损失与全流程前提](benchmarks/RESULTS-recall-score-quality.md#7-remaining-failures-and-interpretation-limits)。

核心仍是本地 SQLite 词法检索，无需模型、向量库或 API key。生产参数 `budget_chars` 限制的是带引用的上下文字符数，不包含外层 JSON；评测中的精确 token 打包器不是生产功能。

### 可选：多事实证据覆盖

开发版新增 **`coverage=True` / `--coverage`**，默认关闭。它识别 `and`、`和`、`以及`、`并且` 等显式连接词，保留原来的首个结果，再从已限定范围的候选集中为其他分句保留结果。适合一个问题要求几项事实、而常规结果反复覆盖同一个主题的情况：

```bash
memory-book recall "cache expiry and retry window" --project atlas --coverage --budget 2000
```

MCP 调用 `recall_memory` 时加入 `"coverage": true`；Python 调用 `MemoryBook.recall` 时传入 `coverage=True`。该选项要求 book 策略，CLI 不可与 `--flat` 同时使用。

在[固定自动分句实验](benchmarks/RESULTS-conjunctive-recall.md)中，8,000 字符下每个合成回归种子的多段完整证据从 **0/16 提升到 8/16**。但公开完整证据率仍为 **72.88%**；相同整页打包政策下，512 `cl100k_base` token 的完整率从 **66.26% 降至 65.79%**，公开 MCP P95 从 **9.564 增至 13.510 ms**。新编写的 36 题跨领域诊断，两版完整率都是 **86.67%**。这些取舍决定了它需要显式开启；该启发式尚未证明语义改写能力提升。固定自动模式的耗时也不冒充最终可选开关版本的实测耗时。

[独立模式核验](benchmarks/reports/coverage-mode-equivalence.json)将最终默认与 coverage 模式分别对照各自的固定源代码，每组比较 **2,774 条完整返回载荷**，仅排除耗时字段，均为 **零差异**。原来的 512-token 缺口仍需继续改善。

### 真实回答评测已可执行

新增[配对回答评测指南](docs/answer-evaluation.md)，提供面向明确配置的真实生成端点的 `prepare` / `run` 命令。它固定两版实际返回的证据，让答案标签留在评测侧，并分别记录服务商 usage、失败调用、未知成本、模型身份和实验文件哈希。最终回答质量仍需接入真实生成模型实测；完整成本比较还需要各对照项目的真实观察与压缩轨迹。HTTP 夹具只验证传输行为，不充当模型效果结果。

现已[核验 128 道公开开发题的配对输入准备](benchmarks/reports/answer-eval-readiness.json)，对照第一轮与最终默认版本：**83 道可回答、45 道无支持证据，实际模型调用为零**。回答质量与服务商成本仍未测量。

[本轮 coverage 实验与复现材料](benchmarks/RESULTS-conjunctive-recall.md) · [默认 score-aware 版本报告](benchmarks/RESULTS-recall-score-quality.md) · [第一轮完整记录](benchmarks/RESULTS-recall-quality.md) · [历史 v0.3.0 报告](benchmarks/RESULTS-v0.3.0.md) · [外部对照协议](docs/comparison-protocol.md)

最终本地完整套件通过 **266 项测试**，无失败、无跳过。[当前 PR 检查](https://github.com/Afloat16/AI-Memory-Book/pull/1/checks)跟踪已发布分支最新提交的验证结果。[此前 CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044450305) 的 **9 项作业全部通过**，含 **13 项真实浏览器检查**，以及 Python 3.10/3.12/3.13、实际 MCP、跨平台安装器和容器验证；这些仍属于历史验证。[验证记录](docs/validation.md) 说明实际覆盖范围。

原始文本和缓存保存在本地未加密文件中；模型调用工具时返回的证据会进入客户端模型上下文。项目不绕过工具授权。支持文本，不恢复图片、音频或完整结构化工具日志。

## 可选：检查记忆归档

需要人工检查或调试时，单独启动本地阅读器：

```bash
memory-book serve
```

随后在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。关闭它不会影响独立运行的采集和 MCP。界面可切换 **EN / 中文**，历史原文保持原语言。[使用虚构会话的界面截图](docs/assets/reader-desktop.png)。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
