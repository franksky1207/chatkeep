import {ConversionQueue,explain,shareURL,safeFilename,apiBase} from './conversion.mjs';
import {DEFAULT_API_BASE} from './site-config.mjs';
import {stateLabels,queueView,reportView,stageText,text} from './presentation.mjs';
const $=id=>document.getElementById(id);
function node(tag,value,className){const element=document.createElement(tag);if(value!==undefined)element.textContent=text(value);if(className)element.className=className;return element;}
function reportElement(job){
 const r=reportView(job),section=node('section');section.setAttribute('aria-label','完整性報告');
 const summary=node('dl',undefined,'report-summary');
 for(const [label,value]of r.summary){const field=node('div');field.append(node('dt',label),node('dd',value));summary.append(field);}
 section.append(summary,node('p','完整性摘要：'+(job.report.missing===false?'未發現輸出序列缺漏。':'請查看驗證結果。')));
 if(job.report.status==='converted_with_warnings')section.append(node('p','有警告：請展開詳細資訊，查看內容限制與來源驗證範圍。','note'));
 const details=node('details'),heading=node('summary','進階完整性資訊');details.append(heading);
 const body=node('div',undefined,'details-body');body.append(node('p',r.scope),node('p',r.disclaimer,'note'));
 const list=node('dl');for(const [label,value]of r.detail)list.append(node('dt',label),node('dd',value,'technical'));
 body.append(list,node('h4','各卷訊息範圍與檔案 SHA-256'));
 const volumes=node('ul');for(const volume of r.volumes)volumes.append(node('li','第 '+volume.number+' 卷：訊息 '+volume.first+'–'+volume.last+(volume.part?'，批次 '+volume.part:'')+'；SHA-256：'+text(volume.hash),'technical'));body.append(volumes);
 body.append(node('h4','內容與格式警告'));const warnings=node('ul');for(const warning of r.warnings)warnings.append(node('li',warning));
 if(!r.warnings.length)warnings.append(node('li','未回報內容或格式警告。這不代表所有媒體或隱藏內容都已輸出。'));
 body.append(warnings);details.append(body);section.append(details);return section;
}
export function mountConversion({getSelected,extract,setLocked,queueFactory=options=>new ConversionQueue(options)}){
 let queue=null,active=false,epoch=0,page=0;const urls=new Set(),cards=new Map(),PAGE_SIZE=20;
 const notify=value=>{$('conversion-status').textContent=value;};
 const service=value=>{$('service-status').textContent=value;};
 function configure(){
  const value=$('api-base').value.trim();$('api-base').removeAttribute('aria-invalid');
  if(!value){service('尚未設定轉換服務。仍可在本機搜尋備份、下載原始 JSON。');return;}
  try{apiBase(value);service('已指定轉換服務，尚未驗證是否支援新版功能。只有開始轉換時才會連線。');}
  catch{$('api-base').setAttribute('aria-invalid','true');service('轉換服務網址無效：請使用 HTTPS，或本機 localhost 的 HTTP；不要包含帳密、路徑或查詢參數。');}
 }
 $('api-base').value=DEFAULT_API_BASE;configure();$('api-base').addEventListener('input',configure);
 function revoke(){for(const url of urls)URL.revokeObjectURL(url);urls.clear();}
 function makeCard(job,number){
  const card=node('article',undefined,'job-card');card.setAttribute('role','listitem');
  const head=node('div',undefined,'job-head'),title=node('h3',number+'．'+job.title),badge=node('span',undefined,'badge');head.append(title,badge);
  const stage=node('p',undefined,'job-stage'),error=node('p',undefined,'error'),report=node('div'),downloadNote=node('p',undefined,'download-note'),actions=node('div',undefined,'actions');
  const errorDetails=node('details'),errorCode=node('p',undefined,'technical');errorDetails.append(node('summary','錯誤詳細資訊'),errorCode);
  const titleDetails=node('details'),fullTitle=node('p',job.title);titleDetails.append(node('summary','查看完整對話名稱'),fullTitle);
  card.append(head,titleDetails,stage,error,errorDetails,report,actions,downloadNote);
  const button=(label,action,secondary=true)=>{const b=node('button',label,secondary?'secondary':undefined);b.type='button';b.addEventListener('click',action);actions.append(b);return b;};
  const download=button('下載成果',()=>{
   const artifact=job.artifact;if(!artifact)return;const url=URL.createObjectURL(artifact.blob);urls.add(url);
   const a=document.createElement('a');a.href=url;a.download=safeFilename(artifact.filename,artifact.artifact_type);document.body.append(a);a.click();a.remove();
   job.downloadRequested=true;notify('已啟動下載；請確認瀏覽器已保存，再清除暫存 Word。網站無法確認磁碟保存狀態。');draw();
   setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
  },false);
  const release=button('清除暫存 Word（不影響已下載檔案）',()=>{job.type=job.artifact.artifact_type;queue.release(job);revoke();($('continue-conversion').disabled?$('conversion-title'):$('continue-conversion')).focus();});
  release.setAttribute('aria-description','僅清除本頁暫存檔，不影響已下載檔案；完整性報告保留。');
  const retry=button('重試失敗對話',()=>{$('conversion-title').focus();void resume();});
  const skip=button('略過失敗對話',()=>{queue.skip(job);$('conversion-title').focus();void resume();});
  return {card,title,titleDetails,fullTitle,badge,stage,error,errorDetails,errorCode,report,downloadNote,download,release,retry,skip,reported:null};
 }
 function draw(){
  const jobs=queue?.jobs||[];page=Math.max(0,Math.min(page,Math.ceil(jobs.length/PAGE_SIZE)-1));
  const visible=jobs.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE),keep=new Set(visible);
  // Only a bounded page of cards is mounted. Stable cards preserve focus/details.
  for(const job of cards.keys())if(!keep.has(job))cards.delete(job);
  for(const [offset,job]of visible.entries()){
   let view=cards.get(job);if(!view){view=makeCard(job,page*PAGE_SIZE+offset+1);cards.set(job,view);}
   const label=stateLabels[job.state]||'等待中';
   view.title.textContent=(page*PAGE_SIZE+offset+1)+'．'+text(job.title);view.badge.textContent=label;view.badge.className='badge '+job.state;view.titleDetails.hidden=Array.from(String(job.title)).length<=40;view.fullTitle.textContent=text(job.title);
   view.stage.textContent=stageText(job.stage);view.error.textContent=job.state==='failed'?explain(job.error):'';view.error.hidden=job.state!=='failed';view.errorDetails.hidden=job.state!=='failed';view.errorCode.textContent='錯誤代碼：'+text(job.error);
   if(job.report&&view.reported!==job.report){view.report.replaceChildren(reportElement(job));view.reported=job.report;}
   view.download.hidden=!job.artifact;view.release.hidden=!job.artifact;
   if(job.artifact)view.download.textContent='下載 '+job.artifact.artifact_type.toUpperCase();
   view.downloadNote.textContent=(job.downloadRequested?'已啟動下載（未確認是否保存至磁碟）。':'')+(job.state==='released'?'成果已從本頁記憶體釋放，完整性報告保留。':'');
   view.retry.hidden=job.state!=='failed';view.skip.hidden=job.state!=='failed';view.retry.disabled=!!queue.running;view.skip.disabled=!!queue.running;
   view.retry.textContent=job.collector?'重試缺少批次（含失敗批次 '+job.failedPart+'）':'重試失敗對話';
  }
  // Avoid disconnecting focused controls on each status event.
  const target=$('conversion-results');if(target.children.length!==visible.length||visible.some((job,i)=>target.children[i]!==cards.get(job).card))target.replaceChildren(...visible.map(job=>cards.get(job).card));
  $('queue-summary').textContent=jobs.length?'共 '+jobs.length+' 段 · '+queueView(jobs)+' · 成果暫存 '+((queue.retained||0)/1_000_000).toFixed(1)+' / 32 MB':'尚無轉換工作。';
  $('queue-pagination').hidden=jobs.length<=PAGE_SIZE;$('queue-page').textContent='第 '+(page+1)+' / '+Math.max(1,Math.ceil(jobs.length/PAGE_SIZE))+' 頁';
  $('queue-prev').disabled=page===0;$('queue-next').disabled=(page+1)*PAGE_SIZE>=jobs.length;$('queue-current').disabled=!queue?.running;
  $('cancel-conversion').disabled=!active;
  $('continue-conversion').disabled=!active||!!queue?.running||!!jobs.find(job=>job.state==='failed');
  $('clear-conversion').disabled=!!queue?.running||!jobs.length;
 }
 function update(job){
  if(job?.state==='failed'){
   notify('轉換失敗，已保留其他已完成成果。請查看該段的重試或略過選項；若要修改服務設定，請先取消佇列。');
   if(['API_UNAVAILABLE','API_INCOMPATIBLE','NETWORK_OR_CORS'].includes(job.error))service(explain(job.error));
  }else if(job?.state==='working')notify(stageText(job.stage)+'。請稍候；此階段不提供內部百分比。');
  if(job?.state==='done')service('已收到並驗證新版轉換回應。服務可用狀態仍以每次轉換結果為準。');
  const complete=queue?.jobs.every(j=>['done','released','skipped','cancelled'].includes(j.state));
  if(complete&&!queue.running){active=false;setLocked(false);if(queue.jobs.length&&!queue.controller.signal.aborted)notify('本次佇列已處理完畢。請查看各段完整性報告，再下載成果。');}
  draw();
 }
 async function resume(){
  if(!queue||queue.running)return;const current=epoch;
  try{await queue.resume();}catch(e){if(current===epoch)notify(explain(e.code||e.message));}finally{if(current===epoch)update(queue.current);}
 }
 async function start(items){
  if(active)return;
  if(queue?.jobs.some(job=>job.artifact)){notify('還有尚未釋放的成果。請先下載並清除暫存 Word，或清除全部轉換紀錄與暫存後，再開始新的轉換。');$('conversion-title').focus();return;}
  const current=++epoch;let started=false;
  try{
   // Validate before discarding a previous successful queue.
   const base=apiBase($('api-base').value);queue?.dispose();revoke();cards.clear();page=0;
   queue=queueFactory({base,extract,onUpdate:job=>{if(current===epoch)update(job);}});
   started=true;active=true;setLocked(true);notify('對話依序轉換中；完成後先查看各段完整性報告。');draw();
   $('conversion-title').focus();await queue.run(items);
  }catch(e){if(current===epoch){active=false;setLocked(false);notify(explain(e.code||e.message));if(e.code==='API_NOT_CONFIGURED'){$('service-settings').open=true;$('api-base').focus();configure();}}}finally{if(current===epoch){if(started)update(queue?.current);else draw();}}
 }
 $('share-form').addEventListener('submit',event=>{
  event.preventDefault();try{const url=shareURL($('share-url').value);$('share-url').removeAttribute('aria-invalid');$('share-error').textContent='';void start([{url,title:'公開分享對話'}]);}
  catch(e){$('share-url').setAttribute('aria-invalid','true');$('share-error').textContent='請貼上 ChatGPT 公開分享連結，格式為 https://chatgpt.com/share/ 後接完整分享編號。私人對話網址不適用。';$('share-url').focus();}
 });
 $('convert-selected').addEventListener('click',()=>{const items=getSelected();if(items.length)void start(items);else notify('請先勾選對話。');});
 $('continue-conversion').addEventListener('click',()=>void resume());
 const cancel=()=>{queue?.cancel();revoke();notify('已取消；已完成段落仍可下載。Render 子程序可能持續至後端期限。');if(!queue?.running){active=false;setLocked(false);}draw();};
 $('cancel-conversion').addEventListener('click',cancel);
 const clear=()=>{epoch++;queue?.dispose();queue=null;active=false;cards.clear();revoke();setLocked(false);notify('已清除全部轉換紀錄與暫存檔案；已下載的檔案不受影響。');draw();};
 $('clear-conversion').addEventListener('click',clear);
 $('queue-prev').addEventListener('click',()=>{page--;draw();});$('queue-next').addEventListener('click',()=>{page++;draw();});
 $('queue-current').addEventListener('click',()=>{const i=queue?.jobs.findIndex(j=>j.state==='working');if(i>=0){page=Math.floor(i/PAGE_SIZE);draw();}});
 window.addEventListener('pagehide',()=>{queue?.dispose();revoke();});
 draw();return {clear,cancel};
}
