---
name: dev-environment
description: 在開始本機開發、修改、測試或除錯前使用，快速取得 runtime、工具、專案邊界與安全編輯規範，避免重複探索環境。凡是要在專案內執行指令、安裝依賴或設定開發環境，即使使用者沒有明說，也應先載入本 skill。
---

# Dev Environment

在進入任何開發、修改、執行或除錯工作前，先套用本 Skill 的固定環境認知。若內容與實際狀態不一致，以實際檢查結果為準並向使用者說明差異。

## Runtime And Tools

- Primary runtime: Python `3.9.7`.
- Installed package manager: `pip 25.0`.
- Available tooling: Git `2.46.0.windows.1`, Node.js `v24.18.1`, npm `11.16.0`, ripgrep, and PowerShell.
- Do not assume additional runtimes, frameworks, build systems, test suites, linters, or application entrypoints exist unless the project explicitly configures them.

## Workspace And Safety Boundary

- Start from the current working directory as the project root.
- All reads, searches, creation, modification, and command execution remain inside that root by default.
- Treat paths outside that root, other repositories, user-level settings, system settings, external drives, and network resources as out of scope unless explicitly approved.
- Do not assume a directory is a Git repository; verify `.git` exists before using Git history or remote operations.
- Ask before hardware health checks, disk diagnostics, network configuration inspection, system logs, installed-software inventories, sensitive environment variables, credentials, or account information.
- Never request, output, or store API keys, passwords, tokens, private keys, or other secrets.

## Editing Rules

- Preserve UTF-8 encoding and original line endings when modifying existing text files.
- Prefer modular design with clear responsibilities and small testable functions.
- Change only the minimum area required by the task.
- Do not refactor, reformat, rename, or move unrelated code without approval.
- After changes, identify modified files and reasons; run only relevant tests when tests exist.

## Confirmation Required

- Installing packages or changing dependency versions.
- Creating top-level files, changing documented architecture, or introducing frameworks.
- Accessing paths outside the project root, modifying system settings, or reading sensitive environment variables.
- Arbitrary network requests.

## Fast Health Check

A minimal non-destructive check is sufficient before normal work:

```powershell
python --version
python -m pip --version
git --version
node --version
npm --version
rg --version
```

If a check fails, diagnose and report the concrete error instead of reinstalling tools or changing configuration automatically.
