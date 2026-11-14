"""Single development diagnostic: fixed SQLite page-cache sizes, full recall.
No product source is modified. Never use these results as formal acceptance.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.run import engine_source_hash
from benchmarks.token_compare import load_dataset, latency_summary
from scripts.benchmark_default_recall import dump, digest, rss
BASELINE = ROOT.parent/'baseline-v0.3.2/src'
RUNTIME = '179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93'
CONFIGS = [{'id':'char4000','budget_chars':4000},
           {'id':'token1024','budget_chars':8000,'budget_tokens':1024,'tokenizer':'cl100k_base'}]
CACHES = [('default', None), ('4MiB', -4096), ('8MiB', -8192)]
ORDER = [['default','4MiB','8MiB'], ['8MiB','4MiB','default'],
         ['8MiB','4MiB','default'], ['default','4MiB','8MiB']]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    with Path(path).open('xb') as stream:
        stream.write((dump(value)+'\n').encode())
        stream.flush()
        os.fsync(stream.fileno())

def worker(directory, key):
    plan = json.loads((directory/'plan.json').read_bytes())
    item = next(i for i in plan['schedule'] if i['key'] == key)
    assert sha(__file__) == plan['script_sha256']
    assert engine_source_hash(BASELINE/'memory_book') == RUNTIME
    sys.path.insert(0, str(BASELINE))
    from memory_book import MemoryBook
    import memory_book
    import tiktoken
    assert Path(memory_book.__file__).resolve().parent == (BASELINE/'memory_book').resolve()
    encoding = tiktoken.get_encoding('cl100k_base')
    encoding.encode_ordinary('Initialize outside timing.')
    source = Path(plan['cohorts'][item['cohort']]['database_path'])
    assert sha(source) == plan['cohorts'][item['cohort']]['database_sha256']
    record = {**item, 'source_sha256': RUNTIME, 'rss_before_open': rss(),
              'configurations': [], 'status':'started', 'sqlite':sqlite3.sqlite_version}
    with tempfile.TemporaryDirectory(prefix='sqlite-cache-probe-', dir=directory) as temporary:
        dbpath = Path(temporary)/'memory.db'
        shutil.copyfile(source, dbpath)
        begin = time.perf_counter_ns()
        with MemoryBook(dbpath, cache_size=0) as book:
            record['open_ms'] = (time.perf_counter_ns()-begin)/1e6
            record['default_cache_size'] = book.db.execute('PRAGMA cache_size').fetchone()[0]
            assert record['default_cache_size'] == -2000
            if item['cache_size'] is not None:
                book.db.execute(f"PRAGMA cache_size={int(item['cache_size'])}")
            book.db.execute('PRAGMA query_only=ON')
            record['actual_cache_size'] = book.db.execute('PRAGMA cache_size').fetchone()[0]
            record['page_size'] = book.db.execute('PRAGMA page_size').fetchone()[0]
            record['page_count'] = book.db.execute('PRAGMA page_count').fetchone()[0]
            record['rss_after_open'] = rss()
            cases = plan['cohorts'][item['cohort']]['queries']
            for index, config in enumerate(CONFIGS):
                order = list(cases)
                random.Random(51061+1009*item['round']+index).shuffle(order)
                rows=[]
                for case in order:
                    options = {k:v for k,v in config.items() if k!='id'}
                    begin = time.perf_counter_ns()
                    response = book.recall(case['query'], project=case['project'], limit=5,
                                           use_cache=False, **options)
                    elapsed = (time.perf_counter_ns()-begin)/1e6
                    response.pop('latency_ms')
                    assert response['cache_hit'] is False
                    assert len(response['context'])<=config['budget_chars']
                    if 'budget_tokens' in config:
                        count=len(encoding.encode_ordinary(response['context']))
                        assert count==response['context_tokens'] and count<=config['budget_tokens']
                    rows.append({'query_id':case['id'], 'wall_ms':elapsed,
                                 'payload_sha256':digest(response),
                                 'context_chars':len(response['context']),
                                 'result_count':len(response['results'])})
                record['configurations'].append({**config,'rows':rows,
                    'latency':latency_summary([r['wall_ms'] for r in rows]),'rss_after_calls':rss()})
            assert book.db.execute('SELECT count(*) FROM recall_cache').fetchone()[0] == 0
    record['status']='completed'
    record['source_sha256_after']=engine_source_hash(BASELINE/'memory_book')
    assert record['source_sha256_after']==RUNTIME
    data=(dump(record)+'\n').encode()
    with (directory/(key+'.json.gz')).open('xb') as stream:
        stream.write(gzip.compress(data,mtime=0))
    print(dump({'worker':key,'calls':sum(len(c['rows']) for c in record['configurations'])}),flush=True)

def main(directory):
    directory.mkdir(parents=True,exist_ok=False)
    assert engine_source_hash(BASELINE/'memory_book')==RUNTIME
    cohorts={}
    for name in ('synthetic61','public1015'):
        data=(load_dataset('synthetic',61,'development',8,None,0) if name=='synthetic61' else
              load_dataset('locomo',61,'heldout',8,str(ROOT/'.artifacts/locomo10.json'),0))
        path=ROOT/'.artifacts/round5-development-dbs'/f'{name}.db'
        assert Path(str(path)+'-wal').stat().st_size==0
        cases=[{'id':c.id,'query':c.query,'project':c.project} for c in data.queries[:128]]
        cohorts[name]={'dataset_sha256':data.fingerprint,'database_path':str(path),
            'database_sha256':sha(path),'database_bytes':path.stat().st_size,
            'selection':'first 128 of unchanged deterministic dataset query order',
            'queries':cases}
    schedule=[{'key':f'r{r}-{cohort}-{label}','round':r,'cohort':cohort,'label':label,
               'cache_size':dict(CACHES)[label]}
              for r,order in enumerate(ORDER) for cohort in cohorts for label in order]
    plan={'kind':'development-only','created_at':datetime.now(timezone.utc).isoformat(),
        'baseline_commit':'692fb959ddf8934c5f516ba3d74ceb4385a2fa82','runtime_sha256':RUNTIME,
        'script_sha256':sha(__file__),'python':platform.python_version(),
        'sqlite':sqlite3.sqlite_version,'cohorts':cohorts,'configs':CONFIGS,'schedule':schedule,
        'calls':6144,'rounds':4,'order':ORDER,
        'boundaries':'Full uncached native recall including source assembly; only timing excluded from full payload hash. Original DBs untouched; fresh writable copy opened then query_only=ON. Fresh process each worker, warm OS file cache from copying. No MCP or ingestion measurement.',
        'decision':'Development diagnostic only. Preserve every sample and adverse cell. Do not rerun to seek favorable speed; consider implementation only on broad stable gains with acceptable memory costs. Formal ABBA gates still required for release.'}
    write(directory/'plan.json',plan)
    records=[]
    for item in schedule:
        write(directory/(item['key']+'.started.json'),item)
        subprocess.run([sys.executable,str(Path(__file__).resolve()),str(directory),'--worker',item['key']],
                       check=True,env={**os.environ,'PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1'})
        records.append(json.loads(gzip.decompress((directory/(item['key']+'.json.gz')).read_bytes())))
    canonical={}; mismatches=[]; comparisons=[]
    for record in records:
        for config in record['configurations']:
            for row in config['rows']:
                key=(record['cohort'],config['id'],row['query_id'])
                if key in canonical and canonical[key]!=row['payload_sha256']:
                    mismatches.append({'worker':record['key'],'config':config['id'],'query_id':row['query_id']})
                canonical.setdefault(key,row['payload_sha256'])
    for cohort in cohorts:
        for config in CONFIGS:
            bylabel={}
            for label,_ in CACHES:
                selected=[r for r in records if r['cohort']==cohort and r['label']==label]
                items=[next(c for c in r['configurations'] if c['id']==config['id']) for r in selected]
                bylabel[label]={'latency':latency_summary([row['wall_ms'] for c in items for row in c['rows']]),
                    'rounds':[{'round':r['round'],'latency':c['latency'],'rss':c['rss_after_calls']} for r,c in zip(selected,items)],
                    'rss_bytes_mean':statistics.fmean(c['rss_after_calls']['rss_bytes'] for c in items)}
            for label in ('4MiB','8MiB'):
                old,new=bylabel['default'],bylabel[label]
                comparisons.append({'cohort':cohort,'config':config['id'],'cache':label,
                    'baseline':old,'candidate':new,
                    'change_percent':{key:100*(new['latency'][key]/old['latency'][key]-1) for key in ('p50_ms','p95_ms','mean_ms')},
                    'rss_delta_bytes':new['rss_bytes_mean']-old['rss_bytes_mean']})
    summary={'kind':'development-only','plan_sha256':sha(directory/'plan.json'),
        'calls':sum(len(c['rows']) for r in records for c in r['configurations']),
        'distinct_query_config_pairs':len(canonical),'payload_mismatches':mismatches,
        'comparisons':comparisons,'database_inputs_unchanged':all(sha(c['database_path'])==c['database_sha256'] for c in cohorts.values()),
        'raw_files_sha256':{p.name:sha(p) for p in sorted(directory.glob('*.json.gz'))}}
    write(directory/'summary.json',summary)
    print(dump({'summary':str(directory/'summary.json'),'calls':summary['calls'],
        'mismatches':len(mismatches),'comparisons':[{k:v for k,v in c.items() if k not in ('baseline','candidate')} for c in comparisons]}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--worker')
    args=parser.parse_args()
    worker(args.directory,args.worker) if args.worker else main(args.directory.resolve())
