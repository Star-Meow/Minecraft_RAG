# ADR-003：Embedding 模型改用 BGE-M3

- **日期**：2026-10-22
- **狀態**：Accepted
- **影響階段**：[5] 切分（tokenizer 與大小上限）、[6] Embedding、[7] 入庫（向量維度）
- **取代**：原定 `sentence-transformers/all-MiniLM-L6-v2`（384 維、`max_seq_length` 256、每 chunk ≤ 254 wordpieces）
- **替代方案**：維持 MiniLM、`BAAI/bge-base-en-v1.5`

## 1. 背景

原定的 MiniLM 輸入上限只有 256 wordpieces，迫使 chunk 切到 200 token 左右。改採子母分層（ADR-005）後，parent 以章節為單位，需要能容納較長內容的模型；同時本專案以學習成熟的 RAG 技術棧為目標之一。

## 2. 決策

- 模型：**`BAAI/bge-m3`**，由 `sentence-transformers` 本機載入，只使用 **dense** 向量。
- 向量：**1024 維**，`normalize_embeddings=True`。
- **鎖定 revision**，並把它記錄在輸出中（沿用原本的可重現性要求）。
- [5] 計數用 **BGE-M3 自己的 tokenizer**；模型輸入上限為 8192 tokens。child／parent 的大小區間另依實測決定（見 ADR-005）。
- 不採用 sparse／ColBERT 模式：需要新依賴 `FlagEmbedding`（AGENTS §8），日後要用須另行授權。

## 3. 否決方案

- **維持 MiniLM**：256 的上限和章節級 parent 不相容。
- **`bge-base-en-v1.5`**：只支援英文、上限 512 tokens；BGE-M3 支援多語言，上限也更長。

## 4. 後果

1. 移除「每 chunk ≤ 254 wordpieces」與「`chunk_size` 200」；新的上限在 [5] 實作前量測後定案。
2. [7] 的向量欄位為 1024 維（schema 其餘部分仍擱置）。
3. 模型檔約 2.3 GB，首次執行 [6] 時下載；建議使用 GPU（torch cu130 build，見 AGENTS §8）。
4. BGE-M3 支援多語言，「英文檢索 + 繁中回答」的查詢策略可以重新評估。這屬於另一個決策，列在 `ARCHITECTURE.md` 待確認事項。

## 5. 相關文件

- `docs/adr/ADR-005-parent-child-chunking.md`
- `ARCHITECTURE.md` §5 [5]／[6]／[7]
- `AGENTS.md` §8
