/* Library only; no UI, app wiring, URL selection or CORS integration. */
import {check,fail,MAX_PARTS,MAX_RAW} from './transfer-format.mjs';
let preparing=false;
export function prepareInWorker(blob,{signal}={}){
 check(signal);if(!(blob instanceof Blob)||!blob.size||blob.size>MAX_RAW)fail('SELECTED_SOURCE_LIMIT');if(preparing)fail('BUSY');preparing=true;return new Promise((resolve,reject)=>{
  let worker;try{worker=new Worker(new URL('./transfer-worker.mjs',import.meta.url),{type:'module'});}catch{preparing=false;reject(Error('PREPARATION_FAILED'));return;}
  let settled=false;const finish=(fn,value)=>{if(settled)return;settled=true;preparing=false;signal?.removeEventListener('abort',cancel);worker.terminate();fn(value);};
  const cancel=()=>finish(reject,new DOMException('已取消','AbortError'));
  signal?.addEventListener('abort',cancel,{once:true});
  worker.onerror=()=>finish(reject,Error('PREPARATION_FAILED'));
  worker.onmessage=({data})=>{if(data.type==='prepared')finish(resolve,data.prepared);else{const e=Error(data.message);e.code=data.code;finish(reject,e);}};
  try{worker.postMessage({type:'prepare',blob});}catch{finish(reject,Error('PREPARATION_FAILED'));}
 });
}
const pause=(ms,signal)=>new Promise((resolve,reject)=>{
 check(signal);const cancel=()=>{clearTimeout(timer);reject(new DOMException('已取消','AbortError'));};
 const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},ms);signal?.addEventListener('abort',cancel,{once:true});
});
export async function sendPrepared(prepared,{send,collector,signal,indices,wait=pause,now=()=>performance.now(),interval=6100}={}){
 if(prepared.mode!=='chunks'||typeof send!=='function'||!collector)fail('INVALID_TRANSFER');
 // One invocation is strictly sequential. A resumed invocation gets an initial
 // cooldown as well; server RateLimit remains authoritative across tabs/jobs.
 let last=now(),started=last;
 const requested=indices??prepared.chunks.map(c=>c.part_index);
 if(requested.length>MAX_PARTS||new Set(requested).size!==requested.length)fail('PART_ORDER');
 if(collector.sending)fail('BUSY');collector.sending=true;
 try{
 for(const index of requested){
  if(!Number.isInteger(index)||index<1||index>prepared.chunks.length)fail('PART_ORDER');
  for(let attempt=0;;attempt++){
   check(signal);if(now()-started>900000)fail('TRANSFER_TIMEOUT');
   await wait(Math.max(0,last+Math.max(6100,interval)-now()),signal);check(signal);last=now();
   const controller=new AbortController();
   const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
   let timer;
   try{
    const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{const e=Error('BATCH_TIMEOUT');e.code='BATCH_TIMEOUT';reject(e);controller.abort();},55000);});
    const aborted=new Promise((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new DOMException('已取消','AbortError')),{once:true}));
    const result=await Promise.race([send(prepared.chunks[index-1],{signal:controller.signal}),timeout,aborted]);
    check(signal);
    if(result.status===429){if(attempt>=2)fail(result.value?.error?.code==='BUSY'?'BUSY':'RATE_LIMITED');const retry=Number(result.retryAfter??60);await wait(Math.min(120000,Math.max(2000,Number.isFinite(retry)?retry*1000:60000)),signal);continue;}
    if(result.status!==200)fail(result.value?.error?.code||'BATCH_FAILED');
    await collector.accept(index,result.value,{signal});break;
   }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
  }
 }
 return collector;
 }catch(e){if(e.name==='AbortError')collector.cancel?.();throw e;}finally{collector.sending=false;}
}

