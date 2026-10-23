# 來源設定與抓取

> 職責：由 `sources.json` 決定範圍，從 sitemap.xml 取得逐頁 URL，抓下 raw HTML。只做網路 I/O。
> 下一個階段：[抽取](02_extract.md)

程式：`src/fetch_pages.py`

## 1. 輸入與輸出

### 輸入：`sources.json`（人工維護，各階段可共用讀取）

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
| `mod` | 模組**原名**，不 slug 化；由本階段轉成 `mod_slug` |
| `entry_url` | 只用來推導站台根（scheme + host），**不作為抓取目標**；版本取自 `version`，不由入口頁推導 |
| `exclude`／`include` | 保留於 schema；目前不讀取（範圍由版本過濾決定） |

`sources.json` 是整條 URL 鏈的起點：`version` + 站台根 → 本階段解析 sitemap.xml 產生逐頁 URL → [抽取](02_extract.md) 抽出 `source` → chunk 的 `source_url`。

### 輸出

- `data/raw/<version>/<mod_slug>/<chapter>/<page_slug>.html`
- `data/raw/_manifest.json`（整份覆寫）：

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

  - `mod` 保留原名、`mod_slug` 為 slug 化結果，manifest 可單獨追溯原名。
  - `source` 記錄 URL 的發現來源（`"sitemap"`）。
  - `local_path` 是相對專案根目錄的 POSIX 路徑；失敗頁為 `null`。
- `data/raw/_fetch_log.txt`：逐頁成敗的 debug log（覆寫，不入版控）。

## 2. 處理方法

1. 由 `entry_url` 推導站台根，讀 `robots.txt` 的 `Sitemap:` 宣告；沒有宣告時依序試 `/sitemap.xml`、`/sitemap_index.xml`、`/sitemap-index.xml`。
2. 有效條件：HTTP 200 **且**根節點為 `<urlset>` 或 `<sitemapindex>`；全部失敗 → fail-fast「此站台無可用 sitemap」（exit 1），**不回退任何導覽爬取**。
3. `xml.etree.ElementTree`（標準庫）解析；`<sitemapindex>` 遞迴抓子 sitemap 後合併 `<loc>`。
4. 版本過濾：`urlparse(url).path.startswith(f"/{version}/")`。**必須帶尾斜槓**，不可用 `"1.21.1" in url`，以免 `1.21.10` 誤判。排除入口頁：路徑去掉結尾 `/` 後等於 `/{version}` 或 `/{version}/index`（站台網址可能帶結尾 `/`，見 [T8](07_troubleshooting.md#t8-站台建置方式改變內容未更新)）。抓取時使用 sitemap 給的原始網址，不改寫。
5. 逐頁抓取，每頁間隔 0.5 秒。
6. 解析路徑三元素（本階段是唯一的計算來源，下游一律從路徑讀）：

   | 元素 | 來源 | 範例 |
   | --- | --- | --- |
   | `mod_slug` | `mod` 經 `python-slugify` | `Applied Energistics 2` → `applied-energistics-2` |
   | `chapter` | URL 去掉版本前綴後的倒數第二段；URL 本身已是 slug，不再 slug 化 | `.../1.21.1/ae2-mechanics/energy` → `ae2-mechanics` |
   | `page_slug` | URL 最後一段 | `energy` |

   只有一段的路徑（如 `/1.21.1/getting-started/`）一律歸 `chapter = other`，確保每頁都恰好有一層 chapter。路徑中的空段（結尾 `/`）不計。

   防護：解析出的 `page_slug` 為空時，該頁記為失敗（`local_path: null`、`error` 說明原因），不寫檔，結束碼為 1。
7. 寫出 `_manifest.json`。

**失敗處理**：不重試；記錄 `http_status` 與 `local_path: null`，仍寫出 manifest，結束碼為 1；人工查驗後重跑。

## 3. 為什麼這樣做

### URL 真值來源用 sitemap.xml

原本的設計是用 BeautifulSoup 解析入口頁側邊欄，取得所有子頁 URL。實作前探查（2026-09-27）發現這個假設不成立：站台是 **Next.js App Router SPA**（`/_next/static/chunks/app/[versionSlug]/[...pagePath]/page-*.js`），伺服器只預渲染骨架。

| 觀察 | 結果 |
| --- | --- |
| 入口頁 `<aside>` 側邊欄連結數 | 6（3 個章節索引 + getting-started + tips-and-tricks + index），不含任何子頁 |
| 側邊欄行為 | 情境式展開：只有「當前所在章節」才展開子頁 |
| `ae2-mechanics` 索引頁 `<main>` 子頁 | 15／15 完整 |
| `example-setups` 索引頁 `<main>` 子頁 | 21／21 完整 |
| `items-blocks-machines` 索引頁 `<main>` 子頁 | **1／86**：該頁為 client-side rendering，伺服器 HTML 只有 `<span>Unknown category: devices</span>` 等 5 個占位字串，真正的 85 個物品連結由 JS 動態填入 |
| 側邊欄 BFS 總涵蓋 | **39／124**（漏 85 頁，佔知識庫內容 69%） |

缺口不是 selector 寫錯，而是資料根本不在伺服器渲染的 HTML 裡；`requests` + BeautifulSoup（沒有 JS 引擎）無法取得完整清單。

sitemap 驗證（2026-09-27）：`robots.txt` 宣告 `https://guide.appliedenergistics.org/sitemap.xml`；根節點 `<urlset>`（單層）；全站 `<loc>` 1,427 個（含所有版本），`1.21.1` 過濾後 125 個，排除入口頁後 124 個；沒有查詢字串、錨點、結尾斜線等雜質，也沒有重複 URL。

### 其他

- **抓取與抽取分離**：本階段只做網路 I/O，主文抽取交給 [抽取](02_extract.md) 的 trafilatura，避免自寫 HTML 轉換器的維護成本。
- **`*-index` 章節索引頁照抓**：sitemap 含這 3 頁，由 [抽取](02_extract.md) 以 navigation_only 規則跳過。
- **失效模式**：站方移除 sitemap 或改變 robots 宣告 → fail-fast 並明確報錯，優於靜默漏資料。
- 不新增依賴：`xml.etree.ElementTree` 是標準庫。

## 4. 否決的方案

- **側邊欄 BFS**：只得 39／124，`items-blocks-machines` 章 85 頁全漏。
- **混合（BFS 為主 + sitemap 補齊）**：最終集合與純 sitemap 相同，卻多維護一套探索邏輯與額外請求；兩套來源併存會讓「真值」定義模糊。
- **Next.js flight data（`self.__next_f.push(...)` 內嵌的 `navigationNodes`）**：單一請求即含全部 125 頁，與 sitemap 雙向差集為空，但仍否決：
  1. **循環驗證**：它的完整性只能靠 sitemap 驗證；以它為主來源就失去獨立的真值。
  2. **內部格式耦合**：它是 Next.js 的內部序列化格式（stream id、`$Lb`、`$undefined` 等），沒有穩定 API，也沒有文件；站方改版或 Next.js 升級就可能失效。
  3. **沒有附加價值**：sitemap 已提供相同的 URL 集合，而且是站台主動對外宣告的標準介面。

  flight data 只保留作為交叉驗證工具，不作為 pipeline 來源。

## 5. 驗證方式

執行 `python src/fetch_pages.py`：

- `_manifest.json` 存在，每頁都記錄 `http_status`。
- 結束碼 0；有失敗記錄時為 1，須如實回報。

## 6. 待定事項

| 事項 | 狀態 |
| --- | --- |
| `exclude`／`include` 是否啟用 | 保留欄位；需要時再定義 |
