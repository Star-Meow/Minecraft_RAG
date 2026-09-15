---
name: verification-first-modular
description: 開發新功能或修改程式行為時使用：先拆解可驗證行為、定義 input/output contract 與成功/失敗條件、建立獨立 validation 並先證明其能辨識失敗，再實作最小模組，並以同一套 validation 驗收。適用於 pipeline stage、data transformation、database integration、retrieval、query logic、UI logic、外部服務整合等任何程式生成任務；純文件修改或無行為變更的整理不適用。
---

# Verification-First Modular Engineering

## 1. Purpose

規範 Agent「如何進行程式開發」的思考順序與工作流程：

```text
需求 → 生成正式程式 → 再想辦法驗證          # 禁止
需求 → 定義驗證標準 → 驗證標準可辨識失敗 → 實作 → 驗收   # 採用
```

目標：先建立可獨立驗證的標準，再生成正式程式；同時讓程式解耦與模組化，使驗證、替換與錯誤定位更容易。

## 2. When to Use

- 適用：任何產生或修改程式行為的任務——pipeline stage、data transformation、database integration、retrieval、query logic、UI logic、external service integration。
- 不適用：純文件修改、無行為變更的整理（遵循 AGENTS.md 即可，不需要本流程）。

## 3. Core Principles

1. **Verification First**：寫正式程式之前，先回答——這個功能需要保證什麼？哪些行為可客觀驗證？正常情況的 acceptance criteria 是什麼？錯誤輸入應如何失敗？能自動化驗證時優先建立自動化驗證。
2. **Validation 必須獨立**：驗證只依賴 input 與外部可觀察 output（`input → implementation → output → independent validation`），不讀取 implementation 的內部旗標或私有狀態。驗證與實作解耦：implementation 換一種寫法，同一套驗證仍然適用。
3. **先證明 Validation 能發現錯誤**：正式實作前，用故意不符 contract 的簡化實作、fixture 或暫時輸入執行驗證，確認它會失敗。目的不是測試測試本身，而是避免驗證標準隨 implementation 被動形成。無法合理建立時，書面說明原因並改提人工驗證計畫，不得假裝完成。
4. **Modular by Default**：寫程式前先劃分功能邊界——單一責任、輸入輸出清楚、side effect 集中、外部依賴可隔離、可獨立驗證、可單獨替換、錯誤可定位到具體階段。
5. **先 Contract 後 Implementation**：需求模糊處先轉成 input contract / output contract / invariants / failure conditions / acceptance criteria；涉及架構或使用者未決事項時，停止並提問（AGENTS.md §16），不自行假設。
6. **防止「為了通過驗證而寫程式」**：implementation 通不過既定 validation 時，修正 implementation；禁止修正 validation、縮小範圍或包裝結果。

## 4. Required Workflow（依序執行，不得跳過）

1. **Understand**：讀取相關模組與既有 contract，確認需求行為。
2. **Decompose**：把需求拆解成可客觀驗證的行為單位。
3. **Define Contract**：為每個單位定義 input / output / invariants / failure conditions / acceptance criteria。若發現需求不足以形成可靠驗證標準——停止，列出需要使用者決策的問題，不先寫程式。
4. **Design Independent Validation**：為每個單位設計驗證；驗證只看 input 與 output，不看內部狀態。
5. **Verify Validation Can Detect Failure**：以故意錯誤的簡化實作或 fixture 執行驗證，確認會失敗並記錄失敗輸出；無法建立時書面說明原因。
6. **Implement Minimal Modules**：依 Modularization Rules 實作；不更動已定義的 contract 與 validation。
7. **Run Validation**：執行全部驗證，記錄實際結果。
8. **Fix Implementation**：失敗時只修正 implementation 與其設計；validation 依第 3 步的 contract 維持不變。
9. **Re-run Validation**：修正後重新執行**完整**驗證（不得只跑先前通過的部分），直到全數通過。
10. **Report Actual Results**：依 AGENTS.md §17 回報 contract、validation 內容與實際結果、修正過的問題、仍未驗證項目。

## 5. Validation Design Rules

- 驗證外部可觀察行為（input → output）；禁止以 implementation 的內部旗標、私有方法或「它自己說成功」作為通過依據。
- 驗證標準在實作前依 contract 制定；不得在看到 implementation 輸出後才制定、放寬或改寫。
- 正常輸入：acceptance criteria 逐條可客觀判定（值、格式、結束碼、筆數、副作用狀態）。
- 錯誤與邊界輸入：驗證「以契約定義的方式失敗」——明確錯誤訊息、拒絕處理、非零結束碼；不得只驗證「沒有崩潰」。
- 解耦：validation 與 implementation 分開存放或分開執行；implementation 重寫時 validation 不需修改。
- 工具中立：以 script、assert、黃金輸出比對、結束碼檢查等方式皆可；專案未設定 pytest／CI 前不得假設其存在（AGENTS.md §13）。
- 自動化優先；無法自動化的項目明確列為人工驗證步驟並寫入回報。

## 6. Modularization Rules

- 先劃分功能邊界，再開始寫程式：每個模組單一責任、輸入輸出明確、side effect 集中在少數明確位置、外部依賴可隔離或注入。
- 每個模組必須能獨立套用第 4 步的驗證；錯誤發生時可定位到具體模組與階段。
- 模組應可單獨替換或修改，而不要求改動其他模組的驗證。
- **禁止為模組化而模組化**：不新增無實際作用的 class、interface、wrapper 或檔案。解耦的目的是可測試性、可維護性與錯誤定位能力，不是抽象層數。

## 7. Anti-patterns（一律禁止）

- 先寫正式程式、事後補驗證；或驗證標準隨 implementation 的輸出浮動調整。
- 自我循環驗證：validation 直接呼叫 implementation 的內部判斷或讀取其內部旗標。
- 降低 assertion 標準、縮小測試資料、跳過 edge cases、把錯誤轉成成功結果（AGENTS.md §13）。
- validation 失敗時修改 validation 而不是修改 implementation。
- 跳過 Workflow 第 5 步，未證明驗證能失敗就宣稱驗證可用。
- 以內部狀態冒充外部行為驗證，或宣稱未執行的驗證為通過。
- 為了「看起來模組化」堆疊無意義的抽象層。

## 8. Definition of Done

- [ ] 每個行為單位有書面 contract：input / output / invariants / failure conditions / acceptance criteria。
- [ ] validation 先於 implementation 存在；第 5 步已證明其能辨識失敗，或附書面理由說明為何無法建立。
- [ ] implementation 通過**全部** validation，且過程中未修改 validation 標準或範圍。
- [ ] 模組符合 Modularization Rules；無多餘抽象。
- [ ] 回報包含：contract、validation 內容與實際結果、修正過的 implementation 問題、仍未驗證項目（AGENTS.md §17）。

## 9. 與 AGENTS.md 的關係

- 本 skill 是 AGENTS.md §12（Change Policy）與 §13（Validation and Anti-False-Success）的**執行流程細化**：§13 定義「必須遵守什麼」，本 skill 定義「按什麼順序做」。
- 不取代、不覆寫 AGENTS.md 的任何永久規範、pipeline contract、validation matrix 或架構決策流程；衝突時依 AGENTS.md §2 Rule Priority 以 AGENTS.md 為準。
- 架構、contract 或 dependency 變更仍走 AGENTS.md §16（Grill-me mode），由使用者決策。
