import test from 'node:test';
import assert from 'node:assert/strict';
import {parseConversation,wordLikeCount,findMessages} from '../docs/local-backup/reader-core.mjs';
const node=(id,parent,role,text,extra={})=>({id,parent,children:[],message:{author:{role},content:{content_type:'text',parts:[text]},...extra}});
test('active branch order and off-branch exclusion',()=>{
 const a=node('a',null,'user','校慶開始');
 const b=node('b','a','assistant','第一章\n重要專題');
 const side=node('side','a','assistant','不應出現');
 const result=parseConversation({title:'測試',current_node:'b',mapping:{a,b,side}});
 assert.deepEqual(result.messages.map(m=>m.text),['校慶開始','第一章\n重要專題']);
 assert.equal(result.summary.offBranch,1);
 assert.deepEqual(findMessages(result.messages,'專題').map(x=>x.index),[1]);
});
test('special content preserves placeholder and warns',()=>{
 const a={parent:null,message:{author:{role:'user'},content:{parts:[{asset_pointer:'x'},'保留文字']}}};
 const r=parseConversation({current_node:'a',mapping:{a}});
 assert.match(r.messages[0].text,/保留文字/);assert.equal(r.summary.nonText,1);
});
test('corrupt path rejects instead of silently truncating',()=>{
 assert.throws(()=>parseConversation({current_node:'a',mapping:{a:{parent:'missing',message:null}}}),/主線/);
});
test('Word-like Chinese and English count is approximate',()=>{assert.equal(wordLikeCount('高中 Hello world 2026'),5);});
