'use strict';
const $ = id => document.getElementById(id);
let downloadURL = null;
let activeController = null;
let cancelledByUser = false;
let suggestedFilename = '未命名對話.docx';
function safeFilename(raw) {
  let name = String(raw || '').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_').trim().replace(/^[. ]+|[. ]+$/g, '')
  name = Array.from(name).slice(0, 100).join('').replace(/[. ]+$/g, '');
  while (new TextEncoder().encode(name).length > 200) name = Array.from(name).slice(0, -1).join('');
  name = name.replace(/[. ]+$/g, '');
  if (!name) name = '未命名對話';
  if (/^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])$/i.test(name.split('.')[0].trimEnd())) name = '_' + name;
  return name + '.docx';
}
function chosenFilename() {
  const value = $('filename').value.trim();
  if (!value) return suggestedFilename;
  return safeFilename(value.replace(/\.docx$/i, ''));
}
function updateFilename() {
  if (downloadURL) $('download').download = chosenFilename();
}
function clearDownload() {
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  downloadURL = null;
  $('download').hidden = true;
  $('download').removeAttribute('href');
}
$('filename').addEventListener('input', updateFilename);
function showProgress(data) {
  const activity = $('activity');
  activity.hidden = false;
  $('progress').textContent = data.message || '正在處理…';
  const percent = Number.isFinite(data.percent) && data.percent >= 0 && data.percent <= 100 ? Math.trunc(data.percent) : null;
  $('percent').hidden = percent === null;
  $('meter').hidden = percent === null;
  if (percent !== null) {
    $('percent').textContent = percent + '%';
    $('meter').value = percent;
  }
  $('progress-detail').textContent = data.detail || '';
}
function report(data) {
  $('result').hidden = false;
  $('summary').textContent = data.status === 'partial' || data.rendering_status === 'partial' ? '部分格式或媒體無法完整還原，請查看警告；尚未完成逐訊息比對。' : '擷取成功，但尚未完成研究 JSON 的逐訊息比對。';
  $('stats').replaceChildren();
  for (const [label, value] of [['原始節點', data.raw_nodes], ['訊息記錄', data.raw_messages], ['可匯出訊息', data.readable_messages], ['使用者', data.visible_roles.user || 0], ['ChatGPT', data.visible_roles.assistant || 0], ['分支以外節點', data.off_branch_nodes]]) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = value;
    $('stats').append(dt, dd);
  }
  $('warnings').replaceChildren();
  for (const warning of data.warnings || []) {
    const li = document.createElement('li'); li.textContent = warning; $('warnings').append(li);
  }
  $('details').replaceChildren();
  const labels = {structural:'結構節點', visible:'可見文字', system:'系統記錄', tool:'工具記錄', hidden:'隱藏訊息', internal:'內部記錄', tool_call:'工具呼叫', empty:'空白', non_text:'非文字內容', unknown:'無法辨識'};
  const dl = document.createElement('dl');
  for (const [category, count] of Object.entries(data.categories || {})) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = labels[category] || category; dd.textContent = count; dl.append(dt, dd);
  }
  $('details').append(dl);
  for (const issue of data.issues || []) {
    const p = document.createElement('p');
    p.textContent = '第 ' + (issue.node_index + 1) + ' 個節點：' + issue.reason;
    $('details').append(p);
  }
}
function onEvent(data) {
  if (data.stage === 'error') throw new Error(data.message || '轉換失敗');
  if (data.stage === 'done') {
    const bytes = Uint8Array.from(atob(data.document), c => c.charCodeAt(0));
    downloadURL = URL.createObjectURL(new Blob([bytes], {type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));
    suggestedFilename = data.filename || '未命名對話.docx';
    $('download').href = downloadURL;
    updateFilename();
    $('download').hidden = false;
    report(data.report);
    $('activity').hidden = true;
    return;
  }
  if (!['fetch', 'parse', 'word', 'pack'].includes(data.stage)) throw new Error('收到無法辨識的進度資料，請重新轉換。');
  showProgress(data);
}
$('convert').addEventListener('submit', async e => {
  e.preventDefault();
  if (activeController) return;
  clearDownload();
  $('filename').value = '';
  cancelledByUser = false;
  $('error').hidden = true;
  $('result').hidden = true;
  $('start').disabled = true;
  showProgress({message:'正在連線取得分享頁…',percent:null});
  const controller = new AbortController();
  activeController = controller;
  $('cancel').hidden = false;
  const timeout = setTimeout(() => controller.abort(), 90000);
  let done = false;
  try {
    const response = await fetch('/api/convert', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('url').value.trim()}),signal:controller.signal});
    if (!response.ok) {
      let message='轉換請求失敗，請稍後重試。';
      try {message=(await response.json()).error || message;} catch {}
      throw new Error(message);
    }
    if (!response.body) throw new Error('目前瀏覽器不支援回應串流。');
    const reader=response.body.getReader(), decoder=new TextDecoder();
    let buffer='', received=0;
    while (true) {
      const chunk=await reader.read();
      received += chunk.value?.byteLength || 0;
      if (received > 26000000) throw new Error('下載回應超過安全大小上限，請縮小分享範圍。');
      buffer += decoder.decode(chunk.value,{stream:!chunk.done});
      const lines=buffer.split('\n');
      buffer=lines.pop();
      if (buffer.length > 24000000) throw new Error('下載資料超過安全大小上限。');
      for (const line of lines) if (line) {
        const data=JSON.parse(line);
        onEvent(data);
        if (data.stage==='done') done=true;
      }
      if (chunk.done) break;
    }
    if (buffer.trim() || !done) throw new Error('下載資料不完整，請重新轉換。');
  } catch (error) {
    controller.abort(); clearDownload();
    $('progress').textContent='轉換未完成';
    $('percent').hidden=true; $('meter').hidden=true;
    $('progress-detail').textContent='';
    $('error').textContent = error.name==='AbortError'?(cancelledByUser?'已取消轉換。':'轉換逾時，請重新嘗試。'):(error instanceof TypeError?'網路或下載中斷，請重新嘗試。':error.message);
    $('error').hidden=false;
    $('activity').hidden=false;
    $('result').hidden=true;
  } finally {
    clearTimeout(timeout);
    $('start').disabled=false;
    $('cancel').hidden=true;
    activeController=null;
  }
});
$('cancel').addEventListener('click', () => { cancelledByUser = true; activeController?.abort(); });
window.addEventListener('pagehide', () => { activeController?.abort(); clearDownload(); });
