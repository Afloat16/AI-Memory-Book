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

### 与对比仓库的实测优势

在相同 **1,024 `cl100k_base` token 上限**下，Book 的完整原文证据率高于三个已执行的原生检索组件：

| 固定版本的检索组件 | 证据召回 ↑ | 完整证据率 ↑ | 平均上下文 token ↓ |
|---|---:|---:|---:|
| **AI-Memory-Book，score-aware `0ab49d4`** | **69.54%** | **72.88%** | 827.2 |
| [claude-mem `2cfed76`](benchmarks/results/claude-mem-components-public.md)，原生 SQLite FTS | 66.24% | 70.11% | 804.8 |
| [billion-context `dc041dd`](benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries)，搜索内核 | 65.48% | 68.72% | 862.6 |
| [ai-memory v3.4.5](benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries)，本地混合检索 | 64.47% | 66.72% | **779.3** |

这一设置下，完整证据率相对 claude-mem FTS **高 2.77 个百分点**，相对 billion-context **高 4.16 个百分点**，相对 ai-memory **高 6.16 个百分点**。上下文 token 比 billion-context 少 4.1%；claude-mem 和 ai-memory 的上下文 token 比 Book 更少。

**质量比较的共同输入：**相同 1,339 个源页面、全部 1,015 道适用的 LoCoMo 纯文本问题、项目范围、top-5 和带引用的整页打包规则。完整证据率以 **649 道可回答题**为分母，证据召回以 **788 条必需原文**为分母，平均 token 以全部 1,015 题为分母。证据必须完整保留并匹配原始来源范围；366 道无支持答案的问题也保留在报告中。非空检索不等于回答正确或能够拒答。

claude-mem 实验直接执行固定上游版本的 `SessionStore` / `SessionSearch`，完成 **3,045 次成功原生调用**和六组 tokenizer/预算配置。它的 observer、Chroma、宿主注入、MCP 序列化及生成回答不在这个组件实验内。其他两个组件也保留各自的版本与边界。[完整比较与成本](docs/comparison.md) · [claude-mem 方法及报告](docs/claude-mem-component-evaluation.md)。

这些是**回归数据上的原文交付指标**，不能直接当作完整产品排名。当前原生 token API 与可选语义模式采用独立实验，见下方；其结果不会替换这张固定版本表。

### 同时比较质量、速度与部署成本

默认记忆路径**无需生成式写入、embedding 下载和独立数据库服务**，保留原文地址，并在一次 MCP 召回中交付有上限的证据。这些部署与使用特点也构成了项目的优势。

| 实际执行的操作 | p50 | p95 | 测量边界 |
|---|---:|---:|---|
| Book 进程内召回，历史固定运行 | 2.945 ms | 4.555 ms | 检索及原生上下文组装 |
| **Book 实际 MCP 召回**，同一历史运行 | **5.764 ms** | **9.181 ms** | 官方 SDK、子进程 stdio 和返回 JSON |
| billion-context 搜索及桥接，历史运行 | 1.298 ms | 2.413 ms | 搜索；不含原生解压 |
| ai-memory v3.4.5 本地混合检索，历史运行 | 29.720 ms | 37.315 ms | HTTP/MCP query；不含后续全文读取 |
| claude-mem 原生 FTS 及 Bun 桥接，2026-11-12 执行机 | 59.664 ms | 100.450 ms | 完整 observation 行 JSON；不含 MCP 和 observer |

billion-context 在其被测搜索边界更快；claude-mem 的执行机与历史三行不同。不同宿主与接口不直接推导整个产品快多少倍。

相对**本项目 v0.2.1，在相同真实 MCP 边界**下，固定 Book 版本的响应 token **减少 54.7%**（`o200k_base`：3,233.5 → 1,465.1），首次调用 p50 **降低 31.1%**（8.371 → 5.764 ms）。ai-memory 另行测量的“一次搜索并读取全部五个页面”策略，完整 payload 平均为 942.5 + 1,913.7 = **2,856.2 token**，content-only 为 **2,574.6 token**；Agent 选择少读页面时可以更低。[成本表](docs/comparison.md)分别标注两种统计范围，不再将旧的 43.1% 混合口径比较当作完整响应节省率。

完整指南还涵盖 **Mem0、Graphiti、PageIndex 和 Letta**，提供带日期的热度、官方来源与运行要求。未执行的流程不填虚构分数。ai-memory 的默认路径同样可以零 LLM 运行；claude-mem 也支持本地模型。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

### 选择版本

| 版本 | 可用能力 | 使用方式 |
|---|---|---|
| **已发布的实验版本 v0.2.1** | 以 Agent 为主的 MCP、共享本地记忆和可选无界面后台采集 | 使用下方固定版本安装器。 |
| **已推送的 v0.3 开发源码** | Score-aware 检索、紧凑的带出处证据、可选精确 token 预算、多事实 coverage、可选本地语义检索和配对回答评测工具 | 按[开发版源码安装](#开发版源码安装)检出 `main`。 |
| **固定对比版本 `0ab49d4`** | 上方检索质量和 MCP 成本数字对应的原始代码 | 按[复现指南](benchmarks/RESULTS-recall-score-quality.md#11-reproduction-and-artifact-index)准备和运行。 |

已验证的后续改进（包含精确 token 预算）已通过 [PR #1](https://github.com/Afloat16/AI-Memory-Book/pull/1) 合入 `main`，合并提交为 [`ce7837f`](https://github.com/Afloat16/AI-Memory-Book/commit/ce7837fb8db7c221f39e27a531f2383385782eb1)。下方安装器仍使用已发布的 **v0.2.1**，目前没有可下载的 `v0.3.0` 发布标签。体验新增能力请从 `main` 安装源码。

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

历史竞品表使用共同的**整页评测打包器**；新 API 组装**原生摘录和完整原文单元**，两者基线不同，新结果不会替换历史对比口径。见[预算实测与仍需解决的差距](#四项原有差距怎样处理)。

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

### 原生 token 预算完整矩阵

固定候选 `407cda1` 与基线 `5abc85e` 已完成 **8 组、2,019 个问题实例、24,228 个问题/配置配对**：五个合成种子、1,015 道公开题、36 道已编写诊断题，以及 128 道外部 HotpotQA。每组覆盖两个字符上限、两种 tokenizer、三个 token 上限和三次重复。

其中 **251 个问题/配置配对新增完整证据，完整问题零退步，原来已容纳的证据块零丢失**。这里的 251 不是互不重复的问题数。各组来源、范围、精确预算与重复一致性检查全部通过。

在 **8,000 字符、512 `cl100k_base` token** 下：

| 题组 | 基线完整证据率 | 原生 token API | 配对 p95，基线 → 候选 |
|---|---:|---:|---:|
| 公开 LoCoMo，649 可回答 / 1,015 总题数 | 65.33% | **66.41%** | 7.120 → 10.076 ms |
| 合成回归种子 883，152 可回答 / 168 总题数 | 68.42% | **84.21%** | 12.550 → 26.448 ms |
| 已编写诊断，30 可回答 / 36 总题数 | 86.67% | 86.67% | 1.644 → 1.721 ms |
| 外部 HotpotQA，128 题全部可回答 | 34.38% | **35.16%** | 7.873 → 9.188 ms |

公开集 512 `o200k_base` 从 **65.95% 提高到 66.72%**，新增完整问题 5 个、丢失 0 个；1,024/2,048 token 的公开完整证据率保持 72.88%。API 用剩余容量补入完整原文单元，也增加 CPU 开销。各题组宿主不同，耗时只在同组配对中比较。

[方案与复现](docs/native-budget-evaluation.md) · [公开原生报告](benchmarks/results/native-completion-regression-public1015.md) · [外部原生报告](benchmarks/results/native-completion-external-hotpot128.md)。

### 可选本地语义检索：实测收益与代价

语义候选需要**显式开启**；默认仍是词法检索。四个注册题组已完成真实本地 MiniLM 测量。在 512 `cl100k_base` token、8,000 字符条件下：

| 题组 | 词法完整证据率 | 语义完整证据率 |
|---|---:|---:|
| 合成开发种子 61 | **85.53%** | 63.16% |
| 已编写诊断，30 题可回答 | 86.67% | **100.00%** |
| 公开 LoCoMo，649 题可回答 | **66.41%** | 62.56% |
| 外部 HotpotQA，128 题可回答 | **35.16%** | 33.59% |

已编写诊断的低重叠子集从 **2/6 提高到 6/6**。公开低重叠问题的完整率从 **46.01% 提高到 47.55%**，跨会话完整率从 **10.53% 提高到 15.79%**；但公开 512-token 全体同时有 **39 个完整问题获益、64 个丢失**。1,024 token 下，外部 HotpotQA 从 **48.44% 提高到 50.00%**，公开集则从 **72.88% 降到 71.49%**。合成低重叠问题仍未解决。

固定模型和 tokenizer 下载共 **127,535,388 字节**。公开语义执行机上的加载为 1.271 秒、建索引为 116.554 秒；512-token 词法/语义查询 p50 为 **8.078 / 18.074 ms**，p95 为 **10.184 / 22.691 ms**。这些结果不支持将语义模式设为默认。

[设置、分类结果及模型/索引成本](docs/semantic-retrieval.md) · [公开语义报告](benchmarks/results/semantic-final-regression-public1015.md) · [外部语义报告](benchmarks/results/semantic-final-external-hotpot128.md)。

### 四项原有差距怎样处理

历史**整页打包**在 512 `cl100k_base` 下的 **66.72% → 66.26%** 退步继续保留。上方原生 API 使用不同交付策略和独立基线，零丢失约定不能抹去历史结果。部分合成尾部延迟仍明显增加。

低词汇重合语义、跨远距离会话的证据组合仍是弱项。语义实验展示了具体获益与损失，尚未建立通用语义记忆能力。没有支持答案的问题也可能返回非空证据；必须单独用生成实验检查模型回答，不能把检索数字直接当作回答准确率。

公开题及重复模板的合成题属于回归数据。本轮固定的外部 HotpotQA 引入 **128 道独立编写的多跳题、1,272 个给定段落和 306 条支持事实**，保留全部给定干扰段落。这是限定范围的外部诊断；全部问题均可回答，规模和领域也不足以证明普遍泛化。看过结果后，它也成为后续调参的回归数据。

### 可选：多事实证据覆盖

开发版新增 **`coverage=True` / `--coverage`**，默认关闭。它识别 `and`、`和`、`以及`、`并且` 等显式连接词，保留原来的首个结果，再从已限定范围的候选集中为其他分句保留结果。适合一个问题要求几项事实、而常规结果反复覆盖同一个主题的情况：

```bash
memory-book recall "cache expiry and retry window" --project atlas --coverage --budget 2000
```

MCP 调用 `recall_memory` 时加入 `"coverage": true`；Python 调用 `MemoryBook.recall` 时传入 `coverage=True`。该选项要求 book 策略，CLI 不可与 `--flat` 同时使用。

在[固定自动分句实验](benchmarks/RESULTS-conjunctive-recall.md)中，8,000 字符下每个合成回归种子的多段完整证据从 **0/16 提升到 8/16**。但公开完整证据率仍为 **72.88%**；相同整页打包政策下，512 `cl100k_base` token 的完整率从 **66.26% 降至 65.79%**，公开 MCP P95 从 **9.564 增至 13.510 ms**。新编写的 36 题跨领域诊断，两版完整率都是 **86.67%**。这些取舍决定了它需要显式开启；该启发式尚未证明语义改写能力提升。固定自动模式的耗时也不冒充最终可选开关版本的实测耗时。

[独立模式核验](benchmarks/reports/coverage-mode-equivalence.json)将最终默认与 coverage 模式分别对照各自的固定源代码，每组比较 **2,774 条完整返回载荷**，仅排除耗时字段，均为 **零差异**。原来的 512-token 缺口仍需继续改善。

### 真实回答与原生记忆流程

注册的本地模型作业正在独立执行：128 道 LoCoMo、128 道 HotpotQA，三种检索模式，**计划 768 次真实回答尝试**；另有 Book 对原生 ai-memory 的 42 会话/36 问题流程，计入捕获、显式开启的 consolidation、检索、后续读页与**计划 72 次回答尝试**。使用固定 Qwen2.5-0.5B 和经过身份校验的 llama.cpp 进程；HTTP 夹具不计作模型结果。

只有完整矩阵、请求账本、模型证明和成本经严格汇总器检查后，才发布回答质量结论。[续作记录](docs/continuation-status.md)列出独立运行任务及持久结果分支；[回答指南](docs/answer-evaluation.md)提供注册命令。

[历史 score-aware 报告](benchmarks/RESULTS-recall-score-quality.md) · [coverage 实验](benchmarks/RESULTS-conjunctive-recall.md) · [第一轮固定记录](benchmarks/RESULTS-recall-quality.md) · [完整比较与 token 口径纠正](docs/comparison.md) · [验证记录](docs/validation.md)。

原始文本和缓存保存在本地未加密文件中；工具返回的证据会进入客户端模型上下文。支持文本，不恢复图片、音频或完整结构化工具日志。

## 可选：检查记忆归档

需要人工检查或调试时，单独启动本地阅读器：

```bash
memory-book serve
```

随后在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。关闭它不会影响独立运行的采集和 MCP。界面可切换 **EN / 中文**，历史原文保持原语言。[使用虚构会话的界面截图](docs/assets/reader-desktop.png)。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
