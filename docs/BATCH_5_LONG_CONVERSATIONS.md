# ChatKeep v1.1.0 第 5 批：單一 Word 優先與完整訊息分卷

基準：重新 fetch 開發分支及讀取 Draft PR #3，確認最新為 `8abc98f424ea392695f5a7ab794f77c4cabedbb8`；工作目錄乾淨。本批沿用 `feat/local-json-extractor`／PR #3，只完成長對話後端、必要回歸及合成量測。未修改正式 Render、部署設定、Pages／web 前端或 Actions；不合併、部署、發布，不開始第 6 批。

## 1. 容量規則與保留界線

移除 `word_export.py` 對「換行 + < 超過 100,000」的整體拒絕。原規則把字面程式碼的 `<` 與真實 Word 結構視為相同成本，無法判斷實際負荷。

現在兩種來源都使用 `export_limits.py` → `conversation_export.export_conversation()` → `word_export.WordVolume` → 既有 `rich_word.py`／`word_layout.py`。`build_docx()` 是同一個 WordVolume 的單 DOCX 相容介面，沒有第二套排版器。

| 類別 | 第 5 批規則 | 理由／變化 |
|---|---|---|
| 粗略門檻 | 刪除 100,000 換行／`<` 總計拒絕 | 改量測生成的 Word 結構，字面 `<` 不算 XML 節點 |
| 正規化總輸入 | ≤5,000 則、≤5,000,000 Python Unicode 字元 | 保留既有硬上限；JSON 原 2,000 則／100 萬字元改為同一組常數，不再用來源區分 Word 容量 |
| 單則文字 | ≤1,000,000 字元 | 兩種來源一致；JSON 原 10 萬字元改由結構預算配合控制，已有 40 萬中文字元單則測試；不是允許任意 100 萬行 |
| 單 DOCX 結構 | Word 本文子樹 ≤120,000 XML 元素、≤8,000,000 XML bytes、≤5,000 表格儲存格 | 基於下列實測設定的保守工作預算，三者先達者為界；非訊息固定切份／固定字數分卷 |
| 分卷 | 最多 16 卷；只在完整訊息邊界換卷 | 防止小文件固定成本、CPU 及輸出無界累積 |
| 二進位下載 | DOCX 或**整個 ZIP** ≤16,000,000 bytes | 未提高舊下載上限，ZIP 不是每卷 16 MB 後無限制加總 |
| API 請求 | 官方單一 JSON ≤2,000,000 bytes；分享網址請求 ≤4,096 bytes | 傳輸界線與 Word 容量分開；不因核心可處理 500 萬字元就允許整包備份上傳 |
| 官方結構 | 原始 mapping ≤5,000 節點、深度 ≤32、值／key 項目 ≤100,000 | 保留第 4 批驗證、重複鍵／循環拒絕；原始節點不等於輸出訊息 |
| 公開頁輸入 | HTML ≤20 MB、擷取預設 30 秒 | 保留 chatkeep.py，沒有新增任意 URL 擷取 |
| 新版轉換程序 | 384 MiB 位址空間、CPU 軟／硬 30／31 秒、wall-clock 45 秒 | JSON 與新版分享 API 共用；分享的 45 秒包含網路擷取；不延長成無上限 |
| 上傳／舊前端 | Gunicorn 接收本文 10 秒；舊分享串流 85 秒；web 前端 90 秒 | 保留；增加舊串流對真實排版檢查點的取消檢查，未修改 web/app.js |
| 回應 | 新版 IPC／JSON ≤24,000,000 bytes；Base64 文件欄位相容 | 16 MB 二進位約膨脹到 21.34 MB；每卷／全域報告有界，沒有每卷分別 Base64 同時常駐 |
| 並行／速率 | 與原分享共用 SLOTS／RateLimit；既有 Gunicorn 1 worker、1 轉換名額 | 不新增排隊、不提高免費服務並行度；本機未載入該配置時仍最多 2 |

8 MB 指實際本文子樹 UTF-8 XML（移除逐子樹序列化時重複的繼承 namespace 宣告），不把 ZIP 壓縮率當記憶體保證；主 XML 還有約 2 KB 的根節點／namespace 開銷及其他標準 DOCX parts。入卷時預留 16 個元素／8 KB 給卷標題與範圍，完成封裝前再量測。這些是可測試的工作預算，不是宣稱超過界線的所有文件都絕對無法在任何電腦開啟。

## 2. 單檔優先及分卷流程

1. 先驗證正式正規化後的有效輸出序列、總輸入及重複訊息 ID；從空文件依序加入完整訊息，沒有依來源、訊息數或長對話標籤預先固定分份。
2. 每則訊息仍走既有 Markdown、程式碼、表格、UI、繁中樣式與版面核心。量測**新加入的實際 OOXML**：元素數、序列化位元組及儲存格數。用穩定 sibling anchor 追蹤新節點，避免每次掃描所有舊訊息。
3. 渲染過程使用 request-local ContextVar 檢查點，定期檢查已生成結構；大 run 加入前，依實際會建立的 Word break／tab／text 節點檢查；表格建立前檢查實際 rows × columns 儲存格配置。這些是輸出結構，不是重新用原始 `<` 或空白行當一刀切門檻。單個大型配置及整則訊息完成後都有檢查。
4. 每則訊息先套用新表格的既有 polish，包括巢狀 cell 最後必須有段落，再量測。若放不下，撤回該訊息的**全部新增 XML 與 hyperlink relationships**，前面已完成的訊息留在本卷。
5. 若本卷本來為空仍放不下，回 `MESSAGE_TOO_LARGE`，不切開訊息、不降低格式、不重試無限次。否則封裝本卷，再於新卷重試該則完整訊息，最多額外重試一次。
6. 所有訊息都放得下就直接回單 DOCX。只有確認下一則使單卷工作預算超限，才建立 ZIP。檔名先安全化／截長，再附加 `_第1卷.docx` 等序號，避免長標題把卷號截掉；最終為 `_完整對話.zip`。
7. 逐卷產生、驗證、寫入 ZIP，接著釋放 DOCX graph／bytes 並 `gc.collect()`；不保留全部 Word 物件或全部 DOCX 清單。DOCX 已壓縮，所以外層 ZIP 使用 ZIP_STORED，避免重複壓縮 CPU。
8. 限長 BytesIO 在寫入時阻擋超出 16 MB，ZIP、DOCX 全在記憶體，不建私人暫存檔或下載快取。ZIP 關閉後驗證檔名序列、實際卷數與 CRC；只有所有卷與完整性核對成功才回傳，任一失敗不提供部分 ZIP。

### 排版與運算修正

大型 Markdown 表格改為逐列取得 row.cells，避免原本對每格反覆 `table.cell(r,c)` 搜尋整張表。相同 3 張 × 200 資料列 × 3 欄合成資料，舊核心 12.007 秒，現核心含結構量測約 1.164 秒，RSS 約 46 MiB。沒有簡化表格或轉成圖片。

`semantic.py` 的行內反引號改為線性 equal-run 掃描，且用二分搜尋排除行內程式碼中的 UI 標籤；避免超長反引號輸入的正規表示式回溯。未知／不安全標記仍保留原文及既有警告。Word 樣式、清單編號、表格重複標頭、程式碼、超連結、巢狀 UI 及 cell 結尾段落維持共用規則。

## 3. 共用完整性紀錄

每則輸出訊息標題嵌入 `ChatKeepMessage_<全域1-based位置>` Word bookmark。封裝後重新讀 DOCX，檢查 CRC、序列化 bookmark 順序及所有 cell 的最後段落，不只依迴圈計數宣稱成功。

各卷包含 number、安全 filename、first_message、last_message、message_count、正規化序列 SHA-256、docx_bytes 及完成文件的 structure 計數。位置是**正式正規化後有效輸出訊息序列的位置**，不是 mapping 插入順序、節點 ID 或分支外訊息位置。

完整性回報包含：

- source：official_json／share_link。
- raw_node_count：官方 mapping 原始節點數；分享頁只有確實有 mapping 時才填，只有 linear_conversation 時為 null。
- active_path_message_count：有效路徑上 message 記錄數（含被分類略過的訊息）；不與輸出數混用。
- expected_output_message_count／output_message_count、docx_volume_count、volumes。
- skipped_categories、off_branch_node_count、warnings、status。
- complete、truncated、duplicated、missing、sequence_sha256、integrity_basis=normalized_output_sequence。

核對每卷範圍相鄰、各卷訊息數等於範圍、總輸出等於預計輸出；與序列化 bookmark 核對後才 complete=true。雜湊採長度前綴的 id／role／原文 text，避免直接串接歧義。**這不代表與 ChatGPT 網頁／真實備份逐字比對完成**，也不是 Markdown 格式轉換後文字與原始語法字面相同；reference_comparison 仍是 not_performed。

官方 JSON 的 current_node／parent 唯一路徑、隱藏／工具／空訊息及非當前分支規則沿用第 4 批。新版兩種來源遇到不支援可見內容、含糊 text+parts、未完成訊息時明確失敗。格式可安全保留成可編輯原文時才帶 RENDERING_LIMITATIONS 警告成功。

## 4. API 相容性與後續契約

| 路徑 | 請求 | 回應 |
|---|---|---|
| POST /api/convert | 舊 `{"url":"https://chatgpt.com/share/<uuid>"}` | 保留 NDJSON 進度／done／document。正常單 DOCX 不變；report.export 新增共用完整性報告。需要 ZIP 時回 stage=error、code=MULTIPART_REQUIRED，明確提示新版 API，**不把 ZIP 冒充 DOCX 傳給舊前端** |
| POST /api/convert-v2 | 同樣單一公開分享網址 JSON | 一次 JSON envelope，單 DOCX 或多卷 ZIP；只允許原固定 chatgpt.com/share UUID URL |
| POST /api/convert-json | 本文直接一個已選取官方對話物件 | 第 4 批 envelope 增加版本／artifact_type／分卷報告，document 仍為 Base64；單檔仍為 DOCX，多卷為 ZIP |

新版成功範例：

```json
{
  "ok": true,
  "api_version": 2,
  "artifact_type": "zip",
  "mime_type": "application/zip",
  "filename": "文明戰線101_完整對話.zip",
  "document": "<base64 ZIP>",
  "report": {
    "source": "official_json",
    "raw_node_count": 101,
    "active_path_message_count": 100,
    "expected_output_message_count": 100,
    "output_message_count": 100,
    "docx_volume_count": 2,
    "volumes": [
      {"number":1,"filename":"文明戰線101_第1卷.docx","first_message":1,"last_message":59,"message_count":59},
      {"number":2,"filename":"文明戰線101_第2卷.docx","first_message":60,"last_message":100,"message_count":41}
    ],
    "complete":true,"truncated":false,"duplicated":false,"missing":false,
    "integrity_basis":"normalized_output_sequence"
  }
}
```

範例省略 hash／structure／warnings，實際卷界以結構量測為準，不保證一定 59 則。單檔 artifact_type=docx、MIME=application/vnd.openxmlformats-officedocument.wordprocessingml.document；仍使用安全 .docx 檔名。

失敗格式維持 `{"ok":false,"error":{"code":"...","message":"..."}}`，不含 document。保留第 4 批輸入、來源、忙碌及速率代碼，新增／明確區分：

| HTTP | code／意義 |
|---|---|
| 400 | INVALID_JSON／INVALID_URL：分享 JSON 語法或固定公開網址格式錯誤 |
| 413 | INPUT_TOO_LARGE／TEXT_LIMIT／NODE_LIMIT／STRUCTURE_LIMIT：傳輸或官方正規化輸入超限 |
| 422 | INPUT_LIMIT：共用總輸入超限；MESSAGE_TOO_LARGE：單則字元或 Word 結構超限；VOLUME_LIMIT：超過 16 卷；OUTPUT_LIMIT：DOCX／整包 ZIP 超過下載預算；UNSUPPORTED_CONTENT：無法安全還原；INTEGRITY_FAILED：序列／封裝／結構核對失敗 |
| 502 | EXTRACTION_FAILED：無法取得可解析公開分享內容 |
| 503 | RESOURCE_LIMIT：記憶體超限或 CPU 等因素中止工作程序；CONVERSION_FAILED：其他固定安全錯誤 |
| 504 | CONVERSION_TIMEOUT：45 秒 wall-clock，到期 kill／reap 後釋放名額 |

舊 v1 的媒體／未知格式警告行為為相容性保留，原 report 的 partial 與警告不被改寫成「來源完整」。其 export.complete 僅表示**既有正規化輸出序列**核對完成。新版兩端點使用嚴格內容拒絕，不沿用舊 v1 的部分媒體輸出行為。

第 6 批需依 artifact_type／mime_type 建立下載，先展示 report，再解碼 document；**本批沒有改 Pages／web 介面，也沒有加跨站 CORS 或對外下載服務**。舊前端繼續使用 v1，暫時不提供 ZIP 按鈕。

## 5. 資源與隱私

新分享與官方端點共用第 4 批的獨立程序、SLOTS、速率、來源驗證及上傳 watchdog。子程序參數只有模式，網址／對話透過 stdin，stdout 為私有 IPC；stderr 丟棄、core dump 關閉，不記錄本文、標題或完整請求。CPU／位址空間限制不因分卷解除。

記憶體同時主要包含：一份正規化模型、一卷 Word graph／DOCX bytes、有界 ZIP buffer；完成後才為最終二進位產生一份 Base64。parent 接收及 JSON 序列化仍有額外複本，因此下列量測也涵蓋整個 Gunicorn 程序樹，而不只子程序 RSS。

舊 NDJSON generator 關閉時設 stopped，排版檢查點會實際中止處理並回收名額，已用真實 exporter 測試。新版同步 WSGI **不保證即時偵測所有客戶端斷線**；沒有第 6 批取消協定，最遲以 45 秒期限或資源限制結束並 reap。這是已知限制，不能把測試「逾時 kill 成功」說成已驗證所有斷線即時取消。

忙碌時在讀取大型本文之前拒絕，避免佔用資源。實測使用 urllib 同時送第二份 1.4 MB 本文可能在讀到 429 前遇到 BrokenPipe（伺服器已提早回覆並關閉未讀本文）；小型並行探測可收到完整 429 BUSY。第 6 批須保留網路錯誤／重試提示，不應為了保證所有客戶端看見 429 而無限制讀完遭拒絕的上傳。

## 6. 合成量測結果（2026-10-28）

環境：Linux x86_64、Debian 13、Python 3.12.14，AMD EPYC 9V74、可見 3 CPU，cgroup memory.max 8 GiB。**不是 Render Free**。每個核心案例是獨立子程序，實際設定 384 MiB RLIMIT_AS、30／31 秒 RLIMIT_CPU，外部 45 秒 timeout。RSS 為 getrusage.ru_maxrss，包含 fixture 建立及封裝驗證，不能當成整個服務的 RSS 或位址空間上限。

| 案例 | 結果 | wall 秒 | CPU 秒 | 峰值 RSS MiB |
|---|---|---:|---:|---:|
| 20 則／60 萬字元中型文字 | 單 DOCX | 0.178 | 0.176 | 30.8 |
| 5,000 則短訊息 | 單 DOCX | 9.864 | 9.863 | 54.5 |
| 20 則程式碼，200,000 個字面 `<`，舊粗略計數超限 | 單 DOCX | 0.110 | 0.110 | 28.2 |
| 100 則／100,000 行 | ZIP、2 卷，100 則核對完成 | 1.485 | 1.483 | 72.7 |
| 10 張表，每張 200 資料列 ×3欄 | ZIP、2 卷，10 則核對完成 | 3.553 | 3.546 | 82.1 |
| 4,000 個程式碼區塊、20 則 | 單 DOCX | 4.637 | 4.637 | 62.4 |
| 4.8 百萬字元文字、80 則 | 單 DOCX，本文 XML 約 6.42 MB | 1.072 | 1.071 | 56.0 |
| 4.8 百萬較難壓縮的合成英數字元 | 單 DOCX，3,660,389 bytes | 1.175 | 1.172 | 51.5 |
| 英數文字＋大量換行 | ZIP、2 卷，3,109,620 bytes | 2.101 | 2.098 | 87.6 |
| 單則 80,000 行程式碼 | MESSAGE_TOO_LARGE，無部分文件 | 0.056 | 0.052 | 30.8 |
| 超過 16 卷所需的訊息序列 | VOLUME_LIMIT，無部分 ZIP | 12.103 | 12.090 | 72.6 |
| 單則表格 2,000 資料列 ×3欄 | MESSAGE_TOO_LARGE，配置前拒絕 | 0.018 | 0.017 | 25.7 |
| 99,999 個反引號＋UI 文字 | 單 DOCX，無 regex 回溯失控 | 0.046 | 0.042 | 27.3 |

最大成功卷量測：118,610 元素；多卷較難壓縮資料峰值約 87.6 MiB；沒有同時保留所有 DOCX。這些結果支持 120,000 元素／8 MB XML／5,000 cells 的工作預算，保留模型、解析、封裝、Base64 與服務程序開銷的餘裕，而不是取消資源限制。

核心 4.8 百萬字元與 5,000 則測試**不是**宣稱可以通過 2 MB 官方 JSON 傳輸限制；它們驗證共用 Word 核心。以下另有真實 HTTP 傳輸量測。

### 本機 Gunicorn 程序樹／高負載

`tests/long_service_stress.py`：使用現有 Gunicorn 配置，送 1,416,036 bytes 的合成官方 JSON（100 則），實際得到 2 卷 ZIP／100 則，695,252 bytes 二進位、927,004 Base64 字元。最終量測 wall 約 2.356 秒，Gunicorn master＋worker＋converter 的 RSS 加總基線 44.1 →峰值 **125.5 MiB**，每 10 ms 讀 `/proc`，共享頁可能重複計算且可能漏掉極短峰值。實際 HTTP envelope 928,387 bytes（約 0.93 MB）；不是只計算壓縮 DOCX 大小。

同時第二個小型請求收到 429 BUSY；之後單則結構過大收到 422 MESSAGE_TOO_LARGE，再轉短對話成功，驗證名額回收。stdout／stderr 沒有合成私人標題／本文。另在 `official_api_transport.py` 真實驗證 DOCX、ZIP、卷數／每則唯一文字、v2 非法 URL、10 秒停滯上傳回 408、釋放後重用及日誌隱私。

### 自動化驗證

```sh
PYTHONPATH=tests .venv/bin/python -W error::ResourceWarning -m unittest \
  test_long_conversations test_official_json test_integration test_rich_word \
  test_word_layout test_acceptance test_chatkeep -q
.venv/bin/python tests/long_export_stress.py
.venv/bin/python tests/long_service_stress.py
.venv/bin/python tests/official_api_transport.py
.venv/bin/python tests/production_check.py
```

85 個必要單元／整合測試（第 5 批專屬 19 個）全通過，最終一輪 12.618 秒；ResourceWarning 視為錯誤。涵蓋單檔優先、實際分卷、CRC／卷數／範圍／唯一文字順序／hash／bookmark、單則與總輸出超限、封裝中途失敗、core 取消後 ContextVar 復原、實際 legacy disconnect 回收、真實子程序逾時 kill／reap／關閉 pipes、真實 384 MiB AS 下的記憶體配置失敗安全回應、縮短至 1 秒的 CPU hard-limit 終止測試，以及既有分享連結／排版／安全回歸。CPU 測試縮短期限以避免測試本身耗滿 30 秒，不能宣稱是實際滿載 31 秒測試。

不使用私人的真實備份；沒有提交合成 DOCX／ZIP、暫存輸出或內容日誌；沒有執行 GitHub Actions 或無關瀏覽器測試。

## 7. 未驗證與免費方案風險

- 真實備份、iPhone Safari、桌機／手機、Microsoft Word 直接開啟及正式 Render Free 的 CPU／RSS／反向代理行為留第 8 批。現階段是 DOCX 重新開啟、OOXML 結構與既有排版回歸通過，不冒充實機驗收。
- Render Free CPU 排程可能比本機慢很多；5,000 則或表格密集案例可能先觸及 45 秒 wall-clock。分卷控制記憶體與單文件結構，不能消除整次轉換的總 CPU 成本，超時仍明確失敗。
- 384 MiB 是子程序位址空間，不是整個 512 MB 服務硬上限。本機觀測約 126 MiB RSS 程序樹不能保證所有格式、來源解析或 Render 平台皆相同；保留單一並行、總輸入、總輸出及 CPU 限制。
- 新版分享端點的網路／擷取總 wall-clock 亦為 45 秒，可能比舊 85 秒串流更保守；沒有為長文盲目延長期限。新版 share 的成功路徑使用合成擷取模型與既有 HTML parser／network regression 測試，未對正式 ChatGPT／Render 做 live 轉換。
- 非 Gunicorn WSGI 宿主的上傳期限仍須由宿主提供；新版同步請求取消不是即時協定；早期拒絕大型上傳可能顯示傳輸錯誤。這些未被宣稱已完整解決。

本批完成後保持 Draft，等待使用者確認；第 6 批尚未開始。
