# ChatKeep v1.1.0 第 7 批：介面、隱私與安全性

狀態：Codex 依本批使用者指令完成介面與必要合成測試，等待確認。沒有執行第 8 批正式驗收或發布。

## 基準與範圍

2026-10-28 重新 fetch `feat/local-json-extractor`，遠端最新仍為 `82322d3930ea40a27f9de08a932c8ef58f59cc5f`，工作目錄乾淨。GitHub PR #3 網頁確認仍為 Draft。已閱讀 `CHATKEEP_V1_1_PLAN.md`、`BATCH_5_1_RESULT.md`、`BATCH_6_INTEGRATION.md` 及指定四個前端檔案。原計畫第 7 批原列 Chat，本次依使用者明確指令由 Codex 執行。

本批只改靜態 Pages 前端、呈現用 helper、必要測試與文件；沒有重寫 JSON／ZIP 索引器、分支正規化、分批 schema／hash、ZIP verifier 或 Word 排版核心，沒有改後端來源、CORS、配額、部署設定或 Actions。

## 雙入口與服務設定

- 網站名稱維持「ChatKeep｜對話收藏」，以原生 HTML／CSS／ES modules 整理為分享連結、官方備份兩個頁籤。同頁共用轉換佇列及報告；切換不重設備份索引、已選清單或現有成果。
- 分享模式顯示固定網址格式、公開分享限制、私人網址改用備份模式、服務等待與長對話分卷說明。表單可 Enter 提交，錯誤定位至輸入，aria-invalid 與文字提醒並存。公開分享仍由 Render 擷取。
- 官方備份分為選檔／建立索引、搜尋選取、Word 轉換三步。原始 JSON 收在獨立「另存原始對話 JSON（不是 Word）」區塊，明示其用途、完整原始結構與其他分支的差異。
- 首頁顯示「開發預覽／尚未設定」，服務網址收在「開發與測試設定」。沒有自動探測或輪詢服務，也不將尚未部署的新 API 標為可用。填入網址只表示已指定、尚未驗證；只有實際通過新版回應驗證後才顯示收到新版回應，且不承諾後續每次都可用。
- `site-config.mjs` 新增可審核的 `DEFAULT_API_BASE=''`。第 8 批確認後才可在版本控制中指定正式 HTTPS origin；本批保持空白、未啟用正式 API，一般未來使用者不需理解 API path 或環境變數。開發 override 只保留在分頁記憶體。
- 保留 HTTPS／本機 HTTP 的既有網址檢查，拒絕不安全公網 HTTP、帳密、path／query／fragment；沒有前端 token。明示只指定信任的服務，因選取內容會送往該位址。404、版本不相容、網路／CORS 提供一般文字原因與可行方式，錯誤 code 收在進階詳細資訊。

## 搜尋與選取

所有精確篩選仍使用原 `filters.mjs`：標題、UTC 建立／更新日期、系列名稱及阿拉伯／中文編號起訖，沒有改其交集或邊界規則。

- 顯示總索引數、符合數、已勾選數；全選按鈕明示符合總數及「包含所有分頁」。改變搜尋不會丟掉先前勾選。
- 搜尋結果每頁 50 筆，已選清單獨立每頁 25 筆，皆有分頁與原生可捲動區塊。DOM 不一次展開數百筆；全選仍包含全部符合對話。
- 已選清單指出有多少勾選位於目前篩選外，轉換會包含全部已選對話。支援逐項移除及清除全部選取，預覽仍只讀索引資訊，不展示私人本文。
- 空結果提供換關鍵字、調整篩選或清除篩選的提示；清除篩選不影響已選清單。
- 缺號／重號文字永遠註明僅根據成功解析且符合篩選的來源。原始 mapping 節點數不當成可見／可匯出訊息數。
- 長標題可換行，搜尋結果／已選／工作摘要最多顯示三行，完整標題可由索引預覽或原生 details 展開；不是裁切原始檔或轉換內容。

## 佇列、進度與報告

第 6 批順序佇列、逐段獨立 prepared／collector、32 MB 成果預算，以及每段 16 MB 來源、每請求 2 MB、最多 16 批／16 卷／16 MB 最終成果等界線保留。

- 工作顯示等待中、處理中、成功／下載就緒、失敗／可重試、已釋放、已略過、已取消，並彙總數量及成果暫存量。佇列每頁最多 20 張卡片，可查看處理中的工作，沒有另建大量 DOM 或全部下載。
- 提供取消、重試失敗對話／缺少批次、略過、容量暫停後繼續、下載、釋放及清除全部結果。失敗時不讓「繼續」混淆為跳過失敗，必須明確重試或略過。
- 轉換按鈕不會默默丟掉上一輪尚未釋放的成果；先提示下載、釋放或明確清除。重新掃描／清除索引也不會順便刪掉先前已完成的 Word 成果。
- 真實掃描 bytes、對話擷取、本機準備、等待傳送、正在處理第 X / Y 批／等待 Render、完整性驗證、必要時 ZIP 封裝、下載就緒分別呈現。沒有假百分比、倒數模擬或額外後端輪詢。
- `sendPrepared()` 只新增可選 `onProgress` 觀察回呼，通知實際等待批次／429 重試秒數；不改傳輸封包、節流、重試次數、順序、期限或驗證規則。429 不再被畫面誤標為分卷驗證。
- 下載按鈕只記錄「已啟動下載（未確認是否保存至磁碟）」，不顯示「下載完成」。釋放後仍保留該段完整性報告與檔案類型。Object URL 依既有轉換下載規則於啟動後 1 秒撤銷，取消／清除／pagehide 也撤銷；原始 JSON 從 60 秒縮短為相同 1 秒。
- 同一頁的工作卡片盡量保留 DOM，階段更新／按下載不摧毀焦點或已展開報告；僅分頁時替換可見卡片。重試／略過／釋放後有明確的焦點去向。

報告改為兩層，`presentation.mjs` 僅產生唯讀呈現資料：

1. 一般摘要：名稱、來源模式、匯出訊息、Word 卷數、DOCX／ZIP、成功／有警告、是否發現輸出序列缺漏；失敗工作直接顯示原因與操作。
2. 進階資訊：原始 mapping 節點、有效路徑訊息、略過分類、非當前分支排除數、批次數、各卷範圍與檔案／序列 SHA-256、警告及來源驗證層級。

`normalized_output_sequence` 說明為伺服器驗證正規化輸出序列，前端另核對文件／書籤；`browser_derived_sequence` 說明為本機衍生有效訊息序列全部批次核對，伺服器只驗證各批、未驗證原始完整官方 JSON。兩者都不代表與 ChatGPT 官方網頁逐字比對，SHA-256 不是官方認證，也不宣稱媒體、隱藏或略過內容全部輸出。缺少資料顯示「未提供」，不捏造數量。

## 隱私、安全與清理

隱私說明直接位於備份入口，細節可展開：

- 整包備份只在本機索引／搜尋，未選取對話不傳送；按下轉換才傳送必要資料。
- 小型路徑可能傳完整已選單一官方 JSON，包含 metadata 與非當前分支；大型路徑建立必要有效訊息衍生序列，可排除不必要 metadata 與其他分支。沒有宣傳「所有資料絕不離開裝置」。
- Render 暫時以記憶體處理內容，本程式不永久儲存本文、不將私人內容寫入一般日誌；這不是對瀏覽器、網路或平台的絕對保證。
- ZIP 使用 OPFS 本機暫存、取消掃描／清除索引會刪除，關閉頁面僅嘗試清理，異常關閉可能殘留；提供清除網站儲存空間的說明。大型備份建議桌機，不保證手機處理數百 MB。

安全檢查與修正：

- 私人標題、API 警告與錯誤均以 textContent／DOM API 插入；新模組沒有 innerHTML、eval、第三方追蹤或內容日誌。合成 `<img onerror>`／`<script>` 只顯示為文字，未執行或發出外部請求。
- 原始 JSON 下載也改用既有安全檔名處理，過濾控制字元、雙向文字控制碼、路徑與保留裝置名稱；原始對話 bytes 不變。DOCX／ZIP MIME、Base64、SHA-256／CRC／書籤 verifier 不改。
- 修正「索引 Worker 在轉換期間失敗，取消 fetch 的完成回呼比本機清理早到」的解鎖競態。`setLocked(false)` 仍尊重 `cleaning`，不允許在舊 Worker／暫存尚未清理完之前重新掃描。對應瀏覽器回歸延遲取消確認 1 秒，檢查清理中按鈕持續停用、取消段落沒有下載，再成功重掃。這是前端資源與操作狀態修正，未放寬後端或協定。
- 保留第 6 批 epoch／AbortController，取消後晚到結果不發布、已完成段落保留。取消仍不能保證同步 Render 子程序立即停止，畫面明示最長 45 秒後端期限。
- 未改 api_origin.py／json_api.py／server.py、Render 配置、Word 核心、CORS 白名單或匿名限額。既有 web/ v1.0.0 分享介面與路徑不變。

## 響應式與可及性

原生響應式 CSS、系統字型，無大型框架／第三方字型／裝飾動畫。320／390／768／844（橫向 CSS viewport）／1280 px 自動檢查無橫向溢出，長標題、篩選、已選清單、工作卡片、展開報告與按鈕有界換行；主要按鈕、summary、文字輸入高度至少約 44 px，勾選框另由同列 label 提供較大的觸控範圍。超長標題保留展開完整名稱的操作，避免占滿手機畫面。

每個輸入皆有 label；原生頁籤採 tablist／tab／tabpanel、aria-controls／selected 與 roving tabindex，支援左右鍵／Home／End。表單可 Enter，清單保留鍵盤勾選與預覽，重要錯誤有文字、aria-invalid，重要狀態 aria-live=polite。焦點外框、跳到主要內容連結、列表／標題／定義清單結構保留，成功／失敗不只依賴顏色。檢查是自動化 DOM／鍵盤／CSS 測試，不是完整 WCAG 認證或真實螢幕閱讀器驗收。

## 測試與證據

全部使用合成資料。執行環境為本機 Linux、Python 3.12、Node 24、Playwright＋系統 Chromium 154.0.8037.57，並非 Render Free、Safari 或實體 iPhone。

```sh
PYTHONPATH=tests .venv/bin/python -W error::ResourceWarning -m unittest \
 test_pages_cors test_chunk_transfer test_long_conversations test_official_json \
 test_integration test_rich_word test_word_layout test_acceptance test_chatkeep -q
node --test tests/presentation.test.mjs tests/pages_conversion.test.mjs \
 tests/large_transfer.test.mjs tests/large_transfer_worker.test.mjs \
 tests/local_backup.test.mjs tests/local_backup_filters.test.mjs
.venv/bin/python tests/ui_security_browser.py
PYTHONPATH=.:tests .venv/bin/python tests/pages_integration_browser.py
.venv/bin/python tests/local_backup_browser.py
```

結果：**96 個 Python、42 個 Node、8 個 UI／安全瀏覽器測試通過**，另兩套本機瀏覽器整合腳本通過。

- Python 96：必要的既有 share v1／v2、官方／chunk、長對話、Word／表格／巢狀 cell、上限、取消／timeout、CORS／RateLimit 與內容隱私回歸。最後一輪約 22.6 秒，ResourceWarning 視為錯誤。
- Node 42：既有 37 加 5 個呈現／scope／文字狀態／重試觀察回呼／設定與檔名測試。真正大量有效文字仍跨多次實際子程序轉換，DOCX／ZIP 順序、hash／CRC／bookmarks、失敗批重試、32 MB 預算與 Worker 取消／重啟不退化。最後一輪約 17.3 秒。
- 新 UI 8：雙模式、公開網址／私人網址、未設定／不安全／未驗證服務、隱私文案、365 筆索引／全選／獨立已選清單、日期／系列缺重號、空結果、原始 JSON、125 段模擬佇列的狀態／分頁／重試／略過／下載／釋放／取消／保護先前成果、兩層報告與兩種 scope、XSS、進階錯誤、鍵盤／焦點／aria-live、5 種視窗尺寸，以及 Worker 失敗清理競態。125 段佇列與部分狀態使用明確的 presentation fake，stub 下載不當成真正 DOCX 核心驗證；測試注入僅存在測試路由，不對正式頁面暴露測試全域。
- `pages_integration_browser.py`：真實本機跨來源 OPTIONS／POST、索引與準備 Worker、官方／chunk 轉換子程序、未選取內容不送出、metadata 排除、原始 JSON 與已驗證 DOCX／ZIP 下載、網路錯誤、fetch 取消／舊回應不發布。分享遠端擷取仍用合成回應注入，不冒充 ChatGPT live。只更新新頁籤／details／顯示按鈕的 selector，及在新轉換前明確清除已完成成果的操作。
- `local_backup_browser.py`：原 JSON／ZIP／CRC／損壞／OPFS／儲存權限／原始 bytes 回歸，365 筆搜尋全選仍全部勾選；預期 DOM 300 筆改為分頁 50 筆。無未捕捉 pageerror 或外部網路請求。
- Node 語法、git diff --check 通過；檢視 390 px 合成首頁／報告截圖，僅留本機暫存，不提交截圖或私人檔案。不執行 GitHub Actions、不做第 8 批壓測或實機驗收。

## 檔案與交付

新增：`site.css`、`site-ui.mjs`、`site-config.mjs`、`presentation.mjs`（皆在 docs/local-backup）、`tests/presentation.test.mjs`、`tests/ui_security_browser.py`、本文件。

修改：`docs/index.html`、`docs/local-backup/app.mjs`、`conversion-ui.mjs`、`conversion.mjs`、`transfer-client.mjs`、`tests/local_backup_browser.py`、`tests/pages_integration_browser.py`、`docs/PR_3_DESCRIPTION.md`。

沿用開發分支／Draft PR #3，commit／push 的 SHA 及結果以交付回報為準。GitHub 網頁可確認 Draft，但 `gh pr view/edit` 的 api.github.com/graphql 目前遭網路政策 Forbidden；PR 說明備稿已更新至 `docs/PR_3_DESCRIPTION.md`。遠端更新是否成功必須以實際工具結果回報，不能把本地備稿當成已更新。

## 正式版影響與第 8 批待辦

本批未修改 main、後端正式環境、Render main／autoDeployTrigger=off 設定、GitHub Pages 發布或 Release；沒有手動觸發 Actions。正式 Render v1.0.0 不受本批前端分支改動影響。

第 8 批仍須驗收：真實官方備份、iPhone Safari／實體手機與桌機、螢幕閱讀器與實際鍵盤操作、Microsoft Word 直接開啟單檔／多卷、Render Free 的 CORS／代理／冷啟動／CPU／RSS／timeout、正式 Pages HTTPS 雙入口與下載、容量及隱私／取消限制。發布前審核 DEFAULT_API_BASE 與來源白名單，確認新版後端已可用；全部通過後才依規則合併、手動部署、發布 Pages／Release。本批未開始這些正式驗收或發布操作，完成後停止等待使用者確認。
