"""Export source-free diagnostics after an interrupted validation.

This module never invokes a model or resumes an evaluation. It preserves only
allowlisted identifiers, hashes, numeric costs and attempt states. An exported
diagnostic is not a completed benchmark or sufficient input to replay requests.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re


ENGINES = {"baseline_native_excerpt_pack", "candidate_native_token_budget",
           "candidate_semantic_native_token_budget", "book", "ai-memory"}
STATUSES = {"running", "ok", "error", "interrupted", "completed", "failed", "incomplete",
            "completed_with_failures", "interrupted_unknown_outcome",
            "model_identity_mismatch", "retrieval_error"}
HASH_FIELDS = ("request_sha256", "context_sha256", "response_sha256",
               "trace_sha256", "summary_sha256", "log_sha256", "model_sha256",
               "archive_sha256", "server_archive_sha256", "identity_sha256",
               "prepared_sha256", "extracted_binary_sha256")
HEX = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:/-]{1,200}")


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def number(value):
    if type(value) is int:
        return value if 0 <= value < 2 ** 63 else None
    return value if type(value) is float and math.isfinite(value) and value >= 0 else None


def integer(value):
    return value if type(value) is int and 0 <= value < 2 ** 63 else None


def clean_identifier(value, permitted, secrets):
    if (isinstance(value, str) and value in permitted and IDENTIFIER.fullmatch(value)
            and not any(secret and secret in value for secret in secrets)):
        return value
    return None


def hashes(value, secrets=()):
    if not isinstance(value, dict):
        return {}
    return {key: item for key in HASH_FIELDS
            if isinstance(item := value.get(key), str) and HEX.fullmatch(item)
            and not any(secret and secret in item for secret in secrets)}


def usage(value):
    value = value if isinstance(value, dict) else {}
    result = {key: integer(value.get(key)) for key in
              ("prompt_tokens", "completion_tokens", "total_tokens")}
    result["fully_reported"] = all(item is not None for item in result.values())
    return result


def read_bytes(path):
    """Do not include paths or exception messages in the public diagnostic."""
    if path is None:
        return None, {"status": "not_supplied"}
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return None, {"status": "unavailable", "error_type": type(exc).__name__}
    return raw, {"status": "read", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read_object(path):
    raw, record = read_bytes(path)
    if raw is None:
        return None, record
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
    except (ValueError, UnicodeError):
        return None, {**record, "status": "invalid_json_object", "unknown_content": True}
    return value, record


def read_jsonl(path):
    """Retain the valid newline-terminated prefix; hash all uncertain tail bytes."""
    raw, record = read_bytes(path)
    if raw is None:
        return [], {**record, "valid_lines": 0, "unknown_content": True}
    rows, offset = [], 0
    for line in raw.splitlines(keepends=True):
        reason = None
        if not line.endswith(b"\n"):
            reason = "unterminated_line"
        else:
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    reason = "non_object_line"
            except (ValueError, UnicodeError):
                reason = "invalid_json_line"
        if reason:
            tail = raw[offset:]
            record.update(status="damaged_tail", unknown_content=True,
                          damaged_tail={"offset": offset, "bytes": len(tail),
                                        "sha256": hashlib.sha256(tail).hexdigest(),
                                        "reason": reason})
            break
        rows.append(value)
        offset += len(line)
    record.update(valid_lines=len(rows), unknown_content=record.get("unknown_content", False))
    return rows, record


def expected_ids(path):
    value, record = read_object(path)
    if value is None:
        return set(), record
    # Prepared answer packages and the registered authored workflow references
    # provide trusted IDs. Questions, answers and contexts are never copied.
    if isinstance(value.get("queries"), list):
        ids = {row["id"] for row in value["queries"]
               if isinstance(row, dict) and isinstance(row.get("id"), str)}
    elif isinstance(value.get("answers"), dict):
        ids = set(value["answers"])
    else:
        return set(), {**record, "status": "unrecognized_id_source"}
    return ids, {**record, "ids": len(ids)}


def sanitize_answer(row, ids, secrets=()):
    result = hashes(row, secrets)
    engine = clean_identifier(row.get("engine"), ENGINES, secrets)
    qid = clean_identifier(row.get("id"), ids, secrets)
    result.update(engine=engine, query_id=qid,
                  engine_sha256=digest(row.get("engine")),
                  query_id_sha256=digest(row.get("id")))
    status = row.get("status")
    result["status"] = status if isinstance(status, str) and status in STATUSES else "unrecognized"
    result["repetition"] = integer(row.get("repetition"))
    result["provider_usage"] = usage(row.get("provider_usage"))
    result["endpoint_roundtrip_ms"] = number(row.get("endpoint_roundtrip_ms"))
    for field in ("served_model", "system_fingerprint", "answer"):
        if field in row:
            result[field + "_sha256"] = digest(row[field])
    if isinstance(row.get("answer"), str):
        result["answer_characters"] = len(row["answer"])
    return result


def sanitize_proof(value, secrets=()):
    if not isinstance(value, dict):
        return None
    identity = value.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    runtime = identity.get("runtime")
    runtime = runtime if isinstance(runtime, dict) else value
    result = {**hashes(value, secrets), "runtime": hashes(runtime, secrets),
              "record_sha256": digest(value),
              "verification": "Allowlisted recorded claims; exporter does not revalidate model artifacts."}
    if "prepared_sha256" in hashes(identity, secrets):
        result["prepared_sha256"] = hashes(identity, secrets)["prepared_sha256"]
    for field in ("argv", "runtime_files", "runtime_symlinks"):
        if field in runtime:
            result["runtime"][field + "_sha256"] = digest(runtime[field])
    runs = value.get("runs", [value])
    if not isinstance(runs, list):
        runs = []
    public_runs = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        public = hashes(run, secrets)
        status = run.get("status")
        public["status"] = status if isinstance(status, str) and status in STATUSES else "unrecognized"
        for field in ("runtime_unchanged", "completed"):
            if type(run.get(field)) is bool:
                public[field] = run[field]
        for field in ("pid", "server_pid"):
            if integer(run.get(field)) is not None:
                public[field] = run[field]
        for field in ("ready_ms", "started_at_unix", "finished_at_unix"):
            if number(run.get(field)) is not None:
                public[field] = run[field]
        if type(run.get("exit_code")) is int:
            public["exit_code"] = run["exit_code"]
        public_runs.append(public)
    result["runs"] = public_runs
    return result


def base_report(kind):
    return {"schema_version": 1, "kind": kind, "status": "partial_diagnostic_not_completion",
            "model_calls_made_by_exporter": 0, "sufficient_for_resume": False,
            "interpretation": "Observed records only. Missing or damaged records leave unknown outcomes and costs. "
                              "This sanitized copy cannot establish benchmark completion or safely replay generation."}


def answer_diagnostic(trace_path, proof_path=None, prepared_path=None, secrets=()):
    rows, source = read_jsonl(trace_path)
    ids, id_source = expected_ids(prepared_path)
    proof, proof_source = read_object(proof_path)
    output = base_report("answers")
    output.update(source=source, identifier_source=id_source, server_proof_source=proof_source,
                  server_proof=sanitize_proof(proof, secrets))
    started, finished, records = {}, {}, []
    metadata_present = bool(rows and rows[0].get("kind") == "run_metadata")
    duplicates = {"started": 0, "finished": 0}
    unexpected = 0
    for position, row in enumerate(rows):
        kind = row.get("kind")
        if kind == "run_metadata":
            records.append({"line": position + 1, "kind": kind, "record_sha256": digest(row),
                            **hashes(row, secrets)})
            continue
        if not isinstance(kind, str) or kind not in {"request_started", "request_finished"}:
            unexpected += 1
            records.append({"line": position + 1, "kind": "unrecognized", "record_sha256": digest(row)})
            continue
        record = {"line": position + 1, "kind": kind, **sanitize_answer(row, ids, secrets)}
        if kind == "request_started":
            record["status"] = "intent_recorded_outcome_unknown"
        key = digest([row.get("engine"), row.get("id"), row.get("repetition")])
        record["attempt_id_sha256"] = key
        records.append(record)
        target = started if kind == "request_started" else finished
        duplicate_key = "started" if kind == "request_started" else "finished"
        if key in target:
            duplicates[duplicate_key] += 1
        else:
            target[key] = row
    mismatched = sum(key in started and row.get("request_sha256") != started[key].get("request_sha256")
                     for key, row in finished.items())
    unresolved = sum(key not in finished or finished[key].get("status") == "interrupted" for key in started)
    missing_intents = len(set(finished) - set(started))
    invalid_statuses = sum(not isinstance(row.get("status"), str) or row.get("status") not in {"ok", "error", "interrupted"}
                           for row in finished.values())
    invalid_intents = sum("request_sha256" not in hashes(row, secrets) for row in started.values())
    matched = [row for key, row in finished.items() if key in started
               and "request_sha256" in hashes(row, secrets)
               and row.get("request_sha256") == started[key].get("request_sha256")]
    costs = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [usage(row.get("provider_usage"))[field] for row in matched]
        known = [value for value in values if value is not None]
        costs[field] = {"reported_attempts": len(known), "known_subtotal": sum(known),
                        "total_if_complete": None}
    output.update(records=records, accounting={
        "observed_unique_intents": len(started), "observed_unique_finished_records": len(finished),
        "unresolved_intents": unresolved, "finished_without_intent": missing_intents,
        "duplicate_records": duplicates, "mismatched_request_hashes": mismatched,
        "unrecognized_records": unexpected, "metadata_present": metadata_present,
        "invalid_finished_statuses": invalid_statuses, "intents_without_valid_request_hash": invalid_intents,
        "has_unknown_outcomes": bool(not metadata_present or source["unknown_content"] or unresolved or missing_intents
                                     or mismatched or unexpected or invalid_statuses or invalid_intents
                                     or any(duplicates.values())),
        "usage": costs})
    return output


def workflow_diagnostic(checkpoint_path, model_trace_path=None, verification_path=None,
                        ids_path=None, secrets=()):
    checkpoint, source = read_object(checkpoint_path)
    checkpoint = checkpoint or {}
    ids, id_source = expected_ids(ids_path)
    output = base_report("workflow")
    stages = checkpoint.get("stages")
    stages = stages if isinstance(stages, dict) else {}
    statuses, public_stages = Counter(), []
    for key, value in stages.items():
        if not isinstance(value, dict):
            continue
        phase = key.split(":", 1)[0] if isinstance(key, str) else ""
        phase = phase if phase in {"book-ingest", "native-capture", "native-consolidate", "native-embed", "context"} else "unrecognized"
        status = value.get("status")
        status = status if isinstance(status, str) and status in STATUSES else "unrecognized"
        statuses[status] += 1
        public_stages.append({"stage_id_sha256": digest(key), "phase": phase, "status": status,
                              "elapsed_ms": number(value.get("elapsed_ms"))})
    answers = checkpoint.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    public_answers = [sanitize_answer(row, ids, secrets) for row in answers.values() if isinstance(row, dict)]
    model_rows, model_source = read_jsonl(model_trace_path)
    public_models, started, finished = [], set(), set()
    for position, row in enumerate(model_rows):
        event = row.get("event")
        if not isinstance(event, str) or event not in {"started", "completed"}:
            public_models.append({"line": position + 1, "event": "unrecognized", "record_sha256": digest(row)})
            continue
        key = digest(row.get("attempt"))
        (started if event == "started" else finished).add(key)
        public = {"line": position + 1, "event": event, "attempt_id_sha256": key,
                  **hashes(row, secrets), "usage": usage(row.get("usage")),
                  "elapsed_ms": number(row.get("elapsed_ms"))}
        attempt = row.get("attempt")
        if (isinstance(attempt, str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", attempt)
                and not any(secret and secret in attempt for secret in secrets)):
            public["attempt_id"] = attempt
        if type(row.get("http_status")) is int and 100 <= row["http_status"] <= 599:
            public["http_status"] = row["http_status"]
        public_models.append(public)
    verification, verification_source = read_jsonl(verification_path)
    model_runs = checkpoint.get("model_server_runs")
    model_runs = model_runs if isinstance(model_runs, list) else []
    output.update(source=source, identifier_source=id_source, stages=public_stages,
                  answers=public_answers, model_trace_source=model_source, model_attempts=public_models,
                  model_verification_source=verification_source,
                  model_verification=[sanitize_proof(row, secrets) for row in verification],
                  recorded_model_runs=[sanitize_proof(row, secrets) for row in model_runs])
    output["accounting"] = {
        "stage_statuses": dict(statuses), "answer_records": len(public_answers),
        "ambiguous_answer_records": sum(row["status"] in {"interrupted", "running", "unrecognized"}
                                        for row in public_answers),
        "observed_native_model_intents": len(started), "observed_native_model_completions": len(finished),
        "unresolved_native_model_intents": len(started - finished),
        "has_unknown_outcomes": True,
        "interpretation": "A checkpoint answer may have been sent even if its request hash was not durably saved. "
                          "Stage or answer counts are not a claim of completed model calls."}
    return output


def sensitive_environment_values():
    """Use credential values only for redaction; never copy names or values."""
    return tuple(value for key, value in os.environ.items()
                 if value and re.search(r"(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY)", key, re.I))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("answers", "workflow"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--server-proof", type=Path)
    parser.add_argument("--native-model-trace", type=Path)
    parser.add_argument("--model-verification", type=Path)
    args = parser.parse_args(argv)
    secrets = sensitive_environment_values()
    if args.kind == "answers":
        value = answer_diagnostic(args.input, args.server_proof, args.prepared, secrets)
    else:
        ids = args.prepared or Path(__file__).parent / "experiments/full-workflow-answers.json"
        value = workflow_diagnostic(args.input, args.native_model_trace, args.model_verification, ids, secrets)
    # Never overwrite an earlier diagnostic if cleanup is invoked twice.
    if args.output.exists():
        raise FileExistsError("Diagnostic exists; preserve it and choose a new output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".partial")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(args.output)
    print(json.dumps({"status": value["status"], "model_calls_made_by_exporter": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
