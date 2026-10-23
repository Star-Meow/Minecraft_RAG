# Architecture

> 本文件是專案的**架構地圖**：模塊有哪些、怎麼串接、邊界在哪、哪些事刻意不做。
> 每個模塊的輸入、輸出、方法與決策理由，寫在 `docs/` 的模塊文件中；本文件不放實作細節，也不記錄進度。

## 1. 概覽

從 AE2 官方指南（Minecraft 1.21.1）建立可檢索、可附來源的 RAG 知識庫。資料準備管線分為六個模塊，單向串接；每個模塊讀上游產物、寫自己的輸出，可單獨重跑。

**範圍外**：檢索（Retrieval）、回答生成與 UI。已定的方向是英文檢索、OpenAI 繁中回答、Streamlit；BGE-M3 支援多語言後，查詢語言策略可重新評估。

## 2. 架構簡圖

```text
 sources.json（共用設定）
      │
      ▼
 ┌──────────────┐   raw HTML    ┌──────────┐ extracted JSON ┌──────────┐  cleaned MD
 │ 來源設定與抓取 │ ────────────▶ │   抽取    │ ─────────────▶ │   清理    │ ───────────┐
 └──────────────┘ + manifest    └──────────┘  (含 markdown) └──────────┘            │
                                                                                     ▼
                                                                               ┌──────────┐
                              ┌────────────── parent 文件 ────────────────────│   切分    │
                              │                                               └──────────┘
                              │                                                     │ child chunks
                              ▼                                                     ▼
                        ┌──────────┐            child + 向量                  ┌──────────┐
                        │   入庫    │ ◀────────────────────────────────────── │  向量化   │
                        └──────────┘                                         └──────────┘
                     PostgreSQL + pgvector（擱置）
```

## 3. 模塊地圖

| 模塊 | 文件 | 程式 | 輸入 | 輸出位置 |
| --- | --- | --- | --- | --- |
| 來源設定與抓取 | `docs/01_fetch.md` | `src/fetch_pages.py` | `sources.json`、sitemap.xml | `data/raw/` |
| 抽取 | `docs/02_extract.md` | `src/extract_pages.py` | raw HTML、`_manifest.json`、`sources.json`（`exclude`） | `data/processed/extracted/`（另有 `extracted_readable/`） |
| 清理 | `docs/03_clean.md` | `src/clean_pages.py` | extracted JSON | `data/processed/cleaned/` |
| 切分 | `docs/04_chunk.md` | `src/chunk_pages.py`（尚未實作） | cleaned MD | `data/processed/chunks/` |
| 向量化 | `docs/05_embed.md` | `src/embed_chunks.py`（尚未實作） | child chunks | `data/processed/embeddings/` |
| 入庫 | `docs/06_index.md` | `src/index_chunks.py`（擱置） | child 向量、parent 文件 | PostgreSQL + pgvector |

其他：各模塊的單次報告放在 `reports/`（不入版控）；評估資料預留在 `data/evaluation/`（範圍外）；疑難排解見 `docs/07_troubleshooting.md`。

## 4. 模塊邊界原則

以業界常見做法（DVC、Kedro 的共用參數；LangChain／LlamaIndex 的 parent-child docstore）為基準，不過度解耦：

1. **設定可以共用**：`sources.json`、模型名稱與 revision、切分參數等設定，任何模塊都可以讀。
2. **資料產物依契約讀取**：一個模塊讀它所依賴的產物，通常是直接上游；天生需要多份產物的模塊（入庫同時讀向量與 parent）可以直接讀多個上游，不需要轉交。
3. **只依賴契約，不依賴實作**：下游只認上游定義的欄位與格式，不需要知道上游工具的行為。
4. **單一職責**：辨識結構＝抽取（唯一看得到 HTML 的模塊）；去噪與層級正規化＝清理；分組與大小＝切分。
5. **格式只在產出它的模塊定義一次**：下游文件只引用，不重寫。

## 5. 不變式

**資料與來源**

- 唯一資料來源是 AE2 官方 1.21.1 指南；版本資訊由目錄路徑承載並貫穿全鏈，不同版本不混用。
- 每個 chunk（含 parent 與 child）保留 `source_url`、`title`、`page`、`chapter`、`section` 與版本；沒有 `source_url` 的內容不進入知識庫。
- `title` 從抽取到 chunk 全程**不改寫**；trafilatura 的原始欄位不改寫。
- 結構性 metadata（版本／模組／章節／頁面）以**目錄路徑**為準；內容性 metadata（`title`／`source_url`）以 **frontmatter** 為準。
- slug 只用於路徑、檔名、ID 與 `mod`／`chapter`／`page`；`text`、`title`、`section` 不 slug 化。

**刻意不做的事**

- 抓取**不爬側邊欄、不解析導覽 DOM、不保留任何 fallback**；沒有可用的 sitemap 就失敗。
- 路徑三元素（`mod_slug`／`chapter`／`page_slug`）只在抓取時計算，下游**不重新推導**。
- 抽取**不判斷噪音、不調整標題層級**。
- 清理**不回頭讀 raw HTML**，不還原段落空行與配方材料。
- 切分**不讀 extracted JSON 或 manifest**，不處理資料品質。
- 中間產物**不保留歷史版本**。

## 6. 跨模塊共通事項

- **路徑慣例**：資料產物一律依 `<version>/<mod_slug>/<chapter>/<page_slug>` 分層；只有一段 URL 的頁歸 `chapter = other`。檔名以 `_` 開頭的是控制檔（manifest、報告），不是資料頁。
- **更新行為**：所有中間產物都是單次記錄、整份覆寫；各模塊可獨立重跑（冪等）。`sources.json` 人工維護；各模塊擁有自己的版本子樹（`raw/<version>/`、`extracted/<version>/`、`extracted_readable/<version>/`、`cleaned/<version>/`），全部處理完且有產出後才清空重建，不留下前次執行的舊檔。
- **不入版控的產物**：`data/` 下的資料產物、`extracted_readable/`、`_fetch_log.txt`、`reports/` 下各模塊產生的報告。
- **模型版本**：模型與 tokenizer 鎖定 revision 並記錄於輸出。
