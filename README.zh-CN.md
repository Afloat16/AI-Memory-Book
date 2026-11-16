# AI-Memory-Book

**像查书一样定位工程问题的原始证据，让相似项目的记忆各有归属。**

项目是书，任务是章，证据是页。AI-Memory-Book 保存规范化的原始文本会话，让 AI 在换会话、换客户端后，仍能找回工程约束、参数修正和失败尝试，引用来源后继续工作。

[English](README.md) · [快速开始](#快速开始) · [2400 字符实测](#2400-字符实测) · [开源方案对比](#开源方案对比)

**v0.7.0 · MIT · Python 3.10+ · 本地 SQLite / FTS5**

## 工程中的优势

- **后续阅读仍留在选定工程。** 将 MCP 连接绑定到一个实际项目 ID；模型漏填范围时继续使用绑定值，误带另一工程的章节、小节或页 ID 时无法换书读取。常规客户端 setup 会保留已有绑定。
- **把决策与理由一起找回来。** 按项目、任务、会话和原始轮次定位证据，保留页面 ID 与来源；需要核对边界条件、错误信息或某次失败原因时，可以继续读原页，便于代码评审和任务交接。
- **跨命名方式找回代码约定。** `http_parser`、`JSONLReader`、`kv_cache` 等查询可以匹配对应的缩写、驼峰及下划线形式。词法索引补充别名，保留原始拼写、来源坐标与项目边界，便于恢复接口和算法实现约束。
- **明确控制当前证据与历史回查。** `temporal=auto/current/relevance` 在 Python、CLI、MCP 和 HTTP 中一致。自动模式区分“请给原始证据”与“最初的决定”，调用方也可直接选择当前证据排序；同会话后续修正同时覆盖字符与 token 截断。排序仍需结合来源判断。
- **区分配置修订与后续维护提及。** 当前查询在同任务、同查询限定条件下比较字段声明，能关联 `retryLimit=3`、`retry_limit=5` 与清晰的自然语言更新。可识别的引用旧日志、代码示例以及不完整轮次不提供这种声明提示；详细结果解释分类依据，原始证据继续保留供核对。
- **让有限上下文用于工程约束。** 先按项目过滤，再检索和组装证据；默认 2400 字符、最多五条，缺什么再补读，便于同时恢复实现约定、数据划分和边界条件。
- **在已有客户端之间接续任务。** Claude Code、Codex、Gemini 等受支持客户端可以配置同一数据库。切换工具后仍可查询同一项目归档；客户端接入与原生历史采集的支持范围分别列在[集成指南](docs/integrations.md#supported-profiles)。
- **降低记忆层的部署与维护负担。** 默认写入和词法检索不调用模型，无需嵌入模型、数据库服务器或记忆服务 API Key。后台采集跳过未变文件，以稳定会话 ID 和内容哈希避免重复灌入；变更会话事务性替换，修改已有客户端配置前会创建备份。
- **让长期归档可检查、可恢复。** 在线 SQLite 备份包含 WAL 中已提交数据，校验完成后才生成新快照；只读检查提供完整性与运行状态，不迁移源库。派生索引升级保留已有页面地址，旧写入进程的不兼容操作会整笔回滚。

**可靠导入与交接。** CLI 在打开数据库前校验全部会话，无效的后续输入不会先覆盖前面的记录。`export-book` 在同一数据库快照中生成 Markdown 与 JSON，完整写入临时目录后发布；失败可清理并重试，已有非空目录受保护。

接续长期任务时，可以先问“当前实现必须遵守哪些约束？”，再按引用核对后续修正和失败尝试，最后继续修改代码。这类“恢复约定—核对出处—继续实现”的工作流，为任务交接提供明确的证据入口。[来源语义与使用方法](docs/agent-guide.md)。

## 快速开始

需要 **Python 3.10+ 与 SQLite FTS5**。v0.7.0 新增固定项目的 MCP 连接与目录/原文后续读取的项目校验，并保留标识符检索、时间意图控制和归档维护能力。安装器使用隔离环境，包含 MCP/客户端依赖，无需克隆仓库或安装 Node.js。已有归档请按[升级步骤](docs/deployment.md#upgrading)更新；已经使用 schema 4 的归档在 v0.7.0 中无需新的模式迁移，schema 4 迁移步骤只适用于更早的归档模式。

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

**接入并检查**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

将 `claude-code` 换成[客户端配置名](docs/integrations.md#supported-profiles)，可重复 `--client` 接入多个客户端。只有支持原生采集的客户端才保留上述采集参数；其他客户端同时省略 `--capture` 和 `--background`。找不到命令时使用安装器输出的完整路径，然后重启客户端。

`--capture` 主动开启既有及未来受支持文本会话的采集，`--background` 安装并启动用户后台服务。仅配置 MCP 时同时省略这两个参数。工具调用由宿主和模型决定，MCP 接入本身不保证自动召回。升级应沿用相应安装方式，再刷新 setup 并重启客户端，详见[部署指南](docs/deployment.md#upgrading)。

## 算法与工程开发示例

[可运行示例](examples/engineering-workflow.json)包含四个项目、五段合成会话：负边最短路修正、训练数据切分约束、HTTP 解析约定、推理配置变更，以及另一项目中的冲突数值。无需模型 API，即可验证原文查询和项目隔离。

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db recall "jsonl_reader input contract and split" --project training-demo
memory-book --db ./demo-memory.db recall "kv_cache block_size 原始证据" --project inference-demo --temporal current
memory-book --db ./demo-memory.db backup --output ./backups/demo-snapshot.db
memory-book --db ./backups/demo-snapshot.db check-database
~~~

从 [v0.7.0 源码](https://github.com/Afloat16/AI-Memory-Book/tree/v0.7.0)取得示例后，在仓库目录执行，并选择新的数据库和快照路径。[开发工作流指南](docs/engineering-workflows.md)讲解算法约束、失败尝试、标识符检索、Python 接入、精确 token 预算、来源核对及恢复操作。示例中的参数用于演示，不代表生产配置建议。

## 默认配置

默认使用**原生词法检索、2400 字符、最多五条结果**，无额外 token 上限。字符预算包含 `context` 内的引用头与分隔符，不是整个 JSON 响应或模型 token 的上限。

MCP 工具 `recall_memory` 示例：

~~~json
{
  "query": "当前梯度累积步数",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5,
  "temporal": "current"
}
~~~

将项目 ID 替换为真实值；证据不足时使用返回的页面 ID 补读。CLI 同样可用：

~~~bash
memory-book projects
memory-book recall "当前梯度累积步数" --project your-project-id --budget 2400 --limit 5
~~~

## 为一个 MCP 连接固定一本项目记忆

相似服务、训练工程或算法实现，先用**实际项目 ID** 区分。书的显示名不等于身份；不同项目可以拥有同名任务、同名会话和相同代码符号。

| 书籍结构 | 对应的工程用途 | 按需读取入口 |
|---|---|---|
| 项目书 | 选定实际工程 | `browse_projects` / `browse_book` |
| 任务章 | 组织已知属于同一任务的多次会话 | `browse_chapter` |
| 问题节 | 定位相关原文页面 | `browse_section` |
| 证据页 | 核对原始轮次及来源坐标 | `read_page` |

已知问题可以直接在项目内召回；需要查看任务脉络时再沿目录阅读。目录不是每次提问的必经步骤，但项目约束会延续到后续的章节、小节和原文页读取。

~~~bash
memory-book projects
# 将 service-alpha 替换为上一步返回的真实项目 ID。
memory-book setup --client codex --mcp-project service-alpha
# 也可以直接启动一个固定项目的 stdio 连接：
memory-book mcp --project service-alpha
~~~

在绑定连接中，省略项目参数会自动采用绑定值，`browse_book` 也一样；显式请求其他项目会在打开数据库前被拒绝。即使模型带来了另一工程的旧章节、小节或页 ID，也无法通过这个连接读取。启用 `remember_session` 后，写入仍必须明确提供相同的 `payload.project`，不会自动替消息改归属。

普通 setup 会保留已经托管的绑定；用 `--mcp-project OTHER_ID` 换绑，用 `--clear-mcp-project` 明确解绑。`setup --project` 控制**采集归属**，仍需配合 `--capture`；`--mcp-project` 控制 **MCP 连接范围**。配置某个客户端 profile 后，该连接整体使用这个项目，不会随终端当前目录自动切换。[项目范围与配置说明](docs/agent-guide.md#bound-project-connections)。

Python 的 `chapter`、`section`、`read` 支持 `project=...`；对应 CLI 支持 `--project`，HTTP 后续读取支持 `project` 查询参数。阅读器会把当前选中的书传入这些请求，切书时使旧原文响应失效。未绑定调用仍可访问整个归档。这是减少项目范围误用的机制，不是用户身份认证，也不会限制另一个服务或直接数据库访问。

### v0.7.0 已执行的范围检查

独立编写的诊断包含 **4 个相似项目、12 份源会话**：显示名、任务 ID、会话 ID 相同，配置值互相冲突。候选完成 **186 次核心 API 调用，合同检查失败为 0**，包括 **36 次跨项目 ID 拒绝**、**12 次不存在项目拒绝**、分页原文重建、交错热缓存、源替换和项目删除。4 个目录完整性检查直接与原始会话核对覆盖范围。按记录仅去掉计时、缓存状态和目录墙钟元数据后，**35/35 既有 API 完整响应或错误与 v0.6.0 一致**；原文、ID、坐标和证据时间继续参与比较。

v0.6.0 在同一诊断中记录为 **37 次通过、77 次不支持新断言**，不能把“不支持”说成 77 次隔离失败。候选支持新的目录读取后会继续执行更多分页调用，两版调用总数因此不同。这些是开发阶段的接口合同检查，不是回答准确率、独立测试集、速度测量或绝对隔离保证。[原始调用与比较](benchmarks/reports/v0.7.0-project-scope/candidate/) · [完整验证及复跑方法](docs/v0.7.0-project-scope-validation.md)。

未改动的原生工程题集也在两版实际回放：**80 题、1200/2400 字符两档，每项执行一次**。仅排除顶层耗时和缓存诊断后，**160/160 个 Book 响应**以及**四种仓库内策略的 640/640 个响应**全部相同，独立审计通过 **16,863 项检查**。这是召回回归证据，没有新增速度结论，也没有重跑外部组件。[原始回放与审计](benchmarks/reports/v0.7.0-project-scope/native-replay-audit.json)。

## 2400 字符实测

下方外部组件表保留**冻结的 v0.6.0 实验**；上方 v0.7.0 范围诊断是另一项测量。新增资料比较的项目没有被填入数值成绩。

### 六个真实开源实现，同一批固定工程案例

这项实验以冻结的 **v0.6.0 运行时**执行 **8 个项目、4 类算法、6 个时间检查点、80 个问题**。其中有 **72 个可回答问题、80 段必需原文证据、48 个固定策略检查案例，以及 8 个缺证据问题**。算法涵盖负边权最短路、Top-k 同分规则、训练数据划分和全 mask softmax；每个检查点只摄取此前可见的历史。每题重复三次用于计时和稳定性检查，不扩充独立质量样本。

实际运行的外部实现为 **billion-context、claude-mem、Basic Memory、Mem0、Chroma、LangGraph Store**，均固定上游版本。各实现得到相同完整原文页、未改写问题、项目范围及前五条候选，由同一个整块打包器控制在 2400 字符内，引用头也计入预算，超大整块会跳过。Book 保留自身层级和索引元数据。[固定协议、包版本与模型校验](benchmarks/competitors/memory-systems-plan.md)。

外部组件在每个检查点按当时可见的原文快照重建；“来源会话替换”类别只验证更新后快照的检索，未验证各产品自身增量更新/删除流程。七后端共形成 560 个查询/后端组合，三次重复共 1680 次真实原生调用，两档预算共 1120 条打包输出；两个预算复用相同候选。

**分数必须连同测试模式理解。** Basic Memory 采用显式 FTS；claude-mem 搜索直接提供的原始 observations，未运行 observer；Mem0 使用 `infer=False`，未运行事实抽取。Chroma 和 LangGraph 属于检索/存储基础设施。Mem0、Chroma、LangGraph 共用真实本地 MiniLM 模型，保留其原生 256-token 截断。这些结果对应明确配置的组件，未覆盖各产品默认完整流程。

| 实测组件 / 模式 | 证据片段召回 | 完整证据 | 策略检查通过 | 仅旧证据 | 平均字符 |
|---|---:|---:|---:|---:|---:|
| **AI-Memory-Book** | 80/80 | 72/72 · 100.00% | 48/48 | 0 | 1799.2 |
| billion-context · 固定搜索内核 | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1955.0 |
| claude-mem 15.18.1 · 原始 observation FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1488.5 |
| Basic Memory 1.0.0 · 显式 FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1333.1 |
| Mem0 2.2.1 · `infer=False` + MiniLM | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |
| Chroma 1.5.9 · MiniLM 集合 | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |
| LangGraph checkpoint 4.3.2 · 建索引 Store | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |

在 2400 字符下，Book 比三个已测词法组件分别**多找全 8 题**，完整证据率高 **11.11 个百分点**；固定策略检查分别**多通过 8 题**，高 **16.67 个百分点**。相对三种共享 MiniLM 配置，分别多找全 **25 题**。后三者相同的质量计数属于共享模型下的相关证据，不能算成三次独立模型优势验证。[完整组件报告](benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json)。

上下文开销也如实列出：Book 比 billion 平均少 **7.97% 字符**，但为恢复额外证据，返回的文字多于 claude-mem FTS 和 Basic Memory FTS，不能声称所有对照中上下文最短。两个预算下，七个实现的**来源校验错误、预算超限、重复输出变化均为 0**。[原始输出与来源映射](benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/)。

“仅旧证据”指命中了标注的过时片段，却未命中必需证据，不涵盖所有错误类型。例如 billion 的历史决定题缺证据，但这项计数仍为 0；判断覆盖效果还需结合完整证据与分类结果。

来源校验验证的是各适配器到共同原文页的映射，不表示各上游产品原生都提供与 Book 一样的精确引用坐标。

### 优势具体出现在哪些工程场景？

下表为相同 2400 字符整块协议下的完整证据数量：

| 场景（各 8 题） | Book | billion | claude-mem FTS | Basic Memory FTS | 三种 MiniLM 模式¹ |
|---|---:|---:|---:|---:|---:|
| 后续决定修正 | 8/8 | 8/8 | 8/8 | 8/8 | 0/8 |
| 长间隔恢复 | 8/8 | 8/8 | 8/8 | 8/8 | 0/8 |
| 同时恢复多项约束 | 8/8 | 8/8 | 8/8 | 8/8 | 6/8 |
| 历史决定回查 | 8/8 | 0/8 | 8/8 | 8/8 | 1/8 |
| 中英查询 | 8/8 | 8/8 | 0/8 | 0/8 | 8/8 |
| 初始决定 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| 代码标识符 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| 失败尝试 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| 来源会话替换 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |

¹ Chroma、建索引的 LangGraph Store 和原始记忆 Mem0 在本次各类别计数相同，主表和原始数据仍逐个保留。Book 相对 billion 的收益来自历史决定回查；相对 claude-mem/Basic Memory FTS 的收益来自双语查询。MiniLM 配置主要在后续修正、长间隔恢复和历史回查中缺失证据。这些是本批合成案例的表现，不能推广为各产品整体语言或推理能力的结论。[分类与逐题配对审计](benchmarks/reports/v0.6.0-engineering/audit.json)。

### 同时保留 1200 字符的边界

相同原文、问题、候选数量和整块打包器，在较小预算下得到：

| 实测组件 / 模式 | 证据片段召回 | 完整证据 | 策略检查通过 | 仅旧证据 | 平均字符 |
|---|---:|---:|---:|---:|---:|
| **AI-Memory-Book** | 76/80 | 68/72 · 94.44% | 44/48 | 4 | 1048.1 |
| billion-context · 固定搜索内核 | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 948.5 |
| claude-mem 15.18.1 · 原始 observation FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 848.0 |
| Basic Memory 1.0.0 · 显式 FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 948.5 |
| Mem0 2.2.1 · `infer=False` + MiniLM | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |
| Chroma 1.5.9 · MiniLM 集合 | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |
| LangGraph checkpoint 4.3.2 · 建索引 Store | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |

Book 有 **68/72 完整证据、44/48 策略通过**，但仍有 **4 个训练决策问题仅返回旧证据**：两个替换决定、两个长间隔查询。每个已测词法对手都在这四题胜过 Book，同时在另八题落后；总体覆盖率更高不表示逐题都更好，也不表示小预算的旧证据问题更少。[详细验证](docs/v0.6.0-engineering-validation.md)保留全部失败。

### 原生检索与常见策略

以下保留**冻结的 v0.6.0 原生摘录实验**，比较 Book 与仓库内策略在 2400 字符下的表现。平铺 FTS、最近历史不计作额外开源项目。

| 策略 | 证据片段 | 完整证据 | 策略检查通过 | 平均字符 |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | 80/80 | 72/72 | 48/48 | 1799.2 |
| 平铺 FTS | 60/80 | 52/72 | 28/48 | 1801.3 |
| 预算内最近历史 | 64/80 | 56/72 | 32/48 | 2260.9 |
| 无记忆 | 0/80 | 0/72 | 0/48 | 0.0 |

Book 比平铺 FTS **多找全 20 题**，比最近历史**多找全 16 题**，平均上下文比最近历史少约 **20.4%**。FTS 使用相同范围、索引和原生打包器；最近历史使用内存文本、更短引用头且不限制前五条。原生 Book 在 1200 字符下为 **76/80 证据片段、68/72 完整证据、48/48 策略通过，仅旧证据案例为 0**；这组摘录结果不能替代上方整块组件表。[原生回放报告](benchmarks/reports/v0.6.0-engineering/hosted/native/report.json)。

**冻结的 v0.6.0 原生回放**在 2400 字符下的 240 次调用中，检索与上下文组装 **p50 / p95 为 1.560 / 4.846 ms**。结果缓存关闭，SQLite/系统缓存未清空，不包含摄取和模型生成。外部进程调用、向量查询及嵌入计算的计时范围不同，因此不据此宣传完整产品加速倍数；上方每项仅执行一次的 v0.7.0 回归不增加计时结论。

### 可复跑与结论边界

独立审计重算分数并重建完整上下文，**116,693 项检查全部通过**。原有双组件框架与扩展框架中，Book/billion、两预算、80 题的 **320 对完整响应全部一致**；默认调用也与显式 2400/5 及全部 80 条 v0.6.0 运行时保存输出一致。[审计结果](benchmarks/reports/v0.6.0-engineering/audit.json) · [默认一致性](benchmarks/reports/v0.6.0-engineering/hosted/default-profile/report.json) · [成功执行记录](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43788979015)。

这批案例是**参与开发的合成数据**，没有独立测试集，也未调用编码 LLM。固定消费者提取记录中的策略并执行手写算法，不能当作代码生成准确率。**七个后端在两档预算下，对全部 8 个缺证据问题都返回了相关上下文**，因此不代表可靠拒答，也不能写成 80/80 问题回答正确。真实任务完成时间、补丁成功率及总模型成本尚未测量。[验证记录](docs/v0.6.0-engineering-validation.md)保留全部失败、测试范围、来源身份，以及正式质量实验前的 Chroma 接入错误。重型对比依赖与正常 Book 安装分离。

## 开源方案对比

下表依据 2026-11-16 核对的官方来源，覆盖 **19 个外部项目家族**。实验分数只对应明确配置的组件，未实测的完整产品不推断分数。[固定来源、测试模式、部署依赖及许可证说明](docs/open-source-memory-comparison.md)。

| 方案 | 主要工作方式 | Book 的适用优势 |
|---|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | 模型代理与客户端插件，模型驱动可逆压缩、解压和上下文搜索 | 独立归档并按项目查原始证据，通过 MCP 接入现有客户端，无需改变模型 API 路由 |
| [claude-mem](https://github.com/thedotmack/claude-mem) | hooks 采集，observer 生成 observations/摘要，本地 HTTP worker、SQLite，可选 Chroma | 默认采集和词法查询不增加摘要模型调用；stdio MCP 与采集无需 HTTP 监听 |
| [Mem0](https://docs.mem0.ai/open-source/python-quickstart) | 面向应用的用户/agent 记忆，默认模型抽取事实并使用 embedding，可配置本地存储 | 工程会话直接形成原文证据，不必配置额外的事实抽取与嵌入模型 |
| [Letta Code](https://github.com/letta-ai/letta-code) | 有状态 agent，自主管理记忆、技能及 Git 支持的 MemFS，可本地或云端运行 | 给现有编程客户端增加共享证据层，保留已有工具与工作流程 |
| [Graphiti](https://github.com/getzep/graphiti) | 保留原始 episode 的时序知识图谱，抽取实体与关系 | 直接查询项目会话及精确来源坐标，无需默认配置图数据库和抽取模型 |
| [MemOS](https://github.com/MemTensor/MemOS) | MemCube、服务端与本地记忆路径；本地插件也支持 SQLite/FTS5 | 以项目、任务和原始会话为中心，用一个本地 SQLite 文件维护归档 |
| [Memori](https://github.com/MemoriLabs/Memori) | 采集会话与 trace，增强为事实和关系，支持云端或自有数据库 | 无需额外增强流水线即可保留原文，并按上下文预算检索 |
| [Cognee](https://github.com/topoteretes/cognee) | 文档和代码的分块、图谱及向量记忆；本地 GLiNER 路径可不使用 LLM API key | 默认词法检索无需嵌入模型，直接回到原始会话轮次核对 |
| [memvid](https://github.com/memvid/memvid) | 可携带的 `.mv2` 内容帧、词法检索与可选向量搜索 | 现有客户端采集、项目/任务层级和带来源的交接工作流 |
| [官方 MCP memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | JSONL 图谱中显式管理实体、观察和关系，提供字面子串查询 | 摄取完整会话，提供排序检索、来源引用和有预算的上下文组装 |
| [LangGraph Store](https://docs.langchain.com/oss/python/langgraph/stores) | 应用定义 namespace/key/value，语义索引需显式配置，与线程 checkpoint 分离 | 为已有客户端提供可直接使用的采集、归档和检索；LangGraph 面向应用基础设施 |
| [LongMemory](https://github.com/CaviraOSS/LongMemory) | 项目记忆、来源和时序 API，可配置不同 embedding provider | 默认不调用模型、稳定页面地址，以及可直接复跑的工程检索证据 |
| [Basic Memory](https://github.com/basicmachines-co/basic-memory) | Markdown 知识、关联观察和项目范围内的文本/语义查询 | 直接保存会话原文，无需先编写或改写知识笔记 |
| [Chroma](https://github.com/chroma-core/chroma) | 文档和向量集合、本地持久化及元数据过滤 | 已有会话采集、任务导航、原文坐标和上下文组装，默认无需嵌入依赖 |
| [OpenViking](https://github.com/volcengine/OpenViking) | 上下文文件系统、目录摘要/概览及目录范围内的向量检索 | 默认不依赖模型的词法路径，直接回到会话页和来源坐标；目录导航并非 Book 独有 |
| [Serena](https://github.com/oraios/serena) | 编码工具、项目 Markdown 记忆、主题目录和显式引用 | 保存完整会话证据并按项目/任务导航；Serena 也支持按需逐步读取记忆 |
| [EverOS / EverMemOS](https://github.com/EverMind-AI/EverOS) | Markdown 原始存储、抽取记忆、SQLite/LanceDB 索引及应用/项目分区 | 专注原始会话归档，默认不配置抽取模型；对方也有项目分区机制 |
| [SimpleMem](https://github.com/aiming-lab/SimpleMem) | 模型抽取原子事实，结合语义、关键词和元数据检索 | 直接核对工程原始轮次及坐标，无需先压缩为抽取事实 |
| [Supermemory](https://github.com/supermemoryai/supermemory) | 抽取记忆/用户画像、混合检索，含项目/container标签及本地/托管路径 | 轻量会话原文归档、显式项目校验，默认不引入嵌入依赖 |

多个项目都支持目录/渐进读取、项目范围、多客户端、来源查询和本地运行。Book 的选择理由是将**原文证据、项目范围、预算控制和低附加推理依赖**集中到轻量记忆层，适合长期开发、故障复盘与跨客户端任务接续。图关系推理、可编辑 agent 状态、人工维护的 Markdown 知识和向量数据库适用于其他需求；此表不代表通用优胜结论。Mem0/OpenMemory、Letta/Letta Code 分别只计一个家族，Chroma 与 LangGraph 明确按基础设施比较。

## 文档与数据边界

[开发工作流](docs/engineering-workflows.md) · [集成](docs/integrations.md) · [部署与 Docker](docs/deployment.md) · [AI 使用指南](docs/agent-guide.md) · [Token 预算](docs/token-budget.md) · [可选语义检索](docs/semantic-retrieval.md) · [贡献指南](CONTRIBUTING.md)

运行 `memory-book serve` 可在 [127.0.0.1:8765](http://127.0.0.1:8765) 检查归档。归档是本地未加密数据，召回证据会进入所用客户端的模型上下文；项目过滤不是多用户权限控制。客户端配置备份不等于数据库自动备份，详见[数据位置与维护](docs/deployment.md#data-and-configuration-paths)。

项目独立实现，采用 [MIT 许可证](LICENSE)。[当前发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.7.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)。
