# AGENTS.md — Project Engineering Contract

本文件是 AI Agent 在本專案中工作的永久工程契約。
本文件描述「應遵守的規則」，不描述會隨時間變動的專案狀態。

- 目標架構（[1]–[7] 的完整定義）：`ARCHITECTURE.md`
- 人類使用說明：`README.md`

## 1. Project Mission

### 1.1 Purpose

**Minecraft AE2 RAG Assistant**：依據 AE2 官方 Minecraft 1.21.1 指南回答知識問題的 RAG 助手。答案附可點擊來源；官方文件不足以確認時，回答「目前官方文件不足以確認」。

本專案同時是**學習成熟 RAG 技術棧**的載體：選型與流程以認識業界常見做法為其中一個目標，不只以最短交付路徑為準。

### 1.2 Scope

- **包含（MVP）**：官方指南頁面之抓取、抽取、清理、切分、向量索引、附來源問答、展示介面。
- **不包含**：modpack JAR 解析、KubeJS／CraftTweaker 覆寫解析、多模組支援、帳號系統、雲端部署、多 Agent。

### 1.3 Non-goals

Agent 不得自行擴張的功能範圍：新增資料來源類型、加入 modpack 配方查詢、引入新框架或外部服務、將 CLI 擴充為 API 服務。以上皆屬 §16 的框架級決策。

## 2. Rule Priority

發生衝突時依以下順序處理：

1. 使用者當前明確指令
2. 本 AGENTS.md
3. 全域 skill（harness 層級，不存於本 repo）
4. `README.md`／`ARCHITECTURE.md`
5. 既有程式碼風格與一般工程慣例

但使用者指令不得要求執行本文件明確禁止的敏感或危險操作，除非使用者針對該操作再次明確授權。

## 3. Core Invariants

以下規則不可因實作方便而放寬。

### 3.1 Data / Knowledge Integrity

- 唯一合法資料來源：AE2 官方 Minecraft 1.21.1 指南（`guide.appliedenergistics.org`）；不混用其他版本或非官方資料。
- 版本限制：知識庫僅限 1.21.1；版本資訊必須隨資料一路傳遞（目錄路徑 `<version>/<mod_slug>/<chapter>/` 與 chunk metadata）。
- Provenance 要求：每個 chunk 必須保留 `source_url`、`title`、`page`、`chapter`、`section` 與版本資訊；無來源 URL 的內容不得進入知識庫。
- 缺乏證據時不得猜測或補完。

### 3.2 Product Integrity

- RAG 回答只能依據實際檢索到的 chunks，不得使用檢索範圍外的 Minecraft／AE2／其他版本知識補字。
- 每個回答必須附可點擊的來源連結。
- 官方文件不足以確認時，必須回答「目前官方文件不足以確認」，不得猜測或自行補完官方文件沒有提供的資訊。

### 3.3 Reproducibility

- 可重複執行的 pipeline 階段必須保持冪等（整份覆寫重產生，重跑不改變語義）。
- 所有中間產物為單次記錄，覆蓋更新，不做 history（見 `ARCHITECTURE.md` §5）。
- 產物不得依賴不可追蹤的人工狀態。
- 不得因驗證失敗而降低驗證標準（見 §13）。

## 4. Evidence and Truthfulness

Agent 必須區分以下四類資訊來源：

### 4.1 Normative Rules（應該怎麼做）

`AGENTS.md`。Skill 規範由全域 harness 提供，不存於本 repo。

### 4.2 Current State（目前實際狀況）

實際程式碼、實際資料產物、Git 狀態，以及必要時重新執行的檢查。

### 4.3 Target State（目標狀態）

`ARCHITECTURE.md` 描述 [1]–[7] 的**目標架構**。它不是進度文件，也不是現況描述——實作狀態以實際程式碼與資料產物為準，不得因 `ARCHITECTURE.md` 列出某階段即假設該階段已實作。

### 4.4 Unknown Rule

若無法由實際檔案、程式碼、資料產物或明確文件確認：

- 標記為 Unknown，不得自行推測為事實。
- 若該資訊會影響架構、資料來源或不可逆操作，必須詢問使用者。

## 5. Repository Map

只描述穩定的目錄與模組職責。完整目錄樹見 `ARCHITECTURE.md` §3。

| Path | Responsibility |
| --- | --- |
| `sources.json` | [1] 知識來源入口：`version` + `mod`（原名）+ `entry_url` + `exclude`／`include`；**整條 URL 鏈的起點**（`version` 由本檔欄位給定，`entry_url` 推導站台根；逐頁 URL 由 [2] 解析 **sitemap.xml** 產生，見 `docs/adr/ADR-001`） |
| `docs/adr/` | Architecture Decision Records（[2] URL 真值來源等架構決策） |
| `src/fetch_pages.py` | [2] 抓取 raw HTML（只做網路 I/O） |
| `src/extract_pages.py` | [3] 抽取主文（trafilatura） |
| `src/clean_pages.py` | [4] 清理與結構化（噪音規則待定） |
| `src/chunk_pages.py` | [5] 切分（真 tokenizer） |
| `src/embed_chunks.py` | [6] Embedding（MiniLM） |
| `src/index_chunks.py` | [7] 寫入 pgvector（擱置） |
| `data/` | pipeline 產物 |
| `reports/` | [3]／[4] 驗證報告 |
| `pyproject.toml` / `requirements.txt` | 專案 metadata 與依賴 |
| `.env.example` | 環境變數範本（實際 `.env` 由本地提供，不入版控） |
| `README.md` | 人類使用說明 |
| `ARCHITECTURE.md` | 目標架構（[1]–[7]） |

pipeline 模組一律置於 `src/`；模組內以 `PROJECT_ROOT = Path(__file__).resolve().parent.parent` 定位專案根，讀寫 `sources.json`、`data/` 與 `reports/`。新增 pipeline 模組時須遵守此配置，不得在根目錄新增腳本。

`ARCHITECTURE.md` §3 列出的模組為**目標狀態**；`src/index_chunks.py` 為擱置階段，`src/query.py`／`src/app.py`（檢索與 UI）不在本檔案目前的契約範圍——實作狀態以實際程式碼為準，不得因表列即假設其存在。

## 6. Pipeline Contract

管線為單向資料流，各階段可獨立重跑，輸出為單次記錄覆蓋（冪等）。各階段完整定義見 `ARCHITECTURE.md` §4。

| Stage | Input | Output | Contract | Failure |
| --- | --- | --- | --- | --- |
| [1] 入口 | 人工維護 | `sources.json` | `version` + `mod`（模組原名）+ `entry_url` + `exclude`／`include`；入口頁僅推導站台根（版本取自 `version` 欄位，不由入口頁推導），不抓取 | 格式不符 → 拒絕 |
| [2] 抓取 | `sources.json`（站台根與版本）+ `sitemap.xml` | `data/raw/<version>/<mod_slug>/<chapter>/*.html`；`data/raw/_manifest.json` | 只做網路 I/O，不做 HTML→MD、**不解析導覽 DOM**；**URL 真值來源為 sitemap.xml**（`robots.txt` 的 `Sitemap:` 宣告為主，慣例路徑為輔；HTTP 200 且根節點為 `<urlset>`／`<sitemapindex>`；無可用 sitemap → fail-fast，不 fallback；見 `docs/adr/ADR-001`）；版本過濾 `path.startswith(f"/{version}/")`（帶尾斜槓）並排除入口頁；逐頁抓取間隔 0.5 秒；`mod` 經 `python-slugify` 轉 `mod_slug`，`chapter`／`page_slug` 由 URL 解析（chapter 為去版本前綴之倒數第二段，無 chapter 頁歸 `other`）；記錄 `http_status` 與 `local_path` | 不重試；`http_status` 非 2xx 或 `local_path: null` → 記錄於 manifest，人工查驗後重跑；無可用 sitemap → 中止、exit 1 |
| [3] 抽取 | `data/raw/<version>/<mod_slug>/<chapter>/*.html` + `_manifest.json` | `data/processed/extracted/<version>/<mod_slug>/<chapter>/*.json`；`data/processed/extracted/_parse_report.json`；`reports/extraction_report.md`；**另產出 `data/processed/extracted_readable/**/*.md` 與 `_index.md`（人類驗收用，真值以 JSON 為準，寫入失敗僅記 warning）** | trafilatura 抽取主文；逐頁 `http_status` + `text` 空值判斷；**navigation_only 頁跳過不輸出**（規則一 `url_ends_with_index`：URL path 以 `-index` 結尾；規則二 `short_text_high_link_density`：文字長度 < 200 且**僅 `<article>` 範圍**連結密度 > 0.5；兩規則 reason 字串相異；預期 3 頁 `*-index` 命中）；**`title` 保留不異動**（[4] 帶入 cleaned MD H1）；**`hostname` 保留 trafilatura 原值不修正**；**不加 `page_slug`／`chapter` 欄位**（[5] 從路徑讀）；整份覆寫 | 缺 `http_status` 或 `text` 為空 → 報告標記，不中斷其他頁；.md 衍生物寫入失敗 → 僅記 warning，不影響 exit code |
| [4] 清理 | `data/processed/extracted/<version>/<mod_slug>/<chapter>/*.json` | `data/processed/cleaned/<version>/<mod_slug>/<chapter>/*.md`；`reports/cleaning_report.md` | 過濾 trafilatura 誤留噪音，輸出**含 frontmatter** 之乾淨 MD（frontmatter 至少含 `title`、`source_url`，其後為 `# <title>` + 正文；其餘 metadata 的權威來源為路徑）；**噪音規則待第一波資料後確認**（本階段不預先定義） | 規則未定義前以最小過濾跑通為主 |
| [5] 切分 | `data/processed/cleaned/<version>/<mod_slug>/<chapter>/*.md` | `data/processed/chunks/chunks.jsonl` | **只讀 cleaned MD**（不讀 extracted／manifest）；`mod_slug`／`chapter`／`page_slug`／`version` 從路徑四層讀，`title`／`source_url` 從 frontmatter 讀（H1 供 MarkdownHeaderTextSplitter 當結構，非 title 來源）；MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter；`chunk_size` 200、`chunk_overlap` 40–50；**MiniLM 真 tokenizer**；**切分後斷言每 chunk ≤ 254 wordpieces**；若 frontmatter 的 `source_url` 為空，中止該頁處理並報錯（不產出該頁 chunk，符合 §3.1「無來源 URL 的內容不得進入知識庫」） | 超出 254 wordpieces → 中止、exit 1 |
| [6] Embedding | `data/processed/chunks/chunks.jsonl` | `data/processed/embeddings/embeddings.jsonl` | embedding 輸入 `{mod} \| {page} \| {section}\n\n{text}`；MiniLM 正規化 encode；**revision 鎖定**並記錄於輸出；整份覆寫 | 輸入缺欄位 → 中止、exit 1 |
| [7] 入庫 | `data/processed/embeddings/embeddings.jsonl` | PostgreSQL + pgvector | **擱置**：schema、入庫方式、索引類型皆待 [1]–[6] 跑通後定義 | 待定 |

Pipeline invariants（跨階段不可破壞）：

- 所有 chunk 必須保留 provenance（`source_url`、`title`、`page`、`chapter`、`section`、版本）。
- **`title` 資料不異動**：extracted JSON 的 `title` 經 cleaned MD frontmatter 原封帶入 chunk metadata，下游（生成答案）直接用 chunk 的 `title`，不回查 JSON。
- 缺少必要 metadata 的文件不得進入下一階段。
- 所有中間產物為單次記錄覆蓋，不做 history。
- 各階段可單獨重跑，正式產物為整份覆寫重產生（冪等）。

## 7. Data Contract

定義正式資料格式。欄位語意詳見 `ARCHITECTURE.md` §4。

### sources.json（[1]）

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| `version` | string | Minecraft 版本，固定 `"1.21.1"`；決定目錄分層 `<version>/<mod_slug>/<chapter>/` |
| `mod` | string | 模組**原名**（`"Applied Energistics 2"`），**不 slug 化**；[2] 以 `python-slugify` 轉為 `mod_slug` 寫入路徑 |
| `entry_url` | string | 入口頁 URL，**僅作導航來源，不作為抓取目標** |
| `exclude` | array | 排除的 URL；**[2] 目前未讀取**（sitemap 時代改由版本過濾決定範圍，保留欄位待日後需要） |
| `include` | array | 額外納入的 URL；**[2] 目前未讀取**（同上） |

**廢棄舊形式**：本檔不再是逐頁人工清單；抓取範圍由 **sitemap.xml** 決定（`version` 由本檔欄位給定，`entry_url` 僅推導站台根，見 `docs/adr/ADR-001`）。`exclude`／`include` 欄位保留於 schema，但 [2] 目前**未讀取**（見 §7 欄位表）。

### Extracted JSON（[3]，trafilatura 輸出）

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| `title` | string | 頁面標題（trafilatura 抽取，**保留不異動**；由 [4] 帶入 cleaned MD 的 H1） |
| `text` | string | 抽取主文 |
| `source` | string | 來源 URL |
| `hostname` | string | 主機名 |
| `http_status` | integer | 由 `_manifest.json` 帶入 |

**不加 `page_slug`／`chapter` 欄位**：[5] 直接從**目錄路徑**讀取這些 metadata，extracted JSON 只保留 trafilatura 原始輸出與 `http_status`。

### Chunk Schema（[5]，`chunks.jsonl`，JSON Lines）

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| `chunk_id` | string | `{mod_slug}_{page_slug}_{seq}_{version}`，如 `applied-energistics-2_energy_0001_v1`；`seq` 以 page 為單位從 `0001` 遞增；結尾 `v1` 為**內容修訂號**，chunk 更新時迭代 `v2`、`v3` |
| `text` | string | chunk 原文 |
| `title` | string | 頁面標題原文（如 `Energy`），從 cleaned MD 的 frontmatter 讀；源頭為 extracted JSON 的 `title`，**不異動** |
| `mod` | string | 模組（**從路徑讀，slug 形式**，如 `applied-energistics-2`） |
| `chapter` | string | 章節（**從路徑讀，slug 形式**，如 `ae2-mechanics`；無 chapter 的頁為 `other`） |
| `page` | string | 頁面（**從檔名讀，slug 形式**，如 `energy`）；與 `title` 為獨立欄位，不可互相替代 |
| `section` | string | 頁面內子標題（MarkdownHeaderTextSplitter 提供） |
| `source_url` | string | 必填、非空；來自 cleaned MD 的 frontmatter（值為 trafilatura 的 `source`） |
| `token_count` | integer | 由**真 tokenizer** 計數，非字元近似 |

- **欄位來源（`mod`／`chapter`／`page` 明確定義，非待定項）**：
  - `mod` ← 目錄路徑第二層（`mod_slug`）；源頭為 `sources.json` 的 `mod` 原名，經 [2] `python-slugify` 轉換後寫入路徑。
  - `chapter` ← 目錄路徑第三層；由 [2] 從 URL 去版本前綴後取倒數第二段（URL 本已是 slug，不另行 slug 化）；無 chapter 的頁使用 `other`。
  - `page` ← 檔名 stem（`page_slug`），**不是** extracted JSON 的 `title`。
  - `title` ← cleaned MD 的 frontmatter（[4] 從 extracted JSON 原封帶入）；H1 供 MarkdownHeaderTextSplitter 當結構，非 title 來源。
  - `section` ← MarkdownHeaderTextSplitter 的頁內標題。
- **權威來源分離**：結構性 metadata（`version`／`mod`／`chapter`／`page`）權威來源為**目錄路徑**，frontmatter 對應欄位 [5] 不讀（僅供人類閱讀）；內容性 metadata（`title`／`source_url`）由 **frontmatter 承載**（路徑推不出）。frontmatter 與 H1 的 `title` 由 [4] 保證一致；若不一致，以 frontmatter 為準。
- **frontmatter 欄位範圍**：frontmatter 至少含 `title`、`source_url`（可含其他欄位供人類閱讀）；`fetched_at` 只留 `_manifest.json`，不進 frontmatter。
- **`source_url` 傳遞**：值為 extracted JSON 的 `source`（trafilatura 從 HTML 抽出），由 [4] 寫入 cleaned MD frontmatter，[5] 讀 frontmatter；鏈路起點為 `sources.json`（`version` 欄位 + `entry_url` 推導站台根 → [2] 解析 sitemap.xml 產生逐頁 URL → [3] trafilatura 抽取）。`_manifest.json` 的 `url` 是「實際抓取的 URL」，`source_url` 取值以 trafilatura 的 `source` 為準。
- **slug 只用於路徑與命名**：資料夾名稱、檔名、`chunk_id` 與 `mod`／`chapter`／`page` 欄位使用 slug；`text`、`title`、`section` 等內容欄位**禁止 slug 化**。
- **版本資訊**由目錄路徑 `<version>/<mod_slug>/<chapter>/` 承載，不另存 chunk 欄位。
- **已知風險（延後處理）**：`chunk_id` 不含 `chapter`，跨 chapter 同名 page 會碰撞；碰撞發生時在方案 A（`seq` 全域遞增）與方案 B（`chapter` 入 ID）間擇一。

### Embedding Schema（[6]，`embeddings.jsonl`，JSON Lines）

每行為一筆 chunk 的完整記錄 + 向量：

| 欄位 | 型別 | 語意 |
| --- | --- | --- |
| 原 chunk 九欄 | 同 Chunk Schema | 完整複製（含 `title`），metadata 不得被破壞 |
| `embedding` | array[float] | 384 維正規化向量（norm = 1） |
| `model_name` | string | 產生向量的模型名稱 |
| `model_revision` | string | **鎖定的 revision**（解決舊版未鎖定的不可重現性） |

- **對齊要求**：每行必須與輸入 `chunks.jsonl` 逐筆對應（順序一致、`chunk_id` 一致、九欄 metadata 零 drift）。

### Versioning

- 版本來源：`sources.json` 的 `version`，寫入目錄路徑並貫穿全鏈。
- 不同版本**不得混用**；知識庫僅限 1.21.1。
- Schema 變更屬 pipeline contract 變更：須經使用者授權（§16），且下游正式產物必須整批冪等重產生。

## 8. Technical Constraints

只放「不可擅自變更」的技術決策：

- Python 3.12（新增程式碼須相容）。
- torch：GPU build 由 cu130 index 安裝（`sentence-transformers` 的傳遞依賴，不另列於 `requirements.txt`；Windows 上 PyPI 預設為 CPU-only build）。
- [2] 抓取：requests + `xml.etree.ElementTree`（**sitemap.xml 為 URL 真值來源**，無新依賴）；`python-slugify`（`mod` 原名 → `mod_slug`，**只用於路徑與命名**，不用於內容）。**不使用 BeautifulSoup 做導覽發現**（見 `docs/adr/ADR-001`）。
- [3] 抽取：trafilatura（`output_format="json"`, `with_metadata=True`, `include_tables=True`，**自行解析 raw HTML**，直接吃字串、不經 BeautifulSoup 預處理）；BeautifulSoup 只在 navigation_only 判定中用於**計算 `<article>` 範圍的連結密度**，不用於導覽發現，也不是 trafilatura 的前置解析器。
- [5] 切分：`MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`（langchain-text-splitters）；tokenizer 為 MiniLM 真 tokenizer；`chunk_size` 200、`chunk_overlap` 40–50；**每 chunk ≤ 254 wordpieces 斷言**。
- Embedding model：`sentence-transformers/all-MiniLM-L6-v2`（**本機執行**，384 維、正規化、`max_seq_length` 256 wordpieces）；**revision 鎖定**。
- 向量資料庫：PostgreSQL + pgvector（[7]，schema 待 [1]–[6] 跑通後定義）。
- LLM provider：OpenAI（回答生成）。
- 查詢語言策略：**英文檢索 + 繁中回答**（檢索以英文進行，LLM 生成時以繁中作答）。
- UI framework：Streamlit（最後階段）。
- API key 僅由 `.env` 提供（範本見 `.env.example`）。
- SQLite modpack 配方解析不屬於 MVP。

任何新的 dependency、framework、database、architecture 或 external service，若不在上述決策中，必須先詢問使用者。

> **LangChain 限制解除**（2026-09-25 使用者確認）：舊版「不使用 LangChain」之禁令已移除。新架構 [5] 明確採用 langchain-text-splitters；禁止範圍不涵蓋 splitter 套件。其餘「原生 Python 管線」之精神不變——不引入 LangChain 的 agent／chain 編排層。

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
- 刪除既有資料產物或既有檔案

例外：檢查 `.gitignore` 內容、以 `git status` / `git ls-files` 確認敏感檔案的版控狀態，不屬於禁止項。

## 10. Agent Decision Boundary

### Can do without asking

- 專案內讀取、搜尋、`cd`。
- 修改當前任務範圍內的程式碼與文件（最小必要範圍，遵循 §12）。
- 重跑 [2]–[6] 階段產生資料產物。

### Must ask first

- 修改架構、管線契約、目錄結構，或 §8 任何技術決策。
- 新增或升級 dependency（含更新 `requirements.txt`／`pyproject.toml`）。
- 修改資料來源（`sources.json`）。
- 刪除或搬移既有檔案。
- 定義 [4] 噪音規則（`ARCHITECTURE.md` 明示「不預先定義」，須待第一波資料後歸納）。
- 定義 [7] schema／入庫方式／索引類型（`ARCHITECTURE.md` 明示擱置）。
- §9 全部 Sensitive Operations。
- 讀取環境變數、系統診斷、硬體狀態等敏感系統資訊。

### Must never do

- §9 全部 Never 項目。
- 未經使用者明確指示執行 push 或 merge。
- 將檢索範圍外知識寫入 RAG 回答或知識庫。
- 未經使用者授權執行 §16 的框架級決策。
- 為 [4] 噪音規則或 [7] schema 預先虛構細節。

## 11. Task Start Protocol

一般任務（不需完整遍歷 repository）：

1. 閱讀 AGENTS.md。
2. 視任務需要閱讀 `ARCHITECTURE.md`（涉及目標架構時）與 `README.md`（涉及使用者操作或介面時）。
3. 定位相關模組（§5 Repository Map）。
4. 判斷最小必要變更範圍與對應驗證方式（§13）。
5. 檢查是否觸及 decision boundary（§9／§10）。
6. 修改前說明預計操作的檔案與原因。
7. 執行修改。
8. 執行對應驗證。
9. 回報實際結果（§17）。

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
- 修改 [2]–[6] 後，必須依下表對應規則驗證。

### Validation Matrix

| Change | Validation | Acceptance Criteria |
| --- | --- | --- |
| [2] Fetch | `python src/fetch_pages.py` | `_manifest.json` 存在且每頁記錄 `http_status`；結束碼 0（有失敗記錄時為 1，須如實回報） |
| [3] Extract | `python src/extract_pages.py` | `extracted/*.json` 每檔可 JSON 解析且含 `title`／`source`／非空 `text`；`extraction_report.md` 產出且標出 `source`（與 `title`）為空的頁；`extracted_readable/*.md` 每頁對應一筆 JSON 且 `_index.md` 產出（.md 數 = `parsed_count`，skipped 頁無 .md） |
| [4] Clean | `python src/clean_pages.py` | `cleaned/*.md` 產出、非空，含 frontmatter（至少 `title`、`source_url`）且 frontmatter 與 `# <title>` 之間有空行；`cleaning_report.md` 產出 |
| [5] Chunk | `python src/chunk_pages.py` | `chunks.jsonl` 每行可 JSON 解析且含 `source_url`、`title`、`section`、`chunk_id`；**每 chunk ≤ 254 wordpieces 斷言通過** |
| [6] Embed | `python src/embed_chunks.py` | `embeddings.jsonl` 每行含 384 維向量、norm = 1、`model_revision` 非空；與 `chunks.jsonl` 逐筆 `chunk_id` 對應一致 |
| [7] Index | 待 schema 定義後補入 | 待定 |
| Documentation | 人工核對 | 文內事實（路徑、檔名、規則引用）與實際狀況一致 |

框架層級決策（§16）：採 grill-me 模式逐項提問，待使用者決策後再實作。

## 14. Documentation Responsibilities

### AGENTS.md（本檔）

只保存：永久規範、不可變契約、Agent 行為邊界、穩定架構規則。
不要保存：當前頁數、chunk 數、Phase 進度、commit 狀態、臨時 bug、一次性 audit 結果。

### ARCHITECTURE.md

保存：[1]–[7] 的**目標架構**定義（pipeline 總覽、目錄結構、各階段職責與參數、schema、更新行為、決策記錄、待確認事項）。
它是目標狀態的單一事實來源，不是進度文件；階段實作狀態以實際程式碼與資料產物為準。

### README.md

保存：專案介紹、安裝、使用方式、人類可讀架構說明、開發者操作方式。

## 15. Handoff Protocol

當 AI 完成一個重要階段時，應確保：

- 若有重大架構決策，同步更新 `ARCHITECTURE.md` 與 `README.md`。
- 回報（§17）：修改了什麼、驗證了什麼、尚未驗證什麼、已知風險、下一步需要使用者決策的事項。

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
- 定義 [4] 噪音規則或 [7] schema（`ARCHITECTURE.md` 明示延後，須待時機成熟）

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
- 當 `ARCHITECTURE.md` 明示某項「待定／擱置／不預先定義」時，不得為其虛構細節。
