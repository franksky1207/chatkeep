import {zipFiles,safeHtmlName} from './reader-export.mjs';
const $=id=>document.getElementById(id);
let instance=null,sequence=0,active=null,page=0,searchTimer=null,copyPlan=null,copyIndex=0,exporting=false;
const pending=new Map();
function ask(type,args={}){
  return new Promise((resolve,reject)=>{
    if(!instance){reject(Error('閱讀器尚未啟動'));return;}
    const request=++sequence;pending.set(request,{resolve,reject});instance.postMessage({type,request,...args});
  });
}
function status(text){$('reader-status').textContent=text;}
function richInline(target,text){
  // Only known Markdown emphasis/code; all other source text remains literal.
  const pattern=/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let cursor=0;
  for(const match of text.matchAll(pattern)){
    const position=match.index;
    if(position>cursor)target.append(document.createTextNode(text.slice(cursor,position)));
    const value=match[0],node=document.createElement(value.startsWith('**')?'strong':value.startsWith('*')?'em':'code');
    node.textContent=value.slice(value.startsWith('**')?2:1,value.startsWith('**')?-2:-1);
    target.append(node);cursor=position+value.length;
  }
  if(cursor<text.length)target.append(document.createTextNode(text.slice(cursor)));
}
function makeBody(text){
  const body=document.createElement('div');body.className='reader-body';
  const lines=text.split(/\n/);let code=null,list=null;
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(!line.trim())continue;
    if(/^\s*```/.test(line)){
      list=null;
      if(code){body.append(code);code=null;}else code=document.createElement('pre');
      continue;
    }
    if(code){code.textContent+=line+'\n';continue;}
    const heading=/^(#{1,6})\s+(.+)$/.exec(line);
    if(heading){list=null;const h=document.createElement('h'+Math.min(heading[1].length+1,6));richInline(h,heading[2]);body.append(h);continue;}
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
      list=null;
      const table=document.createElement('table');
      const cells=s=>s.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
      const header=cells(line),thead=document.createElement('thead'),hr=document.createElement('tr');
      for(const cell of header){const th=document.createElement('th');richInline(th,cell);hr.append(th);}thead.append(hr);table.append(thead);
      i++;
      const tbody=document.createElement('tbody');
      while(i+1<lines.length&&lines[i+1].includes('|')){
        i++;const tr=document.createElement('tr');
        for(const cell of cells(lines[i])){const td=document.createElement('td');richInline(td,cell);tr.append(td);}tbody.append(tr);
      }
      table.append(tbody);body.append(table);continue;
    }
    const bullet=/^\s*([-*+] |\d+[.)] )(.+)$/.exec(line);
    if(bullet){
      const kind=/\d/.test(bullet[1][0])?'ol':'ul';
      if(!list||list.tagName.toLowerCase()!==kind){list=document.createElement(kind);body.append(list);}
      const li=document.createElement('li');richInline(li,bullet[2]);list.append(li);continue;
    }
    list=null;
    const quote=/^>\s?(.*)$/.exec(line);
    const el=document.createElement(quote?'blockquote':'p');richInline(el,quote?quote[1]:line||'\u00a0');body.append(el);
  }
  if(code)body.append(code);
  return body;
}
function render(messages){
  const target=$('reader-messages');target.replaceChildren();
  for(const m of messages){
    const article=document.createElement('article');article.className='reader-message';
    const heading=document.createElement('h3');heading.textContent=m.role==='user'?'使用者':m.role==='assistant'?'ChatGPT':'其他訊息';
    const body=makeBody(m.text);
    article.append(heading,body);target.append(article);
  }
}
async function showPage(next){
  if(!active)return;page=Math.max(0,Math.min(next,Math.ceil(active.count/50)-1));
  const data=await ask('page',{page});render(data.messages);
  const label='第 '+(page+1)+'／'+Math.ceil(active.count/50)+' 頁（訊息 '+(page*50+1)+'～'+Math.min((page+1)*50,active.count)+'／'+active.count+'）';
  $('reader-page').textContent=label;
  $('reader-page-bottom').textContent=label;
  $('reader-jump').max=String(Math.ceil(active.count/50));$('reader-jump').value=String(page+1);
  $('reader-prev').disabled=page===0;$('reader-next').disabled=(page+1)*50>=active.count;
  $('reader-prev-bottom').disabled=page===0;$('reader-next-bottom').disabled=(page+1)*50>=active.count;
}
export function mountReader({extract,isBusy}){
  function close(){
    copyPlan=null;copyIndex=0;$('reader-copy-controls').hidden=true;$('reader-export-status').textContent='';
    if(instance){instance.terminate();instance=null;}
    for(const p of pending.values())p.reject(Error('閱讀器已關閉'));pending.clear();active=null;
    $('reader-panel').hidden=true;$('reader-messages').replaceChildren();$('reader-hits').replaceChildren();
  }
  function downloadable(blob,name){
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  $('reader-copy-plan').addEventListener('click',async()=>{
    if(!active)return;
    try{const plan=await ask('copyPlan');copyPlan=plan.chunks;copyIndex=0;
      $('reader-copy-controls').hidden=false;updateCopy();
    }catch(e){$('reader-export-status').textContent='無法準備複製：'+e.message;}
  });
  function updateCopy(){
    if(!copyPlan)return;
    const chunk=copyPlan[copyIndex];
    $('reader-copy-info').textContent='第 '+(copyIndex+1)+'／'+copyPlan.length+' 批 · 訊息 '+(chunk.start+1)+'～'+(chunk.start+chunk.count)+'／'+active.count;
    $('reader-copy-next').disabled=copyIndex>=copyPlan.length-1;
    $('reader-copy-prev').disabled=copyIndex===0;
  }
  $('reader-copy-next').addEventListener('click',()=>{if(copyPlan&&copyIndex<copyPlan.length-1){copyIndex++;updateCopy();}});
  $('reader-copy-prev').addEventListener('click',()=>{if(copyPlan&&copyIndex>0){copyIndex--;updateCopy();}});
  $('reader-copy-current').addEventListener('click',async()=>{
    if(!copyPlan)return;
    try{
      const data=await ask('copyChunk',{index:copyIndex});
      if(!navigator.clipboard?.write||!window.ClipboardItem)throw Error('瀏覽器不支援含格式剪貼簿，請下載 HTML');
      await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([data.payload.html],{type:'text/html'}),'text/plain':new Blob([data.payload.text],{type:'text/plain'})})]);
      $('reader-export-status').textContent='第 '+(copyIndex+1)+' 批已複製到剪貼簿，請貼入 Word 後再選下一批。網站無法確認 Word 貼上結果。';
    }catch(e){$('reader-export-status').textContent='複製失敗：'+e.message;}
  });
  $('reader-html-download').addEventListener('click',async()=>{
    if(!active||exporting)return;exporting=true;$('reader-html-download').disabled=true;
    try{
      const plan=await ask('htmlPlan');
      if(!plan.volumes.length)throw Error('沒有可匯出的正文');
      if(plan.volumes.length>300)throw Error('分卷數量過多，請改用較小的來源');
      const files=[];
      for(let i=0;i<plan.volumes.length;i++){
        $('reader-export-status').textContent='正在產生 HTML 第 '+(i+1)+'／'+plan.volumes.length+' 卷';
        const v=await ask('htmlVolume',{index:i});
        if(v.count!==plan.volumes[i].count||v.start!==plan.volumes[i].start)throw Error('分卷範圍驗證失敗');
        files.push({name:safeHtmlName(active.title)+(plan.volumes.length>1?'_part'+String(i+1).padStart(3,'0'):'')+'.html',content:v.html});
      }
      if(files.length===1)downloadable(new Blob([files[0].content],{type:'text/html;charset=utf-8'}),files[0].name);
      else downloadable(zipFiles(files),safeHtmlName(active.title)+'_HTML.zip');
      $('reader-export-status').textContent='已啟動 '+files.length+' 卷 HTML 下載；請確認瀏覽器已保存。';
    }catch(e){$('reader-export-status').textContent='HTML 下載失敗：'+e.message;}
    finally{exporting=false;$('reader-html-download').disabled=false;}
  });
  $('reader-close').addEventListener('click',close);
  $('reader-prev').addEventListener('click',()=>void showPage(page-1));
  $('reader-next').addEventListener('click',()=>void showPage(page+1));
  $('reader-prev-bottom').addEventListener('click',()=>void showPage(page-1));
  $('reader-next-bottom').addEventListener('click',()=>void showPage(page+1));
  $('reader-last').addEventListener('click',()=>void showPage(Math.ceil(active.count/50)-1));
  $('reader-first').addEventListener('click',()=>void showPage(0));
  $('reader-first-top').addEventListener('click',()=>void showPage(0));
  $('reader-last-top').addEventListener('click',()=>void showPage(Math.ceil(active.count/50)-1));
  const jump=()=>{const value=Number($('reader-jump').value);if(Number.isSafeInteger(value)&&value>=1&&value<=Math.ceil(active.count/50))void showPage(value-1);else status('頁碼超出範圍，請輸入有效頁數。');};
  $('reader-go').addEventListener('click',jump);
  $('reader-jump').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();jump();}});
  $('reader-search').addEventListener('input',()=>{
    clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{
      if(!active)return;
      try{
        const data=await ask('search',{query:$('reader-search').value});
        const target=$('reader-hits');target.replaceChildren();
        const count=document.createElement('span');count.textContent='符合的訊息 '+data.hits.length+' 則';target.append(count);
        for(const hit of data.hits.slice(0,100)){
          const button=document.createElement('button');button.type='button';button.className='secondary';
          button.textContent='第 '+(hit.index+1)+' 則：'+hit.excerpt.slice(0,70);
          button.addEventListener('click',()=>void showPage(Math.floor(hit.index/50)));target.append(button);
        }
        if(data.hits.length>100)target.append(document.createTextNode('僅顯示前 100 筆跳轉結果，搜尋統計仍涵蓋全部訊息。'));
      }catch(e){status(e.message);}
    },250);
  });
  return {
    close,
    async openShared(source){return this.open({title:source.title||'公開分享對話',shared:source});},
    async open(item){
      if(isBusy())return;
      close();$('reader-panel').hidden=false;$('reader-title').textContent=item.title;status('正在本機解析對話……');
      instance=new Worker(new URL('./reader-worker.mjs',import.meta.url),{type:'module'});
      instance.onmessage=({data})=>{
        const p=pending.get(data.request);if(!p)return;pending.delete(data.request);
        data.type==='readerError'?p.reject(Error(data.message)):p.resolve(data);
      };
      instance.onerror=()=>status('閱讀器背景工作停止，請減少資料量或改用電腦');
      try{
        const result=item.shared?await ask('openShared',{source:item.shared}):await ask('open',{blob:await extract(item)});active=result;

        const mark=result.summary.nonText?' · 有 '+result.summary.nonText+' 處特殊內容待人工核對':'';
        status('主線正文 '+result.count+' 則 · 約 '+result.words.toLocaleString('zh-TW')+' 字（參考 Word 計數，非官方 Word 精確值）'+mark);
        $('reader-scope').textContent=(item.shared?'資料來自公開分享連結，內容由 Render 擷取；來源格式可能無法驗證所有分支。':'')+'請注意：畫面每次僅顯示 50 則訊息，捲到底部不等於對話結尾。請使用「最後一頁」確認結尾。原始節點 '+result.summary.rawNodes+'；非主線 '+result.summary.offBranch+'；排除隱藏／系統／工具類 '+result.summary.hidden+'。HTML 僅顯示目前主線的可還原內容。';
        $('reader-search').value='';$('reader-hits').replaceChildren();
        await showPage(0);$('reader-panel').scrollIntoView({block:'start',behavior:'smooth'});
      }catch(e){status('無法開啟閱讀版：'+e.message);}
    }
  };
}
