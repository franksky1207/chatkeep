# ChatKeep 分享連結 HTTP 拒絕：2026-11-11 技術調查

## 已知實機事實
- 分享頁 `https://chatgpt.com/share/6af41141-2ee4-83ec-a46c-a62ebd9439d6` 可由使用者 Safari 開啟。
- 正式 Word / HTML 都失敗，說明問題發生在共用分享頁擷取階段。
- 測試 Render 回報 `SOURCE_HTTP_REJECTED`，代表 Python 擷取收到 HTTP 錯誤，**但既有診斷未指出確切狀態**。
- 尚無證據確認是 403、429、404，也不能直接說是 Cloudflare 封鎖或 React 格式改版。
- 僅保留固定錯誤分類，絕不把公開分享 URL、原始 HTML、Cookie、驗證資訊輸出到服務紀錄。

## 外部參考
- OpenAI 分享連結說明：https://help.openai.com/en/articles/7925741-sharing-conversations-and-scheduled-tasks-in-chatgpt
  - 個人公開分享連結可供持有者開啟，但**不等於保證機器爬取可用**。
- Render 對外 IP：https://render.com/docs/outbound-ip-addresses
  - 同區域服務使用共用 IP 範圍；伺服器與手機的網路條件不同。
- 開源參考：https://github.com/vl3c/ChatPeek 、https://github.com/pencil311/chat-share-reader
  - 解析 React Flight/turbo-stream 的方式可交叉參考；**不代表能解決來源 HTTP 拒絕**。

## 根因優先順序
1. 先從測試版取得 HTTP 狀態（如 `SOURCE_HTTP_403` / `SOURCE_HTTP_429` / `SOURCE_HTTP_404`）。
2. 若 403/429：視為來源服務存取限制，**不要以代理跳板、登入 Cookie、反爬繞過、頻繁重試嘗試強行存取**。保留既有正常轉換，提示官方 JSON 備份替代路線。
3. 若 404：核實連結是否更新、撤銷或分享範圍不同；不能單憑 Safari 成功推定 Render 端原因。
4. 若 200 但無對話資料：才比較不同解析器的 React payload 結構、主線完整性驗證。
5. 若長期需要不依賴 Render 來源網路的匯入方式，可評估使用者主動提供經瀏覽器儲存的頁面資料，但必須嚴格清理腳本、核對完整性、絕不自動宣稱全部還原。

## 實作範圍
- 本分支只加入安全 HTTP 狀態分類、前端顯示與單元測試。
- 不修改既有網路安全白名單、redirect / DNS 釘選、HTML 主線驗證、Word 轉換功能。
- 不合併 main、不得把此診斷補丁誤當成已修復 HTTP 拒絕。
