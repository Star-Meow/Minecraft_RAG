# 入庫

> 職責：把 child 向量與 parent 文件寫入 PostgreSQL + pgvector。
> 上一個階段：[向量化](05_embed.md)

程式：`src/index_chunks.py`、`src/verify_index.py`、`src/audit_index.py`、`src/index_check_utils.py`（索引類型與重跑策略見 §2.1 D1、D5，schema 見 §2.2）

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
  - 改表結構（換維度、DROP）：每次須使用者確認，人工處理。程式永不 DROP／TRUNCATE；刪除範圍只限 `rag.parents`、`rag.children` 兩表的該 version。
- **D5-1 目標資料庫斷言**（2026-11-07 使用者裁定；兩種模式皆適用，在交易開始前執行，任一不符即中止、不動任何資料）：
  - 從 `DATABASE_URL` 解析出的主機必須是 `127.0.0.1` 或 `localhost`（只能從 URL 判斷；不得使用 `inet_server_addr()`，資料庫在 Docker 中時它回傳容器內部位址）。
  - `SELECT current_database()` 的結果必須是 `minecraft_rag`（以伺服器的回答為準）。
  - `DATABASE_URL` 與 `DATABASE_URL_TEST` 解析出的庫名不得相同。
  - 重做波及範圍：日後資料庫移出本機時，須同步修改本斷言與本文件。
- **D5-2 測試庫斷言**（驗證腳本適用）：從 `DATABASE_URL_TEST` 解析出的主機必須是 `127.0.0.1` 或 `localhost`；`SELECT current_database()` 必須是 `minecraft_rag_test`；兩個 URL 的庫名不得相同；只清理明列的 `rag.children`、`rag.parents`（先 children 後 parents；限定範圍的 DELETE，不用 TRUNCATE 或 DROP），不得以「清空所有表」的方式清理。
- **D6**：不納入問題集；驗收文件須註明「V5 只證明資料庫排序等於暴力計算，不證明檢索品質」。
- **D7**：使用者一次性手動執行 `CREATE EXTENSION IF NOT EXISTS vector;`，兩個庫各一次；程式啟動時檢查擴充存在與版本，缺少即清楚中止。版本規格（2026-11-07 使用者裁定）：`extversion >= 0.8.2`（避開 CVE-2026-3172，影響 pgvector 0.6.0–0.8.1 的平行 HNSW 建索引）。
- **Docker**：個人專案，不做環境隔離：單一容器、兩個 database（`minecraft_rag`、`minecraft_rag_test`）；PG18；映像 `pgvector/pgvector:<固定標籤>`；只綁 `127.0.0.1:5433`；named volume 掛 `/var/lib/postgresql`；init script 只建測試庫，不建擴充；所有指令從專案根目錄執行 `docker compose --env-file .env -f infra/docker-compose.yml …`。細節（服務名稱 `db`、英文錯誤訊息、不設 restart policy、healthcheck 10s/5s/5/10s）2026-11-07 使用者裁定接受。
- **版控流程**（2026-11-07 使用者裁定）：[7] 全部完成後才 push 與開 PR；在此之前只做本機 commit 留存紀錄，方便回溯。
- **schema 已知的必要條件**（不是完整 schema；欄位定義見 §2.2）：
  - parents、children 兩表都必須有 `version` 欄位（D5 的所有刪除都以 version 為範圍）。
  - 必須能查出每列的 `model_name`、`model_revision` 與向量維度（D5 防呆需要）。
  - 唯一鍵用 `parent_id`／`chunk_id`；不可對 `text` 設 UNIQUE。
- 資料事實（2026-11-07 唯讀實測）：child 層有 7 組重複文字（14 個 child，分屬 12 個 parent），parent 層另有 8 個 parent 的完整 text 與其他 parent 相同；各組 source_url 皆不同。因此 schema 不可對 text 設 UNIQUE，唯一鍵用 `parent_id` 或 `chunk_id`。

### 2.2 schema 與實作決策（2026-11-14 使用者核准實作計畫）

- **表與名稱**：schema `rag`，兩表 `rag.parents`、`rag.children`；所有 SQL 一律使用限定名稱（`rag.*`、`public.vector`、`OPERATOR(public.<=>)`），**不更動連線的 `search_path`**；啟動時斷言 pgvector 擴充在 `public`。
- **外鍵**：`rag.children.parent_id` 外鍵指向 `rag.parents.parent_id`，`NO ACTION`，不得 `ON DELETE CASCADE`；`children.parent_id` 建 B-tree 索引（外鍵參照側不會自動建索引；不是向量索引，與 D1 不衝突）。
- **建立方式**：`ensure_schema` 在寫入的同一個交易內執行 `CREATE SCHEMA／TABLE／INDEX IF NOT EXISTS`；寫入前核對既有欄位型別、向量維度、外鍵，不符即中止並列出，不自動變更表結構；擴充由使用者手動建立（D7）。
- **模式**：`--mode` 必填、無預設；update 對空表視同全部新增；update 比對整張 `rag.children` 的 `(model_name, model_revision)` 與向量維度；rebuild 另檢查其他 version 的 model 組，與輸入不一致即中止。
- **寫入順序**：parents 先、children 後；刪除順序 children 先、parents 後；所有 DELETE 皆以 version 為範圍。
- **`DATABASE_URL_TEST`**：缺少即中止（D5-1 需比對兩個庫名）。
- **向量距離**：運算子 `<=>`（cosine 距離）；寫入以 `pgvector` 的轉接器，以 `public.vector` 限定名稱註冊。
- **報告**：`index_chunks.py` 每次執行寫 `reports/index_report.md`，只含它打算寫入的產物端指紋；指紋比對由 `verify_index.py`、`audit_index.py` 各自出報告（`reports/verify_index_report.md`、`reports/audit_index_report.md`）。

DDL（欄位順序即內容指紋的序列化順序）：

```sql
CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.parents (
    parent_id   text    NOT NULL,
    text        text    NOT NULL,
    title       text    NOT NULL,
    source_url  text    NOT NULL,
    version     text    NOT NULL,
    mod         text    NOT NULL,
    chapter     text    NOT NULL,
    page        text    NOT NULL,
    section     text    NOT NULL,
    token_count integer NOT NULL,
    CONSTRAINT parents_pkey PRIMARY KEY (parent_id),
    CONSTRAINT parents_nonempty_chk CHECK (
        parent_id <> '' AND text <> '' AND title <> '' AND source_url <> ''
        AND version <> '' AND mod <> '' AND chapter <> '' AND page <> '' AND section <> ''),
    CONSTRAINT parents_token_count_chk CHECK (token_count > 0)
);

CREATE TABLE IF NOT EXISTS rag.children (
    chunk_id       text                NOT NULL,
    parent_id      text                NOT NULL,
    text           text                NOT NULL,
    title          text                NOT NULL,
    source_url     text                NOT NULL,
    version        text                NOT NULL,
    mod            text                NOT NULL,
    chapter        text                NOT NULL,
    page           text                NOT NULL,
    section        text                NOT NULL,
    token_count    integer             NOT NULL,
    embedding      public.vector(1024) NOT NULL,
    model_name     text                NOT NULL,
    model_revision text                NOT NULL,
    CONSTRAINT children_pkey PRIMARY KEY (chunk_id),
    CONSTRAINT children_parent_id_fkey FOREIGN KEY (parent_id)
        REFERENCES rag.parents (parent_id) ON DELETE NO ACTION ON UPDATE NO ACTION,
    CONSTRAINT children_nonempty_chk CHECK (
        chunk_id <> '' AND parent_id <> '' AND text <> '' AND title <> '' AND source_url <> ''
        AND version <> '' AND mod <> '' AND chapter <> '' AND page <> '' AND section <> ''
        AND model_name <> '' AND model_revision <> ''),
    CONSTRAINT children_token_count_chk CHECK (token_count > 0)
);

CREATE INDEX IF NOT EXISTS children_parent_id_idx ON rag.children USING btree (parent_id);
```

- 不存 `embedding_input`（等於 `f"{section}

{text}"`，可由 `section`、`text` 重現）。
- `model_name`、`model_revision` 不寫死；驗證「全表只有一組非空」。
- 不對 `text` 設 UNIQUE（有重複文字，見上方資料事實）。
- 非空 CHECK 與 `token_count > 0` 是資料庫層面對 AGENTS.md §3.1（provenance 不得為空）的保證。
- 否決：複合外鍵 `(parent_id, version)`（parent_id 本身以 version 開頭，且輸入檢查已保證三檔同一 version，過度設計）；設定 `search_path = rag, public`（需每個使用者記得設定，漏設才出錯，且與「表一律完整名稱」並存會有兩套規則）；為 `version` 另建索引（單一版本、數百列，循序掃描更快）。

## 3. 為什麼這樣做

docstore 模式是子母分層的標準做法（見 [04_chunk.md](04_chunk.md)）：只對 child 建索引，命中後取回 parent 交給 LLM。

## 4. 待定事項

| 事項 | 狀態 |
| --- | --- |
| schema（欄位、型別、約束） | 已定：見 §2.2 |
| 入庫方式 | 已定：兩表、精確掃描（D1）；重跑分 `update`／`rebuild` 兩種模式，由使用者明確指定（D5）；寫入前執行目標資料庫斷言（D5-1） |
| 索引類型 | 已定：不建向量索引（D1），日後依效果新增 |

## 5. 驗證方式

驗證由獨立腳本執行，不寫在 `index_chunks.py` 內（程式不驗證自己）；`index_chunks.py --mode …` 由使用者確認模式後執行；`verify_index.py`、`audit_index.py` 依 AGENTS.md §10（任何 Agent 不得讀 `.env`，D4）。

- **`python src/verify_index.py`**（只連測試庫，D5-2；`--offline` 只跑不讀 `.env`、不連線的項目）：
  - V1 測試庫斷言；V2 筆數（由產物即時計算）；V3 text 往返（內容、字元長度、位元組長度）；V4 純量欄位與欄位清單；V23 向量往返（float32 位元組相等）；V6 內容指紋（資料庫端對產物端）；V7 單一 model 組；
  - V5 最近鄰排序：每個 child 的自身向量當查詢，`<=>` 的第一名須落在暴力計算（float64、先正規化的真 cosine）最小距離的並列組內（容差 |d − d_min| ≤ 1e-6；float32 與 float64 的 cosine 實測最大差 3.1e-7，最小的真實間距 0.0093）；前 5 名距離逐名相差 ≤ 1e-6；沒有向量索引。實測偏差超過 5e-7 時須回報，不自行放寬。**V5 只證明資料庫排序等於暴力計算，不證明檢索品質**（D6）；
  - V8 交易回滾（輸入 1023 維、於第 N 個語句注入例外，兩種模式）；V9 update 新增／更新／刪除筆數；V10 冪等；V11 update 防呆；V12 外鍵與刪除順序；V20 DELETE 範圍限於 version，及 rebuild 檢查其他 version 的 model 組；V22 空表 update；
  - V13 連線前即中止的負向案例（以子行程執行 CLI，spy 證明沒有連線）；V14 密碼遮罩；V15 無模型載入；V16 報告格式；V17 無 DROP／TRUNCATE／ALTER／CASCADE；V18 無測試後門；V19 入庫前驗證先於連線；V21 schema 不符與擴充版本（函式層級）。
- **`python src/index_chunks.py --mode update|rebuild`** 後執行 **`python src/audit_index.py`**（只連正式庫，唯讀）：A1～A12：斷言與唯讀、擴充版本、schema 與外鍵、筆數、內容指紋、單一 model 組、孤兒與子字串、version、text 往返、向量往返、最近鄰排序（同 V5）、腳本無寫入關鍵字。
- 實測（2026-11-14）：測試庫完整驗證 79 項、0 項不通過，V5 最大距離偏差 2.8e-07；正式庫 `audit_index.py` 12 項、0 項不通過。
- `reports/index_report.md`：欄位齊全，不含密碼或完整 URL。
