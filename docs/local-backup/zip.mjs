/* ZIP32 central-directory validation and bounded native streaming decompression.
 * No external code, CDN, upload, or archive-wide expansion in memory. */
import {CHUNK} from './json-index.mjs';
const MAX_ENTRY = 4 * 1024 ** 3 - 1;
const MAX_TOTAL = 8 * 1024 ** 3;
const MAX_RATIO = 200;
const table = new Uint32Array(256);
for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; table[n] = c >>> 0; }
export function crc32(bytes, crc = 0xffffffff) { for (const b of bytes) crc = table[(crc ^ b) & 255] ^ (crc >>> 8); return crc >>> 0; }
async function read(blob, offset, size) {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset + size > blob.size) throw Error('ZIP 範圍超出檔案，資料可能損壞');
  return new Uint8Array(await blob.slice(offset, offset + size).arrayBuffer());
}
const view = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
const equal = (a,b) => a.length === b.length && a.every((x,i) => x === b[i]);
function extras(bytes) {
  const v = view(bytes); let p = 0;
  while (p < bytes.length) {
    if (p + 4 > bytes.length) throw Error('ZIP 額外欄位損壞');
    const id = v.getUint16(p,true), n = v.getUint16(p+2,true); p += 4;
    if (p + n > bytes.length) throw Error('ZIP 額外欄位長度損壞');
    if (id === 1) throw Error('目前不支援 ZIP64，請在電腦解壓後選取 JSON');
    p += n;
  }
}
export async function zipEntries(blob, checkCancelled = () => {}) {
  const tail = await read(blob, Math.max(0, blob.size - 65557), Math.min(blob.size, 65557));
  const t = view(tail); let e = -1;
  for (let p = tail.length - 22; p >= 0; p--) {
    if (t.getUint32(p,true) === 0x06054b50 && p + 22 + t.getUint16(p+20,true) === tail.length) { e = p; break; }
  }
  if (e < 0) throw Error('ZIP 結尾目錄缺失或損壞');
  const disk = t.getUint16(e+4,true), cdDisk = t.getUint16(e+6,true), diskCount = t.getUint16(e+8,true), count = t.getUint16(e+10,true);
  const size = t.getUint32(e+12,true), offset = t.getUint32(e+16,true);
  if (disk || cdDisk || diskCount !== count) throw Error('不支援分卷 ZIP，請先在電腦解壓');
  if (count === 65535 || size === 0xffffffff || offset === 0xffffffff) throw Error('目前不支援 ZIP64，請先在電腦解壓');
  if (offset + size !== blob.size - tail.length + e) throw Error('ZIP 中央目錄範圍無效');
  let p = offset, total = 0, nameBudget = 0; const found = [], intervals = [], names = new Set();
  for (let i = 0; i < count; i++) {
    checkCancelled();
    const h = await read(blob, p, 46), v = view(h);
    if (v.getUint32(0,true) !== 0x02014b50) throw Error('ZIP 中央目錄損壞');
    const flags=v.getUint16(8,true), method=v.getUint16(10,true), crc=v.getUint32(16,true), compressed=v.getUint32(20,true), size=v.getUint32(24,true);
    const nl=v.getUint16(28,true), el=v.getUint16(30,true), cl=v.getUint16(32,true), local=v.getUint32(42,true);
    if (v.getUint16(34,true)) throw Error('不支援分卷 ZIP');
    if ([compressed,size,local].includes(0xffffffff)) throw Error('目前不支援 ZIP64，請先在電腦解壓');
    if (p + 46 + nl + el + cl > offset + (t.getUint32(e+12,true))) throw Error('ZIP 目錄項目超出邊界');
    const nameBytes = await read(blob,p+46,nl);
    // Conversation filenames are ASCII; decoding other export filenames never controls paths on disk.
    const name = new TextDecoder().decode(nameBytes);
    extras(await read(blob,p+46+nl,el));
    const lh = view(await read(blob,local,30));
    if (lh.getUint32(0,true)!==0x04034b50 || lh.getUint16(6,true)!==flags || lh.getUint16(8,true)!==method) throw Error('ZIP 本機標頭與目錄不一致');
    const lnl=lh.getUint16(26,true), lel=lh.getUint16(28,true), start=local+30+lnl+lel;
    if (!equal(nameBytes,await read(blob,local+30,lnl))) throw Error('ZIP 檔名不一致');
    extras(await read(blob,local+30+lnl,lel));
    if (!(flags & 8) && (lh.getUint32(14,true)!==crc || lh.getUint32(18,true)!==compressed || lh.getUint32(22,true)!==size)) throw Error('ZIP 檔案大小或 CRC 標頭不一致');
    if (start + compressed > offset) throw Error('ZIP 資料超出中央目錄邊界');
    let end=start+compressed;
    if (flags & 8) {
      const d=view(await read(blob,end,4)); const signed=d.getUint32(0,true)===0x08074b50;
      const descriptor=view(await read(blob,end+(signed?4:0),12));
      if (descriptor.getUint32(0,true)!==crc || descriptor.getUint32(4,true)!==compressed || descriptor.getUint32(8,true)!==size) throw Error('ZIP 資料描述符不一致');
      end+=signed?16:12;
    }
    if (end > offset) throw Error('ZIP 資料描述符超出邊界');
    intervals.push([local,end]);
    if (/(^|\/)conversations(?:-\d+)?\.json$/i.test(name)) {
      nameBudget+=nameBytes.length;
      if(nameBytes.length>4096 || nameBudget>4*1024*1024 || found.length>=10000) throw Error('ZIP 對話檔案名稱或數量超出安全索引預算，請先解壓並分批選檔');
      if (names.has(name)) throw Error('ZIP 含重複對話檔名，無法安全定位'); names.add(name);
      if (flags & ~0x80e) throw Error('不支援加密或特殊旗標的對話 ZIP，請先在電腦解壓');
      if (![0,8].includes(method)) throw Error('對話 ZIP 壓縮方法不支援（僅 stored／deflate）');
      if (method===0 && compressed!==size) throw Error('ZIP 未壓縮項目大小不一致');
      if (size>MAX_ENTRY || size/Math.max(1,compressed)>MAX_RATIO) throw Error('ZIP 對話項目超出安全大小或 200 倍壓縮比例，請先在電腦解壓');
      total+=size; if(total>MAX_TOTAL) throw Error('ZIP 對話資料超過 8 GiB，請分批選取解壓後的 JSON');
      found.push({name,flags,method,crc,compressed,size,start});
    }
    p+=46+nl+el+cl;
  }
  if(p!==offset+size) throw Error('ZIP 目錄長度不一致');
  intervals.sort((a,b)=>a[0]-b[0]);
  for(let i=1;i<intervals.length;i++) if(intervals[i][0]<intervals[i-1][1]) throw Error('ZIP 項目重疊');
  if(!found.length) throw Error('ZIP 內沒有 conversations.json 或 conversations-XXX.json');
  return found;
}
export async function expandEntry(blob, entry, fileHandle, progress = () => {}) {
  // Blob.stream() chunk sizes are implementation-defined. Bound compressed input too:
  // a native inflater must never receive the whole compressed member in one write.
  let inputOffset=entry.start;const inputEnd=entry.start+entry.compressed;
  let stream=new ReadableStream({
    async pull(controller){
      if(inputOffset===inputEnd){controller.close();return;}
      const end=Math.min(inputOffset+32768,inputEnd);
      controller.enqueue(new Uint8Array(await blob.slice(inputOffset,end).arrayBuffer()));inputOffset=end;
    }
  },{highWaterMark:0});
  if(entry.method===8) {
    try { stream=stream.pipeThrough(new DecompressionStream('deflate-raw')); }
    catch { throw Error('此瀏覽器不支援本機 deflate 解壓，請更新瀏覽器或先在電腦解壓 ZIP'); }
  }
  const reader=stream.getReader(); let writer, count=0, written=0, crc=0xffffffff;
  try {
    if(!fileHandle.createSyncAccessHandle) throw Error('此瀏覽器不支援 Worker 本機暫存寫入，請先在電腦解壓 ZIP 後選取 JSON');
    writer=await fileHandle.createSyncAccessHandle();writer.truncate(0);
    while(true) {
      const {done,value}=await reader.read(); if(done) break;
      count+=value.length;
      if(count>entry.size || count>MAX_ENTRY || count/Math.max(1,entry.compressed)>MAX_RATIO) throw Error('ZIP 解壓大小超出宣告或安全上限');
      crc=crc32(value,crc);
      // Limit each disk write even if a platform yields a large decompressed chunk.
      for(let p=0;p<value.length;) {
        const n=writer.write(value.subarray(p,Math.min(p+CHUNK,value.length)),{at:written});
        if(!n) throw Error('本機暫存寫入未完成，請確認儲存空間');
        p+=n;written+=n;
      }
      progress(count);
    }
    if(count!==entry.size || ((crc^0xffffffff)>>>0)!==entry.crc) throw Error('ZIP 解壓大小或 CRC32 驗證失敗，檔案可能損壞');
    writer.flush();writer.close(); writer=null;
    return await fileHandle.getFile();
  } catch(e) { await reader.cancel().catch(()=>{}); if(writer) {try{writer.close();}catch{ /* worker cleanup removes incomplete temp */ }} throw e; }
  finally { reader.releaseLock(); }
}
