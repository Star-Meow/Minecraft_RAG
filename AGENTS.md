# AGENTS.md — Project Engineering Contract

本文件是 AI Agent 在本專案中工作的永久工程契約。
本文件描述「應遵守的規則」，不描述會隨時間變動的專案狀態。

- 專案狀態與進度：`recall.md`
- 人類使用說明：`README.md`
- 一次性稽核快照（完整遍歷結果）：`REVIEW.md`

## 1. Project Mission

### 1.1 Purpose

**Minecraft AE2 RAG Assistant**：依據 AE2 官方 Minecraft 1.21.1 指南回答知識問題的 RAG 助手。答案附可點擊來源；官方文件不足以確認時，回答「目前官方文件不足以確認」。

### 1.2 Scope

- **包含（MVP）**：人工指定的官方指南頁面（目標 15～20 頁）之擷取、清理、切分、向量索引、附來源問答、Streamlit 展示。
- **不包含**：modpack JAR 解析、KubeJS／CraftTweaker 覆寫解析、多模組支援、帳號系統、雲端部署、多 Agent。

### 1.3 Non-goals

Agent 不得自行擴張的功能範圍：新增資料來源類型、加入 modpack 配方查詢（SQLite 屬非 MVP 的 Phase 6）、引入新框架或外部服務、將 CLI 擴充為 API 服務。以上皆屬 §16 的框架級決策。

## 2. Rule Priority

發生衝突時依以下順序處理：

1. 使用者當前明確指令
2. 本 AGENTS.md
3. `skills/` 與 `.agents/skills/`
4. `README.md`
5. 既有程式碼風格與一般工程慣例

但使用者指令不得要求執行本文件明確禁止的敏感或危險操作，除非使用者針對該操作再次明確授權。

## 3. Core Invariants

以下規則不可因實作方便而放寬。

### 3.1 Data / Knowledge Integrity

- 唯一合法資料來源：AE2 官方 Minecraft 1.21.1 指南（`guide.appliedenergistics.org`）；不混用其他版本或非官方資料。
- 版本限制：知識庫僅限 1.21.1；版本資訊必須隨資料一路傳遞。
- Provenance 要求：每個 chunk 必須保留 `source_url`、頁名、章節標題與版本資訊；無來源 URL 的內容不得進入知識庫。
- 缺乏證據時不得猜測或補完。

### 3.2 Product Integrity

- RAG 回答只能依據實際檢索到的 chunks，不得使用檢索範圍外的 Minecraft／AE2／其他版本知識補字。
- 每個回答必須附可點擊的來源連結。
- 官方文件不足以確認時，必須回答「目前官方文件不足以確認」，不得猜測或自行補完官方文件沒有提供的資訊。

### 3.3 Reproducibility

- 可重複執行的 pipeline 階段必須保持冪等（整份覆寫重產生，重跑不改變語義）。
- 產物不得依賴不可追蹤的人工狀態。
- 不得因驗證失敗而降低驗證標準（見 §13）。

## 4. Evidence and Truthfulness

Agent 必須區分以下四類資訊來源：

### 4.1 Normative Rules（應該怎麼做）

`AGENTS.md`、`skills/`、`.agents/skills/`。

### 4.2 Current State（目前實際狀態）

實際程式碼、實際資料產物、Git 狀態，以及必要時重新執行的檢查。

### 4.3 Historical Snapshot（歷史／審查快照）

`REVIEW.md` 是一次性的完整專案遍歷審查快照，用於需要重新理解整個專案時快速掌握現況：

- 不是永久規範，也不是持續監控文件；一般任務不需要閱讀或更新它。
- 內容可能隨時間過期；與實際程式碼、資料產物或 Git 狀態不一致時，以重新檢查後的實際狀態為準，不得盲從 REVIEW.md。
- 僅在使用者明確要求重新梳理專案、專案狀態已長時間沒有整理、發生大量架構變動、無法可靠理解現有架構，或使用者要求重新建立／更新 REVIEW.md 時，才重新遍歷專案並建立／更新。

### 4.4 Progress & Decisions（進度與決策）

`recall.md`：當前進度、決策歷史與每次工作摘要。

### 4.5 Human Documentation

`README.md` 用於說明專案如何使用，不應被視為高於實際程式碼的現況證據。

### 4.6 Unknown Rule

若無法由實際檔案、程式碼、資料產物或明確文件確認：

- 標記為 Unknown，不得自行推測為事實。
- 若該資訊會影響架構、資料來源或不可逆操作，必須詢問使用者。

## 5. Repository Map

只描述穩定的目錄與模組職責。

| Path | Responsibility |
| --- | --- |
| `sources.json` | 知識來源入口 |
| `fetch_pages.py` | 文件擷取 |
| `chunk_pages.py` | 文件切分 |
| `embed_chunks.py` | Embedding 產生（chunks → 向量） |
| `index_chunks.py` | 向量索引 |
| `query.py` | 檢索與回答 |
| `app.py` | 使用者介面 |
| `data/` | pipeline 產物 |
| `README.md` | 人類使用說明 |
| `recall.md` | 專案狀態與決策 |
| `REVIEW.md` | 一次性稽核快照（完整遍歷結果） |

不在此記錄「目前有幾個檔案、幾個 chunk、Phase 幾完成」等易變資訊。

`fetch_pages.py`、`chunk_pages.py` 與 `embed_chunks.py` 為已實作模組（`embed_chunks.py` 僅完成程式與設定，尚未執行）；`index_chunks.py`、`query.py`、`app.py` 為預定 pipeline 模組——上表描述的是契約職責，實作狀態由 `recall.md` 管理，不得因本表列出即假設這些程式目前存在。

## 6. Pipeline Contract

管線為單向資料流，各階段可獨立重跑。

| Stage | Input | Output | Contract | Failure |
| --- | --- | --- | --- | --- |
| Fetch | `sources.json` | `data/raw/<host>/<slug>.html`；`data/processed/<host>/<slug>.md`（含 YAML metadata） | 僅接受 `guide.appliedenergistics.org` 網域；逐頁處理、單頁失敗不阻斷其他頁；結束時統計成功／失敗／略過 | URL 不在白名單 → 拒絕；整體結束碼：全成功 0、有失敗 1 |
| Chunk | `data/processed/*.md` | `data/chunks.jsonl` | frontmatter 六欄驗證 → 以 Markdown 標題優先分節 → 段落切分（目標 500–700 tokens、重疊 80–120 tokens） | 文件缺任一 metadata 欄位或缺 `source_url` → 整批中止、不產生部分輸出，exit 1 |
| Index | `data/chunks.jsonl` | 向量索引（PostgreSQL + pgvector） | Contract 與 Failure 於實作時定義並補入本表（實作狀態由 `recall.md` 管理） | 實作時補入本表 |
| Query | 使用者問題 + 向量索引 | 附來源回答 | Contract 與 Failure 於實作時定義並補入本表（實作狀態由 `recall.md` 管理） | 實作時補入本表 |

實作標示：Fetch 與 Chunk 為已實作階段；Index 與 Query（及 UI 層的 `app.py`）為預定階段，目前僅存在於契約層——不得為其虛構實作細節，實作狀態由 `recall.md` 管理。

Pipeline invariants（跨階段不可破壞）：

- 所有 chunk 必須保留 provenance（`source_url`、頁名、章節標題、版本）。
- 缺少必要 metadata 的文件不得進入下一階段。
- pipeline 不得產生部分有效但未被明確標記的正式產物（fetch 以統計與結束碼標記；chunk 為全有或全無）。
- 各階段可單獨重跑，正式產物為整份覆寫重產生（冪等）。

## 7. Data Contract

定義正式資料格式，而非描述目前資料數量。

### Metadata（processed Markdown frontmatter）

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| `title` | string | 頁面標題 |
| `source_url` | string | 官方頁面 URL，provenance 主鍵，不得為空 |
| `minecraft_version` | string | 固定 `"1.21.1"` |
| `mod` | string | 固定 `"Applied Energistics 2"` |
| `source_type` | string | `"official_guide"` |
| `fetched_at` | string | 抓取時間，ISO 8601 含時區 |

六欄皆為必填；缺任一欄的文件不得進入 chunks。

### Chunk Schema（chunks.jsonl，JSON Lines）

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| `chunk_id` | string | 階段執行時產生的識別碼 |
| `source_url` | string | 必填、非空，對應 frontmatter |
| `page_title` | string | 對應 frontmatter `title` |
| `section_title` | string | 來源頁內的章節標題 |
| `minecraft_version` / `mod` / `source_type` | string | 繼承 frontmatter 固定值 |
| `fetched_at` | string | 該階段產出時間，ISO 8601 含時區 |
| `estimated_tokens` | integer | token 估算值（字元近似） |
| `content` | string | chunk 正文 |

- **Provenance 要求**：`source_url` / `page_title` / `section_title` / `minecraft_version` 必須可追溯至 processed frontmatter；`content` 不得含無來源的補充文字。
- **ID 穩定性**：現行契約不保證 `chunk_id` 跨執行穩定；下遊若需穩定識別，屬設計決策，須詢問使用者（見 §15）。

### Versioning

- 版本來源：`sources.json` 每筆的 `minecraft_version`，寫入 frontmatter 並繼承至每個 chunk。
- 不同版本**不得混用**；知識庫僅限 1.21.1。
- Schema 變更屬 pipeline contract 變更：須經使用者授權（§16），且下游正式產物必須整批冪等重產生。

### Embedding Input

- Embedding 文字契約：chunk 的 `section_title` + `page_title` + `content`，以換行串接送入模型；`source_url`／`fetched_at`／`chunk_id` 不進入 embedding 文字（保留為 provenance／database 欄位）。
- 指定模型：`sentence-transformers/all-MiniLM-L6-v2`（本機執行），輸出向量正規化；distance metric 待決（正規化向量建議 cosine）。
- 輸出 `data/embeddings.jsonl` 必須保留原始 chunk metadata；`source_url` + `chunk_id` 為複合鍵（`chunk_id` 為頁內編號，非全域唯一）。

## 8. Technical Constraints

只放「不可擅自變更」的技術決策：

- Python 3.9（新增程式碼須相容）。
- 核心套件：requests + BeautifulSoup（擷取）；Markdown + YAML metadata（中間格式）。
- 向量資料庫：PostgreSQL + pgvector（後續 Vector Database；由使用者指定，尚未建立）。
- LLM provider：OpenAI（回答生成）。
- Embedding model：`sentence-transformers/all-MiniLM-L6-v2`（本機執行，來源 Hugging Face）。
- UI framework：Streamlit（最後階段）。
- 不使用 LangChain（本專案採原生 Python 管線，與 LangChain 無關）。
- API key 僅由 `.env` 提供。
- SQLite modpack 配方解析不屬於 MVP。

任何新的 dependency、framework、database、architecture 或 external service，若不在上述決策中，必須先詢問使用者。

## 9. Security and Sensitive Data

### Never

- 讀取或輸出秘密內容（API key、token、password、private key），亦不得要求使用者貼出。
- 將任何憑證寫入程式碼或文件。
- 提交含敏感資料的檔案。
- 修改或刪除 `.env`。
- 讀取、複製、輸出或提交 `gcm-diagnose.log` 的內容（含外洩 API key 的診斷檔）。

### Sensitive Operations（必須取得使用者當前明確授權）

- push、merge、history rewrite、branch deletion
- remote repository creation（新建遠端 repo 一律 private，僅在使用者明確要求時才可 public）
- 修改知識來源（`sources.json`）
- 寫入專案根目錄之外的路徑（含全域 `~/.codex/skills/`）

例外：檢查 `.gitignore` 內容、以 `git status` / `git ls-files` 確認敏感檔案的版控狀態，不屬於禁止項。

## 10. Agent Decision Boundary

### Can do without asking

- 專案內讀取、搜尋、`cd`。
- 修改當前任務範圍內的程式碼與文件（最小必要範圍，遵循 §12）。
- 重跑 fetch / chunk 階段產生資料產物。

### Must ask first

- 修改架構、管線契約、目錄結構，或 §8 任何技術決策。
- 新增或升級 dependency（含更新 `requirements.txt`）。
- 修改資料來源（`sources.json`）。
- 刪除或搬移既有檔案。
- §9 全部 Sensitive Operations。
- 讀取環境變數、系統診斷、硬體狀態等敏感系統資訊。

### Must never do

- §9 全部 Never 項目。
- 未經使用者明確指示執行 push 或 merge。
- 將檢索範圍外知識寫入 RAG 回答或知識庫。
- 未經使用者授權執行 §16 的框架級決策。

## 11. Task Start Protocol

一般任務（不需完整遍歷 repository）：

1. 閱讀 AGENTS.md。
2. 視任務需要閱讀 recall.md（涉及目前進度或既有決策時）；涉及使用者操作或介面時，參考 README.md。
3. 定位相關模組（§5 Repository Map）。
4. 判斷最小必要變更範圍與對應驗證方式（§13）。
5. 檢查是否觸及 decision boundary（§9／§10）。
6. 修改前說明預計操作的檔案與原因。
7. 執行修改。
8. 執行對應驗證。
9. 回報實際結果（§17）。

僅在以下情況才執行完整 repository review（並建立或更新 REVIEW.md）：

- 使用者明確要求重新梳理專案。
- 專案狀態已長時間沒有整理。
- 發生大量架構變動。
- 無法可靠理解現有架構。
- 使用者要求重新建立或更新 REVIEW.md。

## 12. Change Policy

### Minimal Change

- 只修改完成任務所需的檔案。
- 不進行無關重構，不順手清理 unrelated code。
- 不改變既有架構，除非使用者授權。

### Code Quality

- 保持單一職責、模組化。
- 重要函式提供型別標註。
- 錯誤訊息應清楚指出原因。
- 遵循既有程式碼風格與繁中註解慣例。

## 13. Validation and Anti-False-Success

Agent 不得宣稱未執行的驗證為成功。

### Rules

- 實際執行驗證；驗證以實際存在的工具執行（專案未設定 pytest、lint 或 CI 前，不得假設其存在）。
- 如實回報失敗。
- 不得降低 assertion、縮小驗證範圍以製造成功。
- 不得因測試失敗而直接修改測試標準。
- 修改 fetch / chunk / index / query 後，必須依下表對應規則驗證。

### Validation Matrix

| Change | Validation | Acceptance Criteria |
| --- | --- | --- |
| Fetch | `python fetch_pages.py` | 產物存在；每份 processed Markdown frontmatter 六欄完整；結束碼 0（單頁失敗時為 1，須如實回報） |
| Chunk | `python chunk_pages.py` | `chunks.jsonl` 每行可 JSON 解析且含 `source_url` 與 `section_title` |
| Index | 以固定測試問題執行查詢 | 查詢回傳結果且含來源 URL |
| Query | 以固定測試問題執行查詢 | 回答附可點擊來源 URL |
| Documentation | 人工核對 | 文內事實（路徑、檔名、規則引用）與實際狀態一致 |

框架層級決策（§16）：採 grill-me 模式逐項提問，待使用者決策後再實作。

## 14. Documentation Responsibilities

### AGENTS.md（本檔）

只保存：永久規範、不可變契約、Agent 行為邊界、穩定架構規則。
不要保存：當前頁數、chunk 數、Phase 進度、commit 狀態、臨時 bug、一次性 audit 結果。

### README.md

保存：專案介紹、安裝、使用方式、人類可讀架構說明、開發者操作方式。

### recall.md

保存：當前進度、決策歷史、已完成工作、下一步、未決問題、每次更新的 summary。
它不承載永久規範，與本檔衝突時以本檔為準。

### REVIEW.md

保存：某次完整專案遍歷的客觀結果（實際 repository 結構、實際存在的程式、實際 pipeline、data schema、dependency、程式碼缺陷、文件 discrepancy、risk、unknown、handoff summary）。
它是「重新理解專案」的一次性審查快照，不是永久規範，也不是持續監控文件——僅在完整遍歷時建立或更新，一般程式修改不觸發更新。

## 15. Handoff Protocol

當 AI 完成一個重要階段時，應確保：

- `recall.md` 反映最新狀態（每次更新完成後寫入更新總結）。
- 若有重大架構決策，更新相關文件（架構變更須同步 `README.md`）。
- 僅在進行完整專案遍歷時，才建立或更新 `REVIEW.md`；一般程式修改不得自動更新 REVIEW.md。
- 不將 transient state 寫入 AGENTS.md。
- 回報（§17）：修改了什麼、驗證了什麼、尚未驗證什麼、已知風險、下一步需要使用者決策的事項。

## 16. Architecture Change Protocol

以下屬於 framework-level decision，Agent 不得自行決定：

- 更換主要 framework
- 更換資料庫
- 更換 LLM provider
- 更換 embedding strategy
- 修改 pipeline 邊界
- 修改資料來源策略
- 引入新的 agent framework
- 大型目錄重構

應採用 **Grill-me mode**：

1. 說明目前問題。
2. 提供 2–3 個方案。
3. 說明每個方案的成本與風險。
4. 明確指出推薦方案。
5. 等待使用者決策，決策後才實作。

## 17. Completion Report

完成任務後，回報至少包含：

- **Changed**：實際修改的檔案。
- **Validation**：實際執行的驗證與結果。
- **Not Verified**：沒有執行的驗證。
- **Risks**：仍存在的問題。
- **Decisions Needed**：需要使用者決定的事項。

## 18. Final Principle

- Do not guess the codebase.
- Do not silently expand the scope.
- Do not turn temporary state into permanent policy.
- Do not claim validation that was not performed.
- When evidence is insufficient, say so.
