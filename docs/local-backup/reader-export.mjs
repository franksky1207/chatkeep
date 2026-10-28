const escapeHtml=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const inline=s=>escapeHtml(s).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>');
export const safeHtmlName=s=>(String(s||'對話').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/,'').slice(0,100)||'對話');
export function messageHtml(m){
 let out='',code=false,list='';
 const close=()=>{if(list){out+='</'+list+'>';list='';}};
 const lines=m.text.split('\n');
 for(let i=0;i<lines.length;i++){
  const line=lines[i];
  if(line.trim().startsWith(String.fromCharCode(96).repeat(3))){close();out+=code?'</code></pre>':'<pre><code>';code=!code;continue;}
  if(code){out+=escapeHtml(line)+'\n';continue;}
  if(!line.trim())continue;
  const heading=/^(#{1,6})\s+(.+)$/.exec(line);
  if(heading){close();const h=Math.min(heading[1].length+1,6);out+='<h'+h+'>'+inline(heading[2])+'</h'+h+'>';continue;}
  const bullet=/^\s*(?:([-*+])|(\d+)[.)])\s+(.+)$/.exec(line);
  if(bullet){const tag=bullet[2]?'ol':'ul';if(list!==tag){close();out+='<'+tag+'>';list=tag;}out+='<li>'+inline(bullet[3])+'</li>';continue;}
  close();
  if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
    const cells=s=>s.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
    out+='<table><thead><tr>'+cells(line).map(c=>'<th>'+inline(c)+'</th>').join('')+'</tr></thead><tbody>';i++;
    while(i+1<lines.length&&lines[i+1].includes('|')){i++;out+='<tr>'+cells(lines[i]).map(c=>'<td>'+inline(c)+'</td>').join('')+'</tr>';}
    out+='</tbody></table>';continue;
  }
  out+='<p>'+inline(line)+'</p>';
 }
 close();if(code)out+='</code></pre>';
 return '<section class="message"><h2 class="role">'+(m.role==='user'?'使用者':'ChatGPT')+'</h2>'+out+'</section>';
}
const CSS='body{font:14px/1.35 sans-serif;max-width:850px;margin:22px auto;padding:0 12px}.message{padding:5px 0 10px;border-bottom:1px solid #ddd}.role{font-size:15px;margin:0 0 6px;color:#175c75}p{margin:0 0 3px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:4px}pre{white-space:pre-wrap;overflow-wrap:anywhere}';
export function htmlDocument(title,messages,start=0,total=messages.length){
 return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>'+escapeHtml(title)+'</title><style>'+CSS+'</style></head><body><h1>'+escapeHtml(title)+'</h1><p>訊息 '+(start+1)+'～'+(start+messages.length)+'／'+total+'</p>'+messages.map(messageHtml).join('')+'</body></html>';
}
export function richClipboard(messages){return {html:messages.map(messageHtml).join(''),text:messages.map(m=>(m.role==='user'?'使用者':'ChatGPT')+'\n'+m.text).join('\n\n')};}
export function splitMessages(messages,limit=300000){
 const chunks=[];let start=0,batch=[],size=0;
 const flush=()=>{if(batch.length){chunks.push({start,messages:batch});start+=batch.length;batch=[];size=0;}};
 for(const m of messages){const n=m.text.length+160;if(n>limit)throw Error('單則訊息超過安全複製大小，請使用 HTML 下載');if(batch.length&&size+n>limit)flush();batch.push(m);size+=n;}flush();return chunks;
}
export function splitHtmlVolumes(messages,limit=600000){
 const chunks=[];let start=0,batch=[],size=0;
 const flush=()=>{if(batch.length){chunks.push({start,messages:batch});start+=batch.length;batch=[];size=0;}};
 for(const m of messages){const n=m.text.length+160;if(batch.length&&size+n>limit)flush();batch.push(m);size+=n;}flush();return chunks;
}
const table=Array.from({length:256},(_,i)=>{let c=i;for(let j=0;j<8;j++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
const crc32=b=>{let c=0xffffffff;for(const n of b)c=table[(c^n)&255]^(c>>>8);return(c^0xffffffff)>>>0;};
const u16=n=>[n&255,n>>>8&255],u32=n=>[n&255,n>>>8&255,n>>>16&255,n>>>24&255];
export function zipFiles(files){
 const enc=new TextEncoder(),parts=[],directory=[];let offset=0;
 if(files.length>65535)throw Error('ZIP 檔案數量超限');
 for(const f of files){
  const name=enc.encode(f.name),bytes=enc.encode(f.content),crc=crc32(bytes);
  if(name.length>65535||bytes.length>0xffffffff||offset>0xffffffff)throw Error('ZIP 容量超限');
  const local=new Uint8Array([...u32(0x04034b50),...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(0),...u32(crc),...u32(bytes.length),...u32(bytes.length),...u16(name.length),...u16(0)]);
  parts.push(local,name,bytes);
  directory.push(new Uint8Array([...u32(0x02014b50),...u16(20),...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(0),...u32(crc),...u32(bytes.length),...u32(bytes.length),...u16(name.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset)]),name);
  offset+=local.length+name.length+bytes.length;
 }
 const length=directory.reduce((a,b)=>a+b.length,0);if(offset+length>0xffffffff)throw Error('ZIP 總容量超限');
 return new Blob([...parts,...directory,new Uint8Array([...u32(0x06054b50),...u16(0),...u16(0),...u16(files.length),...u16(files.length),...u32(length),...u32(offset),...u16(0)])],{type:'application/zip'});
}
