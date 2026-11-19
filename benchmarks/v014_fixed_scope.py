"""Supplementary pure-foreign growth control using the unchanged v014 worker.

The original nine-stage experiment remains frozen. This separate protocol
repeats a matched 1k/50k/200k series while every target remains at 16 pages with
identical original sources, source timestamps, page identities and queries.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import v014_scale as scale
from benchmarks.v014_workload import SEED, TARGETS, cases, digest, encoded

PROTOCOL = "v014-fixed-target-foreign-growth-1"
PLAN_RELATIVE = "benchmarks/experiments/v014-fixed-scope-plan.json"
PLAN = ROOT / PLAN_RELATIVE
FROZEN = ("benchmarks/v014_fixed_scope.py", "benchmarks/v014_fixed_scope_audit.py",
          PLAN_RELATIVE, "tests/test_v014_fixed_scope.py")


def settings():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan["protocol"] != PROTOCOL or plan["seed"] != SEED:
        raise ValueError("Supplementary protocol/seed mismatch")
    if plan["worker_evaluator"] != scale.protocol_identity():
        raise ValueError("Frozen original v014 worker/evaluator changed")
    if plan["performance_cases"] != list(scale.PERFORMANCE):
        raise ValueError("Frozen performance cases changed")
    for profile in plan["profiles"]:
        specs = checkpoints(profile, plan)
        if len(specs) != 3 or any(len(cases(spec)) != 108 for spec in specs):
            raise ValueError("Unexpected supplementary matrix")
        if len({digest(cases(spec)) for spec in specs}) != 1:
            raise ValueError("Queries/gold vary across pure-foreign stages")
        if expected_records(profile, plan) != plan["profiles"][profile]["expected_records"]:
            raise ValueError("Registered record count differs from executable loops")
    return plan


def checkpoints(profile, plan=None):
    plan = json.loads(PLAN.read_text()) if plan is None else plan
    if profile not in plan["profiles"]:
        raise ValueError("Unknown supplementary profile")
    result, previous = [], None
    for name, total in zip(("reference", "foreign_large", "foreign_200k"),
                           plan["profiles"][profile]["total_pages"]):
        if type(total) is not int or total < 192 or (total - 192) % 32:
            raise ValueError("Supplementary growth must contain whole foreign sessions")
        result.append({"id": name, "axis": "reference" if previous is None else "pure_foreign_growth",
            "foreign_pages": total - 192, "own_pages": 0, "total_pages": total,
            "shift_days": 0, "layout": "clustered", "revision": 0,
            "delete_config": False, "parent": previous})
        previous = name
    if [s["total_pages"] for s in result] != sorted(s["total_pages"] for s in result):
        raise ValueError("Foreign history must grow monotonically")
    return result


def expected_records(profile, plan=None):
    plan = json.loads(PLAN.read_text()) if plan is None else plan
    p = plan["profiles"][profile]
    per_block = p["repetitions"] * (9 * (1 + p["warm_calls"]) + 3) + 1
    return 3 * (2 * p["rounds"] * per_block + 2 * (108 + 12 + 2))


def protocol_files_identity():
    """Portable audit identity; the run guard separately requires clean Git HEAD."""
    return {"protocol": PROTOCOL, "files": {p: scale.common.file_sha(ROOT / p) for p in FROZEN}}


def protocol_identity(require_committed=True):
    names = set(scale.common.git(ROOT, "ls-files", "--", *FROZEN).decode().splitlines())
    if require_committed and names != set(FROZEN):
        raise ValueError("Supplementary protocol must be committed before any measurement")
    status = scale.common.git(ROOT, "status", "--porcelain", "--untracked-files=all", "--", *FROZEN).decode()
    if require_committed and status:
        raise ValueError("Supplementary protocol is dirty: " + status)
    return {**protocol_files_identity(), "commit": scale.common.git(ROOT, "rev-parse", "HEAD").decode().strip()}


def target_fingerprint(database):
    """Hash all target original rows, excluding only host-maintenance clocks/rid."""
    targets = sorted(t["project"] for t in TARGETS)
    marks = ",".join("?" for _ in targets)
    direct = {"projects": "id", "chapters": "project_id", "sessions": "project_id", "pages": "project_id"}
    tables = {}
    with closing(sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True)) as db:
        for table in scale.common.SOURCE_TABLES:
            columns = [r[1] for r in db.execute("PRAGMA table_info(" + table + ")")]
            columns = [c for c in columns if c not in scale.common.HOST_COLUMNS.get(table, set())
                       and not (table == "pages" and c == "rid")]
            where = (f'"{direct[table]}" IN ({marks})' if table in direct else
                     f'"session_pk" IN (SELECT id FROM sessions WHERE project_id IN ({marks}))')
            query = "SELECT " + ",".join('"' + c + '"' for c in columns) + " FROM " + table
            query += " WHERE " + where + " ORDER BY id"
            h, count = hashlib.sha256(), 0
            for row in db.execute(query, targets):
                h.update(encoded(list(row)) + b"\n")
                count += 1
            tables[table] = {"columns": columns, "rows": count, "sha256": h.hexdigest()}
        layouts = {project: dict(zip(("pages", "min_rowid", "max_rowid"),
            db.execute("SELECT COUNT(*),MIN(rid),MAX(rid) FROM pages WHERE project_id=?", (project,)).fetchone()))
            for project in targets}
        physical = list(db.execute(f"SELECT rid,id,project_id,session_pk FROM pages WHERE project_id IN ({marks}) ORDER BY rid", targets))
    return {"source_tables": tables, "source_tables_sha256": digest(tables), "target_layout": layouts,
            "physical_target_pages": {"rows": len(physical), "sha256": digest(physical)}}


def verify_target_scope(fingerprint, previous=None):
    if set(fingerprint["target_layout"]) != {t["project"] for t in TARGETS}:
        raise ValueError("Target project inventory changed")
    if any(row["pages"] != 16 for row in fingerprint["target_layout"].values()):
        raise ValueError("A target no longer contains exactly 16 original pages")
    if previous is not None and fingerprint != previous:
        raise ValueError("Target sources, stable metadata, identities or physical placement changed")


def verify_binding(bound, plan):
    if bound["evaluator"] != scale.protocol_identity() or bound["supplementary_evaluator"] != protocol_identity():
        raise ValueError("Bound worker or supplementary protocol changed")
    for arm in ("baseline", "candidate"):
        actual = scale.common.runtime_identity(bound[arm]["repo_root"])
        if actual != bound[arm]:
            raise ValueError("Bound runtime changed: " + arm)
        for field, expected in plan["runtimes"][arm].items():
            if actual[field] != expected:
                raise ValueError("Runtime differs from pre-registered identity: " + arm + ":" + field)


def summarize(output):
    result = scale.summarize(output)
    result["supplementary_protocol"] = PROTOCOL
    result["scope"] = "Separate pure-foreign series; all 12 targets retain 16 unchanged pages."
    scale.common.atomic_json(Path(output) / "summary.json", result)
    return result


def run(args):
    plan = settings()
    supplementary = protocol_identity()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("Never overwrite a supplementary attempt")
    profile = plan["profiles"][args.profile]
    bound = {"evaluator": scale.protocol_identity(), "supplementary_evaluator": supplementary,
        "baseline": scale.common.runtime_identity(args.baseline_root),
        "candidate": scale.common.runtime_identity(args.candidate_root), "profile": args.profile,
        "backend": args.backend, "host": scale.common.host_identity(),
        "candidate_ranking_scope": "project", "required_fields_controls": False,
        "snapshot_encoding": "gzip", "rounds": profile["rounds"],
        "repetitions": profile["repetitions"], "warm_calls": profile["warm_calls"],
        "checkpoints": checkpoints(args.profile, plan), "performance_cases": list(scale.PERFORMANCE),
        "cases_sha256": digest(cases(checkpoints(args.profile, plan)[0])),
        "expected_records": expected_records(args.profile, plan)}
    verify_binding(bound, plan)
    output.mkdir(parents=True, exist_ok=False)
    binding = output / "binding.json"
    scale.common.atomic_json(binding, bound)
    for relative in (*scale.FROZEN, *FROZEN):
        destination = output / "protocol" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    manifest = {"status": "running", "protocol": PROTOCOL, "started_at": scale.common.now(), "stages": []}
    scale.common.atomic_json(output / "manifest.json", manifest)
    snapshots = output / "snapshots"
    snapshots.mkdir()
    built, initial_targets = {}, None
    try:
        for spec in bound["checkpoints"]:
            verify_binding(bound, plan)
            database = snapshots / (spec["id"] + ".sqlite")
            if spec["parent"]:
                scale.restore_snapshot(built[spec["parent"]], database)
            else:
                scale.require_space(snapshots)
            print(json.dumps({"event": "build_started", "checkpoint": spec["id"], "pages": spec["total_pages"]}), flush=True)
            result = scale.invoke(args, "worker-build", args.baseline_root, "baseline", spec, database,
                                  output / ("build-" + spec["id"]), binding)
            targets = target_fingerprint(database)
            verify_target_scope(targets, initial_targets)
            if initial_targets is None:
                initial_targets = targets
            snapshot = {**scale.pack_snapshot(database, compressed=True), "fingerprint": result["fingerprint"],
                        "fixed_target_fingerprint": targets}
            built[spec["id"]] = snapshot
            stage = {"spec": spec, "snapshot": snapshot,
                     "build_elapsed_seconds": result["elapsed_seconds"], "measurements": []}
            manifest["stages"].append(stage)
            scale.common.atomic_json(output / "manifest.json", manifest)
            for rnd in range(bound["rounds"]):
                for arm in (("baseline", "candidate") if rnd % 2 == 0 else ("candidate", "baseline")):
                    verify_binding(bound, plan)
                    working = output / "working.sqlite"
                    if working.exists():
                        scale.common.remove_working(working)
                    scale.restore_snapshot(snapshot, working)
                    repo = args.baseline_root if arm == "baseline" else args.candidate_root
                    destination = output / f"measure-{spec['id']}-{rnd:02d}-{arm}"
                    measured = scale.invoke(args, "worker-measure", repo, arm, spec, working, destination, binding, rnd)
                    for field in ("logical_sources_sha256", "page_ids", "source_tables_sha256"):
                        if measured["fingerprint"][field] != snapshot["fingerprint"][field]:
                            raise ValueError("Worker changed original source tables or IDs: " + field)
                    verify_binding(bound, plan)
                    stage["measurements"].append({"arm": arm, "round": rnd, "output": destination.name,
                        **{key: measured[key] for key in ("status", "observations", "open_wall_ns",
                            "storage_before", "storage_after", "resources")}})
                    scale.common.remove_working(working)
                    scale.common.atomic_json(output / "manifest.json", manifest)
                    print(json.dumps({"event": "measurement_finished", "checkpoint": spec["id"],
                                      "arm": arm, "round": rnd}), flush=True)
            summarize(output)
        observed = sum(b["observations"] for s in manifest["stages"] for b in s["measurements"])
        if observed != bound["expected_records"]:
            raise ValueError("Supplementary observation count differs from registration")
        manifest["status"] = "completed"
    except Exception as exc:
        manifest.update(status="incomplete", error={"type": type(exc).__name__, "message": str(exc),
                                                    "traceback": traceback.format_exc()})
    manifest["finished_at"] = scale.common.now()
    scale.common.atomic_json(output / "manifest.json", manifest)
    summarize(output)
    print(json.dumps({"status": manifest["status"], "output": str(output)}), flush=True)
    return 0 if manifest["status"] == "completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "run"))
    parser.add_argument("--baseline-root")
    parser.add_argument("--candidate-root")
    parser.add_argument("--output")
    parser.add_argument("--profile", choices=("smoke", "main"), default="main")
    parser.add_argument("--backend", choices=("python", "native"), default="native")
    parser.add_argument("--worker-timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.action == "describe":
        plan = settings()
        print(json.dumps({"protocol": PROTOCOL, "stages": checkpoints(args.profile, plan),
                          "expected_records": expected_records(args.profile, plan)}, indent=2))
        return 0
    if not all((args.baseline_root, args.candidate_root, args.output)):
        parser.error("run requires baseline-root, candidate-root and a new output directory")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
