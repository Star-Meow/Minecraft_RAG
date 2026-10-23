# 向量化

> 職責：把 child chunks 轉成向量。
> 上一個階段：[切分](04_chunk.md)；下一個階段：[入庫](06_index.md)

程式：`src/embed_chunks.py`（**尚未實作**；本文件只寫已定的內容）

## 1. 輸入與輸出

- **輸入**：[切分](04_chunk.md) 的 child chunks（parent 不進 embedding）。
- **輸出**：每筆 child 的欄位 + 1024 維向量 + parent 參照 + `model_name`／`model_revision`；與輸入逐筆對應（順序、ID、metadata 都不變）。檔名與欄位清單待定。

## 2. 處理方法

- 模型：**`BAAI/bge-m3`**，由 sentence-transformers 本機載入，只用 **dense** 向量。
- 向量：**1024 維**，`normalize_embeddings=True`。
- **鎖定 revision**，並把 `model_name`、`model_revision` 寫入輸出。[切分](04_chunk.md) 的 tokenizer 應使用同一個 revision。
- 檢查 embedding 輸入（header 前綴 + child + special tokens）≤ 8192 tokens。

## 3. 為什麼這樣做

原定的 `sentence-transformers/all-MiniLM-L6-v2`（384 維）輸入上限只有 256 wordpieces（`max_seq_length` 256，契約要求每 chunk ≤ 254），迫使 chunk 切到 200 token 左右，且必須為 header 預留空間。改採子母分層後，parent 以章節為單位，需要能容納較長內容的模型；本專案也以學習成熟的 RAG 技術棧為目標之一。BGE-M3 的輸入上限為 8192 tokens，且支援多語言。

模型檔約 2.3 GB，首次執行時才從 Hugging Face 下載；建議使用 GPU（torch cu130 build，見 `AGENTS.md` §8）。

## 4. 否決的方案

- **維持 MiniLM**：256 的上限和章節級 parent 不相容。
- **`BAAI/bge-base-en-v1.5`**：只支援英文、上限 512 tokens；BGE-M3 支援多語言，上限也更長。
- **BGE-M3 的 sparse／ColBERT 模式**：需要新依賴 `FlagEmbedding`，日後要用須另行授權。

## 5. 驗證方式

執行 `python src/embed_chunks.py`（實作後）：

- 每筆 1024 維、norm = 1、`model_revision` 非空。
- 與輸入 child 逐筆對應（順序與 ID 一致、metadata 不變）。

## 6. 待定事項

| 事項 | 狀態 |
| --- | --- |
| embedding 輸入的拼接格式 | 實作時定義（舊格式為 slug 前綴 `{mod} \| {page} \| {section}`；建議改用原始 title／section 路徑，語意較好） |
| 鎖定的 model revision | 實作時定義（建議與切分量測使用的 tokenizer revision 一致） |
| 查詢語言策略（英文檢索 + 繁中回答） | BGE-M3 支援多語言，可重新評估（屬檢索端，範圍外） |
