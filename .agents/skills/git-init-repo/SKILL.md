---
name: git-init-repo
description: 當專案中偵測不到任何 Git 資料（尚未 git init、無 .git、無 remote）時，協助建立 Git repository；建立前必須向使用者詢問名稱、remote、權限與認證方式。凡是在工作目錄發現不是 Git repo 而任務又需要版控時，一律套用本 skill，不得擅自 init。
---

# Git Init Repo

負責一個尚未被 Git 追蹤的專案的初始化。套用時機：Agent 於專案工作目錄執行 `git rev-parse --is-inside-work-tree`（或檢查 `.git`、`git remote`）後，確認專案沒有 Git 資料。

## 套用時機（前提偵測）

在開始建立前，先確認下列條件未滿足，才呼叫本 Skill：

- 不是 Git repo（`git rev-parse --is-inside-work-tree` 回報非 true）。
- 無 `.git` 目錄。
- 無任何 remote（`git remote -v` 為空）。

若已有 repo 或 remote，不適用本 Skill，交由既有 Git 流程處理（例如 git-auto-branch / git-auto-commit）。

## 建立前必須詢問使用者

Agent 不得擅自決定下列資訊，必須逐一以提問方式向使用者確認後才能動手。若使用者未明確回答，不得繼續建立。

1. **Repo 名稱**：本地資料夾或遠端 repo 的名稱。
2. **Remote 設定**：是否要連到遠端（例如 GitHub），以及遠端 URL；若只要本地追蹤，明確確認「僅本地」。
3. **權限／可見性**：遠端 repo 要設為 private 或 public（若適用）。
4. **認證方式**：由使用者決定如何提供 GitHub credential（例如 OAuth / gh CLI / PAT token）。永不要求、輸出或儲存任何 token、密碼或私鑰。

提問時同時說明每項選擇的影響，並依使用者回答的最小範圍執行。

## 建立流程

- 依確認內容執行 `git init`（可用 `-b <main>` 設定初始分支名稱，需先確認）。
- 視需要 `git add` 初始內容並建立初始 commit；commit 前先確認要納入哪些檔案，必要時先設定 `.gitignore`。
- 若使用者要求連線 remote，依其提供的 URL 執行 `git remote add`；推送前先確認認證可用。
- 僅推送使用者指定允許的分支（預設不推 `main`/`master` 以外的分支，也不自行建立多個分支）。

## 權限邊界

可自動執行（在使用者確認後）：`git init`、建立初始 commit、`git remote add`、把允許的分支 push 到使用者指定的 remote。

不得自行執行：未經詢問即建立遠端 repo、幫使用者選擇權限或認證方式、`git push` 至使用者未指定的位置、`git merge`。

## 完成回報

回報時列出：repo 名稱、是否本地/遠端、remote URL、建了哪些 commit、尚未完成（如等待使用者提供認證）。未完成部分交由使用者決定後再繼續。
