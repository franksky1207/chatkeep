import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateRawSync} from 'node:zlib';
import {JsonIndex,indexBlob,INDEX_BUDGET} from '../docs/local-backup/json-index.mjs';
import {zipEntries,expandEntry,crc32} from '../docs/local-backup/zip.mjs';
const enc=new TextEncoder();
const conv=(id='甲')=>({title:'重複標題 English 繁體中文 😀 " \\ \n',id,create_time:123,update_time:456,
 mapping:{root:{message:null,parent:null,children:['visible','hidden']},visible:{parent:'root',children:[],message:{author:{role:'assistant'},content:{content_type:'text',parts:['{[,]},\\"😀\n中文']}}},hidden:{parent:'root',children:[],message:{author:{role:'tool'},metadata:{is_visually_hidden_from_conversation:true},content:{content_type:'unknown',new_field:[null,true,3.2e-4]}}}},current_node:'visible',unknown:{anything:['保留',false]}});
const parse=(s,step=7)=>{const p=new JsonIndex(),bytes=typeof s==='string'?enc.encode(s):s;for(let i=0;i<bytes.length;i+=step)p.push(bytes.subarray(i,i+step));return p.finish();};
function zip(entries,{method=8,flags=0}={}){
 let offset=0;const locals=[],central=[];
 for(const [name,body] of entries){const bytes=enc.encode(body),n=enc.encode(name),data=method===8?deflateRawSync(bytes):bytes,crc=(crc32(bytes)^0xffffffff)>>>0;
 const h=Buffer.alloc(30);h.writeUInt32LE(0x04034b50);h.writeUInt16LE(flags,6);h.writeUInt16LE(method,8);h.writeUInt32LE(crc,14);h.writeUInt32LE(data.length,18);h.writeUInt32LE(bytes.length,22);h.writeUInt16LE(n.length,26);
 const c=Buffer.alloc(46);c.writeUInt32LE(0x02014b50);c.writeUInt16LE(flags,8);c.writeUInt16LE(method,10);c.writeUInt32LE(crc,16);c.writeUInt32LE(data.length,20);c.writeUInt32LE(bytes.length,24);c.writeUInt16LE(n.length,28);c.writeUInt32LE(offset,42);
 const descriptor=Buffer.alloc(flags&8?16:0);if(flags&8){descriptor.writeUInt32LE(0x08074b50);descriptor.writeUInt32LE(crc,4);descriptor.writeUInt32LE(data.length,8);descriptor.writeUInt32LE(bytes.length,12);}
 locals.push(h,n,data,descriptor);central.push(c,n);offset+=h.length+n.length+data.length+descriptor.length;
 }
 const cd=Buffer.concat(central),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(cd.length,12);end.writeUInt32LE(offset,16);
 return new Blob([...locals,cd,end]);
}
function handle(){let chunks=[];return {createSyncAccessHandle:async()=>({truncate:()=>{chunks=[];},write:b=>{chunks.push(b.slice());return b.length;},flush:()=>{},close:()=>{}}),getFile:async()=>new Blob(chunks)};}
test('official array and wrapper: exact UTF-8 ranges at every small chunk boundary',()=>{
 const a=conv(),b=conv('乙');
 for(const source of [JSON.stringify([a,b],null,2),JSON.stringify({unknown:'ignored',conversations:[a,b],tail:{new:true}})]){
 for(let step=1;step<=41;step++){const bytes=enc.encode(source),rows=parse(bytes,step);assert.equal(rows.length,2);for(let i=0;i<2;i++){assert.deepEqual(JSON.parse(new TextDecoder().decode(bytes.slice(rows[i].start,rows[i].end))),[a,b][i]);assert.equal(rows[i].nodes,3);assert.equal(rows[i].originalId,['甲','乙'][i]);}}
 }
});
test('deep unknown mapping, branches and hidden/tool nodes survive unchanged',()=>{
 const c=conv();let deep={x:'底部'};for(let i=0;i<600;i++)deep={a:[deep]};c.mapping.hidden.deep=deep;
 const source=JSON.stringify([c]);const [row]=parse(source);assert.deepEqual(JSON.parse(new TextDecoder().decode(enc.encode(source).slice(row.start,row.end))),c);
});
test('full grammar rejects malformed documents, trailing garbage and invalid schemas',()=>{
 for(const s of ['', ' ', '[', '[{}]', '[1]', '[{"mapping":[]}]','[{"mapping":{},"id":1}]', '[{"mapping":{},"title":true}]','[{"mapping":{},"title":"a","title":"b"}]', '[{"mapping":{}}]x','[{"mapping":{}},]','[{"mapping":{},}]','[{"mapping":{} "x":1}]','[{"mapping":{},"x":01}]','[{"mapping":{},"x":1.}]','[{"mapping":{},"x":tru}]','[{"mapping":{},"x":"\\x"}]','[{"mapping":{},"x":"\\uZZZZ"}]','[{"mapping":{},"x":"\n"}]','[{"mapping":{},"x":[1,]}]','{"conversations":[],"conversations":[]}','{"other":[]}', '[] []','[{"mapping":{},"x":{]}]'])assert.throws(()=>parse(s),s);
 for(const b of [new Uint8Array([91,0xff,93]),new Uint8Array([91,34,0xe4,34,93])])assert.throws(()=>parse(b));
});
test('empty array is valid; metadata/depth resource limits fail explicitly',()=>{
 assert.deepEqual(parse('[]'),[]);assert.throws(()=>parse(JSON.stringify([{mapping:{},title:'x'.repeat(65536)}])),/64 KiB/);
 assert.throws(()=>parse('[{"mapping":{},"x":'+ '['.repeat(2048)+'0'+']'.repeat(2048)+'}]'),/2,048/);
});
test('large results retain positional identity across duplicate titles and IDs',async()=>{
 const list=Array.from({length:3500},(_,i)=>({...conv(String(i%2)),marker:i}));
 const blob=new Blob([JSON.stringify(list)]),rows=await indexBlob(blob);assert.equal(rows.length,3500);
 for(const i of [0,299,300,1500,3499])assert.deepEqual(JSON.parse(await blob.slice(rows[i].start,rows[i].end).text()),list[i]);
});
test('ZIP stored/deflate multiple JSON, unrelated entries ignored; CRC verified',async()=>{
 for(const method of [0,8])for(const flags of [0,8]){
 const blob=zip([['export/conversations-000.json',JSON.stringify([conv()])],['conversations-001.json',JSON.stringify([conv('b')])],['media/unused.bin','ignore'],['other.json','[]']],{method,flags});
 const entries=await zipEntries(blob);assert.equal(entries.length,2);
 for(const e of entries){const expanded=await expandEntry(blob,e,handle());assert.equal((await indexBlob(expanded)).length,1);}
 }
});
test('ZIP malformed headers, truncation, CRC, ratio, methods, encryption and overlap',async()=>{
 await assert.rejects(zipEntries(new Blob([])));await assert.rejects(zipEntries(new Blob(['not zip'])));
 const good=zip([['conversations.json',JSON.stringify([conv()])]],{method:0});
 await assert.rejects(zipEntries(good.slice(0,good.size-1)));
 for(const flags of [1,16])await assert.rejects(zipEntries(zip([['conversations.json','[]']],{flags})),/旗標/);
 await assert.rejects(zipEntries(zip([['conversations.json','[]']],{method:99})),/壓縮方法/);
 await assert.rejects(zipEntries(zip([['conversations.json','x'.repeat(1000000)]])),/壓縮比例/);
 const bytes=new Uint8Array(await good.arrayBuffer());bytes[30+enc.encode('conversations.json').length]^=1;
 const broken=new Blob([bytes]);const [e]=await zipEntries(broken);await assert.rejects(expandEntry(broken,e,handle()),/CRC32/);
 const mismatch=new Uint8Array(await good.arrayBuffer());mismatch[14]^=1;await assert.rejects(zipEntries(new Blob([mismatch])),/不一致/);
 const two=new Uint8Array(await zip([['conversations-000.json','[]'],['conversations-001.json','[]']],{method:0}).arrayBuffer());
 const v=new DataView(two.buffer),end=two.length-22,cd=v.getUint32(end+16,true),second=cd+46+enc.encode('conversations-000.json').length;
 v.setUint32(second+42,0,true);await assert.rejects(zipEntries(new Blob([two])));
});
test('deterministic grammar differential checks against JSON.parse',()=>{
 let seed=617;const rand=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n;};
 const corpus=['null','false','true','0','-4.2e+3','"中文😀\\\"\\n{}[]"','[1,{"a":[null,true]},"\\u1234"]','{"nested":{"x":[1,2]},"empty":{}}'];
 const alphabet='{}[],:"\\0129truefalsenull. \n';
 for(let n=0;n<2500;n++){
  let body=corpus[rand(corpus.length)];if(n%3){const i=rand(body.length+1);body=body.slice(0,i)+alphabet[rand(alphabet.length)]+body.slice(i+(n%2));}
  const source='[{"mapping":{},"x":'+body+'}]';let valid=true;try{JSON.parse(source);}catch{valid=false;}
  if(valid)assert.equal(parse(source,1+rand(19)).length,1,source);else assert.throws(()=>parse(source,1+rand(19)),source);
 }
});

test('memory budget, runtime expansion limit and cancellation close the disk handle',async()=>{
 const p=new JsonIndex();p.indexBytes=INDEX_BUDGET;assert.throws(()=>p.push(enc.encode('[{"mapping":{}}]')),/64 MiB/);
 const blob=zip([['conversations.json',JSON.stringify([conv()])]]);const [e]=await zipEntries(blob);
 await assert.rejects(expandEntry(blob,{...e,size:2},handle()),/超出/);
 let closed=false;const disk={createSyncAccessHandle:async()=>({truncate(){},write:b=>b.length,flush(){},close(){closed=true;}})};
 await assert.rejects(expandEntry(blob,e,disk,()=>{throw new DOMException('cancel','AbortError');}),{name:'AbortError'});assert.equal(closed,true);
 const z64=new Uint8Array(await blob.arrayBuffer());new DataView(z64.buffer).setUint16(z64.length-12,65535,true);await assert.rejects(zipEntries(new Blob([z64])),/分卷|ZIP64/);
});
