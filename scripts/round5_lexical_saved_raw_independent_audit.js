"use strict";
/* Read-only independent audit of existing lexical reports. No retrieval entry point.
 * Inputs are exact UTF-8 objects decoded from immutable Git gzip artifacts.
 * Binary transport uses the separately pinned pure SHA256/base64/pako helpers.
 * Python's seeded PRNG is not reimplemented: each complete registered ID set and
 * paired observed order are independently checked; exact seeded permutations
 * remain the separately preserved unchanged Python auditor's responsibility.
 */
const PIN = Object.freeze({
  result: "a15a5ce36079302de08c9c91dd6eb6896fd6bccc",
  workflow: "be5879400b2f05a250e97b00ce9b488f00413ccb",
  run: "43497150881",
  baseline: "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
  baselineRuntime: "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93",
  candidate: "4a0ad4dc6aec33a91231d419239b7e90b160c695",
  candidateRuntime: "77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32",
  binding: "fd189b2bdd4fd3647ff2fd2835ba21d5a27e36d43b1969efc42297459a9ac66b",
  intent: "28914f5eb73e4e0daaadce81ef730d53197920b7c99642846ff5581296eab71a",
  audit: "8384de7b04d92f521367bf277dc51b190ae78eb37f0de9d762d53d72a2640d35",
  dataset: "fb3cd70ea58fafa5bd9cef0f04dba7399aaafba76f5f92605eee9e516f115e1b",
  preparation: "337eefe4d90475f7577bd2b1a684b34e8672b69452f00d4eed3cc4ae8104f282",
  version: "round5-historical256-compatibility-1",
  root: "benchmarks/reports/round5-lexical-compat-hosted-1/"
});
function requireValue(condition, message) { if (!condition) throw new Error(message); }
function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") return "{" + Object.keys(value).sort().map(
    key => JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
  return JSON.stringify(value);
}
function equal(actual, expected, message) {
  requireValue(canonical(actual) === canonical(expected), message);
}
function integer(value, minimum, maximum, message) {
  requireValue(Number.isSafeInteger(value) && value >= minimum && value <= maximum, message);
}
function percentile(values, quantile) {
  const a = [...values].sort((a,b) => a-b), location = (a.length-1)*quantile;
  return a[Math.floor(location)] + (a[Math.ceil(location)]-a[Math.floor(location)]) *
    (location-Math.floor(location));
}
function stats(values) {
  requireValue(values.length > 0 && values.every(v => Number.isFinite(v) && v > 0), "Invalid timing sample");
  return {samples:values.length,mean_ms:values.reduce((a,b)=>a+b,0)/values.length,
    p50_ms:percentile(values,0.5),p95_ms:percentile(values,0.95)};
}
function closeNumbers(actual, expected, label) {
  if (typeof expected === "number") {
    requireValue(typeof actual === "number" && Number.isFinite(actual) &&
      Math.abs(actual-expected) <= 1e-10*Math.max(1,Math.abs(expected)), "Statistics differ: "+label);
  } else if (Array.isArray(expected)) {
    requireValue(Array.isArray(actual) && actual.length === expected.length, "Array differs: "+label);
    expected.forEach((v,i)=>closeNumbers(actual[i],v,label+"/"+i));
  } else if (expected && typeof expected === "object") {
    equal(Object.keys(actual).sort(),Object.keys(expected).sort(),"Object fields differ: "+label);
    Object.keys(expected).forEach(k=>closeNumbers(actual[k],expected[k],label+"/"+k));
  } else equal(actual,expected,"Value differs: "+label);
}
function auditLexical(input, api) {
  const hash = raw => api.sha256Bytes(api.utf8bytes(raw));
  const parse = key => JSON.parse(input.small[key]);
  for (const [key,pin] of [["binding",PIN.binding],["intent",PIN.intent],["summary",PIN.audit],
    ["preparation.json",PIN.preparation]]) requireValue(hash(input.small[key])===pin,"Pinned JSON differs: "+key);
  const binding=parse("binding"),intent=parse("intent"),saved=parse("summary"),
    prep=parse("preparation.json"),outcome=parse("workflow-outcome.json"),
    completed=parse("completion.json"),attempt=parse("attempt.intent.json"),
    environment=parse("source-environment.json");
  const sources={baseline:{commit:PIN.baseline,runtime_sha256:PIN.baselineRuntime},
    candidate:{commit:PIN.candidate,runtime_sha256:PIN.candidateRuntime}};
  equal(binding.sources,sources,"Bound sources differ");
  equal(intent.sources,sources,"Intent sources differ");
  requireValue(binding.version===PIN.version && binding.dataset_sha256===PIN.dataset &&
    binding.token_calls===3072 && binding.character_calls===2048,"Binding matrix differs");
  requireValue(Array.isArray(binding.ids) && binding.ids.length===256 &&
    new Set(binding.ids).size===256 && binding.ids.every(x=>typeof x==="string"&&x.length>0),"Invalid registered256 IDs");
  const ids=[...binding.ids].sort(),schedule=[
    {kind:"tokens",round:0,label:"baseline"},{kind:"tokens",round:0,label:"candidate"},
    ...[["baseline","candidate"],["candidate","baseline"],["candidate","baseline"],["baseline","candidate"]]
      .flatMap((labels,round)=>labels.map(label=>({kind:"char",round,label})))];
  equal(intent.schedule,schedule,"Fixed token/ABBA worker schedule differs");
  requireValue(intent.calls===5120 && intent.status==="registered-before-retrieval" &&
    intent.binding_sha256===PIN.binding && intent.preparation_sha256===PIN.preparation,"Intent boundary differs");
  requireValue(intent.host.github_run_id===PIN.run && intent.host.github_run_attempt==="1" &&
    intent.host.packages.tiktoken==="0.12.0","Run/tokenizer identity differs");
  equal(environment.environment.host,intent.host,"Saved environment host differs");
  equal(environment.environment.child_python_flags,
    {PYTHONDONTWRITEBYTECODE:"1",PYTHONHASHSEED:"0"},"Child flags differ");
  for(const label of ["baseline","candidate"]) {
    equal(environment.sources[label].identity,sources[label],"Source environment differs: "+label);
    requireValue(Object.keys(environment.sources[label].files_sha256).length===(label==="baseline"?17:18),
      "Source inventory size differs: "+label);
  }
  equal(environment.sources.candidate.files_sha256,attempt.selection.candidate_files_sha256,"Selected18 source inventory differs");
  requireValue(attempt.workflow_commit===PIN.workflow && attempt.run_id===PIN.run &&
    attempt.calls_expected===5120 && attempt.workers_expected===10 && attempt.fresh_rows_decoded===0 &&
    attempt.automatic_replay_permitted===false,"Launch attempt differs");
  requireValue(prep.status==="prepared" && prep.binding_sha256===PIN.binding &&
    prep.dataset_sha256===PIN.dataset && prep.pages===3953 && prep.database_bytes===33923072,"Preparation differs");
  equal(prep.source,sources.baseline,"Preparation source differs");
  const events=input.small["publication-events.jsonl"].trim().split("\n").map(x=>JSON.parse(x));
  let prior=null;
  events.forEach(event=>{
    requireValue(event.expected_previous===prior && event.local_parent===(prior||PIN.workflow) &&
      event.observed_remote===event.published_commit && /^[a-f0-9]{40}$/.test(event.published_commit),
      "Publication event chain differs");
    if(input.gitParents) equal(input.gitParents[event.published_commit],[event.local_parent],"Actual Git parent differs");
    prior=event.published_commit;
  });
  const workers={},observed=[],allMeta={},errorNames=["cache","chars","limit","metadata","policy","projection","scope","source","tokens"],
    rowNames=["configuration","context_chars","context_sha256","elapsed_ms","errors","payload_sha256","query_id","reference_tokens","result_count"];
  let calls=0,ledgerEvents=0,previousEnd=0;
  const orderedNames=schedule.map(x=>x.kind+"-r"+x.round+"-"+x.label+".json.gz");
  equal(Object.keys(input.reports).sort(),[...orderedNames].sort(),"Worker file matrix differs");
  for(const item of schedule) {
    const name=item.kind+"-r"+item.round+"-"+item.label+".json.gz",stem=name.slice(0,-8),
      entry=input.reports[name],report=JSON.parse(entry.raw),ledgerRaw=entry.ledgerRaw,
      ledger=ledgerRaw.trimEnd().split("\n").map(x=>JSON.parse(x)),
      exit=parse(stem+".exit.json"),remote=parse(stem+".remote-intent.json");
    const count=item.kind==="tokens"?1536:256;
    equal({kind:report.kind,round:report.round,label:report.label},item,"Worker identity differs: "+name);
    requireValue(report.version===PIN.version && report.status==="completed" &&
      report.binding_sha256===PIN.binding && report.intent_sha256===PIN.intent &&
      report.dataset_sha256===PIN.dataset,"Worker provenance differs: "+name);
    equal(report.source,sources[item.label],"Worker source differs: "+name);
    equal(report.host,intent.host,"Worker host differs: "+name);
    for(const key of ["started","finished","expected_calls"]) requireValue(report[key]===count,"Count differs: "+name+"/"+key);
    requireValue(report.rows.length===count && ledger.length===2*count && ledgerRaw.endsWith("\n"),"Rows/ledger incomplete: "+name);
    requireValue(report.originals_unchanged===true && report.index_unchanged===true &&
      report.recall_cache_rows===0 && report.source_text_exported===false,"Mutation/export/cache flag differs: "+name);
    integer(report.started_monotonic_ns,1,Number.MAX_SAFE_INTEGER,"Invalid start");
    integer(report.finished_monotonic_ns,report.started_monotonic_ns+1,Number.MAX_SAFE_INTEGER,"Invalid finish");
    requireValue(report.started_monotonic_ns>previousEnd,"Worker order overlaps");
    previousEnd=report.finished_monotonic_ns;
    requireValue(hash(ledgerRaw)===report.ledger_sha256,"Raw ledger hash differs");
    for(const [file,meta,raw] of [[name,entry.meta,entry.raw],
      [name+".attempts.jsonl.gz",entry.ledgerMeta,entry.ledgerRaw]]) {
      requireValue(hash(raw)===meta.raw_sha256 && api.utf8bytes(raw).length===meta.raw_bytes,"Decoded identity differs: "+file);
      const expected=exit.worker_storage.files[file],final=outcome.available_worker_storage[name].files[file],
        actual={bytes:meta.compressed_bytes,sha256:meta.compressed_sha256,
          uncompressed_bytes:meta.raw_bytes,uncompressed_sha256:meta.raw_sha256};
      equal(actual,expected,"Exit raw/compressed storage differs: "+file);
      equal(actual,final,"Outcome raw/compressed storage differs: "+file);
      allMeta[file]=meta;
    }
    requireValue(entry.meta.compressed_sha256===saved.files[name] &&
      exit.outputs_sha256[PIN.root+name]===entry.meta.compressed_sha256,"Saved compressed report differs: "+name);
    requireValue(exit.returncode===0 && exit.error===null && exit.replay_permitted===false,"Nonzero/replayed exit: "+name);
    requireValue(remote.status==="started-before-launch" && remote.binding_sha256===PIN.binding &&
      remote.replay_permitted===false,"Remote intent differs: "+name);
    equal(remote.child_python_flags,{PYTHONDONTWRITEBYTECODE:"1",PYTHONHASHSEED:"0"},"Remote child flags differ");
    const args=remote.argv;
    requireValue(args[1]==="-B" && args[2]==="scripts/round5_compatibility.py" && args[3]==="worker",
      "Unexpected worker command");
    for(const [option,value] of [["--kind",item.kind],["--label",item.label],["--round",String(item.round)]])
      requireValue(args[args.indexOf(option)+1]===value,"Worker argument differs: "+option);
    const claim=events.filter(e=>e.message==="bench: claim historical lexical "+stem),
      done=events.filter(e=>e.message==="bench: preserve historical lexical "+stem+" outcome");
    requireValue(claim.length===1 && done.length===1 && claim[0].expected_previous===remote.expected_publication_parent &&
      done[0].expected_previous===claim[0].published_commit,"Worker durable claim/outcome differs");
    requireValue(Date.parse(claim[0].at)<Date.parse(report.created_at) &&
      Date.parse(report.finished_at)<=Date.parse(exit.at) && Date.parse(exit.at)<=Date.parse(done[0].at),
      "Worker claim/measurement/outcome chronology differs");
    if(input.claimIntentHashes) requireValue(input.claimIntentHashes[stem]===hash(input.small[stem+".remote-intent.json"]),
      "Claim commit intent bytes differ");
    const configs=item.kind==="char"?[{budget_chars:100000}]:
      ["cl100k_base","o200k_base"].flatMap(tokenizer=>[512,1024,2048].map(budget_tokens=>
        ({budget_chars:8000,budget_tokens,tokenizer})));
    const perConfig=[];
    configs.forEach((config,ci)=>{
      const block=report.rows.slice(ci*256,(ci+1)*256);
      equal(block.map(row=>row.query_id).sort(),ids,"Incomplete/duplicate query set: "+name+"/"+ci);
      for(let j=0;j<block.length;j++) {
        const row=block[j],index=ci*256+j;
        equal(Object.keys(row).sort(),rowNames,"Unknown/missing row fields");
        equal(row.configuration,config,"Configuration order differs");
        equal(Object.keys(row.errors).sort(),errorNames,"Invariant names differ");
        Object.values(row.errors).forEach(value=>integer(value,0,0,"Recorded invariant failure"));
        for(const key of ["payload_sha256","context_sha256"]) requireValue(/^[a-f0-9]{64}$/.test(row[key]),"Invalid digest");
        equal(Object.keys(row.reference_tokens).sort(),["cl100k_base","o200k_base"],"Tokenizer names differ");
        Object.values(row.reference_tokens).forEach(value=>integer(value,0,Number.MAX_SAFE_INTEGER,"Invalid token count"));
        integer(row.context_chars,0,config.budget_chars,"Character cap exceeded");
        integer(row.result_count,0,5,"Result cap exceeded");
        if(config.budget_tokens) requireValue(row.reference_tokens[config.tokenizer]<=config.budget_tokens,"Token cap exceeded");
        requireValue(item.kind==="tokens"?row.elapsed_ms===null:Number.isFinite(row.elapsed_ms)&&row.elapsed_ms>0,
          "Invalid timing boundary");
        equal(ledger[2*index],{state:"started",query_id:row.query_id,configuration:config},"Started ledger differs");
        equal(ledger[2*index+1],{state:"finished",...row},"Finished ledger differs");
      }
      perConfig.push({configuration:config,calls:256,
        observed_query_order_sha256:hash(block.map(row=>row.query_id).join("\n")+"\n"),
        maximum_context_chars:Math.max(...block.map(row=>row.context_chars)),
        maximum_result_count:Math.max(...block.map(row=>row.result_count)),
        maximum_reference_tokens:Object.fromEntries(["cl100k_base","o200k_base"].map(enc=>
          [enc,Math.max(...block.map(row=>row.reference_tokens[enc]))]))});
    });
    workers[name]=report;
    observed.push({name,calls:count,ledger_events:ledger.length,
      started_monotonic_ns:report.started_monotonic_ns,finished_monotonic_ns:report.finished_monotonic_ns,
      durable_claim:claim[0].published_commit,durable_outcome:done[0].published_commit,configurations:perConfig});
    calls+=count;ledgerEvents+=ledger.length;
  }
  let pairs=0;
  for(const [kind,round] of [["tokens",0],["char",0],["char",1],["char",2],["char",3]]) {
    const a=workers[kind+"-r"+round+"-baseline.json.gz"].rows,b=workers[kind+"-r"+round+"-candidate.json.gz"].rows;
    for(let i=0;i<a.length;i++) {
      const {elapsed_ms:leftElapsed,...left}=a[i],{elapsed_ms:rightElapsed,...right}=b[i];
      equal(left,right,"Paired full saved payload/reference fields differ: "+kind+"/"+round+"/"+i);
      pairs++;
    }
  }
  requireValue(calls===5120&&pairs===2560&&ledgerEvents===10240,"Incomplete total matrix");
  const rounds=[0,1,2,3].map(round=>({round,...Object.fromEntries(["baseline","candidate"].map(label=>
    [label,stats(workers["char-r"+round+"-"+label+".json.gz"].rows.map(row=>row.elapsed_ms))]))})),
    pooled=Object.fromEntries(["baseline","candidate"].map(label=>[label,stats([0,1,2,3].flatMap(round=>
      workers["char-r"+round+"-"+label+".json.gz"].rows.map(row=>row.elapsed_ms)))])),
    changes=Object.fromEntries(["p50_ms","p95_ms"].map(key=>[key,100*(pooled.candidate[key]/pooled.baseline[key]-1)]));
  const diagnostic={calls:2048,pooled,rounds,candidate_change_percent:changes,
    nonregression_gate_passed:Object.values(changes).every(v=>v<=5+1e-9)};
  closeNumbers(diagnostic,saved.character_diagnostic,"saved-character-diagnostic");
  requireValue(saved.status==="verified" && saved.accepted===diagnostic.nonregression_gate_passed &&
    saved.calls===calls&&saved.complete_payload_pairs===pairs&&saved.workers===10&&saved.retrieval_calls_during_audit===0,
    "Saved summary differs");
  requireValue(completed.status==="completed"&&completed.calls===calls&&completed.complete_payload_pairs===pairs&&completed.workers===10&&
    completed.fresh_rows_decoded===0&&outcome.outcome==="success"&&outcome.retrieval_calls_during_preservation===0&&
    outcome.replay_permitted===false,"Final completion differs");
  return {schema_version:1,status:"independently-verified-complete-historical-lexical-raw-matrix",
    result_commit:PIN.result,workflow_commit:PIN.workflow,run_id:PIN.run,sources,
    binding_sha256:PIN.binding,intent_sha256:PIN.intent,original_audit_sha256:PIN.audit,
    dataset_sha256:PIN.dataset,calls,pairs,workers:10,ledger_events:ledgerEvents,
    token_calls:3072,character_calls:2048,full_saved_payload_pairs_equal:pairs,
    raw_compressed_files:allMeta,worker_details:observed,character_diagnostic:diagnostic,
    adverse_round_p95:rounds.filter(r=>r.candidate.p95_ms>r.baseline.p95_ms).map(r=>({
      round:r.round,candidate_change_percent:100*(r.candidate.p95_ms/r.baseline.p95_ms-1)})),
    actual_git_publication_parents_verified:Boolean(input.gitParents),
    claim_commit_intent_bytes_verified:Boolean(input.claimIntentHashes),
    publication_events:events.length,host:intent.host,
    limits:[
      "No retrieval, model, tokenizer or dataset decoding was executed by this audit.",
      "Complete payload digests and saved context/reference metadata are compared; corpus plaintext and unsaved response objects were not reconstructed.",
      "The full registered256 ID set, every configuration and paired observed order are independently verified. Exact Python seeded shuffle permutations are checked by the unchanged original auditor, not independently reimplemented here.",
      "Recorded source/projection errors are all zero and source/index/cache immutability flags are verified; the absent SQLite files and original source spans are not reconstructed.",
      "The character100000 result is its registered separate nonregression diagnostic, not a pooled formal14-cell or fresh quality result."
    ],retrieval_calls_executed_by_audit:0,fresh_metadata_or_content_reads:0,formal_accepted:false,release_accepted:false};
}
module.exports={PIN,canonical,percentile,stats,auditLexical};
