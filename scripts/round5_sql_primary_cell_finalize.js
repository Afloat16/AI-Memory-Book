"use strict";
/* Final assembly of already-published, SHA-pinned primary-cell receipts.
 * Original span/payload rules are in the pre-read auditor03f5. This assembler
 * performs no new reads and does not claim the unavailable whole gzip was read.
 */
module.exports=function finalizeSqlCells(core,api,input){
 const requireValue=(value,message)=>{if(!value)throw Error(message);};
 const eq=(a,b)=>api.digest(a)===api.digest(b);
 const frozenInput=api.textArtifact("input receipt",input.input_receipt_text,
  "5e5c31fdaa0e1e1e431c9d7adfd7fc59398ac230893442fa6aab97cbd7fceade").value;
 const scope=api.textArtifact("scope",input.scope_text,api.PIN.scope).value;
 const old=api.textArtifact("original binding",input.old_text,api.PIN.old).value;
 api.textArtifact("C2 manifest",input.manifest_text,api.PIN.manifest);
 requireValue(core.sha256Bytes(core.utf8bytes(input.producer_text))===api.PIN.producer,"Producer source differs");
 const metadata={};
 for(const key of ["source_binding","binding","storage","completion","payload_audit"])
  metadata[key]=api.textArtifact(key,input.metadata_text[key],frozenInput.metadata[key].sha256);
 const frozen=metadata.source_binding.value,binding=metadata.binding.value;
 const runtime={commit:api.PIN.source,runtime_sha256:api.PIN.runtime,files_sha256:scope.runtime.files_sha256};
 requireValue(frozen.status==="frozen-after-artificial-proof-before-sql-attribution-corpus"&&
  frozen.attempt==="round5-lm-sql-attribution-1"&&eq(frozen.runtime,runtime)&&
  frozen.scope_sha256===api.PIN.scope&&frozen.pairing_addendum_sha256===api.PIN.pairing&&
  frozen.classification_sha256===api.digest(scope.observer.source_mapping),"Frozen source/classification differs");
 requireValue(binding.attempt==="round5-lm-sql-attribution-1"&&eq(binding.runtime,runtime)&&
  binding.scope_sha256===api.PIN.scope&&binding.pairing_addendum_sha256===api.PIN.pairing&&binding.publisher_addendum_sha256===api.PIN.publisher&&
  binding.source_binding_sha256===metadata.source_binding.sha256&&binding.workflow_commit===frozenInput.run.head_sha&&
  String(binding.run_id)===String(frozenInput.run.id)&&binding.calls_expected===4732n&&
  binding.comparison_engine_calls===0n&&binding.fresh_rows_decoded===0n&&binding.speed_claim===false&&
  binding.locomo_sha256===scope.sequence.locomo_raw_sha256,"Actual source/run binding differs");
 const artifacts=binding.artifact_files_sha256;
 requireValue(artifacts[api.PIN.scriptPath]===api.PIN.producer&&
  artifacts["tests/test_round5_lm_sql_attribution.py"]==="ea6b96e06bd4766741b90a401951d21aeddc3a23e75d58e50e560a159af90dc5"&&
  artifacts[".github/workflows/round5-lm-sql-attribution.yml"]==="4b972bad02fb9fafd1e6885ca441fc9348def85db788db6ec3dfabf5afbcb343"&&
  eq(artifacts,frozen.artifact_files_sha256)&&eq(binding.helpers_sha256,old.helpers_sha256)&&
  eq(binding.helper_dependency_sha256,old.helper_dependency_sha256)&&
  eq(binding.profile_baseline_references.baseline_cells,old.profile.baseline_cells),"Producer/helper/reference closure differs");
 requireValue(input.cell_receipts.length===8,"Eight published cell receipts required");
 const cells=[],inventory=[],groups=new Map(),totals={
  queries:0n,spans:0n,recall_wall_ns_including_observer:0n,observed_exclusive_builtin_ns:0n,
  unattributed_wall_ns:0n,callback_bookkeeping_ns:0n,non_target_events:0n,native_candidate_fetchall:0n,
  fallback_candidate_fetchall:0n,wrapper_same:0n,wrapper_fresh:0n,events:{},target_events:{}};
 let previousSites=[];
 const context={files:{...scope.runtime.files_sha256,[api.PIN.scriptPath]:api.PIN.producer},rules:scope.observer.source_mapping.rules};
 for(let i=0;i<8;i++){
  const pinned=input.cell_receipts[i],read=api.textArtifact("cell receipt "+i,pinned.text,pinned.sha256),record=read.value;
  const spec=old.profile.baseline_cells[i],stored=frozenInput.cells[i],audit=record.audit;
  requireValue(record.status==="independently-checked-primary-raw-cell"&&record.ordinal===BigInt(i)&&
   record.result_commit===frozenInput.result_commit&&record.source_commit===api.PIN.source&&record.runtime_sha256===api.PIN.runtime&&
   record.producer_sha256===api.PIN.producer&&record.scope_sha256===api.PIN.scope&&
   record.audit_code_sha256==="5970f90c6b19df2bf9711c3f5de7f9cae65dac7613e85144c680f9001ba59a01"&&
   record.reader_adapter_sha256==="4ef43c5167c295ad6441380da6d779258523e4557b0503b6756d4c9739935349",
   "Cell proof source differs");
  requireValue(record.monolithic_profile_directly_verified===false&&record.monolithic_cell_equivalence_claimed===false&&
   record.retrieval_calls_executed===0n&&record.new_measurements===0n&&record.fresh_rows_decoded===0n&&record.speed_claim===false,
   "Cell evidence boundary changed");
  for(const field of ["bytes","sha256","raw_bytes","raw_sha256","git_blob"])
   requireValue(record.cell_artifact[field]===stored.cell[field],"Cell primary artifact differs");
  requireValue(record.reference_artifact.commit===api.PIN.reference&&record.reference_artifact.bytes===spec.bytes&&
   record.reference_artifact.sha256===spec.sha256&&record.reference_artifact.raw_sha256===spec.uncompressed_sha256,
   "C2 raw identity differs");
  const expected=old.cohorts[spec.cohort];
  requireValue(audit.cohort===spec.cohort&&audit.configuration===spec.configuration&&audit.dataset_sha256===expected.dataset_sha256&&
   audit.query_order_sha256===expected.profile_query_order_sha256&&
   audit.query_universe_sorted_ids_sha256===expected.query_universe_sorted_ids_sha256&&audit.totals.queries===expected.queries&&
   audit.payload_audit.queries===expected.queries&&audit.callsite_summary_recomputed_equal===true,"Complete cell schedule/summary differs");
  api.validateSites(audit.stored_sites,context);
  requireValue(audit.stored_sites.length>=previousSites.length&&
   previousSites.every((site,index)=>eq(site,audit.stored_sites[index])),"Persistent source catalog changed previous site identities");
  previousSites=audit.stored_sites;
  for(const [key,value] of Object.entries(audit.totals)){
   if(key==="events"||key==="target_events"){
    for(const [event,n] of Object.entries(value)){requireValue(typeof n==="bigint"&&n>=0n,"Invalid event total");totals[key][event]=(totals[key][event]||0n)+n;}
   }else{requireValue(typeof value==="bigint"&&value>=0n&&Object.hasOwn(totals,key),"Invalid cell total");totals[key]+=value;}
  }
  for(const group of audit.categories){
   if(!groups.has(group.category))groups.set(group.category,{category:group.category,calls:0n,returned:0n,exceptions:0n,open:0n,inclusive_ns:0n,exclusive_ns:0n});
   const sum=groups.get(group.category);
   for(const key of ["calls","returned","exceptions","open","inclusive_ns","exclusive_ns"]){requireValue(typeof group[key]==="bigint"&&group[key]>=0n,"Invalid category aggregate");sum[key]+=group[key];}
  }
  cells.push(record);inventory.push({ordinal:BigInt(i),commit:pinned.commit,path:pinned.path,bytes:read.bytes,sha256:read.sha256});
 }
 requireValue(totals.queries===4732n&&totals.observed_exclusive_builtin_ns+totals.unattributed_wall_ns===totals.recall_wall_ns_including_observer,
  "Complete accounting differs");
 const categories=[...groups.values()];
 requireValue(categories.reduce((n,g)=>n+g.calls,0n)===totals.spans&&
  categories.reduce((n,g)=>n+g.exclusive_ns,0n)===totals.observed_exclusive_builtin_ns,"Global category totals differ");
 const payloadCells=cells.map(c=>c.audit.payload_audit),mismatches=payloadCells.flatMap(c=>c.mismatches);
 const payload={attempt:"round5-lm-sql-attribution-1",calls:4732n,cells:payloadCells,mismatches,
  all_full_non_timing_payloads_equal_to_v032_c2:mismatches.length===0,
  all_classification_sites_valid:payloadCells.every(c=>c.all_classification_sites_valid),
  retrieval_calls_executed_by_audit:0n,speed_claim:false,fresh_rows_decoded:0n};
 requireValue(eq(payload,metadata.payload_audit.value),"Saved complete payload/classification audit differs from raw-derived eight cells");
 const complete=metadata.completion.value;
 requireValue(complete.status==="completed"&&complete.attempt==="round5-lm-sql-attribution-1"&&
  complete.calls===4732n&&complete.complete_cells===8n&&complete.all_full_payloads_equal===payload.all_full_non_timing_payloads_equal_to_v032_c2&&
  complete.all_classification_sites_valid===payload.all_classification_sites_valid&&complete.fresh_rows_decoded===0n&&
  complete.comparison_engine_calls===0n&&complete.speed_claim===false&&complete.formal_or_release_acceptance===false,
  "Saved completion differs from independently checked primary cells");
 return {schema_version:1n,status:payload.all_full_non_timing_payloads_equal_to_v032_c2&&payload.all_classification_sites_valid?
  "independently-verified-eight-primary-raw-cells-with-monolithic-transport-limit":"primary-cell-payload-or-classification-invalid",
  input_receipt:{commit:"b2e3db563e30c32b78e5bb23df55d66b2c4fda9b",path:"benchmarks/reports/round5-lm-sql-attribution-1/independent-input-receipt.json",
   sha256:"5e5c31fdaa0e1e1e431c9d7adfd7fc59398ac230893442fa6aab97cbd7fceade"},
  result_commit:frozenInput.result_commit,run:frozenInput.run,producer:frozenInput.producer,runtime,
  original_binding:frozenInput.original_binding,helpers:binding.helpers_sha256,helper_dependencies:binding.helper_dependency_sha256,
  scope_sha256:api.PIN.scope,classification_sha256:frozen.classification_sha256,
  reference_commit:api.PIN.reference,baseline_manifest_sha256:api.PIN.manifest,baseline_runtime_sha256:api.PIN.baselineRuntime,
  sequence:scope.sequence,cohorts:old.cohorts,environment:binding.environment,
  metadata:Object.fromEntries(Object.entries(metadata).map(([key,{value,...identity}])=>[key,identity])),
  monolithic_profile:{expected_storage:metadata.storage.value,git_blob:frozenInput.profile.git_blob,
   compressed_bytes_independently_verified:false,raw_bytes_independently_verified:false,
   canonical_equivalence_with_primary_cells_claimed:false,
   transport_record:{commit:"000bce6ed719589949afe3ece7c7f0272d83dec8",path:"benchmarks/reports/round5-lm-sql-attribution-1/independent-transport-and-primary-cell-adapter.json"}},
  cell_receipt_inventory:inventory,cells,global_totals:totals,global_categories:categories,
  all4732_full_non_timing_payload_digests_equal_to_v032_c2:payload.all_full_non_timing_payloads_equal_to_v032_c2,
  all_classification_sites_valid:payload.all_classification_sites_valid,mismatches,
  total_exception_spans:BigInt(cells.reduce((n,c)=>n+c.audit.exceptions.length,0)),
  full_saved_payload_audit_recomputed_equal:true,full_saved_completion_reconciled:true,
  integer_encoding:"Every nanosecond/count was parsed and summed with BigInt; exact JSON integer tokens are preserved.",
  evidence_scope:"All eight standalone primary-cell gzip files and eight original C2 references were independently read, raw/compressed hash checked, and fully audited. The inaccessible monolithic copy was not independently read or proven equal.",
  interpretation:"Partial instrumented native builtin boundaries only. Inclusive nesting may overlap. Exclusive spans still include callbacks, scheduling and observer effects. Residual is unattributed, never Python-only. Callback bookkeeping is separate and never subtracted. No comparison of these diagnostic times with uninstrumented engine performance.",
  retrieval_calls_executed_by_audit:0n,new_measurements:0n,fresh_rows_decoded:0n,speed_claim:false,formal_or_release_acceptance:false};
};
