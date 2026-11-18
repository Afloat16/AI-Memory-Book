"""Independent inspected development counterexamples, not frozen benchmark gold."""
from __future__ import annotations
import argparse, asyncio, hashlib, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path


def record(sid, text, *, project='workers', date='2026-01-01T00:00:00Z'):
    return {'project':project,'session_id':sid,'task_id':'configuration','task_title':'Configuration',
            'title':'Configuration','created_at':date,'messages':[{'role':'assistant','content':text}]}


def fixtures():
    return [
        {'id':'destination_port_identifier','purpose':'The character 的 is part of the parameter name 目的端口, not possessive grammar.',
         'sources':[record('initial','目的端口为 80。'+'目的端口记录。'*12),record('revised','目的端口为 443。',date='2026-06-01T00:00:00Z')],
         'requests':[{'query':'当前目的端口','project':'workers','limit':1}]},
        {'id':'final_output_dimension_identifier','purpose':'最终 is part of the named output field, in addition to the leading current cue.',
         'sources':[record('initial','最终输出维度为 768。'+'最终输出维度记录。'*12),record('revised','最终输出维度为 1024。',date='2026-06-01T00:00:00Z')],
         'requests':[{'query':'当前最终输出维度','project':'workers','limit':1}]},
        {'id':'qualified_current_identifier','purpose':'The English current segment belongs to the dotted parameter identifier and must survive Chinese-question normalization.',
         'sources':[record('initial','current.phase_size is 30. '+'current.phase_size record. '*12),record('revised','current.phase_size is 12.',date='2026-06-01T00:00:00Z')],
         'requests':[{'query':'当前 current.phase_size','project':'workers','limit':1}]},
        {'id':'irrelevant_field_conflict','purpose':'Queried wait_limit is unchanged; an additional connection_limit differs at the same timestamp.',
         'sources':[record('a','Production wait_limit=12. Production connection_limit=30.'),record('b','Production wait_limit=12. Production connection_limit=99.')],
         'requests':[{'query':'current production wait_limit','project':'workers','limit':5}]},
        {'id':'revoked_old_configuration','purpose':'The later same-field agenda explicitly revokes the previous value and records no replacement.',
         'sources':[record('previous','Production wait_limit=12.'),record('revoked','Production wait_limit remains on the review agenda. The previous value was revoked. No new value was selected. '+'production wait_limit review. '*12,date='2026-06-01T00:00:00Z')],
         'requests':[{'query':'current production wait_limit','project':'workers','limit':1}]},
        {'id':'cross_project_no_conflict','purpose':'Equal timestamps and same task names in distinct project books must not form one conflict.',
         'sources':[record('a','Production wait_limit=12.',project='project-a'),record('a','Production wait_limit=99.',project='project-b')],
         'requests':[{'query':'current production wait_limit','limit':5}]},
        {'id':'cross_project_conflict_addresses','purpose':'Each project has its own conflict; inspect requested-project and unscoped compact address behavior.',
         'sources':[record(sid,f'Production wait_limit={value}.',project=project) for project,values in [('project-a',[12,30]),('project-b',[112,130])] for sid,value in zip(['a','b'],values)],
         'requests':[{'query':'current production wait_limit','project':'project-a','limit':1},{'query':'current production wait_limit','limit':1}],
         'mcp_bound_project':'project-a'},
        {'id':'zero_budget','purpose':'Zero character budget skips retrieval; zero token output budget may still inspect candidates and must describe that distinction.',
         'sources':[record('a','Production wait_limit=12.'),record('b','Production wait_limit=30.')],
         'requests':[{'query':'current production wait_limit','project':'workers','budget_chars':0},
                     {'query':'current production wait_limit','project':'workers','budget_tokens':0}]},
        {'id':'partial_nondecision','purpose':'An incomplete source fragment must not acquire complete-source nondecision priority.',
         'book_options':{'segmentation':'adaptive','max_page_chars':300,'min_page_chars':0},
         'sources':[record('decision','Production wait_limit=12.'),record('partial','Production wait_limit remains on the review agenda. No value was selected. '+'production wait_limit review. '*80,date='2026-06-01T00:00:00Z')],
         'requests':[{'query':'current production wait_limit','project':'workers','limit':1}]},
    ]


def sha(data):return hashlib.sha256(data).hexdigest()

def run(args):
    root=Path(args.runtime).resolve(); out=Path(args.output).resolve();out.mkdir(exist_ok=False)
    sys.path.insert(0,str(root/'src'))
    from memory_book import MemoryBook
    import memory_book.store as runtime
    from memory_book._text_backend import BACKEND_NAME
    assert BACKEND_NAME=='python'
    mcp_path=Path(args.mcp_snapshot).resolve()
    spec=importlib.util.spec_from_file_location('memory_book._independent_mcp',mcp_path)
    mcp=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mcp;spec.loader.exec_module(mcp)
    source_files={str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted((root/'src/memory_book').glob('*.py'))}
    raw=[]
    def save(item):
        raw.append(item)
        with (out/'raw.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(item,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
    cases=fixtures();raw_inputs=json.dumps(cases,ensure_ascii=False,sort_keys=True).encode();(out/'inputs.json').write_bytes(raw_inputs)
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='assessment-case-',dir=out) as temp:
            path=Path(temp)/'memory.sqlite'
            with MemoryBook(path,cache_size=0,**{'segmentation':'turn',**case.get('book_options',{})}) as book:
                ingestions=[book.ingest(value) for value in case['sources']]
                for request in case['requests']:
                    try:
                        response=book.recall(**request,use_cache=False)
                        compact=mcp.recall_payload(response)
                        identities={row['id']:{'project':row['project_id'],'chapter':row['chapter_id'],'session':row['external_id']}
                                    for row in book.db.execute('SELECT p.id,p.project_id,p.chapter_id,s.external_id FROM pages p JOIN sessions s ON s.id=p.session_pk')}
                        item={'case':case['id'],'request':request,'ingestions':ingestions,'response':response,'compact':compact,'page_identities':identities,
                              'declaration_query_terms':sorted(runtime._declaration_query_terms(request['query'])) if hasattr(runtime,'_declaration_query_terms') else None}
                    except Exception as exc:
                        item={'case':case['id'],'request':request,'ingestions':ingestions,'error':{'type':type(exc).__name__,'message':str(exc)}}
                    save(item)
            if case.get('mcp_bound_project'):
                async def mcp_call():
                    server=mcp.create_server(path,project=case['mcp_bound_project'])
                    results=[]
                    for request in ({'query':'current production wait_limit','limit':1}, {'query':'current production wait_limit','project':'project-b','limit':1}):
                        try:
                            blocks=await server.call_tool('recall_memory',request)
                            results.append({'request':request,'raw_blocks':[block.model_dump(mode='json') for block in blocks]})
                        except Exception as exc:
                            results.append({'request':request,'error':{'type':type(exc).__name__,'message':str(exc)}})
                    return results
                save({'case':case['id'],'surface':'bound-MCP-SDK-call_tool','bound_project':case['mcp_bound_project'],'calls':asyncio.run(mcp_call())})
    (out/'raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    for relative,digest in source_files.items():assert sha((root/relative).read_bytes())==digest
    receipt={'scope':'Independent authored and inspected development counterexamples; no frozen workload/gold modifications or scale timing.',
             'runtime_root':str(root),'runtime_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
             'backend':BACKEND_NAME,'runtime_files_sha256':source_files,'mcp_snapshot_sha256':sha(mcp_path.read_bytes()),
             'probe_sha256':sha(Path(__file__).read_bytes()),'inputs_sha256':sha(raw_inputs),'raw_sha256':sha((out/'raw.json').read_bytes()),'responses':len(raw)}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    for item in raw:
        if 'response' not in item: print(json.dumps({'case':item['case'],'surface':item.get('surface'),'error':item.get('error')},ensure_ascii=False));continue
        response=item['response'];assessment=response.get('temporal',{}).get('evidence_assessment')
        print(json.dumps({'case':item['case'],'request':item['request'],'first':response['results'][0]['source_refs'][0]['session_id'] if response['results'] else None,
                          'projects':[hit['source_refs'][0]['project'] for hit in response['results']],
                          'status':assessment['status'] if assessment else None,'conflicts':assessment['conflicts'] if assessment else None,
                          'nondecision_priority':response.get('temporal',{}).get('nondecision_priority'),'query_terms':item['declaration_query_terms']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True);parser.add_argument('--output',required=True);parser.add_argument('--mcp-snapshot',required=True)
    run(parser.parse_args())
