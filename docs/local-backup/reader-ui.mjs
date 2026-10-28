import {wordLikeCount} from './reader-core.mjs';
const $=id=>document.getElementById(id);
let instance=null,sequence=0,active=null,page=0,searchTimer=null;
const pending=new Map();
function ask(type,args={}){
  return new Promise((resolve,reject)=>{
    if(!instance){reject(Error('閱讀器尚未啟動'));return;}
    const request=++sequence;pending.set(request,{resolve,reject});instance.postMessage({type,request,...args});
  });
}
function status(text){$('reader-status').textContent=text;}
function render(messages){
  const target=$('reader-messages');target.replaceChildren();
  for(const m of messages){
    const article=document.createElement('article');article.className='reader-message';
    const heading=document.createElement('h3');heading.textContent=m.role==='user'?'使用者':m.role==='assistant'?'ChatGPT':'其他訊息';
    const body=document.createElement('div');body.className='reader-body';
    // Safe structural subset: never inject untrusted HTML.
    const lines=m.text.split(/\n/);let code=null;
    for(const line of lines){
      if(/^\s*```/.test(line)){if(code){body.append(code);code=null;}else code=document.createElement('pre');continue;}
      if(code){code.textContent+=line+'\n';continue;}
      const match=/^(#{1,6})\s+(.+)$/.exec(line);
      if(match){const h=document.createElement('h'+Math.min(match[1].length+1,6));h.textContent=match[2];body.append(h);continue;}
      const p=document.createElement('p');p.textContent=line||'\u00a0';body.append(p);
    }
    if(code)body.append(code);
    const copy=document.createElement('button');copy.className='secondary';copy.textContent='複製此則文字';copy.type='button';
    copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(m.text);status('已複製單則文字（尚非含格式全文複製）');}catch(e){status('複製失敗：'+e.message);}});
    article.append(heading,body,copy);target.append(article);
  }
}
async function showPage(next){
  if(!active)return;page=Math.max(0,Math.min(next,Math.ceil(active.count/50)-1));
  const data=await ask('page',{page});render(data.messages);
  $('reader-page').textContent='第 '+(page+1)+'／'+Math.ceil(active.count/50)+' 頁（每頁 50 則）';
  $('reader-prev').disabled=page===0;$('reader-next').disabled=(page+1)*50>=active.count;
}
export function mountReader({extract,isBusy}){
  function close(){
    if(instance){instance.terminate();instance=null;}
    for(const p of pending.values())p.reject(Error('閱讀器已關閉'));pending.clear();active=null;
    $('reader-panel').hidden=true;$('reader-messages').replaceChildren();$('reader-hits').replaceChildren();
  }
  $('reader-close').addEventListener('click',close);
  $('reader-prev').addEventListener('click',()=>void showPage(page-1));
  $('reader-next').addEventListener('click',()=>void showPage(page+1));
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
        const blob=await extract(item);
        const result=await ask('open',{blob});active=result;
        const mark=result.summary.nonText?' · 有 '+result.summary.nonText+' 處特殊內容待人工核對':'';
        status('主線正文 '+result.count+' 則 · 約 '+result.words.toLocaleString('zh-TW')+' 字（參考 Word 計數，非官方 Word 精確值）'+mark);
        $('reader-scope').textContent='原始節點 '+result.summary.rawNodes+'；非主線 '+result.summary.offBranch+'；排除隱藏／系統／工具類 '+result.summary.hidden+'。HTML 僅顯示目前主線的可還原內容。';
        $('reader-search').value='';$('reader-hits').replaceChildren();
        await showPage(0);$('reader-panel').scrollIntoView({block:'start',behavior:'smooth'});
      }catch(e){status('無法開啟閱讀版：'+e.message);}
    }
  };
}
