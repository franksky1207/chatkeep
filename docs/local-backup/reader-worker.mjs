import {parseConversation,totalWords,findMessages} from './reader-core.mjs';
import {splitMessages,splitHtmlVolumes,htmlDocument,richClipboard} from './reader-export.mjs';
let active=null;
self.onmessage=async({data})=>{
  const {type,request}=data;
  if(type==='close'){active=null;return;}
  try{
    if(type==='open'){
      if(!(data.blob instanceof Blob))throw Error('來源資料無效');
      // Limit is a client memory safeguard, not the Render 16 MB limit.
      if(data.blob.size>128*1024*1024)throw Error('單段 JSON 超過本機閱讀器目前 128 MiB 安全處理上限；沒有截斷資料');
      const json=JSON.parse(await data.blob.text());
      active=parseConversation(json);
      postMessage({type:'opened',request,title:active.title,count:active.messages.length,words:totalWords(active.messages),summary:active.summary});
    }else if(type==='copyPlan'){
      if(!active)throw Error('請先開啟對話');
      const chunks=splitMessages(active.messages);
      postMessage({type:'copyPlan',request,chunks:chunks.map(c=>({start:c.start,count:c.messages.length})),total:active.messages.length});
    }else if(type==='copyChunk'){
      if(!active)throw Error('請先開啟對話');
      const chunks=splitMessages(active.messages);
      const chunk=chunks[data.index];if(!chunk)throw Error('複製批次不存在');
      postMessage({type:'copyChunk',request,index:data.index,start:chunk.start,count:chunk.messages.length,payload:richClipboard(chunk.messages)});
    }else if(type==='htmlPlan'){
      if(!active)throw Error('請先開啟對話');
      const volumes=splitHtmlVolumes(active.messages);
      postMessage({type:'htmlPlan',request,total:active.messages.length,volumes:volumes.map(v=>({start:v.start,count:v.messages.length}))});
    }else if(type==='htmlVolume'){
      if(!active)throw Error('請先開啟對話');
      const volumes=splitHtmlVolumes(active.messages),v=volumes[data.index];
      if(!v)throw Error('HTML 分卷不存在');
      postMessage({type:'htmlVolume',request,html:htmlDocument(active.title,v.messages,v.start,active.messages.length),start:v.start,count:v.messages.length});
    }else if(type==='page'){
      if(!active)throw Error('請先開啟對話');
      const page=Math.max(0,Math.floor(data.page||0)),limit=50;
      postMessage({type:'page',request,page,total:active.messages.length,messages:active.messages.slice(page*limit,(page+1)*limit)});
    }else if(type==='search'){
      if(!active)throw Error('請先開啟對話');
      postMessage({type:'search',request,hits:findMessages(active.messages,String(data.query||''))});
    }
  }catch(e){postMessage({type:'readerError',request,message:e.message||'閱讀器解析失敗'});}
};
