# AI-Memory-Book

**给 AI 一本有目录、能追读原文的工程记忆书；每个项目各自成书。**

项目是书，任务是章，问题组是节，原始证据是页。AI 可以从标题或问题线索定位章节，再沿地址读取原文。多个相似工程即使复用任务名、代码标识符和参数，也通过明确的项目 ID 分开归档；换会话、换客户端后，继续找回工程约束、后续修正和失败尝试。

[English](README.md) · [快速开始](#快速开始) · [检索效果](#检索效果) · [性能](#性能) · [工作方式](#工作方式) · [文档](#文档)

**v0.13.0 发布准备 · MIT · Python 3.10+ · 本地 SQLite / FTS5 · 可选原生 C 加速**

**v0.13.0 正在准备发布。** 独立审计的长期回放达到 **788 个项目、100,000 页**。七个检查点上，v0.13 均找全 **56/56 个可回答 recall 案例**，v0.12 基线为 **48/56**。目录导航的合并样本 p50 在 14 个已测查询／阶段组中均更低；召回同时存在改善与变慢项。本轮源码实验已经验证；发布登记、最终发布源码 CI、原生包和公开安装仍需各自通过门禁。[结果与边界](docs/current-results.md) · [v0.12 公开安装证明](benchmarks/reports/v0.12-publication/README.md)

## 当前版本一览

| 找回完整证据 | 目录契约检查 | 当前声明诊断 | 独立边界控制 |
|---|---|---|---|
| **72 / 72 个可回答案例** | **每后端 119 / 119 项通过** | **38 / 38 个可回答案例** | **每后端 37 / 37 项通过** |
| 原 80 题工程题集，两预算、两条组装轨道 | 定位、分页、精确范围与原文追读 | 另列的 62 题诊断，四种 auto 预算／上限配置 | 引用、撤销、字段／环境身份及独立报告事实 |

这些是分母各自独立的自编开发题集结果，衡量检索证据与 API 契约；不代表代码模型回答准确率、独立留出集效果或实际工程任务成功率。[真实源码、原始响应与边界](docs/current-results.md)

| 日常需求 | 源码提供的能力 |
|---|---|
| 接续工程 | 找回原始决定、后续修正、约束和失败尝试，并保留来源引用 |
| 隔离相似项目 | 精确项目 ID 与绑定项目的 MCP 连接，后续原文读取沿用同一范围 |
| 从标题找问题 | 索引任务、问题与章节目录，返回去重章节和可继续读取的地址 |
| 找到当前决定 | 核对完整原文中的字段、环境和声明；历史／发生次数问题保留对应证据 |
| 识别待核实内容 | 返回有限候选范围内的声明／潜在冲突状态，附原始页面 ID |
| 检索代码与对话 | 中英文词法检索，支持缩写、camelCase 与 snake_case 别名 |
| 控制上下文 | 默认 2400 字符、最多 5 条；可选精确 token 上限 |
| 切换客户端 | Claude Code、Codex、Gemini 等受支持客户端共享本地归档 |
| 本地运行与恢复 | 默认写入／词法检索不调用模型；支持核验备份、事务性来源替换和快照导出 |

## 快速开始

**以下命令以 v0.13.0 为目标，请在其[发布工作流](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/release.yml)及公开安装检查完成后使用。** 当前实际已发布版本仍是 [v0.12.0](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.12.0)。

需要 **Python 3.10+ 与 SQLite FTS5**。安装器创建隔离环境并安装 MCP／客户端依赖，无需克隆仓库或安装 Node.js。

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.13.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.13.0/scripts/install.py -OutFile install-memory-book.py
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

### 多个相似项目的长期历史

同一冻结协议比较 v0.12 与 v0.13：1024 页参考库、只改时间戳的年龄对照、外项目增长至 10,016／50,016 页、目标自身历史增长至 100,000 页、相同逻辑来源交错写入，以及替换已有来源。完整运行记录 **13,608 次 API 测量**，独立离线审计核对保存的响应和 66,136 条来源引用。这是自编开发题集，包含曾用于定位修复的案例。[原始产物与恢复](benchmarks/reports/v0.13-scale-run2/README.md) · [独立审计](benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-saved-response-review.json)

| 七阶段质量结果 | v0.12 基线 | v0.13 源码 |
|---|---:|---:|
| 可回答 recall 配置完整证据 | 336/392 | **392/392** |
| 找回必需来源片段 | 392/448 | **448/448** |
| 在适用题目中当前来源排第一 | 80/168 | **112/168** |
| 旧来源排在当前来源之前 | 32 | **0** |
| 目录完整证据 | 56/56 | **56/56** |
| 缺证据问题仍返回上下文 | 56/56 | **56/56** |
| 来源错误／跨项目输出 | 0 | **0** |

同一组 56 个可回答问题在不同阶段重复，392 不是独立问题数。每阶段的 8 个多来源问题均补齐两个必要来源，仍保留边界约束第一、当前策略第二，按原评分如实计数：**找全证据不等于当前来源总在第一位**。缺证据问题仍返回相关上下文，不能据此宣称可靠拒答。首轮失败和所有中间退步保留原记录。[完整解释与成本](docs/v0.13.0-validation.md)

### 原固定工程题集

固定工程题集：8 个项目、4 类算法、6 个时间检查点、80 个问题，其中 72 个可回答，8 个询问缺失证据。

v0.12 基线与最终 v0.13 源码各完成 **800 个响应配置**，其中 Book 为 320 个配置，仓库内对照策略为 480 个配置。独立来源、预算和评分检查确认，两版 **逐配置评分无变化**。Book 在 **1200 和 2400 字符两种预算、原生摘录与公共整块两条轨道**上，均保持 **80/80 必需证据、72/72 完整证据、48/48 固定策略检查**。这是自编开发题集上的源码结果。[准确身份、逐题记录与边界](docs/current-results.md)


### 与原生检索策略对比

同一题集、2400 字符预算，使用各策略的原生上下文组装方式：

| 策略 | 必需证据 | 完整证据 | 固定策略通过 | 平均字符 |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **80/80** | **72/72** | **48/48** | **1798.9** |
| 项目范围内平铺 FTS | 60/80 | 52/72 | 28/48 | 1801.3 |
| 预算内最近历史 | 64/80 | 56/72 | 32/48 | 2260.9 |
| 无记忆 | 0/80 | 0/72 | 0/48 | 0.0 |

相对平铺 FTS，Book **多找全 20 题**；相对最近历史，**多找全 16 题，同时平均少用 20.4% 字符**。最近历史使用更短引用头且不限制前五条。这些是仓库内策略，不额外计为外部开源产品。[协议与当前结果](docs/current-results.md)

### 与已测开源组件对比

下表统一使用 **2400 字符整块协议、最多 5 条候选**。Book 使用最终 v0.13 源码 `91412b43` 回放；外部行保留原固定版本的真实执行，并核对相同的 80 题、6 个时间检查点、原始供给页摘要和项目范围。**这些外部组件均未在 v0.13 的十万页实验中重新运行。**

| 组件与测试模式 | 必需证据 | 完整证据 | 固定策略通过 | 仅旧证据 | 平均字符 |
|---|---:|---:|---:|---:|---:|
| **AI-Memory-Book** | **80/80** | **72/72 · 100.00%** | **48/48** | **0** | **1798.9** |
| BM25S 0.3.16 · 检索库默认配置 | 80/80 | 72/72 · 100.00% | 48/48 | 0 | 1846.7 |
| Whoosh 2.7.4 · BM25F、配置 OR 解析器 | 80/80 | 72/72 · 100.00% | 48/48 | 0 | 1457.8 |
| Haystack 3.5.0 · InMemoryBM25Retriever | 74/80 | 66/72 · 91.67% | 42/48 | 0 | 1884.7 |
| LanceDB 0.41.0 · 原生 FTS | 72/80 | 64/72 · 88.89% | 40/48 | 4 | 1876.7 |
| billion-context · 固定搜索内核 | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1955.0 |
| claude-mem · 原始 observation FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1488.5 |
| Basic Memory · 显式 FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1333.1 |
| 共享 MiniLM 配置¹ | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.1 |

**Book、BM25S 与配置后的 Whoosh，在两种预算下的完整证据和固定策略结果均持平；Whoosh 在两种预算下都使用更少平均字符。** 2400 字符时，Book 比 Haystack 多找全 6 题，比 LanceDB 及三个历史词法模式各多找全 8 题，比共享 MiniLM 各配置多找全 25 题。这些结果不能推出全面领先。

¹ Mem0（`infer=False`、Chroma 后端）、Chroma、LangGraph Store 分别执行，使用同一 MiniLM 表示；分数相同属于相关结果。claude-mem 未运行 observer，Mem0 未运行事实抽取，Basic Memory 未运行完整默认混合流程。Whoosh 明确配置 **OR**，并非默认 AND 解析器；Haystack、BM25S、LanceDB 与 Whoosh 属于框架／存储／检索组件。表格比较固定组件配置，不给完整产品默认流程排名。[模式、固定版本与来源审计](docs/current-results.md) · [LanceDB／Whoosh 原始记录](benchmarks/reports/v0.12-search-components/README.md)

**Memvid SDK 2.0.160 的 lex 模式也已实际执行：**全部原始自然语言问题均返回空的原生命中列表。另存的 14 次诊断中，原文关键词正控能读到索引页面，但完整问题在有／无项目范围时仍为空。这些结果作为该固定查询配置的限制保留，不用零分宣称产品胜出，也不当作拒答能力；诊断改写不替换原评分问题。[完整执行、审计与诊断](docs/v0.11.0-validation.md#additional-real-upstream-components)

架构对比已覆盖 **26 个外部项目家族**，其中 6 个是存储／检索库或框架。**11 个外部配置已有实际执行**：10 个在上表体现，Memvid 查询限制单列。Hindsight、MemSearch、MCP Memory Service、Letta、Graphiti、MemOS、Memori、Cognee、OpenViking、Serena、EverOS、SimpleMem、Supermemory、LongMemory 和官方 MCP memory server 等其他家族，仅列官方来源支持的功能与边界，没有填入未测分数。[架构、部署与官方来源](docs/open-source-memory-comparison.md)

### 1200 字符预算下的结果

| v0.13 源码／组装方式 | 必需证据 | 完整证据 | 固定策略 | 仅旧证据 | 平均字符 |
|---|---:|---:|---:|---:|---:|
| 原生摘录 | 80/80 | 72/72 | 48/48 | 0 | 1196.6 |
| 公共整块协议 | 80/80 | 72/72 | 48/48 | 0 | 1041.5 |

这些评分与 v0.12 基线相同。同一 1200 字符整块协议下，**BM25S 与配置后的 Whoosh 也都是 80/80 必需证据、72/72 完整证据、48/48 固定策略、0 仅旧证据**；原记录平均字符分别为 1045.3 和 884.5。此前 v0.11 → v0.12 的改进保存在 [v0.12 历史结果](docs/v0.12.0-readme-results.md#what-changed-at-1200-characters)，不算作本轮新增收益。

两条组装轨道分别统计。“仅旧证据为零”只指没有出现已登记旧片段、却完全缺少必需片段的案例；旧文与当前文仍可能共存。Book 和 10 个有评分的外部配置，都会为 8 个缺证据问题返回相关上下文。重复维护文本、没有独立留出集、没有运行代码 LLM，均限制结果的适用范围；本题集未验证校准拒答或一般事实权威性。[完整结果与边界](docs/current-results.md)

## 性能

同一长期回放在每阶段测量 7 个 recall 查询与 2 条完整目录追读链，采用六轮平衡顺序，每个版本臂单独恢复同一份基线构建快照。每个查询／阶段／版本有 30 次冷结果缓存调用、90 次暖结果缓存调用；目录链各 30 次。“冷”只清除 recall 结果缓存，**没有清空 SQLite 或操作系统缓存**。单台托管 Linux 主机使用 Python 3.12、SQLite 3.45.1、AMD EPYC 7763。[协议、完整耗时和资源记录](benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-summary.md)

| 已测查询／阶段组 | v0.13 合并样本 p50 更低 | v0.13 合并样本 p50 更高 |
|---|---:|---:|
| 冷结果缓存 recall | 12/49 | **37/49** |
| 暖结果缓存 recall | 42/49 | **7/49** |
| 完整目录定位及原文追读 | **14/14** | 0/14 |

在十万页交错写入检查点，归档项目的当前查询由 **166.898 → 102.478 ms**，历史查询由 **133.222 → 67.912 ms**，归档项目目录链由 **159.154 → 26.707 ms**（合并样本 p50）。同时保留成本：最差冷 p50 增幅为 **56.4%**，对应 1024 页多来源查询；小库中的归档项目当前查询也**慢了 56.3%**。7 个暖缓存变慢组全部是多来源查询，虽然新版补齐了原先缺失的证据，其额外耗时仍如实计入。

目录和时间候选路线复用匹配工作，保留项目归属检查、来源 ID 与排序。小项目成员集合可以避开没有筛选价值的 rowid 区间，为其他范围和 SQLite 限制保留回退。**冷缓存召回仍随归档规模增长。** 候选返回数量有上限、设置精确项目过滤，都不能证明全部数据库扫描或[全库 BM25 统计](https://www.sqlite.org/fts5.html#the_bm25_function)有固定上界。恢复快照、打开数据库、评分和记录响应不在查询计时内；这些是 API 耗时，不是代码 LLM 或工程任务端到端耗时。

可选 C 后端保留完整 Python 参考实现。此前 [v0.10 语义／目录实验](docs/comprehensive-v010-validation.md) 和[原生核心实验](docs/native-core-validation.md) 的原始耗时、成本与变慢项仍保留；这些历史提速不转记为 v0.13 收益，也不与本轮相加。

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

自编的 8 项目目录工作负载在 Python 和 native 两个后端分别复测：每后端通过 **119 项契约检查**，实际执行 **130 次定位、161 次原文页读取**，覆盖 **80 个不同页面**。原协议修正与所有尝试均保留；这不是回答准确率或速度测量。[最终 v0.13 回放与来源审计](benchmarks/reports/v0.13-development/legacy-gates-integrated/91412b43-attempt1/summary.json)

### 当前证据、历史与不确定性

`temporal=auto` 根据明确的当前／历史线索选择顺序；`current` 请求当前状态排序，`relevance` 保留相关性顺序。当前与历史线索同时出现时，auto 保留相关性顺序；询问发生次数时保留事件，不把重复记录当成同一个事实。这不等于任意时间点的状态恢复器。

当前声明比较会认证原始来源，并核对声明本身的字段与环境。目录标题、另一个字段或 staging 句不能替 production 声明补足限定词。相同值的重复声明只在保守的全文检查下取得资格；明确未作新决定的报告可以让位给可比较的决定，但报告自身被询问的检查动作或清单结果仍保留为证据。未知语句、引用和撤销用语保持保守处理。

**62 题开发诊断**中，Python／native 在四种 auto 配置（1200／2400 字符 × 返回 1／5 条）上均达到 **38/38 个可回答问题首证据正确且完整**。另列的 **38 题诊断**在相同配置上达到 **32/32**。真实测量源码为 `4e4a8eb2`；每后端分别记录 496、304 个响应配置，不是这么多独立问题。另有**每后端 37 个控制均满足预期**，核对引用、撤销、字段／范围和独立报告事实；早期失败仍保留原文。[全部响应与独立审计](benchmarks/reports/v0.13-development/scale-correctness-review/development-review.json)

已经评估的当前问题，即使使用 MCP 精简输出，也会保留 `evidence_assessment` 和潜在冲突页面 ID。`potential_conflict` 表示检查过的候选中，最新等时、可比较的声明存在不同值，需要追读原文；`no_comparable_declaration` 表示该有限范围内没有建立可比较声明。它们不证明真值、权威性或整个归档不存在决定。相关性／历史、发生次数及跳过检索的路线可以是 `not_assessed`。部分纯自然语言字段和未识别句式仍有限制。[状态语义与已测边界](docs/current-results.md#current-declarations-and-bounded-assessment)

字符与精确 token 组装继续保护已认证的当前证据。最终 v0.13 源码在**每后端 482 个配置**中保留全部 **434 个已记录的当前证据存在结果**；另外 48 个仍是原预算不足控制。这是正确性检查，不是 482 个完整答案或新的速度结论。[最终回放](benchmarks/reports/v0.13-development/legacy-gates-integrated/91412b43-attempt1/summary.json)

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

## 源码验证与交付状态

冻结 v0.13 源码 `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc` 在 [CI 44331775791，attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44331775791) 中 **11/11 个任务全部通过**。其完整 Git tree 与本地测量的 `91412b43` 相同，[身份收据](benchmarks/reports/v0.13-development/postscale-sources/run2-source-equivalence.json) 保留两个真实提交号。MCP 任务发现 1719 项测试，通过 1705 项、跳过 14 项，失败／错误为零。这是源码验证，发布包和公开安装另行取证。[原始 CI 元数据与完整 MCP 日志](benchmarks/reports/v0.13-development/final-source-ci/review.json)

快速开始面向**发布后的 v0.13.0**；本文尚未声称它已通过新的原生发布矩阵和公开安装。当前已发布的 **v0.12.0** 保留独立[发布证明](benchmarks/reports/v0.12-publication/README.md)，其中记录 11 项成功 CI、覆盖五个平台和 CPython 3.10–3.15 的 30 个原生构建／安装组合、4245 次通过与 75 次允许的跳过、67 个独立下载校验的公开文件及真实公开 URL 安装成功。这些属于 v0.12 交付结果。[公开版本](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.12.0) · [v0.11 历史交付](benchmarks/reports/v0.11-publication/README.md)

继续使用 **schema 4**；原始来源／页面 ID 和 Unicode 坐标不变。将 `python` 替换成安装器打印的解释器路径，可核对实际版本和后端：

~~~bash
python -I -X utf8 -c "import memory_book; from memory_book._text_backend import BACKEND_NAME; print(memory_book.__version__, BACKEND_NAME)"
~~~

v0.13 发布后，兼容原生的平台预期打印 `0.13.0 native`；必须由真实发布工作流和公开安装证明核实这一结果。默认 `MEMORY_BOOK_TEXT_BACKEND=auto`；`python` 选择参考实现，`native` 要求扩展存在。[后端选择与源码构建](docs/deployment.md#native-backend-and-source-builds)

## 文档

| 想做什么 | 文档 |
|---|---|
| 核对本文图表、固定配置与原始数据 | [当前结果](docs/current-results.md) · [v0.13 验证](docs/v0.13.0-validation.md) · [v0.12 历史结果](docs/v0.12.0-readme-results.md) · [完整验证索引](docs/validation.md) |
| 接入现有客户端、开启采集 | [集成指南](docs/integrations.md) · [部署与升级](docs/deployment.md) |
| 让 AI 按需使用记忆、核对来源 | [使用指南](docs/agent-guide.md) · [工程示例](docs/engineering-workflows.md) |
| 控制 token 或启用本地语义候选 | [Token 预算](docs/token-budget.md) · [语义检索](docs/semantic-retrieval.md) |
| 比较更多开源项目的架构与用途 | [开源方案对比](docs/open-source-memory-comparison.md) |
| 参与开发 | [贡献指南](CONTRIBUTING.md) |

运行 `memory-book serve` 可在 [127.0.0.1:8765](http://127.0.0.1:8765) 查看归档。数据保存在本地且未加密；召回的证据会进入所用客户端的模型上下文。[数据位置与维护](docs/deployment.md#data-and-configuration-paths)

独立实现，采用 [MIT 许可证](LICENSE)。[当前发布版](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.12.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)
