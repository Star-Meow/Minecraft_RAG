# Minecraft_RAG 架構文件——資料準備 Pipeline 目標狀態

> 本文件描述資料準備管線 **[1]–[7]** 的目標架構。
> **[1]–[6]** 為現階段目標；**[7] 入庫擱置**，schema 待 [1]–[6] 跑通後定義。
> **[4] 噪音規則不預先定義**，待第一波資料處理後從樣本歸納。

## 1. 專案定位

- **目標**：從 AE2 官方指南（Minecraft 1.21.1）抓取知識，建立可檢索的 RAG 系統。
- **性質**：輕量級 Wiki RAG side project；**一半目標是學習成熟 RAG 技術棧**。
- **技術選型**：pgvector（**已確認合理**，schema 待資料準備後定義）。
- **現階段範圍**：資料準備 pipeline [1]–[6]；[7] 入庫擱置。

## 2. Pipeline 總覽

```text
[1] 入口 URL / sources.json
      ↓
[2] 抓取 raw HTML（fetch_pages.py）
      ↓
[3] 抽取主文（extract_pages.py + trafilatura）
      ↓
[4] 清理與結構化（噪音規則待第一波資料後確認）
      ↓
[5] 切分（chunk_pages.py + 真 tokenizer）
      ↓
[6] Embedding（embed_chunks.py + MiniLM）
      ↓
[7] 寫入 pgvector（schema 待 [1]–[6] 跑通後定義）
```

## 3. 目錄結構

```text
Minecraft_RAG/
├── sources.json                      ← [1] 輸入：入口 URL + 版本 + 模組
├── data/
│   ├── raw/                          ← [2] 抓取
│   │   ├── _manifest.json            ← 單次抓取記錄（覆蓋）
│   │   └── 1.21.1/
│   │       └── applied-energistics-2/
│   │           └── <chapter>/
│   │               └── *.html
│   ├── processed/
│   │   ├── extracted/                ← [3] 抽取
│   │   │   └── 1.21.1/
│   │   │       └── applied-energistics-2/
│   │   │           └── <chapter>/
│   │   │               └── *.json
│   │   ├── cleaned/                  ← [4] 清理
│   │   │   └── 1.21.1/
│   │   │       └── applied-energistics-2/
│   │   │           └── <chapter>/
│   │   │               └── *.md
│   │   ├── chunks/                   ← [5] 切分
│   │   │   └── chunks.jsonl
│   │   └── embeddings/               ← [6] Embedding
│   │       └── embeddings.jsonl
│   └── evaluation/                   ← 評估（未來範圍，不屬 [1]–[7]）
├── reports/                          ← 驗證報告
│   ├── extraction_report.md          ← [3] 單次報告（覆蓋）
│   └── cleaning_report.md            ← [4] 單次報告（覆蓋）
└── src/
    ├── fetch_pages.py                ← [2] 抓取
    ├── extract_pages.py              ← [3] 抽取
    ├── clean_pages.py                ← [4] 清理
    ├── chunk_pages.py                ← [5] 切分
    ├── embed_chunks.py               ← [6] Embedding
    └── index_chunks.py               ← [7] 入庫（擱置）
```

**路徑慣例**：所有資料產物按 `<version>/<mod_slug>/<chapter>/` 分層，版本、模組與章節一路傳遞至最終 chunk。chapter 層由 [2] 從 URL 解析後寫入路徑，下游全部從路徑讀（見 §4 [2]）。

## 4. 各階段架構

### [1] 入口與抓取範圍

`sources.json` 內容：

```json
{
  "version": "1.21.1",
  "mod": "Applied Energistics 2",
  "entry_url": "https://guide.appliedenergistics.org/1.21.1/index",
  "exclude": [],
  "include": []
}
```

- `mod` 存**模組原名**（`Applied Energistics 2`），**不 slug 化**；[2] 才用 `python-slugify` 轉成 `mod_slug` 寫入路徑。
- **入口僅作為導航來源，不作為抓取目標**。
- **整條 URL 鏈的起點**：`sources.json` 的 `entry_url` 是 pipeline 所有 URL 的源頭；逐頁 URL 由 [2] 解析其側邊欄導覽產生，再經 [3] trafilatura 抽取為 `source`，一路傳至 chunk 的 `source_url`（見 §4 [5]）。
- **抓取範圍**：入口頁側邊欄的所有 `<a href>`。
- **方式**：BeautifulSoup 解析導航。
- **廢棄舊的 sources.json**（6 頁人工清單）。

### [2] 抓取 raw HTML

- **輸入**：`sources.json` 的 `entry_url`
- **職責**：只負責網路 I/O，**不做 HTML→Markdown 轉換**；同時解析路徑三元素（`mod_slug`／`chapter`／`page_slug`）並寫入目錄
- **步驟**：
  1. 抓入口頁（僅作為導航來源）
  2. 用 BeautifulSoup 解析側邊欄導航，取得所有子頁面 URL
  3. 逐頁抓取 raw HTML，每頁間隔 0.5 秒
  4. 對每個 URL 解析路徑三元素，存入 `data/raw/<version>/<mod_slug>/<chapter>/<page_slug>.html`
  5. 輸出 `data/raw/_manifest.json`（單次記錄，覆蓋）

- **路徑三元素解析規則**（[2] 唯一計算來源，下游一律從路徑讀）：

  | 元素 | 來源 | 範例 |
  | --- | --- | --- |
  | `mod_slug` | `sources.json` 的 `mod` 經 `python-slugify` 轉換 | `Applied Energistics 2` → `applied-energistics-2` |
  | `chapter` | URL **去掉版本前綴後的倒數第二段**；URL 本身已是 slug，**不另行 slug 化** | `.../1.21.1/ae2-mechanics/energy` → `ae2-mechanics` |
  | `page_slug` | URL 最後一段 | `.../ae2-mechanics/energy` → `energy` |

  - **根目錄頁歸類**：`/1.21.1/getting-started`、`/1.21.1/tips-and-tricks` 這類只有一段的路徑，倒數第二段會抓到版本號；此類頁 chapter 統一為 `other`（如 `applied-energistics-2/other/getting-started.html`），作為「沒有 chapter」的預設歸類，確保每頁都恰好有一層 chapter、下游路徑解析一致。
  - slug 只用於**路徑與命名**（資料夾名、檔名、`chunk_id`）；**內容欄位（`text`、`section`）禁止 slug 化**。

- **`_manifest.json` 結構**：

  ```json
  {
    "version": "1.21.1",
    "mod": "Applied Energistics 2",
    "mod_slug": "applied-energistics-2",
    "fetched_at": "2026-09-25T14:00:00",
    "entries": [
      {
        "url": "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/energy",
        "local_path": "data/raw/1.21.1/applied-energistics-2/ae2-mechanics/energy.html",
        "http_status": 200,
        "fetched_at": "2026-09-25T14:00:00"
      }
    ]
  }
  ```

  - `mod` 保留**原名**，`mod_slug` 為 slug 化結果；兩者都記錄，讓 `_manifest.json` 可單獨追溯原名。
  - `entries[].local_path` 已含 chapter 層；失敗頁 `local_path` 為 `null`。

- **失敗處理**：不重試，記錄 `http_status` 與 `local_path: null`，人工查驗後再次執行

### [3] 抽取主文

- **輸入**：`data/raw/<version>/<mod_slug>/<chapter>/*.html`
- **職責**：用 **trafilatura** 從 raw HTML 抽取主文
- **步驟**：
  1. 遍歷 `data/raw/<version>/<mod_slug>/<chapter>/` 下的所有 HTML
  2. 從 `_manifest.json` 取得每個 URL 的 `http_status`
  3. 對每個檔案呼叫：

     ```python
     trafilatura.extract(html, output_format="json", with_metadata=True, include_tables=True)
     ```

  4. 存入 `data/processed/extracted/<version>/<mod_slug>/<chapter>/<page_slug>.json`
- **輸出 JSON 結構**：

  ```json
  {
    "title": "Autocrafting",
    "text": "...",
    "source": "https://...",
    "hostname": "guide.appliedenergistics.org",
    "http_status": 200
  }
  ```

  - **不加 `page_slug`／`chapter` 欄位**：這些 metadata 由 [5] 直接從**目錄路徑**讀取，extracted JSON 只保留 trafilatura 原始輸出與 `http_status`。
  - **`title` 保留不異動**：trafilatura 抽出的 `title` 原封留在 extracted JSON，由 [4] 帶入 cleaned MD 的 H1。

- **狀態判斷**：`http_status` + `text` 是否為空；報告記錄 `source`（與 `title`）是否為空，供人工查驗（不預寫 fallback）
- **更新行為**：單次記錄，覆蓋

### [4] 清理與結構化（噪音規則待確認）

- **輸入**：`data/processed/extracted/<version>/<mod_slug>/<chapter>/*.json`
- **職責**：過濾 trafilatura 誤留的噪音，輸出乾淨的 MD
- **步驟**：
  1. 遍歷 `extracted/*.json`
  2. 讀 `title`、`source`、`text` 欄位（`title` → frontmatter 與 H1；`source` → frontmatter 的 `source_url`）
  3. 用正則或規則過濾噪音（**規則待第一波資料處理後再確認**）
  4. 存入 `data/processed/cleaned/<version>/<mod_slug>/<chapter>/<page_slug>.md`
  5. 產生 `reports/cleaning_report.md`
- **cleaned MD 格式**：**保留 frontmatter 與 H1**，frontmatter 至少含 `title`、`source_url`，其後為 `# <頁面標題>` + 正文：

  ```markdown
  ---
  title: Energy
  source_url: https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/energy
  ---

  # Energy

  Your network will require energy to function.

  ## Energy Accepting

  Machines that accept energy will pull it from the network automatically.
  ```

  - `title`／`source_url` 由 [4] 從 extracted JSON 原封寫入（**資料不異動**，不改寫）；frontmatter 可含其他欄位供人類閱讀，但 [5] 只讀 `title`／`source_url`。
  - **空行要求**：frontmatter 區塊與 `# <title>` 之間以空行分隔；`# <title>` 與正文之間以空行分隔（避免影響 Markdown 解析與 MarkdownHeaderTextSplitter）。
  - 其餘 metadata（版本／模組／章節／頁面）的**權威來源為目錄路徑**；frontmatter 若含這些欄位，僅供人類閱讀，[5] 不從 frontmatter 讀取。
- **備註**：噪音規則不預先定義，先跑 [3] 看輸出，再從樣本歸納

### [5] 切分

- **輸入**：`data/processed/cleaned/<version>/<mod_slug>/<chapter>/*.md`
- **只讀 cleaned MD**：[5] **不讀** `extracted/*.json`、**不讀** `_manifest.json`。**內容性 metadata**（`title`／`source_url`）從 frontmatter 讀；**結構性 metadata** 由以下 snippet 從路徑讀取（只讀檔名與資料夾名，不解析檔案內容）：

  ```python
  page_slug = md_file.stem                          # "energy"
  chapter   = md_file.parent.name                   # "ae2-mechanics"
  mod_slug  = md_file.parent.parent.name            # "applied-energistics-2"
  version   = md_file.parent.parent.parent.name     # "1.21.1"
  ```

  - 三元素在 [2] 就已寫入路徑（見 §4 [2]），[5] 只需解析路徑，不需 slug 化任何東西。
- **職責**：用 **MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter** 切分
- **當前模型**：`all-MiniLM-L6-v2`（`max_seq_length = 256`）
- **切分參數**：
  - `chunk_size`：200 token
  - `chunk_overlap`：40–50 token
  - **tokenizer：MiniLM 的真實 tokenizer**（非字元近似）
- **切分後斷言**：每個 chunk ≤ 254 wordpieces
- **輸出**：`data/processed/chunks/chunks.jsonl`
- **chunk metadata**：

  | 欄位 | 說明 |
  | --- | --- |
  | `chunk_id` | `{mod_slug}_{page_slug}_{seq}_{version}`，如 `applied-energistics-2_energy_0001_v1` |
  | `text` | 原文 |
  | `title` | 頁面標題（從 cleaned MD 的 frontmatter 讀，源頭為 extracted JSON 的 `title`） |
  | `mod` | 模組（**從路徑讀，slug 形式**，如 `applied-energistics-2`） |
  | `chapter` | 章節（**從路徑讀，slug 形式**，如 `ae2-mechanics`；無 chapter 的頁為 `other`） |
  | `page` | 頁面（**從檔名讀，slug 形式**，如 `energy`；非 `title`） |
  | `section` | 頁面內子標題（MarkdownHeaderTextSplitter 提供） |
  | `source_url` | 來源 URL（來自 cleaned MD 的 frontmatter；值為 extracted JSON 的 `source`） |
  | `token_count` | token 數 |

  - **`seq` 以 page 為單位**：同一頁的 chunk 從 `0001` 開始遞增（`energy` 頁：`..._energy_0001_v1`、`..._energy_0002_v1`）。
  - **已知風險（延後處理）**：`chunk_id` 不含 `chapter`，跨 chapter 的同名 page（如 `ae2-mechanics/energy` 與 `items-blocks-machines/energy`）會使 `chunk_id` 碰撞。碰撞實際發生時再解決；預留方案 A：`seq` 改全域遞增；方案 B：`chapter` 加入 `chunk_id`。

  - **欄位來源（`mod`／`chapter`／`page` 明確定義，非待定項）**：三者全部由路徑讀取，源頭是 [2] 從 URL 解析寫入的路徑三元素；`title`／`source_url` 由 [4] 從 extracted JSON 原封寫入 cleaned MD 的 frontmatter（`title` 同時寫入 H1），[5] 讀 frontmatter；`section` 由 MarkdownHeaderTextSplitter 提供。
  - **`title` 欄位（資料不異動原則）**：extracted JSON 的 `title`（trafilatura 抽取結果）由 [4] 原封寫入 cleaned MD 的 frontmatter 與第一個 `#` 標題；[5] **讀 frontmatter** 寫入 chunk metadata，**不重新計算、不改寫**；H1 供 MarkdownHeaderTextSplitter 當結構，非 title 來源。生成答案時直接用 chunk 裡的 `title`，**不回查 extracted JSON**。
  - **`title` 與 `page` 是兩個獨立欄位**：`title` = 頁面標題原文（如 `Energy`），從 cleaned MD 的 frontmatter 讀；`page` = 路徑 slug（如 `energy`），從檔名讀。兩者不可互相替代。
  - **`source_url` 來源**：來自 cleaned MD 的 frontmatter，值為 extracted JSON 的 `source`（trafilatura 從 HTML 抽出）；鏈路起點為 `sources.json`（`entry_url` → [2] 解析側邊欄導覽產生逐頁 URL → [3] trafilatura 抽取）。`_manifest.json` 的 `url` 是「實際抓取的 URL」，`source_url` 取值以 trafilatura 的 `source` 為準；若 frontmatter 的 `source_url` 為空，[5] 中止該頁處理並報錯（不產出該頁 chunk）。
  - **權威來源分離**：結構性 metadata（`version`／`mod`／`chapter`／`page`）權威來源為**目錄路徑**，frontmatter 對應欄位 [5] 不讀（僅供人類閱讀）；內容性 metadata（`title`／`source_url`）由 **frontmatter 承載**（路徑推不出）。frontmatter 與 H1 的 `title` 由 [4] 保證一致；若不一致，以 frontmatter 為準。
  - **frontmatter 與 splitter 的界線待驗證**：frontmatter 是否進 MarkdownHeaderTextSplitter 依其實際行為決定，實作時驗證，本契約不預設（見 §7 待確認）。
  - **slug 只用於路徑與命名**：`mod`／`chapter`／`page` 欄位為 slug 值，**不可**用於 `text`、`title` 或 `section`（`title`／`section` 保留原始大小寫與空白）。
  - `chunk_id` 結尾的 `v1` 為**內容修訂號**：該 chunk 內容需要更新時迭代為 `v2`、`v3`。
- **未來優化**：
  - `requires`：跨模組關聯（視需要再補）
- **備註**：未來以 `BAAI/bge-base-en-v1.5` 交叉比對，需同步調整 chunk 大小

### [6] Embedding

- **輸入**：`data/processed/chunks/chunks.jsonl`
- **職責**：對每個 chunk 做向量化
- **模型**：`sentence-transformers/all-MiniLM-L6-v2`（384 維）
- **模型 revision：鎖定**
- **embedding 輸入**：拼接文字（`{mod} | {page} | {section}\n\n{text}`）；其中 `mod`／`page` 為**從路徑讀的 slug 值**（如 `applied-energistics-2`／`energy`），非頁面原始標題——資訊量較標題低，對檢索的實際影響待 [6] 實作時評估
- **步驟**：
  1. 讀 `chunks.jsonl`
  2. 對每個 chunk，拼接 embedding 輸入文字
  3. 用 MiniLM encode，`normalize_embeddings=True`
  4. 輸出 `embeddings.jsonl`
- **輸出**：`data/processed/embeddings/embeddings.jsonl`
- **`embeddings.jsonl` 每行結構**：

  ```json
  {
    "chunk_id": "...",
    "text": "...",
    "title": "...",
    "mod": "...",
    "chapter": "...",
    "page": "...",
    "section": "...",
    "source_url": "...",
    "token_count": 198,
    "embedding": [...],
    "model_name": "all-MiniLM-L6-v2",
    "model_revision": "..."
  }
  ```

### [7] 寫入 pgvector（擱置）

- **輸入**：`data/processed/embeddings/embeddings.jsonl`
- **職責**：把向量和 metadata 寫入 pgvector
- **技術選型**：pgvector（**已確認合理**）
- **schema**：待 [1]–[6] 跑通後，根據實際資料定義
- **入庫方式**：待定
- **索引類型**：待定
- **狀態**：擱置，等資料準備後再執行

## 5. 更新行為

| 檔案 | 更新行為 |
| --- | --- |
| `sources.json` | 人工維護 |
| `_manifest.json` | 單次記錄，覆蓋 |
| `extracted/*.json` | 單次記錄，覆蓋 |
| `cleaned/*.md` | 單次記錄，覆蓋 |
| `chunks.jsonl` | 單次記錄，覆蓋 |
| `embeddings.jsonl` | 單次記錄，覆蓋 |
| `extraction_report.md` | 單次報告，覆蓋 |
| `cleaning_report.md` | 單次報告，覆蓋 |

**原則**：所有中間產物都是單次記錄，**不做 history**。各階段可獨立重跑，輸出整份覆寫（冪等）。

## 6. 關鍵決策記錄

| 決策 | 內容 |
| --- | --- |
| 廢棄 `sources.json` 的舊形式 | 從「6 頁人工清單」改為「入口 URL + 版本 + 模組」 |
| 抓取與抽取分離 | `fetch_pages.py` 只抓取，`extract_pages.py` 用 trafilatura 抽取 |
| 目錄按版本／模組／章節分 | `data/raw/<version>/<mod_slug>/<chapter>/`；metadata 由路徑承載，下游不讀 JSON |
| `mod` 來源 | `sources.json` 存模組**原名**（`Applied Energistics 2`）；[2] 以 `python-slugify` 轉 `mod_slug` 寫入路徑（slug 只用於路徑與命名） |
| `chapter`／`page_slug` 來源 | [2] 從 URL 解析（chapter 為去版本前綴之倒數第二段，無 chapter 的頁歸 `other`；page_slug 為最後一段），URL 本已是 slug 不另行 slug 化 |
| `title` 帶入 chunk metadata | extracted JSON 的 `title` 由 [4] 寫入 cleaned MD 的 frontmatter（與 H1），[5] 讀 frontmatter；生成答案直接用 chunk 的 `title`，不回查 JSON（資料不異動） |
| cleaned MD 保留 frontmatter 與 H1 | frontmatter 承載 `title`／`source_url` 供 [5] 讀 metadata；H1 供 MarkdownHeaderTextSplitter 當結構；各按各的邏輯索取（見 §4 [4]／[5]） |
| 單次記錄，覆蓋 | 所有中間產物都是單次記錄，不做 history |
| `chunk_id` 格式 | `{mod_slug}_{page_slug}_{seq}_{version}`，如 `applied-energistics-2_energy_0001_v1`；結尾版本號為內容修訂號，chunk 更新時迭代 |
| embedding 輸入拼接 | `{mod} \| {page} \| {section}\n\n{text}` |
| pgvector 選型確認 | 合理，schema 待資料準備後定義 |

## 7. 待確認事項

| 事項 | 狀態 |
| --- | --- |
| [4] 噪音規則 | 待第一波資料處理後確認 |
| frontmatter 是否進 MarkdownHeaderTextSplitter | **待實作驗證**：依 splitter 實際行為決定，契約不預設（見 §4 [5]） |
| [5] 同名 page `chunk_id` 碰撞 | **延後處理**：`chunk_id` 不含 chapter；碰撞實際發生時在方案 A（seq 全域遞增）與方案 B（chapter 入 ID）間擇一 |
| [7] schema | 待 [1]–[6] 跑通後定義 |
| [7] 入庫方式 | 待定 |
| [7] 索引類型 | 待定 |
| 舊版資料產物清除 | 已確認清除、不保留（見 §9） |

> `mod`／`chapter`／`page_slug` 的推導規則**已定義**（見 §4 [2]），不再列為待確認項。

## 8. 本階段不處理

- **不要在這一階段定義 [4] 的噪音規則**
- **不要在這一階段定義 [7] 的 schema**
- **不要在這一階段做 [7] 的入庫實作**

## 9. 舊架構產物處置

重整為本架構時，下列舊格式產物**已確認清除、不保留**：

- `data/raw/<host>/*.html`（舊目錄分層，6 份）
- `data/processed/<host>/*.md`（舊目錄分層，6 份）
- `data/chunks.jsonl`（舊 chunk schema，32 chunks）
- `data/embeddings.jsonl`（舊 embedding schema，32 筆）

理由：舊產物的目錄分層（`<host>/`）、切分策略與 chunk schema 與本文件 [1]–[6] 皆不相容，保留只會造成新舊兩套資料並存的混淆；新管線跑通後以新路徑整份重產生。

舊架構的已知結構問題一併由本架構解決：

| 舊問題 | 本架構解法 |
| --- | --- |
| `index` 頁導覽 chunk 為檢索噪音 | [1] 入口頁僅作導航來源，不作為抓取目標 |
| 自寫 HTML→Markdown renderer 為主要 bug 來源 | [3] 改用 trafilatura，[2] 只負責網路 I/O |
| `chunk_id` 頁內編號、非全域唯一 | [5] 改為 `{mod_slug}_{page_slug}_{seq}_{version}`（如 `applied-energistics-2_energy_0001_v1`） |
| embedding 模型 revision 未鎖定、不可重現 | [6] revision 鎖定並記錄於輸出 |
| chunk 目標尺寸超出模型上限、尾端被截斷 | [5] chunk_size 200 + 真 tokenizer + ≤254 wordpieces 斷言 |
| token 估算為字元近似 | [5] 改用 MiniLM 真實 tokenizer 計數 |
