# AI-Memory-Book

**给 AI 一本有目录、能追读原文的工程记忆书；每个项目各自成书。**

项目是书，任务是章，问题组是节，原始证据是页。AI 可以从标题或问题线索定位章节，再沿地址读取原文。多个相似工程即使复用任务名、代码标识符和参数，也通过明确的项目 ID 分开归档；换会话、换客户端后，继续找回工程约束、后续修正和失败尝试。

[English](README.md) · [快速开始](#快速开始) · [检索效果](#检索效果) · [性能](#性能) · [工作方式](#工作方式) · [文档](#文档)

**v0.11.0 · MIT · Python 3.10+ · 本地 SQLite / FTS5**

## 当前版本一览

| 找回完整证据 | 目录契约检查 | 减少上下文 | 核对原始来源 |
|---|---|---|---|
| **72 / 72 个可回答案例** | **119 / 119 项通过** | **平均少 20.4% 字符** | **161 次原文读取** |
| 固定工程题集，2400 字符预算 | 自编定位、分页与范围检查 | 同题集，相对预算内最近历史 | 目录题集中的 80 个不同页面 |

| 日常使用 | 当前能力 |
|---|---|
| 查询成本 | 默认写入与词法检索 **不调用模型**，无需嵌入模型或记忆服务 API Key |
| 上下文控制 | 默认 **2400 字符、最多 5 条**；可选精确 token 上限 |
| 执行效率 | **22 个 C 加速入口**，保留完整 Python 参考实现与可移植回退 |
| 客户端接续 | Claude Code、Codex、Gemini 等受支持客户端共享本地归档 |
| 目录定位 | 根据标题、问题和任务目录找到章节，保留项目范围与后续读取地址 |
| 新修正恢复 | 当前状态查询在已相关章节内补充较近、可比较且来源经过核验的候选 |

上表是明确条件下的开发题集结果；完整证据率不是 LLM 回答准确率，目录检查不是实际工程任务成功率，也不是独立留出集验证。[当前结果与证据](docs/current-results.md)

## 快速开始

需要 **Python 3.10+ 与 SQLite FTS5**。安装器创建隔离环境并安装 MCP／客户端依赖，无需克隆仓库或安装 Node.js。

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.11.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.11.0/scripts/install.py -OutFile install-memory-book.py
py -3 -I -X utf8 .\install-memory-book.py
~~~

**接入客户端并检查**

~~~bash
memory-book setup --client claude-code
memory-book --version
memory-book doctor
~~~

| 需要的行为 | 操作 |
|---|---|
| 接入其他客户端 | 将 `claude-code` 替换为[支持的配置名](docs/integrations.md#supported-profiles)，可重复 `--client` |
| 开启会话采集与后台服务 | 对支持原生采集的客户端，在 `setup` 后加入 `--capture --background` |
| 升级已有安装 | 沿用原安装路径参数，重新执行原有 `setup` 并重启客户端／后台服务；schema 4 归档无需新增迁移 |
| 命令不在 PATH | 使用安装器输出的完整启动器路径 |

采集需主动启用：`--capture` 包含既有及未来受支持文本会话，`--background` 安装并启动用户服务。MCP 接入后，何时调用记忆工具仍由客户端和模型决定。[部署与升级](docs/deployment.md#upgrading)

## 检索效果

**固定合成开发题集：8 个项目、4 类算法、6 个时间检查点、80 道问题。** 其中 72 题可回答，包含 80 段必需证据和 48 个固定策略检查；每个检查点只摄取当时已出现的历史。

旧版与冻结的 v0.11 算法候选各完成 **800 条响应**：640 条原生策略响应＋160 条 Book 整块输出。独立评分、来源和预算检查通过，逐题评分 **0 退步**；这是固定源码回放，不冒充尚未核验的新发布包结果。[当前版本回放记录](docs/current-results.md)

![2400 字符固定预算下，Book与BM25S均72/72，Haystack BM25为66/72，三个历史词法模式各64/72，共享MiniLM配置47/72。](docs/readme-assets/evidence-coverage.zh.svg)

### 与原生检索策略对比

同一题集、2400 字符预算，使用各策略的原生上下文组装方式：

| 策略 | 必需证据 | 完整证据 | 固定策略通过 | 平均字符 |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **80/80** | **72/72** | **48/48** | **1799.2** |
| 项目范围内平铺 FTS | 60/80 | 52/72 | 28/48 | 1801.3 |
| 预算内最近历史 | 64/80 | 56/72 | 32/48 | 2260.9 |
| 无记忆 | 0/80 | 0/72 | 0/48 | 0.0 |

相对平铺 FTS，Book **多找全 20 题**；相对最近历史，**多找全 16 题，同时平均少用 20.4% 字符**。FTS 使用相同项目范围、索引与原生打包器；最近历史使用更短引用头且不限制前五条。

### 与已测组件对比

下表统一使用 **2400 字符整块协议、最多 5 条候选**。已逐一核对新增 Haystack／BM25S 与六个历史外部配置具有相同的 80 题、6 个时间检查点、原始供给页摘要和项目范围。Book 使用冻结源码回放；历史行保留原执行，不冒充本轮重测。比较对象是固定配置的组件，不是完整产品默认流程排行。

| 组件与测试模式 | 完整证据 | 固定策略通过 | 仅旧证据 | 平均字符 |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **72/72 · 100.00%** | **48/48** | **0** | **1799.2** |
| BM25S 0.3.16 · 检索库默认配置 | 72/72 · 100.00% | 48/48 | 0 | 1846.7 |
| Haystack 3.5.0 · InMemoryBM25Retriever | 66/72 · 91.67% | 42/48 | 0 | 1884.7 |
| billion-context · 固定搜索内核 | 64/72 · 88.89% | 40/48 | 0 | 1955.0 |
| claude-mem · 原始 observation FTS | 64/72 · 88.89% | 40/48 | 0 | 1488.5 |
| Basic Memory · 显式 FTS | 64/72 · 88.89% | 40/48 | 0 | 1333.1 |
| 共享 MiniLM 配置¹ | 47/72 · 65.28% | 25/48 | 4 | 1963.1 |

**Book 与 BM25S 在 2400 字符下的完整证据和固定策略结果持平。** Book 比 Haystack BM25 多找全 6 题，比 billion-context／claude-mem FTS／Basic Memory FTS 各多找全 8 题，比共享 MiniLM 组多找全 25 题。平均上下文比 billion-context 少 7.97%，但多于另两个历史 FTS 组件。**1200 字符下 BM25S 优于 Book 整块模式**，下文完整列出。

¹ Mem0（`infer=False`、Chroma 后端）、Chroma、LangGraph Store 分别执行，使用同一 MiniLM 表示；相同分数属于相关结果。重复维护模板限制了这批语料区分它们的能力。claude-mem 未运行 observer，Mem0 未运行事实抽取。[固定配置、逐题记录与来源](docs/current-results.md)

**Memvid SDK 2.0.160 的 lex 模式也已实际执行：**全部原始自然语言问题均返回空的原生命中列表。另存的 14 次诊断中，原文关键词正控能读到索引页面，但完整问题在有／无项目范围时仍为空。这些结果作为该固定查询配置的限制保留，不用零分宣称产品胜出，也不当作拒答能力；诊断改写不替换原评分问题。[完整执行、审计与诊断](docs/v0.11.0-validation.md#additional-real-upstream-components)

架构对比已覆盖 **21 个外部项目家族**，其中 4 个是存储／检索库或框架。**9 个外部配置已有实际执行**：8 个进入上表，Memvid 的查询限制单列。Letta、Graphiti、MemOS、Memori、Cognee、OpenViking、Serena、EverOS、SimpleMem、Supermemory、LongMemory 和官方 MCP memory server 仅列来源可核对的功能与边界，没有填入未测分数。[项目覆盖与官方来源](docs/open-source-memory-comparison.md)

### 收益出现在哪些问题上

下表列 Book 与**历史外部模式**的完整证据数，每类 8 题。新增 BM25S 在全部可回答类别均为 8/8；Haystack 除历史决定为 2/8 外，其余均为 8/8。

| 场景 | Book | billion | claude-mem FTS | Basic Memory FTS | MiniLM 组 |
|---|---:|---:|---:|---:|---:|
| 后续决定修正 | **8/8** | 8/8 | 8/8 | 8/8 | 0/8 |
| 长间隔恢复 | **8/8** | 8/8 | 8/8 | 8/8 | 0/8 |
| 多项约束 | **8/8** | 8/8 | 8/8 | 8/8 | 6/8 |
| 历史决定回查 | **8/8** | 0/8 | 8/8 | 8/8 | 1/8 |
| 中英查询 | **8/8** | 8/8 | 0/8 | 0/8 | 8/8 |

初始决定、代码标识符、失败尝试和来源会话替换四类，各组均为 8/8。[完整分类与对比边界](docs/current-results.md)

### 小预算边界

| 1200 字符下的 Book 模式 | 必需证据 | 完整证据 | 固定策略通过 | 仅旧证据 |
|---|---:|---:|---:|---:|
| 原生摘录 | 76/80 | 68/72 | 48/48 | 0 |
| 公共整块协议 | 76/80 | 68/72 | 44/48 | 4 |

同一 1200 字符整块协议下，**BM25S 为 80/80 必需证据、72/72 完整证据、48/48 固定策略、0 仅旧证据**；Haystack 分别为 74/80、66/72、42/48、0。Book 的总体分数不能推出每个组件、每道题都更好。

两种打包方式不可混用。Book 整块协议的 4 个训练决策案例仅返回旧证据，已测词法对照在这些题上更好。题集参与过开发，并非独立留出集；固定策略检查不是代码生成准确率。Book 与上表八个外部配置对 8 个缺证据问题仍返回上下文；Memvid 全空结果则按前述查询限制披露，均不构成拒答能力结论。[完整核验与复跑](docs/current-results.md)

## 性能

### 历史固定性能实验

以下保留 **v0.10.0 及更早固定源码**上的测量、原环境和退步项。v0.11 修改了当前状态召回与目录读取事务；这些数字没有在新运行时重新测量，不能用来宣称 v0.11 端到端提速，也不能与本轮结果叠加。C 源码字节相同只证明组件连续性。

![历史 v0.10 语义与目录组件的实测结果：大规模语义受跟踪峰值分配减少66.31%，语义耗时降低6.38%，模拟初始化降低41.50%，大目录读取改善；图中保留小场景退步。](docs/readme-assets/runtime-gains.zh.svg)

| 工作负载 | 对比结果 | 测量边界 |
|---|---|---|
| 32,768 个语义窗口 | **耗时降低 6.38%**；峰值分配 **85,005,064 → 28,637,125 字节（−66.31%）** | 分配量含可跟踪的 NumPy 缓冲区，不是总 RSS |
| 模型文件初始化 | 文件读取与内容哈希字节数**各减半**；模拟初始化**耗时降低 41.50%** | 不含真实 ONNX 加载、分词器解析或推理 |
| 20 节 × 每节 20 页 | **耗时降低 5.31%**；SELECT **63 → 24 次** | 相同固定目录、相同输出 |
| 100 节 × 每节 20 页 | **耗时降低 6.46%**；SELECT **303 → 104 次** | 相同固定目录、相同输出 |
| 20／100 节 × 每节 1 页 | **耗时降低 20.48%／23.97%** | 所有四轮成对测量均改善 |
| 20／100 节 × 每节 100 页 | **耗时降低 1.86%／1.98%** | 只按当前小节保留有界预览记录 |

**该历史实验保留的成本：**4,096 个语义窗口耗时 **+1.41%**；单节目录预览 20／100 页分别 **+1.07%／+0.42%**，总体中位数约增加 2／4 微秒。耗时百分比取四轮成对比值的中位数；完整目录测量 **1,440 次调用全部输出一致**。这些是热缓存组件测量，不代表完整 MCP 或模型回答加速。[v0.10 固定实现的全部测量与验收](docs/comprehensive-v010-validation.md)

### 当前沿用的原生核心

原生核心覆盖词法循环、摘录窗口、候选选择、预算分配、来源投影与分段。以下保留该实现的固定实验记录，**没有重新计时，也不与上表百分比叠加**。

![当前沿用的原生核心在合成与公开数据上的直接调用及真实MCP p95耗时对比；此图展示保留的组件实验记录。](docs/readme-assets/native-latency.zh.svg)

| 数据与预算 | 直接 recall p95 耗时降低 | 真实 stdio MCP p95 耗时降低 |
|---|---:|---:|
| 合成数据 · 2400 字符 | **1.82%** | **2.64%** |
| 公开回归数据 · 2400 字符 | **5.79%** | **3.51%** |
| 合成数据 · 1024-token 上限 | **8.03%** | **8.23%** |
| 公开回归数据 · 1024-token 上限 | **4.80%** | **1.12%** |

| 完整成对导入批次 | 首次导入耗时降低 | 未变数据再次导入耗时降低 |
|---|---:|---:|
| 合成数据 | **9.28%** | **2.97%** |
| 公开回归数据 | **10.39%** | **3.94%** |

保留实验的 **113,568 次调用／56,784 对结果**通过输出、索引与来源坐标核对。默认配置 16 个成对 p95 轮次中有 15 个改善；另一个为 **+0.89%**，token 预算 MCP 也保留 **+3.18%** 的单轮 p95 退步。

**资源代价：**API 导入增加 2.04–2.20 ms，结束时 RSS 增加约 0.02–0.23 MiB；公开集默认 MCP 初始化增加 7.35 ms，测量主机上的扩展文件增加 519,480 字节。单台 Ubuntu／CPython 主机、无结果缓存命中、未清空 SQLite／系统缓存，不含模型生成。[全部配置、成本与原始记录](docs/native-core-validation.md)

## 工作方式

![按项目归档原始会话，经范围约束检索与预算组装后返回带引用的证据，可按需浏览目录或追读原页。](docs/assets/method-overview.svg)

| 结构与机制 | 工程用途 | 入口 |
|---|---|---|
| 项目书 | 将相似工程的记录分开 | `browse_projects`／`browse_book` |
| 目录定位 | 根据标题、问题与目录字段定位章节，按章去重分页 | `search_directory`／CLI `locate` |
| 任务章与问题节 | 组织同一任务的多次会话，按需查看脉络 | `browse_chapter`／`browse_section` |
| 原始证据页 | 核对决定、参数、错误信息和失败原因 | `read_page` |
| 标识符别名 | 查询缩写、驼峰、下划线形式，保留原文与坐标 | `http_parser`、`JSONLReader`、`kv_cache` |
| 时序选择 | 区分当前证据与历史回查 | `temporal=auto/current/relevance` |
| 可恢复归档 | 验证备份、只读检查、同快照导出 | `backup`／`check-database`／`export-book` |

### 从目录定位到原文

~~~bash
# 使用已经存储的实际项目 ID，以及任务或问题标题中的词。
memory-book locate "gradient accumulation" --project service-alpha --limit 10
~~~

定位复用 title、question、directory 索引，即使原文正文没有重复标题词，也可以找到章节。结果按章节去重后分页，每章最多预览 5 个匹配小节，明确标记 `result_type="directory", evidence=false`。沿返回的项目、章节、小节 ID 追读原文；标题和摘要是导航提示，不能直接当作回答证据。分词后采用 OR 匹配，因此部分词命中也可能返回目录。

自编的 8 项目目录工作负载中，**119 项契约检查通过**，实际执行 **130 次定位、161 次原文页读取**，覆盖 **80 个不同页面**。首次运行的 8 项负例预期与分词规则冲突，失败、修订理由和完整第二次记录均保留；这项夹具修正不是算法提升。[目录验证与范围边界](docs/v0.11.0-validation.md)

### 旧记录密集时找回简短新修正

当前状态查询在原相关性结果已经涉及的章节内补充较近候选，每页仍独立核对原始 turn。只有符合既有同章节、同字段和剩余查询线索规则的候选，才有资格替换旧记录；不会直接挑全库最新页。

开发探针包含 4、100、1000 条重复旧记录，以及返回上限 1、5，共 **6 个配置，每个重复 3 次**。找回简短新修正的次数由 **3/18 → 18/18**，并非 18 道独立测试题；相关性模式对照保持一致。其中一个配置仍慢于旧版，额外返回候选的数量上限也不等于数据库扫描／排序工作有界。[完整探针、成本与限制](docs/v0.11.0-validation.md#current-revision-recovery)

### 固定项目范围

~~~bash
memory-book projects
# 用上一步返回的实际项目 ID 替换 service-alpha。
memory-book setup --client codex --mcp-project service-alpha
memory-book recall "当前梯度累积步数" --project service-alpha --budget 2400 --limit 5
~~~

| 范围设置 | 行为 |
|---|---|
| 已绑定连接省略项目参数 | 召回与后续读取继承绑定的项目 |
| 显式冲突项目或其他项目的页 ID | 拒绝读取，不会默默切换工程 |
| 普通 `setup` | 保留已有托管绑定 |
| `--mcp-project`／`--clear-mcp-project` | 明确换绑／解除 MCP 连接绑定 |
| `setup --project` | 控制采集归属，需配合 `--capture` |

绑定作用于配置的连接，不随终端当前目录自动切换。未绑定且省略项目的请求仍可跨书查询。项目范围不是多用户认证，也不约束直接数据库访问。[项目绑定](docs/agent-guide.md#bound-project-connections)

**默认预算覆盖 `context` 内的引用头与分隔符，不是完整 JSON 或模型 token 上限。** 证据不足时再读具体页面；目录浏览是可选步骤，证据排序也不等于事实权威裁定。[可运行工程示例](examples/engineering-workflow.json) · [开发工作流](docs/engineering-workflows.md)

## 保留的 v0.10 交付记录

下表是已经完成的 **v0.10.0** 发布结果。v0.11 的最终源码 CI、原生矩阵和公开安装验证完成后，才会记录其新交付结果。

| 项目 | v0.10 发布结果 |
|---|---|
| 最终源码 CI | **11 / 11 项通过** |
| 原生构建与安装 | **30 / 30 个组合通过**：CPython 3.10–3.15 × 5 个平台目标 |
| 平台目标 | Linux x86_64／ARM64、macOS Intel／ARM64、Windows AMD64 |
| 原生测试记录 | **4,245 项通过、75 项指定可选跳过、0 失败** |
| 公开发布文件 | **67 个**均重新下载并核对大小与 SHA-256 |
| 公开安装 | 确认版本、原生后端与默认 MCP／客户端依赖 |
| 行为与档案 | schema 4、页面／来源 ID 与 Unicode 坐标保持 |

75 项跳过对应指定的可选 token 测试和不可用的子解释器能力。三种操作系统的安装流程由 CI 覆盖；发布后的真实公开 URL 安装测试在 Ubuntu 完成。[发布工作流](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44009581198) · [完整发布证明](https://github.com/Afloat16/AI-Memory-Book/blob/2f57e03299ddc350c773fe3bc2fc528e1b13dbd8/benchmarks/reports/comprehensive-v010/publication-proof/README.md)

用安装器输出的 Python 解释器路径替换下方 `python`，即可检查实际版本与后端：

~~~bash
python -I -X utf8 -c "import memory_book; from memory_book._text_backend import BACKEND_NAME; print(memory_book.__version__, BACKEND_NAME)"
~~~

兼容平台打印 `0.11.0 native`。`MEMORY_BOOK_TEXT_BACKEND=auto` 为默认值，`python` 选择参考实现，`native` 要求扩展存在。[后端选择与源码构建](docs/deployment.md#native-backend-and-source-builds)

## 文档

| 想做什么 | 文档 |
|---|---|
| 核对本文图表、固定配置与原始数据 | [当前结果](docs/current-results.md) · [完整验证索引](docs/validation.md) |
| 接入现有客户端、开启采集 | [集成指南](docs/integrations.md) · [部署与升级](docs/deployment.md) |
| 让 AI 按需使用记忆、核对来源 | [使用指南](docs/agent-guide.md) · [工程示例](docs/engineering-workflows.md) |
| 控制 token 或启用本地语义候选 | [Token 预算](docs/token-budget.md) · [语义检索](docs/semantic-retrieval.md) |
| 比较更多开源项目的架构与用途 | [开源方案对比](docs/open-source-memory-comparison.md) |
| 参与开发 | [贡献指南](CONTRIBUTING.md) |

运行 `memory-book serve` 可在 [127.0.0.1:8765](http://127.0.0.1:8765) 查看归档。数据保存在本地且未加密；召回的证据会进入所用客户端的模型上下文。[数据位置与维护](docs/deployment.md#data-and-configuration-paths)

独立实现，采用 [MIT 许可证](LICENSE)。[当前发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.10.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)
