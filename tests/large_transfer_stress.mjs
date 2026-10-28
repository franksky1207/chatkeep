/* Synthetic end-to-end HTTP probe, no deployments/private artifacts on disk. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {Worker} from 'node:worker_threads';
import {createServer} from 'node:net';
import {readdir,readFile} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
import {TransferResults} from '../docs/local-backup/transfer-results.mjs';
import {sendPrepared} from '../docs/local-backup/transfer-client.mjs';
import {entries,entryBytes,verifyDocx} from '../docs/local-backup/transfer-zip.mjs';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function fixture(texts,padding=0){return {id:'selected-ONLY',title:'合成衍生對話',current_node:'m'+(texts.length-1),metadata:{PRIVATE_UNSENT_METADATA:'x'.repeat(padding)},mapping:{...Object.fromEntries(texts.map((text,i)=>['m'+i,{parent:i?'m'+(i-1):null,message:{id:'m'+i,author:{role:i%2?'assistant':'user'},content:{parts:[text]}}}])),'off':{parent:'m0',message:{id:'off',author:{role:'assistant'},content:{parts:['PRIVATE_OFF_BRANCH']}}}}};}
async function prepare(blob){const worker=new Worker(new URL('./transfer_node_worker.mjs',import.meta.url),{resourceLimits:{maxOldGenerationSizeMb:128}});try{return await new Promise((resolve,reject)=>{worker.once('message',resolve);worker.once('error',reject);worker.postMessage({type:'prepare',blob});});}finally{await worker.terminate();}}
const reservation=createServer();await new Promise(r=>reservation.listen(0,'127.0.0.1',r));const port=reservation.address().port;await new Promise(r=>reservation.close(r));
const gunicorn=spawn('.venv/bin/python',['-m','gunicorn','--config','gunicorn.conf.py','server:application'],{env:{...process.env,PORT:String(port)},stdio:['ignore','pipe','pipe']});
let logs='',stop=false,clientPeak=0,heapPeak=0,serverPeak=0;const cpuTicks=new Map();
for(const stream of [gunicorn.stdout,gunicorn.stderr])stream.on('data',b=>{logs+=b.toString();assert(logs.length<100000);});
async function sample(){const rows=new Map();for(const name of await readdir('/proc'))if(/^\d+$/.test(name))try{const [status,stat]=await Promise.all([readFile('/proc/'+name+'/status','utf8'),readFile('/proc/'+name+'/stat','utf8')]);const ppid=Number(status.match(/^PPid:\s+(\d+)/m)?.[1]),rss=Number(status.match(/^VmRSS:\s+(\d+)/m)?.[1]||0)*1024,fields=stat.slice(stat.lastIndexOf(')')+2).split(' ');rows.set(Number(name),{ppid,rss,cpu:Number(fields[11])+Number(fields[12])});}catch{}
 const ids=new Set([gunicorn.pid]);for(;;){let changed=false;for(const [id,row]of rows)if(ids.has(row.ppid)&&!ids.has(id)){ids.add(id);changed=true;}if(!changed)break;}
 let rss=0;for(const id of ids){const row=rows.get(id);if(row){rss+=row.rss;cpuTicks.set(id,Math.max(cpuTicks.get(id)||0,row.cpu));}}serverPeak=Math.max(serverPeak,rss);
 const memory=process.memoryUsage();clientPeak=Math.max(clientPeak,memory.rss);heapPeak=Math.max(heapPeak,memory.heapUsed);
}
const monitor=(async()=>{while(!stop){await sample();await sleep(20);}})();
const base='http://127.0.0.1:'+port;let requests=0;
async function request(packet){requests++;const body=JSON.stringify(packet),response=await fetch(base+'/api/convert-chunk-v1',{method:'POST',headers:{'Content-Type':'application/json'},body});return {status:response.status,value:await response.json(),retryAfter:response.headers.get('Retry-After'),bytes:Buffer.byteLength(body)};}
try{
 for(let i=0;i<60;i++){try{const r=await fetch(base);if(r.status===200)break;}catch{}if(i===59)throw Error('server readiness');await sleep(100);}
 for(const [name,conv]of [['metadata',fixture(['PRIVATE_SENT_TEXT','ANSWER😀'],4_200_000)],['effective-unicode',fixture(Array.from({length:4},(_,i)=>'PRIVATE_CHUNK_'+i+'\n'+'漢字'.repeat(300000)))]] ){
  const blob=new Blob([JSON.stringify(conv)]),start=performance.now(),prep=await prepare(blob);assert.equal(prep.type,'prepared');const prepared=prep.prepared;assert.equal(prepared.mode,'chunks');
  const collector=new TransferResults(prepared),sizes=[],statuses=[],requestStart=requests;
  await sendPrepared(prepared,{collector,send:async packet=>{assert(!JSON.stringify(packet).includes('PRIVATE_UNSENT_METADATA'));assert(!JSON.stringify(packet).includes('PRIVATE_OFF_BRANCH'));const r=await request(packet);sizes.push(r.bytes);statuses.push(r.status);return r;}});
  const final=await collector.finish();assert(final.report.complete);assert.equal(final.report.output_message_count,conv.mapping?Object.keys(conv.mapping).length-1:0);
  if(final.artifact_type==='zip'){const files=await entries(final.blob);for(let i=0;i<files.length;i++){const data=await entryBytes(final.blob,files[i]);await verifyDocx(new Blob([data]),final.report.volumes[i].first_message,final.report.volumes[i].last_message);}}
  console.log(JSON.stringify({case:name,selected_raw_bytes:blob.size,parts:prepared.chunks.length,request_bytes:sizes,total_transferred_bytes:sizes.reduce((a,b)=>a+b,0),requests:requests-requestStart,statuses,artifact:final.artifact_type,artifact_bytes:final.blob.size,volumes:final.report.docx_volume_count,messages:final.report.output_message_count,wall_seconds:Number(((performance.now()-start)/1000).toFixed(3)),worker_heap_mib:Number((prep.worker_metrics.heapUsed/1048576).toFixed(1)),client_rss_peak_mib:Number((clientPeak/1048576).toFixed(1)),client_main_heap_peak_mib:Number((heapPeak/1048576).toFixed(1)),server_tree_rss_peak_mib:Number((serverPeak/1048576).toFixed(1)),sampled_server_cpu_seconds:[...cpuTicks.values()].reduce((a,b)=>a+b,0)/100}));
  collector.cancel();
 }
 const broken=await prepare(new Blob([JSON.stringify(fixture(['```\n'+'x\n'.repeat(80000)+'```'],2_100_000))]));
 const failure=await request(broken.prepared.chunks[0]);assert.equal(failure.status,422);assert.equal(failure.value.error.code,'MESSAGE_TOO_LARGE');
 const tampered=structuredClone(broken.prepared.chunks[0]);tampered.messages[0].text='y'+tampered.messages[0].text.slice(1);const rejected=await request(tampered);assert.equal(rejected.status,422);assert.equal(rejected.value.error.code,'PART_HASH_MISMATCH');
 let actual429;for(let i=0;i<4;i++)actual429=await request({});assert.equal(actual429.status,429);assert.equal(actual429.value.error.code,'RATE_LIMITED');assert.equal(actual429.retryAfter,'60');
 console.log(JSON.stringify({actual429_status:actual429.status,retry_after:actual429.retryAfter,resource_failure:'MESSAGE_TOO_LARGE',corrupt_part:'PART_HASH_MISMATCH',total_http_requests:requests,server_cpu_observation:'sampled /proc utime+stime; 100Hz; includes master/worker/converters; short lifetime ticks can be missed',client_memory:'whole Node process RSS includes worker thread; main heap excludes worker heap; 20ms polling',pacing:'real >=6100ms start interval, no raised anonymous rate limit'}));
}finally{
 stop=true;await monitor;gunicorn.kill('SIGTERM');await new Promise(r=>gunicorn.once('close',r));assert(!logs.includes('PRIVATE_'),'private content leaked');
}
