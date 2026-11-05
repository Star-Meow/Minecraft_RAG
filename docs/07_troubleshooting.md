# 疑難排解

> 本文件只追加、不改寫：舊紀錄保留原樣，狀態變化時在該條目下補一行「更新」。

## 症狀速查

| 症狀 | 見 |
| --- | --- |
| 抓到的頁數遠少於預期 | [T1](#t1-側邊欄爬取只抓到-39124-頁) |
| 短的物品頁被判成導覽頁跳過 | [T2](#t2-短內容頁被誤判為導覽頁) |
| extracted JSON 沒有任何 `##` 標題 | [T3](#t3-trafilatura-json-模式丟失標題結構) |
| 想改用 trafilatura 的 markdown 輸出 | [T4](#t4-trafilatura-markdown-模式的副作用) |
| Windows 主控台輸出中文變成亂碼 | [T5](#t5-windows-主控台中文亂碼) |
| `git add` 出現 `LF will be replaced by CRLF` 警告 | [T6](#t6-git-的-crlf-警告) |
| `src/fetch_pages.py` 有失敗頁卻回傳 0 | [T7](#t7-抓取失敗時的結束碼與契約不符) |
| 重新抓取後頁數、跳過頁數、清理結果大幅改變，或出現 `other/.html.md` | [T8](#t8-站台建置方式改變內容未更新) |
| 抽取結果的段落與清單黏成一行，或混入提示框的物品名稱 | [T9](#t9-trafilatura-把段落與清單黏成一行) |

## T1 側邊欄爬取只抓到 39/124 頁

- **日期**：2026-09-27
- **現象**：解析入口頁側邊欄做 BFS，只得到 39 頁；`items-blocks-machines` 章 85 頁全漏。
- **根因**：站台是 Next.js SPA，側邊欄情境式展開；`items-blocks-machines` 索引頁為 client-side rendering，伺服器 HTML 沒有子頁連結。
- **處置**：改以 sitemap.xml 為 URL 真值來源（見 [01_fetch.md](01_fetch.md)）。
- **證據**：sitemap 中 1.21.1 共 125 個 URL，排除入口頁後 124 個。

## T2 短內容頁被誤判為導覽頁

- **日期**：2026-09-27
- **現象**：`certus_quartz_dust`、`quartz_glass`、`crank` 等真內容頁被規則二判為 navigation_only。
- **根因**：對整頁 HTML 計算連結密度時，側邊欄（最多 91 個連結）把短頁的密度拉高到 0.84–0.86。
- **處置**：連結密度只計算 `<article>`（見 [02_extract.md](02_extract.md)）；同批頁降為 0.00。

## T3 trafilatura json 模式丟失標題結構

- **日期**：2026-10-22
- **現象**：extracted JSON 與 cleaned MD 中，除頁首 H1 外沒有任何 `##`／`###`；切分時 `section` 恆為空。
- **根因**：trafilatura 的 json 輸出不保留標題記號，標題變成普通的一行；`include_formatting=True` 對 json 輸出幾乎無效。
- **處置**：由抽取階段讀 `<article>` 的 h1–h3，對應回 `text` 產生 `markdown` 欄位（見 [02_extract.md](02_extract.md)）。

## T4 trafilatura markdown 模式的副作用

- **日期**：2026-10-11
- **現象**：改用 `output_format="markdown"` 雖然出現 `##`，但 24 頁沒有 H1、17 頁有多個 H1，`Recipe` 被升為 `## Recipe`；黏合、標籤殘留、孤立 `-` 都沒有修好。
- **處置**：不採用（見 [02_extract.md](02_extract.md)、[03_clean.md](03_clean.md) 的否決方案）。

## T5 Windows 主控台中文亂碼

- **日期**：2026-10-23
- **現象**：在 Git Bash／PowerShell 執行 Python 時，中文輸出變成亂碼，或印出 `⏎` 等字元時出現 `UnicodeEncodeError`。
- **根因**：Windows 主控台預設編碼為 cp950；檔案本身是 UTF-8，不受影響。
- **處置**：需要在主控台看中文時，先設定 `PYTHONIOENCODING=utf-8`；報告檔以 UTF-8 寫入，直接開檔閱讀即可。

## T6 Git 的 CRLF 警告

- **日期**：2026-10-23
- **現象**：`git add` 時出現 `LF will be replaced by CRLF the next time Git touches it`。
- **根因**：Windows 上 Git 的換行轉換設定；工作目錄中的檔案為 LF。
- **處置**：目前只是警告，不影響內容；cleaned MD 的 LF 要求由程式寫檔時保證。若要消除警告，需另行決定 `.gitattributes` 的設定。

## T7 抓取失敗時的結束碼與契約不符

- **日期**：2026-10-22
- **現象**：契約寫「有失敗記錄時 exit 1」，但 `src/fetch_pages.py` 有失敗頁時仍回傳 0。
- **狀態**：待決定要改程式還是改契約（見 [01_fetch.md](01_fetch.md) 的待定事項）。
- **更新（2026-10-23）**：已改程式，有失敗頁時回傳 1，與契約一致。

## T8 站台建置方式改變（內容未更新）

- **日期**：2026-10-23
- **現象**：重新執行抓取後，下游結果大幅改變：
  - sitemap 全站 URL 1,427 → 1,547；1.21.1 為 125 個（含入口頁）。
  - 抽取：輸出／跳過 121／3 → 124／1；清理：輸出／跳過 119／2 → 123／1。
  - 出現 `other/.html.md`（入口頁被當成內容頁，`page_slug` 為空）。
  - `example-setups-index`、`items-blocks-machines-index` 進入知識庫；跳轉頁 `quantum-bridge` 未被排除。
  - 87 頁的抽取正文改變：23 頁換行消失、整段黏成一行；36 頁多出黏在一起的物品名稱；28 頁的配方標籤行消失。R4a 從 44 頁 174 行降為 23 頁 67 行；未對應標題 58 → 87。
  - 所有 `source_url` 結尾多了 `/`。
- **根因**：站台的建置方式改變，**指南內容沒有更新**。
  - 網址改為結尾帶 `/`（`.../ae2-mechanics/energy/`）；舊網址回應 301 轉址到新網址；入口頁由 `/1.21.1/index` 變為 `/1.21.1/`。
  - HTML 由 Next.js 輸出改為靜態 HTML，標記結構不同，trafilatura 的抽取結果跟著改變。
  - 程式未處理結尾 `/`：入口頁排除條件（`/1.21.1/index`）、路徑三元素解析、規則一（`-index` 結尾）都比對失敗。
- **證據**：
  - 124 頁的 `<article>` 文字比對：120 頁完全相同；其餘 4 頁只差站台產生的字串（`Unknown recipe type minecraft:blasting` → `Smelting`、`Unknown config value…` → `Error: no configuration values were exported` 等），以及 `items-blocks-machines-index` 改為伺服器端輸出物品清單。
  - 使用者人工檢視確認網站內容未更新。
- **處置**：目前資料保留新抓取的版本（未還原）。程式的錯誤處理與清理規則是否重新校準，待決定（見 [01_fetch.md](01_fetch.md)、[02_extract.md](02_extract.md)、[03_clean.md](03_clean.md)）。
- **更新（2026-10-24）**：已處理——抓取的入口頁排除與 `page_slug` 防護改為能處理結尾 `/`（[01_fetch.md](01_fetch.md)）；規則一改為去掉結尾 `/` 後比對；人工確認的跳轉頁以 `sources.json` 的 `exclude` 在抽取跳過；段落與清單黏行、提示框名稱雜訊由抽取改為 BS4 整理輸入解決（[T9](#t9-trafilatura-把段落與清單黏成一行)）。

## T9 trafilatura 把段落與清單黏成一行

- **日期**：2026-10-24
- **現象**：靜態 HTML 下，21 頁的段落與清單黏成單行（例：`devices` 的清單變成 `ME InterfaceME Import Bus…`）；12 頁混入提示框的物品名稱。
- **根因**：
  1. 連結密集的區塊被 trafilatura 當成導覽處理，換行資訊丟失。
  2. 正文短於 `MIN_EXTRACTED_SIZE`（250）時，trafilatura 退回 baseline 抽取，baseline 會把區塊黏成一行。
  3. 提示框的 `<template>` 文字被接進正文。
- **處置**：[抽取](02_extract.md) 改為 BS4 整理輸入（只取 `#page-content`、場景說明改清單、刪除模板／配方區塊／圖片、連結與提示框標籤換成純文字）後再 trafilatura 抽取，第二次抽取使用 `MIN_EXTRACTED_SIZE = 1`。
- **證據**：
  - 根因實驗：連結換成純文字後，`devices` 1 → 8 行、`quartz_tools` 1 → 13 行；短頁退回 baseline 而黏行。
  - 結果：黏成單行的頁 21 → 0（剩 17 頁單行皆為 HTML 只有一段文字的頁）；清單項目 404 → 624（含 3D 場景說明 213 條，213/213 保留）；提示框雜訊 12 頁 → 0；內容涵蓋率 99.1%（少掉的字皆為配方標籤）；`title`／`source`／`hostname`／`http_status`、`recipes` 與整理前 119/119 相同。
  - trafilatura markdown 模式在新 HTML 重測：單行 21、無 H1 22、多 H1 11、提示框雜訊 15，不可行（見 [02_extract.md](02_extract.md) 的否決的方案）。
