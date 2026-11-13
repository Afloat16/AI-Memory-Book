"use strict";
/* Standalone-cell adapter, authorized after whole-profile connector limits.
 * Pure function: callers supply immutable base64 and already-frozen text.
 */
module.exports=function auditSavedCell(core,api,input){
 const requireValue=(value,message)=>{if(!value)throw Error(message);};
 const eq=(a,b)=>api.digest(a)===api.digest(b);
 const i=input.index;requireValue(Number.isSafeInteger(i)&&i>=0&&i<8,"Cell index outside original inventory");
 const frozen=api.textArtifact("independent input receipt",input.input_receipt_text,
  "5e5c31fdaa0e1e1e431c9d7adfd7fc59398ac230893442fa6aab97cbd7fceade").value;
 const scope=api.textArtifact("scope",input.scope_text,api.PIN.scope).value;
 const old=api.textArtifact("original I binding",input.old_text,api.PIN.old).value;
 const manifest=api.textArtifact("C2 manifest",input.manifest_text,api.PIN.manifest).value;
 requireValue(frozen.result_commit==="f4a684233adee2da0e2b0c1c093a8b3f806561a7"&&
  frozen.run.id===43492432740n&&frozen.run.run_attempt===1n&&
  frozen.run.head_sha==="e1e56ac93dc4fdc63d1815c7d49894b8e0364093","Execution receipt differs");
 requireValue(eq(frozen.runtime,scope.runtime)&&eq(scope.payload_reference.cells,old.profile.baseline_cells)&&
  manifest.runtime_source_sha256===api.PIN.baselineRuntime&&manifest.script_sha256===api.PIN.helper&&
  manifest.status==="completed"&&manifest.expected_calls===4732n&&manifest.attempted_calls===4732n&&manifest.completed_calls===4732n,
  "Frozen runtime/reference provenance differs");
 const ref=old.profile.baseline_cells[i],m=manifest.cells[i],stored=frozen.cells[i];
 for(const field of ["cohort","configuration","bytes","sha256","uncompressed_sha256"])
  requireValue(m[field]===ref[field],"C2 manifest/reference mismatch");
 requireValue(ref.path==="benchmarks/reports/round4-development/"+m.path&&
  stored.ordinal===BigInt(i)&&stored.cell.path.endsWith("/"+ref.cohort+"-"+ref.configuration+".json.gz"),
  "Stored cell order/path differs");
 const codec=core.codecFromPinnedSource(input.pako_source);
 const candidateRead=api.unpack(stored.cell.path,input.cell_base64,stored.cell,codec);
 const baselineRead=api.unpack(ref.path,input.reference_base64,
  {bytes:ref.bytes,sha256:ref.sha256,raw_sha256:ref.uncompressed_sha256},codec);
 const candidate=api.parseExact(api.boundedUtf8(candidateRead.raw)),baseline=api.parseExact(api.boundedUtf8(baselineRead.raw));
 requireValue(!Object.hasOwn(candidate,"storage"),"Standalone cell has unexpected post-pack storage");
 const context={files:{...scope.runtime.files_sha256,[api.PIN.scriptPath]:api.PIN.producer},rules:scope.observer.source_mapping.rules};
 const audit=api.auditCell(candidate,baseline,[ref.cohort,ref.configuration],old.cohorts[ref.cohort],context,
  scope.sequence.configurations[i%4].recall_options);
 return {schema_version:1n,status:"independently-checked-primary-raw-cell",ordinal:BigInt(i),
  input_receipt_commit:"b2e3db563e30c32b78e5bb23df55d66b2c4fda9b",
  result_commit:frozen.result_commit,source_commit:api.PIN.source,runtime_sha256:api.PIN.runtime,
  producer_commit:api.PIN.producerCommit,producer_sha256:api.PIN.producer,scope_sha256:api.PIN.scope,
  audit_code_sha256:frozen.audit_implementation.sha256,original_binding_sha256:api.PIN.old,
  baseline_manifest_sha256:api.PIN.manifest,baseline_runtime_sha256:api.PIN.baselineRuntime,
  cell_artifact:{...candidateRead.identity,git_blob:stored.cell.git_blob},
  reference_artifact:{...baselineRead.identity,commit:api.PIN.reference},
  storage_receipt:stored.storage_receipt,audit,
  monolithic_profile_directly_verified:false,monolithic_cell_equivalence_claimed:false,
  source_of_spans:"Standalone stored cell gzip, whose raw and compressed sizes/SHA are independently checked.",
  retrieval_calls_executed:0n,new_measurements:0n,fresh_rows_decoded:0n,speed_claim:false};
};
