# Project Audit — Minecraft_RAG

## 1. Audit Metadata

- **Audit date**: 2026-09-13
- **Auditor**: AI Agent（ZCode / GLM），以「Senior Software Engineer + PM」任務框架執行
- **方法**: 唯讀遍歷——`find` 全檔案清點、`git status` / `git ls-files`（唯讀）、`grep`、Python 腳本解析資料產物、逐行閱讀全部 Python 原始碼。**未執行 pipeline**（避免覆寫資料產物）。
- **證據優先序**: 程式碼／實際檔案 > 資料產物 > 文件 > 假設。不確定之事標記 Unknown，不猜測。
- **本階段修改範圍**: 僅新建本檔。未修改 AGENTS.md / README.md / recall.md / sources.json / requirements.txt / 程式碼 / 任何資料產物。
- **敏感邊界**: 未讀取 `gcm-diagnose.log` 內容、未讀取任何 API key / token / password、無 `.env` 檔存在。
- **已檢視證據**: `fetch_pages.py`（442 行，全文）、`chunk_pages.py`（252 行，全文）、`data/chunks.jsonl`（36 行全部解析驗證）、6 份 processed Markdown（frontmatter 全驗證；getting-started.md 全文樣本）、`sources.json`、`requirements.txt`、`.gitignore`、`README.md`、`AGENTS.md`、`recall.md`、`read.md`、7 個 SKILL.md、git 追蹤狀態。**未檢視**: raw HTML 內部結構（僅大小與 blockquote 存在性 grep）、`gcm-diagnose.log`（禁讀）。

## 2. Project Overview

| 項目 | 內容 | 依據 |
| --- | --- | --- |
| 專案名稱 | Minecraft AE2 RAG Assistant | README / AGENTS / recall 一致 |
| 專案目的 | 依據 AE2 官方 Minecraft 1.21.1 指南回答知識問題的 RAG 助手，答案附可點擊來源；文件不足時回答「目前官方文件不足以確認」 | 三份文件一致 |
| 知識來源 | `guide.appliedenergistics.org` 1.21.1 官方指南，人工指定頁面（規劃 15～20 頁） | sources.json + 文件 |
| RAG 核心用途 | 官方指南 → Markdown → chunks → 向量檢索 → LLM 僅依檢索內容作答 | AGENTS.md 契約 |
| 預期輸出 | 附來源 URL 的回答 | README / AGENTS |
| UI 形式 | 規劃 Streamlit（最後階段）；**目前僅 CLI 腳本，無任何 UI/API** | 文件規劃 + 實況 |
| MVP 邊界 | 不含：modpack JAR 解析、KubeJS/CraftTweaker、多模組、帳號、雲端、多 Agent、SQLite 配方解析（非 MVP） | README / AGENTS |
| 終端使用者 | **文件未明確定義**（由使命推斷為 Minecraft/AE2 玩家，屬推斷非明載） | Unknown |

**文件間一致性**：三份主要文件（README / AGENTS / recall）於 2026-09-13 已同步重寫或更新，現今相互一致；歷史不一致（README 第 5 節過時、recall 狀態過期）已於當日解決並記錄於 recall.md。本审计另發現下述 §12 的 discrepancies。

## 3. Repository Structure

實際檔案清點（`find` + `git ls-files` 交叉驗證；── 標記版控狀態）：

```text
Minecraft_RAG/
├── .agents/skills/                  # tracked；5 個 ZCode skill（git-init-repo、project-limit 有未提交修改）
│   ├── dev-environment/SKILL.md
│   ├── git-auto-branch/SKILL.md
│   ├── git-auto-commit/SKILL.md
│   ├── git-init-repo/SKILL.md
│   └── project-limit/SKILL.md
├── .codex/local.ps1                 # ignored（Codex CLI + 本地 llama.cpp 啟動器）
├── .gitignore                       # tracked：__pycache__/ *.pyc .env .env.* .codex/ read.md recall.md gcm-diagnose.log
├── AGENTS.md                        # untracked（已建立、未 commit）
├── README.md                        # tracked；工作目錄有未提交修改（2026-09-13 重寫）
├── __pycache__/                     # ignored、未追蹤（2 個 .pyc，Python 3.9 產物）
├── analysis-summary.md              # tracked，但工作目錄中「已刪除」（git status: D）← 見 §12/§15
├── chunk_pages.py                   # tracked（252 行）
├── fetch_pages.py                   # tracked（442 行）
├── gcm-diagnose.log                 # ignored、untracked；含外洩 API key（先前確認；本階段未讀）
├── project-limit-skill-summary.txt  # tracked（skill 建置紀錄）
├── read.md                          # ignored（歷史需求文件：git skills 規格）
├── recall.md                        # .gitignore 有列，但「仍被追蹤」← 見 §12
├── requirements.txt                 # tracked（2 條依賴）
├── skills/                          # tracked；Codex 版 skill
│   ├── dev-environment/SKILL.md + agents/openai.yaml
│   └── project-limit/SKILL.md + agents/openai.yaml
├── sources.json                     # tracked（6 個來源）
└── data/                            # tracked（資料產物入版控）
    ├── chunks.jsonl                 # 107,541 bytes、36 行
    ├── processed/guide.appliedenergistics.org/*.md   # 6 檔（1,983–13,287 bytes）
    └── raw/guide.appliedenergistics.org/*.html       # 6 檔（43,314–91,955 bytes）
```

不存在於 repository 的東西（已確認，非推測）：`index_chunks.py`、`query.py`、`app.py`、`tests/`、`notebooks/`、`scripts/`、`.env`、任何 `.db`、CI 設定、`AGENTS.md` 以外的 schema 文件。

## 4. Module Inventory

### fetch_pages.py（442 行，tracked，已實作）

- **Entry point**: `main()` → `run_fetcher()`；`if __name__ == "__main__"` 可執行。
- **函式**：`load_sources`（讀 sources.json，驗證非空清單）、`is_allowed_url`（scheme 限 http/https 且 netloc 必須等於 `guide.appliedenergistics.org`）、`fetch_page`（requests，自訂 User-Agent，timeout 25s，`apparent_encoding` 偵測編碼）、`save_raw`（覆寫式寫 `data/raw/<host>/<slug>.html`）、`find_main_content`（候選節點文字量評分制取主文）、`resolve_title`（來源 title > `<title>` > 空）、`make_metadata` / `render_yaml` / `write_processed`（覆寫式寫 `data/processed/<host>/<slug>.md`）、`to_markdown` + `render` 家族（自寫 HTML→Markdown：headings/p/list/pre/blockquote/table/hr/inline）。
- **錯誤處理**：單頁 try/except，下載失敗與解析失敗分別包裝為 RuntimeError；結束時統計成功/失敗/略過；**exit code：有任一失敗 = 1，全成功 = 0**。
- **覆寫行為**：同 URL 永遠覆寫同路徑（冪等）；`fetched_at` 每次執行更新。
- **已證實缺陷**：`render_block` 的 blockquote 分支（第 248 行）呼叫 `render_children(node)`——**此函式從未定義**（僅有未被任何地方呼叫的 `render_children_html`）。任何含 `<blockquote>` 的頁面將觸發 NameError → 該頁「解析失敗」。目前 6 頁 raw HTML 經 grep 均無 blockquote，故尚未觸發。`render_children_html` 為 dead code。

### chunk_pages.py（252 行，tracked，已實作）

- **Entry point**: `main()`；`argparse` 已 import 且建立 parser 但**未定義任何參數**（`parse_args()` 結果未使用）。
- **函式**：`parse_frontmatter`（regex 解析雙引號 YAML 子集，缺 6 個必填欄位任一 → ValueError）、`load_processed_files`（讀取排序後所有 processed md；缺 `source_url` → ValueError）、`split_sections`（以 `^#{1,6}` heading 分節）、`normalize_content`（移除圖片語法、壓平空白）、`estimate_tokens`（`len/4` 字元近似）、`split_long_text`（段落裝箱 + 重疊；長段落先按 `. ` 句界預切）、`make_chunks`、`run_chunker`。
- **錯誤處理**：任一檔案 frontmatter 不合法 → 整個 chunking run 中止（單一錯誤訊息，exit 1），不產生部分輸出（輸出檔在全部解析成功後才開啟）。**exit code：成功 0 / 失敗 1**。
- **覆寫行為**：`chunks.jsonl` 整份覆寫重產生（冪等）；`chunk_id` 為全域流水號（%04d），重跑會重新編號。
- **已證實缺陷**：見 §7 token 分布與重複 chunk（`split_long_text` 的 overlap/flush 邏輯產出超標 chunk 與完全重複內容）。

### index_chunks.py / query.py / app.py / tests/

**Not present**（find 全樹確認，無任何形式的實作、草稿或設定殘留）。不做推測。

## 5. Actual Architecture

以實際程式碼與產物為準（實線 = 已存在且可執行；括號 = 契約上有、實際不存在）：

```text
sources.json（6 頁，人工維護）
     │  讀取＋網域白名單過濾
     ▼
fetch_pages.py ──單頁失敗不阻斷──▶ 統計成功/失敗/略過（exit 0/1）
     │
     ├──▶ data/raw/guide.appliedenergistics.org/*.html        （6 檔，存在）
     └──▶ data/processed/guide.appliedenergistics.org/*.md    （6 檔，YAML frontmatter）
               │  frontmatter 驗證（缺欄位→整個 run 中止）
               ▼
        chunk_pages.py（heading 分節〔實際上失效，見 §7〕→ 段落裝箱＋重疊 → min-filter）
               │
               ▼
        data/chunks.jsonl（36 chunks，10 欄 schema）
               │
               ▼
        (index_chunks.py ──▶ Chroma)        ← Not present
               │
               ▼
        (query.py ──▶ LLM 附來源回答)        ← Not present
               │
               ▼
        (app.py ──▶ Streamlit)              ← Not present
```

## 6. Actual Pipeline

| Stage | Actual Input | Actual Output | Main Logic | Current State |
| --- | --- | --- | --- | --- |
| fetch | `sources.json`（6 筆） | `data/raw/<host>/<slug>.html`（6）、`data/processed/<host>/<slug>.md`（6，含 frontmatter） | 白名單 → requests 下載 → BS4 解析 → 評分取主文 → 移除 nav/footer 等 → 自寫 render → frontmatter 寫入 | Implemented；產物 2026-08-26 產生並入版控 |
| process（HTML→MD） | raw HTML | processed Markdown | 與 fetch 同一腳本內（非獨立階段） | Implemented |
| chunk | `data/processed/*.md` | `data/chunks.jsonl`（36 行） | frontmatter 驗證 → heading 分節（實際 0 命中）→ 圖片移除 → 段落裝箱（600 token 目標/100 重疊/40 下限，字元近似） | Implemented；輸出有品質缺陷（§7） |
| index | 契約：`chunks.jsonl` | 契約：本機 Chroma | 未定義 | **Not implemented / not present** |
| query | 契約：使用者問題 + Chroma | 契約：附來源回答 | 未定義 | **Not implemented / not present** |
| app | 契約：— | 契約：Streamlit 介面 | 未定義 | **Not implemented / not present** |

## 7. Data Schema

### Processed Markdown frontmatter（6 檔全數驗證）

- 欄位（6，順序固定）：`title`、`source_url`、`minecraft_version`、`mod`、`source_type`、`fetched_at`。
- **所有值皆為雙引號字串**（無數字/布林/巢狀型別）；`minecraft_version` 全為 `"1.21.1"`；`mod` 全為 `"Applied Energistics 2"`；`source_type` 全為 `"official_guide"`；`fetched_at` 為含時區 ISO 8601（2026-08-26T01:33:06+08:00）。
- 解析器為 regex 的受限 YAML 子集（非 PyYAML）——與「YAML metadata」名義相容，屬 implementation detail。

### chunks.jsonl（36 行全數驗證）

- **JSON Lines**；0 行解析失敗；**所有 36 行同一 schema（10 欄）**：

| 欄位 | 範例/格式 | 分類 |
| --- | --- | --- |
| `chunk_id` | `"0001"`（全域流水號 %04d） | implementation detail——重跑重新編號，不宜作長期識別 |
| `source_url` | 官方指南 URL；6 個唯一值、0 個空值 | **pipeline contract** |
| `page_title` | `"Applied Energistics 2 Guide - Autocrafting"` | contract |
| `section_title` | `"Introduction（1/14）"` 等 | **contract 欄位存在但實際失去意義**（見下） |
| `minecraft_version` / `mod` / `source_type` | 固定值繼承自 frontmatter | contract |
| `fetched_at` | chunk 執行時間（2026-08-26T21:11:53+08:00） | implementation detail——**與 processed 檔的 fetched_at（頁面抓取時間）語義不同** |
| `estimated_tokens` | 139–1184 | implementation detail（字元近似） |
| `content` | 純文字（圖片語法已移除） | contract |

### 實測發現（證據）

1. **heading 分節實際失效**：6 份 processed Markdown 的 `^#` 標題行數全為 **0**（官網標題未被轉為 Markdown heading，而是併入內文行）。因此 36 個 chunk 的 `section_title` 全部是 `Introduction`（或 `Introduction（n/m）`）——**章節溯源資訊實質喪失**，違反「每個 chunk 保留章節標題」的規範精神（欄位在、內容無效）。
2. **token 分布違反切分基準**：規範目標 500–700 tokens（字元近似）；實測 <500 有 9 個、500–700 有 16 個、**>700 有 11 個（最大 1184，約為目標 2 倍）**。成因在 `split_long_text` 的 overlap/flush 分支：overlap 以「整個段落塊」為單位回收（單塊 2400 字元遠大於 400 字元重疊目標），與新段落合併後再次 flush，產出超大 chunk。
3. **完全重複內容 1 組（x2）**：兩個 chunk 內容完全相同（起於 "e set to handle requests from players, a..."），同樣源於上述 flush 邏輯重複輸出。

## 8. Knowledge Sources

`sources.json`（未修改）：6 筆，結構一致。

| URL | title | version | type |
| --- | --- | --- | --- |
| guide.appliedenergistics.org/1.21.1/index | …Guide - Index | 1.21.1 | official_guide |
| …/getting-started | …Getting Started | 1.21.1 | official_guide |
| …/ae2-mechanics/autocrafting | …Autocrafting | 1.21.1 | official_guide |
| …/ae2-mechanics/energy | …Energy | 1.21.1 | official_guide |
| …/ae2-mechanics/import-export-storage | …Import Export Storage | 1.21.1 | official_guide |
| …/ae2-mechanics/channels | …Channels | 1.21.1 | official_guide |

- 全部屬 `guide.appliedenergistics.org` 單一網域；**無非官方來源、無其他 Minecraft 版本**。
- fetch 端另有程式級白名單（`ALLOWED_DOMAIN`）雙重把關。
- 規劃目標 15–20 頁，目前 6 頁（狀態資訊，歸 recall.md 管理）。

## 9. Dependency Architecture

| Dependency | Declared（requirements.txt） | Used（import 實證） | Purpose |
| --- | --- | --- | --- |
| requests | ✅（>=2.31） | ✅ fetch_pages.py | HTTP 下載 |
| beautifulsoup4 | ✅（>=4.12） | ✅ fetch_pages.py（`bs4`） | HTML 解析 |
| json / re / sys / argparse / datetime / pathlib / typing / urllib.parse | 標準庫 | ✅ 兩檔 | — |
| OpenAI SDK | ❌ Not declared | ❌ Not used | RAG 規劃用，未實作 |
| chromadb | ❌ Not declared | ❌ Not used | 同上 |
| streamlit | ❌ Not declared | ❌ Not used | 同上 |
| python-dotenv | ❌ Not declared | ❌ Not used | 同上 |
| PyYAML | ❌ Not declared | ❌ Not used（frontmatter 以 regex 子集處理） | — |

- Python 版本假設：程式碼以 `from __future__ import annotations` 支援型別標註語法，runtime 語法相容 Python 3.9；`__pycache__` 為 cpython-39 產物，與文件宣稱的 3.9.7 一致。
- 無 lock file、無 dev/test 依賴宣告。

## 10. Configuration / Secret Boundary

- **API key / model name / DB path：程式碼中沒有任何讀取點**（無 openai/dotenv import，無 os.environ 存取）。目前不存在需要金鑰的程式路徑。
- **Runtime configuration = 程式碼內常數**：`ALLOWED_DOMAIN`、`USER_AGENT`、`REQUEST_TIMEOUT=25`（fetch）；`TARGET_TOKENS`、`OVERLAP_TOKENS`、`MIN_CHUNK_TOKENS`、`CHARS_PER_TOKEN`、輸入輸出路徑（chunk）。無外部設定檔、無 CLI 參數（argparse 空殼）。
- `.env`：不存在（find 確認）；`.gitignore` 已預先涵蓋 `.env` / `.env.*`。
- Hard-coded credentials：已審閱的 694 行 Python 內**無**任何憑證、token 或帳密。
- `gcm-diagnose.log`：存在於 repo 根目錄、untracked + ignored。**依本階段禁令未讀取**；其含外洩 API key 之事為先前 session 確認並記錄於 recall.md / AGENTS.md，key 輪換仍為待辦。

## 11. Skills / Agent System

| Skill | 位置 | 類型 | 用途 |
| --- | --- | --- | --- |
| project-limit | skills/ + .agents/skills/ | agent behavior | 專案邊界、敏感資訊確認、UTF-8、最小化修改；含 cd 允許、grill-me 提問、操作前說明、重大異動更新 README |
| dev-environment | skills/ + .agents/skills/ | agent behavior + 環境事實 | Python 3.9.7 等工具認知、邊界、編輯規則、健康檢查 |
| git-auto-branch | .agents/skills/（全域 ~/.codex/skills/ 亦有；**repo 的 skills/ 無此 skill**） | agent behavior（Git workflow） | 任務 branch 管理、禁自行 merge |
| git-auto-commit | 同上 | agent behavior（Git workflow） | 邏輯單位 commit、禁 push main |
| git-init-repo | 同上 | agent behavior（Git workflow） | 無版控專案初始化、先問後建、一律 private |

- **無 pipeline skill**——所有 skill 均為 agent 行為/流程規範，與資料管線無關。
- **重複**：project-limit 與 dev-environment 在「工作區邊界、編輯規則」上內容重疊（兩處各寫一次）；屬刻意冗餘或歷史堆疊，未造成衝突（文字相近）。
- **不對稱**：git-* 三個 skill 僅存在於 .agents/skills/（ZCode）與全域 Codex 目錄，repo 的 `skills/`（Codex 版控源）沒有鏡像——版控完整性缺口。
- **與 AGENTS.md 的一致性**：AGENTS.md §2 將 skill 規範列於優先級第 3 位、§10 描述兩處同步義務——與實際檔案存在狀態一致；skill 內容（cd 允許、grill-me、操作前說明、private repo）與 AGENTS.md 對應規範一致。

## 12. Documentation Consistency

| 文件 | 判定 | 說明 |
| --- | --- | --- |
| AGENTS.md | **Accurate**（整體） | 契約逐條與程式碼核對：網域白名單、輸出路徑規則、metadata 六欄、切分常數值、fetch 結束碼 0/1、chunk 缺欄位整檔報錯且不產部分輸出、覆寫式冪等——全部與實作相符。**1 項 Discrepancy**：切分基準稱「目標 500–700 tokens」，實際輸出 11/36 超出（最大 1184）——契約描述的是常數與意圖，實際輸出行為未達（見 §7.2）。 |
| README.md | **Accurate + 1 drift** | 重寫後與實況一致（6 頁、36 chunks、里程碑、模組職責）。Drift：目錄結構章節仍列出 `analysis-summary.md`，但該檔已從工作目錄刪除。 |
| recall.md | **Accurate + 同上 drift** | 狀態與決策紀錄與實況一致；亦引用 analysis-summary.md。附帶異常：被 .gitignore 列入但仍是 tracked 檔案（gitignore 對已追蹤檔無效）。 |
| analysis-summary.md | **Discrepancy** | 版控中存在（committed），工作目錄中已被刪除（git status `D`，未 staged）。刪除者與原因未知（非本 session 所為）→ 見 §15。 |
| read.md | 歷史文件 | git skills 規格；其要求的 skills 已存在於全域與 .agents/，規格使命已履行，非現況規範。 |
| Contract Violation | **無** | 未發現程式實際行為違反 AGENTS.md 的「禁止/必須」條款；上述 token 超標與分節失效屬品質缺陷 + 契約描述落差，非故意違規。 |

## 13. Current State

| Component | Exists | Implemented | Actual Responsibility | Verified | Notes |
| --- | --- | --- | --- | --- | --- |
| Fetch | ✅ | ✅ | 白名單受控下載 → raw HTML + processed Markdown | ✅（程式碼閱讀 + 6+6 產物驗證） | 單頁失敗隔離；blockquote latent bug |
| Process（HTML→MD） | ✅ | ✅ | 併入 fetch 腳本，非獨立模組 | ✅（產物檢查） | 擷取殘留（$!/$、導覽、標題黏行） |
| Chunk | ✅ | ✅ | frontmatter 驗證 → 分節（失效）→ 切分 | ✅（36 行 schema 驗證） | token 超標 11/36、重複 1 組 |
| Index | ❌ | ❌ | （契約：chunks → Chroma） | — | Not implemented / not present |
| Query | ❌ | ❌ | （契約：檢索 → LLM 附來源回答） | — | Not implemented / not present |
| App | ❌ | ❌ | （契約：Streamlit） | — | Not implemented / not present |

總體：Phase 1 完成（6 頁，超出原定 3 頁）；Phase 2 一半（chunks 完成、頁數 6/15–20、索引未開始）；Phase 3–5 未開始。Git：main 與 origin/main 同步（5 commits），工作目錄有未提交變更（3 SKILL.md + README.md + recall.md 修改、AGENTS.md untracked、analysis-summary.md deleted）。

## 14. Known Issues / Risks

**Critical**

1. **憑證外洩未處置完畢**：`gcm-diagnose.log`（repo 根目錄，untracked+ignored）含真實 API key（先前 session 確認；本階段依禁令未重讀）。key 尚未輪換前，應視為已外洩憑證。檔案目前不在版控，但存在於工作目錄。

**Important**

2. **fetch 潛在 NameError**：`render_block` blockquote 分支呼叫未定義的 `render_children()`（fetch_pages.py:248）。未來任何含 `<blockquote>` 的頁面將解析失敗（單頁隔離不阻斷整批，但屬 pipeline failure）。目前 6 頁 raw HTML 無 blockquote，尚未觸發。
3. **heading 分節實際失效**：processed Markdown 0 個 `#` 標題行 → 36/36 chunk 的 `section_title` 全為 Introduction → 章節溯源喪失（provenance loss），且分節品質問題會直接進入未來的 embedding。
4. **切分輸出違反 token 基準**：11/36 chunk >700 tokens（最大 1184），另有 1 組完全重複 chunk——`split_long_text` overlap/flush 邏輯缺陷。未建索引前可低成本修復重跑；建索引後需整批重建。
5. **擷取殘留**：processed Markdown 含官網特殊標記（`$!/$`）、頁首導覽文字、標題與內文黏行——與 #3 同源，稀釋未來 embedding 品質。

**Minor**

6. `chunk_id` 全域流水號，重跑重編號，不宜作長期識別（應以 source_url+section 組合）。
7. `fetched_at` 在 processed（抓取時間）與 chunks.jsonl（切分時間）語義不一致。
8. `recall.md` 被 .gitignore 列入但仍 tracked；`analysis-summary.md` 被刪除但仍 tracked——兩者皆為版控/工作目錄不一致。
9. `render_children_html` 為 dead code；`argparse` 空殼。
10. `analysis-summary.md` 內容早於 README/AGENTS 重寫（歷史快照），若保留需標註或更新。
11. token 估算為 4 字元近似（非 tokenizer），對英文尚可、對中文偏差。

## 15. Unknown / Open Questions

| Question | Why Unknown | Required Decision |
| --- | --- | --- |
| index/query/app 的實作細節（embedding model、collection 命名、top-k 預設、prompt 模板、LLM 參數） | 未實作，文件僅到契約層 | 實作前的設計決策 |
| `chunk_id` 是否需要跨 run 穩定（如 hash-based） | 契約未規定；現況重跑會重編號 | 設計決策 |
| `chunk_pages.py` 的 argparse 是否預期接受參數 | import 並建立 parser 但未定義/未使用 | 設計意圖確認 |
| RAG 回答的語言（繁中固定？跟隨提問？） | 文件未明定 | 產品決策 |
| 終端使用者是誰（玩家？AI 協作者自我查詢？） | 文件未明載 | 產品決策 |
| `recall.md` 是否以 `git rm --cached` 移出版控 | 已記錄待決，使用者尚未裁決 | 使用者決定 |
| `analysis-summary.md` 的刪除是有意或意外？文件引用（README/recall）是否清理 | 刪除發生於工作目錄，git 顯示 D 未 staged，非本 session 所為 | 使用者決定 |
| 是否修復 blockquote NameError、分節失效、token 超標 | 屬程式修改，本階段禁改；修復方式需設計 | 下一階段排程 + 使用者批准 |
| 官網標題為何未被轉為 Markdown heading | 需解析 raw HTML 結構（本階段未深入 raw html 內部） | 下一階段技術調查 |
| `skills/`（Codex 版控源）是否補齊 git-* 三個 skill 的鏡像 | 現況不對稱，維護策略未定 | 維護決策 |

## 16. Handoff Summary

給未接觸過本 repo 的 AI 的快答：

1. **這是什麼**：Minecraft AE2 RAG Assistant——依 AE2 官方 1.21.1 指南回答問題的 RAG 助手；答案必須附來源，文件不足必須明說「目前官方文件不足以確認」。
2. **技術**：Python 3.9 原生管線（requests + BeautifulSoup → Markdown/YAML → Chroma → OpenAI Embeddings/LLM → Streamlit 展示層）；不用 LangChain。
3. **資料來源**：`sources.json` 人工指定的 `guide.appliedenergistics.org/1.21.1` 頁面（目前 6 頁），fetch 端有程式級網域白名單。
4. **資料流**：fetch → `data/raw/*.html` + `data/processed/*.md`（YAML frontmatter 六欄）→ chunk → `data/chunks.jsonl`（36 chunks、10 欄 schema）；此後（index → Chroma → query → app）為契約、尚未實作。
5. **RAG 現況**：檢索與生成不存在；能跑的只有「抓取與切分」兩個離線階段。
6. **已存在**：fetch_pages.py、chunk_pages.py、6 頁資料產物、7 個行為 skill（2 Codex + 5 ZCode）、三份文件（README 人類用、AGENTS.md 契約、recall.md 狀態）。
7. **未完成**：index/query/app/tests、頁數擴充（6/15–20）、key 輪換。
8. **文件不一致**：AGENTS.md 契約與程式碼整體相符（1 項落差：實際 chunk token 有 11/36 超出 500–700 基準）；README/recall 引用的 analysis-summary.md 已從工作目錄刪除但仍在版控。
9. **最大風險**：① 外洩 API key 未輪換（Critical）；② 建索引前的資料品質債——分節失效（0 heading、全 Introduction）、token 超標、重複 chunk、擷取殘留，若先建索引將整批固化；③ blockquote 潛在 NameError。
10. **接手須知**：先讀 AGENTS.md（契約與優先級）、recall.md（狀態與決策）；push/merge 需使用者明確指示、merge 一律人工；修改前先解決資料品質債再談索引；本檔（project_audit.md）為 2026-09-13 的證據快照，其後以 recall.md 為準。
