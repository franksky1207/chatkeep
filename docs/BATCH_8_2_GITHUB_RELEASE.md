# ChatKeep v1.1.0 第 8-2 批：GitHub 合併與 Pages 發布

日期：2026-10-28 UTC。結論：PR #3 已合併；必要本機驗收及候選 Actions 通過。Pages 未啟用，需使用者操作 Settings。本批未部署 Render、未變更其環境變數、未建立 Release。

## GitHub 基準與合併證據

- 重新 fetch main 及 feat/local-json-extractor，並取得 PR #3 最新資料。開始時 main 為 `151a1eb619c32e3f62c69fc0b1a512bac9fd7337`；開發分支為 `34a3ca6781f70c052e2f6c5ac150228390d0ac20`，包含第 1～7 批及第 8-1 批已提交修改。
- 新增必要合成 CI：`d3723db314e454a35d800d500c7cd0ce334fcd0a`。
- 首頁補上「新版 Render 尚待手動部署及正式跨站驗證，Word 轉換可能暫時無法使用」，並修正過時的預設 API 說明：`d5a777744d35acae278b71c405d6c5451b93fe93`。
- 必要測試與候選 Actions 成功後，將 [PR #3](https://github.com/franksky1207/chatkeep/pull/3) 從 Draft 改為 Ready for review，更新說明，再以 expected_head_sha 固定上述候選執行 merge；沒有 force push、刪除歷史或略過保護。
- GitHub 回傳 merged=true；重新讀取 PR 確認 closed/merged=true，merged_at=`2026-10-28T06:10:23Z`。
- main 合併 SHA：`33a9ef56854f24abd26229438ec48895e08085d9`。重新讀取 main 確認指向此 SHA。
- 合併 commit 與已通過候選的 tree SHA 同為 `f31c4d33d40a13399d02a8629a9c1da7c938a3fe`，沒有混入未驗證程式。
- 本報告後續另以純文件提交加入 main，因此交付時 main 最新 SHA 為本報告所在的提交（完整值見 GitHub file history 與交付回報）；該提交只新增本報告，不改變上述已驗證執行程式。Render Deploy latest commit 應核對交付回報的最新 SHA。

## 程式與隱私檢查

- `DEFAULT_API_BASE=https://chatkeep.onrender.com`，使用 HTTPS，不含 token、query 或私人內容；保留安全開發覆寫。
- 三新版路由 `/api/convert-v2`、`/api/convert-json`、`/api/convert-chunk-v1`、共用 Word 核心、分批協定及 api_origin.py 均納入。
- 原 `/api/convert` 保留，舊 web/ 前端相對原 main 無差異；合成相容性回歸通過。
- 完整 tracked tree／開發歷史／diff 審查未見私人備份、DOCX／ZIP／PDF／截圖／trace、.env／key 等產物被追蹤；常見 private key、GitHub token、AWS access key、OpenAI key 格式掃描無命中。這不是任意形式秘密的絕對證明。
- 測試使用執行時生成的合成資料，未提交對話或產物。未降低 Host allowlist、精確 CORS、Cookie／Authorization 拒絕、RateLimit、SLOTS、CPU／記憶體／逾時限制。

## 本批必要本機測試

全部 exit 0：

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

- 96 Python 通過（43.478 秒）：新舊 API、CORS、非法 Origin／Cookie／Authorization、429 Retry-After、Host／速率／資源限制、Word 順序與完整性、取消／錯誤。
- 42 Node 通過（38.996 秒）：JSON／ZIP 索引、搜尋、原始 bytes、小型／大型選路、有效文字真實分批、hash／CRC／bookmarks、混批／漏批／損壞拒絕、重試／取消與有界成果。
- 8 UI／安全測試通過；首頁提示更新後再次 8/8 通過（25.233 秒）。涵蓋雙入口、正式 HTTPS 預設、服務錯誤、搜尋、XSS、焦點與窄畫面。
- 本機 Chromium 跨來源整合通過：真實 OPTIONS／POST、Workers、只送選取資料、原始 JSON 與 DOCX／ZIP 下載、網路錯誤／取消。公開分享遠端擷取注入合成回應，未冒充 live。
- 原 JSON／ZIP 瀏覽器回歸通過：365 筆、精確 bytes、CRC、OPFS 清理、損壞／儲存權限處理；無未捕捉錯誤及外部請求。
- Gunicorn 實際 HTTP DOCX／ZIP、重新開啟與逐卷完整性、v2 無效 URL 拒絕、上傳期限、名額重用、日誌無合成本文／標題通過。不是 Render Free 實測。

## GitHub Actions

新增 `.github/workflows/release-checks.yml`，contents:read 權限，只跑上述必要合成 Python／Node／Chromium／Gunicorn，沒有觸發舊完整 live／Word PDF／WebKit 工作流程，也不存取 secrets 或上傳測試成果。純 Markdown 更新不重跑。

- 候選 `d5a777744d35acae278b71c405d6c5451b93fe93`：[40641850684](https://github.com/franksky1207/chatkeep/actions/runs/40641850684)，completed/success；成功後才合併。
- 較早 `d3723db…` 的 [40641778818](https://github.com/franksky1207/chatkeep/actions/runs/40641778818) 因首頁更新，由同分支 concurrency 取消。沒有跳過失敗測試，未引用舊分支成功冒充候選通過。
- 合併 main 的 [40642253070](https://github.com/franksky1207/chatkeep/actions/runs/40642253070)：completed/success，全部必要步驟通過；本報告純文件提交不重跑相同程式驗收。

## Pages 實際狀態及停止原因

GitHub repository API 回傳 `has_pages=false`。目前 **未啟用／未發布，沒有可確認真正可開啟的正式 Pages URL，也沒有 Pages 部署成功證據**。

目前 GitHub 連接工具沒有 Pages Settings 寫入能力；github_fetch 不接受 Pages endpoint。CLI `gh api repos/franksky1207/chatkeep/pages` 被環境網路政策回 Forbidden（api.github.com 未在白名單）。repository metadata 的 admin=true 不能證明目前工具可以執行設定。其後本機環境轉為 unavailable，因此改用 GitHub 連接工具完成報告與狀態確認。未繞過政策，也未改用 Actions 部署取代指定模式。

需要使用者操作：

1. 開啟 https://github.com/franksky1207/chatkeep/settings/pages 。
2. Build and deployment → Source 選 **Deploy from a branch**。
3. Branch 選 **main**，Folder 選 **/docs**，按 Save。
4. 等待 Pages build/deploy 成功，記錄 Settings 顯示的真正網址及部署 SHA；從該 HTTPS 網站驗證資源與功能。

`https://franksky1207.github.io/chatkeep/` 只列為預期候選，不當成已發布網址。環境網路也未允許 franksky1207.github.io；本機首頁／CSS／JS、雙入口、JSON 索引／下載通過不能代替正式 Pages 驗證。依使用者「無權操作 Pages Settings 即停止該步驟並回報」規則停在此處。

## Render 留待手動部署

使用者回報已儲存 `CHATKEEP_ALLOWED_ORIGINS=https://franksky1207.github.io`；本批未操作環境變數，也未驗證其正式生效。未自動部署 Render。

由使用者在 GitHub 操作完成後執行：**Render → chatkeep → Manual Deploy → Deploy latest commit**，核對 main 最新 SHA（本報告文件提交，完整值見最終交付）。服務網址 https://chatkeep.onrender.com；沒有本批 Render Live 部署事件／版本證據，不將 GitHub 合併視為 Render 已更新。

## 發布後仍需驗收

- Pages 的實際 HTTPS URL、main /docs 來源、部署 SHA、首頁與 CSS／JS、雙入口、本機 JSON 索引／下載及 API 預設。
- Render Live commit、新版三路由與原 v1 相容；從真正 Pages 測 OPTIONS／POST、合法／非法 Origin、Cookie／Authorization 拒絕與 429 Retry-After。
- 合成小型官方 JSON → DOCX、大型有效 JSON → 有界分批 → ZIP，實際下載／重開／解壓每卷，核對訊息序與完整性報告、取消／錯誤。
- 公開分享 live 需要安全可重複來源；不足時明確未完成，不捏造。
- 本批沒有 Pages ↔ Render 正式端對端成功證據。全部必要正式驗收通過後，才另行建立 v1.1.0 Release。
- 真實 440 MB 官方備份、iPhone Safari、Microsoft Word 桌面版、大型 Render Free CPU／RSS／冷啟動與實機負荷仍待完整第 8 批補驗。本批不執行。
