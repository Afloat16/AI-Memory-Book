/* Pure independent audit of the frozen LM SQLite diagnostic.
 * No I/O, retrieval, subprocess, benchmark, or workflow operation.
 * The caller verifies the pinned NO utility module before passing it here.
 */
"use strict";
module.exports = function makeSqlAudit(core) {
 const PIN={
  producer:"983813673788860014fcb0900583982b46b5d6e5c231541477e54d4a05e76273",
  producerCommit:"108124188381a199735022abf21b9a0b9c812a54",
  source:"49f10e7dec006e3a5760c93623a650dc7b6338d6",
  runtime:"fa56d26927ca625414ae9c9265ab285f2f8e714ec7ed015170e0bdd82d8a5bcd",
  baselineRuntime:"179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93",
  scope:"0b3a249df45a25a00f76f4ad2c6e0cfa56fc7147a19e982fca429884c5ef1269",
  old:"02067bdd4c38bd1fcd2a3feef5974aa7bf9eac213e6009ddd64ead37356b7ad5",
  manifest:"4e1b098f32a89c7c8363c8ee67e02af54bb438965a72e773ec0ef199fb2cca00",
  helper:"593b9f0667b1fc1cb3e38f5cc8411620759bc5abae68c56816221b950f99a416",
  pairing:"cf55b88d45ee7a0dca53abefa6dc651d7eceb36f6ae0e709919655c566c36d21",
  publisher:"c9b58ce1079f449dc6809c54c6f2cf4beba45695af8b3d0ae63c409e26d776a4",
  reference:"761eaf5c9ca47c93dea25f73104eb259304df68a",
  scriptPath:"scripts/round5_lm_sql_attribution.py"
 };
 const HEX=/^[0-9a-f]{64}$/,COMMIT=/^[0-9a-f]{40}$/;
 const PRIMARY=new Set(["Connection.execute","Cursor.fetchall","Cursor.fetchone"]);
 const requireValue=(ok,message)=>{if(!ok)throw new Error(message);};
 function integer(value,label,min=0n){requireValue(typeof value==="bigint"&&value>=min,"Invalid exact integer "+label);return value;}
 function same(a,b){
  if(a===b)return true;
  if(a===null||b===null||typeof a!==typeof b)return false;
  if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>same(v,b[i]));
  if(typeof a!=="object")return false;
  const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
  return same(ak,bk)&&ak.every(k=>same(a[k],b[k]));
 }
 function parseExact(text,transform){
  let at=0;
  function ws(){while(at<text.length&&/[\x20\t\r\n]/.test(text[at]))at++;}
  function string(){
   const begin=at++;while(at<text.length){
    const c=text[at++];if(c==='"')return JSON.parse(text.slice(begin,at));
    if(c==="\\"){requireValue(at<text.length,"Truncated JSON escape");at++;}
   }throw new Error("Unterminated JSON string");
  }
  function value(path){
   ws();const c=text[at];let out;
   if(c==='"')out=string();
   else if(c==="{"){
    at++;out=Object.create(null);ws();
    if(text[at]==="}")at++;
    else while(true){
     ws();requireValue(text[at]==='"',"JSON object key required");const k=string();
     requireValue(!Object.hasOwn(out,k),"Duplicate JSON key");ws();requireValue(text[at++]===":","JSON colon required");
     out[k]=value([...path,k]);ws();const end=text[at++];if(end==="}")break;requireValue(end===",","JSON object delimiter");
    }
   }else if(c==="["){
    at++;out=[];ws();if(text[at]==="]")at++;
    else while(true){out.push(value([...path,out.length]));ws();const end=text[at++];if(end==="]")break;requireValue(end===",","JSON array delimiter");}
   }else if(text.startsWith("true",at)){at+=4;out=true;}
   else if(text.startsWith("false",at)){at+=5;out=false;}
   else if(text.startsWith("null",at)){at+=4;out=null;}
   else {
    const match=text.slice(at).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    requireValue(match,"Invalid JSON value");const token=match[0];at+=token.length;
    out=/[.eE]/.test(token)?Number(token):BigInt(token);
    requireValue(typeof out==="bigint"||Number.isFinite(out),"Nonfinite JSON number");
   }
   return transform?transform(path,out):out;
  }
  const out=value([]);ws();requireValue(at===text.length,"Trailing JSON input");return out;
 }
 function stringifyExact(value,pretty=false,sortKeys=false){
  function emit(v,depth){
   if(typeof v==="bigint")return v.toString();
   if(v===null||typeof v==="boolean"||typeof v==="string")return JSON.stringify(v);
   if(typeof v==="number"){requireValue(Number.isFinite(v),"Cannot serialize nonfinite number");const token=Object.is(v,-0)?"-0.0":JSON.stringify(v);return Number.isInteger(v)&&!/[.eE]/.test(token)?token+".0":token;}
   requireValue(typeof v==="object","Unsupported JSON value");
   const array=Array.isArray(v),keys=array?v.map((_,i)=>i):Object.keys(v);
   if(sortKeys&&!array)keys.sort();
   const rows=keys.map(k=>(array?"":JSON.stringify(k)+(pretty?": ":":"))+emit(v[k],depth+1));
   if(!rows.length)return array?"[]":"{}";
   return (array?"[":"{")+(pretty?"\n"+"  ".repeat(depth+1):"")+
    rows.join(pretty?",\n"+"  ".repeat(depth+1):",")+
    (pretty?"\n"+"  ".repeat(depth):"")+(array?"]":"}");
  }return emit(value,0);
 }
 const digest=value=>core.sha256Bytes(core.utf8bytes(stringifyExact(value,false,true)));
 function textArtifact(label,text,expected){
  requireValue(typeof text==="string"&&HEX.test(expected),"Missing pinned text "+label);
  const bytes=core.utf8bytes(text),actual=core.sha256Bytes(bytes);
  requireValue(core.strictUtf8(bytes)===text&&actual===expected,"Text identity differs "+label);
  return {label,bytes:BigInt(bytes.length),sha256:actual,value:parseExact(text)};
 }
 function unpack(label,encoded,spec,codec){
  integer(spec.bytes,label+" compressed bytes");requireValue(HEX.test(spec.sha256)&&HEX.test(spec.raw_sha256),"Missing binary digest "+label);
  const compressed=boundedBase64(encoded);
  requireValue(BigInt(compressed.length)===spec.bytes&&core.sha256Bytes(compressed)===spec.sha256,"Compressed identity differs "+label);
  requireValue(compressed[0]===31&&compressed[1]===139,"Not gzip "+label);
  const raw=codec.ungzip(compressed);requireValue(raw instanceof Uint8Array,"Codec must return bytes");
  const rawSha=core.sha256Bytes(raw);
  requireValue(rawSha===spec.raw_sha256,"Raw SHA differs "+label);
  if(spec.raw_bytes!==undefined)requireValue(BigInt(raw.length)===integer(spec.raw_bytes,label+" raw bytes"),"Raw size differs "+label);
  return {raw,identity:{label,bytes:BigInt(compressed.length),sha256:spec.sha256,raw_bytes:BigInt(raw.length),raw_sha256:rawSha}};
 }

 // Same pinned strict codec, bounded in chunks to avoid per-byte string arrays
 // for the approximately42MB complete profile. No change to accepted UTF-8.
 function boundedUtf8(bytes){
  const pieces=[];let begin=0;
  while(begin<bytes.length){
   let end=Math.min(bytes.length,begin+65536);
   while(end<bytes.length&&(bytes[end]&192)===128)end--;
   requireValue(end>begin,"Invalid UTF-8 continuation run");
   pieces.push(core.strictUtf8(bytes.subarray(begin,end)));begin=end;
  }
  return pieces.join("");
 }
 function boundedBase64(encoded){
  requireValue(typeof encoded==="string","Base64 transport required");
  const value=encoded.replace(/[\t\n\r ]/g,""),parts=[];let length=0;
  for(let at=0;at<value.length;at+=65536){
   const part=value.slice(at,at+65536);
   if(at+65536<value.length)requireValue(!part.includes("="),"Early base64 padding");
   const bytes=core.base64Bytes(part);parts.push(bytes);length+=bytes.length;
  }
  const out=new Uint8Array(length);let at=0;
  for(const part of parts){out.set(part,at);at+=part.length;}return out;
 }
 function profileIndex(encoded,spec,codec){
  const read=unpack("profile.json.gz",encoded,spec,codec),links=[];
  const header=parseExact(boundedUtf8(read.raw),(path,value)=>{
   if(path.length===2&&path[0]==="cells"&&typeof path[1]==="number"){
    requireValue(path[1]===links.length&&value&&value.storage,"Unexpected profile cell/storage");
    const {storage,...body}=value;
    const link={index:BigInt(path[1]),cohort:value.cohort,configuration:value.configuration,
     queries:value.queries,dataset_sha256:value.dataset_sha256,
     canonical_body_sha256:digest(body),storage};
    links.push(link);
    return {index:link.index,cohort:link.cohort,configuration:link.configuration,
     canonical_body_sha256:link.canonical_body_sha256};
   }
   return value;
  });
  requireValue(links.length===8&&header.cells.length===8,"Complete profile index needs eight cells");
  return {profile_artifact:read.identity,header,links,
   method:"Complete compressed/raw bytes verified; each full cell canonicalized with exact integer tokens, then released. Per-cell stored gzip must match that canonical body before its spans are audited."};
 }
 function auditStoredCell(encoded,link,baseline,axis,expected,context,options,codec){
  const read=unpack(link.storage.cell.path,encoded,link.storage.cell,codec);
  const cell=parseExact(boundedUtf8(read.raw));
  requireValue(!Object.hasOwn(cell,"storage"),"Standalone cell unexpectedly contains post-pack storage");
  const bodySha=digest(cell);requireValue(bodySha===link.canonical_body_sha256,"Stored cell differs from complete profile cell");
  requireValue(cell.cohort===link.cohort&&cell.configuration===link.configuration&&
   cell.queries===link.queries&&cell.dataset_sha256===link.dataset_sha256,"Profile/cell identities differ");
  return {index:link.index,canonical_body_sha256:bodySha,artifact:read.identity,
   audit:auditCell(cell,baseline,axis,expected,context,options)};
 }

 function locationValid(location,context){
  requireValue(location&&typeof location.path==="string"&&typeof location.function==="string"&&typeof location.qualname==="string","Invalid source location");
  integer(location.first_line,"source first line",1n);integer(location.line,"source line",1n);integer(location.offset,"source offset",-1n);
  if(location.source_sha256!==null)
   requireValue(HEX.test(location.source_sha256)&&context.files[location.path]===location.source_sha256,"Unfrozen source location hash");
 }
 function lineMatches(location,rule,prefix=""){
  return (rule[prefix+"lines"]||[]).some(n=>n===location.line)||
   (rule[prefix+"line_ranges"]||[]).some(([lo,hi])=>lo<=location.line&&location.line<=hi);
 }
 function categoryFor(site,context){
  locationValid(site.location,context);if(site.caller!==null)locationValid(site.caller,context);
  const unknown=PRIMARY.has(site.method)?"unclassified_primary":"other_sqlite_builtin",location=site.location,caller=site.caller;
  if(location.source_sha256===null)return unknown;
  for(const rule of context.rules){
   if(rule.path_prefixes){
    if(rule.path_prefixes.some(p=>location.path.startsWith(p)))return rule.category;
    continue;
   }
   if(location.path!=="src/memory_book/store.py"||location.qualname!==rule.function||
    !rule.methods.includes(site.method)||!lineMatches(location,rule))continue;
   if(rule.caller_function&&(caller===null||caller.path!=="src/memory_book/store.py"||
    caller.source_sha256===null||caller.qualname!==rule.caller_function||!lineMatches(caller,rule,"caller_")))continue;
   return rule.category;
  }return unknown;
 }
 function validateSites(sites,context){
  requireValue(Array.isArray(sites),"Missing raw site table");
  return sites.map((site,index)=>{
   requireValue(site.site_id===BigInt(index)&&typeof site.method==="string"&&/^(?:Connection|Cursor)\.[A-Za-z_]\w*$/.test(site.method),"Invalid raw site identity");
   const actual=categoryFor(site,context);requireValue(site.category===actual,"Declared category differs from frozen source rule");
   return actual;
  });
 }
 function observation(value,sites){
  requireValue(value&&value.valid===true&&value.started===true&&value.finished===true&&
   value.callback_failure===null&&same(value.open_sequences,[]),"Invalid/incomplete observation");
  const rows=value.spans;requireValue(Array.isArray(rows),"Missing raw spans");
  const roots=[],children=rows.map(()=>[]),events=Object.create(null);
  let exclusive=0n,previousStart=null,minStart=null,maxEnd=null;
  rows.forEach((row,index)=>{
   requireValue(row.sequence===BigInt(index),"Raw sequence is not exact contiguous integers");
   const sid=integer(row.site_id,"site id");requireValue(sid<BigInt(sites.length),"Missing span source site");
   requireValue(row.method===sites[Number(sid)].method,"Span/site method differs");
   requireValue((row.status==="returned"||row.status==="exception")&&typeof row.wrapper_is==="boolean","Unclosed native span/wrapper evidence");
   for(const field of ["start_ns","end_ns","inclusive_ns","child_inclusive_ns","exclusive_ns"])integer(row[field],field);
   requireValue(row.end_ns-row.start_ns===row.inclusive_ns&&row.inclusive_ns-row.child_inclusive_ns===row.exclusive_ns,"Native arithmetic differs");
   requireValue(previousStart===null||row.start_ns>=previousStart,"Native entry clock moves backward");previousStart=row.start_ns;
   minStart=minStart===null?row.start_ns:(row.start_ns<minStart?row.start_ns:minStart);
   maxEnd=maxEnd===null?row.end_ns:(row.end_ns>maxEnd?row.end_ns:maxEnd);
   if(row.parent_sequence===null)roots.push(index);
   else {
    const parent=integer(row.parent_sequence,"parent sequence");requireValue(parent<BigInt(index),"Invalid parent order");
    const ancestor=rows[Number(parent)];
    requireValue(ancestor.start_ns<=row.start_ns&&row.end_ns<=ancestor.end_ns,"Child outside parent");
    children[Number(parent)].push(index);
   }
   exclusive+=row.exclusive_ns;
   events.c_call=(events.c_call||0n)+1n;const exit=row.status==="exception"?"c_exception":"c_return";events[exit]=(events[exit]||0n)+1n;
  });
  // Independent tree/preorder proof, rather than the producer's active-parent algorithm.
  for(const siblings of [roots,...children]){
   for(let i=1;i<siblings.length;i++)requireValue(rows[siblings[i-1]].end_ns<=rows[siblings[i]].start_ns,"Overlapping siblings/roots");
  }
  const traversal=[],pending=[...roots].reverse();
  while(pending.length){const i=pending.pop();traversal.push(i);for(let j=children[i].length-1;j>=0;j--)pending.push(children[i][j]);}
  requireValue(traversal.length===rows.length&&traversal.every((id,i)=>id===i),"Entry order reopens or bypasses an active parent");
  rows.forEach((row,index)=>requireValue(row.child_inclusive_ns===children[index].reduce((sum,id)=>sum+rows[id].inclusive_ns,0n),"Direct child sum differs"));
  requireValue(roots.reduce((sum,id)=>sum+rows[id].inclusive_ns,0n)===exclusive,"Exclusive sum does not equal disjoint root union");
  requireValue(same(events,value.target_events),"Target event totals differ");
  let allEvents=0n;for(const n of Object.values(value.events))allEvents+=integer(n,"event counter");
  for(const [kind,n] of Object.entries(events))requireValue((value.events[kind]||0n)>=n,"Target count exceeds event count");
  const nativeEvents=Object.values(events).reduce((a,b)=>a+b,0n);
  requireValue(integer(value.non_target_events,"non-target events")===allEvents-nativeEvents,"Non-target count differs");
  const wall=integer(value.recall_wall_ns_including_observer,"recall wall");
  requireValue(wall>=exclusive&&value.observed_exclusive_builtin_ns===exclusive&&
   integer(value.unattributed_wall_ns,"unattributed wall")===wall-exclusive,"Wall/residual reconciliation differs");
  if(minStart!==null)requireValue(maxEnd-minStart<=wall,"Native extent cannot fit in recall wall");
  return {spans:BigInt(rows.length),exclusive,wall,unattributed:value.unattributed_wall_ns,
   bookkeeping:integer(value.callback_bookkeeping_ns,"callback bookkeeping"),events:value.events,
   target_events:events,non_target_events:value.non_target_events};
 }
 function zeroGroup(identity){return {...identity,calls:0n,returned:0n,exceptions:0n,open:0n,inclusive_ns:0n,exclusive_ns:0n};}
 function addSpan(group,span){group.calls++;group[span.status==="returned"?"returned":"exceptions"]++;group.inclusive_ns+=span.inclusive_ns;group.exclusive_ns+=span.exclusive_ns;}
 function idsAndPayloads(cell,axis,expected,observed){
  requireValue(cell.status==="completed"&&cell.cohort===axis[0]&&cell.configuration===axis[1]&&
   cell.dataset_sha256===expected.dataset_sha256&&cell.queries===expected.queries&&
   Array.isArray(cell.rows)&&BigInt(cell.rows.length)===expected.queries,"Cell axis/data/count incomplete");
  const ids=cell.rows.map(row=>{
   requireValue(typeof row.query_id==="string"&&/^[\x00-\x7f]*$/.test(row.query_id)&&HEX.test(row.non_timing_payload_sha256),"Malformed full payload row");
   if(observed)requireValue(!Object.hasOwn(row,"state")&&!Object.hasOwn(row,"error_type")&&row.observation,"Failed observed row");
   return row.query_id;
  });
  requireValue(BigInt(new Set(ids).size)===expected.queries&&core.orderedIdSha(ids)===expected.profile_query_order_sha256&&
   core.orderedIdSha([...ids].sort())===expected.query_universe_sorted_ids_sha256,"Complete query order/universe differs");
  return ids;
 }
 function auditCell(cell,baseline,axis,expected,context,options){
  const leftIds=idsAndPayloads(baseline,axis,expected,false),ids=idsAndPayloads(cell,axis,expected,true);
  requireValue(same(ids,leftIds)&&same(cell.options,options),"Cell options or ordered IDs differ");
  const categories=validateSites(cell.sites,context),siteGroups=new Map(),categoryGroups=new Map();
  for(const name of [...new Set([...context.rules.map(r=>r.category),"unclassified_primary","other_sqlite_builtin"])])
   categoryGroups.set(name,zeroGroup({category:name}));
  const mismatches=[],exceptions=[],violations=new Map(),totals={
   queries:0n,spans:0n,recall_wall_ns_including_observer:0n,observed_exclusive_builtin_ns:0n,
   unattributed_wall_ns:0n,callback_bookkeeping_ns:0n,non_target_events:0n,
   events:Object.create(null),target_events:Object.create(null),
   native_candidate_fetchall:0n,fallback_candidate_fetchall:0n,wrapper_same:0n,wrapper_fresh:0n};
  for(let i=0;i<cell.rows.length;i++){
   const row=cell.rows[i],b=baseline.rows[i];
   if(row.non_timing_payload_sha256!==b.non_timing_payload_sha256)
    mismatches.push({cohort:axis[0],configuration:axis[1],query_id:row.query_id,baseline:b.non_timing_payload_sha256,observed:row.non_timing_payload_sha256});
   const counts=observation(row.observation,cell.sites);
   totals.queries++;totals.spans+=counts.spans;totals.recall_wall_ns_including_observer+=counts.wall;
   totals.observed_exclusive_builtin_ns+=counts.exclusive;totals.unattributed_wall_ns+=counts.unattributed;
   totals.callback_bookkeeping_ns+=counts.bookkeeping;totals.non_target_events+=counts.non_target_events;
   for(const name of ["events","target_events"])
    for(const [event,count] of Object.entries(counts[name]))totals[name][event]=(totals[name][event]||0n)+count;
   for(const span of row.observation.spans){
    const sid=Number(span.site_id),site=cell.sites[sid],category=categories[sid],key=String(sid)+"/"+span.method;
    if(!siteGroups.has(key))siteGroups.set(key,zeroGroup({site_id:span.site_id,method:span.method,category}));
    addSpan(siteGroups.get(key),span);addSpan(categoryGroups.get(category),span);
    totals[span.wrapper_is?"wrapper_same":"wrapper_fresh"]++;
    if(span.status==="exception")exceptions.push({query_id:row.query_id,sequence:span.sequence,site_id:span.site_id,method:span.method,category});
    if(category==="unclassified_primary"||category.startsWith("disabled_"))violations.set(String(sid),{site_id:span.site_id,category});
    if(span.method==="Cursor.fetchall"&&site.location.path==="src/memory_book/store.py"&&site.location.qualname==="_candidate_rows"){
     if(site.location.line===253n)totals.native_candidate_fetchall++;
     if(site.location.line===257n)totals.fallback_candidate_fetchall++;
    }
   }
  }
  const callsites=[...siteGroups.values()];
  requireValue(same(callsites,cell.callsite_summary),"Declared callsite summary differs from every raw span");
  requireValue(callsites.reduce((n,s)=>n+s.exclusive_ns,0n)===totals.observed_exclusive_builtin_ns&&
   [...categoryGroups.values()].reduce((n,s)=>n+s.exclusive_ns,0n)===totals.observed_exclusive_builtin_ns,"Grouped exclusive totals differ");
  const classification=[...violations.values()].sort((a,b)=>a.site_id<b.site_id?-1:a.site_id>b.site_id?1:0);
  const payloadAudit={cohort:axis[0],configuration:axis[1],queries:expected.queries,
   query_order_sha256:expected.profile_query_order_sha256,mismatches,classification_violations:classification,
   all_classification_sites_valid:classification.length===0,all_full_non_timing_payloads_equal:mismatches.length===0};
  requireValue(same(payloadAudit,cell.payload_audit),"Declared per-cell payload/classification audit differs");
  return {cohort:axis[0],configuration:axis[1],dataset_sha256:expected.dataset_sha256,
   query_order_sha256:expected.profile_query_order_sha256,query_universe_sorted_ids_sha256:expected.query_universe_sorted_ids_sha256,
   payload_audit:payloadAudit,totals,categories:[...categoryGroups.values()],callsites,exceptions,
   stored_sites:cell.sites,callsite_summary_recomputed_equal:true};
 }
 function auditReport(report,references,scope,old,incremental=null){
  requireValue(report.schema_version===1n&&report.status==="completed"&&report.attempt==="round5-lm-sql-attribution-1"&&
   report.runtime_source_sha256===PIN.runtime&&report.script_sha256===PIN.producer&&report.scope_sha256===PIN.scope&&
   report.expected_calls===4732n&&report.attempted_calls===4732n&&report.completed_calls===4732n&&
   report.speed_claim===false&&report.fresh_rows_decoded===0n,"Incomplete/differently sourced diagnostic profile");
  requireValue(same(report.helpers_sha256,old.helpers_sha256)&&same(report.helper_dependency_sha256,old.helper_dependency_sha256),"Report helper closure differs");
  const specs=scope.payload_reference.cells;requireValue(Array.isArray(report.cells)&&report.cells.length===8&&references.length===8,"Cell inventory differs");
  const context={files:{...scope.runtime.files_sha256,[PIN.scriptPath]:PIN.producer},rules:scope.observer.source_mapping.rules};
  let previousSites=[];const cells=[];
  for(let i=0;i<8;i++){
   const raw=report.cells[i],spec=specs[i],config=scope.sequence.configurations[i%4];
   let audited;
   if(incremental){
    const receipt=incremental.cell_receipts[i],link=incremental.profile_index.links[i];
    requireValue(receipt.index===BigInt(i)&&link.index===BigInt(i)&&
     receipt.canonical_body_sha256===link.canonical_body_sha256&&
     raw.canonical_body_sha256===link.canonical_body_sha256&&
     receipt.artifact.bytes===link.storage.cell.bytes&&receipt.artifact.sha256===link.storage.cell.sha256&&
     receipt.artifact.raw_bytes===link.storage.cell.raw_bytes&&receipt.artifact.raw_sha256===link.storage.cell.raw_sha256,
     "Incremental receipt differs from complete profile index");
    audited=receipt.audit;
    requireValue(audited.cohort===spec.cohort&&audited.configuration===spec.configuration&&
     audited.dataset_sha256===old.cohorts[spec.cohort].dataset_sha256&&
     audited.payload_audit.queries===old.cohorts[spec.cohort].queries,"Incremental cell axis differs");
   }else audited=auditCell(raw,references[i],[spec.cohort,spec.configuration],old.cohorts[spec.cohort],context,config.recall_options);
   requireValue(audited.stored_sites.length>=previousSites.length&&previousSites.every((v,j)=>same(v,audited.stored_sites[j])),"Persistent site catalog changed prior identities");
   cells.push(audited);previousSites=audited.stored_sites;
  }
  const payloadCells=cells.map(c=>c.payload_audit),mismatches=payloadCells.flatMap(c=>c.mismatches);
  const declaredAudit={attempt:"round5-lm-sql-attribution-1",calls:4732n,cells:payloadCells,mismatches,
   all_full_non_timing_payloads_equal_to_v032_c2:mismatches.length===0,
   all_classification_sites_valid:payloadCells.every(c=>c.all_classification_sites_valid),
   retrieval_calls_executed_by_audit:0n,speed_claim:false,fresh_rows_decoded:0n};
  requireValue(cells.reduce((n,c)=>n+c.totals.queries,0n)===4732n,"Total rows not4732");
  return {cells,declaredAudit,clock:report.clock,clock_placement:report.clock_placement,
   unattributed_meaning:report.unattributed_meaning};
 }
 function auditSQL(input){
  const pins=input.pins;
  requireValue(pins&&COMMIT.test(pins.result_commit)&&COMMIT.test(pins.workflow_commit)&&
   COMMIT.test(pins.source_binding_commit)&&Number.isSafeInteger(pins.run_id)&&pins.run_attempt===1,"Execution input pins absent");
  const scope=textArtifact("scope",input.scope_text,PIN.scope),old=textArtifact("old binding",input.old_text,PIN.old),
   manifest=textArtifact("C2 manifest",input.manifest_text,PIN.manifest);
  requireValue(core.sha256Bytes(core.utf8bytes(input.producer_text))===PIN.producer,"Producer bytes differ");
  const metadata={};for(const k of ["source_binding","binding","storage","completion","payload_audit"])
   metadata[k]=textArtifact(k,input[k+"_text"],pins.metadata_sha256[k]);
  const frozen=metadata.source_binding.value,binding=metadata.binding.value,storage=metadata.storage.value;
  const runtime={commit:PIN.source,runtime_sha256:PIN.runtime,files_sha256:scope.value.runtime.files_sha256};
  requireValue(frozen.status==="frozen-after-artificial-proof-before-sql-attribution-corpus"&&
   frozen.attempt==="round5-lm-sql-attribution-1"&&same(frozen.runtime,runtime)&&
   frozen.scope_sha256===PIN.scope&&frozen.pairing_addendum_sha256===PIN.pairing&&
   frozen.classification_sha256===digest(scope.value.observer.source_mapping),"Frozen source/classification binding differs");
  requireValue(binding.attempt==="round5-lm-sql-attribution-1"&&same(binding.runtime,runtime)&&
   binding.scope_sha256===PIN.scope&&binding.pairing_addendum_sha256===PIN.pairing&&binding.publisher_addendum_sha256===PIN.publisher&&
   binding.source_binding_sha256===metadata.source_binding.sha256&&binding.workflow_commit===pins.workflow_commit&&
   String(binding.run_id)===String(pins.run_id)&&binding.calls_expected===4732n&&
   binding.comparison_engine_calls===0n&&binding.fresh_rows_decoded===0n&&binding.speed_claim===false&&binding.locomo_sha256===scope.value.sequence.locomo_raw_sha256,"Actual binding differs");
  requireValue(binding.artifact_files_sha256[PIN.scriptPath]===PIN.producer&&
   binding.artifact_files_sha256["tests/test_round5_lm_sql_attribution.py"]==="ea6b96e06bd4766741b90a401951d21aeddc3a23e75d58e50e560a159af90dc5"&&
   binding.artifact_files_sha256[".github/workflows/round5-lm-sql-attribution.yml"]==="4b972bad02fb9fafd1e6885ca441fc9348def85db788db6ec3dfabf5afbcb343"&&
   same(binding.artifact_files_sha256,frozen.artifact_files_sha256)&&
   same(binding.helpers_sha256,old.value.helpers_sha256)&&same(binding.helper_dependency_sha256,old.value.helper_dependency_sha256),"Bound producer/helper closure differs");
  const baseline=manifest.value,specs=scope.value.payload_reference.cells;
  requireValue(baseline.status==="completed"&&baseline.runtime_source_sha256===PIN.baselineRuntime&&
   baseline.script_sha256===PIN.helper&&baseline.expected_calls===4732n&&baseline.attempted_calls===4732n&&baseline.completed_calls===4732n,"Baseline profile identity/count differs");
  requireValue(same(specs,old.value.profile.baseline_cells)&&same(binding.profile_baseline_references.baseline_cells,specs)&&
   same(Object.keys(input.reference_base64).sort(),specs.map(s=>s.path).sort()),"Reference inventory differs");
  const codec=core.codecFromPinnedSource(input.pako_source),references=[],referenceIdentities=[];
  for(let i=0;i<8;i++){
   const spec=specs[i],row=baseline.cells[i];
   for(const field of ["cohort","configuration","bytes","sha256","uncompressed_sha256"])requireValue(row[field]===spec[field],"C2 manifest cell differs");
   requireValue(spec.path==="benchmarks/reports/round4-development/"+row.path,"C2 manifest path differs");
   const read=unpack(spec.path,input.reference_base64[spec.path],{bytes:spec.bytes,sha256:spec.sha256,raw_sha256:spec.uncompressed_sha256},codec);
   references.push(parseExact(core.strictUtf8(read.raw)));referenceIdentities.push(read.identity);
  }
  let profile,result;
  if(input.incremental){
   requireValue(input.incremental.cell_receipts.length===8,"Eight incremental receipts required");
   const index=input.incremental.profile_index,identity=index.profile_artifact;
   requireValue(identity.bytes===storage.bytes&&identity.sha256===storage.sha256&&
    identity.raw_bytes===storage.raw_bytes&&identity.raw_sha256===storage.raw_sha256,"Profile index identity differs");
   profile={identity};
   result=auditReport(index.header,references,scope.value,old.value,input.incremental);
  }else{
   profile=unpack("profile.json.gz",input.profile_base64,storage,codec);
   result=auditReport(parseExact(boundedUtf8(profile.raw)),references,scope.value,old.value);
  }
  requireValue(same(result.declaredAudit,metadata.payload_audit.value),"Declared complete payload/classification audit differs");
  const completion=metadata.completion.value;
  requireValue(completion.status==="completed"&&completion.attempt==="round5-lm-sql-attribution-1"&&
   completion.calls===4732n&&completion.complete_cells===8n&&
   completion.all_full_payloads_equal===result.declaredAudit.all_full_non_timing_payloads_equal_to_v032_c2&&
   completion.all_classification_sites_valid===result.declaredAudit.all_classification_sites_valid&&
   completion.fresh_rows_decoded===0n&&completion.comparison_engine_calls===0n&&
   completion.speed_claim===false&&completion.formal_or_release_acceptance===false,"Final completion declaration differs");
  return {schema_version:1n,status:result.declaredAudit.all_full_non_timing_payloads_equal_to_v032_c2&&result.declaredAudit.all_classification_sites_valid?
    "independently-verified-partial-native-boundary-attribution":"diagnostic-payload-or-classification-invalid",
   execution_pins:{...pins,run_id:BigInt(pins.run_id),run_attempt:BigInt(pins.run_attempt)},source_commit:PIN.source,runtime_sha256:PIN.runtime,producer_commit:PIN.producerCommit,producer_sha256:PIN.producer,
   scope_sha256:PIN.scope,original_schedule_sha256:PIN.old,reference_commit:PIN.reference,
   baseline_manifest_sha256:PIN.manifest,baseline_runtime_sha256:PIN.baselineRuntime,
   metadata:Object.fromEntries(Object.entries(metadata).map(([k,{value,...identity}])=>[k,identity])),
   profile_artifact:profile.identity,reference_artifacts:referenceIdentities,
   calls:4732n,all_full_non_timing_payloads_equal:result.declaredAudit.all_full_non_timing_payloads_equal_to_v032_c2,
   all_classification_sites_valid:result.declaredAudit.all_classification_sites_valid,
   mismatches:result.declaredAudit.mismatches,cells:result.cells,clock:result.clock,clock_placement:result.clock_placement,
   unattributed_meaning:result.unattributed_meaning,environment:binding.environment,
   numeric_encoding:"All counters and nanoseconds are exact JSON integer tokens; parser and sums use BigInt.",
   interpretation:"Partial instrumented native builtin boundaries only. Inclusive nesting can overlap; exclusive spans still include callbacks/scheduling/observer effects. The residual is unattributed, not Python-only. Bookkeeping is separate and never subtracted.",
   speed_claim:false,retrieval_calls_executed_by_audit:0n,fresh_rows_decoded:0n};
 }
 return {PIN,boundedUtf8,boundedBase64,profileIndex,auditStoredCell,parseExact,stringifyExact,digest,observation,categoryFor,validateSites,auditCell,auditReport,auditSQL,unpack,textArtifact};
};
