ChatKeep v1.1.0 開發分支：GitHub Pages 在瀏覽器本機索引、搜尋及擷取使用者選中的官方對話；新增後端單一官方對話 JSON → 可編輯 Word API。分享連結與官方 JSON 共用既有 Word 核心。**維持 Draft，尚未合併或部署。**

## 第 1～3 批

- 本機逐檔／增量索引 JSON，ZIP 逐項解壓至 OPFS，下載指定對話保留來源原始 UTF-8 位元組；未選取對話不傳送。
- 搜尋支援標題、UTC 日期、系列編號範圍交集；搜尋結果全選、索引預覽、缺號／重號及來源報告。mapping 節點數不冒充可見或可匯出訊息數。
- 第 2 批合成 JSON／ZIP、Chromium 及 440 MiB 測試證據見 `docs/BATCH_2_LOCAL_BACKUP.md`；第 3 批 3 個 Node 篩選測試已通過，實機驗收延至第 8 批，見 `docs/BATCH_3_SEARCH_REPORT.md`。

## 第 4 批：JSON → Word API

- `POST /api/convert-json`，UTF-8 `application/json`，本文直接為一個已選取的官方對話物件；拒絕整包陣列、ZIP 及 conversations 包裝。
- 以 current_node／parent 決定唯一有效分支，驗證循環、父子關係、重複訊息與內容格式；沿用 `chatkeep.normalize()` 及 `word_export.build_docx(rich=True)`。沒有第二套 Word 產生器。
- 共用 `rich_word.py` 補上行內粗斜體、程式碼字型與安全原生超連結，保留既有程式碼區塊、表格、UI 及 Word 結尾段落規則。
- 成功回傳 Base64 DOCX、安全檔名及報告，區分原始節點、有效路徑訊息、實際輸出訊息；隱藏／工具／空節點及非當前分支明確計數警告。未支援可見內容或未完成訊息明確失敗，不輸出看似完整的部分文件。
- 2 MB 本文、32 層、5,000 原始節點、2,000 輸出訊息、100 萬總字元／單則 10 萬字元；未提高既有 Word 上限。共享速率及轉換名額，Gunicorn 上傳 10 秒、子程序轉換 45 秒、CPU 30／31 秒、位址空間 384 MiB，逾時終止並回收程序。
- 不擷取 JSON 內 URL、不持久保存對話或記錄本文；同 host 來源檢查、沒有萬用 CORS。既有 `/api/convert` NDJSON 分享連結介面保留。

驗證：66 個必要單元／整合測試通過（第 4 批專屬 15 個），含既有分享連結與 Word 排版回歸；本機 Gunicorn JSON 成功／錯誤、可重新開啟 DOCX、10 秒停滯上傳中止／名額重用及日誌隱私通過；既有非 live production smoke test 通過。API 範例、錯誤碼、完整性規則、限制及測試命令見 `docs/BATCH_4_JSON_API.md`。

後續界線：大型對話／分卷是第 5 批；Pages 連接 Render／跨站 CORS／前端取消是第 6 批，尚未開發。真實官方備份、手機／桌機、Microsoft Word 與 Render Free 實機驗收統一留第 8 批。384 MiB 是子程序位址空間限制，不是整個服務 RSS／免費 Render 壓測保證；同步轉換在客戶端斷線後最遲依 45 秒期限中止。

本批沒有修改正式 Render v1.0.0、Render 部署設定、Pages UI 或 Actions，沒有觸發 Actions、合併 main、部署、啟用 Pages 或建立 Release。
