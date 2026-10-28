/* Dedicated opt-in preparation worker. Existing index/extract worker is untouched. */
import {prepareSelected} from './transfer-format.mjs';
let active=false;
self.onmessage=async({data})=>{
 if(data.type!=='prepare'||active)return;active=true;
 try{const prepared=await prepareSelected(data.blob);self.postMessage({type:'prepared',prepared});}
 catch(e){self.postMessage({type:'error',code:e.code||'PREPARATION_FAILED',message:e.code?'選取對話準備失敗：'+e.code:'無法安全準備選取對話。'});}
 finally{active=false;}
};
