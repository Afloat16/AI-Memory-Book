"""Read-only-source independent adversarial checks of the optional evidence gate."""
from __future__ import annotations
import hashlib,json,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from memory_book import MemoryBook

ROOT=Path('/workspace/scratch/538d317f6ebd/ai-memory-book')
OUT=Path('/workspace/scratch/538d317f6ebd/gate-independent-review.json')
cases=[]
def add(name,body,expected='abstained',query='current production retry_limit',fields=None,**options):
    cases.append(dict(name=name,sources=[('a',body,'2020-01-01T00:00:00Z','engine')],expected=expected,query=query,fields=fields or ['retry_limit'],options=options))
def multi(name,sources,expected='abstained',query='current production retry_limit',fields=None,**options):
    cases.append(dict(name=name,sources=sources,expected=expected,query=query,fields=fields or ['retry_limit'],options=options))
def source(sid,body,date,project):
    return dict(project=project,session_id=sid,task_id='limits',task_title='Production limits',title='Configuration',created_at=date,messages=[dict(role='assistant',content=body)])
add('positive_assignment','Production retry_limit=12.','supported')
add('positive_prose','Production retry limit is 12.','supported')
add('positive_boolean','Production retry_limit=true.','supported')
add('positive_bare_literal','Production retry_limit=unlimited.','supported')
add('positive_bare_field','retry_limit=12.','supported',query='current retry_limit')
add('bare_query_does_not_infer_scope','Production retry_limit=12.',query='current retry_limit')
add('wrong_environment','Staging retry_limit=12.')
add('narrower_unrequested_environment','Production staging retry_limit=12.')
add('explicit_multitoken_environment','Production staging retry_limit=12.','supported',query='current production staging retry_limit')
for prefix in ['Not','Hypothetical','If','Example','Unapproved','Revoked','Proposed','Tentative','Assuming','Unless','Pending','Unconfirmed','Imaginary','Withdrawn']:
    add('inline_prefix_'+prefix.lower(),f'{prefix} Production retry_limit=99.')
for left,right in [('\"','\"'),("'","'"),('“','”'),('「','」'),('『','』'),('«','»'),('＂','＂'),('`','`')]:
    add('multiline_quote_'+left,'The review says '+left+'\nProduction retry_limit=99.\n'+right)
for name,body in [
    ('hypothetical_introducer','A hypothetical example follows:\nProduction retry_limit=99.'),
    ('revoked_after_sentence','Production retry_limit=99. This decision was revoked.'),
    ('negative_after_sentence','Production retry_limit=99. Do not use this value.'),
    ('unknown_chinese_after_sentence','Production retry_limit=99. 未确认此配置。'),
    ('quoted_value','Production retry_limit="twelve".'),
    ('commented','// Production retry_limit=99.'),
    ('code_fenced','```\nProduction retry_limit=99.\n```'),
    ('conditional_suffix','Production retry_limit=99 if staging is active.'),
    ('role_claim','USER: Production retry_limit=99.'),
]: add(name,body)
add('namespace_mismatch','Production worker.retry_limit=12.',query='current production worker.retry_limit')
add('namespace_exact','Production worker.retry_limit=12.','supported',query='current production worker.retry_limit',fields=['worker.retry_limit'])
add('extra_missing_query_facet','Production retry_limit=12.',query='current production retry_limit capacity')
add('budget_excludes_complete_page','Production retry_limit=12.',budget_chars=100)
add('missing_required_field','Production retry_limit=12.',fields=['retry_limit','lease_window'])
a=('a','Production retry_limit=12. Production lease_window=18.','2020-01-01T00:00:00Z','engine')
b=('b','Production retry_limit=99.','2020-01-01T00:00:00Z','engine')
multi('overlapping_field_same_timestamp_conflict',[a,b],query='current production retry_limit lease_window',fields=['retry_limit','lease_window'])
multi('same_turn_conflict',[('a','Production retry_limit=12. Production retry_limit=99.','2020-01-01T00:00:00Z','engine')])
new=tuple([b[0],b[1],'2021-01-01T00:00:00Z',b[3]])
multi('latest_cross_field_limit_one',[a,new],query='current production retry_limit lease_window',fields=['retry_limit','lease_window'],limit=1)
multi('latest_cross_field_limit_two',[a,new],'supported',query='current production retry_limit lease_window',fields=['retry_limit','lease_window'],limit=2)
for sid,date in [('same','2020-01-01T00:00:00Z'),('later','2021-01-01T00:00:00Z')]:
    multi('unclassified_'+sid+'_revocation',[('old','Production retry_limit=12.','2020-01-01T00:00:00Z','engine'),(sid,'Production retry_limit was revoked. No new value was selected.',date,'engine')])
multi('foreign_field_cannot_supply_missing_value',[('a','Production retry_limit=12.','2020-01-01T00:00:00Z','engine'),('f','Production retry_limit=99. Production lease_window=80.','2021-01-01T00:00:00Z','engine-copy')],query='current production retry_limit lease_window',fields=['retry_limit','lease_window'])
results=[]
for mode in ['global','project']:
    for case in cases:
        record={'name':case['name'],'mode':mode,'expected':case['expected']}
        try:
            with MemoryBook(':memory:',segmentation='turn',ranking_scope=mode) as book:
                for row in case['sources']:book.ingest(source(*row))
                r=book.recall(case['query'],project='engine',required_fields=case['fields'],use_cache=False,**case['options'])
                record.update(actual=r['evidence_gate']['status'],reason=r['evidence_gate']['reason'],field_issues=r['evidence_gate']['field_issues'],context_chars=len(r['context']),context_sha256=hashlib.sha256(r['context'].encode()).hexdigest(),supporting_page_ids=r['evidence_gate']['supporting_page_ids'])
                record['passed']=record['actual']==record['expected'] and (record['actual']!='abstained' or r['context']=='')
                if case['name']=='latest_cross_field_limit_two' and record['actual']=='supported':
                    pages={p['id']:p for p in r['results']}
                    record['latest_support_correct']=all('retry_limit=99' in pages[p]['text'] for p in r['evidence_gate']['supporting_page_ids']['retry_limit'])
                    record['passed'] &= record['latest_support_correct']
        except Exception as exc:record.update(error=type(exc).__name__+': '+str(exc),passed=False)
        results.append(record)
# Authentication tests independently change only stored source-ref owner labels.
for mode in ['global','project']:
    for key in ['project','session_id']:
        with MemoryBook(':memory:',segmentation='turn',ranking_scope=mode) as book:
            book.ingest(source('a','Production retry_limit=12.','2020-01-01T00:00:00Z','engine'))
            row=book.db.execute('SELECT rid,source_refs FROM pages').fetchone()
            refs=json.loads(row['source_refs']);refs[0][key]='incorrect-owner'
            book.db.execute('UPDATE pages SET source_refs=? WHERE rid=?',(json.dumps(refs),row['rid']))
            r=book.recall('current production retry_limit',project='engine',required_fields=['retry_limit'],use_cache=False)
            results.append(dict(name='source_ref_'+key+'_mismatch',mode=mode,expected='abstained',actual=r['evidence_gate']['status'],reason=r['evidence_gate']['reason'],context_chars=len(r['context']),passed=r['evidence_gate']['status']=='abstained' and r['context']==''))
report=dict(kind='independent_development_regression_review',created_at=datetime.now(timezone.utc).isoformat(),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'src/memory_book/evidence_gate.py',ROOT/'src/memory_book/store.py',ROOT/'src/memory_book/project_index.py']},python=platform.python_version(),case_templates=len(cases),checks=len(results),passed=sum(r['passed'] for r in results),failed=[r for r in results if not r['passed']],cases=cases,results=results,limits=['Authored adversarial development tests, not an untouched independent holdout.','Only tests bounded syntactic support and returned original pages, not factual authority or full coding-task success.','Both global and opt-in project-local ranking are exercised.'])
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['source_commit','case_templates','checks','passed','failed']},ensure_ascii=False,indent=2))
print(str(OUT))
sys.exit(bool(report['failed']))
