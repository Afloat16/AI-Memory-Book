# AI-Memory-Book

**把工程记忆整理成项目书，沿目录找回完整原始问答。**

精确项目 ID 对应一本书，任务组成章节，节与页指向原始会话。AI-Memory-Book 保存规范化的原始文本，让编程 AI 在换会话、换客户端后，仍能核对决策、约束和失败尝试，再继续工作。

[English](README.md) · [快速开始](#快速开始) · [像读书一样找回记忆](#像读书一样找回记忆) · [2400 字符评测](#2400-字符评测) · [18 个项目家族](#开源方案对比)

**v0.7.0 · MIT · Python 3.10+ · 本地 SQLite / FTS5 · 默认上下文 2400 字符**

## 同名或相似工程，也要选对书

- **用身份选书。** 展示名称可以重复，`route-kernel`、`route_kernel`、`Route-Kernel` 是不同的项目 ID。代码标识符的命名别名不会合并项目身份；阅读器同时展示名称和 ID。
- **先确定范围，再召回。** 多项目归档必须指定精确项目，或使用归属明确的章节 ID；缺少范围会拒绝检索。确实需要跨项目时，显式传 `--all-projects` 或 `all_projects=true`。只有一本书时可以自动选中它。
- **沿目录阅读也携带项目。** 章、节、页的读取支持 `project` 归属校验，传入其他书的 ID 会被拒绝。阅读器会携带该参数；API 调用方沿返回的 ID 继续阅读时，也应传入选定项目。
- **从记忆页回到完整原始 turn。** 一页只是阅读单位，未必容纳完整回答。原始 turn 可独立于分页读取，并支持连续翻页；续读携带 `source_hash`，会话已被替换时明确报错，避免拼接不同版本的内容。

这些检查用于在指定项目范围内防止误混，不等同于身份认证或多用户权限隔离。[目录与来源 API 说明](docs/engineering-workflows.md#browse-one-project-book)。

安装后可从源码检出目录运行[相似项目示例](examples/similar-projects.json)：两本书都叫 **Routing Kernel**，复用 `design-review` 会话 ID、任务名和代码符号，却记录了不同约束。

~~~bash
memory-book --db ./similar-projects.db import examples/similar-projects.json --format canonical
memory-book --db ./similar-projects.db projects
memory-book --db ./similar-projects.db index "routing policy" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-eval
~~~

示例中的 `routing-prod` 记录 `edge_policy=bellman_ford`、`routing.relaxation_limit=128`；`routing-eval` 则记录 `edge_policy=reject_negative`、`routing.relaxation_limit=32`。这些是合成演示约束，应按精确项目 ID 分别读取，避免套用另一工程的相反策略。[继续沿目录读到完整原始 turn](docs/book-navigation.md)。

## 快速开始

需要 **Python 3.10+ 与 SQLite FTS5**。安装器创建包含 MCP/客户端依赖的隔离环境；默认采集和词法检索无需嵌入模型、数据库服务器或记忆服务 API Key。

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
~~~

**接入编程客户端**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

选择受支持的[客户端配置](docs/integrations.md#supported-profiles)，例如 Claude Code、Codex 或 Gemini；可重复 `--client` 接入多个客户端。`--capture` 主动开启受支持的既有和未来文本会话采集，`--background` 启动用户采集服务。仅配置 MCP 或客户端不支持原生采集时，同时省略这两个参数。完成后重启客户端。

MCP 工具是否调用仍由宿主与模型决定。命令不在 PATH 中时，使用安装器输出的完整启动路径。已有归档和安装环境请参阅[部署与升级指南](docs/deployment.md)。

## 像读书一样找回记忆

[可运行示例](examples/engineering-workflow.json)包含四个项目、五段合成会话。在源码目录中使用新的演示数据库：

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db projects
memory-book --db ./demo-memory.db toc inference-demo
memory-book --db ./demo-memory.db index "KVCache" --project inference-demo
~~~

`toc` 列出章节；`index` 检索标题、问题和任务/会话目录字段，返回节地址与路径，不加载完整页面正文。同一项目中，共享 `task_id` 的相关会话归入同一章；没有任务 ID 时，每个会话单独成章。

将目录实际返回的 ID 填入后续读取：

~~~bash
memory-book --db ./demo-memory.db chapter CHAPTER_ID --project inference-demo
memory-book --db ./demo-memory.db section SECTION_ID --project inference-demo
memory-book --db ./demo-memory.db read PAGE_ID --project inference-demo
~~~

再按页面来源回到原始 turn。本例的索引 `1` 表示第二轮原始问答：

~~~bash
memory-book --db ./demo-memory.db turn inference-demo cache-configuration 1
~~~

turn 包含带角色标记的规范化原始消息。`next_offset` 非空时，带上 `--offset NEXT_OFFSET --source-hash RETURNED_SOURCE_HASH` 继续读取，直到为空。从页跳到 turn 时，也可用页面返回的 `source_hash` 固定第一次读取的来源版本。[完整来源读取示例](docs/engineering-workflows.md#read-the-evidence-before-applying-it)。

| 操作 | MCP 工具 |
|---|---|
| 选项目书 | `browse_projects` |
| 浏览或检索目录 | `browse_book`、`search_directory` |
| 打开章或节 | `browse_chapter`、`browse_section`，携带选定的 `project` |
| 读取页 | `read_page`，携带选定的 `project` |
| 读取原始 turn | `read_source_turn`，传入 `project`、`session_id`、`turn_index` |

想直接翻阅，运行 `memory-book --db ./demo-memory.db serve`，打开 **http://127.0.0.1:8765**。选择项目书、沿目录打开页面，再点击“完整问答”。阅读器是可选入口，AI 可以直接通过 MCP 使用这些能力。

## 工程中具体解决什么

**恢复实现必须满足的约束。** 示例记录了负边最短路为什么改用 Bellman–Ford、此前 visited-once 原型为何失败，`JSONLReader` 必须有哪些字段，以及数据划分和归一化怎样避免训练数据泄漏。恢复方法名称时，也要把适用条件与理由一起找回来。

**换一种命名，也能核对原始约定。** 词法别名关联 `HTTPParser`、`httpParser`、`http_parser` 等形式，结果仍保留原始拼写和坐标。这是代码命名归一化，不是推断不同名字的语义同义关系。

**把当前修正与其他项目的数值分开。** 示例中，`inference-demo` 的当前 `KVCache block_size` 是 32，并解释了为何替代 128；另一个网关测试替身单独记录 256。先选定项目，再打开原文核对数值：

~~~bash
memory-book --db ./demo-memory.db recall "current KVCache block_size and reason" --project inference-demo --json
~~~

**让长期归档可以维护和交接。** 未变会话跳过重复导入，变更会话事务性替换。`backup` 生成经校验的 SQLite 快照，`check-database` 只读检查归档，`export-book` 从同一快照导出可导航 Markdown 与规范化来源 JSON。[采集支持](docs/integrations.md) · [备份与交接](docs/engineering-workflows.md#maintain-and-move-the-archive)。

## 默认召回

召回可以直接定位证据，不必强制逐层翻目录。默认是**词法检索、2400 字符、最多五条结果**。字符上限覆盖组装后的 `context`，包含引用和分隔符，不是全部 JSON 元数据或模型 token 的上限。

MCP 的 `recall_memory` 调用示例：

~~~json
{
  "query": "current KVCache block_size and reason",
  "project": "inference-demo",
  "budget_chars": 2400,
  "limit": 5,
  "temporal": "current"
}
~~~

`temporal=auto/current/relevance` 控制保守的时间意图排序。`current` 优先考虑可比较的较新证据，但不负责判定权威状态，也不是按指定历史日期还原状态；历史证据仍可查询。精确 token 上限通过 `budget_tokens` 与 `tokens` 扩展启用，语义检索和约束覆盖扩展也分别显式开启。[召回语义](docs/agent-guide.md) · [Token 预算](docs/token-budget.md)。

## 2400 字符评测

**v0.7.0 正式执行尚未完成，本页暂不报告该版本的质量、延迟或导航通过率。** [预注册协议](benchmarks/project_navigation-plan.md)将统一排序检索与原生项目书导航分开验证；官方资料核验和适配器准备不算已完成的实验结果。

首次 hosted 准备运行中，ReMe 的真实原生 API smoke 已通过。claude-mem 的原始观察记录组件有意采用不区分大小写的项目范围语义，与本实验要求区分 `scope-a` 和 `Scope-a` 的精确大小写契约不兼容，触发 `Native project scope violation`；准备阶段因此在正式质量执行前停止。此项保留为契约不兼容，不记作质量零分，也不表示 claude-mem 缺少项目过滤。[保留的准备报告](benchmarks/reports/v0.7.0-engineering/preparation-attempt1/adapter-smoke/report.json)。

目标矩阵为 **Book 加 7 个外部实现**，调用实际固定版本的上游代码：

| 外部目标 | 注册的组件模式 | v0.7.0 状态 |
|---|---|---|
| billion-context | 原生搜索内核，输入完整原文页 | 待正式执行 |
| claude-mem | 原始观察记录，原生 SQLite/FTS 搜索 | 不区分大小写的范围语义与精确大小写契约不兼容 |
| Basic Memory | 显式原生文本/FTS 组件 | 待正式执行 |
| Mem0 | `infer=False`、真实本地 MiniLM 与原生向量存储检索 | 待正式执行 |
| Chroma | 真实本地 MiniLM 文档集合 | 待正式执行 |
| LangGraph Store | 显式索引 Store，使用同一真实 MiniLM | 待正式执行 |
| ReMe | 官方纯文本文件分块器、本地 BM25、原生精确路径过滤 | 原生 API smoke 已通过，待正式执行 |

注册了两套分开的题集：**80 题工程回归**与 **80 题同主题项目对照**。后者包含八本展示名称相同的项目书，会话名和代码符号也有重合，精确项目 ID 则包含大小写、下划线、连字符和后缀差异；其中有些问题的事实只存在于相邻项目，用于区分“本项目没有证据”与“所有项目都没有证据”。

统一排序轨向各后端提供相同的已出现原文页、未改写问题、精确项目范围和原生前五候选；统一整页组装器分别限制 **1200 与 2400 字符**，包含引用。Book 原生摘录轨独立保留。审计将报告完整证据、必需片段、固定策略测试、仅旧证据、来源/串项目错误、预算违规及两类缺失证据表现。

原生导航另行检查目录检索、章/节/页遍历、完整 turn 重建、错误项目地址拒绝和明确范围选择。这些契约验证 Book 的接口，不把评测包装器代选项目算成其他产品的原生能力。

**解释边界：** 题集为人工编写的开发案例，没有独立留出集或编程 LLM；固定策略测试不等于生成代码正确率。Chroma、LangGraph、Mem0 共用一个嵌入模型，结果具有相关性。原文页 FTS/原始记忆模式未覆盖产品完整的提取或生成流程，按检查点重建索引也不代表验证了全部原生更新/删除机制。来源映射验证共同原文，不表示各产品提供相同的原生引用功能；失败或不可运行的后端必须保留真实状态。

## 开源方案对比

截至 **2026-11-16**，官方资料核验覆盖 **18 个外部项目家族**。下表说明架构与原生能力，不给尚未实测的产品排名。[固定来源、精确模式与许可证说明](docs/open-source-memory-comparison.md) · [项目目录专项资料](docs/v0.7.0-open-source-research.md)。

| 项目家族 | 原生方式与工程范围 |
|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | 代理/客户端上下文管理、可逆压缩和可搜索块，支持项目过滤 |
| [claude-mem](https://github.com/thedotmack/claude-mem) | 活动采集、模型生成观察/摘要、渐进式 SQLite 或可选向量检索 |
| [Mem0 / OpenMemory](https://github.com/mem0ai/mem0) | 应用记忆及会话工具；事实提取或显式原始记忆写入，按用户/代理/run 和元数据限定范围 |
| [Letta / Letta Code](https://github.com/letta-ai/letta-code) | 有状态代理、可编辑记忆、Git 支持的 MemFS，提供文件/消息检索与代理专属或共享状态 |
| [Graphiti](https://github.com/getzep/graphiti) | 保留事件、实体和关系的时序知识图谱，以 `group_id` 限定图数据 |
| [MemOS](https://github.com/MemTensor/MemOS) | MemCube 与服务/本地记忆路径，本地插件也支持 SQLite/FTS5 |
| [Memori](https://github.com/MemoriLabs/Memori) | 采集会话和追踪记录，经模型增强，保留实体/进程/会话归属 |
| [Cognee](https://github.com/topoteretes/cognee) | 将文档和代码组织为块、图和向量，提供数据集范围及文档来源 |
| [memvid](https://github.com/memvid/memvid) | 可携带的 `.mv2` 不可变内容帧、原生词法搜索与可选向量检索 |
| [MCP 官方 memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | JSONL 实体/观察/关系、精确读取与字面子串查询，可用不同实例分开图存储 |
| [LangGraph Store](https://github.com/langchain-ai/langgraph) | 命名空间/键/值存储及可选语义索引，与线程 checkpoint 分开，属于检索基础设施 |
| [LongMemory](https://github.com/CaviraOSS/LongMemory) | 项目记忆、来源与时序 API，可配置嵌入提供方 |
| [Basic Memory](https://github.com/basicmachines-co/basic-memory) | Markdown 知识、目录工具、明确项目路由和歧义路径拒绝，提供文本及语义检索 |
| [Chroma](https://github.com/chroma-core/chroma) | 文档/向量集合、元数据过滤及 collection/tenant/database 边界，属于检索基础设施 |
| [ReMe](https://github.com/agentscope-ai/ReMe) | 本地文件、wikilink、来源行号和原生 BM25；默认关闭嵌入，提供精确路径/元数据过滤 |
| [OpenViking](https://github.com/volcengine/OpenViking) | 分层上下文文件系统、目录摘要/概览和完整来源读取，具备账户/用户隔离与可选资源 ACL |
| [Hindsight](https://github.com/vectorize-io/hindsight) | Memory bank、带证据的观察，以及可检索和导出的文件夹/生成页面体系 |
| [MCP Memory Service](https://github.com/doobidoo/mcp-memory-service) | 本地语义/BM25 记忆、采集、文档导入和图浏览，以标签/存储范围过滤 |

多个项目已经具备目录、来源回溯、项目过滤或本地运行。Book 适合需要**以原始会话为主要归档、明确项目书导航、来源版本检查，以及默认无模型的有限预算证据召回**的工作；图推理、生成式知识页、可编辑代理状态和向量基础设施服务于不同需求。Mem0/OpenMemory、Letta/Letta Code 各算一个家族；许可证因项目和组件而异。

## 实际边界与文档

只能找回已导入的受支持文本，规范化归档不会保留所有厂商的多模态载荷。短结果可能遗漏必要约束，相关结果也不等于答案正确；请补读原始 turn，并运行项目自身测试。分页续读应保留来源版本哈希；替换会话也可能改变页面地址。

[工程工作流](docs/engineering-workflows.md) · [Agent 使用指南](docs/agent-guide.md) · [部署](docs/deployment.md) · [客户端集成](docs/integrations.md) · [评测协议](benchmarks/project_navigation-plan.md)

项目独立实现，采用 [MIT License](LICENSE)。[发布页](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.7.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)。
