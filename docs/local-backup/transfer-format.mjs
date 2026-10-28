/* Versioned derived material, never a replacement for original Blob.slice JSON. */
export const SCHEMA='chatkeep.transfer.v1', CHUNK_SCHEMA='chatkeep.chunk.v1';
export const MAX_RAW=16_000_000, MAX_REQUEST=2_000_000, MAX_PARTS=16, MAX_MESSAGES=5000, MAX_TEXT=5_000_000;
export const CATEGORIES=['structural','system','tool','hidden','internal','tool_call','empty'];
export const encoder=new TextEncoder();
export function fail(code,message='選取對話或衍生批次無法安全驗證。'){const e=Error(message);e.code=code;throw e;}
export function check(signal){if(signal?.aborted)throw new DOMException('已取消','AbortError');}
export function canonical(value){
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 return JSON.stringify(value);
}
export async function bytesSha(bytes){if(!globalThis.crypto?.subtle)fail('UNSUPPORTED_CRYPTO');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');}
export const sha=value=>bytesSha(encoder.encode(canonical(value)));
export const partSha=messages=>sha(messages.map(m=>[m.id,m.role,m.text]));
export function xmlString(text){for(const c of text){const n=c.codePointAt(0);if(!(n===9||n===10||n===13||n>=32&&n<=0xd7ff||n>=0xe000&&n<=0xfffd||n>=0x10000&&n<=0x10ffff))fail('INVALID_CHARACTERS');}}
export const hasText=text=>/[^\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(text);
export const charCount=text=>{let n=0;for(const c of text)n++;return n;};
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const id=value=>typeof value==='string'&&charCount(value)>0&&charCount(value)<=256;

export function parseSelected(text){
 // Duplicate/depth validation before materializing the bounded selected object.
 // JSON.parse remains responsible for full JSON grammar, not regex extraction.
 const stack=[];let tokens=0;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(c==='"'){
   const start=i;for(i++;i<text.length;i++){if(text[i]==='\\')i++;else if(text[i]==='"')break;}
   if(i>=text.length)fail('INVALID_JSON');
   let next=i+1;while(next<text.length&&/\s/.test(text[next]))next++;
   if(text[next]===':'&&stack.at(-1)?.type==='{'){
    let key;try{key=JSON.parse(text.slice(start,i+1));}catch{fail('INVALID_JSON');}
    const keys=stack.at(-1).keys;if(keys.has(key))fail('INVALID_JSON','JSON 含重複欄位。');keys.add(key);
   }
   tokens++;
  }else if(c==='{'||c==='['){stack.push({type:c,keys:new Set()});if(stack.length>32)fail('STRUCTURE_LIMIT');tokens++;}
  else if(c==='}'||c===']'){const f=stack.pop();if(!f||f.type!==(c==='}'?'{':'['))fail('INVALID_JSON');}
  else if(c===','||c===':')tokens++;
  if(tokens>600000)fail('STRUCTURE_LIMIT');
 }
 let value;try{value=JSON.parse(text);}catch{fail('INVALID_JSON');}
 const todo=[value];let items=0;
 while(todo.length){const v=todo.pop();if(++items>300000)fail('STRUCTURE_LIMIT');
  if(typeof v==='string')xmlString(v);else if(typeof v==='number'&&!Number.isFinite(v))fail('INVALID_JSON');
  else if(Array.isArray(v))for(const item of v)todo.push(item);else if(object(v)){for(const [k,x]of Object.entries(v)){xmlString(k);todo.push(x);items++;}}
 }
 return {value,items};
}

export function normalizeSelected(conv,signal){
 check(signal);
 if(!object(conv)||'conversations'in conv||'linear_conversation'in conv||!object(conv.mapping))fail('SINGLE_CONVERSATION_REQUIRED');
 if(typeof conv.title!=='string'||charCount(conv.title)>1000)fail('INVALID_CONVERSATION');
 for(const key of ['id','conversation_id'])if(conv[key]!=null&&!id(conv[key]))fail('INVALID_CONVERSATION');
 const mapping=conv.mapping,keys=Object.keys(mapping),has=k=>Object.hasOwn(mapping,k);
 if(!keys.length||keys.length>5000)fail('NODE_LIMIT');
 if(typeof conv.current_node!=='string'||!has(conv.current_node))fail('INVALID_BRANCH');
 for(const key of keys){
  const n=mapping[key];if(!id(key)||!object(n)||n.id!==undefined&&n.id!==key||!Object.hasOwn(n,'parent'))fail('INVALID_BRANCH');
  if(n.parent!==null&&(typeof n.parent!=='string'||!has(n.parent)))fail('INVALID_BRANCH');
  if(n.children!==undefined){if(!Array.isArray(n.children)||new Set(n.children).size!==n.children.length)fail('INVALID_BRANCH');
   for(const child of n.children)if(typeof child!=='string'||!has(child)||!object(mapping[child])||mapping[child].parent!==key)fail('INVALID_BRANCH');}
  if(n.parent!==null&&object(mapping[n.parent])&&mapping[n.parent].children!==undefined&&(!Array.isArray(mapping[n.parent].children)||!mapping[n.parent].children.includes(key)))fail('INVALID_BRANCH');
 }
 const done=new Set();
 for(let key of keys){const trail=new Set();while(key!==null&&!done.has(key)){if(trail.has(key))fail('INVALID_BRANCH');trail.add(key);key=mapping[key].parent;}for(const k of trail)done.add(k);}
 const path=[];for(let key=conv.current_node;key!==null;key=mapping[key].parent)path.push(key);path.reverse();
 const skipped=Object.fromEntries(CATEGORIES.map(k=>[k,0])),seen=new Set(),messages=[];let active=0,totalChars=0;
 for(const key of path){
  check(signal);const m=mapping[key].message;if(m==null){skipped.structural++;continue;}active++;
  if(!object(m)||!object(m.author)||!['user','assistant','system','developer','tool'].includes(m.author.role))fail('UNSUPPORTED_CONTENT');
  const mid=m.id===undefined?key:m.id;if(!id(mid)||seen.has(mid))fail('DUPLICATE_MESSAGE');seen.add(mid);
  const meta=m.metadata??{};if(!object(meta)||'is_visually_hidden_from_conversation'in meta&&typeof meta.is_visually_hidden_from_conversation!=='boolean')fail('INVALID_CONVERSATION');
  for(const field of ['channel','recipient','status'])if(m[field]!=null&&typeof m[field]!=='string')fail('INVALID_CONVERSATION');
  const content=m.content;if(typeof content!=='string'&&!object(content))fail('INVALID_CONVERSATION');
  const ct=object(content)?content.content_type===undefined?'text':content.content_type:'text';if(typeof ct!=='string')fail('INVALID_CONVERSATION');
  let category=null;
  if(['system','developer'].includes(m.author.role))category='system';else if(m.author.role==='tool')category='tool';
  else if(meta.is_visually_hidden_from_conversation===true)category='hidden';
  else if(['reasoning_recap','thoughts','model_editable_context'].includes(ct)||['analysis','justify','confidence'].includes(m.channel))category='internal';
  else if(m.author.role==='assistant'&&m.recipient!=null&&m.recipient!=='all')category='tool_call';
  if(category){skipped[category]++;continue;}
  let text;
  if(typeof content==='string')text=content;
  else{
   if(!['text','code'].includes(ct)||Object.keys(content).some(k=>!['content_type','parts','text','language'].includes(k))||'text'in content&&'parts'in content)fail('UNSUPPORTED_CONTENT');
   if(typeof content.text==='string')text=content.text;
   else if(Array.isArray(content.parts))text=content.parts.map(p=>{
    if(typeof p==='string')return p;
    if(object(p)&&typeof p.text==='string'&&(p.type===undefined?'text':p.type)==='text'&&Object.keys(p).every(k=>['type','text'].includes(k)))return p.text;
    fail('UNSUPPORTED_CONTENT');
   }).join('\n');else fail('UNSUPPORTED_CONTENT');
  }
  if(!hasText(text)){skipped.empty++;continue;}
  if((m.status===undefined?'finished_successfully':m.status)!=='finished_successfully')fail('UNFINISHED_MESSAGE');
  const n=charCount(text);if(n>1_000_000)fail('MESSAGE_TOO_LARGE');totalChars+=n;
  if(totalChars>MAX_TEXT||messages.length>=MAX_MESSAGES)fail('TRANSFER_LIMIT');
  messages.push({id:mid,role:m.author.role,text});
 }
 if(!messages.length)fail('NO_EXPORTABLE_MESSAGES');
 return {title:conv.title,source_id:conv.id??conv.conversation_id??null,messages,total_text_chars:totalChars,
  source_counts:{raw_node_count:keys.length,active_path_node_count:path.length,active_path_message_count:active,
   output_message_count:messages.length,off_branch_node_count:keys.length-path.length,skipped_categories:skipped}};
}

export async function prepareSelected(blob,{signal,nonce}={}){
 check(signal);if(!(blob instanceof Blob)||!blob.size||blob.size>MAX_RAW)fail('SELECTED_SOURCE_LIMIT','已選單一對話須不超過 16 MB；不接受整包備份。');
 let text;try{text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await blob.arrayBuffer());}catch{fail('INVALID_JSON');}
 check(signal);const {value,items}=parseSelected(text);const normalized=normalizeSelected(value,signal);
 if(blob.size<=MAX_REQUEST&&items<=100000)return {mode:'official',path:'/api/convert-json',blob,source_validation:'browser_checked_not_server_verified'};
 if(!nonce){if(!globalThis.crypto?.subtle)fail('UNSUPPORTED_CRYPTO');const bytes=crypto.getRandomValues(new Uint8Array(16));nonce=[...bytes].map(v=>v.toString(16).padStart(2,'0')).join('');}
 if(!/^[a-f0-9]{32}$/.test(nonce))fail('INVALID_NONCE');
 const groups=[];let group=[],size=0;
 for(const m of normalized.messages){const bytes=encoder.encode(JSON.stringify(m)).length+1;
  if(bytes+16384>MAX_REQUEST)fail('CHUNK_TOO_LARGE','單則訊息無法放入 2 MB 封包，未切割訊息。');
  if(group.length&&(size+bytes>1_750_000||group.length>=500)){groups.push(group);group=[];size=0;}
  group.push(m);size+=bytes;
 }if(group.length)groups.push(group);
 if(groups.length>MAX_PARTS)fail('PART_LIMIT');
 const parts=[];let first=1;
 for(let i=0;i<groups.length;i++){check(signal);const messages=groups[i];parts.push({part_index:i+1,first_message:first,last_message:first+messages.length-1,message_count:messages.length,sequence_sha256:await partSha(messages)});first+=messages.length;}
 const manifest={schema_version:SCHEMA,source:'official_json_derived',nonce,source_id:normalized.source_id,title:normalized.title,
  sequence_sha256:await sha(parts),parts,total_message_count:normalized.messages.length,total_text_chars:normalized.total_text_chars,source_counts:normalized.source_counts};
 manifest.conversation_key=await sha(manifest);
 const chunks=groups.map((messages,i)=>({schema_version:CHUNK_SCHEMA,manifest,part_index:i+1,messages}));
 for(const chunk of chunks)if(encoder.encode(JSON.stringify(chunk)).length>MAX_REQUEST)fail('CHUNK_TOO_LARGE');
 check(signal);return {mode:'chunks',path:'/api/convert-chunk-v1',manifest,chunks,source_validation:'browser_derived_not_server_verified'};
}
