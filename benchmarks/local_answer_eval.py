"""Prepare the registered local-answer cohorts and export source-free evidence.

Original passages, questions, gold answers and raw model replies remain in the
ignored working directory. Public exports retain their hashes, scores, usage,
source coordinates, preparation costs and complete attempt accounting.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from benchmarks import answer_eval
from benchmarks import local_answer_server
from benchmarks.hotpot_data import load_hotpot
from benchmarks.token_compare import TokenCounter


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/experiments/local-answer-plan.json"
EXECUTION = ROOT / "benchmarks/experiments/local-answer-execution.json"


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def preparation_sources():
    return {str(path.relative_to(ROOT)): file_hash(path) for path in
            (Path(__file__).resolve(), Path(local_answer_server.__file__), PLAN, EXECUTION, ROOT / "benchmarks/hotpot_data.py",
             ROOT / "benchmarks/hotpot_manifest.json", ROOT / "benchmarks/locomo_split.json")}


def prepare(args):
    sources = preparation_sources()
    plan = json.loads(PLAN.read_text())
    destination = args.work_dir / args.cohort
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "prepared.json"
    engines = plan["engines"]
    options = ["--source-options", engines[1] + '={"native_token_budget":true}',
               "--source-options", engines[2] + "=" + json.dumps({"native_token_budget": True,
                                       "semantic_model_dir": str(args.model_dir.resolve())})]
    command = [sys.executable, "-m", "benchmarks.answer_eval", "prepare",
               "--source", engines[0] + "=" + str(args.baseline_src.resolve()),
               "--source", engines[1] + "=" + str(args.candidate_src.resolve()),
               "--source", engines[2] + "=" + str(args.candidate_src.resolve()),
               "--expected-queries", "128", "--budget-chars", "8000", "--budget-tokens", "512",
               "--tokenizer", "cl100k_base", "--limit", "5", "--output", str(output), *options]
    if args.cohort == "locomo":
        command += ["--locomo-path", str(args.data_dir / "locomo10.json"), "--split", "heldout",
                    "--max-queries", "128", "--cohort-label", "Known public retrieval regression; first actual generation measurement"]
    else:
        source = args.data_dir / "hotpotqa-dev-distractor.json"
        dataset = load_hotpot(source)
        labels = {row["_id"]: row for row in json.loads(source.read_bytes())}
        cases = {"sessions": dataset.sessions, "queries": [{"id": case.id, "query": case.query,
                 "project": case.project, "answerable": True, "answers": [str(labels[case.id]["answer"])],
                 "category": case.category} for case in dataset.queries], "provenance": dataset.provenance}
        private_cases = destination / "cases.json"
        if private_cases.exists():
            if json.loads(private_cases.read_bytes()) != cases:
                raise ValueError("Existing private cases differ; preserve them and choose a new work directory")
        else:
            answer_eval.save_new(private_cases, cases)
        command += ["--cases", str(private_cases), "--cohort-label", "Frozen external HotpotQA scoped-distractor diagnostic"]
    subprocess.run(command, cwd=ROOT, check=True)
    if preparation_sources() != sources:
        raise ValueError("Cohort preparation code or plans changed during execution; retain this attempt")
    answer_eval.save_new(destination / "preparation-binding.json",
                         {"sources": sources, "prepared_sha256": file_hash(output),
                          "cohort": args.cohort})
    print(json.dumps({"prepared": str(output), "cohort": args.cohort, "generative_calls": 0}))


def run(args):
    prepared = args.work_dir / args.cohort / "prepared.json"
    binding = json.loads((prepared.parent / "preparation-binding.json").read_bytes())
    if binding != {"sources": preparation_sources(), "prepared_sha256": file_hash(prepared), "cohort": args.cohort}:
        raise ValueError("Cohort preparation code, plans or prepared inputs changed before execution")
    data = json.loads(prepared.read_bytes())
    answer_eval.validate_prepared(data, TokenCounter(data["tokenizer"]["name"]))
    plan = json.loads(PLAN.read_bytes())
    prefix = args.run_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    # This lock also passes to the owned server: an orphan model process
    # cannot silently overlap a new launch after a parent interruption.
    with answer_eval._lock(Path(str(prefix) + ".server.json")) as lock:
        if Path(str(prefix) + ".summary.json").exists():
            raise ValueError("Completed answer result exists; never replay a completed run")
        trace = Path(str(prefix) + ".jsonl")
        if trace.exists() != args.resume:
            raise ValueError("New runs require a new prefix; resume requires an existing answer ledger")
        with local_answer_server.owned_server(args.model_cache, prepared, prefix,
                                             resume=args.resume, lock_fd=lock.fileno()) as endpoint:
            summary = answer_eval.run(SimpleNamespace(
                prepared=prepared, output=prefix, base_url=endpoint,
                model=plan["model"]["served_alias"], api_key_env=None,
                output_token_field="max_tokens", max_output_tokens=128,
                omit_temperature=False, temperature=0.0, repeats=1,
                timeout=120, resume=args.resume))
    errors = sum(engine["errors"] for engine in summary["engines"])
    print(json.dumps({"cohort": args.cohort, "errors": errors,
                      "server_proof": str(prefix) + ".server.json"}))
    return 2 if errors else 0


def export(args):
    prepared_path = args.work_dir / args.cohort / "prepared.json"
    prepared = json.loads(prepared_path.read_bytes())
    binding = json.loads((prepared_path.parent / "preparation-binding.json").read_bytes())
    if binding != {"sources": preparation_sources(), "prepared_sha256": file_hash(prepared_path), "cohort": args.cohort}:
        raise ValueError("Cohort preparation code, plans or prepared inputs changed after freezing")
    answer_eval.validate_prepared(prepared, TokenCounter(prepared["tokenizer"]["name"]))
    trace = Path(str(args.run_prefix) + ".jsonl")
    summary = json.loads(Path(str(args.run_prefix) + ".summary.json").read_bytes())
    if args.model_file.resolve().parent != args.server_archive.resolve().parent:
        raise ValueError("Pinned local model and server must share their verified artifact cache")
    server_proof = local_answer_server.validate_proof(
        Path(str(args.run_prefix) + ".server.json"), prepared_path, args.run_prefix,
        args.model_file.resolve().parent)
    if summary["trace_sha256"] != file_hash(trace):
        raise ValueError("Raw trace hash differs from the completed summary")
    if summary["run"]["prepared_sha256"] != file_hash(prepared_path):
        raise ValueError("Answer summary used different prepared inputs")
    if len(prepared["queries"]) != 128 or summary["run"]["repeats"] != 1:
        raise ValueError("Registered cohort size or repeat count changed")
    entries = [json.loads(line) for line in trace.read_bytes().splitlines()]
    rows = [row for row in entries if row["kind"] == "request_finished"]
    expected = {(engine["label"], case["id"], 0) for engine in prepared["engines"] for case in prepared["queries"]}
    actual = [(row["engine"], row["id"], row["repetition"]) for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Answer attempt matrix is incomplete or duplicated")
    plan = json.loads(PLAN.read_bytes())
    if [engine["label"] for engine in prepared["engines"]] != plan["engines"]:
        raise ValueError("Prepared engines differ from the registered three-way comparison")
    if prepared["parameters"] != {"budget_chars": 8000, "budget_tokens": 512, "limit": 5,
                                  "packing": "per-engine packing_policy", "segmentation": "adaptive",
                                  "max_page_chars": 900, "min_page_chars": 400, "similarity_threshold": .12}:
        raise ValueError("Prepared retrieval parameters differ from the registered experiment")
    if prepared["tokenizer"] != {"name": "cl100k_base", "version": "0.12.0"}:
        raise ValueError("Reference tokenizer differs from the registered experiment")
    options = [engine["retrieval_options"] for engine in prepared["engines"]]
    if options != [{}, {"native_token_budget": True}, {"native_token_budget": True, "semantic": True}]:
        raise ValueError("Prepared engine options differ from the registered experiment")
    if summary["run"]["parameters"] != {"model": plan["model"]["served_alias"], "stream": False,
                                        "max_tokens": 128, "temperature": 0.0}:
        raise ValueError("Actual request parameters differ from the registered experiment")
    if summary["run"].get("timeout_seconds") != 120:
        raise ValueError("Actual request timeout differs from the registered experiment")
    planned = list(answer_eval.planned_requests(prepared, summary["run"]["parameters"], 1))
    started, completed = answer_eval.resume_ledger(trace, summary["run"], planned)
    if len(started) != len(expected) or len(completed) != len(expected):
        raise ValueError("Retained ledger has unresolved or missing model attempts")
    recomputed = {**answer_eval.summarize(prepared, rows), "run": entries[0], "trace_sha256": file_hash(trace)}
    if recomputed != summary:
        raise ValueError("Completed summary does not reproduce from the retained actual attempts")
    for entry, path in ((plan["model"], args.model_file), (plan["server"], args.server_archive)):
        if path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError("Actual local model/server artifact differs from the registered plan")
    public_rows = []
    for row in rows:
        public = {key: value for key, value in row.items() if key != "answer"}
        public["answer_sha256"] = answer_eval.digest(row["answer"]) if row.get("answer") is not None else None
        public["answer_characters"] = len(row["answer"]) if row.get("answer") is not None else None
        public_rows.append(public)
    preparation = []
    for engine in prepared["engines"]:
        preparation.append({"engine": engine["label"], "source": engine["source"],
                            "source_sha256": engine["source_sha256"],
                            "source_sha256_after": engine["source_sha256_after"],
                            "retrieval_options": engine["retrieval_options"],
                            "packing_policy": engine["packing_policy"],
                            "database_stats": engine["database_stats"],
                            "ingestion_events": engine["ingestion_events"],
                            "rows": [{key: value for key, value in row.items() if key != "context"}
                                     for row in engine["rows"]]})
    result = {"schema_version": 1, "cohort": args.cohort,
              "status": "completed-real-local-model",
              "plan_sha256": file_hash(PLAN), "plan": plan,
              "execution_plan_sha256": file_hash(EXECUTION),
              "execution_plan": json.loads(EXECUTION.read_bytes()),
              "artifact_verification": {"model_sha256": file_hash(args.model_file),
                                        "server_archive_sha256": file_hash(args.server_archive)},
              "owned_server_proof": server_proof,
              "prepared_sha256": file_hash(prepared_path), "raw_trace_sha256": file_hash(trace),
              "preparation_binding": binding,
              "evaluator_sources": prepared["evaluator_files"], "parameters": prepared["parameters"],
              "corpus_provenance": prepared["corpus_provenance"],
              "query_identities": [{"id": case["id"], "category": case.get("category"),
                                    "answerable": case["answerable"],
                                    "question_sha256": answer_eval.digest(case["query"]),
                                    "accepted_answers_sha256": answer_eval.digest(case["answers"])}
                                   for case in prepared["queries"]],
              "preparation": preparation, "attempts": public_rows, "summary": summary,
              "summary_phase": {"model_calls": 0, "reason": "Book's configured summaries are extractive; no model summarization stage is used."},
              "privacy": "No upstream passages, question text, accepted-answer text, context text or model answer text is redistributed; hashes bind the private artifacts.",
              "interpretation": "One small quantized CPU model. Fixed lexical answer metrics; not a semantic judge or official LoCoMo scoring. The separate native workflow experiment has different settings and is not merged into this report."}
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    output = Path(str(args.output) + ".json.gz")
    summary_output = Path(str(args.output) + ".summary.json")
    if output.exists() or summary_output.exists():
        raise ValueError("Public outputs already exist; preserve the previous experiment")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gzip.compress(raw, mtime=0))
    compact = {key: value for key, value in result.items() if key not in {"preparation", "attempts"}}
    compact["full_report_sha256"] = hashlib.sha256(raw).hexdigest()
    compact["truncated_responses"] = sum(row.get("finish_reason") == "length" for row in rows)
    summary_output.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"published": str(output), "attempts": len(rows),
                      "summary": str(summary_output), "truncated_responses": compact["truncated_responses"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run", "export"):
        command = commands.add_parser(name)
        command.add_argument("--cohort", choices=("locomo", "hotpotqa"), required=True)
        command.add_argument("--work-dir", type=Path, default=Path(".artifacts/local-answer-evaluation"))
        if name == "prepare":
            command.add_argument("--data-dir", type=Path, default=Path(".artifacts/data"))
            command.add_argument("--baseline-src", type=Path, default=Path(".artifacts/native-baseline-5abc/src"))
            command.add_argument("--candidate-src", type=Path, default=Path("src"))
            command.add_argument("--model-dir", type=Path, default=Path(".artifacts/models/semantic"))
        elif name == "run":
            command.add_argument("--run-prefix", type=Path, required=True)
            command.add_argument("--model-cache", type=Path, default=Path(".artifacts/local-answer"))
            command.add_argument("--resume", action="store_true")
        else:
            command.add_argument("--run-prefix", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--model-file", type=Path,
                                 default=Path(".artifacts/local-answer/qwen2.5-0.5b-instruct-q4_k_m.gguf"))
            command.add_argument("--server-archive", type=Path,
                                 default=Path(".artifacts/local-answer/llama-b12110-bin-ubuntu-x64.tar.gz"))
    args = parser.parse_args()
    return {"prepare": prepare, "run": run, "export": export}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
