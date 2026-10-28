import {safeFilename} from './conversion.mjs';
import {mountModes} from './site-ui.mjs';
import {mountConversion} from './conversion-ui.mjs';
import {filterRows,report,seriesNumber,isoDate} from './filters.mjs';
const $=id=>document.getElementById(id);
mountModes();
const PAGE_SIZE=50,SELECTED_PAGE_SIZE=25;let resultPage=0,selectedPage=0,lastRows=[];
let index=[],selected=new Set(),worker=null,busy=false,directory=null,generation=0,request=0;
const pending=new Map(),urls=new Set(); let failures=[],completed=0; let cleaning=false,conversionLocked=false;
function status(s,fail=false){$('progress').textContent=s;$('progress').className=fail?'error':'';}
function date(value){const d=new Date(value*1000);return value!=null&&!Number.isNaN(d.valueOf())?d.toLocaleDateString('zh-TW'):'日期未提供';}
function options(){return {query:$('search').value,series:$('series').value,first:$('first').value,last:$('last').value,dateField:$('date-field').value,from:$('from').value,to:$('to').value};}
function matches(){return filterRows(index,options());}
function summary(rows){
  const o=options(),r=report(rows,o),all=report(index,{});
  const problems=[];
  if(o.from&&o.to&&o.from>o.to)problems.push('日期起點晚於終點');
  if(o.series&&o.first&&o.last&&Number(o.first)>Number(o.last))problems.push('編號起點大於終點');
  if(r.missing.length)problems.push('範圍內未找到編號：'+r.missing.join('、'));
  if(r.duplicates.length)problems.push('重複編號：'+r.duplicates.map(x=>x.number+'（'+x.count+' 段）').join('、'));
  if(failures.length)problems.push('有 '+failures.length+' 個來源解析失敗，報告不代表整份備份完整');
  $('index-counts').textContent='總索引 '+all.conversations+' 段 · 符合 '+r.conversations+' 段 · 已勾選 '+selected.size+' 段';
  $('select-visible').textContent='勾選目前搜尋結果（共 '+rows.length+' 段，包含所有分頁）';
  $('select-visible').disabled=busy||!rows.length;
  $('report').textContent=(problems.length?'提醒：'+problems.join('；')+'\n':'')+
    '缺號／重號僅根據成功解析且符合目前篩選的來源，不代表整份備份完整。'+
    '\n原始 mapping 節點欄位合計：'+r.nodes+'；節點數不等於可見訊息數。可匯出訊息數尚未驗證，轉換後請查看完整性報告。';

}
function preview(item){
  const number=$('series').value?seriesNumber(item.title,$('series').value):null;
  $('preview').hidden=false;
  $('preview').textContent='對話預覽（僅索引資料，不讀取或顯示私人訊息本文）\n標題：'+item.title+
    '\n官方 ID：'+(item.originalId??'未提供')+'\n建立日期：'+(isoDate(item.create_time)??'未提供')+
    '\n更新日期：'+(isoDate(item.update_time)??'未提供')+'\n來源：'+item.label+
    '\n原始 mapping 節點欄位：'+item.nodes+
    (number!==null?'\n系列編號：'+number:'')+
    '\n原始位元組範圍：['+item.start+', '+item.end+')'+
    '\n警告：節點欄位不等於可見訊息數；分支、隱藏訊息、內容格式及可匯出訊息數尚未逐一驗證。';
}
function controls(){
  $('local-operation').hidden=!busy||conversionLocked;$('local-operation').textContent=busy&&!conversionLocked?'本機作業進行中，請等候掃描或原始 JSON 擷取完成。可切回官方備份查看進度。':'';
  for(const id of ['scan','reset','files','search','select-visible','deselect','series','first','last','date-field','from','to','convert-share','api-base','share-url','reset-filters','results-prev','results-next','selected-prev','selected-next'])$(id).disabled=busy;
  $('cancel').hidden=!busy||conversionLocked; $('cancel').disabled=cleaning; $('download').disabled=busy||!selected.size;
  $('convert-selected').disabled=busy||!selected.size;
  $('results-prev').disabled=busy||resultPage===0;$('results-next').disabled=busy||(resultPage+1)*PAGE_SIZE>=lastRows.length;
  $('count').textContent='已選 '+selected.size+' 段';
  renderSelected();
}
function renderSelected(){
  const rows=index.filter(item=>selected.has(item.key));
  selectedPage=Math.min(selectedPage,Math.max(0,Math.ceil(rows.length/SELECTED_PAGE_SIZE)-1));
  const visible=lastRows.reduce((n,item)=>n+Number(selected.has(item.key)),0);
  $('selection-scope').textContent=rows.length?'目前篩選中已勾選 '+visible+' 段；另有 '+(rows.length-visible)+' 段位於其他搜尋條件。轉換會包含全部已選對話。':'尚未勾選對話，請從搜尋結果選取。';
  const frag=document.createDocumentFragment();
  for(const item of rows.slice(selectedPage*SELECTED_PAGE_SIZE,(selectedPage+1)*SELECTED_PAGE_SIZE)){
    const row=document.createElement('div');row.className='selected-entry';row.setAttribute('role','listitem');
    const name=document.createElement('p');name.textContent=item.title;
    const remove=document.createElement('button');remove.type='button';remove.className='quiet';remove.textContent='移除選取';remove.setAttribute('aria-label','移除選取：'+item.title);remove.disabled=busy;
    remove.addEventListener('click',()=>{if(busy)return;selected.delete(item.key);display();$('selected-title').focus();});row.append(name,remove);
    if(Array.from(item.title).length>40){const details=document.createElement('details'),summary=document.createElement('summary'),full=document.createElement('p');summary.textContent='查看完整名稱';full.textContent=item.title;details.append(summary,full);row.append(details);}
    frag.append(row);
  }
  if(!rows.length){const p=document.createElement('p');p.className='empty';p.textContent='已選清單是空的。';frag.append(p);}
  $('selected-results').replaceChildren(frag);
  $('selected-page').textContent=rows.length?'第 '+(selectedPage+1)+' / '+Math.ceil(rows.length/SELECTED_PAGE_SIZE)+' 頁':'尚無已選對話';
  $('selected-prev').disabled=busy||selectedPage===0;$('selected-next').disabled=busy||(selectedPage+1)*SELECTED_PAGE_SIZE>=rows.length;
}
function display(){
  const rows=matches();lastRows=rows;resultPage=Math.min(resultPage,Math.max(0,Math.ceil(rows.length/PAGE_SIZE)-1));
  $('shown').textContent=rows.length?'搜尋結果共 '+rows.length+' 段，每頁最多 '+PAGE_SIZE+' 段。「勾選目前搜尋結果」包含所有分頁，不會清除其他已選對話。':'沒有符合條件的對話。請換個關鍵字、調整日期或系列範圍，也可以清除篩選。';
  const frag=document.createDocumentFragment();
  for(const item of rows.slice(resultPage*PAGE_SIZE,(resultPage+1)*PAGE_SIZE)){
    const row=document.createElement('div');row.className='entry'+(selected.has(item.key)?' selected':'');row.setAttribute('role','listitem');
    const c=document.createElement('input');c.type='checkbox';c.checked=selected.has(item.key);c.disabled=busy;c.id='entry-'+item.key;
    c.addEventListener('change',()=>{if(busy)return;c.checked?selected.add(item.key):selected.delete(item.key);row.classList.toggle('selected',c.checked);controls();summary(lastRows);});
    const label=document.createElement('label');label.htmlFor=c.id;const title=document.createElement('span');title.className='entry-title';title.textContent=item.title;label.append(title);
    const sub=document.createElement('span');sub.className='sub';sub.textContent=date(item.update_time)+' · '+item.label;
    label.append(sub);const view=document.createElement('button');view.type='button';view.className='secondary';view.textContent='預覽';view.setAttribute('aria-label','預覽：'+item.title);view.disabled=busy;view.addEventListener('click',()=>{preview(item);$('preview').focus();});row.append(c,label,view);frag.append(row);
  }
  if(!rows.length){const p=document.createElement('p');p.className='empty';p.textContent='沒有符合條件的對話。';frag.append(p);}
  $('results').replaceChildren(frag);controls();summary(rows);
  $('results-page').textContent=rows.length?'第 '+(resultPage+1)+' / '+Math.ceil(rows.length/PAGE_SIZE)+' 頁':'沒有搜尋結果';
  $('results-prev').disabled=busy||resultPage===0;$('results-next').disabled=busy||(resultPage+1)*PAGE_SIZE>=rows.length;
}
async function release(){
  busy=true;
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
  index=[];lastRows=[];resultPage=0;selectedPage=0;selected.clear();$('picker').hidden=true;$('export').hidden=true;
  $('export-status').textContent='';$('results').replaceChildren();$('preview').hidden=true;$('report').textContent='';
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
  if(cleaning)return;if(conversionLocked)conversion.cancel();busy=true;const cleanup=release();controls();
  try{await cleanup;if(clearFiles)$('files').value='';status(message);}
  catch(e){status(e.message,true);}
  finally{busy=false;controls();}
}
function extract(item,signal){
  return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(new DOMException('已取消','AbortError'));return;}
    if(!worker){reject(Error('PREPARATION_FAILED'));return;}
    const id=++request;
    const cancel=()=>{pending.delete(id);reject(new DOMException('已取消','AbortError'));};
    const finish=fn=>value=>{signal?.removeEventListener('abort',cancel);fn(value);};
    pending.set(id,{resolve:finish(resolve),reject:finish(reject)});signal?.addEventListener('abort',cancel,{once:true});worker.postMessage({type:'extract',request:id,source:item.source,start:item.start,end:item.end});});
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
for(const id of ['search','series','first','last','date-field','from','to'])$(id).addEventListener('input',()=>{ $('preview').hidden=true;resultPage=0;display(); });
$('select-visible').addEventListener('click',()=>{if(busy)return;for(const x of matches())selected.add(x.key);display();});
$('deselect').addEventListener('click',()=>{if(busy)return;selected.clear();display();});
$('reset-filters').addEventListener('click',()=>{
  if(busy)return;for(const id of ['search','series','first','last','from','to'])$(id).value='';$('date-field').value='update';resultPage=0;display();$('search').focus();
});
$('results-prev').addEventListener('click',()=>{if(!busy){resultPage--;display();$('results').scrollTop=0;}});
$('results-next').addEventListener('click',()=>{if(!busy){resultPage++;display();$('results').scrollTop=0;}});
$('selected-prev').addEventListener('click',()=>{if(!busy){selectedPage--;renderSelected();$('selected-results').scrollTop=0;}});
$('selected-next').addEventListener('click',()=>{if(!busy){selectedPage++;renderSelected();$('selected-results').scrollTop=0;}});
$('download').addEventListener('click',async()=>{
  if(busy||!selected.size)return;busy=true;display();const current=generation;let n=0;
  try{
    for(const item of index.filter(x=>selected.has(x.key))){
      $('export-status').textContent='正在擷取第 '+(n+1)+' 段：'+item.title;
      const blob=await extract(item);if(current!==generation)return;
      const url=URL.createObjectURL(blob);urls.add(url);const a=document.createElement('a');a.href=url;a.download=safeFilename(item.title+'_'+(++n),'json');
      document.body.append(a);a.click();a.remove();setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
      await new Promise(r=>setTimeout(r,50));
    }
    $('export-status').textContent='已啟動 '+n+' 個原始對話 JSON 下載。如瀏覽器攔截多檔下載，請允許或減少勾選數量。';
  }catch(e){if(current===generation)$('export-status').textContent='下載失敗：'+e.message;}
  finally{if(current===generation){busy=false;display();}}
});
// A session directory is cleaned on explicit cancel/reset. Browsers may retain it after a crash;
// the UI documents site-storage cleanup instead of deleting another tab's files heuristically.
window.addEventListener('pagehide',()=>{worker?.terminate();for(const url of urls)URL.revokeObjectURL(url);if(directory&&navigator.storage?.getDirectory)void navigator.storage.getDirectory().then(root=>root.removeEntry(directory,{recursive:true})).catch(()=>{});});
const conversion=mountConversion({
 getSelected:()=>index.filter(x=>selected.has(x.key)),
 extract:(item,signal)=>{if(item.end-item.start>16_000_000){const e=Error('SELECTED_SOURCE_LIMIT');e.code=e.message;throw e;}return extract(item,signal);},
 setLocked:value=>{conversionLocked=value;busy=value||cleaning;display();}
});
controls();
