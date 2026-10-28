import test from 'node:test';
import assert from 'node:assert/strict';
import {reportView,queueView,stageText,stateLabels,text} from '../docs/local-backup/presentation.mjs';
import {safeFilename,explain} from '../docs/local-backup/conversion.mjs';
import {sendPrepared} from '../docs/local-backup/transfer-client.mjs';
import {DEFAULT_API_BASE} from '../docs/local-backup/site-config.mjs';
const report={source:'official_json',integrity_basis:'normalized_output_sequence',output_message_count:2,docx_volume_count:1,missing:false,status:'converted',warnings:[],raw_node_count:5,active_path_message_count:4,off_branch_node_count:1,skipped_categories:{tool:1,hidden:1},sequence_sha256:'a'.repeat(64),volumes:[{number:1,first_message:1,last_message:2,file_sha256:'b'.repeat(64)}]};
test('normal and derived reports preserve separate verification scopes and human summaries',()=>{
 const normal=reportView({report,type:'docx'});assert(normal.scope.includes('伺服器驗證正規化'));assert(normal.disclaimer.includes('不代表已與 ChatGPT 官方網頁逐字比對'));assert(normal.detail.some(([k,v])=>k==='略過分類'&&v.includes('工具訊息')));assert.equal(normal.summary.find(([k])=>k==='檔案類型')[1],'DOCX');
 const derived=reportView({report:{...report,source:'official_json_derived',integrity_basis:'browser_derived_sequence',client_source_counts:{raw_node_count:12,off_branch_node_count:3,skipped_categories:{internal:2}},volumes:[{part_index:1},{part_index:2}]},type:'zip',partTotal:2});
 assert(derived.scope.includes('未驗證原始完整官方 JSON'));assert.equal(derived.detail.find(([k])=>k==='原始 mapping 節點')[1],12);assert.equal(derived.detail.find(([k])=>k==='批次數')[1],2);
 assert.equal(reportView({}),null);
});
test('missing counts and unsupported warnings never become a full media claim',()=>{
 const view=reportView({report:{...report,raw_node_count:null,warnings:[{code:'UNSUPPORTED',message:'合成警告 <script>'}],status:'converted_with_warnings'},type:'zip'});
 assert.equal(text(view.detail[0][1]),'未提供');assert.equal(view.warnings[0],'合成警告 <script>');assert(view.summary.some(([,v])=>v==='成功，有警告'));assert(view.disclaimer.includes('隱藏內容'));
 assert.equal(text('x'.repeat(5000)).length,2000);
});
test('all queue states have visible text; stage labels use real batch counts without fabricated percentage',()=>{
 const jobs=Object.keys(stateLabels).map(state=>({state}));const summary=queueView(jobs);for(const label of Object.values(stateLabels))assert(summary.includes(label));
 assert.equal(stageText('上傳批次 2 / 4；Render 正在轉換'),'正在處理第 2 / 4 批：傳送資料並等待 Render 轉換');assert(!stageText('分卷驗證').includes('%'));
});
test('retry status observers leave sequential pacing and retry admission intact',async()=>{
 const events=[],waits=[];let calls=0;const collector={accept:async()=>{}};
 await sendPrepared({mode:'chunks',chunks:[{part_index:1}]},{collector,wait:async n=>waits.push(n),onProgress:e=>events.push(e),send:async()=>++calls===1?{status:429,retryAfter:'60'}:{status:200,value:{}}});
 assert.equal(calls,2);assert(waits.includes(60000));assert(events.some(e=>e.phase==='retry'&&e.index===1&&e.seconds===60));
});
test('release defaults stay disabled; error copy is readable and filenames reject control/bidi/reserved names',()=>{
 assert.equal(DEFAULT_API_BASE,'');assert(explain('NETWORK_OR_CORS').includes('來源白名單'));assert(explain('API_UNAVAILABLE').includes('尚未部署'));assert(!explain('API_NOT_CONFIGURED').includes('/api/'));
 assert.equal(safeFilename('CON','json'),'_CON.json');assert(!safeFilename('a\u202eb/😀','docx').includes('\u202e'));assert(safeFilename('../x','zip').endsWith('.zip'));
});
