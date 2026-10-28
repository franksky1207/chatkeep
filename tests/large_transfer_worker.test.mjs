import test from 'node:test';
import assert from 'node:assert/strict';
import {Worker as Thread} from 'node:worker_threads';
import {prepareInWorker,sendPrepared} from '../docs/local-backup/transfer-client.mjs';
const workers=[];
class WorkerAdapter{
 constructor(){this.thread=new Thread(new URL('./transfer_node_worker.mjs',import.meta.url),{resourceLimits:{maxOldGenerationSizeMb:128}});this.exit=new Promise(r=>this.thread.once('exit',r));workers.push(this);this.thread.on('message',data=>this.onmessage?.({data}));this.thread.on('error',e=>this.onerror?.(e));}
 postMessage(value){this.thread.postMessage(value);}
 terminate(){return this.thread.terminate();}
}
const source=padding=>new Blob([JSON.stringify({title:'synthetic',current_node:'a',metadata:'x'.repeat(padding),mapping:{a:{parent:null,message:{id:'a',author:{role:'user'},content:{parts:['TEXT']}}}}})]);
test('preparation runs in an isolated bounded worker without the index worker',async()=>{
 const old=globalThis.Worker;globalThis.Worker=WorkerAdapter;
 try{const promise=prepareInWorker(source(3_000_000));assert.throws(()=>prepareInWorker(source(10)),e=>e.code==='BUSY');const p=await promise;assert.equal(p.mode,'chunks');assert(!JSON.stringify(p.chunks).includes('xxxxx'));await workers.at(-1).exit;}
 finally{globalThis.Worker=old;}
});
test('cancel preparation terminates the worker and releases its private heap',async()=>{
 const old=globalThis.Worker;globalThis.Worker=WorkerAdapter;
 try{const controller=new AbortController(),promise=prepareInWorker(source(12_000_000),{signal:controller.signal});controller.abort();await assert.rejects(()=>promise,e=>e.name==='AbortError');await workers.at(-1).exit;}
 finally{globalThis.Worker=old;}
});
test('in-flight request cancellation aborts transport and clears verified results',async()=>{
 const controller=new AbortController();let cancelled=false,sent=false;
 const p=sendPrepared({mode:'chunks',chunks:[{part_index:1}]},{collector:{accept:async()=>{},cancel(){cancelled=true;}},signal:controller.signal,wait:async()=>{},send:async(_,{signal})=>{sent=true;setTimeout(()=>controller.abort(),5);return new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('cancel','AbortError'))));}});
 await assert.rejects(()=>p,e=>e.name==='AbortError');assert(sent);assert(cancelled);
});
test('failed designated part may be retried without resending accepted parts',async()=>{
 const prepared={mode:'chunks',chunks:[{part_index:1},{part_index:2}]},accepted=new Set(),calls=[];
 const collector={accept:async i=>accepted.add(i)},wait=async()=>{};
 await assert.rejects(()=>sendPrepared(prepared,{collector,wait,send:async p=>{calls.push(p.part_index);return p.part_index===1?{status:200,value:{}}:{status:503,value:{error:{code:'RESOURCE_LIMIT'}}};}}),e=>e.code==='RESOURCE_LIMIT');
 assert.deepEqual([...accepted],[1]);
 await sendPrepared(prepared,{indices:[2],collector,wait,send:async p=>{calls.push(p.part_index);return{status:200,value:{}};}});
 assert.deepEqual(calls,[1,2,2]);assert.deepEqual([...accepted],[1,2]);
});

test('request deadline reports BATCH_TIMEOUT rather than user cancellation',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let sent=false,aborted=false;
 try{
  const promise=sendPrepared({mode:'chunks',chunks:[{part_index:1}]},{collector:{accept:async()=>{}},wait:async()=>{},send:async(_,{signal})=>{sent=true;signal.addEventListener('abort',()=>{aborted=true;});return new Promise(()=>{});}});
  await Promise.resolve();await Promise.resolve();assert(sent);t.mock.timers.tick(55000);
  await assert.rejects(()=>promise,e=>e.code==='BATCH_TIMEOUT');assert(aborted);
 }finally{t.mock.timers.reset();}
});
test('preparation worker runtime failure releases admission and a new worker can restart',async()=>{
 const old=globalThis.Worker;
 class CrashingWorker extends WorkerAdapter{
  constructor(){super();this.thread.terminate();queueMicrotask(()=>this.onerror?.(Error('synthetic worker crash')));}
 }
 try{
  globalThis.Worker=CrashingWorker;await assert.rejects(()=>prepareInWorker(source(10)),/PREPARATION_FAILED/);await workers.at(-1).exit;
  globalThis.Worker=WorkerAdapter;const prepared=await prepareInWorker(source(10));assert.equal(prepared.mode,'official');await workers.at(-1).exit;
 }finally{globalThis.Worker=old;}
});
