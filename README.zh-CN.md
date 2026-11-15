# AI-Memory-Book

**让长期工程中的决定，跨项目、跨会话、跨 AI 客户端保留下来。**

AI-Memory-Book 为编程 AI 提供共享的本地工作记忆。项目是书，任务是章；一次限定项目范围的 MCP 查询，返回带出处的原始证据，让 AI 找回决定、核对后续修正，再继续任务。

[English](README.md) · [快速开始](#快速开始) · [默认配置](#默认配置) · [实测结果](#实测结果) · [v0.4.0 发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.4.0)

**v0.4.0 · 带原始证据的工程记忆 · MIT · Python 3.10+ · 本地 SQLite**

## 它能为工程工作补充什么

- **找回之前为什么这样做。** 决策、约束、失败尝试和原始会话都能按项目、会话、轮次和页面定位。
- **找出长会话中的后续修正。** 明确询问 current/latest/当前时，结合来源轮次寻找后续修正，并在同项目、同任务内优先不同原文，减少重复记录挤占上下文。
- **限定相似项目的检索范围。** 使用已知项目 ID 找回该项目的历史；多个受支持的客户端可以共用一份归档。
- **轻量运行。** 默认写入与词法检索不调用模型，无需下载嵌入模型、启动数据库服务器或配置记忆服务 API Key。

采集与检索独立：主动开启后台采集后，受支持的会话会持续更新；AI 在需要历史时直接检索，证据不足再读取具体原文页面。[AI 工作流程与来源语义](docs/agent-guide.md)。

## 快速开始

准备 **Python 3.10+，且 SQLite 支持 FTS5**。安装器将发布版 wheel 装入独立环境，并包含 MCP 和客户端配置依赖。无需克隆仓库或安装 Node.js。

**macOS / Linux**

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.sh
bash install-memory-book.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

**接入 AI**

```bash
memory-book setup --client claude-code --capture --background
memory-book doctor
```

若终端还找不到 `memory-book`，使用安装器输出的完整启动路径。重启客户端后，可以让 AI：**“找回这个项目当前的工程决定，引用原始来源，然后继续任务。”**

把 `claude-code` 换成你的[客户端配置名](docs/integrations.md#supported-profiles)，或重复 `--client` 接入多个客户端。MCP 配置覆盖 Claude Code/Desktop、Codex、Gemini、Cursor 等；原生会话采集支持 Claude Code、Codex、Gemini 和旧版 Python Kimi，其他配置通过显式导入或开启 MCP 写入积累记忆。

`--capture` 主动开启对既有和未来受支持文本会话的采集；省略它则仅配置 MCP。工具调用由宿主和模型决定，连接 MCP 不会自动安装每轮检索 hook。

**升级：**重新运行安装器，再以原来的客户端和采集选项执行 `setup`。已有记忆和旧环境会保留。[升级说明](docs/deployment.md#upgrading)。

## 默认配置

v0.4.0 默认使用**原生词法检索、2,400 字符上下文预算、最多五条结果**，不额外设置 token 上限。字符预算包含 `context` 内的引用头与分隔符，不是整个 JSON 响应的大小上限。

先针对当前项目发起一次具体查询。例如调用 MCP 工具 `recall_memory`：

```json
{
  "query": "当前梯度累积步数",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5
}
```

将 `your-project-id` 替换为实际项目 ID。MCP 默认返回精简来源引用；需要补充证据时，再使用返回的页面 ID 读取原文。CLI 也可以使用相同配置：

```bash
memory-book projects
memory-book recall "当前梯度累积步数" \
  --project your-project-id --budget 2400 --limit 5
```

需要过去的决定时，明确询问“最初”或具体历史问题。当前查询的偏好用于排列证据，不能把每次较晚提及都当成有效变更。[处理冲突与缺失证据](docs/agent-guide.md#when-evidence-is-insufficient)。

## 实测结果

默认检索配置在 **8 个项目、4 类算法、80 个按时间推进的工程问题**上评估，全部案例均保留。下表比较 v0.3.4 与 v0.4.0 采用的检索实现，均使用 **2,400 字符、五条结果**；计时时关闭结果缓存。

| 原生检索指标 | v0.3.4 基线 | v0.4.0 配置 |
|---|---:|---:|
| 可答问题的完整证据 | 44/72 · 61.11% | **68/72 · 94.44%** |
| 固定已知策略消费者：全部检查通过 | 20/48 · 41.67% | **44/48 · 91.67%** |
| 本地 recall p95，含上下文组装 | 1.986 ms | 2.056 ms · **+3.54%** |

完整证据率提高，同时本地 p95 有小幅增加。固定消费者从原文提取明确记录的策略，再运行手写算法变体；其通过率不是 AI 生成代码的准确率。

另一次**相同页面的组件对比**为双方提供相同完整原文、项目范围、前五条限制，并统一使用 2,400 字符的完整块打包。Book 的完整证据为 **68/72（94.44%）**，[固定版本 billion-context 搜索内核](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15)为 **64/72（88.89%）**，逐题获得六个、失去两个完整证据案例。这是固定组件和打包规则下的结果，不代表完整产品或其最新版本。

**这是合成开发回放，不是编码 LLM 生产率测量。** 全部预算结果、失败案例、计时边界和代价保留在[详细工程报告](docs/engineering-memory-results.md)，并附有[原始证据与重算记录](benchmarks/results/engineering-memory-20261115/)。[实验协议](docs/engineering-memory-evaluation.md)明确了下一步：使用真实项目回放、隐藏测试和首次正确补丁时间验证效果。

历史测量继续保留在 [v0.3.4 启动记录](docs/releases/v0.3.4.md)、[完整 HotpotQA 组件对比](benchmarks/results/round6-comparison-43601518020-1/report.md)与[基准历史](benchmarks/README.md)中。

## 文档导航

| 你想做什么 | 入口 |
|---|---|
| 接入客户端、导入会话 | [客户端与导入格式](docs/integrations.md) |
| 安装、升级、Docker、管理后台采集 | [部署指南](docs/deployment.md) |
| 检索、引用原文、处理缺失证据 | [AI 使用指南](docs/agent-guide.md) |
| 在浏览器检查归档 | 运行 `memory-book serve`，打开 [127.0.0.1:8765](http://127.0.0.1:8765) |
| 配置高级检索选项 | [Token 预算](docs/token-budget.md) · [语义检索](docs/semantic-retrieval.md) · [引用格式](docs/indexed-references.md) |
| 查看工程实验或参与开发 | [实测报告](docs/engineering-memory-results.md) · [验证记录](docs/validation.md) · [贡献指南](CONTRIBUTING.md) · [更新日志](CHANGELOG.md) |

归档是本地未加密数据；返回给 AI 客户端的证据会进入该客户端的模型上下文。网页阅读器用于检查归档，正常 MCP 和采集无需 HTTP 端口。[数据与配置位置](docs/deployment.md#data-and-configuration-paths)。

项目独立实现，采用 [MIT 许可证](LICENSE)。[CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)。
