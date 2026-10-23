# 清理

> 職責：過濾 trafilatura 誤留的噪音、正規化標題層級，輸出含 frontmatter 的乾淨 Markdown。規則只作用於正文；`title`、`source` 原封傳遞。
> 上一個階段：[抽取](02_extract.md)；下一個階段：[切分](04_chunk.md)

程式：`src/clean_pages.py`

## 1. 輸入與輸出

### 輸入

- `data/processed/extracted/<version>/**/*.json`：只讀 `title`／`source`／`markdown`（格式見 [02_extract.md](02_extract.md)）；缺 `markdown` 視為例外。
- `sources.json`：版本與模組（共用設定）。

### 輸出

**cleaned MD**（`data/processed/cleaned/<version>/<mod_slug>/<chapter>/<page_slug>.md`）：

```markdown
---
title: Terminals
source_url: "https://guide.appliedenergistics.org/1.21.1/items-blocks-machines/terminals"
---

# Terminals

While ME Pattern Providers, ... There are several variants with differing functions.
## Terminal Placement
As a terminal is often the first subpart someone might place, ...
## Crafting Terminal
### The UI
...
```

（範例為示意。）

- frontmatter 至少含 `title`、`source_url`，值由 extracted JSON 原封寫入（`_yaml_scalar` 序列化）；frontmatter 與 H1 的 `title` 一致，不一致時以 frontmatter 為準。
- 每頁恰好一個 `#`（由 `title` 寫入）；章節為 `##`／`###`／`####`，每個標題底下必有內容。
- frontmatter 與 `# <title>` 之間、`# <title>` 與正文之間各一個空行；正文段落之間沒有空行（trafilatura json 模式不保留段落）。
- UTF-8、LF、檔尾單一換行。
- 結構性 metadata（版本／模組／章節／頁面）以目錄路徑為準；frontmatter 若含這些欄位，只供人類閱讀。

**報告**：`reports/cleaning_report.md`（覆寫，不入版控）。內容包含：

- 對帳：輸出 + 跳過 + 例外 = 輸入
- 各規則命中數、R6 各層級標題數、R7 刪除的標題
- 跳過頁清單、標籤刪除摘要、孤立 `-` 計數、疑似新標籤（只列不刪）、警告附錄

**目錄擁有權**：`cleaned/<version>/` 由本階段擁有。全部頁面在記憶體處理完、且至少一頁有產出後，才清空並重建；路徑斷言限定該版本子樹，不動 `cleaned/.gitkeep` 與其他階段的目錄。

## 2. 處理方法

所有規則以「**去掉標題記號後的行內容**」比對，標題行與一般行套用同一套規則。R2 判定與字元統計以去掉記號的純文字計算。

| 順序 | 規則 | 定義 | 參數 |
| --- | --- | --- | --- |
| 0 | 前置條件 | `title` 或 `source` 為空 → 不輸出，記入報告 | — |
| 1 | **R2 站名首行警告** | 首行（去空白）== 站名 → **照常輸出**，報告列為警告（可能是跳轉頁）。不排除、不看字數；跳轉頁由 [抽取](02_extract.md) 列出候選，人工複核後再決定是否排除 | 站名 `Applied Energistics 2` |
| 2 | **R1 首行標題去重** | A：首行（含 `# <title>`）== title → 刪首行；B：首行以 title 開頭且更長 → 切掉 title 前綴（守衛：剩餘首字元須為大寫 ASCII，否則不切並警告）；C：次行 == title 且首行不是站名 → 刪次行。頁內其他位置的同名文字不動 | — |
| 3 | **R4a 整行標籤** | 整行（去前後空白）**完全等於**白名單標籤 → 刪該行；標題行一併適用（如 `## Recipe`） | 白名單 9 詞 |
| 4 | **R4b 黏合尾端標籤** | 只作用於**整頁黏成單行**的頁：自第一個黏在前文之後（前一字元不是空白）的 `Recipe`／`Recipes` 起到行尾，能被完整切成白名單 token → 切除。長 token 優先、token 間容許單一空格、區分大小寫、只處理行尾；切除後該行必須仍有內容，否則不切並警告 | 同白名單 |
| 5 | **R6 標題層級正規化** | 以堆疊追蹤祖先標題，輸出層級 = 2 + 祖先數：一般頁 h2 → `##`、其下 h3 → `###`；多 H1 頁的頁內 H1 → `##`、其下 H2 → `###`；直屬頁面標題的 H2 仍為 `##`。每頁只保留寫檔時的 `# <title>` | — |
| 6 | **R7 空章節移除** | 標題範圍（到下一個同層或更高層標題為止）內沒有任何非空白的非標題行 → 刪除該標題；由深到淺反覆判定，只含空子章節的章節也一併刪除 | — |
| 7 | **空 body 守衛** | 處理後 body 為空 → 不輸出，記入報告；不足 200 字元 → 照常輸出，報告標示 | 200 |

白名單（長 token 優先排序）：`Crafting (Shapeless)`、`Throw in Water`、`Inscriber`、`Crafting`、`Smelting`、`Smithing`、`Recipes`、`Charger`、`Recipe`。

**不處理**（只計數或記錄）：孤立 `-`、句子之間的黏合、相鄰表格、段落空行。

**失敗處理**：讀取或處理例外 → 逐頁隔離、記入報告、exit 1；沒有任何頁產出 → 中止、不清空既有輸出、exit 1。

## 3. 為什麼這樣做

### 前提：無圖片版本

本站以圖片呈現配方（合成格、材料、結果）。trafilatura 只抽文字節點，圖片被拿掉後，配方區塊只剩「配方類型標籤」這層空殼（`Recipe`、`Crafting`、`Inscriber`…）。規則專清這層空殼，**依本批資料校準**；網站加入新的圖片相關內容，或 [抽取](02_extract.md) 改為抽取圖片屬性時，必須重新盤點。

### 噪音型態（對 121 頁 extracted JSON 唯讀盤點，2026-10-11～10-17）

| 噪音型態 | 實測 | 根因 |
| --- | --- | --- |
| 跳轉頁 | 2 頁（`ae2-mechanics/p2p-tunnels` 77 字元、`ae2-mechanics/quantum-bridge` 103 字元）：首行為站名，正文只有「已搬到某頁」與版本選單殘留 | 站方以短頁指向正式頁面 |
| 首行重複標題 | A 型（首行 == title）97 頁、B 型（title 黏在首句前）21 頁、C 型（次行 == title，首行為版本宣告）1 頁（`other/getting-started`） | trafilatura 把頁內 H1 當正文保留 |
| 整行配方標籤 | 44 頁 174 行：通用標籤 151 行（`Crafting`／`Recipe`／`Recipes`／`Crafting (Shapeless)`）、製法標籤 23 行（`Inscriber`／`Smithing`／`Throw in Water`／`Smelting`／`Charger`） | 配方圖片被拿掉，只剩類型標籤文字 |
| 黏合尾端標籤 | 21 頁整頁黏成單行；其中 19 頁行尾自第一個黏合 `Recipe`／`Recipes` 起全為標籤詞，0 頁不符 | 同上，且該頁沒有換行 |
| 孤立 `-` | 12 頁 56 處 | 徽章圖被拿掉後只剩項目符號 |
| 版本選單殘留 | `Minecraft 1.21.1 [` 只出現在 2 個跳轉頁；raw HTML 0/124 | mkdocs-versioning 的 JS 注入，只在跳轉頁被序列化 |

**白名單的結構依據**：raw HTML 中配方區塊 `recipe_recipeBoxLayout` 的第一個 div 是「配方類型欄」（`<img aria-description="Crafting Table">` + 文字 `Crafting`），白名單就對應這個 DOM 位置，不是任意挑選。`guide` 頁的 ` Charger` 位於同一結構位置，所以判為標籤。

### 為什麼先刪頁面標題、再由 `title` 寫回 H1

正文裡的頁面標題有三種形式（A 獨立一行、B 黏在第一句前、C 在第二行），不可靠；`title` 欄位可靠。所以 R1 先統一移除，寫檔時再由 `title` 寫入唯一的 `# <title>`，確保每頁恰好一個 H1，且與 frontmatter 一致。

### R6：標題層級正規化

[抽取](02_extract.md) 標上的是 HTML 原始層級；11 頁有多個 H1（例如 `terminals` 每個子終端各一個 H1）。依相對深度輸出，才能讓每頁只有一個 `#`、章節從 `##` 開始，且不產生沒有上層的 `###`。最初的「依層級排序」寫法會把 `terminals` 直屬頁面的 `Terminal Placement` 變成孤立的 `###`，因此改為堆疊判定。

### R7：空章節移除

R4a 刪光標籤後，若章節底下原本只有標籤，就只剩一行標題。空章節是去噪的殘留，屬於本階段的職責；[切分](04_chunk.md) 只負責切分，不處理資料品質。實測（2026-10-23）只有 1 例：`items-blocks-machines/certus_quartz_crystal` 的 `## Some Alternate Recipes`（底下原本是 `Crafting (Shapeless)`、`Throw in Water`）。

### 人工裁定紀錄

清理規則須由人工裁定（`AGENTS.md` §10、§16）。

| 日期 | 事項 | 裁定 |
| --- | --- | --- |
| 2026-10-17 | R2 門檻 | **110**（安全窗口 104–114：最長跳轉頁 103、最短內容頁 114）；另加安全網：首行為站名卻未被排除的頁，報告列為警告 |
| 2026-10-17 | 保護標題的機械檢查基準 | 含標籤字樣、長度 ≤ 40 的 21 行集合（16 行須存活於輸出，5 行為 R1 移除的首行標題）；廣域保護由「純刪除檢查」負責 |
| 2026-10-17 | R4b 實作要求 | 長 token 優先；容許 token 間單一空格；區分大小寫；只處理行尾；切除後該行必須仍有內容 |
| 2026-10-17 | 刪除授權 | 只限本階段重建 `cleaned/<version>/`（範圍限定、路徑斷言、處理完成後才清空）；其他階段須另行授權 |
| 2026-10-17 | 驗收方式 | 被排除的頁不得產出檔案，以報告為憑；加入對帳：輸出頁數 + 報告列出的跳過頁數 = 輸入頁數 |
| 2026-10-17 | 重建範圍 | `cleaned/<version>/`，不動 `cleaned/` 根目錄的 `.gitkeep` |
| 2026-10-17 | 孤立 `-` | 不還原編號、不接回內容；只計數 |
| 2026-10-17 | ` Charger`（`guide` 頁） | 判為標籤（DOM 結構與其他配方類型欄相同） |
| 2026-10-17 | 是否回抽取階段重抽 | 不重抽（見否決的方案） |
| 2026-10-22 | 標題結構 | 改讀 `markdown`、規則以去記號內容比對；新增 R6 |
| 2026-10-23 | 空章節 | 由本階段處理，新增 R7 |
| 2026-10-23 | R2 | **不以字數判斷**（短的物品／配方頁很多，字數會隨站台格式改變）。R2 改為只警告、不排除；跳轉頁改由抽取以 HTML 結構列出候選，人工複核確認後再排除。取代 2026-10-17 的門檻 110 |

## 4. 否決的方案

- **回抽取階段改 `output_format="markdown"` 來修噪音**：能產生 `##`，但不修復黏合、標籤殘留與孤立 `-`，且新增 24 頁無 H1、17 頁多 H1；改抽取屬於契約變更，收益不足。（標題結構另以 [抽取](02_extract.md) 的標題對應解決。）
- **錨點後全刪**（自 `Recipe` 起刪到配方區塊結束）：會誤刪 `Recursive Recipes`、`The Crafting CPU`、`Crafting Unit` 等合法小標題；改採整行精確白名單。
- **對多行頁也套用 R4b**：全庫唯一的多行行尾標籤序列是 `condenser` 的合法小標題 `Settings/Recipes`，套用會誤刪；所以 R4b 只作用於整頁單行的頁。
- **由切分階段略過空章節**：會讓切分承擔資料清理，越過階段邊界，cleaned MD 也會留下不完整的結構。

## 5. 驗證方式

執行 `python src/clean_pages.py`：

- `cleaned/*.md` 產出、非空，含 frontmatter（至少 `title`、`source_url`），frontmatter 與 `# <title>` 之間有空行。
- 每頁恰好一個 `#`；沒有白名單標籤的標題行；沒有空章節。
- 被排除的頁不產出檔案，以報告為憑；**對帳：輸出頁數 + 報告列出的跳過頁數 = 輸入頁數**。
- **純刪除檢查**：輸出的每一行去掉標題記號後，是某個輸入行或其子字串。
- 連跑兩次，輸出位元組相同（冪等）。

最近一次驗證結果（2026-10-23，站台改為靜態 HTML 後重新抓取，見 [T8](07_troubleshooting.md#t8-站台建置方式改變內容未更新)）：輸出 119 + 跳過 0 = 輸入 119，例外 0（2 個跳轉頁已依 `sources.json` 的 `exclude` 在抽取跳過）；R2 警告 0 頁；R1 A 96、B 21、C 1；R4a 23 頁 67 行；R4b 19 頁 19 處；R6 69 頁含小標題（`##` 187、`###` 40）；R7 0 個；冪等通過。

前一版（Next.js HTML，2026-10-23 稍早）：輸出 119 + 跳過 2（R2 依字數排除跳轉頁）；R1 A 97、B 21、C 1；R4a 44 頁 174 行；R6 `##` 187；R7 1 個。保護標題 16/16 存活的檢查為 2026-10-17 的結果。

**注意**：R4a 命中從 174 行降為 67 行，代表新 HTML 下配方標籤的形態改變，白名單與 R4b 的前提需要重新盤點（待定）。

## 6. 已知影響與限制

- **製法資訊轉移**：製法標籤刪除後，「某物以何種機器製作」只存在於報告與 extracted JSON，不進知識庫。
- **R1-B 與 R4b 會改變正文字元內容**：屬於正文清理，不涉及 `title`／`source`。
- **極短頁**：部分物品頁刪標籤後不足 200 字元，照常輸出並在報告標示。
- **跳轉頁由抽取排除**：經人工確認並列入 `sources.json` 的 `exclude` 後，在抽取跳過，不會進入本階段；新出現的候選在確認前仍會輸出，並由 R2 警告。
- **白名單的有效期**：白名單依本批資料校準；站方新增配方類型或改版時須重驗（站台已於 2026-10-23 改為靜態 HTML，待重新盤點）。
- **配方材料的取回方向（未來）**：材料在 raw HTML 配方區塊 `recipe_ingredientBox` 內 `<img>` 的 `aria-description` 屬性中（複核 5 頁：`crank`、`fluix_pearl`、`guide`、`inscriber`、`quartz_glass`，5/5 皆有配方區塊；例如 `crank` 的材料為 `Stick`×4、`Copper Ingot`，結果 `Wooden Crank`；`guide` 的材料為 `Book`，結果 `Guide`；材料欄的最後一個值為產出物）。若要取回，須在 [抽取](02_extract.md) 新增屬性抽取，屬契約變更。
