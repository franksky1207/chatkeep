// Rebuild a linear, importable backup from published reader messages only.
export function shareBackup(data,url){
 if(!data||!Array.isArray(data.messages)||!data.messages.length)throw Error('沒有可下載的對話正文');
 const mapping=Object.create(null),root='share-root';
 mapping[root]={id:root,parent:null,children:[],message:null};
 let parent=root;
 for(const [i,item] of data.messages.entries()){
  if(!item||!['user','assistant'].includes(item.role)||typeof item.text!=='string'||!item.text.trim())throw Error('服務回傳訊息格式不正確');
  const id='share-message-'+(i+1);
  mapping[parent].children.push(id);
  mapping[id]={id,parent,children:[],message:{id,author:{role:item.role},content:{content_type:'text',parts:[item.text]},metadata:{},recipient:'all'}};
  parent=id;
 }
 return [{title:typeof data.title==='string'&&data.title.trim()?data.title:'公開分享對話',id:url.split('/').at(-1),current_node:parent,mapping,chatkeep_source:'public_share_visible_messages'}];
}
