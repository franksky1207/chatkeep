'use strict';
const $ = id => document.getElementById(id);
let downloadURL;
function clearDownload() {
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  downloadURL = null;
  $('download').hidden = true;
  $('download').removeAttribute('href');
}
function report(data) {
  $('result').hidden = false;
  $('summary').textContent = data.status === 'partial' ? '部分內容無法還原，請查看明細。' : '擷取完成；尚未完成逐訊息比對。';
  $('stats').replaceChildren();
  for (const [label, value] of [['原始節點', data.raw_nodes], ['訊息記錄', data.raw_messages], ['可匯出訊息', data.readable_messages], ['使用者（可匯出）', data.visible_roles.user || 0], ['ChatGPT（可匯出）', data.visible_roles.assistant || 0], ['目前分支以外節點', data.off_branch_nodes]]) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = value;
    $('stats').append(dt, dd);
  }
  $('warnings').replaceChildren();
  for (const warning of data.warnings) {
    const li = document.createElement('li'); li.textContent = warning; $('warnings').append(li);
  }
  $('details').replaceChildren();
  const labels = {structural: '結構節點', visible: '可見文字訊息', system: '系統記錄', tool: '工具記錄', hidden: '來源標記為隱藏', internal: '推理及內部記錄', tool_call: '工具呼叫', empty: '空白訊息', non_text: '含未還原的非文字內容', unknown: '無法辨識的訊息'};
  const list = document.createElement('dl');
  for (const [category, count] of Object.entries(data.categories)) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = labels[category] || category; dd.textContent = count; list.append(dt, dd);
  }
  $('details').append(list);
  const reasons = {missing_or_duplicate_id: '訊息識別碼缺失或重複', unfinished_message: '來源訊息尚未完成', unsupported_content: '含無法還原的內容'};
  for (const issue of data.issues) {
    const p = document.createElement('p');
    p.textContent = `第 ${issue.node_index + 1} 個來源節點：${reasons[issue.reason] || '需檢查內容'}。`;
    $('details').append(p);
  }
}
function event(data) {
  $('progress').textContent = data.message;
  for (const step of ['fetch', 'parse', 'word']) $('step-' + step).classList.toggle('active', step === data.stage || data.stage === 'done');
  if (data.report) report(data.report);
  if (data.stage === 'error') throw new Error(data.message);
  if (data.stage === 'done') {
    const bytes = Uint8Array.from(atob(data.document), c => c.charCodeAt(0));
    downloadURL = URL.createObjectURL(new Blob([bytes], {type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));
    $('download').href = downloadURL;
    $('download').download = data.filename;
    $('download').hidden = false;
  }
}
$('convert').addEventListener('submit', async e => {
  e.preventDefault(); clearDownload();
  $('error').hidden = true; $('result').hidden = true; $('start').disabled = true;
  $('progress').textContent = '正在連線…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  let done = false;
  try {
    const response = await fetch('/api/convert', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: $('url').value.trim()}), signal: controller.signal});
    if (!response.ok) {
      let message = '轉換請求失敗，請稍後重試。';
      try { message = (await response.json()).error || message; } catch (_) {}
      throw new Error(message);
    }
    if (!response.body) throw new Error('瀏覽器無法讀取下載串流，請更新瀏覽器。');
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, {stream: !chunk.done});
      const lines = buffer.split('\n'); buffer = lines.pop();
      for (const line of lines) if (line) {
        const data = JSON.parse(line); event(data); if (data.stage === 'done') done = true;
      }
      if (chunk.done) break;
    }
    if (buffer.trim() || !done) throw new Error('下載資料不完整，請重新轉換。');
  } catch (error) {
    controller.abort(); clearDownload();
    $('progress').textContent = '轉換未完成';
    $('error').textContent = error.name === 'AbortError' ? '轉換逾時，請稍後重試。' : (error instanceof TypeError ? '網路或下載中斷，請重新轉換。' : error.message);
    $('error').hidden = false;
  } finally { clearTimeout(timer); $('start').disabled = false; }
});
window.addEventListener('pagehide', clearDownload);
