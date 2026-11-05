# 交接：架構討論與選型現況（2026-11-05）

> **性質**：過程文件，**非規範**（`AGENTS.md` §4）。規則以 `AGENTS.md` 為準，各模塊契約以 `docs/01`～`06` 為準；本文件只負責讓下一個 Agent 快速接手。引用其中任何數字前，請以實際檔案或重跑結果驗證。
> **分支**：`docs/restructure`（最新 commit `6937c94`，**尚未 push**；push 需使用者明確授權）。

---

## 1. 先讀這些

| 順序 | 文件 | 用途 |
| --- | --- | --- |
| 1 | `AGENTS.md` | 行為邊界、權限、驗收標準（§9 安全、§10 決策邊界、§13 驗收、§16 grill-me） |
| 2 | `ARCHITECTURE.md` | 架構地圖、邊界原則、不變式 |
| 3 | `docs/04_chunk.md`、`docs/05_embed.md` | 剛完成的 [5] 與下一步 [6] |
| 4 | `docs/07_troubleshooting.md` | T1–T9 坑紀錄（Windows 編碼、CRLF、站台改版、trafilatura 黏行） |

## 2. 與使用者合作的方式（重要）

- **grill-me**：凡是架構、契約、規則、待定項目，先「問題 → 2–3 方案 → 成本與風險 → 推薦 → 等決定」，**不得擅自決定後執行**。
- **使用者要求被反駁**：認為使用者想法有誤時要明說並給理由。
- 以**業界常見做法**為基準（本專案也是學習 RAG 技術棧的載體），但不過度解耦。
- **資料品質優先**。
- 回覆使用繁體中文；commit 只在使用者要求時做，訊息格式 `type(scope): 繁中摘要` + 條列。
- 使用者若說「未列出則採用推薦選項」，代表只回覆有異議的項目；交接時把替使用者採用的推薦項明確列出供確認。

## 3. 管線現況

| 模塊 | 程式 | 狀態 | 最近一次結果 |
| --- | --- | --- | --- |
| [1] 來源設定 | `sources.json` | 完成 | `exclude` 含 2 個已確認的跳轉頁 |
| [2] 抓取 | `src/fetch_pages.py` | 完成 | 124 頁，失敗 0 |
| [3] 抽取 | `src/extract_pages.py` | 完成 | 119 頁輸出、5 頁跳過；配方 246 個 |
| [4] 清理 | `src/clean_pages.py` | 完成 | 119 + 0 = 119 |
| [5] 切分 | `src/chunk_pages.py` | **完成（2026-10-29）** | parent 387、child 466；驗收全過、冪等 |
| [6] 向量化 | `src/embed_chunks.py` | **未實作（下一步）** | — |
| [7] 入庫 | `src/index_chunks.py` | **擱置** | schema 不得預先定義 |
| 檢索／回答／UI | — | 範圍外（契約後續再納入） | — |

執行環境：一律用 `.venv/Scripts/python.exe`，並設 `PYTHONIOENCODING=utf-8`（T5）。

## 4. 已定的架構與選型（依模塊）

細節與理由都在對應模塊文件；這裡只列結論。

**共通**
- 模塊邊界：設定（`sources.json`、模型 revision、切分參數）可共用；資料產物依契約讀上游；格式只在產出它的模塊定義一次。
- 每個模塊擁有並重建自己的版本子樹（處理完、有產出才清空，有路徑斷言）：[2] `raw/<version>/`、[3] `extracted/<version>/` + `extracted_readable/<version>/`、[4] `cleaned/<version>/`、[5] `chunks/<version>/`。**[6] 尚未取得此授權。**
- 文件體系：`ARCHITECTURE.md` 是精簡地圖；`docs/01`～`06` 模塊文件（含「為什麼」與「否決的方案」，不另設 ADR）；`docs/07` 只追加；`README.md` 暫存專案狀態直到專案完成。
- 依賴：`requirements.txt` 為唯一來源、精確鎖版；`pyproject.toml` 已刪除。

**[2] 抓取**：URL 真值只來自 sitemap.xml（現為 sitemap index），無則 fail-fast；網址保留結尾 `/`；有失敗頁時 exit 1。

**[3] 抽取（方案 ④）**：trafilatura 為主；BS4 只整理輸入（只取 `#page-content`、3D 場景說明轉清單、刪提示框模板／配方區塊／圖片、連結轉純文字）；第二次抽取 `MIN_EXTRACTED_SIZE=1`。配方由 HTML `aria-description` 解析成 `recipes`。跳轉頁以結構判定、只列清單，人工確認後加入 `sources.json` 的 `exclude`。

**[4] 清理**：規則順序 R2（只警告）→ R1 → R4a → R4b → R5 → R6 → R7 → R8 → 空 body 守衛。R4b、R5 目前命中 0，保留作保險。R8 輸出 `## Recipes`，每行 `- {label} [{station}]: {材料} → {產物}`。

**[5] 切分（本輪完成，2026-10-29 決策）**

| 項目 | 決定 |
| --- | --- |
| 架構 | 子母分層：child 檢索、parent 交 LLM（docstore 模式） |
| 上限 | parent ≤ 2048、child ≤ 256（BGE-M3 tokenizer，`add_special_tokens=False`，**含標題行**） |
| parent 切法 | `MarkdownHeaderTextSplitter` 依 `#`／`##`，`strip_headers=False`；`###` 併入所屬 `##` |
| 開頭段落 | 獨立成 parent，`section` = 頁面 `title` |
| 短 parent | 不合併（115 個 < 50 tokens，列於報告） |
| child 切法 | `RecursiveCharacterTextSplitter`，overlap 32，切分點 `\n`→`. `→` `→`""`，`keep_separator="end"` |
| child `section` | parent 路徑 + child 起點所在的 `###` |
| 超限 | 中止、不寫產出、exit 1（不自動再切；使用者表示先不考慮未來超限） |
| ID | `<version>:<mod>:<chapter>:<page>:pNN`、`…:pNN:cNN` |
| 產物 | `chunks/<version>/parents.jsonl`、`children.jsonl`、`reports/chunking_report.md` |
| 空白處理 | splitter 去行首空白、以 `"  \n"` 接段落 → 照工具原樣保留（2026-10-30 裁定） |
| tokenizer | `BAAI/bge-m3` @ `5617a9f61b028005a4858fdac845db406aefb181`；`transformers==5.17.0` 已鎖版 |

**[6] 已定部分**：`BAAI/bge-m3`、sentence-transformers 本機、dense only、1024 維、`normalize_embeddings=True`、revision 鎖定並寫入輸出；sparse／ColBERT 不採用（需 `FlagEmbedding`）。

**[7]**：PostgreSQL + pgvector；docstore 模式（child 向量入向量庫，parent 由 `parent_id` 取回）；其餘全部擱置。

## 5. 選型歷程（決策時間線）

| 日期 | 決策 |
| --- | --- |
| 2026-10-22 | embedding 由 MiniLM 改為 BGE-M3；切分改為子母分層；[3] 產生 `markdown`（標題記號）、[4] 新增 R6 層級正規化 |
| 2026-10-23 | 文件重整（模塊文件取代 ADR）；站台改為靜態 HTML，配合結尾 `/`；跳轉頁改以結構判定＋`exclude`；上限先定 1024／256 |
| 2026-10-24 | 配方轉文字（R8）；parent 上限改 2048；R5；各階段擁有並重建版本子樹；抽取方案 ④（BS4 整理輸入） |
| 2026-10-29 | [5] D1–D8 定案並實作；[5] 取得重建 `chunks/<version>/` 授權 |
| 2026-10-30 | splitter 空白處理照原樣保留；`transformers` 鎖版 |
| — | Q3 格式飄移偵測：使用者決定**先不做管控**（見 §7） |

## 6. 下一步：[6] 向量化的待決事項（需 grill-me）

| # | 事項 | 現況／建議 |
| --- | --- | --- |
| E1 | **模型下載** | 本機 HF 快取**只有 tokenizer 與 config，沒有權重**；需下載約 2.3 GB，**必須先徵得同意**（`AGENTS.md` §10） |
| E2 | embedding 輸入格式 | `docs/05_embed.md` 待定。舊格式為 slug 前綴 `{mod} \| {page} \| {section}`；建議改用原始 `title`／`section` 路徑。**注意**：child 的 `text` 已含標題行（每章第一個 child 以 `## …` 開頭），前綴可能與正文重複，需在方案中說明取捨 |
| E3 | 鎖定的 model revision | 建議與 tokenizer 相同：`5617a9f61b028005a4858fdac845db406aefb181` |
| E4 | 輸出檔名與欄位 | 文件寫「待定」；可比照 [5]：`embeddings/<version>/` 下 JSONL（child 欄位 + 向量 + `model_name`／`model_revision`）。屬 [6] 自己的輸出契約，非 [7] schema |
| E5 | [6] 是否擁有並重建 `embeddings/<version>/` | 需使用者**另行授權**（`AGENTS.md` §9） |
| E6 | 批次大小、GPU／CPU | 實作細節；torch 為 cu130 build（不列於 `requirements.txt`） |
| E7 | 驗收 | 已定於 `AGENTS.md` §13：每筆 1024 維、norm = 1、`model_revision` 非空、與 `children.jsonl` 逐筆對應 |

建議流程：E1–E5 grill-me 定案 → 更新 `docs/05_embed.md` 與 `AGENTS.md`（若有授權）→ 實作 → 依 §13 驗收（含冪等）→ 更新 README 狀態。

## 7. 延後或範圍外的議題

- **Q3 格式飄移偵測**：已列出各階段訊號，2026-10-24 全面檢查無問題。使用者決定先不做自動管控（曾傾向「只警告、不中止」）。仍需留意：
  - 導覽判定的連結密度：非索引頁最高 0.45（`quartz_block`），門檻 0.5，餘裕小。
  - 清理報告「疑似新標籤」10 行（如 `Crafting Terminal`、`8 matter balls around a dye`）：粗看為正文，未逐頁確認；現行規則保留。
- **檢索端**（範圍外）：命中 child 後依 `parent_id` 去重取 parent；top-k 需考慮同 parent 的 child 佔滿；BGE-M3 多語言，「英文檢索 + 繁中回答」可重新評估。
- **配方限制**：`cycling` 材料只取第一個、無產物數量、無擺放形狀（`docs/02_extract.md` §6）。
- **`include` 欄位**：保留未啟用（`docs/01_fetch.md` §6）。

## 8. 已知風險與待修

| 項目 | 說明 |
| --- | --- |
| 短 parent 多 | 115 個 < 50 tokens，交給 LLM 的上下文可能偏短；未經檢索評估 |
| 上限與 overlap 未經評估 | 依資料分布與業界常見值決定，需 [6]／[7] 後以實際問題評估 |
| 驗收腳本不在 repo | [5] 驗收用的檢查腳本在當時的 scratchpad，已不可用；檢查項目見 `docs/04_chunk.md` §5，需要時重寫 |
| 乾淨環境未測 | 全新安裝與首次下載 tokenizer 的流程未驗證 |
| 分支未 push | `docs/restructure` 只在本機 |

## 9. 環境與操作提醒

- Windows + Git Bash：Python heredoc 容易弄壞 `\n` 與反斜線，改寫成檔案再執行；`/tmp` 與 Windows Python 路徑不同，用 scratchpad。
- Git 會出現 LF→CRLF 警告（T6），不影響內容。
- 離線載入 tokenizer：`HF_HUB_OFFLINE=1`。
- **安全**：不讀、不輸出 `.env` 與 `gcm-diagnose.log`；不修改 `.env`；修改 `sources.json`、刪除檔案、下載模型、push／merge 都需使用者當下明確授權。
