"""Untimed exact-source capture for the final 22-entry refinement candidate."""
from __future__ import annotations
import ast, hashlib, importlib.util, json, os, platform, re, subprocess, sys, sysconfig, unittest
from pathlib import Path

ROOT=Path.cwd().resolve()
CANDIDATE="e91183bf6dd9e125d6549ec3fe5d9c81598cd131"
BASELINE="56eccd8c3a6f1d5637664607936da2595ce50c62"
WORK=ROOT.parent/"final-probe-e91183bf"
sys.path.insert(0,str(ROOT));sys.path.insert(1,str(ROOT/"scripts"))
from scripts import native_core_refinement_performance as perf
from scripts import native_core_refinement_host as host
spec=importlib.util.spec_from_file_location("diagnostic_checks",ROOT.parent/"diagnose_refinement_ingestion_v3.py")
checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
def write(path,value): checks.write(path,value)
def ast_bodies(path):
    return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text()).body
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
assert not WORK.exists(),"Never replace a previous capture"
WORK.mkdir()
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()==CANDIDATE
assert not subprocess.check_output(["git","status","--porcelain"],text=True).strip()
flags=checks.reject_sanitizer_environment(os.environ)
capture_path=ROOT.parent/"capture-a0c73165/capture.json"
capture_raw=capture_path.read_bytes()
assert hashlib.sha256(capture_raw).hexdigest()==checks.APPROVED_BASELINE_CAPTURE
original=json.loads(capture_raw)
approved=original["sources"]["baseline"]
assert approved["status"]=="completed" and approved["source_and_binary_unchanged"]
assert set(approved["source_manifest_before"]["native_binaries"].values())=={checks.APPROVED_BASELINE_BINARY}
compiler=subprocess.check_output(["gcc","--version"],text=True)
assert compiler==original["environment"]["compiler"] and sys.version==original["environment"]["python"]
environment={**os.environ,"CC":"gcc","MEMORY_BOOK_BUILD_NATIVE":"1","MEMORY_BOOK_TEXT_BACKEND":"native",
             "PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0"}
environment.pop("PYTHONPATH",None);environment.pop("PYTHONHOME",None)
run={"schema_version":1,"purpose":"Untimed source/build/protocol/probe correctness capture only; no performance claim",
     "status":"started","baseline_commit":BASELINE,"candidate_commit":CANDIDATE,
     "evaluator_commit":CANDIDATE,"evaluator_files":perf.evaluator_manifest(host.PLAN),
     "runner_sha256":perf.sha(Path(__file__).read_bytes()),
     "dependency_runner_sha256":perf.sha((ROOT.parent/"diagnose_refinement_ingestion_v3.py").read_bytes()),
     "environment":{"python":sys.version,"executable":sys.executable,"platform":platform.platform(),
                    "compiler":compiler,"pythonhashseed":"0","sanitizer_check":flags},
     "baseline_reused_from_approved_capture":{"capture_sha256":checks.APPROVED_BASELINE_CAPTURE,
         "native_binary_sha256":checks.APPROVED_BASELINE_BINARY,"build":approved},
     "tests":None,"ast":None,"build":None,"probes":{},"error":None}
write(WORK/"capture.json",run)
try:
    test_code = """import json,sys,unittest
suite=unittest.defaultTestLoader.discover('tests',pattern='test_native_core_refinement_performance.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
print('RESULT_JSON='+json.dumps({'tests_run':result.testsRun,'skipped':len(result.skipped),
'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful()}))
sys.exit(0 if result.wasSuccessful() else 1)
"""
    command=[sys.executable,"-c",test_code]
    result=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,timeout=180)
    (WORK/"protocol-tests.log").write_text(result.stdout+result.stderr)
    lines=[line for line in result.stdout.splitlines() if line.startswith("RESULT_JSON=")]
    run["tests"]={"command":command,"returncode":result.returncode,
                  "log_sha256":perf.sha((WORK/"protocol-tests.log").read_bytes()),
                  "result":json.loads(lines[-1].split("=",1)[1]) if lines else None}
    write(WORK/"capture.json",run)
    assert result.returncode==0,result.stdout+result.stderr
    assert run["tests"]["result"]=={"tests_run":26,"skipped":0,"failures":0,"errors":0,"successful":True}
    print("PROTOCOL_TESTS="+json.dumps(run["tests"]["result"]),flush=True)
    core_names=("mcp_calls","Ledger","validate_response","make_row","summary","archive_state","query_order",
                "stable","schedule","worker","common_probe_suite","comparisons","ingestion_comparisons","dispatch_probe")
    old=ast_bodies(ROOT/"scripts/native_core_performance.py")
    new=ast_bodies(ROOT/"scripts/native_core_refinement_performance.py")
    assert all(old[name]==new[name] for name in core_names)
    run["ast"]={"reference_file":"scripts/native_core_performance.py",
      "reference_file_sha256":perf.sha((ROOT/"scripts/native_core_performance.py").read_bytes()),
      "all_equal":True,"cores":{name:perf.sha(new[name].encode()) for name in core_names}}
    write(WORK/"capture.json",run)
    print("AST_CORES="+str(len(core_names)),flush=True)
    destination=WORK/"candidate"
    host.materialize(CANDIDATE,destination)
    configurations,native_inputs=host.build_input_identity(destination,{"commit":CANDIDATE,"backend":"native"})
    command=[sys.executable,"setup.py","build_ext","--inplace","--build-temp",str(WORK/"build-temp")]
    run["build"]={"status":"started","command":command,"compiler":compiler,
       "extra_compile_args":["-O3"],"build_inputs":configurations,"native_source_inputs":native_inputs}
    write(WORK/"capture.json",run)
    with (WORK/"build.log").open("xb") as stream:
        result=subprocess.run(command,cwd=destination,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    run["build"].update(returncode=result.returncode,log_sha256=perf.sha((WORK/"build.log").read_bytes()))
    write(WORK/"capture.json",run)
    assert result.returncode==0,"Candidate native compilation failed"
    assert not re.search(r"(?:-fsanitize|lib(?:asan|ubsan|tsan|msan|lsan))",(WORK/"build.log").read_text())
    run["build"]["status"]="completed"
    sources={"baseline":ROOT.parent/"capture-a0c73165/baseline/src","candidate":destination/"src"}
    manifests={label:perf.source_manifest(source,{"commit":BASELINE if label=="baseline" else CANDIDATE,
        "backend":"native"}) for label,source in sources.items()}
    assert manifests["baseline"]==approved["source_manifest_before"]
    run["source_manifests_before"]=manifests
    run["binary_checks"]={label:checks.inspect_binary(source.parent/next(iter(manifests[label]["native_binaries"])))
        for label,source in sources.items()}
    write(WORK/"capture.json",run)
    probe_code="""import sys
from pathlib import Path
source=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve();label=sys.argv[3]
sys.path.insert(0,str(root/"scripts"));sys.path.insert(0,str(source))
import native_core_refinement_performance as perf
result=perf.active_backend(source,None)
probe=result["dispatch_probe"]
assert set(probe["native_helper_calls"])==set(perf.PROBE_HELPERS[label])
assert probe["native_helper_effective_calls"]==probe["native_helper_calls"]
assert all(value>0 for value in probe["native_helper_calls"].values())
assert all(value==0 for value in probe["native_helper_fallback_calls"].values())
assert probe["outputs_sha256"]=="9c30e47eb2e492cb5f6595f6f6d7d337bc2d932bdb1a821c4cdd0fd9b51399de"
print(perf.dump(result))
"""
    for label,source in sources.items():
        result=subprocess.run([sys.executable,"-c",probe_code,str(source),str(ROOT),label],cwd=ROOT,
            env=environment,capture_output=True,text=True,timeout=120)
        (WORK/(label+"-probe.log")).write_text(result.stdout+result.stderr)
        assert result.returncode==0,result.stdout+result.stderr
        captured=json.loads(result.stdout)
        assert captured["binary_sha256"] in manifests[label]["native_binaries"].values()
        run["probes"][label]=captured
        write(WORK/"capture.json",run)
        print(label+"_PROBE="+json.dumps(captured["dispatch_probe"]),flush=True)
    after={label:perf.source_manifest(source,{"commit":BASELINE if label=="baseline" else CANDIDATE,"backend":"native"})
           for label,source in sources.items()}
    assert manifests==after
    run["source_manifests_after"]=after
    run.update(status="completed",source_and_binary_unchanged=True,probe_outputs_equal=True)
except BaseException as error:
    run.update(status="failed",error={"type":type(error).__name__,"message":str(error)})
    raise
finally:
    write(WORK/"capture.json",run)
print("COMPLETE="+json.dumps({"status":run["status"],"capture_sha256":perf.sha((WORK/"capture.json").read_bytes()),
    "binary_checks":run.get("binary_checks")}),flush=True)
