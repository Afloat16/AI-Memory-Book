# AI-Memory-Book

**让多个 AI 客户端共用一本本地记忆书。项目成书，任务成章，一次检索直接找到有出处的原文页。**

[English — 主 README](README.md) · [部署与后台运行](docs/deployment.md) · [客户端兼容表](docs/integrations.md) · [完整实验](benchmarks/EXPERIMENTS.md)

当前版本 **v0.2.0**，MIT 开源、实验版本。新增隔离安装器、一条命令配置客户端、可选后台增量采集、Linux/macOS/Windows 用户级服务及 Docker 部署。核心检索不需要 API key、模型调用或向量数据库。

## 安装

需要 Python 3.10+，并且 Python 的 SQLite 包含 FTS5。

macOS / Linux：

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.0/scripts/install.sh
bash install-memory-book.sh
```

Windows PowerShell：

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

安装器建立独立环境，默认安装 MCP 和客户端配置依赖，并打印可执行文件的绝对路径。如果 `memory-book` 尚未加入 PATH，使用显示的路径。不会修改 shell 配置或执行策略。

## 一条命令接入

```bash
# 只接入 MCP
memory-book setup --client claude-code

# 同时接入 Claude Code / Codex，并启用后台采集和登录启动
memory-book setup --client claude-code --client codex --capture --background

memory-book doctor
memory-book service status
```

配置后重启客户端或刷新 MCP 列表。客户端自己的信任、工具授权提示仍然生效。可以问：“使用 memory-book 查一下我们之前为什么选择这个缓存方案，并给出出处。”

`--capture` 开启对显示路径内现有和后续文本会话的读取；不带该参数时只配置 MCP。使用 `--dry-run` 预览；`--all` 配置检测到的客户端，并明确报告哪些只有 MCP 能力。

仅采集一个工作区：

```bash
memory-book setup --client codex --capture --workspace /absolute/path/to/project \
  --project my-project --background
```

原设置会保留，变更前备份，重复执行不重复添加。JSONC 或无效配置不会自动重写，会提供手动合并片段。运行中的后台进程会重新加载配置，收窄范围或移除来源无需等待下次登录。

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

MCP 进程由客户端按需启动；后台服务负责增量采集和阅读器。Linux 使用 `systemd --user`，macOS 使用 LaunchAgent，Windows 使用当前用户的登录计划任务，无需保存密码。

```bash
memory-book service stop
memory-book service start
memory-book service uninstall
```

停用服务不会删除记忆。没有用户服务管理器时可运行 `memory-book daemon`，或按需运行 `memory-book sync --once`。阅读器位于 [http://127.0.0.1:8765](http://127.0.0.1:8765)。Docker 阅读器通过 `docker compose up -d --build reader` 启动，容器不会自动获得宿主历史。

工作区元数据可用时，按工作区路径隔离项目；Gemini/旧 Kimi 的部分格式只有目录桶标识，按子目录隔离。需要跨客户端合并友好项目名时，请明确选择项目日志目录并设置 `--project`。跨会话章节仍依赖 `task_id`。

默认数据库改为系统用户数据目录，所有客户端使用同一绝对路径。可通过 `MEMORY_BOOK_HOME`、`MEMORY_BOOK_DB` 或全局 `--db` 覆盖。**v0.1 的 `.memory-book/memory.db` 不会自动迁移**，见[升级说明](docs/deployment.md#upgrading-from-v010)。

## 实测与限制

v0.1.0 公开了六种检索组合的开发及留出实验。两组留出集各有 112 会话、1,408 次提问、约 114 万原文字符。在 8,000 字符预算下，自适应分节证据召回为 77.27%，完整证据率 78.95%，本地未缓存检索 P95 为 7.42–7.46 ms；平均上下文比整会话少约 31.5%。v0.2.0 增加部署和采集功能，没有将旧测量冒充新版本实测。

数据为合成语料，时延不包括客户端、采集、模型、网络或 MCP 传输。低词面重叠改写、远距离双证据和新旧决定仍有明显不足；目录重排未证明独立总体收益。所有失败保留在[实验记录](benchmarks/EXPERIMENTS.md)。

采集数据留在本机，但模型调用工具时返回的证据会进入客户端模型上下文。项目不强制注入历史，不绕过工具授权。支持文本，不恢复图片、音频或完整结构化工具日志。

[完整英文说明](README.md) · [发布验证](docs/validation.md) · [MIT License](LICENSE)
