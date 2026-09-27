# ADR-001：以 sitemap.xml 作為 [2] 頁面 URL 真值來源

- **日期**：2026-09-27
- **狀態**：Accepted
- **影響階段**：[2] 抓取（`src/fetch_pages.py`）
- **替代方案**：側邊欄 BFS、Next.js flight data `navigationNodes`

## 1. 背景

原契約（`AGENTS.md` §6／`ARCHITECTURE.md` §4 [2]）指定 [2] 以 **BeautifulSoup 解析入口頁側邊欄導覽**，從 `entry_url` 取得所有子頁面 URL。實作前對 `guide.appliedenergistics.org` 做實證探查，發現該假設不成立。

## 2. 問題分析（實測數據）

站台是 **Next.js App Router SPA**（`/_next/static/chunks/app/[versionSlug]/[...pagePath]/page-*.js`），伺服器只預渲染骨架：

| 觀察 | 結果 |
| --- | --- |
| 入口頁 `<aside>` 側邊欄連結數 | **6**（3 章節索引 + getting-started + tips-and-tricks + index），**不含任何子頁** |
| 側邊欄行為 | **情境式展開**：只有「當前所在章節」才展開子頁，無法從入口頁一次取得全貌 |
| `ae2-mechanics` 索引頁 `<main>` 子頁 | 15／15 完整 |
| `example-setups` 索引頁 `<main>` 子頁 | 21／21 完整 |
| `items-blocks-machines` 索引頁 `<main>` 子頁 | **1／86**——該頁為 **client-side rendering**，伺服器 HTML 只剩 `<span>Unknown category: devices</span>` 等 5 個占位字串，真正的 85 個物品連結由 JS 動態填入 |
| **側邊欄 BFS 總涵蓋** | **39／124**（漏 85 頁，佔知識庫內容 69%） |
| `items-blocks-machines-index` 單頁 DFS 補齊 | **1 頁**——索引頁本身無可跟隨的子頁連結，DFS 無法自我引導 |

`requests + BeautifulSoup`（無 JS 引擎）**無法**從伺服器 HTML 取得完整清單。缺口不是 selector 寫錯，而是資料根本不在伺服器渲染的 HTML 裡。

## 3. 決策

**以 `sitemap.xml` 為 [2] 的頁面 URL 真值來源；廢除側邊欄爬取，且不保留任何 fallback。**

發現流程（robust，不寫死路徑）：

1. 由 `entry_url` 推導站台根，抓 `robots.txt`，找所有 `Sitemap:` 宣告 → 用該位置。
2. 無宣告 → 依序試 `/sitemap.xml`、`/sitemap_index.xml`、`/sitemap-index.xml`。
3. 判定標準：HTTP 200 **且** body 根節點為 `<urlset>` 或 `<sitemapindex>`。
4. 皆失敗 → **fail-fast「此站台無可用 sitemap」**，不回退任何導覽爬取。
5. `<sitemapindex>` → 遞迴抓每個子 sitemap 後合併；`<urlset>` → 直接取 `<loc>`。
6. 版本過濾：`urlparse(url).path.startswith(f"/{version}/")`（**帶尾斜槓**，避免 `1.21.10` 誤判）；排除入口頁 `/{version}/index`。

驗證數據（2026-09-27 實測）：

- `robots.txt` 宣告 `https://guide.appliedenergistics.org/sitemap.xml`
- 根節點 `<urlset>`（單層）
- 全站 `<loc>` 1,427（含所有版本）；`1.21.1` 過濾後 **125**；排除入口頁後 **124**
- 無查詢字串、錨點、結尾斜線雜質；1.21.1 集合內無重複 URL

## 4. 為何否決 flight data 方案

探查過程中發現入口頁的 Next.js flight data（`self.__next_f.push([1, "..."])` 內嵌的 RSC payload）含完整 `navigationNodes` 樹：**單一請求即含全部 125 頁**，與 sitemap 雙向差集為空。最終仍否決，理由：

1. **循環驗證**：flight data 的完整性只能靠 sitemap 獨立驗證；若以它為主來源，等於失去獨立真值，驗證循環。
2. **內部格式耦合**：flight data 是 Next.js 的**內部序列化格式**（stream id、`$Lb`、`$undefined` 等），無穩定 API 保證；站方改版或 Next.js 升級即可能破壞，且無文件。
3. **無附加價值**：sitemap 已提供相同 URL 集合，且是站台**主動對外宣告**的標準介面。flight data 唯一優點（少一次請求）不足以換取耦合風險。

flight data 保留為**交叉驗證用途**（本 ADR 即以它確認 sitemap 完整性），不作為 pipeline 來源。

## 5. 為何否決側邊欄 BFS 與混合方案

- **側邊欄 BFS（字面照契約）**：39／124，`items-blocks-machines` 章 85 頁全漏，資料不完整，直接否決。
- **混合（BFS 為主 + sitemap 補齊）**：最終集合與純 sitemap 相同，但多維護一套探索邏輯與額外請求；兩套來源併存會讓「真值」定義模糊，日後維護與除錯成本高於收益。

## 6. 後果與影響

- **`sources.json` 不變**：`entry_url` 職責縮為「推導站台根」（版本由 `sources.json` 的 `version` 欄位給定，不由入口頁推導），仍是整條 URL 鏈的起點；`exclude`／`include` 欄位保留於 schema 但 [2] 目前不讀取（過濾發生在版本層）。
- **`_manifest.json` 新增 `source: "sitemap"` 欄位**記錄發現來源，`urls[]` 每項含 `url`、`chapter`、`page_slug`、`local_path`、`http_status`。
- **`BeautifulSoup` 仍保留於依賴**，但職責改為 [3] 的 leaf page 連結密度計算（navigation_only 判定），**不用於導覽發現**。trafilatura 自行解析 raw HTML（直接吃字串），BeautifulSoup 不是它的前置解析器。
- **[3] 連結密度只算 `<article>`，不算整頁**（2026-09-27 實測，留檔原因：這是「整頁算密度」在 SSR 帶側邊欄站台上的系統性誤殺案例）。本站台每頁帶情境式展開側邊欄（最多 91 連結），對整頁 HTML 算密度時，短內容頁（物品／配方頁）被側邊欄拖高至 0.84–0.86 而遭誤殺（`certus_quartz_dust`／`quartz_glass`／`crank`，真內容頁）；限縮 `<article>` 後同批頁降為 0.00。閾值 0.5 依兩群分離選定：`-index` 頁 0.93／0.97 vs 非 index 121 頁最高 0.44，`0.44 < 0.5 < 0.93` 無重疊。完整規則表與 reason 字串見 `ARCHITECTURE.md` §4 [3]。
- **無新依賴**：`xml.etree.ElementTree` 為 Python 標準庫。
- **`*-index` 章節索引頁**：sitemap 含此 3 頁，[2] 照抓，[3] 以 navigation_only 規則跳過（其 trafilatura 抽出為純標題拼接，無知識內容）。
- **失效模式**：站方移除 sitemap 或改變 robots 宣告 → [2] fail-fast 並明確報錯，優於靜默漏資料。

## 7. 相關文件

- `ARCHITECTURE.md` §4 [1]／[2]
- `AGENTS.md` §6 Pipeline Contract、§8 Technical Constraints
