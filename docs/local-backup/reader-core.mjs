/* Local-only active-path reader. No Render transfer or Word caps. */
export function parseConversation(source){
  if(!source || typeof source!=='object' || Array.isArray(source) || !source.mapping || typeof source.mapping!=='object' || Array.isArray(source.mapping))throw Error('不是可辨識的單段官方對話 JSON');
  const mapping=source.mapping, keys=Object.keys(mapping);
  if(!keys.length)throw Error('對話沒有 mapping 節點');
  if(typeof source.current_node!=='string' || !Object.hasOwn(mapping,source.current_node))throw Error('無法確認目前對話主線');
  const path=[], visited=new Set();let cursor=source.current_node;
  while(cursor!==null){
    if(typeof cursor!=='string'||!Object.hasOwn(mapping,cursor)||visited.has(cursor))throw Error('主線包含缺失節點或循環，無法安全還原');
    visited.add(cursor);const node=mapping[cursor];
    if(!node||typeof node!=='object'||Array.isArray(node))throw Error('主線節點結構損壞');
    path.push({key:cursor,node});cursor=node.parent;
  }
  path.reverse();
  const messages=[],warnings=[];let hidden=0,nonText=0;
  for(const {key,node} of path){
    const m=node.message;if(!m)continue;
    const role=m.author?.role||'unknown',channel=m.channel||m.metadata?.channel;
    if(role==='system'||role==='developer'||role==='tool'||m.metadata?.is_visually_hidden_from_conversation===true||['analysis','justify','confidence'].includes(channel)||['thoughts','reasoning_recap','model_editable_context','reasoning_recap_summary','analysis'].includes(m.content?.content_type)||(role==='assistant'&&m.recipient&&m.recipient!=='all')){hidden++;continue;}
    const parts=[],content=m.content;
    if(typeof content==='string')parts.push(content);
    else if(content&&typeof content==='object'){
      if(typeof content.text==='string')parts.push(content.text);
      if(Array.isArray(content.parts))for(const part of content.parts){
        if(typeof part==='string')parts.push(part);
        else if(part&&typeof part==='object'){
          if(typeof part.text==='string')parts.push(part.text);
          else if(typeof part.content==='string')parts.push(part.content);
          else {nonText++;parts.push('〔無法完整還原的非文字內容〕');warnings.push('訊息 '+key+' 包含無法還原的非文字內容');}
        }else {nonText++;parts.push('〔無法辨識的訊息內容〕');warnings.push('訊息 '+key+' 包含無法辨識的內容');}
      }
      if(!parts.length && content.content_type && !['text','code'].includes(content.content_type)){
        nonText++;parts.push('〔'+String(content.content_type).slice(0,80)+'：非文字或尚未支援的內容〕');warnings.push('訊息 '+key+' 的內容類型尚未完整支援');
      }
    }else if(content!=null){nonText++;parts.push('〔尚未支援的訊息結構〕');warnings.push('訊息 '+key+' 的結構尚未支援');}
    const text=parts.join('\n');
    if(!text.trim())continue;
    messages.push({id:key,role:role==='user'?'user':role==='assistant'?'assistant':'other',text});
  }
  return {title:typeof source.title==='string'?source.title:'未命名對話',messages,summary:{rawNodes:keys.length,pathNodes:path.length,offBranch:keys.length-path.length,hidden,nonText,warnings}};
}
export function wordLikeCount(text){
  const words=text.match(/[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:['’._-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*/gu)||[];
  const asian=text.match(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/gu)||[];
  return words.length+asian.length;
}
export function totalWords(messages){return messages.reduce((sum,m)=>sum+wordLikeCount(m.text),0);}
export function findMessages(messages,query){
  const needle=query.trim().toLocaleLowerCase();if(!needle)return [];
  const hits=[];
  messages.forEach((m,i)=>{const pos=m.text.toLocaleLowerCase().indexOf(needle);if(pos>=0)hits.push({index:i,excerpt:m.text.slice(Math.max(0,pos-45),Math.min(m.text.length,pos+needle.length+75))});});
  return hits;
}
