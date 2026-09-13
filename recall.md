# recall.md — 專案狀態與已確認決策

> 本檔記錄目前狀態、已確認決策、完成內容與後續事項；完成工作後由 AI 追加更新。

## 目前狀態（截至 2026-09-13，第二次更新）

- 專案根目錄：本機專案根目錄（不記錄絕對路徑）。
- 已連結遠端 `origin`（GitHub：Star-Meow/Minecraft_RAG），`main` 與 `origin/main` 同步（2026-09-13 push，遠端原為空 repo）。
- 核心文件：`README.md`（人類導向架構說明）、`AGENTS.md`（永久工程契約，18 節）、`REVIEW.md`（一次性稽核快照，由 project_audit.md 改名）、`recall.md`（本檔）；`analysis-summary.md` 已由使用者自工作目錄刪除（版控仍追蹤，git 狀態 D，是否 `git rm --cached` 待決）。
- 已實作：`fetch_pages.py`、`chunk_pages.py`、`sources.json`（6 頁）、`data/raw/` 與 `data/processed/`（各 6 頁）、`data/chunks.jsonl`（36 chunks）、`requirements.txt`（requests、beautifulsoup4）。
- Skill：`skills/`（Codex 版：project-limit、dev-environment）、`.agents/skills/`（ZCode 版：共 5 個）。
- 尚未建立：`index_chunks.py`、`query.py`、`app.py`、`tests/`、`.env.example`。

## 本次完成內容（2026-09-13，第五次更新）

- 使用者已將 `project_audit.md` 改名為 `REVIEW.md`，並重新定位：一次性的完整專案遍歷審查快照——不是永久規範、不是持續監控文件，一般任務不閱讀也不更新。
- `AGENTS.md` 最小修正（7 處 Edit，規則實質意義、技術決策、pipeline contract、RAG invariants 皆未變）：
  1. 全文 `project_audit.md` → `REVIEW.md`（前言、§4、§5、§11、§14、§15）。
  2. §4 重構為四類資訊來源：Normative（AGENTS + skills）／Current State（程式碼、產物、Git）／Historical Snapshot（REVIEW.md，與實際不一致時以重新檢查後的實際狀態為準）／Progress & Decisions（recall.md）／人類文件／Unknown 規則。
  3. §5 Repository Map 與 §6 Pipeline Contract 標示 Fetch／Chunk 為已實作、Index／Query／App 為預定階段（僅契約層，實作狀態由 recall.md 管理）。
  4. §11 Task Start Protocol 改為一般任務九步流程＋五項完整遍歷觸發條件（一般任務不遍歷 repo、不更新 REVIEW.md）。
- 逐項核對後**刻意未改**：Data Contract（metadata 六欄、chunk schema）、RAG invariants、Security（gcm-diagnose.log、push/merge 授權）、Change Policy、Grill-me、Validation Anti-False-Success（不假設 pytest/lint/CI）。
- 手動核對：`index_chunks.py`／`query.py`／`app.py` 確實不存在；README 與 recall 與實況一致。

## 前次完成內容（2026-09-13，第四次更新）

- 依使用者要求對 `AGENTS.md` 做最小必要優化（規則實質意義、技術決策、管線契約、知識來源限制皆未改變）：
  - 新增「Critical Product / RAG Invariants」：六條產品正確性規則集中單一定義（原分散於管線契約與技術決策）。
  - 新增「Repository Map」：各檔案／目錄職責導向，不含進度資訊。
  - 新增「Task Start Protocol」：八步任務啟動流程（讀契約 → 依任務讀 recall/README → 定位模組 → 定修改範圍與驗證 → 檢查決策邊界 → 操作前簡述 → 驗證回報）。
  - 管線契約表移除「未實作」標記，改以表格註記「失敗條件於實作時補入；實作狀態由 recall.md 管理」。
  - 驗證節新增 Anti-False-Success 原則（未執行不得宣稱通過、失敗如實回報、不得降低標準），並整理為「修改項目｜驗證指令｜Acceptance Criteria」表格。
  - 文件分節重組為：使命與範圍 → 規則優先級 → 不變量 → Repository Map → 管線契約 → 技術決策 → 決策邊界 → Task Start Protocol → 修改與驗證 → 文件維護責任。

## 前次完成內容（2026-09-13，第三次更新）

- 依使用者要求將 `AGENTS.md` 重構為精簡、可執行、低歧義的工程契約（規模縮減、僅寫永久規範）：
  - 新增「規則優先級」（使用者當前指令 > 本檔 > skill 行為規範 > README/程式碼風格 > 一般習慣），並明確「不得擅自」的定義。
  - 規範與現況分離：頁數、chunk 數、Phase 進度、commit 狀態自 AGENTS.md 移出，僅存於 recall.md 與 README.md。
  - 以契約表定義管線各階段的輸入／輸出／失敗條件，保留兩個核心不變量（無完整 metadata 不得進入 chunks；各階段可獨立重跑、輸出冪等）。
  - 集中 Agent 決策邊界為三類：可直接執行／必須先詢問／禁止執行，並保留 .gitignore 與版控狀態檢查的例外。
  - 統一敏感資料原則（gcm-diagnose.log 不得讀取/複製/輸出/提交；任何 key/token/密碼不得讀取輸出）。
  - 新增各階段最小必要驗證條件（fetch/chunk/index/query/純文件），明確專案無 pytest、lint、CI，不得假設其存在。
  - 明確文件責任：recall.md 是狀態與決策摘要、不承載永久規範；架構或重大技術決策變更時 README.md 必須同步更新。
- 依使用者指示：本專案與 LangChain 無關，AGENTS.md 與本檔決策紀錄已移除相關表述，技術方向不變（原生 Python 3.9 管線）。
- 驗證：grep 確認 AGENTS.md 無 LangChain 表述、無現況數字（頁數/chunk 數/commit 數），六個章節結構完整。

## 前次完成內容（2026-09-13，第二次更新）

- 核查 git 紀錄（5 個 commit）與檔案實況後，完成專案進度總結。
- 重寫 `README.md` 為人類導向的專案架構說明（目的、架構、模組職責、關係、使用資訊、里程碑）；依使用者要求補回「目錄結構」章節（依目前實際狀態更新，含未建立檔案標註）。
- 建立 `AGENTS.md` 作為 AI Agent 從頭閱讀專案的架構基準：詳細記錄各模組基準（sources.json、fetch、chunk 的規範值與實作常數對照、index/query/app 預定基準）、回答品質與 RAG 規範、重要決策、已知問題、協作規範與里程碑。
- 發現並記錄：`recall.md` 已列入 `.gitignore` 但仍為被追蹤檔案（gitignore 對已追蹤檔無效）；移出版控需 `git rm --cached`，待使用者決定。
- 確立規則：每次更新完成後將更新總結寫入 `recall.md`；AGENTS.md 為 AI 閱讀專案的架構基準。

## 更早完成內容（2026-09-13，第一次更新）

- 閱讀專案全部文件，產出 `analysis-summary.md` 總結分析（進度：Phase 1 完成、Phase 2 一半）。
- 將全域 Codex skills 轉換為 ZCode harness 可讀取的副本，置於 `.agents/skills/`，共 5 個。
- 兩個 commit（`83bc330`、`b865eb9`）並 push 至 `origin/main`。
- 追加 skill 規則：專案內 `cd` 允許；框架問題採 grill-me 模式提問；重大框架異動更新 README；新建 repo 一律 private；檔案操作前概略說明。

## 已確認決策

- 專案名稱：Minecraft AE2 RAG Assistant。
- 目標：針對 Minecraft 1.21.1 與 Applied Energistics 2（AE2）的知識問答 RAG 助手。
- 第一版只以 AE2 官方 1.21.1 線上指南為資料來源，不宣稱能查核特定模組包的客製配方。
- 初期僅處理人工指定的 15～20 個官方頁面，不進行全站自動爬取。
- 技術棧：Python、requests + BeautifulSoup、Markdown + YAML、Chroma、OpenAI Embeddings／LLM、Streamlit（原生 Python 3.9 管線；2026-09-13 依使用者指示，本專案與 LangChain 無關，技術文件已移除相關表述，技術方向不變）。
- 文件與 chunk 規範：
  - 每份 Markdown 需 YAML metadata：`title`、`source_url`、`minecraft_version`、`mod`、`source_type`、`fetched_at`。
  - 固定 `minecraft_version: "1.21.1"`、`mod: "Applied Energistics 2"`。
  - 以 Markdown 標題優先切分；chunk 約 500～700 tokens、重疊約 80～120 tokens。
  - 每個 chunk 保留頁面 URL、頁名、章節標題與版本資訊；無來源 URL 的文字不得納入正式知識庫。
- 回答品質規範：LLM 只能依檢索到的 chunk 作答；答案需附可點擊來源；資料不足時回「目前官方文件不足以確認」；不可混用非 1.21.1 文件；先檢視檢索品質再調整 chunking。
- Git workflow（2026-09-13 確認）：
  - ZCode harness 的 skill 副本置於 `.agents/skills/`；全域 `~/.codex/skills/` 暫不同步，需使用者明確同意才寫入。
  - 快照／整理類性質的 commit 可直接在 `main`；功能開發依 git-auto-branch 使用任務 branch。
  - push `main` 需使用者明確指示；merge 一律保留給使用者決定。
  - 新建遠端 repo 一律 private。
- 行為規範（2026-09-13 確認）：專案目錄內讀取與查詢一律允許；檔案操作前先概略說明；框架層級決策採 grill-me 提問模式。
- 文件分工（2026-09-13 第二次更新確認）：
  - `README.md` 服務人類讀者（架構與使用說明）。
  - `AGENTS.md` 服務 AI Agent，作為從頭閱讀專案的架構基準，記錄各模組詳細基準。
  - **每次更新完成後，將更新總結寫入 `recall.md`。**

## 下一步

1. 強化 `fetch_pages.py` 清理邏輯（移除官網特殊標記 `$!/$`、導覽殘留、標題黏行），重跑 fetch + chunk。
2. 實作 `index_chunks.py`（OpenAI Embeddings + 本機 Chroma），建立 `.env` / `.env.example` 並在 README 說明新依賴。
3. 實作 `query.py`，以 README 的 5 個驗收問題驗證 Top 3 檢索。
4. 輪換 `gcm-diagnose.log` 中外洩的 API key（檔案已排除版控，key 本身仍建議撤換）。
5. 決定 `recall.md` 是否以 `git rm --cached` 移出版控。

## 注意事項

- 不將 API Key、帳密、個人資料、私人絕對路徑或其他敏感資訊寫入任何檔案。
- 若要改變既有決策，需先說明影響與理由，經確認後再更新本文件。
