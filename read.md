# 建立 Git Commit / Branch 全域 Skills

請完整建立並部署 Git 相關全域 Skills，目的在於讓 Agent 能在自主開發時，自動管理「任務 Branch」與「開發 Commit」，但保留 Merge 的人工決策權。

## 1. 建立前檢查

先確認目前 Skill 系統：

* Skill 規格與合法 YAML frontmatter
* 全域 Skill 目錄結構
* 既有 Git / development 類 Skill
* Skill discovery / invocation 機制
* validator / lint / install / registration 方式

不得猜測 Skill 格式，優先依目前環境既有規範建立。

## 2. 建立 Skills

建立兩個全域 Skill：

* `git-auto-branch`
* `git-auto-commit`

### git-auto-branch

負責任務層級的 Branch 管理：

**任務開始：**

* 確認目前 Repository 與 Branch。
* 若已有目前任務對應的工作 Branch，直接使用。
* 若沒有，建立新的工作 Branch 並切換。
* 一個任務原則上只使用一個主要工作 Branch。

**開發期間：**

* 持續使用目前任務 Branch。
* 不得因修改其他檔案、API 或發現額外修改而自行建立新 Branch。
* 只有開始新的獨立任務或使用者明確要求拆分時，才建立新 Branch。

**Merge：**

* 不得自行 Merge。
* 不得自行將工作 Branch 合併至 `main`、`master` 或其他正式 Branch。

### git-auto-commit

負責開發期間的 Commit 與任務完成後的 Push：

**開發期間：**

* 可依具邏輯意義的完成單位自動建立 Commit。
* Commit 前確認變更與目前任務相關。
* 優先執行必要的 test / lint / type check。
* 遵循專案既有 Commit message 規範。

**任務完成：**

* 確認必要修改均已 Commit。
* 將目前工作 Branch Push 至 Remote。
* 不得自行 Push 至 `main`、`master` 或其他正式 Branch。

**Merge：**

* 不得自行 Merge。
* Merge 必須由使用者決定。

## 3. 權限邊界

Agent 可以自動：

```text id="a4v8qm"
建立任務 Branch
切換任務 Branch
git add
git commit
git push 工作 Branch
```

Agent 不得自行：

```text id="6z5tup"
Merge
Push main / master
刪除他人 Branch
重寫共享 Branch 歷史
執行高風險 Git 操作
```

若專案已有 Git workflow 規範，優先遵循專案規範。

## 4. 驗證與部署

建立完成後：

1. 執行 Skill validator / lint。
2. 完成必要的 install / registration / deployment。
3. 確認兩個 Skill 可被全域 discovery。
4. 實際載入確認內容可正常解析。
5. 若驗證失敗，讀取錯誤、定位原因、修正後重新驗證。
6. 若遇到 JSON / SSE parsing error，先判斷是否為工具或 transport 層問題。

不得因第一次 validation failure 直接停止。

## 5. Smoke Test

模擬 Agent 執行一個新開發任務：

```text id="l2g7pq"
任務開始
↓
確認目前 Branch
↓
建立 / 使用任務 Branch
↓
修改程式
↓
Commit
↓
繼續開發
↓
任務完成
↓
Push 工作 Branch
```

確認 Agent 不會在同一任務期間反覆建立 Branch，也不會自行 Merge 至正式 Branch。

Smoke Test 不得修改實際專案程式碼或造成不必要的 Remote 變更。

## 6. 完成條件

只有確認以下全部成立後才回報完成：

* 兩個 Skill 已建立
* YAML frontmatter 合法
* 已通過 validator / lint
* 已完成必要 registration / deployment
* Agent 可以 discovery 到兩個 Skill
* Agent 可以正常載入
* Branch lifecycle 符合任務邊界
* Commit / Push 行為符合權限限制
* Merge 保持人工決策

最終回報僅包含：

1. Skill 名稱
2. Skill 檔案位置
3. Invocation 方式
4. Commit / Branch 行為
5. 驗證結果
6. 限制或未完成事項
