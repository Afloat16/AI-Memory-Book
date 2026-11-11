# 导入与客户端接入

## 支持的输入

| 格式 | 命令参数 | 行为 |
|---|---|---|
| Canonical JSON | `--format canonical` | 一条会话、数组、或 `sessions` 容器 |
| ChatGPT 导出 | `--format chatgpt` | 沿 `current_node` 祖先链选当前分支，不混入弃用分支 |
| Claude Code JSONL | `--format claude-code` | 按 `sessionId` 分组，读取 `message` 的已知文本块 |
| Codex rollout JSONL | `--format codex` | 读取 `session_meta` 与 `response_item` message；忽略重复 `event_msg` |
| 自动检测 | `--format auto` | 根据已识别的结构选择上述适配器，不把任意 JSON 当成功导入 |

本版本以合成格式夹具和实际本地接口测试验证适配器，没有在用户私人导出上测试。厂商日志格式可能变化；遇到不支持的结构请提供脱敏最小复现，不要提交整个私人会话。

输入文件必须是 UTF-8，可带 BOM，CLI 单文件上限为 64 MiB，核心单会话正文上限为 800 万字符。网页只接收一个 canonical JSON 对象，单次请求上限为 8 MiB。图片、音频和结构化工具调用/结果不重建；标准记录中已经转成文字的 `tool` 消息可以保留。

只有输入里带项目或调用时显式给出 `--project`，才会导入。项目 ID 是逻辑 namespace，不会被当作文件路径读取。指定 `--project`/`--task` 会覆盖输入中的对应归属。原生格式没有稳定 ID 时，使用文件名加内容哈希标记快照；这类文件修改后是新快照，若要增量替换应提供稳定的 canonical `session_id`。

```bash
memory-book --db /data/memory.db import ./export.json --project atlas
memory-book --db /data/memory.db import ./session.jsonl \
  --format claude-code --project atlas --task cache-design
```

每条会话的写入是原子的，重复执行可跳过未变化内容。多文件导入不是跨文件总事务；中途失败时前面成功的会话仍保留，修复后重试即可。

## Canonical 字段

| 字段 | 必需 | 含义 |
|---|---|---|
| `project` | 是 | 项目 ID，建议稳定 |
| `session_id` | 核心 API 必需 | 项目内稳定会话 ID |
| `messages` | 是 | 文本消息数组，角色为 user/assistant/system/developer/tool |
| `title` | 否 | 会话显示标题 |
| `project_name` | 否 | 项目友好名称 |
| `task_id` | 否 | 跨会话任务 ID |
| `task_title` | 否 | 任务章节显示标题 |
| `created_at` | 否 | ISO 8601 源会话时间，统一规范到 UTC |

源 JSON 保存规范化文本，不是原厂商文件的无损二进制备份；厂商自定义字段不会全部保留。源消息里的代码和命令仅作为历史内容，不会自动执行。

## MCP 配置

先在项目虚拟环境安装可选依赖：

```bash
python -m pip install -e ".[mcp]"
```

本版本使用并测试了官方 Python SDK 1.29.0，依赖范围固定为 `mcp>=1.28,<2`。官方 SDK v2 的命名和协议接口有变化，因此不使用不受约束的最新依赖。参见[官方 v1 维护线文档](https://py.sdk.modelcontextprotocol.io/v1/)。

支持 `mcpServers` JSON 配置的宿主可以填写：

```json
{
  "mcpServers": {
    "memory-book": {
      "command": "/absolute/path/AI-Memory-Book/.venv/bin/memory-book",
      "args": ["--db", "/absolute/path/memory.db", "mcp"]
    }
  }
}
```

请替换为实际绝对路径。Windows 可使用虚拟环境 `Scripts/memory-book.exe`。不同客户端的配置文件位置不同；这里提供服务启动配置，不修改宿主全局设置。

### 工具

| 工具 | 作用 |
|---|---|
| `recall_memory` | 默认一次查找并返回有出处的上下文 |
| `browse_projects` | 列出项目书架 |
| `browse_book` | 分页列出项目任务章节 |
| `browse_chapter` | 分页列出会话小节，每节预览有限页数 |
| `browse_section` | 继续浏览一个长小节的页目录 |
| `read_page` | 读取确切页，可按字符分页 |
| `remember_session` | 仅 `--allow-write` 启用，新增或原子替换规范化会话 |

检索例子：

```json
{
  "query": "搜索缓存为什么改为45秒？",
  "project": "atlas",
  "budget_chars": 2000,
  "limit": 5
}
```

若 `context` 不足，宿主可以读取返回的 page ID。无需先调用全部 browse 工具。`turn_index` 从 0 开始；界面显示为第几问时加 1。

### 自动记忆的边界

启动 MCP 服务不会自动得到客户端的全部历史。可使用明确的文件导入步骤，或者在你配置的会话结束流程中让客户端调用 `remember_session`。不要让模型在每次新问题之前重新读取整段历史。

如果接入外部 hooks，建议把“记录/索引更新”放在写入侧，检索时只查已生成索引。首版未发布厂商专用自动 hooks 或后台文件监视器，也不会扫描未指定的项目目录。

## 验证接入

```bash
memory-book --db /absolute/path/memory.db stats
memory-book --db /absolute/path/memory.db recall "你导入过的关键词" --json
python -m unittest tests.test_mcp -v
```

协议测试通过官方 `ClientSession` 和真实 stdio 子进程执行初始化、工具列表、只读召回与显式写入。服务不往 stdout 打印非协议日志。MCP 的上下文预算不包含外层 JSON 的所有来源元数据，请使用 `context_chars` 和实际宿主计量分别观察成本。
