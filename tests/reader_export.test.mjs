import test from 'node:test';
import assert from 'node:assert/strict';
import {htmlDocument,richClipboard,splitMessages,splitHtmlVolumes,zipFiles,safeHtmlName} from '../docs/local-backup/reader-export.mjs';
const messages=[{role:'user',text:'第一句 <安全>'},{role:'assistant',text:'# 章節\n**重點**\n| 項目 | 內容 |\n|---|---|\n| A | B |'}];
test('HTML escapes scripts and preserves structural content',()=>{
 const html=htmlDocument('標題',messages);
 assert.match(html,/&lt;安全&gt;/);
 assert.match(html,/<table>/);assert.match(html,/<strong>重點<\/strong>/);
 assert.doesNotMatch(html,/<安全>/);
});
test('copy chunks preserve every message exactly',()=>{
 const data=Array.from({length:30},(_,i)=>({role:'user',text:'item '+i+' 中文'}));
 const chunks=splitMessages(data,500);
 assert.deepEqual(chunks.flatMap(c=>c.messages),data);
 assert.deepEqual(chunks.map(c=>c.start),chunks.reduce((a,c,i)=>(a.push(i?a[i-1]+chunks[i-1].messages.length:0),a),[]));
 const rich=richClipboard(messages);assert.match(rich.html,/<table>/);assert.match(rich.text,/第一句/);
});
test('HTML volumes and filenames remain complete',()=>{
 const chunks=splitHtmlVolumes(messages,30);assert.deepEqual(chunks.flatMap(c=>c.messages),messages);
 assert.equal(safeHtmlName('X:/非法*名稱'),'X__非法_名稱');
});
test('ZIP archive includes verifiable entries and CRC',async()=>{
 const files=[{name:'一.html',content:htmlDocument('一',[messages[0]])},{name:'二.html',content:htmlDocument('二',[messages[1]])}];
 const bytes=new Uint8Array(await zipFiles(files).arrayBuffer());
 const view=new DataView(bytes.buffer);assert.equal(view.getUint32(0,true),0x04034b50);
 assert.equal(view.getUint32(bytes.length-22,true),0x06054b50);
 assert.equal(view.getUint16(bytes.length-12,true),2);
});

test('long conversation preserves chronological first and final message across HTML volumes',()=>{
 const messages=Array.from({length:1800},(_,i)=>({role:i%2?'assistant':'user',text:'長對話 第'+i+'則；'.repeat(120)}));
 const volumes=splitHtmlVolumes(messages,40000);
 const flattened=volumes.flatMap(x=>x.messages);
 assert.equal(flattened.length,messages.length);
 assert.equal(flattened[0].text,messages[0].text);
 assert.equal(flattened.at(-1).text,messages.at(-1).text);
 assert.deepEqual(flattened,messages);
 for(const volume of volumes){
   const rendered=htmlDocument('長篇測試',volume.messages,volume.start,messages.length);
   assert.equal((rendered.match(/class="message"/g)||[]).length,volume.messages.length);
 }
});
test('large copy batches maintain exact message boundaries',()=>{
 const messages=Array.from({length:1500},(_,i)=>({role:i%2?'assistant':'user',text:'內容 '+i+'。'.repeat(200)}));
 const batches=splitMessages(messages,25000);
 assert.ok(batches.length>1);
 assert.deepEqual(batches.flatMap(c=>c.messages),messages);
 assert.equal(batches.at(-1).start+batches.at(-1).messages.length,messages.length);
});
