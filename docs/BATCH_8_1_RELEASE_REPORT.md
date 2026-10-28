# ChatKeep v1.1.0 第 8-1 批發布報告

日期：2026-10-28 UTC。結論：**本機最低合成驗收通過；正式部署關卡受阻，未發布。**

依本批使用者提前發布授權進行準備，但遵守「必要的部署操作權限不足」停止條件。沒有合併 main、操作 Render、啟用 Pages、建立 tag 或 Release。以下不將本機證據當作正式環境證據。

## 最新 GitHub 與環境證據

- 開始時重新 fetch main 與開發分支；結束前以 `git ls-remote` 再確認：main 為 `151a1eb619c32e3f62c69fc0b1a512bac9fd7337`；開發基準為 `4126c60b908c2ef318b4caa66587bef583e952e5`。本批提交位於該開發基準之後，確切 SHA 見 Git 歷史及交付回報。
- GitHub 連接工具即時讀取 [PR #3](https://github.com/franksky1207/chatkeep/pull/3)：open、draft=true、merged=false、mergeable=true。沒有因本批改變狀態。
- GitHub repository API 即時回傳 `has_pages=false`、`homepage=null`、default_branch=main。尚無可確認真正可開啟的正式 Pages 網址；`https://franksky1207.github.io/chatkeep/` 只是預期候選，不能稱為已發布網址。
- GitHub releases API 只列出 [v1.0.0](https://github.com/franksky1207/chatkeep/releases/tag/v1.0.0)。這不能證明 Render 正在執行相同版本。
- cloud-environment-runtime 狀態：observations_current=true、網路政策 enforced/restricted、secrets/runtime_variables/outbound_identities 均為空；沒有可用 Render 操作工具或配置憑證。
- 05:50:43、05:50:49 UTC，分別對 `https://chatkeep.onrender.com` 與候選 Pages URL 執行 `curl -I --max-time 20`；兩者均在環境代理 CONNECT 階段回 403、curl exit 56。**不是站台 HTTP 回應，不能推斷站台故障、路由 404 或測試通過。**未繞過網路政策。

## 已閱讀與設定變更

已閱讀本批指定計畫、第 5-1／6／7 批文件、render.yaml、site-config.mjs、server.py、api_origin.py，另檢查 Gunicorn、JSON API 受限程序與必要測試。

- `docs/local-backup/site-config.mjs` 預設改為 `https://chatkeep.onrender.com`。不含 token、query 或私人內容；開發覆寫仍只存分頁記憶體，保留 HTTPS／loopback HTTP 驗證。
- 必要設定測試更新為正式 HTTPS 預設；UI 測試先驗證預設再明確清空，繼續驗證未設定服務的錯誤流程，沒有為通過而移除測試。
- 不修改本機 JSON 索引／擷取、CORS 政策、Host allowlist、速率／資源限制或正式環境。因尚未確認 Pages 實際來源且無 Render 權限，沒有冒稱已套用 `CHATKEEP_ALLOWED_ORIGINS`。
- 前端既有 API_UNAVAILABLE／NETWORK_OR_CORS 明確錯誤保留；本機 JSON 功能不依賴後端可用性。仍保留未發布文案，待正式關卡完成後再調整。

## Render 部署前程式庫審查

| 項目 | 審查結果／證據界線 |
| --- | --- |
| GitHub repo／部署分支 | repo 是 franksky1207/chatkeep；render.yaml 宣告 main，實際控制台 repo／branch 未能核實 |
| 方案／部署方式 | yaml 為 Python runtime、plan=free、autoDeployTrigger=off；沒有建立新 Blueprint、提高額度或變更方案 |
| Gunicorn | 1 worker、gthread 8 threads、1 轉換名額；timeout/graceful_timeout=100，無 access log、warning error log |
| 新 API 限制 | 每次 2,000,000 bytes；接收 10 秒；轉換 wall 45 秒、CPU 30/31 秒、AS 384 MiB、core dump=0 |
| 匿名配額 | 每 IP 每分鐘 10、全域 60；原 SLOTS 與 Host 檢查保留，未信任任意轉送 IP |
| 新 API／隱私 | 三個路由存在於候選程式；子程序僅有界 stdin/stdout，不保存私人檔案或本文日誌；Gunicorn 合成隱私測試通過 |
| 舊 `/api/convert` | 保留原同源 NDJSON／DOCX 契約，必要 Python 回歸通過；公開分享 live 未完成 |
| 正式版本／路由 | 無 Render 部署 SHA、部署事件、環境變數證據；不能確認仍為 v1.0.0，也不能確認新版已存在 |

以上資源限制符合既有免費優先設計，**不是 Render Free 實際 CPU／RSS／並行／冷啟動驗收**。

## 本批實際測試（全部合成資料）

所有以下命令 exit 0；未使用私人備份，未把文件／截圖／對話測試成果提交至 GitHub。

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
.venv/bin/python tests/official_api_transport.py
git diff --check
```

| 必要項目 | 本機證據 | 正式環境 |
| --- | --- | --- |
| 首頁／JS／CSS、雙入口 | Chromium 首頁與雙頁籤／鍵盤測試通過 | Pages 未發布，未通過 live |
| JSON 索引／搜尋／原始下載 | 365 筆、選取、JSON／ZIP、CRC、OPFS、精確原始 bytes 回歸通過 | 未發布驗證 |
| 分享 API 選路 | `/api/convert-v2` 選路與 envelope DOCX／ZIP 通過；遠端擷取注入合成回應 | 無安全可重複分享來源，未完成 live |
| 小型 JSON | 真實子程序及跨來源 HTTP `/api/convert-json` 通過 | 未驗證 |
| 大型分批 | 真正有效大文字多次子程序請求、全域順序／hash／bookmarks／ZIP CRC 通過 | 未驗證 |
| CORS | 三新路由 OPTIONS 204；合法 POST、非法 Origin／Cookie／Authorization 403、Host／配額保留、429 可讀 Retry-After 通過 | 未配置／未驗證 |
| DOCX／ZIP | 瀏覽器實際下載；Gunicorn 產物重新開啟、ZIP 解壓逐卷、連續範圍／數量／hash／bookmarks 檢查通過 | 無正式下載證據；不是 Microsoft Word 桌面驗收 |
| 完整性報告 | 來源層級、批次層級、卷序／訊息序、混批／缺批／損壞拒絕通過 | 未驗證 |
| 取消／錯誤 | abort、Worker 取消／重啟、晚回應不發布、網路錯誤、重試通過 | 未驗證 |
| v1 相容／隱私 | 舊端點回歸、Gunicorn 日誌無合成本文／標題、10 秒停滯上傳與名額重用通過 | v1 分享 live 未驗證 |

結果：96 Python（54.803 秒）、42 Node（52.773 秒）、8 UI／安全（49.790 秒）通過，另原 JSON 瀏覽器、跨來源瀏覽器與 Gunicorn 傳輸腳本通過。測試共用本機資源，耗時不是正式效能數據。修改測試名稱後再次跑 presentation 5 測試通過。

GitHub Actions：讀取目前完整 runs 清單共 3 筆，最新成功是 [40495455980](https://github.com/franksky1207/chatkeep/actions/runs/40495455980)，SHA `7f93038f6d271c93f603df25f399b57317a25ed2`，屬舊分支，**不能算此次候選已通過**。開發基準 SHA 的 PR workflow runs 為空。本批未觸發 Actions，現有連接工具無 workflow dispatch 能力；部署受阻時不啟動無關舊 live／視覺工作流程。候選版本必要 CI 仍未完成，不豁免發布關卡。

## 停止位置與接續操作

停止於合併／部署前。需要具備 Render 操作權限的管理者與允許正式網域連線的環境接續：

1. 開放測試環境存取 chatkeep.onrender.com、franksky1207.github.io；若用 GitHub CLI 操作 CI／Pages，另需 api.github.com。以正常設定流程更新，不繞過代理。
2. Render 控制台確認既有服務 repo、main 分支、Free 方案、實際現行部署 SHA／版本與手動部署方式。保留原 Host allowlist、所有資源／配額及無本文日誌設定。
3. GitHub Settings → Pages 確認將使用 main 的 `/docs` 與實際網站來源／自訂網域；目前 has_pages=false。若來源確為 https://franksky1207.github.io，Render 設 `CHATKEEP_ALLOWED_ORIGINS=https://franksky1207.github.io`，不含 path、不使用萬用字元，不加入 token／credentials。先確認實際來源再套用。
4. 重新取得候選最新 SHA，完成僅必要的候選 CI 與部署前驗收；確定 Render 可操作後才將 PR #3 ready 並合併，記錄合併 SHA。保持自動部署關閉，依現有方式手動部署該 main SHA，取得 Live 部署事件與 commit 證據。
5. 檢查三新端點實際 OPTIONS／POST，舊 v1 同源行為及 CORS 拒絕／429。路由 404 必須失敗；無效輸入回 4xx 只能證明路由存在，不能代替成功產物驗收。
6. 發布 main `/docs`，記錄 GitHub Pages 實際部署 URL、SHA、資源 HTTPS 狀態；從該正式頁面，以合成小型／大型有效 JSON 驗證 Render、DOCX／ZIP 下載與每卷完整性、取消／錯誤。公開分享來源不足時標示 live 未完成，不能捏造。
7. 正式必要驗收失敗即停，不建立 Release；修復後重驗。只有全部必要關卡通過才建 v1.1.0。

目前 main／正式服務未由本批改動，不需要回滾。後續若已合併但部署失敗，先停止 Pages／Release；保留先前 Render 成功部署 SHA 與日誌，依既有服務方式回復上一個已驗證部署，必要時用 revert PR 修復 main（不 force push、不關閉保護）。各環境實際版本須重新核實記錄。

## Release 說明備稿（未建立 Release）

正式驗收完成後才可使用以下發布內容：GitHub Pages 主網站正式上線；公開分享連結與官方備份雙入口；本機大型 JSON／ZIP 索引、搜尋與選取指定對話；DOCX／ZIP 自動分卷；大型選取對話有界分批傳輸；完整性驗證與隱私保護。

容量：每個已選原始對話最多 16 MB／5,000 節點；每次上傳 2 MB、最多 16 批；有效輸出最多 5,000 訊息／500 萬字元、單則 100 萬字元；每段最多 16 卷／16 MB，佇列成果保留預算 32 MB。完整訊息無法放入一批或一卷時明確失敗；Render Free 可能冷啟動、忙碌或逾時，取消不能保證後端立即停止，不承諾無限容量。

仍待補驗：真實官方備份／440 MB、iPhone Safari／實體裝置、Microsoft Word 桌面版、大型 Render Free 的實機負荷／CPU／RSS／代理與冷啟動。所有 live 缺項必須於真正發布時依實際進度更新；本備稿不表示 Pages／Render 已上線。

## 本批交付狀態

- PR #3 未合併；main 最新為上述 `151a1eb…`。
- Pages：未發布，沒有可回報已可開啟的正式網址。
- Render：既有使用者提供網址 https://chatkeep.onrender.com；版本與部署狀態無法核實，本批未部署。
- CORS：本機政策驗證通過；正式環境變數未設定／未核實。
- 三新版 API、v1、DOCX／ZIP：本機合成驗收通過，正式 live 未完成。
- Actions：此次候選未執行必要 CI；舊成功不替代。
- v1.1.0 Release：未建立，沒有 Release 連結。
- 本批到此停止，不執行完整第 8 批實機驗收。
