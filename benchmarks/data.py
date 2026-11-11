"""Deterministic bilingual software-project conversations and evidence labels.

Synthetic conversations are useful for controlled regressions, not a substitute
for evaluating consented real conversations.  Labels address original turns so
that the same cases can evaluate every segmentation policy fairly.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any


DATASET_VERSION = "2.0"


@dataclass(frozen=True)
class Evidence:
    session_id: str
    turn_index: int
    needle: str


@dataclass(frozen=True)
class QueryCase:
    id: str
    query: str
    category: str
    project: str | None
    required: tuple[Evidence, ...] = ()
    stale: tuple[Evidence, ...] = ()
    answerable: bool = True


@dataclass
class Dataset:
    seed: int
    split: str
    variant: str = "long_sessions_v2"
    sessions: list[dict[str, Any]] = field(default_factory=list)
    queries: list[QueryCase] = field(default_factory=list)

    @property
    def source_characters(self) -> int:
        return sum(len(message["content"]) for session in self.sessions
                   for message in session["messages"])

    @property
    def turn_count(self) -> int:
        return sum(message["role"] == "user" for session in self.sessions
                   for message in session["messages"])

    @property
    def fingerprint(self) -> str:
        value = {"version": "1.0" if self.variant == "short_sessions_v1" else DATASET_VERSION, "seed": self.seed,
                 "split": self.split, "sessions": self.sessions,
                 "queries": [asdict(case) for case in self.queries]}
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def description(self) -> dict[str, Any]:
        categories: dict[str, int] = {}
        for case in self.queries:
            categories[case.category] = categories.get(case.category, 0) + 1
        return {
            "kind": "synthetic",
            "version": "1.0" if self.variant == "short_sessions_v1" else DATASET_VERSION,
            "variant": self.variant,
            "seed": self.seed,
            "split": self.split,
            "sha256": self.fingerprint,
            "projects": len({session["project"] for session in self.sessions}),
            "sessions": len(self.sessions),
            "turns": self.turn_count,
            "source_characters": self.source_characters,
            "source_utf8_bytes": sum(
                len(message["content"].encode("utf-8"))
                for session in self.sessions for message in session["messages"]
            ),
            "queries": len(self.queries),
            "answerable_queries": sum(case.answerable for case in self.queries),
            "categories": categories,
        }


def _messages(turns: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"role": role, "content": content}
            for question, answer in turns
            for role, content in (("user", question), ("assistant", answer))]


def generate_dataset(seed: int = 29, split: str = "heldout", projects: int = 8,
                     include_long_sessions: bool = True) -> Dataset:
    """Build one corpus; no evidence labels are embedded in conversation text.

    Development and heldout use different source/question phrasings as well as
    different default seeds.  A split name does not enforce non-interference:
    once its outcomes have guided tuning, that run is development evidence.
    """
    if split not in {"development", "heldout"}:
        raise ValueError("split must be 'development' or 'heldout'")
    if not 2 <= projects <= 128:
        raise ValueError("projects must be between 2 and 128")
    rng = random.Random(seed)
    dataset = Dataset(seed=seed, split=split,
                      variant="long_sessions_v2" if include_long_sessions else "short_sessions_v1")
    heldout = split == "heldout"
    names = ["Atlas", "Comet", "Harbor", "Lantern", "Maple", "Nimbus",
             "Orchid", "Pebble", "Quartz", "River", "Solstice", "Tundra",
             "Umber", "Willow", "Xenon", "Zephyr"]
    rng.shuffle(names)

    def add_session(project: str, sid: str, title: str, task: str,
                    task_title: str, day: int, turns: list[tuple[str, str]]) -> None:
        dataset.sessions.append({
            "project": project, "session_id": sid, "title": title,
            "task_id": task, "task_title": task_title,
            "created_at": f"2025-04-{day:02d}T09:00:00Z",
            "messages": _messages(turns),
        })

    def add_query(qid: str, query: str, category: str, project: str | None,
                  *required: Evidence, stale: tuple[Evidence, ...] = (),
                  answerable: bool = True) -> None:
        if heldout:
            # Evaluation questions use a different wording bank from the
            # development split; generated values remain absent from queries.
            key = qid.removeprefix(prefix)
            variations = {
                "cache-current": ("确认报价缓存最终生效的过期秒数。", "State the final effective expiration interval for the quote cache."),
                "cache-history": ("回顾报价缓存首次设计时的有效期。", "Which expiration duration did the cache design start with?"),
                "cache-reason": ("把报价缓存更新后的有效期和修改原因一起找出来。", "Find both the revised quote cache TTL and the incident reason behind that revision."),
                "cache-global": (f"查找{name}的报价缓存最终TTL结论。", f"Find {name}'s final decision about quote cache expiration."),
                "cache-paraphrase": ("暂存的金额经过多久必须扔掉？", "When must a previously saved monetary amount be discarded?"),
                "refresh": ("刷新令牌的失效时间规定了多少小时？", "What expiration window was specified for refresh tokens?"),
                "login-limit": ("一分钟连续登录失败几次会触发账户限流？", "What per-account failed-login cap applies each minute?"),
                "rollback": ("找出自动回滚要求的连续错误分钟数和错误率。", "Find the error threshold and consecutive interval required for automatic rollback."),
                "canary": ("查找讨论里确定的金丝雀初始流量占比。", "Find the agreed initial traffic share in the canary discussion."),
                "worker-concurrency": ("后台任务执行并发上限最终是多少？", "State the permitted simultaneous job count for the background worker."),
                "poison": ("运维手册对毒性消息规定了多久的隔离期，谁负责复核？", "According to the runbook, who reviews poison messages and after what quarantine period?"),
                "unrelated": ("海王星的公转周期有多长？", "How long does Neptune take to orbit the Sun?"),
                "near-miss": ("缓存的AES密钥多久更换一次？", "How often must the cache AES encryption key be rotated?"),
            }
            if key in variations:
                query = variations[key][0 if zh else 1]
        dataset.queries.append(QueryCase(qid, query, category, project,
                                         tuple(required), stale, answerable))

    for index in range(projects):
        name = names[index % len(names)] + (str(index // len(names) + 1)
                                          if index >= len(names) else "")
        project = name.lower()
        zh = index % 2 == 1
        prefix = f"{project}-"
        ttl_old, ttl_new = rng.sample([25, 35, 45, 55, 65, 75, 85, 95], 2)
        refresh = rng.choice([8, 10, 12, 14, 16, 18])
        rollback = rng.choice([2, 3, 4, 5, 6])
        concurrency = rng.choice([6, 10, 14, 18, 22])
        quarantine = rng.choice([7, 11, 13, 17, 19])
        limit = rng.choice([4, 6, 8, 10])
        reason = ("上游报价每分钟更新两次，旧缓存会返回已经失效的价格。" if zh else
                  "The upstream pricing feed changes twice per minute, so stale cache entries returned expired prices.")
        cache_old = (f"最初缓存有效期定为{ttl_old}秒。" if zh else
                     f"The initial cache TTL was {ttl_old} seconds.")
        cache_new = (f"最终缓存有效期定为{ttl_new}秒。" if zh else
                     f"The final cache TTL is {ttl_new} seconds.")
        cache_a, cache_b, cache_c = (prefix + "cache-design", prefix + "cache-incident",
                                    prefix + "cache-followup")
        task_name = "报价缓存" if zh else "Quote cache"
        add_session(project, cache_a, f"{name} — {task_name} / design", "cache", task_name, 1, [
            (("报价缓存的初始方案是什么？" if heldout else "先给报价缓存设个TTL。") if zh else
             ("What should expire the cached price at launch?" if heldout else "Choose the initial cache TTL."),
             cache_old + (" 缓存键包含币种和商户标识。" if zh else " Cache keys include currency and merchant.")),
            ("缓存键如何隔离租户？" if zh else "How are cache keys isolated by tenant?",
             "商户标识必须出现在缓存键前缀中。" if zh else "The merchant identifier must prefix every cache key."),
            ("缓存命中率怎么统计？" if zh else "How is cache hit rate measured?",
             "命中率分商户记录，避免高流量商户掩盖问题。" if zh else "Track hit rates per merchant to expose small-tenant regressions."),
            ("是否需要单飞请求？" if zh else "Do we need request coalescing?",
             "相同商户的并发刷新应合并为一个上游请求。" if zh else "Concurrent refreshes for one merchant share a single upstream request."),
        ])
        add_session(project, cache_b, f"{name} — {task_name} / incident", "cache", task_name, 9, [
            ("为什么报价缓存需要调整？" if zh else "Why does the pricing cache need a change?", reason),
            ("能通过增加缓存内存修复吗？" if zh else "Would allocating more cache memory fix the problem?",
             "增加内存不会改变上游报价的更新频率。" if zh else "Additional memory cannot change the upstream price update frequency."),
            ("失败的缓存刷新要怎样处理？" if zh else "How should a failed cache refresh behave?",
             "短暂错误返回明确的重试响应，不继续提供失效报价。" if zh else "Return an explicit retry response on transient failure instead of an expired quote."),
            ("事故复盘里还记录了什么？" if zh else "What else did the incident review record?",
             "运行手册增加了上游延迟和刷新失败率两个指标。" if zh else "The runbook adds upstream delay and refresh failure metrics."),
        ])
        add_session(project, cache_c, f"{name} — {task_name} / decision", "cache", task_name, 17, [
            (("缓存TTL的最后决定是什么？" if heldout else "给出缓存有效期的最终结论。") if zh else
             ("What did the cache review finally decide?" if heldout else "Confirm the final cache TTL."), cache_new),
            ("旧的有效期还要保留吗？" if zh else "Should the previous expiration remain active?",
             "旧方案已被替代，只保留在变更历史中。" if zh else "The earlier setting is superseded and retained only in the change history."),
            ("什么时候开始监控新配置？" if zh else "When should monitoring start for this setting?",
             "发布当天启动监控，连续观察三个工作日。" if zh else "Start monitoring on release day and observe three business days."),
            ("这项任务可以关闭了吗？" if zh else "Can this task be closed?",
             "验证通过后关闭任务，并保留报价缓存变更记录。" if zh else "Close the task after verification and keep the quote cache change log."),
        ])
        old_ev, new_ev, reason_ev = (Evidence(cache_a, 0, cache_old),
                                      Evidence(cache_c, 0, cache_new), Evidence(cache_b, 0, reason))
        add_query(prefix + "cache-current", "报价缓存现在采用多少秒的有效期？" if zh else
                  "What is the current quote cache expiration?", "latest_decision", project,
                  new_ev, stale=(old_ev,))
        add_query(prefix + "cache-history", "报价缓存最开始定的有效期是多少？" if zh else
                  "What was the original cache TTL?", "historical", project, old_ev)
        add_query(prefix + "cache-reason", "报价缓存最后设成多久，以及调整的原因是什么？" if zh else
                  "What cache lifetime was finally chosen, and why was the change necessary?",
                  "cross_session", project, new_ev, reason_ev)
        add_query(prefix + "cache-global", f"{name} 项目最终采用什么缓存有效期？" if zh else
                  f"For {name}, what cache TTL did the final decision specify?",
                  "cross_project_name", None, new_ev)
        add_query(prefix + "cache-paraphrase", "保存过的金额多久之后就不应该继续拿来用了？" if zh else
                  "After what duration must a stored monetary amount be discarded?",
                  "low_overlap_paraphrase", project, new_ev)

        auth_a, auth_b, auth_c = (prefix + "auth-policy", prefix + "auth-review",
                                prefix + "auth-check")
        auth_name = "身份认证" if zh else "Authentication"
        refresh_fact = (f"刷新令牌有效期为{refresh}小时。" if zh else
                        f"Refresh tokens expire after {refresh} hours.")
        limit_fact = (f"每个账户一分钟内最多允许{limit}次登录失败。" if zh else
                      f"Each account permits at most {limit} failed logins per minute.")
        add_session(project, auth_a, f"{name} — {auth_name} / policy", "authentication", auth_name, 2, [
            ("刷新令牌需要多久失效？" if zh else "How long should a refresh token last?", refresh_fact),
            ("登录失败怎么限流？" if zh else "How are failed sign-ins throttled?", limit_fact),
            ("访问令牌保存在哪里？" if zh else "Where are access credentials stored?",
             "浏览器使用仅HTTP可读的安全Cookie。" if zh else "The browser uses secure HTTP-only cookies."),
            ("如何记录认证拒绝？" if zh else "How are authentication rejections logged?",
             "日志只记录原因码，不记录完整令牌。" if zh else "Logs record a reason code, never the complete token."),
        ])
        add_session(project, auth_b, f"{name} — {auth_name} / review", "authentication", auth_name, 10, [
            ("退出登录如何撤销刷新令牌？" if zh else "How does logout revoke refresh credentials?",
             "退出后撤销当前令牌族，其他设备不受影响。" if zh else "Logout revokes the current token family and leaves other devices unchanged."),
            ("认证缓存可以复用报价缓存吗？" if zh else "Can authentication reuse the quote cache?",
             "认证撤销列表使用独立命名空间，不能与报价缓存混用。" if zh else "Revocation lists use a separate namespace from quote caches."),
            ("要支持哪种额外验证？" if zh else "Which additional verification is supported?",
             "管理员必须提供一次性验证码。" if zh else "Administrators must supply a one-time verification code."),
            ("会话超时要弹出提示吗？" if zh else "Should an expired session show a warning?",
             "先保存草稿，再显示需要重新登录的提示。" if zh else "Save the draft before asking the user to sign in again."),
        ])
        add_session(project, auth_c, f"{name} — {auth_name} / verification", "authentication", auth_name, 18, [
            ("检查认证配置还剩哪些事？" if zh else "What remains on the authentication checklist?",
             "检查时钟偏差、撤销列表和登录失败监控。" if zh else "Verify clock skew, revocation lists, and failed-login monitoring."),
            ("能在测试中使用真实令牌吗？" if zh else "May tests use production credentials?",
             "只能使用专门生成的测试凭据。" if zh else "Use dedicated generated test credentials."),
            ("如何模拟令牌到期？" if zh else "How can tests simulate token expiration?",
             "测试使用可注入时钟，不依赖实际等待。" if zh else "Tests use an injectable clock rather than real waiting."),
            ("认证上线后观察什么？" if zh else "What should we watch after authentication launches?",
             "观察拒绝率、刷新耗时和管理员验证失败率。" if zh else "Watch rejection rate, refresh latency, and admin verification failures."),
        ])
        add_query(prefix + "refresh", "身份认证的刷新令牌多久过期？" if zh else
                  "When does the authentication refresh token expire?", "lookup", project,
                  Evidence(auth_a, 0, refresh_fact))
        add_query(prefix + "login-limit", "账户登录失败限流的次数上限是多少？" if zh else
                  "How many failed logins are allowed for an account in one minute?",
                  "similar_task", project, Evidence(auth_a, 1, limit_fact))

        deploy_a, deploy_b, deploy_c = (prefix + "release-plan", prefix + "release-discussion",
                                       prefix + "release-validation")
        deploy_name = "发布回滚" if zh else "Release rollback"
        threshold_fact = (f"连续{rollback}分钟错误率超过百分之二就自动回滚。" if zh else
                          f"Rollback automatically after {rollback} consecutive minutes above a two percent error rate.")
        short_fact = (f"百分之{rollback}。" if zh else f"{rollback} percent.")
        add_session(project, deploy_a, f"{name} — {deploy_name} / plan", "release", deploy_name, 3, [
            ("发布自动回滚的触发条件是什么？" if zh else "What triggers automatic release rollback?", threshold_fact),
            ("先从哪个环境发布？" if zh else "Which environment receives the release first?",
             "先部署预生产环境，检查完成后再进入生产。" if zh else "Deploy to staging first, then proceed to production after checks."),
            ("数据库迁移要一起回滚吗？" if zh else "Should database migrations roll back with the release?",
             "迁移先保证向后兼容，避免自动破坏数据。" if zh else "Migrations remain backward compatible to avoid destructive automatic reversals."),
            ("部署日志保留多久？" if zh else "How long are deployment logs retained?",
             "保留最近六个月的部署审计记录。" if zh else "Retain six months of deployment audit records."),
        ])
        add_session(project, deploy_b, f"{name} — release discussion", "release", deploy_name, 11, [
            ("谈一下金丝雀发布的流量百分比。" if zh else "Let's discuss the canary rollout traffic percentage.",
             "初始值需要降低，以便减小第一批用户的影响范围。" if zh else "Lower the initial share to limit impact on the first users."),
            ("那最后改成多少？" if zh else "So what should we set it to?", short_fact),
            ("这个数字需要写进运行手册吗？" if zh else "Should that number go in the runbook?",
             "需要，并记录恢复全量流量的条件。" if zh else "Yes; also record when full traffic may resume."),
            ("如果首批失败呢？" if zh else "What if the first batch fails?",
             "暂停扩量，排查异常后再重试。" if zh else "Pause expansion and investigate before retrying."),
        ])
        add_session(project, deploy_c, f"{name} — {deploy_name} / validation", "release", deploy_name, 19, [
            ("发布验证清单需要哪些步骤？" if zh else "What belongs in release verification?",
             "验证健康检查、依赖版本和回滚演练。" if zh else "Verify health checks, dependency versions, and a rollback rehearsal."),
            ("回滚演练在哪里做？" if zh else "Where should rollback be rehearsed?",
             "使用与生产配置接近的隔离环境。" if zh else "Use an isolated environment configured like production."),
            ("演练完成后记录什么？" if zh else "What should we record after the rehearsal?",
             "记录恢复时间和未自动恢复的依赖项。" if zh else "Record recovery time and dependencies that needed manual restoration."),
            ("发布审批是否完成？" if zh else "Is release approval complete?",
             "验证清单全部通过后由值班负责人确认。" if zh else "The on-call lead confirms approval after every checklist item passes."),
        ])
        add_query(prefix + "rollback", "发布错误率达到什么条件会自动回滚？" if zh else
                  "What duration and error rate trigger automatic release rollback?",
                  "lookup", project, Evidence(deploy_a, 0, threshold_fact))
        add_query(prefix + "canary", "金丝雀发布最后确定的流量百分比是多少？" if zh else
                  "What traffic percentage was finally chosen for the canary rollout?",
                  "short_followup", project, Evidence(deploy_b, 1, short_fact))

        worker_a, worker_b, worker_c = (prefix + "worker-plan", prefix + "worker-runbook",
                                       prefix + "worker-check")
        worker_name = "后台任务队列" if zh else "Background worker queue"
        concurrency_fact = (f"后台任务同时运行的并发数为{concurrency}。" if zh else
                            f"The worker runs {concurrency} background jobs concurrently.")
        quarantine_fact = (f"毒性消息隔离{quarantine}天后由值班人员人工复核。" if zh else
                           f"Poison messages are quarantined for {quarantine} days before an on-call manual review.")
        # A fact in the middle of a long answer exposes whole-page prefix
        # truncation. The filler is plausible operational prose, not markers.
        observations = ([
            "检查队列积压趋势，并对照上一班次记录。",
            "核对消费者健康状态，记录异常重启的时间。",
            "查看运行手册中对应的处理步骤，避免重复操作。",
            "在观察窗口结束后，保存相关监控图和排查结论。",
        ] if zh else [
            "Inspect the backlog trend and compare it with the previous shift's notes.",
            "Check consumer health and record the timing of unexpected restarts.",
            "Follow the matching runbook procedure and avoid repeating an operation.",
            "At the end of the observation window, save graphs and investigation conclusions.",
        ])
        filler_before = "\n".join(rng.choice(observations) for _ in range(65))
        filler_after = "\n".join(rng.choice(observations) for _ in range(65))
        long_answer = filler_before + "\n\n" + quarantine_fact + "\n\n" + filler_after
        add_session(project, worker_a, f"{name} — {worker_name} / plan", "workers", worker_name, 4, [
            ("后台任务允许多少并发？" if zh else "How much worker concurrency is allowed?", concurrency_fact),
            ("失败任务采用什么重试策略？" if zh else "What is the retry policy for a failed job?",
             "采用指数退避，最多自动重试三次。" if zh else "Use exponential backoff with at most three automatic retries."),
            ("任务幂等键放在哪里？" if zh else "Where is the job idempotency key stored?",
             "幂等键保存在持久化任务记录中。" if zh else "Store the idempotency key in the persistent job record."),
            ("如何处理优先级任务？" if zh else "How should priority jobs be scheduled?",
             "高优先级任务使用独立通道，但必须防止普通任务饥饿。" if zh else "Priority jobs use a separate lane without starving ordinary work."),
        ])
        add_session(project, worker_b, f"{name} — {worker_name} / runbook", "workers", worker_name, 12, [
            ("写出后台队列的详细运维检查步骤。" if zh else "Describe the detailed operational checks for the background queue.", long_answer),
            ("运维检查完成后通知谁？" if zh else "Who receives the outcome of operational checks?",
             "将结论交给下一班值班人员。" if zh else "Hand the conclusions to the next on-call shift."),
            ("要保留完整任务负载吗？" if zh else "Should we retain the full job payload?",
             "只保留排查所需的脱敏字段。" if zh else "Keep only the redacted fields needed for investigation."),
            ("监控告警如何合并？" if zh else "How should repeated monitoring alerts be grouped?",
             "相同原因的告警合并为同一个事件。" if zh else "Group alerts with the same cause into one incident."),
        ])
        add_session(project, worker_c, f"{name} — {worker_name} / validation", "workers", worker_name, 20, [
            ("任务队列验收包括哪些内容？" if zh else "What does queue acceptance cover?",
             "检查失败重试、重复投递和消费者退出时的任务恢复。" if zh else "Check retries, duplicate delivery, and recovery when a consumer exits."),
            ("需要验证队列积压吗？" if zh else "Should backlog behavior be validated?",
             "模拟流量峰值，确认积压能在低峰期恢复。" if zh else "Simulate a traffic peak and verify that the backlog drains afterward."),
            ("如何检查任务被重复执行？" if zh else "How do we detect duplicate execution?",
             "按幂等键核对结果记录和执行次数。" if zh else "Compare result records and execution counts by idempotency key."),
            ("任务队列工作完成了吗？" if zh else "Is the queue work complete?",
             "验收通过后归档运行手册，保留事故链接。" if zh else "Archive the runbook after acceptance and retain incident links."),
        ])
        add_query(prefix + "worker-concurrency", "后台队列同时能运行多少个任务？" if zh else
                  "How many background jobs may a worker execute at once?",
                  "lookup", project, Evidence(worker_a, 0, concurrency_fact))
        add_query(prefix + "poison", "毒性消息隔离多长时间后由谁复核？" if zh else
                  "How long are poison messages quarantined, and who reviews them?",
                  "long_answer_middle", project, Evidence(worker_b, 0, quarantine_fact))
        add_query(prefix + "unrelated", "木星大红斑的直径是多少？" if zh else
                  "What is the diameter of Jupiter's Great Red Spot?",
                  "unanswerable_unrelated", project, answerable=False)
        add_query(prefix + "near-miss", "报价缓存使用的AES加密密钥轮换周期是多少？" if zh else
                  "What is the AES encryption key rotation interval for the quote cache?",
                  "unanswerable_related", project, answerable=False)

    if include_long_sessions:
        from .long_data import add_long_sessions
        add_long_sessions(dataset, rng)
    rng.shuffle(dataset.queries)
    return dataset
