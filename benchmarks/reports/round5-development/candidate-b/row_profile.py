import cProfile,hashlib,json,pstats,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
import memory_book
from benchmarks.public_data import load_locomo
from benchmarks.run import engine_source_hash
source=Path(memory_book.__file__).resolve().parent
label=sys.argv[1]
root=ROOT/'.artifacts/round5-row-probe'
path=root/(label+'.db')
shutil.copy2(ROOT/'.artifacts/round5-native-development/public1015-0-candidate/book.db',path)
data=load_locomo(ROOT/'.cache/round5/locomo10.json')
queries=sorted(data.queries,key=lambda q:(hashlib.sha256(('round5-row-profile-v1:'+q.id).encode()).digest(),q.id))[:128]
rows=[]
profile=cProfile.Profile()
with memory_book.MemoryBook(path,cache_size=0) as book:
    for query in queries:
        profile.enable()
        value=book.recall(query.query,project=query.project,budget_chars=4000,use_cache=False)
        profile.disable()
        value.pop('latency_ms')
        rows.append({'id':query.id,'payload_sha256':hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
stats=pstats.Stats(profile)
functions=[{'path':p,'line':line,'function':name,'calls':total,'self_seconds':own,'cumulative_seconds':cum} for (p,line,name),(_,total,own,cum,_) in stats.stats.items() if '/memory_book/' in p or p=='~']
result={'scope':'Fixed 128 old public queries; cProfile development diagnostic only, no speed claim','label':label,'source':str(source),'runtime_sha256':engine_source_hash(source),'calls':len(rows),'profile_seconds':stats.total_tt,'rows':rows,'top_self':sorted(functions,key=lambda x:x['self_seconds'],reverse=True)[:30]}
(root/(label+'.profile.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
