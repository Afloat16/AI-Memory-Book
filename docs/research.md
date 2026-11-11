# 设计参考与证据边界

查阅日期：2026-11-11。本文描述 v0.2.0 的设计依据，来自官方仓库、官方文档和论文，没有运行这些项目进行性能对比，没有复制其代码。上游分支与客户端配置会独立演进；链接是核查入口，不是永久兼容承诺。

用户提及的 `claude_mem`、`billion-contex` 分别按 `thedotmack/claude-mem`、`ranxianglei/billion-context` 理解。`ai-memory` 名称有歧义，这里选择与跨厂商编程会话记忆语境匹配的 `akitaonrails/ai-memory`；这不是对所有同名项目的判断。

## claude-mem

[官方检索架构](https://github.com/thedotmack/claude-mem/blob/main/docs/public/architecture/search-architecture.mdx) 将搜索组织为 `search → timeline → get_observations`，先取小索引，再取时间上下文，最后取完整观察。这是为了渐进读取和控制 token，并不意味着该设计本身错误。

对本项目的启发是区分数据库耗时与工具往返耗时。官方也描述了典型 FTS 查询的毫秒级性能，因此不能把新项目的本地 SQLite 毫秒数直接与另一个系统的完整代理等待时间比较。AI-Memory-Book 选择默认一次 recall 返回预算内证据，目录和原文展开仍然可用。

## billion-context

[官方仓库](https://github.com/ranxianglei/billion-context) 主要面向长单会话的增量上下文压缩与恢复，而非完整的跨项目长期知识库。README 明确区分“压缩发给模型的请求”与“缩小宿主自己的历史文件”：前者不会自动完成后者，超长宿主历史仍有处理成本。

对本项目的启发是把长期记忆放入独立索引，并保留可回到原文的引用。AI-Memory-Book 不代理模型网络请求，不改写宿主上下文窗口，也不声称具有 billion-context 的可逆上下文压缩能力。

## ai-memory

[官方架构](https://github.com/akitaonrails/ai-memory/blob/main/docs/ARCHITECTURE.md) 已提供项目/会话、版本化 Markdown wiki、原始观察、分层 brief，以及词法、实体、图和可选向量等检索路径。默认工作流中的若干能力不要求 LLM。

因此，“现有工具不支持层级记忆”并不准确。本项目选择的差异是较小的部署面、可寻址问答页、直接证据召回、明确字符预算，以及能复现失败案例的粒度实验；不把目录或零模型检索宣传为独有创新。

## PageIndex 与 RAPTOR

[PageIndex](https://github.com/VectifyAI/PageIndex) 展示了以树索引和页面定位组织文档的方式。书目录的路径和页地址有助于解释为什么选中某段资料，但在每层调用模型进行路由并不是低延迟的必然路径。

[RAPTOR 论文](https://arxiv.org/html/2401.18059v1) 比较过逐层遍历与将不同层节点一起检索的 collapsed-tree 方法。这支持一个设计问题：**存储是层级的，查询是否也必须逐层执行？** 本项目选择直接查候选页并保留章节信息；这只是设计借鉴，不能把论文在其他数据集上的收益当成本项目的实测结果。

## 采用的取舍

v0.2 保留 v0.1 的检索取舍，并补充显式客户端配置和后台采集。目录结构与接入便利性是两个需要分别验证的维度。

| 问题 | 当前选择 | 代价 |
|---|---|---|
| 每次查询先读目录吗 | 不要求，直接返回页证据 | 模糊问题仍可能需要再次检索 |
| 跨会话任务怎样连接 | 明确 task_id | 需要调用端提供或手工整理 |
| 原文与摘要谁是事实依据 | 原文，摘要只作目录概览 | 存储体积高于仅保存摘要 |
| 默认是否调用模型 | 不调用 | 语义改写和关系推理能力有限 |
| 目录是否硬裁剪分支 | 不硬裁剪 | 不承诺树搜索带来的复杂度下降 |
| 历史矛盾怎样处理 | 展示来源/时间，不自动裁决 | 最新结论仍需解释与核对 |
| 如何减少日常手工导入 | 用户选择来源后，后台按文件元数据/哈希增量同步 | 首次归档、扫描大量目录和整会话替换仍有成本 |
| MCP 接入是否等于原生采集 | 分开配置和声明兼容性 | 某些客户端可检索记忆，但须手工导出后导入 |
| 后台进程怎样启动 | 可选当前用户登录服务，或用户自己的 supervisor | 依赖可用的本机用户服务管理器 |
| 容器怎样部署 | 持久卷、内部显式绑定、宿主 loopback 发布 | 不提供公网身份认证和多用户访问控制 |

## v0.2 的接入与部署设计

本项目用一个 `setup` 入口生成客户端配置，但具体写入仍遵循各宿主的配置格式。MCP stdio 是宿主启动本地工具进程的接口，不是读取宿主全部聊天记录的通行协议；[MCP 本地服务说明](https://modelcontextprotocol.io/docs/develop/connect-local-servers)、[Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)和 [Codex MCP 文档](https://developers.openai.com/codex/mcp/)分别说明了对应连接方式。DeepSeek 等模型/供应商名称也不等于一个确定的 MCP 配置文件位置，应选择实际运行它的客户端。

本项目的安装、MCP 配置、采集授权、后台启动是四个独立操作。安装器准备隔离 Python 环境；`setup` 为选定客户端合并配置；`--capture` 明确启用展示路径中的已有和未来会话读取；`--background` 才安装并启动当前用户服务。客户端配置更新提供 dry run、备份和写前冲突检查，不修改宿主的工具权限策略。运行期间 daemon 加载来源配置变化；缩小范围或配置失效会停止原采集范围。状态 manifest 绑定数据库路径和 generation，避免换数据库后误判“已经同步”。这些是本仓库实现的行为，详见[架构](architecture.md)和[安全边界](../SECURITY.md)。

这套实现采用本地文件轮询与按需 MCP 检索。它没有复制其他项目的会话 hooks、模型请求代理、自动观察模型或会话开始时的提示注入。是否“无感”需要在真实客户端、真实历史规模和操作系统登录环境中另行测量，不能从 SQLite 查询耗时推出。

## 原生会话格式的依据

格式适配与 MCP 配置分别维护。当前原生采集的验证范围如下：

| 来源 | 官方依据 | 本项目的实现范围 |
|---|---|---|
| Claude Code | [官方会话文档](https://code.claude.com/docs/en/sessions) | 选定项目历史中的已知 JSONL 文本消息；内部格式变化可能需要适配 |
| Codex | [官方开源实现](https://github.com/openai/codex/tree/main/codex-rs) | rollout JSONL 的消息记录；避免把同一输出的事件通知再导入一遍 |
| Gemini CLI | [记录类型](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingTypes.ts)、[重放实现](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts) | 旧 ConversationRecord JSON 与当前 append-only JSONL；先重放 `$set`、`$patch` 和 `$rewindTo`，再提取可见用户/助手文本 |
| 旧版 Python Kimi | [context 实现](https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/soul/context.py)、[Kosong 消息类型](https://github.com/MoonshotAI/kimi-cli/blob/main/packages/kosong/src/kosong/message.py) | 活动 `context.jsonl` 中的文本；跳过特殊系统/用量/checkpoint 记录及 think 内容，不读取轮转备份 |
| 当前 Kimi Code | [当前数据位置](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/data-locations.html)、[迁移说明](https://www.kimi.com/en/help/kimi-code/cli-migration) | MCP 配置接入；未声明原生历史采集支持 |

Gemini 的追加日志不能简单把每行用户/助手文本串起来：撤销、替换、删除和顺序调整都影响最终会话。适配器重放这些操作，并用可复现的构造样本检查语义。旧版 Kimi 的活动文件会在回退/清空时重写，因此轮询使用内容哈希和整会话替换，而非假定所有文件永久只追加。

当前 Kimi Code 默认数据根为 `~/.kimi-code`，旧版 Python CLI 使用 `~/.kimi`。当前官方文档说明 `session_index.jsonl` 中的会话/目录元数据，却不足以证明正文文件的结构。把这个索引或旧版适配器直接当作新版会话兼容会产生错误声明，因此当前 Kimi 仅列 MCP 能力。以上测试证明适配器对给定格式样本的行为，不是每个厂商客户端的交互式端到端验证。

## 已发表测量：仅限 v0.1 检索实验

[完整实验记录](../benchmarks/EXPERIMENTS.md)和其中的压缩逐查询报告保留了原始源代码哈希、语料、预算和测量参数。v0.2 继续引用它们作为历史证据，没有以新版本名称重报旧计时。对照是本项目内部的三种分节与两种排序策略，共用词法检索器、摘录算法、过滤和预算；并非与上述外部项目比较。

两个 heldout 合成 seed 各有 112 会话、1,408 次用户提问、168 个查询和约 114.3 万原文字符。在 8,000 字符预算下，adaptive 的证据召回率为 77.27%、完整证据率为 78.95%，未启用结果缓存的本地 p95 为 7.42–7.46 ms。该区间是两个 seed 的观测值，不是置信区间；计时保留 SQLite/操作系统页缓存，排除进程启动、MCP、网络、模型和后台采集开销。页上限 900 是在开发 seed 11 比较 900/1800/3600 后选定，heldout seed 29/47 未用于这个参数选择。

失败同样保留：目录重排序没有提升 aggregate 召回；低词面重叠改写召回为零；同一长会话远处双事实查询只召回 25% 必要证据，没有完整取回两个事实；2,000 字符预算也没有普遍优势。开发集到 heldout 的明显下降说明合成模板仍可能造成乐观估计。whole-session 基线已允许查询居中摘录，但每个检索单元只返回一个窗口；未测量的多窗口实现可能缩小差距。

因此 v0.2 可声明的是增加了安装、采集和客户端配置能力。真实用户历史下的检索质量、后台 CPU/内存与首轮归档时间、多客户端自动调用频率、登录服务在不同机器上的可靠性，仍需要独立实测；有界合成采集样本的验证也不能直接替代这些结果。新增功能的验证范围另见[验证记录](validation.md)。原始会话和缓存也仍是未加密本地文件，元数据日志不意味着正文被脱敏。

## 许可证处理

只参考公开设计，代码独立实现。各上游许可证应以其当前仓库文件为准，本仓库的 MIT 不意味着上游许可证相同，也不替代复用上游代码时的义务。特别是 billion-context 的 LICENSE 包含额外的产品表面出处要求；本项目没有包含其软件。

上述检索实测仅比较自身引擎的分节/排序配置。未声称超越 claude-mem、billion-context、ai-memory、PageIndex 或论文系统。
