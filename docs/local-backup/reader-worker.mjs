import {parseConversation,totalWords,findMessages,cleanDisplayText} from './reader-core.mjs';
import {splitMessages,splitHtmlVolumes,htmlDocument,richClipboard} from './reader-export.mjs';
let active=null,copyChunks=null;
self.onmessage=async({data})=>{
  const {type,request}=data;
  if(type==='close'){active=null;copyChunks=null;return;}
  try{
    if(type==='open'){
      if(!(data.blob instanceof Blob))throw Error('來源資料無效');
      // Limit is a client memory safeguard, not the Render 16 MB limit.
      if(data.blob.size>128*1024*1024)throw Error('單段 JSON 超過本機閱讀器目前 128 MiB 安全處理上限；沒有截斷資料');
      const json=JSON.parse(await data.blob.text());
      active=parseConversation(json);copyChunks=null;
      postMessage({type:'opened',request,title:active.title,count:active.messages.length,words:totalWords(active.messages),summary:active.summary});
    }else if(type==='openShared'){
      const source=data.source;
      if(!source||!Array.isArray(source.messages)||source.messages.length>20000)throw Error('分享內容無效或訊息數超過安全上限');
      const messages=source.messages.map((m,index)=>({
        id:'share-'+index,role:m.role==='user'?'user':'assistant',
        text:cleanDisplayText(String(m.text||''))
      })).filter(m=>m.text.trim());
      if(messages.length!==source.messages.length)throw Error('分享正文存在空白或無法還原的訊息，請檢查來源');
      active={title:String(source.title||'公開分享對話'),messages,
        summary:{rawNodes:messages.length,pathNodes:messages.length,offBranch:0,hidden:0,
        nonText:source.report?.issues||0,warnings:source.report?.warnings||[]}};
      copyChunks=null;
      postMessage({type:'opened',request,title:active.title,count:messages.length,
        words:totalWords(messages),summary:active.summary});
    }else if(type==='copyPlan'){
      if(!active)throw Error('請先開啟對話');
      const first=data.first==null?1:Number(data.first),last=data.last==null?active.messages.length:Number(data.last);
      if(!Number.isSafeInteger(first)||!Number.isSafeInteger(last)||first<1||last<first||last>active.messages.length)throw Error('複製範圍無效');
      copyChunks=splitMessages(active.messages.slice(first-1,last)).map(c=>({...c,start:c.start+first-1}));
      postMessage({type:'copyPlan',request,chunks:copyChunks.map(c=>({start:c.start,count:c.messages.length})),total:active.messages.length});
    }else if(type==='copyChunk'){
      if(!active)throw Error('請先開啟對話');
      const chunk=copyChunks?.[data.index];if(!chunk)throw Error('複製批次不存在');
      postMessage({type:'copyChunk',request,index:data.index,start:chunk.start,count:chunk.messages.length,payload:richClipboard(chunk.messages)});
    }else if(type==='htmlSingle'){
      if(!active)throw Error('請先開啟對話');
      const totalChars=active.messages.reduce((n,m)=>n+m.text.length,0);
      if(totalChars>60_000_000)throw Error('單段正文超過安全單檔界線，請改用分卷 HTML');
      const html=htmlDocument(active.title,active.messages,0,active.messages.length);
      if(html.length>100_000_000)throw Error('單檔 HTML 超過安全記憶體界線，請改用分卷 HTML');
      postMessage({type:'htmlSingle',request,html,count:active.messages.length});
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
