---
name: git-auto-branch
description: 自主開發時管理任務層級的工作 Branch。任務開始時確認或建立並切換單一工作 Branch，開發期間持續使用、不得自行建立新 Branch，任務結束不得自行 Merge。凡是在專案內開始任何自主開發、修改或重構任務，即使使用者沒有明說，也應先套用本 skill 確認 Branch 策略。
---

# Git Auto Branch

負責任務層級的 Branch 管理。套用於自主開發任務，確保整個任務期間只使用一個主要工作 Branch，並把 Merge 決策保留給使用者。

## 任務開始

- 確認目前 Repository 與 Branch。
- 若已有目前任務對應的工作 Branch，直接使用。
- 若沒有，建立新的工作 Branch 並切換。
- 一個任務原則上只使用一個主要工作 Branch。

## 開發期間

- 持續使用目前任務的工作 Branch。
- 不得因修改其他檔案、API 或發現額外修改而自行建立新 Branch。
- 只有開始新的獨立任務，或使用者明確要求拆分時，才建立新 Branch。

## Merge

- 不得自行 Merge。
- 不得自行將工作 Branch 合併至 `main`、`master` 或其他正式 Branch。

## 權限邊界

可自動執行：建立任務 Branch、切換任務 Branch。

不得自行執行：Merge、刪除他人 Branch、重寫共享 Branch 歷史、執行高風險 Git 操作。

若專案已有 Git workflow 規範，優先遵循專案規範。
