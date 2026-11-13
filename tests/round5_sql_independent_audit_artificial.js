"use strict";
/* Invented-only checks. No engine, dataset, I/O, timing, or subprocess. */
module.exports=function testSqlAudit(api,core,scope){
 const cases=[],failures=[];
 function check(name,fn){try{fn();cases.push({name,status:"passed"});}catch(error){cases.push({name,status:"failed",error:String(error)});failures.push(name);}}
 function ok(value,message="assertion failed"){if(!value)throw Error(message);}
 function reject(fn,pattern){let error;try{fn();}catch(e){error=e;}ok(error,"expected rejection");if(pattern)ok(pattern.test(String(error)),"unexpected rejection: "+error);}
 const clone=v=>api.parseExact(api.stringifyExact(v));
 const context={files:{...scope.runtime.files_sha256,[api.PIN.scriptPath]:api.PIN.producer},rules:scope.observer.source_mapping.rules};
 function loc(qualname,line){return {path:"src/memory_book/store.py",source_sha256:scope.runtime.files_sha256["src/memory_book/store.py"],
  function:qualname.split(".").at(-1),qualname,first_line:1n,line,offset:0n};}
 function site(method="Connection.execute",line=739n,qualname="MemoryBook.recall",caller=null){
  const value={site_id:0n,method,location:loc(qualname,line),caller,category:""};
  value.category=api.categoryFor(value,context);return value;
 }
 const sites=[site()];
 function span(sequence,parent,start,end,child=0n,status="returned"){
  return {sequence:BigInt(sequence),parent_sequence:parent===null?null:BigInt(parent),site_id:0n,method:"Connection.execute",
   status,start_ns:start,end_ns:end,inclusive_ns:end-start,child_inclusive_ns:child,exclusive_ns:end-start-child,wrapper_is:false};
 }
 function observed(spans,wall=500n){
  const events={c_call:BigInt(spans.length)};
  for(const span of spans){const key=span.status==="exception"?"c_exception":"c_return";events[key]=(events[key]||0n)+1n;}
  if(!spans.length)delete events.c_call;
  const exclusive=spans.reduce((n,s)=>n+s.exclusive_ns,0n);
  return {valid:true,started:true,finished:true,callback_failure:null,open_sequences:[],spans,
   target_events:{...events},events:{...events,call:2n,return:1n},non_target_events:3n,callback_bookkeeping_ns:7n,
   recall_wall_ns_including_observer:wall,observed_exclusive_builtin_ns:exclusive,unattributed_wall_ns:wall-exclusive};
 }
 const nested=()=>observed([span(0,null,100n,200n,50n),span(1,0,110n,140n,10n),span(2,1,120n,130n,0n,"exception"),
  span(3,0,150n,170n),span(4,null,220n,240n)]);
 check("integer tokens beyond2^53 are exact",()=>{const value=api.parseExact('{"ns":9007199254740993,"counter":123456789012345678901234567890}');
  ok(value.ns===9007199254740993n&&api.stringifyExact(value)==='{"ns":9007199254740993,"counter":123456789012345678901234567890}');});
 check("float exponent and bool remain distinct",()=>{const value=api.parseExact('[1,1.0,1e0,true]');
  ok(typeof value[0]==="bigint"&&typeof value[1]==="number"&&typeof value[2]==="number"&&value[3]===true);});
 check("large floating exponent serializes valid JSON",()=>ok(api.parseExact(api.stringifyExact(1e21))===1e21));
 check("negative floating zero survives serialization",()=>ok(Object.is(api.parseExact(api.stringifyExact(-0)),-0)));
 for(const text of ['{"a":1,"a":2}','[1,]','{"a":1}true','01','1e999','"\\uZZZZ"'])
  check("invalid JSON rejected "+text,()=>reject(()=>api.parseExact(text)));
 check("nested returned and exception spans reconcile",()=>{const value=api.observation(nested(),sites);
  ok(value.spans===5n&&value.exclusive===120n&&value.wall===500n&&value.unattributed===380n&&value.bookkeeping===7n);});
 check("zero targeted calls remains valid observation",()=>ok(api.observation(observed([]),sites).exclusive===0n));
 check("exact large timestamps are retained",()=>{const v=observed([span(0,null,9007199254740993n,9007199254741093n)]);
  ok(api.observation(v,sites).exclusive===100n);});
 check("overlapping roots rejected",()=>reject(()=>api.observation(observed([span(0,null,100n,200n),span(1,null,150n,250n)]),sites),/Overlapping/));
 check("overlapping siblings rejected",()=>reject(()=>api.observation(observed([span(0,null,100n,200n,100n),span(1,0,110n,160n),span(2,0,140n,190n)]),sites),/Overlapping/));
 check("false root nested inside root rejected",()=>reject(()=>api.observation(observed([span(0,null,100n,200n),span(1,null,110n,120n)]),sites),/Overlapping/));
 check("closed same-tick parent cannot reopen",()=>reject(()=>api.observation(observed([span(0,null,100n,100n),span(1,null,100n,100n),span(2,0,100n,100n)]),sites),/reopens/));
 check("shared-tick legal nesting and adjacent roots accepted",()=>ok(api.observation(observed([span(0,null,100n,100n),span(1,0,100n,100n),span(2,null,100n,100n)]),sites).exclusive===0n));
 check("adjacent siblings are accepted",()=>ok(api.observation(observed([span(0,null,100n,200n,50n),span(1,0,100n,125n),span(2,0,125n,150n)]),sites).exclusive===100n));
 check("extent greater than observed wall rejected",()=>reject(()=>api.observation(observed([span(0,null,0n,1n),span(1,null,1000n,1001n)],50n),sites),/extent/));
 const mutations=[
  ["float sequence",v=>v.spans[0].sequence=0],["bool parent",v=>v.spans[1].parent_sequence=false],
  ["float site id",v=>v.spans[0].site_id=0],["float ns",v=>v.spans[0].start_ns=100],
  ["negative ns",v=>v.spans[0].exclusive_ns=-1n],["wrong method",v=>v.spans[0].method="Cursor.fetchall"],
  ["missing site",v=>v.spans[0].site_id=1n],["self-parent",v=>v.spans[1].parent_sequence=1n],
  ["wrong direct-child sum",v=>{v.spans[0].child_inclusive_ns=49n;v.spans[0].exclusive_ns=51n;}],
  ["open native span",v=>v.spans[0].status="open"],["wrapper evidence absent",v=>delete v.spans[0].wrapper_is],
  ["callback failed",v=>v.callback_failure={type:"Error"}],["observer unfinished",v=>v.finished=false],
  ["left open sequence",v=>v.open_sequences=[0n]],["target count mismatch",v=>v.target_events.c_call=4n],
  ["fractional event count",v=>v.events.c_call=5],["negative event count",v=>v.events.call=-1n],
  ["non-target count mismatch",v=>v.non_target_events=2n],["residual mismatch",v=>v.unattributed_wall_ns=379n],
  ["bookkeeping float",v=>v.callback_bookkeeping_ns=7],["bookkeeping negative",v=>v.callback_bookkeeping_ns=-1n],
  ["time order reversal",v=>{v.spans[4].start_ns=0n;v.spans[4].end_ns=20n;}]];
 for(const [name,change] of mutations)check(name+" rejected",()=>{const v=nested();change(v);reject(()=>api.observation(v,sites));});
 check("FTS shared fetch uses frozen upper caller",()=>ok(site("Cursor.fetchall",253n,"_candidate_rows",loc("MemoryBook.recall",810n)).category==="fts_candidates"));
 check("metadata shared fetch has distinct upper caller",()=>ok(site("Cursor.fetchall",257n,"_candidate_rows",loc("MemoryBook.recall",897n)).category==="directory_metadata"));
 check("wrong shared upper caller is unclassified",()=>ok(site("Cursor.fetchall",253n,"_candidate_rows",loc("MemoryBook.recall",999n)).category==="unclassified_primary"));
 check("unknown primary stays separate",()=>{const s=site();s.location.source_sha256=null;ok(api.categoryFor(s,context)==="unclassified_primary");});
 check("other builtin stays separate",()=>ok(site("Cursor.close",739n).category==="other_sqlite_builtin"));
 check("disabled cache remains explicit",()=>ok(site("Connection.execute",752n).category==="disabled_cache_path"));
 check("wrong frozen source hash rejected",()=>{const s=site();s.location.source_sha256="0".repeat(64);reject(()=>api.validateSites([s],context));});
 check("declared category cannot override source map",()=>{const s=site();s.category="fts_candidates";reject(()=>api.validateSites([s],context));});
 const ids=["invented-a","invented-b","invented-c"],digest="a".repeat(64),dataset="1".repeat(64),axis=["invented","native-char4000"];
 const expected={queries:3n,dataset_sha256:dataset,profile_query_order_sha256:core.orderedIdSha(ids),query_universe_sorted_ids_sha256:core.orderedIdSha([...ids].sort())};
 const options={budget_chars:4000n};
 function payload(mismatches=[],classification=[]){return {cohort:axis[0],configuration:axis[1],queries:3n,
  query_order_sha256:expected.profile_query_order_sha256,mismatches,classification_violations:classification,
  all_classification_sites_valid:classification.length===0,all_full_non_timing_payloads_equal:mismatches.length===0};}
 const baseline={cohort:axis[0],configuration:axis[1],dataset_sha256:dataset,queries:3n,status:"completed",rows:ids.map(query_id=>({query_id,non_timing_payload_sha256:digest}))};
 function cell(){return {...clone(baseline),options:clone(options),sites:clone(sites),rows:baseline.rows.map(row=>({...row,observation:nested()})),
  payload_audit:payload(),callsite_summary:[{site_id:0n,method:"Connection.execute",category:"transaction",calls:15n,returned:12n,exceptions:3n,open:0n,inclusive_ns:540n,exclusive_ns:360n}]};}
 const runCell=v=>api.auditCell(v,baseline,axis,expected,context,options);
 check("all invented spans and exceptions aggregate",()=>{const out=runCell(cell());ok(out.totals.spans===15n&&out.totals.observed_exclusive_builtin_ns===360n&&
  out.totals.recall_wall_ns_including_observer===1500n&&out.totals.unattributed_wall_ns===1140n&&out.totals.callback_bookkeeping_ns===21n&&out.exceptions.length===3);});
 check("all mismatches retained without early acceptance",()=>{const value=cell(),mismatches=[];
  for(let i=0;i<3;i++){value.rows[i].non_timing_payload_sha256=String(i).repeat(64);mismatches.push({cohort:axis[0],configuration:axis[1],query_id:ids[i],baseline:digest,observed:String(i).repeat(64)});}
  value.payload_audit=payload(mismatches);const out=runCell(value);ok(out.payload_audit.mismatches.length===3&&!out.payload_audit.all_full_non_timing_payloads_equal);});
 check("query order mismatch rejected",()=>{const v=cell();v.rows.reverse();reject(()=>runCell(v),/order/);});
 check("declared summary count corruption rejected",()=>{const v=cell();v.callsite_summary[0].calls++;reject(()=>runCell(v),/summary/);});
 check("declared duration corruption rejected",()=>{const v=cell();v.callsite_summary[0].exclusive_ns--;reject(()=>runCell(v),/summary/);});
 check("options remain exact",()=>{const v=cell();v.options.budget_chars=4001n;reject(()=>runCell(v),/options/);});
 for(const category of ["unclassified_primary","disabled_cache_path"])
  check(category+" preserves raw but invalidates classification",()=>{const v=cell(),s=site("Connection.execute",category==="disabled_cache_path"?752n:999n);
   v.sites=[s];v.callsite_summary[0].category=category;v.payload_audit=payload([],[{site_id:0n,category}]);
   const out=runCell(v);ok(!out.payload_audit.all_classification_sites_valid&&out.totals.spans===15n&&out.callsites[0].category===category);});
 check("bounded UTF8 split preserves scalar boundaries",()=>{const text="a".repeat(65535)+"汉😀"+"z".repeat(65536);
  ok(api.boundedUtf8(core.utf8bytes(text))===text);});
 check("bounded UTF8 rejects truncated scalar",()=>reject(()=>api.boundedUtf8(new Uint8Array([0xf0,0x9f,0x98]))));
 check("bounded base64 joins complete chunks",()=>{const bytes=api.boundedBase64("AAAA".repeat(50000)+"AA==");ok(bytes.length===150001&&bytes.every(x=>x===0));});
 check("bounded base64 rejects early padding",()=>reject(()=>api.boundedBase64("AA=="+"AAAA".repeat(20000)),/padding/));
 function fakePack(value){
  const raw=core.utf8bytes(api.stringifyExact(value,true)),compressed=new Uint8Array([31,139,0]);
  return {encoded:"H4sA",codec:{ungzip:()=>raw},spec:{path:"invented.json.gz",bytes:3n,sha256:core.sha256Bytes(compressed),raw_bytes:BigInt(raw.length),raw_sha256:core.sha256Bytes(raw)}};
 }
 check("profile index releases cells and standalone body matches",()=>{
  const body=cell(),packed=fakePack(body),full=fakePack({cells:Array.from({length:8},()=>({...clone(body),storage:{cell:clone(packed.spec),ledger:{path:"invented-ledger"}}}))});
  const index=api.profileIndex(full.encoded,full.spec,full.codec);ok(index.links.length===8&&!Object.hasOwn(index.header.cells[0],"rows"));
  const out=api.auditStoredCell(packed.encoded,index.links[0],baseline,axis,expected,context,options,packed.codec);
  ok(out.audit.totals.spans===15n&&out.canonical_body_sha256===index.links[0].canonical_body_sha256);
 });
 check("standalone cell mismatch with full profile rejected",()=>{
  const body=cell(),packed=fakePack(body),link={index:0n,cohort:axis[0],configuration:axis[1],queries:3n,dataset_sha256:dataset,
   canonical_body_sha256:"0".repeat(64),storage:{cell:packed.spec}};
  reject(()=>api.auditStoredCell(packed.encoded,link,baseline,axis,expected,context,options,packed.codec),/differs from complete profile/);
 });
 check("profile index refuses incomplete inventory",()=>{const packed=fakePack({cells:[]});reject(()=>api.profileIndex(packed.encoded,packed.spec,packed.codec),/eight/);});
 return {schema_version:1,status:failures.length?"failed":"passed",tests:cases.length,passed:cases.filter(x=>x.status==="passed").length,
  failed:failures.length,failures,cases,corpus_calls:0,retrieval_calls:0,microbenchmark_calls:0,
  notes:["Gzip transport integrity is covered by the pinned prior48-check utility suite; the three incremental adapter cases inject an invented decoder solely to test exact object handoff.",
   "No engine/source runtime is imported. Fixtures use invented strings, source metadata, exact clocks and spans; no measured duration or performance claim."]};
};
