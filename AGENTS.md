# AGENTS.md — Project Engineering Contract

本文件是 AI Agent 在本專案中工作的永久工程契約：規定**行為邊界、不變式與驗收方式**。
架構地圖見 `ARCHITECTURE.md`；各模塊的 I/O、欄位、規則與決策理由以 `docs/` 的模塊文件為單一事實來源，本文件只引用、不重述。
本文件不記錄會隨時間變動的專案狀態（進度、頁數、實測數字）。

- 架構地圖（模塊、邊界、不變式）：`ARCHITECTURE.md`
- 各模塊的契約與決策理由：`docs/01_fetch.md`～`docs/06_index.md`
- 疑難排解：`docs/07_troubleshooting.md`
- 人類使用說明與開發狀態：`README.md`

## 1. Project Mission

### 1.1 Purpose

**Minecraft AE2 RAG Assistant**：依據 AE2 官方 Minecraft 1.21.1 指南回答知識問題的 RAG 助手。答案附可點擊的來源；官方文件不足以確認時，回答「目前官方文件不足以確認」。

本專案同時是**學習成熟 RAG 技術棧**的載體：選型與流程以認識業界常見做法為目標之一，不只以最短交付路徑為準。

### 1.2 Scope

- **包含（MVP）**：官方指南頁面的抓取、抽取、清理、切分、向量索引、附來源問答、展示介面。
- **不包含**：modpack JAR 解析、KubeJS／CraftTweaker 覆寫解析、多模組支援、帳號系統、雲端部署、多 Agent。
- **目前契約涵蓋範圍**：資料準備（抓取到入庫）。核心查詢（檢索與回答）與 UI 屬於 MVP，但其契約後續再納入；在此之前依 §8 的已定技術，不預先定義細節。

### 1.3 Non-goals

Agent 不得自行擴張以下範圍：新增資料來源類型、加入 modpack 配方查詢、引入新框架或外部服務、將 CLI 擴充為 API 服務。以上皆屬 §16 的框架級決策。

## 2. Rule Priority

發生衝突時依以下順序處理：

1. 使用者當前明確指令
2. 本 AGENTS.md
3. `ARCHITECTURE.md` 與 `docs/` 模塊文件
4. 全域 skill（harness 層級，不存於本 repo；專案文件未規定時才適用）
5. `README.md`
6. 既有程式碼風格與一般工程慣例

但使用者指令不得要求執行本文件明確禁止的敏感或危險操作，除非使用者針對該操作再次明確授權。

## 3. Core Invariants

以下規則不可因實作方便而放寬。

### 3.1 Data / Knowledge Integrity

- 唯一合法資料來源：AE2 官方 Minecraft 1.21.1 指南（`guide.appliedenergistics.org`）；不混用其他版本或非官方資料。
- 版本限制：知識庫僅限 1.21.1；版本資訊必須隨資料一路傳遞（目錄路徑 `<version>/<mod_slug>/<chapter>/` 與 chunk metadata）。
- Provenance：每個 chunk（含 parent 與 child）必須保留 `source_url`、`title`、`page`、`chapter`、`section` 與版本資訊；沒有來源 URL 的內容不得進入知識庫。
- 缺乏證據時不得猜測或補完。

### 3.2 Product Integrity

- RAG 回答只能依據實際檢索到的 chunks，不得用檢索範圍外的 Minecraft／AE2／其他版本知識補字。
- 每個回答必須附可點擊的來源連結。
- 官方文件不足以確認時，必須回答「目前官方文件不足以確認」。

### 3.3 Reproducibility

- 可重複執行的 pipeline 階段必須冪等（整份覆寫重產生，重跑不改變語義）。
- 所有中間產物為單次記錄、覆蓋更新，不做 history（`ARCHITECTURE.md` §6）。
- 產物不得依賴不可追蹤的人工狀態。
- 模型必須鎖定 revision 並記錄於輸出。
- 不得因驗證失敗而降低驗證標準（§13）。

## 4. Evidence and Truthfulness

Agent 必須區分以下資訊來源：

| 類別 | 來源 | 用途 |
| --- | --- | --- |
| Normative（應該怎麼做） | `AGENTS.md`；`ARCHITECTURE.md`；`docs/` 模塊文件的契約 | 規則與契約 |
| Current State（實際狀況） | 程式碼、資料產物、Git 狀態、重新執行的檢查 | 判斷是否已實作、是否正確 |
| Target State（目標狀態） | `ARCHITECTURE.md`、`docs/` 模塊文件 | 目標架構；不是進度。不得因某模塊列在其中就假設已實作 |
| 過程文件（非規範、非現況） | `reports/`、README 的專案狀態、根目錄的交接或筆記檔 | 只作為線索；引用前必須以實際檔案重新驗證 |

**Unknown Rule**：無法由實際檔案、程式碼、資料產物或規範文件確認的資訊：

- 標記為 Unknown，不得推測為事實。
- 若會影響架構、資料來源或不可逆操作，必須詢問使用者。

## 5. Repository Map

模塊地圖見 `ARCHITECTURE.md` §3。

| Path | 編號／模塊名稱 | Responsibility |
| --- | --- | --- |
| `sources.json` | [1] 來源設定 | 入口設定（版本、模組原名、入口 URL）；可被各階段共用讀取 |
| `src/fetch_pages.py` | [2] 抓取 | 抓取 raw HTML（只做網路 I/O）；文件 `docs/01_fetch.md`（含 [1]） |
| `src/extract_pages.py` | [3] 抽取 | 抽取主文與標題結構；文件 `docs/02_extract.md` |
| `src/clean_pages.py` | [4] 清理 | 清理與標題層級正規化；文件 `docs/03_clean.md` |
| `src/chunk_pages.py` | [5] 切分 | 子母分層切分（目標狀態）；文件 `docs/04_chunk.md` |
| `src/embed_chunks.py` | [6] 向量化 | Embedding（目標狀態）；文件 `docs/05_embed.md` |
| `src/index_chunks.py` | [7] 入庫 | 寫入 pgvector（擱置）；文件 `docs/06_index.md` |
| `data/` | — | pipeline 產物 |
| `reports/` | — | 各階段的單次報告 |
| `ARCHITECTURE.md` | — | 架構地圖 |
| `docs/01`～`06_*.md` | — | 各模塊的契約、方法、決策理由、驗證方式、待定事項 |
| `docs/07_troubleshooting.md` | — | 疑難排解（只追加） |
| `requirements.txt` | — | 依賴的唯一來源（鎖定精確版本） |
| `.env.example` | — | 環境變數範本（實際 `.env` 由本地提供，不入版控） |

pipeline 模組一律放在 `src/`，以 `PROJECT_ROOT = Path(__file__).resolve().parent.parent` 定位專案根；不得在根目錄新增腳本。表列「目標狀態」或「擱置」的模組，實作狀態以實際程式碼為準。檢索（`query.py`）與 UI（`app.py`）不在本契約範圍。

## 6. Pipeline Contract

管線為單向資料流，各階段可獨立重跑，正式產物整份覆寫。各階段的完整契約（步驟、欄位、規則、失敗處理）見 `docs/` 對應的模塊文件；模塊邊界原則見 `ARCHITECTURE.md` §4。

| Stage | Input | Output | 不可破壞的約束 |
| --- | --- | --- | --- |
| [1] 入口 | 人工維護 | `sources.json` | 入口頁只推導站台根，不抓取；版本取自 `version` 欄位 |
| [2] 抓取 | `sources.json` + sitemap.xml | `data/raw/<version>/<mod_slug>/<chapter>/*.html`、`_manifest.json` | URL 真值來源只有 sitemap.xml，無可用 sitemap → fail-fast，不 fallback（`docs/01_fetch.md`）；不解析導覽 DOM；路徑三元素只在 [2] 計算 |
| [3] 抽取 | raw HTML + `_manifest.json` | `extracted/**/*.json`、報告、人類可讀衍生物 | trafilatura 原始欄位不異動；`markdown` 只加標題記號（`docs/02_extract.md`）；navigation_only 頁與 `sources.json` 的 `exclude` 網址不輸出；跳轉頁候選只列清單，須人工確認並加入 `exclude` 才排除 |
| [4] 清理 | extracted JSON | `cleaned/**/*.md`、`cleaning_report.md` | 噪音規則、標題正規化、空章節移除依 `docs/03_clean.md`；規則只作用於正文；被排除的頁不輸出、以報告為憑 |
| [5] 切分 | cleaned MD | child chunks + parent 文件 | 只讀 cleaned MD；子母分層；以 BGE-M3 tokenizer 計數並斷言上限（`docs/04_chunk.md`）；`source_url` 為空的頁不產出 |
| [6] Embedding | child chunks | child + 向量 | BGE-M3、1024 維、正規化、revision 鎖定（`docs/05_embed.md`）；與輸入逐筆對應 |
| [7] 入庫 | [6] 向量 + [5] parent | PostgreSQL + pgvector | **擱置**：schema、入庫方式、索引不得預先定義 |

Pipeline invariants（跨階段不可破壞）：

- 所有 chunk 必須保留 provenance（§3.1）。
- 缺少必要 metadata 的文件不得進入下一階段。
- 所有中間產物為單次記錄覆蓋，不做 history；各階段可單獨重跑（冪等）。

## 7. Data Rules

欄位定義見各模塊文件的「輸入與輸出」。以下為不可放寬的資料規則：

- **`title` 不異動**：extracted JSON 的 `title` 經 cleaned MD frontmatter 原封帶入 chunk；下游直接用 chunk 的 `title`，不回查 JSON。
- **trafilatura 原始欄位不異動**：`title`／`text`／`source`／`hostname` 保留原值；`markdown` 去掉標題記號後必須逐行等於 `text`；`recipes` 只來自 HTML 配方區塊的文字屬性，不推測、不補值（無產物數量就不寫）。
- **權威來源分離**：結構性 metadata（`version`／`mod`／`chapter`／`page`）以目錄路徑為準；內容性 metadata（`title`／`source_url`）以 frontmatter 為準。
- **slug 只用於路徑與命名**（資料夾、檔名、ID、`mod`／`chapter`／`page` 欄位）；`text`、`title`、`section` 禁止 slug 化。
- **版本資訊**由目錄路徑承載並貫穿全鏈；不同版本不得混用。
- **Schema 變更**屬 pipeline contract 變更：須經使用者授權（§16），且下游正式產物必須整批冪等重產生。

## 8. Technical Constraints

以下為已定的技術決策，不可擅自變更：

| 範圍 | 決策 |
| --- | --- |
| 語言 | Python 3.12（新程式碼須相容） |
| torch | GPU build 由 cu130 index 安裝（sentence-transformers 的傳遞依賴，不列於 `requirements.txt`） |
| [2] 抓取 | requests + `xml.etree.ElementTree`（sitemap.xml）；`python-slugify`（只用於路徑與命名）；不用 BeautifulSoup 做導覽發現 |
| [3] 抽取 | trafilatura（`output_format="json"`、`with_metadata=True`、`include_tables=True`，直接吃 HTML 字串）；BeautifulSoup 只用於 `<article>` 的連結密度與標題結構 |
| [4] 清理 | 自寫規則，只用標準庫 |
| [5] 切分 | langchain-text-splitters（`MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`）；子母分層；BGE-M3 tokenizer |
| [6] Embedding | `BAAI/bge-m3`，sentence-transformers 本機執行，dense、1024 維、正規化、revision 鎖定；sparse／ColBERT 不採用 |
| [7] 向量庫 | PostgreSQL + pgvector |
| LLM | OpenAI（回答生成） |
| 查詢語言 | 英文檢索 + 繁中回答（BGE-M3 支援多語言，待重新評估） |
| UI | Streamlit（最後階段） |
| 金鑰 | 只由 `.env` 提供（範本見 `.env.example`） |

- LangChain 只允許使用 splitter 套件（langchain-text-splitters）；不引入 LangChain 的 agent／chain 編排層。
- SQLite modpack 配方解析不屬於 MVP。
- 任何不在上表的 dependency、framework、database、architecture 或 external service，必須先詢問使用者。

## 9. Security and Sensitive Data

### Never

- 讀取或輸出秘密內容（API key、token、password、private key），也不得要求使用者貼出。
- 將任何憑證寫入程式碼或文件。
- 提交含敏感資料的檔案。
- 修改或刪除 `.env`。
- 讀取、複製、輸出或提交 `gcm-diagnose.log` 的內容（含外洩 API key 的診斷檔）。

### Sensitive Operations（必須取得使用者當前明確授權）

- push、merge、history rewrite、branch deletion
- remote repository creation（一律 private，只有使用者明確要求才可 public）
- 修改知識來源（`sources.json`）
- 寫入專案根目錄之外的路徑（含全域 `~/.codex/skills/`）。例外：Agent 工具本身的暫存與記憶目錄、套件與模型的快取目錄（例如 `~/.cache/huggingface`）；下載仍依 §10 先詢問。
- 刪除既有資料產物或既有檔案。例外：[4] 依 `docs/03_clean.md` 重建 `cleaned/<version>/`（範圍限定該版本子樹、有路徑斷言、處理完成後才清空）。其他階段如需比照，須另行授權。

例外：檢查 `.gitignore` 內容，以及用 `git status`／`git ls-files` 確認敏感檔案的版控狀態，不屬於禁止項。

## 10. Agent Decision Boundary

### Can do without asking

- 專案內讀取、搜尋、`cd`。
- 修改當前任務範圍內的程式碼與文件（最小必要範圍，遵循 §12）。
- 重跑 [2]–[5] 階段產生資料產物（[2] 會連網抓取官方指南頁面）。
- 重跑 [6]，但僅限模型已在本機快取時；首次需下載模型時依下方「下載模型」先詢問。

### Must ask first

- 修改架構、管線契約、目錄結構，或 §8 任何技術決策。
- 新增或升級 dependency（`requirements.txt`）。
- 下載模型或其他大型檔案（說明來源與大小）。
- 修改資料來源（`sources.json`）。
- 刪除或搬移既有檔案。
- 修改 [4] 清理規則（見 `docs/03_clean.md`）：門檻、白名單的小幅調整須使用者同意並記錄裁定；新增或刪除規則、改變處理順序屬 §16 框架級決策。
- 定義模塊文件標示為「待定」或「擱置」的項目（如 [5] overlap 與 ID、[7] schema）。
- §9 全部 Sensitive Operations。
- 讀取環境變數、系統診斷、硬體狀態等敏感系統資訊。

### Must never do

- §9 全部 Never 項目。
- 未經使用者明確指示執行 push 或 merge。
- 將檢索範圍外的知識寫入 RAG 回答或知識庫。
- 未經授權執行 §16 的框架級決策。
- 為「待定」或「擱置」項目虛構細節。

## 11. Task Start Protocol

1. 閱讀 AGENTS.md。
2. 視任務需要閱讀 `ARCHITECTURE.md`（涉及模塊邊界時）、`docs/` 模塊文件（涉及契約或決策理由時）、`README.md`（涉及使用者操作時）。
3. 定位相關模組（§5）。
4. 判斷最小必要變更範圍與對應驗證方式（§13）。
5. 檢查是否觸及 decision boundary（§9／§10）。
6. 修改前說明預計操作的檔案與原因。
7. 執行修改。
8. 執行對應驗證。
9. 回報實際結果（§17）。

## 12. Change Policy

### Minimal Change

- 只修改完成任務所需的檔案。
- 不做無關重構，不順手清理 unrelated code。
- 不改變既有架構，除非使用者授權。

### Code Quality

- 保持單一職責、模組化。
- 重要函式提供型別標註。
- 錯誤訊息應清楚指出原因。
- 遵循既有程式碼風格與繁中註解慣例。

## 13. Validation and Anti-False-Success

Agent 不得宣稱未執行的驗證為成功。

### Rules

- 實際執行驗證；只使用實際存在的工具（專案未設定 pytest、lint 或 CI 前，不得假設其存在）。
- 如實回報失敗。
- 不得降低 assertion、縮小驗證範圍以製造成功。
- 不得因測試失敗而直接修改測試標準。
- 修改 [2]–[6] 後，必須依下表驗證。

### Validation Matrix

| Change | Validation | Acceptance Criteria |
| --- | --- | --- |
| [2] Fetch | `python src/fetch_pages.py` | `_manifest.json` 存在且每頁記錄 `http_status`；結束碼 0（有失敗記錄時為 1，須如實回報） |
| [3] Extract | `python src/extract_pages.py` | 每份 `extracted/*.json` 可解析，含 `title`／`source`／非空 `text`／`markdown`；`markdown` 去掉標題記號後逐行等於 `text`；`extraction_report.md` 產出，標出 `source`（與 `title`）為空的頁、未對應的標題，並列出尚未確認的跳轉頁候選清單（只列不排除，待人工複核）；`exclude` 中的網址皆被跳過；`extracted_readable/*.md` 數 = `parsed_count`，`_index.md` 產出；報告列出配方總數與各類型數量，無法解析的配方須人工確認 |
| [4] Clean | `python src/clean_pages.py` | `cleaned/*.md` 產出、非空，含 frontmatter（至少 `title`、`source_url`），frontmatter 與 `# <title>` 之間有空行；每頁恰好一個 `#`，沒有白名單標籤的標題行，沒有空章節（標題底下必有內容）；被契約排除的頁不產出檔案，以 `cleaning_report.md` 為憑；**對帳：輸出頁數 + 報告列出的跳過頁數 = 輸入頁數**；`## Recipes` 之前的每一行去掉標題記號後，是某個輸入行或其子字串（純刪除檢查；`## Recipes` 由 R8 產生，行數須等於 `recipes` 筆數）；連跑兩次輸出相同 |
| [5] Chunk | `python src/chunk_pages.py` | 至少：每筆可解析且 provenance 欄位非空；每個 child 都能對應到 parent；parent ≤ 2048、child ≤ 256 tokens（BGE-M3 tokenizer，只算正文）斷言通過。欄位清單待 `docs/04_chunk.md` 定案後補入 |
| [6] Embed | `python src/embed_chunks.py` | 每筆 1024 維、norm = 1、`model_revision` 非空；與輸入 child 逐筆對應（順序與 ID 一致、metadata 不變） |
| [7] Index | 待 schema 定義後補入 | 待定 |
| Documentation | 人工核對 | 文內事實（路徑、檔名、規則引用）與實際狀況一致；每個格式只在產出它的模塊文件定義一次；`ARCHITECTURE.md` 的模塊地圖與模塊文件一致 |

框架層級決策（§16）：採 grill-me 模式逐項提問，待使用者決策後再實作。

## 14. Documentation Responsibilities

| 文件 | 只放 | 不放 |
| --- | --- | --- |
| `README.md` | 入口：專案介紹、架構簡圖、安裝與執行、文件導覽；開發期間暫時保留專案狀態（專案完成後移除） | 欄位級契約、決策理由 |
| `ARCHITECTURE.md` | 架構地圖：概覽、架構簡圖、模塊地圖、邊界原則、不變式（含刻意不做的事）、跨模塊共通事項 | 各模塊的實作細節、實測數字、進度、Agent 行為禁令 |
| `docs/01`～`06_*.md` | 每個模塊一份：輸入與輸出（格式只在此定義）、處理方法、為什麼這樣做（含實測證據與人工裁定）、否決的方案、驗證方式、待定事項 | 其他模塊的格式（只引用）、進度 |
| `docs/07_troubleshooting.md` | 坑紀錄（現象、根因、處置、證據）與症狀速查；只追加不改寫 | 過程敘事 |
| `AGENTS.md` | Agent 行為規則、權限邊界、不變式、驗收標準 | 欄位與參數細節（引用模塊文件）、進度、實測數字 |
| `reports/` | 程式產生的單次報告（不入版控） | 規範（不得被當作規則引用） |

- 不另立決策日誌：決策與否決的方案寫在受影響模塊文件的「為什麼這樣做」與「否決的方案」；跨模塊的決策寫在負責執行的模塊，其他模塊只放一行連結。
- 參數調整、既有規則的小增補：更新對應的模塊文件即可。
- 契約變更時，同步更新對應的模塊文件；模塊、資料流或不變式改變時，同步更新 `ARCHITECTURE.md`；`AGENTS.md` 只在行為規則或不變式變動時更新。

## 15. Handoff Protocol

完成一個重要階段時：

- 若有重大架構決策，同步更新對應的模塊文件、必要時更新 `ARCHITECTURE.md`，以及 `README.md` 的專案狀態。
- 依 §17 回報：修改了什麼、驗證了什麼、尚未驗證什麼、已知風險、需要使用者決策的事項。

## 16. Architecture Change Protocol

以下屬於 framework-level decision，Agent 不得自行決定：

- 更換主要 framework
- 更換資料庫
- 更換 LLM provider
- 更換 embedding strategy 或 embedding 模型
- 修改 pipeline 邊界或階段職責
- 修改資料來源策略
- 引入新的 agent framework
- 大型目錄重構
- 新增或刪除 [4] 清理規則、改變處理順序（須經人工裁定，並更新 `docs/03_clean.md` 的規則與裁定紀錄）
- 定義 [7] schema（`docs/06_index.md` 明示擱置）

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
- 當文件明示某項「待定／擱置」時，不得為其虛構細節。
