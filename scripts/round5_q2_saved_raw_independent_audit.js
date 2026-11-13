"use strict";
/* Pure saved Q2 validation. No I/O, product import, model, tokenizer or query.
 * Pass pinned core bytes/hash helpers and makeSqlAudit(core)'s parse/stringify API.
 * Report integer fields stay BigInt, preserving Python's strict integer contract.
 */
module.exports = function makeQ2RawAudit(core, exact) {
 const PIN={
  workflow:"c23c5d5c9e1b8521ed78bf28e34896bc0755ee86",run:"43505846977",
  attempt:"round5-q2-recovery-hosted-2",root:"benchmarks/reports/round5-q2-recovery-hosted-2/",
  scope:"fc7a0f53b371ffdf6039ce0d171c70f152ce0eb66a2d5a28ba94d32b8ba589c9",
  sourceBinding:"c6ae40b490a7e8358c1709dbb7e6a5999bf6756ef37c66da55488d3539e57828",
  baseline:"692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
  baselineRuntime:"179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93",
  candidate:"4a0ad4dc6aec33a91231d419239b7e90b160c695",
  candidateRuntime:"77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32",
  builder:"7b7a5d7336b9350a128f5e0a888811b1b3015e68",
  builderRuntime:"9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46",
  historical:"43b65c004e1ac1f1d75cf6d1a2421b36e4eab740",
  oldRoot:"benchmarks/reports/round4-compatibility-final/",
  oldPaired:"5e5bffde4729250169e8eb92f1d14088c46c9c57aef1e22be2f52ceafb4593d6",
  oldPreparations:{authored36:"0fb2e417f465fd4748d35a327aaa928f58ae40a3eb9d07d884b5d1ca1bd3e5a9",
   hotpot128:"e16ec2b31633fff438971e48fd4dd7394442018ce16d82d33df4808e684739d5"},
  controllerFiles:{
   "scripts/round5_q2_hosted_recovery_v2.py":"8873d8a20965f6914da5db25bbd6401f5195c0e72281bf0dfb88cd9d57c52b19",
   "tests/test_round5_q2_hosted_recovery_v2.py":"678f23f7f6efc604c6aed728f9b9a7a40fc340d861d051ab2d0c0a2c5318dfe2",
   ".github/workflows/round5-q2-recovery-hosted-v2.yml":"fd7ffb0bbe144f261b96960fe0309fe83ac382803ba293c3d3da7355b6e18944",
   "benchmarks/experiments/round5-q2-recovery-hosted-v2-scope.json":"fc7a0f53b371ffdf6039ce0d171c70f152ce0eb66a2d5a28ba94d32b8ba589c9",
   "benchmarks/experiments/round5-q2-recovery-hosted-scope.json":"f893b6197a1c81e93841dbfe8212cf2f1657e24cc1525123966e5b1cb3554b1e",
   "benchmarks/experiments/round5-q2-recovery-source.json":"c6ae40b490a7e8358c1709dbb7e6a5999bf6756ef37c66da55488d3539e57828"}
 };
 const cohorts=["authored36","hotpot128"],encoders=["cl100k_base","o200k_base"],budgets=[512n,1024n,2048n];
 function check(v,m){if(!v)throw new Error(m);}
 function sha(raw){return core.sha256Bytes(core.utf8bytes(raw));}
 function parse(raw){check(typeof raw==="string","Expected exact JSON text");return exact.parseExact(raw);}
 function canon(v){
  if(typeof v==="bigint")return "integer:"+v.toString();
  if(typeof v==="number"){check(Number.isFinite(v),"Nonfinite value");return "float:"+String(v);}
  if(Array.isArray(v))return "array:["+v.map(canon).join(",")+"]";
  if(v&&typeof v==="object")return "object:{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canon(v[k])).join(",")+"}";
  return JSON.stringify(v);
 }
 function same(a,b,m){check(canon(a)===canon(b),m);}
 function keys(value,expected,m){same(Object.keys(value).sort(),[...expected].sort(),m);}
 function integer(v,min,max,m){check(typeof v==="bigint"&&v>=min&&v<=max,m);}
 function hex(v,m){check(typeof v==="string"&&/^[a-f0-9]{64}$/.test(v),m);}
 function pinned(raw,pin,name){check(sha(raw)===pin,"Pinned JSON differs: "+name);return parse(raw);}
 function schedule(){return cohorts.flatMap(cohort=>encoders.flatMap(encoder=>
  ["baseline","candidate"].map(label=>({cohort,encoder,label})))).map((v,i)=>
   ({index:BigInt(i+1),id:String(i+1).padStart(2,"0")+"-"+v.cohort+"-"+v.encoder+"-"+v.label,...v}));}
 function settings(encoder){return{semantic:true,coverage:false,budget_chars:8000n,token_budgets:budgets,
  tokenizer:encoder,limit:5n,cache_size:0n,use_cache:false,repetitions:1n};}
 function expectedReport(binding,worker,historical){
  const c=binding.cohorts[worker.cohort];
  return{cohort:worker.cohort,label:historical?"candidate":worker.label,
   runtime_sha256:historical?PIN.baselineRuntime:binding.sources[worker.label].runtime_sha256,
   dataset_sha256:c.dataset_sha256,evaluator_files:binding.old_evaluator_files,
   preparation_sha256:c.preparation_sha256,ort_disable_telemetry:"1",model:binding.model,
   configured_generative_model_calls:0n,expected_calls:BigInt(c.query_ids.length)*3n,
   settings:settings(worker.encoder),originals_sha256:c.originals_sha256,vectors:c.vectors,
   interpretation:"Previously-scored regression compatibility only; no timing claim."};
 }
 function validateReport(raw,ledgerRaw,expected,ids){
  const r=parse(raw),n=ids.length*3;
  check(new Set(ids).size===ids.length&&ids.every(x=>typeof x==="string"&&x),"Invalid registered query IDs");
  const fixed={...expected,status:"completed",attempts_started:BigInt(n),attempts_finished:BigInt(n)};
  keys(r,[...Object.keys(fixed),"rows","ledger_sha256"],"Unexpected report fields");
  for(const k of Object.keys(fixed))same(r[k],fixed[k],"Report identity/settings differ: "+k);
  for(const k of ["expected_calls","attempts_started","attempts_finished","configured_generative_model_calls"])
   integer(r[k],0n,BigInt(n),"Non-integer report count: "+k);
  check(sha(ledgerRaw)===r.ledger_sha256,"Raw ledger SHA differs");
  check(ledgerRaw.endsWith("\n"),"Truncated ledger");
  const lines=ledgerRaw.slice(0,-1).split("\n");
  check(Array.isArray(r.rows)&&r.rows.length===n&&lines.length===n*2,"Incomplete rows/ledger");
  for(let i=0;i<n;i++){
   const row=r.rows[i],id=ids[i%ids.length],budget=budgets[Math.floor(i/ids.length)];
   keys(row,["query_id","budget_tokens","payload_sha256","context_sha256","errors"],"Unexpected row fields");
   check(row.query_id===id&&row.budget_tokens===budget,"Missing/duplicate/reordered query-budget row");
   keys(row.errors,["source","projection","scope","token","metadata"],"Unexpected invariant counters");
   Object.values(row.errors).forEach(v=>integer(v,0n,0n,"Invariant errors or invalid integer counter"));
   hex(row.payload_sha256,"Invalid payload digest");hex(row.context_sha256,"Invalid context digest");
   same(parse(lines[2*i]),{state:"started",query_id:id,budget_tokens:budget},"Ledger start differs");
   same(parse(lines[2*i+1]),{state:"finished",...row},"Ledger finish differs");
  }
  return r.rows;
 }
 function compareRows(left,right,label){
  check(left.length===right.length,"Pair count differs: "+label);
  left.forEach((row,i)=>same(row,right[i],"Full payload/context/identity differs: "+label+"/"+i));
  return left.length;
 }
 function decode(packet,compressedSHA,rawSHA,codec){
  const bytes=core.base64Bytes(packet.base64);check(core.sha256Bytes(bytes)===compressedSHA,"Compressed SHA differs");
  if(packet.bytes!==undefined)check(BigInt(bytes.length)===BigInt(packet.bytes),"Git directory byte count differs");
  const decoded=codec.ungzip(bytes),raw=core.strictUtf8(decoded),actualRawSHA=core.sha256Bytes(decoded);
  if(rawSHA!==undefined)check(actualRawSHA===rawSHA,"Decompressed SHA differs");
  return{raw,meta:{git_blob:packet.git_blob,compressed_bytes:bytes.length,compressed_sha256:compressedSHA,
   raw_bytes:decoded.length,raw_sha256:actualRawSHA}};
 }
 function database(actual,c,m){same(actual,{originals_sha256:c.originals_sha256,vectors:c.vectors,cache_rows:0n},m);}
 function checkInputs(input){
  const scope=pinned(input.scopeRaw,PIN.scope,"scope"),source=pinned(input.sourceBindingRaw,PIN.sourceBinding,"source binding"),
   old=pinned(input.oldPairedRaw,PIN.oldPaired,"historical paired manifest"),
   b=parse(input.small["binding.json"]),assets=parse(input.small["asset-binding.json"]),
   attempt=parse(input.small["attempt.intent.json"]),proof=parse(input.small["registered-helper-union.json"]);
  check(input.execution.run_id===PIN.run&&input.execution.workflow_commit===PIN.workflow&&
   /^[a-f0-9]{40}$/.test(input.execution.result_commit),"Actual execution identity required");
  check(b.schema_version===1n&&b.attempt===PIN.attempt&&b.workflow_commit===PIN.workflow&&
   b.run_id===PIN.run&&b.scope_sha256===PIN.scope&&b.source_binding_sha256===PIN.sourceBinding,"Binding identity differs");
  check(source.status==="frozen-before-q2-recovery"&&source.candidate==="NO"&&
   source.commit===PIN.candidate&&source.runtime_sha256===PIN.candidateRuntime,"Candidate binding differs");
  same(b.sources.candidate.files_sha256,source.files_sha256,"Complete candidate file inventory differs");
  for(const [label,commit,runtime]of [["baseline",PIN.baseline,PIN.baselineRuntime],
   ["candidate",PIN.candidate,PIN.candidateRuntime],["historical_builder",PIN.builder,PIN.builderRuntime]])
   check(b.sources[label].commit===commit&&b.sources[label].runtime_sha256===runtime,"Source identity differs: "+label);
  same(b.workers,schedule(),"Fixed8 worker order differs");same(b.model,scope.model,"Model identity differs");
  same(b.old_evaluator_files,scope.original_files.old_evaluator_sha256,"Original evaluator registry differs");
  same(b.historical.old_evaluator_files,b.old_evaluator_files,"Historical evaluator identity differs");
  same(b.historical.model,b.model,"Historical model identity differs");
  check(b.historical_reference_commit===PIN.historical&&b.calls===1968n&&b.complete_payload_pairs===984n&&
   b.fresh_rows_decoded===0n&&b.configured_generative_model_calls===0n&&b.performance_claim===false,"Matrix or claim boundary differs");
  const{cohorts:boundCohorts,...stable}=b;same(stable,assets,"Binding changed apart from adding prepared cohorts");
  check(proof.status==="verified-source-only-union"&&proof.scope_sha256===PIN.scope&&
   proof.source_binding_sha256===PIN.sourceBinding,"Actual union proof identity differs");
  same(proof.counts,{explicit_registry:11n,original_closure:34n,union:35n},"Union counts differ");
  same(proof.scope_only_paths,["scripts/round3_development_checks.py"],"Scope-only path differs");
  keys(proof.files,Object.keys(scope.strict_union_repair.expected_union_git_blobs),"Union keys differ");
  const helpers={...PIN.controllerFiles};
  for(const[name,pin]of Object.entries(scope.strict_union_repair.expected_union_git_blobs)){
   const actual=proof.files[name];check(actual.git_blob===pin,"Actual union Git blob differs: "+name);
   if(name in b.old_evaluator_files)check(actual.sha256===b.old_evaluator_files[name],"Registered SHA differs: "+name);
   hex(actual.sha256,"Invalid union digest");helpers[name]=actual.sha256;
  }
  same(b.helpers_sha256,helpers,"Frozen helper map differs");
  check(attempt.run_id===PIN.run&&attempt.run_attempt===1n&&attempt.workflow_commit===PIN.workflow&&
   attempt.attempt===PIN.attempt&&attempt.candidate_binding_sha256===PIN.sourceBinding&&
   attempt.registered_helper_union_sha256===sha(input.small["registered-helper-union.json"])&&
   attempt.calls_permitted===1968n&&attempt.pairs_expected===984n&&attempt.fresh_rows_decoded===0n,
   "Attempt intent differs");
  same(attempt.helpers_sha256,helpers,"Intent helper map differs");
  same(attempt.previous_failed_attempt,scope.previous_attempt,"Original failed attempt identity changed");
  same(attempt.historical,b.historical,"Historical binding changed after claim");
  keys(b.cohorts,cohorts,"Cohort matrix differs");
  const snapshots={};
  for(const cohort of cohorts){
   const reg=scope.cohorts[cohort],c=b.cohorts[cohort],historical=b.historical.cohorts[cohort],
    prior=pinned(input.oldPreparationRaw[cohort],PIN.oldPreparations[cohort],"old preparation/"+cohort),
    prepRaw=input.small["prepare-"+cohort+".json"],prep=parse(prepRaw),
    audit=parse(input.small["prepare-"+cohort+".audit.json"]),exit=parse(input.small["prepare-"+cohort+".exit.json"]);
   check(BigInt(c.query_ids.length)===reg.queries&&new Set(c.query_ids).size===c.query_ids.length,"Cohort ID set differs");
   same(c.query_ids,historical.query_ids,"Historical/current query order differs");
   check(c.dataset_sha256===reg.dataset_sha256&&historical.dataset_sha256===reg.dataset_sha256,"Dataset differs");
   check(historical.preparation_sha256===PIN.oldPreparations[cohort]&&
    historical.originals_sha256===reg.historical_originals_sha256,"Historical preparation identity differs");
   same(prior.vectors,reg.historical_vectors,"Original historical vectors differ");
   same(prior.model,scope.model,"Original model differs");
   check(prior.originals_sha256===reg.historical_originals_sha256&&prior.source_sha256===PIN.builderRuntime&&
    prior.dataset_sha256===reg.dataset_sha256&&prior.queries===reg.queries,"Original cohort provenance differs");
   check(c.preparation===PIN.root+"prepare-"+cohort+".json"&&c.preparation_sha256===sha(prepRaw)&&
    prep.source_sha256===PIN.builderRuntime&&prep.cohort===cohort&&prep.dataset_sha256===reg.dataset_sha256&&
    prep.queries===reg.queries&&prep.ort_disable_telemetry==="1","New preparation provenance differs");
   same(prep.evaluator_files,b.old_evaluator_files,"New preparation helper registry differs");
   same(prep.model,scope.model,"New preparation model differs");same(prep.vectors,reg.historical_vectors,"New vector identity differs");
   same(c.vectors,reg.historical_vectors,"Bound vector identity differs");
   check(prep.semantic_index.inference_threads===1n&&
    prep.semantic_index.model_fingerprint===reg.historical_vectors.model_fingerprint,"Builder threads/fingerprint differ");
   same(prep.semantic_index.runtime,Object.fromEntries(["onnxruntime","tokenizers","numpy"].map(k=>
    [k,scope.dependencies[k]])),"Builder runtime differs");
   check(c.originals_sha256===prep.originals_sha256&&c.historical_originals_sha256===reg.historical_originals_sha256,
    "New/historical originals accounting differs");
   hex(c.originals_sha256,"Invalid new originals SHA");hex(c.database_sha256,"Invalid new DB SHA");
   check(audit.status==="passed"&&audit.exact_historical_vectors===true&&audit.original_database_restored===false&&
    audit.timestamp_rewrite_permitted===false&&audit.new_database_sha256===c.database_sha256&&
    audit.new_database_bytes===c.database_bytes,"Preparation audit differs");
   database(audit.new_identity,c,"New prepared identity differs");
   check(exit.returncode===0n&&exit.error===null&&exit.available_file_sha256["prepare-"+cohort+".json"]===sha(prepRaw),
    "Preparation exit differs");
   snapshots[cohort]={new_originals_sha256:c.originals_sha256,new_database_sha256:c.database_sha256,
    new_database_bytes:c.database_bytes,historical_originals_sha256:reg.historical_originals_sha256,
    vectors:c.vectors,original_database_restored:false};
  }
  return{scope,source,b,old,snapshots};
 }
 function auditMatrix(input,codec){
  const{b,old,snapshots}=checkInputs(input),reference={},observed={},artifacts={},workers=[];
  let calls=0,pairs=0,historicalPairs=0,ledgerEvents=0,oldLedgerEvents=0;
  keys(input.currentPackets,schedule().map(w=>w.id),"Current worker packet matrix differs");
  keys(input.oldPackets,cohorts.flatMap(c=>encoders.map(e=>c+"/"+e)),"Old C2 packet matrix differs");
  const historic={cohorts:b.historical.cohorts,model:b.model,old_evaluator_files:b.old_evaluator_files};
  for(const w of schedule().filter(w=>w.label==="baseline")){
   const key=w.cohort+"/"+w.encoder,name=w.cohort+"-candidate-"+w.encoder+".json.gz",
    pins=b.historical.old_c2[key],packet=input.oldPackets[key];
   check(pins.report===PIN.oldRoot+name&&pins.ledger===PIN.oldRoot+name+".attempts.jsonl.gz"&&
    pins.report_sha256===old.file_sha256[name]&&pins.ledger_sha256===old.file_sha256[name+".attempts.jsonl.gz"]&&
    pins.ledger_raw_sha256===old.file_sha256[name+".attempts.jsonl"],"Historical C2 reference differs");
   const report=decode(packet.report,pins.report_sha256,pins.report_raw_sha256,codec),
    ledger=decode(packet.ledger,pins.ledger_sha256,pins.ledger_raw_sha256,codec);
   reference[key]=validateReport(report.raw,ledger.raw,expectedReport(historic,w,true),historic.cohorts[w.cohort].query_ids);
   artifacts[PIN.oldRoot+name]=report.meta;artifacts[PIN.oldRoot+name+".attempts.jsonl.gz"]=ledger.meta;
   oldLedgerEvents+=reference[key].length*2;
  }
  for(const w of schedule()){
   const c=b.cohorts[w.cohort],key=w.cohort+"/"+w.encoder,name=w.id+".json.gz",
    intent=parse(input.small[w.id+".intent.json"]),audit=parse(input.small[w.id+".audit.json"]),
    exit=parse(input.small[w.id+".exit.json"]),packet=input.currentPackets[w.id];
   same(intent.worker,w,"Worker intent differs");same(audit.worker,w,"Worker audit identity differs");
   check(intent.status==="started"&&intent.binding_sha256===sha(input.small["binding.json"])&&
    intent.expected_calls===BigInt(c.query_ids.length)*3n&&intent.new_source_database_sha256===c.database_sha256,
    "Worker source-copy binding differs");
   database(intent.worker_database_before,c,"Before-worker database identity differs");
   database(audit.worker_database_after,c,"After-worker database identity differs");
   check(audit.status==="passed"&&audit.full_payload_and_context_equal===true&&
    audit.comparator===(w.label==="baseline"?"saved historical v032 C2":"this attempt's baseline"),"Worker comparator/audit differs");
   check(exit.returncode===0n&&exit.error===null,"Incomplete worker exit");
   const report=decode(packet.report,audit.report_sha256,audit.report_raw_sha256,codec),
    ledger=decode(packet.ledger,audit.ledger_gzip_sha256,audit.ledger_raw_sha256,codec);
   check(exit.available_file_sha256[name]===report.meta.compressed_sha256&&
    exit.available_file_sha256[name+".attempts.jsonl.gz"]===ledger.meta.compressed_sha256&&
    exit.available_file_sha256[name+".attempts.jsonl"]===ledger.meta.raw_sha256,"Worker exit storage hashes differ");
   const rows=validateReport(report.raw,ledger.raw,expectedReport(b,w,false),c.query_ids);
   check(audit.calls===BigInt(rows.length),"Worker audit call count differs");
   if(w.label==="baseline"){historicalPairs+=compareRows(rows,reference[key],"baseline vs historical/"+key);observed[key]=rows;}
   else pairs+=compareRows(rows,observed[key],"candidate vs baseline/"+key);
   calls+=rows.length;ledgerEvents+=rows.length*2;
   artifacts[PIN.root+name]=report.meta;artifacts[PIN.root+name+".attempts.jsonl.gz"]=ledger.meta;
   workers.push({worker:w,calls:rows.length,ledger_events:rows.length*2,report_sha256:report.meta.compressed_sha256,
    ledger_raw_sha256:ledger.meta.raw_sha256,originals_sha256:c.originals_sha256,vector_sha256:c.vectors.sha256});
  }
  check(calls===1968&&pairs===984&&historicalPairs===984&&ledgerEvents===3936&&oldLedgerEvents===1968,"Incomplete full matrix");
  const completion=parse(input.small["completion.json"]),outcome=parse(input.small["workflow-outcome.json"]);
  check(completion.status==="completed"&&completion.attempt===PIN.attempt&&completion.calls===1968n&&
   completion.complete_payload_pairs===984n&&completion.baseline_calls_equal_to_saved_C2===984n&&
   completion.candidate_calls_equal_to_new_baseline===984n&&completion.all_invariant_errors===0n&&
   completion.both_new_persisted_vector_identities_equal_history===true&&completion.new_source_databases_unchanged===true&&
   completion.original_database_restored===false&&completion.fresh_rows_decoded===0n&&
   completion.configured_generative_model_calls===0n&&completion.performance_claim===false&&
   completion.formal_or_release_acceptance===false,"Completion claim differs");
  check(outcome.outcome==="success"&&outcome.run_id===PIN.run&&outcome.run_attempt==="1","Workflow outcome differs");
  return{status:"independently-verified-complete-Q2-saved-payload-matrix",execution:input.execution,
   calls,pairs,baseline_to_historical_C2_pairs:historicalPairs,ledger_events:ledgerEvents,
   historical_ledger_events:oldLedgerEvents,workers,snapshots,artifacts,
   binding_sha256:sha(input.small["binding.json"]),scope_sha256:PIN.scope,
   source_binding_sha256:PIN.sourceBinding,old_paired_manifest_sha256:PIN.oldPaired,
   retrieval_calls_executed_by_audit:0,fresh_metadata_or_content_reads:0,
   old_database_restored:false,performance_claim:false,formal_accepted:false,release_accepted:false,
   remaining_separate_check:"Actual Git ancestry and prelaunch intent/both-snapshot checkpoint ordering are checked from Git objects separately, not inferred from saved receipt flags."};
 }
 return{PIN,parse,stringify:exact.stringifyExact,sha,canon,same,schedule,settings,expectedReport,
  validateReport,compareRows,decode,checkInputs,auditMatrix};
};
