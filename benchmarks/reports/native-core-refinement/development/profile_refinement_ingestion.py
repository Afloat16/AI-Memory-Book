"""cProfile hotspot diagnosis on a named frozen cohort; never formal performance evidence."""
import argparse, cProfile, hashlib, json, os, platform, pstats, sys
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument("--source",required=True); parser.add_argument("--commit",required=True)
parser.add_argument("--output",required=True)
parser.add_argument("--cohort",required=True)
parser.add_argument("--public",required=True)
args=parser.parse_args()
repo=Path.cwd().resolve(); source=Path(args.source).resolve()
sys.path.insert(0,str(source));sys.path.insert(1,str(repo/"scripts"))
import native_core_performance as perf
manifest_before=perf.source_manifest(source,{"commit":args.commit,"backend":"native"})
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
assert BACKEND_NAME=="native"
data=perf.dataset(args.cohort,Path(args.public))
assert len(data.sessions)==({"synthetic61":112,"public1015":216}[args.cohort])
with MemoryBook(":memory:",cache_size=0) as book:
    fresh=[book.ingest(session) for session in data.sessions]
    profiler=cProfile.Profile()
    profiler.enable()
    unchanged=[book.ingest(session) for _ in range(10) for session in data.sessions]
    profiler.disable()
assert len(unchanged)==10*len(data.sessions) and all(item["skipped"] for item in unchanged)
manifest_after=perf.source_manifest(source,{"commit":args.commit,"backend":"native"})
assert manifest_before==manifest_after
def location(key):
    filename,line,name=key
    return {"file":filename,"line":line,"name":name}
stats=pstats.Stats(profiler)
functions=[]
for key,(primitive,calls,self_s,cumulative_s,callers) in stats.stats.items():
    functions.append({**location(key),"primitive_calls":primitive,"calls":calls,"self_s":self_s,"cumulative_s":cumulative_s,
        "callers":[{**location(caller),"statistics":values} for caller,values in callers.items()]})
functions.sort(key=lambda item:(-item["cumulative_s"],item["file"],item["line"],item["name"]))
report={"schema":1,"purpose":"cProfile hotspot diagnosis only, never a formal performance comparison",
 "cohort":args.cohort,"dataset_sha256":data.fingerprint,"sessions_per_batch":len(data.sessions),"unchanged_batches":10,"ingest_calls":10*len(data.sessions),
 "python":sys.version,"platform":platform.platform(),"hash_seed":os.environ.get("PYTHONHASHSEED"),
 "backend":BACKEND_NAME,"source_manifest_before":manifest_before,"source_manifest_after":manifest_after,
 "source_and_binary_unchanged":True,"fresh_returns_sha256":perf.digest(fresh),"unchanged_returns_sha256":perf.digest(unchanged),
 "profiler_total_self_s":stats.total_tt,"total_profile_calls":stats.total_calls,"primitive_profile_calls":stats.prim_calls,
 "functions":functions}
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
with output.open("x") as stream:json.dump(report,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write("\n")
wanted=[item for item in functions if "_native_segmentation_ready" in item["name"] or
        (item["file"].endswith("segmentation.py") and item["name"]=="<genexpr>")]
print(json.dumps({"commit":args.commit,"output":str(output),"profile_total":stats.total_tt,
 "package_top_cumulative":[{k:v for k,v in x.items() if k!="callers"} for x in functions if "/memory_book/" in x["file"]][:16],
 "guards":wanted,"bytes":output.stat().st_size,
 "sha256":hashlib.sha256(output.read_bytes()).hexdigest()},ensure_ascii=False))
