import {ConversionQueue,explain,shareURL,safeFilename} from './conversion.mjs';
const $=id=>document.getElementById(id);
export function mountConversion({getSelected,extract,setLocked}){
 let queue=null,active=false,epoch=0;const urls=new Set();
 const notify=text=>{$('conversion-status').textContent=text;};
 function revoke(){for(const url of urls)URL.revokeObjectURL(url);urls.clear();}
 function draw(){
  const frag=document.createDocumentFragment();
  for(const job of queue?.jobs||[]){
   const card=document.createElement('div');card.className='report';
   const text=document.createElement('div');const r=job.report;
   text.textContent=job.title+'\n'+job.stage+(job.state==='failed'?'\n'+explain(job.error):'');
   if(r)text.textContent+='\n來源：'+r.source+'｜輸出訊息：'+r.output_message_count+'｜DOCX 卷數：'+r.docx_volume_count+
    '｜類型：'+(job.artifact?.artifact_type||job.type||'')+'\n狀態：'+(r.status==='converted_with_warnings'?'有警告':'已完成')+
    '\n缺漏：'+(r.missing?'有':'未發現輸出序列缺漏')+'｜不支援／略過內容：'+JSON.stringify(r.skipped_categories||r.client_source_counts?.skipped_categories||{})+
    '\n警告：'+JSON.stringify(r.warnings||[])+
    '\n完整性驗證層級：'+r.integrity_basis+'（文件 SHA-256／CRC／訊息書籤已驗證；未與 ChatGPT 官方原始網頁逐字比對）';
   card.append(text);
   const button=(label,fn)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',fn);card.append(' ',b);return b;};
   if(job.artifact){
    button('下載 '+job.artifact.artifact_type.toUpperCase(),()=>{
     const artifact=job.artifact;if(!artifact)return;const url=URL.createObjectURL(artifact.blob);urls.add(url);
     const a=document.createElement('a');a.href=url;a.download=safeFilename(artifact.filename,artifact.artifact_type);document.body.append(a);a.click();a.remove();
     notify('已啟動下載；請確認瀏覽器已保存，再釋放成果。');setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
    });
    button('釋放此成果',()=>{job.type=job.artifact.artifact_type;queue.release(job);revoke();draw();});
   }
   if(job.state==='failed'){
    button(job.collector?'重試缺少批次（含失敗批次 '+job.failedPart+'）':'重試此段',()=>void resume()).disabled=!!queue.running;
    button('略過此段並繼續',()=>{queue.skip(job);void resume();}).disabled=!!queue.running;
   }
   frag.append(card);
  }
  $('conversion-results').replaceChildren(frag);
  $('cancel-conversion').disabled=!active;
  $('continue-conversion').disabled=!active||!!queue?.running;
  $('clear-conversion').disabled=!!queue?.running;
 }
 function update(){
  const complete=queue?.jobs.every(j=>['done','released','skipped','cancelled'].includes(j.state));
  if(complete&&!queue.running){active=false;setLocked(false);}
  draw();
 }
 async function resume(){
  if(!queue||queue.running)return;
  const current=epoch;
  try{await queue.resume();}catch(e){if(current===epoch)notify(explain(e.code||e.message));}finally{if(current===epoch)update();}
 }
 async function start(items){
  if(active)return;
  const current=++epoch;
  try{
   queue?.dispose();revoke();queue=new ConversionQueue({base:$('api-base').value,extract,onUpdate:()=>{if(current===epoch)update();}});
   active=true;setLocked(true);notify('對話依序轉換中；完成後先查看各段完整性報告。');draw();await queue.run(items);
  }catch(e){if(current===epoch){active=false;setLocked(false);notify(explain(e.code||e.message));}}finally{if(current===epoch)update();}
 }
 $('convert-share').addEventListener('click',()=>{try{const url=shareURL($('share-url').value);void start([{url,title:'公開分享對話'}]);}catch(e){notify(explain(e.code||e.message));}});
 $('convert-selected').addEventListener('click',()=>{const items=getSelected();if(items.length)void start(items);else notify('請先勾選對話。');});
 $('continue-conversion').addEventListener('click',()=>void resume());
 $('cancel-conversion').addEventListener('click',()=>{queue?.cancel();revoke();notify('已取消；已完成段落仍可下載。Render 子程序可能持續至後端期限。');if(!queue?.running){active=false;setLocked(false);}draw();});
 const clear=()=>{epoch++;queue?.dispose();queue=null;active=false;revoke();setLocked(false);draw();};
 $('clear-conversion').addEventListener('click',clear);
 window.addEventListener('pagehide',()=>{queue?.dispose();revoke();});
 draw();return {clear};
}
