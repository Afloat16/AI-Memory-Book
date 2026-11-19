"""Frozen synthetic engineering histories for the v0.13 scale diagnostic.

This module creates source conversations and separate evaluator labels. It
imports no retriever. Every generated turn is ingested through MemoryBook;
there are no direct INSERTs into pages or retrieval indexes. The deliberately
selected ``turn`` segmentation gives one real stored page per conversation
turn. This is a scale/control diagnostic, not an adaptive-segmentation study.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json


VERSION = "v013-long-history-workload-1"
SEED = 1301729
CORE_PAGES = 128
PAGES_PER_SESSION = 32
FAMILIES = {
    "routing": {"key": "edge_policy", "old": "reject_negative", "new": "bellman_ford",
                "symbol": "routing.relaxation_limit", "zh": "图路径",
                "boundary": "A negative cycle must raise ValueError; unreachable vertices keep infinity.",
                "failure": "The visited-once Dijkstra prototype returned 2 instead of -1 on a negative edge."},
    "ranking": {"key": "tie_policy", "old": "stable_input", "new": "id_ascending",
                "symbol": "ranking.stable_topk_buffer", "zh": "候选排序",
                "boundary": "A request with k=0 returns an empty list; tied scores retain the approved tie policy.",
                "failure": "Converting tied candidates to a set changed the winner across repeated requests."},
    "training": {"key": "split_policy", "old": "row_modulo", "new": "whole_group",
                 "symbol": "training.group_split_seed", "zh": "训练划分",
                 "boundary": "No patient group may cross train and validation; each record appears exactly once.",
                 "failure": "A row-wise split leaked repeated patient records into both train and validation."},
    "attention": {"key": "all_masked_policy", "old": "uniform", "new": "zeros",
                  "symbol": "attention.mask_tile_size", "zh": "注意力算子",
                  "boundary": "Masked positions are zero; subtract the maximum before exponentiation.",
                  "failure": "Subtracting negative infinity produced NaN for a completely masked row."},
}

# Identical human-facing project/task names deliberately coexist with different
# exact project IDs, dates, approved policies, and numeric parameter values.
TARGETS = (
    {"project": "routing-archive", "family": "routing", "lifecycle": "inactive", "variant": 0},
    {"project": "routing-core", "family": "routing", "lifecycle": "long_lived", "variant": 1},
    {"project": "ranking-archive", "family": "ranking", "lifecycle": "inactive", "variant": 0},
    {"project": "ranking-next", "family": "ranking", "lifecycle": "newcomer", "variant": 1},
    {"project": "training-core", "family": "training", "lifecycle": "long_lived", "variant": 0},
    {"project": "training-next", "family": "training", "lifecycle": "newcomer", "variant": 1},
    {"project": "attention-core", "family": "attention", "lifecycle": "long_lived", "variant": 0},
    {"project": "attention-next", "family": "attention", "lifecycle": "newcomer", "variant": 1},
)
GROWING = tuple(t for t in TARGETS if t["lifecycle"] != "inactive")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def source_turn(messages, index):
    """Independent source reconstruction for our alternating user/assistant input."""
    pair = messages[2 * index:2 * index + 2]
    if len(pair) != 2 or [m["role"] for m in pair] != ["user", "assistant"]:
        raise ValueError("Generator source must have alternating user and assistant turns")
    return "\n\n".join(m["role"].upper() + ": " + m["content"] for m in pair)


def _date(lifecycle, ordinal=0, shift_days=0):
    origin = {"inactive": "2012-01-01", "long_lived": "2017-01-01",
              "newcomer": "2025-01-01", "background": "2020-01-01"}[lifecycle]
    value = datetime.fromisoformat(origin).replace(tzinfo=timezone.utc)
    return (value + timedelta(days=ordinal - shift_days)).isoformat(timespec="seconds")


def _session(project, family, sid, title, pairs, date, task="kernel-contract"):
    return {"project": project, "project_name": family + " compute pipeline",
            "session_id": sid, "title": title, "task_id": task,
            "task_title": family + " compute pipeline " + task.replace("-", " "),
            "created_at": date,
            "messages": [{"role": role, "content": text} for q, a in pairs
                         for role, text in (("user", q), ("assistant", a))]}


def core_sessions(target, revision=0, shift_days=0):
    """Six evidence sources and ten realistic, non-authoritative maintenance notes."""
    if revision not in (0, 1):
        raise ValueError("Unknown source revision")
    family = target["family"]
    spec = FAMILIES[family]
    old, current = ((spec["old"], spec["new"]) if not target["variant"]
                    else (spec["new"], spec["old"]))
    number = next(i for i, row in enumerate(TARGETS) if row["project"] == target["project"])
    changed = revision if target["lifecycle"] != "inactive" else 0
    value = 64 + number * 17 + changed * 1000
    rows = [
        ("original-policy", "Original " + family + " implementation decision",
         f"Original approved contract: {spec['key']}={old}. This is historical evidence, superseded by a later approved contract."),
        ("current-policy", "Approved current " + family + " implementation contract",
         f"Approved current contract: {spec['key']}={current}. This decision replaces the original policy and remains active until explicitly revised. "
         f"中文复核记录：当前生效约定为 {spec['key']}={current}。后续维护讨论本身不构成修订。"),
        ("active-config", "Configure " + spec["symbol"],
         f"Approved configuration: {spec['symbol']}={value}. This exact value applies only to this project. Configuration revision {changed}."),
        ("boundary-contract", "Review " + family + " boundary constraints", spec["boundary"]),
        ("failed-prototype", "Why did the " + family + " prototype fail?", spec["failure"]),
        ("handoff", "Resume " + family + " after a long interruption",
         "Continue from the approved implementation contract and recorded failure. This handoff changes no policy or numeric setting."),
    ]
    for i in range(10):
        rows.append((f"maintenance-{i:02d}", f"{family} regression review {i}",
                     f"Reviewed {spec['key']} and {spec['symbol']} logs. The deployment checklist passed. "
                     "This maintenance discussion proposes no approved policy or parameter change."))
    result = []
    for ordinal, (sid, question, answer) in enumerate(rows):
        day = ordinal * 7 + (180 if sid == "active-config" and changed else 0)
        result.append(_session(target["project"], family, sid, question,
                               [(question, answer)], _date(target["lifecycle"], day, shift_days)))
    return result


def background_session(block, kind, shift_days=0, seed=SEED):
    """32 genuine turns; shared identifiers and different project-local values."""
    if kind == "foreign":
        project_index, sub = divmod(block, 2)
        family = tuple(FAMILIES)[project_index % len(FAMILIES)]
        project = f"{family}-similar-{project_index:06d}"
        sid = f"maintenance-{sub:06d}"
        life = "background"
        base = 100_000 + project_index * 128 + sub * PAGES_PER_SESSION
        day = 1200 + project_index % 900
    elif kind == "own":
        target = GROWING[block % len(GROWING)]
        sub = block // len(GROWING)
        project, family, life = target["project"], target["family"], target["lifecycle"]
        sid = f"growth-{sub:06d}"
        base = 500_000 + block * PAGES_PER_SESSION
        day = (3000 if life == "long_lived" else 200) + sub % 180
    else:
        raise ValueError("Unknown history axis")
    spec = FAMILIES[family]
    pairs = []
    for turn in range(PAGES_PER_SESSION):
        nonce = int(hashlib.sha256(f"{seed}:{kind}:{block}:{turn}".encode()).hexdigest()[:6], 16)
        question = f"{family} kernel deployment review {sub} item {turn}"
        if kind == "foreign":
            answer = (f"Approved project-local configuration: {spec['symbol']}={base + turn}. "
                      f"The {spec['key']} contract is {spec['old'] if turn % 2 else spec['new']}. "
                      f"Regression request {nonce} uses this project's compute pipeline.")
        else:
            answer = (f"Review {spec['key']} and {spec['symbol']} in the compute pipeline. "
                      f"Unapproved experiment {nonce} considered {spec['symbol']}={base + turn}. "
                      "This experiment is not an approved replacement for the recorded implementation contract.")
        pairs.append((question, answer))
    return _session(project, family, sid, family + " kernel maintenance", pairs,
                    _date(life, day, shift_days), task="kernel-contract")


def sessions(spec, *, seed=SEED):
    """Yield the same logical source set in clustered or round-robin ingestion order."""
    foreign = spec["foreign_pages"] // PAGES_PER_SESSION
    own = spec["own_pages"] // PAGES_PER_SESSION
    if spec["foreign_pages"] % PAGES_PER_SESSION or spec["own_pages"] % PAGES_PER_SESSION:
        raise ValueError("Background counts must be complete 32-turn sessions")
    if spec["layout"] not in ("clustered", "interleaved"):
        raise ValueError("Unknown source layout")
    shift = spec.get("shift_days", 0)
    revision = spec.get("revision", 0)
    core = [core_sessions(target, revision, shift) for target in TARGETS]
    if spec["layout"] == "clustered":
        for rows in core:
            yield from rows
        for block in range(foreign):
            yield background_session(block, "foreign", shift, seed)
        for block in range(own):
            yield background_session(block, "own", shift, seed)
    else:
        # Interleave each target's original sessions with both foreign and own
        # history throughout the ingestion stream. Only insertion order differs.
        core_at = {(ordinal * max(foreign, own, 16)) // 16: ordinal for ordinal in range(16)}
        for block in range(max(foreign, own, 16)):
            if block in core_at:
                for rows in core:
                    yield rows[core_at[block]]
            if block < foreign:
                yield background_session(block, "foreign", shift, seed)
            if block < own:
                yield background_session(block, "own", shift, seed)


def cases(revision=0):
    """Gold is used only after retrieval; no quotes/IDs are injected into requests."""
    output = []
    for target in TARGETS:
        sources = {row["session_id"]: row for row in core_sessions(target, revision)}
        spec = FAMILIES[target["family"]]
        current = spec["new"] if not target["variant"] else spec["old"]
        old = spec["old"] if not target["variant"] else spec["new"]
        config = sources["active-config"]["messages"][1]["content"].split("Approved configuration: ", 1)[1].split(". This exact", 1)[0]

        def add(kind, query, requirements, surface="recall", stale=()):
            output.append({"id": target["project"] + ":" + kind,
                           "project": target["project"], "lifecycle": target["lifecycle"],
                           "family": target["family"], "category": kind, "surface": surface,
                           "query": query,
                           "required": [{"session_id": sid, "turn_index": 0, "quote": quote}
                                        for sid, quote in requirements],
                           "stale": [{"session_id": sid, "turn_index": 0, "quote": quote}
                                     for sid, quote in stale]})

        present = [("current-policy", f"{spec['key']}={current}")]
        superseded = [("original-policy", f"{spec['key']}={old}")]
        add("current", f"What is the current {spec['key']} implementation contract?", present, stale=superseded)
        add("historical", f"What was the original {spec['key']} implementation decision?", superseded)
        add("identifier", f"What is the approved `{spec['symbol']}` value?", [("active-config", config)])
        add("multi_source", f"What is the current {spec['key']} and which boundary constraints must pass?",
            present + [("boundary-contract", spec["boundary"])], stale=superseded)
        add("chinese", f"中断很久后继续开发{spec['zh']}，当前 {spec['key']} 应当采用什么约定？请回查原始依据。",
            [("current-policy", f"当前生效约定为 {spec['key']}={current}。")], stale=superseded)
        add("failure", f"Why did the {target['family']} prototype fail and what mistake should we avoid?",
            [("failed-prototype", spec["failure"])])
        add("replacement", f"Find the currently approved configuration for {spec['symbol']} in this project.",
            [("active-config", config)])
        add("missing", "What approved distributed_all_reduce_bucket_bytes value should this project deploy?", [])
        add("directory", target["family"] + " approved implementation contract", present,
            surface="directory", stale=superseded)
    return output


def checkpoints(profile="main"):
    """Requested scale floors rounded to complete 32-turn source sessions."""
    if profile not in ("main", "expanded"):
        raise ValueError("Unknown registered resource profile")
    points = [
        ("age-reference-1024", "age", 896, 0, 0, "clustered", 0, None),
        ("age-shift-1024", "age", 896, 0, 3650, "clustered", 0, None),
        ("foreign-10016", "foreign", 9888, 0, 0, "clustered", 0, "age-reference-1024"),
        ("foreign-50016", "foreign", 49888, 0, 0, "clustered", 0, "foreign-10016"),
        ("own-100000", "own", 49888, 49984, 0, "clustered", 0, "foreign-50016"),
        ("interleaved-100000", "layout", 49888, 49984, 0, "interleaved", 0, None),
        ("replacement-100000", "replacement", 49888, 49984, 0, "interleaved", 1, "interleaved-100000"),
    ]
    if profile == "expanded":
        points += [
            ("foreign-150016", "foreign_extension", 99904, 49984, 0, "interleaved", 1, "replacement-100000"),
            ("own-200000", "own_extension", 99904, 99968, 0, "interleaved", 1, "foreign-150016"),
        ]
    return [{"id": name, "axis": axis, "foreign_pages": foreign, "own_pages": own,
             "total_pages": CORE_PAGES + foreign + own, "shift_days": age,
             "layout": layout, "revision": revision, "parent": parent}
            for name, axis, foreign, own, age, layout, revision, parent in points]


def source_for(spec, project, sid, *, seed=SEED):
    """Reconstruct a requested original without loading the whole source corpus."""
    target = next((t for t in TARGETS if t["project"] == project), None)
    if target:
        core = next((s for s in core_sessions(target, spec.get("revision", 0), spec.get("shift_days", 0))
                     if s["session_id"] == sid), None)
        if core:
            return core
        if sid.startswith("growth-") and target in GROWING:
            sub = int(sid.removeprefix("growth-"))
            block = sub * len(GROWING) + GROWING.index(target)
            if 0 <= block < spec["own_pages"] // PAGES_PER_SESSION:
                return background_session(block, "own", spec.get("shift_days", 0), seed)
    if "-similar-" in project and sid.startswith("maintenance-"):
        project_index = int(project.rsplit("-", 1)[1])
        block = project_index * 2 + int(sid.removeprefix("maintenance-"))
        if 0 <= block < spec["foreign_pages"] // PAGES_PER_SESSION:
            source = background_session(block, "foreign", spec.get("shift_days", 0), seed)
            if source["project"] == project and source["session_id"] == sid:
                return source
    raise KeyError((project, sid))
