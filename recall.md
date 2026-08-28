# recall.md — 專案狀態與已確認決策

> 本檔記錄目前狀態、已確認決策、完成內容與後續事項；完成工作後由 AI 追加更新。

## 目前狀態（截至 2026-08-25）

- 專案根目錄：本機專案根目錄（不記錄絕對路徑）。
- 目前實際存在的檔案：
  - `README.md`（已建立並完成撰寫，為專案規格）
  - `fetch_pages.py`（空檔，尚未實作）
  - `read.md`（使用者新要求）
  - `recall.md`（本檔）

## 本次完成內容

- 已依先前 `README.md` 內的任務規範，將 README 取代為正式的專案說明文件（繁體中文、UTF-8）。
- `README.md` 現含 10 個主要區塊：
  1. 專案簡介
  2. MVP 範圍
  3. 預定技術棧
  4. 資料流程（Mermaid 流程圖 + 文字說明）
  5. 預定目錄結構（標註哪些檔案尚未建立）
  6. 文件與 chunk 規範
  7. 回答品質與 RAG 規範
  8. 開發里程碑（Phase 1–6）
  9. 初始驗收問題（5 題）
  10. 給 AI 協作者的工作規範

## 已確認決策

- 專案名稱：Minecraft AE2 RAG Assistant。
- 目標：針對 Minecraft 1.21.1 與 Applied Energistics 2（AE2）的知識問答 RAG 助手。
- 第一版只以 AE2 官方 1.21.1 線上指南為資料來源，不宣稱能查核特定模組包的客製配方。
- 初期僅處理人工指定的 15～20 個官方頁面，不進行全站自動爬取。
- 技術棧：Python、requests + BeautifulSoup、Markdown + YAML、Chroma、OpenAI Embeddings／LLM、Streamlit；初期不使用 LangChain。
- 文件與 chunk 規範：
  - 每份 Markdown 需 YAML metadata：`title`、`source_url`、`minecraft_version`、`mod`、`source_type`、`fetched_at`。
  - 固定 `minecraft_version: "1.21.1"`、`mod: "Applied Energistics 2"`。
  - 以 Markdown 標題優先切分；chunk 約 500～700 tokens、重疊約 80～120 tokens。
  - 每個 chunk 保留頁面 URL、頁名、章節標題與版本資訊；無來源 URL 的文字不得納入正式知識庫。
- 回答品質規範：LLM 只能依檢索到的 chunk 作答；答案需附可點擊來源；資料不足時回「目前官方文件不足以確認」；不可混用非 1.21.1 文件；先檢視檢索品質再調整 chunking。

## 下一步

- 下一個最小工作項目：實作 `fetch_pages.py`（下載 AE2 官方 1.21.1 指定頁面並儲存原始 HTML 至 `data/raw/`），此步尚未進行。
- 之後依里程碑順序：`chunk_pages.py` → `index_chunks.py` → `query.py` → `app.py`（Streamlit demo）。

## 注意事項

- 不將 API Key、帳密、個人資料、私人絕對路徑或其他敏感資訊寫入任何 Markdown 檔案。
- 若要改變既有決策，需先說明影響與理由，經確認後再更新本文件。
