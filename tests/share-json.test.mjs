import test from 'node:test';
import assert from 'node:assert/strict';
import {shareBackup} from '../docs/local-backup/share-json.mjs';
import {parseConversation} from '../docs/local-backup/reader-core.mjs';
import {indexBlob} from '../docs/local-backup/json-index.mjs';
test('986 published messages round trip through existing backup reader and index',async()=>{
 const messages=Array.from({length:986},(_,i)=>({role:i%2?'assistant':'user',text:'訊息 '+i+'\n**測試**'}));
 const b=shareBackup({title:'長對話',messages},'https://chatgpt.com/share/abc');
 const rows=await indexBlob(new Blob([JSON.stringify(b)]));
 assert.equal(rows.length,1);assert.equal(rows[0].nodes,987);
 assert.deepEqual(parseConversation(b[0]).messages.map(({role,text})=>({role,text})),messages);
});
test('reject incomplete and invalid messages',()=>{
 for(const messages of [[],[{role:'system',text:'x'}],[{role:'user',text:''}],[null]])assert.throws(()=>shareBackup({messages},'https://chatgpt.com/share/abc'));
});
