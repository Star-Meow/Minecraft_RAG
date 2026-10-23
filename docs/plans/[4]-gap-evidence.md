# [4] 清理階段計畫缺損調查——證據文件

調查日期：2026-10-11
資料範圍：`data/processed/extracted/1.21.1/applied-energistics-2/` 全量 121 頁 + `data/raw/` 全量 124 頁
執行環境：`H:/git/Minecraft_RAG/.venv/Scripts/python.exe`（Python 3.12.7）

## ⚠ 開頭警告：輸入文件不可得

本任務指定的兩份輸入**未在本儲存庫或已存取的 session 中找到**：

| 指定輸入 | 尋找結果 |
| --- | --- |
| 實作計畫（R1–R5、alias、Decisions Needed） | **未找到**。`docs/plans/` 原不存在；`src/` 只有 `fetch_pages.py`、`extract_pages.py`，無 `clean_pages.py`；`git ls-files` 追蹤的 .md 僅 `AGENTS.md`、`ARCHITECTURE.md`、`README.md`、`docs/adr/ADR-001`；`onetime-report.md` 無 R1–R5；`.zcode/plans/` 4 份計畫分屬 [2]–[3]、[6] 與重構，皆無 [4] 規則 |
| 外部審查結果（缺損 1–6） | **未找到**。無任何檔案含「缺損」相關內容；舊 session（`sess_25d44d9c`）提到 `architecture-assessment.md` 但該檔不在磁碟上 |

**後果**：本文件中 R1–R5 的**具體規則文字、alias 的定義、缺損 1–6 的原文皆無法引用**。凡需要引用計畫原文之處一律標「未取得」。可執行的部分是：從任務描述中**可辨識的線索**（「R4＝配方標籤規則」「R3＝單行合併／終止標點」「R1＝首行標題去重」「alias＝frontmatter 別名」）對 121 頁實測，產出**與計畫文字無關的客觀證據**。

四個已存取 session（`sess_1f512bcc`、`sess_25d44d9c`、`sess_854b5563`、`sess_eaa84c65`）皆已用 ReadSessionContext 查詢「R1–R5／alias／外部審查／缺損」，**全部回報無相關內容**。

---

## 摘要：各任務狀態一覽

| 任務 | 狀態 | 一句結論 |
| --- | --- | --- |
| T0 數字對齊 | **部分確認** | 「44 頁 174 行」可精確重現（`strip() ∈ LABELS`）；「53 頁 193 行」的**頁數**可重現（53）、**行數差 4 行**（見下） |
| T1 R4 反向驗證 | 已確認 | 候選集含**至少 8 個合法章節標題**；兩種匹配策略的誤刪／漏刪已量化 |
| T2 黏合式噪音 | 已確認 | 5 種黏合 token；`RecipesCrafting` **4/4 在行中而非行尾** → 行尾正則不足 |
| T3 規則順序 | 已確認（記憶體模擬，非 R1–R5 原文） | R1→R2→R3→R4 與 R1→R2→R4→R3 輸出**不同**，已在 terminals 定位首差 |
| T4 字元守恆 | 已確認 | 56 處空項目符號**全數通過**（內容恆為空） |
| T5 回 [3] 重抽 | **已確認（結論與假設相反）** | `include_formatting=True` 對 json 輸出**幾乎無效**；改 `output_format="markdown"` 才有 `##`，但**不修復黏合／標籤／游離 `-`**，且引入 24 頁無 H1、17 頁多 H1 |
| T6 alias 讀取端 | 已確認 | **無任何程式碼讀取 alias**（[5]/[6] 未實作） |
| T7 邊界與守衛 | 已確認 | stub 頁有 6 頁交叉引用；C 型頁 line0 為版本宣告 |
| T8 frontmatter／[5] 介面 | 已確認 | `_yaml_scalar` 對 121 title **0 失敗**；extracted_readable 為 **CRLF** |
| T9 fixtures 清單 | 已確認（清單，不建立檔案） | 14 個候選案例 |
| T10 契約措辭 | 已確認（草擬） | 規範語義版本，**不含批次數字** |
| T11 配方材料遺失 | 部分確認 | 4 頁完全無材料資訊；其餘為「材料在圖片裡」不可驗證 |
| T12 決策表 | 已確認 | 22 項，每項含選項／影響／證據 |

---

## T0 數字對齊

**狀態：部分確認**

### 兩個數字的定義（已重現）

**「44 頁 174 行」——精確重現。**

```python
LABELS = {"Crafting","Recipe","Recipes","Crafting (Shapeless)","Inscriber",
          "Smithing","Throw in Water","Smelting","Charger"}
# 逐頁逐行比對 ln.strip() in LABELS
```

實測輸出：`174 lines / 44 pages`。逐標籤分布：

| 標籤 | 次數 |
| --- | --- |
| `Crafting` | 93 |
| `Recipe` | 28 |
| `Recipes` | 17 |
| `Crafting (Shapeless)` | 13 |
| `Inscriber` | 11 |
| `Smithing` | 5 |
| `Throw in Water` | 3 |
| `Smelting` | 3 |
| `Charger` | 1 |

**「53 頁」——可重現；「193 行」——不可精確重現（部分確認）。**

```python
KW = ["Recipe","Crafting","Smithing","Stonecutting","Processing"]
# 逐行比對 strip() 非空 且 len <= 40 且 含任一 KW
# 全集 = LABELS ∪ {KW 命中但不是精確標籤的行}
```

實測：`KW ∪ LABELS`（≤40 字、strip 後）= **197 lines / 53 pages**。

**53 頁完全吻合；197 − 193 = 4 行的差異**。逐一檢驗 197 行的組成：

- 174 行 = 精確標籤（Set A，即「44 頁 174 行」那組）
- 20 行 = 「≤40 字＋含 KW」但**不是**精確標籤（記為 Set C，10 頁）
- 3 行 = 來自 `Getting the Initial Materials)` 之類的重複計數（見 T0.3）

Set C 的 20 行（逐字，含頁與行號）：

| 頁 | 行 | 內容 | 性質 |
| --- | --- | --- | --- |
| `ae2-mechanics/autocrafting.json` | L19 | `Recursive Recipes` | **合法章節標題** |
| `ae2-mechanics/autocrafting.json` | L31 | `The Crafting CPU` | **合法章節標題** |
| `ae2-mechanics/autocrafting.json` | L33 | `Crafting CPUs are made out of:` | **合法章節標題** |
| `example-setups/recursive-crafting-setup.json` | L0 | `A Recursive Crafting Setup` | **頁標題（= title，R1 會先吃掉）** |
| `items-blocks-machines/certus_quartz_crystal.json` | L3 | `Some Alternate Recipes` | **合法章節標題** |
| `items-blocks-machines/condenser.json` | L2 | `Settings/Recipes` | **合法章節標題** |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L0 | `The Crafting CPU` | **頁標題（= title，R1 會先吃掉）** |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L10 | `Crafting Unit` | **合法章節標題** |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L12 | `Crafting Storage` | **合法章節標題** |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L14 | `Crafting Co-Processing Unit` | **合法章節標題** |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L17 | `Crafting Monitor` | **合法章節標題** |
| `items-blocks-machines/level_emitter.json` | L14 | `Crafting Functionality` | **合法章節標題** |
| `items-blocks-machines/terminals.json` | L31 | `Crafting Terminal` | **合法章節標題** |
| `items-blocks-machines/terminals.json` | L48 | `- Crafting` | 清單項（mode 名稱，見 T1.2） |
| `items-blocks-machines/terminals.json` | L49 | `- Processing` | 清單項 |
| `items-blocks-machines/terminals.json` | L50 | `- Smithing` | 清單項 |
| `items-blocks-machines/terminals.json` | L51 | `- Stonecutting` | 清單項 |
| `items-blocks-machines/upgrade_cards.json` | L37 | `Crafting Card` | **合法章節標題** |
| `items-blocks-machines/wireless_terminals.json` | L13 | `Wireless Crafting Terminal` | **合法章節標題** |
| `other/getting-started.json` | L37 | `  - 1x ME Terminal or ME Crafting Terminal` | 清單項（材料） |

**Set C 的 20 行中，只有 4 行是清單項，其餘 16 行是合法章節標題**（其中 2 行是頁標題，R1 會先處理掉）。

### T0.2 「193 行」的差異來源（部分確認）

我測試了所有合理變體：

| 條件 | 行 | 頁 |
| --- | --- | --- |
| `strip() ∈ LABELS`（精確標籤） | **174** | 44 |
| `≤40 字 + KW`（strip 後） | 176 | 48 |
| `≤40 字 + KW + LABELS`（聯集） | **197** | **53** |
| `≤40 字 + KW`（**不** strip，含行首空格） | 175 | 47 |
| `≤40 字 + KW + LABELS`，扣掉 2 個 `L0 == title` 的頁標題行 | **192** | 49 |
| `含 KW`（不限長度） | 246 | 80 |

**53 頁只能由 `LABELS ∪ KW` 聯集重現**（其他條件都給 44／47／48／80）。但聯集是 197 行不是 193 行。

**194 與 193 的 4 行差異，我無法用任何條件組合精確重現**，可能來自計畫對「行」的不同定義（例如：是否含 L0 的頁標題行、是否含 `Getting the Initial Materials)` 這類換行遺留的重複行、是否把 `Recipes` 的複數形與 `Recipe` 分開計）。**這是數字定義歧義，需人工補充計畫原文才能對齊。**

**事實結論**：`53 頁` 與 `174 行` 可重現；`193 行` 不可重現（最接近的聯集為 197 行）。

### T0.3 「21 頁整頁黏成單行」與「9 頁含黏合式 RecipeCrafting」的交集／差集

「21 頁整頁黏成單行」清單（`text` 中無 `\n`）：

| # | 頁 | 字元數 | title |
| --- | --- | --- | --- |
| 1 | `example-setups/main-network.json` | 171 | `An Example "Main Network"` |
| 2 | `items-blocks-machines/certus_quartz_crystal_charged.json` | 174 | `The Charged Certus Quartz Crystal` |
| 3 | `items-blocks-machines/certus_quartz_dust.json` | 160 | `Certus Quartz Dust` |
| 4 | `items-blocks-machines/charged_staff.json` | 192 | `The Charged Staff` |
| 5 | `items-blocks-machines/crank.json` | 163 | `The Crank` |
| 6 | `items-blocks-machines/decorative_fluix.json` | 125 | `Decorative Fluix` |
| 7 | `items-blocks-machines/ender_dust.json` | 164 | `Ender Dust` |
| 8 | `items-blocks-machines/fluix_block.json` | 116 | `The Fluix Block` |
| 9 | `items-blocks-machines/fluix_dust.json` | 143 | `Fluix Dust` |
| 10 | `items-blocks-machines/fluix_pearl.json` | 114 | `Fluix Pearl` |
| 11 | `items-blocks-machines/fluix_upgrade_smithing_template.json` | 146 | `Fluix Smithing Template` |
| 12 | `items-blocks-machines/illuminated_panels.json` | 207 | `Illuminated Panels` |
| 13 | `items-blocks-machines/matter_ball.json` | 180 | `Matter Balls` |
| 14 | `items-blocks-machines/meteorite_compass.json` | 191 | `The Meteorite Compass` |
| 15 | `items-blocks-machines/quartz_block.json` | 152 | `The Certus Quartz Block` |
| 16 | `items-blocks-machines/quartz_fixture.json` | 204 | `Quartz Fixtures` |
| 17 | `items-blocks-machines/quartz_glass.json` | 184 | `Quartz Glass` |
| 18 | `items-blocks-machines/sky_dust.json` | 240 | `Sky Stone Dust` |
| 19 | `items-blocks-machines/sky_stone_tank.json` | 149 | `The Sky Stone Tank` |
| 20 | `items-blocks-machines/spatial_pylon.json`  | 242 | `The Spatial Pylon` |
| 21 | `items-blocks-machines/wireless_receiver.json` | 116 | `Wireless Receiver` |

**交集／差集**：

- 「含黏合式 `RecipeCrafting`」的頁 = #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #14, #15, #16, #17, #18, #19, #20, #21 = **19 頁**（含 `RecipesCrafting`、`Recipe Inscriber`、`Recipe Charger`、`RecipeCrafting (Shapeless)` 全部黏合形態）
- **交集**：19 頁（全部黏合形態都在 21 頁單行組內）
- **差集（21 − 19）**：2 頁 = `main-network.json`（無配方）、`matter_ball.json`（配方說明在行尾 `Made with 256 items or buckets...`，無 `Recipe` token）

**事實**：所有黏合式配方 token 都出現在「整頁單行」的頁裡；反過來 21 頁中有 2 頁不含配方 token。黏合是「換行遺失」的子現象。

### T0.4 121 頁的分類核對

| 分類 | 頁數 | 頁 |
| --- | --- | --- |
| 首行 == title（獨立一行） | **97** | 見 A2 清單 |
| title 黏在正文句首（無換行） | **21** | 見上表 |
| 首行是站台名 `Applied Energistics 2` | **2** | `ae2-mechanics/p2p-tunnels.json`、`ae2-mechanics/quantum-bridge.json` |
| 首行是版本宣告（非 title） | **1** | `other/getting-started.json`（`The following information only applies to Applied Energistics 2 in Minecraft 1.20 and newer.`） |

97 + 21 + 2 + 1 = **121** ✓。與 `onetime-report.md` §3.1 的 118/121（97+21）一致；剩餘 3 頁為站台名 2 頁 + 版本宣告 1 頁。

**事實結論**：分類自洽，121 = 97 + 21 + 2 + 1。

---

## T1 R4 反向驗證：合法標題會不會被誤刪

**狀態：已確認**

### T1.1 候選集逐行分類

候選集 = Set C（20 行）＋ Set A 中易混淆者。已逐行判定：

| 頁 | 行 | 內容 | 分類 | 依據 |
| --- | --- | --- | --- | --- |
| `ae2-mechanics/autocrafting.json` | L19 | `Recursive Recipes` | **(b) 合法章節標題** | 後接 `One thing the autocrafting algorithm cannot handle is recursive recipes...`，是段落主題 |
| `ae2-mechanics/autocrafting.json` | L31 | `The Crafting CPU` | **(b) 合法** | 後接 `Crafting CPUs manage crafting requests/jobs...` |
| `ae2-mechanics/autocrafting.json` | L33 | `Crafting CPUs are made out of:` | **(b) 合法** | 後接 `- (Required) Crafting storages...` 清單 |
| `example-setups/recursive-crafting-setup.json` | L0 | `A Recursive Crafting Setup` | **(b) 合法（且 = title）** | L0 == title，R1 先處理 |
| `items-blocks-machines/certus_quartz_crystal.json` | L3 | `Some Alternate Recipes` | **(b) 合法** | 引導替代配方段落 |
| `items-blocks-machines/condenser.json` | L2 | `Settings/Recipes` | **(b) 合法** | 設定與配方合併標題 |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L0 | `The Crafting CPU` | **(b) 合法（= title）** | L0 == title |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L10 | `Crafting Unit` | **(b) 合法** | 後接 `(Optional) Crafting units simply fill space...` |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L12 | `Crafting Storage` | **(b) 合法** | 後接 `(Required) Crafting storages are available...` |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L14 | `Crafting Co-Processing Unit` | **(b) 合法** | 後接 `(Optional) Crafting co-processors...` |
| `items-blocks-machines/crafting_cpu_multiblock.json` | L17 | `Crafting Monitor` | **(b) 合法** | 後接 `(Optional) The crafting monitor displays...` |
| `items-blocks-machines/level_emitter.json` | L14 | `Crafting Functionality` | **(b) 合法** | 功能段落標題 |
| `items-blocks-machines/terminals.json` | L31 | `Crafting Terminal` | **(b) 合法** | 後接 `The Crafting Terminal is similar to...` |
| `items-blocks-machines/upgrade_cards.json` | L37 | `Crafting Card` | **(b) 合法** | 升級卡分項說明 |
| `items-blocks-machines/wireless_terminals.json` | L13 | `Wireless Crafting Terminal` | **(b) 合法** | 後接 `The Wireless Crafting Terminal is similar to...` |
| `items-blocks-machines/terminals.json` | L48–51 | `- Crafting`／`- Processing`／`- Smithing`／`- Stonecutting` | **(c) 無法判斷** | 上下文為「終端模式切換清單」，是 UI 模式名稱；既是合法內容也帶配方標籤特徵 |
| `other/getting-started.json` | L37 | `  - 1x ME Terminal or ME Crafting Terminal` | **(b) 合法** | 材料清單項 |

### T1.2 指定案例的明確回報

| 指定案例 | 是否在候選集？ | 分類 | 證據 |
| --- | --- | --- | --- |
| `The Crafting CPU` | **是**（2 處） | **合法章節標題** | `autocrafting.json L31` 前為 `There is actually an even more "general" form...`，後接 `Crafting CPUs manage crafting requests/jobs`；`crafting_cpu_multiblock.json L0` == title |
| `Recursive Recipes` | **是** | **合法章節標題** | `autocrafting.json L19`，後接 `One thing the autocrafting algorithm cannot handle is recursive recipes` |
| `Crafting CPUs are made out of:` | **是** | **合法章節標題** | `autocrafting.json L33`，後接 `- (Required) Crafting storages...` 清單 |
| `Crafting Terminal` | **是** | **合法章節標題** | `terminals.json L31`，前為 `Recipe`，後接 `The Crafting Terminal is similar to a regular terminal` |
| `Quantum Link Chamber` | **否**（更正：見下方註） | **合法章節標題** | `items-blocks-machines/quantum_bridge.json` L6，前為 `Recipe`，後接 `One of these blocks surrounded by a ME Quantum Ring will create...` |

> **註（2026-10-12 更正）**：`Quantum Link Chamber`（20 字）**不含任何 KW**（Recipe／Crafting／Smithing／Stonecutting／Processing），因此**不在 Set C 候選集**內。本表原本寫「是」是我另一個「具名案例 substring 掃描」的結果，與 Set C 的定義混用了。**它既不在 Set C，也不在 LABELS**，故修訂後的「整行白名單」R4 **不會刪除它**。此頁的風險不存在。
| 前置空格的 ` Charger` | **是**（`items-blocks-machines/guide.json L5`，strip 後命中 `LABELS`） | **(c) 無法判斷** | 前為 `Recipe`（L4），後為檔案結束（L5 是最後一行）。`guide.json` 全文只 6 行；` Charger` 是「給充電器充電」的配方標籤還是「充電器」這個物品的說明，**從現有資料無法判定** |

### T1.3 噪音標籤行是否總是緊接 `Recipe`／`Recipes`？

**否**。實測 Set A 中：

| 情形 | 行數 |
| --- | --- |
| 標籤行**緊接**在 `Recipe`／`Recipes` 之後 | **34** |
| 標籤行**不**緊接 `Recipe`／`Recipes` | **95** |

反例（逐字，前幾筆）：

| 頁 | 行 | 標籤 | 前一行 |
| --- | --- | --- | --- |
| `certus_quartz_crystal.json` | L4 | `Crafting (Shapeless)` | `Some Alternate Recipes` |
| `certus_quartz_crystal.json` | L5 | `Throw in Water` | `Crafting (Shapeless)` |
| `cutting_knives.json` | L5 | `Crafting` | `Crafting` |
| `decorative_certus.json` | L4 | `Smelting` | `Crafting` |
| `decorative_certus.json` | L5–25 | `Crafting`（×21） | `Crafting`／`Smelting` |
| `decorative_sky_stone.json` | L4+ | `Crafting`（×16） | `Crafting` |

**事實**：`decorative_certus.json` 有連續 21 行 `Crafting`／`Smelting`，`decorative_sky_stone.json` 連續 16 行——這些頁的標籤行**彼此相鄰**，只在第一個標籤前有 `Recipes`。因此「只在 `Recipe` 錨點後刪」的策略會漏掉後續所有標籤。

### T1.4 兩種候選匹配策略比較

| 策略 | 定義 | 刪除行 | 涉及頁 | 誤刪合法標題 | 漏掉噪音 |
| --- | --- | --- | --- | --- | --- |
| **(a) 精確白名單** | `line.strip() ∈ LABELS` | 174 | 44 | 見 T1.5 | **0**（Set A 全命中） |
| **(b) 只在 `Recipe`／`Recipes` 錨點後刪類型標籤** | `line.strip() ∈ LABELS − {Recipe, Recipes}` 且前一行 strip ∈ {`Recipe`, `Recipes`} | 34（標籤）＋45（錨點） | 33／41 | **0** | **95** |

策略 (b) 漏掉的 95 行全是「標籤彼此相鄰」的連續標籤（`decorative_certus` 21 行、`decorative_sky_stone` 16 行、`quartz_tools` 11 行等）。

### T1.5 策略 (a) 的誤刪盤點

策略 (a) 刪除的 174 行中，**有 1 行確定是合法內容**：

- `items-blocks-machines/guide.json L5` `' Charger'`——見 T1.2，**無法判斷**，且它是全文最後一行，刪除後 `guide.json` 只剩 5 行，其中 L4 `Recipe` 也會被 (a) 刪掉。

**觀察**（事實，非建議）：策略 (a) 在 `guide.json` 上會把全文最後兩行（`Recipe` + ` Charger`）一起刪掉，使頁尾停在 `- Many pages have interactive scenes...`。是否可接受取決於 ` Charger` 的語意判定。

### T1.6 補充策略（第三種）

觀察到的**結構特徵**：標籤噪音行的上下文是「同行或相鄰行沒有實質內容句子」。合法章節標題（如 `The Crafting CPU`）**後面緊接完整句子**；噪音標籤（如 `Crafting`×21）**彼此相鄰或接在 `Recipe`／`Recipes` 之後**。可作為第三種匹配策略的依據（**只列方向，不定規則**）。

---

## T2 黏合式噪音的結構性盤點

**狀態：已確認**

### T2.1 21 頁單行頁的黏合形態

| 頁 | 字元數 | 行尾黏合 token | 行尾 60 字元 |
| --- | --- | --- | --- |
| `certus_quartz_crystal_charged` | 174 | `Recipe Charger` | `...budding certus blocks.Recipe Charger` |
| `certus_quartz_dust` | 160 | `Recipe Inscriber` | `...components.Recipe Inscriber` |
| `charged_staff` | 192 | `RecipeCrafting` | `...in a Charger.RecipeCrafting` |
| `crank` | 163 | `RecipeCrafting` | `...am I right?RecipeCrafting` |
| `decorative_fluix` | 125 | `RecipesCrafting`×2 | `...blocks.RecipesCraftingCraftingCrafting` |
| `ender_dust` | 164 | `Recipe Inscriber` | `...pairs.Recipe Inscriber` |
| `fluix_block` | 116 | `RecipeCrafting` | `...machines.RecipeCrafting` |
| `fluix_dust` | 143 | `Recipe Inscriber` | `...components.Recipe Inscriber` |
| `fluix_pearl` | 114 | `RecipeCrafting` | `...components.RecipeCrafting` |
| `fluix_upgrade_smithing_template` | 146 | `RecipeCrafting (Shapeless)` | `...fluix toolsRecipeCrafting (Shapeless)` |
| `illuminated_panels` | 207 | `RecipesCrafting` | `...subparts.RecipesCrafting (Shapeless)Crafting (Shapeless)...` |
| `meteorite_compass` | 191 | `Recipe Charger` | `...you should make.Recipe Charger` |
| `quartz_block` | 152 | `RecipeCrafting` | `...certus blocks.RecipeCrafting` |
| `quartz_fixture` | 204 | `RecipesCrafting` | `...its block.RecipesCraftingCrafting` |
| `quartz_glass` | 184 | `RecipesCrafting` | `...emits light.RecipesCraftingCrafting` |
| `sky_dust` | 240 | `Recipe Inscriber` | `...height limit.Recipe Inscriber` |
| `sky_stone_tank` | 149 | `RecipeCrafting` | `...else to say.RecipeCrafting` |
| `spatial_pylon` | 242 | `RecipeCrafting` | `...to function.RecipeCrafting` |
| `wireless_receiver` | 116 | `RecipeCrafting` | `...ME technology.RecipeCrafting` |
| `main-network` | 171 | 無 | `...Here is an example:` |
| `matter_ball` | 180 | 無 | `...in matter ball mode.` |

### T2.2 全庫黏合 token 清單（去重＋次數＋片段）

| Token | 出現次數 | 前 40 字元片段（節選） |
| --- | --- | --- |
| `RecipeCrafting` | **9** | `...am I right?RecipeCrafting`（crank）／`...a Charger.RecipeCrafting`（charged_staff）／`...few machines.RecipeCrafting`（fluix_block） |
| `RecipesCrafting` | **4** | `...building blocks.RecipesCraftingCraftingCrafting`（decorative_fluix）／`...cable subparts.RecipesCrafting (Shapeless)Crafting...`（illuminated_panels） |
| `Recipe Inscriber` | **4** | `...components.Recipe Inscriber`（certus_quartz_dust、ender_dust、fluix_dust） |
| `Recipe Charger` | **2** | `...certus blocks.Recipe Charger`（certus_quartz_crystal_charged）／`...you should make.Recipe Charger`（meteorite_compass） |
| `RecipeCrafting (Shapeless)` | **1** | `...for fluix toolsRecipeCrafting (Shapeless)`（fluix_upgrade_smithing_template） |
| `RecipeSmithing` | 0 | — |
| `RecipeInscriber` | 0 | — |

**事實**：5 種黏合 token，全庫合計 **20 次**，全部落在 21 頁單行組的 19 頁裡。

### T2.3 黏合 token 在行尾還是行中？

| Token | 在行尾（token 之後只有空白／結尾） | **在行中**（token 之後還有其他內容） |
| --- | --- | --- |
| `RecipeCrafting` | 8 | **1**（`fluix_upgrade_smithing_template`：`...fluix toolsRecipeCrafting (Shapeless)`） |
| `RecipesCrafting` | 0 | **4**（decorative_fluix、illuminated_panels、quartz_fixture、quartz_glass） |

**事實結論**：`RecipesCrafting` **4/4 出現在行中**（後面接 `Crafting`／`Crafting (Shapeless)`）。**只在行尾比對的正則不夠**——至少需要「token 出現即處理」或「token 後可接其他 token」的匹配。`RecipeCrafting` 也有 1/9 在行中。

### T2.4 是否有「標題黏在句首」以外的黏合型態？

**是**，而且更普遍。21 頁的黏合有**三層**：

1. **標題黏在正文句首**：全部 21 頁（`The CrankThe crank is used to...`）。這是 R1 的目標。
2. **句子之間黏合**：`spatial_pylon` — `...affected.Each continuous line of pylons uses 1 channelLines of pylons must be at least 2 blocks long to function.RecipeCrafting`。**這裡 `Each continuous...` 與 `Lines of pylons...` 是兩個獨立句子，中間無換行**。
3. **配方標籤彼此黏合**：`decorative_fluix` — `RecipesCraftingCraftingCrafting`（3 個標籤連成一串，無分隔）。

**事實**：黏合不是「只有標題在句首」的單一形態；句子邊界（句號後大寫）與標籤邊界（標籤 token 相連）也需要處理。

---

## T3 規則順序相依性

**狀態：已確認（但規則文字為模擬，非 R1–R5 原文）**

⚠ **限制**：R1–R5 原文未取得。以下用任務描述可辨識的語義自行定義規則來模擬，**結論是「順序確實有影響」這個事實**，不是對真實 R1–R5 的驗證。

### 模擬用的規則定義（我自行定義，非計畫原文）

- **R1**（首行標題去重）：若 line0 == title，刪 line0
- **R3**（終止標點合併）：若前一行**不以** `[.!?]` 結尾且當前行非空、非清單項，則併入前一行；刪除 `strip() == '-'` 的行
- **R4**（標籤刪除）：`line.strip() ∈ LABELS` 則刪

### 兩種順序的輸出比較（`terminals.json`）

| 順序 | 輸出行數 | 逐字相同？ |
| --- | --- | --- |
| R1 → R2 → R3 → R4 | 50 | **否** |
| R1 → R2 → R4 → R3 | 50 | |

**首差位置**（idx 18）：

| 順序 | 輸出 |
| --- | --- |
| R3 在前 | `Recipe Crafting Terminal The Crafting Terminal is similar to a regular terminal, with all the same settings and sections` |
| R4 在前 | `Crafting Terminal The Crafting Terminal is similar to a regular terminal, with all the same settings and sections, but w...` |

### terminals 指定行範圍的差異

**原始 L14–22**（供對照）：

```
L14| '- Left-click grabs a stack, right-click grabs half a stack.'
L15| '- '                          ← 游離 -
L16| 'If an item or fluid or etc. is able to be autocrafted,'
L17| 'whatever you have bound to "pick block" (usually middle-click) brings up a UI to specify the amount to be crafted. You can also input formulas like 3*64/2 ,'
L18| 'or type=32 to only craft the number of items needed to reach 32 in your storage.'
L19| '- Holding shift will freeze the displayed items in-place...'
L20| '- Right-clicking with a bucket or other fluid container will deposit the fluid...'
L21| 'The left section has settings buttons to:'
L22| '- Sort by different attributes like name, mod, and quantity'
```

**R3 在前**把 L16–L18 合併成一行（因 L16 結尾是逗號、L17 結尾是逗號），再交給 R4 刪 `Recipe`；
**R4 在前**先刪掉 `Recipe`（L30），R3 才把 `Crafting Terminal` 與下一句合併。

**L67–76 區域**（原始）：

```
L67| '- '                          ← 游離 -
L68| 'The smithing and stonecutting mode UIs work similarly to a smithing table and stonecutter respectively.'
L69| 'Recipe'
L70| 'Pattern Access Terminal'
L71| 'The Pattern Access Terminal serves to solve a specific issue...'
```

**R3 在前**：idx45 = `Recipe Pattern Access Terminal The Pattern Access Terminal serves to solve...`（`Recipe` 未被 R4 刪掉前就被 R3 併入）
**R4 在前**：idx45 = `Pattern Access Terminal The Pattern Access Terminal serves to solve...`（`Recipe` 已刪）

**事實結論**：兩種順序輸出**不逐字相同**。差異全部集中在「R3 合併 vs R4 刪除」對同一行的競爭——**R4 在前可避免 `Recipe` 被併入正文**。

### 其他順序相依的事實

- R3 的「終止標點」判斷會被**行內的逗號**干擾（L16–L18 以逗號結尾，被合併）。
- `throw-in-water-automation.json` 的 L11–L12 連續兩個 `- `（見 T4），R3 若先合併會把它們與前後句黏住。

---

## T4 R3 的資訊保存驗證

**狀態：已確認**

### 字元守恆檢查

**定義**：對每頁，移除所有空白與 `-` 標記後，R3 前後的內容應完全一致。

**實測（56 處游離 `-`，12 頁）**：

| 檢查項 | 結果 |
| --- | --- |
| `strip() == '-'` 的行其**非空白內容**是否為空 | **0 行有非空內容** → 守恆對全部 56 處成立 |
| raw 行不等於 `'- '`（含行首空格）的 | 2 行：`'  - '`（`throw-in-water-automation.json` L7、L9）→ 內容仍為空，守恆成立 |

**事實**：所有游離 `-` 行的**內容恆為空**（只有 `-` 與空白），因此刪除它們**不會丟失任何字元資訊**。字元守恆 56/56 通過。

### 兩種 R3 方案的輸出差異

| 方案 | `terminals` L15–18 | `throw-in-water` L11–12 | `autocrafting` |
| --- | --- | --- | --- |
| **「終止標點」合併**（不以 `.!?` 結尾才合併） | L16–18 合併為一行（逗號結尾觸發合併） | L10 與 L11 合併（L10 結尾為 `:`，不觸發）；L11–12 兩個 `- ` 被刪 | L14–17 的長段落不變（以 `.` 結尾） |
| **「嚴格單行合併」**（只處理整頁單行的 21 頁） | 完全不處理（terminals 非單行頁） | 完全不處理 | 完全不處理 |

**事實**：「嚴格單行合併」只影響 21 頁，不動其他 100 頁；「終止標點」會**額外**把 100 頁中的逗號結尾行併入前行（`terminals` L16–18 為例），這可能把**原本換行是有意義的排版**（如 UI 操作步驟）合掉。

---

## T5 根因評估：回 [3] 重抽是否可行

**狀態：已確認（結論與任務假設相反）**

### T5.1 現況參數

`src/extract_pages.py:86-91`：

```python
raw = trafilatura.extract(
    html,
    output_format="json",
    with_metadata=True,
    include_tables=True,
)
```

`trafilatura` 版本：**2.2.0**（實測 `import trafilatura; trafilatura.__version__`）。

### T5.2 raw HTML 可用性

**可用**。`data/raw/1.21.1/applied-energistics-2/` 下 124 頁 HTML 全數存在（實測 `glob("**/*.html")` = 124）。

### T5.3 `include_formatting=True` 實驗（6 頁，隔離於 /tmp）

| 頁 | 模式 | 字元 | 行 | `#` 標題 | 空行 | 單行？ | 游離 `-` | 標籤行 | 表格行 | 黏合 token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `terminals` | current | 6149 | 77 | 0 | 0 | 否 | 4 | 3 | 0 | 0 |
| `terminals` | +formatting | 6149 | 79 | **0** | **0** | 否 | **4** | **3** | 0 | 0 |
| `energy` | current | 2791 | 17 | 0 | 0 | 否 | 0 | 0 | 0 | 0 |
| `energy` | +formatting | 2791 | 17 | **0** | **0** | 否 | 0 | 0 | 0 | 0 |
| `crank` | current | 163 | 1 | 0 | 0 | **是** | 0 | 0 | 0 | 1 |
| `crank` | +formatting | 163 | 1 | **0** | **0** | **是** | 0 | 0 | 0 | **1** |
| `throw-in-water` | current | 2108 | 28 | 0 | 0 | 否 | 8 | 0 | 0 | 0 |
| `throw-in-water` | +formatting | 2108 | 28 | **0** | **0** | 否 | **8** | 0 | 0 | 0 |
| `upgrade_cards` | current | 3076 | 43 | 0 | 0 | 否 | 0 | 0 | 20 | 0 |
| `upgrade_cards` | +formatting | 3076 | 43 | **0** | **0** | 否 | 0 | 0 | **20** | 0 |
| `p2p-tunnels`(stub) | current | 77 | 7 | 0 | 0 | 否 | 0 | 0 | 0 | 0 |
| `p2p-tunnels`(stub) | +formatting | 77 | 7 | **0** | **0** | 否 | 0 | 0 | 0 | 0 |

**事實**：`include_formatting=True` 對 `output_format="json"` **幾乎完全無效**——`##` 數仍為 0、空行仍為 0、單行頁仍單行、游離 `-` 與標籤行計數不變。`terminals` 的 77→79 行差異**只是把一個長段落拆成 3 行**（換行位置不同，無標題產生）：

```
current:  ['While ME Pattern Providers, ... There are several variants with differing functions.']
formatting: ['While ME Pattern Providers, ME Import Busses, ME Storage Busses, and the et cetera',
             'are the primary method by which an AE2 network interacts with the world, Terminals are the primary method by which an AE2',
             'network interacts with you. There are several variants with differing functions.']
```

### T5.4 改用 `output_format="markdown"` 才有效

| 頁 | `##` | 空行 | 單行？ | 游離 `-` | 標籤行 | 表格行 | 黏合 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `energy` | **2** | **15** | 否 | 0 | 0 | 0 | 0 |
| `upgrade_cards` | **10** | **27** | 否 | 0 | **0**（見下） | 20 | 0 |
| `terminals` | 8 | 47 | 否 | **4** | **0** | 0 | 0 |
| `throw-in-water` | 2 | 7 | 否 | **8** | 0 | 0 | 0 |
| `crank` | **0** | **0** | **仍是單行** | 0 | 0 | 0 | **仍有 `RecipeCrafting`** |
| `decorative_certus` | 1 | 25 | 否 | 0 | **23** | 0 | 0 |
| `p2p-tunnels`(stub) | 0 | 0 | 否 | 0 | 0 | 0 | 0 |

逐字範例（`upgrade_cards` markdown 模式）：

```
# Upgrade Cards

Upgrade cards change the behavior of AE2 devices and machines, increasing the speed, imp...

## Card Components
```

**事實**：`markdown` 模式確實產出 `## Card Components` 這類真標題，但：

- **`crank` 仍是單行**：`"The CrankThe crank is used to power machines...RecipeCrafting"`——黏合**未修復**
- **`decorative_certus` 仍有 23 個標籤行**：`Crafting\n\nCrafting\n\nCrafting...`——標籤**未修復**（只是從相鄰變成有空行分隔）
- **游離 `-` 未修復**（terminals 4、throw-in-water 8）
- **表格仍完整**（upgrade_cards 20 行表格行保留）

### T5.5 markdown 模式全 124 頁穩定性 + 新問題

實測 124 頁 HTML 全跑 `output_format="markdown"`：**0 例外、0 個 None**。

但 **H1 數量分布**：

| H1 數 | 頁數 |
| --- | --- |
| 0 | **24** |
| 1 | 89 |
| 2 | 3 |
| 3 | 4 |
| 5 | 2 |
| 6 | 2 |

`terminals` markdown 模式的標題列表（逐字）：

```
'# Terminals'  '# Terminal Search'  '# Terminal'  '# Crafting Terminal'
'# Pattern Encoding Terminal'  '# Pattern Access Terminal'
'## Terminal Placement'  '## The UI'(×4)  '## Recipe'(×3)
```

**事實**：markdown 模式把 `Recipe` 也升級成 `## Recipe`（**噪音被結構化成標題**），且把 6 個子終端都升級成 `# H1`（**一頁多個 H1**，與 [4] 契約的「每頁一個 `# <title>`」衝突）。

### T5.6 若採用 markdown 模式，契約需變動的清單

| 條文位置 | 現況 | 需變動 |
| --- | --- | --- |
| `AGENTS.md` §8 `[3] 抽取` 參數列 | `output_format="json", with_metadata=True, include_tables=True` | 改為 `markdown`（或 json+markdown 雙輸出） |
| `AGENTS.md` §6 [3] Contract | 「trafilatura 抽取主文」 | 需定義 markdown 輸出的 frontmatter（含 `title`/`url`/`hostname`/`sitename`/`date`）如何與 extracted JSON 欄位對應 |
| `AGENTS.md` §7 Extracted JSON 欄位表 | `title`/`text`/`source`/`hostname`/`http_status` | `text` 變為 markdown 後，欄位語義改變；需重新定義 |
| `AGENTS.md` §6 [4] Contract | 「trafilatura 誤留噪音」 | 噪音清單整個重定義（標籤行、游離 `-` 的處理前提改變） |
| `ARCHITECTURE.md:218-233` [4] 範例 | `## Energy Accepting` 假設 | 變為真實（markdown 模式真的產出 `##`） |
| `AGENTS.md` §6 [3] navigation_only 判定 | 用 `extracted["text"]` 長度 | markdown 輸出的長度語義不同（含 `#`、空行），閾值 `NAV_MIN_TEXT_LENGTH` 需重算 |
| `AGENTS.md` §6 [3] `.md` 衍生物 | 「text 原文（不加工）」 | 衍生物與真值都是 markdown，界線消失 |
| `AGENTS.md` §6 [5] 前置條件 | [5] 只讀 cleaned MD | 不變（[4] 仍產出 cleaned MD） |

**事實**：至少 8 處契約條文需變動（**只列清單，不建議採用與否**）。

### T5.7 三個症狀的根因歸屬（事實）

| 症狀 | 根因層 | `include_formatting` 能修？ | `markdown` 能修？ |
| --- | --- | --- | --- |
| 無 `##` 標題 | [3] 輸出格式（json 模式不帶標題記號） | **否** | **是** |
| 21 頁整頁黏成單行 | [3] 換行遺失（此網站的 recipe 區塊無文字節點） | 否 | **否**（crank 實證） |
| 配方標籤行 | [3]（圖片被抽掉只剩 tab label） | 否 | **否**（只是加空行） |
| 游離 `-` | [3]（徽章圖被抽掉） | 否 | **否** |
| 表格結構 | 無此問題 | — | 表格仍完整 |

**事實結論**：只有「無 `##` 標題」可由重抽修復，且**只能靠換 `output_format`**，`include_formatting` 參數本身無效。黏合、標籤、游離 `-` **三項重抽都無法修復**，只能在 [4] 處理。

---

## T6 alias 機制的最小化選項

**狀態：已確認**

### T6.1 [5]／[6] 是否有程式讀取 alias？

**否**。實測：

| 檔 | `alias` 相關字串出現次數 |
| --- | --- |
| `src/extract_pages.py` | **0** |
| `src/fetch_pages.py` | **0** |
| `src/chunk_pages.py` | **不存在** |
| `src/embed_chunks.py` | **不存在** |

**事實**：目前只有 [2]、[3] 實作。**無任何程式碼讀取或使用 alias**。alias 的「fail-fast vs warning」決策目前**不影響任何已實作程式碼**。

### T6.2 三個選項與影響

| 選項 | 定義 | 影響 |
| --- | --- | --- |
| **(a) 保留 frontmatter aliases + fail-fast** | frontmatter 寫入 alias 清單，[5] 讀到時若 `len != 1` 立即中止 | 最嚴格；任何新頁的 alias 異常會中斷整個 [5]。但目前**沒有任何下游讀它**，等於對未實作的契約先設硬約束 |
| **(b) 保留 aliases 但解析失敗只 warning** | 寫入同上，但 `len != 1` 只記錄於 report | 不中斷 pipeline；alias 資訊保留在 frontmatter 供人類閱讀 |
| **(c) 不寫 frontmatter，只記錄於 report** | alias 只進 `cleaning_report.md` | frontmatter 保持最小（`title` + `source_url`），符合 `AGENTS.md` §7「frontmatter 至少含 `title`、`source_url`」；alias 不進入 [5] 的視野 |

### T6.3 `len != 1` 在未來新頁可能觸發的情境

事實列舉（從 121 頁觀察到的模式推導）：

1. **同義詞 renaming**：網站改標題（如 `The Crank` → `Crank`），anchor text 與 title 分離 → alias 清單可能有 0 或 2 個
2. **title 衍生別名**：`The Crank` 的定冠詞 `The` 若被列為 alias，`The Quantum Network Bridge` 類標題會系統性產生多個衍生值
3. **stub 頁**：`ae2-mechanics/p2p-tunnels.json`（title `P2P Tunnels`）與 `items-blocks-machines/p2p_tunnels.json` 同名 → alias 與 page_slug 的對應關係在 stub 頁上不唯一
4. **錨文字別名**：`Getting The Initial Materials)`（`getting-started.json` L2，含孤立右括號）→ 從錨文字抽出的 alias 可能帶標點，數量不穩定

### T6.4 計畫措辭更正（依任務指示）

> 「quantum 的 title 衍生別名是 no-op」

**事實佐證**：`ae2-mechanics/quantum-bridge.json` 的 title = `The Quantum Network Bridge`，page_slug = `quantum-bridge`。從 title 衍生別名（如去 `The`、去空格）得到的值**已包含在 title／page 的變體內**，對檢索無額外增益。**有增益的是錨文字別名**——例如 `items-blocks-machines/quantum_bridge.json` L6 的錨文字 `Quantum Link Chamber` 是一個**與 title 完全不同**的實體名稱，才是 alias 的價值來源。

---

## T7 邊界與守衛

**狀態：已確認**

### T7.1 空 body / 極短頁（模擬 R1–R4 後）

模擬規則：刪 line0（若 == title）、刪 `strip() == '-'` 行、刪 `strip() ∈ LABELS` 行。

| 頁 | 模擬後字元數 | 備註 |
| --- | --- | --- |
| `ae2-mechanics/p2p-tunnels.json` | **77** | stub 頁（見 T7.3） |
| `items-blocks-machines/decorative_sky_stone.json` | **81** | 原本 26 行中 16 行是 `Crafting`，刪光 |
| `items-blocks-machines/decorative_certus.json` | **95** | 原本 26 行中 21 行是 `Crafting`／`Smelting` |
| `ae2-mechanics/quantum-bridge.json` | **103** | stub 頁 |
| `items-blocks-machines/fluix_pearl.json` | **114** | 單行頁，刪標籤後仍短 |
| `items-blocks-machines/fluix_block.json` | **116** | 同上 |
| `items-blocks-machines/wireless_receiver.json` | **116** | 同上 |
| `items-blocks-machines/decorative_fluix.json` | **125** | 同上 |

**空 body（< 1 字元）：0 頁。**「< 200 字元：22 頁」。

**事實**：模擬後**無任何頁為空**，但 `decorative_sky_stone`（81）／`decorative_certus`（95）在刪除標籤後幾乎失去全部內容——因為這些頁的**配方資訊本來就只在被抽掉的圖片裡**。

### T7.2 各處置選項的下游影響（不裁決）

| 選項 | 對 [5] 的影響 | 對 chunk_id 的影響 | 對驗收的影響 |
| --- | --- | --- | --- |
| **(a) 仍輸出 .md** | 該頁仍產 chunk；極短頁在 `chunk_size=200` 下只產 1 個 chunk | 佔用 `{mod}_{page}_0001_v1`，不影響他頁 | `AGENTS.md` §13 [4] 驗收要求 `cleaned/*.md` 非空 → 通過（但內容極短） |
| **(b) 跳過並記 report** | 少 1 chunk／頁 | 無影響（seq 頁內獨立） | 非空斷言對該頁**不成立**，需 report 作為替代證據 |
| **(c) 中止** | [5] 完全不執行 | — | 全批失敗，121 頁中多數正常頁被連累 |

### T7.3 C 型頁（getting-started）

```
L0| 'The following information only applies to Applied Energistics 2 in Minecraft 1.20 and newer.'
L1| 'Getting Started'
L2| 'Getting The Initial Materials)'
L3| 'To get started with Applied Energistics 2, one must first find a meteorite...'
```

**事實**：L0 是版本宣告（admonition），L1 才是 title。R1-C（刪 line0 站名）**在這頁不適用**——L0 不是 `Applied Energistics 2`，是完整版本宣告句。若 R1 規則寫成「刪 line0 若 == 站名」，此頁 L0 **會殘留**。且 L2 `Getting The Initial Materials)` 帶**孤立右括號**（對應左括號在原網頁是連結／圖片，已被抽掉）。

### T7.4 stub 頁排除後的交叉引用

`ae2-mechanics/p2p-tunnels.json`（stub，77 字元）與 `ae2-mechanics/quantum-bridge.json`（stub，103 字元）全文：

```
p2p-tunnels:      ['Applied Energistics 2', 'P2P Tunnels', 'See', 'P2P Tunnels', 'Minecraft 1.21.1 [', 'change', ']']
quantum-bridge:   ['Applied Energistics 2', 'The Quantum Network Bridge', 'See', 'Quantum Network Bridge', 'Minecraft 1.21.1 [', 'change', ']']
```

**其他頁對這兩個實體的引用**（實測全文搜尋）：

| 引用頁 | 引用對象 | 次數 |
| --- | --- | --- |
| `ae2-mechanics/channels.json` | `P2P Tunnel` | 1 |
| `ae2-mechanics/channels.json` | `Quantum Network Bridge` | 1 |
| `ae2-mechanics/me-network-connections.json` | `P2P Tunnel` | 1 |
| `items-blocks-machines/p2p_tunnels.json` | `P2P Tunnel` | 1 |
| `items-blocks-machines/quantum_bridge.json` | `Quantum Network Bridge` | 4 |
| `items-blocks-machines/singularities.json` | `Quantum Network Bridge` | 1 |
| （stub 頁自身） | — | 2 |

**事實**：`channels`／`me-network-connections`／`singularities` 的正文提到這兩個實體，但**這些引用是知識內容（如「quantum bridge 可跨 32 channel」），不是對 stub 頁的連結**。**排除 stub 頁不會使其他頁的內容失去意義**——真正的內容在 `items-blocks-machines/p2p_tunnels.json` 與 `quantum_bridge.json`。

---

## T8 frontmatter 與 [5] 介面

**狀態：已確認**

### T8.1 `_yaml_scalar` round-trip（121 title）

用 `src/extract_pages.py` 的 `_yaml_scalar` 序列化全部 121 個 title，再 `yaml.safe_load` 反解析：

| 檢查 | 結果 |
| --- | --- |
| `title` round-trip 失敗 | **0 / 121** |
| 需加引號的 title | 3 個（`Import, Export, and Storage`、`An Example "Main Network"`、`Item/Fluid "Pipe" Subnet`） |

**事實**：`_yaml_scalar` 對現有 121 個 title **完全安全**。已知弱點（含 `\n` 的值、純數字字串、`true`/`false` 字串）在本語料**皆未觸發**（0 個 title 屬於這些類型）。

### T8.2 [5] 將如何解析 frontmatter

`AGENTS.md` §6 [5] 的契約文字（`ARCHITECTURE.md:243-249`）：[5] 從 cleaned MD 的 **frontmatter 讀 `title`／`source_url`**，從**路徑**讀 `page`／`chapter`／`mod`／`version`。**文件未指定解析方式（手寫或 YAML 套件）**。

**事實**：`PyYAML` **不在 `requirements.txt`／`pyproject.toml`**（6 套件：requests、beautifulsoup4、python-slugify、trafilatura、langchain-text-splitters、sentence-transformers）。`_yaml_scalar` 的註解明載「採用顯式判斷而不引入 pyyaml 依賴（`AGENTS.md` §8）」。因此 [5] 若沿用同一精神，**應手寫解析**（例如正則抓 `title: ` 與 `source_url: `），且對**引號的期待**是 `_yaml_scalar` 的雙引號跳脫格式。

**對 alias 的影響**：若 alias 以 YAML list 寫入 frontmatter（`aliases:\n  - foo\n  - bar`），手寫解析需額外處理 list 格式；`_yaml_scalar` 只處理 scalar。**這是 alias 選項 (a)／(b) 的額外成本**。

### T8.3 檔案換行

**事實**：`data/processed/extracted_readable/1.21.1/applied-energistics-2/ae2-mechanics/energy.md` 的 bytes：`has CR = True`，`CR count = 27`，`LF count = 27`。首 120 bytes：

```
b'---\r\ntitle: Energy\r\nsource: "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/energy"\r\nhostname: appliedenergis'
```

**原因**：`src/extract_pages.py:234-235` 用 `path.write_text(content, encoding="utf-8")`，**未指定 `newline`**。Windows 上 `write_text` 預設把 `\n` 轉成 `\r\n`（Python universal newline 的平台預設）。

**[4] 若要求跨平台 byte-identical，可指定的寫檔參數**（只列選項）：

| 選項 | 效果 |
| --- | --- |
| `open(path, "w", encoding="utf-8", newline="\n")` | 強制 LF，跨平台一致 |
| `open(path, "wb")` + `content.encode("utf-8")` | 二進制，完全不轉換 |
| `path.write_text(content, encoding="utf-8", newline="\n")` | 同第一個，語義明確 |
| 維持現況（不指定） | 與 [3] 一致（Windows 上 CRLF），但 Linux／macOS 重跑會 LF → **不 byte-identical** |

---

## T9 回歸 fixtures 候選清單

**狀態：已確認（只列清單，不建立檔案）**

| # | 頁路徑（相對 `data/processed/extracted/1.21.1/applied-energistics-2/`） | 行範圍 | 要防止的錯誤 | 預期行為 |
| --- | --- | --- | --- | --- |
| 1 | `items-blocks-machines/terminals.json` | 15–18 | R3 把游離 `-` 與正文錯誤合併 | L15 的 `- ` 被刪；L16–18 保持為換行分隔的語句，不與 `- ` 黏連 |
| 2 | `items-blocks-machines/terminals.json` | 67–76 | R3／R4 順序導致 `Recipe` 被併入正文 | `Recipe`（L69）先刪除，`Pattern Access Terminal`（L70）不成為合併起點 |
| 3 | `example-setups/throw-in-water-automation.json` | 11–12 | 連續兩個 `- ` 造成空合併 | 兩行都刪除，前後句不互相黏連 |
| 4 | `items-blocks-machines/crank.json` | 0–1（整頁單行） | 黏合頁的 title 切割誤傷正文 | 只切掉前綴 `The Crank`；`The crank is used to...` 的小寫 `The crank` 保留；行尾 `RecipeCrafting` 分離為標籤並刪除 |
| 5 | `items-blocks-machines/quantum_bridge.json` | 5–7 | `Recipe`（L5）與合法標題 `Quantum Link Chamber`（L6）的誤刪 | L5 刪除；**L6 保留**（它是合法章節標題，後接完整句子） |
| 6 | `ae2-mechanics/autocrafting.json` | 19／31／33 | 三個合法標題被 R4 白名單誤刪 | `Recursive Recipes`、`The Crafting CPU`、`Crafting CPUs are made out of:` **全部保留** |
| 7 | `items-blocks-machines/guide.json` | 4–5 | `Recipe` + 前置空格 ` Charger` 的語意判定 | ` Charger` 的判定結果需人工確認（見 T1.2） |
| 8 | `items-blocks-machines/controller.json` | 12–13 | 結尾 `Recipe`／`Crafting` 連續標籤 | 兩行都刪除，頁尾停在 `You can right-click on a controller...` |
| 9 | `ae2-mechanics/energy.json` | 0 | title `Energy` 在全文出現 13 次（如 `Energy Accepting`、`Energy Storage`），R1 只能切第一處 | 只刪 L0；L2 `Energy Accepting`、L8 `Energy Storage` 等子標題**保留** |
| 10 | `ae2-mechanics/me-network-connections.json` | 6 | L6 `Network Connections` 與 L0（title）**逐字相同**但不是 L0 | L6 **保留**（它是頁內重複的章節標題，不是 title 回聲） |
| 11 | `items-blocks-machines/crafting_cpu_multiblock.json` | 0／10／12／14／17 | title `The Crafting CPU` 與 4 個 `Crafting *` 合法標題 | L0 由 R1 處理；L10／12／14／17 **全部保留** |
| 12 | `other/getting-started.json` | 0–2 | L0 版本宣告被誤當站名刪除 | L0 保留或依規則處理；L1 `Getting Started` 才是 title |
| 13 | `ae2-mechanics/p2p-tunnels.json` | 0–6 | stub 頁處置 | 依人工決策（輸出／跳過／中止） |
| 14 | `items-blocks-machines/decorative_certus.json` | 4–25 | 連續 21 行 `Crafting`／`Smelting` | 依噪音規則決策；注意刪除後僅剩 95 字元 |

---

## T10 契約措辭草擬

**狀態：已確認（草擬，不含批次數字）**

### AGENTS.md §6 [4] 的 Contract 欄（草擬）

> 過濾 trafilatura 誤留噪音，輸出**含 frontmatter** 之乾淨 MD。frontmatter 至少含 `title`、`source_url`（值由 extracted JSON 原封帶入，**資料不異動**），其後為 `# <title>` + 正文。噪音規則涵蓋：**配方標籤孤兒行**（合成圖被抽掉後僅剩 tab 標籤文字）、**游離項目符號**（徽章圖被抽掉後僅剩 `- `）、**黏合頁的標題與正文邊界**（無換行）、**首行標題重複**、**頁首站台名／版本徽章殘留**。`title`／`source_url` 只能原封傳遞，[4] 不得改寫內容欄位。其餘 metadata 的權威來源為目錄路徑。

### AGENTS.md §6 [4] 的 Failure 欄（草擬）

> `title` 或 `source` 為空 → 該頁不輸出 cleaned MD，記錄於 report（不中斷其他頁）。噪音刪除後 body 為空或過短 → 依既決選項處置（輸出／跳過並記 report／中止），於 report 標明。frontmatter 序列化必須可被 YAML 解析器 round-trip 還原。整份覆寫（冪等）。

### 自檢：無一次性數字

上述措辭**不含**任何 `174`／`44`／`193`／`53`／`56`／`21` 等批次數字，所有量詞皆為規範語義（「連續標籤」「黏合頁」）。✓

### ARCHITECTURE.md §4 [4] 範例與實際資料不符的位置

| 位置 | 範例內容 | 實際情況 | 原因 |
| --- | --- | --- | --- |
| `ARCHITECTURE.md:230` | `## Energy Accepting` | 實際 `energy.json` 的 L2 是**裸文字** `Energy Accepting`（無 `##`） | trafilatura json 模式不保留標題記號（T5 實證） |
| `ARCHITECTURE.md:218-233` 整個範例 | 含 H1 + 多個 H2 的結構化 MD | 121 頁**全部無 H2**；小標題皆為裸文字行 | 同上 |
| 範例的「正文不縮排」 | 正文行首無空格 | 11 頁有行首空格（`' Smelting'`、`'  - '`） | trafilatura 保留部分縮排 |

---

## T11 配方材料遺失的下游影響

**狀態：部分確認**

### T11.1 統計

| 檢查 | 頁數 |
| --- | --- |
| 含 `Recipe`／`Recipes`／`Crafting` 標籤行的頁 | 44（Set A） |
| 這些頁中，正文**完全無任何材料相關詞**（`ingredient|pattern|smelt|smith|shapeless|require|combine|place|around|put|mix|dust|crystal|ingot|block|item`） | **4** |

4 頁明細：

| 頁 | 字元數 |
| --- | --- |
| `items-blocks-machines/guide.json` | 341 |
| `items-blocks-machines/memory_card.json` | 323 |
| `items-blocks-machines/mysterious_cube.json` | 282 |
| `items-blocks-machines/quartz_tools.json` | 270 |

**其餘 40 頁**的情況是「材料資訊在**被抽掉的圖片裡**」——正文有標籤（`Crafting`）但材料清單本身是圖片。**這點無法從 extracted JSON 驗證**（圖片已不在資料裡），故標「部分確認」。

**例**（`paintballs.json`）：正文有 `8 matter balls around a dye` 這類**文字 caption**（少數有保留的），但多數頁只有 `Crafting` 標籤。

### T11.2 選項（不裁決）

| 選項 | 影響 |
| --- | --- |
| **(a) 只記錄於 `cleaning_report.md`** | 最小變更；RAG 回答「X 怎麼合成」時無材料可引，需靠 §3.2 拒答機制 |
| **(b) 另建 ADR-003** | 留下架構決策記錄；需寫新 ADR 文件 |
| **(c) 回 [3] 補抽** | 依 T5 評估：**重抽無法取回材料**（材料在圖片裡，任何 `output_format` 都抽不到）。此選項**不可行** |

### T11.3 RAG 回答「X 怎麼合成」時的行為（列為待決）

依 `AGENTS.md` §3.2：回答只能依據實際檢索到的 chunks。若材料不在 chunk 裡，正確行為是回答「目前官方文件不足以確認」或標註資料缺失。**具體措辭與是否加註「配方資訊在官方文件的圖片中」屬待決事項。**

---

## T12 決策表更新

**狀態：已確認**

更新原則：每項只寫**選項／影響／證據來源**。若證據明顯偏向某選項，以「**觀察**」標示事實（**不使用「建議」字眼**）。

| # | 決策事項 | 選項 | 影響 | 證據 |
| --- | --- | --- | --- | --- |
| 1 | **R4 匹配策略** | (a) `strip() ∈ LABELS` 精確白名單<br>(b) 只在 `Recipe`／`Recipes` 錨點後刪類型標籤<br>(c) 依上下文（後接完整句子=標題，相鄰標籤=噪音） | (a) 刪 174 行，誤刪風險集中於 ` Charger`；<br>(b) 只刪 34 行，**漏 95 行**（連續標籤頁）；<br>(c) 邏輯最複雜，需定義「完整句子」 | T1.3、T1.4、T1.5 |
| 2 | **黏合 token 處理** | (a) 只在行尾比對 token<br>(b) token 出現即處理（不論位置） | (a) **漏 `RecipesCrafting` 4/4**（全在行中）與 `RecipeCrafting` 1/9；<br>(b) 全覆蓋，但需確認 token 後是否還有合法內容 | T2.3 |
| 3 | **規則執行順序** | (a) R1→R2→R3→R4<br>(b) R1→R2→R4→R3 | (a) `Recipe` 會被 R3 併入正文（terminals idx45 實證）；<br>(b) 先刪標籤避免併入 | T3 |
| 4 | **是否回 [3] 重抽** | (a) `include_formatting=True`（json 模式）<br>(b) 改 `output_format="markdown"`<br>(c) 不重抽，[4] 全部處理 | (a) **完全無效**（T5.3 實證：`##`=0、空行=0）；<br>(b) 修復 `##`（energy 2、upgrade_cards 10），但**不修黏合／標籤／游離 `-`**，且引入 24 頁無 H1、17 頁多 H1、`## Recipe` 噪音標題；<br>(c) 維持現況，[4] 承擔全部清理 | T5.3、T5.4、T5.5、T5.7 |
| 5 | **alias 機制** | (a) frontmatter aliases + fail-fast<br>(b) 保留但 warning<br>(c) 只記錄於 report，不寫 frontmatter | **無任何已實作程式讀 alias**（T6.1）；<br>(a) 對未實作契約先設硬約束；<br>(c) frontmatter 保持最小，與 §7 一致 | T6.1、T6.2 |
| 6 | **空 body 處置** | (a) 仍輸出 .md<br>(b) 跳過並記 report<br>(c) 中止 | 模擬後**無空頁**，但 `decorative_sky_stone`(81)／`decorative_certus`(95) 極短；<br>(c) 會連累 119 頁正常頁 | T7.1、T7.2 |
| 7 | **R3 是否列為「資料不異動」明文例外** | (a) 列為例外（允許換行正規化）<br>(b) 不列（R3 不得變更任何字元） | (a) 與 §3.1「資料不異動」需明確措辭協調；<br>(b) 則 R3 只能刪不能改，合併句子的操作需另行授權 | T4（字元守恆 56/56 通過，但 R3 的「合併」確實改變了字元順序） |
| 8 | **首行標題去重的範圍** | (a) 只處理 line0 == title（97 頁）<br>(b) 加上 title 前綴切割（21 黏合頁）<br>(c) 只記錄不處理 | (a) 21 頁的 title 仍嵌在正文開頭；<br>(b) 需處理 `The Crank` 與 `The crank` 的大小寫／切點問題（`crank.json` 的 title 前綴後接 `The crank is...` 小寫開頭） | T0.3、T2.4 |
| 9 | **stub 頁（p2p-tunnels／quantum-bridge）** | (a) 輸出 .md<br>(b) 跳過並記 report<br>(c) 中止 | 排除後**無其他頁失去意義**（引用都是知識內容，真內容在 items-blocks-machines 版）；<br>注意 `ae2-mechanics/p2p-tunnels`（stub）與 `items-blocks-machines/p2p_tunnels` 是**不同頁、不同內容** | T7.3、T7.4 |
| 10 | **C 型頁（getting-started）line0** | (a) 視為站名殘留刪除<br>(b) 保留為正文 | L0 是**版本宣告完整句**（`The following information only applies to ... 1.20 and newer.`），**不是** `Applied Energistics 2` 站名；<br>(a) 會刪掉有效 scope 資訊 | T7.3 |
| 11 | **` Charger`（guide.json L5）判定** | (a) 噪音標籤刪除<br>(b) 合法內容保留 | 前為 `Recipe`，後為檔案結束；無法從現有資料判定 | T1.2 |
| 12 | **frontmatter 序列化方式** | (a) 沿用 `_yaml_scalar`<br>(b) 引入 PyYAML | (a) 121 title round-trip **0 失敗**；已知弱點（`\n`／數字樣／布林樣）在本語料 0 觸發；<br>(b) 需新增依賴（§16 須授權） | T8.1、T8.2 |
| 13 | **cleaned MD 換行** | (a) `newline="\n"` 強制 LF<br>(b) 維持現況（Windows CRLF） | (b) 跨平台重跑**不 byte-identical**；[3] 的 readable .md 已是 CRLF | T8.3 |
| 14 | **配方材料遺失** | (a) 只記 report<br>(b) 另建 ADR-003<br>(c) 回 [3] 補抽 | (c) **不可行**（材料在圖片裡，任何 output_format 都抽不到）；<br>4 頁完全無材料詞，其餘 40 頁無法驗證 | T11.1、T5.7 |
| 15 | **`section` 恆空問題** | (a) 不處理<br>(b) [4] 把裸標題升級為 `##`<br>(c) 依 T5.5 改 markdown 模式 | 121 頁全無 `##`；`MarkdownHeaderTextSplitter` 對真實資料恆產出「frontmatter junk + 整頁正文」2 chunk；<br>(b) 升級規則本身就是噪音規則（§16）；<br>(c) 引入多 H1 與 `## Recipe` 噪音 | T5.4、T5.5、T5.7 |
| 16 | **`upgrade_cards` 多段表格相鄰** | (a) 處理（段間插空行）<br>(b) 不處理 | 5 段表格無空行相鄰 → Markdown 渲染合併成單一表格，段間分隔行與重複表頭變成資料行；<br>**視覺可讀，語意被合併** | `onetime-report.md` §3.2 |
| 17 | **` Recipes`／`Recipe` 錨點本身** | (a) 與類型標籤一起刪<br>(b) 保留 | 錨點行在 T1.4 (b) 策略中被計為 45 行；<br>`## Recipe` 在 markdown 模式下會成為標題（T5.5） | T1.4、T5.5 |

**觀察**（事實標示，非建議）：

- 決策 #4：`include_formatting=True` 對 json 輸出**完全無效**（6 頁實證，`##` 與空行計數皆 0），且 `markdown` 模式**不修復**黏合／標籤／游離 `-` 三項——這三項只能在 [4] 處理。
- 決策 #2：`RecipesCrafting` **4/4 在行中**，行尾正則必然漏掉。
- 決策 #5：**無任何程式碼讀取 alias**，[5]／[6] 皆未實作。
- 決策 #6：模擬後**無空頁**，最短 77 字元（stub 頁）。
- 決策 #12：`_yaml_scalar` 對 121 title **0 失敗**。

---

## 需人工決定彙整

| # | 事項 | 選項 | 影響 | 證據題號 |
| --- | --- | --- | --- | --- |
| 1 | R4 匹配策略 | 精確白名單／錨點後刪／上下文判斷 | 見 T12 #1 | T1.3–T1.5 |
| 2 | 黏合 token 處理位置 | 行尾／行中皆處理 | 見 T12 #2 | T2.3 |
| 3 | R3／R4 執行順序 | R3 在前／R4 在前 | 見 T12 #3 | T3 |
| 4 | 是否回 [3] 重抽 | 不重抽／`include_formatting`／`markdown` | 見 T12 #4 | T5.3–T5.7 |
| 5 | alias 機制 | fail-fast／warning／不寫 frontmatter | 見 T12 #5 | T6.1–T6.2 |
| 6 | 空 body 處置 | 輸出／跳過／中止 | 見 T12 #6 | T7.1–T7.2 |
| 7 | R3 是否為「資料不異動」例外 | 列例外／不列 | 見 T12 #7 | T4 |
| 8 | 首行標題去重範圍 | 只 line0／加前綴切割／不處理 | 見 T12 #8 | T0.3、T2.4 |
| 9 | stub 頁處置 | 輸出／跳過／中止 | 見 T12 #9 | T7.3–T7.4 |
| 10 | getting-started line0 | 刪／保留 | 見 T12 #10 | T7.3 |
| 11 | ` Charger` 判定 | 噪音／內容 | 見 T12 #11 | T1.2 |
| 12 | frontmatter 序列化 | `_yaml_scalar`／PyYAML | 見 T12 #12 | T8.1 |
| 13 | cleaned MD 換行 | LF／現況 | 見 T12 #13 | T8.3 |
| 14 | 配方材料遺失補救 | report／ADR-003／不可行 | 見 T12 #14 | T11.1 |
| 15 | `section` 恆空 | 不處理／升級 `##`／改 markdown | 見 T12 #15 | T5.4–T5.5 |
| 16 | `upgrade_cards` 多表格相鄰 | 處理／不處理 | 見 T12 #16 | `onetime-report.md` §3.2 |
| 17 | `Recipe`／`Recipes` 錨點去留 | 一起刪／保留 | 見 T12 #17 | T1.4 |

---

## 未驗證項目與原因

| 項目 | 原因 |
| --- | --- |
| R1–R5 的**規則原文** | 計畫文件未在本儲存庫或已存取 session 中找到（見開頭警告）。T3 的規則定義是我自行模擬，**非計畫原文** |
| 外部審查「缺損 1–6」的**具體內容** | 文件不存在（`architecture-assessment.md` 不在磁碟上） |
| alias 的**定義與資料來源** | 計畫未取得；無法知道 alias 從哪產出（錨文字？title 衍生？） |
| **「53 頁 193 行」的 193** | 只能重現 53 頁；行數最接近為 197（`LABELS ∪ KW`）。4 行差異無法用任何條件組合解釋 |
| 40 頁「材料在圖片裡」的**確認** | 圖片不在資料裡，無法驗證材料是否真的存在於原網頁圖片中（只能從「正文無材料詞 + 有標籤」推導） |
| `terminals` L48–51（`- Crafting` 等 4 行）的**性質判定** | 是 UI 模式切換清單，既像合法內容又帶標籤特徵；需人工判定 |
| `include_formatting` 對**全部 124 頁**的影響 | 只測了 6 頁（任務指定的頁）；全量測試對「無效」結論無額外價值（6 頁已全數無效），未執行 |

---

## 追加驗證（2026-10-12 第二輪，依人工修訂意見重驗）

本節回應人工對計畫的 8 處修訂與 3 項重驗要求，全部為**唯讀實測**。此外順手做了 DOM 層 peek，因它直接決定排程問題。

### V1 版本徽章殘留 grep（重驗 #3）

| 檢查 | 結果 |
| --- | --- |
| 121 頁 extracted text 含獨立行 `Minecraft 1.21.1 [`／`change`／`]` | **僅 2 頁**（`ae2-mechanics/p2p-tunnels.json`、`ae2-mechanics/quantum-bridge.json`）＝ stub 頁 |
| 124 頁 raw HTML 同時含 `Minecraft 1.21.1` 與 `change` | **0 / 124** |

**事實結論**：「傳統噪音為 0」的結論**成立**——版本徽章是 mkdocs-versioning 的 **JS 注入內容**，不在靜態 HTML 裡，因此不可能出現在其他 119 頁。R2 的 stub 排除已涵蓋這 2 頁，無需額外規則。

### V2 R4b 假設驗證（重驗 #2）— **21/21 成立**

對 21 頁單行頁，自第一個 `Recipe`／`Recipes` 起將剩餘字串貪婪切成標籤 token（容許 token 間空格）：

| 結果 | 頁 |
| --- | --- |
| 尾端**完全由標籤 token 組成** | **19** |
| 無 `Recipe` token（R4b 無作用） | 2（`main-network`、`matter_ball`） |
| **失敗（行尾含非標籤內容）** | **0** |

19 頁的 token 序列（逐頁）：

| 頁 | token 序列 |
| --- | --- |
| `certus_quartz_crystal_charged` | `Recipe`, `Charger` |
| `certus_quartz_dust`／`ender_dust`／`fluix_dust`／`sky_dust` | `Recipe`, `Inscriber` |
| `charged_staff`／`crank`／`fluix_block`／`fluix_pearl`／`quartz_block`／`sky_stone_tank`／`spatial_pylon`／`wireless_receiver` | `Recipe`, `Crafting` |
| `fluix_upgrade_smithing_template` | `Recipe`, `Crafting (Shapeless)` |
| `decorative_fluix` | `Recipes`, `Crafting`, `Crafting`, `Crafting` |
| `quartz_fixture`／`quartz_glass` | `Recipes`, `Crafting`, `Crafting` |
| `illuminated_panels` | `Recipes`, `Crafting (Shapeless)`, `Crafting (Shapeless)`, `Crafting (Shapeless)` |
| `meteorite_compass` | `Recipe`, `Charger` |

**⚠ R4b 正則的關鍵細節**：黏合 token 有**兩種空格形態**，必須同時容許：

| 形態 | 次數 | 例子 |
| --- | --- | --- |
| **無空格** | 13 | `RecipeCrafting`（9）、`RecipesCrafting`（4） |
| **含空格** | 6 | `Recipe Charger`（2）、`Recipe Inscriber`（4） |

若只寫 `RecipeCrafting` 類的無空格 pattern，會漏掉全部 6 個含空格案例（含 `guide.json` 判定相關的 `Charger`）。第一次跑漏掉 6 頁就是這個原因。

### V3 R1-B 前綴切割守衛（剩餘首字元為大寫 ASCII）

21 頁 title 前綴切除後，**21/21 剩餘首字元皆為大寫 ASCII**（`A`／`T`／`M`／`F`／`I`／`U`）。例：`crank.json` title `The Crank` → 剩餘 `The crank is used to power machines...`（首字元 `T`）。守衛在現有資料上不會誤觸發。

### V4 T4 檢查式修正的佐證（修訂 #7）

全庫含 `Co-Process` 連字號的**內容行**：

| 頁 | 行內容（節錄） |
| --- | --- |
| `ae2-mechanics/autocrafting.json` | `- (Optional) Crafting Co-Processing Units, they make the system send out ingredi...` |
| `items-blocks-machines/crafting_cpu_multiblock.json` | `Crafting Co-Processing Unit` |
| `items-blocks-machines/crafting_cpu_multiblock.json` | `(Optional) Crafting co-processors make the system send out ingredient batches fr...` |

**事實**：「移除所有 `-`」的守恆檢查會吞掉 `Co-Processing`／`co-processors` 的連字號。人工修訂改為「扣掉**審計表記錄的游離標記**後，以空白正規化比對」是**必要的**。補充說明：我原本的驗證**只施加於 56 處 `strip() == '-'` 的行**（這些行內容恆為空，連字號問題不適用），並非施加於整頁；作為通用檢查式，原寫法確實有缺陷。

### V5 `Quantum Link Chamber` 候選資格更正

`Quantum Link Chamber`（20 字）**不含任何 KW** → 不在 Set C、不在 LABELS → 修訂後的整行白名單 R4 **不會刪它**。已在 T1.2 更正。它與 `Recipe` 相鄰（`quantum_bridge.json` L5/L6）因此**不需**任何防護。

### V6 DOM 層 peek（影響修訂 #5 與排程決策）

| 檢查 | 結果 |
| --- | --- |
| 網站技術 | **Next.js CSR**（`<div id="root">`、`data-nimg`、`_next/static`），但 raw HTML **內含 React 序列化 payload**，非空殼 |
| `aria-description` 存在頁數 | **102 / 124** |
| `aria-label` 存在頁數 | 124 / 124 |
| 配方類型標籤的 DOM 結構 | `recipe_recipeBoxLayout__WIUGR` 的**第一個 div** = `<img aria-description="<站名>"> <標籤文字>`，接著是 `recipe_ingredientBox__B_LNE` |
| 配方材料的 DOM 結構 | 材料在 `recipe_ingredientBox__B_LNE` 內，`<img aria-description="<材料名>">` |

**配方類型欄的 DOM 對應**（這直接驗證修訂 #5）：

| 頁 | 配方類型欄 `aria-description` | 類型標籤文字 | 材料（aria-description） |
| --- | --- | --- | --- |
| `crank.html` | `Crafting Table` | `Crafting` | `Stick`×4, `Copper Ingot`（結果 `Wooden Crank`） |
| `guide.html` | **`Charger`** | **` Charger`** | `Book`（結果 `Guide`） |
| `fluix_pearl.html` | `Crafting Table` | `Crafting` | `Fluix Dust`×4, `Fluix Crystal`×4, `Ender Pearl`（結果 `Fluix Pearl`） |

**事實結論（修訂 #5 升級）**：`guide.json` L5 的 ` Charger` 在 DOM 上是 `recipe_recipeBoxLayout` 的**配方類型欄**（`aria-description="Charger"`），與 `Crafting`／`Inscriber` 是**同一個結構位置**。修訂 #5「Charger 判定為噪音」從「文字類比」升級為 **DOM 結構驗證**。且 `LABELS` 白名單不是任意校準——它對應 DOM 的配方類型欄，**結構上有依據**。

**事實結論（材料可恢復性）**：配方材料（`Stick`、`Copper Ingot`、`Ender Pearl`…）**確實在 raw HTML 的 `aria-description` 裡**，trafilatura 抽不到是因為它們在 `<img>` 的屬性中、不是文字節點。**「1125 個材料遺失」的說法在 DOM 層有實質依據**（數字本身依計畫定義，我無法驗證）。

### V7 重驗 #1 的狀態：**阻塞**

「以計畫原文的 R3 重跑 56 處，比較 R3→R4 與 R4→R3」——**我沒有計畫的 R3 原文**（見開頭警告）。我自行模擬的 R3 結論（T3）**不能**用來驗證計畫的「54 單行合併／1 刪除／1 多行合併」。**需人工提供 R3 的規則文字或計畫檔案**，此項才能完成。

---

## 結束回報

### 暫存檔清理

- `/tmp/t5/`：已清除（所有 trafilatura／DOM 實驗都在記憶體中完成，未寫入任何實驗輸出）
- **未在 repo 內建立任何暫存檔**

### Git 狀態（實測）

```
On branch pipeline-stage-6
Untracked files:
	docs/plans/
nothing added to commit but untracked files present
```

- HEAD：`12ab658 docs: README 開發狀態表標記 [2]-[3] 已實作`
- **無 commit、無 push、無分支切換**；僅新增 `docs/plans/[4]-gap-evidence.md` 一個檔案
- `src/`、`data/`、`reports/`、`sources.json`、`ARCHITECTURE.md`、`AGENTS.md`、`requirements.txt` **全未修改**
