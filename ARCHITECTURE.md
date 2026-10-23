# Minecraft_RAG 架構文件

> 本文件是資料準備管線 **[1]–[7]** 的**目標架構與契約**，也是各階段 I/O、欄位與規則的單一事實來源。
> - 實作進度：見 `README.md`「開發狀態」（本文件不記錄進度）
> - 決策理由與實測依據：見 `docs/adr/`（本文件不記錄實測數字）
> - Agent 行為規則：見 `AGENTS.md`

## 1. 專案定位

- **目標**：從 AE2 官方指南（Minecraft 1.21.1）建立可檢索、可附來源的 RAG 知識庫。
- **性質**：輕量級 Wiki RAG side project；一半目標是學習成熟的 RAG 技術棧。
- **本文件範圍**：資料準備管線 [1]–[7]。[7] 的 schema 擱置；檢索（Retrieval）與 UI 不在本文件範圍。

## 2. Pipeline 總覽（各模塊架構圖）

> 本圖由 §5 衍生，用來快速掌握各模塊的「輸入 > 處理 > 輸出」；欄位與規則的正式定義以 §5 為準。
> - 範例取自 `items-blocks-machines/terminals` 頁，**僅為示意**，不保證與最新資料逐字相同。
> - [5]–[7] 只畫已定的框架；「待定」「擱置」項目不畫細節。
> - §5 或任何 ADR 變更時，本圖須在同一次變更中更新。

```text
══════════════════════════════════════════════════════════════════════════════
 共用設定：sources.json（各階段都可以讀；§3 原則 1）
══════════════════════════════════════════════════════════════════════════════

┌─[1] SOURCE ─────────────────────────────────────────────────── sources.json ─┐
│ 輸入  人工維護                                                                │
│ 處理  無（不需要程式）                                                        │
│ 輸出  { "version": "1.21.1",                                                 │
│         "mod": "Applied Energistics 2",          ← 原名，不 slug 化           │
│         "entry_url": "https://guide.appliedenergistics.org/1.21.1/index",    │
│         "exclude": [], "include": [] }           ← 保留欄位，[2] 目前不讀     │
│ 規則  entry_url 只用來推導站台根，不抓取；版本只取自 version                   │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─[2] CRAWL ────────────────────────────────────────── src/fetch_pages.py ─────┐
│ 輸入  sources.json + robots.txt → sitemap.xml（URL 真值來源，ADR-001）         │
│ 處理  ① 找 sitemap（robots 宣告 → 慣例路徑；找不到 → fail-fast）              │
│       ② ElementTree 解析 <loc>                                               │
│       ③ 版本過濾 path.startswith("/1.21.1/")，排除入口頁                      │
│       ④ 逐頁抓取，間隔 0.5 秒                                                │
│       ⑤ 由 URL 解析路徑三元素（只在這裡計算一次）                             │
│          mod_slug  = slugify(mod)          → applied-energistics-2           │
│          chapter   = 去掉版本後的倒數第二段 → items-blocks-machines           │
│          page_slug = 最後一段               → terminals                       │
│          （只有一段的路徑 → chapter = other）                                 │
│ 輸出  data/raw/1.21.1/applied-energistics-2/items-blocks-machines/           │
│         terminals.html                                                       │
│       data/raw/_manifest.json 的一筆：                                       │
│         { "url": ".../1.21.1/items-blocks-machines/terminals",               │
│           "chapter": "items-blocks-machines", "page_slug": "terminals",      │
│           "local_path": "data/raw/1.21.1/.../terminals.html",                │
│           "http_status": 200 }                                               │
│ 失敗  不重試；記錄 http_status 與 local_path: null                            │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─[3] EXTRACT ───────────────────────────────────── src/extract_pages.py ──────┐
│ 輸入  raw HTML + _manifest.json                                              │
│ 處理  ① trafilatura（json 模式）抽出 title／text／source／hostname（原值不改） │
│       ② navigation_only 判定 → 命中就跳過、不輸出                             │
│          規則一：URL 以 -index 結尾            reason = url_ends_with_index   │
│          規則二：文字 < 200 且 <article> 連結密度 > 0.5                       │
│                                    reason = short_text_high_link_density    │
│       ③ 標題結構（ADR-004）：讀 <article> 的 h1–h3                           │
│          → 依序在 text 中找完全相同的行 → 加上 '#' × 原層級                   │
│          （不調整層級、不判斷雜訊）                                           │
│ 輸出  extracted/1.21.1/applied-energistics-2/items-blocks-machines/          │
│         terminals.json                                                       │
│         { "title": "Terminals",                                              │
│           "text": "Terminals\nWhile ME Pattern Providers, ...\n              │
│                    Terminal Placement\n...\nCrafting Terminal\n              │
│                    The UI\nRecipe\n...",                  ← 原值             │
│           "markdown": "# Terminals\nWhile ME Pattern Providers, ...\n        │
│                    ## Terminal Placement\n...\n# Crafting Terminal\n         │
│                    ## The UI\n## Recipe\n...",            ← 只多了 # 記號    │
│           "source": "https://.../items-blocks-machines/terminals",           │
│           "hostname": "appliedenergistics.org", "http_status": 200 }         │
│       + _parse_report.json、reports/extraction_report.md                     │
│       + extracted_readable/**/*.md（給人看，不入版控）                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─[4] CLEAN ───────────────────────────────────────── src/clean_pages.py ──────┐
│ 輸入  extracted JSON（只讀 title／source／markdown）+ sources.json            │
│ 處理  所有規則都用「去掉 # 後的內容」比對（ADR-002、ADR-004）                  │
│       0 前置條件  title 或 source 為空 → 不輸出                               │
│       1 R2        跳轉頁（首行是站名且字數 < 門檻）→ 不輸出                   │
│       2 R1        刪除重複的頁面標題（# Terminals）                           │
│       3 R4a       刪除整行配方標籤（含 ## Recipe）                            │
│       4 R4b       切除單行頁尾端黏住的標籤                                    │
│       5 R6        依相對深度調整層級：                                        │
│                   直屬頁面的標題 → ##；頁內 H1 → ##、它底下的 H2 → ###          │
│       6 R7        刪除空章節（標題底下已無內容，ADR-006）                     │
│       7 守衛      body 為空 → 不輸出；不足 200 字元 → 輸出但在報告標示         │
│ 輸出  cleaned/1.21.1/applied-energistics-2/items-blocks-machines/            │
│         terminals.md                                                         │
│         ---                                                                  │
│         title: Terminals                                                     │
│         source_url: "https://.../items-blocks-machines/terminals"            │
│         ---                                                                  │
│                                                                              │
│         # Terminals                       ← 每頁只有一個 #                   │
│                                                                              │
│         While ME Pattern Providers, ...                                      │
│         ## Terminal Placement                                                │
│         ...                                                                  │
│         ## Crafting Terminal                                                 │
│         ### The UI                                                           │
│         ...                               ← ## Recipe 已被刪除               │
│       + reports/cleaning_report.md（對帳：輸出 + 跳過 + 例外 = 輸入）         │
│ 擁有  cleaned/<version>/ 由 [4] 負責：全部處理完才清空並重建                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─[5] CHUNK ────────────────────────────────────── src/chunk_pages.py ─────────┐
│ 輸入  只讀 cleaned MD                                                         │
│         路徑      → version／mod／chapter／page                               │
│         frontmatter → title／source_url（不改寫；source_url 為空 → 不產出）   │
│ 處理  子母分層（ADR-005）                                                     │
│         MarkdownHeaderTextSplitter → 依 ## 切成 parent（### 併入所屬的 ##）   │
│                                      沒有 ## 的頁 → 整頁一個 parent           │
│         RecursiveCharacterTextSplitter → 在 parent 內切出 child              │
│         BGE-M3 tokenizer 計數，並檢查不超過上限                               │
│ 輸出  parent 文件與 child chunks，兩者都帶完整 provenance：                   │
│         source_url、title、mod、chapter、page、版本、                         │
│         section = 標題路徑，例如 "Crafting Terminal > The UI"                 │
│       child 必須能對應回所屬的 parent                                         │
│ 待定  大小區間與 overlap（先量 token 分布）、ID 格式、parent 的檔名與 schema   │
└──────────────────────────────────────────────────────────────────────────────┘
                     │ child                           │ parent
                     ▼                                 │
┌─[6] EMBED ───────────────────────── src/embed_chunks.py ─┐  │
│ 輸入  child chunks                                        │  │
│ 處理  BAAI/bge-m3（sentence-transformers，本機執行）        │  │
│       dense、1024 維、正規化、鎖定 revision（ADR-003）     │  │
│       只對 child 做 embedding                             │  │
│ 輸出  每筆 child + 1024 維向量 + parent 參照                │  │
│       + model_name／model_revision                        │  │
│       與輸入逐筆對應（順序、ID、metadata 都不變）           │  │
│ 待定  embedding 輸入的拼接格式                             │  │
└──────────────────────────────────────────────────────────┘  │
                     │                                         │
                     ▼                                         ▼
┌─[7] INDEX ─────────────────────────────────────── src/index_chunks.py ───────┐
│ 輸入  [6] 的 child 向量 + [5] 的 parent 文件（docstore 模式）                 │
│ 處理  寫入 PostgreSQL + pgvector                                             │
│         child 向量 → 向量庫（1024 維）                                       │
│         parent    → 能用 parent 參照取回                                     │
│ 擱置  schema、入庫方式、索引類型                                             │
└──────────────────────────────────────────────────────────────────────────────┘

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ 以下不在 [1]–[7] 範圍內 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  Retrieval  英文問題 → 檢索 child → 依 parent 去重 → 取回 parent
             → OpenAI 用繁中回答 + 附 source_url；找不到依據 → 「目前官方文件不足以確認」
  UI         Streamlit
```

**閱讀重點**：

- **職責分工**：結構由 [3] 辨識（只有它看得到 HTML），[4] 只負責去噪與層級調整，[5] 只依 `##` 切分。
- **兩條資料流**：[5] 之後分成 child（經 [6] 轉成向量）與 parent（直接給 [7]），也就是 docstore 模式。
- **共用設定**：`sources.json` 讓多個階段一起讀，屬於正常的設定共用，不算耦合。

## 3. 模塊邊界原則

以業界常見做法（DVC、Kedro 的 parameters／資料目錄；LangChain／LlamaIndex 的 parent-child docstore）為基準，不過度解耦：

1. **設定可以共用**：`sources.json`、模型名稱與 revision、切分參數等設定，任何階段都可以讀。
2. **資料產物依契約讀取**：一個階段讀它所依賴的產物，通常是直接上游；天生需要多份產物的階段（如 [7] 同時讀向量與 parent）可以直接讀多個上游，不需要轉交。
3. **只依賴契約，不依賴實作**：下游只認上游的契約欄位，不需要知道上游工具的行為。
4. **單一職責**：辨識結構 = [3]（唯一看得到 HTML 的階段）；去噪與正規化 = [4]；切分 = [5]。
5. **能單獨重跑、單獨驗證**：每個階段在 `AGENTS.md` §13 有自己的驗收標準；正式產物整份覆寫（冪等）。

## 4. 目錄結構

```text
Minecraft_RAG/
├── sources.json                  ← [1] 設定：版本 + 模組 + 入口 URL
├── src/                          ← pipeline 模組（每階段一支，見 §5）
├── data/
│   ├── raw/                      ← [2] raw HTML + _manifest.json + _fetch_log.txt
│   ├── processed/
│   │   ├── extracted/            ← [3] 真值（JSON）+ _parse_report.json
│   │   ├── extracted_readable/   ← [3] 人類可讀衍生物（不入版控）
│   │   ├── cleaned/              ← [4]（cleaned/<version>/ 由 [4] 擁有，每次重建）
│   │   ├── chunks/               ← [5]
│   │   └── embeddings/           ← [6]
│   └── evaluation/               ← 評估（未來範圍，不屬 [1]–[7]）
├── reports/                      ← 各階段的單次報告（覆蓋）
├── docs/
│   ├── adr/                      ← Architecture Decision Records
│   └── plans/                    ← 過程文件（調查證據、計畫；非規範，不入版控）
├── ARCHITECTURE.md               ← 本文件
├── AGENTS.md                     ← AI Agent 工程契約
└── README.md                     ← 人類使用說明與開發狀態
```

**路徑慣例**：資料產物一律依 `<version>/<mod_slug>/<chapter>/<page_slug>` 分層。路徑三元素只由 [2] 計算一次，下游一律從路徑讀取。檔名以 `_` 開頭的是控制檔（manifest、報告），不是資料頁。

## 5. 各階段契約

### [1] SOURCE — 入口設定

`sources.json`（人工維護）：

```json
{
  "version": "1.21.1",
  "mod": "Applied Energistics 2",
  "entry_url": "https://guide.appliedenergistics.org/1.21.1/index",
  "exclude": [],
  "include": []
}
```

| 欄位 | 語意 |
| --- | --- |
| `version` | Minecraft 版本；決定目錄分層，並一路傳到 chunk |
| `mod` | 模組**原名**，不 slug 化；由 [2] 轉成 `mod_slug` |
| `entry_url` | 只用來推導站台根（scheme + host），**不作為抓取目標**；版本取自 `version`，不由入口頁推導 |
| `exclude`／`include` | 保留於 schema；[2] 目前不讀取（範圍由版本過濾決定） |

`sources.json` 是整條 URL 鏈的起點：`version` + 站台根 → [2] 解析 sitemap.xml 產生逐頁 URL → [3] 抽出 `source` → chunk 的 `source_url`。

### [2] CRAWL — 抓取 raw HTML（`src/fetch_pages.py`）

- **輸入**：`sources.json`；逐頁 URL 的真值來源為 **sitemap.xml**（ADR-001）。
- **職責**：只做網路 I/O；不做 HTML→Markdown、不解析導覽 DOM、不爬側邊欄、不保留任何 fallback。
- **步驟**：
  1. 由 `entry_url` 推導站台根，讀 `robots.txt` 的 `Sitemap:` 宣告；沒有宣告時依序試 `/sitemap.xml`、`/sitemap_index.xml`、`/sitemap-index.xml`。
  2. 有效條件：HTTP 200 且根節點為 `<urlset>` 或 `<sitemapindex>`；全部失敗 → fail-fast（exit 1）。
  3. `xml.etree.ElementTree` 解析；`<sitemapindex>` 遞迴抓子 sitemap 後合併 `<loc>`。
  4. 版本過濾：`urlparse(url).path.startswith(f"/{version}/")`（必須帶尾斜槓）；排除入口頁 `/{version}/index`。
  5. 逐頁抓取，每頁間隔 0.5 秒，存入 `data/raw/<version>/<mod_slug>/<chapter>/<page_slug>.html`。
  6. 輸出 `data/raw/_manifest.json`（整份覆寫）。
- **路徑三元素**（[2] 是唯一的計算來源）：

  | 元素 | 來源 | 範例 |
  | --- | --- | --- |
  | `mod_slug` | `mod` 經 `python-slugify` | `Applied Energistics 2` → `applied-energistics-2` |
  | `chapter` | URL 去掉版本前綴後的倒數第二段；URL 本身已是 slug，不再 slug 化 | `.../1.21.1/ae2-mechanics/energy` → `ae2-mechanics` |
  | `page_slug` | URL 最後一段 | `energy` |

  只有一段的路徑（如 `/1.21.1/getting-started`）一律歸 `chapter = other`。

- **`_manifest.json`**：

  ```json
  {
    "version": "1.21.1",
    "mod": "Applied Energistics 2",
    "mod_slug": "applied-energistics-2",
    "source": "sitemap",
    "fetched_at": "<ISO 8601>",
    "urls": [
      {
        "url": "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/energy",
        "chapter": "ae2-mechanics",
        "page_slug": "energy",
        "local_path": "data/raw/1.21.1/applied-energistics-2/ae2-mechanics/energy.html",
        "http_status": 200,
        "fetched_at": "<ISO 8601>"
      }
    ]
  }
  ```

  `local_path` 是相對專案根目錄的 POSIX 路徑；失敗頁為 `null`。
- **失敗處理**：不重試；記錄 `http_status` 與 `local_path: null`，人工查驗後重跑；有失敗記錄時 exit 1。

### [3] EXTRACT — 抽取主文與標題結構（`src/extract_pages.py`）

- **輸入**：`data/raw/**/*.html` + `data/raw/_manifest.json`（取 `http_status`、`local_path`）。
- **職責**：用 trafilatura 抽主文；辨識頁內標題結構；跳過 navigation_only 頁。
- **步驟**：
  1. `trafilatura.extract(html, output_format="json", with_metadata=True, include_tables=True)`，直接吃 HTML 字串。
  2. **navigation_only 判定**（命中即跳過，不輸出）。兩條規則為 OR，各有獨立的 `reason` 字串：

     | 規則 | 條件 | `reason` |
     | --- | --- | --- |
     | 規則一（URL） | URL path 以 `-index` 結尾 | `url_ends_with_index` |
     | 規則二（內容） | 抽出文字 < 200 字元 **且** `<article>` 內連結密度 > 0.5 | `short_text_high_link_density` |

     連結密度只計算 `<article>`，不計算整頁（側邊欄會拉高短內容頁的密度）。閾值依據見 ADR-001 §6。
  3. **標題結構（ADR-004）**：讀 `<article>` 的 h1–h3，依文件順序用游標往下找 `text` 中去前後空白後完全相同的行，加上 `'#' × 原層級 + ' '`，產生 `markdown`。找不到的標題不加記號，記入報告。不正規化層級、不判斷噪音。
  4. 寫出 extracted JSON、人類可讀衍生物與報告。
- **輸出 JSON**（`data/processed/extracted/<version>/<mod_slug>/<chapter>/<page_slug>.json`）：

  ```json
  {
    "title": "Energy",
    "text": "Energy\nYour network will require energy to run. ...\nEnergy Accepting\n...",
    "source": "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/energy",
    "hostname": "appliedenergistics.org",
    "markdown": "# Energy\nYour network will require energy to run. ...\n## Energy Accepting\n...",
    "http_status": 200
  }
  ```

  | 欄位 | 規則 |
  | --- | --- |
  | `title`／`text`／`source`／`hostname` | trafilatura 原值，**不異動**（`hostname` 不修正） |
  | `markdown` | 等於 `text` 加上標題記號；去掉記號後逐行等於 `text` |
  | `http_status` | 由 `_manifest.json` 帶入 |

  不加 `page_slug`／`chapter`：下游從路徑讀。
- **其他輸出**：
  - `extracted/_parse_report.json`：`{ parsed_count, skipped: [{url, reason}], warnings: [{url?, phase, error}], errors: [] }`。`reason` 只能是上表的兩個值。
  - `reports/extraction_report.md`：計數、跳過頁、空 `source`／`title` 警示、標題對應數與未對應清單。
  - `extracted_readable/**/*.md` + `_index.md`：人類驗收用，路徑鏡像 JSON；內容為 front matter + `# {title}` + `text` 原文。真值以 JSON 為準；寫入失敗只記 warning，不影響 exit code。
- **失敗處理**：trafilatura 回傳 None → 記入 errors，其他頁繼續；缺 `http_status` 或 `text` 為空 → 報告標記。

### [4] CLEAN — 清理與結構正規化（`src/clean_pages.py`）

- **輸入**：`data/processed/extracted/<version>/**/*.json`（只讀 `title`／`source`／`markdown`；缺 `markdown` 視為例外）+ `sources.json`（版本與模組）。
- **職責**：過濾 trafilatura 誤留的噪音、正規化標題層級，輸出含 frontmatter 的乾淨 Markdown。規則只作用於正文；`title`、`source` 原封傳遞。
- **規則（依序；定義與白名單見 ADR-002，標題相關見 ADR-004）**：所有規則以「去掉標題記號後的行內容」比對，標題行與一般行套用同一套規則。

  | 順序 | 規則 | 摘要 |
  | --- | --- | --- |
  | 0 | 前置條件 | `title` 或 `source` 為空 → 不輸出，記入報告 |
  | 1 | R2 跳轉頁排除 | 首行 == 站名且全頁字元數 < 門檻 → 不輸出；首行為站名但未排除 → 報告警告 |
  | 2 | R1 首行標題去重 | A：首行（含 `# <title>`）== title → 刪；B：title 黏在句首 → 切前綴（有守衛）；C：次行 == title → 刪 |
  | 3 | R4a 整行標籤 | 整行 == 白名單標籤 → 刪（含 `## Recipe` 這類標題行） |
  | 4 | R4b 黏合尾端標籤 | 只作用於整頁單行的頁；行尾黏合的標籤序列 → 切除 |
  | 5 | R6 標題層級正規化 | 依相對深度輸出 `##`／`###`／`####`：一般頁 h2 → `##`；多 H1 頁的頁內 H1 → `##`、其下 H2 → `###`；每頁只保留 `# <title>` |
  | 6 | R7 空章節移除 | 標題範圍內（到下一個同層或更高層標題為止）沒有任何內容 → 刪除該標題；由深到淺判定（ADR-006） |
  | 7 | 空 body 守衛 | 處理後 body 為空 → 不輸出；不足 200 字元 → 輸出並在報告標示 |

  R2 門檻與字元統計以去掉標題記號的純文字計算。
- **輸出格式**（`data/processed/cleaned/<version>/<mod_slug>/<chapter>/<page_slug>.md`）：

  ```markdown
  ---
  title: Terminals
  source_url: "https://guide.appliedenergistics.org/1.21.1/items-blocks-machines/terminals"
  ---

  # Terminals

  While ME Pattern Providers, ... There are several variants with differing functions.
  ## Terminal Placement
  As a terminal is often the first subpart someone might place, ...
  ## Crafting Terminal
  ### The UI
  ...
  ```

  - frontmatter 至少含 `title`、`source_url`，值由 extracted JSON 原封寫入；frontmatter 與 H1 的 `title` 一致，不一致時以 frontmatter 為準。
  - frontmatter 與 `# <title>` 之間、`# <title>` 與正文之間各一個空行；正文段落之間沒有空行（trafilatura json 模式不保留段落）。
  - UTF-8、LF、檔尾單一換行。
- **目錄擁有權**：`cleaned/<version>/` 由 [4] 擁有。全部頁面在記憶體處理完、且至少一頁有產出後，才清空並重建；路徑斷言限定該版本子樹，不動 `cleaned/.gitkeep`。
- **報告**：`reports/cleaning_report.md`。內容包含：
  - 對帳：輸出 + 跳過 + 例外 = 輸入
  - 各規則命中數、R6 各層級標題數
  - 跳過頁清單、標籤刪除摘要、孤立 `-` 計數、疑似新標籤、警告附錄
- **失敗處理**：讀取或處理例外 → 逐頁隔離、記入報告、exit 1；沒有任何頁產出 → 中止、不清空既有輸出、exit 1。
- **前提**：規則依「無圖片版本」的抽取結果校準；站方改版或 [3] 改抽圖片屬性時須重新盤點（ADR-002）。

### [5] CHUNK — 子母分層切分（`src/chunk_pages.py`）

> 框架已定（ADR-005）；參數、ID 與欄位格式待實作時定義，不預先虛構。

- **輸入**：只讀 `data/processed/cleaned/**/*.md`（不讀 extracted JSON 或 manifest）。
- **metadata 來源**：

  | 類別 | 欄位 | 來源 |
  | --- | --- | --- |
  | 結構性 | `version`／`mod`／`chapter`／`page` | 目錄路徑（slug 形式）；frontmatter 同名欄位不讀 |
  | 內容性 | `title`／`source_url` | frontmatter（不重新計算、不改寫）；`source_url` 為空 → 該頁不產出、報錯 |
  | 章節 | `section` | 標題路徑（如 `Crafting Terminal > The UI`），由 `MarkdownHeaderTextSplitter` 提供 |

- **已定的處理方式**：
  - parent = 一個 `##` 章節（`###` 併入所屬的 `##`）；沒有 `##` 的頁，parent = 整頁；超過上限時再切。
  - child = 在 parent 內切出的片段，只有 child 進 embedding。
  - 工具：`MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`（langchain-text-splitters）；以 **BGE-M3 tokenizer** 計數，並斷言不超過上限。
  - child 與 parent 都必須帶完整 provenance（`source_url`、`title`、`mod`、`chapter`、`page`、`section`、版本），child 必須能對應到 parent。
  - slug 只用於路徑、ID 與 `mod`／`chapter`／`page`；`text`、`title`、`section` 禁止 slug 化。
- **待定**：大小區間與 overlap（先量測 token 分布）、第一個 `##` 之前的開頭段落歸屬哪個 parent、ID 格式（含跨 chapter 同名頁碰撞處理）、parent 產物的檔名與 schema。

### [6] EMBED — 向量化（`src/embed_chunks.py`）

> 框架已定（ADR-003）；輸入格式待實作時定義。

- **輸入**：[5] 的 child chunks。
- **已定**：
  - `BAAI/bge-m3`，由 sentence-transformers 本機載入，只用 dense 向量，1024 維，`normalize_embeddings=True`。
  - **鎖定 revision**，並把 `model_name`、`model_revision` 寫入輸出。
  - 輸出逐筆對應輸入 child（順序與 ID 一致，metadata 不得變動），並帶 parent 參照。
- **待定**：embedding 輸入的拼接格式（slug 前綴或原始 title／section 路徑）。

### [7] INDEX — 寫入 pgvector（`src/index_chunks.py`，擱置）

- **已定**：PostgreSQL + pgvector；docstore 模式（child 向量進向量庫，parent 文件能由 parent 參照取回）；輸入為 [6] 的向量產物與 [5] 的 parent 產物；向量 1024 維。
- **擱置**：schema、入庫方式、索引類型，待 [1]–[6] 跑通後依實際資料定義。

## 6. 更新行為

| 產物 | 更新行為 |
| --- | --- |
| `sources.json` | 人工維護 |
| `data/raw/_manifest.json`、`_fetch_log.txt` | 單次記錄，覆蓋；`_fetch_log.txt` 為 debug log，不入版控 |
| `extracted/**/*.json`、`_parse_report.json` | 單次記錄，覆蓋 |
| `extracted_readable/**/*.md` | 單次記錄，覆蓋；不入版控，可由 [3] 重產 |
| `cleaned/<version>/**/*.md` | 由 [4] 擁有，每次重建 |
| [5]／[6] 產物 | 單次記錄，覆蓋 |
| `reports/*.md` | 單次報告，覆蓋 |

所有中間產物都是單次記錄，**不做 history**；各階段可獨立重跑，整份覆寫（冪等）。

## 7. 決策索引

| ADR | 決策 |
| --- | --- |
| `ADR-001` | [2] 以 sitemap.xml 為 URL 真值來源，廢除側邊欄爬取、不保留 fallback |
| `ADR-002` | [4] 噪音規則（無圖片版本）：R2 → R1 → R4a → R4b → 空 body 守衛；不回 [3] 重抽 |
| `ADR-003` | Embedding 改用 BGE-M3（dense、1024 維、revision 鎖定），取代 MiniLM |
| `ADR-004` | 保留頁內標題結構：[3] 產生 `markdown`、[4] 新增 R6 |
| `ADR-006` | [4] 新增 R7：移除去噪後只剩標題的空章節 |
| `ADR-005` | [5] 採子母分層切分（docstore 模式） |

其他已定的架構原則（尚未寫成 ADR）：

- 抓取與抽取分離。
- metadata 依「結構性看路徑、內容性看 frontmatter」分工。
- `title` 全程不異動。
- 中間產物不做 history。

## 8. 待確認事項

| 事項 | 狀態 |
| --- | --- |
| [5] child／parent 大小區間、overlap | 待以 BGE-M3 tokenizer 量測 cleaned MD 後定案 |
| [5] 開頭段落（第一個 `##` 之前）的 parent 歸屬 | 待 [5] 實作時定義（切分職責，不由上游處理） |
| [5] ID 格式、parent 產物格式 | 待 [5] 實作時定義（含跨 chapter 同名頁碰撞） |
| [5] frontmatter 是否會被 `MarkdownHeaderTextSplitter` 當成內容 | 待實作驗證 |
| [6] embedding 輸入拼接格式 | 待 [6] 實作時定義 |
| 查詢語言策略（英文檢索 + 繁中回答） | BGE-M3 支援多語言，可重新評估（範圍外，另行決策） |
| [7] schema、入庫方式、索引類型 | 擱置 |
