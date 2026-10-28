/* Read-only presentation models. No parsing, transport or HTML interpolation. */
export const stateLabels={pending:'等待中',working:'處理中',done:'成功・下載就緒',failed:'失敗・可重試',released:'已釋放記憶體',skipped:'已略過',cancelled:'已取消'};
const sources={share_link:'公開分享連結',official_json:'官方備份',official_json_derived:'官方備份（分段轉換）'};
const categories={structural:'結構節點',system:'系統／開發者訊息',tool:'工具訊息',hidden:'隱藏訊息',internal:'內部訊息',tool_call:'工具呼叫',empty:'空白訊息'};
export const text=value=>String(value??'未提供').slice(0,2000);
export function reportView(job){
 const r=job.report;if(!r)return null;
 const derived=r.integrity_basis==='browser_derived_sequence';
 const counts=derived?r.client_source_counts||{}:r;
 const skipped=Object.entries(counts.skipped_categories||{}).filter(([,n])=>Number.isSafeInteger(n)&&n>0).map(([key,n])=>(categories[key]||text(key))+' '+n+' 項');
 const warnings=Array.isArray(r.warnings)?r.warnings.slice(0,512).map(w=>typeof w==='string'?text(w):text(w?.message||w?.code)):[];
 return {
  summary:[['來源模式',sources[r.source]||'未提供'],['匯出訊息',r.output_message_count],['Word 卷數',r.docx_volume_count],
   ['檔案類型',(job.artifact?.artifact_type||job.type||'').toUpperCase()],['轉換結果',r.status==='converted_with_warnings'?'成功，有警告':'成功'],
   ['輸出序列缺漏',r.missing===false?'未發現':r.missing===true?'發現缺漏':'未確認']],
  scope:derived?'已核對本機衍生有效訊息序列的全部批次；伺服器只驗證各批，未驗證原始完整官方 JSON。':'伺服器驗證正規化後的輸出訊息序列；本機另核對文件檔案、卷序與訊息書籤。',
  disclaimer:'兩種驗證都不代表已與 ChatGPT 官方網頁逐字比對。媒體、隱藏內容及略過項目不代表已完整輸出。SHA-256 用於檢查一致性，不是官方來源證明。',
  detail:[['原始 mapping 節點',counts.raw_node_count],['有效路徑訊息數',counts.active_path_message_count],
   ['非當前分支排除數',counts.off_branch_node_count],['略過分類',skipped.join('；')||'未回報略過項目'],
   ['完整性基準',r.integrity_basis],['來源驗證層級',derived?'本機來源聲明；伺服器僅驗證本批':'伺服器正規化輸出驗證，非官方來源認證'],
   ['批次數',job.partTotal??(derived?new Set((r.volumes||[]).map(v=>v.part_index)).size:1)],['序列 SHA-256',r.sequence_sha256]],
  volumes:(r.volumes||[]).slice(0,16).map(v=>({number:v.number,first:v.first_message,last:v.last_message,part:v.part_index,hash:v.file_sha256})),warnings
 };
}
export function queueView(jobs){
 const counts={};for(const job of jobs)counts[job.state]=(counts[job.state]||0)+1;
 return Object.entries(stateLabels).filter(([key])=>counts[key]).map(([key,label])=>label+' '+counts[key]+' 段').join(' · ');
}
export function stageText(stage){
 return String(stage||'等待開始').replace('對話準備：擷取單一已選對話','對話擷取：從本機取得已選對話')
  .replace('對話準備：驗證目前分支','本機準備：確認分支與可匯出訊息')
  .replace('節流等待 Retry-After','服務忙碌或請求較多，依服務指定時間等待後重試')
  .replace(/上傳批次 (\d+) \/ (\d+)；Render 正在轉換(?:（無內部百分比）)?/,'正在處理第 $1 / $2 批：傳送資料並等待 Render 轉換')
  .replace('分卷驗證','完整性驗證').replace('下載準備完成','下載就緒，請先查看報告');
}
