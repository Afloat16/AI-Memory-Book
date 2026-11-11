"""Mixed-topic long conversations for the v2 synthetic evaluation corpus.

Each project gets two 64-question engineering journals, not a single repeated
filler passage. Domain-specific procedures, code, constraints and numerical
decisions recur across projects to create realistic lexical distractors. The
labels still describe authored synthetic facts, not external ground truth.
"""

from __future__ import annotations

import random

from .data import Dataset, Evidence, QueryCase


# Each tuple is an independent operational topic, not wording generated from the
# answer labels. Values and resource names vary by project, journal and turn.
# Code samples deliberately share common engineering vocabulary across topics.
TOPICS = [
    {
        "key": "webhook",
        "en_question": "How should signed webhook delivery recover after repeated failures?",
        "zh_question": "签名Webhook多次投递失败后如何恢复？",
        "en": "The receiver can acknowledge an event before its downstream transaction finishes, so delivery status and business completion must be tracked separately. Persist the event identifier and the recipient response in the delivery ledger. A retry keeps the original signature timestamp inside the audit envelope and creates a new transport timestamp.\n\nUse a recovery inbox for exhausted deliveries. Operators inspect the recipient health, compare the idempotency key, and explicitly replay an event only after the downstream owner confirms recovery. A replay must not create a second invoice or silently erase the earlier failure history.",
        "zh": "接收端可能在下游业务事务完成前确认事件，因此必须分别记录投递状态和业务完成状态。把事件标识、接收端响应和幂等键写入投递台账；重试保留审计信封里的原始签名时间，并生成新的传输时间。不能仅凭一次成功HTTP响应就认定订单已经处理完毕。\n\n耗尽重试的事件进入恢复收件箱。值班人员先检查接收端健康状态、比较幂等键，再等待下游负责人确认恢复后显式重放。重放不得生成第二张发票，也不能覆盖之前的失败记录。恢复结论必须附上工单和验证结果，以便后续值班人员复核。",
        "code": "delivery.retry(event_id, idempotency_key=record.key, backoff='exponential')",
    },
    {
        "key": "backup",
        "en_question": "What retention and restore checks should production backups use?",
        "zh_question": "生产备份如何保留，以及怎样验证可以恢复？",
        "en": "A completed upload is not proof of a usable backup. Record the database checkpoint, object checksum and encryption-key version in a manifest, and verify that the manifest reaches a different failure domain. Restore tests use a disposable database and compare row counts with a known checkpoint.\n\nWhen retention expires, remove only backups whose replacement has already passed verification. Legal holds are evaluated before deletion. Restore access is limited to the recovery role; the application runtime must not be able to delete its own backup history. Track recovery duration independently from archive upload throughput.",
        "zh": "上传完成不代表备份能够恢复。清单必须记录数据库检查点、对象校验值和加密密钥版本，并确认清单存放在另一个故障域中。恢复演练使用临时数据库，对照已知检查点核对记录数量，同时检查约束、索引和关键查询结果。不能只验证压缩文件可以解开。\n\n保留周期到期时，只删除已有验证通过替代品的备份；删除前还要检查法律保留标记。恢复权限限制在专用角色，应用运行时不能删除自己的备份历史。恢复耗时和上传吞吐量分开记录，避免上传很快却恢复过慢的问题被掩盖。",
        "code": "backup.verify(manifest, restore_target='isolated-recovery', check_constraints=True)",
    },
    {
        "key": "schema",
        "en_question": "How can the customer schema change while old application versions remain live?",
        "zh_question": "旧版本应用还在线时，客户表结构怎样迁移？",
        "en": "Use an expand-and-contract migration. Add the nullable field first, deploy readers that understand both shapes, and backfill in bounded batches. Progress is stored by primary-key range so an interrupted migration resumes without rescanning the entire table. Reject a deployment that drops a field still used by an active reader.\n\nA migration dashboard shows lock time, replication delay and remaining rows. If replica delay rises, pause new batches without rolling back completed work. After the observation period, check read telemetry before making the new column mandatory. The removal step has its own release and rollback notes.",
        "zh": "采用先扩展再收缩的迁移方式：先增加可空字段，部署同时理解新旧结构的读取逻辑，然后按主键范围分批补齐数据。进度持久化到迁移记录，中断后可以从已完成范围继续，避免重新扫描整张表。仍有旧读取者使用的字段不得在当前发布中删除。\n\n迁移面板同时显示锁等待、复制延迟和剩余记录数。副本延迟升高时暂停新批次，不撤销已经完成的部分。观察期结束后核对读取遥测，再把新字段设为必填；删除旧字段需要独立发布记录和回滚说明。",
        "code": "migrate.range(table='customers', after=checkpoint, batch_size=250, lock_timeout_ms=300)",
    },
    {
        "key": "search",
        "en_question": "How should search indexing handle documents that change during a rebuild?",
        "zh_question": "搜索索引重建期间文档继续变化，该怎样处理？",
        "en": "Rebuild into a new index generation while the existing generation serves traffic. Each indexed document stores its source revision, and the change stream replays revisions newer than the snapshot checkpoint. The cutover waits until the new generation has consumed the current watermark.\n\nCompare representative queries before moving the read alias. Deleted documents require tombstones during replay; omitting them resurrects content that users removed. Keep the previous generation available for rollback until both freshness and query latency have remained stable. A failed rebuild should not block writes to the source database.",
        "zh": "重建时写入新的索引代次，现有代次继续承担读流量。每个文档记录来源版本，变更流负责重放快照检查点之后的修订。新索引追到当前水位后才能切换读取别名，切换前要比较代表性查询、权限过滤和排序结果。\n\n删除操作必须在重放过程中保留墓碑标记，否则用户已删除的内容可能重新出现。旧索引保留到新鲜度和查询延迟均稳定，便于必要时回滚。重建失败不能阻止源数据库继续接受写入，检查点也必须可以重试而不重复发布文档。",
        "code": "search.rebuild(generation='next', checkpoint=source.revision, preserve_tombstones=True)",
    },
    {
        "key": "quota",
        "en_question": "How should tenant quota enforcement behave during a traffic burst?",
        "zh_question": "租户突然出现流量峰值时，配额限制应该怎样工作？",
        "en": "Enforce the tenant budget at the shared admission layer rather than separately inside each worker. Reserve capacity before starting expensive work and release the reservation when the operation completes or its lease expires. A missing release must not permanently consume the customer's quota.\n\nReturn a retry delay with quota rejections and expose the remaining allowance in the management console. Administrative overrides have an expiry time and an audit reason. Measure rejected demand separately from successful throughput so capacity planning can see customers whose workload is currently suppressed by the limit.",
        "zh": "在共享准入层统一执行租户配额，不能让每个工作进程分别计算自己的额度。昂贵操作开始前先预留容量，结束或租约到期时释放。进程崩溃造成的释放遗漏不得永久占用客户配额；恢复逻辑应可以识别已经失效的预留记录。\n\n拒绝请求时返回建议重试时间，管理界面显示剩余额度。管理员临时覆盖必须有到期时间和审计原因。被拒绝的需求量与成功吞吐量分开统计，容量规划才能看见被限制压住的真实工作量，而不是把低吞吐误判为低需求。",
        "code": "admission.reserve(tenant_id, units=cost, lease_seconds=60, reason='interactive-request')",
    },
    {
        "key": "timezone",
        "en_question": "How should scheduled reports handle daylight-saving changes?",
        "zh_question": "定时报告遇到夏令时切换时，应该怎样安排？",
        "en": "Store the user's named time zone and intended wall-clock schedule, not only the next UTC timestamp. During a skipped local hour, move the occurrence to the next valid local instant. During a repeated hour, choose one occurrence and persist the selection so a scheduler restart cannot send the report twice.\n\nRecord both the displayed local time and resolved UTC instant in the job history. If the user changes time zones, reschedule future jobs without rewriting completed history. Tests cover spring gaps, autumn overlaps and zones that have abolished daylight-saving changes. The scheduler should use an injectable clock for repeatable verification.",
        "zh": "保存用户选择的时区名称和本地墙上时间规则，不能只保存下一次UTC时间戳。遇到不存在的本地时刻时，移到下一个有效时刻；遇到重复出现的小时，只选择其中一次，并把选择持久化，防止调度器重启后重复发送报告。\n\n任务历史同时记录展示的本地时间和解析后的UTC时刻。用户更换时区时，只重新安排未来任务，不重写已完成历史。测试覆盖春季跳时、秋季重复小时和取消夏令时的地区；通过可注入时钟验证，而不依赖真实等待。",
        "code": "schedule.resolve(zone=user.timezone, gap='next-valid', overlap='first-once')",
    },
    {
        "key": "attachment",
        "en_question": "How are uploaded attachments checked before becoming downloadable?",
        "zh_question": "上传附件在可以下载之前要经过哪些检查？",
        "en": "New objects enter a private quarantine bucket. Validate the declared size against the received stream, inspect file signatures instead of trusting extensions, and scan the object before publishing a download reference. The scanner records its engine version and verdict so a later re-scan can be explained.\n\nA failed or timed-out scan leaves the attachment unavailable with a retryable state. Never expose a public object URL while a verdict is pending. Metadata changes do not bypass the scan gate. Large-file processing uses bounded temporary storage and cleans abandoned multipart uploads after the upload lease expires.",
        "zh": "新对象先进入私有隔离存储。校验声明大小与实际接收字节数，检查文件签名而不是相信扩展名，并在扫描完成后才生成下载引用。扫描记录包含引擎版本、结论和处理时间，后续重新扫描时能够解释为什么同一个文件得到了不同结果。\n\n扫描失败或超时后，附件保持不可下载且允许重试；等待结论期间不能暴露公开对象地址。修改文件名或元数据不能绕过检查。大文件处理必须限制临时存储占用，并在上传租约过期后清理遗留的分片上传。",
        "code": "attachments.publish(object_id, require_scan='clean', check_size=True, private_until_ready=True)",
    },
    {
        "key": "audit",
        "en_question": "Which audit events should survive a failed business transaction?",
        "zh_question": "业务事务失败后，哪些审计事件仍然需要保留？",
        "en": "Record attempted privileged operations separately from successful state changes. A transaction rollback must not erase evidence that an administrator tried to export data or change another user's permissions. Include actor, target, decision reason and correlation identifier, while excluding credentials and raw document contents.\n\nAudit delivery uses an outbox with a distinct failure alarm. Operators can see delivery lag, but application users cannot edit past records. Corrections are additional events linked to the original record. The retention policy distinguishes routine application diagnostics from records required for an access review.",
        "zh": "特权操作的尝试记录与成功状态变更分开保存。业务回滚不能抹去管理员尝试导出数据或修改他人权限的事实。事件包含操作者、目标、决策原因和关联标识，但不记录凭据或完整文档内容；错误堆栈中的敏感值也需要清理。\n\n审计投递使用发件箱，并设置独立的失败告警。运维可以查看投递延迟，普通应用用户不能修改过去记录；纠错通过追加关联事件实现。保留策略区分日常诊断日志和访问审查所需记录，避免把两者混为一个无法解释的清理规则。",
        "code": "audit.append(actor=principal.id, action='export-attempt', outcome=decision, immutable=True)",
    },
    {
        "key": "billing",
        "en_question": "How do usage counters avoid charging twice after an ingestion retry?",
        "zh_question": "用量计数在重复导入后怎样避免重复收费？",
        "en": "Every metering event carries a stable producer identifier and a unique sequence number. Deduplicate before applying the quantity to the account ledger. Corrections are signed adjustment events that reference the original charge rather than edits to a closed invoice. Late-arriving usage is assigned according to the published billing cutoff policy.\n\nReconcile raw accepted events against ledger totals each day. A mismatch blocks final invoice publication but does not prevent customers from using the service. Finance reviewers receive both the original quantity and correction reason. Keep customer-visible units consistent with the measurement units used by the producer.",
        "zh": "每条计量事件带有稳定的生产者标识和唯一序号，去重后才能把数量计入账户台账。纠错使用引用原收费项的签名调整事件，不直接修改已经结算的发票。延迟到达的用量按照事先公布的结算截点归属，不能临时改变规则而使客户无法复算。\n\n每天对账已接收原始事件与台账合计；不一致时阻止最终发票发布，但不影响客户继续使用服务。财务复核需要同时看到原始数量和调整理由。客户页面展示的计费单位必须与生产者实际记录的计量单位一致。",
        "code": "ledger.apply(event, dedupe_by=('producer', 'sequence'), corrections='append-only')",
    },
    {
        "key": "feature",
        "en_question": "How should a feature switch stay consistent across a user's requests?",
        "zh_question": "功能开关怎样在同一用户的多个请求之间保持一致？",
        "en": "Assign rollout cohorts using a stable account key and the switch version. Do not sample independently on each request, because a user could otherwise see incompatible screens within one workflow. Server decisions and client rendering receive the same assignment through the request context. A disabled switch must have a tested default path.\n\nChanging allocation records a new version while preserving the old assignment for active transactions. Monitoring compares error rate and completion rate by cohort. Expired experiments are removed after their decision is documented; leaving obsolete switches in the code makes future rollback behavior difficult to reason about.",
        "zh": "使用稳定账户键和开关版本分配发布分组，不能每次请求都独立抽样，否则用户可能在同一个流程中看到不兼容的界面。服务器决策和客户端渲染通过请求上下文接收同一分配结果。关闭开关后的默认路径必须经过验证，不能只测试实验开启的情况。\n\n调整分配比例时记录新版本，同时为正在处理的事务保留原分组。监控按组比较错误率与流程完成率。实验结束后先记录结论，再清理过期开关；保留大量无效开关会让未来的回滚行为难以理解，也容易产生组合条件漏洞。",
        "code": "flags.assign(account_id, switch_version=revision, stable=True, propagate_context=True)",
    },
    {
        "key": "cdn",
        "en_question": "How do static assets become fresh after a tagged release?",
        "zh_question": "带标签的发布后，静态资源怎样及时更新？",
        "en": "Content-addressed asset filenames allow old and new application versions to coexist. The HTML entry point uses a short freshness window, while immutable asset objects can remain cached longer. A tagged release emits an invalidation event for mutable entry points and waits for the edge acknowledgement before declaring rollout complete.\n\nDo not purge every object for each deploy. Track the release manifest and remove only affected keys. Rollback restores the previous entry-point manifest without deleting the assets still used by open browser tabs. Monitoring samples several edge regions because a successful origin response does not prove every edge has refreshed.",
        "zh": "使用内容寻址的资源文件名，让新旧应用版本能够同时工作。HTML入口保持较短的新鲜度窗口，不可变资源则可以长期缓存。带标签的发布会为可变入口生成失效事件，并等待边缘节点确认后才宣布发布完成；不能把源站成功直接当作全网更新成功。\n\n每次部署不必清空所有对象，应该依据发布清单删除受影响的键。回滚恢复之前的入口清单，保留仍被打开浏览器标签页引用的资源。监控从多个边缘区域抽样，分别记录入口版本、资源校验值和失效确认时间。",
        "code": "cdn.invalidate(manifest.mutable_keys, wait_for_edges=True, preserve_immutable=True)",
    },
    {
        "key": "pool",
        "en_question": "How should database connections be shared during rolling deploys?",
        "zh_question": "滚动发布期间数据库连接池如何共享容量？",
        "en": "Size the connection pool against the maximum simultaneous old and new application replicas. A rolling deployment temporarily increases replica count, so multiplying the steady-state pool size by the ordinary replica count understates demand. Use bounded acquisition waits and expose queue depth separately from active query duration.\n\nLong transactions receive a distinct diagnostic rather than a larger global timeout. Drain connections before terminating a replica, and stop accepting new requests once draining starts. Capacity checks include maintenance clients and background jobs. A saturation alarm should identify the service consuming connections rather than only naming the database.",
        "zh": "按新旧应用副本同时存在时的最大数量计算连接池容量。滚动发布会暂时增加副本，仅把稳定状态池大小乘以平时副本数会低估需求。连接获取需要有界等待，等待队列深度与实际查询耗时分别展示，才能区分数据库慢和客户端争用。\n\n长事务单独诊断，不能靠增大全局超时掩盖。终止副本前先排空连接，进入排空状态后停止接受新请求。容量检查还包含维护客户端和后台任务；饱和告警应指出占用连接的服务，而不只是泛泛报告数据库异常。",
        "code": "pool.configure(max_connections=24, acquire_timeout_ms=800, drain_on_shutdown=True)",
    },
    {
        "key": "export",
        "en_question": "How should a customer export remain consistent while records change?",
        "zh_question": "导出客户数据时记录仍在变化，如何保证一致性？",
        "en": "Bind an export to a snapshot revision and record that revision in its manifest. Paginate by a stable key within the snapshot rather than by a mutable display sort order. The export worker writes chunks to private storage and publishes the manifest only after every chunk checksum has been verified.\n\nCancellation removes unpublished chunks without changing source records. A resumed export uses the same snapshot when it is still available; otherwise it starts a new revision and explains the restart. Download authorization is checked again when a link is used, because a user's access may have changed since the export was requested.",
        "zh": "导出绑定一个快照版本，并在清单中记录版本号。快照内按稳定键分页，不能依据会变化的展示排序分页。导出进程先把分片写入私有存储，逐个验证校验值后才发布总清单；部分失败时不得展示看似完整的下载结果。\n\n取消只清理尚未发布的分片，不改变原始记录。恢复导出时优先使用原快照，原快照不可用则开启新版本并解释重新开始的原因。下载链接被使用时仍需重新检查授权，因为用户权限可能在请求导出之后已经变化。",
        "code": "export.start(snapshot=database.revision, order_by='stable_id', recheck_download_acl=True)",
    },
    {
        "key": "lease",
        "en_question": "How does a distributed lease prevent an expired worker from writing?",
        "zh_question": "分布式租约怎样阻止已经过期的工作进程继续写入？",
        "en": "A lease timeout alone cannot stop a paused process from waking up and completing an old write. Issue a monotonically increasing fencing token when ownership changes, and make the storage layer reject tokens older than the latest accepted owner. Renewal failure causes the worker to stop accepting new work immediately.\n\nUse a bounded grace period only for operations that can be safely retried. Record ownership transitions and rejected stale writes in the job history. Tests pause a worker beyond lease expiry, transfer ownership, and then resume the old worker. Correctness must come from the fencing check, not from assuming clocks or process scheduling are perfect.",
        "zh": "仅靠租约超时无法阻止暂停进程恢复后完成旧写入。每次所有权变化都签发单调递增的隔离令牌，由存储层拒绝早于当前所有者的令牌。续租失败时工作进程立即停止接受新任务，不能继续依赖本地认为自己仍然持有锁的状态。\n\n只有能够安全重试的操作才允许有限宽限期。任务历史记录所有权转移和过期写入拒绝。测试应暂停进程直至租约失效，转移所有权后再恢复旧进程；正确性来自隔离检查，而不是假设时钟和进程调度永远准确。",
        "code": "storage.write(record, fencing_token=lease.epoch, reject_stale_owner=True)",
    },
    {
        "key": "notification",
        "en_question": "How should notification preferences apply to already queued messages?",
        "zh_question": "通知已进入队列后，用户修改偏好应怎样生效？",
        "en": "Evaluate communication preferences again at send time. A user who unsubscribed after an event was queued should not receive optional marketing mail merely because an earlier snapshot allowed it. Essential account alerts follow a separately documented policy and identify why they cannot be disabled.\n\nDeduplicate notifications by event and channel while preserving the delivery attempt history. A provider timeout is an unknown result, not proof of failure, so retries must account for possible earlier delivery. The preference audit records the selected categories and change time without storing message bodies or hidden tracking content.",
        "zh": "发送前重新检查通信偏好。用户在事件入队后退订，不能因为早期快照允许就继续发送可选营销邮件。必要账户告警适用单独说明的规则，并明确告知用户为何不能关闭；营销类别不得借必要告警的通道绕过选择。\n\n按事件和渠道去重，同时保留投递尝试历史。供应商超时代表结果未知，不能直接认定失败，因此重试要考虑之前可能已经送达。偏好审计只记录选中的类别和修改时间，不保存消息正文或隐藏追踪内容。",
        "code": "notify.send(event, channel='email', recheck_preferences=True, dedupe_by='event-channel')",
    },
    {
        "key": "pagination",
        "en_question": "How should activity pagination avoid duplicates as new records arrive?",
        "zh_question": "新活动不断写入时，分页怎样避免重复和遗漏？",
        "en": "Use a cursor containing the stable ordering key and a tie-breaker rather than a page number. New records inserted before the cursor do not shift the next page. The cursor also includes the applied filter revision so the server can reject a continuation request that silently changes the query.\n\nAn expired cursor returns a clear restart instruction with the current snapshot boundary. Avoid including raw permissions or personal data in an unsigned client-controlled cursor. Tests insert records between page requests and verify that each original record appears exactly once. Sorting must remain deterministic when timestamps are equal.",
        "zh": "游标包含稳定排序键和用于消除同值歧义的附加键，不依赖页码。插入到游标之前的新记录不会改变后续页位置。游标还记录过滤规则版本，服务端可以拒绝在继续翻页时悄悄改变查询条件的请求，避免用户看到无法解释的重复结果。\n\n游标过期时返回明确的重新开始说明和当前快照边界。未经签名、由客户端控制的游标不能携带原始权限或个人信息。测试在两次分页请求之间插入记录，并验证原有记录恰好出现一次；时间戳相同时仍须保持确定排序。",
        "code": "activity.page(cursor=signed_cursor, order=('created_at', 'id'), verify_filter_revision=True)",
    },
    {
        "key": "tracing",
        "en_question": "How can tracing connect asynchronous work without exposing credentials?",
        "zh_question": "异步任务怎样关联链路追踪又不暴露凭据？",
        "en": "Propagate a trace link across the queue boundary rather than pretending asynchronous work remains a child of a finished synchronous request. Record producer and consumer timestamps to separate queue delay from processing time. Attribute allowlists prevent credentials, raw request bodies and customer secrets from entering spans.\n\nSampling keeps failed operations and a bounded representative sample of successful work. High-cardinality identifiers belong in searchable attributes rather than metric labels. A missing parent span should not stop task execution. Operators need enough correlation to follow a failure while respecting the retention rules of each telemetry system.",
        "zh": "跨队列边界传播追踪链接，而不是把异步任务伪装成已经结束的同步请求的直接子步骤。记录生产者和消费者时间，以便区分排队延迟与处理耗时。属性白名单阻止凭据、原始请求正文和客户秘密进入追踪记录。\n\n采样保留失败操作以及数量受限的成功代表样本。高基数标识放在可搜索属性里，不放入指标标签。缺少父跨度不能阻止任务执行。运维需要足够的关联信息追查失败，同时遵守各遥测系统的保留规则和访问范围。",
        "code": "tracing.link(message.trace_context, attributes=allowlisted_fields, retain_errors=True)",
    },
    {
        "key": "accessibility",
        "en_question": "How should a modal dialog behave for keyboard and screen-reader users?",
        "zh_question": "弹窗对键盘和屏幕阅读器用户应当如何工作？",
        "en": "Move focus to the dialog heading or first meaningful control when the modal opens, and restore focus to the triggering element when it closes. Trap focus only while the modal is active. The escape key closes a dismissible dialog, but a destructive action still requires its explicit confirmation control.\n\nAssociate validation errors with their input fields and announce asynchronous status updates without repeatedly interrupting navigation. Color cannot be the only signal for success or failure. Verify zoom, high-contrast settings and reduced-motion preferences. Automated checks help locate missing labels, but the keyboard path still needs direct inspection.",
        "zh": "弹窗打开时把焦点移到标题或首个有意义的控件，关闭时恢复到触发元素。只在弹窗活动期间限制焦点范围。可取消弹窗支持Escape关闭，破坏性操作仍然需要明确的确认控件，不能把关闭行为与执行删除混淆。\n\n校验错误关联到对应输入框，异步状态更新通过适当方式播报，避免反复打断导航。成功或失败不能只用颜色表示。检查缩放、高对比度和减少动态效果设置；自动检查能发现缺少标签，实际键盘路径仍需要直接验证。",
        "code": "dialog.open(initial_focus='heading', restore_focus=True, announce_errors='polite')",
    },
    {
        "key": "configuration",
        "en_question": "How should configuration changes roll out without splitting service behavior?",
        "zh_question": "配置变更怎样发布才不会让服务行为分裂？",
        "en": "Version the complete validated configuration snapshot rather than pushing unrelated key updates independently. Each request records the snapshot version it used. Validate constraints before activation, including dependencies between timeout, retry count and overall request deadline. A malformed snapshot remains inactive and produces an operator-visible error.\n\nRoll out to a small replica cohort before promotion. The prior snapshot remains available for immediate rollback, and the change log records the author and rationale. Secrets are referenced through secret identifiers instead of copied into diagnostics. A replica that cannot fetch an update keeps the last valid snapshot and reports its stale version.",
        "zh": "为完整且已校验的配置快照设置版本，不把相互关联的键独立推送。每个请求记录使用的快照版本。激活前检查超时、重试次数和总请求截止时间之间的约束；格式错误的快照保持未激活，并向运维展示可处理的错误。\n\n先发布到少量副本观察，再逐步扩大范围。保留前一快照以便立即回滚，变更记录包含作者和理由。秘密通过标识引用，不复制到诊断信息里。无法获取更新的副本继续使用最后有效快照，同时报告自己落后的版本。",
        "code": "config.activate(snapshot, validate_dependencies=True, canary_replicas=2, keep_previous=True)",
    },
    {
        "key": "deletion",
        "en_question": "How should a deletion request propagate into derived data stores?",
        "zh_question": "删除请求怎样传播到派生数据存储？",
        "en": "Assign a durable deletion request identifier and enumerate the systems containing derived copies. Search indexes, caches, exports and analytics tables acknowledge their own completion. A coordinator retries missing acknowledgements without treating a temporary endpoint failure as a completed deletion.\n\nThe user-visible status distinguishes removal from active product views from expiry of immutable backup retention. Keep a minimal audit record of the deletion request without retaining the deleted content itself. New derived jobs check the deletion ledger before publishing output, preventing a delayed task from recreating information that was just removed.",
        "zh": "为删除请求分配持久标识，列出持有派生副本的系统。搜索索引、缓存、导出文件和分析表分别确认完成，协调器重试缺失确认，不能把临时接口失败当作删除成功。进度记录应能解释哪个系统仍在处理中，以及下一次重试的条件。\n\n面向用户的状态区分活动产品视图已移除和不可变备份保留周期尚未到期。保留最小删除审计记录，但不继续保留被删除的内容。新的派生任务发布前检查删除台账，防止延迟执行的任务重新创建刚刚移除的信息。",
        "code": "deletion.propagate(request_id, targets=derived_stores, require_ack=True, prevent_recreation=True)",
    },
]


def add_long_sessions(dataset: Dataset, rng: random.Random) -> None:
    projects = list(dict.fromkeys(session["project"] for session in dataset.sessions))
    heldout = dataset.split == "heldout"
    service_names = ["gateway", "catalog", "checkout", "reporting", "scheduler", "identity",
                     "archive", "delivery", "analytics", "workspace", "inventory", "profile"]
    environments = ["staging", "production", "recovery", "load-test"]
    topic_by_key = {topic["key"]: topic for topic in TOPICS}

    for index, project in enumerate(projects):
        zh = index % 2 == 1
        display = next(session["title"].split(" — ")[0] for session in dataset.sessions
                       if session["project"] == project)
        for journal_index, milestone in enumerate(("Cedar", "Indigo")):
            sid = f"{project}-journal-{milestone.lower()}"
            retries = rng.choice([5, 7, 9, 11])
            retention = rng.choice([21, 28, 35, 42, 49])
            purge = rng.choice([40, 70, 100, 130, 160])
            reserve = rng.choice([13, 17, 23, 29])
            restart = rng.choice([36, 48, 60, 72])
            webhook_fact = (f"{milestone}里程碑的签名Webhook最多投递{retries}次，随后转入恢复收件箱。" if zh else
                            f"For the {milestone} milestone, signed webhooks allow {retries} delivery attempts before moving to the recovery inbox.")
            backup_fact = (f"{milestone}里程碑的生产备份保留{retention}天，并且每周验证恢复。" if zh else
                           f"For the {milestone} milestone, production backups remain for {retention} days with weekly restore verification.")
            purge_fact = (f"{milestone}里程碑的可变静态入口在带标签发布后{purge}秒内完成边缘失效。" if zh else
                          f"For the {milestone} milestone, mutable asset entry points finish edge invalidation within {purge} seconds of a tagged release.")
            reserve_fact = (f"灾难恢复时必须为审计发件箱预留{reserve}个连接，不能借给普通查询。" if zh else
                            f"Disaster recovery reserves {reserve} connections for the audit outbox, unavailable to ordinary queries.")
            restart_fact = (f"灾难恢复演练中，报告调度器在切换后{restart}分钟才能恢复自动发送。" if zh else
                            f"During the disaster recovery rehearsal, the report scheduler resumes automatic delivery {restart} minutes after cutover.")

            turns: list[tuple[str, str]] = []
            selected = [TOPICS[(position * 7 + journal_index * 3 + index) % len(TOPICS)]
                        for position in range(64)]
            selected[5] = topic_by_key["webhook"]
            selected[52] = topic_by_key["backup"]
            selected[44] = topic_by_key["cdn"]
            for position, topic in enumerate(selected):
                service = service_names[(position + 3 * index + journal_index) % len(service_names)]
                environment = environments[(position + journal_index) % len(environments)]
                number = rng.randrange(100, 999)
                question = (f"{milestone}阶段，{service}服务在{environment}环境：{topic['zh_question']}" if zh else
                            f"In the {milestone} milestone, for {service} in {environment}: {topic['en_question']}")
                evidence = ({5: webhook_fact, 52: backup_fact, 44: purge_fact}.get(position))
                paragraphs = str(topic["zh" if zh else "en"]).split("\n\n")
                if evidence:
                    paragraphs.insert(1, evidence)
                operational_note = (
                    f"本次检查关联变更单OPS-{number}，负责人需要在{environment}环境验证{service}的行为。"
                    f"先保留当前配置和监控快照，再执行变更；验证记录写明输入、预期输出、实际观察和后续处理人。"
                    f"如果发现结果与预期不符，应停止扩大范围并回到最近一次通过验证的版本。"
                    if zh else
                    f"This review is attached to change OPS-{number}. The owner verifies {service} in {environment}, "
                    f"captures the current configuration and monitoring snapshot, then records the input, expected output, "
                    f"observed result and next responder. If the observed result differs from the expected behavior, stop "
                    f"expansion and return to the most recently verified version."
                )
                answer = "\n\n".join(paragraphs) + f"\n\n```python\n# {service}: {milestone}\n{topic['code']}\n```\n\n" + operational_note
                if position == 31:
                    # One long answer made of independently authored procedures;
                    # target facts are well beyond both prefix and first page.
                    question = (f"为{milestone}里程碑写一份完整灾难恢复演练手册，覆盖各个系统。" if zh else
                                f"Write a complete disaster recovery rehearsal manual across systems for the {milestone} milestone.")
                    blocks = []
                    for manual_index, item in enumerate(TOPICS):
                        heading = item["zh_question" if zh else "en_question"]
                        body = item["zh" if zh else "en"]
                        blocks.append(f"## {manual_index + 1}. {heading}\n\n{body}\n\n```python\n{item['code']}\n```")
                        if manual_index == 10:
                            blocks.append(reserve_fact)
                        if manual_index == 17:
                            blocks.append(restart_fact)
                    answer = "\n\n".join(blocks)
                turns.append((question, answer))
            messages = [{"role": role, "content": content}
                        for question, answer in turns
                        for role, content in (("user", question), ("assistant", answer))]
            dataset.sessions.append({
                "project": project, "session_id": sid,
                "title": f"{display} — {milestone} engineering journal",
                "task_id": "engineering-journal", "task_title": "工程交付日志" if zh else "Engineering delivery journal",
                "created_at": f"2025-05-{journal_index + 3:02d}T10:00:00Z", "messages": messages,
            })
            pairs = [
                ("multi-section", "multi_section",
                 (f"{milestone}里程碑的签名Webhook最大投递次数和生产备份保留时间分别是多少？" if not heldout else
                  f"在{milestone}工程日志中同时查找Webhook投递上限，以及生产备份保留多少天。") if zh else
                 (f"For the {milestone} milestone, give the signed webhook attempt limit and production backup retention period." if not heldout else
                  f"Find both the webhook delivery ceiling and backup retention window in the {milestone} journal."),
                 (Evidence(sid, 5, webhook_fact), Evidence(sid, 52, backup_fact))),
                ("topic-change", "topic_change",
                 (f"{milestone}里程碑带标签发布后，静态入口边缘失效应在多少秒内完成？" if not heldout else
                  f"查找{milestone}里程碑对可变静态入口发布失效耗时的要求。") if zh else
                 (f"For {milestone}, how quickly must mutable asset entry points finish edge invalidation after a tagged release?" if not heldout else
                  f"Find the {milestone} tagged-release deadline for mutable asset edge invalidation."),
                 (Evidence(sid, 44, purge_fact),)),
                ("manual-middle", "long_answer_natural_middle",
                 (f"{milestone}灾难恢复手册要求给审计发件箱预留多少连接？" if not heldout else
                  f"在{milestone}灾难恢复演练中，审计发件箱不能被普通查询占用的连接额度是多少？") if zh else
                 (f"In the {milestone} disaster recovery manual, how many connections are reserved for the audit outbox?" if not heldout else
                  f"What connection allowance does the {milestone} disaster recovery procedure reserve for the audit outbox?"),
                 (Evidence(sid, 31, reserve_fact),)),
                ("manual-late", "long_answer_natural_late",
                 (f"{milestone}灾难恢复演练切换后，报告调度器要等多久才能恢复自动发送？" if not heldout else
                  f"查找{milestone}灾难恢复演练中报告调度器重新自动发送的等待分钟数。") if zh else
                 (f"After cutover in the {milestone} disaster recovery rehearsal, when may the report scheduler resume automatic delivery?" if not heldout else
                  f"Find the waiting period before report scheduling resumes after {milestone} disaster recovery cutover."),
                 (Evidence(sid, 31, restart_fact),)),
            ]
            for suffix, category, query, required in pairs:
                dataset.queries.append(QueryCase(f"{sid}-{suffix}", query, category, project, required))
