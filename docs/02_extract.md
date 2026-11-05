# 抽取

> 職責：用 trafilatura 從 raw HTML 抽出主文（輸入先由 BeautifulSoup 整理），辨識頁內標題結構，解析配方，跳過只有導覽的頁面。
> 上一個階段：[來源設定與抓取](01_fetch.md)；下一個階段：[清理](03_clean.md)

程式：`src/extract_pages.py`

## 1. 輸入與輸出

### 輸入

- `data/raw/<version>/<mod_slug>/<chapter>/*.html`
- `data/raw/_manifest.json`（取 `http_status`、`local_path`；格式見 [01_fetch.md](01_fetch.md)）
- `sources.json` 的 `exclude`（共用設定；人工確認要排除的網址）

### 輸出

**extracted JSON**（`data/processed/extracted/<version>/<mod_slug>/<chapter>/<page_slug>.json`）：

```json
{
  "title": "Terminals",
  "text": "Terminals\nWhile ME Pattern Providers, ...\nTerminal Placement\n...\nCrafting Terminal\nThe UI\nRecipe\n...",
  "source": "https://guide.appliedenergistics.org/1.21.1/items-blocks-machines/terminals",
  "hostname": "appliedenergistics.org",
  "markdown": "# Terminals\nWhile ME Pattern Providers, ...\n## Terminal Placement\n...\n# Crafting Terminal\n## The UI\n## Recipe\n...",
  "recipes": [
    {"label": "Crafting", "station": "Crafting Table", "shapeless": false,
     "ingredients": [{"name": "...", "count": 1}], "slots": null, "result": "..."}
  ],
  "http_status": 200
}
```

（範例為示意，`...` 表示省略。）

| 欄位 | 規則 |
| --- | --- |
| `title`／`source`／`hostname` | trafilatura 讀**整頁** HTML 的原值，**不異動**；`hostname` 實際為 `appliedenergistics.org`，也不修正 |
| `text` | trafilatura 讀 **BS4 整理後的 `#page-content`**（見處理方法步驟 2）的結果，抽出後**不異動**；沒有 `#page-content` 或整理後抽不出時，退回整頁抽取的 `text` |
| `markdown` | 等於 `text` 加上標題記號；去掉記號後逐行等於 `text` |
| `recipes` | 配方區塊的結構化結果（見下表）；沒有配方的頁為空清單 |
| `http_status` | 由 `_manifest.json` 帶入 |

`recipes` 每一筆：

| 欄位 | 內容 |
| --- | --- |
| `label` | 頁面上的類型文字（如 `Crafting`、`Crafting (Shapeless)`、`Inscriber`、`Throw in Water`、`Smelting`） |
| `station` | 類型圖示名稱（如 `Crafting Table`、`Inscriber`、`Furnace`、`Blast Furnace`、`Water`、`TNT`） |
| `shapeless` | 是否為無形狀合成 |
| `ingredients` | 一般配方的材料 `[{name, count}]`，依出現順序；數量 = 重複次數。使用槽位的配方為 `null` |
| `slots` | Inscriber（`top`／`middle`／`bottom`）與 Smithing（`template`／`base`／`addition`）的 `[[槽位, 名稱]]`；其他為 `null` |
| `result` | 產物名稱（不含數量） |

不加 `page_slug`／`chapter`：下游從目錄路徑讀。

**其他輸出**：

- `data/processed/extracted/_parse_report.json`：`{ parsed_count, skipped: [{url, reason}], warnings: [{url?, phase, error}], errors: [] }`。
  - `reason` 只能是 `url_ends_with_index`、`short_text_high_link_density`、`redirect_page`、`excluded_by_sources` 之一（`navigation_only` 是類別名稱，不是合法的 `reason` 值）。
  - `warnings` 記非致命問題（例如 .md 衍生物寫入失敗），不影響 exit code。
- `reports/extraction_report.md`：計數、**正文來源**（BS4 整理後抽取頁數、退回整頁抽取的頁清單、保留的 3D 場景說明數）、跳過頁、**跳轉頁候選清單（待人工複核）**、配方總數與各類型數量、無法解析的配方清單、空 `source`／`title` 警示、標題對應數與未對應清單（覆寫，不入版控）。
- `data/processed/extracted_readable/**/*.md` + `_index.md`：人類驗收用。路徑鏡像 JSON；內容為 front matter（`title`／`source`／`hostname`／`http_status`／`text_length`）+ `# {title}` + `text` 原文。真值以 JSON 為準；寫入失敗只記 warning；不入版控，可重產。

**目錄擁有權**：`extracted/<version>/` 與 `extracted_readable/<version>/` 由本階段擁有。全部頁處理完且**至少一頁產出**後，才清空並重建這兩個版本子樹，再寫入本次結果，所以被跳過的頁（導覽頁、`exclude`）不會留下前次的舊檔。路徑斷言限定這兩個版本子樹，不動根目錄的 `_parse_report.json`、`_index.md`、`.gitkeep` 與其他版本。

## 2. 處理方法

1. 從 manifest 取成功抓取的頁面（`local_path` 不為 null）。
   - 網址（去掉結尾 `/`）在 `sources.json` 的 `exclude` 中 → 跳過、不輸出：符合跳轉頁結構時 `reason` 為 `redirect_page`，否則為 `excluded_by_sources`。
2. **BS4 整理輸入，再 trafilatura 抽取**。BS4 只刪除或換掉元素，不產生文字；正文仍完全來自 trafilatura。
   - 整理（`prepare_article_html`）：
     1. 只取 `article #page-content`；
     2. 3D 場景說明（`data-scene-in-world-annotations` → `contentTemplateId` → `<template>`）改成清單，放在場景的位置；
     3. 刪除 `<template>`（提示框）、`div.recipe-container`（配方由步驟 5 處理）、`<img>`／`<svg>`；
     4. `span.minecraft-tooltip` 與 `<a>` 換成純文字（只留文字、去掉標籤）。
   - 抽取兩次：

   ```python
   # 第一次：整頁 HTML，取 title／source／hostname（並作為備援 text）
   trafilatura.extract(html, output_format="json", with_metadata=True, include_tables=True)
   # 第二次：整理後的 HTML，取 text（config：MIN_EXTRACTED_SIZE = 1）
   trafilatura.extract(prepared, output_format="json", include_tables=True, config=TEXT_CONFIG)
   ```

   - 第二次把 `MIN_EXTRACTED_SIZE` 設為 1（預設 250）：正文短於門檻時 trafilatura 會退回 baseline 抽取，baseline 會把區塊黏成一行。
   - 沒有 `#page-content` 或整理後抽不出 → 沿用第一次的 `text`，並列入報告的「退回整頁抽取」。

3. **navigation_only 判定**（命中即跳過，不輸出）。兩條規則為 OR，各有獨立的 `reason`，日後才能分辨是哪一條命中：

   | 規則 | 條件 | `reason` |
   | --- | --- | --- |
   | 規則一（URL） | URL path 去掉結尾 `/` 後以 `-index` 結尾 | `url_ends_with_index` |
   | 規則二（內容） | 抽出文字 < 200 字元 **且** `<article>` 內連結密度 > 0.5（文字長度以 BS4 整理後抽出的 `text` 計算；連結密度以整頁的 `<article>` 計算） | `short_text_high_link_density` |

   連結密度 = `<article>` 內 `<a>` 文字長度 ÷ `<article>` 可見文字長度；沒有 `<article>` 時視為不命中。
4. **尚未確認的跳轉頁候選（只列清單，不排除）**：`<article>` 去掉 h1 後**剛好一個連結**，且扣掉連結文字後**只剩 `See`** → 列入報告的「尚未確認的跳轉頁候選」，並標出指向的頁面是否也在輸出中。判定不看字數。人工複核確認後，把網址加入 `sources.json` 的 `exclude`，下次執行即會跳過（步驟 1）。
5. **配方**：讀 `<article>` 內每個 `div.recipeBoxLayout`，轉成 `recipes`（不處理圖片本身，只讀圖示的 `aria-description` 文字）：
   - 一般配方為「類型、材料格、箭頭、產物」4 欄：空格（`empty-ingredient-box`）與熔爐的火焰略過；材料依出現順序計數。
   - Inscriber 為 2 欄：第二欄的 `ae2-inscriber-top`／`middle`／`bottom`／`result` 槽位。
   - Smithing 的 3 個材料依序為 `template`、`base`、`addition`。
   - 缺類型、產物或材料的區塊記為「無法解析」，列入報告。
6. **標題結構**：讀 `<article>` 的 h1–h3（`get_text(" ", strip=True)`），依文件順序用游標往下，在 `text` 中找去前後空白後完全相同的行，加上 `'#' × 原層級 + ' '`，產生 `markdown`。
   - 找不到的標題不加記號、不移動游標，記入報告。
   - **不正規化層級、不判斷噪音**：這兩件事由 [清理](03_clean.md) 負責。
7. 寫出 JSON；JSON 成功後才寫 .md 衍生物；最後寫報告。

**失敗處理**：第一次 trafilatura 回傳 None → 記入 errors，其他頁繼續；缺 `http_status` 或 `text` 為空 → 報告標記；沒有任何頁產出 → 中止、不清空既有輸出、exit 1。

## 3. 為什麼這樣做

### 連結密度只算 `<article>`，閾值 0.5

本站每頁都帶情境式展開的側邊欄（最多 91 個連結）。若對整頁 HTML 計算密度，短內容頁（物品／配方頁）會被側邊欄拉高到 0.84–0.86 而被誤殺，例如 `certus_quartz_dust`、`quartz_glass`、`crank` 都是真內容頁；只算 `<article>` 後，同一批頁降為 0.00。

閾值依兩群分離選定（124 頁全量，2026-09-27）：`-index` 頁的 `<article>` 密度為 0.93／0.97；非 `-index` 的 121 頁最高 0.44（`p2p-tunnels` 0.440、`quantum-bridge` 0.431，其餘 ≤ 0.31）。`0.44 < 0.5 < 0.93`，沒有重疊。

2026-10-24 以靜態 HTML 重測：非索引頁最高 **0.45**（`quartz_block`），與 0.5 的餘裕變小。規則二仍以整頁 `<article>` 計算（不受 BS4 整理影響），日後若有內容頁逼近 0.5，須重新校準。

規則一不可省：`items-blocks-machines-index` 是 client-side rendering 頁，`<article>` 只有 354 字元的占位文字、**零連結**，規則二判定不命中，只能靠 URL 後綴命中。目前 3 個 `*-index` 頁全由規則一命中，規則二保留給日後「沒有 `-index` 後綴」的導覽頁。

### 由本階段辨識標題結構

下游要用章節切分（見 [切分](04_chunk.md)），需要頁內標題結構，但 trafilatura 的 json 模式不保留標題記號：標題文字還在 `text` 裡，只是變成普通的一行。層級資訊只存在 raw HTML 的 h1–h3。只有本階段看得到 HTML，所以由本階段把結構標回 `text`；正文仍完全來自 trafilatura。

實測（2026-10-22）：

- raw HTML 的 `<article>` 中，124 頁有 113 頁含 h2／h3（h1 153、h2 262、h3 24）；11 頁含多個 H1。
- 扣掉每頁第一個 H1 後共 310 個小標題：82 個是 `Recipe`／`Recipes` 配方標籤（由清理刪除）；其餘 **228 個全部依序對應成功**（13 個重複文字，如 `The UI` ×4，依出現順序對應）。
- 對應結果（舊 HTML，Next.js）：matched 373、unmatched 58。未對應的 58 個皆在預期內：21 個是標題黏在第一句前面的頁首 H1（由清理的 R1-B 處理），37 個是 `Recipe`／`Recipes`。228/228 為舊 HTML 的對應率。
- `title`／`text`／`source`／`hostname`／`http_status` 與加入此功能前比對，121 頁全數相同；人類可讀 .md 位元組相同。
- **最近一次（2026-10-24，靜態 HTML、BS4 整理輸入後）**：matched 360、unmatched 69。未對應的 69 個皆在預期內：68 個是 `Recipe`／`Recipes`（由清理 R4a 刪除），1 個是空章節 `Some Alternate Recipes`（由清理 R7 刪除）；頁首 H1 全數對應成功（標題不再黏在第一句前）。

### 跳轉頁以結構判定、先列清單

跳轉頁（例如 `ae2-mechanics/p2p-tunnels`、`quantum-bridge`）只有一段「See」加上指向正式頁面的連結。原本由清理以「首行是站名且字數 < 110」排除，但字數會隨站台格式改變（站台改為靜態 HTML 後，`quantum-bridge` 從 103 變成 130 字元），而且短的物品／配方頁很多，字數不是可靠的依據（2026-10-23 人工裁定）。

改由本階段看 HTML 結構：連結數必須剛好一個，且沒有任何說明文字。反例 `fluix_dust` 有 3 個連結與說明文字、`main-network`／`crank` 只有 1 個連結但有 138／141 字元的說明，都不會命中。對新舊兩種 HTML 全量掃描，都只命中上述 2 頁。

站台剛改變建置方式，先只列清單、人工複核，確認判定沒有誤算後再排除。2026-10-23 人工確認 `ae2-mechanics/p2p-tunnels`、`ae2-mechanics/quantum-bridge` 為跳轉頁，已加入 `exclude`；它們指向的最終頁 `items-blocks-machines/p2p_tunnels`、`items-blocks-machines/quantum_bridge` 保留。確認結果放在人工維護的 `sources.json`，而不是寫死在程式，以後新的跳轉頁仍須經人工確認才會排除。

### 配方轉為文字

配方以圖片呈現，trafilatura 只抽到「Recipe」「Crafting」這類標籤空殼；若不轉化，「X 怎麼做」這類查詢在知識庫中找不到任何材料資訊（2026-10-24 人工裁定納入）。HTML 的每個格子都以 `aria-description` 寫明物品名稱，所以只需解析 HTML，不需要圖片辨識，也不需要新依賴。

實測（2026-10-24，靜態 HTML）：85 頁共 246 個配方，全部解析成功（無法解析 0）；類型分布為 Crafting Table 210（其中有形狀 142、無形狀 68）、Inscriber 15、Water 8、Smithing Table 5、Charger 3、Furnace 3、Blast Furnace 1、TNT 1。有形狀的合成台保留 9 格（含空格），可重建擺放形狀，但目前只輸出材料計數（見待定事項）。

### 為什麼由 BS4 整理輸入（2026-10-24）

站台改為靜態 HTML 後，直接把整頁交給 trafilatura 會讓 21 頁的段落與清單黏成一行（例：`devices` 的清單變成 `ME InterfaceME Import Bus…`），另有 12 頁混入提示框的物品名稱。

**根因實驗**：
- 連結密集的區塊被 trafilatura 當成導覽處理，換行資訊丟失。把連結換成純文字後，`devices` 由 1 行變 8 行、`quartz_tools` 由 1 行變 13 行。
- 正文短於 `MIN_EXTRACTED_SIZE`（250）時，trafilatura 退回 baseline 抽取，同樣黏行；設為 1 即不退回。
- `<template>` 有兩種用途：滑鼠提示框（1,197 個，其文字被接成物品名稱雜訊）與 3D 場景說明（225 個，是正文的一部分，不能丟）。因此整理時分別處理：提示框模板刪除，場景說明改成清單放回場景位置。

**結果**（119 頁輸出）：

| 項目 | 整理前 | 整理後 |
| --- | --- | --- |
| 黏成單行的頁 | 21 | **0**（剩 17 頁單行，皆為 HTML 只有一段文字的頁） |
| 清單項目 | 404 | **624**（含 3D 場景說明 213 條） |
| 提示框物品名稱雜訊 | 12 頁 | **0** |
| 3D 場景說明 | — | 213/213 保留，位置在場景處 |
| 內容涵蓋率（以舊網站 trafilatura 為基準） | — | **99.1%**；少掉的字皆為配方標籤（`Crafting` 108、`Recipe` 25、`Shapeless` 17、`Inscriber` 15…） |

正文來源：BS4 整理後抽取 119 頁，退回整頁抽取 0 頁。`title`／`source`／`hostname`／`http_status` 與整理前 119/119 相同；`recipes` 119/119 相同（246 個，無法解析 0）；`markdown` 去標題記號後逐行等於 `text` 119/119。

**整理只限結構層級**：移除模板、配方區塊、圖片，把連結與提示框標籤換成純文字；不做文字層級的去噪（標籤、重複標題等仍由 [清理](03_clean.md) 負責）。

### 為什麼同時保留 `text` 與 `markdown`

`text` 是 trafilatura 對整理後輸入的輸出，用於比對與除錯（`markdown` 去掉記號後必須等於 `text`）；下游只讀 `markdown`。

## 4. 否決的方案

- **只用 trafilatura、不整理輸入**（2026-10-24 前的做法）：靜態 HTML 下 21 頁黏成單行、12 頁混入提示框物品名稱。
- **改用 `output_format="markdown"`**：會產生 `##`，但有 24 頁沒有 H1、17 頁有多個 H1，`Recipe` 會被升成 `## Recipe`，而且不修復黏合、標籤殘留與孤立 `-`；`include_formatting=True` 對 json 輸出幾乎無效。新 HTML 重測（2026-10-24）：單行 21、無 H1 22、多 H1 11、提示框雜訊 15，仍不可行。
- **只用 BS4 自寫 HTML→文字轉換**：回到自寫轉換器的維護風險，且要自行處理 trafilatura 已處理的表格、清單與空白規則。
- **先 trafilatura、再補換行**：換行資訊在抽取時已遺失，無法正確補回。
- **`favor_precision`**：效果接近，但改變的是 trafilatura 的抽取啟發式；調整最小長度門檻（`MIN_EXTRACTED_SIZE`）較單純。
- **其他 HTML→Markdown 套件**（markdownify、html2text、unstructured、docling）：屬於新依賴，而且要重新校準清理的全部規則；目前的做法不新增依賴（標題對應率見上方實測）。
- **由清理階段猜標題**（短行、無句號、後接句子）：會誤判合法短行，裸短行的語意無法單憑文字判定。
- **本階段只輸出標題清單、由清理補記號**：會輸出兩份要互相對照的資料，清理還得知道 trafilatura 的換行行為，違反單一職責。

## 5. 驗證方式

執行 `python src/extract_pages.py`：

- 每份 extracted JSON 可解析，含 `title`／`source`／非空 `text`／`markdown`。
- `markdown` 去掉標題記號後逐行等於 `text`。
- `extraction_report.md` 產出，標出 `source`（與 `title`）為空的頁，以及未對應的標題。
- `extracted_readable/*.md` 數 = `parsed_count`，`_index.md` 產出。
- `exclude` 中的網址都被跳過（`redirect_page` 或 `excluded_by_sources`）。
- 黏成單行的頁為 0，或已人工確認為只有一段文字的頁。
- 報告的「正文來源」列出退回整頁抽取的頁（預期 0；非 0 須逐頁確認原因）與保留的 3D 場景說明數。
- `title`／`source`／`hostname` 與上一次執行相同（整理輸入不得影響 metadata）。
- 報告列出尚未確認的跳轉頁候選；人工確認每一列確實是跳轉頁，且「指向頁已在輸出中」為「是」。
- 報告的配方總數與各類型數量合理，無法解析的配方為 0（或已人工確認）。
- 站方改版時，檢查報告中的未對應標題是否只有頁首 H1 與 `Recipe`／`Recipes`。

## 6. 待定事項

| 事項 | 狀態 |
| --- | --- |
| 配方的已知限制 | 輪流顯示的材料（`cycling`，共 78 格）只取第一個；產物數量（HTML 無此資訊）不輸出；擺放形狀不輸出；配方圖片留待未來直接使用。提示框模板內有輪流顯示材料的完整清單，可作為未來補完 `cycling` 的來源 |

（「新 HTML 下的抽取品質」已由 BS4 整理輸入解決，見 [T9](07_troubleshooting.md#t9-trafilatura-把段落與清單黏成一行)。）
