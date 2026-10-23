# ADR-002：[4] 清理噪音規則（無圖片版本）

- **日期**：2026-10-17
- **狀態**：Accepted；§3「不處理：標題還原」與 §7.1「`section` 恆為空」已由 ADR-004 部分取代
- **影響階段**：[4] 清理（`src/clean_pages.py`）
- **替代方案**：回 [3] 改 `output_format="markdown"` 重抽、錨點後全刪的標籤匹配、對多行頁也套用行尾標籤切除

## 1. 背景

`ARCHITECTURE.md` 原把 [4] 噪音規則列為「不預先定義，待第一波資料後歸納」。[2]–[3] 跑通後，對 `data/processed/extracted/1.21.1/applied-energistics-2/` 全量 121 頁做唯讀盤點，歸納出本 ADR 的規則集。

**前提——無圖片版本**：本站以圖片呈現配方（合成格、材料、結果）。trafilatura 只抽文字節點，圖片被拿掉後，配方區塊只剩「配方類型標籤」這層空殼（`Recipe`、`Crafting`、`Inscriber`…）。本 ADR 的規則專清這層空殼，**依本批資料校準**；網站加入新的圖片相關內容，或 [3] 改為抽取圖片屬性時，必須重新盤點。

## 2. 問題分析（實測數據，2026-10-11～10-17）

| 噪音型態 | 實測 | 根因 |
| --- | --- | --- |
| 跳轉頁 | 2 頁（`ae2-mechanics/p2p-tunnels` 77 字元、`ae2-mechanics/quantum-bridge` 103 字元）首行為站名、正文只有「已搬到某頁」與版本選單殘留 | 站方以短頁指向正式頁面 |
| 首行重複標題 | A 型（首行 == title）97 頁、B 型（title 黏在首句前）21 頁、C 型（次行 == title，首行為版本宣告）1 頁（`other/getting-started`） | trafilatura 把頁內 H1 當正文保留 |
| 整行配方標籤 | 44 頁 174 行；通用標籤 151 行（`Crafting`／`Recipe`／`Recipes`／`Crafting (Shapeless)`）、製法標籤 23 行（`Inscriber`／`Smithing`／`Throw in Water`／`Smelting`／`Charger`） | 配方圖片被拿掉，只剩類型標籤文字 |
| 黏合尾端標籤 | 21 頁整頁黏成單行；其中 19 頁行尾自第一個黏合 `Recipe`／`Recipes` 起全為標籤詞，0 頁不符 | 同上，且該頁無換行 |
| 孤立 `-` | 12 頁 56 處 | 徽章圖被拿掉後剩項目符號 |
| 版本選單殘留 | `Minecraft 1.21.1 [` 只在 2 個跳轉頁；raw HTML 0/124 | mkdocs-versioning 的 JS 注入，只在跳轉頁被序列化 |

**標籤白名單的結構依據**：raw HTML 中配方區塊 `recipe_recipeBoxLayout` 的第一個 div 為「配方類型欄」（`<img aria-description="Crafting Table">` + 文字 `Crafting`），白名單即對應這個 DOM 位置，非任意挑選。`guide` 頁的 ` Charger` 位於同一結構位置，故判為標籤。

## 3. 決策

規則集依序執行（`R2 → R1 → R4a → R4b → 空 body 守衛`），**只作用於 `text` 正文**；`title`、`source` 全程原封傳遞（資料不異動）。

| 規則 | 定義 | 參數 |
| --- | --- | --- |
| 前置條件 | `title` 或 `source` 為空 → 該頁不輸出，記入報告 | — |
| **R2 跳轉頁排除** | 首行（去空白）== 站名 **且** 全頁字元數 < 門檻 → 不輸出，記入報告 | 站名 `Applied Energistics 2`；門檻 **110** |
| R2 安全網 | 首行 == 站名但未達排除條件 → 照常輸出，報告列為警告 | — |
| **R1 首行標題去重** | A：首行 == title → 刪首行；B：首行以 title 開頭且更長 → 切掉 title 前綴（守衛：剩餘首字元須為大寫 ASCII，否則不切並警告）；C：次行 == title 且首行非站名 → 刪次行。頁內其他位置的同名文字不動 | — |
| **R4a 整行標籤** | 整行（去前後空白）**完全等於**白名單標籤 → 刪該行 | 白名單 9 詞（見下） |
| **R4b 黏合尾端標籤** | 僅作用於**整頁黏成單行**的頁；自第一個黏在前文之後（前一字元非空白）的 `Recipe`／`Recipes` 起到行尾，能被完整切成白名單 token → 切除。**長 token 優先匹配**、token 間容許單一空格、區分大小寫、只處理行尾；切除後該行必須仍有內容，否則不切並警告 | 同白名單 |
| **空 body 守衛** | 規則處理後 body 為空 → 不輸出，記入報告；不足 200 字元 → 照常輸出，報告標示 | 200 |

白名單（長 token 優先排序）：`Crafting (Shapeless)`、`Throw in Water`、`Inscriber`、`Crafting`、`Smelting`、`Smithing`、`Recipes`、`Charger`、`Recipe`。

**輸出與重建**：

- cleaned MD 格式：frontmatter（`title`、`source_url`，`_yaml_scalar` 序列化）→ 空行 → `# <title>` → 空行 → body；UTF-8、**LF**、檔尾單一換行。
- `data/processed/cleaned/<version>/` 由 [4] 擁有：全部頁先在記憶體處理完、確認至少有一頁產出後，才清空並重建該版本子樹；路徑斷言限定為 `cleaned/<version>/`，不動 `cleaned/.gitkeep` 與其他階段目錄。
- `reports/cleaning_report.md` 每次覆蓋；含對帳（輸出 + 跳過 + 例外 = 輸入）、各規則命中、跳過頁清單、標籤刪除摘要、孤立 `-` 計數、疑似新標籤（只列不刪）、警告附錄。

**不處理（只計數或記錄）**：孤立 `-`、句子之間的黏合、相鄰表格、標題還原（`##`）、段落空行。

## 4. 人工裁定紀錄

AGENTS.md §10／§16 規定 [4] 噪音規則須由人工裁定。以下為 2026-10-17 階段 A 驗證後的裁定：

| # | 事項 | 裁定 |
| --- | --- | --- |
| 1 | R2 門檻 | **110**（安全窗口 104–114：最長跳轉頁 103、最短內容頁 114）。另加安全網：首行為站名卻未被排除的頁，報告列為警告 |
| 2 | 保護標題機械檢查基準 | 含標籤字樣、長度 ≤ 40 的 **21 行集合**（其中 16 行須存活於輸出，5 行為 R1 移除的首行標題）；廣域保護由「純刪除檢查」負責（輸出每一行皆為輸入某行的子字串） |
| 3 | R4b 實作要求 | 長 token 優先；容許 token 間單一空格；區分大小寫；只處理行尾；切除後該行必須仍有內容 |
| 4 | AGENTS.md §9 刪除授權 | 縮小版例外：僅限 [4] 重建 `cleaned/<version>/`（範圍限定、設路徑斷言、處理完成後才清空）；其他階段須另行授權 |
| 5 | AGENTS.md §13 [4] 驗收 | 被契約排除的頁不得產出檔案，以報告為憑；加對帳：輸出頁數 + 報告列出的跳過頁數 = 輸入頁數 |
| 6 | 重建範圍 | `cleaned/<version>/`，不動 `cleaned/` 根目錄的 `.gitkeep` |
| 7 | 孤立 `-` | 不還原編號、不接回內容；只計數 |
| 8 | ` Charger`（`guide` 頁） | 判為標籤（DOM 結構與其他配方類型欄相同） |
| 9 | 是否回 [3] 重抽 | 不重抽（見 §5） |

## 5. 否決方案

- **回 [3] 改 `output_format="markdown"`**：實測可產生 `##`，但不修復黏合、標籤殘留與孤立 `-`，且新增 24 頁無 H1、17 頁多 H1；`include_formatting=True` 對 json 輸出幾乎無效。改 [3] 屬契約變更，收益不足。
- **錨點後全刪（自 `Recipe` 起刪到配方區塊結束）**：會誤刪 `Recursive Recipes`、`The Crafting CPU`、`Crafting Unit` 等合法小標題；改採整行精確白名單。
- **對多行頁也套用 R4b**：全庫唯一的多行行尾標籤序列是 `condenser` 的合法小標題 `Settings/Recipes`；套用會誤刪，故 R4b 只作用於整頁黏成單行的頁。

## 6. 驗證結果（2026-10-17）

| 檢查 | 結果 |
| --- | --- |
| 對帳 | 輸出 119 + 跳過 2（皆為 R2 跳轉頁）= 輸入 121；例外 0 |
| R1 型別 | A 97、B 21、C 1；B 型守衛 21/21 通過 |
| R4a | 44 頁 174 行 |
| R4b | 19 頁 19 處；切空警告 0 |
| R2 安全網警告 | 0 |
| 保護標題 | 16/16 存活 |
| 純刪除檢查、整行標籤殘留、`title`／`source` 原封、LF、frontmatter 格式 | 全數通過 |
| 冪等 | 連跑 3 次，cleaned MD 與報告位元組一致 |

## 7. 後果與影響

1. **`section` 恆為空**：全庫無 Markdown 標題記號、無段落空行，[5] 的 MarkdownHeaderTextSplitter 只會切出 H1；`section` 欄位在本批資料上恆空。
2. **製法資訊轉移**：製法標籤被刪後，「某物以何種機器製作」只存在於 `cleaning_report.md` 與 extracted JSON，不進知識庫。
3. **R1-B 與 R4b 改變 `text` 字元內容**：屬正文清理，不涉及 `title`／`source`，與「title 資料不異動」不衝突。
4. **極短頁**：部分物品頁刪標籤後不足 200 字元，照常輸出並在報告標示（RAG 回答可能只能引用很短的內容）。
5. **跳轉頁被排除**：指向這 2 頁的交叉引用在知識庫內沒有對應 chunk；其正式內容頁仍存在。
6. **門檻與白名單的有效期**：R2 門檻兩側餘裕只有 7／4 字元，白名單亦依本批校準；站方新增短頁、新配方類型或改版時須重驗。
7. **配方材料的取回方向（未來，非本 ADR 範圍）**：配方材料不在文字節點，而在 raw HTML 配方區塊 `recipe_ingredientBox` 內 `<img>` 的 `aria-description` 屬性。**初步複核 5 頁**（`items-blocks-machines/crank`、`fluix_pearl`、`guide`、`inscriber`、`quartz_glass`）：5/5 皆有配方區塊，配方類型欄 `aria-description` 為 `Crafting Table`／`Charger`，材料欄含材料名稱（如 `crank`：`Stick`×4、`Copper Ingot`，結果 `Wooden Crank`；`guide`：`Book`，結果 `Guide`）。注意材料欄的最後一個值為產出物。若日後要取回材料，須在 [3] 新增屬性抽取，屬 pipeline 契約變更，須另立 ADR 並經人工授權。

## 8. 相關文件

- `ARCHITECTURE.md` §5 [4]
- `AGENTS.md` §6 Pipeline Contract、§9 Sensitive Operations、§13 Validation Matrix
- `reports/cleaning_report.md`（每次執行的實際數字）
- `docs/adr/ADR-001-sitemap-as-url-source.md`
