# 第 1-1 批｜分享連結解析器

狀態：**合成測試可執行，真實分享頁驗證尚未完成**。此批只製作直接擷取與結構化資料，不做 Word 或部署。

## 執行

需要 Python 3.10+，不需要安裝額外套件：

```sh
python chatkeep.py --url 'https://chatgpt.com/share/<UUID>' > conversation.json
python chatkeep.py --html saved-public-share.html > conversation.json
python -m unittest discover -s tests -v
```

輸出包含 title、messages（ID、角色、時間、未經刪改的文字）、report（原始節點、可見訊息、角色統計、缺漏警告）。輸出轉向檔案為使用者自行選擇，程式預設不存檔。**請勿把真實 conversation.json 或 HTML 加入公開 GitHub**。

## 技術說明

分享頁可能含 React Router `streamController.enqueue(...)` 多片段字串。解析器將分段內容解跳脫、還原 positional flatten 的參照資料與 deferred promise，尋找 conversation shape，然後讀取 `linear_conversation` 或依 `current_node` / `parent` 鏈建立當前分支。此 wire format 未公開且可能改版，解析失敗必須明確回報。

原理調查參考 [chickensintrees/chatgpt-share-reader](https://github.com/chickensintrees/chatgpt-share-reader)（MIT License）及 [dzoba/chatgpt-to-docx](https://github.com/dzoba/chatgpt-to-docx)。ChatKeep 此版為獨立撰寫的最小模組，無需第三方套件，未直接複製上游程式全文；後續若納入原始碼須一併保留授權與著作權標示。

## 現況與下一步

- 已在本機以合成 stream 測試主要流程。GitHub Actions 的遠端執行結果需另外檢查。
- 嘗試用本會話的執行環境讀取測試分享連結時發生 DNS/連線錯誤，因此**未取得真實分享 HTML**。
- 本批不能聲稱 732 則全部擷取成功。實際連結應由可對外連線的環境重測，逐項與研究用 JSON 比對，而非只比訊息總數。
- Python 解碼器目前對循環參照採保護性斷開、延遲資料採基礎支援，必須經真實頁面確認相容性後再完成擷取 Gate。
