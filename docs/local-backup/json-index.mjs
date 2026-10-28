/* Incremental JSON grammar over UTF-8 bytes. No conversation mapping is materialized. */
export const CHUNK = 256 * 1024;
export const INDEX_BUDGET = 64 * 1024 * 1024;
export const indexCost = row => 256 + 2 * (row.title.length + (row.originalId?.length || 0));
const WS = new Set([9, 10, 13, 32]);
const META = new Set(['title', 'id', 'conversation_id', 'create_time', 'update_time']);
export class JsonIndex {
  constructor() {
    this.offset = 0; this.stack = []; this.root = 'value'; this.mode = ''; this.raw = [];
    this.escape = false; this.unicode = 0; this.capture = false; this.results = [];
    this.decoder = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true});
    this.indexBytes = 0; this.array = null; this.conversation = null; this.wrapper = false;
  }
  fail(message) { throw Error(`JSON 位元組 ${this.offset}：${message}`); }
  expected() { return this.stack.at(-1)?.state || this.root; }
  consume() {
    const parent = this.stack.at(-1);
    if (!parent) { if (this.root !== 'value') this.fail('根資料後有多餘內容'); this.root = 'done'; return; }
    if (!['value', 'first', 'next'].includes(parent.state)) this.fail('此處不應有值');
    if (parent === this.array && this.opening !== '{') this.fail('對話陣列的每一項必須是物件');
    parent.state = 'comma';
  }
  wantsString() {
    const top = this.stack.at(-1);
    if (['key', 'keyFirst'].includes(this.expected())) return this.stack.length === 1 || top === this.conversation?.frame;
    return top && top === this.conversation?.frame && META.has(top.key);
  }
  token(type, value, start) {
    const top = this.stack.at(-1);
    if (type === 'string' && ['key', 'keyFirst'].includes(this.expected())) {
      if (top === this.conversation?.frame && (META.has(value) || value === 'mapping')) {
        if (this.conversation.keys.has(value)) this.fail('對話索引欄位重複');
        this.conversation.keys.add(value);
      }
      top.key = value; top.state = 'colon'; return;
    }
    if (type === ':') { if (this.expected() !== 'colon') this.fail('預期物件鍵後的冒號'); top.state = 'value'; return; }
    if (type === ',') {
      if (this.expected() !== 'comma') this.fail('逗號位置不正確');
      top.state = top.type === '{' ? 'key' : 'next'; return;
    }
    if (type === '}' || type === ']') {
      if (!top || top.type !== (type === '}' ? '{' : '[')) this.fail('括號不相符');
      if (!(top.state === 'comma' || top.state === (type === '}' ? 'keyFirst' : 'first'))) this.fail('結尾不完整或有多餘逗號');
      if (top && top === this.conversation?.frame) {
        const c = this.conversation;
        if (!c.mapping) this.fail('對話缺少物件型態的 mapping，無法辨識官方格式');
        this.results.push({start: c.start, end: this.offset + 1, title: c.title || '未命名對話',
          originalId: c.id ?? c.conversation_id ?? null, create_time: c.create_time ?? null,
          update_time: c.update_time ?? null, nodes: c.nodes});
        this.indexBytes += indexCost(this.results.at(-1));
        if (this.indexBytes > INDEX_BUDGET) this.fail('索引資料超過 64 MiB 預算，請分批選檔');
        if (this.results.length > 200000) this.fail('索引超過 200,000 段，請分批選檔');
        this.conversation = null;
      }
      this.stack.pop(); return;
    }
    const isArray = type === '['; const isObject = type === '{';
    if (this.stack.length === 0 && !(isArray || isObject)) this.fail('需要官方對話陣列');
    if (!this.stack.length && isObject) this.wrapper = true;
    const isConversations = isArray && (!this.stack.length || (this.wrapper && this.stack.length === 1 && top.key === 'conversations'));
    if (this.wrapper && this.stack.length === 1 && top.key === 'conversations' && !isArray) this.fail('conversations 必須是陣列');
    if (isConversations && this.array) this.fail('重複的 conversations 陣列');
    const newConversation = top && top === this.array;
    if (top && top === this.conversation?.frame && META.has(top.key)) {
      if (isArray || isObject || !['string', 'number', 'null'].includes(type)) this.fail('對話索引欄位型態不支援');
      if (['title', 'id', 'conversation_id'].includes(top.key) && !['string', 'null'].includes(type)) this.fail('標題／ID 應為字串');
      if (['create_time', 'update_time'].includes(top.key) && !['number', 'null'].includes(type)) this.fail('時間應為數字');
      this.conversation[top.key] = value;
    }
    if (top && top === this.conversation?.frame && top.key === 'mapping') {
      if (!isObject) this.fail('mapping 必須是物件');
      this.conversation.mapping = true;
    }
    if (top && top === this.conversation?.mappingFrame) this.conversation.nodes++;
    this.opening = type; this.consume();
    if (isArray || isObject) {
      if (this.stack.length >= 2048) this.fail('巢狀深度超過 2,048，請使用桌面工具處理');
      const frame = {type, state: isObject ? 'keyFirst' : 'first', key: null};
      if (newConversation) this.conversation = {frame, start, nodes: 0, mapping: false, keys: new Set()};
      else if (top && top === this.conversation?.frame && top.key === 'mapping') this.conversation.mappingFrame = frame;
      if (isConversations) this.array = frame;
      this.stack.push(frame);
    }
  }
  byte(b) {
    if (this.mode === 'string') {
      if (this.capture) { this.raw.push(b); if (this.raw.length > 65536) this.fail('索引欄位超過 64 KiB，請使用桌面工具處理'); }
      if (this.unicode) { if (!/[0-9a-fA-F]/.test(String.fromCharCode(b))) this.fail('Unicode 跳脫無效'); this.unicode--; }
      else if (this.escape) { this.escape = false; if (b === 117) this.unicode = 4; else if (![34,92,47,98,102,110,114,116].includes(b)) this.fail('字串跳脫無效'); }
      else if (b === 92) this.escape = true;
      else if (b === 34) {
        const value = this.capture ? JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(new Uint8Array(this.raw))) : null;
        this.mode = ''; this.raw = []; this.token('string', value, this.start);
      } else if (b < 32) this.fail('字串含未跳脫控制字元');
      return;
    }
    if (this.mode === 'atom') {
      if (!WS.has(b) && ![44,93,125].includes(b)) { this.raw.push(b); if (this.raw.length > 1024) this.fail('數值／常值過長'); return; }
      this.endAtom();
    }
    if (WS.has(b)) return;
    if (b === 34) { this.mode = 'string'; this.start = this.offset; this.capture = this.wantsString(); this.raw = this.capture ? [34] : []; return; }
    if ([123,125,91,93,44,58].includes(b)) { this.token(String.fromCharCode(b), null, this.offset); return; }
    if (b === 45 || (b >= 48 && b <= 57) || [116,102,110].includes(b)) { this.mode = 'atom'; this.start = this.offset; this.raw = [b]; return; }
    this.fail('非預期字元');
  }
  endAtom() {
    const s = String.fromCharCode(...this.raw); let type, value;
    if (['true','false','null'].includes(s)) { type = s; value = s === 'null' ? null : s === 'true'; }
    else if (/^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/.test(s)) { type = 'number'; value = Number(s); }
    else this.fail('數值或常值無效');
    this.mode = ''; this.raw = []; this.token(type, value, this.start);
  }
  push(bytes) {
    // Fatal validation also covers UTF-8 split across chunks.
    try{this.decoder.decode(bytes, {stream: true});}catch{this.fail('無效的 UTF-8 編碼');}
    for (const b of bytes) { this.byte(b); this.offset++; }
  }
  finish() {
    try{this.decoder.decode();}catch{this.fail('UTF-8 字元被截斷');}
    if (this.mode === 'atom') this.endAtom();
    if (this.mode || this.stack.length || this.root !== 'done' || !this.array) this.fail('檔案為空、被截斷或沒有 conversations 陣列');
    return this.results;
  }
}
export async function indexBlob(blob, progress = () => {}) {
  const parser = new JsonIndex();
  for (let offset = 0; offset < blob.size; offset += CHUNK) {
    parser.push(new Uint8Array(await blob.slice(offset, offset + CHUNK).arrayBuffer()));
    progress(Math.min(offset + CHUNK, blob.size), parser.results.length);
  }
  return parser.finish();
}
