"""New authored source-grounded questions for the v0.14 growth experiment.

The data and gold are independent of any candidate runtime.  This module only
generates public synthetic conversations and evaluator requirements; it never
imports MemoryBook or executes retrieval.  The old v0.13 fixture is unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

VERSION = "v014-project-growth-workload-1"
SEED = 1401917
PAGES_PER_SESSION = 32
CORE_TURNS = 16
TARGETS = (
    {"project": "ledger-archive", "family": "ledger", "lifecycle": "inactive", "pages": 32,
     "old": 16, "current": 48, "sibling": 7, "config": 24, "conflict": [2, 3]},
    {"project": "stream-archive", "family": "stream", "lifecycle": "inactive", "pages": 256,
     "old": 128, "current": 192, "sibling": 17, "config": 320, "conflict": [3, 4]},
    {"project": "decoder-archive", "family": "decoder", "lifecycle": "inactive", "pages": 1024,
     "old": 7, "current": 13, "sibling": 3, "config": 64, "conflict": [1, 2]},
    {"project": "ledger-active", "family": "ledger", "lifecycle": "long_lived", "pages": 64,
     "old": 32, "current": 96, "sibling": 11, "config": 40, "conflict": [5, 7]},
    {"project": "stream-next", "family": "stream", "lifecycle": "newcomer", "pages": 64,
     "old": 256, "current": 384, "sibling": 19, "config": 640, "conflict": [7, 9]},
    {"project": "decoder-next", "family": "decoder", "lifecycle": "newcomer", "pages": 64,
     "old": 11, "current": 29, "sibling": 5, "config": 128, "conflict": [4, 8]},
)
FIXED = TARGETS[:3]
GROWING = TARGETS[3:]
TARGET_PAGES = sum(t["pages"] for t in TARGETS)
FAMILIES = {
    "ledger": {"field": "ledger.checkpoint_stride", "sibling": "ledger.checkpoint_stride_ms",
               "config": "ledger.lease_window_s", "conflict": "ledger.flush_batch",
               "missing": "ledger.remote_ack_quorum", "title": "Ledger checkpoint recovery",
               "zh": "账本检查点", "explanation": "账本检查点以已提交的记录条数为单位。"},
    "stream": {"field": "replay.cursor_batch", "sibling": "replay.cursor_batch_bytes",
               "config": "replay.flush_window_s", "conflict": "replay.ack_window",
               "missing": "replay.remote_ack_quorum", "title": "Replay cursor recovery",
               "zh": "日志重放游标", "explanation": "日志重放游标按已确认的事件条数推进。"},
    "decoder": {"field": "sampling.top_k", "sibling": "decoder.top_k",
                "config": "sampling.cache_slots", "conflict": "sampling.draft_width",
                "missing": "sampling.remote_ack_quorum", "title": "Sampling decoder recovery",
                "zh": "解码候选采样", "explanation": "解码候选采样的数量上限按词表候选个数计。"},
}
BOUNDARIES = {
    "ledger-archive": "A checkpoint may be acknowledged only after both record bytes and the journal marker are durable.",
    "ledger-active": "An empty ledger identifier is rejected; a checkpoint waits for the quorum journal marker.",
    "stream-archive": "The replay cursor cannot pass an event until its dead-letter record is durable; duplicate event IDs are discarded once.",
    "stream-next": "A duplicate event remains pending until the consumer acknowledges it; an epoch marker must match the input epoch.",
    "decoder-archive": "The selected candidate count cannot exceed the allowed vocabulary; a zero temperature selects the largest permitted logit.",
    "decoder-next": "A stop token terminates decoding before another cache slot is allocated; an empty allowed vocabulary returns an empty result.",
}

# Individually authored prompts.  They are new development questions, not
# independent real-user observations or a secret production holdout.
QUESTIONS = {
    "ledger-archive": (
        "I am reopening the archived ledger. Which approved ledger.checkpoint_stride value governs its checkpoint writer now?",
        "继续维护旧账本检查点：当前间隔是多少，确认成功之前必须满足哪条持久化约束？请给出两处原始记录。",
        "Before the checkpoint writer was revised, what ledger.checkpoint_stride did the original design approve?",
        "What is ledger.checkpoint_stride_ms, specifically the time-valued sibling rather than ledger.checkpoint_stride?",
        "Which current ledger.checkpoint_stride decision is still approved after the later review notes?",
        "Two records approved ledger.flush_batch at the same timestamp. Return both recorded values and their separate sources.",
        "Does this ledger project record an approved ledger.remote_ack_quorum? Locate the source if it exists.",
        "Find the currently recorded ledger.lease_window_s allocation for the archived checkpoint worker.",
    ),
    "stream-archive": (
        "Which current replay.cursor_batch should be used when resuming this old event replayer?",
        "旧重放服务重新开工：当前游标批量和死信落盘、重复事件处理的边界分别是什么？两处依据都需要。",
        "Recover the first approved replay.cursor_batch from the original replay design, before its later correction.",
        "Read replay.cursor_batch_bytes exactly; the event-count field replay.cursor_batch is a different setting.",
        "For replay.cursor_batch, which approved configuration survives the more recent maintenance discussions?",
        "Show both same-time approvals of replay.ack_window without selecting one as a uniquely newer decision.",
        "Is an approved replay.remote_ack_quorum present in this project's history? Return its original evidence if present.",
        "Locate the current replay.flush_window_s setting belonging to this archived replayer.",
    ),
    "decoder-archive": (
        "The archived decoder is being restored. What is its currently approved sampling.top_k?",
        "恢复旧解码器时，当前候选上限以及允许词表、零温度的处理条件分别依据哪两条记录？",
        "What sampling.top_k value did this decoder approve in its initial design, before the current revision?",
        "Retrieve decoder.top_k from the decoder namespace, not the similarly spelled sampling.top_k.",
        "Which approved sampling.top_k remains the current decision after the newer inspection logs?",
        "Both approvals of sampling.draft_width have the same recorded time. Supply the two original declarations.",
        "Has this decoder approved sampling.remote_ack_quorum anywhere in its recorded sources?",
        "What is the current sampling.cache_slots configuration for this archived decoder?",
    ),
    "ledger-active": (
        "For the ledger service maintained over many revisions, what ledger.checkpoint_stride is currently approved?",
        "持续迭代的账本服务现在采用什么检查点间隔，空账本标识及法定人数标记有什么限制？请回查两份原文。",
        "Find the original ledger.checkpoint_stride approval before this long-lived service changed it.",
        "Which exact value belongs to ledger.checkpoint_stride_ms in the active ledger service?",
        "After the recent reviews, which approved ledger.checkpoint_stride should the active service retain?",
        "Identify both equal-time ledger.flush_batch approvals for the active ledger and cite each separately.",
        "Find an approved ledger.remote_ack_quorum for the active ledger, or establish only what the retrieved evidence supports.",
        "Read the presently approved ledger.lease_window_s for this active ledger project.",
    ),
    "stream-next": (
        "What is the newer replay project's current replay.cursor_batch, using this project's own decision record?",
        "新重放工程的当前批量是多少？重复事件确认和输入 epoch 的约束还需要哪些原始依据？",
        "What replay.cursor_batch was first approved when the newer replay project was created?",
        "Look up replay.cursor_batch_bytes for the new replayer; keep its byte count separate from the event batch size.",
        "Which replay.cursor_batch approval still applies after the new replayer's inspection and review entries?",
        "Retrieve both same-timestamp replay.ack_window declarations from the new project, including both values.",
        "Where is this new replayer's approved replay.remote_ack_quorum recorded, if anywhere?",
        "Find the current replay.flush_window_s allocation in the new replayer's own configuration source.",
    ),
    "decoder-next": (
        "What sampling.top_k is currently approved for the new decoder, independently of the archived decoder?",
        "新解码器目前的候选上限是多少？停止词和空允许词表的边界从哪份独立记录得到？",
        "Which sampling.top_k was approved in the new decoder's initial design rather than its current revision?",
        "Read decoder.top_k in the new decoder namespace while preserving the distinction from sampling.top_k.",
        "After the newer decoder's review notes, which approved sampling.top_k remains in force?",
        "Return both original sampling.draft_width approvals sharing the same timestamp in the new decoder.",
        "Is there a recorded approval of sampling.remote_ack_quorum for this new decoder project?",
        "What is the currently recorded sampling.cache_slots capacity for the new decoder?",
    ),
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def source_turn(messages, index):
    pair = messages[2 * index:2 * index + 2]
    if len(pair) != 2 or [m["role"] for m in pair] != ["user", "assistant"]:
        raise ValueError("Expected one alternating user/assistant pair per stored turn")
    return "\n\n".join(m["role"].upper() + ": " + m["content"] for m in pair)


def date(lifecycle, ordinal, shift_days=0):
    origin = {"inactive": "2009-01-01", "long_lived": "2014-01-01",
              "newcomer": "2020-01-01", "foreign": "2018-01-01"}[lifecycle]
    return (datetime.fromisoformat(origin).replace(tzinfo=timezone.utc)
            + timedelta(days=ordinal - shift_days)).isoformat(timespec="seconds")


def session(project, family, sid, pairs, created_at, title=None):
    label = FAMILIES[family]["title"]
    return {"project": project, "project_name": label, "session_id": sid,
            "title": title or label, "task_id": "recovery-contract", "task_title": label,
            "created_at": created_at,
            "messages": [{"role": role, "content": content} for question, answer in pairs
                         for role, content in (("user", question), ("assistant", answer))]}


def core_sessions(target, revision=0, shift_days=0, deleted=False):
    f = FAMILIES[target["family"]]
    key, sibling, config, conflict = (f[k] for k in ("field", "sibling", "config", "conflict"))
    mutable = target in GROWING
    value = target["config"] + (1000 if revision and mutable else 0)
    # Each decoy is explicitly quoted, conditional, denied, withdrawn or a
    # nondecision report.  All remain real sources and must be available for
    # explicit historical/report questions; no evaluator erases them.
    contents = [
        ("design-original", 0, f"Original approved configuration: {key}={target['old']}. This was the initial design."),
        ("policy-current", 10, f"Approved configuration: {key}={target['current']}. {f['explanation']} This replaces the initial design."),
        ("boundary-memo", 11, BOUNDARIES[target["project"]]),
        ("sibling-field", 12, f"Approved configuration: {sibling}={target['sibling']}. This is a separate field identity."),
        ("mutable-config", 13 + 200 * bool(revision and mutable), f"Approved configuration: {config}={value}. This is the current resource allocation."),
        ("parallel-approval-a", 20, f"Approved configuration: {conflict}={target['conflict'][0]}. Record A has no precedence over record B."),
        ("parallel-approval-b", 20, f"Approved configuration: {conflict}={target['conflict'][1]}. Record B has no precedence over record A."),
        ("quoted-example", 31, f"The manual quotes “Approved configuration: {key}=7001.” That sentence is an example, not an approval for this project."),
        ("conditional-proposal", 32, f"If the isolated canary succeeds, {key}=7002 may be proposed. This condition has not been met; no change was approved."),
        ("denied-value", 33, f"The setting {key} is not 7003. Do not treat that value as an approved configuration."),
        ("withdrawn-proposal", 34, f"The proposal {key}=7004 has been revoked. This withdrawn proposal does not replace the approved configuration."),
        ("inspection-report", 35, f"Inspected {key} during the recovery review. No configuration change was approved. The deployment checklist passed."),
        ("namespace-note", 36, f"The identifiers {key} and {sibling} belong to different fields. Their values are not interchangeable."),
        ("operations-note", 37, "Recovery logs are retained by session and project. An identifier match alone is not a source authority decision."),
        ("historical-test", 3, "The first recovery prototype skipped an acknowledgement barrier. The regression log records that rejected implementation."),
        ("handoff", 38, f"Resume {f['title']}. Read the approved configuration and the separate boundary memo together before coding."),
    ]
    rows = []
    for sid, day, body in contents:
        if deleted and mutable and sid == "mutable-config":
            continue
        rows.append(session(target["project"], target["family"], sid,
                            [(f"Record {f['title']} {sid.replace('-', ' ')}.", body)],
                            date(target["lifecycle"], day, shift_days)))
    return rows


def filler_session(project, family, sid, count, ordinal, lifecycle, shift_days=0, foreign=False):
    f = FAMILIES[family]
    pairs = []
    for i in range(count):
        nonce = int(hashlib.sha256(encoded([SEED, project, sid, i])).hexdigest()[:8], 16)
        if foreign:
            answer = (f"Approved configuration: {f['field']}={100000 + nonce % 1000000}. "
                      f"Approved configuration: {f['missing']}={3000000 + nonce % 1000000}. "
                      "This approval belongs only to the explicitly named project. "
                      "Checkpoint replay sampling recovery boundary configuration maintenance.")
        elif i % 8 == 0:
            answer = (f"If a future recovery canary succeeds, {f['field']}={8000 + nonce % 1000} could be proposed. "
                      "No change is approved by this maintenance record; keep the recorded decision.")
        else:
            answer = (f"Inspected {f['field']}, {f['sibling']} and {f['config']} while replaying the recovery checklist. "
                      "No configuration change was approved. This is a maintenance observation. "
                      f"Diagnostic sample number {nonce}; checkpoint replay sampling boundary configuration.")
        pairs.append((f"{f['title']} maintenance observation {nonce}.", answer))
    return session(project, family, sid, pairs, date(lifecycle, ordinal, shift_days))


def descriptors(spec):
    rows = []
    deleted = bool(spec.get("deleted", False))
    for target in TARGETS:
        for source in core_sessions(target, spec.get("revision", 0), spec.get("shift_days", 0), deleted):
            rows.append((target["project"], source["session_id"], "core", 0, 1))
        count = target["pages"] - CORE_TURNS
        for block in range((count + PAGES_PER_SESSION - 1) // PAGES_PER_SESSION):
            rows.append((target["project"], f"archive-{block:06d}", "archive", block,
                         min(PAGES_PER_SESSION, count - block * PAGES_PER_SESSION)))
    for block in range((spec["foreign_pages"] + PAGES_PER_SESSION - 1) // PAGES_PER_SESSION):
        family = tuple(FAMILIES)[(block // 2) % len(FAMILIES)]
        project = f"{family}-similar-{block // 2:06d}"
        rows.append((project, f"maintenance-{block % 2}", "foreign", block,
                     min(PAGES_PER_SESSION, spec["foreign_pages"] - block * PAGES_PER_SESSION)))
    for block in range((spec["own_pages"] + PAGES_PER_SESSION - 1) // PAGES_PER_SESSION):
        target = GROWING[block % len(GROWING)]
        rows.append((target["project"], f"growth-{block // len(GROWING):06d}", "own", block,
                     min(PAGES_PER_SESSION, spec["own_pages"] - block * PAGES_PER_SESSION)))
    if spec["layout"] == "interleaved":
        rows.sort(key=lambda d: hashlib.sha256(encoded([SEED, d[0], d[1]])).digest())
    elif spec["layout"] != "clustered":
        raise ValueError("Unknown layout")
    return rows


def source_for(spec, project, sid):
    target = next((t for t in TARGETS if t["project"] == project), None)
    shift = spec.get("shift_days", 0)
    if target:
        for source in core_sessions(target, spec.get("revision", 0), shift, spec.get("deleted", False)):
            if source["session_id"] == sid:
                return source
        if sid.startswith("archive-"):
            block = int(sid[8:]); remaining = target["pages"] - CORE_TURNS - block * PAGES_PER_SESSION
            if block >= 0 and sid == f"archive-{block:06d}" and remaining > 0:
                return filler_session(project, target["family"], sid, min(PAGES_PER_SESSION, remaining),
                                      100 + block, target["lifecycle"], shift)
        if sid.startswith("growth-") and target in GROWING:
            block = int(sid[7:]) * len(GROWING) + GROWING.index(target)
            remaining = spec["own_pages"] - block * PAGES_PER_SESSION
            if block >= 0 and sid == f"growth-{block // len(GROWING):06d}" and remaining > 0:
                return filler_session(project, target["family"], sid, min(PAGES_PER_SESSION, remaining),
                                      300 + block // len(GROWING), target["lifecycle"], shift)
    if "-similar-" in project and sid.startswith("maintenance-"):
        index = int(project.rsplit("-", 1)[1]); part = int(sid.removeprefix("maintenance-"))
        block = index * 2 + part
        family = tuple(FAMILIES)[index % len(FAMILIES)]
        remaining = spec["foreign_pages"] - block * PAGES_PER_SESSION
        if part in (0, 1) and project == f"{family}-similar-{index:06d}" and remaining > 0:
            return filler_session(project, family, sid, min(PAGES_PER_SESSION, remaining),
                                  100 + index % 365, "foreign", shift, foreign=True)
    raise KeyError((project, sid))


def sessions(spec):
    for project, sid, _kind, _block, _count in descriptors(spec):
        yield source_for(spec, project, sid)


def cases(spec=None):
    spec = spec or {"revision": 0, "deleted": False}
    output = []
    categories = ("current", "joint_chinese", "historical", "sibling_identifier",
                  "review_guard", "same_time_conflict", "missing", "mutable_config")
    for target in TARGETS:
        family = FAMILIES[target["family"]]
        current = ("policy-current", f"{family['field']}={target['current']}")
        old = ("design-original", f"{family['field']}={target['old']}")
        mutable = target in GROWING
        config = target["config"] + (1000 if spec.get("revision") and mutable else 0)
        requirements = [
            [current], [current, ("boundary-memo", BOUNDARIES[target["project"]])], [old],
            [("sibling-field", f"{family['sibling']}={target['sibling']}")], [current],
            [("parallel-approval-a", f"{family['conflict']}={target['conflict'][0]}"),
             ("parallel-approval-b", f"{family['conflict']}={target['conflict'][1]}")], [],
            [] if spec.get("deleted") and mutable else [("mutable-config", f"{family['config']}={config}")],
        ]
        for index, (category, query, required) in enumerate(zip(categories, QUESTIONS[target["project"]], requirements)):
            stale = [old] if category in ("current", "joint_chinese", "review_guard") else []
            output.append({"id": target["project"] + ":" + category, "project": target["project"],
                           "family": target["family"], "lifecycle": target["lifecycle"], "category": category,
                           "surface": "recall", "query": query,
                           "required": [{"session_id": sid, "turn_index": 0, "quote": quote} for sid, quote in required],
                           "stale": [{"session_id": sid, "turn_index": 0, "quote": quote} for sid, quote in stale],
                           "single_current_first": category in ("current", "review_guard"),
                           "conflict_sources_required": category == "same_time_conflict",
                           "must_not_claim_unique_current": category in ("same_time_conflict", "missing")
                           or (category == "mutable_config" and not required)})
        output.append({"id": target["project"] + ":directory", "project": target["project"],
                       "family": target["family"], "lifecycle": target["lifecycle"], "category": "directory",
                       "surface": "directory", "query": family["title"] + " approved configuration boundary",
                       "required": [{"session_id": current[0], "turn_index": 0, "quote": current[1]}],
                       "stale": [], "single_current_first": False, "conflict_sources_required": False,
                       "must_not_claim_unique_current": False})
    return output


def checkpoints():
    rows = [
        ("age-reference-2048", "age", 2048, 0, 0, "clustered", 0, False, None),
        ("age-shift-2048", "age", 2048, 0, 3650, "clustered", 0, False, None),
        ("foreign-10240", "foreign", 10240, 0, 0, "clustered", 0, False, "age-reference-2048"),
        ("foreign-51200", "foreign", 51200, 0, 0, "clustered", 0, False, "foreign-10240"),
        ("foreign-100000", "foreign", 100000, 0, 0, "clustered", 0, False, "foreign-51200"),
        ("foreign-200000", "foreign", 200000, 0, 0, "clustered", 0, False, "foreign-100000"),
        ("own-100000", "own", 100000, 48800, 0, "clustered", 0, False, "foreign-51200"),
        ("interleaved-100000", "layout", 100000, 48800, 0, "interleaved", 0, False, None),
        ("replacement-100000", "replacement", 100000, 48800, 0, "interleaved", 1, False, "interleaved-100000"),
        ("deletion-99997", "deletion", 99997, 48800, 0, "interleaved", 1, True, "replacement-100000"),
    ]
    return [{"id": name, "axis": axis, "total_pages": total, "foreign_pages": total - TARGET_PAGES - own + (3 if deleted else 0),
             "own_pages": own, "shift_days": shift, "layout": layout, "revision": revision,
             "deleted": deleted, "parent": parent} for name, axis, total, own, shift, layout, revision, deleted, parent in rows]


def mutation_sources(spec):
    """Public-API mutation instructions; never delete source-table rows directly."""
    return [{"project": target["project"], "session_id": "mutable-config",
             "replacement": source_for({**spec, "revision": 1, "deleted": False}, target["project"], "mutable-config")}
            for target in GROWING]


def with_foreign_write(spec, batches):
    if not 0 <= batches <= 20:
        raise ValueError("Unregistered foreign-write checkpoint")
    return {**spec, "id": spec["id"] + f"-foreign-write-{batches:02d}",
            "foreign_pages": spec["foreign_pages"] + batches * PAGES_PER_SESSION,
            "total_pages": spec["total_pages"] + batches * PAGES_PER_SESSION}
