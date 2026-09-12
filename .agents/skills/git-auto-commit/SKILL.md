---
name: git-auto-commit
description: 自主開發期間依邏輯完成單位自動建立 Commit，任務完成後將工作 Branch Push 至 Remote；不自行 Merge，不 Push 正式 Branch。凡是在開發過程中要提交變更或推送分支，即使使用者沒有明說，也應依本 skill 的權限邊界行動。
---

# Git Auto Commit

負責開發期間的 Commit 與任務完成後的 Push。套用於自主開發任務，讓提交節奏自動化，同時把 Merge 與正式 Branch 的決策保留給使用者。

## 開發期間

- 可依具邏輯意義的完成單位自動建立 Commit。
- Commit 前確認變更與目前任務相關。
- 優先執行必要的 test / lint / type check。
- 遵循專案既有 Commit message 規範。

## 任務完成

- 確認必要修改均已 Commit。
- 將目前工作 Branch Push 至 Remote。
- 不得自行 Push 至 `main`、`master` 或其他正式 Branch。

## Merge

- 不得自行 Merge。
- Merge 必須由使用者決定。

## 權限邊界

可自動執行：`git add`、`git commit`、`git push` 工作 Branch。

不得自行執行：Merge、Push `main` / `master`、刪除他人 Branch、重寫共享 Branch 歷史、執行高風險 Git 操作。

若專案已有 Git workflow 規範，優先遵循專案規範。
