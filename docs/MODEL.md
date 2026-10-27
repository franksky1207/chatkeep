# ChatKeep 正式 JSON 模型 v1.0

`chatkeep.extract_url()` 是正式擷取入口；`parse_html()` 為同一解析流程的離線入口。`word_export.build_docx()` 直接消費本模型；HTTP／前端不重做擷取或訊息選擇。

| 欄位 | 意義 |
| --- | --- |
| `schema_version` | 固定為字串 `1.0`；後續不相容改動須升版 |
| `title` / `source_url` | 對話標題／來源公開分享 URL |
| `provenance` | 線上入口取得的 UTC 時間、HTML 大小／雜湊、串流片段數；不含原始 HTML |
| `branch` | 目前節點、還原方法、有序節點 ID、其他分支節點 ID |
| `records` | 目前分支的**全部**節點，包括無訊息根節點、隱藏、推理、系統及工具；順序與 parent 保留 |
| `records[].message` | 無訊息節點為 null；其餘含 ID、author／role、create_time／update_time、channel、recipient、status、原始 content／metadata、text 與 UTF-8 SHA-256 |
| `messages` | 從 records 選出的使用者／助理可匯出訊息；非文字訊息保留可取得文字並列警告；Word 僅使用此陣列 |
| `report` | 原始節點／訊息數、其他分支數、全部角色／文字角色／內容類型角色分布、可匯出角色數、分類數、定位 issues、warnings 與驗證狀態 |

原始 content、metadata 保留供後續元件還原使用。`text` 不改寫 Markdown、程式碼或 `<box>`／`<row>`／`<text>` 正文；多個文字 parts 依來源順序以一個換行連接，原始 parts 邊界仍在 content。圖片等非文字部分不補成生成圖片。日期類型轉成其來源字串，null／undefined／array hole 在正式 JSON 皆為 null（目前真實頁面只觀察到 null）；負零保留為 -0.0。未知型別、循環或缺失參照、未完成／拒絕的 deferred frame 明確失敗，不悄悄補空。

分類依優先序互斥：system（含 developer）→ tool → hidden（頁面旗標）→ internal（推理類型／內部 channel）→ tool_call（助理 recipient 非 all）→ unknown → non_text → visible → empty。結構節點另計 structural。所有類別仍在 records；只有 visible／non_text 在 messages。工具執行指令不冒充助理對使用者的回答。`roles` 統計所有有訊息記錄，`text_roles` 計算有可取得文字的全部角色，不代表可見數；`content_type_roles` 另列 text、code、thoughts 等來源類型。

`issues` 每項含 node_index（零起算）、message_id、reason，必要時含 content_type 及 parts 位置。缺 ID／重複 ID、未完成可見訊息、未知／非文字內容會標為 partial。隱藏／內部記錄有明確分類，不將它們誤稱為缺漏或空白。

`status=extracted_unverified` 只表示來源解析／分類未發現已知缺漏，**不代表完整性已驗收**。`partial` 表示已知缺漏／未還原；仍可下載帶警告的文件。`reference_comparison=not_performed` 與「尚未完成逐訊息比對」會持續顯示，直到真正取得研究資料並比對。舊欄位 `verified_against_live_page` 保持 false，因尚未逐則對照分享頁的視覺可見內容；HTTP 擷取成功另由 provenance 及 opt-in live check 證明。數量相同不會自動將任何驗證旗標設為 true。

Word 原文模式（rich=False）保留原文標點、tab、換行（Word 以原生 line break 表示；CR／CRLF 依 Word 慣例成為換行），每則訊息有角色標題；不解讀或執行 Markdown、UI 或外部資源。XML 不允許的控制字元會阻止匯出並明確報錯，不無聲刪字。輸出名去除路徑／控制字元與保留裝置名，最長 100 字元再加 .docx。資料只留在本次 HTTP 請求與瀏覽器 Blob，無永久快取、資料庫或伺服器對話檔案。

## 格式與授權參考

延續既有解析器修正，未複製第三方解析器原始碼。參考 turbo-stream 2.4.1 的 [wire 常數](https://unpkg.com/turbo-stream@2.4.1/dist/utils.js) 與 [參照／延遲語義](https://unpkg.com/turbo-stream@2.4.1/dist/unflatten.js)（MIT）。本版支援目前頁面出現的 positional object／array、P deferred，以及合成驗證的多個全域 deferred pool、Z alias、D 日期與特殊值。未支援型別採明確錯誤，不能保證未來未公開 wire format 永遠相容。既有調查來源 chickensintrees/chatgpt-share-reader（MIT）及 dzoba/chatgpt-to-docx 僅為研究參考，未納入其程式。Word 使用 python-docx 1.2.0（MIT，套件自行帶授權）；瀏覽器測試使用 Playwright（Apache-2.0），不屬正式執行依賴。


## 第 5-1 批補充契約

閱讀版使用 `semantic` 的安全 token tree，不執行 JSX 屬性／事件。已知元件採原生儲存格，單欄 row 保持子節點文件流；未知格式與動態文字保留並警告。這不改寫 JSON 的原文／content。閱讀版非 Markdown byte equality；來源逐字核對仍走 rich=False。

HTTP report 增加 `rendering_status`（rendered／partial）及 `rendering_warnings`（message_index、reason）。格式／圖片限制會在文件與網頁明示，不能將來源 `issues=[]` 解讀為所有元件已完整還原。來源 `status`／reference_comparison 仍獨立，研究資料未取得前不提升驗證旗標。

進度只計實際下載 bytes、已處理節點／訊息；pack 在實際存檔前發出且不帶百分比。完成前沒有下載檔名欄位。伺服器與前端檔名均限制 100 Unicode codepoints／200 UTF-8 bytes，處理帶副檔名的 Windows 保留名稱；使用者主檔名固定補 .docx，不改 Word 內容。

部署與資源上限、可重現驗收及未通過事項集中於 [BATCH_5-1](BATCH_5-1.md)。

第 5-1 補修固定參考字型為 Noto Sans CJK TC，避免未安裝 Microsoft JhengHei 時各平台任意替代；未安裝該字型的終端仍可能使用系統 fallback，不能承諾像素相同。巢狀表格的 grid、preferred width、cell width 依父內容寬度（扣除 padding）配置。UI 文字只清理 JSX 純縮排／空行，保留每個非空白字元及有意義的行序；原始 JSON／原文 Word 不改寫。
