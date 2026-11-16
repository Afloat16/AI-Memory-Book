"""Local native-v-native diagnostic; not release performance evidence.

Both backends use the same in-memory SQLite workload and deterministic clock.
The released baseline is a git-show source snapshot prepared by the root agent.
No packages are installed, no source is edited, and the database lives in RAM.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = Path(__file__).with_name('local-native-paired.json')
BASELINE = ROOT / '.artifacts/native-incremental-baseline'
ORDER = [('baseline', 'candidate'), ('candidate', 'baseline'),
         ('candidate', 'baseline'), ('baseline', 'candidate')]
WORKER = r'''
import hashlib,json,platform,random,sqlite3,time
from pathlib import Path
from benchmarks.data import generate_dataset
from memory_book import MemoryBook,store,text
from memory_book._text_backend import BACKEND_NAME,NATIVE
assert BACKEND_NAME == 'native'
store._now=lambda:'2026-04-01T00:00:00Z'
def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
dataset=generate_dataset(seed=61,split='development',projects=8)
book=MemoryBook(':memory:',cache_size=0)
def timed(fn):
 wall=time.perf_counter_ns();cpu=time.process_time_ns();result=fn()
 return result,{'wall_ms':(time.perf_counter_ns()-wall)/1e6,'cpu_ms':(time.process_time_ns()-cpu)/1e6}
ingested,fresh=timed(lambda:[book.ingest(session) for session in dataset.sessions])
unchanged,repeat=timed(lambda:[book.ingest(session) for session in dataset.sessions])
index_hashes={table:digest([tuple(row) for row in book.db.execute('SELECT rowid,* FROM '+table+' ORDER BY rowid')]) for table in ('projects','chapters','sessions','turns','sections','pages','pages_fts','pages_stem_fts')}
def query(case):
 return book.recall(case.query,project=case.project,budget_chars=2400,limit=5,use_cache=False)
for case in dataset.queries:query(case)
rows=[];payloads={};query_cpu=time.process_time_ns()
for repetition in range(3):
 cases=list(dataset.queries);random.Random(110061+repetition).shuffle(cases)
 for case in cases:
  start=time.perf_counter_ns();payload=query(case);elapsed=(time.perf_counter_ns()-start)/1e6
  payload.pop('latency_ms',None);sha=digest(payload)
  assert payloads.setdefault(case.id,sha)==sha
  rows.append({'repetition':repetition,'query_id':case.id,'elapsed_ms':elapsed})
query_cpu=(time.process_time_ns()-query_cpu)/1e6
result={'backend':BACKEND_NAME,'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'text_path':text.__file__,
        'text_sha256':hashlib.sha256(Path(text.__file__).read_bytes()).hexdigest(),
        'native_sha256':hashlib.sha256(Path(NATIVE.__file__).read_bytes()).hexdigest(),
        'dataset':dataset.description(),'fresh':fresh,'unchanged':repeat,'ingest_sha256':digest(ingested),
        'unchanged_sha256':digest(unchanged),'index_sha256':index_hashes,'payloads':payloads,'query_cpu_ms':query_cpu,'rows':rows}
book.close();print(json.dumps(result,separators=(',',':')))
'''


def percentile(values, fraction):
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def main():
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ROOT / 'src/memory_book/text.py', ROOT / 'src/memory_book/_native.c')}
    result = {'purpose': 'Local diagnostic only; shared host, in-memory SQLite, no MCP or exact-token dependency.',
              'baseline_commit': '6a8a9c6d603a812c75def258b11eb563ed590c9b',
              'orders': ORDER, 'cache_size': 0, 'use_cache': False,
              'budget_chars': 2400, 'source_hashes_before': before, 'workers': []}
    for round_index, order in enumerate(ORDER):
        for engine in order:
            path = BASELINE if engine == 'baseline' else ROOT
            environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(path / 'src'), str(ROOT))),
                               MEMORY_BOOK_TEXT_BACKEND='native', PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0')
            process = subprocess.run([sys.executable, '-c', WORKER], cwd=ROOT, env=environment,
                                     capture_output=True, text=True, timeout=60)
            if process.returncode:
                raise RuntimeError(process.stderr)
            worker = json.loads(process.stdout)
            worker.update(round=round_index, engine=engine)
            result['workers'].append(worker)
            values = [row['elapsed_ms'] for row in worker['rows']]
            print(round_index, engine, 'fresh_ms', round(worker['fresh']['wall_ms'], 3),
                  'p50', round(statistics.median(values), 4), 'p95', round(percentile(values, .95), 4), flush=True)
    first = result['workers'][0]
    keys = ('dataset', 'ingest_sha256', 'unchanged_sha256', 'index_sha256', 'payloads')
    result['all_outputs_identical'] = all(all(worker[key] == first[key] for key in keys)
                                          for worker in result['workers'])
    result['source_hashes_after'] = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in before}
    result['source_unchanged'] = result['source_hashes_before'] == result['source_hashes_after']
    result['summary'] = {}
    for engine in ('baseline', 'candidate'):
        workers = [worker for worker in result['workers'] if worker['engine'] == engine]
        values = [row['elapsed_ms'] for worker in workers for row in worker['rows']]
        result['summary'][engine] = {'queries': len(values), 'p50_ms': statistics.median(values),
                                     'p95_ms': percentile(values, .95),
                                     'fresh_median_ms': statistics.median(worker['fresh']['wall_ms'] for worker in workers),
                                     'unchanged_median_ms': statistics.median(worker['unchanged']['wall_ms'] for worker in workers)}
    DESTINATION.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('all_outputs_identical', 'source_unchanged', 'summary')}, indent=2))
    print(DESTINATION)


if __name__ == '__main__':
    main()
