# ADR-007：[5] 切分大小上限（parent ≤ 1024、child ≤ 256）

- **日期**：2026-10-23
- **狀態**：Accepted
- **影響階段**：[5] 切分（`src/chunk_pages.py`）；間接影響 [6] 的輸入長度與 Retrieval 的上下文預算
- **前提**：ADR-003（BGE-M3）、ADR-005（子母分層）
- **替代方案**：2048／256、2048／512

## 1. 背景

ADR-005 定了子母分層的框架，大小上限則留待量測。量測使用 `BAAI/bge-m3` tokenizer（revision `5617a9f61b028005a4858fdac845db406aefb181`），對象是 cleaned MD 正文，不含 frontmatter、`# title` 與 special tokens：

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

## 2. 決策

- **parent ≤ 1024 tokens**、**child ≤ 256 tokens**；超過上限即斷言失敗、exit 1。
- **上限只計算正文**：BGE-M3 tokenizer、`add_special_tokens=False`。標題路徑由 `MarkdownHeaderTextSplitter` 移入 metadata，不計入、也**不另外預留**；[6] 另行檢查「header 前綴 + child + special tokens ≤ 8192」。
- 使用者的考量：以現有資料為準、控制交給 LLM 的上下文大小；日後若長章節增加，再依檢索評估調整上限。

## 3. 理由

- **parent 1024**：目前最大 838，留約 20% 餘裕，現有資料沒有任何 parent 需要切分；與 child 的比例為 4 倍，和 LlamaIndex 相鄰兩層（2048／512／128）的比例一致；交給 LLM 的上下文較省、較聚焦。
- **child 256**：落在常見的 256–512 範圍；大於最長段落 237，任何段落都不必從中間切開；在現有資料上比 512 多切開 19 個 parent（29 對 10），子母分層現在就有作用。
- **不另外預留 header**：BGE-M3 上限 8192，embedding 輸入最多約 35 + 256 + 2 tokens，空間足夠。舊 MiniLM 必須預留，是因為 256 是模型的硬性上限。

## 4. 否決方案

- **2048／256**：日後 1024–2048 的長章節可以保持完整；但 parent／child 比例最大 8 倍，命中一個 child 可能送出 2048 tokens，成本較高、較不聚焦。現有資料上兩者結果完全相同，故先採較保守的 1024，日後再依評估調整。
- **2048／512**：最接近 LlamaIndex 的 4 倍比例；但現有資料只會切開 10 個 parent，子母分層的效果較弱。

## 5. 模擬結果（2026-10-23，overlap 32，暫存環境）

| 項目 | 結果 |
| --- | --- |
| parent | 302 個，最大 832（標題移入 metadata 後） |
| child | 348 個；中位數 99.5、最大 255 |
| 被切成多個 child 的 parent | 29 個 |
| 不到 50 tokens 的 child | 71 個（來自本身就很短的章節，與上限無關） |

## 6. 後果與風險

1. **日後長章節會被切開**：新增資料若出現超過 1024 tokens 的章節，會切成多個 parent，章節上下文會斷開。這時「超過上限的切法」（例如先依 `###`，再依大小）就很重要，必須在 [5] 實作時定好；若長章節變多，可依檢索評估將上限提高到 2048。
2. **child 多切並非沒有成本**：child 越多，同一個 parent 的 child 越容易佔滿 top-k 名額，所以 Retrieval 須依 parent 去重；過短的 child 語意較弱。
3. **parent／child 比例最大 4 倍**：命中一個 child 時，送給 LLM 的上下文最多 1024 tokens；Retrieval（範圍外）仍須依 parent 去重並控制 top-k。
4. 本 ADR 的上限只保證現有資料切分合理，**沒有經過檢索評估**；之後若建立評估集，可據以調整。

## 7. 仍待定（見 `ARCHITECTURE.md` §8）

- child overlap（模擬使用 32，為 child 的 12.5%；業界常見 10–20%）
- Recursive 的切分點順序（模擬使用 `"\n"`、`". "`、`" "`）
- parent 超過上限時的切法
- 開頭段落的 parent 歸屬、極短 parent 是否合併
- ID 格式、parent 產物格式

## 8. 相關文件

- `docs/adr/ADR-003-bge-m3-embedding.md`
- `docs/adr/ADR-005-parent-child-chunking.md`
- `ARCHITECTURE.md` §5 [5]
- 參考：[LlamaIndex HierarchicalNodeParser](https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/hierarchical/)、[LangChain Parent Document Retriever](https://python.langchain.com/docs/how_to/parent_document_retriever)、[arXiv 2407.19794](https://arxiv.org/html/2407.19794v1)
