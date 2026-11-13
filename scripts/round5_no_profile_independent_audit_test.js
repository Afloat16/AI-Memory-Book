/* Invented-data checks for the independent read-only NO profile auditor.
 * No repository runtime or benchmark is imported. No actual dataset is read.
 */
"use strict";
module.exports = function runArtificialChecks(api,pakoSource) {
 const results=[];
 function test(name,fn){try{fn();results.push({name,status:"passed"});}catch(error){results.push({name,status:"failed",error:String(error)});}}
 function equal(a,b,message){if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(message||"Different values");}
 function expectError(fn,pattern){let caught=false;try{fn();}catch(error){caught=true;if(pattern&&!pattern.test(String(error)))throw error;}if(!caught)throw new Error("Expected rejection");}
 const clone=x=>JSON.parse(JSON.stringify(x));
 const configs=["native-char4000","native-token512","native-token1024","native-token2048"];
 const names=["invented-small","invented-large"],cohorts={},axes=[],references=[];
 for(const [index,name] of names.entries()){
  const count=index===0?168:1015,ids=Array.from({length:count},(_,i)=>name+"-q"+String(i).padStart(4,"0"));
  cohorts[name]={queries:count,dataset_sha256:api.sha256Bytes(api.utf8bytes("invented/"+name)),
   profile_query_order_sha256:api.orderedIdSha(ids),
   query_universe_sorted_ids_sha256:api.orderedIdSha([...ids].sort())};
  for(const config of configs){
   axes.push([name,config]);
   references.push({cohort:name,configuration:config,status:"completed",
    dataset_sha256:cohorts[name].dataset_sha256,queries:count,
    rows:ids.map((id,i)=>({query_id:id,non_timing_payload_sha256:
     api.sha256Bytes(api.utf8bytes("invented/"+name+"/"+config+"/"+i))}))});
  }
 }
 const contract={calls:4732,runtime:"a".repeat(64),helper:"b".repeat(64),
  label:"invented-profile",settings:{use_cache:false,query_shuffle_seed:41061},axes,cohorts};
 const candidate={schema_version:1,status:"completed",label:contract.label,
  runtime_source_sha256:contract.runtime,script_sha256:contract.helper,settings:clone(contract.settings),
  expected_calls:4732,attempted_calls:4732,completed_calls:4732,cells:clone(references)};
 const audit=(c=candidate,r=references,k=contract)=>api.compareSavedProfiles(c,r,k);
 test("standard_sha256_empty_vector",()=>equal(api.sha256Bytes(api.utf8bytes("")),
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
 test("standard_sha256_abc_vector",()=>equal(api.sha256Bytes(api.utf8bytes("abc")),
  "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
 test("all4732_invented_digests_are_compared",()=>{const r=audit();equal([r.calls,r.equal,r.mismatched,r.cells.length],[4732,4732,0,8]);equal(r.all_full_non_timing_payloads_equal_to_v032_c2,true);});
 test("first_middle_and_last_mismatches_are_all_retained",()=>{const c=clone(candidate);
  for(const [i,j] of [[0,0],[4,500],[7,1014]])c.cells[i].rows[j].non_timing_payload_sha256="f".repeat(64);
  const r=audit(c);equal([r.calls,r.equal,r.mismatched],[4732,4729,3]);
  equal(r.all_full_non_timing_payloads_equal_to_v032_c2,false);
  equal(r.mismatches.map(v=>[v.cell_index,v.row_index]),[[0,0],[4,500],[7,1014]]);
 });
 for(const field of ["expected_calls","attempted_calls","completed_calls"])
  test("reject_incomplete_"+field,()=>{const c=clone(candidate);c[field]--;expectError(()=>audit(c),/differs/);});
 test("reject_running_profile",()=>{const c=clone(candidate);c.status="running";expectError(()=>audit(c),/incomplete/);});
 test("reject_success_with_retained_error",()=>{const c=clone(candidate);c.error="previous failure";expectError(()=>audit(c),/retains an error/);});
 for(const field of ["runtime_source_sha256","script_sha256"])
  test("reject_changed_"+field,()=>{const c=clone(candidate);c[field]="c".repeat(64);expectError(()=>audit(c),/source or helper/);});
 test("reject_changed_label",()=>{const c=clone(candidate);c.label="other";expectError(()=>audit(c),/label or settings/);});
 test("reject_changed_settings",()=>{const c=clone(candidate);c.settings.use_cache=true;expectError(()=>audit(c),/label or settings/);});
 test("reject_missing_cell",()=>{const c=clone(candidate);c.cells.pop();expectError(()=>audit(c),/profile cell/);});
 test("reject_extra_cell",()=>{const c=clone(candidate);c.cells.push(clone(c.cells[0]));expectError(()=>audit(c),/profile cell/);});
 test("reject_missing_reference",()=>expectError(()=>audit(candidate,references.slice(1)),/profile cell/));
 test("reject_reordered_cells",()=>{const c=clone(candidate);[c.cells[0],c.cells[1]]=[c.cells[1],c.cells[0]];expectError(()=>audit(c),/axis/);});
 test("reject_incomplete_cell",()=>{const c=clone(candidate);c.cells[7].status="failed";expectError(()=>audit(c),/status or axis/);});
 test("reject_dataset_drift",()=>{const c=clone(candidate);c.cells[0].dataset_sha256="d".repeat(64);expectError(()=>audit(c),/dataset/);});
 test("reject_query_count_drift",()=>{const c=clone(candidate);c.cells[0].queries++;expectError(()=>audit(c),/row count/);});
 test("reject_missing_final_row",()=>{const c=clone(candidate);c.cells[7].rows.pop();expectError(()=>audit(c),/row count/);});
 test("reject_extra_row",()=>{const c=clone(candidate);c.cells[0].rows.push(clone(c.cells[0].rows[0]));expectError(()=>audit(c),/row count/);});
 test("reject_duplicate_id",()=>{const c=clone(candidate);c.cells[0].rows[1].query_id=c.cells[0].rows[0].query_id;expectError(()=>audit(c),/duplicate query/);});
 test("reject_row_reorder",()=>{const c=clone(candidate);[c.cells[0].rows[0],c.cells[0].rows[1]]=[c.cells[0].rows[1],c.cells[0].rows[0]];expectError(()=>audit(c),/order digest/);});
 test("reject_sorted_universe_change",()=>{const k=clone(contract);k.cohorts[names[0]].query_universe_sorted_ids_sha256="e".repeat(64);expectError(()=>audit(candidate,references,k),/sorted query universe/);});
 test("reject_nonascii_schedule_before_cross_language_hash",()=>{const c=clone(candidate);c.cells[0].rows[0].query_id="汉";expectError(()=>audit(c),/ASCII/);});
 test("reject_malformed_candidate_digest",()=>{const c=clone(candidate);c.cells[7].rows[1014].non_timing_payload_sha256="x".repeat(64);expectError(()=>audit(c),/malformed/);});
 test("reject_malformed_baseline_digest",()=>{const r=clone(references);r[0].rows[0].non_timing_payload_sha256="F".repeat(64);expectError(()=>audit(candidate,r),/malformed/);});
 test("reject_extra_payload_row_field",()=>{const c=clone(candidate);c.cells[0].rows[0].extra="hidden";expectError(()=>audit(c),/malformed/);});
 test("reject_missing_payload_row_field",()=>{const c=clone(candidate);delete c.cells[0].rows[0].non_timing_payload_sha256;expectError(()=>audit(c),/malformed/);});
 test("utf8_roundtrip_ascii_cjk_supplementary_and_nul",()=>{const text="ascii 汉字 😀 \0";equal(api.strictUtf8(api.utf8bytes(text)),text);});
 for(const [name,bytes] of [
  ["overlong",[192,128]],["surrogate",[237,160,128]],["truncated",[240,159,152]],
  ["bad_continuation",[226,65,128]],["too_large",[244,144,128,128]],["bad_start",[255]]])
  test("reject_utf8_"+name,()=>expectError(()=>api.strictUtf8(Uint8Array.from(bytes)),/UTF-8/));
 test("reject_malformed_base64",()=>expectError(()=>api.base64Bytes("??"),/Malformed base64/));
 test("decode_base64_exact_bytes",()=>equal([...api.base64Bytes("AAECA/8=")],[0,1,2,3,255]));
 test("reject_wrong_pako_source_before_eval",()=>expectError(()=>api.codecFromPinnedSource("throw Error('must not execute');"),/identity changed/));
 const codec=api.codecFromPinnedSource(pakoSource);
 function base64(bytes){const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out="";for(let i=0;i<bytes.length;i+=3){const n=(bytes[i]<<16)|((bytes[i+1]||0)<<8)|(bytes[i+2]||0);
   out+=alphabet[(n>>>18)&63]+alphabet[(n>>>12)&63]+(i+1<bytes.length?alphabet[(n>>>6)&63]:"=")+(i+2<bytes.length?alphabet[n&63]:"=");}return out;}
 function gzipStored(raw){if(raw.length>65535)throw Error("Artificial fixture too big");let crc=4294967295;
  for(const byte of raw){crc^=byte;for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}crc=(crc^4294967295)>>>0;
  const result=new Uint8Array(10+5+raw.length+8);result.set([31,139,8,0,0,0,0,0,0,255,1,raw.length&255,raw.length>>>8,(~raw.length)&255,((~raw.length)>>>8)&255]);
  result.set(raw,15);const v=new DataView(result.buffer);v.setUint32(result.length-8,crc,true);v.setUint32(result.length-4,raw.length,true);return result;}
 const raw=api.utf8bytes('{"invented":"汉😀","rows":[]}\n'),gz=gzipStored(raw),
  spec={bytes:gz.length,sha256:api.sha256Bytes(gz),uncompressed_bytes:raw.length,uncompressed_sha256:api.sha256Bytes(raw)};
 test("actual_gzip_decode_retains_exact_raw_bytes",()=>{const r=api.checkedGzip("invented",base64(gz),spec,codec);equal(r.value,{invented:"汉😀",rows:[]});equal([r.uncompressed_bytes,r.uncompressed_sha256],[raw.length,spec.uncompressed_sha256]);});
 test("reject_wrong_compressed_size",()=>expectError(()=>api.checkedGzip("invented",base64(gz),{...spec,bytes:spec.bytes+1},codec),/Compressed size/));
 test("reject_wrong_compressed_sha",()=>expectError(()=>api.checkedGzip("invented",base64(gz),{...spec,sha256:"0".repeat(64)},codec),/Compressed SHA/));
 test("reject_wrong_raw_sha",()=>expectError(()=>api.checkedGzip("invented",base64(gz),{...spec,uncompressed_sha256:"0".repeat(64)},codec),/Raw SHA/));
 test("reject_wrong_raw_size",()=>expectError(()=>api.checkedGzip("invented",base64(gz),{...spec,uncompressed_bytes:raw.length+1},codec),/Raw size/));
 test("reject_real_gzip_crc_corruption_with_matching_outer_sha",()=>{const damaged=new Uint8Array(gz);damaged[damaged.length-8]^=1;expectError(()=>api.checkedGzip("invented",base64(damaged),{...spec,sha256:api.sha256Bytes(damaged)},codec));});
 test("reject_gzip_with_invalid_utf8_raw_even_when_hashes_match",()=>{const badRaw=Uint8Array.from([255]),badGz=gzipStored(badRaw);expectError(()=>api.checkedGzip("invented",base64(badGz),{bytes:badGz.length,sha256:api.sha256Bytes(badGz),uncompressed_sha256:api.sha256Bytes(badRaw)},codec),/UTF-8/);});
 test("reject_audit_without_frozen_execution_pins",()=>expectError(()=>api.auditNoProfile({}),/execution identities not frozen/));
 return {schema_version:1,status:results.every(r=>r.status==="passed")?"artificial-checks-passed":"artificial-checks-failed",
  tests:results.length,passed:results.filter(r=>r.status==="passed").length,failed:results.filter(r=>r.status==="failed").length,
  invented_comparison_rows:4732,results,actual_no_profile_results_read:0,actual_corpus_retrieval_calls:0,fresh_rows_decoded:0};
};
