# 正式環境 OPTIONS 403：診斷與安全修補

日期：2026-10-28 UTC。**尚未定位現場拒絕條件，不能宣稱正式 CORS 已修復。**本批補上必要診斷缺口與 WebKit 回歸，不放寬原有來源／標頭政策。正式端對端驗收仍未完成。

## 基準及已知事實

- 開始前重新 fetch main，最新為 `fdeb7cc2e38fb0e2db1cae690b0db850f51e9e16`，沒有沿用舊分支直接修改。
- 使用者回報正式 Pages https://franksky1207.github.io/chatkeep/ 已上線、Render 已手動部署，且 2026-10-28 14:27:54 台灣時間（06:27:54 UTC）記錄 OPTIONS /api/convert-v2 403。前端 NETWORK_OR_CORS，Render 首頁可開啟。
- 使用者表示設定 `CHATKEEP_ALLOWED_ORIGINS=https://franksky1207.github.io`；本環境無 Render 環境變數讀取／部署權限，**沒有核實正式值或部署 SHA**。
- 06:31:52 UTC，對正式 Render 以正確 Pages Origin、POST、content-type 發出 OPTIONS；執行環境代理在 CONNECT 階段回 403（curl exit 56、envoy），請求無法到達站台。這是本執行環境代理拒絕，不是正式 Render 應用程式的 403，不能驗證現場原因或端點狀態。未繞過網路政策。

## 最高可信診斷

1. 原 server.py 的 OPTIONS 將 Origin、method、headers、credentials 拒絕全部合併成空白 403；除了 Host 檢查，沒有可安全區分的診斷。因此使用者提供的單行 403 **不足以辨認是哪個條件**。缺少可觀察性是本批確認並修補的程式缺口。
2. Pages 是外部明確白名單：`origin == same or origin in approved`。即使 Render 內部 `wsgi.url_scheme=http`，正確的 `https://franksky1207.github.io` 仍可透過 approved 通過。合成 Render Host／外部 HTTPS／內部 HTTP、真實本機 Chromium 及 WebKit 均已驗證。因此不能把 HTTPS 終止當成此次 Pages 403 的已知根因。
3. 既有 same-origin 判定確實使用 WSGI scheme，未設定信任代理時不將任意 X-Forwarded-* 視為 HTTPS。這可能影響其他直接同源情境，但**不能解釋正確 Pages 白名單的跨站拒絕**；本批不為這個推測更改代理信任或白名單。偽造 forwarded host/proto 不能放行非法來源／Host 的回歸通過。
4. 正確設定下，三新路由合法 OPTIONS 均為 204。空值、帶 `/chatkeep/`、尾端 `/`、錯誤來源等設定／請求會被拒絕。這些是假設候選，未核實正式環境有此問題。
5. 現有前端只主動指定 Content-Type，credentials:omit；本機 Playwright WebKit 26.5 與 Chromium 使用**實際 conversion.mjs transport**，皆成功 OPTIONS 204、POST 200、可重新開啟 DOCX。未觀察到額外不合法 Request Headers，不能宣稱所有 iPhone／舊 Safari 都相同，也不能憑猜測放行更多標頭。
6. 不是以冷啟動或 55 秒逾時解釋已到達服務的 OPTIONS 403。正式請求的實際 Origin、Host、Request-Headers 及代理／應用層回應仍未取得。

## 實際變更

- `api_origin.py`：把原有 OPTIONS 條件抽成 `preflight_denial()`，只產生有限代碼；`preflight_diagnostic()` 限定可記錄代碼，沒有接受任意請求字串。
- `server.py`：Host 優先檢查；OPTIONS 403 寫入固定分類安全日誌，回 `X-ChatKeep-Preflight` 固定分類；成功 204 標記 ACCEPTED。拒絕回應維持空本文。原 POST／v1 路由不變。
- `tests/test_pages_cors.py`：新增分類／日誌隱私、尾端斜線、Render HTTPS 終止、WebKit 常見標頭、偽造 forwarded 資訊與錯誤環境設定回歸。
- `tests/cors_browser.py`：實際兩個 origins、現有前端 transport、真實轉換子程序及 DOCX CRC／訊息／報告／重新開啟；Chromium／WebKit 均執行。
- 必要 CI 增加修復分支與 WebKit 相依套件及上述兩個瀏覽器回歸，不執行私人備份或完整裝置驗收。
- Pages 過時的「Render 尚待部署」改為「已由管理員部署，正式跨站轉換仍在驗證中」，未宣稱 Word 轉換完全正常。
- `json_api.py` 與 `conversion.mjs` 已檢查，不需推測性變更。沒有加入萬用 CORS、允許全部 Host／headers、信任任意 forwarded 資訊、放寬 Cookie／Authorization、改動 RateLimit／SLOTS／CPU／記憶體／逾時或將 CORS 當認證。

## 診斷方式與隱私界線

只記錄以下固定訊息，範例：

```text
chatkeep_preflight_denied status=403 code=ORIGIN_FORBIDDEN
```

| 分類 | 意義／處理方向 |
| --- | --- |
| HOST_FORBIDDEN | 應用收到的 Host 未通過既有 allowlist；確認既有服務的 RENDER_EXTERNAL_HOSTNAME／CHATKEEP_ALLOWED_HOSTS 與平台路由，不開放全部 Host |
| ORIGIN_FORBIDDEN | Origin 缺少、不合法或未核准；確認實際活動服務中白名單恰為 https://franksky1207.github.io，無路徑、尾斜線或引號，已儲存並在部署程序生效 |
| PREFLIGHT_METHOD_FORBIDDEN | Access-Control-Request-Method 不是 POST |
| PREFLIGHT_HEADERS_FORBIDDEN | 請求的非簡單標頭不只 Content-Type；先取得安全的標頭**名稱**並重現，不直接全部放行 |
| PREFLIGHT_CREDENTIALS_FORBIDDEN | OPTIONS 自身帶有 Cookie／Authorization；保持拒絕並確認請求來源，前端仍 credentials:omit |

若 Authorization 出現在 Access-Control-Request-Headers 名稱清單，會歸為 HEADERS_FORBIDDEN；若 OPTIONS 本身帶 Authorization 值，歸為 CREDENTIALS_FORBIDDEN。多重違規以 Host → Origin → credentials → method → headers 次序回報第一個條件。

日誌不含任意 Origin、Host、URL／query、分享連結、header 名稱／值、Cookie、Authorization、本文或 traceback。測試確認精確固定字串且只寫一筆。成功請求不新增逐請求日誌。

`X-ChatKeep-Preflight` 可從 Network 或 curl 觀察，不額外暴露給頁面 JavaScript，也不讓被拒絕來源取得 CORS 授權。只回映經核准 Origin；原 Expose-Headers 仍僅 Retry-After。Host／Origin 拒絕沒有 Access-Control-Allow-Origin；已核准 Origin 的其他拒絕及 429 保留精確 CORS。

固定標記與相符應用日誌能確認此新版應用曾執行該拒絕。**缺少標記不能單獨證明是代理 403**：也可能是舊部署、不同服務、標頭被移除；需要部署版本與代理／應用日誌佐證。本批的 CONNECT 403 可由 curl 明確辨識，不能冒充 Render 可觀察性。

## 必要測試

全部只用合成請求與合成對話：

- 99 Python 通過（35.808 秒），含 8 個 CORS 測試、原 v1、JSON／chunk、Word／ZIP 分卷、訊息順序／完整性、限額／資源、取消與錯誤回歸。
- 42 Node 通過（34.866 秒），含原始 JSON／ZIP、選路、真正大型有效文字分批、CRC／hash／bookmarks、取消／重試／容量。
- 8 UI／安全測試通過（28.345 秒）。
- 新真實 Chromium 與 WebKit 跨來源測試：OPTIONS 204、POST 200、原 transport、DOCX 重新開啟與完整性通過。
- 原跨來源 Chromium 整合、JSON／ZIP 本機索引／下載與 Gunicorn DOCX／ZIP／日誌隱私腳本皆通過；分享遠端擷取仍合成注入，非正式分享 live。
- 正確 Pages Origin、三新路由、非法 Origin、`/chatkeep/`／尾斜線、非法 method／header、Cookie／Authorization、HTTPS 代理、Safari 常見 Accept／Accept-Language／Fetch Metadata、403／429 CORS、偽造 forwarded 資訊均覆蓋。
- 本機無 root／sudo，WebKit 初次因缺少 OS libraries 無法啟動；將 Debian 相依套件解壓至 /tmp 並供本機 Playwright 使用後才真正執行測試。未把相依套件或測試產物提交。CI 以標準 install --with-deps 執行，不跳過依賴檢查或測試。Playwright Linux WebKit 不是實體 iPhone Safari。
- `git diff --check` 通過。

## GitHub／部署完成紀錄

修復分支 `fix/cors-preflight-diagnostics`；程式提交 `8beb3c421d9ad8e2e93574f0710f3f0ce32ab7c8`；[PR #4](https://github.com/franksky1207/chatkeep/pull/4)。必要 CI：[40644717335](https://github.com/franksky1207/chatkeep/actions/runs/40644717335) completed/success，包含真正 Chromium／WebKit 與全部必要回歸。報告提交 `b0b9d5acc704e83e52f011de302d0e944ff19bac` 僅新增 Markdown，沒有更改已通過程式。

PR #4 已於 `2026-10-28T06:40:46Z` 合併，GitHub 再讀確認 merged=true；main 合併 SHA 為 `dd53b2047c74d08452d6e7df959b0bfc9a1f1152`。合併後必要 CI：[40645319123](https://github.com/franksky1207/chatkeep/actions/runs/40645319123) completed/success，全部必要步驟通過。合併後 [Pages build and deployment 40645318494](https://github.com/franksky1207/chatkeep/actions/runs/40645318494) completed/success，包含更新後的提示；本環境未直接驗證正式頁面載入。

本完成紀錄更新為純文件提交，交付時最新 main SHA 以本報告的 GitHub 提交及最終回報為準，不更改已驗證執行程式。沒有 force push 或刪除回歸測試。

本批沒有 Render 操作權限，不宣稱已部署。需使用者在 GitHub 完成後：**Render → chatkeep → Manual Deploy → Deploy latest commit**，核對最終 main SHA。可回復基準為修補前 main `fdeb7cc2e38fb0e2db1cae690b0db850f51e9e16`；這是 GitHub 基準，並非已核實的正式 Render 部署 SHA。部署前請保留控制台目前的成功部署 SHA／事件供回復。

## 尚未完成／後續操作

1. 部署診斷版本後從正式 Pages 再試一次，以有限代碼定位真正拒絕條件。若 ORIGIN_FORBIDDEN，先修正或確認活動服務環境設定，不製造額外程式政策變更；若 HEADERS_FORBIDDEN，取得標頭名稱後針對性重現與修復。
2. iPhone 若無 Mac 不必為此擷取完整 Network；可先提供 Render Logs 的上述固定分類一行，**不要提供私人 URL／對話／Cookie／Authorization**。有 Mac 時可用 Safari Web Inspector 查看預檢的 Request-Headers 名稱。
3. 正式 OPTIONS /api/convert-v2 必須實際回 204，且實際 POST 成功產生可驗證 Word，才算正式分享轉換端對端通過；另驗證 JSON／chunk、DOCX／ZIP。**本批正式 OPTIONS／POST 均未驗證，403 根因仍待上述證據。**
4. 若標記與應用日誌均不存在，先核對部署 SHA／路由及代理證據，不能直接判定代理拒絕。
5. 不建立 v1.1.0 Release、不執行真實 440 MB、iPhone／Word 完整實機或大型 Render Free 驗收。
