# 入庫

> 職責：把 child 向量與 parent 文件寫入 PostgreSQL + pgvector。
> 上一個階段：[向量化](05_embed.md)

程式：`src/index_chunks.py`（**尚未實作**；索引類型與重跑策略已定（見 §2.1 D1、D5），schema 擱置，不預先虛構）

## 1. 輸入與輸出

- **輸入**：[向量化](05_embed.md) 的 child 向量，以及 [切分](04_chunk.md) 的 parent 文件。
- **輸出**：PostgreSQL + pgvector 中的資料。

## 2. 已定的內容

- **資料庫**：PostgreSQL + pgvector。
- **docstore 模式**：child 向量進向量庫；parent 文件能由 child 上的 parent 參照取回。本階段直接讀切分階段的 parent 產物，不經向量化階段轉交。
- **向量維度**：1024（見 [05_embed.md](05_embed.md)）。

### 2.1 決策紀錄（使用者裁定）

- **D1**：方案 A：parents、children 兩表，精確掃描，不建向量索引；日後依效果調整（加索引屬新增索引，不改 schema）。混合檢索屬檢索階段，不在 [7] 決定。
- **D2**：Docker 設定放在 `infra/`（專案內、入版控，`.env` 不入版控）。[7] 只認 `DATABASE_URL`，不 import 任何容器相關知識。
- **D3**：允許專案專用依賴 `psycopg[binary]`、`pgvector`（Python 套件）、`python-dotenv`；版本由實作 Agent 核實 Windows／Python 3.12 相容性後鎖定。numpy 只在程式直接 import 時列入。
- **D4**：連線資訊走 `.env`（`DATABASE_URL`、`DATABASE_URL_TEST`），用 python-dotenv 載入；密碼不得出現在日誌與報告；任何 Agent 不得讀 `.env`。
- **D5**（2026-11-07 使用者裁定）：重跑 [7] 前，由使用者確認切分設定與 embedding 模型是否改變（產物目前不記錄切分設定指紋，程式無法自行判斷）。
  - 模式必須以 `--mode update` 或 `--mode rebuild` 明確傳入，**沒有預設值**；未傳入即中止。
  - 未改變 → `update`（更新模式）：單一交易內，依 `parent_id`（parents）／`chunk_id`（children）就地更新仍存在的列、新增新列，並刪除該 version 中新產物已不存在的列；刪除順序為先 children 後 parents（避免檢索命中已刪除的指南內容）。
  - 有改變 → `rebuild`（重做模式）：單一交易內刪除該 version 兩表的資料（先 children 後 parents），再全部寫入。
  - 防呆：`update` 啟動時，若資料庫內的 `(model_name, model_revision)` 或向量維度與新產物不同，即中止並提示改用 `rebuild`（須使用者確認）。
  - 改表結構（換維度、DROP）：每次須使用者確認，人工處理。程式永不 DROP／TRUNCATE；刪除範圍只限 rag 兩表的該 version。
- **D5-1 目標資料庫斷言**（2026-11-07 使用者裁定；兩種模式皆適用，在交易開始前執行，任一不符即中止、不動任何資料）：
  - 從 `DATABASE_URL` 解析出的主機必須是 `127.0.0.1` 或 `localhost`（只能從 URL 判斷；不得使用 `inet_server_addr()`，資料庫在 Docker 中時它回傳容器內部位址）。
  - `SELECT current_database()` 的結果必須是 `minecraft_rag`（以伺服器的回答為準）。
  - `DATABASE_URL` 與 `DATABASE_URL_TEST` 解析出的庫名不得相同。
  - 重做波及範圍：日後資料庫移出本機時，須同步修改本斷言與本文件。
- **D5-2 測試庫斷言**（驗證腳本適用）：從 `DATABASE_URL_TEST` 解析出的主機必須是 `127.0.0.1` 或 `localhost`；`SELECT current_database()` 必須是 `minecraft_rag_test`；兩個 URL 的庫名不得相同；只清理明列的 rag 資料表，不得以「清空所有表」的方式清理。
- **D6**：不納入問題集；驗收文件須註明「V5 只證明資料庫排序等於暴力計算，不證明檢索品質」。
- **D7**：使用者一次性手動執行 `CREATE EXTENSION IF NOT EXISTS vector;`，兩個庫各一次；程式啟動時檢查擴充存在與版本，缺少即清楚中止。版本規格（2026-11-07 使用者裁定）：`extversion >= 0.8.2`（避開 CVE-2026-3172，影響 pgvector 0.6.0–0.8.1 的平行 HNSW 建索引）。
- **Docker**：個人專案，不做環境隔離：單一容器、兩個 database（`minecraft_rag`、`minecraft_rag_test`）；PG18；映像 `pgvector/pgvector:<固定標籤>`；只綁 `127.0.0.1:5433`；named volume 掛 `/var/lib/postgresql`；init script 只建測試庫，不建擴充；所有指令從專案根目錄執行 `docker compose --env-file .env -f infra/docker-compose.yml …`。細節（服務名稱 `db`、英文錯誤訊息、不設 restart policy、healthcheck 10s/5s/5/10s）2026-11-07 使用者裁定接受。
- **版控流程**（2026-11-07 使用者裁定）：[7] 全部完成後才 push 與開 PR；在此之前只做本機 commit 留存紀錄，方便回溯。
- **schema 已知的必要條件**（不是完整 schema；欄位定義仍擱置）：
  - parents、children 兩表都必須有 `version` 欄位（D5 的所有刪除都以 version 為範圍）。
  - 必須能查出每列的 `model_name`、`model_revision` 與向量維度（D5 防呆需要）。
  - 唯一鍵用 `parent_id`／`chunk_id`；不可對 `text` 設 UNIQUE。
- 資料事實（2026-11-07 唯讀實測）：child 層有 7 組重複文字（14 個 child，分屬 12 個 parent），parent 層另有 8 個 parent 的完整 text 與其他 parent 相同；各組 source_url 皆不同。因此 schema 不可對 text 設 UNIQUE，唯一鍵用 `parent_id` 或 `chunk_id`。

## 3. 為什麼這樣做

docstore 模式是子母分層的標準做法（見 [04_chunk.md](04_chunk.md)）：只對 child 建索引，命中後取回 parent 交給 LLM。

## 4. 待定事項

| 事項 | 狀態 |
| --- | --- |
| schema（欄位、型別、約束） | 擱置（已知必要條件見 §2.1「schema 已知的必要條件」） |
| 入庫方式 | 已定：兩表、精確掃描（D1）；重跑分 `update`／`rebuild` 兩種模式，由使用者明確指定（D5）；寫入前執行目標資料庫斷言（D5-1） |
| 索引類型 | 已定：不建向量索引（D1），日後依效果新增 |
