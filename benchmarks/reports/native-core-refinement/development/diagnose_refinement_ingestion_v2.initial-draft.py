"""Parameterized local ingestion diagnosis; frozen prior runners and results stay intact."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, platform, re, statistics, subprocess, sys, sysconfig, time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path.cwd().resolve()
BASELINE="56eccd8c3a6f1d5637664607936da2595ce50c62"
APPROVED_BASELINE_BINARY="351897e74066f69d592e072e368dd2945d65a0788b7165cabd5f3958e157c564"
APPROVED_BASELINE_CAPTURE="499a8a8d2f710fd2827e7ba860cbabd43026faf8cb1fbc2bef7d87d24d4747ea"
ORDERS=(("baseline","candidate"),("candidate","baseline"),("candidate","baseline"),("baseline","candidate"))
def write(path,value):
    raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix==".gz": raw=gzip.compress(raw,mtime=0)
    path.write_bytes(raw)

def commit_argument(value):
    if not re.fullmatch(r"[0-9a-f]{40}",value):
        raise argparse.ArgumentTypeError("Use an exact lowercase 40-hex commit")
    return value

def reject_sanitizer_environment(environment):
    injection=("ASAN_OPTIONS","UBSAN_OPTIONS","TSAN_OPTIONS","MSAN_OPTIONS","LSAN_OPTIONS",
               "LD_PRELOAD","DYLD_INSERT_LIBRARIES")
    assert not any(environment.get(key) for key in injection),"Sanitizer/injected-library environment is not allowed"
    flag_names=("CC","CXX","CFLAGS","CPPFLAGS","LDFLAGS","LDSHARED","CCSHARED")
    flags={"environment":{key:environment.get(key) for key in flag_names},
           "sysconfig":{key:sysconfig.get_config_var(key) for key in flag_names}}
    assert not re.search(r"(?i)(?:-fsanitize|lib(?:a|ub|t|m|l)san)",json.dumps(flags)), "Sanitizer build flags are not allowed"
    return flags

def inspect_binary(path):
    raw=path.read_bytes()
    assert raw[:4]==bytes((0x7f,0x45,0x4c,0x46)),"This local diagnostic requires a Linux ELF extension"
    audit=subprocess.check_output(["readelf","--wide","--dynamic","--symbols",str(path)],text=True)
    assert not re.search(r"(?:__(?:asan|ubsan|tsan|msan|lsan)_|lib(?:asan|ubsan|tsan|msan|lsan))",audit), "Sanitized native binary is not allowed"
    return {"path":str(path.resolve()),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "elf_sanitizer_scan_sha256":hashlib.sha256(audit.encode()).hexdigest(),"sanitizer_symbols_present":False}

def worker(args):
    source=Path(args.source).resolve()
    reject_sanitizer_environment(os.environ)
    execution=json.loads(Path(args.run_manifest).read_text())
    assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()==execution["evaluator_commit"]
    sys.path.insert(0,str(source));sys.path.insert(1,str(ROOT/"scripts"))
    import native_core_refinement_performance as perf
    before=perf.source_manifest(source,{"commit":args.commit,"backend":"native"})
    assert before==execution["sources"][args.label]
    assert perf.evaluator_manifest(ROOT/"benchmarks/experiments/native_core_refinement_formal_plan.json")==execution["evaluator_files"]
    binary=source.parent/next(iter(before["native_binaries"]))
    binary_check=inspect_binary(binary)
    if args.label=="baseline": assert binary_check["sha256"]==APPROVED_BASELINE_BINARY
    import memory_book
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME, NATIVE
    assert BACKEND_NAME=="native"
    assert Path(memory_book.__file__).resolve()==source/"memory_book"/"__init__.py"
    assert Path(NATIVE.__file__).resolve()==binary.resolve()
    loaded_paths={name:str(Path(sys.modules[name].__file__).resolve())
        for name in ("memory_book","memory_book.store","memory_book.segmentation","memory_book.text",
                     "memory_book.token_budget","memory_book._text_backend")}
    assert all(Path(path).parent==source/"memory_book" for path in loaded_paths.values())
    assert sorted(name for name in dir(NATIVE) if not name.startswith("_"))==sorted(perf.PROBE_HELPERS[args.label])
    data=perf.dataset(args.cohort,Path(args.public))
    order=[{"project":s["project"],"session_id":s["session_id"]} for s in data.sessions]
    output=Path(args.output)
    report={"schema":1,"purpose":"Local unprofiled ingestion diagnosis; no formal performance claim",
      "key":args.key,"label":args.label,"round":args.round,"cohort":args.cohort,"status":"started",
      "source_manifest_before":before,"dataset_sha256":data.fingerprint,"ingestion_order":order,
      "python":sys.version,"platform":platform.platform(),"hash_seed":os.environ.get("PYTHONHASHSEED"),
      "backend":BACKEND_NAME,"loaded_module_paths":loaded_paths,"native_binary_check":binary_check,
      "native_helpers":sorted(name for name in dir(NATIVE) if not name.startswith("_")),
      "fresh":None,"unchanged_batches":[],"error":None}
    write(output,report)
    try:
        with MemoryBook(":memory:",cache_size=0) as book:
            cpu=time.process_time_ns();start=time.perf_counter_ns()
            fresh=[book.ingest(session) for session in data.sessions]
            elapsed=(time.perf_counter_ns()-start)/1e6
            cpu_ms=(time.process_time_ns()-cpu)/1e6
            report["fresh"]={"wall_ms":elapsed,"cpu_ms":cpu_ms,"returns":fresh,"returns_sha256":perf.digest(fresh)}
            write(output,report)
            expected=None
            for batch in range(10):
                cpu=time.process_time_ns();start=time.perf_counter_ns()
                replayed=[book.ingest(session) for session in data.sessions]
                elapsed=(time.perf_counter_ns()-start)/1e6
                cpu_ms=(time.process_time_ns()-cpu)/1e6
                row={"batch":batch,"wall_ms":elapsed,"cpu_ms":cpu_ms,"returns":replayed,
                     "returns_sha256":perf.digest(replayed)}
                report["unchanged_batches"].append(row)
                write(output,report)
                perf.verify_ingestion_results(fresh,replayed,order)
                if expected is None:expected=row["returns_sha256"]
                assert row["returns_sha256"]==expected
        after=perf.source_manifest(source,{"commit":args.commit,"backend":"native"})
        assert before==after
        report.update(source_manifest_after=after,source_and_binary_unchanged=True,status="completed")
    except BaseException as error:
        report.update(status="failed",error={"type":type(error).__name__,"message":str(error)})
        raise
    finally:
        write(output,report)
    print(json.dumps({"key":args.key,"status":report["status"],"fresh_ms":report["fresh"]["wall_ms"],
      "unchanged_ms":[b["wall_ms"] for b in report["unchanged_batches"]]}),flush=True)

def main(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(1,str(ROOT/"scripts"))
    from scripts import native_core_refinement_performance as perf
    from scripts import native_core_refinement_host as host
    candidate=commit_argument(args.candidate_commit)
    assert candidate!=BASELINE,"Candidate must differ from the released baseline"
    flags=reject_sanitizer_environment(os.environ)
    work=Path(args.work).absolute()
    assert not work.exists() and not work.is_symlink(),"Never replace previous diagnosis"
    work.mkdir(parents=True)
    baseline=Path(args.baseline).resolve()
    capture_raw=Path(args.original_capture).read_bytes()
    assert hashlib.sha256(capture_raw).hexdigest()==APPROVED_BASELINE_CAPTURE,"Baseline capture identity differs"
    original=json.loads(capture_raw)
    approved=original["sources"]["baseline"]
    assert approved["status"]=="completed" and approved["source_and_binary_unchanged"]
    assert set(approved["source_manifest_before"]["native_binaries"].values())=={APPROVED_BASELINE_BINARY}
    compiler=subprocess.check_output(["gcc","--version"],text=True)
    assert original["environment"]["compiler"]==compiler
    assert original["environment"]["python"]==sys.version
    evaluator_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    evaluator_files=perf.evaluator_manifest(ROOT/"benchmarks/experiments/native_core_refinement_formal_plan.json")
    run={"schema":1,"purpose":"Local unprofiled paired ingestion diagnosis, not formal benchmark evidence",
      "status":"started","runtime_candidate":candidate,"baseline":BASELINE,
      "evaluator_commit":evaluator_commit,"evaluator_files":evaluator_files,"runner_sha256":perf.sha(Path(__file__).read_bytes()),
      "environment":{"python":sys.version,"platform":platform.platform(),"compiler":compiler,
         "sysconfig":{k:sysconfig.get_config_var(k) for k in ("CC","CFLAGS","LDSHARED","SOABI")}},
      "baseline_build":approved,"baseline_existing_build":True,
      "baseline_capture_sha256":APPROVED_BASELINE_CAPTURE,"sanitizer_environment_check":flags,
      "batch_repetitions":10,"order":[list(o) for o in ORDERS],"workers":[],"error":None}
    write(work/"run.json",run)
    try:
        target=work/"candidate"
        host.materialize(candidate,target)
        environment={**os.environ,"CC":"gcc","MEMORY_BOOK_BUILD_NATIVE":"1",
                     "MEMORY_BOOK_TEXT_BACKEND":"native","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0"}
        environment.pop("PYTHONPATH",None);environment.pop("PYTHONHOME",None)
        command=[sys.executable,"setup.py","build_ext","--inplace","--build-temp",str(work/"build-temp")]
        run["build"]={"command":command,"extra_compile_args":["-O3"],"status":"started"}
        write(work/"run.json",run)
        with (work/"build.log").open("xb") as stream:
            result=subprocess.run(command,cwd=target,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        run["build"].update(returncode=result.returncode,log_sha256=perf.sha((work/"build.log").read_bytes()))
        assert result.returncode==0,"Candidate compilation failed"
        assert not re.search(r"(?:-fsanitize|lib(?:asan|ubsan|tsan|msan|lsan))",(work/"build.log").read_text()),"Sanitizer compiler invocation is not allowed"
        run["build"]["status"]="completed"
        with urlopen(host.LOCOMO_URL,timeout=45) as response:raw=response.read(host.LOCOMO_BYTES+1)
        assert len(raw)==host.LOCOMO_BYTES and hashlib.sha256(raw).hexdigest()==host.LOCOMO_SHA256
        public=work/"locomo10.json";public.write_bytes(raw)
        run["public_input"]={"url":host.LOCOMO_URL,"bytes":len(raw),"sha256":host.LOCOMO_SHA256}
        sources={"baseline":baseline,"candidate":target/"src"}
        manifests={label:perf.source_manifest(src,{"commit":BASELINE if label=="baseline" else candidate,"backend":"native"})
                   for label,src in sources.items()}
        assert manifests["baseline"]==approved["source_manifest_before"],"Approved baseline source/binary changed"
        run["binary_checks"]={label:inspect_binary(src.parent/next(iter(manifests[label]["native_binaries"])))
                              for label,src in sources.items()}
        run["sources"]=manifests
        write(work/"run.json",run)
        for round_index,labels in enumerate(ORDERS):
            for cohort in ("synthetic61","public1015"):
                for label in labels:
                    key=f"r{round_index}-{cohort}-{label}"
                    output=work/(key+".json.gz")
                    command=[sys.executable,str(Path(__file__).resolve()),"--worker","--source",str(sources[label]),
                      "--commit",BASELINE if label=="baseline" else candidate,"--cohort",cohort,
                      "--run-manifest",str(work/"run.json"),
                      "--round",str(round_index),"--label",label,"--key",key,"--public",str(public),"--output",str(output)]
                    run["workers"].append({"key":key,"command":command,"status":"started"})
                    write(work/"run.json",run)
                    result=subprocess.run(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
                    (work/(key+".log")).write_text(result.stdout)
                    run["workers"][-1].update(returncode=result.returncode,status="completed" if result.returncode==0 else "failed")
                    write(work/"run.json",run)
                    assert result.returncode==0,result.stdout
                    print(result.stdout.strip(),flush=True)
        reports=[json.loads(gzip.decompress((work/(w["key"]+".json.gz")).read_bytes())) for w in run["workers"]]
        comparisons=[]
        for cohort in ("synthetic61","public1015"):
            selected=[r for r in reports if r["cohort"]==cohort]
            assert len({r["fresh"]["returns_sha256"] for r in selected})==1
            assert len({batch["returns_sha256"] for r in selected for batch in r["unchanged_batches"]})==1
            for metric in ("fresh","unchanged"):
                rounds=[]
                for round_index in range(4):
                    pair={r["label"]:r for r in selected if r["round"]==round_index}
                    values={label:record["fresh"]["wall_ms"] if metric=="fresh" else
                            sum(batch["wall_ms"] for batch in record["unchanged_batches"])
                            for label,record in pair.items()}
                    rounds.append({"round":round_index,**values,"reduction_percent":100*(1-values["candidate"]/values["baseline"])})
                totals={label:sum(row[label] for row in rounds) for label in ("baseline","candidate")}
                comparisons.append({"cohort":cohort,"metric":metric,"rounds":rounds,
                  "baseline_total_ms":totals["baseline"],"candidate_total_ms":totals["candidate"],
                  "reduction_percent":100*(1-totals["candidate"]/totals["baseline"])})
        run.update(status="completed",comparisons=comparisons,returns_equivalent=True)
        print(json.dumps({"comparisons":comparisons,"returns_equivalent":True}),flush=True)
    except BaseException as error:
        run.update(status="failed",error={"type":type(error).__name__,"message":str(error)})
        raise
    finally:
        write(work/"run.json",run)

parser=argparse.ArgumentParser()
parser.add_argument("--worker",action="store_true")
for name in ("source","output","cohort","label","key","public","work","baseline","original-capture","run-manifest"):
    parser.add_argument("--"+name)
parser.add_argument("--round",type=int)
parser.add_argument("--candidate-commit",type=commit_argument)
parser.add_argument("--commit",type=commit_argument)
if __name__=="__main__":
    args=parser.parse_args()
    required=("source","commit","output","cohort","label","key","public","run_manifest") if args.worker else ("candidate_commit","work","baseline","original_capture")
    if any(getattr(args,name) is None for name in required):
        parser.error("Missing required diagnostic arguments: "+", ".join(required))
    worker(args) if args.worker else main(args)
