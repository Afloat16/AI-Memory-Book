"""Exercise complete external component/report contracts on two invented pages.

This command cannot load the Hotpot cohort. It is a fixture/interface check,
not a quality or performance comparison. Official pinned dependencies must
already be prepared in --cache.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.data import Dataset, Evidence, QueryCase
from benchmarks.round2_eval import (Ledger, PLAN, UPSTREAM_LOCKS, atomic, component,
    component_engine, component_hits, digest, now, sha, summary_of, write_report)
from benchmarks.round2_resources import Resources
from benchmarks.token_compare import TokenCounter
from scripts.summarize_round2_validation import verify_configurations, verify_samples


def fixture():
    data = Dataset(23017, "fictional-interface-smoke", variant="round2_response_contract_fixture")
    documents, groups = [], {}
    for suffix, moment in (("a", "sunrise"), ("b", "noon")):
        project, session, identity = "fixture-" + suffix, "fixture-session-" + suffix, "fixture-query-" + suffix
        body = "The copper ferry leaves at " + moment + "."
        data.sessions.append({"project": project, "session_id": session, "title": "Ferry timetable",
            "created_at": "2000-01-01T00:00:00Z", "messages": [{"role": "user", "content": body}]})
        data.queries.append(QueryCase(identity, "When does the copper ferry leave?", "fixture", project,
                                      (Evidence(session, 0, body),)))
        documents.append({"id": "fixture-page-" + suffix, "project": project, "title": "Ferry timetable",
            "text": body, "created_at": "2000-01-01T00:00:00Z", "breadcrumb": [{"id": project, "title": project}],
            "source_refs": [{"project": project, "session_id": session, "turn_index": 0,
                             "turn_start": len("USER: "), "turn_end": len("USER: ") + len(body)}]})
        groups[identity] = {"diagnostic_groups": ["all", "category:fixture"],
                           "query_term_coverage_by_required_text": None, "required_chapters": 1}
    return data, {"documents": documents, "documents_sha256": digest(documents), "diagnostics": groups,
                  "diagnostics_sha256": digest(groups), "dataset": data.description()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.state, args.output, args.cache = args.state.resolve(), args.output.resolve(), args.cache.resolve()
    if args.state.exists() or args.output.exists():
        raise FileExistsError("Preserve prior fixture runs; require fresh state/output directories")
    args.state.mkdir(parents=True)
    args.output.mkdir(parents=True)
    plan = json.loads(PLAN.read_bytes())
    binding = {"upstream_locks": UPSTREAM_LOCKS}
    data, bundle = fixture()
    records = []
    success = True
    for stage in ("claude-mem-fts", "ai-memory-hybrid", "billion-context"):
        state = args.state / stage
        state.mkdir()
        options = SimpleNamespace(stage=stage, state=state, cache=args.cache.resolve())
        ledger = Ledger(state / "attempts.jsonl")
        resources = Resources()
        report = {"schema_version": 1, "stage": stage, "purpose": "fictional end-to-end component contract smoke",
            "started_at": now(), "dataset": data.description(), "configurations": [], "timing_rows": [],
            "configured_generative_model_calls": 0, "helper_sha256": sha(ROOT / "benchmarks/round2_eval.py"),
            "smoke_script_sha256": sha(Path(__file__))}
        try:
            component(options, plan, binding, data, bundle, report, ledger, resources)
        except BaseException as error:
            report["validation"] = {"passed": False, "failures": [{"error_type": type(error).__name__, "reason": str(error)}]}
        finally:
            ledger.close()
            report.update(finished_at=now(), resources=resources.close(),
                attempt_states=[json.loads(line) for line in (state / "attempts.jsonl").read_text().splitlines()],
                ledger_sha256=sha(state / "attempts.jsonl"), attempts_started=ledger.started, attempts_finished=ledger.finished)
            prefix = args.output / stage
            write_report(report, prefix)
        raw = gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes())
        projected = json.loads(Path(str(prefix) + ".summary.json").read_bytes())
        failures = []
        try:
            assert projected == summary_of(json.loads(raw), hashlib.sha256(raw).hexdigest())
            assert report["validation"] == {"passed": True, "failures": []}, report["validation"]
            verify_samples(report, plan, [case.id for case in data.queries])
            verify_configurations(report, plan, [case.id for case in data.queries])
            assert len(report["configurations"]) == 6 and ledger.started == ledger.finished == 6
            for row in report["timing_rows"]:
                expected = "fixture-page-" + row["id"][-1]
                assert row["hit_ids"] == [expected]
                assert all(row["search_payload_tokens"][name] > 0 for name in ("cl100k_base", "o200k_base"))
                if stage == "ai-memory-hybrid":
                    assert row["read_calls"] == (1 if row["repetition"] == 0 else 0)
                else:
                    assert row["read_calls"] == 0 and row["search_content_tokens"] is None
            assert all(config["metrics"]["complete_evidence_rate"] == 1.0 for config in report["configurations"])
        except Exception as error:
            failures.append({"error_type": type(error).__name__, "reason": str(error)})
        status = not failures
        success &= status
        records.append({"stage": stage, "passed": status, "failures": failures,
            "attempts_started": ledger.started, "attempts_finished": ledger.finished,
            "configurations": len(report["configurations"]), "native_commit": report.get("metadata", {}).get("commit"),
            "source_unchanged": report.get("metadata", {}).get("source_unchanged"),
            "outputs": {str(path.relative_to(ROOT)): sha(path) for path in
                (Path(str(prefix) + ".json.gz"), Path(str(prefix) + ".summary.json"))}})
        print(json.dumps({key: records[-1][key] for key in ("stage", "passed", "failures", "attempts_started", "attempts_finished", "configurations")}), flush=True)
    assessment = {"schema_version": 1, "status": "passed" if success else "failed", "assessed_at": now(),
        "scope": "Three actual pinned external adapters, two invented scoped queries and three repetitions each, complete component search/mapping/payload/full-read/six-budget packing/raw-summary/strict-assessment path. No external cohort content or generation calls.",
        "helper_sha256": sha(ROOT / "benchmarks/round2_eval.py"), "script_sha256": sha(Path(__file__)),
        "upstream_locks": {name: {"path": path, "sha256": sha(ROOT / path)} for name, path in UPSTREAM_LOCKS.items()},
        "records": records}
    atomic(args.output / "assessment.json", assessment)
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
