"use strict";
/* Exact adapter for root's frozen source-free gzip-byte export.
 * Does not change statistics or reconstruct/recompress measurement JSON.
 */
module.exports=function assembleTransport(core,api,entry,texts,original){
 const need=(x,m)=>{if(!x)throw Error(m);},source=entry.source;
 need(source.path===original.path&&source.git_blob===original.git_blob&&source.bytes===original.bytes&&source.sha256===original.sha256,
  "Transport source differs from frozen original Git/completion identity");
 need(entry.reassembled_sha256===original.sha256&&entry.reassembled_bytes===original.bytes,"Transport whole-file receipt differs");
 need(Array.isArray(texts)&&texts.length===entry.chunks.length,"Transport text inventory differs");
 const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 for(let i=0;i<texts.length;i++){
  const item=texts[i],claim=entry.chunks[i],text=item.text;
  need(item.path===claim.path&&typeof text==="string"&&text.endsWith("\n")&&text.indexOf("\n")===text.length-1&&
   !/[\t\r ]/.test(text),"Chunk requires canonical ASCII base64 and exactly one final newline");
  const encoded=text.slice(0,-1);
  need(BigInt(text.length)===claim.base64_bytes&&claim.base64_bytes<=640001n&&
   core.sha256Bytes(core.utf8bytes(text))===claim.base64_sha256,"Chunk encoded byte identity differs");
  for(const char of encoded)need(char==="="||alphabet.includes(char),"Non-base64 character");
  // The original decoder validates length/alphabet/padding placement. These
  // final low bits additionally reject noncanonical encodings of equal bytes.
  if(encoded.endsWith("=="))need((alphabet.indexOf(encoded.at(-3))&15)===0,"Noncanonical double-padding bits");
  else if(encoded.endsWith("="))need((alphabet.indexOf(encoded.at(-2))&3)===0,"Noncanonical padding bits");
 }
 const bytes=api.reassembleChunks(texts.map(t=>t.text),{bytes:source.bytes,sha256:source.sha256,chunks:entry.chunks},original);
 return {bytes,identity:{source_path:source.path,source_git_blob:source.git_blob,compressed_bytes:source.bytes,compressed_sha256:source.sha256,
  chunks:BigInt(texts.length),encoded_and_raw_chunk_hashes_verified:true,original_complete_compressed_hash_verified:true,
  measurement_data_transformed:false}};
};
