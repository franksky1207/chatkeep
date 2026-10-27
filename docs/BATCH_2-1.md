# 第 2-1 批｜UI 元件語義解析與 Word 原生呈現

本批程式已提交至共用整合分支 `feat/share-parser-1-1`、PR #2，**尚未完成執行環境測試與真實 Word 視覺驗收**；不宣稱第 2-1 批完全驗收通過。

## 實作
- `semantic.py`：非執行式 HTML/UI 結構解析，分隔真正的 fenced code 與 UI 元件；認識 `box`、`row`、`col`、`text`、`caption`、`card`、`button`、`checkbox` 等。未辨識的標記保留原文，不執行 JavaScript。
- `rich_word.py`：以 python-docx 表格／儲存格底色輸出資訊卡、橫向列、簡易 LINE 對話泡泡；支援 Markdown 標題、基本清單、引用、圍欄程式碼與 pipe table；未知媒體只輸出明確註記，不假造圖片。
- `word_export.py`：保留 `rich=False` 原文模式供既有逐字測試；正式 HTTP 轉換使用 `rich=True`；統一採正式 JSON 模型，不另寫擷取器。
- `tests/test_rich_word.py`：合成測試確認方框、表格、泡泡、真實程式碼和未知元件內容可讀、Word 原生結構可編輯。

## 已知限制及驗收 Gate
1. 解析尚不涵蓋所有動態 DIL UI 型別；複雜互動和 JSX 表達式無法保證完整靜態重建。未辨識內容保留原文的設計需檢查是否有任何看不見的資料遺漏。
2. LINE 目前依常見文字格式啟用聊天泡泡；需以合成格式和真實代表樣本驗證人名／時間／左右位置，不得把所有含冒號的文字誤判。
3. Markdown 表格與清單為基本支援，巢狀卡片／列、圖片嵌入、數學公式、完整引用和跨頁效果仍需進一步測試，不應宣稱視覺百分之百還原。
4. 既有擷取來源 720／研究 JSON 732 差異未消除；無研究 JSON 逐筆比對，不提升完整性驗證旗標。
5. 當前 ChatGPT 對話環境只能對 GitHub 提交程式，無法直接執行 Codex 本機 Python／Chromium 測試；**已寫測試 ≠ 已通過測試**。

## 下一步在可執行環境驗證
```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tests/browser_check.py
python tests/browser_check.py --live
```
需對產生的 .docx 做文字總量、元件內容、角色分組和 iPhone／桌機 Word 的人工目視檢查。缺字或測試失敗應繼續在同分支修正，**不得合併 main、觸發正式 Actions 或發布**。
