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
