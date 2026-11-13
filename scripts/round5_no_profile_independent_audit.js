/* Independent NO profile audit. Pure data functions: no files, network,
 * subprocesses, imports of memory_book, benchmark execution, or triggers.
 * CommonJS module; the exact upstream pako source is hash-checked before use.
 * Invoke only after a separate immutable input receipt pins actual results.
 */
"use strict";

function utf8bytes(text) {
 const out=[];for(const ch of text){const cp=ch.codePointAt(0);if(cp<128)out.push(cp);else if(cp<2048)out.push(192|(cp>>6),128|(cp&63));else if(cp<65536)out.push(224|(cp>>12),128|((cp>>6)&63),128|(cp&63));else out.push(240|(cp>>18),128|((cp>>12)&63),128|((cp>>6)&63),128|(cp&63));}return Uint8Array.from(out);
}
function b64bytes(text){const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";const map=Object.fromEntries([...alphabet].map((x,i)=>[x,i]));const out=[];let acc=0,bits=0;for(const c of text){if(c==="=")break;if(!(c in map))continue;acc=(acc<<6)|map[c];bits+=6;if(bits>=8){bits-=8;out.push((acc>>bits)&255);}}return Uint8Array.from(out);}
function sha256Bytes(input) {
 const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
 const len=input.length,size=Math.ceil((len+9)/64)*64,data=new Uint8Array(size);data.set(input);data[len]=128;const dv=new DataView(data.buffer),bits=len*8;dv.setUint32(size-8,Math.floor(bits/4294967296));dv.setUint32(size-4,bits>>>0);
 const w=new Uint32Array(64),R=(x,n)=>(x>>>n)|(x<<(32-n));
 for(let off=0;off<size;off+=64){for(let i=0;i<16;i++)w[i]=dv.getUint32(off+4*i);for(let i=16;i<64;i++){const x=w[i-15],y=w[i-2],s0=R(x,7)^R(x,18)^(x>>>3),s1=R(y,17)^R(y,19)^(y>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;}let[a,b,c,d,e,f,g,h]=H;for(let i=0;i<64;i++){const S1=R(e,6)^R(e,11)^R(e,25),ch=(e&f)^(~e&g),t1=(h+S1+ch+K[i]+w[i])>>>0,S0=R(a,2)^R(a,13)^R(a,22),maj=(a&b)^(a&c)^(b&c),t2=(S0+maj)>>>0;h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}[a,b,c,d,e,f,g,h].forEach((x,i)=>H[i]=(H[i]+x)>>>0);}
 return H.map(x=>x.toString(16).padStart(8,"0")).join("");
}
const PIN = Object.freeze({
 scope: "efc5badce593308cf58a623f31053f0b6ccb4151885fff0759c6c21ca160f6ad",
 old: "02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5",
 manifest: "4e1b098f32a89c7c8363c8ee67e02af54bb438965a72e773ec0ef199fb2cca00",
 helper: "593b9f0667b1fc1cb3e38f5cc8411620759bc5abae68c56816221b950f99a416",
 pako: "fa226c8e1e3556993260e6a5c1fe94e225da59b3418a06811fdc51d308f8bb43",
 source: "4a0ad4dc6aec33a91231d419239b7e90b160c695",
 runtime: "77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32",
 baseline: "692fb959ddf8934c5f516ba3d74ceb4385a2fa82",
 baselineRuntime: "179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93",
 reference: "761eaf5c9ca47c93dea25f73104eb259304df68a",
 scopeCommit: "2181b3ae500392ab75f323682750e3d22e385de7"
});
const HEX = /^[0-9a-f]{64}$/;
const COMMIT = /^[0-9a-f]{40}$/;
function requireValue(ok, message) { if (!ok) throw new Error(message); }
function same(a, b) {
 if (a === b) return true;
 if (a === null || b === null || typeof a !== typeof b) return false;
 if (Array.isArray(a) || Array.isArray(b))
  return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v,i)=>same(v,b[i]));
 if (typeof a !== "object") return false;
 const ak=Object.keys(a).sort(), bk=Object.keys(b).sort();
 return same(ak,bk) && ak.every(k=>same(a[k],b[k]));
}
function strictUtf8(bytes) {
 requireValue(bytes instanceof Uint8Array, "Expected exact bytes");
 const output=[];
 for(let i=0;i<bytes.length;) {
  const a=bytes[i++]; let cp, remaining, minimum;
  if(a<128) {output.push(String.fromCharCode(a));continue;}
  if(a>=194&&a<=223) {cp=a&31;remaining=1;minimum=128;}
  else if(a>=224&&a<=239) {cp=a&15;remaining=2;minimum=2048;}
  else if(a>=240&&a<=244) {cp=a&7;remaining=3;minimum=65536;}
  else throw new Error("Invalid UTF-8 leading byte");
  requireValue(i+remaining<=bytes.length, "Truncated UTF-8");
  for(let n=0;n<remaining;n++){const b=bytes[i++];requireValue(b>=128&&b<=191,"Invalid UTF-8 continuation");cp=(cp<<6)|(b&63);}
  requireValue(cp>=minimum&&cp<=1114111&&!(cp>=55296&&cp<=57343),"Noncanonical UTF-8 scalar");
  output.push(String.fromCodePoint(cp));
 }
 return output.join("");
}
function base64Bytes(value) {
 requireValue(typeof value==="string","Binary input must be fetched with encoding=base64");
 const compact=value.replace(/[\t\n\r ]/g,"");
 requireValue(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(compact),
  "Malformed base64 binary transport");
 return b64bytes(compact);
}
function checkedText(label,text,expected) {
 requireValue(typeof text==="string" && HEX.test(expected),"Missing pinned text "+label);
 const bytes=utf8bytes(text);
 requireValue(strictUtf8(bytes)===text,"Text is not exact scalar UTF-8 "+label);
 const actual=sha256Bytes(bytes);
 requireValue(actual===expected,"Text SHA mismatch "+label);
 return {label,bytes:bytes.length,sha256:actual,value:JSON.parse(text)};
}
function codecFromPinnedSource(source) {
 requireValue(typeof source==="string" && sha256Bytes(utf8bytes(source))===PIN.pako,"Pako source identity changed");
 const m={exports:{}};
 new Function("exports","module",source)(m.exports,m);
 requireValue(typeof m.exports.ungzip==="function","Pinned pako missing ungzip");
 return m.exports;
}
function checkedGzip(label,encoded,spec,codec) {
 requireValue(spec && Number.isSafeInteger(spec.bytes) && spec.bytes>0 &&
  HEX.test(spec.sha256) && HEX.test(spec.uncompressed_sha256),"Missing gzip identity "+label);
 const compressed=base64Bytes(encoded);
 requireValue(compressed.length===spec.bytes,"Compressed size mismatch "+label);
 const compressedSha=sha256Bytes(compressed);
 requireValue(compressedSha===spec.sha256,"Compressed SHA mismatch "+label);
 requireValue(compressed[0]===31&&compressed[1]===139,"Not gzip "+label);
 const raw=codec.ungzip(compressed);
 requireValue(raw instanceof Uint8Array,"Codec did not return exact bytes");
 const rawSha=sha256Bytes(raw);
 requireValue(rawSha===spec.uncompressed_sha256,"Raw SHA mismatch "+label);
 if(spec.uncompressed_bytes!==undefined)
  requireValue(raw.length===spec.uncompressed_bytes,"Raw size mismatch "+label);
 return {label,compressed_bytes:compressed.length,compressed_sha256:compressedSha,
  uncompressed_bytes:raw.length,uncompressed_sha256:rawSha,
  value:JSON.parse(strictUtf8(raw))};
}
function orderedIdSha(ids) {
 requireValue(Array.isArray(ids) && ids.every(x=>typeof x==="string" && /^[\x00-\x7f]*$/.test(x)),
  "Frozen IDs must remain ASCII strings for exact Python JSON encoding");
 return sha256Bytes(utf8bytes(JSON.stringify(ids)));
}
function validateCell(cell,axis,cohort,label) {
 requireValue(cell && cell.status==="completed" && cell.cohort===axis[0] &&
  cell.configuration===axis[1],label+" cell status or axis differs");
 requireValue(cell.dataset_sha256===cohort.dataset_sha256,label+" dataset differs");
 requireValue(cell.queries===cohort.queries && Array.isArray(cell.rows) &&
  cell.rows.length===cohort.queries,label+" row count differs");
 const ids=cell.rows.map(row=>{
  requireValue(row && same(Object.keys(row).sort(),["non_timing_payload_sha256","query_id"]) &&
   typeof row.query_id==="string" && HEX.test(row.non_timing_payload_sha256),
   label+" malformed full-payload row");
  return row.query_id;
 });
 requireValue(new Set(ids).size===cohort.queries,label+" duplicate query ID");
 requireValue(orderedIdSha(ids)===cohort.profile_query_order_sha256,label+" order digest differs");
 requireValue(orderedIdSha([...ids].sort())===cohort.query_universe_sorted_ids_sha256,
  label+" sorted query universe differs");
 return ids;
}
function compareSavedProfiles(candidate,references,contract) {
 requireValue(candidate && candidate.schema_version===1 && candidate.status==="completed" &&
  !Object.hasOwn(candidate,"error"),"Candidate profile is incomplete or retains an error");
 for(const field of ["expected_calls","attempted_calls","completed_calls"])
  requireValue(candidate[field]===contract.calls,"Candidate "+field+" differs");
 requireValue(candidate.runtime_source_sha256===contract.runtime &&
  candidate.script_sha256===contract.helper,"Candidate source or helper differs");
 requireValue(candidate.label===contract.label && same(candidate.settings,contract.settings),
  "Candidate label or settings differs");
 requireValue(Array.isArray(candidate.cells) && candidate.cells.length===contract.axes.length &&
  Array.isArray(references) && references.length===contract.axes.length,"Missing/extra profile cell");
 const mismatches=[], cells=[];let count=0;
 for(let i=0;i<contract.axes.length;i++){
  const axis=contract.axes[i],expected=contract.cohorts[axis[0]],left=references[i],right=candidate.cells[i];
  const leftIds=validateCell(left,axis,expected,"Baseline "+i);
  const rightIds=validateCell(right,axis,expected,"Candidate "+i);
  requireValue(same(leftIds,rightIds),"Complete ordered query IDs differ at cell "+i);
  let differences=0;
  for(let j=0;j<expected.queries;j++){
   const baseline=left.rows[j].non_timing_payload_sha256,observed=right.rows[j].non_timing_payload_sha256;
   if(baseline!==observed){
    differences++;
    mismatches.push({cell_index:i,row_index:j,cohort:axis[0],configuration:axis[1],
     query_id:rightIds[j],baseline,candidate:observed});
   }
  }
  const digestPairs=value=>sha256Bytes(utf8bytes(JSON.stringify(
   value.rows.map(row=>[row.query_id,row.non_timing_payload_sha256]))));
  cells.push({cohort:axis[0],configuration:axis[1],dataset_sha256:expected.dataset_sha256,
   queries:expected.queries,query_order_sha256:orderedIdSha(rightIds),
   query_universe_sorted_ids_sha256:orderedIdSha([...rightIds].sort()),
   baseline_ordered_id_payload_pairs_sha256:digestPairs(left),
   candidate_ordered_id_payload_pairs_sha256:digestPairs(right),
   compared:expected.queries,equal:expected.queries-differences,mismatched:differences});
  count+=expected.queries;
 }
 requireValue(count===contract.calls,"Final compared count differs");
 return {calls:count,equal:count-mismatches.length,mismatched:mismatches.length,
  all_full_non_timing_payloads_equal_to_v032_c2:mismatches.length===0,cells,mismatches};
}
function auditNoProfile(input) {
 // The caller first publishes this complete pins object at an exact commit.
 const pins=input.pins;
 requireValue(pins && COMMIT.test(pins.result_commit) && COMMIT.test(pins.controller_commit) &&
  COMMIT.test(pins.source_binding_commit) && HEX.test(pins.controller_sha256) &&
  Number.isSafeInteger(pins.workflow_run_id) && pins.workflow_run_id>0 &&
  pins.workflow_run_attempt===1,"Actual root-controlled execution identities not frozen");
 const scope=checkedText("NO scope",input.scope_text,PIN.scope);
 const old=checkedText("original I binding",input.old_text,PIN.old);
 const manifest=checkedText("C2 manifest",input.manifest_text,PIN.manifest);
 requireValue(sha256Bytes(utf8bytes(input.helper_text))===PIN.helper,"Profile helper differs");
 requireValue(sha256Bytes(utf8bytes(input.controller_text))===pins.controller_sha256,"Bound controller differs");
 const metadata={};
 for(const key of ["source_binding","binding","intent","exit","storage"])
  metadata[key]=checkedText(key,input[key+"_text"],pins.metadata_sha256[key]);
 const frozen=metadata.source_binding.value,binding=metadata.binding.value,
  intent=metadata.intent.value,exit=metadata.exit.value,storage=metadata.storage.value;
 requireValue(frozen.candidate==="NO" && frozen.status==="frozen-before-any-no-corpus-call" &&
  frozen.commit===PIN.source && frozen.runtime_sha256===PIN.runtime &&
  frozen.development_scope_commit===PIN.scopeCommit &&
  frozen.development_scope_sha256===PIN.scope,"Wrong exact NO source binding");
 requireValue(binding.attempt==="round5-candidate-no-development-1" &&
  binding.scope_sha256===PIN.scope && binding.script_sha256===pins.controller_sha256 &&
  binding.workflow_commit===pins.controller_commit && String(binding.run_id)===String(pins.workflow_run_id) &&
  binding.old_schedule_reference_sha256===PIN.old &&
  binding.source_binding_sha256===metadata.source_binding.sha256,"Bound result execution differs");
 requireValue(binding.sources.candidate.commit===PIN.source &&
  binding.sources.candidate.runtime_sha256===PIN.runtime &&
  same(binding.sources.candidate.files_sha256,frozen.files_sha256) &&
  binding.sources.baseline.commit===PIN.baseline &&
  binding.sources.baseline.runtime_sha256===PIN.baselineRuntime,
  "Result source identities differ");
 requireValue(same(binding.helpers_sha256,old.value.helpers_sha256) &&
  same(binding.helper_dependency_sha256,old.value.helper_dependency_sha256) &&
  binding.profile_calls_expected===4732 && binding.fresh_rows_decoded===0,"Result helper/data scope differs");
 for(const cohort of ["synthetic61","public1015"])
  for(const field of ["dataset_sha256","queries","sessions"])
   requireValue(binding.cohorts[cohort][field]===old.value.cohorts[cohort][field],
    "Bound dataset identity differs "+cohort+"/"+field);
 requireValue(intent.status==="started" && intent.expected_calls===4732 &&
  intent.binding_sha256===metadata.binding.sha256 && intent.source.commit===PIN.source &&
  intent.source.runtime_sha256===PIN.runtime && intent.helper_sha256===PIN.helper,
  "Profile intent is not linked to this result");
 requireValue(exit.returncode===0 && exit.error===null,"Profile subprocess did not complete");
 requireValue(same(scope.value.profile.baseline_cells,old.value.profile.baseline_cells) &&
  same(binding.profile_baseline_references.baseline_cells,old.value.profile.baseline_cells) &&
  same(intent.baseline_reference.baseline_cells,old.value.profile.baseline_cells),
  "Frozen reference inventory differs");
 const baseline=manifest.value;
 requireValue(baseline.schema_version===1 && baseline.status==="completed" &&
  baseline.runtime_source_sha256===PIN.baselineRuntime && baseline.script_sha256===PIN.helper,
  "C2 baseline runtime/helper/status differs");
 for(const field of ["expected_calls","attempted_calls","completed_calls"])
  requireValue(baseline[field]===4732,"C2 complete call count differs");
 requireValue(same(baseline.settings,{
  cache_size:0,use_cache:false,limit:5,semantic:false,coverage:false,
  tokenizer:"cl100k_base",query_shuffle_seed:41061}),"Frozen baseline settings differs");
 const specs=scope.value.profile.baseline_cells;
 requireValue(specs.length===8 && baseline.cells.length===8 &&
  same(Object.keys(input.reference_base64).sort(),specs.map(s=>s.path).sort()),
  "Reference object inventory must be exactly eight");
 const codec=codecFromPinnedSource(input.pako_source),references=[],artifacts=[];
 for(let i=0;i<8;i++){
  const spec=specs[i],record=baseline.cells[i];
  for(const k of ["cohort","configuration","bytes","sha256","uncompressed_sha256"])
   requireValue(record[k]===spec[k],"C2 cell manifest differs "+i+"/"+k);
  requireValue(spec.path==="benchmarks/reports/round4-development/"+record.path,"C2 path differs");
  const loaded=checkedGzip(spec.path,input.reference_base64[spec.path],spec,codec);
  references.push(loaded.value);
  const {value,...artifact}=loaded;artifacts.push({reference_commit:PIN.reference,...artifact});
 }
 const profile=checkedGzip("profile.json.gz",input.candidate_base64,{
  bytes:storage.compressed_bytes,sha256:storage.compressed_sha256,
  uncompressed_bytes:storage.uncompressed_bytes,uncompressed_sha256:storage.uncompressed_sha256},codec);
 requireValue(exit.output_sha256===profile.uncompressed_sha256,"Exit/raw report SHA differs");
 requireValue(profile.value.scope===baseline.scope,"Profile diagnostic scope differs");
 const contract={calls:4732,runtime:PIN.runtime,helper:PIN.helper,label:"candidate-no",
  settings:baseline.settings,axes:specs.map(s=>[s.cohort,s.configuration]),cohorts:old.value.cohorts};
 const compared=compareSavedProfiles(profile.value,references,contract);
 const {value,...candidateArtifact}=profile;
 return {schema_version:1,status:compared.mismatched ? "profile-payload-mismatch" :
   "independent-saved-profile-digests-equal",
  execution_pins:pins,source_commit:PIN.source,runtime_sha256:PIN.runtime,
  baseline_commit:PIN.baseline,baseline_runtime_sha256:PIN.baselineRuntime,
  reference_commit:PIN.reference,profile_helper_sha256:PIN.helper,
  scope_sha256:scope.sha256,original_schedule_sha256:old.sha256,
  baseline_manifest:{bytes:manifest.bytes,sha256:manifest.sha256},
  metadata:Object.fromEntries(Object.entries(metadata).map(([k,{value,...v}])=>[k,v])),
  codec:{name:"pako",version:"2.1.0",source_sha256:PIN.pako},
  candidate_artifact:candidateArtifact,reference_artifacts:artifacts,...compared,
  definition:"The unchanged helper removes only latency_ms and SHA256-hashes the complete remaining payload object. Raw profile reports store these digests, not the payload plaintext.",
  speed_claim:false,retrieval_calls_executed_by_audit:0,fresh_rows_decoded:0};
}
module.exports={PIN,sha256Bytes,utf8bytes,strictUtf8,base64Bytes,checkedText,
 codecFromPinnedSource,checkedGzip,orderedIdSha,validateCell,compareSavedProfiles,auditNoProfile};
