# AGENTS.md — Project Engineering Contract

| 文件 | 內容 |
| --- | --- |
| `ARCHITECTURE.md` | 架構地圖：模塊、邊界、不變式 |
| `docs/01`～`06_*.md` | 各模塊的契約與決策理由（單一事實來源，本文件只引用） |
| `docs/07_troubleshooting.md` | 疑難排解（只追加） |
| `README.md` | 人類使用說明與開發狀態 |

## 1. Project Mission

- **目的**：依 AE2 官方 Minecraft 1.21.1 指南回答知識問題的 RAG 助手（見 §3.2）；同時是學習成熟 RAG 技術棧的載體，選型不只求最短路徑。
- **包含（MVP）**：抓取、抽取、清理、切分、向量索引、附來源問答、展示介面。
- **不包含**：modpack JAR 解析、KubeJS／CraftTweaker 覆寫解析、多模組、帳號系統、雲端部署、多 Agent。
- **契約範圍**：目前只涵蓋資料準備（抓取到入庫）；檢索、回答與 UI 的契約後續納入，在此之前依 §8，不預先定義細節。
- **不得自行擴張**：新增資料來源類型、modpack 配方查詢、新框架或外部服務、將 CLI 擴充為 API（屬 §16）。

## 2. Rule Priority

1. 使用者當前明確指令；2. 本文件；3. `ARCHITECTURE.md` 與 `docs/`；4. 全域 skill（專案文件未規定時才適用）；5. `README.md`；6. 既有程式碼風格與工程慣例。
使用者指令不得要求本文件禁止的敏感或危險操作，除非針對該操作再次明確授權。

## 3. Core Invariants

以下規則不可因實作方便而放寬。

### 3.1 Data / Knowledge Integrity

- 唯一資料來源：`guide.appliedenergistics.org` 的 AE2 官方 1.21.1 指南；不混用其他版本或非官方資料。
- 版本隨資料全程傳遞（目錄 `<version>/<mod_slug>/<chapter>/` 與 chunk metadata）。
- 每個 chunk（含 parent 與 child）保留 `source_url`、`title`、`page`、`chapter`、`section` 與版本；無來源 URL 的內容不得進入知識庫。
- 缺乏證據時不得猜測或補完。

### 3.2 Product Integrity

- 回答只能依據實際檢索到的 chunks，不得用範圍外的 Minecraft／AE2／其他版本知識補字。
- 每個回答附可點擊來源；不足以確認時回答「目前官方文件不足以確認」。

### 3.3 Reproducibility

- 可重複執行的階段必須冪等（整份覆寫重產生）；中間產物單次記錄、覆蓋更新，不做 history。
- 產物不得依賴不可追蹤的人工狀態；模型鎖定 revision 並記錄於輸出。

## 4. Evidence and Truthfulness

| 類別 | 來源 |
| --- | --- |
| Normative | `AGENTS.md`、`ARCHITECTURE.md`、`docs/` 的契約 |
| Current State | 程式碼、資料產物、Git 狀態、重新執行的檢查 |
| Target State | `ARCHITECTURE.md`、`docs/`；非進度，不得假設已實作 |
| 過程文件（僅線索，須重新驗證） | `reports/`、`.agent-workspace/`、README 專案狀態、根目錄交接或筆記檔 |

無法由實際檔案、程式碼、產物或規範確認的資訊標為 Unknown，不得推測為事實；會影響架構、資料來源或不可逆操作時須詢問使用者。

## 5. Repository Map

模塊與路徑對應見 `ARCHITECTURE.md` §3。

- pipeline 模組與驗證、核對腳本一律放 `src/`，以 `PROJECT_ROOT = Path(__file__).resolve().parent.parent` 定位專案根；`src/` 只放程式與腳本，不放文件；不得在根目錄新增腳本。
- `.agent-workspace/` 是本機溝通區（不入版控、不得當作規範引用，見 §15.1）；`requirements.txt` 是依賴唯一來源（鎖定精確版本）；`infra/` 只放 [7] 的 Docker Compose（不含密碼）。
- 「目標狀態」或「擱置」的模組以實際程式碼為準；檢索（`query.py`）與 UI（`app.py`）不在本契約範圍。

## 6. Pipeline Contract

單向資料流，各階段可獨立重跑；契約見 `docs/`，邊界見 `ARCHITECTURE.md` §4。缺少必要 metadata 的文件不得進入下一階段。

| Stage | 不可破壞的約束 |
| --- | --- |
| [1] 入口 `sources.json` | 入口頁只推導站台根，不抓取；版本取自 `version` 欄位（`docs/01_fetch.md`） |
| [2] 抓取 | URL 真值只有 sitemap.xml，無則 fail-fast；不解析導覽 DOM；路徑三元素只在 [2] 計算（`docs/01_fetch.md`） |
| [3] 抽取 | trafilatura 輸出不異動；`markdown` 只加標題記號；跳轉頁須人工確認並加入 `exclude` 才排除（`docs/02_extract.md`） |
| [4] 清理 | 規則只作用於正文；被排除的頁以報告為憑（`docs/03_clean.md`） |
| [5] 切分 | 只讀 cleaned MD；以 BGE-M3 tokenizer 斷言上限；`source_url` 為空的頁不產出（`docs/04_chunk.md`） |
| [6] Embedding | revision 鎖定，與輸入逐筆對應（`docs/05_embed.md`） |
| [7] 入庫 | schema **擱置**（不得預先定義）；其餘已定（`docs/06_index.md` §2.1） |

## 7. Data Rules

以下為不可放寬的資料規則：

- `title` 與 trafilatura 輸出不異動：`title` 經 cleaned MD frontmatter 原封帶入 chunk，下游不回查 JSON；`recipes` 只來自 HTML 配方區塊的文字屬性，不推測、不補值（`docs/02_extract.md`）。
- 結構性 metadata（`version`／`mod`／`chapter`／`page`）以目錄路徑為準；內容性 metadata（`title`／`source_url`）以 frontmatter 為準。
- slug 只用於路徑與命名；`text`、`title`、`section` 禁止 slug 化。不同版本不得混用。
- Schema 變更屬 pipeline contract 變更：須經使用者授權（§16），下游正式產物整批冪等重產生。

## 8. Technical Constraints

已定決策，不可擅自變更（細節見各 `docs/`）：Python 3.12；torch GPU build 由 cu130 index 安裝（傳遞依賴，不列於 `requirements.txt`）；[2][3] 的函式庫見 `docs/01`、`docs/02`；[4] 自寫規則、只用標準庫；[5] langchain-text-splitters + BGE-M3 tokenizer；[6] `BAAI/bge-m3`（sentence-transformers 本機、dense）；[7] PostgreSQL + pgvector，Docker Compose 環境（規格見 `docs/06_index.md`，密碼只在 `.env`）；LLM：OpenAI；查詢：英文檢索 + 繁中回答（待重新評估）；UI：Streamlit（最後階段）；金鑰只由 `.env` 提供。

- LangChain 只允許 langchain-text-splitters，不引入 agent／chain 編排層；SQLite modpack 配方解析不屬於 MVP。
- 不在上列的 dependency、framework、database、architecture 或外部服務，必須先詢問使用者。

## 9. Security and Sensitive Data

**Never**：讀取或輸出秘密內容（API key、token、password、private key）或要求使用者貼出；將憑證寫入程式碼或文件；提交含敏感資料的檔案；修改或刪除 `.env`；讀取、複製、輸出或提交 `gcm-diagnose.log`。例外：檢查 `.gitignore` 內容，以及用 `git status`／`git ls-files` 確認敏感檔案的版控狀態。

**Sensitive Operations**（須使用者當前明確授權）：
- push、merge、history rewrite、branch deletion。
- 建立遠端 repository（一律 private，使用者明確要求才可 public）。
- 修改 `sources.json`。
- 寫入專案根目錄之外的路徑（含 `~/.codex/skills/`）；例外：Agent 工具暫存與記憶目錄、套件與模型快取目錄（如 `~/.cache/huggingface`），下載仍依 §10 先詢問。
- 刪除既有資料產物或檔案。例外：
  - [2]～[6] 重建自己擁有的版本子樹，範圍限定該版本子樹、有路徑斷言、處理完成且有產出後才清空：[2] `raw/<version>/`；[3] `extracted/<version>/` 與 `extracted_readable/<version>/`（2026-10-24 授權）；[4] `cleaned/<version>/`、[5] `chunks/<version>/`（2026-10-29 授權）；[6] `embeddings/<version>/`（2026-11-05 授權）。
  - [7]（2026-11-07 授權）：可刪除 PostgreSQL rag 兩表中該 version 的資料；模式（`update`／`rebuild`）由使用者確認後明確傳入、單一交易、通過目標資料庫斷言、限該 version，不得 DROP／TRUNCATE（`docs/06_index.md` D5、D5-1）。
  - `.agent-workspace/workers/worker_<目的>/`（2026-11-08 授權）：工作串合併或驗收且整併完成後可刪；路徑須是 `.agent-workspace/workers/` 的直接子目錄、名稱符合 `^worker_[a-z]+(_[a-z]+)*$`、未被 git 追蹤、整併清單已完成（§15.1）。
  - 其他階段如需比照，須另行授權。

## 10. Agent Decision Boundary

**可直接做**：專案內讀取、搜尋；修改任務範圍內的程式碼與文件；重跑 [2]–[5]（[2] 會連網）；重跑 [6]，限模型已在本機快取。

**必須先問**：
- 修改架構、管線契約、目錄結構或 §8 技術決策；新增或升級 dependency。
- 下載模型或大型檔案（說明來源與大小）；修改 `sources.json`；刪除或搬移既有檔案。
- 修改 [4] 清理規則：門檻、白名單的小幅調整須使用者同意並記錄裁定。
- 定義標示「待定」或「擱置」的項目（如 [6] embedding 輸入格式、[7] schema）。
- §9 的 Sensitive Operations；讀取環境變數、系統診斷、硬體狀態等敏感系統資訊。

**絕不**：為「待定」或「擱置」項目虛構細節。

## 11. Task Start Protocol

讀本文件與相關 `ARCHITECTURE.md`／`docs/`／`README.md` → 定位模組 → 判斷最小變更與驗證 → 檢查是否觸及 §9／§10 → 說明預計修改的檔案與原因 → 修改 → 驗證 → 依 §17 回報。

## 12. Change Policy

- 只改任務所需檔案；不做無關重構；未經授權不改架構。
- 重要函式有型別標註；錯誤訊息指出原因；遵循既有風格與繁中註解慣例。

## 13. Validation and Anti-False-Success

- 實際執行驗證，只用實際存在的工具（未設定 pytest、lint、CI 前不得假設存在）。
- 不得宣稱未執行的驗證成功；如實回報失敗；不得降低 assertion、縮小範圍或修改測試標準以製造成功。
- 修改 [2]–[6] 後必須依下表驗證。

| Change | Validation | Acceptance Criteria |
| --- | --- | --- |
| [2]～[6] | `python src/<階段>.py`（`fetch_pages`、`extract_pages`、`clean_pages`、`chunk_pages`、`embed_chunks`） | 對應 `docs/01`～`05` 的「5. 驗證方式」 |
| [7] Index | 待 schema 定義後補入 | 待定 |
| Documentation | 人工核對 | 文內事實（路徑、檔名、規則引用）與實際一致；每個格式只在產出它的模塊文件定義一次；`ARCHITECTURE.md` 模塊地圖與模塊文件一致 |

## 14. Documentation Responsibilities

| 文件 | 只放 | 不放 |
| --- | --- | --- |
| `README.md` | 介紹、安裝與執行、文件導覽；開發期間的專案狀態（完成後移除） | 欄位級契約、決策理由 |
| `ARCHITECTURE.md` | 模塊地圖、邊界原則、不變式（含刻意不做的事）、跨模塊共通事項 | 實作細節、實測數字、進度、Agent 行為禁令 |
| `docs/01`～`06_*.md` | 輸入與輸出（格式只在此定義）、方法、決策理由、否決的方案、驗證方式、待定事項 | 其他模塊的格式（只引用）、進度 |
| `docs/07_troubleshooting.md` | 坑紀錄（現象、根因、處置、證據）與症狀速查，只追加 | 過程敘事 |
| `AGENTS.md` | 行為規則、權限邊界、不變式、驗收標準 | 欄位與參數細節、進度、實測數字 |

- 決策與否決的方案寫在受影響模塊文件；跨模塊決策寫在負責執行的模塊，其他只放連結；不另立決策日誌。
- 契約變更同步更新模塊文件；模塊、資料流或不變式改變同步更新 `ARCHITECTURE.md`；`AGENTS.md` 只在行為規則或不變式變動時更新。

## 15. Handoff Protocol

重要階段完成時，同步更新 `README.md` 專案狀態（其餘文件同步見 §14），並依 §17 回報。

### 15.1 溝通區 `.agent-workspace/`

- **性質**：本機過程文件區，不入版控，不得當作規則引用；衝突時以 `AGENTS.md`、`docs/` 為準。
- **結構**：`BOARD.md`、`SUPERVISOR.md`、`workers/worker_<目的>/` 下的 `TASK.md`、`STATUS.md`、`REPORT.md`、`REVIEW.md`、`evidence/`（指令完整輸出；執行端檔名以 `report_` 開頭，檢查者以 `review_` 開頭）。
- **命名**：資料夾為 `worker_` 加目的（小寫英文與底線，不放數字）；一個名稱一個工作串，計畫、實作、檢查都在同一資料夾；同一時間每個角色只有一個存活對話。
- **單一寫入者**：`BOARD.md`、`SUPERVISOR.md`、`TASK.md` 由監督者寫；`STATUS.md`、`REPORT.md` 由執行端寫；`REVIEW.md` 由檢查者寫；每個檔案只有一方可寫。
- **有效性**：`TASK.md`、`STATUS.md`、`REPORT.md`、`REVIEW.md` 開頭有 `task_id`、`round`、`base_commit`；與 `TASK.md` 不符即舊資料。`REPORT.md` 另記完成 commit；`REVIEW.md` 另記 `checked_commit`，結果只對該 commit 有效。
- **內容限制**：不得出現密碼、完整連線 URL 或 `.env` 的內容。
- **寫入鎖**：修改 repo 的任務（`modify-repo`）同一時間只能有一個，由 `BOARD.md` 標明；唯讀任務可平行。
- **淘汰**：工作串合併或驗收後，先完成整併清單（決策進 `docs/`、值得保留的數字與證據進對應文件、規則與教訓進 `AGENTS.md`），全部有去處才可刪除該目錄並從 `BOARD.md` 移除；由執行端或使用者刪除，監督者不刪除。

## 16. Architecture Change Protocol

下列屬 framework-level decision，Agent 不得自行決定：更換主要 framework、資料庫、LLM provider、embedding 策略或模型；修改 pipeline 邊界或階段職責、資料來源策略；引入新 agent framework；大型目錄重構；新增或刪除 [4] 清理規則、改變處理順序（須人工裁定並更新 `docs/03_clean.md`）；定義 [7] schema。

採 **Grill-me mode**：說明問題 → 提供 2–3 個方案 → 說明各方案成本與風險 → 明確推薦 → 等待使用者決策後才實作。

## 17. Completion Report

完成任務後回報至少包含：**Changed**（實際修改的檔案）、**Validation**（實際執行的驗證與結果）、**Not Verified**（未執行的驗證）、**Risks**（仍存在的問題）、**Decisions Needed**（需使用者決定的事項）。
