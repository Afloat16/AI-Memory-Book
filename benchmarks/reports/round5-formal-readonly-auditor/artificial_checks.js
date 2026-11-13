"use strict";
module.exports=function runArtificial(core,exact,api,formalConfigs){
 const cases=[],clone=v=>exact.parseExact(exact.stringifyExact(v));
 function ok(v,message="assertion failed"){if(!v)throw Error(message);}
 function test(name,fn){try{fn();cases.push({name,status:"passed"});}catch(error){cases.push({name,status:"failed",error:String(error),stack:error.stack});}}
 function rejected(fn,pattern){let error;try{fn();}catch(e){error=e;}ok(error,"expected rejection");if(pattern)ok(pattern.test(String(error)),"unexpected error "+error);}
 const hash=value=>core.sha256Bytes(core.utf8bytes(value));
 test("cancelled large values retain low-order unit",()=>ok(api.fsum([1e16,1,-1e16])===1));
 test("exact sum rounds an even half-way tie downward",()=>ok(api.fsum([1,Math.pow(2,-53)])===1));
 test("exact sum rounds odd half-way tie upward",()=>ok(api.fsum([1+Math.pow(2,-52),Math.pow(2,-53)])===1+Math.pow(2,-51)));
 test("minimum subnormal survives exact sum",()=>ok(api.fsum([Number.MIN_VALUE,Number.MIN_VALUE])===2*Number.MIN_VALUE));
 test("negative exact sum and cancellation",()=>ok(api.fsum([-1e16,-1,1e16])===-1&&api.fsum([1,-1])===0));
 test("known accurate fractional summation",()=>ok(api.fsum([.1,.1,.1])===.30000000000000004));
 test("known fsum divided by sample count",()=>ok(api.fmean([1,2,6])===3));
 test("nonfinite cannot enter summation",()=>rejected(()=>api.fsum([1,Infinity])));
 test("overflow is retained as failure",()=>rejected(()=>api.fsum([1e308,1e308]),/overflows/));
 test("two-value linearly interpolated quantiles",()=>ok(api.percentile([10,0],.5)===5&&api.percentile([10,0],.95)===9.5));
 test("empty quantile has original null behavior",()=>ok(api.percentile([],.95)===null));
 test("four-value fractional p95",()=>ok(api.percentile([4,1,3,2],.95)===3.8499999999999996));
 test("integer histogram matches manually repeated order statistics",()=>{const n=api.histogramNumeric([[1n,2n],[7n,2n]]);
  ok(n.samples===4n&&n.mean===4&&n.p50===4&&n.p95===7&&n.min===1n&&n.max===7n);});
 test("histogram merge preserves repetitions",()=>ok(api.same(api.mergeHistograms([[[1n,2n],[7n,2n]],[[1n,2n]]]),[[1n,4n],[7n,2n]])));
 test("histogram cannot mix nullable envelopes",()=>rejected(()=>api.mergeHistograms([null,[[1n,1n]]])));
 test("integer and boolean types remain distinct",()=>ok(!api.same(0n,false)&&!api.same(1n,1)&&!api.same("1",1n)));
 test("number declaration comparison uses frozen tolerance",()=>{const issues=[],errors={compared:0n,maximum_absolute_difference:0};
  api.compareNumbers({v:1+1e-13},{v:1},"x",issues,errors);ok(issues.length===0);
  api.compareNumbers({v:1.001},{v:1},"x",issues,errors);ok(issues.length===1&&errors.compared===2n);});
 function b64(bytes){const chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",out=[];for(let i=0;i<bytes.length;i+=3){
  const a=bytes[i],b=bytes[i+1],c=bytes[i+2],v=(a<<16)|((b||0)<<8)|(c||0);out.push(chars[(v>>18)&63]+chars[(v>>12)&63]+(i+1<bytes.length?chars[(v>>6)&63]:"=")+(i+2<bytes.length?chars[v&63]:"="));}return out.join("");}
 function chunks(values){let offset=0;const all=new Uint8Array(values.reduce((n,v)=>n+v.length,0));const claims=values.map((v,i)=>{
  const result={index:BigInt(i),offset:BigInt(offset),bytes:BigInt(v.length),sha256:core.sha256Bytes(v)};all.set(v,offset);offset+=v.length;return result;});
  const spec={bytes:BigInt(all.length),sha256:core.sha256Bytes(all)};return {encoded:values.map(b64),manifest:{...spec,chunks:claims},spec,all};}
 test("transport chunks reassemble exact original bytes",()=>{const f=chunks([new Uint8Array([31,139,0]),new Uint8Array([255,0,12,4])]);
  ok(api.reassembleChunks(f.encoded,f.manifest,f.spec).every((v,i)=>v===f.all[i]));});
 for(const mode of ["offset","digest","missing","reorder","original_hash"])
  test("transport corruption rejected "+mode,()=>{const f=chunks([new Uint8Array([31,139,0]),new Uint8Array([255,0,12,4])]);
   if(mode==="offset")f.manifest.chunks[1].offset++;if(mode==="digest")f.manifest.chunks[1].sha256="0".repeat(64);
   if(mode==="missing")f.encoded.pop();if(mode==="reorder")f.encoded.reverse();if(mode==="original_hash")f.spec.sha256="0".repeat(64);
   rejected(()=>api.reassembleChunks(f.encoded,f.manifest,f.spec));});
 const configs=clone(formalConfigs),ids=["invented-a","invented-b"],source={commit:"b".repeat(40),runtime_sha256:"b".repeat(64)};
 const cert={tool_schema_json:'{"tools":[]}',tool_schema_sha256:hash('{"tools":[]}'),instructions:"invented",
  instructions_sha256:hash("invented"),initialization_tokens:{cl100k_base:{tool_schema:4n,instructions:1n},o200k_base:{tool_schema:4n,instructions:1n}},database_created:false};
 const item={key:"r0-invented-baseline",round:0n,cohort:"invented",label:"baseline"};
 const context={runIdentity:"a".repeat(64),plan:{candidate:{formal:{configs}}},run:{schedule:[item],
  binding:{sources:{baseline:source},interface_certificate:{observations:{baseline:cert}}},cohorts:{invented:{sha256:"d".repeat(64),queries:2n,query_ids:ids}}}};
 function row(id,spec){
  const mcp=spec.surface==="official-sdk-mcp-stdio",cost={context:1n,response_text:4n,response_envelope_json:mcp?7n:null};
  const tm=spec.budget_tokens===null?null:{budget_tokens:spec.budget_tokens,tokenizer:spec.tokenizer,tokenizer_version:"0.12.0",context_tokens:1n};
  return {query_id:id,category:"invented",wall_ms:1.25,engine_source_sha256:source.runtime_sha256,
   payload_sha256:"1".repeat(64),native_payload_sha256:(id==="invented-a"?"2":"3").repeat(64),context_sha256:"4".repeat(64),envelope_sha256:mcp?"5".repeat(64):null,
   response_utf8_bytes:12n,envelope_utf8_bytes:mcp?20n:null,context_chars:1n,result_count:1n,cache_rows_before:0n,cache_rows_after:mcp?1n:0n,
   tokens:{cl100k_base:{...cost},o200k_base:{...cost}},token_metadata:tm?{native:{...tm},response:{...tm}}:null,
   invariants:Object.fromEntries(api.INVARIANTS.map(k=>[k,k.endsWith("_errors")?0n:false]))};
 }
 function fixture(){
  const session={mcp_startup_to_initialize_ms:2.0,mcp_tool_schema_sha256:cert.tool_schema_sha256,mcp_instructions_sha256:cert.instructions_sha256,
   mcp_initialization_tokens:clone(cert.initialization_tokens),mcp_server_memory_after_calls:{available:true,rss_bytes:100n},
   storage_after_mcp_live:{bytes:100n},mcp_tool_schema_json:cert.tool_schema_json,mcp_instructions:cert.instructions};
  const worker={...item,status:"completed",error:null,source:clone(source),source_after:clone(source),run_identity_sha256:context.runIdentity,
   dataset_sha256:"d".repeat(64),all_replayed_sessions_skipped:true,native_recall_cache_rows:0n,indexed_content:"same",indexed_content_after_calls:"same",
   configurations:configs.map(spec=>({...spec,rows:ids.map(id=>row(id,spec)),latency:{samples:2n,p50_ms:1.25,p95_ms:1.25,mean_ms:1.25}})),
   mcp_sessions:{"mcp-char4000":clone(session),"mcp-token1024":clone(session)},...clone(session)};
  return {worker,started:{worker:clone(item),run_identity_sha256:context.runIdentity}};
 }
 function ledger(worker){
  const events=[];let seq=0n;for(const c of worker.configurations)for(const row of c.rows){
   events.push({event:"started",seq,config:c.id,query_id:row.query_id,at:"invented-start"});
   events.push({event:"finished",seq,config:c.id,row:clone(row),at:"invented-end"});seq++;
  }return events;
 }
 function run(f,events=ledger(f.worker)){
  const ledgerText=events.map(v=>exact.stringifyExact(v)).join("\n")+"\n";f.worker.ledger_sha256=hash(ledgerText);
  return api.auditWorker({worker_text:exact.stringifyExact(f.worker),started_text:exact.stringifyExact(f.started),ledger_text:ledgerText},context);
 }
 function has(r,k){return r.issues.some(x=>x.check===k);}
 test("complete invented worker and every ledger pair pass",()=>{const r=run(fixture());ok(r.issues.length===0,exact.stringifyExact(r.issues));
  ok(r.calls===14n&&r.ledger_events===28n&&r.configurations.length===7);});
 test("recorded non-timing field changes alter stable complete-row digest",()=>{const a=run(fixture()),f=fixture();f.worker.configurations[0].rows[0].tokens.o200k_base.response_text=5n;
  const b=run(f);ok(b.issues.length===0&&a.configurations[0].rows[0][1]!==b.configurations[0].rows[0][1]);});
 const bad=[
  ["source_after","source_before_after",f=>f.worker.source_after.runtime_sha256="c".repeat(64)],
  ["query_duplicate","complete_query_universe",f=>f.worker.configurations[0].rows[1].query_id="invented-a"],
  ["strict_integer_cache","cache_counts",f=>f.worker.configurations[0].rows[0].cache_rows_before=false],
  ["invariant","all_original_invariants",f=>f.worker.configurations[0].rows[0].invariants.cache_error=true],
  ["character_bound","character_result_size_bounds",f=>f.worker.configurations[0].rows[0].context_chars=4001n],
  ["missing_full_row_field","complete_row_fields",f=>delete f.worker.configurations[0].rows[0].category],
  ["declared_latency","numeric_declaration",f=>f.worker.configurations[0].latency.p95_ms=2.0],
  ["native_mcp_payload","actual_sdk_native_full_payload",f=>f.worker.configurations[2].rows[0].native_payload_sha256="7".repeat(64)],
  ["strict_token_metadata","strict_token_budget_metadata",f=>f.worker.configurations[3].rows[0].token_metadata.response.budget_tokens=513n],
  ["sdk_certificate","exact_actual_sdk_interface_certificate",f=>f.worker.mcp_sessions["mcp-token1024"].mcp_instructions="changed"],
  ["fake_intent","original_worker_intent",f=>f.started.run_identity_sha256="z".repeat(64)]];
 for(const [name,expected,change] of bad)test("worker preserves invalid predicate "+name,()=>{const f=fixture();change(f);ok(has(run(f),expected));});
 test("ledger end full-row mismatch survives valid byte hash",()=>{const f=fixture(),events=ledger(f.worker);events[1].row.wall_ms=2.0;ok(has(run(f,events),"complete_started_finished_ledger_pair"));});
 test("ledger missing final event is rejected",()=>{const f=fixture(),events=ledger(f.worker);events.pop();rejected(()=>run(f,events),/Interrupted/);});
 test("ledger extra events are retained as invalid",()=>{const f=fixture(),events=ledger(f.worker);events.push({event:"extra"});ok(has(run(f,events),"no_extra_ledger_events"));});
 test("ledger wrong original sequence is invalid",()=>{const f=fixture(),events=ledger(f.worker);events[2].seq=99n;ok(has(run(f,events),"complete_started_finished_ledger_pair"));});
 function constantLatency(count,value){return {samples:count,p50_ms:value,p95_ms:value,mean_ms:value};}
 function constantNumeric(count,value){return {samples:count,mean:Number(value),p50:Number(value),p95:Number(value),min:value,max:value};}
 function aggregateFixture(){
  const formal={cohorts:["synthetic61","public1015"],configs,gate:clone(api.GATES)},schedule=[],receipts=[],byCohort={synthetic61:168,public1015:1015},
   order=[["baseline","candidate"],["candidate","baseline"],["candidate","baseline"],["baseline","candidate"]];
  for(let round=0;round<4;round++)for(const cohort of formal.cohorts)for(const label of order[round]){
   const item={key:"r"+round+"-"+cohort+"-"+label,round:BigInt(round),cohort,label},n=byCohort[cohort],wall=label==="baseline"?10.0:8.0;
   const header={key:item.key,indexed_content:"same",fresh_ingestion_results_sha256:"same",unchanged_reingestion_results_sha256:"same",mcp_instructions:"same",mcp_instructions_sha256:"same"};
   const rows=Array.from({length:n},(_,i)=>["invented-"+i,"a".repeat(64),wall]);if(round%2)rows.reverse();
   const configsHere=configs.map(spec=>({...spec,queries:BigInt(n),rows:rows.map(r=>[...r]),latency:constantLatency(BigInt(n),wall),
    histograms:{response_utf8_bytes:[[16n,BigInt(n)]],context_chars:[[8n,BigInt(n)]],
     tokens:Object.fromEntries(api.ENCODINGS.map(name=>[name,{context:[[2n,BigInt(n)]],response_text:[[4n,BigInt(n)]],
      response_envelope_json:spec.surface==="native"?null:[[6n,BigInt(n)]]}]))}}));
   schedule.push(item);receipts.push({...item,status:"independently-checked-worker-and-ledger",issues:[],run_identity_sha256:"x",
    calls:BigInt(n*7),ledger_events:BigInt(n*14),worker_header:header,configurations:configsHere});
  }
  const comparisons=[];
  for(const cohort of formal.cohorts)for(const spec of configs){
   const n=BigInt(byCohort[cohort]),engines={};
   for(const label of ["baseline","candidate"]){const wall=label==="baseline"?10.0:8.0;
    engines[label]={latency:constantLatency(n*4n,wall),first_round_latency:constantLatency(n,wall),repeat_rounds_latency:constantLatency(n*3n,wall),
     response_utf8_bytes:constantNumeric(n*4n,16n),context_chars:constantNumeric(n*4n,8n),
     tokens:Object.fromEntries(api.ENCODINGS.map(name=>[name,{context:constantNumeric(n*4n,2n),response_text:constantNumeric(n*4n,4n),
      response_envelope_json:spec.surface==="native"?null:constantNumeric(n*4n,6n)}]))};
   }
   comparisons.push({cohort,...spec,...engines,candidate_change_percent:{p50_ms:-19.999999999999996,p95_ms:-19.999999999999996,mean_ms:-19.999999999999996},
    rounds:Array.from({length:4},(_,round)=>({round:BigInt(round),baseline:constantLatency(n,10),candidate:constantLatency(n,8)}))});
  }
  const summary={workers:receipts.map(r=>r.worker_header),comparisons,status:"completed",error:null,evaluator_unchanged:true,
   validation:{passed:true,issues:[],workers:16n,expected_workers:16n,timed_calls:66248n,expected_calls:66248n},
   acceptance:{numeric_gate_passed:true,geometric_mean_p95_improvement_percent:20.0,public_native_char4000_p95_improvement_percent:20.0,
    public_mcp_char4000_p95_improvement_percent:20.0,thresholds_percent:clone(api.GATES),regressions_above_five_percent:[],accepted:true,resource_review:[]}};
  return {receipts,context:{plan:{candidate:{formal}},run:{schedule},runIdentity:"x"},summary};
 }
 test("full66248 invented compact calls reproduce14cells and33124pairs",()=>{const f=aggregateFixture(),r=api.aggregate(f.receipts,f.context,f.summary);
  ok(r.issues.length===0,exact.stringifyExact(r.issues));ok(r.calls===66248n&&r.full_payload_pairs===33124n&&r.comparisons.length===14&&r.numeric_acceptance.numeric_gate_passed);});
 test("all first middle and last paired/cross-round mismatches retained",()=>{const f=aggregateFixture();
  const changed=[f.receipts[1].configurations[0].rows[0],f.receipts[7].configurations[3].rows[30],f.receipts[15].configurations[6].rows.at(-1)];
  changed.forEach((row,i)=>row[1]=String(i).repeat(64));
  const r=api.aggregate(f.receipts,f.context,f.summary);ok(r.pair_mismatches.length===3&&r.cross_round_mismatches.length===3&&!r.issues.every(x=>x.check!=="complete_paired_non_timing_rows"));});
 test("paired order mismatch is independent of full set equality",()=>{const f=aggregateFixture();f.receipts[1].configurations[0].rows.reverse();
  const r=api.aggregate(f.receipts,f.context,f.summary);ok(r.issues.some(x=>x.check==="paired_complete_query_order")&&r.pair_mismatches.length===0);});
 test("adverse cell keeps bothp50/p95 failures and fails original gate",()=>{const f=aggregateFixture();
  for(const worker of f.receipts)if(worker.cohort==="synthetic61"&&worker.label==="candidate"){
   const c=worker.configurations[0];c.rows.forEach(r=>r[2]=11.0);c.latency=constantLatency(168n,11);}
  const r=api.aggregate(f.receipts,f.context,f.summary);ok(!r.numeric_acceptance.numeric_gate_passed&&r.numeric_acceptance.regressions_above_five_percent.length===2);});
 test("aggregate refuses missing worker",()=>{const f=aggregateFixture();f.receipts.pop();rejected(()=>api.aggregate(f.receipts,f.context,f.summary),/sixteen/);});
 const failed=cases.filter(c=>c.status!=="passed");
 return {schema_version:1,status:failed.length?"failed":"passed",tests:cases.length,passed:cases.length-failed.length,failed:failed.length,cases,
  fixture_scope:"Invented metadata/rows/ledgers and66,248 small compact synthetic timing tuples only; no corpus, engine, tokenizer,PRNG or network execution.",
  corpus_calls:0,retrieval_calls:0,microbenchmarks:0};
};
