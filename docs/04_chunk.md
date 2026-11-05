# 切分

> 職責：把 cleaned MD 依章節切成 parent，再在 parent 內切出 child（子母分層）。只負責切分，不處理資料品質。
> 上一個階段：[清理](03_clean.md)；下一個階段：[向量化](05_embed.md)

程式：`src/chunk_pages.py`

## 1. 輸入與輸出

### 輸入

只讀 `data/processed/cleaned/**/*.md`（格式見 [03_clean.md](03_clean.md)）；不讀 extracted JSON 或 manifest。

| 類別 | 欄位 | 來源 |
| --- | --- | --- |
| 結構性 | `version`／`mod`／`chapter`／`page` | 目錄路徑（slug 形式）；frontmatter 同名欄位不讀 |
| 內容性 | `title`／`source_url` | frontmatter（不重新計算、不改寫）；`source_url` 為空 → 該頁不產出、報錯 |
| 章節 | `section` | 標題原文路徑，由 `MarkdownHeaderTextSplitter` 的 metadata 與 parent 內的 `###` 行組成（見下方輸出） |

路徑讀法：

```python
page_slug = md_file.stem                          # "energy"
chapter   = md_file.parent.name                   # "ae2-mechanics"
mod_slug  = md_file.parent.parent.name            # "applied-energistics-2"
version   = md_file.parent.parent.parent.name     # "1.21.1"
```

### 輸出

| 檔案 | 用途 | 讀取者 |
| --- | --- | --- |
| `data/processed/chunks/<version>/parents.jsonl` | parent：交給 LLM 當上下文 | [入庫](06_index.md) |
| `data/processed/chunks/<version>/children.jsonl` | child：用於檢索 | [向量化](05_embed.md) |
| `reports/chunking_report.md` | 對帳、token 分布、短 parent 清單、錯誤頁 | 人工 |

兩個 JSONL 皆一行一筆、UTF-8、依 cleaned MD 路徑與頁內順序排列。欄位：

| 欄位 | parent | child | 說明 |
| --- | --- | --- | --- |
| `parent_id` | ✓ | ✓ | `<version>:<mod>:<chapter>:<page>:pNN`（頁內順序，從 01 起） |
| `chunk_id` | — | ✓ | `<parent_id>:cNN`（parent 內順序，從 01 起） |
| `text` | ✓ | ✓ | 正文，**含標題行**（`#`／`##`／`###`） |
| `title`／`source_url` | ✓ | ✓ | frontmatter 原值 |
| `version`／`mod`／`chapter`／`page` | ✓ | ✓ | 目錄路徑（slug） |
| `section` | ✓ | ✓ | 標題原文路徑，以 ` > ` 連接。parent：開頭段落 = `title`、`##` 章節 = `title > ##`；child：parent 的路徑再加上 child 起點所在的 `###`（如 `Autocrafting > Pattern Providers > Variants`） |
| `token_count` | ✓ | ✓ | BGE-M3 tokenizer，`add_special_tokens=False`，含標題行 |

tokenizer 名稱與 revision 記在報告，不逐筆寫入。ID 為頁內序號：頁內章節增刪會使序號位移，產物整批覆寫，可接受。

### 範例（`ae2-mechanics/energy` 實際輸出）

```text
整頁
 ├─ p01  section = "Energy"                      132 tokens   ← 開頭段落獨立成 parent，text 以 "# Energy" 開頭
 │   └─ c01  132
 ├─ p02  section = "Energy > Energy Accepting"   186 tokens   ← text 以 "## Energy Accepting" 開頭
 │   └─ c01  186
 └─ p03  section = "Energy > Energy Storage"     342 tokens
     ├─ c01  241   結尾 "… ME Controllers have a small amount of internal energy storage, 8,000 AE"
     └─ c02  117   開頭 "ME Controllers have a small amount of internal energy storage, 8,000 AE"（overlap）
```

frontmatter 在切分前去除；標題行留在 `text`，同時以 metadata 組成 `section`。

## 2. 處理方法

- **parent**：`MarkdownHeaderTextSplitter` 依 `#`／`##` 切（`strip_headers=False`，標題行留在正文）。
  - 一個 `##` 章節一個 parent；`###` 併入所屬的 `##`。
  - 第一個 `##` 之前的開頭段落獨立成 parent，`section` = 頁面 `title`；沒有 `##` 的頁，整頁即一個 parent。
  - 極短 parent 不合併（報告列出 < 50 tokens 者）。
- **child**：`RecursiveCharacterTextSplitter` 在 parent 內切；只有 child 進入 embedding。
  - `chunk_size` 256、`chunk_overlap` 32（12.5%），長度以 tokenizer 計算。
  - 切分點依序 `"\n"`、`". "`、`" "`、`""`；`keep_separator="end"`（句點留在前一段結尾）。
- **大小上限**：**parent ≤ 2048 tokens**、**child ≤ 256 tokens**。
  - 以 BGE-M3 tokenizer 計算（`transformers.AutoTokenizer`，revision 鎖定，`add_special_tokens=False`），選型見 [05_embed.md](05_embed.md)。
  - **含標題行**：標題留在正文，一併計入。
  - 超過上限即中止、不寫任何產出、exit 1，由人工處理（不自動再切）。
- **輸出目錄由切分擁有**：處理完成、沒有超限且有產出後，才清空並重建 `chunks/<version>/`（範圍限定、路徑斷言；2026-10-29 授權）。
- `source_url` 或 `title` 為空的頁不產出，列入報告錯誤，exit 1。
- slug 只用於路徑、ID 與 `mod`／`chapter`／`page`；`text`、`title`、`section` 禁止 slug 化。
- `title` 欄位原封來自 frontmatter；下游生成答案直接用 chunk 的 `title`，不回查 extracted JSON。`title`（頁面標題原文，如 `Energy`）與 `page`（slug，如 `energy`）是兩個獨立欄位，不可互相替代。

## 3. 為什麼這樣做

### 子母分層

資料是指南型文件，以「頁 → 章節」組織。單層切分有取捨：chunk 小，檢索精準但上下文片段化；chunk 大，上下文完整但向量語意被稀釋。子母分層用小塊檢索、回傳大塊當上下文，是業界常見做法（LangChain ParentDocumentRetriever、LlamaIndex HierarchicalNodeParser）。章節結構由 [抽取](02_extract.md) 與 [清理](03_clean.md) 保留下來，所以 parent 可以直接用 `##` 章節。

### 大小上限：2048／256

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

- **parent 2048**（2026-10-24 由 1024 調整，人工裁定）：加上 `## Recipes` 後，`storage_cells` 的配方段達 1308 tokens，超過 1024；改為 2048 後現有資料**沒有任何 parent 需要切分**，章節（含配方段）都保持完整。2048 與 LlamaIndex 最上層相同。最初以舊 HTML 量測時（最大 838）選擇 1024，理由是交給 LLM 的上下文較省、比例為 4 倍。
- **child 256**：落在常見的 256–512 範圍；大於最長段落 237，任何段落都不必從中間切開；在現有資料上比 512 多切開 19 個 parent（29 對 10），子母分層現在就有作用。
- **不另外預留 header**：BGE-M3 上限 8192，embedding 輸入最多約 35 + 256 + 2 tokens。舊模型 MiniLM 必須預留，是因為 256 是它的硬性上限。（2026-10-29 起標題行留在正文、計入上限，見下方「標題行保留在正文」。）

**重新量測（2026-10-24，站台改為靜態 HTML，加上 `## Recipes`，並在抽取改為 BS4 整理輸入後重測）**：parent 387 個，中位數 90、p95 **419**、最大 **1308**（`storage_cells` 的 `## Recipes`，該頁配方很多）；超過 1024 的只有這 1 個，因此上限改為 2048（見上方理由）。最長段落 237。上表為舊 HTML 的量測，僅供對照。

（整理輸入前的量測：中位數 90、p95 433、最大 1308，其餘最大 1020〔`storage-types` 的開頭段落〕；`## Recipes` 共 85 個，中位數 48。）

模擬結果（2026-10-23，overlap 32，暫存環境）：parent 302 個（最大 832）；child 348 個（中位數 99.5、最大 255）；被切成多個 child 的 parent 29 個；不到 50 tokens 的 child 71 個（來自本身就很短的章節，與上限無關）。

### 標題行保留在正文（2026-10-29 人工裁定）

業界兩種做法都有（2026-10-29 查證原始碼）：LangChain `MarkdownHeaderTextSplitter` 預設 `strip_headers=True`，標題只進 metadata；LlamaIndex `MarkdownNodeParser` 把標題行留在 node 的 text，祖先標題另存 `header_path`。兩者都把標題路徑存在 metadata。
採保留：parent 交給 LLM 時自帶 `##`／`###` 結構，不必在檢索端另外組回標題。代價是 token 上限改為含標題行計算；保留後的量測仍未超限（parent 最大 1308、child 最大 256）。

### 超過上限即中止（2026-10-29 人工裁定）

parent 上限是 LLM 上下文的成本控制，不是正確性限制；業界多半自動再切（LangChain `parent_splitter`）或不設上限。本專案選擇中止：現有資料沒有任何 parent 超過，官方指南更新少、pipeline 有人工監看，超限時由人決定提高上限或改規則（處理結果須寫回參數或本文件，不依賴未記錄的人工狀態）。

### 最近一次執行結果（2026-10-29）

119 頁輸入、119 頁產出、錯誤 0；parent 387 個（中位數 91、p95 415、最大 1308）；child 466 個（中位數 101、p95 249、最大 256）；被切成多個 child 的 parent 50 個；< 50 tokens 的 parent 列於報告。驗收（§5）全數通過，連跑兩次輸出相同。

## 4. 否決的方案

- **單層固定大小切分**：無法利用指南的章節結構，日後有長篇文章時會從章節中間切斷。
- **單層依章節切分**：章節長度落差大，長章節的向量語意會被稀釋。
- **只用整頁當 parent**：多數頁面本身就比 child 還短，分層幾乎沒有作用；整頁最大 2645 tokens 也太大。
- **1024／256**（2026-10-23 曾採用）：交給 LLM 的上下文較省；但加上 `## Recipes` 後已有 1 個 parent（1308）超過上限，必須切開配方段。
- **維持 1024，超過時依行切成多個 parent**：配方不會被切壞，但同一頁的配方會分散在多個 parent；改為 2048 較單純。
- **2048／512**：最接近 LlamaIndex 的比例，但現有資料只會切開 10 個 parent，子母分層效果較弱。
- **開頭段落併入第一個 `##`／複製到每個 parent**：前者讓總述的 `section` 標示不準；後者重複內容、parent 變大。
- **合併極短 parent**：沒有檢索評估前無法證明效益，且 `section` 會變成多值；日後要改只需重跑。
- **`strip_headers=True`（LangChain 預設）**：標題只在 metadata，檢索端與 embedding 輸入都要另外組回。
- **parent 超限時自動依行切成多個 parent**：同一章節會散成多個 parent；現有資料不會觸發，先以中止處理。
- **單一 `chunks.jsonl` 以欄位區分 parent／child**：[向量化](05_embed.md) 須自行過濾，容易誤把 parent 送進 embedding。
- **內容雜湊 ID**：內容不變時 ID 穩定，但不可讀、看不出歸屬；產物不做 history，穩定性的價值有限。

## 5. 驗證方式

執行 `python src/chunk_pages.py`：

- 結束碼 0；報告對帳：有產出頁數 + 錯誤頁數 = cleaned 頁數。
- 每筆可解析，§1 欄位齊全；provenance 欄位（`source_url`、`title`、`version`、`mod`、`chapter`、`page`、`section`）非空。
- 每個 child 的 `parent_id` 都找得到 parent，每個 parent 至少一個 child；`parent_id`、`chunk_id` 唯一。
- 以 tokenizer 重新計數：parent ≤ 2048、child ≤ 256（含標題行），且等於 `token_count`。
- child 的 `title`／`source_url`／`version`／`mod`／`chapter`／`page` 與所屬 parent 相同，`section` 以 parent 的 `section` 開頭。
- 內容涵蓋：每頁所有 parent 的 `text` 依序串接，逐行去除前後空白並略過空行後，等於 cleaned 正文（見 §6 的空白差異）。
- 每個 child 的 `text` 是所屬 parent `text` 的子字串。
- `title`、`section` 未被 slug 化。
- 連跑兩次輸出相同。

## 6. 待定事項與風險

目前沒有待定事項。

已定（2026-10-29）：開頭段落獨立成 parent；極短 parent 不合併；標題行保留；overlap 32 與切分點；超過上限即中止；ID 格式；兩個 JSONL 產物與欄位；切分擁有並重建 `chunks/<version>/`。frontmatter 在切分前去除，不會被 splitter 當成內容。

已定（2026-10-30，人工裁定）：`MarkdownHeaderTextSplitter` 的空白處理照工具原樣保留，不做後處理。splitter 會逐行去除前後空白，並以 `"  \n"` 連接被空行隔開的區塊。影響：每頁 `# <title>` 行尾多兩個空格（119 個 parent）；2 頁共 17 行巢狀清單失去縮排（`terminals`、`throw-in-water-automation`）。

風險：

- **parent／child 比例最大 8 倍**：命中一個 256 的 child 時，可能送出最多 2048 tokens 的 parent；成本與聚焦度由檢索端的 top-k 與 parent 去重控制。
- **超過 2048 的章節仍會被切開**：新資料若出現更長的章節，章節上下文會斷開。
- **child 多切並非沒有成本**：同一 parent 的 child 容易佔滿 top-k，檢索端須依 parent 去重；過短的 child 語意較弱。
- 上限只保證現有資料切分合理，**沒有經過檢索評估**。

參考：[LlamaIndex HierarchicalNodeParser](https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/hierarchical/)、[LangChain Parent Document Retriever](https://python.langchain.com/docs/how_to/parent_document_retriever)、[arXiv 2407.19794](https://arxiv.org/html/2407.19794v1)
