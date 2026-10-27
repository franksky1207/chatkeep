# 第 1-1＋1-2 批｜分享頁解析、基本 Word 與本機網頁

> 以下為該批當時的施工紀錄；最新集中驗收、修復與限制以 [第 5-1 批](BATCH_5-1.md) 為準。


狀態：**真實來源擷取與本機 Word／網頁流程已實測成功；研究 JSON 逐訊息比對尚未完成，階段 1 完整性 Gate 尚未全數通過。** 不得宣稱全部核對或 MVP 正式驗收完成。

## 本機操作

Python 3.10+：

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

開啟 http://127.0.0.1:8000 ，貼上公開 ChatGPT 分享連結 → 開始轉換 → 查看完整性報告 → 下載 Word。桌機和手機採同一介面；本次僅驗證 Chromium 桌機／手機尺寸，未宣稱 iOS Safari／Android 實機驗收。預設僅綁定 loopback；這是本機驗證伺服器，不是正式部署架構。若從遠端 Codex 環境執行，該環境的 loopback 不是使用者電腦的 loopback，需先取得環境的預覽／轉送能力；本次未發布公共網址。

CLI 原有功能保留，解析器只使用 Python 標準庫：

```sh
python chatkeep.py --url 'https://chatgpt.com/share/<UUID>' > conversation.private.json
python chatkeep.py --html saved.private.html > conversation.private.json
```

CLI 重導是使用者自行選擇存檔；HTTP 轉換不寫入對話 HTML／JSON／Word 或正文日誌。下載 Blob 僅留在目前頁面記憶體，重試或離開時釋放。請勿將真實資料加入 Git；輸出 JSON、HTML、Word 預設忽略，前端 HTML 有明確例外。

## 實際問題與修正

- 舊解析器將 15 筆工具文字計入「可讀訊息」，把多種非文字／推理／隱藏記錄當成空白，無法說明可見數。
- 舊 deferred 實作把任意同號參照當成 promise，沒有依 P tag 辨識，也沒有共享 deferred frame 的全域 positional pool；循環／未知負參照會被靜默換成 null。
- 本版延續原函式與流程，修正 P/E frame／全域參照／Z alias，未知型別、壞參照與不完整資料明確失敗。原文、content、metadata、所有目前分支記錄保留，Word 與網頁共用 [正式模型](MODEL.md)。
- URL 使用完整 HTTPS 主機與 UUID 白名單，禁止 query、fragment、userinfo、port、控制字元及非分享路徑。轉址仍須通過同一白名單，最多 3 次；匿名取得、30 秒 timeout／讀取時間檢查、20 MB 上限、HTML MIME／UTF-8／完整下載檢查，不執行頁面腳本。
- 基本 Word 為原生可編輯文字與角色段落；保留 Markdown、程式碼和 UI 標記，不提前進入第 2-1 批元件排版。
- HTTP 限制 JSON 請求 4 KB、同源／Host 檢查、最多同時 2 件轉換、no-store、CSP；錯誤與中斷不提供成功下載。請求完成即釋放伺服器資料，不保存全文。

## 2026-10-27 真實分享頁結果

指定測試連結匿名取得 HTTP 200，約 6.01 MB HTML，2 段 enqueue 串流；無須 Cookie、登入、付費或繞過存取限制。HTML 長度含每次請求動態資料，並非固定值。

| 項目 | 實測 |
| --- | ---: |
| 目前分支節點（含無訊息根節點） | 1,184 |
| 原始訊息記錄 | 1,183 |
| 其他分支節點 | 0 |
| 原始角色：user / assistant / system / tool | 360 / 767 / 41 / 15 |
| 具有可取得文字：user / assistant / tool | 360 / 372 / 15 |
| 可匯出文字：user / assistant | 359 / 361 |
| 可匯出合計 | 720 |
| 系統／隱藏／內部／工具／工具呼叫 | 41 / 32 / 367 / 15 / 8 |
| 已知解析 issues | 0 |

上述分類之外仍有 1 個 structural 根節點。全部類別合計 1,184，全部有訊息記錄合計 1,183。無已知 issues 不等於已完成完整性驗收。

研究用 JSON 不在環境中，**尚未完成逐訊息比對**。研究的 732 是參考而非程式目標：目前來源可觀察到 1 筆 hidden user、6 筆 hidden assistant 文字、5 筆 assistant code 工具指令；按本版可見定義排除這 12 筆，即與 720 的差額相符。但這只是目前來源的分類解釋，不能冒充與研究 JSON 逐筆核對。另有 3 筆無文字工具呼叫，亦不列入可匯出訊息。

opt-in live check 已對 **1,183 筆來源訊息**逐筆核對 ID、角色、建立時間、原始 content、正規化文字及 SHA-256；目前分支 parent chain 與 linear_conversation 的節點順序相符。這是對**本次取得的來源資料**自洽性檢查，不是研究 JSON 比對，也不是分享頁視覺 DOM 的逐則比對。

實際 Word 約 399 KB，已用 python-docx 重新開啟並逐字核對 720 則匯出訊息與順序；兩種瀏覽器尺寸亦實際下載並重新開啟文件。未在 Microsoft Word／LibreOffice 桌面軟體中人工開啟或逐頁目視檢查，不將其描述成桌面排版驗收。

## 本機驗證指令與結果

```sh
python -m compileall -q chatkeep.py server.py word_export.py tests
node --check web/app.js
python -m unittest discover -s tests -v
# 另外安裝瀏覽器測試工具（不會啟動 GitHub Actions）
python -m pip install -r requirements-dev.txt
python -m playwright install chromium  # 已有系統 Chromium 時不需要
python tests/browser_check.py
# 以下兩項會匿名連線實際公開分享頁；只輸出統計，不保留內容檔案
python tests/live_check.py
python tests/browser_check.py --live
```

瀏覽器測試先尋找 CHATKEEP_CHROMIUM 環境變數或系統 chromium，否則使用 Playwright 已安裝的瀏覽器。測試下載檔會讀取後立即刪除；無截圖及真實 fixture 入庫。

- 靜態檢查：Python 編譯及 JavaScript 語法通過。
- 合成測試：19 項通過，含安全網址／轉址、大小上限、HTTP 錯誤、下載不完整、逾時、deferred／多段／特殊字元、分支與分類、非文字／重複 ID／未完成訊息報告、Word 重開、HTTP 轉換及錯誤回應。
- 大量內容：1,200 則、逾百萬字元合成文件，重開後完整文字與順序相符，無截斷。
- 真實擷取：HTTP 成功與 1,183 筆來源自洽性比對通過；另實測全零 UUID 失效連結，回報無對話資料而不提供文件；研究 JSON 比對未完成。
- Word：真實文件已產生、以文件解析器重開，720 則文字與順序核對通過。
- 網頁：Chromium 1280×900／390×844 都通過「填連結→轉換→報告→下載→重開」；真實連線與合成兩種皆通過，無水平溢出及 JS 例外。
- 網頁失敗情境：錯誤 URL、截斷串流、後端逾時、前端停滯逾時皆顯示錯誤並撤除舊下載；過期／不存在的下載路徑回應 404。

## 保留事項

研究 JSON 比對、分享頁視覺內容逐則核對、其他新式 stream tag 相容性、圖片／元件原生還原、桌面 Word 目視與手機實機測試尚未完成。保持報告 unverified；未知資料不以部分成功冒充完整成功。未啟動正式 Actions、未合併 main、未部署；所有本批變更沿用 feat/share-parser-1-1 與 PR #2。
