import test from 'node:test';
import assert from 'node:assert/strict';
import {seriesNumber,filterRows,report,isoDate} from '../docs/local-backup/filters.mjs';
const row=(title,i=0)=>({title,key:String(i),nodes:4,create_time:1761609600,update_time:1761609600,label:'conversations-000.json'});
test('exact numbered series in Arabic and Chinese numerals',()=>{
 assert.equal(seriesNumber('文明戰線101(全面優化)','文明戰線'),101);
 assert.equal(seriesNumber('文明戰線（一）','文明戰線'),1);
 assert.equal(seriesNumber('文明戰線 100（全面優化）','文明戰線'),100);
 assert.equal(seriesNumber('高中導師遊戲9','高中導師遊戲'),9);
 assert.equal(seriesNumber('高中導師遊戲十','高中導師遊戲'),10);
 assert.equal(seriesNumber('文明戰線1012','文明戰線'),1012);
 assert.equal(seriesNumber('文明戰線外傳 1','文明戰線'),null);
 assert.equal(seriesNumber('文明戰線01xyz','文明戰線'),null);
 assert.equal(seriesNumber('某文明戰線1','文明戰線'),null);
});
test('search, date and range combine as intersection',()=>{
 const rows=[row('文明戰線1',1),row('文明戰線2',2),row('文明戰線10',10),row('高中導師遊戲1',20)];
 assert.deepEqual(filterRows(rows,{series:'文明戰線',first:'1',last:'2'}).map(r=>r.key),['1','2']);
 assert.equal(filterRows(rows,{query:'高中',from:'2025-10-28',to:'2025-10-28'}).length,1);
 assert.equal(filterRows(rows,{from:'2025-10-29'}).length,0);
 assert.equal(filterRows(rows,{from:'2025-10-28',to:'2025-10-28'}).length,4);
 assert.equal(isoDate(1761609600),'2025-10-28');
});
test('missing numbers and duplicates are reported, nodes are not visible messages',()=>{
 const rows=[row('高中導師遊戲1',1),row('高中導師遊戲3',2),row('高中導師遊戲3',3)];
 const r=report(rows,{series:'高中導師遊戲',first:'1',last:'4'});
 assert.deepEqual(r.missing,[2,4]);
 assert.deepEqual(r.duplicates,[{number:3,count:2}]);
 assert.equal(r.nodes,12);
 assert.equal(r.unknownMessages,true);
});
