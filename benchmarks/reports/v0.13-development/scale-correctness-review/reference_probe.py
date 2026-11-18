"""Independent adversarial review: extra quoted/conditional prose references."""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--source',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
root=a.runtime.resolve();sys.path.insert(0,str(root/'src'))
from memory_book import MemoryBook
from memory_book._text_backend import BACKEND_NAME
assert BACKEND_NAME=='python'
sha=lambda x:hashlib.sha256(x).hexdigest()
source_files={str(f.relative_to(root)):sha(f.read_bytes()) for f in sorted((root/'src/memory_book').glob('*.py'))}
assert all(sha(subprocess.check_output(['git','show',a.source+':'+name],cwd=root))==value for name,value in source_files.items())
variants=['Example: "Production access_limit is 99."','If approved, Production access_limit is 99.']
rows=[]
for extra in variants:
 def record(sid,text,newer=False):
  return {'project':'engine','task_id':'configuration','session_id':sid,'created_at':'2026-06-01T00:00:00Z' if newer else '2026-01-01T00:00:00Z','messages':[{'role':'assistant','content':text}]}
 sources=[record('old','Production access_limit=30. '+'production access_limit record. '*16),record('uncertain','Production access_limit=12. Production access_limit=12. '+extra,True)]
 request={'query':'current production access_limit','project':'engine','limit':1,'use_cache':False}
 with MemoryBook(':memory:',segmentation='turn') as book:
  [book.ingest(s) for s in sources];response=book.recall(**request)
 first=response['results'][0]['source_refs'][0]['session_id']
 row={'sources':sources,'request':request,'response':response,'expected_first':'old','first':first,'passed':first=='old'};rows.append(row)
 with (a.output/'raw.jsonl').open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
receipt={'source':a.source,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'runtime_files':source_files,'backend':BACKEND_NAME,'responses':2,'passed':sum(r['passed'] for r in rows),'raw_sha256':sha((a.output/'raw.jsonl').read_bytes()),'probe_sha256':sha(Path(__file__).read_bytes())}
(a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='runtime_files'}))
