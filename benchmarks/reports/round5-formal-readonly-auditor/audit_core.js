"use strict";
/* Read-only formal audit core. All inputs are immutable saved artifacts.
 * No source import, retrieval, tokenizer, PRNG, subprocess, network or workflow.
 */
module.exports=function makeFormalAudit(core,exact){
 const PIN={
  workflow:"cfe8a749efa4add1c62c516aa299ab18ee89b92c",runId:43496488712n,attempt:1n,
  runIdentity:"4ae3879c796f08b016e343c57c9c4468361255c7e57feb1590632c95416e15e6",
  runFile:"049a772a04310f94c833f645ac333cc4f3b8303549d0b03b539d51d9c37aff55",
  binding:"1d5af43c6c9b3e826ce11814f29320f9838c3ad603a80b1a36eb9d122fc6b247",
  plan:"d3302ef1169aa180b492af6b9c9938e5717ff7261e202ef7a3df50e14febaccd",
  producer:"388536dd4bf3dc4c7d76cc8c5bac3afd273071cebcf7f9639ed1b65d19e4f1fb",
  source:{baseline:{commit:"692fb959ddf8934c5f516ba3d74ceb4385a2fa82",runtime_sha256:"179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93"},
   candidate:{commit:"4a0ad4dc6aec33a91231d419239b7e90b160c695",runtime_sha256:"77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32"}}
 };
 const ENCODINGS=["cl100k_base","o200k_base"],INVARIANTS=["cache_error","source_span_errors","source_scope_errors","page_projection_errors",
  "context_reconstruction_error","metadata_error","character_budget_error","token_budget_error","token_metadata_error","mcp_projection_error",
  "result_limit_error","unexpected_policy"];
 const ROW_FIELDS=["query_id","category","wall_ms","engine_source_sha256","payload_sha256","native_payload_sha256","context_sha256",
  "envelope_sha256","response_utf8_bytes","envelope_utf8_bytes","context_chars","result_count","cache_rows_before","cache_rows_after","tokens","token_metadata","invariants"];
 const SESSION_FIELDS=["mcp_startup_to_initialize_ms","mcp_tool_schema_sha256","mcp_instructions_sha256","mcp_initialization_tokens",
  "mcp_server_memory_after_calls","storage_after_mcp_live","mcp_tool_schema_json","mcp_instructions"];
 const HEX=/^[0-9a-f]{64}$/,GATES={minimum_geomean_pooled_p95_improvement_percent:10n,
  minimum_public_native_char4000_p95_improvement_percent:10n,minimum_public_actual_mcp_char4000_p95_improvement_percent:5n,
  maximum_any_pooled_p50_p95_regression_percent:5n,resource_mean_increase_review_percent:10n};
 const need=(x,m)=>{if(!x)throw Error(m);};
 function same(a,b){
  if(a===b)return true;if(a===null||b===null||typeof a!==typeof b)return false;
  if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>same(v,b[i]));
  if(typeof a!=="object")return false;
  const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();return same(ak,bk)&&ak.every(k=>same(a[k],b[k]));
 }
 const int=(value,min=0n)=>typeof value==="bigint"&&value>=min;
 function number(value){if(typeof value==="bigint"){need(value>=-9007199254740991n&&value<=9007199254740991n,"Integer cannot be converted exactly");return Number(value);}
  need(typeof value==="number"&&Number.isFinite(value),"Finite numeric value required");return value;}
 const view=new DataView(new ArrayBuffer(8));
 function units(value){
  value=number(value);view.setFloat64(0,value,false);const bits=view.getBigUint64(0,false),sign=bits>>63n?-1n:1n;
  const exponent=Number((bits>>52n)&2047n),fraction=bits&((1n<<52n)-1n);
  need(exponent!==2047,"Nonfinite binary input");return sign*(exponent===0?fraction:((1n<<52n)|fraction)<<BigInt(exponent-1));
 }
 function roundedUnits(value){
  if(value===0n)return 0;const sign=value<0n?-1:1;let n=value<0n?-value:value;
  const shift=Math.max(0,n.toString(2).length-53);let top=n>>BigInt(shift);
  if(shift){const remainder=n-(top<<BigInt(shift)),half=1n<<BigInt(shift-1);if(remainder>half||(remainder===half&&(top&1n)))top++;}
  const out=sign*Number(top)*Math.pow(2,shift-1074);need(Number.isFinite(out),"Exact sum overflows binary64");return out;
 }
 function fsum(values){let sum=0n;for(const value of values)sum+=units(value);return roundedUnits(sum);}
 function fmean(values){need(values.length>0,"Mean needs samples");return fsum(values)/values.length;}
 function percentile(values,q){if(!values.length)return null;const sorted=values.map(number).sort((a,b)=>a-b),location=(sorted.length-1)*q,
  low=Math.floor(location),high=Math.ceil(location);return sorted[low]+(sorted[high]-sorted[low])*(location-low);}
 function latency(values){return {samples:BigInt(values.length),p50_ms:percentile(values,.5),p95_ms:percentile(values,.95),mean_ms:values.length?fmean(values):null};}
 function numeric(values){if(!values.length)return null;return {samples:BigInt(values.length),mean:fmean(values),p50:percentile(values,.5),p95:percentile(values,.95),
  min:values.reduce((a,b)=>a<b?a:b),max:values.reduce((a,b)=>a>b?a:b)};}
 function histogram(values){
  if(!values.length||values[0]===null){need(values.every(x=>x===null),"Mixed null histogram");return null;}
  const bins=new Map();for(const v of values){need(int(v),"Histogram count must be an exact nonnegative integer");bins.set(v,(bins.get(v)||0n)+1n);}
  return [...bins].sort(([a],[b])=>a<b?-1:a>b?1:0);
 }
 function mergeHistograms(groups){
  if(groups.every(g=>g===null))return null;need(groups.every(g=>g!==null),"Mixed histogram surface");
  const bins=new Map();for(const group of groups)for(const [v,n] of group){need(int(v)&&int(n,1n),"Invalid histogram bin");bins.set(v,(bins.get(v)||0n)+n);}
  return [...bins].sort(([a],[b])=>a<b?-1:a>b?1:0);
 }
 function histogramNumeric(bins){
  if(bins===null)return null;need(bins.length>0,"Empty histogram");let count=0n,sum=0n;
  for(const [v,n] of bins){need(int(v)&&int(n,1n),"Invalid histogram");count+=n;sum+=units(v)*n;}
  function at(index){let cumulative=0n;for(const [v,n] of bins){cumulative+=n;if(index<cumulative)return number(v);}throw Error("Histogram index overflow");}
  function quantile(q){const position=(number(count)-1)*q,lo=Math.floor(position),hi=Math.ceil(position),left=at(BigInt(lo)),right=at(BigInt(hi));return left+(right-left)*(position-lo);}
  return {samples:count,mean:roundedUnits(sum)/number(count),p50:quantile(.5),p95:quantile(.95),min:bins[0][0],max:bins.at(-1)[0]};
 }
 function compareNumbers(actual,expected,path,issues,errors){
  if(typeof actual==="number"&&typeof expected==="number"){
   const difference=Math.abs(actual-expected),allowed=2e-12*Math.max(1,Math.abs(actual),Math.abs(expected));
   if(difference>errors.maximum_absolute_difference)errors.maximum_absolute_difference=difference;
   errors.compared++;if(!Number.isFinite(actual)||!Number.isFinite(expected)||difference>allowed)issues.push({check:"numeric_declaration",path,independent:actual,declared:expected,difference,allowed});
   return;
  }
  if(actual===null||expected===null||typeof actual!=="object"||typeof expected!=="object"){
   if(!same(actual,expected))issues.push({check:"exact_declaration",path,independent:actual,declared:expected});return;
  }
  const ak=Object.keys(actual).sort(),bk=Object.keys(expected).sort();
  if(!same(ak,bk)){issues.push({check:"declaration_keys",path,independent:ak,declared:bk});return;}
  for(const key of ak)compareNumbers(actual[key],expected[key],path+"."+key,issues,errors);
 }
 function parseText(text,sha,label){need(core.sha256Bytes(core.utf8bytes(text))===sha,"Pinned text differs "+label);return exact.parseExact(text);}
 function prepare(input){
  const run=parseText(input.run_text,PIN.runFile,"run"),binding=parseText(input.binding_text,PIN.binding,"binding"),
   plan=parseText(input.plan_text,PIN.plan,"plan");
  need(run.workflow_commit===PIN.workflow&&same(run.binding,binding)&&run.binding_sha256===PIN.binding&&
   run.plan_sha256===PIN.plan&&same(binding.sources,PIN.source)&&same(run.evaluator_files,binding.evaluator_files),"Frozen execution/source closure differs");
  need(binding.evaluator==="round5-default-performance-2-final-interface"&&binding.evaluator_files["scripts/round5_performance_v2.py"]===PIN.producer,
   "Frozen evaluator differs");
  const formal=plan.candidate.formal,expected=[];
  need(formal.rounds===4n&&formal.calls===66248n&&same(formal.cohorts,["synthetic61","public1015"])&&formal.configs.length===7&&same(formal.gate,GATES),"Original formal axes/gates differ");
  const order=[["baseline","candidate"],["candidate","baseline"],["candidate","baseline"],["baseline","candidate"]];
  need(same(formal.engine_order,order),"Original ABBA order changed");
  for(let round=0;round<4;round++)for(const cohort of formal.cohorts)for(const label of order[round])expected.push({key:"r"+round+"-"+cohort+"-"+label,round:BigInt(round),cohort,label});
  need(same(run.schedule,expected),"Complete worker schedule differs");
  for(const cohort of formal.cohorts){
   const saved=run.cohorts[cohort],registered=plan.cohorts.find(c=>c.name===cohort);
   need(saved.sha256===registered.sha256&&saved.queries===registered.queries&&BigInt(saved.query_ids.length)===saved.queries&&
    new Set(saved.query_ids).size===saved.query_ids.length&&same([...saved.query_ids_original_order].sort(),saved.query_ids),"Complete frozen query universe differs");
  }
  return {run,binding,plan,runIdentity:PIN.runIdentity};
 }
 function unpack(encoded,spec,codec){return unpackBytes(exact.boundedBase64(encoded),spec,codec);}
 function unpackBytes(compressed,spec,codec){
  need(compressed instanceof Uint8Array&&int(spec.bytes,1n)&&HEX.test(spec.sha256),"Compressed artifact identity missing");need(BigInt(compressed.length)===spec.bytes&&core.sha256Bytes(compressed)===spec.sha256,"Compressed bytes/hash differ");
  need(compressed[0]===31&&compressed[1]===139,"Expected gzip");
  const raw=codec.ungzip(compressed);need(raw instanceof Uint8Array,"Codec must return exact bytes");
  const rawSha=core.sha256Bytes(raw);
  if(spec.raw_sha256!==undefined)need(rawSha===spec.raw_sha256,"Raw SHA differs");
  if(spec.raw_bytes!==undefined)need(BigInt(raw.length)===spec.raw_bytes,"Raw size differs");
  return {raw,identity:{path:spec.path,compressed_bytes:BigInt(compressed.length),compressed_sha256:spec.sha256,
   raw_bytes:BigInt(raw.length),raw_sha256:rawSha,raw_sha256_source:spec.raw_sha256===undefined?"independently-computed-from-hash-pinned-gzip":"matched-original-raw-hash"}};
 }
 function auditWorker(input,context){
  const w=exact.parseExact(input.worker_text),started=exact.parseExact(input.started_text),run=context.run,formal=context.plan.candidate.formal;
  const issues=[],errors={compared:0n,maximum_absolute_difference:0},configs=[],ledgerRows=[];
  const check=(condition,path,extra={})=>{if(!condition)issues.push({check:path,...extra});};
  const item=run.schedule.find(x=>x.key===w.key);need(item,"Unknown worker");
  check(w.status==="completed"&&w.error===null,"worker_completed");
  check(Object.entries(item).every(([key,v])=>same(w[key],v))&&w.run_identity_sha256===context.runIdentity,"worker_identity");
  check(same(started,{worker:item,run_identity_sha256:context.runIdentity}),"original_worker_intent");
  const expected=run.binding.sources[w.label],cohort=run.cohorts[w.cohort],idsExpected=cohort.query_ids;
  check(same(w.source,expected)&&same(w.source_after,expected),"source_before_after");
  check(w.dataset_sha256===cohort.sha256,"dataset");
  check(w.all_replayed_sessions_skipped===true&&w.native_recall_cache_rows===0n&&same(w.indexed_content,w.indexed_content_after_calls),"ingestion_index_cache");
  need(Array.isArray(w.configurations)&&w.configurations.length===formal.configs.length,"Incomplete worker configuration inventory");
  const byId=new Map();
  for(let index=0;index<formal.configs.length;index++){
   const c=w.configurations[index],spec=formal.configs[index],path=w.key+"/"+spec.id,mcp=spec.surface==="official-sdk-mcp-stdio";
   check(same(Object.fromEntries(Object.keys(spec).map(k=>[k,c[k]])),spec),"config_axis",{path});
   need(Array.isArray(c.rows),"Missing worker rows");
   const ids=c.rows.map(r=>r.query_id);
   check(BigInt(ids.length)===cohort.queries&&new Set(ids).size===ids.length&&same([...ids].sort(),idsExpected),"complete_query_universe",{path});
   const compact=[],nativeHashes=new Map(),series={response_utf8_bytes:[],context_chars:[],tokens:Object.fromEntries(ENCODINGS.map(n=>[n,{context:[],response_text:[],response_envelope_json:[]}]))};
   for(let rowIndex=0;rowIndex<c.rows.length;rowIndex++){
    const row=c.rows[rowIndex],rp=path+"/"+row.query_id;
    check(same(Object.keys(row).sort(),[...ROW_FIELDS].sort()),"complete_row_fields",{path:rp});
    check(typeof row.query_id==="string"&&typeof row.category==="string","row_identity",{path:rp});
    check(typeof row.wall_ms==="number"&&Number.isFinite(row.wall_ms)&&row.wall_ms>0&&row.engine_source_sha256===expected.runtime_sha256,"positive_timing_source",{path:rp});
    check(same(Object.keys(row.invariants).sort(),[...INVARIANTS].sort())&&Object.values(row.invariants).every(v=>v===false||v===0n),"all_original_invariants",{path:rp,invariants:row.invariants});
    check(row.cache_rows_before===0n&&row.cache_rows_after===(mcp?1n:0n),"cache_counts",{path:rp});
    check(int(row.context_chars)&&row.context_chars<=spec.budget_chars&&int(row.result_count)&&row.result_count<=5n&&int(row.response_utf8_bytes,1n),"character_result_size_bounds",{path:rp});
    check(mcp?int(row.envelope_utf8_bytes,1n):row.envelope_utf8_bytes===null,"envelope_bytes_surface",{path:rp});
    check(same(Object.keys(row.tokens).sort(),[...ENCODINGS].sort()),"tokenizer_axis",{path:rp});
    for(const name of ENCODINGS){
     const costs=row.tokens[name];need(costs,"Missing tokenizer counts");
     check(same(Object.keys(costs).sort(),["context","response_envelope_json","response_text"])&&int(costs.context)&&int(costs.response_text)&&
      (mcp?int(costs.response_envelope_json):costs.response_envelope_json===null),"token_counts_surface",{path:rp,tokenizer:name});
     for(const field of ["context","response_text","response_envelope_json"])series.tokens[name][field].push(costs[field]);
    }
    if(spec.budget_tokens!==null){
     const tm={budget_tokens:spec.budget_tokens,tokenizer:spec.tokenizer,tokenizer_version:"0.12.0",context_tokens:row.tokens.cl100k_base.context};
     check(row.tokens.cl100k_base.context<=spec.budget_tokens&&same(row.token_metadata,{native:tm,response:tm}),"strict_token_budget_metadata",{path:rp});
    }else check(row.token_metadata===null,"char_token_metadata_absent",{path:rp});
    check(["payload_sha256","native_payload_sha256","context_sha256"].every(k=>typeof row[k]==="string"&&HEX.test(row[k])),"complete_payload_digests",{path:rp});
    check(mcp?typeof row.envelope_sha256==="string"&&HEX.test(row.envelope_sha256):row.envelope_sha256===null,"envelope_digest_surface",{path:rp});
    const stable=Object.fromEntries(Object.entries(row).filter(([key])=>key!=="wall_ms"&&key!=="engine_source_sha256"));
    compact.push([row.query_id,exact.digest(stable),row.wall_ms]);nativeHashes.set(row.query_id,row.native_payload_sha256);
    series.response_utf8_bytes.push(row.response_utf8_bytes);series.context_chars.push(row.context_chars);
    ledgerRows.push([spec.id,row]);
   }
   const measured=latency(c.rows.map(r=>r.wall_ms));compareNumbers(measured,c.latency,path+".latency",issues,errors);
   const hist={response_utf8_bytes:histogram(series.response_utf8_bytes),context_chars:histogram(series.context_chars),
    tokens:Object.fromEntries(ENCODINGS.map(n=>[n,Object.fromEntries(Object.entries(series.tokens[n]).map(([k,values])=>[k,histogram(values)]))]))};
   const receipt={...spec,queries:BigInt(c.rows.length),query_order_sha256:core.orderedIdSha(ids),rows:compact,latency:measured,histograms:hist};
   configs.push(receipt);byId.set(spec.id,{nativeHashes});
  }
  for(const suffix of ["char4000","token1024"]){
   const native=byId.get("native-"+suffix)?.nativeHashes,mcp=byId.get("mcp-"+suffix)?.nativeHashes;
   need(native&&mcp,"Comparable native/MCP surface missing");
   for(const [id,hash] of mcp)check(native.get(id)===hash,"actual_sdk_native_full_payload",{surface:suffix,query_id:id,baseline:native.get(id),observed:hash});
  }
  const sessionIds=formal.configs.filter(c=>c.surface==="official-sdk-mcp-stdio").map(c=>c.id).sort();
  check(same(Object.keys(w.mcp_sessions).sort(),sessionIds),"mcp_session_inventory");
  const certified=run.binding.interface_certificate.observations[w.label];
  for(const id of sessionIds){
   const session=w.mcp_sessions[id];need(session,"MCP session missing");
   check(same(Object.keys(session).sort(),[...SESSION_FIELDS].sort()),"mcp_session_fields",{surface:id});
   const observation={tool_schema_json:session.mcp_tool_schema_json,tool_schema_sha256:session.mcp_tool_schema_sha256,
    instructions:session.mcp_instructions,instructions_sha256:session.mcp_instructions_sha256,
    initialization_tokens:session.mcp_initialization_tokens,database_created:false};
   exact.parseExact(observation.tool_schema_json);
   check(core.sha256Bytes(core.utf8bytes(observation.tool_schema_json))===observation.tool_schema_sha256&&
    core.sha256Bytes(core.utf8bytes(observation.instructions))===observation.instructions_sha256&&same(observation,certified),
    "exact_actual_sdk_interface_certificate",{surface:id});
   check(session.mcp_server_memory_after_calls.available===true,"mcp_resource_available",{surface:id});
   for(const field of ["mcp_tool_schema_json","mcp_tool_schema_sha256","mcp_instructions","mcp_instructions_sha256","mcp_initialization_tokens"])
    check(same(session[field],w[field]),"mcp_session_initialization_identity",{surface:id,field});
  }
  check(SESSION_FIELDS.every(field=>same(w[field],w.mcp_sessions["mcp-char4000"][field])),"legacy_mcp_character_boundary");
  const ledgerBytes=core.utf8bytes(input.ledger_text);
  check(core.sha256Bytes(ledgerBytes)===w.ledger_sha256,"ledger_raw_sha");
  check(input.ledger_text.endsWith("\n"),"ledger_final_newline");
  let offset=0,lineCount=0;
  function nextLine(){
   if(offset>=input.ledger_text.length)return null;const end=input.ledger_text.indexOf("\n",offset);
   const line=input.ledger_text.slice(offset,end<0?input.ledger_text.length:end);offset=end<0?input.ledger_text.length:end+1;lineCount++;
   need(line.length>0,"Unexpected blank JSONL event");return exact.parseExact(line);
  }
  for(let seq=0;seq<ledgerRows.length;seq++){
   const [config,row]=ledgerRows[seq],begin=nextLine(),end=nextLine();
   need(begin&&end,"Interrupted ledger");check(begin.event==="started"&&end.event==="finished"&&
    begin.seq===BigInt(seq)&&end.seq===BigInt(seq)&&begin.config===config&&end.config===config&&
    begin.query_id===row.query_id&&same(end.row,row)&&typeof begin.at==="string"&&typeof end.at==="string",
    "complete_started_finished_ledger_pair",{seq:BigInt(seq),config,query_id:row.query_id});
  }
  check(nextLine()===null&&lineCount===ledgerRows.length*2,"no_extra_ledger_events",{events:BigInt(lineCount),expected:BigInt(ledgerRows.length*2)});
  const header=Object.fromEntries(Object.entries(w).filter(([key])=>key!=="configurations"));
  return {schema_version:1n,status:issues.length?"invalid-worker-evidence":"independently-checked-worker-and-ledger",
   key:w.key,round:w.round,cohort:w.cohort,label:w.label,source:expected,run_identity_sha256:context.runIdentity,
   calls:BigInt(ledgerRows.length),ledger_events:BigInt(lineCount),ledger_raw_sha256:w.ledger_sha256,
   issues,numeric_comparison:errors,configurations:configs,worker_header:header,
   seeded_shuffle_reimplemented:false,query_order_scope:"Original complete set and paired recorded order; the pinned hosted strictauditor independently enforces the registered Python seeded shuffle.",
   tokenizer_reexecuted:false,retrieval_calls:0n,new_measurements:0n};
 }

 function reassembleChunks(chunks,manifest,spec){
  need(Array.isArray(chunks)&&Array.isArray(manifest.chunks)&&chunks.length===manifest.chunks.length&&int(spec.bytes,1n),"Chunk inventory absent");
  need(manifest.bytes===spec.bytes&&manifest.sha256===spec.sha256,"Transport original-file binding differs");
  const result=new Uint8Array(number(spec.bytes));let offset=0;
  for(let i=0;i<chunks.length;i++){
   const claim=manifest.chunks[i],raw=exact.boundedBase64(chunks[i]);
   need(claim.index===BigInt(i)&&claim.offset===BigInt(offset)&&claim.bytes===BigInt(raw.length)&&
    claim.bytes>0n&&claim.bytes<=480000n&&HEX.test(claim.sha256)&&core.sha256Bytes(raw)===claim.sha256,"Compressed chunk identity/range differs");
   need(offset+raw.length<=result.length,"Compressed chunks overrun original");
   result.set(raw,offset);offset+=raw.length;
  }
  need(offset===result.length&&core.sha256Bytes(result)===spec.sha256,"Reassembled original gzip differs");
  return result;
 }
 function aggregate(receipts,context,summary){
  const formal=context.plan.candidate.formal,issues=[],errors={compared:0n,maximum_absolute_difference:0};
  const check=(condition,check,extra={})=>{if(!condition)issues.push({check,...extra});};
  need(receipts.length===context.run.schedule.length,"Complete sixteen worker receipts required");
  const canonical=new Map(),canonicalHeader=new Map(),comparisons=[],pairMismatches=[],crossRoundMismatches=[];
  let calls=0n,ledgerEvents=0n,paired=0n,comparedWithFirst=0n;
  for(let i=0;i<receipts.length;i++){
   const receipt=receipts[i],item=context.run.schedule[i];
   check(receipt.key===item.key&&receipt.round===item.round&&receipt.cohort===item.cohort&&receipt.label===item.label,
    "worker_schedule",{index:BigInt(i)});
   check(receipt.status==="independently-checked-worker-and-ledger"&&receipt.issues.length===0,"worker_proof_valid",{worker:receipt.key,issues:receipt.issues});
   check(receipt.run_identity_sha256===context.runIdentity,"worker_receipt_run",{worker:receipt.key});
   calls+=receipt.calls;ledgerEvents+=receipt.ledger_events;
   check(same(receipt.worker_header,summary.workers[i]),"summary_worker_metadata",{worker:receipt.key});
   for(const field of ["indexed_content","fresh_ingestion_results_sha256","unchanged_reingestion_results_sha256","mcp_instructions","mcp_instructions_sha256"]){
    const key=receipt.cohort+"/"+field,value=receipt.worker_header[field];
    if(canonicalHeader.has(key))check(same(value,canonicalHeader.get(key)),"cross_worker_ingest_interface",{worker:receipt.key,field});
    else canonicalHeader.set(key,value);
   }
   for(const config of receipt.configurations)for(const [id,hash] of config.rows){
    const key=receipt.cohort+"/"+config.id+"/"+id;
    if(canonical.has(key)){
     comparedWithFirst++;const first=canonical.get(key);
     if(first.hash!==hash)crossRoundMismatches.push({cohort:receipt.cohort,configuration:config.id,query_id:id,
      original_worker:first.worker,observed_worker:receipt.key,baseline:first.hash,observed:hash});
    }else canonical.set(key,{hash,worker:receipt.key});
   }
  }
  check(calls===66248n&&ledgerEvents===132496n,"complete_calls_and_ledger",{calls,ledgerEvents});
  for(const cohort of formal.cohorts)for(const spec of formal.configs){
   const byLabel=Object.fromEntries(["baseline","candidate"].map(label=>[label,receipts.filter(w=>w.cohort===cohort&&w.label===label)]));
   need(byLabel.baseline.length===4&&byLabel.candidate.length===4,"Four round workers per engine/cohort required");
   const rounds=[];
   for(let round=0;round<4;round++){
    const left=byLabel.baseline.find(w=>w.round===BigInt(round)).configurations.find(c=>c.id===spec.id),
     right=byLabel.candidate.find(w=>w.round===BigInt(round)).configurations.find(c=>c.id===spec.id);
    check(same(left.rows.map(r=>r[0]),right.rows.map(r=>r[0])),"paired_complete_query_order",{cohort,configuration:spec.id,round:BigInt(round)});
    const rightMap=new Map(right.rows.map(r=>[r[0],r[1]]));
    for(const [id,hash] of left.rows){paired++;if(rightMap.get(id)!==hash)pairMismatches.push({cohort,configuration:spec.id,round:BigInt(round),
      query_id:id,baseline:hash,candidate:rightMap.get(id)??null});}
    rounds.push({round:BigInt(round),baseline:left.latency,candidate:right.latency});
   }
   const engines={};
   for(const label of ["baseline","candidate"]){
    const workers=byLabel[label],configs=workers.map(w=>w.configurations.find(c=>c.id===spec.id));
    const latencies=configs.flatMap(c=>c.rows.map(row=>row[2]));
    const first=workers.filter(w=>w.round===0n).flatMap(w=>w.configurations.find(c=>c.id===spec.id).rows.map(r=>r[2]));
    const repeat=workers.filter(w=>w.round!==0n).flatMap(w=>w.configurations.find(c=>c.id===spec.id).rows.map(r=>r[2]));
    const countMetric=field=>histogramNumeric(mergeHistograms(configs.map(c=>c.histograms[field])));
    const tokens=Object.fromEntries(ENCODINGS.map(name=>[name,Object.fromEntries(["context","response_text","response_envelope_json"].map(field=>
     [field,histogramNumeric(mergeHistograms(configs.map(c=>c.histograms.tokens[name][field])))]))]));
    engines[label]={latency:latency(latencies),first_round_latency:latency(first),repeat_rounds_latency:latency(repeat),
     response_utf8_bytes:countMetric("response_utf8_bytes"),context_chars:countMetric("context_chars"),tokens};
   }
   const changes=Object.fromEntries(["p50_ms","p95_ms","mean_ms"].map(metric=>[metric,100*(engines.candidate.latency[metric]/engines.baseline.latency[metric]-1)]));
   comparisons.push({cohort,...spec,...engines,candidate_change_percent:changes,rounds});
  }
  check(paired===33124n,"complete_payload_pair_count",{paired});
  check(pairMismatches.length===0,"complete_paired_non_timing_rows",{mismatch_count:BigInt(pairMismatches.length)});
  check(crossRoundMismatches.length===0,"complete_cross_round_non_timing_rows",{mismatch_count:BigInt(crossRoundMismatches.length)});
  compareNumbers(comparisons,summary.comparisons,"comparisons",issues,errors);
  check(summary.status==="completed"&&summary.error===null&&summary.evaluator_unchanged===true,"saved_evaluator_completion");
  const expectedValidation={passed:true,issues:[],workers:16n,expected_workers:16n,timed_calls:66248n,expected_calls:66248n};
  check(same(summary.validation,expectedValidation),"saved_complete_validation");
  need(same(formal.gate,GATES),"Gate values changed");
  const ratios=comparisons.map(c=>c.candidate.latency.p95_ms/c.baseline.latency.p95_ms);
  need(ratios.every(r=>Number.isFinite(r)&&r>0),"Positive pooled p95 required");
  const geomean=100*(1-Math.exp(fmean(ratios.map(r=>Math.log(r)))));
  const pub=(id)=>-comparisons.find(c=>c.cohort==="public1015"&&c.id===id).candidate_change_percent.p95_ms;
  const publicNative=pub("native-char4000"),publicMcp=pub("mcp-char4000"),regressions=[];
  for(const c of comparisons)for(const metric of ["p50_ms","p95_ms"])
   if(c.candidate_change_percent[metric]>5+1e-9)regressions.push({cohort:c.cohort,config:c.id,metric,change_percent:c.candidate_change_percent[metric]});
  const passed=geomean>=10-1e-9&&publicNative>=10-1e-9&&publicMcp>=5-1e-9&&regressions.length===0;
  const numericAcceptance={numeric_gate_passed:passed,geometric_mean_p95_improvement_percent:geomean,
   public_native_char4000_p95_improvement_percent:publicNative,public_mcp_char4000_p95_improvement_percent:publicMcp,
   thresholds_percent:GATES,regressions_above_five_percent:regressions};
  compareNumbers(numericAcceptance,Object.fromEntries(Object.keys(numericAcceptance).map(k=>[k,summary.acceptance[k]])),"acceptance",issues,errors);
  return {schema_version:1n,status:issues.length?"formal_raw_audit_has_issues":"independently-recomputed-sixteen-workers-and-ledgers",
   calls,ledger_events:ledgerEvents,full_payload_pairs:paired,comparisons_against_first_row:comparedWithFirst,
   canonical_non_timing_rows:BigInt(canonical.size),issues,pair_mismatches:pairMismatches,cross_round_mismatches:crossRoundMismatches,
   comparisons,numeric_acceptance:numericAcceptance,numeric_declaration_comparison:errors,
   original_acceptance:summary.acceptance,resource_and_storage_independent_owner:"baseline_audit",
   resource_review_overridden:false,overall_release_acceptance:false,
   seeded_shuffle_reimplemented:false,retokenization_executed:false,retrieval_calls:0n,new_measurements:0n};
 }

 return {reassembleChunks,aggregate,unpackBytes,PIN,GATES,ENCODINGS,INVARIANTS,ROW_FIELDS,SESSION_FIELDS,same,number,units,roundedUnits,fsum,fmean,percentile,latency,numeric,
  histogram,mergeHistograms,histogramNumeric,compareNumbers,prepare,unpack,auditWorker};
};
