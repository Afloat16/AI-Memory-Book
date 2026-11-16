import base64,csv,datetime,hashlib,io,json,re,stat,sys,tarfile,zipfile
from email.parser import BytesParser
from pathlib import PurePosixPath,PureWindowsPath
from urllib.request import urlopen

def require(condition,message):
    if not condition:
        raise AssertionError(message)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def unique_json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,"Duplicate JSON key: "+key)
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=pairs)
def safe(name):
    path=PurePosixPath(name)
    require(name and not path.is_absolute() and ".." not in path.parts and "\\" not in name,
            "Unsafe archive path: "+name)
def zip_members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        require(len({item.filename for item in infos})==len(infos),"Duplicate ZIP path")
        require(sum(item.file_size for item in infos)<256*1024*1024,"ZIP expansion limit")
        files={}
        for item in infos:
            safe(item.filename)
            kind=stat.S_IFMT(item.external_attr>>16)
            require(kind in (0,stat.S_IFREG,stat.S_IFDIR),"Nonregular ZIP entry")
            if item.is_dir():
                require(item.file_size==0,"Nonempty ZIP directory")
            else:
                files[item.filename]=z.read(item)
        return files
def blob_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

require(configuration["producer_git_blobs"]=={"scripts/build_native_release_cell.py":"a3e4792ab93c06b63288e4832b7a684e383e7ef9",".github/workflows/release.yml":"6ee82db4c25799f29c7e5ca0de6cf3008ee41736"},"Grouped producer/workflow source differs")

expected={name:value["content"].encode("utf-8") for name,value in configuration["sources"].items()}
for name,raw in expected.items():
    require(blob_sha(raw)==configuration["sources"][name]["git_blob_sha1"],"Git source bytes differ: "+name)
runtime={name.removeprefix("src/"):raw for name,raw in expected.items() if name.startswith("src/memory_book/")}
build_inputs={name:raw for name,raw in expected.items() if name.startswith("src/memory_book/") or name in ("pyproject.toml","setup.py","README.md","LICENSE")}
hasher=hashlib.sha256()
for name,raw in sorted(runtime.items()):
    if name.endswith((".py",".c",".h",".rs")):
        hasher.update(name.removeprefix("memory_book/").encode()+b"\0"+raw+b"\0")
runtime_sha=hasher.hexdigest()
require(runtime_sha=="6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7","Published runtime differs from the formally measured compatibility candidate")
artifact=configuration["artifact"]
require(artifact["name"]=="release-"+str(configuration["run_id"])+"-1" and not artifact["expired"],"Publication artifact name/lifetime differs")
require(artifact["workflow_run"]["id"]==configuration["run_id"] and artifact["workflow_run"]["head_sha"]==configuration["commit"],"Artifact source run differs")
with urlopen(configuration["download_url"],timeout=60) as response:
    archive=response.read(32*1024*1024+1)
require(len(archive)<32*1024*1024,"Artifact too large")
require(len(archive)==artifact["size_in_bytes"],"Artifact API byte size differs")
require("sha256:"+sha(archive)==artifact["digest"],"Artifact API digest differs")
outer=zip_members(archive)
require("release-notes.md" in outer,"Missing final published release notes")
assets={name.removeprefix("release-assets/"):raw for name,raw in outer.items() if name.startswith("release-assets/")}
require(set(outer)=={"release-notes.md"}|{"release-assets/"+name for name in assets},
        "Unexpected outer artifact member")
require(len(assets)==67,"Expected exactly 67 prepared assets")
manifest=unique_json(assets["release-manifest.json"])
release_notes=outer["release-notes.md"].decode("utf-8")
require(manifest["schema_version"]==2 and manifest["repository"]=="Afloat16/AI-Memory-Book" and manifest["project"]=="ai-memory-book","Manifest identity/schema differs")
require(manifest["commit"]==configuration["commit"] and manifest["tree"]==configuration["tree"],"Manifest commit/tree differs")
require(manifest["version"]=="0.9.0" and manifest["tag"]=="v0.9.0","Prepared version differs")
require(manifest["runtime_sha256"]==runtime_sha,"Runtime aggregate digest differs")
require(manifest["runtime_files_sha256"]=={name:sha(raw) for name,raw in sorted(runtime.items())},"Runtime hash inventory differs")
require(manifest["source_files_sha256"]=={name:sha(raw) for name,raw in sorted(build_inputs.items())},"Source/build hash inventory differs")
require(set(manifest["assets"])==set(assets)-{"release-manifest.json","SHA256SUMS"},"Manifest asset inventory differs")
for name,record in manifest["assets"].items():
    require(record=={"bytes":len(assets[name]),"sha256":sha(assets[name])},"Manifest asset hash/size differs: "+name)
sums={}
for line in assets["SHA256SUMS"].decode().splitlines():
    digest,name=line.split("  ",1)
    require(name not in sums and re.fullmatch("[0-9a-f]{64}",digest),"Invalid/duplicate checksum line")
    sums[name]=digest
require(set(sums)==set(assets)-{"SHA256SUMS"},"Checksum inventory differs")
require(all(sha(assets[name])==digest for name,digest in sums.items()),"Asset checksum differs")
for name in ("install.py","install.sh","install.ps1"):
    require(assets[name]==expected["scripts/"+name],"Installer differs from committed source: "+name)

def inspect_wheel(filename,native=None):
    raw=assets[filename]
    members=zip_members(raw)
    root="ai_memory_book-0.9.0.dist-info/"
    require(all(name.startswith("memory_book/") or name.startswith(root) for name in members),"Unexpected wheel file")
    actual={name:data for name,data in members.items() if name.startswith("memory_book/")}
    binaries=[name for name in actual if re.fullmatch(r"memory_book/_native\.[^/]+\.(?:so|pyd)",name)]
    if native is None:
        require(not binaries,"Fallback includes a native extension")
    else:
        require(binaries==[native["native_member"]],"Unexpected native member inventory")
        binary=actual.pop(binaries[0])
        require(len(binary)==native["native_bytes"] and sha(binary)==native["native_sha256"],"Native extension digest differs")
    require(actual==runtime,"Wheel source bytes differ: "+filename)
    metadata=BytesParser().parsebytes(members[root+"METADATA"])
    require(metadata["Name"]=="ai-memory-book" and metadata["Version"]=="0.9.0","Wheel package identity differs")
    parts=filename[:-4].split("-")
    require(len(parts)==5 and parts[:2]==["ai_memory_book","0.9.0"],"Wheel filename differs")
    tags=sorted(parts[2]+"-"+parts[3]+"-"+part for part in parts[4].split("."))
    wheel=BytesParser().parsebytes(members[root+"WHEEL"])
    require(sorted(wheel.get_all("Tag",[]))==tags,"Wheel tags differ")
    require(wheel["Root-Is-Purelib"].lower()==("true" if native is None else "false"),"Wheel purelib flag differs")
    rows=list(csv.reader(io.StringIO(members[root+"RECORD"].decode())))
    require(all(len(row)==3 for row in rows) and len({row[0] for row in rows})==len(rows),"Invalid/duplicate wheel RECORD")
    require({row[0] for row in rows}==set(members),"Wheel RECORD inventory differs")
    for name,digest,size in rows:
        if name==root+"RECORD":
            require(digest==size=="","RECORD self hash must be empty")
        else:
            expected_digest="sha256="+base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest()).decode().rstrip("=")
            require(digest==expected_digest and size==str(len(members[name])),"Wheel RECORD hash/size differs")
    return {"member_count":len(members),"source_file_count":len(actual),"record_entries":len(rows)}

matrix={(f"3.{minor}",target) for minor in range(10,16) for target in ("linux_x86_64","linux_aarch64","macos_x86_64","macos_arm64","windows_amd64")}
seen=set()
records=[]
require(len(manifest["native_wheels"])==30,"Native wheel count differs")
require(manifest["native_build_run"]=={"run_id":str(configuration["run_id"]),"run_attempt":1},"Native build run differs")
for record in manifest["native_wheels"]:
    cell=(record["python_version"],record["target"])
    require(cell in matrix and cell not in seen,"Duplicate/unknown matrix cell")
    seen.add(cell)
    filename=record["filename"]
    require(record["bytes"]==len(assets[filename]) and record["sha256"]==sha(assets[filename]),"Native wheel asset digest differs")
    receipt_name=record["receipt"]
    require(receipt_name==filename+".receipt.json","Receipt filename differs")
    receipt=unique_json(assets[receipt_name])
    require(receipt["schema_version"]==1 and receipt["source"]=={"commit":configuration["commit"],"tree":configuration["tree"],"files_sha256":manifest["source_files_sha256"]},"Receipt source identity differs")
    require(receipt["wheel"]=={key:value for key,value in record.items() if key not in ("target","python_version","receipt")},"Receipt wheel metadata differs")
    build=receipt["build"]
    require(build["implementation"]=="cpython" and (build["python_version"],build["target"])==cell,"Receipt interpreter/target differs")
    require(build["python_tag"]=="cp"+cell[0].replace(".","") and build["run_id"]==str(configuration["run_id"]) and build["run_attempt"]==1,"Receipt interpreter/run identity differs")
    flags=["/O2"] if cell[1]=="windows_amd64" else ["-O3"]
    require(build["native_build_mode"]=="1" and build["extra_compile_args"]==flags,"Native optimization mode differs")
    tools={"build":"1.3.0","setuptools":"80.9.0","wheel":"0.45.1"}
    if cell[1].startswith("linux_"):
        tools["auditwheel"]="6.4.2"
    require(build["tools"]==tools,"Pinned build tools differ")
    require(build["build_log"]["commands"] and any(flags[0] in line for line in build["build_log"]["commands"]),"Compiler command provenance differs")
    smoke=receipt["runtime_smoke"]
    require(smoke["backend"]=="native" and smoke["version"]=="0.9.0" and smoke["python_version"]==cell[0] and smoke["native_sha256"]==record["native_sha256"],"Installed native identity differs")
    require(smoke["source_files_match"] is True and smoke["ingest_recall_sources_match"] is True,"Installed native smoke assertions not true")
    inspected=inspect_wheel(filename,record)
    records.append({"python_version":cell[0],"target":cell[1],"filename":filename,"wheel_sha256":record["sha256"],"native_sha256":record["native_sha256"],"receipt_sha256":sha(assets[receipt_name]),**inspected})
require(seen==matrix,"Incomplete native matrix")
fallback=manifest["python_fallback_wheel"]
require(fallback=="ai_memory_book-0.9.0-py3-none-any.whl","Fallback wheel differs")
fallback_inspection=inspect_wheel(fallback)
sdist=manifest["source_distribution"]
require(sdist=="ai_memory_book-0.9.0.tar.gz","Source distribution name differs")
with tarfile.open(fileobj=io.BytesIO(assets[sdist]),mode="r:gz") as z:
    entries=z.getmembers()
    require(len({item.name for item in entries})==len(entries),"Duplicate sdist member")
    require(sum(item.size for item in entries)<256*1024*1024,"Source expansion limit")
    source_members={}
    prefix="ai_memory_book-0.9.0/"
    for item in entries:
        safe(item.name)
        require(item.isfile() or item.isdir(),"Nonregular sdist entry")
        require(item.name==prefix.rstrip("/") or item.name.startswith(prefix),"Unexpected sdist root")
        if item.isfile():
            source_members[item.name.removeprefix(prefix)]=z.extractfile(item).read()
source_runtime={name.removeprefix("src/"):raw for name,raw in source_members.items() if name.startswith("src/memory_book/")}
require(source_runtime==runtime,"Sdist runtime bytes differ")
require(all(source_members[name]==raw for name,raw in build_inputs.items()),"Sdist build input bytes differ")
require(all(value is True for value in manifest["checks"].values()) and len(manifest["checks"])==4,"Package checks not all successful")
run=configuration["run"]
require(run["id"]==configuration["run_id"] and run["head_sha"]==configuration["commit"] and run["run_attempt"]==1,"Workflow run identity differs")
require(run["status"]=="completed" and run["conclusion"]=="success","Workflow run is not successful")
require(run["head_branch"]=="release/v0.9.0" and run["event"]=="push","Workflow is not the dedicated final release push")
jobs=configuration["jobs"]["jobs"]
require(len({job["id"] for job in jobs})==len(jobs),"Duplicate workflow job")
targets=("linux_x86_64","linux_aarch64","macos_x86_64","macos_arm64","windows_amd64")
versions=tuple("3."+str(minor) for minor in range(10,16))
native_jobs=[job for job in jobs if job["name"].startswith("native-wheel ")]
require(len(native_jobs)==5,"Grouped native job count differs")
job_by_target={}
for job in native_jobs:
    matched=re.fullmatch(r"native-wheel \(([a-z0-9_]+)\)",job["name"])
    require(matched is not None,"Unexpected grouped native job name")
    target=matched[1]
    require(target in targets and target not in job_by_target,"Duplicate/unknown native platform job")
    job_by_target[target]=job
    require(job["head_sha"]==configuration["commit"] and job["run_attempt"]==1 and job["run_id"]==configuration["run_id"],"Job source/run differs")
    require(job["status"]=="completed" and job["conclusion"]=="success","Native job not successful")
    names=[step["name"] for step in job["steps"]]
    require(len(names)==len(set(names)),"Duplicate native step name")
    steps={step["name"]:step for step in job["steps"]}
    numbered=[]
    for version in versions:
        for name in ("Set up CPython "+version,"Build install and verify CPython "+version):
            require(name in steps and steps[name]["status"]=="completed" and steps[name]["conclusion"]=="success","Native setup/build-test step not successful: "+name)
            numbered.append(steps[name]["number"])
    require(numbered==sorted(set(numbered)),"Native interpreters were not built in explicit sequential steps")
    require(sum(name.startswith("Set up CPython ") for name in names)==6 and sum(name.startswith("Build install and verify CPython ") for name in names)==6,"Unexpected setup/build-test inventory")
    for name in ("Retain each successfully tested wheel and receipt","Preserve all six native cell logs and validation records"):
        require(name in steps and steps[name]["conclusion"]=="success","Native artifacts/evidence upload not successful")
require(set(job_by_target)==set(targets),"Incomplete successful platform jobs")

def timestamp_free(text):
    text=re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]","",text).replace("\r\n","\n")
    return re.sub(r"(?m)^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z ","",text)

retained_cell_archives={}

def downloaded_artifact(document,url,name,limit=16*1024*1024):
    require(document["name"]==name and not document["expired"],"Cell artifact name/lifetime differs")
    require(document["workflow_run"]["id"]==configuration["run_id"] and document["workflow_run"]["head_sha"]==configuration["commit"],"Cell artifact run/source differs")
    with urlopen(url,timeout=60) as response:
        raw=response.read(limit+1)
    require(len(raw)<=limit and len(raw)==document["size_in_bytes"],"Cell artifact API byte size differs")
    require(document["digest"]=="sha256:"+sha(raw),"Cell artifact API digest differs")
    files=zip_members(raw)
    if name.startswith("native-cell-evidence-"):
        retained_cell_archives[name.removeprefix("native-cell-evidence-")]={"artifact_id":document["id"],"raw":raw,"sha256":sha(raw),"bytes":len(raw),"git_blob_sha1":blob_sha(raw)}
    return files,{"id":document["id"],"name":document["name"],"bytes":len(raw),"sha256":sha(raw),"file_count":len(files),"created_at":document["created_at"],"expires_at":document["expires_at"]}

def actual_tests(raw):
    plain=timestamp_free(raw.decode("utf-8")).strip()
    results=re.findall(r"(?m)^Ran (\d+) tests? in ([0-9.]+)s$",plain)
    endings=re.findall(r"(?m)^(OK(?: \([^\n]*\))?|FAILED(?: \([^\n]*\))?)$",plain)
    require(len(results)==1 and results[0][0]=="144" and len(endings)==1 and endings[0].startswith("OK"),"Cell actual installed test result differs")
    match=re.search(r"\bskipped=(\d+)",endings[0])
    skipped=int(match[1]) if match else 0
    skipped_lines=[line for line in plain.splitlines() if "... skipped " in line]
    require(len(skipped_lines)==skipped,"Cell skipped-test count differs")
    allowed_skips=(
        ("test_token_caps_keep_complete_payload_counts_and_source_spans","tests.test_native_backend.NativeMemoryBookEquivalenceTests","Install .[tokens]"),
        ("test_both_token_encoders_keep_exact_budgets_and_source_refs","tests.test_native_ranking_backend.NativeStoreEquivalenceTests","Install .[tokens]"),
        ("test_available_shared_gil_subinterpreters_keep_main_module_working","tests.test_native_segmentation_backend.NativeSegmentationModuleStateTests","_xxsubinterpreters is not available in this Python build"),
    )
    observed_skips=set()
    for line in skipped_lines:
        matching=[index for index,(method,cls,reason) in enumerate(allowed_skips)
                  if re.fullmatch(re.escape(method)+r" \("+re.escape(cls)+r"(?:"+re.escape("."+method)+r")?\) \.\.\. skipped "+re.escape(repr(reason)),line)]
        require(len(matching)==1 and matching[0] not in observed_skips,"Unexpected or duplicate skipped native testcase")
        observed_skips.add(matching[0])
    require(observed_skips in ({0,1},{0,1,2}),"Only the two frozen optional-token skips and the exact optional subinterpreter skip are accepted")
    require("ERROR: AddressSanitizer" not in plain and not re.search(r"(?m)^(ERROR|FAIL): ",plain),"Unexpected actual test failure")
    return {"tests_run":144,"skipped":skipped,"summary":endings[0],"successful_summary":True,"skipped_test_lines":skipped_lines,"reported_test_seconds":float(results[0][1])}

def platform_path(value,target):
    path=PureWindowsPath(value) if target=="windows_amd64" else PurePosixPath(value)
    require(path.is_absolute(),"Cell subprocess path is not absolute")
    return str(path).replace("\\","/")

suites=[
 "tests.test_native_backend","tests.test_native_identifier_backend",
 "tests.test_native_excerpt_backend","tests.test_native_lexical_backend",
 "tests.test_native_window_backend","tests.test_native_ranking_backend",
 "tests.test_native_source_backend","tests.test_native_segmentation_backend"]
evidence=configuration["cell_evidence"]
require(set(evidence)==set(targets),"Cell evidence artifact inventory differs")
require(set(configuration["native_wheel_artifacts"])==set(targets),"Grouped wheel artifact inventory differs")
receipt_by_cell={(record["python_version"],record["target"]):unique_json(assets[record["receipt"]]) for record in manifest["native_wheels"]}
record_by_cell={(record["python_version"],record["target"]):record for record in manifest["native_wheels"]}
cell_records=[]
artifact_records=[]
wheel_artifact_records=[]
seen_cells=set()
for target in targets:
    item=evidence[target]
    files,artifact_record=downloaded_artifact(item["artifact"],item["download_url"],"native-cell-evidence-"+target)
    artifact_records.append(artifact_record)
    expected_names=set()
    job=job_by_target[target]
    job_log=configuration["job_logs"][str(job["id"])]
    plain_job=timestamp_free(job_log)
    starts=list(re.finditer(r"(?m)^##\[group\]Run [^\n]*scripts/build_native_release_cell\.py --expected-python (3\.\d+) --target[^\n]*$",plain_job))
    require([match[1] for match in starts]==list(versions),"Actual job log does not contain six explicit interpreter invocations")
    blocks={}
    for match in starts:
        end=re.search(r"(?m)^##\[group\]Run ",plain_job[match.end():])
        blocks[match[1]]=plain_job[match.start():match.end()+end.start() if end else len(plain_job)]
    wheel_item=configuration["native_wheel_artifacts"][target]
    wheel_files,wheel_artifact=downloaded_artifact(wheel_item["artifact"],wheel_item["download_url"],"native-wheel-"+target)
    expected_wheels={record[key]:assets[record[key]] for record in manifest["native_wheels"] if record["target"]==target for key in ("filename","receipt")}
    require(len(wheel_files)==12 and wheel_files==expected_wheels,"Grouped wheel artifact does not contain exactly the six audited wheel/receipt pairs")
    wheel_artifact_records.append(wheel_artifact)
    for version in versions:
        cell=(version,target)
        require(cell not in seen_cells,"Duplicate actual native cell evidence")
        seen_cells.add(cell)
        cp="cp"+version.replace(".","")
        prefix=cp+"/"
        build_log="native-build-"+target+"-"+cp+".log"
        logs={"tools.log",build_log,"install.log","native-import.log","test.log","receipt.log"}
        phases=["build-tools"]
        if target.startswith("linux_"):
            logs|={"abi-tools.log","repair.log"}
            phases+=["abi-tools"]
        phases+=["compile-wheel"]
        if target.startswith("linux_"):
            phases+=["repair-wheel"]
        if target.startswith("macos_"):
            logs.add("architecture.log")
            phases+=["macho-slices"]
        phases+=["install-wheel","isolated-native-import","installed-native-tests","installed-native-smoke-and-receipt"]
        expected_names|={prefix+name for name in logs|{"validation.json"}}
        require(all(prefix+name in files for name in logs|{"validation.json"}),"Cell evidence file missing")
        raw_validation=files[prefix+"validation.json"]
        report=unique_json(raw_validation)
        record=record_by_cell[cell]
        receipt=receipt_by_cell[cell]
        require(report["schema_version"]==1 and report["status"]=="passed","Cell validation is not passed")
        require((report["expected_python"],report["target"])==cell and report["step_id"]=="cell"+version.replace(".",""),"Cell minor/target/step differs")
        require(report["run_id"]==str(configuration["run_id"]) and report["run_attempt"]=="1","Cell validation run/attempt differs")
        require(report["runner_name"]==job["runner_name"] and report["runner_name"],"Cell runner differs from actual job")
        require(report["source"]=={"version":"0.9.0","tag":"v0.9.0","commit":configuration["commit"],"tree":configuration["tree"],"files_sha256":manifest["source_files_sha256"]},"Cell source/build inventory differs")
        interpreter=report["interpreter"]
        require(interpreter["implementation"]=="cpython" and interpreter["python_version"]==version,"Cell interpreter differs")
        require(re.match(re.escape(version)+r"\.",interpreter["setup_python_version"]) and interpreter["version"].startswith(interpreter["setup_python_version"]+" "),"Cell resolved interpreter version differs")
        executable=interpreter["executable"]
        platform_path(executable,target)
        platform_path(interpreter["setup_python_path"],target)
        require(report["build_log"]==build_log,"Cell compiler log filename differs")
        commands=report["commands"]
        require([entry["phase"] for entry in commands]==phases,"Cell subprocess phase order differs")
        require(len({entry["log"] for entry in commands})==len(commands) and {entry["log"] for entry in commands}==logs,"Cell command log inventory differs")
        by_phase={entry["phase"]:entry for entry in commands}
        actual_commands=[]
        for match in re.finditer(r"(?m)^CELL COMMAND ([a-z-]+) (\[[^\n]+\])$",blocks[version]):
            actual_commands.append((match[1],unique_json(match[2])))
        require(actual_commands==[(entry["phase"],entry["command"]) for entry in commands],"Actual job commands differ from cell validation")
        for entry in commands:
            require(entry["returncode"]==0 and isinstance(entry["elapsed_seconds"],(float,int)) and entry["elapsed_seconds"]>=0,"Cell subprocess failed")
            require(entry["cwd"]==commands[0]["cwd"],"Cell subprocess working directory changed")
            platform_path(entry["cwd"],target)
            raw=files[prefix+entry["log"]]
            require(entry["log_bytes"]==len(raw) and entry["log_sha256"]==sha(raw),"Cell raw log hash/size differs")
            if entry["phase"]!="macho-slices":
                require(entry["command"][0]==executable,"Cell subprocess uses a different interpreter")
            logged=timestamp_free(raw.decode("utf-8")).strip("\n")
            if logged:
                require(logged in blocks[version],"Retained cell log does not appear in the actual step output: "+entry["phase"])
        require(by_phase["build-tools"]["command"]==[executable,"-m","pip","install","setuptools==80.9.0","wheel==0.45.1","build==1.3.0"],"Build tool command differs")
        if target.startswith("linux_"):
            require(by_phase["abi-tools"]["command"]==[executable,"-m","pip","install","auditwheel==6.4.2","patchelf==0.17.2.4"],"Linux ABI tool command differs")
        compile_args=by_phase["compile-wheel"]["command"]
        require(compile_args[:8]==[executable,"-m","pip","wheel","--verbose","--no-deps","--no-build-isolation","--wheel-dir"] and len(compile_args)==10 and compile_args[-1]==".","Native compile command differs")
        require(platform_path(compile_args[8],target).endswith("/native-build-cells/"+target+"/"+cp+"/raw"),"Cell raw build directory is not isolated")
        install_args=by_phase["install-wheel"]["command"]
        require(install_args[:6]==[executable,"-m","pip","install","--no-deps","--force-reinstall"] and len(install_args)==7,"Installed wheel command differs")
        repaired=platform_path(install_args[6],target)
        require(repaired.endswith("/native-build-cells/"+target+"/"+cp+"/repaired/"+record["filename"]),"Installed wheel is not this isolated cell's repaired wheel")
        require(by_phase["isolated-native-import"]["command"]==[executable,"-I","-c","from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'"],"Isolated native import command differs")
        require(by_phase["installed-native-tests"]["command"]==[executable,"-m","unittest",*suites,"-v"],"Installed native suite selection differs")
        receipt_args=by_phase["installed-native-smoke-and-receipt"]["command"]
        require(receipt_args==[executable,"scripts/native_release.py","receipt","--wheel",install_args[6],"--output",install_args[6]+".receipt.json","--target",target],"Original smoke/receipt command differs")
        raw_build=files[prefix+build_log]
        build=receipt["build"]["build_log"]
        require(build["filename"]==build_log and build["bytes"]==len(raw_build) and build["sha256"]==sha(raw_build),"Receipt compiler log identity differs")
        compiler=re.compile(r"\b(?:gcc(?:-\d+)?|g\+\+|cc|clang(?:-cl)?|cl\.exe|link\.exe)\b",re.I)
        compiler_lines=[line.strip() for line in raw_build.decode("utf-8").splitlines() if "_native" in line and compiler.search(line) and re.search(r"(?:^|\s)(?:-c|-shared|-bundle|/c|/DLL)(?:\s|$)",line,re.I)]
        require(compiler_lines==build["commands"] and compiler_lines,"Receipt compiler commands differ from actual raw compilation")
        test_result=actual_tests(files[prefix+"test.log"])
        require(report["tests"]=={key:value for key,value in test_result.items() if key!="reported_test_seconds"}|{"returncode":0,"suites":suites,"log":"test.log","log_sha256":sha(files[prefix+"test.log"])},"Cell declared tests differ from actual test log")
        if target.startswith("macos_"):
            arch="arm64" if target=="macos_arm64" else "x86_64"
            require(report["macos_build"]["architecture"]==arch and report["macos_build"]["observed_slices"]==[arch],"Mach-O architecture validation differs")
            require(files[prefix+"architecture.log"].decode().split()==[arch],"Actual Mach-O slice output differs")
        require(report["wheel"]=={"filename":record["filename"],"bytes":record["bytes"],"sha256":record["sha256"],"native_sha256":record["native_sha256"]},"Cell wheel digest differs")
        require(report["receipt"]=={"filename":record["receipt"],"sha256":sha(assets[record["receipt"]])},"Cell original receipt digest differs")
        require(report["runtime_smoke"]==receipt["runtime_smoke"],"Cell smoke differs from original validated receipt")
        cell_records.append({"python_version":version,"target":target,"job_id":job["id"],"step_id":report["step_id"],"setup_step_number":next(step["number"] for step in job["steps"] if step["name"]=="Set up CPython "+version),"build_step_number":next(step["number"] for step in job["steps"] if step["name"]=="Build install and verify CPython "+version),"runner_name":report["runner_name"],"interpreter":interpreter,"validation_sha256":sha(raw_validation),"evidence_artifact_id":artifact_record["id"],"evidence_prefix":prefix,"wheel":report["wheel"],"receipt":report["receipt"],"tests":{**test_result,"passed":144-test_result["skipped"],"log_sha256":sha(files[prefix+"test.log"])},"compiler_log":build,"commands":[{key:entry[key] for key in ("phase","command","returncode","log","log_bytes","log_sha256")} for entry in commands],"runtime_smoke":report["runtime_smoke"]})
    require(set(files)==expected_names,"Unexpected grouped cell evidence inventory")
require(seen_cells==matrix and len(cell_records)==30,"Incomplete actual tested cell matrix")
expected_job_names={"preflight","release","prepare-only","published-install"}|{"native-wheel ("+target+")" for target in targets}
require(len(jobs)==9 and {job["name"] for job in jobs}==expected_job_names,"Final workflow job inventory differs")
by_name={job["name"]:job for job in jobs}
for name,job in by_name.items():
    require(job["head_sha"]==configuration["commit"] and job["run_id"]==configuration["run_id"] and job["run_attempt"]==1,"Final job identity differs")
    require(job["status"]=="completed" and job["conclusion"]==("skipped" if name=="prepare-only" else "success"),"Final workflow did not complete every required gate")
release_job=by_name["release"]
public_install=by_name["published-install"]
for name in ("Verify existing CI, build, check and publish","Preserve release assets and checksums"):
    require(next(step for step in release_job["steps"] if step["name"]==name)["conclusion"]=="success","Actual publication step not successful")
public_step=next(step for step in public_install["steps"] if step["name"]=="Install through the real public URL and default release-wheel path")
require(public_step["conclusion"]=="success","Actual public installer step not successful")
release_log=configuration["job_logs"][str(release_job["id"])]
public_log=configuration["job_logs"][str(public_install["id"])]
require("Default text backend: native" in public_log and "Verified public installer URL, release wheel, version and default MCP/client extras." in public_log,"Actual default public native/MCP/client installer proof missing")
require(re.search(r"Successfully installed [^\r\n]*ai-memory-book-0\.9\.0(?:\s|$)",public_log),"Public installer did not report the released package version")
release=configuration["published_release"]
require(type(release["id"]) is int and release["id"]>0,"Invalid public release ID")
require(release["tag_name"]=="v0.9.0" and release["target_commitish"]==configuration["commit"] and release["draft"] is False and release["prerelease"] is False,"Published release identity/channel differs")
latest=configuration["latest_release"]
require(latest["id"]==release["id"] and latest["tag_name"]=="v0.9.0" and latest["target_commitish"]==configuration["commit"] and latest["draft"] is False and latest["prerelease"] is False,"The formal release is not Latest")
for ref in (configuration["main_ref"],configuration["tag_ref"]):
    require(ref["object"]["sha"]==configuration["commit"] and ref["object"]["type"]=="commit","Final main/tag must directly identify the exact final commit")
public_assets=configuration["public_assets"]
require(len(public_assets)==67 and len({item["name"] for item in public_assets})==67 and {item["name"] for item in public_assets}==set(assets),"Published 67-asset inventory differs")
public_asset_records=[]
for item in public_assets:
    name=item["name"]
    require(item["state"]=="uploaded" and item["size"]==len(assets[name]),"Published asset size/state differs")
    require(item["digest"]=="sha256:"+sha(assets[name]),"Published asset API digest differs from independently audited bytes")
    require(item["browser_download_url"]=="https://github.com/Afloat16/AI-Memory-Book/releases/download/v0.9.0/"+name,"Unexpected public asset URL")
    public_asset_records.append({key:item[key] for key in ("id","name","state","size","digest","created_at","updated_at","browser_download_url")})
require({item["name"]:item["id"] for item in release["assets"]}=={item["name"]:item["id"] for item in public_assets},"Release object and asset-list endpoint differ")
ci=configuration["publication_ci_run"]
ci_jobs=configuration["publication_ci_jobs"]["jobs"]
ci_names={"core (3.10)","core (3.12)","core (3.13)","core (3.14)","core (3.15)","mcp","reader-browser","installers (ubuntu-latest)","installers (macos-latest)","installers (windows-latest)","container"}
require(ci["head_sha"]==configuration["commit"] and ci["event"]=="push" and ci["status"]=="completed" and ci["conclusion"]=="success","Publication CI is not a successful exact-commit push")
require(len(ci_jobs)==11 and {job["name"] for job in ci_jobs}==ci_names,"Publication CI does not contain exactly the 11 original gates")
for job in ci_jobs:
    require(job["head_sha"]==configuration["commit"] and job["run_id"]==ci["id"] and job["run_attempt"]==ci["run_attempt"] and job["status"]=="completed" and job["conclusion"]=="success","Publication CI job identity/result differs")
committed_notes=configuration["committed_release_notes"]
require(blob_sha(committed_notes["content"].encode())==committed_notes["git_blob_sha1"],"Committed release notes Git bytes differ")
expected_notes=committed_notes["content"]+"\n\nSource commit: "+chr(96)+configuration["commit"]+chr(96)+".\n\nCI: "+ci["html_url"]+"\n\nRelease workflow: https://github.com/Afloat16/AI-Memory-Book/actions/runs/"+str(configuration["run_id"])+"\n"
require(release_notes==expected_notes and release["body"]==release_notes,"Archive/public release notes differ from the exact committed notes and actual CI/run binding")
published=[]
for line in release_log.splitlines():
    if '"published": ' in line and '"commit": ' in line and "{" in line:
        try:
            value=unique_json(line[line.index("{"):])
        except (ValueError,AssertionError):
            continue
        if value.get("published")==release["html_url"]:
            published.append(value)
require(len(published)==1,"Actual publication completion JSON missing or duplicated")
require(published[0]["tag"]=="v0.9.0" and published[0]["commit"]==configuration["commit"] and published[0]["prerelease"] is False and published[0]["assets"]==67,"Actual publication completion identity/count differs")
require(len(retained_cell_archives)==5,"Original cell evidence ZIP bytes were not retained")
def emit_record(name,value):
    print(name+"="+json.dumps(value,sort_keys=True),flush=True)
    require(sys.stdin.readline().strip()=="NEXT","Expected read-only audit output acknowledgement")
job_matrix={"schema_version":2,"run_id":configuration["run_id"],"run_attempt":1,"head_sha":configuration["commit"],"head_branch":run["head_branch"],"workflow_path":run["path"],"status":run["status"],"conclusion":run["conclusion"],"created_at":run["created_at"],"updated_at":run["updated_at"],"job_count":len(jobs),"native_platform_jobs":5,"independently_tested_cells":30,"jobs":[{key:job[key] for key in ("id","name","status","conclusion","head_sha","run_attempt","html_url","started_at","completed_at")} for job in jobs],"native_job_logs":[{"job_id":job["id"],"decoded_log_sha256":sha(configuration["job_logs"][str(job["id"])].encode()),"decoded_log_bytes":len(configuration["job_logs"][str(job["id"])].encode())} for job in native_jobs],"cell_evidence_artifacts":artifact_records,"native_wheel_artifacts":wheel_artifact_records,"native_installed_tests":cell_records,"publication":{"job_id":release_job["id"],"decoded_log_sha256":sha(release_log.encode()),"decoded_log_bytes":len(release_log.encode()),"actual_published_summary":published[0]},"published_install":{"job_id":public_install["id"],"decoded_log_sha256":sha(public_log.encode()),"decoded_log_bytes":len(public_log.encode()),"actual_backend_and_completion_lines":[line for line in public_log.splitlines() if "Default text backend:" in line or "Verified public installer URL" in line or re.search(r"Successfully installed [^\r\n]*ai-memory-book-0\.9\.0",line)]},"scope":"Read-only final-publication proof of five platform jobs and 30 independently built, installed and tested cells in one exact-final-source run/attempt. Every actual step command, 144-test log, compiler log, original receipt and artifact is cross-bound. The real public default installer succeeded; no jobs, application tests or measurements were rerun."}
emit_record("PUBLICATION_JOBS_JSON",job_matrix)

audit={"schema_version":2,"status":"passed","prepared_only":False,"published":True,
       "run_id":configuration["run_id"],"run_attempt":1,"commit":configuration["commit"],"tree":configuration["tree"],"runtime_sha256":runtime_sha,
       "artifact":{key:artifact[key] for key in ("id","name","size_in_bytes","digest","created_at","expires_at")},
       "archive":{"sha256":sha(archive),"bytes":len(archive),"file_count":len(outer),"asset_count":len(assets),"manifest_payload_count":len(manifest["assets"]),"checksummed_file_count":len(sums)},
       "source":{"producer_git_blobs":configuration["producer_git_blobs"],"runtime_files":len(runtime),"build_inputs":len(build_inputs),"expected_git_blob_sha1":{name:value["git_blob_sha1"] for name,value in configuration["sources"].items()}},
       "matrix":records,"fallback_wheel":fallback_inspection,"sdist":{"members":len(source_members),"runtime_source_files":len(source_runtime)},
       "manifest_sha256":sha(assets["release-manifest.json"]),"release_notes_sha256":sha(outer["release-notes.md"]),
       "checks":["All 67 prepared asset bytes match manifest/SHA256SUMS inventories.","All 30 receipt source/build hashes match independently fetched exact Git source.","All 30 native and fallback wheel source bytes, metadata, native hashes and complete RECORD inventories verified in RAM.","Source distribution runtime and build inputs match the exact Git source.","The exact final release package checks passed; the actual public installer verified native backend, released version and default MCP/client extras.","No ZIP, wheel or source distribution was written to disk."],
       "scope":"Final-publication archive and identity audit. Public API digests are compared with independently audited artifact bytes; the unchanged publisher also downloads and hashes every remote asset before and after publication. Companion jobs proof binds all 30 fresh cells and the actual public installer to this exact final run/attempt."}
audit["auditor"]={"source":configuration["script"],"bytes":len(configuration["script"].encode()),"sha256":sha(configuration["script"].encode())}
emit_record("PUBLICATION_AUDIT_JSON",audit)
publication={"schema_version":1,"status":"passed","run_id":configuration["run_id"],"run_attempt":1,"commit":configuration["commit"],"tree":configuration["tree"],"runtime_sha256":runtime_sha,"release":{key:release[key] for key in ("id","tag_name","name","target_commitish","draft","prerelease","html_url","created_at","published_at")},"release_body_sha256":sha(release["body"].encode()),"latest_release_id":latest["id"],"main_ref":configuration["main_ref"],"tag_ref":configuration["tag_ref"],"assets":public_asset_records,"publication_ci":{"id":ci["id"],"run_attempt":ci["run_attempt"],"head_sha":ci["head_sha"],"event":ci["event"],"status":ci["status"],"conclusion":ci["conclusion"],"html_url":ci["html_url"],"jobs":[{key:job[key] for key in ("id","name","run_id","run_attempt","head_sha","status","conclusion","html_url")} for job in ci_jobs]},"committed_release_notes_git_blob":committed_notes["git_blob_sha1"],"actual_public_installer_job_id":public_install["id"],"public_asset_verification_scope":"All 67 API SHA256 digests and sizes match the corresponding independently read artifact bytes. The pinned release.py independently downloaded and hashed remote assets as part of the successful publication step; this auditor does not claim a second independent public download of all 67 assets."}
emit_record("PUBLICATION_API_JSON",publication)
emit_record("PUBLICATION_RELEASE_NOTES_TEXT",release_notes)
emit_record("PUBLICATION_MANIFEST_TEXT",assets["release-manifest.json"].decode("utf-8"))
for target in targets:
    record=retained_cell_archives[target]
    emit_record("PUBLICATION_RAW_EVIDENCE_JSON",{"target":target,**{key:record[key] for key in ("artifact_id","bytes","sha256","git_blob_sha1")},"base64":base64.b64encode(record["raw"]).decode()})
print("PUBLICATION_AUDIT_COMPLETE",flush=True)
