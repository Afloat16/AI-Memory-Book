import json,hashlib
from pathlib import Path
import memory_book
from memory_book import MemoryBook
cases=[
('assignment_seconds','current timeout','timeout=30 seconds. '+'timeout. '*12,'timeout=5 seconds.'),
('prose_retries','current retry limit','The retry limit is 3 retries. '+'retry limit. '*12,'The retry limit is now 7 retries.'),
('prose_reason','current worker prefetch window','Worker prefetch window is 12. '+'worker prefetch window. '*12,'Worker prefetch window is now 3 because memory usage was too high.'),
('explicit_scope_assignment_units','current production lease_duration','Production lease_duration=30 seconds. '+'production lease_duration. '*12,'Production lease_duration=12 seconds.'),
]
rows=[]
for name,query,old,new in cases:
 with MemoryBook(':memory:',cache_size=0) as b:
  sources=[]
  for sid,body,date in [('old',old,'2026-01-01T00:00:00Z'),('new',new,'2026-10-01T00:00:00Z')]:
   source={'project':'p','task_id':'same','task_title':'Worker settings','session_id':sid,'title':'Worker settings','created_at':date,'messages':[{'role':'assistant','content':body}]}
   sources.append(source);b.ingest(source)
  req={'query':query,'project':'p','limit':1,'budget_chars':1200,'use_cache':False}
  r=b.recall(**req)
  rows.append({'case':name,'sources':sources,'request':req,'response':r,'pages':[b.read(x['id']) for x in r['results']]})
for name,new,query in [('scoped_revocation','Staging rollout still needs review. The old value is invalid. Production is otherwise unchanged.','current production lease_duration'),('unscoped_latest','Staging lease_duration=99.','current lease_duration')]:
 with MemoryBook(':memory:',cache_size=0) as b:
  source={'project':'p','task_id':'same','task_title':'Production configuration','session_id':'conversation','title':'Production configuration','messages':[{'role':'user','content':'Production lease_duration?'},{'role':'assistant','content':'Production lease_duration=30. '+'production lease_duration. '*8},{'role':'user','content':'Production lease_duration follow-up?'},{'role':'assistant','content':new}]}
  b.ingest(source)
  for budget in (250,300):
   req={'query':query,'project':'p','limit':1,'budget_chars':budget,'use_cache':False}
   r=b.recall(**req)
   rows.append({'case':name,'sources':[source],'request':req,'response':r,'pages':[b.read(x['id']) for x in r['results']]})
print(json.dumps({'package':memory_book.__file__,'store_sha256':hashlib.sha256(Path(memory_book.__file__).with_name('store.py').read_bytes()).hexdigest(),'rows':rows},ensure_ascii=False))
