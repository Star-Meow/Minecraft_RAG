# ADR-005：[5] 採子母分層切分（parent-child）

- **日期**：2026-10-22
- **狀態**：Accepted（框架已定；參數、ID 與欄位格式待 [5] 實作時定義）
- **影響階段**：[5] 切分、[6] Embedding、[7] 入庫
- **前提**：ADR-003（BGE-M3）、ADR-004（cleaned MD 帶 `##`／`###`）
- **替代方案**：單層固定大小切分、單層依章節切分、以整頁為 parent

## 1. 背景

資料來源是指南型文件，內容以「頁 → 章節」組織。單層切分會遇到取捨：chunk 小，檢索精準但交給 LLM 的上下文片段化；chunk 大，上下文完整但向量語意被稀釋。業界常見的做法是子母分層，例如 LangChain ParentDocumentRetriever、LlamaIndex HierarchicalNodeParser：用小塊檢索，回傳大塊當上下文。

## 2. 決策

- **parent**：一個 `##` 章節（底下的 `###` 併入所屬的 `##`）；頁面沒有 `##` 時，整頁為一個 parent。parent 超過上限時再切成多個 parent。
- **child**：在 parent 內切出的小片段，用於檢索。
- **工具**：`langchain-text-splitters` 的 `MarkdownHeaderTextSplitter`（章節邊界）+ `RecursiveCharacterTextSplitter`（大小切分），並以 BGE-M3 tokenizer 計數。
- **embedding 範圍**：只對 child 做 embedding。
- **儲存模式**：docstore 模式。child 的向量進向量庫；parent 文件另外保存，並且能由 child 上的 parent 參照找回。[7] 入庫直接讀 [5] 的 parent 產物，不經 [6] 轉交。
- **provenance**：parent 和 child 都必須帶 `source_url`、`title`、`mod`、`chapter`、`page`、`section`（標題路徑）與版本資訊（AGENTS §3.1）。

## 3. 待定（不在本 ADR 預先虛構）

| 項目 | 狀態 |
| --- | --- |
| child／parent 大小區間、overlap | 先用 BGE-M3 tokenizer 量測 cleaned MD 的 token 分布再定案 |
| ID 格式（是否加入 chapter 以解決跨 chapter 同名頁碰撞） | [5] 實作時定案 |
| parent 產物的檔名與 schema | [5] 實作時定案 |
| [6] embedding 輸入格式（slug 前綴或原始 title／section 路徑） | [6] 實作時定案 |
| [7] 資料表、入庫方式、索引 | 仍擱置 |

## 4. 否決方案

- **單層固定大小**：無法利用指南的章節結構，以後有長篇文章時也會從章節中間切斷。
- **單層依章節切**：章節長度落差大，長章節的向量語意會被稀釋。
- **只用整頁當 parent**：多數頁面本身就比 child 還短，分層幾乎沒有作用；採用 ADR-004 的章節結構後已不需要。

## 5. 後果

1. [5] 的輸出由一份 chunk 變成 child + parent 兩類產物；Chunk Schema 要新增 parent 參照。
2. 檢索端（範圍外）需要依 parent 去重後再交給 LLM。
3. 舊契約中「`chunk_id` 不含 chapter 可能碰撞」的問題，會在 ID 格式定案時一併處理。

## 6. 相關文件

- `docs/adr/ADR-003-bge-m3-embedding.md`
- `docs/adr/ADR-004-heading-structure.md`
- `ARCHITECTURE.md` §5 [5]／[6]／[7]
