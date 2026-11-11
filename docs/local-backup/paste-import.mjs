/* User-pasted transcript fallback. All processing and .docx generation stay local. */
import {zipFiles} from './reader-export.mjs';

const xml=s=>String(s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/g,'')
  .replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const LIMIT=2_000_000;
export function parsePastedConversation(title,raw){
  if(typeof raw!=='string'||!raw.trim())throw Error('請先貼上對話內容。');
  if(raw.length>LIMIT)throw Error('貼上的內容超過 200 萬字元，請分段處理。');
  const text=raw.replace(/\r\n?/g,'\n').trim();
  const marker=/^(?:你說(?:：|:)|使用者(?:：|:)|You said:|ChatGPT 說(?:：|:)|ChatGPT said:)\s*$/i;
  const lines=text.split('\n'),messages=[];let role='assistant',buffer=[],recognized=0;
  const flush=()=>{const t=buffer.join('\n').trim();if(t)messages.push({role,text:t});buffer=[];};
  for(const line of lines){
    const label=line.trim();
    if(marker.test(label)){
      flush();role=/^(?:你說|使用者|You said)/i.test(label)?'user':'assistant';recognized++;
    }else buffer.push(line);
  }
  flush();
  if(!messages.length)throw Error('沒有可辨識的文字內容。');
  return {title:String(title||'貼上的對話').trim().slice(0,100)||'貼上的對話',
    messages,recognized,warning:recognized===0?'未找到「你說：／ChatGPT 說：」等角色標記，內容會視為一則未分角色文字。':'僅根據貼上的角色標記分段，請確認訊息順序與內容完整。'};
}
const paragraph=(text,style='')=>'<w:p>'+(style?'<w:pPr><w:pStyle w:val="'+style+'"/></w:pPr>':'')
  +'<w:r><w:t xml:space="preserve">'+xml(text)+'</w:t></w:r></w:p>';
export function makeLocalDocx(title,messages){
  if(!Array.isArray(messages)||!messages.length)throw Error('沒有可匯出的訊息。');
  const blocks=[paragraph(title,'Title')];
  for(const message of messages){
    blocks.push(paragraph(message.role==='user'?'使用者':'ChatGPT','Heading2'));
    for(const line of message.text.split('\n'))blocks.push(paragraph(line));
  }
  const document='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    +'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    +blocks.join('')+'<w:sectPr/></w:body></w:document>';
  const types='<?xml version="1.0" encoding="UTF-8"?>'
    +'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    +'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    +'<Default Extension="xml" ContentType="application/xml"/>'
    +'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    +'</Types>';
  const rels='<?xml version="1.0" encoding="UTF-8"?>'
    +'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    +'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    +'</Relationships>';
  return zipFiles([{name:'[Content_Types].xml',content:types},{name:'_rels/.rels',content:rels},{name:'word/document.xml',content:document}]);
}
