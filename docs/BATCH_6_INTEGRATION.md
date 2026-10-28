# ChatKeep v1.1.0 第 6 批：Pages／Render 整合

基準：2026-10-28 fetch `feat/local-json-extractor` 得到 `a26c1c9f6f0c3621923c38b4c28bca627f08ef29`，與指定第 5-1 批相同；原工作目錄乾淨，從環境初始 `work` 分支切換至指定開發分支。已閱讀計畫及第 4／5／5-1 批指定文件。沿用 PR #3，GitHub 頁面確認 Draft，沒有合併或變更正式服務。本批完成技術整合與合成測試，等待驗收；不是正式部署或第 8 批驗收。

## 入口及資料邊界

`docs/index.html` 是兩模式主入口，沿用 `local-backup/app.mjs` 與原 JSON／ZIP 索引 Worker；未建立替代備份解析器。

- A：固定 `https://chatgpt.com/share/<uuid>` → `POST /api/convert-v2` JSON envelope。只傳網址，Render 繼續擷取公開頁；Pages 不擷取 ChatGPT 網頁。保留既有 v1.0.0 網站的獨立連結與 `/api/convert` NDJSON 行為，未改 `web/`。
- B：原標題／日期／系列篩選、缺重號報告、單多選／全選、預覽、原始 JSON 下載繼續獨立運作。只從 index 中明確選取的 row 逐一向現有 Worker 取得 Blob，擷取前檢查 16 MB。索引僅保存來源範圍與摘要；未選取的 row 沒有呼叫 extract／prepare／API。
- 每段 Blob 交第 5-1 批 `prepareInWorker()`。mode=official 將原 Blob 送 `/api/convert-json`；mode=chunks 只將必要有效文字衍生封包送 `/api/convert-chunk-v1`，以既有 `sendPrepared()` 與 `TransferResults` 發送／核對／組裝。大量 metadata／非當前分支不進衍生封包。小型官方路徑依原契約保留已選單一原始物件，不宣稱會刪掉其中全部 metadata。
- 所有請求是 POST，URL 不帶私人內容；不放認證金鑰、不使用 Cookie、不記錄來源／對話本文。不傳 GitHub、第三方雲端或公共分享服務，不新增內容持久化。ZIP 備份原有 OPFS 暫存與清理規則保留。

新增 `conversion.mjs` 負責服務設定、傳輸、單次回應驗證、有界佇列與錯誤說明；`conversion-ui.mjs` 只接 UI 與結果按鈕。原 app 只新增 selected/extract/lock 接點及可取消 extract promise，原索引／Blob.slice 解析器不變。

## API 與 CORS 設定

前端 API Base URL 預設**空白**，只存在分頁記憶體；輸入例如 `http://localhost:8000`。允許 HTTPS origin，HTTP 僅限 localhost／127.0.0.1／IPv6 loopback；拒絕帳密、路徑、query、fragment。不得將開發版預設指向正式服務未發布路由。未部署路由 404、錯誤 MIME／API 版本、網路／CORS 問題各有提示；瀏覽器不能精確區分斷網與 CORS，故不捏造單一原因。

後端 `api_origin.py` 對新版三路徑共用來源檢查：

```sh
# 未來部署前由管理員設定，這裡只是設定範例，未執行部署。
CHATKEEP_ALLOWED_ORIGINS=https://franksky1207.github.io
# 本機核准測試可明確加入實際 port；正式不要沿用測試來源。
CHATKEEP_ALLOWED_ORIGINS=https://franksky1207.github.io,http://127.0.0.1:9000
# Host 與 origin 是不同清單；Render 提供 RENDER_EXTERNAL_HOSTNAME。
CHATKEEP_ALLOWED_HOSTS=localhost,127.0.0.1
```

預設跨站清單為空（fail closed），同源請求仍可用。Origin 是 scheme／host／port，不能填 `/chatkeep/` 路徑；GitHub Pages 同帳號其他 repo 共用此 origin，CORS 無法限制到單一 repo path，正式要更細隔離可採專屬網域後重新設定明確 origin。未改 render.yaml 或目前任何 Render 環境設定。

- Host 先驗證；Origin 必須是有效無路徑 HTTP(S) origin，精確比對同源或明確清單。不接受 `null`、萬用字元或子網域模糊匹配。合法 Pages Origin 的 cross-site Fetch Metadata 可通過；無 Origin 的 cross-site 仍拒絕。
- OPTIONS 只放行 POST／Content-Type，204 無本文；錯誤來源、方法、Authorization 等 header 403。不消耗轉換 RateLimit／SLOTS。
- 實際 POST 僅 application/json 或 UTF-8 charset，沿用不接受壓縮／chunked body 的規則，明確拒絕 Cookie／Authorization。
- 合法來源回精確 Access-Control-Allow-Origin、Vary: Origin、Expose-Headers: Retry-After；無 Allow-Credentials、無 `*`、無代理。403／429 等合法來源錯誤也有對應 CORS headers。
- Origin／CORS **不是認證**，非瀏覽器可偽造標頭。保留匿名每 IP 每分鐘 10 次、全域 60 次、SLOTS、Host、請求大小、CPU／AS／wall 與上傳限制，未提高額度。舊 v1 分享端點的同源限制保持不變。

## 多選、資源與下載

逐段有界順序佇列，沒有 Promise.all 大量轉換，不同對話不共用 prepared／manifest／collector。每段獨立成功／失敗／取消狀態；失敗暫停供指定重試或略過，已完成段落不消失。只留一個失敗中的 prepared／collector；重試以原 manifest／nonce 為基礎，只送 collector 尚未驗證的批次，已驗證批次不重新送。

| 項目 | 本批維持／新增界線 |
|---|---|
| 原選取準備 | ≤16,000,000 bytes；單段有界 Worker，不讀取整包備份 |
| 單次上傳／批數 | ≤2,000,000 bytes／最多 16 批，完整訊息邊界 |
| 輸出 | 每段 ≤16 卷／16,000,000 bytes；單 DOCX 優先，分卷才 ZIP |
| 多選成果暫存 | **32,000,000 bytes** Blob 邏輯總量；開始下一段前預留完整 16 MB，超出先暫停 |
| 釋放 | 使用者逐段下載、確認保存後按「釋放此成果」，報告保留；按「繼續佇列」才繼續。沒有跨對話全部 ZIP |
| 發送 | 順序；小型及分享每次起始等候 ≥6.1 秒，大型沿用 sendPrepared ≥6.1 秒／批 |
| 429 | 原次＋最多 2 次自動重試；沿用 Retry-After 2–120 秒政策，後端目前回 2／60 秒；再失敗由使用者重試 |
| 期限 | 前端每 request 55 秒，大型每輪 15 分鐘；後端原 wall 45 秒／CPU 30／31 秒／AS 384 MiB／上傳 10 秒 |
| 回應 | 串流讀取 envelope 最多 24 MB，無 Content-Length 也執行；二進位最多 16 MB |

32 MB 是跨對話保留成果 Blob 的預算，**不是瀏覽器 RSS 上限**。當前 prepared、解碼字串／Base64／UTF-8 buffer、驗證 XML、ZIP 複本與原有索引各有既有界線，仍有暫時記憶體開銷；手機瀏覽器可因記憶體不足停止。已完成 Blob 與失敗中的 collector 分別有總預算，沒有保留全部選取對話的本文或全部 Base64。

新版小型／分享回應必須符合 v2、正確 DOCX／ZIP MIME、合法且有界 Base64、完整報告／卷數／連續訊息範圍。共用 export 報告新增每卷 `file_sha256`（加欄位，不改排版），前端驗證檔案 SHA-256、ZIP CRC、實際 DOCX bookmarks 與 cell 結尾段落後才發佈下載。ZIP 內各卷逐一驗證。大型仍用既有 pinned manifest verifier，所有批次完成才 finish；新增可選 onStage 回呼僅在真的需要 writeZip 時顯示 ZIP 封裝。

報告先顯示標題、來源、訊息數、卷數、類型、成功／警告、略過分類、缺漏與完整性層級，再提供逐段下載。`browser_derived_sequence` 明確不等於官方原始網頁逐字比對，原始統計仍是 client_source_counts。檔名重新安全化並固定擴展名，未知 MIME 不接受。Object URL 僅在按下載時建立，啟動後 1 秒撤銷（瀏覽器沒有可靠的磁碟保存完成事件），取消／清除／pagehide 也撤銷；未宣稱可確認使用者已保存。

## 進度、取消及錯誤

本機掃描以實際 bytes 顯示原有進度；準備只顯示擷取／分支驗證階段，不假造百分比。傳送只顯示批次序號與「Render 正在轉換」，同步 API 不提供內部百分比；之後是真實分卷驗證、必要時 ZIP 封裝、下載就緒。

取消 abort 當前 fetch、停止未開始批次、終止準備 Worker、清除未完成段落的 prepared／collector，不將取消視為成功。取消 extract promise 會移除等待者，已送出的 index Worker Blob.slice 是立即回傳的操作，晚到回應被丟棄；索引 Worker 保留供後續選取，不會開始解析備份。原掃描取消／reset 仍通知並終止索引 Worker、清除 OPFS。取消轉換保留其他已完成成果；另有「清除轉換結果」全部釋放。UI epoch 隔離已清除／新工作，不能讓舊回應覆蓋新結果。

明示限制：瀏覽器取消不能保證同步 Render 子程序立即停止；仍受 45 秒及 CPU／AS 期限約束，短時間可能 BUSY。轉換時鎖住索引／選取操作，使用專用取消按鈕；暫停時可下載釋放、重試或略過，不能平行開另一個轉換佇列。

錯誤顯示保留 code，含 RATE_LIMITED／BUSY、INPUT_TOO_LARGE／CHUNK_TOO_LARGE／MESSAGE_TOO_LARGE／VOLUME_LIMIT／OUTPUT_LIMIT、INVALID_BRANCH／UNSUPPORTED_CONTENT、CONVERSION_TIMEOUT／BATCH_TIMEOUT、MANIFEST_MISMATCH／MISSING_PART 及其他原契約代碼。容量、完整性、來源內容、網路／CORS／未部署、瀏覽器能力有相應可行提示；未知代碼仍顯示 code 與確認來源／服務後重試方式。非 429 不自動重送整段。Worker、WebCrypto、deflate-raw DecompressionStream 缺少時明確停止，不提供未驗證下載。

## 自動化測試（全部合成）

```sh
PYTHONPATH=tests .venv/bin/python -W error::ResourceWarning -m unittest \
 test_pages_cors test_chunk_transfer test_long_conversations test_official_json \
 test_integration test_rich_word test_word_layout test_acceptance test_chatkeep -q
node --test tests/pages_conversion.test.mjs tests/large_transfer.test.mjs \
 tests/large_transfer_worker.test.mjs tests/local_backup.test.mjs tests/local_backup_filters.test.mjs
PYTHONPATH=.:tests .venv/bin/python tests/pages_integration_browser.py
.venv/bin/python tests/local_backup_browser.py
.venv/bin/python tests/official_api_transport.py
```

- 96 個 Python 測試：含 5 個 CORS 整合與既有 91 個後端／排版測試；OPTIONS 三路徑、Pages 明確 origin／核准開發 origin、拒絕來源／Cookie／Authorization／格式、真實跨站轉換、429 可讀 Retry-After、Host／上傳界線、preflight 不消耗配額。原 OPTIONS 的 METHOD_NOT_ALLOWED 回歸改測 PUT，因 OPTIONS 現為正式支援方法。
- 37 個 Node 測試：新增 8 個 Pages controller／transport／download verifier，加既有 28 個原始擷取／篩選／大型傳輸，新增 1 個準備 Worker 崩潰後重啟。覆蓋雙入口選路、小型原 Blob、真正大文字多批、非選取隔離、metadata 排除、批次順序／hash／CRC／bookmarks、DOCX／ZIP、逐段多選、保留成果、指定失敗批重試、429 次數／Retry-After、容量暫停、API 404／版本／MIME／回應大小、網路錯誤、取消 fetch／晚到回應、Worker 崩潰與重啟、ZIP 上限／缺批／混批／損壞。
- 本機 Chromium（系統 `/usr/bin/chromium`，Playwright）整合：真實兩個 HTTP origins、原 index Worker、prepare Worker、真實官方／chunk 子程序及實際 CORS OPTIONS／POST；未選取本文完全不傳、>2 MB metadata 不進衍生封包。原始 JSON 位元組下載、DOCX／ZIP MIME／副檔名下載、完整性報告、實際拒絕 Authorization preflight、模擬斷網、fetch 進行中取消／晚回應後無下載、清除結果通過。分享遠端擷取用合成 DOCX／ZIP envelope 注入；不是 ChatGPT live 或 Render 驗收。
- 原本機備份瀏覽器回歸：JSON／ZIP／OPFS 清理、搜尋選取、預覽、原始 JSON、錯誤檔、桌面與 390／320 CSS viewport 通過；僅將舊「兩個 Render 跳轉」斷言改成新的雙入口按鈕與一個 v1 連結。CSS viewport 不是手機實機。
- 真實本機 Gunicorn：DOCX／ZIP、內容順序、v2 無效 URL、10 秒停滯上傳期限、名額回收及 stdout／stderr 無合成私人本文／標題通過。沒有對正式 Render 發送測試。
- `git diff --check`、Node 語法檢查通過。未新增套件或觸發 Actions。測試成果及私人內容不提交。

## GitHub 交付及未部署限制

本地備妥 `docs/PR_3_DESCRIPTION.md` 作 PR #3 新說明。GitHub 網頁可讀並確認 Draft；目前環境對 `api.github.com` 的請求被網路政策拒絕，`gh pr view/edit` 不能使用。Git fetch／push 經 github.com 另行驗證；最終 commit SHA 與實際推送結果以交付回報為準。若 API 仍受阻，PR 遠端說明未更新，不能將本地備稿宣稱為已更新；允許 api.github.com 後可執行：

```sh
gh pr edit 3 --repo franksky1207/chatkeep --body-file docs/PR_3_DESCRIPTION.md
```

Render 部署仍指 main 且 autoDeployTrigger=off；本批未修改此設定、不部署、不發布 Pages、不合併、不建立 Release。正式 v1.0.0 未被更新。沒有執行與本批無關的 GitHub Actions。

第 7 批仍需由 Chat 做統一介面、隱私告知及安全／操作審查；本批只完成整合必要控制。第 8 批仍需真實官方備份、Safari／手機／桌機、Microsoft Word 直接開啟、Render Free 代理／CORS／CPU／RSS／超時與 Pages HTTPS 全流程實機驗收，通過後才依發布規則合併、手動部署、發布 Pages／Release。本批不提前執行第 7、8 批，完成後等待驗收。
