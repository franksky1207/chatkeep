const $=id=>document.getElementById(id);
let index=[],selected=new Set(),worker=null,busy=false,directory=null,generation=0,request=0;
const pending=new Map(),urls=new Set(); let failures=[],completed=0; let cleaning=false;
function status(s,fail=false){$('progress').textContent=s;$('progress').className=fail?'error':'';}
function safe(s){return String(s||'未命名對話').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,70).trim()||'未命名對話';}
function date(value){const d=new Date(value*1000);return value!=null&&!Number.isNaN(d.valueOf())?d.toLocaleDateString('zh-TW'):'日期未提供';}
function matches(){const q=$('search').value.trim().toLocaleLowerCase();return index.filter(x=>x.title.toLocaleLowerCase().includes(q));}
function controls(){
  for(const id of ['scan','reset','files','search','select-visible','deselect'])$(id).disabled=busy;
  $('cancel').hidden=!busy; $('cancel').disabled=cleaning; $('download').disabled=busy||!selected.size;
  $('count').textContent='已選 '+selected.size+' 段';
}
function display(){
  const rows=matches();$('shown').textContent='找到 '+rows.length+' 段符合搜尋的對話（清單最多顯示前 300 筆；勾選搜尋結果會包含全部符合項目）';
  const frag=document.createDocumentFragment();
  for(const item of rows.slice(0,300)){
    const row=document.createElement('div');row.className='entry';
    const c=document.createElement('input');c.type='checkbox';c.checked=selected.has(item.key);c.disabled=busy;c.id='entry-'+item.key;
    c.addEventListener('change',()=>{if(busy)return;c.checked?selected.add(item.key):selected.delete(item.key);controls();});
    const label=document.createElement('label');label.htmlFor=c.id;label.textContent=item.title;
    const sub=document.createElement('div');sub.className='sub';sub.textContent=date(item.update_time)+' · '+item.label+' · '+item.nodes+' 個原始 mapping 節點欄位（非可見訊息數）';
    label.append(sub);row.append(c,label);frag.append(row);
  }
  $('results').replaceChildren(frag);controls();
}
async function release(){
  cleaning=true;generation++;const oldWorker=worker;worker=null;
  if(oldWorker){
    await new Promise(resolve=>{
      const done=()=>{clearTimeout(timer);oldWorker.removeEventListener('message',listener);resolve();};
      const listener=event=>{if(event.data.type==='cancelled')done();};
      const timer=setTimeout(done,2000);oldWorker.addEventListener('message',listener);oldWorker.postMessage({type:'cancel'});
    });
    oldWorker.terminate();
  }
  for(const {reject} of pending.values())reject(Error('操作已取消'));pending.clear();
  for(const url of urls)URL.revokeObjectURL(url);urls.clear();
  index=[];selected.clear();$('picker').hidden=true;$('export').hidden=true;
  $('export-status').textContent='';$('results').replaceChildren();
  const old=directory;directory=null;
  if(old && navigator.storage?.getDirectory){
    try{const root=await navigator.storage.getDirectory();
      for(let attempt=0;;attempt++){
        try{await root.removeEntry(old,{recursive:true});break;}
        catch(e){if(!['NoModificationAllowedError','InvalidStateError'].includes(e.name)||attempt>=20)throw e;await new Promise(r=>setTimeout(r,100));}
      }
    }
    catch(e){if(e.name!=='NotFoundError'){directory=old;cleaning=false;throw Error('本機暫存清理失敗，請關閉分頁並清除此網站儲存空間後重試');}}
  }
  cleaning=false;controls();
}
async function clear(message,clearFiles=false){
  // Keep all controls locked until the old worker's disk resources are removed.
  if(cleaning)return;busy=true;const cleanup=release();controls();
  try{await cleanup;if(clearFiles)$('files').value='';status(message);}
  catch(e){status(e.message,true);}
  finally{busy=false;controls();}
}
function extract(item){
  return new Promise((resolve,reject)=>{const id=++request;pending.set(id,{resolve,reject});worker.postMessage({type:'extract',request:id,source:item.source,start:item.start,end:item.end});});
}
$('scan').addEventListener('click',async()=>{
  if(busy)return;const files=[...$('files').files];if(!files.length){status('請先選擇 JSON 或官方 ZIP 備份。',true);return;}
  busy=true;controls();status('正在準備本機掃描…');
  try{await release();}catch(e){busy=false;controls();status(e.message,true);return;}
  busy=true;controls();failures=[];completed=0;const current=generation;
  // Plain JSON must remain usable even when origin storage is unavailable.
  cleaning=true;controls();
  if(files.some(file=>/\.zip$/i.test(file.name)) && navigator.storage?.getDirectory){
    try{const name='chatkeep-backup-'+crypto.randomUUID();const root=await navigator.storage.getDirectory();await root.getDirectoryHandle(name,{create:true});directory=name;}
    catch{directory=null;}
  }
  cleaning=false;controls();
  try{worker=new Worker(new URL('./worker.mjs',import.meta.url),{type:'module'});}
  catch(e){await clear('無法啟動本機解析 Worker，請使用新版瀏覽器並透過網站開啟。');return;}
  worker.onmessage=({data})=>{
    if(current!==generation)return;
    if(data.type==='rows'){for(const row of data.rows){row.label=data.label;index.push(row);}return;}
    if(data.type==='progress'){status(data.phase+'：'+data.source+'\n'+(data.bytes/1048576).toFixed(1)+' / '+(data.total/1048576).toFixed(1)+' MiB（'+(data.total?Math.floor(data.bytes/data.total*100):0)+'%） · 已辨識 '+data.count+' 段（檔案驗證完成後才加入清單）');return;}
    if(data.type==='sourceDone'){completed++;return;}
    if(data.type==='failure'){failures.push(data.source+'：'+data.message);return;}
    if(data.type==='done'){
      busy=false;status('索引完成：'+completed+' 個對話 JSON，'+index.length+' 段對話。'+(failures.length?'\n部分來源失敗（未加入失敗來源的索引）：\n'+failures.join('\n'):''),!!failures.length);
      $('picker').hidden=!index.length;$('export').hidden=!index.length;display();return;
    }
    if(data.type==='extracted'||data.type==='extractError'){
      const p=pending.get(data.request);if(!p)return;pending.delete(data.request);data.type==='extracted'?p.resolve(data.blob):p.reject(Error(data.message));return;
    }
    if(data.type==='fatal')void clear('解析停止：'+data.message+'。請減少檔案或改用記憶體較多的電腦重試。');
  };
  worker.onerror=()=>void clear('解析 Worker 停止，可能是瀏覽器記憶體或功能限制。請分批選檔或改用電腦重試。');
  worker.postMessage({type:'scan',files,directory});
});
$('cancel').addEventListener('click',()=>void clear('已取消並清除本次索引與暫存，可重新選檔掃描。'));
$('reset').addEventListener('click',()=>{if(!busy)void clear('已清除清單與本機暫存。',true);});
$('search').addEventListener('input',display);
$('select-visible').addEventListener('click',()=>{if(busy)return;for(const x of matches())selected.add(x.key);display();});
$('deselect').addEventListener('click',()=>{if(busy)return;selected.clear();display();});
$('download').addEventListener('click',async()=>{
  if(busy||!selected.size)return;busy=true;display();const current=generation;let n=0;
  try{
    for(const item of index.filter(x=>selected.has(x.key))){
      $('export-status').textContent='正在擷取第 '+(n+1)+' 段：'+item.title;
      const blob=await extract(item);if(current!==generation)return;
      const url=URL.createObjectURL(blob);urls.add(url);const a=document.createElement('a');a.href=url;a.download=safe(item.title)+'_'+(++n)+'.json';
      document.body.append(a);a.click();a.remove();setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},60000);
      await new Promise(r=>setTimeout(r,50));
    }
    $('export-status').textContent='已啟動 '+n+' 個原始對話 JSON 下載。如瀏覽器攔截多檔下載，請允許或減少勾選數量。';
  }catch(e){if(current===generation)$('export-status').textContent='下載失敗：'+e.message;}
  finally{if(current===generation){busy=false;display();}}
});
// A session directory is cleaned on explicit cancel/reset. Browsers may retain it after a crash;
// the UI documents site-storage cleanup instead of deleting another tab's files heuristically.
window.addEventListener('pagehide',()=>{worker?.terminate();for(const url of urls)URL.revokeObjectURL(url);if(directory&&navigator.storage?.getDirectory)void navigator.storage.getDirectory().then(root=>root.removeEntry(directory,{recursive:true})).catch(()=>{});});
controls();
