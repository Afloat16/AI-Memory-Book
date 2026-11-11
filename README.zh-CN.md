# AI-Memory-Book

**给 AI Agent 使用的后台记忆。项目成书，任务成章，AI 按需取回有出处的原文，然后继续完成任务。**

[English — 主 README](README.md) · [Agent 使用指南](docs/agent-guide.md) · [部署与后台运行](docs/deployment.md) · [客户端兼容表](docs/integrations.md) · [完整实验](benchmarks/EXPERIMENTS.md)

AI-Memory-Book 的主要使用者是 AI。接入客户端并选择开启采集后，后台把受支持的会话整理成可检索记忆。当任务依赖之前的决定、约束或未完成步骤时，AI 可以通过 MCP 直接取回预算内的原文和出处，接着处理当前任务。它不需要每次先读目录，也不需要加载完整历史会话。

当前版本 **v0.2.1**，MIT 开源、实验版本。主入口是供 Agent 调用的 **MCP 工具**；后台默认无界面运行，不启动 HTTP 阅读器。网页只作为可选的检查与调试工具。核心检索不需要 API key、模型调用或向量数据库。

服务向 AI 提供按需读取策略，但是否调用工具仍由宿主和模型决定。项目不承诺每个客户端都会自动调用，也不要求每次提问都读取记忆。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

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

返回的 `context` 包含预算内证据，结果还提供页 ID、`project`、`session_id`、`turn_index` 和字符区间。在[示例归档](examples/conversations.json)中，缓存复核记录把有效期从 300 秒改为 45 秒，并保留 revision 失效机制。AI 可以引用 `atlas / atlas-cache-review / turn 0`，核对来源时间，再据此继续实现。历史证据可能已经过时或互相冲突，不能直接当成当前指令。

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

**v0.1.0 历史检索实验**公开了六种组合的开发及留出结果。两组留出集各有 112 会话、1,408 次提问、约 114 万原文字符。在 8,000 字符预算下，自适应分节证据召回为 77.27%，完整证据率 78.95%，本地关闭结果缓存的检索 P95 为 7.42–7.46 ms；平均上下文比整会话少约 31.5%。v0.2.0 增加部署和采集，v0.2.1 明确 AI 工作流和后台默认行为；这些改动没有将旧测量冒充新版本实测。

数据为合成语料，计时保留 SQLite/操作系统页缓存，不包括进程启动、客户端、采集、模型、网络或 MCP 传输。低词面重叠改写、远距离双证据和新旧决定仍有明显不足；目录重排未证明独立总体收益。所有失败保留在[实验记录](benchmarks/EXPERIMENTS.md)。预算以包含引用标题的字符数计，不是整个传输 JSON 或精确模型 token 上限。

**v0.2.0 采集样本**使用 300 个合成文件，八次未变更扫描的中位时间为 36.95 ms，均无重复导入；改动一个文件后更新一个会话、跳过 299 个文件。扫描仍写入状态和心跳。这是小规模热缓存样本，不能推出零 CPU、零磁盘开销或实际大档案性能。[方法与原始结果](docs/validation.md#v020-capture-overhead-sample)。

**v0.2.0 候选版本**通过了[九项 CI 作业](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672)，包括安装可选依赖后的 158 项测试，以及实际 MCP、浏览器、三平台安装器和 Docker 验证。这些数量属于该候选版本；v0.2.1 的后续验证单独记录在[发布验证](docs/validation.md)，不等于每个厂商应用和登录环境均已实测。

原始文本和缓存保存在本地未加密文件中；模型调用工具时返回的证据会进入客户端模型上下文。项目不绕过工具授权。支持文本，不恢复图片、音频或完整结构化工具日志。

## 可选：检查记忆归档

需要人工检查或调试时，单独启动本地阅读器：

```bash
memory-book serve
```

随后在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。关闭它不会影响独立运行的采集和 MCP。界面可切换 **EN / 中文**，历史原文保持原语言。[使用虚构会话的界面截图](docs/assets/reader-desktop.png)。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
