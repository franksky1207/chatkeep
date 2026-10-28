ChatKeep v1.1.0 開發分支：GitHub Pages 在瀏覽器本機索引、搜尋及擷取使用者選中的官方對話；新增後端單一官方對話 JSON → 可編輯 Word API。分享連結與官方 JSON 共用既有 Word 核心。**維持 Draft，尚未合併或部署。**

## 第 1～3 批

- 本機逐檔／增量索引 JSON，ZIP 逐項解壓至 OPFS，下載指定對話保留來源原始 UTF-8 位元組；未選取對話不傳送。
- 搜尋支援標題、UTC 日期、系列編號範圍交集；搜尋結果全選、索引預覽、缺號／重號及來源報告。mapping 節點數不冒充可見或可匯出訊息數。
- 第 2 批合成 JSON／ZIP、Chromium 及 440 MiB 測試證據見 `docs/BATCH_2_LOCAL_BACKUP.md`；第 3 批 3 個 Node 篩選測試已通過，實機驗收延至第 8 批，見 `docs/BATCH_3_SEARCH_REPORT.md`。

## 第 4 批：JSON → Word API（當批基準；最新容量規則見第 5 批）

- `POST /api/convert-json`，UTF-8 `application/json`，本文直接為一個已選取的官方對話物件；拒絕整包陣列、ZIP 及 conversations 包裝。
- 以 current_node／parent 決定唯一有效分支，驗證循環、父子關係、重複訊息與內容格式；沿用 `chatkeep.normalize()` 及 `word_export.build_docx(rich=True)`。沒有第二套 Word 產生器。
- 共用 `rich_word.py` 補上行內粗斜體、程式碼字型與安全原生超連結，保留既有程式碼區塊、表格、UI 及 Word 結尾段落規則。
- 成功回傳 Base64 DOCX、安全檔名及報告，區分原始節點、有效路徑訊息、實際輸出訊息；隱藏／工具／空節點及非當前分支明確計數警告。未支援可見內容或未完成訊息明確失敗，不輸出看似完整的部分文件。
- 2 MB 本文、32 層、5,000 原始節點、2,000 輸出訊息、100 萬總字元／單則 10 萬字元；未提高既有 Word 上限。共享速率及轉換名額，Gunicorn 上傳 10 秒、子程序轉換 45 秒、CPU 30／31 秒、位址空間 384 MiB，逾時終止並回收程序。
- 不擷取 JSON 內 URL、不持久保存對話或記錄本文；同 host 來源檢查、沒有萬用 CORS。既有 `/api/convert` NDJSON 分享連結介面保留。

驗證：66 個必要單元／整合測試通過（第 4 批專屬 15 個），含既有分享連結與 Word 排版回歸；本機 Gunicorn JSON 成功／錯誤、可重新開啟 DOCX、10 秒停滯上傳中止／名額重用及日誌隱私通過；既有非 live production smoke test 通過。API 範例、錯誤碼、完整性規則、限制及測試命令見 `docs/BATCH_4_JSON_API.md`。

## 第 5 批：單一 Word 優先／長對話分卷

- 移除 100,000 換行與 `<` 粗略拒絕；用實際 Word XML 元素／bytes／表格 cells 判斷單卷容量。兩種來源共用 `conversation_export`／`WordVolume`，能容納就保留單 DOCX。
- 只有下一則完整訊息使單卷超限才換卷；撤回該則的 XML／hyperlink，再於新卷重試。單則本身超限明確失敗；逐卷產生／驗證／封裝 ZIP，不保存全部 Word graph，也不建立私人暫存檔。
- 新版分享 `POST /api/convert-v2` 與原 `/api/convert-json` 回傳版本 2 envelope：artifact_type、MIME、安全檔名、Base64 document、共用完整性報告。保留舊 `/api/convert` NDJSON／DOCX 行為，需 ZIP 時明確回 MULTIPART_REQUIRED，沒有把 ZIP 冒充 DOCX 送給舊前端。
- 依序列化 Word bookmarks、CRC、每卷連續範圍、訊息數與正規化序列 hash 驗證完成；不宣稱已與真實備份／網頁逐字比對。新版不支援的可見內容仍明確失敗。
- 單卷工作預算 120,000 元素／8 MB 本文 XML／5,000 cells；保留全域 5,000 則／500 萬字元，兩來源共用單則 100 萬字元界線。官方傳輸仍為 2 MB、原始節點仍 5,000；最多 16 卷、整包下載仍 16 MB、回應仍 24 MB。新端點沿用 384 MiB AS、30/31 秒 CPU、45 秒 wall-clock、共享並行／速率限制。
- 必要測試 85 個通過（第 5 批專屬 19 個）。13 組獨立受限程序合成量測：60 萬字元、5,000 則短訊息、4.8 百萬字元、4,000 個 code blocks 都優先單 DOCX；舊計數 200,000 的 `<` 案例成功單檔；100,000 行與大型表格各為 2 卷，完整性核對完成。較難壓縮多卷案例 RSS 峰值 87.6 MiB。
- 本機 Gunicorn 實際送 1,416,036 bytes 官方 JSON → 2 卷 ZIP／100 則，約 2.356 秒，程序樹 RSS 基線 44.1 →峰值 125.5 MiB，實際 HTTP envelope 928,387 bytes；並行 429、失敗後重用、DOCX／ZIP／日誌隱私與逾時回收通過。不是 Render Free 實測。

完整 API 契約、容量分類、測試命令／環境／CPU／RSS 數據與未驗證事項見 `docs/BATCH_5_LONG_CONVERSATIONS.md`。Render Free CPU 可能較慢而逾時；新版同步 API 不保證所有斷線立即取消，最遲以 45 秒／資源期限結束。忙碌時提早拒絕大型上傳可能呈現網路錯誤；Pages／跨站 CORS／下載及取消整合留第 6 批，**尚未開始**。真實備份、手機／桌機、Microsoft Word 與正式 Render 驗收統一留第 8 批。

## 第 5-1 批：大型選取對話有界衍生傳輸

- 採免費 Render 優先方案 A：選取對話在獨立本機 worker 驗證 current_node／parent／分類，最小化為有版本、可核對的有效訊息封包；不傳未知 metadata、隱藏／工具本文或非當前分支。原始 Blob.slice JSON 擷取／下載不變；小型仍走 `/api/convert-json`。
- 新 `/api/convert-chunk-v1` 每次仍 ≤2 MB，沿用 SLOTS／RateLimit、384 MiB AS、30/31 秒 CPU、45 秒 wall、10 秒接收期限。沒有 session／私人跨請求 dict／暫存檔；伺服器只確認本批，complete=false、chunk_complete=true、source_verified_by_server=false。
- manifest 綁定隨機 nonce、來源 id、全域順序／範圍／計數及 SHA-256。每批沿用 WordVolume，共用 Word 排版及批內分卷，全域訊息 bookmarks 保持連續；本機逐份驗證 hash／CRC／bookmarks，去重重試、拒絕混批／漏批／錯序後才發布完整 DOCX／ZIP。只有一份成果仍回單 DOCX。
- 本機已選原始物件 ≤16 MB、≤5,000 原始節點；有效序列仍 ≤5,000 則／500 萬字元，單則 ≤100 萬字元；最多 16 批、500 訊息／批、最終合計 16 卷／16 MB，單則不能裝入封包或 Word 容量就明確失敗。順序傳輸至少 6.1 秒節流、429 依 Retry-After 有限重試；可取消／指定批重試。
- **25 個 Node 測試通過**（16 個本批＋9 個原始擷取回歸），**91 個 Python 測試通過**（6 個本批＋85 個必要回歸）。跨語言 canonical vectors、原始 JSON 位元組保留、4 批有效中文、單批內分卷、混批／偽造 complete／損壞／跨批重複 ID、重試去重、worker／request 取消、timeout 與容量界線皆驗證。
- 本機真實 Gunicorn：4,200,461 bytes 冗餘來源只送 989 bytes →單 DOCX；7,200,693 bytes 有效中文以 4 次約 1.80 MB HTTP POST →4 卷 ZIP，約 25.307 秒（含真實節流），全域序列核對完成。伺服器 RSS 程序樹峰值 126.8 MiB，Node 客戶端峰值 218 MiB；第 11 次 POST 真實回 429／Retry-After=60，未提高匿名額度。

完整契約、固定 hash vectors、記憶體／CPU 觀察、來源與驗證範圍及未驗證事項見 `docs/BATCH_5_1_RESULT.md`。未開發第 6 批 UI／跨站 CORS／下載接線；Node worker-thread／Streams 測試不是 Safari、手機／桌機、Microsoft Word 或正式 Render Free 驗收，仍留第 8 批。大型單則／>16 MB 選取來源與成果／過多批卷仍有明確限制，取消 HTTP 亦不保證即時停止後端程序。


本批沒有修改正式 Render v1.0.0、Render 部署設定、Pages UI 或 Actions，沒有觸發 Actions、合併 main、部署、啟用 Pages 或建立 Release。
