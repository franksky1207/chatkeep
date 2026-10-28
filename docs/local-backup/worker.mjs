import {indexBlob, indexCost, INDEX_BUDGET} from './json-index.mjs';
import {zipEntries, expandEntry} from './zip.mjs';
const sources=new Map(); let running=false, cancelled=false, directory=null, nextSource=0, totalIndexed=0, indexBytes=0;
let lastProgress=0;
function checkCancelled(){if(cancelled)throw new DOMException('使用者取消','AbortError');}
async function removeTemp(name){
  try{await directory.removeEntry(name);}
  catch(e){if(e.name!=='NotFoundError'){const error=Error('本機暫存清理失敗，將停止並清除本次操作；請確認儲存空間');error.name='CleanupError';throw error;}}
}
function progress(source, phase, bytes, total, count=0) {
  checkCancelled();const now=performance.now(); if(now-lastProgress<100 && bytes!==total) return; lastProgress=now;
  postMessage({type:'progress',source,phase,bytes,total,count:totalIndexed+count});
}
async function scanSource(blob, label, temp=null) {
  const source=String(nextSource++);
  try {
    checkCancelled();const rows=await indexBlob(blob,(bytes,count)=>progress(label,'建立索引',bytes,blob.size,count));
    checkCancelled();if(totalIndexed+rows.length>200000) throw Error('本次索引超過 200,000 段，請分批選檔');
    const cost=rows.reduce((sum,row)=>sum+indexCost(row),0);
    if(indexBytes+cost>INDEX_BUDGET) throw Error('索引資料超過 64 MiB 預算，請分批選檔');
    indexBytes+=cost;sources.set(source,blob); totalIndexed+=rows.length;
    // Do not publish a partially parsed source: trailing corruption invalidates all its ranges.
    for(let i=0;i<rows.length;i+=500) postMessage({type:'rows',label,rows:rows.slice(i,i+500).map(row=>({...row,source,key:source+':'+row.start}))});
    postMessage({type:'sourceDone',source:label,count:rows.length});
  } catch(e) {
    if(temp && directory) await removeTemp(temp);
    if(e.name==='AbortError')throw e;
    postMessage({type:'failure',source:label,message:e.message});
  }
}
self.onmessage=async({data})=>{
  if(data.type==='cancel'){cancelled=true;if(!running)postMessage({type:'cancelled'});return;}
  if(data.type==='extract') {
    const blob=sources.get(data.source);
    if(!blob || !Number.isSafeInteger(data.start) || !Number.isSafeInteger(data.end) || data.start<0 || data.end>blob.size || data.end<=data.start) {
      postMessage({type:'extractError',request:data.request,message:'對話來源已清除或索引範圍無效，請重新掃描'}); return;
    }
    postMessage({type:'extracted',request:data.request,blob:blob.slice(data.start,data.end,'application/json;charset=utf-8')}); return;
  }
  if(data.type!=='scan' || running) return;
  running=true;cancelled=false;
  try {
    for(const file of data.files) {
      checkCancelled();
      if(!/\.zip$/i.test(file.name)) { await scanSource(file,file.name); continue; }
      try {
        const entries=await zipEntries(file,checkCancelled);checkCancelled();
        if(!data.directory || !navigator.storage?.getDirectory) throw Error('此瀏覽器無法提供 ZIP 本機暫存空間，請先在電腦解壓後選取 JSON');
        if(!directory) { const root=await navigator.storage.getDirectory(); directory=await root.getDirectoryHandle(data.directory); }
        const estimate=await navigator.storage.estimate();
        const needed=entries.reduce((n,e)=>n+e.size,0);
        if(estimate.quota && needed>estimate.quota-(estimate.usage||0)) throw Error('本機暫存空間不足，請釋放空間或先解壓並選取 JSON');
        for(const entry of entries) {
          checkCancelled();
          const temp='entry-'+nextSource+'-'+crypto.randomUUID();
          const label=file.name+' / '+entry.name;
          try {
            const handle=await directory.getFileHandle(temp,{create:true});
            const blob=await expandEntry(file,entry,handle,bytes=>progress(label,'本機解壓與 CRC 驗證',bytes,entry.size));
            await scanSource(blob,label,temp);
          } catch(e) {
            if(e.name==='CleanupError')throw e;
            await removeTemp(temp);
            if(e.name==='AbortError')throw e;
            postMessage({type:'failure',source:label,message:e.name==='QuotaExceededError'?'本機暫存空間不足，請先解壓並分批選取 JSON':e.message});
          }
        }
      } catch(e) { if(['AbortError','CleanupError'].includes(e.name))throw e;postMessage({type:'failure',source:file.name,message:e.message}); }
    }
    postMessage({type:'done',count:totalIndexed});
  } catch(e) { postMessage(e.name==='AbortError'?{type:'cancelled'}:{type:'fatal',message:e.message}); }
  finally { running=false; }
};
