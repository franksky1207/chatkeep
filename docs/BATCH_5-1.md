# 第 5-1 批｜集中整合驗收與發布前評估

2026-10-27（台北）。沿用 `feat/share-parser-1-1`／PR #2，起點為遠端最新 `e384d5db6b6d13752ffa86aec936df150debad59`。本文件集中記錄現役驗收；前批文件為施工時的歷史狀態。

**實作及本機驗收已進行；不能宣稱正式發布條件全部通過。** 研究 JSON、分享頁視覺 DOM 逐則比對、iPhone 真機與外部部署驗收尚缺。本批不合併、不發布、不啟用付費資源、不進入 5-2。Actions 的實際執行結果／run URL 與最終 SHA 記錄於 PR #2／Issue #1，不能將本機通過當作 Actions 通過。

## 架構與修復

正式資料流維持單一路徑：`chatkeep.extract_url` → JSON v1.0 → `semantic` → `rich_word` → `word_layout`／`word_export` → `server.application` NDJSON → 同一套網頁。原始 content／metadata 不被閱讀版改寫；`rich=False` 仍可逐字核對。

| 實際問題 | 修復與驗證 |
| --- | --- |
| `<text>` 有 children 卻只讀空的 node.text | 展平子節點；補巢狀與自閉合 value 測試，正文各出現一次 |
| HTMLParser 將普通標點拆成多段，Word 每段另起段落 | 合併相鄰原文 token，保留 `<&>`、tab、中文與特殊字元 |
| JSX `{…}` 屬性／事件中的 `>` 干擾解析，整段 UI 退回工程文字 | 以括號／引號詞法掃描處理已知標記，不執行任何表達式；版面／事件屬性不輸出，動態文字屬性與未知格式保留並警告 |
| 真正 inline code 或長圍欄內的標記可能被當 UI | 保護行內 backtick 及同種類、足夠長度的 closing fence |
| 外層 box 展平使巢狀 row／card 喪失原生結構 | 遞迴以原生儲存格／段落呈現；獨立 OOXML 讀取器遞迴驗證 |
| 單欄 row 展平成帶大量縮排換行的巢狀儲存格 | 保留子節點文件流。真實 PDF 曾少 6 個中文字；修正後 573 頁中文字覆蓋通過，未降低檢查標準 |
| 同一列無條件 cantSplit、只整理外層表格 | 長卡片允許跨頁；遞迴整理巢狀表格、頂端對齊、固定可用欄寬，Markdown 表頭重複 |
| 前言後表格未辨識、escaped pipe 被拆欄、明示清單編號被重設 | 修正表格邊界／pipe 分割，保留原始 5.／9. 等數字 |
| 含 LINE 的整段 prose 都可能變泡泡 | 只按明確 LINE 前綴辨識，保留姓名、時間、左右位置；普通冒號 prose 不誤判 |
| 媒體與語義 parser 警告被丟棄 | 加入文件、API rendering_warnings／rendering_status；結果明示部分格式未完整還原 |
| 解析尚未處理節點就上報、未知下載總量只更新一次、Zip 已存好才說封裝 | 真實處理後計數；未知總量仍回報實收 bytes；pack 在實際 save 前發出，無百分比 |
| 取消後作業仍可能持續、HTTP 執行緒未限制 | 單一 WSGI app、有限 queue／轉換槽／本機 HTTP 執行緒、取消檢查、真實工作退出才釋放槽 |
| 檔名只處理完全相等的 CON，長 Unicode 可能切斷 surrogate 或超過檔案系統限制 | 保留名稱含 .txt 仍防護，100 codepoints／200 UTF-8 bytes 上限，固定 .docx；連續下載雜湊不變 |
| 直接連線僅檢查主機名稱，未防 DNS 指向私網 | 無 HTTPS proxy 時檢查所有解析位址為公開 IP，使用已驗證 numeric sockaddr 建連線並保留原主機 TLS 憑證驗證，避免再次 DNS 解析 |
| 原 workflow 未安裝 Word 相依，無法驗證後續批次 | 沿用同一路徑，改成單一手動整合工作流程，安裝一次相依並快取 pip／瀏覽器；沒有 push／PR 自動觸發 |

## 本機測試證據

| 層級 | 結果與限制 |
| --- | --- |
| 靜態 | Python compileall、JS 語法、git diff whitespace 通過 |
| 合成單元／HTTP／安全／Word 回歸 | 49 項通過，包含真實缺字根因的回歸案例，不以刪功能或改成包含少量字詞取代驗收 |
| 元件／內容 | box、row／col、text、caption、巢狀卡片、Markdown 標題／清單／表格／引用、程式碼、LINE 左右／時間／姓名、靜態選項、未知元件／圖片警告均有合成核對 |
| 短／中／長 Word | 4、100、1,000 則：重新讀取後所有唯一正文標記及順序一致，原生可編輯文字／表格，非截圖 |
| 實際渲染 | LibreOffice Writer 25.2 輸出 PDF：4 則 2 頁、100 則 10 頁、1,000 則 92 頁；400 行長卡片 9 頁；180 列表格 5 頁，全部合成標記可取得 |
| 目視 | 檢視合成範例頁：A4、繁中、原生巢狀欄位、聊天泡泡、引用、程式碼、頁碼與警告。沒有宣稱人工逐頁看完長篇或在 Microsoft Word 開啟 |
| 效能 | 獨立本機程序 4／100／1,000 則約 0.05／0.12／0.88 秒，程序峰值約 53 MiB；不是 Render 免費 0.1 CPU 的效能承諾 |
| 瀏覽器 | Chromium 與 WebKit 各驗證 1280×900、390×844、320×740，含合成及真實分享連結；無水平溢出、JS 例外或遮擋，非 iPhone 真機 |
| 操作與進度 | 逐事件比對 API current／total／percent 與 DOM；僅當前階段，未知大小／pack 無百分比，真正完成才出現檔名／下載 |
| 檔名與重試 | 中文、英文、保留裝置名含副檔名、長 Unicode、留空預設、連續下載、重新轉換；同份 Word 雜湊不變 |
| 失敗 | 非法 URL、403／404 合成回應、真實失效全零 UUID、下載大小／不完整、壞 stream／deferred、未知格式、XML 控制字元、前後端逾時、中止、過大瀏覽器回應、忙碌／速率限制均有明確處置 |
| 正式 HTTP 執行方式 | 本機 Gunicorn 實際提供首頁、拒絕非法 URL、串流真實轉換並下載 720 則 Word；敏感測試哨兵及分享路徑未出現在伺服器輸出 |

## 真實來源、720／732 與 Word

指定公開分享連結匿名 HTTP 200，約 6.01 MB、2 段 enqueue；未使用 Cookie、GPT Export、登入、付費服務或存取限制繞過。

- 1,184 個目前分支節點：無訊息根節點 1、訊息記錄 1,183；其他分支 0。
- 原始角色：user 360、assistant 767、system 41、tool 15。
- 可匯出 720：user 359、assistant 361。
- 其餘互斥分類：system 41、hidden 32、internal 367、tool 15、tool_call 8。全部保留在 records，沒有直接刪除或為湊數改分類。
- 有文字的 user 360、assistant 372（一般文字 367＋code 5）、tool 15，不能直接稱為可見訊息。
- 研究參考 732 與 720 的差額：本次來源可定位 hidden user 文字 1、hidden assistant 文字 6、assistant code 工具指令 5。**這是本次來源的分類證據，研究 JSON 不在環境中，尚未完成兩份資料逐訊息比對。** 也未將分享頁視覺 DOM 逐則驗證旗標改為 true。

已逐筆核對本次取得的 1,183 筆來源 ID、角色、建立時間、content、文字雜湊及順序。原文 Word 約 400 KB，重開後 720 則全文逐字與順序相符。閱讀版約 416 KB，逐訊息檢查中文字序及合成英文／標點／程式碼案例；不能稱為已把閱讀版所有符號與原始 Markdown 做 byte equality，因為標記已轉成結構。

真實閱讀版在本機約 5.1 秒產生，核對程序在 PDF 前峰值約 145 MiB（該程序同時持有原文、閱讀版及核對資料，非純 HTTP 單次請求峰值）。LibreOffice 實際產生 573 頁，所有 Word OOXML 中的中文字經 Unicode 正規化後均可在 PDF 文字層取得；並未讓多欄 PDF 抽取順序冒充 Word 的語義順序。Word 語義順序另外於 OOXML 逐訊息檢查。沒有人工逐頁閱讀真實私人內容，也未公開任何實際對話檔案／截圖／原文。

本次閱讀版仍有約 100 項媒體／未知或動態格式警告，均顯示於文件與結果報告。未知 JSX、`{@body}`／變數綁定、未取得圖片及原生數學公式不是已完整還原的功能，不執行程式、不生成替代圖片、不自行推導正文。這些限制及缺少研究資料仍應納入發布決策。

## 安全與隱私界線

- 只接受精確 `https://chatgpt.com/share/<UUID>`；禁止其他主機、userinfo、port、控制字元、query／fragment、非分享路徑與不安全轉址，最多 3 次轉址。
- 匿名 HTML 20 MB 上限、30 秒 socket timeout 及讀取／轉址時間檢查；Content-Length 不可靠就不用它顯示百分比，不支援編碼／不完整資料明確失敗。
- 直接 HTTPS 模式做公開 IP 檢查及數值位址釘選，TLS 仍驗原主機。若使用管理者設定的 HTTPS proxy（如本次執行環境），由受信任 proxy 的目的地／DNS 政策負責該層限制，不移除或繞過 proxy。
- HTTP JSON 4 KB；Host 精確白名單、同源 Origin／Fetch Metadata、拒絕 transfer encoding、no-store、CSP，無 CORS 任意授權。
- 本機最多 8 個 HTTP 執行緒／2 個轉換；建議免費部署設定最多 1 個轉換。每來源每分鐘 10 次、全程序每分鐘 60 次，地址計數表最多 1,024 筆、60 秒過期；不信任任意 X-Forwarded-For。
- Word 最多 5,000 則、500 萬字元；閱讀版換行及標記的預估版面單位最多 100,000，實際 Word 最多 16 MB，單個 NDJSON 事件 24 MB、瀏覽器回應 26 MB。超限明確拒絕而非截斷；不承諾無上限轉換。版面估計上限涵蓋本次真實 37,414 個單位，不將正常來源誤判為超限。
- 有限回應 queue 與 transport heartbeat（空行不是假進度），伺服器 85 秒處理期限、瀏覽器 90 秒期限；取消時 producer 在下一次真實 callback 停止，網路阻塞仍可能等 socket timeout。實際工作退出才歸還轉換槽，避免假釋放造成無上限併發。
- 無對話資料庫、永久快取、HTML／JSON／Word 暫存或正文日誌。瀏覽器 Blob 在重試／離開時釋放。測試需落地的私密 Word／PDF 使用 TemporaryDirectory，退出即清除；只有合成視覺案例可選擇留存。

## 部署方案與費用（僅準備，未開通）

建議先採 **Render Hobby＋Free Python Web Service，單一同源服務，Gunicorn WSGI、1 worker、8 HTTP threads、1 個實際轉換**，不拆前後端、不建立資料庫。已準備 `render.yaml` 與 `gunicorn.conf.py`：指定 free、branch main、自動部署關閉；本批沒有建立 Blueprint 或觸發任何部署。

依 2026-10-27 查閱的官方 [Free](https://render.com/docs/free)、[Pricing](https://render.com/pricing)、[Web services](https://render.com/docs/web-services)、[Blueprint](https://render.com/docs/blueprint-spec)：免費 web service 512 MB，工作區共享 750 instance hours／月；15 分鐘無流量後休眠，再次啟動可能約一分鐘。Hobby 公開價目列出 5 GB included bandwidth；建置／頻寬亦與工作區其他服務共享，以開通時頁面為準。HTTPS 由平台終止並將 HTTP 轉址至 HTTPS。NDJSON 使用逐段產出、有限 queue、`X-Accel-Buffering: no`；尚未有 Render 公共網址，因此不能宣稱平台層實際串流／iPhone 線上下載通過。

**免費不是永遠自動免扣款。** 官方說明：未加付款方式時，額度用完會暫停服務／建置；已加付款方式時可能產生額外頻寬／建置費。後續須確認使用無付款方式的免費工作區，且不啟用自動加購或付費方案；若帳戶既有付款／收費設定不明，先不要啟動。付費入門 compute 現列 US$7／月，只供成本比較，本批未購買。Base64 回應增加約 33% 傳輸量；不能把額度直接等同固定轉換次數。

免費方案的休眠、冷啟動、0.1 CPU 級計算資源、共享出口被分享頁限制、85／90 秒期限與容量上限都需在真實部署後驗證。本次本機快，不代表免費平台同樣快；沒有 SLA／常駐保證。Cloud Run 雖有免費額度，通常需啟用 billing 且有超額費用，不作為本次零費用預設。

後續人工需求（尚未執行）：
1. 使用者開通／選定 Render 免費、無付款方式的工作區，連接本 GitHub repo；審核方案、區域與費用設定。
2. 第 5-2 批獲授權並合併後，才使用 main 的設定手動建立／部署；建立 Blueprint 本身會部署，不能在本批先按建立。
3. `RENDER_EXTERNAL_HOSTNAME` 由平台提供；自訂網域另於 `CHATKEEP_ALLOWED_HOSTS` 填精確主機。無需 ChatGPT Cookie、Token 或 API Key。
4. 驗收公共 HTTPS、未緩衝 NDJSON、冷啟動、匿名來源存取、最大負載及手機下載，再判斷是否可發布。未驗證前不虛構網站 URL。

## 重現與 Actions

```sh
python -m pip install -r requirements-dev.txt
python -m compileall -q chatkeep.py semantic.py rich_word.py word_layout.py word_export.py server.py tests
node --check web/app.js
python -m unittest discover -s tests -v
python -m playwright install --with-deps chromium webkit
python tests/browser_check.py --browser all
python tests/browser_check.py --browser all --live
python tests/production_check.py --live
# 需 LibreOffice＋繁中文字型；PDF 檢查使用開發相依 PyMuPDF
python tests/visual_check.py
python tests/live_check.py --visual
```

本次雲端主機無 sudo，LibreOffice 使用隔離的本機 Docker QA image（無網路執行、不含專案或對話）；也可用上述腳本的 `--docker-image` 指定已備妥的工具映像。WebKit 依賴放在使用者目錄，實際啟動測試，沒有把缺少真機測試說成真機通過。CI 在 runner 安裝標準系統相依，不依賴本環境的工具映像。

`.github/workflows/parser-tests.yml` 沿用既有 workflow 路徑，只有 workflow_dispatch，單一整合 job，預設 include_live=true；完整單元、合成 Word/PDF、Chromium／WebKit、Gunicorn 及真實來源／Word/PDF／瀏覽器驗收。真實測試只輸出統計，不上傳任何來源 HTML、JSON、Word、PDF、截圖或 trace。若遠端無法啟動或某一步失敗，必須在 PR／Issue 保留失敗與原因；不透過移除測試、改合成資料或重跑舊 SHA 冒充成功。
