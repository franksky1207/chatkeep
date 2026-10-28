/* Pages conversion boundary: no backup parsing, persistence, or content logging. */
import {prepareInWorker,sendPrepared} from './transfer-client.mjs';
import {TransferResults} from './transfer-results.mjs';
import {entries,entryBytes,verifyDocx,MAX_OUTPUT} from './transfer-zip.mjs';
import {bytesSha,check,fail} from './transfer-format.mjs';
export const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
export const RETAINED_LIMIT=32_000_000;
export function apiBase(value){
 let u;try{u=new URL(value);}catch{fail('API_NOT_CONFIGURED');}
 if(u.username||u.password||u.search||u.hash||u.pathname!=='/'||
    !(u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname)))fail('API_NOT_CONFIGURED');
 return u.origin;
}
export function shareURL(value){
 const s=value.trim();if(!/^https:\/\/chatgpt\.com\/share\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s))fail('INVALID_URL');return s;
}
export function safeFilename(value,type){
 const stem=String(value||'ChatKeep').replace(/\.(docx|zip)$/i,'').replace(/[<>:"/\\|?*\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/g,'_').replace(/^[ .]+|[ .]+$/g,'');
 const name=Array.from(stem).slice(0,80).join('')||'ChatKeep';return (/^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])($|\.)/i.test(name)?'_':'')+name+'.'+type;
}
export function capabilities(){
 if(typeof Worker==='undefined')fail('UNSUPPORTED_WORKER');if(!globalThis.crypto?.subtle)fail('UNSUPPORTED_CRYPTO');
 try{new DecompressionStream('deflate-raw');}catch{fail('UNSUPPORTED_DECOMPRESSION');}
}
export async function transport(base,path,body,{signal,fetcher=fetch}={}){
 check(signal);if(!['/api/convert-v2','/api/convert-json','/api/convert-chunk-v1'].includes(path))fail('INVALID_TRANSFER');
 const payload=body instanceof Blob?body:JSON.stringify(body);
 if((payload instanceof Blob?payload.size:new TextEncoder().encode(payload).length)>(path==='/api/convert-v2'?4096:2_000_000))fail('INPUT_TOO_LARGE');
 let response;try{response=await fetcher(apiBase(base)+path,{method:'POST',headers:{'Content-Type':'application/json'},body:payload,signal,credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer',redirect:'error'});}catch(e){check(signal);fail('NETWORK_OR_CORS');}
 const retryAfter=response.headers.get('Retry-After');
 if(!/^application\/json(?:\s*;|$)/i.test(response.headers.get('Content-Type')||''))fail(response.status===404?'API_UNAVAILABLE':'API_INCOMPATIBLE');
 if(Number(response.headers.get('Content-Length'))>24_000_000)fail('OUTPUT_LIMIT');
 // Bound streamed envelopes even when Content-Length is absent/untrusted.
 const reader=response.body?.getReader();if(!reader)fail('API_INCOMPATIBLE');const decoder=new TextDecoder('utf-8',{fatal:true});let size=0,text='';
 try{for(;;){check(signal);const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>24_000_000)fail('OUTPUT_LIMIT');text+=decoder.decode(value,{stream:true});}text+=decoder.decode();}
 catch(e){await reader.cancel().catch(()=>{});check(signal);if(e.code)throw e;fail('NETWORK_OR_CORS');}
 let value;try{value=JSON.parse(text);}catch{fail('API_INCOMPATIBLE');}
 if(response.status===404)fail('API_UNAVAILABLE');
 return {status:response.status,value,retryAfter};
}
export async function verifyEnvelope(value,{signal,onStage=()=>{}}={}){
 check(signal);if(!value?.ok||value.api_version!==2)fail('API_INCOMPATIBLE');
 const type=value.artifact_type,mime=type==='docx'?DOCX:type==='zip'?'application/zip':null,r=value.report;
 if(!mime||value.mime_type!==mime||!r||r.complete!==true||r.missing!==false||r.duplicated!==false||r.truncated!==false||
    !Array.isArray(r.volumes)||!r.volumes.length||r.volumes.length>16||r.docx_volume_count!==r.volumes.length||
    !Number.isSafeInteger(r.output_message_count)||r.output_message_count<1||r.expected_output_message_count!==r.output_message_count||
    !['official_json','share_link'].includes(r.source)||r.integrity_basis!=='normalized_output_sequence'||!Array.isArray(r.warnings)||r.warnings.length>32)fail('INVALID_RESPONSE');
 const b64=value.document;if(typeof b64!=='string'||b64.length>21_333_336||b64.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(b64))fail('INVALID_ARTIFACT');
 let raw;try{raw=atob(b64);}catch{fail('INVALID_ARTIFACT');}if(raw.length>MAX_OUTPUT)fail('OUTPUT_LIMIT');
 const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
 const blob=new Blob([bytes],{type:mime});let files;
 onStage('分卷驗證');
 if(type==='docx'&&r.volumes.length===1)files=[{name:value.filename,blob}];
 else if(type==='zip'&&r.volumes.length>1){files=[];for(const entry of await entries(blob,{signal})){const data=await entryBytes(blob,entry,{signal});files.push({name:entry.name,blob:new Blob([data])});}}
 else fail('INVALID_ARTIFACT');
 if(files.length!==r.volumes.length)fail('MANIFEST_MISMATCH');let next=1;
 for(let i=0;i<files.length;i++){
  check(signal);const v=r.volumes[i],f=files[i];
  if(v.number!==i+1||v.filename!==f.name||v.first_message!==next||!Number.isSafeInteger(v.last_message)||v.last_message<next||v.message_count!==v.last_message-next+1||v.docx_bytes!==f.blob.size)fail('MANIFEST_MISMATCH');
  if(await bytesSha(new Uint8Array(await f.blob.arrayBuffer()))!==v.file_sha256)fail('ARTIFACT_HASH');
  await verifyDocx(f.blob,next,v.last_message,{signal});next=v.last_message+1;
 }
 if(next!==r.output_message_count+1)fail('MANIFEST_MISMATCH');check(signal);
 return {blob,filename:safeFilename(value.filename,type),artifact_type:type,mime_type:mime,report:r};
}
const sleep=(ms,signal)=>new Promise((resolve,reject)=>{
 check(signal);const cancel=()=>{clearTimeout(timer);reject(new DOMException('已取消','AbortError'));};
 const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},ms);signal?.addEventListener('abort',cancel,{once:true});
});
export class ConversionQueue{
 constructor({base,extract,onUpdate=()=>{},prepare=prepareInWorker,send=transport,wait=sleep,featureCheck=capabilities}={}){
  Object.assign(this,{base:apiBase(base),extract,onUpdate,prepare,send,wait,featureCheck});this.jobs=[];this.retained=0;this.running=false;this.controller=new AbortController();
 }
 emit(job,stage){job.stage=stage;this.onUpdate(job,this);}
 async once(path,body,job){
  for(let attempt=0;;attempt++){
   await this.wait(6100,this.controller.signal);check(this.controller.signal);this.emit(job,'上傳批次 1 / 1；Render 正在轉換（無內部百分比）');
   const c=new AbortController(),abort=()=>c.abort();this.controller.signal.addEventListener('abort',abort,{once:true});
   const timer=setTimeout(()=>c.abort(),55000);let result;
   try{result=await this.send(this.base,path,body,{signal:c.signal});}
   catch(e){check(this.controller.signal);if(c.signal.aborted)fail('BATCH_TIMEOUT');throw e;}
   finally{clearTimeout(timer);this.controller.signal.removeEventListener('abort',abort);}
   if(c.signal.aborted)fail('BATCH_TIMEOUT');
   if(result.status===429&&attempt<2){this.emit(job,'節流等待 Retry-After');const n=Number(result.retryAfter??60);await this.wait(Math.min(120000,Math.max(2000,Number.isFinite(n)?n*1000:60000)),this.controller.signal);continue;}
   if(result.status!==200)fail(result.value?.error?.code||'API_INCOMPATIBLE');return result.value;
  }
 }
 async run(items){
  if(this.running||this.jobs.length)fail('BUSY');this.featureCheck();
  this.jobs=items.map(item=>({item,title:item.title,stage:'等待',state:'pending'}));await this.resume();
 }
 async resume(){
  if(this.running)return;check(this.controller.signal);this.running=true;
  try{for(const job of this.jobs){
   if(job.state==='done'||job.state==='released'||job.state==='skipped')continue;
   if(this.retained+MAX_OUTPUT>RETAINED_LIMIT){this.emit(job,'容量暫停：請下載並釋放先前成果後繼續');return;}
   this.current=job;job.state='working';
   try{
    let artifact;
    if(job.item.url){artifact=await verifyEnvelope(await this.once('/api/convert-v2',{url:shareURL(job.item.url)},job),{signal:this.controller.signal,onStage:s=>this.emit(job,s)});}
    else{
     if(!job.prepared){this.emit(job,'對話準備：擷取單一已選對話');const blob=await this.extract(job.item,this.controller.signal);check(this.controller.signal);this.emit(job,'對話準備：驗證目前分支');job.prepared=await this.prepare(blob,{signal:this.controller.signal});}
     const p=job.prepared;
     if(p.mode==='official')artifact=await verifyEnvelope(await this.once('/api/convert-json',p.blob,job),{signal:this.controller.signal,onStage:s=>this.emit(job,s)});
     else{
      job.collector??=new TransferResults(p);
      const indices=p.chunks.map(c=>c.part_index).filter(i=>!job.collector.results.has(i));
      await sendPrepared(p,{collector:job.collector,signal:this.controller.signal,indices,wait:this.wait,
       send:async(packet,{signal})=>{job.failedPart=packet.part_index;this.emit(job,'上傳批次 '+packet.part_index+' / '+p.chunks.length+'；Render 正在轉換');const result=await this.send(this.base,'/api/convert-chunk-v1',packet,{signal});this.emit(job,'分卷驗證：批次 '+packet.part_index);return result;}});
      this.emit(job,'分卷驗證：核對全部批次');artifact=await job.collector.finish({signal:this.controller.signal,onStage:s=>this.emit(job,s)});
     }
    }
    check(this.controller.signal);job.artifact=artifact;if(job.item.url)job.title=artifact.filename.replace(/\.(docx|zip)$/i,'');job.report=artifact.report;this.retained+=artifact.blob.size;job.prepared=null;job.collector=null;job.state='done';this.emit(job,'下載準備完成');
   }catch(e){
    if(this.controller.signal.aborted||e.name==='AbortError'){job.prepared=null;job.collector?.cancel();job.collector=null;job.state='cancelled';this.emit(job,'已取消');return;}
    job.state='failed';job.error=e.code||e.message||'CONVERSION_FAILED';this.emit(job,'失敗');return;
   }
  }}finally{this.running=false;this.onUpdate(this.current,this);}
 }
 release(job){if(job.artifact){this.retained-=job.artifact.blob.size;job.artifact=null;job.state='released';this.emit(job,'成果已釋放；報告保留');}}
 skip(job){job.prepared=null;job.collector?.cancel();job.collector=null;job.state='skipped';this.emit(job,'已略過');}
 cancel(){this.controller.abort();for(const job of this.jobs){if(!['done','released','skipped'].includes(job.state)){job.collector?.cancel();job.collector=null;job.prepared=null;job.state='cancelled';job.artifact=null;this.emit(job,'已取消');}}}
 dispose(){this.cancel();for(const job of this.jobs)this.release(job);this.jobs=[];}
}
export function explain(code){
 const map={INVALID_URL:'請輸入 https://chatgpt.com/share/UUID 公開分享網址。',API_NOT_CONFIGURED:'請設定已支援新版 API 的本機或測試 Render 位址；正式 v1.0.0 尚未部署新版路由。',API_UNAVAILABLE:'API 尚未部署或位址不正確；請確認新版服務後重試。',API_INCOMPATIBLE:'API 版本或回應不相容；請使用支援 v2 的服務。',NETWORK_OR_CORS:'連線中斷或跨來源請求遭阻擋；請檢查網路、API 位址與 Render 來源白名單後重試。',RATE_LIMITED:'已達速率限制；請等候至少 60 秒後重試。',BUSY:'Render 正忙；請稍後重試。',UNSUPPORTED_WORKER:'瀏覽器不支援 Worker；請使用新版桌面瀏覽器。',UNSUPPORTED_CRYPTO:'需要安全連線與 WebCrypto；請使用 HTTPS 或 localhost。',UNSUPPORTED_DECOMPRESSION:'瀏覽器不支援 deflate-raw DecompressionStream；請更新瀏覽器。',PREPARATION_FAILED:'準備 Worker 停止；請減少選取內容或改用電腦後重試。'};
 if(map[code])return code+'：'+map[code];
 if(/LIMIT|TOO_LARGE/.test(code))return code+'：超過安全容量；請減少內容或選取較小對話，單則訊息不能裁切。';
 if(/TIMEOUT/.test(code))return code+'：轉換或傳輸逾時；請稍後重試失敗批次。';
 if(/MISMATCH|MISSING|HASH|CRC|BOOKMARK|INVALID_ARTIFACT|INVALID_DOCX|INVALID_RESPONSE/.test(code))return code+'：完整性驗證失敗，未提供下載；請重試失敗批次或重新準備。';
 if(code==='INVALID_BRANCH'||code==='UNSUPPORTED_CONTENT')return code+'：無法確認分支或含不支援內容，未產生不完整文件；請改選可支援的文字對話。';
 return code+'：未完成轉換；請確認來源及服務版本後重試。';
}
