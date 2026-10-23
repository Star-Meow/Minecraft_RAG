# 切分

> 職責：把 cleaned MD 依章節切成 parent，再在 parent 內切出 child（子母分層）。只負責切分，不處理資料品質。
> 上一個階段：[清理](03_clean.md)；下一個階段：[向量化](05_embed.md)

程式：`src/chunk_pages.py`（**尚未實作**；本文件只寫已定的方法，待定項目不預先虛構）

## 1. 輸入與輸出

### 輸入

只讀 `data/processed/cleaned/**/*.md`（格式見 [03_clean.md](03_clean.md)）；不讀 extracted JSON 或 manifest。

| 類別 | 欄位 | 來源 |
| --- | --- | --- |
| 結構性 | `version`／`mod`／`chapter`／`page` | 目錄路徑（slug 形式）；frontmatter 同名欄位不讀 |
| 內容性 | `title`／`source_url` | frontmatter（不重新計算、不改寫）；`source_url` 為空 → 該頁不產出、報錯 |
| 章節 | `section` | 標題路徑（如 `Crafting Terminal > The UI`），由 `MarkdownHeaderTextSplitter` 提供 |

路徑讀法：

```python
page_slug = md_file.stem                          # "energy"
chapter   = md_file.parent.name                   # "ae2-mechanics"
mod_slug  = md_file.parent.parent.name            # "applied-energistics-2"
version   = md_file.parent.parent.parent.name     # "1.21.1"
```

### 輸出

- **parent 文件**：交給 LLM 當上下文；[入庫](06_index.md) 直接讀取。
- **child chunks**：用於檢索；[向量化](05_embed.md) 讀取。

兩者都必須帶完整 provenance：`source_url`、`title`、`mod`、`chapter`、`page`、`section`、版本；child 必須能對應回所屬的 parent。檔名、ID 與 schema 待定（見 §6）。

### 範例（示意，以 `ae2-mechanics/energy` 試切）

```text
整頁（651 tokens）
 ├─ parent 1  section = "Energy"            130 tokens   ← 開頭段落（歸屬方式待定）
 │   └─ child 1.1  130
 ├─ parent 2  section = "Energy Accepting"  182 tokens
 │   └─ child 2.1  182
 └─ parent 3  section = "Energy Storage"    339 tokens
     ├─ child 3.1  238   結尾 "… ME Controllers have a small amount of internal energy storage, 8,000 AE"
     └─ child 3.2  117   開頭 "ME Controllers have a small amount of internal energy storage, 8,000 AE"（overlap）
```

標題行由 splitter 從正文移出，存入 metadata（例如 `{'h1': 'Energy', 'h2': 'Energy Storage'}`）；frontmatter 在切分前去除。

## 2. 處理方法

- **parent**：一個 `##` 章節（`###` 併入所屬的 `##`）；沒有 `##` 的頁，parent = 整頁；超過上限時再切。
- **child**：在 parent 內切出的片段；只有 child 進入 embedding。
- **工具**：`MarkdownHeaderTextSplitter`（章節邊界）+ `RecursiveCharacterTextSplitter`（大小切分），皆來自 langchain-text-splitters。
- **大小上限**：**parent ≤ 1024 tokens**、**child ≤ 256 tokens**。
  - 以 BGE-M3 tokenizer 計算（`add_special_tokens=False`），選型見 [05_embed.md](05_embed.md)。
  - **只算正文**：標題路徑存於 metadata，不計入、也不另外預留。
  - 超過上限即斷言失敗、exit 1。
- slug 只用於路徑、ID 與 `mod`／`chapter`／`page`；`text`、`title`、`section` 禁止 slug 化。
- `title` 欄位原封來自 frontmatter；下游生成答案直接用 chunk 的 `title`，不回查 extracted JSON。`title`（頁面標題原文，如 `Energy`）與 `page`（slug，如 `energy`）是兩個獨立欄位，不可互相替代。

## 3. 為什麼這樣做

### 子母分層

資料是指南型文件，以「頁 → 章節」組織。單層切分有取捨：chunk 小，檢索精準但上下文片段化；chunk 大，上下文完整但向量語意被稀釋。子母分層用小塊檢索、回傳大塊當上下文，是業界常見做法（LangChain ParentDocumentRetriever、LlamaIndex HierarchicalNodeParser）。章節結構由 [抽取](02_extract.md) 與 [清理](03_clean.md) 保留下來，所以 parent 可以直接用 `##` 章節。

### 大小上限：1024／256

量測（2026-10-23；`BAAI/bge-m3` tokenizer，revision `5617a9f61b028005a4858fdac845db406aefb181`；對象是 cleaned MD 正文，不含 frontmatter、`# title` 與 special tokens）：

| 對象 | 數量 | 中位數 | p95 | 最大 |
| --- | --- | --- | --- | --- |
| parent 候選（`##` 章節、開頭段落、沒有 `##` 的整頁） | 302 | — | — | 838 |
| `##` 章節（含 `###`） | 187 | 108 | 411 | 838 |
| 整頁 | 119 | 247 | 1031 | 2645 |
| 單一段落（行） | — | — | — | 237 |
| 標題路徑（title > section） | 346 | 8 | 17 | 35 |

業界參考（2026-10-23 查證）：

- LlamaIndex `HierarchicalNodeParser`：未指定時預設 `chunk_sizes = [2048, 512, 128]` tokens。
- LangChain `ParentDocumentRetriever`：官方範例 parent 2000 字元、child 400 字元。
- 研究與廠商建議：常見預設 512，256 與 1024 是常見的替代值；最佳值須用自己的資料評估。

理由：

- **parent 1024**：目前最大 838，留約 20% 餘裕，現有資料沒有任何 parent 需要切分；與 child 的比例為 4 倍，和 LlamaIndex 相鄰兩層的比例一致；交給 LLM 的上下文較省、較聚焦。
- **child 256**：落在常見的 256–512 範圍；大於最長段落 237，任何段落都不必從中間切開；在現有資料上比 512 多切開 19 個 parent（29 對 10），子母分層現在就有作用。
- **不另外預留 header**：BGE-M3 上限 8192，embedding 輸入最多約 35 + 256 + 2 tokens。舊模型 MiniLM 必須預留，是因為 256 是它的硬性上限。

模擬結果（2026-10-23，overlap 32，暫存環境）：parent 302 個（最大 832）；child 348 個（中位數 99.5、最大 255）；被切成多個 child 的 parent 29 個；不到 50 tokens 的 child 71 個（來自本身就很短的章節，與上限無關）。

## 4. 否決的方案

- **單層固定大小切分**：無法利用指南的章節結構，日後有長篇文章時會從章節中間切斷。
- **單層依章節切分**：章節長度落差大，長章節的向量語意會被稀釋。
- **只用整頁當 parent**：多數頁面本身就比 child 還短，分層幾乎沒有作用；整頁最大 2645 tokens 也太大。
- **2048／256**：日後 1024–2048 的長章節可保持完整，但 parent／child 比例最大 8 倍，成本較高、較不聚焦。現有資料上兩者結果相同，先採較保守的 1024，日後依評估調整。
- **2048／512**：最接近 LlamaIndex 的比例，但現有資料只會切開 10 個 parent，子母分層效果較弱。

## 5. 驗證方式

執行 `python src/chunk_pages.py`（實作後）：

- 每筆可解析，provenance 欄位非空。
- 每個 child 都能對應到 parent。
- parent ≤ 1024、child ≤ 256 tokens（BGE-M3 tokenizer，只算正文）斷言通過。
- 欄位清單待 §6 定案後補入。

## 6. 待定事項與風險

| 事項 | 狀態 |
| --- | --- |
| child overlap、Recursive 切分點 | 實作時定義（模擬使用 overlap 32，即 child 的 12.5%；切分點 `"\n"`、`". "`、`" "`；業界常見 overlap 10–20%） |
| parent 超過 1024 時的切法 | 實作時定義（建議先依 `###`，再依大小）；上限較低，日後長章節較容易碰到 |
| 第一個 `##` 之前的開頭段落歸屬 | 實作時定義（建議獨立成 parent，`section` = 頁面標題） |
| 極短 parent 是否合併 | 實作時定義 |
| ID 格式（含跨 chapter 同名頁碰撞）、parent 產物的檔名與 schema | 實作時定義 |
| frontmatter 是否會被 `MarkdownHeaderTextSplitter` 當成內容 | 實作時驗證（試切時先去除 frontmatter） |

風險：

- **長章節會被切開**：新資料若出現超過 1024 tokens 的章節，章節上下文會斷開；若長章節變多，可依評估將上限提高到 2048。
- **child 多切並非沒有成本**：同一 parent 的 child 容易佔滿 top-k，檢索端須依 parent 去重；過短的 child 語意較弱。
- 上限只保證現有資料切分合理，**沒有經過檢索評估**。

參考：[LlamaIndex HierarchicalNodeParser](https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/hierarchical/)、[LangChain Parent Document Retriever](https://python.langchain.com/docs/how_to/parent_document_retriever)、[arXiv 2407.19794](https://arxiv.org/html/2407.19794v1)
