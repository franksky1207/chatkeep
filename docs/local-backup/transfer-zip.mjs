/* Bounded ZIP32 for backend artifacts, not an importer for arbitrary backup ZIPs. */
import {crc32} from './zip.mjs';
import {check,fail,encoder,bytesSha} from './transfer-format.mjs';
export const MAX_OUTPUT=16_000_000;
const v=bytes=>new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
const crc=bytes=>(crc32(bytes)^0xffffffff)>>>0;
async function read(blob,start,size){if(start<0||size<0||start+size>blob.size)fail('INVALID_ARTIFACT');return new Uint8Array(await blob.slice(start,start+size).arrayBuffer());}
const equal=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
function extra(bytes){const d=v(bytes);for(let i=0;i<bytes.length;){if(i+4>bytes.length)fail('INVALID_ARTIFACT');const id=d.getUint16(i,true),n=d.getUint16(i+2,true);if(id===1||i+4+n>bytes.length)fail('INVALID_ARTIFACT');i+=4+n;}}
export async function entries(blob,{docx=false,signal}={}){
 check(signal);if(blob.size>MAX_OUTPUT||blob.size<22)fail('OUTPUT_LIMIT');
 const tail=await read(blob,Math.max(0,blob.size-65557),Math.min(blob.size,65557)),d=v(tail);let end=-1;
 for(let i=tail.length-22;i>=0;i--)if(d.getUint32(i,true)===0x06054b50&&i+22+d.getUint16(i+20,true)===tail.length){end=i;break;}
 if(end<0||d.getUint16(end+4,true)||d.getUint16(end+6,true))fail('INVALID_ARTIFACT');
 const count=d.getUint16(end+10,true),cdSize=d.getUint32(end+12,true),cd=d.getUint32(end+16,true);
 if(!count||count>(docx?64:16)||count!==d.getUint16(end+8,true)||cd+cdSize!==blob.size-tail.length+end)fail('INVALID_ARTIFACT');
 let pos=cd,total=0;const found=[],names=new Set(),ranges=[];
 for(let i=0;i<count;i++){
  check(signal);const h=v(await read(blob,pos,46));if(h.getUint32(0,true)!==0x02014b50||h.getUint16(34,true))fail('INVALID_ARTIFACT');
  const flags=h.getUint16(8,true),method=h.getUint16(10,true),sum=h.getUint32(16,true),compressed=h.getUint32(20,true),size=h.getUint32(24,true),nl=h.getUint16(28,true),el=h.getUint16(30,true),cl=h.getUint16(32,true),local=h.getUint32(42,true);
  if(flags&~0x800||![0,8].includes(method)||!docx&&method!==0||nl>512||!nl||pos+46+nl+el+cl>cd+cdSize)fail('INVALID_ARTIFACT');
  const nameBytes=await read(blob,pos+46,nl);let name;try{name=new TextDecoder('utf-8',{fatal:true}).decode(nameBytes);}catch{fail('INVALID_ARTIFACT');}
  if(names.has(name)||name.split('/').some(p=>p==='..'||p==='.')||name.includes('\\')||name.startsWith('/')||!docx&&name.includes('/'))fail('INVALID_ARTIFACT');names.add(name);
  extra(await read(blob,pos+46+nl,el));
  const l=v(await read(blob,local,30));if(l.getUint32(0,true)!==0x04034b50||l.getUint16(6,true)!==flags||l.getUint16(8,true)!==method||l.getUint32(14,true)!==sum||l.getUint32(18,true)!==compressed||l.getUint32(22,true)!==size)fail('INVALID_ARTIFACT');
  const lnl=l.getUint16(26,true),lel=l.getUint16(28,true),start=local+30+lnl+lel;
  if(!equal(nameBytes,await read(blob,local+30,lnl))||start+compressed>cd||method===0&&compressed!==size)fail('INVALID_ARTIFACT');
  extra(await read(blob,local+30+lnl,lel));
  total+=size;if(size>(docx?8_100_000:MAX_OUTPUT)||total>(docx?12_000_000:MAX_OUTPUT))fail('OUTPUT_LIMIT');
  found.push({name,start,compressed,size,method,crc:sum});ranges.push([local,start+compressed]);pos+=46+nl+el+cl;
 }
 if(pos!==cd+cdSize)fail('INVALID_ARTIFACT');ranges.sort((a,b)=>a[0]-b[0]);let next=0;
 for(const [a,b]of ranges){if(a!==next)fail('INVALID_ARTIFACT');next=b;}if(next!==cd)fail('INVALID_ARTIFACT');
 return found;
}
export async function entryBytes(blob,entry,{signal}={}){
 check(signal);let data;
 if(entry.method===0)data=await read(blob,entry.start,entry.size);
 else{
  if(typeof DecompressionStream!=='function')fail('UNSUPPORTED_DECOMPRESSION');
  let offset=entry.start,reader;
  const input=new ReadableStream({async pull(controller){if(offset>=entry.start+entry.compressed){controller.close();return;}const end=Math.min(offset+1024,entry.start+entry.compressed);controller.enqueue(await read(blob,offset,end-offset));offset=end;}});
  try{reader=input.pipeThrough(new DecompressionStream('deflate-raw')).getReader();}catch{fail('UNSUPPORTED_DECOMPRESSION');}
  const parts=[];let size=0;
  try{while(true){check(signal);const r=await reader.read();if(r.done)break;size+=r.value.length;if(size>entry.size)fail('OUTPUT_LIMIT');parts.push(r.value);}}
  catch(e){if(e.name==='AbortError'||['OUTPUT_LIMIT','INVALID_ARTIFACT'].includes(e.code))throw e;fail('INVALID_ARTIFACT');}
  finally{await reader.cancel().catch(()=>{});}
  if(size!==entry.size)fail('INVALID_ARTIFACT');data=new Uint8Array(size);let p=0;for(const part of parts){data.set(part,p);p+=part.length;}
 }
 if(data.length!==entry.size||crc(data)!==entry.crc)fail('ARTIFACT_CRC');return data;
}
function bookmarks(xml){
 // Narrow XML lexer for python-docx output. No DOM, DTD, entity expansion or eval.
 const stack=[],result=[];let p=0,root=false;
 while(p<xml.length){const start=xml.indexOf('<',p);if(start<0)break;
  if(xml.startsWith('<!--',start)){const end=xml.indexOf('-->',start+4);if(end<0)fail('INVALID_DOCX');p=end+3;continue;}
  if(xml.startsWith('<?',start)){const end=xml.indexOf('?>',start+2);if(end<0)fail('INVALID_DOCX');p=end+2;continue;}
  if(xml[start+1]==='!')fail('INVALID_DOCX');
  let end=start+1,quote=null;for(;end<xml.length;end++){const c=xml[end];if(quote){if(c===quote)quote=null;}else if(c==='"'||c==="'")quote=c;else if(c==='>')break;}
  if(end===xml.length||quote)fail('INVALID_DOCX');const tag=xml.slice(start+1,end),closing=tag[0]==='/',self=/\/$/.test(tag),match=tag.match(/^\/?([\w:.-]+)/);if(!match)fail('INVALID_DOCX');const name=match[1];
  if(closing){const frame=stack.pop();if(!frame||frame.name!==name||name==='w:tc'&&frame.last!=='w:p')fail('INVALID_DOCX');}
  else{
   const attrs={};let rest=tag.slice(match[0].length).replace(/\/$/,'');
   while(rest.trim()){const a=rest.match(/^\s+([\w:.-]+)\s*=\s*("[^"]*"|'[^']*')/);if(!a||Object.hasOwn(attrs,a[1]))fail('INVALID_DOCX');attrs[a[1]]=a[2].slice(1,-1);rest=rest.slice(a[0].length);}
   if(!root){if(name!=='w:document'||attrs['xmlns:w']!=='http://schemas.openxmlformats.org/wordprocessingml/2006/main')fail('INVALID_DOCX');root=true;}
   if(stack.length)stack.at(-1).last=name;
   if(name==='w:bookmarkStart'&&attrs['w:name']?.startsWith('ChatKeepMessage_'))result.push(attrs['w:name']);
   if(!self)stack.push({name,last:null});
  }
  p=end+1;
 }if(stack.length||!root)fail('INVALID_DOCX');return result;
}
export async function verifyDocx(blob,first,last,{signal}={}){
 const files=await entries(blob,{docx:true,signal});let xml=null;
 for(const file of files){const data=await entryBytes(blob,file,{signal});if(file.name==='word/document.xml')try{xml=new TextDecoder('utf-8',{fatal:true}).decode(data);}catch{fail('INVALID_DOCX');}}
 if(xml===null)fail('INVALID_DOCX');const actual=bookmarks(xml),expected=Array.from({length:last-first+1},(_,i)=>'ChatKeepMessage_'+(first+i));
 if(actual.length!==expected.length||actual.some((v,i)=>v!==expected[i]))fail('BOOKMARK_MISMATCH');
}
export async function writeZip(files,{signal}={}){
 check(signal);if(!files.length||files.length>16)fail('VOLUME_LIMIT');
 let offset=0,total=22;const local=[],central=[],names=new Set();
 for(const file of files){check(signal);const name=encoder.encode(file.name);if(!name.length||name.length>240||names.has(file.name)||/[\\/]/.test(file.name))fail('INVALID_ARTIFACT');names.add(file.name);
  total+=file.blob.size+76+name.length*2;if(total>MAX_OUTPUT)fail('OUTPUT_LIMIT');
  const data=new Uint8Array(await file.blob.arrayBuffer()),sum=crc(data),h=new Uint8Array(30+name.length),d=v(h);
  d.setUint32(0,0x04034b50,true);d.setUint16(4,20,true);d.setUint16(6,0x800,true);d.setUint16(12,33,true);d.setUint32(14,sum,true);d.setUint32(18,data.length,true);d.setUint32(22,data.length,true);d.setUint16(26,name.length,true);h.set(name,30);
  const c=new Uint8Array(46+name.length),cv=v(c);cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint16(14,33,true);cv.setUint32(16,sum,true);cv.setUint32(20,data.length,true);cv.setUint32(24,data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);c.set(name,46);
  local.push(h,file.blob);central.push(c);offset+=h.length+file.blob.size;
 }
 const cdSize=central.reduce((n,c)=>n+c.length,0),end=new Uint8Array(22),e=v(end);e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,cdSize,true);e.setUint32(16,offset,true);
 const blob=new Blob([...local,...central,end],{type:'application/zip'});if(blob.size!==total)fail('INTEGRITY_FAILED');return blob;
}
export {bytesSha};
