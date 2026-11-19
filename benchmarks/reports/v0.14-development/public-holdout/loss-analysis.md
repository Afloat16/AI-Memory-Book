# v0.14 公开源码保留集：15 个退化配置的只读归因

**结论：当前 project-local ranking 不应升级为默认模式。** 冻结的逐题无退化门槛仍未通过：每个 backend 有 12 个首来源退化配置和 3 个新丢失必要证据的配置。candidate_global 的 216 个配置与 v0.13 baseline 的分数逐项一致。应保留 global 默认；project 最多维持明确标注质量边界的实验性显式选项。

本报告仅分析已保存的 raw responses、原页跟读、frozen provenance、比较报告和 ingestion receipts。新增 recall 为 **0**，新增 source-page API 读取为 **0**，未修改 runtime、evaluator、source、gold 或协议。所有分类都是事后描述，不改变原有验收和评分。

## 1. 结果、重复次数与收益/损失同时报告

| 每 backend、每运行配置 | 完整证据 | 必要 spans | 预期首来源 |
|---|---:|---:|---:|
| baseline_global | 125 / 192 | 200 / 288 | 66 / 120 |
| candidate_global | 125 / 192 | 200 / 288 | 66 / 120 |
| candidate_project | 126 / 192 | 204 / 288 | 80 / 120 |

完整证据的净增 1 来自 **4 个改善、3 个退化**；必要 spans 的净增 4 来自 **7 个恢复、3 个丢失**；首来源净增 14 来自 **26 个改善、12 个退化**。因此，aggregate 增加不能作为逐题无退化通过的替代。

15 个退化配置只涉及 **6 个不同 query IDs、4 个工程**。Python/native 两后端重复观察到相同 15 个配置，合计 30 个失败观测，但不是 30 个独立失败问题。本次还直接比较了每配置的 216 对保存结果：三个配置合计 **648 对** context、results、原页、冲突页及 score 完全一致；没有把运行耗时或 project 准备耗时列入这个相等结论。

| 分布 | 退化配置数 / backend |
|---|---:|
| Requests | 6 |
| Werkzeug | 4 |
| Flask | 2 |
| HTTPX | 3 |
| turn / adaptive / session | 4 / 7 / 4 |
| 1,200 / 2,400 字符 | 8 / 7 |

十份输入文件在两个对比配置中均真实 ingest：turn 为 10 页、adaptive 为 36 页、session 为 10 页。turn/session 在此单文件单 turn 输入中是相同页面分组的接口复核，不能当作独立语义样本。

来源：[首次比较](python-baseline-global-vs-candidate-project-stdout.json)、[默认兼容比较](python-baseline-global-vs-candidate-global-stdout.json)、[完整结构化归因](loss-analysis.json)。

## 2. 15 个配置逐项登记

| # | 模式 | 预算 | Query ID | 新丢 span 数 | 退化机制 |
|---:|---|---:|---|---:|---|
| 1 | turn | 1200 | `psf--requests:older-secondary` | 0 | 首来源顺序变化 |
| 2 | turn | 1200 | `pallets--werkzeug:older-secondary` | 0 | 首来源顺序变化 |
| 3 | turn | 2400 | `psf--requests:older-secondary` | 0 | 首来源顺序变化 |
| 4 | turn | 2400 | `pallets--werkzeug:older-secondary` | 0 | 首来源顺序变化 |
| 5 | adaptive | 1200 | `psf--requests:older-python` | 1 | gold 页退出返回 top-5 |
| 6 | adaptive | 1200 | `pallets--flask:newer-additional` | 0 | 首来源顺序变化 |
| 7 | adaptive | 1200 | `encode--httpx:newer-python` | 0 | 首来源顺序变化 |
| 8 | adaptive | 1200 | `encode--httpx:secondary-change` | 1 | 已返回 gold 页的摘录移开 |
| 9 | adaptive | 2400 | `psf--requests:older-python` | 1 | gold 页退出返回 top-5 |
| 10 | adaptive | 2400 | `pallets--flask:newer-additional` | 0 | 首来源顺序变化 |
| 11 | adaptive | 2400 | `encode--httpx:newer-python` | 0 | 首来源顺序变化 |
| 12 | session | 1200 | `psf--requests:older-secondary` | 0 | 首来源顺序变化 |
| 13 | session | 1200 | `pallets--werkzeug:older-secondary` | 0 | 首来源顺序变化 |
| 14 | session | 2400 | `psf--requests:older-secondary` | 0 | 首来源顺序变化 |
| 15 | session | 2400 | `pallets--werkzeug:older-secondary` | 0 | 首来源顺序变化 |

## 3. 四个 query 的 12 个首来源退化：证据保留与首位顺序分开判断

| Query ID | 配置 | 预期源的返回排名变化 | 完整性影响 |
|---|---|---|---|
| `psf--requests:older-secondary` | turn/session × 两预算，共 4 个 | 旧版 setup.py：1 → 2；新版取代首位 | 四个均仍完整 |
| `pallets--werkzeug:older-secondary` | turn/session × 两预算，共 4 个 | 旧版 setup.py：1 → 3；新版 pyproject.toml 取代首位 | 四个均仍完整 |
| `pallets--flask:newer-additional` | adaptive × 两预算，共 2 个 | 新版 pyproject.toml：1 → 2；旧版 setup.py 取代首位 | 两个均仍完整 |
| `encode--httpx:newer-python` | adaptive × 两预算，共 2 个 | 新版原文件：首位 → 最早 rank 2；旧版取代首位 | baseline 和 project 都已缺少所需字段，不能称为新增完整性损失 |

前八个 turn/session 配置中，返回的 page ID 集合完全相同，要求的原文也仍在 context 内，属于明确可见的排序变化。Flask 的 gold 页保留、HTTPX 的新版文件仍有页面被返回，但 adaptive 的其他返回页面还发生了替换。历史问题有“新版压过指定旧版”，新版本问题也有“旧版压过指定新版”；仅按时间新旧整体加权无法同时处理两种要求。

这些顺序改变确实违反已冻结的 first-source 条件，不能因为十个配置仍有完整证据就删掉失败；另一方面，它们也不能全部被描述成“答案证据丢了”。对于 HTTPX newer-python，正确首来源只代表选对文件版本，本来就未代表选中了含字段的那一页。

## 4. Requests：两预算下，含 gold 的 adaptive 页被挤出返回 top-5

涉及 `psf--requests:older-python`，adaptive / 1,200 与 2,400 字符。baseline 的第 5 页为 `p_ca3d05a11f217c06967f1975`，其原始 turn 区间为 `[2104, 2963)`；该页包含被冻结的旧版 Python 要求，且原文进入两个预算的 context。project 保持前四个返回 page IDs，却把第 5 页换成 `p_44b15c88936c6935e65768b4`，其区间为 `[856, 1592)`，不含 gold。

两个 arm 的 `candidate_count` 都为 11，返回条数都为 5；旧版 setup.py 仍有其他页被返回。被移出的 gold 页还出现在其他 **10 个已保存的 candidate_project query 配置**的原页跟读中，证明它不是这份候选 archive 中消失的原始数据。

**可以确认的阶段是“gold-bearing 页未进入最终返回 top-5”**，不能确认它是否在某个更早的内部候选池被剔除，因为日志只保存了总 candidate_count，没有保存完整候选身份和截断前排名。因而本报告不把这两项误称为已证明的 preselection candidate miss，也不把它归为裁剪已返回页造成的损失。提高现有字符预算并未修复这两项，因为同一必要页仍未返回。

## 5. HTTPX：必要页仍在 rank 2，但摘录移开了字段

涉及 `encode--httpx:secondary-change`，adaptive / 1,200 字符。两 arm 都返回同一新版页 `p_b844af4b48807ddbcc71a85e`，始终位于 rank 2，其原文长度均为 843 字符。gold 在该页 `[121, 136)`。baseline 摘录窗口 `[85, 203)` 覆盖它；project 改为 `[444, 579)`，不再覆盖。摘录长度从 **120 → 137** 字符，整体 context 都为 **1,198** 字符，因此不是“少给了几个字符”这一单一原因。

输出层面的直接原因是 **已返回页的摘录窗口选择/字符分配发生变化**。其余返回页面集合也变化，可能影响了预算分配；仅凭保存响应不能进一步证明内部哪一个窗口打分项或分配步骤造成跳转。

原先已执行的 2,400 字符控制也必须保留：baseline 的同题完整性反而从 1,200 时完整变为不完整，新版页窗口为 `[422, 843)`；project 为 `[444, 819)`，同样遗漏该 gold。更大预算不是已观察到的修复，且 baseline 自身就存在预算增加却丢证据的现象。这是后续可以独立研究的通用 packing 问题，不能只归罪于 project ranking。

## 6. 分段、源正确性和可观测性的边界

- 三个新增的证据完整性损失都出现在 adaptive，说明此数据中局部排名与多页选择、摘录分配的相互作用值得重点研究。并不意味着 adaptive 的原始切分数据发生破坏。
- 全部 15 个退化配置的必要原始文件仍至少有一页被返回；没有整份必要 source 文件消失的记录。Requests 的关键区别是同一文件的含答案页与其他页不能互相替代。
- 首次完整审计记录仍为零 source-coordinate、project-isolation、预算或 API 错误。所有候选 project 请求真实走 project 路径，没有 global fallback。
- project/global 的 reported score 来自不同统计范围，不是可直接比较的置信度。观察到排序及 score 改变支持“检索策略发生改变”，不支持仅凭数值解释具体 BM25 分量或因果机制。
- 四个缺失字段问题在每配置/backend 的 24 次重复中都返回相关 context；本分析没有把返回 context 判成新增源错误，也没有把任何空结果当作已证明的可靠拒答。

## 7. 下一步方向：先泛化问题定义，再冻结新的评估

1. **继续拒绝把 project 模式改成默认。** 保留 global 的既有兼容结果；性能大实验的结果应独立报告，不能抵消预注册质量门槛失败。若保留 project，只能作为明确标注策略改变和实测回退的实验性选择。
2. **把明确版本/来源选择与新旧时间偏好分开处理。** 在新的开发集上测试可验证的 version/tag 元数据约束和不明确选择的保守处理，不加入这些仓库、版本或 gold 值的特例。历史问题与当前快照问题都需要覆盖。
3. **分开度量候选召回、最终页面覆盖与实际 context 覆盖。** 后续新实验应记录有界候选 IDs/排序、最终页面选择及 field/facet 覆盖；研究 source/page 层面的多样性或覆盖约束，避免“选对文件，但五页全没字段”。不通过悄悄扩大 top-k 或预算改写本轮结果。
4. **研究完整配置绑定和预算变化下的证据保留。** 使用新的 TOML/INI/Python/JSON 配置素材，对同一候选页在预算变化时的完整字段绑定保留建立通用控制；继续验证原始 offsets 和总字符预算。不要针对本题择优取某个窗口或预算。
5. **将计算加速与排名语义选择分别验收。** 一条路线可以追求相同 global 排序下减少无关工作；另一条可以把 project-local 作为独立策略，要求新的泛化证据。不能把不同 corpus statistics 带来的排名变化全部宣传成纯性能优化。

这些方向尚未实施、未运行新检索，也未被新实验验证。此时的失败分析一旦用于后续调参，本数据对于新候选就转为 development；必须另选未查看结果的公开来源/问题并重新冻结 holdout，才能作新的独立泛化结论。原 candidate 的首次 holdout 结果永久保留。

## 8. 证据定位

- [原始 Python baseline 记录](python-baseline-global-attempt1/raw.jsonl.gz)
- [原始 Python project 记录](python-candidate-project-attempt1/raw.jsonl.gz)
- [原始 native project 记录](native-candidate-project-attempt1/raw.jsonl.gz)
- [Python 完整比较及 15 项原判定](python-baseline-global-vs-candidate-project-stdout.json)
- [native 完整比较](native-baseline-global-vs-candidate-project-stdout.json)
- [冻结来源、原文件和 gold provenance](python-baseline-global-attempt1/frozen-provenance.json)
- [机器可读完整归因、逐页坐标与输入 SHA-256](loss-analysis.json)

基线 `861b7f35ac2557024d89bc51d5b3017ca35cb9d0`；候选及协议 `ad8f9e8095e465fff83415057cc3428e44b73c59`。本报告没有执行任何新 API 测量；公开配置片段检索不能等同真实工程会话、完整产品使用或 coding-LLM 任务成功。
