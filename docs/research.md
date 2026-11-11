# 设计参考与证据边界

查阅日期：2026-11-11。本文来自官方仓库、官方文档和论文，没有运行这些项目进行性能对比，没有复制其代码。

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

| 问题 | v0.1 选择 | 代价 |
|---|---|---|
| 每次查询先读目录吗 | 不要求，直接返回页证据 | 模糊问题仍可能需要再次检索 |
| 跨会话任务怎样连接 | 明确 task_id | 需要调用端提供或手工整理 |
| 原文与摘要谁是事实依据 | 原文，摘要只作目录概览 | 存储体积高于仅保存摘要 |
| 默认是否调用模型 | 不调用 | 语义改写和关系推理能力有限 |
| 目录是否硬裁剪分支 | 不硬裁剪 | 不承诺树搜索带来的复杂度下降 |
| 历史矛盾怎样处理 | 展示来源/时间，不自动裁决 | 最新结论仍需解释与核对 |

## 许可证处理

只参考公开设计，代码独立实现。各上游许可证应以其当前仓库文件为准，本仓库的 MIT 不意味着上游许可证相同，也不替代复用上游代码时的义务。特别是 billion-context 的 LICENSE 包含额外的产品表面出处要求；本项目没有包含其软件。

本项目实测仅比较自身引擎的分节/排序配置。未声称超越 claude-mem、billion-context、ai-memory、PageIndex 或论文系统。
