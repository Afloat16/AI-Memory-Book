"""Read immutable Git evidence and extract every compatibility metric; never measures."""
from __future__ import annotations
import argparse, copy, hashlib, json, math, re, statistics
from pathlib import Path
from urllib.request import urlopen

RUN_ID=43886529702
EVALUATOR="cfdb3ca2c8ff2d71792e820923057d6613ea08b7"
SOURCES={"baseline":"56eccd8c3a6f1d5637664607936da2595ce50c62","candidate":"4390d013986ab9c96b49cc6964f075f3866f21ee"}
PROTOCOL="native-core-compatibility-performance-5"
EVIDENCE_PREFIX="evidence/native-core-compatibility"
PREFIX="benchmarks/reports/native-core-compatibility/formal-run-1/"
COHORTS=("synthetic61","public1015")
CONFIGS=("native-char2400","mcp-char2400","native-token1024","mcp-token1024")
def sha(raw): return hashlib.sha256(raw).hexdigest()
def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n"
def reduction(baseline,candidate): return 100*(1-candidate/baseline)
def require(value,message):
    if not value: raise ValueError(message)
def same(actual,expected,message):
    require(math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12),message)
def source_file(raw):
    return {"git_blob":hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest(),
            "bytes":len(raw),"sha256":sha(raw)}
def get(commit,path):
    url=f"https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/{commit}/{path}"
    with urlopen(url,timeout=60) as response: raw=response.read()
    return raw,json.loads(raw)

def extract(commit,run,summary,manifest,files):
    require(manifest["protocol"]==run["protocol"]==summary["protocol"]==PROTOCOL,"Protocol differs")
    require(manifest["source_run"]["commit"]==run["evaluator_commit"]==EVALUATOR,"Frozen evaluator differs")
    require(int(manifest["source_run"]["id"])==RUN_ID and manifest["source_run"]["attempt"]==1,"Wrong first attempt")
    require(manifest["evidence_branch"]==f"{EVIDENCE_PREFIX}-{RUN_ID}-1","Wrong evidence branch")
    require(summary["status"]=="completed" and summary["comparison"]["complete_output_and_archive_equivalence"]
            and not summary["comparison"]["differences"],"Incomplete or unequal summary")
    require(summary["attempted_calls"]==run["plan"]["expected_timed_calls"]==113568
            and summary["paired_calls"]==run["plan"]["expected_paired_calls"]==56784,"Incomplete matrix")
    for label,commit_id in SOURCES.items():
        require(run["sources"][label]["commit"]==commit_id and run["sources"][label]["backend"]=="native","Wrong native source")
    query=copy.deepcopy(summary["comparison"]["cells"])
    require({(c["cohort"],c["configuration"]) for c in query}=={(h,k) for h in COHORTS for k in CONFIGS} and len(query)==8,"Query cells differ")
    negative=[]
    for cell in query:
        require(len(cell["rounds"])==4 and [r["round"] for r in cell["rounds"]]==list(range(4)),"Missing query rounds")
        for percentile in ("p50","p95"):
            field=percentile+"_improvement_percent"
            value=reduction(cell["baseline"][percentile+"_ms"],cell["candidate"][percentile+"_ms"])
            same(cell[field],value,"Pooled percentage differs")
            for row in cell["rounds"]:
                rate=reduction(row["baseline"][percentile+"_ms"],row["candidate"][percentile+"_ms"])
                if field in row:same(row[field],rate,"Round percentage differs")
                row[field]=rate
                if rate<0:negative.append({"kind":"query_round","cohort":cell["cohort"],"configuration":cell["configuration"],"round":row["round"],"metric":percentile,"reduction_percent":rate})
            cell[percentile+"_improving_rounds"]=sum(row[field]>0 for row in cell["rounds"])
            if value<0:negative.append({"kind":"query_pooled","cohort":cell["cohort"],"configuration":cell["configuration"],"metric":percentile,"reduction_percent":value})
    ingestion=copy.deepcopy(summary["ingestion_comparisons"])
    require({(c["cohort"],c["metric"]) for c in ingestion}=={(h,k) for h in COHORTS for k in ("fresh_ingestion_ms","unchanged_reingestion_ms")} and len(ingestion)==4,"Ingestion cells differ")
    for cell in ingestion:
        require(cell["paired_batches"]==4 and [r["round"] for r in cell["rounds"]]==list(range(4)),"Missing ingestion rounds")
        for label in SOURCES:
            values=[row[label] for row in cell["rounds"]]
            require(values==cell[label+"_ms"],"Raw ingestion ordering differs")
            same(cell[label+"_total_ms"],sum(values),"Ingestion total differs")
            same(cell[label+"_median_ms"],statistics.median(values),"Ingestion median differs")
        for row in cell["rounds"]:
            same(row["improvement_percent"],reduction(row["baseline"],row["candidate"]),"Ingestion round percentage differs")
            if row["improvement_percent"]<0:negative.append({"kind":"ingestion_round","cohort":cell["cohort"],"metric":cell["metric"],"round":row["round"],"reduction_percent":row["improvement_percent"]})
        same(cell["total_improvement_percent"],reduction(cell["baseline_total_ms"],cell["candidate_total_ms"]),"Ingestion total percentage differs")
        cell["median_improvement_percent"]=reduction(cell["baseline_median_ms"],cell["candidate_median_ms"])
        cell["improving_rounds"]=sum(row["improvement_percent"]>0 for row in cell["rounds"])
        if cell["total_improvement_percent"]<0:negative.append({"kind":"ingestion_total","cohort":cell["cohort"],"metric":cell["metric"],"reduction_percent":cell["total_improvement_percent"]})
    schedule={item["key"]:item for item in run["schedule"]}
    workers=summary["worker_resources"]
    require(len(workers)==16 and {w["key"] for w in workers}==set(schedule),"Worker resources incomplete")
    coord={(schedule[w["key"]]["cohort"],schedule[w["key"]]["round"],schedule[w["key"]]["label"]):w for w in workers}
    resource=[]
    definitions=[
      ("runtime_import_ms","ms","Import MemoryBook after evaluator/bootstrap imports; not full process or CLI startup.",lambda w:w["runtime_import_ms"]),
      ("new_database_ms","ms","Fresh database opening and schema initialization.",lambda w:w["resources"]["new_database_ms"]),
      ("existing_database_open_ms","ms","Open the completed, checkpointed existing database.",lambda w:w["resources"]["existing_database_open_ms"]),
    ]
    for point in ("after_ingestion","after_calls"):
        for kind in ("rss","hwm"):
            boundary=("Worker live RSS" if kind=="rss" else "Worker process lifetime RSS high-water mark")+" "+point.replace("_"," ")+"; includes evaluator/bootstrap state."
            definitions.append((f"worker_{kind}_{point}","MiB",boundary,lambda w,p=point,k=kind:w["resources"][p][k+"_bytes"]/1024**2))
    for point in ("after_ingestion","after_calls"):
        definitions.append((f"worker_cpu_{point}","s","Cumulative worker user+system CPU since process start; includes probes/bootstrap/evaluation and is not isolated query CPU.",
            lambda w,p=point:w["resources"][p]["user_cpu_s"]+w["resources"][p]["system_cpu_s"]))
    for config in ("mcp-char2400","mcp-token1024"):
        definitions.extend([
          (config+"_startup_to_initialize_ms","ms","Fresh subprocess launch through official SDK initialize; four launches per side/cohort.",lambda w,c=config:w["configuration_resources"][c]["startup_to_initialize_ms"]),
          (config+"_server_rss_before_calls","MiB","MCP server live RSS after initialization/list_tools, before timed calls.",lambda w,c=config:w["configuration_resources"][c]["server_before_calls"]["rss_bytes"]/1024**2),
          (config+"_server_rss_after_calls","MiB","MCP server live RSS after all three query passes.",lambda w,c=config:w["configuration_resources"][c]["server_after_calls"]["rss_bytes"]/1024**2),
          (config+"_server_hwm_after_calls","MiB","MCP server process lifetime RSS high-water mark after three query passes.",lambda w,c=config:w["configuration_resources"][c]["server_after_calls"]["hwm_bytes"]/1024**2),
          (config+"_server_cpu_during_calls","s","Server user+system CPU snapshot difference across three query passes; procfs tick granularity; excludes client CPU.",
           lambda w,c=config:sum(w["configuration_resources"][c]["server_after_calls"][k]-w["configuration_resources"][c]["server_before_calls"][k] for k in ("user_cpu_s","system_cpu_s"))),
        ])
    require(len(definitions)==19,"Unexpected resource inventory")
    for cohort in COHORTS:
        for metric,unit,boundary,read_value in definitions:
            values={label:[read_value(coord[(cohort,round_,label)]) for round_ in range(4)] for label in SOURCES}
            require(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for vals in values.values() for v in vals),"Invalid resource")
            medians={label:statistics.median(values[label]) for label in SOURCES}
            resource.append({"cohort":cohort,"metric":metric,"unit":unit,"boundary":boundary,**values,
                "baseline_median":medians["baseline"],"candidate_median":medians["candidate"],
                "delta":medians["candidate"]-medians["baseline"],
                "reduction_percent":reduction(medians["baseline"],medians["candidate"]) if medians["baseline"] else None})
    storage=[]
    for worker in workers:
        identity=schedule[worker["key"]]
        storage.append({**{k:identity[k] for k in ("cohort","key","label","round")},
          "after_ingestion":worker["resources"]["storage_after_ingestion"],
          "after_checkpoint":worker["resources"]["storage_after_checkpoint"],
          "mcp_live":{k:v["storage_live"] for k,v in worker["configuration_resources"].items() if k.startswith("mcp-")}})
    binaries={}
    for label in SOURCES:
        digest=next(iter(run["sources"][label]["native_binaries"].values()))
        hits=[(name,item) for name,item in manifest["original_files"].items() if "/"+label+"/src/memory_book/_native." in name and item["sha256"]==digest]
        require(len(hits)==1,"Binary manifest inventory differs")
        name,item=hits[0];binaries[label]={"path":name,**item}
    return {"schema_version":1,"kind":"independent-summary-and-resource-extraction",
      "source":{"evidence_commit":commit,"evidence_branch":manifest["evidence_branch"],"run_id":RUN_ID,
        "evaluator_commit":EVALUATOR,"sources":{label:{key:source[key] for key in ("commit","backend","source_files_sha256","native_binaries")} for label,source in run["sources"].items()},
        "summary_file":files["summary.json"],"run_file":files["run.json"],"manifest_file":files["evidence-manifest.json"],
        "byte_hash_verification":"Fetched exact bytes matched evidence-manifest SHA256 and byte lengths; Git blob identities computed from those same bytes."},
      "measurement":{"host":run["host"],"counts":{"calls":summary["attempted_calls"],"paired":summary["paired_calls"]},
        "complete_output_and_archive_equivalence":summary["comparison"]["complete_output_and_archive_equivalence"],"differences":summary["comparison"]["differences"],
        "timing_boundaries":run["timing_boundaries"]},
      "method":{"timed_calls_repeated":0,"query_statistics":"Exact frozen summary values retained; all pooled/round reductions independently checked.",
        "resource_statistics":"Medians of exactly four workers per side/cohort; all individual values and raw snapshots retained. Delta is candidate minus baseline.",
        "ingestion_statistics":"Headline percentage uses sum of four paired batches; every batch and both aggregate definitions retained.",
        "cpu":"MCP calling-process CPU belongs to the client and is not substituted for server CPU. Server CPU uses procfs snapshot differences.",
        "scope":"One isolated hosted first attempt on existing regression cohorts; no generated answers or new quality claim."},
      "disposition":{"candidate_accepted_for_release":None,"reason":"Metric extraction makes no acceptance decision; independent artifact audit and release review remain separate.","first_attempt_retained":True},
      "query_cells":query,"ingestion_cells":ingestion,"resource_cells":resource,"storage_by_worker":storage,"native_binary_size":binaries,
      "negative_query_and_ingestion_observations":negative,
      "resource_increases":[{k:c[k] for k in ("cohort","metric","unit","baseline_median","candidate_median","delta","reduction_percent")} for c in resource if c["delta"]>0],
      "worker_resource_snapshots":workers}

def markdown(m):
    f=lambda x:f"{x:.3f}"
    sign=lambda x:f"{x:+.3f}"
    lines=["# Native core compatibility formal run 1: complete metric extraction","",
      "This report retains every registered query and ingestion cell, every paired round, and all resource observations. It makes no release-acceptance decision.","",
      "## Evidence and method","",
      f"- Hosted first attempt: [{RUN_ID}](https://github.com/Afloat16/AI-Memory-Book/actions/runs/{RUN_ID}).",
      f"- Frozen evaluator: \u0060{EVALUATOR}\u0060; baseline: native v0.8.1 \u0060{SOURCES['baseline']}\u0060; candidate: \u0060{SOURCES['candidate']}\u0060.",
      f"- Immutable evidence: [{m['source']['evidence_commit']}](https://github.com/Afloat16/AI-Memory-Book/tree/{m['source']['evidence_commit']}).",
      "- Fetched run/summary bytes match the evidence manifest. This extraction repeats no timed calls; the separately retained artifact audit verifies every raw row, ledger and source.",
      f"- Host: {m['measurement']['host']['cpu_model']}; Python {m['measurement']['host']['python'].split()[0]}, SQLite {m['measurement']['host']['sqlite']}. Four AB/BA/BA/AB rounds, three passes per worker, 113,568 calls and 56,784 pairs.",
      "- Positive reduction means faster: 100 * (1 - candidate / baseline). Negative values remain regressions. All latency values are milliseconds; resource values are medians of four workers per side/cohort.",
      "- No model generation or query-result cache hits. SQLite/OS caches are not cleared. Existing regression cohorts give no new retrieval-quality or large-archive guarantee. Different experiments/hosts are not added together.","",
      "## All eight query cells","",
      "| Cohort | Configuration | Baseline p50 | Candidate p50 | p50 reduction | Baseline p95 | Candidate p95 | p95 reduction | Improving p95 rounds |",
      "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c in m["query_cells"]:
        lines.append(f"| {c['cohort']} | {c['configuration']} | {f(c['baseline']['p50_ms'])} | {f(c['candidate']['p50_ms'])} | {sign(c['p50_improvement_percent'])}% | {f(c['baseline']['p95_ms'])} | {f(c['candidate']['p95_ms'])} | {sign(c['p95_improvement_percent'])}% | {c['p95_improving_rounds']}/4 |")
    lines+=["","## Every paired query round","","Each entry is p50 / p95 reduction (%), in chronological round order.","",
      "| Cohort | Configuration | Round 1 | Round 2 | Round 3 | Round 4 |","|---|---|---:|---:|---:|---:|"]
    for c in m["query_cells"]:
        cells=[f"{sign(r['p50_improvement_percent'])} / {sign(r['p95_improvement_percent'])}" for r in c["rounds"]]
        lines.append("| "+ " | ".join([c["cohort"],c["configuration"],*cells])+" |")
    lines+=["","## All four ingestion cells","","The registered percentage compares the sum of all four paired batches. Medians and every raw batch time remain in the JSON. Each batch contains 112 synthetic or 216 public sessions.","",
      "| Cohort | Batch | Baseline total (ms) | Candidate total (ms) | Total reduction | Baseline median (ms) | Candidate median (ms) | Improving rounds |",
      "|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in m["ingestion_cells"]:
        lines.append(f"| {c['cohort']} | {c['metric']} | {f(c['baseline_total_ms'])} | {f(c['candidate_total_ms'])} | {sign(c['total_improvement_percent'])}% | {f(c['baseline_median_ms'])} | {f(c['candidate_median_ms'])} | {c['improving_rounds']}/4 |")
    lines+=["","| Cohort | Batch | Round 1 | Round 2 | Round 3 | Round 4 |","|---|---|---:|---:|---:|---:|"]
    for c in m["ingestion_cells"]:lines.append("| "+" | ".join([c["cohort"],c["metric"],*[sign(r["improvement_percent"])+"%" for r in c["rounds"]]])+" |")
    lines+=["","## Every negative query or ingestion observation","","Negative pooled, individual-round and ingestion-total reductions are listed without filtering.",""]
    if m["negative_query_and_ingestion_observations"]:
        lines+=["| Kind | Cohort | Configuration / metric | Round | Reduction |","|---|---|---|---:|---:|"]
        for n in m["negative_query_and_ingestion_observations"]:
            lines.append(f"| {n['kind']} | {n['cohort']} | {n.get('configuration','')} {n['metric']} | {n['round']+1 if 'round' in n else 'all'} | {sign(n['reduction_percent'])}% |")
    else:lines.append("No query p50/p95 or ingestion total/round reduction is negative in this first attempt.")
    lines+=["","## Startup, memory and CPU: all 38 resource cells","","Positive delta means a higher candidate value. JSON retains all four raw values per side, the exact sampling boundary, and every original worker resource snapshot.","",
      "| Cohort | Resource | Unit | Baseline median | Candidate median | Delta |","|---|---|---|---:|---:|---:|"]
    for c in m["resource_cells"]:lines.append(f"| {c['cohort']} | {c['metric']} | {c['unit']} | {f(c['baseline_median'])} | {f(c['candidate_median'])} | {sign(c['delta'])} |")
    lines+=["","API import starts after evaluator/bootstrap imports and is not full CLI startup. MCP initialization starts at fresh server launch. Worker RSS/CPU includes probes, ingestion, evaluation and output validation; cumulative worker CPU is not isolated recall CPU. MCP server CPU is the user+system snapshot difference with procfs tick granularity; per-call calling-process CPU is the client. Four resource samples per side do not establish a universal startup or memory gain.","",
      "## Storage and native binaries","","Every live and checkpointed DB/WAL/SHM observation is retained in JSON.","",
      "| Cohort | Side | Checkpointed DB sizes (bytes) | WAL sizes | SHM sizes |","|---|---|---|---|---|"]
    for cohort in COHORTS:
        for label in SOURCES:
            rows=[w for w in m["storage_by_worker"] if w["cohort"]==cohort and w["label"]==label]
            sizes=lambda key:", ".join(str(v) for v in sorted({r["after_checkpoint"]["file_bytes"][key] for r in rows}))
            lines.append(f"| {cohort} | {label} | {sizes('db')} | {sizes('-wal')} | {sizes('-shm')} |")
    lines+=["","| Side | Native extension bytes | SHA256 |","|---|---:|---|"]
    for label,item in m["native_binary_size"].items():lines.append(f"| {label} | {item['bytes']} | \u0060{item['sha256']}\u0060 |")
    delta=m["native_binary_size"]["candidate"]["bytes"]-m["native_binary_size"]["baseline"]["bytes"]
    lines+=["",f"Native extension size changes by {delta:+,} bytes on this host. These are compiled extension files, not wheel download or all-platform installation sizes.",""]
    return "\n".join(lines)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence-commit",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{40}",args.evidence_commit),"Use an immutable exact evidence commit")
    require(not args.output.exists(),"Do not overwrite an earlier extraction")
    raw_manifest,manifest=get(args.evidence_commit,"evidence-manifest.json")
    files={"evidence-manifest.json":source_file(raw_manifest)}
    loaded={}
    for name in ("run.json","summary.json"):
        raw,value=get(args.evidence_commit,PREFIX+name)
        info=source_file(raw)
        require({k:info[k] for k in ("bytes","sha256")}==manifest["original_files"][PREFIX+name],"Evidence bytes differ")
        files[name]=info;loaded[name]=value
    metrics=extract(args.evidence_commit,loaded["run.json"],loaded["summary.json"],manifest,files)
    args.output.mkdir(parents=True)
    (args.output/"metrics-extract.json").write_text(dump(metrics))
    (args.output/"metrics-extract.md").write_text(markdown(metrics))
    print(dump({"status":"extracted","calls":metrics["measurement"]["counts"],
      "queries":[{"cohort":c["cohort"],"config":c["configuration"],"p50_reduction":c["p50_improvement_percent"],"p95_reduction":c["p95_improvement_percent"],"p95_rounds":c["p95_improving_rounds"]} for c in metrics["query_cells"]],
      "ingestion":[{"cohort":c["cohort"],"metric":c["metric"],"reduction":c["total_improvement_percent"],"improving_rounds":c["improving_rounds"]} for c in metrics["ingestion_cells"]],
      "negative_observations":metrics["negative_query_and_ingestion_observations"]}))
if __name__=="__main__":main()
