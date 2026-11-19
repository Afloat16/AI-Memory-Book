from __future__ import annotations
import ast,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from memory_book import MemoryBook, store
root=Path('/workspace/scratch/538d317f6ebd/ai-memory-book')
path=root/'benchmarks/reports/v0.13-development/independent-assessment-review/probe.py'
namespace={}
tree=ast.parse(path.read_text())
chosen=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('record','fixtures')]
exec(compile(ast.Module(body=chosen,type_ignores=[]),str(path),'exec'),namespace)
cases=[case for case in namespace['fixtures']() if case['id'] in ('final_output_dimension_identifier','qualified_current_identifier')]
records=[]
for case in cases:
 for ranking_scope in ('global','project'):
  with MemoryBook(':memory:',cache_size=0,segmentation='turn',ranking_scope=ranking_scope) as book:
   ingests=[book.ingest(s) for s in case['sources']]
   result=book.recall(**case['requests'][0])
   field='最终输出维度' if case['id']=='final_output_dimension_identifier' else 'current.phase_size'
   records.append({'case':case['id'],'mode':ranking_scope,'source_inputs':case['sources'],'request':case['requests'][0],'ingests':ingests,'first_session':result['results'][0]['source_refs'][0]['session_id'],'expected_first_session':'revised','response':result,'diagnostic':{'field':field,'query_terms':store.query_terms(case['requests'][0]['query']),'declaration_query_terms':sorted(store._declaration_query_terms(case['requests'][0]['query'])),'field_aliases':store.query_terms(field),'field_lexical_terms':store.lexical_terms(field),'field_identity':store._field_identity(field),'field_discovery_lexical_guard':set(store.lexical_terms(field))<=set(store.query_terms(field)),'prose_bindings_by_source':[[m.groupdict() for m in store._PROSE_BINDING.finditer(s['messages'][0]['content'])] for s in case['sources']]}})
report={'kind':'reproduction_of_two_existing_v013_failures','created_at':datetime.now(timezone.utc).isoformat(),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'src/memory_book/store.py',path]},'records':records,'all_original_failures_persist':all(r['first_session']=='initial' for r in records),'qualification':'Original v013 cases, both old baseline and candidate originally failed; not a new regression or untouched holdout.'}
out=Path('/workspace/scratch/538d317f6ebd/legacy-identifier-reproduction.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'path':str(out),'source_commit':report['source_commit'],'cases':[{'case':r['case'],'mode':r['mode'],'first_session':r['first_session'],'diagnostic':r['diagnostic']} for r in records]},ensure_ascii=False,indent=2))
