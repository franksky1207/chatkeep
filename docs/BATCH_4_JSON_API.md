# v1.1.0 第 4 批：官方 JSON → Word API

基準：`38a0845489401b158bcb2cd5bf5717593d88f825`，分支 `feat/local-json-extractor`，沿用 Draft PR #3。只完成後端及必要的共用排版修正；沒有 Pages 接線、跨站 CORS、長文分卷、部署、發布或實機驗收。正式 Render v1.0.0 沒有被更新或呼叫。

## API 契約

`POST /api/convert-json`，`Content-Type: application/json`（亦接受 `; charset=utf-8`），必須有正確 `Content-Length`。本文直接是使用者選取的一個官方對話物件，**沒有 conversation 包裝**：

```json
{
  "title": "合成對話",
  "id": "optional-official-id",
  "current_node": "a",
  "mapping": {
    "u": {"parent": null, "children": ["a"], "message": {
      "id": "u", "author": {"role": "user"},
      "content": {"content_type": "text", "parts": ["你好"]}
    }},
    "a": {"parent": "u", "children": [], "message": {
      "id": "a", "author": {"role": "assistant"},
      "content": {"content_type": "text", "parts": ["你好！"]}
    }}
  }
}
```

不接受陣列、`conversations` 包裝、`linear_conversation` 替代路徑、ZIP、multipart、壓縮或 chunked 本文。單一物件必須有字串 title、非空 mapping、有效 current_node。官方 ID 可省略；節點冗餘 id 可省略，若存在必須和 mapping key 相同；parent 必填；children 可省略，存在時檢查父子雙向一致性。未知頂層／metadata 欄位不當成訊息，也不執行或擷取其 URL。伺服器不能證明使用者實際點選行為；第 6 批前端必須確保只送選中的對話。

成功 HTTP 200，JSON envelope：

```json
{
  "ok": true,
  "filename": "合成對話.docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "document": "<base64 DOCX>",
  "report": {
    "source": "official_json",
    "raw_node_count": 2,
    "active_path_node_count": 2,
    "active_path_message_count": 2,
    "output_message_count": 2,
    "off_branch_node_count": 0,
    "skipped_categories": {},
    "warnings": [],
    "status": "converted",
    "reference_comparison": "not_performed",
    "verified_against_live_page": false
  }
}
```

前端先顯示 report，再把 document Base64 解碼成指定 MIME 的 Blob，使用 filename 下載。選擇 JSON envelope 是為了將完整性報告和 DOCX 一起回傳，並沿用既有服務的 Base64 文件傳輸方式，不建立持久下載 URL。JSON 模式是一次完成回應；既有 `/api/convert` 保持 NDJSON 進度串流及原有格式。

失敗一律不含 document：`{"ok":false,"error":{"code":"INVALID_JSON","message":"請提供有效 UTF-8 JSON。"}}`。HTTP 狀態與 code 為前端判斷依據，message 只供顯示。

| HTTP | code |
|---|---|
| 400 | INVALID_JSON、INVALID_LENGTH、INCOMPLETE_BODY |
| 403 | HOST_FORBIDDEN、ORIGIN_FORBIDDEN |
| 405 | METHOD_NOT_ALLOWED |
| 408 | UPLOAD_TIMEOUT |
| 413 | INPUT_TOO_LARGE、STRUCTURE_LIMIT、NODE_LIMIT、TEXT_LIMIT |
| 415 | UNSUPPORTED_MEDIA_TYPE、UNSUPPORTED_ENCODING |
| 422 | SINGLE_CONVERSATION_REQUIRED、INVALID_CONVERSATION、INVALID_BRANCH、DUPLICATE_MESSAGE、UNSUPPORTED_CONTENT、UNFINISHED_MESSAGE、NO_EXPORTABLE_MESSAGES、INVALID_CHARACTERS、EXPORT_LIMIT |
| 429 | RATE_LIMITED、BUSY |
| 503 | RESOURCE_LIMIT、CONVERSION_FAILED |
| 504 | CONVERSION_TIMEOUT |

## 正規化、分支與完整性

`official_json.normalize_official()` 在嚴格 UTF-8／JSON 驗證後，檢查 parent 關係、所有節點（含非當前分支）的循環、children 一致性及必要欄位。只用 current_node 的 parent 鏈，反轉成根到葉順序；不依 mapping 插入順序、時間戳或 children 猜測順序。無法決定 current_node 就失敗，不選任意葉節點。有效路徑訊息 ID 重複直接拒絕，不冒險自行去重。

之後沿用 `chatkeep.normalize()` 既有分類與文字抽取能力，產生 schema_version 1.0 訊息，交給同一個 `word_export.build_docx(rich=True)`、`rich_word.py`、`word_layout.py`。沒有第二套 Word 產生器，也沒有改寫 chatkeep.py／word_export.py 的既有分享頁行為或上限。

- user／assistant 可見文字依原順序輸出；Unicode、換行及 Markdown 交給共用排版器。多個文字 parts 按既有規則以換行連接。
- structural、system／developer、tool、隱藏旗標、analysis／justify／confidence 內部訊息、reasoning 類內容、assistant 工具呼叫、空訊息分別略過並回報分類數量；不把內部／工具內容冒充可見對話。
- 其他分支只回報數量及 `OFF_BRANCH_EXCLUDED` 警告，不將其混入 Word。有效路徑訊息數包含路徑上所有非 null message（含被略過類別），輸出訊息數只計算可見文字；原始節點數是整個 mapping。
- 有效可見內容只支援純文字／code。多媒體、未知角色／內容型態、混合 text/parts 的不明確內容或未完成訊息，整次明確失敗，避免大量遺漏後看似成功。隱藏／工具節點不會因非文字內容而被輸出。
- 回報的 warnings 只含固定 code／文字／count，不含標題、本文、訊息 ID 或使用者自訂 metadata。成功有略過節點或排版限制時 status 為 converted_with_warnings。
- Word 內同時列出來源數量與略過警告。共用排版器的格式限制會在對應訊息註記，API 另提供 RENDERING_LIMITATIONS 數量。未知 HTML／UI 格式保留可編輯原文與既有警告，不執行腳本；圖片不下載。
- 未宣稱與 ChatGPT 網頁／真實備份逐訊息比對完成。統計與合成測試不能替代第 8 批驗收。

本批測試發現原共用排版器一般 Markdown 行內粗體／斜體／超連結仍是字面文字，因此在 **同一個 rich_word.py** 補上 Word 原生 runs／hyperlink：段落、標題、清單及表格都共用，兩種來源一起使用。安全連結只允許 HTTP(S)／mailto，不在伺服器擷取；其他協定保留原文。行內程式碼使用 Consolas 並保留既有反引號原文契約。程式碼區塊、巢狀 UI 及表格結尾段落規則保持既有核心。

## 安全與資源界線

| 項目 | 第 4 批 JSON 端點界線 |
|---|---|
| 請求 | 2,000,000 UTF-8 bytes，先檢查 Content-Length，再有限讀取 |
| JSON 結構 | 解碼前深度掃描 ≤32 層；拒絕重複鍵、NaN／Infinity、非有限數、非法 XML／Unicode 字元；解碼後 ≤100,000 個值／key 項目 |
| 對話 | 原始節點 ≤5,000；輸出 ≤2,000 則、總文字 ≤1,000,000 字元、單則 ≤100,000 字元 |
| 欄位 | title ≤1,000 字元；對話／節點／訊息 ID ≤256 字元 |
| Word | 原有 5,000 則／500 萬字元、100,000 換行及 `<` 計數、16,000,000 bytes DOCX 上限仍保留；不截斷／分卷 |
| 回應 | ≤24,000,000 bytes，包含 Base64 與報告；子程序輸出由可信 worker 依 DOCX 上限產生 |
| 轉換程序 | Linux resource 限制：虛擬位址空間 384 MiB、CPU 軟／硬 30／31 秒；wall-clock 45 秒後 kill 並 reap，core dump 關閉 |
| 同時轉換 | 與分享端點共用 SLOTS；既有 Gunicorn 設定一個 worker、一個轉換名額；本機設定最多 2；不新增工作佇列 |
| 速率 | 兩端點共用既有 RateLimit，每來源 IP 每分鐘 10 次、全域每分鐘 60 次、最多 1,024 個來源紀錄；不信任 forwarded IP |
| 接收本文 | Gunicorn 的 gunicorn.socket 設 10 秒總接收 watchdog，逾時 shutdown 讀端並回 408；非 Gunicorn WSGI 須由宿主提供上傳期限，本機既有 Handler 有 10 秒 socket timeout |
| 來源 | 既有 Host allowlist；拒絕 cross-site Fetch Metadata、不匹配 host 的 Origin；沒有萬用 CORS、沒有憑證／cookie 或 CSRF 豁免。Pages 跨站接線留第 6 批 |

資料只在請求及子程序記憶體／pipe 中；不建立私人暫存檔、資料庫、下載快取或內容日誌；子程序 stderr 丟棄，例外只回固定錯誤，不回 traceback／來源內容。filename_for() 共用既有安全檔名處理。用絕對程式路徑、無 shell／私人命令列參數執行 worker。既有 Gunicorn 不開 access log。所有來源 URL 都不拿來擷取；超連結僅成為 DOCX 關聯。

限制：384 MiB 是單一子程序位址空間限制，**不是整個服務 RSS 上限或免費 Render 負載驗收**。反向代理若共用 REMOTE_ADDR，會受較保守共用速率限制。匿名 API 的來源檢查無法阻止非瀏覽器客戶端偽造標頭，仍依大小、速率、並行與程序限制保護。同步 WSGI 無法即時得知所有客戶端斷線；最遲 45 秒停止轉換，主動取消／前端體驗留第 6 批。此端點刻意拒絕超限大型單段對話，第 5 批尚未開發。

## 自動化驗證（合成資料）

```sh
PYTHONPATH=tests .venv/bin/python -W error::ResourceWarning -m unittest \
  test_official_json test_integration test_rich_word test_acceptance test_word_layout test_chatkeep -q
.venv/bin/python tests/official_api_transport.py
.venv/bin/python tests/production_check.py
```

第 4 批專屬測試涵蓋官方結構、交替角色、打亂 mapping 順序、多分支／current_node、隱藏／工具／空節點、循環、重複訊息、未知內容、損壞／重複鍵 JSON、Unicode／Emoji、輸入／深度／項目／節點／訊息／字元上限、惡意 HTML／不安全協定／檔名、HTTP 契約、繁忙／速率／逾時／程序中止、可重新開啟 DOCX、表格／原生粗斜體／超連結、日誌隱私與共用排版器呼叫。

`official_api_transport.py` 實際啟動**本機 Gunicorn**：成功轉 Word、400 JSON 錯誤、10 秒停滯上傳回 408、釋放名額後再次成功，並檢查 stdout／stderr 沒有合成私人標題、本文及非當前分支。既有 production_check.py 僅執行非 live 模式。未跑手機／桌機實機、Microsoft Word、真實備份、正式 Render、瀏覽器或 GitHub Actions；統一留第 8 批。

結果：上述 **66 個單元／整合測試全通過**（其中第 4 批專屬 15 個，9.017 秒），ResourceWarning 視為錯誤；兩項本機 Gunicorn smoke test 均通過。`git diff --check` 通過。沒有新增套件依賴或修改部署設定。
