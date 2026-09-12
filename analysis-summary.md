# Minecraft_RAG 專案總結分析

> 由 AI 協作者於 2026-09-13 閱讀專案全部文件後撰寫，作為現況總結與分析。

## 1. 專案定位

**Minecraft AE2 RAG Assistant**：針對 Minecraft 1.21.1 與 Applied Energistics 2（AE2）的知識問答 RAG（檢索增強生成）助手。核心設計原則：

- 僅以 **AE2 官方 1.21.1 線上指南**為資料來源，不做全站爬取（初期 15～20 頁人工指定）。
- 所有回答附**可點擊來源連結**；官方文件不足時必須明確表示「無法確認」，不得猜測。
- 初期**不使用 LangChain**，先以原生 Python 理解底層資料流程。

## 2. 技術棧與資料流程

Python + `requests`/BeautifulSoup → Markdown + YAML metadata → chunking（500～700 tokens、重疊 80～120）→ OpenAI Embeddings → 本機 Chroma → LLM 依檢索內容回答 → Streamlit 展示（最後階段）。

## 3. 目前的實際進度

對照 README 的 Phase 1–6 里程碑，專案已完成 **Phase 1，並部分進入 Phase 2**：

| 項目 | 規劃狀態 | 實際狀態 |
| --- | --- | --- |
| `README.md` | 專案規格書 | ✅ 完整（10 個區塊，含規範與里程碑） |
| `sources.json` | — | ✅ 已建立，含 6 個官方頁面來源 |
| `fetch_pages.py` | Phase 1 | ✅ **已完整實作**（約 440 行，非 README 所述的空檔） |
| `chunk_pages.py` | Phase 2 | ✅ **已完整實作**（約 250 行） |
| `data/raw/` | 原始 HTML | ✅ 已有 6 頁 HTML |
| `data/processed/` | 清理後 Markdown | ✅ 已有 6 頁含 YAML frontmatter 的 Markdown |
| `data/chunks.jsonl` | 切分輸出 | ✅ 已產出 36 個 chunks（fetched_at 為 2026-08-26） |
| `index_chunks.py` | Phase 2 | ❌ 尚未建立 |
| `query.py` | Phase 3–4 | ❌ 尚未建立 |
| `app.py`（Streamlit） | Phase 5 | ❌ 尚未建立 |
| `tests/`、`.env.example` | — | ❌ 尚未建立 |

**注意**：README 第 5 節與 `recall.md`（截至 2026-08-25）仍記載「僅有 README 與空的 fetch_pages.py」，已明顯落後於實際進度，建議更新。

## 4. 已實作程式碼分析

### fetch_pages.py（擷取器）
- 受控擷取：僅接受 `guide.appliedenergistics.org` 網域、自訂 User-Agent、25 秒 timeout；單頁失敗不影響其他頁，結束時統計成功/失敗/略過。
- 自行實作 HTML→Markdown 轉換（headings、清單、表格、程式碼區塊、連結），排除 nav/footer/aside/script 等雜訊。
- 輸出 `data/raw/<host>/<slug>.html` 與 `data/processed/<host>/<slug>.md`，後者帶符合規範的 YAML frontmatter（title、source_url、minecraft_version、mod、source_type、fetched_at）。

### chunk_pages.py（切分器）
- 解析 frontmatter（簡易雙引號 YAML，缺欄位即報錯），強制要求 `source_url`——符合「無來源不得入知識庫」規範。
- 以 Markdown 標題分節，節內以 600 tokens（字元數 ÷4 估算）為目標切分、重疊 100 tokens、過濾低於 40 tokens 的碎塊。
- 每 chunk 保留完整 metadata（來源 URL、頁名、章節標題、版本），符合規範。

### 品質觀察（對 RAG 檢索品質有直接影響）
- 抽樣 `getting-started.md` 與 `chunks.jsonl` 可見明顯的**擷取殘留**：
  - 頁首導覽文字（如 `[Applied Energistics 2](/)` logo 連結）被保留。
  - 官方網站的特殊標記字串（`$!/$`、`$!!` 之類裝飾符號）混入正文。
  - 部分標題與內文黏成同一行（如「Getting StartedGetting The Initial Materials）$!/$」），會讓「以標題分節」失效或分節錯誤。
  - 圖片語法大量殘留（chunker 會移除圖片，但 processed 文件本身仍很雜）。
- 這些殘留會稀釋 embedding 品質，建議在進入 `index_chunks.py` 前先強化 `to_markdown()` 的清理邏輯（處理該站的標記符號與標題黏行）。
- token 估算採固定 4 字元/token 的近似值，對英文內容尚可，屬 MVP 合理取捨。

## 5. 專案周邊文件與雜項

- `recall.md`：狀態與決策記錄（已過時，見第 3 節）。
- `read.md`：使用者對 AI 的 Git 工作流要求（任務 branch、自動 commit、不得自行 merge/push main）。
- `skills/project-limit/`、`skills/dev-environment/`：兩個 instruction-only Skill，規範專案邊界存取、敏感資訊確認、UTF-8 與最小化模組化修改、開發環境認知（Python 3.9.7、Git 2.46、Node 24 等）；各含 `agents/openai.yaml`。`project-limit-skill-summary.txt` 記錄其建立與全域部署過程（安裝至 `~/.codex/skills/`）。
- `.codex/local.ps1`：以本地 llama.cpp 伺服器（Qwen 量化模型）啟動 Codex CLI 的啟動器，顯示專案也在嘗試本地模型路線。
- `requirements.txt`：目前僅 `requests`、`beautifulsoup4`；後續加入 `chromadb`、`openai`、`streamlit` 時需依規範在 README 說明用途。

### ⚠️ 安全問題（建議優先處理）
- **`gcm-diagnose.log`（未納入版控）是 Git Credential Manager 的診斷輸出，內含環境變數傾印，其中包括一組真實的 API key**。此內容違反專案自身規範（「不將 API Key 寫入任何檔案」）。建議：刪除該檔或加入 `.gitignore`，並到該服務後台撤銷/輪換該 key（檔案曾存在於工作目錄，且 key 已外洩至 log 即應視為失效）。本報告不重述該值。

## 6. 建議的下一步

1. **處理安全問題**：移除 `gcm-diagnose.log` 並輪換外洩的 key。
2. **強化 fetch_pages.py 的清理**：去除該站特殊標記（`$!/$` 等）與導覽殘留，修正標題黏行，再重新執行 fetch + chunk。
3. **更新 `recall.md` 與 README 第 5 節**，反映 fetch/chunk 已完成、資料已產出的現況。
4. **實作 `index_chunks.py`**：讀取 `chunks.jsonl`，以 OpenAI Embeddings 寫入本機 Chroma（需要 `.env` 與 `python-dotenv`，並建立 `.env.example`）。
5. **實作 `query.py`**：以 README 第 9 節的 5 個驗收問題做 Top 3 檢索驗證。
6. 為 `fetch_pages.py` 與 `chunk_pages.py` 補上基本測試（`tests/`）。
