"""New v0.14 authored transfer and scale controls; v0.13 fixtures stay frozen.

This is synthetic development evidence, not an untouched real-project holdout.
Eight legacy targets remain byte-identical to the v0.13 corpus. Four new
targets have independently written lease/compaction contracts and queries.
Every stored page is produced through the public ingestion API by the runner.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from benchmarks import v013_workload as legacy

VERSION = "v014-longitudinal-transfer-1"
SEED = 1401973
PAGES_PER_SESSION = 32
TRANSFER_TARGETS = (
    {"project": "lease-archive", "family": "lease", "lifecycle": "inactive", "variant": 0},
    {"project": "lease-live", "family": "lease", "lifecycle": "long_lived", "variant": 1},
    {"project": "compaction-archive", "family": "compaction", "lifecycle": "inactive", "variant": 0},
    {"project": "compaction-live", "family": "compaction", "lifecycle": "long_lived", "variant": 1},
)
TARGETS = (*legacy.TARGETS, *TRANSFER_TARGETS)
CORE_PAGES = 16 * len(TARGETS)
TRANSFER = {
    "lease": {
        "field": "lease_expiry_policy", "old": "client_clock", "new": "monotonic_server",
        "symbol": "lease.renewal_margin_ms", "zh": "租约",
        "boundary": "An expired lease cannot renew; fencing tokens must increase for every new owner.",
        "failure": "A delayed renewal from the former owner overwrote a newer writer after clock skew.",
    },
    "compaction": {
        "field": "tombstone_retention_policy", "old": "drop_on_merge", "new": "snapshot_watermark",
        "symbol": "compaction.retained_generations", "zh": "存储压缩",
        "boundary": "A live snapshot must still read its original version; tombstones survive until all older snapshots close.",
        "failure": "Discarding a tombstone during compaction resurrected a deleted key in an older segment.",
    },
}
encoded, digest, source_turn = legacy.encoded, legacy.digest, legacy.source_turn


def transfer_sessions(target, revision=0, shift_days=0):
    spec = TRANSFER[target["family"]]
    old, current = ((spec["old"], spec["new"]) if not target["variant"]
                    else (spec["new"], spec["old"]))
    number = TRANSFER_TARGETS.index(target)
    value = 23 + 19 * number + 1000 * revision
    rows = [
        ("original-policy", "First design approval", f"Originally approved: {spec['field']}={old}. A later contract superseded this design."),
        ("current-policy", "Accepted implementation contract", f"Approved current contract: {spec['field']}={current}. This is the active decision. 中文签核：当前生效配置为 {spec['field']}={current}。"),
        ("active-config", "Accepted numerical configuration", f"Approved configuration: {spec['symbol']}={value}. Keep this project-local setting until the next approved revision."),
        ("boundary-contract", "Boundary invariants", spec["boundary"]),
        ("failed-prototype", "Previous implementation failure", spec["failure"]),
        ("handoff", "Maintainer handoff", "Resume the signed contract, boundary invariants and original failure evidence. No parameter changed at this handoff."),
    ]
    rows.extend((f"maintenance-{i:02d}", "Routine implementation review",
                 f"Reviewed {spec['field']} and {spec['symbol']} logs. This is a monitoring note, not an approved configuration change.")
                for i in range(10))
    start = datetime(2011 if target["lifecycle"] == "inactive" else 2018, 1, 1, tzinfo=timezone.utc)
    for ordinal, (sid, title, body) in enumerate(rows):
        question = f"{target['family']} {title.lower()}"
        date = start + timedelta(days=ordinal * 11 - shift_days + (300 if revision and sid == "active-config" else 0))
        yield {"project": target["project"], "project_name": target["family"] + " engine",
               "session_id": sid, "title": question, "task_id": "engine-contract",
               "task_title": target["family"] + " engine implementation",
               "created_at": date.isoformat(timespec="seconds"),
               "messages": [{"role": "user", "content": question}, {"role": "assistant", "content": body}]}


def _is_deleted(spec, project, sid):
    return bool(spec.get("delete_config")) and project in {t["project"] for t in TARGETS} and sid == "active-config"


def core_sources(spec):
    for target in legacy.TARGETS:
        for row in legacy.core_sessions(target, spec.get("revision", 0), spec.get("shift_days", 0)):
            if not _is_deleted(spec, row["project"], row["session_id"]):
                yield row
    for target in TRANSFER_TARGETS:
        for row in transfer_sessions(target, spec.get("revision", 0), spec.get("shift_days", 0)):
            if not _is_deleted(spec, row["project"], row["session_id"]):
                yield row


def background_session(block, kind, shift_days=0):
    source = legacy.background_session(block, kind, shift_days, SEED)
    project_index, sub = divmod(block, 2)
    if kind != "foreign" or project_index % 3 != 2:
        return source
    family_name = tuple(TRANSFER)[(project_index // 3) % len(TRANSFER)]
    family = TRANSFER[family_name]
    source.update(project=f"{family_name}-transfer-foreign-{project_index:06d}",
                  project_name=family_name + " engine", title=family_name + " engine maintenance",
                  task_title=family_name + " engine implementation", task_id="engine-contract")
    source["messages"] = []
    for turn in range(32):
        question = f"{family_name} deployment review {sub} item {turn}"
        answer = (f"Approved project-local setting: {family['symbol']}={100000 + block * 32 + turn}. "
                  f"Approved {family['field']}={family['old'] if turn % 2 else family['new']}. "
                  "This contract belongs to this separate engine project.")
        source["messages"].extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    return source


def sessions(spec):
    foreign, own = spec["foreign_pages"] // 32, spec["own_pages"] // 32
    if spec["foreign_pages"] % 32 or spec["own_pages"] % 32:
        raise ValueError("History must consist of whole 32-turn sessions")
    core = list(core_sources(spec))
    shift = spec.get("shift_days", 0)
    if spec["layout"] == "clustered":
        yield from core
        for block in range(foreign):
            yield background_session(block, "foreign", shift)
        for block in range(own):
            yield background_session(block, "own", shift)
    elif spec["layout"] == "interleaved":
        total = max(foreign, own, len(core))
        positions = {i * total // len(core): row for i, row in enumerate(core)}
        for block in range(total):
            if block in positions:
                yield positions[block]
            if block < foreign:
                yield background_session(block, "foreign", shift)
            if block < own:
                yield background_session(block, "own", shift)
    else:
        raise ValueError("Unknown layout")


def source_for(spec, project, sid):
    if _is_deleted(spec, project, sid):
        raise KeyError("Deleted original source")
    target = next((t for t in TRANSFER_TARGETS if t["project"] == project), None)
    if target:
        row = next((r for r in transfer_sessions(target, spec.get("revision", 0), spec.get("shift_days", 0))
                    if r["session_id"] == sid), None)
        if row is None:
            raise KeyError((project, sid))
        return row
    if ("-similar-" in project or "-transfer-foreign-" in project) and sid.startswith("maintenance-"):
        project_index = int(project.rsplit("-", 1)[1])
        block = project_index * 2 + int(sid.removeprefix("maintenance-"))
        if 0 <= block < spec["foreign_pages"] // 32:
            row = background_session(block, "foreign", spec.get("shift_days", 0))
            if row["project"] == project and row["session_id"] == sid:
                return row
        raise KeyError((project, sid))
    return legacy.source_for(spec, project, sid, seed=SEED)


def cases(spec=None):
    spec = spec or {"revision": 0}
    revision = spec.get("revision", 0)
    result = [dict(c, cohort="legacy-v013") for c in legacy.cases(revision)]
    for target in TRANSFER_TARGETS:
        family = TRANSFER[target["family"]]
        sources = {r["session_id"]: r for r in transfer_sessions(target, revision)}
        current = family["new"] if not target["variant"] else family["old"]
        old = family["old"] if not target["variant"] else family["new"]
        config = sources["active-config"]["messages"][1]["content"].split("Approved configuration: ")[1].split(". Keep")[0]

        def add(category, query, requirements, surface="recall", stale=()):
            result.append({"id": target["project"] + ":" + category, "project": target["project"],
                "family": target["family"], "lifecycle": target["lifecycle"], "category": category,
                "cohort": "authored-transfer-v014", "surface": surface, "query": query,
                "required": [{"session_id": sid, "turn_index": 0, "quote": quote} for sid, quote in requirements],
                "stale": [{"session_id": sid, "turn_index": 0, "quote": quote} for sid, quote in stale]})

        current_req = [("current-policy", f"{family['field']}={current}")]
        old_req = [("original-policy", f"{family['field']}={old}")]
        add("current", f"Which {family['field']} contract is currently approved for implementation?", current_req, stale=old_req)
        add("historical", f"Find the originally approved {family['field']} design before it was superseded.", old_req)
        add("identifier", f"What value was approved for `{family['symbol']}`?", [("active-config", config)])
        add("multi_source", f"Which current {family['field']} contract and boundary invariants must the implementation satisfy?", current_req + [("boundary-contract", family["boundary"])], stale=old_req)
        add("chinese", f"继续旧的{family['zh']}工程，当前 {family['field']} 的生效配置是什么？请给出原始签核依据。", [("current-policy", f"当前生效配置为 {family['field']}={current}。")], stale=old_req)
        add("failure", f"What was the earlier {target['family']} implementation failure and what must not happen again?", [("failed-prototype", family["failure"])])
        add("replacement", f"Retrieve the current approved {family['symbol']} configuration.", [("active-config", config)])
        add("missing", "Which approved erasure_recovery_quorum value is deployed here?", [])
        add("directory", target["family"] + " accepted implementation contract", current_req, "directory", old_req)
    if spec.get("delete_config"):
        result = [dict(c, required=[], deleted_source="active-config")
                  if c["category"] in {"identifier", "replacement"} else c for c in result]
    return result


def checkpoints(profile="main"):
    if profile not in {"smoke", "main", "expanded"}:
        raise ValueError("Unknown profile")
    foreign = [64, 320, 832] if profile == "smoke" else [832, 9824, 49824]
    own = 384 if profile == "smoke" else 50016
    rows = [
        ("reference", "reference", foreign[0], 0, 0, "clustered", 0, False, None),
        ("aged", "timestamp_age_only", foreign[0], 0, 7300, "clustered", 0, False, None),
        ("foreign_medium", "foreign_growth", foreign[1], 0, 0, "clustered", 0, False, "reference"),
        ("foreign_large", "foreign_growth", foreign[2], 0, 0, "clustered", 0, False, "foreign_medium"),
        ("own_large", "own_history_growth", foreign[2], own, 0, "clustered", 0, False, "foreign_large"),
        ("interleaved", "physical_layout", foreign[2], own, 0, "interleaved", 0, False, None),
        ("replacement", "source_replacement", foreign[2], own, 0, "interleaved", 1, False, "interleaved"),
        ("deletion", "source_deletion", foreign[2], own, 0, "interleaved", 1, True, "replacement"),
    ]
    if profile == "expanded":
        rows.append(("foreign_expanded", "foreign_growth_extension", 149824, own, 0, "interleaved", 1, True, "deletion"))
    return [{"id": name, "axis": axis, "foreign_pages": foreign_count, "own_pages": own_count,
             "total_pages": CORE_PAGES + foreign_count + own_count - (len(TARGETS) if deleted else 0),
             "shift_days": age, "layout": layout, "revision": revision, "delete_config": deleted,
             "parent": parent} for name, axis, foreign_count, own_count, age, layout, revision, deleted, parent in rows]
