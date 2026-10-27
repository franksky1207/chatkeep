'use strict';
const $ = id => document.getElementById(id);
let downloadURL = null;
let suggestedFilename = '未命名對話.docx';
function safeFilename(raw) {
  let name = String(raw || '').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_').trim().replace(/[. ]+$/g, '').slice(0, 100);
  if (!name) name = '未命名對話';
  if (/^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])$/i.test(name)) name = '_' + name;
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
  $('summary').textContent = data.status === 'partial' ? '部分內容無法還原，請查看明細。' : '擷取成功，但尚未完成研究 JSON 的逐訊息比對。';
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
  showProgress(data);
}
$('convert').addEventListener('submit', async e => {
  e.preventDefault();
  clearDownload();
  $('error').hidden = true;
  $('result').hidden = true;
  $('start').disabled = true;
  showProgress({message:'正在連線取得分享頁…',percent:null});
  const controller = new AbortController();
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
    let buffer='';
    while (true) {
      const chunk=await reader.read();
      buffer += decoder.decode(chunk.value,{stream:!chunk.done});
      const lines=buffer.split('\n');
      buffer=lines.pop();
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
    $('error').textContent = error.name==='AbortError'?'轉換逾時，請重新嘗試。':(error instanceof TypeError?'網路或下載中斷，請重新嘗試。':error.message);
    $('error').hidden=false;
    $('activity').hidden=false;
    $('result').hidden=true;
  } finally {
    clearTimeout(timeout);
    $('start').disabled=false;
  }
});
window.addEventListener('pagehide',clearDownload);
