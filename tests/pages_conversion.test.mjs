import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {ConversionQueue,apiBase,shareURL,transport,verifyEnvelope,safeFilename,DOCX} from '../docs/local-backup/conversion.mjs';
import {prepareSelected} from '../docs/local-backup/transfer-format.mjs';
function fixture(texts=['ONE','TWO'],padding=0){return {title:'Synthetic',current_node:'m'+(texts.length-1),mapping:Object.fromEntries(texts.map((text,i)=>['m'+i,{parent:i?'m'+(i-1):null,message:{id:'m'+i,author:{role:i%2?'assistant':'user'},content:{content_type:'text',parts:[text]}}}])),metadata:'PRIVATE_METADATA'+('x'.repeat(padding))};}
const source=c=>new Blob([JSON.stringify(c)]);
function convert(mode,input){const p=spawnSync('.venv/bin/python',['official_worker.py',mode],{input:typeof input==='string'?input:JSON.stringify(input),encoding:'utf8',maxBuffer:24_000_000});assert.equal(p.status,0);return JSON.parse(p.stdout);}
const opts={base:'http://localhost:8000',featureCheck:()=>{},wait:async()=>{},prepare:prepareSelected};
let single;
test('safe config, URLs, MIME and streamed envelope limits',async()=>{
 assert.equal(apiBase('http://localhost:8000'),'http://localhost:8000');
 for(const value of ['', 'http://evil.test','https://u:p@evil.test','https://evil.test/path','https://evil.test/?private=1'])assert.throws(()=>apiBase(value));
 assert.throws(()=>shareURL('https://evil.test/share/x'));assert.throws(()=>shareURL('https://chatgpt.com/share/00000000-0000-0000-0000-000000000000?private=x'));
 assert.equal(safeFilename('../CON.docx','docx'),'_CON.docx');
 let request;const result=await transport(opts.base,'/api/convert-v2',{url:'synthetic'},{fetcher:async(url,o)=>{request={url,...o};return new Response('{"ok":false}',{headers:{'Content-Type':'application/json','Retry-After':'60'},status:429});}});
 assert.equal(result.status,429);assert.equal(result.retryAfter,'60');assert.equal(request.credentials,'omit');assert.equal(request.referrerPolicy,'no-referrer');assert(!request.url.includes('synthetic'));
 await assert.rejects(()=>transport(opts.base,'/api/convert-v2',{}, {fetcher:async()=>new Response('<html>',{status:404})}),e=>e.code==='API_UNAVAILABLE');
 await assert.rejects(()=>transport(opts.base,'/api/convert-v2',{}, {fetcher:async()=>{throw Error('private');}}),e=>e.code==='NETWORK_OR_CORS');
 await assert.rejects(()=>transport(opts.base,'/api/convert-v2',{}, {fetcher:async()=>new Response('{}',{headers:{'Content-Type':'application/json','Content-Length':'24000001'}})}),e=>e.code==='OUTPUT_LIMIT');
});
test('small selected official uses original single API, independent reports and sequential multi-select',async()=>{
 const seen=[],extracted=[];let inflight=0,peak=0;
 const queue=new ConversionQueue({...opts,extract:async item=>{extracted.push(item.id);return source(fixture([item.id]));},send:async(base,path,body)=>{
  inflight++;peak=Math.max(peak,inflight);seen.push(path);const result=convert('official',await body.text());inflight--;return result;
 }});
 await queue.run([{id:'SELECTED_1',title:'one'},{id:'SELECTED_2',title:'two'}]);
 assert.deepEqual(extracted,['SELECTED_1','SELECTED_2']);assert.deepEqual(seen,['/api/convert-json','/api/convert-json']);assert.equal(peak,1);
 assert(queue.jobs.every(j=>j.state==='done'));single=queue.jobs[0].artifact;assert.equal(single.mime_type,DOCX);assert.equal(single.report.output_message_count,1);
 queue.release(queue.jobs[0]);assert(queue.jobs[0].report);assert.equal(queue.jobs[0].artifact,null);queue.dispose();assert.equal(queue.retained,0);
});
test('strict single envelope rejects unknown MIME, corrupted file, report ranges and cancellation',async()=>{
 const response=convert('official',fixture()).value;
 for(const mutate of [x=>x.mime_type='text/plain',x=>x.api_version=1,x=>x.report.volumes[0].first_message=2,x=>x.document='AAAA',x=>x.document='!!!!']){
  const v=structuredClone(response);mutate(v);await assert.rejects(()=>verifyEnvelope(v));
 }
 const controller=new AbortController();controller.abort();await assert.rejects(()=>verifyEnvelope(response,{signal:controller.signal}),e=>e.name==='AbortError');
});
test('share mode selects v2 endpoint and verifies DOCX and ZIP envelopes',async()=>{
 const docx=convert('official',fixture()).value;docx.report.source='share_link';
 const zip=convert('official',fixture(Array.from({length:100},()=> 'line\n'.repeat(1000)))).value;zip.report.source='share_link';assert.equal(zip.artifact_type,'zip');
 for(const value of [docx,zip]){
  const paths=[];const q=new ConversionQueue({...opts,send:async(base,path)=>{paths.push(path);return {status:200,value};}});
  await q.run([{url:'https://chatgpt.com/share/00000000-0000-0000-0000-000000000000',title:'share'}]);
  assert.deepEqual(paths,['/api/convert-v2']);assert.equal(q.jobs[0].state,'done');assert.equal(q.jobs[0].artifact.artifact_type,value.artifact_type);q.dispose();
 }
});
test('large selected source strips metadata, retries only missing batch and preserves previous success',async()=>{
 const calls=[];let failed=false;
 const q=new ConversionQueue({...opts,extract:async i=>source(fixture(i.id===1?['small']:Array(3).fill('漢'.repeat(600000)),i.id===1?0:2_100_000)),send:async(base,path,payload)=>{
  if(path==='/api/convert-json')return convert('official',await payload.text());
  calls.push(payload.part_index);assert(!JSON.stringify(payload).includes('PRIVATE_METADATA'));
  if(payload.part_index===2&&!failed){failed=true;throw Error('NETWORK_OR_CORS');}return convert('chunk',payload);
 }});
 await q.run([{id:1,title:'small'},{id:2,title:'large'}]);assert.equal(q.jobs[0].state,'done');assert.equal(q.jobs[1].state,'failed');assert.deepEqual([...q.jobs[1].collector.results.keys()],[1]);
 await q.resume();assert.deepEqual(calls,[1,2,2,3]);assert.equal(q.jobs[1].state,'done');assert.equal(q.jobs[1].artifact.artifact_type,'zip');assert.equal(q.jobs[1].report.integrity_basis,'browser_derived_sequence');q.dispose();
});
test('429 bounded retries and Retry-After, errors and Worker restart',async()=>{
 let calls=0;const waits=[];const q=new ConversionQueue({...opts,wait:async ms=>waits.push(ms),send:async()=>{calls++;return {status:429,retryAfter:'60',value:{error:{code:'RATE_LIMITED'}}};}});
 await q.run([{url:'https://chatgpt.com/share/00000000-0000-0000-0000-000000000000',title:'s'}]);assert.equal(calls,3);assert.equal(q.jobs[0].error,'RATE_LIMITED');assert.equal(waits.filter(x=>x===60000).length,2);
 let attempts=0;const r=new ConversionQueue({...opts,extract:async()=>source(fixture()),prepare:async blob=>{if(!attempts++)throw Error('PREPARATION_FAILED');return prepareSelected(blob);},send:async(b,p,blob)=>convert('official',await blob.text())});
 await r.run([{title:'worker'}]);assert.equal(r.jobs[0].error,'PREPARATION_FAILED');await r.resume();assert.equal(r.jobs[0].state,'done');r.dispose();
});
test('cancel aborts active transport, clears partial state and never publishes late result',async()=>{
 let entered;const started=new Promise(r=>entered=r);let signal;
 const q=new ConversionQueue({...opts,send:async(b,p,body,o)=>{signal=o.signal;entered();await new Promise(resolve=>o.signal.addEventListener('abort',resolve,{once:true}));return convert('official',fixture());}});
 const work=q.run([{url:'https://chatgpt.com/share/00000000-0000-0000-0000-000000000000',title:'cancel'},{title:'pending'}]);await started;q.cancel();await work;
 assert(signal.aborted);assert(q.jobs.every(j=>j.state==='cancelled'&&!j.artifact&&!j.prepared));assert.equal(q.retained,0);
});
test('retained budget pauses before extraction, release permits continuation',async()=>{
 let extracts=0;const q=new ConversionQueue({...opts,extract:async()=>{extracts++;return source(fixture());},send:async(b,p,blob)=>convert('official',await blob.text())});
 q.retained=16_000_001;await q.run([{title:'budget'}]);assert.equal(extracts,0);assert.equal(q.jobs[0].state,'pending');q.retained=0;await q.resume();assert.equal(q.jobs[0].state,'done');q.dispose();
});
