# 向量化

> 職責：把 child chunks 轉成向量。
> 上一個階段：[切分](04_chunk.md)；下一個階段：[入庫](06_index.md)

程式：`src/embed_chunks.py`

## 1. 輸入與輸出

### 輸入

[切分](04_chunk.md) 的 `data/processed/chunks/<version>/children.jsonl`（parent 不進 embedding）。

### embedding 輸入格式（2026-11-05 人工裁定）

```python
embedding_input = f"{section}\n\n{text}"
```

- `section` 取 child 的 `section` 欄位原文（已含頁面 `title` 為第一段，不另加 title）。
- 所有 child 套用同一規則，不做條件判斷；不附 parent；不改寫 `text` 與 `section`（禁止 slug 化）。
- 每頁第一個 child 的 `text` 以 `# <title>` 開頭，標題會與 `section` 重複，接受之。
- 含 special tokens 的 token 數須 ≤ 8192（BGE-M3 tokenizer 斷言）；輸入 token 分布（最大值、平均）寫入報告。

### 輸出

| 檔案 | 用途 | 讀取者 |
| --- | --- | --- |
| `data/processed/embeddings/<version>/children_embeddings.jsonl` | child + 向量 | [入庫](06_index.md) |
| `reports/embedding_report.md` | 對帳、輸入 token 分布、模型與 revision | 人工 |

一行一筆、UTF-8、順序與 `children.jsonl` 完全一致。欄位 = `children.jsonl` 的 11 個原欄位原樣帶入（`chunk_id`、`parent_id`、`text`、`title`、`source_url`、`version`、`mod`、`chapter`、`page`、`section`、`token_count`；定義見 [04_chunk.md](04_chunk.md) §1），加上：

| 欄位 | 說明 |
| --- | --- |
| `embedding_input` | 實際送入模型的字串（利於追溯） |
| `embedding` | 1024 維 float list（dense、已正規化） |
| `model_name` | `BAAI/bge-m3` |
| `model_revision` | 鎖定的 commit hash |

不新增其他欄位；`embedding_input` 的 token 數只放報告，不逐筆寫入。

輸出目錄由向量化擁有：處理完成且有產出後，才清空並重建 `embeddings/<version>/`（範圍限定、路徑斷言；2026-11-05 授權）。

## 2. 處理方法

- 模型：**`BAAI/bge-m3`**，revision **`5617a9f61b028005a4858fdac845db406aefb181`**，由 sentence-transformers 本機載入（離線，`HF_HUB_OFFLINE=1`），只用 **dense** 向量。
- 向量：**1024 維**，`normalize_embeddings=True`。
- revision 以常數鎖定，並把 `model_name`、`model_revision` 寫入輸出。[切分](04_chunk.md) 的 tokenizer 使用同一個 revision（`chunk_pages.py` 的 `TOKENIZER_REVISION`，已核對一致；不一致即中止）。
- 缺少 provenance 欄位（`chunk_id`、`source_url`、`title`、`version`、`mod`、`chapter`、`page`、`section`）或 `chunk_id` 重複 → 中止。
- `--dry-run`：只組 embedding 輸入、做 tokenizer 斷言與對帳並印出摘要；**不載入模型、不初始化 CUDA、不寫任何檔案**。
- 裝置：**必須使用 GPU（CUDA）**；`SentenceTransformer` 明確指定 `device="cuda"`。非 dry-run 在載入模型、寫檔、刪檔之前先檢查 `torch.cuda.is_available()`，不可用即中止（exit 1），不退回 CPU，也不改動既有輸出。實際裝置名稱與 torch 版本寫入 stdout 與報告「設定」段。
- 批次大小為實作細節，見程式常數。

## 3. 為什麼這樣做

### 模型

原定的 `sentence-transformers/all-MiniLM-L6-v2`（384 維）輸入上限只有 256 wordpieces（`max_seq_length` 256，契約要求每 chunk ≤ 254），迫使 chunk 切到 200 token 左右，且必須為 header 預留空間。改採子母分層後，parent 以章節為單位，需要能容納較長內容的模型；本專案也以學習成熟的 RAG 技術棧為目標之一。BGE-M3 的輸入上限為 8192 tokens，且支援多語言。

模型檔約 2.3 GB，已由使用者授權下載至本機快取；需要 NVIDIA GPU（torch cu130 build，見 `AGENTS.md` §8）。

### embedding 輸入：child 前加 `section`，不附 parent（2026-11-05 人工裁定）

業界慣例是對 child 補輕量上下文（標題或章節路徑），讓只有一句話的 child 仍帶有「它屬於哪一頁哪一節」的語意。不附 parent，因為同一 parent 的 child 若都帶入整個 parent，向量會趨同，檢索粒度退化，子母分層的意義消失。`section` 已含頁面 `title` 為第一段，所以不另加 title 前綴。所有 child 一律套用，規則單純、可重現。

## 4. 否決的方案

- **維持 MiniLM**：256 的上限和章節級 parent 不相容。
- **`BAAI/bge-base-en-v1.5`**：只支援英文、上限 512 tokens；BGE-M3 支援多語言，上限也更長。
- **CUDA 不可用時退回 CPU**（2026-11-05 人工裁定）：CPU 向量與 GPU 向量可能有數值差異，破壞輸出的可重現性；不可用時直接中止，由人處理環境。
- **BGE-M3 的 sparse／ColBERT 模式**：需要新依賴 `FlagEmbedding`，日後要用須另行授權。
- **embedding 輸入附整個 parent**：同 parent 的 child 向量趨同，檢索粒度退化。
- **另加 title 前綴**：`section` 已含 title，重複。
- **LLM 生成上下文（Contextual Retrieval）**：需要新外部服務與成本，超出目前範圍。
- **條件式前綴**（只對短 child 加）：規則不單純，行為難以重現。
- **純 `text`（不加前綴）**：保留為日後對照組，見 §6。

## 5. 驗證方式

- `python src/embed_chunks.py --dry-run`（不需 GPU）：輸入筆數與 `children.jsonl` 一致、`chunk_id` 唯一；每筆 `embedding_input` 恰為 `f"{section}\n\n{text}"`；每筆 token 數（含 special tokens）≤ 8192；連跑兩次輸出一致。
- `python src/embed_chunks.py`（需 CUDA GPU）：每筆 1024 維、`model_revision` 非空；與輸入 child 逐筆對應（順序與 ID 一致、11 個原欄位不變）。
  - norm = 1，容差 **1e-4**（`NORM_TOLERANCE`；float32 正規化後誤差通常在 1e-6 量級）。
  - 連跑兩次：非向量欄位逐位元相同；向量採容差比對，**每個元素絕對誤差 ≤ 1e-5**，實測最大誤差於驗收時回報。超過時不放寬標準，如實回報後由人工裁定。
- CUDA 不可用（例如 `CUDA_VISIBLE_DEVICES=-1`）時執行：結束碼 1、不載入模型、`embeddings/<version>/` 與報告不變（雜湊比對）。空字串不會隱藏 GPU（`torch.cuda.is_available()` 仍為 True）；執行前須先確認 `torch.cuda.is_available()` 為 False 再解讀結果。
- dry-run 的性質是「不載入模型權重、不初始化 CUDA、不寫檔」；`transformers`／`sentence_transformers`／`torch` 可能因 `chunk_pages` 的匯入而被載入，不在此限。

## 6. 待定事項

| 事項 | 狀態 |
| --- | --- |
| A（純 `text`）與 B（`section` + `text`）的檢索效果比較 | 評估資料出現後再比較 |
| 查詢語言策略（英文檢索 + 繁中回答） | BGE-M3 支援多語言，可重新評估（屬檢索端，範圍外） |
