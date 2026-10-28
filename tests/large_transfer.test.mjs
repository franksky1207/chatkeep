import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {prepareSelected,normalizeSelected,parseSelected,canonical,sha,partSha,encoder,MAX_RAW} from '../docs/local-backup/transfer-format.mjs';
import {TransferResults} from '../docs/local-backup/transfer-results.mjs';
import {entries,entryBytes,verifyDocx,writeZip} from '../docs/local-backup/transfer-zip.mjs';
import {sendPrepared} from '../docs/local-backup/transfer-client.mjs';
const nonce='0123456789abcdef0123456789abcdef';
export function fixture(texts=['你好😀','ANSWER'],padding=0){
 const mapping=Object.fromEntries(texts.map((text,i)=>['m'+i,{id:'m'+i,parent:i?'m'+(i-1):null,message:{id:'m'+i,author:{role:i%2?'assistant':'user'},content:{content_type:'text',parts:[text]}}}]));
 mapping.off={parent:'m0',message:{id:'off',author:{role:'assistant'},content:{content_type:'text',parts:['OFF_BRANCH_PRIVATE']}}};
 return {id:'選取ID😀',title:'../文明戰線101/😀',mapping,current_node:'m'+(texts.length-1),metadata:{never_upload:'PRIVATE_METADATA_'+('x'.repeat(padding))}};
}
const blob=c=>new Blob([JSON.stringify(c)]);
export function convert(chunk){const p=spawnSync('.venv/bin/python',['official_worker.py','chunk'],{input:JSON.stringify(chunk),encoding:'utf8',maxBuffer:24_000_000,timeout:45000});assert.equal(p.status,0,p.stderr);assert.equal(p.stderr,'');return JSON.parse(p.stdout);}
const code=c=>e=>e.code===c;
let large,reply;
test('small conversation retains original API and Blob bytes',async()=>{
 const source=blob(fixture());const p=await prepareSelected(source,{nonce});assert.equal(p.mode,'official');assert.equal(p.path,'/api/convert-json');assert.equal(p.blob,source);
});
test('selected raw >2MB drops metadata/other branches and yields verified single DOCX',async()=>{
 const source=blob(fixture(undefined,2_200_000));assert(source.size>2_000_000);
 large=await prepareSelected(source,{nonce});assert.equal(large.mode,'chunks');assert.equal(large.chunks.length,1);
 const payload=JSON.stringify(large.chunks[0]);assert(!payload.includes('PRIVATE_METADATA'));assert(!payload.includes('OFF_BRANCH_PRIVATE'));assert(payload.length<5000);
 reply=convert(large.chunks[0]);assert.equal(reply.status,200);assert.equal(reply.value.report.complete,false);assert.equal(reply.value.report.chunk_complete,true);
 const result=new TransferResults(large);await result.accept(1,reply.value);const final=await result.finish();assert.equal(final.artifact_type,'docx');assert(final.report.complete);assert.equal(final.report.source_verified_by_server,false);
 await verifyDocx(final.blob,1,2);
});
test('retry is logically idempotent; missing, swapped, mixed and corrupted parts are rejected',async()=>{
 const result=new TransferResults(large);await assert.rejects(()=>result.finish(),code('MISSING_PART'));
 await result.accept(1,reply.value);const retried=convert(large.chunks[0]);assert.equal(retried.status,200);await result.accept(1,retried.value);assert.equal(result.results.size,1);await assert.rejects(()=>verifyDocx(new Blob([Buffer.from(reply.value.document,'base64')]),2,3),code('BOOKMARK_MISMATCH'));
 const bad=structuredClone(reply.value);bad.transfer.part_index=2;await assert.rejects(()=>result.accept(1,bad),code('CONVERSATION_MISMATCH'));
 const mixed=structuredClone(reply.value);mixed.transfer.conversation_key='0'.repeat(64);await assert.rejects(()=>result.accept(1,mixed),code('CONVERSATION_MISMATCH'));
 const corrupt=structuredClone(reply.value);corrupt.document=corrupt.document.slice(0,50)+(corrupt.document[50]==='A'?'B':'A')+corrupt.document.slice(51);await assert.rejects(()=>result.accept(1,corrupt),code('ARTIFACT_HASH'));
 const mutated=structuredClone(large);const collector=new TransferResults(mutated);mutated.manifest.title='other';await assert.rejects(()=>collector.accept(1,reply.value),code('MANIFEST_MISMATCH'));
 result.cancel();await assert.rejects(()=>result.finish(),code('TRANSFER_CANCELLED'));
});
test('backend rejects tampered hashes, false complete, unsupported roles and wrong order',()=>{
 for(const change of [p=>p.messages[0].text+='tampered',p=>p.complete=true,p=>p.part_index=2,p=>p.messages[0].role='tool',p=>p.manifest.parts[0].first_message=2,p=>p.manifest.conversation_key='0'.repeat(64)]){
  const packet=structuredClone(large.chunks[0]);change(packet);const r=convert(packet);assert.equal(r.status,422);assert(!r.value.document);assert(r.value.error.code);
 }
});
test('current branch, tools/hidden/empty and parser validation fail closed',async()=>{
 const c=fixture(['USER','ANSWER'],2_100_000);let parent='m1';
 for(const [id,role,extra,text]of [['hidden','assistant',{metadata:{is_visually_hidden_from_conversation:true}},'PRIVATE_HIDDEN'],['tool','tool',{},'PRIVATE_TOOL'],['empty','user',{},'']]){c.mapping[id]={parent,message:{id,author:{role},content:{parts:[text]},...extra}};parent=id;}c.current_node=parent;
 const p=await prepareSelected(blob(c),{nonce});assert.equal(p.manifest.total_message_count,2);assert.equal(p.manifest.source_counts.active_path_message_count,5);assert.equal(p.manifest.source_counts.skipped_categories.hidden,1);assert(!JSON.stringify(p.chunks).includes('PRIVATE_HIDDEN'));
 for(const mutate of [x=>x.current_node='missing',x=>x.mapping.m0.parent='m1',x=>x.mapping.m1.message.id='m0',x=>x.mapping.m1.message.content={content_type:'multimodal_text',parts:['caption',{image:'x'}]},x=>x.mapping.m1.message.status=null,x=>x.mapping.m1.message.content.content_type=null]){
  const broken=fixture();mutate(broken);assert.throws(()=>normalizeSelected(broken));
 }
 assert.throws(()=>parseSelected('{"title":"a","title":"b"}'),code('INVALID_JSON'));assert.throws(()=>parseSelected('['.repeat(33)+']'.repeat(33)),code('STRUCTURE_LIMIT'));
 const whitespace=normalizeSelected(fixture(['\u0085','\ufeff']));assert.equal(whitespace.messages.length,1);assert.equal(whitespace.messages[0].text,'\ufeff');
 assert.throws(()=>parseSelected('{"x":1e999}'),code('INVALID_JSON'));assert.throws(()=>parseSelected('{"x":"\\ud800"}'),code('INVALID_CHARACTERS'));
});
test('large effective Unicode text crosses multiple real requests with global bookmarks and final ZIP CRC',async()=>{
 const texts=Array.from({length:4},(_,i)=>'PART_'+i+'😀\n'+('漢字'.repeat(300000)));
 const source=blob(fixture(texts));assert(source.size>7_000_000);const prepared=await prepareSelected(source,{nonce});assert.equal(prepared.chunks.length,4);
 const collector=new TransferResults(prepared);
 for(let i=0;i<4;i++){assert(encoder.encode(JSON.stringify(prepared.chunks[i])).length<=2_000_000);const response=convert(prepared.chunks[i]);assert.equal(response.status,200);if(i===1)await assert.rejects(()=>collector.accept(1,response.value),code('CONVERSATION_MISMATCH'));await collector.accept(i+1,response.value);if(i===2)await assert.rejects(()=>collector.finish(),code('MISSING_PART'));}
 const final=await collector.finish();assert.equal(final.artifact_type,'zip');assert.equal(final.report.output_message_count,4);const files=await entries(final.blob);assert.equal(files.length,4);
 for(let i=0;i<files.length;i++){const data=await entryBytes(final.blob,files[i]);await verifyDocx(new Blob([data]),i+1,i+1);assert(files[i].name.endsWith('_第'+(i+1)+'卷.docx'));}
});
test('one chunk may contain multiple Word volumes; final indices and volume names remain global',async()=>{
 const c=fixture(Array.from({length:100},(_,i)=>'UNIQUE_'+i+'\n'+'line\n'.repeat(1000)),2_100_000),prepared=await prepareSelected(blob(c),{nonce});assert.equal(prepared.chunks.length,1);
 const r=convert(prepared.chunks[0]);assert.equal(r.status,200);assert.equal(r.value.artifact_type,'zip');const collector=new TransferResults(prepared);await collector.accept(1,r.value);const final=await collector.finish();assert.equal(final.report.docx_volume_count,2);
 const files=await entries(final.blob);assert.equal(files.length,2);
});
test('selection, message, transfer and final ZIP bounds are explicit',async()=>{
 await assert.rejects(()=>prepareSelected(new Blob([new Uint8Array(MAX_RAW+1)])),code('SELECTED_SOURCE_LIMIT'));
 await assert.rejects(()=>prepareSelected(blob(fixture(['x'.repeat(1_000_001)]))),code('MESSAGE_TOO_LARGE'));
 await assert.rejects(()=>prepareSelected(blob(fixture(['漢'.repeat(800000)]))),code('CHUNK_TOO_LARGE'));
 assert.throws(()=>normalizeSelected(fixture(Array(6).fill('x'.repeat(900000)))),code('TRANSFER_LIMIT'));
 await assert.rejects(()=>writeZip([{name:'a.docx',blob:new Blob([new Uint8Array(16_000_000)])}]),code('OUTPUT_LIMIT'));
 const collector=new TransferResults(large);const altered=structuredClone(reply.value);altered.report.truncated=true;await assert.rejects(()=>collector.accept(1,altered),code('INVALID_RESPONSE'));
});
test('sequential paced requests, bounded 429 retry, designated part retry and cancellation',async()=>{
 const prepared={mode:'chunks',chunks:[{part_index:1}]};
 let clock=0,attempts=0,accepted=0;const waits=[],collector={accept:async()=>{accepted++;}},wait=async n=>{waits.push(n);clock+=n;};
 await sendPrepared(prepared,{send:async()=>++attempts===1?{status:429,retryAfter:60}:{status:200,value:{}},collector,wait,now:()=>clock,indices:[1]});assert.equal(attempts,2);assert.equal(accepted,1);assert(waits.includes(60000));assert(waits[0]>=6100);
 attempts=0;await assert.rejects(()=>sendPrepared(prepared,{send:async()=>{attempts++;return{status:429};},collector,wait,now:()=>clock}),code('RATE_LIMITED'));assert.equal(attempts,3);await assert.rejects(()=>sendPrepared(prepared,{send:async()=>({status:429,value:{error:{code:'BUSY'}}}),collector,wait,now:()=>clock}),code('BUSY'));
 const controller=new AbortController();let sent=false;await assert.rejects(()=>sendPrepared(prepared,{send:async()=>{sent=true;return new Promise(()=>{});},collector,signal:controller.signal,wait:async()=>{controller.abort();},now:()=>clock}),e=>e.name==='AbortError');assert.equal(sent,false);
});
test('canonical cross-language vectors include Unicode, escapes and deterministic manifest',async()=>{
 const messages=[{id:'α😀',role:'user',text:'繁中\n"quote"\\slash😀'},{id:'β',role:'assistant',text:'English\t<&>'}];
 const vector={canonical:canonical(messages.map(m=>[m.id,m.role,m.text])),part:await partSha(messages)};
 const python=spawnSync('.venv/bin/python',['-c','import sys,json;from chunk_transfer import part_sha,canonical;m=json.load(sys.stdin);print(json.dumps({"canonical":canonical([[x["id"],x["role"],x["text"]]for x in m]).decode(),"part":part_sha(m)},ensure_ascii=False))'],{input:JSON.stringify(messages),encoding:'utf8'});assert.equal(python.status,0);assert.deepEqual(JSON.parse(python.stdout),vector);assert.equal(vector.part,'e3ee668688256fc84a3a9dc66cb27ca49ab378ee2a8f702c03c846799c1c6c06');
});

test('a forged cross-part duplicate source cannot be completed even if individual chunks verify',async()=>{
 const manifest=structuredClone(large.manifest);delete manifest.conversation_key;
 manifest.parts.push({...manifest.parts[0],part_index:2,first_message:3,last_message:4});
 manifest.total_message_count=4;manifest.total_text_chars*=2;
 Object.assign(manifest.source_counts,{raw_node_count:5,active_path_node_count:4,active_path_message_count:4,output_message_count:4});
 manifest.sequence_sha256=await sha(manifest.parts);manifest.conversation_key=await sha(manifest);
 const prepared={mode:'chunks',manifest,chunks:[1,2].map(part_index=>({schema_version:'chatkeep.chunk.v1',manifest,part_index,messages:large.chunks[0].messages}))},collector=new TransferResults(prepared);
 for(let i=1;i<=2;i++){const value=convert(prepared.chunks[i-1]);assert.equal(value.status,200);await collector.accept(i,value.value);}
 await assert.rejects(()=>collector.finish(),code('DUPLICATE_MESSAGE'));
});
