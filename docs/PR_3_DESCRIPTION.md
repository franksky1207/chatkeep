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

## 第 7 批：介面、隱私與安全性

- 原生雙模式頁籤與台灣繁體中文步驟；不重設索引／已選對話／成果。開發服務設定收在 details，新增可審核 `site-config.mjs`，正式預設仍空白、未啟用新服務。
- 搜尋結果每頁 50 筆、獨立已選清單每頁 25 筆，工作卡片每頁 20 筆。全選明示包含所有搜尋分頁，顯示篩選外已選數；長名稱可展開、空結果與缺重號範圍說明清楚。原精確日期／系列篩選及原始 JSON 下載保留。
- 一般摘要與進階完整性報告分層，翻譯來源／狀態／略過分類，保留 hash／各卷範圍／scope。小型完整單一 JSON 與大型必要衍生資料的隱私界線明示；不宣稱官方網頁逐字比對或所有媒體已輸出。
- 佇列文字狀態、重試／等待、取消／略過／繼續、下載啟動／釋放均可辨識。未釋放成果不被新轉換默默清掉；控制項維持焦點／展開報告，取消後舊結果仍不發布。下載不宣稱已保存至磁碟。
- 修正 Worker 在轉換期間失敗時，fetch 取消回呼過早解鎖本機清理的競態，附對應瀏覽器回歸。原始 JSON 檔名也使用既有安全處理，URL 啟動後 1 秒撤銷。XSS 合成字串只當文字顯示，無外部請求或追蹤。
- 保留分批協定、Word 核心、所有驗證及 32 MB 成果預算；transfer-client 只加等待／429 的觀察回呼，未改封包、節流或重試政策。未改後端／CORS／配額／部署設定。

## 驗證

合成資料：**96 個 Python、42 個 Node、8 個 UI／安全瀏覽器測試通過**，另本機 Chromium 雙入口整合與原備份 JSON／ZIP 瀏覽器回歸通過。新 UI 測試覆蓋雙模式、365 筆搜尋／全選／精確篩選、125 段模擬工作狀態、兩層報告、XSS、API 錯誤、鍵盤／焦點／aria-live、320／390／768／844／1280 px 無橫向溢出與操作目標，以及 Worker 清理競態。模擬佇列不代替實際大型分批；既有真實 Worker／轉換器／HTTP／DOCX／ZIP 回歸另行通過。公開分享遠端擷取仍為合成注入，不是 ChatGPT／Render 或實體手機驗收。

詳見 `docs/BATCH_7_UI_SECURITY.md`、`docs/BATCH_6_INTEGRATION.md` 及前批文件。**未開始第 8 批**；真實備份、Safari／iPhone／桌機、Microsoft Word、Render Free、正式 Pages 及發布驗收仍待處理。未合併、部署、發布、建立 Release 或啟動 GitHub Actions，正式 v1.0.0 保持原樣。
