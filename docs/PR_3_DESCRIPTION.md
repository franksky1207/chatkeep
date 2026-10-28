GitHub Pages 現在可在同一頁面完成公開分享連結、或本機官方備份中明確選取對話的 Word／ZIP 轉換。備份仍由既有 Worker 在瀏覽器增量索引、搜尋與擷取，Render 只處理選取對話或必要衍生批次。兩種來源沿用同一 Word 排版與分卷核心。

**維持 Draft，等待驗收；未合併、部署 Render／Pages 或建立 Release。正式 Render v1.0.0 保持原樣。**

## 整合行為

- A 分享連結：Pages 驗證固定 ChatGPT share UUID 網址 → `/api/convert-v2`；公開頁仍由 Render 擷取，前端不跨站擷取分享頁。
- B 官方備份：保留本機 JSON／ZIP、Worker 增量索引、標題／UTC 日期／系列篩選、缺重號報告、搜尋全選、預覽及原始位元組 JSON 下載。選取後逐段擷取 Blob，交 `prepareInWorker()`；小型走 `/api/convert-json`，大型走 `/api/convert-chunk-v1`、`sendPrepared()`、`TransferResults`。
- 多選依序處理，每段獨立狀態與完整性報告。失敗暫停，可重試缺少／失敗批次或略過；已驗證批次與其他已完成對話保留。完成成果總預算 32 MB，開始下一段前預留 16 MB；不足時先下載並明確釋放成果，再繼續。沒有無界全部下載或跨對話混卷。
- 新版 API 僅對 `CHATKEEP_ALLOWED_ORIGINS` 明確設定的完整 origin 開放 CORS，預設不開跨站；正式設定可使用 `https://franksky1207.github.io`，開發僅加入核准的精確 localhost origin。保留 Host、RateLimit、SLOTS、上傳與子程序限制；不接受 Cookie／Authorization，不使用萬用來源或公開代理。OPTIONS 僅允許 POST／Content-Type，實際請求僅 UTF-8 JSON，Expose Retry-After。
- API Base URL 由本頁明確設定，預設空白；可用本機 API 或未來新版 Render，不假設正式 v1.0.0 已提供新路由。不放金鑰、不持久保存設定或私人轉換成果。
- 進度只顯示實際本機掃描／準備／批次、等待 Render、分卷驗證、ZIP 封裝與下載就緒。取消中止 fetch、準備 Worker 與未開始批次，清除取消段落；工作世代隔離舊回應。取消瀏覽器不保證同步 Render 程序即時停止，仍受 45 秒期限控制。
- DOCX／ZIP 必須通過 v2 envelope、MIME、Base64、容量、每卷 SHA-256／CRC／bookmarks／連續範圍核對後才提供下載，先呈現來源、輸出數、卷數、警告與完整性層級。大型衍生序列標示 `browser_derived_sequence`，不宣稱官方網頁逐字比對。Object URL 下載啟動後撤銷，取消／清除亦撤銷。

## 保留的容量與排版

第 1～5-1 批的增量索引、分支驗證、完整訊息切批、Word Markdown／表格／巢狀儲存格結尾段落及單檔優先規則保留。選取來源 ≤16 MB、每次上傳 ≤2 MB、最多 16 批、16 卷／16 MB 最終成果；有效輸出 ≤5,000 則／500 萬字元，單則不能裁切。至少 6.1 秒節流、每次最多原次加兩次 429 重試並遵守既有 Retry-After 政策；沒有提高匿名 API 額度。

## 驗證

合成資料：96 個 Python、37 個 Node 測試通過。本機 Chromium 雙入口整合驗證實際跨 origin OPTIONS／POST、真實 Worker 與轉換器、選取隔離、metadata 排除、原始 JSON、DOCX／ZIP 下載、網路失敗與取消後舊回應隔離。公開分享遠端擷取以合成內容注入；不是正式 ChatGPT／Render 或手機驗收。既有本機 JSON／ZIP 瀏覽器回歸與 Gunicorn DOCX／ZIP、停滯上傳期限、名額回收、日誌隱私檢查通過。

詳見 `docs/BATCH_6_INTEGRATION.md`；第 1～5-1 批原始證據見各批文件。第 7 批介面／安全性優化與第 8 批真實備份、手機／桌機、Microsoft Word、Render Free 及正式發布驗收仍未執行。未啟動 GitHub Actions。
