/* Transactional verifier/assembler for one pinned local prepared selection. */
import {canonical,sha,partSha,encoder,bytesSha,charCount,check,fail} from './transfer-format.mjs';
import {entries,entryBytes,verifyDocx,writeZip,MAX_OUTPUT} from './transfer-zip.mjs';
const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const same=(a,b)=>canonical(a)===canonical(b);
function safeStem(title){let name=String(title).replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g,'_').replace(/^[ .]+|[ .]+$/g,'');name=Array.from(name).slice(0,100).join('');while(encoder.encode(name).length>200)name=Array.from(name).slice(0,-1).join('');if(!name)name='未命名對話';if(/^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])$/i.test(name.split('.')[0]))name='_'+name;return name;}
async function legacyDigest(messages){const parts=[];let size=0;for(const m of messages){const encoded=encoder.encode(JSON.stringify([m.id,m.role,m.text])),length=new Uint8Array(8);new DataView(length.buffer).setBigUint64(0,BigInt(encoded.length));parts.push(length,encoded);size+=8+encoded.length;}const all=new Uint8Array(size);let p=0;for(const a of parts){all.set(a,p);p+=a.length;}return bytesSha(all);}
function decode64(value){if(typeof value!=='string'||value.length>21_333_336||value.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(value))fail('INVALID_ARTIFACT');let raw;try{raw=atob(value);}catch{fail('INVALID_ARTIFACT');}if(raw.length>MAX_OUTPUT)fail('OUTPUT_LIMIT');const out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return new Blob([out]);}
export class TransferResults{
 constructor(prepared){if(prepared.mode!=='chunks')fail('INVALID_TRANSFER');this.prepared=prepared;this.manifestCanonical=canonical(prepared.manifest);this.results=new Map();this.cancelled=false;this.busy=false;}
 cancel(){this.cancelled=true;this.results.clear();}
 async accept(index,value,{signal}={}){
  if(this.busy)fail('BUSY');this.busy=true;
  try{
   check(signal);if(this.cancelled)fail('TRANSFER_CANCELLED');const {manifest,chunks}=this.prepared,part=manifest.parts[index-1],chunk=chunks[index-1];
   if(canonical(manifest)!==this.manifestCanonical)fail('MANIFEST_MISMATCH');
   if(!part||!value?.ok||value.api_version!==2)fail('INVALID_RESPONSE');
   const unsigned={...manifest};delete unsigned.conversation_key;
   if(await sha(unsigned)!==manifest.conversation_key||await sha(manifest.parts)!==manifest.sequence_sha256||await partSha(chunk.messages)!==part.sequence_sha256)fail('MANIFEST_MISMATCH');
   const expected={schema_version:'chatkeep.chunk.v1',conversation_key:manifest.conversation_key,manifest_sha256:manifest.conversation_key,part_index:index,part_total:manifest.parts.length,
    first_message:part.first_message,last_message:part.last_message,message_count:part.message_count,part_sequence_sha256:part.sequence_sha256,sequence_sha256:manifest.sequence_sha256};
   if(!same(value.transfer,expected))fail('CONVERSATION_MISMATCH');
   const report=value.report;
   if(!report||!Array.isArray(report.warnings)||report.warnings.length>32||report.source!=='official_json_derived'||!same(report.client_source_counts,manifest.source_counts)||report.complete!==false||report.chunk_complete!==true||report.source_verified_by_server!==false||report.server_validated_scope!=='this_chunk_only'||report.truncated!==false||report.duplicated!==false||report.missing!==false||report.expected_output_message_count!==part.message_count||report.output_message_count!==part.message_count)fail('INVALID_RESPONSE');
   if(!Array.isArray(report.volumes)||!report.volumes.length||report.volumes.length>16||report.docx_volume_count!==report.volumes.length)fail('VOLUME_LIMIT');
   const blob=decode64(value.document),files=[];
   if(value.artifact_type==='docx'&&value.mime_type===DOCX&&report.volumes.length===1)files.push({name:value.filename,blob});
   else if(value.artifact_type==='zip'&&value.mime_type==='application/zip'&&report.volumes.length>1){for(const e of await entries(blob,{signal})){await entryBytes(blob,e,{signal});files.push({name:e.name,blob:blob.slice(e.start,e.start+e.compressed)});}}
   else fail('INVALID_ARTIFACT');
   if(files.length!==report.volumes.length)fail('VOLUME_LIMIT');let position=part.first_message,total=0;
   for(let i=0;i<files.length;i++){
    check(signal);const file=files[i],volume=report.volumes[i];
    if(!volume||typeof volume!=='object')fail('INVALID_RESPONSE');
    if(volume.number!==i+1||file.name!==volume.filename||volume.first_message!==position||!Number.isSafeInteger(volume.last_message)||volume.last_message<position||volume.last_message>part.last_message||volume.message_count!==volume.last_message-position+1||volume.docx_bytes!==file.blob.size)fail('PART_ORDER');
    const subset=chunk.messages.slice(position-part.first_message,volume.last_message-part.first_message+1);
    if(await legacyDigest(subset)!==volume.sequence_sha256||await bytesSha(new Uint8Array(await file.blob.arrayBuffer()))!==volume.file_sha256)fail('ARTIFACT_HASH');
    await verifyDocx(file.blob,volume.first_message,volume.last_message,{signal});position=volume.last_message+1;total+=file.blob.size;
   }
   if(position!==part.last_message+1||report.sequence_sha256!==await legacyDigest(chunk.messages))fail('PART_ORDER');
   let count=files.length,size=total;for(const [partIndex,r]of this.results)if(partIndex!==index){count+=r.files.length;size+=r.bytes;}
   if(count>16)fail('VOLUME_LIMIT');if(size+16384>MAX_OUTPUT)fail('OUTPUT_LIMIT');
   check(signal);if(this.cancelled)fail('TRANSFER_CANCELLED');this.results.set(index,{files,bytes:total,volumes:report.volumes.map(v=>({...v})),warnings:structuredClone(report.warnings)});
  }catch(e){if(e.name==='AbortError')this.cancel();throw e;}finally{this.busy=false;}
 }
 async finish({signal}={}){
  if(signal?.aborted)this.cancel();check(signal);if(this.cancelled)fail('TRANSFER_CANCELLED');if(this.busy)fail('BUSY');this.busy=true;
  try{
  const {manifest}=this.prepared;if(canonical(manifest)!==this.manifestCanonical)fail('MANIFEST_MISMATCH');if(this.results.size!==manifest.parts.length)fail('MISSING_PART');
  const files=[],volumes=[],warnings=[];let position=1;
  for(let index=1;index<=manifest.parts.length;index++){
   const result=this.results.get(index),part=manifest.parts[index-1];if(!result||part.first_message!==position)fail('MISSING_PART');
   for(let j=0;j<result.files.length;j++){const file=result.files[j],v=result.volumes[j],number=files.length+1,name=safeStem(manifest.title)+'_第'+number+'卷.docx';files.push({name,blob:file.blob});volumes.push({...v,number,filename:name,part_index:index,part_volume_number:v.number});}
   position=part.last_message+1;warnings.push(...result.warnings);
  }
  if(position!==manifest.total_message_count+1)fail('PART_ORDER');
  for(let i=0;i<this.prepared.chunks.length;i++)if(await partSha(this.prepared.chunks[i].messages)!==manifest.parts[i].sequence_sha256)fail('MANIFEST_MISMATCH');
  const ids=new Set();let chars=0;for(const chunk of this.prepared.chunks)for(const m of chunk.messages){if(ids.has(m.id))fail('DUPLICATE_MESSAGE');ids.add(m.id);chars+=charCount(m.text);}
  if(chars!==manifest.total_text_chars||ids.size!==manifest.total_message_count)fail('PART_COUNT');
  const single=files.length===1,blob=single?new Blob([files[0].blob],{type:DOCX}):await writeZip(files,{signal});
  if(single)volumes[0].filename=safeStem(manifest.title)+'.docx';check(signal);if(this.cancelled)fail('TRANSFER_CANCELLED');
  return {blob,filename:safeStem(manifest.title)+(single?'.docx':'_完整對話.zip'),artifact_type:single?'docx':'zip',mime_type:single?DOCX:'application/zip',
   report:{status:'converted_with_warnings',complete:true,all_parts_verified:true,source_verified_by_server:false,integrity_basis:'browser_derived_sequence',
    source:'official_json_derived',conversation_key:manifest.conversation_key,sequence_sha256:manifest.sequence_sha256,
    expected_output_message_count:manifest.total_message_count,output_message_count:manifest.total_message_count,
    docx_volume_count:files.length,volumes,warnings,client_source_counts:manifest.source_counts,truncated:false,duplicated:false,missing:false}};
  }catch(e){if(e.name==='AbortError')this.cancel();throw e;}finally{this.busy=false;}
 }
}
