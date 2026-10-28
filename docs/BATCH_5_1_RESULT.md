# 第 5-1 批：大型選取對話衍生傳輸

基準：遠端 `48484f1615f2c3672a86430a7da8a56c869edfb3`。技術實作與合成測試完成，待使用者驗收；未部署。

## 架構比較與決策

| 選項 | 記憶體／隱私 | 恢復／安全成本 |
|---|---|---|
| A 本機衍生序列＋無狀態批次＋本機 ZIP | 伺服器只保留當次 ≤2 MB 輸入、一卷 Word／有界 ZIP；無跨請求私人持久化。本機選取與回應緩衝皆設上限 | 本機 manifest 固定身分、順序及 SHA-256；指定批次可重試替換，所有批次驗證完成才發布 ZIP。不能跨請求憑空合成單一 DOCX |
| B 暫時性服務端 session／串流組卷 | 可合成跨批單 DOCX，但必須持有跨請求訊息／Word 物件或私人暫存 | 需要 token、TTL、全域配額、重啟／取消清理、競態及併發測試；單 worker／免費服務重啟與記憶體負荷成本較高 |

採 **A**；不建立 session、全域內容 dict、私密暫存檔或新依賴。不修改第 2 批索引／Blob.slice 原始擷取、UI、CORS 或部署。本機模組接受「已選取單一對話 Blob」，不接受整包備份；小型可驗證對話仍交既有官方 API。大型來源產物明確標示衍生表示。

## 已實作的資料流程

1. `prepareInWorker(selectedBlob)` 只接受第 2 批擷取後的一個已選取對話 Blob，不接整包備份。用獨立 `transfer-worker.mjs`，不改 index／extract worker 或原始 JSON 下載；同一模組一次只開一個準備 worker，取消會終止它。
2. `transfer-format.mjs` 在限定大小內檢查嚴格 UTF-8、重複 JSON key、深度／項目上限、XML 字元及有限數；對單一物件做 mapping／parent／children／所有 parent 鏈循環、current_node 路徑及路徑訊息 ID 檢查。沒有用 mapping 插入順序或 regex 擷取對話。
3. 角色、隱藏旗標、internal／tool call、空白、內容格式及 unfinished 規則與 Python 官方 adapter 對齊。只將當前有效輸出的 `{id,role,text}` 放入衍生表示；不傳未知 metadata、隱藏／工具本文或非當前分支內容。保留統計，但標示為本機來源聲明。Unicode 字元計數與 Python strip 空白集合對齊，避免 Emoji／NEL／BOM 判定不同。
4. 若原始選取 Blob ≤2,000,000 bytes，且符合既有 API 的結構預算，回 `mode=official`／`path=/api/convert-json` 與**原 Blob**；不重新序列化原始下載。
5. 其餘在本機依完整訊息切批，產生 `mode=chunks`、固定 manifest 與封包。每批只含選中對話的必要有效文字；這是 `official_json_derived`，不是保留完整 mapping 的官方 JSON。
6. 新 `POST /api/convert-chunk-v1` 使用既有來源／Host／大小／上傳期限、SLOTS、RateLimit、受限子程序。`chunk_transfer.py` 重驗版本、精確欄位、範圍／計數、manifest／批次 SHA-256、已接收訊息的 role／text／ID，然後共用 `export_conversation()`／WordVolume／rich_word／word_layout，沒有另一套產生器。
7. 一批可產一個 DOCX，也可因既有 Word 容量產生批內 ZIP。全域 bookmark／訊息標題從 first_message 開始；伺服器檔名帶 `_批001_第1卷`，批內分卷標題明示「第 N 批｜批內第 M 卷」，避免誤認最終全域卷號。
8. `TransferResults` 釘住最初 manifest。逐批檢查回應身分、範圍、計數、SHA-256、DOCX／ZIP CRC、實際全域 bookmarks、cell 結尾段落；檢查整段唯一訊息 ID、全域字元／訊息數。每個 part_index 只有一筆已驗證結果，重試替換，不能重複放 ZIP。
9. 所有批次完全成功才 `finish()`。一個文件仍回單 DOCX；多文件才在本機以有界 ZIP32／stored 組裝，按全域卷數重新命名；回傳清單同時保留 part_index、part_volume_number 與全域 number。漏批、混批、損壞、超限或取消都不回貌似完整的 ZIP。

`transfer-client.mjs` 是可注入 transport 的**獨立函式庫**：沒有呼叫 app、沒有改 UI／下載按鈕／跨站網址／CORS。第 6 批可接續：

```js
const prepared = await prepareInWorker(selectedBlob, {signal});
// mode=official 時送原 Blob 至既有 API。
// mode=chunks 時由第 6 批提供 transport(packet,{signal})：
const collector = new TransferResults(prepared);
await sendPrepared(prepared, {send: transport, collector, signal});
const verified = await collector.finish({signal});
// verified.blob / filename / mime_type / report 才是可提供的完整下載。
// 失敗後可沿用同一 prepared/collector，以 indices:[failedPart] 重試。
```

## 版本化契約與 canonical hash

Content-Type 使用 `application/json`，Content-Length 為真實 UTF-8 bytes。禁止壓縮、multipart、分塊傳輸及 ZIP 輸入。新端點最多仍為 2,000,000 bytes。

封包精確欄位：

```text
{
 schema_version: "chatkeep.chunk.v1",
 manifest: {
   schema_version: "chatkeep.transfer.v1",
   source: "official_json_derived",
   nonce: <每次選取新建的 16 random bytes、小寫 hex>,
   source_id: <官方 id／conversation_id 字串或 null>,
   title: <原選取對話標題>,
   conversation_key: <SHA-256>,
   sequence_sha256: <SHA-256>,
   total_message_count, total_text_chars,
   source_counts: {
     raw_node_count, active_path_node_count, active_path_message_count,
     output_message_count, off_branch_node_count,
     skipped_categories: {structural,system,tool,hidden,internal,tool_call,empty}
   },
   parts: [{part_index,first_message,last_message,message_count,sequence_sha256}, ...]
 },
 part_index: <1-based>,
 messages: [{id,role,text}, ...]
}
```

`complete=true` 等未定義欄位直接拒絕。兩種完整性層次不可混用：

- **伺服器回應：** 沿用 v2 envelope 的 artifact_type、MIME、filename、Base64 document、report，另附 transfer（conversation_key／manifest_sha256、part_index／part_total、全域範圍／訊息數、part_sequence_sha256、sequence_sha256）。report 必為 complete=false、chunk_complete=true、source_verified_by_server=false、server_validated_scope=this_chunk_only；原始統計放在 client_source_counts，而非冒充伺服器從 mapping 驗出的數字。
- **本機最終驗證清單：** complete=true／all_parts_verified=true 只代表全部**本機衍生有效輸出序列**已核對；integrity_basis=browser_derived_sequence、source_verified_by_server=false，仍附來源／略過統計與警告。不宣稱伺服器驗證過原始官方物件／網頁逐字完整。

定義 `C(x)`：JSON 無空白，物件 key 以排序輸出（協定 key 都是 ASCII）、array 保持順序，字串使用 JSON escapes，非 ASCII 以原 Unicode UTF-8 編碼；拒絕 unpaired surrogate、非法 XML 字元、NaN／Infinity。協定數值僅允許有界整數，不接受 boolean 冒充整數。

1. 每批 `sequence_sha256 = SHA256(C([[id,role,text], ...]))`。
2. 全段 `manifest.sequence_sha256 = SHA256(C(manifest.parts))`，parts 是包含每批順序、範圍、訊息數及 hash 的**完整有序 descriptor 清單**。這是版本化的分塊序列承諾，不是直接串接本文的 hash；重新切批會改變它。
3. `conversation_key = SHA256(C(manifest 去除 conversation_key))`，綁定隨機 nonce、來源 id、標題、全序列、計數及原始來源統計；不靠檔名判定歸屬。重試須沿用原 prepared，不產生新 nonce。
4. 各 DOCX report.volume 保留第 5 批的 sequence_sha256（每訊息 `[id,role,text]` 的 UTF-8 JSON，前置 8-byte big-endian 長度，再依序 SHA-256），另外提供 file_sha256。前端分別核對來源子序列與實際檔案 bytes，不能把兩種 hash 規範混為一談。

Hash 是完整性／歸屬承諾，**不是認證或官方來源證明**。無狀態伺服器無法知道其他批次的真實內容，也不能識別能自行重算整個 manifest 的惡意客戶端；它仍只確認本批且受全服務速率／資源限制。全段完整性由持有最初 prepared 的本機 verifier 判斷，不能接收伺服器或外部提供的新 manifest 取代它。

### 固定跨語言 test vector

```json
[["α😀","user","繁中\n\"quote\"\\slash😀"],["β","assistant","English\t<&>"]]
```

以上是 C(messages tuple array)，其批次 hash 為：

```text
e3ee668688256fc84a3a9dc66cb27ca49ab378ee2a8f702c03c846799c1c6c06
```

單批 descriptor 為 index=1、first=1、last=2、count=2 及上述 hash 時，全段 parts hash：

```text
e26548a40682ec2791eca5416ee15daec6c2da3bf4a6af42e9357a46f3d38f3f
```

`tests/test_chunk_transfer.py:packet()` 完整 manifest（title=test、source_id=source、nonce=0123456789abcdef0123456789abcdef、2 節點／2 訊息、略過全 0）的 conversation_key：

```text
6428efd9c2c40f5f0f07d82233e795fd9239787c2aca5dd244d0813883d2336f
```

Node 與 Python 對同一 canonical Unicode／quotes／換行／反斜線資料實際比對，且實際跨程序轉換使用相同規範。

## 容量、資源與頻率政策

| 層次 | 實際界線 |
|---|---|
| 已選原始來源本機準備 | ≤16,000,000 bytes、≤5,000 mapping 節點；深度 ≤32、值／key 項目 ≤300,000。先檢查 Blob.size，再解碼／JSON.parse **這一個有界選取物件**；不是整包 440 MB JSON.parse |
| 小型原始 API | 維持 2,000,000 bytes、100,000 結構項目；可走此路徑時仍傳原 Blob |
| 本機衍生有效序列 | ≤5,000 訊息、≤5,000,000 Unicode 字元；單則 ≤1,000,000 字元，依 Python 字元數而非 UTF-16 units |
| 分批 | 最多 16 批，每批 ≤500 完整訊息；目標訊息 JSON 約 1.75 MB，最終含 manifest 的每次 HTTP 本文仍硬限制 ≤2 MB；較大單則可獨占一批，但仍須在完整封包上限內 |
| 單則過大 | 無法裝進封包（保留 manifest 預算）回 CHUNK_TOO_LARGE；字元／Word 結構超限回 MESSAGE_TOO_LARGE，不切訊息。整段在總量內仍可能因完整訊息配置需要 >16 批而拒絕 |
| 單批伺服器 | 共用第 5 批 Word 結構預算：120,000 元素／8 MB 本文 XML／5,000 cells；可批內分卷。最多 16 卷／16 MB 該批 artifact；Base64 envelope／IPC ≤24 MB |
| 服務資源 | 舊配置 1 worker／1 轉換名額；新端點同 SLOTS／RateLimit，AS=384 MiB、CPU 軟／硬 30／31 秒、wall=45 秒；Gunicorn 上傳 10 秒。未調高匿名額度、部署配置或 2 MB 本文門檻 |
| 本機總成果 | **所有批次合計** ≤16 卷、所有 DOCX bytes 加 16 KB 封裝預留 ≤16,000,000 bytes；ZIP32 stored，無 ZIP64。ZIP writer 寫入前核算精確總長，超限不發布 |
| 回應 DOCX 驗證 | 最多 64 個 ZIP parts、每個解壓項目 ≤8.1 MB、整份 DOCX 解壓合計 ≤12 MB；只接受現有後端產生的 ZIP32 stored／deflate 與旗標，不是任意 DOCX／備份匯入器。即使 server 可產生，超出本機 verifier 預算亦會明確拒絕而不宣告成功 |
| 客戶端發送 | 每 collector 一個順序發送流程；起始亦冷卻至少 6,100 ms；每批最多原次＋2 次 429 重試，依 Retry-After 等待（2–120 秒），非 429 失敗交由指定批次重試；每次 request deadline 55 秒；每輪開始批次檢查 15 分鐘發送預算 |
| 來源速率 | 仍每 REMOTE_ADDR 每分鐘 10 次、全域每分鐘 60 次。RateLimit 是最終依據，跨頁／跨使用者不可由本機節流取代；RATE_LIMITED 回 Retry-After:60，BUSY 回 Retry-After:2 |

同一個 module 只準備一個 worker；準備取消會 terminate。本機 verified results Map 以 part_index 為唯一 key，有上述總 bytes／卷數界線；正常重試替換，不累積一份重複文件。發送取消會 abort 當前 transport、停止後續批次並清除已驗證成果；直接在驗證／finish 階段取消亦不回完整產物。非取消失敗保留已驗證批，供指定批次重試。

伺服器沒有跨請求內容狀態、session、暫存檔、完整請求／標題／本文日誌或外部代理。單批 ZIP hash 逐卷讀取，不同時收集全部 DOCX bytes。客戶端最終 ZIP 用 Blob 引用既有 bytes，逐份計算 CRC，沒有 Base64 成果全數另存成第二份持久檔；只處理當前有限結果。

取消 HTTP 不保證伺服器即時偵測斷線；工作程序仍依 45 秒／CPU／AS 上限終止並回收，後續可能暫時收到 BUSY。這沿用既有同步 WSGI 限制，沒有假裝已完成第 6 批取消協定。

### 錯誤碼

沿用既有 HTTP 400／403／405／408／413／415／429／503／504 契約，新增衍生驗證 HTTP 422：INVALID_CHUNK、UNSUPPORTED_SCHEMA、TRANSFER_LIMIT、PART_LIMIT、PART_ORDER、PART_COUNT、CONVERSATION_MISMATCH、SEQUENCE_HASH_MISMATCH、PART_HASH_MISMATCH、DUPLICATE_MESSAGE、UNSUPPORTED_CONTENT、MESSAGE_TOO_LARGE。受共用 decoder 拒絕的損壞 UTF-8／重複 key 仍為 INVALID_JSON／400。

本機另有 SELECTED_SOURCE_LIMIT、CHUNK_TOO_LARGE、MANIFEST_MISMATCH、MISSING_PART、ARTIFACT_HASH、ARTIFACT_CRC、BOOKMARK_MISMATCH、INVALID_ARTIFACT／INVALID_DOCX／INVALID_RESPONSE、OUTPUT_LIMIT／VOLUME_LIMIT、TRANSFER_CANCELLED、BATCH_TIMEOUT、TRANSFER_TIMEOUT、UNSUPPORTED_CRYPTO／UNSUPPORTED_DECOMPRESSION 等明確原因。使用者取消為 AbortError。未知 worker 錯誤只回固定 PREPARATION_FAILED，不回本文或完整例外內容。

## 自動化結果與合成實測（2026-10-28）

環境：Debian 13／Linux x86_64、AMD EPYC 9V74，可見 3 CPU，cgroup 8 GiB，Python 3.12.14、Node 24.19.0。**不是 Render Free、Safari 或實體裝置**。

測試命令：

```sh
node --test tests/large_transfer.test.mjs tests/large_transfer_worker.test.mjs tests/local_backup.test.mjs
PYTHONPATH=tests .venv/bin/python -W error::ResourceWarning -m unittest \
 test_chunk_transfer test_long_conversations test_official_json test_integration \
 test_rich_word test_word_layout test_acceptance test_chatkeep -q
node --max-old-space-size=256 tests/large_transfer_stress.mjs
```

- 新增 Node 純模組／跨語言轉換與 worker lifecycle 測試 16 個，加既有原始 JSON／ZIP／Blob 範圍／取消回歸 9 個，合計 **25 個通過**（最終一輪 6.402 秒）。
- Python 新增 6 個協定／API 測試，加第 4／5 批必要回歸，合計 **91 個通過**（ResourceWarning 視為錯誤；最終完整一輪 12.657 秒）。
- 小型原始 API、公開分享 v1／v2、Word 樣式／表格結尾段落及原始擷取位元組回歸通過；不重跑無關 Actions／瀏覽器 UI。
- 跨語言真實 subprocess 測試：>2 MB metadata 冗餘來源；7.2 MB 有效 Unicode 文字四批；單批內兩卷 Word 再驗證封裝；SHA／CRC／bookmarks／順序／唯一位置；混批、交換、遺漏、篡改、偽造 complete 及跨批重複 ID 不得完成；相同批重新轉換與接受仍只有一筆成果。
- 受限 Node worker（測試設定 old-generation heap=128 MiB）完成來源準備；取消會實際 terminate 並等待 exit。發送中 AbortSignal 取消、55 秒 deadline（fake timer）、指定失敗批重試、429 三次上限、來源／單訊息／ZIP 上限與範圍驗證均通過。這個 128 MiB 設定是 Node 測試環境，不是聲稱瀏覽器提供相同 heap 開關。

### 真實本機 HTTP 壓測

測試啟動現有 Gunicorn 配置及真正 `official_worker.py chunk`，worker 實際使用 384 MiB AS、30／31 秒 CPU、45 秒 wall；客戶端 Node old-space 上限 256 MiB。沒有 mocking 傳輸、沒有將 2 MB 調高，使用真的 ≥6.1 秒節流。

| 案例 | 原選取來源 bytes | 實際傳輸 | 結果 | wall（含節流） |
|---|---:|---|---|---:|
| 大量無關 metadata、2 則有效訊息 | 4,200,461 | 1 次、989 bytes | 單 DOCX，37,924 bytes | 6.458 秒 |
| 2.4 百萬有效中文字元、4 則完整訊息 | 7,200,693 | 4 次：1,801,408／1,801,413／1,801,408／1,801,413 bytes，合計 7,205,642 | 4 卷 ZIP，163,182 bytes；全域 1～4 bookmarks／CRC／hash 全通過 | 25.307 秒 |

冗餘案例無 `PRIVATE_UNSENT_METADATA` 或 `PRIVATE_OFF_BRANCH` 離開本機；有效文字案例不是只驗證「metadata 能縮小」：實際傳送了 >7 MB 必要文字，每次均 <2 MB。四個成功 HTTP status 均 200，完整訊息未切開。

記憶體觀察（同一壓測程序累計峰值，約每 20 ms 採樣）：

| 範圍 | 冗餘案例後 | 有效大文字案例後 |
|---|---:|---:|
| Node 客戶端整體 RSS（含 worker thread、native buffers） | 139.3 MiB | 218.0 MiB |
| Node 主執行緒 heap 峰值（不含 worker heap） | 21.2 MiB | 34.9 MiB |
| worker 回報的完成時 heapUsed（不是峰值） | 12.7 MiB | 11.9 MiB |
| Gunicorn master＋worker＋converter RSS 加總 | 73.7 MiB | 126.8 MiB |
| 採樣累計服務 CPU 秒 | 約 0.28 | 約 1.95 |

服務 CPU 從 `/proc` utime＋stime（100 Hz）採樣，累計保留已退出 PID 的觀察值；短生命週期可能漏 ticks，**不是精確 profiler 或全 31 秒滿載測試**。RSS 共享頁可能重複計算、極短峰值可能漏取；客戶端峰值包含兩種案例及 fixture 建立，不能把 worker 結束時 heapUsed 當成整體峰值。

高負載失敗：真實 HTTP 的單則 Word 結構超限回 MESSAGE_TOO_LARGE，篡改同長度文字回 PART_HASH_MISMATCH；同一服務第 11 個匿名 POST 實際收到 429 RATE_LIMITED、Retry-After=60，沒有放寬額度。總共 11 次 HTTP POST（5 次成功轉換、其餘為失敗與速率檢查）；stdout／stderr 未含任何 PRIVATE_ 合成本文／標題／metadata。

## 尚未解決／未驗證事項

- 來源 >16 MB、>5,000 原始節點、深度／項目超限、有效文字 >500 萬、單則無法裝入 2 MB／單卷結構預算、需要 >16 批／>16 最終卷或 >16 MB 成果，仍明確失敗；不是任何尺寸都能轉。單個過大訊息不切開。
- 多次無狀態呼叫不會合成跨批單一 DOCX；只有全部只產出一個文件時仍回單檔，其餘是驗證過的多卷 ZIP。每批皆成功之前沒有完整 ZIP。
- SHA-256 沒有認證來源、nonce 也不是 session token；本機能驗證 current_node／parent 與來源序列，伺服器不能獨立證明被略過的官方原始資料。report 必須保留這個範圍區別。
- 16 MB 選取物件會在獨立 worker 中有界解碼／JSON.parse，不是增量解析任意大小單一物件；低記憶體手機仍可能終止 worker，應顯示失敗而不偷偷截斷。瀏覽器須提供 secure-context WebCrypto、Worker、Blob／Streams 與 deflate-raw DecompressionStream，缺少時不能宣稱產物已驗證。
- 本機 verifier 僅支援現有後端產出的 ZIP32 格式、禁止 DTD／ZIP64／描述符／特殊旗標；額外文件擴充或大量 relationship XML 也可能超出 verifier 解壓預算，會明確拒絕。
- 取消網路不一定令同步 WSGI 工作即時停止；依最長 45 秒資源期限回收。早期 429／413 拒絕大上傳時，部分 client 可能遇 BrokenPipe／網路錯誤，沿用第 5 批限制；本機保留可指定批次重試機制，不假裝網路錯誤是成功。
- Render Free CPU／RSS／代理、真實官方備份、Safari／iPhone／桌機、Microsoft Word 實機驗收、真實瀏覽器 Worker 記憶體留第 8 批。Node worker-thread shim 與 native Streams 測試不是跨瀏覽器驗收。免費排程較慢時仍可能 45 秒逾時，分批沒有解除 CPU／輸出限制。
- 第 6 批 UI／跨站 CORS／endpoint 設定／下載提示尚未接線；這裡提供可獨立測試的協定、準備、傳輸控制及驗證模組，不修改現有主網站行為。

沒有合併 main、部署 Render／Pages、建立 Release 或觸發 GitHub Actions。完成後保持 Draft，等待驗收，不開始第 6 批。
