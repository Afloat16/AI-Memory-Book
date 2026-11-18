"""Small adversarial source-scope review; no benchmark gold or production edit."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.source.resolve()
    args.output.mkdir(exist_ok=False,parents=True)
    sys.path.insert(0,str(root/'src'))
    import memory_book
    from memory_book import MemoryBook
    from memory_book._text_backend import BACKEND_NAME
    def identity():
        git=lambda *a: subprocess.check_output(['git','-C',str(root),*a])
        head=git('rev-parse','HEAD').decode().strip()
        names=git('ls-tree','-r','--name-only',head,'src/memory_book').decode().splitlines()
        actual={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
        expected={n:hashlib.sha256(git('show',head+':'+n)).hexdigest() for n in names}
        if actual!=expected: raise ValueError('Runtime differs from Git HEAD')
        return {'commit':head,'files':actual,'package':str(Path(memory_book.__file__).resolve()),'backend':BACKEND_NAME}
    before=identity()
    variants={
      'suffix_other_scope':'Production retry_limit=99，旧值已撤销，此值仅用于 staging。',
      'suffix_pending':'Production retry_limit=99，旧值已撤销，pending staging approval。',
      'safe_causal_control':'Production retry_limit=7，旧值已因延迟测试失败而弃用。',
    }
    rows=[]
    for name,body in variants.items():
        for count in [2,8,104]:
            sources=[]
            for i in range(count):
                sources.append({'project':'workers','session_id':f'decision-{i}','task_id':'shared-task',
                    'task_title':'Worker configuration','title':'Worker configuration','created_at':'2026-01-01T00:00:00Z',
                    'messages':[{'role':'assistant','content':'Production retry_limit=3. '+'production retry_limit. '*12}]})
            sources.append({'project':'workers','session_id':'latest','task_id':'shared-task',
                    'task_title':'Worker configuration','title':'Worker configuration','created_at':'2026-10-01T00:00:00Z',
                    'messages':[{'role':'assistant','content':body}]})
            with MemoryBook(':memory:',segmentation='turn',cache_size=0) as book:
                for s in sources: book.ingest(s)
                for mode in ['relevance','current']:
                    response=book.recall('current production retry_limit',project='workers',temporal=mode,
                                         limit=1,budget_chars=1200,use_cache=False)
                    pages={h['id']:book.read(h['id'],project='workers',limit=100000) for h in response['results']}
                    first=response['results'][0]['source_refs'][0]['session_id'] if response['results'] else None
                    rows.append({'variant':name,'count':count,'mode':mode,'sources':sources,
                                 'response':response,'original_pages':pages,'first_session':first})
    after=identity()
    if before!=after: raise ValueError('Runtime changed during probe')
    with (args.output/'raw.json').open('x') as f: json.dump(rows,f,ensure_ascii=False,indent=2)
    report={'status':'completed','before':before,'after':after,
            'summary':[{k:r[k] for k in ['variant','count','mode','first_session']} for r in rows],
            'scope':'Authored adversarial development diagnostic; no general accuracy or speed claim.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__': main()
